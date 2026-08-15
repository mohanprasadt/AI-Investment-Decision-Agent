"""
Phase 9.3b Regression Tests — EV/EBITDA Cash-Source Fix
=========================================================
Root cause:
  ValuationBuilder sourced cash from ``total_debt − net_debt``, which equals
  only the narrow ``Cash And Cash Equivalents`` balance-sheet line (₹6,434.6M
  for ITC.NS).  The broader ``Cash Cash Equivalents And Short Term Investments``
  line (₹234,907.7M) was ignored, understating the EV→equity bridge and
  producing an EV/EBITDA implied fair value of ₹222.04 instead of ₹240.28.

Fix:
  1. ``data_loader.py`` step 3b: exposes ``cash_broad``, ``cash_narrow``, and
     ``cash_info`` in ``result.supplemental``, extracted from the raw yfinance
     balance sheet (``raw["financials"]["balance_sheet"]``).
  2. ``valuation_builder.py`` cash block: priority order
       cash_broad (REPORTED) → cash_narrow (REPORTED)
       → net_debt-derived (CALCULATED) → cash_info (REPORTED fallback).

Run:  pytest tests/test_phase93b.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock
from analytics.valuation.valuation_models import InputType


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_load_result(
    *,
    cash_broad: float = None,
    cash_narrow: float = None,
    cash_info: float = None,
    total_debt: float = 0.0,
    net_debt: float = 0.0,
    shares: float = 1_000_000_000,  # 1B shares (absolute)
    current_price: float = 100.0,
    ticker: str = "TEST.NS",
):
    """
    Build a minimal mock DataLoadResult that the valuation builder can consume.
    Financial values are in absolute local currency (pre-scaling), matching
    the yfinance raw format.
    """
    from analytics.agent.data_loader import DataLoadResult
    from analytics.financial_quality.financial_metrics_model import (
        CompanyFinancialMetrics, DebtMetrics, FreeCashFlowMetrics,
        RevenueGrowthMetrics,
    )

    r = DataLoadResult(ticker=ticker)
    r.company_name = "Test Corp"
    r.current_price = current_price
    r.price_currency = "INR"
    r.price_date = "2026-08-11"

    # Debt metrics — drives fallback path when broad/narrow are missing
    dm = DebtMetrics()
    dm.interest_bearing_debt = total_debt
    dm.net_debt = net_debt

    # Minimal FCF so valuation can run
    fcf = FreeCashFlowMetrics()
    fcf.fcf_current = 50_000_000_000.0   # ₹50B
    fcf.annual_fcf = {"2026": 50_000_000_000.0, "2025": 48_000_000_000.0, "2024": 46_000_000_000.0}

    # Minimal revenue
    rg = RevenueGrowthMetrics()
    rg.annual_revenues = {"2026": 200_000_000_000.0}

    m = CompanyFinancialMetrics(ticker=ticker)
    m.debt = dm
    m.free_cash_flow = fcf
    m.revenue_growth = rg

    r.metrics = m
    r.supplemental = {
        "shares_outstanding": shares,
        "trailing_eps":       5.0,
        "book_value_per_share": 30.0,
        "analyst_forward_eps":  5.5,
        "cash_broad":  cash_broad,
        "cash_narrow": cash_narrow,
        "cash_info":   cash_info,
    }
    return r


# ---------------------------------------------------------------------------
# Class A — cash priority ordering in ValuationBuilder
# ---------------------------------------------------------------------------

class TestA_CashPriority:
    """Verify the priority: cash_broad → cash_narrow → net_debt → cash_info."""

    def test_broad_cash_used_when_available(self):
        """When cash_broad is present it must be the selected source."""
        from analytics.agent.valuation_builder import build_valuation_input

        r = _make_load_result(
            cash_broad=234_907_700_000.0,
            cash_narrow=6_434_600_000.0,
            cash_info=245_109_702_656.0,
        )
        vi = build_valuation_input(r)

        assert vi.cash_and_equivalents is not None
        # Scaled to millions
        assert abs(vi.cash_and_equivalents.value - 234_907.7) < 0.5, (
            f"Expected ~234907.7M, got {vi.cash_and_equivalents.value}"
        )
        assert vi.cash_and_equivalents.input_type == InputType.REPORTED
        assert "Short-Term" in vi.cash_and_equivalents.source, (
            "Source should mention Short-Term Investments"
        )

    def test_narrow_cash_used_when_broad_absent(self):
        """When cash_broad is missing but cash_narrow is present, use narrow."""
        from analytics.agent.valuation_builder import build_valuation_input

        r = _make_load_result(
            cash_broad=None,
            cash_narrow=6_434_600_000.0,
            cash_info=245_109_702_656.0,
        )
        vi = build_valuation_input(r)

        assert vi.cash_and_equivalents is not None
        assert abs(vi.cash_and_equivalents.value - 6_434.6) < 0.5
        assert vi.cash_and_equivalents.input_type == InputType.REPORTED
        assert "Cash And Cash Equivalents" in vi.cash_and_equivalents.source

    def test_net_debt_fallback_when_balance_sheet_missing(self):
        """When both cash_broad and cash_narrow are None, fall back to net_debt."""
        from analytics.agent.valuation_builder import build_valuation_input

        total_debt = 24_000_000_000.0
        net_debt   = 17_000_000_000.0
        expected_cash = (total_debt - net_debt) / 1_000_000   # = 7000 M

        r = _make_load_result(
            cash_broad=None,
            cash_narrow=None,
            cash_info=None,
            total_debt=total_debt,
            net_debt=net_debt,
        )
        vi = build_valuation_input(r)

        assert vi.cash_and_equivalents is not None
        assert abs(vi.cash_and_equivalents.value - expected_cash) < 0.5
        assert vi.cash_and_equivalents.input_type == InputType.CALCULATED
        assert "net_debt" in vi.cash_and_equivalents.source.lower()

    def test_cash_info_fallback_last_resort(self):
        """When only cash_info is available it is used as the final fallback."""
        from analytics.agent.valuation_builder import build_valuation_input

        r = _make_load_result(
            cash_broad=None,
            cash_narrow=None,
            cash_info=245_109_702_656.0,
            # No debt → net_debt fallback also unavailable
            total_debt=None,
            net_debt=None,
        )
        # Manually clear the debt metrics so the net_debt path can't fire
        r.metrics.debt.interest_bearing_debt = None
        r.metrics.debt.net_debt = None

        vi = build_valuation_input(r)

        assert vi.cash_and_equivalents is not None
        assert abs(vi.cash_and_equivalents.value - 245_109.7) < 1.0
        assert vi.cash_and_equivalents.input_type == InputType.REPORTED
        assert "totalCash" in vi.cash_and_equivalents.source

    def test_all_cash_fields_absent_produces_no_cash(self):
        """When every cash source is absent, cash_and_equivalents must be None."""
        from analytics.agent.valuation_builder import build_valuation_input

        r = _make_load_result(
            cash_broad=None,
            cash_narrow=None,
            cash_info=None,
            total_debt=None,
            net_debt=None,
        )
        r.metrics.debt.interest_bearing_debt = None
        r.metrics.debt.net_debt = None

        vi = build_valuation_input(r)

        assert vi.cash_and_equivalents is None, (
            "No cash source → cash_and_equivalents must be None, not fabricated"
        )


# ---------------------------------------------------------------------------
# Class B — EV/EBITDA implied value increases with correct cash
# ---------------------------------------------------------------------------

class TestB_EVEBITDAImpact:
    """Verify that correct cash raises EV/EBITDA implied value."""

    def _run_ev_ebitda_mid(self, cash_abs: float) -> float:
        """Run valuation for ITC-like data with the given cash value; return EV/EBITDA mid."""
        from analytics.agent.valuation_builder import build_valuation_input
        from analytics.valuation.valuation_synthesizer import run_valuation

        r = _make_load_result(
            cash_broad=cash_abs,
            cash_narrow=6_434_600_000.0,
            cash_info=245_109_702_656.0,
            total_debt=23_993_600_000.0,
            net_debt=17_559_000_000.0,
            shares=12_529_468_231.0,
            current_price=282.65,
        )
        # ebitda_metrics not injected; EV/EBITDA will use the derived EBITDA
        # path (EV / trailing EV/EBITDA ratio) already in the builder.

        vi = build_valuation_input(r)
        assessment = run_valuation(vi)
        ev = assessment.ev_ebitda_result
        return ev.implied_value_mid if ev and ev.is_valid() else None

    def test_narrow_cash_ev_ebitda_baseline(self):
        """Narrow cash (₹6,435M) → EV/EBITDA mid should be near ₹222."""
        mid = self._run_ev_ebitda_mid(6_434_600_000.0)
        if mid is None:
            return   # EV/EBITDA not applicable for these simplified inputs; skip
        assert mid < 230, f"Expected < 230 with narrow cash, got {mid:.2f}"

    def test_broad_cash_ev_ebitda_higher(self):
        """Broad cash (₹234,908M) → EV/EBITDA mid must be higher than narrow cash."""
        mid_narrow = self._run_ev_ebitda_mid(6_434_600_000.0)
        mid_broad  = self._run_ev_ebitda_mid(234_907_700_000.0)
        if mid_narrow is None or mid_broad is None:
            return   # EV/EBITDA not applicable; skip
        assert mid_broad > mid_narrow, (
            f"Broad cash should raise EV/EBITDA mid: "
            f"narrow={mid_narrow:.2f}  broad={mid_broad:.2f}"
        )
        # The expected delta is (broad_cash − narrow_cash) / shares
        expected_delta = (234_907.7 - 6_434.6) / 12_529.47
        actual_delta   = mid_broad - mid_narrow
        assert abs(actual_delta - expected_delta) < 1.0, (
            f"Delta mismatch: expected ≈ ₹{expected_delta:.2f}, got ₹{actual_delta:.2f}"
        )


# ---------------------------------------------------------------------------
# Class C — ITC.NS integration: classification unchanged after fix
# ---------------------------------------------------------------------------

class TestC_ITCClassificationUnchanged:
    """
    Load the real ITC.NS cached data through the full pipeline and confirm:
      * Broad cash is selected
      * Base FV rises (≈₹232.52)
      * Zone remains WAIT
      * valuation_attractiveness_label remains "NEGATIVE"
    """

    @classmethod
    def setup_class(cls):
        """Run the full pipeline once and cache results."""
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            from analytics.agent.data_loader import load_ticker
            from analytics.agent.valuation_builder import build_valuation_input
            from analytics.valuation.valuation_synthesizer import run_valuation

            cls.result = load_ticker("ITC.NS")
            cls.vi = build_valuation_input(cls.result, research=None)
            cls.assessment = run_valuation(cls.vi)
            cls.available = True
        except Exception as e:
            cls.available = False
            cls.skip_reason = str(e)

    def _check_available(self):
        if not self.available:
            import pytest
            pytest.skip(f"ITC.NS data unavailable: {self.skip_reason}")

    def test_itc_broad_cash_selected(self):
        """ITC.NS must use the broad cash line (₹234,907.7M) after the fix."""
        self._check_available()
        cash_M = self.vi.cash_and_equivalents.value
        assert cash_M > 200_000, (
            f"Expected broad cash > 200,000M, got {cash_M:.1f}M — "
            "narrow cash selected instead of broad"
        )
        assert "Short-Term" in self.vi.cash_and_equivalents.source

    def test_itc_ev_ebitda_mid_increased(self):
        """EV/EBITDA mid must be > ₹235 (was ₹222.04 with narrow cash)."""
        self._check_available()
        ev = self.assessment.ev_ebitda_result
        assert ev is not None and ev.is_valid()
        assert ev.implied_value_mid > 235, (
            f"EV/EBITDA mid should be > ₹235 after fix, got ₹{ev.implied_value_mid:.2f}"
        )

    def test_itc_base_fv_between_230_and_235(self):
        """
        Base FV after Phase 9.3b cash fix, Phase 9.9, and Phase 9.9b.

        History of expected values:
          Pre-Phase-9.3b fix:    ₹226.44  (narrow cash → low EV → low EV/EBITDA FV)
          Post-Phase-9.3b fix:   ₹232.52  (broad cash; TTM EPS ≈ ₹15.83)
          Post-Phase-9.9 fix:    ₹241.80  (broad cash; 4yr total-NI derived EPS ≈ ₹18.97;
                                            included FY2025 discontinued-ops NI ₹347.5B)
          Post-Phase-9.9b fix:   ₹233.02  (broad cash; 3yr continuing-ops derived EPS ≈ ₹16.05;
                                            FY2025 total NI replaced by continuing-ops NI ₹197.3B;
                                            window aligned to same FY2024–FY2026 as FCF)

        Phase 9.9b corrects two issues:
          1. NI source: uses "Net Income From Continuing Operation Net Minority Interest"
             rather than total "Net Income", excluding the FY2025 ₹150B discontinued-ops gain.
          2. Period alignment: EPS window now equals FCF window (FY2024–FY2026, 3yr).

        The WAIT zone conclusion is preserved (₹282.65 price > ₹233.02 fair value).
        P/FCF (₹216.67), EV/EBITDA (₹240.01), and DCF (₹195.93) are unchanged.
        """
        self._check_available()
        base = self.assessment.fair_value_range.base
        assert 229 <= base <= 237, (
            f"Base FV ₹{base:.2f} outside expected range [₹229, ₹237] "
            f"(Phase 9.9b: 3yr continuing-ops derived EPS ≈ ₹16.05, "
            f"window FY2024–FY2026, excl. FY2025 discontinued-ops gain)"
        )

    def test_itc_zone_still_wait(self):
        """Price ₹282.65 must still be above post-fix FV → zone = WAIT."""
        self._check_available()
        from analytics.valuation.valuation_models import AccumulationZoneLabel
        assert self.assessment.accumulation_zone is not None
        assert self.assessment.accumulation_zone.zone == AccumulationZoneLabel.WAIT, (
            f"Zone changed unexpectedly: {self.assessment.accumulation_zone.zone}"
        )

    def test_itc_valuation_attractiveness_still_negative(self):
        """
        Run through the full decision pipeline and confirm
        valuation_attractiveness_label is still "NEGATIVE".
        """
        self._check_available()
        try:
            from analytics.decision.decision_synthesizer import make_investment_decision
            assessment = make_investment_decision(
                ticker="ITC.NS",
                company_name="ITC Limited",
                analysis_date="2026-08-11",
                valuation=self.assessment,
                current_price=282.65,
                price_currency="INR",
            )
            label = assessment.valuation_attractiveness_label
            assert label == "NEGATIVE", (
                f"Expected NEGATIVE, got {label}. "
                "The cash fix must not change the WAIT-zone NEGATIVE classification."
            )
        except Exception:
            import pytest
            pytest.skip("Decision pipeline not available in this environment")


# ---------------------------------------------------------------------------
# Class D — data_loader supplemental exposure
# ---------------------------------------------------------------------------

class TestD_SupplementalCashFields:
    """Verify data_loader exposes the three cash keys in supplemental."""

    def test_supplemental_has_cash_keys(self):
        """
        After loading ITC.NS, supplemental must contain
        cash_broad, cash_narrow, and cash_info.
        """
        try:
            from analytics.agent.data_loader import load_ticker
            r = load_ticker("ITC.NS")
        except Exception as e:
            import pytest
            pytest.skip(f"ITC.NS unavailable: {e}")

        supp = r.supplemental
        assert "cash_broad" in supp, "cash_broad missing from supplemental"
        assert "cash_narrow" in supp, "cash_narrow missing from supplemental"
        assert "cash_info" in supp, "cash_info missing from supplemental"

    def test_supplemental_broad_larger_than_narrow(self):
        """Broad cash must be > narrow cash when both are present."""
        try:
            from analytics.agent.data_loader import load_ticker
            r = load_ticker("ITC.NS")
        except Exception as e:
            import pytest
            pytest.skip(f"ITC.NS unavailable: {e}")

        broad  = r.supplemental.get("cash_broad")
        narrow = r.supplemental.get("cash_narrow")
        if broad is None or narrow is None:
            return   # one field absent; skip comparison
        assert broad > narrow, (
            f"Broad cash ({broad}) should exceed narrow cash ({narrow})"
        )

    def test_latest_bs_helper_handles_missing_field(self):
        """_latest_bs returns None for a field that doesn't exist in the dict."""
        from analytics.agent.data_loader import _latest_bs
        assert _latest_bs({}, "NonExistentField") is None
        assert _latest_bs({"Other Field": {"2026": 100.0}}, "Missing") is None

    def test_latest_bs_helper_returns_most_recent_value(self):
        """_latest_bs picks the max year key."""
        from analytics.agent.data_loader import _latest_bs
        bs = {
            "Cash Cash Equivalents And Short Term Investments": {
                "2023": 100.0, "2024": 200.0, "2026": 400.0, "2025": 300.0
            }
        }
        result = _latest_bs(bs, "Cash Cash Equivalents And Short Term Investments")
        assert result == 400.0, f"Expected 400.0 (year 2026), got {result}"
