"""
Financial Quality Engine
========================
Takes a CompanyFinancialMetrics object and produces a structured,
multi-dimensional financial quality assessment.

Design principles:
- No single overall "score" — that would imply false precision
- Each dimension is assessed independently with a classification + evidence
- Strengths and concerns are explicitly listed for Claude to interpret
- Industry context flags are always surfaced (Claude applies judgment)
- Distinguish temporary from structural where possible
- The engine produces inputs for reasoning; Claude produces the conclusion

Output: FinancialQualityAssessment
  → Consumed by Phase 7 (Decision Engine)
  → Displayed in investment analysis reports
  → Stored in thesis JSON under financial_summary
"""

import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.financial_quality.financial_metrics_model import (
    CompanyFinancialMetrics, Trend
)
from analytics.financial_quality.thresholds_engine import (
    classify_roic, classify_debt_to_assets, classify_dividend_payout,
    classify_dividend_yield, classify_revenue_growth_cagr,
    classify_fcf_conversion, ClassificationResult
)
from analytics.financial_quality.calculations import (
    extract_cagr_from_series, count_negative_growth_years
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class DimensionAssessment:
    """
    Assessment of a single financial quality dimension.
    Not a score — a structured evidence + classification package.
    """
    dimension: str
    classification: str                    # Excellent / Strong / Good / Watch / Concern / N/A
    headline: str                          # One-line summary
    evidence: List[str] = field(default_factory=list)   # Specific data points supporting the classification
    flags: List[str] = field(default_factory=list)      # Items requiring Claude's interpretation
    requires_industry_context: bool = False
    requires_trajectory_review: bool = False
    data_available: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FinancialQualityAssessment:
    """
    Full financial quality assessment for a company.

    This is the primary output of the Financial Quality Engine.
    It is structured, explainable, and designed to support — not replace —
    qualitative investment judgment.
    """
    ticker: str
    company_name: str
    assessment_date: str
    is_emerging_company: bool = False
    is_financial_institution: bool = False
    is_etf: bool = False

    # Dimension assessments
    revenue_growth: Optional[DimensionAssessment] = None
    margins: Optional[DimensionAssessment] = None
    free_cash_flow: Optional[DimensionAssessment] = None
    roic: Optional[DimensionAssessment] = None
    balance_sheet: Optional[DimensionAssessment] = None
    dividend: Optional[DimensionAssessment] = None
    earnings_quality: Optional[DimensionAssessment] = None

    # Synthesis (populated by engine, interpreted by Claude)
    strengths: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)
    neutral_observations: List[str] = field(default_factory=list)
    for_claude_interpretation: List[str] = field(default_factory=list)

    # Data quality
    data_completeness_pct: Optional[float] = None
    missing_dimensions: List[str] = field(default_factory=list)
    data_caveats: List[str] = field(default_factory=list)

    def overall_classification_hint(self) -> str:
        """
        A rough hint at overall financial quality — NOT a definitive rating.
        Claude must interpret this in context of business model, industry, stage.
        """
        dims = [
            self.revenue_growth, self.margins, self.free_cash_flow,
            self.roic, self.balance_sheet
        ]
        available = [d for d in dims if d and d.data_available]
        if not available:
            return "Insufficient Data"

        score_map = {
            "Excellent": 5, "Strong": 4, "Good": 3,
            "Watch": 2, "Concern": 1, "High Concern": 0,
            "N/A": None, "Insufficient Data": None,
            "Industry-Specific": None
        }
        scores = [score_map.get(d.classification) for d in available]
        scores = [s for s in scores if s is not None]
        if not scores:
            return "Insufficient Data"
        avg = sum(scores) / len(scores)
        if avg >= 4.5:
            return "Excellent"
        elif avg >= 3.5:
            return "Strong"
        elif avg >= 2.5:
            return "Good"
        elif avg >= 1.5:
            return "Watch"
        else:
            return "Concern"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["overall_classification_hint"] = self.overall_classification_hint()
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def summary_text(self) -> str:
        """
        Compact human-readable summary for use in chat responses.
        Designed to be pasted directly into Claude's analysis context.
        """
        lines = [
            f"=== Financial Quality: {self.ticker} ({self.company_name}) ===",
            f"Overall hint: {self.overall_classification_hint()} "
            f"(data completeness: {self.data_completeness_pct or 0:.0f}%)",
            "",
        ]

        dims = [
            ("Revenue Growth", self.revenue_growth),
            ("Margins", self.margins),
            ("Free Cash Flow", self.free_cash_flow),
            ("ROIC", self.roic),
            ("Balance Sheet", self.balance_sheet),
            ("Dividend", self.dividend),
            ("Earnings Quality", self.earnings_quality),
        ]
        for label, dim in dims:
            if dim:
                lines.append(f"  {label:<20} {dim.classification:<15} {dim.headline}")
                for e in dim.evidence[:3]:   # top 3 evidence points
                    lines.append(f"    • {e}")

        if self.strengths:
            lines += ["", "Strengths:"] + [f"  ✓ {s}" for s in self.strengths]
        if self.concerns:
            lines += ["", "Concerns:"] + [f"  ⚠ {c}" for c in self.concerns]
        if self.for_claude_interpretation:
            lines += ["", "For Qualitative Interpretation:"] + [f"  → {i}" for i in self.for_claude_interpretation]
        if self.data_caveats:
            lines += ["", "Data Caveats:"] + [f"  ℹ {c}" for c in self.data_caveats]

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Classification to readable label
# ---------------------------------------------------------------------------

_BUCKET_MAP = {
    # Revenue growth
    "Excellent": "Excellent",
    "Strong": "Strong",
    "Adequate": "Good",
    "Below Preference": "Watch",
    "Negative Growth": "Concern",
    # Debt
    "Preferred": "Excellent",
    "Acceptable": "Good",
    "Investigate": "Watch",
    "High Concern": "Concern",
    "Industry-Specific": "Industry-Specific",
    # Dividend payout
    "Strong Cushion": "Excellent",
    "Preferred": "Strong",
    "Caution": "Watch",
    "Sustainability Concern": "Concern",
    "Significant Concern": "Concern",
    "Negative Earnings Warning": "Concern",
    # FCF
    "Good": "Good",
    "Negative FCF Warning": "Concern",
    # Div yield
    "Within Preferred Range": "Good",
    "N/A": "N/A",
}


def _standardize(classification: str) -> str:
    return _BUCKET_MAP.get(classification, classification)


# ---------------------------------------------------------------------------
# Individual dimension assessors
# ---------------------------------------------------------------------------

def _assess_revenue_growth(m: CompanyFinancialMetrics, is_emerging: bool) -> DimensionAssessment:
    rg = m.revenue_growth
    evidence = []
    flags = []

    if not rg.annual_revenues:
        return DimensionAssessment(
            dimension="Revenue Growth",
            classification="N/A",
            headline="No revenue data available",
            data_available=False
        )

    # CAGRs
    if rg.cagr_5yr is not None:
        result = classify_revenue_growth_cagr(rg.cagr_5yr, 5)
        classification = _standardize(result.classification)
        evidence.append(f"5yr revenue CAGR: {rg.cagr_5yr:.1f}% ({result.classification})")
    elif rg.cagr_3yr is not None:
        result = classify_revenue_growth_cagr(rg.cagr_3yr, 3)
        classification = _standardize(result.classification)
        evidence.append(f"3yr revenue CAGR: {rg.cagr_3yr:.1f}% (5yr not available)")
    else:
        classification = "N/A"
        evidence.append("Insufficient history for CAGR calculation")

    if rg.cagr_3yr is not None and rg.cagr_5yr is not None:
        if rg.cagr_3yr > rg.cagr_5yr + 2:
            evidence.append(f"3yr CAGR ({rg.cagr_3yr:.1f}%) > 5yr CAGR ({rg.cagr_5yr:.1f}%) — growth accelerating")
        elif rg.cagr_3yr < rg.cagr_5yr - 2:
            evidence.append(f"3yr CAGR ({rg.cagr_3yr:.1f}%) < 5yr CAGR ({rg.cagr_5yr:.1f}%) — growth decelerating")
            flags.append("Revenue growth decelerating — investigate whether cyclical or structural")

    # Consistency
    if rg.negative_growth_years is not None and rg.negative_growth_years > 0:
        evidence.append(f"Negative growth years: {rg.negative_growth_years} of {rg.data_years_available}")
        if rg.negative_growth_years >= 2:
            flags.append(f"{rg.negative_growth_years} years of revenue decline — investigate causes")
            classification = min_class(classification, "Watch")

    if rg.growth_volatility is not None:
        if rg.growth_volatility > 15:
            evidence.append(f"Growth volatility (std dev): {rg.growth_volatility:.1f}% — high inconsistency")
            flags.append("High revenue growth volatility — does not reflect durable, consistent growth")
        elif rg.growth_volatility < 5:
            evidence.append(f"Growth volatility: {rg.growth_volatility:.1f}% — very consistent")

    # Organic growth note
    if rg.organic_vs_acquisition_note:
        flags.append(rg.organic_vs_acquisition_note)

    # Trend
    if rg.trend == Trend.IMPROVING:
        evidence.append("Revenue trend: improving")
    elif rg.trend == Trend.DETERIORATING:
        evidence.append("Revenue trend: deteriorating")
        flags.append("Revenue trend is deteriorating — determine if temporary or structural")

    if is_emerging and classification in ("Watch", "Concern"):
        flags.append("Emerging company context: lower/volatile growth may be acceptable if trajectory is improving")

    headline = f"{rg.cagr_5yr:.1f}% 5yr CAGR" if rg.cagr_5yr is not None else (
        f"{rg.cagr_3yr:.1f}% 3yr CAGR" if rg.cagr_3yr is not None else "Insufficient data"
    )

    return DimensionAssessment(
        dimension="Revenue Growth",
        classification=classification,
        headline=headline,
        evidence=evidence,
        flags=flags,
        requires_trajectory_review=True
    )


def _assess_margins(m: CompanyFinancialMetrics) -> DimensionAssessment:
    mg = m.margins
    evidence = []
    flags = []

    if mg.gross_margin is None and mg.operating_margin is None:
        return DimensionAssessment(
            dimension="Margins",
            classification="N/A",
            headline="No margin data available",
            data_available=False
        )

    # Gross margin
    if mg.gross_margin is not None:
        evidence.append(f"Gross margin: {mg.gross_margin:.1f}% ({mg.gross_margin_trend or 'trend N/A'})")
        if mg.gross_margin < 20:
            flags.append("Low gross margin — may indicate commodity-like or high-competition business")

    # Operating margin
    if mg.operating_margin is not None:
        evidence.append(f"Operating margin: {mg.operating_margin:.1f}% ({mg.operating_margin_trend or 'trend N/A'})")

    # Net margin
    if mg.net_margin is not None:
        evidence.append(f"Net margin: {mg.net_margin:.1f}%")

    # FCF margin (meaningful quality indicator)
    if mg.fcf_margin is not None:
        evidence.append(f"FCF margin: {mg.fcf_margin:.1f}%")
        if mg.fcf_margin < mg.net_margin - 5 if mg.net_margin else False:
            flags.append("FCF margin materially below net margin — investigate working capital or non-cash items")

    # Classify based on operating margin as primary signal
    if mg.operating_margin is not None:
        if mg.operating_margin >= 20:
            classification = "Excellent"
        elif mg.operating_margin >= 12:
            classification = "Strong"
        elif mg.operating_margin >= 6:
            classification = "Good"
        elif mg.operating_margin >= 0:
            classification = "Watch"
        else:
            classification = "Concern"
            flags.append("Negative operating margin — business not yet profitable at operating level")
    else:
        classification = "N/A"

    # Trend signals
    if mg.operating_margin_trend == Trend.IMPROVING:
        evidence.append("Operating margin trend: expanding")
    elif mg.operating_margin_trend == Trend.DETERIORATING:
        evidence.append("Operating margin trend: contracting")
        flags.append("Contracting operating margins — determine if pricing pressure, cost inflation, or mix shift")

    if mg.gross_margin_trend == Trend.DETERIORATING and mg.operating_margin_trend == Trend.DETERIORATING:
        flags.append("Both gross and operating margins contracting — potential structural margin pressure")
        classification = min_class(classification, "Watch")

    headline = (
        f"Operating: {mg.operating_margin:.1f}%, FCF: {mg.fcf_margin:.1f}%"
        if mg.fcf_margin is not None and mg.operating_margin is not None
        else f"Operating: {mg.operating_margin:.1f}%" if mg.operating_margin is not None
        else f"Gross: {mg.gross_margin:.1f}%"
    )

    return DimensionAssessment(
        dimension="Margins",
        classification=classification,
        headline=headline,
        evidence=evidence,
        flags=flags,
        requires_industry_context=True,
        requires_trajectory_review=True
    )


def _assess_fcf(m: CompanyFinancialMetrics) -> DimensionAssessment:
    fcf = m.free_cash_flow
    evidence = []
    flags = []

    if fcf.fcf_current is None and not fcf.annual_fcf:
        return DimensionAssessment(
            dimension="Free Cash Flow",
            classification="N/A",
            headline="No FCF data available",
            data_available=False
        )

    # FCF level and trend
    if fcf.fcf_current is not None:
        fcf_m = fcf.fcf_current / 1e6
        sign = "+" if fcf.fcf_current >= 0 else ""
        evidence.append(f"FCF (latest year): {sign}${fcf_m:,.0f}M")

    if fcf.fcf_trend:
        evidence.append(f"FCF trend: {fcf.fcf_trend}")

    # Negative FCF years
    if fcf.recurring_negative_fcf:
        evidence.append(f"Recurring negative FCF: {fcf.negative_fcf_years} years")
        flags.append("Recurring negative FCF — determine if investment phase or structural cash burn")

    # FCF margin
    if fcf.fcf_margin_current is not None:
        evidence.append(f"FCF margin: {fcf.fcf_margin_current:.1f}%")

    # FCF conversion
    if fcf.fcf_conversion_ratio is not None:
        cr = fcf.fcf_conversion_ratio
        result = classify_fcf_conversion(cr)
        evidence.append(f"FCF conversion (FCF/Net Income): {cr:.2f}x ({result.classification})")
        if cr < 0:
            flags.append("Negative FCF conversion despite positive net income — investigate accruals/working capital")

    # CapEx intensity
    if fcf.capex_as_pct_revenue is not None:
        evidence.append(f"CapEx intensity: {fcf.capex_as_pct_revenue:.1f}% of revenue")
        if fcf.capex_as_pct_revenue > 20:
            flags.append("High CapEx intensity — capital-heavy business; verify maintenance vs growth CapEx")

    # Classification
    if fcf.recurring_negative_fcf:
        classification = "Concern"
    elif fcf.fcf_current is not None and fcf.fcf_current < 0:
        classification = "Watch"
        flags.append("Most recent year FCF is negative — determine if cyclical trough or deteriorating economics")
    elif fcf.fcf_conversion_ratio is not None:
        result = classify_fcf_conversion(fcf.fcf_conversion_ratio)
        classification = _standardize(result.classification)
        if fcf.fcf_trend == Trend.IMPROVING:
            classification = max_class(classification, "Good")
    elif fcf.fcf_trend == Trend.IMPROVING:
        classification = "Good"
    else:
        classification = "Watch"

    headline = (
        f"FCF margin {fcf.fcf_margin_current:.1f}%, conversion {fcf.fcf_conversion_ratio:.2f}x"
        if fcf.fcf_margin_current is not None and fcf.fcf_conversion_ratio is not None
        else f"FCF trend: {fcf.fcf_trend}" if fcf.fcf_trend else "Limited FCF data"
    )

    return DimensionAssessment(
        dimension="Free Cash Flow",
        classification=classification,
        headline=headline,
        evidence=evidence,
        flags=flags,
        requires_trajectory_review=True
    )


def _assess_roic(m: CompanyFinancialMetrics, is_emerging: bool) -> DimensionAssessment:
    roic = m.roic
    evidence = []
    flags = []

    if roic.current is None and not roic.annual_roic:
        # Provide what we have from ROE proxy if noted in data_quality_notes
        roic_note = next(
            (n for n in m.data_quality_notes if "ROIC approximated" in n), None
        )
        if roic_note:
            evidence.append(f"⚠ {roic_note}")
            flags.append("Full ROIC requires Phase 3 financial quality engine — using ROE proxy for now")
            return DimensionAssessment(
                dimension="ROIC",
                classification="N/A",
                headline="Approximate only — Phase 3 ROIC calculation pending",
                evidence=evidence,
                flags=flags,
                data_available=False
            )
        return DimensionAssessment(
            dimension="ROIC",
            classification="N/A",
            headline="No ROIC data available",
            data_available=False
        )

    # Current ROIC
    if roic.current is not None:
        result = classify_roic(roic.current, is_emerging=is_emerging)
        classification = result.classification
        evidence.append(f"Current ROIC: {roic.current:.1f}% ({result.classification})")
    else:
        classification = "N/A"

    # Historical
    if roic.avg_3yr is not None:
        evidence.append(f"3yr avg ROIC: {roic.avg_3yr:.1f}%")
    if roic.avg_5yr is not None:
        evidence.append(f"5yr avg ROIC: {roic.avg_5yr:.1f}%")
    if roic.trend:
        evidence.append(f"ROIC trend: {roic.trend}")
        if roic.trend == Trend.DETERIORATING:
            flags.append("ROIC deteriorating — check if competitive advantage is eroding")

    if roic.moat_support_note:
        evidence.append(roic.moat_support_note)

    # Moat interpretation hint
    if roic.current is not None and roic.current >= 15:
        flags.append("High sustained ROIC can SUPPORT a moat thesis but does not prove it — qualitative verification required")

    if is_emerging and roic.current is not None and roic.current < 10:
        flags.append("Emerging company: lower ROIC may be acceptable if trajectory is improving and unit economics are strong")

    headline = (
        f"Current: {roic.current:.1f}%"
        + (f", 5yr avg: {roic.avg_5yr:.1f}%" if roic.avg_5yr is not None else "")
        if roic.current is not None else "Calculation pending"
    )

    return DimensionAssessment(
        dimension="ROIC",
        classification=classification,
        headline=headline,
        evidence=evidence,
        flags=flags,
        requires_trajectory_review=True
    )


def _assess_balance_sheet(
    m: CompanyFinancialMetrics,
    is_financial_institution: bool
) -> DimensionAssessment:
    db = m.debt
    evidence = []
    flags = []

    if db.total_assets is None and db.interest_bearing_debt is None:
        return DimensionAssessment(
            dimension="Balance Sheet",
            classification="N/A",
            headline="No balance sheet data available",
            data_available=False
        )

    # Debt/assets
    if db.debt_to_assets_pct is not None:
        result = classify_debt_to_assets(
            db.debt_to_assets_pct,
            is_financial_institution=is_financial_institution
        )
        classification = _standardize(result.classification)
        evidence.append(
            f"Interest-bearing debt / total assets: {db.debt_to_assets_pct:.1f}% ({result.classification})"
        )
        if is_financial_institution:
            flags.append("Financial institution — debt/assets threshold does not apply; use sector-specific metrics (Tier 1 capital, NIM, loan loss provisions)")
    else:
        classification = "N/A"

    # Net debt position
    if db.net_debt is not None:
        if db.net_debt < 0:
            evidence.append(f"Net cash position: ${abs(db.net_debt)/1e6:,.0f}M")
        else:
            evidence.append(f"Net debt: ${db.net_debt/1e6:,.0f}M")

    # Interest coverage
    if db.interest_coverage is not None:
        evidence.append(f"Interest coverage: {db.interest_coverage:.1f}x")
        if db.interest_coverage < 3:
            flags.append(f"Interest coverage {db.interest_coverage:.1f}x — thin margin; investigate ability to service debt")
            classification = min_class(classification, "Watch")
        elif db.interest_coverage < 1.5:
            flags.append("Interest coverage below 1.5x — high risk of financial distress")
            classification = "Concern"

    # FCF / debt
    if db.fcf_to_debt_ratio is not None:
        evidence.append(f"FCF / debt: {db.fcf_to_debt_ratio:.2f}x")
        if db.fcf_to_debt_ratio > 0.25:
            evidence.append("Debt could be repaid from FCF within ~4 years")

    # Debt trend
    if db.debt_trend:
        evidence.append(f"Leverage trend: {db.debt_trend}")
        if db.debt_trend == Trend.IMPROVING:
            evidence.append("Leverage declining over time — positive signal")
        elif db.debt_trend == Trend.DETERIORATING:
            flags.append("Leverage increasing — verify whether funding growth or covering operational weakness")

    headline = (
        f"{db.debt_to_assets_pct:.1f}% debt/assets"
        + (f", {db.interest_coverage:.1f}x coverage" if db.interest_coverage else "")
        if db.debt_to_assets_pct is not None else "Debt data limited"
    )

    return DimensionAssessment(
        dimension="Balance Sheet",
        classification=classification,
        headline=headline,
        evidence=evidence,
        flags=flags,
        requires_industry_context=True
    )


def _assess_dividend(m: CompanyFinancialMetrics) -> DimensionAssessment:
    div = m.dividend
    evidence = []
    flags = []

    if not div.pays_dividend:
        return DimensionAssessment(
            dimension="Dividend",
            classification="N/A",
            headline="No dividend — acceptable for growth-focused companies",
            evidence=["Company does not pay a dividend"],
            flags=["Verify whether retained capital is being reinvested at attractive returns (ROIC > cost of capital)"],
            data_available=True
        )

    # Yield
    if div.current_yield_pct is not None:
        result = classify_dividend_yield(div.current_yield_pct)
        evidence.append(f"Dividend yield: {div.current_yield_pct:.2f}% ({result.classification})")
        if result.classification == "Investigate":
            flags.append(f"Yield {div.current_yield_pct:.1f}% — investigate reason: stock decline, high payout, or genuine value?")

    # Payout ratio
    if div.payout_ratio_pct is not None:
        result = classify_dividend_payout(div.payout_ratio_pct)
        classification = _standardize(result.classification)
        evidence.append(f"Payout ratio (EPS basis): {div.payout_ratio_pct:.1f}% ({result.classification})")
    else:
        classification = "N/A"

    # FCF payout (more reliable than EPS payout)
    if div.fcf_payout_ratio_pct is not None:
        evidence.append(f"FCF payout ratio: {div.fcf_payout_ratio_pct:.1f}%")
        if div.fcf_payout_ratio_pct > 90:
            flags.append(f"FCF payout {div.fcf_payout_ratio_pct:.0f}% — dividend may be strained; monitor FCF trajectory")
            classification = min_class(classification, "Watch")
        elif div.fcf_payout_ratio_pct < 50:
            evidence.append("FCF covers dividend with strong headroom")

    # Growth
    if div.dividend_growth_3yr_cagr is not None:
        evidence.append(f"Dividend growth (3yr CAGR): {div.dividend_growth_3yr_cagr:.1f}%")
        if div.dividend_growth_3yr_cagr < 0:
            flags.append("Dividend has been cut in the recent period — investigate reason and sustainability going forward")
            classification = min_class(classification, "Watch")

    if div.dividend_cuts and div.dividend_cuts > 0:
        flags.append(f"Historical dividend cut(s): {div.dividend_cuts} — assess whether circumstances have changed")

    headline = (
        f"{div.current_yield_pct:.2f}% yield, {div.payout_ratio_pct:.0f}% payout ratio"
        if div.current_yield_pct is not None and div.payout_ratio_pct is not None
        else f"{div.current_yield_pct:.2f}% yield" if div.current_yield_pct is not None
        else "Dividend data limited"
    )

    return DimensionAssessment(
        dimension="Dividend",
        classification=classification,
        headline=headline,
        evidence=evidence,
        flags=flags
    )


def _assess_earnings_quality(m: CompanyFinancialMetrics) -> DimensionAssessment:
    eq = m.earnings_quality
    fcf = m.free_cash_flow
    evidence = []
    flags = []
    concerns = 0

    if not eq.annual_revenue and not eq.annual_net_income:
        return DimensionAssessment(
            dimension="Earnings Quality",
            classification="N/A",
            headline="No earnings data available",
            data_available=False
        )

    # Revenue vs FCF divergence
    if eq.revenue_vs_fcf_divergence:
        flags.append("Revenue growing while FCF is declining — investigate receivables, inventory, or working capital")
        concerns += 1

    # EPS vs cash divergence
    if eq.eps_vs_cashflow_divergence:
        flags.append("EPS improving while operating economics deteriorating — investigate earnings quality")
        concerns += 1

    # FCF conversion
    if fcf.fcf_conversion_ratio is not None:
        result = classify_fcf_conversion(fcf.fcf_conversion_ratio)
        evidence.append(f"FCF conversion: {fcf.fcf_conversion_ratio:.2f}x ({result.classification})")
        if fcf.fcf_conversion_ratio < 0.5:
            flags.append("Low FCF conversion — earnings may include significant non-cash or accrual items")
            concerns += 1

    # EPS trend
    if eq.eps_trend:
        evidence.append(f"Earnings trend: {eq.eps_trend}")

    # Earnings consistency
    if eq.eps_consistency:
        evidence.append(f"Earnings consistency: {eq.eps_consistency}")

    if eq.earnings_quality_note:
        evidence.append(eq.earnings_quality_note)

    # Recurring negative FCF alongside reported profits
    if fcf.recurring_negative_fcf and eq.eps_trend == Trend.IMPROVING:
        flags.append("⚠ Earnings appear positive/growing but FCF is recurrently negative — high priority investigation")
        concerns += 2

    classification = "Good" if concerns == 0 else "Watch" if concerns == 1 else "Concern"

    headline = (
        f"FCF conversion {fcf.fcf_conversion_ratio:.2f}x; earnings {eq.eps_trend}"
        if fcf.fcf_conversion_ratio is not None and eq.eps_trend
        else "Earnings quality data limited"
    )

    return DimensionAssessment(
        dimension="Earnings Quality",
        classification=classification,
        headline=headline,
        evidence=evidence,
        flags=flags
    )


# ---------------------------------------------------------------------------
# Ordering helper: rank quality tiers
# ---------------------------------------------------------------------------

_TIER = {
    "Excellent": 6, "Strong": 5, "Good": 4,
    "Watch": 3, "Concern": 2, "High Concern": 1,
    "N/A": 0, "Insufficient Data": 0, "Industry-Specific": 0
}

def min_class(a: str, b: str) -> str:
    """Return the lower-quality classification."""
    return a if _TIER.get(a, 0) <= _TIER.get(b, 0) else b

def max_class(a: str, b: str) -> str:
    """Return the higher-quality classification."""
    return a if _TIER.get(a, 0) >= _TIER.get(b, 0) else b


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

def assess_financial_quality(
    metrics: CompanyFinancialMetrics,
    is_emerging_company: bool = False,
    is_financial_institution: bool = False,
) -> FinancialQualityAssessment:
    """
    Run a full financial quality assessment on a CompanyFinancialMetrics object.

    Args:
        metrics: Normalized financial data (from Phase 2 normalizer)
        is_emerging_company: If True, apply more lenient thresholds for ROIC/growth
        is_financial_institution: If True, suppress standard debt/leverage thresholds

    Returns:
        FinancialQualityAssessment with all dimension scores, strengths,
        concerns, and flags for Claude interpretation.
    """
    from datetime import datetime

    is_etf = bool(metrics.data_quality_notes and any("ETF" in n for n in metrics.data_quality_notes))

    assessment = FinancialQualityAssessment(
        ticker=metrics.ticker,
        company_name=metrics.company_name,
        assessment_date=datetime.utcnow().isoformat()[:10],
        is_emerging_company=is_emerging_company,
        is_financial_institution=is_financial_institution,
        is_etf=is_etf,
        data_completeness_pct=metrics.data_completeness_pct,
    )

    if is_etf:
        assessment.for_claude_interpretation.append(
            "This is an ETF/Fund — financial quality dimensions are not applicable. "
            "Assess based on: NAV tracking, expense ratio, underlying holdings, and fit within portfolio."
        )
        return assessment

    # --- Run dimension assessments ---
    assessment.revenue_growth = _assess_revenue_growth(metrics, is_emerging_company)
    assessment.margins = _assess_margins(metrics)
    assessment.free_cash_flow = _assess_fcf(metrics)
    assessment.roic = _assess_roic(metrics, is_emerging_company)
    assessment.balance_sheet = _assess_balance_sheet(metrics, is_financial_institution)
    assessment.dividend = _assess_dividend(metrics)
    assessment.earnings_quality = _assess_earnings_quality(metrics)

    # --- Collect missing dimensions ---
    dim_map = [
        ("revenue_growth", assessment.revenue_growth),
        ("margins", assessment.margins),
        ("free_cash_flow", assessment.free_cash_flow),
        ("roic", assessment.roic),
        ("balance_sheet", assessment.balance_sheet),
    ]
    for name, dim in dim_map:
        if dim and not dim.data_available:
            assessment.missing_dimensions.append(name)

    # --- Synthesize strengths ---
    dims_for_synthesis = [
        assessment.revenue_growth, assessment.margins, assessment.free_cash_flow,
        assessment.roic, assessment.balance_sheet
    ]
    for dim in dims_for_synthesis:
        if not dim or not dim.data_available:
            continue
        if dim.classification in ("Excellent", "Strong"):
            assessment.strengths.append(f"{dim.dimension}: {dim.headline}")

    # Specific cross-dimension strengths
    if (assessment.revenue_growth and assessment.margins and
        assessment.revenue_growth.classification in ("Excellent", "Strong") and
        assessment.margins.classification in ("Excellent", "Strong")):
        assessment.strengths.append("Strong revenue growth paired with healthy margins — quality growth signal")

    if (assessment.free_cash_flow and assessment.balance_sheet and
        assessment.free_cash_flow.classification in ("Excellent", "Strong", "Good") and
        assessment.balance_sheet.classification in ("Excellent", "Strong")):
        assessment.strengths.append("Strong FCF generation with low leverage — financial durability")

    if (assessment.dividend and assessment.dividend.pays_dividend if hasattr(assessment.dividend, 'pays_dividend') else False):
        pass  # handled in dividend dimension

    # --- Synthesize concerns ---
    for dim in dims_for_synthesis:
        if not dim or not dim.data_available:
            continue
        if dim.classification in ("Concern", "High Concern"):
            assessment.concerns.append(f"{dim.dimension}: {dim.headline}")

    # All flags bubble up to for_claude_interpretation
    all_dims = [
        assessment.revenue_growth, assessment.margins, assessment.free_cash_flow,
        assessment.roic, assessment.balance_sheet, assessment.dividend,
        assessment.earnings_quality
    ]
    for dim in all_dims:
        if dim and dim.flags:
            assessment.for_claude_interpretation.extend(dim.flags)

    # --- Industry context reminders ---
    if is_financial_institution:
        assessment.for_claude_interpretation.append(
            "Financial institution: evaluate using sector-specific metrics — "
            "Tier 1 capital ratio, NIM, ROE, loan loss provisions, efficiency ratio"
        )

    if is_emerging_company:
        assessment.for_claude_interpretation.append(
            "Emerging company: prioritize trajectory over current levels — "
            "improving ROIC, expanding margins, and unit economics matter more than current absolute values"
        )

    # --- Data caveats ---
    if metrics.data_quality_notes:
        assessment.data_caveats.extend(metrics.data_quality_notes)
    if metrics.missing_fields:
        assessment.data_caveats.append(f"Missing data fields: {', '.join(metrics.missing_fields)}")
    if assessment.missing_dimensions:
        assessment.data_caveats.append(
            f"Dimensions with no data: {', '.join(assessment.missing_dimensions)} — "
            "verify data fetch succeeded; analysis may be incomplete"
        )

    return assessment


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from analytics.financial_quality.financial_metrics_model import (
        RevenueGrowthMetrics, MarginMetrics, FreeCashFlowMetrics,
        DebtMetrics, DividendMetrics, EarningsQualityMetrics
    )

    # Build a synthetic high-quality company
    m = CompanyFinancialMetrics(
        ticker="QUALITY.TO",
        company_name="Quality Corp",
        currency="CAD",
        data_as_of_date="2024-12-31",
        data_completeness_pct=95.0,
    )
    m.revenue_growth = RevenueGrowthMetrics(
        annual_revenues={2019: 2.0e9, 2020: 2.2e9, 2021: 2.5e9, 2022: 2.8e9, 2023: 3.1e9},
        cagr_3yr=11.4, cagr_5yr=9.2,
        negative_growth_years=0, growth_volatility=2.1,
        trend=Trend.IMPROVING, data_years_available=5,
    )
    m.margins = MarginMetrics(
        gross_margin=45.0, operating_margin=18.0, net_margin=13.0, fcf_margin=14.0,
        gross_margin_trend=Trend.STABLE, operating_margin_trend=Trend.IMPROVING,
    )
    m.free_cash_flow = FreeCashFlowMetrics(
        fcf_current=430e6, fcf_trend=Trend.IMPROVING,
        fcf_conversion_ratio=1.05, fcf_margin_current=14.0,
        recurring_negative_fcf=False, negative_fcf_years=0,
    )
    from analytics.financial_quality.financial_metrics_model import ROICMetrics
    m.roic = ROICMetrics(current=19.0, avg_3yr=17.5, avg_5yr=16.0, trend=Trend.STABLE)
    m.debt = DebtMetrics(
        debt_to_assets_pct=14.0, interest_coverage=22.0,
        fcf_to_debt_ratio=0.6, debt_trend=Trend.IMPROVING,
        interest_bearing_debt=700e6, total_assets=5e9, net_debt=500e6,
    )
    m.dividend = DividendMetrics(
        pays_dividend=True, current_yield_pct=2.5, payout_ratio_pct=38.0,
        fcf_payout_ratio_pct=30.0, dividend_growth_3yr_cagr=7.5,
    )
    m.earnings_quality = EarningsQualityMetrics(
        annual_revenue={2019: 2.0e9, 2020: 2.2e9, 2021: 2.5e9, 2022: 2.8e9, 2023: 3.1e9},
        annual_net_income={2019: 0.22e9, 2020: 0.27e9, 2021: 0.31e9, 2022: 0.36e9, 2023: 0.41e9},
        eps_trend=Trend.IMPROVING, eps_consistency="High",
        revenue_vs_fcf_divergence=False,
    )

    qa = assess_financial_quality(m, is_emerging_company=False)
    print(qa.summary_text())
    print(f"\nOverall classification hint: {qa.overall_classification_hint()}")
