# Known Limitations

> **Purpose:** Honest inventory of what the system cannot do or does imperfectly  
> **Status:** Current as of Phase 10.6  
> **Note:** Limitations that are risks are also in `docs/governance/assumptions-risks-dependencies.md`

---

## L1 — yfinance field availability varies by ticker

**What it means:** Not all tickers return the same set of fields from Yahoo Finance. A field that exists for MSFT may not exist for KTKBANK.NS. A field that exists today may not exist after a yfinance update.

**Impact:** Gaps are reported in `data_quality_notes`. The analysis proceeds with reduced confidence. Some valuation methods may be inapplicable for a given ticker.

**Status:** Managed by the normalizer's defensive field access and the `data_quality_notes` mechanism. No fix is possible without a different data source.

---

## L2 — Continuing-operations NI not always available

**What it means:** When yfinance does not provide a separate continuing-operations net income field, the normalizer falls back to total NI for EPS calculation. Total NI can be inflated by discontinued-operations gains, demerger proceeds, or one-time asset sales.

**Impact:** Normalised EPS may be overstated if a large one-time gain occurred in the normalisation window. For ITC.NS FY2025, the one-time demerger gain was ₹150.16B — using total NI would have overstated normalised EPS by ~76%.

**Current behaviour:** The normalizer attempts multiple yfinance field names before falling back. The source used is documented in `eps_provenance` in `data_quality_notes`.

**Visibility:** The UI shows which NI source was used. A prominent warning when total NI is used (rather than continuing-ops) is a PROPOSED improvement (Product Backlog B3).

---

## L3 — DCF not applicable to financial institutions

**What it means:** Banks and insurance companies are excluded from DCF valuation because cash flow is both an input to and output of their core business (lending). Applying a standard FCF-based DCF to a bank produces meaningless results.

**Impact:** For the 8 financial institution tickers in the MVP universe (TD.TO, CM.TO, BNS.TO, MFC.TO, BN.TO, BAM.TO, FFH.TO, EQB.TO), DCF is excluded. Valuation relies on P/E and EV/EBITDA.

**No financial-institution-specific method (P/BV, ROE-to-COE):** This is a known gap. Product Backlog B16 proposes adding one.

---

## L4 — Peer valuation not automated

**What it means:** The `PeerData` model exists in the codebase, and peer valuation is architecturally supported, but no peer data is automatically fetched. Peer comparison requires manual input.

**Impact:** Peer-relative valuation is not currently used in the synthesized fair value. Multiples valuation relies on absolute multiples rather than peer-relative multiples.

**Current state:** The valuation config notes that peer comparison should use "relevant industry peers only — not simply companies in the same broad sector." Given the difficulty of defining appropriate peer sets automatically, peer valuation remains manual.

---

## L5 — No decision history

**What it means:** Each analysis is independent. The system cannot compare today's analysis to a previous analysis for the same ticker. There is no way to see whether the recommendation has changed since last month.

**Impact:** Thesis tracking must be done manually by the user. The journal and thesis templates (`journal/TEMPLATE_journal_entry.json`, `portfolio/thesis/TEMPLATE_thesis.json`) exist but are not integrated.

**Priority:** Product Backlog B1 (high priority).

---

## L6 — Session state is per-browser-tab and not persistent

**What it means:** Streamlit's `st.session_state` is in-memory and bound to the browser tab's Streamlit connection. Closing the tab, refreshing the browser, or restarting the Streamlit server clears all session state.

**Impact:** A mid-session browser refresh loses the current analysis and conversation history. The user must re-run the analysis.

**No workaround:** This is a Streamlit architectural limitation. Persistent sessions would require a server-side session store (Product Backlog B12).

---

## L7 — Cache expires and must be manually refreshed

**What it means:** Cache TTLs are 24h (info, history) and 48h (financials). After a TTL expires, the next analysis attempt will try a live fetch. If Yahoo Finance is rate-limiting at that moment, the analysis will fail.

**Impact:** For a regularly-used demo or analysis session, the pre-warm script must be re-run periodically. This is a manual step.

**Partial mitigation:** The Force Refresh checkbox allows refreshing on demand. A scheduled cache refresh is proposed in Product Backlog B13.

---

## L8 — FCF reconciliation is partial

**What it means:** The FCF-vs-EPS reconciliation renderer can show OCF and capex (both available from yfinance) but cannot fully decompose the gap into D&A, working capital changes, and taxes — because these are not separately persisted in the normalizer.

**Impact:** The gap explanation in the rendered report says "items not separately tracked include: D&A, changes in working capital, deferred taxes." This is honest but incomplete.

**Future improvement:** Product Backlog B4 proposes adding these fields to the normalizer.

---

## L9 — D&A and working capital changes not tracked separately

**What it means:** The normalizer does not persist depreciation/amortisation or working capital changes as separate fields. They are available in the raw yfinance cash flow statement data but are not extracted.

**Impact:** As noted in L8, FCF reconciliation is incomplete. Also, EBITDA adjustments for D&A may be less precise.

---

## L10 — Streamlit UI has no automated tests

**What it means:** `ui/app.py` and `ui/data_status.py` have no automated tests. A rendering bug or a broken widget would not be caught by the existing test suite.

**Impact:** UI regressions require manual verification after each change to `app.py`.

**Proposed fix:** Product Backlog B14 (Playwright smoke test).

---

## L11 — yfinance data accuracy is not guaranteed

**What it means:** Yahoo Finance data occasionally has errors: wrong currency labelling, incorrect period dates, zero values where non-zero data should exist, mismatched fiscal year boundaries.

**Impact:** The normalizer does basic sanity checks (e.g., reject zero revenue) but cannot catch all Yahoo Finance data errors. A data error that passes sanity checks will produce an incorrect analysis.

**Current mitigation:** The ITC.NS baseline (Phase 9.9b) provides one verified reference point. Other tickers have been informally reviewed but not formally baselined.

---

## L12 — No multi-user support

**What it means:** The system is designed for a single user (the Product Owner). There is no authentication, no user isolation, no concurrent-session support.

**Impact:** If deployed to a web server accessible by multiple users, all users would share the same cache and session state. This would be a privacy and data integrity failure.

**Status:** This is a deliberate design boundary. The system is explicitly not designed for multi-user deployment.
