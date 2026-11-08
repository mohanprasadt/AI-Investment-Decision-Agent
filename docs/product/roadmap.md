# Project Roadmap

> **Status pointer (2026-10-11):** This page is the phase history only. Feature status, priorities and the forward plan live in the [Product Feature Inventory and Roadmap](product-feature-inventory-and-roadmap.md). Phase 11A/11B work exists in the working tree and is not described below.

> **Last updated:** Phase 10.6  
> **Note:** Early phase history (Phases 1–8) is [RECONSTRUCTED] from repository evidence — module docstrings, file names, test names, validation reports, and README content. Phase 9+ history is well-evidenced.

---

## Visual roadmap

```
Phase 1-2   Data Foundation          ████████ DONE
Phase 3     Financial Quality        ████████ DONE
Phase 4     Business Research        ████████ DONE
Phase 5     Valuation                ████████ DONE
Phase 6     Portfolio Context        ████████ DONE
Phase 7     Decision Architecture    ████████ DONE
Phase 7.5   Data Freshness           ████████ DONE
Phase 8     Renderer & Agent Shell   ████████ DONE
Phase 9.x   Valuation Hardening      ████████ DONE
Phase 9.9b  EPS/FCF Alignment        ████████ DONE (verified)
Phase 10    Conversational UI        ████████ DONE
Phase 10.x  Yahoo Reliability        ████████ DONE
Phase 10.5  MVP Usability            ████████ DONE (accepted)
Phase 10.6  Documentation            ████░░░░ IN PROGRESS ← YOU ARE HERE
Phase 11+   To be defined            ░░░░░░░░ NOT STARTED
```

---

## Phase history

### Phase 1–2 — Data Foundation [RECONSTRUCTED]

**Objective:** Establish the data ingestion and normalisation pipeline.

**Why it existed:** Before any analysis is possible, the system needs to reliably fetch financial data and map it to a structured, typed model. This is the foundation everything else builds on.

**Major deliverables:**
- `data/ingestion/fetcher.py` — yfinance fetch with local JSON cache (info, financials, price history)
- `data/ingestion/normalizer.py` — raw yfinance fields → `CompanyFinancialMetrics` typed model
- Cache directory: `data/cache/` with TTLs (info 24h, financials 48h, history 24h)
- ETF detection (separate handling for ETFs vs equities)
- `CompanyFinancialMetrics` model covering revenue, margins, FCF, debt, dividends, earnings quality

**Important decisions:**
- Use yfinance (free, no API key for data) as the sole data source for MVP
- Cache locally as JSON — no database dependency
- Never fabricate missing fields — use `None` and report in `data_quality_notes`

**Current status:** IMPLEMENTED. Ongoing maintenance as yfinance field names change.

**Known debt:** yfinance field-name changes across versions require ongoing normalizer updates.

---

### Phase 3 — Financial Quality Assessment [RECONSTRUCTED]

**Objective:** Evaluate raw financial data against investment philosophy thresholds.

**Why it existed:** Raw financial numbers are not useful alone. The system needed to classify whether each dimension (ROIC, margins, FCF, debt) meets the investor's standards.

**Major deliverables:**
- `analytics/financial_quality/quality_engine.py` — evaluates each dimension; produces `FinancialQualityAssessment`
- `analytics/financial_quality/thresholds_engine.py` — loads thresholds from `config/thresholds.yaml`
- `analytics/financial_quality/calculations.py` — deterministic financial calculations
- `config/thresholds.yaml` — all quality thresholds (guidelines, not absolute rules)

**Dimensions evaluated:** Revenue growth, ROIC, margins (gross/operating/net), FCF conversion, balance sheet/debt, dividend quality, earnings quality.

**Current status:** IMPLEMENTED and tested.

---

### Phase 4 — Business Research [RECONSTRUCTED]

**Objective:** Add qualitative research using the Claude API.

**Why it existed:** Numbers alone cannot assess business quality. The investment philosophy explicitly requires understanding the business model, competitive moat, management quality, and risks before looking at valuation.

**Major deliverables:**
- `analytics/agent/anthropic_researcher.py` — Claude API integration
- `analytics/business_research/` — models for moat, management, industry, risk, bull/bear cases
- `agent/prompts/` — prompt templates for each research dimension
- `analytics/agent/research_orchestrator.py` — coordinates research workflow
- Quantitative fallback: when no API key, Gate 1 fails → `WAIT_INSUFFICIENT_EVIDENCE` (correct, safe)

**Evidence hierarchy implemented:** Tier 1 (filings), Tier 2 (databases), Tier 3 (model-derived) — tagged by source and strength.

**Current status:** IMPLEMENTED. API key required for full research path.

---

### Phase 5 — Valuation [RECONSTRUCTED]

**Objective:** Estimate intrinsic value using multiple independent methods.

**Why it existed:** Valuation is the timing filter. The philosophy states: "A great company is not automatically a great investment at any price." Without fair value estimates, the decision cannot go beyond WATCH.

**Major deliverables:**
- `analytics/valuation/dcf_engine.py` — DCF with bear/base/bull scenarios
- `analytics/valuation/multiples_engine.py` — P/E, P/FCF, EV/EBITDA
- `analytics/valuation/valuation_synthesizer.py` — weighted fair value synthesis
- `analytics/valuation/method_selector.py` — applicability rules per company type
- `analytics/valuation/margin_of_safety.py` — MOS calculation and zone classification
- `config/valuation_config.yaml` — DCF assumptions, zones, MOS guidelines

**Current status:** IMPLEMENTED. Four methods, weighted synthesis, bear/base/bull ranges.

---

### Phase 6 — Portfolio Context [RECONSTRUCTED]

**Objective:** Factor in the user's existing portfolio position when sizing a recommendation.

**Why it existed:** The same company can warrant different actions depending on whether you already own 10% of your portfolio in it vs 0%. The system needed to adjust its recommendation for concentration and position sizing.

**Major deliverables:**
- `analytics/portfolio/portfolio_calculator.py` — concentration and allocation calculations
- `analytics/portfolio/portfolio_synthesizer.py` — portfolio context for the decision
- `analytics/portfolio/concentration_analyzer.py` — position size risk evaluation
- `analytics/portfolio/incremental_scenarios.py` — what-if scenarios
- Privacy protection: portfolio weight (%) only — no shares, no cost basis, no account value

**Current status:** IMPLEMENTED. Weight-only input strictly enforced.

---

### Phase 7 — Decision Architecture [RECONSTRUCTED]

**Objective:** Combine all upstream phases through a principled decision framework.

**Why it existed:** Previously each analysis phase produced its own output but there was no single, principled arbiter of the final investment action. Phase 7 is the decision engine.

**Major deliverables:**
- `analytics/decision/decision_synthesizer.py` — five-gate sequential pipeline
- `analytics/decision/gate1_understanding.py` — business understanding gate
- `analytics/decision/gate2_quality.py` — financial quality gate
- `analytics/decision/gate3_valuation.py` — valuation attractiveness gate
- `analytics/decision/gate4_portfolio.py` — portfolio fit gate
- `analytics/decision/gate5_adversarial.py` — adversarial stress test gate
- `analytics/decision/decision_models.py` — `InvestmentDecisionAssessment`, `DecisionAction`, all enums
- `config/investment_philosophy.md` — documented philosophy that gates enforce

**Key design decision:** Sequential gates, not a weighted score. Quality is the primary filter. Valuation is the timing filter. A SEVERE adversarial finding overrides all other signals.

**Current status:** IMPLEMENTED and heavily tested.

---

### Phase 7.5 — Data Freshness Assessment

**Objective:** Track and communicate the age of financial data used in analysis.

**Why it existed:** Stale data can produce misleading conclusions. The system needed to know when financial statements were last updated and communicate this transparently.

**Major deliverables:**
- `analytics/data_freshness.py` — `DataFreshnessAssessment` model
- Integration into decision output and renderer
- `WATCH_PENDING_DATA` action when price is unknown or stale

**Current status:** IMPLEMENTED.

---

### Phase 8 — Renderer & Agent Shell [RECONSTRUCTED]

**Objective:** Produce human-readable reports from structured decision objects.

**Why it existed:** The decision engine produced structured data (`InvestmentDecisionAssessment`) but no human-readable output. Phase 8 added the presentation layer.

**Major deliverables:**
- `analytics/agent/renderer.py` — formats `InvestmentDecisionAssessment` as readable report
- `analytics/agent/investment_agent.py` — top-level agent orchestration
- `analytics/agent/data_loader.py` — thin adapter: fetch → normalise → quality → `DataLoadResult`
- `analytics/agent/valuation_builder.py` — `DataLoadResult` → `ValuationInput`
- `run_agent.py` — CLI entry point

**Current status:** IMPLEMENTED.

---

### Phase 9.x — Valuation Hardening Series

**Objective:** Fix systematic accuracy problems in valuation inputs.

**Why it existed:** Real-world testing against ITC.NS, TD.TO, and other tickers exposed several calculation errors. These phases corrected them methodologically.

**Sub-phases (evidenced by validation reports and test files):**

| Sub-phase | Problem fixed |
|-----------|---------------|
| Phase 9 | Initial valuation integration |
| Phase 9.1 | EV/EBITDA cash sourcing — broad cash vs narrow cash |
| Phase 9.2 | FCF normalisation multi-year averaging |
| Phase 9.3 | ITC.NS baseline validation (first real-ticker test) |
| Phase 9.3b | ITC classification corrections, supplemental cash fields |
| Phase 9.4–9.4d | Additional valuation corrections |
| Phase 9.5–9.9 | FCF/EPS period alignment, continuing-operations NI |

**Current status:** IMPLEMENTED and verified. See Phase 9.9b baseline in README.

---

### Phase 9.9b — EPS/FCF Period Alignment (KEY PHASE)

**Objective:** Ensure EPS and FCF normalisation use the same fiscal-year window.

**Why it existed:** The system was averaging EPS over one set of years and FCF over a different set, creating an artificial "gap" that was not real — it was a methodological inconsistency. This phase also fixed the use of total net income (which could include one-time discontinued-operations gains) for EPS normalisation.

**The ITC.NS problem:** In FY2025, ITC Ltd reported ₹197.31B in continuing-operations net income but ₹347.47B in total net income (₹150.16B was a one-time demerger gain). Using total net income would have overstated normalised EPS by ~76%.

**Major deliverables:**
- Continuing-operations NI preference chain in `normalizer.py`
- Common fiscal-year intersection logic in `valuation_builder.py`
- Period-alignment renderer in `renderer.py` (shows ✓ SAME-PERIOD BASIS or ⚠ PERIOD MISMATCH)
- `tests/test_phase99.py` — 6 test classes verifying all alignment cases

**Verified ITC.NS baseline:** Normalised EPS ₹16.05/share, FCF/share ₹12.04/share, same fiscal years FY2024–FY2026.

**Current status:** IMPLEMENTED and VERIFIED.

**PO lesson:** This phase demonstrates why real-ticker validation matters. A theoretical implementation can look correct but produce misleading numbers on actual data.

---

### Phase 10 — Conversational UI

**Objective:** Replace the CLI with a conversational Streamlit interface.

**Why it existed:** The CLI required technical knowledge to use. A conversational interface makes the analysis accessible to the intended user — an investor, not a developer.

**Major deliverables:**
- `ui/app.py` — Streamlit application
- `run_ui.py` — UI entry point
- `conversation/manager.py` — `ConversationManager` orchestrates session + pipeline + response
- `conversation/session.py` — `ConversationSession` holds per-session state
- `conversation/intent.py` — intent classification (6 intent types)
- Follow-up question rendering for 10+ topics without re-running analysis
- 64 conversation tests in `tests/test_phase10_conversation.py`

**Key architectural decision:** Follow-up questions re-use the existing `InvestmentDecisionAssessment` in session state — no additional Yahoo Finance calls. A stale analysis can still answer follow-up questions.

**Current status:** IMPLEMENTED and tested.

---

### Phase 10.x — Yahoo Finance Reliability

**Objective:** Fix catastrophic 429 amplification and protect cached-data paths.

**Why it existed:** During real-world use, a Yahoo Finance 429 rate-limit triggered a retry loop that caused 90-second hangs, and when the retry loop itself failed, the error text was exposed directly in the UI.

**Sub-phases:**

| Fix | What it addressed |
|-----|------------------|
| P0 — Empty financials not cached | Failed fetches were being cached, poisoning future reads |
| P1 — Failed cache rejected | Cache entries with `_fetch_success=False` were served |
| History fix — Empty history not cached | Price history with no rows was cached as valid |
| Fix 1 — fetch_ticker() short-circuit | On info failure, skip financials/history (saves 3 calls) |
| Fix 2 — Retry delays [30, 60] | Replaced [5, 15, 30] with more conservative delays |

**Diagnostic work:** 4 diagnostic scripts, 4 output files, 5 detailed reports produced to understand Yahoo Finance rate-limiting behaviour before any code changes.

**Current status:** IMPLEMENTED. 36 fetcher-specific tests passing.

---

### Phase 10.5 — MVP Usability & Demo Readiness

**Objective:** Make the system usable and reliable for a demonstration without developer intervention.

**Why it existed:** The system was technically functional but had several UX and reliability gaps that would embarrass it in a demo: broken Force Refresh, raw error strings in the UI, no ticker selector, no cache visibility.

**Decisions made (by PO):**
1. Fail-fast on 429 — no retry spin in interactive path
2. Searchable MVP ticker dropdown + custom fallback
3. Fix Force Refresh wiring (it was silently broken)
4. Windows-compatible sequential pre-warm with 35s delays
5. Cache as demo experience — no synthetic data
6. Data status visibility in UI

**Major deliverables:**
- `data/mvp_tickers.py` — canonical 33-ticker universe
- `ui/data_status.py` — cache status reader
- `scripts/prewarm_mvp.py` — pre-warm script
- `analytics/agent/pipeline.py` — fail-fast 429, `is_rate_limited` flag
- `conversation/manager.py` — friendly error messages, raw error in logs only
- `ui/app.py` — MVP ticker dropdown, data status card
- `tests/test_phase105.py` — 43 tests

**UX polish (Phase 10.6 prelude):** `session.last_error` now stores the friendly message rather than the raw technical string — the fix that eliminated the final route by which raw errors reached the UI.

**Current status:** IMPLEMENTED and ACCEPTED.

---

### Phase 10.6 — Documentation & Product Governance Foundation

**Objective:** Create maintainable Product Owner documentation for the entire project.

**Why it exists:** After 10+ phases of development, the only documentation was scattered phase reports and README files. A Product Owner cannot manage a product they cannot fully comprehend without reading source code.

**Major deliverables:** This `docs/` directory.

**Current status:** IN PROGRESS.

---

## Phase 11 and beyond

**Status: NOT STARTED. PO decision required.**

No Phase 11 scope has been committed. The Product Owner should review the [Product Backlog](product-backlog.md) and [Current State](current-state.md) before defining Phase 11.

**Suggested PO exercise before Phase 11:** Write a one-page Phase 11 brief answering: What problem does this phase solve for me as the investor? What would I be able to do after Phase 11 that I cannot do today?
