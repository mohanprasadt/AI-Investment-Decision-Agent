"""
Phase 9.6 Regression Tests — FCF Calculation Chain Surfacing
=============================================================
Ensures the annual OCF / capex / FCF breakdown plus shares outstanding
is surfaced in the FCF/EPS follow-up response, using real ITC.NS-shaped data.

Test groups:
  A — InvestmentDecisionAssessment carries the two new Phase 9.6 fields
  B — make_investment_decision populates breakdown from fcf_raw_metrics
  C — _answer_fcf_eps shows the full annual chain when breakdown is present
  D — FCF/share calculation chain (avg → ÷ shares → consistent with stored)
  E — No-fabrication: only stored facts; gap attribution stays hedged
  F — Graceful fallback when Phase 9.6 fields are absent
  G — Non-regression: Phase 9.5 tests and other follow-ups unaffected

Run:  pytest tests/test_phase96.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from dataclasses import dataclass, field
from typing import Dict, Optional

from analytics.decision.decision_models import (
    InvestmentDecisionAssessment, DecisionAction,
)


# ---------------------------------------------------------------------------
# ITC.NS constants (from real financial statements / cache)
# ---------------------------------------------------------------------------

ITC_OCF   = {2026: 184_643_100_000.0, 2025: 176_270_400_000.0,
             2024: 171_788_600_000.0, 2023: 188_775_500_000.0}
ITC_CAPEX = {2026: -21_828_900_000.0, 2025: -22_787_000_000.0,
             2024: -35_625_300_000.0, 2023: -27_429_900_000.0}
ITC_FCF   = {yr: ITC_OCF[yr] + ITC_CAPEX[yr] for yr in ITC_OCF}
# {2026: 162_814_200_000, 2025: 153_483_400_000, 2024: 136_163_300_000, 2023: 161_345_600_000}

ITC_SHARES     = 12_529_468_231.0   # from supplemental["shares_outstanding"]
ITC_FCF_PS     = 12.04              # stored from valuation engine (Phase 9.5)
ITC_EPS        = 15.83              # trailingEps


# ---------------------------------------------------------------------------
# Minimal FreeCashFlowMetrics stub (duck-typed)
# ---------------------------------------------------------------------------

@dataclass
class _FakeFCFMetrics:
    """Minimal duck-type stand-in for FreeCashFlowMetrics."""
    annual_fcf:   Dict[int, float] = field(default_factory=dict)
    annual_capex: Dict[int, float] = field(default_factory=dict)


def _itc_fcf_metrics() -> _FakeFCFMetrics:
    return _FakeFCFMetrics(annual_fcf=dict(ITC_FCF), annual_capex=dict(ITC_CAPEX))


# ---------------------------------------------------------------------------
# Assessment fixture helpers
# ---------------------------------------------------------------------------

def _make_assessment(
    *,
    breakdown=None,
    shares=None,
    fcf_per_share_used=None,
    fcf_normalization_note="",
    eps_used_in_valuation=None,
) -> InvestmentDecisionAssessment:
    return InvestmentDecisionAssessment(
        ticker="ITC.NS",
        company_name="ITC Limited",
        analysis_date="2026-08-10",
        current_price=282.65,
        price_currency="INR",
        action=DecisionAction.WATCH,
        valuation_conclusion="Price above estimated fair value.",
        fcf_annual_breakdown=breakdown if breakdown is not None else [],
        fcf_shares_outstanding=shares,
        fcf_per_share_used=fcf_per_share_used,
        fcf_normalization_note=fcf_normalization_note,
        eps_used_in_valuation=eps_used_in_valuation,
    )


def _itc_full_assessment() -> InvestmentDecisionAssessment:
    """Assessment with all Phase 9.5 + 9.6 fields populated (ITC values)."""
    # Build breakdown same way the synthesizer does: sorted descending
    breakdown = []
    for yr in sorted(ITC_FCF.keys(), reverse=True):
        fcf_v   = ITC_FCF[yr]
        capex_v = ITC_CAPEX[yr]
        ocf_v   = fcf_v - capex_v
        breakdown.append({"year": yr, "ocf": ocf_v, "capex": capex_v, "fcf": fcf_v})
    return _make_assessment(
        breakdown=breakdown,
        shares=ITC_SHARES,
        fcf_per_share_used=ITC_FCF_PS,
        fcf_normalization_note="Derived: 3-year average FCF (3yr avg to 2026)",
        eps_used_in_valuation=ITC_EPS,
    )


def _render_fcf(d=None, question="why is fcf/share lower than eps") -> str:
    from analytics.agent.renderer import render_followup
    return render_followup(question, d or _itc_full_assessment())


# ---------------------------------------------------------------------------
# Class A — IDA carries Phase 9.6 fields
# ---------------------------------------------------------------------------

class TestA_ModelFields:

    def test_breakdown_defaults_empty(self):
        d = InvestmentDecisionAssessment(ticker="X", company_name="X", analysis_date="2026-08-10")
        assert d.fcf_annual_breakdown == []

    def test_shares_defaults_none(self):
        d = InvestmentDecisionAssessment(ticker="X", company_name="X", analysis_date="2026-08-10")
        assert d.fcf_shares_outstanding is None

    def test_breakdown_populated(self):
        d = _itc_full_assessment()
        assert len(d.fcf_annual_breakdown) == 4
        # most recent year first
        assert d.fcf_annual_breakdown[0]["year"] == 2026

    def test_breakdown_row_keys(self):
        d = _itc_full_assessment()
        row = d.fcf_annual_breakdown[0]
        assert set(row.keys()) == {"year", "ocf", "capex", "fcf"}

    def test_ocf_derived_correctly(self):
        """OCF = FCF − capex (capex is negative, so OCF = FCF + |capex|)."""
        d = _itc_full_assessment()
        row2026 = next(r for r in d.fcf_annual_breakdown if r["year"] == 2026)
        expected_ocf = ITC_FCF[2026] - ITC_CAPEX[2026]  # 162.8B - (-21.8B) = 184.6B
        assert abs(row2026["ocf"] - expected_ocf) < 1.0

    def test_shares_stored(self):
        d = _itc_full_assessment()
        assert d.fcf_shares_outstanding == pytest.approx(ITC_SHARES)

    def test_breakdown_in_to_dict(self):
        d = _itc_full_assessment()
        raw = d.to_dict()
        assert "fcf_annual_breakdown" in raw
        assert isinstance(raw["fcf_annual_breakdown"], list)
        assert len(raw["fcf_annual_breakdown"]) == 4

    def test_shares_in_to_dict(self):
        d = _itc_full_assessment()
        raw = d.to_dict()
        assert "fcf_shares_outstanding" in raw
        assert raw["fcf_shares_outstanding"] == pytest.approx(ITC_SHARES)


# ---------------------------------------------------------------------------
# Class B — make_investment_decision populates breakdown
# ---------------------------------------------------------------------------

class TestB_SynthesizerPopulation:

    def _run(self, fcf_metrics=None, shares=None):
        from analytics.decision.decision_synthesizer import make_investment_decision
        return make_investment_decision(
            ticker="ITC.NS",
            company_name="ITC Limited",
            analysis_date="2026-08-10",
            fcf_raw_metrics=fcf_metrics,
            fcf_shares_outstanding=shares,
        )

    def test_no_metrics_gives_empty_breakdown(self):
        d = self._run()
        assert d.fcf_annual_breakdown == []
        assert d.fcf_shares_outstanding is None

    def test_metrics_with_data_builds_breakdown(self):
        d = self._run(fcf_metrics=_itc_fcf_metrics(), shares=ITC_SHARES)
        assert len(d.fcf_annual_breakdown) > 0

    def test_breakdown_rows_have_correct_keys(self):
        d = self._run(fcf_metrics=_itc_fcf_metrics())
        for row in d.fcf_annual_breakdown:
            assert "year" in row and "ocf" in row and "capex" in row and "fcf" in row

    def test_2026_ocf_correct(self):
        d = self._run(fcf_metrics=_itc_fcf_metrics())
        row = next(r for r in d.fcf_annual_breakdown if r["year"] == 2026)
        assert abs(row["ocf"] - ITC_OCF[2026]) < 100.0   # within ₹100

    def test_2026_fcf_correct(self):
        d = self._run(fcf_metrics=_itc_fcf_metrics())
        row = next(r for r in d.fcf_annual_breakdown if r["year"] == 2026)
        assert abs(row["fcf"] - ITC_FCF[2026]) < 100.0

    def test_2024_high_capex_visible(self):
        """2024 had unusually high capex (₹35.6B vs ₹21-22B in other years)."""
        d = self._run(fcf_metrics=_itc_fcf_metrics())
        row = next(r for r in d.fcf_annual_breakdown if r["year"] == 2024)
        assert abs(row["capex"]) > 30_000_000_000    # > ₹30B absolute capex

    def test_shares_stored(self):
        d = self._run(fcf_metrics=_itc_fcf_metrics(), shares=ITC_SHARES)
        assert d.fcf_shares_outstanding == pytest.approx(ITC_SHARES)

    def test_empty_fcf_metrics_gives_empty_breakdown(self):
        d = self._run(fcf_metrics=_FakeFCFMetrics())   # empty dicts
        assert d.fcf_annual_breakdown == []


# ---------------------------------------------------------------------------
# Class C — Renderer shows the annual chain
# ---------------------------------------------------------------------------

class TestC_RendererChain:

    def test_all_recent_years_shown(self):
        out = _render_fcf()
        for yr in [2026, 2025, 2024]:
            assert str(yr) in out

    def test_ocf_2026_shown(self):
        out = _render_fcf()
        # 184_643_100_000 / 1e9 = 184.6
        assert "184.6" in out

    def test_capex_2026_shown(self):
        out = _render_fcf()
        # 21_828_900_000 / 1e9 = 21.8
        assert "21.8" in out

    def test_fcf_2026_shown(self):
        out = _render_fcf()
        # 162_814_200_000 / 1e9 = 162.8
        assert "162.8" in out

    def test_2024_high_capex_shown(self):
        out = _render_fcf()
        # 35_625_300_000 / 1e9 = 35.6
        assert "35.6" in out

    def test_avg_fcf_shown(self):
        out = _render_fcf()
        # 3-yr avg (2024-2026) = (162.8 + 153.5 + 136.2) / 3 ≈ 150.8B
        assert "150." in out   # 150.8 or 150.9 depending on rounding

    def test_shares_shown(self):
        out = _render_fcf()
        # 12_529_468_231 / 1e9 = 12.529
        assert "12.529" in out or "12.53" in out

    def test_fcf_per_share_shown(self):
        out = _render_fcf()
        assert "12.04" in out

    def test_eps_shown(self):
        out = _render_fcf()
        assert "15.83" in out

    def test_currency_prefix_shown(self):
        out = _render_fcf()
        assert "INR" in out

    def test_chain_section_header(self):
        out = _render_fcf()
        assert "FCF CALCULATION CHAIN" in out or "CALCULATION CHAIN" in out

    def test_structural_explanation_present(self):
        out = _render_fcf()
        assert "STRUCTURAL EXPLANATION" in out or "structural" in out.lower()


# ---------------------------------------------------------------------------
# Class D — FCF/share calculation chain consistency
# ---------------------------------------------------------------------------

class TestD_FcfPerShareChain:

    def test_computed_fcf_ps_consistent_with_stored(self):
        """avg(FCF 2024-2026) / shares ≈ stored ITC_FCF_PS (±5%)."""
        recent_fcf = [ITC_FCF[2026], ITC_FCF[2025], ITC_FCF[2024]]
        avg = sum(recent_fcf) / 3
        computed = avg / ITC_SHARES
        assert abs(computed - ITC_FCF_PS) / ITC_FCF_PS < 0.05

    def test_renderer_notes_consistency(self):
        out = _render_fcf()
        assert "consistent" in out.lower() or "12.04" in out

    def test_gap_value_shown(self):
        out = _render_fcf()
        gap = round(ITC_EPS - ITC_FCF_PS, 2)   # 3.79
        assert str(gap) in out or "3.79" in out

    def test_eps_minus_fcf_gap_labelled(self):
        out = _render_fcf()
        lower = out.lower()
        assert "gap" in lower or "difference" in lower


# ---------------------------------------------------------------------------
# Class E — No fabrication; gap attribution stays hedged
# ---------------------------------------------------------------------------

class TestE_NoFabrication:

    def test_capex_not_claimed_as_sole_driver(self):
        out = _render_fcf()
        lower = out.lower()
        assert "capex is the sole cause" not in lower
        assert "caused by capex" not in lower
        assert "capex alone" not in lower

    def test_hedge_language_present(self):
        """Renderer must note that per-share attribution of gap drivers is not stored."""
        out = _render_fcf()
        lower = out.lower()
        assert ("does not break" in lower or "not stored" in lower
                or "requires" in lower or "beyond what" in lower)

    def test_no_depreciation_per_share_invented(self):
        out = _render_fcf()
        assert "depreciation per share" not in out.lower()
        assert "amortisation per share" not in out.lower()

    def test_footer_cites_stored_assessment(self):
        out = _render_fcf()
        assert "stored" in out.lower()
        assert "ITC.NS" in out

    def test_no_new_financial_data_note(self):
        out = _render_fcf()
        lower = out.lower()
        assert "no new financial data" in lower or "source: stored" in lower


# ---------------------------------------------------------------------------
# Class F — Graceful fallback when Phase 9.6 fields absent
# ---------------------------------------------------------------------------

class TestF_Fallback:

    def test_no_breakdown_falls_to_phase95_section(self):
        d = _make_assessment(
            fcf_per_share_used=ITC_FCF_PS,
            eps_used_in_valuation=ITC_EPS,
        )
        out = _render_fcf(d)
        assert "12.04" in out
        assert "15.83" in out

    def test_no_breakdown_no_phase95_gives_not_available(self):
        d = _make_assessment()
        out = _render_fcf(d)
        lower = out.lower()
        assert "not available" in lower or "not stored" in lower or "no fcf" in lower

    def test_no_fabrication_when_breakdown_absent(self):
        d = _make_assessment()
        out = _render_fcf(d)
        assert "184.6" not in out
        assert "12.04" not in out

    def test_structural_explanation_always_shown(self):
        d = _make_assessment()
        out = _render_fcf(d)
        assert "EPS" in out and "FCF" in out

    def test_partial_breakdown_no_shares_still_renders(self):
        """Breakdown present but shares=None — table shows, per-share calc omitted."""
        breakdown = [{"year": 2026, "ocf": ITC_OCF[2026], "capex": ITC_CAPEX[2026], "fcf": ITC_FCF[2026]}]
        d = _make_assessment(breakdown=breakdown, shares=None)
        out = _render_fcf(d)
        assert "184.6" in out    # OCF visible
        assert "21.8" in out     # capex visible
        # shares line should not appear (no data)
        assert "12.529" not in out


# ---------------------------------------------------------------------------
# Class G — Non-regression
# ---------------------------------------------------------------------------

class TestG_NonRegression:

    def _d(self):
        return _itc_full_assessment()

    def test_watch_followup_unaffected(self):
        from analytics.agent.renderer import render_followup
        out = render_followup("why is it a watch?", self._d())
        assert out
        assert "FCF CALCULATION CHAIN" not in out

    def test_valuation_method_followup_unaffected(self):
        from analytics.agent.renderer import render_followup
        out = render_followup("explain the P/E valuation method", self._d())
        assert out
        assert "FCF CALCULATION CHAIN" not in out

    def test_phase95_test_still_passes_with_new_fields(self):
        """Phase 9.5 IDA fields still work alongside Phase 9.6 fields."""
        d = self._d()
        assert d.fcf_per_share_used == pytest.approx(ITC_FCF_PS)
        assert d.eps_used_in_valuation == pytest.approx(ITC_EPS)
        assert d.fcf_normalization_note != ""

    def test_to_json_round_trip(self):
        import json
        d = self._d()
        raw = json.loads(d.to_json())
        assert len(raw["fcf_annual_breakdown"]) == 4
        assert raw["fcf_shares_outstanding"] == pytest.approx(ITC_SHARES)
        assert raw["fcf_per_share_used"] == pytest.approx(ITC_FCF_PS)

    def test_synthesizer_without_new_params_still_works(self):
        """Calling make_investment_decision with no Phase 9.6 params is backward-compatible."""
        from analytics.decision.decision_synthesizer import make_investment_decision
        d = make_investment_decision(
            ticker="TEST", company_name="Test Co", analysis_date="2026-08-10"
        )
        assert d.fcf_annual_breakdown == []
        assert d.fcf_shares_outstanding is None
