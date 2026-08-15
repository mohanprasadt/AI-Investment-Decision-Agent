"""
DataLoader — Phase 8.1
======================
Thin adapter: yfinance fetch → CompanyFinancialMetrics → FinancialQualityAssessment.

This is the ONLY entry point for live market data in the agent layer.

What it does:
  1. Calls fetcher.fetch_ticker() to pull price + financials from yfinance
  2. Calls normalizer.normalize() to map raw data → CompanyFinancialMetrics
  3. Calls assess_financial_quality() to produce FinancialQualityAssessment
  4. Returns a DataLoadResult containing all three plus any failure reason

What it does NOT do (by design — requirement 5):
  - It does NOT generate or infer business research (Phase 4)
  - It does NOT generate or infer valuation assumptions (Phase 5)
  - It does NOT fabricate moat, management, growth, or risk assessments
  - It does NOT invent peer data or EV/EBITDA multiples

When data is unavailable:
  DataLoadResult.cannot_complete_reason is set to a non-empty string.
  The caller MUST check this field before passing results to the pipeline.
  The pipeline with research=None will produce WAIT_INSUFFICIENT_EVIDENCE (Gate 1
  forces this when no BusinessResearchAssessment is provided — not an action).

Testability:
  _fetch_fn and _normalize_fn are injectable so tests can run without yfinance
  or network access. The default values wire up the real fetcher and normalizer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable, Dict, Any

log = logging.getLogger(__name__)

# Sentinel string returned as cannot_complete_reason when fetch fails
CANNOT_COMPLETE = "CANNOT_COMPLETE_LIVE_ANALYSIS"


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class DataLoadResult:
    """
    Output of load_ticker().

    Check cannot_complete_reason FIRST.  If it is non-empty, metrics /
    financial_quality may be partial or None — do not pass them to the pipeline.
    """
    ticker: str
    company_name: str = ""
    current_price: Optional[float] = None
    price_currency: str = ""
    price_date: str = ""

    # Phase 2 output
    metrics: Optional[object] = None           # CompanyFinancialMetrics

    # Phase 3 output
    financial_quality: Optional[object] = None  # FinancialQualityAssessment

    # Freshness (Phase 7.5)
    freshness: Optional[object] = None          # DataFreshnessAssessment

    # Data completeness bookkeeping
    data_completeness_pct: float = 0.0
    data_quality_notes: list = field(default_factory=list)

    # Supplemental raw_info fields not in CompanyFinancialMetrics.
    # Phase 9: ValuationBuilder reads these to populate ValuationInput
    # without needing direct access to raw yfinance dicts.
    # Keys: shares_outstanding (int), trailing_eps (float),
    #       book_value_per_share (float), analyst_forward_eps (float)
    supplemental: dict = field(default_factory=dict)

    # Set to non-empty string when fetch failed completely
    cannot_complete_reason: str = ""

    @property
    def ok(self) -> bool:
        """True when data was successfully loaded and pipeline can proceed."""
        return not self.cannot_complete_reason


# ---------------------------------------------------------------------------
# Default fetch / normalize callables (real yfinance path)
# ---------------------------------------------------------------------------

def _latest_bs(balance_sheet: Dict[str, Any], field: str) -> Optional[float]:
    """
    Return the most recent annual value for a balance sheet field, or None.

    ``balance_sheet`` is the raw yfinance balance_sheet dict keyed by field
    name, where each value is itself a dict of {year_str: float}.
    """
    series = balance_sheet.get(field)
    if not series:
        return None
    try:
        latest_key = max(series.keys())
        return series[latest_key]
    except (ValueError, TypeError):
        return None


def _default_fetch(ticker: str) -> Dict[str, Any]:
    """Fetch via yfinance (requires network). Returns dict from fetch_ticker()."""
    try:
        from data.ingestion.fetcher import fetch_ticker  # type: ignore
        return fetch_ticker(ticker)
    except ImportError as e:
        raise RuntimeError(
            f"yfinance or data.ingestion.fetcher not available: {e}. "
            "Install yfinance: pip install yfinance"
        ) from e


def _default_normalize(ticker: str, raw: Dict[str, Any]):
    """Map raw yfinance dict → CompanyFinancialMetrics."""
    from data.ingestion.normalizer import normalize  # type: ignore
    return normalize(
        ticker=ticker,
        raw_info=raw.get("info", {}),
        raw_financials=raw.get("financials", {}),
        is_etf=raw.get("is_etf", False),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_ticker(
    ticker: str,
    analysis_date: str = "",
    *,
    _fetch_fn: Callable[[str], Dict[str, Any]] = _default_fetch,
    _normalize_fn: Callable = _default_normalize,
) -> DataLoadResult:
    """
    Load financial data for a single ticker through the existing pipeline.

    Parameters
    ----------
    ticker        : stock ticker symbol, e.g. exchange-listed equity ticker
    analysis_date : ISO date string for freshness tracking (defaults to today)
    _fetch_fn     : Injectable fetch function (default: yfinance via fetcher.py)
    _normalize_fn : Injectable normalize function (default: normalizer.py)

    Returns
    -------
    DataLoadResult — always returns, never raises.
    Check .ok / .cannot_complete_reason before using.
    """
    if not analysis_date:
        analysis_date = datetime.utcnow().strftime("%Y-%m-%d")

    result = DataLoadResult(ticker=ticker)

    # ── Step 1: Fetch raw data ──────────────────────────────────────────────
    try:
        raw = _fetch_fn(ticker)
    except Exception as exc:
        msg = f"yfinance fetch failed for {ticker}: {exc}"
        log.warning(msg)
        result.cannot_complete_reason = (
            f"{CANNOT_COMPLETE}: {msg}. "
            "Ensure yfinance is installed (pip install yfinance) and network is available."
        )
        return result

    # ── Step 2: Check fetch success ─────────────────────────────────────────
    info = raw.get("info", {})
    fetch_ok = info.get("_fetch_success", False)
    company_name = info.get("longName") or info.get("shortName") or ""

    if not fetch_ok:
        err = info.get("_fetch_error") or "unknown fetch error"
        result.cannot_complete_reason = (
            f"{CANNOT_COMPLETE}: yfinance returned no data for '{ticker}'. "
            f"Reason: {err}. "
            "Verify the ticker symbol is correct and the network is available."
        )
        return result

    # Treat a ticker with no company name and no price as a failed lookup
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    if not company_name and not current_price:
        result.cannot_complete_reason = (
            f"{CANNOT_COMPLETE}: '{ticker}' returned empty data from yfinance. "
            "The ticker may be invalid, delisted, or not supported by yfinance."
        )
        return result

    result.company_name = company_name or ticker
    result.current_price = current_price
    result.price_currency = info.get("currency", "")
    result.price_date = analysis_date   # yfinance current price is as-of fetch date

    # ── Step 3: Normalize → CompanyFinancialMetrics ─────────────────────────
    try:
        metrics = _normalize_fn(ticker, raw)
    except Exception as exc:
        msg = f"Normalization failed for {ticker}: {exc}"
        log.warning(msg)
        result.cannot_complete_reason = f"{CANNOT_COMPLETE}: {msg}"
        return result

    result.metrics = metrics
    result.data_completeness_pct = getattr(metrics, "data_completeness_pct", 0.0)
    result.data_quality_notes = getattr(metrics, "data_quality_notes", [])

    # ── Step 3b: Supplemental raw_info fields (Phase 9) ────────────────────
    # Capture fields not stored in CompanyFinancialMetrics so ValuationBuilder
    # can use them without needing direct access to raw yfinance dicts.
    #
    # Cash fields — exposed in priority order so ValuationBuilder can pick the
    # most appropriate definition (broad preferred for EV calculations):
    #   cash_broad  : Cash + Short-Term Investments (balance sheet)
    #   cash_narrow : Cash And Cash Equivalents only (balance sheet)
    #   cash_info   : totalCash from yfinance info (final fallback; may differ
    #                 in period or definition from the balance sheet figures)
    _bs = raw.get("financials", {}).get("balance_sheet", {})
    result.supplemental = {
        "shares_outstanding": info.get("sharesOutstanding"),
        "trailing_eps":       info.get("trailingEps"),
        "book_value_per_share": info.get("bookValue"),
        "analyst_forward_eps": info.get("forwardEps"),
        # Cash (absolute local currency units, pre-scaling)
        "cash_broad":  _latest_bs(
            _bs, "Cash Cash Equivalents And Short Term Investments"
        ),
        "cash_narrow": _latest_bs(_bs, "Cash And Cash Equivalents"),
        "cash_info":   info.get("totalCash"),
    }

    # ── Step 4: Financial Quality Assessment (Phase 3) ─────────────────────
    try:
        from analytics.financial_quality.quality_engine import assess_financial_quality
        fq = assess_financial_quality(metrics)
        result.financial_quality = fq
    except Exception as exc:
        msg = f"Financial quality assessment failed for {ticker}: {exc}"
        log.warning(msg)
        # Not fatal — FQ can be None and the pipeline degrades gracefully
        result.data_quality_notes.append(f"[FQ error] {msg}")

    # ── Step 5: Freshness Assessment (Phase 7.5) ───────────────────────────
    try:
        from analytics.data_freshness import build_freshness_assessment
        # Phase 8.3 fix: derive financial_statements_date from the latest revenue year
        # in annual_revenues (e.g. 2024 → "2024-12-31") rather than using data_as_of_date,
        # which is the fetch timestamp and not the reporting period.
        fin_date = ""
        rev_series = getattr(getattr(metrics, "revenue_growth", None), "annual_revenues", {})
        if rev_series:
            latest_yr = max(rev_series.keys())
            fin_date = f"{latest_yr}-12-31"
        # Fallback: use data_as_of_date only when no revenue series is available
        if not fin_date:
            fin_date = getattr(metrics, "data_as_of_date", "") or ""

        result.freshness = build_freshness_assessment(
            analysis_date=analysis_date,
            price_date=analysis_date,    # yfinance price is current as of fetch
            financial_statements_date=fin_date,
        )
    except Exception as exc:
        log.warning(f"Freshness assessment failed for {ticker}: {exc}")

    return result


# ---------------------------------------------------------------------------
# Convenience: describe what the loader found (for CLI output)
# ---------------------------------------------------------------------------

def describe_load_result(r: DataLoadResult) -> str:
    """Human-readable summary of what data was loaded."""
    if not r.ok:
        return r.cannot_complete_reason

    lines = [
        f"Live data loaded: {r.company_name} ({r.ticker})",
        f"  Price:           {r.current_price} {r.price_currency}  (as of {r.price_date})",
        f"  Data completeness: {r.data_completeness_pct:.0f}%",
    ]
    if r.data_quality_notes:
        lines.append(f"  Notes: {'; '.join(r.data_quality_notes[:3])}")
    lines += [
        "",
        "  ⚠  Business research (Phase 4) and valuation (Phase 5) are not available.",
        "     These require human analysis and cannot be automated.",
        "     The decision pipeline will produce WAIT_INSUFFICIENT_EVIDENCE.",
        "     No investment action will be generated.",
    ]
    return "\n".join(lines)
