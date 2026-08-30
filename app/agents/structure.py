"""
Market Structure Agent — pure computation, no LLM.

Finds recent swing highs/lows (a simple fractal/pivot method), derives a
support and resistance level from them, and flags whether the latest close
just broke out of that range with above-average volume.
"""
import numpy as np
import pandas as pd

from app.formatting import round_price


def _swing_points(df: pd.DataFrame, window: int = 3):
    highs, lows = [], []
    h, l = df["high"].values, df["low"].values
    for i in range(window, len(df) - window):
        if h[i] == max(h[i - window:i + window + 1]):
            highs.append(h[i])
        if l[i] == min(l[i - window:i + window + 1]):
            lows.append(l[i])
    return highs, lows


def run(adapter, symbol: str, timeframe: str = "4h") -> dict:
    df = adapter.get_ohlcv(symbol, timeframe, limit=150)
    highs, lows = _swing_points(df)

    resistance = float(np.median(highs[-5:])) if highs else float(df["high"].max())
    support = float(np.median(lows[-5:])) if lows else float(df["low"].min())

    last_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2])

    vol_avg = df["volume"].rolling(20).mean().iloc[-1]
    vol_confirmed = df["volume"].iloc[-1] > vol_avg if vol_avg else False

    broke_resistance = prev_close <= resistance < last_close
    broke_support = prev_close >= support > last_close

    if broke_resistance:
        event = "breakout_above_resistance"
    elif broke_support:
        event = "breakdown_below_support"
    else:
        event = "inside_range"

    # Higher-highs / higher-lows check over the recent swing points, a cheap
    # proxy for "is this an established uptrend structurally, not just price".
    hh_hl = len(highs) >= 2 and len(lows) >= 2 and highs[-1] > highs[-2] and lows[-1] > lows[-2]
    lh_ll = len(highs) >= 2 and len(lows) >= 2 and highs[-1] < highs[-2] and lows[-1] < lows[-2]

    return {
        "agent": "structure",
        "support": round_price(support),
        "resistance": round_price(resistance),
        "last_close": round_price(last_close),
        "event": event,
        "volume_confirmed": bool(vol_confirmed),
        "higher_highs_higher_lows": bool(hh_hl),
        "lower_highs_lower_lows": bool(lh_ll),
    }
