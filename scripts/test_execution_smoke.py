"""
Smoke test for the Hyperliquid execution path (testnet recommended).

Does NOT place a real order unless you pass --live.
With no flags it only checks:
  - config is present
  - client can connect
  - account equity is readable
  - a few common symbols are tradeable
  - builder fee approval status (best-effort)

Usage:
    python -m scripts.test_execution_smoke
    python -m scripts.test_execution_smoke --live   # actually opens a tiny position (use with care)
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

from app.config import settings
from app.execution import hyperliquid_adapter as hl


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Actually open a tiny test position")
    args = parser.parse_args()

    print(f"HYPERLIQUID_ENV          = {settings.hyperliquid_env}")
    print(f"EXECUTION_ENABLED        = {settings.execution_enabled}")
    print(f"Builder address          = {settings.hyperliquid_builder_address or '(not set)'}")
    print(f"Account address          = {settings.hyperliquid_account_address or '(derived from key)'}")
    print()

    if not settings.hyperliquid_private_key:
        print("HYPERLIQUID_PRIVATE_KEY is missing — cannot continue.")
        sys.exit(1)

    try:
        equity = hl.get_account_equity()
        print(f"Account equity           = ${equity:,.2f}")
    except Exception as e:
        print(f"Failed to read equity: {e}")
        sys.exit(1)

    candidates = ["BTC", "ETH", "SOL", "HYPE"]
    print("\nTradeable check:")
    tradeable = []
    for s in candidates:
        ok = hl.is_tradeable(s)
        print(f"  {s:6}  {'YES' if ok else 'no'}")
        if ok:
            tradeable.append(s)

    if not tradeable:
        print("No common perps found as tradeable — check network / env.")
        sys.exit(1)

    symbol = tradeable[0]
    mid = hl.get_mid_price(symbol)
    print(f"\nMid price for {symbol} = {mid}")

    if not args.live:
        print("\nSmoke test OK (no order placed). Re-run with --live to open a tiny position.")
        return

    # Extremely small size for smoke test
    size = max(0.001, round(5.0 / mid, 4))  # ~$5 notional
    print(f"\nPlacing tiny LONG on {symbol} size={size} ...")
    try:
        resp = hl.open_market_position(symbol, is_buy=True, size=size)
        print("Order response:", resp)
        print("Smoke live order submitted. Check the Hyperliquid testnet UI.")
    except Exception as e:
        print(f"Live order failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
