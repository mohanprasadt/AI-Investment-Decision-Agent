"""
Phase 9.2 Regression Tests
===========================
Two focused test classes covering the two fixes in Phase 9.2:

  A. ValuationBuilder unit-scaling regression (ITC.NS-style large share-count ticker)
  B. Follow-up Q&A routing and growth/attractiveness renderer

Run with:  pytest tests/test_phase92.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import Optional, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Helpers shared by both test classes
# ---------------------------------------------------------------------------

def _make_fq_item(classification="Strong", data_available=True):
    """Minimal FinancialQualityDimension stub."""
    item = MagicMock()
    item.classification = classification
    item.data_available = data_available
    return item


def _make_financial_quality():
    """Minimal FinancialQualityAssessment stub (all dims stubbed)."""
    fq = MagicMock()
    for dim in ("roic", "revenue_growth", "margins", "free_cash_flow",
                "balance_sheet", "dividend", "earnings_quality"):
        setattr(fq, dim, _make_fq_item())
    fq.free_cash_flow.data_available = False   # avoids needing fcf_current
    fq.dividend.data_available = False
    fq.dividend.pays_dividend = False
    fq.earnings_quality.data_available = False
    fq.overall_classification = "STRONG"
    fq.strengths = []
    fq.concerns = []
    fq.is_financial_institution = False
    fq.is_emerging_company = False
    return fq


# ---------------------------------------------------------------------------
# Class A — Valuation scaling
# ---------------------------------------------------------------------------

class TestA_ValuationScaling:
    """
    Regression tests proving that ValuationBuilder converts all financial-statement
    quantities (FCF, revenue, debt, cash) from absolute yfinance units to millions,
    consistent with shares_outstanding (which is also stored in millions).

    The bug: ₹157,318,743 per-share for ITC.NS — ~10⁶× the correct value —
    caused by absolute FCF / millions-shares in simple_dcf().

    ITC.NS-like inputs:
      - Shares: 12,500,000,000 (12.5 B) → after fix: 12,500 M
      - FCF: 200,000,000,000 INR (200 B) → after fix: 200,000 M
      - Revenue: 700,000,000,000 INR → after fix: 700,000 M
      - Debt: 50,000,000,000 INR → after fix: 50,000 M
    """

    def _build_metrics(
        self,
        fcf_current: float = 200e9,
        annual_fcf: Optional[Dict] = None,
        revenue_series: Optional[Dict] = None,
        total_debt: float = 50e9,
        net_debt: float = 10e9,
    ):
        """Build a CompanyFinancialMetrics mock with ITC.NS-like absolute-unit values."""
        m = MagicMock()

        # Revenue (absolute INR)
        rev = annual_fcf or {2022: 600e9, 2023: 650e9, 2024: 700e9}
        rev_series = revenue_series or {2022: 600e9, 2023: 650e9, 2024: 700e9}
        rg = MagicMock()
        rg.annual_revenues = rev_series
        rg.cagr_3yr = 7.0
        m.revenue_growth = rg

        # FCF (absolute INR)
        fcf_m = MagicMock()
        fcf_m.fcf_current = fcf_current
        fcf_m.annual_fcf = annual_fcf or {2022: 180e9, 2023: 190e9, 2024: 200e9}
        m.free_cash_flow = fcf_m

        # Margins
        mg = MagicMock()
        mg.operating_margin = 30.0
        m.margins = mg

        # Debt (absolute INR)
        db = MagicMock()
        db.interest_bearing_debt = total_debt
        db.net_debt = net_debt
        m.debt = db

        # EV / EBITDA
        m.enterprise_value = 2_000e9   # absolute INR
        m.ev_ebitda = 25.0

        # Market cap (absolute)
        m.market_cap = 5_625e9

        return m

    def _build_load_result(self, shares_outstanding: int = 12_500_000_000):
        """Build a DataLoadResult mock."""
        lr = MagicMock()
        lr.ticker = "ITC.NS"
        lr.company_name = "ITC Limited"
        lr.current_price = 450.0      # INR per share
        lr.price_currency = "INR"
        lr.price_date = "2026-08-10"
        lr.metrics = self._build_metrics()
        lr.supplemental = {
            "shares_outstanding": shares_outstanding,
            "trailing_eps": 15.0,         # INR per share — already per-share, no conversion
            "book_value_per_share": 80.0,  # INR per share
            "analyst_forward_eps": 17.0,
        }
        return lr

    def test_fcf_ttm_stored_in_millions(self):
        """fcf_ttm.value must be in millions, not absolute INR."""
        from analytics.agent.valuation_builder import build_valuation_input

        lr = self._build_load_result()
        vi = build_valuation_input(lr, analysis_date="2026-08-10")

        assert vi.fcf_ttm is not None, "fcf_ttm must be populated"
        # Absolute INR was 200e9; after ÷1e6 → 200,000
        assert abs(vi.fcf_ttm.value - 200_000.0) < 1.0, (
            f"Expected fcf_ttm ≈ 200,000 M INR, got {vi.fcf_ttm.value:.2f}"
        )

    def test_fcf_history_stored_in_millions(self):
        """Every entry in fcf_history must be in millions."""
        from analytics.agent.valuation_builder import build_valuation_input

        lr = self._build_load_result()
        vi = build_valuation_input(lr, analysis_date="2026-08-10")

        assert vi.fcf_history, "fcf_history must be populated"
        for yr, val in vi.fcf_history.items():
            assert val < 1_000_000, (
                f"fcf_history[{yr}] = {val:.0f} — looks like absolute units, expected millions"
            )

    def test_fcf_normalized_stored_in_millions(self):
        """3-year normalised FCF must be in millions."""
        from analytics.agent.valuation_builder import build_valuation_input

        lr = self._build_load_result()
        vi = build_valuation_input(lr, analysis_date="2026-08-10")

        assert vi.fcf_normalized is not None, "fcf_normalized must be populated"
        # avg of 180,000 + 190,000 + 200,000 = 190,000 M
        assert abs(vi.fcf_normalized.value - 190_000.0) < 1.0, (
            f"Expected fcf_normalized ≈ 190,000 M INR, got {vi.fcf_normalized.value:.2f}"
        )

    def test_revenue_stored_in_millions(self):
        """revenue.value must be in millions."""
        from analytics.agent.valuation_builder import build_valuation_input

        lr = self._build_load_result()
        vi = build_valuation_input(lr, analysis_date="2026-08-10")

        assert vi.revenue is not None
        assert abs(vi.revenue.value - 700_000.0) < 1.0, (
            f"Expected revenue ≈ 700,000 M INR, got {vi.revenue.value:.2f}"
        )

    def test_total_debt_stored_in_millions(self):
        """total_debt.value must be in millions."""
        from analytics.agent.valuation_builder import build_valuation_input

        lr = self._build_load_result()
        vi = build_valuation_input(lr, analysis_date="2026-08-10")

        assert vi.total_debt is not None
        assert abs(vi.total_debt.value - 50_000.0) < 1.0, (
            f"Expected total_debt ≈ 50,000 M INR, got {vi.total_debt.value:.2f}"
        )

    def test_cash_stored_in_millions(self):
        """cash_and_equivalents.value must be in millions."""
        from analytics.agent.valuation_builder import build_valuation_input

        lr = self._build_load_result()
        vi = build_valuation_input(lr, analysis_date="2026-08-10")

        # cash = total_debt - net_debt = 50B - 10B = 40B → 40,000 M
        assert vi.cash_and_equivalents is not None
        assert abs(vi.cash_and_equivalents.value - 40_000.0) < 1.0, (
            f"Expected cash ≈ 40,000 M INR, got {vi.cash_and_equivalents.value:.2f}"
        )

    def test_shares_outstanding_in_millions(self):
        """shares_outstanding.value must be in millions (pre-existing behaviour, unchanged)."""
        from analytics.agent.valuation_builder import build_valuation_input

        lr = self._build_load_result()
        vi = build_valuation_input(lr, analysis_date="2026-08-10")

        assert vi.shares_outstanding is not None
        assert abs(vi.shares_outstanding.value - 12_500.0) < 0.1, (
            f"Expected shares ≈ 12,500 M, got {vi.shares_outstanding.value:.2f}"
        )

    def test_eps_ttm_not_scaled(self):
        """
        EPS from yfinance is already per-share (not an aggregate).
        ValuationBuilder must NOT divide it by 1e6.
        """
        from analytics.agent.valuation_builder import build_valuation_input

        lr = self._build_load_result()
        vi = build_valuation_input(lr, analysis_date="2026-08-10")

        assert vi.eps_ttm is not None
        assert abs(vi.eps_ttm.value - 15.0) < 0.01, (
            f"EPS must remain 15.0 INR/share, got {vi.eps_ttm.value}"
        )

    def test_dcf_per_share_realistic_range(self):
        """
        End-to-end: with correctly scaled inputs, the DCF must produce a per-share
        value in a plausible range for an INR-denominated stock near ₹450.

        Sanity bounds: ₹100 – ₹5,000 per share.
        Before the fix: ₹157,318,743 (157 million per share).
        """
        from analytics.agent.valuation_builder import build_valuation_input
        from analytics.valuation.dcf_engine import run_dcf

        lr = self._build_load_result()
        vi = build_valuation_input(lr, analysis_date="2026-08-10")

        result = run_dcf(vi)

        assert result.is_valid(), (
            f"DCF should produce valid output; reliability={result.reliability}, "
            f"note={result.reliability_note}"
        )
        assert result.base_value is not None
        assert 100 <= result.base_value <= 5_000, (
            f"DCF base value {result.base_value:.2f} INR/share is outside plausible range "
            f"[100, 5000]. This likely indicates a unit-scaling bug."
        )
        # Bear < Base < Bull ordering must hold
        assert result.bear_value < result.base_value < result.bull_value


# ---------------------------------------------------------------------------
# Class B — Follow-up Q&A routing and growth/attractiveness renderer
# ---------------------------------------------------------------------------

class TestB_FollowupRouting:
    """
    Regression tests for the follow-up routing and growth/attractiveness handler.

    Before the fix:
      "ITC.NS has a FMCG division ... Aren't they growing to make this company
       more attractive?" → classified INTENT_ANALYZE → re-rendered the full
       assessment → silently ignored the user's actual question.

    After the fix:
      1. The intent parser surfaces has_analyze_verb=False for this message.
      2. _handle_analyze routes to _handle_followup when no analyze verb found
         and the ticker matches the cache.
      3. render_followup routes growth/attractiveness keywords to
         _answer_growth_attractiveness.
      4. That handler either surfaces stored evidence or explicitly states
         that new research is required — never invents facts.
    """

    # ------------------------------------------------------------------
    # Intent-parser tests
    # ------------------------------------------------------------------

    def test_intent_has_analyze_verb_false_for_conceptual_question(self):
        """A conceptual question about a ticker must set has_analyze_verb=False."""
        from analytics.agent.intent_parser import parse_intent, INTENT_ANALYZE

        q = "ITC.NS has a FMCG division as well as a Tech company inside it. Aren't they growing to make this company more attractive?"
        intent = parse_intent(q)

        assert intent.intent_type == INTENT_ANALYZE   # still sees ticker
        assert intent.ticker is not None
        assert not intent.has_analyze_verb, (
            "has_analyze_verb must be False — question contains no analyze verb"
        )

    def test_intent_has_analyze_verb_true_for_analyze_request(self):
        """An explicit analyze request must set has_analyze_verb=True."""
        from analytics.agent.intent_parser import parse_intent, INTENT_ANALYZE

        intent = parse_intent("Analyze ITC.NS for me")
        assert intent.intent_type == INTENT_ANALYZE
        assert intent.has_analyze_verb

    def test_intent_has_analyze_verb_true_for_run_request(self):
        """'Run an analysis on CNR.TO' must set has_analyze_verb=True."""
        from analytics.agent.intent_parser import parse_intent, INTENT_ANALYZE

        intent = parse_intent("Run an analysis on CNR.TO")
        assert intent.intent_type == INTENT_ANALYZE
        assert intent.has_analyze_verb

    # ------------------------------------------------------------------
    # Agent routing tests
    # ------------------------------------------------------------------

    def _build_assessment(self, action_value="WAIT_INSUFFICIENT_EVIDENCE",
                          research_gaps=None):
        """Build a minimal InvestmentDecisionAssessment stub."""
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence
        )
        d = InvestmentDecisionAssessment(
            ticker="ITC.NS",
            company_name="ITC Limited",
            analysis_date="2026-08-10",
            current_price=450.0,
            price_currency="INR",
        )
        d.action = DecisionAction[action_value]
        d.decision_confidence = DecisionConfidence.LOW
        d.research_gaps = research_gaps or [
            "growth", "moat", "industry", "management", "risk", "bull/bear"
        ]
        d.why_attractive_or_unattractive = ""
        d.biggest_reason_to_invest = ""
        d.business_thesis = ""
        d.supporting_evidence = []
        return d

    def test_conceptual_question_routes_to_followup_not_reanalysis(self):
        """
        After ITC.NS is analyzed, a conceptual question about it must NOT
        silently re-render the full assessment.
        It must reach render_followup (we verify via the response content).
        """
        from analytics.agent.investment_agent import InvestmentAgent
        from analytics.decision.decision_synthesizer import make_investment_decision

        agent = InvestmentAgent()

        # Seed the cache by running an analysis programmatically
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
        agent._session.last_assessment = self._build_assessment()
        agent._session.last_ticker = "ITC.NS"

        response = agent.chat(
            "ITC.NS has a FMCG division as well as a Tech company inside it. "
            "Aren't they growing to make this company more attractive?"
        )

        # Response must NOT be the "I understand you want to analyze" template
        assert "I understand you want to analyze" not in response, (
            "Conceptual question must not trigger the re-analysis prompt"
        )
        # It must acknowledge the growth / evidence question
        assert any(kw in response.lower() for kw in (
            "growth", "attractiveness", "research", "missing", "not assessed"
        )), "Response must address growth/attractiveness or explain the gap"

    def test_explicit_analyze_still_reruns_pipeline(self):
        """
        An explicit 'Analyze ITC.NS' with cached inputs must still re-run the pipeline
        (not route to follow-up).
        """
        from analytics.agent.investment_agent import InvestmentAgent
        from unittest.mock import patch, MagicMock

        agent = InvestmentAgent()
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
        agent._session.last_assessment = self._build_assessment()
        agent._session.last_ticker = "ITC.NS"

        with patch("analytics.agent.investment_agent.make_investment_decision") as mock_decide, \
             patch("analytics.agent.investment_agent.render_assessment") as mock_render:
            mock_decide.return_value = self._build_assessment()
            mock_render.return_value = "RENDERED_ASSESSMENT"
            response = agent.chat("Analyze ITC.NS")

        mock_decide.assert_called_once()   # pipeline must be re-run
        assert response == "RENDERED_ASSESSMENT"

    # ------------------------------------------------------------------
    # Renderer tests
    # ------------------------------------------------------------------

    def test_growth_renderer_on_wait_state_mentions_gap(self):
        """
        When no research was done (WAIT_INSUFFICIENT_EVIDENCE), the growth handler
        must explicitly state that research is required and list the missing dims.
        """
        from analytics.agent.renderer import render_followup

        d = self._build_assessment(
            action_value="WAIT_INSUFFICIENT_EVIDENCE",
            research_gaps=["growth", "moat", "industry", "management"],
        )
        response = render_followup(
            "ITC.NS has a FMCG division. Aren't they growing?", d
        )

        assert "not assessed" in response.lower() or "not completed" in response.lower() or "not available" in response.lower(), (
            "Response must state that growth was not assessed"
        )
        # Must mention the research gap dims
        assert "growth" in response.lower()

    def test_growth_renderer_surfaces_stored_evidence(self):
        """
        When the assessment contains growth evidence, the renderer must surface it
        without inventing new facts.
        """
        from analytics.agent.renderer import render_followup
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
            DecisionEvidenceItem, EvidenceStrength,
        )

        d = InvestmentDecisionAssessment(
            ticker="ITC.NS",
            company_name="ITC Limited",
            analysis_date="2026-08-10",
            current_price=450.0,
            price_currency="INR",
        )
        d.action = DecisionAction.START_SMALL
        d.decision_confidence = DecisionConfidence.MEDIUM
        d.why_attractive_or_unattractive = "FMCG segment growing at ~10% annually with strong brand moat."
        d.biggest_reason_to_invest = "Diversified revenue with FMCG, agri, paper, hotels — FMCG now >60% of revenue."
        d.business_thesis = "ITC is transitioning from a tobacco conglomerate to a consumer FMCG company."
        d.supporting_evidence = [
            DecisionEvidenceItem(
                source_phase="business_research",
                dimension="growth",
                observation="FMCG revenue CAGR 12% over 5 years; segment expanding margins.",
                strength=EvidenceStrength.STRONG,
                supports_thesis=True,
            )
        ]
        d.research_gaps = []

        response = render_followup(
            "ITC.NS has a FMCG division. Aren't they growing?", d
        )

        # Must surface the stored evidence
        assert "fmcg" in response.lower() or "growing" in response.lower() or "10%" in response
        # Must not invent facts — check the architecture boundary disclaimer
        assert "no new facts" in response.lower() or "stored" in response.lower()

    def test_growth_renderer_does_not_invent_facts(self):
        """
        The growth handler must never produce a response that asserts facts
        not present in the stored assessment.
        When evidence is empty and action is WAIT, it must say research is needed.
        """
        from analytics.agent.renderer import _answer_growth_attractiveness
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
        )

        d = InvestmentDecisionAssessment(
            ticker="ITC.NS",
            company_name="ITC Limited",
            analysis_date="2026-08-10",
        )
        d.action = DecisionAction.WAIT_INSUFFICIENT_EVIDENCE
        d.decision_confidence = DecisionConfidence.LOW
        d.why_attractive_or_unattractive = ""
        d.biggest_reason_to_invest = ""
        d.business_thesis = ""
        d.supporting_evidence = []
        d.research_gaps = ["growth", "moat", "industry"]

        response = _answer_growth_attractiveness(d)

        # Must not contain invented analysis
        assert "fmcg segment is" not in response.lower()
        assert "tech subsidiary is" not in response.lower()
        # Must contain the gap/research-required signal
        assert "research" in response.lower() or "not" in response.lower()

    def test_growth_keywords_route_to_growth_handler(self):
        """
        All growth/attractiveness/segment keywords must reach _answer_growth_attractiveness,
        not the default executive-conclusion block.
        """
        from analytics.agent.renderer import render_followup
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
        )

        d = InvestmentDecisionAssessment(
            ticker="ITC.NS",
            company_name="ITC Limited",
            analysis_date="2026-08-10",
        )
        d.action = DecisionAction.WAIT_INSUFFICIENT_EVIDENCE
        d.decision_confidence = DecisionConfidence.LOW
        d.why_attractive_or_unattractive = ""
        d.biggest_reason_to_invest = ""
        d.business_thesis = ""
        d.supporting_evidence = []
        d.research_gaps = ["growth"]
        d.executive_conclusion = "ORIGINAL EXECUTIVE CONCLUSION"

        questions = [
            "Aren't they growing to make this company more attractive?",
            "What about the FMCG division growth?",
            "Is the tech subsidiary growing?",
            "How attractive is this segment?",
        ]
        for q in questions:
            resp = render_followup(q, d)
            # Must NOT fall through to the bare executive conclusion default
            assert "ORIGINAL EXECUTIVE CONCLUSION" not in resp, (
                f"Question '{q}' fell through to default; expected growth handler"
            )
            assert "Ask me about" not in resp, (
                f"Question '{q}' hit the bare default block"
            )
