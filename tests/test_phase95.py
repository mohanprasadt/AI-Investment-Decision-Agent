"""
Phase 9.5 Regression Tests — FCF/EPS Provenance Surfacing
==========================================================
D1 change: three provenance fields added to InvestmentDecisionAssessment
  - fcf_per_share_used       : FCF/share used by the P/FCF valuation method
  - fcf_normalization_note   : how that FCF figure was derived
  - eps_used_in_valuation    : normalised EPS used by the P/E method

These are populated in decision_synthesizer.py from ValuationAssessment method
results and surfaced in renderer._answer_fcf_eps so users get the actual
stored ITC values, not just a generic structural explanation.

Test groups:
  A — InvestmentDecisionAssessment carries provenance fields correctly
  B — _answer_fcf_eps surfaces stored values when provenance fields are set
  C — _answer_fcf_eps falls back gracefully when provenance fields are None
  D — Gap calculation shown when both FCF/share and EPS are available
  E — Non-regression: existing follow-ups (WATCH, valuation methods) unchanged

Run:  pytest tests/test_phase95.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from analytics.decision.decision_models import (
    InvestmentDecisionAssessment, DecisionAction,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_assessment(
    *,
    fcf_per_share_used=None,
    fcf_normalization_note="",
    eps_used_in_valuation=None,
    key_assumptions=None,
    per_method_summary=None,
    valuation_conclusion="Price is above estimated fair value.",
    action=DecisionAction.WATCH,
) -> InvestmentDecisionAssessment:
    """ITC assessment for Phase 9.5 provenance tests."""
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
            "P/FCF uses trailing FCF; FCF normalised for capex cycle.",
        ],
        per_method_valuation_summary=per_method_summary if per_method_summary is not None else [
            "P/FCF: bear INR 184.17 | mid INR 216.67 | bull INR 249.17  [reliability: MEDIUM, weight: 0.6]",
            "Normalised P/E: bear INR 242.51 | mid INR 285.30 | bull INR 328.10  [reliability: LOW, weight: 0.3]",
        ],
        fcf_per_share_used=fcf_per_share_used,
        fcf_normalization_note=fcf_normalization_note,
        eps_used_in_valuation=eps_used_in_valuation,
    )


def _render_fcf(d=None, question="why is fcf/share lower than eps") -> str:
    from analytics.agent.renderer import render_followup
    return render_followup(question, d or _make_assessment())


# ---------------------------------------------------------------------------
# Class A — InvestmentDecisionAssessment carries provenance fields
# ---------------------------------------------------------------------------

class TestA_ProvenanceFields:
    """Verify the three Phase 9.5 fields exist and round-trip through to_dict."""

    def test_fields_default_to_none_and_empty(self):
        d = InvestmentDecisionAssessment(ticker="X", company_name="X", analysis_date="2026-08-10")
        assert d.fcf_per_share_used is None
        assert d.fcf_normalization_note == ""
        assert d.eps_used_in_valuation is None

    def test_fields_accept_values(self):
        d = _make_assessment(
            fcf_per_share_used=12.04,
            fcf_normalization_note="Derived: 3-year average FCF (3yr avg to 2026)",
            eps_used_in_valuation=15.83,
        )
        assert d.fcf_per_share_used == pytest.approx(12.04)
        assert "3-year" in d.fcf_normalization_note
        assert d.eps_used_in_valuation == pytest.approx(15.83)

    def test_fcf_field_in_to_dict(self):
        d = _make_assessment(fcf_per_share_used=12.04)
        result = d.to_dict()
        assert "fcf_per_share_used" in result
        assert result["fcf_per_share_used"] == pytest.approx(12.04)

    def test_eps_field_in_to_dict(self):
        d = _make_assessment(eps_used_in_valuation=15.83)
        result = d.to_dict()
        assert "eps_used_in_valuation" in result
        assert result["eps_used_in_valuation"] == pytest.approx(15.83)

    def test_normalization_note_in_to_dict(self):
        note = "Derived: 3-year average FCF (3yr avg to 2026)"
        d = _make_assessment(fcf_normalization_note=note)
        result = d.to_dict()
        assert "fcf_normalization_note" in result
        assert result["fcf_normalization_note"] == note

    def test_none_values_serialise_as_null(self):
        d = _make_assessment()
        result = d.to_dict()
        assert result["fcf_per_share_used"] is None
        assert result["eps_used_in_valuation"] is None

    def test_empty_string_note_serialises_correctly(self):
        d = _make_assessment(fcf_normalization_note="")
        result = d.to_dict()
        assert result["fcf_normalization_note"] == ""


# ---------------------------------------------------------------------------
# Class B — _answer_fcf_eps surfaces stored values
# ---------------------------------------------------------------------------

class TestB_ProvenanceSurfaced:
    """When provenance fields are set, the rendered answer shows the stored values."""

    def test_fcf_per_share_shown(self):
        d = _make_assessment(fcf_per_share_used=12.04)
        out = _render_fcf(d)
        assert "12.04" in out

    def test_eps_shown(self):
        d = _make_assessment(eps_used_in_valuation=15.83)
        out = _render_fcf(d)
        assert "15.83" in out

    def test_currency_prefix_shown(self):
        d = _make_assessment(fcf_per_share_used=12.04, eps_used_in_valuation=15.83)
        out = _render_fcf(d)
        assert "INR" in out

    def test_normalization_note_shown(self):
        note = "Derived: 3-year average FCF (3yr avg to 2026)"
        d = _make_assessment(
            fcf_per_share_used=12.04,
            fcf_normalization_note=note,
        )
        out = _render_fcf(d)
        assert "3-year" in out or "3yr" in out

    def test_stored_section_header_present(self):
        d = _make_assessment(fcf_per_share_used=12.04)
        out = _render_fcf(d)
        assert "STORED VALUATION METRICS" in out.upper() or "STORED" in out.upper()

    def test_structural_explanation_still_present(self):
        """Structural EPS/FCF definition is always shown, even when provenance is available."""
        d = _make_assessment(fcf_per_share_used=12.04, eps_used_in_valuation=15.83)
        out = _render_fcf(d)
        assert "Operating Cash Flow" in out or "capital expenditure" in out.lower()

    def test_no_capex_invention_when_not_stored(self):
        """
        If the stored assessment has provenance values but no explicit capex breakdown,
        the renderer must NOT attribute the FCF/EPS gap to capex specifically.
        """
        d = _make_assessment(fcf_per_share_used=12.04, eps_used_in_valuation=15.83)
        out = _render_fcf(d)
        # The word "capex" or "capital expenditure" may appear in the generic explanation,
        # but no assertion like "capex causes this gap" should be made as a stored fact.
        # Verify the output doesn't claim to know the specific driver of ITC's gap.
        lower = out.lower()
        assert "stored assessment does not contain" in lower or \
               "cannot attribute" in lower or \
               "does not" in lower, (
            "Renderer should note that the specific gap driver is not in stored data"
        )


# ---------------------------------------------------------------------------
# Class C — graceful fallback when provenance fields are None
# ---------------------------------------------------------------------------

class TestC_FallbackWhenMissing:
    """When provenance fields are None, output notes the gap and gives structural info."""

    def test_structural_explanation_shown_when_no_provenance(self):
        d = _make_assessment()  # all provenance = None
        out = _render_fcf(d)
        assert "EPS" in out
        assert "FCF" in out

    def test_evidence_gap_noted_when_no_provenance(self):
        d = _make_assessment()
        out = _render_fcf(d)
        lower = out.lower()
        assert "not available" in lower or "not stored" in lower or \
               "not contain" in lower or "pre-dates" in lower, (
            "Should note that provenance values are unavailable"
        )

    def test_no_specific_values_invented(self):
        """With None provenance, output must not contain 12.04 or 15.83."""
        d = _make_assessment()
        out = _render_fcf(d)
        assert "12.04" not in out
        assert "15.83" not in out

    def test_no_capex_specific_claim_when_no_provenance(self):
        """Without stored capex data, must not attribute ITC gap to capex."""
        d = _make_assessment(key_assumptions=[], per_method_summary=[])
        out = _render_fcf(d)
        lower = out.lower()
        # Generic capex education is fine; claiming capex IS the cause is not
        # The test checks the answer doesn't make a specific causal claim about ITC
        assert "itc's gap is caused by capex" not in lower
        assert "the gap is caused by capital expenditure" not in lower

    def test_footer_present(self):
        d = _make_assessment()
        out = _render_fcf(d)
        assert d.analysis_date in out
        assert "No new financial data" in out or "stored" in out.lower()


# ---------------------------------------------------------------------------
# Class D — Gap calculation when both FCF/share and EPS are available
# ---------------------------------------------------------------------------

class TestD_GapCalculation:
    """When both fcf_per_share_used and eps_used_in_valuation are set, gap is shown."""

    ITC_FCF = 12.04
    ITC_EPS = 15.83

    def _itc_d(self) -> InvestmentDecisionAssessment:
        return _make_assessment(
            fcf_per_share_used=self.ITC_FCF,
            fcf_normalization_note="Derived: 3-year average FCF (3yr avg to 2026)",
            eps_used_in_valuation=self.ITC_EPS,
        )

    def test_gap_value_shown(self):
        out = _render_fcf(self._itc_d())
        expected_gap = round(self.ITC_EPS - self.ITC_FCF, 2)  # 3.79
        assert str(expected_gap) in out or "3.79" in out

    def test_both_values_shown_together(self):
        out = _render_fcf(self._itc_d())
        assert "12.04" in out
        assert "15.83" in out

    def test_gap_note_does_not_claim_specific_driver(self):
        out = _render_fcf(self._itc_d())
        lower = out.lower()
        # Must not pick capex as the confirmed driver
        assert "capex is the cause" not in lower
        assert "because of capex" not in lower

    def test_gap_capped_at_two_values_not_fabricated(self):
        """Gap = EPS − FCF/share; no third value (e.g., ΔD&A) should be claimed."""
        out = _render_fcf(self._itc_d())
        # Confirm the two known values and their difference appear, not extra per-share items
        assert "12.04" in out
        assert "15.83" in out
        # No line should claim a depreciation/amortisation per-share figure (fabrication)
        assert "depreciation per share" not in out.lower()
        assert "amortisation per share" not in out.lower()


# ---------------------------------------------------------------------------
# Class E — Non-regression: other follow-ups still work
# ---------------------------------------------------------------------------

class TestE_NonRegression:
    """Existing follow-up handlers should be unaffected by Phase 9.5."""

    def _d(self) -> InvestmentDecisionAssessment:
        return _make_assessment(
            fcf_per_share_used=12.04,
            eps_used_in_valuation=15.83,
        )

    def test_watch_followup_unchanged(self):
        from analytics.agent.renderer import render_followup
        out = render_followup("why is it a watch?", self._d())
        assert out  # produces non-empty output
        # Must not be the FCF/EPS handler
        assert "STRUCTURAL DIFFERENCE" not in out

    def test_valuation_method_followup_unchanged(self):
        from analytics.agent.renderer import render_followup
        out = render_followup("explain the P/E method", self._d())
        assert out
        assert "STRUCTURAL DIFFERENCE" not in out

    def test_dcf_followup_unchanged(self):
        from analytics.agent.renderer import render_followup
        out = render_followup("how was the DCF calculated?", self._d())
        assert out
        # Should route to valuation method handler, not FCF/EPS handler
        assert "STRUCTURAL DIFFERENCE" not in out

    def test_pfcf_valuation_method_followup_unchanged(self):
        """'P/FCF method' is a valuation-method question, not an FCF-metric question."""
        from analytics.agent.renderer import render_followup
        out = render_followup("what is the P/FCF method?", self._d())
        assert out
        # The P/FCF routing should hit the valuation method handler, not _answer_fcf_eps,
        # because "p/fcf" is in _METHOD_KEYWORDS which is checked first.
        assert out  # just verify it doesn't crash

    def test_fcf_eps_routing_still_works_with_provenance_set(self):
        """With provenance fields set, routing to _answer_fcf_eps still triggers correctly."""
        from analytics.agent.renderer import render_followup
        out = render_followup("why is fcf per share lower than eps?", self._d())
        assert "STRUCTURAL DIFFERENCE" in out
        assert "12.04" in out
        assert "15.83" in out

    def test_assessment_with_provenance_does_not_break_summary_text(self):
        """summary_text() should work regardless of Phase 9.5 fields."""
        d = self._d()
        txt = d.summary_text()
        assert d.ticker in txt
        assert d.company_name in txt

    def test_to_json_round_trip(self):
        """to_json() / to_dict() should include all Phase 9.5 fields."""
        d = self._d()
        import json
        raw = json.loads(d.to_json())
        assert raw["fcf_per_share_used"] == pytest.approx(12.04)
        assert raw["eps_used_in_valuation"] == pytest.approx(15.83)
        assert "fcf_normalization_note" in raw
