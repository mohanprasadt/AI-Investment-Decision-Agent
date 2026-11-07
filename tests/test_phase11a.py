"""
Phase 11A Tests
===============
Covers all 12 test requirements from the Phase 11A specification:

  1.  CAGR label: 3yr window called correctly when 5yr baseline unavailable
  2.  CAGR label: 5yr label when 5 full years available
  3.  CAGR label: "unavailable" when fewer than 2 data points
  4.  Dividend yield: trailingAnnualDividendYield (decimal) used when available
  5.  Dividend yield: dividendYield pre-multiplied guard (>100% → warning)
  6.  Dividend yield: dividendYield decimal fallback when trailing absent
  7.  ROIC: populated from NOPAT/InvestedCapital when data available
  8.  ROIC: falls back gracefully when Invested Capital absent
  9.  ROIC: annual_roic multi-year dict populated correctly
  10. Decision Trace: build_decision_trace returns correct gate count
  11. Decision Trace: render_decision_trace contains final action
  12. Decision Trace: _answer_why includes trace text
"""

from __future__ import annotations

import pytest
from typing import Dict, Optional


# ---------------------------------------------------------------------------
# 11A-3A: CAGR labeling (tests 1-3)
# ---------------------------------------------------------------------------

class TestCagrLabel:
    """Tests 1-3: cagr_period_label never misnames a shorter period."""

    def _make_series(self, years_back: int) -> Dict[int, float]:
        """Build a simple revenue series from (2025 - years_back) to 2025."""
        base = 100.0
        return {
            2025 - i: base * (1.05 ** (years_back - i))
            for i in range(years_back + 1)
        }

    def test_1_5yr_label_when_only_3yr_data_available(self):
        """5yr label must say '3yr CAGR ... [5yr baseline unavailable]' not '5yr CAGR'."""
        from analytics.financial_quality.calculations import cagr_period_label, extract_cagr_from_series

        series = self._make_series(3)          # 2022→2025 only
        val = extract_cagr_from_series(series, 5)
        label = cagr_period_label(series, 5, val)

        assert label is not None
        assert "5yr CAGR" not in label or "[5yr baseline unavailable]" in label, (
            f"Label incorrectly calls short window a 5yr CAGR: {label!r}"
        )
        assert "5yr baseline unavailable" in label, (
            f"Missing unavailability note: {label!r}"
        )
        assert "3yr" in label, f"Expected '3yr' in label: {label!r}"

    def test_2_5yr_label_when_full_5yr_data_available(self):
        """Full 5yr baseline → label says '5yr CAGR' with no caveat."""
        from analytics.financial_quality.calculations import cagr_period_label, extract_cagr_from_series

        series = self._make_series(5)          # 2020→2025
        val = extract_cagr_from_series(series, 5)
        label = cagr_period_label(series, 5, val)

        assert "5yr CAGR" in label, f"Expected '5yr CAGR' in label: {label!r}"
        assert "unavailable" not in label, f"Spurious unavailability: {label!r}"

    def test_3_label_when_fewer_than_2_datapoints(self):
        """Fewer than 2 points → 'unavailable (insufficient data)'."""
        from analytics.financial_quality.calculations import cagr_period_label

        label = cagr_period_label({2025: 100.0}, 5, None)
        assert "unavailable" in label, f"Expected 'unavailable' in: {label!r}"


# ---------------------------------------------------------------------------
# 11A-3B: Dividend yield normalization (tests 4-6)
# ---------------------------------------------------------------------------

class TestDividendYieldNormalization:
    """Tests 4-6: normalizer uses trailingAnnualDividendYield first."""

    def _normalize_with_info(self, info_overrides: dict) -> object:
        from data.ingestion.normalizer import normalize

        base_info = {
            "shortName": "TestCo", "exchange": "TSX", "currency": "CAD",
            "currentPrice": 50.0, "marketCap": 1e10,
            "dividendYield": None, "trailingAnnualDividendYield": None,
            "dividendRate": None, "payoutRatio": None,
        }
        base_info.update(info_overrides)
        return normalize("TEST.TO", base_info, {}, is_etf=False)

    def test_4_trailing_decimal_used_when_available(self):
        """trailingAnnualDividendYield=0.0361 → current_yield_pct ≈ 3.61%."""
        m = self._normalize_with_info({
            "dividendYield": 3.72,                   # wrong format — must be ignored
            "trailingAnnualDividendYield": 0.036102,
        })
        assert m.dividend.current_yield_pct is not None
        assert abs(m.dividend.current_yield_pct - 3.6102) < 0.02, (
            f"Expected ~3.61%, got {m.dividend.current_yield_pct}"
        )

    def test_5_premultiplied_dividendyield_guarded(self):
        """dividendYield=3.72 (percentage) with no trailing → stored as ~3.72%, not 372%."""
        m = self._normalize_with_info({
            "dividendYield": 3.72,
            "trailingAnnualDividendYield": None,
        })
        assert m.dividend.current_yield_pct is not None
        assert m.dividend.current_yield_pct < 100, (
            f"Yield stored as {m.dividend.current_yield_pct}% — looks like pre-multiplication bug"
        )

    def test_6_dividendyield_decimal_fallback(self):
        """dividendYield=0.037 (decimal) with no trailing → current_yield_pct ≈ 3.7%."""
        m = self._normalize_with_info({
            "dividendYield": 0.037,
            "trailingAnnualDividendYield": None,
        })
        assert m.dividend.current_yield_pct is not None
        assert abs(m.dividend.current_yield_pct - 3.7) < 0.5, (
            f"Expected ~3.7%, got {m.dividend.current_yield_pct}"
        )


# ---------------------------------------------------------------------------
# 11A-3C: ROIC implementation (tests 7-9)
# ---------------------------------------------------------------------------

class TestRoicImplementation:
    """Tests 7-9: ROIC computed from NOPAT/InvestedCapital."""

    def _make_financials(
        self,
        include_invested_capital: bool = True,
    ) -> dict:
        """Minimal synthetic financials for ROIC computation."""
        income = {
            "Operating Income": {2023: 1_000_000, 2024: 1_100_000},
            "Tax Provision":    {2023:   200_000, 2024:   220_000},
            "Pretax Income":    {2023: 1_000_000, 2024: 1_100_000},
            "Total Revenue":    {2023: 5_000_000, 2024: 5_500_000},
            "Net Income":       {2023:   800_000, 2024:   880_000},
        }
        balance: dict = {
            "Total Assets": {2023: 10_000_000, 2024: 11_000_000},
            "Total Debt":   {2023:  2_000_000, 2024:  2_200_000},
            "Cash And Cash Equivalents": {2023: 500_000, 2024: 600_000},
        }
        if include_invested_capital:
            balance["Invested Capital"] = {2023: 8_000_000, 2024: 8_800_000}

        cashflow = {
            "Total Cash From Operating Activities": {2023: 900_000, 2024: 1_000_000},
            "Capital Expenditures": {2023: -200_000, 2024: -250_000},
        }
        return {
            "income_stmt": income,
            "balance_sheet": balance,
            "cash_flow": cashflow,
            "_fetch_success": True,
        }

    def _normalize(self, include_invested_capital: bool = True) -> object:
        from data.ingestion.normalizer import normalize

        info = {
            "shortName": "ROICTestCo", "exchange": "NYSE", "currency": "USD",
            "currentPrice": 100.0, "marketCap": 1e9,
            "dividendYield": None, "trailingAnnualDividendYield": None,
            "dividendRate": None, "payoutRatio": None,
        }
        fin = self._make_financials(include_invested_capital)
        return normalize("ROIC.US", info, fin, is_etf=False)

    def test_7_roic_populated_from_nopat_invested_capital(self):
        """ROIC.current set to a plausible % when InvestedCapital data available."""
        m = self._normalize(include_invested_capital=True)
        assert m.roic.current is not None, "ROIC.current should be populated"
        # NOPAT 2024 = 1_100_000 * (1 - 220k/1100k) = 880_000
        # ROIC = 880_000 / 8_800_000 = 10.0%
        assert abs(m.roic.current - 10.0) < 1.0, (
            f"ROIC.current expected ~10%, got {m.roic.current:.2f}%"
        )

    def test_8_roic_graceful_fallback_when_no_invested_capital(self):
        """When Invested Capital absent, ROIC.current is None and note explains."""
        m = self._normalize(include_invested_capital=False)
        assert m.roic.current is None, (
            "ROIC.current should be None when Invested Capital unavailable"
        )
        assert m.roic.calculation_note, "calculation_note should explain missing data"
        assert "unavailable" in m.roic.calculation_note.lower(), (
            f"Expected 'unavailable' in note: {m.roic.calculation_note!r}"
        )

    def test_9_annual_roic_multi_year(self):
        """annual_roic should have an entry for each year where data overlaps."""
        m = self._normalize(include_invested_capital=True)
        assert len(m.roic.annual_roic) >= 2, (
            f"Expected ≥2 annual ROIC entries, got {m.roic.annual_roic}"
        )


# ---------------------------------------------------------------------------
# 11A-1 & 11A-2: Decision Trace (tests 10-12)
# ---------------------------------------------------------------------------

class TestDecisionTrace:
    """Tests 10-12: build_decision_trace, render_decision_trace, _answer_why."""

    def _make_assessment(self) -> object:
        """Minimal InvestmentDecisionAssessment for trace tests."""
        from analytics.decision.decision_models import (
            InvestmentDecisionAssessment, DecisionAction, DecisionConfidence,
            GateResult,
        )
        assessment = InvestmentDecisionAssessment(
            ticker="TEST.TO",
            company_name="Test Company",
            analysis_date="2026-09-29",
            action=DecisionAction.REDUCE,
            decision_confidence=DecisionConfidence.HIGH,
            executive_conclusion="Test conclusion.",
            business_quality_conclusion="Quality is good.",
            valuation_conclusion="Trading above fair value.",
            portfolio_context_conclusion="Existing 8% position.",
        )
        assessment.gate_results = [
            GateResult(
                gate_number=1, gate_name="Business Understanding",
                passed=True, confidence="HIGH",
                summary="Business model understood.",
                supporting_evidence=["Clear moat"],
                contradictory_evidence=[],
                data_gaps=[],
            ),
            GateResult(
                gate_number=2, gate_name="Financial Quality",
                passed=True, quality_tier="GOOD", confidence="MEDIUM",
                summary="GOOD quality tier.",
                supporting_evidence=["Strong FCF"],
                contradictory_evidence=["Revenue declining"],
                data_gaps=[],
            ),
            GateResult(
                gate_number=3, gate_name="Valuation",
                passed=True, confidence="MEDIUM",
                summary="Above fair value.",
                supporting_evidence=[],
                contradictory_evidence=["Trading at premium"],
                data_gaps=[],
            ),
            GateResult(
                gate_number=4, gate_name="Portfolio Context",
                passed=True, confidence="HIGH",
                summary="Existing 8.87% position.",
                supporting_evidence=["Dividend income"],
                contradictory_evidence=[],
                data_gaps=[],
            ),
            GateResult(
                gate_number=5, gate_name="Adversarial Challenge",
                passed=False, adversarial_risk="SEVERE", confidence="MEDIUM",
                summary="4 thesis breakers at MEDIUM likelihood.",
                supporting_evidence=[],
                contradictory_evidence=["Regulatory risk", "Oil price exposure"],
                data_gaps=[],
            ),
        ]
        return assessment

    def test_10_build_trace_returns_correct_gate_count(self):
        """build_decision_trace should return one GateTraceLine per gate."""
        from analytics.decision.decision_trace import build_decision_trace

        assessment = self._make_assessment()
        trace = build_decision_trace(assessment)
        assert len(trace.gate_lines) == 5, (
            f"Expected 5 gate lines, got {len(trace.gate_lines)}"
        )
        assert trace.final_action == "REDUCE"
        assert trace.ticker == "TEST.TO"

    def test_11_render_trace_contains_final_action(self):
        """render_decision_trace output must include the final action string."""
        from analytics.decision.decision_trace import build_decision_trace, render_decision_trace

        assessment = self._make_assessment()
        trace = build_decision_trace(assessment)
        rendered = render_decision_trace(trace)

        assert "REDUCE" in rendered, f"Final action not in rendered trace: {rendered[:200]}"
        assert "Gate 1" in rendered or "①" in rendered, "Gate 1 missing from trace"
        assert "Gate 5" in rendered or "⑤" in rendered, "Gate 5 missing from trace"

    def test_12_answer_why_includes_trace(self):
        """_answer_why must include decision trace text, not just narrative."""
        from analytics.agent.renderer import _answer_why

        assessment = self._make_assessment()
        # Attach labels expected by _answer_why
        assessment.business_quality_label = "GOOD"
        assessment.valuation_attractiveness_label = "EXPENSIVE"
        assessment.philosophy_alignment_notes = []
        assessment.data_freshness = None

        result = _answer_why(assessment)
        assert "DECISION TRACE" in result, (
            f"Decision trace header missing from _answer_why output: {result[:400]}"
        )
        assert "REDUCE" in result, "Final action missing from _answer_why output"
