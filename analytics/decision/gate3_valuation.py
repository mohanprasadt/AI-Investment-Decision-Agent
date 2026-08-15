"""
Gate 3 — Valuation
===================
Assesses whether the current market price is attractive relative to
estimated intrinsic value.

A high-quality company at an unattractive valuation does NOT automatically
receive a positive action. Valuation is the timing filter — it determines
WHEN to act, not WHETHER the business is investment-worthy.

Valuation zone mapping:
  ACCUMULATE   → most attractive (> required MoS)
  START_SMALL  → attractive (partial MoS)
  WATCH        → approaching fair value but not compelling
  WAIT         → at or above fair value — monitor for entry

If ValuationAssessment is None, the gate still passes but confidence
is downgraded and the synthesizer will default to WATCH for new positions.
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.decision.decision_models import GateResult
from analytics.valuation.valuation_models import (
    ValuationAssessment, AccumulationZoneLabel, ValuationConfidence,
)


def evaluate_gate3(
    valuation: Optional[ValuationAssessment],
) -> GateResult:
    """
    Gate 3: Valuation attractiveness assessment.

    Always passes (returns passed=True).
    Sets zone_label and confidence used by the synthesizer.
    """
    if valuation is None:
        return GateResult(
            gate_number=3,
            gate_name="Valuation",
            passed=True,
            confidence="LOW",
            summary=(
                "No ValuationAssessment provided. Valuation attractiveness cannot be assessed. "
                "The synthesizer will default to WATCH for this dimension."
            ),
            data_gaps=[
                "ValuationAssessment missing — no fair value range, no accumulation zone, "
                "no margin of safety information."
            ],
        )

    supporting   = []
    contradictory = []
    philosophy   = []
    data_gaps    = []

    # -----------------------------------------------------------------------
    # Accumulation zone
    # -----------------------------------------------------------------------
    az = valuation.accumulation_zone
    zone_label = az.zone.value if az else "WATCH"

    if az:
        mos = az.actual_margin_of_safety_pct
        required = az.required_margin_of_safety_pct
        price = az.current_price
        fv = az.fair_value_base

        if az.zone in (AccumulationZoneLabel.ACCUMULATE,):
            supporting.append(
                f"Accumulation zone: ACCUMULATE — price {price:.2f} is below "
                f"accumulation threshold. MoS: {mos:.1f}% vs required {required:.0f}%."
                if mos is not None else
                f"Accumulation zone: ACCUMULATE — price below accumulation threshold."
            )
        elif az.zone == AccumulationZoneLabel.START_SMALL:
            supporting.append(
                f"Accumulation zone: START_SMALL — price is in the attractive-entry range. "
                f"MoS: {mos:.1f}% vs required {required:.0f}%."
                if mos is not None else
                "Accumulation zone: START_SMALL."
            )
        elif az.zone == AccumulationZoneLabel.WATCH:
            supporting.append(
                f"Accumulation zone: WATCH — price is approaching fair value. "
                f"{'MoS: ' + f'{mos:.1f}%' if mos is not None else 'No MoS data.'}"
            )
        else:   # WAIT
            contradictory.append(
                f"Accumulation zone: WAIT — price at or above fair value. "
                f"{'MoS: ' + f'{mos:.1f}%' if mos is not None else ''} "
                f"Fair value base: {fv:.2f}." if fv else "WAIT zone."
            )

        if az.zone_reasoning:
            supporting.append(f"Zone reasoning: {az.zone_reasoning}")
        if az.caveat:
            data_gaps.append(f"Valuation caveat: {az.caveat}")

    # -----------------------------------------------------------------------
    # Fair value range and method agreement
    # -----------------------------------------------------------------------
    fvr = valuation.fair_value_range
    if fvr:
        width = fvr.width_pct()
        if fvr.base and fvr.bear and fvr.bull:
            note = (
                f"Fair value range: {fvr.bear:.2f}–{fvr.bull:.2f} {fvr.currency} "
                f"(base: {fvr.base:.2f}). Primary method: {fvr.primary_method}."
            )
            supporting.append(note)
            if fvr.convergence_note:
                if any(w in fvr.convergence_note.lower() for w in ["agree", "converge", "consistent"]):
                    supporting.append(f"Method convergence: {fvr.convergence_note}")
                else:
                    data_gaps.append(f"Method divergence: {fvr.convergence_note}")
            if width and width > 60:
                data_gaps.append(
                    f"High valuation uncertainty: range width is {width:.0f}% of base value. "
                    "Wide range suggests sensitive assumptions; treat fair value estimate with caution."
                )

    # -----------------------------------------------------------------------
    # Valuation confidence
    # -----------------------------------------------------------------------
    vc = valuation.overall_confidence
    if vc == ValuationConfidence.LOW:
        data_gaps.append(
            "Valuation confidence is LOW — limited applicable methods or high assumption sensitivity. "
            "Treat valuation zone as directional, not precise."
        )
    elif vc == ValuationConfidence.HIGH:
        supporting.append("Valuation confidence: HIGH — multiple methods in agreement.")

    # -----------------------------------------------------------------------
    # Applicable methods
    # -----------------------------------------------------------------------
    applicable = valuation.applicable_methods()
    if len(applicable) == 0:
        data_gaps.append("No valuation methods were applicable — cannot estimate intrinsic value.")
    elif len(applicable) == 1:
        data_gaps.append(
            f"Only one valuation method applicable ({applicable[0]}). "
            "Single-method valuation is less reliable; use wider margin of safety."
        )

    # Valuation flags and caveats
    for flag in (valuation.valuation_flags or []):
        data_gaps.append(f"Valuation flag: {flag}")
    for cav in (valuation.valuation_caveats or [])[:3]:
        data_gaps.append(f"Caveat: {cav}")

    # Key assumptions
    key_assumptions = valuation.key_valuation_assumptions or []

    # -----------------------------------------------------------------------
    # Confidence
    # -----------------------------------------------------------------------
    gate_confidence = _gate3_confidence(valuation, zone_label, data_gaps)

    return GateResult(
        gate_number=3,
        gate_name="Valuation",
        passed=True,
        confidence=gate_confidence,
        summary=_valuation_summary(zone_label, vc, applicable, fvr, data_gaps),
        supporting_evidence=supporting,
        contradictory_evidence=contradictory,
        data_gaps=data_gaps,
        philosophy_notes=philosophy,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gate3_confidence(valuation: ValuationAssessment, zone_label: str, gaps: list) -> str:
    vc = valuation.overall_confidence
    n_applicable = len(valuation.applicable_methods())
    n_gaps = len(gaps)

    if vc == ValuationConfidence.HIGH and n_applicable >= 2 and n_gaps <= 2:
        return "HIGH"
    if vc == ValuationConfidence.LOW or n_applicable == 0:
        return "LOW"
    if n_gaps <= 4:
        return "MEDIUM"
    return "LOW"


def _valuation_summary(zone_label, vc, applicable, fvr, gaps) -> str:
    vc_val = vc.value if hasattr(vc, "value") else str(vc)
    fv_str = ""
    if fvr and fvr.base:
        fv_str = f", fair value base: {fvr.base:.2f} {fvr.currency}"
    return (
        f"Zone: {zone_label}. "
        f"Valuation confidence: {vc_val}. "
        f"Methods applicable: {len(applicable)}{fv_str}. "
        f"{len(gaps)} data gaps/caveats."
    )
