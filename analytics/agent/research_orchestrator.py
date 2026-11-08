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
            assessment.bull_bear = self._parse_bull_bear(bull_bear_raw, context)
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

                # Phase 11B P0-2 corrective (root-cause fix):
                # The normalizer populates cagr_5yr via extract_cagr_from_series()
                # which falls back to the earliest available year when the true 5yr
                # baseline is absent.  For CNQ.TO with 2022-2025 data, this means
                # cagr_5yr = -3.75 (a 3yr CAGR) is returned instead of None.
                # When ctx["revenue_cagr_5yr"] is set to that fallback value,
                # _format_context() emits "revenue_cagr_5yr: -3.75" (not UNAVAILABLE),
                # _5yr_missing evaluates to False, and the post-generation validator
                # never fires — so the LLM's fabricated "5-year CAGR" claim passes
                # through unchecked.
                #
                # K1 fix: use the structured data_years_available field as the
                # authoritative signal — it is set by the normalizer to len(revenue_series)
                # and accurately reflects how many years of historical data are available.
                # The display label substring is retained as a defense-in-depth check
                # (belt-and-suspenders) but is NOT the primary business rule.
                # This eliminates the silent failure mode where cagr_5yr_label is ""
                # (its dataclass default) while data_years_available < 5.
                _cagr_5yr_val   = getattr(rg, "cagr_5yr", None)
                _data_years     = getattr(rg, "data_years_available", 0)
                _cagr_5yr_label = getattr(rg, "cagr_5yr_label", "") or ""
                # Genuine 5yr CAGR: value exists AND at least 5 data-years available
                # AND label does not explicitly override this (defense-in-depth).
                _5yr_genuine    = (
                    _cagr_5yr_val is not None
                    and _data_years >= 5
                    and "[5yr baseline unavailable]" not in _cagr_5yr_label
                )
                ctx["revenue_cagr_5yr"] = _cagr_5yr_val if _5yr_genuine else None

                # Provide accurate period label so the LLM can cite the correct period.
                # e.g. "3yr CAGR: -3.7% (2022→2025)" helps it say "3-year" not "5-year".
                _3yr_label = getattr(rg, "cagr_3yr_label", "") or ""
                if _3yr_label:
                    ctx["revenue_cagr_3yr_label"] = _3yr_label

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

    def _parse_bull_bear(self, raw: dict, context: dict | None = None):
        from analytics.business_research.research_models import BullBearAssessment
        import re as _re_pb
        import logging as _log_pb

        # Phase 11B: thesis_breakers may be array-of-strings (old) or
        # array-of-objects (new schema with likelihood + evidence).
        # We populate both fields for backward compat:
        #   thesis_breakers        — List[str]  (condition text only)
        #   thesis_breaker_details — List[dict] (structured; empty if old format)
        raw_breakers = raw.get("thesis_breakers", [])
        plain: list = []
        details: list = []
        _valid_likelihoods = {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
        for entry in raw_breakers:
            if isinstance(entry, dict):
                condition = entry.get("condition", "")
                likelihood = str(entry.get("likelihood", "UNKNOWN")).upper()
                if likelihood not in _valid_likelihoods:
                    likelihood = "UNKNOWN"
                details.append({
                    "condition": condition,
                    "likelihood": likelihood,
                    "evidence": entry.get("evidence", []),
                    "likelihood_rationale": entry.get("likelihood_rationale", ""),
                })
                plain.append(condition)
            else:
                # Legacy plain-string format — no likelihood evidence available
                plain.append(str(entry))
                # No detail added; gate5 will fall back to MEDIUM for plain strings

        # Phase 11B P0-2 (corrective): post-generation evidence-boundary validation.
        #
        # Purpose: detect and annotate claims that reference metrics the current run
        # did NOT provide in its structured context. The LLM must not silently use
        # training knowledge to reconstruct UNAVAILABLE metrics.
        #
        # This does NOT reject or discard output — it annotates violating strings so
        # analysts can identify fabricated claims.  Violations are also logged at WARNING.
        #
        # Corrective changes vs. original P0-2:
        #   1. Regex now covers plural "years" (original used `year\b` which missed
        #      "5 years", "over 5 years", "Revenue CAGR over 5 years").
        #   2. Field coverage expanded: now also scans likelihood_rationale and
        #      confirmation_bias_check (original only scanned bear/bull narrative + evidence).
        #   3. Added carbon-pricing pattern: $/tonne claims not in structured context.
        _ctx = context or {}
        _ticker = _ctx.get("ticker", "UNKNOWN")

        # ── Pattern 1: 5-year CAGR (fires only when revenue_cagr_5yr was UNAVAILABLE) ──
        _5yr_missing = _ctx.get("revenue_cagr_5yr") is None
        _5yr_re = _re_pb.compile(
            # Singular AND plural years; all common phrasings found in LLM output.
            r"\b(5[\s-]?years?|5yr|five[\s-]?years?)\b.*?CAGR"   # "5-year CAGR", "5 years CAGR"
            r"|CAGR.*?\b(5[\s-]?years?|5yr|five[\s-]?years?)\b"   # "CAGR over 5 years"
            r"|over\s+(?:the\s+)?(?:past\s+)?5\s+years?"          # "over 5 years", "over the past 5 years"
            r"|both\s+3[\s-]?and\s+5[\s-]?year",                  # "both 3- and 5-year periods"
            _re_pb.IGNORECASE,
        )

        # ── Pattern 2: carbon-pricing external fact (always flagged — never in structured context) ──
        # Carbon pricing data ($/tonne, $/t) is never provided in the financial context dict.
        # If it appears in evidence strings it is an external fact, not context evidence.
        _carbon_re = _re_pb.compile(
            r"\$\s*\d[\d,.]*/\s*(?:tonne|ton)\b"                  # "$170/tonne", "$20/t"
            r"|\bcarbon\s+(?:tax|price|levy|cost)\s.*?\$\s*\d"     # "carbon tax of $170"
            r"|\$\s*\d[\d,.]*\s+per\s+(?:tonne|ton)\b",           # "$170 per tonne"
            _re_pb.IGNORECASE,
        )

        def _flag(text: str, field: str, reason: str, label: str) -> str:
            """Annotate text with a DATA-BOUNDARY-VIOLATION prefix and log a warning."""
            if not text:
                return text
            _log_pb.warning(
                "[Phase11B-P0-2] DATA-BOUNDARY-VIOLATION in field '%s' (%s). "
                "Ticker: %s. Snippet: %.120s",
                field, reason, _ticker, text[:120],
            )
            return f"[DATA-BOUNDARY-VIOLATION: {label}] {text}"

        def _scan_5yr(text: str, field: str) -> str:
            if _5yr_missing and text and _5yr_re.search(text):
                return _flag(text, field, "5yr CAGR not in context", "5yr CAGR not in context")
            return text

        def _scan_carbon(text: str, field: str) -> str:
            """Carbon pricing is never in structured context — always flag if found in evidence."""
            if text and _carbon_re.search(text):
                return _flag(text, field, "carbon price not in structured context",
                             "external carbon-pricing claim not in structured context")
            return text

        # Apply scans to narrative fields (5yr CAGR only — carbon is evidence-level claim)
        bear_narrative = _scan_5yr(raw.get("bear_case_narrative", ""),  "bear_case_narrative")
        bull_narrative = _scan_5yr(raw.get("bull_case_narrative", ""),  "bull_case_narrative")
        confirm_bias   = _scan_5yr(raw.get("confirmation_bias_check", ""), "confirmation_bias_check")
        devils_note    = _scan_5yr(raw.get("devils_advocate_research_note", ""), "devils_advocate_research_note")

        # Apply both scans to per-breaker evidence and rationale fields.
        # P0-2 corrective: for evidence[], SEGREGATE violating strings rather than
        # annotating them in-place.  An annotated string that stays in evidence[]
        # is still displayed and treated as trusted evidence downstream (Gate 5,
        # renderer, Decision Trace).  Instead:
        #   - clean strings stay in evidence[]   → trusted, shown in Gate 5 render
        #   - violating strings go to unsupported_evidence[]  → audit record only
        # ThesisBreaker.evidence (built by evaluate_gate5) only receives clean_ev.
        for d in details:
            clean_ev: list = []
            flagged_ev: list = []
            for ev in d.get("evidence", []):
                scanned = _scan_carbon(_scan_5yr(ev, "evidence"), "evidence")
                if scanned.startswith("[DATA-BOUNDARY-VIOLATION"):
                    # Keep the annotated form for audit, but NOT in trusted evidence
                    flagged_ev.append(scanned)
                else:
                    clean_ev.append(ev)   # original clean string
            d["evidence"] = clean_ev
            if flagged_ev:
                # Auditable record of suppressed claims — not passed to ThesisBreaker
                d["unsupported_evidence"] = flagged_ev

            # likelihood_rationale — annotation-in-place is acceptable here since
            # this field is display-only (not fed into evidence arrays or n_bear).
            rat = d.get("likelihood_rationale", "")
            d["likelihood_rationale"] = _scan_5yr(rat, "likelihood_rationale")

        return BullBearAssessment(
            bull_case_title=raw.get("bull_case_title", raw.get("bull_case_headline", "")),
            bull_case_narrative=bull_narrative,
            bear_case_title=raw.get("bear_case_title", raw.get("bear_case_headline", "")),
            bear_case_narrative=bear_narrative,
            thesis_breakers=plain,
            thesis_breaker_details=details,
            devils_advocate_research_note=devils_note,
            confirmation_bias_check=confirm_bias,
        )
