# Architecture Overview

> **Audience:** Product Owner (business view) and developer reference  
> **Status:** IMPLEMENTED as described

---

## Level 1 — Business view (what the system does)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           USER (Mapla)                                   │
│                     Streamlit browser interface                           │
└─────────────────────────────┬────────────────────────────────────────────┘
                              │ "Analyse MSFT"  /  "Why WATCH?"
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    CONVERSATIONAL LAYER                                   │
│   Intent classification → analysis trigger → follow-up routing            │
└──────────────────────┬────────────────────────────────────────────────────┘
                       │
          ┌────────────┴──────────────┐
          │                           │
          ▼                           ▼
  ┌───────────────┐         ┌──────────────────┐
  │  ANALYSIS     │         │  FOLLOW-UP       │
  │  PIPELINE     │         │  (from session)  │
  │               │         │  No new data     │
  │  Data fetch   │         │  fetched         │
  │  Quality      │         └──────────────────┘
  │  Research     │
  │  Valuation    │
  │  5 Gates      │
  │               │
  └───────┬───────┘
          │
    ┌─────┴──────┐
    │            │
    ▼            ▼
 Yahoo       Claude
 Finance     API
 (data)      (research)
```

**In plain English:**  
The user asks about a company in plain language. The system decides whether this is a new analysis request or a follow-up on a previous analysis. If it's new, it fetches financial data, runs qualitative research, applies valuation methods, and then evaluates the result through 5 sequential decision gates. The output is an investment action (WATCH, ACCUMULATE, etc.) with reasoning. If it's a follow-up, the system answers from the stored result without making any new data calls.

---

## Level 2 — Technical view (how it's built)

### Three-layer architecture

The system is built in three layers that enforce a strict one-way dependency flow:

```
Layer 1 — Data (L1)
  Responsibility: Fetch, cache, normalise raw financial data
  Key modules:   data/ingestion/fetcher.py
                 data/ingestion/normalizer.py
  Output:        CompanyFinancialMetrics (typed dataclass)

Layer 2 — Analysis (L2)
  Responsibility: Evaluate quality, conduct research, build valuation
  Key modules:   analytics/financial_quality/quality_engine.py
                 analytics/agent/anthropic_researcher.py
                 analytics/valuation/dcf_engine.py
                 analytics/valuation/multiples_engine.py
                 analytics/valuation/valuation_synthesizer.py
                 analytics/portfolio/portfolio_calculator.py
  Output:        FinancialQualityAssessment, BusinessResearchAssessment,
                 ValuationAssessment, PortfolioContext

Layer 3 — Decision (L3)
  Responsibility: Apply investment philosophy through sequential gates
  Key modules:   analytics/decision/decision_synthesizer.py
                 analytics/decision/gate1..gate5.py
                 analytics/decision/decision_models.py
  Output:        InvestmentDecisionAssessment (contains DecisionAction)
```

**Rule:** L3 depends on L2. L2 depends on L1. L1 does not depend on L2 or L3. This rule is enforced in the module docstrings.

---

### Presentation and orchestration

The decision-to-display path has two more components:

```
analytics/agent/renderer.py
  → Converts InvestmentDecisionAssessment → human-readable report string

analytics/agent/investment_agent.py
  → Top-level agent: orchestrates pipeline and follow-up routing

analytics/agent/pipeline.py
  → Assembles and runs the full analysis sequence (L1 → L2 → L3)
  → Single function: run_analysis_pipeline(ticker, …) → PipelineResult
  → Always returns PipelineResult (never raises to the caller)

conversation/manager.py
  → Thin adapter between the Streamlit UI and the analytics layers
  → Manages ConversationSession state
  → Routes intent to pipeline or follow-up handler

ui/app.py
  → Streamlit UI. Presentation only.
  → Calls ConversationManager, renders output
  → No analysis logic lives here
```

---

### Key architectural boundaries

| Boundary | Rule | Why |
|---------|------|-----|
| L3 is the ONLY source of investment conclusions | `DecisionAction` is only defined in `decision_models.py`; no other module produces BUY/SELL/WATCH | Prevents fragmented decision logic scattered across modules |
| `pipeline.py` never raises | All errors become `PipelineResult(ok=False, error=...)` | Ensures the UI always gets a structured response |
| `renderer.py` is presentation-only | No analysis logic in renderer | Separation of concerns |
| `session.py` stores only `portfolio_weight_pct` | No shares, cost basis, or account value | Privacy protection |
| API key from environment only | `ANTHROPIC_API_KEY` read from `os.environ` only | Security |

---

### Entry points

| Entry point | What it does |
|-------------|-------------|
| `run_ui.py` | Starts the Streamlit web interface |
| `run_agent.py` | CLI entry point; legacy; also has demo paths |
| `scripts/prewarm_mvp.py` | Pre-warms the 33 MVP tickers into local cache |

---

### What is NOT in the architecture (deliberate)

- No database — local JSON cache only
- No authentication — single user, local execution
- No background workers — all analysis is synchronous
- No real-time data — yfinance gives end-of-day or delayed prices
- No trade execution — human-in-loop is a safety principle
