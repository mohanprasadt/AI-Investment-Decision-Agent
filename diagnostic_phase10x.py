#!/usr/bin/env python3
"""
Phase 10.x Diagnostic — yfinance Financial Statement Root-Cause Investigation
Runs on Windows in the project's Python environment.
Output: diagnostic_output.json  (same folder as this script)

DO NOT MODIFY application code. This is a read-only investigation.
"""

import json
import sys
import os
import time
import traceback
import subprocess
import logging
import io
from datetime import datetime

output = {
    "timestamp": datetime.now().isoformat(),
    "step1_environment": {},
    "step2_tickers": {},
    "step3_version_check": {},
    "step4_raw_inspection": {},
    "step5_itcns_fresh": {},
}

print("=" * 60)
print("Phase 10.x Diagnostic")
print("=" * 60)

# ─── STEP 1: Environment ──────────────────────────────────────────────────────
print("\n[STEP 1] Capturing environment...")
env = {}
env["python_version"] = sys.version
env["python_executable"] = sys.executable
env["platform"] = sys.platform
env["cwd"] = os.getcwd()

try:
    import yfinance as yf
    env["yfinance_version"] = yf.__version__
except Exception as e:
    env["yfinance_version"] = f"IMPORT ERROR: {e}"

try:
    import pandas as pd
    env["pandas_version"] = pd.__version__
except Exception as e:
    env["pandas_version"] = f"ERROR: {e}"

try:
    import requests
    env["requests_version"] = requests.__version__
except Exception as e:
    env["requests_version"] = f"not available: {e}"

try:
    import httpx
    env["httpx_version"] = httpx.__version__
except Exception:
    env["httpx_version"] = "not installed"

# Which streamlit?
try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "show", "yfinance", "streamlit", "pandas"],
        capture_output=True, text=True, timeout=30
    )
    env["pip_show"] = result.stdout.strip()
except Exception as e:
    env["pip_show"] = f"ERROR: {e}"

output["step1_environment"] = env
print(f"  Python: {env['python_version'].split()[0]}")
print(f"  Executable: {env['python_executable']}")
print(f"  yfinance: {env['yfinance_version']}")
print(f"  pandas: {env['pandas_version']}")

# ─── STEP 2: Ticker tests ─────────────────────────────────────────────────────
print("\n[STEP 2] Testing tickers (no caching - fresh yfinance calls)...")
TICKERS = ["ENB.TO", "MSFT", "FTS.TO", "ITC.NS", "CNQ.TO"]

for sym in TICKERS:
    print(f"\n  Testing {sym}...")
    r = {
        "ticker": sym,
        "info": {"keys": 0, "price": None, "name": "", "error": None},
        "income_stmt": {"rows": 0, "cols": 0, "col_names": [], "index_names": [], "error": None},
        "balance_sheet": {"rows": 0, "error": None},
        "cash_flow": {"rows": 0, "error": None},
        "history_1mo": {"rows": 0, "last_close": None, "error": None},
    }

    try:
        t = yf.Ticker(sym)

        # --- info ---
        try:
            info = t.info or {}
            r["info"]["keys"] = len(info)
            r["info"]["price"] = info.get("currentPrice") or info.get("regularMarketPrice")
            r["info"]["name"] = info.get("longName") or info.get("shortName", "")
        except Exception as e:
            r["info"]["error"] = str(e)
        print(f"    info: {r['info']['keys']} keys, price={r['info']['price']}, error={r['info']['error']}")
        time.sleep(1)

        # --- income statement ---
        # Try both old (.financials) and new (.income_stmt) API
        try:
            income = None
            income_source = None
            # Try newer API first
            try:
                income = t.income_stmt
                income_source = "income_stmt"
            except AttributeError:
                pass
            # Fall back to .financials
            if income is None or (hasattr(income, 'empty') and income.empty):
                income = t.financials
                income_source = "financials"

            if income is not None and not income.empty:
                r["income_stmt"]["rows"] = len(income)
                r["income_stmt"]["cols"] = len(income.columns)
                r["income_stmt"]["col_names"] = [str(c)[:20] for c in income.columns[:4]]
                r["income_stmt"]["index_names"] = [str(i) for i in income.index[:5].tolist()]
                r["income_stmt"]["source"] = income_source
            else:
                r["income_stmt"]["empty"] = True
                r["income_stmt"]["source"] = income_source
        except Exception as e:
            r["income_stmt"]["error"] = str(e)
            r["income_stmt"]["traceback"] = traceback.format_exc()[-500:]
        print(f"    income_stmt: {r['income_stmt']['rows']} rows, error={r['income_stmt'].get('error')}")
        time.sleep(1)

        # --- balance sheet ---
        try:
            bal = t.balance_sheet
            if bal is not None and not bal.empty:
                r["balance_sheet"]["rows"] = len(bal)
                r["balance_sheet"]["cols"] = len(bal.columns)
        except Exception as e:
            r["balance_sheet"]["error"] = str(e)
        print(f"    balance_sheet: {r['balance_sheet']['rows']} rows, error={r['balance_sheet'].get('error')}")
        time.sleep(1)

        # --- cash flow ---
        try:
            cf = t.cashflow
            if cf is not None and not cf.empty:
                r["cash_flow"]["rows"] = len(cf)
                r["cash_flow"]["cols"] = len(cf.columns)
        except Exception as e:
            r["cash_flow"]["error"] = str(e)
        print(f"    cash_flow: {r['cash_flow']['rows']} rows, error={r['cash_flow'].get('error')}")
        time.sleep(1)

        # --- history (1 month only — don't hammer) ---
        try:
            hist = t.history(period="1mo")
            if hist is not None and not hist.empty:
                r["history_1mo"]["rows"] = len(hist)
                r["history_1mo"]["last_close"] = float(hist["Close"].iloc[-1])
        except Exception as e:
            r["history_1mo"]["error"] = str(e)
        print(f"    history(1mo): {r['history_1mo']['rows']} rows, error={r['history_1mo'].get('error')}")

    except Exception as e:
        r["outer_error"] = str(e)
        print(f"    OUTER ERROR: {e}")

    output["step2_tickers"][sym] = r
    time.sleep(3)   # pause between tickers

# ─── STEP 3: Check available yfinance versions ───────────────────────────────
print("\n[STEP 3] Checking available yfinance versions...")
try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "index", "versions", "yfinance"],
        capture_output=True, text=True, timeout=60
    )
    output["step3_version_check"]["pip_index"] = result.stdout.strip() or result.stderr.strip()
except Exception as e:
    try:
        # Fallback: pip install with impossible version to see what's available
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "yfinance==0.0.0"],
            capture_output=True, text=True, timeout=60
        )
        output["step3_version_check"]["available"] = result.stderr.strip()
    except Exception as e2:
        output["step3_version_check"]["error"] = f"{e}; {e2}"
print(f"  Result: {str(output['step3_version_check'])[:200]}")

# ─── STEP 4: yfinance debug log inspection ───────────────────────────────────
print("\n[STEP 4] Enabling yfinance debug logging for ENB.TO financials...")
try:
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)
    for logger_name in ["yfinance", "yfinance.base", "yfinance.utils", "yfinance.scrapers"]:
        lg = logging.getLogger(logger_name)
        lg.addHandler(handler)
        lg.setLevel(logging.DEBUG)

    # Fresh Ticker (no cache from prior calls — yfinance itself has no disk cache by default)
    t_debug = yf.Ticker("ENB.TO")
    income_debug = None
    try:
        income_debug = t_debug.income_stmt
    except AttributeError:
        try:
            income_debug = t_debug.financials
        except Exception as e2:
            output["step4_raw_inspection"]["financials_error"] = str(e2)

    log_text = log_capture.getvalue()
    output["step4_raw_inspection"]["debug_log"] = log_text[:3000]
    output["step4_raw_inspection"]["income_rows"] = (
        len(income_debug) if income_debug is not None and not income_debug.empty else 0
    )

    # Try to inspect what yfinance sends internally
    inspect_info = {}
    # Check _data attribute (yfinance >= 0.2.x)
    for attr in ["_data", "_scraper", "_financials", "_base", "_fundamentals"]:
        if hasattr(t_debug, attr):
            inspect_info[attr] = str(type(getattr(t_debug, attr)))
    output["step4_raw_inspection"]["ticker_attrs"] = inspect_info

    # Check if there's a cached response we can read
    if hasattr(t_debug, '_data') and hasattr(t_debug._data, '_history'):
        output["step4_raw_inspection"]["data_history_type"] = str(type(t_debug._data._history))

    print(f"  Debug log captured: {len(log_text)} chars")
    print(f"  income_rows after debug fetch: {output['step4_raw_inspection']['income_rows']}")

    # Clean up handlers
    for logger_name in ["yfinance", "yfinance.base", "yfinance.utils", "yfinance.scrapers"]:
        lg = logging.getLogger(logger_name)
        lg.removeHandler(handler)

except Exception as e:
    output["step4_raw_inspection"]["error"] = str(e)
    output["step4_raw_inspection"]["traceback"] = traceback.format_exc()
    print(f"  ERROR: {e}")

time.sleep(2)

# ─── STEP 5: ITC.NS fresh test ───────────────────────────────────────────────
print("\n[STEP 5] Testing ITC.NS fresh (not from project cache)...")
try:
    t_itc = yf.Ticker("ITC.NS")
    itc_result = {"income_rows": 0, "balance_rows": 0, "cf_rows": 0, "error": None}

    try:
        income_itc = None
        try:
            income_itc = t_itc.income_stmt
        except AttributeError:
            income_itc = t_itc.financials
        itc_result["income_rows"] = len(income_itc) if income_itc is not None and not income_itc.empty else 0
    except Exception as e:
        itc_result["income_error"] = str(e)

    time.sleep(1)
    try:
        bal_itc = t_itc.balance_sheet
        itc_result["balance_rows"] = len(bal_itc) if bal_itc is not None and not bal_itc.empty else 0
    except Exception as e:
        itc_result["balance_error"] = str(e)

    time.sleep(1)
    try:
        cf_itc = t_itc.cashflow
        itc_result["cf_rows"] = len(cf_itc) if cf_itc is not None and not cf_itc.empty else 0
    except Exception as e:
        itc_result["cf_error"] = str(e)

    output["step5_itcns_fresh"] = itc_result
    print(f"  ITC.NS fresh: income={itc_result['income_rows']}, balance={itc_result['balance_rows']}, cf={itc_result['cf_rows']}")

except Exception as e:
    output["step5_itcns_fresh"]["error"] = str(e)
    print(f"  ERROR: {e}")

# ─── Write output ────────────────────────────────────────────────────────────
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diagnostic_output.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, default=str)

print(f"\n{'=' * 60}")
print(f"Diagnostic complete.")
print(f"Output: {out_path}")
print(f"{'=' * 60}")
