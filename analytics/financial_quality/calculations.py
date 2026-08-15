"""
Financial Calculations
======================
Pure Python deterministic financial calculations.
No external dependencies (stdlib only) except typing.

All functions return Optional[float] — they return None rather than raising
exceptions when data is insufficient, so the calling layer can flag missing data
gracefully without crashing the analysis.

Python handles ALL calculations. Claude handles ALL interpretation.
"""

import math
from typing import Optional, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Growth Calculations
# ---------------------------------------------------------------------------

def cagr(start_value: float, end_value: float, years: int) -> Optional[float]:
    """
    Compound Annual Growth Rate.

    Returns None if:
    - years <= 0
    - start_value <= 0 (can't compute CAGR from negative or zero base)
    - end_value < 0 (negative terminal value — return None, flag separately)
    """
    if years <= 0 or start_value <= 0:
        return None
    if end_value <= 0:
        return None  # Negative/zero terminal — caller should handle
    return (((end_value / start_value) ** (1.0 / years)) - 1) * 100


def annual_growth_rates(time_series: Dict[int, float]) -> Dict[int, Optional[float]]:
    """
    Compute year-over-year growth rates from a {year: value} dict.

    Returns {year: growth_rate_pct} for each year after the first.
    Returns None for a year if previous year's value was zero or negative.
    """
    if len(time_series) < 2:
        return {}
    sorted_years = sorted(time_series.keys())
    rates: Dict[int, Optional[float]] = {}
    for i in range(1, len(sorted_years)):
        yr = sorted_years[i]
        prev_yr = sorted_years[i - 1]
        prev_val = time_series[prev_yr]
        curr_val = time_series[yr]
        if prev_val <= 0:
            rates[yr] = None
        else:
            rates[yr] = ((curr_val / prev_val) - 1) * 100
    return rates


def growth_volatility(growth_rates: Dict[int, Optional[float]]) -> Optional[float]:
    """
    Standard deviation of annual growth rates.
    Higher volatility = less consistent growth.
    Returns None if fewer than 2 data points.
    """
    valid = [v for v in growth_rates.values() if v is not None]
    if len(valid) < 2:
        return None
    mean = sum(valid) / len(valid)
    variance = sum((x - mean) ** 2 for x in valid) / (len(valid) - 1)
    return math.sqrt(variance)


def count_negative_growth_years(growth_rates: Dict[int, Optional[float]]) -> int:
    """Count years with negative growth (None values excluded)."""
    return sum(1 for v in growth_rates.values() if v is not None and v < 0)


def extract_cagr_from_series(
    time_series: Dict[int, float], years: int
) -> Optional[float]:
    """
    Extract CAGR over the specified number of years from a time series.
    Uses the most recent 'years' data points available.
    """
    if len(time_series) < 2:
        return None
    sorted_years = sorted(time_series.keys())
    # Use last `years` entries if available
    if len(sorted_years) < years + 1:
        # Use whatever we have
        start_yr = sorted_years[0]
        end_yr = sorted_years[-1]
        actual_years = end_yr - start_yr
    else:
        end_yr = sorted_years[-1]
        start_yr = sorted_years[-1] - years
        actual_years = years
        if start_yr not in time_series:
            # Find closest available year
            available = [y for y in sorted_years if y <= start_yr]
            if not available:
                return None
            start_yr = available[-1]
            actual_years = end_yr - start_yr

    if actual_years <= 0:
        return None
    return cagr(time_series[start_yr], time_series[end_yr], actual_years)


# ---------------------------------------------------------------------------
# ROIC Calculations
# ---------------------------------------------------------------------------

def calculate_roic(
    nopat: float,             # Net Operating Profit After Tax
    invested_capital: float   # Total capital invested in operations
) -> Optional[float]:
    """
    ROIC = NOPAT / Invested Capital * 100
    Returns None if invested_capital <= 0.
    """
    if invested_capital <= 0:
        return None
    return (nopat / invested_capital) * 100


def average_roic(annual_roic: Dict[int, float], years: int) -> Optional[float]:
    """Average ROIC over the most recent N years."""
    if not annual_roic:
        return None
    sorted_years = sorted(annual_roic.keys(), reverse=True)
    selected = sorted_years[:years]
    values = [annual_roic[y] for y in selected if annual_roic[y] is not None]
    if not values:
        return None
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# Margin Calculations
# ---------------------------------------------------------------------------

def gross_margin(revenue: float, cogs: float) -> Optional[float]:
    """Gross Margin % = (Revenue - COGS) / Revenue * 100"""
    if revenue <= 0:
        return None
    return ((revenue - cogs) / revenue) * 100


def operating_margin(revenue: float, operating_income: float) -> Optional[float]:
    """Operating Margin % = Operating Income / Revenue * 100"""
    if revenue <= 0:
        return None
    return (operating_income / revenue) * 100


def net_margin(revenue: float, net_income: float) -> Optional[float]:
    """Net Margin % = Net Income / Revenue * 100"""
    if revenue <= 0:
        return None
    return (net_income / revenue) * 100


def fcf_margin(revenue: float, free_cash_flow: float) -> Optional[float]:
    """FCF Margin % = FCF / Revenue * 100"""
    if revenue <= 0:
        return None
    return (free_cash_flow / revenue) * 100


# ---------------------------------------------------------------------------
# Free Cash Flow Calculations
# ---------------------------------------------------------------------------

def free_cash_flow(operating_cash_flow: float, capex: float) -> float:
    """FCF = Operating Cash Flow - Capital Expenditures"""
    return operating_cash_flow - abs(capex)


def fcf_conversion_ratio(fcf: float, net_income: float) -> Optional[float]:
    """
    FCF Conversion = FCF / Net Income
    Preferred >= 0.70 (see thresholds.yaml)
    Returns None if net_income == 0.
    """
    if net_income == 0:
        return None
    return fcf / net_income


def capex_as_pct_revenue(capex: float, revenue: float) -> Optional[float]:
    """CapEx Intensity = CapEx / Revenue * 100"""
    if revenue <= 0:
        return None
    return (abs(capex) / revenue) * 100


# ---------------------------------------------------------------------------
# Debt / Balance Sheet Calculations
# ---------------------------------------------------------------------------

def debt_to_assets(
    interest_bearing_debt: float,
    total_assets: float
) -> Optional[float]:
    """
    Debt-to-Assets = Interest-Bearing Debt / Total Assets * 100

    IMPORTANT: Use ONLY interest-bearing debt.
    Do NOT include accounts payable, deferred revenue, or other operating liabilities.
    """
    if total_assets <= 0:
        return None
    return (interest_bearing_debt / total_assets) * 100


def interest_coverage(
    ebit: float,
    interest_expense: float
) -> Optional[float]:
    """
    Interest Coverage = EBIT / Interest Expense
    Higher = better ability to service debt.
    Returns None if interest_expense <= 0 (no debt or data unavailable).
    """
    if interest_expense <= 0:
        return None
    return ebit / interest_expense


def fcf_to_debt_ratio(fcf: float, interest_bearing_debt: float) -> Optional[float]:
    """
    FCF-to-Debt = FCF / Interest-Bearing Debt
    Indicates how quickly the company could theoretically repay debt from FCF.
    """
    if interest_bearing_debt <= 0:
        return None
    return fcf / interest_bearing_debt


def net_debt(
    interest_bearing_debt: float,
    cash_and_equivalents: float
) -> float:
    """Net Debt = Interest-Bearing Debt - Cash & Equivalents"""
    return interest_bearing_debt - cash_and_equivalents


# ---------------------------------------------------------------------------
# Dividend Calculations
# ---------------------------------------------------------------------------

def dividend_payout_ratio(
    annual_dividend_per_share: float,
    earnings_per_share: float
) -> Optional[float]:
    """
    Payout Ratio = DPS / EPS * 100
    Returns None if EPS <= 0 (negative or zero earnings).
    """
    if earnings_per_share <= 0:
        return None
    return (annual_dividend_per_share / earnings_per_share) * 100


def fcf_payout_ratio(
    total_dividends_paid: float,
    free_cash_flow_value: float
) -> Optional[float]:
    """
    FCF Payout Ratio = Total Dividends / FCF * 100
    Returns None if FCF <= 0.
    """
    if free_cash_flow_value <= 0:
        return None
    return (total_dividends_paid / free_cash_flow_value) * 100


def dividend_yield(
    annual_dividend_per_share: float,
    current_price: float
) -> Optional[float]:
    """Dividend Yield = DPS / Price * 100"""
    if current_price <= 0:
        return None
    return (annual_dividend_per_share / current_price) * 100


def dividend_cagr(time_series: Dict[int, float], years: int) -> Optional[float]:
    """Dividend CAGR over specified years."""
    return extract_cagr_from_series(time_series, years)


# ---------------------------------------------------------------------------
# Valuation Calculations
# ---------------------------------------------------------------------------

def pe_ratio(price: float, eps: float) -> Optional[float]:
    """P/E Ratio. Returns None if EPS <= 0."""
    if eps <= 0:
        return None
    return price / eps


def price_to_fcf(market_cap: float, fcf_value: float) -> Optional[float]:
    """Price-to-FCF = Market Cap / FCF. Returns None if FCF <= 0."""
    if fcf_value <= 0:
        return None
    return market_cap / fcf_value


def ev_ebitda(enterprise_value: float, ebitda: float) -> Optional[float]:
    """EV/EBITDA. Returns None if EBITDA <= 0."""
    if ebitda <= 0:
        return None
    return enterprise_value / ebitda


def price_to_sales(market_cap: float, revenue: float) -> Optional[float]:
    """Price-to-Sales. Returns None if revenue <= 0."""
    if revenue <= 0:
        return None
    return market_cap / revenue


def enterprise_value(
    market_cap: float,
    interest_bearing_debt: float,
    cash_and_equivalents: float
) -> float:
    """EV = Market Cap + Debt - Cash"""
    return market_cap + interest_bearing_debt - cash_and_equivalents


# ---------------------------------------------------------------------------
# DCF Calculations
# ---------------------------------------------------------------------------

def simple_dcf(
    base_fcf: float,
    growth_rates: List[float],     # % growth rate per year (list of N values)
    terminal_growth_rate: float,   # % long-run growth rate
    discount_rate: float,          # % WACC
    shares_outstanding: float
) -> Optional[float]:
    """
    Simple multi-stage DCF.

    Args:
        base_fcf: Most recent annual FCF (the starting point)
        growth_rates: List of year-by-year FCF growth rates (%, e.g., [15.0, 12.0, ...])
        terminal_growth_rate: Terminal growth rate (%, e.g., 3.0)
        discount_rate: Discount rate / WACC (%, e.g., 9.0)
        shares_outstanding: Number of shares for per-share value

    Returns:
        Intrinsic value per share (in same currency as base_fcf/shares)
        Returns None if inputs are invalid.

    NOTE: This is a simplified model. Phase 5 (Valuation Engine) will implement
    a more comprehensive DCF with reinvestment, revenue-based projections, etc.
    """
    if base_fcf <= 0 or shares_outstanding <= 0:
        return None
    if discount_rate <= terminal_growth_rate:
        return None  # Gordon growth model would produce negative/infinite value

    r = discount_rate / 100
    g_terminal = terminal_growth_rate / 100

    pv_fcfs = 0.0
    fcf = base_fcf

    for i, g_pct in enumerate(growth_rates):
        fcf = fcf * (1 + g_pct / 100)
        year = i + 1
        pv_fcfs += fcf / ((1 + r) ** year)

    # Terminal value (Gordon Growth Model applied to final FCF)
    terminal_fcf = fcf * (1 + g_terminal)
    terminal_value = terminal_fcf / (r - g_terminal)
    n = len(growth_rates)
    pv_terminal = terminal_value / ((1 + r) ** n)

    total_equity_value = pv_fcfs + pv_terminal
    return total_equity_value / shares_outstanding


def dcf_sensitivity(
    base_fcf: float,
    growth_rates: List[float],
    terminal_growth_rate: float,
    discount_rates: List[float],   # Range of discount rates to test
    shares_outstanding: float
) -> Dict[float, Optional[float]]:
    """
    Run DCF across a range of discount rates.
    Returns {discount_rate: intrinsic_value_per_share}.
    """
    return {
        r: simple_dcf(base_fcf, growth_rates, terminal_growth_rate, r, shares_outstanding)
        for r in discount_rates
    }


# ---------------------------------------------------------------------------
# Portfolio Calculations
# ---------------------------------------------------------------------------

def position_weight(
    position_value: float,
    total_portfolio_value: float
) -> Optional[float]:
    """Portfolio weight % for a single position."""
    if total_portfolio_value <= 0:
        return None
    return (position_value / total_portfolio_value) * 100


def sector_exposure(
    positions: List[Tuple[str, float, float]]   # (sector, value, portfolio_total)
) -> Dict[str, float]:
    """
    Aggregate portfolio weight by sector.
    positions: list of (sector, position_value, total_portfolio_value)
    Returns {sector: weight_pct}
    """
    sector_totals: Dict[str, float] = {}
    total = sum(v for _, v, _ in positions)
    if total <= 0:
        return {}
    for sector, value, _ in positions:
        sector_totals[sector] = sector_totals.get(sector, 0) + (value / total) * 100
    return sector_totals


def unrealized_gain_loss(
    shares: float,
    average_cost: float,
    current_price: float
) -> Tuple[float, float]:
    """
    Returns (unrealized_gain_loss_amount, unrealized_gain_loss_pct).
    """
    cost_basis = shares * average_cost
    current_value = shares * current_price
    gain_loss = current_value - cost_basis
    gain_loss_pct = ((current_price - average_cost) / average_cost) * 100 if average_cost > 0 else 0.0
    return gain_loss, gain_loss_pct


# ---------------------------------------------------------------------------
# Normalization Utilities
# ---------------------------------------------------------------------------

def normalize_earnings(
    annual_eps: Dict[int, float],
    years: int = 3,
    exclude_outliers: bool = False
) -> Optional[float]:
    """
    Normalized earnings: simple average over N most recent years.

    Optionally exclude the single highest and lowest year (trimmed mean).
    Returns None if insufficient data.
    """
    if not annual_eps:
        return None
    sorted_years = sorted(annual_eps.keys(), reverse=True)
    selected = [annual_eps[y] for y in sorted_years[:years] if annual_eps[y] is not None]
    if not selected:
        return None
    if exclude_outliers and len(selected) >= 4:
        selected = sorted(selected)[1:-1]   # Trim min and max
    return sum(selected) / len(selected)


# ---------------------------------------------------------------------------
# Smoke Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Financial Calculations Smoke Test ===\n")

    # CAGR
    result = cagr(100, 161, 5)
    print(f"CAGR(100→161 over 5yr): {result:.2f}%  (expected ~10.00%)")

    # Annual growth rates
    series = {2019: 100, 2020: 95, 2021: 108, 2022: 120, 2023: 135}
    rates = annual_growth_rates(series)
    print(f"Annual growth rates: {rates}")
    print(f"Growth volatility: {growth_volatility(rates):.2f}%")
    print(f"Negative growth years: {count_negative_growth_years(rates)}")

    # CAGR from series
    print(f"5yr CAGR from series: {extract_cagr_from_series(series, 5):.2f}%")

    # Margins
    print(f"\nGross margin: {gross_margin(1000, 600):.1f}%")
    print(f"Operating margin: {operating_margin(1000, 150):.1f}%")
    print(f"FCF margin: {fcf_margin(1000, 120):.1f}%")

    # Debt
    print(f"\nDebt-to-assets: {debt_to_assets(200, 1000):.1f}%")
    print(f"Interest coverage: {interest_coverage(300, 20):.1f}x")

    # Dividend
    print(f"\nDividend payout: {dividend_payout_ratio(2.5, 8.0):.1f}%")
    print(f"Dividend yield: {dividend_yield(2.5, 180):.2f}%")

    # DCF
    growth_rates = [12.0, 11.0, 10.0, 9.0, 8.0, 7.0, 7.0, 6.0, 6.0, 5.0]
    iv = simple_dcf(
        base_fcf=5_000_000_000,
        growth_rates=growth_rates,
        terminal_growth_rate=3.0,
        discount_rate=9.0,
        shares_outstanding=400_000_000
    )
    print(f"\nDCF intrinsic value per share: ${iv:,.2f}")

    # Sensitivity
    sensitivity = dcf_sensitivity(
        base_fcf=5_000_000_000,
        growth_rates=growth_rates,
        terminal_growth_rate=3.0,
        discount_rates=[7.5, 8.5, 9.0, 9.5, 11.0],
        shares_outstanding=400_000_000
    )
    print("DCF sensitivity (discount rate → value):")
    for r, v in sensitivity.items():
        print(f"  {r}% → ${v:,.2f}")

    print("\n=== All calculations OK ===")
