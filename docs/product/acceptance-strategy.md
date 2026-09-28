# Acceptance Strategy

> **Purpose:** How does the Product Owner know when work is done and safe?  
> **Scope:** Phase-level acceptance — not system-wide QA, not user testing (single-user product).

---

## Acceptance philosophy

This is a single-user product built by and for the same person. Classical QA (acceptance tester ≠ developer) does not apply. Instead, acceptance relies on three complementary signals:

1. **Automated tests** — do the expected behaviours pass programmatically?
2. **Real-ticker validation** — does the system produce sensible outputs for known tickers?
3. **PO inspection** — does the work satisfy the original specification?

A phase is accepted when all three signals are satisfied for that phase's scope.

---

## The three acceptance signals

### Signal 1 — Automated tests

**Purpose:** Protect known-correct behaviour from regression.

**What passes today:** 1,228 tests passing, 1 skipped.

**What tests prove:**
- Safe failure modes (empty data → conservative output, not a buy signal)
- Rate-limit error message quality (8 specific "must not contain" string assertions)
- Force Refresh wiring
- Gate behaviour with missing inputs
- Conversation intent handling
- Data freshness assessment

**What tests do NOT prove:**
- That the investment recommendation is correct for a given company
- That the analysis is complete for tickers with partial yfinance data
- That the UI renders correctly in a browser (no Streamlit UI tests)

**Pre-existing test issues (not regressions):**
- 3 collection errors — naming conflicts in legacy helper imports in 3 test files
- 5 failures — `test_phase93b` tests depend on live Yahoo Finance network (sandbox restriction)

---

### Signal 2 — Real-ticker validation

**Purpose:** Confirm that the system produces sensible, mathematically consistent outputs for actual companies.

**Primary validated baseline: ITC.NS (Phase 9.9b)**

| Metric | Verified value |
|--------|---------------|
| Normalised EPS | ₹16.05/share |
| Normalised FCF/share | ₹12.04/share |
| Period alignment | ✅ Same 3-year window (FY2024–FY2026) |
| Continuing-ops NI used | ₹197.31B (not ₹347.47B total) |

**What the baseline tells us:** The normalisation logic correctly excludes the ₹150.16B one-time demerger gain from EPS. Without this, EPS would be overstated by ~76%.

**Other tickers informally validated:** TD.TO, MSFT, AMZN (outputs reviewed but not formally baselined).

**PO guidance for future phases:** Any phase that touches valuation inputs, normalisation, or gate logic must re-verify ITC.NS produces the same baseline numbers before acceptance.

---

### Signal 3 — PO specification inspection

**Purpose:** Confirm the implemented feature matches what was requested.

**Process (for each phase):**
1. Phase brief defines explicit acceptance criteria before work starts
2. After implementation, PO reviews the acceptance criteria table
3. Each criterion is marked ✅ (verified) or ❌ (failed)
4. Work is not accepted until all criteria pass

**Phase 10.5 example — criteria verified at acceptance:**

| Criterion | Status |
|-----------|--------|
| Can select a ticker from the 33-ticker dropdown | ✅ |
| Can enter a custom ticker | ✅ |
| Rate-limit error shows friendly message | ✅ |
| Force Refresh actually forces a fresh fetch | ✅ |
| Cache freshness visible in UI | ✅ |
| Empty financials cannot produce positive recommendation | ✅ |
| No technical strings exposed in UI error messages | ✅ |
| Pre-warm script runs on Windows | ✅ |
| Full test suite passes (excluding pre-existing failures) | ✅ |

---

## What "ACCEPTED" means

When a phase is marked ACCEPTED:
- The acceptance criteria defined in the brief are verified as passing
- Automated tests pass (excluding pre-existing failures)
- The PO has reviewed the output and is satisfied
- **No code changes to that phase's scope will be made retrospectively** unless a new phase explicitly authorises them

A phase being ACCEPTED does not mean it is bug-free or complete for all possible inputs. Known limitations are documented separately in `docs/engineering/known-limitations.md`.

---

## Acceptance anti-patterns (what NOT to do)

| Anti-pattern | Risk |
|-------------|------|
| Accepting a phase without running the full test suite | Silent regression |
| Writing acceptance criteria AFTER implementation | Criteria shaped by implementation, not user need |
| Treating "tests pass" as sufficient for valuation logic | Tests cannot verify numerical correctness — real-ticker validation is required |
| Modifying production code while writing documentation | Documentation phase and implementation phase must be separate |
| Accepting a phase with known regressions | Technical debt hidden from PO |

---

## Acceptance for non-code phases

**Documentation phases (like 10.6):**
- Acceptance criteria: documents exist, are accurate, are clearly labelled (IMPLEMENTED / PROPOSED / RECONSTRUCTED), and do not contain fabricated claims
- PO can verify by spot-checking key claims against the source code

**Configuration changes:**
- Must be reflected in documentation
- Must not alter gate logic, valuation formulas, or decision philosophy without explicit PO authorisation

---

## Future: What stronger acceptance would look like

These are PROPOSED improvements — not currently implemented:

1. **Baseline regression suite:** A set of 5–10 "golden" ticker outputs that are automatically re-verified after any valuation or gate change
2. **UI smoke test:** Playwright or similar — verify that the Streamlit app starts, shows the dropdown, and completes an analysis for a cached ticker
3. **Decision audit log:** Record each analysis output to a file so the PO can review decisions made during the week
