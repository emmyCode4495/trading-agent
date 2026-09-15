"""
Interactive Telegram bot for the Market Intelligence Agent.

UI approach: Telegram has no visual layer to skin, so "modern clean UI" here
means three concrete things instead:
  1. A persistent reply keyboard (the row of buttons pinned above the text
     field) so the five main actions never require typing a command.
  2. Inline keyboards attached to each message — buttons that live inside
     the message itself (View report, Refresh, Back to menu) — so results
     are actionable, not just read-only text dumps.
  3. Consistent card formatting: every message uses the same header/divider/
     badge style instead of each command inventing its own layout.

Report messages stay short (symbol, direction, confidence, risk, regime,
entry/invalidation/target). Full evidence text lives on the web dashboard.

Requires TELEGRAM_BOT_TOKEN in .env.
Optional: TELEGRAM_ALLOWED_CHAT_IDS=comma-separated chat ids (restrict access).
If empty, the bot responds to anyone who messages it.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

import requests

from app.config import settings

logger = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}"
DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def _allowed(chat_id: int | str) -> bool:
    """
    Access control:
      - If TELEGRAM_ALLOWED_CHAT_IDS is empty → allow everyone
      - Otherwise only listed chat IDs
      - TELEGRAM_CHAT_ID is always treated as allowed (convenience)
    """
    cid = str(chat_id).strip()

    single = (getattr(settings, "telegram_chat_id", "") or "").strip()
    if single and cid == single:
        return True

    raw = (getattr(settings, "telegram_allowed_chat_ids", "") or "").strip()
    if not raw:
        return True

    allowed = {x.strip() for x in raw.split(",") if x.strip()}
    ok = cid in allowed
    if not ok:
        logger.warning(
            "Unauthorized chat_id=%s (allowed=%s, telegram_chat_id=%s)",
            cid, allowed, single or "(empty)",
        )
    return ok


def _esc(s) -> str:
    """Escape HTML special chars for Telegram HTML parse mode."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# Low-level Telegram API calls
# ---------------------------------------------------------------------------

def _send(
    chat_id: int | str,
    text: str,
    parse_mode: str | None = "HTML",
    reply_markup: dict | None = None,
) -> bool:
    if not settings.telegram_bot_token:
        return False
    url = f"{API.format(token=settings.telegram_bot_token)}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        r = requests.post(url, json=payload, timeout=15)
        if not r.ok:
            payload.pop("parse_mode", None)
            r = requests.post(url, json=payload, timeout=15)
        return r.ok
    except requests.RequestException as e:
        logger.warning("Telegram send failed: %s", e)
        return False


def _answer_callback_query(
    callback_query_id: str,
    text: str | None = None,
    show_alert: bool = False,
) -> None:
    """Stops the button's loading spinner."""
    if not settings.telegram_bot_token or not callback_query_id:
        return
    url = f"{API.format(token=settings.telegram_bot_token)}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = show_alert
    try:
        requests.post(url, json=payload, timeout=10)
    except requests.RequestException:
        pass


def _delete_webhook() -> None:
    try:
        requests.get(
            f"{API.format(token=settings.telegram_bot_token)}/deleteWebhook",
            params={"drop_pending_updates": False},
            timeout=10,
        )
    except requests.RequestException:
        pass


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------

def _ikb(rows: list[list[tuple[str, str]]]) -> dict:
    """Inline keyboard from rows of (label, callback_data) pairs."""
    return {
        "inline_keyboard": [
            [{"text": label, "callback_data": data} for label, data in row]
            for row in rows
        ]
    }


def _ikb_for_opportunities(opps: list, refresh_data: str) -> dict:
    """Two symbol buttons per row, then refresh + menu."""
    rows: list[list[tuple[str, str]]] = []
    row: list[tuple[str, str]] = []
    for opp in opps[:10]:
        sym = str(opp.get("symbol", "?"))
        row.append((f"📄 {sym}", f"report:{sym}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([("🔄 Refresh", refresh_data), ("⬅️ Menu", "menu")])
    return _ikb(rows)


MAIN_REPLY_KB = {
    "keyboard": [
        ["🔍 Scan Markets"],
        ["📊 Top Picks", "📈 Positions"],
        ["⚙️ Status", "⚡ Execution"],
        ["❓ Help"],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
}

MENU_KB = _ikb([
    [("🔍 Scan Now", "scan"), ("📊 Top Picks", "top")],
    [("📈 Positions", "positions"), ("⚙️ Status", "status")],
    [("⚡ Execution", "execution"), ("❓ Help", "help")],
])

TEXT_ALIASES = {
    "🔍 Scan Markets": "/scan",
    "📊 Top Picks": "/top",
    "📈 Positions": "/positions",
    "⚙️ Status": "/status",
    "⚡ Execution": "/execution",
    "❓ Help": "/help",
}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _header(icon: str, title: str, subtitle: str | None = None) -> str:
    lines = [f"{icon} <b>{_esc(title)}</b>"]
    if subtitle:
        lines.append(f"<i>{_esc(subtitle)}</i>")
    lines.append(DIVIDER)
    return "\n".join(lines)


def _dir_badge(direction: str) -> str:
    d = (direction or "").upper()
    if d == "LONG":
        return "🟢 <b>LONG</b>"
    if d == "SHORT":
        return "🔴 <b>SHORT</b>"
    return f"⚪ <b>{_esc(d or 'WAIT')}</b>"


def _risk_badge(risk: str) -> str:
    r = (risk or "n/a").lower()
    return f"<code>{_esc(r)}</code>"


def _pill(on: bool) -> str:
    return "🟢 ON" if on else "⚪ OFF"


def _pnl_badge(pnl) -> str:
    try:
        v = float(pnl)
        icon = "🟢" if v >= 0 else "🔴"
        sign = "+" if v >= 0 else ""
        return f"{icon} <code>{sign}{v:.2f}%</code>"
    except (TypeError, ValueError):
        return f"<code>{_esc(pnl)}</code>"


def _risk_reward(entry, invalidation, target, direction: str | None = None) -> str | None:
    """
    Return formatted R:R string, e.g. "1:2.50", or None if levels are
    invalid / not computable. Rejects inverted geometry (e.g. LONG with
    stop above entry) so we never show "1:0.00".
    """
    try:
        e, inv, t = float(entry), float(invalidation), float(target)
    except (TypeError, ValueError):
        return None

    d = (direction or "").upper()
    if d == "LONG":
        if not (inv < e < t):
            return None
        risk, reward = e - inv, t - e
    elif d == "SHORT":
        if not (t < e < inv):
            return None
        risk, reward = inv - e, e - t
    else:
        risk, reward = abs(e - inv), abs(t - e)

    if risk <= 0 or reward <= 0:
        return None
    ratio = reward / risk
    if ratio < 0.01:
        return None
    return f"1:{ratio:.2f}"


def _fmt_opportunity(opps: list, title: str, subtitle: str = "", icon: str = "📊") -> str:
    lines = [_header(icon, title, subtitle or None)]
    for i, opp in enumerate(opps[:10], 1):
        sym = _esc(opp.get("symbol", "?"))
        direction = _dir_badge(str(opp.get("direction", "?")))
        conf = opp.get("confidence", "?")
        risk = _risk_badge(str(opp.get("risk_level", "n/a")))
        bias = _esc(opp.get("bias", ""))
        lines.append(f"<b>{i}. {sym}</b>   {direction}")
        lines.append(
            f"    conf <code>{_esc(conf)}</code>/100 · risk {risk}"
            + (f" · {bias}" if bias else "")
        )
    lines.append(DIVIDER)
    lines.append("👇 Tap a symbol below for the full report")
    return "\n".join(lines)


def _help_text() -> str:
    lines = [_header("❓", "Commands")]
    lines += [
        "🔍 /scan — run a full market scan",
        "📊 /top — latest ranked opportunities",
        "📄 /report SYMBOL — full analysis",
        "     <i>e.g. /report BTC/USDT</i>",
        "⚙️ /status — scanner &amp; config status",
        "📈 /positions — open &amp; recent positions",
        "⚡ /execution — turn auto-trading on/off",
        "❓ /help — this message",
        DIVIDER,
        "<i>Tip: the buttons below work the same as typing.</i>",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _cmd_start(chat_id: str, _args: str) -> None:
    _send(
        chat_id,
        f"{_header('🤖', 'dakChat', 'Autonomous market intelligence')}\n"
        "Ready when you are — tap a button below.",
        reply_markup=MAIN_REPLY_KB,
    )
    _send(chat_id, _help_text(), reply_markup=MENU_KB)


def _cmd_help(chat_id: str, _args: str) -> None:
    _send(chat_id, _help_text(), reply_markup=MENU_KB)


def _cmd_scan(chat_id: str, _args: str) -> None:
    _send(chat_id, "⏳ <b>Scanning markets…</b>\n<i>Typically 30–90 seconds</i>")
    try:
        from app.scanner import run_scan
        result = run_scan()
        opps = result.get("opportunities") or result.get("top") or result.get("ranked") or []
        if not opps:
            _send(
                chat_id,
                f"{_header('✅', 'Scan complete')}\nNo actionable opportunities this cycle.",
                reply_markup=_ikb([[("🔄 Scan Again", "scan")], [("⬅️ Menu", "menu")]]),
            )
            return
        discovered = result.get("markets_discovered", "?")
        screened = result.get("markets_screened", "?")
        sub = f"{discovered} discovered · {screened} screened · {len(opps)} ranked"
        _send(
            chat_id,
            _fmt_opportunity(opps, "Scan complete", sub, icon="✅"),
            reply_markup=_ikb_for_opportunities(opps, refresh_data="scan"),
        )
    except Exception as e:
        logger.exception("Telegram /scan failed")
        _send(
            chat_id,
            f"{_header('❌', 'Scan failed')}\n<code>{_esc(e)}</code>",
            reply_markup=_ikb([[("🔄 Try Again", "scan")], [("⬅️ Menu", "menu")]]),
        )


def _cmd_top(chat_id: str, _args: str) -> None:
    try:
        from app.models import ScanRun, get_session, init_db
        import json
        init_db()
        session = get_session()
        try:
            run = session.query(ScanRun).order_by(ScanRun.created_at.desc()).first()
            if not run:
                _send(
                    chat_id,
                    "No scan yet. Tap below to run one.",
                    reply_markup=_ikb([[("🔍 Scan Now", "scan")], [("⬅️ Menu", "menu")]]),
                )
                return
            opps = json.loads(run.top_opportunities_json or "[]")
            if not opps:
                _send(
                    chat_id,
                    f"{_header('📊', 'Latest opportunities', f'Scan @ {run.created_at} UTC')}\n"
                    "No opportunities.",
                    reply_markup=_ikb([[("🔄 Scan Again", "scan")], [("⬅️ Menu", "menu")]]),
                )
                return
            _send(
                chat_id,
                _fmt_opportunity(opps, "Latest opportunities", f"Scan @ {run.created_at} UTC"),
                reply_markup=_ikb_for_opportunities(opps, refresh_data="top"),
            )
        finally:
            session.close()
    except Exception as e:
        logger.exception("Telegram /top failed")
        _send(chat_id, f"❌ <code>{_esc(e)}</code>", reply_markup=_ikb([[("⬅️ Menu", "menu")]]))


def _cmd_report(chat_id: str, args: str) -> None:
    """
    Compact signal card only — no long evidence / "what changed" wall of text.
    Full analysis lives on the web dashboard.
    """
    symbol = (args or "").strip().upper()
    if not symbol:
        _send(
            chat_id,
            "Usage: <code>/report BTC/USDT</code>",
            reply_markup=_ikb([[("⬅️ Menu", "menu")]]),
        )
        return
    if "/" not in symbol:
        symbol = f"{symbol}/USDT"

    _send(chat_id, f"⏳ Analysing <b>{_esc(symbol)}</b>…")
    try:
        from app.pipeline import run_cycle
        report = run_cycle(symbol)

        direction = _dir_badge(str(report.get("direction", "?")))
        conf = report.get("confidence", "?")
        risk = _risk_badge(str(report.get("risk_level", "n/a")))
        entry = report.get("entry_price")
        inv = report.get("invalidation_price")
        target = report.get("target_price")
        bias = _esc(report.get("bias", "") or "")
        regime = _esc(report.get("market_regime", "") or "")

        # Subtitle stops at bias + market regime — no evidence dump
        subtitle_parts = [p for p in (bias, regime) if p]
        subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

        lines = [_header("📄", symbol, subtitle)]
        lines.append(f"{direction}   conf <code>{_esc(conf)}</code>/100   risk {risk}")
        lines.append(DIVIDER)

        if entry is not None:
            lines.append(f"🎯 Entry          <code>{_esc(entry)}</code>")
        if inv is not None:
            lines.append(f"🛑 Invalidation   <code>{_esc(inv)}</code>")
        if target is not None:
            lines.append(f"🏁 Target         <code>{_esc(target)}</code>")

        # Prefer decision-engine ratio; fall back to local geometry check
        engine_rr = report.get("risk_reward_ratio")
        if engine_rr is not None:
            try:
                rr = f"1:{float(engine_rr):.2f}"
            except (TypeError, ValueError):
                rr = _risk_reward(entry, inv, target, str(report.get("direction", "")))
        else:
            rr = _risk_reward(entry, inv, target, str(report.get("direction", "")))
        if rr:
            lines.append(f"📐 R:R            <code>{_esc(rr)}</code>")
        elif str(report.get("direction", "")).upper() in ("LONG", "SHORT"):
            lines.append("📐 R:R            <i>n/a (invalid levels)</i>")

        # Intentionally NO report["text"] / evidence block here.
        # Full detail is on the website dashboard.

        exe = report.get("execution") or {}
        if exe and exe.get("status") and exe.get("status") != "skipped":
            lines.append(DIVIDER)
            status_icon = {"submitted": "✅", "error": "❌"}.get(exe.get("status"), "ℹ️")
            lines.append(
                f"{status_icon} Execution: <code>{_esc(exe.get('status'))}</code>"
                + (f" — {_esc(exe.get('reason'))}" if exe.get("reason") else "")
            )

        lines.append(DIVIDER)
        lines.append("<i>Full evidence &amp; history → web dashboard</i>")

        _send(
            chat_id,
            "\n".join(lines),
            reply_markup=_ikb([
                [("🔄 Refresh", f"report:{symbol}")],
                [("⬅️ Menu", "menu")],
            ]),
        )
    except Exception as e:
        logger.exception("Telegram /report failed")
        _send(
            chat_id,
            f"{_header('❌', 'Report failed')}\n<code>{_esc(e)}</code>",
            reply_markup=_ikb([[("⬅️ Menu", "menu")]]),
        )


def _cmd_status(chat_id: str, _args: str) -> None:
    try:
        from app import scan_state
        st = scan_state.get_state() if hasattr(scan_state, "get_state") else {}
        lines = [_header("⚙️", "System status")]
        lines.append(f"Data source     <code>{_esc(settings.data_source)}</code>")
        try:
            from app.preferences import execution_status_summary
            est = execution_status_summary()
            lines.append(f"Execution master {_pill(est['master_enabled'])}")
            lines.append(f"Execution opt-in {_pill(est['user_opt_in'])}")
            lines.append(f"Will trade       {_pill(est['will_execute'])}")
        except Exception:
            lines.append(f"Execution       {_pill(settings.execution_enabled)}")
        lines.append(f"Payments        {_pill(settings.payments_enabled)}")
        lines.append(f"Scanner         {_pill(getattr(settings, 'enable_background_scanner', True))}")
        if st:
            lines.append(DIVIDER)
            lines.append(f"Last start      <code>{_esc(st.get('last_scan_started_at') or '—')}</code>")
            lines.append(f"Last finish     <code>{_esc(st.get('last_scan_finished_at') or '—')}</code>")
            lines.append(f"Phase           <code>{_esc(st.get('status') or st.get('phase') or 'idle')}</code>")
        _send(
            chat_id,
            "\n".join(lines),
            reply_markup=_ikb([[("🔄 Refresh", "status")], [("⬅️ Menu", "menu")]]),
        )
    except Exception as e:
        _send(chat_id, f"❌ <code>{_esc(e)}</code>")


def _cmd_positions(chat_id: str, _args: str) -> None:
    try:
        from app.backtest import open_positions_summary, recent_resolved_summary
        open_pos = open_positions_summary()
        recent = recent_resolved_summary(limit=8)

        lines = [_header("📈", "Open positions")]
        if not open_pos:
            lines.append("<i>None right now</i>")
        else:
            for p in open_pos[:10]:
                lines.append(
                    f"<b>{_esc(p.get('symbol'))}</b>  {_dir_badge(str(p.get('direction')))}  "
                    f"{_pnl_badge(p.get('pnl_pct', '?'))}"
                )

        lines.append("")
        lines.append("🗂 <b>Recently resolved</b>")
        lines.append(DIVIDER)
        if not recent:
            lines.append("<i>None yet</i>")
        else:
            for p in recent:
                outcome = _esc(p.get("outcome", "?"))
                lines.append(
                    f"<b>{_esc(p.get('symbol'))}</b>  <code>{outcome}</code>  "
                    f"{_pnl_badge(p.get('pnl_pct', '?'))}"
                )

        _send(
            chat_id,
            "\n".join(lines),
            reply_markup=_ikb([[("🔄 Refresh", "positions")], [("⬅️ Menu", "menu")]]),
        )
    except Exception as e:
        logger.exception("Telegram /positions failed")
        _send(chat_id, f"❌ <code>{_esc(e)}</code>")



def _cmd_execution(chat_id: str, args: str) -> None:
    """
    Show execution status and let the user opt in / out of auto-trading.

    Master switch remains EXECUTION_ENABLED in .env (server operator).
    This toggle is the user-facing preference on top of that.
    """
    from app.preferences import execution_status_summary, set_execution_opt_in

    arg = (args or "").strip().lower()
    if arg in ("on", "enable", "1", "true"):
        set_execution_opt_in(True)
    elif arg in ("off", "disable", "0", "false"):
        set_execution_opt_in(False)

    st = execution_status_summary()
    lines = [_header("⚡", "Execution")]
    lines.append(f"Master (.env)    {_pill(st['master_enabled'])}")
    lines.append(f"Your opt-in      {_pill(st['user_opt_in'])}")
    lines.append(f"Will trade       {_pill(st['will_execute'])}")
    lines.append(DIVIDER)

    if not st["master_enabled"]:
        lines.append(
            "<i>Master switch is OFF in server config.\n"
            "Opt-in alone cannot place orders until the operator enables EXECUTION_ENABLED.</i>"
        )
    elif st["user_opt_in"]:
        lines.append("<i>Auto-execution is active for qualifying signals.</i>")
    else:
        lines.append("<i>Signals only — no orders will be placed until you opt in.</i>")

    # Toggle buttons
    if st["user_opt_in"]:
        rows = [[("⏹ Turn OFF", "execution_off")], [("⬅️ Menu", "menu")]]
    else:
        rows = [[("▶️ Turn ON", "execution_on")], [("⬅️ Menu", "menu")]]

    _send(chat_id, "\n".join(lines), reply_markup=_ikb(rows))


COMMANDS: dict[str, Callable[[str, str], None]] = {
    "/start": _cmd_start,
    "/help": _cmd_help,
    "/scan": _cmd_scan,
    "/top": _cmd_top,
    "/report": _cmd_report,
    "/status": _cmd_status,
    "/positions": _cmd_positions,
    "/execution": _cmd_execution,
}

CALLBACK_COMMANDS: dict[str, Callable[[str, str], None]] = {
    "menu": _cmd_start,
    "scan": _cmd_scan,
    "top": _cmd_top,
    "positions": _cmd_positions,
    "status": _cmd_status,
    "help": _cmd_help,
    "execution": _cmd_execution,
}


# ---------------------------------------------------------------------------
# Update routing
# ---------------------------------------------------------------------------

def _handle_callback_query(cq: dict) -> None:
    cq_id = cq.get("id")
    data = cq.get("data", "")
    message = cq.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return

    if not _allowed(chat_id):
        _answer_callback_query(cq_id, "Not authorized.", show_alert=True)
        return

    _answer_callback_query(cq_id)

    if data.startswith("report:"):
        symbol = data.split(":", 1)[1]
        _cmd_report(str(chat_id), symbol)
        return

    if data == "execution_on":
        from app.preferences import set_execution_opt_in
        set_execution_opt_in(True)
        _cmd_execution(str(chat_id), "")
        return
    if data == "execution_off":
        from app.preferences import set_execution_opt_in
        set_execution_opt_in(False)
        _cmd_execution(str(chat_id), "")
        return

    handler = CALLBACK_COMMANDS.get(data)
    if handler:
        try:
            handler(str(chat_id), "")
        except Exception:
            logger.exception("Callback handler for %r failed", data)
            _send(chat_id, "⚠️ Internal error.")
    else:
        logger.warning("Unknown callback_data: %s", data)


def _handle_update(update: dict) -> None:
    if "callback_query" in update:
        _handle_callback_query(update["callback_query"])
        return

    msg = update.get("message") or update.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return
    if not _allowed(chat_id):
        _send(
            chat_id,
            f"Unauthorized (chat_id={chat_id}).\n"
            "Fix: set TELEGRAM_ALLOWED_CHAT_IDS= empty in .env, or add this chat_id, then restart the bot.",
        )
        return

    text = TEXT_ALIASES.get(text, text)

    parts = text.split(maxsplit=1)
    cmd = parts[0].split("@")[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handler = COMMANDS.get(cmd)
    if handler:
        try:
            handler(str(chat_id), args)
        except Exception:
            logger.exception("Handler %s failed", cmd)
            _send(chat_id, "⚠️ Internal error.")
    else:
        _send(
            chat_id,
            "Unrecognized command. Tap a button below or try /help",
            reply_markup=MAIN_REPLY_KB,
        )


# ---------------------------------------------------------------------------
# Long-polling loop
# ---------------------------------------------------------------------------

def poll_forever(stop_event: threading.Event | None = None) -> None:
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — bot not started")
        return

    _delete_webhook()
    offset = 0
    logger.info("Telegram bot polling started (pid=%s)", os.getpid())
    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            r = requests.get(
                f"{API.format(token=settings.telegram_bot_token)}/getUpdates",
                params={"timeout": 25, "offset": offset},
                timeout=35,
            )
            data = r.json()
            if not data.get("ok"):
                time.sleep(3)
                continue
            for upd in data.get("result", []):
                offset = max(offset, upd["update_id"] + 1)
                try:
                    _handle_update(upd)
                except Exception:
                    logger.exception("Failed to handle update")
        except requests.RequestException as e:
            logger.warning("Telegram poll error: %s", e)
            time.sleep(5)
        except Exception:
            logger.exception("Unexpected bot loop error")
            time.sleep(5)


_bot_lock_fh = None


def start_bot_background() -> threading.Thread | None:
    """
    Start the long-poll loop in a daemon thread.
    File lock prevents duplicate pollers under uvicorn --reload.
    """
    global _bot_lock_fh
    if not settings.telegram_bot_token:
        return None

    lock_path = os.path.join(os.path.dirname(__file__), "..", "..", ".telegram_bot.lock")
    lock_path = os.path.abspath(lock_path)
    try:
        _bot_lock_fh = open(lock_path, "w")
        import fcntl
        fcntl.flock(_bot_lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _bot_lock_fh.write(str(os.getpid()))
        _bot_lock_fh.flush()
    except OSError:
        logger.warning(
            "Another process already holds the Telegram bot lock — not starting a second poller."
        )
        return None
    except ImportError:
        pass

    t = threading.Thread(target=poll_forever, name="telegram-bot", daemon=True)
    t.start()
    return t
