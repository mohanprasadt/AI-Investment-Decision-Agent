# Portfolio Context Logic

> **Status:** IMPLEMENTED (Phase 6)  
> **Privacy constraint:** Portfolio weight (%) is the ONLY portfolio input. Shares, cost basis, and account value are never requested, stored, or used.

---

## What portfolio context does

The portfolio context layer answers: "Given my existing position, what size action makes sense?"

The decision action (WATCH, ACCUMULATE, etc.) comes from the quality and valuation gates. Portfolio context only affects the sizing and framing of that action — it does not change the action itself (except in cases of extreme concentration).

---

## The only input: portfolio_weight_pct

The system accepts a single portfolio input:

```
portfolio_weight_pct: float | None
```

- `None`: No existing position (new position analysis)
- `0.0`: Zero weight (position recently closed)
- `4.5`: 4.5% of portfolio in this holding

**What is NOT accepted:**
- Number of shares
- Average cost / cost basis
- Total portfolio value
- Unrealised profit or loss

This constraint is enforced at every layer: `ConversationSession`, `ConversationManager`, `run_analysis_pipeline()`, and `portfolio_synthesizer.py`.

---

## Why only weight?

### 1 — Portfolio privacy

Sharing account size and position details is a privacy risk. A percentage conveys the same information needed for portfolio fit assessment without revealing total wealth.

### 2 — Sunk-cost protection

Average cost is excluded because it is irrelevant to forward-looking investment decisions. The sunk-cost fallacy is one of the most common investor mistakes:

- "I can't sell at a loss" — but the loss is real whether or not you sell
- "I should hold until it recovers" — but this assumes it will recover, independent of current analysis
- "I should buy more to lower my average" — but this is only rational if the forward investment case is sound

The system is designed to evaluate the investment case from today's price forward. What you paid previously has no bearing on this analysis.

---

## How portfolio weight is used

### New position (weight = None)

No existing position context. Gate 4 evaluates the position as an initiation:
- A small allocation is appropriate to start (reduces single-entry-point risk)
- The action range is fully open (if quality and valuation support it)

### Small existing position (e.g., 1–4%)

Low concentration. Gate 4 supports adding if quality and valuation gates support it. No concentration concern.

### Moderate existing position (e.g., 4–8%)

Meaningful position. Gate 4 notes the existing allocation. May suggest a smaller addition than for a new position.

### Large existing position (e.g., 8–15%)

Significant concentration. Gate 4 applies a more conservative sizing modifier. An ACCUMULATE signal may be downgraded to "add cautiously" or "no further addition until position rebalances."

### Very large existing position (>15%)

High concentration. Gate 4 may recommend reducing the position rather than adding, regardless of the quality and valuation signals. At this concentration level, the risk from further accumulation may outweigh the valuation opportunity.

---

## Concentration analysis

`analytics/portfolio/concentration_analyzer.py` evaluates whether the existing or proposed position represents an undue concentration risk:

- Portfolio concentration by position (percentage of total portfolio)
- Sector concentration (if multiple holdings in same sector — limited without cross-ticker data)
- Incremental concentration scenarios (`incremental_scenarios.py`): "If I add X% more, what does my concentration become?"

---

## What-if scenarios

`analytics/portfolio/incremental_scenarios.py` generates what-if scenarios for the portfolio context:
- "If I add 1% to this position: new weight would be X%"
- "If I add 2%: new weight would be Y%"

These are used in follow-up responses to "what-if" questions in the conversation layer.

---

## What portfolio context does NOT do

- It does NOT change the quality tier (Gate 2)
- It does NOT change the valuation zone (Gate 3)
- It does NOT override an adversarial finding (Gate 5)
- It does NOT use average cost for any calculation
- It does NOT request or accept total portfolio value
- It does NOT compare positions across different tickers (single-ticker analysis only)

---

## Implementation notes

**Module:** `analytics/portfolio/portfolio_synthesizer.py` — builds `PortfolioContext` from `portfolio_weight_pct`

**Privacy enforcement locations:**
- `conversation/session.py` — `ConversationSession` dataclass stores only `portfolio_weight_pct`
- `conversation/manager.py` — docstring: "Only portfolio_weight_pct (float | None) passes through this layer. Shares, average cost, and account value are never requested or stored."
- `analytics/decision/decision_synthesizer.py` — docstring: "Average cost / unrealized P/L from portfolio context is NEVER used in any decision logic."

---

## Future considerations (PROPOSED, not committed)

A multi-ticker portfolio view would allow sector concentration analysis across holdings. This would still require only weight percentages — not shares or account values — but would need cross-ticker session state, which is not currently implemented.
