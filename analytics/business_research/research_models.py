"""
Business Research Data Models
==============================
Defines the structured data containers for qualitative investment research.

Architecture boundary (strictly enforced):
  Level 1 — Quantitative fact        e.g. "5yr ROIC = 14.2%"
  Level 2 — Qualitative interpretation  e.g. "Consistently high ROIC supports strong economics"
  Level 3 — Investment conclusion     e.g. "Business quality appears strong; valuation TBD"

These levels are NEVER collapsed into a single score.
Valuation is NOT part of Phase 4.
Final investment recommendation is NOT part of Phase 4.

How this fits the system:
  Phase 2 (data) → Phase 3 (FinancialQualityAssessment)
                 → Phase 4 (BusinessResearchAssessment)   ← this file
                 → Phase 5 (ValuationAssessment)
  All four feed → Phase 7 (InvestmentDecisionEngine)
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SourceTier(str, Enum):
    TIER_1_PRIMARY = "Tier 1 — Primary"        # SEC/SEDAR+, annual/quarterly reports, investor presentations
    TIER_2_SECONDARY = "Tier 2 — Secondary"    # Reputable financial databases, industry research
    TIER_3_SUPPORTING = "Tier 3 — Supporting"  # Investor commentary, forums, social media

class ResearchLevel(str, Enum):
    L1_FACT = "L1 — Quantitative Fact"
    L2_INTERPRETATION = "L2 — Qualitative Interpretation"
    L3_CONCLUSION = "L3 — Investment Conclusion"

class Confidence(str, Enum):
    HIGH = "High"       # Strong data, consistent signals, reliable sources
    MEDIUM = "Medium"   # Adequate data, some uncertainty
    LOW = "Low"         # Limited data, conflicting signals, speculation

class MoatStrength(str, Enum):
    NONE = "None"
    WEAK = "Weak"
    MODERATE = "Moderate"
    STRONG = "Strong"
    EXCEPTIONAL = "Exceptional"

class MoatDurability(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"

class MoatTrajectory(str, Enum):
    STRENGTHENING = "Strengthening"
    STABLE = "Stable"
    WEAKENING = "Weakening"
    INSUFFICIENT_DATA = "Insufficient Data"

class MoatStatus(str, Enum):
    CURRENT = "Current"          # Demonstrably active competitive advantage
    EMERGING = "Emerging"        # Credible but not yet fully established
    WEAKENING = "Weakening"      # Previously present but eroding
    ABSENT = "Absent"            # No credible moat identified

class IndustryClassification(str, Enum):
    ATTRACTIVE = "Attractive"
    NEUTRAL = "Neutral"
    CHALLENGING = "Challenging"

class RiskLevel(str, Enum):
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"

class RiskType(str, Enum):
    TEMPORARY = "Temporary"
    STRUCTURAL = "Structural"
    UNCERTAIN = "Uncertain"

class ManagementRating(str, Enum):
    STRONG = "Strong"
    GOOD = "Good"
    MIXED = "Mixed"
    WEAK = "Weak"
    INSUFFICIENT_DATA = "Insufficient Data"

class UnderstandabilityRating(str, Enum):
    SUFFICIENT = "Sufficient"
    BORDERLINE = "Borderline"
    INSUFFICIENT = "Insufficient"


# ---------------------------------------------------------------------------
# Evidence item — the atomic unit of research
# ---------------------------------------------------------------------------

@dataclass
class EvidenceItem:
    """
    A single piece of research evidence with full provenance.

    Separating fact / source / interpretation / confidence prevents
    the common error of conflating what is known with what it means.
    """
    fact: str                                      # The factual claim (L1)
    source: str                                    # Where this came from
    source_tier: SourceTier = SourceTier.TIER_2_SECONDARY
    source_date: str = ""                          # ISO date or fiscal period
    interpretation: str = ""                       # What this means in context (L2)
    research_level: ResearchLevel = ResearchLevel.L1_FACT
    confidence: Confidence = Confidence.MEDIUM
    supports_thesis: Optional[bool] = None         # True=bullish, False=bearish, None=neutral
    notes: str = ""

    def is_tier1(self) -> bool:
        return self.source_tier == SourceTier.TIER_1_PRIMARY

    def to_dict(self) -> dict:
        d = asdict(self)
        # Convert Enum values to strings for JSON serialization
        d["source_tier"] = self.source_tier.value
        d["research_level"] = self.research_level.value
        d["confidence"] = self.confidence.value
        return d

    def summary(self) -> str:
        level_str = f"[{self.research_level.value}]"
        tier_str = f"({self.source_tier.value})"
        interp = f" → {self.interpretation}" if self.interpretation else ""
        return f"{level_str} {self.fact}{interp} {tier_str}"


# ---------------------------------------------------------------------------
# Risk item
# ---------------------------------------------------------------------------

@dataclass
class RiskItem:
    """A single identified risk with classification."""
    description: str
    risk_type: RiskType = RiskType.UNCERTAIN
    severity: str = ""         # High / Medium / Low
    likelihood: str = ""       # High / Medium / Low
    mitigants: List[str] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["risk_type"] = self.risk_type.value
        return d


# ---------------------------------------------------------------------------
# Moat source analysis — enforces Claim → Evidence → Durability → Threats → Conclusion
# ---------------------------------------------------------------------------

MOAT_SOURCE_TYPES = [
    "network_effects", "switching_costs", "cost_advantage", "scale",
    "brand", "intellectual_property", "regulatory_barriers",
    "efficient_scale", "ecosystem", "distribution_advantage",
    "data_advantage", "other"
]

@dataclass
class MoatSourceAnalysis:
    """
    Analysis of a single potential moat source.

    Enforces the mandatory framework:
      Claim → Evidence → Durability → Threats → Conclusion

    Brand recognition alone is NOT sufficient to conclude a moat exists.
    The evidence must demonstrate at least one of:
      - Pricing power
      - Customer retention above industry norms
      - Switching costs
      - Superior margins sustained over time
      - Market-share durability
    """
    moat_type: str                                  # from MOAT_SOURCE_TYPES

    # Step 1: Claim
    claim: str = ""                                 # "We claim this company has X advantage because..."

    # Step 2: Evidence (minimum 1 required for any positive conclusion)
    evidence: List[EvidenceItem] = field(default_factory=list)

    # Step 3: Durability
    durability: MoatDurability = MoatDurability.MEDIUM
    durability_reasoning: str = ""

    # Step 4: Threats
    threats: List[str] = field(default_factory=list)

    # Step 5: Conclusion
    status: MoatStatus = MoatStatus.ABSENT
    strength: MoatStrength = MoatStrength.NONE
    conclusion: str = ""                             # Full reasoning sentence
    confidence: Confidence = Confidence.MEDIUM

    # Brand-specific guardrail
    brand_demonstrates_pricing_power: Optional[bool] = None  # Required if moat_type == "brand"
    brand_demonstrates_retention: Optional[bool] = None
    brand_demonstrates_switching_costs: Optional[bool] = None

    def validate(self) -> List[str]:
        """
        Check that the mandatory framework is followed.
        Returns list of validation issues.
        """
        issues = []
        if self.status != MoatStatus.ABSENT and not self.claim:
            issues.append(f"{self.moat_type}: Missing claim")
        if self.status != MoatStatus.ABSENT and not self.evidence:
            issues.append(f"{self.moat_type}: Positive conclusion requires at least one evidence item")
        if not self.conclusion:
            issues.append(f"{self.moat_type}: Missing conclusion")
        if self.moat_type == "brand" and self.status != MoatStatus.ABSENT:
            if not any([
                self.brand_demonstrates_pricing_power,
                self.brand_demonstrates_retention,
                self.brand_demonstrates_switching_costs
            ]):
                issues.append(
                    f"brand: Brand moat conclusion requires evidence of pricing power, "
                    "retention, or switching costs — brand recognition alone is insufficient"
                )
        return issues

    def to_dict(self) -> dict:
        d = asdict(self)
        d["durability"] = self.durability.value
        d["status"] = self.status.value
        d["strength"] = self.strength.value
        d["confidence"] = self.confidence.value
        d["evidence"] = [e.to_dict() for e in self.evidence]
        d["_validation_issues"] = self.validate()
        return d


# ---------------------------------------------------------------------------
# Individual research dimension models
# ---------------------------------------------------------------------------

@dataclass
class BusinessUnderstandingAssessment:
    """
    Can this business be understood sufficiently to make an investment judgment?

    If understandability_rating == INSUFFICIENT, no further positive
    investment conclusion should be forced. Flag for human review.
    """
    what_it_does: str = ""
    how_it_makes_money: str = ""
    main_products_services: List[str] = field(default_factory=list)
    main_customer_groups: List[str] = field(default_factory=list)
    revenue_sources: List[str] = field(default_factory=list)
    major_cost_drivers: List[str] = field(default_factory=list)
    geographic_exposure: Dict[str, str] = field(default_factory=dict)   # region: description
    key_business_drivers: List[str] = field(default_factory=list)
    major_competitors: List[str] = field(default_factory=list)
    understandability_rating: UnderstandabilityRating = UnderstandabilityRating.BORDERLINE
    understandability_note: str = ""
    confidence: Confidence = Confidence.MEDIUM
    evidence: List[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["understandability_rating"] = self.understandability_rating.value
        d["confidence"] = self.confidence.value
        d["evidence"] = [e.to_dict() for e in self.evidence]
        return d


@dataclass
class IndustryAssessment:
    """Industry-level attractiveness assessment."""
    industry_name: str = ""
    industry_growth_outlook: str = ""
    long_term_demand_drivers: List[str] = field(default_factory=list)
    competitive_intensity: str = ""
    barriers_to_entry: str = ""
    regulatory_environment: str = ""
    cyclicality: str = ""
    capital_intensity: str = ""
    technology_disruption_risk: str = ""
    substitution_risk: str = ""
    structural_trends: List[str] = field(default_factory=list)
    industry_profitability: str = ""

    classification: IndustryClassification = IndustryClassification.NEUTRAL
    classification_reasoning: str = ""
    challenging_industry_exception_note: str = ""  # Populated if challenging but company has strong moat
    confidence: Confidence = Confidence.MEDIUM
    evidence: List[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["classification"] = self.classification.value
        d["confidence"] = self.confidence.value
        d["evidence"] = [e.to_dict() for e in self.evidence]
        return d


@dataclass
class MoatAssessment:
    """
    Competitive advantage / moat assessment.

    Does NOT simply label a company as "having a moat."
    Each potential source is evaluated individually using the
    Claim → Evidence → Durability → Threats → Conclusion framework.
    """
    sources_investigated: List[MoatSourceAnalysis] = field(default_factory=list)
    active_sources: List[str] = field(default_factory=list)     # moat_types with positive conclusion

    overall_strength: MoatStrength = MoatStrength.NONE
    overall_durability: MoatDurability = MoatDurability.MEDIUM
    trajectory: MoatTrajectory = MoatTrajectory.INSUFFICIENT_DATA

    current_vs_emerging_note: str = ""     # Explicitly distinguish current from potential moat
    moat_summary: str = ""                 # Full reasoning paragraph
    roic_consistency_note: str = ""        # Does ROIC data support or challenge moat thesis?

    confidence: Confidence = Confidence.MEDIUM
    research_gaps: List[str] = field(default_factory=list)

    def validate_all_sources(self) -> Dict[str, List[str]]:
        """Validate all moat source analyses. Returns {moat_type: [issues]}."""
        results = {}
        for s in self.sources_investigated:
            issues = s.validate()
            if issues:
                results[s.moat_type] = issues
        return results

    def to_dict(self) -> dict:
        d = asdict(self)
        d["overall_strength"] = self.overall_strength.value
        d["overall_durability"] = self.overall_durability.value
        d["trajectory"] = self.trajectory.value
        d["confidence"] = self.confidence.value
        d["sources_investigated"] = [s.to_dict() for s in self.sources_investigated]
        d["_validation_issues"] = self.validate_all_sources()
        return d


@dataclass
class GrowthAssessment:
    """
    Qualitative growth quality assessment.
    Works alongside the quantitative growth metrics from Phase 3.
    """
    revenue_growth_quality: str = ""        # Quality of growth (organic? sustainable? driven by what?)
    growth_drivers: List[str] = field(default_factory=list)
    addressable_market_note: str = ""
    market_share_trajectory: str = ""
    organic_vs_inorganic: str = ""
    reinvestment_requirements: str = ""     # How much must be reinvested to sustain growth?
    growth_sustainability_assessment: str = ""
    growth_ceiling_risks: List[str] = field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM
    evidence: List[EvidenceItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence"] = self.confidence.value
        d["evidence"] = [e.to_dict() for e in self.evidence]
        return d


@dataclass
class ManagementAssessment:
    """
    Management quality assessment.
    Investor sentiment is supporting evidence only, never primary evidence.
    """
    capital_allocation: str = ""
    execution_track_record: str = ""
    strategic_consistency: str = ""
    guidance_credibility: str = ""
    governance: str = ""
    incentive_alignment: str = ""
    insider_ownership_note: str = ""
    notable_acquisitions: List[str] = field(default_factory=list)
    notable_buybacks: str = ""
    debt_management: str = ""
    shareholder_treatment: str = ""

    overall_rating: ManagementRating = ManagementRating.INSUFFICIENT_DATA
    management_summary: str = ""
    confidence: Confidence = Confidence.MEDIUM
    evidence: List[EvidenceItem] = field(default_factory=list)
    sentiment_note: str = ""   # Investor sentiment explicitly flagged as supporting only

    def to_dict(self) -> dict:
        d = asdict(self)
        d["overall_rating"] = self.overall_rating.value
        d["confidence"] = self.confidence.value
        d["evidence"] = [e.to_dict() for e in self.evidence]
        return d


@dataclass
class RiskAssessment:
    """
    Comprehensive risk assessment.
    Every risk is classified as temporary or structural where possible.
    """
    business_risks: List[RiskItem] = field(default_factory=list)
    financial_risks: List[RiskItem] = field(default_factory=list)
    industry_risks: List[RiskItem] = field(default_factory=list)
    competitive_risks: List[RiskItem] = field(default_factory=list)
    regulatory_risks: List[RiskItem] = field(default_factory=list)
    technology_risks: List[RiskItem] = field(default_factory=list)
    management_risks: List[RiskItem] = field(default_factory=list)
    valuation_risks: List[RiskItem] = field(default_factory=list)
    macro_risks: List[RiskItem] = field(default_factory=list)

    overall_level: RiskLevel = RiskLevel.MODERATE
    risk_summary: str = ""
    temporary_vs_structural_note: str = ""
    confidence: Confidence = Confidence.MEDIUM

    def all_risks(self) -> List[RiskItem]:
        return (
            self.business_risks + self.financial_risks + self.industry_risks +
            self.competitive_risks + self.regulatory_risks + self.technology_risks +
            self.management_risks + self.valuation_risks + self.macro_risks
        )

    def high_severity_risks(self) -> List[RiskItem]:
        return [r for r in self.all_risks() if r.severity == "High"]

    def structural_risks(self) -> List[RiskItem]:
        return [r for r in self.all_risks() if r.risk_type == RiskType.STRUCTURAL]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["overall_level"] = self.overall_level.value
        d["confidence"] = self.confidence.value
        for cat in ["business_risks", "financial_risks", "industry_risks",
                    "competitive_risks", "regulatory_risks", "technology_risks",
                    "management_risks", "valuation_risks", "macro_risks"]:
            d[cat] = [r.to_dict() for r in getattr(self, cat)]
        return d


@dataclass
class BullBearAssessment:
    """
    Bull and bear cases with explicit devil's advocate component.

    The bear case is MANDATORY and must be researched actively —
    not merely listed as a theoretical possibility.
    """
    # Bull case
    bull_case_title: str = ""
    bull_case_narrative: str = ""
    bull_case_assumptions: List[str] = field(default_factory=list)
    bull_case_catalysts: List[str] = field(default_factory=list)
    bull_case_confidence: Confidence = Confidence.MEDIUM

    # Bear case (devil's advocate)
    bear_case_title: str = ""
    bear_case_narrative: str = ""
    bear_case_assumptions: List[str] = field(default_factory=list)
    bear_case_catalysts: List[str] = field(default_factory=list)   # Events that would trigger the bear case
    bear_case_confidence: Confidence = Confidence.MEDIUM

    # Thesis breakers — conditions that would make you NOT invest / EXIT
    thesis_breakers: List[str] = field(default_factory=list)

    # Devil's advocate note: what evidence was found AGAINST the thesis?
    devils_advocate_research_note: str = ""
    negative_evidence_found: List[EvidenceItem] = field(default_factory=list)
    confirmation_bias_check: str = ""    # Explicit statement of what would disprove the thesis

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bull_case_confidence"] = self.bull_case_confidence.value
        d["bear_case_confidence"] = self.bear_case_confidence.value
        d["negative_evidence_found"] = [e.to_dict() for e in self.negative_evidence_found]
        return d

    def is_complete(self) -> bool:
        """Check that both bull and bear cases have been filled in."""
        return bool(
            self.bull_case_narrative and
            self.bear_case_narrative and
            self.thesis_breakers and
            self.devils_advocate_research_note
        )


# ---------------------------------------------------------------------------
# Master research assessment container
# ---------------------------------------------------------------------------

@dataclass
class BusinessResearchAssessment:
    """
    Master container for all qualitative research on a single company.

    This is the Phase 4 output. It does NOT contain:
    - Valuation (Phase 5)
    - Portfolio fit (Phase 6)
    - Final investment decision (Phase 7)

    It DOES contain structured qualitative research that Claude can later
    combine with quantitative metrics and valuation to make a decision.
    """
    # Identification
    ticker: str = ""
    company_name: str = ""
    exchange: str = ""
    sector: str = ""
    industry: str = ""
    geography: str = ""
    assessment_date: str = ""
    analyst_note: str = "AI Research Agent + Human Review"

    # Core research dimensions
    business_understanding: Optional[BusinessUnderstandingAssessment] = None
    industry_assessment: Optional[IndustryAssessment] = None
    moat_assessment: Optional[MoatAssessment] = None
    growth_assessment: Optional[GrowthAssessment] = None
    management_assessment: Optional[ManagementAssessment] = None
    risk_assessment: Optional[RiskAssessment] = None
    bull_bear: Optional[BullBearAssessment] = None

    # Evidence registry — all evidence items from all dimensions
    evidence_registry: List[EvidenceItem] = field(default_factory=list)

    # Research quality
    research_completeness: Dict[str, bool] = field(default_factory=dict)
    research_gaps: List[str] = field(default_factory=list)
    research_flags: List[str] = field(default_factory=list)   # Items needing further investigation
    data_sources_used: List[str] = field(default_factory=list)

    # Overall assessment (L2 — interpretation, not L3 conclusion)
    business_quality_interpretation: str = ""   # L2 synthesis of all dimensions
    key_investment_questions: List[str] = field(default_factory=list)  # Open questions for Phase 7

    # Confidence
    confidence_by_dimension: Dict[str, str] = field(default_factory=dict)
    overall_research_confidence: Confidence = Confidence.MEDIUM

    def register_evidence(self, item: EvidenceItem) -> None:
        """Add an evidence item to the central registry."""
        self.evidence_registry.append(item)

    def tier1_evidence_count(self) -> int:
        return sum(1 for e in self.evidence_registry if e.is_tier1())

    def negative_evidence_count(self) -> int:
        return sum(1 for e in self.evidence_registry if e.supports_thesis is False)

    def completeness_check(self) -> Dict[str, bool]:
        """Check which research dimensions have been completed."""
        return {
            "business_understanding": self.business_understanding is not None,
            "industry_assessment": self.industry_assessment is not None,
            "moat_assessment": self.moat_assessment is not None,
            "growth_assessment": self.growth_assessment is not None,
            "management_assessment": self.management_assessment is not None,
            "risk_assessment": self.risk_assessment is not None,
            "bull_bear": self.bull_bear is not None and (self.bull_bear.is_complete() if self.bull_bear else False),
        }

    def incomplete_dimensions(self) -> List[str]:
        return [k for k, v in self.completeness_check().items() if not v]

    def validate(self) -> List[str]:
        issues = []
        if not self.ticker:
            issues.append("Missing ticker")
        if not self.assessment_date:
            issues.append("Missing assessment_date")
        incomplete = self.incomplete_dimensions()
        if incomplete:
            issues.append(f"Incomplete dimensions: {', '.join(incomplete)}")
        if self.moat_assessment:
            moat_issues = self.moat_assessment.validate_all_sources()
            for moat_type, moat_issues_list in moat_issues.items():
                for issue in moat_issues_list:
                    issues.append(f"Moat/{moat_type}: {issue}")
        if self.bull_bear and not self.bull_bear.is_complete():
            issues.append("Bull/bear assessment is incomplete")
        if not self.evidence_registry:
            issues.append("No evidence items registered — research may not have been conducted")
        return issues

    def to_dict(self) -> dict:
        from datetime import datetime
        d = {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "exchange": self.exchange,
            "sector": self.sector,
            "industry": self.industry,
            "geography": self.geography,
            "assessment_date": self.assessment_date,
            "analyst_note": self.analyst_note,
            "business_quality_interpretation": self.business_quality_interpretation,
            "key_investment_questions": self.key_investment_questions,
            "research_completeness": self.completeness_check(),
            "research_gaps": self.research_gaps,
            "research_flags": self.research_flags,
            "data_sources_used": self.data_sources_used,
            "overall_research_confidence": self.overall_research_confidence.value,
            "confidence_by_dimension": self.confidence_by_dimension,
            "tier1_evidence_count": self.tier1_evidence_count(),
            "negative_evidence_count": self.negative_evidence_count(),
            "total_evidence_items": len(self.evidence_registry),
            "_generated_at": datetime.utcnow().isoformat(),
        }
        if self.business_understanding:
            d["business_understanding"] = self.business_understanding.to_dict()
        if self.industry_assessment:
            d["industry_assessment"] = self.industry_assessment.to_dict()
        if self.moat_assessment:
            d["moat_assessment"] = self.moat_assessment.to_dict()
        if self.growth_assessment:
            d["growth_assessment"] = self.growth_assessment.to_dict()
        if self.management_assessment:
            d["management_assessment"] = self.management_assessment.to_dict()
        if self.risk_assessment:
            d["risk_assessment"] = self.risk_assessment.to_dict()
        if self.bull_bear:
            d["bull_bear"] = self.bull_bear.to_dict()
        d["evidence_registry"] = [e.to_dict() for e in self.evidence_registry]
        d["_validation_issues"] = self.validate()
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    def summary_text(self) -> str:
        """Compact human-readable summary for Claude's analysis context."""
        completeness = self.completeness_check()
        done = sum(1 for v in completeness.values() if v)
        total = len(completeness)

        lines = [
            f"=== Business Research: {self.ticker} ({self.company_name}) ===",
            f"Research completeness: {done}/{total} dimensions | "
            f"Evidence items: {len(self.evidence_registry)} "
            f"(Tier 1: {self.tier1_evidence_count()}, "
            f"Contra: {self.negative_evidence_count()})",
            f"Overall confidence: {self.overall_research_confidence.value}",
            "",
        ]

        if self.business_understanding:
            bu = self.business_understanding
            lines += [
                "BUSINESS UNDERSTANDING",
                f"  Understandability: {bu.understandability_rating.value}",
                f"  What it does: {bu.what_it_does[:120]}{'...' if len(bu.what_it_does) > 120 else ''}",
                f"  Revenue sources: {', '.join(bu.revenue_sources[:4])}",
            ]

        if self.industry_assessment:
            ia = self.industry_assessment
            lines += [
                "",
                "INDUSTRY",
                f"  Classification: {ia.classification.value} | Confidence: {ia.confidence.value}",
                f"  {ia.classification_reasoning[:120]}{'...' if len(ia.classification_reasoning) > 120 else ''}",
            ]

        if self.moat_assessment:
            ma = self.moat_assessment
            active = ", ".join(ma.active_sources) if ma.active_sources else "None identified"
            lines += [
                "",
                "COMPETITIVE ADVANTAGE",
                f"  Overall moat: {ma.overall_strength.value} | Durability: {ma.overall_durability.value} | Trajectory: {ma.trajectory.value}",
                f"  Active sources: {active}",
                f"  {ma.moat_summary[:120]}{'...' if len(ma.moat_summary) > 120 else ''}",
            ]

        if self.management_assessment:
            mgmt = self.management_assessment
            lines += [
                "",
                "MANAGEMENT",
                f"  Rating: {mgmt.overall_rating.value} | Confidence: {mgmt.confidence.value}",
            ]

        if self.risk_assessment:
            ra = self.risk_assessment
            high_risks = ra.high_severity_risks()
            structural = ra.structural_risks()
            lines += [
                "",
                "RISKS",
                f"  Overall: {ra.overall_level.value} | High-severity: {len(high_risks)} | Structural: {len(structural)}",
            ]
            for r in high_risks[:3]:
                lines.append(f"  ⚠ {r.description[:100]}")

        if self.bull_bear:
            bb = self.bull_bear
            lines += [
                "",
                "BULL / BEAR",
                f"  Bull: {bb.bull_case_title}",
                f"  Bear: {bb.bear_case_title}",
                f"  Thesis breakers: {len(bb.thesis_breakers)}",
                f"  Contra evidence: {len(bb.negative_evidence_found)} items",
            ]

        if self.research_gaps:
            lines += ["", "RESEARCH GAPS:"] + [f"  • {g}" for g in self.research_gaps[:5]]
        if self.research_flags:
            lines += ["", "FLAGS FOR INVESTIGATION:"] + [f"  → {f}" for f in self.research_flags[:5]]
        if self.key_investment_questions:
            lines += ["", "KEY QUESTIONS FOR PHASE 7:"] + [f"  ? {q}" for q in self.key_investment_questions[:5]]

        return "\n".join(lines)


if __name__ == "__main__":
    # Smoke test of models
    print("Testing research_models.py...")

    e = EvidenceItem(
        fact="ATD generated $3.8B in free cash flow in FY2024",
        source="Alimentation Couche-Tard FY2024 Annual Report",
        source_tier=SourceTier.TIER_1_PRIMARY,
        source_date="2024-04-30",
        interpretation="Consistently strong FCF generation over multiple years supports high-quality earnings",
        research_level=ResearchLevel.L2_INTERPRETATION,
        confidence=Confidence.HIGH,
        supports_thesis=True
    )
    print(f"  EvidenceItem: {e.summary()[:80]}...")

    moat = MoatSourceAnalysis(
        moat_type="switching_costs",
        claim="ATD's fuel supply agreements and private-label products create moderate switching costs for fleet customers",
        evidence=[e],
        durability=MoatDurability.MEDIUM,
        durability_reasoning="Fleet agreements typically 2-3 year terms; private label loyalty varies",
        threats=["Consumer fuel substitution (EVs)", "Competing private label programs"],
        status=MoatStatus.CURRENT,
        strength=MoatStrength.MODERATE,
        conclusion="Moderate switching costs exist for commercial fleet customers; limited for retail consumers",
        confidence=Confidence.MEDIUM
    )
    issues = moat.validate()
    print(f"  MoatSourceAnalysis valid: {len(issues) == 0}")

    # Test brand-without-evidence validation
    bad_brand = MoatSourceAnalysis(
        moat_type="brand",
        claim="Strong brand",
        evidence=[],
        status=MoatStatus.CURRENT,
        strength=MoatStrength.STRONG,
        conclusion="Brand is a moat",
        confidence=Confidence.HIGH
    )
    issues = bad_brand.validate()
    print(f"  Brand-without-evidence caught: {len(issues) > 0} ({issues})")

    # Full assessment
    assessment = BusinessResearchAssessment(
        ticker="ATD.TO",
        company_name="Alimentation Couche-Tard",
        assessment_date="2024-12-31"
    )
    assessment.register_evidence(e)
    print(f"  Evidence registered: {len(assessment.evidence_registry)}")
    print(f"  Tier 1 evidence: {assessment.tier1_evidence_count()}")
    print(f"  Incomplete dimensions: {assessment.incomplete_dimensions()}")
    print("research_models.py: OK")
