"""
Financial Data Fetcher
======================
Fetches financial data from yfinance with local JSON caching.

Design principles:
- Never crashes the pipeline on a single ticker failure
- Always records what data is missing and why
- Cache to disk so repeated analysis doesn't re-hit the network
- Clearly flags data staleness
- ETFs are handled separately from equities (limited fundamental data)

Run this on your local machine (not in the Cowork sandbox, which has no
outbound internet). After running, cached data is stored in data/cache/
and available for all downstream analysis.
"""

import json
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    raise ImportError("yfinance not installed. Run: pip install yfinance")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# ETF / Fund detection
# These tickers in the portfolio are ETFs or funds — treated differently
# ---------------------------------------------------------------------------

KNOWN_ETFS = {
    "CGL.C.TO",        # iShares Gold Bullion ETF (CAD hedged)
    "QGOLDHALF.NS",    # Nippon India Gold ETF (INR)
    "HDFCMFGETF.NS",   # HDFC Mutual Fund Gold ETF (INR)
}

# ---------------------------------------------------------------------------
# Cache utilities
# ---------------------------------------------------------------------------

def _cache_path(ticker: str, data_type: str) -> Path:
    safe = ticker.replace(".", "_").replace("/", "_").replace("^", "_")
    return CACHE_DIR / f"{safe}_{data_type}.json"


def _load_cache(ticker: str, data_type: str, max_age_hours: int = 24) -> Optional[dict]:
    """Load cached data if it exists and is fresh enough.

    P1: A cached entry whose ``_fetch_success`` is ``False`` is treated as a
    cache miss so the caller retries the underlying yfinance request rather
    than serving stale failure data for the full TTL.
    """
    path = _cache_path(ticker, data_type)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            cached = json.load(f)
        fetched_at = datetime.fromisoformat(cached.get("_fetched_at", "2000-01-01"))
        age = datetime.utcnow() - fetched_at
        if age > timedelta(hours=max_age_hours):
            log.debug(f"Cache expired for {ticker}/{data_type} (age: {age})")
            return None
        # P1: Do not serve a previously failed fetch as a valid cache hit.
        # Returning None here causes the caller to retry yfinance immediately
        # rather than blocking retries for the full TTL (24 h for history,
        # 48 h for financials).
        if not cached.get("_fetch_success", True):
            log.debug(
                f"Cache miss (prior failed fetch) for {ticker}/{data_type} "
                "— will retry fetch"
            )
            return None
        return cached
    except Exception as e:
        log.warning(f"Cache read failed for {ticker}/{data_type}: {e}")
        return None


def _save_cache(ticker: str, data_type: str, data: dict) -> None:
    path = _cache_path(ticker, data_type)
    data["_fetched_at"] = datetime.utcnow().isoformat()
    data["_ticker"] = ticker
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        log.warning(f"Cache write failed for {ticker}/{data_type}: {e}")


def clear_cache(ticker: Optional[str] = None) -> None:
    """Clear cache for one ticker or all tickers."""
    if ticker:
        for path in CACHE_DIR.glob(f"{ticker.replace('.', '_')}*.json"):
            path.unlink()
        log.info(f"Cache cleared for {ticker}")
    else:
        for path in CACHE_DIR.glob("*.json"):
            path.unlink()
        log.info("All cache cleared")


# ---------------------------------------------------------------------------
# Raw yfinance fetch
# ---------------------------------------------------------------------------

def _safe_get(info: dict, key: str, default=None):
    """Get a value from yfinance info dict, returning default on None or missing."""
    val = info.get(key, default)
    return default if val is None else val


def fetch_info(ticker: str, force_refresh: bool = False, max_age_hours: int = 24) -> Dict[str, Any]:
    """
    Fetch yfinance .info for a ticker with caching.

    Returns a dict with keys:
    - _ticker, _fetched_at, _fetch_success, _fetch_error
    - All yfinance info fields (or empty dict on failure)
    """
    if not force_refresh:
        cached = _load_cache(ticker, "info", max_age_hours)
        if cached:
            log.debug(f"Cache hit: {ticker}/info")
            return cached

    log.info(f"Fetching info: {ticker}")
    result: Dict[str, Any] = {"_ticker": ticker, "_fetch_success": False, "_fetch_error": None}

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        result.update(info)
        result["_fetch_success"] = True
        _save_cache(ticker, "info", result)
        time.sleep(0.5)   # polite rate limiting
    except Exception as e:
        result["_fetch_error"] = str(e)
        log.warning(f"Failed to fetch info for {ticker}: {e}")

    return result


def fetch_financials(ticker: str, force_refresh: bool = False, max_age_hours: int = 48) -> Dict[str, Any]:
    """
    Fetch annual income statement, balance sheet, and cash flow statement.

    Returns a dict with:
    - income_stmt: {field: {date: value}} or {}
    - balance_sheet: {field: {date: value}} or {}
    - cash_flow: {field: {date: value}} or {}
    - _fetch_success, _fetch_error
    """
    if not force_refresh:
        cached = _load_cache(ticker, "financials", max_age_hours)
        if cached:
            log.debug(f"Cache hit: {ticker}/financials")
            return cached

    log.info(f"Fetching financials: {ticker}")
    result: Dict[str, Any] = {
        "_ticker": ticker,
        "_fetch_success": False,
        "_fetch_error": None,
        "income_stmt": {},
        "balance_sheet": {},
        "cash_flow": {},
    }

    try:
        t = yf.Ticker(ticker)

        def df_to_dict(df):
            """Convert a yfinance DataFrame (fields × dates) to {field: {year: value}}."""
            if df is None or df.empty:
                return {}
            out = {}
            for field in df.index:
                out[str(field)] = {}
                for col in df.columns:
                    year = col.year if hasattr(col, 'year') else str(col)
                    val = df.loc[field, col]
                    # Convert numpy types to Python native
                    if hasattr(val, 'item'):
                        val = val.item()
                    if val != val:   # NaN check
                        val = None
                    out[str(field)][year] = val
            return out

        result["income_stmt"] = df_to_dict(t.financials)
        result["balance_sheet"] = df_to_dict(t.balance_sheet)
        result["cash_flow"] = df_to_dict(t.cashflow)

        # P0: If ALL three statements are empty, yfinance returned no data.
        # This typically occurs when Yahoo Finance rate-limits the financial-
        # data endpoint: yfinance silently catches the error internally and
        # returns an empty DataFrame instead of raising.  Treat all-empty as a
        # failed fetch so the result is not cached, allowing the next request
        # to retry.  A partial result (at least one non-empty statement) is
        # still considered success and is cached normally.
        if not result["income_stmt"] and not result["balance_sheet"] and not result["cash_flow"]:
            result["_fetch_error"] = (
                "yfinance returned empty DataFrames for all financial statements "
                "(income statement, balance sheet, cash flow). "
                "This typically indicates a Yahoo Finance rate-limit on the "
                "financial-data endpoint. Result not cached — next request will retry."
            )
            log.warning(
                f"fetch_financials: all statements empty for {ticker} "
                "(likely rate-limited or data unavailable) — not caching"
            )
            return result   # _fetch_success remains False; no _save_cache call

        result["_fetch_success"] = True
        _save_cache(ticker, "financials", result)
        time.sleep(0.5)
    except Exception as e:
        result["_fetch_error"] = str(e)
        log.warning(f"Failed to fetch financials for {ticker}: {e}")

    return result


def fetch_history(
    ticker: str,
    period: str = "5y",
    force_refresh: bool = False,
    max_age_hours: int = 24
) -> Dict[str, Any]:
    """
    Fetch price history.

    Returns {dates: [...], closes: [...], _fetch_success, _fetch_error}

    Cache behaviour (mirrors fetch_financials P0 fix):
    - Successful fetch (non-empty DataFrame) → _fetch_success=True, result cached.
    - Empty DataFrame → _fetch_success=False, result NOT cached; next request retries.
    - Exception → _fetch_success=False, result NOT cached (existing behaviour).
    """
    cache_key = f"history_{period}"
    if not force_refresh:
        cached = _load_cache(ticker, cache_key, max_age_hours)
        if cached:
            return cached

    log.info(f"Fetching price history: {ticker} ({period})")
    result: Dict[str, Any] = {
        "_ticker": ticker,
        "_fetch_success": False,
        "_fetch_error": None,
        "dates": [],
        "closes": [],
    }

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist is not None and not hist.empty:
            result["dates"] = [d.isoformat() for d in hist.index]
            result["closes"] = [float(c) for c in hist["Close"]]
            result["_fetch_success"] = True
            _save_cache(ticker, cache_key, result)
            time.sleep(0.3)
        else:
            # Empty DataFrame — typically Yahoo Finance rate-limiting this endpoint.
            # Do NOT cache: next request must retry rather than serving a dead entry.
            result["_fetch_error"] = (
                "yfinance returned an empty history DataFrame. "
                "This typically indicates a Yahoo Finance rate-limit or data "
                "unavailability. Result not cached — next request will retry."
            )
            log.warning(
                f"fetch_history: empty result for {ticker} ({period}) "
                "(likely rate-limited or data unavailable) — not caching"
            )
    except Exception as e:
        result["_fetch_error"] = str(e)
        log.warning(f"Failed to fetch history for {ticker}: {e}")

    return result


# ---------------------------------------------------------------------------
# Portfolio-level batch fetch
# ---------------------------------------------------------------------------

FetchResult = Dict[str, Any]   # {ticker: {info, financials, history}}


def fetch_portfolio(
    tickers: List[str],
    force_refresh: bool = False,
    include_financials: bool = True,
    include_history: bool = True,
    delay_between_tickers: float = 1.0
) -> Dict[str, FetchResult]:
    """
    Fetch data for all portfolio tickers.

    Returns {ticker: {"info": ..., "financials": ..., "history": ...}}
    Continues on individual ticker failures — never aborts the whole batch.
    """
    results: Dict[str, FetchResult] = {}
    total = len(tickers)

    for i, ticker in enumerate(tickers, 1):
        log.info(f"[{i}/{total}] Processing {ticker}")
        ticker_data: FetchResult = {}

        is_etf = ticker in KNOWN_ETFS

        ticker_data["info"] = fetch_info(ticker, force_refresh=force_refresh)
        ticker_data["is_etf"] = is_etf

        if include_financials and not is_etf:
            ticker_data["financials"] = fetch_financials(ticker, force_refresh=force_refresh)
        else:
            ticker_data["financials"] = {
                "_ticker": ticker, "_fetch_success": False,
                "_fetch_error": "ETF — fundamental financial statements not applicable",
                "income_stmt": {}, "balance_sheet": {}, "cash_flow": {}
            }

        if include_history:
            ticker_data["history"] = fetch_history(ticker, force_refresh=force_refresh)

        results[ticker] = ticker_data

        if i < total:
            time.sleep(delay_between_tickers)

    return results


def fetch_status_report(results: Dict[str, FetchResult]) -> Dict[str, Any]:
    """Summarize what succeeded and what failed in a batch fetch."""
    report = {
        "total": len(results),
        "info_success": 0,
        "financials_success": 0,
        "history_success": 0,
        "failures": {}
    }
    for ticker, data in results.items():
        if data.get("info", {}).get("_fetch_success"):
            report["info_success"] += 1
        else:
            report["failures"].setdefault(ticker, []).append("info")

        if data.get("financials", {}).get("_fetch_success"):
            report["financials_success"] += 1
        elif not data.get("is_etf"):
            report["failures"].setdefault(ticker, []).append("financials")

        if data.get("history", {}).get("_fetch_success"):
            report["history_success"] += 1
        else:
            report["failures"].setdefault(ticker, []).append("history")

    return report


# ---------------------------------------------------------------------------
# Quick single-ticker convenience function
# ---------------------------------------------------------------------------

def fetch_ticker(ticker: str, force_refresh: bool = False) -> FetchResult:
    """Convenience: fetch all data for a single ticker.

    Short-circuit on info failure: when fetch_info() returns _fetch_success=False
    (typically HTTP 429 / rate limit), fetch_financials() and fetch_history() are
    NOT called.  Sending additional requests to Yahoo while rate-limited extends
    the rate-limit window rather than letting it clear.  The skipped components are
    returned as _fetch_success=False stubs so callers can distinguish "skipped due
    to info failure" from genuine data unavailability.
    """
    is_etf = ticker in KNOWN_ETFS
    info = fetch_info(ticker, force_refresh=force_refresh)

    if not info.get("_fetch_success"):
        _skip_reason = (
            "Skipped — fetch_info() failed (likely HTTP 429 / rate limit). "
            "Sending additional Yahoo Finance requests while rate-limited extends "
            "the rate-limit window. Retry the full fetch after the window clears."
        )
        return {
            "info": info,
            "financials": {
                "_ticker": ticker,
                "_fetch_success": False,
                "_fetch_error": _skip_reason,
                "income_stmt": {},
                "balance_sheet": {},
                "cash_flow": {},
            },
            "history": {
                "_ticker": ticker,
                "_fetch_success": False,
                "_fetch_error": _skip_reason,
                "dates": [],
                "closes": [],
            },
            "is_etf": is_etf,
        }

    return {
        "info": info,
        "financials": fetch_financials(ticker, force_refresh=force_refresh) if not is_etf else {},
        "history": fetch_history(ticker, force_refresh=force_refresh),
        "is_etf": is_etf,
    }


if __name__ == "__main__":
    # Quick smoke test — run on your local machine
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    log.info(f"Testing fetcher with: {ticker}")
    data = fetch_ticker(ticker)
    info = data["info"]
    print(f"\n{ticker} — {info.get('longName', 'Unknown')}")
    print(f"  Fetch success: {info.get('_fetch_success')}")
    print(f"  Current price: {info.get('currentPrice')}")
    print(f"  Currency: {info.get('currency')}")
    print(f"  Sector: {info.get('sector')}")
    print(f"  Market cap: {info.get('marketCap'):,}" if info.get('marketCap') else "  Market cap: N/A")
    if data["financials"].get("_fetch_success"):
        fields = list(data["financials"]["income_stmt"].keys())
        print(f"  Income stmt fields: {len(fields)} ({fields[:3]}...)")
