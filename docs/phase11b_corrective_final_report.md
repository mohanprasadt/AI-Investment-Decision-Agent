# Phase 11B Corrective Fix — Final Report

**Date:** 2026-09-30  
**Scope:** Two acceptance defects identified after Phase 11B controlled implementation was exercised against CNQ.TO.  
**Constraint:** No redesign of Phase 11B. Gate 5 severity thresholds, UNKNOWN semantics, decision synthesis, and the five-gate architecture are unchanged.

---

## Section 1 — Defects fixed

### Defect 1 — Decision Trace mixes monitoring-only indicators into Thesis Breakers

**Root cause:** `build_decision_trace()` iterated `assessment.thesis_breakers` without filtering, placing all items — including those tagged `is_monitoring_only=True` — under a single "THESIS BREAKERS (Gate 5):" heading. The `GateTraceLine` and `DecisionTrace` dataclasses had no separate field for monitoring items.

**Fix applied** (`analytics/decision/decision_trace.py`):

- Added `monitoring_indicator_lines: List[str]` to `GateTraceLine`
- Added `monitoring_indicator_summary: List[str]` to `DecisionTrace`
- Updated `build_decision_trace()` Gate 5 loop to route by `getattr(tb, "is_monitoring_only", False)` — severity-contributing items to `tb_lines`, monitoring-only items to `mon_lines`
- Updated `render_decision_trace()` per-gate block: two explicit headings — "Severity-contributing thesis breakers:" and "Monitoring indicators (did NOT affect Gate 5 severity):"
- Updated end-of-trace summary: "CONTRIBUTING THESIS BREAKERS (Gate 5):" and "MONITORING INDICATORS (did NOT affect Gate 5 severity):"
- Flag used: `is_monitoring_only` — never string matching

---

### Defect 2 — 5-year CAGR evidence boundary still violated

**Root cause (diagnosed, not assumed):** The post-generation validator in `_parse_bull_bear()` had three bugs:

1. **Regex failed for plural "years":** Pattern used `year\b` — the boundary `\b` between `r` and `s` is not a word boundary in Python's `re` module. Result: "Revenue contraction of -3.7% CAGR over 5 years" was not matched. Confirmed by direct Python test.

2. **Insufficient field coverage:** The original validator only scanned `bear_case_narrative`, `bull_case_narrative`, and `evidence[]`. It did not scan `likelihood_rationale` — which the CNQ output used to carry additional 5yr CAGR claims.

3. **No carbon-pricing pattern:** The CNQ output contained "Federal carbon tax ~$170/tonne by 2030" in evidence. This is an external fact never present in structured context, with no detection pattern.

**Fix applied** (`analytics/agent/research_orchestrator.py`, `_parse_bull_bear()`):

- Regex corrected: `year` → `years?` in all positions; added `over\s+(?:the\s+)?(?:past\s+)?5\s+years?` pattern; added `both\s+3[\s-]?and\s+5[\s-]?year` pattern for "both 3- and 5-year periods" phrasing
- Field coverage expanded: now also scans `likelihood_rationale` per detail, `confirmation_bias_check`, `devils_advocate_research_note`
- Carbon-pricing pattern added: `\$\s*\d[\d,.]*/\s*(?:tonne|ton)\b`, `carbon\s+(?:tax|price|levy|cost)\s.*?\$\s*\d`, `\$\s*\d[\d,.]*\s+per\s+(?:tonne|ton)\b` — applied to evidence strings
- Annotation approach preserved: `[DATA-BOUNDARY-VIOLATION: ...]` prefix; output not rejected or discarded

---

## Section 2 — Gate 5 severity: unchanged

Gate 5 severity thresholds are **not changed**:

```
n_high >= 1               → SEVERE
n_medium_equiv >= 4       → SEVERE
n_medium_equiv >= 2       → HIGH   (or n_bear >= 6)
n_medium_equiv >= 1       → MODERATE (or n_bear >= 3)
else                      → LOW
```

where `n_medium_equiv = n_medium + n_unknown`.

The monitoring-only breakers (`is_monitoring_only=True`) are **never passed to `evaluate_gate5()`**. They are added by `extract_thesis_breakers()` after Gate 5 severity is computed, for display only. This design contract is unchanged.

---

## Section 3 — CNQ acceptance re-run

The stored CNQ JSON (`data/output/CNQ_TO_20260930_decision.json`) predates Phase 11B. A live re-generation requires an API call. The acceptance re-run was performed by: (a) deserializing the CNQ JSON, applying `is_monitoring_only` as `extract_thesis_breakers()` would tag them, and running it through the current renderers in-process; (b) feeding the known CNQ evidence strings directly through the corrected `_parse_bull_bear()` validator.

### 3a — Decision Trace: valuation assumption breaker correctly separated

The CNQ valuation-assumption-break breaker (index 4: "Key valuation assumptions fail: DCF base discount rate: 9.5%…") now renders under:

```
Monitoring indicators (did NOT affect Gate 5 severity):
  [LOW] Key valuation assumptions fail: DCF base discount rate: 9.5% ...
       Monitor: Track actuals vs assumptions in quarterly results.
```

It does NOT appear under "Severity-contributing thesis breakers:" or "CONTRIBUTING THESIS BREAKERS (Gate 5):" in the end-of-trace summary.

The four severity-contributing breakers (FCF decline MEDIUM, net debt LOW, operating margin UNKNOWN, capital allocation UNKNOWN) appear under "CONTRIBUTING THESIS BREAKERS (Gate 5):" only.

### 3b — CAGR treatment: all CNQ 5yr CAGR strings now flagged

| String | Original validator | Corrective validator |
|---|---|---|
| "Revenue contraction of -3.7% CAGR over 5 years…" | ❌ NOT flagged (plural "years") | ✅ `[DATA-BOUNDARY-VIOLATION]` |
| "Revenue CAGR of -3.75% over 5 years" | ❌ NOT flagged (plural "years") | ✅ `[DATA-BOUNDARY-VIOLATION]` |
| "revenues declined at a 3.75% CAGR over both the 3- and 5-year periods" | ✅ Flagged (singular "year") | ✅ `[DATA-BOUNDARY-VIOLATION]` |
| "FCF fell 47.8% from 2022…" | ✅ Clean | ✅ Clean |
| likelihood_rationale "Revenue CAGR of -3.75% over 5 years is a concern." | ❌ Not scanned | ✅ `[DATA-BOUNDARY-VIOLATION]` |

### 3c — Carbon pricing treatment

A CNQ-style evidence string "Federal carbon tax ~$170/tonne by 2030 would add ~$4/bbl to costs" is now detected by the carbon-pricing pattern and annotated `[DATA-BOUNDARY-VIOLATION: external carbon-pricing claim not in structured context]`. The adjacent clean evidence string "Current WTI at $72/bbl provides buffer" is not flagged.

### 3d — Final action and consistency

The CNQ decision remains **HOLD** (MEDIUM confidence, adversarial risk HIGH). No gate thresholds, no severity levels, and no decision action changed as a result of the corrective fix. The corrective fix is display-only for Defect 1 and annotation-only for Defect 2 — neither alters the decision engine outputs.

---

## Section 4 — Test results

```
58 tests passed, 0 failed
```

Group 11 (Tests A–F) added — all pass:

| Test | What it covers | Result |
|---|---|---|
| A (test_53) | Decision Trace monitoring items routed to correct section, not leaking into contributing section | PASS |
| B (test_54) | Plural "years" in CAGR claim flagged (original regex bug) | PASS |
| C (test_55) | "Revenue CAGR of -X% over 5 years" short form flagged | PASS |
| D (test_56) | Carbon-pricing $/tonne claim in evidence flagged | PASS |
| E (test_57) | Valid 3yr CAGR in context NOT flagged (no false positive) | PASS |
| F (test_58) | monitoring-only breakers excluded from severity list → LOW | PASS |

All 52 pre-existing tests continue to pass (Groups 1–10).

---

## Section 5 — Files changed

| File | Change |
|---|---|
| `analytics/decision/decision_trace.py` | Defect 1: `GateTraceLine.monitoring_indicator_lines`, `DecisionTrace.monitoring_indicator_summary`; `build_decision_trace()` split; `render_decision_trace()` two-section rendering |
| `analytics/agent/research_orchestrator.py` | Defect 2: corrected regex (`years?`), expanded field coverage, carbon-pricing pattern |
| `tests/test_phase11b.py` | Added Group 11 Tests A–F (tests 53–58) |

Files NOT changed: `gate5_adversarial.py`, `decision_models.py`, `renderer.py`, `anthropic_researcher.py`, `scenario_engine.py`, `gate2_quality.py`, `gate3_valuation.py`, `gate4_portfolio.py`, decision synthesizer.

---

## Section 6 — Constraints compliance

| Constraint | Status |
|---|---|
| Do NOT redesign Phase 11B | ✅ Only two targeted bugs fixed |
| Do NOT change Gate 5 severity thresholds | ✅ Unchanged |
| Do NOT change UNKNOWN semantics | ✅ Unchanged |
| Do NOT change decision synthesis or five-gate architecture | ✅ Unchanged |
| Do not assume the existing validator is functioning | ✅ Root cause was diagnosed via direct Python test before fix |
| Do NOT prohibit the LLM from generating hypotheses | ✅ Output is annotated, not rejected |
| Do not build a generalized LLM fact-checking system | ✅ Only two specific patterns added (5yr CAGR + carbon pricing); no general inference |
| Do not change production behavior to match stale documentation | ✅ No doc-driven changes |
| Do not silently fix additional architectural issues | ✅ No undeclared changes |

---

## Section 7 — Recommendation

**ACCEPT.** Both defects are fixed, all 58 tests pass, no gate logic or severity model was altered. The next live CNQ.TO run will produce a Decision Trace with correct section separation and a validator that catches all known 5yr CAGR phrasing variants and carbon-pricing external claims.
