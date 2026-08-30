"""
Tests FailoverAdapter's core behavior with lightweight fake adapters (no
HTTP involved) — this is pure control-flow logic, so real network access
isn't needed to verify it correctly.

Run with: python -m scripts.test_failover_adapter
"""
import pandas as pd

from app.data.base import DataAdapter
from app.data.failover_adapter import AllAdaptersFailedError, FailoverAdapter


class FakeAdapter(DataAdapter):
    """A fake exchange that either always fails or always returns a fixed price/frame."""

    def __init__(self, name: str, fails: bool = False, price: float = 100.0):
        self.name = name
        self.fails = fails
        self.price = price
        self.calls = 0

    def get_ohlcv(self, symbol, timeframe, limit=200):
        self.calls += 1
        if self.fails:
            raise RuntimeError(f"{self.name} is unreachable")
        return pd.DataFrame({"open": [self.price], "high": [self.price], "low": [self.price],
                              "close": [self.price], "volume": [1.0]})

    def get_latest_price(self, symbol):
        self.calls += 1
        if self.fails:
            raise RuntimeError(f"{self.name} is unreachable")
        return self.price

    def list_markets(self, quote_asset=None):
        self.calls += 1
        if self.fails:
            raise RuntimeError(f"{self.name} is unreachable")
        return [{"symbol": "BTC/USDT", "last_price": self.price}]


def test_falls_through_to_second_adapter_on_failure():
    blocked = FakeAdapter("blocked_exchange", fails=True)
    working = FakeAdapter("working_exchange", fails=False, price=250.0)
    adapter = FailoverAdapter([("blocked_exchange", blocked), ("working_exchange", working)])

    price = adapter.get_latest_price("BTC/USDT")

    assert price == 250.0
    assert blocked.calls == 1  # it was tried...
    assert working.calls == 1  # ...and failed over correctly
    print("OK  falls through to the next exchange when the first fails")


def test_remembers_last_good_adapter():
    blocked = FakeAdapter("blocked_exchange", fails=True)
    working = FakeAdapter("working_exchange", fails=False, price=250.0)
    adapter = FailoverAdapter([("blocked_exchange", blocked), ("working_exchange", working)])

    adapter.get_latest_price("BTC/USDT")
    adapter.get_latest_price("BTC/USDT")
    adapter.get_latest_price("BTC/USDT")

    # After the first failure, subsequent calls for the SAME cache key should
    # prefer "working_exchange" directly rather than re-trying "blocked_exchange"
    # every single time.
    assert blocked.calls == 1, "should stop re-trying the known-bad exchange for this key"
    assert working.calls == 3
    print("OK  remembers the last-good exchange per call-key instead of re-trying a dead one every time")


def test_all_fail_raises_with_combined_message():
    a = FakeAdapter("exchange_a", fails=True)
    b = FakeAdapter("exchange_b", fails=True)
    adapter = FailoverAdapter([("exchange_a", a), ("exchange_b", b)])

    try:
        adapter.get_latest_price("BTC/USDT")
        raise AssertionError("Expected AllAdaptersFailedError")
    except AllAdaptersFailedError as e:
        assert "exchange_a" in str(e)
        assert "exchange_b" in str(e)
    print("OK  raises a clear error naming every exchange that failed, when all fail")


def test_different_symbols_are_independent():
    """A failure resolving one symbol shouldn't affect the preferred exchange for a different symbol."""
    primary = FakeAdapter("primary", fails=False, price=100.0)
    adapter = FailoverAdapter([("primary", primary)])

    adapter.get_latest_price("BTC/USDT")
    adapter.get_latest_price("ETH/USDT")

    assert primary.calls == 2
    print("OK  different symbols/timeframes are tracked as independent cache keys")


def test_list_markets_and_ohlcv_also_fail_over():
    blocked = FakeAdapter("blocked", fails=True)
    working = FakeAdapter("working", fails=False, price=42.0)
    adapter = FailoverAdapter([("blocked", blocked), ("working", working)])

    markets = adapter.list_markets(quote_asset="USDT")
    df = adapter.get_ohlcv("BTC/USDT", "1h", limit=10)

    assert markets[0]["last_price"] == 42.0
    assert df.iloc[0]["close"] == 42.0
    print("OK  list_markets and get_ohlcv fail over the same way get_latest_price does")


if __name__ == "__main__":
    test_falls_through_to_second_adapter_on_failure()
    test_remembers_last_good_adapter()
    test_all_fail_raises_with_combined_message()
    test_different_symbols_are_independent()
    test_list_markets_and_ohlcv_also_fail_over()
    print("\nAll FailoverAdapter tests passed.")
