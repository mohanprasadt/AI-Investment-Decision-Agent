"""
Phase 9.7 — P/FCF follow-up calculation chain tests
=====================================================

Tests for the enhanced _answer_valuation_method() P/FCF branch:
  - _parse_method_values() helper
  - Current P/FCF ratio display
  - Implied multiples derived from stored data (not hard-coded)
  - Midpoint calculation chain  (FCF/share × multiple = fair value)
  - Price vs fair value with two distinct % framings
  - P/E comparison when both P/FCF and P/E lines available
  - No fabrication / no hard-coded multiples
  - Non-regression for other follow-up handlers

Architecture boundary: tests call renderer.render_followup() and
                       renderer._parse_method_values() only.
                       No valuation logic is tested or changed.

ITC constants (sourced from stored assessment):
  FCF/share         = 12.04
  EPS               = 15.83
  Current price     = 279.00
  P/FCF mid         = 216.67
  P/FCF bear        = 184.17
  P/FCF bull        = 249.17
  P/E mid           = 285.30
  P/FCF implied mid multiple = 216.67 / 12.04 ≈ 18×
  Current P/FCF     = 279 / 12.04 ≈ 23.2×
  % above P/FCF mid = (279 - 216.67) / 216.67 = 28.8%
  % of price        = (279 - 216.67) / 279     = 22.3%
"""

from __future__ import annotations

import math
import pytest

from analytics.agent.renderer import render_followup, _parse_method_values
from analytics.decision.decision_models import (
    InvestmentDecisionAssessment,
    DecisionAction,
    DecisionConfidence,
)


# ---------------------------------------------------------------------------
# Shared test fixture helpers
# ---------------------------------------------------------------------------

PFCF_SUMMARY_LINE = (
    "P/FCF: bear INR 184.17 | mid INR 216.67 | bull INR 249.17"
    "  [reliability: MEDIUM, weight: 0.6]"
)

PE_SUMMARY_LINE = (
    "Normalised P/E: bear INR 242.51 | mid INR 285.30 | bull INR 328.10"
    "  [reliability: LOW, weight: 0.3]"
)

WEIGHTED_LINE = "Weighted average: bear INR 200.00 | mid INR 235.00 | bull INR 270.00"

ITC_PRICE   = 279.0
ITC_FCF_PS  = 12.04
ITC_EPS     = 15.83
PFCF_MID    = 216.67
PFCF_BEAR   = 184.17
PFCF_BULL   = 249.17
PE_MID      = 285.30


def _make_ida(
    *,
    price: float = ITC_PRICE,
    fcf_ps: float | None = ITC_FCF_PS,
    eps: float | None = ITC_EPS,
    method_lines: list[str] | None = None,
    currency: str = "INR",
    ticker: str = "ITC.NS",
) -> InvestmentDecisionAssessment:
    """Minimal IDA with Phase 9.5/9.6 fields set for P/FCF tests."""
    if method_lines is None:
        method_lines = [PFCF_SUMMARY_LINE, PE_SUMMARY_LINE, WEIGHTED_LINE]
    return InvestmentDecisionAssessment(
        ticker=ticker,
        company_name="ITC Ltd",
        analysis_date="2026-08-09",
        action=DecisionAction.WATCH,
        decision_confidence=DecisionConfidence.MEDIUM,
        qualitative_investment_view="Stable conglomerate.",
        business_thesis="Steady FCF generator.",
        current_price=price,
        price_currency=currency,
        price_date="2026-08-09",
        valuation_conclusion="P/FCF views current price as above midpoint.",
        per_method_valuation_summary=method_lines,
        fcf_per_share_used=fcf_ps,
        eps_used_in_valuation=eps,
        fcf_normalization_note="3-year average FCF / shares outstanding.",
    )


def _followup(question: str, ida: InvestmentDecisionAssessment | None = None) -> str:
    if ida is None:
        ida = _make_ida()
    return render_followup(question, ida)


# ===========================================================================
# A — _parse_method_values() helper
# ===========================================================================

class TestA_ParseMethodValues:
    """Unit tests for the bear/mid/bull extractor."""

    def test_pfcf_line_extracted(self):
        bear, mid, bull = _parse_method_values([PFCF_SUMMARY_LINE], "p/fcf")
        assert math.isclose(bear, 184.17, abs_tol=0.01)
        assert math.isclose(mid,  216.67, abs_tol=0.01)
        assert math.isclose(bull, 249.17, abs_tol=0.01)

    def test_pe_line_extracted(self):
        bear, mid, bull = _parse_method_values([PE_SUMMARY_LINE], "normalised p/e")
        assert math.isclose(mid, 285.30, abs_tol=0.01)

    def test_prefix_case_insensitive(self):
        result = _parse_method_values([PFCF_SUMMARY_LINE], "P/FCF")
        assert result is not None

    def test_wrong_prefix_returns_none(self):
        result = _parse_method_values([PFCF_SUMMARY_LINE], "ev/ebitda")
        assert result is None

    def test_empty_list_returns_none(self):
        assert _parse_method_values([], "p/fcf") is None

    def test_none_list_returns_none(self):
        assert _parse_method_values(None, "p/fcf") is None

    def test_multiple_lines_correct_prefix_matched(self):
        lines = [PE_SUMMARY_LINE, PFCF_SUMMARY_LINE]
        bear, mid, bull = _parse_method_values(lines, "p/fcf")
        assert math.isclose(mid, 216.67, abs_tol=0.01)

    def test_pe_not_matched_by_pfcf_prefix(self):
        # "Normalised P/E" should NOT match prefix "p/fcf"
        result = _parse_method_values([PE_SUMMARY_LINE], "p/fcf")
        assert result is None


# ===========================================================================
# B — Current P/FCF ratio
# ===========================================================================

class TestB_CurrentRatio:
    """The follow-up must show current price ÷ FCF/share with the result."""

    def test_current_pfcf_shown(self):
        out = _followup("Does ITC's lower FCF/share make it look expensive on P/FCF?")
        assert "23." in out or "23.2" in out   # 279 / 12.04 ≈ 23.2

    def test_fcf_per_share_surfaced(self):
        out = _followup("p/fcf question for ITC")
        assert "12.04" in out

    def test_current_price_shown(self):
        out = _followup("p/fcf question for ITC")
        assert "279" in out

    def test_division_expression_shown(self):
        # "279.00 ÷ 12.04" or similar
        out = _followup("p/fcf question")
        assert "÷" in out

    def test_no_fcf_ps_graceful(self):
        ida = _make_ida(fcf_ps=None)
        out = _followup("p/fcf question", ida)
        # Should not crash and should flag that FCF/share is unavailable
        assert "not stored" in out.lower() or "not available" in out.lower() or "cannot" in out.lower()


# ===========================================================================
# C — Implied multiples and midpoint calculation
# ===========================================================================

class TestC_ImpliedMultiples:
    """Midpoint multiple must be derived from stored values, not hard-coded."""

    def test_mid_multiple_present(self):
        # 216.67 / 12.04 ≈ 18.0 — the × symbol should appear
        out = _followup("Why does P/FCF value ITC lower than P/E?")
        assert "18" in out   # implied multiple ≈ 18×

    def test_midpoint_calc_chain_shown(self):
        # "12.04 × 18× = 216.67" pattern (approx)
        out = _followup("Why does P/FCF value ITC lower than P/E?")
        assert "12.04" in out
        assert "216.67" in out

    def test_bear_mid_bull_all_present(self):
        out = _followup("p/fcf method for ITC")
        assert "184.17" in out
        assert "216.67" in out
        assert "249.17" in out

    def test_base_case_label_present(self):
        out = _followup("p/fcf fair value")
        lower = out.lower()
        assert "base" in lower or "mid" in lower

    def test_multiples_not_hardcoded_uses_division(self):
        # The output must explicitly say it derived multiples from stored data
        out = _followup("p/fcf multiple question")
        lower = out.lower()
        assert "derived" in lower or "stored" in lower or "not hard" in lower

    def test_no_pfcf_summary_graceful(self):
        ida = _make_ida(method_lines=[])
        out = _followup("p/fcf question", ida)
        assert "not stored" in out.lower() or "not available" in out.lower()


# ===========================================================================
# D — Price vs fair value — two % framings
# ===========================================================================

class TestD_PercentFramings:
    """Both '28.8% above fair value' and '22.3% of current price' must appear."""

    def _get_out(self) -> str:
        return _followup("Does ITC's lower FCF/share make it look expensive on P/FCF?")

    def test_pct_above_fair_value_present(self):
        # (279 - 216.67) / 216.67 = 28.8%
        out = self._get_out()
        assert "28.8" in out

    def test_pct_of_current_price_present(self):
        # (279 - 216.67) / 279 = 22.3%
        out = self._get_out()
        assert "22.3" in out

    def test_both_framings_in_same_response(self):
        out = self._get_out()
        assert "28.8" in out and "22.3" in out

    def test_framing_distinction_language_present(self):
        out = self._get_out()
        lower = out.lower()
        # Must explain the different denominators
        assert "denominator" in lower or "framing" in lower or "different" in lower

    def test_above_midpoint_conclusion_shown(self):
        out = self._get_out()
        lower = out.lower()
        assert "above" in lower and ("midpoint" in lower or "fair value" in lower)


# ===========================================================================
# E — P/E comparison
# ===========================================================================

class TestE_PeComparison:
    """P/FCF vs P/E comparison must appear when both valuation lines are available."""

    def _get_out(self) -> str:
        return _followup("Why does P/FCF value ITC lower than P/E?")

    def test_pe_midpoint_shown(self):
        out = self._get_out()
        assert "285.30" in out

    def test_pfcf_midpoint_shown_alongside_pe(self):
        out = self._get_out()
        assert "216.67" in out

    def test_pe_closer_to_price_statement(self):
        out = self._get_out()
        lower = out.lower()
        assert "closer" in lower or "p/e" in lower

    def test_structural_reason_present(self):
        out = self._get_out()
        lower = out.lower()
        assert "structural" in lower

    def test_fcf_ps_and_eps_both_shown_in_explanation(self):
        out = self._get_out()
        # Both per-share metrics should appear in the explanation
        assert "12.04" in out
        assert "15.83" in out

    def test_pe_comparison_present_for_expensive_question(self):
        # P/E comparison should appear even when P/E is not explicitly asked
        out = _followup("Does ITC's lower FCF/share make it look expensive on P/FCF?")
        assert "285.30" in out or "p/e" in out.lower()

    def test_no_pe_comparison_when_pe_line_absent(self):
        ida = _make_ida(method_lines=[PFCF_SUMMARY_LINE])
        out = render_followup("Why does P/FCF value ITC lower than P/E?", ida)
        # Should not mention "285.30" — no P/E data stored
        assert "285.30" not in out


# ===========================================================================
# F — No fabrication
# ===========================================================================

class TestF_NoFabrication:
    """Renderer must not invent multiples, data, or conclusions."""

    def test_multiples_derived_not_stated_as_fact(self):
        # The word "assumed" or "hard-coded" should NOT appear
        out = _followup("p/fcf multiple question")
        assert "assumed multiple" not in out.lower()
        assert "hard-coded multiple" not in out.lower()

    def test_sourcing_note_present(self):
        out = _followup("p/fcf follow-up")
        lower = out.lower()
        assert "stored" in lower or "assessment" in lower

    def test_no_dna_per_share_invented(self):
        # D&A per share is not a stored field — should not appear
        out = _followup("p/fcf question")
        assert "d&a per share" not in out.lower()
        assert "depreciation per share" not in out.lower()

    def test_no_invented_peg_ratio(self):
        out = _followup("p/fcf question")
        assert "peg ratio" not in out.lower()

    def test_currency_from_stored_not_hardcoded(self):
        # Currency must come from d.price_currency, not literal "₹"
        # Test with a USD company
        ida = _make_ida(currency="USD")
        out = render_followup("p/fcf question", ida)
        # Should say "USD" not "₹" for the values
        assert "USD" in out or "usd" in out.lower()


# ===========================================================================
# G — Non-regression
# ===========================================================================

class TestG_NonRegression:
    """Other follow-up handlers must be unaffected by Phase 9.7 changes."""

    def test_pe_question_still_routed_to_pe_block(self):
        out = _followup("Explain the P/E ratio used in valuation")
        lower = out.lower()
        # P/E handler talks about weight/reliability
        assert "p/e" in lower

    def test_ev_question_still_routed_to_ev_block(self):
        out = _followup("Explain the EV/EBITDA method")
        lower = out.lower()
        assert "ev/ebitda" in lower or "enterprise value" in lower

    def test_why_expensive_still_works(self):
        out = _followup("Why does the stock look expensive?")
        # Should not crash and should mention valuation
        assert "valuation" in out.lower() or "weighted" in out.lower()

    def test_fcf_eps_handler_unaffected(self):
        # FCF metric questions (no "p/fcf" keyword) go to _answer_fcf_eps
        out = _followup("Why is FCF lower than EPS for ITC?")
        lower = out.lower()
        # _answer_fcf_eps talks about structural difference
        assert "structural" in lower or "eps" in lower or "fcf" in lower

    def test_pfcf_question_does_not_leak_into_generic_handler(self):
        # A P/FCF question must NOT produce the generic "I don't have an analysis"
        out = _followup("p/fcf question")
        assert "I don't have an analysis" not in out
        assert "don't have" not in out.lower()

    def test_per_method_breakdown_still_shown_after_pfcf_intro(self):
        # The full per-method table should still appear after the P/FCF-specific intro
        out = _followup("p/fcf question")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in out

    def test_phase95_fields_still_readable(self):
        ida = _make_ida()
        assert ida.fcf_per_share_used == ITC_FCF_PS
        assert ida.eps_used_in_valuation == ITC_EPS

    def test_parse_method_values_not_broken_by_weighted_line(self):
        # Weighted average line must not accidentally match a method prefix
        lines = [WEIGHTED_LINE]
        assert _parse_method_values(lines, "p/fcf") is None
        assert _parse_method_values(lines, "normalised p/e") is None
