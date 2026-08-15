"""
Margin of Safety & Accumulation Zones — Phase 5
================================================
Calculates:
  1. Required margin of safety — varies by moat strength, financial quality,
     and valuation confidence (NOT a universal fixed %)
  2. Accumulation zone at the current price
  3. Zone threshold prices (where the investor transitions between zones)

Design rules:
  - Higher quality + higher confidence → lower required MoS
  - Higher uncertainty → larger required MoS
  - Accumulation zones are derived from fair value, not from arbitrary price levels
  - This module does NOT produce investment recommendations
  - Phase 7 (Decision Engine) will integrate zone signal with business quality
    and portfolio context before any action is considered
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.valuation.valuation_models import (
    FairValueRange, AccumulationZone, AccumulationZoneLabel, ValuationConfidence,
)


# ---------------------------------------------------------------------------
# Required margin of safety matrix
# ---------------------------------------------------------------------------

# Base required MoS by moat strength (%)
_MOAT_BASE_MOS = {
    "EXCEPTIONAL": 10.0,
    "STRONG":      15.0,
    "MODERATE":    20.0,
    "WEAK":        28.0,
    "NONE":        35.0,
}

# Adjustment by financial quality
_QUALITY_MOS_ADJ = {
    "EXCELLENT": -3.0,
    "STRONG":     0.0,
    "GOOD":       0.0,
    "WATCH":     +5.0,
    "CONCERN":  +10.0,
}

# Adjustment by valuation confidence
_CONFIDENCE_MOS_ADJ = {
    ValuationConfidence.HIGH:   0.0,
    ValuationConfidence.MEDIUM: +5.0,
    ValuationConfidence.LOW:   +10.0,
}

# Hard limits
_MIN_MOS = 8.0    # Never require less than 8% even for exceptional companies
_MAX_MOS = 45.0   # Never require more than 45%


def required_margin_of_safety(
    moat_strength: str,
    financial_quality: str,
    valuation_confidence: ValuationConfidence,
) -> float:
    """
    Calculate the required margin of safety for this investor profile.

    The required MoS is NOT a universal number — it is context-dependent:
      - Exceptional moat + high confidence → lower MoS needed
      - Weak moat + low confidence → higher MoS needed

    Returns a percentage (e.g. 20.0 means price must be 20% below fair value).
    """
    base = _MOAT_BASE_MOS.get(moat_strength.upper(), 20.0)
    quality_adj = _QUALITY_MOS_ADJ.get(financial_quality.upper(), 0.0)
    confidence_adj = _CONFIDENCE_MOS_ADJ.get(valuation_confidence, 5.0)
    mos = base + quality_adj + confidence_adj
    return round(max(_MIN_MOS, min(_MAX_MOS, mos)), 1)


# ---------------------------------------------------------------------------
# Accumulation zone thresholds
# ---------------------------------------------------------------------------

def accumulation_zone_thresholds(
    fair_value_base: float,
    required_mos_pct: float,
) -> dict:
    """
    Derive the price thresholds for each accumulation zone.

    Zone logic:
      ACCUMULATE  : price <= fair_value * (1 - required_mos%)
      START_SMALL : price <= fair_value * (1 - required_mos% * 0.5)
      WATCH       : price <= fair_value
      WAIT        : price > fair_value

    Returns dict of {zone_label: price_threshold}.
    """
    mos = required_mos_pct / 100
    return {
        "accumulate_below":  round(fair_value_base * (1 - mos), 2),
        "start_small_below": round(fair_value_base * (1 - mos * 0.5), 2),
        "watch_below":       round(fair_value_base, 2),
    }


def current_accumulation_zone(
    current_price: float,
    fair_value_range: FairValueRange,
    moat_strength: str,
    financial_quality: str,
) -> AccumulationZone:
    """
    Determine the accumulation zone at the current price.

    Uses the base case fair value as the primary reference point.
    Bear/bull range informs the confidence of the zone assignment.
    """
    fv_base = fair_value_range.base
    fv_confidence = fair_value_range.confidence

    if fv_base is None or fv_base <= 0:
        return AccumulationZone(
            zone=AccumulationZoneLabel.WAIT,
            current_price=current_price,
            current_price_currency=fair_value_range.currency,
            fair_value_base=None,
            required_margin_of_safety_pct=0.0,
            actual_margin_of_safety_pct=None,
            zone_reasoning="Fair value could not be estimated — defaulting to WAIT.",
            caveat="Resolve data gaps before considering any investment action.",
        )

    req_mos = required_margin_of_safety(moat_strength, financial_quality, fv_confidence)
    thresholds = accumulation_zone_thresholds(fv_base, req_mos)

    # Margin of safety at current price vs base fair value (positive = below FV)
    actual_mos = ((fv_base - current_price) / fv_base) * 100

    # Determine zone
    if current_price <= thresholds["accumulate_below"]:
        zone = AccumulationZoneLabel.ACCUMULATE
        reasoning = (
            f"Price ({current_price:.2f}) is {actual_mos:.1f}% below base fair value "
            f"({fv_base:.2f}), exceeding the required {req_mos:.0f}% margin of safety."
        )
    elif current_price <= thresholds["start_small_below"]:
        zone = AccumulationZoneLabel.START_SMALL
        half_req = req_mos * 0.5
        reasoning = (
            f"Price ({current_price:.2f}) is {actual_mos:.1f}% below base fair value "
            f"({fv_base:.2f}). Provides half the required MoS ({half_req:.0f}% of "
            f"required {req_mos:.0f}%) — attractive enough to initiate a small position."
        )
    elif current_price <= thresholds["watch_below"]:
        zone = AccumulationZoneLabel.WATCH
        reasoning = (
            f"Price ({current_price:.2f}) is below fair value ({fv_base:.2f}) but "
            f"does not yet meet the required {req_mos:.0f}% margin of safety."
        )
    else:
        zone = AccumulationZoneLabel.WAIT
        premium = ((current_price / fv_base) - 1) * 100
        reasoning = (
            f"Price ({current_price:.2f}) is {premium:.1f}% above base fair value "
            f"({fv_base:.2f}). Business may be excellent but valuation is not compelling."
        )

    # Caveat for wide ranges
    caveat = ""
    if fair_value_range.width_pct() is not None and fair_value_range.width_pct() > 50:
        caveat = (
            f"Wide fair-value range (bear: {fair_value_range.bear:.2f}, "
            f"bull: {fair_value_range.bull:.2f}) indicates high valuation uncertainty. "
            "Zone assignment should be treated with lower confidence."
        )
    if fv_confidence == ValuationConfidence.LOW:
        caveat += (" Low valuation confidence — do not act on zone signal alone." if not caveat
                   else " | Low valuation confidence.")

    return AccumulationZone(
        zone=zone,
        current_price=current_price,
        current_price_currency=fair_value_range.currency,
        fair_value_base=fv_base,
        required_margin_of_safety_pct=req_mos,
        actual_margin_of_safety_pct=round(actual_mos, 1),
        accumulate_below=thresholds["accumulate_below"],
        start_small_below=thresholds["start_small_below"],
        watch_below=thresholds["watch_below"],
        zone_reasoning=reasoning,
        caveat=caveat,
    )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Testing margin_of_safety.py...")

    # Test 1: Strong moat + excellent quality + high confidence → low MoS
    mos1 = required_margin_of_safety("STRONG", "EXCELLENT", ValuationConfidence.HIGH)
    print(f"  STRONG moat + EXCELLENT quality + HIGH conf → required MoS: {mos1}%")
    assert mos1 <= 15.0, f"Expected ≤15%, got {mos1}%"

    # Test 2: No moat + concern quality + low confidence → high MoS
    mos2 = required_margin_of_safety("NONE", "CONCERN", ValuationConfidence.LOW)
    print(f"  NONE moat + CONCERN quality + LOW conf → required MoS: {mos2}%")
    assert mos2 >= 40.0, f"Expected ≥40%, got {mos2}%"

    # Test 3: Accumulation zone at current price
    fv_range = FairValueRange(
        bear=140.0, base=175.0, bull=210.0,
        currency="CAD", confidence=ValuationConfidence.MEDIUM
    )

    # Price well below base — should be ACCUMULATE
    zone1 = current_accumulation_zone(135.0, fv_range, "STRONG", "GOOD")
    print(f"  Price 135 vs FV 175 → zone: {zone1.zone.value} (MoS: {zone1.actual_margin_of_safety_pct:.1f}%)")
    assert zone1.zone == AccumulationZoneLabel.ACCUMULATE

    # Price near fair value — should be WATCH
    zone2 = current_accumulation_zone(168.0, fv_range, "STRONG", "GOOD")
    print(f"  Price 168 vs FV 175 → zone: {zone2.zone.value} (MoS: {zone2.actual_margin_of_safety_pct:.1f}%)")
    assert zone2.zone == AccumulationZoneLabel.WATCH

    # Price above fair value — should be WAIT
    zone3 = current_accumulation_zone(190.0, fv_range, "STRONG", "GOOD")
    print(f"  Price 190 vs FV 175 → zone: {zone3.zone.value} (MoS: {zone3.actual_margin_of_safety_pct:.1f}%)")
    assert zone3.zone == AccumulationZoneLabel.WAIT

    # Price slightly below — should be START_SMALL
    req = required_margin_of_safety("STRONG", "GOOD", ValuationConfidence.MEDIUM)
    threshold = fv_range.base * (1 - req / 100)
    start_small_price = threshold + (fv_range.base * (1 - req / 200) - threshold) / 2
    zone4 = current_accumulation_zone(start_small_price, fv_range, "STRONG", "GOOD")
    print(f"  Price {start_small_price:.1f} → zone: {zone4.zone.value}")
    assert zone4.zone == AccumulationZoneLabel.START_SMALL

    print("\nmargin_of_safety.py: OK")
