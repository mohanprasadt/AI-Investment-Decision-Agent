# Product Backlog

> **Status:** PROPOSED — no items are committed. PO decision required before any item moves to a phase brief.  
> **Last updated:** Phase 10.6

This is the Product Owner's working list of candidate improvements. Items are grouped by theme. Each item includes a value hypothesis and rough effort estimate to support prioritisation.

---

## How to use this backlog

This is an input to phase planning, not a commitment. Before any item becomes a phase:
1. Write a one-paragraph problem statement: what problem does this solve for you as the investor?
2. Define acceptance criteria before implementation starts
3. Confirm scope boundaries (what is explicitly OUT of scope)

---

## Theme 1 — Decision continuity and history

### B1 — Decision journal integration
**Problem:** Each analysis is independent. There is no way to compare today's recommendation to what the system said 3 months ago for the same ticker.  
**Value hypothesis:** Enables thesis tracking over time; catches when a WATCH should become ACCUMULATE or EXIT.  
**What exists:** `journal/TEMPLATE_journal_entry.json` and `portfolio/thesis/TEMPLATE_thesis.json` are templates but not integrated.  
**What is needed:** Decision persistence (JSON or SQLite), a journal reader, a comparison renderer.  
**Effort:** Medium  
**Dependencies:** Decision persistence architecture decision (currently: in-memory only)

### B2 — Thesis change detection
**Problem:** You cannot tell whether the system's reasoning has changed between two runs of the same ticker, even if the action changes.  
**Value hypothesis:** Catches subtle thesis drift — e.g., moat classification changed from NARROW to NONE.  
**Effort:** Medium  
**Depends on:** B1 (journal)

---

## Theme 2 — Data quality and completeness

### B3 — Continuing-operations NI availability flag
**Problem:** When yfinance does not provide a continuing-ops NI field, the system falls back to total NI. This is logged but not visible in the UI. The ITC.NS case showed this matters — a one-time gain overstated EPS by 76%.  
**Value hypothesis:** The PO should see a prominent warning when EPS is calculated from total NI rather than continuing-ops NI.  
**Effort:** Low  
**Note:** DOCUMENTATION ONLY — no code change authorised in Phase 10.6

### B4 — D&A and working capital in FCF reconciliation
**Problem:** The FCF-vs-EPS reconciliation shows OCF and capex but cannot fully decompose the gap because D&A and working capital changes are not separately persisted.  
**Value hypothesis:** A complete reconciliation gives higher confidence that FCF is a reliable proxy for earnings quality.  
**Effort:** Low (add fields to normalizer) to Medium (depends on yfinance field availability)

### B5 — Peer valuation data
**Problem:** Peer comparison (P/E relative to sector peers) is architecturally supported (`PeerData` model exists) but requires manual input. No peer data is automatically fetched.  
**Value hypothesis:** Multiples valuation is stronger with peer context.  
**Effort:** Medium  
**Risk:** Peer universe definition is non-trivial — wrong peers produce worse analysis than no peers

---

## Theme 3 — Ticker universe

### B6 — Expand MVP ticker universe
**Problem:** 33 tickers covers a representative sample but misses tickers the investor actually holds or monitors.  
**Value hypothesis:** Adding 5–10 tickers to the pre-approved universe would cover more of the actual portfolio.  
**Effort:** Low (add to mvp_tickers.py, prewarm)  
**Note:** Custom ticker input already works — this is about pre-warming and the official list

### B7 — Ticker universe governance
**Problem:** There is no formal process for adding or removing tickers from the MVP universe.  
**Value hypothesis:** A lightweight process (e.g., "add after one confirmed analysis session") prevents the list from growing unmanaged.  
**Effort:** Very Low

---

## Theme 4 — Portfolio-level view

### B8 — Portfolio-level analysis summary
**Problem:** You can only analyse one ticker at a time. There is no way to see all current positions in one view.  
**Value hypothesis:** A one-page portfolio summary would show which positions are WATCH vs HOLD vs REDUCE without running each analysis individually.  
**Effort:** High  
**Risk:** Requires decision persistence (B1) and multi-ticker orchestration

### B9 — Concentration alert
**Problem:** If you add to a position that already represents 15%+ of the portfolio, there is no automatic warning.  
**Value hypothesis:** Prevents inadvertent over-concentration.  
**Effort:** Low (concentration logic already exists in portfolio_calculator.py — UI alert is the addition)

---

## Theme 5 — Monitoring and alerts

### B10 — Price target alert
**Problem:** No notification when a WATCH ticker crosses into the START_SMALL accumulation zone.  
**Value hypothesis:** You don't have to periodically re-run analysis for WATCH tickers — the system alerts when conditions change.  
**Effort:** High  
**Dependencies:** Continuous price monitoring (background task or scheduled script), notification mechanism

### B11 — Earnings-release refresh trigger
**Problem:** Cache TTLs mean you might run analysis on stale data without knowing an earnings release has occurred.  
**Value hypothesis:** After earnings, a refresh prompt appears for affected tickers.  
**Effort:** High  
**Dependencies:** Event calendar integration or manual trigger

---

## Theme 6 — Technical reliability

### B12 — Streamlit session persistence
**Problem:** Closing the browser tab or restarting the Streamlit server clears all session state. A mid-analysis refresh loses the conversation.  
**Value hypothesis:** The conversation and analysis state should survive a browser refresh.  
**Effort:** Medium  
**Options:** Server-side session store (Redis/SQLite), URL-encoded state, or explicit "Save session" button

### B13 — Automated cache refresh schedule
**Problem:** Cache TTLs expire after 24–48 hours. The user must manually run the pre-warm script.  
**Value hypothesis:** A scheduled job would keep the cache warm without manual intervention.  
**Effort:** Low (cron or Task Scheduler wrapper around prewarm_mvp.py)

### B14 — Test for UI rendering
**Problem:** The Streamlit UI has no automated tests. A regression in the UI rendering layer (app.py) would not be caught by the existing test suite.  
**Value hypothesis:** Even a smoke test (app starts, shows dropdown, completes analysis) would catch major regressions.  
**Effort:** Medium  
**Options:** Playwright, Streamlit's testing API

---

## Theme 7 — Analysis quality

### B15 — Sector/industry context in research
**Problem:** The Claude API research prompt does not currently include sector-level context (e.g., "Canadian energy sector context: …"). Research relies on general model knowledge.  
**Value hypothesis:** Sector context in the prompt could improve moat and risk assessment accuracy.  
**Effort:** Low (prompt change) to Medium (if sector data is structured)

### B16 — Financial institution DCF alternative
**Problem:** DCF is excluded for banks and insurance companies (correctly). But no alternative valuation method specifically suited to financial institutions is used instead (e.g., P/BV, P/TBV, ROE-to-COE model).  
**Value hypothesis:** Financial institutions represent 8 of 33 MVP tickers — better methods improve recommendation quality for a quarter of the universe.  
**Effort:** Medium

---

## Backlog priority (PO suggestion — PROPOSED)

| Priority | Item | Reason |
|----------|------|--------|
| High | B1 (Decision journal) | Enables thesis tracking — biggest gap in current MVP |
| High | B13 (Automated cache refresh) | Low effort, eliminates manual maintenance |
| High | B9 (Concentration alert) | Low effort, existing logic exists |
| Medium | B3 (Continuing-ops NI flag) | Low effort; improves transparency |
| Medium | B6 (Expand ticker universe) | Low effort; directly covers more of the portfolio |
| Medium | B16 (Financial institution valuation) | 8 of 33 tickers are financials |
| Low | B4 (FCF reconciliation detail) | Nice-to-have; yfinance field availability uncertain |
| Low | B15 (Sector context in research) | Prompt quality improvement |
| Defer | B8, B10, B11 | High effort; requires significant infrastructure |
