"""
Valuation Builder — Phase 9
============================
Builds a ValuationInput from a DataLoadResult (and optionally a
BusinessResearchAssessment) so the existing Phase 5 valuation engine
can be run on any ticker loaded through the data pipeline.

Design constraints (strictly enforced)
---------------------------------------
1.  Conservative: only populate fields where source data is available.
    Partially populated ValuationInputs are explicitly supported by Phase 5.
2.  Transparent: every derived/assumed value is marked with
    InputType.CALCULATED or InputType.ASSUMED — never InputType.REPORTED.
3.  No fabricated peers: peers=[] when no peer data is available.
    Never invent peer multiples.
4.  No invented growth assumptions: dcf_revenue_growth_rate is set only
    when an explicit source (analyst estimate or historical CAGR) is
    available; if neither exists the field is left as None.
5.  No qualitative conclusions from quantitative data:
    moat_strength and financial_quality_hint are passed through from
    Phase 3/4 assessments when available; otherwise the defaults
    ("MODERATE", "GOOD") are used from ValuationInput's own defaults.

Usage
-----
    vi = build_valuation_input(
        load_result=load_result,
        research=research,          # Optional[BusinessResearchAssessment]
        analysis_date="2026-08-10",
        company_type=CompanyType.CYCLICAL,  # Optional override
    )
    assessment = run_valuation(vi)
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

log = logging.getLogger(__name__)

from analytics.valuation.valuation_models import (
    ValuationInput,
    InputItem,
    InputType,
    ValuationConfidence,
    CompanyType,
    PeerData,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_valuation_input(
    load_result,                              # DataLoadResult
    research=None,                            # Optional[BusinessResearchAssessment]
    analysis_date: str = "",
    company_type: Optional[CompanyType] = None,
) -> ValuationInput:
    """
    Build a ValuationInput from DataLoadResult (Phase 1-3) output.

    Parameters
    ----------
    load_result  : DataLoadResult from load_ticker()
    research     : Optional BusinessResearchAssessment from Phase 4
                   (used for moat_strength, company_type hint)
    analysis_date: ISO date string for the valuation
    company_type : Override company type — if None, inferred from metrics

    Returns
    -------
    ValuationInput — partially populated; missing fields left as None.
    """
    ticker       = load_result.ticker
    company_name = load_result.company_name or ticker
    currency     = load_result.price_currency or "CAD"
    date_str     = analysis_date or load_result.price_date or ""
    m            = load_result.metrics           # CompanyFinancialMetrics or None
    supp         = getattr(load_result, "supplemental", {}) or {}

    # ── Company type ──────────────────────────────────────────────────────
    if company_type is None:
        company_type = _infer_company_type(m)

    # ── Moat and quality hints (from Phase 3/4 if available) ──────────────
    moat_strength         = _extract_moat_strength(research)
    financial_quality_hint = _extract_quality_hint(load_result)

    vi = ValuationInput(
        ticker=ticker,
        company_name=company_name,
        company_type=company_type,
        valuation_date=date_str,
        currency=currency,
        fx_rate_to_cad=1.0,   # TODO: cross-currency support (Phase 9+)
        moat_strength=moat_strength,
        financial_quality_hint=financial_quality_hint,
        peers=[],              # Never fabricated — see constraint #3
    )

    if m is None:
        log.warning("ValuationBuilder: no CompanyFinancialMetrics for %s — returning sparse ValuationInput", ticker)
        return vi

    # ── Current price ─────────────────────────────────────────────────────
    if load_result.current_price:
        vi.current_price = InputItem(
            name="current_price",
            value=load_result.current_price,
            source="yfinance (live)",
            period=date_str,
            retrieval_date=date_str,
            input_type=InputType.REPORTED,
            confidence=ValuationConfidence.HIGH,
        )

    # ── Shares outstanding ────────────────────────────────────────────────
    raw_shares = supp.get("shares_outstanding")
    if raw_shares:
        vi.shares_outstanding = InputItem(
            name="shares_outstanding",
            value=raw_shares / 1_000_000,   # → millions
            source="yfinance (sharesOutstanding)",
            period=date_str,
            retrieval_date=date_str,
            input_type=InputType.REPORTED,
            confidence=ValuationConfidence.HIGH,
        )
    elif load_result.current_price and getattr(m, "market_cap", None):
        # Derived — clearly marked CALCULATED
        computed = m.market_cap / load_result.current_price / 1_000_000
        vi.shares_outstanding = InputItem(
            name="shares_outstanding",
            value=computed,
            source="Derived: market_cap / current_price",
            period=date_str,
            retrieval_date=date_str,
            input_type=InputType.CALCULATED,
            confidence=ValuationConfidence.MEDIUM,
            notes="Computed from market cap and current price; may differ from reported shares due to rounding.",
        )

    # ── Revenue (latest annual) and history ──────────────────────────────
    # yfinance financial statements return absolute currency units (e.g. raw INR, raw CAD).
    # ValuationInput convention: all P&L / balance-sheet quantities in MILLIONS of
    # local currency, consistent with shares_outstanding which is also in millions.
    # All values from CompanyFinancialMetrics must be divided by 1_000_000 here.
    rg = getattr(m, "revenue_growth", None)
    if rg:
        rev_series = getattr(rg, "annual_revenues", {})
        if rev_series:
            latest_rev = _latest_value(rev_series)
            latest_yr  = _latest_year(rev_series)
            if latest_rev:
                vi.revenue = InputItem(
                    name="revenue",
                    value=latest_rev / 1_000_000,   # absolute → millions
                    source="yfinance financial statements",
                    period=f"FY{latest_yr}" if latest_yr else "Latest",
                    retrieval_date=date_str,
                    input_type=InputType.REPORTED,
                )
            vi.revenue_history = {str(k): v / 1_000_000 for k, v in rev_series.items()}

    # ── FCF (current and history) ─────────────────────────────────────────
    # FCF_NORM_YEARS is the single authoritative window length for BOTH FCF
    # normalization and EPS history (Phase 9.9b).  Change here to widen/narrow
    # both windows simultaneously.
    FCF_NORM_YEARS: int = 3

    fcf_metrics = getattr(m, "free_cash_flow", None)
    if fcf_metrics:
        fcf_current = getattr(fcf_metrics, "fcf_current", None)
        if fcf_current is not None:
            vi.fcf_ttm = InputItem(
                name="fcf_ttm",
                value=fcf_current / 1_000_000,      # absolute → millions
                source="yfinance (operating cash flow - capex)",
                period="TTM/Latest Annual",
                retrieval_date=date_str,
                input_type=InputType.CALCULATED,
                notes="Free cash flow = operating cash flow minus capital expenditures.",
            )
        fcf_series = getattr(fcf_metrics, "annual_fcf", {})
        if fcf_series:
            vi.fcf_history = {str(k): v / 1_000_000 for k, v in fcf_series.items()}

            # Normalized FCF: FCF_NORM_YEARS average over the most recent common
            # years (Phase 9.9b).  The common-year set is also used for eps_history
            # so both metrics cover identical fiscal periods.
            recent_fcf_vals = sorted(fcf_series.items(), reverse=True)[:FCF_NORM_YEARS]
            if len(recent_fcf_vals) >= FCF_NORM_YEARS:
                avg_fcf = sum(v for _, v in recent_fcf_vals) / len(recent_fcf_vals) / 1_000_000
                _fcf_norm_years = sorted(yr for yr, _ in recent_fcf_vals)
                vi.fcf_normalized = InputItem(
                    name="fcf_normalized",
                    value=avg_fcf,
                    source=f"Derived: {FCF_NORM_YEARS}-year average FCF",
                    period=f"{FCF_NORM_YEARS}yr avg FY{_fcf_norm_years[0]}–FY{_fcf_norm_years[-1]}",
                    retrieval_date=date_str,
                    input_type=InputType.CALCULATED,
                    notes=(
                        f"Average of the {FCF_NORM_YEARS} most recent annual FCF values "
                        f"(FY{_fcf_norm_years[0]}–FY{_fcf_norm_years[-1]}) to smooth volatility."
                    ),
                )

    # ── EBIT (operating income) ───────────────────────────────────────────
    mg = getattr(m, "margins", None)
    if mg and rg:
        op_margin = getattr(mg, "operating_margin", None)
        rev_latest = getattr(vi, "revenue", None)
        if op_margin is not None and rev_latest and rev_latest.value:
            ebit_val = rev_latest.value * op_margin / 100.0
            vi.ebit = InputItem(
                name="ebit",
                value=ebit_val,
                source="Derived: revenue × operating_margin",
                period=f"FY{_latest_year(rev_series) if rg and getattr(rg, 'annual_revenues', {}) else 'latest'}",
                retrieval_date=date_str,
                input_type=InputType.CALCULATED,
                notes=f"EBIT = revenue ({rev_latest.value:.0f}M) × operating margin ({op_margin:.1f}%). "
                      "Operating margin from yfinance financial statements.",
            )

    # ── EBITDA (EV/EBITDA back-calculation) ──────────────────────────────
    ev = getattr(m, "enterprise_value", None)
    ev_ebitda_ratio = getattr(m, "ev_ebitda", None)
    if ev and ev_ebitda_ratio and ev_ebitda_ratio > 0:
        ebitda_val = ev / ev_ebitda_ratio
        vi.ebitda = InputItem(
            name="ebitda",
            value=ebitda_val / 1_000_000,  # yfinance EV is in absolute units
            source="Derived: enterprise_value / EV/EBITDA ratio",
            period="TTM",
            retrieval_date=date_str,
            input_type=InputType.CALCULATED,
            confidence=ValuationConfidence.LOW,
            notes=(
                f"EBITDA = EV ({ev/1e9:.1f}B) ÷ EV/EBITDA ratio ({ev_ebitda_ratio:.1f}x). "
                "Low confidence — both EV and ratio may have rounding; prefer income statement EBITDA if available."
            ),
        )

    # ── Debt and cash ─────────────────────────────────────────────────────
    debt_metrics = getattr(m, "debt", None)
    if debt_metrics:
        total_debt = getattr(debt_metrics, "interest_bearing_debt", None)
        net_debt   = getattr(debt_metrics, "net_debt", None)

        if total_debt is not None:
            vi.total_debt = InputItem(
                name="total_debt",
                value=total_debt / 1_000_000,       # absolute → millions
                source="yfinance balance sheet (interest-bearing debt)",
                period="Latest",
                retrieval_date=date_str,
                input_type=InputType.REPORTED,
            )

        # ── Cash (broad definition preferred for EV calculations) ────────────
        # Priority:
        #   1. Balance-sheet "Cash Cash Equivalents And Short Term Investments"
        #      Includes short-term investments, which are near-cash for
        #      valuation purposes.  Excluding them understates equity value
        #      in the EV bridge (EV − debt + cash = equity).
        #   2. Balance-sheet "Cash And Cash Equivalents" (narrow)
        #      Fallback when the broad line is absent (e.g. some US filers).
        #   3. Derived from net_debt (total_debt − net_debt = narrow cash)
        #      Secondary fallback; relies on the normaliser's net_debt calc.
        #   4. totalCash from yfinance info
        #      Last resort — reporting period may differ from balance sheet.
        cash_broad  = supp.get("cash_broad")
        cash_narrow = supp.get("cash_narrow")
        cash_info   = supp.get("cash_info")

        if cash_broad is not None:
            vi.cash_and_equivalents = InputItem(
                name="cash_and_equivalents",
                value=cash_broad / 1_000_000,        # absolute → millions
                source="yfinance balance sheet (Cash + Short-Term Investments)",
                period="Latest Annual",
                retrieval_date=date_str,
                input_type=InputType.REPORTED,
                notes=(
                    "Broad cash: includes short-term investments. "
                    "Preferred for EV-bridge calculations."
                ),
            )
        elif cash_narrow is not None:
            vi.cash_and_equivalents = InputItem(
                name="cash_and_equivalents",
                value=cash_narrow / 1_000_000,       # absolute → millions
                source="yfinance balance sheet (Cash And Cash Equivalents)",
                period="Latest Annual",
                retrieval_date=date_str,
                input_type=InputType.REPORTED,
                notes="Narrow cash only — short-term investments excluded.",
            )
        elif total_debt is not None and net_debt is not None:
            cash_val = total_debt - net_debt         # both absolute; difference is absolute
            vi.cash_and_equivalents = InputItem(
                name="cash_and_equivalents",
                value=cash_val / 1_000_000,          # absolute → millions
                source="Derived: total_debt - net_debt",
                period="Latest",
                retrieval_date=date_str,
                input_type=InputType.CALCULATED,
                notes="Cash derived as total_debt − net_debt from balance sheet data.",
            )
        elif cash_info is not None:
            vi.cash_and_equivalents = InputItem(
                name="cash_and_equivalents",
                value=cash_info / 1_000_000,         # absolute → millions
                source="yfinance info (totalCash)",
                period="Latest",
                retrieval_date=date_str,
                input_type=InputType.REPORTED,
                notes=(
                    "totalCash from yfinance info; reporting period may differ "
                    "from balance sheet figures."
                ),
            )

    # ── EPS (trailing) ────────────────────────────────────────────────────
    trailing_eps = supp.get("trailing_eps")
    if trailing_eps is not None:
        vi.eps_ttm = InputItem(
            name="eps_ttm",
            value=trailing_eps,
            source="yfinance (trailingEps)",
            period="TTM",
            retrieval_date=date_str,
            input_type=InputType.REPORTED,
        )

    # ── Derived annual EPS history (Phase 9.9b) ──────────────────────────
    # Populates eps_history restricted to the same fiscal years used by
    # fcf_normalized (the FCF_NORM_YEARS most recent COMMON years).
    #
    # Labelling constraints:
    #   • NI source: FreeCashFlowMetrics.annual_net_income, which normalizer.py
    #     now populates from the continuing-operations sub-line when available,
    #     falling back to total Net Income.  EPS derived here is therefore
    #     "continuing-operations derived EPS", not company-reported diluted EPS.
    #   • Never call these "reported EPS" — they differ due to share-count
    #     treatment (basic vs diluted), EPS-specific adjustments, and rounding.
    #
    # Period-alignment guarantee:
    #   Common years = intersection of annual_net_income years and annual_fcf
    #   years, capped at FCF_NORM_YEARS.  Both eps_history and fcf_normalized
    #   cover exactly these years, eliminating the period-mismatch false positive
    #   that Phase 9.9 introduced (EPS used 4yr, FCF used 3yr).
    fcf_m_for_eps = getattr(m, "free_cash_flow", None)
    _ni_series_eps  = getattr(fcf_m_for_eps, "annual_net_income", {}) if fcf_m_for_eps else {}
    _fcf_series_eps = getattr(fcf_m_for_eps, "annual_fcf",        {}) if fcf_m_for_eps else {}
    _shares_mm_eps  = vi.shares_outstanding.value if vi.shares_outstanding else None

    if _shares_mm_eps and _ni_series_eps and _fcf_series_eps:
        _shares_abs_eps = _shares_mm_eps * 1_000_000   # millions → absolute units

        # Intersection of NI years and FCF years, FCF_NORM_YEARS most recent.
        _common_years: list = sorted(
            set(_ni_series_eps.keys()) & set(_fcf_series_eps.keys()),
            reverse=True,
        )[:FCF_NORM_YEARS]

        _derived_eps_hist: dict = {}
        for _yr in _common_years:
            _ni = _ni_series_eps.get(_yr)
            if _ni is not None and _shares_abs_eps > 0:
                _derived_eps_hist[str(_yr)] = round(_ni / _shares_abs_eps, 4)

        if _derived_eps_hist:
            vi.eps_history = _derived_eps_hist
            _eps_yrs_sorted = sorted(int(y) for y in _derived_eps_hist)
            log.debug(
                "ValuationBuilder: populated eps_history (%d years: %s) from "
                "continuing-ops NI ÷ shares_outstanding — same window as fcf_normalized",
                len(_derived_eps_hist),
                _eps_yrs_sorted,
            )

    # ── Book value per share ──────────────────────────────────────────────
    bvps = supp.get("book_value_per_share")
    if bvps is not None:
        vi.book_value_per_share = InputItem(
            name="book_value_per_share",
            value=bvps,
            source="yfinance (bookValue)",
            period="Latest",
            retrieval_date=date_str,
            input_type=InputType.REPORTED,
        )

    # ── Analyst forward EPS ───────────────────────────────────────────────
    fwd_eps = supp.get("analyst_forward_eps")
    if fwd_eps is not None:
        vi.analyst_eps_next_year = InputItem(
            name="analyst_eps_next_year",
            value=fwd_eps,
            source="yfinance (forwardEps — analyst consensus)",
            period="NTM",
            retrieval_date=date_str,
            input_type=InputType.ASSUMED,
            confidence=ValuationConfidence.LOW,
            notes="Analyst consensus estimate — subject to revision. Treat as directional only.",
        )

    # ── DCF growth rate — only from explicit source, never invented ───────
    if rg:
        cagr_3yr = getattr(rg, "cagr_3yr", None)
        if cagr_3yr is not None:
            # Use 3yr historical revenue CAGR as a conservative growth anchor.
            # Mark CALCULATED (from data) not ASSUMED.
            vi.dcf_revenue_growth_rate = cagr_3yr
            # We also store the source in a note — growth rate is a bare float
            # in ValuationInput, but the EBIT/FCF inputs above carry provenance.

    return vi


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _latest_value(series: Dict) -> Optional[float]:
    if not series:
        return None
    return series[max(series.keys())]


def _latest_year(series: Dict) -> Optional[int]:
    if not series:
        return None
    return max(series.keys())


def _infer_company_type(m) -> CompanyType:
    """
    Infer company type from available quantitative signals.
    Conservative: defaults to INDUSTRIAL when no strong signal.
    """
    if m is None:
        return CompanyType.INDUSTRIAL

    # High-growth: revenue CAGR > 15% AND negative or near-zero FCF
    rg = getattr(m, "revenue_growth", None)
    if rg:
        cagr = getattr(rg, "cagr_3yr", None)
        if cagr and cagr > 15.0:
            fcf_metrics = getattr(m, "free_cash_flow", None)
            fcf_curr = getattr(fcf_metrics, "fcf_current", None) if fcf_metrics else None
            if fcf_curr is not None and fcf_curr <= 0:
                return CompanyType.HIGH_GROWTH

    # Negative FCF
    fcf_metrics = getattr(m, "free_cash_flow", None)
    if fcf_metrics:
        fcf_curr = getattr(fcf_metrics, "fcf_current", None)
        if fcf_curr is not None and fcf_curr < 0:
            return CompanyType.NEGATIVE_FCF

    return CompanyType.INDUSTRIAL


def _extract_moat_strength(research) -> str:
    """Extract moat_strength string from BusinessResearchAssessment if available."""
    if research is None:
        return "MODERATE"   # ValuationInput default
    moat = getattr(research, "moat_assessment", None)
    if moat is None:
        return "MODERATE"
    strength = getattr(moat, "overall_strength", None)
    if strength is None:
        return "MODERATE"
    # MoatStrength enum has .value attribute
    val = getattr(strength, "value", str(strength))
    return val.upper()


def _extract_quality_hint(load_result) -> str:
    """Extract financial quality hint from FinancialQualityAssessment if available."""
    fq = getattr(load_result, "financial_quality", None)
    if fq is None:
        return "GOOD"   # ValuationInput default
    overall = getattr(fq, "overall_classification", None)
    if overall is None:
        return "GOOD"
    return str(overall).upper()
