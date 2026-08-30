"""
Risk Agent — pure computation, no LLM, and deliberately the one layer the
LLM-based decision step is NOT allowed to override. It measures realized
volatility over the last bars and flags when conditions are too chaotic for
a directional call, regardless of how convincing the trend/momentum story is.
"""
import numpy as np


def run(adapter, symbol: str, timeframe: str = "1h", max_volatility_pct: float = 6.0) -> dict:
    df = adapter.get_ohlcv(symbol, timeframe, limit=48)
    returns = df["close"].pct_change().dropna()

    realized_vol_pct = float(returns.std() * 100)
    last_move_pct = float(returns.iloc[-1] * 100)
    max_abs_move_pct = float(returns.abs().max() * 100)

    abnormal = max_abs_move_pct > max_volatility_pct

    if abnormal:
        risk_level = "high"
    elif realized_vol_pct > max_volatility_pct * 0.5:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "agent": "risk",
        "risk_level": risk_level,
        "realized_vol_pct": round(realized_vol_pct, 3),
        "last_bar_move_pct": round(last_move_pct, 3),
        "max_abs_move_pct_recent": round(max_abs_move_pct, 3),
        "abnormal_volatility": bool(abnormal),
        # Hard veto: the decision engine must respect this regardless of confidence.
        "veto_directional_trade": bool(abnormal),
    }
