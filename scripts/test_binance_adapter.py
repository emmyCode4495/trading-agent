"""
Verifies BinanceAdapter's parsing logic against response shapes copied from
Binance's own API docs — without needing real network access (this sandbox
can't reach api.binance.com, so this is the offline substitute for it).

Run with: python -m scripts.test_binance_adapter
"""
from unittest.mock import MagicMock, patch

from app.data.binance_adapter import BinanceAdapter, _to_binance_symbol

# Real shape of a Binance /api/v3/klines row, per their docs:
# [ open_time, open, high, low, close, volume, close_time, quote_asset_volume,
#   number_of_trades, taker_buy_base_vol, taker_buy_quote_vol, ignore ]
SAMPLE_KLINES = [
    [1699999200000, "43250.10", "43310.55", "43180.00", "43290.75", "125.432",
     1699999259999, "5428193.12", 4821, "62.5", "2705000.0", "0"],
    [1699999260000, "43290.75", "43400.00", "43260.20", "43385.60", "98.210",
     1699999319999, "4256789.00", 3902, "50.1", "2170000.0", "0"],
]

SAMPLE_TICKER = {"symbol": "BTCUSDT", "price": "43391.20"}


def test_symbol_conversion():
    assert _to_binance_symbol("BTC/USDT") == "BTCUSDT"
    assert _to_binance_symbol("btc-usdt") == "BTCUSDT"
    assert _to_binance_symbol("ETHUSDT") == "ETHUSDT"
    print("OK  _to_binance_symbol")


def test_get_ohlcv_parses_klines():
    adapter = BinanceAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = SAMPLE_KLINES

    with patch.object(adapter.session, "get", return_value=mock_resp) as mock_get:
        df = adapter.get_ohlcv("BTC/USDT", "1h", limit=2)

    assert mock_get.call_args.kwargs["params"]["symbol"] == "BTCUSDT"
    assert mock_get.call_args.kwargs["params"]["interval"] == "1h"
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df.iloc[0]["open"] == 43250.10
    assert df.iloc[-1]["close"] == 43385.60
    print("OK  get_ohlcv parses real Binance kline shape into the expected DataFrame")


def test_get_ohlcv_uses_cache():
    adapter = BinanceAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = SAMPLE_KLINES

    with patch.object(adapter.session, "get", return_value=mock_resp) as mock_get:
        adapter.get_ohlcv("BTC/USDT", "1h", limit=2)
        adapter.get_ohlcv("BTC/USDT", "1h", limit=2)  # should hit cache, not the network again

    assert mock_get.call_count == 1
    print("OK  get_ohlcv caches within TTL to avoid redundant calls")


def test_get_latest_price():
    adapter = BinanceAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = SAMPLE_TICKER

    with patch.object(adapter.session, "get", return_value=mock_resp):
        price = adapter.get_latest_price("BTC/USDT")

    assert price == 43391.20
    print("OK  get_latest_price parses ticker response")


def test_rate_limit_raises():
    from app.data.binance_adapter import BinanceError

    adapter = BinanceAdapter()
    mock_resp = MagicMock(ok=False, status_code=429, text="rate limited")

    with patch.object(adapter.session, "get", return_value=mock_resp):
        try:
            adapter.get_latest_price("BTC/USDT")
            raise AssertionError("Expected BinanceError to be raised")
        except BinanceError as e:
            assert "rate limit" in str(e).lower()
    print("OK  429 responses raise BinanceError with a clear message")


def test_full_pipeline_with_mocked_binance():
    """
    The real integration check: point the whole agent pipeline at
    BinanceAdapter with mocked HTTP, and confirm trend/momentum/structure/
    risk agents (which only know the DataAdapter interface) run without
    modification against it — proving the adapter is a drop-in swap for
    MockAdapter.
    """
    import numpy as np
    from app.agents import momentum, risk, structure, trend

    # Build a longer synthetic-but-realistic kline series (120 bars) so the
    # indicator windows (EMA26, RSI14, rolling 20) have enough data.
    rng = np.random.default_rng(7)
    n = 120
    base = 43000
    closes = base * np.exp(np.cumsum(rng.normal(0.0003, 0.004, n)))
    rows = []
    t0 = 1699999200000
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        rows.append([
            t0 + i * 3600_000, f"{o:.2f}", f"{max(o, c) * 1.001:.2f}", f"{min(o, c) * 0.999:.2f}",
            f"{c:.2f}", f"{rng.uniform(50, 150):.2f}", t0 + i * 3600_000 + 3599999,
            "0", 0, "0", "0", "0",
        ])

    adapter = BinanceAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = rows

    with patch.object(adapter.session, "get", return_value=mock_resp):
        trend_out = trend.run(adapter, "BTC/USDT")
        momentum_out = momentum.run(adapter, "BTC/USDT")
        structure_out = structure.run(adapter, "BTC/USDT")
        risk_out = risk.run(adapter, "BTC/USDT")

    assert trend_out["agent"] == "trend"
    assert momentum_out["agent"] == "momentum"
    assert structure_out["agent"] == "structure"
    assert risk_out["agent"] == "risk"
    print("OK  full agent pipeline runs against BinanceAdapter with no code changes")


if __name__ == "__main__":
    test_symbol_conversion()
    test_get_ohlcv_parses_klines()
    test_get_ohlcv_uses_cache()
    test_get_latest_price()
    test_rate_limit_raises()
    test_full_pipeline_with_mocked_binance()
    print("\nAll BinanceAdapter tests passed.")
