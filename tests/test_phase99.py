"""
Phase 9.9 — Regression tests
==============================

Covers:
  A — annual_ocf persistence in FreeCashFlowMetrics and normalizer
  B — eps_history population in valuation_builder
  C — normalized_eps() no longer unnecessarily falls back to TTM
  D — same-period EPS/FCF reconciliation display
  E — explicit missing-component messaging (D&A, WC, tax)
  F — no-fabrication / no capex-exceeds-D&A assertion
  G — period-mismatch warning for TTM EPS vs 3yr-avg FCF
  H — non-regression: existing Phase 9.7/9.8 tests must not break

Key constants (ITC-like fixture):
  Net income per year:  FY2024 ≈ 200B, FY2025 ≈ 210B, FY2026 ≈ 220B  (abs INR)
  OCF per year:         FY2024  171B, FY2025  176B, FY2026  185B
  Capex per year:       FY2024 -36B,  FY2025 -23B,  FY2026 -22B
  FCF per year:         OCF + capex
  Shares:               12,529,468,231  (≈ 12.53B)
  Derived EPS/share:    FY2024 ≈ 15.96, FY2025 ≈ 16.76, FY2026 ≈ 17.56
  3yr avg derived EPS:  ≈ 16.76
  3yr avg FCF/share:    ≈ 12.04
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from analytics.financial_quality.financial_metrics_model import (
    FreeCashFlowMetrics, CompanyFinancialMetrics,
)
from analytics.valuation.valuation_models import (
    ValuationInput, InputItem, InputType, ValuationConfidence, CompanyType,
)
from analytics.agent.renderer import render_followup
from analytics.decision.decision_models import (
    InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

SHARES = 12_529_468_231.0  # absolute units

# Annual OCF / capex / net income in absolute INR
OCF   = {2024: 171_788_600_000.0, 2025: 176_270_400_000.0, 2026: 184_643_100_000.0}
CAPEX = {2024: -35_625_300_000.0, 2025: -22_787_000_000.0, 2026: -21_828_900_000.0}
NI    = {2024: 200_000_000_000.0, 2025: 210_000_000_000.0, 2026: 220_000_000_000.0}
FCF   = {yr: OCF[yr] + CAPEX[yr] for yr in OCF}

AVG_FCF_PS   = sum(FCF.values()) / 3 / SHARES    # ≈ 12.04
AVG_NI_EPS   = sum(NI.values()) / 3 / SHARES     # ≈ 16.76 (derived EPS)
TTM_EPS      = 15.83  # as returned by yfinance trailingEps


def _make_fcf_metrics(**overrides) -> FreeCashFlowMetrics:
    kwargs = dict(
        annual_fcf=FCF,
        annual_capex=CAPEX,
        annual_net_income=NI,
        annual_ocf=OCF,
    )
    kwargs.update(overrides)
    return FreeCashFlowMetrics(**kwargs)


def _make_valuation_input(
    *,
    eps_history: dict | None = None,
    ttm_eps: float | None = TTM_EPS,
    shares_mm: float = SHARES / 1_000_000,
) -> ValuationInput:
    vi = ValuationInput(
        ticker="ITC.NS",
        company_name="ITC Ltd",
        company_type=CompanyType.INDUSTRIAL,
        currency="INR",
        valuation_date="2026-08-09",
    )
    vi.shares_outstanding = InputItem(
        name="shares_outstanding", value=shares_mm,
        source="test", period="test", retrieval_date="2026-08-09",
        input_type=InputType.REPORTED,
    )
    if ttm_eps is not None:
        vi.eps_ttm = InputItem(
            name="eps_ttm", value=ttm_eps,
            source="yfinance (trailingEps)", period="TTM",
            retrieval_date="2026-08-09", input_type=InputType.REPORTED,
        )
    if eps_history is not None:
        vi.eps_history = eps_history
    return vi


def _make_ida(
    *,
    eps_note: str = "3-year average of derived EPS",
    fcf_note: str = "3-year average FCF / shares outstanding.",
    fcf_ps: float | None = AVG_FCF_PS,
    eps_val: float | None = AVG_NI_EPS,
    with_breakdown: bool = True,
) -> InvestmentDecisionAssessment:
    breakdown = []
    if with_breakdown:
        for yr in sorted(OCF.keys(), reverse=True):
            breakdown.append({
                "year": yr,
                "ocf": OCF[yr],
                "capex": CAPEX[yr],
                "fcf": FCF[yr],
            })
    return InvestmentDecisionAssessment(
        ticker="ITC.NS",
        company_name="ITC Ltd",
        analysis_date="2026-08-09",
        action=DecisionAction.WATCH,
        decision_confidence=DecisionConfidence.MEDIUM,
        qualitative_investment_view="Stable FCF generator.",
        business_thesis="Steady compounder.",
        current_price=279.0,
        price_currency="INR",
        price_date="2026-08-09",
        valuation_conclusion="P/FCF above midpoint.",
        fcf_per_share_used=fcf_ps,
        fcf_normalization_note=fcf_note,
        eps_used_in_valuation=eps_val,
        eps_normalization_note=eps_note,
        fcf_annual_breakdown=breakdown,
        fcf_shares_outstanding=SHARES if with_breakdown else None,
    )


def _ask(question: str, **kw) -> str:
    return render_followup(question, _make_ida(**kw))


# ===========================================================================
# A — annual_ocf field exists on FreeCashFlowMetrics
# ===========================================================================

class TestA_AnnualOcfPersistence:

    def test_field_exists_on_model(self):
        fcf = FreeCashFlowMetrics()
        assert hasattr(fcf, "annual_ocf"), "annual_ocf field missing from FreeCashFlowMetrics"

    def test_field_default_is_empty_dict(self):
        fcf = FreeCashFlowMetrics()
        assert fcf.annual_ocf == {}

    def test_field_is_populated_when_set(self):
        fcf = _make_fcf_metrics()
        assert fcf.annual_ocf == OCF
        assert fcf.annual_ocf[2026] == OCF[2026]

    def test_annual_ocf_independent_of_annual_fcf(self):
        fcf = _make_fcf_metrics()
        # OCF != FCF because FCF = OCF + capex
        for yr in OCF:
            assert fcf.annual_ocf[yr] != fcf.annual_fcf[yr]

    def test_normalizer_populates_annual_ocf(self):
        """
        Verify normalizer.normalize() stores op_cf_series in annual_ocf.
        Uses synthetic financials so no network required.
        """
        from data.ingestion.normalizer import normalize

        info = {
            "_fetch_success": True,
            "_fetched_at": "2026-01-01T00:00:00",
            "longName": "Test Co",
            "currency": "INR",
        }
        financials = {
            "_fetch_success": True,
            "income_stmt": {
                "Net Income": {2024: 200e9, 2025: 210e9, 2026: 220e9},
            },
            "balance_sheet": {},
            "cash_flow": {
                "Total Cash From Operating Activities": {
                    2024: 171e9, 2025: 176e9, 2026: 185e9,
                },
                "Capital Expenditures": {
                    2024: -36e9, 2025: -23e9, 2026: -22e9,
                },
            },
        }
        m = normalize("TEST.NS", info, financials)
        assert hasattr(m.free_cash_flow, "annual_ocf"), "annual_ocf not set on result"
        assert 2024 in m.free_cash_flow.annual_ocf
        assert m.free_cash_flow.annual_ocf[2024] == pytest.approx(171e9, rel=1e-3)
        assert m.free_cash_flow.annual_ocf[2026] == pytest.approx(185e9, rel=1e-3)

    def test_normalizer_annual_ocf_matches_fcf_plus_capex(self):
        """OCF stored directly must equal FCF + |capex| (mathematical identity)."""
        from data.ingestion.normalizer import normalize

        info = {
            "_fetch_success": True,
            "_fetched_at": "2026-01-01T00:00:00",
            "longName": "Test Co",
            "currency": "INR",
        }
        ocf_raw  = {2024: 170e9, 2025: 175e9, 2026: 183e9}
        capex_raw = {2024: -35e9, 2025: -22e9, 2026: -21e9}
        financials = {
            "_fetch_success": True,
            "income_stmt": {"Net Income": {2024: 190e9, 2025: 200e9, 2026: 210e9}},
            "balance_sheet": {},
            "cash_flow": {
                "Total Cash From Operating Activities": ocf_raw,
                "Capital Expenditures": capex_raw,
            },
        }
        m = normalize("TEST.NS", info, financials)
        for yr in ocf_raw:
            stored_ocf = m.free_cash_flow.annual_ocf.get(yr)
            stored_fcf = m.free_cash_flow.annual_fcf.get(yr)
            stored_cap = m.free_cash_flow.annual_capex.get(yr)
            assert stored_ocf is not None
            assert stored_fcf == pytest.approx(stored_ocf + stored_cap, rel=1e-6)


# ===========================================================================
# B — eps_history populated in valuation_builder
# ===========================================================================

class TestB_EpsHistoryPopulation:

    def _make_load_result(self, *, ni_series=None, shares=SHARES, ttm_eps=TTM_EPS):
        """Build a minimal DataLoadResult-like object for valuation_builder tests."""
        # Use real FreeCashFlowMetrics so annual_net_income is accessible
        _ni = ni_series if ni_series is not None else NI
        fcf_m = FreeCashFlowMetrics(
            annual_net_income=_ni,
            annual_fcf={yr: OCF[yr] + CAPEX[yr] for yr in OCF},
            annual_capex=CAPEX,
            annual_ocf=OCF,
            fcf_current=sum(OCF[yr] + CAPEX[yr] for yr in OCF) / 3,
        )

        # Use a real CompanyFinancialMetrics so attribute access works safely
        m = CompanyFinancialMetrics(
            ticker="ITC.NS",
            company_name="ITC Ltd",
            currency="INR",
            data_as_of_date="2026-08-09",
        )
        m.free_cash_flow = fcf_m
        # revenue_growth stays default (empty RevenueGrowthMetrics) — no TypeError

        lr = MagicMock()
        lr.ticker = "ITC.NS"
        lr.company_name = "ITC Ltd"
        lr.price_currency = "INR"
        lr.price_date = "2026-08-09"
        lr.current_price = 279.0
        lr.metrics = m
        lr.supplemental = {
            "shares_outstanding": shares,
            "trailing_eps": ttm_eps,
        }
        lr.financial_quality = None
        return lr

    def test_eps_history_populated_when_ni_and_shares_available(self):
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_load_result()
        vi = build_valuation_input(lr)
        assert vi.eps_history, "eps_history should be populated"
        assert len(vi.eps_history) == 3
        # Check values are approximately net income / shares
        for yr_str, eps in vi.eps_history.items():
            yr = int(yr_str)
            expected = NI[yr] / SHARES
            assert eps == pytest.approx(expected, rel=1e-3), \
                f"Year {yr}: expected {expected:.4f}, got {eps:.4f}"

    def test_eps_history_keys_are_str_years(self):
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_load_result()
        vi = build_valuation_input(lr)
        for k in vi.eps_history:
            assert isinstance(k, str), f"eps_history key {k!r} should be str"
            int(k)  # must be parseable as year

    def test_eps_history_empty_when_no_net_income(self):
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_load_result(ni_series={})
        vi = build_valuation_input(lr)
        assert vi.eps_history == {}

    def test_eps_history_empty_when_no_shares(self):
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_load_result(shares=None)
        vi = build_valuation_input(lr)
        assert vi.eps_history == {}


# ===========================================================================
# C — normalized_eps() uses history instead of TTM when history exists
# ===========================================================================

class TestC_NormalizedEpsPreference:

    def test_uses_history_not_ttm_when_history_available(self):
        """When eps_history is populated, normalized_eps() must NOT fall back to TTM."""
        derived_hist = {str(yr): NI[yr] / SHARES for yr in NI}
        vi = _make_valuation_input(eps_history=derived_hist)
        norm_eps = vi.normalized_eps()
        assert norm_eps is not None
        # Must be the average of the history, NOT the TTM value
        expected_avg = sum(NI[yr] / SHARES for yr in NI) / 3
        assert norm_eps == pytest.approx(expected_avg, rel=1e-3)
        # Specifically must NOT equal TTM
        assert norm_eps != pytest.approx(TTM_EPS, abs=0.01), \
            f"normalized_eps() returned TTM {TTM_EPS} instead of history avg {expected_avg:.4f}"

    def test_falls_back_to_ttm_when_history_empty(self):
        vi = _make_valuation_input(eps_history={})
        assert vi.normalized_eps() == pytest.approx(TTM_EPS, rel=1e-4)

    def test_falls_back_to_ttm_when_no_history_field(self):
        vi = _make_valuation_input()
        # eps_history not set — should return TTM
        assert vi.normalized_eps() == pytest.approx(TTM_EPS, rel=1e-4)

    def test_normalized_eps_higher_than_fcf_per_share(self):
        """Derived EPS (NI/shares) should exceed FCF/share (consistent with ITC data)."""
        derived_hist = {str(yr): NI[yr] / SHARES for yr in NI}
        vi = _make_valuation_input(eps_history=derived_hist)
        norm_eps = vi.normalized_eps()
        assert norm_eps > AVG_FCF_PS, \
            f"Derived EPS {norm_eps:.4f} should exceed FCF/share {AVG_FCF_PS:.4f}"


# ===========================================================================
# D — same-period EPS/FCF reconciliation display
# ===========================================================================

class TestD_SamePeriodReconciliation:

    def test_same_period_confirmed_when_both_are_averages(self):
        # Phase 9.9b: renderer requires parseable year lists for ✓ SAME-PERIOD BASIS.
        # Use the new note format that includes "years: FY2024, FY2025, FY2026".
        out = _ask(
            "Why is FCF/share lower than EPS specifically? Please reconcile by capex",
            eps_note=(
                "Normalized EPS: 3-year average of continuing-ops derived EPS "
                "(net income from continuing operations ÷ shares); "
                "years: FY2024, FY2025, FY2026"
            ),
            fcf_note="Source: Derived: 3-year average FCF (3yr avg FY2024–FY2026)",
        )
        assert "SAME-PERIOD" in out or "same-period" in out.lower(), (
            f"Expected SAME-PERIOD when year sets are identical.\nGot:\n{out}"
        )

    def test_same_period_shows_period_label(self):
        out = _ask(
            "Explain FCF gap using financial-statement data, capex, depreciation",
            eps_note=(
                "Normalized EPS: 3-year average of continuing-ops derived EPS "
                "(net income from continuing operations ÷ shares); "
                "years: FY2024, FY2025, FY2026"
            ),
            fcf_note="Source: Derived: 3-year average FCF (3yr avg FY2024–FY2026)",
        )
        # Should show a year reference in the basis note
        assert "2024" in out or "2026" in out or "3-year" in out.lower()

    def test_eps_normalization_note_surfaced(self):
        out = _ask(
            "FCF reconciliation — capex and depreciation analysis",
            eps_note="3-year average of derived EPS",
            fcf_note="3-year average FCF / shares outstanding.",
        )
        # eps_normalization_note should appear in output
        assert "3-year average" in out.lower() or "3yr" in out.lower()

    def test_fcf_normalization_note_still_surfaced(self):
        out = _ask(
            "FCF reconciliation — capex, D&A",
            fcf_note="Derived: 3-year average FCF",
        )
        assert "3-year average" in out.lower() or "3yr" in out.lower() or "derived" in out.lower()


# ===========================================================================
# E — period-mismatch warning when TTM EPS vs avg FCF
# ===========================================================================

class TestE_PeriodMismatchWarning:

    def test_mismatch_warning_when_eps_ttm_and_fcf_avg(self):
        out = _ask(
            "Reconcile FCF vs EPS — capex, depreciation, working capital",
            eps_note="Using TTM EPS (historical normalization not available)",
            fcf_note="3-year average FCF / shares outstanding.",
        )
        assert "PERIOD MISMATCH" in out or "period mismatch" in out.lower()

    def test_mismatch_warning_says_different_windows(self):
        out = _ask(
            "FCF reconciliation — capex, D&A, taxes",
            eps_note="Using TTM EPS",
            fcf_note="3yr avg to 2026",
        )
        lower = out.lower()
        assert "ttm" in lower or "trailing" in lower

    def test_no_mismatch_warning_when_both_are_same_period(self):
        out = _ask(
            "FCF reconciliation — capex, depreciation",
            eps_note="3-year average of derived EPS",
            fcf_note="3-year average FCF / shares outstanding.",
        )
        assert "PERIOD MISMATCH" not in out

    def test_mismatch_says_indicative_only(self):
        out = _ask(
            "FCF reconciliation — capex, D&A, taxes",
            eps_note="Using TTM EPS",
            fcf_note="3yr avg to 2026",
        )
        lower = out.lower()
        assert "indicative" in lower or "not a" in lower or "mismatch" in lower


# ===========================================================================
# F — explicit missing-component messaging (D&A, WC, tax)
# ===========================================================================

class TestF_MissingComponentMessaging:

    def test_cannot_reconcile_section_present(self):
        out = _ask("FCF reconciliation — capex, D&A, working capital, taxes")
        assert "CANNOT RECONCILE" in out

    def test_da_listed_as_not_extracted(self):
        out = _ask("FCF reconciliation — capex, D&A, depreciation")
        lower = out.lower()
        assert ("d&a" in lower or "depreciation" in lower) and (
            "not extracted" in lower or "not stored" in lower or "cannot" in lower
        )

    def test_working_capital_listed_as_not_extracted(self):
        out = _ask("FCF reconciliation — capex, working capital")
        lower = out.lower()
        assert "working" in lower and (
            "not extracted" in lower or "cannot" in lower or "not stored" in lower
        )

    def test_tax_listed_as_not_extracted(self):
        out = _ask("FCF reconciliation — capex, tax, depreciation")
        lower = out.lower()
        assert "tax" in lower and (
            "not extracted" in lower or "cannot" in lower or "not stored" in lower
        )

    def test_step1_labelled_as_total_only(self):
        """Step 1 (EPS → OCF) must be shown as a total — not decomposed."""
        out = _ask("FCF reconciliation — capex, D&A, taxes")
        lower = out.lower()
        # "individual sub-components" or "cannot be decomposed" signals must appear
        assert "sub-component" in lower or "individual" in lower or "cannot be decomposed" in lower


# ===========================================================================
# G — no-fabrication / no capex-exceeds-D&A assertion
# ===========================================================================

class TestG_NoFabrication:

    def test_no_da_per_share_invented(self):
        out = _ask("FCF reconciliation — D&A and capex from financial-statement data")
        assert "d&a per share" not in out.lower()
        assert "depreciation per share" not in out.lower()

    def test_no_wc_per_share_invented(self):
        out = _ask("FCF reconciliation — working capital and depreciation")
        assert "working capital per share" not in out.lower()

    def test_no_capex_alone_claim(self):
        out = _ask("FCF reconciliation — capex, D&A")
        lower = out.lower()
        assert "capex alone" not in lower
        assert "capex explains the" not in lower

    def test_no_capex_exceeds_da_claim(self):
        """Must NOT assert that capex exceeds D&A — D&A is not stored."""
        out = _ask("FCF reconciliation — capex, D&A, depreciation")
        lower = out.lower()
        # These specific phrasings would be fabrications
        assert "capex exceeds d&a" not in lower
        assert "capex exceeds depreciation" not in lower

    def test_source_footer_present(self):
        out = _ask("FCF reconciliation — capex, D&A")
        assert "No new financial data" in out

    def test_structural_section_labelled_as_general(self):
        out = _ask("FCF reconciliation — capex, depreciation")
        lower = out.lower()
        assert "general" in lower or "not company-specific" in lower or "not itc" in lower


# ===========================================================================
# H — non-regression
# ===========================================================================

class TestH_NonRegression:

    def test_routing_original_question_still_hits_reconciliation(self):
        out = render_followup(
            "Why is ITC's FCF/share lower than EPS specifically? Show me whether capex, "
            "working capital, depreciation/amortization, taxes, or other items explain the "
            "₹3.79/share difference using the available financial-statement data.",
            _make_ida()
        )
        assert "DATA QUALITY" not in out
        assert "RECONCILIATION" in out.upper() or "observed" in out.lower()

    def test_data_freshness_still_routes_to_data_quality(self):
        out = render_followup("How fresh is the underlying data?", _make_ida())
        lower = out.lower()
        assert "freshness" in lower or "stale" in lower or "data" in lower

    def test_pfcf_question_unaffected(self):
        out = render_followup("How does P/FCF work for ITC?", _make_ida())
        assert "p/fcf" in out.lower() or "P/FCF" in out

    def test_risk_question_unaffected(self):
        out = render_followup("What are the biggest risks?", _make_ida())
        assert "risk" in out.lower()

    def test_fcf_metrics_model_to_dict_still_works(self):
        """FreeCashFlowMetrics.to_dict() must include the new field."""
        fcf = _make_fcf_metrics()
        d = fcf.to_dict()
        assert "annual_ocf" in d
        assert d["annual_ocf"] == OCF

    def test_ida_eps_normalization_note_stored(self):
        ida = _make_ida(eps_note="3-year average of derived EPS")
        assert ida.eps_normalization_note == "3-year average of derived EPS"

    def test_ida_to_dict_includes_eps_normalization_note(self):
        ida = _make_ida(eps_note="3-year average of derived EPS")
        d = ida.to_dict()
        assert "eps_normalization_note" in d
        assert d["eps_normalization_note"] == "3-year average of derived EPS"

    def test_ida_default_eps_normalization_note_is_empty_string(self):
        ida = InvestmentDecisionAssessment(
            ticker="TEST",
            company_name="Test Co",
            analysis_date="2026-08-09",
            action=DecisionAction.WATCH,
            decision_confidence=DecisionConfidence.MEDIUM,
            qualitative_investment_view="test",
            business_thesis="test",
        )
        assert ida.eps_normalization_note == ""


# ===========================================================================
# Phase 9.9b — Regression tests
# ===========================================================================
# Tests A–F covering:
#   A. Continuing-ops NI preferred over total NI when both present
#   B. Total NI used as fallback when continuing-ops absent
#   C. Legitimate zero continuing-ops NI accepted (not treated as missing)
#   D. eps_history uses same fiscal-year set as FCF normalization
#   E. Renderer year-set comparison: same-period and mismatch cases
#   F. Synthetic fixtures without discontinued ops retain expected behaviour

# Constants for Phase 9.9b tests
# Continuing-ops NI: FY2025 is normal (≈200B), unlike total NI which spikes to 347B
CONT_OPS_NI = {2024: 198_982_000_000.0, 2025: 197_306_000_000.0, 2026: 206_895_000_000.0}
TOTAL_NI_WITH_DISC = {
    2024: 204_588_000_000.0,
    2025: 347_466_000_000.0,   # includes ₹150B discontinued-ops gain
    2026: 206_895_000_000.0,
}


class TestA_ContinuingOpsNIPreferred:
    """
    A. When annual_net_income contains continuing-ops values (loaded by
       Phase 9.9b normalizer), derived EPS must use those values, NOT the
       total-NI values that include discontinued-operations gains.
    """

    def _make_load_result_with_cont_ops(self, ni_series: dict):
        """Build a DataLoadResult-like mock with the given NI series."""
        from analytics.financial_quality.financial_metrics_model import CompanyFinancialMetrics
        fcf_m = FreeCashFlowMetrics(
            annual_net_income=ni_series,
            annual_fcf=FCF,
            annual_capex=CAPEX,
            annual_ocf=OCF,
        )
        m = CompanyFinancialMetrics(
            ticker="ITC.NS", company_name="ITC Ltd",
            currency="INR", data_as_of_date="2026-08-09",
        )
        m.free_cash_flow = fcf_m
        lr = MagicMock()
        lr.ticker = "ITC.NS"
        lr.company_name = "ITC Ltd"
        lr.price_currency = "INR"
        lr.price_date = "2026-08-09"
        lr.current_price = 282.65
        lr.metrics = m
        lr.supplemental = {
            "shares_outstanding": SHARES,   # absolute count; builder divides by 1e6 internally
            "trailing_eps": TTM_EPS,
        }
        lr.financial_quality = None
        return lr

    def test_continuing_ops_eps_lower_than_total_ni_eps_when_discontinuity_present(self):
        """
        With total NI (including FY2025 ₹347B), normalized EPS ≈ ₹20.19.
        With continuing-ops NI (FY2025 ₹197B), normalized EPS ≈ ₹16.05.
        The continuing-ops figure must be lower.
        """
        from analytics.agent.valuation_builder import build_valuation_input
        lr_total = self._make_load_result_with_cont_ops(TOTAL_NI_WITH_DISC)
        lr_cont  = self._make_load_result_with_cont_ops(CONT_OPS_NI)
        vi_total = build_valuation_input(lr_total)
        vi_cont  = build_valuation_input(lr_cont)
        eps_total = vi_total.normalized_eps()
        eps_cont  = vi_cont.normalized_eps()
        assert eps_cont is not None and eps_total is not None
        assert eps_cont < eps_total, (
            f"Continuing-ops EPS ({eps_cont:.4f}) should be lower than "
            f"total-NI EPS ({eps_total:.4f}) when FY2025 has a large discontinued gain."
        )

    def test_continuing_ops_fy2025_eps_normal_not_spiked(self):
        """
        With continuing-ops NI, FY2025 derived EPS ≈ ₹15.75, not ₹27.73.
        The spike from discontinued operations must not appear in eps_history.
        """
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_load_result_with_cont_ops(CONT_OPS_NI)
        vi = build_valuation_input(lr)
        fy2025_eps = vi.eps_history.get("2025")
        assert fy2025_eps is not None, "FY2025 should be in eps_history"
        # Continuing-ops FY2025: ₹197.306B / 12.529B shares ≈ ₹15.75
        assert fy2025_eps < 20.0, (
            f"FY2025 EPS ({fy2025_eps:.4f}) should be ≈₹15.75 (continuing-ops), "
            f"not ≈₹27.73 (total NI incl. discontinued-ops gain)."
        )

    def test_eps_history_values_match_cont_ops_ni_divided_by_shares(self):
        """Exact value check: eps_history[year] == cont_ops_ni[year] / shares."""
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_load_result_with_cont_ops(CONT_OPS_NI)
        vi = build_valuation_input(lr)
        for yr_str, eps in vi.eps_history.items():
            yr = int(yr_str)
            if yr in CONT_OPS_NI:
                expected = round(CONT_OPS_NI[yr] / SHARES, 4)
                assert abs(eps - expected) < 0.001, (
                    f"FY{yr}: expected {expected:.4f} (cont-ops), got {eps:.4f}"
                )


class TestB_TotalNIFallback:
    """
    B. When the continuing-ops NI series is absent, valuation_builder must
       fall back to total Net Income without error.
    """

    def _make_lr(self, ni_series: dict):
        from analytics.financial_quality.financial_metrics_model import CompanyFinancialMetrics
        fcf_m = FreeCashFlowMetrics(
            annual_net_income=ni_series,
            annual_fcf=FCF,
            annual_capex=CAPEX,
            annual_ocf=OCF,
        )
        m = CompanyFinancialMetrics(ticker="TST", company_name="Test Co",
                                    currency="CAD", data_as_of_date="2026-01-01")
        m.free_cash_flow = fcf_m
        lr = MagicMock()
        lr.ticker = "TST"
        lr.company_name = "Test Co"
        lr.price_currency = "CAD"
        lr.price_date = "2026-01-01"
        lr.current_price = 100.0
        lr.metrics = m
        lr.supplemental = {"shares_outstanding": SHARES, "trailing_eps": TTM_EPS}
        lr.financial_quality = None
        return lr

    def test_fallback_to_total_ni_produces_eps_history(self):
        """With total-NI fixture (no cont-ops series in normalizer), eps_history is still populated."""
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_lr(NI)
        vi = build_valuation_input(lr)
        # eps_history should be populated from total NI as fallback
        assert vi.eps_history, "eps_history must be populated from total NI when cont-ops absent"
        assert len(vi.eps_history) == 3

    def test_fallback_eps_values_match_total_ni(self):
        """Fallback EPS values equal total NI / shares."""
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_lr(NI)
        vi = build_valuation_input(lr)
        for yr_str, eps in vi.eps_history.items():
            yr = int(yr_str)
            if yr in NI:
                expected = round(NI[yr] / SHARES, 4)
                assert abs(eps - expected) < 0.001, (
                    f"FY{yr}: expected {expected:.4f} (total NI fallback), got {eps:.4f}"
                )

    def test_fallback_no_exception_raised(self):
        """No exception when annual_net_income is populated from total NI."""
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_lr(NI)
        try:
            vi = build_valuation_input(lr)
        except Exception as exc:
            pytest.fail(f"build_valuation_input raised {type(exc).__name__}: {exc}")


class TestC_LegitimateZeroNI:
    """
    C. A year with genuine zero continuing-operations NI must not be
       treated as 'missing' — it is a valid (bad) result: EPS = 0.0.
    """

    def test_zero_ni_year_accepted_not_skipped(self):
        """Year with NI=0 produces EPS=0.0 in eps_history, not omitted."""
        from analytics.agent.valuation_builder import build_valuation_input
        from analytics.financial_quality.financial_metrics_model import CompanyFinancialMetrics
        ni_with_zero = {2024: 200_000_000_000.0, 2025: 0.0, 2026: 220_000_000_000.0}
        fcf_m = FreeCashFlowMetrics(
            annual_net_income=ni_with_zero,
            annual_fcf=FCF,
            annual_capex=CAPEX,
            annual_ocf=OCF,
        )
        m = CompanyFinancialMetrics(ticker="ZNI", company_name="Zero NI Co",
                                    currency="INR", data_as_of_date="2026-01-01")
        m.free_cash_flow = fcf_m
        lr = MagicMock()
        lr.ticker = "ZNI"
        lr.company_name = "Zero NI Co"
        lr.price_currency = "INR"
        lr.price_date = "2026-01-01"
        lr.current_price = 50.0
        lr.metrics = m
        lr.supplemental = {"shares_outstanding": SHARES, "trailing_eps": 0.0}
        lr.financial_quality = None
        vi = build_valuation_input(lr)
        # FY2025 should be present with EPS=0.0
        assert "2025" in vi.eps_history, "FY2025 with NI=0 should be in eps_history, not omitted"
        assert vi.eps_history["2025"] == pytest.approx(0.0, abs=1e-6)

    def test_zero_ni_year_included_in_average(self):
        """Zero NI year depresses normalized_eps (not silently excluded)."""
        from analytics.agent.valuation_builder import build_valuation_input
        from analytics.financial_quality.financial_metrics_model import CompanyFinancialMetrics
        ni_with_zero = {2024: 200_000_000_000.0, 2025: 0.0, 2026: 220_000_000_000.0}
        fcf_m = FreeCashFlowMetrics(
            annual_net_income=ni_with_zero,
            annual_fcf=FCF,
            annual_capex=CAPEX,
            annual_ocf=OCF,
        )
        m = CompanyFinancialMetrics(ticker="ZNI", company_name="Zero NI Co",
                                    currency="INR", data_as_of_date="2026-01-01")
        m.free_cash_flow = fcf_m
        lr = MagicMock()
        lr.ticker = "ZNI"
        lr.company_name = "Zero NI Co"
        lr.price_currency = "INR"
        lr.price_date = "2026-01-01"
        lr.current_price = 50.0
        lr.metrics = m
        lr.supplemental = {"shares_outstanding": SHARES, "trailing_eps": 5.0}
        lr.financial_quality = None
        vi = build_valuation_input(lr)
        norm = vi.normalized_eps()
        # (200B + 0 + 220B) / 3 / shares ≈ 11.17, well below the non-zero avg ≈ 16.76
        assert norm is not None
        assert norm < AVG_NI_EPS * 0.8, (
            f"normalized_eps() ({norm:.4f}) should be depressed by FY2025 zero; "
            f"expected < {AVG_NI_EPS*0.8:.4f}"
        )


class TestD_CommonYearWindowAlignment:
    """
    D. eps_history must use exactly the same fiscal years as fcf_normalized.
    """

    def _build_vi(self, ni_years: list, fcf_years: list):
        """
        Build a ValuationInput via build_valuation_input using the given
        year sets for NI and FCF respectively.
        """
        from analytics.agent.valuation_builder import build_valuation_input
        from analytics.financial_quality.financial_metrics_model import CompanyFinancialMetrics

        base_ocf   = {2023: 160e9, 2024: 171e9, 2025: 176e9, 2026: 185e9}
        base_capex = {2023: -30e9, 2024: -36e9, 2025: -23e9, 2026: -22e9}
        base_ni    = {2023: 192e9, 2024: 200e9, 2025: 210e9, 2026: 220e9}
        ni_series  = {yr: base_ni[yr]    for yr in ni_years  if yr in base_ni}
        ocf_sel    = {yr: base_ocf[yr]   for yr in fcf_years if yr in base_ocf}
        cap_sel    = {yr: base_capex[yr] for yr in fcf_years if yr in base_capex}
        fcf_series = {yr: ocf_sel[yr] + cap_sel.get(yr, 0) for yr in ocf_sel}

        fcf_m = FreeCashFlowMetrics(
            annual_net_income=ni_series,
            annual_fcf=fcf_series,
            annual_capex=cap_sel,
            annual_ocf=ocf_sel,
            fcf_current=list(fcf_series.values())[-1] if fcf_series else None,
        )
        m = CompanyFinancialMetrics(ticker="TST", company_name="Test",
                                    currency="INR", data_as_of_date="2026-01-01")
        m.free_cash_flow = fcf_m
        lr = MagicMock()
        lr.ticker = "TST"
        lr.company_name = "Test"
        lr.price_currency = "INR"
        lr.price_date = "2026-01-01"
        lr.current_price = 100.0
        lr.metrics = m
        lr.supplemental = {"shares_outstanding": SHARES, "trailing_eps": 15.0}
        lr.financial_quality = None
        return build_valuation_input(lr)

    def test_eps_history_years_equal_fcf_norm_years_when_ni_has_extra_year(self):
        """
        NI has 4 years (FY2023–2026), FCF has 3 years (FY2024–2026).
        eps_history must use only FY2024–2026 (the common 3yr window),
        NOT include FY2023 merely because it exists in NI.
        """
        vi = self._build_vi(ni_years=[2023, 2024, 2025, 2026],
                            fcf_years=[2024, 2025, 2026])
        eps_years = sorted(int(y) for y in vi.eps_history.keys())
        assert eps_years == [2024, 2025, 2026], (
            f"eps_history years {eps_years} should be [2024, 2025, 2026] "
            f"(common window with FCF), not include FY2023"
        )

    def test_eps_history_years_match_when_both_have_same_three_years(self):
        """NI and FCF both cover FY2024–2026: eps_history must be exactly those 3 years."""
        vi = self._build_vi(ni_years=[2024, 2025, 2026],
                            fcf_years=[2024, 2025, 2026])
        eps_years = sorted(int(y) for y in vi.eps_history.keys())
        assert eps_years == [2024, 2025, 2026]

    def test_eps_history_empty_when_no_common_years(self):
        """NI covers FY2023 only, FCF covers FY2024–2026: no common years → eps_history empty."""
        vi = self._build_vi(ni_years=[2023],
                            fcf_years=[2024, 2025, 2026])
        assert vi.eps_history == {}, (
            "eps_history should be empty when NI and FCF share no common fiscal years"
        )

    def test_eps_history_capped_at_fcf_norm_years(self):
        """Even with 5 NI years and 3 FCF years, eps_history is capped at 3."""
        vi = self._build_vi(ni_years=[2023, 2024, 2025, 2026],
                            fcf_years=[2024, 2025, 2026])
        assert len(vi.eps_history) <= 3, (
            f"eps_history has {len(vi.eps_history)} years; must not exceed FCF_NORM_YEARS=3"
        )

    def test_fcf_normalized_period_string_contains_year_range(self):
        """fcf_normalized.period must contain the FCF year range for renderer parsing."""
        vi = self._build_vi(ni_years=[2024, 2025, 2026],
                            fcf_years=[2024, 2025, 2026])
        assert vi.fcf_normalized is not None, "fcf_normalized should be populated"
        period = vi.fcf_normalized.period or ""
        # Phase 9.9b format: "3yr avg FY2024–FY2026"
        import re
        assert re.search(r"FY\d{4}", period), (
            f"fcf_normalized.period {period!r} should contain a FY year reference for renderer"
        )


class TestE_RendererYearSetComparison:
    """
    E. _answer_fcf_reconciliation must compare actual year sets, not text keywords.
    """

    def _make_ida_with_notes(self, eps_note: str, fcf_note: str,
                              eps_val: float = 16.05, fcf_ps: float = 12.04):
        return InvestmentDecisionAssessment(
            ticker="ITC.NS",
            company_name="ITC Ltd",
            analysis_date="2026-08-09",
            action=DecisionAction.WAIT_INSUFFICIENT_EVIDENCE,
            decision_confidence=DecisionConfidence.MEDIUM,
            qualitative_investment_view="test",
            business_thesis="test",
            eps_used_in_valuation=eps_val,
            eps_normalization_note=eps_note,
            fcf_per_share_used=fcf_ps,
            fcf_normalization_note=fcf_note,
        )

    def _render_reconciliation(self, ida: InvestmentDecisionAssessment) -> str:
        from analytics.decision.decision_models import (
            DecisionAction, DecisionConfidence
        )
        class MockSession:
            last_ticker = "ITC.NS"
            last_assessment = ida
        agent = MagicMock()
        agent._session = MockSession()
        return render_followup("Why is FCF lower than EPS? Explain the difference.", ida)

    def test_same_period_when_year_sets_identical(self):
        """When EPS and FCF both cover FY2024–FY2026, ✓ SAME-PERIOD BASIS must appear."""
        eps_note = (
            "Normalized EPS: 3-year average of continuing-ops derived EPS "
            "(net income from continuing operations ÷ shares); "
            "years: FY2024, FY2025, FY2026"
        )
        fcf_note = "Source: Derived: 3-year average FCF (3yr avg FY2024–FY2026)"
        ida = self._make_ida_with_notes(eps_note, fcf_note)
        resp = render_followup("Why is FCF lower than EPS? Explain the difference.", ida)
        assert "SAME-PERIOD" in resp, (
            f"Expected '✓ SAME-PERIOD BASIS' when year sets are identical.\nGot:\n{resp}"
        )
        assert "MISMATCH" not in resp

    def test_period_mismatch_when_eps_covers_extra_year(self):
        """When EPS uses FY2023–2026 (4yr) and FCF uses FY2024–2026 (3yr), ⚠ PERIOD MISMATCH."""
        eps_note = (
            "Normalized EPS: 4-year average of continuing-ops derived EPS "
            "(net income from continuing operations ÷ shares); "
            "years: FY2023, FY2024, FY2025, FY2026"
        )
        fcf_note = "Source: Derived: 3-year average FCF (3yr avg FY2024–FY2026)"
        ida = self._make_ida_with_notes(eps_note, fcf_note)
        resp = render_followup("Why is FCF lower than EPS? Explain the difference.", ida)
        assert "MISMATCH" in resp, (
            f"Expected '⚠ PERIOD MISMATCH' when EPS covers FY2023 but FCF doesn't.\nGot:\n{resp}"
        )
        assert "SAME-PERIOD" not in resp

    def test_ttm_eps_triggers_mismatch_not_same_period(self):
        """TTM EPS vs multi-year FCF must show ⚠ PERIOD MISMATCH, not ✓ SAME-PERIOD."""
        eps_note = "Using TTM EPS (no annual history available)"
        fcf_note = "Source: Derived: 3-year average FCF (3yr avg FY2024–FY2026)"
        ida = self._make_ida_with_notes(eps_note, fcf_note)
        resp = render_followup("Why is FCF lower than EPS? Explain the difference.", ida)
        assert "MISMATCH" in resp
        assert "SAME-PERIOD" not in resp

    def test_no_false_same_period_from_keyword_only(self):
        """
        Old bug: 'ttm' absent from both notes → false ✓ SAME-PERIOD BASIS.
        Phase 9.9b fix: must parse year sets, not rely on keyword absence.
        An EPS note with 'average' but covering FY2023–2026 vs FCF covering
        FY2024–2026 must NOT claim same-period.
        """
        # Simulate the old Phase 9.9 scenario: EPS note says "4-year average"
        # but has no year list (pre-Phase-9.9b format), FCF covers 3yr.
        # Without year-list parsing the renderer falls back to the generic note.
        eps_note = "Normalized EPS: 4-year average of reported EPS"  # no year list
        fcf_note = "Source: Derived: 3-year average FCF (3yr avg FY2024–FY2026)"
        ida = self._make_ida_with_notes(eps_note, fcf_note)
        resp = render_followup("Why is FCF lower than EPS? Explain the difference.", ida)
        # Without parseable year lists, it must NOT assert SAME-PERIOD
        # (may show generic note or mismatch, but must NOT say ✓ SAME-PERIOD BASIS)
        assert "✓ SAME-PERIOD BASIS" not in resp, (
            f"Must not claim ✓ SAME-PERIOD BASIS when year sets cannot be verified.\nGot:\n{resp}"
        )


class TestF_SyntheticFixtureNonRegression:
    """
    F. Synthetic fixtures that have NO discontinued operations (NI same as cont-ops)
       must produce the same eps_history and normalized_eps as before Phase 9.9b.
    """

    def _make_lr(self, ni_series: dict = None):
        from analytics.financial_quality.financial_metrics_model import CompanyFinancialMetrics
        ni = ni_series if ni_series is not None else NI
        fcf_m = FreeCashFlowMetrics(
            annual_net_income=ni,
            annual_fcf=FCF,
            annual_capex=CAPEX,
            annual_ocf=OCF,
        )
        m = CompanyFinancialMetrics(ticker="ITC.NS", company_name="ITC Ltd",
                                    currency="INR", data_as_of_date="2026-08-09")
        m.free_cash_flow = fcf_m
        lr = MagicMock()
        lr.ticker = "ITC.NS"
        lr.company_name = "ITC Ltd"
        lr.price_currency = "INR"
        lr.price_date = "2026-08-09"
        lr.current_price = 282.65
        lr.metrics = m
        lr.supplemental = {
            "shares_outstanding": SHARES,   # absolute count; builder divides by 1e6 internally
            "trailing_eps": TTM_EPS,
        }
        lr.financial_quality = None
        return lr

    def test_synthetic_ni_eps_history_length_still_three(self):
        """Synthetic 3-year NI fixture still produces 3-year eps_history."""
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_lr()
        vi = build_valuation_input(lr)
        assert len(vi.eps_history) == 3

    def test_synthetic_ni_eps_values_unchanged(self):
        """eps_history values for synthetic fixture (no discontinuity) unchanged from Phase 9.9."""
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_lr()
        vi = build_valuation_input(lr)
        for yr_str, eps in vi.eps_history.items():
            yr = int(yr_str)
            expected = round(NI[yr] / SHARES, 4)
            assert abs(eps - expected) < 0.001, (
                f"FY{yr}: expected {expected:.4f}, got {eps:.4f}"
            )

    def test_synthetic_normalized_eps_unchanged(self):
        """normalized_eps() for synthetic fixture matches 3yr NI average."""
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_lr()
        vi = build_valuation_input(lr)
        expected_avg = sum(NI.values()) / len(NI) / SHARES
        norm = vi.normalized_eps()
        assert norm == pytest.approx(expected_avg, rel=1e-3), (
            f"normalized_eps() {norm:.4f} should equal 3yr avg {expected_avg:.4f}"
        )

    def test_eps_history_keys_are_str_years(self):
        """eps_history keys remain str year-strings after Phase 9.9b."""
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_lr()
        vi = build_valuation_input(lr)
        for k in vi.eps_history:
            assert isinstance(k, str)
            int(k)  # must parse as integer year

    def test_normalized_eps_higher_than_fcf_per_share(self):
        """EPS > FCF/share for synthetic fixture (capex > 0 always)."""
        from analytics.agent.valuation_builder import build_valuation_input
        lr = self._make_lr()
        vi = build_valuation_input(lr)
        norm_eps = vi.normalized_eps()
        assert norm_eps is not None
        assert norm_eps > AVG_FCF_PS, (
            f"normalized_eps() {norm_eps:.4f} should exceed FCF/share {AVG_FCF_PS:.4f}"
        )
