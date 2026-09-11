"""
Correlation Agent — pure computation, no LLM.

In crypto, an altcoin's "trend" signal is frequently just BTC beta in
disguise: BTC moves, everything else follows, and the trend/momentum/
structure agents on the altcoin end up re-describing BTC's move as if it
were symbol-specific conviction. This agent measures how correlated the
symbol's recent returns are to BTC/USDT's, and separately reads BTC's own
direction. The one case worth discounting confidence for is: symbol is
highly correlated to BTC, AND BTC itself has no clear direction — that
combination means the symbol's own technical story is more likely noise
riding a directionless market than a real, symbol-specific edge.

Deliberately NOT a veto (that's the Risk agent's job) — this only informs
the decision engine's confidence, via `discount_confidence`.
"""
BTC_REFERENCE_SYMBOL = "BTC/USDT"
HIGH_CORRELATION_THRESHOLD = 0.80


def _btc_trend_label(btc_df) -> str:
    close = btc_df["close"]
    ema_fast = close.ewm(span=12, adjust=False).mean()
    slope = (ema_fast.iloc[-1] - ema_fast.iloc[-5]) / ema_fast.iloc[-5] if len(ema_fast) > 5 else 0.0
    if slope > 0.002:
        return "bullish"
    if slope < -0.002:
        return "bearish"
    return "directionless"


def run(adapter, symbol: str, timeframe: str = "1h", lookback: int = 60) -> dict:
    base = {
        "agent": "correlation",
        "is_btc": symbol.upper() == BTC_REFERENCE_SYMBOL,
    }

    if base["is_btc"]:
        return {
            **base,
            "btc_correlation": 1.0,
            "high_correlation": False,
            "btc_trend_label": None,
            "discount_confidence": False,
            "note": "This IS the BTC reference symbol — correlation to itself isn't meaningful.",
        }

    try:
        symbol_df = adapter.get_ohlcv(symbol, timeframe, limit=lookback + 5)
        btc_df = adapter.get_ohlcv(BTC_REFERENCE_SYMBOL, timeframe, limit=lookback + 5)
    except Exception as exc:  # noqa: BLE001 — degrade gracefully, never sink the pipeline
        return {
            **base,
            "btc_correlation": None,
            "high_correlation": False,
            "btc_trend_label": None,
            "discount_confidence": False,
            "note": f"correlation agent unavailable ({exc}); treated as neutral, no discount applied.",
        }

    sym_returns = symbol_df["close"].pct_change().dropna().reset_index(drop=True)
    btc_returns = btc_df["close"].pct_change().dropna().reset_index(drop=True)

    n = min(len(sym_returns), len(btc_returns), lookback)
    if n < 10:
        return {
            **base,
            "btc_correlation": None,
            "high_correlation": False,
            "btc_trend_label": None,
            "discount_confidence": False,
            "note": "Not enough overlapping history yet to compute a meaningful correlation.",
        }

    sym_recent = sym_returns.iloc[-n:].reset_index(drop=True)
    btc_recent = btc_returns.iloc[-n:].reset_index(drop=True)
    correlation = float(sym_recent.corr(btc_recent))
    if correlation != correlation:  # NaN guard (e.g. zero-variance window)
        correlation = 0.0

    btc_trend = _btc_trend_label(btc_df)
    high_correlation = correlation >= HIGH_CORRELATION_THRESHOLD
    discount_confidence = high_correlation and btc_trend == "directionless"

    return {
        **base,
        "btc_correlation": round(correlation, 3),
        "high_correlation": bool(high_correlation),
        "btc_trend_label": btc_trend,
        "discount_confidence": bool(discount_confidence),
        "note": (
            f"{correlation:.2f} correlation to BTC over the last {n} {timeframe} bars; "
            f"BTC itself reads '{btc_trend}'."
        ),
    }
