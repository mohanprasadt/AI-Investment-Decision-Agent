# Data Flow

> **Purpose:** Trace the journey of financial data from source to displayed decision  
> **Status:** IMPLEMENTED as described

---

## Full analysis flow (new ticker)

```
USER selects ticker + portfolio weight → clicks Analyse
  │
  ▼
ui/app.py
  → ConversationManager.run_analysis(ticker, portfolio_weight_pct, force_refresh)
        │
        ▼
  conversation/manager.py
    → analytics.agent.pipeline.run_analysis_pipeline(ticker, force_refresh)
          │
          ├─── Step 1: FETCH & NORMALISE
          │       analytics.agent.data_loader.load_ticker(ticker)
          │         → data/ingestion/fetcher.fetch_ticker(ticker, force_refresh)
          │              ├── Check cache: data/cache/{TICKER}/info.json
          │              │                data/cache/{TICKER}/financials.json
          │              │                data/cache/{TICKER}/history.json
          │              │
          │              ├── Cache HIT and fresh → return cached data
          │              │
          │              └── Cache MISS or stale → yfinance.Ticker(ticker)
          │                      ├── On HTTP 429 → raises; pipeline catches →
          │                      │   PipelineResult(ok=False, is_rate_limited=True)
          │                      └── On success → save to cache → return data
          │
          │       data/ingestion/normalizer.normalize(raw_data)
          │         → CompanyFinancialMetrics
          │              └── Continuing-ops NI preference chain (for EPS)
          │              └── 3-year normalised EPS and FCF
          │              └── data_quality_notes (what's missing)
          │
          ├─── Step 2: FINANCIAL QUALITY
          │       analytics.financial_quality.quality_engine.evaluate(metrics)
          │         → FinancialQualityAssessment
          │              └── QualityTier (EXCELLENT/STRONG/GOOD/WATCH/CONCERN)
          │              └── Per-dimension: strengths, concerns
          │
          ├─── Step 3: BUSINESS RESEARCH
          │       analytics.agent.research_orchestrator.run(ticker, metrics)
          │         → (if ANTHROPIC_API_KEY set)
          │              analytics.agent.anthropic_researcher.research()
          │                → Claude API call → BusinessResearchAssessment
          │         → (if no API key)
          │              Quantitative fallback: research=None → Gate 1 fails
          │
          ├─── Step 4: BUILD VALUATION INPUT
          │       analytics.agent.valuation_builder.build(metrics, research)
          │         → ValuationInput (EPS, FCF, growth rates, WACC)
          │              └── Common fiscal-year intersection (EPS ∩ FCF window)
          │
          ├─── Step 5: VALUATION
          │       analytics.valuation.valuation_synthesizer.run_valuation(input)
          │         → ValuationAssessment
          │              ├── DCF: bear/base/bull scenarios
          │              ├── Normalized P/E: peer-relative or absolute
          │              ├── EV/EBITDA: enterprise value method
          │              ├── P/FCF: FCF yield method
          │              └── Weighted synthesis → fair value range
          │
          ├─── Step 6: PORTFOLIO CONTEXT
          │       analytics.portfolio.portfolio_synthesizer.build(weight_pct)
          │         → PortfolioContext (concentration, position sizing)
          │
          └─── Step 7: DECISION (5 gates)
                  analytics.decision.decision_synthesizer.make_investment_decision(
                      financial_quality, research, valuation, portfolio)
                    │
                    ├── Gate 1: Business understanding
                    │     FAIL → WAIT_INSUFFICIENT_EVIDENCE (pipeline stops here)
                    │
                    ├── Gate 2: Financial quality
                    │     Tier = WATCH or CONCERN → caps action at WATCH
                    │
                    ├── Gate 3: Valuation attractiveness
                    │     Zone → START_SMALL / ACCUMULATE / WATCH / WAIT
                    │
                    ├── Gate 4: Portfolio fit
                    │     High concentration → reduces position size
                    │
                    └── Gate 5: Adversarial
                          SEVERE risk → forces REDUCE or EXIT
                          │
                          ▼
                    InvestmentDecisionAssessment
                          └── DecisionAction (8 possible values)
                          └── GateResults (5 gates)
                          └── Evidence items
                          └── ThesisBreakers

  analytics.agent.renderer.render_assessment(assessment)
    → formatted string report

  PipelineResult(ok=True, assessment=…, rendered_report=…)

ConversationManager stores assessment in ConversationSession
ui/app.py renders the report
```

---

## Follow-up question flow (no new data)

```
USER types follow-up question
  │
  ▼
ui/app.py → ConversationManager.route(user_input)
  │
  ▼
conversation/intent.classify_intent(user_input)
  → INTENT_FOLLOW_UP / METRIC_EXPLANATION / EVIDENCE_REQUEST / SCENARIO_WHAT_IF
  │
  ▼
InvestmentAgent.chat(user_input, session.assessment)
  → Generates answer from stored InvestmentDecisionAssessment
  → NO new yfinance calls
  → NO new Claude API calls (typically)
  │
  ▼
Answer displayed in chat panel
```

---

## Error flow (rate limited)

```
yfinance → HTTP 429
  │
  ▼
fetcher.py raises exception
  │
  ▼
pipeline.py catches → PipelineResult(ok=False, is_rate_limited=True, error="<raw>")
  │
  ▼
conversation/manager.py
  → error_msg = _format_pipeline_error(pipeline_result)
    → "Live data could not be retrieved for [TICKER] because market data
       sources are temporarily limiting requests…"
  → session.last_error = error_msg  ← friendly message (not raw)
  → log.warning(pipeline_result.error)  ← raw message to logs only
  │
  ▼
ui/app.py → st.error(session.last_error)  ← user sees friendly message only
```

---

## Data storage locations

| What | Where | Format | TTL |
|------|-------|--------|-----|
| Company info | `data/cache/{TICKER}/info.json` | JSON | 24h |
| Income statement, balance sheet, cash flow | `data/cache/{TICKER}/financials.json` | JSON | 48h |
| Price history | `data/cache/{TICKER}/history.json` | JSON | 24h |
| Session state | Streamlit `st.session_state` | In-memory | Browser tab lifetime |
| Error messages (raw) | Application log (`logging`) | Text | Session lifetime |

No database. No persistent session storage.
