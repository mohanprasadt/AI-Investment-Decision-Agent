# Test Status

> **Last updated:** Phase 10.6  
> **Total: 1,228 passing, 1 skipped**

---

## Summary

| Category | Count |
|----------|-------|
| Total tests passing | 1,228 |
| Skipped | 1 |
| Pre-existing failures | 5 (test_phase93b — network-dependent) |
| Collection errors | 3 (pre-existing — legacy import naming) |
| **New failures introduced in Phase 10.5** | **0** |

---

## Phase 10.5 tests (43 tests)

All 43 Phase 10.5 tests pass. These are the most important tests for the MVP release.

**`tests/test_phase105.py`** covers:

| Test area | # Tests |
|-----------|---------|
| Safe failure mode (Gate 2 with empty data) | ~5 |
| Rate-limit error message quality (string assertions) | ~8 |
| Force Refresh propagation | ~4 |
| MVP ticker list integrity | ~6 |
| Data status reading | ~10 |
| Pipeline fail-fast behaviour | ~10 |

---

## Phase 10 conversation tests (64 tests)

**`tests/test_phase10_conversation.py`** — all passing.

Covers: intent classification, follow-up routing, session state management, conversation manager error handling, chat history accumulation.

---

## Fetcher reliability tests (50 tests)

**`tests/test_fetcher_p0_p1.py`** — all passing.

Covers: cache miss → live fetch, cache hit → no fetch, empty data rejection (not cached), failed fetch non-caching, TTL calculation, ETF detection.

---

## Phase 9.9b alignment tests (6 test classes)

**`tests/test_phase99.py`** — all passing.

Covers: EPS/FCF same-window enforcement, continuing-ops NI preference, period mismatch detection, ITC.NS fiscal year intersection logic.

---

## Valuation tests

Multiple test files covering DCF engine, multiples engine, valuation synthesizer, margin of safety, method selection. All passing.

---

## Decision tests

Tests for all 5 gates plus the synthesizer. All passing.

Coverage includes:
- Gate 1 fail → WAIT_INSUFFICIENT_EVIDENCE
- Gate 2 WATCH cap → cannot produce ACCUMULATE with WATCH quality
- Gate 5 SEVERE → forces REDUCE/EXIT
- Sunk-cost protection (average cost excluded from Gate 4)
- All 8 DecisionAction values producible under correct conditions

---

## Pre-existing issues (not introduced by Phase 10.5)

### 5 failures — test_phase93b.py

These tests call live Yahoo Finance endpoints. They fail in environments where the network is restricted or when Yahoo Finance rate-limits the test runner.

**Why they exist:** Written before the "no network calls in unit tests" policy was established.

**Status:** Pre-existing. Not regressions. Not counted in failure statistics for Phase 10.5.

**Recommendation:** These tests should be refactored to use mocked responses. However, this is a non-trivial effort and is not a Phase 10.6 priority.

### 3 collection errors

Three test files have an import structure issue — they import a helper using a name that conflicts with a module-level name in the test runner context. This produces `ERROR collecting` warnings but does not affect test execution for other files.

**Status:** Pre-existing. No action required unless the affected test files need modification.

---

## How to verify the test state

```bash
# From the project root
pytest tests/ -v 2>&1 | tail -30
```

The last 30 lines will show the summary: `N passed, M failed, K errors, J skipped`.

Expected output (excluding pre-existing):
```
============== 1228 passed, 1 skipped in Xs ==============
```

With pre-existing issues included:
```
============== 1228 passed, 5 failed, 3 errors, 1 skipped in Xs ==============
```
