# Phase 10.1 — Diagnostic Report: yfinance 429 / TSX Financial Data
**Date:** 2026-08-15  
**Status:** DIAGNOSTIC COMPLETE — awaiting PO decision before any code changes  
**Environment:** Windows (user's machine); sandbox has no outbound network — all cache evidence is from Windows

---

## Executive Summary

| Question | Verdict |
|----------|---------|
| Is the 429 error Streamlit-specific? | **No** — cold-cache issue shared by CLI and Streamlit |
| Does Streamlit cause repeated fetches? | **No** — architecturally clean; analysis triggers only on button click |
| Does `route()` call yfinance? | **No** — routes to `agent.chat()` only |
| Is `force_refresh` wired through? | **No** — minor bug; UI checkbox does nothing |
| Is failed history re-cached for 24h? | **Yes** — confirmed bug in `fetcher.py` |
| Are TSX financial statements empty? | **Yes, on Windows** — confirmed from cache evidence (not sandbox) |
| Are US financial statements empty? | **Yes, on Windows** — MSFT also 0 rows in current cache |
| Why does ITC.NS work? | Financials served from **25h-old cache** — no fresh fetch needed |
| Is TSX emptiness a code bug? | **Partly** — yfinance returns empty DataFrames; fetcher marks this `_fetch_success=True` (code bug) |
| Is the underlying empty-data cause a code bug? | **No** — Yahoo Finance API restriction or yfinance 1.5.x incompatibility with TSX/US endpoints |
| Is the 429 retry sufficient? | Handles common case; won't fix empty financials or 24h stale-failure cache |
| Ready for final acceptance? | **Blocked** — TSX/US financial data unavailable until root cause is resolved |

---

## Step 1 — Execution Path Tracing

**Finding:** CLI and Streamlit use **identical** code paths for live analysis.

```
Both paths:
  load_ticker(ticker, analysis_date)
    → _default_fetch(ticker)
      → fetch_info(ticker)        → yfinance t.info     (cached 24h)
      → fetch_financials(ticker)  → yfinance t.financials etc. (cached 48h)
      → fetch_history(ticker)     → yfinance t.history() (cached 24h)
    → _default_normalize(ticker, raw)
    → quality_engine, freshness, InvestmentAgent.analyze()
```

**Confirmed:** `route()` in `ConversationManager` never calls `run_analysis_pipeline()` or `load_ticker()`. It routes only to `agent.chat()`.

**Confirmed:** `run_analysis()` in `ui/app.py` is guarded by `if analyse_clicked and ticker_input.strip()`. `st.button()` returns `True` only on the single rerun immediately after click. No duplicate fetches.

**Confirmed:** `ConversationManager` lives in `st.session_state["manager"]`, created once per session. Assessment and history survive reruns.

**CLI "works" explanation:** The user's CLI tests use `CNR.TO` (pre-built demo data, never calls yfinance). The live path on CLI is identical to Streamlit; CLI tests of uncached tickers would also hit 429.

---

## Step 2 — Environment Versions

Confirmed from `requirements.txt` and environment:
- Python 3.10  
- yfinance 1.5.2  
- streamlit 1.61.1  

> **Note:** The sandbox runs Python 3.10.12 on Ubuntu 22 with zero outbound network access (curl/yfinance both fail with 403 CONNECT tunnel error). All live yfinance calls in this diagnostic are inferred from cache evidence, not from live sandbox tests.

---

## Step 3 — Direct yfinance Network Test

**Sandbox result:** ALL tickers fail with `ConnectionError: CONNECT tunnel failed, response 403`. The sandbox has no network path to Yahoo Finance. This is a sandbox infrastructure limitation and does NOT represent behavior on the user's Windows machine.

**Windows behavior inferred from cache evidence** (see Step 4): yfinance CAN reach Yahoo Finance from Windows. Info fetches succeed. Financials fetches complete without exception but return empty DataFrames.

---

## Step 4 — Cache State at Time of Investigation

All cache files were synced from the user's Windows machine via OneDrive. Timestamps reflect when yfinance was called on Windows.

### Complete cache inventory

| File | Age | `_fetch_success` | Notes |
|------|-----|-----------------|-------|
| `ITC_NS_info.json` | 0.8h | True | 168 keys, price=278.2 |
| `ITC_NS_financials.json` | **25.2h** | True | **53 income, 82 balance, 52 cash flow rows** — old CLI session cache |
| `ITC_NS_history_5y.json` | 1.2h | **False** | 0 closes — failed empty, cached for 24h |
| `ENB_TO_info.json` | 0.6h | True | 186 keys, price=70.61 |
| `ENB_TO_financials.json` | 1.0h | True | **0 income, 0 balance, 0 cash flow rows** |
| `ENB_TO_history_5y.json` | 1.0h | **False** | 0 closes — failed empty, cached for 24h |
| `FTS_TO_financials.json` | 0.8h | True | 0 rows all statements |
| `FTS_TO_history_5y.json` | 0.8h | **False** | 0 closes |
| `MSFT_financials.json` | 1.0h | True | **0 rows all statements** |
| `MSFT_history_5y.json` | 1.0h | **False** | 0 closes |
| `CNQ_TO_info.json` | 142.2h | True | 182 keys, price=63.45 (stale, >24h TTL) |
| `CNQ_TO_financials.json` | 142.3h | True | **0 rows all statements** (stale, >48h TTL) |
| `CNQ_TO_history_5y.json` | 142.2h | True | **1,255 closes** — history WAS working 6 days ago |
| COOK, DATA, LUNCH, OUT, PRICE, SHOW, ENB (11 files) | 1.5h | varies | False-ticker junk from old intent classifier; all empty |

### Critical observations

1. **ENB.TO, FTS.TO, MSFT, CNQ.TO** all have 0-row financial statements. These span **TSX (Canadian) and US NASDAQ tickers**.
2. **CNQ.TO** (142h old) also had 0-row financials — this is not a recent change. TSX financial data has been empty for **at least 6 days**.
3. **CNQ.TO history** (142h old) has 1,255 closes — price history WAS working 6 days ago. It has since failed for all tickers.
4. **ITC.NS financials** (53 rows) are from a **25-hour-old CLI session cache** — NOT from the recent Streamlit session. They were not re-fetched. The Streamlit session served them from cache.
5. **MSFT is a US ticker.** The empty-financials problem is not TSX-only.

---

## Step 5 — CLI vs Streamlit Comparison

| Trigger | Calls yfinance? | Confirmed |
|---------|----------------|-----------|
| Streamlit page load / rerun | No | `_init_session` only creates manager if absent |
| User types in ticker input | No | `text_input` changes trigger rerun but not analysis |
| "Analyse" button click | Yes — once | Guarded by `analyse_clicked` flag |
| Follow-up chat message | No | `manager.route()` → `agent.chat()` only |
| Sidebar render | No | Reads session state |
| Decision panel render | No | Reads session state |

**Streamlit introduces zero duplicate or spurious yfinance calls. This is confirmed by code inspection.**

The user's observation that "ITC.NS works but TSX doesn't" is explained entirely by cache state — not by a Streamlit-specific defect.

---

## Step 6 — Live Fetch Behavior (inferred from Windows cache)

**Cannot be verified from sandbox** — all outbound network calls fail. The following is inferred from cache evidence:

| Ticker | Info fetch | Financials fetch | History fetch |
|--------|-----------|-----------------|---------------|
| ITC.NS | OK (168 keys) | Served from 25h old cache — NOT re-fetched | Empty DataFrame returned; 0 closes cached |
| ENB.TO | OK (186 keys) | Empty DataFrame returned (no exception); `_fetch_success=True` | Empty DataFrame returned; 0 closes cached |
| FTS.TO | (no info cache found) | Empty DataFrame; `_fetch_success=True` | Empty DataFrame; 0 closes cached |
| MSFT | (no info cache found) | Empty DataFrame; `_fetch_success=True` | Empty DataFrame; 0 closes cached |

**The 429 the user saw on first attempt of ENB.TO was from the info endpoint.** After the pipeline's retry logic succeeded, the info was fetched and cached. The financials fetch then completed without a 429 (no exception at all) but returned empty DataFrames.

---

## Step 7 — Cache Bug Classification

### Bug A: `_fetch_success=False` history results cached and served

**Location:** `data/ingestion/fetcher.py` — `fetch_history()` and `_load_cache()`

**Mechanism:**
```python
# fetch_history() — when t.history() returns empty DataFrame (no exception):
if hist is not None and not hist.empty:
    result["_fetch_success"] = True   # stays False — no closes written
_save_cache(ticker, cache_key, result)   # ← saves _fetch_success=False to disk
```

```python
# _load_cache() — does NOT check _fetch_success:
if age_hours < max_age_hours:
    return data   # returns _fetch_success=False result as valid cache hit
```

**Impact:** A failed history fetch locks out retries for up to 24 hours. The pipeline silently continues with no price history.

**Classification:** **BUG** — empty failure results should not be cached as valid entries.

---

### Bug B: `fetch_financials()` marks empty DataFrames as `_fetch_success=True`

**Location:** `data/ingestion/fetcher.py` — `fetch_financials()`

**Mechanism:**
```python
result["income_stmt"] = df_to_dict(t.financials)    # {} when empty
result["balance_sheet"] = df_to_dict(t.balance_sheet)  # {}
result["cash_flow"] = df_to_dict(t.cashflow)           # {}
result["_fetch_success"] = True   # ← set unconditionally, even when all {} above
_save_cache(ticker, "financials", result)
```

**Impact:** Empty financial data is cached as successful. The caller (`data_loader.py`) accepts it. The pipeline proceeds to `InvestmentAgent.analyze()` with `data_completeness_pct ≈ 0%` and no financial statement rows. Any investment decision produced is unfounded.

**Classification:** **BUG** — `_fetch_success=True` must require at least one non-empty statement.

---

### Bug C: `force_refresh` not wired through

**Location:** `analytics/agent/pipeline.py` → `analytics/agent/data_loader.py`

`run_analysis_pipeline(force_refresh=True)` is called by the Streamlit UI when the user ticks "Force refresh". But:
```python
# pipeline.py line 142:
load_result = load_ticker(ticker=ticker, analysis_date=_date)  # force_refresh not passed
```

`load_ticker()` has no `force_refresh` parameter; `_default_fetch()` calls `fetch_ticker(ticker)` with `force_refresh=False`. The UI checkbox does nothing.

**Classification:** **MINOR BUG** — causes false user expectation but does not affect core analysis.

---

## Step 8 — TSX / US Financial Data Root Cause

**Finding:** TSX and US ticker financial statements are empty across both old (142h) and recent (1h) cache entries. This has been the case for at least 6 days.

**Three possible causes — cannot distinguish without Windows-side verification:**

| Cause | Evidence for | Evidence against |
|-------|-------------|-----------------|
| (A) Yahoo Finance API restriction: free-tier financial data now requires authentication (crumb/cookie) that yfinance 1.5.2 doesn't handle correctly for TSX/US | CNQ.TO empty 142h ago; ENB.TO/MSFT empty 1h ago; ITC.NS working from old cache | ITC.NS financials may also be empty if re-fetched fresh |
| (B) yfinance 1.5.x bug specific to TSX (`.TO` suffix) financial endpoints | TSX pattern consistent | MSFT (US ticker, no `.TO`) also empty |
| (C) Yahoo Finance temporarily rate-limiting financials (silent empty instead of 429) | All fetches in same session period | CNQ.TO empty since 142h — would not persist 6 days from one rate-limit event |

**Most likely cause: (A)** — Yahoo Finance progressively restricting financial statement data for non-India markets in the free (unauthenticated) API tier. NSE/India data appears to be served via a different endpoint or with different access controls.

**Windows verification command** (run from PowerShell, outside the Streamlit app):
```powershell
python -c "import yfinance as yf; t = yf.Ticker('ENB.TO'); f = t.financials; print(f'ENB.TO income_stmt rows: {len(f)}')"
python -c "import yfinance as yf; t = yf.Ticker('MSFT'); f = t.financials; print(f'MSFT income_stmt rows: {len(f)}')"
python -c "import yfinance as yf; t = yf.Ticker('ITC.NS'); f = t.financials; print(f'ITC.NS income_stmt rows: {len(f)}')"
```

Expected result if cause (A): ENB.TO=0, MSFT=0, ITC.NS varies (may be 0 or populated depending on endpoint).

---

## Step 9 — AAPL Cold-Cache Test

**Cannot be performed from sandbox** (no network). AAPL has no cache files at all.

**Windows verification command:**
```powershell
python -c "
import yfinance as yf
t = yf.Ticker('AAPL')
info = t.info
print('AAPL price:', info.get('currentPrice') or info.get('regularMarketPrice'))
f = t.financials
print('AAPL income_stmt rows:', len(f))
"
```

If `AAPL income_stmt rows: 0` → confirms the financial data gap is not TSX-specific; it affects US tickers too.  
If `AAPL income_stmt rows > 0` → confirms TSX/US distinction is real; may be a `.TO` suffix issue.

---

## Step 10 — Final Verdict

### On the 429 error

**PASS WITH KNOWN LIMITATION.** The 429 is a cold-cache rate limit from Yahoo Finance's info endpoint. The retry logic in `pipeline.py` mitigates it. This is an environment characteristic (Yahoo Finance rate limits anonymous callers), not an application defect. Streamlit does not make it worse.

### On the empty financial statements

**FAIL.** TSX and US ticker financial statements are empty on Windows. The analysis engine produces an investment decision with `data_completeness_pct ≈ 0%`. Any buy/hold/wait output in this state is unfounded and misleading to the user.

Two separate defects compound this:
1. **Yahoo Finance data availability** — the underlying data cannot be retrieved (external, not fixable in application code).
2. **`fetch_financials()` Bug B** — empty DataFrames are marked `_fetch_success=True`, so the application believes the fetch succeeded. The user receives an "analysis" rather than an honest "financial data unavailable" message.

---

## Recommendations (priority order, NOT yet implemented)

### R1 — Fix `fetch_financials()` to detect empty data — HIGH PRIORITY

**File:** `data/ingestion/fetcher.py`  
**Change:** After fetching all three DataFrames, check if all are empty. If so, set `_fetch_success=False` and `_fetch_error="yfinance returned empty financial statements"`. Do NOT save to cache on empty result.  
**Why:** Prevents the pipeline from producing a 0%-completeness "analysis" that looks like a real result.  
**Scope:** ~6 lines in `fetch_financials()`. No analytics/ changes.

```python
# RECOMMENDED FUTURE FIX — NOT IMPLEMENTED
if not result["income_stmt"] and not result["balance_sheet"] and not result["cash_flow"]:
    result["_fetch_success"] = False
    result["_fetch_error"] = "yfinance returned empty financial statements for all three endpoints"
    # Do NOT save to cache — allow retry on next call
    return result
result["_fetch_success"] = True
_save_cache(ticker, "financials", result)
```

---

### R2 — Fix `_load_cache()` to treat `_fetch_success=False` as a cache miss — HIGH PRIORITY

**File:** `data/ingestion/fetcher.py`  
**Change:** In `_load_cache()`, after reading the file, check `data.get("_fetch_success", True)`. If False, return `None` so the caller performs a fresh fetch.  
**Why:** Prevents stale failure results (especially failed history) from blocking retries for 24h.  
**Scope:** ~3 lines in `_load_cache()`.

```python
# RECOMMENDED FUTURE FIX — NOT IMPLEMENTED
# After: if age_hours < max_age_hours:
if not data.get("_fetch_success", True):
    return None   # treat failed fetch as cache miss; allow retry
return data
```

---

### R3 — Wire `force_refresh` through pipeline → load_ticker — LOW PRIORITY

**Files:** `analytics/agent/data_loader.py` (add `force_refresh: bool = False`, pass to `_default_fetch`), `analytics/agent/pipeline.py` (pass `force_refresh` to `load_ticker`).  
**Why:** Makes the UI "Force refresh" checkbox actually work.  
**Risk:** Minor — `load_ticker` is covered by the existing test suite (1,071 tests).

---

### R4 — Investigate yfinance upgrade or alternative data source — MEDIUM PRIORITY

**Context:** yfinance 1.5.2 may have a known issue with financial statement retrieval for TSX/US tickers. Later versions of yfinance (2.x) changed the authentication approach.  
**Action:** Test `pip install --upgrade yfinance` on Windows and re-run the Step 8 verification commands. If financial data becomes available, upgrade.  
**Risk:** API surface changes between yfinance versions may require fetcher updates.

---

### R5 — Prune false-ticker cache pollution — OPTIONAL CLEANUP

11 junk cache files (COOK, DATA, LUNCH, OUT, PRICE, SHOW, ENB without `.TO` suffix) were written by the pre-fix intent classifier. These are harmless and will expire naturally within 24–48h, but pruning them cleans the workspace.

---

## Files Requiring Modification (if recommendations approved)

| File | What | Recommendation |
|------|------|----------------|
| `data/ingestion/fetcher.py` | `fetch_financials()`: treat all-empty DataFrames as failure; don't cache | R1 |
| `data/ingestion/fetcher.py` | `_load_cache()`: return None when `_fetch_success=False` | R2 |
| `analytics/agent/data_loader.py` | Add `force_refresh` param, pass to `_default_fetch` | R3 |
| `analytics/agent/pipeline.py` | Pass `force_refresh` to `load_ticker()` call | R3 |

`analytics/` changes require re-running 1,071-test suite (currently all pass).

---

## Tests Required After Any Fix

| Test | Purpose |
|------|---------|
| Full suite (1,071 tests) | Regression — must pass after any `fetcher.py` or `data_loader.py` change |
| New: `test_fetch_financials_empty_returns_failure` | Verify `fetch_financials()` returns `_fetch_success=False` when all statements empty |
| New: `test_load_cache_ignores_failed_entries` | Verify `_load_cache()` returns None when `_fetch_success=False` |
| New: `test_force_refresh_passes_through` | Verify pipeline.py passes `force_refresh=True` to `fetch_ticker` |
| Manual: Step 8 commands on Windows | Determine if TSX/US financial data gap is Yahoo Finance restriction or yfinance bug |

---

## Phase 10 Acceptance Status

| Area | Status | Notes |
|------|--------|-------|
| Streamlit architecture | ✅ PASS | No duplicate fetches, clean session management |
| Intent classification | ✅ PASS | 64/64 Phase 10 tests passing |
| 429 retry logic | ✅ PASS | Mitigates cold-cache rate limiting |
| ITC.NS end-to-end | ✅ PASS | Works when financials cache is warm |
| TSX ticker analysis | ❌ FAIL | Empty financial data; analysis unusable |
| US ticker analysis | ❌ FAIL | MSFT also has empty financials |
| `force_refresh` UI | ❌ MINOR | Checkbox does nothing; wiring not implemented |
| Error surfacing | ⚠️ PARTIAL | 429 shown; empty-financials NOT surfaced — pipeline returns "analysis" with 0% completeness |

**Phase 10 is not ready for acceptance as a TSX/US stock analysis tool until R1 (detect empty financials) and R4 (yfinance upgrade investigation) are resolved.**

ITC.NS (India/NSE) analysis is functional and can be demonstrated.
