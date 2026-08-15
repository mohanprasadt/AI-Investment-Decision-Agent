"""
Gate 4 — Portfolio Context
===========================
Contextualises the investment opportunity within the existing portfolio.

Privacy-first design — three context modes are supported:

  NONE        → No portfolio information provided.
                Treats the company as a new position.
                Returns MEDIUM confidence (portfolio data is not fundamental
                investment evidence; its absence does not reduce quality of the
                business/valuation assessment).

  WEIGHT_ONLY → User supplies only the portfolio weight percentage.
                The system uses the weight for position-size reasoning only.
                Does NOT infer shares, average cost, total value, sector
                weights, geographic weights, or other holdings.
                Returns MEDIUM confidence.

  FULL        → Complete PortfolioPositionContext provided.
                Full sizing, concentration, and incremental-scenario analysis.
                Returns HIGH/MEDIUM confidence based on data completeness.

Critical design rules (enforced in all modes):
  1. Average cost / cost basis is NEVER used in decision logic.
     Sunk-cost reasoning is architecturally blocked.

  2. Concentration flags are CONTEXT, not VETO.
     A great business at a great price should not be rejected because
     the sector is already represented. Context influences sizing,
     not the fundamental decision.

  3. Missing portfolio context must NOT reduce overall investment
     decision confidence. Portfolio context is not evidence about the
     quality of the company.

Portfolio influence matrix:
  is_existing + ACCUMULATE zone → ACCUMULATE preferred
  is_existing + WATCH zone      → HOLD preferred
  not_existing + ACCUMULATE     → START_SMALL preferred
  not_existing + WATCH          → WATCH
"""

import sys
from pathlib import Path
from typing import Optional, Union

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.decision.decision_models import GateResult, DecisionAction
from analytics.portfolio.portfolio_models import (
    PortfolioPositionContext, WeightOnlyPortfolioContext,
    FlagSeverity, PortfolioContextMode,
)

# Union type accepted by this gate
AnyPortfolioContext = Optional[Union[PortfolioPositionContext, WeightOnlyPortfolioContext]]


def evaluate_gate4(portfolio_ctx: AnyPortfolioContext) -> GateResult:
    """
    Gate 4: Portfolio context assessment.

    Always passes (returns passed=True).
    Sets contextual signals consumed by the synthesizer.
    Never reduces overall decision confidence for absent/partial portfolio data.
    """
    if portfolio_ctx is None:
        return _gate4_none()

    if isinstance(portfolio_ctx, WeightOnlyPortfolioContext):
        return _gate4_weight_only(portfolio_ctx)

    return _gate4_full(portfolio_ctx)


# ---------------------------------------------------------------------------
# Mode: NONE
# ---------------------------------------------------------------------------

def _gate4_none() -> GateResult:
    return GateResult(
        gate_number=4,
        gate_name="Portfolio Context",
        passed=True,
        confidence="MEDIUM",        # NOT LOW — absence of portfolio data is not
                                    # a signal about company quality
        summary=(
            "Portfolio context: NOT PROVIDED. "
            "Treating as new position per investor philosophy default. "
            "Decision confidence is not reduced — portfolio data is context, "
            "not fundamental investment evidence."
        ),
        supporting_evidence=[
            "No portfolio context provided — analysis proceeds as a new-position evaluation.",
        ],
        contradictory_evidence=[],
        data_gaps=[
            "Portfolio context not provided. "
            "Position sizing, concentration flags, and incremental scenarios are unavailable. "
            "These are sizing inputs, not investment-quality inputs.",
        ],
        philosophy_notes=[
            "No portfolio context provided. Applying philosophy default: "
            "new positions begin small (START_SMALL preferred for positive actions).",
        ],
    )


# ---------------------------------------------------------------------------
# Mode: WEIGHT_ONLY
# ---------------------------------------------------------------------------

def _gate4_weight_only(ctx: WeightOnlyPortfolioContext) -> GateResult:
    weight = ctx.portfolio_weight_pct
    supporting   = []
    contradictory = []
    philosophy   = []

    supporting.append(
        f"Existing position: approximately {weight:.1f}% of portfolio. "
        f"(Weight-only mode — shares and average cost not provided.)"
    )

    if weight >= 10.0:
        contradictory.append(
            f"Position weight {weight:.1f}% is significant — meaningful existing exposure. "
            "Consider this when sizing any additional purchases. "
            "[Context only — not an automatic veto.]"
        )
        philosophy.append(
            f"Existing weight of {weight:.1f}% is large. "
            "Philosophy: consider smaller incremental additions at high weights."
        )
    elif weight >= 5.0:
        supporting.append(
            f"Position weight {weight:.1f}% represents moderate existing exposure."
        )
        philosophy.append(
            f"Existing weight of {weight:.1f}% is moderate. "
            "ACCUMULATE is preferred over START_SMALL for existing positions "
            "when valuation zone supports additional ownership."
        )
    else:
        supporting.append(
            f"Position weight {weight:.1f}% is small — room to add "
            "if quality and valuation justify it."
        )
        philosophy.append(
            f"Small existing position ({weight:.1f}%). "
            "ACCUMULATE is preferred when valuation zone is favourable."
        )

    philosophy.append(
        "WEIGHT_ONLY mode: shares, average cost, total portfolio value, "
        "sector/geographic concentration, and other holdings were not provided "
        "and are NOT inferred. Concentration analysis requires full portfolio data."
    )
    philosophy.append(
        "Average cost is not provided and is not used in any decision logic. "
        "(Sunk-cost protection — applies in all modes.)"
    )

    return GateResult(
        gate_number=4,
        gate_name="Portfolio Context",
        passed=True,
        confidence="MEDIUM",
        summary=(
            f"Portfolio context: WEIGHT_ONLY. "
            f"Existing position at {weight:.1f}% of portfolio. "
            f"Shares, average cost, and concentration data not provided — not inferred."
        ),
        supporting_evidence=supporting,
        contradictory_evidence=contradictory,
        data_gaps=list(ctx.data_gaps),
        philosophy_notes=philosophy,
    )


# ---------------------------------------------------------------------------
# Mode: FULL
# ---------------------------------------------------------------------------

def _gate4_full(ctx: PortfolioPositionContext) -> GateResult:
    supporting    = []
    contradictory = []
    philosophy    = []
    data_gaps     = list(ctx.data_gaps or [])

    if ctx.is_existing_holding:
        supporting.append(
            f"Existing holding: {ctx.shares_held:,.0f} shares at "
            f"{ctx.current_price_local:.2f} {ctx.price_currency}/share, "
            f"representing {ctx.portfolio_weight_pct:.2f}% of portfolio."
        )
        philosophy.append(
            "Existing position: ACCUMULATE is preferred over START_SMALL "
            "when valuation zone supports additional ownership."
        )
    else:
        supporting.append(
            f"{ctx.ticker} is not currently held. "
            "Philosophy: begin new positions small — START_SMALL preferred."
        )
        philosophy.append(
            "New position: investor philosophy is to begin small "
            "and accumulate gradually — START_SMALL preferred."
        )

    # Cost-basis exclusion — always documented
    if ctx.is_existing_holding and ctx.average_cost_per_share:
        if ctx.unrealized_gain_loss_pct is not None:
            philosophy.append(
                f"Average cost ({ctx.average_cost_per_share:.2f} {ctx.price_currency}) "
                f"is documented but explicitly excluded from this decision. "
                f"Unrealized P/L ({ctx.unrealized_gain_loss_pct:+.1f}%) does not "
                f"influence the action. (Sunk-cost protection.)"
            )
        else:
            philosophy.append(
                f"Average cost ({ctx.average_cost_per_share:.2f} {ctx.price_currency}) "
                "is documented but explicitly excluded from this decision. "
                "(Sunk-cost protection.)"
            )

    # Concentration flags — context only, never a veto
    high_flags     = [f for f in ctx.concentration_flags if f.severity == FlagSeverity.HIGH]
    elevated_flags = [f for f in ctx.concentration_flags if f.severity == FlagSeverity.ELEVATED]

    if high_flags:
        for f in high_flags:
            contradictory.append(
                f"HIGH concentration: {f.description} "
                "[Context only — not an automatic veto. "
                "Consider smaller incremental scenario if action is positive.]"
            )
        philosophy.append(
            "HIGH concentration flags noted. Portfolio allocation is a guideline, "
            "not a hard rule. These flags inform position sizing, not the fundamental "
            "investment decision."
        )
    if elevated_flags:
        for f in elevated_flags:
            contradictory.append(f"ELEVATED concentration: {f.description}")

    if ctx.incremental_scenarios:
        smallest = ctx.incremental_scenarios[0]
        supporting.append(
            f"Smallest scenario: {smallest.investment_amount_cad:,.0f} CAD → "
            f"{smallest.shares_purchasable} shares, "
            f"new portfolio weight {smallest.new_portfolio_weight_pct:.2f}%."
        )

    if ctx.related_holdings:
        contradictory.append(
            f"Related holdings in same economic group '{ctx.economic_group}': "
            f"{', '.join(ctx.related_holdings)}. "
            "Correlated risk concentration noted."
        )

    if ctx.annual_dividend_income_cad and ctx.annual_dividend_income_cad > 0:
        supporting.append(
            f"Position contributes {ctx.annual_dividend_income_cad:.0f} CAD/year in dividend income "
            f"({ctx.dividend_contribution_to_portfolio_income_pct:.1f}% of portfolio income)."
        )

    if ctx.sector and ctx.sector_weight_in_portfolio_pct:
        supporting.append(
            f"Sector '{ctx.sector}' is {ctx.sector_weight_in_portfolio_pct:.1f}% of portfolio."
        )
    if ctx.geography and ctx.geography_weight_in_portfolio_pct:
        supporting.append(
            f"Geography '{ctx.geography}' is {ctx.geography_weight_in_portfolio_pct:.1f}% of portfolio."
        )

    gate_confidence = (ctx.context_confidence or "MEDIUM").upper()

    return GateResult(
        gate_number=4,
        gate_name="Portfolio Context",
        passed=True,
        confidence=gate_confidence,
        summary=_full_summary(ctx, high_flags, elevated_flags),
        supporting_evidence=supporting,
        contradictory_evidence=contradictory,
        data_gaps=data_gaps,
        philosophy_notes=philosophy,
    )


# ---------------------------------------------------------------------------
# Helpers — also used by synthesizer
# ---------------------------------------------------------------------------

def is_existing_holding(portfolio_ctx: AnyPortfolioContext) -> bool:
    if portfolio_ctx is None:
        return False
    return portfolio_ctx.is_existing_holding


def has_high_concentration(portfolio_ctx: AnyPortfolioContext) -> bool:
    if portfolio_ctx is None:
        return False
    if isinstance(portfolio_ctx, WeightOnlyPortfolioContext):
        return portfolio_ctx.portfolio_weight_pct >= 10.0
    return any(f.severity == FlagSeverity.HIGH for f in portfolio_ctx.concentration_flags)


def _full_summary(ctx: PortfolioPositionContext, high_flags, elevated_flags) -> str:
    holding_str = "Existing holding" if ctx.is_existing_holding else "New position"
    conc_str = ""
    if high_flags:
        conc_str = f", {len(high_flags)} HIGH concentration flag(s)"
    elif elevated_flags:
        conc_str = f", {len(elevated_flags)} ELEVATED concentration flag(s)"
    return (
        f"{holding_str}: {ctx.portfolio_weight_pct:.2f}% of portfolio"
        f"{conc_str}. "
        f"Context confidence: {ctx.context_confidence or 'MEDIUM'}. "
        f"Average cost excluded from decision logic (sunk-cost protection)."
    )
