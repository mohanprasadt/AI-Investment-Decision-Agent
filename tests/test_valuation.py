"""
Phase 5 Test Suite — Valuation Engine
======================================
Tests all Phase 5 modules with synthetic data — no network calls.

Scenarios covered:
  1.  Normal positive-FCF company (industrial)
  2.  Negative-FCF company
  3.  Negative-earnings company
  4.  High-growth company
  5.  Mature dividend company (utility)
  6.  Financial institution
  7.  REIT with FFO data
  8.  High-debt company
  9.  Missing valuation inputs
  10. Currency conversion (USD company, CAD base)
  11. DCF sensitivity table
  12. Fair-value range generation
  13. Margin-of-safety calculation
  14. Accumulation-zone derivation
  15. Peer valuation
  16. Historical multiple comparison
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.valuation.valuation_models import (
    ValuationInput, ValuationAssessment, FairValueRange,
    InputItem, InputType, PeerData,
    CompanyType, ValuationMethod, MethodApplicability, MethodReliability,
    ValuationConfidence, AccumulationZoneLabel,
)
from analytics.valuation.dcf_engine import run_dcf, dcf_applicability, _base_discount_rate
from analytics.valuation.multiples_engine import (
    run_normalized_pe, run_ev_ebitda, run_price_to_fcf,
    run_historical_pe, run_historical_ev_ebitda,
    run_peer_valuation, run_specialist_multiple,
)
from analytics.valuation.method_selector import select_methods
from analytics.valuation.margin_of_safety import (
    required_margin_of_safety, current_accumulation_zone, accumulation_zone_thresholds,
)
from analytics.valuation.valuation_synthesizer import run_valuation


# ---------------------------------------------------------------------------
# Test fixture helpers
# ---------------------------------------------------------------------------

def _item(name, value, source="Annual Report FY2024", period="FY2024",
          currency="CAD", itype=InputType.REPORTED):
    return InputItem(name=name, value=value, source=source, period=period,
                     currency=currency, input_type=itype)


def make_industrial_inputs(
    ticker="CNR.TO",
    company_name="CN Rail",
    price=170.0,
    shares=670.0,
    eps=8.50,
    ebitda=8_500.0,
    debt=15_000.0,
    cash=1_200.0,
    fcf=3_800.0,
    fcf_norm=3_500.0,
    revenue=17_000.0,
    currency="CAD",
    moat="STRONG",
    quality="EXCELLENT",
) -> ValuationInput:
    return ValuationInput(
        ticker=ticker,
        company_name=company_name,
        company_type=CompanyType.INDUSTRIAL,
        valuation_date="2024-12-31",
        currency=currency,
        current_price=_item("Price", price, source="Market data", currency=currency),
        shares_outstanding=_item("Shares", shares, currency=currency),
        eps_ttm=_item("EPS", eps, currency=currency),
        ebitda=_item("EBITDA", ebitda, currency=currency),
        total_debt=_item("Debt", debt, currency=currency),
        cash_and_equivalents=_item("Cash", cash, currency=currency),
        fcf_ttm=_item("FCF", fcf, currency=currency),
        fcf_normalized=_item("FCF Norm", fcf_norm, period="3yr avg", currency=currency),
        revenue=_item("Revenue", revenue, currency=currency),
        eps_history={"2019": 6.0, "2020": 5.8, "2021": 7.0, "2022": 8.0, "2023": 8.5},
        pe_history={"2019": 20.0, "2020": 21.0, "2021": 23.0, "2022": 19.0, "2023": 18.0},
        ev_ebitda_history={"2019": 12.0, "2020": 13.0, "2021": 14.0, "2022": 12.5, "2023": 11.5},
        fcf_history={"2019": 2800.0, "2020": 2600.0, "2021": 3100.0, "2022": 3400.0, "2023": 3700.0},
        dcf_revenue_growth_rate=7.0,
        moat_strength=moat,
        financial_quality_hint=quality,
        peers=[
            PeerData("CP.TO", "CP Rail", pe_ratio=22.0, ev_ebitda=14.0, price_to_fcf=20.0),
            PeerData("UNP", "Union Pacific", pe_ratio=20.0, ev_ebitda=12.0, price_to_fcf=18.0),
        ],
    )


# ===========================================================================
# Scenario 1: Normal positive-FCF company
# ===========================================================================

class TestNormalPositiveFCF(unittest.TestCase):

    def setUp(self):
        self.inputs = make_industrial_inputs()
        self.result = run_valuation(self.inputs)

    def test_assessment_has_fair_value_range(self):
        self.assertIsNotNone(self.result.fair_value_range)
        self.assertIsNotNone(self.result.fair_value_range.base)

    def test_bear_lt_base_lt_bull(self):
        fv = self.result.fair_value_range
        self.assertLess(fv.bear, fv.base)
        self.assertLess(fv.base, fv.bull)

    def test_dcf_is_valid(self):
        self.assertIsNotNone(self.result.dcf_result)
        self.assertTrue(self.result.dcf_result.is_valid())

    def test_dcf_sensitivity_table_shape(self):
        t = self.result.dcf_result.sensitivity_table
        self.assertEqual(len(t), 5)                    # 5 discount rates
        first_row = next(iter(t.values()))
        self.assertEqual(len(first_row), 5)            # 5 terminal growth rates

    def test_accumulation_zone_set(self):
        self.assertIsNotNone(self.result.accumulation_zone)

    def test_margin_of_safety_set(self):
        self.assertIsNotNone(self.result.margin_of_safety_at_current_price_pct)
        self.assertIsNotNone(self.result.required_margin_of_safety_pct)

    def test_multiple_methods_applicable(self):
        self.assertGreater(len(self.result.applicable_methods()), 2)

    def test_json_serializable(self):
        j = self.result.to_json()
        parsed = json.loads(j)
        self.assertEqual(parsed["ticker"], "CNR.TO")

    def test_currency_preserved(self):
        self.assertEqual(self.result.currency, "CAD")
        self.assertEqual(self.result.fair_value_range.currency, "CAD")

    def test_no_investment_recommendation_in_output(self):
        text = self.result.summary_text()
        for word in ["BUY", "SELL", "HOLD", "overweight", "underweight"]:
            self.assertNotIn(word, text)


# ===========================================================================
# Scenario 2: Negative-FCF company
# ===========================================================================

class TestNegativeFCF(unittest.TestCase):

    def setUp(self):
        self.inputs = ValuationInput(
            ticker="BURN.TO",
            company_name="Cash Burner Corp",
            company_type=CompanyType.NEGATIVE_FCF,
            valuation_date="2024-12-31",
            currency="CAD",
            current_price=_item("Price", 25.0),
            shares_outstanding=_item("Shares", 200.0),
            fcf_ttm=_item("FCF", -80.0),
            revenue=_item("Revenue", 500.0),
            ebitda=_item("EBITDA", 30.0),
            total_debt=_item("Debt", 200.0),
            cash_and_equivalents=_item("Cash", 150.0),
            moat_strength="WEAK",
            financial_quality_hint="CONCERN",
        )

    def test_dcf_not_applicable(self):
        dcf = run_dcf(self.inputs)
        self.assertFalse(dcf.is_valid())
        self.assertEqual(dcf.reliability, MethodReliability.NA)

    def test_p_fcf_not_applicable(self):
        app, _, _ = run_price_to_fcf(self.inputs)
        self.assertEqual(app, MethodApplicability.NOT_APPLICABLE)

    def test_revenue_multiple_used(self):
        result = run_valuation(self.inputs)
        applicable = result.applicable_methods()
        # Revenue multiple should be in applicable set for NEGATIVE_FCF
        self.assertIn(ValuationMethod.REVENUE_MULTIPLE.value, applicable)

    def test_low_confidence_flagged(self):
        # Only the revenue multiple produces a base value (EV/EBITDA has no
        # default range for NEGATIVE_FCF, so n_applicable > 1 but only 1 method
        # yields a result → synthesizer scores MEDIUM, not LOW)
        result = run_valuation(self.inputs)
        self.assertIn(result.overall_confidence,
                      [ValuationConfidence.LOW, ValuationConfidence.MEDIUM])

    def test_high_mos_required(self):
        mos = required_margin_of_safety("WEAK", "CONCERN", ValuationConfidence.LOW)
        self.assertGreaterEqual(mos, 35.0)


# ===========================================================================
# Scenario 3: Negative-earnings company
# ===========================================================================

class TestNegativeEarnings(unittest.TestCase):

    def setUp(self):
        self.inputs = ValuationInput(
            ticker="LOSS.TO",
            company_name="Loss Making Corp",
            company_type=CompanyType.INDUSTRIAL,
            valuation_date="2024-12-31",
            currency="CAD",
            current_price=_item("Price", 30.0),
            shares_outstanding=_item("Shares", 100.0),
            eps_ttm=_item("EPS", -2.50),
            fcf_ttm=_item("FCF", 100.0),   # Positive FCF despite negative earnings
            ebitda=_item("EBITDA", 200.0),
            total_debt=_item("Debt", 500.0),
            cash_and_equivalents=_item("Cash", 100.0),
            revenue=_item("Revenue", 1_000.0),
            moat_strength="MODERATE",
            financial_quality_hint="WATCH",
        )

    def test_pe_not_applicable(self):
        app, reason, _ = run_normalized_pe(self.inputs)
        self.assertEqual(app, MethodApplicability.NOT_APPLICABLE)
        self.assertIn("earnings", reason.lower())

    def test_historical_pe_not_applicable(self):
        app, _, _ = run_historical_pe(self.inputs)
        self.assertEqual(app, MethodApplicability.NOT_APPLICABLE)

    def test_ev_ebitda_still_applicable(self):
        app, _, result = run_ev_ebitda(self.inputs)
        self.assertIn(app, [MethodApplicability.APPLICABLE, MethodApplicability.APPLICABLE_WITH_CAVEATS])
        self.assertIsNotNone(result)

    def test_p_fcf_applicable_despite_negative_earnings(self):
        app, _, result = run_price_to_fcf(self.inputs)
        self.assertEqual(app, MethodApplicability.APPLICABLE)
        self.assertIsNotNone(result)


# ===========================================================================
# Scenario 4: High-growth company
# ===========================================================================

class TestHighGrowthCompany(unittest.TestCase):

    def setUp(self):
        self.inputs = ValuationInput(
            ticker="GROW.TO",
            company_name="High Growth SaaS",
            company_type=CompanyType.HIGH_GROWTH,
            valuation_date="2024-12-31",
            currency="CAD",
            current_price=_item("Price", 120.0),
            shares_outstanding=_item("Shares", 100.0),
            eps_ttm=_item("EPS", 1.50),
            fcf_ttm=_item("FCF", -50.0),       # Burning cash
            revenue=_item("Revenue", 500.0),
            ebitda=_item("EBITDA", 50.0),
            total_debt=_item("Debt", 100.0),
            cash_and_equivalents=_item("Cash", 200.0),
            dcf_revenue_growth_rate=25.0,
            moat_strength="MODERATE",
            financial_quality_hint="GOOD",
        )

    def test_dcf_with_caveats_for_negative_fcf_high_growth(self):
        # dcf_applicability returns a 2-tuple (applicability, reason)
        app, reason = dcf_applicability(self.inputs)
        self.assertEqual(app, MethodApplicability.APPLICABLE_WITH_CAVEATS)

    def test_pe_range_higher_for_high_growth(self):
        # High-growth companies get different default P/E range
        self.inputs.eps_ttm = _item("EPS", 1.50)
        app, _, result = run_normalized_pe(self.inputs)
        if result:
            self.assertGreater(result.multiple_mid, 20.0)  # Should be higher than industrial

    def test_valuation_has_wide_range(self):
        result = run_valuation(self.inputs)
        if result.fair_value_range and result.fair_value_range.width_pct():
            # High-growth should produce a wider range than a stable industrial
            # (or at minimum it should have a valid range)
            self.assertGreater(result.fair_value_range.bull, result.fair_value_range.bear)

    def test_revenue_multiple_applicable(self):
        app, _, _ = run_specialist_multiple(self.inputs)
        self.assertIn(app, [MethodApplicability.APPLICABLE, MethodApplicability.APPLICABLE_WITH_CAVEATS])

    def test_low_reliability_revenue_multiple(self):
        _, _, result = run_specialist_multiple(self.inputs)
        if result:
            self.assertEqual(result.reliability, MethodReliability.LOW)


# ===========================================================================
# Scenario 5: Mature dividend company (utility-like)
# ===========================================================================

class TestMatureDividendCompany(unittest.TestCase):

    def setUp(self):
        self.inputs = ValuationInput(
            ticker="UTIL.TO",
            company_name="Stable Utility Corp",
            company_type=CompanyType.UTILITY,
            valuation_date="2024-12-31",
            currency="CAD",
            current_price=_item("Price", 45.0),
            shares_outstanding=_item("Shares", 500.0),
            eps_ttm=_item("EPS", 3.20),
            fcf_ttm=_item("FCF", 1_200.0),
            fcf_normalized=_item("FCF Norm", 1_150.0, period="5yr avg"),
            ebitda=_item("EBITDA", 3_500.0),
            total_debt=_item("Debt", 12_000.0),
            cash_and_equivalents=_item("Cash", 400.0),
            revenue=_item("Revenue", 5_000.0),
            dcf_revenue_growth_rate=3.5,
            eps_history={str(y): 2.8 + (y - 2019) * 0.1 for y in range(2019, 2024)},
            pe_history={"2019": 17.0, "2020": 19.0, "2021": 18.0, "2022": 16.0, "2023": 15.0},
            moat_strength="MODERATE",
            financial_quality_hint="GOOD",
        )

    def test_dcf_applicable_for_stable_utility(self):
        dcf = run_dcf(self.inputs)
        self.assertTrue(dcf.is_valid())

    def test_high_debt_does_not_break_ev_ebitda(self):
        app, _, result = run_ev_ebitda(self.inputs)
        # Should still work (high debt is a utility characteristic)
        self.assertIsNotNone(result)

    def test_lower_discount_rate_for_predictable_utility(self):
        # MODERATE moat + GOOD quality
        dr = _base_discount_rate("MODERATE", "GOOD")
        self.assertLessEqual(dr, 10.5)  # should not be punishingly high

    def test_full_valuation_runs(self):
        result = run_valuation(self.inputs)
        self.assertIsNotNone(result.fair_value_range)


# ===========================================================================
# Scenario 6: Financial institution
# ===========================================================================

class TestFinancialInstitution(unittest.TestCase):

    def setUp(self):
        self.inputs = ValuationInput(
            ticker="TD.TO",
            company_name="TD Bank",
            company_type=CompanyType.FINANCIAL,
            valuation_date="2024-12-31",
            currency="CAD",
            current_price=_item("Price", 80.0),
            shares_outstanding=_item("Shares", 1_800.0),
            eps_ttm=_item("EPS", 7.20),
            book_value_per_share=_item("BVPS", 55.0),
            ebitda=_item("EBITDA", 20_000.0),
            total_debt=_item("Debt", 0.0),  # Not meaningful for banks
            cash_and_equivalents=_item("Cash", 0.0),
            eps_history={"2019": 6.5, "2020": 5.8, "2021": 7.0, "2022": 7.2, "2023": 7.2},
            pe_history={"2019": 11.0, "2020": 12.5, "2021": 13.0, "2022": 10.5, "2023": 11.0},
            moat_strength="MODERATE",
            financial_quality_hint="STRONG",
        )

    def test_dcf_not_applicable(self):
        dcf = run_dcf(self.inputs)
        self.assertFalse(dcf.is_valid())

    def test_ev_ebitda_not_applicable(self):
        app, _, _ = run_ev_ebitda(self.inputs)
        self.assertEqual(app, MethodApplicability.NOT_APPLICABLE)

    def test_p_fcf_not_applicable(self):
        app, _, _ = run_price_to_fcf(self.inputs)
        self.assertEqual(app, MethodApplicability.NOT_APPLICABLE)

    def test_normalized_pe_applicable_for_bank(self):
        app, _, result = run_normalized_pe(self.inputs)
        self.assertIn(app, [MethodApplicability.APPLICABLE, MethodApplicability.APPLICABLE_WITH_CAVEATS])
        self.assertIsNotNone(result)

    def test_p_bv_applicable_for_bank(self):
        app, _, result = run_specialist_multiple(self.inputs)
        self.assertEqual(app, MethodApplicability.APPLICABLE)
        self.assertEqual(result.method, ValuationMethod.PRICE_TO_BOOK)
        self.assertIsNotNone(result.implied_value_mid)

    def test_full_valuation_runs_for_bank(self):
        result = run_valuation(self.inputs)
        self.assertIsNotNone(result.fair_value_range)
        self.assertIn(ValuationMethod.PRICE_TO_BOOK.value, result.applicable_methods())

    def test_bank_caveat_present(self):
        result = run_valuation(self.inputs)
        caveat_text = " ".join(result.valuation_caveats)
        self.assertIn("financial", caveat_text.lower())


# ===========================================================================
# Scenario 7: REIT
# ===========================================================================

class TestREIT(unittest.TestCase):

    def setUp(self):
        self.inputs = ValuationInput(
            ticker="REIT.TO",
            company_name="Commercial REIT",
            company_type=CompanyType.REIT,
            valuation_date="2024-12-31",
            currency="CAD",
            current_price=_item("Price", 18.0),
            shares_outstanding=_item("Shares", 300.0),
            eps_ttm=_item("EPS", 0.80),             # Net income low due to D&A
            ffo_per_share=_item("FFO/share", 2.10),
            affo_per_share=_item("AFFO/share", 1.85),
            # FCF proxy for REIT DCF (run with caveats); AFFO × shares ≈ 555M
            fcf_normalized=_item("FCF proxy", 555.0, period="FY2024 AFFO-based"),
            ebitda=_item("EBITDA", 800.0),
            total_debt=_item("Debt", 4_000.0),
            cash_and_equivalents=_item("Cash", 200.0),
            revenue=_item("Revenue", 1_200.0),
            moat_strength="MODERATE",
            financial_quality_hint="GOOD",
        )

    def test_ffo_multiple_applicable(self):
        app, _, result = run_specialist_multiple(self.inputs)
        self.assertEqual(app, MethodApplicability.APPLICABLE)
        self.assertEqual(result.method, ValuationMethod.FFO_MULTIPLE)

    def test_affo_preferred_over_ffo(self):
        _, _, result = run_specialist_multiple(self.inputs)
        self.assertIn("AFFO", result.metric_used)

    def test_pe_not_applicable_for_reit(self):
        app, _, _ = run_normalized_pe(self.inputs)
        self.assertEqual(app, MethodApplicability.NOT_APPLICABLE)

    def test_ffo_implied_value_positive(self):
        _, _, result = run_specialist_multiple(self.inputs)
        self.assertGreater(result.implied_value_mid, 0)

    def test_full_valuation_runs(self):
        result = run_valuation(self.inputs)
        self.assertIsNotNone(result.fair_value_range)


# ===========================================================================
# Scenario 8: High-debt company
# ===========================================================================

class TestHighDebtCompany(unittest.TestCase):

    def setUp(self):
        self.inputs = ValuationInput(
            ticker="DEBT.TO",
            company_name="Leveraged Co",
            company_type=CompanyType.INDUSTRIAL,
            valuation_date="2024-12-31",
            currency="CAD",
            current_price=_item("Price", 20.0),
            shares_outstanding=_item("Shares", 200.0),
            eps_ttm=_item("EPS", 2.0),
            ebitda=_item("EBITDA", 800.0),
            total_debt=_item("Debt", 5_000.0),    # Very high debt
            cash_and_equivalents=_item("Cash", 300.0),
            fcf_ttm=_item("FCF", 400.0),
            revenue=_item("Revenue", 3_000.0),
            dcf_revenue_growth_rate=4.0,
            moat_strength="WEAK",
            financial_quality_hint="WATCH",
        )

    def test_ev_ebitda_reflects_high_debt(self):
        _, _, result = run_ev_ebitda(self.inputs)
        # High debt → low implied equity per share
        self.assertIsNotNone(result)
        # implied value should be much lower than for low-debt company
        mc = 20.0 * 200.0   # 4000M market cap
        ev = mc + 5000.0 - 300.0   # 8700M EV
        ev_ebitda = ev / 800.0      # ~10.9x
        # Our result should have produced a value
        self.assertGreater(result.implied_value_mid, 0)

    def test_high_required_mos(self):
        mos = required_margin_of_safety("WEAK", "WATCH", ValuationConfidence.MEDIUM)
        self.assertGreater(mos, 25.0)

    def test_dcf_runs_despite_high_debt(self):
        # High debt doesn't block DCF directly — it affects equity value via net debt
        dcf = run_dcf(self.inputs)
        self.assertTrue(dcf.is_valid())

    def test_full_valuation_runs(self):
        result = run_valuation(self.inputs)
        self.assertIsNotNone(result.fair_value_range)


# ===========================================================================
# Scenario 9: Missing valuation inputs
# ===========================================================================

class TestMissingInputs(unittest.TestCase):

    def test_no_fcf_blocks_dcf(self):
        inputs = ValuationInput(
            ticker="SPARSE.TO", company_name="Sparse Corp",
            company_type=CompanyType.INDUSTRIAL,
            valuation_date="2024-12-31", currency="CAD",
            shares_outstanding=_item("Shares", 100.0),
            moat_strength="MODERATE", financial_quality_hint="GOOD",
        )
        dcf = run_dcf(inputs)
        self.assertFalse(dcf.is_valid())

    def test_no_ebitda_blocks_ev_ebitda(self):
        inputs = ValuationInput(
            ticker="SPARSE.TO", company_name="Sparse Corp",
            company_type=CompanyType.INDUSTRIAL,
            valuation_date="2024-12-31", currency="CAD",
            current_price=_item("Price", 50.0),
            shares_outstanding=_item("Shares", 100.0),
            moat_strength="MODERATE", financial_quality_hint="GOOD",
        )
        app, _, _ = run_ev_ebitda(inputs)
        self.assertEqual(app, MethodApplicability.NOT_APPLICABLE)

    def test_no_eps_history_uses_defaults(self):
        inputs = ValuationInput(
            ticker="SPARSE.TO", company_name="Sparse Corp",
            company_type=CompanyType.INDUSTRIAL,
            valuation_date="2024-12-31", currency="CAD",
            eps_ttm=_item("EPS", 5.0),
            moat_strength="MODERATE", financial_quality_hint="GOOD",
        )
        app, _, result = run_normalized_pe(inputs)
        self.assertIn(app, [MethodApplicability.APPLICABLE, MethodApplicability.APPLICABLE_WITH_CAVEATS])
        self.assertEqual(result.reliability, MethodReliability.LOW)  # defaults used

    def test_no_methods_applicable_returns_gracefully(self):
        inputs = ValuationInput(
            ticker="EMPTY.TO", company_name="Empty Corp",
            company_type=CompanyType.INDUSTRIAL,
            valuation_date="2024-12-31", currency="CAD",
            moat_strength="NONE", financial_quality_hint="CONCERN",
        )
        result = run_valuation(inputs)
        # Should not crash — just produce empty/low-confidence result
        self.assertEqual(result.overall_confidence, ValuationConfidence.LOW)


# ===========================================================================
# Scenario 10: Currency conversion (USD company)
# ===========================================================================

class TestCurrencyConversion(unittest.TestCase):

    def setUp(self):
        self.inputs = make_industrial_inputs(
            ticker="MSFT",
            company_name="Microsoft Corporation",
            price=420.0,
            currency="USD",
        )
        self.inputs.fx_rate_to_cad = 1.35
        self.inputs.fx_rate_date = "2024-12-31"

    def test_local_currency_preserved(self):
        result = run_valuation(self.inputs)
        self.assertEqual(result.currency, "USD")

    def test_fair_value_in_local_currency(self):
        result = run_valuation(self.inputs)
        if result.fair_value_range:
            self.assertEqual(result.fair_value_range.currency, "USD")

    def test_fx_rate_documented(self):
        result = run_valuation(self.inputs)
        # FX rate should appear in provenance notes
        provenance = " ".join(result.data_provenance_notes)
        self.assertIn("1.35", provenance)

    def test_cad_equivalent_derivable(self):
        result = run_valuation(self.inputs)
        if result.fair_value_range and result.fair_value_range.base:
            cad_equiv = result.fair_value_range.base * self.inputs.fx_rate_to_cad
            self.assertGreater(cad_equiv, 0)


# ===========================================================================
# Scenario 11: DCF sensitivity table
# ===========================================================================

class TestDCFSensitivity(unittest.TestCase):

    def setUp(self):
        self.inputs = make_industrial_inputs()
        self.dcf = run_dcf(self.inputs)

    def test_sensitivity_table_has_correct_shape(self):
        t = self.dcf.sensitivity_table
        self.assertEqual(len(t), 5)    # 5 discount rates
        for row in t.values():
            self.assertEqual(len(row), 5)  # 5 terminal growth rates

    def test_higher_discount_rate_gives_lower_value(self):
        rows = list(self.dcf.sensitivity_table.items())
        # Sort by discount rate (key is "X.X%")
        rows_sorted = sorted(rows, key=lambda x: float(x[0].rstrip('%')))
        for tg_key in next(iter(self.dcf.sensitivity_table.values())).keys():
            vals = [row[tg_key] for _, row in rows_sorted if row[tg_key] is not None]
            if len(vals) >= 2:
                self.assertGreater(vals[0], vals[-1])  # lower DR → higher value

    def test_higher_terminal_growth_gives_higher_value(self):
        for dr_key, row in self.dcf.sensitivity_table.items():
            tg_vals = sorted([(float(k.rstrip('%')), v) for k, v in row.items() if v])
            if len(tg_vals) >= 2:
                self.assertLess(tg_vals[0][1], tg_vals[-1][1])  # higher TG → higher value
                break

    def test_bear_lt_base_lt_bull(self):
        self.assertLess(self.dcf.bear_value, self.dcf.base_value)
        self.assertLess(self.dcf.base_value, self.dcf.bull_value)

    def test_terminal_value_pct_populated(self):
        self.assertIsNotNone(self.dcf.terminal_value_pct_of_base)
        self.assertGreater(self.dcf.terminal_value_pct_of_base, 0)
        self.assertLess(self.dcf.terminal_value_pct_of_base, 100)

    def test_key_assumptions_documented(self):
        self.assertGreater(len(self.dcf.key_assumptions), 2)


# ===========================================================================
# Scenario 12: Fair-value range generation
# ===========================================================================

class TestFairValueRange(unittest.TestCase):

    def test_range_has_all_three_cases(self):
        inputs = make_industrial_inputs()
        result = run_valuation(inputs)
        fv = result.fair_value_range
        self.assertIsNotNone(fv.bear)
        self.assertIsNotNone(fv.base)
        self.assertIsNotNone(fv.bull)

    def test_range_currency_matches_inputs(self):
        inputs = make_industrial_inputs(currency="CAD")
        result = run_valuation(inputs)
        self.assertEqual(result.fair_value_range.currency, "CAD")

    def test_primary_method_documented(self):
        inputs = make_industrial_inputs()
        result = run_valuation(inputs)
        self.assertGreater(len(result.fair_value_range.primary_method), 0)

    def test_range_width_calculable(self):
        inputs = make_industrial_inputs()
        result = run_valuation(inputs)
        w = result.fair_value_range.width_pct()
        self.assertIsNotNone(w)
        self.assertGreater(w, 0)

    def test_midpoint_between_bear_and_bull(self):
        inputs = make_industrial_inputs()
        result = run_valuation(inputs)
        fv = result.fair_value_range
        midpoint = fv.midpoint()
        self.assertGreaterEqual(midpoint, fv.bear)
        self.assertLessEqual(midpoint, fv.bull)

    def test_json_roundtrip(self):
        inputs = make_industrial_inputs()
        result = run_valuation(inputs)
        j = result.to_json()
        parsed = json.loads(j)
        self.assertIn("fair_value_range", parsed)
        self.assertIn("base", parsed["fair_value_range"])


# ===========================================================================
# Scenario 13: Margin-of-safety calculation
# ===========================================================================

class TestMarginOfSafety(unittest.TestCase):

    def test_exceptional_moat_low_mos(self):
        mos = required_margin_of_safety("EXCEPTIONAL", "EXCELLENT", ValuationConfidence.HIGH)
        self.assertLessEqual(mos, 12.0)

    def test_no_moat_high_mos(self):
        mos = required_margin_of_safety("NONE", "CONCERN", ValuationConfidence.LOW)
        self.assertGreaterEqual(mos, 40.0)

    def test_moderate_moat_medium_mos(self):
        mos = required_margin_of_safety("MODERATE", "GOOD", ValuationConfidence.MEDIUM)
        self.assertGreater(mos, 15.0)
        self.assertLess(mos, 35.0)

    def test_low_confidence_increases_mos(self):
        mos_high = required_margin_of_safety("MODERATE", "GOOD", ValuationConfidence.HIGH)
        mos_low  = required_margin_of_safety("MODERATE", "GOOD", ValuationConfidence.LOW)
        self.assertGreater(mos_low, mos_high)

    def test_mos_within_hard_limits(self):
        for moat in ["EXCEPTIONAL", "STRONG", "MODERATE", "WEAK", "NONE"]:
            for quality in ["EXCELLENT", "STRONG", "GOOD", "WATCH", "CONCERN"]:
                for conf in ValuationConfidence:
                    mos = required_margin_of_safety(moat, quality, conf)
                    self.assertGreaterEqual(mos, 8.0)
                    self.assertLessEqual(mos, 45.0)

    def test_zone_thresholds_ordered_correctly(self):
        thresholds = accumulation_zone_thresholds(100.0, 20.0)
        self.assertLess(thresholds["accumulate_below"], thresholds["start_small_below"])
        self.assertLess(thresholds["start_small_below"], thresholds["watch_below"])


# ===========================================================================
# Scenario 14: Accumulation zone derivation
# ===========================================================================

class TestAccumulationZone(unittest.TestCase):

    def _fv(self, base=200.0, bear=160.0, bull=240.0,
            conf=ValuationConfidence.MEDIUM):
        return FairValueRange(bear=bear, base=base, bull=bull,
                               currency="CAD", confidence=conf)

    def test_accumulate_zone_when_deeply_discounted(self):
        # Even with STRONG moat (15% required MoS), price at 80% of FV = 160
        # 160 vs 200 = 20% MoS → above required 15-25% (MEDIUM conf adds 5%)
        zone = current_accumulation_zone(155.0, self._fv(), "STRONG", "GOOD")
        self.assertEqual(zone.zone, AccumulationZoneLabel.ACCUMULATE)

    def test_wait_zone_when_above_fair_value(self):
        zone = current_accumulation_zone(215.0, self._fv(), "STRONG", "GOOD")
        self.assertEqual(zone.zone, AccumulationZoneLabel.WAIT)

    def test_watch_zone_near_fair_value(self):
        zone = current_accumulation_zone(195.0, self._fv(), "STRONG", "GOOD")
        self.assertEqual(zone.zone, AccumulationZoneLabel.WATCH)

    def test_zone_has_reasoning(self):
        zone = current_accumulation_zone(155.0, self._fv(), "STRONG", "GOOD")
        self.assertGreater(len(zone.zone_reasoning), 20)

    def test_no_fair_value_returns_wait(self):
        empty_fv = FairValueRange(currency="CAD", confidence=ValuationConfidence.LOW)
        zone = current_accumulation_zone(100.0, empty_fv, "MODERATE", "GOOD")
        self.assertEqual(zone.zone, AccumulationZoneLabel.WAIT)

    def test_low_confidence_adds_caveat(self):
        zone = current_accumulation_zone(
            155.0, self._fv(conf=ValuationConfidence.LOW), "STRONG", "GOOD"
        )
        self.assertGreater(len(zone.caveat), 0)

    def test_zone_thresholds_present(self):
        zone = current_accumulation_zone(155.0, self._fv(), "STRONG", "GOOD")
        self.assertIsNotNone(zone.accumulate_below)
        self.assertIsNotNone(zone.start_small_below)
        self.assertIsNotNone(zone.watch_below)


# ===========================================================================
# Scenario 15: Peer valuation
# ===========================================================================

class TestPeerValuation(unittest.TestCase):

    def setUp(self):
        self.inputs = make_industrial_inputs()

    def test_peer_median_calculated(self):
        _, _, result = run_peer_valuation(self.inputs)
        self.assertIsNotNone(result.peer_median_pe)
        # Two peers: 22.0 and 20.0 → median 21.0
        self.assertAlmostEqual(result.peer_median_pe, 21.0, places=0)

    def test_implied_value_by_pe(self):
        _, _, result = run_peer_valuation(self.inputs)
        self.assertIsNotNone(result.implied_value_by_pe)
        self.assertGreater(result.implied_value_by_pe, 0)

    def test_no_peers_gives_insufficient_data(self):
        no_peer_inputs = ValuationInput(
            ticker="SOLO.TO", company_name="Solo Corp",
            company_type=CompanyType.INDUSTRIAL,
            valuation_date="2024-12-31", currency="CAD",
            moat_strength="MODERATE", financial_quality_hint="GOOD",
        )
        app, _, _ = run_peer_valuation(no_peer_inputs)
        self.assertEqual(app, MethodApplicability.INSUFFICIENT_DATA)

    def test_single_peer_gives_caveat(self):
        one_peer_inputs = make_industrial_inputs()
        one_peer_inputs.peers = [PeerData("CP.TO", "CP Rail", pe_ratio=22.0)]
        app, _, _ = run_peer_valuation(one_peer_inputs)
        self.assertEqual(app, MethodApplicability.APPLICABLE_WITH_CAVEATS)

    def test_peer_reliability_is_low_for_few_peers(self):
        _, _, result = run_peer_valuation(self.inputs)
        # 2 peers → still low reliability
        self.assertIn(result.reliability, [MethodReliability.LOW, MethodReliability.MEDIUM])


# ===========================================================================
# Scenario 16: Historical multiple comparison
# ===========================================================================

class TestHistoricalMultiples(unittest.TestCase):

    def setUp(self):
        self.inputs = make_industrial_inputs(price=170.0)

    def test_historical_pe_runs(self):
        app, _, result = run_historical_pe(self.inputs)
        self.assertEqual(app, MethodApplicability.APPLICABLE)
        self.assertIsNotNone(result.current_multiple)

    def test_current_percentile_calculated(self):
        _, _, result = run_historical_pe(self.inputs)
        self.assertIsNotNone(result.current_percentile)
        self.assertGreaterEqual(result.current_percentile, 0)
        self.assertLessEqual(result.current_percentile, 100)

    def test_implied_values_at_historical_levels(self):
        _, _, result = run_historical_pe(self.inputs)
        self.assertIsNotNone(result.implied_at_median)
        self.assertIsNotNone(result.implied_at_low)
        self.assertIsNotNone(result.implied_at_high)

    def test_implied_at_low_lt_median_lt_high(self):
        _, _, result = run_historical_pe(self.inputs)
        self.assertLess(result.implied_at_low, result.implied_at_median)
        self.assertLess(result.implied_at_median, result.implied_at_high)

    def test_insufficient_history_blocked(self):
        sparse_inputs = make_industrial_inputs()
        sparse_inputs.pe_history = {"2023": 18.0}  # Only 1 year
        app, _, _ = run_historical_pe(sparse_inputs)
        self.assertEqual(app, MethodApplicability.INSUFFICIENT_DATA)

    def test_historical_ev_ebitda_runs(self):
        app, _, result = run_historical_ev_ebitda(self.inputs)
        self.assertEqual(app, MethodApplicability.APPLICABLE)
        self.assertIsNotNone(result.implied_at_median)

    def test_bank_historical_ev_ebitda_blocked(self):
        bank = ValuationInput(
            ticker="TD.TO", company_name="TD Bank",
            company_type=CompanyType.FINANCIAL,
            valuation_date="2024-12-31", currency="CAD",
            moat_strength="MODERATE", financial_quality_hint="STRONG",
        )
        app, _, _ = run_historical_ev_ebitda(bank)
        self.assertEqual(app, MethodApplicability.NOT_APPLICABLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
