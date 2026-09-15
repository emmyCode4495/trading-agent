"""
Run the interactive Telegram bot as a standalone process
(without the web dashboard).

Usage:
    python -m scripts.run_telegram_bot

Requires TELEGRAM_BOT_TOKEN in .env.
"""
import logging
import signal
import threading

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")

from app.config import settings
from app.notifiers.telegram_bot import poll_forever


def main():
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set in .env")

    stop = threading.Event()

    def _stop(*_):
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    print("Telegram bot running. Press Ctrl+C to stop.")
    print("Commands: /start /scan /top /report /status /positions /help")
    poll_forever(stop_event=stop)
    print("Stopped.")


if __name__ == "__main__":
    main()
