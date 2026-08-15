"""
Phase 9.4c Regression Tests — Valuation-Method Follow-up Routing
=================================================================
Bug fixed: "Which valuation method makes ITC look most expensive?"
was parsed as INTENT_ANALYZE with ticker="METHOD" (a false extraction),
then returned "I understand you want to analyze METHOD."

Root cause:
  1. "which method" / "which valuation method" / "most expensive" did not
     appear in _FOLLOW_UP_TRIGGERS → no early follow-up classification.
  2. "METHOD" (6 chars) was not in _COMMON_WORDS → _TICKER_RE accepted it
     as the first candidate ticker before reaching "ITC".

Fix:
  1. Added follow-up trigger patterns for "which (valuation) method",
     "what (valuation) method", "most expensive", "look expensive",
     and specific metric keywords (p/e, ev/ebitda, p/fcf).
  2. Added valuation-domain words to _COMMON_WORDS: METHOD, MAKES, MAKING,
     MOST, LOOK, LOOKS, CHEAP, PRICEY, DRIVES, WEIGHT, METRIC, RATIOS etc.

Run:  pytest tests/test_phase94c.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.agent.intent_parser import parse_intent, INTENT_ANALYZE, INTENT_FOLLOW_UP
from analytics.agent.investment_agent import InvestmentAgent
from analytics.decision.decision_models import InvestmentDecisionAssessment, DecisionAction


# ---------------------------------------------------------------------------
# Shared helper: build a mock session with a cached ITC.NS assessment
# ---------------------------------------------------------------------------

def _agent_with_itc_cached() -> InvestmentAgent:
    """
    Return an InvestmentAgent whose session already has an ITC.NS assessment
    cached, simulating a prior analysis run.
    """
    agent = InvestmentAgent()
    # Build a minimal assessment matching what a real ITC run would produce
    assessment = InvestmentDecisionAssessment(
        ticker="ITC.NS",
        company_name="ITC Limited",
        analysis_date="2026-08-10",
        current_price=282.65,
        price_currency="INR",
        action=DecisionAction.WATCH,
        valuation_attractiveness_label="NEGATIVE",
        valuation_conclusion="Price is above estimated fair value.",
        per_method_valuation_summary=[
            "DCF: bear INR 166.54 | mid INR 195.93 | bull INR 225.32"
            "  [reliability: LOW, weight: 0.3] (30.7% below current price INR 282.65)",
            "Normalised P/E: bear INR 242.51 | mid INR 285.30 | bull INR 328.10"
            "  [reliability: LOW, weight: 0.3] (0.9% above current price INR 282.65)",
            "EV/EBITDA: bear INR 204.04 | mid INR 240.05 | bull INR 276.06"
            "  [reliability: MEDIUM, weight: 0.6] (15.1% below current price INR 282.65)",
            "P/FCF: bear INR 184.17 | mid INR 216.67 | bull INR 249.17"
            "  [reliability: MEDIUM, weight: 0.6] (23.4% below current price INR 282.65)",
            "Weighted average fair value: bear INR 197.64 | base INR 232.52 | bull INR 267.40"
            " (17.7% below current price INR 282.65)",
        ],
        key_assumptions=["Normalised P/E based on 3-year average EPS."],
    )
    # Manually inject state so we can test routing without a full pipeline run
    agent._session.last_assessment = assessment
    agent._session.last_ticker = "ITC.NS"
    agent._session._cached_inputs = {
        "ticker": "ITC.NS",
        "company_name": "ITC Limited",
        "analysis_date": "2026-08-10",
        "current_price": 282.65,
        "price_currency": "INR",
        "price_date": "2026-08-10",
        "financial_quality": None,
        "research": None,
        "valuation": None,
        "freshness": None,
    }
    return agent


# ---------------------------------------------------------------------------
# Class A — Intent parser routing (parse_intent directly)
# ---------------------------------------------------------------------------

class TestA_IntentParserRouting:
    """Verify parse_intent classifies method questions as FOLLOW_UP."""

    def test_which_valuation_method_is_follow_up(self):
        intent = parse_intent("Which valuation method makes ITC look most expensive?")
        assert intent.intent_type == INTENT_FOLLOW_UP, (
            f"Expected FOLLOW_UP, got {intent.intent_type}. "
            "This question should not be classified as ANALYZE."
        )

    def test_which_method_itc_expensive_is_follow_up(self):
        intent = parse_intent("Which method is making ITC look expensive?")
        assert intent.intent_type == INTENT_FOLLOW_UP, (
            f"Expected FOLLOW_UP, got {intent.intent_type}"
        )

    def test_what_method_drives_is_follow_up(self):
        intent = parse_intent("What method drives the valuation conclusion?")
        assert intent.intent_type == INTENT_FOLLOW_UP

    def test_pe_ratio_question_is_follow_up(self):
        intent = parse_intent("Why is ITC expensive if P/E is only 18x?")
        assert intent.intent_type == INTENT_FOLLOW_UP, (
            "P/E question with 'why' should be FOLLOW_UP"
        )

    def test_most_expensive_is_follow_up(self):
        intent = parse_intent("Which method makes ITC look most expensive?")
        assert intent.intent_type == INTENT_FOLLOW_UP

    def test_analyze_itc_again_is_analyze(self):
        """Explicit 'Analyze ITC.NS again' must remain INTENT_ANALYZE."""
        intent = parse_intent("Analyze ITC.NS again")
        assert intent.intent_type == INTENT_ANALYZE, (
            "Explicit analyze verb must produce INTENT_ANALYZE"
        )
        assert intent.has_analyze_verb is True

    def test_analyze_cnr_is_analyze(self):
        """Fresh 'Analyze CNR.TO' must remain INTENT_ANALYZE."""
        intent = parse_intent("Analyze CNR.TO")
        assert intent.intent_type == INTENT_ANALYZE
        assert intent.ticker == "CNR.TO"

    def test_ticker_not_method(self):
        """'Which valuation method …' must NOT extract METHOD as ticker."""
        intent = parse_intent("Which valuation method makes ITC look most expensive?")
        # Either FOLLOW_UP (no ticker) or the ticker must not be METHOD
        if intent.intent_type == INTENT_ANALYZE:
            assert intent.ticker != "METHOD", (
                "METHOD should not be extracted as a ticker"
            )

    def test_ev_ebitda_question_is_follow_up(self):
        intent = parse_intent("What does the EV/EBITDA method say about ITC?")
        assert intent.intent_type == INTENT_FOLLOW_UP

    def test_pfcf_question_is_follow_up(self):
        intent = parse_intent("How does P/FCF compare for ITC?")
        assert intent.intent_type == INTENT_FOLLOW_UP


# ---------------------------------------------------------------------------
# Class B — End-to-end agent routing with cached session
# ---------------------------------------------------------------------------

class TestB_AgentRoutingWithCache:
    """Verify InvestmentAgent routes method questions to the follow-up handler."""

    def test_which_valuation_method_returns_breakdown(self):
        """The response must contain the per-method breakdown, not an 'I understand you want to analyze' message."""
        agent = _agent_with_itc_cached()
        resp = agent.chat("Which valuation method makes ITC look most expensive?")
        assert "I understand you want to analyze" not in resp, (
            "Routing error: should be a follow-up, not an analyze prompt"
        )
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp, (
            "Response should contain per-method breakdown for ITC"
        )

    def test_which_method_making_expensive_returns_breakdown(self):
        agent = _agent_with_itc_cached()
        resp = agent.chat("Which method is making ITC look expensive?")
        assert "I understand you want to analyze" not in resp
        assert "PER-METHOD FAIR VALUE BREAKDOWN" in resp

    def test_pe_question_routes_to_followup(self):
        """'Why is ITC expensive if P/E is only 18x?' — preserve existing behaviour."""
        agent = _agent_with_itc_cached()
        resp = agent.chat("Why is ITC expensive if P/E is only 18x?")
        assert "I understand you want to analyze" not in resp
        # Should get the per-method breakdown (from _answer_valuation_method)
        # OR the generic valuation answer — either is acceptable as long as
        # it does NOT say "I understand you want to analyze"
        assert len(resp) > 50, "Response should be substantive"

    def test_analyze_again_re_runs(self):
        """'Analyze ITC.NS again' must still trigger re-analysis, not follow-up."""
        agent = _agent_with_itc_cached()
        resp = agent.chat("Analyze ITC.NS again")
        # Without a live pipeline, this produces the cached-inputs re-run path.
        # It should NOT route to _handle_followup (which would return valuation text).
        # Since cached inputs have no research, the decision should be
        # WAIT_INSUFFICIENT_EVIDENCE — different from the mock WATCH in session.
        # Key: response must not be the "PER-METHOD FAIR VALUE BREAKDOWN" follow-up text.
        # It should be a rendered assessment (starts with the assessment header pattern).
        assert "PER-METHOD FAIR VALUE BREAKDOWN" not in resp or "ACTION" in resp, (
            "Re-analysis should produce an assessment report, not a follow-up answer"
        )

    def test_no_session_returns_helpful_message(self):
        """Without a cached session, method questions prompt the user to run an analysis first."""
        agent = InvestmentAgent()  # fresh, no session
        resp = agent.chat("Which valuation method makes ITC look most expensive?")
        assert "analysis" in resp.lower() or "analyze" in resp.lower(), (
            "Without a session, agent should prompt user to run an analysis first"
        )


# ---------------------------------------------------------------------------
# Class C — _COMMON_WORDS coverage for false-ticker words
# ---------------------------------------------------------------------------

class TestC_CommonWords:
    """Verify that valuation-domain words are not extracted as tickers."""

    def _ticker_for(self, text: str):
        intent = parse_intent(text)
        return intent.ticker

    def test_method_not_extracted_as_ticker(self):
        """'Which method …' should not yield ticker=METHOD."""
        # Use a sentence that has no real ticker at all
        intent = parse_intent("Which method looks most accurate?")
        # Either FOLLOW_UP or ANALYZE with a non-METHOD ticker
        if intent.intent_type == INTENT_ANALYZE:
            assert intent.ticker != "METHOD", "METHOD should not be a ticker candidate"

    def test_look_not_extracted_as_ticker(self):
        intent = parse_intent("Does this look expensive?")
        if intent.intent_type == INTENT_ANALYZE:
            assert intent.ticker != "LOOK"

    def test_most_not_extracted_as_ticker(self):
        intent = parse_intent("Which is most expensive?")
        if intent.intent_type == INTENT_ANALYZE:
            assert intent.ticker != "MOST"

    def test_makes_not_extracted_as_ticker(self):
        intent = parse_intent("What makes it look cheap?")
        if intent.intent_type == INTENT_ANALYZE:
            assert intent.ticker != "MAKES"

    def test_real_ticker_still_extracted(self):
        """Real tickers must still be found after the common-word expansion."""
        intent = parse_intent("Analyze CNR.TO")
        assert intent.intent_type == INTENT_ANALYZE
        assert intent.ticker == "CNR.TO"

    def test_itc_still_valid_ticker(self):
        """ITC (3 chars) must still be extracted as a ticker in genuine analyze requests."""
        intent = parse_intent("Analyze ITC.NS")
        assert intent.intent_type == INTENT_ANALYZE
        assert intent.ticker == "ITC.NS"
