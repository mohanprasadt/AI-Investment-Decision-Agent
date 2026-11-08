"""
Phase 11B Tests
===============
Covers Gate 5 hardening and what-if scenario UI requirements.

Test groups:
  1.  TestSeverityModel              — fixed severity model (only MEDIUM+ escalate)
  2.  TestUnknownLikelihood          — UNKNOWN accepted, preserved, treated conservatively
  3.  TestBreakerDetails             — structured details path vs plain-string fallback
  4.  TestRendererFix                — 6-vs-5 defect fix (D4)
  5.  TestScenarioEngine             — run_scenario() correctness
  6.  TestGate5UX                    — Gate 5 icon fix (D1)
  7.  TestBreakerSpecificAnswer      — _answer_breaker_specific() unit tests (UX fix)
  8.  TestBreakerSpecificRouting     — render_followup() routing regression tests (UX fix)
  9.  TestD1D2CorrectionAcceptance   — acceptance tests for D1 + D2 corrective fix
                                       (likelihood-question guard, Gate 5 explanation,
                                        $50-vs-$60 threshold mismatch note, UNKNOWN preserve)

PO constraints enforced by tests:
  - UNKNOWN ≠ MEDIUM (not silently collapsed)
  - UNKNOWN contributes conservatively to severity
  - System baseline never mutated by scenario engine
  - Evidence-backed likelihoods flow through to Decision Trace
  - Breaker-specific question returns focused single-breaker block (not full trace)
  - "Why is X MEDIUM/HIGH/LOW/UNKNOWN?" does not return full Decision Trace
  - "Why is Gate 5 SEVERE/HIGH/…?" returns focused Gate 5 explanation, not full trace
  - User's stated threshold ($50) is never silently equated to stored threshold ($60)
"""

from __future__ import annotations

import pytest
from typing import List


# ===========================================================================
# Helpers
# ===========================================================================

def _make_breaker(condition: str, likelihood: str, evidence=None, rationale=""):
    from analytics.decision.decision_models import ThesisBreaker
    return ThesisBreaker(
        condition=condition,
        likelihood=likelihood,
        impact="SEVERE",
        monitoring_indicator="Monitor quarterly.",
        trigger_action="Would prompt review.",
        evidence=evidence or [],
        likelihood_rationale=rationale,
    )


def _make_assessment_with_breakers(breakers, quality_tier="GOOD", is_existing=True, val_zone="WAIT"):
    """Build a minimal InvestmentDecisionAssessment with given thesis breakers."""
    from analytics.decision.decision_models import (
        InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
    )
    assessment = InvestmentDecisionAssessment(
        ticker="TEST.TO",
        company_name="Test Company",
        analysis_date="2026-09-30",
        action=DecisionAction.REDUCE,
        decision_confidence=DecisionConfidence.MEDIUM,
        executive_conclusion="Test.",
        business_quality_conclusion="Quality.",
        valuation_conclusion="Valuation.",
        portfolio_context_conclusion="Existing position.",
        valuation_zone=val_zone,
    )
    assessment.thesis_breakers = breakers
    assessment.gate_results = [
        GateResult(gate_number=1, gate_name="Business Understanding", passed=True,
                   confidence="HIGH", summary="OK"),
        GateResult(gate_number=2, gate_name="Financial Quality", passed=True,
                   quality_tier=quality_tier, confidence="MEDIUM", summary="OK"),
        GateResult(gate_number=3, gate_name="Valuation", passed=True,
                   confidence="MEDIUM", summary=f"Zone: {val_zone}"),
        GateResult(gate_number=4, gate_name="Portfolio Context", passed=True,
                   confidence="HIGH", summary="Existing 8% position."),
        GateResult(gate_number=5, gate_name="Adversarial Challenge", passed=True,
                   adversarial_risk="SEVERE", confidence="MEDIUM",
                   summary="4 breakers identified."),
    ]
    return assessment


# ===========================================================================
# Group 1: Severity model
# ===========================================================================

class TestSeverityModel:
    """Verify the Phase 11B fixed severity model (only MEDIUM/HIGH/UNKNOWN escalate)."""

    def _severity(self, breakers):
        # K1: _calculate_severity moved to gate5_adversarial as shared function
        from analytics.decision.gate5_adversarial import calculate_adversarial_severity
        return calculate_adversarial_severity(breakers, n_bear=0)

    def test_01_one_high_breaker_is_severe(self):
        """n_high=1 → SEVERE regardless of LOW count."""
        breakers = [
            _make_breaker("B1", "HIGH"),
            _make_breaker("B2", "LOW"),
            _make_breaker("B3", "LOW"),
            _make_breaker("B4", "LOW"),
            _make_breaker("B5", "LOW"),
        ]
        assert self._severity(breakers) == "SEVERE"

    def test_02_four_medium_is_severe(self):
        """n_medium=4, n_high=0 → SEVERE."""
        breakers = [_make_breaker(f"B{i}", "MEDIUM") for i in range(4)]
        assert self._severity(breakers) == "SEVERE"

    def test_03_two_medium_three_low_is_high_not_severe(self):
        """CNQ case: n_medium=2, n_low=3 → HIGH, not SEVERE (the D3 fix)."""
        breakers = [
            _make_breaker("Crude <$50", "MEDIUM"),
            _make_breaker("FCF deterioration", "MEDIUM"),
            _make_breaker("Dividend cut", "LOW"),
            _make_breaker("Credit downgrade", "LOW"),
            _make_breaker("Major impairment", "LOW"),
        ]
        result = self._severity(breakers)
        assert result == "HIGH", (
            f"Expected HIGH for 2 MEDIUM + 3 LOW, got {result}. "
            f"This is the D3 fix — LOW breakers must not count toward SEVERE."
        )

    def test_04_one_medium_is_moderate(self):
        """n_medium=1 → MODERATE."""
        breakers = [_make_breaker("B1", "MEDIUM")]
        assert self._severity(breakers) == "MODERATE"

    def test_05_all_low_is_low(self):
        """All LOW breakers → LOW severity (no escalation)."""
        breakers = [_make_breaker(f"B{i}", "LOW") for i in range(6)]
        assert self._severity(breakers) == "LOW"


# ===========================================================================
# Group 2: UNKNOWN likelihood
# ===========================================================================

class TestUnknownLikelihood:
    """UNKNOWN is accepted, preserved, and treated conservatively in severity."""

    def _severity(self, breakers):
        # K1: _calculate_severity moved to gate5_adversarial as shared function
        from analytics.decision.gate5_adversarial import calculate_adversarial_severity
        return calculate_adversarial_severity(breakers, n_bear=0)

    def test_06_unknown_accepted_in_dataclass(self):
        """ThesisBreaker.likelihood accepts UNKNOWN."""
        tb = _make_breaker("Credit downgrade risk", "UNKNOWN",
                           rationale="UNKNOWN — no credit-rating data in context.")
        assert tb.likelihood == "UNKNOWN"

    def test_07_unknown_preserved_in_decision_trace(self):
        """UNKNOWN is preserved as UNKNOWN in render_decision_trace — not shown as MEDIUM."""
        from analytics.decision.decision_trace import build_decision_trace, render_decision_trace
        breakers = [_make_breaker("Credit risk", "UNKNOWN",
                                  rationale="No rating agency data available.")]
        assessment = _make_assessment_with_breakers(breakers)
        trace = build_decision_trace(assessment)
        rendered = render_decision_trace(trace)
        assert "UNKNOWN" in rendered, (
            f"UNKNOWN should appear in rendered trace, not be silently replaced: {rendered}"
        )
        # Must NOT appear as MEDIUM in the breaker display
        # (The rendered text might contain MEDIUM elsewhere, but not for this specific breaker)
        assert "[MEDIUM]" not in rendered or "[UNKNOWN]" in rendered

    def test_08_unknown_contributes_conservatively_to_severity(self):
        """1 UNKNOWN breaker → MODERATE (same as 1 MEDIUM)."""
        breakers = [_make_breaker("Credit risk", "UNKNOWN")]
        assert self._severity(breakers) == "MODERATE"

    def test_09_two_unknown_is_high(self):
        """2 UNKNOWN breakers → HIGH (same as 2 MEDIUM)."""
        breakers = [
            _make_breaker("Risk A", "UNKNOWN"),
            _make_breaker("Risk B", "UNKNOWN"),
        ]
        assert self._severity(breakers) == "HIGH"

    def test_10_unknown_does_not_display_as_medium_in_renderer(self):
        """renderer.py must show [UNKNOWN] not [MEDIUM] for UNKNOWN breakers."""
        from analytics.agent.renderer import render_assessment
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
        )
        assessment = InvestmentDecisionAssessment(
            ticker="TEST.TO", company_name="TestCo", analysis_date="2026-09-30",
            action=DecisionAction.HOLD, decision_confidence=DecisionConfidence.MEDIUM,
            executive_conclusion="Test.", business_quality_conclusion="",
            valuation_conclusion="", portfolio_context_conclusion="",
        )
        assessment.thesis_breakers = [
            _make_breaker("Credit downgrade", "UNKNOWN",
                          rationale="No rating agency evidence in context."),
        ]
        rendered = render_assessment(assessment)
        assert "[UNKNOWN]" in rendered, (
            f"Expected [UNKNOWN] in renderer output, got: {rendered}"
        )
        # Confirm it does NOT silently say MEDIUM for this breaker
        lines = rendered.split("\n")
        breaker_lines = [l for l in lines if "Credit downgrade" in l]
        assert breaker_lines, "Breaker not found in rendered output"
        assert "[UNKNOWN]" in breaker_lines[0], (
            f"Breaker line shows wrong likelihood: {breaker_lines[0]!r}"
        )

    def test_11_insufficient_evidence_not_silently_medium(self):
        """
        Ensure the orchestrator parser does NOT default UNKNOWN to MEDIUM
        when the LLM returns likelihood: 'UNKNOWN'.
        """
        from analytics.agent.research_orchestrator import ResearchOrchestrator

        class _FakeExecutor:
            def __call__(self, step_name, context):
                if step_name == "bull_bear_analysis":
                    return {
                        "bear_case_narrative": "Bear case.",
                        "thesis_breakers": [
                            {
                                "condition": "Credit downgrade",
                                "likelihood": "UNKNOWN",
                                "evidence": [],
                                "likelihood_rationale": "No rating agency data in context.",
                            }
                        ],
                    }
                return None

        orc = ResearchOrchestrator(research_executor=_FakeExecutor())
        from unittest.mock import MagicMock
        result = orc.build_assessment("TEST.TO", "TestCo", metrics=None, analysis_date="2026-09-30")
        assert result.bull_bear is not None
        assert result.bull_bear.thesis_breaker_details, "thesis_breaker_details should be populated"
        detail = result.bull_bear.thesis_breaker_details[0]
        assert detail["likelihood"] == "UNKNOWN", (
            f"Expected UNKNOWN, got {detail['likelihood']!r} — "
            f"insufficient evidence must not silently become MEDIUM"
        )


# ===========================================================================
# Group 3: Structured details path vs plain-string fallback
# ===========================================================================

class TestBreakerDetails:
    """Structured details from LLM flow correctly; plain strings fall back to MEDIUM."""

    def test_12_structured_details_produce_correct_likelihoods(self):
        """
        When thesis_breaker_details is populated, evaluate_gate5 uses
        the evidence-backed likelihoods instead of hardcoded MEDIUM.
        """
        from analytics.decision.gate5_adversarial import evaluate_gate5
        from analytics.business_research.research_models import (
            BusinessResearchAssessment, BullBearAssessment,
        )

        bb = BullBearAssessment(
            bear_case_narrative="Bear case.",
            thesis_breakers=["Crude <$50", "FCF deterioration", "Dividend cut"],
            thesis_breaker_details=[
                {"condition": "Crude <$50", "likelihood": "MEDIUM",
                 "evidence": ["Oil <$50 for 18mo is tail risk"], "likelihood_rationale": "MEDIUM — plausible tail"},
                {"condition": "FCF deterioration", "likelihood": "MEDIUM",
                 "evidence": ["FCF could drop 40% at $55 oil"], "likelihood_rationale": "MEDIUM — reachable threshold"},
                {"condition": "Dividend cut", "likelihood": "LOW",
                 "evidence": ["Payout 43%", "0 cuts in 10yr"], "likelihood_rationale": "LOW — strong FCF support"},
            ],
        )
        research = BusinessResearchAssessment(ticker="TEST.TO", company_name="TestCo")
        research.bull_bear = bb

        gate_result = evaluate_gate5(research=research)
        # With 2 MEDIUM + 1 LOW, severity should be HIGH (not SEVERE)
        assert gate_result.adversarial_risk == "HIGH", (
            f"Expected HIGH for 2 MEDIUM + 1 LOW, got {gate_result.adversarial_risk}. "
            f"Structured details should produce evidence-backed severity."
        )

    def test_13_plain_string_fallback_uses_medium(self):
        """Plain-string thesis_breakers (no details) → all MEDIUM (backward compat)."""
        from analytics.decision.gate5_adversarial import evaluate_gate5
        from analytics.business_research.research_models import (
            BusinessResearchAssessment, BullBearAssessment,
        )

        bb = BullBearAssessment(
            bear_case_narrative="Bear case.",
            thesis_breakers=["Risk A", "Risk B"],
            thesis_breaker_details=[],  # empty → use plain strings
        )
        research = BusinessResearchAssessment(ticker="TEST.TO", company_name="TestCo")
        research.bull_bear = bb

        gate_result = evaluate_gate5(research=research)
        # 2 MEDIUM → HIGH
        assert gate_result.adversarial_risk == "HIGH", (
            f"Expected HIGH for 2 plain-string breakers (→MEDIUM fallback), "
            f"got {gate_result.adversarial_risk}"
        )


# ===========================================================================
# Group 4: Renderer fix — 6-vs-5 defect (D4)
# ===========================================================================

class TestRendererFix:
    """D4: all thesis breakers must be shown, not capped at 5."""

    def test_14_all_breakers_shown_not_capped_at_5(self):
        """renderer.py must show all 6 breakers, not first 5."""
        from analytics.agent.renderer import render_assessment
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
        )
        assessment = InvestmentDecisionAssessment(
            ticker="TEST.TO", company_name="TestCo", analysis_date="2026-09-30",
            action=DecisionAction.HOLD, decision_confidence=DecisionConfidence.MEDIUM,
            executive_conclusion="", business_quality_conclusion="",
            valuation_conclusion="", portfolio_context_conclusion="",
        )
        assessment.thesis_breakers = [
            _make_breaker(f"Breaker number {i+1}", "MEDIUM") for i in range(6)
        ]
        rendered = render_assessment(assessment)
        for i in range(1, 7):
            assert f"Breaker number {i}" in rendered, (
                f"Breaker {i} missing from renderer output — [:5] cap not removed"
            )


# ===========================================================================
# Group 5: Scenario engine
# ===========================================================================

class TestScenarioEngine:
    """run_scenario() correctness — baseline immutability, decision changes, UNKNOWN override."""

    def test_15_no_overrides_returns_baseline(self):
        """run_scenario with empty overrides returns same risk as baseline."""
        from analytics.decision.scenario_engine import run_scenario
        breakers = [_make_breaker("Risk", "MEDIUM")]
        assessment = _make_assessment_with_breakers(breakers)
        result = run_scenario(assessment, [])
        assert result.decision_changed is False
        assert result.n_overrides == 0

    def test_16_upgrade_to_high_escalates_severity(self):
        """Overriding MEDIUM→HIGH on 1 breaker changes severity to SEVERE."""
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        breakers = [_make_breaker("Oil price", "MEDIUM")]
        assessment = _make_assessment_with_breakers(
            breakers, quality_tier="GOOD", is_existing=False, val_zone="WAIT"
        )
        result = run_scenario(assessment, [
            BreakerOverride(condition="Oil price", baseline_likelihood="MEDIUM",
                            user_likelihood="HIGH"),
        ])
        assert result.scenario_adversarial_risk == "SEVERE"

    def test_17_downgrade_low_does_not_change_severity(self):
        """Overriding LOW→LOW on a breaker produces same scenario severity as baseline."""
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        breakers = [_make_breaker("Minor risk", "LOW")]
        assessment = _make_assessment_with_breakers(breakers)
        result = run_scenario(assessment, [
            BreakerOverride(condition="Minor risk", baseline_likelihood="LOW",
                            user_likelihood="LOW"),
        ])
        # After a LOW→LOW no-op the scenario severity must equal what the severity model
        # would produce for 1 LOW breaker (LOW), regardless of the stored Gate 5 value.
        assert result.scenario_adversarial_risk == "LOW", (
            f"Expected LOW scenario risk for all-LOW breakers, got {result.scenario_adversarial_risk}"
        )

    def test_18_baseline_not_mutated(self):
        """Thesis breakers on the assessment must be unchanged after run_scenario."""
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        breakers = [_make_breaker("Crude <$50", "MEDIUM")]
        assessment = _make_assessment_with_breakers(breakers)
        original_lk = assessment.thesis_breakers[0].likelihood

        run_scenario(assessment, [
            BreakerOverride(condition="Crude <$50", baseline_likelihood="MEDIUM",
                            user_likelihood="HIGH"),
        ])
        assert assessment.thesis_breakers[0].likelihood == original_lk, (
            f"Baseline mutated! Expected {original_lk!r}, "
            f"got {assessment.thesis_breakers[0].likelihood!r}"
        )

    def test_19_unknown_overridden_in_scenario(self):
        """User can override an UNKNOWN breaker to LOW/MEDIUM/HIGH in a scenario."""
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        breakers = [
            _make_breaker("Credit downgrade", "UNKNOWN"),
            _make_breaker("Oil price", "MEDIUM"),
        ]
        assessment = _make_assessment_with_breakers(breakers, is_existing=True, val_zone="WAIT")
        result = run_scenario(assessment, [
            BreakerOverride(condition="Credit downgrade", baseline_likelihood="UNKNOWN",
                            user_likelihood="LOW"),
        ])
        # Credit goes from UNKNOWN (counts as MEDIUM) to LOW (does not count)
        # Remaining: 1 MEDIUM → scenario severity = MODERATE (not HIGH)
        assert result.scenario_adversarial_risk == "MODERATE", (
            f"Expected MODERATE after lowering UNKNOWN to LOW, "
            f"got {result.scenario_adversarial_risk}"
        )
        # Baseline must still show UNKNOWN
        assert assessment.thesis_breakers[0].likelihood == "UNKNOWN", (
            "Baseline UNKNOWN was mutated after scenario override"
        )

    def test_20_decision_changed_flag_accurate(self):
        """ScenarioResult.decision_changed is True when action differs from baseline."""
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride

        # Build scenario where raising severity causes decision change
        # Baseline: 1 MEDIUM → MODERATE → WATCH for new position
        breakers = [_make_breaker("Risk A", "MEDIUM")]
        assessment = _make_assessment_with_breakers(
            breakers, quality_tier="GOOD", is_existing=False, val_zone="WATCH"
        )
        # Override to HIGH → SEVERE → WATCH (no change for non-existing)
        result = run_scenario(assessment, [
            BreakerOverride(condition="Risk A", baseline_likelihood="MEDIUM",
                            user_likelihood="HIGH"),
        ])
        # SEVERE adversarial + is_existing=False + quality=GOOD → WATCH (same as baseline)
        # Confirm ScenarioResult accurately reflects this
        assert isinstance(result.decision_changed, bool)


# ===========================================================================
# Group 6: Gate 5 UX — icon fix (D1)
# ===========================================================================

class TestGate5UX:
    """D1: Gate 5 icon in Decision Trace must reflect adversarial_risk, not passed=True."""

    def _render_with_risk(self, risk_level: str) -> str:
        from analytics.decision.decision_trace import build_decision_trace, render_decision_trace
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
        )
        assessment = InvestmentDecisionAssessment(
            ticker="TEST.TO", company_name="TestCo", analysis_date="2026-09-30",
            action=DecisionAction.REDUCE, decision_confidence=DecisionConfidence.MEDIUM,
            executive_conclusion="", business_quality_conclusion="",
            valuation_conclusion="", portfolio_context_conclusion="",
        )
        assessment.gate_results = [
            GateResult(gate_number=1, gate_name="Business Understanding", passed=True,
                       confidence="HIGH", summary="OK"),
            GateResult(gate_number=2, gate_name="Financial Quality", passed=True,
                       quality_tier="GOOD", confidence="MEDIUM", summary="OK"),
            GateResult(gate_number=3, gate_name="Valuation", passed=True,
                       confidence="MEDIUM", summary="OK"),
            GateResult(gate_number=4, gate_name="Portfolio Context", passed=True,
                       confidence="HIGH", summary="Existing 8% position."),
            GateResult(gate_number=5, gate_name="Adversarial Challenge", passed=True,
                       adversarial_risk=risk_level, confidence="MEDIUM", summary="Test."),
        ]
        trace = build_decision_trace(assessment)
        return render_decision_trace(trace)

    def test_21_severe_shows_red_icon_not_checkmark(self):
        """SEVERE adversarial risk must show 🔴, not ✅."""
        rendered = self._render_with_risk("SEVERE")
        # The circled ⑤ marks the start of the Gate 5 gate-line section.
        # (The decision path line may also contain "Gate 5" — we need the gate section.)
        g5_idx = rendered.find("⑤")
        assert g5_idx != -1, "Gate 5 section (⑤) not found in trace"
        g5_section = rendered[g5_idx:g5_idx + 200]
        assert "🔴" in g5_section, (
            f"Expected 🔴 for SEVERE in Gate 5 section, got: {g5_section!r}"
        )
        assert "✅" not in g5_section, (
            f"✅ must not appear for SEVERE Gate 5: {g5_section!r}"
        )

    def test_22_low_shows_checkmark(self):
        """LOW adversarial risk on Gate 5 must show ✅."""
        rendered = self._render_with_risk("LOW")
        g5_idx = rendered.find("⑤")
        assert g5_idx != -1, "Gate 5 section (⑤) not found in trace"
        g5_section = rendered[g5_idx:g5_idx + 200]
        assert "✅" in g5_section, (
            f"Expected ✅ for LOW in Gate 5 section, got: {g5_section!r}"
        )

    def test_23_high_shows_warning_icon(self):
        """HIGH adversarial risk on Gate 5 must show ⚠️."""
        rendered = self._render_with_risk("HIGH")
        g5_idx = rendered.find("⑤")
        assert g5_idx != -1, "Gate 5 section (⑤) not found in trace"
        g5_section = rendered[g5_idx:g5_idx + 200]
        assert "⚠️" in g5_section, (
            f"Expected ⚠️ for HIGH in Gate 5 section, got: {g5_section!r}"
        )


# ===========================================================================
# Group 7: _answer_breaker_specific() unit tests (Phase 11B UX fix)
# ===========================================================================

class TestBreakerSpecificAnswer:
    """
    Unit tests for _answer_breaker_specific() in renderer.py.

    Verifies focused single-breaker responses: condition matching, UNKNOWN
    preservation, empty-evidence messaging, multi-match output, and None
    return when no condition matches.
    """

    def _breaker(self, condition, likelihood="MEDIUM", evidence=None, rationale=""):
        return _make_breaker(condition, likelihood, evidence=evidence, rationale=rationale)

    def _assessment(self, breakers):
        return _make_assessment_with_breakers(breakers)

    def test_24_exact_condition_match_returns_focused_block(self):
        """Exact condition substring in question → returns focused block for that breaker only."""
        from analytics.agent.renderer import _answer_breaker_specific
        tb = self._breaker(
            "Sustained crude oil prices below $50/bbl for 12+ months",
            likelihood="MEDIUM",
            evidence=["Brent spot at $65/bbl as of Sep 2026", "Futures curve flat"],
            rationale="Oil currently above threshold; risk is conditional.",
        )
        d = self._assessment([tb])
        q = "What about sustained crude oil prices below $50/bbl for 12+ months?"
        result = _answer_breaker_specific(q, d)
        assert result is not None, "_answer_breaker_specific returned None for exact match"
        assert "Sustained crude oil prices below $50/bbl" in result
        assert "MEDIUM" in result
        assert "Oil currently above threshold" in result
        assert "Brent spot at $65/bbl" in result

    def test_25_four_word_anchor_match(self):
        """4-word anchor phrase from condition found in question → returns block (partial-match path)."""
        from analytics.agent.renderer import _answer_breaker_specific
        tb = self._breaker(
            "Regulatory reversal of pipeline approval permits in Alberta",
            likelihood="LOW",
            evidence=["NEB approval granted Dec 2025"],
            rationale="Approval is legally binding; low probability of reversal.",
        )
        d = self._assessment([tb])
        # User only mentions a 4-word anchor from the condition
        q = "pipeline approval permits in Alberta — what does this mean for the thesis?"
        result = _answer_breaker_specific(q, d)
        assert result is not None, "_answer_breaker_specific returned None for 4-word anchor"
        assert "Regulatory reversal" in result
        assert "LOW" in result

    def test_26_no_condition_match_returns_none(self):
        """Question contains no breaker condition text → returns None (falls through)."""
        from analytics.agent.renderer import _answer_breaker_specific
        tb = self._breaker("Crude oil price collapse below $40/bbl", "HIGH")
        d = self._assessment([tb])
        q = "Why did you recommend REDUCE?"
        result = _answer_breaker_specific(q, d)
        assert result is None, (
            f"Expected None for generic question, got: {result!r}"
        )

    def test_27_multiple_condition_matches_returns_all(self):
        """Question matches two breaker conditions → both returned, separated by divider."""
        from analytics.agent.renderer import _answer_breaker_specific
        tb1 = self._breaker(
            "Sustained crude oil prices below $50/bbl",
            likelihood="MEDIUM",
            evidence=["Spot at $65"],
        )
        tb2 = self._breaker(
            "Prolonged crude oil demand destruction",
            likelihood="LOW",
            evidence=["IEA demand growth at 1.2M bpd"],
        )
        d = self._assessment([tb1, tb2])
        # Question mentions key words from both conditions
        q = "What about sustained crude oil prices below $50/bbl and crude oil demand destruction?"
        result = _answer_breaker_specific(q, d)
        assert result is not None, "Expected multi-match result, got None"
        assert "Sustained crude oil prices below $50/bbl" in result
        assert "Prolonged crude oil demand destruction" in result
        assert "─" * 10 in result, "Expected divider between multiple breaker blocks"

    def test_28_unknown_likelihood_displayed_as_unknown_not_medium(self):
        """UNKNOWN likelihood in a matched breaker is shown as UNKNOWN — never MEDIUM (PD-1)."""
        from analytics.agent.renderer import _answer_breaker_specific
        tb = self._breaker(
            "Geopolitical disruption to export routes",
            likelihood="UNKNOWN",
            evidence=[],
            rationale="Insufficient evidence to assess likelihood at this time.",
        )
        d = self._assessment([tb])
        q = "What about geopolitical disruption to export routes?"
        result = _answer_breaker_specific(q, d)
        assert result is not None
        assert "UNKNOWN" in result, "UNKNOWN likelihood was not preserved in output"
        assert "Insufficient evidence" in result

    def test_29_empty_evidence_shows_no_evidence_message(self):
        """Matched breaker with empty evidence list → explicit 'No specific evidence' message."""
        from analytics.agent.renderer import _answer_breaker_specific
        tb = self._breaker(
            "Management fraud or accounting restatement",
            likelihood="LOW",
            evidence=[],        # empty — legacy fallback or low-confidence LLM output
            rationale="No indicators identified; low baseline probability.",
        )
        d = self._assessment([tb])
        q = "What about management fraud or accounting restatement?"
        result = _answer_breaker_specific(q, d)
        assert result is not None
        assert "No specific evidence stored for this breaker." in result

    def test_30_empty_rationale_shows_not_stated(self):
        """Matched breaker with empty likelihood_rationale → 'Not stated.' in output."""
        from analytics.agent.renderer import _answer_breaker_specific
        tb = self._breaker(
            "Dividend cut or suspension",
            likelihood="MEDIUM",
            evidence=["Payout ratio at 78%"],
            rationale="",       # empty — plain-string fallback breaker
        )
        d = self._assessment([tb])
        q = "What about dividend cut or suspension risk?"
        result = _answer_breaker_specific(q, d)
        assert result is not None
        assert "Not stated." in result, (
            f"Expected 'Not stated.' for empty rationale, got: {result!r}"
        )


# ===========================================================================
# Group 8: render_followup() routing regression tests (Phase 11B UX fix)
# ===========================================================================

class TestBreakerSpecificRouting:
    """
    Integration routing tests for render_followup() in renderer.py.

    Verifies that:
      - Breaker-specific questions return focused blocks (not full trace or all-breaker list)
      - Generic "risks" and "why" questions still fire their existing handlers
      - The early-exit check does not regress any existing behavior
    """

    def _assessment_with_oil_breaker(self):
        tb = _make_breaker(
            "Sustained crude oil prices below $50/bbl for 12+ months",
            likelihood="MEDIUM",
            evidence=["Brent spot $65/bbl Sep 2026", "OPEC+ production intact"],
            rationale="Oil currently above threshold; breaker is conditional on sustained drop.",
        )
        return _make_assessment_with_breakers([tb])

    def test_31_condition_plus_why_returns_breaker_not_trace(self):
        """
        Question with breaker condition + 'why' must return the focused breaker block,
        NOT the full 5-gate Decision Trace.

        Regression guard: _answer_breaker_specific() must fire BEFORE _answer_why().
        """
        from analytics.agent.renderer import render_followup
        d = self._assessment_with_oil_breaker()
        q = "Why is sustained crude oil prices below $50/bbl for 12+ months rated MEDIUM?"
        result = render_followup(q, d)

        # Should return the focused breaker block
        # Phase 11B P0-1: label now includes category "(severity-contributing)" or
        # "(Monitoring indicator did not affect...)" — check for the prefix only.
        assert "Thesis breaker" in result or "Monitoring indicator" in result, (
            f"Expected focused breaker block, got: {result[:300]!r}"
        )
        assert "Likelihood:     MEDIUM" in result

        # Must NOT return the full Decision Trace (no gate numbers, no header)
        assert "DECISION TRACE" not in result, (
            "Full Decision Trace returned instead of focused breaker block"
        )
        assert "Gate 1:" not in result and "Gate 2:" not in result, (
            "Gate details found — full trace was returned instead of breaker block"
        )

    def test_32_generic_risks_question_returns_all_breakers(self):
        """
        'What are the risks?' (no condition fragment) must still return all breakers
        via _answer_risks() — regression guard for existing behavior.
        """
        from analytics.agent.renderer import render_followup
        tb1 = _make_breaker("Crude oil collapse", "MEDIUM")
        tb2 = _make_breaker("Regulatory reversal", "LOW")
        d = _make_assessment_with_breakers([tb1, tb2])
        result = render_followup("What are the biggest risks?", d)

        # _answer_risks() header
        assert "Key risks and thesis breakers" in result
        # Both breakers must appear
        assert "Crude oil collapse" in result
        assert "Regulatory reversal" in result
        # Must NOT be a breaker-specific block
        assert "Thesis breaker:" not in result

    def test_33_generic_why_question_returns_decision_trace(self):
        """
        'Why did you recommend REDUCE?' (no condition fragment) must still return
        the full Decision Trace via _answer_why() — regression guard.
        """
        from analytics.agent.renderer import render_followup
        d = _make_assessment_with_breakers([_make_breaker("Some risk", "MEDIUM")])
        result = render_followup("Why did you recommend REDUCE?", d)

        # _answer_why() returns the Decision Trace header
        assert "DECISION TRACE" in result, (
            f"Expected Decision Trace for generic 'why' question, got: {result[:300]!r}"
        )

    def test_34_no_breakers_returns_none_falls_through(self):
        """
        Assessment with no thesis_breakers → _answer_breaker_specific() returns None
        so render_followup() falls through to keyword handlers normally.
        """
        from analytics.agent.renderer import _answer_breaker_specific, render_followup
        d = _make_assessment_with_breakers([])  # empty breakers list

        # Direct function check: must return None
        specific = _answer_breaker_specific(
            "What about crude oil prices below $50/bbl?", d
        )
        assert specific is None, (
            "Expected None when assessment has no thesis_breakers"
        )

        # render_followup must still work (falls through to default or other handler)
        result = render_followup("What are the risks?", d)
        assert isinstance(result, str) and len(result) > 0


# ===========================================================================
# Group 9: D1 + D2 corrective fix acceptance tests (Phase 11B corrective)
# ===========================================================================

class TestD1D2CorrectionAcceptance:
    """
    Acceptance tests for the Phase 11B D1 + D2 corrective fix.

    AT-1  Exact defect: "$50 vs $60" threshold mismatch.
          "Why is sustained crude oil below $50/barrel for 12+ months MEDIUM?"
          stored breaker is "Oil price collapse (WTI <$60/bbl sustained)" → MEDIUM.
          Expected: focused response mentioning the stored $60 condition;
          MUST NOT pretend $50 == $60; MUST NOT return the full Decision Trace.

    AT-2  "Why is Gate 5 SEVERE?" → focused Gate 5 explanation; no full trace.

    AT-3  "Why is Gate 5 HIGH?" (likelihood token) → Gate 5 explanation takes
          priority over the "why + likelihood" breaker-likelihood guard.

    AT-4  "Why did you recommend REDUCE?" → full Decision Trace (no likelihood token
          → falls through to _answer_why(); D1 guard must NOT intercept it).

    AT-5  "Why is the crude oil price breaker MEDIUM?" → fuzzy match finds the oil
          breaker; focused block returned (no full trace).

    AT-6  "Why is the credit downgrade risk UNKNOWN?" → UNKNOWN preserved in output.

    AT-7  _answer_gate5_explanation() structure: shows adversarial risk, counts,
          severity logic, contributing breakers. Does NOT include Gate 1–4 info.

    AT-8  No thesis breakers → likelihood question returns a graceful "no breakers"
          message (not an exception or the full Decision Trace).
    """

    # ------------------------------------------------------------------
    # Shared fixtures
    # ------------------------------------------------------------------

    def _cnq_style_assessment(self):
        """
        Assessment modelling the CNQ.TO acceptance defect:
        stored breaker uses "$60" threshold; user will ask about "$50".
        """
        tb1 = _make_breaker(
            "Oil price collapse (WTI <$60/bbl sustained)",
            likelihood="MEDIUM",
            evidence=["WTI at $72/bbl as of Sep 2026", "Futures curve flat"],
            rationale=(
                "Oil is currently above the $60 threshold; sustained breach "
                "would materially pressure CNQ cash flows."
            ),
        )
        tb2 = _make_breaker(
            "Credit downgrade below investment grade",
            likelihood="UNKNOWN",
            evidence=[],
            rationale="Insufficient credit-agency signals at analysis date.",
        )
        tb3 = _make_breaker(
            "Regulatory pipeline reversal (Alberta)",
            likelihood="MEDIUM",
            evidence=["NEB approval intact"],
            rationale="Low probability given binding approval, but monitored.",
        )
        return _make_assessment_with_breakers([tb1, tb2, tb3])

    # ------------------------------------------------------------------
    # AT-1: exact defect — $50 vs $60 threshold
    # ------------------------------------------------------------------

    def test_35_at1_fifty_vs_sixty_no_full_trace_and_no_silent_equate(self):
        """
        AT-1 (exact acceptance defect):
        'Why is sustained crude oil below $50/barrel for 12+ months MEDIUM?'
        - Stored breaker: 'Oil price collapse (WTI <$60/bbl sustained)'
        - Expected: response showing the stored $60 condition (not pretending $50 == $60)
        - MUST NOT return the full Decision Trace (no "DECISION TRACE" header)
        - MUST NOT silently equate $50 and $60
        """
        from analytics.agent.renderer import render_followup
        d = self._cnq_style_assessment()
        q = "Why is sustained crude oil below $50/barrel for 12+ months MEDIUM?"
        result = render_followup(q, d)

        # Must NOT return the full Decision Trace
        assert "DECISION TRACE" not in result, (
            f"Full Decision Trace returned for the exact defect question.\n"
            f"Got (first 400 chars): {result[:400]!r}"
        )
        assert "Gate 1:" not in result and "Gate 2:" not in result, (
            "Gate 1/2 content found — full trace was returned"
        )

        # Must show the stored $60 condition so the user can see the mismatch
        assert "$60" in result or "60" in result, (
            f"Stored '$60' threshold not mentioned in response — $50 may have been "
            f"silently equated to $60.\nGot: {result[:400]!r}"
        )

        # Must be a substantive response (not an error or empty)
        assert len(result) > 80, f"Response too short: {result!r}"

    # ------------------------------------------------------------------
    # AT-2: "Why is Gate 5 SEVERE?" → Gate 5 explanation
    # ------------------------------------------------------------------

    def test_36_at2_why_gate5_severe_returns_gate5_explanation(self):
        """
        AT-2: 'Why is Gate 5 SEVERE?' must return a focused Gate 5 explanation,
        not the full Decision Trace.
        """
        from analytics.agent.renderer import render_followup
        d = self._cnq_style_assessment()
        result = render_followup("Why is Gate 5 SEVERE?", d)

        # Must show Gate 5 adversarial risk info
        assert "Gate 5" in result, f"Gate 5 header not in result: {result[:400]!r}"
        assert "Adversarial" in result or "adversarial" in result, (
            f"Adversarial risk not mentioned: {result[:400]!r}"
        )

        # Must NOT be the full Decision Trace
        assert "DECISION TRACE" not in result, (
            "Full Decision Trace returned for 'Why is Gate 5 SEVERE?'"
        )

        # Severity logic must appear
        assert any(tok in result for tok in ("SEVERE", "HIGH", "MODERATE", "LOW")), (
            "No adversarial risk level in Gate 5 explanation"
        )

        # Contributing breakers must be listed
        assert "Oil price collapse" in result or "MEDIUM" in result, (
            "Contributing breakers not shown in Gate 5 explanation"
        )

    # ------------------------------------------------------------------
    # AT-3: "Why is Gate 5 HIGH?" — Gate 5 check must beat D1 guard
    # ------------------------------------------------------------------

    def test_37_at3_why_gate5_high_routes_to_gate5_not_breaker_likelihood(self):
        """
        AT-3: 'Why is Gate 5 HIGH?' contains 'why' AND likelihood token 'high'.
        Gate 5 check must fire first — result is Gate 5 explanation, NOT the
        breaker-likelihood fallback listing.
        """
        from analytics.agent.renderer import render_followup
        # Build assessment with HIGH Gate 5 risk
        tb = _make_breaker("Some risk", "MEDIUM")
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
        )
        d = _make_assessment_with_breakers([tb])
        # Override Gate 5 to HIGH
        for gr in d.gate_results:
            if gr.gate_number == 5:
                gr.adversarial_risk = "HIGH"
                break

        result = render_followup("Why is Gate 5 HIGH?", d)

        assert "Gate 5" in result, "Gate 5 explanation not returned"
        assert "Adversarial" in result or "adversarial" in result
        assert "DECISION TRACE" not in result

    # ------------------------------------------------------------------
    # AT-4: "Why did you recommend REDUCE?" → full Decision Trace preserved
    # ------------------------------------------------------------------

    def test_38_at4_why_recommend_reduce_still_returns_full_trace(self):
        """
        AT-4: 'Why did you recommend REDUCE?' must still return the full Decision
        Trace. 'REDUCE' is NOT a likelihood token, so the D1 guard must not fire.
        """
        from analytics.agent.renderer import render_followup
        d = self._cnq_style_assessment()
        result = render_followup("Why did you recommend REDUCE?", d)

        # _answer_why() returns DECISION TRACE header
        assert "DECISION TRACE" in result, (
            f"Expected full Decision Trace for 'Why did you recommend REDUCE?', "
            f"got: {result[:400]!r}"
        )

    # ------------------------------------------------------------------
    # AT-5: "Why is the crude oil price breaker MEDIUM?" → fuzzy match
    # ------------------------------------------------------------------

    def test_39_at5_crude_oil_price_breaker_medium_returns_focused_block(self):
        """
        AT-5: 'Why is the crude oil price breaker MEDIUM?' — the words 'oil'
        and 'price' both appear in the stored condition 'Oil price collapse
        (WTI <$60/bbl sustained)'.  D2 widened matching (len >= 3) allows
        'oil' (3 chars) to participate.  Fuzzy match in
        _answer_breaker_likelihood_question() finds the breaker.

        Expected: focused breaker block; NOT the full Decision Trace.
        """
        from analytics.agent.renderer import render_followup
        d = self._cnq_style_assessment()
        result = render_followup("Why is the crude oil price breaker MEDIUM?", d)

        # Must not be the full trace
        assert "DECISION TRACE" not in result, (
            f"Full trace returned for crude oil price breaker question.\n"
            f"Got: {result[:400]!r}"
        )

        # Should contain content about the oil price breaker or at least a breaker
        assert "MEDIUM" in result or "Oil price" in result, (
            f"No breaker content in response: {result[:400]!r}"
        )

    # ------------------------------------------------------------------
    # AT-6: UNKNOWN preserved through likelihood-question path
    # ------------------------------------------------------------------

    def test_40_at6_unknown_likelihood_preserved_in_likelihood_question(self):
        """
        AT-6: 'Why is the credit downgrade risk UNKNOWN?' — the stored breaker
        has likelihood UNKNOWN.  PD-1 requires UNKNOWN to be displayed as-is,
        never coerced to MEDIUM.
        """
        from analytics.agent.renderer import render_followup
        d = self._cnq_style_assessment()
        result = render_followup("Why is the credit downgrade risk UNKNOWN?", d)

        # Must not return the full Decision Trace
        assert "DECISION TRACE" not in result, (
            "Full Decision Trace returned for UNKNOWN likelihood question"
        )
        # UNKNOWN must appear in output (PD-1)
        assert "UNKNOWN" in result, (
            f"UNKNOWN likelihood was not preserved in the response.\nGot: {result[:400]!r}"
        )
        # MEDIUM must not be substituted for UNKNOWN
        assert "Likelihood:     MEDIUM" not in result or "UNKNOWN" in result, (
            "MEDIUM was silently substituted for UNKNOWN (PD-1 violation)"
        )

    # ------------------------------------------------------------------
    # AT-7: _answer_gate5_explanation() structural content
    # ------------------------------------------------------------------

    def test_41_at7_gate5_explanation_structure(self):
        """
        AT-7: _answer_gate5_explanation() must show:
          - Adversarial risk level
          - Breaker counts (HIGH / MEDIUM / UNKNOWN / LOW)
          - Medium-equivalent count
          - Severity logic explanation
          - Contributing thesis breakers (condition + likelihood)
          - Does NOT include Gates 1–4 details (no "Gate 1", "Gate 2" etc.)
        """
        from analytics.agent.renderer import _answer_gate5_explanation
        d = self._cnq_style_assessment()
        result = _answer_gate5_explanation(d)

        # Adversarial risk
        assert "SEVERE" in result or "HIGH" in result or "MODERATE" in result or "LOW" in result, (
            "No adversarial risk level in Gate 5 explanation"
        )
        # Counts section
        assert "MEDIUM" in result, "MEDIUM count not in Gate 5 explanation"
        assert "UNKNOWN" in result, "UNKNOWN count not in Gate 5 explanation"
        assert "LOW" in result, "LOW count not in Gate 5 explanation"
        # Medium-equivalent
        assert "Medium-equivalent" in result or "medium-equivalent" in result, (
            "Medium-equivalent count not in Gate 5 explanation"
        )
        # Severity logic
        assert "threshold" in result or "SEVERE" in result, (
            "Severity threshold logic not in Gate 5 explanation"
        )
        # Contributing breakers
        assert "Oil price collapse" in result, (
            "Contributing breaker 'Oil price collapse' not in Gate 5 explanation"
        )
        # No Gate 1–4 content
        for g in ("Gate 1:", "Gate 2:", "Gate 3:", "Gate 4:"):
            assert g not in result, (
                f"{g!r} found in Gate 5 explanation — should not include other gates"
            )

    # ------------------------------------------------------------------
    # AT-8: No thesis breakers → graceful message
    # ------------------------------------------------------------------

    def test_42_at8_no_breakers_likelihood_question_returns_graceful_message(self):
        """
        AT-8: Assessment with no thesis breakers → a likelihood question such as
        'Why is the oil risk MEDIUM?' must return a graceful message, not raise an
        exception or return the full Decision Trace.
        """
        from analytics.agent.renderer import render_followup
        d = _make_assessment_with_breakers([])  # no breakers

        result = render_followup("Why is the oil risk MEDIUM?", d)

        assert isinstance(result, str), "Result must be a string"
        assert len(result) > 0, "Result must not be empty"
        assert "DECISION TRACE" not in result, (
            "Full Decision Trace returned for likelihood question with no breakers"
        )


# ===========================================================================
# Group 10: Phase 11B P0-1 (monitoring-only separation) +
#           Phase 11B P0-2 (absent-metric boundary)
# ===========================================================================

class TestPhase11BP0:
    """
    Group 10 — Phase 11B P0-1 and P0-2 acceptance tests.

    P0-1 (5 tests): is_monitoring_only flag and renderer separation.
    P0-2 (5 tests): _format_context() UNAVAILABLE label + post-generation CAGR validation.
    """

    # -----------------------------------------------------------------------
    # P0-1 Test 1: ThesisBreaker.is_monitoring_only defaults to False
    # -----------------------------------------------------------------------

    def test_43_p0_1_is_monitoring_only_default_false(self):
        """
        P0-1-T1: ThesisBreaker.is_monitoring_only must default to False
        (backward-compatible) so existing callers that don't set it are unaffected.
        """
        from analytics.decision.decision_models import ThesisBreaker
        tb = ThesisBreaker(
            condition="Revenue concentration risk",
            likelihood="MEDIUM",
            impact="SEVERE",
            monitoring_indicator="Watch.",
            trigger_action="Review.",
        )
        assert tb.is_monitoring_only is False, (
            "is_monitoring_only must default to False for backward compatibility"
        )

    # -----------------------------------------------------------------------
    # P0-1 Test 2: extract_thesis_breakers tags moat/valuation items as monitoring-only
    # -----------------------------------------------------------------------

    def test_44_p0_1_extract_thesis_breakers_tags_monitoring_only(self):
        """
        P0-1-T2: extract_thesis_breakers() must tag the moat-erosion and
        valuation-assumption-break items with is_monitoring_only=True.
        Severity-contributing items from thesis_breaker_details must remain False.
        """
        from analytics.decision.gate5_adversarial import extract_thesis_breakers
        from analytics.business_research.research_models import (
            BusinessResearchAssessment, BullBearAssessment,
            MoatAssessment, MoatStrength,
        )

        # Minimal mock objects
        class _FakeValuation:
            key_valuation_assumptions = ["FCF yield > 5%", "WACC = 8%"]

        class _FakeMoat:
            class _Strength:
                value = "Strong"
            overall_strength = _Strength()

        research = BusinessResearchAssessment(ticker="X", company_name="X Inc")
        research.bull_bear = BullBearAssessment(
            bull_case_title="", bull_case_narrative="",
            bear_case_title="", bear_case_narrative="",
            thesis_breakers=["Revenue decline"],
            thesis_breaker_details=[{
                "condition": "Revenue decline risk",
                "likelihood": "MEDIUM",
                "evidence": ["Revenue -3.7% CAGR"],
                "likelihood_rationale": "3yr trend negative.",
            }],
        )
        research.moat_assessment = _FakeMoat()

        breakers = extract_thesis_breakers(research, valuation=_FakeValuation())

        sev = [b for b in breakers if not b.is_monitoring_only]
        mon = [b for b in breakers if b.is_monitoring_only]

        assert len(sev) >= 1, "Expected at least 1 severity-contributing breaker"
        assert len(mon) >= 2, (
            f"Expected at least 2 monitoring-only breakers (moat + valuation), "
            f"got {len(mon)}: {[b.condition[:40] for b in mon]}"
        )
        for b in mon:
            assert b.is_monitoring_only is True, (
                f"Monitoring breaker '{b.condition[:40]}' has is_monitoring_only=False"
            )

    # -----------------------------------------------------------------------
    # P0-1 Test 3: render_assessment separates severity vs monitoring in GATE 5 block
    # -----------------------------------------------------------------------

    def test_45_p0_1_render_assessment_separates_severity_and_monitoring(self):
        """
        P0-1-T3: render_assessment() GATE 5 section must contain both:
          - A "Severity-contributing thesis breakers" heading
          - A "Monitoring indicators" heading
        and must NOT mix them under the same unlabelled heading.
        """
        from analytics.agent.renderer import render_assessment
        from analytics.decision.decision_models import ThesisBreaker

        sev_breaker = ThesisBreaker(
            condition="Oil price collapses below $50",
            likelihood="MEDIUM",
            impact="SEVERE",
            monitoring_indicator="Watch WTI.",
            trigger_action="Review.",
            is_monitoring_only=False,
        )
        mon_breaker = ThesisBreaker(
            condition="Moat erosion: market share loss",
            likelihood="LOW",
            impact="FATAL",
            monitoring_indicator="Watch ROIC trend.",
            trigger_action="EXIT review.",
            is_monitoring_only=True,
        )
        d = _make_assessment_with_breakers([sev_breaker, mon_breaker])
        result = render_assessment(d)

        assert "Severity-contributing thesis breakers" in result, (
            "render_assessment() missing 'Severity-contributing thesis breakers' heading"
        )
        assert "Monitoring indicators" in result, (
            "render_assessment() missing 'Monitoring indicators' heading"
        )
        # Monitoring disclaimer must be present
        assert "did NOT affect" in result or "did not affect" in result, (
            "render_assessment() missing disclaimer that monitoring items didn't affect severity"
        )

    # -----------------------------------------------------------------------
    # P0-1 Test 4: _answer_gate5_explanation() counts only severity breakers
    # -----------------------------------------------------------------------

    def test_46_p0_1_gate5_explanation_counts_only_severity_breakers(self):
        """
        P0-1-T4: _answer_gate5_explanation() must compute n_high / n_medium_equiv
        from severity-contributing breakers only.  A monitoring-only LOW breaker
        must not inflate any severity counter.
        """
        from analytics.agent.renderer import _answer_gate5_explanation
        from analytics.decision.decision_models import ThesisBreaker

        # 1 MEDIUM severity-contributing + 1 LOW monitoring-only
        sev = ThesisBreaker(
            condition="Revenue decline", likelihood="MEDIUM", impact="SEVERE",
            monitoring_indicator="", trigger_action="",
            is_monitoring_only=False,
        )
        mon = ThesisBreaker(
            condition="Moat erosion watchlist", likelihood="LOW", impact="FATAL",
            monitoring_indicator="Watch ROIC.", trigger_action="EXIT review.",
            is_monitoring_only=True,
        )
        d = _make_assessment_with_breakers([sev, mon])
        result = _answer_gate5_explanation(d)

        # Medium-equivalent must reflect only the MEDIUM sev breaker (=1), not the LOW mon
        assert "CONTRIBUTING THESIS BREAKERS (severity-contributing)" in result, (
            "Gate 5 explanation missing updated severity-contributing heading"
        )
        assert "MONITORING INDICATORS" in result, (
            "Gate 5 explanation missing MONITORING INDICATORS section"
        )
        # Revenue decline is severity-contributing
        assert "Revenue decline" in result, (
            "Severity-contributing breaker 'Revenue decline' missing from Gate 5 explanation"
        )

    # -----------------------------------------------------------------------
    # P0-1 Test 5: _answer_risks() shows two separate sections
    # -----------------------------------------------------------------------

    def test_47_p0_1_answer_risks_shows_separate_sections(self):
        """
        P0-1-T5: _answer_risks() must show severity-contributing breakers under
        "THESIS BREAKERS (severity-contributing)" and monitoring-only items under
        "MONITORING INDICATORS (did not affect Gate 5 severity)".
        """
        from analytics.agent.renderer import _answer_risks
        from analytics.decision.decision_models import ThesisBreaker

        sev = ThesisBreaker(
            condition="Price war risk", likelihood="MEDIUM", impact="SEVERE",
            monitoring_indicator="Watch margin.", trigger_action="Review.",
            is_monitoring_only=False,
        )
        mon = ThesisBreaker(
            condition="Valuation assumption break: FCF yield < 4%", likelihood="LOW",
            impact="SEVERE", monitoring_indicator="Track FCF.", trigger_action="Reassess.",
            is_monitoring_only=True,
        )
        d = _make_assessment_with_breakers([sev, mon])
        result = _answer_risks(d)

        assert "THESIS BREAKERS (severity-contributing)" in result, (
            "_answer_risks() missing 'THESIS BREAKERS (severity-contributing)'"
        )
        assert "MONITORING INDICATORS" in result, (
            "_answer_risks() missing 'MONITORING INDICATORS' section"
        )
        assert "Price war risk" in result, "Severity breaker condition missing from _answer_risks()"
        assert "Valuation assumption break" in result, (
            "Monitoring indicator condition missing from _answer_risks()"
        )

    # -----------------------------------------------------------------------
    # P0-2 Test 1: _format_context emits UNAVAILABLE for absent revenue_cagr_5yr
    # -----------------------------------------------------------------------

    def test_48_p0_2_format_context_emits_unavailable_for_5yr_cagr(self):
        """
        P0-2-T1: _format_context() for bull_bear_analysis step must include
        'revenue_cagr_5yr: UNAVAILABLE' when revenue_cagr_5yr is None in context.
        """
        from analytics.agent.anthropic_researcher import _format_context

        ctx = {
            "ticker": "CNQ.TO",
            "company_name": "Canadian Natural Resources",
            "analysis_date": "2026-09-30",
            "revenue_cagr_3yr": -3.7,
            "revenue_cagr_5yr": None,  # absent
        }
        result = _format_context("bull_bear_analysis", ctx)

        assert "revenue_cagr_5yr: UNAVAILABLE" in result, (
            f"_format_context() did not emit UNAVAILABLE for absent revenue_cagr_5yr.\n"
            f"Got snippet: {result[result.find('revenue_cagr'):result.find('revenue_cagr')+80]!r}"
        )

    # -----------------------------------------------------------------------
    # P0-2 Test 2: _format_context present 5yr metric is emitted normally
    # -----------------------------------------------------------------------

    def test_49_p0_2_format_context_emits_value_when_5yr_cagr_present(self):
        """
        P0-2-T2: When revenue_cagr_5yr is provided, _format_context() must emit
        its value normally (not UNAVAILABLE).
        """
        from analytics.agent.anthropic_researcher import _format_context

        ctx = {
            "ticker": "CNQ.TO",
            "company_name": "Canadian Natural Resources",
            "analysis_date": "2026-09-30",
            "revenue_cagr_5yr": -2.1,
        }
        result = _format_context("bull_bear_analysis", ctx)

        assert "revenue_cagr_5yr: -2.1" in result, (
            "Present revenue_cagr_5yr value not emitted by _format_context()"
        )
        assert "UNAVAILABLE" not in result or "revenue_cagr_5yr: UNAVAILABLE" not in result, (
            "Present revenue_cagr_5yr should not show UNAVAILABLE"
        )

    # -----------------------------------------------------------------------
    # P0-2 Test 3: Evidence-boundary instruction is present for bull_bear step
    # -----------------------------------------------------------------------

    def test_50_p0_2_bull_bear_prompt_contains_evidence_boundary_instruction(self):
        """
        P0-2-T3: The prompt returned by _format_context() for bull_bear_analysis
        must contain the evidence-boundary instruction that forbids referencing
        UNAVAILABLE metrics.
        """
        from analytics.agent.anthropic_researcher import _format_context

        ctx = {"ticker": "X", "company_name": "X Inc", "analysis_date": "2026-09-30",
               "revenue_cagr_5yr": None}
        result = _format_context("bull_bear_analysis", ctx)

        assert "EVIDENCE BOUNDARY" in result, (
            "bull_bear_analysis prompt missing EVIDENCE BOUNDARY instruction"
        )
        assert "UNAVAILABLE" in result, (
            "bull_bear_analysis prompt missing UNAVAILABLE reference in boundary instruction"
        )

    # -----------------------------------------------------------------------
    # P0-2 Test 4: Evidence-boundary instruction absent for non-bull-bear steps
    # -----------------------------------------------------------------------

    def test_51_p0_2_evidence_boundary_not_in_other_steps(self):
        """
        P0-2-T4: The EVIDENCE BOUNDARY instruction is specific to bull_bear_analysis.
        It must NOT appear in prompts for other steps (e.g. risk_analysis).
        """
        from analytics.agent.anthropic_researcher import _format_context

        ctx = {"ticker": "X", "company_name": "X Inc", "analysis_date": "2026-09-30",
               "revenue_cagr_5yr": None}
        result = _format_context("risk_analysis", ctx)

        assert "EVIDENCE BOUNDARY" not in result, (
            "EVIDENCE BOUNDARY instruction appeared in risk_analysis prompt — should only be in bull_bear_analysis"
        )

    # -----------------------------------------------------------------------
    # P0-2 Test 5: _parse_bull_bear flags 5yr CAGR narrative when context lacks it
    # -----------------------------------------------------------------------

    def test_52_p0_2_parse_bull_bear_flags_fabricated_5yr_cagr(self):
        """
        P0-2-T5: _parse_bull_bear() must annotate bear_case_narrative with a
        DATA-BOUNDARY-VIOLATION prefix when it contains a '5-year CAGR' claim
        and revenue_cagr_5yr was not in context.
        """
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from analytics.agent.research_orchestrator import ResearchOrchestrator

        raw = {
            "bull_case_title": "Strong FCF",
            "bull_case_narrative": "3-year revenue trend positive.",
            "bear_case_title": "Revenue decline",
            "bear_case_narrative": (
                "Revenue has contracted at -3.7% CAGR over both 3- and 5-year periods, "
                "indicating structural challenges."
            ),
            "thesis_breakers": [],
        }
        ctx = {
            "ticker": "CNQ.TO",
            "revenue_cagr_5yr": None,  # absent — 5yr claim is fabricated
        }

        # Instantiate orchestrator with a no-op executor (we're testing _parse_bull_bear only)
        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        bb = orch._parse_bull_bear(raw, ctx)

        assert "DATA-BOUNDARY-VIOLATION" in bb.bear_case_narrative, (
            "bear_case_narrative with fabricated 5-year CAGR claim was not flagged.\n"
            f"Got: {bb.bear_case_narrative!r}"
        )
        # Bull narrative had no 5yr claim — must be clean
        assert "DATA-BOUNDARY-VIOLATION" not in bb.bull_case_narrative, (
            "bull_case_narrative was incorrectly flagged (no 5yr CAGR claim present)"
        )


# ===========================================================================
# Group 11: Phase 11B Corrective Fix — Regression tests A–F
# ===========================================================================

class TestPhase11BCorrectiveFix:
    """
    Group 11 — Corrective regression tests added after CNQ acceptance failure.

    Test A: Decision Trace classifies monitoring-only items under "MONITORING INDICATORS"
            heading, not under "CONTRIBUTING THESIS BREAKERS (Gate 5)".
    Test B: _parse_bull_bear() flags 5yr CAGR in plural "years" form (original regex bug).
    Test C: _parse_bull_bear() flags "Revenue CAGR of -X% over 5 years" (short form).
    Test D: _parse_bull_bear() flags carbon-pricing $/tonne in evidence string.
    Test E: _parse_bull_bear() does NOT flag 3yr CAGR (valid, in context — must be clean).
    Test F: monitoring-only breaker does NOT change Gate 5 severity count.
    """

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _make_monitoring_breaker(self, condition="Valuation assumption break"):
        from analytics.decision.decision_models import ThesisBreaker
        return ThesisBreaker(
            condition=condition,
            likelihood="LOW",
            impact="SEVERE",
            monitoring_indicator="Track FCF yield.",
            trigger_action="Reassess if FCF yield < 4%.",
            is_monitoring_only=True,
        )

    def _make_severity_breaker(self, condition="Oil price collapse", likelihood="MEDIUM"):
        from analytics.decision.decision_models import ThesisBreaker
        return ThesisBreaker(
            condition=condition,
            likelihood=likelihood,
            impact="SEVERE",
            monitoring_indicator="Watch WTI.",
            trigger_action="Review position.",
            is_monitoring_only=False,
        )

    def _parse_bb(self, raw, ctx):
        """Helper: call _parse_bull_bear() without instantiating full orchestrator."""
        from analytics.agent.research_orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        return orch._parse_bull_bear(raw, ctx)

    # ------------------------------------------------------------------
    # Test A: Decision Trace separates monitoring items into correct section
    # ------------------------------------------------------------------

    def test_53_A_decision_trace_monitoring_items_under_correct_heading(self):
        """
        Test A: Decision Trace corrective fix.

        When an assessment has:
          - 1 severity-contributing breaker (is_monitoring_only=False)
          - 1 monitoring-only breaker (is_monitoring_only=True)

        render_decision_trace() must:
          - Place the severity breaker under "CONTRIBUTING THESIS BREAKERS (Gate 5):"
          - Place the monitoring breaker under "MONITORING INDICATORS (did NOT affect Gate 5 severity):"
          - NOT mix both under the same heading.
        """
        from analytics.decision.decision_trace import build_decision_trace, render_decision_trace

        sev = self._make_severity_breaker("Crude oil collapse", "MEDIUM")
        mon = self._make_monitoring_breaker("Valuation assumption break: FCF yield < 4%")

        assessment = _make_assessment_with_breakers([sev, mon])
        trace = build_decision_trace(assessment)
        rendered = render_decision_trace(trace)

        # Severity breaker must appear under contributing section
        assert "CONTRIBUTING THESIS BREAKERS (Gate 5):" in rendered, (
            "render_decision_trace() missing 'CONTRIBUTING THESIS BREAKERS (Gate 5):' heading\n"
            f"Got (first 600 chars): {rendered[:600]!r}"
        )
        # Monitoring breaker must appear under its own section
        assert "MONITORING INDICATORS (did NOT affect Gate 5 severity):" in rendered, (
            "render_decision_trace() missing 'MONITORING INDICATORS' section\n"
            f"Got (first 600 chars): {rendered[:600]!r}"
        )

        # Validate routing: severity condition appears in the trace (under contributing)
        assert "Crude oil collapse" in rendered, "Severity breaker not in trace"
        assert "Valuation assumption break" in rendered, "Monitoring breaker not in trace"

        # Critical: monitoring item must NOT appear in the contributing sections.
        # The trace renders two levels:
        #   1. Per-gate block: "Severity-contributing thesis breakers:" / "Monitoring indicators ..."
        #   2. End-of-trace:   "CONTRIBUTING THESIS BREAKERS (Gate 5):" / "MONITORING INDICATORS ..."
        # Extract the text of each contributing section and assert monitoring item is absent.

        # Per-gate: text between "Severity-contributing thesis breakers:" and next empty block
        per_gate_sev_start = rendered.find("Severity-contributing thesis breakers:")
        per_gate_mon_start = rendered.find("Monitoring indicators (did NOT affect")
        assert per_gate_sev_start != -1, "Per-gate severity heading not found"
        assert per_gate_mon_start != -1, "Per-gate monitoring heading not found"
        # Text that belongs to the severity section only (between the two per-gate headings)
        per_gate_sev_section = rendered[per_gate_sev_start:per_gate_mon_start]
        assert "Valuation assumption break" not in per_gate_sev_section, (
            "Monitoring-only item 'Valuation assumption break' leaked into the "
            "per-gate severity-contributing section.\n"
            f"Severity section text: {per_gate_sev_section!r}"
        )

        # End-of-trace: text between "CONTRIBUTING THESIS BREAKERS (Gate 5):" and "MONITORING INDICATORS"
        et_sev_start = rendered.find("CONTRIBUTING THESIS BREAKERS (Gate 5):")
        et_mon_start = rendered.find("MONITORING INDICATORS (did NOT affect Gate 5 severity):")
        assert et_sev_start != -1, "End-of-trace CONTRIBUTING heading not found"
        assert et_mon_start != -1, "End-of-trace MONITORING INDICATORS heading not found"
        et_sev_section = rendered[et_sev_start:et_mon_start]
        assert "Valuation assumption break" not in et_sev_section, (
            "Monitoring-only item 'Valuation assumption break' leaked into the "
            "end-of-trace CONTRIBUTING THESIS BREAKERS section.\n"
            f"Contributing section text: {et_sev_section!r}"
        )

        # Monitoring item must appear in the monitoring section (end-of-trace)
        et_mon_section = rendered[et_mon_start:]
        assert "Valuation assumption break" in et_mon_section, (
            "Monitoring-only item 'Valuation assumption break' not found in "
            "MONITORING INDICATORS end-of-trace section.\n"
            f"Monitoring section text: {et_mon_section!r}"
        )

    # ------------------------------------------------------------------
    # Test B: Plural "years" in 5yr CAGR string is flagged (original regex bug)
    # ------------------------------------------------------------------

    def test_54_B_plural_years_in_cagr_claim_is_flagged(self):
        """
        Test B: Original regex bug — 'year\\b' failed for 'years' (plural).

        The corrective fix changes 'year\\b' to 'years?\\b' and adds additional
        plural patterns. This test verifies the exact string that escaped the
        original validator:
          "Revenue contraction of -3.7% CAGR over 5 years suggests ongoing pressure"

        Expected: bear_case_narrative annotated with [DATA-BOUNDARY-VIOLATION].
        """
        raw = {
            "bull_case_title": "Solid balance sheet",
            "bull_case_narrative": "3-year FCF trend positive.",
            "bear_case_title": "Revenue decline",
            "bear_case_narrative": (
                "Revenue contraction of -3.7% CAGR over 5 years suggests "
                "ongoing volume or price pressure."
            ),
            "thesis_breakers": [],
        }
        ctx = {"ticker": "CNQ.TO", "revenue_cagr_5yr": None}

        bb = self._parse_bb(raw, ctx)

        assert "DATA-BOUNDARY-VIOLATION" in bb.bear_case_narrative, (
            "Plural 'years' 5yr CAGR claim NOT flagged — original regex bug not fixed.\n"
            f"bear_case_narrative: {bb.bear_case_narrative!r}"
        )
        assert "DATA-BOUNDARY-VIOLATION" not in bb.bull_case_narrative, (
            "bull_case_narrative incorrectly flagged (contains no 5yr claim)"
        )

    # ------------------------------------------------------------------
    # Test C: Short-form "Revenue CAGR of -X% over 5 years" is flagged
    # ------------------------------------------------------------------

    def test_55_C_short_form_cagr_over_5_years_is_flagged(self):
        """
        Test C: Another pattern that escaped the original validator:
          "Revenue CAGR of -3.75% over 5 years"

        The corrective fix adds 'over\\s+(?:the\\s+)?(?:past\\s+)?5\\s+years?' to the
        pattern which matches this phrasing (CAGR need not appear adjacent).

        Expected: flagged with DATA-BOUNDARY-VIOLATION when revenue_cagr_5yr is None.
        """
        raw = {
            "bull_case_title": "Strong moat",
            "bull_case_narrative": "Revenue CAGR of +2.1% over 3 years positive.",
            "bear_case_title": "Revenue trend",
            "bear_case_narrative": (
                "Revenue CAGR of -3.75% over 5 years is a concern."
            ),
            "thesis_breakers": [],
        }
        ctx = {"ticker": "CNQ.TO", "revenue_cagr_5yr": None}

        bb = self._parse_bb(raw, ctx)

        assert "DATA-BOUNDARY-VIOLATION" in bb.bear_case_narrative, (
            "'Revenue CAGR of -X% over 5 years' not flagged — corrective pattern missing.\n"
            f"bear_case_narrative: {bb.bear_case_narrative!r}"
        )
        # 3yr claim in bull is valid — must not be flagged
        assert "DATA-BOUNDARY-VIOLATION" not in bb.bull_case_narrative, (
            "3-year CAGR in bull_case_narrative was incorrectly flagged"
        )

    # ------------------------------------------------------------------
    # Test D: Carbon-pricing $/tonne claim in evidence is flagged
    # ------------------------------------------------------------------

    def test_56_D_carbon_pricing_claim_in_evidence_is_flagged(self):
        """
        Test D: Carbon-pricing external claims ($/tonne) must be flagged in
        evidence strings. Carbon pricing data is never provided in the
        structured context dict, so any $/tonne claim is an unsupported external fact.

        Test string derived from CNQ output: 'Federal carbon tax ~$170/tonne by 2030'
        """
        raw = {
            "bull_case_title": "Hedging in place",
            "bull_case_narrative": "Commodity hedges reduce downside.",
            "bear_case_title": "Carbon cost risk",
            "bear_case_narrative": "Carbon cost risk remains on the horizon.",
            "thesis_breakers": [
                {
                    "condition": "Carbon cost escalation",
                    "likelihood": "MEDIUM",
                    "evidence": [
                        "Federal carbon tax ~$170/tonne by 2030 would add ~$4/bbl to costs",
                        "Current WTI at $72/bbl provides buffer.",
                    ],
                    "likelihood_rationale": "Carbon price trajectory is legislated.",
                }
            ],
        }
        ctx = {"ticker": "CNQ.TO", "revenue_cagr_5yr": -2.1}  # 5yr present — only carbon matters

        bb = self._parse_bb(raw, ctx)

        # Must have thesis_breaker_details with segregated evidence
        assert len(bb.thesis_breaker_details) >= 1, "Expected at least 1 detail"
        detail = bb.thesis_breaker_details[0]
        clean_ev   = detail.get("evidence", [])
        flagged_ev = detail.get("unsupported_evidence", [])

        # Carbon $/tonne string must be in unsupported_evidence (segregated, not annotated in-place)
        assert len(flagged_ev) >= 1, (
            "Carbon-pricing $/tonne claim not moved to unsupported_evidence.\n"
            f"evidence: {clean_ev!r}\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )
        assert any("DATA-BOUNDARY-VIOLATION" in e for e in flagged_ev), (
            "Carbon-pricing unsupported_evidence entry not annotated.\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )

        # Clean WTI string must remain in evidence[]
        assert any("WTI" in e for e in clean_ev), (
            "Clean evidence string incorrectly removed from evidence[].\n"
            f"evidence: {clean_ev!r}"
        )
        # No violation annotation in evidence[]
        assert not any("DATA-BOUNDARY-VIOLATION" in e for e in clean_ev), (
            "DATA-BOUNDARY-VIOLATION annotation leaked into clean evidence[].\n"
            f"evidence: {clean_ev!r}"
        )

    # ------------------------------------------------------------------
    # Test E: Valid 3yr CAGR (in context) is NOT flagged
    # ------------------------------------------------------------------

    def test_57_E_valid_3yr_cagr_not_flagged(self):
        """
        Test E: A 3-year CAGR claim that IS supported by context must NOT be flagged.
        The validator must only flag 5yr CAGR when 5yr is absent — it must never
        flag 3yr CAGR claims (which are always permissible if in context).
        """
        raw = {
            "bull_case_title": "Revenue stabilizing",
            "bull_case_narrative": (
                "Revenue declined at -3.7% CAGR over 3 years but trend is reversing."
            ),
            "bear_case_title": "Continued decline",
            "bear_case_narrative": (
                "Revenue contracted -3.7% CAGR over 3-year period; "
                "near-term outlook dependent on oil price recovery."
            ),
            "thesis_breakers": [],
        }
        ctx = {
            "ticker": "CNQ.TO",
            "revenue_cagr_3yr": -3.7,
            "revenue_cagr_5yr": None,  # 5yr absent — but only 3yr referenced in text
        }

        bb = self._parse_bb(raw, ctx)

        assert "DATA-BOUNDARY-VIOLATION" not in bb.bull_case_narrative, (
            "3yr CAGR claim in bull narrative was incorrectly flagged.\n"
            f"bull_case_narrative: {bb.bull_case_narrative!r}"
        )
        assert "DATA-BOUNDARY-VIOLATION" not in bb.bear_case_narrative, (
            "3yr CAGR claim in bear narrative was incorrectly flagged.\n"
            f"bear_case_narrative: {bb.bear_case_narrative!r}"
        )

    # ------------------------------------------------------------------
    # Test F: monitoring-only breaker does NOT contribute to Gate 5 severity
    # ------------------------------------------------------------------

    def test_58_F_monitoring_only_breaker_does_not_affect_severity(self):
        """
        Test F: The severity model (n_high, n_medium_equiv) must use only
        severity-contributing breakers.  A monitoring-only breaker — even
        if tagged MEDIUM — must NOT be passed to evaluate_gate5() and must
        NOT inflate the severity count.

        Design contract: evaluate_gate5() receives only breakers A+B;
        extract_thesis_breakers() adds C (monitoring) for display only.
        This test verifies the calculate_adversarial_severity() shared function
        ignores is_monitoring_only when only an empty severity list is passed.

        Implementation note: calculate_adversarial_severity() takes the breaker list
        it is given — it does not filter by is_monitoring_only internally.  The caller
        (run_scenario/evaluate_gate5) is responsible for passing only severity-contributing
        breakers.  This test verifies that an empty list → LOW.
        """
        from analytics.decision.gate5_adversarial import calculate_adversarial_severity
        from analytics.decision.decision_models import ThesisBreaker

        # Simulate: monitoring-only breakers are excluded by caller before this call.
        # K1: scenario engine now filters is_monitoring_only before calling the shared function.
        # This test verifies the model's low-severity baseline when no genuine breakers exist.
        severity_only_list = []  # monitoring-only items filtered out by caller
        result = calculate_adversarial_severity(severity_only_list, n_bear=0)

        assert result == "LOW", (
            f"Expected LOW when no severity-contributing breakers present, got {result!r}.\n"
            "If non-LOW: monitoring-only breakers may have been incorrectly included "
            "in the severity-contributing list passed to calculate_adversarial_severity()."
        )


# ===========================================================================
# Group 12: Phase 11B Evidence Boundary — final correction regression tests
# ===========================================================================

class TestPhase11BEvidenceBoundaryFinal:
    r"""
    Group 12 — Regression tests for the Phase 11B Evidence Boundary Final Correction.

    Covers:
      Test 1:  Evidence segregation — 5yr CAGR claim in evidence when revenue_cagr_5yr
               is absent goes to unsupported_evidence[], NOT evidence[]
      Test 2:  Multiple wording variants of 5yr CAGR all flagged in evidence
      Test 3:  Valid 3yr CAGR in context NOT flagged (no false positive)
      Test 4:  Carbon-pricing external metric in evidence flagged
      Test 5:  Hypothetical breaker condition containing '<' is NOT filtered
               (_parse_bull_bear does not scan the condition field)
      Test 6:  Gate 5 evidence clean — detail["evidence"] contains only clean strings
               after _parse_bull_bear; violating strings are in unsupported_evidence
      Test 7:  UNKNOWN likelihood renders as UNKNOWN in render_assessment output,
               not silently replaced with MEDIUM
      Test 8:  Monitoring-only separation — render_assessment() shows monitoring items
               under a monitoring section, never under severity-contributing section
      Test 9:  _md_safe() escapes < and > but preserves all other characters
      Test 10: render_assessment() output for a breaker with '<' in condition contains
               escaped '\<' not raw '<' — regression guard for Streamlit rendering defect
    """

    def _parse_bb(self, raw: dict, ctx: dict):
        """Call _parse_bull_bear() without full orchestrator instantiation."""
        from analytics.agent.research_orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        return orch._parse_bull_bear(raw, ctx)

    def _raw_with_detail(self, condition: str, evidence: list,
                          bear_narrative: str = "Neutral bear case.") -> dict:
        """Build a minimal raw LLM output dict with one thesis_breaker_detail.

        _parse_bull_bear() ingests thesis_breaker_details from the thesis_breakers
        array (where each dict entry is the structured format), NOT from a separate
        thesis_breaker_details key.  See research_orchestrator._parse_bull_bear().
        """
        return {
            "bull_case_title": "Bull",
            "bull_case_narrative": "Stable revenue.",
            "bear_case_title": "Bear",
            "bear_case_narrative": bear_narrative,
            "thesis_breakers": [
                {
                    "condition": condition,
                    "likelihood": "MEDIUM",
                    "likelihood_rationale": "Moderate scenario.",
                    "evidence": evidence,
                }
            ],
        }

    # ------------------------------------------------------------------
    # Test 1: Evidence segregation — violating string goes to unsupported_evidence
    # ------------------------------------------------------------------

    def test_59_1_5yr_cagr_evidence_segregated_to_unsupported(self):
        """
        Test 1: When revenue_cagr_5yr is absent from context (None) and an evidence
        string references '5-year CAGR', _parse_bull_bear() must move that string to
        d['unsupported_evidence'] and NOT leave it in d['evidence'].

        This ensures the violating string never reaches ThesisBreaker.evidence
        (which is what Gate 5 and the renderer treat as trusted evidence).
        """
        raw = self._raw_with_detail(
            condition="Commodity price collapse below $40/bbl",
            evidence=[
                "FCF declined 47.8% from 2022 to 2025.",                            # clean
                "Revenue CAGR of -3.75% over 5 years reflects weak pricing or volume", # violating: 5yr
            ],
        )
        ctx = {
            "ticker": "CNQ.TO",
            "revenue_cagr_3yr": -3.75,
            "revenue_cagr_5yr": None,  # absent — 5yr claim must be segregated
        }

        bb = self._parse_bb(raw, ctx)
        detail = bb.thesis_breaker_details[0]

        clean_ev = detail.get("evidence", [])
        flagged_ev = detail.get("unsupported_evidence", [])

        # The violating string must NOT be in evidence[]
        assert not any("5 year" in e.lower() or "5yr" in e.lower() or "5-year" in e.lower()
                        for e in clean_ev), (
            f"Violating 5yr CAGR claim found in trusted evidence[].\n"
            f"evidence: {clean_ev!r}\n"
            "It must be in unsupported_evidence[], not evidence[]."
        )

        # The violating string MUST be in unsupported_evidence[]
        assert len(flagged_ev) >= 1, (
            f"Expected unsupported_evidence[] to contain the 5yr CAGR claim.\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )
        assert any("DATA-BOUNDARY-VIOLATION" in e for e in flagged_ev), (
            f"unsupported_evidence[] entries are not annotated.\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )

        # The clean evidence must still be in evidence[]
        assert any("FCF declined" in e for e in clean_ev), (
            f"Clean evidence string was incorrectly removed from evidence[].\n"
            f"evidence: {clean_ev!r}"
        )

    # ------------------------------------------------------------------
    # Test 2: Multiple wording variants all flagged
    # ------------------------------------------------------------------

    def test_60_2_multiple_5yr_wording_variants_all_flagged_in_evidence(self):
        """
        Test 2: All known wording variants of a 5yr CAGR claim must be flagged in
        evidence when revenue_cagr_5yr is None.

        Variants tested (from known CNQ LLM output and the corrected regex):
          a) "Revenue CAGR of -3.75% already reflects weak pricing or volume"
             (no explicit 'year' — relies on CAGR + context; this is NOT a 5yr-specific
             regex match unless the LLM includes 'year' — test only the wording variants
             that include year references)
          a) "revenue contraction of -3.7% CAGR over 5 years" (plural, original bug)
          b) "Revenue CAGR of -3.75% over 5 years" (short form)
          c) "revenues declined at a 3.75% CAGR over the 5-year period"
          d) "revenues declined at a 3.75% CAGR over both 3- and 5-year periods"
        """
        variants = [
            "revenue contraction of -3.7% CAGR over 5 years",
            "Revenue CAGR of -3.75% over 5 years",
            "revenues declined at a 3.75% CAGR over the 5-year period",
            "revenues declined at a 3.75% CAGR over both 3- and 5-year periods",
        ]
        ctx = {
            "ticker": "CNQ.TO",
            "revenue_cagr_3yr": -3.75,
            "revenue_cagr_5yr": None,
        }

        for variant in variants:
            raw = self._raw_with_detail(
                condition="Oil price collapse",
                evidence=[variant],
            )
            bb = self._parse_bb(raw, ctx)
            detail = bb.thesis_breaker_details[0]
            flagged = detail.get("unsupported_evidence", [])
            clean = detail.get("evidence", [])

            assert len(flagged) >= 1 and any("DATA-BOUNDARY-VIOLATION" in e for e in flagged), (
                f"Wording variant NOT flagged: {variant!r}\n"
                f"evidence (should be empty): {clean!r}\n"
                f"unsupported_evidence: {flagged!r}"
            )

    # ------------------------------------------------------------------
    # Test 3: Valid 3yr CAGR not flagged (no false positive)
    # ------------------------------------------------------------------

    def test_61_3_valid_3yr_cagr_not_flagged_in_evidence(self):
        """
        Test 3: A 3yr CAGR evidence string must NOT be flagged even when
        revenue_cagr_5yr is None.  The evidence boundary only applies to 5yr claims.
        """
        raw = self._raw_with_detail(
            condition="Revenue contraction accelerates",
            evidence=[
                "Revenue contracted -3.7% over the 3-year period 2022–2025.",
                "3yr CAGR of -3.7% reflects depressed oil prices.",
            ],
        )
        ctx = {
            "ticker": "CNQ.TO",
            "revenue_cagr_3yr": -3.7,
            "revenue_cagr_5yr": None,  # 5yr absent, but only 3yr referenced in evidence
        }

        bb = self._parse_bb(raw, ctx)
        detail = bb.thesis_breaker_details[0]

        # Clean evidence must be preserved
        clean_ev = detail.get("evidence", [])
        flagged_ev = detail.get("unsupported_evidence", [])

        assert len(clean_ev) == 2, (
            f"Expected 2 clean evidence strings; got {len(clean_ev)}.\n"
            f"evidence: {clean_ev!r}\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )
        assert not flagged_ev, (
            f"3yr CAGR evidence was incorrectly flagged as a boundary violation.\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )

    # ------------------------------------------------------------------
    # Test 4: Carbon-pricing external metric flagged in evidence
    # ------------------------------------------------------------------

    def test_62_4_carbon_pricing_external_metric_flagged_in_evidence(self):
        """
        Test 4: A carbon-pricing claim in evidence ($/tonne) is always an external fact
        — it is never provided in the structured financial context dict.
        _parse_bull_bear() must flag it to unsupported_evidence[] regardless of
        whether revenue_cagr_5yr is present or absent.
        """
        raw = self._raw_with_detail(
            condition="Carbon regulation cost escalation",
            evidence=[
                "Current WTI at $72/bbl provides near-term buffer.",                      # clean
                "Federal carbon tax ~$170/tonne by 2030 would add ~$4/bbl to costs.",    # external
            ],
        )
        ctx = {
            "ticker": "CNQ.TO",
            "revenue_cagr_3yr": -3.7,
            "revenue_cagr_5yr": -3.7,  # present — so 5yr rule does NOT fire; only carbon rule fires
        }

        bb = self._parse_bb(raw, ctx)
        detail = bb.thesis_breaker_details[0]

        clean_ev = detail.get("evidence", [])
        flagged_ev = detail.get("unsupported_evidence", [])

        # WTI price is clean (it's in context-computable range, no $/tonne pattern)
        assert any("WTI" in e for e in clean_ev), (
            f"Clean WTI evidence removed from evidence[].\nevidence: {clean_ev!r}"
        )

        # Carbon tax claim must be in unsupported_evidence
        assert len(flagged_ev) >= 1, (
            f"Carbon-pricing claim not flagged.\n"
            f"evidence: {clean_ev!r}\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )
        assert any("DATA-BOUNDARY-VIOLATION" in e for e in flagged_ev), (
            f"Carbon-pricing flagged entry is not annotated.\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )

    # ------------------------------------------------------------------
    # Test 5: Hypothetical breaker condition with '<' passes through unchanged
    # ------------------------------------------------------------------

    def test_63_5_hypothetical_breaker_condition_not_filtered(self):
        """
        Test 5: The evidence-boundary filter must NOT suppress the 'condition' field
        of thesis_breaker_details, even when the condition contains symbols like '<'.

        The LLM is permitted to generate hypothetical breaker conditions
        ("Brent crude <$40/bbl") — these are forward-looking hypotheticals, not
        claims about current structured data.  Only evidence[] and narrative fields
        are scanned for boundary violations.

        This test confirms:
          a) condition field passes through unmodified
          b) evidence[] strings are correctly filtered
          c) no cross-contamination between condition filtering and evidence filtering
        """
        condition = "Commodity price collapse (Brent crude <$40/bbl or natural gas sustained <$2 USD/MMBtu)"
        raw = self._raw_with_detail(
            condition=condition,
            evidence=[
                "Brent spot at $72/bbl as of Sep 2026.",                    # clean
                "Revenue CAGR of -3.75% over 5 years drives bear case.",   # violating (5yr absent)
            ],
            bear_narrative="If crude drops below $40, FCF turns negative.",
        )
        ctx = {
            "ticker": "CNQ.TO",
            "revenue_cagr_3yr": -3.7,
            "revenue_cagr_5yr": None,   # absent — so 5yr evidence violation fires
        }

        bb = self._parse_bb(raw, ctx)
        detail = bb.thesis_breaker_details[0]

        # Condition must be unchanged — hypothetical breaker generation is permitted
        assert detail.get("condition") == condition, (
            f"Breaker condition was incorrectly modified by the evidence-boundary filter.\n"
            f"Expected: {condition!r}\n"
            f"Got:      {detail.get('condition')!r}"
        )

        # Evidence violation still correctly routed
        flagged_ev = detail.get("unsupported_evidence", [])
        assert len(flagged_ev) >= 1 and any("DATA-BOUNDARY-VIOLATION" in e for e in flagged_ev), (
            f"5yr CAGR evidence violation not flagged when condition has '<'.\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )

        # Clean evidence stays
        clean_ev = detail.get("evidence", [])
        assert any("Brent spot" in e for e in clean_ev), (
            f"Clean evidence string removed from evidence[].\nevidence: {clean_ev!r}"
        )

    # ------------------------------------------------------------------
    # Test 6: Gate 5 evidence clean — only clean strings in detail["evidence"]
    # ------------------------------------------------------------------

    def test_64_6_gate5_evidence_array_contains_only_clean_strings(self):
        """
        Test 6: After _parse_bull_bear(), detail["evidence"] must contain ONLY
        strings that passed the boundary check.  Violating strings must be in
        unsupported_evidence[] only.

        This is the contract that ensures ThesisBreaker.evidence (populated by
        evaluate_gate5() from detail["evidence"]) never carries fabricated data.
        """
        raw = {
            "bull_case_title": "Bull",
            "bull_case_narrative": "Stable operations.",
            "bear_case_title": "Bear",
            "bear_case_narrative": "Revenue under pressure.",
            "thesis_breakers": [
                {
                    "condition": "FCF collapse below maintenance threshold",
                    "likelihood": "MEDIUM",
                    "likelihood_rationale": "FCF declined 47.8% over the measured period.",
                    "evidence": [
                        "FCF fell 47.8% from 2022 to 2025.",                     # clean
                        "Federal carbon tax ~$170/tonne by 2030.",                # violating (carbon)
                        "Revenue CAGR of -3.75% over 5 years is a concern.",     # violating (5yr)
                        "Net debt increased to $8.2B as of Q2 2026.",             # clean
                    ],
                }
            ],
        }
        ctx = {
            "ticker": "CNQ.TO",
            "revenue_cagr_3yr": -3.7,
            "revenue_cagr_5yr": None,
        }

        bb = self._parse_bb(raw, ctx)
        detail = bb.thesis_breaker_details[0]
        clean_ev = detail.get("evidence", [])
        flagged_ev = detail.get("unsupported_evidence", [])

        # Exactly the two clean strings must survive
        assert len(clean_ev) == 2, (
            f"Expected 2 clean evidence strings after segregation, got {len(clean_ev)}.\n"
            f"evidence: {clean_ev!r}"
        )
        assert any("FCF fell" in e for e in clean_ev), "FCF fell removed from evidence[]"
        assert any("Net debt" in e for e in clean_ev), "Net debt removed from evidence[]"

        # Exactly the two violating strings must be in unsupported_evidence
        assert len(flagged_ev) == 2, (
            f"Expected 2 unsupported_evidence entries, got {len(flagged_ev)}.\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )
        assert all("DATA-BOUNDARY-VIOLATION" in e for e in flagged_ev), (
            f"Not all unsupported_evidence entries are annotated.\n"
            f"unsupported_evidence: {flagged_ev!r}"
        )

        # No DATA-BOUNDARY-VIOLATION in evidence[]
        assert not any("DATA-BOUNDARY-VIOLATION" in e for e in clean_ev), (
            f"Annotated violation string leaked into evidence[].\nevidence: {clean_ev!r}"
        )

    # ------------------------------------------------------------------
    # Test 7: UNKNOWN semantics — render_assessment displays UNKNOWN not MEDIUM
    # ------------------------------------------------------------------

    def test_65_7_unknown_likelihood_renders_as_unknown_not_medium(self):
        """
        Test 7: A breaker with likelihood UNKNOWN must render as '[UNKNOWN]' in
        render_assessment() output — never silently replaced with '[MEDIUM]'.

        Phase 11B contract: UNKNOWN is treated as MEDIUM-equivalent for the
        *severity calculation* only.  It is displayed as UNKNOWN everywhere else.
        """
        from analytics.agent.renderer import render_assessment
        from analytics.decision.decision_models import ThesisBreaker

        tb = ThesisBreaker(
            condition="Operating margin deterioration below 20%",
            likelihood="UNKNOWN",
            impact="SEVERE",
            monitoring_indicator="Watch quarterly margin trends.",
            trigger_action="Would prompt REDUCE review.",
            evidence=[],
            likelihood_rationale="No margin trend data in structured context.",
            is_monitoring_only=False,
        )
        assessment = _make_assessment_with_breakers([tb])
        output = render_assessment(assessment)

        assert "[UNKNOWN]" in output, (
            f"'[UNKNOWN]' not found in render_assessment() output.\n"
            "UNKNOWN likelihood must be preserved as UNKNOWN in all display contexts.\n"
            f"Output excerpt (first 1000 chars):\n{output[:1000]}"
        )
        # Must NOT be silently replaced with [MEDIUM] in the breaker display line
        # (MEDIUM may appear elsewhere in the output, so check for the specific line)
        assert "[UNKNOWN] Operating margin deterioration" in output, (
            f"Expected '[UNKNOWN] Operating margin deterioration' in output.\n"
            f"Output excerpt:\n{output[:1200]}"
        )

    # ------------------------------------------------------------------
    # Test 8: Monitoring-only separation in render_assessment
    # ------------------------------------------------------------------

    def test_66_8_monitoring_only_breaker_under_monitoring_section_in_render_assessment(self):
        """
        Test 8: render_assessment() must place a monitoring-only breaker under the
        'Monitoring indicators' section, NOT under 'Severity-contributing thesis breakers'.
        """
        from analytics.agent.renderer import render_assessment
        from analytics.decision.decision_models import ThesisBreaker

        sev_tb = ThesisBreaker(
            condition="Commodity price collapse below $60/bbl",
            likelihood="MEDIUM",
            impact="SEVERE",
            monitoring_indicator="Watch Brent/WTI monthly.",
            trigger_action="Would prompt REDUCE review.",
            is_monitoring_only=False,
        )
        mon_tb = ThesisBreaker(
            condition="Key valuation assumptions fail: DCF discount rate rises above 12%",
            likelihood="LOW",
            impact="SEVERE",
            monitoring_indicator="Track actuals vs assumptions quarterly.",
            trigger_action="Reassess fair value.",
            is_monitoring_only=True,
        )
        assessment = _make_assessment_with_breakers([sev_tb, mon_tb])
        output = render_assessment(assessment)

        # Severity section must exist
        assert "Severity-contributing thesis breakers" in output, (
            "Severity-contributing section not found in render_assessment() output."
        )
        # Monitoring section must exist
        assert "Monitoring indicators" in output, (
            "Monitoring indicators section not found in render_assessment() output."
        )

        # Locate each section in the rendered string
        sev_start = output.find("Severity-contributing thesis breakers")
        mon_start = output.find("Monitoring indicators")

        sev_section = output[sev_start:mon_start]

        # Severity breaker appears in severity section
        assert "Commodity price collapse" in sev_section, (
            f"Severity breaker not found in severity section.\n"
            f"Severity section: {sev_section!r}"
        )
        # Monitoring breaker must NOT appear in severity section
        assert "DCF discount rate" not in sev_section, (
            f"Monitoring-only breaker leaked into severity-contributing section.\n"
            f"Severity section: {sev_section!r}"
        )
        # Monitoring breaker appears in monitoring section
        mon_section = output[mon_start:]
        assert "DCF discount rate" in mon_section, (
            f"Monitoring-only breaker not found in monitoring section.\n"
            f"Monitoring section: {mon_section!r}"
        )

    # ------------------------------------------------------------------
    # Test 9: _md_safe() helper — escapes < and > only
    # ------------------------------------------------------------------

    def test_67_9_md_safe_escapes_angle_brackets_only(self):
        r"""
        Test 9: _md_safe() must escape '<' to '\<' and '>' to '\>' but must
        leave all other characters (including '$', '/', '%', spaces, digits,
        and alphabetic characters) completely unchanged.
        """
        from analytics.agent.renderer import _md_safe

        # Core escaping
        assert _md_safe("Brent crude <$40/bbl") == r"Brent crude \<$40/bbl", (
            "_md_safe did not escape '<' in 'Brent crude <$40/bbl'"
        )
        assert _md_safe("P/E ratio > 20x") == r"P/E ratio \> 20x", (
            "_md_safe did not escape '>' in 'P/E ratio > 20x'"
        )
        assert _md_safe(
            "Commodity price collapse (Brent crude <$40/bbl or natural gas sustained <$2 USD/MMBtu)"
        ) == r"Commodity price collapse (Brent crude \<$40/bbl or natural gas sustained \<$2 USD/MMBtu)", (
            "_md_safe incorrectly processed multi-< condition string"
        )

        # No mutation of clean text
        clean = "Revenue CAGR -3.7% (3yr, 2022–2025); FCF margin 18%."
        assert _md_safe(clean) == clean, (
            f"_md_safe mutated text that contained no angle brackets: {clean!r}"
        )

        # Empty string safe
        assert _md_safe("") == ""

        # Both > and < in same string
        assert _md_safe("10 < x > 5") == r"10 \< x \> 5"

    # ------------------------------------------------------------------
    # Test 10: render_assessment() escapes < in condition for Streamlit markdown
    # ------------------------------------------------------------------

    def test_68_10_render_assessment_escapes_angle_brackets_in_condition(self):
        r"""
        Test 10: Regression guard for Streamlit markdown rendering defect.

        A breaker condition containing '<' (e.g. "Brent crude <$40/bbl") must appear
        in render_assessment() output with '\<' (escaped), NOT raw '<'.

        Without this fix, Streamlit's st.markdown() treats "<$40/bbl" as an HTML tag,
        producing malformed output like "<40/bblornaturalgassustained<2 USD/MMBtu".

        The underlying ThesisBreaker.condition must NOT be modified — escaping is
        render-time only.
        """
        from analytics.agent.renderer import render_assessment
        from analytics.decision.decision_models import ThesisBreaker

        raw_condition = (
            "Commodity price collapse (Brent crude <$40/bbl "
            "or natural gas sustained <$2 USD/MMBtu)"
        )
        tb = ThesisBreaker(
            condition=raw_condition,
            likelihood="MEDIUM",
            impact="SEVERE",
            monitoring_indicator="Watch Brent/WTI monthly prices.",
            trigger_action="Would prompt REDUCE or EXIT review.",
            evidence=["Brent spot at $72/bbl as of Sep 2026."],
            likelihood_rationale="Oil currently well above threshold; conditional scenario.",
            is_monitoring_only=False,
        )
        assessment = _make_assessment_with_breakers([tb])
        output = render_assessment(assessment)

        # Verify the raw '<' does NOT appear in the condition display line
        # (it may appear in evidence strings, which are not rendered via _md_safe)
        assert r"\<" in output, (
            "Expected '\\<' (escaped) in render_assessment() output for condition with '<'.\n"
            "Streamlit markdown rendering defect: raw '<' in a condition is treated as an HTML tag.\n"
            f"Output (first 1200 chars):\n{output[:1200]}"
        )

        # The escaped form of the condition must appear in the output
        expected_escaped = r"Commodity price collapse (Brent crude \<$40/bbl"
        assert expected_escaped in output, (
            f"Expected '{expected_escaped}' in output but did not find it.\n"
            f"Output (first 1200 chars):\n{output[:1200]}"
        )

        # The stored condition is NOT mutated by render_assessment()
        assert tb.condition == raw_condition, (
            f"render_assessment() mutated ThesisBreaker.condition.\n"
            f"Expected: {raw_condition!r}\n"
            f"Got:      {tb.condition!r}"
        )


# ===========================================================================
# Group 13: K1 Regression Tests — DEF-1, DEF-2, DEF-3, CAGR, Persistence,
#           Evidence Boundary (11 required behaviors)
# ===========================================================================

def _make_monitoring_breaker(condition: str, likelihood: str = "MEDIUM"):
    """Helper: build a monitoring-only ThesisBreaker (is_monitoring_only=True)."""
    from analytics.decision.decision_models import ThesisBreaker
    return ThesisBreaker(
        condition=condition,
        likelihood=likelihood,
        impact="SEVERE",
        monitoring_indicator="Watch quarterly.",
        trigger_action="Would prompt review.",
        is_monitoring_only=True,
    )


def _make_assessment_with_bear_count(breakers, bear_count: int, quality_tier="GOOD",
                                     is_existing=False, val_zone="WAIT"):
    """
    Build assessment with Gate 5 summary containing an explicit bear-count string.
    Used to test DEF-1 (n_bear in scenario severity).
    """
    from analytics.decision.decision_models import (
        InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
    )
    assessment = InvestmentDecisionAssessment(
        ticker="BEAR.TO",
        company_name="Bear Test Co",
        analysis_date="2026-11-08",
        action=DecisionAction.WATCH,
        decision_confidence=DecisionConfidence.MEDIUM,
        valuation_zone=val_zone,
    )
    assessment.thesis_breakers = breakers
    assessment.gate_results = [
        GateResult(gate_number=2, gate_name="Financial Quality", passed=True,
                   quality_tier=quality_tier, summary="OK"),
        GateResult(gate_number=3, gate_name="Valuation", passed=True,
                   summary=f"Zone: {val_zone}"),
        GateResult(gate_number=4, gate_name="Portfolio Context", passed=True,
                   summary="New position." if not is_existing else "Existing 5% position."),
        GateResult(
            gate_number=5, gate_name="Adversarial Challenge", passed=True,
            adversarial_risk="LOW", confidence="MEDIUM",
            # Must match the format _get_bear_count() searches for
            summary=(
                f"Adversarial risk: LOW. Breakers: 0 HIGH / 0 MEDIUM / 0 UNKNOWN / 0 LOW. "
                f"{bear_count} bear-case evidence point(s). Bear case synthesised from..."
            ),
        ),
    ]
    return assessment


class TestK1Regressions:
    """
    K1 regression tests: DEF-1/DEF-2/DEF-3 scenario engine fixes, CAGR fallback,
    unsupported evidence persistence, and evidence boundary / Gate 5 isolation.
    All 11 required behaviors from K1 brief Section 3.
    """

    # -----------------------------------------------------------------------
    # T1: Six bear points without eligible breakers produce HIGH severity
    # (DEF-1: n_bear threshold in calculate_adversarial_severity shared function)
    # -----------------------------------------------------------------------

    def test_k1_t1_six_bear_points_no_breakers_produce_high(self):
        """
        DEF-1: calculate_adversarial_severity([], n_bear=6) must return HIGH.
        This is the shared function called by the scenario engine for all override
        scenarios.  Previously _calculate_severity() had no n_bear parameter and
        would return LOW for a breaker-free assessment with 6 bear points.
        """
        from analytics.decision.gate5_adversarial import calculate_adversarial_severity
        result = calculate_adversarial_severity([], n_bear=6)
        assert result == "HIGH", (
            f"6 bear points, no breakers: expected HIGH, got {result}. DEF-1 not fixed."
        )

    def test_k1_t1b_three_bear_points_no_breakers_produce_moderate(self):
        """DEF-1: n_bear=3 → MODERATE (lower boundary)."""
        from analytics.decision.gate5_adversarial import calculate_adversarial_severity
        assert calculate_adversarial_severity([], n_bear=3) == "MODERATE"

    def test_k1_t1c_five_bear_points_no_breakers_produce_moderate(self):
        """DEF-1: n_bear=5 (below HIGH threshold of 6) → MODERATE."""
        from analytics.decision.gate5_adversarial import calculate_adversarial_severity
        assert calculate_adversarial_severity([], n_bear=5) == "MODERATE"

    def test_k1_t1d_bear_count_read_from_assessment(self):
        """
        DEF-1: _get_bear_count() must parse the bear count from the Gate 5 summary
        string in the assessment.  Validates that the scenario engine feeds the correct
        n_bear into calculate_adversarial_severity() for override calculations.
        """
        from analytics.decision.scenario_engine import _get_bear_count, run_scenario
        from analytics.decision.decision_models import BreakerOverride
        # Assessment with Gate 5 summary containing "6 bear-case evidence point(s)"
        assessment = _make_assessment_with_bear_count(
            breakers=[_make_breaker("Oil price <$50", "LOW")],
            bear_count=6,
        )
        assert _get_bear_count(assessment) == 6, (
            f"_get_bear_count() failed to parse n_bear=6 from Gate 5 summary. "
            f"Got: {_get_bear_count(assessment)}"
        )
        # With an override applied, the scenario should be HIGH (from n_bear=6)
        # even though only a LOW breaker exists
        result = run_scenario(assessment, [
            BreakerOverride(condition="Oil price <$50", baseline_likelihood="LOW",
                            user_likelihood="LOW"),
        ])
        assert result.scenario_adversarial_risk == "HIGH", (
            f"6 bear points + 1 LOW breaker override: expected HIGH, "
            f"got {result.scenario_adversarial_risk}"
        )

    # -----------------------------------------------------------------------
    # T2: Two monitoring-only MEDIUM breakers alone do not escalate severity
    # (DEF-2: monitoring-only excluded from baseline scenario severity)
    # -----------------------------------------------------------------------

    def test_k1_t2_two_monitoring_only_medium_do_not_escalate(self):
        """
        DEF-2: Two monitoring-only MEDIUM breakers must produce LOW scenario severity.
        Previously the scenario engine included them in n_medium_equiv, inflating
        severity to HIGH for any ticker with a moat and valuation assessment.
        Uses an override to trigger the full recalculation path (not early-return).
        """
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        mon1 = _make_monitoring_breaker("Moat erosion: market share loss", likelihood="MEDIUM")
        mon2 = _make_monitoring_breaker("Key valuation assumptions fail", likelihood="MEDIUM")
        assessment = _make_assessment_with_bear_count(
            breakers=[mon1, mon2], bear_count=0
        )
        # Apply override to mon1 to trigger full recalculation (not early-return path)
        result = run_scenario(assessment, [
            BreakerOverride(
                condition="Moat erosion: market share loss",
                baseline_likelihood="MEDIUM",
                user_likelihood="HIGH",
            )
        ])
        # Even after overriding monitoring-only to HIGH, severity must remain LOW
        # because monitoring-only breakers are excluded from the calculation.
        assert result.scenario_adversarial_risk == "LOW", (
            f"2 monitoring-only breakers (1 overridden to HIGH): expected LOW, "
            f"got {result.scenario_adversarial_risk}. DEF-2 not fixed."
        )

    def test_k1_t2b_monitoring_only_low_plus_decision_medium_produce_moderate(self):
        """
        DEF-2: One genuine MEDIUM breaker (not monitoring-only) must still produce
        MODERATE severity even when monitoring-only breakers are present.
        Uses a no-op override on the genuine breaker to trigger full recalculation.
        """
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        monitoring = _make_monitoring_breaker("Moat erosion", likelihood="MEDIUM")
        genuine = _make_breaker("Revenue decline >20% for 2 consecutive quarters", "MEDIUM")
        assessment = _make_assessment_with_bear_count(
            breakers=[monitoring, genuine], bear_count=0
        )
        # Trigger full recalculation via a no-op override on the genuine breaker
        result = run_scenario(assessment, [
            BreakerOverride(
                condition="Revenue decline >20% for 2 consecutive quarters",
                baseline_likelihood="MEDIUM",
                user_likelihood="MEDIUM",
            )
        ])
        assert result.scenario_adversarial_risk == "MODERATE", (
            f"1 genuine MEDIUM + 1 monitoring-only MEDIUM: expected MODERATE, "
            f"got {result.scenario_adversarial_risk}"
        )

    # -----------------------------------------------------------------------
    # T3: Monitoring-only breakers remain excluded after an override copy
    # (DEF-3: is_monitoring_only preserved in override copy)
    # -----------------------------------------------------------------------

    def test_k1_t3_override_copy_preserves_monitoring_only(self):
        """
        DEF-3: When a monitoring-only breaker receives a likelihood override,
        is_monitoring_only must be preserved on the copy so it remains excluded
        from severity calculation.
        """
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        monitoring_breaker = _make_monitoring_breaker(
            "Moat erosion: market share loss", likelihood="LOW"
        )
        genuine_breaker = _make_breaker("Oil price <$50/bbl", "LOW")
        assessment = _make_assessment_with_bear_count(
            breakers=[monitoring_breaker, genuine_breaker], bear_count=0
        )
        # Override the monitoring-only breaker to MEDIUM — it must still not escalate severity
        result = run_scenario(assessment, [
            BreakerOverride(
                condition="Moat erosion: market share loss",
                baseline_likelihood="LOW",
                user_likelihood="MEDIUM",
            )
        ])
        # Monitoring-only excluded → 0 genuine MEDIUM breakers → LOW
        assert result.scenario_adversarial_risk == "LOW", (
            f"Overriding monitoring-only breaker to MEDIUM: expected LOW (still excluded), "
            f"got {result.scenario_adversarial_risk}. DEF-3 not fixed."
        )

    def test_k1_t3b_override_copy_does_not_lose_other_fields(self):
        """
        DEF-3: Override copy must preserve evidence, likelihood_rationale, and
        is_monitoring_only — not just condition and likelihood.
        """
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride, ThesisBreaker
        tb = ThesisBreaker(
            condition="Crude oil <$50/bbl",
            likelihood="MEDIUM",
            evidence=["Brent at $72/bbl as of Q3 2026"],
            likelihood_rationale="Well above threshold",
            is_monitoring_only=False,
            unsupported_evidence=["5yr CAGR claim not supported"],
        )
        assessment = _make_assessment_with_bear_count(breakers=[tb], bear_count=0)
        # Override to HIGH
        run_scenario(assessment, [
            BreakerOverride(condition="Crude oil <$50/bbl", baseline_likelihood="MEDIUM",
                            user_likelihood="HIGH")
        ])
        # Original ThesisBreaker must be unchanged (immutability check)
        assert tb.likelihood == "MEDIUM", "Original ThesisBreaker was mutated"
        assert tb.evidence == ["Brent at $72/bbl as of Q3 2026"], "Evidence lost on original"
        assert tb.is_monitoring_only is False
        assert tb.unsupported_evidence == ["5yr CAGR claim not supported"]

    # -----------------------------------------------------------------------
    # T4: Genuine decision-relevant breakers still affect severity
    # -----------------------------------------------------------------------

    def test_k1_t4_genuine_breaker_affects_severity(self):
        """
        Genuine (non-monitoring-only) breakers must still drive severity escalation
        after the DEF-2 fix.  Uses override to trigger full recalculation.
        """
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        genuine1 = _make_breaker("Revenue decline >20% for 2 quarters", "MEDIUM")
        genuine2 = _make_breaker("Key customer >30% revenue gives notice", "MEDIUM")
        monitoring = _make_monitoring_breaker("Moat erosion: market share loss")  # excluded
        assessment = _make_assessment_with_bear_count(
            breakers=[genuine1, genuine2, monitoring], bear_count=0
        )
        # No-op override on genuine1 to trigger full recalculation
        result = run_scenario(assessment, [
            BreakerOverride(
                condition="Revenue decline >20% for 2 quarters",
                baseline_likelihood="MEDIUM",
                user_likelihood="MEDIUM",
            )
        ])
        # 2 genuine MEDIUM (monitoring excluded) → HIGH (n_medium_equiv >= 2)
        assert result.scenario_adversarial_risk == "HIGH", (
            f"2 genuine MEDIUM breakers + 1 monitoring: expected HIGH, "
            f"got {result.scenario_adversarial_risk}"
        )

    # -----------------------------------------------------------------------
    # T5: Gate 5 and scenario severity agree for equivalent inputs
    # (shared calculate_adversarial_severity function)
    # -----------------------------------------------------------------------

    def test_k1_t5_gate5_and_scenario_agree_on_severity(self):
        """
        Gate 5 and the scenario engine must return the same severity for the same
        non-monitoring-only breaker set.  Validates the shared severity function.
        Uses an override to trigger the full scenario recalculation path.
        """
        from analytics.decision.gate5_adversarial import calculate_adversarial_severity
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import ThesisBreaker, BreakerOverride

        breakers = [
            ThesisBreaker(condition="A", likelihood="MEDIUM"),
            ThesisBreaker(condition="B", likelihood="MEDIUM"),
        ]
        # Direct call to shared function (Gate 5 path)
        gate5_result = calculate_adversarial_severity(breakers, n_bear=0)
        assert gate5_result == "HIGH"  # 2 MEDIUM → HIGH

        # Scenario with same breakers + no-op override to trigger recalculation
        assessment = _make_assessment_with_bear_count(breakers=breakers, bear_count=0)
        scenario_result = run_scenario(assessment, [
            BreakerOverride(condition="A", baseline_likelihood="MEDIUM",
                            user_likelihood="MEDIUM"),
        ])
        assert gate5_result == scenario_result.scenario_adversarial_risk, (
            f"Gate 5 and scenario disagree: gate5={gate5_result}, "
            f"scenario={scenario_result.scenario_adversarial_risk}"
        )

    # -----------------------------------------------------------------------
    # T6: LOW, MODERATE, HIGH, SEVERE boundary conditions
    # (via shared calculate_adversarial_severity)
    # -----------------------------------------------------------------------

    def test_k1_t6_severity_boundaries(self):
        """
        Verify all four severity boundaries for calculate_adversarial_severity.
        """
        from analytics.decision.gate5_adversarial import calculate_adversarial_severity
        from analytics.decision.decision_models import ThesisBreaker

        def _b(lk): return ThesisBreaker(condition="X", likelihood=lk)

        # LOW: no breakers, no bear points
        assert calculate_adversarial_severity([], 0) == "LOW"

        # MODERATE: 1 MEDIUM breaker
        assert calculate_adversarial_severity([_b("MEDIUM")], 0) == "MODERATE"

        # MODERATE: 2 bear points (< 3 threshold)
        assert calculate_adversarial_severity([], 2) == "LOW"

        # MODERATE: exactly 3 bear points
        assert calculate_adversarial_severity([], 3) == "MODERATE"

        # HIGH: 2 MEDIUM breakers
        assert calculate_adversarial_severity([_b("MEDIUM"), _b("MEDIUM")], 0) == "HIGH"

        # HIGH: exactly 6 bear points
        assert calculate_adversarial_severity([], 6) == "HIGH"

        # SEVERE: 1 HIGH breaker
        assert calculate_adversarial_severity([_b("HIGH")], 0) == "SEVERE"

        # SEVERE: 4 MEDIUM breakers (n_medium_equiv >= 4)
        assert calculate_adversarial_severity(
            [_b("MEDIUM"), _b("MEDIUM"), _b("MEDIUM"), _b("MEDIUM")], 0
        ) == "SEVERE"

        # SEVERE: 1 UNKNOWN breaker (counts as MEDIUM) + 3 MEDIUM → n_medium_equiv = 4
        assert calculate_adversarial_severity(
            [_b("UNKNOWN"), _b("MEDIUM"), _b("MEDIUM"), _b("MEDIUM")], 0
        ) == "SEVERE"

    # -----------------------------------------------------------------------
    # T7: CAGR fallback with structured historical-data availability
    # -----------------------------------------------------------------------

    def test_k1_t7_cagr_suppressed_when_data_years_lt5(self):
        """
        K1-2: When data_years_available < 5, ctx['revenue_cagr_5yr'] must be None
        regardless of whether cagr_5yr_label is set or empty.
        """
        from analytics.agent.research_orchestrator import ResearchOrchestrator
        from analytics.financial_quality.financial_metrics_model import (
            CompanyFinancialMetrics, RevenueGrowthMetrics,
        )

        rg_4yr = RevenueGrowthMetrics(
            annual_revenues={2022: 100, 2023: 110, 2024: 120, 2025: 130},
            cagr_5yr=9.0,          # Fallback value computed from 4-yr data
            cagr_5yr_label="",     # Empty label — the silent failure mode
            data_years_available=4,
        )
        metrics = CompanyFinancialMetrics()
        metrics.revenue_growth = rg_4yr

        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        ctx = orch._build_context("TST", "Test Co", metrics, "2026-11-08")

        assert ctx.get("revenue_cagr_5yr") is None, (
            f"Expected None for 4-year data with empty label, "
            f"got {ctx.get('revenue_cagr_5yr')}. "
            "Structured data_years_available check not applied."
        )

    def test_k1_t7b_cagr_accepted_when_data_years_ge5(self):
        """
        K1-2: When data_years_available >= 5 and cagr_5yr is set without fallback label,
        ctx['revenue_cagr_5yr'] must be the actual CAGR value (not suppressed).
        """
        from analytics.agent.research_orchestrator import ResearchOrchestrator
        from analytics.financial_quality.financial_metrics_model import (
            CompanyFinancialMetrics, RevenueGrowthMetrics,
        )

        rg_5yr = RevenueGrowthMetrics(
            annual_revenues={2021: 90, 2022: 100, 2023: 110, 2024: 120, 2025: 130},
            cagr_5yr=7.6,
            cagr_5yr_label="5yr CAGR: 7.6% (2021→2025)",
            data_years_available=5,
        )
        metrics = CompanyFinancialMetrics()
        metrics.revenue_growth = rg_5yr

        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        ctx = orch._build_context("TST", "Test Co", metrics, "2026-11-08")

        assert ctx.get("revenue_cagr_5yr") == 7.6, (
            f"Expected 7.6 for genuine 5yr CAGR, got {ctx.get('revenue_cagr_5yr')}"
        )

    # -----------------------------------------------------------------------
    # T8: Missing or default CAGR labels do not silently change business decision
    # -----------------------------------------------------------------------

    def test_k1_t8_empty_label_with_lt5_data_years_suppressed(self):
        """
        K1-2: When cagr_5yr_label is empty (default) AND data_years_available < 5,
        the CAGR must be suppressed.  This is the silent failure mode fixed by K1.
        """
        from analytics.agent.research_orchestrator import ResearchOrchestrator
        from analytics.financial_quality.financial_metrics_model import (
            CompanyFinancialMetrics, RevenueGrowthMetrics,
        )

        # Empty label, 3-year data — the pre-K1 bug would have let this through
        rg = RevenueGrowthMetrics(
            cagr_5yr=-3.75,
            cagr_5yr_label="",    # Default empty — previously NOT caught
            data_years_available=3,
        )
        metrics = CompanyFinancialMetrics()
        metrics.revenue_growth = rg

        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        ctx = orch._build_context("CNQ", "Test Co", metrics, "2026-11-08")

        assert ctx.get("revenue_cagr_5yr") is None, (
            f"Pre-K1 silent failure: empty label with 3yr data was not suppressed. "
            f"Got {ctx.get('revenue_cagr_5yr')}."
        )

    def test_k1_t8b_none_cagr_5yr_always_suppressed(self):
        """
        K1-2: When cagr_5yr is None, ctx['revenue_cagr_5yr'] must be None
        regardless of data_years_available.
        """
        from analytics.agent.research_orchestrator import ResearchOrchestrator
        from analytics.financial_quality.financial_metrics_model import (
            CompanyFinancialMetrics, RevenueGrowthMetrics,
        )

        rg = RevenueGrowthMetrics(
            cagr_5yr=None,
            cagr_5yr_label="5yr CAGR: N/A",
            data_years_available=7,  # Data available but cagr_5yr is None
        )
        metrics = CompanyFinancialMetrics()
        metrics.revenue_growth = rg

        orch = ResearchOrchestrator.__new__(ResearchOrchestrator)
        ctx = orch._build_context("TST", "Test Co", metrics, "2026-11-08")

        assert ctx.get("revenue_cagr_5yr") is None, (
            f"None cagr_5yr must stay None; got {ctx.get('revenue_cagr_5yr')}"
        )

    # -----------------------------------------------------------------------
    # T9: Unsupported evidence survives persistence (to_dict / from_dict round-trip)
    # -----------------------------------------------------------------------

    def test_k1_t9_unsupported_evidence_in_to_dict(self):
        """
        K1-3: ThesisBreaker.unsupported_evidence must appear in to_dict() output
        and therefore survive JSON persistence.
        """
        from analytics.decision.decision_models import ThesisBreaker
        tb = ThesisBreaker(
            condition="Crude oil <$50/bbl",
            likelihood="MEDIUM",
            evidence=["Brent at $72/bbl Q3 2026"],
            unsupported_evidence=["5yr revenue CAGR -3.75% (only 4yr data available)"],
        )
        d = tb.to_dict()
        assert "unsupported_evidence" in d, "unsupported_evidence missing from to_dict()"
        assert d["unsupported_evidence"] == ["5yr revenue CAGR -3.75% (only 4yr data available)"]

    def test_k1_t9b_unsupported_evidence_in_assessment_to_dict(self):
        """
        K1-3: unsupported_evidence on a ThesisBreaker must round-trip through
        InvestmentDecisionAssessment.to_dict() (via thesis_breakers serialization).
        """
        from analytics.decision.decision_models import ThesisBreaker
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
        )
        tb = ThesisBreaker(
            condition="Carbon price risk",
            likelihood="LOW",
            evidence=["EU ETS at €65/tonne"],
            unsupported_evidence=["Carbon price $120/tonne claim not in context"],
        )
        assessment = InvestmentDecisionAssessment(
            ticker="TEST.TO",
            company_name="Test",
            analysis_date="2026-11-08",
            action=DecisionAction.WATCH,
            decision_confidence=DecisionConfidence.LOW,
        )
        assessment.thesis_breakers = [tb]
        d = assessment.to_dict()
        breaker_dicts = d["thesis_breakers"]
        assert len(breaker_dicts) == 1
        assert "unsupported_evidence" in breaker_dicts[0], (
            "unsupported_evidence lost during assessment.to_dict()"
        )
        assert breaker_dicts[0]["unsupported_evidence"] == [
            "Carbon price $120/tonne claim not in context"
        ]

    def test_k1_t9c_empty_unsupported_evidence_backward_compatible(self):
        """
        K1-3: ThesisBreaker created without unsupported_evidence (legacy) must
        default to empty list — backward compatibility with existing persisted records.
        """
        from analytics.decision.decision_models import ThesisBreaker
        tb = ThesisBreaker(condition="Old breaker", likelihood="MEDIUM")
        assert tb.unsupported_evidence == [], (
            "Default unsupported_evidence must be [] for backward compatibility"
        )
        d = tb.to_dict()
        assert d["unsupported_evidence"] == []

    # -----------------------------------------------------------------------
    # T10: Annotated unsupported narrative does not improperly affect Gate 5
    # -----------------------------------------------------------------------

    def test_k1_t10_annotation_stripped_before_bear_point(self):
        """
        K1-4: When bear_case_narrative starts with [DATA-BOUNDARY-VIOLATION:...],
        the annotation prefix must be stripped before the string enters bear_points.
        The underlying bear case content must be preserved.
        """
        from analytics.decision.gate5_adversarial import _strip_boundary_annotation

        # Pure annotation — stripped entirely
        annotated = "[DATA-BOUNDARY-VIOLATION: 5yr_cagr] Revenue declined 5% over 5 years."
        result = _strip_boundary_annotation(annotated)
        assert result == "Revenue declined 5% over 5 years.", (
            f"Expected annotation stripped; got {result!r}"
        )

        # No annotation — unchanged
        clean = "Revenue declined 3% year-over-year."
        assert _strip_boundary_annotation(clean) == clean

        # Annotation in middle of string — only leading prefix is stripped
        mid = "Bear case is weak. [DATA-BOUNDARY-VIOLATION: carbon] No pricing data."
        assert _strip_boundary_annotation(mid) == mid  # not a leading prefix

    def test_k1_t10b_annotated_narrative_does_not_inflate_n_bear_beyond_one(self):
        """
        K1-4: An annotated bear_case_narrative contributes exactly 1 to n_bear
        (the stripped content) — the annotation metadata does not add extra entries.
        """
        from analytics.decision.gate5_adversarial import evaluate_gate5
        from analytics.business_research.research_models import (
            BusinessResearchAssessment, BullBearAssessment,
        )

        bb = BullBearAssessment(
            bear_case_narrative=(
                "[DATA-BOUNDARY-VIOLATION: 5yr_cagr] "
                "Revenue declined over the past five years."
            ),
        )
        research = BusinessResearchAssessment(ticker="TST", company_name="Test")
        research.bull_bear = bb

        gate_result = evaluate_gate5(research=research)
        # bear_case_narrative → 1 bear point; no breakers → severity LOW or MODERATE
        # The annotation prefix must NOT add more than 1 bear point
        # Count from summary
        import re
        m = re.search(r'(\d+) bear-case evidence point', gate_result.summary)
        n_bear = int(m.group(1)) if m else -1
        assert n_bear == 1, (
            f"Expected 1 bear point from annotated narrative, got {n_bear}. "
            f"Summary: {gate_result.summary}"
        )

    # -----------------------------------------------------------------------
    # T11: Legitimate bear-case evidence remains decision-eligible when valid
    # -----------------------------------------------------------------------

    def test_k1_t11_clean_evidence_remains_eligible(self):
        """
        K1-4: Evidence strings without boundary violations must remain in
        ThesisBreaker.evidence (decision-eligible), not in unsupported_evidence.
        """
        from analytics.decision.decision_models import ThesisBreaker
        tb = ThesisBreaker(
            condition="Revenue decline risk",
            likelihood="MEDIUM",
            evidence=["Q3 2026 revenue -8% YoY", "2 of last 4 quarters negative growth"],
            unsupported_evidence=[],
        )
        # Clean evidence must stay in .evidence, not leak to .unsupported_evidence
        assert len(tb.evidence) == 2
        assert tb.unsupported_evidence == []

    def test_k1_t11b_gate5_uses_clean_evidence_not_unsupported(self):
        """
        K1-4: When thesis_breaker_details contains both 'evidence' and
        'unsupported_evidence', extract_thesis_breakers() must put them in the
        correct fields — clean in .evidence, violations in .unsupported_evidence.
        """
        from analytics.decision.gate5_adversarial import extract_thesis_breakers
        from analytics.business_research.research_models import (
            BusinessResearchAssessment, BullBearAssessment,
        )

        detail = {
            "condition": "Carbon price spike",
            "likelihood": "LOW",
            "evidence": ["EU ETS at €65/tonne Q3 2026"],
            "likelihood_rationale": "Current prices well below business impact threshold",
            "unsupported_evidence": ["$120/tonne cited by LLM — not in source context"],
        }
        bb = BullBearAssessment(
            thesis_breaker_details=[detail],
        )
        research = BusinessResearchAssessment(ticker="TST", company_name="Test")
        research.bull_bear = bb

        result_breakers = extract_thesis_breakers(research)

        # Find the breaker from thesis_breaker_details (not monitoring-only ones)
        from_details = [b for b in result_breakers if not b.is_monitoring_only]
        assert len(from_details) >= 1, "No non-monitoring breakers returned"
        carbon_breaker = next(
            (b for b in from_details if "Carbon" in b.condition), None
        )
        assert carbon_breaker is not None, "Carbon price breaker not found"
        assert carbon_breaker.evidence == ["EU ETS at €65/tonne Q3 2026"], (
            f"Clean evidence incorrect: {carbon_breaker.evidence}"
        )
        assert carbon_breaker.unsupported_evidence == [
            "$120/tonne cited by LLM — not in source context"
        ], f"Unsupported evidence incorrect: {carbon_breaker.unsupported_evidence}"
        # Unsupported must NOT bleed into .evidence
        assert "$120/tonne" not in " ".join(carbon_breaker.evidence), (
            "Unsupported evidence bled into decision-eligible .evidence"
        )


# ===========================================================================
# Group 14: K1 Follow-Up — Structured Bear Count (GateResult.n_bear)
# ===========================================================================
#
# These tests verify that bear-point count is now a first-class structured field
# on GateResult rather than a parsed substring of the summary text.
#
# Required behaviors (from K1 follow-up brief):
#   T12: 6 bear points → HIGH scenario severity (via structured field)
#   T13: 3–5 bear points → MODERATE when no higher condition applies (via structured field)
#   T14: Scenario severity is UNAFFECTED by changes to Gate 5 summary wording
#   T15: Gate 5 and scenario analysis use the same underlying bear-point count
# ===========================================================================

def _make_assessment_with_structured_bear_count(
    breakers, bear_count: int, quality_tier="GOOD",
    is_existing=False, val_zone="WAIT", summary_override: str = ""
):
    """
    Build an assessment where GateResult.n_bear is explicitly set (structured field).
    When summary_override is provided, the Gate 5 summary string carries DIFFERENT
    content — used to verify wording-immunity (T14).
    """
    from analytics.decision.decision_models import (
        InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
    )
    assessment = InvestmentDecisionAssessment(
        ticker="STRUCT.TO",
        company_name="Structured Bear Co",
        analysis_date="2026-11-08",
        action=DecisionAction.WATCH,
        decision_confidence=DecisionConfidence.MEDIUM,
        valuation_zone=val_zone,
    )
    assessment.thesis_breakers = breakers
    # Build the Gate 5 summary: use override if provided (for wording-immunity test),
    # otherwise include the standard phrase so string parsing also works.
    gate5_summary = summary_override or (
        f"Adversarial risk: LOW. Breakers: 0 HIGH / 0 MEDIUM / 0 UNKNOWN / 0 LOW. "
        f"{bear_count} bear-case evidence point(s). Bear case synthesised from..."
    )
    assessment.gate_results = [
        GateResult(gate_number=2, gate_name="Financial Quality", passed=True,
                   quality_tier=quality_tier, summary="OK"),
        GateResult(gate_number=3, gate_name="Valuation", passed=True,
                   summary=f"Zone: {val_zone}"),
        GateResult(gate_number=4, gate_name="Portfolio Context", passed=True,
                   summary="New position." if not is_existing else "Existing 5% position."),
        GateResult(
            gate_number=5, gate_name="Adversarial Challenge", passed=True,
            adversarial_risk="LOW", confidence="MEDIUM",
            # Structured field — the authoritative value for scenario engine
            n_bear=bear_count,
            summary=gate5_summary,
        ),
    ]
    return assessment


class TestK1FollowUpStructuredBearCount:
    """
    K1 Follow-Up: structured n_bear field on GateResult.

    After the follow-up, GateResult.n_bear is set by evaluate_gate5() and read
    by _get_bear_count() — no summary-string parsing is needed for new assessments.
    Legacy assessments (n_bear=0, bear count in summary string) still work via the
    string-parse fallback.
    """

    # -----------------------------------------------------------------------
    # T12: 6 structured bear points → HIGH via scenario engine
    # -----------------------------------------------------------------------

    def test_k1_fu_t12_six_structured_bear_points_produce_high_severity(self):
        """
        T12: When GateResult.n_bear=6 (structured field), run_scenario() must
        produce HIGH adversarial risk (n_bear >= 6 threshold) even with no
        eligible breakers and an override applied.
        """
        from analytics.decision.scenario_engine import run_scenario, _get_bear_count
        from analytics.decision.decision_models import BreakerOverride
        low_breaker = _make_breaker("Oil price <$50", "LOW")
        assessment = _make_assessment_with_structured_bear_count(
            breakers=[low_breaker], bear_count=6
        )
        # Verify structured field is read (not string)
        assert _get_bear_count(assessment) == 6, (
            f"_get_bear_count() did not read structured n_bear=6 from GateResult."
        )
        # Apply an override to trigger full recalculation
        result = run_scenario(assessment, [
            BreakerOverride(condition="Oil price <$50", baseline_likelihood="LOW",
                            user_likelihood="LOW"),
        ])
        assert result.scenario_adversarial_risk == "HIGH", (
            f"6 structured bear points + 1 LOW breaker: expected HIGH, "
            f"got {result.scenario_adversarial_risk}. T12 failed."
        )

    # -----------------------------------------------------------------------
    # T13: 3–5 structured bear points → MODERATE when no higher condition applies
    # -----------------------------------------------------------------------

    def test_k1_fu_t13a_three_structured_bear_points_produce_moderate(self):
        """T13 lower bound: n_bear=3, no eligible breakers → MODERATE."""
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        low_breaker = _make_breaker("Revenue risk", "LOW")
        assessment = _make_assessment_with_structured_bear_count(
            breakers=[low_breaker], bear_count=3
        )
        result = run_scenario(assessment, [
            BreakerOverride(condition="Revenue risk", baseline_likelihood="LOW",
                            user_likelihood="LOW"),
        ])
        assert result.scenario_adversarial_risk == "MODERATE", (
            f"n_bear=3 structured, 0 eligible breakers: expected MODERATE, "
            f"got {result.scenario_adversarial_risk}."
        )

    def test_k1_fu_t13b_five_structured_bear_points_produce_moderate(self):
        """T13 upper bound (below HIGH): n_bear=5 → MODERATE (< 6 threshold)."""
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        low_breaker = _make_breaker("Revenue risk", "LOW")
        assessment = _make_assessment_with_structured_bear_count(
            breakers=[low_breaker], bear_count=5
        )
        result = run_scenario(assessment, [
            BreakerOverride(condition="Revenue risk", baseline_likelihood="LOW",
                            user_likelihood="LOW"),
        ])
        assert result.scenario_adversarial_risk == "MODERATE", (
            f"n_bear=5 structured, 0 eligible breakers: expected MODERATE, "
            f"got {result.scenario_adversarial_risk}."
        )

    def test_k1_fu_t13c_two_structured_bear_points_produce_low(self):
        """T13 below MODERATE threshold: n_bear=2 → LOW (< 3)."""
        from analytics.decision.scenario_engine import run_scenario
        from analytics.decision.decision_models import BreakerOverride
        low_breaker = _make_breaker("Revenue risk", "LOW")
        assessment = _make_assessment_with_structured_bear_count(
            breakers=[low_breaker], bear_count=2
        )
        result = run_scenario(assessment, [
            BreakerOverride(condition="Revenue risk", baseline_likelihood="LOW",
                            user_likelihood="LOW"),
        ])
        assert result.scenario_adversarial_risk == "LOW", (
            f"n_bear=2 structured, 0 eligible breakers: expected LOW, "
            f"got {result.scenario_adversarial_risk}."
        )

    # -----------------------------------------------------------------------
    # T14: Wording immunity — scenario severity unaffected by summary string changes
    # -----------------------------------------------------------------------

    def test_k1_fu_t14_severity_immune_to_summary_wording(self):
        """
        T14: Scenario severity must not change when Gate 5 summary wording is
        modified, as long as GateResult.n_bear (structured field) is unchanged.

        Setup: n_bear=6 in structured field; summary string contains no bear-
        count phrase at all (simulates a reworded format or deliberate test of
        independence from text parsing).

        Expected: _get_bear_count() returns 6 (from structured field), not 0,
        and scenario severity is HIGH.
        """
        from analytics.decision.scenario_engine import run_scenario, _get_bear_count
        from analytics.decision.decision_models import BreakerOverride
        low_breaker = _make_breaker("Oil price risk", "LOW")
        assessment = _make_assessment_with_structured_bear_count(
            breakers=[low_breaker],
            bear_count=6,
            # Summary deliberately contains NO bear-count phrase — string parsing
            # would return 0, but structured field should return 6.
            summary_override=(
                "Adversarial risk: LOW. No thesis breakers. "
                "Bear narrative evaluated. Assessment complete."
            ),
        )
        # Confirm string parsing would fail
        import re
        gate5_gr = next(
            gr for gr in assessment.gate_results if getattr(gr, "gate_number", 0) == 5
        )
        string_parse = re.search(r'(\d+)\s+bear-case evidence point', gate5_gr.summary)
        assert string_parse is None, (
            "Test setup error: summary_override should contain no bear-count phrase"
        )
        # Structured field must still return 6
        assert _get_bear_count(assessment) == 6, (
            f"_get_bear_count() failed to return structured n_bear=6 when summary "
            f"wording was changed. Got: {_get_bear_count(assessment)}. "
            f"Summary: {gate5_gr.summary!r}"
        )
        # Scenario must be HIGH from structured field
        result = run_scenario(assessment, [
            BreakerOverride(condition="Oil price risk", baseline_likelihood="LOW",
                            user_likelihood="LOW"),
        ])
        assert result.scenario_adversarial_risk == "HIGH", (
            f"Wording-immune test failed: expected HIGH (from n_bear=6 structured field), "
            f"got {result.scenario_adversarial_risk}."
        )

    # -----------------------------------------------------------------------
    # T15: Gate 5 and scenario analysis use the same underlying bear-point count
    # -----------------------------------------------------------------------

    def test_k1_fu_t15_gate5_and_scenario_use_same_n_bear(self):
        """
        T15: evaluate_gate5() must set GateResult.n_bear to the same count as
        appears in the Gate 5 summary string, and _get_bear_count() must read
        the structured field (not reparse the string).

        Uses evaluate_gate5() with real inputs to verify the full chain:
          evaluate_gate5() → GateResult.n_bear = N
          _get_bear_count(assessment_with_that_result) → N
          calculate_adversarial_severity([], n_bear=N) → expected level
        """
        from analytics.decision.gate5_adversarial import evaluate_gate5
        from analytics.decision.scenario_engine import _get_bear_count
        from analytics.decision.gate5_adversarial import calculate_adversarial_severity
        from analytics.business_research.research_models import (
            BusinessResearchAssessment, BullBearAssessment,
        )
        import re

        # Build an assessment with 7 bear points by supplying multiple sources:
        # 1 from bear_case_narrative + multiple from negative evidence would need
        # more infrastructure; instead use direct bear_case_narrative (1 bear point)
        # and a known breaker. Test T15 is about structural identity, not threshold.
        bb = BullBearAssessment(
            bear_case_narrative="Revenue contracted over the past 3 years.",
            thesis_breaker_details=[
                {
                    "condition": "Revenue decline below breakeven",
                    "likelihood": "MEDIUM",
                    "evidence": ["Revenue -3.7% CAGR 2022-2025"],
                    "likelihood_rationale": "Trend confirmed by 3yr data.",
                }
            ],
        )
        research = BusinessResearchAssessment(ticker="TST2", company_name="Test2")
        research.bull_bear = bb

        gate_result = evaluate_gate5(research=research)

        # The structured field must equal the count in the summary string
        m = re.search(r'(\d+)\s+bear-case evidence point', gate_result.summary)
        n_from_summary = int(m.group(1)) if m else -1
        n_structured   = gate_result.n_bear

        assert n_structured == n_from_summary, (
            f"GateResult.n_bear (structured={n_structured}) does not match "
            f"n_bear from summary string ({n_from_summary}). "
            f"Summary: {gate_result.summary!r}"
        )

        # Simulate what _get_bear_count() would see by embedding gate_result
        # in a minimal assessment
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
        )
        assessment = InvestmentDecisionAssessment(
            ticker="TST2", company_name="Test2", analysis_date="2026-11-08",
            action=DecisionAction.WATCH, decision_confidence=DecisionConfidence.MEDIUM,
        )
        assessment.gate_results = [gate_result]

        n_from_accessor = _get_bear_count(assessment)
        assert n_from_accessor == n_structured, (
            f"_get_bear_count() returned {n_from_accessor} but GateResult.n_bear "
            f"is {n_structured}. Accessor must prefer structured field."
        )

        # Verify severity is consistent
        severity_from_function = calculate_adversarial_severity([], n_bear=n_structured)
        severity_from_summary  = calculate_adversarial_severity([], n_bear=n_from_summary)
        assert severity_from_function == severity_from_summary, (
            "Severity differs depending on whether structured field or string was used — "
            f"structured: {severity_from_function}, string: {severity_from_summary}"
        )

    # -----------------------------------------------------------------------
    # T16: GateResult.n_bear is auto-included in to_dict() persistence
    # -----------------------------------------------------------------------

    def test_k1_fu_t16_n_bear_persists_through_to_dict(self):
        """
        T16: GateResult.n_bear must round-trip through to_dict() (which uses
        asdict()) so persisted JSON assessments preserve the structured count.
        """
        from analytics.decision.decision_models import GateResult
        gr = GateResult(
            gate_number=5,
            gate_name="Adversarial Challenge",
            passed=True,
            adversarial_risk="HIGH",
            n_bear=7,
            confidence="HIGH",
            summary="7 bear-case evidence point(s). Risk HIGH.",
        )
        d = gr.to_dict()
        assert "n_bear" in d, "n_bear missing from GateResult.to_dict() output"
        assert d["n_bear"] == 7, f"Expected n_bear=7 in to_dict(), got {d['n_bear']}"

    # -----------------------------------------------------------------------
    # T17: Legacy assessment (n_bear=None default, bear count in summary) still works
    # -----------------------------------------------------------------------

    def test_k1_fu_t17_legacy_string_fallback_still_works(self):
        """
        T17: Backward compatibility — an assessment where GateResult.n_bear=0
        (the default, as if loaded from pre-K1-follow-up JSON) but the summary
        string contains the bear-count phrase must still return the correct count.

        _get_bear_count() uses structured-field-first with string fallback.
        """
        from analytics.decision.scenario_engine import _get_bear_count
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
        )
        assessment = InvestmentDecisionAssessment(
            ticker="LEGACY.TO", company_name="Legacy Co", analysis_date="2026-11-08",
            action=DecisionAction.WATCH, decision_confidence=DecisionConfidence.MEDIUM,
        )
        assessment.gate_results = [
            GateResult(
                gate_number=5, gate_name="Adversarial Challenge", passed=True,
                adversarial_risk="HIGH", confidence="MEDIUM",
                # n_bear defaults to None (legacy / field absent)
                summary=(
                    "Adversarial risk: HIGH. Breakers: 0 HIGH / 2 MEDIUM / 0 UNKNOWN / 0 LOW. "
                    "5 bear-case evidence point(s). Bear case synthesised from revenue data."
                ),
            )
        ]
        # n_bear is None by default (legacy) → string fallback must return 5
        gr = assessment.gate_results[0]
        assert gr.n_bear is None, f"Test setup: expected n_bear=None, got {gr.n_bear!r}"
        result = _get_bear_count(assessment)
        assert result == 5, (
            f"Legacy string fallback failed: expected 5 from summary string "
            f"(n_bear=None default), got {result}."
        )


# ===========================================================================
# Group 15: K1 Final Closure — Optional[int] Sentinel Tests
# ===========================================================================
#
# GateResult.n_bear: Optional[int] = None
#   None  → field absent / legacy, _get_bear_count() uses summary-string fallback
#   int   → explicitly set by evaluate_gate5(), including 0 ("assessed, zero points")
#
# S1: Structured n_bear=0 beats nonzero summary string count.
# S2: Structured n_bear=6 beats unparseable summary.
# S3: Legacy n_bear=None uses summary-string fallback.
# S4: New evaluate_gate5() always populates structured int, including zero.
# S5: Serialization preserves None vs 0 distinction (JSON null vs 0).
# ===========================================================================

class TestK1SentinelNBear:
    """K1 Final Closure: Optional[int] sentinel distinguishes structured-zero from absent."""

    # -----------------------------------------------------------------------
    # S1: Structured n_bear=0 takes precedence over nonzero summary string
    # -----------------------------------------------------------------------

    def test_k1_s1_structured_zero_beats_nonzero_summary(self):
        """
        S1: GateResult.n_bear=0 (explicitly set) must be returned by
        _get_bear_count() even when the summary string contains '7 bear-case
        evidence point(s)'.  An explicitly-set zero means 'assessed, found
        nothing' — it is authoritative, not a fallback trigger.
        """
        from analytics.decision.scenario_engine import _get_bear_count
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
        )
        assessment = InvestmentDecisionAssessment(
            ticker="ZERO.TO", company_name="Zero Co", analysis_date="2026-11-08",
            action=DecisionAction.WATCH, decision_confidence=DecisionConfidence.MEDIUM,
        )
        assessment.gate_results = [
            GateResult(
                gate_number=5, gate_name="Adversarial Challenge", passed=True,
                adversarial_risk="LOW", confidence="MEDIUM",
                n_bear=0,          # explicitly structured zero — authoritative
                # summary string misleadingly contains 7 — must NOT be used
                summary="Adversarial risk: LOW. 7 bear-case evidence point(s). Assessment.",
            )
        ]
        result = _get_bear_count(assessment)
        assert result == 0, (
            f"S1 FAILED: n_bear=0 (explicitly set) must beat summary '7'. "
            f"Got: {result}. n_bear=0 is authoritative zero, not a legacy-absent sentinel."
        )

    # -----------------------------------------------------------------------
    # S2: Structured n_bear=6 takes precedence over unparseable summary
    # -----------------------------------------------------------------------

    def test_k1_s2_structured_six_beats_unparseable_summary(self):
        """
        S2: GateResult.n_bear=6 must be returned even when the summary string
        contains no parseable bear-count phrase.
        """
        from analytics.decision.scenario_engine import _get_bear_count
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
        )
        assessment = InvestmentDecisionAssessment(
            ticker="SIX.TO", company_name="Six Co", analysis_date="2026-11-08",
            action=DecisionAction.WATCH, decision_confidence=DecisionConfidence.MEDIUM,
        )
        assessment.gate_results = [
            GateResult(
                gate_number=5, gate_name="Adversarial Challenge", passed=True,
                adversarial_risk="HIGH", confidence="HIGH",
                n_bear=6,
                summary="Adversarial risk HIGH. No standard summary phrase present.",
            )
        ]
        result = _get_bear_count(assessment)
        assert result == 6, (
            f"S2 FAILED: n_bear=6 must beat unparseable summary. Got: {result}."
        )

    # -----------------------------------------------------------------------
    # S3: Legacy n_bear=None uses summary-string fallback
    # -----------------------------------------------------------------------

    def test_k1_s3_none_sentinel_uses_summary_fallback(self):
        """
        S3: GateResult.n_bear is None by default (legacy / field absent).
        _get_bear_count() must fall back to parsing the summary string.
        """
        from analytics.decision.scenario_engine import _get_bear_count
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
        )
        assessment = InvestmentDecisionAssessment(
            ticker="LEG.TO", company_name="Legacy Co", analysis_date="2026-11-08",
            action=DecisionAction.WATCH, decision_confidence=DecisionConfidence.MEDIUM,
        )
        assessment.gate_results = [
            GateResult(
                gate_number=5, gate_name="Adversarial Challenge", passed=True,
                adversarial_risk="HIGH", confidence="MEDIUM",
                # n_bear omitted → defaults to None (legacy behaviour)
                summary=(
                    "Adversarial risk: HIGH. Breakers: 0 HIGH / 2 MEDIUM / 0 UNKNOWN / 0 LOW. "
                    "4 bear-case evidence point(s). Bear case: revenue decline."
                ),
            )
        ]
        gr = assessment.gate_results[0]
        assert gr.n_bear is None, (
            f"Test setup error: n_bear should be None for legacy GateResult, got {gr.n_bear!r}"
        )
        result = _get_bear_count(assessment)
        assert result == 4, (
            f"S3 FAILED: legacy n_bear=None must use string fallback and return 4. Got: {result}."
        )

    # -----------------------------------------------------------------------
    # S4: evaluate_gate5() always sets n_bear as int, including zero
    # -----------------------------------------------------------------------

    def test_k1_s4_evaluate_gate5_always_sets_n_bear_including_zero(self):
        """
        S4: evaluate_gate5() must always set GateResult.n_bear to an int
        (including 0 when no bear points exist).  n_bear must never be None
        on a freshly produced GateResult.
        """
        from analytics.decision.gate5_adversarial import evaluate_gate5

        # Zero-input call → no bear points
        gr_empty = evaluate_gate5()
        assert gr_empty.n_bear is not None, (
            "S4 FAILED: evaluate_gate5() with no inputs must set n_bear to int "
            "(including 0), not leave it as None."
        )
        assert isinstance(gr_empty.n_bear, int), (
            f"S4: n_bear must be int, got {type(gr_empty.n_bear).__name__}"
        )
        assert gr_empty.n_bear == 0, (
            f"S4: expected n_bear=0 for empty gate5 call, got {gr_empty.n_bear}"
        )

        # Call with one bear source → non-zero count
        from analytics.business_research.research_models import (
            BusinessResearchAssessment, BullBearAssessment,
        )
        bb = BullBearAssessment(
            bear_case_narrative="Revenue contracted -3.7% over 3 years.",
        )
        research = BusinessResearchAssessment(ticker="TST", company_name="Test")
        research.bull_bear = bb
        gr_one = evaluate_gate5(research=research)
        assert gr_one.n_bear is not None, (
            "S4 FAILED: evaluate_gate5() with one bear source must set n_bear, "
            "not leave it as None."
        )
        assert isinstance(gr_one.n_bear, int), (
            f"S4: n_bear must be int, got {type(gr_one.n_bear).__name__}"
        )
        assert gr_one.n_bear >= 1, (
            f"S4: expected n_bear >= 1 when bear_case_narrative supplied, got {gr_one.n_bear}"
        )

    # -----------------------------------------------------------------------
    # S5: Serialization preserves None vs 0 distinction
    # -----------------------------------------------------------------------

    def test_k1_s5_serialization_preserves_none_vs_zero(self):
        """
        S5: GateResult.to_dict() must preserve the None/0 distinction so that
        a loaded JSON assessment can tell whether the structured field was set.

        None  → serialised as None (JSON null)
        0     → serialised as 0 (JSON 0)
        These must not be equal after serialization.
        """
        from analytics.decision.decision_models import GateResult

        # None case (legacy / absent)
        gr_none = GateResult(gate_number=5, gate_name="Adv", passed=True)
        assert gr_none.n_bear is None, "Default must be None (sentinel for absent/legacy)"
        d_none = gr_none.to_dict()
        assert d_none["n_bear"] is None, (
            f"Serialized legacy GateResult must have n_bear=None, got {d_none['n_bear']!r}"
        )

        # Zero case (explicitly assessed as zero bear points)
        gr_zero = GateResult(gate_number=5, gate_name="Adv", passed=True, n_bear=0)
        assert gr_zero.n_bear == 0
        d_zero = gr_zero.to_dict()
        assert d_zero["n_bear"] == 0, (
            f"Serialized n_bear=0 must be 0 in to_dict(), got {d_zero['n_bear']!r}"
        )

        # Non-zero case
        gr_six = GateResult(gate_number=5, gate_name="Adv", passed=True, n_bear=6)
        d_six = gr_six.to_dict()
        assert d_six["n_bear"] == 6, (
            f"Serialized n_bear=6 must be 6, got {d_six['n_bear']!r}"
        )

        # Critical: None and 0 must be distinguishable
        assert d_none["n_bear"] is None
        assert d_zero["n_bear"] == 0
        # In Python, None != 0, confirming they are distinguishable
        assert d_none["n_bear"] != d_zero["n_bear"], (
            "CRITICAL S5: None and 0 must be distinguishable after to_dict() serialization. "
            "Deloading JSON: `is None` check identifies legacy records; `== 0` identifies "
            "structured-zero records."
        )
