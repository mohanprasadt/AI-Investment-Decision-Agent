"""
Phase 9.1 Tests — Live Anthropic Research Executor
====================================================
Tests are grouped into 8 categories (A–H):

A. API key missing → AnthropicResearcher returns None; pipeline uses quantitative fallback
B. Successful structured response → parsed correctly into research dimensions
C. Malformed JSON response → None returned; no exception raised
D. Missing required evidence → result with empty evidence accepted; gaps flagged
E. Research gaps → gaps propagate through orchestrator to assessment.research_gaps
F. Executor injection → AnthropicResearcher can be injected into ResearchOrchestrator
G. CNQ deterministic unchanged → quantitative_executor still produces WAIT_INSUFFICIENT_EVIDENCE
H. Portfolio privacy unchanged → no shares, cost, total value requested or stored

All tests are deterministic — no network calls, no Anthropic API calls are made.
The Anthropic client is mocked at the anthropic.Anthropic level.
"""

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.business_research.research_models import (
    BusinessResearchAssessment,
    BusinessUnderstandingAssessment,
    UnderstandabilityRating,
    Confidence,
    MoatStrength,
)
from analytics.decision.decision_models import DecisionAction
from analytics.decision.gate1_understanding import evaluate_gate1
from analytics.agent.research_orchestrator import ResearchOrchestrator, quantitative_executor
from analytics.agent.anthropic_researcher import (
    AnthropicResearcher,
    make_anthropic_researcher,
    _extract_json,
    _validate_required,
    _STEP_SCHEMAS,
)


# ---------------------------------------------------------------------------
# Helpers — build a fake Anthropic API response
# ---------------------------------------------------------------------------

def _make_anthropic_response(text: str):
    """Create a mock anthropic Messages response with a single text block."""
    block = MagicMock()
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    return resp


def _make_valid_bu_json() -> str:
    """Valid business_understanding JSON response."""
    import json
    return json.dumps({
        "what_it_does": "The company produces and sells hydrocarbon products.",
        "how_it_makes_money": "Revenue from crude oil and natural gas sales at market prices.",
        "main_products_services": ["Crude oil", "Natural gas"],
        "main_customer_groups": ["Refineries", "Utilities"],
        "revenue_sources": ["Oil sands crude", "Conventional gas"],
        "major_cost_drivers": ["Operating costs", "Sustaining capital"],
        "understandability_rating": "Sufficient",
        "understandability_note": "Business model is clear.",
        "confidence": "High",
        "evidence": [
            {
                "fact": "Produced 1.36 MMBoe/d in Q1 2026.",
                "source": "Q1 2026 Press Release",
                "source_tier": "Tier 1 — Primary",
                "confidence": "High",
            }
        ],
    })


def _make_valid_moat_json() -> str:
    import json
    return json.dumps({
        "active_sources": ["cost_advantage"],
        "overall_strength": "Moderate",
        "overall_durability": "High",
        "trajectory": "Stable",
        "moat_summary": "Low sustaining capital on long-life assets creates a cost advantage.",
        "roic_consistency_note": "ROIC 12–18% over cycle supports the moat claim.",
        "confidence": "Medium",
        "research_gaps": [],
    })


def _make_cnq_load_result():
    """Minimal synthetic DataLoadResult for CNQ.TO — no yfinance call."""
    from analytics.agent.data_loader import DataLoadResult
    from analytics.financial_quality.financial_metrics_model import (
        CompanyFinancialMetrics, RevenueGrowthMetrics, FreeCashFlowMetrics,
        DebtMetrics, MarginMetrics,
    )
    result = DataLoadResult(ticker="CNQ.TO")
    result.company_name = "Canadian Natural Resources Limited"
    result.current_price = 63.45
    result.price_currency = "CAD"
    result.price_date = "2026-08-10"
    result.data_completeness_pct = 75.0
    result.supplemental = {
        "shares_outstanding": 1_950_000_000,
        "trailing_eps": 4.85,
        "book_value_per_share": 28.30,
        "analyst_forward_eps": 5.20,
    }

    m = CompanyFinancialMetrics(
        ticker="CNQ.TO",
        company_name="Canadian Natural Resources Limited",
        currency="CAD",
        data_as_of_date="2026-08-10",
    )
    m.current_price = 63.45
    m.market_cap = 63.45 * 1_950_000_000
    m.pe_ratio = 13.1
    m.ev_ebitda = 6.5

    rg = RevenueGrowthMetrics()
    rg.annual_revenues = {2020: 12_476, 2021: 19_139, 2022: 28_530, 2023: 24_161, 2024: 22_800}
    m.revenue_growth = rg

    fcf = FreeCashFlowMetrics()
    fcf.fcf_current = 6_800.0
    m.free_cash_flow = fcf

    debt = DebtMetrics()
    debt.interest_bearing_debt = 12_000.0
    debt.net_debt = 9_000.0
    m.debt = debt

    mg = MarginMetrics()
    mg.operating_margin = 38.5
    m.margins = mg

    result.metrics = m
    return result


# ===========================================================================
# A. API key missing
# ===========================================================================

class TestA_ApiKeyMissing(unittest.TestCase):
    """When ANTHROPIC_API_KEY is absent, AnthropicResearcher returns None."""

    def test_no_key_is_not_available(self):
        r = AnthropicResearcher(api_key="")
        self.assertFalse(r.is_available())

    def test_no_key_returns_none(self):
        r = AnthropicResearcher(api_key="")
        result = r("business_understanding", {"ticker": "CNQ.TO", "company_name": "CNQ"})
        self.assertIsNone(result)

    def test_make_factory_returns_none_when_no_key(self):
        with patch.dict("os.environ", {}, clear=True):
            # Ensure key is absent from env
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            r = make_anthropic_researcher(api_key="")
            self.assertIsNone(r)

    def test_unknown_step_name_returns_none(self):
        r = AnthropicResearcher(api_key="sk-test-key-not-real")
        # Patch is_available to True but step name is invalid
        result = r("not_a_real_step", {"ticker": "TEST"})
        self.assertIsNone(result)

    def test_pipeline_falls_back_to_quantitative_when_no_key(self):
        """Orchestrator with AnthropicResearcher(no key) behaves like quantitative fallback."""
        researcher = AnthropicResearcher(api_key="")
        orchestrator = ResearchOrchestrator(research_executor=researcher)
        load_result = _make_cnq_load_result()
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO",
            company_name="Canadian Natural Resources Limited",
            metrics=load_result.metrics,
            analysis_date="2026-08-10",
        )
        # Without a key, all qualitative dims should remain None
        self.assertIsNone(assessment.moat_assessment)
        self.assertIsNone(assessment.industry_assessment)
        self.assertIsNone(assessment.risk_assessment)

    def test_gate1_blocks_when_no_key(self):
        """Gate 1 must produce WAIT_INSUFFICIENT_EVIDENCE when researcher has no key."""
        researcher = AnthropicResearcher(api_key="")
        orchestrator = ResearchOrchestrator(research_executor=researcher)
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO",
            company_name="CNQ",
            metrics=None,
            analysis_date="2026-08-10",
        )
        gate1 = evaluate_gate1(assessment)
        self.assertFalse(gate1.passed)


# ===========================================================================
# B. Successful structured response
# ===========================================================================

class TestB_SuccessfulResponse(unittest.TestCase):
    """Valid API responses are parsed correctly into assessment dimensions."""

    def _make_researcher_with_mock(self, response_text: str) -> AnthropicResearcher:
        r = AnthropicResearcher(api_key="sk-test-fake")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response(response_text)
        r._client = mock_client
        return r

    def test_business_understanding_parsed(self):
        r = self._make_researcher_with_mock(_make_valid_bu_json())
        result = r("business_understanding", {"ticker": "CNQ.TO", "company_name": "CNQ"})
        self.assertIsNotNone(result)
        self.assertEqual(result["understandability_rating"], "Sufficient")
        self.assertIn("what_it_does", result)

    def test_moat_parsed(self):
        r = self._make_researcher_with_mock(_make_valid_moat_json())
        result = r("moat_analysis", {"ticker": "CNQ.TO", "company_name": "CNQ"})
        self.assertIsNotNone(result)
        self.assertEqual(result["overall_strength"], "Moderate")
        self.assertIn("moat_summary", result)

    def test_business_understanding_flows_into_orchestrator(self):
        """AnthropicResearcher returning valid BU dict → orchestrator sets business_understanding."""
        import json

        call_count = {"n": 0}

        def mock_executor(step_name, context):
            call_count["n"] += 1
            if step_name == "business_understanding":
                return json.loads(_make_valid_bu_json())
            return None

        orchestrator = ResearchOrchestrator(research_executor=mock_executor)
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO",
            company_name="CNQ",
            metrics=None,
            analysis_date="2026-08-10",
        )
        self.assertIsNotNone(assessment.business_understanding)
        self.assertEqual(
            assessment.business_understanding.understandability_rating,
            UnderstandabilityRating.SUFFICIENT,
        )

    def test_all_dims_filled_when_all_steps_return_data(self):
        """When every step returns data, all 7 dims are populated."""
        import json

        def _all_steps_executor(step_name, context):
            if step_name == "business_understanding":
                return json.loads(_make_valid_bu_json())
            if step_name == "moat_analysis":
                return json.loads(_make_valid_moat_json())
            if step_name == "industry_analysis":
                return {
                    "industry_name": "Oil Sands",
                    "classification": "Neutral",
                    "classification_reasoning": "Commodity business.",
                    "confidence": "Medium",
                }
            if step_name == "growth_analysis":
                return {
                    "revenue_growth_quality": "Organic, volume-driven.",
                    "confidence": "Medium",
                }
            if step_name == "management_analysis":
                return {
                    "overall_rating": "Good",
                    "management_summary": "Track record of disciplined capital allocation.",
                    "capital_allocation": "Dividends and buybacks prioritised over M&A.",
                    "confidence": "Medium",
                }
            if step_name == "risk_analysis":
                return {
                    "risk_summary": "Commodity price and energy transition risk.",
                    "overall_level": "High",
                    "confidence": "Medium",
                }
            if step_name == "bull_bear_analysis":
                return {
                    "bull_case_title": "Oil demand resilience",
                    "bull_case_narrative": "Oil demand sustains above 100 MMbpd through 2035.",
                    "bear_case_title": "Energy transition accelerates",
                    "bear_case_narrative": "EV adoption and carbon pricing compress oil demand.",
                    "thesis_breakers": ["Sustained WTI < $50 for 2+ years"],
                    "devils_advocate_research_note": "IEA forecasts peak oil demand mid-2030s.",
                    "confirmation_bias_check": "Would exit if oil demand visibly peaked.",
                }
            return None

        orchestrator = ResearchOrchestrator(research_executor=_all_steps_executor)
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO", company_name="CNQ",
            metrics=None, analysis_date="2026-08-10",
        )
        self.assertIsNotNone(assessment.business_understanding)
        self.assertIsNotNone(assessment.moat_assessment)
        self.assertIsNotNone(assessment.industry_assessment)
        self.assertIsNotNone(assessment.growth_assessment)
        self.assertIsNotNone(assessment.management_assessment)
        self.assertIsNotNone(assessment.risk_assessment)
        self.assertIsNotNone(assessment.bull_bear)


# ===========================================================================
# C. Malformed JSON response
# ===========================================================================

class TestC_MalformedResponse(unittest.TestCase):
    """Malformed, non-JSON, and truncated responses → None; no exception raised."""

    def _researcher_returning(self, text: str) -> AnthropicResearcher:
        r = AnthropicResearcher(api_key="sk-test-fake")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response(text)
        r._client = mock_client
        return r

    def test_non_json_text_returns_none(self):
        r = self._researcher_returning("Sure! Here is my analysis of CNQ...")
        result = r("business_understanding", {"ticker": "CNQ.TO"})
        self.assertIsNone(result)

    def test_truncated_json_returns_none(self):
        r = self._researcher_returning('{"what_it_does": "The company...')
        result = r("business_understanding", {"ticker": "CNQ.TO"})
        self.assertIsNone(result)

    def test_empty_response_returns_none(self):
        r = self._researcher_returning("")
        result = r("business_understanding", {"ticker": "CNQ.TO"})
        self.assertIsNone(result)

    def test_json_array_not_object_returns_none(self):
        r = self._researcher_returning('["not", "an", "object"]')
        result = r("business_understanding", {"ticker": "CNQ.TO"})
        self.assertIsNone(result)

    def test_extract_json_handles_markdown_fences(self):
        """_extract_json should strip ```json fences if present."""
        import json
        data = {"overall_strength": "Moderate", "moat_summary": "Test."}
        fenced = "```json\n" + json.dumps(data) + "\n```"
        result = _extract_json(fenced)
        self.assertIsNotNone(result)
        self.assertEqual(result["overall_strength"], "Moderate")

    def test_missing_required_field_returns_none(self):
        """A valid JSON response missing a required field → None."""
        import json
        # moat_analysis requires "overall_strength" and "moat_summary"
        incomplete = json.dumps({"trajectory": "Stable", "confidence": "Medium"})
        r = self._researcher_returning(incomplete)
        result = r("moat_analysis", {"ticker": "CNQ.TO"})
        self.assertIsNone(result)

    def test_no_exception_on_api_error(self):
        """API exceptions are caught; None is returned."""
        r = AnthropicResearcher(api_key="sk-test-fake")
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = RuntimeError("Simulated API error")
        r._client = mock_client
        result = r("business_understanding", {"ticker": "CNQ.TO"})
        self.assertIsNone(result)


# ===========================================================================
# D. Missing evidence
# ===========================================================================

class TestD_MissingEvidence(unittest.TestCase):
    """Responses without evidence lists are accepted; missing evidence is not fatal."""

    def _researcher_returning(self, text: str) -> AnthropicResearcher:
        r = AnthropicResearcher(api_key="sk-test-fake")
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_anthropic_response(text)
        r._client = mock_client
        return r

    def test_bu_without_evidence_field_accepted(self):
        """business_understanding without evidence field → accepted (not required)."""
        import json
        data = {
            "what_it_does": "Produces crude oil.",
            "understandability_rating": "Sufficient",
            "understandability_note": "Clear business model.",
            "confidence": "High",
        }
        r = self._researcher_returning(json.dumps(data))
        result = r("business_understanding", {"ticker": "CNQ.TO"})
        self.assertIsNotNone(result)

    def test_moat_with_empty_evidence_accepted(self):
        """moat_analysis with no evidence does not break orchestrator parser."""
        import json
        data = {
            "active_sources": [],
            "overall_strength": "None",
            "overall_durability": "Low",
            "trajectory": "Insufficient Data",
            "moat_summary": "No credible moat identified from available sources.",
            "confidence": "Low",
            "research_gaps": ["Annual reports not reviewed."],
        }
        r = self._researcher_returning(json.dumps(data))
        result = r("moat_analysis", {"ticker": "UNKNOWN.TO"})
        self.assertIsNotNone(result)
        self.assertEqual(result["overall_strength"], "None")

    def test_orchestrator_sets_moat_none_strength_on_no_moat_response(self):
        """Orchestrator maps 'None' overall_strength to MoatStrength.NONE."""
        import json
        no_moat = {
            "active_sources": [],
            "overall_strength": "None",
            "overall_durability": "Low",
            "trajectory": "Insufficient Data",
            "moat_summary": "No credible moat.",
            "confidence": "Low",
            "research_gaps": [],
        }
        def executor(step_name, context):
            if step_name == "moat_analysis":
                return no_moat
            return None

        orchestrator = ResearchOrchestrator(research_executor=executor)
        assessment = orchestrator.build_assessment(
            ticker="TEST.TO", company_name="Test Co.",
            metrics=None, analysis_date="2026-08-10",
        )
        self.assertIsNotNone(assessment.moat_assessment)
        self.assertEqual(assessment.moat_assessment.overall_strength, MoatStrength.NONE)


# ===========================================================================
# E. Research gaps
# ===========================================================================

class TestE_ResearchGaps(unittest.TestCase):
    """Research gaps from the API response propagate through to assessment.research_gaps."""

    def test_missing_dims_become_research_gaps(self):
        """When an executor returns None for a dim, it appears in research_gaps."""
        orchestrator = ResearchOrchestrator(research_executor=quantitative_executor)
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO", company_name="CNQ",
            metrics=None, analysis_date="2026-08-10",
        )
        # All 6 optional qualitative dims should appear as gaps
        self.assertGreaterEqual(len(assessment.research_gaps), 6)
        gap_text = " ".join(assessment.research_gaps).lower()
        self.assertIn("moat", gap_text)
        self.assertIn("industry", gap_text)
        self.assertIn("management", gap_text)

    def test_partial_research_gaps_reflect_missing_dims(self):
        """Only missing dims appear in research_gaps."""
        def partial_executor(step_name, context):
            if step_name == "moat_analysis":
                return {
                    "active_sources": ["cost_advantage"],
                    "overall_strength": "Moderate",
                    "overall_durability": "High",
                    "trajectory": "Stable",
                    "moat_summary": "Cost advantage from scale.",
                    "confidence": "Medium",
                    "research_gaps": [],
                }
            return None

        orchestrator = ResearchOrchestrator(research_executor=partial_executor)
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO", company_name="CNQ",
            metrics=None, analysis_date="2026-08-10",
        )
        # Moat is present — should NOT appear in gaps
        gap_text = " ".join(assessment.research_gaps).lower()
        self.assertNotIn("moat", gap_text)
        # Other dims still missing
        self.assertIn("industry", gap_text)

    def test_research_completeness_dict_reflects_available_dims(self):
        """research_completeness accurately reflects which dims are present."""
        def moat_only_executor(step_name, context):
            if step_name == "moat_analysis":
                return {
                    "active_sources": [],
                    "overall_strength": "None",
                    "overall_durability": "Low",
                    "trajectory": "Insufficient Data",
                    "moat_summary": "No moat.",
                    "confidence": "Low",
                }
            return None

        orchestrator = ResearchOrchestrator(research_executor=moat_only_executor)
        assessment = orchestrator.build_assessment(
            ticker="TEST.TO", company_name="Test", metrics=None, analysis_date="2026-08-10",
        )
        comp = assessment.research_completeness
        self.assertTrue(comp.get("moat_assessment"))
        self.assertFalse(comp.get("industry_assessment"))
        self.assertFalse(comp.get("growth_assessment"))


# ===========================================================================
# F. Executor injection
# ===========================================================================

class TestF_ExecutorInjection(unittest.TestCase):
    """AnthropicResearcher can be injected into ResearchOrchestrator."""

    def test_researcher_is_callable(self):
        r = AnthropicResearcher(api_key="sk-test-fake")
        self.assertTrue(callable(r))

    def test_researcher_injected_into_orchestrator(self):
        """ResearchOrchestrator accepts AnthropicResearcher as its executor."""
        researcher = AnthropicResearcher(api_key="")  # no key → all steps return None
        orchestrator = ResearchOrchestrator(research_executor=researcher)
        self.assertIs(orchestrator._executor, researcher)

    def test_orchestrator_default_is_quantitative(self):
        """ResearchOrchestrator defaults to quantitative_executor when no executor given."""
        orchestrator = ResearchOrchestrator()
        self.assertIs(orchestrator._executor, quantitative_executor)

    def test_mock_executor_can_simulate_anthropic(self):
        """A lambda can stand in for AnthropicResearcher for lightweight testing."""
        call_log = []

        def recording_executor(step_name, context):
            call_log.append(step_name)
            return None

        orchestrator = ResearchOrchestrator(research_executor=recording_executor)
        orchestrator.build_assessment(
            ticker="TEST.TO", company_name="Test", metrics=None, analysis_date="2026-08-10",
        )
        # Orchestrator calls 7 steps (business_understanding + 6 qualitative dims)
        self.assertEqual(len(call_log), 7)
        self.assertIn("business_understanding", call_log)
        self.assertIn("moat_analysis", call_log)

    def test_is_available_false_when_package_missing(self):
        """is_available() returns False when anthropic package cannot be imported."""
        r = AnthropicResearcher(api_key="sk-test-key")
        with patch.dict("sys.modules", {"anthropic": None}):
            self.assertFalse(r.is_available())


# ===========================================================================
# G. CNQ deterministic unchanged
# ===========================================================================

class TestG_CnqDeterministicUnchanged(unittest.TestCase):
    """
    Phase 9 regression: quantitative_executor still produces the same
    deterministic result — CNQ.TO gets WAIT_INSUFFICIENT_EVIDENCE.
    The Anthropic executor does NOT affect this path.
    """

    def test_quantitative_executor_always_returns_none(self):
        steps = [
            "business_understanding", "moat_analysis", "industry_analysis",
            "growth_analysis", "management_analysis", "risk_analysis", "bull_bear_analysis",
        ]
        for step in steps:
            result = quantitative_executor(step, {"ticker": "CNQ.TO"})
            self.assertIsNone(result, f"Step {step} should return None")

    def test_gate1_fails_for_quantitative_cnq(self):
        """quantitative_executor → Gate 1 fails → WAIT_INSUFFICIENT_EVIDENCE."""
        orchestrator = ResearchOrchestrator(research_executor=quantitative_executor)
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO",
            company_name="Canadian Natural Resources Limited",
            metrics=None,
            analysis_date="2026-08-10",
        )
        gate1 = evaluate_gate1(assessment)
        self.assertFalse(gate1.passed)

    def test_decision_is_wait_for_quantitative_cnq(self):
        """End-to-end: quantitative fallback produces WAIT_INSUFFICIENT_EVIDENCE."""
        orchestrator = ResearchOrchestrator(research_executor=quantitative_executor)
        load_result = _make_cnq_load_result()
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO",
            company_name="Canadian Natural Resources Limited",
            metrics=load_result.metrics,
            analysis_date="2026-08-10",
        )
        decision = make_investment_decision(
            "CNQ.TO",
            "Canadian Natural Resources Limited",
            "2026-08-10",
            research=assessment,
        )
        self.assertEqual(decision.action, DecisionAction.WAIT_INSUFFICIENT_EVIDENCE)

    def test_cnq_completeness_is_one_seventh(self):
        """Quantitative fallback: 1/7 dims complete (business_understanding only)."""
        orchestrator = ResearchOrchestrator(research_executor=quantitative_executor)
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO", company_name="CNQ", metrics=None, analysis_date="2026-08-10",
        )
        comp = assessment.research_completeness
        complete_count = sum(1 for v in comp.values() if v)
        total_count = len(comp)
        self.assertEqual(complete_count, 1, "Only business_understanding should be set")
        self.assertEqual(total_count, 7)

    def test_no_investment_conclusion_in_quantitative_assessment(self):
        """Quantitative fallback never embeds investment conclusions."""
        orchestrator = ResearchOrchestrator(research_executor=quantitative_executor)
        assessment = orchestrator.build_assessment(
            ticker="CNQ.TO", company_name="CNQ", metrics=None, analysis_date="2026-08-10",
        )
        bu = assessment.business_understanding
        self.assertIsNotNone(bu)
        text = (bu.what_it_does or "") + (bu.understandability_note or "")
        # Should not contain investment action words
        for forbidden in ("BUY", "SELL", "ACCUMULATE", "START_SMALL", "undervalued"):
            self.assertNotIn(forbidden, text, f"Found forbidden word '{forbidden}' in BU fallback")


# ===========================================================================
# H. Portfolio privacy unchanged
# ===========================================================================

class TestH_PortfolioPrivacy(unittest.TestCase):
    """
    Portfolio privacy: only portfolio_weight_pct is accepted.
    Shares, average cost, total portfolio value are never requested, stored, or inferred.
    """

    def test_weight_only_context_accepted(self):
        from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
        ctx = WeightOnlyPortfolioContext(ticker="CNQ.TO", portfolio_weight_pct=4.5)
        self.assertEqual(ctx.ticker, "CNQ.TO")
        self.assertEqual(ctx.portfolio_weight_pct, 4.5)

    def test_weight_only_context_shares_are_locked_to_none(self):
        """
        WeightOnlyPortfolioContext declares shares_held and average_cost_per_share
        as permanently None (type-enforced absence, not missing data).
        They must not hold actual values.
        """
        from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
        ctx = WeightOnlyPortfolioContext(ticker="CNQ.TO", portfolio_weight_pct=3.0)
        # Fields exist but are hardwired to None — this IS the privacy guarantee
        self.assertIsNone(ctx.shares_held)
        self.assertIsNone(ctx.average_cost_per_share)
        # The only usable field is portfolio_weight_pct
        self.assertEqual(ctx.portfolio_weight_pct, 3.0)

    def test_researcher_context_contains_no_portfolio_details(self):
        """The context dict passed to AnthropicResearcher never contains private portfolio data."""
        orchestrator = ResearchOrchestrator(research_executor=quantitative_executor)
        load_result = _make_cnq_load_result()
        ctx = orchestrator._build_context(
            "CNQ.TO",
            "Canadian Natural Resources Limited",
            load_result.metrics,
            "2026-08-10",
        )
        for forbidden_key in (
            "shares_held", "average_cost", "cost_basis", "portfolio_value",
            "shares_outstanding_held", "position_size",
        ):
            self.assertNotIn(
                forbidden_key, ctx,
                f"Context should not contain private portfolio field '{forbidden_key}'",
            )

    def test_anthropic_prompts_contain_no_portfolio_instructions(self):
        """The format context does not ask the model to reason about shares or cost basis."""
        from analytics.agent.anthropic_researcher import _format_context
        ctx = {
            "ticker": "CNQ.TO",
            "company_name": "CNQ",
            "current_price": 63.45,
        }
        prompt = _format_context("business_understanding", ctx)
        for forbidden in ("shares held", "average cost", "cost basis", "portfolio value", "position size"):
            self.assertNotIn(
                forbidden, prompt.lower(),
                f"Prompt must not ask about private portfolio data: '{forbidden}'",
            )

    def test_decision_with_weight_context_does_not_expose_shares(self):
        """make_investment_decision with WeightOnlyPortfolioContext never stores shares."""
        from analytics.portfolio.portfolio_models import WeightOnlyPortfolioContext
        from analytics.decision.decision_synthesizer import make_investment_decision
        from analytics.business_research.research_models import (
            BusinessResearchAssessment,
            BusinessUnderstandingAssessment,
            UnderstandabilityRating,
            MoatAssessment, MoatStrength, MoatDurability, MoatTrajectory,
            IndustryAssessment, IndustryClassification,
            ManagementAssessment, ManagementRating,
            GrowthAssessment, RiskAssessment, RiskLevel,
            BullBearAssessment, Confidence,
        )
        # Build minimal research that passes Gate 1
        r = BusinessResearchAssessment(ticker="CNQ.TO", company_name="CNQ", assessment_date="2026-08-10")
        r.business_understanding = BusinessUnderstandingAssessment(
            what_it_does="Oil sands producer.",
            understandability_rating=UnderstandabilityRating.SUFFICIENT,
            confidence=Confidence.HIGH,
        )
        r.moat_assessment = MoatAssessment(
            overall_strength=MoatStrength.MODERATE,
            overall_durability=MoatDurability.HIGH,
            trajectory=MoatTrajectory.STABLE,
            moat_summary="Cost advantage.",
        )
        r.industry_assessment = IndustryAssessment(
            classification=IndustryClassification.NEUTRAL,
            confidence=Confidence.MEDIUM,
        )
        r.management_assessment = ManagementAssessment(
            overall_rating=ManagementRating.GOOD,
            confidence=Confidence.MEDIUM,
        )
        r.growth_assessment = GrowthAssessment(confidence=Confidence.MEDIUM)
        r.risk_assessment = RiskAssessment(overall_level=RiskLevel.MODERATE)
        r.bull_bear = BullBearAssessment(
            bear_case_narrative="Oil demand declines.",
            thesis_breakers=["ROIC < 8% for 3 years"],
        )
        r.research_completeness = {k: True for k in
                                   ["business_understanding", "moat_assessment",
                                    "industry_assessment", "growth_assessment",
                                    "management_assessment", "risk_assessment", "bull_bear"]}

        portfolio_ctx = WeightOnlyPortfolioContext(ticker="CNQ.TO", portfolio_weight_pct=4.5)
        decision = make_investment_decision(
            "CNQ.TO", "CNQ", "2026-08-10",
            research=r,
            portfolio_ctx=portfolio_ctx,
        )
        # Decision object must not store shares or cost
        self.assertFalse(hasattr(decision, "shares_held"))
        self.assertFalse(hasattr(decision, "average_cost"))


# ---------------------------------------------------------------------------
# Helpers imported for TestG
# ---------------------------------------------------------------------------
from analytics.decision.decision_synthesizer import make_investment_decision  # noqa: E402


if __name__ == "__main__":
    unittest.main(verbosity=2)
