# Financial Quality Logic

> **Status:** IMPLEMENTED (Phase 3)  
> **Thresholds:** `config/thresholds.yaml`  
> **CRITICAL:** Thresholds are guidelines, not absolute pass/fail rules. Context always overrides a raw number.

---

## Purpose

Financial quality assessment answers: "Is this a quality business by objective financial measures?" before any valuation is considered.

Quality is the primary filter in the investment philosophy. A company with poor financial quality will be capped at WATCH or CONCERN regardless of how attractive the valuation looks. A cheap company with deteriorating fundamentals is a value trap.

---

## The dimensions evaluated

The `quality_engine.py` evaluates seven dimensions of financial quality. Each dimension contributes to the overall `QualityTier`.

### 1 — Return on Invested Capital (ROIC)

**Why it matters:** ROIC measures how efficiently a company uses the capital invested in it. A consistently high ROIC (above the cost of capital) is the clearest financial evidence of a competitive moat.

**Thresholds (guidelines):**
| ROIC | Classification |
|------|---------------|
| ≥ 15% consistently | Excellent |
| 10–15% | Strong |
| 7–10% | Watch |
| < 7% persistently | Concern |

**Context note:** Emerging companies may have lower current ROIC if the trajectory is strongly improving and the underlying economics are compelling. Persistent high ROIC can support the existence of a moat but does not prove it.

---

### 2 — Revenue Growth

**Why it matters:** Sustained revenue growth demonstrates market relevance, pricing power, and expanding opportunity.

**Thresholds:**
| 5-year CAGR | Classification |
|------------|---------------|
| ≥ 15% | Excellent |
| ≥ 10% | Strong |
| ≥ 5% | Preferred minimum |
| Volatile or negative | Flag for investigation |

**Context note:** Consistent, sustainable growth is preferred over volatile high-average growth. The trajectory and consistency matter as much as the level.

---

### 3 — Margins (Gross, Operating, FCF)

**Why they matter:** Margins reflect pricing power, cost discipline, and competitive position.

**Thresholds (industry-context-dependent):**
| Margin | Guideline |
|--------|----------|
| Gross margin ≥ 40% | Strong (varies enormously by industry) |
| Operating margin ≥ 15% | Good |
| Operating margin < 5% | Watch |
| FCF margin ≥ 10% | Good |

**Context note:** Margin levels must be evaluated relative to the company's industry. Retail has naturally thin margins; software naturally high. Focus on level, consistency, trend, and peer comparison.

---

### 4 — FCF Conversion (Quality of Earnings)

**Why it matters:** Free cash flow conversion measures whether reported earnings translate into actual cash. A company that reports high earnings but generates little FCF may be using aggressive accounting.

**What is evaluated:** OCF-to-net-income ratio; FCF-to-net-income ratio; trend in the gap between reported earnings and FCF.

**Red flag:** Persistently high earnings with low or negative FCF — possible working capital expansion, aggressive revenue recognition, or capitalised expenses.

---

### 5 — Balance Sheet / Debt

**Why it matters:** Excessive debt increases risk, reduces financial flexibility, and can amplify losses in downturns.

**Thresholds:**
| Debt/Assets | Classification |
|-------------|---------------|
| 0–20% | Preferred |
| 20–40% | Generally acceptable |
| 40–60% | Investigate carefully |
| > 60% | High leverage concern |

**Context note:** These thresholds MUST be interpreted in industry context. Banks and insurance companies operate with very different leverage norms than software or consumer companies. Measure interest-bearing debt only — accounts payable is not borrowing.

**Also evaluated:** Interest coverage ratio, FCF-to-debt ratio, debt trend direction.

---

### 6 — Dividend Quality

**Why it matters:** For income positions, dividend sustainability matters. A high dividend that gets cut is doubly harmful — the income disappears and the share price typically falls.

**Thresholds:**
| Payout ratio | Classification |
|-------------|---------------|
| < 50% | Strong cushion |
| 50–70% | Preferred range |
| 70–85% | Caution |
| 85–100% | Sustainability concern |
| ≥ 100% | Significant concern |

**FCF payout:** Also evaluated against FCF (not just earnings). FCF payout preferred below 75%.

**High yield investigation:** A yield ≥ 6% requires investigation — it may reflect a falling share price (business deterioration), a high payout ratio, or a genuinely attractive yield in a quality business.

---

### 7 — Earnings Quality

**Why it matters:** Reported earnings can be manipulated or distorted by accounting choices. High earnings quality means earnings are predictable, cash-backed, and free from one-time items.

**What is evaluated:**
- Consistency of earnings over time
- Proportion of earnings backed by FCF
- Presence of material one-time items
- Use of continuing-operations NI vs total NI (Phase 9.9b)

---

## QualityTier — the overall classification

After evaluating all dimensions, the quality engine produces an overall `QualityTier`:

| Tier | Meaning | Impact on decision |
|------|---------|-------------------|
| EXCELLENT | Exceptional across most dimensions | No constraint on action |
| STRONG | Strong across most dimensions | No constraint on action |
| GOOD | Solid but not exceptional | No constraint on action |
| WATCH | Adequate but notable concerns | **Caps final action at WATCH** |
| CONCERN | Material quality weaknesses | **Caps at WATCH; may produce REDUCE** |

The WATCH/CONCERN cap is an important constraint: even if the valuation is very attractive (Gate 3 says ACCUMULATE), a WATCH quality tier means the final recommendation is WATCH. Quality must be established before price is considered.

---

## Empty data handling (tested and verified)

If financial data is empty or unavailable (e.g., yfinance returned no financials), the quality engine produces `WATCH` tier — not EXCELLENT. This prevents an empty-data analysis from producing a positive recommendation.

**Verified by:** `test_phase105.py` — `test_gate2_evaluate_with_empty_metrics_stays_watch` confirms that an empty `FinancialQualityAssessment` with no data available produces at most a WATCH tier decision.

---

## Thresholds are guidelines, not rules

This is stated explicitly in `config/thresholds.yaml`:

> "All thresholds are GUIDELINES, not absolute pass/fail rules. The agent must interpret these in context of: industry norms, business model, emerging vs. mature company stage, trajectory of the metric, not just current level."

This means:
- A bank with 70% debt/assets should not be flagged as "high leverage concern" by the same threshold as a software company
- An emerging company with 8% ROIC but strongly improving trajectory may not be a WATCH-tier concern
- The Claude API (in Gate 1/4 research) is responsible for applying this contextual judgement — the thresholds are inputs to that judgement, not overrides

---

## Configuration

All thresholds are in `config/thresholds.yaml`. Changes to this file affect quality assessment outcomes but do not require code changes. However, threshold changes should be treated as PO-level decisions and documented.
