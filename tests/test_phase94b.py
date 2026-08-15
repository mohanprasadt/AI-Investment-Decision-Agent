"""
Phase 9.4b Regression Tests — Valuation Follow-up Specificity
==============================================================
Tests that follow-up questions about specific valuation methods (P/E, EV/EBITDA,
P/FCF) and "why expensive" route to the new _answer_valuation_method handler and
produce a response that:
  1. Uses per_method_valuation_summary data from the stored assessment.
  2. Explains the weighted combination rather than a single metric.
  3. Does NOT invent financial facts not present in the assessment.
  4. Still routes generic valuation questions to _answer_valuation.

Run:  pytest tests/test_phase94b.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.decision.decision_models import InvestmentDecisionAssessment, DecisionAction


# ---------------------------------------------------------------------------
# Shared fixture helper
# ---------------------------------------------------------------------------

def _make_assessment(
    *,
    per_method_summary=None,
    valuation_conclusion="Price is above estimated fair value.",
    key_assumptions=None,
    valuation_attractiveness_label="NEGATIVE",
    action=DecisionAction.WATCH,
) -> InvestmentDecisionAssessment:
    """
    Build a minimal InvestmentDecisionAssessment with pre-populated
    per_method_valuation_summary for routing/renderer tests.
    """
    d = InvestmentDecisionAssessment(
        ticker="ITC.NS",
        company_name="ITC Limited",
        analysis_date="2026-08-10",
        current_price=282.65,
        price_currency="INR",
        action=action,
        valuation_conclusion=valuation_conclusion,
        valuation_attractiveness_label=valuation_attractiveness_label,
        key_assumptions=key_assumptions or [
            "Normalised P/E based on 3-year average EPS.",
            "EV/EBITDA uses trailing 12-month EBITDA.",
            "P/FCF uses trailing FCF; FCF normalised for capex cycle.",
        ],
        per_method_valuation_summary=per_method_summary if per_method_summary is not None else [
            "DCF: bear INR 166.54 | mid INR 195.93 | bull INR 225.32"
            "  [reliability: LOW, weight: 0.3] (30.7% below current price INR 282.65)",
            "Normalised P/E: bear INR 242.51 | mid INR 285.30 | bull INR 328.10"
            "  [reliability: LOW, weight: 0.3] (0.9% above current price INR 282.65)",
            "EV/EBITDA: bear INR 204.04 | mid INR 240.05 | bull INR 276.06"
            "  [reliability: MEDIUM, weight: 0.6] (15.1% below current price INR 282.65)",
            "P/FCF: bear INR 184.17 | mid INR 216.67 | bull INR 249.17"
            "  [reliability: MEDIUM, weight: 0.6] (23.4% below current price INR 282.65)",
            "Weighted average fair value: bear INR 197.64 | base INR 232.52 | bull INR 267.40"
            " (17.7% below current price INR 282.65)",
        ],
    )
    return d


# ---------------------------------------------------------------------------
# Class A — Routing: specific-method keywords reach _answer_valuation_method
# ---------------------------------------------------------------------------

class TestA_Routing:
    """Verify render_followup routes method-specific questions correctly."""

    def _render(self, question: str, d=None) -> str:
        from analytics.agent.renderer import render_followup
        return render_followup(question, d or _make_assessment())

    def test_pe_question_routes_to_method_handler(self):
        """'P/E is only 18x' must route to the method breakdown handler."""
        resp = self._render("Why is ITC considered expensive when its P/E is only around 18x?")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp, (
            "P/E question should trigger per-method breakdown"
        )

    def test_why_expensive_routes_to_method_handler(self):
        """'Why is it expensive' must route to the method breakdown handler."""
        resp = self._render("Why is ITC considered expensive at ₹282.65?")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp, (
            "'why expensive' should trigger per-method breakdown"
        )

    def test_ev_ebitda_question_routes_to_method_handler(self):
        """EV/EBITDA question must route to the method breakdown handler."""
        resp = self._render("What does the EV/EBITDA method say about ITC's valuation?")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp, (
            "EV/EBITDA question should trigger per-method breakdown"
        )

    def test_pfcf_question_routes_to_method_handler(self):
        """P/FCF question routes to method breakdown."""
        resp = self._render("How does the P/FCF valuation compare to the current price?")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp

    def test_which_method_routes_to_method_handler(self):
        """'Which method drives the valuation' routes to method breakdown."""
        resp = self._render("Which method drives the valuation conclusion for ITC?")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp

    def test_generic_assumption_still_routes_to_answer_valuation(self):
        """Generic 'what are the valuation assumptions' does NOT use the method handler."""
        resp = self._render("What are the valuation assumptions for ITC?")
        # _answer_valuation produces "Valuation detail" header, not method-specific header
        assert "Valuation detail" in resp or "KEY VALUATION ASSUMPTIONS" in resp

    def test_generic_fair_value_still_routes_to_answer_valuation(self):
        """'What is the fair value?' routes to generic _answer_valuation."""
        resp = self._render("What is the fair value for ITC?")
        assert "Valuation detail" in resp or "KEY VALUATION ASSUMPTIONS" in resp

    def test_price_to_earnings_spelled_out_routes_correctly(self):
        """'price-to-earnings' (hyphenated) must also route to method handler."""
        resp = self._render("The price-to-earnings ratio seems reasonable, why WAIT?")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp


# ---------------------------------------------------------------------------
# Class B — Content: P/E-specific response
# ---------------------------------------------------------------------------

class TestB_PEContent:
    """Verify the P/E response explains the weighted combination correctly."""

    def _render_pe(self, d=None) -> str:
        from analytics.agent.renderer import render_followup
        return render_followup(
            "Why is ITC considered expensive when its P/E is only around 18x?",
            d or _make_assessment()
        )

    def test_pe_response_mentions_weighted_combination(self):
        """Response must explain that P/E is one of several methods in a weighted combination."""
        resp = self._render_pe()
        assert (
            "weighted" in resp.lower() or "combination" in resp.lower()
            or "weight" in resp.lower()
        ), "P/E response should mention weighted combination"

    def test_pe_response_shows_all_four_methods(self):
        """All four method names should appear in the response when summary is populated."""
        resp = self._render_pe()
        for method_fragment in ("DCF", "P/E", "EV/EBITDA", "P/FCF"):
            assert method_fragment in resp, (
                f"Method '{method_fragment}' should appear in P/E follow-up response"
            )

    def test_pe_response_shows_weighted_average_line(self):
        """The weighted-average base fair value line must be shown."""
        resp = self._render_pe()
        assert "Weighted average" in resp

    def test_pe_response_explains_not_sole_determinant(self):
        """Response must clarify P/E is not the sole determinant."""
        resp = self._render_pe()
        assert (
            "not the sole" in resp.lower()
            or "not solely" in resp.lower()
            or "not only" in resp.lower()
            or "one of" in resp.lower()
        ), "Response should clarify P/E is not the only driver"

    def test_pe_response_no_fabrication_when_summary_empty(self):
        """
        When per_method_valuation_summary is empty, the response must NOT
        fabricate method values — it must say data is unavailable.
        """
        d = _make_assessment(per_method_summary=[])
        from analytics.agent.renderer import render_followup
        resp = render_followup(
            "Why is ITC expensive? The P/E seems fine at 18x.",
            d
        )
        # Must NOT contain fabricated INR values
        assert "INR 195" not in resp, "Should not fabricate DCF value when summary is empty"
        assert "INR 240" not in resp, "Should not fabricate EV/EBITDA value when summary is empty"
        # Must say data is unavailable
        assert (
            "not available" in resp.lower()
            or "not present" in resp.lower()
            or "re-run" in resp.lower()
            or "breakdown" in resp.lower()
        ), "Should acknowledge missing per-method data"


# ---------------------------------------------------------------------------
# Class C — Content: EV/EBITDA-specific response
# ---------------------------------------------------------------------------

class TestC_EVEBITDAContent:
    """Verify the EV/EBITDA response explains the EV bridge concept."""

    def _render_ev(self, d=None) -> str:
        from analytics.agent.renderer import render_followup
        return render_followup(
            "What does the EV/EBITDA method say about ITC's valuation?",
            d or _make_assessment()
        )

    def test_ev_response_shows_method_breakdown(self):
        """EV/EBITDA response must include per-method breakdown."""
        resp = self._render_ev()
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp

    def test_ev_response_mentions_ev_bridge(self):
        """EV/EBITDA response should mention the EV bridge (debt + cash)."""
        resp = self._render_ev()
        assert (
            "bridge" in resp.lower()
            or ("debt" in resp.lower() and "cash" in resp.lower())
            or "enterprise" in resp.lower()
        ), "EV/EBITDA response should mention EV bridge or enterprise value"

    def test_ev_response_shows_ebitda_line(self):
        """EV/EBITDA summary line must be visible in the response."""
        resp = self._render_ev()
        assert "EV/EBITDA" in resp

    def test_ev_response_no_fabrication_when_empty(self):
        """No fabrication when per_method_valuation_summary is empty."""
        d = _make_assessment(per_method_summary=[])
        from analytics.agent.renderer import render_followup
        resp = render_followup("What does EV/EBITDA say about ITC?", d)
        assert "INR 240" not in resp, "Must not fabricate EV/EBITDA value"


# ---------------------------------------------------------------------------
# Class D — Content: "why expensive" response
# ---------------------------------------------------------------------------

class TestD_WhyExpensiveContent:
    """Verify the 'why expensive' response explains the aggregate, not one method."""

    def _render_why(self, d=None) -> str:
        from analytics.agent.renderer import render_followup
        return render_followup(
            "Why is ITC considered expensive at ₹282.65?",
            d or _make_assessment()
        )

    def test_why_expensive_shows_breakdown(self):
        resp = self._render_why()
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp

    def test_why_expensive_shows_weighted_average(self):
        resp = self._render_why()
        assert "Weighted average" in resp

    def test_why_expensive_references_current_price_vs_fv(self):
        """Response should include 'above' or 'below' vs current price context."""
        resp = self._render_why()
        assert "above" in resp.lower() or "below" in resp.lower(), (
            "Response should indicate price is above/below fair value"
        )

    def test_why_expensive_explains_zone_logic(self):
        """Response should explain that WAIT zone comes from price > weighted avg FV."""
        resp = self._render_why()
        assert (
            "weighted" in resp.lower() and (
                "wait" in resp.lower() or "exceeds" in resp.lower() or "above" in resp.lower()
            )
        ), "Response should link WAIT zone to price exceeding weighted average FV"

    def test_why_expensive_no_fabrication_empty_summary(self):
        """No fabricated values when per_method_summary is empty."""
        d = _make_assessment(per_method_summary=[])
        from analytics.agent.renderer import render_followup
        resp = render_followup("Why is ITC expensive?", d)
        assert "INR 232" not in resp, "Must not fabricate base FV value"
        assert "INR 240" not in resp, "Must not fabricate EV/EBITDA value"


# ---------------------------------------------------------------------------
# Class E — direct _answer_valuation_method unit tests
# ---------------------------------------------------------------------------

class TestE_DirectHandler:
    """Unit tests for _answer_valuation_method called directly."""

    def test_handler_is_callable(self):
        from analytics.agent.renderer import _answer_valuation_method
        d = _make_assessment()
        result = _answer_valuation_method(d, "why is it expensive?")
        assert isinstance(result, str) and len(result) > 0

    def test_analysis_date_present_in_output(self):
        from analytics.agent.renderer import _answer_valuation_method
        d = _make_assessment()
        resp = _answer_valuation_method(d, "p/e valuation")
        assert "2026-08-10" in resp, "Analysis date should appear in response footer"

    def test_disclaimer_present(self):
        from analytics.agent.renderer import _answer_valuation_method
        d = _make_assessment()
        resp = _answer_valuation_method(d, "p/e valuation")
        assert "not a" in resp.lower() or "estimate" in resp.lower() or "not" in resp.lower()
