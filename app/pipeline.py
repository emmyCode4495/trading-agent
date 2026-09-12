"""
Orchestrates one full cycle for one symbol:
  data → [trend, momentum, structure, risk, news] agents → decision engine
  → persist Recommendation row → return report dict

`run_cycle` is deliberately symbol-agnostic and doesn't care where the
symbol came from — it's called both by app.scanner (once per symbol that
survives discovery + liquidity screening) and by the manual watchlist path
below / GET /api/report/latest (a person asking about one specific pair).
The scanner is the primary, autonomous path; `run_all_symbols` here is only
the manual-watchlist fallback used by `scripts/run_once.py`.
"""
import json

from app.agents import correlation, momentum, news_sentiment, risk, structure, trend, volume_profile
from app.config import settings
from app.data import get_adapter
from app.decision import build_report, format_report_text
from app.models import Recommendation, get_session, init_db


def run_cycle(symbol: str) -> dict:
    adapter = get_adapter()

    trend_out = trend.run(adapter, symbol)
    momentum_out = momentum.run(adapter, symbol)
    structure_out = structure.run(adapter, symbol)
    risk_out = risk.run(adapter, symbol, max_volatility_pct=settings.max_volatility_pct)
    news_out = news_sentiment.run(symbol)
    correlation_out = correlation.run(adapter, symbol)
    volume_profile_out = volume_profile.run(adapter, symbol)

    report = build_report(
        symbol, trend_out, momentum_out, structure_out, risk_out, news_out,
        correlation=correlation_out, volume_profile=volume_profile_out,
    )
    report["text"] = format_report_text(report)

    _persist(report)

    # Execution is fully additive and off by default (EXECUTION_ENABLED=false).
    # Import here, not at module top, so this file has zero hard dependency
    # on hyperliquid-python-sdk being installed when execution isn't in use.
    from app.execution.executor import maybe_execute
    report["execution"] = maybe_execute(report)

    return report


def _persist(report: dict) -> int:
    init_db()
    session = get_session()
    try:
        rec = Recommendation(
            symbol=report["symbol"],
            bias=report["bias"],
            direction=report["direction"],
            confidence=report["confidence"],
            market_regime=report["market_regime"],
            entry_price=report["entry_price"],
            invalidation_price=report["invalidation_price"],
            target_price=report["target_price"],
            risk_level=report["risk_level"],
            summary=report["what_changed"],
            evidence_json=json.dumps(report["evidence"]),
            agent_outputs_json=json.dumps(report["agent_outputs"]),
            # Only LONG/SHORT calls have a real entry/target/invalidation to
            # track — WAIT calls have nothing to resolve, so they're marked
            # "n/a" rather than sitting "open" forever.
            status="open" if report["direction"] in ("LONG", "SHORT") else "n/a",
        )
        session.add(rec)
        session.commit()
        session.refresh(rec)
        report["recommendation_id"] = rec.id
        return rec.id
    finally:
        session.close()


def run_all_symbols() -> list[dict]:
    """Manual-watchlist runner (settings.symbols) — not used by the scanner."""
    return [run_cycle(sym.strip()) for sym in settings.symbols if sym.strip()]
