# Assumptions, Risks, and Dependencies (RAID Register)

> **Purpose:** Single place to track what the product assumes to be true, what risks exist, and what it depends on  
> **Status:** Current as of Phase 10.6  
> **Format:** RAID (Risks, Assumptions, Issues, Dependencies)

---

## Assumptions

These are things the product assumes to be true. If any assumption turns out to be false, the product may need to change.

| # | Assumption | Consequence if false |
|---|-----------|---------------------|
| A1 | yfinance will continue to provide adequate financial data for the MVP ticker universe | Data layer fails; would need to replace data source |
| A2 | Yahoo Finance rate limits will not become so aggressive that cached data cannot be refreshed within a reasonable time window | Cache becomes permanently stale; pre-warm fails |
| A3 | The Anthropic Claude API will continue to be available at reasonable cost | Business research fails; all analyses produce WAIT_INSUFFICIENT_EVIDENCE |
| A4 | Financial statements from Yahoo Finance are sufficiently accurate for the analysis to be useful | Recommendations may be based on incorrect data; no automated detection |
| A5 | The investment philosophy in `config/investment_philosophy.md` reflects the investor's actual values and remains stable | All gate logic would need to be revisited |
| A6 | A single user accesses the system at a time on a single machine | Cache consistency, session isolation, and concurrent access are not problems |
| A7 | The 33 MVP tickers are all tradeable equities (not deregistered, not merged, not changed symbols) | Analysis for affected tickers fails; ticker list needs maintenance |
| A8 | yfinance continuing-operations NI will be available for most tickers (especially Indian stocks) | EPS normalisation falls back to total NI; overstatement risk for tickers with large one-time items |

---

## Risks

Risks are events that could occur and would have a negative impact if they do.

### R1 — Yahoo Finance rate limiting prevents demo [LIKELIHOOD: HIGH, IMPACT: HIGH]

**Description:** During a demo or planned analysis session, Yahoo Finance rate-limits requests. The pre-warm cache is too old to use.

**Current mitigation:** Run prewarm_mvp.py immediately before the demo. Cache TTLs give a 24–48h window.

**Residual risk:** If Yahoo Finance rate-limits the pre-warm script itself (which has happened), the cache may not fully refresh.

**Proposed additional mitigation:** Automated cache refresh on a schedule (Product Backlog B13).

---

### R2 — yfinance field name change breaks normalizer [LIKELIHOOD: MEDIUM, IMPACT: MEDIUM]

**Description:** Yahoo Finance silently renames an internal field. The normalizer looks for the old name, returns `None`, and the analysis proceeds with a missing field. The investor does not know the data is wrong.

**Current mitigation:** `data_quality_notes` records missing fields. The renderer surfaces data completeness %.

**Gap:** There is no alert when a previously-present field suddenly returns `None` for all tickers. This would look like "data not available for this ticker" rather than "the field name changed."

**Proposed mitigation:** Technical debt D8 — add validation logging.

---

### R3 — Valuation correctness regression [LIKELIHOOD: LOW, IMPACT: HIGH]

**Description:** A code change to the normalizer or valuation builder accidentally breaks the ITC.NS baseline. The incorrect numbers pass all tests because there is no baseline assertion test.

**Current mitigation:** The ITC.NS baseline is documented in the README and in `docs/logic/valuation-logic.md`. Manual verification is required after any normalizer or valuation change.

**Gap:** No automated test asserts the specific baseline numbers.

**Proposed mitigation:** Technical debt D9 — add baseline assertion test.

---

### R4 — Claude API response quality degrades [LIKELIHOOD: LOW, IMPACT: MEDIUM]

**Description:** A new Claude model version changes the structure or quality of business research responses. The system still runs but produces lower-quality or structurally incompatible research.

**Current mitigation:** None. The system does not validate the structure of Claude API responses.

**Proposed mitigation:** Response schema validation and alerting (not currently prioritised).

---

### R5 — yfinance package abandonment [LIKELIHOOD: LOW, IMPACT: SEVERE]

**Description:** The yfinance Python package is abandoned or Yahoo Finance blocks it entirely.

**Consequence:** All live data fetching fails. Cached data can be used until it expires, but no fresh data is possible.

**Mitigation:** Pin to last working version. If this occurs, the data layer would need to be replaced — a significant engineering effort.

---

### R6 — Session state loss during demo [LIKELIHOOD: MEDIUM, IMPACT: LOW]

**Description:** Browser refresh or accidental tab close during a demo clears the Streamlit session state. The analysis must be re-run.

**Current mitigation:** None.

**Proposed mitigation:** Product Backlog B12 (persistent sessions) or user education ("don't refresh the browser during a demo").

---

## Issues (active)

Issues are problems that have already materialised.

| # | Issue | Status |
|---|-------|--------|
| I1 | KTKBANK.NS has partial cache (1 of 3 files) | Known; pre-warm produced partial data; re-run prewarm to attempt refresh |
| I2 | 5 tests in test_phase93b.py fail in network-restricted environments | Pre-existing; not a regression |
| I3 | 3 pytest collection errors in legacy test files | Pre-existing; cosmetic |

---

## Dependencies

| # | Dependency | Type | Criticality | What breaks without it |
|---|-----------|------|-------------|----------------------|
| D1 | yfinance | Data | Critical | All financial data unavailable |
| D2 | Yahoo Finance (upstream) | External service | Critical | yfinance cannot fetch data |
| D3 | Anthropic Claude API | AI service | Optional | Business research unavailable; all analyses → WAIT_INSUFFICIENT_EVIDENCE |
| D4 | ANTHROPIC_API_KEY env var | Configuration | Optional | Same as D3 |
| D5 | Python 3.10+ | Runtime | Required | Code does not run |
| D6 | Streamlit | Framework | Required for UI | UI does not start; CLI still works |
| D7 | Local filesystem (data/cache/) | Storage | Required | No cache; all analysis requires live data |
| D8 | Internet connection | Network | Required for live data | Can only use cached data |
