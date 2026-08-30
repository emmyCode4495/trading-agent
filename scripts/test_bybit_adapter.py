"""
Verifies BybitAdapter's parsing logic against response shapes copied from
Bybit's own v5 API docs — this sandbox can't reach api.bybit.com, so this is
the offline substitute for real network testing.

Run with: python -m scripts.test_bybit_adapter
"""
from unittest.mock import MagicMock, patch

from app.data.bybit_adapter import BybitAdapter, BybitError, _to_bybit_symbol

# Real shape of a Bybit /v5/market/kline response. IMPORTANT: Bybit returns
# klines NEWEST-FIRST (descending) — the opposite order of Binance/MEXC. The
# adapter must reverse this, and this test specifically checks that it does.
SAMPLE_KLINE_RESPONSE = {
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "symbol": "BTCUSDT",
        "category": "spot",
        "list": [
            # newest bar first, per Bybit's actual ordering
            ["1699999260000", "43290.7", "43400.0", "43260.2", "43385.6", "98.21", "4256789.00"],
            ["1699999200000", "43250.1", "43310.5", "43180.0", "43290.7", "125.43", "5428193.12"],
        ],
    },
}

SAMPLE_TICKER_RESPONSE = {
    "retCode": 0,
    "retMsg": "OK",
    "result": {"category": "spot", "list": [{"symbol": "BTCUSDT", "lastPrice": "43391.20"}]},
}

SAMPLE_ALL_TICKERS_RESPONSE = {
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "category": "spot",
        "list": [
            {"symbol": "BTCUSDT", "lastPrice": "43391.20", "turnover24h": "812345678.90", "price24hPcnt": "0.0231"},
            {"symbol": "ETHUSDT", "lastPrice": "3050.10", "turnover24h": "312345678.90", "price24hPcnt": "-0.0114"},
        ],
    },
}

SAMPLE_INSTRUMENTS_RESPONSE = {
    "retCode": 0,
    "retMsg": "OK",
    "result": {
        "category": "spot",
        "list": [
            {"symbol": "BTCUSDT", "baseCoin": "BTC", "quoteCoin": "USDT", "status": "Trading"},
            {"symbol": "ETHUSDT", "baseCoin": "ETH", "quoteCoin": "USDT", "status": "Trading"},
            {"symbol": "BTC3LUSDT", "baseCoin": "BTC3L", "quoteCoin": "USDT", "status": "Trading"},  # leveraged token, should be screened out
        ],
    },
}

SAMPLE_ERROR_RESPONSE = {"retCode": 10001, "retMsg": "params error: symbol invalid", "result": {}}


def test_symbol_conversion():
    assert _to_bybit_symbol("BTC/USDT") == "BTCUSDT"
    assert _to_bybit_symbol("btc-usdt") == "BTCUSDT"
    print("OK  _to_bybit_symbol")


def test_get_ohlcv_reverses_descending_order():
    adapter = BybitAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = SAMPLE_KLINE_RESPONSE

    with patch.object(adapter.session, "get", return_value=mock_resp) as mock_get:
        df = adapter.get_ohlcv("BTC/USDT", "1h", limit=2)

    assert mock_get.call_args.kwargs["params"]["symbol"] == "BTCUSDT"
    assert mock_get.call_args.kwargs["params"]["interval"] == "60"
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    # The EARLIER bar (43250.1 open) must come FIRST after reversal, even
    # though Bybit sent it second (newest-first).
    assert df.iloc[0]["open"] == 43250.1
    assert df.iloc[-1]["close"] == 43385.6
    assert df.index[0] < df.index[1]  # chronological order confirmed
    print("OK  get_ohlcv reverses Bybit's newest-first kline order to chronological")


def test_get_latest_price():
    adapter = BybitAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = SAMPLE_TICKER_RESPONSE

    with patch.object(adapter.session, "get", return_value=mock_resp):
        price = adapter.get_latest_price("BTC/USDT")

    assert price == 43391.20
    print("OK  get_latest_price parses ticker response")


def test_list_markets_filters_leveraged_tokens_and_converts_pct():
    adapter = BybitAdapter()

    def fake_get(url, params=None, timeout=None):
        resp = MagicMock(ok=True, status_code=200)
        if "instruments-info" in url:
            resp.json.return_value = SAMPLE_INSTRUMENTS_RESPONSE
        elif "tickers" in url:
            resp.json.return_value = SAMPLE_ALL_TICKERS_RESPONSE
        return resp

    with patch.object(adapter.session, "get", side_effect=fake_get):
        markets = adapter.list_markets(quote_asset="USDT")

    symbols = {m["symbol"] for m in markets}
    assert "BTC/USDT" in symbols
    assert "ETH/USDT" in symbols
    assert "BTC3L/USDT" not in symbols, "leveraged token should be screened out"

    btc = next(m for m in markets if m["symbol"] == "BTC/USDT")
    # price24hPcnt 0.0231 (a fraction) must become 2.31 (a percent)
    assert abs(btc["price_change_pct_24h"] - 2.31) < 1e-6
    assert btc["quote_volume_24h"] == 812345678.90
    print("OK  list_markets screens leveraged tokens and converts price24hPcnt fraction -> percent")


def test_logical_error_raises():
    """Bybit returns HTTP 200 even for bad requests — retCode != 0 is the real error signal."""
    adapter = BybitAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = SAMPLE_ERROR_RESPONSE

    with patch.object(adapter.session, "get", return_value=mock_resp):
        try:
            adapter.get_latest_price("FAKE/PAIR")
            raise AssertionError("Expected BybitError to be raised")
        except BybitError as e:
            assert "10001" in str(e)
    print("OK  non-zero retCode (HTTP 200 body) raises BybitError")


def test_full_pipeline_with_mocked_bybit():
    """Same integration check as the Binance test: run the real agents against
    BybitAdapter with mocked HTTP, proving it's a drop-in DataAdapter."""
    import numpy as np
    from app.agents import momentum, risk, structure, trend

    rng = np.random.default_rng(13)
    n = 120
    base = 43000
    closes = base * np.exp(np.cumsum(rng.normal(0.0002, 0.004, n)))
    rows = []
    t0 = 1699999200000
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        rows.append([
            str(t0 + i * 3600_000), f"{o:.2f}", f"{max(o, c) * 1.001:.2f}", f"{min(o, c) * 0.999:.2f}",
            f"{c:.2f}", f"{rng.uniform(50, 150):.2f}", "0",
        ])
    rows.reverse()  # Bybit's real newest-first order

    payload = {"retCode": 0, "retMsg": "OK", "result": {"symbol": "BTCUSDT", "category": "spot", "list": rows}}

    adapter = BybitAdapter()
    mock_resp = MagicMock(ok=True, status_code=200)
    mock_resp.json.return_value = payload

    with patch.object(adapter.session, "get", return_value=mock_resp):
        trend_out = trend.run(adapter, "BTC/USDT")
        momentum_out = momentum.run(adapter, "BTC/USDT")
        structure_out = structure.run(adapter, "BTC/USDT")
        risk_out = risk.run(adapter, "BTC/USDT")

    assert trend_out["agent"] == "trend"
    assert momentum_out["agent"] == "momentum"
    assert structure_out["agent"] == "structure"
    assert risk_out["agent"] == "risk"
    print("OK  full agent pipeline runs against BybitAdapter with no code changes")


if __name__ == "__main__":
    test_symbol_conversion()
    test_get_ohlcv_reverses_descending_order()
    test_get_latest_price()
    test_list_markets_filters_leveraged_tokens_and_converts_pct()
    test_logical_error_raises()
    test_full_pipeline_with_mocked_bybit()
    print("\nAll BybitAdapter tests passed.")
