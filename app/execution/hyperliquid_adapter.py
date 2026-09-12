"""
Thin wrapper around `hyperliquid-python-sdk`. Same philosophy as
app/data/*_adapter.py: isolate the network/SDK calls behind a small, clear
interface so executor.py never touches the SDK directly, and so this file
alone is what needs mocking for offline tests (see
scripts/test_hyperliquid_adapter.py).

Signatures below were verified against the installed hyperliquid-python-sdk
(not guessed) — see inspect.signature output used while building this:
  Exchange.market_open(name, is_buy, sz, px=None, slippage=0.05, cloid=None, builder=None)
  Exchange.market_close(coin, sz=None, px=None, slippage=0.05, cloid=None, builder=None)
  Exchange.approve_builder_fee(builder, max_fee_rate)
  Info.user_state(address, dex="")
  Info.all_mids(dex="")
  BuilderInfo = {"b": str, "f": int}   # f is tenths of a basis point
"""
import logging

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from app.config import settings

logger = logging.getLogger(__name__)


class HyperliquidError(Exception):
    pass


def to_hl_symbol(symbol: str) -> str:
    """'BTC/USDT' -> 'BTC'. Hyperliquid perps are named by base asset only."""
    return symbol.split("/")[0].upper()


def _api_url() -> str:
    return constants.TESTNET_API_URL if settings.hyperliquid_env == "testnet" else constants.MAINNET_API_URL


def _builder_info():
    if not settings.hyperliquid_builder_address:
        return None
    return {"b": settings.hyperliquid_builder_address, "f": settings.hyperliquid_builder_fee_tenths_bps}


def get_client():
    """
    Builds (info, exchange) from the configured API wallet. Raises
    HyperliquidError with an actionable message rather than letting
    eth_account/the SDK throw something opaque when a key is missing.
    """
    if not settings.hyperliquid_private_key:
        env_note = "https://app.hyperliquid-testnet.xyz/API" if settings.hyperliquid_env == "testnet" else "https://app.hyperliquid.xyz/API"
        raise HyperliquidError(
            f"HYPERLIQUID_PRIVATE_KEY is not set. Generate an API wallet at {env_note} "
            "and put its private key (not your main wallet's) in .env."
        )
    wallet = Account.from_key(settings.hyperliquid_private_key)
    base_url = _api_url()
    info = Info(base_url, skip_ws=True)
    account_address = settings.hyperliquid_account_address or wallet.address
    exchange = Exchange(wallet, base_url, account_address=account_address)
    return info, exchange


def ensure_builder_fee_approved() -> dict:
    """
    One-time approval so this wallet's orders can carry the builder code.
    Call this once during setup (see scripts/) — safe to call again later,
    it just re-approves at the same ceiling.
    """
    if not settings.hyperliquid_builder_address:
        raise HyperliquidError("HYPERLIQUID_BUILDER_ADDRESS is not set — nothing to approve.")
    _, exchange = get_client()
    result = exchange.approve_builder_fee(settings.hyperliquid_builder_address, settings.hyperliquid_builder_max_fee_rate)
    logger.info("Builder fee approval result: %s", result)
    return result


def get_account_equity() -> float:
    """Total account value in USD — what sizing.py sizes positions against."""
    info, exchange = get_client()
    state = info.user_state(exchange.account_address)
    return float(state["marginSummary"]["accountValue"])


def get_current_position(hl_symbol: str) -> dict | None:
    """
    Returns the open position dict for hl_symbol (with at least 'szi', the
    signed size — positive is long, negative is short) or None if flat.
    """
    info, exchange = get_client()
    state = info.user_state(exchange.account_address)
    for p in state.get("assetPositions", []):
        pos = p.get("position", {})
        if pos.get("coin") == hl_symbol and float(pos.get("szi", 0)) != 0:
            return pos
    return None


def list_perp_symbols() -> set[str]:
    """
    Returns the set of currently listed Hyperliquid perp base symbols
    (e.g. {"BTC", "ETH", "SOL", ...}). Used by the executor to decide
    whether a CEX signal can actually be traded on Hyperliquid.
    """
    info, _ = get_client()
    mids = info.all_mids()
    return set(mids.keys())


def is_tradeable(hl_symbol: str) -> bool:
    """True if hl_symbol is a currently listed Hyperliquid perp."""
    try:
        return hl_symbol in list_perp_symbols()
    except Exception:
        # Network / auth issues should not crash the scanner; treat as
        # not-tradeable so the signal is still recorded and skipped cleanly.
        logger.warning("Could not fetch Hyperliquid market list; treating %s as not tradeable", hl_symbol)
        return False


def get_mid_price(hl_symbol: str) -> float:
    info, _ = get_client()
    mids = info.all_mids()
    if hl_symbol not in mids:
        raise HyperliquidError(
            f"No Hyperliquid market found for {hl_symbol!r}. "
            "Only symbols that exist as Hyperliquid perps can be executed."
        )
    return float(mids[hl_symbol])


def open_market_position(hl_symbol: str, is_buy: bool, size: float) -> dict:
    """
    Opens (or adds to) a position with the configured builder code attached,
    so every fill this system generates attributes its fee share to
    HYPERLIQUID_BUILDER_ADDRESS. Market order, sized in units of the
    underlying asset (not USD notional).

    Size is rounded to a safe number of decimals to avoid Hyperliquid
    precision rejections on testnet/mainnet.
    """
    if size <= 0:
        raise HyperliquidError(f"Invalid size {size} for {hl_symbol}")

    # Hyperliquid is strict about size precision. 4–6 decimals is safe for
    # most perps; we use 4 as a conservative default for the MVP.
    size = round(float(size), 4)
    if size <= 0:
        raise HyperliquidError(f"Size rounded to zero for {hl_symbol}")

    _, exchange = get_client()
    result = exchange.market_open(
        hl_symbol,
        is_buy,
        size,
        None,
        settings.hyperliquid_max_slippage_pct,
        builder=_builder_info(),
    )
    if result.get("status") != "ok":
        raise HyperliquidError(f"market_open failed for {hl_symbol}: {result}")
    logger.info(
        "Opened %s %s size=%.4f builder=%s → %s",
        "LONG" if is_buy else "SHORT",
        hl_symbol,
        size,
        settings.hyperliquid_builder_address or "none",
        result,
    )
    return result


def close_position(hl_symbol: str) -> dict:
    """Closes the entire open position in hl_symbol at market, builder-attributed."""
    _, exchange = get_client()
    result = exchange.market_close(
        hl_symbol,
        None,
        None,
        settings.hyperliquid_max_slippage_pct,
        builder=_builder_info(),
    )
    if result.get("status") != "ok":
        raise HyperliquidError(f"market_close failed for {hl_symbol}: {result}")
    logger.info("Closed position %s → %s", hl_symbol, result)
    return result
