"""
Scenario Engine — Phase 11B
============================
Recalculates Gate 5 adversarial risk and the final decision action
using user-supplied likelihood overrides on thesis breakers.

Design contract:
  - NEVER mutates the assessment.  The system baseline is immutable.
  - No pipeline re-run.  Only the severity calculation and action selection
    are re-run on the modified breaker list.
  - Returns a ScenarioResult that carries both baseline and scenario values.
  - All reads from the assessment are via getattr() with safe defaults so
    this module degrades gracefully when called against partial assessments.
  - UNKNOWN breakers: treated as MEDIUM for severity purposes (conservative),
    but displayed as UNKNOWN everywhere else.

Usage:
    from analytics.decision.scenario_engine import run_scenario
    from analytics.decision.decision_models import BreakerOverride

    result = run_scenario(assessment, [
        BreakerOverride(
            condition="Crude oil sustained below $50/bbl",
            baseline_likelihood="MEDIUM",
            user_likelihood="HIGH",
        )
    ])
    print(result.scenario_action, result.decision_changed)
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from analytics.decision.decision_models import (
        InvestmentDecisionAssessment,
        BreakerOverride,
        ScenarioResult,
    )

log = logging.getLogger(__name__)

# Valid user-supplied likelihood values (UNKNOWN not accepted as a what-if target)
_VALID_USER_LIKELIHOODS = {"LOW", "MEDIUM", "HIGH"}


def run_scenario(
    assessment: "InvestmentDecisionAssessment",
    overrides: List["BreakerOverride"],
) -> "ScenarioResult":
    """
    Apply user likelihood overrides to thesis breakers and recalculate
    Gate 5 severity and the final decision action.

    Parameters
    ----------
    assessment  : The completed InvestmentDecisionAssessment (never mutated).
    overrides   : List of BreakerOverride — one per breaker the user adjusted.
                  condition must match ThesisBreaker.condition exactly.
                  user_likelihood must be LOW, MEDIUM, or HIGH.

    Returns
    -------
    ScenarioResult with baseline vs scenario comparison.
    """
    from analytics.decision.decision_models import ScenarioResult, BreakerOverride as _BO

    # --- Baseline values from assessment ---
    baseline_risk = _get_baseline_risk(assessment)
    baseline_action = _get_baseline_action(assessment)

    # --- Validate overrides ---
    clean_overrides: List[_BO] = []
    for ov in overrides:
        user_lk = str(getattr(ov, "user_likelihood", "")).upper()
        if user_lk not in _VALID_USER_LIKELIHOODS:
            log.warning(
                "scenario_engine: invalid user_likelihood %r for condition %r — skipped",
                user_lk, getattr(ov, "condition", "?"),
            )
            continue
        clean_overrides.append(ov)

    if not clean_overrides:
        return ScenarioResult(
            overrides=[],
            baseline_adversarial_risk=baseline_risk,
            scenario_adversarial_risk=baseline_risk,
            baseline_action=baseline_action,
            scenario_action=baseline_action,
            decision_changed=False,
            n_overrides=0,
            scenario_note="No valid overrides applied.",
        )

    # --- Build scenario breaker list (copy + apply overrides) ---
    baseline_breakers = list(getattr(assessment, "thesis_breakers", []))
    override_map = {
        getattr(ov, "condition", ""): str(getattr(ov, "user_likelihood", "")).upper()
        for ov in clean_overrides
    }

    scenario_breakers = []
    for tb in baseline_breakers:
        cond = getattr(tb, "condition", "")
        if cond in override_map:
            # DEF-3 fix: Create a modified copy preserving ALL ThesisBreaker fields,
            # especially is_monitoring_only which must NOT default to False on the copy.
            from analytics.decision.decision_models import ThesisBreaker
            scenario_breakers.append(ThesisBreaker(
                condition=cond,
                likelihood=override_map[cond],
                impact=getattr(tb, "impact", "SEVERE"),
                monitoring_indicator=getattr(tb, "monitoring_indicator", ""),
                trigger_action=getattr(tb, "trigger_action", ""),
                evidence=list(getattr(tb, "evidence", [])),
                likelihood_rationale=getattr(tb, "likelihood_rationale", ""),
                unsupported_evidence=list(getattr(tb, "unsupported_evidence", [])),
                is_monitoring_only=getattr(tb, "is_monitoring_only", False),  # DEF-3
            ))
        else:
            scenario_breakers.append(tb)

    # --- DEF-2 fix: exclude monitoring-only breakers from severity calculation ---
    # Monitoring-only items (moat erosion, valuation assumption watchlist) are
    # generic forward-looking conditions that did NOT enter Gate 5 severity.
    # They must remain excluded in scenario analysis too, regardless of any
    # likelihood override applied to them.
    severity_breakers = [
        b for b in scenario_breakers
        if not getattr(b, "is_monitoring_only", False)
    ]

    # --- DEF-1 fix: include n_bear in severity — read from assessment Gate 5 result ---
    # Bear points are fixed by the original research; only breaker likelihoods change
    # in a scenario.  n_bear is therefore constant across baseline and scenario.
    n_bear = _get_bear_count(assessment)

    # --- Recalculate severity (shared function — single source of truth) ---
    from analytics.decision.gate5_adversarial import calculate_adversarial_severity
    scenario_risk = calculate_adversarial_severity(severity_breakers, n_bear)

    # --- Recalculate action ---
    quality_tier = _get_quality_tier(assessment)
    val_zone     = _get_valuation_zone(assessment)
    is_existing  = _get_is_existing(assessment)

    scenario_action = _select_action(quality_tier, val_zone, scenario_risk, is_existing)

    # --- Build human-readable note ---
    changed_parts = []
    for ov in clean_overrides:
        cond = getattr(ov, "condition", "?")[:60]
        bl   = getattr(ov, "baseline_likelihood", "?")
        ul   = getattr(ov, "user_likelihood", "?")
        changed_parts.append(f"{cond!r}: {bl}→{ul}")
    note = f"{len(clean_overrides)} override(s): " + "; ".join(changed_parts)

    decision_changed = (scenario_action != baseline_action)

    return ScenarioResult(
        overrides=clean_overrides,
        baseline_adversarial_risk=baseline_risk,
        scenario_adversarial_risk=scenario_risk,
        baseline_action=baseline_action,
        scenario_action=scenario_action,
        decision_changed=decision_changed,
        n_overrides=len(clean_overrides),
        scenario_note=note,
    )


# ---------------------------------------------------------------------------
# Bear count accessor
# ---------------------------------------------------------------------------

def _get_bear_count(assessment) -> int:
    """
    Return the Gate 5 bear-point count for use in scenario severity calculation.
    Bear points are fixed by the original research pipeline and do not change
    when the user adjusts breaker likelihoods in a scenario.

    Preference order:
      1. GateResult.n_bear structured field (set by evaluate_gate5() after K1 follow-up).
         This is the authoritative value and is immune to summary-wording changes.
      2. Summary-string parse (legacy fallback for assessments loaded from JSON that
         pre-date the n_bear field — the field defaults to 0 on those objects so we
         can distinguish "structured 0" from "not set" only via the string).

    For new assessments, path 1 always wins.  For legacy assessments, path 2 recovers
    the count exactly as the original K1 implementation did.

    Returns 0 on missing data (safe — scenario evaluates breaker-based risk alone).
    """
    _bear_re = re.compile(r'(\d+)\s+bear-case evidence point')
    for gr in getattr(assessment, "gate_results", []):
        if getattr(gr, "gate_number", 0) == 5:
            # Path 1: structured field — None means absent/legacy; int (including 0) is authoritative.
            n_bear_structured = getattr(gr, "n_bear", None)
            if n_bear_structured is not None:
                return int(n_bear_structured)
            # Path 2: legacy fallback — n_bear field absent or None
            # Covers assessments loaded from JSON that pre-date the structured field.
            summary = getattr(gr, "summary", "")
            m = _bear_re.search(summary)
            if m:
                return int(m.group(1))
    return 0


# ---------------------------------------------------------------------------
# Action selection (pure function — mirrors decision_synthesizer._select_action)
# ---------------------------------------------------------------------------

def _select_action(
    quality_tier: str,
    val_zone: str,
    adversarial_risk: str,
    is_existing: bool,
) -> str:
    """
    Simplified action selection for scenario recalculation.
    Mirrors the logic of decision_synthesizer._select_action() but as a
    pure function operating on string values — no pipeline dependencies.
    """
    # Step 1: CONCERN quality — no positive actions
    if quality_tier == "CONCERN":
        if is_existing:
            return "EXIT" if adversarial_risk == "SEVERE" else "REDUCE"
        return "WATCH"

    # Step 2: SEVERE adversarial risk — override positive conclusions
    if adversarial_risk == "SEVERE":
        if is_existing:
            if val_zone in ("ACCUMULATE", "START_SMALL"):
                return "HOLD"
            return "REDUCE"
        return "WATCH"

    # Step 3: WATCH quality — limited positive action
    if quality_tier == "WATCH":
        return "HOLD" if is_existing else "WATCH"

    # Step 4: Quality is GOOD/STRONG/EXCELLENT — apply valuation zone
    if val_zone == "ACCUMULATE":
        return "ACCUMULATE" if is_existing else "START_SMALL"
    if val_zone == "START_SMALL":
        return "ACCUMULATE" if is_existing else "START_SMALL"

    # WATCH or WAIT zone
    return "HOLD" if is_existing else "WATCH"


# ---------------------------------------------------------------------------
# Assessment accessors (all safe-default to avoid AttributeError)
# ---------------------------------------------------------------------------

def _get_baseline_risk(assessment) -> str:
    for gr in getattr(assessment, "gate_results", []):
        if getattr(gr, "gate_number", 0) == 5:
            return getattr(gr, "adversarial_risk", "MODERATE") or "MODERATE"
    return "MODERATE"


def _get_baseline_action(assessment) -> str:
    action = getattr(assessment, "action", None)
    if action is None:
        return "UNKNOWN"
    return action.value if hasattr(action, "value") else str(action)


def _get_quality_tier(assessment) -> str:
    for gr in getattr(assessment, "gate_results", []):
        if getattr(gr, "gate_number", 0) == 2:
            return getattr(gr, "quality_tier", "WATCH") or "WATCH"
    return "WATCH"


def _get_valuation_zone(assessment) -> str:
    zone = getattr(assessment, "valuation_zone", "")
    if zone:
        return zone
    # Fallback: try to read from Gate 3 summary
    for gr in getattr(assessment, "gate_results", []):
        if getattr(gr, "gate_number", 0) == 3:
            summary = getattr(gr, "summary", "").upper()
            for z in ("ACCUMULATE", "START_SMALL", "WATCH", "WAIT"):
                if z in summary:
                    return z
    return "WAIT"


def _get_is_existing(assessment) -> bool:
    for gr in getattr(assessment, "gate_results", []):
        if getattr(gr, "gate_number", 0) == 4:
            summary = getattr(gr, "summary", "").lower()
            return "existing" in summary or "8" in summary  # heuristic
    # Fallback: check portfolio_context_conclusion
    port = getattr(assessment, "portfolio_context_conclusion", "").lower()
    return "existing" in port
