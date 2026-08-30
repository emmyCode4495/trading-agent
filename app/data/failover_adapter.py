"""
Wraps a prioritized list of real exchange adapters and, for every call,
tries them in order until one actually works — so a single exchange being
geo-blocked, rate-limited, or briefly down doesn't take the whole scanner
down, and you don't have to hand-pick which one is reachable from wherever
this happens to be running.

This is what DATA_SOURCE=auto resolves to (see app/data/__init__.py), using
the exchanges and order from settings.data_source_priority.
"""
import logging
import time

from app.data.base import DataAdapter

log = logging.getLogger("failover_adapter")

# How long to keep preferring the exchange that last worked for a given
# call, before trying the full priority order again. Avoids repeatedly
# re-trying a currently-unreachable exchange first on every single call
# within a session, while still eventually re-checking it (in case a block
# was temporary).
_REMEMBER_TTL_SECONDS = 300


class AllAdaptersFailedError(RuntimeError):
    pass


class FailoverAdapter(DataAdapter):
    def __init__(self, adapters: list[tuple[str, DataAdapter]]):
        if not adapters:
            raise ValueError("FailoverAdapter needs at least one (name, adapter) pair")
        self.adapters = adapters
        self._last_good: dict[str, tuple[str, float]] = {}  # cache_key -> (adapter_name, timestamp)

    def get_ohlcv(self, symbol: str, timeframe: str, limit: int = 200):
        return self._try_each(f"ohlcv:{symbol}:{timeframe}", "get_ohlcv", symbol, timeframe, limit)

    def get_latest_price(self, symbol: str) -> float:
        return self._try_each(f"price:{symbol}", "get_latest_price", symbol)

    def list_markets(self, quote_asset: str | None = None) -> list[dict]:
        return self._try_each(f"markets:{quote_asset}", "list_markets", quote_asset)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _ordered_for(self, cache_key: str):
        remembered = self._last_good.get(cache_key)
        if remembered and (time.time() - remembered[1]) < _REMEMBER_TTL_SECONDS:
            preferred_name = remembered[0]
            preferred = [(n, a) for n, a in self.adapters if n == preferred_name]
            rest = [(n, a) for n, a in self.adapters if n != preferred_name]
            return preferred + rest
        return self.adapters

    def _try_each(self, cache_key: str, fn_name: str, *args, **kwargs):
        errors = []
        for name, adapter in self._ordered_for(cache_key):
            try:
                result = getattr(adapter, fn_name)(*args, **kwargs)
                self._last_good[cache_key] = (name, time.time())
                return result
            except Exception as exc:  # noqa: BLE001 — deliberately broad: any
                # failure reason (network, geo-block, rate limit, bad data)
                # should just mean "try the next exchange", not crash the scan
                errors.append(f"{name}: {exc}")
                log.warning("Exchange %s failed for %s(%s) -> trying next: %s", name, fn_name, cache_key, exc)
                continue

        raise AllAdaptersFailedError(
            f"All configured exchanges failed for {fn_name} ({cache_key}): " + " | ".join(errors)
        )
