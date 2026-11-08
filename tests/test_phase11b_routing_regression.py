"""
Regression tests: breaker-likelihood routing in render_followup().

Defect (fixed): the D1 guard used substring tests (`"why" in q and tok in q`), so
ordinary questions such as "Why is the price so high?" or "Why is FCF/share lower
than EPS?" ("lower" contains "low") were routed to the breaker-likelihood handler.

Contract under test:
  - Ordinary "why" questions containing low/medium/high/unknown only as substrings
    ("below", "higher", "highlight", "lower") or as whole words WITHOUT breaker
    context fall through to the normal handlers.
  - Genuine likelihood questions (breaker vocabulary, or >= 2 whole content words
    shared with a stored breaker condition, incl. paraphrases) reach the handler.
  - Gate 5 explanation routing is unchanged ("Why is Gate 5 HIGH?").
  - Phase 11B contract: UNKNOWN likelihood is preserved as-is.
  - Fuzzy matcher uses whole words, not substrings.
"""

from __future__ import annotations

import pytest

import analytics.agent.renderer as R

_SENTINEL = "<<LIKELIHOOD_HANDLER>>"


def _breaker(condition, likelihood, rationale=""):
    from analytics.decision.decision_models import ThesisBreaker
    return ThesisBreaker(
        condition=condition,
        likelihood=likelihood,
        impact="SEVERE",
        monitoring_indicator="Monitor quarterly.",
        trigger_action="Would prompt review.",
        evidence=[],
        likelihood_rationale=rationale,
    )


@pytest.fixture
def assessment():
    from analytics.decision.decision_models import (
        InvestmentDecisionAssessment, DecisionAction, DecisionConfidence, GateResult,
    )
    d = InvestmentDecisionAssessment(
        ticker="TEST.TO",
        company_name="Test Company",
        analysis_date="2026-09-30",
        action=DecisionAction.REDUCE,
        decision_confidence=DecisionConfidence.MEDIUM,
        executive_conclusion="Test.",
        business_quality_conclusion="Quality.",
        valuation_conclusion="Valuation.",
        portfolio_context_conclusion="Existing position.",
        valuation_zone="WAIT",
    )
    d.thesis_breakers = [
        _breaker("Sustained crude oil prices below $60/bbl for 12+ months", "MEDIUM"),
        _breaker("Credit rating downgrade by a major agency", "UNKNOWN", "No data."),
        _breaker("Regulatory tax increase on cigarettes", "HIGH"),
    ]
    d.gate_results = [
        GateResult(gate_number=5, gate_name="Adversarial Challenge", passed=True,
                   adversarial_risk="SEVERE", confidence="MEDIUM", summary="3 breakers."),
    ]
    return d


@pytest.fixture
def routed(monkeypatch, assessment):
    """Return a function reporting whether a question reaches the likelihood handler."""
    monkeypatch.setattr(R, "_answer_breaker_likelihood_question",
                        lambda *a, **k: _SENTINEL)

    def _go(question: str) -> bool:
        return R.render_followup(question, assessment) == _SENTINEL

    return _go


# ---------------------------------------------------------------------------
# 1. Ordinary questions must NOT be misrouted
# ---------------------------------------------------------------------------

ORDINARY = [
    "Why is the price so high?",                         # whole word, no breaker context
    "Why is the stock trading below my entry?",          # "low" inside "below"
    "Why is the valuation higher than last quarter?",    # "high" inside "higher"
    "Why does the report highlight FCF?",                # "high" inside "highlight"
    "Why is free cash flow per share lower than EPS?",   # "low" inside "lower"/"flow"
    "Why is the dividend yield low?",
    "Why is the margin so high this year?",
    "Why is the allowance for doubtful accounts growing?",   # "low" inside "allowance"
    "Why is the cash flow volatile?",                    # "low" inside "flow"
]


@pytest.mark.parametrize("question", ORDINARY)
def test_ordinary_question_not_routed_to_likelihood(routed, question):
    assert routed(question) is False


# ---------------------------------------------------------------------------
# 2. Genuine and paraphrased breaker-likelihood questions MUST reach the handler
# ---------------------------------------------------------------------------

GENUINE = [
    "Why is the crude oil price breaker MEDIUM?",
    "Why is the credit downgrade risk UNKNOWN?",
    "Why is the likelihood of a tax increase high?",
    "Why is the cigarette tax increase rated HIGH?",
    "Why is sustained crude oil below $50/barrel for 12+ months MEDIUM?",
]

PARAPHRASED = [
    "Why do you think oil prices staying below sixty dollars is medium probability?",
    "Why is a credit agency downgrade unknown?",
]


@pytest.mark.parametrize("question", GENUINE)
def test_genuine_likelihood_question_routed(routed, question):
    assert routed(question) is True


@pytest.mark.parametrize("question", PARAPHRASED)
def test_paraphrased_breaker_question_routed(routed, question):
    assert routed(question) is True


def test_paraphrase_without_any_breaker_words_is_not_routed(routed):
    """Documented limitation of option B: no stored-breaker words, no breaker vocabulary."""
    assert routed("Why is the chance of that regulation high?") is False


# ---------------------------------------------------------------------------
# 3. Gate 5 explanation routing preserved
# ---------------------------------------------------------------------------

def test_gate5_question_still_routes_to_gate5_handler(routed, assessment):
    assert routed("Why is Gate 5 HIGH?") is False
    out = R.render_followup("Why is Gate 5 HIGH?", assessment)
    assert out != _SENTINEL
    assert "Gate 5" in out


# ---------------------------------------------------------------------------
# 4. UNKNOWN likelihood contract (Phase 11B) + real handler output
# ---------------------------------------------------------------------------

def test_unknown_likelihood_preserved_in_real_output(assessment):
    out = R.render_followup("Why is the credit downgrade risk UNKNOWN?", assessment)
    assert "Thesis breaker: Credit rating downgrade by a major agency" in out
    assert "Likelihood:     UNKNOWN" in out
    assert "MEDIUM" not in out.split("Likelihood:")[1].splitlines()[0]


def test_real_handler_returns_matching_breaker_for_paraphrase(assessment):
    out = R.render_followup(
        "Why do you think oil prices staying below sixty dollars is medium probability?",
        assessment,
    )
    assert "Sustained crude oil prices below" in out
    assert "Likelihood:     MEDIUM" in out


def test_ordinary_question_does_not_return_breaker_block(assessment):
    out = R.render_followup("Why is free cash flow per share lower than EPS?", assessment)
    assert "Thesis breaker:" not in out
    assert "No thesis breakers are recorded" not in out


# ---------------------------------------------------------------------------
# 5. Fuzzy matcher: whole words, not substrings
# ---------------------------------------------------------------------------

def test_overlap_score_uses_whole_words_not_substrings():
    cond = "Sustained crude oil prices below $60/bbl for 12+ months"
    # "crudeoil" / "oilfield" / "belowground" contain the condition words as substrings only
    q_sub = R._word_set("why is crudeoil oilfield belowground medium")
    assert R._breaker_overlap_score(q_sub, cond) == 0
    q_whole = R._word_set("why are crude oil prices medium")
    assert R._breaker_overlap_score(q_whole, cond) >= 3


def test_plural_folding():
    assert R._word_set("months prices") >= {"month", "price"}
