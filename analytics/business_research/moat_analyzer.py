"""
Moat Analyzer
=============
Implements the structured Claim → Evidence → Durability → Threats → Conclusion
framework for competitive advantage analysis.

This module:
  1. Provides the MoatAnalyzer builder — used to construct MoatSourceAnalysis
     objects with proper validation at each step.
  2. Provides the MoatAssessmentBuilder — aggregates individual source analyses
     into an overall MoatAssessment.
  3. Provides helper functions for synthesizing moat conclusions.

Key design principles:
  - No conclusion without evidence
  - Brand recognition alone NEVER qualifies as a moat
  - Distinguish current / emerging / weakening
  - ROIC provides supporting (not conclusive) evidence for moat existence
  - Threats must be explicitly considered before concluding moat strength
"""

import sys
from pathlib import Path
from typing import Optional, List
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.business_research.research_models import (
    MoatSourceAnalysis, MoatAssessment, EvidenceItem,
    MoatStrength, MoatDurability, MoatTrajectory, MoatStatus,
    Confidence, SourceTier, ResearchLevel, MOAT_SOURCE_TYPES
)


# ---------------------------------------------------------------------------
# ROIC → moat support mapping
# ---------------------------------------------------------------------------

def roic_moat_support_note(roic_current: Optional[float], roic_5yr_avg: Optional[float]) -> str:
    """
    Derive a ROIC-based moat support note.
    High sustained ROIC supports (but does not prove) a moat.
    """
    if roic_current is None:
        return "ROIC data unavailable — cannot use as moat evidence"
    parts = []
    if roic_current >= 15:
        parts.append(f"Current ROIC of {roic_current:.1f}% is above the 15% threshold that supports strong economics")
    elif roic_current >= 10:
        parts.append(f"Current ROIC of {roic_current:.1f}% indicates adequate capital returns")
    else:
        parts.append(f"Current ROIC of {roic_current:.1f}% is below preferred threshold — may challenge moat thesis")

    if roic_5yr_avg is not None:
        if roic_5yr_avg >= 15:
            parts.append(f"5yr avg ROIC of {roic_5yr_avg:.1f}% suggests sustained competitive advantage")
        elif roic_5yr_avg >= roic_current + 3:
            parts.append(f"5yr avg ROIC ({roic_5yr_avg:.1f}%) > current ({roic_current:.1f}%) — potential erosion")

    parts.append(
        "Note: High ROIC can SUPPORT a moat thesis but cannot prove it — "
        "qualitative verification of the competitive mechanism is required."
    )
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Moat source builder — enforces the framework step by step
# ---------------------------------------------------------------------------

class MoatSourceBuilder:
    """
    Fluent builder for MoatSourceAnalysis.
    Enforces the Claim → Evidence → Durability → Threats → Conclusion sequence.

    Usage:
        analysis = (
            MoatSourceBuilder("switching_costs")
            .claim("High ERP switching costs lock in enterprise clients")
            .add_evidence(EvidenceItem(...))
            .durability(MoatDurability.HIGH, "ERP migrations typically take 2+ years")
            .threats(["Open-source ERPs", "Cloud disaggregation"])
            .conclude(MoatStatus.CURRENT, MoatStrength.STRONG,
                      "Switching costs are real and measurable — NRR > 120% supports retention")
            .build()
        )
    """

    def __init__(self, moat_type: str):
        if moat_type not in MOAT_SOURCE_TYPES:
            raise ValueError(f"moat_type must be one of: {MOAT_SOURCE_TYPES}")
        self._type = moat_type
        self._claim = ""
        self._evidence: List[EvidenceItem] = []
        self._durability = MoatDurability.MEDIUM
        self._durability_reasoning = ""
        self._threats: List[str] = []
        self._status = MoatStatus.ABSENT
        self._strength = MoatStrength.NONE
        self._conclusion = ""
        self._confidence = Confidence.MEDIUM
        self._brand_pricing_power: Optional[bool] = None
        self._brand_retention: Optional[bool] = None
        self._brand_switching: Optional[bool] = None

    def claim(self, text: str) -> "MoatSourceBuilder":
        self._claim = text
        return self

    def add_evidence(self, item: EvidenceItem) -> "MoatSourceBuilder":
        self._evidence.append(item)
        return self

    def durability(
        self,
        level: MoatDurability,
        reasoning: str = ""
    ) -> "MoatSourceBuilder":
        self._durability = level
        self._durability_reasoning = reasoning
        return self

    def threats(self, threat_list: List[str]) -> "MoatSourceBuilder":
        self._threats = threat_list
        return self

    def conclude(
        self,
        status: MoatStatus,
        strength: MoatStrength,
        conclusion_text: str,
        confidence: Confidence = Confidence.MEDIUM
    ) -> "MoatSourceBuilder":
        self._status = status
        self._strength = strength
        self._conclusion = conclusion_text
        self._confidence = confidence
        return self

    def brand_evidence(
        self,
        pricing_power: Optional[bool] = None,
        retention: Optional[bool] = None,
        switching_costs: Optional[bool] = None
    ) -> "MoatSourceBuilder":
        """Required call for brand moat type."""
        self._brand_pricing_power = pricing_power
        self._brand_retention = retention
        self._brand_switching = switching_costs
        return self

    def build(self) -> MoatSourceAnalysis:
        source = MoatSourceAnalysis(
            moat_type=self._type,
            claim=self._claim,
            evidence=self._evidence,
            durability=self._durability,
            durability_reasoning=self._durability_reasoning,
            threats=self._threats,
            status=self._status,
            strength=self._strength,
            conclusion=self._conclusion,
            confidence=self._confidence,
            brand_demonstrates_pricing_power=self._brand_pricing_power,
            brand_demonstrates_retention=self._brand_retention,
            brand_demonstrates_switching_costs=self._brand_switching,
        )
        issues = source.validate()
        if issues:
            raise ValueError(
                f"MoatSourceAnalysis for '{self._type}' failed validation:\n" +
                "\n".join(f"  • {i}" for i in issues)
            )
        return source


# ---------------------------------------------------------------------------
# Overall moat assessment builder
# ---------------------------------------------------------------------------

class MoatAssessmentBuilder:
    """
    Aggregates individual MoatSourceAnalysis objects into a MoatAssessment.

    Determines overall moat strength, durability, and trajectory from
    the individual source analyses.
    """

    def __init__(self):
        self._sources: List[MoatSourceAnalysis] = []
        self._trajectory = MoatTrajectory.INSUFFICIENT_DATA
        self._current_vs_emerging_note = ""
        self._moat_summary = ""
        self._roic_note = ""
        self._confidence = Confidence.MEDIUM
        self._research_gaps: List[str] = []

    def add_source(self, source: MoatSourceAnalysis) -> "MoatAssessmentBuilder":
        self._sources.append(source)
        return self

    def trajectory(
        self,
        traj: MoatTrajectory,
        note: str = ""
    ) -> "MoatAssessmentBuilder":
        self._trajectory = traj
        self._current_vs_emerging_note = note
        return self

    def summary(self, text: str) -> "MoatAssessmentBuilder":
        self._moat_summary = text
        return self

    def roic_note(self, note: str) -> "MoatAssessmentBuilder":
        self._roic_note = note
        return self

    def confidence(self, level: Confidence) -> "MoatAssessmentBuilder":
        self._confidence = level
        return self

    def research_gap(self, gap: str) -> "MoatAssessmentBuilder":
        self._research_gaps.append(gap)
        return self

    def build(self) -> MoatAssessment:
        active_sources = [
            s.moat_type for s in self._sources
            if s.status in (MoatStatus.CURRENT, MoatStatus.EMERGING)
            and s.strength != MoatStrength.NONE
        ]
        current_sources = [
            s for s in self._sources if s.status == MoatStatus.CURRENT
        ]
        emerging_sources = [
            s for s in self._sources if s.status == MoatStatus.EMERGING
        ]

        overall_strength = _aggregate_strength(current_sources)
        overall_durability = _aggregate_durability(current_sources + emerging_sources)

        return MoatAssessment(
            sources_investigated=self._sources,
            active_sources=active_sources,
            overall_strength=overall_strength,
            overall_durability=overall_durability,
            trajectory=self._trajectory,
            current_vs_emerging_note=self._current_vs_emerging_note,
            moat_summary=self._moat_summary,
            roic_consistency_note=self._roic_note,
            confidence=self._confidence,
            research_gaps=self._research_gaps,
        )


# ---------------------------------------------------------------------------
# Strength / durability aggregation helpers
# ---------------------------------------------------------------------------

_STRENGTH_ORDER = [
    MoatStrength.NONE, MoatStrength.WEAK, MoatStrength.MODERATE,
    MoatStrength.STRONG, MoatStrength.EXCEPTIONAL
]

_DURABILITY_ORDER = [MoatDurability.LOW, MoatDurability.MEDIUM, MoatDurability.HIGH]


def _aggregate_strength(sources: List[MoatSourceAnalysis]) -> MoatStrength:
    """
    Aggregate strength from multiple moat sources.
    Strategy: the strongest individual source sets the floor;
    multiple reinforcing sources can elevate the overall.
    """
    if not sources:
        return MoatStrength.NONE
    strengths = [s.strength for s in sources if s.strength != MoatStrength.NONE]
    if not strengths:
        return MoatStrength.NONE
    max_idx = max(_STRENGTH_ORDER.index(s) for s in strengths)
    # Multiple strong sources → one tier up (capped at EXCEPTIONAL)
    reinforcement_boost = 1 if len(strengths) >= 2 else 0
    final_idx = min(max_idx + reinforcement_boost, len(_STRENGTH_ORDER) - 1)
    return _STRENGTH_ORDER[final_idx]


def _aggregate_durability(sources: List[MoatSourceAnalysis]) -> MoatDurability:
    """
    Aggregate durability: limited by the lowest-durability active source,
    but elevated if all sources are high-durability.
    """
    if not sources:
        return MoatDurability.MEDIUM
    durabilities = [s.durability for s in sources]
    # If any source is LOW durability, overall is at most MEDIUM
    if MoatDurability.LOW in durabilities:
        return MoatDurability.LOW
    if all(d == MoatDurability.HIGH for d in durabilities):
        return MoatDurability.HIGH
    return MoatDurability.MEDIUM


# ---------------------------------------------------------------------------
# Moat description helper for reports
# ---------------------------------------------------------------------------

def moat_description(assessment: MoatAssessment) -> str:
    """
    Generate a structured moat description paragraph from a MoatAssessment.
    Follows the Claim → Evidence → Durability → Threats → Conclusion format.
    """
    lines = [
        f"Moat Strength: {assessment.overall_strength.value} | "
        f"Durability: {assessment.overall_durability.value} | "
        f"Trajectory: {assessment.trajectory.value}",
        "",
    ]

    if assessment.active_sources:
        lines.append(f"Active competitive advantages: {', '.join(assessment.active_sources)}")
    else:
        lines.append("No confirmed competitive advantages identified.")

    lines.append("")
    for source in assessment.sources_investigated:
        if source.status == MoatStatus.ABSENT:
            continue
        lines += [
            f"[{source.moat_type.upper()}] — {source.status.value} | {source.strength.value}",
            f"  Claim: {source.claim}",
        ]
        for e in source.evidence[:2]:
            lines.append(f"  Evidence: {e.fact} ({e.source_tier.value})")
        lines.append(f"  Durability: {source.durability.value} — {source.durability_reasoning}")
        if source.threats:
            lines.append(f"  Threats: {'; '.join(source.threats[:3])}")
        lines.append(f"  Conclusion: {source.conclusion}")
        lines.append("")

    if assessment.moat_summary:
        lines.append(f"Overall: {assessment.moat_summary}")
    if assessment.roic_consistency_note:
        lines.append(f"ROIC consistency: {assessment.roic_consistency_note}")
    if assessment.current_vs_emerging_note:
        lines.append(f"Current vs. emerging: {assessment.current_vs_emerging_note}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Testing moat_analyzer.py...")

    # Build a switching-cost moat for a hypothetical software company
    e1 = EvidenceItem(
        fact="Net revenue retention rate > 120% for five consecutive years",
        source="Company Annual Report FY2024",
        source_tier=SourceTier.TIER_1_PRIMARY,
        interpretation="Customers expand usage over time, indicating genuine stickiness",
        research_level=ResearchLevel.L2_INTERPRETATION,
        confidence=Confidence.HIGH,
        supports_thesis=True
    )
    e2 = EvidenceItem(
        fact="Average customer contract length of 3.2 years with 95% renewal rate",
        source="Investor Day Presentation 2024",
        source_tier=SourceTier.TIER_1_PRIMARY,
        confidence=Confidence.HIGH,
        supports_thesis=True
    )

    switching_cost = (
        MoatSourceBuilder("switching_costs")
        .claim("Deep integration with customer workflows creates high switching costs — migration risk is multi-year")
        .add_evidence(e1)
        .add_evidence(e2)
        .durability(MoatDurability.HIGH, "ERP/workflow integrations take 2+ years to replace; data migration risk")
        .threats(["API commoditization", "AI-native competitor workflows", "Open-source alternatives"])
        .conclude(
            MoatStatus.CURRENT,
            MoatStrength.STRONG,
            "Switching costs are real, measurable, and multi-year — supported by NRR and renewal rate data",
            Confidence.HIGH
        )
        .build()
    )
    print(f"  Switching cost moat built: {switching_cost.strength.value}, valid: {not switching_cost.validate()}")

    # Test that brand without evidence fails
    try:
        bad = (
            MoatSourceBuilder("brand")
            .claim("Well-known brand")
            .conclude(MoatStatus.CURRENT, MoatStrength.STRONG, "Strong brand = moat")
            .build()
        )
        print("  FAIL: Brand without evidence should have raised ValueError")
    except ValueError as e:
        print(f"  Brand without evidence correctly blocked: {str(e)[:80]}...")

    # Build overall assessment
    builder = MoatAssessmentBuilder()
    builder.add_source(switching_cost)
    builder.trajectory(MoatTrajectory.STABLE, "Current moat is established; no emerging sources identified")
    builder.summary("Strong switching-cost moat supported by multi-year NRR and renewal data.")
    builder.roic_note(roic_moat_support_note(18.5, 16.2))
    builder.confidence(Confidence.HIGH)
    assessment = builder.build()

    print(f"  Overall strength: {assessment.overall_strength.value}")
    print(f"  Durability: {assessment.overall_durability.value}")
    print(f"  Active sources: {assessment.active_sources}")
    print("\n" + moat_description(assessment))
    print("moat_analyzer.py: OK")
