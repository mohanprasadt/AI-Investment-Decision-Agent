"""
Phase 9.3 Regression Tests — Follow-up Intent Bug (holding horizon)
=====================================================================
Root cause:
  "does the recommendation change if I want to buy and hold this stock for more
   than 10 years" was parsed as INTENT_ANALYZE with ticker="CHANGE" because:
   (1) _FOLLOW_UP_TRIGGERS had no time-horizon patterns so no match was triggered;
   (2) after uppercasing, "CHANGE" (6 chars) was the first word not in _COMMON_WORDS;
   (3) _handle_analyze then re-ran make_investment_decision with "CHANGE" as ticker.

Fix:
  - Added `\d+\s+years?`, `long[\s-]term`, `buy\s+and\s+hold`,
    `holding\s+period`, `investment\s+horizon`, `time\s+horizon`,
    `hold\s+(this|it|the\s+stock)` to _FOLLOW_UP_TRIGGERS.
  - Added `_answer_holding_horizon` renderer, routed on "year/years/long-term/
    buy and hold/holding period/investment horizon/time horizon/decade".

Run with:  pytest tests/test_phase93.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_assessment(
    action_value="WAIT_INSUFFICIENT_EVIDENCE",
    business_thesis="",
    valuation_conclusion="",
    why_text="",
    thesis_breakers=None,
    what_would_change="",
):
    """Minimal InvestmentDecisionAssessment for renderer tests."""
    from analytics.decision.decision_models import (
        InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
    )
    d = InvestmentDecisionAssessment(
        ticker="ITC.NS",
        company_name="ITC Limited",
        analysis_date="2026-08-10",
        current_price=450.0,
        price_currency="INR",
    )
    d.action = DecisionAction[action_value]
    d.decision_confidence = DecisionConfidence.MEDIUM
    d.business_thesis = business_thesis
    d.valuation_conclusion = valuation_conclusion
    d.why_attractive_or_unattractive = why_text
    d.thesis_breakers = thesis_breakers or []
    d.what_would_change_conclusion = what_would_change
    d.supporting_evidence = []
    d.research_gaps = []
    d.executive_conclusion = "ORIGINAL EXECUTIVE CONCLUSION"
    d.gate_results = []
    return d


# ---------------------------------------------------------------------------
# Class A — Intent parser: horizon triggers now route to FOLLOW_UP
# ---------------------------------------------------------------------------

class TestA_IntentParserHorizonTriggers:
    """The exact failing question and variants must be INTENT_FOLLOW_UP."""

    def test_exact_failing_question_is_follow_up(self):
        """
        'does the recommendation change if I want to buy and hold this stock
         for more than 10 years' must be INTENT_FOLLOW_UP, not INTENT_ANALYZE.
        """
        from analytics.agent.intent_parser import parse_intent, INTENT_FOLLOW_UP

        q = "does the recommendation change if I want to buy and hold this stock for more than 10 years"
        intent = parse_intent(q)

        assert intent.intent_type == INTENT_FOLLOW_UP, (
            f"Expected INTENT_FOLLOW_UP, got {intent.intent_type}. "
            "This is the regression for the CHANGE-ticker bug."
        )

    def test_10_years_variant(self):
        """'Does the recommendation change if I hold for 10 years?' → FOLLOW_UP."""
        from analytics.agent.intent_parser import parse_intent, INTENT_FOLLOW_UP

        intent = parse_intent("Does the recommendation change if I hold for 10 years?")
        assert intent.intent_type == INTENT_FOLLOW_UP

    def test_15_years_variant(self):
        """'What if I'm investing for 15 years?' → FOLLOW_UP."""
        from analytics.agent.intent_parser import parse_intent, INTENT_FOLLOW_UP

        intent = parse_intent("What if I'm investing for 15 years?")
        assert intent.intent_type == INTENT_FOLLOW_UP

    def test_long_term_variant(self):
        """'How does a long-term view change the recommendation?' → FOLLOW_UP."""
        from analytics.agent.intent_parser import parse_intent, INTENT_FOLLOW_UP

        intent = parse_intent("How does a long-term view change the recommendation?")
        assert intent.intent_type == INTENT_FOLLOW_UP

    def test_buy_and_hold_variant(self):
        """'Is this a good buy and hold stock?' → FOLLOW_UP."""
        from analytics.agent.intent_parser import parse_intent, INTENT_FOLLOW_UP

        intent = parse_intent("Is this a good buy and hold stock?")
        assert intent.intent_type == INTENT_FOLLOW_UP

    def test_holding_period_variant(self):
        """'Does the holding period matter for this investment?' → FOLLOW_UP."""
        from analytics.agent.intent_parser import parse_intent, INTENT_FOLLOW_UP

        intent = parse_intent("Does the holding period matter for this investment?")
        assert intent.intent_type == INTENT_FOLLOW_UP

    def test_investment_horizon_variant(self):
        """'What changes with a 20-year investment horizon?' → FOLLOW_UP."""
        from analytics.agent.intent_parser import parse_intent, INTENT_FOLLOW_UP

        intent = parse_intent("What changes with a 20-year investment horizon?")
        assert intent.intent_type == INTENT_FOLLOW_UP

    def test_ticker_not_extracted_as_change(self):
        """
        The old bug: parse_intent returned ticker='CHANGE' for the failing question.
        Verify the ticker field is None for FOLLOW_UP intents.
        """
        from analytics.agent.intent_parser import parse_intent, INTENT_FOLLOW_UP

        q = "does the recommendation change if I want to buy and hold this stock for more than 10 years"
        intent = parse_intent(q)

        assert intent.intent_type == INTENT_FOLLOW_UP
        assert intent.ticker is None, (
            f"ticker must be None for FOLLOW_UP; got '{intent.ticker}'. "
            "'CHANGE' was incorrectly extracted as a ticker before the fix."
        )

    # ------------------------------------------------------------------
    # Critical: explicit CHANGE ticker must still work
    # ------------------------------------------------------------------

    def test_explicit_analyze_change_is_still_analyze(self):
        """
        'Analyze CHANGE' — user intends the CHANGE ticker — must be INTENT_ANALYZE.
        The fix must not break genuine ticker-analysis requests.
        """
        from analytics.agent.intent_parser import parse_intent, INTENT_ANALYZE

        intent = parse_intent("Analyze CHANGE")
        assert intent.intent_type == INTENT_ANALYZE, (
            "Explicit 'Analyze CHANGE' must remain INTENT_ANALYZE"
        )
        assert intent.ticker == "CHANGE"
        assert intent.has_analyze_verb

    def test_check_change_is_still_analyze(self):
        """'Check CHANGE for me' → INTENT_ANALYZE with ticker=CHANGE."""
        from analytics.agent.intent_parser import parse_intent, INTENT_ANALYZE

        intent = parse_intent("Check CHANGE for me")
        assert intent.intent_type == INTENT_ANALYZE
        assert intent.ticker == "CHANGE"


# ---------------------------------------------------------------------------
# Class B — Agent routing: horizon question uses cached assessment
# ---------------------------------------------------------------------------

class TestB_AgentHorizonRouting:

    def _seed_cache(self, agent):
        """Seed the agent session with a fake ITC.NS analysis."""
        agent._session._cached_inputs = {
            "ticker": "ITC.NS",
            "company_name": "ITC Limited",
            "analysis_date": "2026-08-10",
            "financial_quality": None,
            "research": None,
            "valuation": None,
            "current_price": 450.0,
            "price_currency": "INR",
            "price_date": "2026-08-10",
            "freshness": None,
        }
        agent._session.last_assessment = _make_assessment(
            action_value="START_SMALL",
            business_thesis="ITC is a diversified conglomerate with FMCG growth and strong cash generation.",
            valuation_conclusion="Current price at 8% discount to base fair value.",
        )
        agent._session.last_ticker = "ITC.NS"

    def test_horizon_question_does_not_reanalyze(self):
        """
        After ITC.NS analysis, a horizon question must NOT call make_investment_decision.
        """
        from analytics.agent.investment_agent import InvestmentAgent
        from unittest.mock import patch

        agent = InvestmentAgent()
        self._seed_cache(agent)

        with patch("analytics.agent.investment_agent.make_investment_decision") as mock_decide:
            agent.chat(
                "does the recommendation change if I want to buy and hold this stock for more than 10 years"
            )
            mock_decide.assert_not_called()

    def test_horizon_question_uses_stored_assessment(self):
        """Response must reference stored data (ticker, date, or thesis content)."""
        from analytics.agent.investment_agent import InvestmentAgent

        agent = InvestmentAgent()
        self._seed_cache(agent)

        response = agent.chat(
            "does the recommendation change if I want to buy and hold this stock for more than 10 years"
        )

        assert "ITC.NS" in response or "ITC Limited" in response, (
            "Response must reference the stored ticker or company name"
        )
        assert "ORIGINAL EXECUTIVE CONCLUSION" not in response, (
            "Must not fall through to bare executive-conclusion default"
        )

    def test_no_session_returns_helpful_message(self):
        """Without a prior analysis, must ask the user to run one first."""
        from analytics.agent.investment_agent import InvestmentAgent

        agent = InvestmentAgent()   # empty session
        response = agent.chat("Does the recommendation change if I hold for 10 years?")
        assert "analysis" in response.lower() or "don't have" in response.lower()


# ---------------------------------------------------------------------------
# Class C — Renderer: _answer_holding_horizon structure and content
# ---------------------------------------------------------------------------

class TestC_HorizonRenderer:

    def test_renderer_reached_on_years_keyword(self):
        """'10 years' keyword must route to _answer_holding_horizon, not default."""
        from analytics.agent.renderer import render_followup

        d = _make_assessment(action_value="START_SMALL")
        response = render_followup("Does the recommendation change if I hold for 10 years?", d)

        assert "ORIGINAL EXECUTIVE CONCLUSION" not in response
        assert "Ask me about" not in response

    def test_renderer_reached_on_long_term_keyword(self):
        """'long-term' keyword must route to _answer_holding_horizon."""
        from analytics.agent.renderer import render_followup

        d = _make_assessment()
        response = render_followup("How does a long-term view change things?", d)

        assert "ORIGINAL EXECUTIVE CONCLUSION" not in response

    def test_renderer_distinguishes_thesis_from_valuation(self):
        """
        The response must explicitly address both:
          A. Business/thesis effect of a long horizon
          B. Valuation/entry-timing effect
        """
        from analytics.agent.renderer import _answer_holding_horizon

        d = _make_assessment(
            action_value="START_SMALL",
            business_thesis="Strong moat with durable FCF.",
            valuation_conclusion="At 8% discount to base fair value; MoS below required 12%.",
        )
        response = _answer_holding_horizon(d)

        # Both sections must be present
        assert "BUSINESS" in response.upper() or "THESIS" in response.upper(), (
            "Response must address the business/thesis dimension"
        )
        assert "VALUATION" in response.upper() or "ENTRY" in response.upper(), (
            "Response must address the valuation/entry-timing dimension"
        )

    def test_renderer_includes_stored_thesis(self):
        """When a business_thesis is stored, it must appear in the response."""
        from analytics.agent.renderer import _answer_holding_horizon

        d = _make_assessment(
            action_value="WATCH",
            business_thesis="ITC has a dominant cigarette franchise with high FCF generation.",
        )
        response = _answer_holding_horizon(d)
        assert "ITC has a dominant cigarette franchise" in response

    def test_renderer_on_wait_state_says_research_needed(self):
        """
        When action is WAIT_INSUFFICIENT_EVIDENCE (no research done), the renderer
        must not pretend the thesis is strong — it must say research is needed.
        """
        from analytics.agent.renderer import _answer_holding_horizon

        d = _make_assessment(
            action_value="WAIT_INSUFFICIENT_EVIDENCE",
            business_thesis="",
            valuation_conclusion="",
        )
        response = _answer_holding_horizon(d)

        # Must mention the WAIT action or missing research
        assert (
            "WAIT" in response
            or "research" in response.lower()
            or "not stored" in response.lower()
            or "not available" in response.lower()
        )

    def test_renderer_surfaces_thesis_breakers(self):
        """Thesis breakers must appear in the horizon response (they're long-term risks)."""
        from analytics.agent.renderer import _answer_holding_horizon
        from analytics.decision.decision_models import ThesisBreaker

        d = _make_assessment(
            action_value="START_SMALL",
            business_thesis="Durable FMCG franchise.",
            thesis_breakers=[
                ThesisBreaker(
                    condition="Sustained regulatory restrictions on tobacco revenues",
                    likelihood="MEDIUM",
                    impact="SEVERE",
                )
            ],
        )
        response = _answer_holding_horizon(d)
        assert "tobacco" in response.lower() or "regulatory" in response.lower()

    def test_renderer_does_not_invent_facts(self):
        """
        The response must include the boundary disclaimer that no new research
        was generated.
        """
        from analytics.agent.renderer import _answer_holding_horizon

        d = _make_assessment(action_value="WATCH")
        response = _answer_holding_horizon(d)
        assert "no new research" in response.lower() or "stored" in response.lower()

    def test_renderer_action_guidance_reflects_current_action(self):
        """
        The response must reference the current stored action value so the user
        understands it was not re-derived.
        """
        from analytics.agent.renderer import _answer_holding_horizon

        for action in ("START_SMALL", "WATCH", "WAIT_INSUFFICIENT_EVIDENCE"):
            d = _make_assessment(action_value=action)
            response = _answer_holding_horizon(d)
            assert action in response, (
                f"Current action '{action}' must appear in horizon response"
            )
