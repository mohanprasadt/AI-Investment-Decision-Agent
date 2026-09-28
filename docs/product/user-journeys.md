# User Journeys

> **Status:** Journeys 1–9 are IMPLEMENTED. Journey 10 (decision history) is NOT IMPLEMENTED.  
> **User:** Single investor (Product Owner)

---

## Journey 1 — Select and analyse a ticker

**User intent:** Analyse a company from the MVP universe.

**Entry point:** Streamlit UI → ticker dropdown → select ticker → click Analyse.

**System behaviour:**
1. Check data status (cache freshness shown in collapsible card before analysis)
2. Fetch data from cache if fresh, otherwise live from Yahoo Finance
3. Run full 8-step pipeline (data → quality → research → valuation → portfolio → gates → decision → render)
4. Display rendered decision with reasoning

**Expected output:** Full investment decision with action (e.g., WATCH, ACCUMULATE), fair value range, gate summary, quality tier, valuation zone, confidence, and supporting evidence.

**Failure scenarios:**
- Yahoo Finance rate-limited: friendly message shown; no technical error exposed
- Ticker has no data: clear "data could not be retrieved" message
- No Claude API key: analysis completes but produces `WAIT_INSUFFICIENT_EVIDENCE` (correct output)

**Acceptance criteria:** Decision displayed within 60 seconds for a cached ticker. Decision includes action, reasoning, and valuation range.

**Current status:** ✅ IMPLEMENTED

---

## Journey 2 — Ask a follow-up question after analysis

**User intent:** Understand a specific aspect of the completed analysis without re-running it.

**Entry point:** Chat panel below the analysis result → type a question → press Enter.

**Example questions:**
- "Why did you recommend WATCH?"
- "What's the valuation?"
- "What are the main risks?"
- "What's the moat assessment?"

**System behaviour:**
1. Classify intent as `FOLLOW_UP`
2. Route to `InvestmentAgent.chat()` which uses the existing `InvestmentDecisionAssessment` in session state
3. Render a focused answer from the stored assessment — no new Yahoo Finance calls
4. Display in chat panel

**Expected output:** Focused natural-language answer drawn from the analysis already completed.

**Failure scenarios:**
- No active analysis in session: system asks user to run an analysis first
- Question not recognisable: system asks for clarification

**Acceptance criteria:** Follow-up answer is consistent with the analysis. No new data is fetched for follow-ups.

**Current status:** ✅ IMPLEMENTED

---

## Journey 3 — Ask why the decision was reached

**User intent:** Understand the decision rationale at a gate level.

**Example questions:**
- "Why did you give WATCH rather than ACCUMULATE?"
- "What stopped you from recommending a buy?"
- "Explain the decision"

**System behaviour:** Renders the gate-by-gate reasoning — which gates passed, which limited the decision, what evidence was considered.

**Expected output:** Gate-by-gate explanation — e.g., "Gate 1 passed (business understood), Gate 2 produced WATCH tier (quality adequate but not exceptional), Gate 3 showed price above base fair value → WATCH action."

**Current status:** ✅ IMPLEMENTED

---

## Journey 4 — Ask about valuation

**User intent:** Understand the fair value estimates.

**Example questions:**
- "What's the fair value?"
- "Walk me through the valuation"
- "What does DCF say?"
- "Is the stock expensive?"

**System behaviour:** Renders the valuation assessment — all four methods (DCF, P/E, EV/EBITDA, P/FCF), their bear/base/bull ranges, weights, and the weighted synthesis.

**Expected output:** Table or summary of valuation methods, fair value range, current price vs fair value, valuation zone (START_SMALL / ACCUMULATE / WATCH / WAIT).

**Current status:** ✅ IMPLEMENTED

---

## Journey 5 — Ask about FCF vs EPS reconciliation

**User intent:** Understand why FCF and EPS differ and whether the gap is explainable.

**Example questions:**
- "Why is FCF so different from EPS?"
- "Walk me through the FCF reconciliation"
- "Are EPS and FCF from the same period?"

**System behaviour:** Renders the period-alignment analysis — shows whether EPS and FCF use the same fiscal-year window, highlights any mismatch, explains available components (OCF, capex) and unavailable ones (D&A, working capital when not separately stored).

**Expected output:** Period alignment status (✓ SAME-PERIOD BASIS or ⚠ PERIOD MISMATCH), numerical reconciliation of the gap using available data, honest list of unavailable items.

**Current status:** ✅ IMPLEMENTED (Phase 9.9b)

---

## Journey 6 — Ask about risks

**User intent:** Understand what could go wrong with this investment.

**Example questions:**
- "What are the risks?"
- "What's the bear case?"
- "What would break the investment thesis?"

**System behaviour:** Renders the adversarial assessment — thesis breakers, their severity (LOW/MODERATE/HIGH/SEVERE), and the bull/bear case balance.

**Expected output:** List of identified risks with severity, thesis breakers, and the bear case narrative.

**Current status:** ✅ IMPLEMENTED

---

## Journey 7 — Ask what would change the decision

**User intent:** Understand the conditions under which the recommendation would improve or worsen.

**Example questions:**
- "What price would make this a buy?"
- "What would need to change for ACCUMULATE?"
- "If FCF grows 10%, what happens?"

**System behaviour:** Routes to SCENARIO_WHAT_IF intent handler. Generates a qualitative or quantitative scenario answer from the assessment.

**Expected output:** Scenario-based response — e.g., "The current WATCH rating would likely shift to ACCUMULATE if the price fell below the bear fair value of [X], assuming the thesis remains intact."

**Current status:** ✅ IMPLEMENTED (basic scenario handling)

---

## Journey 8 — Cold ticker / uncached data

**User intent:** Analyse a ticker with no local cache.

**Entry point:** Select ticker → data status shows ⬜ Not cached → click Analyse.

**System behaviour:**
1. Data status card warns: "No cached data found. Analysis will fetch live data..."
2. User clicks Analyse
3. Live fetch from Yahoo Finance (15–60 seconds typical)
4. If successful: analysis proceeds normally
5. If rate-limited: friendly error message shown

**Expected output for success:** Normal analysis output.
**Expected output for rate limit:** "Live data could not be retrieved for [TICKER] because market data sources are temporarily limiting requests. This ticker does not currently have usable cached data, so the analysis cannot proceed right now. Please try again later, or select a ticker with cached data."

**Acceptance criteria:** User understands what happened without seeing any technical error text.

**Current status:** ✅ IMPLEMENTED

---

## Journey 9 — Force Refresh

**User intent:** Get fresh data even if a cache exists (e.g., after earnings release).

**Entry point:** Tick the "Force refresh" checkbox → click Analyse.

**System behaviour:**
1. `force_refresh=True` is passed through `pipeline.py` → `load_ticker()` → `_default_fetch()` → `fetch_ticker()`
2. Cache is bypassed; live data is fetched
3. Cache is updated with fresh data
4. Analysis proceeds with fresh data

**Expected output:** Analysis runs with fresh Yahoo Finance data.

**Failure scenarios:** If Yahoo Finance rate-limits the refresh, the user sees the friendly rate-limit message.

**Current status:** ✅ IMPLEMENTED (fixed in Phase 10.5 — was silently broken before)

---

## Journey 10 — Compare current analysis to prior analysis

**User intent:** See how the recommendation has changed since the last time this ticker was analysed.

**Entry point:** (No entry point exists)

**Current status:** ❌ NOT IMPLEMENTED

**What exists:** `journal/TEMPLATE_journal_entry.json` and `portfolio/thesis/TEMPLATE_thesis.json` are templates but are not integrated into the system.

**What would be needed:** Decision persistence, a comparison renderer, and a UI component for historical view.

**PO note:** This is likely a Phase 11+ candidate. Assess whether the value justifies the effort.

---

## Journey 11 — Custom ticker

**User intent:** Analyse a company not in the 33-ticker MVP universe.

**Entry point:** Ticker dropdown → select "✏️ Custom ticker…" → type any ticker symbol → click Analyse.

**System behaviour:** Identical to Journey 1. The custom ticker is treated the same as any MVP ticker — fetch from Yahoo Finance, full pipeline, same gates.

**Expected output:** Normal analysis output if data is available.

**Failure scenarios:** Unknown ticker → clear error message.

**Current status:** ✅ IMPLEMENTED
