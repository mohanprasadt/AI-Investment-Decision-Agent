"""
Thresholds Engine
=================
Applies the configured thresholds from config/thresholds.yaml to financial
metrics and returns structured classification results.

IMPORTANT DESIGN PRINCIPLE:
- Thresholds are GUIDELINES, not absolute pass/fail rules.
- Every classification result includes a note field for context.
- Industry context, company stage, and trajectory must all factor into
  final qualitative interpretation (done by Claude, not this module).
- This module handles ONLY the mechanical application of thresholds.
"""

import yaml
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Configuration Loader
# ---------------------------------------------------------------------------

def _load_thresholds() -> dict:
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "thresholds.yaml"
    )
    config_path = os.path.normpath(config_path)
    with open(config_path, "r") as f:
        # Strip comment lines (PyYAML handles # comments, but be safe)
        return yaml.safe_load(f)

_THRESHOLDS: Optional[dict] = None

def get_thresholds() -> dict:
    global _THRESHOLDS
    if _THRESHOLDS is None:
        _THRESHOLDS = _load_thresholds()
    return _THRESHOLDS


# ---------------------------------------------------------------------------
# Result Container
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """
    Output of a single threshold classification.
    Always carry forward the raw value and a context note.
    """
    metric_name: str
    raw_value: Optional[float]
    classification: str
    guideline_note: str = ""
    requires_industry_context: bool = False
    requires_trajectory_review: bool = False

    def __str__(self):
        value_str = f"{self.raw_value:.1f}" if self.raw_value is not None else "N/A"
        return (
            f"{self.metric_name}: {value_str} → {self.classification}"
            + (f" | {self.guideline_note}" if self.guideline_note else "")
        )


# ---------------------------------------------------------------------------
# Individual Classifiers
# ---------------------------------------------------------------------------

def classify_roic(roic_pct: Optional[float], is_emerging: bool = False) -> ClassificationResult:
    """
    Classify ROIC against configured thresholds.

    Args:
        roic_pct: ROIC as a percentage (e.g., 15.0 for 15%)
        is_emerging: If True, apply additional context for emerging companies
    """
    t = get_thresholds()["roic"]
    note = ""

    if roic_pct is None:
        return ClassificationResult("ROIC", None, "N/A", "Data unavailable")

    if roic_pct >= t["excellent"]:
        classification = "Excellent"
        note = f"≥{t['excellent']}% — strong capital efficiency"
    elif roic_pct >= t["strong"]:
        classification = "Strong"
        note = f"{t['strong']}–{t['excellent']}% — good capital returns"
    elif roic_pct >= t["watch"]:
        classification = "Watch"
        note = f"{t['watch']}–{t['strong']}% — monitor trend closely"
    else:
        classification = "Concern"
        note = f"<{t['concern']}% persistently — potential concern"

    if is_emerging and roic_pct < t["strong"]:
        note += " | EMERGING company: trajectory and improving economics may justify lower current ROIC"

    return ClassificationResult(
        metric_name="ROIC",
        raw_value=roic_pct,
        classification=classification,
        guideline_note=note,
        requires_trajectory_review=True  # Always check trend, not just current level
    )


def classify_debt_to_assets(
    debt_to_assets_pct: Optional[float],
    is_financial_institution: bool = False
) -> ClassificationResult:
    """
    Classify debt-to-assets ratio.

    NOTE: Thresholds are NOT applicable to banks, insurers, REITs.
    is_financial_institution flag disables threshold logic for those cases.
    """
    t = get_thresholds()["debt_to_assets"]

    if debt_to_assets_pct is None:
        return ClassificationResult(
            "Debt/Assets", None, "N/A", "Data unavailable",
            requires_industry_context=True
        )

    if is_financial_institution:
        return ClassificationResult(
            metric_name="Debt/Assets",
            raw_value=debt_to_assets_pct,
            classification="Industry-Specific",
            guideline_note="Financial institution — standard thresholds do not apply. Evaluate using sector-specific metrics.",
            requires_industry_context=True
        )

    if debt_to_assets_pct <= t["preferred_max"]:
        classification = "Preferred"
        note = f"≤{t['preferred_max']}% — low leverage, preferred range"
    elif debt_to_assets_pct <= t["acceptable_max"]:
        classification = "Acceptable"
        note = f"{t['preferred_max']}–{t['acceptable_max']}% — generally acceptable"
    elif debt_to_assets_pct <= t["investigate"]:
        classification = "Investigate"
        note = f"{t['acceptable_max']}–{t['investigate']}% — warrants investigation"
    else:
        classification = "High Concern"
        note = f">{t['high_concern']}% — high leverage concern"

    return ClassificationResult(
        metric_name="Debt/Assets (Interest-Bearing)",
        raw_value=debt_to_assets_pct,
        classification=classification,
        guideline_note=note,
        requires_industry_context=True
    )


def classify_dividend_payout(
    payout_ratio_pct: Optional[float]
) -> ClassificationResult:
    """Classify dividend payout ratio (Dividend / EPS)."""
    t = get_thresholds()["dividend"]["payout_ratio"]

    if payout_ratio_pct is None:
        return ClassificationResult("Dividend Payout Ratio", None, "N/A", "Data unavailable or no dividend")

    if payout_ratio_pct < 0:
        return ClassificationResult(
            "Dividend Payout Ratio", payout_ratio_pct,
            "Negative Earnings Warning",
            "Negative earnings — payout ratio not meaningful; investigate earnings quality"
        )

    if payout_ratio_pct < t["strong_cushion"]:
        classification = "Strong Cushion"
        note = f"<{t['strong_cushion']}% — well-covered dividend"
    elif payout_ratio_pct <= t["preferred_max"]:
        classification = "Preferred"
        note = f"{t['strong_cushion']}–{t['preferred_max']}% — preferred range"
    elif payout_ratio_pct <= t["caution"]:
        classification = "Caution"
        note = f"{t['preferred_max']}–{t['caution']}% — monitor coverage carefully"
    elif payout_ratio_pct < t["significant_concern"]:
        classification = "Sustainability Concern"
        note = f">{t['sustainability_concern']}% — dividend sustainability at risk"
    else:
        classification = "Significant Concern"
        note = f"≥{t['significant_concern']}% — dividend likely unsustainable or earnings distorted"

    return ClassificationResult(
        metric_name="Dividend Payout Ratio",
        raw_value=payout_ratio_pct,
        classification=classification,
        guideline_note=note
    )


def classify_dividend_yield(
    yield_pct: Optional[float]
) -> ClassificationResult:
    """
    Classify dividend yield. High yield triggers investigation, not automatic positive rating.
    """
    t = get_thresholds()["dividend"]

    if yield_pct is None:
        return ClassificationResult("Dividend Yield", None, "N/A", "No dividend or data unavailable")

    if yield_pct <= t["yield"]["preferred_max"]:
        classification = "Within Preferred Range"
        note = f"≤{t['yield']['preferred_max']}% — within preferred range"
    else:
        classification = "Investigate"
        note = (
            f">{t['yield']['preferred_max']}% — high yield requires investigation. "
            "Possible causes: falling stock price, business deterioration, high payout, "
            "cyclical business, or genuine attractive yield. "
            "NEVER assume high yield = good investment."
        )

    return ClassificationResult(
        metric_name="Dividend Yield",
        raw_value=yield_pct,
        classification=classification,
        guideline_note=note,
        requires_trajectory_review=True
    )


def classify_revenue_growth_cagr(
    cagr_pct: Optional[float],
    period_years: int = 5
) -> ClassificationResult:
    """Classify revenue growth CAGR."""
    t = get_thresholds()["revenue_growth"]
    label = f"Revenue CAGR ({period_years}yr)"

    if cagr_pct is None:
        return ClassificationResult(label, None, "N/A", "Data unavailable")

    if cagr_pct >= t["excellent_cagr_5yr"]:
        classification = "Excellent"
        note = f"≥{t['excellent_cagr_5yr']}% CAGR — strong growth"
    elif cagr_pct >= t["strong_cagr_5yr"]:
        classification = "Strong"
        note = f"{t['strong_cagr_5yr']}–{t['excellent_cagr_5yr']}% CAGR — good growth"
    elif cagr_pct >= t["preferred_min_cagr_5yr"]:
        classification = "Adequate"
        note = f"{t['preferred_min_cagr_5yr']}–{t['strong_cagr_5yr']}% CAGR — meets minimum preference"
    elif cagr_pct >= 0:
        classification = "Below Preference"
        note = f"<{t['preferred_min_cagr_5yr']}% — below preferred growth threshold"
    else:
        classification = "Negative Growth"
        note = "Negative CAGR — revenue has contracted over the period"

    return ClassificationResult(
        metric_name=label,
        raw_value=cagr_pct,
        classification=classification,
        guideline_note=note,
        requires_trajectory_review=True   # Must also check consistency, not just CAGR
    )


def classify_fcf_conversion(
    fcf_to_net_income_ratio: Optional[float]
) -> ClassificationResult:
    """
    Classify FCF conversion ratio (FCF / Net Income).
    Preferred: >= 70% (indicating earnings convert well to cash).
    """
    t = get_thresholds()["earnings_quality"]
    min_ratio = t["fcf_to_net_income_ratio_min"]

    if fcf_to_net_income_ratio is None:
        return ClassificationResult("FCF Conversion", None, "N/A", "Data unavailable")

    if fcf_to_net_income_ratio < 0:
        classification = "Negative FCF Warning"
        note = "Negative FCF despite positive net income — investigate working capital and capex"
    elif fcf_to_net_income_ratio >= 1.0:
        classification = "Excellent"
        note = f"FCF exceeds net income — high-quality earnings conversion"
    elif fcf_to_net_income_ratio >= min_ratio:
        classification = "Good"
        note = f"≥{min_ratio:.0%} conversion — solid FCF quality"
    elif fcf_to_net_income_ratio >= 0.5:
        classification = "Watch"
        note = f"50–70% conversion — investigate whether gap is structural or temporary"
    else:
        classification = "Concern"
        note = "<50% conversion — significant gap between earnings and cash; investigate"

    return ClassificationResult(
        metric_name="FCF Conversion (FCF/Net Income)",
        raw_value=fcf_to_net_income_ratio,
        classification=classification,
        guideline_note=note
    )


# ---------------------------------------------------------------------------
# Batch Classifier
# ---------------------------------------------------------------------------

def classify_all(
    roic: Optional[float] = None,
    debt_to_assets: Optional[float] = None,
    dividend_payout: Optional[float] = None,
    dividend_yield: Optional[float] = None,
    revenue_cagr_5yr: Optional[float] = None,
    fcf_conversion: Optional[float] = None,
    is_emerging: bool = False,
    is_financial_institution: bool = False,
) -> Dict[str, ClassificationResult]:
    """
    Classify all provided metrics in a single call.
    Returns a dict keyed by metric name.
    """
    results = {}

    if roic is not None:
        results["roic"] = classify_roic(roic, is_emerging=is_emerging)
    if debt_to_assets is not None:
        results["debt_to_assets"] = classify_debt_to_assets(
            debt_to_assets, is_financial_institution=is_financial_institution
        )
    if dividend_payout is not None:
        results["dividend_payout"] = classify_dividend_payout(dividend_payout)
    if dividend_yield is not None:
        results["dividend_yield"] = classify_dividend_yield(dividend_yield)
    if revenue_cagr_5yr is not None:
        results["revenue_cagr_5yr"] = classify_revenue_growth_cagr(revenue_cagr_5yr, period_years=5)
    if fcf_conversion is not None:
        results["fcf_conversion"] = classify_fcf_conversion(fcf_conversion)

    return results


# ---------------------------------------------------------------------------
# CLI / Smoke Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Thresholds Engine Smoke Test ===\n")

    # Example: Costco-like profile
    results = classify_all(
        roic=27.0,
        debt_to_assets=18.0,
        dividend_payout=28.0,
        dividend_yield=0.6,
        revenue_cagr_5yr=9.5,
        fcf_conversion=0.82,
        is_emerging=False,
    )

    for name, result in results.items():
        print(result)

    print("\n=== Emerging company, lower ROIC ===")
    r = classify_roic(8.5, is_emerging=True)
    print(r)

    print("\n=== Financial institution debt check ===")
    r = classify_debt_to_assets(85.0, is_financial_institution=True)
    print(r)

    print("\n=== High yield warning ===")
    r = classify_dividend_yield(7.5)
    print(r)
