"""
Valuation Synthesizer — Phase 5
================================
Orchestrates the full valuation workflow:
  1. Select applicable methods via method_selector
  2. Run each applicable method
  3. Synthesize method outputs into a FairValueRange (bear / base / bull)
  4. Calculate margin of safety and accumulation zone
  5. Assess overall confidence
  6. Package into ValuationAssessment

Architecture boundary:
  This module is the top-level entry point for Phase 5.
  It does NOT produce investment recommendations.
  The ValuationAssessment it produces feeds Phase 7 (Decision Engine).

Currency handling:
  All values are in the company's local reporting currency.
  FX conversion to CAD is stored but NOT applied to the primary output —
  the local currency valuation is always preserved.
"""

import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.valuation.valuation_models import (
    ValuationInput, ValuationAssessment, FairValueRange,
    ValuationConfidence, MethodApplicability, MethodReliability,
    MultipleValuationResult, HistoricalMultiplesResult,
    CompanyType,
)
from analytics.valuation.method_selector import select_methods
from analytics.valuation.dcf_engine import run_dcf, dcf_applicability
from analytics.valuation.multiples_engine import (
    run_normalized_pe, run_ev_ebitda, run_price_to_fcf,
    run_historical_pe, run_historical_ev_ebitda,
    run_peer_valuation, run_specialist_multiple,
)
from analytics.valuation.margin_of_safety import (
    required_margin_of_safety, current_accumulation_zone,
)


# ---------------------------------------------------------------------------
# Fair value synthesis helpers
# ---------------------------------------------------------------------------

_RELIABILITY_WEIGHT = {
    MethodReliability.HIGH:   1.0,
    MethodReliability.MEDIUM: 0.6,
    MethodReliability.LOW:    0.3,
    MethodReliability.NA:     0.0,
}


def _weighted_value(results: list, bear_attr: str, base_attr: str, bull_attr: str):
    """
    Compute weighted bear/base/bull from a list of (result, weight) tuples.
    Each element: (MultipleValuationResult or DCFResult, weight).
    Attributes named by bear_attr/base_attr/bull_attr.
    """
    bears, bases, bulls = [], [], []
    total_weight = 0.0
    for result, weight in results:
        b = getattr(result, bear_attr, None)
        m = getattr(result, base_attr, None)
        u = getattr(result, bull_attr, None)
        if b is not None and m is not None and u is not None and weight > 0:
            bears.append(b * weight)
            bases.append(m * weight)
            bulls.append(u * weight)
            total_weight += weight
    if total_weight == 0 or not bases:
        return None, None, None
    return (
        round(sum(bears) / total_weight, 2),
        round(sum(bases) / total_weight, 2),
        round(sum(bulls) / total_weight, 2),
    )


def _confidence_from_method_count_and_convergence(
    n_applicable: int,
    bear: Optional[float],
    base: Optional[float],
    bull: Optional[float],
    method_values: List[float],  # base-case values from all methods
) -> tuple[ValuationConfidence, str]:
    """
    Assess overall valuation confidence based on:
    - Number of applicable methods
    - Method convergence (do they agree?)
    """
    if n_applicable == 0 or base is None:
        return ValuationConfidence.LOW, "No applicable valuation methods produced a result."

    # Method convergence: compare base to each individual method output
    if len(method_values) >= 2 and base and base > 0:
        spread_pcts = [abs((v - base) / base) * 100 for v in method_values if v > 0]
        max_spread = max(spread_pcts) if spread_pcts else 0

        if max_spread > 40:
            conv_note = f"Methods diverge significantly (max spread: {max_spread:.0f}% from base) — low confidence."
            conv_conf = ValuationConfidence.LOW
        elif max_spread > 20:
            conv_note = f"Methods show moderate divergence ({max_spread:.0f}% from base) — medium confidence."
            conv_conf = ValuationConfidence.MEDIUM
        else:
            conv_note = f"Methods broadly converge (max spread: {max_spread:.0f}% from base)."
            conv_conf = ValuationConfidence.HIGH
    else:
        conv_note = "Single method result — confidence limited."
        conv_conf = ValuationConfidence.MEDIUM

    # Downgrade if few methods
    if n_applicable == 1:
        if conv_conf == ValuationConfidence.HIGH:
            conv_conf = ValuationConfidence.MEDIUM
        conv_note += " Only 1 method applicable."
    elif n_applicable >= 3 and conv_conf == ValuationConfidence.HIGH:
        pass  # 3+ converging methods → maintain HIGH

    return conv_conf, conv_note


# ---------------------------------------------------------------------------
# Main synthesizer
# ---------------------------------------------------------------------------

def run_valuation(inputs: ValuationInput) -> ValuationAssessment:
    """
    Run the full Phase 5 valuation workflow.
    Returns a populated ValuationAssessment.
    """
    assessment = ValuationAssessment(
        ticker=inputs.ticker,
        company_name=inputs.company_name,
        valuation_date=inputs.valuation_date,
        currency=inputs.currency,
        fx_rate_to_cad=inputs.fx_rate_to_cad,
        fx_rate_date=inputs.fx_rate_date,
    )

    current_price = inputs.current_price.value if inputs.current_price else None
    assessment.current_price = current_price

    # --- Step 1: Select applicable methods ---
    method_assessments = select_methods(inputs)
    assessment.methods_evaluated = method_assessments

    applicable = {
        m.method for m in method_assessments
        if m.applicability in (MethodApplicability.APPLICABLE,
                                MethodApplicability.APPLICABLE_WITH_CAVEATS)
    }

    if not applicable:
        assessment.valuation_flags.append("No valuation methods are applicable — check data inputs.")
        assessment.overall_confidence = ValuationConfidence.LOW
        return assessment

    # --- Step 2: Run each applicable method ---
    from analytics.valuation.valuation_models import ValuationMethod

    # DCF
    if ValuationMethod.DCF_FCF in applicable:
        dcf = run_dcf(inputs)
        assessment.dcf_result = dcf
        if not dcf.is_valid():
            assessment.valuation_flags.append(f"DCF returned no valid result: {dcf.reliability_note}")

    # Normalized P/E
    if ValuationMethod.NORMALIZED_PE in applicable:
        _, _, pe_r = run_normalized_pe(inputs)
        assessment.normalized_pe_result = pe_r

    # EV/EBITDA
    if ValuationMethod.EV_EBITDA in applicable:
        _, _, ev_r = run_ev_ebitda(inputs)
        assessment.ev_ebitda_result = ev_r

    # P/FCF
    if ValuationMethod.PRICE_TO_FCF in applicable:
        _, _, pfcf_r = run_price_to_fcf(inputs)
        assessment.price_to_fcf_result = pfcf_r

    # Historical P/E
    if ValuationMethod.HISTORICAL_PE in applicable:
        _, _, hist_pe = run_historical_pe(inputs, current_price)
        assessment.historical_pe_result = hist_pe

    # Historical EV/EBITDA
    if ValuationMethod.HISTORICAL_EV_EBITDA in applicable:
        _, _, hist_ev = run_historical_ev_ebitda(inputs, current_price)
        assessment.historical_ev_ebitda_result = hist_ev

    # Specialist (P/BV, FFO, Revenue)
    if any(m in applicable for m in [
        ValuationMethod.PRICE_TO_BOOK,
        ValuationMethod.FFO_MULTIPLE,
        ValuationMethod.REVENUE_MULTIPLE,
    ]):
        _, _, spec = run_specialist_multiple(inputs)
        assessment.specialist_result = spec

    # Peer
    if ValuationMethod.PEER_COMPARISON in applicable:
        _, _, peer = run_peer_valuation(inputs)
        assessment.peer_valuation_result = peer

    # --- Step 3: Synthesize fair value range ---
    assessment.fair_value_range = _synthesize_fair_value(assessment, inputs)

    # --- Step 4: Margin of safety and accumulation zone ---
    if assessment.fair_value_range and current_price and current_price > 0:
        req_mos = required_margin_of_safety(
            inputs.moat_strength,
            inputs.financial_quality_hint,
            assessment.fair_value_range.confidence,
        )
        assessment.required_margin_of_safety_pct = req_mos

        fv_base = assessment.fair_value_range.base
        if fv_base and fv_base > 0:
            assessment.margin_of_safety_at_current_price_pct = round(
                (fv_base - current_price) / fv_base * 100, 1
            )

        assessment.accumulation_zone = current_accumulation_zone(
            current_price,
            assessment.fair_value_range,
            inputs.moat_strength,
            inputs.financial_quality_hint,
        )

    # --- Step 5: Overall confidence ---
    conf, conf_note = _confidence_from_method_count_and_convergence(
        n_applicable=len(applicable),
        bear=assessment.fair_value_range.bear if assessment.fair_value_range else None,
        base=assessment.fair_value_range.base if assessment.fair_value_range else None,
        bull=assessment.fair_value_range.bull if assessment.fair_value_range else None,
        method_values=_collect_base_values(assessment),
    )
    assessment.overall_confidence = conf
    assessment.confidence_reasoning = conf_note
    if assessment.fair_value_range:
        assessment.fair_value_range.confidence = conf

    # --- Step 6: Document assumptions and caveats ---
    _populate_caveats_and_assumptions(assessment, inputs)

    # --- Step 7: FX provenance note ---
    if inputs.fx_rate_to_cad != 1.0:
        assessment.data_provenance_notes.append(
            f"FX rate: 1 {inputs.currency} = {inputs.fx_rate_to_cad:.4f} CAD "
            f"(as of {inputs.fx_rate_date or 'N/A'}). "
            "Valuations are in local currency ({inputs.currency}). "
            "CAD equivalent = local value × FX rate."
        )

    return assessment


# ---------------------------------------------------------------------------
# Fair value range synthesis
# ---------------------------------------------------------------------------

def _synthesize_fair_value(
    assessment: ValuationAssessment,
    inputs: ValuationInput,
) -> FairValueRange:
    """
    Synthesize bear / base / bull from applicable method outputs.

    Strategy:
    - DCF is the primary anchor for industrial companies with predictable FCF
    - Multiples corroborate or challenge the DCF
    - Specialist methods anchor for financials/REITs
    - Peer and historical are secondary checks only
    - Weighted by method reliability
    """
    primaries = []    # (result, weight, bear, base, bull)
    secondaries = []  # Historical and peer results (used for range width only)
    primary_method_names = []

    # DCF
    dcf = assessment.dcf_result
    if dcf and dcf.is_valid() and dcf.bear_value and dcf.base_value and dcf.bull_value:
        w = _RELIABILITY_WEIGHT.get(dcf.reliability, 0.6)
        primaries.append((dcf.bear_value, dcf.base_value, dcf.bull_value, w))
        primary_method_names.append(f"DCF ({dcf.reliability.value} confidence)")

    # Specialist (highest weight for financial/REIT — no DCF)
    spec = assessment.specialist_result
    if spec and spec.is_valid():
        w = _RELIABILITY_WEIGHT.get(spec.reliability, 0.5)
        # For specialist, use implied_value_low/mid/high
        if spec.implied_value_low and spec.implied_value_mid and spec.implied_value_high:
            primaries.append((spec.implied_value_low, spec.implied_value_mid, spec.implied_value_high, w))
            primary_method_names.append(f"{spec.method.value} ({spec.reliability.value})")

    # Normalized P/E
    pe = assessment.normalized_pe_result
    if pe and pe.is_valid() and pe.implied_value_low and pe.implied_value_mid and pe.implied_value_high:
        w = _RELIABILITY_WEIGHT.get(pe.reliability, 0.5)
        primaries.append((pe.implied_value_low, pe.implied_value_mid, pe.implied_value_high, w))
        primary_method_names.append(f"Normalized P/E ({pe.reliability.value})")

    # EV/EBITDA
    ev = assessment.ev_ebitda_result
    if ev and ev.is_valid() and ev.implied_value_low and ev.implied_value_mid and ev.implied_value_high:
        w = _RELIABILITY_WEIGHT.get(ev.reliability, 0.5)
        primaries.append((ev.implied_value_low, ev.implied_value_mid, ev.implied_value_high, w))
        primary_method_names.append(f"EV/EBITDA ({ev.reliability.value})")

    # P/FCF
    pfcf = assessment.price_to_fcf_result
    if pfcf and pfcf.is_valid() and pfcf.implied_value_low and pfcf.implied_value_mid and pfcf.implied_value_high:
        w = _RELIABILITY_WEIGHT.get(pfcf.reliability, 0.5)
        primaries.append((pfcf.implied_value_low, pfcf.implied_value_mid, pfcf.implied_value_high, w))
        primary_method_names.append(f"P/FCF ({pfcf.reliability.value})")

    # Historical (secondary — informs the range)
    hist_pe = assessment.historical_pe_result
    if hist_pe and hist_pe.implied_at_low and hist_pe.implied_at_high:
        secondaries.append((hist_pe.implied_at_low, hist_pe.implied_at_median, hist_pe.implied_at_high))

    hist_ev = assessment.historical_ev_ebitda_result
    if hist_ev and hist_ev.implied_at_low and hist_ev.implied_at_high:
        secondaries.append((hist_ev.implied_at_low, hist_ev.implied_at_median, hist_ev.implied_at_high))

    if not primaries:
        # No primary methods produced results — try peer as fallback
        peer = assessment.peer_valuation_result
        if peer and peer.is_valid():
            # Use peer P/E as very rough anchor
            vals = [v for v in [
                peer.implied_value_by_pe,
                peer.implied_value_by_ev_ebitda,
                peer.implied_value_by_p_fcf,
            ] if v and v > 0]
            if vals:
                import statistics
                base_val = round(statistics.median(vals), 2)
                primaries.append((base_val * 0.85, base_val, base_val * 1.15, 0.3))
                primary_method_names.append("Peer comparison (low confidence)")

    if not primaries:
        return FairValueRange(
            currency=inputs.currency,
            confidence=ValuationConfidence.LOW,
            convergence_note="No valuation methods produced a usable result.",
        )

    # Weighted average of primary methods
    total_w = sum(w for _, _, _, w in primaries)
    w_bear = sum(b * w for b, _, _, w in primaries) / total_w
    w_base = sum(m * w for _, m, _, w in primaries) / total_w
    w_bull = sum(u * w for _, _, u, w in primaries) / total_w

    # Widen range if secondary methods suggest wider spread
    if secondaries:
        sec_lows  = [s[0] for s in secondaries if s[0]]
        sec_highs = [s[2] for s in secondaries if s[2]]
        if sec_lows:
            w_bear = min(w_bear, min(sec_lows))
        if sec_highs:
            w_bull = max(w_bull, max(sec_highs))

    # Ensure bear < base < bull ordering
    w_bear = min(w_bear, w_base)
    w_bull = max(w_bull, w_base)

    secondary_names = []
    if assessment.historical_pe_result:
        secondary_names.append("Historical P/E")
    if assessment.historical_ev_ebitda_result:
        secondary_names.append("Historical EV/EBITDA")
    if assessment.peer_valuation_result and assessment.peer_valuation_result.is_valid():
        secondary_names.append("Peer comparison")

    # Identify primary anchor method
    primary_anchor = primary_method_names[0] if primary_method_names else "N/A"

    return FairValueRange(
        bear=round(w_bear, 2),
        base=round(w_base, 2),
        bull=round(w_bull, 2),
        currency=inputs.currency,
        primary_method=primary_anchor,
        secondary_methods=secondary_names,
        confidence=ValuationConfidence.MEDIUM,  # Will be updated in Step 5
    )


def _collect_base_values(assessment: ValuationAssessment) -> List[float]:
    """Collect base-case values from all methods for convergence analysis."""
    vals = []
    if assessment.dcf_result and assessment.dcf_result.base_value:
        vals.append(assessment.dcf_result.base_value)
    for r in [assessment.normalized_pe_result, assessment.ev_ebitda_result,
              assessment.price_to_fcf_result, assessment.specialist_result]:
        if r and hasattr(r, 'implied_value_mid') and r.implied_value_mid:
            vals.append(r.implied_value_mid)
    return vals


def _populate_caveats_and_assumptions(
    assessment: ValuationAssessment,
    inputs: ValuationInput,
) -> None:
    """Add caveats and document key assumptions."""
    caveats = assessment.valuation_caveats
    assumptions = assessment.key_valuation_assumptions

    # Data quality caveats
    if inputs.company_type == CompanyType.FINANCIAL:
        caveats.append(
            "Financial institution: standard DCF and EV/EBITDA not used. "
            "Valuation is more sensitive to credit cycle and regulatory capital."
        )
    if inputs.company_type == CompanyType.CYCLICAL:
        caveats.append(
            "Cyclical company: point-in-cycle EPS or FCF may be unrepresentative. "
            "Mid-cycle normalization has been applied where possible."
        )
    if inputs.company_type == CompanyType.REIT:
        caveats.append(
            "REIT: standard earnings-based valuation less meaningful. "
            "FFO/AFFO multiple is the primary approach."
        )
    if inputs.company_type in (CompanyType.HIGH_GROWTH, CompanyType.NEGATIVE_FCF):
        caveats.append(
            "High-growth / negative FCF: conventional valuation methods are unreliable. "
            "Results should be treated as highly illustrative."
        )

    # DCF terminal value warning
    if assessment.dcf_result and assessment.dcf_result.terminal_value_warning:
        caveats.append(
            f"DCF terminal value accounts for "
            f"{assessment.dcf_result.terminal_value_pct_of_base:.0f}% of total value — "
            "small changes in terminal growth rate have large impact on result."
        )

    # General
    caveats.append(
        "All valuations are estimates with inherent uncertainty. "
        "Fair value ranges are not guarantees of future price performance."
    )
    caveats.append(
        "This assessment does not constitute an investment recommendation. "
        "Phase 7 (Decision Engine) combines this with business quality and portfolio context."
    )

    # Key assumptions
    if assessment.dcf_result and assessment.dcf_result.is_valid():
        assumptions.extend([
            f"DCF base discount rate: {assessment.dcf_result.base_discount_rate:.1f}% "
            f"(derived from moat: {inputs.moat_strength})",
            f"DCF terminal growth rate: {assessment.dcf_result.terminal_growth_rate:.1f}%",
            f"DCF growth: {assessment.dcf_result.base_growth_rates[0]:.1f}% → "
            f"{assessment.dcf_result.base_growth_rates[-1]:.1f}% (decay schedule)",
        ])

    if assessment.normalized_pe_result:
        r = assessment.normalized_pe_result
        assumptions.append(
            f"Normalized EPS: {r.metric_value:.2f} {inputs.currency} "
            f"({r.normalization_note}) | P/E range: {r.multiple_low:.1f}–{r.multiple_high:.1f}x"
        )

    if inputs.fx_rate_to_cad != 1.0:
        assumptions.append(
            f"Currency: {inputs.currency} | FX to CAD: {inputs.fx_rate_to_cad:.4f} "
            f"(as of {inputs.fx_rate_date or 'N/A'})"
        )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from analytics.valuation.valuation_models import InputItem, InputType, PeerData

    print("Testing valuation_synthesizer.py...")

    def _item(name, value, source="Annual Report FY2024", period="FY2024",
              currency="CAD", itype=InputType.REPORTED):
        return InputItem(name=name, value=value, source=source, period=period,
                         currency=currency, input_type=itype)

    # Full industrial company — CNR-like
    inputs = ValuationInput(
        ticker="CNR.TO",
        company_name="Canadian National Railway",
        company_type=CompanyType.INDUSTRIAL,
        valuation_date="2024-12-31",
        currency="CAD",
        current_price=_item("Price", 170.0, source="Market data", period="2024-12-31"),
        shares_outstanding=_item("Shares", 670.0),
        eps_ttm=_item("EPS", 8.50),
        ebitda=_item("EBITDA", 8_500.0),
        total_debt=_item("Debt", 15_000.0),
        cash_and_equivalents=_item("Cash", 1_200.0),
        fcf_ttm=_item("FCF TTM", 3_800.0),
        fcf_normalized=_item("FCF Norm", 3_500.0, period="3yr avg"),
        revenue=_item("Revenue", 17_000.0),
        eps_history={"2019": 6.0, "2020": 5.5, "2021": 7.5, "2022": 8.0, "2023": 8.5},
        pe_history={"2019": 20.0, "2020": 22.0, "2021": 23.0, "2022": 19.0, "2023": 18.0},
        ev_ebitda_history={"2019": 12.0, "2020": 13.0, "2021": 14.0, "2022": 12.5, "2023": 11.5},
        fcf_history={"2019": 2800.0, "2020": 2600.0, "2021": 3100.0, "2022": 3400.0, "2023": 3700.0},
        dcf_revenue_growth_rate=7.0,
        moat_strength="STRONG",
        financial_quality_hint="EXCELLENT",
        peers=[
            PeerData("CP.TO", "CP Rail", pe_ratio=22.0, ev_ebitda=14.0, price_to_fcf=20.0),
            PeerData("UNP", "Union Pacific", pe_ratio=20.0, ev_ebitda=12.0, price_to_fcf=18.0),
        ],
    )

    result = run_valuation(inputs)
    print(result.summary_text())

    assert result.fair_value_range is not None
    assert result.fair_value_range.base is not None
    assert result.accumulation_zone is not None
    assert result.margin_of_safety_at_current_price_pct is not None
    print(f"\nAssertions passed — JSON keys: {list(result.to_dict().keys())[:5]}...")
    print("\nvaluation_synthesizer.py: OK")
