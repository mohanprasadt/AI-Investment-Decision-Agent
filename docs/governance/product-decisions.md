# Product Decisions

> **Purpose:** Record PO-level decisions — what the product is, who it's for, what it does and doesn't do  
> **Format:** Each decision records context, options, decision, and rationale  
> **Status labels:** DECIDED, OPEN (pending), SUPERSEDED

---

## PD-001 — Single-user product: no multi-user support in MVP

**Status:** DECIDED  
**Context:** Who is this product for?

**Decision:** Single user — the Product Owner (Mapla). No authentication, no multi-user session isolation, no shared deployment.

**Rationale:**
- The investment philosophy is deeply personal — it reflects one investor's values, risk tolerance, and investment goals
- Multi-user support would require authentication, data isolation, and usage limits — significant infrastructure for no user benefit in the MVP
- The product is a personal investment tool, not a SaaS product

**Consequence:** Any deployment beyond personal use would be a new product with different requirements.

---

## PD-002 — Investment philosophy is fixed for the duration of the MVP

**Status:** DECIDED  
**Context:** Can the gates, thresholds, or decision philosophy be changed during a phase?

**Decision:** No. The investment philosophy documented in `config/investment_philosophy.md`, the gate logic, and the decision philosophy can only be changed by an explicit PO decision recorded as a new product decision.

**Rationale:**
- The philosophy represents considered investment principles, not implementation choices
- Changing the philosophy mid-phase would make test results and phase history uninterpretable
- The sunk-cost protection, privacy constraints, and quality-before-price ordering are especially important to preserve

**Standing constraints (from Phase 10.6 specification):**
- "Do not change Phase 7 decision philosophy or weaken any existing gates"
- "Do not change valuation formulas, weights, gates, decision logic, or financial calculations"

---

## PD-003 — Canadian market is the primary market; US and India are secondary

**Status:** DECIDED  
**Context:** Which markets should the MVP cover?

**Decision:** Canada (TSX) is the primary market with 23 of 33 tickers. US (NYSE/NASDAQ) has 5 tickers. India (NSE) has 3 tickers. ETFs (gold) are supported but treated separately.

**Rationale:**
- Reflects the investor's actual portfolio and market focus
- Canadian markets have the most existing positions to monitor
- US large-caps (MSFT, AMZN, ASML, GOOG, TSM) represent key holdings
- Indian market (ITC.NS, TATASTEEL.NS, KTKBANK.NS) represents existing Indian positions

---

## PD-004 — Gradual accumulation strategy; no single-point-of-entry

**Status:** DECIDED  
**Context:** Should the system recommend full position sizing in one go?

**Decision:** No. The philosophy is gradual accumulation — START_SMALL first, then ACCUMULATE as conviction grows. No single-entry-point recommendations.

**Rationale:**
- Reduces timing risk (buying in at a single price)
- Allows the investor to observe company behaviour over time before committing more capital
- Aligned with the documented investment philosophy

---

## PD-005 — Cache-based demo; no synthetic or fabricated data

**Status:** DECIDED (Phase 10.5)  
**Context:** For demonstration without live data, should the system use fabricated/synthetic data?

**Decision:** No. Demo mode is simply an analysis run on cached real data. There is no synthetic data path.

**Rationale:**
- Fabricated data undermines the integrity of the analysis
- Cached real data is more interesting and more honest — it shows what the system actually produces on real companies
- The pre-warm script makes this practical

---

## PD-006 — Friendly error messages; never expose technical strings to the UI

**Status:** DECIDED (Phase 10.5 UX polish)  
**Context:** When a technical failure occurs (e.g., Yahoo Finance rate limit), what should the user see?

**Decision:** User-facing messages must:
- Be in plain language
- Explain what happened in terms of the user's experience ("live data could not be retrieved")
- Include an actionable suggestion ("try again later, or select a ticker with cached data")
- Never include: exception class names, Python error strings, HTTP status codes, library names (yfinance), internal error codes (CANNOT_COMPLETE_LIVE_ANALYSIS)

**Rationale:**
- Technical strings erode trust and confuse non-technical users
- A clear, actionable message is more helpful than a stack trace
- The raw error is preserved in logs for debugging — not lost, just hidden from the UI

---

## PD-007 — Phase structure: documentation must not modify code

**Status:** DECIDED (Phase 10.6)  
**Context:** When documentation reveals a bug or improvement opportunity, should the documentation phase address it?

**Decision:** No. Documentation phases are strictly documentation-only. Any bugs or improvements discovered during documentation are recorded as technical debt or product backlog items, not fixed in place.

**Rationale:**
- Mixed phases (doc + code) are harder to track and review
- A code change during a documentation phase can introduce regressions without proper testing
- The Phase 10.6 specification is explicit: "This phase is DOCUMENTATION ONLY. Do NOT modify production code."

---

## PD-008 — No Git commits during automated sessions

**Status:** DECIDED  
**Context:** Should automated sessions commit work to Git?

**Decision:** No Git commits during automated development sessions. The Product Owner reviews and commits manually.

**Rationale:**
- The PO should review changes before they are permanently recorded
- Automated commits to a shared history without review could introduce unwanted changes
- Manual commit preserves PO control over the project's Git history

---

## Open decisions

### OPD-001 — Phase 11 scope

**Status:** OPEN  
**Question:** What should Phase 11 focus on?

**Options:** See `docs/product/product-backlog.md` for 16 candidate items.

**PO action required:** Review the backlog, identify the highest-value problem, write a Phase 11 brief.

---

### OPD-002 — Decision history architecture

**Status:** OPEN  
**Question:** If decision history is prioritised (Backlog B1), should it use JSON files (consistent with cache), SQLite, or something else?

**Considerations:** JSON is consistent with current architecture but lacks query capability. SQLite adds querying but adds a dependency. A simple "one JSON per analysis session" approach may be sufficient for a single-user tool.
