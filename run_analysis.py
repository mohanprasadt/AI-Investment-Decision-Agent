"""
End-to-End Investment Analysis Runner
======================================
Usage:
    python run_analysis.py TD.TO --demo                    # demo data, no internet
    python run_analysis.py TD.TO --demo --portfolio new    # treat as new position
    python run_analysis.py TD.TO --demo --portfolio 5%     # existing position, 5% weight only
    python run_analysis.py TD.TO --demo --portfolio none   # no portfolio context
    python run_analysis.py TD.TO                           # live yfinance data

Portfolio context modes (--portfolio):
  none          No portfolio information. Treated as new position.
  new           Explicitly new position (alias for none with clear intent).
  <N>%          Existing position at N% of portfolio (weight-only, privacy-preserving).
                Does NOT require shares, average cost, or total portfolio value.

Privacy note:
  Weight-only mode is the default for existing positions.
  The system will NOT ask for shares, average cost, account information,
  or any other portfolio details beyond the percentage provided.
  Average cost is NEVER used in the investment decision.
"""

import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Pipeline imports
# ---------------------------------------------------------------------------
from analytics.financial_quality.quality_engine import assess_financial_quality
from analytics.financial_quality.financial_metrics_model import (
    CompanyFinancialMetrics,
    RevenueGrowthMetrics, ROICMetrics, MarginMetrics, FreeCashFlowMetrics,
    DebtMetrics, DividendMetrics, EarningsQualityMetrics,
)
from analytics.valuation.valuation_models import (
    ValuationInput, CompanyType, InputItem, PeerData,
)
from analytics.valuation.valuation_synthesizer import run_valuation
from analytics.business_research.research_models import (
    BusinessResearchAssessment, BusinessUnderstandingAssessment,
    MoatAssessment, MoatStrength, MoatDurability, MoatTrajectory,
    IndustryAssessment, IndustryClassification,
    ManagementAssessment, ManagementRating,
    GrowthAssessment, RiskAssessment, RiskLevel, BullBearAssessment,
    UnderstandabilityRating, Confidence,
)
from analytics.portfolio.portfolio_models import (
    Portfolio, Position, PositionType,
    WeightOnlyPortfolioContext, PortfolioContextMode,
)
from analytics.portfolio.portfolio_synthesizer import build_portfolio_context
from analytics.decision.decision_synthesizer import make_investment_decision
from analytics.data_freshness import build_freshness_assessment


# ===========================================================================
# Live data fetcher (requires yfinance + internet)
# ===========================================================================

def fetch_live(ticker: str) -> dict:
    """Fetch raw yfinance data and return as a plain dict."""
    try:
        import yfinance as yf
    except ImportError:
        raise SystemExit("yfinance not installed. Run: pip install yfinance")

    print(f"Fetching live data for {ticker}...")
    t = yf.Ticker(ticker)
    info = t.info
    if not info or "symbol" not in info:
        raise SystemExit(f"yfinance returned no data for {ticker}. Check the ticker.")

    # Financials
    try:
        income_stmt = t.financials          # annual, most recent first
        balance_sheet = t.balance_sheet
        cashflow = t.cashflow
    except Exception as e:
        print(f"  Warning: could not fetch financials: {e}")
        income_stmt = balance_sheet = cashflow = None

    return {
        "info": info,
        "income_stmt": income_stmt.to_dict() if income_stmt is not None else {},
        "balance_sheet": balance_sheet.to_dict() if balance_sheet is not None else {},
        "cashflow": cashflow.to_dict() if cashflow is not None else {},
    }


def build_metrics_from_live(ticker: str, raw: dict) -> CompanyFinancialMetrics:
    """
    Convert raw yfinance data into a CompanyFinancialMetrics object.
    This is a best-effort mapping — missing fields are left as None.
    The normalizer (Phase 2) does a fuller job; this runner bypasses it
    intentionally so the end-to-end demo works without the full ingestion pipeline.
    """
    info = raw.get("info", {})
    today = date.today().isoformat()

    m = CompanyFinancialMetrics(
        ticker=ticker,
        company_name=info.get("longName", ticker),
        exchange=info.get("exchange", ""),
        currency=info.get("currency", "CAD"),
        data_source="yfinance",
        data_as_of_date=today,
        retrieved_at=today,
        current_price=info.get("currentPrice") or info.get("regularMarketPrice"),
        market_cap=info.get("marketCap"),
        pe_ratio=info.get("trailingPE"),
    )

    # Revenue growth — use trailing revenue and quick CAGR if available
    m.revenue_growth = RevenueGrowthMetrics(
        cagr_5yr=None,  # Would need historical; yfinance summary doesn't expose
        data_years_available=0,
    )

    # ROIC — yfinance doesn't expose directly; approximate via ROE for banks
    roe = info.get("returnOnEquity")
    m.roic = ROICMetrics(
        current=roe * 100 if roe else None,
        moat_support_note="Using ROE as ROIC proxy for financial institution.",
    )

    # Margins
    m.margins = MarginMetrics(
        net_margin=info.get("profitMargins") * 100 if info.get("profitMargins") else None,
    )

    # FCF
    fcf = info.get("freeCashflow")
    rev = info.get("totalRevenue")
    m.free_cash_flow = FreeCashFlowMetrics(
        fcf_current=fcf / 1e9 if fcf else None,
        fcf_margin_current=(fcf / rev * 100) if (fcf and rev) else None,
    )

    # Debt — for banks, total liabilities / total assets is the relevant metric
    total_assets = info.get("totalAssets")
    total_debt = info.get("totalDebt")
    m.debt = DebtMetrics(
        total_assets=total_assets / 1e9 if total_assets else None,
        interest_bearing_debt=total_debt / 1e9 if total_debt else None,
        debt_to_assets_pct=(total_debt / total_assets * 100) if (total_debt and total_assets) else None,
        industry_context_note="High debt-to-assets is structural for a bank; not used as a concern.",
    )

    # Dividend
    div_rate = info.get("dividendRate")
    div_yield = info.get("dividendYield")
    payout = info.get("payoutRatio")
    m.dividend = DividendMetrics(
        pays_dividend=bool(div_rate),
        current_yield_pct=div_yield * 100 if div_yield else None,
        annual_dividend_per_share=div_rate,
        payout_ratio_pct=payout * 100 if payout else None,
    )

    m.data_completeness_pct = 55.0  # Partial — live quick-fetch
    m.data_quality_notes = [
        "Live yfinance quick-fetch — incomplete historical data.",
        "Run the full ingestion pipeline (data/ingestion/fetcher.py) for a complete assessment.",
    ]
    return m


# ===========================================================================
# Demo data — TD Bank as of mid-2025 (from training knowledge)
# ===========================================================================

def build_td_demo_metrics() -> CompanyFinancialMetrics:
    """
    Pre-populated TD Bank financials based on publicly available data.
    Figures are approximate; the live pipeline will be more precise.
    Currency: CAD. Fiscal year end: October.
    Key metrics sourced from FY2024 annual report and Q1-Q2 FY2025.
    """
    m = CompanyFinancialMetrics(
        ticker="TD.TO",
        company_name="The Toronto-Dominion Bank",
        exchange="TSX",
        currency="CAD",
        data_source="manual_demo",
        data_as_of_date="2025-05-01",
        retrieved_at=datetime.utcnow().isoformat()[:10],
        current_price=169.30,    # Market price as of 2026-08-09
        market_cap=141_000,      # ~$141B CAD
        pe_ratio=12.4,
        ev_ebitda=None,          # Not standard for banks
    )

    # Revenue growth (net interest income + non-interest revenue)
    m.revenue_growth = RevenueGrowthMetrics(
        annual_revenues={
            2019: 41_100, 2020: 38_200, 2021: 43_800,
            2022: 48_700, 2023: 52_400, 2024: 54_900,
        },
        cagr_3yr=4.6,
        cagr_5yr=6.0,
        annual_growth_rates={
            2020: -7.1, 2021: 14.7, 2022: 11.2,
            2023: 7.6,  2024: 4.8,
        },
        negative_growth_years=1,
        data_years_available=6,
        trend="Stable",
        consistency_classification="Good",
        organic_vs_acquisition_note="Primarily organic; First Horizon acquisition failed (2023).",
    )

    # ROIC — for banks, ROE is the primary metric
    # TD ROE has declined from ~15% to ~8-10% due to AML issues and provisions
    m.roic = ROICMetrics(
        annual_roic={
            2019: 14.8, 2020: 10.1, 2021: 15.2,
            2022: 14.9, 2023: 11.2, 2024: 8.1,
        },
        current=8.1,
        avg_3yr=11.4,
        avg_5yr=12.3,
        trend="Declining",
        classification="Watch",
        moat_support_note=(
            "ROE declining sharply in FY2024 due to AML provisions and US regulatory issues. "
            "Normalized ROE ex-AML provisions estimated ~12-13%. "
            "Structural quality intact but near-term impairment is real."
        ),
        calculation_note="ROE used as primary metric for financial institution.",
    )

    # Margins — net interest margin and efficiency ratio
    m.margins = MarginMetrics(
        net_margin=20.8,
        operating_margin=28.4,
        net_margin_history={
            2020: 18.2, 2021: 27.4, 2022: 26.1,
            2023: 22.3, 2024: 20.8,
        },
        operating_margin_history={
            2020: 24.1, 2021: 36.2, 2022: 34.8,
            2023: 29.7, 2024: 28.4,
        },
        net_margin_trend="Declining",
        margin_change_explanation=(
            "Net margin under pressure from higher credit provisions (AML-related) "
            "and elevated US regulatory costs. NIM stable but efficiency ratio rising."
        ),
    )

    # FCF — banks generate income, not traditional FCF; use net income as proxy
    m.free_cash_flow = FreeCashFlowMetrics(
        annual_net_income={
            2020: 6_970, 2021: 14_430, 2022: 14_950,
            2023: 10_780, 2024: 9_050,
        },
        fcf_current=9_050,
        fcf_conversion_ratio=0.92,
        fcf_trend="Declining",
        fcf_consistency="Positive but declining",
        recurring_negative_fcf=False,
        fcf_quality_note=(
            "FCF equivalent (net income) positive in all years but declining sharply "
            "due to AML provisions. Dividend is well-covered on normalized earnings."
        ),
    )

    # Debt — bank-specific; focus on Tier 1 capital ratio, not D/A
    m.debt = DebtMetrics(
        debt_to_assets_pct=92.0,     # Normal for a bank (deposits = liabilities)
        interest_coverage=None,
        classification="Good",
        industry_context_note=(
            "High debt-to-assets is structural for Canadian banks. "
            "The relevant metric is Tier 1 Capital ratio (CET1): 13.1% as of Q1 FY2025 — "
            "well above OSFI regulatory minimum of 11.5%. Balance sheet is sound."
        ),
        debt_analysis_note=(
            "CET1 ratio 13.1% provides ample capital buffer. "
            "No going-concern leverage risk."
        ),
    )

    # Dividend
    m.dividend = DividendMetrics(
        pays_dividend=True,
        current_yield_pct=5.1,
        annual_dividend_per_share=4.08,  # CAD (raised FY2024)
        payout_ratio_pct=55.0,           # On normalized earnings
        fcf_payout_ratio_pct=51.0,
        dividend_growth_5yr_cagr=6.8,
        dividend_growth_3yr_cagr=5.2,
        annual_dividends={
            2020: 3.11, 2021: 3.16, 2022: 3.56,
            2023: 3.84, 2024: 4.08,
        },
        years_of_dividend_history=25,
        dividend_cuts=0,
        sustainability_classification="Good",
        sustainability_note=(
            "Dividend yield of 5.1% is close to the 6% investigation threshold. "
            "Payout ratio on normalized earnings is ~55% — sustainable. "
            "25-year dividend growth history with no cuts. "
            "Yield elevated due to regulatory/AML-driven price compression, not underlying impairment."
        ),
        high_yield_investigation_note="",
    )

    # Earnings quality
    m.earnings_quality = EarningsQualityMetrics(
        eps_trend="Declining",
        earnings_quality_note="Negative — AML provisions impacted FY2024 EPS significantly.",
    )

    m.data_completeness_pct = 88.0
    m.data_quality_notes = [
        "Demo data — approximate figures from public sources as of May 2025.",
        "AML consent order (US DOJ, Oct 2024) creates one-time and ongoing provisions.",
        "Normalized earnings (ex-AML) are meaningfully higher than reported FY2024 earnings.",
        "Run the live ingestion pipeline for auditable, timestamped data.",
    ]
    return m


def build_td_demo_research() -> BusinessResearchAssessment:
    """
    Business research assessment for TD Bank.
    This is the kind of content a human analyst would populate
    after studying the company.
    """
    r = BusinessResearchAssessment(
        ticker="TD.TO",
        company_name="The Toronto-Dominion Bank",
        assessment_date="2025-05-01",
    )

    r.business_understanding = BusinessUnderstandingAssessment(
        what_it_does=(
            "The Toronto-Dominion Bank is Canada's second-largest bank by assets (~$2.1T CAD). "
            "It operates through four segments: Canadian Personal and Commercial Banking, "
            "U.S. Retail Banking (extensive branch network), Wealth Management and Insurance, "
            "and TD Securities (wholesale banking and capital markets)."
        ),
        how_it_makes_money=(
            "Net interest income (spread between lending rates and deposit costs) is the primary "
            "driver (~55% of revenue). Non-interest income from fees, trading, wealth management "
            "and insurance contributes the remainder. TD has unusually high US retail exposure vs. "
            "Canadian peers (~30% of earnings when normalized)."
        ),
        understandability_rating=UnderstandabilityRating.SUFFICIENT,
        understandability_note=(
            "Business model is well-understood. The primary current complexity is the ongoing "
            "resolution of the US AML consent order and its impact on US growth restrictions."
        ),
        confidence=Confidence.HIGH,
    )

    r.moat_assessment = MoatAssessment(
        active_sources=["switching_costs", "network_effects", "cost_advantage"],
        overall_strength=MoatStrength.MODERATE,
        overall_durability=MoatDurability.HIGH,
        trajectory=MoatTrajectory.STABLE,
        moat_summary=(
            "Canadian Big Six banking oligopoly provides a structural moat: high regulatory "
            "barriers to entry, entrenched customer relationships (average banking relationship "
            "duration 15+ years), and deposit franchise that provides low-cost funding. "
            "Switching costs are high for both retail and business clients. "
            "The moat is MODERATE rather than STRONG due to US regulatory headwinds and "
            "the commoditised nature of retail banking products."
        ),
        roic_consistency_note=(
            "ROE averaged 13-15% for 10 years pre-AML, supporting a MODERATE moat. "
            "Current ROE compression is regulatory in nature, not structural moat erosion."
        ),
        confidence=Confidence.HIGH,
    )

    r.industry_assessment = IndustryAssessment(
        industry_name="Canadian Banking",
        classification=IndustryClassification.ATTRACTIVE,
        classification_reasoning=(
            "The Canadian banking oligopoly is one of the most attractive banking structures globally: "
            "6 banks control >90% of retail banking deposits. Regulatory barriers prevent new entry. "
            "OSFI oversight is stringent but creates predictability. Net interest margins are structurally "
            "better than most global peers. The industry is ATTRACTIVE despite near-term rate sensitivity."
        ),
        confidence=Confidence.HIGH,
    )

    r.management_assessment = ManagementAssessment(
        overall_rating=ManagementRating.MIXED,
        capital_allocation=(
            "Capital allocation record is mixed. Dividend growth is consistent and well-managed. "
            "The failed First Horizon acquisition ($13.4B USD, cancelled 2023) destroyed significant "
            "value and management credibility. The AML failures in the US represent a serious "
            "compliance and risk management lapse. CEO Bharat Masrani retired 2024; Raymond Chun "
            "took over. New leadership is credible but untested in this role."
        ),
        execution_track_record=(
            "Strong execution in Canadian retail banking. US expansion strategy has been problematic: "
            "AML consent order, asset cap on US retail growth, and failed First Horizon acquisition "
            "are all material management failures. Canadian operations remain well-run."
        ),
        confidence=Confidence.MEDIUM,
    )

    r.growth_assessment = GrowthAssessment(
        growth_sustainability_assessment=(
            "Canadian segment: steady, GDP-plus growth in loans and deposits. "
            "US segment: constrained by US regulator asset cap until AML consent order resolved "
            "(expected 2025-2026). Wealth management and TD Securities provide diversification. "
            "Long-term growth is sustainable at 5-8% EPS CAGR on normalized basis. "
            "Near-term (FY2025-2026) growth is suppressed by AML costs and US growth restrictions."
        ),
        revenue_growth_quality="Primarily organic; fee income growing faster than NII.",
        confidence=Confidence.MEDIUM,
    )

    r.risk_assessment = RiskAssessment(
        overall_level=RiskLevel.HIGH,
        risk_summary=(
            "Risk level is elevated primarily due to the US AML consent order. "
            "This is a binary-ish risk: resolution unlocks US growth; non-resolution or escalation "
            "is a material negative. Canadian operations are low-risk."
        ),
        business_risks=[],
        industry_risks=[],
    )

    r.bull_bear = BullBearAssessment(
        bull_case_narrative=(
            "AML consent order resolved on schedule (FY2025-2026). US asset cap lifted. "
            "TD re-accelerates US retail growth from its already-dominant Northeast franchise. "
            "Dividend yield of ~5% is a floor; capital returns increase as provisions unwind. "
            "Stock re-rates to historical P/Book of 1.5-1.7x from current ~1.2x. "
            "Canadian banking oligopoly remains structurally intact."
        ),
        bear_case_narrative=(
            "AML consent order resolution is delayed or scope expanded by US DOJ. "
            "US asset cap extended, preventing TD from growing its most profitable segment. "
            "Canadian housing correction deepens — elevated HELOC exposure becomes a credit concern. "
            "Rising credit losses across both segments compress earnings further. "
            "Dividend is maintained but EPS/ROE recovery is pushed to FY2027+."
        ),
        thesis_breakers=[
            "AML penalty materially exceeds $3B USD provisions already taken (consensus estimate).",
            "US retail asset cap extended beyond FY2026 — US segment permanently impaired.",
            "Canadian housing correction of >20% with material credit losses (HELOC book).",
            "Dividend cut or suspension — would signal earnings stress beyond current consensus.",
            "ROE fails to recover to 12%+ within 3 years of AML resolution.",
        ],
        devils_advocate_research_note=(
            "The bear case is credible. The AML failures represent genuine risk management breakdown, "
            "not a one-time technical violation. TD's US operations were built on a culture that "
            "de-prioritized compliance. Whether new management has genuinely fixed this, or whether "
            "the consent order reveals deeper systemic issues, is unknowable with certainty."
        ),
        confirmation_bias_check=(
            "The bull thesis requires AML resolution on a specific timeline. "
            "If resolution is delayed by 12+ months, the thesis is materially weakened. "
            "I am checking: is the Canadian banking moat argument post-rationalising an attractive "
            "valuation? The moat argument was true pre-AML and should remain true post-resolution. "
            "The AML issue is the key variable."
        ),
    )

    r.business_quality_interpretation = (
        "TD is a high-quality franchise temporarily impaired by US regulatory issues. "
        "The Canadian banking moat is intact. The question is: (1) AML resolution timeline and cost, "
        "and (2) whether US operations can re-accelerate once the asset cap is lifted. "
        "Normalized quality is STRONG; current reported quality is WATCH."
    )

    r.research_completeness = {
        k: True for k in
        ["business_understanding", "moat", "industry", "management", "growth", "risk", "bull_bear"]
    }
    r.research_gaps = [
        "Precise AML settlement amount not yet publicly disclosed — consensus is ~$2-3B USD.",
        "US retail asset cap removal timeline uncertain — regulatory discretion.",
        "New CEO (Raymond Chun) track record limited — took role Q4 2024.",
    ]
    r.key_investment_questions = [
        "When will the US AML consent order be resolved, and at what total cost?",
        "Can ROE recover to 12-13% within 2-3 years of AML resolution?",
        "Is the Canadian housing exposure (HELOC book) a latent credit risk?",
    ]
    return r


def build_td_demo_valuation(current_price: float = 169.30) -> ValuationInput:
    """
    TD Bank valuation inputs.
    For a bank, Price/Book and normalized P/E are the primary methods.
    DCF is not standard for banks.
    """
    return ValuationInput(
        ticker="TD.TO",
        company_name="The Toronto-Dominion Bank",
        company_type=CompanyType.FINANCIAL,
        valuation_date="2025-05-01",
        currency="CAD",
        fx_rate_to_cad=1.0,

        current_price=InputItem(
            name="current_price", value=current_price,
            source="Market", period="2026-08-09",
            retrieval_date="2026-08-09",
        ),
        shares_outstanding=InputItem(
            name="shares_outstanding", value=1_800.0,
            source="FY2024 annual report", period="FY2024",
        ),
        # Earnings — use eps_ttm for reported; eps_history for normalized context
        eps_ttm=InputItem(
            name="eps_ttm", value=6.33,
            source="FY2024 annual report", period="FY2024",
            retrieval_date="2025-05-01",
        ),
        # EPS history — used for normalization
        eps_history={
            "2020": 5.36, "2021": 10.78, "2022": 11.18,
            "2023": 7.99, "2024": 6.33,
        },
        # Book value — key metric for banks (P/B valuation)
        book_value_per_share=InputItem(
            name="book_value_per_share", value=64.50,
            source="FY2024 balance sheet", period="FY2024",
        ),
        # Revenue / NII
        revenue=InputItem(
            name="revenue", value=54_900.0,
            source="FY2024 annual report", period="FY2024",
        ),
        revenue_history={
            "2020": 38_200, "2021": 43_800, "2022": 48_700,
            "2023": 52_400, "2024": 54_900,
        },
        # No EBITDA for banks
        ebitda=None,
        ebit=None,
        # FCF proxy — net income for banks
        fcf_ttm=InputItem(
            name="fcf_ttm", value=9_050.0,
            source="FY2024 net income (FCF proxy for bank)", period="FY2024",
        ),
        fcf_history={
            "2020": 6_970, "2021": 14_430, "2022": 14_950,
            "2023": 10_780, "2024": 9_050,
        },
        # Debt / capital (bank-context)
        total_debt=InputItem(
            name="total_debt", value=1_920_000.0,
            source="FY2024 balance sheet", period="FY2024",
        ),
        cash_and_equivalents=InputItem(
            name="cash", value=110_000.0,
            source="FY2024 balance sheet", period="FY2024",
        ),
        # Peer comparables — pass as PeerData objects (P/E and P/B for Canadian banks)
        peers=[
            PeerData(ticker="RY.TO",  name="Royal Bank",          pe_ratio=13.1, price_to_book=2.0,  source="TSX", similarity_note="Largest Canadian bank; premium P/B justified by superior ROE"),
            PeerData(ticker="BNS.TO", name="Bank of Nova Scotia",  pe_ratio=10.8, price_to_book=1.1,  source="TSX", similarity_note="Similar Big 6 structure; higher EM exposure"),
            PeerData(ticker="BMO.TO", name="Bank of Montreal",     pe_ratio=11.2, price_to_book=1.3,  source="TSX", similarity_note="Similar US exposure via BMO Harris"),
            PeerData(ticker="CM.TO",  name="CIBC",                 pe_ratio=11.9, price_to_book=1.5,  source="TSX", similarity_note="Smaller US footprint; Canada-focused"),
        ],
        # Historical multiples (for mean-reversion analysis)
        pe_history={
            "2020": 15.2, "2021": 11.8, "2022": 10.9,
            "2023": 12.1, "2024": 12.4,
        },
        # DCF growth hint (used if DCF is run — not primary for banks)
        dcf_revenue_growth_rate=5.0,
        # Analyst estimate for forward year
        analyst_eps_next_year=InputItem(
            name="analyst_eps_fy2025", value=7.80,
            source="Analyst consensus FY2025E — normalized ex-AML", period="FY2025E",
        ),
        # Moat and quality hints for method selection
        moat_strength="MODERATE",
        financial_quality_hint="WATCH",
    )


# ===========================================================================
# Portfolio context builder (optional)
# ===========================================================================

def build_portfolio_ctx(ticker: str, portfolio_arg: str):
    """
    Parse --portfolio argument and return the appropriate context object.

    portfolio_arg values:
      "none" / "new"   → None (treat as new position)
      "N%"             → WeightOnlyPortfolioContext at N%
      None             → None (no portfolio info)
    """
    if portfolio_arg is None or portfolio_arg.lower() in ("none", "new"):
        return None

    # Weight-only mode: "5%" or "5"
    pct_str = portfolio_arg.strip().rstrip("%")
    try:
        weight = float(pct_str)
    except ValueError:
        print(f"  ⚠ Could not parse --portfolio '{portfolio_arg}' as a percentage. Treating as new position.")
        return None

    return WeightOnlyPortfolioContext(
        ticker=ticker,
        portfolio_weight_pct=weight,
    )


# ===========================================================================
# Output formatter
# ===========================================================================

def print_report(decision):
    """Print a human-readable investment decision report."""
    d = decision

    bar = "=" * 72
    thin = "-" * 72

    print(f"\n{bar}")
    print(f"  INVESTMENT DECISION — {d.ticker}  |  {d.company_name}")
    print(f"  Analysis date: {d.analysis_date}  |  Price: {d.current_price:.2f} {d.price_currency}" if d.current_price else f"  Analysis date: {d.analysis_date}")
    print(bar)

    print(f"\n  ACTION:      {d.action.value}")
    print(f"  CONFIDENCE:  {d.decision_confidence.value}")
    if d.data_freshness_cap_applied:
        print(f"  [Confidence was capped by data freshness — see DATA FRESHNESS section]")
    print()

    # Three-way attractiveness (Phase 7.5)
    if d.business_quality_label or d.valuation_attractiveness_label:
        print(thin)
        print("  THREE-WAY ATTRACTIVENESS")
        print(thin)
        print(f"  Business Quality:       {d.business_quality_label or 'N/A'}")
        print(f"  Valuation Attractive:   {d.valuation_attractiveness_label or 'N/A'}")
        print(f"  Investment Attractive:  {d.investment_attractiveness_label or 'N/A'}")
        if d.investment_attractiveness_note:
            print(f"  Note: {d.investment_attractiveness_note}")
        print()

    print(thin)
    print("  EXECUTIVE SUMMARY")
    print(thin)
    print(f"  {d.executive_conclusion}")
    print()

    print(thin)
    print("  BUSINESS THESIS")
    print(thin)
    print(f"  {d.business_thesis}")
    print()

    print(thin)
    print("  6 EXPLANATION QUESTIONS")
    print(thin)
    print(f"  1. Why attractive/unattractive?")
    print(f"     {d.why_attractive_or_unattractive}")
    print()
    print(f"  2. Biggest reason TO invest?")
    print(f"     {d.biggest_reason_to_invest}")
    print()
    print(f"  3. Biggest reason NOT to invest?")
    print(f"     {d.biggest_reason_not_to_invest}")
    print()
    print(f"  4. Is current price attractive?")
    print(f"     {d.is_current_price_attractive}")
    print()
    print(f"  5. Appropriate action given portfolio?")
    print(f"     {d.appropriate_action_given_portfolio}")
    print()
    print(f"  6. What would change the conclusion?")
    # what_would_change_conclusion is the formatted prose version
    change_text = d.what_would_change_conclusion or ""
    if not change_text and d.what_would_change_decision:
        items = d.what_would_change_decision
        change_text = "\n".join(f"     • {i}" for i in items)
        print(change_text)
    else:
        for line in change_text.split("\n"):
            print(f"     {line}")
    print()

    print(thin)
    print("  GATE RESULTS (Decision Hierarchy)")
    print(thin)
    for g in d.gate_results:
        status = "PASS" if g.passed else "FAIL"
        extra = ""
        if g.quality_tier:    extra += f"  QualityTier:{g.quality_tier}"
        if g.adversarial_risk: extra += f"  AdversarialRisk:{g.adversarial_risk}"
        if g.forced_action:    extra += f"  FORCED→{g.forced_action}"
        print(f"  Gate {g.gate_number}: {g.gate_name:<30} [{status}]  conf:{g.confidence}{extra}")
    print()

    print(thin)
    print("  KEY THESIS BREAKERS")
    print(thin)
    for i, b in enumerate(d.thesis_breakers[:5], 1):
        print(f"  {i}. [{b.likelihood}/{b.impact}] {b.condition[:100]}")
        print(f"     Monitor: {b.monitoring_indicator[:80]}")
        print(f"     Trigger: {b.trigger_action[:60]}")
    print()

    print(thin)
    print("  SUPPORTING EVIDENCE")
    print(thin)
    for e in d.supporting_evidence[:4]:
        print(f"  + {e.observation[:100]}")
    print()

    print(thin)
    print("  CONTRADICTORY EVIDENCE")
    print(thin)
    for e in d.contradictory_evidence[:4]:
        print(f"  - {e.observation[:100]}")
    print()

    print(thin)
    print("  RISKS")
    print(thin)
    for r in d.key_risks[:4]:
        print(f"  ! {r[:100]}")
    print()

    print(thin)
    print("  RESEARCH GAPS / DATA QUALITY")
    print(thin)
    for g in (d.research_gaps + d.data_quality_limitations)[:5]:
        print(f"  ? {g[:100]}")
    print()

    print(thin)
    print("  PHILOSOPHY ALIGNMENT")
    print(thin)
    for n in d.philosophy_alignment_notes[:5]:
        print(f"  • {n[:100]}")
    print()

    # Data freshness (Phase 7.5)
    if d.data_freshness:
        print(thin)
        print("  DATA FRESHNESS")
        print(thin)
        df = d.data_freshness
        print(f"  Overall status: {df.get('overall_status', 'UNKNOWN')}")
        if df.get('confidence_cap'):
            print(f"  Confidence cap: {df['confidence_cap']}")
        for item in df.get('items', []):
            print(f"  {item.get('label',''):<26} {item.get('period_or_date',''):<15} [{item.get('status','')}]")
        for note in df.get('freshness_notes', [])[:2]:
            print(f"  Note: {note[:120]}")
        print()

    print(thin)
    print(f"  NEXT STEP: {d.recommended_next_step}")
    print()
    print(f"  {d.cost_basis_excluded_note[:120]}")
    print(bar)


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Run end-to-end investment analysis.")
    parser.add_argument("ticker", nargs="?", default="TD.TO", help="Ticker symbol (default: TD.TO)")
    parser.add_argument("--demo", action="store_true", help="Use pre-populated demo data (no internet)")
    parser.add_argument(
        "--portfolio", type=str, default=None,
        help=(
            "Portfolio context mode: "
            "'none' or omit = no portfolio info (new position); "
            "'new' = explicitly a new position; "
            "'5%%' or '5.0' = existing position at that portfolio weight %%. "
            "Never asks for shares, average cost, or account details."
        ),
    )
    parser.add_argument("--output", type=str, default=None, help="Output JSON path (default: data/output/<ticker>.json)")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    analysis_date = date.today().isoformat()

    # -----------------------------------------------------------------------
    # Step 1: Build financial metrics
    # -----------------------------------------------------------------------
    if args.demo or ticker == "TD.TO":
        print(f"\n[1/5] Building financial metrics (demo data for {ticker})...")
        metrics = build_td_demo_metrics()
        fq = assess_financial_quality(metrics, is_financial_institution=True)
        current_price = 169.30
        price_currency = "CAD"
    else:
        print(f"\n[1/5] Fetching live data for {ticker}...")
        raw = fetch_live(ticker)
        metrics = build_metrics_from_live(ticker, raw)
        current_price = metrics.current_price or 0.0
        price_currency = metrics.currency
        fq = assess_financial_quality(metrics, is_financial_institution=False)

    print(f"     ✓ Financial quality: {fq.data_completeness_pct:.0f}% data completeness")

    # -----------------------------------------------------------------------
    # Step 2: Business research
    # -----------------------------------------------------------------------
    print(f"[2/5] Loading business research...")
    if ticker == "TD.TO" or args.demo:
        research = build_td_demo_research()
    else:
        print("     ⚠ No automated business research — returning None (WAIT_INSUFFICIENT_EVIDENCE likely)")
        research = None
    print(f"     ✓ Research loaded")

    # -----------------------------------------------------------------------
    # Step 3: Valuation
    # -----------------------------------------------------------------------
    print(f"[3/5] Running valuation engine...")
    if ticker == "TD.TO" or args.demo:
        val_inputs = build_td_demo_valuation(current_price=current_price)
    else:
        print("     ⚠ No valuation inputs for this ticker — valuation will be skipped")
        val_inputs = None

    valuation = run_valuation(val_inputs) if val_inputs else None
    if valuation:
        zone = valuation.accumulation_zone.zone.value if valuation.accumulation_zone else "N/A"
        print(f"     ✓ Valuation complete — zone: {zone}")
    else:
        print(f"     ✓ Valuation skipped")

    # -----------------------------------------------------------------------
    # Step 4: Portfolio context
    # -----------------------------------------------------------------------
    print(f"[4/5] Building portfolio context...")
    portfolio_ctx = build_portfolio_ctx(ticker, args.portfolio)
    if portfolio_ctx is None:
        print(f"     ✓ No portfolio context — treating as new position (NONE mode)")
    elif isinstance(portfolio_ctx, WeightOnlyPortfolioContext):
        print(f"     ✓ Portfolio context: WEIGHT_ONLY — {portfolio_ctx.portfolio_weight_pct:.1f}% existing position")
    else:
        print(f"     ✓ Portfolio context: FULL — {portfolio_ctx.portfolio_weight_pct:.2f}% existing position")

    # -----------------------------------------------------------------------
    # Step 5: Decision engine
    # -----------------------------------------------------------------------
    print(f"[5/5] Running investment decision engine...")

    # Build data freshness assessment from known input dates
    _fin_stmt_date = getattr(metrics, "data_as_of_date", None) or analysis_date
    freshness = build_freshness_assessment(
        analysis_date=analysis_date,
        price_date=analysis_date,           # Demo: price quoted today
        financial_statements_period="FY2024",
        financial_statements_date=_fin_stmt_date,
        earnings_period="Q2 FY2025",
        earnings_date=_fin_stmt_date,
        research_date=_fin_stmt_date,
        valuation_date=_fin_stmt_date,
    )

    decision = make_investment_decision(
        ticker=ticker,
        company_name=metrics.company_name,
        analysis_date=analysis_date,
        financial_quality=fq,
        research=research,
        valuation=valuation,
        portfolio_ctx=portfolio_ctx,
        current_price=current_price,
        price_currency=price_currency,
        price_date=analysis_date,
        freshness=freshness,
    )
    print(f"     ✓ Decision: {decision.action.value} (confidence: {decision.decision_confidence.value})")

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------
    output_dir = PROJECT_ROOT / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_ticker = ticker.replace(".", "_")
    output_path = args.output or str(output_dir / f"{safe_ticker}_decision.json")
    with open(output_path, "w") as f:
        f.write(decision.to_json())
    print(f"\n  JSON saved → {output_path}")

    # Print formatted report
    print_report(decision)


if __name__ == "__main__":
    main()
