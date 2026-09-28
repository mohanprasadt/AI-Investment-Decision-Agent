# Phase 10.x — P0/P1 Implementation Report

**Date:** 2026-08-15  
**Scope:** `data/ingestion/fetcher.py` — two targeted bug fixes (P0, P1)  
**Status:** Complete — all tests passing, no Git commit

---

## 1. Problem Statement

After Phase 10, the Streamlit UI successfully ran analyses for ITC.NS but returned
`CANNOT_COMPLETE_LIVE_ANALYSIS` errors for TSX tickers (ENB.TO, FTS.TO, CNQ.TO) and
MSFT. Root-cause investigation (Phase 10.x, classified as "D: trigger + amplifier")
confirmed two bugs in `fetcher.py` that compounded each other:

**Bug A (amplifier — P0 target):** `fetch_financials()` unconditionally set
`_fetch_success = True` and called `_save_cache()` even when all three financial
statement DataFrames were empty. This cached a "dead" result for 48 hours.

**Bug B (amplifier — P1 target):** `_load_cache()` served any cache entry within TTL
regardless of its `_fetch_success` value. A cached `_fetch_success=False` entry was
indistinguishable from a successful one, blocking retries for the full 48-hour TTL.

**Root trigger (Yahoo Finance rate-limiting):** The financials endpoint
(`query2.finance.yahoo.com/ws/fundamentals-timeseries/...`) is rate-limited
independently of the info/history endpoints. When rate-limited, yfinance silently
catches the error inside `_create_financials_table()` and returns an empty DataFrame
rather than raising. Bug A then cached this empty result, and Bug B prevented the
retry that would otherwise have succeeded on the next request.

Diagnostic confirmed all five tickers return full financial data on fresh yfinance
calls from the user's Windows environment (Python 3.14.6, yfinance 1.5.2).

---

## 2. Changes Made

Exactly two changes were made to `data/ingestion/fetcher.py`. No other files were
modified. No Git commit was made.

### P0 — `fetch_financials()`: detect all-empty result, do not cache

**Location:** After the three `df_to_dict()` calls that populate `income_stmt`,
`balance_sheet`, and `cash_flow`, before setting `_fetch_success = True`.

**Logic added:**
```python
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
```

**Key design decisions:**
- **Partial data is still success.** If at least one of the three statements is
  non-empty, `_fetch_success = True` and the result is cached. This preserves
  legitimate partial-data behavior and was explicitly required by the brief.
- **The existing exception path is unchanged.** A yfinance exception still sets
  `_fetch_error` and returns without caching — the new check adds a parallel path
  for the silent-empty case.
- **`_fetch_success` starts as `False` in `result`.** The early return on all-empty
  leaves it `False` without an extra assignment.

### P1 — `_load_cache()`: treat `_fetch_success=False` as cache miss

**Location:** After the TTL age check, before returning the cached dict.

**Logic added:**
```python
if not cached.get("_fetch_success", True):
    log.debug(
        f"Cache miss (prior failed fetch) for {ticker}/{data_type} "
        "— will retry fetch"
    )
    return None
```

**Key design decisions:**
- **Default is `True` for backward compatibility.** Old cache entries that predate
  the `_fetch_success` key are treated as successful hits (they were written by
  a successful fetch path that simply didn't record the field). This prevents
  a full cache-miss storm on first deployment.
- **Applies to all data types.** The same `_load_cache()` function serves `info`,
  `financials`, and `history_*` data types. P1 fixes the cache-miss behavior for
  all of them uniformly, including the pre-existing `fetch_history()` bug where
  `_save_cache()` was called even on empty history (Bug B already covers that).
- **No disk write on cache miss.** Returning `None` causes the caller to retry
  yfinance. The stale false-entry file remains on disk but is now transparently
  skipped on every read until it expires by TTL.

---

## 3. Partial-Data Behavior: Unchanged

The brief required: *"Do not assume that one individual statement being empty
necessarily means the entire fetch failed unless the existing design already requires
all three."*

P0 uses `and not` across all three statements — all three must be empty to trigger
the failure path. A single non-empty statement makes the condition false and
execution falls through to `_fetch_success = True` and `_save_cache()`.

This is verified by three dedicated test cases (income-only, balance-only,
cashflow-only) all asserting `_fetch_success = True`.

---

## 4. Behaviors Explicitly Preserved

| Behavior | Preserved? |
|---|---|
| `fetch_info()` exception path: no cache write | ✓ Unchanged (not touched) |
| `fetch_history()` exception path: no cache write | ✓ Unchanged |
| `fetch_financials()` exception path (yfinance raises) | ✓ Unchanged — exception still caught, `_fetch_error` set, no cache |
| Partial financial data (≥1 statement non-empty) → success | ✓ New P0 check only fires on all-three-empty |
| ITC.NS full-data path → cached, second call uses cache | ✓ Verified by test |
| TTL expiry: expired successful cache → None | ✓ Unchanged |
| Old cache entries without `_fetch_success` key → still served | ✓ Default `True` in `cached.get("_fetch_success", True)` |
| 429 retry logic in `pipeline.py` | ✓ Not touched; P1 returning `None` causes `_load_cache` miss which allows the pipeline retry loop to fire naturally |

---

## 5. Test Coverage Added

**New file:** `tests/test_fetcher_p0_p1.py`  
**Tests:** 21 test cases across 6 test classes

| Class | Cases | What it covers |
|---|---|---|
| `TestP0AllEmptyIsFailed` | 3 | All-empty → `_fetch_success=False`, `_fetch_error` set, no cache file |
| `TestP0ValidDataCached` | 4 | Full data → success, cache file written, content correct, second call uses cache |
| `TestP0PartialData` | 4 | Income-only, balance-only, cashflow-only all yield `_fetch_success=True` and are cached |
| `TestP0ExceptionPath` | 2 | yfinance raises → failure returned, not cached (existing behavior) |
| `TestP1CacheMissOnFailure` | 6 | `_fetch_success=False` → None; True → returned; expired → None; missing file → None; missing key → backward-compat |
| `TestP0P1Integration` | 2 | Failed fetch + retry returns real data on second call; pre-existing dead `_fetch_success=False` file triggers fresh yfinance call |

All tests use `unittest.mock.patch` to mock `yf.Ticker` (no network calls) and
`monkeypatch` to redirect `CACHE_DIR` to an isolated `tmp_path` (no interference
with the real `data/cache/` directory).

---

## 6. Test Results

### New fetcher tests

```
tests/test_fetcher_p0_p1.py — 21 passed in 9.22s
```

### Phase 10 regression

```
tests/test_phase10_conversation.py + tests/test_phase10_ui.py — 64 passed in 3.62s
```

### Full suite

| Metric | Before Phase 10.x | After Phase 10.x |
|---|---|---|
| Passing | 1,135 | **1,156** |
| Skipped | 1 | 1 |
| Pre-existing errors | 3 | 3 |
| New failures | — | **0** |

**Net new tests added: +21**

The 3 pre-existing errors are helper functions named `test()` inside
`test_calculations.py`, `test_ingestion.py`, and `test_quality_engine.py` that pytest
mistakenly collects as test functions. These existed before this phase and are
unrelated to the changes here.

---

## 7. Validation Against Five Tickers

Validation was performed via the diagnostic script (`diagnostic_phase10x.py`) run on
the user's Windows machine (Python 3.14.6, yfinance 1.5.2), which confirmed all five
tickers return full financial data on fresh yfinance calls. The P0/P1 fixes ensure
that a rate-limit event during one session cannot poison the cache and block those
successful fresh calls for the 48-hour TTL.

| Ticker | Fresh yfinance data | P0 protects against caching empty | P1 clears dead cache entries |
|---|---|---|---|
| ENB.TO | 53 income rows, 89 balance rows, 67 CF rows | ✓ | ✓ |
| MSFT | 47 income rows, 79 balance rows, 59 CF rows | ✓ | ✓ |
| FTS.TO | 50 income rows, 87 balance rows, 57 CF rows | ✓ | ✓ |
| ITC.NS | 53 income rows, 82 balance rows, 52 CF rows | ✓ (was working) | ✓ |
| CNQ.TO | 46 income rows, 60 balance rows, 49 CF rows | ✓ | ✓ |

---

## 8. Dead Cache Entries in `data/cache/`

Any existing dead cache entries written before this fix (with `_fetch_success=False`,
or with `_fetch_success=True` but all-empty data) will be transparently handled:

- `_fetch_success=False` entries → P1 treats as cache miss on next read; fresh fetch
  attempted automatically.
- `_fetch_success=True` / all-empty entries (old bug state) → P1 does not catch
  these (it trusts the `True` flag). These will be served once more, but will expire
  at their 48h TTL. After that, P0 ensures any replacement fetch is stored correctly.

If immediate correction is needed, running `clear_cache()` or deleting `data/cache/`
files for the affected tickers will force a clean re-fetch.

---

## 9. What Was Not Changed

Per the explicit constraints in the Phase 10.x brief:

- **`fetch_history()` Bug B** (calls `_save_cache()` even on empty history): not
  modified. P1 now catches these on the read side, so the impact is mitigated.
  A future P2 could fix the write side.
- **`force_refresh` not propagated** from `pipeline.py` to `load_ticker()`: not
  modified (P3 — not authorized in this phase).
- **yfinance not upgraded** from 1.5.2 to 1.6.0: not performed.
- **`data/cache/` files not deleted**: existing cache files left intact.
- **No Git commit made.**
- **No other files modified** outside `data/ingestion/fetcher.py` and
  `tests/test_fetcher_p0_p1.py`.

---

## 10. Recommended Validation Steps

After deploying, run the following on the Windows machine to confirm the fix works
end-to-end:

1. Delete or rename `data/cache/` entries for ENB.TO, FTS.TO, CNQ.TO, MSFT
   (to force a clean fetch):
   ```
   del data\cache\ENB_TO_financials.json
   del data\cache\FTS_TO_financials.json
   del data\cache\CNQ_TO_financials.json
   del data\cache\MSFT_financials.json
   ```

2. Start the Streamlit app and request analysis for ENB.TO (or any TSX ticker).

3. Verify `_fetch_success = True` in the resulting cache file:
   ```
   python -c "import json; d=json.load(open('data/cache/ENB_TO_financials.json')); print(d['_fetch_success'], len(d['income_stmt']), 'fields')"
   ```

4. Run the analysis again immediately — confirm it uses the cache (no duplicate
   yfinance call, fast response).

5. If a 429 is still encountered during the first fresh fetch, the pipeline's retry
   logic (delays of 5, 15, 30 s in `pipeline.py`) will retry. On success the result
   will now be correctly cached for subsequent requests.
