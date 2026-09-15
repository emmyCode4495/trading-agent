"""
The one new seam in the whole system: takes a report dict exactly as
produced by app.pipeline.run_cycle() (unchanged — nothing about the
scanner/agents/decision engine is touched) and decides whether to also act
on it via Hyperliquid.

Gating, in order — any of these being false means "skip", never "error":
  1. settings.execution_enabled (global off switch, default false)
  2. report["direction"] in ("LONG", "SHORT") — WAIT calls, and anything the
     Risk agent already vetoed upstream, never reach here as LONG/SHORT
  3. report["confidence"] >= settings.min_confidence_to_act
  4. the symbol actually maps to a listed Hyperliquid perp
  5. no existing same-direction position already open (skip rather than
     pyramid — simplest safe default for a hackathon build)

An opposite-direction position that's still open gets closed first, then
the new one opens — a flip, not a stack.
"""
import json
import logging

from app.execution import hyperliquid_adapter as hl
from app.execution.sizing import SizingError, compute_size
from app.config import settings
from app.models import Execution, get_session, init_db

logger = logging.getLogger(__name__)


def maybe_execute(report: dict) -> dict:
    """
    Always returns a dict describing what happened (even when skipped), and
    always persists an Execution row — including skips — so the dashboard
    has a full audit trail of "why didn't this trade?" alongside "why did?".
    """
    init_db()
    result = {"executed": False, "reason": None, "execution_id": None}

    if not settings.execution_enabled:
        return _record(report, status="skipped", skip_reason="EXECUTION_ENABLED=false (master switch)", result=result)

    # Runtime opt-in (Telegram / dashboard toggle). Default off so users are
    # never forced into live orders just because the server master switch is on.
    try:
        from app.preferences import is_execution_opted_in
        if not is_execution_opted_in():
            return _record(
                report,
                status="skipped",
                skip_reason="execution opt-in is OFF (enable from Telegram: /execution on)",
                result=result,
            )
    except Exception as exc:
        return _record(report, status="skipped", skip_reason=f"preference check failed: {exc}", result=result)

    direction = report.get("direction")
    if direction not in ("LONG", "SHORT"):
        return _record(report, status="skipped", skip_reason=f"direction={direction}", result=result)

    confidence = report.get("confidence", 0)
    if confidence < settings.min_confidence_to_act:
        return _record(
            report, status="skipped",
            skip_reason=f"confidence {confidence} < MIN_CONFIDENCE_TO_ACT {settings.min_confidence_to_act}",
            result=result,
        )

    hl_symbol = hl.to_hl_symbol(report["symbol"])
    is_buy = direction == "LONG"

    # Explicit tradeability check before any network-heavy sizing / order calls.
    # CEX-only pairs that have no Hyperliquid perp are skipped cleanly so the
    # signal is still recorded and the dashboard can show why it was not traded.
    if not hl.is_tradeable(hl_symbol):
        return _record(
            report,
            status="skipped",
            skip_reason=f"{hl_symbol} is not a listed Hyperliquid perp (CEX signal only)",
            result=result,
            hl_symbol=hl_symbol,
        )

    try:
        existing = hl.get_current_position(hl_symbol)
        if existing is not None:
            existing_is_long = float(existing["szi"]) > 0
            if existing_is_long == is_buy:
                return _record(
                    report,
                    status="skipped",
                    skip_reason=f"already {'long' if existing_is_long else 'short'} {hl_symbol}, not pyramiding",
                    result=result,
                    hl_symbol=hl_symbol,
                )
            logger.info(
                "Flipping %s: closing existing %s position before opening %s",
                hl_symbol,
                "long" if existing_is_long else "short",
                direction,
            )
            close_resp = hl.close_position(hl_symbol)
        else:
            close_resp = None

        equity = hl.get_account_equity()
        current_price = hl.get_mid_price(hl_symbol)
        sized = compute_size(report, equity=equity, current_price=current_price)

        open_resp = hl.open_market_position(hl_symbol, is_buy, sized.size)

        return _record(
            report,
            status="submitted",
            result=result,
            hl_symbol=hl_symbol,
            size=sized.size,
            equity=equity,
            hl_response=open_resp,
            close_response=close_resp,
            executed=True,
        )

    except (hl.HyperliquidError, SizingError) as exc:
        logger.warning("Execution failed for %s (%s): %s", report.get("symbol"), hl_symbol, exc)
        return _record(
            report,
            status="error",
            skip_reason=str(exc),
            result=result,
            hl_symbol=hl_symbol,
        )


def _record(report: dict, status: str, result: dict, skip_reason: str = None, hl_symbol: str = None,
            size: float = None, equity: float = None, hl_response: dict = None,
            close_response: dict = None, executed: bool = False) -> dict:
    session = get_session()
    try:
        row = Execution(
            recommendation_id=report.get("recommendation_id"),
            symbol=report.get("symbol"),
            hl_symbol=hl_symbol or hl.to_hl_symbol(report.get("symbol", "")),
            direction=report.get("direction"),
            requested_size=size,
            equity_at_sizing=equity,
            status=status,
            skip_reason=skip_reason,
            hyperliquid_response_json=json.dumps(hl_response) if hl_response else None,
            close_response_json=json.dumps(close_response) if close_response else None,
            builder_fee_tenths_bps=settings.hyperliquid_builder_fee_tenths_bps if executed else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        result.update(executed=executed, reason=skip_reason, execution_id=row.id, status=status)
        return result
    finally:
        session.close()
