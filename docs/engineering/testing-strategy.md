# Testing Strategy

> **Status:** 1,228 tests passing, 1 skipped (as of Phase 10.6)  
> **Test runner:** pytest  
> **See also:** [Test Status](test-status.md) for current numbers

---

## What the test suite is for

The test suite exists to:

1. **Protect safe-failure modes.** The most important tests are those that verify the system cannot produce a false-positive recommendation when data is missing or degraded.
2. **Catch regressions.** When a change is made to the pipeline, tests confirm that existing correct behaviour has not broken.
3. **Document intent.** Test names and docstrings explain what the code is supposed to do.

The test suite does NOT:
- Verify that investment recommendations are correct for actual companies
- Test the Streamlit UI rendering
- Test against live Yahoo Finance data (network tests are isolated and skipped in CI-like environments)

---

## Test structure

Tests are in the `tests/` directory. Major test files:

| File | Phase | What it covers |
|------|-------|---------------|
| `tests/test_phase105.py` | 10.5 | Safe failure modes, rate-limit message quality, force refresh, MVP ticker list, data status |
| `tests/test_phase10_conversation.py` | 10 | Intent classification, follow-up routing, session state, conversation manager |
| `tests/test_fetcher_p0_p1.py` | 10.x | Fetcher cache behaviour, empty-data rejection, failed-fetch non-caching |
| `tests/test_phase99.py` | 9.9b | EPS/FCF period alignment, continuing-ops NI, same-window verification |
| `tests/test_valuation_*.py` | 5–9 | Valuation engine, DCF, multiples, synthesizer |
| `tests/test_decision_*.py` | 7 | Gate logic, decision synthesis, edge cases |
| `tests/test_financial_quality_*.py` | 3 | Quality assessment, threshold evaluation |

---

## What the Phase 10.5 tests specifically prove

`tests/test_phase105.py` (43 tests) is the most important Phase 10.5 artifact. It verifies:

### Safe failure mode (Gate 2 with empty data)
- `test_gate2_evaluate_with_empty_metrics_stays_watch` — confirms that a `FinancialQualityAssessment` with `_no_data=True` on all dimensions produces at most WATCH tier, never ACCUMULATE or EXCELLENT

### Rate-limit message quality (8 specific assertions)
Tests verify the friendly error message:
- Contains ticker name
- Contains "temporarily" or "limitation" language
- Does NOT contain: `CANNOT_COMPLETE_LIVE_ANALYSIS`, `yfinance`, `429`, `Yahoo Finance API`, `Exception`, `HTTPError`, `Traceback`, Python stack trace strings

### Force Refresh wiring
- `test_force_refresh_propagates` — confirms `force_refresh=True` in the UI reaches `fetch_ticker()` at the bottom of the call stack

### MVP ticker list
- Tests that `MVP_TICKERS` contains exactly 33 items
- Tests that all tickers are valid non-empty strings
- Tests that `MVP_TICKER_MAP` has matching keys

### Data status
- Tests that `get_ticker_data_status()` correctly reports cache freshness (fresh/stale/missing) based on file modification time and TTL

---

## Test philosophy

### Mocking policy

- **Mock the boundary, not the implementation.** Tests mock at the external API boundary (yfinance calls, Anthropic API calls) — not internal business logic.
- **Do NOT mock financial quality assessment with spec'd mocks.** Lesson from Phase 10.5: `spec=FinancialQualityAssessment` created a mock that didn't have all the required dimension attributes. Use plain `MagicMock` and set required attributes explicitly.
- **Do NOT use network calls in unit tests.** The 5 pre-existing failures in `test_phase93b` are all network-dependent tests that were written before this policy was established.

### Test naming convention

Test names follow: `test_{what}_{condition}_{expected_outcome}`

Examples:
- `test_gate2_evaluate_with_empty_metrics_stays_watch`
- `test_force_refresh_propagates_through_pipeline`
- `test_rate_limit_message_does_not_contain_yfinance`

### Arrange-Act-Assert

All tests follow the AAA pattern:
1. **Arrange:** Set up the inputs and mocks
2. **Act:** Call the code under test
3. **Assert:** Verify the expected outcome

---

## Running the tests

```bash
# Run all tests
pytest tests/ -v

# Run specific file
pytest tests/test_phase105.py -v

# Run and show output for failing tests
pytest tests/ -v --tb=short

# Run excluding network tests
pytest tests/ -v --ignore=tests/test_phase93b.py
```

---

## Pre-existing issues (not regressions)

### 3 collection errors

Three test files have naming conflicts in their legacy helper imports (an internal import structure issue unrelated to the tests themselves). These produce collection warnings but do not prevent the tests from running.

**Files affected:** (pre-existing — inspect `pytest` output for `ERROR collecting tests/` lines)

### 5 pre-existing failures

`tests/test_phase93b.py` contains 5 tests that attempt live Yahoo Finance network calls. These fail in any environment where network access is restricted (CI, sandbox, rate-limited sessions). These are pre-existing and were not introduced by Phase 10.5.

**They are not counted as regressions.** A Phase 10.5+ implementation report notes: "0 new failures introduced."

---

## Test coverage gaps (PROPOSED improvements)

| Gap | Risk | Proposed fix |
|-----|------|-------------|
| UI rendering (app.py) | A bug in app.py rendering wouldn't be caught | Playwright or Streamlit testing API smoke test |
| Valuation golden outputs | A normalisation change could produce wrong numbers without a test catching it | Baseline assertion test for ITC.NS (EPS ₹16.05, FCF ₹12.04) |
| Pre-warm script | Script could silently fail | Integration test with mocked yfinance |
| Conversation turn completeness | Follow-up handlers could be incomplete | Property-based tests on all 6 intent types |
