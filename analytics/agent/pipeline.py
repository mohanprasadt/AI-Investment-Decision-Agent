"""
Investment Analysis Pipeline — Phase 10
========================================
Reusable, callable pipeline extracted from run_agent.py.

Both the CLI (run_agent.py) and the Streamlit UI (conversation/manager.py)
use this single function.  The extraction is behavior-preserving: the same
sequence of steps, the same executor selection logic, and the same fallback
behavior as the original run_agent.py live-fetch path.

The CNR.TO demo path is NOT extracted here — it lives in run_agent.py and
is not needed for the conversational UI, which always uses live data.

Architecture boundary:
  This module is the ONLY place that assembles the full pipeline sequence.
  It does NOT perform analysis itself — it delegates:
    load_ticker()            → DataLoadResult (Phase 2 + 3)
    ResearchOrchestrator     → BusinessResearchAssessment (Phase 4)
    build_valuation_input()  → ValuationInput (Phase 5 input)
    run_valuation()          → ValuationAssessment (Phase 5)
    InvestmentAgent.analyze()→ InvestmentDecisionAssessment (Phase 7)

Returns:
  PipelineResult — always returns, never raises.
  Check .ok / .error before using.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Module-level imports allow tests to patch analytics.agent.pipeline.load_ticker
from analytics.agent.data_loader import load_ticker, describe_load_result

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """
    Output of run_analysis_pipeline().

    Always returned — never raises.  Check .ok before using analytical fields.
    """
    # Success flag
    ok: bool = False
    error: str = ""

    # Pipeline intermediates (populated on success)
    ticker: str = ""
    company_name: str = ""
    analysis_date: str = ""
    current_price: Optional[float] = None
    price_currency: str = ""
    price_date: str = ""

    # The full structured result (source of truth for all follow-ups)
    assessment: Optional[object] = None           # InvestmentDecisionAssessment
    rendered_report: str = ""                      # render_assessment() output

    # Rate-limit flag — set True when Yahoo Finance returned HTTP 429
    # Callers (UI, manager.py) use this to show a specific friendly message
    # instead of a generic error. No retry is performed in the interactive path.
    is_rate_limited: bool = False

    # Research mode (for UI display)
    research_mode: str = "QUANTITATIVE_FALLBACK"  # or "ANTHROPIC"

    # Load diagnostics (for UI data-quality display)
    load_description: str = ""
    data_completeness_pct: float = 0.0

    # FCF chain (carried through for renderer access)
    fcf_raw_metrics: Optional[object] = None
    fcf_shares_outstanding: Optional[int] = None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_analysis_pipeline(
    ticker: str,
    portfolio_weight_pct: Optional[float] = None,
    ignore_portfolio: bool = False,
    price_date: str = "",
    force_refresh: bool = False,
    analysis_date: Optional[str] = None,
) -> PipelineResult:
    """
    Run the full investment analysis pipeline for a live ticker.

    This replicates the live-fetch path from run_agent.py (lines 383–465)
    as a pure function, returning a PipelineResult instead of printing.

    Parameters
    ----------
    ticker              : e.g. "ITC.NS", "CNQ.TO"
    portfolio_weight_pct: Optional portfolio weight in %. None = no context.
    ignore_portfolio    : If True, treat as new position regardless of weight.
    price_date          : ISO date of the price quote. Defaults to today.
    force_refresh       : If True, bypass local yfinance cache.
    analysis_date       : ISO date for analysis. Defaults to today (UTC).

    Returns
    -------
    PipelineResult — always returns, never raises.
    """
    from analytics.agent.research_orchestrator import (
        ResearchOrchestrator, quantitative_executor,
    )
    from analytics.agent.valuation_builder import build_valuation_input
    from analytics.agent.investment_agent import InvestmentAgent
    from analytics.valuation.valuation_synthesizer import run_valuation

    _date = analysis_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _price_date = price_date or _date
    ticker = ticker.strip().upper()

    result = PipelineResult(ticker=ticker, analysis_date=_date)

    # ── Step 1: Load financial data (fail-fast, no retry) ────────────────────
    # Retries belong in the pre-warm script (scripts/prewarm_mvp.py), not here.
    # In the interactive path a 90-second frozen spinner is worse than a clear
    # "rate-limited" message — the user can try again in a minute.
    try:
        load_result = load_ticker(
            ticker=ticker,
            analysis_date=_date,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        result.error = f"Data fetch error: {exc}"
        log.warning("load_ticker raised for %s: %s", ticker, exc)
        return result

    if not load_result.ok:
        _err = load_result.cannot_complete_reason or ""
        if "429" in _err or "Too Many Requests" in _err:
            result.is_rate_limited = True
        result.error = _err
        return result

    result.company_name     = load_result.company_name
    result.current_price    = load_result.current_price
    result.price_currency   = load_result.price_currency
    result.price_date       = _price_date or load_result.price_date or _date
    result.data_completeness_pct = load_result.data_completeness_pct
    result.load_description = describe_load_result(load_result)

    fq        = load_result.financial_quality
    freshness = load_result.freshness

    # ── Step 2: Research executor selection ─────────────────────────────────
    # Same priority logic as run_agent.py lines 406–419.
    research_executor = quantitative_executor
    _api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    _anthropic_available = False
    make_anthropic_researcher = None
    try:
        from analytics.agent.anthropic_researcher import make_anthropic_researcher
        _anthropic_available = True
    except ImportError:
        pass

    if _anthropic_available and _api_key and make_anthropic_researcher is not None:
        _researcher = make_anthropic_researcher(api_key=_api_key)
        if _researcher is not None:
            research_executor = _researcher
            result.research_mode = "ANTHROPIC"
            log.info("Using AnthropicResearcher for %s", ticker)
        else:
            log.info("AnthropicResearcher unavailable — using quantitative fallback for %s", ticker)
    else:
        log.info("Using quantitative fallback for %s (no API key or package)", ticker)

    # ── Step 3: Qualitative research ────────────────────────────────────────
    try:
        orchestrator = ResearchOrchestrator(research_executor=research_executor)
        research = orchestrator.build_assessment(
            ticker=ticker,
            company_name=result.company_name,
            metrics=load_result.metrics,
            analysis_date=_date,
        )
    except Exception as exc:
        log.warning("Research orchestrator failed for %s: %s", ticker, exc)
        research = None

    # ── Step 4: Valuation ───────────────────────────────────────────────────
    valuation = None
    try:
        vi = build_valuation_input(
            load_result=load_result,
            research=research,
            analysis_date=_date,
        )
        valuation = run_valuation(vi)
    except Exception as exc:
        log.warning("Valuation engine error for %s: %s", ticker, exc)

    # ── Step 5: FCF chain ───────────────────────────────────────────────────
    _fcf_raw = None
    _fcf_shr = None
    if load_result.metrics is not None:
        _fcf_raw = getattr(load_result.metrics, "free_cash_flow", None)
        _fcf_shr = (load_result.supplemental or {}).get("shares_outstanding")

    result.fcf_raw_metrics       = _fcf_raw
    result.fcf_shares_outstanding = _fcf_shr

    # ── Step 6: Decision synthesis ───────────────────────────────────────────
    agent = InvestmentAgent()
    try:
        rendered = agent.analyze(
            ticker=ticker,
            company_name=result.company_name,
            analysis_date=_date,
            financial_quality=fq,
            research=research,
            valuation=valuation,
            portfolio_weight_pct=portfolio_weight_pct,
            ignore_portfolio=ignore_portfolio,
            current_price=result.current_price,
            price_currency=result.price_currency,
            price_date=result.price_date,
            freshness=freshness,
            fcf_raw_metrics=_fcf_raw,
            fcf_shares_outstanding=_fcf_shr,
        )
    except Exception as exc:
        result.error = f"Decision synthesis error: {exc}"
        log.error("InvestmentAgent.analyze failed for %s: %s", ticker, exc)
        return result

    result.ok              = True
    result.assessment      = agent.last_assessment
    result.rendered_report = rendered
    return result
