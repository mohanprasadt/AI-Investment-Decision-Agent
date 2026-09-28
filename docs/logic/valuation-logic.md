# Valuation Logic

> **Status:** IMPLEMENTED (Phase 5, hardened through Phase 9.9b)  
> **CRITICAL:** Do not change valuation formulas, weights, or zone definitions without explicit PO authorisation.  
> **Verified baseline:** ITC.NS at Phase 9.9b (see below)

---

## Why four methods?

No single valuation method is reliable in all circumstances. DCF is sensitive to growth assumptions. P/E is meaningless for loss-making companies. EV/EBITDA misses capital intensity differences. P/FCF requires stable FCF.

By running four methods independently and weighting them by reliability, the system produces a range of fair values that reflects genuine uncertainty rather than false precision. When methods converge, confidence is higher. When they diverge, the confidence is lower.

---

## The four valuation methods

### Method 1 — Discounted Cash Flow (DCF)

**What it estimates:** The present value of all future free cash flows, discounted at the company's cost of capital.

**Scenarios:** Bear / Base / Bull — each with different growth rate and margin assumptions.

**Key inputs:**
- Normalised FCF/share (3-year average, same fiscal-year window as EPS)
- Growth rate assumptions (per scenario)
- Discount rate (WACC — default 9%, adjusted by moat strength)

**Discount rate by moat:**
| Moat quality | Rate |
|-------------|------|
| Exceptional moat, low risk | 7.5% |
| Strong moat | 8.5% |
| Moderate moat | 9.5% |
| Weak or no moat | 11.0% |
| High uncertainty | 12.5% |

**Terminal growth rate:** Default 3% (long-run nominal GDP proxy). Capped at 5% — higher rates are not accepted without strong justification.

**Projection period:** 10 years.

**When it does NOT apply:**
- Financial institutions (banks, insurance companies) — DCF does not work well for entities where lending is the core business (cash flows are not the right valuation driver)
- Companies with negative FCF — DCF produces misleading results

**Configuration:** `config/valuation_config.yaml` → `dcf` section  
**Module:** `analytics/valuation/dcf_engine.py`

---

### Method 2 — Normalized P/E

**What it estimates:** Fair value based on normalised earnings per share multiplied by an appropriate P/E multiple.

**Key inputs:**
- Normalised EPS (3-year average, preferring continuing-operations NI over total NI)
- Target P/E multiple (based on growth rate, moat quality, industry)

**Why normalised EPS?** Single-year EPS can be distorted by one-time items (restructuring charges, asset sales, discontinued operations, demerger gains). The 3-year normalised average smooths this out.

**Why continuing-operations NI?** Total net income includes discontinued operations and one-time gains/losses. For a long-term investor, what matters is the earnings power of the ongoing business. ITC.NS FY2025 demonstrated why this matters: total NI was ₹347.47B (including a ₹150.16B demerger gain) but continuing-ops NI was ₹197.31B. Using total NI would have overstated normalised EPS by ~76%.

**Module:** `analytics/valuation/multiples_engine.py`

---

### Method 3 — EV/EBITDA

**What it estimates:** Fair value based on enterprise value relative to earnings before interest, taxes, depreciation, and amortisation.

**Key inputs:**
- EBITDA (trailing or normalised)
- Net debt (to convert EV → equity value)
- Target EV/EBITDA multiple (industry-appropriate)

**Why use it?** EV/EBITDA is useful for capital-intensive businesses where depreciation is large and meaningful. It is also useful for cross-jurisdictional comparisons because it removes the effect of different tax rates.

**Module:** `analytics/valuation/multiples_engine.py`

---

### Method 4 — P/FCF (Price-to-Free-Cash-Flow)

**What it estimates:** Fair value based on free cash flow yield relative to a target multiple.

**Key inputs:**
- Normalised FCF/share (3-year average)
- Target P/FCF multiple

**Why use it?** FCF is harder to manipulate than EPS (which can be affected by accounting choices for depreciation, amortisation, and accruals). For companies with large non-cash charges, FCF is a better indicator of actual cash generation.

**When it's less reliable:** Capital-light businesses with lumpy capex; early-stage companies with negative FCF; companies in heavy investment phases.

**Module:** `analytics/valuation/multiples_engine.py`

---

## Weighted fair value synthesis

After all applicable methods run, their results are combined into a weighted fair value synthesis:

1. Each method is assessed for reliability (`MethodReliability`: HIGH / MEDIUM / LOW / NOT_APPLICABLE)
2. Reliability maps to a weight (higher reliability → higher weight)
3. Weighted average of bear, base, and bull estimates across methods
4. Final output: fair value range (bear–base–bull) with an overall confidence level

**Configuration:** `analytics/valuation/valuation_synthesizer.py` → `_RELIABILITY_WEIGHT`

---

## Accumulation zones (Gate 3 output)

The valuation zone classifies where the current price sits relative to the fair value range:

| Zone | Price relationship | Action |
|------|--------------------|--------|
| WAIT | Materially above fair value | Do not initiate or add |
| WATCH | Business attractive but price not compelling | Monitor; no action yet |
| START_SMALL | Reasonably attractive entry (near bear fair value) | Initiate small position |
| ACCUMULATE | Attractive, meaningful margin of safety | Add to position |

**Margin of safety philosophy (from `config/valuation_config.yaml`):**  
Do not use a universal fixed MOS percentage. Required MOS varies by:
- Business quality (higher quality = lower required MOS)
- FCF predictability
- Moat strength
- Financial strength
- Growth uncertainty
- Valuation method confidence

Illustrative MOS ranges:
| Business quality | Illustrative MOS |
|----------------|----------------|
| Exceptional quality, high confidence | ~10% below midpoint |
| Strong quality, good confidence | ~15% |
| Moderate quality, medium confidence | ~20% |
| Lower quality or high uncertainty | ~30% |

---

## EPS and FCF period alignment (Phase 9.9b)

A critical correctness requirement: normalised EPS and normalised FCF must use the same fiscal-year window.

**Why:** If EPS is averaged over FY2022–FY2024 but FCF is averaged over FY2023–FY2025, comparing them as if they're equivalent is methodologically wrong. The gap between them may be a calculation artifact rather than a real difference in earnings quality.

**How it's enforced:** `analytics/agent/valuation_builder.py` computes the intersection of available EPS years and available FCF years, then forces both to use only the years in the intersection.

**What the renderer shows:** Either "✓ SAME-PERIOD BASIS" or "⚠ PERIOD MISMATCH" in the FCF reconciliation section.

---

## Verified ITC.NS baseline (Phase 9.9b)

The following numbers have been verified against actual yfinance data as the correct output of the valuation engine for ITC.NS:

| Metric | Verified value | Notes |
|--------|---------------|-------|
| Normalised EPS | ₹16.05/share | 3-year average, continuing-ops NI |
| Normalised FCF/share | ₹12.04/share | 3-year average, same fiscal window |
| Period alignment | ✅ Same 3-year window | FY2024–FY2026 |
| Continuing-ops NI used | ₹197.31B | Not ₹347.47B total (demerger gain excluded) |

Any change to the normalisation logic, valuation inputs, or fiscal-year alignment must re-verify these numbers before acceptance.

---

## Currencies

The system handles three currencies: CAD (Canadian Dollar), USD (US Dollar), INR (Indian Rupee). Fair values are displayed in the company's local currency. Cross-currency comparisons require an assumed exchange rate, which must be clearly stated.

---

## What the valuation engine does NOT do

- It does NOT produce a price target (a single point estimate). It produces a range.
- It does NOT use analyst consensus estimates as primary inputs.
- It does NOT support options, derivatives, or leveraged instruments.
- It does NOT produce peer-relative valuation automatically (PeerData must be manually supplied; currently not populated from yfinance).
