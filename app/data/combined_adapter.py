"""
Combined data adapter: merges CEX (Bybit/MEXC/Binance failover) + Hyperliquid
perps into one universe for the scanner.

- list_markets() returns the union (Hyperliquid symbols take precedence on
  name collision so we prefer the executable venue).
- get_ohlcv / get_latest_price prefer Hyperliquid when the symbol is a
  known HL perp, otherwise fall back to the CEX adapter.
"""
from __future__ import annotations

import logging

import pandas as pd

from app.data.base import DataAdapter
from app.data.failover_adapter import FailoverAdapter
from app.data.hyperliquid_adapter import HyperliquidAdapter
from app.config import settings

logger = logging.getLogger(__name__)


class CombinedAdapter(DataAdapter):
    def __init__(self):
        # CEX side – reuse the existing failover logic
        from app.data import _load_registry
        registry = _load_registry()
        priority = [p.strip().lower() for p in settings.data_source_priority.split(",") if p.strip()]
        cex_adapters = [(name, registry[name]()) for name in priority if name in registry and name not in ("hyperliquid", "hl")]
        if not cex_adapters:
            # fallback to bybit alone if priority is empty/broken
            from app.data.bybit_adapter import BybitAdapter
            cex_adapters = [("bybit", BybitAdapter())]
        self.cex = FailoverAdapter(cex_adapters)
        self.hl = HyperliquidAdapter()
        self._hl_bases: set[str] | None = None

    def _hl_base_set(self) -> set[str]:
        if self._hl_bases is None:
            try:
                markets = self.hl.list_markets()
                self._hl_bases = {m["base_asset"] for m in markets}
            except Exception:
                self._hl_bases = set()
        return self._hl_bases

    def list_markets(self, quote_asset: str | None = None) -> list[dict]:
        cex_markets = []
        hl_markets = []
        try:
            cex_markets = self.cex.list_markets(quote_asset=quote_asset)
        except Exception as e:
            logger.warning("CEX list_markets failed: %s", e)
        try:
            hl_markets = self.hl.list_markets(quote_asset=quote_asset)
        except Exception as e:
            logger.warning("Hyperliquid list_markets failed: %s", e)

        # Prefer Hyperliquid entry when the same base appears on both
        by_symbol = {}
        for m in cex_markets:
            by_symbol[m["symbol"]] = m
        for m in hl_markets:
            by_symbol[m["symbol"]] = m  # HL overwrites

        return list(by_symbol.values())

    def get_latest_price(self, symbol: str) -> float:
        base = symbol.split("/")[0].upper()
        if base in self._hl_base_set():
            try:
                return self.hl.get_latest_price(symbol)
            except Exception as e:
                logger.debug("HL price failed for %s, falling back to CEX: %s", symbol, e)
        return self.cex.get_latest_price(symbol)

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        base = symbol.split("/")[0].upper()
        if base in self._hl_base_set():
            try:
                return self.hl.get_ohlcv(symbol, timeframe, limit)
            except Exception as e:
                logger.debug("HL ohlcv failed for %s, falling back to CEX: %s", symbol, e)
        return self.cex.get_ohlcv(symbol, timeframe, limit)
