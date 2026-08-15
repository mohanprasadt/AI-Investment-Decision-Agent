"""
Portfolio Calculator — Phase 6
================================
Pure calculation functions for portfolio-level metrics.
All inputs and outputs are deterministic — no side effects.

Multi-currency notes:
  - All per-position values stay in local currency until explicitly converted.
  - Portfolio aggregations use CAD via each Position's fx_rate_to_cad.
  - Never mix local-currency values across different currencies without FX.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.portfolio.portfolio_models import Portfolio, Position


# ---------------------------------------------------------------------------
# Weight calculations
# ---------------------------------------------------------------------------

def position_weight_pct(market_value_cad: float, total_portfolio_cad: float) -> float:
    """Portfolio weight of a position as % of total (CAD)."""
    if total_portfolio_cad <= 0:
        return 0.0
    return round(market_value_cad / total_portfolio_cad * 100, 4)


def hypothetical_weight_pct(
    additional_cad: float,
    current_position_cad: float,
    total_portfolio_cad: float,
) -> float:
    """
    Portfolio weight if 'additional_cad' is added to a position.
    Assumes the total portfolio value grows by the same amount.
    """
    new_position_cad = current_position_cad + additional_cad
    new_total_cad = total_portfolio_cad + additional_cad
    if new_total_cad <= 0:
        return 0.0
    return round(new_position_cad / new_total_cad * 100, 4)


# ---------------------------------------------------------------------------
# Dividend calculations
# ---------------------------------------------------------------------------

def dividend_contribution_to_portfolio_income_pct(
    position_annual_income_cad: float,
    portfolio_annual_income_cad: float,
) -> float:
    """
    Share of total portfolio dividend income from this position.
    Returns 0 if portfolio has no dividend income.
    """
    if portfolio_annual_income_cad <= 0:
        return 0.0
    return round(position_annual_income_cad / portfolio_annual_income_cad * 100, 2)


# ---------------------------------------------------------------------------
# Concentration calculations
# ---------------------------------------------------------------------------

def sector_weight_for(sector: str, portfolio: Portfolio) -> float:
    """Current % weight of a sector in the portfolio."""
    weights = portfolio.sector_weights_pct()
    return weights.get(sector, 0.0)


def geography_weight_for(geography: str, portfolio: Portfolio) -> float:
    """Current % weight of a geography in the portfolio."""
    weights = portfolio.geography_weights_pct()
    return weights.get(geography, 0.0)


def economic_group_weight_for(group: str, portfolio: Portfolio) -> float:
    """Current % weight of an economic group in the portfolio."""
    if not group:
        return 0.0
    weights = portfolio.economic_group_weights_pct()
    return weights.get(group, 0.0)


# ---------------------------------------------------------------------------
# Hypothetical sector / geography weight after investment
# ---------------------------------------------------------------------------

def hypothetical_sector_weight_pct(
    sector: str,
    additional_cad: float,
    portfolio: Portfolio,
) -> float:
    """
    Sector weight % if 'additional_cad' is added to a position in 'sector'.
    Assumes the additional amount stays in the same sector.
    """
    total = portfolio.total_market_value_cad()
    current_sector_cad = sum(
        p.market_value_cad() for p in portfolio.positions
        if (p.sector or "Unclassified") == sector
    )
    new_sector_cad = current_sector_cad + additional_cad
    new_total = total + additional_cad
    if new_total <= 0:
        return 0.0
    return round(new_sector_cad / new_total * 100, 2)


# ---------------------------------------------------------------------------
# Unrealized P/L
# ---------------------------------------------------------------------------

def unrealized_gain_loss_local(position: Position) -> float:
    return position.unrealized_gain_loss_local()


def unrealized_gain_loss_cad(position: Position) -> float:
    return position.unrealized_gain_loss_cad()


def unrealized_gain_loss_pct(position: Position) -> Optional[float]:
    return position.unrealized_gain_loss_pct()


# ---------------------------------------------------------------------------
# Data-gap detection
# ---------------------------------------------------------------------------

def detect_data_gaps(
    ticker: str,
    is_existing_holding: bool,
    position: Optional[Position],
    sector: str,
    geography: str,
) -> List[str]:
    """Return a list of missing or incomplete data items."""
    gaps = []
    if is_existing_holding and position is None:
        gaps.append(f"Position for {ticker} not found in portfolio.")
    if not sector:
        gaps.append("Sector classification not provided.")
    if not geography:
        gaps.append("Geography classification not provided.")
    if is_existing_holding and position:
        if position.shares <= 0:
            gaps.append("Shares held is zero or negative.")
        if position.average_cost <= 0:
            gaps.append("Average cost is zero — cost-basis context unavailable.")
        if position.current_price <= 0:
            gaps.append("Current price is zero.")
        if position.fx_rate_to_cad <= 0:
            gaps.append("FX rate to CAD is missing or invalid.")
    return gaps


def context_confidence(data_gaps: List[str]) -> str:
    """Derive overall context confidence from data gaps."""
    if not data_gaps:
        return "HIGH"
    if len(data_gaps) <= 2:
        return "MEDIUM"
    return "LOW"
