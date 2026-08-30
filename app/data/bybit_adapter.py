"""
Live market data from Bybit's public v5 REST API. No API key needed for
market data. Bybit is not among the exchanges named in Nigeria's 2024 NCC
directive (which named Binance, Coinbase, and Kraken specifically), so this
is likely reachable without a VPN where Binance/Kraken are not — worth
trying first if you're in an affected region.

Docs: https://bybit-exchange.github.io/docs/v5/market/kline
"""
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from app.data.base import DataAdapter

BASE_URL = "https://api.bybit.com"

# Bybit's kline "interval" is minutes as a string, except daily/weekly/monthly
# which use letter codes.
TIMEFRAME_MAP = {"15m": "15", "1h": "60", "4h": "240", "1d": "D"}

_CACHE_TTL_SECONDS = 30
_INSTRUMENTS_TTL_SECONDS = 300
_TICKERS_TTL_SECONDS = 60

_LEVERAGED_TOKEN_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR", "3L", "3S", "5L", "5S")
_STABLECOINS = {"USDT", "USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "PYUSD", "EUR", "GBP"}


def _to_bybit_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTCUSDT'."""
    return symbol.replace("/", "").replace("-", "").upper()


def _is_leveraged_token(base_asset: str) -> bool:
    return base_asset.endswith(_LEVERAGED_TOKEN_SUFFIXES)


class BybitError(RuntimeError):
    pass


class BybitAdapter(DataAdapter):
    def __init__(self, session: requests.Session | None = None, timeout: float = 10.0):
        self.session = session or requests.Session()
        self.timeout = timeout
        self._ohlcv_cache: dict[tuple[str, str, int], tuple[float, pd.DataFrame]] = {}
        self._price_cache: dict[str, tuple[float, float]] = {}
        self._instruments_cache: tuple[float, list[dict]] | None = None
        self._tickers_cache: tuple[float, dict[str, dict]] | None = None

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
            "category": "spot",
            "symbol": _to_bybit_symbol(symbol),
            "interval": TIMEFRAME_MAP[timeframe],
            "limit": min(limit, 1000),
        }
        data = self._get("/v5/market/kline", params)
        rows_raw = data["result"]["list"]

        # Bybit returns klines newest-first — reverse to the oldest-first
        # order every other adapter (and the agents) expect.
        rows_raw = list(reversed(rows_raw))

        # Each row: [startTime, open, high, low, close, volume, turnover]
        rows = [
            {
                "ts": datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).replace(tzinfo=None),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }
            for row in rows_raw
        ]
        df = pd.DataFrame(rows).set_index("ts")
        self._ohlcv_cache[cache_key] = (time.time(), df)
        return df

    def get_latest_price(self, symbol: str) -> float:
        cached = self._price_cache.get(symbol)
        if cached and (time.time() - cached[0]) < 5:
            return cached[1]

        data = self._get("/v5/market/tickers", {"category": "spot", "symbol": _to_bybit_symbol(symbol)})
        tickers = data["result"]["list"]
        if not tickers:
            raise BybitError(f"Bybit returned no ticker data for {symbol}")
        price = float(tickers[0]["lastPrice"])
        self._price_cache[symbol] = (time.time(), price)
        return price

    def list_markets(self, quote_asset: str | None = None) -> list[dict]:
        """
        Discover every tradable spot pair (optionally filtered to one quote
        asset), enriched with 24h volume/price-change. Two cached calls
        total regardless of how many symbols end up in the result.
        """
        tradable = self._get_instruments()
        tickers = self._get_all_tickers()

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

            ticker = tickers.get(info["bybit_symbol"])
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
    def _get_instruments(self) -> list[dict]:
        cached = self._instruments_cache
        if cached and (time.time() - cached[0]) < _INSTRUMENTS_TTL_SECONDS:
            return cached[1]

        data = self._get("/v5/market/instruments-info", {"category": "spot"})
        tradable = [
            {
                "bybit_symbol": s["symbol"],
                "base_asset": s["baseCoin"],
                "quote_asset": s["quoteCoin"],
                "status": s.get("status", "Trading"),
            }
            for s in data["result"]["list"]
            if s.get("status") == "Trading"
        ]
        self._instruments_cache = (time.time(), tradable)
        return tradable

    def _get_all_tickers(self) -> dict[str, dict]:
        cached = self._tickers_cache
        if cached and (time.time() - cached[0]) < _TICKERS_TTL_SECONDS:
            return cached[1]

        data = self._get("/v5/market/tickers", {"category": "spot"})
        tickers = {}
        for row in data["result"]["list"]:
            try:
                tickers[row["symbol"]] = {
                    "last_price": float(row["lastPrice"]),
                    "quote_volume_24h": float(row["turnover24h"]),
                    # Bybit reports this as a fraction (0.0177), not a percent.
                    "price_change_pct_24h": float(row["price24hPcnt"]) * 100,
                }
            except (KeyError, ValueError):
                continue  # skip malformed rows rather than aborting the whole call
        self._tickers_cache = (time.time(), tickers)
        return tickers

    def _get(self, path: str, params: dict):
        try:
            resp = self.session.get(f"{BASE_URL}{path}", params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise BybitError(f"Network error calling {path}: {exc}") from exc

        if not resp.ok:
            raise BybitError(f"Bybit API error {resp.status_code} on {path}: {resp.text[:200]}")

        data = resp.json()
        # Bybit returns HTTP 200 even on logical errors — retCode 0 means success.
        if data.get("retCode") != 0:
            raise BybitError(f"Bybit API returned retCode={data.get('retCode')} on {path}: {data.get('retMsg')}")

        return data
