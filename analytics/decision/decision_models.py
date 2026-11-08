"""
Investment Decision Models — Phase 7
======================================
Data structures for the Investment Decision Engine.

Architecture boundary:
  This is the FIRST and ONLY phase that produces L3 investment conclusions.
  BUY / SELL / HOLD / ACCUMULATE / EXIT / REDUCE appear here — nowhere else.

Hierarchy:
  L1  Quantitative fact      → Phase 2 / Phase 3
  L2  Qualitative analysis   → Phase 4 / Phase 5 / Phase 6
  L3  Investment conclusion  → Phase 7  ← THIS FILE

Decision philosophy:
  - Hierarchical gates, not weighted scores
  - Quality is the primary filter; valuation is the timing filter
  - Portfolio context sizes the position, never vetoes the decision
  - Average cost is excluded from decision logic (sunk-cost rule)
  - WAIT_INSUFFICIENT_EVIDENCE is a valid and important output
"""

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any


# ---------------------------------------------------------------------------
# Core enums
# ---------------------------------------------------------------------------

class DecisionAction(Enum):
    START_SMALL             = "START_SMALL"
    ACCUMULATE              = "ACCUMULATE"
    WATCH                   = "WATCH"
    HOLD                    = "HOLD"
    REDUCE                  = "REDUCE"
    EXIT                    = "EXIT"
    WAIT_INSUFFICIENT_EVIDENCE = "WAIT_INSUFFICIENT_EVIDENCE"
    WATCH_PENDING_DATA      = "WATCH_PENDING_DATA"  # Price STALE/UNKNOWN — action suppressed


class DecisionConfidence(Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    LOW    = "LOW"


class EvidenceStrength(Enum):
    STRONG   = "STRONG"    # Multiple tier-1 sources, consistent signal
    MODERATE = "MODERATE"  # Some direct evidence, plausible inference
    WEAK     = "WEAK"      # Limited data, extrapolation, speculation


class QualityTier(Enum):
    """Internal quality classification used by Gate 2."""
    EXCELLENT = "EXCELLENT"
    STRONG    = "STRONG"
    GOOD      = "GOOD"
    WATCH     = "WATCH"
    CONCERN   = "CONCERN"


class AdversarialRisk(Enum):
    """Internal thesis-risk level used by Gate 5."""
    LOW      = "LOW"
    MODERATE = "MODERATE"
    HIGH     = "HIGH"
    SEVERE   = "SEVERE"   # One or more thesis breakers are credible


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

@dataclass
class DecisionEvidenceItem:
    """
    A single piece of evidence that influenced the decision.
    Tracks source phase, dimension, confidence, and thesis direction.
    """
    source_phase: str        # "financial_quality" | "business_research" | "valuation" | "portfolio"
    dimension: str           # e.g. "ROIC", "moat", "accumulation_zone", "sector_concentration"
    observation: str         # What was observed
    strength: EvidenceStrength = EvidenceStrength.MODERATE
    supports_thesis: bool = True    # True = bullish; False = bearish

    def to_dict(self) -> dict:
        d = asdict(self)
        d["strength"] = self.strength.value
        return d


@dataclass
class ThesisBreaker:
    """
    A condition that, if it materialised, would invalidate the investment thesis.

    Thesis breakers must be actively researched — not listed as theoretical risks.
    Each breaker specifies:
      - The condition
      - How to monitor for early warning
      - What action to take if triggered

    Phase 11B: likelihood now accepts UNKNOWN when available evidence is
    insufficient to assign LOW, MEDIUM, or HIGH defensibly.
    UNKNOWN ≠ MEDIUM — it means the assessment could not be made.
    For Gate 5 severity, UNKNOWN is treated conservatively as MEDIUM.
    """
    condition: str                    # "What would break the thesis?"
    likelihood: str = "LOW"          # LOW | MEDIUM | HIGH | UNKNOWN
    impact: str = "SEVERE"           # MODERATE | SEVERE | FATAL
    monitoring_indicator: str = ""   # "Watch for X in quarterly filings"
    trigger_action: str = ""         # "Would prompt EXIT / REDUCE review"
    # Phase 11B additions — populated by LLM-backed research:
    evidence: List[str] = field(default_factory=list)
    # Specific quantitative/operational facts supporting the likelihood.
    # e.g. ["Payout ratio 43%", "0 cuts in 10yr", "CAD 8.3B FCF covers 3.4x"]
    likelihood_rationale: str = ""
    # One-line explanation: why this level vs alternatives.
    # For UNKNOWN: what evidence is missing.
    # e.g. "UNKNOWN — no credit-rating outlook or agency evidence in current context"

    # Phase 11B K1: evidence-boundary audit trail.
    # Strings from the LLM's research that referenced data outside the allowed boundary
    # (e.g. 5yr CAGR when only 3yr data was available, carbon prices).
    # Preserved for audit; never promoted to decision-eligible evidence.
    # Empty list for all legacy breakers (backward-compatible default).
    unsupported_evidence: List[str] = field(default_factory=list)

    # Phase 11B P0-1: evidence-separation flag.
    # True  → this item is a generic monitoring condition (moat erosion, valuation
    #          assumption break) that did NOT enter the Gate 5 severity calculation.
    #          It is useful for ongoing monitoring but is NOT a severity-contributing
    #          thesis breaker for the current assessment.
    # False → this item came from the LLM bull/bear analysis or structural risk
    #          assessment and DID contribute to the Gate 5 n_high / n_medium_equiv
    #          severity count.  (Default for all existing breakers.)
    is_monitoring_only: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# Phase 11B: scenario data model
@dataclass
class BreakerOverride:
    """
    User-supplied likelihood override for one thesis breaker in a what-if scenario.
    Never mutates the system baseline.
    """
    condition: str              # matches ThesisBreaker.condition for lookup
    baseline_likelihood: str   # system-assigned (LOW | MEDIUM | HIGH | UNKNOWN)
    user_likelihood: str        # user's scenario assumption (LOW | MEDIUM | HIGH)


@dataclass
class ScenarioResult:
    """
    Output of scenario_engine.run_scenario().
    Baseline values are always read from the original assessment — never mutated.
    """
    overrides: List[BreakerOverride] = field(default_factory=list)
    baseline_adversarial_risk: str = ""
    scenario_adversarial_risk: str = ""
    baseline_action: str = ""
    scenario_action: str = ""
    decision_changed: bool = False
    n_overrides: int = 0
    scenario_note: str = ""  # human-readable summary of what changed


@dataclass
class GateResult:
    """
    Structured output from a single decision gate.
    Gates are evaluated in order 1→5; a gate may force early termination.
    """
    gate_number: int
    gate_name: str
    passed: bool                          # True = gate cleared, proceed to next
    forced_action: Optional[str] = None  # If set, terminates evaluation early
    quality_tier: Optional[str] = None   # Gate 2 output
    adversarial_risk: Optional[str] = None  # Gate 5 output
    # K1 follow-up: structured bear-point count from Gate 5.
    # Set by evaluate_gate5() so scenario analysis never needs to parse summary text.
    #
    # None  → field absent / legacy record predating this field.
    #         _get_bear_count() falls back to summary-string parsing.
    # int   → explicitly set by evaluate_gate5(), including zero (meaning
    #         "assessed and found no bear points").  _get_bear_count() uses
    #         this value directly and does NOT parse the summary string.
    #
    # This sentinel distinction means "structured 0 (zero bear points, confirmed)"
    # and "legacy default (not set)" are unambiguous.
    n_bear: Optional[int] = None
    confidence: str = "MEDIUM"
    summary: str = ""
    supporting_evidence: List[str] = field(default_factory=list)
    contradictory_evidence: List[str] = field(default_factory=list)
    data_gaps: List[str] = field(default_factory=list)
    philosophy_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Master output
# ---------------------------------------------------------------------------

@dataclass
class InvestmentDecisionAssessment:
    """
    Phase 7 master output — the first L3 investment conclusion in the system.

    Combines:
      - FinancialQualityAssessment  (Phase 3)
      - BusinessResearchAssessment  (Phase 4)
      - ValuationAssessment         (Phase 5)
      - PortfolioPositionContext    (Phase 6)

    Answers: "Given business quality, valuation, and portfolio context,
              what action is most consistent with my investment philosophy?"

    This is a DECISION-SUPPORT document. It does not execute trades.
    """
    # --- Identification ---
    ticker: str
    company_name: str
    analysis_date: str
    current_price: Optional[float] = None
    price_currency: str = "CAD"
    price_date: str = ""

    # --- L3 Decision ---
    action: DecisionAction = DecisionAction.WAIT_INSUFFICIENT_EVIDENCE
    decision_confidence: DecisionConfidence = DecisionConfidence.MEDIUM

    # --- Narrative explanation (6 questions from spec) ---
    why_attractive_or_unattractive: str = ""
    biggest_reason_to_invest: str = ""
    biggest_reason_not_to_invest: str = ""
    is_current_price_attractive: str = ""
    appropriate_action_given_portfolio: str = ""
    what_would_change_conclusion: str = ""

    # --- Full narrative ---
    executive_conclusion: str = ""
    business_thesis: str = ""

    # --- Evidence ---
    supporting_evidence: List[DecisionEvidenceItem] = field(default_factory=list)
    contradictory_evidence: List[DecisionEvidenceItem] = field(default_factory=list)

    # --- Gate results (audit trail) ---
    gate_results: List[GateResult] = field(default_factory=list)

    # --- Domain conclusions ---
    business_quality_conclusion: str = ""
    valuation_conclusion: str = ""
    portfolio_context_conclusion: str = ""

    # --- Risk framework ---
    key_risks: List[str] = field(default_factory=list)
    bear_case: str = ""
    thesis_breakers: List[ThesisBreaker] = field(default_factory=list)

    # --- Monitoring ---
    what_would_change_decision: List[str] = field(default_factory=list)
    key_assumptions: List[str] = field(default_factory=list)

    # --- Data quality ---
    data_quality_limitations: List[str] = field(default_factory=list)
    research_gaps: List[str] = field(default_factory=list)

    # --- Philosophy ---
    philosophy_alignment_notes: List[str] = field(default_factory=list)

    # --- Next steps ---
    recommended_next_step: str = ""

    # --- Sources ---
    evidence_sources: List[str] = field(default_factory=list)

    # --- Sunk-cost protection ---
    cost_basis_excluded_note: str = (
        "Average cost / cost basis was explicitly excluded from this decision. "
        "Investment attractiveness is based solely on current business quality, "
        "valuation, and future economics."
    )

    # --- Three-way attractiveness separation (Phase 7.5) ---
    # These are distinct concepts. A GOOD business at an expensive price
    # can have LOW investment attractiveness.
    business_quality_label: str = ""       # EXCELLENT | STRONG | GOOD | WATCH | CONCERN
    valuation_attractiveness_label: str = ""  # HIGH | MODERATE | LOW | NEGATIVE
    investment_attractiveness_label: str = "" # HIGH | MODERATE | LOW | NEGATIVE
    investment_attractiveness_note: str = ""  # One-line explanation of the combination

    # --- Data freshness (Phase 7.5) ---
    data_freshness: Optional[dict] = None  # DataFreshnessAssessment.to_dict()
    data_freshness_cap_applied: bool = False  # True if confidence was capped by staleness

    # --- Valuation zone (Phase 11B) ---
    # The AccumulationZoneLabel that drove action selection in the synthesizer.
    # Stored here so the scenario engine can re-run action selection without
    # re-running the full pipeline.  Empty string when not yet set.
    valuation_zone: str = ""   # e.g. "ACCUMULATE" | "START_SMALL" | "WATCH" | "WAIT"

    # --- Price-data suppression (Phase 7.8) ---
    # When the current market price is STALE or UNKNOWN, transactional purchase/reduction
    # actions (START_SMALL, ACCUMULATE, REDUCE) are suppressed to WATCH_PENDING_DATA.
    # The qualitative investment view (what the action WOULD have been) is preserved here
    # so the fundamental thesis is not lost.
    qualitative_investment_view: str = ""      # e.g. "ACCUMULATE-CANDIDATE"
    price_suppression_applied: bool = False    # True when action was suppressed

    # --- Per-method valuation transparency (Phase 9.4) ---
    # Each entry is a formatted string describing one valuation method:
    # method name, bear/mid/bull implied values, reliability, weight, and
    # a comparison with the current price.  The final entry is a weighted-
    # average summary line.  Empty list when no valuation data is available.
    per_method_valuation_summary: List[str] = field(default_factory=list)

    # --- FCF / EPS provenance (Phase 9.5) ---
    # Sourced directly from ValuationAssessment method results at decision time.
    # These are L2 calculation outputs — no new assumptions are introduced.
    # All three are None when the corresponding valuation method was not run
    # (e.g. negative FCF → P/FCF not applicable).
    #
    # fcf_per_share_used      : FCF/share (local currency) used by the P/FCF method.
    #                           = fcf_normalized (or fcf_ttm) / shares_outstanding.
    #                           From price_to_fcf_result.metric_value.
    # fcf_normalization_note  : Human-readable note describing what FCF figure was
    #                           used and how it was derived (e.g. "3-year average").
    #                           From price_to_fcf_result.normalization_note.
    # eps_used_in_valuation   : Normalised EPS used by the P/E method (per share,
    #                           local currency).  May be a multi-year average, not
    #                           just TTM EPS.  From normalized_pe_result.metric_value.
    # eps_normalization_note  : Human-readable note describing the EPS normalization
    #                           method — e.g. "3-year average of derived EPS" or
    #                           "Using TTM EPS (historical normalization not available)".
    #                           From normalized_pe_result.normalization_note (Phase 9.9).
    fcf_per_share_used: Optional[float] = None
    fcf_normalization_note: str = ""
    eps_used_in_valuation: Optional[float] = None
    eps_normalization_note: str = ""

    # --- FCF annual calculation chain (Phase 9.6) ---
    # Per-year OCF / capex / FCF from CompanyFinancialMetrics.free_cash_flow,
    # forwarded at synthesis time when raw metrics are available.
    # Each dict: {"year": int, "ocf": float, "capex": float, "fcf": float}
    # All values in absolute local-currency units (not scaled).
    # capex is stored as the SIGNED value from yfinance (typically negative).
    # ocf is derived here as fcf - capex (= fcf + |capex| when capex < 0).
    # Empty list when FreeCashFlowMetrics was not provided or had no data.
    #
    # fcf_shares_outstanding : shares used to convert total FCF → FCF/share.
    #                          From DataLoadResult.supplemental["shares_outstanding"].
    #                          None when not available.
    fcf_annual_breakdown: List[dict] = field(default_factory=list)
    fcf_shares_outstanding: Optional[float] = None

    # -----------------------------------------------------------------------

    def is_positive_action(self) -> bool:
        return self.action in (DecisionAction.START_SMALL, DecisionAction.ACCUMULATE)

    def is_negative_action(self) -> bool:
        return self.action in (DecisionAction.REDUCE, DecisionAction.EXIT)

    def requires_more_evidence(self) -> bool:
        return self.action in (
            DecisionAction.WAIT_INSUFFICIENT_EVIDENCE,
            DecisionAction.WATCH_PENDING_DATA,
        )

    def is_price_suppressed(self) -> bool:
        """True if a transactional action was suppressed due to stale/unknown price data."""
        return self.action == DecisionAction.WATCH_PENDING_DATA

    def high_confidence_supporting(self) -> List[DecisionEvidenceItem]:
        return [e for e in self.supporting_evidence
                if e.strength == EvidenceStrength.STRONG]

    def high_confidence_opposing(self) -> List[DecisionEvidenceItem]:
        return [e for e in self.contradictory_evidence
                if e.strength == EvidenceStrength.STRONG]

    def active_thesis_breakers(self) -> List[ThesisBreaker]:
        """Thesis breakers with HIGH likelihood."""
        return [t for t in self.thesis_breakers if t.likelihood == "HIGH"]

    def to_dict(self) -> dict:
        d = {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "analysis_date": self.analysis_date,
            "current_price": self.current_price,
            "price_currency": self.price_currency,
            "price_date": self.price_date,
            "action": self.action.value,
            "decision_confidence": self.decision_confidence.value,
            # 6-question narrative
            "why_attractive_or_unattractive": self.why_attractive_or_unattractive,
            "biggest_reason_to_invest": self.biggest_reason_to_invest,
            "biggest_reason_not_to_invest": self.biggest_reason_not_to_invest,
            "is_current_price_attractive": self.is_current_price_attractive,
            "appropriate_action_given_portfolio": self.appropriate_action_given_portfolio,
            "what_would_change_conclusion": self.what_would_change_conclusion,
            # Full narrative
            "executive_conclusion": self.executive_conclusion,
            "business_thesis": self.business_thesis,
            # Evidence
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "contradictory_evidence": [e.to_dict() for e in self.contradictory_evidence],
            # Gate audit trail
            "gate_results": [g.to_dict() for g in self.gate_results],
            # Domain conclusions
            "business_quality_conclusion": self.business_quality_conclusion,
            "valuation_conclusion": self.valuation_conclusion,
            "portfolio_context_conclusion": self.portfolio_context_conclusion,
            # Risk
            "key_risks": self.key_risks,
            "bear_case": self.bear_case,
            "thesis_breakers": [t.to_dict() for t in self.thesis_breakers],
            # Monitoring
            "what_would_change_decision": self.what_would_change_decision,
            "key_assumptions": self.key_assumptions,
            # Data quality
            "data_quality_limitations": self.data_quality_limitations,
            "research_gaps": self.research_gaps,
            # Philosophy
            "philosophy_alignment_notes": self.philosophy_alignment_notes,
            "cost_basis_excluded_note": self.cost_basis_excluded_note,
            # Next steps
            "recommended_next_step": self.recommended_next_step,
            "evidence_sources": self.evidence_sources,
            # Three-way attractiveness (Phase 7.5)
            "business_quality_label": self.business_quality_label,
            "valuation_attractiveness_label": self.valuation_attractiveness_label,
            "investment_attractiveness_label": self.investment_attractiveness_label,
            "investment_attractiveness_note": self.investment_attractiveness_note,
            # Data freshness (Phase 7.5)
            "data_freshness": self.data_freshness,
            "data_freshness_cap_applied": self.data_freshness_cap_applied,
            # Price-data suppression (Phase 7.8)
            "qualitative_investment_view": self.qualitative_investment_view,
            "price_suppression_applied": self.price_suppression_applied,
            # Per-method valuation transparency (Phase 9.4)
            "per_method_valuation_summary": self.per_method_valuation_summary,
            # FCF / EPS provenance (Phase 9.5 / 9.9)
            "fcf_per_share_used": self.fcf_per_share_used,
            "fcf_normalization_note": self.fcf_normalization_note,
            "eps_used_in_valuation": self.eps_used_in_valuation,
            "eps_normalization_note": self.eps_normalization_note,
            # FCF annual chain (Phase 9.6)
            "fcf_annual_breakdown": self.fcf_annual_breakdown,
            "fcf_shares_outstanding": self.fcf_shares_outstanding,
            # Valuation zone (Phase 11B)
            "valuation_zone": self.valuation_zone,
        }
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")

    def summary_text(self) -> str:
        lines = [
            f"=== Investment Decision: {self.company_name} ({self.ticker}) ===",
            f"Analysis Date: {self.analysis_date}",
        ]
        if self.current_price:
            lines.append(f"Current Price: {self.current_price:.2f} {self.price_currency}")
        lines += [
            f"",
            f"ACTION:     {self.action.value}",
            f"CONFIDENCE: {self.decision_confidence.value}",
            f"",
            f"Executive Conclusion:",
            f"  {self.executive_conclusion}",
            f"",
            f"Why attractive/unattractive: {self.why_attractive_or_unattractive}",
            f"Biggest reason TO invest:    {self.biggest_reason_to_invest}",
            f"Biggest reason NOT to invest:{self.biggest_reason_not_to_invest}",
            f"Is price attractive:         {self.is_current_price_attractive}",
            f"",
            f"Bear case: {self.bear_case}",
            f"",
            f"Thesis breakers ({len(self.thesis_breakers)}):",
        ]
        for t in self.thesis_breakers:
            lines.append(f"  [{t.likelihood}] {t.condition}")
        lines += [
            f"",
            f"Recommended next step: {self.recommended_next_step}",
            f"",
            f"[This is a decision-support document. No automated execution.]",
        ]
        return "\n".join(lines)
