# Phase 10.x Follow-up Diagnostic Report
## yfinance 429 Behaviour Across Multiple Tickers

**Date:** 2026-08-15  
**Status:** Diagnostic complete — root cause identified from code analysis + cache inspection  
**No production code was modified during this diagnostic.**

---

## A. Root Cause

There are **four overlapping problems**, not one. They interact and amplify each other.

### Problem 1 — Asymmetric cache coverage (primary cause of "why ENB works, others don't")

ENB.TO is the only ticker with a **valid `info` cache entry**. Every other ticker that fails lacks an info cache and must make a fresh yfinance request to Yahoo's info endpoint. That fresh request is the one that hits the rate limit.

| Ticker | info cache | financials cache | history cache |
|---|---|---|---|
| ENB.TO | **Valid** (1.9h, ok=True) | Legacy dead (ok=True, empty) | ok=False → P1 rejects |
| FTS.TO | **MISSING** → fresh request | Legacy dead (ok=True, empty) | ok=False → P1 rejects |
| AAPL | **MISSING** → fresh request | MISSING → fresh request | ok=False → P1 rejects |
| TATASTEEL.NS | **MISSING** → fresh request | MISSING → fresh request | ok=False → P1 rejects |

ENB.TO's info was cached ~1.9 hours ago from a Streamlit test run. Its financials cache was written by the pre-P0 buggy code (empty data, ok=True), which P1 cannot detect as bad — but P1 does not need to, because the financials cache is served as-is (no fresh request is made). Only 1 fresh yfinance request is needed for ENB.TO (history, which P1 correctly rejects). That request either succeeds or is absorbed by the retry before hitting the pipeline check.

For FTS.TO, AAPL, and TATASTEEL.NS: 2–3 fresh requests are needed on the first attempt. If any of those hits a 429, the retry loop fires and generates up to 8 additional requests (see Problem 3 below).

---

### Problem 2 — Legacy dead cache entries not caught by P0/P1

After the earlier Streamlit debugging sessions (before P0 was deployed), the pre-P0 bug wrote `_fetch_success=True` into cache files for empty financial statements. The current cache has:

- `ENB_TO_financials.json`: ok=True, income=0, balance=0, cf=0 (written ~2.4h ago by pre-P0 code)  
- `FTS_TO_financials.json`: ok=True, income=0, balance=0, cf=0 (written ~2.2h ago by pre-P0 code)  
- `MSFT_financials.json`: ok=True, income=0, balance=0, cf=0 (written ~2.3h ago by pre-P0 code)  
- `CNQ_TO_financials.json`: ok=True, income=0, balance=0, cf=0 (written ~143.6h ago)

P0 prevents new dead entries from being written. P1 rejects entries with `_fetch_success=False`. Neither touches these legacy entries because they have `_fetch_success=True`. They will continue to be served as "valid cache hits" (no fresh requests) for the rest of their 48-hour TTL — up to ~46 more hours for the 2h-old entries.

**Effect:** these tickers' financials are permanently producing 0% data_completeness analyses until the TTL expires or they are manually deleted. The pipeline does not abort on 0% completeness — it produces a WAIT_INSUFFICIENT_EVIDENCE result, which may look like success but is substantively hollow.

---

### Problem 3 — Retry loop amplification

The pipeline's 429 retry loop (`_RETRY_DELAYS = [5, 15, 30]`) is designed to help. Under current cache conditions, it amplifies the problem.

**How the retry loop works:**
```
for _attempt, _wait in enumerate([0] + [5, 15, 30]):
    load_result = load_ticker(ticker)   # → fetch_ticker() → fetch_info + fetch_financials + fetch_history
    if load_result.ok:
        break
    if "429" not in load_result.cannot_complete_reason:
        break
```

**Key constraints:**
- `load_result.ok` is False ONLY when `info._fetch_success=False`. Financials-empty and history-empty do not set `cannot_complete_reason`.
- When the retry loop fires (info 429), each retry calls `fetch_ticker()` which calls all three fetchers.
- `fetch_history()` checks P1: all current history caches have `_fetch_success=False` → P1 rejects all of them → every retry attempt makes a fresh history yfinance request.
- So each retry attempt = 1 info request + 1 history request (financials are cache-hit from legacy dead entry or cached ok=True).

**Total requests if info 429s:**

| Ticker | Attempt 1 | Retries (3×) | Total |
|---|---|---|---|
| FTS.TO | info + history = 2 | 3 × (info + history) = 6 | **8 fresh requests** |
| AAPL | info + financials + history = 3 | 3 × (info + history) = 6 | **9 fresh requests** |
| TATASTEEL.NS | info + financials + history = 3 | 3 × (info + history) = 6 | **9 fresh requests** |

These requests are spaced 5 s, 15 s, 30 s apart. But each one is a fresh call to Yahoo Finance — still within the rate-limit window. The retry loop, intended to recover from transient 429s, is instead making repeated calls that extend the rate-limit episode.

---

### Problem 4 — `fetch_history()` Bug B: always caches, even on empty result

This is the pre-existing bug identified in Phase 10.x but not fixed. `fetch_history()` always calls `_save_cache()` regardless of whether `hist.empty` is True:

```python
# fetcher.py fetch_history()
if hist is not None and not hist.empty:
    result["dates"] = ...
    result["_fetch_success"] = True
_save_cache(ticker, cache_key, result)   # ← called even when _fetch_success=False
```

All current `history_5y` entries are `ok=False, datapoints=0` — written by failed/empty history fetches. P1 correctly rejects them on read, forcing a fresh request. But the fresh request also fails (same rate limit) and writes another `ok=False` entry. The cycle repeats: every history fetch attempt creates a dead entry, P1 rejects it next time, another fresh request is made.

Without fixing Bug B, the history cache never accumulates good entries for any ticker that is currently 429-limited on history.

---

## B. Evidence

All evidence is from code analysis and cache inspection (no network calls were made during this diagnostic):

**Cache files inspected:** `data/cache/*.json` — 28 files total.

**Code files analysed:**
- `data/ingestion/fetcher.py` — fetch_info, fetch_financials, fetch_history, _load_cache
- `analytics/agent/pipeline.py` — retry loop logic
- `analytics/agent/data_loader.py` — cannot_complete_reason trigger
- `ui/app.py` — Streamlit rerun behaviour
- `conversation/manager.py` — run_analysis flow

**Key measurements from cache inspection:**
- ENB.TO info: age=1.9h, `_fetch_success=True`, valid → no fresh request needed
- All other target tickers: info missing or P1-rejected → fresh request required
- All `history_5y` entries except CNQ.TO: `_fetch_success=False`, P1-rejected → fresh requests required
- CNQ.TO history: age=143.5h, exceeds 24h TTL → also expired

**Exact code path for the "why retry makes it worse" finding:**  
`pipeline.py:133` — retry loop fires on `"429"` in `cannot_complete_reason`  
`data_loader.py:183` — `cannot_complete_reason` set when `info._fetch_success=False`  
`fetcher.py:179` — `_load_cache(ticker, "history_5y", 24)` → P1 rejects ok=False → returns None → fresh yfinance call on every retry attempt

---

## C. Why ENB.TO Works

ENB.TO has a valid `info` cache entry (age 1.9h, within 24h TTL, `_fetch_success=True`, price=70.61). `fetch_info()` returns a cache hit → no yfinance request. `fetch_financials()` returns a legacy dead cache hit (ok=True but empty — P1 does not catch ok=True entries) → no yfinance request. Only `fetch_history()` makes a fresh request (because its cache entry is P1-rejected). With only 1 fresh request, ENB.TO stays under the rate limit.

---

## D. Why FTS.TO, AAPL, TATASTEEL.NS Fail

FTS.TO has no `info` cache. AAPL and TATASTEEL.NS have no `info` or `financials` cache. All three require fresh info requests to Yahoo Finance. Yahoo Finance is currently rate-limiting on the info endpoint (or has a short-term rate-limit window still active from earlier debugging sessions). The fresh info request hits 429, which triggers the retry loop, which makes up to 8–9 additional requests per ticker — further exhausting the rate limit budget.

---

## E. Reproducibility Outside Streamlit

**Streamlit is not the cause.** Code analysis confirms:

1. No double-analysis on button click: `st.button()` returns True only on the render cycle where it was clicked. `st.rerun()` sets it to False.
2. No double-analysis from widget reruns: `analyse_clicked` guards the analysis call.
3. The Streamlit process is long-lived and shares a yfinance HTTP session across requests — but this means a 429 from one ticker can affect the next, which is a concern. However, this same effect would occur in a long-running CLI session too.

The same 429s would occur running `fetch_ticker("FTS.TO")` from the command line right now, because the rate limit is a Yahoo Finance server-side restriction, not an application-side or Streamlit-side issue.

The `diagnostic_phase10x_2.py` script tests this directly: Step 3 calls `fetch_ticker()` for each ticker from a plain Python process without Streamlit.

---

## F. Is the Retry Logic Helping or Hurting?

**Currently: net negative.** The retry loop was designed for transient 429s (a brief rate-limit window that clears in 5–30 seconds). Under the current conditions:

1. Yahoo Finance's rate limit window appears longer than 30 seconds (the sum of all retry delays).
2. The retry loop makes up to 9 fresh requests per failing ticker instead of giving up after 1.
3. Because all history caches are P1-rejected, every retry attempt includes a history request, doubling the request rate.
4. After the 4 attempts fail (~50 seconds of elapsed time), the error is finally returned. If the user then clicks Analyse again, another 4 attempts × 2 requests = 8 more requests are made immediately.

**However:** the retry loop is not wrong in principle. If Yahoo's rate limit cleared within the 30s window (as originally designed), it would work correctly. The problem is the combination of: (a) all history caches being dead (P1 side effect), and (b) Yahoo's current rate limit window being longer than the retry window.

---

## G. Exact Production Files and Functions Involved

| File | Function | Role |
|---|---|---|
| `data/ingestion/fetcher.py` | `_load_cache()` | P1 rejects ok=False entries — causes fresh history requests on every call |
| `data/ingestion/fetcher.py` | `fetch_history()` | Bug B: caches ok=False entries → triggers P1 rejections forever |
| `data/ingestion/fetcher.py` | `fetch_financials()` | P0 fixed (new dead entries not cached) — but legacy dead entries (ok=True, empty) remain |
| `analytics/agent/pipeline.py` | `run_analysis_pipeline()` | Retry loop amplifies 429s by making 2+ requests per retry |
| `analytics/agent/pipeline.py` | `run_analysis_pipeline()` | `force_refresh` parameter is silently dropped — never reaches fetcher.py |
| `analytics/agent/data_loader.py` | `load_ticker()` | No `force_refresh` param — cannot pass it through even if pipeline sent it |
| `analytics/agent/data_loader.py` | `_default_fetch()` | Calls `fetch_ticker(ticker)` without `force_refresh` |

---

## H. Recommended Fix Options (Ranked)

### P0 (Immediate, no code change) — Clear legacy dead cache entries manually

Delete the dead cache files that block good data. These are the entries with `_fetch_success=True` but empty financial data, and all the `_fetch_success=False` history entries. After deletion, the next analysis will make fresh yfinance requests — but wait 5–10 minutes first to let the rate limit cool down.

Files to delete (from `data/cache/`):
```
ENB_TO_financials.json   (ok=True but empty — legacy pre-P0)
FTS_TO_financials.json   (ok=True but empty — legacy pre-P0)
MSFT_financials.json     (ok=True but empty — legacy pre-P0)
CNQ_TO_financials.json   (ok=True but empty — legacy pre-P0, also 6 days old)
*_history_5y.json        (all ok=False — P1 will reject, wasting requests)
ENB_financials.json      (junk ticker — pre-P0 dead entry)
ENB_history_5y.json      (junk ticker)
OUT_financials.json      (junk ticker)
SHOW_financials.json     (junk ticker)
PRICE_*.json             (junk ticker)
COOK_*.json              (junk ticker)
DATA_*.json              (junk ticker)
LUNCH_*.json             (junk ticker)
```

After deletion, run one ticker at a time from the Streamlit UI with 2–3 minutes between each. This allows Yahoo's rate limit to reset between tickers.

**Risk:** None. These are cache files, not production data. Deleting them forces a fresh fetch on next analysis, which is exactly what we want.

### P1 (Code change, small — fix Bug B in fetch_history()) 

Fix `fetch_history()` to not call `_save_cache()` when `hist.empty`. Mirrors the fix already done for `fetch_financials()` in P0:

```python
# In fetch_history(), after the if/else block:
if not result["_fetch_success"]:
    log.warning(f"fetch_history: empty result for {ticker} — not caching")
    return result  # do NOT call _save_cache
_save_cache(ticker, cache_key, result)
time.sleep(0.3)
```

Without this, every history fetch failure writes a dead cache entry, P1 rejects it on the next read, another fresh request is made, which may also fail and write another dead entry — an infinite retry loop at the cache level.

**Risk:** Low. Same logic as P0. Partial results (where dates exists but is short) should still be treated as success and cached. The guard should only fire when `not result["_fetch_success"]`.

### P2 (Code change, medium — add pre-write validation to _save_cache())

Add a guard in `_save_cache()` itself that refuses to write entries with `_fetch_success=False`, as a defensive backstop regardless of which fetch function calls it:

```python
def _save_cache(ticker: str, data_type: str, data: dict) -> None:
    if not data.get("_fetch_success", False):
        log.debug(f"_save_cache: skipping write for failed fetch {ticker}/{data_type}")
        return
    ...
```

This is a belt-and-suspenders fix that catches any future fetch functions that forget to guard their own `_save_cache()` call (like `fetch_history()` currently does). It also protects against the legacy dead financials pattern if it ever resurfaces.

**Risk:** Very low. Any entry with `_fetch_success=False` is useless to cache (P1 rejects it immediately on read). Making the write itself a no-op is pure improvement.

### P3 (Code change, medium — wire force_refresh through the full call chain)

Connect the `force_refresh` parameter from the UI all the way to `fetch_ticker()`:

1. Add `force_refresh: bool = False` to `load_ticker()` in `data_loader.py`
2. Pass it to `_default_fetch()` → modify `_default_fetch()` to accept and pass it
3. In `pipeline.py`, pass `force_refresh=force_refresh` to `load_ticker()`

This makes the "Force refresh" checkbox in the UI actually bypass the cache — useful for testing and for recovering from legacy dead cache entries without manual file deletion.

**Risk:** Low. Requires touching `data_loader.py` and `pipeline.py`. Tests should be updated to cover the new parameter.

### P4 (Design change, larger — smarter retry strategy)

Instead of retrying by calling the full `load_ticker()` again (which re-calls all three fetchers), the retry should be targeted:
- Only retry the specific endpoint that failed (info or history), not all three.
- Check whether retry attempts are actually clearing the error before continuing.
- Implement exponential backoff that scales with Yahoo's actual rate-limit window (which appears to be >30s currently).

This is a larger change and should wait until the simpler fixes are validated.

---

## I. Is a Code Change Actually Required?

**Not immediately.** The highest-priority action (P0) requires no code change: delete the dead cache files and wait for the rate limit to clear. This will restore functionality for all four tickers.

Code changes (P1 through P4) prevent the problem from recurring. Without P1 (fixing `fetch_history()`), every history fetch failure will recreate a dead cache entry that P1 immediately rejects on the next read, continuing to generate fresh requests indefinitely. P1 is the most important code change.

---

## J. Recommended Next Test Before Implementation

**Before any code change:**

1. **Delete the dead cache files** listed in H.P0 above (from `data/cache/`).
2. **Wait 5 minutes** (no yfinance calls during this time — let Yahoo's rate limit window expire).
3. **Run one ticker from the CLI** (not Streamlit):
   ```
   python -c "from data.ingestion.fetcher import fetch_ticker; import json; r=fetch_ticker('FTS.TO'); print(json.dumps({k:v for k,v in r['info'].items() if not k.startswith('_') or k in ['_fetch_success','_fetch_error']}, indent=2, default=str)[:500])"
   ```
   Verify: `_fetch_success=True`, financial data populated.
4. **Wait 3 minutes**, then test AAPL, then TATASTEEL.NS — one at a time with 3-minute gaps.
5. If CLI tests pass cleanly, start the Streamlit app and test the same tickers one at a time with 2-minute gaps between each analysis.

If the CLI tests still return 429 after a 5-minute wait, the rate limit window is longer than expected. In that case, wait 15–30 minutes before retrying. Yahoo Finance's rate limit resets on a per-IP basis and typically clears within 15–30 minutes of no requests.

---

## Summary

| Finding | Detail |
|---|---|
| Root cause of ENB.TO working | Has valid info cache (1.9h). Only 1 fresh yfinance request needed. |
| Root cause of FTS.TO/AAPL/TATASTEEL.NS failing | No valid info cache. Fresh info request hits Yahoo 429. |
| Number of fresh requests per failing ticker | 2–3 on first attempt, up to 8–9 total with retries |
| P1 side effect | Correctly rejects bad history caches, but forces fresh history requests on every retry |
| Retry loop verdict | Amplifies rate limiting under current cache conditions |
| Streamlit double-analysis | Not happening (confirmed by code analysis) |
| Force refresh checkbox | Broken — parameter dropped before reaching fetcher.py |
| Legacy dead financials | ok=True but empty; P1 cannot catch; will persist 46+ more hours |
| Immediate fix | Delete dead cache files (no code change) + wait for rate limit to clear |
| Most important code fix | P1: fix fetch_history() to not cache failed/empty results (mirrors P0) |
