"""
refresh_portfolio.py
====================
One-command portfolio data refresh.

Run this on your local Windows machine (not in the Cowork sandbox):
    python scripts/refresh_portfolio.py

What it does:
1. Reads your portfolio_snapshot.csv
2. Fetches current price, financials, and company info from yfinance
3. Saves normalized data to data/processed/portfolio_metrics.json
4. Updates portfolio_snapshot.csv with current prices and company info
5. Prints a portfolio summary

Options:
    --force-refresh     Ignore cache, re-fetch all data from yfinance
    --ticker TICKER     Refresh only a single ticker
    --dry-run           Fetch and display but do not write files
    --no-financials     Skip financial statements (faster, price data only)
"""

import sys
import os
import argparse
import json
from pathlib import Path
from datetime import datetime

# Make project root importable
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from data.ingestion.fetcher import fetch_portfolio, fetch_ticker, fetch_status_report, KNOWN_ETFS
from data.ingestion.normalizer import normalize, normalize_portfolio
from data.ingestion.portfolio_updater import (
    read_portfolio_csv, write_portfolio_csv, enrich_portfolio,
    portfolio_summary, save_processed_metrics, load_processed_metrics
)

# ---------------------------------------------------------------------------
# Sector enrichment from yfinance info
# yfinance provides sector in .info but our CompanyFinancialMetrics doesn't
# store it natively yet (Phase 3 will formalize this). We attach it as a
# temporary attribute here.
# ---------------------------------------------------------------------------

SECTOR_OVERRIDES = {
    # ETFs and funds don't have a sector — classify as such
    "CGL.C.TO": "Commodities (Gold ETF)",
    "QGOLDHALF.NS": "Commodities (Gold ETF)",
    "HDFCMFGETF.NS": "Commodities (Gold ETF)",
    # Add overrides here if yfinance misclassifies anything
}

GEOGRAPHY_OVERRIDES = {
    # Indian stocks via NSE
    "ITC.NS": "India",
    "TATASTEEL.NS": "India",
    "QGOLDHALF.NS": "India",
    "HDFCMFGETF.NS": "India",
}


def _attach_yf_sector(metrics_map, fetch_results):
    """Attach yfinance sector string to metrics objects for portfolio_updater."""
    for ticker, data in fetch_results.items():
        m = metrics_map.get(ticker)
        if not m:
            continue
        info = data.get("info", {})
        sector = SECTOR_OVERRIDES.get(ticker) or info.get("sector") or info.get("quoteType", "Unknown")
        m._yf_sector = sector


def _print_summary(rows, metrics_map, fetch_results):
    print("\n" + "=" * 65)
    print("PORTFOLIO REFRESH SUMMARY")
    print("=" * 65)

    # Status
    status = fetch_status_report(fetch_results)
    print(f"  Tickers processed:   {status['total']}")
    print(f"  Info fetch success:  {status['info_success']}/{status['total']}")
    print(f"  Financials success:  {status['financials_success']}/{status['total']}")
    if status["failures"]:
        print(f"\n  Fetch issues:")
        for ticker, types in status["failures"].items():
            print(f"    {ticker}: failed to fetch {', '.join(types)}")

    # Portfolio overview
    summary = portfolio_summary(rows, metrics_map)
    print(f"\n  Holdings: {summary['total_holdings']}")

    if summary.get("geography_weights"):
        print(f"\n  By Geography:")
        for geo, w in summary["geography_weights"].items():
            print(f"    {geo:<15} {w:.1f}%")

    if summary.get("currency_weights"):
        print(f"\n  By Currency:")
        for ccy, w in summary["currency_weights"].items():
            print(f"    {ccy:<5} {w:.1f}%")

    if summary.get("data_quality_issues"):
        print(f"\n  ⚠  Data Quality Flags:")
        for issue in summary["data_quality_issues"]:
            print(f"    {issue}")

    print("\n  Per-Holding Snapshot:")
    print(f"  {'Ticker':<15} {'Company':<30} {'Price':>10} {'Div Yld':>8} {'Data%':>6}")
    print(f"  {'-'*15} {'-'*30} {'-'*10} {'-'*8} {'-'*6}")
    for row in rows:
        ticker = row.get("ticker", "")
        m = metrics_map.get(ticker)
        company = (row.get("company") or "")[:30]
        price_str = row.get("current_price", "N/A")
        div_str = row.get("dividend_yield_pct", "—")
        completeness = f"{m.data_completeness_pct:.0f}%" if m and m.data_completeness_pct is not None else "—"
        print(f"  {ticker:<15} {company:<30} {price_str:>10} {div_str:>8} {completeness:>6}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Refresh portfolio data from yfinance")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Ignore cache, re-fetch all data")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Refresh only this ticker")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and display but do not write files")
    parser.add_argument("--no-financials", action="store_true",
                        help="Skip financial statements (faster)")
    args = parser.parse_args()

    print(f"\nAI Investment Agent — Portfolio Refresh")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Project: {PROJECT_ROOT}")

    # Read portfolio
    rows = read_portfolio_csv()
    print(f"\nLoaded {len(rows)} holdings from portfolio_snapshot.csv")

    # Note any anomalies
    for row in rows:
        weight_str = row.get("portfolio_weight_pct", "").replace("%", "")
        try:
            w = float(weight_str)
            if w < 0:
                print(f"  ⚠  {row['ticker']}: negative portfolio weight ({weight_str}%) — please verify")
        except ValueError:
            pass

    # Determine tickers to fetch
    if args.ticker:
        tickers = [args.ticker]
    else:
        tickers = [r["ticker"].strip() for r in rows if r.get("ticker", "").strip()]

    print(f"\nFetching data for {len(tickers)} tickers...")
    if args.force_refresh:
        print("(Cache bypassed — fetching fresh from yfinance)")

    # Fetch
    fetch_results = fetch_portfolio(
        tickers=tickers,
        force_refresh=args.force_refresh,
        include_financials=not args.no_financials,
        include_history=True,
    )

    # Normalize
    print("\nNormalizing financial data...")
    metrics_map = normalize_portfolio(fetch_results)

    # Attach yfinance sector info
    _attach_yf_sector(metrics_map, fetch_results)

    # Enrich portfolio rows
    enriched_rows = enrich_portfolio(rows, metrics_map)

    # Print summary
    _print_summary(enriched_rows, metrics_map, fetch_results)

    if args.dry_run:
        print("Dry run — no files written.")
        return

    # Save processed metrics
    metrics_path = save_processed_metrics(metrics_map)
    print(f"Metrics saved: {metrics_path}")

    # Write updated portfolio CSV
    write_portfolio_csv(enriched_rows)
    print(f"Portfolio updated: {PORTFOLIO_FILE}")

    print(f"\nDone. {datetime.now().strftime('%H:%M:%S')}")
    print(
        "\nNext step: ask Claude to analyze any holding, e.g.:\n"
        '  "Analyze FFH.TO" or "Should I add to ATD.TO?"'
    )


if __name__ == "__main__":
    main()
