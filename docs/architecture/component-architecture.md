# Component Architecture

> **Audience:** Developer reference and PO learning  
> **Status:** IMPLEMENTED as described  
> **See also:** [Architecture Overview](architecture-overview.md) for the high-level view

This document lists each major module, its responsibility, its key inputs and outputs, and its phase of origin.

---

## Data layer (L1)

### `data/ingestion/fetcher.py`

**Purpose:** Fetch financial data from Yahoo Finance (yfinance) and cache to local JSON files.

**Key responsibilities:**
- Fetch company info, income statement, balance sheet, cash flow, and price history
- Cache each type separately in `data/cache/{TICKER}/`
- Enforce TTLs (info 24h, financials 48h, history 24h)
- Detect and skip ETFs (different data profile from equities)
- Fail fast on HTTP 429 — no retry in interactive path
- Never cache failed fetches or empty data (Phase 10.x fix)

**Key constants:**
- `KNOWN_ETFS` — set of tickers treated as ETFs
- `INFO_TTL_HOURS = 24`, `FINANCIALS_TTL_HOURS = 48`, `HISTORY_TTL_HOURS = 24`

**Key functions:**
- `fetch_ticker(ticker, force_refresh)` — main entry point
- Internal: `_load_cache()`, `_is_fresh()`, `_save_cache()`

**Phase introduced:** Phase 1–2

---

### `data/ingestion/normalizer.py`

**Purpose:** Convert raw yfinance dictionary output into typed `CompanyFinancialMetrics`.

**Key responsibilities:**
- Map yfinance field names to structured model fields
- Compute derived fields (FCF = OCF − capex, normalised EPS, normalised FCF)
- Apply 3-year averaging for normalised EPS and FCF
- Prefer continuing-operations NI over total NI for EPS normalisation
- Record what data is missing in `data_quality_notes`

**Output:** `CompanyFinancialMetrics` — the single typed model that all downstream L2 analysis uses.

**Critical logic:** Continuing-operations NI preference chain — attempts several yfinance field names before falling back to total NI. Documents which source was used in `eps_provenance` note.

**Phase introduced:** Phase 2, key upgrade in Phase 9.9b

---

### `data/mvp_tickers.py`

**Purpose:** Canonical 33-ticker MVP universe.

**Exports:**
- `MVP_TICKERS` — list of ticker strings (e.g., `["ENB.TO", "TD.TO", ...]`)
- `MVP_TICKER_MAP` — `{ticker: company_name}` dict for UI display
- `MVP_TICKER_SYMBOLS` — `{ticker: display_label}` for the dropdown

**Validation:** `_validate()` runs at import time — fails loudly if the list is malformed.

**Phase introduced:** Phase 10.5

---

## Analysis layer (L2)

### `analytics/financial_quality/quality_engine.py`

**Purpose:** Evaluate financial metrics against quality thresholds.

**Dimensions evaluated:** Revenue growth, ROIC, gross/operating/net margins, FCF conversion, balance sheet/debt, dividend quality, earnings quality.

**Output:** `FinancialQualityAssessment` — includes `QualityTier` (EXCELLENT/STRONG/GOOD/WATCH/CONCERN), per-dimension strengths and concerns, and an overall tier.

**Thresholds source:** `config/thresholds.yaml` — loaded by `analytics/financial_quality/thresholds_engine.py`. These are guidelines, not absolute rules.

**Phase introduced:** Phase 3

---

### `analytics/agent/anthropic_researcher.py`

**Purpose:** Call the Anthropic Claude API to conduct qualitative business research.

**What it researches:** Moat (competitive advantage), management quality, industry position, key risks, bull and bear case.

**Quantitative fallback:** If `ANTHROPIC_API_KEY` is not set, this module signals a failure. Gate 1 then produces `WAIT_INSUFFICIENT_EVIDENCE`.

**Output:** `BusinessResearchAssessment`

**Phase introduced:** Phase 4

---

### `analytics/valuation/`

**Purpose:** Estimate intrinsic fair value using four independent methods.

| Module | Method | Applicability |
|--------|--------|---------------|
| `dcf_engine.py` | Discounted Cash Flow (bear/base/bull) | Most equities except financials |
| `multiples_engine.py` | Normalized P/E | Earnings-generating equities |
| `multiples_engine.py` | EV/EBITDA | Capital-intensive businesses |
| `multiples_engine.py` | P/FCF | FCF-generating equities |
| `valuation_synthesizer.py` | Weighted fair value synthesis | Always — combines above |
| `method_selector.py` | Applicability rules | Selects which methods apply |
| `margin_of_safety.py` | MOS and zone classification | Always |

**Output:** `ValuationAssessment` — includes per-method bear/base/bull ranges, weights, weighted synthesis, and valuation zone (START_SMALL / ACCUMULATE / WATCH / WAIT).

**Configuration:** `config/valuation_config.yaml` — DCF discount rate (default 9%), MOS framework, accumulation zones.

**Phase introduced:** Phase 5

---

### `analytics/portfolio/`

**Purpose:** Incorporate portfolio context (position size) into the analysis.

**Key constraint:** Only `portfolio_weight_pct` (float | None) is accepted. No shares, cost basis, or account value.

**Modules:**
- `portfolio_calculator.py` — concentration and allocation calculations
- `portfolio_synthesizer.py` — portfolio context for the decision
- `concentration_analyzer.py` — position size risk
- `incremental_scenarios.py` — what-if scenarios (adding X% more)

**Output:** `PortfolioContext`

**Phase introduced:** Phase 6

---

## Decision layer (L3)

### `analytics/decision/decision_synthesizer.py`

**Purpose:** Apply the investment philosophy through 5 sequential gates to produce a final `DecisionAction`.

**Key function:** `make_investment_decision(financial_quality, research, valuation, portfolio)` — the only public entry point for decision-making.

**Sunk-cost protection:** Average cost (if accidentally passed) is explicitly excluded from gate logic.

**Output:** `InvestmentDecisionAssessment`

**Phase introduced:** Phase 7

---

### `analytics/decision/gate1_understanding.py` through `gate5_adversarial.py`

**Purpose:** Each gate enforces one principle of the investment philosophy.

| Module | Gate | Question |
|--------|------|----------|
| `gate1_understanding.py` | Gate 1 | Do I understand this business? |
| `gate2_quality.py` | Gate 2 | Is this a quality business? |
| `gate3_valuation.py` | Gate 3 | Is the price attractive? |
| `gate4_portfolio.py` | Gate 4 | Does this fit my portfolio? |
| `gate5_adversarial.py` | Gate 5 | What could break the thesis? |

**Each gate returns:** `GateResult(passed, tier, action_if_failed, notes)`

**Phase introduced:** Phase 7

---

### `analytics/decision/decision_models.py`

**Purpose:** All data models for the decision layer.

**Key types:**
- `DecisionAction` — 8-value enum (the final recommendation)
- `QualityTier` — EXCELLENT/STRONG/GOOD/WATCH/CONCERN
- `AdversarialRisk` — LOW/MODERATE/HIGH/SEVERE
- `InvestmentDecisionAssessment` — the full structured output
- `GateResult` — single gate pass/fail with notes
- `DecisionEvidenceItem` — single piece of evidence with source and strength
- `ThesisBreaker` — a condition that would invalidate the thesis

**Phase introduced:** Phase 7

---

## Presentation layer

### `analytics/agent/renderer.py`

**Purpose:** Convert `InvestmentDecisionAssessment` into a human-readable text report.

**Output:** Formatted string displayed in the Streamlit UI and CLI.

**Key function:** `render_assessment(assessment)` → `str`

**No analysis logic lives here.** If the renderer disagrees with the decision, the decision is the truth.

---

### `analytics/agent/investment_agent.py`

**Purpose:** Top-level orchestration. Assembles the pipeline and routes follow-up questions.

---

### `analytics/agent/pipeline.py`

**Purpose:** Single-function pipeline entry point used by both UI and CLI.

**Key contract:** Always returns `PipelineResult` — never raises. The caller checks `.ok` before using `.assessment`.

**`is_rate_limited` flag:** Set when Yahoo Finance returns HTTP 429. Callers use this to show a specific friendly error message.

---

## UI and conversation layer

### `ui/app.py`

**Purpose:** Streamlit application — presentation only.

**Responsibilities:** Renders the ticker dropdown (from `data/mvp_tickers.py`), data status card, portfolio weight input, analysis output, and chat panel. No analysis logic.

### `ui/data_status.py`

**Purpose:** Reads the local cache to show per-ticker freshness (info, financials, history) before analysis is triggered.

### `conversation/manager.py`

**Purpose:** Thin adapter between the UI and the analytics layers. Manages session state, routes intent, handles friendly error messages.

**Key rule:** `session.last_error` stores the friendly error message (not the raw error). Raw error goes to logs only.

### `conversation/session.py`

**Purpose:** `ConversationSession` dataclass — holds `ticker`, `assessment`, `history` (list of `ChatTurn`), `portfolio_weight_pct`, `last_error`.

### `conversation/intent.py`

**Purpose:** Classify user input into one of 6 intent types:
- `INTENT_ANALYZE` — new analysis request
- `INTENT_FOLLOW_UP` — question about current analysis
- `INTENT_METRIC_EXPLANATION` — "what does ROIC mean?"
- `INTENT_EVIDENCE_REQUEST` — "show me the data"
- `INTENT_SCENARIO_WHAT_IF` — "what if price drops 10%?"
- `INTENT_UNKNOWN_CLARIFICATION` — not classified

---

## Configuration files

| File | Purpose |
|------|---------|
| `config/investment_philosophy.md` | The investor's documented decision philosophy — referenced by gate logic |
| `config/thresholds.yaml` | Financial quality thresholds per dimension |
| `config/valuation_config.yaml` | DCF assumptions, MOS zones, accumulation zones |
