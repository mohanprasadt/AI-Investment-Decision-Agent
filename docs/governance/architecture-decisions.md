# Architecture Decisions (ADRs)

> **Format:** Architecture Decision Record — each decision records the context, the options considered, and the decision made.  
> **Status labels:** ACCEPTED (in effect), SUPERSEDED (replaced by a later decision), PROPOSED (not yet decided)

---

## ADR-001 — Use yfinance as the sole data source

**Status:** ACCEPTED (Phase 1–2)  
**Context:** A data source is required for all financial analysis. Options include paid APIs (Quandl, Alpha Vantage Pro, Bloomberg), free APIs (Yahoo Finance via yfinance, Alpha Vantage free tier), and manual data entry.

**Decision:** Use `yfinance` — a free, unofficial Python library that scrapes Yahoo Finance.

**Reasons:**
- Zero cost (no API subscription required)
- Adequate data coverage for MVP scope (income statement, balance sheet, cash flow, price history)
- No API key required (yfinance handles authentication internally)
- Sufficient for a single-user, local-execution tool

**Trade-offs accepted:**
- No SLA or data quality guarantee
- Rate limiting is a real and ongoing risk
- Field names can change without notice
- Some fields unavailable for some markets (especially Indian stocks)

**Consequence:** All data reliability limitations in this product trace back to this decision. If yfinance becomes unusable, the data layer would need to be replaced entirely.

---

## ADR-002 — Sequential decision gates, not a weighted score

**Status:** ACCEPTED (Phase 7)  
**Context:** How should the decision engine combine quality, valuation, research, and portfolio signals into a single action?

**Options considered:**
1. Weighted scoring model (e.g., quality × 40% + valuation × 30% + research × 30%)
2. Sequential hierarchical gates (evaluate quality first, then valuation, then portfolio)

**Decision:** Sequential hierarchical gates.

**Reasons:**
- The investment philosophy explicitly requires this: "Quality is the primary filter; valuation is the timing filter."
- A weighted score allows bad quality to be compensated by cheap price — this is a value-trap pattern to avoid
- Sequential gates make the reasoning auditable and explainable: each gate has one responsibility
- The investor's documented philosophy (config/investment_philosophy.md) prescribes a specific order of analysis

**Consequence:** A WATCH-tier quality assessment will always cap the action at WATCH regardless of valuation. This is correct by design.

**Do not change without PO authorisation.**

---

## ADR-003 — Portfolio weight only; no shares, cost, or account value

**Status:** ACCEPTED (Phase 6)  
**Context:** How much portfolio context should the system use? Options range from no portfolio context to full portfolio knowledge (shares, cost basis, account value, other holdings).

**Decision:** Accept only `portfolio_weight_pct` (float | None). All other portfolio data is excluded.

**Reasons:**
1. Privacy: Total account value and position details are sensitive. A percentage conveys the same information needed for fit assessment.
2. Sunk-cost protection: Average cost must not influence forward-looking decisions. Excluding it by design prevents this mistake.
3. Simplicity: A single input is clear and unambiguous.

**Consequence:** Portfolio analysis is limited to concentration assessment. A multi-ticker portfolio view is not possible without cross-ticker weight data (but still no shares/cost required).

**Do not change without PO authorisation.**

---

## ADR-004 — Local JSON cache, no database

**Status:** ACCEPTED (Phase 1–2)  
**Context:** Where should fetched financial data be stored?

**Options considered:**
1. In-memory only (no persistence)
2. Local JSON files in `data/cache/`
3. SQLite database
4. Remote database

**Decision:** Local JSON files with TTL-based invalidation.

**Reasons:**
- No infrastructure required (no database setup, no server)
- Human-readable files (can inspect cache contents directly)
- TTL logic is simple to implement and understand
- Sufficient for single-user, single-machine use case

**Trade-offs accepted:**
- JSON reads/writes are slower than a database at scale — acceptable for single-user use
- No transactional guarantees (a partial write could corrupt a cache file)
- No sharing between multiple machines

---

## ADR-005 — Fail-fast on HTTP 429 in interactive path; retry in pre-warm only

**Status:** ACCEPTED (Phase 10.5)  
**Context:** When Yahoo Finance rate-limits a request (HTTP 429), should the system retry?

**Options considered:**
1. Retry with backoff in all paths (interactive + pre-warm)
2. No retry anywhere — always fail fast
3. Fail fast in interactive path; retry with backoff in pre-warm script only

**Decision:** Option 3.

**Reasons:**
- During interactive use, a 30–90 second retry hang is a poor user experience
- Rate limits at Yahoo Finance often persist for several minutes — retrying immediately is unlikely to help
- Pre-warm is a background operation where the user is not waiting; retry is appropriate there
- The interactive user can see the friendly error and decide to try again manually

**Implementation:** `analytics/agent/pipeline.py` does not retry. `scripts/prewarm_mvp.py` retries with delays.

---

## ADR-006 — ANTHROPIC_API_KEY from environment only

**Status:** ACCEPTED (established early, explicitly documented Phase 10.6)  
**Context:** How should the Anthropic API key be provided?

**Options considered:**
1. UI input field (text box in Streamlit)
2. Configuration file
3. Environment variable only

**Decision:** Environment variable only.

**Reasons:**
- UI input would expose the key in browser history and Streamlit session state
- Configuration files risk accidental commit to version control
- Environment variables are the standard practice for secrets management

**Enforcement:** The code reads `ANTHROPIC_API_KEY` from `os.environ`. No UI field for this exists. No configuration file stores it.

---

## ADR-007 — Quantitative fallback when no API key (WAIT_INSUFFICIENT_EVIDENCE)

**Status:** ACCEPTED (Phase 4)  
**Context:** What should the system do if the Anthropic API key is not set?

**Options considered:**
1. Error and refuse to run
2. Skip Gate 1 and produce a decision from financial data only
3. Fail Gate 1 → WAIT_INSUFFICIENT_EVIDENCE

**Decision:** Option 3 — WAIT_INSUFFICIENT_EVIDENCE is the correct output.

**Reasons:**
- The investment philosophy states: "I will not invest in a business I don't understand"
- Without qualitative research, business understanding is not established
- Producing a financial-data-only recommendation risks producing a positive recommendation for a business the investor doesn't understand
- WAIT_INSUFFICIENT_EVIDENCE is not an error — it is a correct, safe output

---

## ADR-008 — ConversationSession.last_error stores friendly message only

**Status:** ACCEPTED (Phase 10.5 UX polish)  
**Context:** When a pipeline error occurs, `session.last_error` is rendered directly in the UI via `st.error(session.last_error)`. What should it contain?

**Options considered:**
1. Raw error string from `PipelineResult.error`
2. Friendly formatted message from `_format_pipeline_error()`

**Decision:** Friendly formatted message only. Raw error goes to logs.

**Reason:** `app.py` renders `session.last_error` directly. If it contains raw technical strings (`CANNOT_COMPLETE_LIVE_ANALYSIS`, `yfinance`, `429`, Python stack traces), those strings appear in the UI. This was the exact bug present before the fix.

**Implementation change:** `session.last_error = error_msg` (not `pipeline_result.error`). `log.warning(pipeline_result.error)` preserves the raw error for debugging.
