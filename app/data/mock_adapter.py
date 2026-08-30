"""
Generates synthetic but plausible OHLCV data using a regime-switching random
walk (drift alternates between up/down/flat periods, with volatility bursts).
This lets every agent, the decision engine, and the backtester be exercised
end-to-end without any network access or API keys.

Two important design points, both fixes for real bugs found while testing:

1. COHERENT TIMEFRAMES: every timeframe (15m/1h/4h/1d) and get_latest_price()
   are all derived from ONE master 15m-resolution price path per symbol (via
   pandas resampling), not generated as independent random walks. An earlier
   version generated each timeframe separately, which meant "current price"
   (from a 15m series) and "entry price" (from a 4h series) could drift
   apart into unrelated numbers — occasionally producing nonsensical results
   like a recommendation resolving as a "win" while showing a negative P&L,
   because the two series had no real relationship to each other.

2. PRICE ACTUALLY EVOLVES OVER REAL TIME: the master series is kept in a
   module-level store that PERSISTS for the life of the process and is
   INCREMENTALLY EXTENDED (not regenerated from scratch) every time it's
   accessed. An earlier version regenerated the whole history fresh and
   deterministically on every call, which meant the "latest price" was
   frozen forever — calling it now vs. two minutes from now returned the
   exact same number. That silently broke real-time position resolution:
   nothing could ever newly cross a target or invalidation level, because
   nothing ever moved. Now, every new 15-minute bar that becomes due (based
   on wall-clock time) is generated once, continuing the same random walk
   from where it left off, so prices genuinely drift over real time the way
   a live market would.

Swap this out for BinanceAdapter (or your own) once you're ready to trade on
real data — nothing else in the codebase changes.
"""
import hashlib
import threading
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from app.data.base import DataAdapter
from app.formatting import round_price

TIMEFRAME_MINUTES = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
_RESAMPLE_RULE = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}

_MASTER_MINUTES = 15
_MASTER_WINDOW_BARS = 45 * 24 * (60 // _MASTER_MINUTES)  # 45 days of 15m bars kept in memory per symbol

# A plausible-looking synthetic universe so the scanner (discover -> screen
# -> analyze) has something real to exercise with zero setup, the same way
# get_ohlcv gives every agent something to compute on without a network
# call. Roughly ordered largest-cap to smallest, which the synthetic 24h
# volume below mirrors, so liquidity screening produces a sensible ranking.
_MOCK_UNIVERSE_BASE_ASSETS = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK",
    "TRX", "MATIC", "LTC", "SHIB", "BCH", "UNI", "ATOM", "XLM", "ETC", "FIL",
    "APT", "NEAR", "ARB", "OP", "VET", "ICP", "HBAR", "SAND", "MANA", "AAVE",
    "ALGO", "EGLD", "THETA", "AXS", "GRT", "EOS", "FLOW", "CHZ", "XTZ", "KAVA",
    "MINA", "ZEC", "ENJ", "1INCH", "GMX", "SNX", "CRV", "COMP", "LDO", "INJ",
]

# Realistic ballpark anchor prices per base asset, so mock data lands in the
# right order of magnitude (this is illustrative synthetic data, not a live
# feed — the point is "looks like a real market", not tracking actual spot
# price). Previously this used Python's built-in hash(symbol), which is
# randomized per process by default and produced base prices anywhere from
# ~$100 to ~$50,100 for ANY symbol — including large, well-known assets like
# ETH — which is what caused garbled, wildly-wrong-magnitude prices.
_ANCHOR_PRICES = {
    "BTC": 65000, "ETH": 3400, "BNB": 580, "SOL": 150, "XRP": 0.55,
    "ADA": 0.45, "DOGE": 0.12, "AVAX": 28, "DOT": 6.0, "LINK": 14,
    "TRX": 0.12, "MATIC": 0.55, "LTC": 75, "SHIB": 0.000018, "BCH": 380,
    "UNI": 7.0, "ATOM": 7.0, "XLM": 0.11, "ETC": 20, "FIL": 4.5,
    "APT": 8.0, "NEAR": 4.5, "ARB": 0.8, "OP": 1.8, "VET": 0.03,
    "ICP": 9.0, "HBAR": 0.06, "SAND": 0.35, "MANA": 0.35, "AAVE": 90,
    "ALGO": 0.15, "EGLD": 30, "THETA": 1.3, "AXS": 5.0, "GRT": 0.15,
    "EOS": 0.6, "FLOW": 0.6, "CHZ": 0.07, "XTZ": 0.7, "KAVA": 0.4,
    "MINA": 0.4, "ZEC": 30, "ENJ": 0.2, "1INCH": 0.3, "GMX": 30,
    "SNX": 2.5, "CRV": 0.5, "COMP": 50, "LDO": 1.2, "INJ": 25,
}


def _seed_for(symbol: str, key: str) -> int:
    # Stable per (symbol, key) seed so the FIRST generation of a symbol's
    # history is reproducible across process restarts, while different
    # symbols diverge from each other. Uses hashlib (not Python's built-in
    # hash()) specifically because built-in hash() is randomized per
    # process — the same bug that caused the base-price issue above would
    # resurface here otherwise. Bars generated AFTER the initial backfill
    # continue from the persistent Generator's live state, not this seed.
    h = hashlib.sha256(f"{symbol}:{key}".encode()).hexdigest()
    return int(h[:8], 16)


def _anchor_price(symbol: str) -> float:
    base_asset = symbol.split("/")[0].upper()
    if base_asset in _ANCHOR_PRICES:
        return _ANCHOR_PRICES[base_asset]
    # Unknown/long-tail asset: derive a modest, deterministic small-cap-style
    # price (a few cents to a few dollars) instead of the old unbounded
    # hash()-based range that could land anywhere from $100 to $50,100.
    h = hashlib.sha256(base_asset.encode()).hexdigest()
    scale = int(h[:8], 16) / 0xFFFFFFFF  # deterministic float in [0, 1)
    return round(0.05 + scale * 5.0, 6)


def _draw_bars(rng: np.random.Generator, n: int, start_price: float):
    """Draw n new 15m bars continuing on from start_price, using rng's live (advancing) state."""
    regime_len = 32  # ~8 hours of 15m bars per regime
    n_regimes = n // regime_len + 2
    regime_drifts = rng.choice([0.00025, -0.00025, 0.00002], size=n_regimes, p=[0.4, 0.35, 0.25])
    drift = np.repeat(regime_drifts, regime_len)[:n]

    vol = 0.0015 + 0.001 * rng.random(n)
    burst_mask = rng.random(n) < 0.02
    vol[burst_mask] *= 4

    returns = rng.normal(loc=drift, scale=vol)
    close = start_price * np.exp(np.cumsum(returns))

    open_ = np.roll(close, 1)
    open_[0] = start_price
    high = np.maximum(open_, close) * (1 + rng.random(n) * 0.0015)
    low = np.minimum(open_, close) * (1 - rng.random(n) * 0.0015)
    volume = rng.lognormal(mean=6, sigma=0.5, size=n) * (1 + 3 * burst_mask)

    return open_, high, low, close, volume


class _SymbolState:
    """Persistent, incrementally-extending price process for one symbol."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.rng = np.random.default_rng(_seed_for(symbol, "master"))
        now = datetime.utcnow().replace(minute=(datetime.utcnow().minute // _MASTER_MINUTES) * _MASTER_MINUTES,
                                         second=0, microsecond=0)
        start_price = _anchor_price(symbol)
        open_, high, low, close, volume = _draw_bars(self.rng, _MASTER_WINDOW_BARS, start_price)
        timestamps = [now - timedelta(minutes=_MASTER_MINUTES * (_MASTER_WINDOW_BARS - 1 - i)) for i in range(_MASTER_WINDOW_BARS)]
        self.df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=pd.DatetimeIndex(timestamps, name="ts"),
        )

    def latest(self) -> pd.DataFrame:
        """Extend the series with any new 15m bars that have become due since the last access, then return it."""
        now = datetime.utcnow().replace(minute=(datetime.utcnow().minute // _MASTER_MINUTES) * _MASTER_MINUTES,
                                         second=0, microsecond=0)
        last_ts = self.df.index[-1]
        bars_due = int((now - last_ts).total_seconds() // (_MASTER_MINUTES * 60))
        if bars_due > 0:
            start_price = float(self.df["close"].iloc[-1])
            open_, high, low, close, volume = _draw_bars(self.rng, bars_due, start_price)
            timestamps = [last_ts + timedelta(minutes=_MASTER_MINUTES * (i + 1)) for i in range(bars_due)]
            new_rows = pd.DataFrame(
                {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
                index=pd.DatetimeIndex(timestamps, name="ts"),
            )
            self.df = pd.concat([self.df, new_rows]).iloc[-_MASTER_WINDOW_BARS:]
        return self.df


_STORE: dict[str, _SymbolState] = {}
_STORE_LOCK = threading.Lock()


def _get_state(symbol: str) -> _SymbolState:
    with _STORE_LOCK:
        if symbol not in _STORE:
            _STORE[symbol] = _SymbolState(symbol)
        return _STORE[symbol]


class MockAdapter(DataAdapter):
    """
    Stateless from the caller's point of view (matches DataAdapter exactly),
    but reads from the process-wide, time-evolving _STORE above rather than
    generating a fresh isolated series per instance — that's what makes
    prices actually move between calls instead of being frozen.
    """

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        if timeframe not in TIMEFRAME_MINUTES:
            raise ValueError(f"Unsupported timeframe '{timeframe}'. Supported: {list(TIMEFRAME_MINUTES)}")

        master = _get_state(symbol).latest()
        if timeframe == "15m":
            return master.tail(limit)

        rule = _RESAMPLE_RULE[timeframe]
        resampled = master.resample(rule).agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna()
        return resampled.tail(limit)

    def get_latest_price(self, symbol: str) -> float:
        master = _get_state(symbol).latest()
        return float(master["close"].iloc[-1])

    def list_markets(self, quote_asset: str | None = None) -> list[dict]:
        quote_asset = (quote_asset or "USDT").upper()
        markets = []
        for rank, base in enumerate(_MOCK_UNIVERSE_BASE_ASSETS):
            symbol = f"{base}/{quote_asset}"
            # 1h bars over the last day give a real (synthetic) 24h price
            # change and a volume figure, computed the same way live data
            # would be — not hardcoded numbers dressed up as market data.
            df = self.get_ohlcv(symbol, "1h", limit=24)
            last_price = float(df["close"].iloc[-1])
            price_change_pct = float((df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100)

            # Liquidity roughly tracks cap rank (BTC >> a long-tail altcoin),
            # with enough per-symbol jitter that the screen isn't a trivial
            # fixed cutoff at position N.
            rng = np.random.default_rng(_seed_for(symbol, "volume"))
            base_liquidity = 400_000_000 / (1 + rank) ** 1.15
            quote_volume_24h = float(base_liquidity * rng.uniform(0.5, 1.5))

            markets.append({
                "symbol": symbol,
                "base_asset": base,
                "quote_asset": quote_asset,
                "status": "TRADING",
                "last_price": round_price(last_price),
                "quote_volume_24h": round(quote_volume_24h, 2),
                "price_change_pct_24h": round(price_change_pct, 3),
            })
        return markets
