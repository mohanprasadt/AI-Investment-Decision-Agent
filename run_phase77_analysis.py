"""
Phase 7.7 — Cross-Company Investment Philosophy Validation
==========================================================
Runs the full investment decision pipeline on 4 archetypes:

  A: CSU.TO  — Constellation Software   (Excellent business, expensive valuation)
  B: CNR.TO  — Canadian National Railway (High quality, reasonable value + dividend)
  C: BCE.TO  — BCE Inc.                  (Cheap-looking but questionable)
  D: TOI.V   — Topicus.com              (Emerging company with potential moat)

Usage:
    python run_phase77_analysis.py                   # run all 4
    python run_phase77_analysis.py --ticker CSU.TO   # run one
    python run_phase77_analysis.py --counterfactual  # also run counterfactuals
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

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
    GrowthAssessment, RiskAssessment, RiskLevel, RiskItem, RiskType,
    BullBearAssessment, UnderstandabilityRating, Confidence,
)
from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
from analytics.decision.decision_synthesizer import make_investment_decision
from analytics.data_freshness import build_freshness_assessment

ANALYSIS_DATE = "2026-08-09"


# ============================================================================
# ARCHETYPE A — Constellation Software (CSU.TO)
# Excellent business, expensive valuation
# ============================================================================

def build_csu_metrics() -> CompanyFinancialMetrics:
    m = CompanyFinancialMetrics(
        ticker="CSU.TO",
        company_name="Constellation Software Inc.",
        exchange="TSX",
        currency="CAD",
        data_source="manual_demo",
        data_as_of_date="2025-09-01",
        retrieved_at=ANALYSIS_DATE,
        current_price=4_200.0,     # ~CAD 4,200 as of Aug 2026 (high-priced no-split stock)
        market_cap=93_000,         # ~$93B CAD
        pe_ratio=78.0,             # GAAP P/E (amortization-heavy)
    )
    m.revenue_growth = RevenueGrowthMetrics(
        annual_revenues={
            2019: 3_882, 2020: 4_399, 2021: 5_105,
            2022: 6_920, 2023: 8_692, 2024: 10_104,
        },
        cagr_3yr=20.8,
        cagr_5yr=21.1,
        annual_growth_rates={
            2020: 13.3, 2021: 16.1, 2022: 35.5,
            2023: 25.6, 2024: 16.2,
        },
        negative_growth_years=0,
        data_years_available=6,
        trend="Stable (acquisition-driven)",
        consistency_classification="Excellent",
        organic_vs_acquisition_note=(
            "Growth is primarily acquisition-driven — VMS (vertical market software) "
            "acquisitions. Organic growth ~5-8%. Acquisition pace has accelerated. "
            "Revenue recognition in USD; CAD figures at ~1.35 USD/CAD."
        ),
    )
    m.roic = ROICMetrics(
        annual_roic={
            2019: 22.4, 2020: 18.6, 2021: 24.3,
            2022: 19.8, 2023: 21.2, 2024: 20.1,
        },
        current=20.1,
        avg_3yr=20.4,
        avg_5yr=20.8,
        trend="Stable",
        classification="Excellent",
        moat_support_note=(
            "Consistently 20%+ ROIC over 10+ years is the strongest evidence of durable moat. "
            "VMS businesses generate recurring revenue with very high customer retention (>95%). "
            "ROIC is understated by GAAP due to acquisition amortization — cash-on-cash returns "
            "to acquired businesses are typically 20-30%+."
        ),
        calculation_note="Adjusted ROIC (adds back acquisition-related amortization).",
    )
    m.margins = MarginMetrics(
        net_margin=9.2,           # GAAP net margin (depressed by amortization)
        operating_margin=16.8,
        net_margin_history={
            2020: 8.1, 2021: 10.4, 2022: 9.8,
            2023: 10.1, 2024: 9.2,
        },
        net_margin_trend="Stable",
        margin_change_explanation=(
            "GAAP net margins appear modest due to amortization of acquired intangibles. "
            "Adjusted EBITDA margins ~25-30% are more meaningful. "
            "FCF margins on adjusted basis ~15-20% of revenue — strong."
        ),
    )
    m.free_cash_flow = FreeCashFlowMetrics(
        fcf_current=1_720,         # ~USD 1.72B = ~CAD 2.3B
        fcf_conversion_ratio=1.15, # Exceeds net income (amortization add-back)
        fcf_trend="Growing",
        fcf_consistency="Consistently positive and growing",
        recurring_negative_fcf=False,
        fcf_quality_note=(
            "FCF is the key metric for CSU — significantly exceeds GAAP earnings "
            "because acquisition amortization is a non-cash charge. "
            "FCF per share growing at ~15-20% p.a. over 10 years."
        ),
        annual_net_income={
            2020: 398, 2021: 543, 2022: 586,
            2023: 798, 2024: 930,
        },
    )
    m.debt = DebtMetrics(
        debt_to_assets_pct=42.0,
        interest_coverage=8.2,
        classification="Good",
        industry_context_note=(
            "Moderate leverage acceptable for acquisition-driven software company. "
            "CSU finances acquisitions partly with debt but FCF generation is strong "
            "enough to service and repay debt rapidly."
        ),
    )
    m.dividend = DividendMetrics(
        pays_dividend=True,
        current_yield_pct=0.3,          # ~$1 USD/qtr = ~$5.4 CAD/yr / $4,200 = ~0.13%
        annual_dividend_per_share=5.40,  # CAD
        payout_ratio_pct=4.5,            # Very small payout; CSU retains most FCF for acquisitions
        dividend_growth_5yr_cagr=0.0,   # Special dividends occasionally; base is stable
        years_of_dividend_history=12,
        dividend_cuts=0,
        sustainability_classification="Excellent",
        sustainability_note=(
            "Dividend is immaterial — CSU's primary capital return is through acquisitions "
            "generating future earnings growth. Payout ratio is 4-5% — almost all FCF "
            "is redeployed into acquisition machine. Dividend yield is ~0.3% — not an income stock."
        ),
    )
    m.earnings_quality = EarningsQualityMetrics(
        eps_trend="Growing",
        earnings_quality_note=(
            "GAAP earnings understated relative to economic earnings due to amortization. "
            "FCF per share is a better earnings proxy. FCF/share growing consistently."
        ),
    )
    m.strengths = [
        "20+ year track record of disciplined VMS acquisitions with 20%+ ROIC.",
        "Decentralized operating model preserves entrepreneurial culture at scale.",
        "Mark Leonard's capital allocation philosophy has been validated over two decades.",
        "Recurring software revenues create extremely visible, durable cash flows.",
    ]
    m.concerns = [
        "Acquisition pace must continue to sustain growth — acquisition multiples rising.",
        "Founder dependency: Mark Leonard's succession is not fully clear.",
        "GAAP earnings significantly understate economic earnings — requires analyst sophistication.",
    ]
    m.data_completeness_pct = 85.0
    m.data_quality_notes = [
        "Demo data — approximate figures from public sources as of Sep 2025.",
        "Revenue in USD; converted to CAD at ~1.35.",
        "ROIC adjusted for amortization; GAAP ROIC would be significantly lower.",
    ]
    return m


def build_csu_research() -> BusinessResearchAssessment:
    r = BusinessResearchAssessment(
        ticker="CSU.TO",
        company_name="Constellation Software Inc.",
        assessment_date="2025-09-01",
    )
    r.business_understanding = BusinessUnderstandingAssessment(
        what_it_does=(
            "Constellation Software acquires, manages, and builds vertical market software (VMS) businesses "
            "— software companies that serve specific, niche end-markets (transit, healthcare admin, "
            "municipal government, utilities, hospitality, etc.). "
            "CSU operates a large and growing portfolio of ~1,000+ software businesses globally."
        ),
        how_it_makes_money=(
            "Revenue is primarily recurring: maintenance/support contracts and SaaS subscriptions "
            "from customers who depend on CSU's software to run their operations. "
            "Switching costs are extraordinarily high in VMS — the software is often deeply embedded "
            "in the customer's workflows. CSU acquires these businesses at reasonable multiples, "
            "then improves their economics while maintaining low churn."
        ),
        understandability_rating=UnderstandabilityRating.SUFFICIENT,
        understandability_note=(
            "Business model is well-documented. The acquisition machine is complex but the "
            "underlying unit economics are clear. GAAP earnings require adjustment for "
            "amortization to understand economic reality."
        ),
        confidence=Confidence.HIGH,
    )
    r.moat_assessment = MoatAssessment(
        active_sources=["switching_costs", "network_effects", "intangible_assets"],
        overall_strength=MoatStrength.EXCEPTIONAL,
        overall_durability=MoatDurability.HIGH,
        trajectory=MoatTrajectory.STABLE,
        moat_summary=(
            "The moat is structural: VMS customers are deeply dependent on installed software "
            "and face very high switching costs (retraining, data migration, workflow disruption). "
            "CSU's decentralized operating model and acquisition expertise are additional advantages "
            "that cannot be replicated quickly. 20%+ ROIC sustained over 20+ years is the "
            "strongest empirical confirmation of moat durability."
        ),
        roic_consistency_note=(
            "ROIC consistently 20%+ for 15+ years. This is the strongest empirical evidence "
            "of a wide, durable moat available for any company."
        ),
        confidence=Confidence.HIGH,
    )
    r.industry_assessment = IndustryAssessment(
        industry_name="Vertical Market Software",
        classification=IndustryClassification.ATTRACTIVE,
        classification_reasoning=(
            "VMS is an excellent industry: high recurring revenues, high switching costs, "
            "fragmented market allowing continued acquisition, low capital intensity, "
            "resilient through economic cycles. The TAM is enormous and fragmented — "
            "thousands of VMS businesses exist globally."
        ),
        confidence=Confidence.HIGH,
    )
    r.management_assessment = ManagementAssessment(
        overall_rating=ManagementRating.STRONG,
        capital_allocation=(
            "Mark Leonard is widely considered among the best capital allocators in public markets. "
            "The Berkshire Hathaway of software — buys at good prices, operates frugally, "
            "decentralizes decision-making, retains talent. Track record is extraordinary."
        ),
        execution_track_record=(
            "20+ year track record of acquiring hundreds of VMS businesses at disciplined "
            "multiples and improving their economics. Internally, management letters are "
            "extraordinarily detailed and honest about challenges."
        ),
        confidence=Confidence.HIGH,
    )
    r.growth_assessment = GrowthAssessment(
        growth_sustainability_assessment=(
            "Growth is primarily acquisition-driven. The key risk is whether the acquisition "
            "machine can continue to find targets at acceptable multiples as CSU has grown "
            "much larger. CSU has responded by spinning off Topicus (Europe) and Jonas (other). "
            "Organic growth ~5-8% is modest but reliable."
        ),
        revenue_growth_quality=(
            "Acquisition-driven growth is of high quality — recurring SaaS/maintenance revenue. "
            "However, it requires continuous capital deployment. If acquisition multiples rise "
            "materially, FCF returns may compress."
        ),
        confidence=Confidence.MEDIUM,
    )
    r.risk_assessment = RiskAssessment(
        overall_level=RiskLevel.LOW,
        risk_summary=(
            "Structural risks are modest. The main risks are: (1) acquisition-machine slows "
            "as VMS market gets picked over; (2) founder succession risk; (3) a regulatory "
            "environment hostile to software acquisitions. None of these is imminent."
        ),
        business_risks=[
            RiskItem(
                risk_type=RiskType.STRUCTURAL,
                description="Acquisition machine depends on continued availability of VMS targets at acceptable multiples.",
                severity="Medium",
                likelihood="LOW",
                mitigants=["Expanding globally", "Spinning off subsidiaries for additional scale"],
            ),
        ],
    )
    r.bull_bear = BullBearAssessment(
        bull_case_narrative=(
            "CSU's acquisition machine continues to compound at 15-20% for 10+ more years. "
            "As global VMS market is vast and fragmented, the runway is long. Mark Leonard's "
            "capital allocation prowess is a durable advantage. FCF/share grows accordingly, "
            "eventually justifying current multiples."
        ),
        bear_case_narrative=(
            "At current multiples (~$4,200/share, ~80x GAAP earnings, ~35x FCF), CSU must "
            "maintain 15-20% compound FCF growth for 10+ years just to justify the price "
            "paid today. Any deceleration in acquisition pace, multiple expansion in acquisition "
            "targets, or operational stumble would meaningfully impair the investment thesis."
        ),
        thesis_breakers=[
            "If FCF/share growth decelerates below 10% for 3+ consecutive years.",
            "If acquisition multiples paid rise materially (>10x FCF), compressing returns.",
            "If Mark Leonard departs and the succession proves ineffective.",
        ],
        devils_advocate_research_note=(
            "The bull case requires near-perfect execution for a decade. "
            "The valuation leaves very little room for error. "
            "Even a great company can be a poor investment at the wrong price."
        ),
        confirmation_bias_check=(
            "Would revisit if FCF growth decelerates for 2+ years, acquisition pace slows, "
            "or a successor demonstrates materially different capital allocation philosophy."
        ),
        bear_case_confidence=Confidence.MEDIUM,
    )
    r.business_quality_interpretation = (
        "Exceptional business quality. The strongest evidence: 20%+ ROIC sustained over 20 years, "
        "recurring revenue model, and empirically demonstrated moat through customer retention. "
        "The question is entirely about valuation — is the quality priced in?"
    )
    r.key_investment_questions = [
        "At $4,200/share (~35x FCF), how many years of 15%+ FCF/share growth is already priced in?",
        "Can CSU sustain its acquisition machine at scale as it approaches $100B+ market cap?",
        "What is the succession plan and how does it affect the thesis?",
    ]
    r.research_completeness = {k: True for k in
                               ["business_understanding", "moat", "industry", "management",
                                "growth", "risk", "bull_bear"]}
    return r


def build_csu_valuation(price: float = 4_200.0) -> ValuationInput:
    """
    CSU is a software company — use P/FCF and normalized P/E as primary methods.
    DCF is secondary (very sensitive to terminal growth assumption).
    """
    return ValuationInput(
        ticker="CSU.TO",
        company_name="Constellation Software Inc.",
        company_type=CompanyType.INDUSTRIAL,   # Software but not HIGH_GROWTH (profitable, mature)
        valuation_date="2025-09-01",
        currency="CAD",
        fx_rate_to_cad=1.0,

        current_price=InputItem(
            name="current_price", value=price,
            source="Market", period=ANALYSIS_DATE,
            retrieval_date=ANALYSIS_DATE,
        ),
        shares_outstanding=InputItem(
            name="shares_outstanding", value=22.2,  # ~22.2M shares
            source="FY2024 annual report", period="FY2024",
        ),
        eps_ttm=InputItem(
            name="eps_ttm", value=53.80,   # CAD (GAAP; amortization-depressed)
            source="FY2024 annual report", period="FY2024",
            retrieval_date="2025-09-01",
        ),
        eps_history={
            "2020": 21.90, "2021": 29.90, "2022": 31.50,
            "2023": 42.10, "2024": 53.80,
        },
        # FCF per share is the better metric (non-GAAP adjusted)
        fcf_ttm=InputItem(
            name="fcf_per_share_adjusted", value=103.50,  # CAD adj FCF/share
            source="FY2024 — management adj FCF", period="FY2024",
        ),
        fcf_history={
            "2020": 47.20, "2021": 62.80, "2022": 75.40,
            "2023": 89.10, "2024": 103.50,
        },
        revenue=InputItem(
            name="revenue_usd", value=13_640.0,  # CAD converted
            source="FY2024 annual report (USD×1.35)", period="FY2024",
        ),
        ebitda=InputItem(
            name="adjusted_ebitda", value=2_860.0,  # CAD ~30% EBITDA margin
            source="FY2024 management disclosure", period="FY2024",
        ),
        ebit=InputItem(
            name="ebit", value=1_850.0,  # CAD (after D&A but before one-time items)
            source="FY2024", period="FY2024",
        ),
        total_debt=InputItem(
            name="total_debt", value=3_800.0,  # CAD
            source="FY2024 balance sheet", period="FY2024",
        ),
        cash_and_equivalents=InputItem(
            name="cash", value=980.0,  # CAD
            source="FY2024 balance sheet", period="FY2024",
        ),
        # Historical P/E for mean reversion
        pe_history={
            "2020": 58.0, "2021": 65.0, "2022": 55.0,
            "2023": 68.0, "2024": 78.0,
        },
        # No book value for software (intangibles dominate)
        book_value_per_share=None,
        # Peers — limited; Topicus is the closest pure-play
        peers=[
            PeerData(ticker="TOI.V",  name="Topicus.com",
                     pe_ratio=55.0, ev_ebitda=28.0, source="TSX-V",
                     similarity_note="Spun off from CSU; same model in Europe; smaller and earlier-stage"),
            PeerData(ticker="MSFT",   name="Microsoft",
                     pe_ratio=33.0, ev_ebitda=22.0, source="NASDAQ",
                     similarity_note="Software but very different scale and model"),
        ],
        dcf_revenue_growth_rate=16.0,   # Acquisition-driven compound growth
        moat_strength="EXCEPTIONAL",
        financial_quality_hint="EXCELLENT",
        analyst_eps_next_year=InputItem(
            name="analyst_adj_eps_fy2025", value=62.0,
            source="Analyst consensus FY2025E (adjusted)", period="FY2025E",
        ),
    )


# ============================================================================
# ARCHETYPE B — Canadian National Railway (CNR.TO)
# High quality, reasonable value, dividend + growth
# ============================================================================

def build_cnr_metrics() -> CompanyFinancialMetrics:
    m = CompanyFinancialMetrics(
        ticker="CNR.TO",
        company_name="Canadian National Railway Company",
        exchange="TSX",
        currency="CAD",
        data_source="manual_demo",
        data_as_of_date="2025-09-01",
        retrieved_at=ANALYSIS_DATE,
        current_price=160.0,      # CAD as of Aug 2026 (estimated)
        market_cap=78_000,        # ~$78B CAD
        pe_ratio=20.8,
    )
    m.revenue_growth = RevenueGrowthMetrics(
        annual_revenues={
            2019: 14_917, 2020: 13_819, 2021: 14_906,
            2022: 17_113, 2023: 16_806, 2024: 17_244,
        },
        cagr_3yr=5.0,
        cagr_5yr=4.5,
        annual_growth_rates={
            2020: -7.4, 2021: 7.9, 2022: 14.8,
            2023: -1.8, 2024: 2.6,
        },
        negative_growth_years=2,
        data_years_available=6,
        trend="Stable with cyclical dips",
        consistency_classification="Good",
        organic_vs_acquisition_note=(
            "Organic growth driven by volume, price increases, and mix shift. "
            "2020 dip due to COVID. 2023 modest decline due to labour disputes and slower macro."
        ),
    )
    m.roic = ROICMetrics(
        annual_roic={
            2019: 17.2, 2020: 14.1, 2021: 17.8,
            2022: 19.4, 2023: 16.2, 2024: 15.8,
        },
        current=15.8,
        avg_3yr=17.1,
        avg_5yr=16.7,
        trend="Stable",
        classification="Excellent",
        moat_support_note=(
            "ROIC consistently above 15% demonstrates durable competitive advantage. "
            "Rail networks are natural monopolies — cannot be replicated at any price. "
            "Operating ratio ~61% is among the best in North American rail."
        ),
        calculation_note="Standard ROIC on operating capital (excludes deferred tax).",
    )
    m.margins = MarginMetrics(
        net_margin=26.8,
        operating_margin=36.4,
        net_margin_history={
            2020: 24.1, 2021: 28.3, 2022: 29.1,
            2023: 26.2, 2024: 26.8,
        },
        net_margin_trend="Stable",
        margin_change_explanation=(
            "Operating ratio ~61% reflects excellent network efficiency. "
            "Margins slightly compressed in 2023 by labour costs and slower volumes. "
            "2024 recovering to normalized levels."
        ),
    )
    m.free_cash_flow = FreeCashFlowMetrics(
        fcf_current=3_840,
        fcf_conversion_ratio=0.88,
        fcf_trend="Stable",
        fcf_consistency="Consistently positive",
        recurring_negative_fcf=False,
        fcf_quality_note=(
            "FCF is high quality — recurring, capital-light relative to revenue after "
            "maintenance capex. Growth capex (capacity expansion) is discretionary. "
            "FCF supports buybacks and dividend comfortably."
        ),
        annual_net_income={
            2020: 3_331, 2021: 4_218, 2022: 4_970,
            2023: 4_406, 2024: 4_620,
        },
    )
    m.debt = DebtMetrics(
        debt_to_assets_pct=35.8,
        interest_coverage=9.4,
        classification="Strong",
        industry_context_note=(
            "Rail companies carry moderate debt to finance long-lived infrastructure assets. "
            "CNR's D/E of ~0.8x is conservative for the industry. "
            "Investment-grade credit rating (Moody's A2)."
        ),
    )
    m.dividend = DividendMetrics(
        pays_dividend=True,
        current_yield_pct=2.1,
        annual_dividend_per_share=3.38,
        payout_ratio_pct=38.0,
        fcf_payout_ratio_pct=24.5,
        dividend_growth_5yr_cagr=12.4,
        dividend_growth_3yr_cagr=9.8,
        annual_dividends={
            2020: 2.15, 2021: 2.46, 2022: 2.93,
            2023: 3.16, 2024: 3.38,
        },
        years_of_dividend_history=28,
        dividend_cuts=0,
        sustainability_classification="Excellent",
        sustainability_note=(
            "28-year consecutive dividend growth record with no cuts. "
            "Payout ratio 38% of earnings, 24% of FCF — ample coverage. "
            "Dividend growth ~9-12% annually aligns well with investor's income + growth objective. "
            "Yield of 2.1% is well within the 6% investigation threshold — not a yield trap."
        ),
    )
    m.earnings_quality = EarningsQualityMetrics(
        eps_trend="Growing",
        earnings_quality_note=(
            "High-quality earnings — predominantly cash-based revenue from freight tariffs. "
            "No material one-time items. Operating ratio is a clean, recurring measure."
        ),
    )
    m.strengths = [
        "Network monopoly — the only rail connecting Atlantic, Pacific, and Gulf coasts.",
        "15%+ ROIC for 10+ consecutive years — empirical moat confirmation.",
        "28-year dividend growth track record with 38% payout ratio (sustainable).",
        "Best-in-class operating ratio (~61%) reflects operating leverage advantage.",
    ]
    m.concerns = [
        "Revenue is cyclical — economic slowdowns reduce freight volumes.",
        "Labour disputes create periodic service disruptions and uncertainty.",
        "Regulatory risk: STB (US) and CTA (Canada) can impose operational requirements.",
    ]
    m.data_completeness_pct = 92.0
    m.data_quality_notes = [
        "Demo data — approximate figures from public sources as of Sep 2025.",
        "Fiscal year end: December.",
    ]
    return m


def build_cnr_research() -> BusinessResearchAssessment:
    r = BusinessResearchAssessment(
        ticker="CNR.TO",
        company_name="Canadian National Railway Company",
        assessment_date="2025-09-01",
    )
    r.business_understanding = BusinessUnderstandingAssessment(
        what_it_does=(
            "Canadian National Railway operates the only transcontinental rail network in North America, "
            "connecting the Atlantic, Pacific, and Gulf of Mexico coasts. CN handles bulk commodities "
            "(grain, coal, potash), intermodal (containers), petroleum products, forest products, and "
            "automotive goods across a ~33,000-route-mile network."
        ),
        how_it_makes_money=(
            "CN charges tariffs per tonne-mile for moving goods across its network. "
            "Revenue is driven by volume (carloads), mix (commodity type), length of haul, and pricing. "
            "Operating leverage is significant — fixed costs (infrastructure) are spread across "
            "growing volumes, allowing margin expansion as volumes increase."
        ),
        understandability_rating=UnderstandabilityRating.SUFFICIENT,
        understandability_note="Simple business model: move freight, charge tariffs. Economics are well-documented.",
        confidence=Confidence.HIGH,
    )
    r.moat_assessment = MoatAssessment(
        active_sources=["network_effects", "switching_costs", "intangible_assets"],
        overall_strength=MoatStrength.EXCEPTIONAL,
        overall_durability=MoatDurability.HIGH,
        trajectory=MoatTrajectory.STABLE,
        moat_summary=(
            "The moat is effectively permanent: the CN rail network cannot be replicated at any cost. "
            "Land acquisition, environmental approvals, and capital requirements make new rail "
            "construction economically impossible. Customers have very high switching costs — "
            "roads can't match rail economics for bulk, long-distance freight. "
            "Operating ratio consistently among the best 2-3 in North American rail."
        ),
        roic_consistency_note="ROIC 15%+ for 10+ years. One of the most consistent ROIC records in Canadian public markets.",
        confidence=Confidence.HIGH,
    )
    r.industry_assessment = IndustryAssessment(
        industry_name="Rail Freight",
        classification=IndustryClassification.ATTRACTIVE,
        classification_reasoning=(
            "Rail is an essential infrastructure industry with very high barriers to entry. "
            "Secular tailwinds: carbon-efficiency advantage over trucking, intermodal growth, "
            "near-shoring of North American supply chains. Pricing power is structurally supported."
        ),
        confidence=Confidence.HIGH,
    )
    r.management_assessment = ManagementAssessment(
        overall_rating=ManagementRating.STRONG,
        capital_allocation=(
            "CN allocates capital well: disciplined capex (15-17% of revenue for maintenance + growth), "
            "consistent buybacks (reducing share count ~2-3% annually), and sustainable 38% dividend payout. "
            "Hunter Harrison's precision railroading legacy is institutionalized."
        ),
        execution_track_record=(
            "Operating ratio improvement over 10+ years. Failed KCS acquisition (2021) was a setback "
            "but management pivoted efficiently. Labour dispute resolution (2023) was slower than ideal "
            "but ultimately resolved without sustained operational damage."
        ),
        confidence=Confidence.HIGH,
    )
    r.growth_assessment = GrowthAssessment(
        growth_sustainability_assessment=(
            "GDP-plus growth (rail pricing power + modest volume growth) is sustainable. "
            "Near-shoring of North American supply chains is a meaningful secular tailwind. "
            "Intermodal growth driven by truck-to-rail conversion continues. "
            "Long-term revenue growth of 4-6% annually is realistic."
        ),
        revenue_growth_quality="Organic, pricing-driven, with modest volume sensitivity to economic cycles.",
        confidence=Confidence.HIGH,
    )
    r.risk_assessment = RiskAssessment(
        overall_level=RiskLevel.LOW,
        risk_summary=(
            "Risk profile is low overall. Main risks are cyclical (volume dips in recession), "
            "labour (periodic disputes), and regulatory (pricing oversight). None are structural threats."
        ),
        business_risks=[
            RiskItem(
                risk_type=RiskType.TEMPORARY,
                description="Economic recession reduces freight volumes — revenue decline of 7-15% in severe recession.",
                severity="Medium",
                likelihood="LOW",
                mitigants=["Pricing power offsets some volume decline", "Cost flexibility in variable components"],
            ),
        ],
    )
    r.bull_bear = BullBearAssessment(
        bull_case_narrative=(
            "CN compounds earnings at 8-10% annually via GDP-plus pricing, volume growth, "
            "continued operating ratio improvement, and buybacks. Dividend grows 10%+ annually. "
            "Near-shoring tailwinds accelerate intermodal volumes. Over 10 years, CNR is a "
            "reliable compounder with durable competitive position and modest but steady income."
        ),
        bear_case_narrative=(
            "Extended economic slowdown reduces freight volumes 10-15%. Labour cost inflation "
            "compresses operating ratio gains. Regulatory scrutiny limits pricing power. "
            "Growth decelerates to 3-4% — still positive but may not justify current P/E of 20x."
        ),
        thesis_breakers=[
            "If operating ratio deteriorates above 68% for 2+ consecutive years (loss of efficiency leadership).",
            "If dividend is cut (would signal severe FCF stress — unlikely given current 24% FCF payout).",
        ],
        devils_advocate_research_note=(
            "Investigated competitive dynamics. Trucking is not a credible moat threat for "
            "long-haul bulk freight. Air freight is different segment. No new rail is being built."
        ),
        confirmation_bias_check=(
            "Would reassess if operating ratio rises structurally above 65%, if revenue "
            "growth decelerates below 2% for 3+ years, or if dividend policy changes materially."
        ),
        bear_case_confidence=Confidence.MEDIUM,
    )
    r.business_quality_interpretation = (
        "One of the highest-quality businesses in Canadian public markets. "
        "Permanent moat, excellent capital returns, reliable dividend growth, "
        "and management with a proven track record. "
        "The investment question is purely about valuation."
    )
    r.key_investment_questions = [
        "At current P/E of ~21x, what earnings growth rate is required to justify the price?",
        "How does a moderate economic slowdown affect the thesis?",
        "Is the 2.1% dividend yield + 9-12% dividend growth an adequate income + growth combination?",
    ]
    r.research_completeness = {k: True for k in
                               ["business_understanding", "moat", "industry", "management",
                                "growth", "risk", "bull_bear"]}
    return r


def build_cnr_valuation(price: float = 160.0) -> ValuationInput:
    return ValuationInput(
        ticker="CNR.TO",
        company_name="Canadian National Railway Company",
        company_type=CompanyType.INDUSTRIAL,
        valuation_date="2025-09-01",
        currency="CAD",
        fx_rate_to_cad=1.0,

        current_price=InputItem(
            name="current_price", value=price,
            source="Market", period=ANALYSIS_DATE,
            retrieval_date=ANALYSIS_DATE,
        ),
        shares_outstanding=InputItem(
            name="shares_outstanding", value=487.0,  # millions
            source="FY2024 annual report", period="FY2024",
        ),
        eps_ttm=InputItem(
            name="eps_ttm", value=7.70,
            source="FY2024 annual report", period="FY2024",
            retrieval_date="2025-09-01",
        ),
        eps_history={
            "2020": 6.85, "2021": 8.67, "2022": 10.20,
            "2023": 9.04, "2024": 7.70,
        },
        revenue=InputItem(
            name="revenue", value=17_244.0,
            source="FY2024 annual report", period="FY2024",
        ),
        revenue_history={
            "2020": 13_819, "2021": 14_906, "2022": 17_113,
            "2023": 16_806, "2024": 17_244,
        },
        ebitda=InputItem(
            name="ebitda", value=7_910.0,   # ~45.8% EBITDA margin
            source="FY2024 annual report", period="FY2024",
        ),
        ebit=InputItem(
            name="ebit", value=6_275.0,     # ~36.4% operating margin
            source="FY2024 annual report", period="FY2024",
        ),
        fcf_ttm=InputItem(
            name="fcf_ttm", value=3_840.0,
            source="FY2024 cash flow statement", period="FY2024",
        ),
        fcf_history={
            "2020": 2_980, "2021": 3_620, "2022": 4_150,
            "2023": 3_710, "2024": 3_840,
        },
        total_debt=InputItem(
            name="total_debt", value=17_200.0,
            source="FY2024 balance sheet", period="FY2024",
        ),
        cash_and_equivalents=InputItem(
            name="cash", value=680.0,
            source="FY2024 balance sheet", period="FY2024",
        ),
        book_value_per_share=InputItem(
            name="book_value_per_share", value=48.20,
            source="FY2024 balance sheet", period="FY2024",
        ),
        pe_history={
            "2020": 19.2, "2021": 21.8, "2022": 18.4,
            "2023": 19.7, "2024": 20.8,
        },
        peers=[
            PeerData(ticker="CP.TO",  name="Canadian Pacific Kansas City",
                     pe_ratio=22.1, ev_ebitda=18.2, source="TSX",
                     similarity_note="Direct peer; similar Canadian rail network"),
            PeerData(ticker="UNP",    name="Union Pacific",
                     pe_ratio=21.4, ev_ebitda=16.8, source="NYSE",
                     similarity_note="US Class 1 rail; comparable quality"),
            PeerData(ticker="NSC",    name="Norfolk Southern",
                     pe_ratio=19.8, ev_ebitda=15.1, source="NYSE",
                     similarity_note="US Class 1 rail; slightly lower quality"),
        ],
        dcf_revenue_growth_rate=5.0,
        moat_strength="EXCEPTIONAL",
        financial_quality_hint="EXCELLENT",
        analyst_eps_next_year=InputItem(
            name="analyst_eps_fy2025", value=8.40,
            source="Analyst consensus FY2025E", period="FY2025E",
        ),
    )


# ============================================================================
# ARCHETYPE C — BCE Inc. (BCE.TO)
# Cheap-looking but questionable quality
# ============================================================================

def build_bce_metrics() -> CompanyFinancialMetrics:
    m = CompanyFinancialMetrics(
        ticker="BCE.TO",
        company_name="BCE Inc.",
        exchange="TSX",
        currency="CAD",
        data_source="manual_demo",
        data_as_of_date="2025-09-01",
        retrieved_at=ANALYSIS_DATE,
        current_price=30.50,      # CAD (post-dividend-cut, depressed price)
        market_cap=21_600,        # ~$21.6B CAD
        pe_ratio=14.8,            # Appears low — but earnings declining
        ev_ebitda=6.8,
    )
    m.revenue_growth = RevenueGrowthMetrics(
        annual_revenues={
            2019: 23_964, 2020: 22_883, 2021: 23_449,
            2022: 24_193, 2023: 24_673, 2024: 23_600,  # Declining on media/wireline losses
        },
        cagr_3yr=-1.1,
        cagr_5yr=-0.3,
        annual_growth_rates={
            2020: -4.5, 2021: 2.5, 2022: 3.2,
            2023: 2.0,  2024: -4.3,
        },
        negative_growth_years=2,
        data_years_available=6,
        trend="Declining",
        consistency_classification="Watch",
        organic_vs_acquisition_note=(
            "Revenue decline driven by: cord-cutting in media (Bell Media), "
            "wireline voice/broadband subscriber losses to cable competitors (Rogers, Videotron), "
            "and macro pressure on enterprise spending. Wireless growth partially offsets."
        ),
    )
    m.roic = ROICMetrics(
        annual_roic={
            2019: 7.8, 2020: 6.2, 2021: 7.4,
            2022: 7.1, 2023: 6.4, 2024: 5.2,
        },
        current=5.2,
        avg_3yr=6.2,
        avg_5yr=6.9,
        trend="Declining",
        classification="Watch",
        moat_support_note=(
            "ROIC declining from already-modest levels. BCE's returns are well below "
            "a typical moat company's ROIC (>10%). The telecom model requires enormous "
            "recurring capex (fiber rollout) which depresses returns. "
            "ROIC below cost of capital is a warning sign."
        ),
        calculation_note="ROIC on total capital employed; capex-intensive nature depresses returns.",
    )
    m.margins = MarginMetrics(
        net_margin=10.2,
        operating_margin=19.8,
        net_margin_history={
            2020: 8.4, 2021: 11.2, 2022: 10.8,
            2023: 10.9, 2024: 10.2,
        },
        net_margin_trend="Declining",
        margin_change_explanation=(
            "EBITDA margins are respectable (~40%) but conversion to FCF is poor due to "
            "extremely high capex requirements. Fiber-to-the-home rollout requires billions "
            "annually. True FCF margins after capex are very thin."
        ),
    )
    m.free_cash_flow = FreeCashFlowMetrics(
        fcf_current=730,           # Very thin FCF after heavy capex
        fcf_conversion_ratio=0.30, # Only 30% of net income converts to FCF
        fcf_trend="Declining",
        fcf_consistency="Declining, thin",
        recurring_negative_fcf=False,
        fcf_quality_note=(
            "FCF is the critical concern. While EBITDA is ~$9.5B, maintenance + growth "
            "capex (~$3.9B) leaves thin FCF. Dividend cut was a direct consequence of "
            "FCF inadequacy. Pre-cut dividend required ~$3.3B annually vs ~$730M FCF — "
            "clearly unsustainable. Post-cut dividend ($1.75B) still consumes >2x FCF. "
            "Additional cuts or significant capex reduction would be required to achieve sustainability."
        ),
        annual_net_income={
            2020: 1_931, 2021: 2_621, 2022: 2_619,
            2023: 2_689, 2024: 2_407,
        },
    )
    m.debt = DebtMetrics(
        debt_to_assets_pct=68.4,
        interest_coverage=2.9,     # Thin interest coverage
        classification="Concern",
        industry_context_note=(
            "BCE carries $38-40B CAD of long-term debt — extremely elevated. "
            "Debt/EBITDA ~4x. Interest coverage of 2.9x is uncomfortably thin. "
            "High capex requirements mean debt reduction is very slow. "
            "This is not normal capital structure for a telecom — it is structurally concerning."
        ),
        debt_analysis_note=(
            "Net debt/EBITDA: ~4x. Bond market signals stress — BCE bonds have widened significantly. "
            "Refinancing risk as interest rates have risen — older low-rate debt must be rolled at higher rates."
        ),
    )
    m.dividend = DividendMetrics(
        pays_dividend=True,
        current_yield_pct=5.7,    # $1.75 / $30.50 — after the cut
        annual_dividend_per_share=1.75,  # Post-cut (Feb 2025): reduced from $3.99
        payout_ratio_pct=108.0,   # Still paying more than earned on FCF basis
        fcf_payout_ratio_pct=240.0,  # Dividend significantly exceeds FCF
        dividend_growth_5yr_cagr=-8.5,   # Negative — the cut
        dividend_growth_3yr_cagr=-15.2,
        annual_dividends={
            2020: 3.33, 2021: 3.50, 2022: 3.68,
            2023: 3.87, 2024: 3.99, 2025: 1.75,  # CUT in Feb 2025
        },
        years_of_dividend_history=15,
        dividend_cuts=1,
        sustainability_classification="Concern",
        sustainability_note=(
            "Dividend was cut 56% in February 2025 — from $3.99 to $1.75/share. "
            "Even at the reduced level, the payout still exceeds FCF by ~2.4x. "
            "Without a substantial improvement in FCF (via capex reduction or asset sales) "
            "or another dividend cut, the current dividend is not FCF-sustainable. "
            "Yield of 5.7% at reduced dividend is NOT a value opportunity — it reflects risk."
        ),
        high_yield_investigation_note=(
            "Dividend yield above 5% — INVESTIGATE per investment philosophy. "
            "Result of investigation: yield reflects investor repricing of dividend risk "
            "after the Feb 2025 cut. The elevated yield is a warning, not an opportunity."
        ),
    )
    m.earnings_quality = EarningsQualityMetrics(
        eps_trend="Declining",
        earnings_quality_note=(
            "Earnings quality is mixed: EBITDA is meaningful but large capex is not optional "
            "(network maintenance + competitive fiber rollout). "
            "True economic earnings (FCF) are materially below reported net income."
        ),
    )
    m.strengths = [
        "Large, diversified telecom incumbent with wireline, wireless, and media.",
        "Wireless segment growing and generating reasonable returns.",
        "Bell Media provides content assets (though under structural pressure).",
    ]
    m.concerns = [
        "FCF significantly below post-cut dividend — sustainability in question.",
        "Net debt/EBITDA ~4x — elevated leverage constrains strategic flexibility.",
        "Revenue declining on wireline and media — structural, not cyclical.",
        "ROIC declining below cost of capital — value destruction in progress.",
        "Dividend was cut once; further cuts cannot be ruled out.",
    ]
    m.data_completeness_pct = 87.0
    m.data_quality_notes = [
        "Demo data — approximate figures from public sources as of Sep 2025.",
        "Dividend cut (Feb 2025) is a key recent development that significantly alters the thesis.",
        "FCF calculations exclude spectrum payments (treated as capex).",
    ]
    return m


def build_bce_research() -> BusinessResearchAssessment:
    r = BusinessResearchAssessment(
        ticker="BCE.TO",
        company_name="BCE Inc.",
        assessment_date="2025-09-01",
    )
    r.business_understanding = BusinessUnderstandingAssessment(
        what_it_does=(
            "BCE Inc. is Canada's largest communications company, operating under the Bell brand. "
            "BCE operates three segments: Bell Wireless (mobile), Bell Wireline "
            "(broadband, business, legacy voice), and Bell Media (CTV, TSN, RDS, streaming). "
            "BCE serves ~22M+ wireless subscribers and is deploying fiber-to-the-home nationally."
        ),
        how_it_makes_money=(
            "Bell earns subscription revenue from wireless and broadband customers, "
            "and advertising revenue from Bell Media assets. "
            "The model is capital-intensive: BCE must continuously invest billions in spectrum "
            "licenses, cell towers, and fiber infrastructure to remain competitive."
        ),
        understandability_rating=UnderstandabilityRating.SUFFICIENT,
        understandability_note="Business model is clear; capital intensity and competitive dynamics are well-documented.",
        confidence=Confidence.HIGH,
    )
    r.moat_assessment = MoatAssessment(
        active_sources=["switching_costs"],  # Limited moat; oligopoly weakening
        overall_strength=MoatStrength.WEAK,
        overall_durability=MoatDurability.LOW,
        trajectory=MoatTrajectory.WEAKENING,
        moat_summary=(
            "BCE has a NARROW moat from Canadian telecom oligopoly structure (3-4 national carriers). "
            "However, the moat is eroding: (1) MVNO entrants (Videotron nationally, WIND legacy) "
            "are disrupting the oligopoly; (2) Rogers competition intensifying post-Shaw acquisition; "
            "(3) cord-cutting is structurally destroying the Bell Media business; "
            "(4) wireline broadband losing share to cable (Rogers, Videotron). "
            "The oligopoly moat is weaker than it appears."
        ),
        roic_consistency_note=(
            "ROIC declining to 5.2% — below the 10% minimum preference threshold. "
            "ROIC consistently below cost of capital is evidence of moat erosion, not moat presence."
        ),
        confidence=Confidence.HIGH,
    )
    r.industry_assessment = IndustryAssessment(
        industry_name="Canadian Telecommunications",
        classification=IndustryClassification.CHALLENGING,
        classification_reasoning=(
            "Canadian telecom is structurally challenged: "
            "(1) CRTC regulatory pressure on pricing; "
            "(2) Increasing competition from MVNOs and cable companies offering bundled services; "
            "(3) Cord-cutting destroying media revenues; "
            "(4) Massive capex requirements for 5G and fiber constrain FCF generation. "
            "Returns are sub-standard and improving slowly."
        ),
        confidence=Confidence.HIGH,
    )
    r.management_assessment = ManagementAssessment(
        overall_rating=ManagementRating.MIXED,
        capital_allocation=(
            "Capital allocation has been questionable: BCE prioritized dividend growth over "
            "FCF sustainability, ultimately leading to the Feb 2025 cut — a significant credibility event. "
            "Mirko Bibic (CEO since 2020) is working to restructure but faces structural headwinds."
        ),
        execution_track_record=(
            "Dividend cut is a negative execution event — management maintained the dividend "
            "at unsustainable levels for too long before cutting. "
            "Corus Entertainment acquisition (Bell Media) has been written down significantly. "
            "Fiber rollout is proceeding but FCF impact is severe."
        ),
        confidence=Confidence.HIGH,
    )
    r.growth_assessment = GrowthAssessment(
        growth_sustainability_assessment=(
            "Growth prospects are poor. Wireless is the only growing segment, but "
            "ARPU (average revenue per user) is under competitive pressure. "
            "Wireline is declining. Media is declining. "
            "Revenue growth is unlikely to exceed 1-2% even in an optimistic scenario."
        ),
        revenue_growth_quality="Low quality — driven by acquisition of subscribers at subsidized rates in competitive wireless market.",
        confidence=Confidence.HIGH,
    )
    r.risk_assessment = RiskAssessment(
        overall_level=RiskLevel.HIGH,
        risk_summary=(
            "BCE has multiple concurrent risks: structural decline in wireline/media, "
            "elevated leverage, FCF below dividend, and regulatory uncertainty. "
            "Risk level is HIGH — not because of a single event but because of the "
            "intersection of structural, financial, and competitive risks."
        ),
        business_risks=[
            RiskItem(
                risk_type=RiskType.STRUCTURAL,
                description="Wireline and media revenues declining structurally due to cord-cutting and cable competition.",
                severity="High",
                likelihood="HIGH",
                mitigants=["Fiber rollout may partially offset wireline losses", "Streaming pivot for Bell Media"],
            ),
            RiskItem(
                risk_type=RiskType.STRUCTURAL,
                description="Net debt/EBITDA ~4x constrains strategic flexibility and creates refinancing risk.",
                severity="High",
                likelihood="MEDIUM",
                mitigants=["Asset sales (real estate, towers) are possible", "Capex reduction over time"],
            ),
        ],
    )
    r.bull_bear = BullBearAssessment(
        bull_case_narrative=(
            "BCE stabilizes: fiber buildout completes (~2026-2027), reducing capex burden. "
            "Wireless growth continues. Media assets monetized or restructured. "
            "Debt reduced via asset sales. Reduced but sustainable dividend attracts income investors "
            "at a lower base, and the stock stabilizes/recovers from depressed levels."
        ),
        bear_case_narrative=(
            "BCE's structural problems accelerate: wireline and media decline faster than "
            "fiber and wireless can offset. FCF remains insufficient to service the post-cut dividend. "
            "Another dividend cut is required. Debt refinancing costs rise as rates remain elevated. "
            "Stock price continues to decline. The company requires capital restructuring."
        ),
        thesis_breakers=[
            "If FCF fails to recover above $1.5B by FY2026 (post capex normalization fails). → REDUCE or EXIT.",
            "If a second dividend cut occurs within 24 months. → EXIT — thesis is broken.",
            "If net debt/EBITDA rises above 4.5x. → REDUCE — debt spiral risk.",
        ],
        devils_advocate_research_note=(
            "The bull case requires: (1) fiber capex peaking and declining, (2) no second "
            "dividend cut, (3) wireless maintaining ARPU. All three are uncertain. "
            "The bear case does not require anything unusual — just continuation of current trends."
        ),
        confirmation_bias_check=(
            "The high yield is tempting but must not bias analysis. "
            "The yield reflects risk, not opportunity. Would reassess if FCF recovers "
            "materially and debt declines from current levels."
        ),
        bear_case_confidence=Confidence.HIGH,
    )
    r.business_quality_interpretation = (
        "BCE is a low-quality business in structural decline. "
        "The ROIC below cost of capital, declining revenue, thin FCF, elevated debt, "
        "and dividend cut collectively signal a value trap rather than a value opportunity. "
        "Cheapness alone is not a sufficient investment thesis."
    )
    r.key_investment_questions = [
        "When does BCE's capex peak and FCF materially recover?",
        "Can the post-cut dividend ($1.75) be sustained without further cuts?",
        "Is net debt/EBITDA at ~4x manageable, or does refinancing risk materialize?",
    ]
    r.research_completeness = {k: True for k in
                               ["business_understanding", "moat", "industry", "management",
                                "growth", "risk", "bull_bear"]}
    return r


def build_bce_valuation(price: float = 30.50) -> ValuationInput:
    return ValuationInput(
        ticker="BCE.TO",
        company_name="BCE Inc.",
        company_type=CompanyType.UTILITY,  # Utility-like regulated returns
        valuation_date="2025-09-01",
        currency="CAD",
        fx_rate_to_cad=1.0,

        current_price=InputItem(
            name="current_price", value=price,
            source="Market", period=ANALYSIS_DATE,
            retrieval_date=ANALYSIS_DATE,
        ),
        shares_outstanding=InputItem(
            name="shares_outstanding", value=908.0,   # millions
            source="FY2024 annual report", period="FY2024",
        ),
        eps_ttm=InputItem(
            name="eps_ttm", value=2.65,
            source="FY2024 annual report", period="FY2024",
            retrieval_date="2025-09-01",
        ),
        eps_history={
            "2020": 2.73, "2021": 2.89, "2022": 2.88,
            "2023": 2.96, "2024": 2.65,
        },
        revenue=InputItem(
            name="revenue", value=23_600.0,
            source="FY2024 annual report", period="FY2024",
        ),
        revenue_history={
            "2020": 22_883, "2021": 23_449, "2022": 24_193,
            "2023": 24_673, "2024": 23_600,
        },
        ebitda=InputItem(
            name="ebitda", value=9_393.0,   # ~39.8% margin
            source="FY2024 annual report", period="FY2024",
        ),
        ebit=InputItem(
            name="ebit", value=4_673.0,     # ~19.8% operating margin
            source="FY2024 annual report", period="FY2024",
        ),
        fcf_ttm=InputItem(
            name="fcf_ttm", value=730.0,    # Very thin after heavy capex
            source="FY2024 — after capex of ~$3.9B", period="FY2024",
        ),
        fcf_history={
            "2020": 1_890, "2021": 1_420, "2022": 1_100,
            "2023": 890,  "2024": 730,
        },
        total_debt=InputItem(
            name="total_debt", value=38_900.0,   # Extremely high
            source="FY2024 balance sheet", period="FY2024",
        ),
        cash_and_equivalents=InputItem(
            name="cash", value=980.0,
            source="FY2024 balance sheet", period="FY2024",
        ),
        book_value_per_share=InputItem(
            name="book_value_per_share", value=19.80,
            source="FY2024 balance sheet", period="FY2024",
        ),
        pe_history={
            "2020": 17.2, "2021": 18.4, "2022": 15.2,
            "2023": 14.1, "2024": 14.8,
        },
        peers=[
            PeerData(ticker="T.TO",    name="Telus Corporation",
                     pe_ratio=19.2, ev_ebitda=8.2, source="TSX",
                     similarity_note="Closest peer; similar structure but more conservative dividend policy"),
            PeerData(ticker="RCI-B.TO", name="Rogers Communications",
                     pe_ratio=15.8, ev_ebitda=7.4, source="TSX",
                     similarity_note="Post-Shaw acquisition; similar wireless exposure"),
        ],
        dcf_revenue_growth_rate=1.0,     # Low growth expectations
        moat_strength="NARROW",
        financial_quality_hint="WATCH",
        analyst_eps_next_year=InputItem(
            name="analyst_eps_fy2025", value=2.40,
            source="Analyst consensus FY2025E (declining)", period="FY2025E",
        ),
    )


# ============================================================================
# ARCHETYPE D — Topicus.com (TOI.V)
# Emerging company with potential moat
# ============================================================================

def build_toi_metrics() -> CompanyFinancialMetrics:
    m = CompanyFinancialMetrics(
        ticker="TOI.V",
        company_name="Topicus.com Inc.",
        exchange="TSX-V",
        currency="CAD",
        data_source="manual_demo",
        data_as_of_date="2025-09-01",
        retrieved_at=ANALYSIS_DATE,
        current_price=120.0,      # CAD (TOI.V on TSX Venture Exchange)
        market_cap=6_200,         # ~$6.2B CAD
        pe_ratio=42.0,

    )
    m.revenue_growth = RevenueGrowthMetrics(
        annual_revenues={
            # Revenue in EUR, converted ~1.45 to CAD
            2021: 720,   # First partial year as independent (Feb 2021 spin-off)
            2022: 1_032,
            2023: 1_298,
            2024: 1_560,
        },
        cagr_3yr=29.4,   # High but acquisition-driven
        cagr_5yr=None,   # Insufficient years as independent
        annual_growth_rates={
            2022: 43.3, 2023: 25.7, 2024: 20.2,
        },
        negative_growth_years=0,
        data_years_available=4,  # Only 4 years as independent company
        trend="Growing (acquisition-driven)",
        consistency_classification="Strong",
        organic_vs_acquisition_note=(
            "Growth is primarily acquisition-driven — VMS acquisitions in Europe "
            "(Netherlands, Belgium, Germany, Nordics). Organic growth ~5-8%. "
            "Revenue in EUR; CAD at ~1.45. Limited historical track record as independent entity."
        ),
    )
    m.roic = ROICMetrics(
        annual_roic={
            2022: 14.2, 2023: 16.8, 2024: 17.1,
        },
        current=17.1,
        avg_3yr=16.0,
        avg_5yr=None,   # Insufficient history
        trend="Growing",
        classification="Strong",
        moat_support_note=(
            "ROIC of 16-17% in only 3 years of consistent measurement is promising evidence "
            "of the VMS model's economics. However, the track record is short (4 years public). "
            "The parent company (CSU) demonstrates this model can sustain 20%+ ROIC, "
            "which provides credible forward evidence but is not a substitute for Topicus-specific track record."
        ),
        calculation_note="Adjusted for amortization. Short track record limits reliability.",
    )
    m.margins = MarginMetrics(
        net_margin=8.4,
        operating_margin=14.2,
        net_margin_history={
            2022: 6.8, 2023: 8.1, 2024: 8.4,
        },
        net_margin_trend="Improving",
        margin_change_explanation=(
            "Margins improving as acquired businesses are integrated and optimized. "
            "GAAP net margins depressed by acquisition amortization — similar to CSU. "
            "Adjusted FCF margins are higher (~12-15% of revenue)."
        ),
    )
    m.free_cash_flow = FreeCashFlowMetrics(
        fcf_current=187,           # CAD million
        fcf_conversion_ratio=0.85,
        fcf_trend="Growing",
        fcf_consistency="Positive and growing",
        recurring_negative_fcf=False,
        fcf_quality_note=(
            "FCF is positive and growing — strong signal for an emerging company. "
            "FCF significantly exceeds GAAP net income when amortization is added back. "
            "Capital allocation reinvestment into acquisitions is the primary use of FCF."
        ),
        annual_net_income={
            2022: 70, 2023: 105, 2024: 131,
        },
    )
    m.debt = DebtMetrics(
        debt_to_assets_pct=38.0,
        interest_coverage=6.2,
        classification="Good",
        industry_context_note=(
            "Moderate leverage for an acquisition-driven software company. "
            "Debt finances European VMS acquisitions. FCF generation is strong enough "
            "to service and reduce debt. No going-concern leverage concerns."
        ),
    )
    m.dividend = DividendMetrics(
        pays_dividend=False,
        current_yield_pct=0.0,
        annual_dividend_per_share=0.0,
        payout_ratio_pct=0.0,
        sustainability_classification="N/A",
        sustainability_note=(
            "No dividend — Topicus reinvests all FCF into VMS acquisitions. "
            "This is the correct capital allocation for a company in early growth phase "
            "where acquisition returns (20%+) significantly exceed dividend yield alternatives. "
            "Dividend absence is not a concern — it is the expected and correct behavior."
        ),
    )
    m.earnings_quality = EarningsQualityMetrics(
        eps_trend="Growing",
        earnings_quality_note=(
            "Earnings quality is high — recurring SaaS/maintenance revenues with very "
            "high customer retention. GAAP earnings understated vs economic earnings "
            "due to amortization. Positive FCF generation confirms real earnings."
        ),
    )
    m.strengths = [
        "Follows proven Constellation Software VMS model — with only 4 years of track record.",
        "ROIC of 16-17% in early years matches CSU's early-period returns.",
        "European VMS market is vast and fragmented — long acquisition runway.",
        "Mark Leonard and CSU provide governance, model, and talent pipeline.",
    ]
    m.concerns = [
        "Only 4 years of independent operating history — limited track record.",
        "Daan Dijkhuizen (CEO) unproven at this scale without direct CSU oversight.",
        "European VMS acquisition multiples rising — compressing returns potential.",
        "Liquidity is lower (TSX-V listing) — less analyst coverage than TSX main board.",
    ]
    m.data_completeness_pct = 72.0   # Emerging — intentionally lower
    m.data_quality_notes = [
        "Demo data — approximate figures from public sources as of Sep 2025.",
        "Revenue in EUR converted to CAD at ~1.45.",
        "Only 4 years of operating data as independent company — structural limitation.",
        "Track record too short to confirm moat durability by itself.",
    ]
    return m


def build_toi_research() -> BusinessResearchAssessment:
    r = BusinessResearchAssessment(
        ticker="TOI.V",
        company_name="Topicus.com Inc.",
        assessment_date="2025-09-01",
    )
    r.business_understanding = BusinessUnderstandingAssessment(
        what_it_does=(
            "Topicus.com acquires, manages, and builds vertical market software (VMS) businesses "
            "in Europe and beyond, following the Constellation Software playbook. "
            "Topicus was spun out of CSU in February 2021. "
            "Target markets include Dutch/European government, healthcare, education, and "
            "other verticals with high-retention mission-critical software."
        ),
        how_it_makes_money=(
            "Same model as CSU: acquire VMS businesses at reasonable multiples, "
            "retain management, improve unit economics, collect highly recurring maintenance "
            "and SaaS revenues from customers deeply embedded in the acquired software. "
            "High switching costs mean customer retention is 95%+."
        ),
        understandability_rating=UnderstandabilityRating.SUFFICIENT,
        understandability_note=(
            "Business model is well understood via CSU precedent. "
            "European VMS markets are less well-known but mechanics are the same. "
            "Risk: limited independent track record (4 years) means forward projections "
            "rely partially on CSU precedent rather than Topicus-specific evidence."
        ),
        confidence=Confidence.MEDIUM,  # Medium due to short track record
    )
    r.moat_assessment = MoatAssessment(
        active_sources=["switching_costs"],  # Potential; not yet proven at scale
        overall_strength=MoatStrength.STRONG,  # Based on model + early evidence
        overall_durability=MoatDurability.MEDIUM,  # Uncertain — insufficient track record
        trajectory=MoatTrajectory.STRENGTHENING,
        moat_summary=(
            "EVIDENCE OF MOAT: VMS switching costs are structural and validated by CSU over 20+ years. "
            "Topicus's early ROIC of 16-17% is consistent with the moat thesis. "
            "Customer retention in acquired businesses is reported as 95%+. "
            "\n"
            "LIMITS OF EVIDENCE: Topicus has only 4 years of operating history. "
            "The moat claim is partially based on inference from CSU's proven model "
            "rather than independent Topicus-specific confirmation. "
            "A 4-year track record is insufficient to confirm moat durability."
        ),
        roic_consistency_note=(
            "ROIC 14-17% over 3 years is promising but not long enough to confirm "
            "structural moat durability. CSU required 10+ years to establish high confidence."
        ),
        confidence=Confidence.MEDIUM,
    )
    r.industry_assessment = IndustryAssessment(
        industry_name="European Vertical Market Software",
        classification=IndustryClassification.ATTRACTIVE,
        classification_reasoning=(
            "European VMS market is large, fragmented, and under-consolidated. "
            "Similar structural attractiveness to North American VMS (high switching costs, "
            "fragmented competitive landscape, recurring revenues). "
            "CSU's success in North America is a positive reference point."
        ),
        confidence=Confidence.MEDIUM,
    )
    r.management_assessment = ManagementAssessment(
        overall_rating=ManagementRating.GOOD,
        capital_allocation=(
            "Capital allocation follows CSU playbook closely. "
            "Acquisition pace is disciplined. FCF is reinvested rather than paid as dividends. "
            "The CSU governance model (decentralized operating groups) is being replicated."
        ),
        execution_track_record=(
            "4-year track record is positive but short. "
            "ROIC improving from 14% to 17% suggests early execution is working. "
            "However, Daan Dijkhuizen's long-term track record at this scale is unproven."
        ),
        confidence=Confidence.MEDIUM,
    )
    r.growth_assessment = GrowthAssessment(
        growth_sustainability_assessment=(
            "Growth prospects are genuinely strong if the VMS model is applied successfully. "
            "European VMS market is enormous and fragmented — the runway could be as long "
            "as CSU's has been in North America. However, this is forward-looking. "
            "Revenue growth 20-30% should be achievable for several more years."
        ),
        revenue_growth_quality="Acquisition-driven; high quality (recurring SaaS) but requires continued capital deployment.",
        confidence=Confidence.MEDIUM,
    )
    r.risk_assessment = RiskAssessment(
        overall_level=RiskLevel.MODERATE,
        risk_summary=(
            "Main risks are: (1) limited track record means forward projections are speculative; "
            "(2) acquisition machine needs to find appropriate targets at reasonable multiples; "
            "(3) management team has not been stress-tested through a downturn; "
            "(4) European regulatory environment (M&A, software procurement) may differ from North America."
        ),
        business_risks=[
            RiskItem(
                risk_type=RiskType.UNCERTAIN,
                description="4-year track record is insufficient to confirm whether VMS model scales in Europe exactly as it did in North America.",
                severity="Medium",
                likelihood="MEDIUM",
                mitigants=["CSU provides model and governance", "Early ROIC metrics are positive"],
            ),
        ],
    )
    r.bull_bear = BullBearAssessment(
        bull_case_narrative=(
            "Topicus successfully replicates the CSU playbook in Europe. "
            "ROIC maintains 15-20%+ as acquisitions are disciplined. "
            "Revenue compounds at 15-20% for 10+ years as the European VMS market is large. "
            "FCF/share growth mirrors early CSU trajectory. "
            "In 5-7 years, Topicus becomes a significant mid-large cap compounder."
        ),
        bear_case_narrative=(
            "Topicus cannot find enough high-quality VMS targets at acceptable multiples "
            "as the European market gets competitive. ROIC compresses toward 10-12%. "
            "Without CSU's 20-year track record, the market re-rates the stock downward. "
            "Management team proves less capable than CSU's founding generation. "
            "The 4-year track record was insufficient evidence for the premium valuation."
        ),
        thesis_breakers=[
            "If ROIC declines below 12% for 2+ consecutive years — model not translating.",
            "If acquisition pace slows dramatically or multiples paid rise above 12x FCF consistently.",
            "If a major acquisition (>$200M) is written down significantly.",
        ],
        devils_advocate_research_note=(
            "The bull case requires making assumptions not fully supported by Topicus's own "
            "4-year track record. The CSU comparison is compelling but analogical. "
            "An emerging company should be valued with explicit evidence discount."
        ),
        confirmation_bias_check=(
            "Would downgrade conviction if ROIC plateaus below 14% for 2+ years, "
            "acquisition pace slows, or if Topicus departs from CSU's disciplined model."
        ),
        bear_case_confidence=Confidence.MEDIUM,
    )
    r.business_quality_interpretation = (
        "Topicus is a POTENTIAL high-quality business with promising early evidence "
        "of the VMS model working in Europe. The moat thesis is credible and backed "
        "by the CSU precedent, but Topicus's own track record is only 4 years — "
        "insufficient to reach HIGH confidence in moat durability independently. "
        "Confidence appropriately constrained by evidence limitations, not by pessimism."
    )
    r.key_investment_questions = [
        "Is 4 years of operating history sufficient to have HIGH confidence in the moat thesis?",
        "Can the VMS acquisition model sustain 15%+ ROIC in European markets?",
        "At ~$120/share (~42x GAAP earnings), how much is the market already pricing in?",
    ]
    r.research_completeness = {
        "business_understanding": True,
        "moat": True,
        "industry": True,
        "management": True,
        "growth": True,
        "risk": True,
        "bull_bear": True,
    }
    r.data_quality_notes = [
        "Only 4 years of independent operating history — structural evidence limitation.",
        "Moat confidence partially relies on CSU analogy, not purely Topicus-specific evidence.",
        "European VMS markets less well-studied than North American counterparts.",
    ]
    return r


def build_toi_valuation(price: float = 120.0) -> ValuationInput:
    return ValuationInput(
        ticker="TOI.V",
        company_name="Topicus.com Inc.",
        company_type=CompanyType.HIGH_GROWTH,
        valuation_date="2025-09-01",
        currency="CAD",
        fx_rate_to_cad=1.0,

        current_price=InputItem(
            name="current_price", value=price,
            source="Market", period=ANALYSIS_DATE,
            retrieval_date=ANALYSIS_DATE,
        ),
        shares_outstanding=InputItem(
            name="shares_outstanding", value=51.7,   # millions
            source="FY2024 annual report", period="FY2024",
        ),
        eps_ttm=InputItem(
            name="eps_ttm", value=2.53,
            source="FY2024 annual report", period="FY2024",
            retrieval_date="2025-09-01",
        ),
        eps_history={
            "2022": 1.35, "2023": 2.03, "2024": 2.53,
        },
        fcf_ttm=InputItem(
            name="fcf_per_share_adjusted", value=3.62,   # Adjusted FCF/share
            source="FY2024 — adj for amortization", period="FY2024",
        ),
        fcf_history={
            "2022": 1.80, "2023": 2.71, "2024": 3.62,
        },
        revenue=InputItem(
            name="revenue", value=1_560.0,   # CAD
            source="FY2024 annual report (EUR×1.45)", period="FY2024",
        ),
        revenue_history={
            "2022": 1_032, "2023": 1_298, "2024": 1_560,
        },
        ebitda=InputItem(
            name="adjusted_ebitda", value=358.0,   # ~23% EBITDA margin
            source="FY2024 management disclosure", period="FY2024",
        ),
        ebit=InputItem(
            name="ebit", value=222.0,
            source="FY2024", period="FY2024",
        ),
        total_debt=InputItem(
            name="total_debt", value=620.0,
            source="FY2024 balance sheet", period="FY2024",
        ),
        cash_and_equivalents=InputItem(
            name="cash", value=140.0,
            source="FY2024 balance sheet", period="FY2024",
        ),
        book_value_per_share=None,  # Not meaningful for acquisition-driven software
        pe_history={
            "2022": 38.0, "2023": 45.0, "2024": 42.0,
        },
        peers=[
            PeerData(ticker="CSU.TO", name="Constellation Software",
                     pe_ratio=78.0, ev_ebitda=32.0, source="TSX",
                     similarity_note="Parent/model company; much larger and more proven"),
        ],
        dcf_revenue_growth_rate=20.0,  # Acquisition-driven growth expectation
        moat_strength="STRONG",        # Potential moat — not yet EXCEPTIONAL
        financial_quality_hint="STRONG",
        analyst_eps_next_year=InputItem(
            name="analyst_eps_fy2025", value=3.10,
            source="Limited analyst coverage; estimate", period="FY2025E",
        ),
    )


# ============================================================================
# Run analysis for one company
# ============================================================================

def run_archetype(
    ticker: str,
    company_name: str,
    archetype_label: str,
    metrics_fn,
    research_fn,
    valuation_fn,
    is_financial_institution: bool = False,
    portfolio_arg: str = "none",
    price_override: float = None,
) -> dict:
    print(f"\n{'='*72}")
    print(f"  ARCHETYPE {archetype_label}: {ticker} — {company_name}")
    print(f"{'='*72}")

    metrics = metrics_fn()
    current_price = price_override or metrics.current_price
    price_currency = metrics.currency

    print(f"[1/5] Assessing financial quality...")
    fq = assess_financial_quality(metrics, is_financial_institution=is_financial_institution)
    print(f"     ✓ Quality: {fq.overall_quality_tier.value if hasattr(fq, 'overall_quality_tier') else 'assessed'} | Completeness: {fq.data_completeness_pct:.0f}%")

    print(f"[2/5] Loading business research...")
    research = research_fn()
    print(f"     ✓ Research loaded")

    print(f"[3/5] Running valuation engine...")
    val_input = valuation_fn(current_price)
    valuation = run_valuation(val_input)
    zone = valuation.accumulation_zone.zone.value if valuation and valuation.accumulation_zone else "N/A"
    fv = valuation.fair_value_range.base if valuation and valuation.fair_value_range else "N/A"
    print(f"     ✓ Valuation: zone={zone} | base fair value={fv}")

    print(f"[4/5] Portfolio context ({portfolio_arg})...")
    if portfolio_arg.lower() in ("none", "new"):
        portfolio_ctx = None
        print(f"     ✓ New position (no portfolio context)")
    else:
        pct = float(portfolio_arg.rstrip("%"))
        portfolio_ctx = WeightOnlyPortfolioContext(ticker=ticker, portfolio_weight_pct=pct)
        print(f"     ✓ Weight-only: {pct}% existing")

    print(f"[5/5] Running decision engine...")
    data_date = metrics.data_as_of_date or "2025-09-01"
    freshness = build_freshness_assessment(
        analysis_date=ANALYSIS_DATE,
        price_date=ANALYSIS_DATE,
        financial_statements_period="FY2024",
        financial_statements_date=data_date,
        earnings_period="H1 FY2025",
        earnings_date=data_date,
        research_date=data_date,
        valuation_date=data_date,
    )

    decision = make_investment_decision(
        ticker=ticker,
        company_name=company_name,
        analysis_date=ANALYSIS_DATE,
        financial_quality=fq,
        research=research,
        valuation=valuation,
        portfolio_ctx=portfolio_ctx,
        current_price=current_price,
        price_currency=price_currency,
        price_date=ANALYSIS_DATE,
        freshness=freshness,
    )
    print(f"     ✓ Decision: {decision.action.value} | Confidence: {decision.decision_confidence.value}")
    print(f"       BQ={decision.business_quality_label} | VA={decision.valuation_attractiveness_label} | IA={decision.investment_attractiveness_label}")

    gate5 = next((g for g in decision.gate_results if g.gate_number == 5), None)
    adv = gate5.adversarial_risk if gate5 else "N/A"
    print(f"       AdversarialRisk: {adv} | Breakers: {len(decision.thesis_breakers)}")

    return {
        "ticker": ticker,
        "archetype": archetype_label,
        "decision": decision,
        "valuation": valuation,
        "fq": fq,
        "adversarial_risk": adv,
    }


# ============================================================================
# Counterfactual runner
# ============================================================================

def run_counterfactual(label, ticker, company_name, metrics_fn, research_fn, valuation_fn,
                       price_pct_change=None, research_override=None,
                       is_financial_institution=False):
    metrics = metrics_fn()
    fq = assess_financial_quality(metrics, is_financial_institution=is_financial_institution)
    research = research_override() if research_override else research_fn()
    base_price = metrics.current_price

    if price_pct_change is not None:
        new_price = base_price * (1 + price_pct_change / 100.0)
    else:
        new_price = base_price

    val_input = valuation_fn(new_price)
    valuation = run_valuation(val_input)
    zone = valuation.accumulation_zone.zone.value if valuation and valuation.accumulation_zone else "N/A"

    portfolio_ctx = WeightOnlyPortfolioContext(ticker=ticker, portfolio_weight_pct=5.0)
    freshness = build_freshness_assessment(
        analysis_date=ANALYSIS_DATE, price_date=ANALYSIS_DATE,
        financial_statements_period="FY2024",
        financial_statements_date=metrics.data_as_of_date or "2025-09-01",
    )
    decision = make_investment_decision(
        ticker=ticker, company_name=company_name,
        analysis_date=ANALYSIS_DATE,
        financial_quality=fq, research=research, valuation=valuation,
        portfolio_ctx=portfolio_ctx, current_price=new_price,
        freshness=freshness,
    )
    gate5 = next((g for g in decision.gate_results if g.gate_number == 5), None)
    adv = gate5.adversarial_risk if gate5 else "N/A"
    print(f"  CF [{label}]: {decision.action.value} | conf={decision.decision_confidence.value} | zone={zone} | adv={adv} | price={new_price:.0f}")
    return decision


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default=None)
    parser.add_argument("--counterfactual", action="store_true")
    args = parser.parse_args()

    ARCHETYPES = [
        dict(
            ticker="CSU.TO", company_name="Constellation Software Inc.",
            archetype_label="A",
            metrics_fn=build_csu_metrics,
            research_fn=build_csu_research,
            valuation_fn=build_csu_valuation,
            portfolio_arg="new",   # Testing as new position
        ),
        dict(
            ticker="CNR.TO", company_name="Canadian National Railway Company",
            archetype_label="B",
            metrics_fn=build_cnr_metrics,
            research_fn=build_cnr_research,
            valuation_fn=build_cnr_valuation,
            portfolio_arg="new",   # Testing as new position
        ),
        dict(
            ticker="BCE.TO", company_name="BCE Inc.",
            archetype_label="C",
            metrics_fn=build_bce_metrics,
            research_fn=build_bce_research,
            valuation_fn=build_bce_valuation,
            portfolio_arg="new",   # Testing as new position
        ),
        dict(
            ticker="TOI.V",  company_name="Topicus.com Inc.",
            archetype_label="D",
            metrics_fn=build_toi_metrics,
            research_fn=build_toi_research,
            valuation_fn=build_toi_valuation,
            portfolio_arg="new",   # Testing as new position
        ),
    ]

    if args.ticker:
        to_run = [a for a in ARCHETYPES if a["ticker"].upper() == args.ticker.upper()]
        if not to_run:
            print(f"Unknown ticker {args.ticker}. Available: {[a['ticker'] for a in ARCHETYPES]}")
            return
    else:
        to_run = ARCHETYPES

    results = {}
    for cfg in to_run:
        r = run_archetype(**cfg)
        results[cfg["ticker"]] = r

    # Summary table
    print(f"\n{'='*72}")
    print("  CROSS-COMPANY SUMMARY")
    print(f"{'='*72}")
    print(f"  {'Ticker':<10} {'Arch':<5} {'Action':<10} {'Conf':<8} {'BQ':<12} {'VA':<12} {'IA':<12} {'Adv':<10}")
    print(f"  {'-'*80}")
    for tk, r in results.items():
        d = r["decision"]
        print(f"  {tk:<10} {r['archetype']:<5} {d.action.value:<10} {d.decision_confidence.value:<8} "
              f"{d.business_quality_label:<12} {d.valuation_attractiveness_label:<12} "
              f"{d.investment_attractiveness_label:<12} {r['adversarial_risk']:<10}")

    if args.counterfactual and results:
        print(f"\n{'='*72}")
        print("  COUNTERFACTUAL ANALYSIS")
        print(f"{'='*72}")

        # A: CSU -30% price
        print("\n  Archetype A (CSU.TO) — price -30%:")
        run_counterfactual("CSU -30%", "CSU.TO", "Constellation Software",
                           build_csu_metrics, build_csu_research, build_csu_valuation,
                           price_pct_change=-30)

        # B: CNR -20% price
        print("\n  Archetype B (CNR.TO) — price -20%:")
        run_counterfactual("CNR -20%", "CNR.TO", "Canadian National Railway",
                           build_cnr_metrics, build_cnr_research, build_cnr_valuation,
                           price_pct_change=-20)

        # B: CNR +30% price
        print("\n  Archetype B (CNR.TO) — price +30%:")
        run_counterfactual("CNR +30%", "CNR.TO", "Canadian National Railway",
                           build_cnr_metrics, build_cnr_research, build_cnr_valuation,
                           price_pct_change=+30)

        # C: BCE — thesis resolves (FCF recovers, 1 breaker only)
        def bce_resolved():
            r = build_bce_research()
            r.bull_bear.thesis_breakers = [
                "If revenue decline accelerates beyond -5% annually."
            ]
            return r
        print("\n  Archetype C (BCE.TO) — thesis partially resolves (1 breaker):")
        run_counterfactual("BCE resolved", "BCE.TO", "BCE Inc.",
                           build_bce_metrics, bce_resolved, build_bce_valuation)

        # D: TOI - ROIC collapses (thesis break)
        def toi_deteriorated():
            r = build_toi_research()
            r.bull_bear.thesis_breakers = [
                "ROIC declined below 12% for 2 consecutive years — model not translating.",
                "Acquisition pace slowed; multiples paid rising above 12x FCF.",
                "CEO departure; governance uncertainty without CSU oversight.",
                "Major acquisition ($250M) required material write-down.",
            ]
            return r
        print("\n  Archetype D (TOI.V) — ROIC collapses, multiple thesis breaks:")
        run_counterfactual("TOI deteriorated", "TOI.V", "Topicus.com",
                           build_toi_metrics, toi_deteriorated, build_toi_valuation)


if __name__ == "__main__":
    main()
