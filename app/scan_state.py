"""
Simple in-memory live-scanner status, shared between the background scan
loop (running inside the same process as the FastAPI app) and GET
/api/status, which the dashboard polls to show a live "● LIVE" indicator,
last-scan time, and countdown to the next scan.

Deliberately just process memory, not a DB table — this is UI/status only
and doesn't need to survive a restart. This assumes the default single-
process deployment (`uvicorn app.api:app`). If you scale to multiple worker
processes, move this to Redis or similar so every worker reports the same
state.
"""
import threading
from datetime import datetime

_lock = threading.Lock()
_state = {
    "scanner_running": False,        # is the background loop active at all
    "is_scanning": False,            # a scan is actively in progress right now
    "last_scan_started_at": None,
    "last_scan_finished_at": None,
    "next_scan_at": None,
    "last_position_check_at": None,
    "scan_interval_minutes": None,
    "position_check_interval_minutes": None,
}


def set_scanner_running(running: bool, scan_interval_minutes=None, position_check_interval_minutes=None):
    with _lock:
        _state["scanner_running"] = running
        if scan_interval_minutes is not None:
            _state["scan_interval_minutes"] = scan_interval_minutes
        if position_check_interval_minutes is not None:
            _state["position_check_interval_minutes"] = position_check_interval_minutes


def mark_scan_started():
    with _lock:
        _state["is_scanning"] = True
        _state["last_scan_started_at"] = datetime.utcnow().isoformat()


def mark_scan_finished(next_scan_at=None):
    with _lock:
        _state["is_scanning"] = False
        _state["last_scan_finished_at"] = datetime.utcnow().isoformat()
        if next_scan_at is not None:
            _state["next_scan_at"] = next_scan_at.isoformat()


def mark_position_check():
    with _lock:
        _state["last_position_check_at"] = datetime.utcnow().isoformat()


def get_state() -> dict:
    with _lock:
        return dict(_state)
