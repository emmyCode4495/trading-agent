"""
Quick manual test of the MANUAL WATCHLIST path: runs one full cycle for
every symbol in SYMBOLS (.env) and prints the formatted report. No
scheduler, no server, just the pipeline for a symbol or two you already
know you want to check.

For the autonomous scanner (discover -> screen -> analyze -> rank across
the whole exchange), use `python -m scripts.run_scan` instead.

Usage: python -m scripts.run_once
"""
from app.pipeline import run_all_symbols

if __name__ == "__main__":
    for report in run_all_symbols():
        print(report["text"])
        print("-" * 50)
