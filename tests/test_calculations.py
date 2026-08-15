"""
Tests for Financial Calculations
=================================
Run with: python -m pytest tests/test_calculations.py -v
Or:        python tests/test_calculations.py

Tests cover:
- Core financial calculations
- Edge cases (zero, negative, missing data)
- CAGR consistency
- Threshold classifications
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analytics.financial_quality.calculations import (
    cagr, annual_growth_rates, growth_volatility, count_negative_growth_years,
    extract_cagr_from_series, calculate_roic, average_roic,
    gross_margin, operating_margin, net_margin, fcf_margin,
    free_cash_flow, fcf_conversion_ratio, capex_as_pct_revenue,
    debt_to_assets, interest_coverage, fcf_to_debt_ratio, net_debt,
    dividend_payout_ratio, fcf_payout_ratio, dividend_yield, dividend_cagr,
    pe_ratio, price_to_fcf, ev_ebitda, enterprise_value,
    simple_dcf, normalize_earnings, position_weight, unrealized_gain_loss
)

from analytics.financial_quality.thresholds_engine import (
    classify_roic, classify_debt_to_assets, classify_dividend_payout,
    classify_dividend_yield, classify_revenue_growth_cagr,
    classify_fcf_conversion, classify_all
)

from analytics.financial_quality.financial_metrics_model import (
    CompanyFinancialMetrics, PortfolioPosition, WatchlistItem
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def approx(value, expected, tolerance=0.01):
    """Assert approximately equal within tolerance."""
    if value is None:
        return False
    return abs(value - expected) <= abs(expected) * tolerance + 1e-9


def test(name, condition, value=None):
    status = "PASS" if condition else "FAIL"
    value_str = f" [{value}]" if value is not None else ""
    print(f"  [{status}] {name}{value_str}")
    return condition


# ---------------------------------------------------------------------------
# CAGR Tests
# ---------------------------------------------------------------------------

def test_cagr():
    print("\n--- CAGR ---")
    results = []
    results.append(test("CAGR 100→161 over 5yr ≈ 10%", approx(cagr(100, 161, 5), 10.0, 0.01), cagr(100, 161, 5)))
    results.append(test("CAGR same value = 0%", approx(cagr(100, 100, 5), 0.0, 0.001)))
    results.append(test("CAGR negative start = None", cagr(-10, 100, 5) is None))
    results.append(test("CAGR zero start = None", cagr(0, 100, 5) is None))
    results.append(test("CAGR zero years = None", cagr(100, 200, 0) is None))
    results.append(test("CAGR negative end = None", cagr(100, -50, 5) is None))
    return all(results)


def test_annual_growth_rates():
    print("\n--- Annual Growth Rates ---")
    series = {2019: 100, 2020: 95, 2021: 108, 2022: 120, 2023: 135}
    rates = annual_growth_rates(series)
    results = []
    results.append(test("4 rate values from 5 year series", len(rates) == 4))
    results.append(test("2020 rate ≈ -5%", approx(rates[2020], -5.0, 0.1), rates.get(2020)))
    results.append(test("2023 rate ≈ 12.5%", approx(rates[2023], 12.5, 0.1), rates.get(2023)))
    results.append(test("Negative year counted", count_negative_growth_years(rates) == 1))
    results.append(test("Volatility computed", growth_volatility(rates) is not None))
    results.append(test("Single year series = empty", len(annual_growth_rates({2023: 100})) == 0))
    return all(results)


def test_extract_cagr_from_series():
    print("\n--- Extract CAGR from Series ---")
    series = {2018: 80, 2019: 100, 2020: 95, 2021: 108, 2022: 120, 2023: 135}
    results = []
    v = extract_cagr_from_series(series, 5)
    results.append(test("5yr CAGR from series not None", v is not None, v))
    results.append(test("5yr CAGR > 0", v is not None and v > 0))
    results.append(test("Single value series = None", extract_cagr_from_series({2023: 100}, 5) is None))
    return all(results)


# ---------------------------------------------------------------------------
# Margin Tests
# ---------------------------------------------------------------------------

def test_margins():
    print("\n--- Margins ---")
    results = []
    results.append(test("Gross margin 40%", approx(gross_margin(1000, 600), 40.0), gross_margin(1000, 600)))
    results.append(test("Operating margin 15%", approx(operating_margin(1000, 150), 15.0)))
    results.append(test("Net margin 10%", approx(net_margin(1000, 100), 10.0)))
    results.append(test("FCF margin 12%", approx(fcf_margin(1000, 120), 12.0)))
    results.append(test("Zero revenue = None", gross_margin(0, 100) is None))
    results.append(test("Negative revenue = None", gross_margin(-100, 50) is None))
    return all(results)


# ---------------------------------------------------------------------------
# FCF Tests
# ---------------------------------------------------------------------------

def test_fcf():
    print("\n--- Free Cash Flow ---")
    results = []
    results.append(test("FCF = OCF - CapEx", approx(free_cash_flow(500, 100), 400.0)))
    results.append(test("FCF = OCF - |negative CapEx|", approx(free_cash_flow(500, -100), 400.0)))
    results.append(test("FCF conversion 80%", approx(fcf_conversion_ratio(80, 100), 0.80)))
    results.append(test("FCF conversion zero NI = None", fcf_conversion_ratio(80, 0) is None))
    results.append(test("CapEx pct revenue 10%", approx(capex_as_pct_revenue(100, 1000), 10.0)))
    return all(results)


# ---------------------------------------------------------------------------
# Debt Tests
# ---------------------------------------------------------------------------

def test_debt():
    print("\n--- Debt / Balance Sheet ---")
    results = []
    results.append(test("Debt/assets 20%", approx(debt_to_assets(200, 1000), 20.0)))
    results.append(test("Debt/assets zero assets = None", debt_to_assets(200, 0) is None))
    results.append(test("Interest coverage 15x", approx(interest_coverage(300, 20), 15.0)))
    results.append(test("Interest coverage no debt = None", interest_coverage(300, 0) is None))
    results.append(test("FCF-to-debt 0.5", approx(fcf_to_debt_ratio(500, 1000), 0.5)))
    results.append(test("Net debt 200", approx(net_debt(500, 300), 200.0)))
    results.append(test("Net cash position", approx(net_debt(100, 500), -400.0)))
    return all(results)


# ---------------------------------------------------------------------------
# Dividend Tests
# ---------------------------------------------------------------------------

def test_dividends():
    print("\n--- Dividend Calculations ---")
    results = []
    results.append(test("Payout ratio 31.25%", approx(dividend_payout_ratio(2.5, 8.0), 31.25)))
    results.append(test("Payout ratio zero EPS = None", dividend_payout_ratio(2.5, 0) is None))
    results.append(test("Payout ratio neg EPS = None", dividend_payout_ratio(2.5, -1.0) is None))
    results.append(test("FCF payout 50%", approx(fcf_payout_ratio(500, 1000), 50.0)))
    results.append(test("FCF payout neg FCF = None", fcf_payout_ratio(500, -100) is None))
    results.append(test("Dividend yield 1.39%", approx(dividend_yield(2.5, 180), 1.389, 0.01)))
    return all(results)


# ---------------------------------------------------------------------------
# Valuation Tests
# ---------------------------------------------------------------------------

def test_valuation():
    print("\n--- Valuation Calculations ---")
    results = []
    results.append(test("P/E 25x", approx(pe_ratio(200, 8), 25.0)))
    results.append(test("P/E neg EPS = None", pe_ratio(200, -1) is None))
    results.append(test("Price/FCF 20x", approx(price_to_fcf(2000, 100), 20.0)))
    results.append(test("Price/FCF neg FCF = None", price_to_fcf(2000, -100) is None))
    results.append(test("EV/EBITDA 12x", approx(ev_ebitda(1200, 100), 12.0)))
    results.append(test("EV calculation", approx(enterprise_value(1000, 200, 50), 1150.0)))
    return all(results)


# ---------------------------------------------------------------------------
# DCF Tests
# ---------------------------------------------------------------------------

def test_dcf():
    print("\n--- DCF ---")
    results = []
    growth_rates = [12.0] * 5 + [8.0] * 5
    iv = simple_dcf(
        base_fcf=1_000_000_000,
        growth_rates=growth_rates,
        terminal_growth_rate=3.0,
        discount_rate=9.0,
        shares_outstanding=100_000_000
    )
    results.append(test("DCF produces positive value", iv is not None and iv > 0, iv))
    results.append(test("DCF discount <= terminal = None",
        simple_dcf(1e9, growth_rates, 4.0, 3.0, 1e8) is None))
    results.append(test("DCF neg FCF = None",
        simple_dcf(-1e9, growth_rates, 3.0, 9.0, 1e8) is None))

    # Higher discount rate → lower value
    iv_low = simple_dcf(1e9, growth_rates, 3.0, 7.5, 1e8)
    iv_high = simple_dcf(1e9, growth_rates, 3.0, 11.0, 1e8)
    results.append(test("Higher discount rate → lower intrinsic value",
        iv_low is not None and iv_high is not None and iv_low > iv_high,
        f"{iv_low:.2f} > {iv_high:.2f}"))
    return all(results)


# ---------------------------------------------------------------------------
# Threshold Classification Tests
# ---------------------------------------------------------------------------

def test_thresholds():
    print("\n--- Threshold Classifications ---")
    results = []

    # ROIC
    r = classify_roic(20.0)
    results.append(test("ROIC 20% = Excellent", r.classification == "Excellent", r.classification))
    r = classify_roic(12.0)
    results.append(test("ROIC 12% = Strong", r.classification == "Strong", r.classification))
    r = classify_roic(5.0)
    results.append(test("ROIC 5% = Concern", r.classification == "Concern", r.classification))
    r = classify_roic(None)
    results.append(test("ROIC None = N/A", r.classification == "N/A"))

    # Debt
    r = classify_debt_to_assets(15.0)
    results.append(test("Debt 15% = Preferred", r.classification == "Preferred", r.classification))
    r = classify_debt_to_assets(85.0, is_financial_institution=True)
    results.append(test("FI debt = Industry-Specific", r.classification == "Industry-Specific"))

    # Dividend payout
    r = classify_dividend_payout(45.0)
    results.append(test("Payout 45% = Strong Cushion", r.classification == "Strong Cushion"))
    r = classify_dividend_payout(105.0)
    results.append(test("Payout 105% = Significant Concern", r.classification == "Significant Concern"))

    # Dividend yield
    r = classify_dividend_yield(7.5)
    results.append(test("Yield 7.5% = Investigate", r.classification == "Investigate"))
    r = classify_dividend_yield(3.0)
    results.append(test("Yield 3.0% = Within Preferred Range", r.classification == "Within Preferred Range"))

    # Revenue growth
    r = classify_revenue_growth_cagr(17.0)
    results.append(test("Revenue CAGR 17% = Excellent", r.classification == "Excellent"))
    r = classify_revenue_growth_cagr(-2.0)
    results.append(test("Revenue CAGR -2% = Negative Growth", r.classification == "Negative Growth"))

    return all(results)


# ---------------------------------------------------------------------------
# Data Model Tests
# ---------------------------------------------------------------------------

def test_models():
    print("\n--- Data Models ---")
    results = []

    m = CompanyFinancialMetrics(ticker="AAPL", company_name="Apple", currency="USD")
    issues = m.validate()
    results.append(test("Missing data_as_of_date flagged", any("data_as_of_date" in i for i in issues)))

    m.data_as_of_date = "2024-12-31"
    issues = m.validate()
    results.append(test("Valid model: no issues", len(issues) == 0))

    pos = PortfolioPosition(ticker="CNR.TO", shares=100, average_cost=170.0, current_price=180.0)
    gl, gl_pct = unrealized_gain_loss(100, 170.0, 180.0)
    results.append(test("Unrealized gain = $1000", approx(gl, 1000.0), gl))
    results.append(test("Unrealized gain % ≈ 5.88%", approx(gl_pct, 5.882, 0.01), gl_pct))

    watch = WatchlistItem(
        ticker="COST", fair_value_low=680.0, fair_value_high=750.0, current_price=710.0
    )
    results.append(test("In accumulation zone (below FV high)", watch.is_in_accumulation_zone() is True))
    disc = watch.discount_to_fair_value_midpoint_pct()
    results.append(test("Discount to FV midpoint computed", disc is not None, disc))

    # JSON roundtrip
    d = m.to_dict()
    results.append(test("to_dict() produces ticker", d.get("ticker") == "AAPL"))
    json_str = m.to_json()
    results.append(test("to_json() produces non-empty string", len(json_str) > 10))

    return all(results)


# ---------------------------------------------------------------------------
# Portfolio Calculation Tests
# ---------------------------------------------------------------------------

def test_portfolio():
    print("\n--- Portfolio Calculations ---")
    results = []
    results.append(test("Position weight 10%", approx(position_weight(10000, 100000), 10.0)))
    results.append(test("Position weight zero portfolio = None", position_weight(10000, 0) is None))
    gl, gl_pct = unrealized_gain_loss(50, 100.0, 120.0)
    results.append(test("Unrealized gain correct amount", approx(gl, 1000.0)))
    results.append(test("Unrealized gain correct pct", approx(gl_pct, 20.0)))
    return all(results)


# ---------------------------------------------------------------------------
# Normalize Earnings Tests
# ---------------------------------------------------------------------------

def test_normalize():
    print("\n--- Normalize Earnings ---")
    results = []
    eps = {2021: 5.0, 2022: 6.0, 2023: 7.0, 2024: 8.0}
    norm = normalize_earnings(eps, years=3)
    results.append(test("3yr normalized ≈ 7.0", approx(norm, 7.0), norm))
    results.append(test("Empty series = None", normalize_earnings({}) is None))
    return all(results)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all():
    print("=" * 60)
    print("AI Investment Agent — Phase 1 Test Suite")
    print("=" * 60)

    test_funcs = [
        test_cagr,
        test_annual_growth_rates,
        test_extract_cagr_from_series,
        test_margins,
        test_fcf,
        test_debt,
        test_dividends,
        test_valuation,
        test_dcf,
        test_thresholds,
        test_models,
        test_portfolio,
        test_normalize,
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
        print(f"⚠  {failed} test group(s) had failures — review above")
    else:
        print("✓  All test groups passed")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
