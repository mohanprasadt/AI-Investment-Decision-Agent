# Technical Debt

> **Purpose:** Honest inventory of known debt items and their priority  
> **Status:** Current as of Phase 10.6  
> **Rule:** No debt items may be addressed outside of a formally authorised phase

---

## What counts as technical debt here

Technical debt is a known deficiency in the code that:
- Makes the system harder to maintain, extend, or understand
- Increases the risk of future bugs
- Represents a deviation from what the code "should" be

Not included: limitations that are deliberate design decisions (those are in `known-limitations.md`).

---

## D1 — test_phase93b.py network-dependent tests [LOW PRIORITY]

**What it is:** 5 tests in `tests/test_phase93b.py` make live network calls to Yahoo Finance. They fail in rate-limited or network-restricted environments.

**Why it's debt:** Tests should be deterministic and environment-independent. Network-dependent tests are fragile, slow, and produce false failures.

**How to fix:** Replace live calls with mocked yfinance responses. Record real responses once and replay them.

**Effort:** Low  
**Risk of leaving as-is:** Low (5 tests fail on every CI-like run, but they are known and documented)

---

## D2 — 3 collection errors in test files [LOW PRIORITY]

**What it is:** Three test files have import naming conflicts that cause pytest to emit `ERROR collecting tests/...` during the collection phase. The tests themselves run, but the warnings are noisy.

**Why it's debt:** Noisy test output makes it harder to spot real errors.

**How to fix:** Rename the conflicting helper imports in the affected test files.

**Effort:** Very low  
**Risk of leaving as-is:** Low (cosmetic issue only)

---

## D3 — Valuation multiples are absolute, not peer-relative [MEDIUM PRIORITY]

**What it is:** Target multiples for P/E, EV/EBITDA, and P/FCF are derived from business quality assessments, not from actual peer comparisons. The `PeerData` model exists but is not populated.

**Why it's debt:** Absolute multiples are a second-best proxy. Peer-relative multiples would be more accurate and defensible.

**How to fix:** Implement automatic peer data fetching (Product Backlog B5), or define a curated peer mapping per ticker.

**Effort:** Medium  
**Risk of leaving as-is:** Medium (valuation output is less precise than it could be)

---

## D4 — D&A and working capital not separately persisted [LOW PRIORITY]

**What it is:** The normalizer doesn't extract depreciation/amortisation and working capital changes from the raw yfinance cash flow data. They are available in the raw data but discarded.

**Why it's debt:** This limits FCF reconciliation detail and EBITDA adjustment precision.

**How to fix:** Add fields to `CompanyFinancialMetrics` and extract them in `normalizer.py`.

**Effort:** Low  
**Risk of leaving as-is:** Low (analysis still works; reconciliation is less complete)

---

## D5 — No Streamlit UI smoke test [MEDIUM PRIORITY]

**What it is:** `ui/app.py` has no automated tests. UI regressions are caught only by manual inspection.

**Why it's debt:** The UI is the only way most users interact with the system. A broken UI is a broken product.

**How to fix:** Playwright or Streamlit testing API smoke test: app starts, dropdown shows, analysis completes for a cached ticker.

**Effort:** Medium  
**Risk of leaving as-is:** Medium (UI changes carry regression risk)

---

## D6 — `run_agent.py` demo paths [LOW PRIORITY]

**What it is:** `run_agent.py` contains hard-coded demo paths (CNR.TO demo) that were not extracted into `pipeline.py`. The comment in `pipeline.py` notes this explicitly.

**Why it's debt:** Inconsistency — the demo path bypasses the pipeline abstraction.

**How to fix:** Extract demo logic into a separate script or remove it entirely now that the Streamlit UI is the primary interface.

**Effort:** Low  
**Risk of leaving as-is:** Low (demo paths are not used in production)

---

## D7 — Journal and thesis templates not integrated [MEDIUM PRIORITY]

**What it is:** `journal/TEMPLATE_journal_entry.json` and `portfolio/thesis/TEMPLATE_thesis.json` exist as templates but there is no code to populate, read, or display them.

**Why it's debt:** Templates that reference non-existent functionality are confusing. Either integrate them or remove them.

**How to fix:** Integrate as Product Backlog B1 (decision journal), or remove the template files.

**Effort:** Low to remove; Medium to properly implement  
**Risk of leaving as-is:** Low (no runtime impact)

---

## D8 — yfinance normalizer field-name fragility [HIGH PRIORITY]

**What it is:** The normalizer maps hard-coded yfinance field names to structured fields. Yahoo Finance changes field names without notice. When this happens, fields silently return `None` rather than raising an error.

**Why it's debt:** A silent `None` produces a lower-confidence analysis without the user knowing why. A field-name change could reduce analysis quality for an entire market segment without a clear error.

**How to fix:** Add validation logging that alerts when expected fields are not found (beyond just recording in `data_quality_notes`). Maintain a test fixture of known-correct yfinance responses for key tickers.

**Effort:** Low (logging improvement) to Medium (test fixture)  
**Risk of leaving as-is:** High (yfinance field changes happen; silent degradation is hard to notice)

---

## D9 — No baseline assertion tests for ITC.NS valuation [HIGH PRIORITY]

**What it is:** The Phase 9.9b verification confirmed ITC.NS normalised EPS = ₹16.05, FCF/share = ₹12.04. But there is no automated test that asserts these numbers. A code change that accidentally breaks this produces no test failure.

**Why it's debt:** The ITC.NS baseline is the primary verified correctness checkpoint for the valuation engine. Without an automated assertion, it provides weaker protection than it should.

**How to fix:** Add a test in `test_phase99.py` or a new `test_baselines.py` that mocks the yfinance ITC.NS response and asserts the normalised output values.

**Effort:** Low  
**Risk of leaving as-is:** High (any change to normalisation or valuation builder could silently break the baseline)

---

## Debt priority summary

| Debt item | Priority | Effort | Risk of leaving |
|-----------|----------|--------|----------------|
| D8 — yfinance field-name fragility | High | Low–Medium | High |
| D9 — No baseline assertion test | High | Low | High |
| D5 — No UI smoke test | Medium | Medium | Medium |
| D3 — No peer-relative multiples | Medium | Medium | Medium |
| D7 — Unintegrated journal templates | Medium | Low–Medium | Low |
| D4 — D&A not separately persisted | Low | Low | Low |
| D1 — Network-dependent tests | Low | Low | Low |
| D2 — Collection errors | Low | Very low | Low |
| D6 — Demo paths in run_agent.py | Low | Low | Low |
