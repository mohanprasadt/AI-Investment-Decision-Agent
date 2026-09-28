"""
Phase 10.x — Cold-Cache Request-Burst Hypothesis Confirmation
=============================================================
Run ONLY on the Windows machine (not sandbox — no network there).

Usage:
    python diagnostic_phase10x_4.py

Output:
    diagnostic_output_4.json

What this tests
---------------
Scenario A — back-to-back cold fetches (no delay between tickers):
    fetch_ticker("FTS.TO")    → immediately →   fetch_ticker("TATASTEEL.NS")

Scenario B — spaced cold fetches (~35 seconds between tickers):
    fetch_ticker("FTS.TO")    → sleep 35s  →   fetch_ticker("TATASTEEL.NS")

Each scenario runs in a fresh subprocess so the YfData singleton starts
clean and the cookie strategy is in its default state.  The disk cache for
FTS.TO and TATASTEEL.NS is cleared before EACH scenario.

This is equivalent to two back-to-back Streamlit analyses because:
  • run_analysis_pipeline() calls load_ticker() → fetch_ticker() as step 1.
  • The research/valuation/decision steps that follow make NO Yahoo requests.
  • The singleton cookie state in a real Streamlit session is warm (cookies.db
    is present) — same as here.

Note: the cookies.db at ~/.cache/py-yfinance/ is NOT touched.  Only the
application-level data/cache/ files for the two test tickers are cleared.
"""

import json
import os
import pathlib
import subprocess
import sys
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = pathlib.Path(__file__).parent
CACHE_DIR = ROOT / "data" / "cache"
OUTPUT_FILE = ROOT / "diagnostic_output_4.json"

TICKERS = ["FTS.TO", "TATASTEEL.NS"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_path(ticker: str, suffix: str) -> pathlib.Path:
    safe = ticker.replace(".", "_").replace("/", "_")
    return CACHE_DIR / f"{safe}_{suffix}.json"


def _clear_test_cache():
    """Delete disk-cache entries for the two test tickers only."""
    cleared = []
    for ticker in TICKERS:
        for suffix in ["info", "financials", "history_5y"]:
            p = _cache_path(ticker, suffix)
            if p.exists():
                p.unlink()
                cleared.append(p.name)
    if cleared:
        print(f"  Cache cleared: {cleared}")
    else:
        print("  Cache already clear for test tickers.")


def _run_scenario(inter_ticker_sleep: float) -> dict:
    """
    Run both tickers in a FRESH subprocess.  Returns the parsed result dict.

    Using a subprocess gives each scenario a clean YfData singleton (fresh
    cookie strategy, no in-process state from prior yfinance calls).
    """
    # Write the scenario runner to a temp script
    runner_src = f"""
import json, logging, pathlib, sys, time, traceback
from datetime import datetime, timezone

ROOT = pathlib.Path(r"{ROOT}")
sys.path.insert(0, str(ROOT))

# Suppress all logging except what we capture explicitly
logging.basicConfig(level=logging.WARNING)

# ── HTTP request counter ──────────────────────────────────────────────────

class _RequestCounter(logging.Handler):
    def __init__(self):
        super().__init__()
        self.urls = []
    def emit(self, record):
        msg = record.getMessage()
        if msg.startswith("url="):
            self.urls.append(msg[4:].strip())

def _attach():
    c = _RequestCounter()
    c.setLevel(logging.DEBUG)
    yf_log = logging.getLogger("yfinance")
    yf_log.setLevel(logging.DEBUG)
    yf_log.addHandler(c)
    return c

def _detach(c):
    logging.getLogger("yfinance").removeHandler(c)

# ── Retry-activation capture ──────────────────────────────────────────────

class _RetryCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.retries = []
    def emit(self, record):
        msg = record.getMessage()
        if "Rate-limited (429)" in msg or "retrying in" in msg.lower():
            self.retries.append(msg)

def _attach_retry():
    c = _RetryCapture()
    c.setLevel(logging.INFO)
    pipe_log = logging.getLogger("analytics.agent.pipeline")
    pipe_log.setLevel(logging.INFO)
    pipe_log.addHandler(c)
    # also catch root logger messages from pipeline
    root_log = logging.getLogger()
    root_log.setLevel(logging.INFO)
    root_log.addHandler(c)
    return c

# ── Per-ticker fetch ──────────────────────────────────────────────────────

TICKERS = {json.dumps(TICKERS)}

results = []

retry_cap = _attach_retry()

for i, ticker in enumerate(TICKERS):
    if i > 0 and {inter_ticker_sleep} > 0:
        print(f"  [runner] sleeping {inter_ticker_sleep}s before next ticker...", flush=True)
        time.sleep({inter_ticker_sleep})

    from data.ingestion.fetcher import fetch_ticker, _cache_path

    counter = _attach()
    t_start = time.monotonic()
    row = {{
        "ticker": ticker,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "info_fetch_success": None,
        "info_fetch_error": None,
        "financials_fetch_success": None,
        "financials_fetch_error": None,
        "history_fetch_success": None,
        "history_fetch_error": None,
        "load_ok": None,
        "cannot_complete_reason": None,
        "data_completeness_pct": None,
        "http_requests": 0,
        "urls": [],
        "elapsed_s": 0,
        "error": None,
    }}

    try:
        raw = fetch_ticker(ticker, force_refresh=True)

        row["info_fetch_success"] = raw["info"].get("_fetch_success")
        row["info_fetch_error"] = raw["info"].get("_fetch_error")
        row["financials_fetch_success"] = raw["financials"].get("_fetch_success")
        row["financials_fetch_error"] = raw["financials"].get("_fetch_error")
        row["history_fetch_success"] = raw["history"].get("_fetch_success")
        row["history_fetch_error"] = raw["history"].get("_fetch_error")

        # Run through load_ticker for completeness/load_ok
        from analytics.agent.data_loader import load_ticker
        from datetime import datetime as _dt
        result = load_ticker(ticker=ticker,
                             analysis_date=_dt.utcnow().strftime("%Y-%m-%d"))
        row["load_ok"] = result.ok
        row["cannot_complete_reason"] = result.cannot_complete_reason or None
        row["data_completeness_pct"] = result.data_completeness_pct

    except Exception as e:
        row["error"] = f"{{type(e).__name__}}: {{e}}\\n{{traceback.format_exc()}}"
    finally:
        _detach(counter)
        row["http_requests"] = len(counter.urls)
        row["urls"] = counter.urls
        row["elapsed_s"] = round(time.monotonic() - t_start, 2)

    got_429 = (
        bool(row["info_fetch_error"] and "429" in str(row["info_fetch_error"])) or
        bool(row["cannot_complete_reason"] and "429" in str(row["cannot_complete_reason"])) or
        bool(row["cannot_complete_reason"] and "Too Many" in str(row["cannot_complete_reason"]))
    )
    row["got_429"] = got_429

    status = "OK" if row["load_ok"] else ("429" if got_429 else "FAIL")
    print(
        f"  [runner] {{ticker:16s}} {{status:6s}}  "
        f"{{row['http_requests']:2d}} HTTP  "
        f"{{row['data_completeness_pct']}}% complete  "
        f"{{row['elapsed_s']}}s",
        flush=True
    )

    results.append(row)

output = {{
    "inter_ticker_sleep_s": {inter_ticker_sleep},
    "retries_fired": retry_cap.retries,
    "retry_activated": bool(retry_cap.retries),
    "rows": results,
    "total_http_requests": sum(r["http_requests"] for r in results),
    "any_429": any(r.get("got_429") for r in results),
    "all_load_ok": all(r.get("load_ok") for r in results),
}}

print(json.dumps(output))
"""

    tmp = ROOT / "_burst_runner.py"
    tmp.write_text(runner_src, encoding="utf-8")

    try:
        proc = subprocess.run(
            [sys.executable, str(tmp)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=300,
        )
        # Extract the last JSON line from stdout
        lines = proc.stdout.strip().splitlines()
        print(proc.stdout.rstrip())
        if proc.stderr.strip():
            print("  STDERR:", proc.stderr[:500])

        result_dict = None
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{"):
                try:
                    result_dict = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass

        if result_dict is None:
            result_dict = {
                "error": "Could not parse JSON from runner output",
                "stdout": proc.stdout[-500:],
                "stderr": proc.stderr[-200:],
                "returncode": proc.returncode,
            }
        return result_dict
    finally:
        if tmp.exists():
            tmp.unlink()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import yfinance as yf

    print()
    print("=" * 70)
    print("  PHASE 10.x — COLD-CACHE REQUEST-BURST CONFIRMATION")
    print("=" * 70)
    print(f"  Python: {sys.version.split()[0]}")
    print(f"  yfinance: {yf.__version__}")
    print(f"  Test tickers: {TICKERS}")
    print()
    print("  Each scenario runs in a fresh subprocess (clean singleton).")
    print("  Disk cache for test tickers is cleared before each scenario.")
    print()

    results = {
        "started": _now(),
        "env": {
            "python": sys.version,
            "yfinance": yf.__version__,
        },
        "scenarios": {}
    }

    # ── Scenario A — back-to-back (0s delay) ─────────────────────────────

    print("=" * 70)
    print("  SCENARIO A — back-to-back (0 seconds between tickers)")
    print("=" * 70)
    _clear_test_cache()
    print("  Starting Scenario A...", flush=True)
    t_a = time.monotonic()
    result_a = _run_scenario(inter_ticker_sleep=0)
    elapsed_a = round(time.monotonic() - t_a, 1)
    results["scenarios"]["A_burst"] = result_a
    results["scenarios"]["A_burst"]["scenario_elapsed_s"] = elapsed_a

    print()
    _a_label = "CONFIRMED 429" if result_a.get("any_429") else "NO 429 observed"
    print(f"  Scenario A result:  {_a_label}")
    print(f"  Total HTTP:         {result_a.get('total_http_requests', '?')}")
    print(f"  Retry activated:    {result_a.get('retry_activated', '?')}")
    print(f"  All load_ok:        {result_a.get('all_load_ok', '?')}")
    print(f"  Scenario duration:  {elapsed_a}s")

    # Wait for Yahoo rate-limit window to clear before Scenario B
    wait_between = 90
    print()
    print(f"  Waiting {wait_between}s for Yahoo rate-limit window to clear...")
    time.sleep(wait_between)

    # ── Scenario B — spaced (35s delay) ──────────────────────────────────

    print()
    print("=" * 70)
    print("  SCENARIO B — spaced (35 seconds between tickers)")
    print("=" * 70)
    _clear_test_cache()
    print("  Starting Scenario B...", flush=True)
    t_b = time.monotonic()
    result_b = _run_scenario(inter_ticker_sleep=35)
    elapsed_b = round(time.monotonic() - t_b, 1)
    results["scenarios"]["B_spaced"] = result_b
    results["scenarios"]["B_spaced"]["scenario_elapsed_s"] = elapsed_b

    print()
    _b_label = "429 observed (unexpected)" if result_b.get("any_429") else "All succeeded"
    print(f"  Scenario B result:  {_b_label}")
    print(f"  Total HTTP:         {result_b.get('total_http_requests', '?')}")
    print(f"  Retry activated:    {result_b.get('retry_activated', '?')}")
    print(f"  All load_ok:        {result_b.get('all_load_ok', '?')}")
    print(f"  Scenario duration:  {elapsed_b}s")

    # ── Summary ───────────────────────────────────────────────────────────

    print()
    print("=" * 70)
    print("  BURST HYPOTHESIS VERDICT")
    print("=" * 70)

    a_429 = result_a.get("any_429", False)
    b_ok  = result_b.get("all_load_ok", False)

    if a_429 and b_ok:
        verdict = "CONFIRMED"
        detail = (
            "Scenario A produced a 429; Scenario B succeeded. "
            "Cold analyses in rapid succession DO exceed Yahoo's rate limit."
        )
    elif not a_429 and b_ok:
        verdict = "NOT REPRODUCED"
        detail = (
            "Scenario A did NOT produce a 429 in this run. "
            "Yahoo's threshold may be higher than the burst rate tested, "
            "or the rate-limit window has already cleared from a prior session."
        )
    elif a_429 and not b_ok:
        verdict = "PARTIAL — both scenarios failed"
        detail = (
            "Scenario A 429'd as expected, but Scenario B also failed. "
            "Yahoo may still be rate-limiting from the burst. "
            "Consider re-running Scenario B after a longer wait."
        )
    else:
        verdict = "INCONCLUSIVE"
        detail = "Both scenarios failed without a clear 429 signal. Check error details."

    print(f"  Verdict: {verdict}")
    print(f"  Detail:  {detail}")

    results["verdict"] = verdict
    results["verdict_detail"] = detail
    results["finished"] = _now()

    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print()
    print(f"  Output saved: {OUTPUT_FILE}")
    print()


if __name__ == "__main__":
    main()
