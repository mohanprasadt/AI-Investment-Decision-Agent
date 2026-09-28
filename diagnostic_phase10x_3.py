"""
Phase 10.x Controlled Cold-Cache 429 Diagnostic — TEST SUITE 3
==============================================================
Run ONLY on the Windows machine (not sandbox — no network there).

Usage:
    python diagnostic_phase10x_3.py

Output:
    diagnostic_output_3.json  (read back into the session for analysis)

Tests:
    T1  — Direct yfinance per-endpoint: info, financials, history separately
    T2  — yfinance internal SQLite cache presence (py-yfinance/)
    T3  — Application path: load_ticker() through data_loader
    T4  — HTTP request count via DEBUG log interception
    T5  — ENB.TO vs FTS.TO vs TATASTEEL.NS comparison
    T6  — Singleton state: does the first 429 poison later tickers?
    T7  — Minimum production footprint: single ticker, zero retries
"""

import json
import logging
import os
import pathlib
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OUTPUT_FILE = pathlib.Path(__file__).parent / "diagnostic_output_3.json"
START = datetime.now(timezone.utc).isoformat()
RESULTS: Dict[str, Any] = {"started": START, "tests": {}}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _save():
    with open(OUTPUT_FILE, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)
    print(f"  [saved → {OUTPUT_FILE}]")

def _banner(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# HTTP request counter — hooks into yfinance DEBUG logger
# ---------------------------------------------------------------------------

class _RequestCounter(logging.Handler):
    """Captures every 'url=...' line emitted by yfinance's DEBUG logger."""
    def __init__(self):
        super().__init__()
        self.urls: List[str] = []
        self.count = 0

    def emit(self, record):
        msg = record.getMessage()
        if msg.startswith("url="):
            self.urls.append(msg[4:].strip())
            self.count += 1

def _attach_counter() -> _RequestCounter:
    counter = _RequestCounter()
    counter.setLevel(logging.DEBUG)
    yf_log = logging.getLogger("yfinance")
    yf_log.setLevel(logging.DEBUG)
    yf_log.addHandler(counter)
    return counter

def _detach_counter(counter: _RequestCounter):
    logging.getLogger("yfinance").removeHandler(counter)

def _read_counter(counter: _RequestCounter) -> Dict[str, Any]:
    return {
        "total_http_requests": counter.count,
        "urls": counter.urls,
    }


# ---------------------------------------------------------------------------
# T2 — Internal yfinance SQLite cache inspection (run FIRST — no HTTP calls)
# ---------------------------------------------------------------------------

def test_t2_internal_cache():
    _banner("T2 — yfinance internal SQLite cache inspection")
    import platformdirs
    cache_dir = pathlib.Path(platformdirs.user_cache_dir()) / "py-yfinance"
    result = {
        "cache_dir": str(cache_dir),
        "exists": cache_dir.exists(),
        "files": [],
        "tkr_tz_db_size_bytes": None,
        "cookies_db_size_bytes": None,
        "note": "",
    }

    if cache_dir.exists():
        for f in sorted(cache_dir.iterdir()):
            info = {"name": f.name, "size_bytes": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()}
            result["files"].append(info)
            if f.name == "tkr-tz.db":
                result["tkr_tz_db_size_bytes"] = f.stat().st_size
            elif f.name == "cookies.db":
                result["cookies_db_size_bytes"] = f.stat().st_size
        result["note"] = (
            "These caches survive deletion of data/cache/. "
            "A warm cookies.db means yfinance reuses an existing Yahoo cookie/crumb, "
            "reducing initial HTTP requests for subsequent tickers."
        )
    else:
        result["note"] = (
            "No py-yfinance cache directory found. "
            "First ticker will need a full cookie/crumb negotiation."
        )

    print(f"  Cache dir: {cache_dir}")
    print(f"  Exists:    {result['exists']}")
    for f in result["files"]:
        print(f"    {f['name']:30s}  {f['size_bytes']:8,d} bytes  mod={f['modified']}")
    if not result["files"]:
        print("    (no files)")
    RESULTS["tests"]["T2_internal_cache"] = result
    _save()


# ---------------------------------------------------------------------------
# T1 — Direct yfinance, per-endpoint, with request counting
# ---------------------------------------------------------------------------

TICKERS_T1 = ["ENB.TO", "FTS.TO", "TATASTEEL.NS"]
DELAY_BETWEEN = 35   # seconds — enough for Yahoo rate-limit window

def _fetch_endpoint(ticker: str, endpoint: str) -> Dict[str, Any]:
    """Fetch a single endpoint, count HTTP requests, return summary."""
    import yfinance as yf

    counter = _attach_counter()
    t_start = time.monotonic()
    row: Dict[str, Any] = {
        "ticker": ticker,
        "endpoint": endpoint,
        "timestamp": _now(),
        "success": False,
        "error": None,
        "empty": None,
        "http_requests": 0,
        "urls": [],
        "elapsed_s": 0,
    }

    try:
        tkr = yf.Ticker(ticker)
        if endpoint == "info":
            data = tkr.info
            row["success"] = bool(data and (data.get("longName") or data.get("currentPrice")))
            row["empty"] = not bool(data)
            row["sample"] = {k: data.get(k) for k in
                             ["longName", "currentPrice", "currency"] if k in (data or {})}
        elif endpoint == "financials":
            data = tkr.financials
            row["success"] = data is not None and not data.empty
            row["empty"] = (data is None or data.empty)
            row["rows"] = 0 if (data is None or data.empty) else len(data)
        elif endpoint == "balance_sheet":
            data = tkr.balance_sheet
            row["success"] = data is not None and not data.empty
            row["empty"] = (data is None or data.empty)
            row["rows"] = 0 if (data is None or data.empty) else len(data)
        elif endpoint == "cashflow":
            data = tkr.cashflow
            row["success"] = data is not None and not data.empty
            row["empty"] = (data is None or data.empty)
            row["rows"] = 0 if (data is None or data.empty) else len(data)
        elif endpoint == "history":
            data = tkr.history(period="5y")
            row["success"] = data is not None and not data.empty
            row["empty"] = (data is None or data.empty)
            row["rows"] = 0 if (data is None or data.empty) else len(data)
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"
        row["success"] = False
    finally:
        _detach_counter(counter)
        row["elapsed_s"] = round(time.monotonic() - t_start, 2)
        rc = _read_counter(counter)
        row["http_requests"] = rc["total_http_requests"]
        row["urls"] = rc["urls"]

    status = "OK" if row["success"] else ("EMPTY" if row["empty"] else "ERROR")
    print(f"    {ticker:16s} {endpoint:14s}  {status:6s}  "
          f"{row['http_requests']} HTTP req  {row['elapsed_s']}s"
          + (f"  ERR={row['error']}" if row['error'] else ""))
    return row


def test_t1_direct_yfinance():
    _banner("T1 — Direct yfinance per-endpoint (with HTTP request counting)")
    print(f"  Tickers: {TICKERS_T1}")
    print(f"  Delay between tickers: {DELAY_BETWEEN}s")
    print()

    rows: List[Dict] = []

    for i, ticker in enumerate(TICKERS_T1):
        if i > 0:
            print(f"  Waiting {DELAY_BETWEEN}s before next ticker...")
            time.sleep(DELAY_BETWEEN)

        print(f"  --- {ticker} ---")

        # Test info first
        r = _fetch_endpoint(ticker, "info")
        rows.append(r)
        time.sleep(2)

        # Only test financial endpoints if info succeeded (otherwise we'd be
        # wasting requests on a ticker we know is rate-limited)
        for ep in ["financials", "balance_sheet", "cashflow"]:
            r = _fetch_endpoint(ticker, ep)
            rows.append(r)
            time.sleep(1)

        r = _fetch_endpoint(ticker, "history")
        rows.append(r)

    # Summarize by ticker
    summary: Dict[str, Any] = {}
    for ticker in TICKERS_T1:
        t_rows = [r for r in rows if r["ticker"] == ticker]
        total_req = sum(r["http_requests"] for r in t_rows)
        any_error = [r for r in t_rows if r["error"]]
        any_empty = [r for r in t_rows if r["empty"] and not r["error"]]
        all_ok = all(r["success"] for r in t_rows)
        summary[ticker] = {
            "all_succeeded": all_ok,
            "total_http_requests": total_req,
            "failed_endpoints": [r["endpoint"] for r in t_rows if not r["success"]],
            "errored_endpoints": [r["endpoint"] for r in any_error],
            "empty_endpoints": [r["endpoint"] for r in any_empty],
        }

    print()
    print("  SUMMARY:")
    for ticker, s in summary.items():
        status = "ALL OK" if s["all_succeeded"] else "PARTIAL/FAIL"
        print(f"    {ticker:16s}  {status:10s}  "
              f"{s['total_http_requests']} total HTTP  "
              f"failed={s['failed_endpoints']}")

    RESULTS["tests"]["T1_direct_yfinance"] = {"rows": rows, "summary": summary}
    _save()


# ---------------------------------------------------------------------------
# T3 — Application path: load_ticker() through data_loader
# ---------------------------------------------------------------------------

TICKERS_T3 = ["ENB.TO", "FTS.TO", "TATASTEEL.NS"]

def test_t3_application_path():
    _banner("T3 — Application path: load_ticker() through data_loader")
    print("  Note: This uses the REAL application data_loader + fetcher pipeline.")
    print("  No retries (we're testing one call only).")
    print()

    rows: List[Dict] = []

    for i, ticker in enumerate(TICKERS_T3):
        if i > 0:
            print(f"  Waiting {DELAY_BETWEEN}s before next ticker...")
            time.sleep(DELAY_BETWEEN)

        print(f"  --- {ticker} ---")
        counter = _attach_counter()
        t_start = time.monotonic()
        row: Dict[str, Any] = {
            "ticker": ticker,
            "timestamp": _now(),
            "load_ok": False,
            "cannot_complete_reason": None,
            "company_name": None,
            "current_price": None,
            "data_completeness_pct": None,
            "info_fetch_success": None,
            "financials_fetch_success": None,
            "history_fetch_success": None,
            "http_requests": 0,
            "urls": [],
            "elapsed_s": 0,
            "error": None,
        }

        try:
            from analytics.agent.data_loader import load_ticker
            from data.ingestion.fetcher import fetch_ticker

            # Fetch raw first to see individual component status
            raw = fetch_ticker(ticker, force_refresh=True)
            row["info_fetch_success"] = raw.get("info", {}).get("_fetch_success")
            row["info_fetch_error"] = raw.get("info", {}).get("_fetch_error")
            row["financials_fetch_success"] = raw.get("financials", {}).get("_fetch_success")
            row["financials_fetch_error"] = raw.get("financials", {}).get("_fetch_error")
            row["history_fetch_success"] = raw.get("history", {}).get("_fetch_success")
            row["history_fetch_error"] = raw.get("history", {}).get("_fetch_error")

            # Now load through the full pipeline
            result = load_ticker(ticker=ticker, analysis_date=datetime.utcnow().strftime("%Y-%m-%d"))
            row["load_ok"] = result.ok
            row["cannot_complete_reason"] = result.cannot_complete_reason or None
            row["company_name"] = result.company_name
            row["current_price"] = result.current_price
            row["data_completeness_pct"] = result.data_completeness_pct

        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        finally:
            _detach_counter(counter)
            row["elapsed_s"] = round(time.monotonic() - t_start, 2)
            rc = _read_counter(counter)
            row["http_requests"] = rc["total_http_requests"]
            row["urls"] = rc["urls"]

        rows.append(row)
        status = "OK" if row["load_ok"] else "FAIL"
        print(f"    {ticker:16s}  load={status:4s}  "
              f"info={row['info_fetch_success']}  "
              f"fin={row['financials_fetch_success']}  "
              f"hist={row['history_fetch_success']}  "
              f"{row['http_requests']} HTTP  "
              f"{row['data_completeness_pct']}% complete")
        if row["cannot_complete_reason"]:
            reason_short = str(row["cannot_complete_reason"])[:120]
            print(f"    cannot_complete: {reason_short}")

    RESULTS["tests"]["T3_application_path"] = rows
    _save()


# ---------------------------------------------------------------------------
# T4 — HTTP request count anatomy for a single cold-cache ticker
# ---------------------------------------------------------------------------

def test_t4_request_count_anatomy():
    _banner("T4 — HTTP request count anatomy (cold cache, one ticker)")
    ticker = "AAPL"   # Well-known ticker; usually succeeds; good baseline
    print(f"  Ticker: {ticker}  (force_refresh=True, always cold)")
    print()

    import yfinance as yf
    from data.ingestion.fetcher import _cache_path, CACHE_DIR

    # Clear any existing cache for AAPL
    for suffix in ["info", "financials", "history_5y"]:
        p = _cache_path(ticker, suffix)
        if p.exists():
            p.unlink()
            print(f"  Cleared cache: {p.name}")

    time.sleep(2)

    endpoints = [
        ("info",         lambda tkr: tkr.info),
        ("financials",   lambda tkr: tkr.financials),
        ("balance_sheet",lambda tkr: tkr.balance_sheet),
        ("cashflow",     lambda tkr: tkr.cashflow),
        ("history_5y",   lambda tkr: tkr.history(period="5y")),
    ]

    endpoint_rows = []
    running_total = 0

    for ep_name, fn in endpoints:
        counter = _attach_counter()
        t_start = time.monotonic()
        ep_row: Dict[str, Any] = {
            "endpoint": ep_name,
            "error": None,
            "empty": None,
            "http_requests": 0,
        }
        try:
            tkr = yf.Ticker(ticker)
            data = fn(tkr)
            if hasattr(data, "empty"):
                ep_row["empty"] = data.empty
            else:
                ep_row["empty"] = not bool(data)
        except Exception as e:
            ep_row["error"] = f"{type(e).__name__}: {e}"
        finally:
            _detach_counter(counter)
            rc = _read_counter(counter)
            ep_row["http_requests"] = rc["total_http_requests"]
            ep_row["urls"] = rc["urls"]
            ep_row["elapsed_s"] = round(time.monotonic() - t_start, 2)

        running_total += ep_row["http_requests"]
        status = "OK" if not ep_row["empty"] and not ep_row["error"] else (
                 "EMPTY" if ep_row["empty"] else "ERROR")
        print(f"    {ep_name:15s}  {status:6s}  "
              f"{ep_row['http_requests']:2d} req  "
              f"cumulative={running_total:3d}  {ep_row['elapsed_s']}s")
        for url in ep_row["urls"]:
            print(f"      → {url[:100]}")
        endpoint_rows.append(ep_row)
        time.sleep(1)

    print()
    print(f"  TOTAL HTTP requests for one cold ticker ({ticker}): {running_total}")
    print(f"  (with 4 pipeline retries × {running_total} ≈ {running_total * 4} requests per failing ticker)")

    RESULTS["tests"]["T4_request_count"] = {
        "ticker": ticker,
        "endpoints": endpoint_rows,
        "total_http_requests": running_total,
        "pipeline_retry_amplification": running_total * 4,
    }
    _save()


# ---------------------------------------------------------------------------
# T5 — ENB.TO vs FTS.TO: singleton state and cookie reuse
# ---------------------------------------------------------------------------

def test_t5_singleton_comparison():
    _banner("T5 — Singleton cookie state: ENB.TO first vs FTS.TO first")
    print("  Testing whether ORDER matters — does the first ticker poison the singleton?")
    print()

    import yfinance as yf

    results_by_order: Dict[str, Any] = {}

    for order_label, tickers in [
        ("ENB_first", ["ENB.TO", "FTS.TO"]),
        ("FTS_first_after_delay", ["FTS.TO"]),
    ]:
        print(f"  --- Order: {order_label} ---")
        if order_label != "ENB_first":
            print(f"  Waiting {DELAY_BETWEEN}s...")
            time.sleep(DELAY_BETWEEN)

        order_rows = []
        for i, ticker in enumerate(tickers):
            if i > 0:
                print(f"    Waiting 10s between tickers in same order...")
                time.sleep(10)

            counter = _attach_counter()
            t_start = time.monotonic()
            row = {"ticker": ticker, "order": i + 1,
                   "info_success": False, "info_error": None,
                   "http_requests": 0, "urls": []}
            try:
                tkr = yf.Ticker(ticker)
                info = tkr.info or {}
                row["info_success"] = bool(info.get("longName") or info.get("currentPrice"))
                row["info_empty"] = not bool(info)
                row["company"] = info.get("longName") or info.get("shortName") or "?"
            except Exception as e:
                row["info_error"] = f"{type(e).__name__}: {e}"
            finally:
                _detach_counter(counter)
                rc = _read_counter(counter)
                row["http_requests"] = rc["total_http_requests"]
                row["urls"] = rc["urls"]
                row["elapsed_s"] = round(time.monotonic() - t_start, 2)

            order_rows.append(row)
            status = "OK" if row["info_success"] else (
                     "EMPTY" if row.get("info_empty") else "ERROR")
            print(f"    pos={i+1}  {ticker:16s}  {status:6s}  "
                  f"{row['http_requests']} HTTP  "
                  + (row.get("company", "") or row.get("info_error", "")))

        results_by_order[order_label] = order_rows

    RESULTS["tests"]["T5_singleton_comparison"] = results_by_order
    _save()


# ---------------------------------------------------------------------------
# T6 — Pipeline retry amplification: does 429 on info trigger multiple attempts?
# ---------------------------------------------------------------------------

def test_t6_retry_amplification():
    _banner("T6 — Pipeline retry amplification analysis (code inspection only)")
    print("  Analyzing pipeline.py retry logic without making network calls.")
    print()

    # Read pipeline.py and data_loader.py to confirm the exact retry conditions
    project_root = pathlib.Path(__file__).parent
    pipeline_path = project_root / "analytics" / "agent" / "pipeline.py"
    loader_path   = project_root / "analytics" / "agent" / "data_loader.py"

    findings: Dict[str, Any] = {}

    for label, path in [("pipeline", pipeline_path), ("data_loader", loader_path)]:
        lines = path.read_text().splitlines()
        key_lines = {}
        for i, line in enumerate(lines, 1):
            if any(k in line for k in ["429", "Too Many", "cannot_complete", "RETRY", "_RETRY_DELAYS",
                                        "cannot_complete_reason", "fetch_success", "load_ok"]):
                key_lines[i] = line.rstrip()
        findings[label] = key_lines

    # Summarize logic
    summary = {
        "retry_delays_seconds": [0, 5, 15, 30],
        "total_attempts": 4,
        "retry_condition": (
            "'429' or 'Too Many Requests' in load_result.cannot_complete_reason"
        ),
        "cannot_complete_reason_set_when": (
            "info._fetch_success=False OR (no company_name AND no current_price)"
        ),
        "financials_failure_triggers_retry": False,
        "history_failure_triggers_retry": False,
        "reason": (
            "data_loader.py only checks raw['info']['_fetch_success'] to set "
            "cannot_complete_reason. financials and history failures are NOT checked "
            "— the pipeline proceeds with 0% data completeness, never retrying."
        ),
        "consequence": (
            "If info succeeds but financials 429s silently, the pipeline proceeds "
            "with empty financials, produces a 0%-complete WAIT_INSUFFICIENT_EVIDENCE "
            "result, and returns ok=True. The UI shows an analysis with no data."
        ),
    }

    print(f"  Retry delays: {summary['retry_delays_seconds']}")
    print(f"  Retry condition: {summary['retry_condition']}")
    print(f"  financials failure triggers retry: {summary['financials_failure_triggers_retry']}")
    print(f"  history failure triggers retry:    {summary['history_failure_triggers_retry']}")
    print()
    print(f"  CONSEQUENCE: {summary['consequence']}")

    findings["summary"] = summary
    RESULTS["tests"]["T6_retry_amplification"] = findings
    _save()


# ---------------------------------------------------------------------------
# T7 — Minimum footprint test: single endpoint, single ticker
# ---------------------------------------------------------------------------

def test_t7_minimum_footprint():
    _banner("T7 — Minimum footprint: is it info OR financials that triggers 429?")
    print("  Testing info ONLY for each problem ticker to isolate the failing endpoint.")
    print()

    import yfinance as yf

    rows = []
    for i, ticker in enumerate(["ENB.TO", "FTS.TO", "TATASTEEL.NS"]):
        if i > 0:
            print(f"  Waiting {DELAY_BETWEEN}s...")
            time.sleep(DELAY_BETWEEN)

        counter = _attach_counter()
        t_start = time.monotonic()
        row = {"ticker": ticker, "endpoint": "info_only",
               "timestamp": _now(), "success": False,
               "empty": None, "error": None, "company": None,
               "http_requests": 0, "urls": []}
        try:
            tkr = yf.Ticker(ticker)
            info = tkr.info or {}
            row["success"] = bool(info.get("longName") or info.get("currentPrice"))
            row["empty"] = not bool(info)
            row["company"] = info.get("longName") or info.get("shortName") or "?"
            row["currentPrice"] = info.get("currentPrice")
            row["currency"] = info.get("currency")
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
        finally:
            _detach_counter(counter)
            rc = _read_counter(counter)
            row["http_requests"] = rc["total_http_requests"]
            row["urls"] = rc["urls"]
            row["elapsed_s"] = round(time.monotonic() - t_start, 2)

        rows.append(row)
        status = "OK" if row["success"] else ("EMPTY" if row["empty"] else "ERROR")
        print(f"    {ticker:16s}  {status:6s}  "
              f"{row['http_requests']} HTTP  "
              f"{row.get('company') or row.get('error', '')}")

    RESULTS["tests"]["T7_minimum_footprint"] = rows
    _save()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Suppress all other logging noise
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    _banner("PHASE 10.x COLD-CACHE 429 DIAGNOSTIC — SUITE 3")
    print(f"  Python: {sys.version}")

    try:
        import yfinance as yf
        print(f"  yfinance: {yf.__version__}")
        RESULTS["env"] = {
            "python": sys.version,
            "yfinance": yf.__version__,
        }
    except ImportError as e:
        print(f"  ERROR: cannot import yfinance: {e}")
        sys.exit(1)

    # Collect env info
    try:
        import platformdirs
        import curl_cffi
        RESULTS["env"]["curl_cffi"] = curl_cffi.__version__
        print(f"  curl_cffi: {curl_cffi.__version__}")
    except ImportError:
        RESULTS["env"]["curl_cffi"] = "NOT INSTALLED — yfinance will use requests (less effective)"
        print("  curl_cffi: NOT INSTALLED")

    print()
    print("  IMPORTANT: Ensure data/cache/ has been FULLY deleted before running.")
    print("  Ensure at least 5 minutes have passed since any previous yfinance calls.")
    print("  Tests will pause between tickers to respect Yahoo rate limits.")
    print()

    # Run in order: T2 first (no HTTP), then T1, T3, T4, T5, T6 (code only), T7
    test_t2_internal_cache()
    test_t6_retry_amplification()   # code-only, no network

    print()
    print("  Starting network tests. Total estimated time: ~12 minutes.")
    print("  DO NOT run any other yfinance calls while this is running.")
    print()

    test_t1_direct_yfinance()
    test_t4_request_count_anatomy()
    test_t7_minimum_footprint()
    test_t3_application_path()
    test_t5_singleton_comparison()

    RESULTS["finished"] = _now()
    _save()

    _banner("DIAGNOSTIC COMPLETE")
    print(f"  Output: {OUTPUT_FILE}")
    print()
    print("  NEXT STEP: Copy diagnostic_output_3.json back to the")
    print("  AI-Investment-Decision-Agent folder and share it in the session.")


if __name__ == "__main__":
    main()
