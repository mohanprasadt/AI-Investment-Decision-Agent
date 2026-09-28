# MVP Definition

> **Status:** IMPLEMENTED and ACCEPTED through Phase 10.6  
> **Last reviewed:** Phase 10.6

The MVP is a local, conversational investment decision-support tool for a single user, operating on a controlled 33-ticker universe, capable of producing structured investment decisions through a Streamlit UI with conversational follow-up.

---

## MVP IN SCOPE

### Ticker universe
- **IMPLEMENTED:** 33 pre-approved MVP tickers across Canadian (TSX), US (NYSE/NASDAQ), and Indian (NSE) markets
- **IMPLEMENTED:** Canonical ticker list in `data/mvp_tickers.py` — single source of truth, validated at import time
- **IMPLEMENTED:** Custom ticker fallback — user can type any ticker beyond the 33
- **IMPLEMENTED:** Searchable dropdown in the UI for the 33 approved tickers

The 33 MVP tickers span: Canadian Energy (7), Utilities (2), Financials (8), Real Estate (1), Consumer (3), Telecom (1), Technology (1), Other (1); US Technology (5); Indian Consumer (1), Materials (1), Financials (1).

### Data ingestion
- **IMPLEMENTED:** Financial data from yfinance (income statement, balance sheet, cash flow, price history)
- **IMPLEMENTED:** Local JSON cache in `data/cache/` — prevents repeated network calls
- **IMPLEMENTED:** Cache TTLs: company info 24h, financials 48h, price history 24h
- **IMPLEMENTED:** Failed fetches are NOT cached (Phase 10.x fix)
- **IMPLEMENTED:** Empty financials/history are NOT cached (Phase 10.x fix)
- **IMPLEMENTED:** Force Refresh option to bypass cache for a fresh fetch
- **IMPLEMENTED:** Data status panel in UI showing cache freshness per ticker

### Analysis pipeline
- **IMPLEMENTED:** Financial quality assessment (Phase 3) — ROIC, revenue growth, margins, FCF, balance sheet, dividend, earnings quality
- **IMPLEMENTED:** Business research via Claude API (Phase 4) — moat, management, industry, risk
- **IMPLEMENTED:** Quantitative fallback when no Claude API key is present
- **IMPLEMENTED:** Four valuation methods (Phase 5) — DCF, Normalized P/E, EV/EBITDA, P/FCF
- **IMPLEMENTED:** Weighted fair-value synthesis
- **IMPLEMENTED:** Portfolio context from weight % (Phase 6)
- **IMPLEMENTED:** Five sequential decision gates (Phase 7)
- **IMPLEMENTED:** Investment decision with full reasoning trace

### Decision actions
- **IMPLEMENTED:** `START_SMALL` — attractive entry point, meaningful uncertainty
- **IMPLEMENTED:** `ACCUMULATE` — attractive valuation, intact thesis
- **IMPLEMENTED:** `WATCH` — quality company, valuation not compelling
- **IMPLEMENTED:** `HOLD` — existing position, thesis intact, no reason to add
- **IMPLEMENTED:** `REDUCE` — thesis weakened
- **IMPLEMENTED:** `EXIT` — material thesis deterioration
- **IMPLEMENTED:** `WAIT_INSUFFICIENT_EVIDENCE` — missing data or failed Gate 1
- **IMPLEMENTED:** `WATCH_PENDING_DATA` — price stale/unknown

### Conversational UI
- **IMPLEMENTED:** Streamlit web interface (`run_ui.py`)
- **IMPLEMENTED:** Natural language analysis trigger ("Analyze ITC.NS", "What about AMZN?")
- **IMPLEMENTED:** Follow-up question handling — valuation, FCF, risk, decision rationale, what-if
- **IMPLEMENTED:** Context retention across follow-up turns for the active ticker
- **IMPLEMENTED:** Intent classification (ANALYZE, FOLLOW_UP, METRIC_EXPLANATION, EVIDENCE_REQUEST, SCENARIO_WHAT_IF)

### Rate-limit and reliability
- **IMPLEMENTED:** Fail-fast on Yahoo Finance 429 — no retry spin in interactive path
- **IMPLEMENTED:** User-friendly error message — no technical strings exposed to UI
- **IMPLEMENTED:** Technical error retained in application logs
- **IMPLEMENTED:** Pre-warm script (`scripts/prewarm_mvp.py`) for demo preparation

### Privacy protection
- **IMPLEMENTED:** Portfolio weight (%) is the only portfolio input accepted
- **IMPLEMENTED:** No shares, no cost basis, no total account value ever requested, stored, or used
- **IMPLEMENTED:** API key from environment variable only — never from UI

### Safety (IMPLEMENTED and VERIFIED by tests)
- Gate 1 fails → `WAIT_INSUFFICIENT_EVIDENCE` when no business research
- Gate 2 → `WATCH` tier when financial data is empty (prevents `ACCUMULATE`/`START_SMALL`)
- Empty financials cannot produce a positive recommendation
- Adversarial `SEVERE` finding forces `REDUCE` or `EXIT` regardless of valuation

---

## MVP OUT OF SCOPE

These are deliberate exclusions for the current MVP:

| Item | Reason |
|------|--------|
| Multi-user support | Single-user tool; philosophy is personal |
| Real-time price streaming | Adds infrastructure complexity |
| Automated trade execution | Human-in-loop is a safety principle |
| Portfolio-level optimisation | Out of scope; positions are evaluated individually |
| News / event monitoring | Requires continuous data pipeline |
| Tax calculation | Jurisdiction-specific; excluded |
| Historical decision tracking | Templates exist; not integrated |
| Options / derivatives | Wrong product category |
| Peer comparison (automatic) | Peer universe requires validation |
| Mobile app | Desktop-only for MVP |
| Cloud hosting | Local execution only for MVP |
| Authentication | Single-user; no auth needed |
| Database | In-memory state + local JSON cache only |

---

## POST-MVP CANDIDATES

Items that are candidates for future phases. **None are committed.** PO decision required before scheduling.

| Item | Value hypothesis | Effort estimate |
|------|-----------------|-----------------|
| Decision history / thesis journal | Compare current vs prior analysis; track thesis over time | Medium |
| Expanded ticker universe | Cover more holdings and watchlist | Low |
| Portfolio-level view | See all holdings in one view | High |
| Monitoring / alerts | Notify when thesis conditions change | High |
| Peer valuation (automatic) | Better context for multiples valuation | Medium |
| Improved FCF reconciliation detail | Decompose OCF → FCF (D&A, WC, tax) | Medium |
| Sector / industry context | Richer qualitative research | Medium |

---

## MVP acceptance criteria (VERIFIED at Phase 10.5 / 10.6)

| Criterion | Status |
|-----------|--------|
| Can select a ticker from the 33-ticker dropdown | ✅ |
| Can enter a custom ticker | ✅ |
| Analysis runs and produces a decision | ✅ (with network or cache) |
| Decision is explainable in plain language | ✅ |
| Follow-up questions work without re-running analysis | ✅ |
| Rate-limit error shows friendly message | ✅ |
| Force Refresh actually forces a fresh fetch | ✅ |
| Cache freshness visible in UI | ✅ |
| Empty financials cannot produce positive recommendation | ✅ (verified by tests) |
| No technical strings exposed in UI error messages | ✅ (verified by tests) |
| ANTHROPIC_API_KEY never appears in UI | ✅ |
| Portfolio weight accepted; shares never requested | ✅ |
| Pre-warm script runs on Windows | ✅ |
| Full test suite passes (excluding pre-existing failures) | ✅ 1,228 passed |
