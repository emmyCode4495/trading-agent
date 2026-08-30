"""
Trend Agent — pure computation, no LLM.

Determines bullish / bearish / sideways structure across multiple timeframes
using EMA slope + fast/slow EMA alignment. Multiple timeframes agreeing is
what gives this agent's output real weight downstream.
"""
import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _single_timeframe_trend(df: pd.DataFrame) -> dict:
    close = df["close"]
    ema_fast = _ema(close, 12)
    ema_slow = _ema(close, 26)

    slope = (ema_fast.iloc[-1] - ema_fast.iloc[-5]) / ema_fast.iloc[-5] if len(ema_fast) > 5 else 0.0
    aligned_bullish = ema_fast.iloc[-1] > ema_slow.iloc[-1]

    if slope > 0.002 and aligned_bullish:
        label = "bullish"
    elif slope < -0.002 and not aligned_bullish:
        label = "bearish"
    else:
        label = "sideways"

    return {
        "label": label,
        "ema_fast": round(float(ema_fast.iloc[-1]), 4),
        "ema_slow": round(float(ema_slow.iloc[-1]), 4),
        "slope_pct": round(float(slope) * 100, 3),
    }


def run(adapter, symbol: str, timeframes=("15m", "1h", "4h", "1d")) -> dict:
    per_tf = {}
    for tf in timeframes:
        df = adapter.get_ohlcv(symbol, tf, limit=120)
        per_tf[tf] = _single_timeframe_trend(df)

    labels = [v["label"] for v in per_tf.values()]
    bullish_count = labels.count("bullish")
    bearish_count = labels.count("bearish")

    if bullish_count >= 3:
        overall = "bullish"
    elif bearish_count >= 3:
        overall = "bearish"
    elif bullish_count > bearish_count:
        overall = "mildly bullish"
    elif bearish_count > bullish_count:
        overall = "mildly bearish"
    else:
        overall = "sideways"

    agreement = max(bullish_count, bearish_count) / len(timeframes)

    return {
        "agent": "trend",
        "overall": overall,
        "agreement_score": round(agreement, 2),  # 0..1, how many timeframes agree
        "per_timeframe": per_tf,
    }
