"""
Investment Decision Synthesizer — Phase 7
==========================================
Main entry point for the Phase 7 decision engine.

Combines all four upstream assessments through five hierarchical gates
to produce a structured InvestmentDecisionAssessment.

Decision hierarchy:
  Gate 1 — Business understanding    (can force WAIT_INSUFFICIENT_EVIDENCE)
  Gate 2 — Business & financial quality  (produces QualityTier)
  Gate 3 — Valuation                 (produces zone and confidence)
  Gate 4 — Portfolio context         (produces sizing modifier)
  Gate 5 — Adversarial challenge     (produces AdversarialRisk)
  Synthesizer — combines all gates → DecisionAction

Quality is the primary filter.
Valuation is the timing filter.
Portfolio context sizes the position.
Adversarial challenge stress-tests the conclusion.

Sunk-cost protection:
  Average cost / unrealized P/L from portfolio context is NEVER
  used in any decision logic. It is acknowledged and excluded.

Do not use a weighted score.
"""

import sys
from pathlib import Path
from typing import Optional, List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.decision.decision_models import (
    InvestmentDecisionAssessment,
    DecisionAction,
    DecisionConfidence,
    DecisionEvidenceItem,
    EvidenceStrength,
    QualityTier,
    AdversarialRisk,
    ThesisBreaker,
    GateResult,
)
from analytics.decision.gate1_understanding import evaluate_gate1
from analytics.decision.gate2_quality import evaluate_gate2
from analytics.decision.gate3_valuation import evaluate_gate3
from analytics.decision.gate4_portfolio import evaluate_gate4
from analytics.decision.gate5_adversarial import evaluate_gate5, extract_thesis_breakers
from analytics.business_research.research_models import BusinessResearchAssessment
from analytics.portfolio.portfolio_models import (
    PortfolioPositionContext, WeightOnlyPortfolioContext,
)
from analytics.valuation.valuation_models import (
    ValuationAssessment, AccumulationZoneLabel, ValuationConfidence,
    MethodReliability,
)
from analytics.valuation.valuation_synthesizer import _RELIABILITY_WEIGHT
from analytics.data_freshness import DataFreshnessAssessment


def make_investment_decision(
    ticker: str,
    company_name: str,
    analysis_date: str,
    financial_quality=None,          # FinancialQualityAssessment (Phase 3)
    research: Optional[BusinessResearchAssessment] = None,   # Phase 4
    valuation: Optional[ValuationAssessment] = None,         # Phase 5
    portfolio_ctx=None,              # Phase 6: PortfolioPositionContext | WeightOnlyPortfolioContext | None
    current_price: Optional[float] = None,
    price_currency: str = "CAD",
    price_date: str = "",
    freshness: Optional[DataFreshnessAssessment] = None,     # Phase 7.5: data freshness
    fcf_raw_metrics=None,            # Phase 9.6: FreeCashFlowMetrics (duck-typed); provides annual_fcf, annual_capex
    fcf_shares_outstanding=None,     # Phase 9.6: shares outstanding (int/float) for FCF/share attribution
) -> InvestmentDecisionAssessment:
    """
    Produce a structured InvestmentDecisionAssessment from upstream phase outputs.

    All four upstream inputs are optional — missing inputs degrade confidence
    and may trigger WAIT_INSUFFICIENT_EVIDENCE, but the engine always returns
    a structured output.

    Parameters
    ----------
    ticker            : Stock ticker (e.g. "CNR.TO")
    company_name      : Display name
    analysis_date     : ISO date string of this analysis
    financial_quality : Phase 3 FinancialQualityAssessment
    research          : Phase 4 BusinessResearchAssessment
    valuation         : Phase 5 ValuationAssessment
    portfolio_ctx     : Phase 6 PortfolioPositionContext
    current_price     : Current share price (if not in valuation)
    price_currency    : Currency code for current_price
    price_date        : Date of the price quote

    Returns
    -------
    InvestmentDecisionAssessment — the first L3 output in the system.
    """
    # -----------------------------------------------------------------------
    # Resolve current price
    # -----------------------------------------------------------------------
    _price = current_price
    _currency = price_currency
    if _price is None and valuation and valuation.current_price:
        _price = valuation.current_price
        _currency = valuation.currency
    # Only full PortfolioPositionContext carries current_price_local
    if (_price is None and portfolio_ctx is not None
            and isinstance(portfolio_ctx, PortfolioPositionContext)
            and portfolio_ctx.current_price_local):
        _price = portfolio_ctx.current_price_local
        _currency = portfolio_ctx.price_currency

    # Build per-method summary early so early-stop paths can also carry it.
    method_summary = _build_method_summary(valuation, _price, _currency)

    # Extract FCF / EPS provenance from ValuationAssessment (Phase 9.5).
    # Reads only existing method-result fields — no new calculations.
    # All three stay None when the respective method was not applicable.
    _fcf_per_share: Optional[float] = None
    _fcf_norm_note: str = ""
    _eps_used: Optional[float] = None
    _eps_norm_note: str = ""
    if valuation is not None:
        pfcf = valuation.price_to_fcf_result
        if pfcf is not None and pfcf.metric_value is not None:
            _fcf_per_share = pfcf.metric_value
            _fcf_norm_note = pfcf.normalization_note or ""
        pe_r = valuation.normalized_pe_result
        if pe_r is not None and pe_r.metric_value is not None:
            _eps_used = pe_r.metric_value
            _eps_norm_note = pe_r.normalization_note or ""

    # Build FCF annual breakdown from raw FreeCashFlowMetrics (Phase 9.6 / 9.9).
    # fcf_raw_metrics is duck-typed: expects .annual_fcf, .annual_capex, .annual_ocf.
    # capex is stored as a signed value (typically negative cash outflow).
    # ocf: prefer the directly stored annual_ocf series (Phase 9.9); fall back to
    #      deriving it as fcf - capex when annual_ocf is not available for that year.
    # No new financial calculations — reads only values already computed by normalizer.py.
    _fcf_breakdown: List[dict] = []
    _fcf_shares: Optional[float] = fcf_shares_outstanding
    if fcf_raw_metrics is not None:
        _ann_fcf   = getattr(fcf_raw_metrics, "annual_fcf",   {}) or {}
        _ann_capex = getattr(fcf_raw_metrics, "annual_capex", {}) or {}
        _ann_ocf   = getattr(fcf_raw_metrics, "annual_ocf",   {}) or {}
        for _yr in sorted(_ann_fcf.keys(), reverse=True):
            _fcf_v   = _ann_fcf[_yr]
            _capex_v = _ann_capex.get(_yr, None)
            # Prefer persisted OCF (directly from yfinance cash flow statement)
            if _ann_ocf and _yr in _ann_ocf:
                _ocf_v = _ann_ocf[_yr]
            elif _capex_v is not None:
                _ocf_v = _fcf_v - _capex_v   # fallback: re-derive as FCF − capex
            else:
                _ocf_v = None
            _fcf_breakdown.append({
                "year":  int(_yr),
                "ocf":   _ocf_v,
                "capex": _capex_v,
                "fcf":   _fcf_v,
            })

    # -----------------------------------------------------------------------
    # Run gates sequentially
    # -----------------------------------------------------------------------
    g1 = evaluate_gate1(research, financial_quality)

    # Gate 1 hard stop
    if not g1.passed:
        return _early_stop(
            ticker, company_name, analysis_date,
            _price, _currency, price_date,
            forced_action=DecisionAction.WAIT_INSUFFICIENT_EVIDENCE,
            gate_results=[g1],
            reason=g1.summary,
            data_gaps=g1.data_gaps,
            per_method_valuation_summary=method_summary,
            fcf_per_share_used=_fcf_per_share,
            fcf_normalization_note=_fcf_norm_note,
            eps_used_in_valuation=_eps_used,
            eps_normalization_note=_eps_norm_note,
            fcf_annual_breakdown=_fcf_breakdown,
            fcf_shares_outstanding=_fcf_shares,
        )

    g2 = evaluate_gate2(financial_quality, research)
    g3 = evaluate_gate3(valuation)
    g4 = evaluate_gate4(portfolio_ctx)
    g5 = evaluate_gate5(research, financial_quality, valuation, portfolio_ctx, g2)

    all_gates = [g1, g2, g3, g4, g5]

    # -----------------------------------------------------------------------
    # Extract key signals from gates
    # -----------------------------------------------------------------------
    quality_tier       = QualityTier(g2.quality_tier) if g2.quality_tier else QualityTier.WATCH
    val_zone           = _extract_zone(valuation)
    adversarial_risk   = AdversarialRisk(g5.adversarial_risk) if g5.adversarial_risk else AdversarialRisk.MODERATE
    is_existing        = portfolio_ctx.is_existing_holding if portfolio_ctx is not None else False
    # has_high_conc: WeightOnly uses weight >= 10% as a proxy; full uses concentration flags
    from analytics.decision.gate4_portfolio import has_high_concentration
    has_high_conc      = has_high_concentration(portfolio_ctx)

    # -----------------------------------------------------------------------
    # Core action selection
    # -----------------------------------------------------------------------
    action = _select_action(
        quality_tier, val_zone, adversarial_risk, is_existing, has_high_conc, g3,
    )

    # -----------------------------------------------------------------------
    # Decision confidence
    # -----------------------------------------------------------------------
    confidence = _compute_confidence(
        action, g1, g2, g3, g4, g5, quality_tier, adversarial_risk,
        portfolio_ctx=portfolio_ctx,
    )

    # -----------------------------------------------------------------------
    # Thesis breakers
    # -----------------------------------------------------------------------
    thesis_breakers = extract_thesis_breakers(research, financial_quality, valuation)

    # -----------------------------------------------------------------------
    # Aggregate evidence items
    # -----------------------------------------------------------------------
    supporting_ev  = _collect_evidence(all_gates, supports_thesis=True)
    contradictory_ev = _collect_evidence(all_gates, supports_thesis=False)

    # -----------------------------------------------------------------------
    # Domain conclusions
    # -----------------------------------------------------------------------
    bq_conclusion  = _business_quality_conclusion(quality_tier, g2)
    val_conclusion = _valuation_conclusion(val_zone, valuation, g3)
    port_conclusion = _portfolio_conclusion(is_existing, portfolio_ctx, g4)

    # -----------------------------------------------------------------------
    # Narrative — 6 required questions
    # -----------------------------------------------------------------------
    why_attr         = _why_attractive_or_not(quality_tier, val_zone, g2)
    biggest_for      = _biggest_reason_to_invest(quality_tier, val_zone, g2, research)
    biggest_against  = _biggest_reason_not_to_invest(adversarial_risk, g5, quality_tier, val_zone)
    price_attractive = _price_attractive_text(val_zone, valuation, _price, _currency)
    what_would_change = _what_would_change_list(g5, research, valuation, quality_tier)

    # -----------------------------------------------------------------------
    # Bear case
    # -----------------------------------------------------------------------
    bear_case = _bear_case_text(g5, research)

    # -----------------------------------------------------------------------
    # Key risks and assumptions
    # -----------------------------------------------------------------------
    key_risks   = _collect_risks(g2, g5, portfolio_ctx)
    key_assumps = list(valuation.key_valuation_assumptions or []) if valuation else []
    if research and research.business_understanding:
        key_assumps.append(f"Business model: {research.business_understanding.how_it_makes_money[:100]}" if research.business_understanding.how_it_makes_money else "")

    # -----------------------------------------------------------------------
    # Data quality
    # -----------------------------------------------------------------------
    dq_limitations = _collect_data_gaps(all_gates)
    research_gaps  = list(research.research_gaps or []) if research else ["BusinessResearchAssessment not provided."]

    # -----------------------------------------------------------------------
    # Philosophy alignment
    # -----------------------------------------------------------------------
    philosophy_notes = _collect_philosophy(all_gates, financial_quality=financial_quality)

    # -----------------------------------------------------------------------
    # Evidence sources
    # -----------------------------------------------------------------------
    sources = _collect_sources(research, financial_quality, valuation, portfolio_ctx)

    # -----------------------------------------------------------------------
    # Business thesis
    # -----------------------------------------------------------------------
    business_thesis = _business_thesis(research, quality_tier, g2)

    # next_step and action_given_port are computed AFTER suppression (below)

    # -----------------------------------------------------------------------
    # Three-way attractiveness labels (Phase 7.5)
    # -----------------------------------------------------------------------
    bq_label = quality_tier.value
    va_label = _valuation_attractiveness_label(val_zone)
    ia_label = _investment_attractiveness_label(quality_tier, val_zone, adversarial_risk)
    ia_note  = _investment_attractiveness_note(quality_tier, val_zone, adversarial_risk)

    # -----------------------------------------------------------------------
    # Data freshness cap (Phase 7.5) — applied BEFORE narrative generation
    # so that exec_conclusion reflects the final capped confidence
    # -----------------------------------------------------------------------
    freshness_dict = None
    freshness_cap_applied = False
    if freshness is not None:
        freshness_dict = freshness.to_dict()
        capped = freshness.apply_confidence_cap(confidence.value)
        if capped != confidence.value:
            confidence = DecisionConfidence(capped)
            freshness_cap_applied = True

    # -----------------------------------------------------------------------
    # Price-data suppression (Phase 7.8)
    # When the current market price is STALE or UNKNOWN, suppress transactional
    # purchase/reduction actions that require knowing the current price to be
    # directionally correct.  The qualitative conclusion is preserved separately.
    #
    # Suppressed actions: START_SMALL, ACCUMULATE, REDUCE
    #   → All require knowing whether the current price is above/below a zone.
    # Preserved actions: HOLD, WATCH, EXIT, WAIT_INSUFFICIENT_EVIDENCE
    #   → HOLD/WATCH: directionally correct regardless of exact price.
    #   → EXIT: driven by thesis break, not zone.
    #   → WAIT_INSUFFICIENT_EVIDENCE: already a non-transactional state.
    # -----------------------------------------------------------------------
    _PRICE_DEPENDENT_ACTIONS = frozenset({
        DecisionAction.START_SMALL,
        DecisionAction.ACCUMULATE,
        DecisionAction.REDUCE,
    })

    # Always compute the qualitative view from the pre-suppression action so
    # the field is populated in every output, not only when suppression fires.
    qualitative_investment_view = _qualitative_view_label(action)
    price_suppression_applied = False

    if action in _PRICE_DEPENDENT_ACTIONS and _price_is_stale_or_unknown(freshness):
        # qualitative_investment_view already captures the pre-suppression direction;
        # only the transaction action is suppressed here.
        action = DecisionAction.WATCH_PENDING_DATA
        price_suppression_applied = True

    # -----------------------------------------------------------------------
    # Narrative fields that depend on the final (possibly suppressed) action
    # Must be computed AFTER suppression so they reflect WATCH_PENDING_DATA,
    # not the pre-suppression ACCUMULATE/START_SMALL/REDUCE.
    # -----------------------------------------------------------------------
    action_given_port = _action_given_portfolio(
        action, is_existing, portfolio_ctx, has_high_conc,
        adversarial_risk=adversarial_risk, quality_tier=quality_tier,
    )
    next_step = _recommended_next_step(action, is_existing, portfolio_ctx, thesis_breakers, val_zone)

    # -----------------------------------------------------------------------
    # Executive conclusion (after freshness cap so it reflects final confidence)
    # -----------------------------------------------------------------------
    exec_conclusion = _executive_conclusion(
        ticker, company_name, action, quality_tier, val_zone,
        is_existing, confidence, adversarial_risk,
        qualitative_view=qualitative_investment_view,
    )

    return InvestmentDecisionAssessment(
        ticker=ticker,
        company_name=company_name,
        analysis_date=analysis_date,
        current_price=_price,
        price_currency=_currency,
        price_date=price_date,
        action=action,
        decision_confidence=confidence,
        why_attractive_or_unattractive=why_attr,
        biggest_reason_to_invest=biggest_for,
        biggest_reason_not_to_invest=biggest_against,
        is_current_price_attractive=price_attractive,
        appropriate_action_given_portfolio=action_given_port,
        what_would_change_conclusion=_format_what_would_change(what_would_change),
        executive_conclusion=exec_conclusion,
        business_thesis=business_thesis,
        supporting_evidence=supporting_ev,
        contradictory_evidence=contradictory_ev,
        gate_results=all_gates,
        business_quality_conclusion=bq_conclusion,
        valuation_conclusion=val_conclusion,
        portfolio_context_conclusion=port_conclusion,
        key_risks=key_risks,
        bear_case=bear_case,
        thesis_breakers=thesis_breakers,
        what_would_change_decision=what_would_change,
        key_assumptions=[a for a in key_assumps if a],
        data_quality_limitations=dq_limitations,
        research_gaps=research_gaps,
        philosophy_alignment_notes=philosophy_notes,
        recommended_next_step=next_step,
        evidence_sources=sources,
        # Three-way attractiveness (Phase 7.5)
        business_quality_label=bq_label,
        valuation_attractiveness_label=va_label,
        investment_attractiveness_label=ia_label,
        investment_attractiveness_note=ia_note,
        # Data freshness (Phase 7.5)
        data_freshness=freshness_dict,
        data_freshness_cap_applied=freshness_cap_applied,
        # Price-data suppression (Phase 7.8)
        qualitative_investment_view=qualitative_investment_view,
        price_suppression_applied=price_suppression_applied,
        # Per-method valuation transparency (Phase 9.4)
        per_method_valuation_summary=method_summary,
        # FCF / EPS provenance (Phase 9.5 / 9.9)
        fcf_per_share_used=_fcf_per_share,
        fcf_normalization_note=_fcf_norm_note,
        eps_used_in_valuation=_eps_used,
        eps_normalization_note=_eps_norm_note,
        # FCF annual chain (Phase 9.6)
        fcf_annual_breakdown=_fcf_breakdown,
        fcf_shares_outstanding=_fcf_shares,
        # Valuation zone (Phase 11B) — stored for scenario engine reuse
        valuation_zone=val_zone if isinstance(val_zone, str) else str(val_zone),
    )


# ===========================================================================
# Action selection (core hierarchical logic)
# ===========================================================================

def _select_action(
    quality: QualityTier,
    zone: str,            # AccumulationZoneLabel value or "WATCH"
    adversarial: AdversarialRisk,
    is_existing: bool,
    has_high_concentration: bool,
    g3: GateResult,
) -> DecisionAction:
    """
    Hierarchical action selection.

    Priority order:
    1. Quality gate — CONCERN quality blocks positive actions
    2. Adversarial gate — SEVERE risk overrides positive conclusions
    3. Valuation zone — timing signal
    4. Portfolio context — sizing modifier (existing vs new)
    """

    # -----------------------------------------------------------------------
    # Step 1: CONCERN quality — no positive actions
    # -----------------------------------------------------------------------
    if quality == QualityTier.CONCERN:
        if is_existing:
            # Existing position with CONCERN quality — must investigate
            if adversarial == AdversarialRisk.SEVERE:
                return DecisionAction.EXIT
            return DecisionAction.REDUCE
        else:
            return DecisionAction.WATCH  # Don't START if quality is CONCERN

    # -----------------------------------------------------------------------
    # Step 2: SEVERE adversarial risk — override positive conclusions
    # -----------------------------------------------------------------------
    if adversarial == AdversarialRisk.SEVERE:
        if is_existing:
            # Valuation zone modifies the REDUCE decision:
            #
            # When the current price offers a genuine margin of safety
            # (ACCUMULATE or START_SMALL zone), the valuation discount partially
            # compensates for thesis uncertainty.  In that case HOLD is more
            # appropriate than REDUCE: the investor is not adding, but the cheap
            # price means they are not actively harmed by holding while monitoring.
            #
            # When the price is at or above fair value (WATCH or WAIT zone),
            # there is no valuation buffer to offset the thesis risk.  Holding
            # an expensive position with an uncertain thesis is a double negative
            # — REDUCE is the correct response.
            #
            # This also avoids a perverse outcome: a great business that has
            # fallen to half its fair value should NOT be reduced simply because
            # an adversarial risk appeared; the cheap price already prices in risk.
            if zone in ("ACCUMULATE", "START_SMALL"):
                return DecisionAction.HOLD  # Valuation buffer offsets thesis uncertainty
            else:
                return DecisionAction.REDUCE  # No valuation buffer; thesis at risk
        else:
            # New position: don't start when thesis is under severe challenge
            return DecisionAction.WATCH

    # -----------------------------------------------------------------------
    # Step 3: WATCH quality — limited positive action
    # -----------------------------------------------------------------------
    if quality == QualityTier.WATCH:
        if is_existing:
            return DecisionAction.HOLD
        else:
            return DecisionAction.WATCH

    # -----------------------------------------------------------------------
    # Step 4: Quality is GOOD, STRONG, or EXCELLENT — apply valuation filter
    # -----------------------------------------------------------------------

    # No valuation data → watch until valuation is established
    if zone == "WATCH" and g3.confidence == "LOW" and not g3.supporting_evidence:
        # True "no valuation" case
        if is_existing:
            return DecisionAction.HOLD
        else:
            return DecisionAction.WATCH

    # Map zone to base action
    if zone == "ACCUMULATE":
        base = DecisionAction.ACCUMULATE if is_existing else DecisionAction.START_SMALL
    elif zone == "START_SMALL":
        base = DecisionAction.ACCUMULATE if is_existing else DecisionAction.START_SMALL
    elif zone == "WATCH":
        base = DecisionAction.HOLD if is_existing else DecisionAction.WATCH
    else:  # WAIT
        base = DecisionAction.HOLD if is_existing else DecisionAction.WATCH

    # -----------------------------------------------------------------------
    # Step 5: Adversarial modifier (HIGH risk softens positive actions)
    # -----------------------------------------------------------------------
    if adversarial == AdversarialRisk.HIGH:
        if base == DecisionAction.ACCUMULATE:
            # Still proceed but note caution; synthesizer will reflect in lower confidence
            pass  # ACCUMULATE with HIGH adversarial → confidence downgraded, noted in output
        if base == DecisionAction.START_SMALL and not is_existing:
            pass  # START_SMALL is already cautious — keep it

    # -----------------------------------------------------------------------
    # Step 6: Existing position with WAIT/WATCH zone — HOLD unless deteriorating
    # -----------------------------------------------------------------------
    if is_existing and base == DecisionAction.WATCH:
        base = DecisionAction.HOLD

    return base


# ===========================================================================
# Confidence
# ===========================================================================

def _compute_confidence(
    action: DecisionAction,
    g1: GateResult, g2: GateResult, g3: GateResult,
    g4: GateResult, g5: GateResult,
    quality: QualityTier,
    adversarial: AdversarialRisk,
    portfolio_ctx=None,
) -> DecisionConfidence:
    """
    Confidence reflects evidence quality of INVESTMENT evidence only.

    Portfolio context (gate 4) is NOT counted in the confidence average when:
    - Portfolio context was not provided (NONE mode)
    - Portfolio context is weight-only (WEIGHT_ONLY mode)

    Rationale: portfolio context tells us about position sizing, not about the
    quality of the investment thesis. Its absence does not reduce the quality
    of the business/valuation assessment.

    Explicitly downgraded when:
    - Adversarial risk is HIGH or SEVERE
    - Gate 2 confidence is LOW (insufficient financial/business data)
    - Gate 3 has many data gaps (valuation uncertain)
    """
    confidence_map = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

    # Only gate 1 (understanding), 2 (quality), 3 (valuation) are investment-quality gates
    investment_gates = [g1, g2, g3]

    # Include gate 4 in the average ONLY for full portfolio context
    from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
    if (portfolio_ctx is not None
            and not isinstance(portfolio_ctx, WeightOnlyPortfolioContext)
            and hasattr(portfolio_ctx, "shares_held")):   # full PortfolioPositionContext
        investment_gates.append(g4)

    scores = [confidence_map.get((g.confidence or "MEDIUM").upper(), 1) for g in investment_gates]
    avg = sum(scores) / max(len(scores), 1)

    # Adversarial downgrade
    if adversarial == AdversarialRisk.SEVERE:
        avg -= 0.8
    elif adversarial == AdversarialRisk.HIGH:
        avg -= 0.4

    # Quality downgrade
    if quality in (QualityTier.WATCH, QualityTier.CONCERN):
        avg -= 0.3

    # EXIT/REDUCE — higher confidence (deterioration is more evident)
    if action in (DecisionAction.EXIT, DecisionAction.REDUCE):
        avg = max(avg, 1.0)

    if avg >= 1.6:
        return DecisionConfidence.HIGH
    elif avg >= 0.8:
        return DecisionConfidence.MEDIUM
    else:
        return DecisionConfidence.LOW


# ===========================================================================
# Narrative builders
# ===========================================================================

def _why_attractive_or_not(quality: QualityTier, zone: str, g2: GateResult) -> str:
    if quality in (QualityTier.EXCELLENT, QualityTier.STRONG):
        q_text = "The business demonstrates strong financial quality and competitive advantage."
    elif quality == QualityTier.GOOD:
        q_text = "The business shows adequate quality with some positive characteristics."
    elif quality == QualityTier.WATCH:
        q_text = "Business quality is mixed — insufficient to support a confident positive conclusion."
    else:
        q_text = "Business quality shows material concerns that outweigh positive factors."

    zone_text = {
        "ACCUMULATE": "The current price offers an attractive margin of safety relative to estimated fair value.",
        "START_SMALL": "The current price is within the attractive entry range.",
        "WATCH": "The current price is approaching but not yet at an attractive level.",
        "WAIT": "The current price is at or above estimated fair value.",
    }.get(zone, "Valuation attractiveness is uncertain — insufficient data.")

    return f"{q_text} {zone_text}"


def _biggest_reason_to_invest(
    quality: QualityTier, zone: str, g2: GateResult,
    research: Optional[BusinessResearchAssessment],
) -> str:
    reasons = []
    if quality in (QualityTier.EXCELLENT, QualityTier.STRONG):
        reasons.append("High business quality (ROIC, moat, FCF) provides a durable earnings base.")
    if zone in ("ACCUMULATE", "START_SMALL"):
        reasons.append("Current price offers a margin of safety relative to intrinsic value.")
    if research and research.moat_assessment:
        moat = research.moat_assessment
        if moat.overall_strength.value in ("Strong", "Exceptional"):
            reasons.append(f"Strong competitive moat ({', '.join(moat.active_sources or [])}) protects long-term economics.")
    if research and research.growth_assessment and research.growth_assessment.growth_sustainability_assessment:
        gs = research.growth_assessment.growth_sustainability_assessment
        if any(w in gs.lower() for w in ["durable", "sustained", "organic", "strong"]):
            reasons.append("Sustainable organic growth provides a long-term compounding runway.")
    return reasons[0] if reasons else "No single dominant reason identified — thesis is balanced."


def _biggest_reason_not_to_invest(
    adversarial: AdversarialRisk, g5: GateResult,
    quality: QualityTier, zone: str,
) -> str:
    if adversarial == AdversarialRisk.SEVERE:
        breakers = [b for b in g5.contradictory_evidence if "breaker" in b.lower() or "structural" in b.lower()]
        if breakers:
            return f"Severe thesis risk: {breakers[0][:200]}"
        return "Severe adversarial risk — one or more credible thesis breakers identified."
    if adversarial == AdversarialRisk.HIGH:
        bc = g5.contradictory_evidence
        return bc[0][:200] if bc else "Significant bear case risks that could challenge the thesis."
    if quality == QualityTier.WATCH:
        return "Business quality is insufficient to support conviction in the thesis."
    if zone == "WAIT":
        return "Current market price is at or above estimated fair value — no margin of safety."
    if zone == "WATCH":
        return "Valuation has not yet reached an attractive entry point."
    contras = g5.contradictory_evidence if g5.contradictory_evidence else []
    return contras[0][:200] if contras else "No dominant reason to avoid — proceed with normal diligence."


def _price_attractive_text(
    zone: str, valuation: Optional[ValuationAssessment],
    price: Optional[float], currency: str,
) -> str:
    if valuation and valuation.accumulation_zone:
        az = valuation.accumulation_zone
        mos = az.actual_margin_of_safety_pct
        req = az.required_margin_of_safety_pct
        if zone == "ACCUMULATE":
            return (
                f"Yes — price ({price:.2f} {currency}) offers {mos:.1f}% margin of safety "
                f"vs required {req:.0f}%. Accumulation zone active."
                if mos is not None else f"Yes — price is in the ACCUMULATE zone."
            )
        elif zone == "START_SMALL":
            return (
                f"Moderately attractive — price ({price:.2f} {currency}) offers {mos:.1f}% MoS, "
                f"approaching required {req:.0f}%. START_SMALL zone."
                if mos is not None else "Moderately attractive — START_SMALL zone."
            )
        elif zone == "WATCH":
            return f"Not yet compelling — price approaching fair value. Monitor for better entry."
        else:
            return f"Not attractive — price at or above estimated fair value."
    if valuation and valuation.fair_value_range and valuation.fair_value_range.base and price:
        fv = valuation.fair_value_range.base
        prem_disc = (price - fv) / fv * 100
        if prem_disc < -15:
            return f"Yes — trading at {-prem_disc:.1f}% discount to base fair value estimate."
        elif prem_disc < 0:
            return f"Modest discount of {-prem_disc:.1f}% to fair value — limited margin of safety."
        else:
            return f"No — trading at {prem_disc:.1f}% premium to base fair value estimate."
    return "Valuation data insufficient to assess price attractiveness."


def _action_given_portfolio(
    action: DecisionAction,
    is_existing: bool,
    portfolio_ctx,
    has_high_conc: bool,
    adversarial_risk: AdversarialRisk = AdversarialRisk.MODERATE,
    quality_tier: QualityTier = QualityTier.WATCH,
) -> str:
    from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
    pos_str = "existing position" if is_existing else "new position"
    conc_note = " (High concentration noted — consider a smaller incremental addition.)" if has_high_conc else ""

    # Incremental scenario note — only available in FULL mode
    size_note = ""
    if (portfolio_ctx is not None
            and not isinstance(portfolio_ctx, WeightOnlyPortfolioContext)
            and hasattr(portfolio_ctx, "incremental_scenarios")
            and portfolio_ctx.incremental_scenarios):
        s = portfolio_ctx.incremental_scenarios[0]
        size_note = (
            f" Smallest scenario: {s.investment_amount_cad:,.0f} CAD → "
            f"{s.shares_purchasable} shares, new weight {s.new_portfolio_weight_pct:.2f}%."
        )
    elif isinstance(portfolio_ctx, WeightOnlyPortfolioContext):
        size_note = (
            f" Current position is ~{portfolio_ctx.portfolio_weight_pct:.1f}% of portfolio. "
            "Position size is not the driver of this recommendation — "
            "determine any sizing change based on the thesis trajectory below."
        )

    # Build REDUCE/EXIT rationale — explicitly distinguish thesis risk from weight size
    if action == DecisionAction.REDUCE:
        if adversarial_risk == AdversarialRisk.SEVERE:
            reduce_rationale = (
                "REDUCE — driven by SEVERE thesis deterioration risk, NOT by portfolio weight. "
                "One or more credible thesis breakers have been identified. "
                "The question is not 'should I add more?' but 'is the original investment thesis still intact?' "
                "Reduce while re-examining the thesis. If thesis breakers resolve, action may be upgraded to HOLD."
            )
        elif quality_tier == QualityTier.CONCERN:
            reduce_rationale = (
                "REDUCE — driven by CONCERN-level business quality deterioration. "
                "Financial or qualitative indicators have weakened materially. "
                "Reduce exposure while monitoring for signs of recovery or further deterioration."
            )
        else:
            reduce_rationale = f"Reduce {pos_str}; thesis signals have weakened."
        return f"{reduce_rationale}{conc_note}{size_note}"

    if action == DecisionAction.EXIT:
        return (
            f"EXIT — thesis has broken materially. "
            "This is not driven by price performance or portfolio weight. "
            f"Exit the {pos_str} in a planned manner and document the thesis break."
        )

    if action == DecisionAction.HOLD and adversarial_risk == AdversarialRisk.SEVERE:
        hold_str = (
            f"HOLD — do NOT add to {pos_str} while thesis risk is unresolved. "
            "The current price provides a valuation buffer that makes active reduction "
            "unwarranted, but this is a monitoring hold, not a conviction hold. "
            "If thesis breakers trigger or price rises above fair value, escalate to REDUCE."
        )
        return f"{hold_str}{size_note}"

    action_str = {
        DecisionAction.START_SMALL:   f"Initiate a small {pos_str}.",
        DecisionAction.ACCUMULATE:    f"Add to {pos_str} at current price.",
        DecisionAction.WATCH:         f"Monitor {pos_str}; wait for better entry or clearer thesis.",
        DecisionAction.HOLD:          f"Maintain {pos_str}; no change warranted.",
        DecisionAction.WAIT_INSUFFICIENT_EVIDENCE: "Gather more evidence before acting.",
        DecisionAction.WATCH_PENDING_DATA: (
            f"No transaction action at this time — current price is stale/unknown. "
            f"Refresh the market price and re-run the analysis to confirm the valuation zone "
            f"before adding to or reducing the {pos_str}."
        ),
    }.get(action, "Review required.")
    return f"{action_str}{conc_note}{size_note}"


def _format_what_would_change(items: List[str]) -> str:
    """Format a list of change-triggers into readable prose/bullet text."""
    if not items:
        return "No specific change triggers identified."
    if len(items) == 1:
        return items[0]
    bullets = "\n".join(f"• {item}" for item in items)
    return bullets


def _what_would_change_list(
    g5: GateResult, research: Optional[BusinessResearchAssessment],
    valuation: Optional[ValuationAssessment], quality: QualityTier,
) -> List[str]:
    items = list(g5.supporting_evidence or [])  # Gate 5 puts "what would change" in supporting
    if quality in (QualityTier.EXCELLENT, QualityTier.STRONG, QualityTier.GOOD):
        items.append(
            "Material deterioration in ROIC, FCF quality, or moat strength would reduce conviction."
        )
    if valuation:
        items.append(
            "Significant price appreciation toward or above fair value would prompt HOLD."
        )
    if research and research.key_investment_questions:
        items += [f"Open question: {q}" for q in research.key_investment_questions[:2]]
    return items[:8] if items else ["No specific change triggers identified."]


def _bear_case_text(g5: GateResult, research: Optional[BusinessResearchAssessment]) -> str:
    if research and research.bull_bear and research.bull_bear.bear_case_narrative:
        return research.bull_bear.bear_case_narrative
    if g5.contradictory_evidence:
        return "Bear case synthesised from available evidence: " + "; ".join(
            g5.contradictory_evidence[:3]
        )
    return "No explicit bear case evidence available — conduct active adversarial research."


def _collect_risks(g2: GateResult, g5: GateResult, portfolio_ctx) -> List[str]:
    risks = list(g2.contradictory_evidence or [])[:4]
    risks += list(g5.contradictory_evidence or [])[:4]
    # Only full PortfolioPositionContext has portfolio_risks
    from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
    if (portfolio_ctx is not None
            and not isinstance(portfolio_ctx, WeightOnlyPortfolioContext)
            and hasattr(portfolio_ctx, "portfolio_risks")):
        risks += list(portfolio_ctx.portfolio_risks or [])[:2]
    return list(dict.fromkeys(risks))[:10]


# ===========================================================================
# Domain conclusion builders
# ===========================================================================

def _business_quality_conclusion(quality: QualityTier, g2: GateResult) -> str:
    tier_map = {
        QualityTier.EXCELLENT: "Excellent business quality — multiple strong financial and qualitative signals.",
        QualityTier.STRONG:    "Strong business quality — broadly positive signals with some areas to monitor.",
        QualityTier.GOOD:      "Adequate business quality — positive foundation with notable areas for improvement.",
        QualityTier.WATCH:     "Mixed quality — insufficient positive signals to support high conviction.",
        QualityTier.CONCERN:   "Material quality concerns — significant financial or qualitative weaknesses identified.",
    }
    base = tier_map.get(quality, f"Quality tier: {quality.value}.")
    top_support = (g2.supporting_evidence or [])[:2]
    top_contra  = (g2.contradictory_evidence or [])[:2]
    extras = []
    if top_support:
        extras.append("Strengths: " + "; ".join(top_support))
    if top_contra:
        extras.append("Concerns: " + "; ".join(top_contra))
    return base + (" " + " | ".join(extras) if extras else "")


def _valuation_conclusion(
    zone: str, valuation: Optional[ValuationAssessment], g3: GateResult,
) -> str:
    if valuation is None:
        return "Valuation not assessed — no intrinsic value estimate available."
    zone_map = {
        "ACCUMULATE":  "Price offers a compelling margin of safety — valuation is attractive.",
        "START_SMALL": "Price is in the attractive entry range — valuation supports cautious initiation.",
        "WATCH":       "Price is approaching fair value but not yet compelling for accumulation.",
        "WAIT":        "Price is at or above estimated fair value — patient observation warranted.",
    }
    base = zone_map.get(zone, f"Valuation zone: {zone}.")
    vc = valuation.overall_confidence.value if valuation.overall_confidence else "Medium"
    return f"{base} Valuation confidence: {vc}. Methods applicable: {len(valuation.applicable_methods())}."


def _portfolio_conclusion(
    is_existing: bool,
    portfolio_ctx,
    g4: GateResult,
) -> str:
    if portfolio_ctx is None:
        return (
            "Portfolio context: not provided. "
            "Analysis proceeds as a new-position evaluation. "
            "No position sizing, concentration, or incremental-scenario data available."
        )
    from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
    if isinstance(portfolio_ctx, WeightOnlyPortfolioContext):
        return (
            f"Existing position: approximately {portfolio_ctx.portfolio_weight_pct:.1f}% of portfolio. "
            f"(Weight-only mode — shares, average cost, and concentration data not provided.)"
        )
    # Full context
    if is_existing:
        return (
            f"Existing holding: {portfolio_ctx.shares_held:,.0f} shares at "
            f"{portfolio_ctx.portfolio_weight_pct:.2f}% of portfolio. "
            f"Average cost excluded from decision (sunk-cost protection). "
            f"Unrealized P/L is context only."
        )
    else:
        return (
            f"{portfolio_ctx.ticker} not currently held. "
            f"START_SMALL preferred per investor philosophy. "
            f"Sector weight: {portfolio_ctx.sector_weight_in_portfolio_pct:.1f}%, "
            f"Geography: {portfolio_ctx.geography_weight_in_portfolio_pct:.1f}%."
        )


def _executive_conclusion(
    ticker: str, company_name: str, action: DecisionAction,
    quality: QualityTier, zone: str,
    is_existing: bool, confidence: DecisionConfidence,
    adversarial: AdversarialRisk,
    qualitative_view: str = "",
) -> str:
    holding_str = "existing holding" if is_existing else "new investment candidate"
    action_map = {
        DecisionAction.START_SMALL:   f"{company_name} ({ticker}) qualifies as a {holding_str}. "
                                       f"Business quality is {quality.value.lower()} and valuation is in the {zone} zone. "
                                       f"Initiate a small position per investor preference to begin gradually.",
        DecisionAction.ACCUMULATE:    f"{company_name} ({ticker}) — {holding_str} with intact thesis. "
                                       f"Quality tier {quality.value}, valuation zone {zone}. "
                                       f"Add to the existing position at current levels.",
        DecisionAction.WATCH:         f"{company_name} ({ticker}) is a {holding_str} that does not yet meet "
                                       f"the entry criteria. "
                                       f"Quality is {quality.value.lower()}; valuation zone is {zone}. "
                                       f"Monitor for a better entry point or clearer thesis resolution.",
        DecisionAction.HOLD:          (
            f"{company_name} ({ticker}) — {holding_str}. "
            + (
                f"SEVERE adversarial risk is present, but the current price provides a valuation buffer "
                f"(zone: {zone}). HOLD while monitoring thesis breakers — do not add, but the margin of "
                f"safety means active reduction is not yet warranted. Business quality: {quality.value}."
                if adversarial == AdversarialRisk.SEVERE else
                f"Thesis remains intact. Quality: {quality.value}. "
                f"No compelling case to add or reduce at current levels."
            )
        ),
        DecisionAction.REDUCE:        (
            f"{company_name} ({ticker}) — REDUCE recommended for {holding_str}. "
            + (
                f"SEVERE adversarial risk has identified credible thesis-breaker conditions. "
                f"Business quality is {quality.value} — the REDUCE is not a quality judgment, "
                f"it reflects unresolved regulatory or structural risk requiring thesis review."
                if adversarial == AdversarialRisk.SEVERE else
                f"Business quality has deteriorated to {quality.value}. "
                f"Reduce position size while monitoring for recovery or further deterioration."
            )
        ),
        DecisionAction.EXIT:          f"{company_name} ({ticker}) — fundamental thesis deterioration warrants exit. "
                                       f"Quality tier: {quality.value}. Adversarial risk: {adversarial.value}. "
                                       f"Exit position and document thesis break for future reference.",
        DecisionAction.WAIT_INSUFFICIENT_EVIDENCE:
                                      f"{company_name} ({ticker}) — insufficient evidence to produce a confident "
                                       f"investment conclusion. Gather additional research before acting.",
        DecisionAction.WATCH_PENDING_DATA:
                                      (
                                          f"{company_name} ({ticker}) — qualitative investment view: "
                                          f"{qualitative_view or 'ACCUMULATE-CANDIDATE'}. "
                                          f"Transactional action suppressed: current price data is STALE or UNKNOWN. "
                                          f"The valuation zone cannot be reliably confirmed at this time. "
                                          f"Business quality: {quality.value}. "
                                          f"Refresh the current market price before acting."
                                      ),
    }
    base = action_map.get(action, f"Action: {action.value}.")
    return f"{base} Decision confidence: {confidence.value}."


def _business_thesis(
    research: Optional[BusinessResearchAssessment],
    quality: QualityTier,
    g2: GateResult,
) -> str:
    if research is None:
        return f"Business thesis cannot be articulated — no research assessment available."
    bu = research.business_understanding
    moat = research.moat_assessment
    growth = research.growth_assessment

    parts = []
    if bu and bu.what_it_does:
        parts.append(f"Business: {bu.what_it_does[:120]}")
    if moat and moat.moat_summary:
        parts.append(f"Moat: {moat.moat_summary[:150]}")
    if growth and growth.growth_sustainability_assessment:
        parts.append(f"Growth: {growth.growth_sustainability_assessment[:120]}")
    if research.business_quality_interpretation:
        parts.append(f"Quality interpretation: {research.business_quality_interpretation[:150]}")

    return " | ".join(parts) if parts else f"Business quality: {quality.value}."


def _build_method_summary(
    valuation: Optional[ValuationAssessment],
    current_price: Optional[float],
    currency: str = "",
) -> List[str]:
    """
    Build a list of human-readable strings, one per applicable valuation method,
    showing bear/mid/bull implied values, reliability, weight, and price comparison.
    Final entry is a weighted-average summary line.

    Only reads existing ValuationAssessment data — no new calculations.
    Returns an empty list when valuation is None or no methods produced results.
    """
    if valuation is None:
        return []

    cur = f"{currency} " if currency else ""
    price_str = f"{cur}{current_price:.2f}" if current_price is not None else "N/A"
    lines: List[str] = []

    def _rel_label(rel) -> str:
        if rel is None:
            return "N/A"
        return rel.value if hasattr(rel, "value") else str(rel)

    def _weight_for(rel) -> float:
        return _RELIABILITY_WEIGHT.get(rel, 0.0) if rel is not None else 0.0

    def _vs_price(mid_val: Optional[float]) -> str:
        """Return a short comparison string vs current price."""
        if mid_val is None or current_price is None:
            return ""
        pct = (mid_val - current_price) / current_price * 100
        direction = "above" if pct > 0 else "below"
        return f" ({abs(pct):.1f}% {direction} current price {price_str})"

    def _fmt_method(name: str, bear, mid, bull, rel, weight: float) -> str:
        bear_s = f"{cur}{bear:.2f}" if bear is not None else "N/A"
        mid_s  = f"{cur}{mid:.2f}"  if mid  is not None else "N/A"
        bull_s = f"{cur}{bull:.2f}" if bull  is not None else "N/A"
        vs = _vs_price(mid)
        return (
            f"{name}: bear {bear_s} | mid {mid_s} | bull {bull_s}"
            f"  [reliability: {_rel_label(rel)}, weight: {weight:.1f}]{vs}"
        )

    # DCF
    dcf = valuation.dcf_result
    if dcf is not None and dcf.is_valid():
        w = _weight_for(dcf.reliability)
        lines.append(_fmt_method(
            "DCF",
            dcf.bear_value, dcf.base_value, dcf.bull_value,
            dcf.reliability, w,
        ))

    # Normalised P/E
    pe = valuation.normalized_pe_result
    if pe is not None and pe.is_valid():
        w = _weight_for(pe.reliability)
        lines.append(_fmt_method(
            "Normalised P/E",
            pe.implied_value_low, pe.implied_value_mid, pe.implied_value_high,
            pe.reliability, w,
        ))

    # EV/EBITDA
    ev = valuation.ev_ebitda_result
    if ev is not None and ev.is_valid():
        w = _weight_for(ev.reliability)
        lines.append(_fmt_method(
            "EV/EBITDA",
            ev.implied_value_low, ev.implied_value_mid, ev.implied_value_high,
            ev.reliability, w,
        ))

    # P/FCF
    pfcf = valuation.price_to_fcf_result
    if pfcf is not None and pfcf.is_valid():
        w = _weight_for(pfcf.reliability)
        lines.append(_fmt_method(
            "P/FCF",
            pfcf.implied_value_low, pfcf.implied_value_mid, pfcf.implied_value_high,
            pfcf.reliability, w,
        ))

    if not lines:
        return []

    # Weighted average summary
    fvr = valuation.fair_value_range
    if fvr is not None:
        base_vs = _vs_price(fvr.base)
        base_s  = f"{cur}{fvr.base:.2f}"  if fvr.base  is not None else "N/A"
        bear_s  = f"{cur}{fvr.bear:.2f}"  if fvr.bear  is not None else "N/A"
        bull_s  = f"{cur}{fvr.bull:.2f}"  if fvr.bull  is not None else "N/A"
        lines.append(
            f"Weighted average fair value: bear {bear_s} | base {base_s} | bull {bull_s}"
            f"{base_vs}"
        )

    return lines


def _recommended_next_step(
    action: DecisionAction,
    is_existing: bool,
    portfolio_ctx: Optional[PortfolioPositionContext],
    thesis_breakers: List[ThesisBreaker],
    val_zone: str = "",
) -> str:
    next_map = {
        DecisionAction.START_SMALL:   (
            "Review the smallest incremental scenario and confirm the position sizing is "
            "appropriate for current portfolio concentration. Record the thesis assumptions "
            "and thesis breakers in the investment journal for longitudinal tracking."
        ),
        DecisionAction.ACCUMULATE:    (
            "Select an incremental amount from the portfolio scenarios. "
            "Confirm no new thesis-breaking information has emerged since last analysis. "
            "Update average cost context after purchase (informational only)."
        ),
        DecisionAction.WATCH:         (
            # Zone WAIT means price > fair value — alert language must reflect that,
            # not mislead the user into thinking a START_SMALL threshold is near.
            (
                "Monitor for a price pullback toward fair value. "
                "The current price is above the estimated fair value range — "
                "wait for a more attractive entry before initiating a position. "
                "Schedule a quarterly review of key thesis assumptions. "
                f"Monitor thesis breaker indicators: "
                f"{'; '.join(t.monitoring_indicator for t in thesis_breakers[:2]) or 'See thesis breakers.'}."
            ) if val_zone == "WAIT" else (
                "Set a price alert at the START_SMALL threshold. "
                "Schedule a quarterly review of the key thesis assumptions. "
                f"Monitor thesis breaker indicators: "
                f"{'; '.join(t.monitoring_indicator for t in thesis_breakers[:2]) or 'See thesis breakers.'}."
            )
        ),
        DecisionAction.HOLD:          (
            "Schedule next review in one quarter. "
            "Monitor key thesis indicators and watch for any deterioration signals. "
            "No portfolio action required at current price."
        ),
        DecisionAction.REDUCE:        (
            "Define the target reduced position size. "
            "Document specific evidence of thesis deterioration. "
            "Reassess at reduced weight: if thesis continues to deteriorate, escalate to EXIT."
        ),
        DecisionAction.EXIT:          (
            "Confirm thesis deterioration is structural, not temporary. "
            "Execute exit in a planned manner (not panic selling). "
            "Document what went wrong for future avoidance. "
            "Reinvest proceeds only after a better opportunity is identified."
        ),
        DecisionAction.WAIT_INSUFFICIENT_EVIDENCE: (
            "Complete the missing research dimensions identified in data_quality_limitations. "
            "Re-run the decision engine once evidence is sufficient. "
            "Do not initiate a position on incomplete information."
        ),
        DecisionAction.WATCH_PENDING_DATA: (
            "Obtain the current market price from a live data source. "
            "Re-run the decision engine with a fresh price to confirm the valuation zone. "
            "Qualitative thesis and fair value estimates remain valid — only the zone "
            "classification requires the updated price."
        ),
    }
    return next_map.get(action, "Review and proceed based on the available evidence.")


# ===========================================================================
# Early stop helper
# ===========================================================================

def _early_stop(
    ticker, company_name, analysis_date,
    price, currency, price_date,
    forced_action: DecisionAction,
    gate_results: List[GateResult],
    reason: str,
    data_gaps: List[str],
    per_method_valuation_summary: Optional[List[str]] = None,
    fcf_per_share_used: Optional[float] = None,
    fcf_normalization_note: str = "",
    eps_used_in_valuation: Optional[float] = None,
    eps_normalization_note: str = "",
    fcf_annual_breakdown: Optional[List[dict]] = None,
    fcf_shares_outstanding: Optional[float] = None,
) -> InvestmentDecisionAssessment:
    return InvestmentDecisionAssessment(
        ticker=ticker,
        company_name=company_name,
        analysis_date=analysis_date,
        current_price=price,
        price_currency=currency,
        price_date=price_date,
        action=forced_action,
        decision_confidence=DecisionConfidence.LOW,
        executive_conclusion=reason,
        business_thesis="Cannot be assessed — see data_quality_limitations.",
        gate_results=gate_results,
        why_attractive_or_unattractive="Cannot assess — insufficient evidence.",
        biggest_reason_to_invest="N/A — evidence insufficient.",
        biggest_reason_not_to_invest=reason,
        is_current_price_attractive="Cannot assess — no fair value available.",
        appropriate_action_given_portfolio="Gather evidence before taking any action.",
        what_would_change_conclusion="Completion of missing research dimensions.",
        bear_case="Cannot assess — see data gaps.",
        data_quality_limitations=data_gaps,
        research_gaps=data_gaps,
        recommended_next_step=(
            "Complete the missing research dimensions. "
            "Re-run the decision engine once evidence is sufficient."
        ),
        per_method_valuation_summary=per_method_valuation_summary or [],
        # FCF / EPS provenance (Phase 9.5 / 9.9)
        fcf_per_share_used=fcf_per_share_used,
        fcf_normalization_note=fcf_normalization_note,
        eps_used_in_valuation=eps_used_in_valuation,
        eps_normalization_note=eps_normalization_note,
        # FCF annual chain (Phase 9.6)
        fcf_annual_breakdown=fcf_annual_breakdown or [],
        fcf_shares_outstanding=fcf_shares_outstanding,
    )


# ===========================================================================
# Evidence and metadata collectors
# ===========================================================================

def _collect_evidence(
    gates: List[GateResult], supports_thesis: bool,
) -> List[DecisionEvidenceItem]:
    items = []
    phase_map = {1: "business_research", 2: "financial_quality", 3: "valuation", 4: "portfolio", 5: "adversarial"}
    for g in gates:
        source = phase_map.get(g.gate_number, f"gate{g.gate_number}")
        ev_list = g.supporting_evidence if supports_thesis else g.contradictory_evidence
        for obs in (ev_list or [])[:3]:   # max 3 per gate to avoid noise
            if obs:
                items.append(DecisionEvidenceItem(
                    source_phase=source,
                    dimension=g.gate_name,
                    observation=obs[:200],
                    strength=EvidenceStrength.MODERATE,
                    supports_thesis=supports_thesis,
                ))
    return items


def _collect_data_gaps(gates: List[GateResult]) -> List[str]:
    gaps = []
    for g in gates:
        gaps.extend(g.data_gaps or [])
    return list(dict.fromkeys(gaps))[:15]   # dedup, max 15


def _collect_philosophy(gates: List[GateResult], financial_quality=None) -> List[str]:
    """
    Collect all philosophy notes from gates AND surface relevant threshold
    observations from the financial quality assessment.
    """
    notes = []
    for g in gates:
        notes.extend(g.philosophy_notes or [])

    # Surface philosophy-relevant observations from FinancialQualityAssessment
    if financial_quality is not None:
        notes.extend(_philosophy_from_financial_quality(financial_quality))

    return list(dict.fromkeys(notes))[:15]


def _philosophy_from_financial_quality(fq) -> List[str]:
    """
    Derive philosophy-threshold observations from financial quality dimensions.
    These are contextual notes, not rules. They surface relevant data relative
    to the investor's stated philosophy guidelines.
    """
    notes = []
    # Thresholds (must match gate2_quality.py constants)
    ROIC_STRONG       = 15.0
    ROIC_GOOD         = 10.0
    DEBT_GOOD         = 30.0
    DEBT_WATCH        = 50.0
    PAYOUT_MAX        = 70.0
    DIV_YIELD_HIGH    = 6.0
    DIV_YIELD_VERY_HIGH = 8.0

    # ROIC vs philosophy guideline
    if hasattr(fq, "roic") and fq.roic is not None:
        roic = getattr(fq.roic, "avg_5yr", None) or getattr(fq.roic, "current", None)
        if roic is not None:
            if roic >= ROIC_STRONG:
                notes.append(
                    f"ROIC {roic:.1f}% — above the philosophy strong threshold of {ROIC_STRONG:.0f}%. "
                    "Consistent ROIC above cost of capital is a primary quality indicator."
                )
            elif roic >= ROIC_GOOD:
                notes.append(
                    f"ROIC {roic:.1f}% — above the philosophy minimum of {ROIC_GOOD:.0f}% "
                    f"but below the strong threshold of {ROIC_STRONG:.0f}%. Adequate."
                )
            elif roic is not None:
                notes.append(
                    f"ROIC {roic:.1f}% — below the philosophy minimum of {ROIC_GOOD:.0f}%. "
                    "This is a meaningful concern; the business may not be earning above its cost of capital."
                )

    # Debt-to-assets vs philosophy guideline
    if hasattr(fq, "balance_sheet") and fq.balance_sheet is not None:
        bshed = fq.balance_sheet
        # Try to get debt_to_assets from headline or raw metrics
        # The financial quality assessment stores this in the dimension classification
        # We surface the note from the dimension headline
        headline = getattr(bshed, "headline", "") or ""
        # Fall back to raw metrics if available
        if hasattr(fq, "_metrics") and fq._metrics:
            dta = getattr(getattr(fq, "_metrics", None), "debt", None)
            if dta and hasattr(dta, "debt_to_assets_pct") and dta.debt_to_assets_pct is not None:
                pct = dta.debt_to_assets_pct
                if fq.is_financial_institution:
                    notes.append(
                        f"Debt/assets {pct:.0f}% — high leverage is structural for a financial institution "
                        "and is not assessed against the standard philosophy threshold. "
                        "CET1 capital ratio is the relevant metric instead."
                    )
                elif pct <= DEBT_GOOD:
                    notes.append(
                        f"Debt/assets {pct:.0f}% — within the philosophy preferred range (≤{DEBT_GOOD:.0f}%). "
                        "Conservative balance sheet."
                    )
                elif pct <= DEBT_WATCH:
                    notes.append(
                        f"Debt/assets {pct:.0f}% — above preferred (≤{DEBT_GOOD:.0f}%) but below watch threshold ({DEBT_WATCH:.0f}%). Monitor."
                    )
                else:
                    notes.append(
                        f"Debt/assets {pct:.0f}% — above the philosophy watch threshold of {DEBT_WATCH:.0f}%. "
                        "Elevated leverage warrants monitoring."
                    )

    # Dividend yield vs philosophy investigation threshold
    if hasattr(fq, "dividend") and fq.dividend is not None:
        div = fq.dividend
        yield_pct = getattr(div, "headline", "")
        # Try to get yield from the raw dimension or financial quality metrics
        if hasattr(fq, "_metrics") and fq._metrics:
            div_metrics = getattr(getattr(fq, "_metrics", None), "dividend", None)
            if div_metrics:
                y = getattr(div_metrics, "current_yield_pct", None)
                payout = getattr(div_metrics, "payout_ratio_pct", None)
                pays = getattr(div_metrics, "pays_dividend", False)

                if pays and y is not None:
                    if y >= DIV_YIELD_VERY_HIGH:
                        notes.append(
                            f"Dividend yield {y:.1f}% — above the {DIV_YIELD_VERY_HIGH:.0f}% "
                            "very-high threshold. Dividend sustainability requires careful scrutiny."
                        )
                    elif y >= DIV_YIELD_HIGH:
                        notes.append(
                            f"Dividend yield {y:.1f}% — above the philosophy {DIV_YIELD_HIGH:.0f}% "
                            "investigation threshold. Verify that the dividend is covered by FCF "
                            "and that the elevated yield does not signal distress."
                        )
                    else:
                        notes.append(
                            f"Dividend yield {y:.1f}% — below the {DIV_YIELD_HIGH:.0f}% investigation threshold. "
                            "Yield level does not raise a philosophy concern."
                        )
                if pays and payout is not None:
                    if payout > PAYOUT_MAX:
                        notes.append(
                            f"Dividend payout ratio {payout:.0f}% — above the philosophy maximum of {PAYOUT_MAX:.0f}%. "
                            "Dividend may be consuming capital needed for reinvestment or debt service."
                        )
                    else:
                        notes.append(
                            f"Dividend payout ratio {payout:.0f}% — within the philosophy guideline of ≤{PAYOUT_MAX:.0f}%. "
                            "Dividend appears sustainable from an earnings perspective."
                        )

    # FCF quality
    if hasattr(fq, "free_cash_flow") and fq.free_cash_flow is not None:
        fcf_classification = getattr(fq.free_cash_flow, "classification", "")
        headline = getattr(fq.free_cash_flow, "headline", "")
        if fcf_classification in ("Excellent", "Strong"):
            notes.append(
                "FCF quality rated as strong — the business converts earnings to cash reliably. "
                "Strong FCF supports dividend sustainability and reinvestment capacity."
            )
        elif fcf_classification in ("Concern", "High Concern"):
            notes.append(
                "FCF quality is a concern — earnings may not be converting to cash reliably. "
                "Verify that the dividend and capex plans are FCF-covered."
            )

    # Moat — from research but surfaced here for philosophy alignment
    return notes


def _collect_sources(research, financial_quality, valuation, portfolio_ctx) -> List[str]:
    sources = []
    if financial_quality:
        sources.append(f"FinancialQualityAssessment: {getattr(financial_quality, 'ticker', 'N/A')} ({getattr(financial_quality, 'assessment_date', 'N/A')})")
    if research:
        sources.append(f"BusinessResearchAssessment: {research.ticker} ({research.assessment_date})")
        for s in (research.data_sources_used or [])[:3]:
            sources.append(f"  Source: {s}")
    if valuation:
        sources.append(f"ValuationAssessment: {valuation.ticker} ({valuation.valuation_date})")
    from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
    if portfolio_ctx is not None:
        if isinstance(portfolio_ctx, WeightOnlyPortfolioContext):
            sources.append(
                f"PortfolioContext (WEIGHT_ONLY): {portfolio_ctx.ticker} "
                f"— {portfolio_ctx.portfolio_weight_pct:.1f}% of portfolio."
            )
        elif hasattr(portfolio_ctx, "valuation_date"):
            sources.append(f"PortfolioPositionContext: {portfolio_ctx.ticker} ({portfolio_ctx.valuation_date})")
    return sources


def _extract_zone(valuation: Optional[ValuationAssessment]) -> str:
    if valuation and valuation.accumulation_zone:
        return valuation.accumulation_zone.zone.value
    return "WATCH"   # default when no valuation


# ===========================================================================
# Three-way attractiveness helpers (Phase 7.5)
# ===========================================================================

def _valuation_attractiveness_label(zone: str) -> str:
    """
    Maps the valuation zone to a simple attractiveness label.
    This answers: "Is the current price an attractive entry point?"
    """
    return {
        "ACCUMULATE":  "HIGH",
        "START_SMALL": "MODERATE",
        "WATCH":       "LOW",
        "WAIT":        "NEGATIVE",
    }.get(zone, "UNKNOWN")


def _investment_attractiveness_label(
    quality: QualityTier, zone: str, adversarial: AdversarialRisk,
) -> str:
    """
    Combines Business Quality + Valuation Attractiveness → Investment Attractiveness.

    This answers: "Given what I know about the business AND the price,
                   how attractive is this as an investment TODAY?"

    Distinct from Business Quality (which measures the business independently
    of price) and Valuation Attractiveness (which measures price independently
    of business quality).

    Rules:
    - SEVERE adversarial always caps at LOW regardless of BQ or VA
    - CONCERN quality → NEGATIVE (regardless of valuation)
    - WATCH quality → LOW even at cheap valuations
    - GOOD/STRONG/EXCELLENT quality:
        ACCUMULATE zone → HIGH (EXCELLENT/STRONG) or MODERATE (GOOD)
        START_SMALL zone → MODERATE
        WATCH zone → LOW
        WAIT zone → LOW or NEGATIVE (price above FV)
    """
    # Adversarial override
    if adversarial == AdversarialRisk.SEVERE:
        return "LOW"   # Thesis at risk — investment attractiveness capped

    if quality == QualityTier.CONCERN:
        return "NEGATIVE"

    if quality == QualityTier.WATCH:
        return "LOW"

    # Quality is GOOD, STRONG, or EXCELLENT
    if zone == "ACCUMULATE":
        return "HIGH" if quality in (QualityTier.EXCELLENT, QualityTier.STRONG) else "MODERATE"
    elif zone == "START_SMALL":
        return "MODERATE"
    elif zone == "WATCH":
        return "LOW"
    else:  # WAIT
        return "LOW"


def _investment_attractiveness_note(
    quality: QualityTier, zone: str, adversarial: AdversarialRisk,
) -> str:
    """One-line explanation of why Investment Attractiveness is what it is."""
    if adversarial == AdversarialRisk.SEVERE:
        return (
            f"{quality.value} business quality, but SEVERE adversarial risk means "
            "the investment thesis is under material challenge. "
            "Investment attractiveness is capped until thesis risk resolves."
        )
    if quality == QualityTier.CONCERN:
        return "Business quality is at CONCERN level — investment attractiveness is negative regardless of price."
    if quality == QualityTier.WATCH:
        return "Business quality is WATCH — insufficient quality foundation for a positive investment case."

    va = _valuation_attractiveness_label(zone)
    if va == "HIGH":
        return f"{quality.value} business quality combined with HIGH valuation attractiveness ({zone} zone) → strong investment case."
    elif va == "MODERATE":
        return f"{quality.value} business quality + MODERATE valuation attractiveness ({zone} zone) → reasonable entry point."
    elif va == "LOW":
        return f"{quality.value} business quality, but LOW valuation attractiveness ({zone} zone) — wait for better price."
    else:  # NEGATIVE
        return (
            f"{quality.value} business quality, but price is above estimated fair value (WAIT zone). "
            "Good business at the wrong price — monitor for a pullback."
        )


# ===========================================================================
# Price-data suppression helpers (Phase 7.8)
# ===========================================================================

def _price_is_stale_or_unknown(freshness) -> bool:
    """
    Return True when the price data is STALE or UNKNOWN, meaning the
    valuation zone cannot be reliably determined.

    Relies on the DataFreshnessAssessment.  If no freshness object is
    provided we conservatively return False (do not suppress).
    """
    if freshness is None:
        return False
    from analytics.data_freshness import FreshnessStatus
    for item in getattr(freshness, "items", []):
        if item.category == "price" and item.status in (
            FreshnessStatus.STALE, FreshnessStatus.UNKNOWN
        ):
            return True
    return False


def _qualitative_view_label(action: DecisionAction) -> str:
    """
    Qualitative investment view derived from the decision logic output.

    Always populated — regardless of whether price-suppression fires.
    Describes the investment thesis direction (what the fundamentals say)
    rather than the specific transaction instruction.

    Distinct from the final action in two ways:
      1. Uses "-CANDIDATE" suffix to signal qualitative assessment, not order.
      2. START_SMALL and ACCUMULATE both map to ACCUMULATE-CANDIDATE because
         they reflect the same underlying investment thesis; the difference
         between them is only position-sizing, not thesis quality.

    Does not reference average cost, shares, portfolio value, or any
    private portfolio data.
    """
    return {
        DecisionAction.ACCUMULATE:               "ACCUMULATE-CANDIDATE",
        DecisionAction.START_SMALL:              "ACCUMULATE-CANDIDATE",
        DecisionAction.HOLD:                     "HOLD-CANDIDATE",
        DecisionAction.WATCH:                    "WATCH-CANDIDATE",
        DecisionAction.REDUCE:                   "REDUCE-CANDIDATE",
        DecisionAction.EXIT:                     "EXIT-CANDIDATE",
        DecisionAction.WAIT_INSUFFICIENT_EVIDENCE: "INSUFFICIENT-EVIDENCE",
        DecisionAction.WATCH_PENDING_DATA:       "",   # Should not be called with this value
    }.get(action, "")
