"""
Risk Agent — pure computation, no LLM, and deliberately the one layer the
decision engine is NOT allowed to override.

Volatility thresholds are regime-adaptive: instead of applying one fixed
MAX_VOLATILITY_PCT identically to a slow-moving major and a wild
micro-cap, this agent also computes the symbol's OWN recent volatility
distribution (a longer lookback) and flags "abnormal" against whichever is
more informative — a move unusual for the market in general, or unusual for
this particular symbol. MAX_VOLATILITY_PCT still acts as a floor/ceiling so
a single wild outlier bar in the lookback can't make the veto meaningless,
and a very calm symbol can't make it impossibly tight either.
"""
import numpy as np


def run(
    adapter, symbol: str, timeframe: str = "1h",
    max_volatility_pct: float = 6.0, regime_lookback: int = 90,
) -> dict:
    df_short = adapter.get_ohlcv(symbol, timeframe, limit=48)
    returns_short = df_short["close"].pct_change().dropna()

    realized_vol_pct = float(returns_short.std() * 100)
    last_move_pct = float(returns_short.iloc[-1] * 100)
    max_abs_move_pct = float(returns_short.abs().max() * 100)

    # This symbol's own historical distribution of bar-to-bar moves, so
    # "abnormal" means abnormal for THIS symbol, not just above one global
    # constant that treats BTC and a micro-cap identically.
    historical_p90 = max_volatility_pct
    vol_percentile_rank = None
    try:
        df_long = adapter.get_ohlcv(symbol, timeframe, limit=regime_lookback)
        returns_long = (df_long["close"].pct_change().dropna().abs() * 100)
        if len(returns_long) >= 20:
            historical_p90 = float(np.percentile(returns_long, 90))
            vol_percentile_rank = float((returns_long < max_abs_move_pct).mean() * 100)
    except Exception:
        pass  # fall back to the global constant below — never sink the pipeline over this

    # Effective threshold: the symbol's own p90 move, floored at half the
    # global setting and capped at double it.
    effective_threshold = min(max(historical_p90, max_volatility_pct * 0.5), max_volatility_pct * 2.0)

    abnormal = max_abs_move_pct > effective_threshold

    if abnormal:
        risk_level = "high"
    elif realized_vol_pct > effective_threshold * 0.5:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "agent": "risk",
        "risk_level": risk_level,
        "realized_vol_pct": round(realized_vol_pct, 3),
        "last_bar_move_pct": round(last_move_pct, 3),
        "max_abs_move_pct_recent": round(max_abs_move_pct, 3),
        "historical_p90_move_pct": round(historical_p90, 3),
        "vol_percentile_rank": round(vol_percentile_rank, 1) if vol_percentile_rank is not None else None,
        "effective_volatility_threshold_pct": round(effective_threshold, 3),
        "abnormal_volatility": bool(abnormal),
        # Hard veto: the decision engine must respect this regardless of confidence.
        "veto_directional_trade": bool(abnormal),
    }
