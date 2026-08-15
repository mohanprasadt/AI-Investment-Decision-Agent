"""
Valuation Models — Phase 5
==========================
Data models for the Valuation Engine.

Architecture boundary:
  L1 — Raw inputs with full data provenance
  L2 — Valuation calculations (DCF, multiples, historical, peer)
  L3 — Investment interpretation (Phase 7 only — NOT produced here)

This module does NOT produce investment recommendations.
It produces fair-value ranges, accumulation zones, and margin-of-safety
assessments that Phase 7 will combine with business and financial quality.
"""

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CompanyType(Enum):
    INDUSTRIAL       = "Industrial"          # Standard operating company
    FINANCIAL        = "Financial"           # Banks, insurers — different metrics
    REIT             = "REIT"                # FFO/AFFO-based valuation
    HIGH_GROWTH      = "HighGrowth"          # Revenue CAGR > 15%; often negative FCF
    CYCLICAL         = "Cyclical"            # Commodity/macro-sensitive; use normalized earnings
    UTILITY          = "Utility"             # Regulated; stable FCF; yield-oriented
    NEGATIVE_FCF     = "NegativeFCF"         # Pre-profit or capex-heavy; DCF unreliable


class ValuationMethod(Enum):
    DCF_FCF          = "DCF_FCF"
    NORMALIZED_PE    = "NormalizedPE"
    EV_EBITDA        = "EV_EBITDA"
    PRICE_TO_FCF     = "PriceToFCF"
    HISTORICAL_PE    = "HistoricalPE"
    HISTORICAL_EV_EBITDA = "HistoricalEV_EBITDA"
    PEER_COMPARISON  = "PeerComparison"
    PRICE_TO_BOOK    = "PriceToBook"         # For financials
    FFO_MULTIPLE     = "FFOMultiple"         # For REITs
    REVENUE_MULTIPLE = "RevenueMultiple"     # For high-growth / negative earnings


class MethodApplicability(Enum):
    APPLICABLE              = "Applicable"
    APPLICABLE_WITH_CAVEATS = "ApplicableWithCaveats"
    NOT_APPLICABLE          = "NotApplicable"
    INSUFFICIENT_DATA       = "InsufficientData"


class MethodReliability(Enum):
    HIGH   = "High"
    MEDIUM = "Medium"
    LOW    = "Low"
    NA     = "NotApplicable"


class AccumulationZoneLabel(Enum):
    WAIT        = "WAIT"
    WATCH       = "WATCH"
    START_SMALL = "START_SMALL"
    ACCUMULATE  = "ACCUMULATE"


class ValuationConfidence(Enum):
    HIGH   = "High"
    MEDIUM = "Medium"
    LOW    = "Low"


class InputType(Enum):
    REPORTED   = "reported"    # From financial statements / filings
    CALCULATED = "calculated"  # Derived from reported data
    ASSUMED    = "assumed"     # Analyst / AI assumption


# ---------------------------------------------------------------------------
# Data provenance item
# ---------------------------------------------------------------------------

@dataclass
class InputItem:
    """
    A single valuation input with full provenance.
    Every material assumption in the valuation must be traceable.
    """
    name: str
    value: Optional[float]
    period: str = ""           # e.g. "FY2024", "TTM", "5yr avg"
    currency: str = ""         # "CAD", "USD", "INR"
    source: str = ""           # "Annual Report FY2024", "yfinance", "User assumption"
    retrieval_date: str = ""   # ISO date or "N/A"
    input_type: InputType = InputType.REPORTED
    confidence: ValuationConfidence = ValuationConfidence.MEDIUM
    notes: str = ""

    def is_available(self) -> bool:
        return self.value is not None

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["input_type"] = self.input_type.value
        d["confidence"] = self.confidence.value
        return d


# ---------------------------------------------------------------------------
# Peer data
# ---------------------------------------------------------------------------

@dataclass
class PeerData:
    """One comparable company for peer valuation."""
    ticker: str
    name: str
    pe_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    price_to_fcf: Optional[float] = None
    price_to_book: Optional[float] = None
    ffo_multiple: Optional[float] = None
    revenue_growth_pct: Optional[float] = None
    ebitda_margin_pct: Optional[float] = None
    roic_pct: Optional[float] = None
    source: str = ""
    similarity_note: str = ""    # Why this peer is (or isn't) comparable

    def to_dict(self) -> Dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Valuation inputs container
# ---------------------------------------------------------------------------

@dataclass
class ValuationInput:
    """
    All inputs required for the valuation engine, with full provenance.
    Caller is responsible for populating fields — partial inputs are allowed
    but will limit which methods are applicable.
    """
    # Identity
    ticker: str
    company_name: str
    company_type: CompanyType
    valuation_date: str                  # ISO date string

    # Currency
    currency: str                        # Local reporting currency
    fx_rate_to_cad: float = 1.0          # 1.0 for CAD companies
    fx_rate_date: str = ""

    # === Price / market data ===
    current_price: Optional[InputItem] = None        # Per-share price in local currency
    shares_outstanding: Optional[InputItem] = None   # Millions
    total_debt: Optional[InputItem] = None           # Interest-bearing debt, millions
    cash_and_equivalents: Optional[InputItem] = None # Millions

    # === Income statement (TTM or most recent annual) ===
    revenue: Optional[InputItem] = None              # Millions
    ebitda: Optional[InputItem] = None               # Millions
    ebit: Optional[InputItem] = None                 # Millions
    net_income: Optional[InputItem] = None           # Millions
    eps_ttm: Optional[InputItem] = None              # Per share
    book_value_per_share: Optional[InputItem] = None # For financials

    # === Cash flow ===
    fcf_ttm: Optional[InputItem] = None              # Millions
    fcf_normalized: Optional[InputItem] = None       # 3–5yr average FCF, millions

    # === REIT-specific ===
    ffo_per_share: Optional[InputItem] = None
    affo_per_share: Optional[InputItem] = None

    # === Historical series (for normalization and historical multiple comparison) ===
    # Dict: {"2019": value, "2020": value, ...}
    eps_history: Dict[str, float] = field(default_factory=dict)
    fcf_history: Dict[str, float] = field(default_factory=dict)
    revenue_history: Dict[str, float] = field(default_factory=dict)
    pe_history: Dict[str, float] = field(default_factory=dict)
    ev_ebitda_history: Dict[str, float] = field(default_factory=dict)
    price_to_fcf_history: Dict[str, float] = field(default_factory=dict)

    # === DCF explicit assumptions ===
    # If not provided, DCF engine will derive from available data
    dcf_base_fcf: Optional[InputItem] = None        # Starting FCF (millions)
    dcf_growth_rates: Optional[List[float]] = None  # Year-by-year %, e.g. [12,10,8,7,6,5,4,4,3,3]
    dcf_revenue_growth_rate: Optional[float] = None # Simplified single growth rate %
    dcf_fcf_margin_pct: Optional[float] = None      # FCF margin as % of revenue

    # === Context from prior phases ===
    moat_strength: str = "MODERATE"                 # From Phase 4: NONE/WEAK/MODERATE/STRONG/EXCEPTIONAL
    financial_quality_hint: str = "GOOD"            # From Phase 3: EXCELLENT/STRONG/GOOD/WATCH/CONCERN

    # === Peers ===
    peers: List[PeerData] = field(default_factory=list)

    # === Analyst estimates (clearly labeled as assumptions) ===
    analyst_eps_next_year: Optional[InputItem] = None
    analyst_revenue_next_year: Optional[InputItem] = None

    # --- Convenience properties ---

    def market_cap(self) -> Optional[float]:
        """Market cap in local currency (millions)."""
        if self.current_price and self.shares_outstanding:
            if self.current_price.value and self.shares_outstanding.value:
                return self.current_price.value * self.shares_outstanding.value
        return None

    def enterprise_value(self) -> Optional[float]:
        """EV in local currency (millions)."""
        mc = self.market_cap()
        if mc is None:
            return None
        debt = self.total_debt.value if self.total_debt else 0.0
        cash = self.cash_and_equivalents.value if self.cash_and_equivalents else 0.0
        return mc + (debt or 0.0) - (cash or 0.0)

    def has_positive_fcf(self) -> bool:
        if self.fcf_ttm and self.fcf_ttm.value is not None:
            return self.fcf_ttm.value > 0
        if self.fcf_normalized and self.fcf_normalized.value is not None:
            return self.fcf_normalized.value > 0
        return False

    def has_positive_earnings(self) -> bool:
        if self.eps_ttm and self.eps_ttm.value is not None:
            return self.eps_ttm.value > 0
        if self.net_income and self.net_income.value is not None:
            return self.net_income.value > 0
        return False

    def normalized_eps(self) -> Optional[float]:
        """3–5yr average EPS from history, or TTM if history unavailable."""
        if self.eps_history:
            values = sorted(self.eps_history.items())[-5:]  # last 5 years
            vals = [v for _, v in values if v is not None]
            if vals:
                return sum(vals) / len(vals)
        if self.eps_ttm and self.eps_ttm.value is not None:
            return self.eps_ttm.value
        return None

    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "company_type": self.company_type.value,
            "valuation_date": self.valuation_date,
            "currency": self.currency,
            "fx_rate_to_cad": self.fx_rate_to_cad,
            "moat_strength": self.moat_strength,
            "financial_quality_hint": self.financial_quality_hint,
            "market_cap_local": self.market_cap(),
            "has_positive_fcf": self.has_positive_fcf(),
            "has_positive_earnings": self.has_positive_earnings(),
            "peers_count": len(self.peers),
        }


# ---------------------------------------------------------------------------
# DCF result
# ---------------------------------------------------------------------------

@dataclass
class DCFResult:
    """Output of the DCF valuation engine."""
    # Per-share intrinsic value (bear/base/bull scenarios)
    bear_value: Optional[float] = None   # Conservative: low growth, high discount rate
    base_value: Optional[float] = None   # Expected: base assumptions
    bull_value: Optional[float] = None   # Optimistic: high growth, low discount rate

    # Scenario assumptions (for transparency)
    base_growth_rates: List[float] = field(default_factory=list)
    bear_growth_rates: List[float] = field(default_factory=list)
    bull_growth_rates: List[float] = field(default_factory=list)

    base_discount_rate: float = 9.0
    bear_discount_rate: float = 10.5
    bull_discount_rate: float = 7.5
    terminal_growth_rate: float = 3.0

    # Sensitivity table: {discount_rate_str: {terminal_growth_str: value}}
    sensitivity_table: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)

    # Terminal value diagnostics
    terminal_value_pct_of_base: Optional[float] = None  # % of base value from TV
    terminal_value_warning: bool = False                 # True if TV > 75% of total

    # Confidence and reliability
    reliability: MethodReliability = MethodReliability.MEDIUM
    reliability_note: str = ""
    key_assumptions: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        return self.base_value is not None and self.base_value > 0

    def range_width_pct(self) -> Optional[float]:
        """Width of the bear-to-bull range as % of base value."""
        if self.base_value and self.bear_value and self.bull_value:
            return ((self.bull_value - self.bear_value) / self.base_value) * 100
        return None

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["reliability"] = self.reliability.value
        d["is_valid"] = self.is_valid()
        return d


# ---------------------------------------------------------------------------
# Multiple valuation result
# ---------------------------------------------------------------------------

@dataclass
class MultipleValuationResult:
    """
    Output of a multiple-based valuation (P/E, EV/EBITDA, P/FCF, P/BV, FFO).
    Produces a low/mid/high implied value range based on multiple range.
    """
    method: ValuationMethod
    metric_used: str = ""               # "Normalized EPS", "EBITDA", "FCF", "FFO", etc.
    metric_value: Optional[float] = None  # The metric value used (per share or total)
    normalization_note: str = ""        # How metric was normalized (if applicable)

    multiple_low: Optional[float] = None   # Conservative multiple
    multiple_mid: Optional[float] = None   # Base multiple
    multiple_high: Optional[float] = None  # Optimistic multiple
    multiple_basis: str = ""               # "Historical 5yr range" / "Peer median" / "Analyst consensus"

    implied_value_low: Optional[float] = None    # Per share
    implied_value_mid: Optional[float] = None
    implied_value_high: Optional[float] = None

    reliability: MethodReliability = MethodReliability.MEDIUM
    reliability_note: str = ""
    caveats: List[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        return self.implied_value_mid is not None and self.implied_value_mid > 0

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["method"] = self.method.value
        d["reliability"] = self.reliability.value
        return d


# ---------------------------------------------------------------------------
# Historical multiples result
# ---------------------------------------------------------------------------

@dataclass
class HistoricalMultiplesResult:
    """
    Compares current valuation multiple against the company's own history.
    Not intrinsic value — contextual positioning only.
    """
    metric_name: str = ""              # "P/E", "EV/EBITDA", "P/FCF"
    current_multiple: Optional[float] = None
    historical_low: Optional[float] = None
    historical_median: Optional[float] = None
    historical_high: Optional[float] = None
    historical_years: int = 0          # How many years of history used

    # Percentile of current multiple in historical distribution (0-100%)
    current_percentile: Optional[float] = None

    # Implied per-share value if multiple reverts to median / low / high
    implied_at_median: Optional[float] = None
    implied_at_low: Optional[float] = None
    implied_at_high: Optional[float] = None

    interpretation: str = ""          # L2 note on what this positioning means
    reliability: MethodReliability = MethodReliability.MEDIUM
    reliability_note: str = ""
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["reliability"] = self.reliability.value
        return d


# ---------------------------------------------------------------------------
# Peer valuation result
# ---------------------------------------------------------------------------

@dataclass
class PeerValuationResult:
    """
    Relative valuation against comparable companies.
    Confidence is usually LOW unless peers are very directly comparable.
    """
    peers_used: List[PeerData] = field(default_factory=list)
    peers_excluded: List[str] = field(default_factory=list)  # tickers excluded + reason

    peer_median_pe: Optional[float] = None
    peer_median_ev_ebitda: Optional[float] = None
    peer_median_p_fcf: Optional[float] = None
    peer_median_p_book: Optional[float] = None

    implied_value_by_pe: Optional[float] = None
    implied_value_by_ev_ebitda: Optional[float] = None
    implied_value_by_p_fcf: Optional[float] = None

    premium_discount_to_peers_pct: Optional[float] = None  # +% = premium, -% = discount
    premium_justified_note: str = ""

    reliability: MethodReliability = MethodReliability.LOW
    reliability_note: str = ""
    applicability_note: str = ""
    caveats: List[str] = field(default_factory=list)

    def is_valid(self) -> bool:
        return len(self.peers_used) >= 2

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["reliability"] = self.reliability.value
        d["peers_used"] = [p.to_dict() for p in self.peers_used]
        return d


# ---------------------------------------------------------------------------
# Method applicability assessment
# ---------------------------------------------------------------------------

@dataclass
class MethodAssessment:
    """Records which valuation methods were evaluated and why."""
    method: ValuationMethod
    applicability: MethodApplicability
    reason: str = ""

    def to_dict(self) -> Dict:
        return {
            "method": self.method.value,
            "applicability": self.applicability.value,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Fair value range
# ---------------------------------------------------------------------------

@dataclass
class FairValueRange:
    """
    Synthesized fair value range across all applicable methods.

    bear / base / bull are per-share values in local currency.
    These are NOT buy/sell signals — they are intrinsic value estimates.
    """
    bear: Optional[float] = None
    base: Optional[float] = None
    bull: Optional[float] = None
    currency: str = ""

    primary_method: str = ""        # Which method anchors the base case
    secondary_methods: List[str] = field(default_factory=list)  # Contributing methods

    key_assumption_drivers: List[str] = field(default_factory=list)  # What moves the range
    convergence_note: str = ""      # Do methods agree / diverge?

    confidence: ValuationConfidence = ValuationConfidence.MEDIUM

    def width_pct(self) -> Optional[float]:
        """Width of range as % of base."""
        if self.base and self.bear and self.bull and self.base > 0:
            return ((self.bull - self.bear) / self.base) * 100
        return None

    def midpoint(self) -> Optional[float]:
        if self.bear and self.bull:
            return (self.bear + self.bull) / 2
        return self.base

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["confidence"] = self.confidence.value
        d["width_pct"] = self.width_pct()
        d["midpoint"] = self.midpoint()
        return d


# ---------------------------------------------------------------------------
# Accumulation zone
# ---------------------------------------------------------------------------

@dataclass
class AccumulationZone:
    """
    Price-based accumulation assessment.
    NOT a buy/sell recommendation — a decision-support signal.
    Phase 7 will combine this with business quality and portfolio context
    before any investment action is considered.
    """
    zone: AccumulationZoneLabel
    current_price: float
    current_price_currency: str

    fair_value_base: Optional[float]     # Reference point
    required_margin_of_safety_pct: float # How much MoS this investor requires
    actual_margin_of_safety_pct: Optional[float]  # MoS at current price vs base

    # Threshold prices for zone transitions
    accumulate_below: Optional[float] = None   # Price below which ACCUMULATE applies
    start_small_below: Optional[float] = None  # Price below which START_SMALL applies
    watch_below: Optional[float] = None        # Price below which WATCH applies

    zone_reasoning: str = ""
    caveat: str = ""   # Important context before acting on this zone

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["zone"] = self.zone.value
        return d


# ---------------------------------------------------------------------------
# Master ValuationAssessment
# ---------------------------------------------------------------------------

@dataclass
class ValuationAssessment:
    """
    Master container for Phase 5 valuation output.

    Architecture boundary: This produces L2 valuation outputs only.
    Phase 7 (Investment Decision Engine) will combine this with:
      - FinancialQualityAssessment (Phase 3)
      - BusinessResearchAssessment (Phase 4)
      - PortfolioAssessment (Phase 6)
    to produce the final investment conclusion.
    """
    ticker: str
    company_name: str
    valuation_date: str
    currency: str                               # Local reporting currency
    fx_rate_to_cad: float = 1.0
    fx_rate_date: str = ""

    # --- Method evaluations ---
    methods_evaluated: List[MethodAssessment] = field(default_factory=list)

    # --- Method results ---
    dcf_result: Optional[DCFResult] = None
    normalized_pe_result: Optional[MultipleValuationResult] = None
    ev_ebitda_result: Optional[MultipleValuationResult] = None
    price_to_fcf_result: Optional[MultipleValuationResult] = None
    historical_pe_result: Optional[HistoricalMultiplesResult] = None
    historical_ev_ebitda_result: Optional[HistoricalMultiplesResult] = None
    peer_valuation_result: Optional[PeerValuationResult] = None
    specialist_result: Optional[MultipleValuationResult] = None  # FFO, P/BV, Revenue

    # --- Synthesized output ---
    fair_value_range: Optional[FairValueRange] = None
    accumulation_zone: Optional[AccumulationZone] = None

    # --- Current price context ---
    current_price: Optional[float] = None
    margin_of_safety_at_current_price_pct: Optional[float] = None
    required_margin_of_safety_pct: Optional[float] = None

    # --- Qualitative context ---
    valuation_caveats: List[str] = field(default_factory=list)
    key_valuation_assumptions: List[str] = field(default_factory=list)
    data_provenance_notes: List[str] = field(default_factory=list)
    valuation_flags: List[str] = field(default_factory=list)  # Warnings / contradictions

    # --- Overall confidence ---
    overall_confidence: ValuationConfidence = ValuationConfidence.MEDIUM
    confidence_reasoning: str = ""

    # --- Phase 7 handoff note ---
    for_phase7_note: str = (
        "This is a valuation assessment only. Investment decision requires combining "
        "financial quality (Phase 3), business research (Phase 4), this valuation "
        "(Phase 5), and portfolio context (Phase 6)."
    )

    # -----------------------------------------------------------------------

    def applicable_methods(self) -> List[str]:
        return [
            m.method.value for m in self.methods_evaluated
            if m.applicability in (
                MethodApplicability.APPLICABLE,
                MethodApplicability.APPLICABLE_WITH_CAVEATS
            )
        ]

    def not_applicable_methods(self) -> List[str]:
        return [
            m.method.value for m in self.methods_evaluated
            if m.applicability == MethodApplicability.NOT_APPLICABLE
        ]

    def is_in_accumulation_zone(self) -> bool:
        if self.accumulation_zone:
            return self.accumulation_zone.zone in (
                AccumulationZoneLabel.ACCUMULATE,
                AccumulationZoneLabel.START_SMALL
            )
        return False

    def peer_transparency(self) -> Dict:
        """
        Structured peer-valuation transparency report (Phase 7.8).

        Explicitly distinguishes between:
          - PERFORMED: peer_valuation_result is present and has ≥ 2 peers
          - NOT_PERFORMED: no peer dataset was supplied

        When NOT_PERFORMED, surfaces any configured EV/EBITDA multiple so
        that downstream narrative layers cannot attribute the assumption to
        a specific peer without evidence.

        Design intent: prevent the LLM/reporting layer from implying that
        a specific company or peer group supports the multiple unless that
        evidence actually exists in structured input.
        """
        pvr = self.peer_valuation_result
        if pvr is not None and pvr.is_valid():
            return {
                "peer_valuation_status": "PERFORMED",
                "peers_used_count": len(pvr.peers_used),
                "peers_used": [p.ticker for p in pvr.peers_used],
                "peer_median_ev_ebitda": pvr.peer_median_ev_ebitda,
                "source": "Live peer comparison",
            }

        # NOT_PERFORMED — extract configured multiple if available
        ev_multiple_mid = None
        ev_multiple_basis = None
        if self.ev_ebitda_result is not None:
            ev_multiple_mid = self.ev_ebitda_result.multiple_mid
            ev_multiple_basis = self.ev_ebitda_result.multiple_basis or "Not recorded"

        return {
            "peer_valuation_status": "NOT_PERFORMED",
            "reason": "No peer dataset supplied.",
            "ev_ebitda_assumption": ev_multiple_mid,
            "ev_ebitda_assumption_basis": ev_multiple_basis,
            "source": (
                "Configured/manual assumption — NOT derived from live peer comparison. "
                "Do not attribute this multiple to a specific peer or peer group "
                "without independent evidence."
            ),
        }

    def summary_text(self) -> str:
        lines = [
            f"=== Valuation Assessment: {self.company_name} ({self.ticker}) ===",
            f"Date: {self.valuation_date} | Currency: {self.currency}",
        ]
        if self.current_price:
            lines.append(f"Current Price: {self.current_price:.2f} {self.currency}")

        if self.fair_value_range:
            fv = self.fair_value_range
            lines.append(
                f"Fair Value Range: {fv.bear:.2f}–{fv.bull:.2f} {self.currency} "
                f"(base: {fv.base:.2f}) | Confidence: {fv.confidence.value}"
            )
        if self.margin_of_safety_at_current_price_pct is not None:
            mos = self.margin_of_safety_at_current_price_pct
            sign = "+" if mos >= 0 else ""
            lines.append(f"Margin of Safety at Current Price: {sign}{mos:.1f}%")
        if self.required_margin_of_safety_pct is not None:
            lines.append(f"Required Margin of Safety: {self.required_margin_of_safety_pct:.0f}%")
        if self.accumulation_zone:
            az = self.accumulation_zone
            lines.append(f"Accumulation Zone: {az.zone.value}")
            if az.zone_reasoning:
                lines.append(f"  {az.zone_reasoning}")

        lines.append(f"\nMethods Applicable: {', '.join(self.applicable_methods()) or 'None'}")
        lines.append(f"Methods N/A: {', '.join(self.not_applicable_methods()) or 'None'}")

        if self.valuation_flags:
            lines.append("\nFlags:")
            for f_ in self.valuation_flags:
                lines.append(f"  ⚠ {f_}")

        if self.valuation_caveats:
            lines.append("\nKey Caveats:")
            for c in self.valuation_caveats[:3]:
                lines.append(f"  • {c}")

        lines.append(f"\n[{self.for_phase7_note}]")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "valuation_date": self.valuation_date,
            "currency": self.currency,
            "fx_rate_to_cad": self.fx_rate_to_cad,
            "current_price": self.current_price,
            "methods_evaluated": [m.to_dict() for m in self.methods_evaluated],
            "applicable_methods": self.applicable_methods(),
            "dcf_result": self.dcf_result.to_dict() if self.dcf_result else None,
            "normalized_pe_result": self.normalized_pe_result.to_dict() if self.normalized_pe_result else None,
            "ev_ebitda_result": self.ev_ebitda_result.to_dict() if self.ev_ebitda_result else None,
            "price_to_fcf_result": self.price_to_fcf_result.to_dict() if self.price_to_fcf_result else None,
            "historical_pe_result": self.historical_pe_result.to_dict() if self.historical_pe_result else None,
            "peer_valuation_result": self.peer_valuation_result.to_dict() if self.peer_valuation_result else None,
            "specialist_result": self.specialist_result.to_dict() if self.specialist_result else None,
            "fair_value_range": self.fair_value_range.to_dict() if self.fair_value_range else None,
            "accumulation_zone": self.accumulation_zone.to_dict() if self.accumulation_zone else None,
            "margin_of_safety_at_current_price_pct": self.margin_of_safety_at_current_price_pct,
            "required_margin_of_safety_pct": self.required_margin_of_safety_pct,
            "overall_confidence": self.overall_confidence.value,
            "confidence_reasoning": self.confidence_reasoning,
            "valuation_flags": self.valuation_flags,
            "valuation_caveats": self.valuation_caveats,
            "key_valuation_assumptions": self.key_valuation_assumptions,
            "data_provenance_notes": self.data_provenance_notes,
            # Peer-data transparency (Phase 7.8)
            "peer_transparency": self.peer_transparency(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path) -> None:
        from pathlib import Path
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")
