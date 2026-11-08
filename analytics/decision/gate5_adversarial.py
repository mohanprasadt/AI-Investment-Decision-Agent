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

import re
import sys
from pathlib import Path
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.decision.decision_models import (
    GateResult, ThesisBreaker, AdversarialRisk,
)
from analytics.business_research.research_models import BusinessResearchAssessment
from analytics.portfolio.portfolio_models import PortfolioPositionContext


# ---------------------------------------------------------------------------
# Shared deterministic severity function
# ---------------------------------------------------------------------------
# Single source of truth for Gate 5 adversarial risk.  Called by both
# evaluate_gate5() (inline) and scenario_engine.run_scenario() (via import).
# Callers MUST pre-filter breakers to exclude is_monitoring_only=True items
# before calling this function.
# ---------------------------------------------------------------------------

def calculate_adversarial_severity(breakers: list, n_bear: int = 0) -> str:
    """
    Deterministic Gate 5 severity calculation.

    Parameters
    ----------
    breakers : list of ThesisBreaker
        Pre-filtered to exclude is_monitoring_only=True items.
    n_bear   : int
        Count of bear-case evidence points from Gate 5 bear_points list.
        Not applicable in scenario context (use 0 for scenario-only calls).

    Returns
    -------
    'LOW' | 'MODERATE' | 'HIGH' | 'SEVERE'
    """
    n_high    = sum(1 for b in breakers if getattr(b, "likelihood", "") == "HIGH")
    n_medium  = sum(1 for b in breakers if getattr(b, "likelihood", "") in ("MEDIUM", "HIGH"))
    n_unknown = sum(1 for b in breakers if getattr(b, "likelihood", "") == "UNKNOWN")
    n_medium_equiv = n_medium + n_unknown

    if n_high >= 1:
        return "SEVERE"
    if n_medium_equiv >= 4:
        return "SEVERE"
    if n_medium_equiv >= 2 or n_bear >= 6:
        return "HIGH"
    if n_medium_equiv >= 1 or n_bear >= 3:
        return "MODERATE"
    return "LOW"


# ---------------------------------------------------------------------------
# Annotation-stripping helper
# ---------------------------------------------------------------------------

_ANNOTATION_PREFIX_RE = re.compile(r'^\[DATA-BOUNDARY-VIOLATION:[^\]]*\]\s*')


def _strip_boundary_annotation(text: str) -> str:
    """
    Remove a leading [DATA-BOUNDARY-VIOLATION:...] annotation from a string.
    Returns the original text unchanged when no annotation is present.
    The annotation is preserved in BullBearAssessment for audit; this helper
    ensures the annotation does not enter operational Gate 5 bear_points as
    metadata noise.
    """
    return _ANNOTATION_PREFIX_RE.sub("", text)


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
    # Phase 11B: use thesis_breaker_details (structured, evidence-backed) when
    # available; fall back to thesis_breakers (plain strings → MEDIUM) otherwise.
    # -----------------------------------------------------------------------
    if research and research.bull_bear:
        bb = research.bull_bear
        if bb.bear_case_narrative:
            # K1 fix: strip [DATA-BOUNDARY-VIOLATION:...] annotation prefix before adding
            # to bear_points.  The annotation is preserved in bb.bear_case_narrative for
            # audit; stripping it here prevents annotation metadata from entering n_bear.
            _bear_narrative = _strip_boundary_annotation(bb.bear_case_narrative)
            bear_points.append(f"Bear case: {_bear_narrative[:200]}")

        if bb.thesis_breaker_details:
            # New structured path — likelihoods are evidence-backed (LOW/MEDIUM/HIGH/UNKNOWN)
            _valid = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
            for detail in bb.thesis_breaker_details:
                lk = str(detail.get("likelihood", "UNKNOWN")).upper()
                if lk not in _valid:
                    lk = "UNKNOWN"
                breakers.append(ThesisBreaker(
                    condition=detail.get("condition", ""),
                    likelihood=lk,
                    impact="SEVERE",
                    monitoring_indicator="Monitor quarterly filings for signs of thesis deterioration.",
                    trigger_action="Would prompt REDUCE or EXIT review.",
                    evidence=detail.get("evidence", []),
                    likelihood_rationale=detail.get("likelihood_rationale", ""),
                    # K1: preserve unsupported evidence for audit trail
                    unsupported_evidence=list(detail.get("unsupported_evidence", [])),
                ))
        else:
            # Legacy / quantitative fallback — no evidence available; use MEDIUM
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
                # Structural risks from risk_assessment always use MEDIUM
                # (no per-breaker evidence available from this source)
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
    # Determine adversarial risk level — K1: delegate to shared function
    # -----------------------------------------------------------------------
    n_bear = len(bear_points)

    # Note: `breakers` here are built from thesis_breaker_details and structural
    # risks — none carry is_monitoring_only=True (those are added only by
    # extract_thesis_breakers(), which is NOT called in evaluate_gate5()).
    # The shared function therefore receives a pre-filtered list by construction.
    risk_str   = calculate_adversarial_severity(breakers, n_bear)
    risk_level = AdversarialRisk(risk_str)

    # Recompute counts for display-only breakdown (not for severity).
    n_high    = sum(1 for b in breakers if b.likelihood == "HIGH")
    n_unknown = sum(1 for b in breakers if b.likelihood == "UNKNOWN")
    n_low     = sum(1 for b in breakers if b.likelihood == "LOW")

    # -----------------------------------------------------------------------
    # Bear case synthesis
    # -----------------------------------------------------------------------
    bear_summary = _synthesise_bear_case(
        research, financial_quality, valuation, bear_points, breakers,
    )

    # What would make the thesis wrong
    what_would_change = _what_would_change(research, breakers, bear_points)

    n_breakers = len(breakers)  # total breaker count (used by _gate5_confidence)
    confidence = _gate5_confidence(n_bear, n_breakers, gaps)

    # Breakdown for display only (not used in severity)
    _n_med_only = sum(1 for b in breakers if b.likelihood == "MEDIUM")
    lk_breakdown = (
        f"Breakers: {n_high} HIGH / {_n_med_only} MEDIUM / {n_unknown} UNKNOWN / {n_low} LOW."
    )
    return GateResult(
        gate_number=5,
        gate_name="Adversarial Challenge",
        passed=True,
        adversarial_risk=risk_level.value,
        # K1 follow-up: expose structured n_bear so scenario_engine never parses text.
        n_bear=n_bear,
        confidence=confidence,
        summary=(
            f"Adversarial risk: {risk_level.value}. "
            f"{lk_breakdown} "
            f"{n_bear} bear-case evidence point(s). "
            f"{bear_summary[:150]}"
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
        bb = research.bull_bear
        if bb.thesis_breaker_details:
            # Phase 11B: use evidence-backed structured details
            _valid = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
            for detail in bb.thesis_breaker_details:
                lk = str(detail.get("likelihood", "UNKNOWN")).upper()
                if lk not in _valid:
                    lk = "UNKNOWN"
                breakers.append(ThesisBreaker(
                    condition=detail.get("condition", ""),
                    likelihood=lk,
                    impact="SEVERE",
                    monitoring_indicator="Monitor quarterly filings and management commentary.",
                    trigger_action="Would prompt REDUCE or EXIT review.",
                    evidence=detail.get("evidence", []),
                    likelihood_rationale=detail.get("likelihood_rationale", ""),
                    # K1: preserve unsupported evidence for audit trail
                    unsupported_evidence=list(detail.get("unsupported_evidence", [])),
                ))
        else:
            for text in (bb.thesis_breakers or []):
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

    # Moat deterioration is always a thesis breaker if moat is central.
    # Phase 11B P0-1: is_monitoring_only=True — this is a generic forward-looking
    # watchlist item, NOT a company-specific evidence-backed assessment.  It does not
    # enter the Gate 5 severity calculation (only extract_thesis_breakers adds it).
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
                is_monitoring_only=True,
            ))

    # Valuation model assumption break.
    # Phase 11B P0-1: is_monitoring_only=True — duplicates what Gate 3 already covers
    # (fair value range uncertainty → bear_point).  Present here for user awareness
    # of the specific valuation assumptions to track, not as a severity input.
    if valuation and valuation.key_valuation_assumptions:
        breakers.append(ThesisBreaker(
            condition="Key valuation assumptions fail: "
                      + "; ".join(valuation.key_valuation_assumptions[:2]),
            likelihood="LOW",
            impact="SEVERE",
            monitoring_indicator="Track actuals vs assumptions in quarterly results.",
            trigger_action="Material assumption miss → reassess fair value; consider REDUCE.",
            is_monitoring_only=True,
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
