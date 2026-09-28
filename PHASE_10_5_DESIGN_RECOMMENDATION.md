# Phase 10.5 — Architecture Design Recommendation

**Date:** 2026-08-16  
**Status:** Design only. No code written. Awaiting authorization.  
**Prepared by:** Code inspection of all production files + test suite.

---

## 1. Current-State Assessment

### What exists today

| Area | Current state |
|------|--------------|
| Ticker input | Free-text field only — user must know and type ticker symbols |
| MVP ticker universe | Not defined anywhere in the codebase |
| Cache coverage | 3/33 MVP tickers have data: ENB.TO, FTS.TO, TATASTEEL.NS (all ~23h old) |
| Data source visibility | None. UI never tells you if data came from cache or live fetch |
| 429 error message | Raw technical text: "CANNOT_COMPLETE_LIVE_ANALYSIS: yfinance returned no data... Reason: 429 Client Error: Too Many Requests" reaches the UI |
| force_refresh wiring | Broken: `pipeline.py` receives the flag but does not pass it to `load_ticker()` or `fetch_ticker()`. The "Force refresh" checkbox has no effect. |
| Pre-warm tooling | `scripts/refresh_portfolio.py` exists but requires a `portfolio_snapshot.csv` file — it is portfolio-based, not MVP-universe-based |
| Demo/test mode | None |
| Safety (empty financials) | Partially safe — see Section 2 |

### What the baseline test suite shows (1,189 tests)

All existing Phase 9.9b and Phase 10 tests pass. Six pre-existing failures are:
network-dependent tests in the sandbox (test_phase93b), one flaky ordering issue, and three
collection errors. None are caused by Phase 10.x fixes.

---

## 2. Safety Analysis — Critical Finding

**Question: Can the agent produce a positive investment recommendation when financial statements are empty?**

Traced through the complete production path:

### Path A — No ANTHROPIC_API_KEY (quantitative fallback)

```
fetch_financials → _fetch_success=False → normalizer returns data_completeness=0.0
→ quality_engine → FinancialQualityAssessment (all dimensions None/data_available=False)
→ ResearchOrchestrator → research=None (quantitative fallback, no API key)
→ Gate 1: research is None → FAIL → WAIT_INSUFFICIENT_EVIDENCE
```

**Result: Safe.** Analysis stops at Gate 1. No investment action is generated.

### Path B — With ANTHROPIC_API_KEY

```
fetch_financials → _fetch_success=False → normalizer returns data_completeness=0.0
→ quality_engine → FinancialQualityAssessment (all dimensions None/data_available=False)
→ ResearchOrchestrator → research = BusinessResearchAssessment (from Claude API)
→ Gate 1: research is not None → PASS (research was obtained)
→ Gate 2: financial_quality has 0 populated dimensions
         quality_scores = [] (all dimensions have data_available=False, no scores added)
         _compute_tier([]) → QualityTier.WATCH (explicit: "if not scores: return QualityTier.WATCH")
→ Gate 3: valuation — ValuationBuilder receives CompanyFinancialMetrics with:
          revenue_series={}, fcf_current=None, etc.
          DCF, multiples, P/FCF all produce None/unreliable
          ValuationAssessment with few/no methods → zone likely UNCERTAIN or WAIT
→ Synthesizer: WATCH quality + UNCERTAIN/WAIT valuation → WATCH (not ACCUMULATE/START_SMALL)
```

**Result: Likely safe but NOT verified by existing tests.**

The WATCH quality tier is set by the explicit `if not scores: return QualityTier.WATCH` branch in
`gate2_quality.py`. A WATCH tier prevents START_SMALL and ACCUMULATE actions (those require GOOD
or better quality). The worst plausible outcome with empty financials + API key is WATCH — a
neutral observation, not a buy signal.

**However:** This path is not covered by any existing test. A targeted test — ANTHROPIC API key
scenario with empty financials — must be written as part of Phase 10.5 to formally verify the
safety invariant.

### Other scenarios

| Scenario | Path | Safe? | Verified? |
|----------|------|:---:|:---:|
| 429 — info fails | short-circuit → cannot_complete_reason → no decision | ✅ | ✅ |
| 429 — all retries fail | pipeline returns PipelineResult(ok=False) → error message | ✅ | ✅ |
| Invalid ticker | empty info → cannot_complete_reason → error message | ✅ | ✅ |
| Stale cache | freshness assessment caps confidence at LOW; action NOT changed | ✅ | ✅ |
| financials empty (no API key) | Gate 1 fails → WAIT_INSUFFICIENT_EVIDENCE | ✅ | ✅ |
| financials empty (API key) | WATCH quality tier, UNCERTAIN valuation → WATCH | ⚠️ likely | ❌ |
| partial financials (some missing) | data_completeness_pct reflects gaps; Gate 2 scores only available dims | ✅ | partial |
| cash flow missing | FCF = None; valuation uses price-based methods only; low confidence | ✅ | partial |

**Phase 10.5 must add tests for the unverified paths.** No code change to the investment engine
is needed — only targeted test coverage to confirm the existing behavior.

---

## 3. Proposed Phase 10.5 Architecture

### Architectural principle maintained

```
Yahoo Finance (provider)
     ↓ (isolated)
fetcher.py (network layer)
     ↓
data/cache/ (local disk cache)
     ↓
data_loader.py (validated data)
     ↓
pipeline.py (orchestration)
     ↓
Investment intelligence (unchanged)
     ↓
ConversationManager (unchanged)
     ↓
Streamlit UI (Phase 10.5 changes here)
```

Phase 10.5 changes are concentrated in:
- A new data layer module (`data/mvp_tickers.py`)
- A new UI utility module (`ui/data_status.py`)
- A new pre-warm script (`scripts/prewarm_mvp.py`)
- Targeted fixes in `pipeline.py` and `data_loader.py` (force_refresh + fail-fast)
- Modest changes to `ui/app.py` and `conversation/manager.py` (UI improvements)
- New test file (`tests/test_phase105.py`)

### Capability A — MVP ticker universe module

**New file:** `data/mvp_tickers.py`

A single source of truth for the 33 approved MVP tickers. Contains:
- Ticker symbol
- Display name (known a priori — no API call needed)
- Market/region label
- Exchange

This module is imported by the UI for the ticker selector and by the pre-warm script.
It has zero dependencies on yfinance or any external service.

Company names are hardcoded from known information (these are all well-known public companies).
If the cache has a `longName` for a ticker, the UI can prefer that — but the module provides
a sensible fallback so the selector is populated even before any data is fetched.

### Capability B — Data status visibility

**New file:** `ui/data_status.py`

A module that reads cache files directly and computes status metadata without triggering
any network requests. This module exposes:

- `get_ticker_cache_status(ticker) → dict` — returns source, age, completeness, fetch timestamp
- `get_mvp_universe_status() → list[dict]` — status for all 33 tickers (for pre-warm panel)

The existing `_fetched_at` field in cache files already provides what we need.
The existing `data_completeness_pct` in the normalizer output already provides completeness.
The existing `freshness` object already provides staleness.

The UI shows a DATA STATUS card after each analysis:
```
DATA STATUS — MSFT
Source:      Local cache   ← or "Live (just fetched)" or "Unavailable"
Cache age:   3.2 hours
Financials:  FY2024 (12/31/2024)
Completeness: 92%
Status:      ✓ Ready for analysis
```

### Capability C — Safe cold-cache failure (fail-fast + friendly error)

**Modified file:** `analytics/agent/pipeline.py`

Remove the `[30, 60]` retry loop from the interactive pipeline path. Replace with:
- Single attempt
- If 429 detected: immediately return `PipelineResult(ok=False, error_type="RATE_LIMITED")`
- No more 90-second frozen spinner

**Modified file:** `conversation/manager.py`

Add 429-specific detection in `_format_pipeline_error()`:
```
"Live data temporarily unavailable for MSFT.
Yahoo Finance is currently rate-limiting requests. No investment decision was generated.
→ Wait 2–3 minutes and click Analyse again, or select a ticker with cached data."
```

Distinguish clearly:
- Rate limited (429) → "try again in a few minutes"
- Invalid ticker → "check the ticker symbol"
- Incomplete data → "data was fetched but too incomplete for analysis"
- Valid cached data → normal analysis

**Note on retries:** Retries with delays belong in a batch/pre-warm context, not in the
interactive UI. The pre-warm script will use delays; the interactive pipeline will not.

### Capability D — Pre-warm script

**New file:** `scripts/prewarm_mvp.py`

A Windows-compatible script that:
1. Reads the 33-ticker MVP universe from `data/mvp_tickers.py`
2. Checks existing cache status for each ticker
3. Skips tickers whose cache is valid (info < 24h, financials < 48h, history < 24h)
4. Fetches only missing/expired tickers
5. Uses a 35-second inter-ticker gap (validated by diagnostic Suite 3 as safe)
6. Prints a clear status table before and after

Output example:
```
MVP DATA PRE-WARM STATUS
========================
ENB.TO     SKIP    Cache valid (info: 2.1h, fin: 2.1h, hist: 2.1h)
FTS.TO     SKIP    Cache valid
SU.TO      FETCH   No cache
CNQ.TO     FETCH   No cache
...

Fetching 30 tickers with 35s gap... estimated: ~17 minutes
[1/30] SU.TO...     ✓ OK (6.2s)
[2/30] CNQ.TO...    ✓ OK (5.8s)
...
```

This script is designed to be run once before a demo session. It is NOT a background service.

### Capability E — Demo/Test mode decision

**Recommendation: No separate synthetic demo mode. Cache = demo mode.**

Rationale:
- The repository has no pre-existing stored financial datasets for real companies
- The normalizer's synthetic data (in `__main__`) is a test utility for a fictional company —
  using it as "demo mode" would be misleading and require labeling it clearly as fake
- The test fixture builders in `test_decision.py` represent fictional tickers (TEST.TO, CNR.TO
  proxy) — exposing them to the UI would be misleading
- The cleanest and most honest demo mode is: **pre-warm the cache, then run from cache**

What this means in the UI:
- A cache-warm indicator shows which tickers are ready
- The PO runs `prewarm_mvp.py` once before the demo
- During the demo, all analyses are cache-hits = instant, 0 Yahoo requests, 0 risk of 429
- The UI clearly labels: "Source: Local cache (2.3h old)"

If the PO later wants a fully offline synthetic demo (e.g., for an environment with no internet at all), that is a Phase 10.6 decision — it requires deliberately constructing realistic financial datasets for specific companies, which is non-trivial and must be labeled clearly.

### Capability F — force_refresh fix (required for Capability C)

**Modified file:** `analytics/agent/data_loader.py`

Add `force_refresh: bool = False` parameter to `_default_fetch` and `load_ticker`.
Pass it through to `fetch_ticker(ticker, force_refresh=force_refresh)`.

**Modified file:** `analytics/agent/pipeline.py`

Pass `force_refresh=force_refresh` to `load_ticker()`.

This is a small, contained fix that makes the existing "Force refresh" checkbox actually work.

---

## 4. Files That Need Modification

| File | Change | Risk |
|------|--------|------|
| `analytics/agent/pipeline.py` | Remove retry from interactive path; fix force_refresh wiring | Low |
| `analytics/agent/data_loader.py` | Add force_refresh parameter to load_ticker + _default_fetch | Low |
| `conversation/manager.py` | Improve 429 error message in _format_pipeline_error | Very low |
| `ui/app.py` | Add MVP ticker selector; add data status card; remove force_refresh checkbox (now only in script) | Medium |

---

## 5. New Files Required

| File | Purpose |
|------|---------|
| `data/mvp_tickers.py` | 33-ticker MVP universe with display metadata |
| `ui/data_status.py` | Cache status reader, data source display, status card renderer |
| `scripts/prewarm_mvp.py` | Pre-warm / cache status script for demo preparation |
| `tests/test_phase105.py` | Phase 10.5 tests (safety, MVP universe, pre-warm, status, error messages) |

---

## 6. Files That Must NOT Be Touched

| File | Reason |
|------|--------|
| `analytics/decision/` (all 5 gates + synthesizer) | Investment engine — Phase 10.5 prohibition |
| `analytics/valuation/` (all files) | Valuation methodology — untouched |
| `analytics/financial_quality/` (all files) | Financial quality calculations — untouched |
| `analytics/business_research/` | Business research models — untouched |
| `analytics/agent/investment_agent.py` | Agent logic — untouched |
| `analytics/agent/renderer.py` | Report rendering — untouched |
| `analytics/agent/research_orchestrator.py` | Research — untouched |
| `analytics/agent/valuation_builder.py` | Valuation input builder — untouched |
| `data/ingestion/fetcher.py` | Fetch/cache layer — untouched (force_refresh already works at this level) |
| `data/ingestion/normalizer.py` | Normalization — untouched |
| `conversation/session.py` | Session model — untouched |
| `conversation/intent.py` | Intent classifier — untouched |
| `config/` (all files) | Investment philosophy and thresholds — untouched |
| All existing test files | No modifications to passing tests |
| `analytics/data_freshness.py` | Freshness model — untouched |

---

## 7. Test Strategy

**New test file:** `tests/test_phase105.py`

Minimum test coverage required:

| # | Test | What it verifies |
|---|------|-----------------|
| 1 | Valid cached ticker | Cache hit → analysis proceeds with "Source: Local cache" status |
| 2 | Missing cache | No cache → fresh fetch attempted (mocked) |
| 3 | Successful fresh fetch | Mocked successful fetch → analysis succeeds, source = "Live" |
| 4 | Yahoo 429 → fail-fast | Pipeline returns immediately with rate-limit error, no retries |
| 5 | 429 error message is friendly | Manager formats message in PO language, no raw HTTP text |
| 6 | Empty financial statements (no API key) | Gate 1 fails → WAIT_INSUFFICIENT_EVIDENCE, not a buy signal |
| 7 | Empty financial statements (with API key mock) | Gate 2 → WATCH tier, action ≠ ACCUMULATE or START_SMALL |
| 8 | Partial financial statements (income only) | data_completeness < 100%; analysis degrades gracefully |
| 9 | Failed cache entry (P1) | _fetch_success=False in cache → treated as miss, retry attempted |
| 10 | Valid cache entry | _fetch_success=True, within TTL → cache hit, no network call |
| 11 | MVP ticker universe integrity | All 33 tickers present, no duplicates, correct count |
| 12 | Pre-warm skips valid cache | fetch_ticker NOT called for a ticker with fresh cache |
| 13 | Pre-warm fetches expired cache | fetch_ticker IS called when cache is missing or expired |
| 14 | force_refresh wires correctly | force_refresh=True passed through pipeline → data_loader → fetcher |
| 15 | Invalid ticker error message | PO-friendly message, not raw "CANNOT_COMPLETE_LIVE_ANALYSIS" |
| 16 | Cache status read | data_status module reads cache age, source, completeness without network call |

**Test run sequence after implementation:**
1. `pytest tests/test_phase105.py -v` — new tests only
2. `pytest tests/test_fetcher_p0_p1.py tests/test_phase10_conversation.py tests/test_phase10_ui.py -v` — Phase 10.x and 10 baseline
3. `pytest tests/ -q` — full regression

---

## 8. Risks and Trade-offs

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Removing retries from interactive pipeline breaks a test | Low | test_fetcher_p0_p1.py TestPipelineRetrySchedule tests `_RETRY_DELAYS` by source inspection — will need to update those tests or keep the constant for batch use |
| force_refresh wiring touches data_loader.py | Low | Change is additive (new optional parameter with default=False); backward compatible |
| UI ticker dropdown adds complexity | Medium | Start with a simple selectbox + search; keep text input as fallback for non-MVP tickers |
| Company names in mvp_tickers.py may diverge from yfinance longName | Very low | mvp_tickers.py names are fallbacks; UI prefers cache longName when available |
| Pre-warm 33 tickers at 35s gaps = ~19 minutes | Acceptable | Must be run before demo, not during. Well-documented in script output. |
| Retry removal for interactive pipeline affects existing retry tests | Medium | The retry constant can remain for batch use; the interactive path's behavior changes. Need to update `TestPipelineRetrySchedule` to reflect that interactive = 1 attempt. |

---

## 9. Recommended Implementation Sequence

The sequence is ordered to: (a) prove safety first, (b) deliver the most valuable UX improvement early, (c) keep each step independently testable.

**Step 1** — MVP ticker universe (`data/mvp_tickers.py`)  
Foundation for everything else. No dependencies, no risk.

**Step 2** — Safety test coverage (`tests/test_phase105.py`, tests 6–7)  
Verify the empty-financials safety invariant before any UI changes. If a defect is found,
fix it before proceeding. If no defect (expected), document it formally.

**Step 3** — force_refresh fix (`data_loader.py` + `pipeline.py`)  
Small, isolated, low-risk. Makes the existing "Force refresh" checkbox work.

**Step 4** — Fail-fast 429 + friendly error message (`pipeline.py` + `manager.py`)  
Eliminates the 90-second frozen spinner. Highest immediate UX value.

**Step 5** — Cache status module (`ui/data_status.py`)  
Read-only, no network calls. Provides the data source display.

**Step 6** — UI improvements (`ui/app.py`)  
Add MVP ticker selector, data status card, improved error display.

**Step 7** — Pre-warm script (`scripts/prewarm_mvp.py`)  
Standalone script. No production code dependencies.

**Step 8** — Complete test suite (`tests/test_phase105.py`, all remaining tests)  
Run full regression. Report results.

---

## 10. Specific Design Decisions Requiring Your Confirmation

Before implementation begins, please confirm these choices:

**Decision 1 — Retry behavior in interactive pipeline**  
The current `[30, 60]` retry schedule is in `pipeline.py`. Removing it from the interactive
path means a 429 gets an immediate, clear error message instead of a 90-second spinner.

- **Option A (recommended):** Remove retries from interactive path entirely. Fast fail + clear message.
- **Option B:** Keep retries but add a visible progress message in the UI (requires Streamlit spinner text updates, more complex).

**Decision 2 — Ticker input UI**  
The current UI has a plain text input.

- **Option A (recommended):** Replace with a searchable dropdown of the 33 MVP tickers. Add a small "Use custom ticker" text input below it for non-MVP tickers.
- **Option B:** Add the dropdown as a separate panel ("Quick Select from MVP Universe") but keep the existing text input as the primary input. More cluttered but more flexible.

**Decision 3 — force_refresh**  
The "Force refresh" checkbox is broken. Options:

- **Option A (recommended):** Fix the wiring and keep the checkbox. PO should be able to force a fresh fetch when desired.
- **Option B:** Remove the checkbox entirely. Pre-warm script handles refreshing. Simpler UI.

**Decision 4 — Demo/test data mode**  
Based on inspection, no suitable real-company fixture data exists for demo mode.

- **Option A (recommended):** Cache = demo mode. The pre-warm script prepares data; the UI clearly labels cache-sourced analyses. No synthetic data.
- **Option B:** Explicitly mark 2–3 tickers (e.g., ENB.TO, FTS.TO) as "always available demo tickers" and ship their cache data in the repository as committed JSON files. PO can always analyze these even without internet.

Option B is achievable (commit the 3 current cache files) but has a maintenance implication: the committed data ages. It could be labeled "Demo data — as of [date]" in the UI to be transparent.

---

## 11. Acceptance Criteria Mapping

| PO Success Criterion | How Phase 10.5 delivers it |
|---------------------|---------------------------|
| See 33 MVP tickers in UI | `data/mvp_tickers.py` + ticker selector in `ui/app.py` |
| Know if data is fresh/cached/unavailable | Data status card via `ui/data_status.py` |
| 429 does not cause long spinner | Fail-fast in `pipeline.py` + interactive path change |
| 429 does not produce a decision from incomplete data | Already true; formally verified by new safety tests |
| Practical pre-warm mechanism | `scripts/prewarm_mvp.py` |
| Test conversational experience with cached data | Pre-warm + cache-sourced analysis + full conversation layer works off cache |
| Investment engine logic unchanged | Gated explicitly in "do not touch" list |
| Phase 9.9b and Phase 10 behavior intact | Full regression suite run; 1189+ existing tests pass |
| All new tests pass | `tests/test_phase105.py` run clean |

---

## Summary

Phase 10.5 is achievable in one implementation session with low risk. The critical path is:

1. Safety test (confirms no investment engine defect found)
2. Fail-fast 429 + friendly error message (highest immediate value)
3. MVP ticker selector + data status card (PO testing experience)
4. Pre-warm script (demo preparation)
5. Full test run

No changes to the investment intelligence engine are anticipated. The safety analysis
indicates the existing gate system correctly handles empty financial data, but explicit
test coverage is required to formally verify this.

**Awaiting your authorization and confirmation of the four design decisions above before implementation begins.**
