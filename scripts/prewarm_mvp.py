"""
Pre-warm MVP Ticker Cache — Phase 10.5
=======================================
Sequentially fetches all 33 MVP tickers and writes them to the local cache.
Spaces requests 35 seconds apart to avoid Yahoo Finance rate-limiting (429).

This script is meant to be run BEFORE a demo or presentation so the Streamlit
UI can serve analysis from cache instead of making live Yahoo Finance requests.

Usage
-----
  python scripts/prewarm_mvp.py                  # warm all 33 tickers
  python scripts/prewarm_mvp.py --force-refresh  # re-fetch even if cached
  python scripts/prewarm_mvp.py --ticker ENB.TO  # warm a single ticker
  python scripts/prewarm_mvp.py --ticker ENB.TO --ticker AMZN  # subset

Windows compatible — no bash, no Unix-specific commands.

Output legend
  ✓ cached    ticker already has fresh cache, skipped
  ✓ fetched   ticker was fetched and cached successfully
  ⚠ limited   Yahoo Finance returned 429 (rate limited); will retry with delay
  ✗ failed    fetch failed for another reason

The script exits 0 if all tickers were either already cached or fetched
successfully, and exits 1 if any ticker failed permanently.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from data.mvp_tickers import MVP_TICKER_SYMBOLS  # noqa: E402
from ui.data_status import get_ticker_cache_status  # noqa: E402

log = logging.getLogger("prewarm")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INTER_TICKER_DELAY_S = 35       # seconds between ticker fetches
_RATE_LIMIT_RETRY_DELAY_S = 90  # seconds to wait after a 429 before retrying
_MAX_RATE_LIMIT_RETRIES = 2      # how many times we'll retry a single 429'd ticker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_fresh(ticker: str) -> bool:
    """Return True if all three cache files for `ticker` are fresh."""
    return get_ticker_cache_status(ticker)["ready"]


def _fetch_one(ticker: str, force_refresh: bool) -> str:
    """
    Fetch a single ticker using the project's real fetcher.
    Returns one of: "cached", "fetched", "limited", "failed"
    """
    from data.ingestion.fetcher import fetch_ticker  # type: ignore

    try:
        result = fetch_ticker(ticker, force_refresh=force_refresh)
    except Exception as exc:
        err = str(exc)
        if "429" in err or "Too Many Requests" in err:
            return "limited"
        log.warning("Unexpected exception for %s: %s", ticker, exc)
        return "failed"

    info = result.get("info", {})
    if not info.get("_fetch_success", False):
        err = info.get("_fetch_error", "unknown")
        if "429" in str(err) or "Too Many Requests" in str(err):
            return "limited"
        log.warning("Fetch failed for %s: %s", ticker, err)
        return "failed"

    return "fetched"


# ---------------------------------------------------------------------------
# Main pre-warm loop
# ---------------------------------------------------------------------------

def prewarm(tickers: list[str], force_refresh: bool) -> dict[str, str]:
    """
    Pre-warm `tickers` sequentially.
    Returns a dict of ticker → outcome ("cached" | "fetched" | "limited" | "failed").
    """
    outcomes: dict[str, str] = {}
    total = len(tickers)

    for idx, ticker in enumerate(tickers, start=1):
        prefix = f"[{idx:>2}/{total}] {ticker:<18}"

        # Skip if already fresh (unless force-refresh)
        if not force_refresh and _is_fresh(ticker):
            print(f"{prefix}  ✓ cached")
            outcomes[ticker] = "cached"
            continue

        # Fetch with retry on rate-limit
        outcome = "failed"
        for attempt in range(1 + _MAX_RATE_LIMIT_RETRIES):
            if attempt > 0:
                print(
                    f"{prefix}  ⚠ rate limited — waiting {_RATE_LIMIT_RETRY_DELAY_S}s "
                    f"before retry {attempt}/{_MAX_RATE_LIMIT_RETRIES}…"
                )
                time.sleep(_RATE_LIMIT_RETRY_DELAY_S)

            outcome = _fetch_one(ticker, force_refresh=force_refresh)
            if outcome != "limited":
                break  # success or non-429 failure — stop retrying

        if outcome == "fetched":
            print(f"{prefix}  ✓ fetched")
        elif outcome == "cached":
            print(f"{prefix}  ✓ cached")
        elif outcome == "limited":
            print(f"{prefix}  ⚠ rate limited (gave up after {_MAX_RATE_LIMIT_RETRIES} retries)")
        else:
            print(f"{prefix}  ✗ failed")

        outcomes[ticker] = outcome

        # Inter-ticker delay (skip after the last ticker)
        if idx < total:
            print(f"         ↳ waiting {_INTER_TICKER_DELAY_S}s before next ticker…")
            time.sleep(_INTER_TICKER_DELAY_S)

    return outcomes


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _print_summary(outcomes: dict[str, str]) -> int:
    """Print a summary table. Return exit code (0 = all ok, 1 = any failure)."""
    n_cached  = sum(1 for v in outcomes.values() if v == "cached")
    n_fetched = sum(1 for v in outcomes.values() if v == "fetched")
    n_limited = sum(1 for v in outcomes.values() if v == "limited")
    n_failed  = sum(1 for v in outcomes.values() if v == "failed")

    print()
    print("=" * 60)
    print("Pre-warm complete")
    print("-" * 60)
    print(f"  ✓ Already cached : {n_cached}")
    print(f"  ✓ Freshly fetched: {n_fetched}")
    print(f"  ⚠ Rate limited   : {n_limited}")
    print(f"  ✗ Failed         : {n_failed}")
    print("=" * 60)

    if n_limited:
        print()
        print("Rate-limited tickers (re-run this script in 5 minutes):")
        for t, v in outcomes.items():
            if v == "limited":
                print(f"  {t}")

    if n_failed:
        print()
        print("Failed tickers (check ticker symbols and network):")
        for t, v in outcomes.items():
            if v == "failed":
                print(f"  {t}")

    return 1 if (n_limited or n_failed) else 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-warm the local yfinance cache for MVP tickers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--ticker",
        metavar="TICKER",
        action="append",
        dest="tickers",
        help="Warm only this ticker (can be specified multiple times). "
             "Default: all 33 MVP tickers.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        default=False,
        help="Re-fetch even if the cache is already fresh.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be done without actually fetching.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    args = _parse_args()

    # Resolve ticker list
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers]
        # Validate against MVP universe (warn but don't block — user may want custom)
        from data.mvp_tickers import MVP_TICKER_MAP
        for t in tickers:
            if t not in MVP_TICKER_MAP:
                print(f"  ⚠ Warning: {t} is not in the MVP ticker universe")
    else:
        tickers = list(MVP_TICKER_SYMBOLS)

    print(f"Pre-warming {len(tickers)} ticker(s)  "
          f"[force_refresh={args.force_refresh}]")
    print(f"Inter-ticker delay: {_INTER_TICKER_DELAY_S}s")
    print()

    if args.dry_run:
        for ticker in tickers:
            status = "READY (would skip)" if _is_fresh(ticker) else "would fetch"
            print(f"  {ticker:<18}  {status}")
        sys.exit(0)

    outcomes = prewarm(tickers, force_refresh=args.force_refresh)
    exit_code = _print_summary(outcomes)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
