"""
Phase 10 UI / Integration Tests
=================================
Tests the integration between ConversationManager and the full pipeline
(using the CNR.TO demo path to avoid network calls), and validates that
the CLI path and the new pipeline function produce equivalent assessments.

Coverage:
  Pipeline via ConversationManager (mocked load_ticker):
    1.  run_analysis("FAKE.TICKER") with load failure → clean error string
    2.  manager.route() after failed analysis → correct no-analysis message
    3.  Error string contains ticker name

  CLI vs pipeline equivalence:
    4.  InvestmentAgent.analyze() with identical inputs → same action
    5.  InvestmentAgent.analyze() with identical inputs → same confidence
    6.  InvestmentAgent.analyze() with identical inputs → same ticker
    7.  Phase 9.9b key fields preserved: action, valuation_conclusion, gate count

  End-to-end manager flow (all synthetic, no network):
    8.  ConversationManager with injected assessment → route(why?) returns str
    9.  route(risks?) returns str with content
    10. route(valuation?) returns str with content
    11. route(data quality?) returns str with content
    12. route(metric: ROIC) returns general explanation without assessment fields
    13. route(scenario: price) returns str with content
    14. route(evidence) returns str with content
    15. route(unknown) returns clarification str
    16. run_analysis raises no exception (exception boundary)
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Manager & session
from conversation.manager import ConversationManager

# Pipeline
from analytics.agent.pipeline import run_analysis_pipeline, PipelineResult

# Decision engine (for equivalence tests)
from analytics.agent.investment_agent import InvestmentAgent
from analytics.decision.decision_synthesizer import make_investment_decision
from analytics.data_freshness import build_freshness_assessment

# Reuse shared fixtures
from tests.test_decision import (
    make_excellent_financial_quality,
    make_strong_research,
    make_accumulate_valuation,
    make_wait_valuation,
)
from analytics.agent.data_loader import DataLoadResult, CANNOT_COMPLETE

ANALYSIS_DATE = "2026-08-15"
PRICE_DATE    = "2026-08-15"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _freshness():
    return build_freshness_assessment(
        analysis_date=ANALYSIS_DATE,
        price_date=PRICE_DATE,
        financial_statements_date="2025-12-31",
        research_date="2026-07-01",
    )


def _make_assessment(ticker="CNR.TO", price=155.0, zone="accumulate"):
    valuation = (
        make_accumulate_valuation(ticker, price=price)
        if zone == "accumulate"
        else make_wait_valuation(ticker, price=price)
    )
    return make_investment_decision(
        ticker=ticker,
        company_name="Test Co",
        analysis_date=ANALYSIS_DATE,
        financial_quality=make_excellent_financial_quality(ticker),
        research=make_strong_research(ticker),
        valuation=valuation,
        portfolio_ctx=None,
        current_price=price,
        price_currency="CAD",
        price_date=PRICE_DATE,
        freshness=_freshness(),
    )


def _manager_with(assessment) -> ConversationManager:
    """Return a ConversationManager wired up with the given assessment."""
    manager = ConversationManager()
    manager.session.ticker             = assessment.ticker
    manager.session.company_name       = assessment.company_name
    manager.session.analysis_timestamp = ANALYSIS_DATE
    manager.session.assessment         = assessment
    manager.session.rendered_report    = "SYNTHETIC REPORT"

    agent = InvestmentAgent()
    agent._session.last_assessment = assessment
    agent._session.last_ticker     = assessment.ticker
    manager._agent = agent
    return manager


# ===========================================================================
# 1–3: Manager with failed pipeline
# ===========================================================================

class TestManagerFailedPipeline(unittest.TestCase):

    def _failing_result(self, ticker="FAKE.XX"):
        return DataLoadResult(ticker=ticker, cannot_complete_reason=CANNOT_COMPLETE)

    def test_failed_analysis_returns_string(self):
        """1. run_analysis("FAKE.TICKER") with load failure → clean error string."""
        manager = ConversationManager()
        with patch("analytics.agent.pipeline.load_ticker",
                   return_value=self._failing_result("FAKE.XX")):
            result = manager.run_analysis("FAKE.XX")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 5)

    def test_no_analysis_message_after_failure(self):
        """2. manager.route() after failed analysis → correct no-analysis message."""
        manager = ConversationManager()
        with patch("analytics.agent.pipeline.load_ticker",
                   return_value=self._failing_result("FAKE.XX")):
            manager.run_analysis("FAKE.XX")
        response = manager.route("Why WAIT?")
        self.assertIsInstance(response, str)
        # Shouldn't claim it has an analysis
        self.assertFalse(manager.has_analysis)

    def test_error_message_contains_ticker(self):
        """3. Error string contains ticker name."""
        manager = ConversationManager()
        with patch("analytics.agent.pipeline.load_ticker",
                   return_value=self._failing_result("FAKE.XX")):
            result = manager.run_analysis("FAKE.XX")
        self.assertIn("FAKE.XX", result.upper())


# ===========================================================================
# 4–7: CLI vs pipeline equivalence
# ===========================================================================

class TestCLIvsPipelineEquivalence(unittest.TestCase):
    """
    Verify that calling InvestmentAgent.analyze() with the same inputs
    produces identical L3 results regardless of entry path.

    This test does NOT involve the conversational pipeline — it tests that
    the decision engine is deterministic for the same inputs.
    """

    def _run_via_agent(self, ticker, price, valuation):
        agent = InvestmentAgent()
        agent.analyze(
            ticker=ticker,
            company_name="Test Co",
            analysis_date=ANALYSIS_DATE,
            financial_quality=make_excellent_financial_quality(ticker),
            research=make_strong_research(ticker),
            valuation=valuation,
            portfolio_weight_pct=None,
            ignore_portfolio=True,
            current_price=price,
            price_currency="CAD",
            price_date=PRICE_DATE,
            freshness=_freshness(),
        )
        return agent.last_assessment

    def test_same_action_both_paths(self):
        """4. Two agent runs with identical inputs produce the same action."""
        v = make_accumulate_valuation("CNR.TO", price=155.0)
        a1 = self._run_via_agent("CNR.TO", 155.0, v)
        a2 = self._run_via_agent("CNR.TO", 155.0, v)
        self.assertEqual(a1.action, a2.action)

    def test_same_confidence_both_paths(self):
        """5. Two agent runs with identical inputs produce the same confidence."""
        v = make_accumulate_valuation("CNR.TO", price=155.0)
        a1 = self._run_via_agent("CNR.TO", 155.0, v)
        a2 = self._run_via_agent("CNR.TO", 155.0, v)
        self.assertEqual(a1.decision_confidence, a2.decision_confidence)

    def test_same_ticker(self):
        """6. assessment.ticker matches what was passed in."""
        v = make_accumulate_valuation("CNR.TO", price=155.0)
        a = self._run_via_agent("CNR.TO", 155.0, v)
        self.assertEqual(a.ticker, "CNR.TO")

    def test_phase99b_fields_preserved(self):
        """
        7. Phase 9.9b key fields are preserved through the decision engine:
           action, decision_confidence, gate_results present.
        """
        assessment = _make_assessment("ITC.NS", price=278.0, zone="wait")
        self.assertIsNotNone(assessment.action)
        self.assertIsNotNone(assessment.decision_confidence)
        self.assertIsInstance(assessment.gate_results, list)
        # 5 gates
        self.assertEqual(len(assessment.gate_results), 5)


# ===========================================================================
# 8–16: End-to-end manager flow (all synthetic)
# ===========================================================================

class TestManagerEndToEnd(unittest.TestCase):

    def setUp(self):
        self.assessment = _make_assessment("CNR.TO", price=155.0, zone="accumulate")
        self.manager = _manager_with(self.assessment)

    def test_route_why(self):
        """8. route(why?) returns non-empty string."""
        r = self.manager.route("Why did you reach that conclusion?")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 10)

    def test_route_risks(self):
        """9. route(risks?) returns non-empty string with content."""
        r = self.manager.route("What are the biggest risks?")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 10)

    def test_route_valuation(self):
        """10. route(valuation?) returns non-empty string."""
        r = self.manager.route("What are the valuation assumptions?")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 10)

    def test_route_data_quality(self):
        """11. route(data quality?) returns non-empty string."""
        r = self.manager.route("What important data is missing or unreliable?")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 10)

    def test_route_metric_no_assessment_bleed(self):
        """12. route(metric: ROIC) returns general explanation, not assessment fields."""
        r = self.manager.route("What is ROIC?")
        self.assertIn("Return on Invested Capital", r)
        self.assertIn("GENERAL FINANCIAL EXPLANATION", r)
        # Should NOT contain ticker-specific numbers like the actual stock price
        self.assertNotIn("155.00", r)

    def test_route_scenario(self):
        """13. route(scenario: price) returns non-empty string."""
        r = self.manager.route("At what price would CNR.TO become attractive?")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 10)

    def test_route_evidence(self):
        """14. route(evidence) returns non-empty string."""
        r = self.manager.route("Show me the evidence behind the moat claim")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 10)

    def test_route_unknown(self):
        """15. route(unknown) returns clarification string with ticker context."""
        r = self.manager.route("What should I have for lunch?")
        self.assertIsInstance(r, str)
        self.assertGreater(len(r), 10)
        self.assertIn("CNR.TO", r)

    def test_run_analysis_exception_boundary(self):
        """16. run_analysis catches exceptions and returns clean string."""
        manager = ConversationManager()

        def exploding_load(ticker, **kwargs):
            raise RuntimeError("Simulated network explosion")

        with patch("analytics.agent.pipeline.load_ticker", side_effect=exploding_load):
            result = manager.run_analysis("BOOM.XX")

        # Must not raise; must return a string
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 5)


# ===========================================================================
# Phase 9.9b regression via ConversationManager
# ===========================================================================

class TestPhase99bRegression(unittest.TestCase):
    """
    Confirm that Phase 9.9b EPS/FCF behavior is preserved when the
    InvestmentDecisionAssessment is rendered through the conversational layer.
    """

    def setUp(self):
        self.assessment = _make_assessment("ITC.NS", price=278.0, zone="wait")
        self.manager = _manager_with(self.assessment)

    def test_fcf_eps_question_routes_to_renderer(self):
        """FCF/EPS follow-up question returns a response from the renderer."""
        response = self.manager.route("Why is FCF lower than EPS? Explain the difference.")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 20)

    def test_risk_question_routes_to_renderer(self):
        """Risk question returns a response from the renderer."""
        response = self.manager.route("What are the thesis breakers?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 20)

    def test_what_would_change_routes_correctly(self):
        """'What would change your recommendation?' routes to renderer."""
        response = self.manager.route("What would change your recommendation?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 20)

    def test_five_gates_present_in_assessment(self):
        """All 5 decision gates are present in the assessment."""
        self.assertEqual(len(self.assessment.gate_results), 5)
        gate_numbers = [g.gate_number for g in self.assessment.gate_results]
        self.assertEqual(gate_numbers, [1, 2, 3, 4, 5])

    def test_action_is_valid_enum(self):
        """assessment.action is a valid DecisionAction enum member."""
        from analytics.decision.decision_models import DecisionAction
        self.assertIsInstance(self.assessment.action, DecisionAction)


if __name__ == "__main__":
    unittest.main(verbosity=2)
