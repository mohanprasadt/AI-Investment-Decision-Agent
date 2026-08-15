"""
Phase 9.4 Regression Tests — Valuation Transparency + Recommendation Consistency
==================================================================================
Two fix areas:

Fix 1 — Per-method valuation transparency
  * InvestmentDecisionAssessment now carries per_method_valuation_summary: List[str]
  * Each entry describes one valuation method (bear/mid/bull, reliability, weight,
    price comparison).
  * Final entry is a weighted-average summary line.

Fix 2 — WAIT-zone recommended_next_step consistency
  * When action=WATCH and zone=WAIT, the next step must NOT say
    "Set a price alert at the START_SMALL threshold."
  * When action=WATCH and zone is NOT WAIT, the alert-at-threshold
    wording is preserved.

Run:  pytest tests/test_phase94.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataclasses import field as dc_field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_valuation_assessment(
    *,
    dcf_mid: float = 200.0,
    pe_mid: float = 220.0,
    ev_mid: float = 240.0,
    pfcf_mid: float = 210.0,
    base_fv: float = 220.0,
    zone: str = "WAIT",
):
    """
    Build a minimal ValuationAssessment suitable for unit tests.
    Uses synthetic values — no live data needed.
    """
    from analytics.valuation.valuation_models import (
        ValuationAssessment, FairValueRange, AccumulationZone,
        AccumulationZoneLabel, MethodReliability, DCFResult,
        MultipleValuationResult, MethodApplicability, ValuationConfidence,
        ValuationMethod,
    )

    def _dcf(mid):
        r = DCFResult()
        r.base_value = mid
        r.bear_value = mid * 0.85
        r.bull_value = mid * 1.15
        r.reliability = MethodReliability.LOW
        r.is_applicable = True
        return r

    def _mult(mid, rel=MethodReliability.MEDIUM, method=ValuationMethod.NORMALIZED_PE):
        r = MultipleValuationResult(method=method)
        r.implied_value_mid  = mid
        r.implied_value_low  = mid * 0.85
        r.implied_value_high = mid * 1.15
        r.reliability = rel
        r.is_applicable = True
        return r

    zone_label = AccumulationZoneLabel[zone] if isinstance(zone, str) else zone
    az = AccumulationZone(
        zone=zone_label,
        current_price=300.0,
        current_price_currency="INR",
        fair_value_base=base_fv,
        required_margin_of_safety_pct=0.15,
        actual_margin_of_safety_pct=None,
    )

    fvr = FairValueRange(bear=base_fv * 0.85, base=base_fv, bull=base_fv * 1.15)

    va = ValuationAssessment(
        ticker="TEST.NS",
        company_name="Test Corp",
        valuation_date="2026-08-10",
        currency="INR",
    )
    va.dcf_result           = _dcf(dcf_mid)
    va.normalized_pe_result = _mult(pe_mid,   MethodReliability.LOW,    ValuationMethod.NORMALIZED_PE)
    va.ev_ebitda_result     = _mult(ev_mid,   MethodReliability.MEDIUM, ValuationMethod.EV_EBITDA)
    va.price_to_fcf_result  = _mult(pfcf_mid, MethodReliability.MEDIUM, ValuationMethod.PRICE_TO_FCF)
    va.fair_value_range     = fvr
    va.accumulation_zone    = az
    va.overall_confidence   = ValuationConfidence.MEDIUM
    return va


def _make_decision(
    *,
    zone: str = "WAIT",
    current_price: float = 282.65,
    currency: str = "INR",
    action_override=None,
):
    """
    Run make_investment_decision with synthetic valuation data.
    Supplies no research (→ WATCH or WAIT_INSUFFICIENT_EVIDENCE based on gates).
    action_override is not used — we test the actual engine output.
    """
    from analytics.decision.decision_synthesizer import make_investment_decision

    va = _make_valuation_assessment(zone=zone, base_fv=200.0)
    return make_investment_decision(
        ticker="TEST.NS",
        company_name="Test Corp",
        analysis_date="2026-08-10",
        valuation=va,
        current_price=current_price,
        price_currency=currency,
    )


# ---------------------------------------------------------------------------
# Class A — _build_method_summary unit tests (pure function)
# ---------------------------------------------------------------------------

class TestA_BuildMethodSummary:
    """Direct unit tests of _build_method_summary."""

    def _run(self, zone="WAIT", price=282.65, currency="INR"):
        from analytics.decision.decision_synthesizer import _build_method_summary
        va = _make_valuation_assessment(zone=zone)
        return _build_method_summary(va, price, currency)

    def test_returns_list_not_empty(self):
        lines = self._run()
        assert isinstance(lines, list)
        assert len(lines) > 0, "Expected at least one line in method summary"

    def test_dcf_line_present(self):
        lines = self._run()
        assert any("DCF" in l for l in lines), "DCF line missing from summary"

    def test_pe_line_present(self):
        lines = self._run()
        assert any("P/E" in l for l in lines), "Normalised P/E line missing"

    def test_ev_ebitda_line_present(self):
        lines = self._run()
        assert any("EV/EBITDA" in l for l in lines), "EV/EBITDA line missing"

    def test_pfcf_line_present(self):
        lines = self._run()
        assert any("P/FCF" in l for l in lines), "P/FCF line missing"

    def test_weighted_average_line_present(self):
        lines = self._run()
        assert any("Weighted average" in l for l in lines), (
            "Weighted average summary line missing"
        )

    def test_price_comparison_in_line(self):
        lines = self._run(price=282.65, currency="INR")
        # At least one method line should contain "above" or "below"
        has_comparison = any(
            ("above" in l or "below" in l)
            for l in lines
            if "Weighted average" not in l
        )
        assert has_comparison, "No price comparison (above/below) found in method lines"

    def test_reliability_weight_shown(self):
        lines = self._run()
        method_lines = [l for l in lines if "Weighted average" not in l]
        assert all("reliability:" in l and "weight:" in l for l in method_lines), (
            "reliability or weight missing from a method line"
        )

    def test_none_valuation_returns_empty(self):
        from analytics.decision.decision_synthesizer import _build_method_summary
        assert _build_method_summary(None, 100.0, "INR") == []

    def test_no_fabrication_when_method_invalid(self):
        """When a method's is_valid() returns False, it must not appear in summary."""
        from analytics.decision.decision_synthesizer import _build_method_summary
        from analytics.valuation.valuation_models import (
            ValuationAssessment, FairValueRange, AccumulationZone,
            AccumulationZoneLabel, MethodReliability, ValuationConfidence,
            ValuationMethod,
        )

        va = ValuationAssessment(
            ticker="X", company_name="Empty", valuation_date="2026-01-01", currency="INR"
        )
        va.dcf_result           = None   # no DCF
        va.normalized_pe_result = None
        va.ev_ebitda_result     = None
        va.price_to_fcf_result  = None
        va.fair_value_range     = None
        va.accumulation_zone    = AccumulationZone(
            zone=AccumulationZoneLabel.WAIT,
            current_price=100.0,
            current_price_currency="INR",
            fair_value_base=80.0,
            required_margin_of_safety_pct=0.15,
            actual_margin_of_safety_pct=None,
        )
        va.overall_confidence   = ValuationConfidence.LOW

        result = _build_method_summary(va, 100.0, "INR")
        assert result == [], (
            "No methods valid → summary must be empty, not fabricated"
        )


# ---------------------------------------------------------------------------
# Class B — per_method_valuation_summary field in InvestmentDecisionAssessment
# ---------------------------------------------------------------------------

class TestB_FieldPopulation:
    """Confirm the field is populated by make_investment_decision."""

    def test_field_exists_on_model(self):
        from analytics.decision.decision_models import InvestmentDecisionAssessment
        d = InvestmentDecisionAssessment(
            ticker="X", company_name="Y", analysis_date="2026-01-01"
        )
        assert hasattr(d, "per_method_valuation_summary")
        assert isinstance(d.per_method_valuation_summary, list)

    def test_field_populated_when_valuation_provided(self):
        d = _make_decision(zone="WAIT", current_price=282.65)
        assert len(d.per_method_valuation_summary) > 0, (
            "per_method_valuation_summary must be non-empty when valuation is provided"
        )

    def test_field_empty_when_no_valuation(self):
        from analytics.decision.decision_synthesizer import make_investment_decision
        d = make_investment_decision(
            ticker="X",
            company_name="No-Val Corp",
            analysis_date="2026-01-01",
            valuation=None,
            current_price=100.0,
        )
        assert d.per_method_valuation_summary == [], (
            "per_method_valuation_summary must be empty when no valuation supplied"
        )

    def test_field_in_to_dict(self):
        d = _make_decision(zone="WAIT", current_price=282.65)
        d_dict = d.to_dict()
        assert "per_method_valuation_summary" in d_dict
        assert isinstance(d_dict["per_method_valuation_summary"], list)

    def test_weighted_avg_last_entry(self):
        d = _make_decision(zone="WAIT", current_price=282.65)
        summary = d.per_method_valuation_summary
        if len(summary) >= 2:
            assert "Weighted average" in summary[-1], (
                "Last summary entry should be the weighted-average line"
            )


# ---------------------------------------------------------------------------
# Class C — recommended_next_step WAIT-zone consistency
# ---------------------------------------------------------------------------

class TestC_NextStepZoneConsistency:
    """Verify WAIT-zone next_step does not contain START_SMALL alert language."""

    def _next_step_for_zone(self, zone: str, price: float = 282.65):
        from analytics.decision.decision_synthesizer import _recommended_next_step
        from analytics.decision.decision_models import DecisionAction, ThesisBreaker
        # Simulate the WATCH action with the given zone
        return _recommended_next_step(
            DecisionAction.WATCH,
            is_existing=False,
            portfolio_ctx=None,
            thesis_breakers=[],
            val_zone=zone,
        )

    def test_wait_zone_no_start_small_alert(self):
        """WAIT zone → next_step must NOT say 'Set a price alert at the START_SMALL threshold'."""
        text = self._next_step_for_zone("WAIT")
        assert "START_SMALL threshold" not in text, (
            f"WAIT zone should not mention START_SMALL threshold. Got:\n{text}"
        )

    def test_wait_zone_mentions_pullback_or_fair_value(self):
        """WAIT zone → next_step should mention waiting for a pullback or fair value."""
        text = self._next_step_for_zone("WAIT")
        assert "pullback" in text.lower() or "fair value" in text.lower(), (
            f"WAIT zone next_step should reference pullback/fair value. Got:\n{text}"
        )

    def test_non_wait_zone_preserves_alert_language(self):
        """Non-WAIT zone (e.g. WATCH) keeps the original START_SMALL alert wording."""
        text = self._next_step_for_zone("WATCH")
        assert "START_SMALL threshold" in text, (
            f"Non-WAIT zone should retain START_SMALL threshold language. Got:\n{text}"
        )

    def test_accumulate_zone_preserves_alert_language(self):
        """ACCUMULATE zone → still uses original WATCH language."""
        text = self._next_step_for_zone("ACCUMULATE")
        assert "START_SMALL threshold" in text, (
            f"ACCUMULATE zone should retain START_SMALL threshold language. Got:\n{text}"
        )

    def test_start_small_action_unchanged(self):
        """START_SMALL action is not affected by zone — its text should not change."""
        from analytics.decision.decision_synthesizer import _recommended_next_step
        from analytics.decision.decision_models import DecisionAction
        wait_text = _recommended_next_step(
            DecisionAction.START_SMALL, False, None, [], "WAIT"
        )
        non_wait_text = _recommended_next_step(
            DecisionAction.START_SMALL, False, None, [], "ACCUMULATE"
        )
        assert wait_text == non_wait_text, (
            "START_SMALL action text should not vary by zone"
        )

    def test_accumulate_action_unchanged(self):
        """ACCUMULATE action is not affected by zone."""
        from analytics.decision.decision_synthesizer import _recommended_next_step
        from analytics.decision.decision_models import DecisionAction
        wait_text = _recommended_next_step(
            DecisionAction.ACCUMULATE, False, None, [], "WAIT"
        )
        non_wait_text = _recommended_next_step(
            DecisionAction.ACCUMULATE, False, None, [], "ACCUMULATE"
        )
        assert wait_text == non_wait_text, (
            "ACCUMULATE action text should not vary by zone"
        )

    def test_pipeline_wait_zone_next_step_correct(self):
        """
        Full pipeline: a WAIT-zone decision must not have START_SMALL threshold
        language in its recommended_next_step field.
        """
        d = _make_decision(zone="WAIT", current_price=282.65)
        # The action may not be WATCH if quality gates intervene, but if it is WATCH
        # the next_step wording must be zone-appropriate.
        from analytics.decision.decision_models import DecisionAction
        if d.action == DecisionAction.WATCH:
            assert "START_SMALL threshold" not in d.recommended_next_step, (
                f"WATCH + WAIT zone must not say 'START_SMALL threshold'. Got:\n"
                f"{d.recommended_next_step}"
            )


# ---------------------------------------------------------------------------
# Class D — renderer integration
# ---------------------------------------------------------------------------

class TestD_RendererIntegration:
    """Confirm _answer_valuation renders the per-method breakdown."""

    def test_answer_valuation_renders_method_section(self):
        from analytics.agent.renderer import _answer_valuation
        from analytics.decision.decision_models import InvestmentDecisionAssessment, DecisionAction
        d = InvestmentDecisionAssessment(
            ticker="TEST",
            company_name="Test Corp",
            analysis_date="2026-08-10",
            action=DecisionAction.WATCH,
            per_method_valuation_summary=[
                "DCF: bear 170.00 | mid 200.00 | bull 230.00  [reliability: LOW, weight: 0.3] (29.2% below current price INR 282.65)",
                "EV/EBITDA: bear 204.00 | mid 240.00 | bull 276.00  [reliability: MEDIUM, weight: 0.6] (15.1% below current price INR 282.65)",
                "Weighted average fair value: bear 187.00 | base 220.00 | bull 253.00 (22.2% below current price INR 282.65)",
            ],
            valuation_conclusion="Price is above estimated fair value.",
        )
        rendered = _answer_valuation(d)
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in rendered
        assert "DCF" in rendered
        assert "EV/EBITDA" in rendered
        assert "Weighted average" in rendered

    def test_answer_valuation_skips_section_when_empty(self):
        from analytics.agent.renderer import _answer_valuation
        from analytics.decision.decision_models import InvestmentDecisionAssessment, DecisionAction
        d = InvestmentDecisionAssessment(
            ticker="TEST",
            company_name="Test Corp",
            analysis_date="2026-08-10",
            action=DecisionAction.WATCH,
            per_method_valuation_summary=[],  # empty
            valuation_conclusion="No valuation data.",
        )
        rendered = _answer_valuation(d)
        assert "PER-METHOD FAIR VALUE BREAKDOWN" not in rendered
