"""
Multiples Engine — Phase 5
==========================
Implements:
  1. Normalized P/E valuation
  2. EV/EBITDA valuation
  3. Price-to-FCF valuation
  4. Historical multiple comparison (P/E, EV/EBITDA)
  5. Peer valuation
  6. Specialist multiples: P/BV (financials), FFO (REITs), P/Revenue (high-growth)

Design rules:
  - Negative earnings → P/E not applicable; say so explicitly
  - Negative EBITDA → EV/EBITDA not applicable
  - Negative FCF → P/FCF not applicable
  - Insufficient history (<3yr) → historical comparison flagged as low confidence
  - Fewer than 2 peers → peer comparison flagged as not reliable
  - All multiple ranges are documented with their basis
  - All implied values are per share in local currency
"""

import sys
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.valuation.valuation_models import (
    ValuationInput, MultipleValuationResult, HistoricalMultiplesResult,
    PeerValuationResult, PeerData,
    ValuationMethod, MethodApplicability, MethodReliability, ValuationConfidence,
    CompanyType,
)


# ---------------------------------------------------------------------------
# Default multiple ranges by context
# ---------------------------------------------------------------------------

# Historical "reasonable range" defaults by company type — used when no history available
_DEFAULT_PE_RANGES = {
    CompanyType.INDUSTRIAL:   (12.0, 18.0, 25.0),   # low, mid, high
    CompanyType.HIGH_GROWTH:  (25.0, 40.0, 60.0),
    CompanyType.CYCLICAL:     (8.0,  12.0, 18.0),   # use trough earnings for cyclicals
    CompanyType.UTILITY:      (15.0, 19.0, 24.0),
    CompanyType.FINANCIAL:    (9.0,  13.0, 17.0),   # P/E for financials is acceptable
    CompanyType.REIT:         (None, None, None),    # Use FFO instead
    CompanyType.NEGATIVE_FCF: (None, None, None),   # No P/E applicable
}

_DEFAULT_EV_EBITDA_RANGES = {
    CompanyType.INDUSTRIAL:  (7.0,  11.0, 15.0),
    CompanyType.HIGH_GROWTH: (15.0, 25.0, 40.0),
    CompanyType.CYCLICAL:    (4.0,   7.0, 10.0),
    CompanyType.UTILITY:     (10.0, 13.0, 16.0),
    CompanyType.FINANCIAL:   (None, None, None),   # EV/EBITDA not meaningful for banks
    CompanyType.REIT:        (12.0, 16.0, 22.0),
    CompanyType.NEGATIVE_FCF:(None, None, None),
}

_DEFAULT_P_FCF_RANGES = {
    CompanyType.INDUSTRIAL:  (12.0, 18.0, 25.0),
    CompanyType.HIGH_GROWTH: (None, None, None),   # Usually negative FCF
    CompanyType.CYCLICAL:    (8.0,  13.0, 18.0),
    CompanyType.UTILITY:     (12.0, 16.0, 22.0),
    CompanyType.FINANCIAL:   (None, None, None),
    CompanyType.REIT:        (None, None, None),   # Use FFO
    CompanyType.NEGATIVE_FCF:(None, None, None),
}


def _derive_multiple_range_from_history(
    history: Dict[str, float],
    min_years: int = 3,
) -> Optional[Tuple[float, float, float]]:
    """
    Derive (low, median, high) from historical multiple series.
    Returns None if insufficient history.
    """
    if len(history) < min_years:
        return None
    values = [v for v in history.values() if v is not None and v > 0]
    if len(values) < min_years:
        return None
    low = min(values)
    high = max(values)
    med = statistics.median(values)
    return (round(low, 1), round(med, 1), round(high, 1))


def _current_percentile(current: float, history: Dict[str, float]) -> Optional[float]:
    """Where does the current multiple sit in its historical distribution? (0–100%)"""
    values = sorted([v for v in history.values() if v is not None and v > 0])
    if not values:
        return None
    below = sum(1 for v in values if v <= current)
    return round((below / len(values)) * 100, 1)


# ---------------------------------------------------------------------------
# 1. Normalized P/E valuation
# ---------------------------------------------------------------------------

def run_normalized_pe(inputs: ValuationInput) -> Tuple[MethodApplicability, str, Optional[MultipleValuationResult]]:
    """
    Normalized P/E valuation.
    Returns (applicability, reason, result_or_None).
    """
    # Guard: not applicable for REITs or negative-FCF companies
    if inputs.company_type == CompanyType.REIT:
        return (MethodApplicability.NOT_APPLICABLE,
                "REIT: Use FFO/AFFO multiple instead of P/E.", None)

    norm_eps = inputs.normalized_eps()
    if norm_eps is None or norm_eps <= 0:
        if inputs.has_positive_earnings():
            # TTM positive but historical normalization failed
            if inputs.eps_ttm and inputs.eps_ttm.value and inputs.eps_ttm.value > 0:
                norm_eps = inputs.eps_ttm.value
                norm_note = "Using TTM EPS (historical normalization not available)"
            else:
                return (MethodApplicability.NOT_APPLICABLE,
                        "Negative or zero earnings — P/E not applicable.", None)
        else:
            return (MethodApplicability.NOT_APPLICABLE,
                    "Negative or zero earnings — P/E not applicable.", None)
    else:
        years_used = min(len(inputs.eps_history), 5) if inputs.eps_history else 1
        if years_used > 1:
            # List the exact fiscal years covered so the renderer can do an
            # explicit year-set comparison with the FCF normalization window.
            _eps_yr_list = sorted(int(y) for y in inputs.eps_history.keys())
            _eps_yr_str = ", ".join(f"FY{y}" for y in _eps_yr_list)
            norm_note = (
                f"Normalized EPS: {years_used}-year average of continuing-ops "
                f"derived EPS (net income from continuing operations ÷ shares); "
                f"years: {_eps_yr_str}"
            )
        else:
            norm_note = "Using TTM EPS (no annual history available)"

    # Determine multiple range
    if inputs.pe_history:
        range_result = _derive_multiple_range_from_history(inputs.pe_history)
        if range_result:
            p_low, p_mid, p_high = range_result
            multiple_basis = f"Company's own {len(inputs.pe_history)}-year P/E history"
        else:
            defaults = _DEFAULT_PE_RANGES.get(inputs.company_type, (12.0, 18.0, 25.0))
            if defaults[0] is None:
                return (MethodApplicability.NOT_APPLICABLE,
                        "No applicable P/E range for this company type.", None)
            p_low, p_mid, p_high = defaults
            multiple_basis = f"Default range for {inputs.company_type.value} (insufficient history)"
    else:
        defaults = _DEFAULT_PE_RANGES.get(inputs.company_type, (12.0, 18.0, 25.0))
        if defaults[0] is None:
            return (MethodApplicability.NOT_APPLICABLE,
                    "No applicable P/E range for this company type.", None)
        p_low, p_mid, p_high = defaults
        multiple_basis = f"Default range for {inputs.company_type.value}"

    result = MultipleValuationResult(
        method=ValuationMethod.NORMALIZED_PE,
        metric_used="Normalized EPS",
        metric_value=norm_eps,
        normalization_note=norm_note,
        multiple_low=p_low,
        multiple_mid=p_mid,
        multiple_high=p_high,
        multiple_basis=multiple_basis,
        implied_value_low=round(norm_eps * p_low, 2),
        implied_value_mid=round(norm_eps * p_mid, 2),
        implied_value_high=round(norm_eps * p_high, 2),
    )

    # Reliability
    if inputs.pe_history and len(inputs.pe_history) >= 5:
        result.reliability = MethodReliability.HIGH
        result.reliability_note = "5+ years of P/E history available"
    elif inputs.pe_history and len(inputs.pe_history) >= 3:
        result.reliability = MethodReliability.MEDIUM
        result.reliability_note = "3–4 years of P/E history"
    else:
        result.reliability = MethodReliability.LOW
        result.reliability_note = "Using default multiple range — no company-specific history"

    if inputs.company_type == CompanyType.CYCLICAL:
        result.caveats.append(
            "Cyclical company: normalized EPS reflects a mid-cycle estimate — "
            "verify that the earnings used are genuinely representative of normal conditions."
        )

    return (MethodApplicability.APPLICABLE, "Applicable", result)


# ---------------------------------------------------------------------------
# 2. EV/EBITDA valuation
# ---------------------------------------------------------------------------

def run_ev_ebitda(inputs: ValuationInput) -> Tuple[MethodApplicability, str, Optional[MultipleValuationResult]]:
    """EV/EBITDA-based valuation."""
    if inputs.company_type == CompanyType.FINANCIAL:
        return (MethodApplicability.NOT_APPLICABLE,
                "Financial institutions: EV/EBITDA is not meaningful (debt is a revenue source).", None)

    ebitda = inputs.ebitda.value if inputs.ebitda else None
    if ebitda is None or ebitda <= 0:
        return (MethodApplicability.NOT_APPLICABLE,
                "Negative or zero EBITDA — EV/EBITDA not applicable.", None)

    ev = inputs.enterprise_value()
    if ev is None or ev <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA,
                "Enterprise value could not be calculated (missing price or debt/cash data).", None)

    shares = inputs.shares_outstanding.value if inputs.shares_outstanding else None
    if shares is None or shares <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA, "Shares outstanding not available.", None)

    # Multiple range
    if inputs.ev_ebitda_history:
        range_result = _derive_multiple_range_from_history(inputs.ev_ebitda_history)
        if range_result:
            e_low, e_mid, e_high = range_result
            multiple_basis = f"Company's own {len(inputs.ev_ebitda_history)}-year EV/EBITDA history"
        else:
            defaults = _DEFAULT_EV_EBITDA_RANGES.get(inputs.company_type, (7.0, 11.0, 15.0))
            if defaults[0] is None:
                return (MethodApplicability.NOT_APPLICABLE,
                        "No applicable EV/EBITDA range for this company type.", None)
            e_low, e_mid, e_high = defaults
            multiple_basis = "Default range"
    else:
        defaults = _DEFAULT_EV_EBITDA_RANGES.get(inputs.company_type, (7.0, 11.0, 15.0))
        if defaults[0] is None:
            return (MethodApplicability.NOT_APPLICABLE,
                    "No applicable EV/EBITDA range for this company type.", None)
        e_low, e_mid, e_high = defaults
        multiple_basis = f"Default range for {inputs.company_type.value}"

    net_debt = (inputs.total_debt.value or 0.0) - (inputs.cash_and_equivalents.value or 0.0) \
               if inputs.total_debt else 0.0

    def _implied_price(multiple: float) -> float:
        implied_ev = ebitda * multiple
        implied_equity = implied_ev - net_debt
        return round(max(implied_equity / shares, 0.0), 2)

    result = MultipleValuationResult(
        method=ValuationMethod.EV_EBITDA,
        metric_used="EBITDA",
        metric_value=ebitda,
        normalization_note="",
        multiple_low=e_low,
        multiple_mid=e_mid,
        multiple_high=e_high,
        multiple_basis=multiple_basis,
        implied_value_low=_implied_price(e_low),
        implied_value_mid=_implied_price(e_mid),
        implied_value_high=_implied_price(e_high),
        reliability=MethodReliability.MEDIUM if not inputs.ev_ebitda_history
                    else MethodReliability.HIGH if len(inputs.ev_ebitda_history) >= 5
                    else MethodReliability.MEDIUM,
        reliability_note=(
            "5+ years EV/EBITDA history" if len(inputs.ev_ebitda_history or {}) >= 5
            else "Default multiple range used" if not inputs.ev_ebitda_history
            else "Limited history"
        ),
    )
    return (MethodApplicability.APPLICABLE, "Applicable", result)


# ---------------------------------------------------------------------------
# 3. Price-to-FCF valuation
# ---------------------------------------------------------------------------

def run_price_to_fcf(inputs: ValuationInput) -> Tuple[MethodApplicability, str, Optional[MultipleValuationResult]]:
    """Price-to-FCF valuation."""
    if not inputs.has_positive_fcf():
        return (MethodApplicability.NOT_APPLICABLE,
                "Negative or zero FCF — P/FCF not applicable.", None)

    if inputs.company_type in (CompanyType.FINANCIAL, CompanyType.REIT):
        return (MethodApplicability.NOT_APPLICABLE,
                f"{inputs.company_type.value}: P/FCF not the primary metric.", None)

    fcf_item = inputs.fcf_normalized or inputs.fcf_ttm
    fcf = fcf_item.value if fcf_item else None
    if fcf is None or fcf <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA, "No positive FCF available.", None)

    shares = inputs.shares_outstanding.value if inputs.shares_outstanding else None
    if shares is None or shares <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA, "Shares outstanding not available.", None)

    fcf_per_share = fcf / shares

    if inputs.price_to_fcf_history:
        range_result = _derive_multiple_range_from_history(inputs.price_to_fcf_history)
        if range_result:
            f_low, f_mid, f_high = range_result
            multiple_basis = f"Company {len(inputs.price_to_fcf_history)}-year P/FCF history"
        else:
            defaults = _DEFAULT_P_FCF_RANGES.get(inputs.company_type, (12.0, 18.0, 25.0))
            if defaults[0] is None:
                return (MethodApplicability.NOT_APPLICABLE,
                        "No applicable P/FCF range.", None)
            f_low, f_mid, f_high = defaults
            multiple_basis = "Default range"
    else:
        defaults = _DEFAULT_P_FCF_RANGES.get(inputs.company_type, (12.0, 18.0, 25.0))
        if defaults[0] is None:
            return (MethodApplicability.NOT_APPLICABLE,
                    "No applicable P/FCF range for this company type.", None)
        f_low, f_mid, f_high = defaults
        multiple_basis = f"Default range for {inputs.company_type.value}"

    result = MultipleValuationResult(
        method=ValuationMethod.PRICE_TO_FCF,
        metric_used="FCF per share",
        metric_value=fcf_per_share,
        normalization_note=f"Source: {fcf_item.source if fcf_item else 'N/A'} ({fcf_item.period if fcf_item else 'N/A'})",
        multiple_low=f_low,
        multiple_mid=f_mid,
        multiple_high=f_high,
        multiple_basis=multiple_basis,
        implied_value_low=round(fcf_per_share * f_low, 2),
        implied_value_mid=round(fcf_per_share * f_mid, 2),
        implied_value_high=round(fcf_per_share * f_high, 2),
        reliability=MethodReliability.HIGH if inputs.price_to_fcf_history and len(inputs.price_to_fcf_history) >= 5
                    else MethodReliability.MEDIUM,
        reliability_note="P/FCF is a reliable anchor for capital-light businesses with predictable FCF",
    )
    return (MethodApplicability.APPLICABLE, "Applicable", result)


# ---------------------------------------------------------------------------
# 4. Historical multiple comparison
# ---------------------------------------------------------------------------

def run_historical_pe(
    inputs: ValuationInput,
    current_price: Optional[float] = None,
) -> Tuple[MethodApplicability, str, Optional[HistoricalMultiplesResult]]:
    """Compare current P/E against historical P/E range."""
    if not inputs.has_positive_earnings():
        return (MethodApplicability.NOT_APPLICABLE,
                "Negative earnings — historical P/E comparison not applicable.", None)
    if len(inputs.pe_history) < 3:
        return (MethodApplicability.INSUFFICIENT_DATA,
                f"Only {len(inputs.pe_history)} year(s) of P/E history — need at least 3.", None)

    price = current_price or (inputs.current_price.value if inputs.current_price else None)
    eps = inputs.eps_ttm.value if inputs.eps_ttm else None
    if price is None or eps is None or eps <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA,
                "Current price or EPS not available for historical comparison.", None)

    current_pe = price / eps
    range_result = _derive_multiple_range_from_history(inputs.pe_history)
    if range_result is None:
        return (MethodApplicability.INSUFFICIENT_DATA,
                "Insufficient valid data in P/E history.", None)
    pe_low, pe_med, pe_high = range_result
    percentile = _current_percentile(current_pe, inputs.pe_history)

    # Implied values at historical points (using current EPS)
    implied_at_med = round(eps * pe_med, 2)
    implied_at_low = round(eps * pe_low, 2)
    implied_at_high = round(eps * pe_high, 2)

    # Contextual interpretation
    if percentile is not None:
        if percentile >= 80:
            interp = (f"Currently trading at the HIGH end of its {len(inputs.pe_history)}-year "
                      f"P/E range ({current_pe:.1f}x vs median {pe_med:.1f}x). "
                      "Requires above-average growth or quality justification.")
        elif percentile <= 20:
            interp = (f"Currently trading at the LOW end of its {len(inputs.pe_history)}-year "
                      f"P/E range ({current_pe:.1f}x vs median {pe_med:.1f}x). "
                      "Historically inexpensive on this metric.")
        else:
            interp = (f"Trading near the middle of its {len(inputs.pe_history)}-year "
                      f"P/E range ({current_pe:.1f}x vs median {pe_med:.1f}x).")
    else:
        interp = f"Current P/E: {current_pe:.1f}x | Historical median: {pe_med:.1f}x"

    reliability = (MethodReliability.HIGH if len(inputs.pe_history) >= 7
                   else MethodReliability.MEDIUM)
    result = HistoricalMultiplesResult(
        metric_name="P/E",
        current_multiple=round(current_pe, 1),
        historical_low=pe_low,
        historical_median=pe_med,
        historical_high=pe_high,
        historical_years=len(inputs.pe_history),
        current_percentile=percentile,
        implied_at_median=implied_at_med,
        implied_at_low=implied_at_low,
        implied_at_high=implied_at_high,
        interpretation=interp,
        reliability=reliability,
        reliability_note=f"{len(inputs.pe_history)} years of history",
        caveats=[
            "Historical valuation ≠ intrinsic value. "
            "The market may have been systematically mispriced in prior periods."
        ],
    )
    return (MethodApplicability.APPLICABLE, "Applicable", result)


def run_historical_ev_ebitda(
    inputs: ValuationInput,
    current_price: Optional[float] = None,
) -> Tuple[MethodApplicability, str, Optional[HistoricalMultiplesResult]]:
    """Compare current EV/EBITDA against historical range."""
    if inputs.company_type == CompanyType.FINANCIAL:
        return (MethodApplicability.NOT_APPLICABLE,
                "Financial institution — EV/EBITDA historical comparison not meaningful.", None)
    if len(inputs.ev_ebitda_history) < 3:
        return (MethodApplicability.INSUFFICIENT_DATA,
                f"Only {len(inputs.ev_ebitda_history)} year(s) of EV/EBITDA history.", None)

    ev = inputs.enterprise_value()
    ebitda = inputs.ebitda.value if inputs.ebitda else None
    if ev is None or ebitda is None or ebitda <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA,
                "EV or EBITDA not available.", None)

    current_ev_ebitda = ev / ebitda
    range_result = _derive_multiple_range_from_history(inputs.ev_ebitda_history)
    if range_result is None:
        return (MethodApplicability.INSUFFICIENT_DATA,
                "Insufficient valid EV/EBITDA history.", None)
    e_low, e_med, e_high = range_result
    percentile = _current_percentile(current_ev_ebitda, inputs.ev_ebitda_history)

    shares = inputs.shares_outstanding.value if inputs.shares_outstanding else None
    net_debt = ((inputs.total_debt.value or 0.0) - (inputs.cash_and_equivalents.value or 0.0)) \
               if inputs.total_debt else 0.0

    def _implied(multiple: float) -> Optional[float]:
        if shares and shares > 0:
            return round((ebitda * multiple - net_debt) / shares, 2)
        return None

    if percentile is not None:
        if percentile >= 80:
            interp = (f"EV/EBITDA near historical high ({current_ev_ebitda:.1f}x vs median {e_med:.1f}x). "
                      "Premium valuation requires justification.")
        elif percentile <= 20:
            interp = (f"EV/EBITDA near historical low ({current_ev_ebitda:.1f}x vs median {e_med:.1f}x). "
                      "Appears historically inexpensive on this metric.")
        else:
            interp = (f"EV/EBITDA in normal range ({current_ev_ebitda:.1f}x vs median {e_med:.1f}x).")
    else:
        interp = f"Current EV/EBITDA: {current_ev_ebitda:.1f}x | Median: {e_med:.1f}x"

    result = HistoricalMultiplesResult(
        metric_name="EV/EBITDA",
        current_multiple=round(current_ev_ebitda, 1),
        historical_low=e_low,
        historical_median=e_med,
        historical_high=e_high,
        historical_years=len(inputs.ev_ebitda_history),
        current_percentile=percentile,
        implied_at_median=_implied(e_med),
        implied_at_low=_implied(e_low),
        implied_at_high=_implied(e_high),
        interpretation=interp,
        reliability=MethodReliability.HIGH if len(inputs.ev_ebitda_history) >= 7
                    else MethodReliability.MEDIUM,
        reliability_note=f"{len(inputs.ev_ebitda_history)} years of history",
        caveats=["Historical EV/EBITDA is contextual, not intrinsic value."],
    )
    return (MethodApplicability.APPLICABLE, "Applicable", result)


# ---------------------------------------------------------------------------
# 5. Peer valuation
# ---------------------------------------------------------------------------

def run_peer_valuation(inputs: ValuationInput) -> Tuple[MethodApplicability, str, Optional[PeerValuationResult]]:
    """Relative valuation against peer companies."""
    if not inputs.peers:
        return (MethodApplicability.INSUFFICIENT_DATA,
                "No peer data provided.", None)
    if len(inputs.peers) < 2:
        return (MethodApplicability.APPLICABLE_WITH_CAVEATS,
                "Only one peer provided — peer comparison is low confidence with a single data point.",
                _build_peer_result(inputs, inputs.peers))

    return (MethodApplicability.APPLICABLE, "Peer comparison applicable.",
            _build_peer_result(inputs, inputs.peers))


def _build_peer_result(inputs: ValuationInput, peers: List[PeerData]) -> PeerValuationResult:
    result = PeerValuationResult()
    result.peers_used = peers

    # Peer medians
    pe_vals = [p.pe_ratio for p in peers if p.pe_ratio and p.pe_ratio > 0]
    ev_vals = [p.ev_ebitda for p in peers if p.ev_ebitda and p.ev_ebitda > 0]
    pfcf_vals = [p.price_to_fcf for p in peers if p.price_to_fcf and p.price_to_fcf > 0]

    result.peer_median_pe = round(statistics.median(pe_vals), 1) if pe_vals else None
    result.peer_median_ev_ebitda = round(statistics.median(ev_vals), 1) if ev_vals else None
    result.peer_median_p_fcf = round(statistics.median(pfcf_vals), 1) if pfcf_vals else None

    # Implied values
    shares = inputs.shares_outstanding.value if inputs.shares_outstanding else None
    eps = inputs.eps_ttm.value if inputs.eps_ttm else None
    ebitda = inputs.ebitda.value if inputs.ebitda else None
    fcf_item = inputs.fcf_normalized or inputs.fcf_ttm
    fcf = fcf_item.value if fcf_item else None
    net_debt = ((inputs.total_debt.value or 0.0) - (inputs.cash_and_equivalents.value or 0.0)) \
               if inputs.total_debt else 0.0

    if result.peer_median_pe and eps and eps > 0:
        result.implied_value_by_pe = round(eps * result.peer_median_pe, 2)

    if result.peer_median_ev_ebitda and ebitda and ebitda > 0 and shares and shares > 0:
        result.implied_value_by_ev_ebitda = round(
            (ebitda * result.peer_median_ev_ebitda - net_debt) / shares, 2
        )

    if result.peer_median_p_fcf and fcf and fcf > 0 and shares and shares > 0:
        result.implied_value_by_p_fcf = round((fcf / shares) * result.peer_median_p_fcf, 2)

    # Premium / discount to peers (using P/E as primary if available)
    current_price = inputs.current_price.value if inputs.current_price else None
    if result.implied_value_by_pe and current_price and current_price > 0:
        result.premium_discount_to_peers_pct = round(
            (current_price / result.implied_value_by_pe - 1) * 100, 1
        )

    result.reliability = MethodReliability.LOW if len(peers) < 3 else MethodReliability.MEDIUM
    result.reliability_note = (
        f"{len(peers)} peer(s) used. Peer comparisons are inherently imprecise — "
        "business quality differences are not fully captured in multiples alone."
    )
    result.applicability_note = (
        "Peer valuation is a secondary check. "
        "Premiums to peers may be justified by superior moat, growth, or capital allocation."
    )
    result.caveats.append(
        "Peer valuation reflects market pricing, not intrinsic value. "
        "If the entire peer group is overvalued, implied values will also be elevated."
    )
    return result


# ---------------------------------------------------------------------------
# 6. Specialist multiples
# ---------------------------------------------------------------------------

def run_specialist_multiple(inputs: ValuationInput) -> Tuple[MethodApplicability, str, Optional[MultipleValuationResult]]:
    """
    Specialist multiples by company type:
      - Financial institutions: P/Book Value
      - REITs: FFO or AFFO multiple
      - High-growth / negative FCF: Price-to-Revenue (EV/Sales)
    """
    if inputs.company_type == CompanyType.FINANCIAL:
        return _run_price_to_book(inputs)

    if inputs.company_type == CompanyType.REIT:
        return _run_ffo_multiple(inputs)

    if inputs.company_type in (CompanyType.HIGH_GROWTH, CompanyType.NEGATIVE_FCF):
        return _run_revenue_multiple(inputs)

    return (MethodApplicability.NOT_APPLICABLE,
            "No specialist multiple applicable for this company type.", None)


def _run_price_to_book(inputs: ValuationInput) -> Tuple[MethodApplicability, str, Optional[MultipleValuationResult]]:
    bvps = inputs.book_value_per_share.value if inputs.book_value_per_share else None
    if bvps is None or bvps <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA,
                "Book value per share not available.", None)

    # For financial institutions, P/BV typical range
    # High-quality bank: 1.5–2.5x; average: 1.0–1.8x; stressed: 0.7–1.2x
    p_low, p_mid, p_high = 1.0, 1.5, 2.0

    result = MultipleValuationResult(
        method=ValuationMethod.PRICE_TO_BOOK,
        metric_used="Book Value per Share",
        metric_value=bvps,
        normalization_note="Tangible book value preferred where available",
        multiple_low=p_low, multiple_mid=p_mid, multiple_high=p_high,
        multiple_basis="Typical range for financial institutions",
        implied_value_low=round(bvps * p_low, 2),
        implied_value_mid=round(bvps * p_mid, 2),
        implied_value_high=round(bvps * p_high, 2),
        reliability=MethodReliability.MEDIUM,
        reliability_note="P/BV range is wide for financials; ROE-adjusted P/BV preferred",
        caveats=["Book value quality depends heavily on loan loss provisioning and write-downs."],
    )
    return (MethodApplicability.APPLICABLE, "P/BV applicable for financial institution.", result)


def _run_ffo_multiple(inputs: ValuationInput) -> Tuple[MethodApplicability, str, Optional[MultipleValuationResult]]:
    ffo = inputs.affo_per_share or inputs.ffo_per_share
    if ffo is None or ffo.value is None or ffo.value <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA,
                "FFO/AFFO per share not available for REIT valuation.", None)

    metric_name = "AFFO per share" if inputs.affo_per_share else "FFO per share"
    # REIT FFO multiples: 12–20x is typical range
    f_low, f_mid, f_high = 12.0, 16.0, 22.0

    result = MultipleValuationResult(
        method=ValuationMethod.FFO_MULTIPLE,
        metric_used=metric_name,
        metric_value=ffo.value,
        normalization_note="AFFO preferred over FFO where available (accounts for maintenance capex)",
        multiple_low=f_low, multiple_mid=f_mid, multiple_high=f_high,
        multiple_basis="Typical REIT FFO range; varies by property type and quality",
        implied_value_low=round(ffo.value * f_low, 2),
        implied_value_mid=round(ffo.value * f_mid, 2),
        implied_value_high=round(ffo.value * f_high, 2),
        reliability=MethodReliability.MEDIUM,
        reliability_note="FFO multiples are the standard REIT metric but vary significantly by property type",
        caveats=["REIT multiple ranges depend heavily on property sector, leverage, and interest rates."],
    )
    return (MethodApplicability.APPLICABLE, "FFO multiple applicable for REIT.", result)


def _run_revenue_multiple(inputs: ValuationInput) -> Tuple[MethodApplicability, str, Optional[MultipleValuationResult]]:
    revenue = inputs.revenue.value if inputs.revenue else None
    shares = inputs.shares_outstanding.value if inputs.shares_outstanding else None
    if revenue is None or revenue <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA, "Revenue not available.", None)
    if shares is None or shares <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA, "Shares not available.", None)

    ev = inputs.enterprise_value()
    if ev is None or ev <= 0:
        return (MethodApplicability.INSUFFICIENT_DATA, "EV not available.", None)

    current_ev_sales = ev / revenue
    net_debt = ((inputs.total_debt.value or 0.0) - (inputs.cash_and_equivalents.value or 0.0)) \
               if inputs.total_debt else 0.0
    revenue_per_share = revenue / shares

    # EV/Sales multiples for high-growth SaaS/tech: wide range
    e_low, e_mid, e_high = 3.0, 7.0, 15.0

    def _implied_from_ev_sales(multiple: float) -> float:
        return round((revenue * multiple - net_debt) / shares, 2)

    result = MultipleValuationResult(
        method=ValuationMethod.REVENUE_MULTIPLE,
        metric_used="Revenue (EV/Sales)",
        metric_value=current_ev_sales,
        normalization_note="EV/Sales used for high-growth or negative-FCF companies",
        multiple_low=e_low, multiple_mid=e_mid, multiple_high=e_high,
        multiple_basis="Illustrative range for high-growth/negative-FCF companies; highly uncertain",
        implied_value_low=_implied_from_ev_sales(e_low),
        implied_value_mid=_implied_from_ev_sales(e_mid),
        implied_value_high=_implied_from_ev_sales(e_high),
        reliability=MethodReliability.LOW,
        reliability_note="Revenue multiples have very low precision — useful for range check only",
        caveats=[
            "EV/Sales is a highly uncertain metric — small changes in assumed multiple produce large value swings.",
            "This multiple is only meaningful when FCF profitability is achievable in a reasonable timeframe.",
        ],
    )
    return (MethodApplicability.APPLICABLE_WITH_CAVEATS,
            "EV/Sales applicable with significant caveats for negative-FCF company.", result)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from analytics.valuation.valuation_models import InputItem, InputType

    print("Testing multiples_engine.py...")

    def _item(name, value, source="Annual Report", period="FY2024", currency="CAD"):
        return InputItem(name=name, value=value, source=source, period=period,
                         currency=currency, input_type=InputType.REPORTED)

    # Normal industrial company
    inputs = ValuationInput(
        ticker="CNR.TO", company_name="CN Rail",
        company_type=CompanyType.INDUSTRIAL,
        valuation_date="2024-12-31", currency="CAD",
        current_price=_item("Price", 170.0),
        shares_outstanding=_item("Shares", 670.0),
        eps_ttm=_item("EPS", 8.50),
        ebitda=_item("EBITDA", 8_500.0),
        total_debt=_item("Debt", 15_000.0),
        cash_and_equivalents=_item("Cash", 1_200.0),
        fcf_ttm=_item("FCF", 3_800.0),
        fcf_normalized=_item("FCF Norm", 3_500.0, period="3yr avg"),
        eps_history={"2019": 6.5, "2020": 6.0, "2021": 7.5, "2022": 8.0, "2023": 8.5},
        pe_history={"2019": 20.0, "2020": 22.0, "2021": 23.0, "2022": 19.0, "2023": 18.0},
        ev_ebitda_history={"2019": 12.0, "2020": 13.0, "2021": 14.0, "2022": 12.5, "2023": 11.5},
        peers=[
            PeerData("CP.TO", "CP Rail", pe_ratio=22.0, ev_ebitda=14.0, price_to_fcf=20.0),
            PeerData("UNP", "Union Pacific", pe_ratio=20.0, ev_ebitda=12.0, price_to_fcf=18.0),
        ],
        moat_strength="STRONG",
    )

    app, reason, pe_result = run_normalized_pe(inputs)
    print(f"  P/E: {app.value} — implied mid: {pe_result.implied_value_mid if pe_result else 'N/A'}")

    app, reason, ev_result = run_ev_ebitda(inputs)
    print(f"  EV/EBITDA: {app.value} — implied mid: {ev_result.implied_value_mid if ev_result else 'N/A'}")

    app, reason, fcf_result = run_price_to_fcf(inputs)
    print(f"  P/FCF: {app.value} — implied mid: {fcf_result.implied_value_mid if fcf_result else 'N/A'}")

    app, reason, hist_pe = run_historical_pe(inputs)
    print(f"  Historical P/E: {app.value} — percentile: {hist_pe.current_percentile if hist_pe else 'N/A'}%")

    app, reason, hist_ev = run_historical_ev_ebitda(inputs)
    print(f"  Historical EV/EBITDA: {app.value} — percentile: {hist_ev.current_percentile if hist_ev else 'N/A'}%")

    app, reason, peer = run_peer_valuation(inputs)
    print(f"  Peer: {app.value} — implied by P/E: {peer.implied_value_by_pe if peer else 'N/A'}")

    # Financial institution — negative cases
    bank_inputs = ValuationInput(
        ticker="TD.TO", company_name="TD Bank",
        company_type=CompanyType.FINANCIAL,
        valuation_date="2024-12-31", currency="CAD",
        current_price=_item("Price", 80.0),
        shares_outstanding=_item("Shares", 1800.0),
        eps_ttm=_item("EPS", 7.20),
        book_value_per_share=_item("BVPS", 55.0),
        moat_strength="MODERATE",
    )
    app, reason, ev_r = run_ev_ebitda(bank_inputs)
    assert app == MethodApplicability.NOT_APPLICABLE
    print(f"  Bank EV/EBITDA correctly blocked: {reason[:50]}...")

    app, reason, spec = run_specialist_multiple(bank_inputs)
    print(f"  Bank P/BV: {app.value} — implied mid: {spec.implied_value_mid if spec else 'N/A'}")

    print("\nmultiples_engine.py: OK")
