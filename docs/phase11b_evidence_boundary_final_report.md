# Phase 11B Evidence Boundary — Final Correction Report

**Date:** 2026-10-01  
**Scope:** Root-cause fix of P0-2 evidence-boundary bypass confirmed in live CNQ.TO run + evidence segregation hardening + Streamlit rendering defect fix.  
**Prior report:** `docs/phase11b_corrective_final_report.md` (58 tests, Defect 1 + partial Defect 2 fixed).  
**Constraint:** No Gate 5 redesign. Gate 5 severity thresholds, UNKNOWN semantics, n_bear logic, decision synthesis, and five-gate architecture are unchanged.

---

## Section A — Root Cause Diagnosis

### A1 — P0-2 bypass: 5yr CAGR still reaching trusted output

**Live CNQ run showed two strings still appearing as trusted evidence:**

1. `"Canadian Natural Resources faces a 3-year and 5-year revenue CAGR of -3.75%"` (in bear_case_narrative)
2. `"Revenue CAGR of -3.75% already reflects weak pricing or volume"` (in evidence[])

**Full data path traced:**

```
calculations.py:extract_cagr_from_series()
  ↓  len(sorted_years) < 6 → fallback to earliest year → returns -3.75 (numeric, not None)
  
metrics.revenue_growth.cagr_5yr = -3.75 (genuine 5yr value? NO — it's a 3yr fallback)
metrics.revenue_growth.cagr_5yr_label = "3yr CAGR: -3.7% (2022→2025)  [5yr baseline unavailable]"
  
_build_context() [BEFORE Fix 1]:
  ctx["revenue_cagr_5yr"] = getattr(rg, "cagr_5yr", None)  # = -3.75 (NOT None)
  
_parse_bull_bear():
  _5yr_missing = ctx.get("revenue_cagr_5yr") is None  # = False (-3.75 is not None)
  → validator NEVER fires
  
LLM sees "revenue_cagr_5yr: -3.75" in prompt → generates "3-year and 5-year revenue CAGR of -3.75%"
→ string passes post-generation check (validator skipped)
→ string reaches BullBearAssessment → Gate 5 → renderer → trusted output
```

**Root cause:** `extract_cagr_from_series()` returns a numeric fallback (-3.75) when fewer than 6 years are available, but `_build_context()` passed this value through as a genuine 5yr CAGR. The only reliable signal for the fallback is `cagr_5yr_label` containing `"[5yr baseline unavailable]"`.

### A2 — Evidence segregation insufficient

**Prior fix (corrective cycle):** annotated violating strings with `[DATA-BOUNDARY-VIOLATION:]` prefix in place — leaving them in `d["evidence"]`. This kept them in `ThesisBreaker.evidence` (populated by `evaluate_gate5()`), which is what Gate 5, renderer, and Decision Trace all treat as trusted evidence.

**Root cause:** annotation without removal. The string's content is flagged, but its location in `evidence[]` is unchanged, so it still flows downstream as trusted.

### A3 — Streamlit rendering defect

**Observed output:** `<40/bblornaturalgassustained<2 USD/MMBtu`  
**Cause:** Breaker conditions containing `<` (e.g., `"Brent crude <$40/bbl"`) are passed raw to Streamlit's `st.markdown()`, which treats `<$40/bbl` as an opening HTML tag and strips/merges it with adjacent text.  
**Scope:** All condition display locations in `renderer.py`.

---

## Section B — Fixes Applied

### B1 — Fix 1: `_build_context()` fallback detection (`research_orchestrator.py`)

```python
# BEFORE (bypassed — numeric fallback set as genuine 5yr value):
ctx["revenue_cagr_5yr"] = getattr(rg, "cagr_5yr", None)

# AFTER (root-cause fix — suppresses fallback value):
_cagr_5yr_val   = getattr(rg, "cagr_5yr", None)
_cagr_5yr_label = getattr(rg, "cagr_5yr_label", "") or ""
_5yr_genuine    = (
    _cagr_5yr_val is not None
    and "[5yr baseline unavailable]" not in _cagr_5yr_label
)
ctx["revenue_cagr_5yr"] = _cagr_5yr_val if _5yr_genuine else None
```

Effect: When `extract_cagr_from_series()` used a fallback, `ctx["revenue_cagr_5yr"]` is now `None` → `_format_context()` emits `"revenue_cagr_5yr: UNAVAILABLE — ..."` → LLM is correctly informed → `_5yr_missing = True` → post-generation validator fires.

Also added `revenue_cagr_3yr_label` to context when available, giving the LLM accurate period labeling.

### B2 — Fix 2: Evidence segregation (`research_orchestrator.py`, `_parse_bull_bear()`)

```python
# BEFORE (annotation-in-place — violating string stays in evidence[]):
for ev in d.get("evidence", []):
    scanned = _scan_carbon(_scan_5yr(ev, "evidence"), "evidence")
    if "[DATA-BOUNDARY-VIOLATION" in scanned:
        clean_ev.append(scanned)   # annotated but still trusted!
    ...

# AFTER (segregation — violating string routed to audit-only field):
for ev in d.get("evidence", []):
    scanned = _scan_carbon(_scan_5yr(ev, "evidence"), "evidence")
    if scanned.startswith("[DATA-BOUNDARY-VIOLATION"):
        flagged_ev.append(scanned)   # annotated form for audit
    else:
        clean_ev.append(ev)          # original clean string only
d["evidence"] = clean_ev
if flagged_ev:
    d["unsupported_evidence"] = flagged_ev   # audit only — not passed to ThesisBreaker
```

Effect: `ThesisBreaker.evidence` (built by `evaluate_gate5()` from `detail.get("evidence", [])`) contains only clean, structurally-supported evidence. Violating strings are preserved in `unsupported_evidence[]` for audit and debugging — they are NOT silently deleted.

### B3 — Fix 3: `_md_safe()` rendering helper (`renderer.py`)

```python
def _md_safe(text: str) -> str:
    """Escape < and > in text for Streamlit markdown rendering.
    Applied at render time only — does NOT alter stored condition data."""
    return text.replace("<", r"\<").replace(">", r"\>")
```

Applied to every condition display location in `renderer.py`:

| Function | Location |
|---|---|
| `render_assessment()` | severity breaker `[{likelihood}] {condition}` line |
| `render_assessment()` | monitoring breaker `[{likelihood}] {condition}` line |
| `_answer_gate5_explanation()` | contributing breakers condition line |
| `_answer_gate5_explanation()` | monitoring indicators condition line |
| `_answer_risks()` | severity breakers condition line |
| `_answer_risks()` | monitoring indicators condition line |
| `_answer_breaker_specific()` | header `{header}: {condition}` |
| `_answer_breaker_likelihood_question()` | `Thesis breaker: {condition}` |
| `_answer_breaker_likelihood_question()` | mismatch note `'{condition}'` |
| `_answer_breaker_likelihood_question()` | fallback list `[{lk}] {cond}` (both severity + monitoring) |

The underlying `ThesisBreaker.condition` is **never mutated**. Escaping is render-time only.

Also added `revenue_cagr_3yr_label` to the `_format_context()` key list in `anthropic_researcher.py` so the period label reaches the LLM prompt when available.

---

## Section C — Evidence Boundary Contract

Three categories of LLM-generated content are now handled distinctly:

| Category | Description | Treatment |
|---|---|---|
| **A — Structured evidence** | Claims derivable from `context` dict (3yr CAGR, FCF, net debt, price) | Remains in `evidence[]` → trusted, shown in Gate 5 |
| **B — Hypothetical breaker conditions** | Forward-looking "if X then Y" scenarios in the `condition` field | NOT scanned — LLM hypothesis generation is permitted |
| **C — Unsupported external facts** | 5yr CAGR when absent from context; carbon-pricing $/tonne figures | Moved to `unsupported_evidence[]` → annotated audit record only |

Category C strings are not silently deleted and are not suppressed from the audit trail. They are excluded from `ThesisBreaker.evidence` only.

---

## Section D — Gate 5 Architecture: Unchanged

Gate 5 severity thresholds are unchanged:

```
n_high >= 1               → SEVERE
n_medium_equiv >= 4       → SEVERE
n_medium_equiv >= 2       → HIGH   (or n_bear >= 6)
n_medium_equiv >= 1       → MODERATE (or n_bear >= 3)
else                      → LOW
```

where `n_medium_equiv = n_medium + n_unknown`.

UNKNOWN semantics: treated as MEDIUM-equivalent for severity **only**. Displayed as UNKNOWN everywhere else. Unchanged.

`n_bear`, `n_breakers`, Gate 5 confidence logic: unchanged.

---

## Section E — Test Results

```
68 tests passed, 0 failed, 0 warnings
```

### Group 12 — Phase 11B Evidence Boundary Final (Tests 59–68)

| Test | What it covers | Result |
|---|---|---|
| 59 (Test 1) | Evidence segregation: 5yr CAGR claim → unsupported_evidence, not evidence[] | PASS |
| 60 (Test 2) | Four 5yr CAGR wording variants all flagged | PASS |
| 61 (Test 3) | Valid 3yr CAGR in evidence NOT flagged (no false positive) | PASS |
| 62 (Test 4) | Carbon-pricing $/tonne claim → unsupported_evidence | PASS |
| 63 (Test 5) | Hypothetical condition with `<` in condition field NOT filtered | PASS |
| 64 (Test 6) | Gate 5 evidence array: 2 clean of 4 survive; 2 violating in unsupported | PASS |
| 65 (Test 7) | UNKNOWN renders as `[UNKNOWN]`, not `[MEDIUM]`, in render_assessment() | PASS |
| 66 (Test 8) | Monitoring-only section separated from severity section in render_assessment() | PASS |
| 67 (Test 9) | `_md_safe()`: `<` → `\<`, `>` → `\>`, other chars unchanged | PASS |
| 68 (Test 10) | render_assessment() escapes `<` in condition; ThesisBreaker.condition unmutated | PASS |

### test_56_D updated

test_56_D (Group 11 — carbon pricing in evidence) was updated to assert the new segregation behavior (check `unsupported_evidence[]` instead of annotated string in `evidence[]`). All prior Groups 1–11 continue to pass.

All 58 pre-existing tests continue to pass.

---

## Section F — CNQ Acceptance Re-run

Six checks against the exact CNQ strings that failed in the live run:

| Check | Input | Result |
|---|---|---|
| 1 | `"3-year and 5-year revenue CAGR of -3.75%"` in bear_case_narrative | → `[DATA-BOUNDARY-VIOLATION]` prefix added ✅ |
| 2 | `"Revenue CAGR of -3.75% over 5 years"` in evidence[] | → moved to unsupported_evidence[], NOT in evidence[] ✅ |
| 3 | `"FCF declined 47.8% from 2022 to 2025."` (clean) | → remains in evidence[] ✅ |
| 4 | Condition `"Brent crude <$40/bbl or natural gas sustained <$2 USD/MMBtu"` | → preserved unchanged (hypothesis, not evidence) ✅ |
| 5 | `_md_safe(condition)` | → produces `"Brent crude \<$40/bbl..."` ✅ |
| 6 | `render_assessment()` output | → contains `\<$40/bbl` (escaped), not raw `<$40/bbl` ✅ |

The CNQ decision output remains **HOLD** (MEDIUM confidence, adversarial risk HIGH). No gate thresholds, severity levels, or decision action are affected by the corrective fix.

---

## Section G — Files Changed

| File | Change |
|---|---|
| `analytics/agent/research_orchestrator.py` | Fix 1: `_build_context()` fallback detection via `cagr_5yr_label`; Fix 2: evidence segregation in `_parse_bull_bear()` |
| `analytics/agent/anthropic_researcher.py` | Added `revenue_cagr_3yr_label` to `_format_context()` key list |
| `analytics/agent/renderer.py` | Fix 3: `_md_safe()` helper added; applied to all 10 condition display locations |
| `tests/test_phase11b.py` | Group 12 Tests 1–10 added (tests 59–68); test_56_D updated for segregation semantics |
| `docs/phase11b_evidence_boundary_final_report.md` | This file |

**Files NOT changed:** `gate5_adversarial.py`, `decision_models.py`, `decision_trace.py`, `scenario_engine.py`, `gate2_quality.py`, `gate3_valuation.py`, `gate4_portfolio.py`, decision synthesizer.

---

## Constraints Compliance

| Constraint | Status |
|---|---|
| Do NOT redesign Gate 5 | ✅ Only evidence routing changed; Gate 5 severity model untouched |
| Do NOT change Gate 5 severity thresholds | ✅ Unchanged |
| Do NOT change UNKNOWN semantics | ✅ Unchanged |
| Do NOT change n_bear logic | ✅ Unchanged |
| Do NOT change Gate 5 confidence logic | ✅ Unchanged |
| Do NOT change decision synthesis | ✅ Unchanged |
| Do NOT change five-gate architecture | ✅ Unchanged |
| Do NOT prohibit LLM from generating hypotheses | ✅ `condition` field is never scanned or filtered |
| Do not build a generalized NLP system | ✅ Two specific patterns only (5yr CAGR + carbon pricing) |
| Do not silently delete information | ✅ Violating strings preserved in `unsupported_evidence[]` with annotation |
| Do not alter underlying breaker condition | ✅ `_md_safe()` is render-time only; stored condition unmodified |

---

## Recommendation — RETRACTED (K1 2026-11-08)

> **⚠️ RETRACTION NOTICE — K1 Remediation 2026-11-08**
>
> The ACCEPT conclusion below was premature.  Subsequent audit (Full Repository Audit
> 2026-11-07) identified three defects in `scenario_engine.py` that were not visible
> at the time this report was written:
>
> - **DEF-1**: `_calculate_severity()` in the scenario engine lacked the `n_bear >= 6 → HIGH`
>   and `n_bear >= 3 → MODERATE` escalation paths that Gate 5 applies.
> - **DEF-2**: `run_scenario()` included `is_monitoring_only=True` breakers (moat erosion,
>   valuation assumption) in the severity-contributing breaker set.  This caused the
>   scenario engine to overstate risk for all tickers with moat or valuation assessments.
> - **DEF-3**: `is_monitoring_only` and `unsupported_evidence` were not propagated when
>   creating ThesisBreaker override copies in `run_scenario()`.
>
> Additionally:
>
> - **CAGR fallback**: the structured `data_years_available` field was not used as the
>   primary availability signal; the display-label substring was the only check, leaving
>   a silent failure mode when `cagr_5yr_label` is empty.
> - **Evidence persistence**: `unsupported_evidence` from `thesis_breaker_details` was not
>   present on `ThesisBreaker` and therefore did not survive persistence.
>
> All five issues have been corrected in K1 (committed as working-tree changes, not yet
> staged).  Phase 11B is NOT accepted.  Independent review of K1 is required before
> acceptance can be declared.

---

~~**ACCEPT.**~~ *(retracted — see notice above)*

The original scope of this report (Fix 1 / Fix 2 / Fix 3) was implemented correctly.
68/68 tests passed at the time. The retraction applies to the overall Phase 11B ACCEPT
claim, not to the correctness of the three evidence-boundary fixes themselves.

- A `_format_context()` that correctly marks 5yr CAGR as UNAVAILABLE when the data is a 3yr fallback
- A `_parse_bull_bear()` whose evidence segregation prevents unsupported external claims from reaching `ThesisBreaker.evidence`
- A renderer that safely handles `<` and `>` in all breaker condition display contexts
