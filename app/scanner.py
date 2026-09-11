"""
Market Scanner — this is what makes the system autonomous instead of a
fixed-watchlist bot.

Every cycle:
  1. DISCOVER  — ask the exchange for every tradable pair (app/data adapters'
                 `list_markets`), not a config file.
  2. SCREEN    — drop illiquid/noisy pairs by 24h quote volume. This is a
                 cheap, no-agent-involved filter: hundreds of markets down to
                 a shortlist worth actually analyzing.
  3. ANALYZE   — run the full 5-agent pipeline (trend/momentum/structure/
                 risk/news -> decision engine) on each shortlisted symbol,
                 via app.pipeline.run_cycle, exactly as before per symbol.
  4. RANK      — sort analyzed symbols by confidence (WAIT calls excluded —
                 "no edge here" isn't an opportunity) and keep the top N.

A manual watchlist symbol (app.config.settings.symbols) is NOT an input to
any of this — it's a separate, optional drill-down exposed by
GET /api/report/latest?symbol=..., for when a person wants to check one
specific pair regardless of what the scanner surfaced.
"""
import logging
from datetime import datetime

from app.config import settings
from app.data import get_adapter
from app.models import ScanRun, get_session, init_db
from app.pipeline import run_cycle

log = logging.getLogger("scanner")


def discover_markets(adapter=None, quote_asset: str | None = None) -> list[dict]:
    """Step 1: ask the exchange what's tradable. No liquidity filtering here."""
    adapter = adapter or get_adapter()
    quote_asset = quote_asset or settings.scan_quote_asset
    return adapter.list_markets(quote_asset=quote_asset)


def screen_by_liquidity(
    markets: list[dict],
    min_quote_volume: float | None = None,
    max_candidates: int | None = None,
) -> list[dict]:
    """Step 2: cheap filter, no agents involved. Sorted most-liquid first."""
    min_quote_volume = settings.scan_min_quote_volume_24h if min_quote_volume is None else min_quote_volume
    max_candidates = settings.scan_max_symbols_to_analyze if max_candidates is None else max_candidates

    liquid = [m for m in markets if m.get("quote_volume_24h", 0) >= min_quote_volume]
    liquid.sort(key=lambda m: m["quote_volume_24h"], reverse=True)
    return liquid[:max_candidates]


def run_scan(
    adapter=None,
    quote_asset: str | None = None,
    min_quote_volume: float | None = None,
    max_candidates: int | None = None,
    top_n: int | None = None,
) -> dict:
    """
    Runs one full discover -> screen -> analyze -> rank cycle and persists a
    ScanRun summary. This is what the scheduler calls hourly, and what
    POST /api/scan/run calls on demand — there is no separate "autonomous"
    vs "manual" scan, just this one path.
    """
    adapter = adapter or get_adapter()
    quote_asset = quote_asset or settings.scan_quote_asset
    top_n = settings.scan_top_n_opportunities if top_n is None else top_n

    started_at = datetime.utcnow()
    error = None
    all_markets: list[dict] = []
    candidates: list[dict] = []
    reports: list[dict] = []

    try:
        all_markets = discover_markets(adapter, quote_asset=quote_asset)
        candidates = screen_by_liquidity(all_markets, min_quote_volume, max_candidates)

        for market in candidates:
            try:
                report = run_cycle(market["symbol"])
                report["quote_volume_24h"] = market["quote_volume_24h"]
                report["price_change_pct_24h"] = market["price_change_pct_24h"]
                reports.append(report)
            except Exception as exc:  # one bad symbol shouldn't sink the scan
                log.warning("Skipping %s after analysis error: %s", market["symbol"], exc)
    except Exception as exc:
        error = str(exc)
        log.error("Scan failed at discovery/screening stage: %s", exc)

    # Rank: confidence first, WAIT calls excluded — "no edge" isn't an
    # opportunity to surface, even if it was correctly identified as such.
    actionable = [r for r in reports if r["direction"] != "WAIT"]
    actionable.sort(key=lambda r: r["confidence"], reverse=True)
    opportunities = actionable[:top_n]

    result = {
        "started_at": started_at.isoformat(),
        "finished_at": datetime.utcnow().isoformat(),
        "quote_asset": quote_asset,
        "markets_discovered": len(all_markets),
        "markets_screened": len(candidates),
        "symbols_analyzed": [r["symbol"] for r in reports],
        "opportunities": opportunities,
        "all_reports": reports,
        "error": error,
    }

    _persist(result)
    return result


def _persist(result: dict) -> int:
    init_db()
    session = get_session()
    try:
        run = ScanRun(
            created_at=datetime.utcnow(),
            quote_asset=result["quote_asset"],
            markets_discovered=result["markets_discovered"],
            markets_screened=result["markets_screened"],
            symbols_analyzed_json=_to_json(result["symbols_analyzed"]),
            top_opportunities_json=_to_json([_opportunity_summary(r) for r in result["opportunities"]]),
            error=result["error"],
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        result["scan_run_id"] = run.id
        return run.id
    finally:
        session.close()


def _opportunity_summary(report: dict) -> dict:
    return {
        "symbol": report["symbol"],
        "bias": report["bias"],
        "direction": report["direction"],
        "confidence": report["confidence"],
        "market_regime": report["market_regime"],
        "risk_level": report["risk_level"],
        "risk_reward_ratio": report.get("risk_reward_ratio"),
        "what_changed": report["what_changed"],
        "quote_volume_24h": report.get("quote_volume_24h"),
        "price_change_pct_24h": report.get("price_change_pct_24h"),
    }


def _to_json(obj) -> str:
    import json
    return json.dumps(obj)
