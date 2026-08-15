"""
Incremental Investment Scenarios — Phase 6
==========================================
Models the portfolio impact of hypothetical additional investments.

Design rules:
  - No investment recommendation is made — the investor decides whether,
    when, and how much to invest.
  - Scenarios show portfolio mechanics only: shares purchasable, new weight,
    weight delta, updated cost basis (as informational context only).
  - Cost basis update in the scenario is shown to complete the picture —
    it is NOT a reason to invest or not invest.
  - Fractional shares are not assumed by default (floor rounding).
    Override allow_fractional=True for ETFs and brokers that support it.
  - If the requested CAD amount cannot buy even one share, the scenario
    is returned with 0 shares and a note rather than being omitted.
"""

import math
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.portfolio.portfolio_models import IncrementalScenario


def build_incremental_scenarios(
    scenario_amounts_cad: List[float],
    current_price_local: float,
    currency: str,
    fx_rate_to_cad: float,
    shares_held: float,
    average_cost_local: Optional[float],
    current_portfolio_value_cad: float,
    current_position_value_cad: float,
    allow_fractional: bool = False,
) -> List[IncrementalScenario]:
    """
    Build a scenario for each requested CAD investment amount.

    Parameters
    ----------
    scenario_amounts_cad   : List of CAD amounts to model (e.g. [500, 1000, 2000])
    current_price_local    : Per-share price in local currency
    currency               : Local currency code (CAD, USD, INR)
    fx_rate_to_cad         : Conversion rate local → CAD
    shares_held            : Current shares (0 for new position)
    average_cost_local     : Current average cost per share in local currency (None if new)
    current_portfolio_value_cad : Total portfolio value before investment
    current_position_value_cad  : Current position market value in CAD
    allow_fractional       : If True, fractional shares allowed (for ETFs)

    Returns
    -------
    List[IncrementalScenario] — one per scenario amount, always returned even
    if amount is too small to buy a share (shares_purchasable=0 in that case).
    """
    scenarios: List[IncrementalScenario] = []

    price_in_cad = current_price_local * fx_rate_to_cad
    if price_in_cad <= 0:
        return []

    for amount_cad in scenario_amounts_cad:
        if amount_cad <= 0:
            continue

        # Shares purchasable
        if allow_fractional:
            shares_purchasable = round(amount_cad / price_in_cad, 6)
        else:
            shares_purchasable = math.floor(amount_cad / price_in_cad)

        actual_investment_cad = round(shares_purchasable * price_in_cad, 4)
        new_total_shares = shares_held + shares_purchasable
        new_position_value_cad = current_position_value_cad + actual_investment_cad
        new_portfolio_total_cad = current_portfolio_value_cad + actual_investment_cad

        new_weight = (
            round(new_position_value_cad / new_portfolio_total_cad * 100, 4)
            if new_portfolio_total_cad > 0 else 0.0
        )
        current_weight = (
            round(current_position_value_cad / current_portfolio_value_cad * 100, 4)
            if current_portfolio_value_cad > 0 else 0.0
        )
        weight_change = round(new_weight - current_weight, 4)

        # Updated average cost — context only, not a decision anchor
        new_avg_cost: Optional[float] = None
        if shares_purchasable > 0 and new_total_shares > 0:
            if average_cost_local is not None and shares_held > 0:
                total_cost = (average_cost_local * shares_held) + (current_price_local * shares_purchasable)
                new_avg_cost = round(total_cost / new_total_shares, 4)
            else:
                # New position: average cost = purchase price
                new_avg_cost = current_price_local

        if shares_purchasable == 0:
            note = (
                f"CAD {amount_cad:,.0f} is insufficient to purchase one share "
                f"at {current_price_local:.2f} {currency} "
                f"({price_in_cad:.2f} CAD/share). "
                "Consider a larger amount or a broker that supports fractional shares."
            )
        else:
            note = (
                "Scenario only — no investment recommendation. "
                "Dollar amounts and timing are the investor's decision."
            )

        scenarios.append(IncrementalScenario(
            investment_amount_cad=amount_cad,
            current_price_local=current_price_local,
            currency=currency,
            fx_rate_to_cad=fx_rate_to_cad,
            shares_purchasable=shares_purchasable,
            actual_investment_cad=actual_investment_cad,
            shares_held_before=shares_held,
            new_total_shares=new_total_shares,
            new_market_value_cad=round(new_position_value_cad, 4),
            new_portfolio_weight_pct=new_weight,
            weight_change_pct=weight_change,
            new_average_cost_local=new_avg_cost,
            note=note,
        ))

    return scenarios
