"""
FastAPI app exposing:
  GET  /api/scan/latest                      -> most recent scan summary + its opportunities
  POST /api/scan/run                          -> force a new discover->screen->analyze->rank cycle now
  GET  /api/markets?quote_asset=USDT          -> discovered+screened universe, no agent analysis (fast, for transparency)
  GET  /api/report/latest?symbol=BTC/USDT     -> MANUAL drill-down: runs the full pipeline for one specific symbol
  GET  /api/history?symbol=BTC/USDT&limit=50  -> past recommendations for one symbol
  GET  /api/positions                         -> currently-open + recently-resolved trades, with live P&L%
  GET  /api/calibration                       -> backtest/calibration summary (real-time win rate)
  GET  /api/calibration/agent-accuracy         -> per-agent accuracy: does each agent's read predict wins?
  GET  /api/status                            -> is the background scanner running, last/next scan time
  GET  /api/symbols                           -> the manual watchlist (optional, secondary to the scanner)
  GET  /                                       -> the dashboard UI

Run with: uvicorn app.api:app --reload --port 8000

On startup, this launches a background scan loop inside the API process
itself (see app.scheduler.start_background) — the dashboard is "live" the
moment the server is running, with no separate scheduler process required.
Set ENABLE_BACKGROUND_SCANNER=false to disable this (e.g. if you're running
`python -m app.scheduler` as a separate process instead, or only want
on-demand scans triggered by the RUN SCAN button).
"""
import json
import os

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import scan_state
from app.backtest import (agent_accuracy_report, calibration_report, evaluate_open_positions,
                           open_positions_summary, recent_resolved_summary)
from app.config import settings
from app.data import get_adapter
from app.models import Recommendation, ScanRun, get_session, init_db
from app.pipeline import run_cycle
from app.scanner import discover_markets, run_scan, screen_by_liquidity

app = FastAPI(title="Market Intelligence Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

init_db()

_background_scheduler = None


@app.on_event("startup")
def _launch_background_scanner():
    global _background_scheduler
    if os.getenv("ENABLE_BACKGROUND_SCANNER", "true").lower() != "true":
        return
    from app.scheduler import start_background
    _background_scheduler = start_background()


@app.on_event("shutdown")
def _stop_background_scanner():
    if _background_scheduler is not None:
        _background_scheduler.shutdown(wait=False)


@app.get("/api/status")
def status():
    """Live-scanner status for the dashboard's 'LIVE' indicator: is it running, last/next scan, last position check."""
    return scan_state.get_state()


@app.get("/api/scan/latest")
def latest_scan():
    """
    Returns the most recent scan summary from the DB without re-running
    anything. If no scan has ever run, triggers one (so a fresh dashboard
    load always has something to show) — otherwise this is a cheap read.
    """
    session = get_session()
    try:
        run = session.query(ScanRun).order_by(ScanRun.created_at.desc()).first()
    finally:
        session.close()

    if run is None:
        return run_scan()

    return {
        "scan_run_id": run.id,
        "finished_at": run.created_at.isoformat(),
        "quote_asset": run.quote_asset,
        "markets_discovered": run.markets_discovered,
        "markets_screened": run.markets_screened,
        "symbols_analyzed": json.loads(run.symbols_analyzed_json or "[]"),
        "opportunities": json.loads(run.top_opportunities_json or "[]"),
        "error": run.error,
    }


@app.post("/api/scan/run")
def force_scan():
    """Forces a brand new discover -> screen -> analyze -> rank cycle right now."""
    return run_scan()


@app.get("/api/markets")
def markets(
    quote_asset: str = Query(default=None),
    min_quote_volume: float = Query(default=None),
):
    """
    Discovery + liquidity screening only — no agent analysis. Lets the
    dashboard (or a curious person) see the universe the scanner is choosing
    from, and why a given symbol did or didn't make the cut, without paying
    the cost of the full pipeline.
    """
    quote_asset = quote_asset or settings.scan_quote_asset
    all_markets = discover_markets(get_adapter(), quote_asset=quote_asset)
    screened = screen_by_liquidity(all_markets, min_quote_volume=min_quote_volume)
    screened_symbols = {m["symbol"] for m in screened}

    all_markets.sort(key=lambda m: m["quote_volume_24h"], reverse=True)
    for m in all_markets:
        m["passed_screen"] = m["symbol"] in screened_symbols

    return {
        "quote_asset": quote_asset,
        "total_discovered": len(all_markets),
        "total_screened": len(screened),
        "markets": all_markets,
    }


def _default_symbol() -> str:
    """
    Shared fallback for endpoints that need *a* symbol when none was given:
    manual watchlist first, else the last scan's top opportunity, else a
    hardcoded last resort so nothing 400s on a completely fresh system.
    """
    if settings.symbols and settings.symbols[0].strip():
        return settings.symbols[0].strip()

    session = get_session()
    try:
        run = session.query(ScanRun).order_by(ScanRun.created_at.desc()).first()
    finally:
        session.close()
    if run:
        opps = json.loads(run.top_opportunities_json or "[]")
        if opps:
            return opps[0]["symbol"]

    return "BTC/USDT"


@app.get("/api/report/latest")
def latest_report(symbol: str = Query(default=None)):
    """
    MANUAL drill-down for one specific symbol — separate from, and secondary
    to, the autonomous scanner above. Defaults to the manual watchlist
    symbol, or the top opportunity from the last scan if no watchlist is set.
    """
    return run_cycle(symbol or _default_symbol())


@app.get("/api/history")
def history(symbol: str = Query(default=None), limit: int = 50):
    symbol = symbol or _default_symbol()
    session = get_session()
    try:
        rows = (
            session.query(Recommendation)
            .filter(Recommendation.symbol == symbol)
            .order_by(Recommendation.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "symbol": r.symbol,
                "bias": r.bias,
                "direction": r.direction,
                "confidence": r.confidence,
                "market_regime": r.market_regime,
                "entry_price": r.entry_price,
                "invalidation_price": r.invalidation_price,
                "target_price": r.target_price,
                "risk_level": r.risk_level,
                "summary": r.summary,
                "evidence": json.loads(r.evidence_json or "[]"),
                "status": r.status,
                "exit_price": r.exit_price,
                "pnl_pct": r.pnl_pct,
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            }
            for r in rows
        ]
    finally:
        session.close()


@app.get("/api/positions")
def positions():
    """
    Currently-open LONG/SHORT recommendations plus the most recently
    resolved ones, each with live P&L%: positive when it hit target,
    negative when it hit invalidation. This is the real-time win/loss feed.
    """
    evaluate_open_positions()  # resolve anything that's crossed target/invalidation since the last check
    return {
        "open": open_positions_summary(),
        "recently_resolved": recent_resolved_summary(),
    }


@app.get("/api/calibration")
def calibration():
    evaluate_open_positions()
    return calibration_report()


@app.get("/api/calibration/agent-accuracy")
def agent_accuracy():
    """Per-agent accuracy: does each agent's own directional read, when it agrees with the trade taken, actually predict wins?"""
    return agent_accuracy_report()


@app.get("/api/symbols")
def symbols():
    return settings.symbols


app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def dashboard():
    return FileResponse("app/static/dashboard.html")
