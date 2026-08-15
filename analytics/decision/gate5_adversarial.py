"""
Gate 5 — Adversarial Challenge
================================
Before producing the final conclusion, Gate 5 explicitly challenges
the investment thesis by asking:

  "What evidence would make this investment thesis wrong?"

This gate synthesises bear cases, thesis breakers, and contradictory
evidence from all prior phases. Its purpose is to prevent the system
from producing overconfident positive conclusions when meaningful
downside risks exist.

Sources of adversarial evidence:
  1. BusinessResearchAssessment.bull_bear.bear_case_narrative
  2. BusinessResearchAssessment.bull_bear.thesis_breakers
  3. BusinessResearchAssessment.risk_assessment (structural high-severity)
  4. FinancialQualityAssessment.concerns + data_caveats
  5. ValuationAssessment.valuation_flags
  6. PortfolioPositionContext.portfolio_risks (ELEVATED/HIGH flags)
  7. Gate 2 contradictions (financial quality deterioration)

AdversarialRisk levels:
  LOW      → No material thesis breakers; bear case is manageable
  MODERATE → Some concerns; thesis could be tested; monitor indicators
  HIGH     → Significant risks; bear case credible; positive action should
              be sized cautiously; confidence downgraded
  SEVERE   → One or more thesis breakers are highly credible; existing
              holders should review; new positions should wait

Only SEVERE may override a positive action to WATCH for new positions
or REDUCE review for existing holders. This is not automatic — it is
flagged for the synthesizer to apply with judgment.
"""

import sys
from pathlib import Path
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.decision.decision_models import (
    GateResult, ThesisBreaker, AdversarialRisk,
)
from analytics.business_research.research_models import BusinessResearchAssessment
from analytics.portfolio.portfolio_models import PortfolioPositionContext


def evaluate_gate5(
    research: Optional[BusinessResearchAssessment] = None,
    financial_quality=None,
    valuation=None,
    portfolio_ctx: Optional[PortfolioPositionContext] = None,
    quality_gate_result: Optional[GateResult] = None,
) -> GateResult:
    """
    Gate 5: Adversarial challenge.

    Returns a GateResult with adversarial_risk set to LOW/MODERATE/HIGH/SEVERE.
    """
    bear_points:  List[str] = []
    breakers:     List[ThesisBreaker] = []
    gaps:         List[str] = []

    # -----------------------------------------------------------------------
    # Source 1: Business research bear case and thesis breakers
    # -----------------------------------------------------------------------
    if research and research.bull_bear:
        bb = research.bull_bear
        if bb.bear_case_narrative:
            bear_points.append(f"Bear case: {bb.bear_case_narrative[:200]}")
        for breaker_text in (bb.thesis_breakers or []):
            breakers.append(ThesisBreaker(
                condition=breaker_text,
                likelihood="MEDIUM",
                impact="SEVERE",
                monitoring_indicator="Monitor quarterly filings for signs of thesis deterioration.",
                trigger_action="Would prompt REDUCE or EXIT review.",
            ))
        for neg in (bb.negative_evidence_found or []):
            bear_points.append(f"Negative evidence: {neg.fact[:150]}")
        if bb.confirmation_bias_check:
            bear_points.append(f"Confirmation bias check: {bb.confirmation_bias_check[:150]}")

    # -----------------------------------------------------------------------
    # Source 2: Structural high-severity risks
    # -----------------------------------------------------------------------
    if research and research.risk_assessment:
        risk = research.risk_assessment
        for r in risk.high_severity_risks():
            from analytics.business_research.research_models import RiskType
            severity_note = " [STRUCTURAL]" if r.risk_type == RiskType.STRUCTURAL else ""
            bear_points.append(f"High-severity risk{severity_note}: {r.description[:150]}")
            if r.risk_type == RiskType.STRUCTURAL:
                breakers.append(ThesisBreaker(
                    condition=r.description[:200],
                    likelihood="MEDIUM",
                    impact="SEVERE",
                    monitoring_indicator=f"Watch for: {', '.join(r.mitigants[:2]) if r.mitigants else 'quarterly deterioration.'}",
                    trigger_action="Structural deterioration would prompt EXIT review.",
                ))

    # -----------------------------------------------------------------------
    # Source 3: Financial quality concerns
    # -----------------------------------------------------------------------
    if financial_quality:
        for concern in (financial_quality.concerns or []):
            bear_points.append(f"Financial concern: {concern[:120]}")
        for caveat in (financial_quality.data_caveats or []):
            gaps.append(f"Financial data caveat: {caveat[:100]}")

    # -----------------------------------------------------------------------
    # Source 4: Valuation risks
    # -----------------------------------------------------------------------
    if valuation:
        for flag in (valuation.valuation_flags or []):
            bear_points.append(f"Valuation risk: {flag[:120]}")
        # Wide fair value range = high uncertainty
        if valuation.fair_value_range:
            w = valuation.fair_value_range.width_pct()
            if w and w > 80:
                bear_points.append(
                    f"Very wide valuation range ({w:.0f}% of base) — "
                    "high intrinsic value uncertainty is a downside risk."
                )
                gaps.append(f"Valuation range width: {w:.0f}% — high uncertainty.")

    # -----------------------------------------------------------------------
    # Source 5: Portfolio concentration risks (ELEVATED/HIGH only)
    # -----------------------------------------------------------------------
    if portfolio_ctx:
        for risk_text in (portfolio_ctx.portfolio_risks or []):
            bear_points.append(f"Portfolio risk: {risk_text[:120]}")

    # -----------------------------------------------------------------------
    # Source 6: Gate 2 contradictions (financial quality deterioration)
    # -----------------------------------------------------------------------
    if quality_gate_result:
        for contra in (quality_gate_result.contradictory_evidence or []):
            if any(w in contra.lower() for w in
                   ["concern", "deteriorat", "weak", "high concern", "structural"]):
                bear_points.append(f"Quality concern: {contra[:120]}")

    # -----------------------------------------------------------------------
    # Determine adversarial risk level
    # -----------------------------------------------------------------------
    n_breakers = len(breakers)
    n_bear     = len(bear_points)

    # Assess severity: SEVERE if any breaker has HIGH likelihood
    # or many structural risks exist
    high_breakers = [b for b in breakers if b.likelihood == "HIGH"]

    if high_breakers or n_breakers >= 4:
        risk_level = AdversarialRisk.SEVERE
    elif n_breakers >= 2 or n_bear >= 6:
        risk_level = AdversarialRisk.HIGH
    elif n_breakers >= 1 or n_bear >= 3:
        risk_level = AdversarialRisk.MODERATE
    else:
        risk_level = AdversarialRisk.LOW

    # -----------------------------------------------------------------------
    # Bear case synthesis
    # -----------------------------------------------------------------------
    bear_summary = _synthesise_bear_case(
        research, financial_quality, valuation, bear_points, breakers,
    )

    # What would make the thesis wrong
    what_would_change = _what_would_change(research, breakers, bear_points)

    confidence = _gate5_confidence(n_bear, n_breakers, gaps)

    return GateResult(
        gate_number=5,
        gate_name="Adversarial Challenge",
        passed=True,
        adversarial_risk=risk_level.value,
        confidence=confidence,
        summary=(
            f"Adversarial risk: {risk_level.value}. "
            f"{n_breakers} thesis breaker(s) identified. "
            f"{n_bear} bear-case evidence point(s). "
            f"{bear_summary[:200]}"
        ),
        supporting_evidence=what_would_change,  # "what would change" — for audit trail
        contradictory_evidence=bear_points[:10],  # top 10 bear points
        data_gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Thesis breakers extraction (also called by synthesizer)
# ---------------------------------------------------------------------------

def extract_thesis_breakers(
    research: Optional[BusinessResearchAssessment],
    financial_quality=None,
    valuation=None,
) -> List[ThesisBreaker]:
    """Extract all thesis breakers. Called by the synthesizer for the final output."""
    breakers: List[ThesisBreaker] = []

    if research and research.bull_bear:
        for text in (research.bull_bear.thesis_breakers or []):
            breakers.append(ThesisBreaker(
                condition=text,
                likelihood="MEDIUM",
                impact="SEVERE",
                monitoring_indicator="Monitor quarterly filings and management commentary.",
                trigger_action="Would prompt REDUCE or EXIT review.",
            ))

    if research and research.risk_assessment:
        from analytics.business_research.research_models import RiskType
        for r in research.risk_assessment.structural_risks():
            if r.severity == "High":
                breakers.append(ThesisBreaker(
                    condition=r.description[:200],
                    likelihood="MEDIUM",
                    impact="FATAL",
                    monitoring_indicator=", ".join(r.mitigants[:2]) if r.mitigants else "",
                    trigger_action="Structural thesis break → EXIT review.",
                ))

    # Moat deterioration is always a thesis breaker if moat is central
    if research and research.moat_assessment:
        moat = research.moat_assessment
        if moat.overall_strength.value in ("Strong", "Exceptional"):
            breakers.append(ThesisBreaker(
                condition="Moat erosion: sustained market share loss, pricing power decline, "
                          "or competitor breakthrough that undermines the identified moat sources.",
                likelihood="LOW",
                impact="FATAL",
                monitoring_indicator="Watch ROIC trend, market share data, and pricing realisation.",
                trigger_action="Moat deterioration → EXIT review.",
            ))

    # Valuation model assumption break
    if valuation and valuation.key_valuation_assumptions:
        breakers.append(ThesisBreaker(
            condition="Key valuation assumptions fail: "
                      + "; ".join(valuation.key_valuation_assumptions[:2]),
            likelihood="LOW",
            impact="SEVERE",
            monitoring_indicator="Track actuals vs assumptions in quarterly results.",
            trigger_action="Material assumption miss → reassess fair value; consider REDUCE.",
        ))

    return breakers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synthesise_bear_case(
    research, financial_quality, valuation, bear_points, breakers,
) -> str:
    parts = []
    if research and research.bull_bear and research.bull_bear.bear_case_narrative:
        parts.append(research.bull_bear.bear_case_narrative[:300])
    elif bear_points:
        parts.append("Bear case synthesised from: " + "; ".join(bear_points[:3]))
    if breakers:
        parts.append(f"Thesis breakers: {'; '.join(b.condition[:80] for b in breakers[:2])}.")
    return " ".join(parts) if parts else "No material bear case evidence identified."


def _what_would_change(research, breakers, bear_points) -> List[str]:
    items = []
    for b in breakers:
        items.append(f"If {b.condition[:100]} → {b.trigger_action}")
    if research and research.key_investment_questions:
        for q in research.key_investment_questions[:3]:
            items.append(f"Key question: {q}")
    if not items and bear_points:
        items.append(
            "Resolution of bear case concerns would trigger re-assessment of the action."
        )
    return items


def _gate5_confidence(n_bear: int, n_breakers: int, gaps: list) -> str:
    if n_bear == 0 and n_breakers == 0:
        return "LOW"  # No adversarial evidence is suspicious — likely not searched
    if n_bear >= 2 and len(gaps) <= 2:
        return "HIGH"
    return "MEDIUM"
