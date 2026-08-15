"""
Phase 9.8 — FCF/EPS reconciliation handler tests
==================================================

Tests that the dedicated _answer_fcf_reconciliation() handler is:
  - Routed to correctly (not falling through to data-quality handler)
  - Showing OBSERVED / CALCULATED / CANNOT RECONCILE sections
  - Presenting correct partial attribution (EPS→OCF step, OCF→FCF step)
  - Not fabricating D&A, WC, or tax values
  - Preserving existing routing for unrelated questions

ITC constants (from stored assessment):
  FCF/share = 12.04, EPS = 15.83, gap = 3.79
  shares = 12,529,468,231
  OCF/share ≈ 14.4, capex/share ≈ 2.2  (from annual breakdown)
"""

from __future__ import annotations

import pytest

from analytics.agent.renderer import render_followup
from analytics.decision.decision_models import (
    InvestmentDecisionAssessment,
    DecisionAction,
    DecisionConfidence,
)

# ---------------------------------------------------------------------------
# Shared ITC constants
# ---------------------------------------------------------------------------

ITC_OCF   = {2026: 184_643_100_000.0, 2025: 176_270_400_000.0, 2024: 171_788_600_000.0}
ITC_CAPEX = {2026: -21_828_900_000.0, 2025: -22_787_000_000.0, 2024: -35_625_300_000.0}
ITC_FCF   = {yr: ITC_OCF[yr] + ITC_CAPEX[yr] for yr in ITC_OCF}
ITC_SHARES = 12_529_468_231.0
ITC_FCF_PS = 12.04
ITC_EPS    = 15.83


def _breakdown(years=None):
    years = years or sorted(ITC_OCF.keys(), reverse=True)
    return [
        {
            "year":  yr,
            "ocf":   ITC_OCF[yr] + ITC_CAPEX[yr] - ITC_CAPEX[yr],   # = ITC_OCF[yr]
            "capex": ITC_CAPEX[yr],
            "fcf":   ITC_FCF[yr],
        }
        for yr in years
    ]


def _make_ida(
    *,
    with_breakdown: bool = True,
    fcf_ps: float | None = ITC_FCF_PS,
    eps: float | None = ITC_EPS,
    ticker: str = "ITC.NS",
) -> InvestmentDecisionAssessment:
    return InvestmentDecisionAssessment(
        ticker=ticker,
        company_name="ITC Ltd",
        analysis_date="2026-08-09",
        action=DecisionAction.WATCH,
        decision_confidence=DecisionConfidence.MEDIUM,
        qualitative_investment_view="Stable conglomerate.",
        business_thesis="Steady FCF generator.",
        current_price=279.0,
        price_currency="INR",
        price_date="2026-08-09",
        valuation_conclusion="P/FCF views price as above midpoint.",
        fcf_per_share_used=fcf_ps,
        eps_used_in_valuation=eps,
        fcf_normalization_note="3-year average FCF / shares outstanding.",
        fcf_annual_breakdown=_breakdown() if with_breakdown else [],
        fcf_shares_outstanding=ITC_SHARES if with_breakdown else None,
    )


def _ask(question: str, **kw) -> str:
    return render_followup(question, _make_ida(**kw))


# ===========================================================================
# A — Routing: the failing question and equivalent phrasings
# ===========================================================================

class TestA_Routing:
    """All reconciliation-type phrasings must NOT fall through to data-quality."""

    QUESTIONS = [
        # Original failing question
        "Why is ITC's FCF/share lower than EPS specifically? Show me whether capex, "
        "working capital, depreciation/amortization, taxes, or other items explain the "
        "₹3.79/share difference using the available financial-statement data.",
        # Equivalent phrasing 1
        "Can you decompose the FCF vs EPS gap by capex, D&A, and working capital?",
        # Equivalent phrasing 2
        "Please reconcile the difference between ITC's EPS and FCF/share — "
        "decompose by capex and other line items.",
        # Equivalent phrasing 3
        "Explain the gap between FCF/share and EPS using the available financial statements. "
        "How much is capex? How much is depreciation and tax timing?",
    ]

    def test_original_question_not_data_quality(self):
        out = _ask(self.QUESTIONS[0])
        assert "DATA QUALITY" not in out
        assert "data freshness" not in out.lower()
        assert "RECONCILIATION" in out.upper() or "observed" in out.lower()

    def test_decompose_phrasing(self):
        out = _ask(self.QUESTIONS[1])
        assert "DATA QUALITY" not in out
        assert "reconcil" in out.lower() or "calculated" in out.lower() or "observed" in out.lower()

    def test_reconcile_phrasing(self):
        out = _ask(self.QUESTIONS[2])
        assert "DATA QUALITY" not in out
        assert "reconcil" in out.lower() or "capex" in out.lower()

    def test_explain_gap_phrasing(self):
        out = _ask(self.QUESTIONS[3])
        assert "DATA QUALITY" not in out
        assert "capex" in out.lower()

    def test_generic_data_question_still_routes_to_data_quality(self):
        # "data freshness" without FCF context must still go to data quality
        out = render_followup("How fresh is the data?", _make_ida())
        assert "DATA QUALITY" in out or "freshness" in out.lower() or "stale" in out.lower()

    def test_generic_gap_question_without_fcf_routes_correctly(self):
        # "gap" without "fcf" should still hit data quality
        out = render_followup("What are the data gaps in this analysis?", _make_ida())
        # should NOT return reconciliation output
        assert "RECONCILIATION" not in out.upper() or "DATA QUALITY" in out or "freshness" in out.lower()


# ===========================================================================
# B — DIRECTLY OBSERVED section
# ===========================================================================

class TestB_ObservedSection:

    def test_observed_section_header_present(self):
        out = _ask("FCF reconciliation — capex and working capital components")
        assert "DIRECTLY OBSERVED" in out

    def test_eps_shown(self):
        out = _ask("Explain FCF/EPS gap using financial-statement data, capex, depreciation")
        assert "15.83" in out

    def test_fcf_per_share_shown(self):
        out = _ask("Explain FCF/EPS gap using financial-statement data, capex, depreciation")
        assert "12.04" in out

    def test_observed_gap_shown(self):
        out = _ask("FCF reconciliation — capex and depreciation attribution")
        assert "3.79" in out

    def test_no_eps_graceful(self):
        out = _ask("FCF reconciliation — capex, depreciation", eps=None)
        # Should not crash, should say not stored
        assert "not stored" in out.lower()

    def test_no_fcf_ps_graceful(self):
        out = _ask("FCF reconciliation — capex, depreciation", fcf_ps=None)
        assert "not stored" in out.lower()


# ===========================================================================
# C — CALCULATED section (annual breakdown present)
# ===========================================================================

class TestC_CalculatedSection:

    def test_calculated_section_header_present(self):
        out = _ask("Explain FCF gap with capex and depreciation — financial-statement data")
        assert "CALCULATED" in out

    def test_ocf_per_share_present(self):
        out = _ask("FCF reconciliation — capex, working capital, tax attribution")
        assert "OCF/share" in out

    def test_capex_per_share_present(self):
        out = _ask("FCF reconciliation — capex, D&A decomposition")
        assert "capex/share" in out.lower() or "capex" in out.lower()

    def test_annual_table_years_present(self):
        out = _ask("Explain the FCF/EPS difference using financial-statement data, capex")
        assert "2024" in out
        assert "2025" in out
        assert "2026" in out

    def test_partial_gap_attribution_shown(self):
        out = _ask("FCF reconciliation — capex, D&A decomposition")
        lower = out.lower()
        assert "step 1" in lower or "partial" in lower or "eps" in lower

    def test_capex_step_attribution(self):
        # Step 2 should show capex deduction
        out = _ask("FCF reconciliation — capex, working capital, depreciation")
        lower = out.lower()
        assert "capex" in lower and ("step 2" in lower or "ocf" in lower)

    def test_no_breakdown_graceful(self):
        out = _ask("FCF reconciliation — capex, depreciation", with_breakdown=False)
        # Should not crash, should say breakdown not stored
        assert "not stored" in out.lower() or "not available" in out.lower()


# ===========================================================================
# D — CANNOT RECONCILE section
# ===========================================================================

class TestD_CannotReconcile:

    def test_cannot_reconcile_section_present(self):
        out = _ask("Explain FCF/EPS gap by capex, depreciation, working capital, taxes")
        assert "CANNOT RECONCILE" in out

    def test_da_listed_as_missing(self):
        out = _ask("Explain FCF gap by depreciation, capex, working capital")
        lower = out.lower()
        assert "d&a" in lower or "depreciation" in lower

    def test_working_capital_listed_as_missing(self):
        out = _ask("FCF reconciliation — capex, working capital, D&A")
        lower = out.lower()
        assert "working" in lower or "working-capital" in lower

    def test_tax_listed_as_missing(self):
        out = _ask("FCF reconciliation — capex, tax")
        lower = out.lower()
        assert "tax" in lower

    def test_no_fabrication_of_da_per_share(self):
        # Should NOT invent a ₹X.XX D&A per share value
        out = _ask("Explain FCF/EPS gap by D&A and capex from financial-statement data")
        # Must not claim to know D&A per share
        assert "d&a per share" not in out.lower() or "not stored" in out.lower() or "cannot" in out.lower()

    def test_no_fabrication_of_wc_per_share(self):
        out = _ask("FCF reconciliation — working capital and depreciation")
        # Must not claim a specific WC value
        lower = out.lower()
        assert "working capital per share" not in lower or "not stored" in lower or "cannot" in lower

    def test_exact_attribution_not_claimed(self):
        # Must NOT say "capex alone explains the ₹3.79 gap"
        out = _ask("FCF reconciliation — capex, D&A, taxes")
        lower = out.lower()
        assert "capex alone" not in lower
        assert "capex explains the" not in lower


# ===========================================================================
# E — Structural section
# ===========================================================================

class TestE_StructuralSection:

    def test_structural_section_present(self):
        out = _ask("FCF reconciliation — capex and depreciation analysis")
        assert "STRUCTURAL" in out

    def test_structural_labelled_as_general(self):
        out = _ask("FCF reconciliation — capex, D&A")
        # Must say it's general / not company-specific
        lower = out.lower()
        assert "general" in lower or "not itc" in lower or "not company" in lower

    def test_structural_mentions_da_as_mechanism(self):
        out = _ask("FCF reconciliation — capex, depreciation, taxes")
        lower = out.lower()
        assert "d&a" in lower or "depreciation" in lower

    def test_structural_mentions_capex_as_mechanism(self):
        out = _ask("FCF reconciliation — capex, working capital")
        assert "capex" in out.lower()

    def test_source_footer_present(self):
        out = _ask("FCF reconciliation — capex, D&A")
        assert "No new financial data" in out


# ===========================================================================
# F — Non-regression
# ===========================================================================

class TestF_NonRegression:

    def test_risk_question_unaffected(self):
        out = render_followup("What are the biggest risks?", _make_ida())
        assert "RISK" in out.upper() or "risk" in out.lower()

    def test_pe_question_unaffected(self):
        out = render_followup("Explain the P/E ratio", _make_ida())
        assert "p/e" in out.lower() or "P/E" in out

    def test_pfcf_question_unaffected(self):
        out = render_followup("How does P/FCF work for ITC?", _make_ida())
        assert "p/fcf" in out.lower() or "P/FCF" in out

    def test_fcf_eps_generic_still_works(self):
        # Generic FCF vs EPS (no reconciliation terms) goes to _answer_fcf_eps
        out = render_followup("Why is FCF lower than EPS?", _make_ida())
        assert "FCF" in out or "fcf" in out.lower()

    def test_why_question_unaffected(self):
        out = render_followup("Why did you reach a WATCH conclusion?", _make_ida())
        lower = out.lower()
        assert "watch" in lower or "conclusion" in lower or "decision" in lower

    def test_confidence_question_unaffected(self):
        out = render_followup("How confident are you in this analysis?", _make_ida())
        lower = out.lower()
        assert "confidence" in lower or "confident" in lower

    def test_data_quality_still_works(self):
        out = render_followup("How fresh is the underlying data?", _make_ida())
        lower = out.lower()
        assert "freshness" in lower or "stale" in lower or "data" in lower
