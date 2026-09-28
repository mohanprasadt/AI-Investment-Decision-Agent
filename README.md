# AI Investment Decision Agent

A personal investment research and decision-support system. Given a stock ticker, it ingests financial data, evaluates business quality, analyses competitive advantages, estimates intrinsic value across multiple methods, and synthesises a disciplined investment action — aligned with a defined investment philosophy.

**This system is an analytical tool, not financial advice.** See the disclaimer at the bottom.

---

## Table of Contents

1. [Purpose](#purpose)
2. [Core Capabilities](#core-capabilities)
3. [Valuation Framework](#valuation-framework)
4. [Decision Architecture](#decision-architecture)
5. [EPS / FCF Period-Alignment Architecture](#eps--fcf-period-alignment-architecture)
6. [Project Structure](#project-structure)
7. [Setup and Usage](#setup-and-usage)
8. [Testing](#testing)
9. [Known Limitations](#known-limitations)
10. [Disclaimer](#disclaimer)

---

## Purpose

The agent supports individual investors who want to analyse equities using a structured, repeatable process — not gut feel. It:

- Gathers financial data from yfinance (free, no API key required for the data layer)
- Evaluates financial quality against configurable thresholds
- Researches business understanding, moat, management, and risk using the Anthropic Claude API
- Estimates intrinsic value using four independent methods with a weighted synthesis
- Applies sequential decision gates before emitting a recommended action
- Preserves portfolio privacy: accepts portfolio weight (%) only; never requests or stores shares, cost basis, or total account value

**Intended users:** Individual investors who want a systematic, transparent, and auditable decision-support workflow.

**Supported markets:** Canadian (TSX), US (NYSE/NASDAQ), Indian (NSE/BSE) equities.

---

## Core Capabilities

### Phase 1–2: Financial Data Ingestion
`data/ingestion/fetcher.py` — yfinance fetch of income statement, balance sheet, and cash-flow statement. Results are cached locally in `data/cache/`.

`data/ingestion/normalizer.py` — maps raw yfinance fields to a strongly-typed `CompanyFinancialMetrics` model. Handles field-name variations across yfinance versions. Separates continuing-operations net income from discontinued-operations gains for accurate EPS derivation.

### Phase 3: Financial Quality Analysis
`analytics/financial_quality/quality_engine.py` — evaluates revenue growth, ROIC, margins, FCF conversion, debt coverage, and earnings quality against configurable thresholds (`config/thresholds.yaml`). Produces a `FinancialQualityAssessment` with a pass/fail classification per dimension.

### Phase 4: Business Research
`analytics/agent/anthropic_researcher.py` / `analytics/business_research/` — uses the Claude API to research business understanding, competitive moat, management quality, and investment risks. Evidence is tagged by strength (STRONG / MODERATE / WEAK) and source tier (T1 primary / T2 secondary / T3 model-derived).

### Phase 5: Valuation
Four independent valuation methods (see [Valuation Framework](#valuation-framework)) produce bear/mid/bull implied value ranges that are weighted into a synthesised fair-value range.

### Phase 6: Portfolio Context
`analytics/portfolio/` — evaluates incremental position sizing, concentration impact, and sector/geography exposure using the user-supplied portfolio weight. No shares, cost, or account value is ever used.

### Phase 7: Adversarial / Risk Analysis
`analytics/decision/gate5_adversarial.py` — stress-tests the investment thesis against identified thesis breakers. A SEVERE adversarial finding forces a REDUCE or EXIT action regardless of valuation attractiveness.

### Phase 7: Decision Synthesis
`analytics/decision/decision_synthesizer.py` — combines all prior phases through a five-gate sequential filter into a final `InvestmentDecisionAssessment` with an action (START_SMALL / ACCUMULATE / WATCH / HOLD / REDUCE / EXIT / WAIT_INSUFFICIENT_EVIDENCE).

---

## Valuation Framework

All four methods run independently. Each produces a bear / mid / bull implied value. Results are weighted and synthesised into a `FairValueRange`.

### Normalised P/E
Derives EPS from **continuing-operations net income** (not total net income) divided by shares outstanding, averaged over the common fiscal-year window shared with FCF normalisation. Applies a multiple range appropriate to the company type.

### P/FCF (Price-to-Free-Cash-Flow)
Averages FCF (Operating Cash Flow − Capital Expenditure) over the same 3-year fiscal-year window as the EPS normalisation. Applies a multiple range to FCF/share.

### EV/EBITDA
Enterprise value over EBITDA using a sector-appropriate multiple range. Cash is sourced from the broadest available balance-sheet line (short-term + cash equivalents preferred over narrow cash equivalents only).

### DCF (Discounted Cash Flow)
FCF-based DCF with bear/base/bull scenarios for revenue growth, FCF margin, terminal growth, and discount rate. Inputs are sourced from historical data and analyst estimates where available; conservative defaults are applied otherwise.

### Weighted Fair-Value Synthesis
Each applicable method is assigned a weight. The synthesised fair value is a weighted average across methods. Methods without sufficient data are excluded and weights are redistributed.

### Valuation Zones

| Zone | Condition | Typical Action |
|---|---|---|
| START_SMALL | Price well below bear FV; strong thesis | Begin accumulation |
| ACCUMULATE | Price below base FV; intact thesis | Add to position |
| WATCH | Price near or above base FV | Monitor; no new buying |
| WAIT | Insufficient data or gate failure | Hold; gather evidence |

---

## Decision Architecture

The pipeline is structured as three layers (L1 → L2 → L3) with five sequential gates.

```
L1  Financial Data   →  CompanyFinancialMetrics  (Phase 1–2)
                        FinancialQualityAssessment (Phase 3)

L2  Valuation        →  ValuationAssessment       (Phase 5)
                        (DCF + P/E + EV/EBITDA + P/FCF → weighted FairValueRange)

L3  Decision         →  InvestmentDecisionAssessment (Phase 7)
```

### Five Decision Gates

```
Gate 1 — Business Understanding     Must have sufficient qualitative research
Gate 2 — Financial Quality          Must meet minimum quality threshold
Gate 3 — Valuation Attractiveness   Must have a computable fair-value range
Gate 4 — Portfolio Fit              Must pass concentration and risk limits
Gate 5 — Adversarial Stress Test    No active thesis breakers at SEVERE level
```

Each gate is a hard filter. Failing Gate 1 (no business research) produces `WAIT_INSUFFICIENT_EVIDENCE` regardless of the quantitative picture. Failing Gate 5 (SEVERE adversarial risk) forces REDUCE or EXIT regardless of valuation attractiveness.

The quantitative fallback (no Claude API key) intentionally fails Gate 1 and produces `WAIT_INSUFFICIENT_EVIDENCE`. This is the correct output — a valuation alone is not a decision.

---

## EPS / FCF Period-Alignment Architecture

Phase 9.9b introduced a set of corrections to ensure the EPS and FCF inputs to valuation are methodologically consistent. These are production architectural choices, not temporary workarounds.

### Continuing-Operations Net Income for EPS

`normalizer.py` extracts net income from continuing operations in preference order:

```
1. "Net Income From Continuing Operation Net Minority Interest"
2. "Net Income From Continuing Operations Net Minority Interest"
3. "Net Income Continuous Operations"
4. "Net Income From Continuing Operations"
5. fallback: total "Net Income"
```

This prevents one-time discontinued-operations gains from inflating normalised EPS. For ITC Ltd (ITC.NS), the FY2025 demerger produced a ₹150.16B discontinued-operations gain that raised total net income to ₹347.47B versus recurring continuing-operations income of ₹197.31B. Without this correction, normalised EPS would overstate recurring earnings by ~76%.

`FreeCashFlowMetrics.annual_net_income` stores the continuing-operations series. `EarningsQualityMetrics.annual_net_income` intentionally retains total net income (it is an accounting completeness metric, not a recurring-income metric).

### Common Fiscal-Year Window

EPS history and FCF normalisation use **the same fiscal-year set**: the intersection of years present in both the net-income series and the FCF series, taking the most recent `FCF_NORM_YEARS` (currently 3) common years. This prevents a spurious EPS-vs-FCF "gap" caused purely by different averaging windows.

`valuation_builder.py`:
```python
_common_years = sorted(
    set(_ni_series_eps.keys()) & set(_fcf_series_eps.keys()),
    reverse=True,
)[:FCF_NORM_YEARS]
```

### Period-Alignment Renderer

The `_answer_fcf_reconciliation` renderer function:
- Parses the actual fiscal-year lists from EPS and FCF normalization notes
- Compares them as sets
- Emits `✓ SAME-PERIOD BASIS` only when year sets are identical
- Emits `⚠ PERIOD MISMATCH` when year sets differ, identifying the specific differing years
- Does **not** fabricate D&A, working-capital, or tax components; labels any residual as unexplained and lists the unavailable line items explicitly

### Verified ITC.NS Baseline (Phase 9.9b)

| Metric | Value |
|---|---|
| EPS fiscal years | FY2024, FY2025, FY2026 |
| FY2025 continuing-ops NI | ₹197.31B (not ₹347.47B total NI) |
| Normalised EPS | ₹16.05/share |
| FCF fiscal years | FY2024–FY2026 (3yr avg) |
| FCF/share | ₹12.04/share |
| Period alignment | ✓ SAME-PERIOD BASIS (FY2024–FY2026) |
| P/E bear / mid / bull | ₹192.56 / ₹288.85 / ₹401.18 |
| P/FCF bear / mid / bull | ₹144.45 / ₹216.67 / ₹300.93 |
| EV/EBITDA bear / mid / bull | ₹158.86 / ₹240.01 / ₹321.17 |
| DCF bear / base / bull | ₹128.77 / ₹195.93 / ₹349.79 |
| Weighted FV bear / base / bull | ₹154.66 / ₹233.02 / ₹332.53 |
| Valuation zone | WAIT (price above base FV) |

---

## Project Structure

```
AI-Investment-Decision-Agent/
│
├── config/
│   ├── investment_philosophy.md     # Investor profile and decision principles
│   ├── thresholds.yaml              # Financial quality thresholds (all guidelines)
│   └── valuation_config.yaml        # DCF assumptions, zone boundaries, FX handling
│
├── analytics/
│   ├── financial_quality/
│   │   ├── financial_metrics_model.py   # Typed data models for all financial metrics
│   │   ├── calculations.py              # Deterministic financial calculations
│   │   ├── quality_engine.py            # Evaluates metrics against thresholds
│   │   └── thresholds_engine.py         # Threshold loading and classification
│   ├── valuation/
│   │   ├── valuation_models.py          # ValuationInput, ValuationAssessment data models
│   │   ├── multiples_engine.py          # P/E, P/FCF, EV/EBITDA, historical methods
│   │   ├── dcf_engine.py                # DCF with bear/base/bull scenarios
│   │   ├── valuation_synthesizer.py     # Weighted synthesis of all methods
│   │   ├── method_selector.py           # Method applicability rules
│   │   └── margin_of_safety.py          # MOS calculation and zone classification
│   ├── portfolio/
│   │   ├── portfolio_models.py          # Portfolio data models
│   │   ├── portfolio_calculator.py      # Concentration and allocation calculations
│   │   ├── portfolio_synthesizer.py     # Portfolio context for decision
│   │   ├── concentration_analyzer.py    # Position size risk evaluation
│   │   └── incremental_scenarios.py     # What-if scenarios for position changes
│   ├── business_research/
│   │   ├── research_models.py           # BusinessResearchAssessment data models
│   │   ├── research_synthesizer.py      # Synthesises qualitative research
│   │   └── moat_analyzer.py             # Competitive advantage classification
│   ├── decision/
│   │   ├── decision_models.py           # InvestmentDecisionAssessment, DecisionAction
│   │   ├── decision_synthesizer.py      # Five-gate decision pipeline
│   │   ├── gate1_understanding.py       # Gate 1: business understanding
│   │   ├── gate2_quality.py             # Gate 2: financial quality
│   │   ├── gate3_valuation.py           # Gate 3: valuation attractiveness
│   │   ├── gate4_portfolio.py           # Gate 4: portfolio fit
│   │   └── gate5_adversarial.py         # Gate 5: adversarial stress test
│   └── agent/
│       ├── data_loader.py               # DataLoadResult: fetch → normalise → quality
│       ├── valuation_builder.py         # DataLoadResult → ValuationInput
│       ├── investment_agent.py          # Top-level agent orchestration
│       ├── anthropic_researcher.py      # Claude API business research
│       ├── renderer.py                  # Follow-up question renderer
│       ├── intent_parser.py             # Natural language intent routing
│       └── research_orchestrator.py     # Research workflow coordination
│
├── data/
│   ├── ingestion/
│   │   ├── fetcher.py                   # yfinance data fetch with local cache
│   │   ├── normalizer.py                # Raw → CompanyFinancialMetrics mapping
│   │   └── portfolio_updater.py         # Portfolio snapshot updater
│   ├── cache/                           # Auto-generated; gitignored
│   ├── output/                          # Generated decision JSON; gitignored
│   ├── raw/                             # Gitignored
│   └── processed/                       # Gitignored
│
├── portfolio/
│   ├── portfolio_snapshot.csv           # Personal holdings; gitignored
│   └── thesis/
│       └── TEMPLATE_thesis.json         # Template for per-company thesis files
│
├── decisions/
│   ├── current/                         # Active decisions; gitignored
│   └── history/                         # Historical decisions; gitignored
│
├── journal/
│   └── TEMPLATE_journal_entry.json      # Decision journal template
│
├── agent/
│   └── prompts/                         # Claude prompt templates for research phases
│
├── tests/
│   ├── test_calculations.py             # Financial calculation unit tests
│   ├── test_ingestion.py                # Data ingestion tests
│   ├── test_quality_engine.py           # Financial quality engine tests
│   ├── test_valuation.py                # Valuation engine tests
│   ├── test_decision.py                 # Decision synthesis tests
│   ├── test_portfolio.py                # Portfolio analytics tests
│   ├── test_phase9*.py                  # Phase-by-phase integration tests
│   └── test_phase99.py                  # Phase 9.9b period-alignment tests
│
├── run_agent.py                         # Main interactive agent entry point
├── run_analysis.py                      # Batch analysis runner
├── .env.example                         # Environment variable template
└── config/
    └── investment_philosophy.md         # Investment philosophy documentation
```

---

## Current Phase

**Last completed: Phase 10.6 — Documentation & Product Governance Foundation**

The system now includes a conversational Streamlit UI, a 33-ticker MVP universe (25 Canada, 5 USA, 3 India), and a complete documentation pack at `docs/README.md`.

---

## Setup and Usage

### Requirements

```bash
pip install -r requirements.txt
```

Requires Python 3.10+. See `requirements.txt` for pinned dependencies (yfinance, anthropic, streamlit, pyyaml, python-dotenv, pytest).

### Environment Variables

Copy `.env.example` to `.env` and set your Anthropic API key:

```
ANTHROPIC_API_KEY=your-key-here
```

The API key is required only for the qualitative research phase (Phase 4). Without it, the pipeline produces `WAIT_INSUFFICIENT_EVIDENCE` — which is the correct output when business research is absent.

yfinance requires no API key.

### Running the UI (recommended)

```bash
# Pre-warm the cache before first use (run once; takes ~25 min for 33 tickers)
python scripts/prewarm_mvp.py

# Launch the conversational Streamlit interface
streamlit run run_ui.py
```

The UI opens at `http://localhost:8501`. Select a ticker from the 33-ticker dropdown (or enter a custom ticker), optionally provide a portfolio weight, and click Analyse. Follow-up questions are answered from the held session without re-fetching data.

### Running the CLI (advanced)

```bash
# Analyse a ticker (requires yfinance network access)
python run_agent.py --ticker ITC.NS

# With portfolio weight context
python run_agent.py --ticker ITC.NS --weight 4.1

# Treat as a new position (no portfolio context)
python run_agent.py --ticker ITC.NS --new-position
```

### Running Tests

```bash
# Full test suite
python -m pytest

# Specific phase
python -m pytest tests/test_phase99.py -v
```

### Data Cache

yfinance responses are cached as flat JSON files in `data/cache/` (gitignored). TTLs: company info 24h, financials 48h, price history 24h. Use `Force Refresh` in the UI or re-run `scripts/prewarm_mvp.py` to refresh stale data.

---

## Testing

**Current baseline: Phase 10.6 — 1,223 passed**

```
Passed:    1,223
Skipped:       1
Failed:        5  (pre-existing — network-dependent, test_phase93b.py only)
Errors:        3  (pre-existing — collection errors in legacy helper files)
```

**Pre-existing failures (5):** `test_phase93b.py` makes live yfinance calls; these fail in network-restricted or rate-limited environments. Not regressions.

**Pre-existing collection errors (3):** `test_calculations.py`, `test_ingestion.py`, `test_quality_engine.py` each define a `def test(...)` helper that conflicts with pytest's `name` fixture. All substantive tests in those files run and pass correctly.

**Phase 10.5 coverage (107 tests):** pipeline, 429 fail-fast, prewarm, ticker dropdown, data status panel, Force Refresh, conversation intents, session state, UI rendering.

**Phase 9.9b coverage (63 tests):** continuing-ops NI preference, total NI fallback, common fiscal-year window alignment, SAME-PERIOD BASIS / PERIOD MISMATCH renderer.

---

## Known Limitations

These limitations are grounded in the current implementation, not aspirational statements.

**Qualitative research requires the Anthropic API.** Without `ANTHROPIC_API_KEY`, Gate 1 fails and the output is `WAIT_INSUFFICIENT_EVIDENCE`. The quantitative pipeline (financial quality, valuation) runs fully without the API.

**yfinance field availability varies.** Field names differ across yfinance versions and ticker types. The normalizer handles known variations; unexpected fields produce `None` (never a fabricated value). Gaps are reported in `data_quality_notes`.

**Continuing-operations NI availability.** When yfinance does not provide a continuing-operations net income field, the pipeline falls back to total net income. This is logged in the normalization note and visible in the EPS provenance.

**EPS and FCF window capped at 3 years.** The common-year intersection is limited to the 3 most recent fiscal years. Companies with fewer than 3 years of data in either series will produce a shorter window, reported honestly in the normalization note.

**No real-time pricing.** Prices are fetched from yfinance at analysis time and cached. The pipeline does not subscribe to live price feeds.

**No automated trade execution.** The system produces a recommended action and rationale. All trading decisions and order placement remain with the human investor.

**D&A / working-capital decomposition.** The EPS-to-FCF reconciliation shows the observed gap and available OCF/capex data. When D&A, working capital, and tax-timing items are not separately available in the stored assessment, they are listed as unavailable rather than estimated.

**Peer valuation requires manual input.** The peer comparison method is not populated automatically. Peer multiples must be supplied as `PeerData` objects if used.

---

## Disclaimer

This system is an **analytical and decision-support tool** for educational and personal research purposes. It is **not financial advice**, and it does not constitute a solicitation to buy or sell any security.

All outputs — including valuation estimates, fair-value ranges, and recommended actions — are based on publicly available data processed through a deterministic model with configurable assumptions. They reflect the model's calculations, not a guarantee of future investment performance.

The authors and contributors accept no liability for investment decisions made based on the outputs of this system. Consult a qualified financial adviser before making investment decisions.

---

*Phase 10.6 — Documentation & Product Governance Foundation — September 2026*  
*Full documentation: [`docs/README.md`](docs/README.md)*
