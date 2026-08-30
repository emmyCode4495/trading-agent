"""
Minimal Telegram notifier. Create a bot via @BotFather, get its token, and
get your chat_id (message the bot once, then hit
https://api.telegram.org/bot<TOKEN>/getUpdates to find it). Put both in .env.

Uses plain requests instead of a Telegram SDK to keep the dependency list
small — swap for python-telegram-bot if you want richer formatting/buttons.
"""
import requests

from app.config import settings


def send_report(text: str) -> bool:
    return _send(text)


def send_scan_summary(opportunities: list[dict]) -> bool:
    """Formats the scanner's ranked opportunity list, not a single symbol's report."""
    if not opportunities:
        return _send("Scan complete — no actionable opportunities this cycle.")

    lines = ["Scan results — top opportunities:"]
    for i, opp in enumerate(opportunities, 1):
        lines.append(
            f"{i}. {opp['symbol']} — {opp['direction']} ({opp['bias']}), "
            f"confidence {opp['confidence']}/100, risk {opp['risk_level']}"
        )
    return _send("\n".join(lines))


def _send(text: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": settings.telegram_chat_id,
            "text": f"```\n{text}\n```",
            "parse_mode": "MarkdownV2" if False else None,  # keep plain to avoid MarkdownV2 escaping headaches
        }, timeout=10)
        return resp.ok
    except requests.RequestException:
        return False
