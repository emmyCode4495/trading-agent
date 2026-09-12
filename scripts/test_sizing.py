"""
Tests app.execution.sizing with plain numbers — no network, no SDK, pure math.

Run with: python -m scripts.test_sizing
"""
from app.config import settings
from app.execution.sizing import SizingError, compute_size


def _report(entry=100.0, invalidation=95.0, risk_level="low"):
    return {"symbol": "BTC/USDT", "entry_price": entry, "invalidation_price": invalidation, "risk_level": risk_level}


def test_basic_sizing_matches_hand_calculation():
    settings.risk_per_trade_pct = 1.0
    settings.max_position_pct_of_equity = 50.0  # high enough not to cap in this test
    result = compute_size(_report(entry=100.0, invalidation=95.0, risk_level="low"), equity=10_000, current_price=100.0)

    # $10,000 equity * 1% risk * 1.0 (low-risk multiplier) = $100 at risk.
    # Stop distance = |100 - 95| = 5. size = 100 / 5 = 20 units.
    assert abs(result.size - 20.0) < 1e-6, result.size
    assert abs(result.dollar_risk - 100.0) < 1e-6
    assert not result.capped_by_max_position
    print("OK  basic fixed-fractional sizing matches hand calculation")


def test_risk_level_multiplier_reduces_size():
    settings.risk_per_trade_pct = 1.0
    settings.max_position_pct_of_equity = 50.0
    low = compute_size(_report(risk_level="low"), equity=10_000, current_price=100.0)
    high = compute_size(_report(risk_level="high"), equity=10_000, current_price=100.0)

    assert high.size < low.size, "a 'high' risk_level report should size smaller than 'low' for the same setup"
    assert abs(high.size - low.size * 0.5) < 1e-6, "RISK_LEVEL_MULTIPLIER['high'] is 0.5x"
    print("OK  risk_level multiplier scales size down as documented")


def test_max_position_cap_kicks_in_on_tight_stop():
    settings.risk_per_trade_pct = 1.0
    settings.max_position_pct_of_equity = 10.0  # deliberately tight cap
    # Very tight stop (entry=100, invalidation=99.9) would otherwise produce
    # a huge position for the same $ risk — the cap must catch this.
    result = compute_size(_report(entry=100.0, invalidation=99.9, risk_level="low"), equity=10_000, current_price=100.0)

    max_notional = 10_000 * 0.10
    assert result.capped_by_max_position
    assert abs(result.notional - max_notional) < 1e-6
    print("OK  max_position_pct_of_equity caps an oversized position from a tight stop")


def test_zero_stop_distance_raises():
    try:
        compute_size(_report(entry=100.0, invalidation=100.0), equity=10_000, current_price=100.0)
        raise AssertionError("Expected SizingError")
    except SizingError:
        print("OK  zero stop distance (entry == invalidation) raises SizingError instead of dividing by zero")


def test_missing_prices_raises():
    try:
        compute_size({"symbol": "BTC/USDT", "entry_price": None, "invalidation_price": None}, equity=10_000, current_price=100.0)
        raise AssertionError("Expected SizingError")
    except SizingError:
        print("OK  missing entry/invalidation price raises SizingError instead of crashing")


def test_non_positive_equity_raises():
    try:
        compute_size(_report(), equity=0, current_price=100.0)
        raise AssertionError("Expected SizingError")
    except SizingError:
        print("OK  non-positive equity raises SizingError")


if __name__ == "__main__":
    test_basic_sizing_matches_hand_calculation()
    test_risk_level_multiplier_reduces_size()
    test_max_position_cap_kicks_in_on_tight_stop()
    test_zero_stop_distance_raises()
    test_missing_prices_raises()
    test_non_positive_equity_raises()
    print("\nAll sizing tests passed.")
