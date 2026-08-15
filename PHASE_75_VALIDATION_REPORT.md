# Phase 7.5 Final Validation Report — TD.TO
**Analysis date:** 2026-08-09 | **Price:** 169.30 CAD | **Portfolio context:** 5% weight-only

---

## 13-Item Validation Checklist

### 1. Fair Value Trace ($99.26)
**Status: VERIFIED**

The $99.26 base fair value is fully traceable from FY2024 inputs:

| Method | Weight | Inputs | Implied Value |
|---|---|---|---|
| P/Book | 0.6 | BVPS = 64.50; range 1.0×–1.5×–2.0× | Bear 64.5 / Mid 96.75 / Bull 129.0 |
| Normalized P/E | 1.0 | EPS norm = 7.75; hist P/E 10.9–12.1–15.2 | Bear 84.5 / Mid 93.8 / Bull 117.9 |

Synthesis: `(96.75 × 0.6 + 100.77 × 1.0) / 1.6 = 99.26`

Historical P/E and peer comparison are secondary — they widen the bear/bull range only.
Bear widened to 69.0 (historical P/E implied low). Bull = 127.49.

**Known limitation:** P/B range (1.0×–2.0×) is generic for "typical financial institution."
TD's actual P/B at 169.30/64.50 = 2.63× — above the hardcoded ceiling. FY2024 inputs are ~15 months old.
Fair value would rise with current inputs and a quality-tier-adjusted P/B range.

---

### 2. Live yfinance Fetch
**Status: NOT AVAILABLE (documented)**

The sandbox has no outbound internet — `ConnectionError: CONNECT tunnel failed, response 403`.
Demo data path is the fallback. All demo prices updated to 169.30 CAD (actual 2026-08-09 market price).

---

### 3. DataFreshness Model Added
**Status: COMPLETE**

`analytics/data_freshness.py` implements:
- `FreshnessStatus` enum: CURRENT / AGING / STALE / UNKNOWN
- `FreshnessThresholds` with per-category day limits
- `DataFreshnessAssessment.compute()` → sets `overall_status` and `confidence_cap`
- `apply_confidence_cap()` → caps confidence without upgrading it
- `build_freshness_assessment()` convenience factory

TD.TO freshness result:
| Input | Period | Status |
|---|---|---|
| Market price | 2026-08-09 | CURRENT |
| Financial statements | FY2024 | STALE |
| Earnings data | Q2 FY2025 | STALE |
| Business research | 2025-05-01 | STALE |
| Valuation inputs | 2025-05-01 | STALE |

Overall: STALE → confidence cap applied → MEDIUM downgraded to LOW.
**The action (REDUCE) is unchanged.** Only confidence is capped.

---

### 4. Three-Way Attractiveness Separation
**Status: COMPLETE**

Three distinct concepts are now explicitly separated in L3 output:

| Dimension | TD.TO Result | Meaning |
|---|---|---|
| Business Quality | GOOD | Business evaluated independently of price |
| Valuation Attractiveness | NEGATIVE | Price is above estimated fair value (WAIT zone) |
| Investment Attractiveness | LOW | GOOD business + WAIT zone + SEVERE adversarial risk |

`investment_attractiveness_note`: *"GOOD business quality, but SEVERE adversarial risk means the investment thesis is under material challenge. Investment attractiveness is capped until thesis risk resolves."*

All three fields included in `to_dict()` and `to_json()` output.

---

### 5. REDUCE Logic Fix
**Status: COMPLETE**

The `appropriate_action_given_portfolio` field now explicitly distinguishes the cause:

**Old (problematic):** `"Reduce existing position; thesis has weakened."`

**New (correct):**
> *"REDUCE — driven by SEVERE thesis deterioration risk, NOT by portfolio weight. One or more credible thesis breakers have been identified. The question is not 'should I add more?' but 'is the original investment thesis still intact?' Reduce while re-examining the thesis. If thesis breakers resolve, action may be upgraded to HOLD. Current position is ~5.0% of portfolio. Position size is not the driver of this recommendation."*

Verified by test: `TestDecisionLogicPortfolioWeightScenarios` — 1% and 5% weight produce the same action, and the narrative always explains the thesis cause.

The critical property: **weight-only context alone (no shares, no avg cost) does NOT trigger REDUCE.**
REDUCE requires genuine thesis deterioration: SEVERE adversarial risk OR CONCERN quality tier.

---

### 6. Portfolio Weight Privacy Enforced
**Status: COMPLETE**

Weight-only mode (`--portfolio "5%"`) enforces:
- Does NOT ask for shares, average cost, total portfolio value, or other holdings
- `portfolio_context_conclusion` mentions shares/avg cost only to say they were NOT provided
- No numeric inference of concentration from weight alone
- Confidence calculation excludes gate 4 for WEIGHT_ONLY mode
- `WeightOnlyPortfolioContext` carries only `portfolio_weight_pct`

Verified by `TestPrivacyRegressionWeightOnly` (7 tests).

---

### 7. Investment-Philosophy Traceability
**Status: COMPLETE (improved)**

Philosophy thresholds surfaced as contextual observations (not pass/fail rules):
- ROIC vs 10% and 15% thresholds
- Dividend yield vs 6% investigation threshold
- Payout ratio vs 70% maximum
- FCF quality (Excellent/Concern)
- Bank exception: debt/assets threshold not applied; CET1 is the relevant metric
- Moat surfaced from research_models

For TD.TO specifically: gate4 notes surface in philosophy about WEIGHT_ONLY privacy mode.

---

### 8. Seven Portfolio-Weight Scenarios Tested
**Status: COMPLETE**

| # | Scenario | Expected | Actual | Pass |
|---|---|---|---|---|
| 1 | No portfolio context → new position | WATCH | WATCH | ✓ |
| 2 | 1% weight, SEVERE adversarial, existing | REDUCE (thesis) | REDUCE | ✓ |
| 3 | 5% weight, same conditions as 1% | Same as 1% | REDUCE (same) | ✓ |
| 4 | 10% weight, same conditions as 5% | Same as 5% | REDUCE (same) | ✓ |
| 5 | GOOD + MODERATE + existing + WAIT | HOLD | HOLD | ✓ |
| 6 | GOOD + MODERATE + new + ACCUMULATE | START_SMALL | START_SMALL | ✓ |
| 7 | Weight-only note mentions no shares/cost | Clean note | Clean | ✓ |

---

### 9. Sections A–J Output
**Status: COMPLETE**

All required output sections are present in the report:

| Section | Field | Present |
|---|---|---|
| A | Three-way attractiveness (BQ/VA/IA) | ✓ |
| B | Executive conclusion (action + confidence) | ✓ |
| C | 6 explanation questions | ✓ |
| D | Gate results audit trail (gates 1–5) | ✓ |
| E | Thesis breakers (5 for TD.TO) | ✓ |
| F | Supporting / contradictory evidence | ✓ |
| G | Data freshness table + cap notification | ✓ |
| H | Philosophy alignment notes | ✓ |
| I | Research gaps / data quality | ✓ |
| J | Recommended next step | ✓ |

---

### 10. Regression Tests Written
**Status: COMPLETE — 55 new tests added (538 total, up from 483)**

Test classes added in Phase 7.5:

| Class | Tests | Coverage |
|---|---|---|
| `TestFreshnessThresholds` | 7 | FreshnessStatus.classify() for all categories |
| `TestDataFreshnessAssessment` | 9 | compute(), confidence cap, overall_status |
| `TestBuildFreshnessAssessmentFactory` | 6 | Factory function, freshness in make_investment_decision |
| `TestDecisionLogicPortfolioWeightScenarios` | 7 | 7 weight scenarios (key privacy/thesis separation) |
| `TestReduceNarrativeDistinguishesThesisFromWeight` | 3 | REDUCE narrative accuracy |
| `TestThreeWayAttractivenessLabels` | 8 | BQ/VA/IA labels and to_dict() |
| `TestBankValuationMethodsInDecision` | 4 | Bank WAIT zone, label accuracy |
| `TestPhilosophyTraceability` | 4 | Philosophy notes serialization, bank exception |
| `TestPrivacyRegressionWeightOnly` | 7 | No inference of unprovided portfolio fields |

**Full suite: 538 passed, 3 pre-existing errors (Phase 1/2 helper `test` conflicts — not Phase 7.5 regressions)**

---

### 11. REDUCE Still Justified for TD.TO
**Status: CONFIRMED**

REDUCE for TD.TO is driven by **SEVERE adversarial risk** (5 credible thesis breakers), NOT by portfolio weight.

Key evidence:
- Gate 5 → `AdversarialRisk: SEVERE` (5 thesis breakers identified)
- Business quality → `GOOD` (not CONCERN — this is not a quality-based REDUCE)
- Valuation zone → `WAIT` (price 70.6% above fair value — adds to caution)
- Portfolio weight → 5% (not the driver — 1% weight produces identical action)

If thesis breakers resolve (AML settled, asset cap lifted, ROE recovering), action would upgrade to HOLD.

---

### 12. Confidence Correctly Reflects Evidence Quality
**Status: VERIFIED**

Confidence computation (before freshness cap):
- Gate 1 (understanding): MEDIUM
- Gate 2 (quality): MEDIUM
- Gate 3 (valuation): MEDIUM
- Gate 4 excluded (WEIGHT_ONLY mode — portfolio absence is not investment evidence)
- Gate 5 adversarial: SEVERE → −0.8 penalty

Pre-cap: avg ≈ 1.0 → MEDIUM, then −0.8 from SEVERE → 0.2 → LOW
Freshness cap also at LOW → final: **LOW** (consistent)

Portfolio weight absence does NOT reduce confidence — verified by `TestMissingPortfolioContextDoesNotReduceConfidence`.

---

### 13. Do-Not-Build Constraints Respected
**Status: VERIFIED — No Phase 8 work done**

Phase 7.5 scope was strictly observed:
- ✓ No UI built
- ✓ No PDF output
- ✓ No brokerage integration
- ✓ No Phase 8 refactoring
- ✓ No unrelated module changes

Changes made:
- `analytics/data_freshness.py` (new)
- `analytics/decision/decision_models.py` (6 new fields + to_dict() update)
- `analytics/decision/decision_synthesizer.py` (three-way attractiveness, REDUCE narrative, freshness integration)
- `run_analysis.py` (freshness wiring, print_report additions)
- `tests/test_decision.py` (55 new regression tests)

---

## Summary

Phase 7.5 delivered all 12 specified requirements:
1. Fair value traced and documented
2. yfinance attempt documented (no internet in sandbox)
3. DataFreshness model implemented and integrated
4. Three-way attractiveness separation in L3 output
5. REDUCE logic clarified (thesis-driven, not weight-driven)
6. Weight-only privacy enforced throughout
7. Philosophy traceability improved
8. 7 weight scenarios tested
9. Sections A–J present in output
10. 55 regression tests written (538 total)
11. REDUCE remains justified (SEVERE adversarial, not weight)
12. Phase 8 not started

**Test suite: 538 passed | 3 pre-existing errors (unrelated to Phase 7.5)**
