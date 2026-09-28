# Current State — Where We Are Now

> **As of:** Phase 10.6 inspection, August 2026  
> **Answer to:** "If I open the project today, what do I actually have?"

---

## What you have

### The Streamlit UI (`run_ui.py`)

Run it with:
```
streamlit run run_ui.py
```

You get a web-based interface with:
- **Ticker selector:** Searchable dropdown of 33 MVP tickers (format: `TICKER — Company Name`) plus a "✏️ Custom ticker…" option for anything outside the 33
- **Portfolio weight input:** Optional weight % for existing position context
- **New position checkbox:** Treats analysis as a fresh position regardless of weight
- **Analyse button:** Triggers the full pipeline
- **Force Refresh checkbox:** Forces a fresh fetch even if cached data exists (now working correctly)
- **Data status panel:** Collapsible card showing cache freshness (info, financials, history) for the selected ticker before analysis runs
- **Analysis output:** Full rendered decision with reasoning trace
- **Chat panel:** Follow-up questions in natural language

### The analysis pipeline (what happens when you click Analyse)

```
1. Fetch financial data (from cache, or live from Yahoo Finance)
2. Normalise raw data → CompanyFinancialMetrics
3. Assess financial quality → FinancialQualityAssessment
4. Business research via Claude API (or quantitative fallback)
5. Build valuation inputs → ValuationInput
6. Run four valuation methods → ValuationAssessment
7. Apply portfolio context (if weight provided)
8. Run five decision gates → InvestmentDecisionAssessment
9. Render decision as human-readable report
10. Display in UI + enable follow-up Q&A
```

### The decision engine

Produces one of 8 actions:
- `START_SMALL` — Attractive entry, some uncertainty
- `ACCUMULATE` — Attractive valuation, intact thesis
- `WATCH` — Quality company, valuation not compelling
- `HOLD` — Existing position, thesis intact
- `REDUCE` — Thesis weakened
- `EXIT` — Thesis broken
- `WAIT_INSUFFICIENT_EVIDENCE` — Gate 1 or data failure
- `WATCH_PENDING_DATA` — Price unknown/stale

### The conversational layer

After an analysis runs, you can ask follow-up questions without re-running the analysis:
- "Why did you recommend WATCH?"
- "What's the valuation?"
- "What are the main risks?"
- "Walk me through the FCF vs EPS"
- "What would change the decision?"
- "What's the bull case?"

These work because the full `InvestmentDecisionAssessment` object is held in session state.

---

## Supported ticker universe

**33 pre-approved tickers in `data/mvp_tickers.py`:**

| Market | Count | Examples |
|--------|-------|---------|
| Canada — Energy | 7 | ENB.TO, SU.TO, CNQ.TO, TOU.TO, TPZ.TO, ARX.TO, PPL.TO |
| Canada — Financials | 8 | TD.TO, CM.TO, BNS.TO, MFC.TO, BN.TO, BAM.TO, FFH.TO, EQB.TO |
| Canada — Utilities | 2 | FTS.TO, CPX.TO |
| Canada — Consumer | 3 | ATD.TO, NWC.TO, DOL.TO |
| Canada — Real Estate | 1 | REI.UN.TO |
| Canada — Telecom | 1 | T.TO |
| Canada — Technology | 1 | CSU.TO |
| Canada — Other | 1 | ABXX.TO |
| USA | 5 | AMZN, MSFT, ASML, GOOG, TSM |
| India | 3 | ITC.NS, TATASTEEL.NS, KTKBANK.NS |

Plus: custom ticker input for any other ticker.

---

## Cache status (as of Phase 10.6 inspection)

The pre-warm script has been run. Cache is nearly complete:

| Status | Count |
|--------|-------|
| ✅ Ready (all 3 files fresh) | 32 of 33 |
| ⚠️ Partial | 1 of 33 |
| ⬜ Empty | 0 of 33 |

Cache files expire: info after 24h, financials after 48h, history after 24h. Run `scripts/prewarm_mvp.py` to refresh.

---

## Testing state

| Category | Result |
|----------|--------|
| Total tests | 1,228 passed, 1 skipped |
| Collection errors | 3 (pre-existing — legacy helper naming conflict in 3 test files) |
| Pre-existing failures | 5 (test_phase93b — network-dependent, sandbox-only) |
| New failures introduced | 0 |
| Phase 10.5 tests | 43 passed |
| Phase 10 conversation tests | 64 passed |
| Fetcher reliability tests | 50 passed |

The 3 collection errors and 5 failures are pre-existing and do not indicate regressions.

---

## External dependencies

| Dependency | Required | Without it |
|------------|----------|-----------|
| Internet connection | For live data only | Can use cached data |
| Yahoo Finance (yfinance) | For all live data | Analysis fails with friendly error |
| Anthropic Claude API key | For qualitative research | Falls back to WAIT_INSUFFICIENT_EVIDENCE |
| Python 3.10+ | Always | Won't run |
| Streamlit | For UI | CLI still works via run_agent.py |

---

## Known limitations (current)

1. **yfinance field availability varies by ticker and version.** Some tickers return fewer fields. Gaps are reported honestly in `data_quality_notes`.

2. **Continuing-operations NI not always available.** When yfinance doesn't provide a continuing-ops field, the pipeline falls back to total net income. This is logged and visible in the EPS provenance note.

3. **DCF not applicable to financial institutions.** Banks and insurance companies are excluded from DCF (this is intentional — DCF doesn't work well for financial institutions).

4. **Peer valuation not automated.** The peer comparison method requires manual `PeerData` input. It is not populated by yfinance.

5. **No decision history.** The system cannot compare today's analysis to a prior analysis for the same ticker. Each run is independent.

6. **Session state is per-browser-tab.** Streamlit's `st.session_state` is not persistent. Closing the tab or restarting the app clears the conversation.

7. **Pre-warm must be re-run as cache expires.** Cache TTLs are 24–48 hours. For regular use, cache must be refreshed periodically.

---

## Immediate next milestone

**Phase 11 — To be defined by Product Owner.**

Before Phase 11 starts, the Product Owner should:
1. Review the [Product Backlog](product-backlog.md)
2. Decide which problem is most valuable to solve next
3. Write a one-paragraph Phase 11 brief: problem, desired outcome, scope boundaries
4. Agree acceptance criteria before any code is written

---

## Current product maturity

**FUNCTIONAL MVP** — not a prototype, not production-grade.

This means:
- The core capability works end-to-end for the 33 MVP tickers
- The decision engine has been validated against real tickers (ITC.NS, TD.TO and others)
- The test suite provides meaningful regression coverage
- The system can be used for real investment analysis today — with awareness of its limitations
- It is not suitable for deployment to multiple users without architectural changes (no auth, no multi-session persistence, single-user philosophy)
- It depends on a free, unofficial API (yfinance) that has no service-level guarantees

**Confidence level: MEDIUM-HIGH** for its intended single-user purpose. **LOW** for any broader deployment.
