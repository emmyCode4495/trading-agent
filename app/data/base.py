"""
Every data source (mock, Binance, a stock API, whatever) implements this
same interface. Nothing downstream (agents, decision engine, backtester,
scanner) needs to know or care where the candles came from.
"""
from abc import ABC, abstractmethod

import pandas as pd


class DataAdapter(ABC):
    @abstractmethod
    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """
        Return a DataFrame indexed by timestamp with columns:
        open, high, low, close, volume — most recent bar last.
        """
        raise NotImplementedError

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float:
        raise NotImplementedError

    @abstractmethod
    def list_markets(self, quote_asset: str | None = None) -> list[dict]:
        """
        Discover the tradable universe on this exchange — this is what makes
        the scanner autonomous instead of driven by a hardcoded watchlist.

        Return one dict per tradable symbol:
            {
                "symbol": "BTC/USDT",
                "base_asset": "BTC",
                "quote_asset": "USDT",
                "status": "TRADING",
                "last_price": 67000.12,
                "quote_volume_24h": 1834920123.45,   # liquidity screen uses this
                "price_change_pct_24h": 2.31,
            }

        If quote_asset is given (e.g. "USDT"), only symbols quoted in that
        asset are returned. Implementations should exclude non-tradable
        symbols (delisted, halted, pre-launch) themselves — callers should
        not need to filter status.
        """
        raise NotImplementedError
