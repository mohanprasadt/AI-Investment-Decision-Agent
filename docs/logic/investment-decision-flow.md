# Investment Decision Flow

> **Purpose:** End-to-end explanation of how a ticker → investment action  
> **Audience:** Product Owner (plain language + technical mapping)

---

## Plain language summary

When you ask the system to analyse a company, it works through a structured sequence that mirrors how a careful long-term investor would think:

1. **Get the facts.** Fetch the company's financial data.
2. **Normalise.** Convert raw numbers into consistent, comparable metrics. Smooth out one-time gains.
3. **Quality check.** Is this a quality business? How does it score on ROIC, revenue growth, margins, FCF, and balance sheet health?
4. **Understand the business.** What does the company do, what is its moat, who runs it, what are the risks? (This requires the Claude API.)
5. **Value it.** Using four independent methods, what is a reasonable fair value range?
6. **Check the portfolio.** How much do I already own? Does this position fit my current allocation?
7. **Challenge the thesis.** What could go wrong? Are any risks severe enough to override a positive conclusion?
8. **Decide.** Given everything above, what is the right action?

The output is a structured investment decision — not just the action, but the reasoning behind it, the evidence, the confidence level, and the thesis breakers to watch for.

---

## The 8-step pipeline (technical mapping)

| Step | What happens | Module | Output |
|------|-------------|--------|--------|
| 1 | Fetch data | `data/ingestion/fetcher.py` | Raw JSON (info, financials, history) |
| 2 | Normalise | `data/ingestion/normalizer.py` | `CompanyFinancialMetrics` |
| 3 | Financial quality | `analytics/financial_quality/quality_engine.py` | `FinancialQualityAssessment` |
| 4 | Business research | `analytics/agent/anthropic_researcher.py` | `BusinessResearchAssessment` |
| 5a | Build valuation input | `analytics/agent/valuation_builder.py` | `ValuationInput` |
| 5b | Run valuation | `analytics/valuation/valuation_synthesizer.py` | `ValuationAssessment` |
| 6 | Portfolio context | `analytics/portfolio/portfolio_synthesizer.py` | `PortfolioContext` |
| 7 | 5 decision gates | `analytics/decision/decision_synthesizer.py` | `InvestmentDecisionAssessment` |
| 8 | Render | `analytics/agent/renderer.py` | Formatted string report |

---

## How the decision is reached

The decision engine does not compute a score. It runs five sequential gates:

```
Gate 1: Do I understand this business?
  → No  → WAIT_INSUFFICIENT_EVIDENCE (stop)
  → Yes → continue

Gate 2: Is this a quality business?
  → WATCH/CONCERN tier → cap action at WATCH
  → GOOD+ tier → full action range available

Gate 3: Is the price attractive?
  → ACCUMULATE zone → action = ACCUMULATE (if Gate 2 allows)
  → WATCH zone → action = WATCH
  → WAIT zone → action = no action

Gate 4: Does this fit my portfolio?
  → Adjusts position sizing
  → Does NOT change the action itself (just the magnitude)

Gate 5: What could break the thesis?
  → SEVERE risk → override to REDUCE or EXIT
  → HIGH risk → cap at WATCH
  → LOWER risk → no change

Final action = min(Gate 2 cap, Gate 3 zone, Gate 5 override)
```

---

## Decision confidence

`DecisionConfidence` (HIGH / MEDIUM / LOW) reflects the overall reliability of the analysis:

- **HIGH:** All four upstream assessments are present and consistent; data is complete; valuation methods converge.
- **MEDIUM:** Some gaps in data or moderate divergence between valuation methods.
- **LOW:** Significant data gaps; methods disagree; one or more upstream phases missing.

Confidence affects how strongly the decision should be acted on. A LOW confidence ACCUMULATE should be treated more cautiously than a HIGH confidence ACCUMULATE.

---

## Evidence tracking

Every decision includes `DecisionEvidenceItem` objects — individual pieces of evidence that influenced the decision. Each item records:
- Which phase it came from (financial_quality, business_research, valuation, portfolio)
- What dimension it relates to (e.g., "ROIC", "moat", "accumulation_zone")
- What was observed
- Whether it supports or contradicts the thesis
- Its evidence strength (STRONG / MODERATE / WEAK)

This is what makes the decision explainable — you can trace exactly what evidence led to what conclusion.

---

## What WAIT_INSUFFICIENT_EVIDENCE means

This is a correct output, not an error. It means:

1. Gate 1 was not satisfied — the system does not have enough qualitative research to make an investment decision.

**Most common cause:** No Anthropic API key is set. Without the Claude API, the business research step cannot run, Gate 1 fails, and the pipeline returns `WAIT_INSUFFICIENT_EVIDENCE`.

**The right response:** Either provide an API key, or accept that this ticker cannot be fully analysed in this environment.

**What it does NOT mean:** The company is bad. It simply means insufficient information was available to the system.

---

## What WATCH_PENDING_DATA means

This action is produced when the current share price is unknown or stale beyond the configured threshold. Without a reliable current price, the valuation zone cannot be assessed. The system suppresses the action recommendation and waits for fresh price data.

---

## The sunk-cost protection rule

Gate 4 (portfolio fit) explicitly excludes average cost and unrealised profit/loss from its analysis. This is documented in the module docstring and enforced by design.

**Why:** A rational investment decision considers forward-looking returns, not the price at which you originally bought the stock. "I can't sell because I'm down 20%" is sunk-cost thinking. The system is designed to never exhibit this reasoning.

---

## Follow-up questions and the stored assessment

After an analysis runs, the full `InvestmentDecisionAssessment` is stored in session state. Follow-up questions ("why WATCH?", "what's the fair value?", "what are the risks?") are answered from this stored object — no new data is fetched.

This has an important implication: if you want a refreshed analysis (e.g., after earnings), you must explicitly run a new analysis (with Force Refresh if needed). Follow-up questions always reflect the analysis that was run in your current session.

---

## Minimal analysis (no API key)

Without the Anthropic API key:
- Steps 1–2 (data) run normally
- Step 3 (quality) runs normally
- Step 4 (research) produces no output → Gate 1 fails
- All subsequent steps are skipped
- Output: `WAIT_INSUFFICIENT_EVIDENCE` with a note that qualitative research was unavailable

This is the correct safe-failure mode. The system does not produce a recommendation from financial data alone.
