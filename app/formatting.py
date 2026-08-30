"""
Shared price precision logic. Used anywhere a price gets rounded before
being stored, reported, or displayed, so an entry/target/invalidation price
always shows a sensible number of decimals for its magnitude instead of a
fixed decimal count that looks wrong at very different price scales (e.g.
4 decimals is fine for ETH at ~$3,400 but produces nonsense-looking output
for a sub-cent token, and is *too many* significant digits for anything
above $100).
"""


def price_decimals(price: float) -> int:
    """How many decimal places make sense to display for a price of this size."""
    price = abs(price)
    if price == 0:
        return 2
    if price >= 1000:
        return 2
    if price >= 1:
        return 4
    if price >= 0.01:
        return 6
    return 8


def round_price(price):
    """Round a price to a sensible number of decimals for its magnitude. Passes None through."""
    if price is None:
        return None
    return round(float(price), price_decimals(float(price)))


def format_price(price) -> str:
    """Human-readable price string with thousands separators, e.g. '43,290.75' or '0.0000412'."""
    if price is None:
        return "—"
    price = round_price(price)
    decimals = price_decimals(price)
    return f"{price:,.{decimals}f}"
