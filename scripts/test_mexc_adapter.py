"""
Verifies MexcAdapter's parsing logic against response shapes copied from
MEXC's own v3 API docs — this sandbox can't reach api.mexc.com, so this is
the offline substitute for real network testing.

Run with: python -m scripts.test_mexc_adapter
"""
from unittest.mock import MagicMock, patch

from app.data.mexc_adapter import MexcAdapter, MexcError, _to_mexc_symbol

# Real shape of a MEXC /api/v3/klines row (Binance-compatible: open_time,
# open, high, low, close, volume, close_time, ...).
SAMPLE_KLINES = [
    [1699999200000, "43250.10", "43310.55", "43180.00", "43290.75", "125.432", 1699999259999],
    [1699999260000, "43290.75", "43400.00", "43260.20", "43385.60", "98.210", 1699999319999],
]

SAMPLE_TICKER = {"symbol": "BTCUSDT", "price": "43391.20"}

SAMPLE_EXCHANGE_INFO = {
    "symbols": [
        {"symbol": "BTCUSDT", "baseAsset": "BTC", "quoteAsset": "USDT", "status": "ENABLED", "isSpotTradingAllowed": True},
        {"symbol": "ETHUSDT", "baseAsset": "ETH", "quoteAsset": "USDT", "status": "ENABLED", "isSpotTradingAllowed": True},
        {"symbol": "XYZUSDT", "baseAsset": "XYZ", "quoteAsset": "USDT", "status": "DISABLED", "isSpotTradingAllowed": True},
        {"symbol": "BTCUPUSDT", "baseAsset": "BTCUP", "quoteAsset": "USDT", "status": "ENABLED", "isSpotTradingAllowed": True},
    ]
}

SAMPLE_TICKER_24H = [
    {"symbol": "BTCUSDT", "lastPrice": "43391.20", "quoteVolume": "812345678.90", "priceChangePercent": "2.31"},
    {"symbol": "ETHUSDT", "lastPrice": "3050.10", "quoteVolume": "312345678.90", "priceChangePercent": "-1.14"},
]


def test_symbol_conversion():
    assert _to_mexc_symbol("BTC/USDT") == "BTCUSDT"
    assert _to_mexc_symbol("btc-usdt") == "BTCUSDT"
    print("OK  _to_mexc_symbol")


def test_1h_maps_to_60m():
    """MEXC has no native '1h' interval — this is the one real gotcha in their API vs Binance's."""
    adapter = MexcAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = SAMPLE_KLINES

    with patch.object(adapter.session, "get", return_value=mock_resp) as mock_get:
        adapter.get_ohlcv("BTC/USDT", "1h", limit=2)

    assert mock_get.call_args.kwargs["params"]["interval"] == "60m"
    print("OK  '1h' correctly maps to MEXC's '60m' interval, not a native '1h'")


def test_get_ohlcv_parses_klines():
    adapter = MexcAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = SAMPLE_KLINES

    with patch.object(adapter.session, "get", return_value=mock_resp):
        df = adapter.get_ohlcv("BTC/USDT", "4h", limit=2)

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert df.iloc[0]["open"] == 43250.10
    assert df.iloc[-1]["close"] == 43385.60
    print("OK  get_ohlcv parses MEXC's Binance-compatible kline shape")


def test_get_latest_price():
    adapter = MexcAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = SAMPLE_TICKER

    with patch.object(adapter.session, "get", return_value=mock_resp):
        price = adapter.get_latest_price("BTC/USDT")

    assert price == 43391.20
    print("OK  get_latest_price parses ticker response")


def test_list_markets_filters_disabled_and_leveraged():
    adapter = MexcAdapter()

    def fake_get(url, params=None, timeout=None):
        resp = MagicMock(ok=True, status_code=200)
        if "exchangeInfo" in url:
            resp.json.return_value = SAMPLE_EXCHANGE_INFO
        elif "ticker/24hr" in url:
            resp.json.return_value = SAMPLE_TICKER_24H
        return resp

    with patch.object(adapter.session, "get", side_effect=fake_get):
        markets = adapter.list_markets(quote_asset="USDT")

    symbols = {m["symbol"] for m in markets}
    assert "BTC/USDT" in symbols
    assert "ETH/USDT" in symbols
    assert "XYZ/USDT" not in symbols, "DISABLED status should be screened out"
    assert "BTCUP/USDT" not in symbols, "leveraged token should be screened out"
    print("OK  list_markets screens DISABLED symbols and leveraged tokens")


def test_rate_limit_raises():
    adapter = MexcAdapter()
    mock_resp = MagicMock(ok=False, status_code=429, text="rate limited")

    with patch.object(adapter.session, "get", return_value=mock_resp):
        try:
            adapter.get_latest_price("BTC/USDT")
            raise AssertionError("Expected MexcError to be raised")
        except MexcError as e:
            assert "rate limit" in str(e).lower()
    print("OK  429 responses raise MexcError with a clear message")


def test_full_pipeline_with_mocked_mexc():
    """Same integration check as the Binance/Bybit tests: run the real agents
    against MexcAdapter with mocked HTTP, proving it's a drop-in DataAdapter."""
    import numpy as np
    from app.agents import momentum, risk, structure, trend

    rng = np.random.default_rng(17)
    n = 120
    base = 43000
    closes = base * np.exp(np.cumsum(rng.normal(0.0002, 0.004, n)))
    rows = []
    t0 = 1699999200000
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        rows.append([
            t0 + i * 3600_000, f"{o:.2f}", f"{max(o, c) * 1.001:.2f}", f"{min(o, c) * 0.999:.2f}",
            f"{c:.2f}", f"{rng.uniform(50, 150):.2f}", t0 + i * 3600_000 + 3599999,
        ])

    adapter = MexcAdapter()
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
    print("OK  full agent pipeline runs against MexcAdapter with no code changes")


if __name__ == "__main__":
    test_symbol_conversion()
    test_1h_maps_to_60m()
    test_get_ohlcv_parses_klines()
    test_get_latest_price()
    test_list_markets_filters_disabled_and_leveraged()
    test_rate_limit_raises()
    test_full_pipeline_with_mocked_mexc()
    print("\nAll MexcAdapter tests passed.")
