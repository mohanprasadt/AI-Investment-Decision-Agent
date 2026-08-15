# Phase 8.2 — Diagnostic Report
# Generalized Research & Freshness Integration

**Diagnostic case:** CNQ.TO live yfinance run, 2026-08-10
**Test suite:** 641 passed, 3 pre-existing errors, 0 production code modified

---

## 1. Root Cause — Missing BusinessResearchAssessment

**Short answer:** Intentional design limitation. Phase 4 has no automated implementation.

**Execution path for non-CNR tickers:**

```
run_agent.py
  → load_ticker(CNQ.TO)           # Phases 1–3: fetch + normalize + FQ
  → research = None               # Explicit: "Phase 4 requires human analysis"
  → agent.analyze(..., research=None, ...)
      → make_investment_decision(..., research=None, ...)
          → evaluate_gate1(research=None)
              → GateResult(passed=False, forced_action=WAIT_INSUFFICIENT_EVIDENCE)
          → Synthesizer: Gate 1 failed → action = WAIT_INSUFFICIENT_EVIDENCE
```

Gate 1 (`gate1_understanding.py` line 51):
```python
if research is None:
    return GateResult(
        gate_number=1, passed=False,
        forced_action=DecisionAction.WAIT_INSUFFICIENT_EVIDENCE.value,
        summary="No BusinessResearchAssessment provided. ..."
    )
```

**This is correct behaviour, not a bug.** `run_agent.py` sets `research = None` deliberately
with the comment "Phase 4 requires human analysis". Gate 1 then enforces the safeguard.

**Where Phase 4 lives:** `analytics/business_research/` contains:
- `research_models.py` — the `BusinessResearchAssessment` data model (10 dimensions)
- `research_synthesizer.py` — L2 synthesis of a *completed* assessment
- `moat_analyzer.py` — moat-scoring helpers

**Does `research_workflow.py` solve this?** No.
`agent/orchestration/research_workflow.py` exists and is a workflow *sequencer*. It defines a 10-step process and loads prompt templates. Its own docstring explicitly states: "This module does NOT: Execute research itself (Claude does that)." It prepares prompts for a human or LLM to execute; it cannot fill `BusinessResearchAssessment` autonomously. It is the right plumbing for Phase 8.3 but is not wired into the Phase 8/8.1 runner.

**Orchestration gap:** There is no component that calls `research_workflow.py`, executes the
10-step prompts, and maps the output into a `BusinessResearchAssessment`. That bridge does not
exist yet.

---

## 2. Root Cause — UNKNOWN Price Freshness

**Short answer:** `build_freshness_assessment()` always creates five items. The two with no
dates (earnings, research) get `UNKNOWN` status. The `compute()` method then sets
`overall_status = UNKNOWN` because the `all(CURRENT)` check fails.

**Trace:**

In `data_loader.py` (Step 5):
```python
fin_date = getattr(metrics, "data_as_of_date", "") or ""  # = "2026-08-10" (fetch date)
result.freshness = build_freshness_assessment(
    analysis_date="2026-08-10",
    price_date="2026-08-10",        # set to fetch date (correct for current price)
    financial_statements_date=fin_date,  # = "2026-08-10" (incorrect — see Note A)
    # earnings_date=None  (not passed)
    # research_date=None  (not passed)
)
```

Inside `build_freshness_assessment()` this produces five items:

| Category            | Date       | Status    |
|---------------------|------------|-----------|
| price               | 2026-08-10 | CURRENT   |
| financial_statements| 2026-08-10 | CURRENT   |
| earnings            | None       | UNKNOWN   |
| research            | None       | UNKNOWN   |
| valuation_inputs    | 2026-08-10 | CURRENT   |

Then `compute()` runs:
```python
# statuses = [CURRENT, CURRENT, UNKNOWN, UNKNOWN, CURRENT]
if FreshnessStatus.STALE in statuses:      # False
    ...
elif FreshnessStatus.AGING in statuses:    # False
    ...
elif all(s == FreshnessStatus.CURRENT ...):# False — two UNKNOWN items
    ...
else:
    self.overall_status = FreshnessStatus.UNKNOWN  # ← here
```

The renderer then displays `overall_status` next to the price:
```python
freshness_status = _freshness_status(d)   # returns overall_status = "UNKNOWN"
lines.append(f"Current price:  {d.current_price:.2f} {d.price_currency}  [{freshness_status}]")
```

**Result:** The price is actually CURRENT (age = 0 days), but the display says `[UNKNOWN]`
because the overall assessment is dominated by the UNKNOWN earnings/research items.

**Important distinction:** The price *suppression* check (`_price_is_stale_or_unknown()` in
`decision_synthesizer.py`) correctly inspects the price *item's* status (CURRENT), not
the overall status. So price suppression is NOT incorrectly triggered. The UNKNOWN
classification is a display/UX issue, not a decision-logic issue.

**Note A — secondary issue (financial_statements_date):** The normalizer sets
`data_as_of_date = _fetched_at[:10]` — the fetch timestamp, not the reporting period.
This causes the financial_statements item to be classified as CURRENT even though the
actual statements may be from FY2024 (up to 18 months old). This is a separate
correctness issue that should be addressed in Phase 8.3.

**Note B — is UNKNOWN intentional?** Partially. The FreshnessStatus.UNKNOWN enum value
is intended for "no date metadata available." Earnings and research genuinely have no
date in the yfinance path. The problem is that UNKNOWN items drag the *display* label
to UNKNOWN even when the actionable item (price) is CURRENT.

---

## 3. Current Phase 8/8.1 Execution Architecture

```
python run_agent.py --ticker <TICKER>
│
├── CNR.TO ─────────────────────────────────────────────────────
│     ↓
│   _load_cnr_demo()
│     → _build_cnr_metrics()         Phase 2 model (manual data)
│     → assess_financial_quality()   Phase 3
│     → _build_cnr_research()        Phase 4 (hand-coded demo)
│     → _build_cnr_valuation()       Phase 5 (hand-coded demo)
│     → build_freshness_assessment() Phase 7.5
│     → agent.analyze(fq, research, valuation, freshness)
│         → make_investment_decision()
│         → render_assessment()
│         → REPL follow-ups
│
└── Any other ticker ────────────────────────────────────────────
      ↓
    load_ticker(ticker)           Phase 1 → 3 only
      → fetch_ticker()            yfinance (Phase 1)
      → normalize()               → CompanyFinancialMetrics (Phase 2)
      → assess_financial_quality()→ FinancialQualityAssessment (Phase 3)
      → build_freshness_assessment() Phase 7.5 (partial — see §2)
      ↓
    research = None               Phase 4: NOT wired
    valuation = None              Phase 5: NOT wired
      ↓
    agent.analyze(fq, research=None, valuation=None, freshness)
      → make_investment_decision()
          → Gate 1: research is None → WAIT_INSUFFICIENT_EVIDENCE
      → render_assessment() → shows WAIT_INSUFFICIENT_EVIDENCE
```

---

## 4. Can Phase 4 Be Invoked Dynamically?

**The research_synthesizer.py** (`finalize_assessment()`) can be called on any populated
`BusinessResearchAssessment` object — it is ticker-agnostic. Calling it produces the L2
synthesis. But it requires a fully or partially populated `BusinessResearchAssessment` as
input. It does not produce that object from scratch.

**The research_workflow.py** (`create_workflow()`, `load_step_prompt()`) can be instantiated
for any ticker and produces a sequenced 10-step workflow with prompt templates rendered
with the ticker's financial context injected. Steps 2, 3, 5, 6, 7, 8, 9 have prompt
template files. Steps 1, 4, 10 are programmatic (ETF check, FQ review, synthesis).

**Gap:** Nothing currently maps `research_workflow.py` output into a `BusinessResearchAssessment`.
The workflow is designed for interactive use: Claude (or a human) executes each prompt, produces
structured answers, and those answers must be parsed into the assessment object. That parsing
bridge does not exist.

---

## 5. Minimal Change for End-to-End Arbitrary-Ticker Analysis

To produce a full investment decision for an arbitrary supported ticker, two gaps need closing.
These are listed in priority order, smallest change first.

### Gap A — Freshness display (small, self-contained)

**Change:** In `build_freshness_assessment()`, only add earnings/research items when dates
are actually provided. If `earnings_date=None` and `research_date=None`, skip those items.
This prevents UNKNOWN items from pulling `overall_status` to UNKNOWN when the price and
financial data are genuinely current.

Also correct the `financial_statements_date` in `data_loader.py`: the normalizer's
`data_as_of_date` is the fetch date, not the reporting period. A separate `fin_stmt_period`
field (e.g., derived from the latest income statement date in raw financials) would be needed.

**Risk:** None. The price suppression check already reads the price item directly; this
change only affects display.

### Gap B — Phase 4 research bridge (large, Phase 8.3 scope)

**What's needed:** A `ResearchOrchestrator` that:
1. Takes a ticker + `DataLoadResult` (Phase 1–3 output)
2. Calls `create_workflow(ticker, company_name, financial_context={...})`
3. Executes each step's prompt via an LLM call (requires web access for current information)
4. Parses each step's output into the corresponding `BusinessResearchAssessment` dimension
5. Calls `finalize_assessment()` to produce the complete Phase 4 output
6. If LLM/web access is unavailable → returns `None`, preserving `WAIT_INSUFFICIENT_EVIDENCE`

This is non-trivial. The 10 research dimensions require external knowledge (company filings,
industry data, moat evidence) that is not available from yfinance alone.

**What must not change:** Gate 1's `research is None → WAIT_INSUFFICIENT_EVIDENCE` must
remain intact. The research bridge must produce a valid `BusinessResearchAssessment` or
explicitly return `None` — never inject a fabricated or incomplete object that bypasses Gate 1.

---

## 6. Safeguards Affected by Proposed Changes

| Safeguard | Gap A (freshness) | Gap B (research bridge) |
|---|---|---|
| Gate 1 WAIT_INSUFFICIENT_EVIDENCE | Not affected | Not affected if bridge returns None on failure |
| Price suppression (WATCH_PENDING_DATA) | Not affected (reads price item directly) | Not affected |
| CANNOT_COMPLETE_LIVE_ANALYSIS | Not affected | Not affected |
| Data fabrication prohibition | Not affected | Bridge must not fabricate — must reflect real research |
| Portfolio privacy | Not affected | Not affected |

---

## 7. Recommended Next Implementation Step

**Phase 8.3 — Freshness Fix (Gap A only, small scope)**

Fixing the misleading `[UNKNOWN]` freshness display is the right next step. It:
- Is self-contained (2 files: `data_freshness.py`, `data_loader.py`)
- Doesn't touch Gate 1 or any investment-logic
- Makes the CNQ.TO output clearer and more accurate
- Has a natural regression test

The research bridge (Gap B) is a larger Phase 9+ feature involving LLM orchestration and
should be scoped separately with its own design review.

Specific changes for Phase 8.3:
1. In `build_freshness_assessment()`: skip earnings/research items when dates are not provided
2. In `data_loader.py`: derive `financial_statements_date` from the latest financial statement
   period in the raw data, not the fetch timestamp
3. In `renderer.py`: optionally show the price item's freshness status specifically rather than
   the overall status

---

## 8. Tests to Add Before Implementation

For Gap A (freshness fix):

```python
# test_freshness_live_path
def test_price_only_freshness_shows_current():
    """
    When build_freshness_assessment is called with only price_date (no
    earnings/research dates), overall_status should be CURRENT or AGING,
    not UNKNOWN.
    """

def test_earnings_date_missing_does_not_force_unknown():
    """
    Omitting earnings_date should not cause overall_status=UNKNOWN when
    price and financial_statements are both CURRENT.
    """

def test_financial_statements_date_not_set_to_fetch_date():
    """
    Confirm that data_loader.py uses the latest statement period date,
    not the fetch timestamp, as financial_statements_date.
    """

def test_price_item_always_has_date_from_yfinance_path():
    """
    Confirm that a successful yfinance load produces a freshness assessment
    where the 'price' item has a non-None data_date.
    """

def test_price_suppression_not_triggered_for_same_day_price():
    """
    A price fetched today (age=0) must NOT trigger WATCH_PENDING_DATA
    suppression, regardless of overall_status.
    """
```

For regression (ensuring Gate 1 safeguard is intact):

```python
def test_gate1_still_blocks_when_research_none():
    """
    Confirm that after freshness fix, research=None still → WAIT_INSUFFICIENT_EVIDENCE.
    """

def test_freshness_fix_does_not_affect_cnr_demo():
    """
    CNR.TO demo run with research+valuation populated should still produce
    an investment action (not WAIT_INSUFFICIENT_EVIDENCE).
    """
```

---

## Summary Table

| Item | Finding |
|---|---|
| Missing BusinessResearchAssessment | Intentional — Phase 4 has no automated implementation. research_workflow.py exists but requires LLM execution bridge (not yet built). |
| UNKNOWN price freshness | Bug in display — earnings/research items have no dates → UNKNOWN status dominates overall_status. Price item is correctly CURRENT. Decision logic is unaffected. |
| Phase 8.1 scope | Ticker ingestion (Phases 1–3) only. End-to-end analysis requires Phase 4–5 which are not automated. |
| Phase 4 dynamic invocation | research_workflow.py can be instantiated for any ticker. research_synthesizer.py can finalize any populated assessment. The parsing bridge (LLM output → BusinessResearchAssessment fields) does not exist. |
| Safeguards | All intact. Gate 1, price suppression, CANNOT_COMPLETE, and fabrication prohibition remain unchanged. |
| Recommended next step | Phase 8.3: Fix freshness display (Gap A). Research bridge (Gap B) is Phase 9+. |
| Secondary issue found | financial_statements_date in data_loader.py is set to fetch timestamp, not statement period. Overstates freshness of financial data. Address in Phase 8.3. |
