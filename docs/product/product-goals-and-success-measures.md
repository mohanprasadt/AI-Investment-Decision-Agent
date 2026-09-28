# Product Goals and Success Measures

> **Important:** This document distinguishes between goals that emerge clearly from the project and measures that are **PROPOSED** by the Product Owner framework. No fabricated "already agreed" success criteria are presented here.

---

## Established product goals

These goals are clearly evidenced by the project — in the investment philosophy, architecture decisions, and implemented gates.

### Goal 1: Produce a structured, explainable investment decision

The system must output not just a recommendation but the reasoning behind it. A "black box" recommendation has no value because the investor cannot evaluate whether to trust it.

**Evidence:** `InvestmentDecisionAssessment` contains gate results, quality tier, valuation zone, adversarial risk, and supporting/contradictory evidence for each dimension.

### Goal 2: Never produce a positive recommendation from insufficient evidence

`WAIT_INSUFFICIENT_EVIDENCE` is a first-class, correct output. The system must prefer caution over false confidence.

**Evidence:** Gate 1 forces `WAIT_INSUFFICIENT_EVIDENCE` when business research is absent. Gate 2 produces `WATCH` (not `ACCUMULATE`) when financial data is empty. Verified by tests in `test_phase105.py`.

### Goal 3: Protect portfolio privacy

The investor's shares, cost basis, and account value must never be requested, stored, or used. Portfolio weight (%) is sufficient context.

**Evidence:** `ConversationSession` stores only `portfolio_weight_pct`. The constraint is documented in code comments and enforced by design.

### Goal 4: Produce consistent, repeatable analysis

Running the same ticker twice with the same data should produce the same decision. The system is deterministic (given the same data).

**Evidence:** Deterministic decision gates; no randomness in the decision path.

### Goal 5: Be transparent about data quality and staleness

The system must clearly communicate when data is old, partial, or unavailable rather than silently producing lower-confidence outputs.

**Evidence:** `DataFreshnessAssessment`, `data_quality_notes`, data completeness %, data status panel in UI.

### Goal 6: Support the investor's philosophy, not override it

The system encodes the investor's documented philosophy (`config/investment_philosophy.md`) and must not deviate from it.

**Evidence:** Philosophy is explicitly documented and referenced in gate logic, threshold configuration, and valuation configuration.

---

## PROPOSED success measures

**Label: PROPOSED — NOT YET AGREED**

The following measures are proposed as useful for evaluating whether the product is working. None are currently tracked systematically. The Product Owner should decide which to adopt.

| # | Measure | Why it matters | How to assess |
|---|---------|---------------|---------------|
| M1 | Analysis completion rate | Can you get a decision for a typical ticker? | % of tickers where analysis completes vs fails |
| M2 | Decision explainability | Can you understand why the recommendation was made? | After reading the output, can you explain it in 2 sentences? |
| M3 | Conversation continuity | Do follow-up questions work without re-running analysis? | Test 5 follow-up types after a completed analysis |
| M4 | Data quality transparency | Is it clear when data is old or partial? | Does the UI communicate freshness status? |
| M5 | Rate-limit resilience | Does a Yahoo rate limit break the experience or produce a clear message? | User-facing error shows actionable guidance |
| M6 | Privacy protection | Is portfolio weight the only portfolio input used? | No shares/cost/value appears anywhere in flow |
| M7 | Decision consistency | Same input → same output? | Re-run same cached ticker; compare decisions |
| M8 | Time to understanding | How long to understand a recommendation? | PROPOSED: < 5 minutes for a completed analysis |
| M9 | Safe failure mode | Does empty data produce a conservative output? | Empty financials → WATCH or WAIT (verified by tests) |
| M10 | Cache hit rate | After pre-warming, how many analyses run without live data? | % of analyses served from cache |

---

## What has actually been measured

| Measure | What was measured | Result |
|---------|------------------|--------|
| Test coverage | Number of automated tests | 1,228 passing |
| Safe failure (M9) | Empty financials → conservative output | ✅ Verified by test_phase105.py |
| ITC.NS baseline accuracy | EPS, FCF, valuation | ✅ Verified at Phase 9.9b |
| Rate-limit message quality (M5) | 8 specific "must NOT contain" assertions | ✅ Verified by test_phase105.py |
| Privacy protection (M6) | Code inspection + design constraints | ✅ Verified by design |
| Force Refresh wiring | End-to-end flag propagation | ✅ Verified by test_phase105.py |

---

## What has NOT been measured (OPEN QUESTIONS)

- No user satisfaction measure exists (single-user product; subjective)
- No formal time-to-understanding measure (M8)
- No systematic decision quality review (would require tracking actual investment outcomes)
- No measure of how often the system produces `WAIT_INSUFFICIENT_EVIDENCE` vs an actionable recommendation in real use

**PO recommendation:** At minimum, track M1 (completion rate) and M2 (explainability) subjectively during normal use. Note when a decision surprises you or seems wrong — that is the most valuable feedback signal.
