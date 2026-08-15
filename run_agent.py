"""
run_agent.py — Phase 9.1 End-to-End Research & Decision Pipeline
=================================================================
Interactive Investment Decision Agent.

Usage:
    python run_agent.py --ticker CNR.TO            # uses bundled CNR.TO demo data
    python run_agent.py --ticker CNQ.TO            # live yfinance fetch
    python run_agent.py --ticker AAPL              # live yfinance fetch
    python run_agent.py --ticker CNR.TO --weight 5.0   # with portfolio weight
    python run_agent.py --ticker CNR.TO --new-position  # ignore portfolio

Ticker routing:
  CNR.TO → rich pre-built demo data (always works, no network required)
  Any other ticker → live yfinance fetch via the existing ingestion pipeline
                     (requires: pip install yfinance; network access)

When live data is unavailable or the ticker is invalid, the agent emits:
    CANNOT_COMPLETE_LIVE_ANALYSIS
and exits without producing an investment action.

When live data is available but no ANTHROPIC_API_KEY is set, the pipeline
uses the quantitative fallback executor and emits:
    WAIT_INSUFFICIENT_EVIDENCE
This is the correct output — Gate 1 requires qualitative business research.

When ANTHROPIC_API_KEY is set, the pipeline uses AnthropicResearcher to
perform live qualitative research via the Anthropic API.  Gate 1 will pass
only if the model returns sufficient business understanding evidence.

Portfolio privacy:
  --weight accepts a portfolio weight % only.
  Shares, average cost, account value, and other holdings are never requested.
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.agent.investment_agent import InvestmentAgent
from analytics.agent.data_loader import load_ticker, describe_load_result, CANNOT_COMPLETE
from analytics.agent.research_orchestrator import ResearchOrchestrator, quantitative_executor
from analytics.agent.valuation_builder import build_valuation_input
from analytics.data_freshness import build_freshness_assessment
from analytics.valuation.valuation_synthesizer import run_valuation

# Phase 9.1 — live Anthropic researcher (optional; requires ANTHROPIC_API_KEY)
try:
    from analytics.agent.anthropic_researcher import make_anthropic_researcher
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    make_anthropic_researcher = None  # type: ignore

ANALYSIS_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ── CNR.TO demo imports ───────────────────────────────────────────────────────
# These are only used when --ticker CNR.TO is requested.
# No other ticker has pre-built demo data — any addition would violate req. 3.

from analytics.financial_quality.quality_engine import assess_financial_quality
from analytics.financial_quality.financial_metrics_model import (
    CompanyFinancialMetrics,
    RevenueGrowthMetrics, ROICMetrics, MarginMetrics, FreeCashFlowMetrics,
    DebtMetrics, DividendMetrics, EarningsQualityMetrics,
)
from analytics.valuation.valuation_models import (
    ValuationInput, CompanyType, InputItem, PeerData,
)
# Note: run_valuation already imported above (shared between CNR demo and live path)
from analytics.business_research.research_models import (
    BusinessResearchAssessment, BusinessUnderstandingAssessment,
    MoatAssessment, MoatStrength, MoatDurability, MoatTrajectory,
    IndustryAssessment, IndustryClassification,
    ManagementAssessment, ManagementRating,
    GrowthAssessment, RiskAssessment, RiskLevel, RiskItem, RiskType,
    BullBearAssessment, UnderstandabilityRating, Confidence,
)

# ─────────────────────────────────────────────────────────────────────────────
# CNR.TO pre-built demo data
# ─────────────────────────────────────────────────────────────────────────────

_CNR_DEMO_TICKER = "CNR.TO"


def _is_cnr_demo(ticker: str) -> bool:
    return ticker.upper() == _CNR_DEMO_TICKER


def _build_cnr_metrics() -> CompanyFinancialMetrics:
    m = CompanyFinancialMetrics(
        ticker="CNR.TO",
        company_name="Canadian National Railway Company",
        exchange="TSX", currency="CAD",
        data_source="manual_demo",
        data_as_of_date="2025-09-01",
        retrieved_at=ANALYSIS_DATE,
        current_price=160.0, market_cap=78_000, pe_ratio=20.8,
    )
    m.revenue_growth = RevenueGrowthMetrics(
        annual_revenues={2019: 14_917, 2020: 13_819, 2021: 14_906,
                         2022: 17_113, 2023: 16_806, 2024: 17_244},
        cagr_3yr=5.0, cagr_5yr=4.5,
        annual_growth_rates={2020: -7.4, 2021: 7.9, 2022: 14.8, 2023: -1.8, 2024: 2.6},
        negative_growth_years=2, data_years_available=6,
        trend="Stable with cyclical dips", consistency_classification="Good",
    )
    m.roic = ROICMetrics(
        annual_roic={2019: 17.2, 2020: 14.1, 2021: 17.8, 2022: 19.4, 2023: 16.2, 2024: 15.8},
        current=15.8, avg_3yr=17.1, avg_5yr=16.7,
        trend="Stable", classification="Excellent",
        moat_support_note="ROIC consistently above 15% — natural monopoly network.",
    )
    m.margins = MarginMetrics(
        net_margin=26.8, operating_margin=36.4,
        net_margin_history={2020: 24.1, 2021: 28.3, 2022: 29.1, 2023: 26.2, 2024: 26.8},
        net_margin_trend="Stable",
    )
    m.free_cash_flow = FreeCashFlowMetrics(
        fcf_current=3_840, fcf_conversion_ratio=0.88,
        fcf_trend="Stable", fcf_consistency="Consistently positive",
        recurring_negative_fcf=False,
        annual_net_income={2020: 3_331, 2021: 4_218, 2022: 4_970, 2023: 4_406, 2024: 4_620},
    )
    m.debt = DebtMetrics(
        debt_to_assets_pct=35.8, debt_trend="Stable",
        interest_coverage=9.2,
        classification="Moderate — acceptable for capital-intensive rail",
    )
    m.dividend = DividendMetrics(
        pays_dividend=True, current_yield_pct=2.1,
        payout_ratio_pct=42.0, years_of_dividend_history=28,
        sustainability_note="Strong — FCF coverage 2.1x",
    )
    m.earnings_quality = EarningsQualityMetrics(
        earnings_quality_note="High-quality earnings — minimal accruals, strong FCF conversion.",
        revenue_vs_fcf_divergence=False,
    )
    m.strengths = [
        "ROIC consistently 15–19% — well above cost of capital.",
        "Natural monopoly rail network — essentially irreplaceable infrastructure.",
        "28-year consecutive dividend growth track record.",
        "Operating ratio ~61% among best in North American rail.",
    ]
    m.concerns = [
        "Revenue cyclicality — sensitive to freight volumes and macro conditions.",
        "Labour dispute risk (2023 strike illustrates vulnerability).",
    ]
    m.data_completeness_pct = 97.0
    return m


def _build_cnr_research() -> BusinessResearchAssessment:
    r = BusinessResearchAssessment(
        ticker="CNR.TO",
        company_name="Canadian National Railway Company",
        assessment_date=ANALYSIS_DATE,
    )
    r.business_understanding = BusinessUnderstandingAssessment(
        what_it_does="Operates the only transcontinental Class 1 railroad in North America.",
        how_it_makes_money="Earns freight revenue by moving bulk commodities and intermodal cargo.",
        understandability_rating=UnderstandabilityRating.SUFFICIENT,
        understandability_note="Business model is straightforward — move freight, charge tariffs.",
        confidence=Confidence.HIGH,
    )
    r.moat_assessment = MoatAssessment(
        active_sources=["infrastructure_asset", "switching_costs", "network_effects"],
        overall_strength=MoatStrength.STRONG,
        overall_durability=MoatDurability.HIGH,
        trajectory=MoatTrajectory.STABLE,
        moat_summary="Rail network is a natural monopoly — cannot be replicated at any price.",
        roic_consistency_note="ROIC 15–19% over 6 years confirms moat is real and durable.",
        confidence=Confidence.HIGH,
    )
    r.industry_assessment = IndustryAssessment(
        industry_name="Class 1 Rail Freight",
        classification=IndustryClassification.ATTRACTIVE,
        classification_reasoning="Essential infrastructure with high barriers to entry.",
        confidence=Confidence.HIGH,
    )
    r.management_assessment = ManagementAssessment(
        overall_rating=ManagementRating.STRONG,
        capital_allocation="Disciplined capital allocation — buybacks, dividend growth, capex balanced.",
        execution_track_record="Consistent OR improvement over a decade.",
        confidence=Confidence.HIGH,
    )
    r.growth_assessment = GrowthAssessment(
        growth_sustainability_assessment="Modest but durable organic growth. GDP+ as trade recovers.",
        revenue_growth_quality="Organic, volume- and price-driven. Not acquisition-dependent.",
        confidence=Confidence.MEDIUM,
    )
    r.risk_assessment = RiskAssessment(
        overall_level=RiskLevel.MODERATE,
        risk_summary="Moderate macro and regulatory risk. No structural competitive threat identified.",
        business_risks=[
            RiskItem(
                description="Labour dispute risk — 2023 strike showed network vulnerability.",
                risk_type=RiskType.UNCERTAIN,
                severity="Moderate", likelihood="Low",
            ),
        ],
    )
    r.bull_bear = BullBearAssessment(
        bull_case_narrative="Volume recovery + pricing power + buybacks → 10–12% EPS CAGR.",
        bear_case_narrative="Macro recession reduces freight volumes 10–15%; FCF compresses.",
        thesis_breakers=[
            "Sustained traffic-loss to trucking due to infrastructure shift.",
            "Regulatory rate caps that materially impair returns.",
            "ROIC declining below 12% for 3+ consecutive years.",
        ],
        devils_advocate_research_note="Bears point to cyclicality and labour risk — real but cyclical.",
        confirmation_bias_check="Would re-examine if ROIC < 12% for 3 consecutive years.",
        bear_case_confidence=Confidence.MEDIUM,
    )
    r.business_quality_interpretation = (
        "High-quality business — durable natural monopoly with strong FCF and 28-year dividend growth."
    )
    r.research_completeness = {k: True for k in
                               ["business_understanding", "moat", "industry", "management",
                                "growth", "risk", "bull_bear"]}
    return r


def _build_cnr_valuation(price: float = 160.0):
    inp = ValuationInput(
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
            name="shares_outstanding", value=487.0,
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
            name="ebitda", value=7_910.0,
            source="FY2024 annual report", period="FY2024",
        ),
        ebit=InputItem(
            name="ebit", value=6_275.0,
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
            PeerData(ticker="CP.TO", name="Canadian Pacific Kansas City",
                     pe_ratio=22.1, ev_ebitda=18.2, source="TSX",
                     similarity_note="Direct peer; similar Canadian rail network"),
            PeerData(ticker="UNP",   name="Union Pacific",
                     pe_ratio=21.4, ev_ebitda=16.8, source="NYSE",
                     similarity_note="US Class 1 rail; comparable quality"),
            PeerData(ticker="NSC",   name="Norfolk Southern",
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
    return run_valuation(inp)


def _load_cnr_demo(price: float, price_date: str):
    """Return (fq, research, valuation, freshness, company_name) for CNR.TO demo."""
    metrics   = _build_cnr_metrics()
    fq        = assess_financial_quality(metrics)
    research  = _build_cnr_research()
    valuation = _build_cnr_valuation(price=price)
    freshness = build_freshness_assessment(
        analysis_date=ANALYSIS_DATE,
        price_date=price_date,
        financial_statements_date="2025-12-31",
        research_date="2026-07-01",
    )
    return fq, research, valuation, freshness, "Canadian National Railway Company"


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Investment Decision Agent — interactive REPL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--ticker",       default="CNR.TO", metavar="TICKER",
                        help="Ticker to analyze (default: CNR.TO)")
    parser.add_argument("--weight",       type=float, metavar="PCT",
                        help="Portfolio weight %% for existing position (e.g. 5.0)")
    parser.add_argument("--new-position", action="store_true",
                        help="Treat as a new position — ignore any --weight")
    parser.add_argument("--price",        type=float, default=None,
                        help="Override current price (CNR.TO demo only; default 160.0)")
    parser.add_argument("--price-date",   default=ANALYSIS_DATE,
                        help="ISO date of the price (default: today)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Force yfinance re-fetch, ignoring local cache")
    args = parser.parse_args()

    ticker = args.ticker.upper()

    print("\n" + "═" * 64)
    print(f"  Investment Decision Agent — Phase 9.1")
    print(f"  Ticker: {ticker}")
    print("═" * 64)

    # Phase 9.6: FCF chain — only populated on the live-fetch path.
    _fcf_raw = None
    _fcf_shr = None

    # ── Route: CNR.TO demo or live fetch ────────────────────────────────────
    if _is_cnr_demo(ticker):
        price = args.price if args.price is not None else 160.0
        print(f"  Using pre-built CNR.TO demo data (price: ${price:.2f} CAD)")
        print("─" * 64)
        fq, research, valuation, freshness, company_name = _load_cnr_demo(
            price=price, price_date=args.price_date
        )
        current_price   = price
        price_currency  = "CAD"

    else:
        print(f"  Fetching live data via yfinance…")
        print("─" * 64)

        load_result = load_ticker(
            ticker=ticker,
            analysis_date=ANALYSIS_DATE,
        )

        if not load_result.ok:
            # Fetch failed — print the reason and exit cleanly
            print(load_result.cannot_complete_reason)
            sys.exit(1)

        print(describe_load_result(load_result))
        print()

        fq              = load_result.financial_quality
        freshness       = load_result.freshness
        company_name    = load_result.company_name
        current_price   = load_result.current_price
        price_currency  = load_result.price_currency

        # ── Phase 9.1: Research Executor selection ─────────────────────────
        # Priority: AnthropicResearcher (if API key available) → quantitative fallback.
        # The quantitative fallback always returns None for qualitative steps,
        # so Gate 1 will produce WAIT_INSUFFICIENT_EVIDENCE in that case.
        _api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if _ANTHROPIC_AVAILABLE and _api_key:
            _researcher = make_anthropic_researcher(api_key=_api_key)
            if _researcher is not None:
                research_executor = _researcher
                print("  Using AnthropicResearcher for qualitative research (Phase 9.1)")
            else:
                research_executor = quantitative_executor
                print("  AnthropicResearcher unavailable — using quantitative fallback")
        else:
            research_executor = quantitative_executor
            if not _api_key:
                print("  ANTHROPIC_API_KEY not set — using quantitative fallback")
                print("  (set ANTHROPIC_API_KEY to enable live qualitative research)")

        orchestrator = ResearchOrchestrator(research_executor=research_executor)
        research = orchestrator.build_assessment(
            ticker=ticker,
            company_name=company_name,
            metrics=load_result.metrics,
            analysis_date=ANALYSIS_DATE,
        )

        # ── Phase 9: Valuation Builder ──────────────────────────────────────
        # Builds a ValuationInput from live financial data.
        # Conservative: marks all derived values explicitly; never invents peers.
        try:
            vi = build_valuation_input(
                load_result=load_result,
                research=research,
                analysis_date=ANALYSIS_DATE,
            )
            valuation = run_valuation(vi)
        except Exception as exc:
            print(f"  ⚠  Valuation engine error: {exc}")
            valuation = None

        # Phase 9.6: capture FCF metrics and shares for the calculation chain.
        if load_result.metrics is not None:
            _fcf_raw = getattr(load_result.metrics, "free_cash_flow", None)
            _fcf_shr = (load_result.supplemental or {}).get("shares_outstanding")

    # ── Run the pipeline ─────────────────────────────────────────────────────
    agent = InvestmentAgent()
    report = agent.analyze(
        ticker=ticker,
        company_name=company_name,
        analysis_date=ANALYSIS_DATE,
        financial_quality=fq,
        research=research,
        valuation=valuation,
        portfolio_weight_pct=args.weight,
        ignore_portfolio=args.new_position,
        current_price=current_price,
        price_currency=price_currency,
        price_date=args.price_date,
        freshness=freshness,
        fcf_raw_metrics=_fcf_raw,
        fcf_shares_outstanding=_fcf_shr,
    )

    print(report)

    # ── REPL ─────────────────────────────────────────────────────────────────
    print("Analysis loaded.  Ask follow-up questions below.")
    print("Commands: 'quit'/'exit' to stop.  'reload' to re-print the full report.")
    print("─" * 64)

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye.")
            break
        if user_input.lower() == "reload":
            print(report)
            continue

        print("\n" + agent.chat(user_input))


if __name__ == "__main__":
    main()
