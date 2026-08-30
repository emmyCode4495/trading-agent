"""
Continuous automation, two independent cadences:

  1. Full market scan (discover -> screen -> analyze -> rank) — the
     expensive cycle, since it runs the whole 5-agent pipeline per
     candidate symbol. Runs every `settings.run_interval_minutes`
     (default 15 — frequent enough to feel "continuously scanning", while
     staying well within any public exchange API's rate limits for a few
     dozen symbols).

  2. Open-position monitoring — cheap (one price lookup per open position),
     so it runs far more often, every `settings.position_check_interval_minutes`
     (default 2). This is what makes the win rate genuinely real-time: a
     position resolves the moment price actually reaches its target or
     invalidation, not on the next full hourly cycle.

`job_run_scan` and `job_evaluate_open_positions` are the shared building
blocks. Two ways to run them continuously:

  - Standalone process: `python -m app.scheduler` — for a headless/
    production deployment where the dashboard isn't necessarily running.
  - In-process background loop inside the API itself (see app/api.py's
    startup hook) — this is the default for local/dashboard use: just run
    `uvicorn app.api:app` and the agent scans continuously in the
    background while you watch the dashboard, no second process needed.

Run only ONE of these two at a time against the same database — running
both doubles the effective scan frequency and isn't harmful, but isn't
the intent either.
"""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler

from app import scan_state
from app.backtest import evaluate_open_positions
from app.config import settings
from app.notifiers.telegram import send_scan_summary
from app.scanner import run_scan

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scheduler")


def job_run_scan():
    scan_state.mark_scan_started()
    log.info("Scanning %s-quoted markets (min 24h volume %.0f)...",
              settings.scan_quote_asset, settings.scan_min_quote_volume_24h)
    try:
        result = run_scan()
    finally:
        next_at = datetime.utcnow() + timedelta(minutes=settings.run_interval_minutes)
        scan_state.mark_scan_finished(next_scan_at=next_at)

    if result["error"]:
        log.error("Scan aborted: %s", result["error"])
        return

    log.info(
        "Scan complete: %d markets discovered, %d passed liquidity screen, "
        "%d analyzed, %d opportunities surfaced",
        result["markets_discovered"], result["markets_screened"],
        len(result["symbols_analyzed"]), len(result["opportunities"]),
    )
    for opp in result["opportunities"]:
        log.info("  %s — %s, %s, confidence %d/100", opp["symbol"], opp["bias"], opp["direction"], opp["confidence"])

    sent = send_scan_summary(result["opportunities"])
    if settings.telegram_bot_token:
        log.info("Telegram delivery: %s", "ok" if sent else "failed")


def job_evaluate_open_positions():
    scan_state.mark_position_check()
    result = evaluate_open_positions()
    if result["wins"] or result["losses"] or result["expired"]:
        log.info(
            "Position check: %d open positions checked -> %d win(s), %d loss(es), %d expired",
            result["checked"], result["wins"], result["losses"], result["expired"],
        )


def main():
    scheduler = BlockingScheduler()
    scheduler.add_job(job_run_scan, "interval", minutes=settings.run_interval_minutes)
    scheduler.add_job(job_evaluate_open_positions, "interval", minutes=settings.position_check_interval_minutes)

    scan_state.set_scanner_running(
        True,
        scan_interval_minutes=settings.run_interval_minutes,
        position_check_interval_minutes=settings.position_check_interval_minutes,
    )

    log.info(
        "Starting scheduler: full scan every %d min, position check every %d min",
        settings.run_interval_minutes, settings.position_check_interval_minutes,
    )
    job_run_scan()  # run once immediately on startup
    job_evaluate_open_positions()
    scheduler.start()


def start_background(scheduler: "BackgroundScheduler | None" = None) -> BackgroundScheduler:
    """
    Used by app/api.py to run the same two jobs inside the API process
    itself, so `uvicorn app.api:app` alone gives continuous real-time
    scanning with no second process required. Both jobs fire once
    immediately (in a background thread, non-blocking to API startup) and
    then on their configured interval.
    """
    scheduler = scheduler or BackgroundScheduler()
    now = datetime.now()
    scheduler.add_job(job_run_scan, "interval", minutes=settings.run_interval_minutes, id="run_scan", next_run_time=now)
    scheduler.add_job(
        job_evaluate_open_positions, "interval",
        minutes=settings.position_check_interval_minutes, id="evaluate_open_positions",
        next_run_time=now,
    )
    scan_state.set_scanner_running(
        True,
        scan_interval_minutes=settings.run_interval_minutes,
        position_check_interval_minutes=settings.position_check_interval_minutes,
    )
    scheduler.start()
    return scheduler


if __name__ == "__main__":
    main()
