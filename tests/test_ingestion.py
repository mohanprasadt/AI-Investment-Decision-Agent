"""
Tests for Phase 2: Data Ingestion and Normalization
====================================================
Uses synthetic data only — no network required.
Tests normalizer logic, portfolio updater, and data quality flags.
"""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.financial_quality.financial_metrics_model import (
    CompanyFinancialMetrics, DividendMetrics
)
from data.ingestion.normalizer import normalize
from data.ingestion.portfolio_updater import (
    enrich_portfolio, portfolio_summary, _infer_geography
)


def test(name, condition, value=None):
    status = "PASS" if condition else "FAIL"
    value_str = f" [{value}]" if value is not None else ""
    print(f"  [{status}] {name}{value_str}")
    return condition


# ---------------------------------------------------------------------------
# Synthetic data fixtures
# ---------------------------------------------------------------------------

def _make_info(overrides=None):
    info = {
        "_fetch_success": True,
        "_fetched_at": "2024-12-31T00:00:00",
        "longName": "Synthetic Corp",
        "currency": "CAD",
        "exchange": "TSX",
        "currentPrice": 50.0,
        "marketCap": 5_000_000_000,
        "dividendYield": 0.030,
        "dividendRate": 1.50,
        "payoutRatio": 0.42,
        "trailingPE": 18.0,
        "totalDebt": 600_000_000,
        "totalCash": 150_000_000,
        "totalAssets": 4_000_000_000,
        "returnOnEquity": 0.20,
    }
    if overrides:
        info.update(overrides)
    return info


def _make_financials(overrides=None):
    financials = {
        "_fetch_success": True,
        "_fetched_at": "2024-12-31T00:00:00",
        "income_stmt": {
            "Total Revenue": {2019: 1.8e9, 2020: 1.9e9, 2021: 2.1e9, 2022: 2.4e9, 2023: 2.7e9},
            "Gross Profit": {2019: 0.7e9, 2020: 0.75e9, 2021: 0.84e9, 2022: 0.96e9, 2023: 1.08e9},
            "Operating Income": {2019: 0.3e9, 2020: 0.32e9, 2021: 0.37e9, 2022: 0.44e9, 2023: 0.51e9},
            "Net Income": {2019: 0.18e9, 2020: 0.20e9, 2021: 0.23e9, 2022: 0.28e9, 2023: 0.33e9},
            "Interest Expense": {2019: -0.03e9, 2020: -0.028e9, 2021: -0.025e9, 2022: -0.022e9, 2023: -0.020e9},
        },
        "balance_sheet": {
            "Total Assets": {2019: 3.5e9, 2020: 3.7e9, 2021: 3.9e9, 2022: 4.1e9, 2023: 4.3e9},
            "Total Debt": {2019: 0.75e9, 2020: 0.72e9, 2021: 0.68e9, 2022: 0.63e9, 2023: 0.60e9},
            "Cash And Cash Equivalents": {2019: 0.10e9, 2020: 0.11e9, 2021: 0.12e9, 2022: 0.13e9, 2023: 0.15e9},
        },
        "cash_flow": {
            "Total Cash From Operating Activities": {2019: 0.35e9, 2020: 0.38e9, 2021: 0.44e9, 2022: 0.52e9, 2023: 0.60e9},
            "Capital Expenditures": {2019: -0.08e9, 2020: -0.09e9, 2021: -0.10e9, 2022: -0.11e9, 2023: -0.12e9},
            "Dividends Paid": {2019: -0.07e9, 2020: -0.08e9, 2021: -0.09e9, 2022: -0.10e9, 2023: -0.12e9},
        },
    }
    if overrides:
        financials.update(overrides)
    return financials


# ---------------------------------------------------------------------------
# Normalizer tests
# ---------------------------------------------------------------------------

def test_normalizer_basic():
    print("\n--- Normalizer: Basic fields ---")
    m = normalize("TEST.TO", _make_info(), _make_financials())
    results = []
    results.append(test("Ticker set", m.ticker == "TEST.TO"))
    results.append(test("Company name set", m.company_name == "Synthetic Corp"))
    results.append(test("Currency set", m.currency == "CAD"))
    results.append(test("Current price set", m.current_price == 50.0, m.current_price))
    results.append(test("Market cap set", m.market_cap == 5e9))
    results.append(test("Data as-of-date set", m.data_as_of_date == "2024-12-31"))
    return all(results)


def test_normalizer_revenue_growth():
    print("\n--- Normalizer: Revenue growth ---")
    m = normalize("TEST.TO", _make_info(), _make_financials())
    rg = m.revenue_growth
    results = []
    results.append(test("5 years of revenue data", rg.data_years_available == 5, rg.data_years_available))
    results.append(test("3yr CAGR computed", rg.cagr_3yr is not None, rg.cagr_3yr))
    results.append(test("3yr CAGR > 0", rg.cagr_3yr is not None and rg.cagr_3yr > 0))
    results.append(test("No negative growth years", rg.negative_growth_years == 0, rg.negative_growth_years))
    results.append(test("Growth volatility computed", rg.growth_volatility is not None))
    results.append(test("Revenue trend = Improving", rg.trend == "Improving", rg.trend))
    return all(results)


def test_normalizer_margins():
    print("\n--- Normalizer: Margins ---")
    m = normalize("TEST.TO", _make_info(), _make_financials())
    mg = m.margins
    results = []
    results.append(test("Gross margin > 0", mg.gross_margin is not None and mg.gross_margin > 0, mg.gross_margin))
    results.append(test("Operating margin > 0", mg.operating_margin is not None and mg.operating_margin > 0))
    results.append(test("Net margin > 0", mg.net_margin is not None and mg.net_margin > 0))
    results.append(test("FCF margin > 0", mg.fcf_margin is not None and mg.fcf_margin > 0, mg.fcf_margin))
    results.append(test("Gross margin ≈ 40%", mg.gross_margin is not None and 35 < mg.gross_margin < 45, mg.gross_margin))
    results.append(test("Operating margin trend set", mg.operating_margin_trend != ""))
    return all(results)


def test_normalizer_fcf():
    print("\n--- Normalizer: Free Cash Flow ---")
    m = normalize("TEST.TO", _make_info(), _make_financials())
    fcf = m.free_cash_flow
    results = []
    results.append(test("FCF current > 0", fcf.fcf_current is not None and fcf.fcf_current > 0, fcf.fcf_current))
    results.append(test("FCF series has 5 years", len(fcf.annual_fcf) == 5))
    results.append(test("No recurring negative FCF", not fcf.recurring_negative_fcf))
    results.append(test("FCF conversion > 0.70", fcf.fcf_conversion_ratio is not None and fcf.fcf_conversion_ratio > 0.70, fcf.fcf_conversion_ratio))
    results.append(test("FCF trend = Improving", fcf.fcf_trend == "Improving", fcf.fcf_trend))
    return all(results)


def test_normalizer_debt():
    print("\n--- Normalizer: Debt ---")
    m = normalize("TEST.TO", _make_info(), _make_financials())
    db = m.debt
    results = []
    results.append(test("Debt/assets computed", db.debt_to_assets_pct is not None, db.debt_to_assets_pct))
    results.append(test("Debt/assets < 20% (preferred)", db.debt_to_assets_pct is not None and db.debt_to_assets_pct < 20, db.debt_to_assets_pct))
    results.append(test("Interest coverage computed", db.interest_coverage is not None, db.interest_coverage))
    results.append(test("Interest coverage > 10x (healthy)", db.interest_coverage is not None and db.interest_coverage > 10))
    results.append(test("Debt trend computed", db.debt_trend != ""))
    return all(results)


def test_normalizer_dividend():
    print("\n--- Normalizer: Dividend ---")
    m = normalize("TEST.TO", _make_info(), _make_financials())
    div = m.dividend
    results = []
    results.append(test("Pays dividend = True", div.pays_dividend))
    results.append(test("Yield = 3.0%", div.current_yield_pct == 3.0, div.current_yield_pct))
    results.append(test("Payout ratio = 42%", div.payout_ratio_pct == 42.0, div.payout_ratio_pct))
    results.append(test("FCF payout computed", div.fcf_payout_ratio_pct is not None, div.fcf_payout_ratio_pct))
    results.append(test("FCF payout <= 25%", div.fcf_payout_ratio_pct is not None and div.fcf_payout_ratio_pct <= 25))
    return all(results)


def test_normalizer_no_dividend():
    print("\n--- Normalizer: No dividend ---")
    info = _make_info({"dividendYield": None, "dividendRate": None, "payoutRatio": None})
    m = normalize("TECH.TO", info, _make_financials())
    results = []
    results.append(test("Pays dividend = False", not m.dividend.pays_dividend))
    results.append(test("Yield = None", m.dividend.current_yield_pct is None))
    return all(results)


def test_normalizer_failed_financials():
    print("\n--- Normalizer: Failed financials ---")
    info = _make_info()
    failed_financials = {
        "_fetch_success": False,
        "_fetch_error": "Connection timeout",
        "income_stmt": {}, "balance_sheet": {}, "cash_flow": {}
    }
    m = normalize("FAIL.TO", info, failed_financials)
    results = []
    results.append(test("Model still created", m is not None))
    results.append(test("Price still populated", m.current_price == 50.0))
    results.append(test("Error recorded in notes", len(m.data_quality_notes) > 0))
    results.append(test("'income_stmt' in missing_fields", "income_stmt" in m.missing_fields))
    return all(results)


def test_normalizer_etf():
    print("\n--- Normalizer: ETF handling ---")
    info = _make_info({"longName": "iShares Gold ETF", "dividendYield": None})
    m = normalize("CGL.C.TO", info, {}, is_etf=True)
    results = []
    results.append(test("ETF model created", m is not None))
    results.append(test("Price populated for ETF", m.current_price == 50.0))
    results.append(test("Revenue growth empty (ETF)", len(m.revenue_growth.annual_revenues) == 0))
    results.append(test("ETF note in data_quality_notes", any("ETF" in n for n in m.data_quality_notes)))
    return all(results)


def test_normalizer_revenue_fcf_divergence():
    print("\n--- Normalizer: Revenue/FCF divergence flag ---")
    # Revenue improving but FCF deteriorating
    financials = _make_financials()
    financials["cash_flow"]["Total Cash From Operating Activities"] = {
        2019: 0.60e9, 2020: 0.55e9, 2021: 0.48e9, 2022: 0.42e9, 2023: 0.35e9
    }
    m = normalize("DIVG.TO", _make_info(), financials)
    results = []
    results.append(test("Divergence flag set", m.earnings_quality.revenue_vs_fcf_divergence))
    results.append(test("Warning in notes", any("⚠" in n for n in m.data_quality_notes)))
    return all(results)


# ---------------------------------------------------------------------------
# Portfolio updater tests
# ---------------------------------------------------------------------------

def test_portfolio_enrichment():
    print("\n--- Portfolio Updater: Enrichment ---")
    rows = [
        {
            "ticker": "TEST.TO", "company": "", "exchange": "TSX", "currency": "CAD",
            "shares": "500", "average_cost": "45.00", "current_price": "",
            "current_value": "", "portfolio_weight_pct": "",
            "sector": "", "geography": "", "dividend_yield_pct": "",
            "original_thesis_summary": "", "thesis_status": "",
            "last_review_date": "", "notes": ""
        },
        {
            "ticker": "AMZN", "company": "", "exchange": "NASDAQ", "currency": "USD",
            "shares": "10", "average_cost": "180.00", "current_price": "",
            "current_value": "", "portfolio_weight_pct": "",
            "sector": "", "geography": "", "dividend_yield_pct": "",
            "original_thesis_summary": "", "thesis_status": "",
            "last_review_date": "", "notes": ""
        }
    ]

    m1 = CompanyFinancialMetrics(ticker="TEST.TO", company_name="Test Corp", current_price=50.0)
    m1.dividend = DividendMetrics(pays_dividend=True, current_yield_pct=3.5)
    m1._yf_sector = "Industrials"

    m2 = CompanyFinancialMetrics(ticker="AMZN", company_name="Amazon", current_price=200.0)
    m2.dividend = DividendMetrics(pays_dividend=False)
    m2._yf_sector = "Consumer Discretionary"

    enriched = enrich_portfolio(rows, {"TEST.TO": m1, "AMZN": m2})
    results = []

    t = enriched[0]
    results.append(test("Company name populated", t["company"] == "Test Corp", t["company"]))
    results.append(test("Current price updated", t["current_price"] == "50.0000"))
    results.append(test("Current value = 25000", t["current_value"] == "25000.00", t["current_value"]))
    results.append(test("Dividend yield populated", "3.50" in t["dividend_yield_pct"]))
    results.append(test("Geography inferred (Canada)", t["geography"] == "Canada", t["geography"]))

    a = enriched[1]
    results.append(test("AMZN price updated", a["current_price"] == "200.0000"))
    results.append(test("AMZN no-dividend shown", "0.00" in a["dividend_yield_pct"]))
    results.append(test("AMZN geography (US)", a["geography"] == "United States"))

    # Portfolio weights should be recalculated
    # TEST.TO: 25000 / (25000 + 2000) ≈ 92.6%
    # AMZN: 2000 / 27000 ≈ 7.4%
    results.append(test("Portfolio weights recalculated", "%" in t.get("portfolio_weight_pct", "")))
    return all(results)


def test_geography_inference():
    print("\n--- Portfolio Updater: Geography inference ---")
    results = []
    results.append(test("TSX → Canada", _infer_geography("TSX") == "Canada"))
    results.append(test("NYSE → United States", _infer_geography("NYSE") == "United States"))
    results.append(test("NASDAQ → United States", _infer_geography("NASDAQ") == "United States"))
    results.append(test("NSE → India", _infer_geography("NSE") == "India"))
    results.append(test("BSE → India", _infer_geography("BSE") == "India"))
    results.append(test("Unknown → Unknown", _infer_geography("XYZEXCHANGE") == "Unknown"))
    return all(results)


def test_data_completeness():
    print("\n--- Normalizer: Data completeness tracking ---")
    # Full data — should be 100%
    m_full = normalize("FULL.TO", _make_info(), _make_financials())
    results = []
    results.append(test("Full data completeness > 80%",
        m_full.data_completeness_pct is not None and m_full.data_completeness_pct > 80,
        m_full.data_completeness_pct))

    # Failed financials — should be 0%
    failed = {
        "_fetch_success": False, "_fetch_error": "timeout",
        "income_stmt": {}, "balance_sheet": {}, "cash_flow": {}
    }
    m_fail = normalize("FAIL.TO", _make_info(), failed)
    results.append(test("Failed financials completeness < 30%",
        m_fail.data_completeness_pct is not None and m_fail.data_completeness_pct < 30,
        m_fail.data_completeness_pct))
    return all(results)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all():
    print("=" * 60)
    print("AI Investment Agent — Phase 2 Test Suite")
    print("=" * 60)

    test_funcs = [
        test_normalizer_basic,
        test_normalizer_revenue_growth,
        test_normalizer_margins,
        test_normalizer_fcf,
        test_normalizer_debt,
        test_normalizer_dividend,
        test_normalizer_no_dividend,
        test_normalizer_failed_financials,
        test_normalizer_etf,
        test_normalizer_revenue_fcf_divergence,
        test_portfolio_enrichment,
        test_geography_inference,
        test_data_completeness,
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
    success = run_all()
    sys.exit(0 if success else 1)
