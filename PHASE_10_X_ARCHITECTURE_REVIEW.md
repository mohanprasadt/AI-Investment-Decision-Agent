# Phase 10.x — Architecture Review: Yahoo Finance / yfinance Reliability

**Date:** 2026-08-15  
**Scope:** Diagnostic only. No code changes recommended for immediate implementation.  
**Basis:** Code inspection of `fetcher.py`, `data_loader.py`, `pipeline.py`,
`conversation/manager.py`, `conversation/session.py`, `ui/app.py`,
`analytics/agent/investment_agent.py`, plus live Streamlit logs and four diagnostic
runs (Suites 1–4).

---

## 1. Root Cause

**Proven facts:**

**C — Yahoo Finance rate limiting** is the primary and sufficient cause of the remaining
429 failures. Yahoo applies a sliding rate-limit window to unauthenticated clients. The
window persists for ≥74 seconds (observed: SU.TO) and ≥97 seconds (observed: MSFT). No
documented threshold or `Retry-After` header is provided.

**B — yfinance behavior** is a contributing amplifier. For each cold ticker, yfinance
makes 7 HTTP requests across three fetcher calls. This is not a bug — it is correct
behavior for fetching three distinct data categories. However, it means each pipeline
invocation costs 7 requests against Yahoo's rate-limit counter.

**A — Application defects (now fixed):** Three defects (P0/P1/History) created a
dead-cache amplification loop: failed fetches were written to cache; P1 rejected them as
cache misses; the next request fetched again, also failed, also wrote a dead entry.
This multiplied Yahoo requests by 4× per retry attempt for data that was already
rate-limited. These are fixed. The amplification loop no longer exists.

**D — Architecture:** The application makes live Yahoo requests only when the user
submits a new ticker for analysis. Follow-up questions make zero Yahoo requests (proven
below). The architecture is not structurally excessive. The remaining problem is that a
single cold-ticker analysis costs 7 Yahoo requests, and those 7 requests can land inside
an active rate-limit window with no prior warning.

**Hypothesis (not proven, architecturally plausible):** The MSFT 429 window exceeding
97 seconds suggests that Yahoo's rate-limit window accumulates across the process's full
request history for the session — including requests made for earlier tickers in the same
Streamlit session. A session that analyzed 2–3 tickers before MSFT may have consumed
enough of Yahoo's rolling window to place MSFT's requests inside an extended limit period.

**Summary:** The remaining 429 failures are inherent to unauthenticated access to Yahoo
Finance when cold-cache data is needed. No application defect causes them. They cannot be
eliminated without either (a) pre-warming the cache before interactive use, or (b)
using authenticated / licensed market data.

---

## 2. Request Profile

### Complete data acquisition path

```
User clicks "Analyse"
  → ui/app.py: _run_analysis()
    → manager.run_analysis()
      → pipeline.run_analysis_pipeline()
        → data_loader.load_ticker()
          → data_loader._default_fetch()
            → fetcher.fetch_ticker()
              → fetcher.fetch_info()       [check cache → yfinance if miss]
              → fetcher.fetch_financials() [check cache → yfinance if miss; skipped if info failed]
              → fetcher.fetch_history()    [check cache → yfinance if miss; skipped if info failed]
          → normalizer.normalize()
          → quality_engine.assess_financial_quality()
          → build_freshness_assessment()
        → ResearchOrchestrator.build_assessment()
        → build_valuation_input()
        → run_valuation()
        → InvestmentAgent.analyze()
```

### HTTP request count — cold ticker (no cache)

Measured from `diagnostic_output_3.json` and `diagnostic_output_4.json` (URL arrays).
Each ticker in both suite runs logged exactly 7 HTTP requests:

| # | Call origin | Endpoint | Purpose |
|---|-------------|----------|---------|
| 1 | `fetch_info` | `v10/finance/quoteSummary/{T}` | Company info (basic cookie strategy) |
| 2 | `fetch_info` | `v7/finance/quote?` | CSRF strategy — yfinance always toggles on first call |
| 3 | `fetch_financials` | `ws/fundamentals-timeseries/...?type=trailingPegRatio` | Trailing PEG ratio |
| 4 | `fetch_financials` | `ws/fundamentals-timeseries/...?type=annualTaxEffect,...` | Income statement batch |
| 5 | `fetch_financials` | `ws/fundamentals-timeseries/...?type=annualTreasuryShares,...` | Balance sheet batch |
| 6 | `fetch_financials` | `ws/fundamentals-timeseries/...?type=annualForeignSales,...` | Cash flow batch |
| 7 | `fetch_history` | `v8/finance/chart/{T}` | 5-year price history |

Total: **7 HTTP requests per cold ticker.**

All 7 are sequential (each yfinance call is synchronous). None are parallelized.

### What happens after a 429

With the Phase 10.x short-circuit fix in place:

1. Request #1 or #2 (`fetch_info`) receives HTTP 429.
2. `fetch_info` returns `{"_fetch_success": False, "_fetch_error": "429..."}`.
3. `fetch_ticker` detects `_fetch_success=False` → returns immediately with stubs for
   financials and history. **Requests #3–#7 are never made.**
4. `data_loader.load_ticker()` detects `info._fetch_success=False` → sets
   `cannot_complete_reason` → returns `DataLoadResult(ok=False)`.
5. `pipeline.run_analysis_pipeline()` checks the 429 signature in `_err`:
   `"429" in _err or "Too Many Requests" in _err` → waits `_RETRY_DELAYS[i]` seconds →
   retries `load_ticker()`.
6. If all 3 attempts fail, `PipelineResult(ok=False, error=...)` is returned.
7. `manager._format_pipeline_error()` formats the error → UI displays it.

**Requests per retry attempt (with short-circuit):** 1–2 (info only), not 7.

### Cache behaviour

| Data type | TTL | Written when | Rejected on read when |
|-----------|-----|-------------|----------------------|
| info | 24h | `_fetch_success=True` | Expired or `_fetch_success=False` (P1) |
| financials | 48h | `_fetch_success=True` | Expired or `_fetch_success=False` (P1) |
| history | 24h | `_fetch_success=True` | Expired or `_fetch_success=False` (P1) |

Cache is stored in `data/cache/` as individual JSON files per ticker + data type.
The `cookies.db` SQLite file (`C:\Users\...\AppData\Local\py-yfinance\`) is maintained
by yfinance separately and survives deletion of `data/cache/`.

### Subsequent requests for the same ticker (within TTL)

With all 3 data types cached: **0 HTTP requests.** All three fetchers return cached data
immediately. The normalizer, quality engine, research, valuation, and decision synthesis
still run (CPU-bound, no network calls).

---

## 3. Interactive Architecture — Follow-Up Questions

**Finding: Follow-up questions make zero Yahoo Finance requests. This is already correct.**

Code trace for a follow-up question ("Why is FCF lower than EPS?"):

```
User types in chat input
  → ui/app.py: _render_conversation_panel() → manager.route(text)
    → conversation/manager.py: classify_intent(text) → INTENT_FOLLOW_UP
      → _handle_followup(text, intent)
        → self._agent.chat(text)
          → analytics/agent/investment_agent.py: _handle_followup(text)
            → render_followup(self._session.last_assessment, text)
              [pure function — reads from stored InvestmentDecisionAssessment]
              [no data fetching of any kind]
```

`render_followup()` reads entirely from `InvestmentDecisionAssessment` stored in
`self._agent._session.last_assessment`, which was populated once during `run_analysis()`
and is preserved for the entire conversation session.

The only operations that trigger a Yahoo request are:
1. User clicks the "🔍 Analyse" button.
2. User types "Analyze TICKER" in the chat input (classified as `INTENT_ANALYZE`).

Both call `manager.run_analysis()` → `run_analysis_pipeline()`. If the ticker and its
cache are still warm, 0 Yahoo requests are made even for button re-clicks.

**One edge case:** If the user types "Analyze MSFT" in the chat box for an already-loaded
MSFT session, `manager._handle_analyze_from_chat()` calls `run_analysis()` which calls
`run_analysis_pipeline()` which calls `load_ticker()`. Since MSFT is cached, 0 Yahoo
requests. But the full analysis pipeline (research, valuation, synthesis) re-runs,
unnecessarily. This is a minor inefficiency, not a correctness problem.

---

## 4. Cache-First Design

### Where the cache is strong

- **Disk persistence:** Raw yfinance data survives Streamlit restarts, browser refreshes,
  and session resets. A cached ticker is available across sessions.
- **P0/P1/History fixes:** Failed fetches are not written to cache. The cache only grows
  from successful fetches.
- **ETF handling:** ETFs correctly skip financials; cache entries for ETF info and history
  are handled identically to equities.
- **Force-refresh escape hatch:** The UI exposes a "Force refresh" checkbox. It correctly
  passes `force_refresh=True` through `manager.run_analysis()` to `run_analysis_pipeline()`.

### Where the cache is weak

**Weakness 1 — `force_refresh` is silently dropped.**  
`pipeline.run_analysis_pipeline()` receives `force_refresh` as a parameter (line 92) but
does NOT pass it to `load_ticker()` (line 142). `load_ticker()` calls `_default_fetch(ticker)`
without `force_refresh`. The "Force refresh" checkbox has no effect on the fetcher cache.
This is the open defect from Phase 10.x.

**Weakness 2 — Assessment is not cached.**  
The analysis pipeline (normalizer, quality engine, research, valuation, decision synthesis)
re-runs on every "Analyse" button click, even when all three yfinance data sources are
cached. For cached tickers this is fast (< 5 seconds, CPU-bound). It is not a 429 risk,
but it adds latency and repeated Claude API calls if Anthropic research is enabled.

**Weakness 3 — No pre-warm facility.**  
There is no built-in mechanism to pre-fetch data for known tickers ahead of a demo session.
`fetch_portfolio()` in `fetcher.py` provides batch fetching, but it is not wired to the UI.
A demo that starts with cold cache is entirely dependent on Yahoo's rate-limit state.

**Weakness 4 — Cache is local to one machine.**  
`data/cache/` is a local directory. If the demo runs on a different machine, or after
a system rebuild, all tickers are cold. `cookies.db` (yfinance auth state) is also local.

---

## 5. Failure Safety

### Scenario analysis

**Scenario A — info missing (fetch_info returns `_fetch_success=False`)**

Path: `data_loader.py` line 183 detects `fetch_ok=False` → sets `cannot_complete_reason` →
returns `DataLoadResult(ok=False)` → pipeline returns `PipelineResult(ok=False)` → UI shows
error message. **Safe. Analysis does not proceed.**

**Scenario B — financial statements empty (fetch_financials returns `_fetch_success=False`)**

Path: Info succeeded, financials failed (P0 detected all-empty DataFrames). `fetch_ticker()`
returns financials stub with `_fetch_success=False` and empty statement dicts.
`data_loader.py` does NOT check `raw_financials._fetch_success`. It calls
`_normalize_fn(ticker, raw)` with `raw_financials = {"_fetch_success": False, "income_stmt": {}, ...}`.

The normalizer receives empty financial statements. It produces `CompanyFinancialMetrics`
with most financial fields as `None` or zero. `data_completeness_pct` will be low (likely
20–40% — price and basic info available, no historical financials).

The gate system then runs:
- Gate 2 (financial quality): `FinancialQualityAssessment` will score very poorly with no
  revenue history, no ROIC, no FCF data. This is designed to produce
  `WAIT_INSUFFICIENT_EVIDENCE` or `WAIT_DATA_INCOMPLETE`.
- The analysis DOES proceed — it does not short-circuit on empty financials.
- The final output will likely show WAIT with data quality warnings.

**Risk:** If Gate 2 does not catch the empty-financials case robustly, a partial analysis
could be presented. This has not been verified in the current code review without reading
the gate implementations. **This scenario should be explicitly tested.**

**Scenario C — price history missing (fetch_history returns `_fetch_success=False`)**

Path: Similar to Scenario B. `data_loader.py` does not check `raw["history"]._fetch_success`.
The normalizer does not use history data directly — history is used by ValuationBuilder for
DCF / CAGR calculations. If history is absent, DCF fair values will be affected.

The freshness assessment and valuation engine may produce degraded or incomplete valuations.
The risk is the same as Scenario B: whether the degradation is clearly communicated.

**Scenario D — partial financial data (some statements non-empty)**

Path: P0 fix only fires when ALL three statements are empty. If one statement is populated
(e.g., income statement but not cash flow), `_fetch_success=True` is set and partial data
is cached. Analysis proceeds with partial data. `data_completeness_pct` reflects this.
Gate 2 responds to data completeness. This path appears handled correctly.

**Scenario E — Yahoo returns a 429**

With the short-circuit fix: financials and history are skipped. Pipeline retries info fetch
up to 3 times with 30s/60s delays. If all fail, `cannot_complete_reason` is set →
`PipelineResult(ok=False)` → UI shows error. **Safe. Analysis does not proceed on 429.**

**Scenario F — cached data is stale**

Path: Cache TTL is 24h (info, history) or 48h (financials). Beyond TTL, `_load_cache`
returns `None` → fresh fetch attempted. If cache is expired and Yahoo rate-limits, Scenario E
applies.

If cache is within TTL but the underlying data has changed (e.g., earnings released),
the analysis uses stale data. The freshness assessment (`build_freshness_assessment()`)
computes staleness from the latest revenue year vs. analysis date. If stale,
`data_freshness_cap_applied=True` → UI shows warning, confidence capped at LOW.
This is the designed behavior.

### Summary of failure modes

| Scenario | Analysis runs? | User told? | Safe? |
|----------|:---:|:---:|:---:|
| info 429 / missing | No | Yes (error msg) | ✅ |
| financials empty (info ok) | Yes (degraded) | Partial (data quality warnings) | ⚠️ verify |
| history missing (info ok) | Yes (degraded) | Partial | ⚠️ verify |
| all 3 cached, stale | Yes (with warning) | Yes (freshness cap) | ✅ |
| 429 on retry → all fail | No | Yes (error msg) | ✅ |

**The most important open question** is Scenario B/C: whether the gate system reliably
produces a WAIT outcome (rather than a weak ACCUMULATE/REDUCE) when financials or history
are missing. This has NOT been verified in this review. A targeted test — mock
`fetch_financials` to return an empty-statement result with `info` succeeding — would
confirm or deny this.

---

## 6. Retry Strategy

### Is the current [30, 60] strategy appropriate for an interactive UI?

**No.** The retry loop was designed for a batch/scripted context where the user is not
waiting at a screen. In an interactive UI:

- The user submits a ticker and sees a spinner.
- With `[30, 60]`, if the first attempt fails with 429, the user waits **at minimum 30
  more seconds** before the second attempt, and **90 more seconds total** if all three
  fail. The spinner shows "Analysing MSFT… this may take 15–60 seconds" throughout.
- The live MSFT log shows 90+ seconds of silent waiting followed by a failure message.
- The user has no way to know they should wait and retry manually.

### What retries are actually useful for in an interactive UI

Automatic retries in the interactive UI are only useful if:
1. The retry window exceeds Yahoo's rate-limit window (so the final attempt succeeds).
2. The user experience of waiting is acceptable.

For condition (1): the MSFT failure shows Yahoo's window can exceed 97 seconds. Adding
more delay only helps if the window duration is bounded and predictable. It is not.

For condition (2): 30–90 seconds of invisible waiting (spinner only) is poor UX. A user
who waits 90 seconds to see an error message is more frustrated than a user who sees a
clear message in 5 seconds: "Yahoo is temporarily rate-limiting this ticker. Please wait
2 minutes and try again."

### Whether the UI should fail fast

**Yes, for the interactive case.** A better pattern is:
- Attempt 1: fetch immediately.
- If 429: stop. Tell the user immediately. Do not spin silently.
- The user decides when to retry manually.

### Whether retry behavior should differ between UI and batch

**Yes.** Retries with long delays are correct for batch pre-fetch (`fetch_portfolio()`),
where the user is not waiting and persistence matters. For the interactive pipeline,
fail-fast with a clear message is better UX.

The current architecture does not distinguish these modes. `_RETRY_DELAYS` is a single
constant in `pipeline.py` that affects all callers.

---

## 7. yfinance as a Data Provider

Based on code inspection and observed behavior, yfinance/Yahoo Finance is appropriate as:

**B — Development/demo data source:** It is free, requires no API key, covers global
equities including NSE (.NS), TSX (.TO), and US markets, and returns enough structured
data for the full pipeline. It is adequate for a portfolio demonstration tool.

**C — Cached historical data source:** Once fetched and cached, data is reliable for
analysis. The cache architecture (24/48h TTL, failure rejection) makes this workable.

It is **not appropriate** as:
- **A — Primary live data source** for a product where users expect reliable real-time
  data. Unauthenticated access is rate-limited by opaque, undocumented Yahoo rules.
  The YfData singleton means one 429 event can poison all subsequent requests in the
  same process.

No alternative provider is recommended here. The goal is MVP demonstration quality, not
institutional-grade reliability. yfinance is the correct choice for this stage — the
architecture should be adjusted to use it in its reliable mode (pre-cached), not its
unreliable mode (live, cold-cache, interactive).

---

## 8. Recommended Phase 10.x End State

**The goal:** A reliable demo where the user enters a ticker, sees a trustworthy analysis,
and can have a multi-turn conversation — without Yahoo 429 errors interrupting the demo.

**The insight:** The architecture is already correct for cached tickers. The only
vulnerability is cold-cache tickers. The fix is not to make cold-cache more reliable
(Yahoo controls that). The fix is to ensure demo tickers are never cold.

**The recommended end state** has two parts:

**Part 1 — Pre-warm the cache before demo.**  
Run a pre-fetch script for the tickers you plan to demo. With all 3 data types cached,
the Streamlit demo makes 0 Yahoo requests per "Analyse" click. 429 cannot occur.
This is reliable, requires no architecture change, and is the single most impactful
action available.

**Part 2 — Fix the interactive failure experience.**  
When a 429 occurs (cold-cache ticker added mid-demo), the UI should tell the user
immediately with a clear, actionable message rather than spinning silently for 90 seconds.
This is a small UI change.

**Part 3 (optional) — Wire `force_refresh` correctly.**  
The open defect means the "Force refresh" checkbox has no effect. Fix it when needed.

---

## 9. Options

---

### Option A — No code change: Pre-warm the cache before demo

**Files affected:** None. Manual workflow only.

**Complexity:** Zero. Run `python -c "from data.ingestion.fetcher import fetch_ticker; fetch_ticker('MSFT')"` for each demo ticker at least 30 minutes before the demo. Or write a one-time script (not committed to the repo).

**User experience:** During demo, all analyses are instant (cache hits). 0 Yahoo requests.
No 429 possible. If a cold ticker is added mid-demo, 429 may occur (current behavior).

**Reliability:** High for pre-warmed tickers. No improvement for unexpected cold tickers.

**Risks:** Cache expiry (24h for info/history, 48h for financials). If demo runs more than
24h after pre-warm, info and history will re-fetch. Easy to mitigate by warming 2–3 hours
before demo.

**Recommended:** Yes, as an immediate action regardless of which other option is chosen.
Pre-warming is always beneficial and has no code risk.

---

### Option B — Small reliability improvement: Fail fast + clear 429 message in UI

**Files affected:** `analytics/agent/pipeline.py`, `ui/app.py` (or
`conversation/manager.py`).

**Complexity:** Small. Two changes:
1. In `pipeline.py`: remove the retry loop from `run_analysis_pipeline()` (or make it
   conditional on a `batch_mode` flag), replacing it with a single attempt. If 429, return
   `PipelineResult(ok=False, error="Yahoo Finance is temporarily rate-limiting...")`.
2. In `ui/app.py` or `manager.py`: detect the 429 error string in `pipeline_result.error`
   and display a specific, actionable message: "Yahoo Finance is rate-limiting this ticker.
   Please wait 2–3 minutes and click Analyse again."

**User experience:** On 429: user sees a clear message in ~5 seconds rather than waiting
90 seconds for a failure. User knows what to do (wait and retry). On subsequent retry
(manually), if Yahoo's window has cleared, analysis succeeds.

**Reliability:** Same as current for warm-cache tickers. Better UX for cold-cache 429.
Does not increase 429 probability (removing retries reduces total requests per event).

**Risks:** Removes the chance that a retry at +90s would succeed. In practice, this is
acceptable: the user retrying manually after 2 minutes is equivalent to the third retry
at +90s, but with a better UX. If the demo explicitly needs hands-off retry, this is not
the right option.

**Recommended:** Yes. Complements Option A. Should be authorized as a small Phase 10.x
follow-on.

---

### Option C — Recommended MVP architecture: Separate pre-fetch from interactive analysis

**Files affected:** New script (`scripts/prefetch_demo.py`), `analytics/agent/pipeline.py`,
`ui/app.py` or `conversation/manager.py`.

**Complexity:** Moderate. Three parts:
1. **Pre-fetch script** (`scripts/prefetch_demo.py`): Takes a list of tickers, calls
   `fetch_ticker()` for each with 35s inter-ticker spacing, logs success/failure, saves
   to `data/cache/`. Run once before each demo session.
2. **Fail-fast in interactive pipeline** (same as Option B, part 1).
3. **Cache status indicator in UI**: Show the user whether the current ticker has a warm
   cache hit or is being fetched live. A simple indicator (`✓ Cached` vs `⟳ Live fetch`)
   sets expectations before the user clicks Analyse.

**User experience:** 
- Pre-demo: run `python scripts/prefetch_demo.py MSFT AAPL ITC.NS CNQ.TO`
- During demo: all analyses instant (cached), conversation works perfectly
- If an unexpected ticker is entered: user sees cache status indicator, and if 429 occurs,
  a clear message with wait time
- The demo narrative becomes: "Our agent fetches and caches financial data independently
  from the analysis. Let me show you an already-cached analysis of MSFT..."

**Reliability:** High for pre-cached tickers. Transparent and graceful for cold tickers.

**Risks:** Pre-fetch script requires a 35s inter-ticker gap → warming 10 tickers takes
~6 minutes. Must be done before demo. Adds one new file to maintain.

**Recommended:** Yes. This is the right end state for a reliable demo MVP. Option A is
the immediate tactical solution; Option C is the architecture that makes Option A
systematic and repeatable.

---

## 10. Final Recommendation

**Do Option A immediately (today).** Pre-warm your demo tickers before every demo session.
No code risk, no authorization needed, immediate effect.

**Authorize Option B for next implementation.** Two small, targeted changes: remove
automatic retries from the interactive pipeline path; add a specific, actionable 429
error message in the UI. This eliminates the 90-second frozen spinner and gives users
clear instructions. Files affected: `pipeline.py`, and one of `manager.py` or `app.py`.
Estimated complexity: ~30 lines changed.

**Defer Option C** until after a successful demo. The pre-fetch script adds real value
for a repeatable demo workflow, but it is not needed to fix the immediate problem, and
adding new scripts to the repo before a demo adds unnecessary risk.

**One thing to verify before next demo:** Confirm that the gate system (Gate 2 in
particular) produces a WAIT outcome — not a mistakenly affirmative recommendation — when
`fetch_financials()` succeeds for info but returns empty financial statements. This is the
one failure mode not fully verified in this review. A targeted mock test would close this.
