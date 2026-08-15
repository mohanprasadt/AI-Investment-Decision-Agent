"""
Tests for Phase 3: Financial Quality Engine
============================================
All synthetic data — no network required.
Tests each dimension assessor, synthesis logic, and edge cases.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.financial_quality.financial_metrics_model import (
    CompanyFinancialMetrics, RevenueGrowthMetrics, MarginMetrics,
    FreeCashFlowMetrics, ROICMetrics, DebtMetrics, DividendMetrics,
    EarningsQualityMetrics, Trend
)
from analytics.financial_quality.quality_engine import (
    assess_financial_quality, FinancialQualityAssessment, DimensionAssessment,
    _assess_revenue_growth, _assess_margins, _assess_fcf,
    _assess_roic, _assess_balance_sheet, _assess_dividend,
    _assess_earnings_quality, min_class, max_class
)


def test(name, condition, value=None):
    status = "PASS" if condition else "FAIL"
    value_str = f" [{value}]" if value is not None else ""
    print(f"  [{status}] {name}{value_str}")
    return condition


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _strong_metrics() -> CompanyFinancialMetrics:
    """A financially strong company — should score Strong/Excellent overall."""
    m = CompanyFinancialMetrics(
        ticker="STRONG.TO", company_name="Strong Corp",
        currency="CAD", data_as_of_date="2024-12-31", data_completeness_pct=90.0
    )
    m.revenue_growth = RevenueGrowthMetrics(
        annual_revenues={2019: 1.0e9, 2020: 1.1e9, 2021: 1.25e9, 2022: 1.4e9, 2023: 1.55e9},
        cagr_3yr=11.4, cagr_5yr=9.1,
        negative_growth_years=0, growth_volatility=2.5,
        trend=Trend.IMPROVING, data_years_available=5,
    )
    m.margins = MarginMetrics(
        gross_margin=48.0, operating_margin=20.0, net_margin=14.0, fcf_margin=15.0,
        gross_margin_trend=Trend.STABLE, operating_margin_trend=Trend.IMPROVING,
    )
    m.free_cash_flow = FreeCashFlowMetrics(
        annual_fcf={2019: 100e6, 2020: 120e6, 2021: 140e6, 2022: 175e6, 2023: 220e6},
        fcf_current=220e6, fcf_trend=Trend.IMPROVING,
        fcf_conversion_ratio=1.02, fcf_margin_current=15.0,
        recurring_negative_fcf=False, negative_fcf_years=0,
    )
    m.roic = ROICMetrics(
        current=22.0, avg_3yr=20.0, avg_5yr=18.0, trend=Trend.STABLE
    )
    m.debt = DebtMetrics(
        debt_to_assets_pct=12.0, interest_coverage=25.0,
        fcf_to_debt_ratio=0.8, debt_trend=Trend.IMPROVING,
        interest_bearing_debt=400e6, total_assets=3.3e9, net_debt=250e6,
    )
    m.dividend = DividendMetrics(
        pays_dividend=True, current_yield_pct=2.2, payout_ratio_pct=35.0,
        fcf_payout_ratio_pct=28.0, dividend_growth_3yr_cagr=8.5,
    )
    m.earnings_quality = EarningsQualityMetrics(
        annual_revenue={2019: 1.0e9, 2020: 1.1e9, 2021: 1.25e9, 2022: 1.4e9, 2023: 1.55e9},
        annual_net_income={2019: 120e6, 2020: 140e6, 2021: 160e6, 2022: 195e6, 2023: 215e6},
        eps_trend=Trend.IMPROVING, revenue_vs_fcf_divergence=False,
    )
    return m


def _weak_metrics() -> CompanyFinancialMetrics:
    """A financially stressed company."""
    m = CompanyFinancialMetrics(
        ticker="WEAK.TO", company_name="Weak Corp",
        currency="CAD", data_as_of_date="2024-12-31", data_completeness_pct=75.0
    )
    m.revenue_growth = RevenueGrowthMetrics(
        annual_revenues={2019: 2.0e9, 2020: 1.8e9, 2021: 1.7e9, 2022: 1.75e9, 2023: 1.72e9},
        cagr_3yr=-0.5, cagr_5yr=-3.0,
        negative_growth_years=3, growth_volatility=8.5,
        trend=Trend.DETERIORATING, data_years_available=5,
    )
    m.margins = MarginMetrics(
        gross_margin=22.0, operating_margin=3.0, net_margin=0.5, fcf_margin=-2.0,
        gross_margin_trend=Trend.DETERIORATING, operating_margin_trend=Trend.DETERIORATING,
    )
    m.free_cash_flow = FreeCashFlowMetrics(
        annual_fcf={2019: 50e6, 2020: -20e6, 2021: -40e6, 2022: -10e6, 2023: -35e6},
        fcf_current=-35e6, fcf_trend=Trend.DETERIORATING,
        fcf_conversion_ratio=-0.5, fcf_margin_current=-2.0,
        recurring_negative_fcf=True, negative_fcf_years=3,
    )
    m.roic = ROICMetrics(current=4.0, avg_3yr=5.0, avg_5yr=8.0, trend=Trend.DETERIORATING)
    m.debt = DebtMetrics(
        debt_to_assets_pct=65.0, interest_coverage=1.2,
        fcf_to_debt_ratio=-0.1, debt_trend=Trend.DETERIORATING,
        interest_bearing_debt=1.3e9, total_assets=2.0e9, net_debt=1.2e9,
    )
    m.dividend = DividendMetrics(
        pays_dividend=True, current_yield_pct=8.5, payout_ratio_pct=110.0,
        fcf_payout_ratio_pct=None, dividend_growth_3yr_cagr=-5.0, dividend_cuts=1,
    )
    m.earnings_quality = EarningsQualityMetrics(
        annual_revenue={2019: 2.0e9, 2020: 1.8e9, 2021: 1.7e9, 2022: 1.75e9, 2023: 1.72e9},
        annual_net_income={2019: 80e6, 2020: 30e6, 2021: 20e6, 2022: 10e6, 2023: 8e6},
        eps_trend=Trend.DETERIORATING,
        revenue_vs_fcf_divergence=False,
        eps_vs_cashflow_divergence=True,
    )
    return m


def _etf_metrics() -> CompanyFinancialMetrics:
    m = CompanyFinancialMetrics(
        ticker="CGL.C.TO", company_name="iShares Gold ETF",
        currency="CAD", data_as_of_date="2024-12-31",
        data_quality_notes=["ETF/Fund: only price and market data populated"]
    )
    m.current_price = 22.5
    return m


def _empty_metrics() -> CompanyFinancialMetrics:
    """Minimal data — tests graceful handling of missing fields."""
    return CompanyFinancialMetrics(
        ticker="EMPTY.TO", company_name="Empty Corp",
        data_as_of_date="2024-12-31",
        data_completeness_pct=0.0,
        data_quality_notes=["Financial statements unavailable: timeout"],
        missing_fields=["income_stmt", "balance_sheet", "cash_flow"]
    )


# ---------------------------------------------------------------------------
# Strong company tests
# ---------------------------------------------------------------------------

def test_strong_company_overall():
    print("\n--- Strong Company: Overall ---")
    qa = assess_financial_quality(_strong_metrics())
    results = []
    results.append(test("Returns FinancialQualityAssessment", isinstance(qa, FinancialQualityAssessment)))
    results.append(test("Ticker preserved", qa.ticker == "STRONG.TO"))
    results.append(test("Overall hint is Strong or Excellent",
        qa.overall_classification_hint() in ("Strong", "Excellent"), qa.overall_classification_hint()))
    results.append(test("Has strengths", len(qa.strengths) > 0, len(qa.strengths)))
    results.append(test("No concerns (strong company)", len(qa.concerns) == 0, qa.concerns))
    results.append(test("All 5 core dimensions populated",
        all([qa.revenue_growth, qa.margins, qa.free_cash_flow, qa.roic, qa.balance_sheet])))
    return all(results)


def test_strong_company_dimensions():
    print("\n--- Strong Company: Dimension Classifications ---")
    qa = assess_financial_quality(_strong_metrics())
    results = []
    results.append(test("Revenue growth: Good or better",
        qa.revenue_growth.classification in ("Excellent", "Strong", "Good"),
        qa.revenue_growth.classification))
    results.append(test("Margins: Strong or Excellent",
        qa.margins.classification in ("Excellent", "Strong"),
        qa.margins.classification))
    results.append(test("FCF: Excellent",
        qa.free_cash_flow.classification == "Excellent", qa.free_cash_flow.classification))
    results.append(test("ROIC: Excellent",
        qa.roic.classification == "Excellent", qa.roic.classification))
    results.append(test("Balance sheet: Excellent or Strong",
        qa.balance_sheet.classification in ("Excellent", "Strong"),
        qa.balance_sheet.classification))
    results.append(test("Dividend: Excellent or Strong",
        qa.dividend.classification in ("Excellent", "Strong"),
        qa.dividend.classification))
    results.append(test("Earnings quality: Good or better",
        qa.earnings_quality.classification in ("Excellent", "Strong", "Good"),
        qa.earnings_quality.classification))
    return all(results)


def test_strong_company_evidence():
    print("\n--- Strong Company: Evidence populated ---")
    qa = assess_financial_quality(_strong_metrics())
    results = []
    results.append(test("Revenue evidence has entries", len(qa.revenue_growth.evidence) > 0))
    results.append(test("ROIC evidence mentions 22%",
        any("22" in e for e in qa.roic.evidence), qa.roic.evidence))
    results.append(test("Balance sheet evidence mentions coverage",
        any("coverage" in e.lower() for e in qa.balance_sheet.evidence)))
    results.append(test("Dividend evidence mentions yield",
        any("yield" in e.lower() for e in qa.dividend.evidence)))
    results.append(test("FCF flag about moat support present",
        any("ROIC" in f or "moat" in f.lower() for f in qa.for_claude_interpretation)))
    return all(results)


# ---------------------------------------------------------------------------
# Weak company tests
# ---------------------------------------------------------------------------

def test_weak_company_overall():
    print("\n--- Weak Company: Overall ---")
    qa = assess_financial_quality(_weak_metrics())
    results = []
    results.append(test("Overall hint is Watch or Concern",
        qa.overall_classification_hint() in ("Watch", "Concern"),
        qa.overall_classification_hint()))
    results.append(test("Has concerns", len(qa.concerns) > 0, len(qa.concerns)))
    results.append(test("FCF flagged as Concern",
        qa.free_cash_flow.classification == "Concern", qa.free_cash_flow.classification))
    results.append(test("Debt flagged as Concern or High Concern",
        qa.balance_sheet.classification in ("Concern", "High Concern", "Watch"),
        qa.balance_sheet.classification))
    return all(results)


def test_weak_company_flags():
    print("\n--- Weak Company: Flags ---")
    qa = assess_financial_quality(_weak_metrics())
    all_flags = qa.for_claude_interpretation
    results = []
    results.append(test("Dividend sustainability flagged",
        any("dividend" in f.lower() or "yield" in f.lower() for f in all_flags),
        all_flags[:3]))
    results.append(test("Negative FCF flagged",
        any("FCF" in f or "cash" in f.lower() for f in all_flags)))
    results.append(test("EPS/cashflow divergence flagged",
        any("deteriorat" in f.lower() or "earnings" in f.lower() for f in all_flags)))
    results.append(test("High yield requires investigation",
        any("8.5" in f or "yield" in f.lower() for f in all_flags)))
    return all(results)


def test_weak_company_revenue():
    print("\n--- Weak Company: Revenue Growth Assessment ---")
    qa = assess_financial_quality(_weak_metrics())
    results = []
    results.append(test("Revenue classified as Concern or Watch",
        qa.revenue_growth.classification in ("Concern", "Watch"),
        qa.revenue_growth.classification))
    results.append(test("Negative growth years in evidence",
        any("3" in e and "negative" in e.lower() or "Negative" in e
            for e in qa.revenue_growth.evidence),
        qa.revenue_growth.evidence))
    return all(results)


# ---------------------------------------------------------------------------
# Special case tests
# ---------------------------------------------------------------------------

def test_etf_handling():
    print("\n--- ETF: Special handling ---")
    qa = assess_financial_quality(_etf_metrics())
    results = []
    results.append(test("Is ETF flag set", qa.is_etf))
    results.append(test("No dimension assessments for ETF",
        qa.revenue_growth is None and qa.margins is None))
    results.append(test("ETF interpretation note present",
        any("ETF" in n for n in qa.for_claude_interpretation)))
    return all(results)


def test_empty_metrics():
    print("\n--- Empty/Missing Data: Graceful handling ---")
    qa = assess_financial_quality(_empty_metrics())
    results = []
    results.append(test("Returns assessment (no crash)", qa is not None))
    results.append(test("Data completeness 0%", qa.data_completeness_pct == 0.0))
    results.append(test("Missing dimensions recorded", len(qa.missing_dimensions) > 0, qa.missing_dimensions))
    results.append(test("Data caveats present", len(qa.data_caveats) > 0))
    results.append(test("All dimensions N/A",
        all(d is None or not d.data_available
            for d in [qa.revenue_growth, qa.margins, qa.free_cash_flow, qa.roic, qa.balance_sheet])))
    return all(results)


def test_financial_institution():
    print("\n--- Financial Institution: Debt threshold override ---")
    m = _strong_metrics()
    m.debt.debt_to_assets_pct = 82.0   # Normal for a bank
    qa_normal = assess_financial_quality(m, is_financial_institution=False)
    qa_fi = assess_financial_quality(m, is_financial_institution=True)
    results = []
    results.append(test("Non-FI: 82% debt = Concern",
        qa_normal.balance_sheet.classification in ("Concern", "Watch"),
        qa_normal.balance_sheet.classification))
    results.append(test("FI: 82% debt = Industry-Specific",
        qa_fi.balance_sheet.classification == "Industry-Specific",
        qa_fi.balance_sheet.classification))
    results.append(test("FI flag in interpretation",
        any("financial institution" in f.lower() for f in qa_fi.for_claude_interpretation)))
    return all(results)


def test_emerging_company():
    print("\n--- Emerging Company: Lenient ROIC thresholds ---")
    m = _strong_metrics()
    m.roic.current = 7.5  # Below the 10% preferred threshold
    m.roic.avg_3yr = 6.5
    m.roic.avg_5yr = 5.5
    qa_normal = assess_financial_quality(m, is_emerging_company=False)
    qa_emerging = assess_financial_quality(m, is_emerging_company=True)
    results = []
    results.append(test("ROIC 7.5% = Watch (non-emerging)",
        qa_normal.roic.classification in ("Watch", "Concern"),
        qa_normal.roic.classification))
    results.append(test("Emerging company context flag present",
        any("emerging" in f.lower() for f in qa_emerging.for_claude_interpretation or qa_emerging.roic.flags)))
    return all(results)


def test_no_dividend():
    print("\n--- No Dividend: Acceptable for growth companies ---")
    m = _strong_metrics()
    m.dividend = DividendMetrics(pays_dividend=False)
    qa = assess_financial_quality(m)
    results = []
    results.append(test("No dividend = N/A (not Concern)",
        qa.dividend.classification == "N/A", qa.dividend.classification))
    results.append(test("Note about retained capital in flags",
        any("reinvest" in f.lower() or "ROIC" in f for f in qa.dividend.flags)))
    return all(results)


def test_revenue_fcf_divergence():
    print("\n--- Revenue/FCF Divergence: Flag raised ---")
    m = _strong_metrics()
    m.earnings_quality.revenue_vs_fcf_divergence = True
    qa = assess_financial_quality(m)
    results = []
    results.append(test("Divergence flag raised in earnings quality",
        any("Revenue" in f and "FCF" in f for f in qa.earnings_quality.flags)))
    results.append(test("Flag propagated to for_claude_interpretation",
        any("FCF" in f or "receivables" in f.lower() for f in qa.for_claude_interpretation)))
    return all(results)


def test_decelerating_growth():
    print("\n--- Decelerating Growth: Flag raised ---")
    m = _strong_metrics()
    m.revenue_growth.cagr_3yr = 4.0   # Much lower than 5yr
    m.revenue_growth.cagr_5yr = 9.1
    qa = assess_financial_quality(m)
    results = []
    results.append(test("Deceleration flagged",
        any("decelerat" in f.lower() for f in qa.revenue_growth.flags or qa.for_claude_interpretation)))
    return all(results)


def test_high_yield_investigation():
    print("\n--- High Dividend Yield: Investigation triggered ---")
    m = _strong_metrics()
    m.dividend.current_yield_pct = 7.8
    qa = assess_financial_quality(m)
    results = []
    results.append(test("High yield triggers investigation flag",
        any("yield" in f.lower() and ("7.8" in f or "investigate" in f.lower())
            for f in qa.dividend.flags)))
    return all(results)


def test_classification_helpers():
    print("\n--- Classification Helpers ---")
    results = []
    results.append(test("min_class: Concern < Watch", min_class("Concern", "Watch") == "Concern"))
    results.append(test("min_class: Watch < Good", min_class("Watch", "Good") == "Watch"))
    results.append(test("max_class: Excellent > Strong", max_class("Excellent", "Strong") == "Excellent"))
    results.append(test("min_class: N/A handling", min_class("N/A", "Good") == "N/A"))
    return all(results)


def test_output_serialization():
    print("\n--- Output Serialization ---")
    qa = assess_financial_quality(_strong_metrics())
    results = []
    d = qa.to_dict()
    results.append(test("to_dict() has ticker", d.get("ticker") == "STRONG.TO"))
    results.append(test("to_dict() has overall_classification_hint", "overall_classification_hint" in d))
    results.append(test("to_dict() has strengths list", isinstance(d.get("strengths"), list)))

    j = qa.to_json()
    results.append(test("to_json() produces non-empty string", len(j) > 100))

    txt = qa.summary_text()
    results.append(test("summary_text() mentions ticker", "STRONG.TO" in txt))
    results.append(test("summary_text() mentions Strengths", "Strengths:" in txt))
    results.append(test("summary_text() mentions ROIC", "ROIC" in txt))
    return all(results)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all():
    print("=" * 60)
    print("AI Investment Agent — Phase 3 Test Suite")
    print("=" * 60)

    test_funcs = [
        test_strong_company_overall,
        test_strong_company_dimensions,
        test_strong_company_evidence,
        test_weak_company_overall,
        test_weak_company_flags,
        test_weak_company_revenue,
        test_etf_handling,
        test_empty_metrics,
        test_financial_institution,
        test_emerging_company,
        test_no_dividend,
        test_revenue_fcf_divergence,
        test_decelerating_growth,
        test_high_yield_investigation,
        test_classification_helpers,
        test_output_serialization,
    ]

    passed = 0
    failed = 0
    for fn in test_funcs:
        result = fn()
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed}/{len(test_funcs)} test groups passed")
    if failed:
        print(f"⚠  {failed} test group(s) had failures")
    else:
        print("✓  All test groups passed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    import sys
    success = run_all()
    sys.exit(0 if success else 1)
