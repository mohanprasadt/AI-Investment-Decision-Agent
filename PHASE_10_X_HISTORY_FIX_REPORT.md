# Phase 10.x — History Fix Implementation Report

**Date:** 2026-08-15  
**Scope:** `data/ingestion/fetcher.py` (one change), `tests/test_fetcher_p0_p1.py` (tests added)  
**No Git commit. No analytics/ changes. No retry delays changed. No yfinance upgrade.**

---

## 1. Files Modified

| File | Type | Change |
|---|---|---|
| `data/ingestion/fetcher.py` | Production | `fetch_history()` — empty result no longer cached |
| `tests/test_fetcher_p0_p1.py` | Tests | 15 new history test cases added; `fetch_history` import added |

No other files were modified.

---

## 2. Exact Behaviour Changed

### `fetch_history()` — empty DataFrame no longer written to cache

**Before (Bug B — old behaviour):**
```python
        if hist is not None and not hist.empty:
            result["dates"] = [...]
            result["closes"] = [...]
            result["_fetch_success"] = True
        _save_cache(ticker, cache_key, result)   # ← called unconditionally
        time.sleep(0.3)
```

When `hist.empty` was True: `_fetch_success` stayed `False`, `dates=[]`, but `_save_cache()` was still called — writing a `_fetch_success=False` entry to disk. P1 then rejected it on the next read, forcing another fresh request. That fresh request also returned empty, wrote another dead entry. Infinite dead-cache cycle.

**After (fix — mirrors P0 pattern):**
```python
        if hist is not None and not hist.empty:
            result["dates"] = [...]
            result["closes"] = [...]
            result["_fetch_success"] = True
            _save_cache(ticker, cache_key, result)   # only on success
            time.sleep(0.3)
        else:
            result["_fetch_error"] = (
                "yfinance returned an empty history DataFrame. "
                "This typically indicates a Yahoo Finance rate-limit or data "
                "unavailability. Result not cached — next request will retry."
            )
            log.warning(f"fetch_history: empty result for {ticker} ({period}) — not caching")
```

When `hist.empty` is True: `_fetch_success=False`, `_fetch_error` set, `_save_cache()` NOT called, result returned immediately. Next request finds no cache file → clean miss → retries yfinance.

**Existing exception path: unchanged.** Exceptions still set `_fetch_error` and return without calling `_save_cache()`. This was already correct.

**Successful history: unchanged.** Non-empty DataFrame → `_fetch_success=True` → `_save_cache()` called → result cached for 24h TTL.

---

## 3. New Tests Added

File: `tests/test_fetcher_p0_p1.py`  
15 new test cases across 5 new classes (all mocked — no network calls):

| Class | Cases | What it covers |
|---|---|---|
| `TestHistoryEmptyNotCached` | 4 | Empty DataFrame → `_fetch_success=False`, error set, no cache file, empty lists |
| `TestHistorySuccessCached` | 5 | Valid DataFrame → success, dates/closes populated, cached, second call uses cache |
| `TestHistoryExceptionNotCached` | 2 | Exception → failure returned, no cache (existing behaviour verified) |
| `TestHistoryP1Interaction` | 2 | P1 still rejects pre-existing `ok=False` history; P1 serves valid history from cache |
| `TestHistoryRetryBehaviourAfterFix` | 2 | Empty→retry→success path; clean miss without force_refresh |

All 21 pre-existing tests (P0, P1, integration) continue to pass unchanged.

---

## 4. Test Results

```
tests/test_fetcher_p0_p1.py — 36 passed in 12.69s
  (21 pre-existing P0/P1 tests + 15 new history tests)

tests/test_phase10_conversation.py + tests/test_phase10_ui.py — 64 passed in 5.23s

Full suite:
  1171 passed, 1 skipped, 42 warnings, 3 errors, 12 subtests passed
  (3 errors are pre-existing helper-function collection errors — unrelated)
```

| Metric | After P0/P1 | After History Fix |
|---|---|---|
| Passing | 1,156 | **1,171** |
| New tests added | — | +15 |
| New failures | — | 0 |

---

## 5. Retry Amplification: Is It Resolved?

**Partially.** The dead-cache cycle that was the primary _structural_ amplifier is gone:

| Scenario | Before fix | After fix |
|---|---|---|
| Empty history result written to disk | Yes (ok=False) | **No** |
| P1 rejection on next read | Yes (forces fresh request) | No file → clean miss (same outcome, cleaner path) |
| Requests per retry attempt (info + history) | 2 | **2** (unchanged) |
| Total requests if all 4 attempts fail | 8 | **8** (unchanged) |

**The request count per retry is identical before and after the fix.** Retrying history on each attempt is correct and unavoidable — history is a required data component, and a prior failure does not mean the next attempt will also fail.

**What the fix eliminates:**
- Dead `ok=False` history files no longer accumulate on disk between sessions.
- After a successful retry, the cache is written immediately and used by all subsequent calls.
- The dead-cache → P1-reject → fresh-request → dead-cache loop is broken.

**What the fix cannot change:**  
If Yahoo Finance rate-limits for longer than the total retry window (~50 seconds combined), all 4 attempts will fail. That is a Yahoo-side constraint. The retry loop is working as designed within the application's control. No redesign of retry behaviour is warranted.

**Conclusion:** retry amplification is resolved at the structural level. The remaining request count (up to 8 for a persistently rate-limited ticker) is the correct minimum for the retry strategy as authorized.

---

## 6. Remaining `force_refresh` Defect

**The `force_refresh` UI checkbox does nothing.** The parameter is silently dropped before reaching the cache layer.

**Exact location where propagation is lost:**

```
analytics/agent/pipeline.py  line 142:
    load_result = load_ticker(ticker=ticker, analysis_date=_date)
    # ↑ force_refresh is accepted by run_analysis_pipeline() but NOT passed here
```

**Root cause chain:**

| Layer | Accepts force_refresh? | Passes it? |
|---|---|---|
| `ui/app.py` `_run_analysis()` | Yes | Yes → `manager.run_analysis()` |
| `conversation/manager.py` `run_analysis()` | Yes | Yes → `run_analysis_pipeline()` |
| `analytics/agent/pipeline.py` `run_analysis_pipeline()` | Yes | **NO** — dropped at `load_ticker()` call |
| `analytics/agent/data_loader.py` `load_ticker()` | **No param** | N/A |
| `analytics/agent/data_loader.py` `_default_fetch()` | **No param** | N/A |
| `data/ingestion/fetcher.py` `fetch_ticker()` | Yes | Never reached |

**Recommended correction (not implemented — for separate authorization):**

Three coordinated changes required:

1. `data_loader.py` — replace `_default_fetch` with a closure factory:
   ```python
   def _make_default_fetch(force_refresh: bool = False):
       def _fetch(ticker: str) -> Dict[str, Any]:
           from data.ingestion.fetcher import fetch_ticker
           return fetch_ticker(ticker, force_refresh=force_refresh)
       return _fetch
   ```
   Then change `load_ticker()` signature:
   ```python
   def load_ticker(ticker, analysis_date="", *, force_refresh=False,
                   _fetch_fn=None, _normalize_fn=_default_normalize):
       if _fetch_fn is None:
           _fetch_fn = _make_default_fetch(force_refresh)
   ```

2. `pipeline.py` — pass the parameter:
   ```python
   load_result = load_ticker(ticker=ticker, analysis_date=_date,
                             force_refresh=force_refresh)
   ```

**Complexity:** Medium. Two production files; injectable `_fetch_fn` interface changes (default shifts from a module-level function to `None`). Tests that inject `_fetch_fn` explicitly are unaffected. Tests that use the default path need verification. Recommend as a separate authorized change.

---

## 7. Legacy Cache Cleanup Required

The following cache files in `data/cache/` were written by the pre-P0 buggy code. They have `_fetch_success=True` but zero financial data rows. P0 prevents new such files; P1 cannot detect them (both check for `False`, these are `True`). They will silently produce 0%-completeness analyses until their 48h TTL expires:

**Financial (ok=True, empty — legacy pre-P0 entries):**
```
data/cache/ENB_TO_financials.json    (age ~4h, ~44h remaining)
data/cache/FTS_TO_financials.json    (age ~4h, ~44h remaining)
data/cache/MSFT_financials.json      (age ~4h, ~44h remaining)
data/cache/CNQ_TO_financials.json    (age ~6 days, expired — next read will re-fetch)
```

**History (ok=False — will be rejected by P1, forcing fresh requests):**  
After the history fix, empty history results are no longer written. However, the existing `ok=False` history files created before this fix remain on disk and will still be P1-rejected on first read. They can be deleted without consequence:
```
data/cache/*_history_5y.json   (all ok=False entries)
```

**Junk tickers (false-positive cache entries from earlier debugging):**
```
data/cache/OUT_financials.json
data/cache/SHOW_financials.json
data/cache/PRICE_financials.json  +  PRICE_history_5y.json
data/cache/COOK_financials.json   +  COOK_history_5y.json
data/cache/DATA_financials.json   +  DATA_history_5y.json
data/cache/LUNCH_financials.json  +  LUNCH_history_5y.json
data/cache/ENB_financials.json    +  ENB_history_5y.json   (missing .TO suffix)
```

**Action:** Delete these files manually. No code change is needed. After deletion, wait 5–10 minutes for Yahoo's rate limit to clear before running analyses.

---

## 8. Remaining Production Defects

| Defect | Severity | Status |
|---|---|---|
| `fetch_history()` writing dead cache entries | **Fixed** by this change |
| `fetch_financials()` writing dead cache entries | **Fixed** by P0 |
| `_load_cache()` serving failed-fetch entries | **Fixed** by P1 |
| Legacy ok=True/empty financials cache files | Low — manual cleanup required (see §7) |
| `force_refresh` silently dropped | Medium — see §6; separate authorization needed |
| Junk-ticker cache files | Low — manual cleanup, no code change needed |

No new defects were introduced. No analytics, renderer, decision gates, or valuation logic was modified.

---

## 9. Recommended Next Step

**Immediate (before next Streamlit test):**

Delete the dead cache files listed in §7. A one-liner that handles all of them:
```
# From the project root in a Windows terminal:
del data\cache\ENB_TO_financials.json
del data\cache\FTS_TO_financials.json
del data\cache\MSFT_financials.json
del data\cache\CNQ_TO_financials.json
del data\cache\*_history_5y.json
del data\cache\OUT_financials.json
del data\cache\SHOW_financials.json
del data\cache\PRICE_*.json
del data\cache\COOK_*.json
del data\cache\DATA_*.json
del data\cache\LUNCH_*.json
del data\cache\ENB_financials.json
del data\cache\ENB_history_5y.json
```

Then wait 5 minutes (no yfinance calls during this time) and test one ticker at a time:
1. FTS.TO — expect full financials and history on fresh fetch
2. Wait 3 minutes
3. AAPL — same expectation
4. Wait 3 minutes
5. TATASTEEL.NS — same expectation

**After cache tests pass:**  
Authorize and implement the `force_refresh` fix (§6) as a separate change. This is the last known defect affecting user-observable behaviour.
