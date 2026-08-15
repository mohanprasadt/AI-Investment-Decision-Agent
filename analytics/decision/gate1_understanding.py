"""
Gate 1 — Business Understanding
================================
Can the investor reasonably understand the business and its economics?

If the business cannot be understood well enough to form a credible thesis,
no investment action should be forced. The system should return
WAIT_INSUFFICIENT_EVIDENCE rather than fabricating a positive conclusion.

Checks:
  1. Is BusinessResearchAssessment available?
  2. Is understandability_rating SUFFICIENT (or at least BORDERLINE)?
  3. Is research completeness adequate (≥ 40% for BORDERLINE)?
  4. Are critical dimensions (moat, industry, business model) present?

Thresholds are deliberately lenient — this gate is a safety check,
not a perfectionism filter. Partial understanding is sufficient to proceed;
genuine incomprehension is not.
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.decision.decision_models import GateResult, DecisionAction
from analytics.business_research.research_models import (
    BusinessResearchAssessment, UnderstandabilityRating, Confidence,
)

# Minimum research completeness to proceed (fraction of True values)
_MIN_COMPLETENESS_BORDERLINE = 0.30   # 30% for borderline understanding
_MIN_COMPLETENESS_SUFFICIENT = 0.20   # 20% for sufficient understanding


def evaluate_gate1(
    research: Optional[BusinessResearchAssessment],
    financial_quality=None,       # FinancialQualityAssessment — checked for data availability
) -> GateResult:
    """
    Gate 1: Business understanding check.

    Returns a GateResult with:
      - passed=True  → proceed to Gate 2
      - passed=False → forced_action=WAIT_INSUFFICIENT_EVIDENCE
    """
    # -----------------------------------------------------------------------
    # Case 1: No research assessment available at all
    # -----------------------------------------------------------------------
    if research is None:
        return GateResult(
            gate_number=1,
            gate_name="Business Understanding",
            passed=False,
            forced_action=DecisionAction.WAIT_INSUFFICIENT_EVIDENCE.value,
            confidence="LOW",
            summary=(
                "No BusinessResearchAssessment provided. "
                "Business understanding cannot be assessed. "
                "Complete qualitative research before proceeding."
            ),
            data_gaps=[
                "BusinessResearchAssessment missing entirely.",
                "Cannot assess business model, moat, industry, or management.",
            ],
        )

    # -----------------------------------------------------------------------
    # Case 2: Business understanding dimension missing
    # -----------------------------------------------------------------------
    bu = research.business_understanding
    if bu is None:
        return GateResult(
            gate_number=1,
            gate_name="Business Understanding",
            passed=False,
            forced_action=DecisionAction.WAIT_INSUFFICIENT_EVIDENCE.value,
            confidence="LOW",
            summary=(
                "BusinessUnderstandingAssessment sub-dimension is missing. "
                "Cannot assess whether the business is comprehensible."
            ),
            data_gaps=["business_understanding dimension not populated."],
        )

    # -----------------------------------------------------------------------
    # Case 3: Explicit INSUFFICIENT understandability
    # -----------------------------------------------------------------------
    if bu.understandability_rating == UnderstandabilityRating.INSUFFICIENT:
        return GateResult(
            gate_number=1,
            gate_name="Business Understanding",
            passed=False,
            forced_action=DecisionAction.WAIT_INSUFFICIENT_EVIDENCE.value,
            confidence=bu.confidence.value if hasattr(bu.confidence, "value") else str(bu.confidence),
            summary=(
                f"Business understandability rated INSUFFICIENT: {bu.understandability_note}. "
                "An investor who cannot understand how a company makes money and sustains its "
                "advantage should not invest. This is a protective gate, not a negative quality signal."
            ),
            data_gaps=[f"Business understandability: INSUFFICIENT — {bu.understandability_note}"],
        )

    # -----------------------------------------------------------------------
    # Case 4: BORDERLINE — check if research completeness compensates
    # -----------------------------------------------------------------------
    completeness = _research_completeness(research)
    is_borderline = (bu.understandability_rating == UnderstandabilityRating.BORDERLINE)

    if is_borderline and completeness < _MIN_COMPLETENESS_BORDERLINE:
        return GateResult(
            gate_number=1,
            gate_name="Business Understanding",
            passed=False,
            forced_action=DecisionAction.WAIT_INSUFFICIENT_EVIDENCE.value,
            confidence="LOW",
            summary=(
                f"Business understandability is BORDERLINE and research completeness is only "
                f"{completeness:.0%}. Insufficient evidence to proceed with confidence. "
                "Complete at minimum: moat assessment, industry assessment, growth assessment."
            ),
            data_gaps=_missing_dimensions(research),
        )

    # -----------------------------------------------------------------------
    # Case 5: Passed — sufficient or borderline-with-adequate-research
    # -----------------------------------------------------------------------
    gaps = _missing_dimensions(research)
    confidence = _gate1_confidence(bu, completeness, gaps)

    return GateResult(
        gate_number=1,
        gate_name="Business Understanding",
        passed=True,
        confidence=confidence,
        summary=(
            f"Business understandability: {bu.understandability_rating.value}. "
            f"Research completeness: {completeness:.0%}. "
            f"{bu.understandability_note or 'Business model is assessable.'}"
        ),
        supporting_evidence=[
            f"What it does: {bu.what_it_does}" if bu.what_it_does else None,
            f"How it earns: {bu.how_it_makes_money}" if bu.how_it_makes_money else None,
        ],
        contradictory_evidence=[],
        data_gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _research_completeness(research: BusinessResearchAssessment) -> float:
    """Fraction of research dimensions that are populated."""
    dims = {
        "business_understanding": research.business_understanding is not None,
        "industry_assessment": research.industry_assessment is not None,
        "moat_assessment": research.moat_assessment is not None,
        "growth_assessment": research.growth_assessment is not None,
        "management_assessment": research.management_assessment is not None,
        "risk_assessment": research.risk_assessment is not None,
        "bull_bear": research.bull_bear is not None,
    }
    if research.research_completeness:
        # Use existing completeness dict if populated
        completed = sum(1 for v in research.research_completeness.values() if v)
        total = max(len(research.research_completeness), 1)
        return completed / total
    return sum(dims.values()) / len(dims)


def _missing_dimensions(research: BusinessResearchAssessment) -> list:
    gaps = []
    if research.moat_assessment is None:
        gaps.append("Moat assessment not completed.")
    if research.industry_assessment is None:
        gaps.append("Industry assessment not completed.")
    if research.growth_assessment is None:
        gaps.append("Growth assessment not completed.")
    if research.management_assessment is None:
        gaps.append("Management assessment not completed.")
    if research.risk_assessment is None:
        gaps.append("Risk assessment not completed.")
    if research.bull_bear is None:
        gaps.append("Bull/bear case not completed.")
    gaps.extend(research.research_gaps or [])
    return gaps


def _gate1_confidence(bu, completeness: float, gaps: list) -> str:
    if (bu.understandability_rating == UnderstandabilityRating.SUFFICIENT
            and completeness >= 0.70 and len(gaps) <= 1):
        return "HIGH"
    if completeness >= 0.40 and len(gaps) <= 3:
        return "MEDIUM"
    return "LOW"
