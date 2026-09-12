"""
Hyperliquid market-data adapter.

Implements the same DataAdapter interface as the CEX adapters so the scanner
can discover and analyse Hyperliquid perps alongside (or instead of) CEX
USDT pairs.

Notes:
- Hyperliquid perps are named by base asset only (BTC, ETH, ...).
- We surface them to the rest of the system as "BTC/USDT"-style symbols
  for compatibility with existing agents and the decision engine.
- OHLCV is fetched from Hyperliquid's candle snapshot endpoint.
- Liquidity screening uses approximate 24h volume when available; otherwise
  a high default so major perps always pass the screen.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd
import requests

from app.data.base import DataAdapter
from app.config import settings

logger = logging.getLogger(__name__)

# Map our internal timeframes to Hyperliquid candle intervals
_TF_MAP = {
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


def _api_url() -> str:
    from hyperliquid.utils import constants
    return constants.TESTNET_API_URL if settings.hyperliquid_env == "testnet" else constants.MAINNET_API_URL


class HyperliquidAdapter(DataAdapter):
    """Read-only market data from Hyperliquid (no trading keys required)."""

    def __init__(self):
        self._base = _api_url().rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def _post(self, payload: dict) -> dict | list:
        r = self._session.post(f"{self._base}/info", json=payload, timeout=15)
        r.raise_for_status()
        return r.json()

    def list_markets(self, quote_asset: str | None = None) -> list[dict]:
        """
        Return Hyperliquid perps in the same shape the scanner expects.
        We present them as BASE/USDT so the rest of the pipeline stays
        unchanged. quote_asset is accepted for interface compatibility;
        Hyperliquid perps are effectively USD-margined.
        """
        try:
            mids = self._post({"type": "allMids"})
            if not isinstance(mids, dict):
                logger.warning("Unexpected allMids response: %s", type(mids))
                return []

            # Best-effort volume / change data
            meta = {}
            try:
                meta_resp = self._post({"type": "metaAndAssetCtxs"})
                if isinstance(meta_resp, list) and len(meta_resp) >= 2:
                    universe = meta_resp[0].get("universe", [])
                    ctxs = meta_resp[1]
                    for i, asset in enumerate(universe):
                        name = asset.get("name")
                        if name and i < len(ctxs):
                            meta[name] = ctxs[i]
            except Exception as e:
                logger.debug("Could not fetch metaAndAssetCtxs: %s", e)

            markets = []
            for coin, mid in mids.items():
                if not coin or coin.startswith("@"):
                    continue
                ctx = meta.get(coin, {})
                day_ntl = float(ctx.get("dayNtlVlm", 0) or 0)
                prev = float(ctx.get("prevDayPx", 0) or 0)
                mid_f = float(mid)
                change = ((mid_f - prev) / prev * 100) if prev > 0 else 0.0

                markets.append({
                    "symbol": f"{coin}/USDT",
                    "base_asset": coin,
                    "quote_asset": "USDT",
                    "status": "TRADING",
                    "last_price": mid_f,
                    "quote_volume_24h": day_ntl if day_ntl > 0 else 50_000_000,  # fallback so majors pass screen
                    "price_change_pct_24h": change,
                    "source": "hyperliquid",
                })
            return markets
        except Exception as e:
            logger.error("Hyperliquid list_markets failed: %s", e)
            return []

    def get_latest_price(self, symbol: str) -> float:
        coin = symbol.split("/")[0].upper()
        mids = self._post({"type": "allMids"})
        if coin not in mids:
            raise ValueError(f"No Hyperliquid mid for {coin}")
        return float(mids[coin])

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        coin = symbol.split("/")[0].upper()
        interval = _TF_MAP.get(timeframe)
        if not interval:
            raise ValueError(f"Unsupported timeframe for Hyperliquid: {timeframe}")

        # Hyperliquid candleSnapshot expects startTime in ms
        # Request a generous window; we trim to `limit` afterwards.
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        # rough lookback: limit * interval minutes
        minutes = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}.get(interval, 60)
        start_ms = end_ms - (limit * minutes * 60 * 1000)

        raw = self._post({
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
            },
        })

        if not isinstance(raw, list) or not raw:
            # Fallback: synthesize a flat series from mid so agents don't crash
            mid = self.get_latest_price(symbol)
            idx = pd.date_range(end=datetime.now(timezone.utc), periods=limit, freq=interval)
            return pd.DataFrame({
                "open": mid, "high": mid, "low": mid, "close": mid, "volume": 0.0
            }, index=idx)

        rows = []
        for c in raw:
            # Hyperliquid candle fields: t (open time ms), o,h,l,c,v, n, ...
            ts = datetime.fromtimestamp(c["t"] / 1000, tz=timezone.utc)
            rows.append({
                "ts": ts,
                "open": float(c["o"]),
                "high": float(c["h"]),
                "low": float(c["l"]),
                "close": float(c["c"]),
                "volume": float(c.get("v", 0)),
            })

        df = pd.DataFrame(rows).set_index("ts").sort_index()
        if len(df) > limit:
            df = df.iloc[-limit:]
        return df
