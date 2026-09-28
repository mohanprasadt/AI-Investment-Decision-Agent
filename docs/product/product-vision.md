# Product Vision

> **Status:** IMPLEMENTED (vision) | Ongoing (execution)  
> **Last reviewed:** Phase 10.6

---

## Problem statement

Individual investors who want to analyse equities systematically face a real problem: applying a rigorous, repeatable process is time-consuming and requires holding multiple analytical frameworks in mind simultaneously — financial quality, business understanding, competitive position, valuation, and portfolio fit. Most investors either shortcut the process (relying on gut feel or P/E alone) or abandon rigour under time pressure.

There is no tool aimed at the disciplined individual investor that:
- Applies a complete, philosophy-driven decision framework
- Preserves the investor's privacy (no shares, no cost basis, no account value)
- Produces a transparent, explainable decision — not a black-box score
- Handles multiple markets (Canadian, US, Indian equities)
- Distinguishes "we don't have enough information to decide" from "the answer is no"

---

## Target user

**A single, specific user: the Product Owner (Mapla).**

This is explicitly a personal investment decision-support tool, not a multi-user product. The investment philosophy baked into the system reflects the owner's preferences:
- Long-term investor (not a trader)
- Blended value + growth + dividend approach
- Primary focus: Canadian and US equities
- Occasional Indian equities
- Preference for gradual accumulation over large one-time purchases

> **ASSUMPTION:** The tool is built for one user's philosophy. If the user base ever expanded, the philosophy, thresholds, and decision logic would need to become configurable per-user — a significant architectural change.

---

## Product vision

> *A structured, explainable, and privacy-respecting investment decision-support system that applies a complete, repeatable analytical framework to any supported equity, and surfaces a clear, reasoned recommendation that an individual investor can understand, question, and trust.*

---

## Product mission

Replace gut feel and fragmented analysis with a disciplined, conversational research partner that:
1. Gathers financial facts without fabrication
2. Evaluates business quality against explicit criteria
3. Estimates intrinsic value using multiple independent methods
4. Applies sequential quality and risk gates before reaching a conclusion
5. Explains every conclusion in plain language
6. Never pretends to know more than the data supports

---

## Core value proposition

| Without the agent | With the agent |
|-------------------|----------------|
| Ad hoc analysis, inconsistent methodology | Repeatable, structured process every time |
| Temptation to act on P/E alone | Four valuation methods, weighted and reconciled |
| Forgetting to check business quality before valuation | Five sequential gates — quality before price |
| Blind spots in risk identification | Mandatory adversarial/bear-case challenge |
| Risk of acting on insufficient evidence | `WAIT_INSUFFICIENT_EVIDENCE` is a first-class output |
| Privacy exposure if using portfolio-tracking apps | Portfolio weight only — no shares, no cost |
| Black-box recommendations | Every conclusion is explained with evidence |

---

## What the product intentionally does NOT attempt

These are **deliberate exclusions**, not gaps:

| Excluded | Reason |
|----------|--------|
| Real-time price feeds | Adds complexity, cost, and external dependency for marginal benefit |
| Automated trade execution | Human in the loop is a deliberate safety principle |
| Multi-user support | Single-user philosophy; personalization would break for others |
| Portfolio-level optimization | Position sizing is additive context, not a portfolio optimizer |
| News or event monitoring | Requires continuous data pipeline; out of scope for MVP |
| Peer comparison (auto) | Requires validated peer universe; manual input only |
| Tax considerations | Jurisdiction-specific complexity; out of scope |
| Options or derivatives | Wrong product category |
| Financial advice | Explicitly disclaimed — this is analytical support, not advice |

---

## MVP boundary

The MVP is a **local, single-user, conversational investment analysis tool** that:
- Runs on the investor's own machine
- Works on a controlled universe of 33 tickers
- Produces a structured investment decision via a Streamlit UI
- Supports conversational follow-up questions on a completed analysis
- Does not require any infrastructure beyond a laptop and an internet connection

See [MVP Definition](mvp-definition.md) for the full in/out scope.

---

## Long-term direction (PROPOSED — PO decision required)

The following are potential future directions, **not committed roadmap items**:

| Direction | Description | Status |
|-----------|-------------|--------|
| Expanded ticker universe | More tickers, more markets | PROPOSED |
| Thesis journaling | Capture and track investment theses over time | PROPOSED |
| Decision history | Compare current analysis to prior analysis for same ticker | PROPOSED |
| Portfolio-level view | Aggregate across all holdings | PROPOSED |
| Mobile-friendly UI | Better UX for on-the-go research | DEFERRED |
| Automated monitoring | Alerts when thesis conditions change | DEFERRED |
| Peer comparison | Automatic peer universe for valuation multiples | DEFERRED |

---

## Assumptions behind the vision

1. **yfinance remains free and functional.** The entire data layer depends on a free, unofficial API. If Yahoo Finance restricts or breaks it, the data layer must be replaced. *(Risk — see RAID register)*

2. **The Anthropic Claude API remains available and affordable.** Qualitative research (Phase 4) requires the Claude API. Without it, the system degrades gracefully to `WAIT_INSUFFICIENT_EVIDENCE` for any ticker. *(Known dependency)*

3. **The investment philosophy is stable.** The decision gates, thresholds, and valuation configuration encode a specific investment philosophy. If the philosophy changes, the configuration — and potentially the logic — must change with it.

4. **The user understands the system's limitations.** The agent produces a reasoned recommendation, not a guarantee. The user is expected to review the reasoning and make their own decision.

5. **A local, offline-capable tool is acceptable for MVP.** Future phases may require hosting, but the MVP assumes local execution.

---

## Separation: vision vs current implementation

| Aspect | Vision | Currently implemented |
|--------|--------|----------------------|
| Markets | Canadian, US, Indian | ✅ All three |
| Ticker universe | Flexible | ✅ 33 MVP tickers + custom input |
| Qualitative research | Claude API | ✅ Anthropic researcher + quantitative fallback |
| Conversational UI | Natural language Q&A | ✅ Phase 10 Streamlit UI |
| Decision explanation | Full reasoning trace | ✅ Rendered assessment |
| Multiple valuation methods | 4+ methods | ✅ DCF, P/E, EV/EBITDA, P/FCF |
| Five decision gates | Sequential quality/risk gates | ✅ All five implemented |
| Portfolio privacy | Weight only | ✅ Strictly enforced |
| Pre-warm capability | Cache before demo | ✅ scripts/prewarm_mvp.py |
| Decision history | Track over time | ❌ Not implemented |
| Thesis journaling | Capture thesis | ❌ Template only, not integrated |
| Automated monitoring | Alert on changes | ❌ Not implemented |
