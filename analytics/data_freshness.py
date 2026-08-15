"""
Data Freshness — Phase 7.5
===========================
Tracks how current the inputs to an investment analysis are.

Freshness affects confidence but does NOT flip the investment conclusion.
Stale data means: "conclusion is constrained by stale inputs" — not "company
is unattractive."

Thresholds (configurable via FRESHNESS_THRESHOLDS):
  CURRENT  — data is sufficiently recent for the intended analysis
  AGING    — data is older but may still be usable with a warning
  STALE    — data is too old to support a high-confidence current decision

Default thresholds (in calendar days):
  Price:               CURRENT < 3,  AGING < 30,  else STALE
  Financial statements:CURRENT < 180, AGING < 365, else STALE
  Research:            CURRENT < 90,  AGING < 180, else STALE
  Valuation inputs:    follows financial statements freshness
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FreshnessStatus(Enum):
    CURRENT = "CURRENT"   # Sufficiently recent
    AGING   = "AGING"     # Older but usable with caveat
    STALE   = "STALE"     # Too old for high-confidence conclusion
    UNKNOWN = "UNKNOWN"   # No date metadata available


# ---------------------------------------------------------------------------
# Configurable thresholds
# ---------------------------------------------------------------------------

@dataclass
class FreshnessThresholds:
    """
    Days thresholds for each data category.
    current_days: age <= this → CURRENT
    aging_days:   age <= this → AGING  (else STALE)
    """
    current_days: int
    aging_days: int

    def classify(self, data_date: Optional[date], reference_date: Optional[date] = None) -> FreshnessStatus:
        if data_date is None:
            return FreshnessStatus.UNKNOWN
        ref = reference_date or date.today()
        age_days = (ref - data_date).days
        if age_days <= self.current_days:
            return FreshnessStatus.CURRENT
        elif age_days <= self.aging_days:
            return FreshnessStatus.AGING
        else:
            return FreshnessStatus.STALE


# Default thresholds by data category
FRESHNESS_THRESHOLDS: Dict[str, FreshnessThresholds] = {
    "price":                FreshnessThresholds(current_days=3,   aging_days=30),
    "financial_statements": FreshnessThresholds(current_days=180, aging_days=365),
    "earnings":             FreshnessThresholds(current_days=90,  aging_days=180),
    "research":             FreshnessThresholds(current_days=90,  aging_days=180),
    "valuation_inputs":     FreshnessThresholds(current_days=180, aging_days=365),
}


# ---------------------------------------------------------------------------
# Per-item freshness record
# ---------------------------------------------------------------------------

@dataclass
class DataFreshnessItem:
    """Freshness record for one data input."""
    category: str                     # e.g. "price", "financial_statements"
    label: str                        # Human-readable label
    period_or_date: str               # e.g. "FY2024", "2026-08-09", "Q3 2025"
    data_date: Optional[date] = None  # Parsed date for threshold comparison
    status: FreshnessStatus = FreshnessStatus.UNKNOWN
    note: str = ""                    # Additional context or caveat

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["data_date"] = self.data_date.isoformat() if self.data_date else None
        return d


# ---------------------------------------------------------------------------
# Full freshness assessment
# ---------------------------------------------------------------------------

@dataclass
class DataFreshnessAssessment:
    """
    Aggregated freshness view across all inputs for one analysis.

    Confidence impact rules:
    - All CURRENT          → no confidence penalty
    - Any STALE critical   → cap confidence at MEDIUM (never HIGH)
    - All STALE critical   → cap confidence at LOW
    - UNKNOWN              → treat as AGING (warn, but don't hard-cap)

    Critical categories: price, financial_statements, valuation_inputs
    Non-critical:        research (more qualitative, slower-changing)
    """
    analysis_date: str = ""
    items: List[DataFreshnessItem] = field(default_factory=list)

    # Overall summary
    overall_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    confidence_cap: Optional[str] = None    # None | "MEDIUM" | "LOW"
    freshness_notes: List[str] = field(default_factory=list)
    stale_inputs: List[str] = field(default_factory=list)       # What's stale
    refresh_priorities: List[str] = field(default_factory=list) # What to refresh first

    def add_item(self, item: DataFreshnessItem) -> None:
        self.items.append(item)

    def compute(self, reference_date: Optional[date] = None) -> "DataFreshnessAssessment":
        """
        Evaluate freshness of all items and set overall_status and confidence_cap.
        Call this after adding all items.
        """
        ref = reference_date or date.today()
        critical = {"price", "financial_statements", "valuation_inputs"}

        # Recompute status for each item that has a data_date
        for item in self.items:
            if item.data_date and item.status == FreshnessStatus.UNKNOWN:
                thresholds = FRESHNESS_THRESHOLDS.get(item.category)
                if thresholds:
                    item.status = thresholds.classify(item.data_date, ref)

        statuses = [i.status for i in self.items]
        critical_statuses = [i.status for i in self.items if i.category in critical]

        # Overall status = worst single status
        if FreshnessStatus.STALE in statuses:
            self.overall_status = FreshnessStatus.STALE
        elif FreshnessStatus.AGING in statuses:
            self.overall_status = FreshnessStatus.AGING
        elif all(s == FreshnessStatus.CURRENT for s in statuses):
            self.overall_status = FreshnessStatus.CURRENT
        else:
            self.overall_status = FreshnessStatus.UNKNOWN

        # Confidence cap
        stale_critical = [i for i in self.items
                          if i.category in critical and i.status == FreshnessStatus.STALE]
        if len(stale_critical) >= 2:
            self.confidence_cap = "LOW"
        elif len(stale_critical) == 1:
            self.confidence_cap = "MEDIUM"
        else:
            self.confidence_cap = None  # No cap

        # Stale inputs and refresh priorities
        for item in self.items:
            if item.status == FreshnessStatus.STALE:
                self.stale_inputs.append(item.label)
                if item.category in critical:
                    self.refresh_priorities.append(
                        f"{item.label} ({item.period_or_date}) — required for high-confidence conclusion"
                    )

        # Freshness notes
        if self.overall_status == FreshnessStatus.CURRENT:
            self.freshness_notes.append("All data inputs are sufficiently current.")
        elif self.overall_status == FreshnessStatus.STALE:
            self.freshness_notes.append(
                "One or more critical inputs are stale. The investment conclusion is valid "
                "but confidence is capped — refresh before acting on this analysis."
            )
            self.freshness_notes.append(
                "Stale data does NOT imply the company is unattractive. "
                "It means the conclusion may not reflect the most current fundamentals."
            )
        elif self.overall_status == FreshnessStatus.AGING:
            self.freshness_notes.append(
                "Some inputs are aging. The conclusion remains usable but a refresh "
                "is recommended before any significant portfolio action."
            )

        return self

    def apply_confidence_cap(self, confidence: str) -> str:
        """
        Apply the freshness confidence cap to a computed confidence level.
        Returns the capped (or unchanged) confidence string.
        """
        order = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}
        if self.confidence_cap is None:
            return confidence
        cap_rank = order.get(self.confidence_cap, 1)
        conf_rank = order.get(confidence.upper(), 1)
        return confidence if conf_rank <= cap_rank else self.confidence_cap

    def to_dict(self) -> dict:
        return {
            "analysis_date": self.analysis_date,
            "overall_status": self.overall_status.value,
            "confidence_cap": self.confidence_cap,
            "freshness_notes": self.freshness_notes,
            "stale_inputs": self.stale_inputs,
            "refresh_priorities": self.refresh_priorities,
            "items": [i.to_dict() for i in self.items],
        }

    def summary_table(self) -> str:
        """Return a markdown-style summary table of freshness items."""
        lines = ["| Data | Period/Date | Status |", "|---|---|---|"]
        for item in self.items:
            lines.append(f"| {item.label} | {item.period_or_date} | {item.status.value} |")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """Try to parse a date string into a date object. Returns None on failure."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def build_freshness_assessment(
    analysis_date: str,
    price_date: Optional[str] = None,
    financial_statements_period: Optional[str] = None,
    financial_statements_date: Optional[str] = None,
    earnings_period: Optional[str] = None,
    earnings_date: Optional[str] = None,
    research_date: Optional[str] = None,
    valuation_date: Optional[str] = None,
) -> DataFreshnessAssessment:
    """
    Convenience factory for building a DataFreshnessAssessment from date strings.

    Parameters map to standard pipeline fields:
      price_date              : date of last price quote
      financial_statements_*  : period/date of latest annual financials
      earnings_*              : period/date of latest earnings report
      research_date           : date of business research assessment
      valuation_date          : date of valuation inputs
    """
    ref = _parse_date(analysis_date) or date.today()
    assessment = DataFreshnessAssessment(analysis_date=analysis_date)

    # Price
    pd = _parse_date(price_date)
    thresholds = FRESHNESS_THRESHOLDS["price"]
    assessment.add_item(DataFreshnessItem(
        category="price",
        label="Market price",
        period_or_date=price_date or "Unknown",
        data_date=pd,
        status=thresholds.classify(pd, ref) if pd else FreshnessStatus.UNKNOWN,
    ))

    # Financial statements
    fsd = _parse_date(financial_statements_date)
    thresholds = FRESHNESS_THRESHOLDS["financial_statements"]
    assessment.add_item(DataFreshnessItem(
        category="financial_statements",
        label="Financial statements",
        period_or_date=financial_statements_period or financial_statements_date or "Unknown",
        data_date=fsd,
        status=thresholds.classify(fsd, ref) if fsd else FreshnessStatus.UNKNOWN,
    ))

    # Earnings — only add item when a date or period is actually provided.
    # Phase 8.3 fix: omitting earnings_date previously created an UNKNOWN item
    # that dragged the overall_status to UNKNOWN even when price was CURRENT.
    if earnings_date or earnings_period:
        ed = _parse_date(earnings_date)
        thresholds = FRESHNESS_THRESHOLDS["earnings"]
        assessment.add_item(DataFreshnessItem(
            category="earnings",
            label="Earnings data",
            period_or_date=earnings_period or earnings_date or "Unknown",
            data_date=ed,
            status=thresholds.classify(ed, ref) if ed else FreshnessStatus.UNKNOWN,
        ))

    # Research — only add item when a date is actually provided.
    # Phase 8.3 fix: same pattern as earnings above.
    if research_date:
        rd = _parse_date(research_date)
        thresholds = FRESHNESS_THRESHOLDS["research"]
        assessment.add_item(DataFreshnessItem(
            category="research",
            label="Business research",
            period_or_date=research_date or "Unknown",
            data_date=rd,
            status=thresholds.classify(rd, ref) if rd else FreshnessStatus.UNKNOWN,
        ))

    # Valuation inputs
    vd = _parse_date(valuation_date) or fsd
    thresholds = FRESHNESS_THRESHOLDS["valuation_inputs"]
    assessment.add_item(DataFreshnessItem(
        category="valuation_inputs",
        label="Valuation inputs",
        period_or_date=valuation_date or financial_statements_period or "Unknown",
        data_date=vd,
        status=thresholds.classify(vd, ref) if vd else FreshnessStatus.UNKNOWN,
    ))

    return assessment.compute(reference_date=ref)
