# Decision Log

> **Purpose:** Chronological record of significant decisions — what was decided, when, why, and what it replaced  
> **Format:** Newest first  
> **Note:** Early phase decisions (Phases 1–8) are RECONSTRUCTED from README, commit messages, and module docstrings

---

## Phase 10.6 — August 2026

### DL-020 — Documentation only; no code changes
**Decided:** Phase 10.6  
**Decision:** Phase 10.6 is strictly documentation. Any bugs or improvements discovered during documentation are recorded as debt or backlog items — not fixed in place.  
**Rationale:** Mixed phases are harder to track and review; code changes during documentation risk untested regressions.

### DL-019 — session.last_error stores friendly message only (not raw error)
**Decided:** Phase 10.5 UX polish (documented in 10.6)  
**Decision:** `session.last_error` is set to the output of `_format_pipeline_error()` — the friendly message. The raw error string goes to `log.warning()` only.  
**What it replaced:** `session.last_error = pipeline_result.error` — raw error string exposed in UI via `st.error(session.last_error)`.  
**Why:** `app.py` renders `session.last_error` directly. The raw string contained `CANNOT_COMPLETE_LIVE_ANALYSIS`, `yfinance`, `429`, and similar strings — all of which the UX policy prohibits in the user-facing UI.

---

## Phase 10.5 — Demo Readiness

### DL-018 — Fail-fast on HTTP 429 in interactive path; retry in prewarm only
**Decided:** Phase 10.5  
**Decision:** No retry in the interactive analysis path. Pre-warm script may retry.  
**Why:** A 30–90s retry hang during interactive use is a poor user experience. Rate limits persist for minutes — immediate retry doesn't help.

### DL-017 — 33-ticker canonical MVP universe
**Decided:** Phase 10.5  
**Decision:** `data/mvp_tickers.py` is the single source of truth for the MVP ticker universe (33 tickers).  
**Why:** Previously tickers were ad-hoc. A canonical list enables pre-warming, the UI dropdown, and controlled testing.

### DL-016 — Cache as demo experience; no synthetic data
**Decided:** Phase 10.5  
**Decision:** Demo mode uses real cached data. No synthetic/fabricated data.  
**Why:** Fabricated data undermines analysis integrity. Pre-warming makes cached real data practical for demos.

### DL-015 — Windows-compatible sequential prewarm (35s delays)
**Decided:** Phase 10.5  
**Decision:** `scripts/prewarm_mvp.py` runs sequentially (not parallel) with 35-second delays between tickers.  
**Why:** Windows multiprocessing restrictions prevent the parallel approach. Sequential with delays avoids rate limiting.

---

## Phase 10.x — Yahoo Finance Reliability

### DL-014 — Failed fetches must not be cached
**Decided:** Phase 10.x  
**Decision:** If a fetch fails or returns empty data, the cache file is NOT written.  
**What it replaced:** Failed fetches were being cached, poisoning subsequent reads with empty data.  
**Why:** An empty cache file served as "valid data" — subsequent analyses silently used bad data.

### DL-013 — fetch_ticker() short-circuit on info failure
**Decided:** Phase 10.x  
**Decision:** If the `info` fetch fails (often the first call), skip financials and history fetches — they will almost certainly also fail.  
**Why:** Saves 3 wasted network calls when the first call indicates rate limiting or unavailability.

---

## Phase 9.9b — EPS/FCF Period Alignment

### DL-012 — Common fiscal-year window for EPS and FCF normalisation
**Decided:** Phase 9.9b  
**Decision:** Normalised EPS and normalised FCF must use the intersection of their available fiscal-year windows.  
**What it replaced:** EPS averaged over years A–C, FCF averaged over years B–D — different windows created an artificial gap.  
**Why:** Comparing EPS and FCF from different periods is methodologically wrong.

### DL-011 — Prefer continuing-operations NI over total NI for EPS normalisation
**Decided:** Phase 9.9b  
**Decision:** The normalizer attempts multiple yfinance field names to find continuing-ops NI; falls back to total NI if unavailable.  
**Why:** Total NI can include large one-time gains (ITC.NS FY2025: ₹150.16B demerger gain overstated total NI by 76% vs continuing-ops).

---

## Phase 9.x — Valuation Hardening

### DL-010 — EV/EBITDA uses broad cash (not narrow cash) for net debt
**Decided:** Phase 9.1  
**Decision:** Use total cash and equivalents for the EV → equity value bridge, not just "narrow" cash.  
**Why:** Initial implementation used an incorrect cash definition that understated equity value.

### DL-009 — FCF normalisation uses multi-year averaging
**Decided:** Phase 9.2  
**Decision:** Normalised FCF is a 3-year average, not a single-year figure.  
**Why:** Single-year FCF is volatile (lumpy capex, working capital swings). A 3-year average is more representative of sustainable FCF.

---

## Phase 7 — Decision Architecture

### DL-008 — Sequential gates, not weighted score
**Decided:** Phase 7  
**Decision:** Decision engine uses 5 sequential gates, not a weighted composite score.  
**Why:** A weighted score allows poor quality to be compensated by cheap price (value trap). Sequential gates enforce the priority order: quality first, then valuation.

### DL-007 — Sunk-cost protection: exclude average cost from all gate logic
**Decided:** Phase 7  
**Decision:** Average cost and unrealised P/L are explicitly excluded from Gate 4 and all other gate logic.  
**Why:** Forward-looking investment decisions must not be influenced by historical purchase price.

### DL-006 — Gate 5 SEVERE override: highest-priority signal
**Decided:** Phase 7  
**Decision:** A SEVERE adversarial risk finding forces REDUCE or EXIT regardless of quality and valuation signals.  
**Why:** A credible, material thesis breaker overrides any other positive signal — no amount of cheap price justifies holding a broken thesis.

---

## Phase 6 — Portfolio Context

### DL-005 — Portfolio weight only; exclude shares, cost, account value
**Decided:** Phase 6  
**Decision:** The only portfolio input is `portfolio_weight_pct` (float | None).  
**Why:** Privacy protection; sunk-cost avoidance; simplicity.

---

## Phase 4 — Business Research

### DL-004 — Quantitative fallback: WAIT_INSUFFICIENT_EVIDENCE when no API key
**Decided:** Phase 4  
**Decision:** If no Anthropic API key is present, Gate 1 fails → WAIT_INSUFFICIENT_EVIDENCE.  
**Why:** Business understanding is a prerequisite. Financial-data-only recommendations would be produced without this understanding — a violation of the investment philosophy.

---

## Phase 1–2 — Data Foundation

### DL-003 — Local JSON cache with TTLs
**Decided:** Phase 1–2 [RECONSTRUCTED]  
**Decision:** Cache fetched data as JSON files with TTL-based expiry.  
**Why:** Avoids repeated network calls; no database infrastructure required; human-readable.

### DL-002 — Never cache failed fetches or empty data
**Decided:** Phase 10.x [retroactive fix for Phase 1–2 design gap]  
**Decision:** Failed fetches must not be cached.  
**Why:** Empty cache files were serving as "valid" data, causing silent bad analysis.

### DL-001 — yfinance as sole data source
**Decided:** Phase 1–2 [RECONSTRUCTED]  
**Decision:** Use yfinance for all financial data.  
**Why:** Free, no API key required for data, adequate coverage for MVP.  
**Trade-off accepted:** No SLA, rate limiting, field instability.
