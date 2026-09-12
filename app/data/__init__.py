from app.config import settings
from app.data.mock_adapter import MockAdapter

# Registry of real exchange adapters, used both for a direct DATA_SOURCE
# choice and to build the priority list for DATA_SOURCE=auto. Populated
# lazily so importing this module never requires the `requests` library's
# transitive imports to succeed unless a real adapter is actually used.
_REAL_ADAPTER_REGISTRY = {}


def _load_registry():
    if _REAL_ADAPTER_REGISTRY:
        return _REAL_ADAPTER_REGISTRY
    from app.data.binance_adapter import BinanceAdapter
    from app.data.bybit_adapter import BybitAdapter
    from app.data.mexc_adapter import MexcAdapter
    from app.data.hyperliquid_adapter import HyperliquidAdapter
    _REAL_ADAPTER_REGISTRY.update({
        "binance": BinanceAdapter,
        "bybit": BybitAdapter,
        "mexc": MexcAdapter,
        "hyperliquid": HyperliquidAdapter,
        "hl": HyperliquidAdapter,
    })
    return _REAL_ADAPTER_REGISTRY


def get_adapter():
    source = settings.data_source.strip().lower()

    if source == "mock":
        return MockAdapter()

    # Combined mode: CEX failover + Hyperliquid markets merged.
    # Scanner sees both universes; execution still only happens for
    # symbols that exist as Hyperliquid perps.
    if source in ("combined", "cex+hl", "all"):
        from app.data.combined_adapter import CombinedAdapter
        return CombinedAdapter()

    if source in ("auto", "multi", "failover"):
        from app.data.failover_adapter import FailoverAdapter
        registry = _load_registry()
        priority = [p.strip().lower() for p in settings.data_source_priority.split(",") if p.strip()]
        adapters = [(name, registry[name]()) for name in priority if name in registry]
        if not adapters:
            raise ValueError(
                f"DATA_SOURCE_PRIORITY='{settings.data_source_priority}' matched no known exchange "
                f"(known: {list(registry)})"
            )
        return FailoverAdapter(adapters)

    registry = _load_registry()
    if source in registry:
        return registry[source]()

    raise ValueError(
        f"Unknown DATA_SOURCE: '{settings.data_source}'. "
        f"Use 'mock', 'auto', 'combined', or one of: {list(registry)}"
    )
