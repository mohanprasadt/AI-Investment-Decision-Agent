"""
Decision Trace — Phase 11A-1
=============================
Builds and renders a human-readable, gate-by-gate audit trail from a completed
InvestmentDecisionAssessment.

Design contract:
  - Read-only: never mutates the assessment.
  - No external dependencies beyond stdlib.
  - render_decision_trace() returns a plain text string suitable for UI and logs.
  - Consumed by: analytics/agent/renderer.py (_answer_why) and ui/app.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from analytics.decision.decision_models import InvestmentDecisionAssessment


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class GateTraceLine:
    """One gate's contribution to the decision trace."""
    gate_number: int
    gate_name: str
    verdict: str          # "PASSED" | "FAILED" | "FORCED: <action>"
    quality_tier: Optional[str] = None
    adversarial_risk: Optional[str] = None
    confidence: str = ""
    summary: str = ""
    key_evidence: List[str] = field(default_factory=list)   # top supporting/contradictory
    data_gaps: List[str] = field(default_factory=list)
    philosophy_notes: List[str] = field(default_factory=list)
    # Phase 11B: per-breaker details for Gate 5 display.
    # P0-1 corrective: only severity-contributing breakers (is_monitoring_only=False).
    thesis_breaker_lines: List[str] = field(default_factory=list)
    # Phase 11B P0-1 corrective: monitoring-only items shown separately (is_monitoring_only=True).
    monitoring_indicator_lines: List[str] = field(default_factory=list)


@dataclass
class DecisionTrace:
    """
    Full gate-by-gate audit trail for one analysis run.

    Built from InvestmentDecisionAssessment.gate_results.
    Consumed by render_decision_trace() and UI expanders.
    """
    ticker: str
    analysis_date: str
    final_action: str
    decision_confidence: str
    gate_lines: List[GateTraceLine] = field(default_factory=list)
    # Human-readable path explanation (e.g. "Path B: SEVERE adversarial + existing position")
    decision_path: str = ""
    # Severity-contributing thesis breakers (is_monitoring_only=False) — drove Gate 5 severity.
    thesis_breaker_summary: List[str] = field(default_factory=list)
    # Phase 11B P0-1 corrective: monitoring-only items — did NOT affect Gate 5 severity.
    monitoring_indicator_summary: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_decision_trace(assessment: "InvestmentDecisionAssessment") -> DecisionTrace:
    """
    Convert a completed InvestmentDecisionAssessment into a DecisionTrace.

    Never raises — returns a partial trace if gate_results is empty.
    """
    action = assessment.action.value if hasattr(assessment.action, "value") else str(assessment.action)
    confidence = (
        assessment.decision_confidence.value
        if hasattr(assessment.decision_confidence, "value")
        else str(assessment.decision_confidence)
    )

    gate_lines: List[GateTraceLine] = []
    for gr in assessment.gate_results:
        if gr.forced_action:
            verdict = f"FORCED: {gr.forced_action}"
        elif gr.passed:
            verdict = "PASSED"
        else:
            verdict = "FAILED"

        # Combine supporting + contradictory evidence (up to 4 items total)
        key_ev: List[str] = []
        for ev in (gr.supporting_evidence or [])[:2]:
            key_ev.append(f"✓ {ev}")
        for ev in (gr.contradictory_evidence or [])[:2]:
            key_ev.append(f"✗ {ev}")

        # Phase 11B P0-1 corrective: separate severity-contributing from monitoring-only.
        # Uses is_monitoring_only flag — never string matching.
        tb_lines: List[str] = []         # severity-contributing only
        mon_lines: List[str] = []        # monitoring-only only
        if gr.gate_number == 5:
            for tb in (assessment.thesis_breakers or []):
                is_mon = getattr(tb, "is_monitoring_only", False)
                lk = getattr(tb, "likelihood", "?")
                cond = getattr(tb, "condition", str(tb))
                ev_list = getattr(tb, "evidence", [])
                rationale = getattr(tb, "likelihood_rationale", "")
                if is_mon:
                    mon_lines.append(f"  [{lk}] {cond}")
                    monitor = getattr(tb, "monitoring_indicator", "")
                    if monitor:
                        mon_lines.append(f"       Monitor: {monitor}")
                else:
                    tb_lines.append(f"  [{lk}] {cond}")
                    if rationale:
                        tb_lines.append(f"       Rationale: {rationale}")
                    for ev in ev_list[:2]:
                        tb_lines.append(f"       — {ev}")

        gate_lines.append(GateTraceLine(
            gate_number=gr.gate_number,
            gate_name=gr.gate_name,
            verdict=verdict,
            quality_tier=gr.quality_tier,
            adversarial_risk=gr.adversarial_risk,
            confidence=gr.confidence,
            summary=gr.summary,
            key_evidence=key_ev,
            data_gaps=list(gr.data_gaps or []),
            philosophy_notes=list(gr.philosophy_notes or []),
            thesis_breaker_lines=tb_lines,
            monitoring_indicator_lines=mon_lines,
        ))

    # Infer decision path from gate results
    decision_path = _infer_decision_path(assessment, action)

    # Phase 11B P0-1 corrective: split thesis breakers by is_monitoring_only.
    # severity-contributing breakers drove Gate 5 n_high / n_medium_equiv.
    # monitoring-only items are forward-looking watchlist items that did NOT enter severity.
    tb_summary: List[str] = []
    mon_summary: List[str] = []
    for tb in (assessment.thesis_breakers or []):
        is_mon = getattr(tb, "is_monitoring_only", False)
        line = f"• {tb.condition} (likelihood: {tb.likelihood})"
        if is_mon:
            mon_summary.append(line)
        else:
            tb_summary.append(line)

    return DecisionTrace(
        ticker=assessment.ticker,
        analysis_date=assessment.analysis_date,
        final_action=action,
        decision_confidence=confidence,
        gate_lines=gate_lines,
        decision_path=decision_path,
        thesis_breaker_summary=tb_summary,
        monitoring_indicator_summary=mon_summary,
    )


def _infer_decision_path(
    assessment: "InvestmentDecisionAssessment",
    action: str,
) -> str:
    """
    Produce a one-line explanation of which decision branch was taken.
    Reads gate_results rather than re-implementing synthesizer logic.
    """
    gate2_tier = next(
        (gr.quality_tier for gr in assessment.gate_results if gr.gate_number == 2),
        None,
    )
    gate5_risk = next(
        (gr.adversarial_risk for gr in assessment.gate_results if gr.gate_number == 5),
        None,
    )
    gate1_passed = next(
        (gr.passed for gr in assessment.gate_results if gr.gate_number == 1),
        None,
    )

    if action in ("EXIT",) and gate2_tier in ("CONCERN",):
        return "Path A: Gate 2 CONCERN tier → EXIT (quality too low)"
    if action in ("WAIT_INSUFFICIENT_EVIDENCE",) and gate1_passed is False:
        return "Path X: Gate 1 failed → WAIT (business not understood)"
    if gate5_risk == "SEVERE" and action in ("REDUCE", "EXIT", "WATCH"):
        return (
            f"Path B: Gate 5 SEVERE adversarial risk → {action} "
            f"(thesis breakers credible, position adjustment warranted)"
        )
    if action in ("ACCUMULATE", "START_SMALL"):
        return f"Path C: Quality gates passed, valuation attractive → {action}"
    if action in ("HOLD", "WATCH"):
        return f"Path D: Quality gates passed, valuation not yet in zone → {action}"
    return f"Decision: {action} (see gate details below)"


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

GATE_ICONS = {1: "①", 2: "②", 3: "③", 4: "④", 5: "⑤"}
VERDICT_ICONS = {
    "PASSED": "✅",
    "FAILED": "❌",
}


def render_decision_trace(trace: DecisionTrace) -> str:
    """
    Render a DecisionTrace to a plain-text string.

    Suitable for Streamlit st.text / st.expander, CLI output, and log files.
    """
    lines: List[str] = []
    sep = "─" * 60

    lines.append(sep)
    lines.append(f"DECISION TRACE — {trace.ticker}  ({trace.analysis_date})")
    lines.append(sep)
    lines.append(f"Final action : {trace.final_action}")
    lines.append(f"Confidence   : {trace.decision_confidence}")
    lines.append(f"Path         : {trace.decision_path}")
    lines.append("")

    for gl in trace.gate_lines:
        icon = GATE_ICONS.get(gl.gate_number, str(gl.gate_number))

        # Phase 11B fix (D1): Gate 5 always passes but its icon must reflect
        # adversarial_risk, not the verdict string — showing ✅ PASSED with
        # SEVERE risk was misleading.
        if gl.gate_number == 5 and gl.adversarial_risk:
            verdict_icon = {
                "SEVERE":   "🔴",
                "HIGH":     "⚠️",
                "MODERATE": "🟡",
                "LOW":      "✅",
            }.get(gl.adversarial_risk, "⚠️")
        elif gl.verdict.startswith("FORCED"):
            verdict_icon = "🔴"
        else:
            verdict_icon = VERDICT_ICONS.get(gl.verdict, "⚠")

        lines.append(f"{icon} Gate {gl.gate_number}: {gl.gate_name}")
        lines.append(f"   {verdict_icon} {gl.verdict}  |  Confidence: {gl.confidence}")

        if gl.quality_tier:
            lines.append(f"   Quality tier: {gl.quality_tier}")
        if gl.adversarial_risk:
            lines.append(f"   Adversarial risk: {gl.adversarial_risk}")

        if gl.summary:
            lines.append(f"   {gl.summary}")

        for ev in gl.key_evidence:
            lines.append(f"      {ev}")

        if gl.data_gaps:
            lines.append(f"   Data gaps:")
            for dg in gl.data_gaps:
                lines.append(f"      ⚠ {dg}")

        if gl.philosophy_notes:
            for pn in gl.philosophy_notes:
                lines.append(f"   📌 {pn}")

        # Phase 11B P0-1 corrective: per-breaker block for Gate 5, separated by category.
        if gl.thesis_breaker_lines:
            lines.append("   Severity-contributing thesis breakers:")
            lines += gl.thesis_breaker_lines
        if gl.monitoring_indicator_lines:
            if gl.thesis_breaker_lines:
                lines.append("")
            lines.append("   Monitoring indicators (did NOT affect Gate 5 severity):")
            lines += gl.monitoring_indicator_lines

        lines.append("")

    # Phase 11B P0-1 corrective: THESIS BREAKERS summary uses only severity-contributing items.
    if trace.thesis_breaker_summary:
        lines.append("CONTRIBUTING THESIS BREAKERS (Gate 5):")
        lines += trace.thesis_breaker_summary
        lines.append("")
    if trace.monitoring_indicator_summary:
        lines.append("MONITORING INDICATORS (did NOT affect Gate 5 severity):")
        lines += trace.monitoring_indicator_summary
        lines.append("")

    lines.append(sep)
    return "\n".join(lines)
