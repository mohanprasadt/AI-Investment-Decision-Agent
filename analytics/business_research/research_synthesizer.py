"""
Research Synthesizer
====================
Combines completed research dimensions into a L2-level business quality
interpretation. Produces the consolidated BusinessResearchAssessment summary
that Phase 7 (Decision Engine) will consume alongside financial and valuation data.

This module does NOT:
- Produce investment recommendations
- Set price targets
- Assess valuation
- Make BUY/SELL decisions

It DOES:
- Synthesize qualitative research into structured, readable L2 interpretation
- Identify internal contradictions and research gaps
- Surface open questions for Phase 7 reasoning
- Validate completeness of the research
"""

import sys
from pathlib import Path
from typing import List, Optional
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.business_research.research_models import (
    BusinessResearchAssessment, IndustryClassification,
    MoatStrength, MoatDurability, MoatStatus, MoatTrajectory,
    ManagementRating, RiskLevel, Confidence, RiskType,
    ResearchLevel
)


# ---------------------------------------------------------------------------
# Contradiction detector
# ---------------------------------------------------------------------------

def detect_contradictions(assessment: BusinessResearchAssessment) -> List[str]:
    """
    Look for internal contradictions across dimensions.
    These are not errors — they are important analytical signals.
    """
    contradictions = []

    # Strong moat claim vs. weak/deteriorating ROIC
    if assessment.moat_assessment:
        ma = assessment.moat_assessment
        if ma.overall_strength in (MoatStrength.STRONG, MoatStrength.EXCEPTIONAL):
            if ma.roic_consistency_note and "below preferred" in ma.roic_consistency_note:
                contradictions.append(
                    "Strong moat claimed but ROIC is below preferred threshold — "
                    "verify whether moat is genuine or narrative"
                )
            if ma.trajectory == MoatTrajectory.WEAKENING:
                contradictions.append(
                    "Strong moat claimed but moat trajectory is weakening — "
                    "investigate whether competitive advantage is eroding"
                )

    # Attractive industry vs. high competitive risk
    if assessment.industry_assessment and assessment.risk_assessment:
        ia = assessment.industry_assessment
        ra = assessment.risk_assessment
        if ia.classification == IndustryClassification.ATTRACTIVE:
            competitive_risks = ra.competitive_risks
            high_competitive = [r for r in competitive_risks if r.severity == "High"]
            if high_competitive:
                contradictions.append(
                    "Industry classified Attractive but high-severity competitive risks identified — "
                    "assess whether industry tailwinds can outweigh competitive pressure"
                )

    # Strong management vs. weak capital allocation
    if assessment.management_assessment:
        mgmt = assessment.management_assessment
        if mgmt.overall_rating == ManagementRating.STRONG and mgmt.capital_allocation:
            if any(word in mgmt.capital_allocation.lower() for word in ["poor", "weak", "questionable", "dilutive"]):
                contradictions.append(
                    "Management rated Strong but capital allocation concerns noted — "
                    "reconcile this inconsistency"
                )

    # Challenging industry but company has exceptional moat
    if assessment.industry_assessment and assessment.moat_assessment:
        ia = assessment.industry_assessment
        ma = assessment.moat_assessment
        if (ia.classification == IndustryClassification.CHALLENGING and
                ma.overall_strength in (MoatStrength.STRONG, MoatStrength.EXCEPTIONAL)):
            contradictions.append(
                "Challenging industry but strong/exceptional moat — "
                "this combination is rare but can represent exceptional opportunity: "
                "verify moat durability carefully given industry headwinds"
            )

    return contradictions


# ---------------------------------------------------------------------------
# Research gap detector
# ---------------------------------------------------------------------------

def identify_research_gaps(assessment: BusinessResearchAssessment) -> List[str]:
    """
    Identify areas where research is incomplete or confidence is low.
    """
    gaps = []

    # Missing dimensions
    incomplete = assessment.incomplete_dimensions()
    for dim in incomplete:
        gaps.append(f"Research dimension not completed: {dim}")

    # Low-confidence dimensions
    for dim_name, conf in assessment.confidence_by_dimension.items():
        if conf == Confidence.LOW.value:
            gaps.append(f"Low confidence in {dim_name} — additional research recommended")

    # Moat: no Tier 1 evidence
    if assessment.moat_assessment:
        for source in assessment.moat_assessment.sources_investigated:
            if source.status != MoatStatus.ABSENT and source.evidence:
                tier1_evidence = [e for e in source.evidence if e.is_tier1()]
                if not tier1_evidence:
                    gaps.append(
                        f"Moat claim '{source.moat_type}' has no Tier 1 (primary source) evidence — "
                        "verify against annual report or regulatory filing"
                    )

    # Management: no Tier 1 evidence
    if assessment.management_assessment:
        tier1 = [e for e in assessment.management_assessment.evidence if e.is_tier1()]
        if not tier1:
            gaps.append("Management assessment has no Tier 1 evidence — "
                        "review investor presentations and annual report letters")

    # Devil's advocate: no negative evidence found
    if assessment.bull_bear:
        if not assessment.bull_bear.negative_evidence_found:
            gaps.append(
                "Devil's advocate research found no negative evidence — "
                "this is unusual; actively search for contrarian views and recent negative developments"
            )
        if not assessment.bull_bear.thesis_breakers:
            gaps.append("Thesis breakers not defined — required before any investment consideration")

    # Low total evidence
    if len(assessment.evidence_registry) < 5:
        gaps.append(
            f"Only {len(assessment.evidence_registry)} evidence items registered — "
            "research appears thin; conduct more primary source review"
        )

    # Low Tier 1 evidence ratio
    if assessment.evidence_registry:
        tier1_ratio = assessment.tier1_evidence_count() / len(assessment.evidence_registry)
        if tier1_ratio < 0.3 and len(assessment.evidence_registry) > 5:
            gaps.append(
                f"Only {tier1_ratio:.0%} of evidence is Tier 1 — "
                "increase reliance on primary sources (filings, annual reports)"
            )

    return gaps


# ---------------------------------------------------------------------------
# Business quality interpretation (L2 synthesis)
# ---------------------------------------------------------------------------

def synthesize_business_quality(assessment: BusinessResearchAssessment) -> str:
    """
    Produce an L2 (qualitative interpretation) synthesis.
    This is NOT an investment recommendation.
    It synthesizes what the research tells us about business quality.
    """
    parts = []
    ticker = assessment.ticker
    name = assessment.company_name or ticker

    # Understandability
    if assessment.business_understanding:
        bu = assessment.business_understanding
        parts.append(
            f"{name}'s business is {bu.understandability_rating.value.lower()} to understand "
            f"based on available information."
        )

    # Industry
    if assessment.industry_assessment:
        ia = assessment.industry_assessment
        parts.append(
            f"The industry is classified as {ia.classification.value}. "
            f"{ia.classification_reasoning}"
        )
        if ia.challenging_industry_exception_note:
            parts.append(ia.challenging_industry_exception_note)

    # Moat
    if assessment.moat_assessment:
        ma = assessment.moat_assessment
        if ma.overall_strength == MoatStrength.NONE:
            parts.append(
                "No meaningful competitive advantage has been identified. "
                "The business appears to compete in a commodity-like environment."
            )
        elif ma.overall_strength == MoatStrength.WEAK:
            parts.append(
                f"A weak competitive advantage has been identified ({', '.join(ma.active_sources)}), "
                "but its durability and significance are limited."
            )
        else:
            traj_note = {
                MoatTrajectory.STRENGTHENING: "and appears to be strengthening",
                MoatTrajectory.STABLE: "and appears stable",
                MoatTrajectory.WEAKENING: "but shows signs of weakening — this requires close monitoring",
                MoatTrajectory.INSUFFICIENT_DATA: "though trajectory is unclear from available data",
            }.get(ma.trajectory, "")
            parts.append(
                f"A {ma.overall_strength.value.lower()} competitive advantage "
                f"({', '.join(ma.active_sources)}) with {ma.overall_durability.value.lower()} durability "
                f"has been identified, {traj_note}. "
                f"{ma.moat_summary}"
            )
        if ma.current_vs_emerging_note:
            parts.append(ma.current_vs_emerging_note)

    # Management
    if assessment.management_assessment:
        mgmt = assessment.management_assessment
        if mgmt.overall_rating != ManagementRating.INSUFFICIENT_DATA:
            parts.append(
                f"Management is assessed as {mgmt.overall_rating.value}. "
                f"{mgmt.management_summary}"
            )

    # Risk
    if assessment.risk_assessment:
        ra = assessment.risk_assessment
        structural = ra.structural_risks()
        high_sev = ra.high_severity_risks()
        risk_note = f"Overall risk is {ra.overall_level.value.lower()}."
        if structural:
            risk_note += f" {len(structural)} structural risk(s) identified."
        if high_sev:
            risk_note += f" {len(high_sev)} high-severity risk(s) require attention."
        parts.append(risk_note)

    # Growth
    if assessment.growth_assessment:
        ga = assessment.growth_assessment
        if ga.growth_sustainability_assessment:
            parts.append(ga.growth_sustainability_assessment)

    # Level 3 boundary note
    parts.append(
        "[L2 synthesis — this is a business quality interpretation, not a valuation or investment recommendation. "
        "Valuation is assessed separately in Phase 5.]"
    )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Key investment question generator
# ---------------------------------------------------------------------------

def generate_key_questions(assessment: BusinessResearchAssessment) -> List[str]:
    """
    Generate open questions that Phase 7 (Decision Engine) must address
    when combining business quality with valuation and portfolio context.
    """
    questions = []

    if assessment.moat_assessment:
        ma = assessment.moat_assessment
        if ma.trajectory == MoatTrajectory.WEAKENING:
            questions.append(
                "Is the moat erosion temporary (cyclical pressure) or structural "
                "(competitive displacement)? This affects the appropriate discount rate and margin of safety."
            )
        if ma.overall_strength in (MoatStrength.STRONG, MoatStrength.EXCEPTIONAL):
            questions.append(
                "Is the market already pricing in the moat strength? "
                "Even exceptional businesses can be poor investments at premium valuations."
            )

    if assessment.industry_assessment:
        ia = assessment.industry_assessment
        if ia.classification == IndustryClassification.CHALLENGING:
            questions.append(
                "Can the company's competitive advantage insulate it from industry headwinds "
                "for long enough to justify the investment?"
            )

    if assessment.risk_assessment:
        ra = assessment.risk_assessment
        for risk in ra.structural_risks()[:2]:
            questions.append(
                f"Structural risk: '{risk.description[:80]}' — "
                "does the current valuation adequately compensate for this risk?"
            )

    if assessment.bull_bear:
        for breaker in assessment.bull_bear.thesis_breakers[:3]:
            questions.append(f"Thesis breaker: {breaker} — is this currently occurring or imminent?")

    if not questions:
        questions.append(
            "What is the appropriate discount rate given business quality and competitive position? "
            "What valuation multiple is justified by the identified moat strength and growth quality?"
        )

    return questions


# ---------------------------------------------------------------------------
# Full synthesis entry point
# ---------------------------------------------------------------------------

def finalize_assessment(assessment: BusinessResearchAssessment) -> BusinessResearchAssessment:
    """
    Run the full synthesis on a completed (or partially-completed) assessment.
    Populates: business_quality_interpretation, research_gaps, research_flags,
    key_investment_questions, overall_research_confidence.

    Call this after all research dimensions have been filled in.
    """
    # Detect contradictions → flags
    contradictions = detect_contradictions(assessment)
    assessment.research_flags.extend(contradictions)

    # Identify gaps
    gaps = identify_research_gaps(assessment)
    assessment.research_gaps.extend(gaps)

    # L2 synthesis
    assessment.business_quality_interpretation = synthesize_business_quality(assessment)

    # Key questions for Phase 7
    assessment.key_investment_questions = generate_key_questions(assessment)

    # Overall confidence (conservative: limited by weakest populated dimension)
    dim_confidences = list(assessment.confidence_by_dimension.values())
    if not dim_confidences:
        assessment.overall_research_confidence = Confidence.LOW
    elif Confidence.LOW.value in dim_confidences:
        assessment.overall_research_confidence = Confidence.LOW
    elif dim_confidences.count(Confidence.MEDIUM.value) > len(dim_confidences) // 2:
        assessment.overall_research_confidence = Confidence.MEDIUM
    else:
        assessment.overall_research_confidence = Confidence.HIGH

    # Adjust confidence down for incomplete research
    if len(assessment.incomplete_dimensions()) > 2:
        assessment.overall_research_confidence = Confidence.LOW
    elif len(assessment.incomplete_dimensions()) > 0:
        if assessment.overall_research_confidence == Confidence.HIGH:
            assessment.overall_research_confidence = Confidence.MEDIUM

    return assessment


if __name__ == "__main__":
    from analytics.business_research.research_models import (
        BusinessUnderstandingAssessment, IndustryAssessment, MoatAssessment,
        GrowthAssessment, ManagementAssessment, RiskAssessment, BullBearAssessment,
        MoatSourceAnalysis, EvidenceItem, RiskItem,
        UnderstandabilityRating, IndustryClassification,
        MoatStrength, MoatDurability, MoatTrajectory, MoatStatus,
        ManagementRating, RiskLevel, RiskType, Confidence, SourceTier
    )

    print("Testing research_synthesizer.py...")

    a = BusinessResearchAssessment(
        ticker="ATD.TO",
        company_name="Alimentation Couche-Tard",
        assessment_date="2024-12-31",
    )

    a.business_understanding = BusinessUnderstandingAssessment(
        what_it_does="Operates convenience stores and fuel retail across NA, Europe, and Asia",
        how_it_makes_money="Fuel margin, in-store merchandise, private-label goods, Quick Service Restaurants",
        revenue_sources=["Fuel sales", "Merchandise", "Foodservice", "Car wash"],
        understandability_rating=UnderstandabilityRating.SUFFICIENT,
        confidence=Confidence.HIGH,
    )
    a.industry_assessment = IndustryAssessment(
        industry_name="Convenience Store / Fuel Retail",
        classification=IndustryClassification.NEUTRAL,
        classification_reasoning="Mature market with EV transition risk; partial offset from food/convenience growth",
        confidence=Confidence.MEDIUM,
    )
    a.moat_assessment = MoatAssessment(
        overall_strength=MoatStrength.MODERATE,
        overall_durability=MoatDurability.MEDIUM,
        trajectory=MoatTrajectory.STABLE,
        active_sources=["scale", "cost_advantage"],
        moat_summary="Scale-based cost advantages allow better supplier terms; execution excellence sustains margins",
        roic_consistency_note="ROIC above 12% consistently supports the scale/cost advantage thesis",
        confidence=Confidence.MEDIUM,
    )
    a.management_assessment = ManagementAssessment(
        overall_rating=ManagementRating.STRONG,
        management_summary="Exceptional M&A track record; disciplined capital allocation; founder-influenced culture",
        confidence=Confidence.HIGH,
    )
    a.risk_assessment = RiskAssessment(
        overall_level=RiskLevel.MODERATE,
        risk_summary="EV transition is the primary structural risk; execution risk on large acquisitions",
        business_risks=[RiskItem("EV adoption reducing fuel volumes", RiskType.STRUCTURAL, "High")],
        competitive_risks=[RiskItem("Grocery/QSR competition in food", RiskType.TEMPORARY, "Medium")],
        confidence=Confidence.MEDIUM,
    )
    a.growth_assessment = GrowthAssessment(
        growth_sustainability_assessment="Growth sustainable via network expansion and same-store merchandise growth; fuel volume long-term headwind",
        confidence=Confidence.MEDIUM,
    )
    a.bull_bear = BullBearAssessment(
        bull_case_title="Scale compounder with durable margin expansion",
        bull_case_narrative="ATD continues to acquire fragmented markets at attractive multiples, driving ROIC improvement",
        bull_case_assumptions=["Fuel volumes stable for 10+ years", "M&A pipeline remains deep"],
        bear_case_title="EV disruption accelerates, acquisition pipeline dries up",
        bear_case_narrative="EV adoption accelerates faster than expected, eroding high-margin fuel business",
        bear_case_assumptions=["EV fleet >20% by 2030", "Acquisition targets dry up"],
        thesis_breakers=["ROIC falls below 10% for 2+ consecutive years",
                         "Major acquisition destroys capital at scale"],
        devils_advocate_research_note="Actively searched for evidence of fuel margin compression and EV acceleration",
        negative_evidence_found=[
            EvidenceItem(
                fact="European EV adoption running ahead of projections in ATD's core markets",
                source="IEA Global EV Outlook 2024",
                source_tier=SourceTier.TIER_2_SECONDARY,
                supports_thesis=False,
                confidence=Confidence.MEDIUM,
            )
        ],
        confirmation_bias_check="What would make me NOT invest: ROIC below 10%, fuel volumes declining >5%/yr, management departure",
    )

    a.confidence_by_dimension = {
        "business_understanding": Confidence.HIGH.value,
        "industry": Confidence.MEDIUM.value,
        "moat": Confidence.MEDIUM.value,
        "management": Confidence.HIGH.value,
        "risks": Confidence.MEDIUM.value,
        "growth": Confidence.MEDIUM.value,
        "bull_bear": Confidence.MEDIUM.value,
    }
    a.register_evidence(EvidenceItem(
        fact="ATD FY2024 ROIC: 14.2%",
        source="ATD FY2024 Annual Report",
        source_tier=SourceTier.TIER_1_PRIMARY,
        confidence=Confidence.HIGH,
        supports_thesis=True,
    ))

    a = finalize_assessment(a)
    print(a.summary_text())
    print(f"\nContradictions found: {len(a.research_flags)}")
    print(f"Research gaps: {len(a.research_gaps)}")
    print(f"Overall confidence: {a.overall_research_confidence.value}")
    print("\nresearch_synthesizer.py: OK")
