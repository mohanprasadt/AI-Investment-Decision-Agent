"""
Method Selector — Phase 5
=========================
Determines which valuation methods are appropriate for a given company,
based on: company type, data availability, FCF sign, earnings history,
and available peer data.

Returns a prioritized list of applicable methods with reasoning.
Does NOT run the methods — that is the synthesizer's responsibility.
"""

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.valuation.valuation_models import (
    ValuationInput, MethodAssessment, ValuationMethod,
    MethodApplicability, CompanyType,
)


def select_methods(inputs: ValuationInput) -> List[MethodAssessment]:
    """
    Evaluate all valuation methods for applicability.
    Returns a list of MethodAssessment objects (one per method).
    Ordered: primary methods first, specialist second, peer last.
    """
    assessments: List[MethodAssessment] = []

    assessments.append(_assess_dcf(inputs))
    assessments.append(_assess_normalized_pe(inputs))
    assessments.append(_assess_ev_ebitda(inputs))
    assessments.append(_assess_price_to_fcf(inputs))
    assessments.append(_assess_historical_pe(inputs))
    assessments.append(_assess_historical_ev_ebitda(inputs))
    assessments.append(_assess_specialist(inputs))
    assessments.append(_assess_peer(inputs))

    return assessments


def _assess_dcf(inputs: ValuationInput) -> MethodAssessment:
    if inputs.company_type == CompanyType.FINANCIAL:
        return MethodAssessment(
            ValuationMethod.DCF_FCF,
            MethodApplicability.NOT_APPLICABLE,
            "Financial institution: levered FCF DCF is not appropriate. Use P/BV or normalized earnings."
        )
    if inputs.company_type == CompanyType.REIT:
        return MethodAssessment(
            ValuationMethod.DCF_FCF,
            MethodApplicability.APPLICABLE_WITH_CAVEATS,
            "REIT: standard DCF run with caveats; FFO multiple is preferred primary method."
        )
    base_fcf_item = inputs.dcf_base_fcf or inputs.fcf_normalized or inputs.fcf_ttm
    if base_fcf_item is None or base_fcf_item.value is None:
        return MethodAssessment(
            ValuationMethod.DCF_FCF,
            MethodApplicability.INSUFFICIENT_DATA,
            "No FCF data available for DCF."
        )
    if not inputs.has_positive_fcf():
        if inputs.company_type == CompanyType.HIGH_GROWTH:
            return MethodAssessment(
                ValuationMethod.DCF_FCF,
                MethodApplicability.APPLICABLE_WITH_CAVEATS,
                "Negative FCF: DCF run on projected revenue-to-FCF basis — highly illustrative only."
            )
        return MethodAssessment(
            ValuationMethod.DCF_FCF,
            MethodApplicability.NOT_APPLICABLE,
            "Negative FCF: conventional DCF is unreliable. Use revenue multiple instead."
        )
    if inputs.shares_outstanding is None or inputs.shares_outstanding.value is None:
        return MethodAssessment(
            ValuationMethod.DCF_FCF,
            MethodApplicability.INSUFFICIENT_DATA,
            "Shares outstanding not available."
        )
    return MethodAssessment(
        ValuationMethod.DCF_FCF,
        MethodApplicability.APPLICABLE,
        "Positive FCF with shares data available — DCF applicable."
    )


def _assess_normalized_pe(inputs: ValuationInput) -> MethodAssessment:
    if inputs.company_type == CompanyType.REIT:
        return MethodAssessment(
            ValuationMethod.NORMALIZED_PE,
            MethodApplicability.NOT_APPLICABLE,
            "REIT: use FFO/AFFO multiple instead of P/E."
        )
    if not inputs.has_positive_earnings():
        return MethodAssessment(
            ValuationMethod.NORMALIZED_PE,
            MethodApplicability.NOT_APPLICABLE,
            "Negative or zero earnings — P/E not applicable."
        )
    if inputs.company_type == CompanyType.CYCLICAL:
        return MethodAssessment(
            ValuationMethod.NORMALIZED_PE,
            MethodApplicability.APPLICABLE_WITH_CAVEATS,
            "Cyclical: P/E applicable only on normalized (mid-cycle) earnings — not current-year EPS."
        )
    norm_eps = inputs.normalized_eps()
    if norm_eps is None or norm_eps <= 0:
        return MethodAssessment(
            ValuationMethod.NORMALIZED_PE,
            MethodApplicability.INSUFFICIENT_DATA,
            "Normalized EPS could not be derived."
        )
    return MethodAssessment(
        ValuationMethod.NORMALIZED_PE,
        MethodApplicability.APPLICABLE,
        "Positive earnings available — normalized P/E applicable."
    )


def _assess_ev_ebitda(inputs: ValuationInput) -> MethodAssessment:
    # Types where no meaningful EV/EBITDA multiple range exists
    if inputs.company_type == CompanyType.FINANCIAL:
        return MethodAssessment(
            ValuationMethod.EV_EBITDA,
            MethodApplicability.NOT_APPLICABLE,
            "Financial institution: EV/EBITDA not meaningful (debt is a revenue source)."
        )
    if inputs.company_type == CompanyType.NEGATIVE_FCF:
        return MethodAssessment(
            ValuationMethod.EV_EBITDA,
            MethodApplicability.NOT_APPLICABLE,
            "NEGATIVE_FCF: no meaningful EV/EBITDA multiple range — use revenue multiple instead."
        )
    ebitda = inputs.ebitda.value if inputs.ebitda else None
    if ebitda is None or ebitda <= 0:
        return MethodAssessment(
            ValuationMethod.EV_EBITDA,
            MethodApplicability.NOT_APPLICABLE,
            "Negative or zero EBITDA."
        )
    if inputs.enterprise_value() is None:
        return MethodAssessment(
            ValuationMethod.EV_EBITDA,
            MethodApplicability.INSUFFICIENT_DATA,
            "Cannot calculate EV — missing price, debt, or cash data."
        )
    return MethodAssessment(
        ValuationMethod.EV_EBITDA,
        MethodApplicability.APPLICABLE,
        "EBITDA and EV available — EV/EBITDA applicable."
    )


def _assess_price_to_fcf(inputs: ValuationInput) -> MethodAssessment:
    if inputs.company_type in (CompanyType.FINANCIAL, CompanyType.REIT):
        return MethodAssessment(
            ValuationMethod.PRICE_TO_FCF,
            MethodApplicability.NOT_APPLICABLE,
            f"{inputs.company_type.value}: P/FCF is not the primary metric."
        )
    if not inputs.has_positive_fcf():
        return MethodAssessment(
            ValuationMethod.PRICE_TO_FCF,
            MethodApplicability.NOT_APPLICABLE,
            "Negative or zero FCF — P/FCF not applicable."
        )
    return MethodAssessment(
        ValuationMethod.PRICE_TO_FCF,
        MethodApplicability.APPLICABLE,
        "Positive FCF — P/FCF applicable."
    )


def _assess_historical_pe(inputs: ValuationInput) -> MethodAssessment:
    if not inputs.has_positive_earnings():
        return MethodAssessment(
            ValuationMethod.HISTORICAL_PE,
            MethodApplicability.NOT_APPLICABLE,
            "No positive earnings — historical P/E comparison not possible."
        )
    if len(inputs.pe_history) < 3:
        return MethodAssessment(
            ValuationMethod.HISTORICAL_PE,
            MethodApplicability.INSUFFICIENT_DATA,
            f"Only {len(inputs.pe_history)} year(s) of P/E history — need at least 3."
        )
    return MethodAssessment(
        ValuationMethod.HISTORICAL_PE,
        MethodApplicability.APPLICABLE,
        f"{len(inputs.pe_history)} years of P/E history available."
    )


def _assess_historical_ev_ebitda(inputs: ValuationInput) -> MethodAssessment:
    if inputs.company_type == CompanyType.FINANCIAL:
        return MethodAssessment(
            ValuationMethod.HISTORICAL_EV_EBITDA,
            MethodApplicability.NOT_APPLICABLE,
            "Financial institution: historical EV/EBITDA not meaningful."
        )
    if len(inputs.ev_ebitda_history) < 3:
        return MethodAssessment(
            ValuationMethod.HISTORICAL_EV_EBITDA,
            MethodApplicability.INSUFFICIENT_DATA,
            f"Only {len(inputs.ev_ebitda_history)} year(s) of EV/EBITDA history."
        )
    return MethodAssessment(
        ValuationMethod.HISTORICAL_EV_EBITDA,
        MethodApplicability.APPLICABLE,
        f"{len(inputs.ev_ebitda_history)} years of EV/EBITDA history available."
    )


def _assess_specialist(inputs: ValuationInput) -> MethodAssessment:
    if inputs.company_type == CompanyType.FINANCIAL:
        bvps = inputs.book_value_per_share
        if bvps and bvps.value and bvps.value > 0:
            return MethodAssessment(
                ValuationMethod.PRICE_TO_BOOK,
                MethodApplicability.APPLICABLE,
                "Financial institution: P/BV is the primary valuation metric."
            )
        return MethodAssessment(
            ValuationMethod.PRICE_TO_BOOK,
            MethodApplicability.INSUFFICIENT_DATA,
            "Book value per share not provided."
        )
    if inputs.company_type == CompanyType.REIT:
        ffo = inputs.affo_per_share or inputs.ffo_per_share
        if ffo and ffo.value and ffo.value > 0:
            return MethodAssessment(
                ValuationMethod.FFO_MULTIPLE,
                MethodApplicability.APPLICABLE,
                "REIT: FFO/AFFO multiple is the primary valuation metric."
            )
        return MethodAssessment(
            ValuationMethod.FFO_MULTIPLE,
            MethodApplicability.INSUFFICIENT_DATA,
            "FFO/AFFO per share not provided for REIT."
        )
    if inputs.company_type in (CompanyType.HIGH_GROWTH, CompanyType.NEGATIVE_FCF):
        rev = inputs.revenue
        if rev and rev.value and rev.value > 0:
            return MethodAssessment(
                ValuationMethod.REVENUE_MULTIPLE,
                MethodApplicability.APPLICABLE_WITH_CAVEATS,
                "High-growth/negative-FCF: EV/Revenue applicable with significant uncertainty."
            )
        return MethodAssessment(
            ValuationMethod.REVENUE_MULTIPLE,
            MethodApplicability.INSUFFICIENT_DATA,
            "Revenue not available for EV/Sales calculation."
        )
    # No specialist method for standard industrial
    return MethodAssessment(
        ValuationMethod.REVENUE_MULTIPLE,
        MethodApplicability.NOT_APPLICABLE,
        "No specialist multiple required for this company type."
    )


def _assess_peer(inputs: ValuationInput) -> MethodAssessment:
    n_peers = len(inputs.peers)
    if n_peers == 0:
        return MethodAssessment(
            ValuationMethod.PEER_COMPARISON,
            MethodApplicability.INSUFFICIENT_DATA,
            "No peer data provided."
        )
    if n_peers == 1:
        return MethodAssessment(
            ValuationMethod.PEER_COMPARISON,
            MethodApplicability.APPLICABLE_WITH_CAVEATS,
            "Only 1 peer available — low confidence; single data point."
        )
    return MethodAssessment(
        ValuationMethod.PEER_COMPARISON,
        MethodApplicability.APPLICABLE,
        f"{n_peers} peers provided — peer comparison applicable."
    )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from analytics.valuation.valuation_models import InputItem, InputType

    print("Testing method_selector.py...")

    def _item(name, value, currency="CAD"):
        return InputItem(name=name, value=value, currency=currency,
                         input_type=InputType.REPORTED)

    # Normal industrial
    inputs = ValuationInput(
        ticker="CNR.TO", company_name="CN Rail",
        company_type=CompanyType.INDUSTRIAL,
        valuation_date="2024-12-31", currency="CAD",
        current_price=_item("Price", 170.0),
        shares_outstanding=_item("Shares", 670.0),
        eps_ttm=_item("EPS", 8.5),
        ebitda=_item("EBITDA", 8_500.0),
        total_debt=_item("Debt", 15_000.0),
        cash_and_equivalents=_item("Cash", 1_200.0),
        fcf_ttm=_item("FCF", 3_800.0),
        eps_history={"2020": 6.0, "2021": 7.5, "2022": 8.0, "2023": 8.5},
        pe_history={"2020": 22.0, "2021": 23.0, "2022": 19.0, "2023": 18.0},
        ev_ebitda_history={"2020": 13.0, "2021": 14.0, "2022": 12.5, "2023": 11.5},
        peers=[
            PeerData("CP.TO", "CP Rail", pe_ratio=22.0),
            PeerData("UNP", "Union Pacific", pe_ratio=20.0),
        ],
    )

    from analytics.valuation.valuation_models import PeerData
    methods = select_methods(inputs)
    for m in methods:
        print(f"  {m.method.value}: {m.applicability.value} — {m.reason[:60]}")

    applicable = [m for m in methods if m.applicability in (
        MethodApplicability.APPLICABLE, MethodApplicability.APPLICABLE_WITH_CAVEATS)]
    assert len(applicable) >= 4, f"Expected at least 4 applicable methods, got {len(applicable)}"

    print("\nmethod_selector.py: OK")
