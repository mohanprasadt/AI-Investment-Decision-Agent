"""
Research Orchestrator — Phase 9
================================
Bridges the gap between raw financial data (DataLoadResult) and the
BusinessResearchAssessment required by the Phase 7 decision engine.

Architecture
------------
ResearchOrchestrator receives an injectable `research_executor`:

    research_executor(step_name: str, context: dict) -> Optional[dict]

The executor is called for each research step and returns a raw dict
describing the research for that dimension.  Two executors are provided:

  quantitative_executor   — always returns None (all qualitative dims remain
                            as explicit research gaps → Gate 1 blocks →
                            WAIT_INSUFFICIENT_EVIDENCE)

  AnthropicResearcher     — calls the Anthropic API with the appropriate
                            prompt (implemented separately; NOT in tests)

A pre-written deterministic fixture can also be used as the executor
for regression tests (see tests/test_phase9.py).

Safety invariants (strictly enforced here)
------------------------------------------
1.  The quantitative fallback NEVER manufactures moat, management, industry,
    or business-understanding claims from financial metrics alone.
2.  Missing qualitative dimensions remain None — explicit research gaps.
3.  Gate 1 will block (WAIT_INSUFFICIENT_EVIDENCE) for any ticker that has
    only quantitative data.  This is correct and expected.
4.  No weighted scoring.  No fabricated conclusions.

Injectable executor contract
----------------------------
  Input:  (step_name: str, context: dict) where step_name is one of:
            "business_understanding", "moat_analysis", "industry_analysis",
            "growth_analysis", "management_analysis", "risk_analysis",
            "bull_bear_analysis"
          context contains financial metrics formatted for the prompt.
  Output: dict with keys matching the dimension model, OR None to signal
          "no qualitative research available for this step."
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

log = logging.getLogger(__name__)

# Research model imports
from analytics.business_research.research_models import (
    BusinessResearchAssessment,
    BusinessUnderstandingAssessment,
    UnderstandabilityRating,
    Confidence,
)


# ---------------------------------------------------------------------------
# Quantitative fallback executor
# ---------------------------------------------------------------------------

def quantitative_executor(step_name: str, context: Dict[str, Any]) -> Optional[dict]:
    """
    Executor that returns None for every step.

    Effect: all qualitative dimensions remain None in the assessment.
    Gate 1 will produce WAIT_INSUFFICIENT_EVIDENCE for any ticker run
    through this executor.

    This is the CORRECT behaviour when no qualitative research has been
    performed.  The caller must provide a proper executor (e.g. Anthropic
    API) to get past Gate 1.
    """
    return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class ResearchOrchestrator:
    """
    Builds a BusinessResearchAssessment by calling the injected executor
    for each research dimension.

    Parameters
    ----------
    research_executor : callable, optional
        (step_name, context) → Optional[dict]
        Defaults to quantitative_executor (all dims = None → Gate 1 blocks).
    """

    def __init__(
        self,
        research_executor: Optional[Callable[[str, Dict[str, Any]], Optional[dict]]] = None,
    ) -> None:
        self._executor = research_executor or quantitative_executor

    def build_assessment(
        self,
        ticker: str,
        company_name: str,
        metrics,              # CompanyFinancialMetrics (or None)
        analysis_date: str = "",
    ) -> BusinessResearchAssessment:
        """
        Orchestrate research for `ticker` and return a BusinessResearchAssessment.

        When the executor returns None for a step, that dimension remains None
        in the assessment (an explicit research gap — NOT a fabricated default).

        Parameters
        ----------
        ticker        : stock ticker, e.g. "CNQ.TO"
        company_name  : company display name
        metrics       : CompanyFinancialMetrics from Phase 2/3 (may be None)
        analysis_date : ISO date string for the analysis
        """
        context = self._build_context(ticker, company_name, metrics, analysis_date)

        assessment = BusinessResearchAssessment(
            ticker=ticker,
            company_name=company_name,
            assessment_date=analysis_date,
        )

        # ── Step 1: Business understanding ─────────────────────────────────
        bu_raw = self._executor("business_understanding", context)
        if bu_raw:
            assessment.business_understanding = self._parse_business_understanding(bu_raw)
        else:
            # Minimal fallback — explicitly notes that research is missing.
            # understandability_rating = BORDERLINE so Gate 1 (Case 4) will
            # trigger WAIT_INSUFFICIENT_EVIDENCE when completeness < 30%.
            assessment.business_understanding = BusinessUnderstandingAssessment(
                what_it_does=(
                    f"[Research gap] No qualitative research has been performed for {ticker}. "
                    "Only quantitative financial data is available."
                ),
                understandability_rating=UnderstandabilityRating.BORDERLINE,
                understandability_note=(
                    "Qualitative research not completed. Only quantitative financial data is "
                    "available. Complete business understanding research before proceeding."
                ),
                confidence=Confidence.LOW,
            )

        # ── Steps 2-7: Qualitative dimensions (all remain None if executor returns None) ──
        # IMPORTANT: We never invent a qualitative conclusion from financial metrics.
        # Missing = explicit research gap, not a default value.

        moat_raw = self._executor("moat_analysis", context)
        if moat_raw:
            assessment.moat_assessment = self._parse_moat(moat_raw)
        # else: moat_assessment remains None (research gap)

        industry_raw = self._executor("industry_analysis", context)
        if industry_raw:
            assessment.industry_assessment = self._parse_industry(industry_raw)
        # else: industry_assessment remains None

        growth_raw = self._executor("growth_analysis", context)
        if growth_raw:
            assessment.growth_assessment = self._parse_growth(growth_raw)
        # else: growth_assessment remains None

        management_raw = self._executor("management_analysis", context)
        if management_raw:
            assessment.management_assessment = self._parse_management(management_raw)
        # else: management_assessment remains None

        risk_raw = self._executor("risk_analysis", context)
        if risk_raw:
            assessment.risk_assessment = self._parse_risk(risk_raw)
        # else: risk_assessment remains None

        bull_bear_raw = self._executor("bull_bear_analysis", context)
        if bull_bear_raw:
            assessment.bull_bear = self._parse_bull_bear(bull_bear_raw)
        # else: bull_bear remains None

        # ── Completeness and gaps ───────────────────────────────────────────
        assessment.research_completeness = {
            "business_understanding": assessment.business_understanding is not None,
            "moat_assessment":        assessment.moat_assessment is not None,
            "industry_assessment":    assessment.industry_assessment is not None,
            "growth_assessment":      assessment.growth_assessment is not None,
            "management_assessment":  assessment.management_assessment is not None,
            "risk_assessment":        assessment.risk_assessment is not None,
            "bull_bear":              assessment.bull_bear is not None,
        }

        gaps = []
        if not assessment.moat_assessment:
            gaps.append("Moat assessment not completed — qualitative research required.")
        if not assessment.industry_assessment:
            gaps.append("Industry assessment not completed — qualitative research required.")
        if not assessment.growth_assessment:
            gaps.append("Growth assessment not completed — qualitative research required.")
        if not assessment.management_assessment:
            gaps.append("Management assessment not completed — qualitative research required.")
        if not assessment.risk_assessment:
            gaps.append("Risk assessment not completed — qualitative research required.")
        if not assessment.bull_bear:
            gaps.append("Bull/bear case not completed — qualitative research required.")
        assessment.research_gaps = gaps

        return assessment

    # -----------------------------------------------------------------------
    # Context builder — financial data formatted for the research prompt
    # -----------------------------------------------------------------------

    def _build_context(
        self,
        ticker: str,
        company_name: str,
        metrics,
        analysis_date: str,
    ) -> Dict[str, Any]:
        """
        Build a context dict to pass to the research executor.
        Contains quantitative facts only — no qualitative conclusions.
        """
        ctx: Dict[str, Any] = {
            "ticker": ticker,
            "company_name": company_name,
            "analysis_date": analysis_date,
        }
        if metrics is None:
            return ctx

        try:
            ctx["currency"] = getattr(metrics, "currency", "")
            ctx["current_price"] = getattr(metrics, "current_price", None)
            ctx["market_cap"] = getattr(metrics, "market_cap", None)
            ctx["pe_ratio"] = getattr(metrics, "pe_ratio", None)
            ctx["ev_ebitda"] = getattr(metrics, "ev_ebitda", None)

            rg = getattr(metrics, "revenue_growth", None)
            if rg:
                ctx["revenue_cagr_3yr"] = getattr(rg, "cagr_3yr", None)
                ctx["revenue_cagr_5yr"] = getattr(rg, "cagr_5yr", None)
                ctx["annual_revenues"] = getattr(rg, "annual_revenues", {})

            mg = getattr(metrics, "margins", None)
            if mg:
                ctx["gross_margin"] = getattr(mg, "gross_margin", None)
                ctx["operating_margin"] = getattr(mg, "operating_margin", None)
                ctx["net_margin"] = getattr(mg, "net_margin", None)

            fcf = getattr(metrics, "free_cash_flow", None)
            if fcf:
                ctx["fcf_current"] = getattr(fcf, "fcf_current", None)
                ctx["annual_fcf"] = getattr(fcf, "annual_fcf", {})

            debt = getattr(metrics, "debt", None)
            if debt:
                ctx["total_debt"] = getattr(debt, "interest_bearing_debt", None)
                ctx["net_debt"] = getattr(debt, "net_debt", None)
                ctx["interest_coverage"] = getattr(debt, "interest_coverage", None)

            roic = getattr(metrics, "roic", None)
            if roic:
                ctx["roic_current"] = getattr(roic, "current", None)
                ctx["roic_5yr_avg"] = getattr(roic, "avg_5yr", None)

        except Exception as exc:  # pragma: no cover
            log.warning("Context build error for %s: %s", ticker, exc)

        return ctx

    # -----------------------------------------------------------------------
    # Dimension parsers
    # These parse raw dicts returned by the executor into model objects.
    # They are intentionally minimal — the executor is responsible for
    # producing valid content; the parser just maps it into the model.
    # -----------------------------------------------------------------------

    def _parse_business_understanding(self, raw: dict) -> BusinessUnderstandingAssessment:
        from analytics.business_research.research_models import (
            BusinessUnderstandingAssessment, UnderstandabilityRating, Confidence,
        )
        rating_str = raw.get("understandability_rating", "BORDERLINE").upper()
        try:
            rating = UnderstandabilityRating(rating_str.capitalize())
        except ValueError:
            rating = UnderstandabilityRating.BORDERLINE

        confidence_str = raw.get("confidence", "MEDIUM").capitalize()
        try:
            conf = Confidence(confidence_str)
        except ValueError:
            conf = Confidence.MEDIUM

        return BusinessUnderstandingAssessment(
            what_it_does=raw.get("what_it_does", ""),
            how_it_makes_money=raw.get("how_it_makes_money", ""),
            main_products_services=raw.get("main_products_services", []),
            main_customer_groups=raw.get("main_customer_groups", []),
            revenue_sources=raw.get("revenue_sources", []),
            understandability_rating=rating,
            understandability_note=raw.get("understandability_note", ""),
            confidence=conf,
        )

    def _parse_moat(self, raw: dict):
        from analytics.business_research.research_models import (
            MoatAssessment, MoatStrength, MoatDurability, MoatTrajectory, Confidence,
        )

        def _safe_enum(enum_cls, val, default):
            try:
                return enum_cls(val)
            except (ValueError, KeyError):
                return default

        return MoatAssessment(
            active_sources=raw.get("active_sources", []),
            overall_strength=_safe_enum(MoatStrength, raw.get("overall_strength", "None"), MoatStrength.NONE),
            overall_durability=_safe_enum(MoatDurability, raw.get("overall_durability", "Medium"), MoatDurability.MEDIUM),
            trajectory=_safe_enum(MoatTrajectory, raw.get("trajectory", "Insufficient Data"), MoatTrajectory.INSUFFICIENT_DATA),
            moat_summary=raw.get("moat_summary", ""),
            roic_consistency_note=raw.get("roic_consistency_note", ""),
            confidence=_safe_enum(Confidence, raw.get("confidence", "Medium"), Confidence.MEDIUM),
            research_gaps=raw.get("research_gaps", []),
        )

    def _parse_industry(self, raw: dict):
        from analytics.business_research.research_models import (
            IndustryAssessment, IndustryClassification, Confidence,
        )

        def _safe_enum(enum_cls, val, default):
            try:
                return enum_cls(val)
            except (ValueError, KeyError):
                return default

        return IndustryAssessment(
            industry_name=raw.get("industry_name", ""),
            classification=_safe_enum(IndustryClassification, raw.get("classification", "Neutral"), IndustryClassification.NEUTRAL),
            classification_reasoning=raw.get("classification_reasoning", ""),
            technology_disruption_risk=raw.get("technology_disruption_risk", ""),
            capital_intensity=raw.get("capital_intensity", ""),
            confidence=_safe_enum(Confidence, raw.get("confidence", "Medium"), Confidence.MEDIUM),
        )

    def _parse_growth(self, raw: dict):
        from analytics.business_research.research_models import GrowthAssessment, Confidence
        conf_str = raw.get("confidence", "Medium").capitalize()
        try:
            conf = Confidence(conf_str)
        except ValueError:
            conf = Confidence.MEDIUM
        return GrowthAssessment(
            revenue_growth_quality=raw.get("revenue_growth_quality", ""),
            organic_vs_inorganic=raw.get("organic_vs_inorganic", ""),
            growth_sustainability_assessment=raw.get("growth_sustainability_assessment", ""),
            growth_drivers=raw.get("growth_drivers", []),
            growth_ceiling_risks=raw.get("growth_ceiling_risks", []),
            confidence=conf,
        )

    def _parse_management(self, raw: dict):
        from analytics.business_research.research_models import (
            ManagementAssessment, ManagementRating, Confidence,
        )

        def _safe_enum(enum_cls, val, default):
            try:
                return enum_cls(val)
            except (ValueError, KeyError):
                return default

        return ManagementAssessment(
            overall_rating=_safe_enum(ManagementRating, raw.get("overall_rating", "Insufficient Data"), ManagementRating.INSUFFICIENT_DATA),
            capital_allocation=raw.get("capital_allocation", raw.get("capital_allocation_note", "")),
            management_summary=raw.get("management_summary", ""),
            confidence=_safe_enum(Confidence, raw.get("confidence", "Medium"), Confidence.MEDIUM),
        )

    def _parse_risk(self, raw: dict):
        from analytics.business_research.research_models import RiskAssessment, RiskLevel, Confidence
        def _safe_enum(enum_cls, val, default):
            try:
                return enum_cls(val)
            except (ValueError, KeyError):
                return default
        return RiskAssessment(
            risk_summary=raw.get("risk_summary", raw.get("headline_risk", "")),
            temporary_vs_structural_note=raw.get("temporary_vs_structural_note", ""),
            overall_level=_safe_enum(RiskLevel, raw.get("overall_level", "Moderate"), RiskLevel.MODERATE),
            confidence=_safe_enum(Confidence, raw.get("confidence", "Medium"), Confidence.MEDIUM),
        )

    def _parse_bull_bear(self, raw: dict):
        from analytics.business_research.research_models import BullBearAssessment
        return BullBearAssessment(
            bull_case_title=raw.get("bull_case_title", raw.get("bull_case_headline", "")),
            bull_case_narrative=raw.get("bull_case_narrative", ""),
            bear_case_title=raw.get("bear_case_title", raw.get("bear_case_headline", "")),
            bear_case_narrative=raw.get("bear_case_narrative", ""),
            thesis_breakers=raw.get("thesis_breakers", []),
            devils_advocate_research_note=raw.get("devils_advocate_research_note", ""),
            confirmation_bias_check=raw.get("confirmation_bias_check", ""),
        )
