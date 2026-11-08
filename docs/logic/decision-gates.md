# Decision Gates

> **Status:** IMPLEMENTED (Phase 7). Gate logic and thresholds must not be changed without explicit PO authorisation.  
> **See also:** `config/investment_philosophy.md` (the documented philosophy that these gates enforce)

---

## The gate model

The investment decision is not a weighted score. It is a sequential pipeline of five gates. Each gate asks one question. If a gate fails, it constrains the final action — or stops the pipeline entirely.

**Analogy:** Think of the gates as a checklist a careful investor would work through in order. You would not look at the share price (Gate 3) before deciding whether you understand the business (Gate 1). You would not calculate position size (Gate 4) without first verifying the quality of the business (Gate 2).

**Key rule:** Quality is the primary filter. Valuation is the timing filter. Portfolio context sizes the position. Nothing overrides the quality gate except an adversarial finding.

---

## Gate 1 — Business Understanding

**Question:** Do I understand this business well enough to make an investment decision?

**What it evaluates:** The output of Phase 4 (business research). If no `BusinessResearchAssessment` is present (either because no Anthropic API key was provided, or because the research failed), Gate 1 fails.

**Possible outcomes:**
- **PASS:** Research was completed successfully; the system has a business model understanding, moat assessment, and risk identification.
- **FAIL → `WAIT_INSUFFICIENT_EVIDENCE`:** No research was completed. Pipeline stops. No further gates are evaluated.

**Why this gate exists:** The investment philosophy states that understanding the business is the prerequisite to any other analysis. Valuation without business understanding is price speculation, not investment analysis.

**Implemented in:** `analytics/decision/gate1_understanding.py`

---

## Gate 2 — Financial Quality

**Question:** Is this a quality business by financial measures?

**What it evaluates:** The `FinancialQualityAssessment` from Phase 3. Evaluates ROIC, revenue growth, margins, FCF conversion, balance sheet strength, dividend quality, and earnings quality against configured thresholds.

**QualityTier output:**

| Tier | Meaning | Constraint on final action |
|------|---------|---------------------------|
| EXCELLENT | Exceptional across most dimensions | No constraint — full action range |
| STRONG | Strong across most dimensions | No constraint — full action range |
| GOOD | Solid but not exceptional | No constraint |
| WATCH | Adequate but notable concerns | Caps action at WATCH — cannot produce ACCUMULATE or START_SMALL |
| CONCERN | Material quality weaknesses | Caps action at WATCH or produces REDUCE |

**What a WATCH cap means:** Even if the valuation looks attractive (Gate 3), if the business only passes Gate 2 at WATCH tier, the final action cannot be stronger than WATCH. You do not accumulate into a business with meaningful quality concerns.

**Empty data case:** If financials are empty or unavailable, Gate 2 produces `WATCH` tier — not EXCELLENT. This prevents an empty-data analysis from generating a positive recommendation. This is tested and verified.

**Implemented in:** `analytics/decision/gate2_quality.py`  
**Thresholds in:** `config/thresholds.yaml`

---

## Gate 3 — Valuation

**Question:** Is the current price attractive relative to estimated fair value?

**What it evaluates:** The `ValuationAssessment` from Phase 5. Compares the current price to the weighted fair value synthesis across DCF, Normalized P/E, EV/EBITDA, and P/FCF.

**Accumulation zone output:**

| Zone | Price vs fair value | Action range |
|------|---------------------|-------------|
| WAIT | Materially above fair value | No action |
| WATCH | Business attractive but price not compelling | WATCH |
| START_SMALL | Reasonably attractive entry | START_SMALL |
| ACCUMULATE | Attractive with sufficient margin of safety | ACCUMULATE |

**Interaction with Gate 2:** The final action is the more conservative of (Gate 2 cap, Gate 3 zone). If Gate 2 says WATCH and Gate 3 says ACCUMULATE, the result is WATCH.

**Implemented in:** `analytics/decision/gate3_valuation.py`

---

## Gate 4 — Portfolio Fit

**Question:** Given my existing position, how much of this can I add?

**What it evaluates:** `PortfolioContext` from Phase 6. Uses `portfolio_weight_pct` (the only portfolio input) to assess concentration.

**What it does:**
- If portfolio_weight_pct is None (no existing position): produces a "new position" sizing recommendation
- If portfolio_weight_pct > threshold (high concentration): reduces the recommended position size
- If portfolio_weight_pct is very high: may recommend reducing rather than adding

**What it does NOT do:**
- It does NOT use shares outstanding
- It does NOT use average cost or unrealised P/L (sunk-cost protection)
- It does NOT override the Gate 2 or Gate 3 action

**Sunk-cost protection:** The investment philosophy explicitly states that average cost must not influence investment decisions. Gate 4 enforces this by never accepting or using cost basis information.

**Implemented in:** `analytics/decision/gate4_portfolio.py`

---

## Gate 5 — Adversarial Challenge

**Question:** What could break the investment thesis? Are any thesis breakers credible and severe enough to override the current recommendation?

**What it evaluates:** The adversarial risk section of `BusinessResearchAssessment` (Phase 4). Identifies thesis breakers, evaluates their likelihood and impact, and produces an `AdversarialRisk` level.

**AdversarialRisk levels:**

| Risk level | Meaning | Impact on action |
|------------|---------|-----------------|
| LOW | No credible thesis breakers identified | No constraint |
| MODERATE | Thesis breakers exist but are unlikely or manageable | No action change (confidence noted) |
| HIGH | Significant risks to the thesis; monitoring required | Downgrades Gate 5 confidence by −0.4; does NOT change the action or cap it at WATCH |
| SEVERE | One or more credible, material thesis breakers | Forces REDUCE (existing + WATCH/WAIT) or HOLD (existing + ACCUMULATE/START_SMALL); new positions capped at WATCH |

> **Important:** HIGH does **not** cap the final action at WATCH. Only SEVERE overrides the action. HIGH's only effect is a confidence downgrade in the Gate 5 GateResult (avg confidence − 0.4). This is a common documentation error — the code in `_select_action()` is the source of truth.

**Override rule:** A SEVERE adversarial finding overrides all other gate outputs in `_select_action()`:
- Existing position + WATCH or WAIT starting action → REDUCE
- Existing position + ACCUMULATE or START_SMALL starting action → HOLD
- New position → action capped at WATCH

**Severity thresholds** (computed in `evaluate_gate5()`, unchanged since Phase 7):
```
n_high >= 1               → SEVERE
n_medium_equiv >= 4       → SEVERE
n_medium_equiv >= 2       → HIGH
  OR n_bear >= 6          → HIGH
n_medium_equiv >= 1       → MODERATE
  OR n_bear >= 3          → MODERATE
else                      → LOW
```
where `n_medium_equiv = n_medium + n_unknown` (UNKNOWN is treated conservatively as MEDIUM-equivalent for severity counting only).

**UNKNOWN likelihood treatment:** When the LLM cannot determine likelihood from available evidence, it assigns UNKNOWN. UNKNOWN is deliberately treated as MEDIUM-equivalent in the severity count — a conservative design that prevents underestimating risk from ambiguous data. UNKNOWN is always displayed as UNKNOWN in the UI and Decision Trace; it is never coerced to MEDIUM in output.

**Thesis breaker types (Phase 11B P0-1 distinction):**

| Type | Source | Enters severity calc? | Displayed as |
|------|--------|----------------------|--------------|
| Severity-contributing | LLM bull/bear analysis (`thesis_breaker_details`) + structural risk assessment | Yes — feeds n_high / n_medium_equiv | "Severity-contributing thesis breakers" |
| Monitoring indicator | Generic forward-looking watchlist items (moat erosion, valuation assumption break) added by `extract_thesis_breakers()` | No — tagged `is_monitoring_only=True` | "Monitoring indicators" |

The monitoring indicators (moat erosion, valuation assumption break) are added by `extract_thesis_breakers()` for display purposes only. They are NOT present in `evaluate_gate5()` and therefore do NOT affect the severity or confidence calculation. They appear in the UI as a separate section with an explicit disclaimer.

**Thesis breakers** are specific, identifiable conditions — not generic sector risks. Each thesis breaker specifies what to monitor and what action to take if it materialises.

**Implemented in:** `analytics/decision/gate5_adversarial.py`

---

## Gate interaction summary

```
Gate 1 FAIL     → WAIT_INSUFFICIENT_EVIDENCE (pipeline ends)
Gate 1 PASS     → continue to Gate 2

Gate 2 WATCH/CONCERN  → caps action at WATCH
Gate 2 GOOD+          → full action range available

Gate 3 zone           → START_SMALL / ACCUMULATE / WATCH / WAIT

Final action before Gate 5 = min(Gate 2 cap, Gate 3 zone)

Gate 5 SEVERE   → REDUCE or HOLD (overrides everything; see severity rules above)
Gate 5 HIGH     → confidence downgraded only; action is NOT capped or changed
Gate 5 LOWER    → no change
```

---

## What the 8 decision actions mean

| Action | When produced | Investor interpretation |
|--------|--------------|------------------------|
| `START_SMALL` | GOOD+ quality, attractive price, first position | Initiate a small position; plan to add on weakness |
| `ACCUMULATE` | GOOD+ quality, strong margin of safety, intact thesis | Add meaningfully; valuation is compelling |
| `WATCH` | Quality OK but price not compelling, or WATCH tier quality | No action; monitor for a better entry or quality improvement |
| `HOLD` | Existing position, thesis intact, no strong case to add or reduce | Maintain position; review on next earnings |
| `REDUCE` | Quality deteriorating (CONCERN tier) or SEVERE adversarial risk (existing + WATCH/WAIT action) | Trim position; reassess thesis |
| `EXIT` | SEVERE adversarial risk or CONCERN quality tier | Exit position; thesis is broken |
| `WAIT_INSUFFICIENT_EVIDENCE` | Gate 1 fails (no research) | Cannot proceed; need business research |
| `WATCH_PENDING_DATA` | Price unknown or stale | Action suppressed; refresh data |

---

## What gates cannot be changed without PO authorisation

The Phase 10.6 specification includes this constraint: "Do not change Phase 7 decision philosophy or weaken any existing gates."

This means:
- Gate ordering cannot change (Quality before Valuation before Portfolio)
- The WAIT_INSUFFICIENT_EVIDENCE gate-1 rule cannot be removed
- The safe failure mode (empty data → WATCH, not ACCUMULATE) cannot be weakened
- The sunk-cost exclusion in Gate 4 cannot be removed
- The SEVERE adversarial override in Gate 5 cannot be weakened
