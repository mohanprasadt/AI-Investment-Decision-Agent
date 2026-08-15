"""
Portfolio Models — Phase 6
==========================
Data models for the Portfolio Context Engine.

Architecture boundary:
  L1 — Portfolio facts (position data, prices, FX rates)
  L2 — Portfolio calculations / context (weights, P/L, concentration, scenarios)
  L3 — Investment interpretation (Phase 7 only — NOT produced here)

Currency handling:
  All positions carry local currency + FX rate to CAD.
  Portfolio-level aggregations use CAD.
  Local currency values are always preserved alongside CAD equivalents.

Cost basis rule:
  Average cost is L1 context — NOT a determinant of investment attractiveness.
  Phase 6 documents cost basis facts but does NOT use them to evaluate whether
  to hold or add to a position. Sunk-cost reasoning is explicitly excluded.

This module does NOT produce BUY / SELL / HOLD / ACCUMULATE / EXIT signals.
"""

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ConcentrationFlagType(Enum):
    POSITION_SIZE  = "PositionSize"
    SECTOR         = "Sector"
    GEOGRAPHY      = "Geography"
    ECONOMIC_GROUP = "EconomicGroup"


class FlagSeverity(Enum):
    NOTE     = "Note"        # Informational — worth tracking
    ELEVATED = "Elevated"    # Meaningful concentration — keep in view
    HIGH     = "High"        # Significant concentration — warrants attention


class PositionType(Enum):
    INCOME   = "Income"      # Primarily dividend / distribution yield
    GROWTH   = "Growth"      # Primarily capital appreciation
    BALANCED = "Balanced"    # Meaningful yield + growth
    REIT     = "REIT"        # Distribution-focused real estate
    ETF      = "ETF"         # Fund / index exposure
    UNKNOWN  = "Unknown"


class PortfolioContextMode(Enum):
    """
    Controls how much portfolio information the user has chosen to provide.

    NONE        — No portfolio information provided. The company is treated as a
                  new-position candidate. Portfolio context is marked "not provided."
                  Overall decision confidence is NOT reduced by this choice.

    WEIGHT_ONLY — User supplies only the current portfolio weight percentage.
                  The system may use the weight for position-size reasoning only.
                  Shares, average cost, total portfolio value, sector weights,
                  and other holdings are NOT requested and NOT inferred.

    FULL        — Complete position details provided (shares, average cost, portfolio
                  value, etc.). This is the richest context but is optional.
                  The system never requires FULL mode for normal analysis.
    """
    NONE        = "NONE"
    WEIGHT_ONLY = "WEIGHT_ONLY"
    FULL        = "FULL"


# ---------------------------------------------------------------------------
# WeightOnlyPortfolioContext
# ---------------------------------------------------------------------------

@dataclass
class WeightOnlyPortfolioContext:
    """
    Privacy-preserving portfolio context: only the portfolio weight is known.

    Design rules (strictly enforced):
    1. Only portfolio_weight_pct is provided — nothing else is assumed.
    2. Shares, average cost, total portfolio value, other holdings,
       sector weights, and geographic weights are explicitly NOT inferred.
    3. is_existing_holding is True (weight > 0 implies existing position).
    4. Concentration flags are NOT generated (would require full portfolio data).
    5. Unrealised P/L is NOT computed (requires average cost and price).
    6. Gate 4 returns MEDIUM confidence — WEIGHT_ONLY is adequate context.
       Overall decision confidence is NOT penalised.
    """
    ticker: str
    portfolio_weight_pct: float          # The ONLY data point provided
    mode: str = PortfolioContextMode.WEIGHT_ONLY.value
    is_existing_holding: bool = True     # Weight > 0 implies existing

    # Explicitly absent — privacy preference, not missing data
    shares_held: None = None
    average_cost_per_share: None = None
    current_price_local: None = None
    position_value_cad: None = None
    unrealized_gain_loss_pct: None = None
    sector: str = ""
    geography: str = ""
    economic_group: str = ""

    # No concentration flags can be derived without full portfolio
    concentration_flags: List = field(default_factory=list)
    portfolio_risks: List[str] = field(default_factory=list)
    incremental_scenarios: List = field(default_factory=list)
    related_holdings: List[str] = field(default_factory=list)

    # Privacy note always present
    privacy_note: str = (
        "Portfolio context mode: WEIGHT_ONLY. "
        "Only portfolio weight was provided. "
        "Shares, average cost, total portfolio value, sector/geographic weights, "
        "and other holdings were not provided and are not inferred. "
        "Concentration analysis is not possible without full portfolio data."
    )
    data_gaps: List[str] = field(default_factory=lambda: [
        "Shares held: not provided (WEIGHT_ONLY mode).",
        "Average cost: not provided (WEIGHT_ONLY mode).",
        "Total portfolio value: not provided (WEIGHT_ONLY mode).",
        "Sector/geographic concentration: not assessable without full portfolio.",
    ])
    context_confidence: str = "MEDIUM"   # WEIGHT_ONLY is sufficient — not LOW

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "ticker": self.ticker,
            "portfolio_weight_pct": self.portfolio_weight_pct,
            "is_existing_holding": self.is_existing_holding,
            "shares_held": None,
            "average_cost_per_share": None,
            "privacy_note": self.privacy_note,
            "data_gaps": self.data_gaps,
            "context_confidence": self.context_confidence,
        }


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """
    A single portfolio holding with full currency provenance.

    Prices and costs are always in local currency.
    FX rate is applied for CAD-denominated portfolio aggregations.

    IMPORTANT: average_cost is context only — it documents the investor's
    entry point but must NOT be used to determine whether to continue
    holding or adding to the position.
    """
    ticker: str
    company_name: str
    shares: float
    average_cost: float           # Per share — local currency (context only)
    current_price: float          # Per share — local currency
    currency: str                 # "CAD" | "USD" | "INR" | etc.
    fx_rate_to_cad: float = 1.0   # 1.0 for CAD positions
    fx_rate_date: str = ""

    # Classification
    sector: str = ""              # e.g. "Energy", "Financials", "Technology"
    geography: str = ""           # e.g. "Canada", "USA", "India"
    exchange: str = ""            # "TSX" | "NASDAQ" | "NYSE" | "NSE"
    economic_group: str = ""      # e.g. "Canadian Banks", "Canadian Energy"
    position_type: PositionType = PositionType.GROWTH

    # Income
    is_dividend_payer: bool = False
    annual_dividend_per_share: float = 0.0   # Local currency

    # -----------------------------------------------------------------------
    # Computed properties
    # -----------------------------------------------------------------------

    def market_value_local(self) -> float:
        """Current market value in local currency (shares × price)."""
        return round(self.shares * self.current_price, 4)

    def market_value_cad(self) -> float:
        """Current market value in CAD."""
        return round(self.market_value_local() * self.fx_rate_to_cad, 4)

    def cost_basis_total_local(self) -> float:
        """Total cost basis in local currency (shares × average_cost)."""
        return round(self.shares * self.average_cost, 4)

    def cost_basis_total_cad(self) -> float:
        """Total cost basis in CAD."""
        return round(self.cost_basis_total_local() * self.fx_rate_to_cad, 4)

    def unrealized_gain_loss_local(self) -> float:
        """Unrealized gain (positive) or loss (negative) in local currency."""
        return round((self.current_price - self.average_cost) * self.shares, 4)

    def unrealized_gain_loss_cad(self) -> float:
        """Unrealized gain/loss in CAD."""
        return round(self.unrealized_gain_loss_local() * self.fx_rate_to_cad, 4)

    def unrealized_gain_loss_pct(self) -> Optional[float]:
        """Unrealized return % vs average cost."""
        if self.average_cost > 0:
            return round(
                (self.current_price - self.average_cost) / self.average_cost * 100, 2
            )
        return None

    def annual_dividend_income_local(self) -> float:
        """Annual dividend income in local currency."""
        return round(self.shares * self.annual_dividend_per_share, 4)

    def annual_dividend_income_cad(self) -> float:
        """Annual dividend income in CAD."""
        return round(self.annual_dividend_income_local() * self.fx_rate_to_cad, 4)

    def dividend_yield_on_cost_pct(self) -> Optional[float]:
        """Dividend yield on average cost basis."""
        if self.average_cost > 0 and self.annual_dividend_per_share > 0:
            return round(self.annual_dividend_per_share / self.average_cost * 100, 2)
        return None

    def dividend_yield_on_current_price_pct(self) -> Optional[float]:
        """Current dividend yield."""
        if self.current_price > 0 and self.annual_dividend_per_share > 0:
            return round(self.annual_dividend_per_share / self.current_price * 100, 2)
        return None

    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "shares": self.shares,
            "average_cost": self.average_cost,
            "current_price": self.current_price,
            "currency": self.currency,
            "fx_rate_to_cad": self.fx_rate_to_cad,
            "fx_rate_date": self.fx_rate_date,
            "market_value_local": self.market_value_local(),
            "market_value_cad": self.market_value_cad(),
            "unrealized_gain_loss_local": self.unrealized_gain_loss_local(),
            "unrealized_gain_loss_pct": self.unrealized_gain_loss_pct(),
            "sector": self.sector,
            "geography": self.geography,
            "exchange": self.exchange,
            "economic_group": self.economic_group,
            "position_type": self.position_type.value,
            "annual_dividend_per_share": self.annual_dividend_per_share,
            "annual_dividend_income_local": self.annual_dividend_income_local(),
            "annual_dividend_income_cad": self.annual_dividend_income_cad(),
        }


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

@dataclass
class Portfolio:
    """
    Collection of positions. Base currency is CAD.
    All multi-currency aggregations convert to CAD via per-position FX rates.
    FX rates must be provided at the same date for consistent cross-currency
    comparisons. Silently mixing stale FX rates is an input error, not a
    Phase 6 responsibility.
    """
    positions: List[Position]
    base_currency: str = "CAD"
    valuation_date: str = ""

    # -----------------------------------------------------------------------

    def total_market_value_cad(self) -> float:
        """Total portfolio value in CAD."""
        return round(sum(p.market_value_cad() for p in self.positions), 4)

    def find_position(self, ticker: str) -> Optional[Position]:
        """Return the Position for the given ticker, or None."""
        for p in self.positions:
            if p.ticker.upper() == ticker.upper():
                return p
        return None

    def sector_weights_pct(self) -> Dict[str, float]:
        """Portfolio weight by sector (% of total CAD value)."""
        total = self.total_market_value_cad()
        if total <= 0:
            return {}
        weights: Dict[str, float] = {}
        for p in self.positions:
            s = p.sector or "Unclassified"
            weights[s] = weights.get(s, 0.0) + p.market_value_cad()
        return {k: round(v / total * 100, 2) for k, v in weights.items()}

    def geography_weights_pct(self) -> Dict[str, float]:
        """Portfolio weight by geography (% of total CAD value)."""
        total = self.total_market_value_cad()
        if total <= 0:
            return {}
        weights: Dict[str, float] = {}
        for p in self.positions:
            g = p.geography or "Unclassified"
            weights[g] = weights.get(g, 0.0) + p.market_value_cad()
        return {k: round(v / total * 100, 2) for k, v in weights.items()}

    def economic_group_weights_pct(self) -> Dict[str, float]:
        """Portfolio weight by economic group (% of total CAD value)."""
        total = self.total_market_value_cad()
        if total <= 0:
            return {}
        weights: Dict[str, float] = {}
        for p in self.positions:
            g = p.economic_group or "Other"
            weights[g] = weights.get(g, 0.0) + p.market_value_cad()
        return {k: round(v / total * 100, 2) for k, v in weights.items()}

    def annual_dividend_income_cad(self) -> float:
        """Total annual dividend income across all positions in CAD."""
        return round(sum(p.annual_dividend_income_cad() for p in self.positions), 4)

    def position_count(self) -> int:
        return len(self.positions)

    def related_tickers(self, ticker: str, economic_group: str) -> List[str]:
        """Other tickers in the same economic group (excluding the ticker itself)."""
        if not economic_group:
            return []
        return [
            p.ticker for p in self.positions
            if p.economic_group == economic_group
            and p.ticker.upper() != ticker.upper()
        ]

    def to_dict(self) -> Dict:
        return {
            "base_currency": self.base_currency,
            "valuation_date": self.valuation_date,
            "position_count": self.position_count(),
            "total_market_value_cad": self.total_market_value_cad(),
            "annual_dividend_income_cad": self.annual_dividend_income_cad(),
            "sector_weights_pct": self.sector_weights_pct(),
            "geography_weights_pct": self.geography_weights_pct(),
        }


# ---------------------------------------------------------------------------
# Concentration flag
# ---------------------------------------------------------------------------

@dataclass
class ConcentrationFlag:
    """
    A concentration observation — context and awareness, NOT a rejection rule.

    A high concentration flag does NOT automatically preclude adding to a
    position. Phase 7 (Decision Engine) weighs this against business quality,
    valuation, and the investor's overall risk tolerance.
    """
    flag_type: ConcentrationFlagType
    severity: FlagSeverity
    dimension: str          # What is concentrated (ticker, sector name, etc.)
    current_pct: float      # Current weight %
    description: str        # Plain-language description
    context: str = (
        "Concentration flag is for awareness only — not an automatic constraint."
    )

    def to_dict(self) -> Dict:
        return {
            "flag_type": self.flag_type.value,
            "severity": self.severity.value,
            "dimension": self.dimension,
            "current_pct": self.current_pct,
            "description": self.description,
            "context": self.context,
        }


# ---------------------------------------------------------------------------
# Incremental investment scenario
# ---------------------------------------------------------------------------

@dataclass
class IncrementalScenario:
    """
    Portfolio impact of a hypothetical additional investment.

    This is scenario modelling only — no investment recommendation is made.
    The investor decides whether, when, and how much to invest.
    """
    investment_amount_cad: float           # Requested CAD amount
    current_price_local: float             # Per share in local currency
    currency: str
    fx_rate_to_cad: float
    shares_purchasable: float              # Floor(amount / price_cad)
    actual_investment_cad: float           # shares × price × fx (may differ from requested)
    shares_held_before: float
    new_total_shares: float
    new_market_value_cad: float
    new_portfolio_weight_pct: float
    weight_change_pct: float               # new - current
    # Cost-basis update — shown as context only, not an anchor for decisions
    new_average_cost_local: Optional[float] = None
    note: str = (
        "Scenario only — no investment recommendation. "
        "Dollar amounts and timing are the investor's decision."
    )

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Master output: PortfolioPositionContext
# ---------------------------------------------------------------------------

@dataclass
class PortfolioPositionContext:
    """
    Phase 6 output — portfolio context for a single position or candidate.

    Architecture boundary:
      L1 — Facts: prices, shares, weights, FX rates
      L2 — Calculations: P/L, sector %, concentration flags, scenarios
      L3 — Investment interpretation: Phase 7 ONLY

    This output does NOT produce BUY / SELL / HOLD / ACCUMULATE / EXIT signals.
    It is a structured context package for Phase 7 (Investment Decision Engine).
    """

    # Identity
    ticker: str
    company_name: str
    valuation_date: str

    # Holding status
    is_existing_holding: bool

    # Position details (zero / None if not currently held)
    shares_held: float = 0.0
    average_cost_per_share: Optional[float] = None
    cost_basis_currency: str = ""

    # Current market data — local currency always primary
    current_price_local: float = 0.0
    price_currency: str = ""
    fx_rate_to_cad: float = 1.0
    fx_rate_date: str = ""
    market_value_local: float = 0.0
    market_value_cad: float = 0.0

    # Portfolio weight
    portfolio_weight_pct: float = 0.0
    total_portfolio_value_cad: float = 0.0

    # Cost basis context — CONTEXT ONLY, not a decision input
    unrealized_gain_loss_local: Optional[float] = None
    unrealized_gain_loss_cad: Optional[float] = None
    unrealized_gain_loss_pct: Optional[float] = None
    cost_basis_note: str = (
        "Average cost is historical context. Investment attractiveness is determined by "
        "current business quality, valuation, and future economics — not by where the "
        "position was originally purchased. Sunk-cost reasoning is not applied."
    )

    # Sector / geography
    sector: str = ""
    geography: str = ""
    sector_weight_in_portfolio_pct: float = 0.0
    geography_weight_in_portfolio_pct: float = 0.0

    # Economic / related-exposure
    economic_group: str = ""
    economic_group_weight_in_portfolio_pct: float = 0.0
    related_holdings: List[str] = field(default_factory=list)

    # Dividend / income
    annual_dividend_per_share_local: float = 0.0
    annual_dividend_income_local: float = 0.0
    annual_dividend_income_cad: float = 0.0
    dividend_yield_on_cost_pct: Optional[float] = None
    dividend_yield_on_current_price_pct: Optional[float] = None
    dividend_contribution_to_portfolio_income_pct: float = 0.0
    position_type: str = PositionType.GROWTH.value

    # Concentration flags
    concentration_flags: List[ConcentrationFlag] = field(default_factory=list)

    # Incremental scenarios
    incremental_scenarios: List[IncrementalScenario] = field(default_factory=list)

    # Valuation zone interaction (populated when ValuationAssessment is provided)
    valuation_zone_label: Optional[str] = None   # WAIT / WATCH / START_SMALL / ACCUMULATE
    fair_value_base_local: Optional[float] = None
    fair_value_bear_local: Optional[float] = None
    fair_value_bull_local: Optional[float] = None
    margin_of_safety_at_current_pct: Optional[float] = None
    required_margin_of_safety_pct: Optional[float] = None
    valuation_confidence: Optional[str] = None

    # Portfolio-level risk observations (L2 — factual, no action implied)
    portfolio_risks: List[str] = field(default_factory=list)

    # Contextual observations (L2 — factual descriptions, not recommendations)
    contextual_observations: List[str] = field(default_factory=list)

    # Data quality
    context_confidence: str = "MEDIUM"   # HIGH / MEDIUM / LOW
    data_gaps: List[str] = field(default_factory=list)

    # Architecture boundary
    for_phase7_note: str = (
        "This is portfolio context only. The investment decision requires combining "
        "financial quality (Phase 3), business research (Phase 4), valuation (Phase 5), "
        "and this portfolio context (Phase 6) in the Phase 7 Decision Engine."
    )

    # -----------------------------------------------------------------------

    def has_concentration_flags(self) -> bool:
        return len(self.concentration_flags) > 0

    def highest_severity_flag(self) -> Optional[FlagSeverity]:
        if not self.concentration_flags:
            return None
        order = {FlagSeverity.NOTE: 0, FlagSeverity.ELEVATED: 1, FlagSeverity.HIGH: 2}
        return max(self.concentration_flags, key=lambda f: order.get(f.severity, 0)).severity

    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "valuation_date": self.valuation_date,
            "is_existing_holding": self.is_existing_holding,
            "shares_held": self.shares_held,
            "average_cost_per_share": self.average_cost_per_share,
            "cost_basis_currency": self.cost_basis_currency,
            "current_price_local": self.current_price_local,
            "price_currency": self.price_currency,
            "fx_rate_to_cad": self.fx_rate_to_cad,
            "fx_rate_date": self.fx_rate_date,
            "market_value_local": self.market_value_local,
            "market_value_cad": self.market_value_cad,
            "portfolio_weight_pct": self.portfolio_weight_pct,
            "total_portfolio_value_cad": self.total_portfolio_value_cad,
            "unrealized_gain_loss_local": self.unrealized_gain_loss_local,
            "unrealized_gain_loss_cad": self.unrealized_gain_loss_cad,
            "unrealized_gain_loss_pct": self.unrealized_gain_loss_pct,
            "cost_basis_note": self.cost_basis_note,
            "sector": self.sector,
            "geography": self.geography,
            "sector_weight_in_portfolio_pct": self.sector_weight_in_portfolio_pct,
            "geography_weight_in_portfolio_pct": self.geography_weight_in_portfolio_pct,
            "economic_group": self.economic_group,
            "economic_group_weight_in_portfolio_pct": self.economic_group_weight_in_portfolio_pct,
            "related_holdings": self.related_holdings,
            "annual_dividend_per_share_local": self.annual_dividend_per_share_local,
            "annual_dividend_income_local": self.annual_dividend_income_local,
            "annual_dividend_income_cad": self.annual_dividend_income_cad,
            "dividend_yield_on_cost_pct": self.dividend_yield_on_cost_pct,
            "dividend_yield_on_current_price_pct": self.dividend_yield_on_current_price_pct,
            "dividend_contribution_to_portfolio_income_pct": self.dividend_contribution_to_portfolio_income_pct,
            "position_type": self.position_type,
            "concentration_flags": [f.to_dict() for f in self.concentration_flags],
            "incremental_scenarios": [s.to_dict() for s in self.incremental_scenarios],
            "valuation_zone_label": self.valuation_zone_label,
            "fair_value_base_local": self.fair_value_base_local,
            "fair_value_bear_local": self.fair_value_bear_local,
            "fair_value_bull_local": self.fair_value_bull_local,
            "margin_of_safety_at_current_pct": self.margin_of_safety_at_current_pct,
            "required_margin_of_safety_pct": self.required_margin_of_safety_pct,
            "valuation_confidence": self.valuation_confidence,
            "portfolio_risks": self.portfolio_risks,
            "contextual_observations": self.contextual_observations,
            "context_confidence": self.context_confidence,
            "data_gaps": self.data_gaps,
            "for_phase7_note": self.for_phase7_note,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path) -> None:
        from pathlib import Path
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
