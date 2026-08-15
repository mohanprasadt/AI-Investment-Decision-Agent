"""
Financial Data Normalizer
=========================
Maps raw yfinance data to the CompanyFinancialMetrics data model.

Design:
- Every field that can't be found or calculated returns None (not zero, not error)
- Missing fields are collected into data_quality_notes for human review
- All calculations delegated to calculations.py — this module only maps + calls
- ETFs produce a minimal metrics object (price history only, no fundamentals)
"""

import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.financial_quality.financial_metrics_model import (
    CompanyFinancialMetrics, RevenueGrowthMetrics, ROICMetrics, MarginMetrics,
    FreeCashFlowMetrics, DebtMetrics, DividendMetrics, EarningsQualityMetrics,
    Trend, MetricClassification
)
from analytics.financial_quality.calculations import (
    annual_growth_rates, growth_volatility, count_negative_growth_years,
    extract_cagr_from_series, gross_margin, operating_margin, net_margin,
    fcf_margin, free_cash_flow, fcf_conversion_ratio, capex_as_pct_revenue,
    debt_to_assets, interest_coverage, fcf_to_debt_ratio, net_debt,
    dividend_payout_ratio, fcf_payout_ratio, dividend_yield as calc_dividend_yield,
    extract_cagr_from_series as dividend_cagr_from_series,
    pe_ratio, price_to_fcf, ev_ebitda, enterprise_value
)

# ---------------------------------------------------------------------------
# Field name mappings from yfinance
# ---------------------------------------------------------------------------

# yfinance income statement field names (may vary slightly by version)
REVENUE_FIELDS = ["Total Revenue", "TotalRevenue", "Revenue"]
GROSS_PROFIT_FIELDS = ["Gross Profit", "GrossProfit"]
OPERATING_INCOME_FIELDS = [
    "Operating Income", "OperatingIncome",
    "EBIT", "Ebit", "Total Operating Income As Reported"
]
NET_INCOME_FIELDS = ["Net Income", "NetIncome", "Net Income Common Stockholders"]

# Preferred NI source for EPS derivation: continuing operations only.
# Excludes one-time gains from discontinued business disposals.
# Tried in order before falling back to NET_INCOME_FIELDS (Phase 9.9b).
CONTINUING_OPS_NI_FIELDS = [
    "Net Income From Continuing Operation Net Minority Interest",
    "Net Income From Continuing Operations Net Minority Interest",
    "Net Income Continuous Operations",
    "Net Income From Continuing Operations",
]
EBITDA_FIELDS = ["EBITDA", "Ebitda", "Normalized EBITDA"]
INTEREST_EXPENSE_FIELDS = ["Interest Expense", "InterestExpense"]

# yfinance balance sheet field names
TOTAL_ASSETS_FIELDS = ["Total Assets", "TotalAssets"]
TOTAL_DEBT_FIELDS = [
    "Total Debt", "TotalDebt", "Long Term Debt And Capital Lease Obligation",
    "Long Term Debt", "LongTermDebt"
]
SHORT_TERM_DEBT_FIELDS = [
    "Current Debt", "CurrentDebt", "Short Long Term Debt",
    "Short Term Borrowings", "Current Portion Of Long Term Debt"
]
CASH_FIELDS = [
    "Cash And Cash Equivalents", "CashAndCashEquivalents",
    "Cash Cash Equivalents And Short Term Investments",
    "Cash And Short Term Investments"
]
TOTAL_EQUITY_FIELDS = [
    "Total Stockholder Equity", "Stockholders Equity",
    "Total Equity Gross Minority Interest", "Common Stock Equity"
]

# yfinance cash flow statement field names
OPERATING_CASHFLOW_FIELDS = [
    "Total Cash From Operating Activities", "Operating Cash Flow",
    "Cash Flow From Operations", "Cash Flows From Used In Operating Activities"
]
CAPEX_FIELDS = [
    "Capital Expenditures", "CapitalExpenditures",
    "Capital Expenditure", "Purchase Of Property Plant And Equipment",
    "Investments In Property Plant And Equipment"
]
DIVIDENDS_PAID_FIELDS = [
    "Dividends Paid", "DividendsPaid",
    "Payment Of Dividends", "Cash Dividends Paid"
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first(d: dict, keys: list, default=None):
    """Return first matching value from a dict given a list of candidate keys."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _extract_annual_series(
    stmt: Dict[str, Dict],
    field_candidates: List[str]
) -> Dict[int, float]:
    """
    Extract a {year: value} series from a yfinance statement dict.
    Tries each candidate field name in order.
    """
    for field in field_candidates:
        if field in stmt:
            series = {}
            for year, val in stmt[field].items():
                if val is not None and isinstance(val, (int, float)):
                    series[int(year)] = float(val)
            if series:
                return series
    return {}


def _latest(series: Dict[int, float]) -> Optional[float]:
    """Most recent value in a {year: value} dict."""
    if not series:
        return None
    return series[max(series.keys())]


def _trend_from_series(series: Dict[int, float], min_points: int = 3) -> str:
    """Rough trend: compare latest half vs earliest half."""
    if len(series) < min_points:
        return Trend.INSUFFICIENT_DATA
    sorted_years = sorted(series.keys())
    mid = len(sorted_years) // 2
    early_avg = sum(series[y] for y in sorted_years[:mid]) / max(mid, 1)
    late_avg = sum(series[y] for y in sorted_years[mid:]) / max(len(sorted_years) - mid, 1)
    if early_avg == 0:
        return Trend.INSUFFICIENT_DATA
    change = (late_avg - early_avg) / abs(early_avg)
    if change > 0.05:
        return Trend.IMPROVING
    elif change < -0.05:
        return Trend.DETERIORATING
    return Trend.STABLE


# ---------------------------------------------------------------------------
# Main normalizer
# ---------------------------------------------------------------------------

def normalize(
    ticker: str,
    raw_info: Dict[str, Any],
    raw_financials: Dict[str, Any],
    is_etf: bool = False
) -> CompanyFinancialMetrics:
    """
    Normalize raw yfinance data into a CompanyFinancialMetrics object.

    Args:
        ticker: The ticker symbol
        raw_info: Output of fetcher.fetch_info()
        raw_financials: Output of fetcher.fetch_financials()
        is_etf: If True, only populate market/price data, skip fundamentals

    Returns:
        CompanyFinancialMetrics with as many fields populated as data allows
    """
    notes: List[str] = []
    missing: List[str] = []

    m = CompanyFinancialMetrics(
        ticker=ticker,
        company_name=raw_info.get("longName") or raw_info.get("shortName", ""),
        exchange=raw_info.get("exchange", ""),
        currency=raw_info.get("currency", ""),
        data_source="yfinance",
        data_as_of_date=raw_info.get("_fetched_at", datetime.utcnow().isoformat())[:10],
        retrieved_at=raw_info.get("_fetched_at", ""),
    )

    # --- Market data (always populated for equities and ETFs) ---
    m.current_price = raw_info.get("currentPrice") or raw_info.get("regularMarketPrice")
    m.market_cap = raw_info.get("marketCap")

    if raw_info.get("trailingPE"):
        m.pe_ratio = raw_info["trailingPE"]
    if raw_info.get("enterpriseToEbitda"):
        m.ev_ebitda = raw_info["enterpriseToEbitda"]

    # Compute EV if we have components
    mk = m.market_cap
    debt_info = raw_info.get("totalDebt")
    cash_info = raw_info.get("totalCash")
    if mk and debt_info and cash_info:
        m.enterprise_value = enterprise_value(mk, debt_info, cash_info)

    # --- ETF: stop here ---
    if is_etf:
        notes.append("ETF/Fund: only price and market data populated; fundamental analysis not applicable")
        m.data_quality_notes = notes
        return m

    # --- Dividend (from info — more reliable than cash flow statement) ---
    div = DividendMetrics()
    div.pays_dividend = (raw_info.get("dividendYield") or 0) > 0
    div.current_yield_pct = (
        raw_info["dividendYield"] * 100 if raw_info.get("dividendYield") else None
    )
    div.annual_dividend_per_share = raw_info.get("dividendRate")
    div.payout_ratio_pct = (
        raw_info["payoutRatio"] * 100 if raw_info.get("payoutRatio") else None
    )
    m.dividend = div

    # --- Early return if financials failed ---
    income = raw_financials.get("income_stmt", {})
    balance = raw_financials.get("balance_sheet", {})
    cashflow = raw_financials.get("cash_flow", {})

    if not raw_financials.get("_fetch_success"):
        notes.append(f"Financial statements unavailable: {raw_financials.get('_fetch_error', 'unknown error')}")
        missing.extend(["income_stmt", "balance_sheet", "cash_flow"])
        m.data_completeness_pct = 0.0
        m.data_quality_notes = notes
        m.missing_fields = missing
        return m

    # --- Revenue growth ---
    revenue_series = _extract_annual_series(income, REVENUE_FIELDS)
    if not revenue_series:
        missing.append("revenue_series")
    rg = RevenueGrowthMetrics(
        annual_revenues=revenue_series,
        data_years_available=len(revenue_series),
    )
    if revenue_series:
        yoy_rates = annual_growth_rates(revenue_series)
        rg.annual_growth_rates = yoy_rates
        rg.negative_growth_years = count_negative_growth_years(yoy_rates)
        rg.growth_volatility = growth_volatility(yoy_rates)
        rg.cagr_3yr = extract_cagr_from_series(revenue_series, 3)
        rg.cagr_5yr = extract_cagr_from_series(revenue_series, 5)
        rg.trend = _trend_from_series(revenue_series)
    m.revenue_growth = rg

    # --- Margins ---
    net_income_series = _extract_annual_series(income, NET_INCOME_FIELDS)
    gross_profit_series = _extract_annual_series(income, GROSS_PROFIT_FIELDS)
    op_income_series = _extract_annual_series(income, OPERATING_INCOME_FIELDS)

    # --- Continuing-operations NI (Phase 9.9b) ---
    # For EPS derivation we prefer income from continuing operations only.
    # This strips one-time gains from discontinued-business disposals (e.g. ITC
    # FY2025: ₹150B from a demerger inflated total NI to ₹347B vs ₹197B recurring).
    # _extract_annual_series preserves genuine 0.0 values; it only skips None.
    # Fall back to total NET_INCOME_FIELDS when continuing-ops series is absent.
    _cont_ops_series = _extract_annual_series(income, CONTINUING_OPS_NI_FIELDS)
    ni_for_eps_series: Dict[int, float] = _cont_ops_series if _cont_ops_series else net_income_series

    mg = MarginMetrics()
    if revenue_series and gross_profit_series:
        r, g = _latest(revenue_series), _latest(gross_profit_series)
        if r and g:
            mg.gross_margin = gross_margin(r, r - g)   # gross margin = (rev - cogs) / rev
            mg.gross_margin_history = {
                yr: gross_margin(revenue_series.get(yr, 0), revenue_series.get(yr, 0) - gross_profit_series.get(yr, 0))
                for yr in set(revenue_series) & set(gross_profit_series)
                if revenue_series.get(yr)
            }
            mg.gross_margin_trend = _trend_from_series(
                {k: v for k, v in mg.gross_margin_history.items() if v is not None}
            )

    if revenue_series and op_income_series:
        r, o = _latest(revenue_series), _latest(op_income_series)
        if r and o is not None:
            mg.operating_margin = operating_margin(r, o)
            op_margin_hist = {
                yr: operating_margin(revenue_series.get(yr, 0), op_income_series.get(yr, 0))
                for yr in set(revenue_series) & set(op_income_series)
                if revenue_series.get(yr)
            }
            mg.operating_margin_history = {k: v for k, v in op_margin_hist.items() if v is not None}
            mg.operating_margin_trend = _trend_from_series(mg.operating_margin_history)

    # net_margin uses total net_income_series (latest year) for margin accounting,
    # not the continuing-ops series.  This preserves pre-Phase-9.9b margin values.
    if revenue_series and net_income_series:
        r, n = _latest(revenue_series), _latest(net_income_series)
        if r and n is not None:
            mg.net_margin = net_margin(r, n)
    m.margins = mg

    # --- Free Cash Flow ---
    op_cf_series = _extract_annual_series(cashflow, OPERATING_CASHFLOW_FIELDS)
    capex_series = _extract_annual_series(cashflow, CAPEX_FIELDS)

    fcf_obj = FreeCashFlowMetrics(
        # annual_net_income stores the continuing-ops series when available.
        # valuation_builder.py reads this field to derive eps_history.
        # fcf_conversion_ratio (below) uses _latest() which is typically the most
        # recent year; in years where discontinued ops = 0, total NI == cont-ops NI.
        annual_net_income=ni_for_eps_series,
        annual_capex=capex_series,
    )

    if op_cf_series:
        # Persist extracted OCF directly so downstream handlers can use it without
        # re-deriving it as FCF − capex (Phase 9.9).
        fcf_obj.annual_ocf = op_cf_series

        fcf_series: Dict[int, float] = {}
        for yr in op_cf_series:
            ocf = op_cf_series[yr]
            capex_val = capex_series.get(yr, 0) or 0
            fcf_series[yr] = free_cash_flow(ocf, capex_val)

        fcf_obj.annual_fcf = fcf_series
        current_fcf = _latest(fcf_series)
        fcf_obj.fcf_current = current_fcf
        fcf_obj.fcf_trend = _trend_from_series(fcf_series)
        fcf_obj.negative_fcf_years = sum(1 for v in fcf_series.values() if v < 0)
        fcf_obj.recurring_negative_fcf = fcf_obj.negative_fcf_years >= 2

        if revenue_series and current_fcf is not None:
            r = _latest(revenue_series)
            if r:
                fcf_obj.fcf_margin_current = fcf_margin(r, current_fcf)

        current_ni = _latest(net_income_series) if net_income_series else None
        if current_fcf is not None and current_ni:
            fcf_obj.fcf_conversion_ratio = fcf_conversion_ratio(current_fcf, current_ni)

        if capex_series and revenue_series:
            latest_capex = _latest(capex_series)
            r = _latest(revenue_series)
            if latest_capex and r:
                fcf_obj.capex_as_pct_revenue = capex_as_pct_revenue(latest_capex, r)
    else:
        missing.append("operating_cashflow")
    m.free_cash_flow = fcf_obj

    # Also update FCF margin in margins
    if m.free_cash_flow.fcf_margin_current is not None:
        m.margins.fcf_margin = m.free_cash_flow.fcf_margin_current

    # --- Debt ---
    total_assets_series = _extract_annual_series(balance, TOTAL_ASSETS_FIELDS)
    long_debt_series = _extract_annual_series(balance, TOTAL_DEBT_FIELDS)
    cash_series = _extract_annual_series(balance, CASH_FIELDS)

    # Use info for simpler current values if statement parsing fails
    total_assets_val = _latest(total_assets_series) or raw_info.get("totalAssets")
    total_debt_val = _latest(long_debt_series) or raw_info.get("totalDebt")
    cash_val = _latest(cash_series) or raw_info.get("totalCash")

    db = DebtMetrics(
        total_assets=total_assets_val,
        interest_bearing_debt=total_debt_val,
        net_debt=net_debt(total_debt_val, cash_val) if total_debt_val and cash_val else None,
    )
    if total_debt_val and total_assets_val:
        db.debt_to_assets_pct = debt_to_assets(total_debt_val, total_assets_val)
        db.debt_trend = _trend_from_series(
            {yr: long_debt_series.get(yr, 0) / max(total_assets_series.get(yr, 1), 1) * 100
             for yr in set(long_debt_series) & set(total_assets_series)
             if total_assets_series.get(yr)}
        )

    # Interest coverage: need EBIT and interest expense
    ebit_series = _extract_annual_series(income, OPERATING_INCOME_FIELDS)
    interest_series = _extract_annual_series(income, INTEREST_EXPENSE_FIELDS)
    ebit_val = _latest(ebit_series)
    interest_val = _latest(interest_series)
    if ebit_val and interest_val:
        db.interest_coverage = interest_coverage(ebit_val, abs(interest_val))

    if m.free_cash_flow.fcf_current is not None and total_debt_val:
        db.fcf_to_debt_ratio = fcf_to_debt_ratio(m.free_cash_flow.fcf_current, total_debt_val)

    m.debt = db

    # --- ROIC (simplified: NOPAT / (Total Assets - Current Liabilities)) ---
    # yfinance doesn't give invested capital directly, so we approximate
    # A more accurate calculation requires Phase 3 (Financial Quality Engine)
    # For now, use ROE from info as a proxy if available
    roe = raw_info.get("returnOnEquity")
    if roe is not None:
        notes.append(
            f"ROIC approximated from ROE ({roe*100:.1f}%) — accurate ROIC requires Phase 3 engine"
        )
    roic_obj = ROICMetrics(
        calculation_note="Approximate — Phase 3 will compute full ROIC from financial statements"
    )
    m.roic = roic_obj

    # --- Earnings Quality ---
    eq = EarningsQualityMetrics(
        annual_net_income=net_income_series,
        annual_revenue=revenue_series,
    )
    if net_income_series:
        eq.eps_trend = _trend_from_series(net_income_series)
    # Flag revenue/FCF divergence
    if revenue_series and op_cf_series:
        rev_trend = _trend_from_series(revenue_series)
        fcf_trend_val = _trend_from_series(fcf_series) if op_cf_series else Trend.INSUFFICIENT_DATA
        if rev_trend == Trend.IMPROVING and fcf_trend_val == Trend.DETERIORATING:
            eq.revenue_vs_fcf_divergence = True
            notes.append("⚠ Revenue improving while FCF deteriorating — investigate earnings quality")
    m.earnings_quality = eq

    # --- FCF payout ratio ---
    if (m.dividend.pays_dividend and
        m.free_cash_flow.fcf_current is not None and
        m.free_cash_flow.fcf_current > 0):
        total_divs_paid_series = _extract_annual_series(cashflow, DIVIDENDS_PAID_FIELDS)
        total_divs_paid = abs(_latest(total_divs_paid_series)) if total_divs_paid_series else None
        if total_divs_paid and m.free_cash_flow.fcf_current:
            m.dividend.fcf_payout_ratio_pct = fcf_payout_ratio(
                total_divs_paid, m.free_cash_flow.fcf_current
            )

    # --- Valuation ratios from market data ---
    current_fcf = m.free_cash_flow.fcf_current
    if m.market_cap and current_fcf and current_fcf > 0:
        m.price_to_fcf = price_to_fcf(m.market_cap, current_fcf)

    revenue_latest = _latest(revenue_series)
    if m.market_cap and revenue_latest and revenue_latest > 0:
        m.price_to_sales = m.market_cap / revenue_latest

    # --- Data completeness ---
    important_fields = [
        revenue_series, net_income_series, op_cf_series,
        total_assets_series, long_debt_series
    ]
    populated = sum(1 for f in important_fields if f)
    m.data_completeness_pct = (populated / len(important_fields)) * 100

    m.data_quality_notes = notes
    m.missing_fields = missing

    return m


# ---------------------------------------------------------------------------
# Batch normalize
# ---------------------------------------------------------------------------

def normalize_portfolio(
    fetch_results: Dict[str, Any]
) -> Dict[str, CompanyFinancialMetrics]:
    """
    Normalize a full batch of fetched results.

    Args:
        fetch_results: Output of fetcher.fetch_portfolio()

    Returns:
        {ticker: CompanyFinancialMetrics}
    """
    normalized = {}
    for ticker, data in fetch_results.items():
        try:
            metrics = normalize(
                ticker=ticker,
                raw_info=data.get("info", {}),
                raw_financials=data.get("financials", {}),
                is_etf=data.get("is_etf", False)
            )
            normalized[ticker] = metrics
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Normalization failed for {ticker}: {e}")
            # Return a minimal object rather than nothing
            normalized[ticker] = CompanyFinancialMetrics(
                ticker=ticker,
                data_quality_notes=[f"Normalization error: {e}"],
                missing_fields=["all"]
            )
    return normalized


if __name__ == "__main__":
    # Test with synthetic data (no network required)
    print("Testing normalizer with synthetic data...")

    synthetic_info = {
        "_fetch_success": True,
        "_fetched_at": "2024-12-31T00:00:00",
        "longName": "Test Company Inc.",
        "currency": "CAD",
        "exchange": "TSX",
        "currentPrice": 45.0,
        "marketCap": 4_500_000_000,
        "dividendYield": 0.035,
        "dividendRate": 1.58,
        "payoutRatio": 0.45,
        "trailingPE": 18.5,
        "totalDebt": 800_000_000,
        "totalCash": 200_000_000,
        "totalAssets": 5_000_000_000,
        "returnOnEquity": 0.18,
    }

    synthetic_financials = {
        "_fetch_success": True,
        "_fetched_at": "2024-12-31T00:00:00",
        "income_stmt": {
            "Total Revenue": {2020: 2.0e9, 2021: 2.2e9, 2022: 2.5e9, 2023: 2.8e9},
            "Gross Profit": {2020: 0.8e9, 2021: 0.9e9, 2022: 1.05e9, 2023: 1.18e9},
            "Operating Income": {2020: 0.35e9, 2021: 0.40e9, 2022: 0.48e9, 2023: 0.54e9},
            "Net Income": {2020: 0.22e9, 2021: 0.25e9, 2022: 0.30e9, 2023: 0.35e9},
        },
        "balance_sheet": {
            "Total Assets": {2020: 4.0e9, 2021: 4.3e9, 2022: 4.7e9, 2023: 5.0e9},
            "Total Debt": {2020: 0.9e9, 2021: 0.85e9, 2022: 0.82e9, 2023: 0.80e9},
            "Cash And Cash Equivalents": {2020: 0.15e9, 2021: 0.17e9, 2022: 0.19e9, 2023: 0.20e9},
        },
        "cash_flow": {
            "Total Cash From Operating Activities": {2020: 0.40e9, 2021: 0.46e9, 2022: 0.52e9, 2023: 0.60e9},
            "Capital Expenditures": {2020: -0.10e9, 2021: -0.12e9, 2022: -0.13e9, 2023: -0.14e9},
            "Dividends Paid": {2020: -0.10e9, 2021: -0.11e9, 2022: -0.12e9, 2023: -0.14e9},
        },
    }

    m = normalize("TEST.TO", synthetic_info, synthetic_financials)
    print(f"\n{m.ticker} — {m.company_name}")
    print(f"  Revenue CAGR 3yr: {m.revenue_growth.cagr_3yr:.1f}%")
    print(f"  Gross margin: {m.margins.gross_margin:.1f}%")
    print(f"  Operating margin: {m.margins.operating_margin:.1f}%")
    print(f"  Net margin: {m.margins.net_margin:.1f}%")
    print(f"  FCF current: ${m.free_cash_flow.fcf_current/1e9:.2f}B")
    print(f"  FCF margin: {m.margins.fcf_margin:.1f}%")
    print(f"  FCF conversion: {m.free_cash_flow.fcf_conversion_ratio:.2f}x")
    print(f"  Debt/assets: {m.debt.debt_to_assets_pct:.1f}%")
    print(f"  Dividend yield: {m.dividend.current_yield_pct:.1f}%")
    print(f"  Payout ratio: {m.dividend.payout_ratio_pct:.1f}%")
    print(f"  FCF payout: {m.dividend.fcf_payout_ratio_pct:.1f}%" if m.dividend.fcf_payout_ratio_pct else "  FCF payout: N/A")
    print(f"  Data completeness: {m.data_completeness_pct:.0f}%")
    print(f"  Notes: {m.data_quality_notes}")
    print("\nNormalizer: OK")
