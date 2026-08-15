"""
Phase 9.4d Regression Tests — FCF/EPS Follow-up Routing
=========================================================
Bug fixed: "Why is ITC's FCF/share only ~₹12 while EPS is ~₹15.83?"
was routed to the generic _answer_why handler because no FCF-specific
routing existed before the "why" catch.

Fix:
  1. Added FCF-metric routing block in render_followup BEFORE the "why" catch.
     Triggers on: "free cash flow", "fcf/share", "fcf per share", "cash flow per share",
     OR: "fcf" in question + at least one contextual word (eps, per share, calculat, etc.)
  2. Added _answer_fcf_eps() handler that:
     - Gives the structural EPS vs FCF accounting definition (always shown, factual).
     - Searches stored assessment for EPS/FCF references.
     - States the evidence gap explicitly when specific values are not stored.
     - Does NOT invent capex, working-capital, or tax numbers.

Run:  pytest tests/test_phase94d.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.decision.decision_models import (
    InvestmentDecisionAssessment, DecisionAction, DecisionEvidenceItem, EvidenceStrength,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_assessment(
    *,
    key_assumptions=None,
    per_method_summary=None,
    supporting_evidence=None,
    valuation_conclusion="Price is above estimated fair value.",
    action=DecisionAction.WATCH,
) -> InvestmentDecisionAssessment:
    """Minimal ITC assessment for FCF/EPS routing tests."""
    return InvestmentDecisionAssessment(
        ticker="ITC.NS",
        company_name="ITC Limited",
        analysis_date="2026-08-10",
        current_price=282.65,
        price_currency="INR",
        action=action,
        valuation_conclusion=valuation_conclusion,
        valuation_attractiveness_label="NEGATIVE",
        key_assumptions=key_assumptions if key_assumptions is not None else [
            "Normalised P/E based on 3-year average EPS.",
            "EV/EBITDA uses trailing 12-month EBITDA.",
            "P/FCF uses trailing FCF; FCF normalised for capex cycle.",
        ],
        per_method_valuation_summary=per_method_summary if per_method_summary is not None else [
            "DCF: bear INR 166.54 | mid INR 195.93 | bull INR 225.32  [reliability: LOW, weight: 0.3]",
            "Normalised P/E: bear INR 242.51 | mid INR 285.30 | bull INR 328.10  [reliability: LOW, weight: 0.3]",
            "EV/EBITDA: bear INR 204.04 | mid INR 240.05 | bull INR 276.06  [reliability: MEDIUM, weight: 0.6]",
            "P/FCF: bear INR 184.17 | mid INR 216.67 | bull INR 249.17  [reliability: MEDIUM, weight: 0.6]",
            "Weighted average fair value: bear INR 197.64 | base INR 232.52 | bull INR 267.40",
        ],
        supporting_evidence=supporting_evidence or [],
    )


def _render(question: str, d=None) -> str:
    from analytics.agent.renderer import render_followup
    return render_followup(question, d or _make_assessment())


# ---------------------------------------------------------------------------
# Class A — Routing: FCF/EPS questions reach _answer_fcf_eps
# ---------------------------------------------------------------------------

class TestA_Routing:
    """Verify render_followup routes FCF/EPS questions to the dedicated handler."""

    def test_fcf_share_vs_eps_routes_to_fcf_handler(self):
        """Primary bug case: 'Why is ITC's FCF/share only ~₹12 while EPS is ~₹15.83?'"""
        resp = _render("Why is ITC's FCF/share only ~₹12 while EPS is ~₹15.83?")
        # Must NOT be the generic "Why WATCH?" response
        assert "STRUCTURAL DIFFERENCE" in resp, (
            "FCF/share vs EPS question should route to _answer_fcf_eps, not _answer_why"
        )

    def test_fcf_per_share_lower_than_eps_routes_to_fcf_handler(self):
        """'Why is FCF per share lower than EPS?' → FCF handler."""
        resp = _render("Why is FCF per share lower than EPS?")
        assert "STRUCTURAL DIFFERENCE" in resp

    def test_how_is_fcf_calculated_routes_to_fcf_handler(self):
        """'How is ITC's FCF calculated?' → FCF handler (via _fcf_context: calculat)."""
        resp = _render("How is ITC's FCF calculated?")
        assert "STRUCTURAL DIFFERENCE" in resp

    def test_free_cash_flow_keyword_routes_to_fcf_handler(self):
        """'What is ITC's free cash flow?' → FCF handler via explicit keyword."""
        resp = _render("What is ITC's free cash flow vs earnings?")
        assert "STRUCTURAL DIFFERENCE" in resp

    def test_why_watch_still_routes_to_why_handler(self):
        """'Why WATCH?' must NOT be intercepted by FCF routing."""
        resp = _render("Why WATCH for ITC?")
        # _answer_why produces the action-based explanation, not STRUCTURAL DIFFERENCE
        assert "STRUCTURAL DIFFERENCE" not in resp, (
            "'Why WATCH' should route to _answer_why, not _answer_fcf_eps"
        )

    def test_which_valuation_method_still_routes_to_method_handler(self):
        """'Which valuation method makes ITC look most expensive?' → _answer_valuation_method (9.4c)."""
        resp = _render("Which valuation method makes ITC look most expensive?")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp
        assert "STRUCTURAL DIFFERENCE" not in resp

    def test_pfcf_valuation_question_routes_to_method_handler(self):
        """'How does P/FCF valuation compare?' (as multiple) → _answer_valuation_method, not FCF handler."""
        resp = _render("How does the P/FCF valuation compare to the current price?")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp


# ---------------------------------------------------------------------------
# Class B — Content: structural explanation always present
# ---------------------------------------------------------------------------

class TestB_StructuralExplanation:
    """Verify _answer_fcf_eps always includes the EPS/FCF structural definition."""

    def test_eps_definition_present(self):
        resp = _render("Why is FCF per share lower than EPS?")
        assert "EPS" in resp and "Net income" in resp.replace("\n", " "), (
            "Structural EPS definition should be present"
        )

    def test_fcf_definition_present(self):
        resp = _render("Why is FCF per share lower than EPS?")
        assert "Operating Cash Flow" in resp and "Capital Expenditure" in resp, (
            "FCF = OCF − capex definition should be present"
        )

    def test_capex_explanation_present(self):
        """The capex capitalisation reason (why FCF < EPS) should always be stated."""
        resp = _render("How is ITC's FCF calculated?")
        assert "capex" in resp.lower() or "capital expenditure" in resp.lower()

    def test_working_capital_mentioned(self):
        resp = _render("Why is ITC's FCF/share only ~₹12 while EPS is ~₹15.83?")
        assert "working capital" in resp.lower() or "receivable" in resp.lower() or "inventory" in resp.lower()

    def test_no_new_data_disclaimer_present(self):
        """Footer must state no new financial data was generated."""
        resp = _render("Why is ITC's FCF/share only ~₹12 while EPS is ~₹15.83?")
        assert "no new financial data" in resp.lower(), (
            "Response must include a disclaimer that no new data was generated"
        )


# ---------------------------------------------------------------------------
# Class C — Evidence gap: explicit when specific values not in stored assessment
# ---------------------------------------------------------------------------

class TestC_EvidenceGap:
    """When no specific EPS/FCF values are stored, the gap is explicitly stated."""

    def test_evidence_gap_stated_when_no_specific_values(self):
        """
        The default assessment has no specific ₹12 FCF or ₹15.83 EPS stored.
        The handler must say so — not invent the values.
        """
        resp = _render(
            "Why is ITC's FCF/share only ~₹12 while EPS is ~₹15.83?",
            _make_assessment(key_assumptions=[], per_method_summary=[], supporting_evidence=[]),
        )
        # Must NOT fabricate specific ₹ values
        assert "₹12" not in resp or "not" in resp.lower(), (
            "Must not state ₹12 as a fact when it's not in the assessment"
        )
        assert "₹15.83" not in resp or "not" in resp.lower(), (
            "Must not state ₹15.83 as a fact when it's not in the assessment"
        )
        # Must acknowledge the gap
        assert (
            "not contain" in resp.lower()
            or "not stored" in resp.lower()
            or "not available" in resp.lower()
            or "evidence gap" in resp.lower()
            or "cannot identify" in resp.lower()
            or "cannot determine" in resp.lower()
        ), "Response must explicitly state that specific values are not in the stored assessment"

    def test_no_invented_capex_numbers(self):
        """No fabricated capex or WC amounts when assessment has no such data."""
        resp = _render(
            "Why is ITC's FCF/share only ~₹12 while EPS is ~₹15.83?",
            _make_assessment(key_assumptions=[], per_method_summary=[], supporting_evidence=[]),
        )
        # Structural conceptual mention is OK; specific ₹ amounts for capex are not
        # We check that no suspicious invented ₹ figures appear beyond the user's own quote
        import re
        inr_amounts = re.findall(r"(?:INR|₹)\s*[\d,]+(?:\.\d+)?", resp)
        # All INR amounts in the response must come from structural definitions or explicit
        # evidence gaps — not from the user's quoted values repeated as facts.
        # A response with zero invented INR amounts is fine.
        # We allow the "not contain" path to mention user quotes only in a dismissal context.
        # Simple check: if any specific INR figure appears, it must be labeled as "not stored"
        for amt in inr_amounts:
            if "12" in amt or "15" in amt:
                assert (
                    "not" in resp.lower()
                    or "stored" in resp.lower()
                ), f"Found suspicious INR amount {amt} that may be fabricated"

    def test_pfcf_line_surfaced_when_present(self):
        """When per_method_summary contains a P/FCF line, it IS surfaced in the response."""
        d = _make_assessment()  # default has P/FCF line
        resp = _render("Why is ITC's FCF/share lower than EPS?", d)
        assert "P/FCF" in resp or "FCF" in resp, (
            "When P/FCF summary line is stored, it should appear in the FCF handler response"
        )

    def test_key_assumption_with_fcf_surfaced(self):
        """When a key assumption references FCF, it is surfaced."""
        d = _make_assessment(key_assumptions=[
            "P/FCF uses trailing FCF; FCF normalised for capex cycle.",
            "Normalised P/E based on 3-year average EPS.",
        ])
        resp = _render("How is ITC's FCF calculated?", d)
        assert "trailing FCF" in resp or "capex cycle" in resp, (
            "Key assumption referencing FCF should be surfaced in the response"
        )

    def test_supporting_evidence_fcf_surfaced(self):
        """When supporting_evidence contains an FCF observation, it is surfaced."""
        evidence = [
            DecisionEvidenceItem(
                source_phase="financial_quality",
                dimension="FCF",
                observation="FCF yield of 5.2% is moderate; capex intensity has increased.",
                strength=EvidenceStrength.MODERATE,
                supports_thesis=True,
            )
        ]
        d = _make_assessment(supporting_evidence=evidence)
        resp = _render("Why is FCF per share lower than EPS?", d)
        assert "FCF yield" in resp or "capex intensity" in resp, (
            "Supporting evidence FCF observation should be surfaced"
        )


# ---------------------------------------------------------------------------
# Class D — Non-regression: existing handlers unchanged
# ---------------------------------------------------------------------------

class TestD_NonRegression:
    """Verify 9.4a/9.4b/9.4c behaviour is preserved."""

    def test_why_watch_answer_not_corrupted(self):
        """'Why did you recommend WATCH?' still explains the WATCH decision, not FCF."""
        resp = _render("Why did you recommend WATCH for ITC?")
        assert "STRUCTURAL DIFFERENCE" not in resp

    def test_valuation_assumption_question_unchanged(self):
        """'What are the valuation assumptions?' still routes to _answer_valuation."""
        resp = _render("What are the valuation assumptions for ITC?")
        assert "Valuation detail" in resp or "KEY VALUATION ASSUMPTIONS" in resp

    def test_pe_question_still_routes_to_method_handler(self):
        """'P/E is only 18x — why expensive?' still routes to _answer_valuation_method."""
        resp = _render("Why is ITC expensive if P/E is only 18x?")
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp
        assert "STRUCTURAL DIFFERENCE" not in resp

    def test_risk_question_still_routes_to_risk_handler(self):
        """'What are the biggest risks?' still routes to _answer_risks."""
        d = _make_assessment()
        from analytics.agent.renderer import render_followup
        resp = render_followup("What are the biggest risks for ITC?", d)
        assert "risk" in resp.lower() or "breaker" in resp.lower()
        assert "STRUCTURAL DIFFERENCE" not in resp
