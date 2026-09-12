"""
One-time (or re-runnable) helper: approve the configured builder address
so subsequent orders from this API wallet can carry the builder code and
earn fee share.

Usage (from project root, with venv active and .env filled):

    python -m scripts.approve_builder_fee

Safe to run multiple times — it just re-approves at the same ceiling.
"""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

from app.config import settings
from app.execution import hyperliquid_adapter as hl


def main():
    if not settings.hyperliquid_private_key:
        print("HYPERLIQUID_PRIVATE_KEY is not set in .env")
        sys.exit(1)
    if not settings.hyperliquid_builder_address:
        print("HYPERLIQUID_BUILDER_ADDRESS is not set in .env")
        sys.exit(1)

    print(f"Environment : {settings.hyperliquid_env}")
    print(f"Builder     : {settings.hyperliquid_builder_address}")
    print(f"Max fee rate: {settings.hyperliquid_builder_max_fee_rate}")
    print()

    try:
        result = hl.ensure_builder_fee_approved()
        print("Approval result:", result)
        print("\nDone. Orders placed by this API wallet can now attach the builder code.")
    except hl.HyperliquidError as e:
        print(f"Failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
