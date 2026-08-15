"""
Portfolio Synthesizer — Phase 6
================================
Orchestrates the full portfolio-context workflow:

  1. Look up the position in the portfolio (existing or new candidate)
  2. Calculate weight, P/L, sector/geography/economic-group context
  3. Analyse concentration across all four dimensions
  4. Build incremental investment scenarios
  5. Integrate valuation zone from Phase 5 (optional)
  6. Generate contextual observations (L2 only — no recommendations)
  7. Package into PortfolioPositionContext

Architecture boundary:
  This module is the top-level entry point for Phase 6.
  It does NOT produce BUY / SELL / HOLD / ACCUMULATE / EXIT signals.
  The PortfolioPositionContext it produces feeds Phase 7 (Decision Engine).

Cost basis rule (strictly enforced):
  Average cost is shown as historical context.
  Contextual observations reference current business, valuation, and
  portfolio fit — never the original purchase price as a decision anchor.

Currency handling:
  All per-position values are in local currency.
  Portfolio aggregations are in CAD.
  FX rates provided by the caller; they are never fetched here.
"""

import sys
from pathlib import Path
from typing import List, Optional, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.portfolio.portfolio_models import (
    Portfolio, Position, PortfolioPositionContext,
    ConcentrationFlag, IncrementalScenario, PositionType,
)
from analytics.portfolio.portfolio_calculator import (
    position_weight_pct,
    sector_weight_for,
    geography_weight_for,
    economic_group_weight_for,
    dividend_contribution_to_portfolio_income_pct,
    detect_data_gaps,
    context_confidence,
)
from analytics.portfolio.concentration_analyzer import analyze_concentration
from analytics.portfolio.incremental_scenarios import build_incremental_scenarios


# ---------------------------------------------------------------------------
# Default scenario amounts (CAD) — always shown unless caller overrides
# ---------------------------------------------------------------------------
_DEFAULT_SCENARIO_AMOUNTS_CAD = [500.0, 1_000.0, 2_000.0, 5_000.0]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def build_portfolio_context(
    portfolio: Portfolio,
    ticker: str,
    # Required when ticker is not in portfolio (new candidate):
    company_name: str = "",
    current_price_local: Optional[float] = None,
    currency: str = "",
    fx_rate_to_cad: float = 0.0,   # 0 = "use portfolio position's rate"
    fx_rate_date: str = "",
    sector: str = "",
    geography: str = "",
    economic_group: str = "",
    annual_dividend_per_share: float = 0.0,
    position_type: str = "",
    # Optional Phase 5 output for valuation-zone integration:
    valuation_assessment: Optional[Any] = None,   # ValuationAssessment
    # Scenario amounts in CAD (None → use defaults)
    scenario_amounts_cad: Optional[List[float]] = None,
) -> PortfolioPositionContext:
    """
    Build a PortfolioPositionContext for an existing holding or a new candidate.

    For existing holdings: pulls position data from portfolio (overridable by caller).
    For new candidates: all position fields default to zero; scenarios still run.

    Parameters
    ----------
    portfolio              : The current portfolio snapshot
    ticker                 : Stock ticker (exchange-qualified e.g. "CNR.TO")
    company_name           : Company display name (used if not in portfolio)
    current_price_local    : Per-share price in local currency (overrides portfolio if provided)
    currency               : Reporting currency code
    fx_rate_to_cad         : FX rate local→CAD (1.0 for CAD positions)
    fx_rate_date           : Date of FX rate (ISO string)
    sector                 : Sector classification
    geography              : Geography (e.g. "Canada", "USA", "India")
    economic_group         : Related-exposure group (e.g. "Canadian Banks")
    annual_dividend_per_share : Annual DPS in local currency
    position_type          : "INCOME" / "GROWTH" / "BALANCED" / "REIT" / "ETF"
    valuation_assessment   : Phase 5 ValuationAssessment (optional)
    scenario_amounts_cad   : CAD amounts to model; defaults to [500, 1000, 2000, 5000]
    """
    amounts = scenario_amounts_cad or _DEFAULT_SCENARIO_AMOUNTS_CAD

    # --- Step 1: Resolve position ---
    existing = portfolio.find_position(ticker)
    is_existing = existing is not None

    # Override / fill from portfolio position if found
    if existing:
        _name          = company_name or existing.company_name
        _price         = current_price_local if current_price_local is not None else existing.current_price
        _currency      = currency or existing.currency          # prefer position's currency
        _fx            = fx_rate_to_cad if fx_rate_to_cad > 0 else existing.fx_rate_to_cad
        _fx_date       = fx_rate_date or existing.fx_rate_date
        _sector        = sector or existing.sector
        _geography     = geography or existing.geography
        _eco_group     = economic_group or existing.economic_group
        _div_ps        = annual_dividend_per_share or existing.annual_dividend_per_share
        _pos_type      = position_type or existing.position_type.value  # prefer position type
        _shares        = existing.shares
        _avg_cost      = existing.average_cost
    else:
        _name          = company_name or ticker
        _price         = current_price_local or 0.0
        _currency      = currency or "CAD"
        _fx            = fx_rate_to_cad if fx_rate_to_cad > 0 else 1.0
        _fx_date       = fx_rate_date
        _sector        = sector
        _geography     = geography
        _eco_group     = economic_group
        _div_ps        = annual_dividend_per_share
        _pos_type      = position_type or PositionType.GROWTH.value
        _shares        = 0.0
        _avg_cost      = None

    # --- Step 2: Market value ---
    mv_local = round(_shares * _price, 4) if _shares > 0 and _price > 0 else 0.0
    mv_cad   = round(mv_local * _fx, 4)
    total_cad = portfolio.total_market_value_cad()
    weight_pct = position_weight_pct(mv_cad, total_cad)

    # --- Step 3: Unrealized P/L ---
    ugl_local: Optional[float] = None
    ugl_cad:   Optional[float] = None
    ugl_pct:   Optional[float] = None
    if is_existing and _avg_cost and _avg_cost > 0 and _shares > 0 and _price > 0:
        ugl_local = round((_price - _avg_cost) * _shares, 4)
        ugl_cad   = round(ugl_local * _fx, 4)
        ugl_pct   = round((_price - _avg_cost) / _avg_cost * 100, 2)

    # --- Step 4: Sector / geography / economic group ---
    sector_wt  = sector_weight_for(_sector, portfolio)
    geo_wt     = geography_weight_for(_geography, portfolio)
    eco_wt     = economic_group_weight_for(_eco_group, portfolio) if _eco_group else 0.0
    related    = portfolio.related_tickers(ticker, _eco_group)

    # --- Step 5: Dividend / income ---
    div_income_local = round(_shares * _div_ps, 4)
    div_income_cad   = round(div_income_local * _fx, 4)
    port_div_cad     = portfolio.annual_dividend_income_cad()
    div_contrib_pct  = dividend_contribution_to_portfolio_income_pct(div_income_cad, port_div_cad)

    div_yield_cost: Optional[float] = None
    div_yield_price: Optional[float] = None
    if _div_ps > 0:
        if _avg_cost and _avg_cost > 0:
            div_yield_cost = round(_div_ps / _avg_cost * 100, 2)
        if _price > 0:
            div_yield_price = round(_div_ps / _price * 100, 2)

    # --- Step 6: Concentration ---
    flags = analyze_concentration(
        ticker=ticker,
        sector=_sector,
        geography=_geography,
        economic_group=_eco_group,
        position_weight_pct=weight_pct,
        sector_weight_pct=sector_wt,
        geography_weight_pct=geo_wt,
        economic_group_weight_pct=eco_wt,
    )

    # --- Step 7: Incremental scenarios ---
    scenarios = build_incremental_scenarios(
        scenario_amounts_cad=amounts,
        current_price_local=_price,
        currency=_currency,
        fx_rate_to_cad=_fx,
        shares_held=_shares,
        average_cost_local=_avg_cost,
        current_portfolio_value_cad=total_cad,
        current_position_value_cad=mv_cad,
    )

    # --- Step 8: Valuation zone integration ---
    val_zone     = None
    fv_base      = None
    fv_bear      = None
    fv_bull      = None
    mos_actual   = None
    mos_required = None
    val_conf     = None
    if valuation_assessment is not None:
        try:
            az = getattr(valuation_assessment, 'accumulation_zone', None)
            if az:
                val_zone = az.zone.value if hasattr(az.zone, 'value') else str(az.zone)
                mos_actual   = getattr(az, 'actual_margin_of_safety_pct', None)
                mos_required = getattr(az, 'required_margin_of_safety_pct', None)
            fvr = getattr(valuation_assessment, 'fair_value_range', None)
            if fvr:
                fv_base = getattr(fvr, 'base', None)
                fv_bear = getattr(fvr, 'bear', None)
                fv_bull = getattr(fvr, 'bull', None)
            conf_obj = getattr(valuation_assessment, 'overall_confidence', None)
            val_conf = conf_obj.value if hasattr(conf_obj, 'value') else str(conf_obj)
        except Exception:
            pass  # Valuation context is optional; don't crash Phase 6

    # --- Step 9: Contextual observations ---
    observations = _build_observations(
        ticker=ticker,
        is_existing=is_existing,
        shares=_shares,
        price=_price,
        currency=_currency,
        weight_pct=weight_pct,
        sector=_sector,
        sector_wt=sector_wt,
        geography=_geography,
        geo_wt=geo_wt,
        eco_group=_eco_group,
        eco_wt=eco_wt,
        related=related,
        ugl_pct=ugl_pct,
        div_income_cad=div_income_cad,
        div_contrib_pct=div_contrib_pct,
        val_zone=val_zone,
        fv_base=fv_base,
        mos_actual=mos_actual,
        mos_required=mos_required,
    )

    # --- Step 10: Portfolio risks ---
    risks = _build_portfolio_risks(
        flags=flags,
        related=related,
        eco_group=_eco_group,
    )

    # --- Step 11: Data gaps and confidence ---
    gaps = detect_data_gaps(ticker, is_existing, existing, _sector, _geography)
    conf = context_confidence(gaps)

    return PortfolioPositionContext(
        ticker=ticker,
        company_name=_name,
        valuation_date=portfolio.valuation_date,
        is_existing_holding=is_existing,
        shares_held=_shares,
        average_cost_per_share=_avg_cost,
        cost_basis_currency=_currency,
        current_price_local=_price,
        price_currency=_currency,
        fx_rate_to_cad=_fx,
        fx_rate_date=_fx_date,
        market_value_local=mv_local,
        market_value_cad=mv_cad,
        portfolio_weight_pct=weight_pct,
        total_portfolio_value_cad=total_cad,
        unrealized_gain_loss_local=ugl_local,
        unrealized_gain_loss_cad=ugl_cad,
        unrealized_gain_loss_pct=ugl_pct,
        sector=_sector,
        geography=_geography,
        sector_weight_in_portfolio_pct=sector_wt,
        geography_weight_in_portfolio_pct=geo_wt,
        economic_group=_eco_group,
        economic_group_weight_in_portfolio_pct=eco_wt,
        related_holdings=related,
        annual_dividend_per_share_local=_div_ps,
        annual_dividend_income_local=div_income_local,
        annual_dividend_income_cad=div_income_cad,
        dividend_yield_on_cost_pct=div_yield_cost,
        dividend_yield_on_current_price_pct=div_yield_price,
        dividend_contribution_to_portfolio_income_pct=div_contrib_pct,
        position_type=_pos_type,
        concentration_flags=flags,
        incremental_scenarios=scenarios,
        valuation_zone_label=val_zone,
        fair_value_base_local=fv_base,
        fair_value_bear_local=fv_bear,
        fair_value_bull_local=fv_bull,
        margin_of_safety_at_current_pct=mos_actual,
        required_margin_of_safety_pct=mos_required,
        valuation_confidence=val_conf,
        portfolio_risks=risks,
        contextual_observations=observations,
        context_confidence=conf,
        data_gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Observation builder — L2 context only, never L3 recommendations
# ---------------------------------------------------------------------------

def _build_observations(
    ticker: str,
    is_existing: bool,
    shares: float,
    price: float,
    currency: str,
    weight_pct: float,
    sector: str,
    sector_wt: float,
    geography: str,
    geo_wt: float,
    eco_group: str,
    eco_wt: float,
    related: List[str],
    ugl_pct: Optional[float],
    div_income_cad: float,
    div_contrib_pct: float,
    val_zone: Optional[str],
    fv_base: Optional[float],
    mos_actual: Optional[float],
    mos_required: Optional[float],
) -> List[str]:
    obs = []

    if is_existing:
        obs.append(
            f"{ticker} is an existing holding: {shares:,.0f} shares "
            f"at {price:.2f} {currency}/share, representing {weight_pct:.2f}% "
            f"of the portfolio."
        )
    else:
        obs.append(
            f"{ticker} is not currently held. "
            f"Current price: {price:.2f} {currency}/share."
        )

    # Unrealized P/L — context, no recommendation
    if ugl_pct is not None:
        direction = "gain" if ugl_pct >= 0 else "loss"
        obs.append(
            f"Unrealized {direction}: {ugl_pct:+.1f}% vs average cost. "
            f"This does not affect current investment attractiveness — "
            f"decisions are based on current business quality and valuation."
        )

    # Sector context
    if sector:
        obs.append(
            f"Sector: {sector} — currently {sector_wt:.1f}% of the portfolio."
        )

    # Geography context
    if geography:
        obs.append(
            f"Geography: {geography} — currently {geo_wt:.1f}% of the portfolio."
        )

    # Economic group
    if eco_group and eco_wt > 0:
        if related:
            obs.append(
                f"Economic group '{eco_group}' is {eco_wt:.1f}% of the portfolio. "
                f"Related holdings in same group: {', '.join(related)}."
            )
        else:
            obs.append(
                f"Economic group '{eco_group}' is {eco_wt:.1f}% of the portfolio."
            )

    # Dividend contribution
    if div_income_cad > 0:
        obs.append(
            f"Contributes {div_income_cad:.0f} CAD/year in dividend income "
            f"({div_contrib_pct:.1f}% of portfolio total income)."
        )

    # Valuation zone (reported as fact, no action implied)
    if val_zone:
        obs.append(
            f"Valuation zone: {val_zone}."
            + (
                f" Current price is {mos_actual:+.1f}% vs base fair value "
                f"(required MoS: {mos_required:.0f}%)."
                if mos_actual is not None and mos_required is not None
                else ""
            )
        )

    return obs


def _build_portfolio_risks(
    flags: List[ConcentrationFlag],
    related: List[str],
    eco_group: str,
) -> List[str]:
    risks = []
    for f in flags:
        from analytics.portfolio.portfolio_models import FlagSeverity
        if f.severity in (FlagSeverity.ELEVATED, FlagSeverity.HIGH):
            risks.append(f.description)
    if related and eco_group:
        risks.append(
            f"Multiple positions in '{eco_group}' group share correlated risk drivers. "
            f"Adverse events affecting the group impact all holdings simultaneously."
        )
    return risks
