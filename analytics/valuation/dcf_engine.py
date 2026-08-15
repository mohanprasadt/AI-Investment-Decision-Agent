"""
DCF Engine — Phase 5
====================
Runs bear / base / bull DCF scenarios and a 2-D sensitivity table
(discount rate × terminal growth rate).

Wraps calculations.simple_dcf — the underlying math is unchanged from Phase 1.
This module adds: scenario construction, sensitivity, terminal-value diagnostics,
company-type guards, data-provenance passthrough, and confidence assessment.

Design rules:
- Negative or zero FCF → not applicable; return None with clear reason
- Financial institutions → not applicable; add explicit note
- Terminal value > 75% of total → raise warning
- Never produce a single point estimate as the output
- All assumptions are surfaced in DCFResult.key_assumptions
"""

import sys
from pathlib import Path
from typing import List, Optional, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.financial_quality.calculations import simple_dcf, dcf_sensitivity
from analytics.valuation.valuation_models import (
    ValuationInput, DCFResult, CompanyType,
    MethodApplicability, MethodReliability, ValuationConfidence,
    InputType,
)


# ---------------------------------------------------------------------------
# Default growth rate helpers
# ---------------------------------------------------------------------------

_MOAT_TO_DISCOUNT = {
    "EXCEPTIONAL": 7.5,
    "STRONG":      8.5,
    "MODERATE":    9.5,
    "WEAK":       11.0,
    "NONE":       12.5,
}

_QUALITY_DISCOUNT_ADJUSTMENT = {
    "EXCELLENT": -0.5,
    "STRONG":     0.0,
    "GOOD":       0.0,
    "WATCH":     +0.5,
    "CONCERN":   +1.5,
}


def _base_discount_rate(moat_strength: str, financial_quality: str) -> float:
    """Derive the base discount rate from moat and financial quality."""
    base = _MOAT_TO_DISCOUNT.get(moat_strength.upper(), 9.5)
    adj  = _QUALITY_DISCOUNT_ADJUSTMENT.get(financial_quality.upper(), 0.0)
    return round(base + adj, 2)


def _build_growth_schedule(
    base_rate: float,
    years: int = 10,
    decay_to: float = 3.0,
) -> List[float]:
    """
    Build a year-by-year growth schedule that linearly decays from base_rate
    to decay_to over the projection period.
    Used when explicit growth_rates are not provided.
    """
    if years <= 1:
        return [base_rate]
    schedule = []
    for i in range(years):
        # Linear interpolation
        t = i / (years - 1)
        rate = base_rate + t * (decay_to - base_rate)
        schedule.append(round(rate, 2))
    return schedule


def _terminal_value_pct(
    base_fcf: float,
    growth_rates: List[float],
    terminal_growth_rate: float,
    discount_rate: float,
) -> Optional[float]:
    """
    Calculate what % of total DCF value comes from the terminal value.
    A high % (>75%) signals fragility — small changes in terminal assumptions
    have outsized impact on the result.
    """
    r = discount_rate / 100
    g_t = terminal_growth_rate / 100

    # PV of explicit forecast period
    fcf = base_fcf
    pv_fcfs = 0.0
    for i, g_pct in enumerate(growth_rates):
        fcf = fcf * (1 + g_pct / 100)
        pv_fcfs += fcf / ((1 + r) ** (i + 1))

    # Terminal value
    terminal_fcf = fcf * (1 + g_t)
    if (r - g_t) <= 0:
        return None
    terminal_value = terminal_fcf / (r - g_t)
    n = len(growth_rates)
    pv_terminal = terminal_value / ((1 + r) ** n)

    total = pv_fcfs + pv_terminal
    if total <= 0:
        return None
    return (pv_terminal / total) * 100


# ---------------------------------------------------------------------------
# Applicability check
# ---------------------------------------------------------------------------

def dcf_applicability(inputs: ValuationInput) -> tuple[MethodApplicability, str]:
    """
    Determine whether DCF is applicable for this company.
    Returns (applicability_status, reason_string).
    """
    if inputs.company_type == CompanyType.FINANCIAL:
        return (
            MethodApplicability.NOT_APPLICABLE,
            "Financial institutions: DCF on levered FCF is not appropriate. "
            "Use P/BV, ROE-based, or normalized earnings instead."
        )

    if inputs.company_type == CompanyType.REIT:
        return (
            MethodApplicability.APPLICABLE_WITH_CAVEATS,
            "REIT: Standard FCF-based DCF is less reliable. "
            "FFO/AFFO multiple is preferred; DCF run with caveats."
        )

    if not inputs.has_positive_fcf():
        if inputs.company_type == CompanyType.HIGH_GROWTH:
            return (
                MethodApplicability.APPLICABLE_WITH_CAVEATS,
                "Negative FCF: DCF run on revenue-to-FCF projection basis. "
                "High sensitivity — results should be treated as illustrative only."
            )
        return (
            MethodApplicability.NOT_APPLICABLE,
            "Negative or zero FCF: Conventional DCF is not reliable. "
            "Revenue multiple or sum-of-parts may be more appropriate."
        )

    base_fcf_item = inputs.dcf_base_fcf or inputs.fcf_normalized or inputs.fcf_ttm
    if base_fcf_item is None or base_fcf_item.value is None:
        return (
            MethodApplicability.INSUFFICIENT_DATA,
            "No FCF data available for DCF."
        )
    if inputs.shares_outstanding is None or inputs.shares_outstanding.value is None:
        return (
            MethodApplicability.INSUFFICIENT_DATA,
            "No shares outstanding data available."
        )

    return (MethodApplicability.APPLICABLE, "Standard FCF-based DCF applicable.")


# ---------------------------------------------------------------------------
# Main DCF runner
# ---------------------------------------------------------------------------

def run_dcf(inputs: ValuationInput, projection_years: int = 10) -> DCFResult:
    """
    Run the bear/base/bull DCF and generate a sensitivity table.

    Growth schedule strategy (in order of preference):
    1. Use inputs.dcf_growth_rates if explicitly provided
    2. Build from inputs.dcf_revenue_growth_rate (scalar → decay schedule)
    3. Derive from historical FCF CAGR (approximate)
    4. Use conservative defaults

    Returns a DCFResult with None values if DCF is not applicable.
    """
    result = DCFResult()
    applicability, reason = dcf_applicability(inputs)

    if applicability == MethodApplicability.NOT_APPLICABLE:
        result.reliability = MethodReliability.NA
        result.reliability_note = reason
        result.caveats.append(reason)
        return result

    if applicability == MethodApplicability.INSUFFICIENT_DATA:
        result.reliability = MethodReliability.NA
        result.reliability_note = reason
        result.caveats.append(reason)
        return result

    # Resolve base FCF
    base_fcf_item = inputs.dcf_base_fcf or inputs.fcf_normalized or inputs.fcf_ttm
    base_fcf = base_fcf_item.value
    shares = inputs.shares_outstanding.value

    # Derive discount rates
    base_dr = _base_discount_rate(inputs.moat_strength, inputs.financial_quality_hint)
    bear_dr = round(base_dr + 1.5, 2)
    bull_dr = round(max(base_dr - 1.5, 6.0), 2)

    result.base_discount_rate = base_dr
    result.bear_discount_rate = bear_dr
    result.bull_discount_rate = bull_dr
    result.terminal_growth_rate = 3.0

    # Derive growth schedules
    if inputs.dcf_growth_rates and len(inputs.dcf_growth_rates) >= 5:
        base_rates = inputs.dcf_growth_rates[:projection_years]
        # Extend or truncate to projection_years
        while len(base_rates) < projection_years:
            base_rates.append(3.0)
    elif inputs.dcf_revenue_growth_rate is not None:
        base_rate = inputs.dcf_revenue_growth_rate
        base_rates = _build_growth_schedule(base_rate, projection_years, decay_to=3.0)
    else:
        # Derive from FCF history if available
        if len(inputs.fcf_history) >= 3:
            vals = sorted(inputs.fcf_history.items())
            oldest = list(vals)[0][1]
            newest = list(vals)[-1][1]
            n_years = len(vals) - 1
            if oldest > 0 and newest > 0 and n_years > 0:
                hist_cagr = ((newest / oldest) ** (1 / n_years) - 1) * 100
                base_rate = max(min(hist_cagr, 20.0), 0.0)  # cap 0–20%
            else:
                base_rate = 5.0
        else:
            base_rate = 5.0
        base_rates = _build_growth_schedule(base_rate, projection_years, decay_to=3.0)

    # Bear / bull growth rate adjustments
    bear_rates = [max(r - 3.0, 0.0) for r in base_rates]
    bull_rates = [min(r + 4.0, 25.0) for r in base_rates]

    result.base_growth_rates = base_rates
    result.bear_growth_rates = bear_rates
    result.bull_growth_rates = bull_rates

    # Run the three scenarios
    result.base_value = simple_dcf(base_fcf, base_rates, 3.0, base_dr, shares)
    result.bear_value = simple_dcf(base_fcf, bear_rates, 3.0, bear_dr, shares)
    result.bull_value = simple_dcf(base_fcf, bull_rates, 3.0, bull_dr, shares)

    # Terminal value % for base scenario
    if result.base_value:
        tv_pct = _terminal_value_pct(base_fcf, base_rates, 3.0, base_dr)
        result.terminal_value_pct_of_base = tv_pct
        if tv_pct is not None and tv_pct > 75:
            result.terminal_value_warning = True
            result.caveats.append(
                f"Terminal value represents {tv_pct:.0f}% of total DCF value — "
                "results are highly sensitive to terminal growth rate assumptions."
            )

    # 2-D sensitivity table: discount rate × terminal growth
    discount_rates_range = [
        round(base_dr - 2.0, 1),
        round(base_dr - 1.0, 1),
        round(base_dr, 1),
        round(base_dr + 1.0, 1),
        round(base_dr + 2.0, 1),
    ]
    terminal_growths_range = [2.0, 2.5, 3.0, 3.5, 4.0]

    sensitivity: Dict[str, Dict[str, Optional[float]]] = {}
    for dr in discount_rates_range:
        dr_key = f"{dr:.1f}%"
        sensitivity[dr_key] = {}
        for tg in terminal_growths_range:
            tg_key = f"{tg:.1f}%"
            val = simple_dcf(base_fcf, base_rates, tg, dr, shares)
            sensitivity[dr_key][tg_key] = round(val, 2) if val else None
    result.sensitivity_table = sensitivity

    # Reliability assessment
    data_source = base_fcf_item.input_type if base_fcf_item else InputType.ASSUMED
    if data_source == InputType.REPORTED and len(inputs.fcf_history) >= 5:
        reliability = MethodReliability.HIGH
        reliability_note = "Strong FCF history with reported data — DCF well-supported"
    elif data_source == InputType.REPORTED:
        reliability = MethodReliability.MEDIUM
        reliability_note = "Reported FCF data but limited history — moderate DCF reliability"
    else:
        reliability = MethodReliability.LOW
        reliability_note = "FCF assumed or calculated — treat DCF as illustrative only"

    if applicability == MethodApplicability.APPLICABLE_WITH_CAVEATS:
        # Downgrade reliability one notch
        if reliability == MethodReliability.HIGH:
            reliability = MethodReliability.MEDIUM
        elif reliability == MethodReliability.MEDIUM:
            reliability = MethodReliability.LOW
        reliability_note += f" | {reason}"
        result.caveats.append(reason)

    if result.terminal_value_warning:
        if reliability == MethodReliability.HIGH:
            reliability = MethodReliability.MEDIUM

    result.reliability = reliability
    result.reliability_note = reliability_note

    # Document assumptions
    result.key_assumptions = [
        f"Base FCF: {base_fcf:.1f}M {inputs.currency} "
        f"({base_fcf_item.source if base_fcf_item else 'N/A'}, "
        f"{base_fcf_item.period if base_fcf_item else 'N/A'})",
        f"Shares outstanding: {shares:.1f}M",
        f"Base case: growth {base_rates[0]:.1f}%→{base_rates[-1]:.1f}% | "
        f"discount {base_dr:.1f}% | terminal growth 3.0%",
        f"Bear case: growth {bear_rates[0]:.1f}%→{bear_rates[-1]:.1f}% | "
        f"discount {bear_dr:.1f}%",
        f"Bull case: growth {bull_rates[0]:.1f}%→{bull_rates[-1]:.1f}% | "
        f"discount {bull_dr:.1f}%",
        f"Moat strength: {inputs.moat_strength} → base discount rate {base_dr:.1f}%",
    ]

    return result


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from analytics.valuation.valuation_models import (
        ValuationInput, CompanyType, InputItem, ValuationConfidence, InputType
    )

    print("Testing dcf_engine.py...")

    def _item(name, value, source="Annual Report FY2024", period="FY2024",
              currency="CAD", itype=InputType.REPORTED):
        return InputItem(name=name, value=value, source=source, period=period,
                         currency=currency, input_type=itype)

    # Test 1: Normal industrial company with positive FCF
    inputs = ValuationInput(
        ticker="CNR.TO",
        company_name="Canadian National Railway",
        company_type=CompanyType.INDUSTRIAL,
        valuation_date="2024-12-31",
        currency="CAD",
        fcf_ttm=_item("FCF TTM", 3_800.0, period="FY2024"),
        fcf_normalized=_item("FCF Normalized", 3_500.0, period="3yr avg"),
        shares_outstanding=_item("Shares", 670.0),
        moat_strength="STRONG",
        financial_quality_hint="EXCELLENT",
        dcf_revenue_growth_rate=7.0,
        fcf_history={"2019": 2800.0, "2020": 2600.0, "2021": 3100.0,
                     "2022": 3400.0, "2023": 3700.0, "2024": 3800.0},
    )

    result = run_dcf(inputs)
    print(f"  Base value: {result.base_value:.2f} CAD/share")
    print(f"  Bear value: {result.bear_value:.2f}")
    print(f"  Bull value: {result.bull_value:.2f}")
    print(f"  TV %: {result.terminal_value_pct_of_base:.1f}%")
    print(f"  TV warning: {result.terminal_value_warning}")
    print(f"  Reliability: {result.reliability.value}")
    print(f"  Sensitivity rows: {len(result.sensitivity_table)}")
    assert result.is_valid()
    assert result.bear_value < result.base_value < result.bull_value

    # Test 2: Negative FCF
    neg_fcf_inputs = ValuationInput(
        ticker="LOSS.TO",
        company_name="Money Losing Corp",
        company_type=CompanyType.NEGATIVE_FCF,
        valuation_date="2024-12-31",
        currency="CAD",
        fcf_ttm=_item("FCF", -150.0),
        shares_outstanding=_item("Shares", 100.0),
        moat_strength="WEAK",
        financial_quality_hint="CONCERN",
    )
    neg_result = run_dcf(neg_fcf_inputs)
    assert not neg_result.is_valid()
    assert neg_result.reliability == MethodReliability.NA
    print(f"  Negative FCF correctly blocked: {neg_result.reliability_note[:60]}...")

    # Test 3: Financial institution
    bank_inputs = ValuationInput(
        ticker="TD.TO",
        company_name="TD Bank",
        company_type=CompanyType.FINANCIAL,
        valuation_date="2024-12-31",
        currency="CAD",
        shares_outstanding=_item("Shares", 1_800.0),
        moat_strength="MODERATE",
        financial_quality_hint="STRONG",
    )
    bank_result = run_dcf(bank_inputs)
    assert not bank_result.is_valid()
    assert bank_result.reliability == MethodReliability.NA
    print(f"  Financial institution DCF blocked: {bank_result.reliability_note[:60]}...")

    print("\ndcf_engine.py: OK")
