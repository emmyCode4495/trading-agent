"""
Live market data from MEXC's public spot v3 REST API. No API key needed for
market data. MEXC is not among the exchanges named in Nigeria's 2024 NCC
directive (Binance, Coinbase, Kraken) — its P2P service is actively marketed
to Nigerian users with no VPN workaround mentioned, a strong signal it's
reachable without one.

MEXC's spot API is close to Binance's (same field names in most places),
but NOT identical — two real differences handled here:
  - No native "1h" kline interval; MEXC uses "60m" instead.
  - Symbol status uses different values ("ENABLED"/"1" depending on
    endpoint/version) rather than Binance's "TRADING", so tradability is
    checked more defensively here instead of matching one exact string.

Docs: https://mexcdevelop.github.io/apidocs/spot_v3_en/
"""
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from app.data.base import DataAdapter

BASE_URL = "https://api.mexc.com"

TIMEFRAME_MAP = {"15m": "15m", "1h": "60m", "4h": "4h", "1d": "1d"}

_CACHE_TTL_SECONDS = 30
_EXCHANGE_INFO_TTL_SECONDS = 300
_TICKER_24H_TTL_SECONDS = 60

_LEVERAGED_TOKEN_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S")
_STABLECOINS = {"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "PYUSD"}


def _to_mexc_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTCUSDT'."""
    return symbol.replace("/", "").replace("-", "").upper()


def _is_leveraged_token(base_asset: str) -> bool:
    return base_asset.endswith(_LEVERAGED_TOKEN_SUFFIXES)


def _is_tradable(status) -> bool:
    # MEXC has used different status representations across API versions/
    # endpoints ("ENABLED", "1", "TRADING"). Rather than pin to one exact
    # value and silently return an empty universe if MEXC changes it again,
    # explicitly exclude the known "not tradable" values instead.
    return str(status).upper() not in ("DISABLED", "0", "BREAK", "HALT", "OFFLINE")


class MexcError(RuntimeError):
    pass


class MexcAdapter(DataAdapter):
    def __init__(self, session: requests.Session | None = None, timeout: float = 10.0):
        self.session = session or requests.Session()
        self.timeout = timeout
        self._ohlcv_cache: dict[tuple[str, str, int], tuple[float, pd.DataFrame]] = {}
        self._price_cache: dict[str, tuple[float, float]] = {}
        self._exchange_info_cache: tuple[float, list[dict]] | None = None
        self._ticker_24h_cache: tuple[float, dict[str, dict]] | None = None

    # ------------------------------------------------------------------ #
    # Public interface (matches DataAdapter / MockAdapter / BinanceAdapter)
    # ------------------------------------------------------------------ #
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        if timeframe not in TIMEFRAME_MAP:
            raise ValueError(f"Unsupported timeframe '{timeframe}'. Supported: {list(TIMEFRAME_MAP)}")

        cache_key = (symbol, timeframe, limit)
        cached = self._ohlcv_cache.get(cache_key)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            return cached[1]

        params = {
            "symbol": _to_mexc_symbol(symbol),
            "interval": TIMEFRAME_MAP[timeframe],
            "limit": min(limit, 1000),
        }
        data = self._get("/api/v3/klines", params)

        # Each row (Binance-compatible): [open_time, open, high, low, close,
        # volume, close_time, ...additional fields we don't need]
        rows = [
            {
                "ts": datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).replace(tzinfo=None),
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
        if cached and (time.time() - cached[0]) < 5:
            return cached[1]

        data = self._get("/api/v3/ticker/price", {"symbol": _to_mexc_symbol(symbol)})
        price = float(data["price"])
        self._price_cache[symbol] = (time.time(), price)
        return price

    def list_markets(self, quote_asset: str | None = None) -> list[dict]:
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
                continue

            ticker = tickers.get(info["mexc_symbol"])
            if not ticker:
                continue

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
                "mexc_symbol": s["symbol"],
                "base_asset": s["baseAsset"],
                "quote_asset": s["quoteAsset"],
                "status": s.get("status", "ENABLED"),
            }
            for s in data.get("symbols", [])
            if _is_tradable(s.get("status", "ENABLED")) and s.get("isSpotTradingAllowed", True)
        ]
        self._exchange_info_cache = (time.time(), tradable)
        return tradable

    def _get_all_tickers_24h(self) -> dict[str, dict]:
        cached = self._ticker_24h_cache
        if cached and (time.time() - cached[0]) < _TICKER_24H_TTL_SECONDS:
            return cached[1]

        data = self._get("/api/v3/ticker/24hr", {})
        tickers = {}
        for row in data:
            try:
                tickers[row["symbol"]] = {
                    "last_price": float(row["lastPrice"]),
                    "quote_volume_24h": float(row["quoteVolume"]),
                    "price_change_pct_24h": float(row["priceChangePercent"]),
                }
            except (KeyError, ValueError):
                continue
        self._ticker_24h_cache = (time.time(), tickers)
        return tickers

    def _get(self, path: str, params: dict):
        try:
            resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise MexcError(f"Network error calling {path}: {exc}") from exc

        if resp.status_code == 429:
            raise MexcError("MEXC rate limit hit (429) — back off and retry with fewer symbols/agents.")
        if not resp.ok:
            raise MexcError(f"MEXC API error {resp.status_code} on {path}: {resp.text[:200]}")

        return resp.json()
