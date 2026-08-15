"""
Financial Metrics Data Model
============================
Defines the data structures for storing and validating financial metrics.
This module is intentionally pure-Python (no external dependencies beyond stdlib)
so it can be used as a foundation before any data ingestion layer is built.

Python performs all calculations; Claude performs all qualitative interpretation.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List
from datetime import date
import json


# ---------------------------------------------------------------------------
# Enums / Constants
# ---------------------------------------------------------------------------

class MetricClassification:
    """Human-readable classification labels applied after threshold comparison."""
    EXCELLENT = "Excellent"
    STRONG = "Strong"
    GOOD = "Good"
    WATCH = "Watch"
    CONCERN = "Concern"
    HIGH_CONCERN = "High Concern"
    NOT_AVAILABLE = "N/A"


class Trend:
    IMPROVING = "Improving"
    STABLE = "Stable"
    DETERIORATING = "Deteriorating"
    VOLATILE = "Volatile"
    INSUFFICIENT_DATA = "Insufficient Data"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

@dataclass
class RevenueGrowthMetrics:
    """Revenue growth analysis."""
    annual_revenues: Dict[int, float] = field(default_factory=dict)   # {year: revenue}
    cagr_3yr: Optional[float] = None     # %
    cagr_5yr: Optional[float] = None     # %
    cagr_10yr: Optional[float] = None    # %
    annual_growth_rates: Dict[int, float] = field(default_factory=dict)  # {year: % growth}
    negative_growth_years: int = 0
    growth_volatility: Optional[float] = None   # std dev of annual growth rates
    organic_vs_acquisition_note: str = ""
    consistency_classification: str = ""
    trend: str = ""
    data_years_available: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ROICMetrics:
    """Return on Invested Capital analysis."""
    annual_roic: Dict[int, float] = field(default_factory=dict)   # {year: ROIC %}
    current: Optional[float] = None
    avg_3yr: Optional[float] = None
    avg_5yr: Optional[float] = None
    trend: str = ""
    classification: str = ""
    moat_support_note: str = ""   # ROIC supports/challenges moat thesis?
    calculation_note: str = ""   # e.g., "Goodwill excluded/included"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MarginMetrics:
    """Margin analysis across gross, operating, net, FCF."""
    # Current year
    gross_margin: Optional[float] = None          # %
    operating_margin: Optional[float] = None      # %
    net_margin: Optional[float] = None            # %
    fcf_margin: Optional[float] = None            # %

    # Historical (year: value)
    gross_margin_history: Dict[int, float] = field(default_factory=dict)
    operating_margin_history: Dict[int, float] = field(default_factory=dict)
    net_margin_history: Dict[int, float] = field(default_factory=dict)
    fcf_margin_history: Dict[int, float] = field(default_factory=dict)

    # Trends
    gross_margin_trend: str = ""
    operating_margin_trend: str = ""
    net_margin_trend: str = ""
    margin_change_explanation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FreeCashFlowMetrics:
    """Free cash flow quality analysis."""
    annual_fcf: Dict[int, float] = field(default_factory=dict)         # {year: FCF}
    annual_capex: Dict[int, float] = field(default_factory=dict)       # {year: capex}
    annual_net_income: Dict[int, float] = field(default_factory=dict)  # {year: net income}
    # Directly extracted operating cash flow series (Phase 9.9).
    # Stored here so the reconciliation handler can show persisted OCF rather
    # than re-deriving it as FCF − capex.  Populated by normalizer.py.
    annual_ocf: Dict[int, float] = field(default_factory=dict)         # {year: operating CF}

    fcf_current: Optional[float] = None
    fcf_margin_current: Optional[float] = None    # %
    fcf_conversion_ratio: Optional[float] = None  # FCF / Net Income
    capex_as_pct_revenue: Optional[float] = None  # %

    fcf_trend: str = ""
    fcf_consistency: str = ""
    recurring_negative_fcf: bool = False
    negative_fcf_years: int = 0
    fcf_quality_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DebtMetrics:
    """Balance sheet / leverage analysis."""
    total_assets: Optional[float] = None
    interest_bearing_debt: Optional[float] = None    # NOT total liabilities
    total_liabilities: Optional[float] = None        # for context only
    accounts_payable: Optional[float] = None         # to explicitly separate

    debt_to_assets_pct: Optional[float] = None       # interest-bearing debt / total assets
    interest_coverage: Optional[float] = None        # EBIT / interest expense
    fcf_to_debt_ratio: Optional[float] = None        # FCF / interest-bearing debt
    net_debt: Optional[float] = None                 # debt - cash

    debt_trend: str = ""
    classification: str = ""
    industry_context_note: str = ""
    debt_analysis_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DividendMetrics:
    """Dividend quality analysis."""
    pays_dividend: bool = False
    current_yield_pct: Optional[float] = None
    annual_dividend_per_share: Optional[float] = None
    payout_ratio_pct: Optional[float] = None          # Dividend / EPS
    fcf_payout_ratio_pct: Optional[float] = None      # Dividend / FCF per share

    dividend_growth_1yr: Optional[float] = None       # %
    dividend_growth_3yr_cagr: Optional[float] = None  # %
    dividend_growth_5yr_cagr: Optional[float] = None  # %

    annual_dividends: Dict[int, float] = field(default_factory=dict)  # {year: DPS}
    years_of_dividend_history: int = 0
    dividend_cuts: int = 0

    sustainability_classification: str = ""
    sustainability_note: str = ""
    high_yield_investigation_note: str = ""   # populated if yield > threshold

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EarningsQualityMetrics:
    """Earnings quality — relationship between accounting earnings and cash."""
    annual_eps: Dict[int, float] = field(default_factory=dict)     # {year: EPS}
    annual_revenue: Dict[int, float] = field(default_factory=dict)  # {year: revenue}
    annual_net_income: Dict[int, float] = field(default_factory=dict)

    eps_trend: str = ""
    eps_consistency: str = ""
    revenue_vs_fcf_divergence: bool = False    # Flag: revenue up, FCF down
    eps_vs_cashflow_divergence: bool = False   # Flag: EPS up, operating economics worsening
    earnings_quality_note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Master Financial Metrics Model
# ---------------------------------------------------------------------------

@dataclass
class CompanyFinancialMetrics:
    """
    Master container for all financial metrics of a single company.

    Created by the data ingestion layer (Phase 2).
    Consumed by the Financial Quality Engine (Phase 3).
    """
    # Identification
    ticker: str = ""
    company_name: str = ""
    exchange: str = ""
    currency: str = ""
    fiscal_year_end_month: int = 12
    data_source: str = ""
    data_as_of_date: str = ""       # ISO date string
    retrieved_at: str = ""

    # Financial statement data
    revenue_growth: RevenueGrowthMetrics = field(default_factory=RevenueGrowthMetrics)
    roic: ROICMetrics = field(default_factory=ROICMetrics)
    margins: MarginMetrics = field(default_factory=MarginMetrics)
    free_cash_flow: FreeCashFlowMetrics = field(default_factory=FreeCashFlowMetrics)
    debt: DebtMetrics = field(default_factory=DebtMetrics)
    dividend: DividendMetrics = field(default_factory=DividendMetrics)
    earnings_quality: EarningsQualityMetrics = field(default_factory=EarningsQualityMetrics)

    # Market data
    current_price: Optional[float] = None
    market_cap: Optional[float] = None
    enterprise_value: Optional[float] = None
    pe_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    price_to_fcf: Optional[float] = None
    price_to_sales: Optional[float] = None

    # Data quality flags
    data_completeness_pct: Optional[float] = None
    missing_fields: List[str] = field(default_factory=list)
    data_quality_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "CompanyFinancialMetrics":
        """Reconstruct from a previously serialized dict."""
        obj = cls()
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
        return obj

    def validate(self) -> List[str]:
        """
        Basic validation. Returns list of warnings/issues found.
        Does NOT raise exceptions — flags issues for human review.
        """
        issues = []
        if not self.ticker:
            issues.append("Missing ticker")
        if not self.data_as_of_date:
            issues.append("Missing data_as_of_date — always required for staleness tracking")
        if self.debt.interest_bearing_debt is not None and self.debt.total_liabilities is not None:
            if self.debt.interest_bearing_debt > self.debt.total_liabilities:
                issues.append("interest_bearing_debt > total_liabilities — check data")
        if self.dividend.pays_dividend and self.dividend.current_yield_pct is None:
            issues.append("Company pays dividend but current_yield_pct is missing")
        if self.revenue_growth.cagr_5yr is not None and self.revenue_growth.data_years_available < 5:
            issues.append("5yr CAGR reported but fewer than 5 years of data available")
        return issues


# ---------------------------------------------------------------------------
# Portfolio Position Model
# ---------------------------------------------------------------------------

@dataclass
class PortfolioPosition:
    """
    Represents a single holding in the investment portfolio.
    Sensitive — store locally only; never transmit credentials or account info.
    """
    ticker: str = ""
    company_name: str = ""
    exchange: str = ""
    currency: str = ""
    shares: float = 0.0
    average_cost: float = 0.0          # Per share, in position's currency
    current_price: Optional[float] = None
    current_value: Optional[float] = None   # shares × current_price
    portfolio_weight_pct: Optional[float] = None

    sector: str = ""
    geography: str = ""
    dividend_yield_pct: Optional[float] = None

    original_thesis_summary: str = ""
    thesis_status: str = ""            # Intact / Weakened / Broken / Under Review
    last_review_date: str = ""
    notes: str = ""

    def unrealized_gain_loss(self) -> Optional[float]:
        """Unrealized gain/loss in position currency."""
        if self.current_price is not None and self.shares and self.average_cost:
            return (self.current_price - self.average_cost) * self.shares
        return None

    def unrealized_gain_loss_pct(self) -> Optional[float]:
        """Unrealized gain/loss as % of cost basis."""
        if self.current_price is not None and self.average_cost:
            return ((self.current_price - self.average_cost) / self.average_cost) * 100
        return None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Watchlist Item Model
# ---------------------------------------------------------------------------

@dataclass
class WatchlistItem:
    """
    Represents a company under active monitoring on the watchlist.
    """
    ticker: str = ""
    company_name: str = ""
    exchange: str = ""
    currency: str = ""
    reason_for_watching: str = ""

    fair_value_low: Optional[float] = None
    fair_value_high: Optional[float] = None
    fair_value_currency: str = ""
    current_price: Optional[float] = None

    accumulation_zone: str = ""        # WAIT / WATCH / START_SMALL / ACCUMULATE
    moat_status: str = ""              # Confirmed / Emerging / None / Under Review
    moat_strength: str = ""
    thesis_status: str = ""
    last_review_date: str = ""
    priority: str = ""                 # High / Medium / Low
    notes: str = ""

    def is_in_accumulation_zone(self) -> Optional[bool]:
        """Returns True if current price is within or below the fair value range."""
        if self.current_price and self.fair_value_low and self.fair_value_high:
            return self.current_price <= self.fair_value_high
        return None

    def discount_to_fair_value_midpoint_pct(self) -> Optional[float]:
        """Premium/discount vs midpoint of fair value range."""
        if self.current_price and self.fair_value_low and self.fair_value_high:
            midpoint = (self.fair_value_low + self.fair_value_high) / 2
            return ((self.current_price - midpoint) / midpoint) * 100
        return None

    def to_dict(self) -> dict:
        return asdict(self)


if __name__ == "__main__":
    # Quick smoke test
    metrics = CompanyFinancialMetrics(
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        currency="USD",
        data_as_of_date="2024-12-31"
    )
    issues = metrics.validate()
    print(f"Validation issues: {issues}")
    print("CompanyFinancialMetrics model: OK")

    pos = PortfolioPosition(
        ticker="CNR.TO",
        company_name="Canadian National Railway",
        exchange="TSX",
        currency="CAD",
        shares=100,
        average_cost=170.0,
        current_price=180.0
    )
    print(f"Unrealized gain: CAD ${pos.unrealized_gain_loss():,.2f} ({pos.unrealized_gain_loss_pct():.1f}%)")
    print("PortfolioPosition model: OK")

    watch = WatchlistItem(
        ticker="COST",
        company_name="Costco Wholesale",
        fair_value_low=680.0,
        fair_value_high=750.0,
        current_price=710.0
    )
    print(f"Discount/premium to fair value: {watch.discount_to_fair_value_midpoint_pct():.1f}%")
    print("WatchlistItem model: OK")
