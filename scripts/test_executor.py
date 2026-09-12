"""
Tests app.execution.executor's gating logic by monkeypatching
app.execution.hyperliquid_adapter — no real network/SDK calls happen. This
is deliberately testing the *decision* of whether/what to send, which is the
safety-critical part; the actual SDK call shapes were verified separately
against the installed library (see the module docstring in
hyperliquid_adapter.py).

Uses an in-memory SQLite DB so this doesn't touch trading_agent.db.

Run with: python -m scripts.test_executor
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.config import settings  # noqa: E402
from app.execution import executor, hyperliquid_adapter as hl  # noqa: E402
from app.models import init_db  # noqa: E402

init_db()


def _report(direction="LONG", confidence=80, symbol="BTC/USDT", risk_level="low"):
    return {
        "symbol": symbol, "direction": direction, "confidence": confidence,
        "entry_price": 100.0, "invalidation_price": 95.0, "target_price": 115.0,
        "risk_level": risk_level, "recommendation_id": 1,
    }


def test_skips_when_execution_disabled():
    settings.execution_enabled = False
    result = executor.maybe_execute(_report())
    assert result["executed"] is False
    assert "EXECUTION_ENABLED" in result["reason"]
    print("OK  skips entirely when EXECUTION_ENABLED=false (the default)")


def test_skips_wait_direction():
    settings.execution_enabled = True
    result = executor.maybe_execute(_report(direction="WAIT"))
    assert result["executed"] is False
    assert "direction=WAIT" in result["reason"]
    print("OK  skips WAIT calls (including anything the Risk agent already vetoed upstream)")


def test_skips_below_confidence_threshold():
    settings.execution_enabled = True
    settings.min_confidence_to_act = 60
    result = executor.maybe_execute(_report(confidence=40))
    assert result["executed"] is False
    assert "confidence" in result["reason"]
    print("OK  skips a LONG/SHORT call whose confidence is below MIN_CONFIDENCE_TO_ACT")


def test_executes_when_gates_pass(monkeypatch):
    settings.execution_enabled = True
    settings.min_confidence_to_act = 60

    monkeypatch.setattr(hl, "get_current_position", lambda symbol: None)
    monkeypatch.setattr(hl, "get_account_equity", lambda: 10_000.0)
    monkeypatch.setattr(hl, "get_mid_price", lambda symbol: 100.0)
    monkeypatch.setattr(hl, "open_market_position", lambda symbol, is_buy, size: {"status": "ok", "response": {}})

    result = executor.maybe_execute(_report(confidence=80))
    assert result["executed"] is True
    assert result["status"] == "submitted"
    print("OK  executes and records status=submitted once all gates pass")


def test_flips_opposite_position_before_opening(monkeypatch):
    settings.execution_enabled = True
    calls = {"closed": False, "opened": False}

    monkeypatch.setattr(hl, "get_current_position", lambda symbol: {"szi": "-1.5"})  # existing SHORT
    monkeypatch.setattr(hl, "close_position", lambda symbol: calls.__setitem__("closed", True) or {"status": "ok"})
    monkeypatch.setattr(hl, "get_account_equity", lambda: 10_000.0)
    monkeypatch.setattr(hl, "get_mid_price", lambda symbol: 100.0)

    def fake_open(symbol, is_buy, size):
        calls["opened"] = True
        assert is_buy is True  # the new report below is LONG, opposite of the existing short
        return {"status": "ok"}
    monkeypatch.setattr(hl, "open_market_position", fake_open)

    result = executor.maybe_execute(_report(direction="LONG", confidence=80))
    assert calls["closed"] is True and calls["opened"] is True
    assert result["executed"] is True
    print("OK  closes an opposite-direction position before opening the new one (flip, not stack)")


def test_skips_same_direction_pyramid(monkeypatch):
    settings.execution_enabled = True
    monkeypatch.setattr(hl, "get_current_position", lambda symbol: {"szi": "1.5"})  # existing LONG

    result = executor.maybe_execute(_report(direction="LONG", confidence=80))
    assert result["executed"] is False
    assert "not pyramiding" in result["reason"]
    print("OK  skips adding to an already-open same-direction position instead of pyramiding")


def test_records_error_status_on_adapter_failure(monkeypatch):
    settings.execution_enabled = True

    def raise_error(symbol):
        raise hl.HyperliquidError("simulated Hyperliquid outage")
    monkeypatch.setattr(hl, "get_current_position", raise_error)

    result = executor.maybe_execute(_report(confidence=80))
    assert result["executed"] is False
    assert result["status"] == "error"
    assert "simulated Hyperliquid outage" in result["reason"]
    print("OK  a Hyperliquid error is recorded as status=error, not raised uncaught")


class _FakeMonkeypatch:
    """Tiny standalone monkeypatch, so this script needs no pytest dependency."""

    def __init__(self):
        self._originals = []

    def setattr(self, obj, name, value):
        self._originals.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, value in reversed(self._originals):
            setattr(obj, name, value)


if __name__ == "__main__":
    test_skips_when_execution_disabled()
    test_skips_wait_direction()
    test_skips_below_confidence_threshold()

    for fn in (test_executes_when_gates_pass, test_flips_opposite_position_before_opening,
               test_skips_same_direction_pyramid, test_records_error_status_on_adapter_failure):
        mp = _FakeMonkeypatch()
        try:
            fn(mp)
        finally:
            mp.undo()

    print("\nAll executor tests passed.")
