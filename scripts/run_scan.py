"""
Quick manual test of the AUTONOMOUS SCANNER: discovers every tradable
{SCAN_QUOTE_ASSET}-quoted pair on the exchange, screens by 24h liquidity,
runs the full 5-agent pipeline on the survivors, and prints the ranked
opportunities. No scheduler, no server, no fixed watchlist.

Usage: python -m scripts.run_scan
"""
from app.scanner import run_scan

if __name__ == "__main__":
    result = run_scan()

    if result["error"]:
        print(f"Scan failed: {result['error']}")
        raise SystemExit(1)

    print(
        f"Discovered {result['markets_discovered']} {result['quote_asset']}-quoted markets, "
        f"{result['markets_screened']} passed the liquidity screen, "
        f"{len(result['symbols_analyzed'])} analyzed.\n"
    )

    if not result["opportunities"]:
        print("No actionable opportunities this cycle (every screened symbol came back WAIT).")
    else:
        for report in result["all_reports"]:
            if report["direction"] == "WAIT":
                continue
            print(report["text"])
            print("-" * 50)
