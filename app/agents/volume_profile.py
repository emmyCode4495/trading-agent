"""
Volume Profile Agent — pure computation, no LLM.

The Structure agent's support/resistance comes from swing highs/lows —
where price happened to turn. This agent builds a volume-at-price histogram
over recent bars and derives the Point of Control (POC — the price level
where the most volume actually transacted) and a Value Area (the tightest
band containing ~70% of volume). These are generally sharper, more
defensible levels for invalidation/target than swing points alone, because
they reflect where the market actually traded heavily rather than just
where a candle wicked to.

No trade-level tick data is available from these adapters, so this is a
bar-level approximation: each bar's volume is spread evenly across the
histogram bins its [low, high] range touches, rather than concentrated at
its close. That's standard practice for OHLCV-only volume profiles.
"""
import numpy as np

from app.formatting import round_price


def run(
    adapter,
    symbol: str,
    timeframe: str = "4h",
    lookback: int = 150,
    num_bins: int = 24,
    value_area_pct: float = 0.70,
) -> dict:
    df = adapter.get_ohlcv(symbol, timeframe, limit=lookback)
    last_close = float(df["close"].iloc[-1])

    lo = float(df["low"].min())
    hi = float(df["high"].max())
    if hi <= lo:
        return {
            "agent": "volume_profile",
            "poc": round_price(last_close),
            "value_area_high": round_price(last_close),
            "value_area_low": round_price(last_close),
            "last_close": round_price(last_close),
            "price_vs_poc": "at_poc",
            "note": "Insufficient price range in the lookback window to build a profile.",
        }

    bin_edges = np.linspace(lo, hi, num_bins + 1)
    volume_per_bin = np.zeros(num_bins)

    for _, row in df.iterrows():
        bar_lo, bar_hi, vol = float(row["low"]), float(row["high"]), float(row["volume"])
        if vol <= 0:
            continue
        if bar_hi <= bar_lo:
            idx = min(max(int(np.searchsorted(bin_edges, row["close"])) - 1, 0), num_bins - 1)
            volume_per_bin[idx] += vol
            continue
        start_idx = max(int(np.searchsorted(bin_edges, bar_lo, side="right")) - 1, 0)
        end_idx = min(int(np.searchsorted(bin_edges, bar_hi, side="right")) - 1, num_bins - 1)
        span = max(end_idx - start_idx + 1, 1)
        volume_per_bin[start_idx:end_idx + 1] += vol / span

    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    poc_idx = int(np.argmax(volume_per_bin))
    poc = float(bin_centers[poc_idx])

    total_volume = float(volume_per_bin.sum())
    target_volume = total_volume * value_area_pct
    lo_idx = hi_idx = poc_idx
    captured = volume_per_bin[poc_idx]

    while captured < target_volume and (lo_idx > 0 or hi_idx < num_bins - 1):
        next_lo = volume_per_bin[lo_idx - 1] if lo_idx > 0 else -1.0
        next_hi = volume_per_bin[hi_idx + 1] if hi_idx < num_bins - 1 else -1.0
        if next_hi >= next_lo:
            hi_idx += 1
            captured += volume_per_bin[hi_idx]
        else:
            lo_idx -= 1
            captured += volume_per_bin[lo_idx]

    value_area_low = float(bin_centers[lo_idx])
    value_area_high = float(bin_centers[hi_idx])

    if last_close > value_area_high:
        price_vs_poc = "above_value_area"
    elif last_close < value_area_low:
        price_vs_poc = "below_value_area"
    else:
        price_vs_poc = "inside_value_area"

    return {
        "agent": "volume_profile",
        "poc": round_price(poc),
        "value_area_high": round_price(value_area_high),
        "value_area_low": round_price(value_area_low),
        "last_close": round_price(last_close),
        "price_vs_poc": price_vs_poc,
        "note": (
            f"POC {round_price(poc)}; value area [{round_price(value_area_low)}, "
            f"{round_price(value_area_high)}] over the last {len(df)} {timeframe} bars."
        ),
    }
