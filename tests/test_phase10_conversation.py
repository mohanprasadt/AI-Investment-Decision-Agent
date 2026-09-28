"""
Phase 10 Test Suite — Conversational Layer
============================================
Tests the Phase 10 additions:
  - conversation/session.py   (ConversationSession, ChatTurn)
  - conversation/intent.py    (classify_intent, explain_metric)
  - conversation/manager.py   (ConversationManager)
  - analytics/agent/pipeline.py (run_analysis_pipeline — pipeline only, not network)

All tests are deterministic: no network calls, no yfinance, no Anthropic API.
The pipeline is tested by injecting synthetic fixtures, mirroring the pattern
established in test_agent.py.

Coverage:
  Session:
    1.  ConversationSession initialises with correct defaults
    2.  clear_for_new_ticker() resets analysis fields, preserves weight
    3.  add_turn() appends correctly; role and text preserved
    4.  has_active_analysis() returns False before analysis, True after

  Intent classification (14 intents):
    5.  "Analyze ITC.NS" → INTENT_ANALYZE
    6.  "Analyze CNQ.TO. I hold 4%" → INTENT_ANALYZE
    7.  "Why are you recommending WAIT?" → INTENT_FOLLOW_UP
    8.  "What are the biggest risks?" → INTENT_FOLLOW_UP
    9.  "What is ROIC?" → INTENT_METRIC_EXPLANATION
    10. "Explain FCF conversion" → INTENT_METRIC_EXPLANATION
    11. "What is your source for the moat claim?" → INTENT_EVIDENCE_REQUEST
    12. "Show me the evidence" → INTENT_EVIDENCE_REQUEST
    13. "At what price would this become attractive?" → INTENT_SCENARIO_WHAT_IF
    14. "What if EPS grows 10%?" → INTENT_SCENARIO_WHAT_IF
    15. "What should I cook for dinner?" → INTENT_UNKNOWN_CLARIFICATION
    16. "Hello" → INTENT_UNKNOWN_CLARIFICATION

  Metric explanations:
    17. explain_metric("What is ROIC?") contains "Return on Invested Capital"
    18. explain_metric("What is DCF?") contains "Discounted Cash Flow"
    19. explain_metric("P/E ratio") contains "Price-to-Earnings"
    20. explain_metric("What is EV/EBITDA?") contains "Enterprise Value"
    21. explain_metric("What is P/FCF?") contains "Price-to-Free-Cash-Flow"
    22. All metric explanations end with [GENERAL FINANCIAL EXPLANATION]

  ConversationManager — no active analysis:
    23. route(follow-up) before analysis → no-analysis message
    24. route(unknown) before analysis → help/onboarding message
    25. route(metric explanation) before analysis → general explanation returned

  ConversationManager — with synthetic assessment:
    26. Manager with injected assessment returns follow-up via route()
    27. route("Why WAIT?") → non-empty response (delegates to renderer)
    28. route("What are the risks?") → non-empty response
    29. route("What assumptions…?") → non-empty response
    30. route("What would change the recommendation?") → non-empty response
    31. route("What is ROIC?") → general metric explanation (no assessment fields)
    32. route("Show me the evidence") → evidence/confidence response
    33. route("At what price would this be attractive?") → valuation response
    34. route("What should I cook for dinner?") → unknown clarification (with ticker context)
    35. route("Analyze ITC.NS") in chat → triggers analysis path in manager

  Pipeline (no network — uses mock load_ticker):
    36. run_analysis_pipeline() with failing fetch → PipelineResult.ok == False
    37. PipelineResult.error is non-empty on failure
    38. PipelineResult has expected fields on failure
"""

import sys
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Session
from conversation.session import ConversationSession, ChatTurn

# Intent
from conversation.intent import (
    classify_intent, explain_metric,
    INTENT_ANALYZE, INTENT_FOLLOW_UP,
    INTENT_METRIC_EXPLANATION, INTENT_EVIDENCE_REQUEST,
    INTENT_SCENARIO_WHAT_IF, INTENT_UNKNOWN_CLARIFICATION,
)

# Manager
from conversation.manager import ConversationManager

# Pipeline
from analytics.agent.pipeline import PipelineResult

# Existing test fixtures (reuse from test_decision.py and test_agent.py)
from tests.test_decision import (
    make_excellent_financial_quality,
    make_strong_research,
    make_accumulate_valuation,
    make_wait_valuation,
)
from analytics.decision.decision_synthesizer import make_investment_decision
from analytics.decision.decision_models import DecisionAction, DecisionConfidence
from analytics.data_freshness import build_freshness_assessment
from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext

ANALYSIS_DATE = "2026-08-15"
PRICE_DATE    = "2026-08-15"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_freshness():
    return build_freshness_assessment(
        analysis_date=ANALYSIS_DATE,
        price_date=PRICE_DATE,
        financial_statements_date="2025-12-31",
        research_date="2026-07-01",
    )


def _make_accumulate_assessment(ticker: str = "CNR.TO") -> object:
    """Build a synthetic InvestmentDecisionAssessment in ACCUMULATE zone."""
    return make_investment_decision(
        ticker=ticker,
        company_name="Test Company",
        analysis_date=ANALYSIS_DATE,
        financial_quality=make_excellent_financial_quality(ticker),
        research=make_strong_research(ticker),
        valuation=make_accumulate_valuation(ticker, price=155.0),
        portfolio_ctx=None,
        current_price=155.0,
        price_currency="CAD",
        price_date=PRICE_DATE,
        freshness=_make_freshness(),
    )


def _make_wait_assessment(ticker: str = "ITC.NS") -> object:
    """Build a synthetic InvestmentDecisionAssessment in WAIT / WATCH zone."""
    return make_investment_decision(
        ticker=ticker,
        company_name="ITC Limited",
        analysis_date=ANALYSIS_DATE,
        financial_quality=make_excellent_financial_quality(ticker),
        research=make_strong_research(ticker),
        valuation=make_wait_valuation(ticker, price=278.0),
        portfolio_ctx=None,
        current_price=278.0,
        price_currency="INR",
        price_date=PRICE_DATE,
        freshness=_make_freshness(),
    )


def _manager_with_assessment(assessment) -> ConversationManager:
    """Return a ConversationManager pre-loaded with a synthetic assessment."""
    from analytics.agent.investment_agent import InvestmentAgent
    manager = ConversationManager()
    manager.session.ticker           = assessment.ticker
    manager.session.company_name     = assessment.company_name
    manager.session.analysis_timestamp = ANALYSIS_DATE
    manager.session.assessment       = assessment
    manager.session.rendered_report  = "SYNTHETIC REPORT"

    # Wire up an InvestmentAgent with the assessment in its session
    agent = InvestmentAgent()
    agent._session.last_assessment = assessment
    agent._session.last_ticker     = assessment.ticker
    manager._agent = agent
    return manager


# ===========================================================================
# 1–4: ConversationSession
# ===========================================================================

class TestConversationSession(unittest.TestCase):

    def test_defaults(self):
        """1. ConversationSession initialises with correct defaults."""
        s = ConversationSession()
        self.assertIsNone(s.ticker)
        self.assertIsNone(s.assessment)
        self.assertEqual(s.history, [])
        self.assertFalse(s.has_active_analysis())

    def test_clear_for_new_ticker_resets_analysis_preserves_weight(self):
        """2. clear_for_new_ticker() resets analysis fields, preserves weight."""
        s = ConversationSession()
        s.ticker               = "ITC.NS"
        s.portfolio_weight_pct = 4.1
        s.company_name         = "ITC Limited"
        s.assessment           = object()  # sentinel
        s.rendered_report      = "some report"
        s.history              = [ChatTurn(role="user", text="hello")]

        s.clear_for_new_ticker()

        self.assertIsNone(s.company_name)
        self.assertIsNone(s.assessment)
        self.assertEqual(s.rendered_report, "")
        self.assertEqual(s.history, [])
        # Weight should survive — user doesn't re-enter it after ticker change
        self.assertEqual(s.portfolio_weight_pct, 4.1)

    def test_add_turn_appends(self):
        """3. add_turn() appends correctly; role and text preserved."""
        s = ConversationSession()
        s.add_turn("user", "hello")
        s.add_turn("agent", "hi there", intent=INTENT_FOLLOW_UP)
        self.assertEqual(len(s.history), 2)
        self.assertEqual(s.history[0].role, "user")
        self.assertEqual(s.history[0].text, "hello")
        self.assertEqual(s.history[1].role, "agent")
        self.assertEqual(s.history[1].intent, INTENT_FOLLOW_UP)

    def test_has_active_analysis(self):
        """4. has_active_analysis() returns False before analysis, True after."""
        s = ConversationSession()
        self.assertFalse(s.has_active_analysis())
        s.assessment = object()  # sentinel
        self.assertTrue(s.has_active_analysis())


# ===========================================================================
# 5–16: Intent classification
# ===========================================================================

class TestIntentClassifier(unittest.TestCase):

    def test_analyze_intent(self):
        """5. 'Analyze ITC.NS' → INTENT_ANALYZE."""
        self.assertEqual(classify_intent("Analyze ITC.NS"), INTENT_ANALYZE)

    def test_analyze_with_weight(self):
        """6. 'Analyze CNQ.TO. I hold 4%' → INTENT_ANALYZE."""
        self.assertEqual(classify_intent("Analyze CNQ.TO. I hold 4%"), INTENT_ANALYZE)

    def test_follow_up_why(self):
        """7. 'Why are you recommending WAIT?' → INTENT_FOLLOW_UP."""
        self.assertEqual(classify_intent("Why are you recommending WAIT?"), INTENT_FOLLOW_UP)

    def test_follow_up_risk(self):
        """8. 'What are the biggest risks?' → INTENT_FOLLOW_UP."""
        self.assertEqual(classify_intent("What are the biggest risks?"), INTENT_FOLLOW_UP)

    def test_metric_explanation_roic(self):
        """9. 'What is ROIC?' → INTENT_METRIC_EXPLANATION."""
        self.assertEqual(classify_intent("What is ROIC?"), INTENT_METRIC_EXPLANATION)

    def test_metric_explanation_fcf(self):
        """10. 'Explain FCF conversion' → INTENT_METRIC_EXPLANATION."""
        self.assertEqual(classify_intent("Explain FCF conversion"), INTENT_METRIC_EXPLANATION)

    def test_evidence_source(self):
        """11. 'What is your source for the moat claim?' → INTENT_EVIDENCE_REQUEST."""
        self.assertEqual(
            classify_intent("What is your source for the moat claim?"),
            INTENT_EVIDENCE_REQUEST,
        )

    def test_evidence_show_me(self):
        """12. 'Show me the evidence' → INTENT_EVIDENCE_REQUEST."""
        self.assertEqual(classify_intent("Show me the evidence"), INTENT_EVIDENCE_REQUEST)

    def test_scenario_price(self):
        """13. 'At what price would this become attractive?' → INTENT_SCENARIO_WHAT_IF."""
        self.assertEqual(
            classify_intent("At what price would this become attractive?"),
            INTENT_SCENARIO_WHAT_IF,
        )

    def test_scenario_what_if(self):
        """14. 'What if EPS grows 10%?' → INTENT_SCENARIO_WHAT_IF."""
        self.assertEqual(classify_intent("What if EPS grows 10%?"), INTENT_SCENARIO_WHAT_IF)

    def test_unknown_dinner(self):
        """15. 'What should I cook for dinner?' → INTENT_UNKNOWN_CLARIFICATION."""
        self.assertEqual(
            classify_intent("What should I cook for dinner?"),
            INTENT_UNKNOWN_CLARIFICATION,
        )

    def test_unknown_hello(self):
        """16. 'Hello' → INTENT_UNKNOWN_CLARIFICATION."""
        self.assertEqual(classify_intent("Hello"), INTENT_UNKNOWN_CLARIFICATION)


# ===========================================================================
# 17–22: Metric explanations
# ===========================================================================

class TestMetricExplanations(unittest.TestCase):

    def test_roic_explanation(self):
        """17. explain_metric('What is ROIC?') mentions Return on Invested Capital."""
        result = explain_metric("What is ROIC?")
        self.assertIn("Return on Invested Capital", result)

    def test_dcf_explanation(self):
        """18. explain_metric('What is DCF?') mentions Discounted Cash Flow."""
        result = explain_metric("What is DCF?")
        self.assertIn("Discounted Cash Flow", result)

    def test_pe_explanation(self):
        """19. explain_metric('P/E ratio') mentions Price-to-Earnings."""
        result = explain_metric("What is a P/E ratio?")
        self.assertIn("Price-to-Earnings", result)

    def test_evebitda_explanation(self):
        """20. explain_metric('What is EV/EBITDA?') mentions Enterprise Value."""
        result = explain_metric("What is EV/EBITDA?")
        self.assertIn("Enterprise Value", result)

    def test_pfcf_explanation(self):
        """21. explain_metric('What is P/FCF?') mentions Free-Cash-Flow."""
        result = explain_metric("What is P/FCF?")
        self.assertIn("Free-Cash-Flow", result)

    def test_all_explanations_labelled_general(self):
        """22. All metric explanations end with [GENERAL FINANCIAL EXPLANATION]."""
        for query in [
            "What is ROIC?",
            "What is DCF?",
            "What is a P/E ratio?",
            "What is EV/EBITDA?",
            "What is P/FCF?",
            "What is FCF?",
            "What is margin of safety?",
        ]:
            result = explain_metric(query)
            self.assertIn(
                "GENERAL FINANCIAL EXPLANATION",
                result,
                f"Expected [GENERAL FINANCIAL EXPLANATION] label in: {query!r}",
            )


# ===========================================================================
# 23–25: Manager without active analysis
# ===========================================================================

class TestManagerNoAnalysis(unittest.TestCase):

    def setUp(self):
        self.manager = ConversationManager()

    def test_followup_before_analysis_returns_no_analysis_message(self):
        """23. route(follow-up) before analysis → no-analysis message."""
        response = self.manager.route("Why are you recommending WAIT?")
        # Should not crash; should return a helpful string
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 10)
        # Should NOT contain an investment decision (no analysis was run)
        self.assertNotIn("ACCUMULATE", response)
        self.assertNotIn("START_SMALL", response)

    def test_unknown_before_analysis_returns_onboarding(self):
        """24. route(unknown) before analysis → help / onboarding message."""
        response = self.manager.route("Hello, help me out")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 10)

    def test_metric_explanation_before_analysis(self):
        """25. route(metric explanation) before analysis → general explanation returned."""
        response = self.manager.route("What is ROIC?")
        self.assertIsInstance(response, str)
        self.assertIn("Return on Invested Capital", response)
        self.assertIn("GENERAL FINANCIAL EXPLANATION", response)


# ===========================================================================
# 26–35: Manager with synthetic assessment
# ===========================================================================

class TestManagerWithAssessment(unittest.TestCase):

    def setUp(self):
        self.assessment = _make_wait_assessment("ITC.NS")
        self.manager = _manager_with_assessment(self.assessment)

    def test_assessment_loaded(self):
        """26. Manager with injected assessment is active."""
        self.assertTrue(self.manager.has_analysis)
        self.assertEqual(self.manager.session.ticker, "ITC.NS")

    def test_why_decision(self):
        """27. route('Why are you recommending WAIT?') → non-empty response."""
        response = self.manager.route("Why are you recommending WAIT?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 20)

    def test_risks(self):
        """28. route('What are the risks?') → non-empty response."""
        response = self.manager.route("What are the risks?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 20)

    def test_assumptions(self):
        """29. route('What assumptions drive the fair value?') → non-empty response."""
        response = self.manager.route("What assumptions drive the fair value?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 20)

    def test_what_would_change(self):
        """30. route('What would change the recommendation?') → non-empty response."""
        response = self.manager.route("What would change the recommendation?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 20)

    def test_metric_explanation_with_active_analysis(self):
        """31. route('What is ROIC?') → general metric explanation (not assessment fields)."""
        response = self.manager.route("What is ROIC?")
        self.assertIn("Return on Invested Capital", response)
        self.assertIn("GENERAL FINANCIAL EXPLANATION", response)

    def test_evidence_request(self):
        """32. route('Show me the evidence') → evidence/confidence response."""
        response = self.manager.route("Show me the evidence behind this recommendation")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 20)

    def test_scenario_price(self):
        """33. route('At what price would this be attractive?') → valuation response."""
        response = self.manager.route("At what price would this become attractive?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 20)

    def test_unknown_with_context(self):
        """34. route(unknown) with active analysis → contextual unknown message."""
        response = self.manager.route("What should I cook for dinner?")
        self.assertIsInstance(response, str)
        # Should mention the ticker since analysis is active
        self.assertIn("ITC.NS", response)

    def test_chat_analyze_reroutes_to_pipeline(self):
        """35. route('Analyze CNR.TO') in chat → triggers analysis path."""
        # We mock run_analysis to avoid a real network call
        called_with = {}

        def mock_run_analysis(ticker, **kwargs):
            called_with["ticker"] = ticker
            # Simulate a failed fetch to avoid network access
            return f"MOCK: attempted analysis of {ticker}"

        self.manager.run_analysis = mock_run_analysis
        self.manager.route("Analyze CNR.TO")
        self.assertEqual(called_with.get("ticker"), "CNR.TO")


# ===========================================================================
# 36–38: Pipeline unit tests (no network)
# ===========================================================================

class TestPipeline(unittest.TestCase):

    def test_pipeline_failure_on_bad_ticker(self):
        """36. run_analysis_pipeline() with failing fetch → PipelineResult.ok == False."""
        from analytics.agent.pipeline import run_analysis_pipeline
        from analytics.agent.data_loader import DataLoadResult, CANNOT_COMPLETE

        failing_result = DataLoadResult(
            ticker="FAKE.TICKER",
            cannot_complete_reason=CANNOT_COMPLETE,
        )

        with patch("analytics.agent.pipeline.load_ticker", return_value=failing_result):
            result = run_analysis_pipeline("FAKE.TICKER")

        self.assertFalse(result.ok)

    def test_pipeline_error_message_non_empty(self):
        """37. PipelineResult.error is non-empty on failure."""
        from analytics.agent.pipeline import run_analysis_pipeline
        from analytics.agent.data_loader import DataLoadResult, CANNOT_COMPLETE

        failing_result = DataLoadResult(
            ticker="FAKE.TICKER",
            cannot_complete_reason=CANNOT_COMPLETE,
        )

        with patch("analytics.agent.pipeline.load_ticker", return_value=failing_result):
            result = run_analysis_pipeline("FAKE.TICKER")

        self.assertGreater(len(result.error), 0)

    def test_pipeline_result_fields_on_failure(self):
        """38. PipelineResult has expected fields on failure."""
        from analytics.agent.pipeline import run_analysis_pipeline
        from analytics.agent.data_loader import DataLoadResult, CANNOT_COMPLETE

        failing_result = DataLoadResult(
            ticker="FAKE.TICKER",
            cannot_complete_reason=CANNOT_COMPLETE,
        )

        with patch("analytics.agent.pipeline.load_ticker", return_value=failing_result):
            result = run_analysis_pipeline("FAKE.TICKER")

        self.assertIsInstance(result, PipelineResult)
        self.assertFalse(result.ok)
        self.assertIsNone(result.assessment)
        self.assertEqual(result.rendered_report, "")
        self.assertEqual(result.ticker, "FAKE.TICKER")


# ===========================================================================
# Context retention — conversation continuity across turns
# ===========================================================================

class TestContextRetention(unittest.TestCase):

    def test_context_retained_across_follow_ups(self):
        """
        After analysis, multiple follow-up questions should all route correctly
        without the user re-specifying the ticker.
        """
        assessment = _make_accumulate_assessment("CNR.TO")
        manager = _manager_with_assessment(assessment)

        # Turn 1
        r1 = manager.route("What are the biggest risks?")
        self.assertIsInstance(r1, str)
        self.assertGreater(len(r1), 10)

        # Turn 2 — no ticker mention
        r2 = manager.route("What would change your recommendation?")
        self.assertIsInstance(r2, str)
        self.assertGreater(len(r2), 10)

        # Turn 3 — another follow-up
        r3 = manager.route("How confident are you?")
        self.assertIsInstance(r3, str)
        self.assertGreater(len(r3), 10)

        # All responses should be from the CNR.TO assessment context
        # (manager.session.ticker unchanged)
        self.assertEqual(manager.session.ticker, "CNR.TO")

    def test_history_accumulates(self):
        """Chat history grows with each turn."""
        assessment = _make_accumulate_assessment("CNR.TO")
        manager = _manager_with_assessment(assessment)

        initial_len = len(manager.session.history)
        manager.route("What are the biggest risks?")
        manager.route("What would change the recommendation?")

        # Each route() adds user turn + agent turn = 2 per call
        self.assertEqual(len(manager.session.history), initial_len + 4)

    def test_portfolio_weight_preserved_across_turns(self):
        """Portfolio weight set at analysis time is preserved for follow-ups."""
        assessment = _make_accumulate_assessment("CNR.TO")
        manager = _manager_with_assessment(assessment)
        manager.session.portfolio_weight_pct = 5.0

        manager.route("Why this recommendation?")

        self.assertEqual(manager.session.portfolio_weight_pct, 5.0)


# ===========================================================================
# Regression: existing INTENT_ANALYZE / INTENT_FOLLOW_UP still work
# ===========================================================================

class TestExistingIntentRegression(unittest.TestCase):
    """
    Confirm that the Phase 10 intent classifier does not break the
    existing intent_parser.py ANALYZE / FOLLOW_UP routing.
    """

    def test_analyze_verbs_still_route_to_analyze(self):
        for phrase in [
            "Analyze ITC.NS",
            "Run an analysis of CNQ.TO",
            "Check AAPL for me",
            "Assess TD.TO",
            "Look at CNR.TO",
        ]:
            with self.subTest(phrase=phrase):
                self.assertEqual(classify_intent(phrase), INTENT_ANALYZE, phrase)

    def test_follow_up_keywords_still_route_to_follow_up(self):
        for phrase in [
            "Why did you reach that conclusion?",
            "What are the biggest risks?",
            "Explain the assumptions",
            "What would change the recommendation?",
            "How confident are you?",
            "What about the dividend?",
            "What would you recommend if I hold for 10 years?",
        ]:
            with self.subTest(phrase=phrase):
                self.assertEqual(classify_intent(phrase), INTENT_FOLLOW_UP, phrase)


if __name__ == "__main__":
    unittest.main(verbosity=2)
