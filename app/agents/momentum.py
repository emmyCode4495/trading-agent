"""
Momentum Agent — pure computation, no LLM.

RSI, MACD histogram, and volume-momentum (current volume vs its recent
average). Implemented directly with pandas so there's no dependency on
compiled libraries like TA-Lib.
"""
import pandas as pd


def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean().iloc[-1]
    avg_loss = loss.rolling(period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(float(100 - (100 / (1 + rs))), 2)


def _macd_histogram(close: pd.Series) -> float:
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    return round(float(hist.iloc[-1]), 6)


def run(adapter, symbol: str, timeframe: str = "1h") -> dict:
    df = adapter.get_ohlcv(symbol, timeframe, limit=120)
    close = df["close"]
    volume = df["volume"]

    rsi = _rsi(close)
    macd_hist = _macd_histogram(close)
    macd_hist_prev = _macd_histogram(close.iloc[:-1]) if len(close) > 30 else macd_hist

    vol_avg = volume.rolling(20).mean().iloc[-1]
    vol_ratio = round(float(volume.iloc[-1] / vol_avg), 2) if vol_avg else 1.0

    if rsi >= 70:
        rsi_state = "overbought"
    elif rsi <= 30:
        rsi_state = "oversold"
    else:
        rsi_state = "neutral"

    macd_rising = macd_hist > macd_hist_prev

    if rsi_state != "overbought" and macd_hist > 0 and macd_rising:
        momentum_label = "positive"
    elif rsi_state != "oversold" and macd_hist < 0 and not macd_rising:
        momentum_label = "negative"
    else:
        momentum_label = "mixed"

    return {
        "agent": "momentum",
        "label": momentum_label,
        "rsi": rsi,
        "rsi_state": rsi_state,
        "macd_histogram": macd_hist,
        "macd_rising": bool(macd_rising),
        "volume_ratio_vs_20bar_avg": vol_ratio,
        "volume_increasing": vol_ratio > 1.2,
    }
