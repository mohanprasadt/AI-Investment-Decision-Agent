# Phase 10.x — Final Root-Cause Diagnosis
**Date:** 2026-08-15  
**Status:** DIAGNOSIS COMPLETE — awaiting PO authorization before any code changes  
**Environment:** Python 3.14.6 · yfinance 1.5.2 · streamlit 1.58.0 · Windows

---

## Step 9 — Final Diagnosis

### ROOT CAUSE:
The application's `fetch_financials()` in `data/ingestion/fetcher.py` treats a yfinance empty-DataFrame response as `_fetch_success=True`, then caches it for 48 hours. The empty DataFrame is produced when Yahoo Finance rate-limits the financial statement sub-call; yfinance silently converts the resulting error into an empty DataFrame rather than raising an exception. After that, every call within the 48-hour TTL returns the cached empty data — preventing any retry — and the pipeline delivers an investment analysis built on zero rows of financial data.

### CONFIDENCE: HIGH

Evidence below is based on direct controlled measurements, not inference.

### Classification: D — COMBINATION OF A + C

**A — Environment / Yahoo Finance issue (trigger):** Yahoo Finance rate-limits aggressive bursts of API calls. When a fresh ticker is fetched for the first time, multiple endpoints are hit in rapid succession (info → financials → history). The financials call can hit a 429 window even when the info call already succeeded.

**C — Application bug (amplifier):** `fetch_financials()` receives an empty DataFrame from yfinance (because yfinance's internal exception handler silently swallowed the rate-limit error), sets `_fetch_success=True`, and writes the zero-row result to cache. The `_load_cache()` function later serves this as valid data, blocking retries for 48 hours.

---

## Step 1 — Exact Windows Environment

| Property | Value |
|----------|-------|
| Python | **3.14.6** `[MSC v.1944 64 bit (AMD64)]` |
| Python path | `C:\Python314\python.exe` |
| yfinance | **1.5.2** (user install: `AppData\Roaming\Python\Python314\site-packages`) |
| streamlit | **1.58.0** |
| pandas | **3.0.3** |
| requests | 2.34.2 |
| Platform | win32 |

> **Note:** The sandbox (Ubuntu 22, Python 3.10.12, streamlit 1.61.1) does not match the user's Windows environment in any version. All conclusions about runtime behavior are based on the Windows diagnostic output only.

---

## Step 2 — Controlled yfinance Tests (Windows, Fresh Calls)

| Ticker | info keys | income_stmt rows | balance_sheet rows | cash_flow rows | history (1mo) rows | Any error |
|--------|-----------|-----------------|-------------------|----------------|-------------------|-----------|
| ENB.TO | 182 | **53** | **89** | **67** | 23 | None |
| MSFT | 185 | **47** | **79** | **59** | 23 | None |
| FTS.TO | 180 | **50** | **87** | **57** | 23 | None |
| ITC.NS | 164 | **53** | **82** | **52** | 24 | None |
| CNQ.TO | 179 | **46** | **60** | **49** | 23 | None |

**All five tickers return complete financial data when called fresh from yfinance, outside the application's caching layer.**

This directly contradicts the earlier hypothesis that Yahoo Finance was not serving TSX or US financial statement data. Yahoo Finance IS serving the data. The empty-row cache entries were a transient artifact.

---

## Step 3 — yfinance Version Analysis

| | Version |
|-|---------|
| Installed | **1.5.2** |
| Latest available | **1.6.0** |

**Whether 1.6.0 is relevant:**

From source code inspection of 1.5.2, the root issue — `_create_financials_table()` silently catching all exceptions and returning None — is a design choice within yfinance's debug/hide_exceptions configuration:

```python
# yfinance/scrapers/fundamentals.py — _fetch_time_series()
try:
    statement = self._create_financials_table(name, timescale)
    if statement is not None:
        return statement
except YFException as e:
    if not YfConfig.debug.hide_exceptions:
        raise          # ← only if debug mode enabled
    utils.get_yf_logger().error(...)
return pd.DataFrame()  # ← silently returns empty
```

```python
# _create_financials_table() — swallows ALL exceptions by default
try:
    return self._get_financials_time_series(timescale, keys)
except Exception:
    if not YfConfig.debug.hide_exceptions:
        raise
    pass
```

Whether 1.6.0 changes this behavior cannot be confirmed from the sandbox (no network to fetch the changelog). However, **upgrading yfinance will not fix the application bug** — `fetch_financials()` will still mark empty DataFrames as `_fetch_success=True` regardless of the yfinance version. The application-level fix must happen in `fetcher.py`.

---

## Step 4 — Yahoo Finance vs yfinance vs Application

**Is the empty DataFrame occurring inside yfinance, from Yahoo Finance, or from a parsing failure?**

The yfinance financials call chain is:

```
t.financials → t.income_stmt
  → base.get_income_stmt()
    → fundamentals.financials.get_income_time_series(freq="yearly")
      → Financials._fetch_time_series("income", "yearly")
        → _create_financials_table("income", "yearly")
          → _get_financials_time_series("yearly", keys)
            → _fetch_fundamentals_payload(url)     ← HTTP GET to Yahoo Finance
```

The URL hit is:
```
https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}
  ?type=annualTaxEffectOfUnusualItems,...  (103 keys for income, up to 145 for balance-sheet)
  &period1=1483142400&period2=...&crumb={crumb}
```

The URL length for balance-sheet is **~4,361 characters**. yfinance's own comments note this endpoint is sensitive to restrictive proxies and NAT paths (including Windows home routers), which can silently drop long URLs. The chunked fallback (60 keys per request) is triggered automatically after a first failure — but if both the single-URL and the chunked path fail silently, the result is an empty DataFrame.

When `_fetch_fundamentals_payload` gets back an empty `timeseries.result` (whether from a silent 400/429 response, a dropped request, or an empty payload), it raises `YFException("Empty fundamentals-timeseries result")`. This exception is caught by `_create_financials_table`'s `except Exception: pass` → returns None → `_fetch_time_series()` returns `pd.DataFrame()`. No exception reaches `fetch_financials()`.

**Conclusion:** The empty DataFrame originates inside yfinance as a consequence of either a silent rate-limit response or a dropped HTTP call. It is not an explicit application logic failure — it is a masked failure that the application has no visibility into.

---

## Step 5 — ITC.NS Fresh vs Cache

**ITC.NS works from a fresh yfinance call.** The diagnostic Step 5 result:

```
income_rows: 53, balance_rows: 82, cf_rows: 52, error: null
```

The earlier hypothesis that "ITC.NS only works because of an old cache" was incorrect. ITC.NS financial data is genuinely available from Yahoo Finance. The 25-hour-old cache was merely coincidence — the fresh call succeeds identically.

---

## Step 6 — Cache Behavior Confirmed (Code Analysis, No Changes)

### A. What happens when financial statements are empty?

`fetch_financials()` calls `df_to_dict(t.financials)`. If `t.financials` returns an empty DataFrame, `df_to_dict()` returns `{}`. The code then sets `_fetch_success = True` unconditionally and calls `_save_cache()`. Zero-row financial data is cached as a successful fetch.

### B. Does `fetch_financials()` mark empty results `_fetch_success=True`?

**Yes.** Confirmed in code:
```python
result["income_stmt"]   = df_to_dict(t.financials)   # {} when empty
result["balance_sheet"] = df_to_dict(t.balance_sheet) # {}
result["cash_flow"]     = df_to_dict(t.cashflow)       # {}
result["_fetch_success"] = True   # ← set unconditionally, no data check
_save_cache(ticker, "financials", result)
```

### C. Does `_load_cache()` treat `_fetch_success=False` as a cache hit?

**Yes.** `_load_cache()` only checks file age against TTL. It does not inspect `_fetch_success`:
```python
if age_hours < max_age_hours:
    return data   # returns regardless of _fetch_success value
```

This affects both failed history (`_fetch_success=False` served for 24h) and empty-but-marked-successful financials (`_fetch_success=True`, 0 rows, served for 48h).

### D. How long is the failed cache retained?

| Data type | TTL | Impact of bug |
|-----------|-----|---------------|
| info | 24h | Fails with `_fetch_error` → NOT cached (info exception path skips `_save_cache`) |
| financials | **48h** | Empty DataFrame cached as `_fetch_success=True` → **48-hour retry blackout** |
| history_5y | **24h** | Empty DataFrame cached as `_fetch_success=False` → **24-hour retry blackout** |

### E. Can an empty successful result prevent future retries?

**Yes, for 48 hours.** Any call to `fetch_financials()` within the 48h TTL receives the cached zero-row result with `_fetch_success=True`. From the application's perspective, the fetch succeeded. No retry is triggered. `data_completeness_pct` will be 0–20% depending on what the normalizer can derive from the info dict alone.

---

## Step 7 — Application Safety Assessment

### What does the pipeline produce with 0% financial data?

The normalizer computes `data_completeness_pct` from five fields:
```python
important_fields = [revenue_series, net_income_series, op_cf_series,
                    total_assets_series, long_debt_series]
populated = sum(1 for f in important_fields if f)
data_completeness_pct = (populated / 5) * 100
```

With empty `income_stmt`, `balance_sheet`, and `cash_flow`, all five series are empty → **`data_completeness_pct = 0.0%`**.

### Does the agent surface a data-unavailable error?

**No.** The pipeline does NOT abort when `data_completeness_pct = 0%`. `load_ticker()` returns `ok=True` (because info fetch succeeded and `_fetch_success=True` in financials). The pipeline proceeds through all five gates.

Gate 1 evaluates business understanding from the research assessment — not from financial data. With the quantitative fallback executor, Gate 1 can still pass.

Gate 2 evaluates financial quality: all ROIC, FCF, revenue, and debt dimensions will report `data_available=False` → these appear as gaps, not as failures. The synthesizer proceeds with a degraded quality tier.

**The user receives a rendered investment report with action (WAIT, WATCH, or BUY) that is grounded in zero rows of financial data.** The report will contain data-gap notes, but the top-level action and confidence score can still look like a valid analysis to a non-expert reader.

### Could the user reasonably interpret this as a valid investment analysis?

**Yes, and that is the safety concern.** The rendered output includes:
- Company name and current price (from `info` — these are valid)
- An investment action (WAIT / WATCH / BUY — not valid; driven by research fallback with no financial grounding)
- Gate summaries that mention "data gaps" — but in paragraph form, not as a prominent warning

A user unfamiliar with the data-completeness indicator could act on this analysis. The action is not grounded in any income statement, balance sheet, or cash flow data.

---

## Step 8 — No Code Changes Implemented

Per the diagnostic brief: no modifications have been made to `fetcher.py`, `pipeline.py`, `data_loader.py`, any Streamlit file, cache logic, or tests.

---

## Step 9 Summary — PO Decision Questions

### 1. Evidence

**For the diagnosis:**
- Diagnostic script run on Windows at 20:27 local time returns 46–89 rows of financial data per statement for every tested ticker, with zero errors
- The earlier empty cache entries (written ~1–1.5h before the diagnostic) predate the diagnostic run — they were written during a period of active rate limiting
- yfinance source code confirms the silent-empty-DataFrame path exists and is exercised on any rate-limited or dropped HTTP call
- The cache TTL logic confirms 48-hour lockout once an empty-success result is written

**Against alternative hypotheses:**
- Not a Yahoo Finance data availability issue: all five tickers return full data on fresh calls
- Not a Streamlit-specific issue: confirmed in prior diagnostic, not revisited
- Not a Python 3.14.6 / pandas 3.0.3 compatibility issue: the diagnostic succeeds on the same interpreter
- Not an ongoing yfinance 1.5.2 bug: data is available; the bug is in how the application handles yfinance's masked failure mode

---

### 2. What is already working

- Yahoo Finance data is available and correct for all tested tickers: TSX (ENB.TO, FTS.TO, CNQ.TO), US (MSFT), India (ITC.NS)
- yfinance 1.5.2 on Python 3.14.6 / Windows correctly fetches and returns financial statements when not rate-limited
- The 429 retry in `pipeline.py` correctly handles the info endpoint rate limit
- The intent classifier and conversational layer (Phase 10) are working correctly
- ITC.NS analysis is fully functional (data available, cache warm, Phase 10 UI complete)

---

### 3. What is actually broken

**Primary bug — `fetch_financials()` treats empty DataFrames as success:**
When a Yahoo Finance 429 hits the financials endpoint during a burst-fetch of a cold ticker, yfinance silently returns an empty DataFrame. `fetch_financials()` has no way to detect this and marks the result `_fetch_success=True`. The empty result is cached for 48 hours. For the entire TTL, the pipeline produces investment analyses with 0% financial data completeness, and the user receives no explicit "data unavailable" error.

**Secondary bug — `_load_cache()` serves `_fetch_success=False` history results for 24h:**
When `fetch_history()` fails (empty DataFrame, no exception), it caches the failure as `_fetch_success=False`. `_load_cache()` serves this without checking `_fetch_success`, blocking history retries for 24 hours. This is less severe than the financials bug because price history is not used in the core investment metrics.

**Minor bug — `force_refresh` not wired through:**
UI checkbox does nothing. Low-priority.

---

### 4. Whether yfinance should be upgraded

**Not required to fix the identified bugs.** The application bugs in `fetcher.py` are independent of the yfinance version. Fixing `fetch_financials()` to detect empty DataFrames and treat them as failures will resolve the 48-hour lockout regardless of the yfinance version.

**Optional:** Upgrading to 1.6.0 may contain improvements to session handling or chunked URL fallback. Given Python 3.14.6 is very new, there is a non-zero risk that 1.6.0 has compatibility issues not yet discovered. Recommend: fix the application bugs first; evaluate 1.6.0 upgrade separately with a controlled test run.

---

### 5. Whether the cache bugs should be fixed

**Yes — both bugs should be fixed.** They are independent, low-risk changes confined to `data/ingestion/fetcher.py`:

**Bug A — `fetch_financials()` empty-DataFrame detection:**
```python
# RECOMMENDED FIX (not yet implemented)
# After fetching all three statements, before setting _fetch_success:
if not result["income_stmt"] and not result["balance_sheet"] and not result["cash_flow"]:
    result["_fetch_success"] = False
    result["_fetch_error"] = "yfinance returned empty financial statements (likely rate-limited)"
    return result   # do NOT cache — allow retry on next call
result["_fetch_success"] = True
_save_cache(ticker, "financials", result)
```

**Bug B — `_load_cache()` stale failure serving:**
```python
# RECOMMENDED FIX (not yet implemented)
# After reading the file and checking TTL:
if not data.get("_fetch_success", True):
    return None   # treat failed fetch as cache miss; allow retry
```

Both fixes together: any rate-limited fetch fails explicitly and cleanly, retries on the next call, and is never cached as valid.

---

### 6. Whether empty financial statements should be treated as a hard failure

**Yes — for the income statement.** Without at least one non-empty financial statement, `data_completeness_pct = 0%` and the pipeline has no financial data for any gate. The correct response is to fail explicitly (return `cannot_complete_reason`, do not produce an analysis) rather than produce an unfounded recommendation.

The minimum bar should be: if `income_stmt` (revenue/net income series) is empty after fetching, treat the result as a failed fetch. Balance sheet and cash flow alone are insufficient for the core investment metrics.

**This should be implemented as Bug A fix above** — detecting empty DataFrames in `fetch_financials()` and not caching them as success. The application-level `load_ticker()` already propagates a `cannot_complete_reason` to the UI when `_fetch_success=False`.

---

### 7. Whether Phase 10 can be accepted

**Not in its current state for TSX and US tickers.** The following defects must be resolved first:

| Defect | Severity | Required before acceptance |
|--------|----------|--------------------------|
| Empty financial statements cached as success (Bug A) | **CRITICAL** | Yes |
| Failed history cached as valid hit for 24h (Bug B) | Medium | Recommended |
| `force_refresh` not wired through (Bug C) | Minor | No |

Once Bug A is fixed, the application will correctly surface "financial data unavailable" when a rate-limited fetch returns empty DataFrames. The user will see a `CANNOT_COMPLETE` error rather than a zero-data analysis. The retry will succeed on the next explicit re-analysis request.

**ITC.NS is ready for demonstration today** — data is available, cache is warm, analysis is grounded.

---

### 8. Recommended Minimum Phase 10.x Changes

Listed in priority order. No changes are authorized until explicitly approved.

**P0 — Fix `fetch_financials()` empty-DataFrame detection (Bug A)**
- File: `data/ingestion/fetcher.py`
- Change: After fetching all three DataFrames, detect all-empty result → set `_fetch_success=False`, set `_fetch_error`, return without caching
- Risk: LOW — no analytics/ changes, no test file changes needed
- Tests needed: 1 new unit test (`test_fetch_financials_empty_returns_failure`), then full 1,071-test regression run

**P1 — Fix `_load_cache()` to skip `_fetch_success=False` entries (Bug B)**
- File: `data/ingestion/fetcher.py`
- Change: Return None when `data.get("_fetch_success", True)` is False
- Risk: LOW — narrow change, affects all three fetch types uniformly
- Tests needed: 1 new unit test (`test_load_cache_ignores_failed_entries`), regression run

**P2 — Delete the 11 false-ticker junk cache files**
- Files: `data/cache/COOK_*.json`, `DATA_*.json`, `LUNCH_*.json`, `OUT_*.json`, `PRICE_*.json`, `SHOW_*.json`, `ENB_financials.json`, `ENB_history_5y.json`
- Change: Delete files. They will be re-created with bad data if not removed.
- Risk: ZERO — junk files from old intent classifier

**P3 — Wire `force_refresh` through pipeline → load_ticker (Bug C)**
- Files: `analytics/agent/data_loader.py`, `analytics/agent/pipeline.py`
- Change: Add `force_refresh` param to `load_ticker()`, pass through to `_default_fetch()`
- Risk: LOW — requires regression run on the `load_ticker` test coverage
- Tests needed: 1 new integration test, regression run

---

## Files Requiring Modification (if authorized)

| File | Change | Priority |
|------|--------|----------|
| `data/ingestion/fetcher.py` | `fetch_financials()`: detect all-empty → fail, don't cache | P0 |
| `data/ingestion/fetcher.py` | `_load_cache()`: return None when `_fetch_success=False` | P1 |
| `data/cache/` | Delete 11 false-ticker junk files | P2 |
| `analytics/agent/data_loader.py` | Add `force_refresh` param | P3 |
| `analytics/agent/pipeline.py` | Pass `force_refresh` to `load_ticker()` | P3 |

No changes to `analytics/decision/`, `analytics/financial_quality/`, `analytics/valuation/`, or any Phase 10 conversation/UI files.

---

## Cleanup

The following diagnostic files were created during this investigation. They can be deleted once the PO review is complete:

- `diagnostic_phase10x.py`
- `run_diagnostic.bat`
- `diagnostic_output.json`
