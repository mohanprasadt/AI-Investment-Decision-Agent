"""
Gate 2 — Business & Financial Quality
========================================
Assesses the combined quality signal from:
  - FinancialQualityAssessment  (Phase 3)
  - BusinessResearchAssessment  (Phase 4)

Output: QualityTier (EXCELLENT / STRONG / GOOD / WATCH / CONCERN)

Philosophy alignment (investor preferences):
  - ROIC consistently > 10% (ideally > 15%)
  - Debt-to-assets is an important balance-sheet indicator (preference: low)
  - Dividend payout ratio generally < 70%
  - Dividend yield generally ≤ 6% (high yield requires investigation)
  - Preference for competitive advantage / moat
  - Consistent rather than erratic revenue growth
  - Emerging companies may qualify with credible moat / economic advantage

Note: this gate does NOT produce investment actions — it produces a
quality tier that feeds the synthesizer. A CONCERN tier does not
automatically mean EXIT; it means the quality bar is not met for a
positive action.
"""

import sys
from pathlib import Path
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.decision.decision_models import (
    GateResult, QualityTier, DecisionEvidenceItem, EvidenceStrength,
)
from analytics.business_research.research_models import (
    BusinessResearchAssessment, MoatStrength, ManagementRating,
    IndustryClassification, Confidence,
)


# ---------------------------------------------------------------------------
# Philosophy thresholds
# ---------------------------------------------------------------------------

_ROIC_STRONG_THRESHOLD  = 15.0   # %
_ROIC_GOOD_THRESHOLD    = 10.0   # %
_ROIC_WATCH_THRESHOLD   = 7.0    # %

_DEBT_TO_ASSETS_GOOD    = 30.0   # % — preference for low debt
_DEBT_TO_ASSETS_WATCH   = 50.0   # %
_DEBT_TO_ASSETS_CONCERN = 65.0   # %  (financial institutions exempt)

_PAYOUT_RATIO_MAX       = 70.0   # % — preference
_DIV_YIELD_HIGH         = 6.0    # % — above this requires investigation
_DIV_YIELD_VERY_HIGH    = 8.0    # % — high concern


def evaluate_gate2(
    financial_quality=None,   # FinancialQualityAssessment
    research: Optional[BusinessResearchAssessment] = None,
) -> GateResult:
    """
    Gate 2: Business and financial quality assessment.

    Returns a GateResult with quality_tier set.
    This gate does not force early termination (even CONCERN passes Gate 2).
    The synthesizer uses the quality_tier to select the appropriate action.
    """
    supporting: List[str] = []
    contradictory: List[str] = []
    gaps: List[str] = []
    philosophy_notes: List[str] = []

    quality_scores: List[int] = []   # 0=Concern, 1=Watch, 2=Good, 3=Strong, 4=Excellent

    # -----------------------------------------------------------------------
    # Financial quality dimensions
    # -----------------------------------------------------------------------
    if financial_quality is None:
        gaps.append("FinancialQualityAssessment not provided — financial quality cannot be assessed.")
    else:
        is_financial = getattr(financial_quality, "is_financial_institution", False)
        is_emerging  = getattr(financial_quality, "is_emerging_company", False)

        # ROIC
        roic_dim = getattr(financial_quality, "roic", None)
        if roic_dim and roic_dim.data_available:
            cl = roic_dim.classification
            score, note = _classify_roic(cl, is_financial)
            quality_scores.append(score)
            if score >= 3:
                supporting.append(f"ROIC: {cl} — consistent returns above cost of capital.")
                philosophy_notes.append(f"ROIC classification '{cl}' meets/exceeds the >10% philosophy preference.")
            elif score <= 1:
                contradictory.append(f"ROIC: {cl} — below philosophy preference of >10%.")
            else:
                supporting.append(f"ROIC: {cl}.")
        else:
            gaps.append("ROIC data not available.")

        # Revenue growth
        rev_dim = getattr(financial_quality, "revenue_growth", None)
        if rev_dim and rev_dim.data_available:
            cl = rev_dim.classification
            score = _dim_score(cl)
            quality_scores.append(score)
            if "Concern" in cl or "High Concern" in cl:
                contradictory.append(f"Revenue growth: {cl} — inconsistency concerns philosophy preference for stable growth.")
            else:
                supporting.append(f"Revenue growth: {cl}.")
        else:
            gaps.append("Revenue growth data not available.")

        # Margins
        margin_dim = getattr(financial_quality, "margins", None)
        if margin_dim and margin_dim.data_available:
            cl = margin_dim.classification
            score = _dim_score(cl)
            quality_scores.append(score)
            if score is not None:
                if score >= 2:
                    supporting.append(f"Margins: {cl}.")
                else:
                    contradictory.append(f"Margins: {cl}.")

        # FCF
        fcf_dim = getattr(financial_quality, "free_cash_flow", None)
        if fcf_dim and fcf_dim.data_available:
            cl = fcf_dim.classification
            score = _dim_score(cl)
            quality_scores.append(score)
            if score is not None:
                if score >= 3:
                    supporting.append(f"Free cash flow: {cl} — strong FCF generation supports long-term value.")
                elif score <= 1:
                    contradictory.append(f"Free cash flow: {cl} — FCF quality concern.")
                else:
                    supporting.append(f"Free cash flow: {cl}.")

        # Balance sheet / debt
        bs_dim = getattr(financial_quality, "balance_sheet", None)
        if bs_dim and bs_dim.data_available:
            cl = bs_dim.classification
            score = _dim_score(cl)
            quality_scores.append(score)
            if score is not None:
                if score >= 3:
                    supporting.append(f"Balance sheet: {cl} — low debt aligns with philosophy preference.")
                    philosophy_notes.append("Low/moderate debt aligns with investor preference.")
                elif score <= 1:
                    contradictory.append(f"Balance sheet: {cl} — elevated debt. "
                                         f"{'Financial institution context applies.' if is_financial else ''}")

        # Dividend
        div_dim = getattr(financial_quality, "dividend", None)
        if div_dim and div_dim.data_available:
            cl = div_dim.classification
            score = _dim_score(cl)
            quality_scores.append(score)
            _assess_dividend_philosophy(div_dim, supporting, contradictory, philosophy_notes)

        # Strengths / concerns from quality engine
        for s in (financial_quality.strengths or []):
            supporting.append(f"Financial strength: {s}")
        for c in (financial_quality.concerns or []):
            contradictory.append(f"Financial concern: {c}")

        # Emerging company context
        if is_emerging:
            philosophy_notes.append(
                "Emerging company: financial thresholds applied leniently — "
                "credible moat / economic advantage may compensate."
            )

    # -----------------------------------------------------------------------
    # Business / qualitative quality
    # -----------------------------------------------------------------------
    if research is not None:
        _assess_moat(research, quality_scores, supporting, contradictory, philosophy_notes)
        _assess_industry(research, quality_scores, supporting, contradictory)
        _assess_management(research, quality_scores, supporting, contradictory)
        _assess_growth_quality(research, supporting, contradictory)
        _assess_risk_level(research, contradictory)

        for flag in (research.research_flags or []):
            contradictory.append(f"Research flag: {flag}")
        for gap in (research.research_gaps or []):
            gaps.append(f"Research gap: {gap}")

    # -----------------------------------------------------------------------
    # Determine quality tier
    # -----------------------------------------------------------------------
    tier = _compute_tier(quality_scores, contradictory)

    confidence = _gate2_confidence(quality_scores, gaps, financial_quality, research)

    return GateResult(
        gate_number=2,
        gate_name="Business & Financial Quality",
        passed=True,  # Gate 2 always passes — tier feeds synthesizer
        quality_tier=tier.value,
        confidence=confidence,
        summary=_quality_summary(tier, quality_scores, supporting, contradictory),
        supporting_evidence=supporting,
        contradictory_evidence=contradictory,
        data_gaps=gaps,
        philosophy_notes=philosophy_notes,
    )


# ---------------------------------------------------------------------------
# Moat assessment
# ---------------------------------------------------------------------------

def _assess_moat(
    research: BusinessResearchAssessment,
    scores: list, supporting: list, contradictory: list, philosophy: list,
) -> None:
    moat = research.moat_assessment
    if moat is None:
        return
    strength = moat.overall_strength
    if strength in (MoatStrength.STRONG, MoatStrength.EXCEPTIONAL):
        scores.append(4)   # Excellent
        supporting.append(
            f"Moat: {strength.value} — active sources: {', '.join(moat.active_sources or ['N/A'])}. "
            f"Aligns with philosophy preference for competitive advantage."
        )
        philosophy.append(f"Strong moat ({strength.value}) is central to philosophy preference.")
    elif strength == MoatStrength.MODERATE:
        scores.append(3)   # Strong
        supporting.append(f"Moat: {strength.value} — {moat.moat_summary[:100] if moat.moat_summary else ''}.")
    elif strength == MoatStrength.WEAK:
        scores.append(2)   # Good (weak moat is OK, not ideal)
        contradictory.append(f"Moat: WEAK — competitive advantage limited; watch for erosion.")
        philosophy.append("Weak moat is below philosophy preference; additional quality evidence needed.")
    else:
        scores.append(1)   # Watch
        contradictory.append("Moat: NONE identified — no demonstrable competitive advantage.")
        philosophy.append("No moat identified — investor preference is for competitive advantage.")

    # Moat trajectory
    trajectory = getattr(moat, "trajectory", None)
    if trajectory and hasattr(trajectory, "value"):
        if trajectory.value == "Weakening":
            contradictory.append(f"Moat trajectory: WEAKENING — erosion risk.")


def _assess_industry(
    research: BusinessResearchAssessment,
    scores: list, supporting: list, contradictory: list,
) -> None:
    ind = research.industry_assessment
    if ind is None:
        return
    if ind.classification == IndustryClassification.ATTRACTIVE:
        scores.append(3)
        supporting.append(f"Industry: {ind.industry_name} — classified Attractive. {ind.classification_reasoning[:80] if ind.classification_reasoning else ''}")
    elif ind.classification == IndustryClassification.NEUTRAL:
        scores.append(2)
        supporting.append(f"Industry: {ind.industry_name} — Neutral. Adequate but not tailwind.")
    else:
        scores.append(1)
        contradictory.append(
            f"Industry: {ind.industry_name} — Challenging. "
            f"{ind.challenging_industry_exception_note or 'Company must have exceptional moat to compensate.'}"
        )


def _assess_management(
    research: BusinessResearchAssessment,
    scores: list, supporting: list, contradictory: list,
) -> None:
    mgmt = research.management_assessment
    if mgmt is None:
        return
    rating = mgmt.overall_rating
    if rating in (ManagementRating.STRONG,):
        scores.append(3)
        supporting.append(f"Management: {rating.value}. {mgmt.capital_allocation[:80] if mgmt.capital_allocation else ''}")
    elif rating == ManagementRating.GOOD:
        scores.append(2)
        supporting.append(f"Management: {rating.value}.")
    elif rating == ManagementRating.MIXED:
        scores.append(2)
        contradictory.append(f"Management: {rating.value} — mixed execution history.")
    elif rating == ManagementRating.WEAK:
        scores.append(1)
        contradictory.append(f"Management: {rating.value} — material management concern.")
    # INSUFFICIENT_DATA — no score added (avoid penalising missing data)


def _assess_growth_quality(
    research: BusinessResearchAssessment,
    supporting: list, contradictory: list,
) -> None:
    growth = research.growth_assessment
    if growth is None:
        return
    if growth.growth_sustainability_assessment:
        note = growth.growth_sustainability_assessment
        if any(w in note.lower() for w in ["strong", "sustained", "durable", "organic"]):
            supporting.append(f"Growth quality: {note[:100]}")
        elif any(w in note.lower() for w in ["risk", "uncertain", "declining", "limited"]):
            contradictory.append(f"Growth quality concern: {note[:100]}")


def _assess_risk_level(
    research: BusinessResearchAssessment,
    contradictory: list,
) -> None:
    risk = research.risk_assessment
    if risk is None:
        return
    from analytics.business_research.research_models import RiskLevel
    if risk.overall_level == RiskLevel.HIGH:
        contradictory.append(
            f"Overall risk level: HIGH — {risk.risk_summary[:100] if risk.risk_summary else 'Elevated risk profile.'}"
        )
    high_structural = risk.structural_risks()
    for r in high_structural[:2]:   # flag top 2 structural risks
        if r.severity == "High":
            contradictory.append(f"Structural risk: {r.description[:100]}")


# ---------------------------------------------------------------------------
# Dividend philosophy checks
# ---------------------------------------------------------------------------

def _assess_dividend_philosophy(
    div_dim, supporting: list, contradictory: list, philosophy: list,
) -> None:
    cl = div_dim.classification
    score = _dim_score(cl)
    if score is None:
        # "N/A" or "Not Applicable" — company does not pay a dividend; skip philosophy check
        return
    if score >= 3:
        supporting.append(f"Dividend: {cl} — sustainable payout supports philosophy preference.")
    elif score <= 1:
        contradictory.append(f"Dividend: {cl} — sustainability concern.")

    # High yield investigation note
    note = getattr(div_dim, "flags", [])
    for flag in (note or []):
        if "yield" in flag.lower() and any(w in flag.lower() for w in ["high", "above"]):
            philosophy.append(
                f"High dividend yield flag: {flag} — "
                "investor philosophy requires investigation for yields above 6%."
            )


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

_DIM_SCORE_MAP = {
    "Excellent": 4, "Strong": 3, "Good": 2, "Watch": 1,
    "Concern": 0, "High Concern": 0, "N/A": None, "Insufficient Data": None,
    "Industry-Specific": None, "Not Applicable": None,
}


def _dim_score(classification: str) -> int:
    return _DIM_SCORE_MAP.get(classification, 2)  # Default to "Good"


def _classify_roic(classification: str, is_financial: bool) -> tuple:
    score = _dim_score(classification)
    if is_financial:
        return max(score, 2), "Financial institution — ROIC thresholds adjusted."
    return score, ""


def _compute_tier(scores: list, contradictory: list) -> QualityTier:
    # Filter out None values (from N/A dimensions like missing dividend)
    scores = [s for s in scores if s is not None]
    if not scores:
        return QualityTier.WATCH
    avg = sum(scores) / len(scores)
    # Penalise for many contradictions
    penalty = 0.15 * max(0, len(contradictory) - 3)
    effective = max(0, avg - penalty)

    if effective >= 3.5:
        return QualityTier.EXCELLENT
    elif effective >= 2.8:
        return QualityTier.STRONG
    elif effective >= 2.0:
        return QualityTier.GOOD
    elif effective >= 1.2:
        return QualityTier.WATCH
    else:
        return QualityTier.CONCERN


def _gate2_confidence(scores, gaps, financial_quality, research) -> str:
    n_gaps = len(gaps)
    n_scores = len(scores)
    has_fq  = financial_quality is not None
    has_res = research is not None and research.business_understanding is not None

    if has_fq and has_res and n_gaps <= 2 and n_scores >= 5:
        return "HIGH"
    if (has_fq or has_res) and n_gaps <= 4:
        return "MEDIUM"
    return "LOW"


def _quality_summary(
    tier: QualityTier, scores: list,
    supporting: list, contradictory: list,
) -> str:
    valid = [s for s in scores if s is not None]
    avg = sum(valid) / max(len(valid), 1)
    return (
        f"Quality tier: {tier.value} "
        f"(avg dimension score: {avg:.1f}/4.0, "
        f"{len(supporting)} supporting signals, "
        f"{len(contradictory)} contradictions)."
    )
