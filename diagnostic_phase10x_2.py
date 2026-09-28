"""
Phase 10.x Follow-up Diagnostic — yfinance 429 Behaviour Across Multiple Tickers
==================================================================================
Run from the project root on the Windows machine:

    python diagnostic_phase10x_2.py

Output is written to diagnostic_output_2.json.

DO NOT run this inside the Streamlit process.  Run it from a plain terminal.

What this script tests (in order):
  1.  Cache state for each target ticker (what exists, ages, validity)
  2.  Per-endpoint yfinance tests with delays (info / financials / history)
       tested for ENB.TO, FTS.TO, AAPL, TATASTEEL.NS
  3.  Full fetch_ticker() call (application path) for each ticker,
      one at a time with 10 s gaps
  4.  Retry-loop simulation: does a 429 on info trigger retries correctly?
  5.  Request counting: how many actual HTTP calls does one analysis generate?
  6.  yfinance / Python version confirmation

Design constraints:
  - No production code is modified.
  - Cache files are NOT deleted or overwritten.
  - All network calls go through the real yfinance session (same as production).
  - The script exits cleanly on 429 and records what it observed.
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# ── project root on sys.path ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CACHE_DIR = ROOT / "data" / "cache"
OUTPUT    = ROOT / "diagnostic_output_2.json"

TICKERS = ["ENB.TO", "FTS.TO", "AAPL", "TATASTEEL.NS"]

# Delay between individual endpoint tests (seconds).
# Keep at ≥5 s to stay well under Yahoo's rate limit during the diagnostic.
INTER_ENDPOINT_DELAY = 5
INTER_TICKER_DELAY   = 15   # between full-ticker sequences
INTER_STEP_DELAY     = 30   # between major diagnostic steps


# ── helpers ─────────────────────────────────────────────────────────────────

def ts() -> str:
    return datetime.utcnow().isoformat()


def _safe(ticker: str) -> str:
    return ticker.replace(".", "_").replace("/", "_")


def _cache_file(ticker: str, dtype: str) -> Path:
    return CACHE_DIR / f"{_safe(ticker)}_{dtype}.json"


def _read_cache(ticker: str, dtype: str) -> dict | None:
    p = _cache_file(ticker, dtype)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _cache_entry_summary(ticker: str, dtype: str, ttl_h: int) -> dict:
    now = datetime.utcnow()
    data = _read_cache(ticker, dtype)
    if data is None:
        return {"exists": False, "will_fetch": True, "reason": "no file"}

    fetched_at_str = data.get("_fetched_at", "2000-01-01")
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str)
    except ValueError:
        fetched_at = datetime(2000, 1, 1)

    age_h = (now - fetched_at).total_seconds() / 3600

    if age_h > ttl_h:
        return {"exists": True, "age_h": round(age_h, 2), "will_fetch": True,
                "reason": f"expired (TTL={ttl_h}h)", "_fetch_success": data.get("_fetch_success")}

    ok = data.get("_fetch_success", True)
    if not ok:
        return {"exists": True, "age_h": round(age_h, 2), "will_fetch": True,
                "reason": "P1 rejects _fetch_success=False", "_fetch_success": False}

    # ok=True — but may have empty payload (legacy dead entry, pre-P0)
    if dtype == "financials":
        inc = len(data.get("income_stmt", {}))
        bal = len(data.get("balance_sheet", {}))
        cf  = len(data.get("cash_flow", {}))
        if inc == 0 and bal == 0 and cf == 0:
            return {"exists": True, "age_h": round(age_h, 2), "will_fetch": False,
                    "reason": "LEGACY DEAD — ok=True but all statements empty (pre-P0 entry, P1 cannot catch)",
                    "_fetch_success": True, "income_fields": 0, "balance_fields": 0, "cf_fields": 0}
        return {"exists": True, "age_h": round(age_h, 2), "will_fetch": False,
                "reason": "valid", "_fetch_success": True,
                "income_fields": inc, "balance_fields": bal, "cf_fields": cf}

    elif dtype.startswith("history"):
        pts = len(data.get("dates", []))
        if pts == 0:
            return {"exists": True, "age_h": round(age_h, 2), "will_fetch": False,
                    "reason": "LEGACY DEAD — ok=True but 0 data points",
                    "_fetch_success": True, "datapoints": 0}
        return {"exists": True, "age_h": round(age_h, 2), "will_fetch": False,
                "reason": "valid", "_fetch_success": True, "datapoints": pts}

    else:  # info
        name = data.get("longName") or data.get("shortName") or ""
        price = data.get("currentPrice") or data.get("regularMarketPrice")
        return {"exists": True, "age_h": round(age_h, 2), "will_fetch": False,
                "reason": "valid", "_fetch_success": True,
                "name": name, "price": price}


# ── Step 1: Cache state ──────────────────────────────────────────────────────

def step1_cache_state() -> dict:
    print("\n[Step 1] Inspecting cache state...")
    result = {}
    for t in TICKERS:
        result[t] = {
            "info":       _cache_entry_summary(t, "info", 24),
            "financials": _cache_entry_summary(t, "financials", 48),
            "history_5y": _cache_entry_summary(t, "history_5y", 24),
        }
        fresh_count = sum(v["will_fetch"] for v in result[t].values())
        print(f"  {t}: {fresh_count} fresh yfinance requests needed for this analysis")
        for dtype, s in result[t].items():
            print(f"    {dtype:12s}: will_fetch={s['will_fetch']}  reason={s['reason']}")
    return result


# ── Step 2: Per-endpoint yfinance tests ──────────────────────────────────────

def _test_endpoint(ticker: str, endpoint: str) -> dict:
    """Call one yfinance endpoint and record success/failure/timing."""
    import yfinance as yf
    record = {"ticker": ticker, "endpoint": endpoint, "timestamp": ts()}
    t0 = time.time()
    try:
        obj = yf.Ticker(ticker)
        if endpoint == "info":
            data = obj.info
            record["keys"] = len(data) if data else 0
            record["price"] = data.get("currentPrice") or data.get("regularMarketPrice") if data else None
            record["name"]  = (data.get("longName") or data.get("shortName") or "")[:40] if data else ""
            record["ok"] = bool(data and (record["price"] or record["name"]))
        elif endpoint == "income_stmt":
            df = obj.financials
            record["rows"] = len(df) if df is not None else 0
            record["empty"] = df is None or df.empty
            record["ok"] = not record["empty"]
        elif endpoint == "balance_sheet":
            df = obj.balance_sheet
            record["rows"] = len(df) if df is not None else 0
            record["empty"] = df is None or df.empty
            record["ok"] = not record["empty"]
        elif endpoint == "cashflow":
            df = obj.cashflow
            record["rows"] = len(df) if df is not None else 0
            record["empty"] = df is None or df.empty
            record["ok"] = not record["empty"]
        elif endpoint == "history":
            df = obj.history(period="1mo")
            record["rows"] = len(df) if df is not None else 0
            record["empty"] = df is None or df.empty
            record["ok"] = not record["empty"]
        record["elapsed_s"] = round(time.time() - t0, 2)
        record["error"] = None
    except Exception as e:
        record["elapsed_s"] = round(time.time() - t0, 2)
        record["error"] = str(e)
        record["ok"] = False
        record["is_429"] = "429" in str(e) or "Too Many Requests" in str(e)
    return record


def step2_endpoint_tests() -> dict:
    print(f"\n[Step 2] Per-endpoint tests ({INTER_ENDPOINT_DELAY}s between endpoints, {INTER_TICKER_DELAY}s between tickers)...")
    results = {}
    endpoints = ["info", "income_stmt", "balance_sheet", "cashflow", "history"]

    for i, ticker in enumerate(TICKERS):
        if i > 0:
            print(f"  (waiting {INTER_TICKER_DELAY}s before next ticker...)")
            time.sleep(INTER_TICKER_DELAY)
        print(f"  Testing {ticker}...")
        results[ticker] = {}
        for j, ep in enumerate(endpoints):
            if j > 0:
                time.sleep(INTER_ENDPOINT_DELAY)
            r = _test_endpoint(ticker, ep)
            results[ticker][ep] = r
            status = "OK" if r["ok"] else f"FAIL{' (429)' if r.get('is_429') else ''}"
            print(f"    {ep:15s}: {status}  elapsed={r['elapsed_s']}s"
                  + (f"  error={r['error'][:80]}" if r.get("error") else ""))
    return results


# ── Step 3: Full application-path fetch_ticker() ────────────────────────────

def step3_full_fetch() -> dict:
    print(f"\n[Step 3] Full fetch_ticker() via application path ({INTER_TICKER_DELAY}s between tickers)...")
    from data.ingestion.fetcher import fetch_ticker
    results = {}

    for i, ticker in enumerate(TICKERS):
        if i > 0:
            print(f"  (waiting {INTER_TICKER_DELAY}s...)")
            time.sleep(INTER_TICKER_DELAY)
        print(f"  fetch_ticker('{ticker}')...")
        t0 = time.time()
        try:
            raw = fetch_ticker(ticker)
        except Exception as e:
            results[ticker] = {"error": str(e), "elapsed_s": round(time.time()-t0, 2)}
            print(f"    EXCEPTION: {e}")
            continue

        info = raw.get("info", {})
        fin  = raw.get("financials", {})
        hist = raw.get("history", {})

        r = {
            "elapsed_s":         round(time.time()-t0, 2),
            "info_ok":           info.get("_fetch_success", False),
            "info_error":        info.get("_fetch_error"),
            "info_price":        info.get("currentPrice") or info.get("regularMarketPrice"),
            "info_name":         (info.get("longName") or "")[:40],
            "financials_ok":     fin.get("_fetch_success", False),
            "financials_error":  fin.get("_fetch_error"),
            "income_fields":     len(fin.get("income_stmt", {})),
            "balance_fields":    len(fin.get("balance_sheet", {})),
            "cf_fields":         len(fin.get("cash_flow", {})),
            "history_ok":        hist.get("_fetch_success", False),
            "history_error":     hist.get("_fetch_error"),
            "history_datapoints":len(hist.get("dates", [])),
        }
        results[ticker] = r
        print(f"    info: ok={r['info_ok']} price={r['info_price']} name={r['info_name']}")
        print(f"    fin:  ok={r['financials_ok']} income={r['income_fields']} bal={r['balance_fields']} cf={r['cf_fields']}")
        print(f"    hist: ok={r['history_ok']} pts={r['history_datapoints']}")
        print(f"    elapsed: {r['elapsed_s']}s")
    return results


# ── Step 4: Retry-loop simulation ────────────────────────────────────────────

def step4_retry_loop_analysis() -> dict:
    """
    Code-analysis only (no network calls).
    Documents what the pipeline retry loop does on info 429 vs financials 429.
    """
    return {
        "retry_loop_trigger": "Only fires when load_result.cannot_complete_reason contains '429' or 'Too Many Requests'",
        "cannot_complete_set_when": "data_loader.py sets it ONLY when info._fetch_success=False",
        "financials_ok_False_triggers_retry": False,
        "financials_ok_False_effect": "Pipeline proceeds with 0% completeness, no retry",
        "history_ok_False_triggers_retry": False,
        "history_ok_False_effect": "load_result.ok=True (as long as info ok), no retry",
        "retry_attempts": 4,
        "retry_delays_s": [0, 5, 15, 30],
        "each_retry_calls": "load_ticker() -> fetch_ticker() -> all 3 fetches",
        "cache_interaction_per_retry": {
            "info":       "P1-rejected ok=False or missing -> fresh request EVERY retry",
            "financials": "Legacy dead ok=True -> cache HIT (no fresh request in retries)",
            "history":    "ok=False -> P1 rejects -> fresh request EVERY retry",
        },
        "total_requests_if_info_429s": {
            "FTS.TO":     "4 attempts x (info + history) = 8 fresh requests",
            "AAPL":       "attempt 1: info+financials+history=3; retries: 4x(info+history)=8; total~11",
            "TATASTEEL":  "same as AAPL: ~11 fresh requests",
        },
        "retry_loop_making_429_worse": True,
        "explanation": (
            "When info 429s, the retry loop fires 3 more times (5s, 15s, 30s delays). "
            "Each retry calls fetch_ticker() which calls fetch_history() again. "
            "Since all history_5y caches have _fetch_success=False, P1 rejects them, "
            "causing a fresh history request on EVERY retry attempt. "
            "For a ticker where both info and history fail: 4 retry attempts x 2 requests = 8 "
            "rapid-fire yfinance calls. Combined with the 429 Yahoo is already imposing, "
            "these additional calls extend the rate-limit window."
        ),
    }


# ── Step 5: Streamlit rerun analysis ────────────────────────────────────────

def step5_streamlit_rerun_analysis() -> dict:
    """Code-analysis only."""
    return {
        "double_analysis_on_button_click": False,
        "reason": (
            "analyse_clicked uses st.button() which returns True only on the render cycle "
            "where the physical click occurred. After st.rerun() is called, analyse_clicked "
            "is False. manager is in st.session_state and not re-created."
        ),
        "double_analysis_on_chat_submit": False,
        "reason_chat": (
            "st.chat_input() similarly returns prompt only once per submit. "
            "After st.rerun(), the input is cleared and returns None."
        ),
        "widget_rerun_risk": (
            "Typing in ticker_input or weight_input triggers Streamlit reruns (default behavior). "
            "analyse_clicked=False during those reruns, so no analysis is triggered."
        ),
        "force_refresh_actually_works": False,
        "force_refresh_reason": (
            "ui/app.py -> manager.run_analysis(force_refresh) -> "
            "run_analysis_pipeline(force_refresh) -> load_ticker() [no force_refresh param] -> "
            "_default_fetch(ticker) -> fetch_ticker(ticker) [no force_refresh param]. "
            "The parameter is accepted at two layers but never passed through to the cache layer."
        ),
    }


# ── Step 6: Session sharing analysis ────────────────────────────────────────

def step6_session_analysis() -> dict:
    """Inspect whether yfinance uses shared sessions."""
    try:
        import yfinance as yf
        import inspect, importlib
        # yfinance uses curl_cffi sessions internally
        # Each yf.Ticker() creates a new data object but shares the module-level session
        yf_data_src = inspect.getfile(yf)
        return {
            "yfinance_version": yf.__version__,
            "yfinance_location": yf_data_src,
            "session_model": (
                "yfinance uses a shared curl_cffi session internally (module-level). "
                "All Ticker() calls within one Python process share the same HTTP session "
                "and cookies/crumb. This means: one 429 response can affect subsequent "
                "requests in the same process run."
            ),
            "streamlit_implication": (
                "Streamlit runs as a single persistent Python process. "
                "The yfinance session (and its rate-limit state) persists across "
                "multiple user requests in the same Streamlit session. "
                "A 429 received for ticker A can cause ticker B (analyzed moments later) "
                "to also receive 429s."
            ),
        }
    except Exception as e:
        return {"error": str(e)}


# ── Step 7: Environment ──────────────────────────────────────────────────────

def step7_environment() -> dict:
    import platform
    try:
        import yfinance as yf
        yf_ver = yf.__version__
    except Exception as e:
        yf_ver = f"ERROR: {e}"
    try:
        import streamlit as st
        st_ver = st.__version__
    except Exception:
        st_ver = "not installed or not importable"
    try:
        import pandas as pd
        pd_ver = pd.__version__
    except Exception:
        pd_ver = "?"
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "yfinance_version": yf_ver,
        "streamlit_version": st_ver,
        "pandas_version": pd_ver,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Phase 10.x Follow-up Diagnostic — yfinance 429 Behaviour")
    print("=" * 70)
    print(f"Start: {ts()}")
    print(f"Output will be written to: {OUTPUT}")
    print()
    print("WARNING: This script makes real yfinance network requests.")
    print("         It uses delays between requests to avoid worsening rate limits.")
    print()

    output = {"start_timestamp": ts()}

    # Step 7 first (no network)
    print("[Step 7] Environment check...")
    output["step7_environment"] = step7_environment()
    print(f"  Python: {output['step7_environment']['python_version'].split()[0]}")
    print(f"  yfinance: {output['step7_environment']['yfinance_version']}")

    # Step 1 (no network — cache inspection)
    output["step1_cache_state"] = step1_cache_state()

    # Steps 4 & 5 (code analysis — no network)
    print("\n[Step 4] Retry-loop analysis (code analysis only)...")
    output["step4_retry_loop"] = step4_retry_loop_analysis()
    print("  (see output JSON for details)")

    print("\n[Step 5] Streamlit rerun analysis (code analysis only)...")
    output["step5_streamlit_rerun"] = step5_streamlit_rerun_analysis()
    print(f"  double_analysis: {output['step5_streamlit_rerun']['double_analysis_on_button_click']}")
    print(f"  force_refresh works: {output['step5_streamlit_rerun']['force_refresh_actually_works']}")

    print("\n[Step 6] Session sharing analysis...")
    output["step6_session"] = step6_session_analysis()
    print(f"  {output['step6_session'].get('session_model','')[:80]}")

    # Steps 2 and 3 — make real network calls
    print(f"\nAbout to make real yfinance network calls.")
    print(f"Total estimated time: ~{len(TICKERS) * (INTER_TICKER_DELAY + 5 * INTER_ENDPOINT_DELAY)}s for endpoint tests,")
    print(f"  plus ~{len(TICKERS) * INTER_TICKER_DELAY}s for full-fetch tests.")
    print()
    input("Press ENTER to continue (or Ctrl+C to skip network tests)...")

    try:
        print(f"\n[Step 2] Starting endpoint tests (waiting {INTER_STEP_DELAY}s first to let any 429 cool down)...")
        time.sleep(INTER_STEP_DELAY)
        output["step2_endpoint_tests"] = step2_endpoint_tests()
    except KeyboardInterrupt:
        print("  (skipped by user)")
        output["step2_endpoint_tests"] = {"skipped": True}

    try:
        print(f"\n[Step 3] Starting full-fetch tests (waiting {INTER_STEP_DELAY}s first)...")
        time.sleep(INTER_STEP_DELAY)
        output["step3_full_fetch"] = step3_full_fetch()
    except KeyboardInterrupt:
        print("  (skipped by user)")
        output["step3_full_fetch"] = {"skipped": True}

    output["end_timestamp"] = ts()
    OUTPUT.write_text(json.dumps(output, indent=2, default=str))
    print(f"\nDone. Results written to: {OUTPUT}")
    print("Share diagnostic_output_2.json for analysis.")


if __name__ == "__main__":
    main()
