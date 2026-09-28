"""
ConversationManager — Phase 10
================================
Routes user input to the correct handler and manages ConversationSession state.

Architecture boundary:
  This module is the thin adapter between the Streamlit UI and InvestmentAgent.
  It does NOT implement investment analysis logic.
  All analysis comes from analytics.agent.pipeline.run_analysis_pipeline().
  All follow-up responses come from InvestmentAgent.chat() → renderer.

Session management:
  ConversationManager owns a ConversationSession and an InvestmentAgent.
  The InvestmentAgent's internal session (AgentSession) is the authoritative
  state for follow-up routing. ConversationSession adds display-layer state
  (chat history, UI metadata) that AgentSession does not hold.

Portfolio privacy:
  Only portfolio_weight_pct (float | None) passes through this layer.
  Shares, average cost, and account value are never requested or stored.

Exception policy:
  All calls to the analytics pipeline are wrapped in try/except.
  Errors produce clean string messages — never tracebacks to the UI.
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

from conversation.session import ConversationSession, ChatTurn
from conversation.intent import (
    classify_intent,
    explain_metric,
    INTENT_ANALYZE,
    INTENT_FOLLOW_UP,
    INTENT_METRIC_EXPLANATION,
    INTENT_EVIDENCE_REQUEST,
    INTENT_SCENARIO_WHAT_IF,
    INTENT_UNKNOWN_CLARIFICATION,
)


# ---------------------------------------------------------------------------
# ConversationManager
# ---------------------------------------------------------------------------

class ConversationManager:
    """
    Single entry point for the Phase 10 conversational UI.

    Usage (from Streamlit app):
        manager = ConversationManager()
        result = manager.run_analysis("ITC.NS", portfolio_weight_pct=4.1)
        response = manager.route("Why are you recommending WAIT?")
    """

    def __init__(self) -> None:
        self.session = ConversationSession()
        self._agent = None          # InvestmentAgent — created lazily after first analysis
        self._last_pipeline_result = None

    # ------------------------------------------------------------------
    # Primary entry points
    # ------------------------------------------------------------------

    def run_analysis(
        self,
        ticker: str,
        portfolio_weight_pct: Optional[float] = None,
        ignore_portfolio: bool = False,
        force_refresh: bool = False,
    ) -> str:
        """
        Run the full investment analysis pipeline for a ticker.

        Replaces the role of run_agent.py for programmatic callers.
        Returns the rendered report string; also updates self.session.

        Parameters
        ----------
        ticker               : e.g. "ITC.NS"
        portfolio_weight_pct : Optional portfolio weight in % (privacy-preserving)
        ignore_portfolio     : If True, treat as new position
        force_refresh        : Force yfinance cache bypass

        Returns
        -------
        Human-readable analysis report string.
        On error, returns a clean error message string (never raises).
        """
        from analytics.agent.pipeline import run_analysis_pipeline
        from analytics.agent.investment_agent import InvestmentAgent

        ticker = ticker.strip().upper()

        # Reset session for the new ticker
        self.session.ticker = ticker
        self.session.portfolio_weight_pct = portfolio_weight_pct
        self.session.clear_for_new_ticker()
        self.session.ticker = ticker  # restore after clear

        try:
            pipeline_result = run_analysis_pipeline(
                ticker=ticker,
                portfolio_weight_pct=portfolio_weight_pct,
                ignore_portfolio=ignore_portfolio,
                force_refresh=force_refresh,
            )
        except Exception as exc:
            error_msg = f"Unexpected pipeline error for {ticker}: {exc}"
            log.error(error_msg)
            self.session.last_error = error_msg
            self.session.add_turn("agent", error_msg, intent="ERROR", response_type="ERROR")
            return error_msg

        self._last_pipeline_result = pipeline_result

        if not pipeline_result.ok:
            error_msg = self._format_pipeline_error(ticker, pipeline_result)
            # Log the raw technical error for diagnostics; never expose it in the UI.
            log.warning(
                "Pipeline failed for %s [is_rate_limited=%s]: %s",
                ticker,
                getattr(pipeline_result, "is_rate_limited", False),
                pipeline_result.error,
            )
            # Store the friendly message — this is what app.py renders via session.last_error.
            self.session.last_error = error_msg
            self.session.add_turn("agent", error_msg, intent="ERROR", response_type="ERROR")
            return error_msg

        # Success — store session state
        self.session.company_name       = pipeline_result.company_name
        self.session.analysis_timestamp = pipeline_result.analysis_date
        self.session.assessment         = pipeline_result.assessment
        self.session.rendered_report    = pipeline_result.rendered_report
        self.session.research_mode      = pipeline_result.research_mode
        self.session.load_description   = pipeline_result.load_description
        self.session.last_error         = None

        # Rebuild InvestmentAgent with the completed assessment in its session
        # so that subsequent chat() calls can use render_followup() correctly.
        self._agent = InvestmentAgent()
        self._agent._session.last_assessment = pipeline_result.assessment
        self._agent._session.last_ticker     = ticker

        self.session.add_turn(
            "agent",
            pipeline_result.rendered_report,
            intent=INTENT_ANALYZE,
            response_type="ANALYSIS",
        )
        return pipeline_result.rendered_report

    def route(self, user_text: str) -> str:
        """
        Route a user message to the correct handler.

        Parameters
        ----------
        user_text : raw user input from the chat box

        Returns
        -------
        Human-readable response string (never raises).
        """
        user_text = user_text.strip()
        if not user_text:
            return "Please type a question or ticker to analyse."

        self.session.add_turn("user", user_text)

        intent = classify_intent(user_text)

        if intent == INTENT_ANALYZE:
            response = self._handle_analyze_from_chat(user_text)
        elif intent == INTENT_FOLLOW_UP:
            response = self._handle_followup(user_text, intent)
        elif intent == INTENT_METRIC_EXPLANATION:
            response = self._handle_metric_explanation(user_text)
        elif intent == INTENT_EVIDENCE_REQUEST:
            response = self._handle_evidence_request(user_text)
        elif intent == INTENT_SCENARIO_WHAT_IF:
            response = self._handle_scenario(user_text)
        else:
            response = self._handle_unknown(user_text)

        self.session.add_turn("agent", response, intent=intent, response_type="FOLLOWUP")
        return response

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    def _handle_analyze_from_chat(self, text: str) -> str:
        """
        Handle 'Analyze TICKER' typed into the chat box.

        Extracts the ticker from text and runs the full pipeline.
        Portfolio context from the current session is preserved unless
        the user provided a new weight in the message.
        """
        from analytics.agent.intent_parser import parse_intent
        intent = parse_intent(text)
        ticker = intent.ticker

        if ticker is None:
            return (
                "I could not identify a ticker symbol in your message. "
                "Please include it — for example: 'Analyze ITC.NS' or 'Analyze CNQ.TO'."
            )

        weight = intent.portfolio_weight_pct or self.session.portfolio_weight_pct
        ignore = intent.ignore_portfolio

        return self.run_analysis(
            ticker=ticker,
            portfolio_weight_pct=weight,
            ignore_portfolio=ignore,
        )

    def _handle_followup(self, text: str, intent: str) -> str:
        """
        Delegate a follow-up question to InvestmentAgent.chat().

        All follow-up rendering is done by renderer.py — no duplication here.
        """
        if self._agent is None or not self.session.has_active_analysis():
            return self._no_analysis_message()

        try:
            return self._agent.chat(text)
        except Exception as exc:
            log.warning("Follow-up routing error: %s", exc)
            return (
                f"I encountered an error answering that question ({exc}). "
                "Try rephrasing, or ask about risks, valuation, assumptions, "
                "or what would change the recommendation."
            )

    def _handle_metric_explanation(self, text: str) -> str:
        """
        Return a general financial term explanation.

        These are clearly labelled as general education, not stock-specific.
        """
        explanation = explain_metric(text)
        if not explanation:
            return (
                "I can explain: ROIC, FCF / FCF conversion, DCF, P/E, "
                "P/FCF, EV/EBITDA, and margin of safety. "
                "Which would you like explained?"
            )

        # If we have an active analysis, offer to apply the concept
        suffix = ""
        if self.session.has_active_analysis() and self.session.ticker:
            suffix = (
                f"\n\nFor {self.session.ticker} specifically, ask: "
                f"'What is the ROIC for {self.session.ticker}?' or "
                f"'How does this apply to the current recommendation?'"
            )
        return explanation + suffix

    def _handle_evidence_request(self, text: str) -> str:
        """
        Route evidence/source requests to the confidence/data-quality renderer.

        The existing renderer handles this through _answer_confidence() and
        _answer_data_quality() — we just ensure the question reaches it.
        """
        if self._agent is None or not self.session.has_active_analysis():
            return self._no_analysis_message()

        try:
            # The renderer's _answer_confidence() covers source/evidence questions.
            # Prefix with a confidence keyword to ensure correct routing.
            augmented = text if any(kw in text.lower() for kw in (
                "confident", "confidence", "certain", "source", "data",
                "limitation", "stale", "fresh", "gap", "uncertain",
            )) else f"How confident are you? {text}"
            return self._agent.chat(augmented)
        except Exception as exc:
            log.warning("Evidence request routing error: %s", exc)
            return self._fallback_followup()

    def _handle_scenario(self, text: str) -> str:
        """
        Route scenario/what-if questions to the renderer.

        "At what price" and "what would change" questions are handled by
        _answer_valuation() and _answer_what_would_change() in renderer.py.
        """
        if self._agent is None or not self.session.has_active_analysis():
            return self._no_analysis_message()

        try:
            return self._agent.chat(text)
        except Exception as exc:
            log.warning("Scenario routing error: %s", exc)
            return self._fallback_followup()

    def _handle_unknown(self, text: str) -> str:
        """Return a friendly clarification prompt."""
        if self.session.has_active_analysis() and self.session.ticker:
            return (
                f"I'm not sure how to answer that in the context of the "
                f"{self.session.ticker} analysis. Here are some things I can help with:\n\n"
                "  • Why did you recommend WAIT / ACCUMULATE / etc.?\n"
                "  • What are the biggest risks?\n"
                "  • Why is P/FCF lower than P/E?\n"
                "  • What assumptions drive the fair value?\n"
                "  • What data is missing or unreliable?\n"
                "  • What would change your recommendation?\n"
                "  • At what price would this become attractive?\n"
                "  • What is ROIC / FCF / DCF? (general explanation)"
            )
        return (
            "I'm an investment decision support agent. Here's how to get started:\n\n"
            "  1. Enter a ticker in the analysis panel (e.g. ITC.NS, CNQ.TO, AAPL)\n"
            "  2. Click 'Analyse' to run the full investment pipeline\n"
            "  3. Ask follow-up questions in this chat\n\n"
            "Or type 'Analyze ITC.NS' directly in this chat box."
        )

    # ------------------------------------------------------------------
    # Convenience accessors for the UI
    # ------------------------------------------------------------------

    @property
    def last_assessment(self):
        """The most recent InvestmentDecisionAssessment, or None."""
        return self.session.assessment

    @property
    def has_analysis(self) -> bool:
        return self.session.has_active_analysis()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _no_analysis_message(self) -> str:
        return (
            "I don't have an analysis loaded yet. "
            "Enter a ticker in the analysis panel above and click 'Analyse', "
            "or type 'Analyze ITC.NS' here to start."
        )

    def _fallback_followup(self) -> str:
        return (
            "I had trouble routing that question. Try asking about: "
            "risks, assumptions, fair value, what would change the recommendation, "
            "or data quality."
        )

    @staticmethod
    def _format_pipeline_error(ticker: str, pipeline_result) -> str:
        """Format a pipeline error into a friendly UI message.

        Accepts either a PipelineResult object (preferred, carries is_rate_limited)
        or a plain error string (legacy call-sites in tests).
        """
        # Support both PipelineResult objects and plain error strings
        if isinstance(pipeline_result, str):
            error = pipeline_result
            is_rate_limited = "429" in error or "Too Many Requests" in error
        else:
            error = getattr(pipeline_result, "error", "") or ""
            is_rate_limited = getattr(pipeline_result, "is_rate_limited", False)

        # ── 429 / rate-limit ───────────────────────────────────────────────
        if is_rate_limited:
            return (
                f"Live data could not be retrieved for **{ticker}** because "
                "market data sources are temporarily limiting requests.\n\n"
                "This ticker does not currently have usable cached data, "
                "so the analysis cannot proceed right now.\n\n"
                "**What to do:**\n"
                "- Wait 2–3 minutes and try again\n"
                "- Select a ticker that already has cached data "
                "(look for the ✅ badge in the Data status panel)\n"
                "- Use the pre-warm script (`scripts/prewarm_mvp.py`) before "
                "a demo session to cache all tickers in advance"
            )

        # ── Ticker not found / no data ─────────────────────────────────────
        if "CANNOT_COMPLETE" in error or "not found" in error.lower():
            return (
                f"Market data could not be retrieved for **{ticker}**. "
                "Please check that the ticker symbol is correct "
                "(e.g. ITC.NS, CNQ.TO, AMZN) and try again."
            )

        # ── Network error ──────────────────────────────────────────────────
        if "network" in error.lower() or "connection" in error.lower():
            return (
                f"A network error prevented data retrieval for **{ticker}**. "
                "Please check your internet connection and try again."
            )

        # ── Fallback — do not expose raw exception/stack details ───────────
        return (
            f"Live data could not be retrieved for **{ticker}** at this time. "
            "Please try again in a moment. "
            "If the problem persists, check your network connection or select "
            "a ticker with cached data."
        )
