"""
Live market data from Binance's public REST API.

No API key needed for market data (klines/ticker are public endpoints), so
this works the moment you set DATA_SOURCE=binance — no account required to
get started. You'd only need keys later if you extend this to actually place
orders, which this adapter deliberately does not do.

Docs: https://developers.binance.com/docs/binance-spot-api-docs/rest-api
"""
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from app.data.base import DataAdapter

BASE_URL = "https://api.binance.com"

# Our internal timeframe names map 1:1 onto Binance's interval strings —
# convenient, but kept explicit in case that ever changes.
TIMEFRAME_MAP = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}

_CACHE_TTL_SECONDS = 30  # avoid hammering the API when several agents ask
                          # for the same symbol/timeframe within one cycle

_EXCHANGE_INFO_TTL_SECONDS = 300  # symbol list/status barely changes intra-day
_TICKER_24H_TTL_SECONDS = 60      # volume/price-change stats refresh every minute

# Leveraged tokens (e.g. BTCUPUSDT, ETHBEARUSDT) are decay products, not spot
# markets — they'd pollute a trend/momentum scan with noise. Binance's own
# convention is a base asset ending in one of these suffixes.
_LEVERAGED_TOKEN_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")

# Stablecoin-vs-stablecoin pairs (e.g. USDCUSDT) have ~no directional signal
# to analyze — screen them out at the source rather than wasting an analysis
# slot on them.
_STABLECOINS = {"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "PYUSD", "EUR", "GBP", "TRY"}


def _to_binance_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTCUSDT'. Also accepts 'BTCUSDT' unchanged."""
    return symbol.replace("/", "").replace("-", "").upper()


def _is_leveraged_token(base_asset: str) -> bool:
    return base_asset.endswith(_LEVERAGED_TOKEN_SUFFIXES)


class BinanceError(RuntimeError):
    pass


class BinanceAdapter(DataAdapter):
    def __init__(self, session: requests.Session | None = None, timeout: float = 10.0):
        self.session = session or requests.Session()
        self.timeout = timeout
        self._ohlcv_cache: dict[tuple[str, str, int], tuple[float, pd.DataFrame]] = {}
        self._price_cache: dict[str, tuple[float, float]] = {}
        self._exchange_info_cache: tuple[float, list[dict]] | None = None
        self._ticker_24h_cache: tuple[float, dict[str, dict]] | None = None

    # ------------------------------------------------------------------ #
    # Public interface (matches DataAdapter / MockAdapter exactly)
    # ------------------------------------------------------------------ #
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe '{timeframe}'. Supported: {list(TIMEFRAME_MAP)}")

        cache_key = (symbol, timeframe, limit)
        cached = self._ohlcv_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        params = {
            "symbol": _to_binance_symbol(symbol),
            "interval": TIMEFRAME_MAP[timeframe],
            "limit": min(limit, 1000),  # Binance's own hard cap per request
        }
        data = self._get("/api/v3/klines", params)

        # Each row: [open_time, open, high, low, close, volume, close_time,
        #            quote_vol, trades, taker_buy_base, taker_buy_quote, ignore]
        rows = [
            {
                "ts": datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc).replace(tzinfo=None),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in data
        ]
        df = pd.DataFrame(rows).set_index("ts")
        self._ohlcv_cache[cache_key] = (time.time(), df)
        return df

    def get_latest_price(self, symbol: str) -> float:
        cached = self._price_cache.get(symbol)
        if cached and (time.time() - cached[0]) < 5:  # prices move fast, shorter TTL
            return cached[1]

        data = self._get("/api/v3/ticker/price", {"symbol": _to_binance_symbol(symbol)})
        price = float(data["price"])
        self._price_cache[symbol] = (time.time(), price)
        return price

    def list_markets(self, quote_asset: str | None = None) -> list[dict]:
        """
        Discover every tradable spot pair (optionally filtered to one quote
        asset), enriched with 24h volume/price-change so the scanner can
        screen by liquidity without a second round trip per symbol.

        Two calls total, each cached separately (exchangeInfo for the
        tradable universe + per-symbol base/quote assets, ticker/24hr for
        volume) — cheap regardless of how many symbols end up in the result.
        """
        tradable = self._get_exchange_info()
        tickers = self._get_all_tickers_24h()

        if quote_asset:
            quote_asset = quote_asset.upper()

        markets = []
        for info in tradable:
            if quote_asset and info["quote_asset"] != quote_asset:
                continue
            if _is_leveraged_token(info["base_asset"]):
                continue
            if info["base_asset"] in _STABLECOINS and info["quote_asset"] in _STABLECOINS:
                continue  # stablecoin-vs-stablecoin: no directional signal to analyze

            ticker = tickers.get(info["binance_symbol"])
            if not ticker:
                continue  # no recent trading activity to report on

            markets.append({
                "symbol": f"{info['base_asset']}/{info['quote_asset']}",
                "base_asset": info["base_asset"],
                "quote_asset": info["quote_asset"],
                "status": info["status"],
                "last_price": ticker["last_price"],
                "quote_volume_24h": ticker["quote_volume_24h"],
                "price_change_pct_24h": ticker["price_change_pct_24h"],
            })

        return markets

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _get_exchange_info(self) -> list[dict]:
        cached = self._exchange_info_cache
        if cached and (time.time() - cached[0]) < _EXCHANGE_INFO_TTL_SECONDS:
            return cached[1]

        data = self._get("/api/v3/exchangeInfo", {})
        tradable = [
            {
                "binance_symbol": s["symbol"],
                "base_asset": s["baseAsset"],
                "quote_asset": s["quoteAsset"],
                "status": s["status"],
            }
            for s in data.get("symbols", [])
            if s.get("status") == "TRADING" and s.get("isSpotTradingAllowed", True)
        ]
        self._exchange_info_cache = (time.time(), tradable)
        return tradable

    def _get_all_tickers_24h(self) -> dict[str, dict]:
        cached = self._ticker_24h_cache
        if cached and (time.time() - cached[0]) < _TICKER_24H_TTL_SECONDS:
            return cached[1]

        data = self._get("/api/v3/ticker/24hr", {})
        tickers = {
            row["symbol"]: {
                "last_price": float(row["lastPrice"]),
                "quote_volume_24h": float(row["quoteVolume"]),
                "price_change_pct_24h": float(row["priceChangePercent"]),
            }
            for row in data
        }
        self._ticker_24h_cache = (time.time(), tickers)
        return tickers

    def _get(self, path: str, params: dict):
        try:
            resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise BinanceError(f"Network error calling {path}: {exc}") from exc

        if resp.status_code == 429:
            raise BinanceError("Binance rate limit hit (429) — back off and retry with fewer symbols/agents.")
        if not resp.ok:
            raise BinanceError(f"Binance API error {resp.status_code} on {path}: {resp.text[:200]}")

        return resp.json()
