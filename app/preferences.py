"""
Runtime preferences stored in the DB so operators can toggle features
(e.g. auto-execution) from Telegram without restarting or editing .env.

Master switches in .env still win:
  EXECUTION_ENABLED=false  → execution never runs, regardless of preference.
  EXECUTION_ENABLED=true   → preference decides whether to actually trade.
"""
from __future__ import annotations

from datetime import datetime

from app.models import AppSetting, get_session, init_db

# Keys
EXECUTION_OPT_IN = "execution_opt_in"  # "true" | "false"


def _get(key: str, default: str = "") -> str:
    init_db()
    session = get_session()
    try:
        row = session.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row else default
    finally:
        session.close()


def _set(key: str, value: str) -> None:
    init_db()
    session = get_session()
    try:
        row = session.query(AppSetting).filter(AppSetting.key == key).first()
        if row is None:
            row = AppSetting(key=key, value=value, updated_at=datetime.utcnow())
            session.add(row)
        else:
            row.value = value
            row.updated_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()


def is_execution_opted_in() -> bool:
    """User/runtime preference. Default: off (safe)."""
    return _get(EXECUTION_OPT_IN, "false").lower() == "true"


def set_execution_opt_in(enabled: bool) -> bool:
    _set(EXECUTION_OPT_IN, "true" if enabled else "false")
    return enabled


def execution_status_summary() -> dict:
    """For /status and the execution toggle UI."""
    from app.config import settings
    opted = is_execution_opted_in()
    master = bool(settings.execution_enabled)
    return {
        "master_enabled": master,          # EXECUTION_ENABLED in .env
        "user_opt_in": opted,              # runtime preference
        "will_execute": master and opted,  # effective
    }
