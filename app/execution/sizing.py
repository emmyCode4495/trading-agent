"""
Position sizing for executed trades.

Deliberately NOT Kelly-fraction sizing, despite the README roadmap mentioning
it as an idea. Kelly needs an accurate edge/win-rate estimate to be safe, and
with mock data (or a live system that's only run a few hundred cycles) that
estimate is exactly what you don't have yet — Kelly sizing on a
miscalibrated edge oversizes aggressively and is fragile. Fixed-fractional
risk sizing (risk a fixed % of equity on the distance to invalidation) is
the standard practitioner default: simpler, auditable, and safe even before
`backtest.agent_accuracy_report()` has enough resolved trades to trust.

The one thing this module deliberately does NOT decide is whether to trade
at all — that gate (direction != WAIT, confidence >= min_confidence_to_act)
lives in executor.py, and the Risk agent's veto already happened upstream in
the decision engine. This module only answers "how much", never "whether".
"""
from dataclasses import dataclass

from app.config import settings

# Extra haircut on top of the fixed risk fraction when the Risk agent flagged
# elevated (but not vetoed) risk. The Risk agent's veto already blocks the
# worst cases before a report ever reaches here — this is defense in depth
# for the "medium"/"high" cases that passed through.
RISK_LEVEL_MULTIPLIER = {"low": 1.0, "medium": 0.75, "high": 0.5}


class SizingError(Exception):
    pass


@dataclass
class SizeResult:
    size: float              # units of the underlying asset to trade
    dollar_risk: float       # $ actually at risk if invalidation is hit
    notional: float          # size * current_price
    capped_by_max_position: bool


def compute_size(report: dict, equity: float, current_price: float) -> SizeResult:
    """
    Fixed-fractional risk sizing:
      dollar_risk = equity * (risk_per_trade_pct / 100) * risk_level_multiplier
      size = dollar_risk / |entry_price - invalidation_price|
    then capped so notional never exceeds max_position_pct_of_equity, since a
    very tight invalidation (small stop distance) would otherwise produce an
    oversized, over-leveraged position for the same dollar risk.
    """
    entry = report.get("entry_price")
    invalidation = report.get("invalidation_price")
    if not entry or not invalidation:
        raise SizingError(f"Report for {report.get('symbol')} is missing entry/invalidation price.")

    stop_distance = abs(entry - invalidation)
    if stop_distance <= 0:
        raise SizingError(f"Zero stop distance for {report.get('symbol')} — entry == invalidation.")
    if equity <= 0:
        raise SizingError("Non-positive account equity — check Hyperliquid connection/funding.")

    risk_multiplier = RISK_LEVEL_MULTIPLIER.get(report.get("risk_level"), 0.5)
    dollar_risk = equity * (settings.risk_per_trade_pct / 100) * risk_multiplier

    raw_size = dollar_risk / stop_distance
    notional = raw_size * current_price
    max_notional = equity * (settings.max_position_pct_of_equity / 100)

    capped = False
    if notional > max_notional:
        raw_size = max_notional / current_price
        dollar_risk = raw_size * stop_distance
        capped = True

    return SizeResult(
        size=raw_size,
        dollar_risk=dollar_risk,
        notional=raw_size * current_price,
        capped_by_max_position=capped,
    )
