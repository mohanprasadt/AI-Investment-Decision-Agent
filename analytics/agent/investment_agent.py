"""
InvestmentAgent — Phase 8
==========================
Thin conversational/orchestration layer over the Phase 1–7.8 analytical pipeline.

Architecture:
  - parse_intent()            → Intent (analytics.agent.intent_parser)
  - make_investment_decision() → InvestmentDecisionAssessment (analytics.decision.decision_synthesizer)
  - render_assessment()        → str (analytics.agent.renderer)
  - render_followup()          → str (analytics.agent.renderer)

This class holds per-session state (last assessment, last ticker, portfolio mode).
It does NOT run analysis itself — all L3 conclusions come from make_investment_decision().

Portfolio privacy rules enforced:
  - InvestmentAgent accepts only portfolio_weight_pct (0.0–100.0).
  - It never requests, stores, or infers: shares, average cost, account value,
    purchase price, other holdings, or transaction history.
  - When the user says "without my portfolio", ignore_portfolio=True → no context.

Usage example (interactive)::

    agent = InvestmentAgent()
    print(agent.chat("Analyze CNR.TO"))
    print(agent.chat("Why did you reach that conclusion?"))
"""

from __future__ import annotations

from typing import Optional
from dataclasses import dataclass, field

from analytics.agent.intent_parser import parse_intent, Intent, INTENT_ANALYZE, INTENT_FOLLOW_UP
from analytics.agent.renderer import render_assessment, render_followup
from analytics.decision.decision_models import InvestmentDecisionAssessment
from analytics.decision.decision_synthesizer import make_investment_decision


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

@dataclass
class AgentSession:
    """
    Holds the state for one conversation session.
    Cleared when a new analysis is started.
    """
    last_assessment: Optional[InvestmentDecisionAssessment] = None
    last_ticker: Optional[str] = None
    portfolio_mode: str = "NONE"          # "NONE" | "WEIGHT_ONLY"
    # Raw pipeline inputs cached so re-runs after "ignore portfolio" are instant
    _cached_inputs: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# InvestmentAgent
# ---------------------------------------------------------------------------

class InvestmentAgent:
    """
    One-stop entry point for the Phase 8 conversational interface.

    chat(text) → str
        Parse the user message, route to analysis or follow-up, return human text.

    analyze(ticker, ...) → str
        Run the pipeline directly (programmatic use / testing).

    last_assessment → InvestmentDecisionAssessment | None
        Access the structured result of the most recent analysis (for tests).
    """

    def __init__(self) -> None:
        self._session = AgentSession()

    # ------------------------------------------------------------------
    # Public: conversational entry point
    # ------------------------------------------------------------------

    def chat(self, text: str) -> str:
        """
        Accept free-text user input, route to analysis or follow-up.

        Parameters
        ----------
        text : raw user message

        Returns
        -------
        Human-readable response string.
        """
        intent = parse_intent(text)

        if intent.intent_type == INTENT_ANALYZE:
            return self._handle_analyze(intent)

        if intent.intent_type == INTENT_FOLLOW_UP:
            return self._handle_followup(text)

        # INTENT_UNKNOWN
        return self._help_text()

    # ------------------------------------------------------------------
    # Public: direct programmatic analysis
    # ------------------------------------------------------------------

    def analyze(
        self,
        ticker: str,
        company_name: str,
        analysis_date: str,
        *,
        financial_quality=None,
        research=None,
        valuation=None,
        portfolio_weight_pct: Optional[float] = None,
        ignore_portfolio: bool = False,
        current_price: Optional[float] = None,
        price_currency: str = "CAD",
        price_date: str = "",
        freshness=None,
        fcf_raw_metrics=None,        # Phase 9.6: FreeCashFlowMetrics for annual OCF/capex/FCF
        fcf_shares_outstanding=None, # Phase 9.6: shares outstanding for FCF/share attribution
    ) -> str:
        """
        Run the full pipeline and return a human-readable report.

        This is the programmatic counterpart to chat().  Tests and
        integration scripts should call this method directly.

        Parameters
        ----------
        ticker            : e.g. "CNR.TO"
        company_name      : Display name
        analysis_date     : ISO date, e.g. "2026-08-09"
        financial_quality : Phase 3 FinancialQualityAssessment (optional)
        research          : Phase 4 BusinessResearchAssessment (optional)
        valuation         : Phase 5 ValuationAssessment (optional)
        portfolio_weight_pct : Portfolio weight in % (0–100). None → no context.
        ignore_portfolio  : If True, treat as new position regardless of weight.
        current_price     : Market price (if not in valuation object)
        price_currency    : Currency code
        price_date        : Date of the price quote (ISO string)
        freshness         : Phase 7.5 DataFreshnessAssessment (optional)
        fcf_raw_metrics   : Phase 9.6 FreeCashFlowMetrics (optional) for annual chain
        fcf_shares_outstanding : Phase 9.6 shares count (optional) for FCF/share chain

        Returns
        -------
        Human-readable assessment report.
        """
        portfolio_ctx, portfolio_mode = _build_portfolio_ctx(
            ticker, portfolio_weight_pct, ignore_portfolio
        )

        # Cache raw inputs so follow-up "ignore portfolio" re-runs are instant
        self._session._cached_inputs = dict(
            ticker=ticker,
            company_name=company_name,
            analysis_date=analysis_date,
            financial_quality=financial_quality,
            research=research,
            valuation=valuation,
            current_price=current_price,
            price_currency=price_currency,
            price_date=price_date,
            freshness=freshness,
        )

        assessment = make_investment_decision(
            ticker=ticker,
            company_name=company_name,
            analysis_date=analysis_date,
            financial_quality=financial_quality,
            research=research,
            valuation=valuation,
            portfolio_ctx=portfolio_ctx,
            current_price=current_price,
            price_currency=price_currency,
            price_date=price_date,
            freshness=freshness,
            fcf_raw_metrics=fcf_raw_metrics,
            fcf_shares_outstanding=fcf_shares_outstanding,
        )

        self._session.last_assessment = assessment
        self._session.last_ticker = ticker
        self._session.portfolio_mode = portfolio_mode

        return render_assessment(assessment, portfolio_mode=portfolio_mode)

    # ------------------------------------------------------------------
    # Public: expose last structured assessment (for tests / integration)
    # ------------------------------------------------------------------

    @property
    def last_assessment(self) -> Optional[InvestmentDecisionAssessment]:
        """The structured InvestmentDecisionAssessment from the most recent run."""
        return self._session.last_assessment

    @property
    def last_ticker(self) -> Optional[str]:
        return self._session.last_ticker

    # ------------------------------------------------------------------
    # Internal routing
    # ------------------------------------------------------------------

    def _handle_analyze(self, intent: Intent) -> str:
        """
        Route an INTENT_ANALYZE to the pipeline.

        If the ticker matches the cached session and only the portfolio
        context changed, re-run cheaply from the cached inputs.
        """
        ticker = intent.ticker
        if ticker is None:
            return "I could not identify a ticker symbol. Please include it, e.g. 'Analyze CNR.TO'."

        cached = self._session._cached_inputs

        # If ticker matches and we have cached inputs, re-use them.
        # GUARD: if the message contains no explicit analyze verb (e.g. "run", "analyze",
        # "check") it is a conceptual question about the already-analyzed ticker, not a
        # genuine re-analysis request.  Route to the follow-up handler so it can answer
        # from the stored assessment or explicitly state that new research is required.
        if cached and cached.get("ticker") == ticker and not intent.has_analyze_verb:
            return self._handle_followup(intent.raw_text)

        if cached and cached.get("ticker") == ticker:
            portfolio_ctx, portfolio_mode = _build_portfolio_ctx(
                ticker,
                intent.portfolio_weight_pct,
                intent.ignore_portfolio,
            )
            assessment = make_investment_decision(
                ticker=ticker,
                company_name=cached["company_name"],
                analysis_date=cached["analysis_date"],
                financial_quality=cached.get("financial_quality"),
                research=cached.get("research"),
                valuation=cached.get("valuation"),
                portfolio_ctx=portfolio_ctx,
                current_price=cached.get("current_price"),
                price_currency=cached.get("price_currency", "CAD"),
                price_date=cached.get("price_date", ""),
                freshness=cached.get("freshness"),
            )
            self._session.last_assessment = assessment
            self._session.last_ticker = ticker
            self._session.portfolio_mode = portfolio_mode
            return render_assessment(assessment, portfolio_mode=portfolio_mode)

        # No cached inputs → return a friendly prompt asking for data
        return (
            f"I understand you want to analyze {ticker}.\n\n"
            f"To run the full pipeline, call agent.analyze() directly with the\n"
            f"pre-built FinancialQualityAssessment, BusinessResearchAssessment,\n"
            f"ValuationAssessment, and DataFreshnessAssessment objects.\n\n"
            f"  agent.analyze(\n"
            f"      ticker='{ticker}',\n"
            f"      company_name='...',\n"
            f"      analysis_date='2026-08-09',\n"
            f"      financial_quality=fq,\n"
            f"      research=research,\n"
            f"      valuation=valuation,\n"
            f"      freshness=freshness,\n"
            f"  )\n\n"
            f"Or call agent.analyze() once with all inputs — subsequent 'ignore portfolio'\n"
            f"or same-ticker requests are handled from the session cache."
        )

    def _handle_followup(self, text: str) -> str:
        """Route a follow-up question to the renderer using the stored assessment."""
        if self._session.last_assessment is None:
            return (
                "I don't have an analysis in memory yet. "
                "Start with something like 'Analyze CNR.TO' and I'll run the full pipeline first."
            )
        return render_followup(text, self._session.last_assessment)

    @staticmethod
    def _help_text() -> str:
        return (
            "I'm not sure what you'd like to do. Here are some examples:\n\n"
            "  Analyze CNR.TO\n"
            "  Analyze CNR.TO. I currently hold 5% of my portfolio.\n"
            "  Analyze CNR.TO without considering my portfolio.\n"
            "  Why did you reach that conclusion?\n"
            "  What are the biggest risks?\n"
            "  What would change the recommendation?\n"
            "  What assumptions did you make on valuation?\n"
        )


# ---------------------------------------------------------------------------
# Portfolio context helper
# ---------------------------------------------------------------------------

def _build_portfolio_ctx(
    ticker: str,
    portfolio_weight_pct: Optional[float],
    ignore_portfolio: bool,
):
    """
    Build a WeightOnlyPortfolioContext (or None) from the intent fields.

    Returns
    -------
    (portfolio_ctx, portfolio_mode_str)
      portfolio_ctx   : WeightOnlyPortfolioContext | None
      portfolio_mode_str : "WEIGHT_ONLY" | "NONE"

    Privacy guarantee:
      Only portfolio_weight_pct is accepted.  Average cost, shares, and
      account value are never requested, stored, or passed to the pipeline.
    """
    if ignore_portfolio or portfolio_weight_pct is None:
        return None, "NONE"

    from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
    ctx = WeightOnlyPortfolioContext(
        ticker=ticker,
        portfolio_weight_pct=portfolio_weight_pct,
    )
    return ctx, "WEIGHT_ONLY"
