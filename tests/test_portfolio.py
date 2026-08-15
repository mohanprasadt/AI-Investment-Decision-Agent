"""
Phase 6 Test Suite — Portfolio Context Engine
=============================================
All data is synthetic — no network calls, no real portfolio files read.

Scenarios covered:
  1.  New company not currently held
  2.  Existing holding (basic)
  3.  Small position (<5% weight)
  4.  Large position (>8% weight) — concentration flags
  5.  High sector concentration
  6.  Geographic concentration
  7.  Multi-currency: USD position in CAD portfolio
  8.  Multi-currency: INR position in CAD portfolio
  9.  Unrealized gain
  10. Unrealized loss
  11. Zero / very small position
  12. Incremental investment scenarios
  13. Dividend contribution
  14. Growth vs income characterization
  15. Portfolio allocation guideline — no optimization
  16. No automatic optimization (no optimal weight output)
  17. No sunk-cost reasoning (cost basis not a recommendation driver)
  18. Economic group / related-exposure overlap
  19. Phase 5 EV/EBITDA applicability fix (NEGATIVE_FCF selector alignment)
  20. Full JSON serialization
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.portfolio.portfolio_models import (
    Portfolio, Position, PortfolioPositionContext,
    ConcentrationFlag, ConcentrationFlagType, FlagSeverity,
    IncrementalScenario, PositionType,
)
from analytics.portfolio.portfolio_calculator import (
    position_weight_pct, hypothetical_weight_pct,
    sector_weight_for, geography_weight_for,
    dividend_contribution_to_portfolio_income_pct,
    detect_data_gaps, context_confidence,
)
from analytics.portfolio.concentration_analyzer import analyze_concentration
from analytics.portfolio.incremental_scenarios import build_incremental_scenarios
from analytics.portfolio.portfolio_synthesizer import build_portfolio_context


# ===========================================================================
# Shared fixtures
# ===========================================================================

def _pos(
    ticker, company="Co", shares=100.0, avg_cost=50.0, price=60.0,
    currency="CAD", fx=1.0, fx_date="2024-12-31",
    sector="Industrials", geography="Canada",
    economic_group="", div_ps=0.0,
    position_type=PositionType.GROWTH,
) -> Position:
    return Position(
        ticker=ticker,
        company_name=company,
        shares=shares,
        average_cost=avg_cost,
        current_price=price,
        currency=currency,
        fx_rate_to_cad=fx,
        fx_rate_date=fx_date,
        sector=sector,
        geography=geography,
        economic_group=economic_group,
        is_dividend_payer=(div_ps > 0),
        annual_dividend_per_share=div_ps,
        position_type=position_type,
    )


def make_simple_portfolio() -> Portfolio:
    """
    10-position CAD portfolio, total ≈ CAD 100,000:
      - 5 × Industrials / Canada, 6,000 each
      - 2 × Energy / Canada, 6,000 each
      - 2 × Financials / Canada + USA, 6,000 each
      - 1 × Anchor position (large), 40,000
    """
    positions = [
        _pos("A.TO",  shares=100, avg_cost=50, price=60, sector="Industrials",   economic_group="Manufacturing"),
        _pos("B.TO",  shares=100, avg_cost=50, price=60, sector="Industrials",   economic_group="Manufacturing"),
        _pos("C.TO",  shares=100, avg_cost=50, price=60, sector="Industrials",   economic_group="Manufacturing"),
        _pos("D.TO",  shares=100, avg_cost=50, price=60, sector="Industrials",   economic_group="Other"),
        _pos("E.TO",  shares=100, avg_cost=50, price=60, sector="Industrials",   economic_group="Other"),
        _pos("F.TO",  shares=100, avg_cost=50, price=60, sector="Energy",        economic_group="Canadian Energy"),
        _pos("G.TO",  shares=100, avg_cost=50, price=60, sector="Energy",        economic_group="Canadian Energy"),
        _pos("H.TO",  shares=100, avg_cost=50, price=60, sector="Financials",    economic_group="Canadian Banks"),
        _pos("I.TO",  shares=100, avg_cost=50, price=60, sector="Financials",    economic_group="Canadian Banks"),
        # Large anchor: 400 shares × $100 = $40,000 (39.2% of portfolio)
        _pos("ANCHOR.TO", shares=400, avg_cost=80, price=100, sector="Technology", economic_group="Other"),
    ]
    return Portfolio(positions=positions, base_currency="CAD", valuation_date="2024-12-31")


def make_dividend_portfolio() -> Portfolio:
    """Portfolio with income-generating positions."""
    positions = [
        _pos("DIV1.TO", shares=200, avg_cost=40, price=45, div_ps=2.0,
             sector="Utilities", geography="Canada", position_type=PositionType.INCOME),
        _pos("DIV2.TO", shares=150, avg_cost=60, price=65, div_ps=3.0,
             sector="Utilities", geography="Canada", position_type=PositionType.INCOME),
        _pos("GROW.TO", shares=100, avg_cost=80, price=100,
             sector="Technology", geography="Canada", position_type=PositionType.GROWTH),
    ]
    return Portfolio(positions=positions, base_currency="CAD", valuation_date="2024-12-31")


def make_multicurrency_portfolio() -> Portfolio:
    """Portfolio with CAD, USD and INR positions."""
    positions = [
        _pos("CNR.TO",  shares=100, avg_cost=150, price=170, currency="CAD", fx=1.0,
             sector="Industrials", geography="Canada"),
        _pos("AAPL",    shares=20,  avg_cost=150, price=220, currency="USD", fx=1.35,
             sector="Technology", geography="USA"),
        _pos("TCS.NS",  shares=10,  avg_cost=3500, price=4000, currency="INR", fx=0.016,
             sector="Technology", geography="India"),
    ]
    return Portfolio(positions=positions, base_currency="CAD", valuation_date="2024-12-31")


# ===========================================================================
# Scenario 1: New company not currently held
# ===========================================================================

class TestNewCompany(unittest.TestCase):

    def setUp(self):
        self.portfolio = make_simple_portfolio()
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="NEW.TO",
            company_name="New Corp",
            current_price_local=80.0,
            currency="CAD",
            sector="Technology",
            geography="Canada",
        )

    def test_is_not_existing_holding(self):
        self.assertFalse(self.ctx.is_existing_holding)

    def test_shares_held_zero(self):
        self.assertEqual(self.ctx.shares_held, 0.0)

    def test_market_value_zero(self):
        self.assertEqual(self.ctx.market_value_local, 0.0)
        self.assertEqual(self.ctx.market_value_cad, 0.0)

    def test_portfolio_weight_zero(self):
        self.assertEqual(self.ctx.portfolio_weight_pct, 0.0)

    def test_no_unrealized_pnl(self):
        self.assertIsNone(self.ctx.unrealized_gain_loss_pct)

    def test_incremental_scenarios_generated(self):
        self.assertGreater(len(self.ctx.incremental_scenarios), 0)

    def test_scenarios_show_new_weight_above_zero(self):
        for s in self.ctx.incremental_scenarios:
            if s.shares_purchasable > 0:
                self.assertGreater(s.new_portfolio_weight_pct, 0.0)

    def test_price_currency_set(self):
        self.assertEqual(self.ctx.price_currency, "CAD")

    def test_json_serializable(self):
        j = self.ctx.to_json()
        parsed = json.loads(j)
        self.assertEqual(parsed["ticker"], "NEW.TO")
        self.assertFalse(parsed["is_existing_holding"])


# ===========================================================================
# Scenario 2 & 3: Existing holding — small position
# ===========================================================================

class TestExistingSmallPosition(unittest.TestCase):

    def setUp(self):
        self.portfolio = make_simple_portfolio()
        # A.TO: 100 × $60 = $6,000 / ~$102,000 total ≈ 5.9%
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="A.TO",
        )

    def test_is_existing_holding(self):
        self.assertTrue(self.ctx.is_existing_holding)

    def test_shares_held_populated(self):
        self.assertEqual(self.ctx.shares_held, 100.0)

    def test_market_value_correct(self):
        self.assertAlmostEqual(self.ctx.market_value_local, 6000.0, places=1)
        self.assertAlmostEqual(self.ctx.market_value_cad, 6000.0, places=1)

    def test_portfolio_weight_reasonable(self):
        # 6000 / ~102000 ≈ 5.9%
        self.assertGreater(self.ctx.portfolio_weight_pct, 4.0)
        self.assertLess(self.ctx.portfolio_weight_pct, 10.0)

    def test_average_cost_populated(self):
        self.assertEqual(self.ctx.average_cost_per_share, 50.0)

    def test_unrealized_gain_positive(self):
        self.assertGreater(self.ctx.unrealized_gain_loss_pct, 0.0)

    def test_sector_populated(self):
        self.assertEqual(self.ctx.sector, "Industrials")

    def test_geography_populated(self):
        self.assertEqual(self.ctx.geography, "Canada")


# ===========================================================================
# Scenario 4: Large position — concentration flags
# ===========================================================================

class TestLargePosition(unittest.TestCase):

    def setUp(self):
        self.portfolio = make_simple_portfolio()
        # ANCHOR.TO: 400 × $100 = $40,000 / ~$102,000 ≈ 39.2%
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="ANCHOR.TO",
        )

    def test_has_concentration_flags(self):
        self.assertTrue(self.ctx.has_concentration_flags())

    def test_position_size_flag_present(self):
        flag_types = [f.flag_type for f in self.ctx.concentration_flags]
        self.assertIn(ConcentrationFlagType.POSITION_SIZE, flag_types)

    def test_position_flag_is_high_severity(self):
        pos_flags = [f for f in self.ctx.concentration_flags
                     if f.flag_type == ConcentrationFlagType.POSITION_SIZE]
        self.assertTrue(any(f.severity == FlagSeverity.HIGH for f in pos_flags))

    def test_highest_severity_is_high(self):
        self.assertEqual(self.ctx.highest_severity_flag(), FlagSeverity.HIGH)

    def test_portfolio_weight_above_12pct(self):
        self.assertGreater(self.ctx.portfolio_weight_pct, 12.0)

    def test_flags_are_context_not_rejection(self):
        # Every flag must include a context note — not an automatic constraint
        for f in self.ctx.concentration_flags:
            self.assertGreater(len(f.context), 0)
            self.assertNotIn("reject", f.context.lower())
            self.assertNotIn("do not", f.context.lower())


# ===========================================================================
# Scenario 5: High sector concentration
# ===========================================================================

class TestHighSectorConcentration(unittest.TestCase):

    def setUp(self):
        # Portfolio dominated by a single sector
        positions = [
            _pos("A.TO", shares=100, price=100, sector="Energy", economic_group="Canadian Energy"),
            _pos("B.TO", shares=100, price=100, sector="Energy", economic_group="Canadian Energy"),
            _pos("C.TO", shares=100, price=100, sector="Energy", economic_group="Canadian Energy"),
            _pos("D.TO", shares=100, price=100, sector="Energy", economic_group="Canadian Energy"),
            _pos("E.TO", shares=10,  price=100, sector="Technology"),  # small non-energy
        ]
        self.portfolio = Portfolio(positions=positions, valuation_date="2024-12-31")
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="A.TO",
            sector="Energy",
            geography="Canada",
            economic_group="Canadian Energy",
        )

    def test_sector_concentration_flag_present(self):
        sector_flags = [f for f in self.ctx.concentration_flags
                        if f.flag_type == ConcentrationFlagType.SECTOR]
        self.assertTrue(len(sector_flags) > 0)

    def test_sector_flag_elevated_or_high(self):
        sector_flags = [f for f in self.ctx.concentration_flags
                        if f.flag_type == ConcentrationFlagType.SECTOR]
        high_enough = any(f.severity in (FlagSeverity.ELEVATED, FlagSeverity.HIGH)
                          for f in sector_flags)
        self.assertTrue(high_enough)

    def test_sector_weight_above_threshold(self):
        # 4 × 10000 / (4×10000 + 1000) ≈ 97.6%
        self.assertGreater(self.ctx.sector_weight_in_portfolio_pct, 45.0)

    def test_sector_flag_is_context_not_automatic_rejection(self):
        for f in self.ctx.concentration_flags:
            self.assertNotIn("BUY", f.description)
            self.assertNotIn("SELL", f.description)
            self.assertNotIn("HOLD", f.description)


# ===========================================================================
# Scenario 6: Geographic concentration
# ===========================================================================

class TestGeographicConcentration(unittest.TestCase):

    def setUp(self):
        positions = [
            _pos("A.TO", shares=100, price=100, geography="Canada", sector="Industrials"),
            _pos("B.TO", shares=100, price=100, geography="Canada", sector="Financials"),
            _pos("C.TO", shares=100, price=100, geography="Canada", sector="Energy"),
            _pos("D.TO", shares=100, price=100, geography="Canada", sector="Utilities"),
            _pos("INT",  shares=5,   price=100, geography="USA",    sector="Technology"),
        ]
        self.portfolio = Portfolio(positions=positions, valuation_date="2024-12-31")
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="A.TO",
            sector="Industrials",
            geography="Canada",
        )

    def test_geography_weight_high(self):
        self.assertGreater(self.ctx.geography_weight_in_portfolio_pct, 65.0)

    def test_geography_flag_present(self):
        geo_flags = [f for f in self.ctx.concentration_flags
                     if f.flag_type == ConcentrationFlagType.GEOGRAPHY]
        self.assertTrue(len(geo_flags) > 0)

    def test_geography_flag_context_mentions_home_bias(self):
        geo_flags = [f for f in self.ctx.concentration_flags
                     if f.flag_type == ConcentrationFlagType.GEOGRAPHY
                     and f.dimension == "Canada"]
        if geo_flags:
            # At NOTE severity → "home-market" in description; at HIGH → "concentrated in a
            # single geography". Either is an accurate contextual observation.
            desc = geo_flags[0].description.lower()
            self.assertTrue(
                "home" in desc or "concentrated" in desc or "geography" in desc,
                msg=f"Expected geo-context language, got: {desc}",
            )


# ===========================================================================
# Scenario 7 & 8: Multi-currency (USD and INR positions)
# ===========================================================================

class TestMultiCurrencyUSD(unittest.TestCase):

    def setUp(self):
        self.portfolio = make_multicurrency_portfolio()
        # AAPL: 20 × $220 USD × 1.35 = $5,940 CAD
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="AAPL",
            sector="Technology",
            geography="USA",
        )

    def test_price_currency_is_usd(self):
        self.assertEqual(self.ctx.price_currency, "USD")

    def test_market_value_local_in_usd(self):
        self.assertAlmostEqual(self.ctx.market_value_local, 20 * 220, places=0)

    def test_market_value_cad_converted(self):
        expected_cad = 20 * 220 * 1.35
        self.assertAlmostEqual(self.ctx.market_value_cad, expected_cad, places=0)

    def test_fx_rate_preserved(self):
        self.assertAlmostEqual(self.ctx.fx_rate_to_cad, 1.35, places=4)

    def test_total_portfolio_in_cad(self):
        # CNR: 100×170×1=17,000 | AAPL: 20×220×1.35=5,940 | TCS: 10×4000×0.016=640
        expected_total = 100*170 + 20*220*1.35 + 10*4000*0.016
        self.assertAlmostEqual(self.ctx.total_portfolio_value_cad, expected_total, places=0)

    def test_portfolio_weight_in_cad_terms(self):
        total_cad = 100*170 + 20*220*1.35 + 10*4000*0.016
        expected_weight = (20*220*1.35) / total_cad * 100
        self.assertAlmostEqual(self.ctx.portfolio_weight_pct, expected_weight, places=1)


class TestMultiCurrencyINR(unittest.TestCase):

    def setUp(self):
        self.portfolio = make_multicurrency_portfolio()
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="TCS.NS",
            sector="Technology",
            geography="India",
        )

    def test_price_currency_is_inr(self):
        self.assertEqual(self.ctx.price_currency, "INR")

    def test_market_value_local_in_inr(self):
        self.assertAlmostEqual(self.ctx.market_value_local, 10 * 4000, places=0)

    def test_market_value_cad_converted(self):
        expected_cad = 10 * 4000 * 0.016
        self.assertAlmostEqual(self.ctx.market_value_cad, expected_cad, places=1)

    def test_cad_values_are_small_vs_local(self):
        # INR values are large, CAD values should be much smaller
        self.assertLess(self.ctx.market_value_cad, self.ctx.market_value_local)


# ===========================================================================
# Scenario 9: Unrealized gain
# ===========================================================================

class TestUnrealizedGain(unittest.TestCase):

    def setUp(self):
        portfolio = Portfolio(
            positions=[_pos("WIN.TO", shares=100, avg_cost=50, price=80,
                            sector="Industrials", geography="Canada")],
            valuation_date="2024-12-31",
        )
        self.ctx = build_portfolio_context(portfolio=portfolio, ticker="WIN.TO")

    def test_unrealized_gain_positive(self):
        self.assertGreater(self.ctx.unrealized_gain_loss_local, 0)
        self.assertGreater(self.ctx.unrealized_gain_loss_pct, 0)

    def test_unrealized_gain_correct(self):
        # (80 - 50) × 100 = 3000
        self.assertAlmostEqual(self.ctx.unrealized_gain_loss_local, 3000.0, places=1)
        self.assertAlmostEqual(self.ctx.unrealized_gain_loss_pct, 60.0, places=1)

    def test_cost_basis_note_present(self):
        self.assertGreater(len(self.ctx.cost_basis_note), 20)

    def test_observation_mentions_gain(self):
        obs_text = " ".join(self.ctx.contextual_observations).lower()
        self.assertIn("gain", obs_text)


# ===========================================================================
# Scenario 10: Unrealized loss
# ===========================================================================

class TestUnrealizedLoss(unittest.TestCase):

    def setUp(self):
        portfolio = Portfolio(
            positions=[_pos("LOSE.TO", shares=100, avg_cost=80, price=50,
                            sector="Industrials", geography="Canada")],
            valuation_date="2024-12-31",
        )
        self.ctx = build_portfolio_context(portfolio=portfolio, ticker="LOSE.TO")

    def test_unrealized_loss_negative(self):
        self.assertLess(self.ctx.unrealized_gain_loss_local, 0)
        self.assertLess(self.ctx.unrealized_gain_loss_pct, 0)

    def test_unrealized_loss_correct(self):
        # (50 - 80) × 100 = -3000
        self.assertAlmostEqual(self.ctx.unrealized_gain_loss_local, -3000.0, places=1)
        self.assertAlmostEqual(self.ctx.unrealized_gain_loss_pct, -37.5, places=1)

    def test_no_sunk_cost_in_note(self):
        # Cost basis note must NOT suggest holding because of the loss
        note = self.ctx.cost_basis_note.lower()
        self.assertNotIn("hold", note)
        self.assertNotIn("wait", note)
        self.assertNotIn("recover", note)

    def test_observation_does_not_recommend_action(self):
        obs = " ".join(self.ctx.contextual_observations)
        # "holding" appears in "existing holding" — that's factual, not a recommendation.
        # Check for actual action recommendation phrases instead.
        action_phrases = [
            "you should", "we recommend", "consider selling", "consider buying",
            "accumulate", "exit the position", "do not sell", "do not buy",
        ]
        for phrase in action_phrases:
            self.assertNotIn(phrase, obs.lower(), msg=f"Found recommendation phrase: {phrase!r}")


# ===========================================================================
# Scenario 11: Zero / very small position
# ===========================================================================

class TestZeroPosition(unittest.TestCase):

    def setUp(self):
        # Position with 1 share — near-zero weight
        positions = [
            _pos("TINY.TO", shares=1, avg_cost=100, price=100, sector="Industrials"),
            _pos("BIG.TO",  shares=1000, avg_cost=50, price=100, sector="Energy"),
        ]
        self.portfolio = Portfolio(positions=positions, valuation_date="2024-12-31")
        self.ctx = build_portfolio_context(portfolio=self.portfolio, ticker="TINY.TO")

    def test_position_weight_near_zero(self):
        self.assertLess(self.ctx.portfolio_weight_pct, 1.0)

    def test_no_concentration_flags_for_small_position(self):
        pos_flags = [f for f in self.ctx.concentration_flags
                     if f.flag_type == ConcentrationFlagType.POSITION_SIZE]
        self.assertEqual(len(pos_flags), 0)

    def test_market_value_correct(self):
        self.assertAlmostEqual(self.ctx.market_value_local, 100.0, places=1)


# ===========================================================================
# Scenario 12: Incremental investment scenarios
# ===========================================================================

class TestIncrementalScenarios(unittest.TestCase):

    def setUp(self):
        self.portfolio = make_simple_portfolio()
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="A.TO",
            scenario_amounts_cad=[500.0, 1_000.0, 2_000.0],
        )

    def test_three_scenarios_generated(self):
        self.assertEqual(len(self.ctx.incremental_scenarios), 3)

    def test_scenarios_ordered_by_amount(self):
        amounts = [s.investment_amount_cad for s in self.ctx.incremental_scenarios]
        self.assertEqual(amounts, sorted(amounts))

    def test_larger_amount_gives_higher_weight(self):
        weights = [s.new_portfolio_weight_pct for s in self.ctx.incremental_scenarios
                   if s.shares_purchasable > 0]
        for i in range(len(weights) - 1):
            self.assertGreater(weights[i + 1], weights[i])

    def test_new_shares_exceeds_current(self):
        current_shares = self.ctx.shares_held
        for s in self.ctx.incremental_scenarios:
            self.assertGreaterEqual(s.new_total_shares, current_shares)

    def test_scenario_note_says_no_recommendation(self):
        for s in self.ctx.incremental_scenarios:
            if s.shares_purchasable > 0:
                self.assertIn("no investment recommendation", s.note.lower())

    def test_weight_change_is_positive(self):
        for s in self.ctx.incremental_scenarios:
            if s.shares_purchasable > 0:
                self.assertGreater(s.weight_change_pct, 0)

    def test_new_position_scenarios(self):
        # For a new company, starting shares = 0
        ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="BRAND_NEW.TO",
            current_price_local=50.0,
            currency="CAD",
            scenario_amounts_cad=[500.0, 1_000.0],
        )
        self.assertTrue(all(s.shares_held_before == 0 for s in ctx.incremental_scenarios))
        self.assertTrue(all(s.new_total_shares > 0
                            for s in ctx.incremental_scenarios if s.shares_purchasable > 0))


# ===========================================================================
# Scenario 13: Dividend contribution
# ===========================================================================

class TestDividendContribution(unittest.TestCase):

    def setUp(self):
        self.portfolio = make_dividend_portfolio()
        # DIV1.TO: 200 shares × $2.00/share = $400 income CAD
        self.ctx = build_portfolio_context(portfolio=self.portfolio, ticker="DIV1.TO")

    def test_dividend_income_calculated(self):
        self.assertAlmostEqual(self.ctx.annual_dividend_income_local, 400.0, places=1)
        self.assertAlmostEqual(self.ctx.annual_dividend_income_cad, 400.0, places=1)

    def test_dividend_yield_on_cost_calculated(self):
        # $2 / $40 = 5%
        self.assertIsNotNone(self.ctx.dividend_yield_on_cost_pct)
        self.assertAlmostEqual(self.ctx.dividend_yield_on_cost_pct, 5.0, places=1)

    def test_dividend_yield_on_current_price(self):
        # $2 / $45 ≈ 4.44%
        self.assertIsNotNone(self.ctx.dividend_yield_on_current_price_pct)
        self.assertAlmostEqual(self.ctx.dividend_yield_on_current_price_pct, 200/45, delta=0.1)

    def test_dividend_contribution_to_portfolio(self):
        # DIV1 income = 400, DIV2 income = 150×3=450, total = 850
        # DIV1 contribution = 400/850 ≈ 47.1%
        self.assertGreater(self.ctx.dividend_contribution_to_portfolio_income_pct, 30.0)
        self.assertLess(self.ctx.dividend_contribution_to_portfolio_income_pct, 70.0)

    def test_non_dividend_position_zero_income(self):
        ctx = build_portfolio_context(portfolio=self.portfolio, ticker="GROW.TO")
        self.assertEqual(ctx.annual_dividend_income_local, 0.0)
        self.assertEqual(ctx.dividend_contribution_to_portfolio_income_pct, 0.0)


# ===========================================================================
# Scenario 14: Growth vs income classification
# ===========================================================================

class TestPositionTypeClassification(unittest.TestCase):

    def test_income_position_type(self):
        portfolio = make_dividend_portfolio()
        ctx = build_portfolio_context(portfolio=portfolio, ticker="DIV1.TO")
        self.assertEqual(ctx.position_type, PositionType.INCOME.value)

    def test_growth_position_type(self):
        portfolio = make_dividend_portfolio()
        ctx = build_portfolio_context(portfolio=portfolio, ticker="GROW.TO")
        self.assertEqual(ctx.position_type, PositionType.GROWTH.value)

    def test_new_company_position_type_preserved(self):
        portfolio = make_simple_portfolio()
        ctx = build_portfolio_context(
            portfolio=portfolio,
            ticker="REIT.UN.TO",
            current_price_local=18.0,
            currency="CAD",
            position_type=PositionType.REIT.value,
        )
        self.assertEqual(ctx.position_type, PositionType.REIT.value)


# ===========================================================================
# Scenario 15 & 16: No optimization, no automatic optimal weight
# ===========================================================================

class TestNoAutomaticOptimization(unittest.TestCase):

    def setUp(self):
        self.portfolio = make_simple_portfolio()
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="A.TO",
            scenario_amounts_cad=[500.0, 1_000.0, 5_000.0],
        )

    def test_no_optimal_weight_field(self):
        d = self.ctx.to_dict()
        self.assertNotIn("optimal_weight_pct", d)
        self.assertNotIn("recommended_weight", d)
        self.assertNotIn("target_allocation", d)

    def test_scenarios_do_not_recommend_amount(self):
        # "no investment recommendation" is correct phrasing — contains "recommend" as negation.
        # Check that notes don't *make* recommendations (positive action phrases).
        for s in self.ctx.incremental_scenarios:
            note_lower = s.note.lower()
            self.assertNotIn("should invest", note_lower)
            self.assertNotIn("optimal", note_lower)
            self.assertNotIn("you should buy", note_lower)
            self.assertNotIn("advised to", note_lower)

    def test_contextual_observations_have_no_recommendations(self):
        # "holding" is used factually ("existing holding") — check for action *phrases* instead
        action_phrases = [
            "you should", "we recommend", "consider selling", "consider buying",
            "accumulate", "exit the position", "do not sell", "do not buy",
        ]
        obs = " ".join(self.ctx.contextual_observations)
        for phrase in action_phrases:
            self.assertNotIn(phrase, obs.lower(), msg=f"Found recommendation phrase: {phrase!r}")

    def test_phase7_note_present(self):
        self.assertIn("Phase 7", self.ctx.for_phase7_note)

    def test_phase7_note_in_json(self):
        d = self.ctx.to_dict()
        self.assertIn("for_phase7_note", d)
        self.assertIn("Phase 7", d["for_phase7_note"])


# ===========================================================================
# Scenario 17: No sunk-cost reasoning
# ===========================================================================

class TestNoSunkCostReasoning(unittest.TestCase):

    def setUp(self):
        # Deep loss position (-40%)
        portfolio = Portfolio(
            positions=[
                _pos("UNDERWATER.TO", shares=200, avg_cost=100, price=60,
                     sector="Energy", geography="Canada"),
            ],
            valuation_date="2024-12-31",
        )
        self.ctx = build_portfolio_context(portfolio=portfolio, ticker="UNDERWATER.TO")

    def test_cost_basis_note_explicitly_rejects_sunk_cost(self):
        note = self.ctx.cost_basis_note.lower()
        # Note must explicitly address the issue
        self.assertTrue(
            "not" in note or "sunk" in note or "does not" in note,
            msg=f"Cost basis note should reject sunk-cost reasoning: {self.ctx.cost_basis_note}"
        )

    def test_unrealized_loss_documented_correctly(self):
        self.assertAlmostEqual(self.ctx.unrealized_gain_loss_pct, -40.0, places=1)

    def test_portfolio_risks_do_not_anchor_on_cost(self):
        risks_text = " ".join(self.ctx.portfolio_risks).lower()
        for phrase in ["average cost", "cost basis", "original price", "purchase price"]:
            self.assertNotIn(phrase, risks_text)

    def test_observations_do_not_say_wait_to_recover(self):
        obs = " ".join(self.ctx.contextual_observations).lower()
        self.assertNotIn("wait to recover", obs)
        self.assertNotIn("until breakeven", obs)


# ===========================================================================
# Scenario 18: Economic group / related-exposure overlap
# ===========================================================================

class TestEconomicGroupOverlap(unittest.TestCase):

    def setUp(self):
        positions = [
            _pos("TD.TO",  shares=100, price=80,  sector="Financials",
                 geography="Canada", economic_group="Canadian Banks"),
            _pos("CM.TO",  shares=100, price=60,  sector="Financials",
                 geography="Canada", economic_group="Canadian Banks"),
            _pos("BNS.TO", shares=100, price=65,  sector="Financials",
                 geography="Canada", economic_group="Canadian Banks"),
            _pos("GROW.TO", shares=100, price=100, sector="Technology",
                 geography="Canada", economic_group="Other"),
        ]
        self.portfolio = Portfolio(positions=positions, valuation_date="2024-12-31")
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="TD.TO",
            sector="Financials",
            geography="Canada",
            economic_group="Canadian Banks",
        )

    def test_related_holdings_populated(self):
        self.assertIn("CM.TO", self.ctx.related_holdings)
        self.assertIn("BNS.TO", self.ctx.related_holdings)
        self.assertNotIn("TD.TO", self.ctx.related_holdings)

    def test_economic_group_weight_reflects_all_banks(self):
        # 3 banks, each ~$6000-$8000; GROW is $10,000
        # Bank total ≈ $20,500 / $30,500 ≈ 67%
        self.assertGreater(self.ctx.economic_group_weight_in_portfolio_pct, 50.0)

    def test_economic_group_flag_present(self):
        eco_flags = [f for f in self.ctx.concentration_flags
                     if f.flag_type == ConcentrationFlagType.ECONOMIC_GROUP]
        self.assertTrue(len(eco_flags) > 0)

    def test_portfolio_risk_mentions_correlated_exposure(self):
        risks_text = " ".join(self.ctx.portfolio_risks).lower()
        self.assertIn("correlated", risks_text)

    def test_observation_mentions_related_holdings(self):
        obs_text = " ".join(self.ctx.contextual_observations)
        self.assertIn("Canadian Banks", obs_text)


# ===========================================================================
# Scenario 19: Phase 5 EV/EBITDA applicability fix verification
# ===========================================================================

class TestPhase5EVEBITDAFix(unittest.TestCase):

    def test_negative_fcf_ev_ebitda_not_applicable_in_selector(self):
        """After Phase 5 fix, selector and runner both agree for NEGATIVE_FCF."""
        from analytics.valuation.valuation_models import (
            ValuationInput, InputItem, InputType, CompanyType, MethodApplicability,
            ValuationMethod,
        )
        from analytics.valuation.method_selector import select_methods

        def _item(name, value):
            return InputItem(name=name, value=value, currency="CAD",
                             input_type=InputType.REPORTED)

        inputs = ValuationInput(
            ticker="BURN.TO", company_name="Cash Burner",
            company_type=CompanyType.NEGATIVE_FCF,
            valuation_date="2024-12-31", currency="CAD",
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

        methods = select_methods(inputs)
        applicable = [
            m.method.value for m in methods
            if m.applicability in (
                MethodApplicability.APPLICABLE,
                MethodApplicability.APPLICABLE_WITH_CAVEATS
            )
        ]
        not_applicable = [
            m.method.value for m in methods
            if m.applicability == MethodApplicability.NOT_APPLICABLE
        ]

        # Selector must now agree with runner: EV_EBITDA is NOT_APPLICABLE
        self.assertNotIn(ValuationMethod.EV_EBITDA.value, applicable)
        self.assertIn(ValuationMethod.EV_EBITDA.value, not_applicable)

    def test_negative_fcf_confidence_not_inflated(self):
        """With EV_EBITDA correctly excluded, n_applicable is accurate."""
        from analytics.valuation.valuation_models import (
            ValuationInput, InputItem, InputType, CompanyType,
        )
        from analytics.valuation.valuation_synthesizer import run_valuation

        def _item(name, value):
            return InputItem(name=name, value=value, currency="CAD",
                             input_type=InputType.REPORTED)

        inputs = ValuationInput(
            ticker="BURN.TO", company_name="Cash Burner",
            company_type=CompanyType.NEGATIVE_FCF,
            valuation_date="2024-12-31", currency="CAD",
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

        result = run_valuation(inputs)
        # EV_EBITDA not in applicable (was incorrectly counted before fix)
        self.assertNotIn("EV_EBITDA", result.applicable_methods())
        # Only REVENUE_MULTIPLE is applicable — so n_applicable = 1
        self.assertIn("RevenueMultiple", result.applicable_methods())
        self.assertEqual(len(result.applicable_methods()), 1)

    def test_standard_industrial_ev_ebitda_still_applicable(self):
        """The fix must not break EV_EBITDA for normal industrial companies."""
        from analytics.valuation.valuation_models import (
            ValuationInput, InputItem, InputType, CompanyType, MethodApplicability,
            ValuationMethod,
        )
        from analytics.valuation.method_selector import select_methods

        def _item(name, value):
            return InputItem(name=name, value=value, currency="CAD",
                             input_type=InputType.REPORTED)

        inputs = ValuationInput(
            ticker="CNR.TO", company_name="CN Rail",
            company_type=CompanyType.INDUSTRIAL,
            valuation_date="2024-12-31", currency="CAD",
            current_price=_item("Price", 170.0),
            shares_outstanding=_item("Shares", 670.0),
            ebitda=_item("EBITDA", 8_500.0),
            total_debt=_item("Debt", 15_000.0),
            cash_and_equivalents=_item("Cash", 1_200.0),
            moat_strength="STRONG",
            financial_quality_hint="EXCELLENT",
        )
        methods = select_methods(inputs)
        applicable = [
            m.method.value for m in methods
            if m.applicability == MethodApplicability.APPLICABLE
        ]
        self.assertIn(ValuationMethod.EV_EBITDA.value, applicable)


# ===========================================================================
# Scenario 20: JSON serialization + Portfolio model
# ===========================================================================

class TestJSONSerialization(unittest.TestCase):

    def setUp(self):
        self.portfolio = make_simple_portfolio()
        self.ctx = build_portfolio_context(
            portfolio=self.portfolio,
            ticker="A.TO",
            scenario_amounts_cad=[500.0, 1_000.0],
        )

    def test_to_dict_has_required_keys(self):
        d = self.ctx.to_dict()
        required = [
            "ticker", "is_existing_holding", "shares_held", "market_value_cad",
            "portfolio_weight_pct", "unrealized_gain_loss_pct", "cost_basis_note",
            "sector", "geography", "concentration_flags", "incremental_scenarios",
            "contextual_observations", "for_phase7_note",
        ]
        for key in required:
            self.assertIn(key, d, msg=f"Missing key: {key}")

    def test_json_roundtrip_valid(self):
        j = self.ctx.to_json()
        parsed = json.loads(j)
        self.assertEqual(parsed["ticker"], "A.TO")

    def test_concentration_flags_serialized(self):
        d = self.ctx.to_dict()
        for flag in d["concentration_flags"]:
            self.assertIn("flag_type", flag)
            self.assertIn("severity", flag)
            self.assertIn("description", flag)

    def test_incremental_scenarios_serialized(self):
        d = self.ctx.to_dict()
        for s in d["incremental_scenarios"]:
            self.assertIn("investment_amount_cad", s)
            self.assertIn("new_portfolio_weight_pct", s)
            self.assertIn("note", s)

    def test_portfolio_model_to_dict(self):
        d = self.portfolio.to_dict()
        self.assertIn("position_count", d)
        self.assertIn("total_market_value_cad", d)
        self.assertIn("sector_weights_pct", d)
        self.assertIn("geography_weights_pct", d)


# ===========================================================================
# Portfolio Calculator unit tests
# ===========================================================================

class TestPortfolioCalculator(unittest.TestCase):

    def test_position_weight_pct(self):
        self.assertAlmostEqual(position_weight_pct(5000, 100_000), 5.0, places=2)

    def test_position_weight_zero_total(self):
        self.assertEqual(position_weight_pct(1000, 0), 0.0)

    def test_hypothetical_weight(self):
        # Add $5000 to a $5000 position in a $100k portfolio
        new_w = hypothetical_weight_pct(5000, 5000, 100_000)
        self.assertAlmostEqual(new_w, 10_000 / 105_000 * 100, places=1)

    def test_dividend_contribution(self):
        self.assertAlmostEqual(
            dividend_contribution_to_portfolio_income_pct(400, 1000), 40.0, places=1
        )

    def test_dividend_contribution_zero_portfolio(self):
        self.assertEqual(
            dividend_contribution_to_portfolio_income_pct(400, 0), 0.0
        )

    def test_context_confidence_high(self):
        self.assertEqual(context_confidence([]), "HIGH")

    def test_context_confidence_medium(self):
        self.assertEqual(context_confidence(["gap1"]), "MEDIUM")

    def test_context_confidence_low(self):
        self.assertEqual(context_confidence(["g1", "g2", "g3"]), "LOW")


# ===========================================================================
# Incremental scenarios unit tests
# ===========================================================================

class TestIncrementalScenariosUnit(unittest.TestCase):

    def test_basic_scenario(self):
        scenarios = build_incremental_scenarios(
            scenario_amounts_cad=[1_000.0],
            current_price_local=50.0,
            currency="CAD",
            fx_rate_to_cad=1.0,
            shares_held=100.0,
            average_cost_local=40.0,
            current_portfolio_value_cad=100_000.0,
            current_position_value_cad=5_000.0,
        )
        self.assertEqual(len(scenarios), 1)
        s = scenarios[0]
        self.assertEqual(s.shares_purchasable, 20)          # floor(1000/50)
        self.assertAlmostEqual(s.actual_investment_cad, 1000.0, places=1)
        self.assertEqual(s.new_total_shares, 120)

    def test_usd_scenario_uses_fx(self):
        # $500 CAD / ($220 USD × 1.35) = $500 / $297 = 1 share
        scenarios = build_incremental_scenarios(
            scenario_amounts_cad=[500.0],
            current_price_local=220.0,
            currency="USD",
            fx_rate_to_cad=1.35,
            shares_held=10.0,
            average_cost_local=180.0,
            current_portfolio_value_cad=50_000.0,
            current_position_value_cad=2_970.0,  # 10 × $220 × 1.35
        )
        s = scenarios[0]
        import math
        expected_shares = math.floor(500.0 / (220.0 * 1.35))
        self.assertEqual(s.shares_purchasable, expected_shares)

    def test_insufficient_amount_gives_zero_shares(self):
        # $10 CAD for a $500 stock
        scenarios = build_incremental_scenarios(
            scenario_amounts_cad=[10.0],
            current_price_local=500.0,
            currency="CAD",
            fx_rate_to_cad=1.0,
            shares_held=0.0,
            average_cost_local=None,
            current_portfolio_value_cad=100_000.0,
            current_position_value_cad=0.0,
        )
        s = scenarios[0]
        self.assertEqual(s.shares_purchasable, 0)
        self.assertIn("insufficient", s.note.lower())

    def test_new_position_average_cost_equals_price(self):
        scenarios = build_incremental_scenarios(
            scenario_amounts_cad=[1_000.0],
            current_price_local=50.0,
            currency="CAD",
            fx_rate_to_cad=1.0,
            shares_held=0.0,
            average_cost_local=None,
            current_portfolio_value_cad=100_000.0,
            current_position_value_cad=0.0,
        )
        s = scenarios[0]
        self.assertAlmostEqual(s.new_average_cost_local, 50.0, places=1)

    def test_updated_average_cost_blended(self):
        # Existing: 100 shares @ $40; buying 20 more @ $50
        scenarios = build_incremental_scenarios(
            scenario_amounts_cad=[1_000.0],
            current_price_local=50.0,
            currency="CAD",
            fx_rate_to_cad=1.0,
            shares_held=100.0,
            average_cost_local=40.0,
            current_portfolio_value_cad=100_000.0,
            current_position_value_cad=5_000.0,
        )
        s = scenarios[0]
        # new avg = (100×40 + 20×50) / 120 = (4000 + 1000) / 120 = 41.67
        expected_avg = (100 * 40 + 20 * 50) / 120
        self.assertAlmostEqual(s.new_average_cost_local, expected_avg, places=1)


# ===========================================================================
# Concentration analyzer unit tests
# ===========================================================================

class TestConcentrationAnalyzerUnit(unittest.TestCase):

    def test_no_flags_for_small_weights(self):
        flags = analyze_concentration(
            ticker="SMALL.TO", sector="Industrials", geography="Canada",
            economic_group="Manufacturing",
            position_weight_pct=3.0, sector_weight_pct=15.0,
            geography_weight_pct=55.0, economic_group_weight_pct=5.0,
        )
        self.assertEqual(len(flags), 0)

    def test_position_note_at_5pct(self):
        flags = analyze_concentration(
            ticker="MED.TO", sector="Industrials", geography="Canada",
            economic_group="",
            position_weight_pct=6.0, sector_weight_pct=10.0,
            geography_weight_pct=50.0, economic_group_weight_pct=0.0,
        )
        pos_flags = [f for f in flags if f.flag_type == ConcentrationFlagType.POSITION_SIZE]
        self.assertEqual(len(pos_flags), 1)
        self.assertEqual(pos_flags[0].severity, FlagSeverity.NOTE)

    def test_position_elevated_at_9pct(self):
        flags = analyze_concentration(
            ticker="BIG.TO", sector="Industrials", geography="Canada",
            economic_group="",
            position_weight_pct=9.0, sector_weight_pct=9.0,
            geography_weight_pct=50.0, economic_group_weight_pct=0.0,
        )
        pos_flags = [f for f in flags if f.flag_type == ConcentrationFlagType.POSITION_SIZE]
        self.assertEqual(pos_flags[0].severity, FlagSeverity.ELEVATED)

    def test_position_high_at_15pct(self):
        flags = analyze_concentration(
            ticker="HUGE.TO", sector="Industrials", geography="Canada",
            economic_group="",
            position_weight_pct=15.0, sector_weight_pct=15.0,
            geography_weight_pct=50.0, economic_group_weight_pct=0.0,
        )
        pos_flags = [f for f in flags if f.flag_type == ConcentrationFlagType.POSITION_SIZE]
        self.assertEqual(pos_flags[0].severity, FlagSeverity.HIGH)

    def test_sector_flag_triggered_above_25pct(self):
        flags = analyze_concentration(
            ticker="A.TO", sector="Energy", geography="Canada",
            economic_group="",
            position_weight_pct=3.0, sector_weight_pct=30.0,
            geography_weight_pct=50.0, economic_group_weight_pct=0.0,
        )
        sector_flags = [f for f in flags if f.flag_type == ConcentrationFlagType.SECTOR]
        self.assertTrue(len(sector_flags) > 0)

    def test_other_economic_group_not_flagged(self):
        """'Other' economic group should never trigger an economic-group flag."""
        flags = analyze_concentration(
            ticker="A.TO", sector="Industrials", geography="Canada",
            economic_group="Other",
            position_weight_pct=3.0, sector_weight_pct=10.0,
            geography_weight_pct=50.0, economic_group_weight_pct=50.0,
        )
        eco_flags = [f for f in flags if f.flag_type == ConcentrationFlagType.ECONOMIC_GROUP]
        self.assertEqual(len(eco_flags), 0)

    def test_flags_are_context_not_directives(self):
        flags = analyze_concentration(
            ticker="HUGE.TO", sector="Energy", geography="Canada",
            economic_group="Canadian Energy",
            position_weight_pct=20.0, sector_weight_pct=50.0,
            geography_weight_pct=85.0, economic_group_weight_pct=35.0,
        )
        for f in flags:
            self.assertNotIn("BUY", f.description)
            self.assertNotIn("SELL", f.description)
            # The context field should signal awareness, not prohibition
            ctx_lower = f.context.lower()
            self.assertTrue(
                "awareness" in ctx_lower or "context" in ctx_lower or "constraint" in ctx_lower,
                msg=f"Context field should signal awareness/context: {f.context}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
