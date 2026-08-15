"""
Phase 4 Test Suite — Business & Industry Research Engine
=========================================================
Tests all Phase 4 models, validators, builders, and orchestration.
All tests use synthetic data — no network calls, no external dependencies.
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.business_research.research_models import (
    # Enums
    SourceTier, ResearchLevel, Confidence,
    MoatStrength, MoatDurability, MoatTrajectory, MoatStatus,
    IndustryClassification, RiskLevel, RiskType,
    ManagementRating, UnderstandabilityRating,
    MOAT_SOURCE_TYPES,
    # Data items
    EvidenceItem, RiskItem,
    # Assessment dataclasses
    MoatSourceAnalysis,
    BusinessUnderstandingAssessment,
    IndustryAssessment,
    MoatAssessment,
    GrowthAssessment,
    ManagementAssessment,
    RiskAssessment,
    BullBearAssessment,
    BusinessResearchAssessment,
)
from analytics.business_research.moat_analyzer import (
    MoatSourceBuilder,
    MoatAssessmentBuilder,
    roic_moat_support_note,
    moat_description,
    _aggregate_strength,
    _aggregate_durability,
)
from analytics.business_research.research_synthesizer import (
    detect_contradictions,
    identify_research_gaps,
    synthesize_business_quality,
    generate_key_questions,
    finalize_assessment,
)
from agent.orchestration.research_workflow import (
    create_workflow,
    ResearchWorkflow,
    StepStatus,
    build_workflow_steps,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_evidence(
    fact="Revenue grew 12% organically",
    source="Annual Report 2024",
    tier=SourceTier.TIER_1_PRIMARY,
    supports=True,
    confidence=Confidence.HIGH,
) -> EvidenceItem:
    return EvidenceItem(
        fact=fact,
        source=source,
        source_tier=tier,
        supports_thesis=supports,
        confidence=confidence,
    )


def make_switching_cost_moat(strength=MoatStrength.STRONG) -> MoatSourceAnalysis:
    return (
        MoatSourceBuilder("switching_costs")
        .claim("Deep ERP integration creates multi-year migration risk")
        .add_evidence(make_evidence("NRR > 120% for 5 consecutive years"))
        .add_evidence(make_evidence("95% renewal rate, avg contract 3.2 years"))
        .durability(MoatDurability.HIGH, "Migration requires 2+ years and significant spend")
        .threats(["Open-source alternatives", "API disaggregation"])
        .conclude(MoatStatus.CURRENT, strength, "Switching costs confirmed by retention data", Confidence.HIGH)
        .build()
    )


def make_full_assessment(ticker="TEST.TO", name="Test Corp") -> BusinessResearchAssessment:
    a = BusinessResearchAssessment(
        ticker=ticker,
        company_name=name,
        assessment_date="2024-12-31",
    )
    a.business_understanding = BusinessUnderstandingAssessment(
        what_it_does="Sells enterprise software",
        how_it_makes_money="Subscription SaaS revenue",
        revenue_sources=["Subscriptions", "Professional services"],
        understandability_rating=UnderstandabilityRating.SUFFICIENT,
        confidence=Confidence.HIGH,
    )
    a.industry_assessment = IndustryAssessment(
        industry_name="Enterprise Software",
        classification=IndustryClassification.ATTRACTIVE,
        classification_reasoning="High switching costs, recurring revenue, favorable unit economics",
        confidence=Confidence.HIGH,
    )
    a.moat_assessment = MoatAssessment(
        overall_strength=MoatStrength.STRONG,
        overall_durability=MoatDurability.HIGH,
        trajectory=MoatTrajectory.STABLE,
        active_sources=["switching_costs"],
        moat_summary="Strong switching costs confirmed by NRR and retention data",
        confidence=Confidence.HIGH,
    )
    a.management_assessment = ManagementAssessment(
        overall_rating=ManagementRating.STRONG,
        management_summary="Founder-led, strong capital allocation track record",
        confidence=Confidence.HIGH,
    )
    a.risk_assessment = RiskAssessment(
        overall_level=RiskLevel.MODERATE,
        risk_summary="AI disruption is the primary long-term structural risk",
        business_risks=[RiskItem("AI-native alternatives", RiskType.STRUCTURAL, "Medium")],
        competitive_risks=[],
        macro_risks=[],
        financial_risks=[],
        confidence=Confidence.MEDIUM,
    )
    a.growth_assessment = GrowthAssessment(
        growth_sustainability_assessment="12% organic growth sustainable for 5+ years given TAM expansion",
        confidence=Confidence.MEDIUM,
    )
    a.bull_bear = BullBearAssessment(
        bull_case_title="Compounding moat with long runway",
        bull_case_narrative="Switching costs + TAM expansion creates a 10-year compounder",
        bull_case_assumptions=["NRR remains > 110%", "TAM grows at 8%/yr"],
        bear_case_title="AI disruption breaks switching costs",
        bear_case_narrative="AI-native competitors make migration trivial, NRR collapses",
        bear_case_assumptions=["LLM-based alternatives reach parity by 2028"],
        thesis_breakers=["NRR falls below 100% for 2 consecutive quarters",
                         "AI-native competitor reaches 5% market share"],
        devils_advocate_research_note="Reviewed 3 analyst reports with negative ratings; examined AI competitor landscape",
        negative_evidence_found=[make_evidence(
            fact="AI startup raised $300M to build LLM-native alternative",
            source="TechCrunch 2024",
            tier=SourceTier.TIER_3_SUPPORTING,
            supports=False,
            confidence=Confidence.MEDIUM,
        )],
        confirmation_bias_check="What would make me not invest: NRR < 100%, founder departure, AI disruption materializing",
    )
    a.confidence_by_dimension = {
        "business_understanding": Confidence.HIGH.value,
        "industry": Confidence.HIGH.value,
        "moat": Confidence.HIGH.value,
        "management": Confidence.HIGH.value,
        "risks": Confidence.MEDIUM.value,
        "growth": Confidence.MEDIUM.value,
        "bull_bear": Confidence.HIGH.value,
    }
    a.register_evidence(make_evidence())
    a.register_evidence(make_evidence("Tier 1 fact 2", tier=SourceTier.TIER_1_PRIMARY))
    return a


# ===========================================================================
# Test: research_models.py
# ===========================================================================

class TestEvidenceItem(unittest.TestCase):

    def test_tier1_identification(self):
        e = make_evidence(tier=SourceTier.TIER_1_PRIMARY)
        self.assertTrue(e.is_tier1())

    def test_tier2_is_not_tier1(self):
        e = make_evidence(tier=SourceTier.TIER_2_SECONDARY)
        self.assertFalse(e.is_tier1())

    def test_to_dict_roundtrip(self):
        e = make_evidence()
        d = e.to_dict()
        self.assertIn("fact", d)
        self.assertIn("source_tier", d)
        self.assertEqual(d["confidence"], Confidence.HIGH.value)

    def test_summary_contains_fact(self):
        e = make_evidence(fact="ROIC: 18%")
        self.assertIn("ROIC", e.summary())


class TestRiskItem(unittest.TestCase):

    def test_risk_item_creation(self):
        r = RiskItem("EV disruption", RiskType.STRUCTURAL, "High",
                     mitigants=["Diversified non-fuel revenue"])
        self.assertEqual(r.severity, "High")
        self.assertEqual(r.risk_type, RiskType.STRUCTURAL)


class TestMoatSourceAnalysis(unittest.TestCase):

    def test_valid_moat_passes_validation(self):
        source = MoatSourceAnalysis(
            moat_type="switching_costs",
            claim="Deep integration creates migration risk",
            evidence=[make_evidence()],
            status=MoatStatus.CURRENT,
            strength=MoatStrength.STRONG,
            conclusion="Switching costs confirmed by retention data",
        )
        issues = source.validate()
        self.assertEqual(issues, [])

    def test_missing_claim_caught(self):
        source = MoatSourceAnalysis(
            moat_type="network_effects",
            claim="",
            evidence=[make_evidence()],
            status=MoatStatus.CURRENT,
            strength=MoatStrength.STRONG,
            conclusion="Network effects confirmed",
        )
        issues = source.validate()
        self.assertTrue(any("claim" in i.lower() for i in issues))

    def test_positive_conclusion_without_evidence_caught(self):
        source = MoatSourceAnalysis(
            moat_type="cost_advantage",
            claim="Structural cost advantage",
            evidence=[],
            status=MoatStatus.CURRENT,
            strength=MoatStrength.STRONG,
            conclusion="Cost advantage confirmed",
        )
        issues = source.validate()
        self.assertTrue(any("evidence" in i.lower() for i in issues))

    def test_brand_without_pricing_power_caught(self):
        source = MoatSourceAnalysis(
            moat_type="brand",
            claim="Well-known brand",
            evidence=[make_evidence()],
            status=MoatStatus.CURRENT,
            strength=MoatStrength.MODERATE,
            conclusion="Brand is a moat",
            brand_demonstrates_pricing_power=False,
            brand_demonstrates_retention=False,
            brand_demonstrates_switching_costs=False,
        )
        issues = source.validate()
        self.assertTrue(any("brand" in i.lower() for i in issues))

    def test_brand_with_pricing_power_passes(self):
        source = MoatSourceAnalysis(
            moat_type="brand",
            claim="Brand commands premium pricing",
            evidence=[make_evidence()],
            status=MoatStatus.CURRENT,
            strength=MoatStrength.MODERATE,
            conclusion="Brand moat confirmed via pricing power",
            brand_demonstrates_pricing_power=True,
            brand_demonstrates_retention=True,
            brand_demonstrates_switching_costs=False,
        )
        issues = source.validate()
        self.assertEqual(issues, [])

    def test_absent_status_with_none_strength_valid(self):
        source = MoatSourceAnalysis(
            moat_type="network_effects",
            claim="",
            evidence=[],
            status=MoatStatus.ABSENT,
            strength=MoatStrength.NONE,
            conclusion="No network effects identified",
        )
        issues = source.validate()
        self.assertEqual(issues, [])


class TestBusinessResearchAssessment(unittest.TestCase):

    def test_register_evidence(self):
        a = BusinessResearchAssessment(ticker="X", assessment_date="2024-01-01")
        e = make_evidence()
        a.register_evidence(e)
        self.assertEqual(len(a.evidence_registry), 1)

    def test_tier1_evidence_count(self):
        a = BusinessResearchAssessment(ticker="X", assessment_date="2024-01-01")
        a.register_evidence(make_evidence(tier=SourceTier.TIER_1_PRIMARY))
        a.register_evidence(make_evidence(tier=SourceTier.TIER_2_SECONDARY))
        self.assertEqual(a.tier1_evidence_count(), 1)

    def test_negative_evidence_count(self):
        a = BusinessResearchAssessment(ticker="X", assessment_date="2024-01-01")
        a.register_evidence(make_evidence(supports=True))
        a.register_evidence(make_evidence(supports=False))
        self.assertEqual(a.negative_evidence_count(), 1)

    def test_incomplete_dimensions_full_assessment(self):
        a = make_full_assessment()
        incomplete = a.incomplete_dimensions()
        self.assertEqual(incomplete, [])

    def test_incomplete_dimensions_empty_assessment(self):
        a = BusinessResearchAssessment(ticker="X", assessment_date="2024-01-01")
        incomplete = a.incomplete_dimensions()
        self.assertGreater(len(incomplete), 0)

    def test_validate_passes_complete_assessment(self):
        a = make_full_assessment()
        issues = a.validate()
        self.assertEqual(issues, [])

    def test_to_json_parseable(self):
        a = make_full_assessment()
        j = a.to_json()
        parsed = json.loads(j)
        self.assertEqual(parsed["ticker"], "TEST.TO")

    def test_summary_text_contains_ticker(self):
        a = make_full_assessment()
        text = a.summary_text()
        self.assertIn("TEST.TO", text)

    def test_moat_assessment_validate_all_sources(self):
        a = make_full_assessment()
        ma = a.moat_assessment
        ma.sources_investigated = [make_switching_cost_moat()]
        issues = ma.validate_all_sources()
        self.assertEqual(issues, {})  # returns dict; empty means no issues


# ===========================================================================
# Test: moat_analyzer.py
# ===========================================================================

class TestROICMoatSupportNote(unittest.TestCase):

    def test_high_roic_positive_note(self):
        note = roic_moat_support_note(18.0, 16.5)
        self.assertIn("15%", note)
        self.assertIn("cannot prove", note)

    def test_low_roic_warns(self):
        note = roic_moat_support_note(6.5, None)
        self.assertIn("below preferred", note)

    def test_none_roic_graceful(self):
        note = roic_moat_support_note(None, None)
        self.assertIn("unavailable", note)

    def test_erosion_note_when_avg_higher(self):
        # avg must be > current + 3 but < 15 to hit the erosion branch
        note = roic_moat_support_note(8.0, 13.0)
        self.assertIn("erosion", note.lower())


class TestMoatSourceBuilder(unittest.TestCase):

    def test_valid_switching_cost_moat(self):
        moat = make_switching_cost_moat()
        self.assertEqual(moat.strength, MoatStrength.STRONG)
        self.assertEqual(moat.durability, MoatDurability.HIGH)
        self.assertEqual(moat.status, MoatStatus.CURRENT)

    def test_brand_without_evidence_raises(self):
        with self.assertRaises(ValueError) as ctx:
            (
                MoatSourceBuilder("brand")
                .claim("Well-known brand")
                .conclude(MoatStatus.CURRENT, MoatStrength.MODERATE, "Brand = moat")
                .build()
            )
        self.assertIn("brand", str(ctx.exception).lower())

    def test_brand_with_pricing_power_succeeds(self):
        moat = (
            MoatSourceBuilder("brand")
            .claim("Brand commands 15–20% price premium vs generic")
            .add_evidence(make_evidence("Price realization 18% above category average"))
            .brand_evidence(pricing_power=True, retention=True)
            .durability(MoatDurability.HIGH, "Premium brand built over 50+ years")
            .threats(["Private label competition"])
            .conclude(MoatStatus.CURRENT, MoatStrength.MODERATE, "Brand moat via pricing power")
            .build()
        )
        self.assertEqual(moat.strength, MoatStrength.MODERATE)

    def test_no_conclusion_without_evidence_raises(self):
        with self.assertRaises(ValueError):
            (
                MoatSourceBuilder("network_effects")
                .claim("More users = more value")
                .conclude(MoatStatus.CURRENT, MoatStrength.STRONG, "Network effects confirmed")
                .build()
            )

    def test_missing_claim_raises(self):
        with self.assertRaises(ValueError):
            (
                MoatSourceBuilder("cost_advantage")
                .add_evidence(make_evidence())
                .conclude(MoatStatus.CURRENT, MoatStrength.MODERATE, "Cost advantage")
                .build()
            )

    def test_absent_moat_builds_cleanly(self):
        moat = (
            MoatSourceBuilder("network_effects")
            .claim("")
            .conclude(MoatStatus.ABSENT, MoatStrength.NONE, "No network effects identified")
            .build()
        )
        self.assertEqual(moat.status, MoatStatus.ABSENT)

    def test_invalid_moat_type_raises(self):
        with self.assertRaises(ValueError):
            MoatSourceBuilder("magic_moat")


class TestAggregation(unittest.TestCase):

    def test_single_strong_source_is_strong(self):
        # Single source: no reinforcement boost, stays at STRONG
        sources = [make_switching_cost_moat(MoatStrength.STRONG)]
        result = _aggregate_strength(sources)
        self.assertEqual(result, MoatStrength.STRONG)

    def test_two_strong_sources_elevate_to_exceptional(self):
        sources = [
            make_switching_cost_moat(MoatStrength.STRONG),
            make_switching_cost_moat(MoatStrength.STRONG),
        ]
        result = _aggregate_strength(sources)
        self.assertEqual(result, MoatStrength.EXCEPTIONAL)

    def test_empty_sources_is_none(self):
        self.assertEqual(_aggregate_strength([]), MoatStrength.NONE)

    def test_all_none_strength_is_none(self):
        sources = [make_switching_cost_moat(MoatStrength.NONE)]
        result = _aggregate_strength(sources)
        self.assertEqual(result, MoatStrength.NONE)

    def test_low_durability_limits_aggregate(self):
        low_dur = (
            MoatSourceBuilder("switching_costs")
            .claim("Some switching costs")
            .add_evidence(make_evidence())
            .durability(MoatDurability.LOW, "Can be overcome with effort")
            .threats(["Competition"])
            .conclude(MoatStatus.CURRENT, MoatStrength.MODERATE, "Moderate switching costs")
            .build()
        )
        high_dur = make_switching_cost_moat()
        result = _aggregate_durability([low_dur, high_dur])
        self.assertEqual(result, MoatDurability.LOW)

    def test_all_high_durability_is_high(self):
        sources = [make_switching_cost_moat(), make_switching_cost_moat()]
        result = _aggregate_durability(sources)
        self.assertEqual(result, MoatDurability.HIGH)


class TestMoatAssessmentBuilder(unittest.TestCase):

    def test_build_from_single_source(self):
        source = make_switching_cost_moat()
        assessment = (
            MoatAssessmentBuilder()
            .add_source(source)
            .trajectory(MoatTrajectory.STABLE)
            .summary("Strong switching cost moat")
            .roic_note(roic_moat_support_note(17.0, 15.5))
            .confidence(Confidence.HIGH)
            .build()
        )
        self.assertIn("switching_costs", assessment.active_sources)
        self.assertEqual(assessment.trajectory, MoatTrajectory.STABLE)

    def test_empty_builder_produces_none_moat(self):
        assessment = MoatAssessmentBuilder().build()
        self.assertEqual(assessment.overall_strength, MoatStrength.NONE)

    def test_moat_description_contains_strength(self):
        source = make_switching_cost_moat()
        assessment = (
            MoatAssessmentBuilder()
            .add_source(source)
            .trajectory(MoatTrajectory.STABLE)
            .summary("Test summary")
            .build()
        )
        desc = moat_description(assessment)
        self.assertIn("Strong", desc)


# ===========================================================================
# Test: research_synthesizer.py
# ===========================================================================

class TestDetectContradictions(unittest.TestCase):

    def test_strong_moat_weakening_is_contradiction(self):
        a = make_full_assessment()
        a.moat_assessment.overall_strength = MoatStrength.STRONG
        a.moat_assessment.trajectory = MoatTrajectory.WEAKENING
        contradictions = detect_contradictions(a)
        self.assertTrue(any("weakening" in c.lower() for c in contradictions))

    def test_strong_moat_below_preferred_roic_is_contradiction(self):
        a = make_full_assessment()
        a.moat_assessment.overall_strength = MoatStrength.STRONG
        a.moat_assessment.roic_consistency_note = "ROIC is below preferred threshold"
        contradictions = detect_contradictions(a)
        self.assertTrue(any("roic" in c.lower() or "moat" in c.lower() for c in contradictions))

    def test_challenging_industry_exceptional_moat_flagged(self):
        a = make_full_assessment()
        a.industry_assessment.classification = IndustryClassification.CHALLENGING
        a.moat_assessment.overall_strength = MoatStrength.EXCEPTIONAL
        contradictions = detect_contradictions(a)
        self.assertTrue(any("challenging" in c.lower() for c in contradictions))

    def test_no_contradictions_clean_assessment(self):
        a = make_full_assessment()
        contradictions = detect_contradictions(a)
        self.assertEqual(contradictions, [])


class TestIdentifyResearchGaps(unittest.TestCase):

    def test_no_gaps_complete_assessment(self):
        a = make_full_assessment()
        # Provide enough evidence to pass the thin-evidence check
        for _ in range(5):
            a.register_evidence(make_evidence())
        gaps = identify_research_gaps(a)
        # May have gap about management tier 1 evidence — that's expected
        # Just ensure no "Research dimension not completed" gaps
        dimension_gaps = [g for g in gaps if "not completed" in g]
        self.assertEqual(dimension_gaps, [])

    def test_missing_thesis_breakers_is_gap(self):
        a = make_full_assessment()
        a.bull_bear.thesis_breakers = []
        gaps = identify_research_gaps(a)
        self.assertTrue(any("breaker" in g.lower() for g in gaps))

    def test_no_negative_evidence_is_gap(self):
        a = make_full_assessment()
        a.bull_bear.negative_evidence_found = []
        gaps = identify_research_gaps(a)
        self.assertTrue(any("negative" in g.lower() for g in gaps))

    def test_thin_evidence_is_gap(self):
        a = BusinessResearchAssessment(ticker="X", assessment_date="2024-01-01")
        a.business_understanding = BusinessUnderstandingAssessment(
            what_it_does="Something",
            how_it_makes_money="Revenue",
            understandability_rating=UnderstandabilityRating.SUFFICIENT,
            confidence=Confidence.HIGH,
        )
        gaps = identify_research_gaps(a)
        self.assertTrue(any("evidence" in g.lower() for g in gaps))


class TestSynthesizeBusinessQuality(unittest.TestCase):

    def test_synthesis_contains_moat_strength(self):
        a = make_full_assessment()
        text = synthesize_business_quality(a)
        self.assertIn("strong", text.lower())

    def test_synthesis_contains_l2_marker(self):
        a = make_full_assessment()
        text = synthesize_business_quality(a)
        self.assertIn("[L2", text)

    def test_synthesis_no_investment_recommendation(self):
        a = make_full_assessment()
        text = synthesize_business_quality(a)
        for forbidden in ["BUY", "SELL", "HOLD", "overweight", "underweight"]:
            self.assertNotIn(forbidden, text)


class TestGenerateKeyQuestions(unittest.TestCase):

    def test_thesis_breakers_become_questions(self):
        a = make_full_assessment()
        questions = generate_key_questions(a)
        self.assertTrue(any("NRR" in q or "thesis breaker" in q.lower() for q in questions))

    def test_weakening_moat_generates_question(self):
        a = make_full_assessment()
        a.moat_assessment.trajectory = MoatTrajectory.WEAKENING
        questions = generate_key_questions(a)
        self.assertTrue(any("moat" in q.lower() or "erosion" in q.lower() for q in questions))


class TestFinalizeAssessment(unittest.TestCase):

    def test_finalize_populates_interpretation(self):
        a = make_full_assessment()
        a = finalize_assessment(a)
        self.assertIsNotNone(a.business_quality_interpretation)
        self.assertGreater(len(a.business_quality_interpretation), 50)

    def test_finalize_sets_confidence(self):
        a = make_full_assessment()
        a = finalize_assessment(a)
        self.assertIsNotNone(a.overall_research_confidence)

    def test_finalize_generates_questions(self):
        a = make_full_assessment()
        a = finalize_assessment(a)
        self.assertGreater(len(a.key_investment_questions), 0)

    def test_finalize_low_confidence_for_incomplete(self):
        a = BusinessResearchAssessment(ticker="X", assessment_date="2024-01-01")
        a = finalize_assessment(a)
        self.assertEqual(a.overall_research_confidence, Confidence.LOW)


# ===========================================================================
# Test: research_workflow.py
# ===========================================================================

class TestResearchWorkflow(unittest.TestCase):

    def _make_wf(self) -> ResearchWorkflow:
        return create_workflow(
            ticker="FFH.TO",
            company_name="Fairfax Financial Holdings",
            financial_context={"sector": "Financial Services"},
        )

    def test_initial_state_all_pending(self):
        wf = self._make_wf()
        pending = wf.pending_steps()
        self.assertEqual(len(pending), 10)

    def test_next_step_is_step_1_initially(self):
        wf = self._make_wf()
        self.assertEqual(wf.next_step().step_number, 1)

    def test_mark_complete_advances_workflow(self):
        wf = self._make_wf()
        wf.mark_complete(1)
        completed = wf.complete_steps()
        self.assertEqual(len(completed), 1)

    def test_prerequisites_gate_steps(self):
        wf = self._make_wf()
        # Step 5 (moat) requires steps 2, 3, 4
        self.assertFalse(wf.prerequisites_met(5))
        wf.mark_complete(1)
        wf.mark_complete(2)
        wf.mark_complete(3)
        wf.mark_complete(4)
        self.assertTrue(wf.prerequisites_met(5))

    def test_etf_short_circuit(self):
        wf = create_workflow("CGL.C.TO", "Gold ETF", is_etf=True)
        self.assertTrue(wf.is_complete())
        skipped = [s for s in wf.steps if s.status == StepStatus.SKIPPED]
        self.assertEqual(len(skipped), 9)  # all but step 1

    def test_serialization(self):
        wf = self._make_wf()
        wf.mark_complete(1)
        d = wf.to_dict()
        self.assertEqual(d["ticker"], "FFH.TO")
        self.assertEqual(d["steps_complete"], 1)

    def test_prompt_loading_injects_ticker(self):
        wf = self._make_wf()
        wf.mark_complete(1)
        wf.mark_complete(2)  # prereq for step 3
        prompt = wf.load_step_prompt(3)  # industry_analysis
        self.assertIn("FFH.TO", prompt)

    def test_status_report_contains_ticker(self):
        wf = self._make_wf()
        report = wf.status_report()
        self.assertIn("FFH.TO", report)

    def test_is_complete_false_when_steps_pending(self):
        wf = self._make_wf()
        self.assertFalse(wf.is_complete())

    def test_is_complete_true_when_all_done(self):
        wf = self._make_wf()
        for step in wf.steps:
            wf.mark_complete(step.step_number)
        self.assertTrue(wf.is_complete())

    def test_workflow_steps_have_10_steps(self):
        steps = build_workflow_steps()
        self.assertEqual(len(steps), 10)

    def test_all_steps_have_dimension_keys(self):
        steps = build_workflow_steps()
        for step in steps:
            self.assertTrue(step.dimension_key, f"Step {step.step_number} missing dimension_key")


# ===========================================================================
# Test: Integration
# ===========================================================================

class TestPhase4Integration(unittest.TestCase):
    """
    End-to-end: build a complete assessment using the builder pattern,
    run the synthesizer, and verify the output is coherent.
    """

    def test_end_to_end_with_builder_pattern(self):
        # Build moat analysis using builder
        switching_moat = make_switching_cost_moat()
        moat_assessment = (
            MoatAssessmentBuilder()
            .add_source(switching_moat)
            .trajectory(MoatTrajectory.STABLE)
            .summary("Strong switching cost moat confirmed by NRR > 120%")
            .roic_note(roic_moat_support_note(19.0, 17.0))
            .confidence(Confidence.HIGH)
            .build()
        )

        # Assemble full assessment
        a = make_full_assessment()
        a.moat_assessment = moat_assessment

        # Run synthesis
        a = finalize_assessment(a)

        # Verify
        self.assertIsNotNone(a.business_quality_interpretation)
        self.assertIsNotNone(a.overall_research_confidence)
        # 5 HIGH + 2 MEDIUM dims → majority HIGH → overall HIGH
        self.assertEqual(a.overall_research_confidence, Confidence.HIGH)
        self.assertGreater(len(a.key_investment_questions), 0)

        # Verify JSON roundtrip
        j = a.to_json()
        parsed = json.loads(j)
        self.assertEqual(parsed["ticker"], "TEST.TO")
        self.assertIn("business_quality_interpretation", parsed)

    def test_workflow_loads_correct_prompt_for_each_step(self):
        from agent.orchestration.research_workflow import PROMPTS_DIR
        wf = create_workflow("ATD.TO", "Couche-Tard")
        # Steps 2, 3, 5, 6, 7, 8, 9 have prompt templates
        steps_with_prompts = [s for s in wf.steps if s.prompt_template]
        for step in steps_with_prompts:
            prompt_path = PROMPTS_DIR / step.prompt_template
            self.assertTrue(prompt_path.exists(),
                            f"Prompt template missing: {step.prompt_template}")

    def test_brand_moat_guardrail_enforced_in_integration(self):
        """Verify that a brand moat claim without pricing power is blocked end-to-end."""
        with self.assertRaises(ValueError):
            (
                MoatSourceBuilder("brand")
                .claim("Famous brand")
                .add_evidence(make_evidence())
                .conclude(MoatStatus.CURRENT, MoatStrength.STRONG, "Brand = moat")
                .build()
            )

    def test_moat_source_types_are_complete(self):
        """Ensure the MOAT_SOURCE_TYPES list contains all expected types."""
        expected = ["network_effects", "switching_costs", "cost_advantage",
                    "scale", "brand", "intellectual_property"]
        for moat_type in expected:
            self.assertIn(moat_type, MOAT_SOURCE_TYPES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
