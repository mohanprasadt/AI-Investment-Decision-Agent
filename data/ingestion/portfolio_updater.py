"""
Portfolio Updater
=================
Reads portfolio_snapshot.csv, enriches it with live market data,
and writes back the updated file — preserving the user's manual entries
(shares, average_cost, thesis fields) and only overwriting calculated fields.

Manual fields (never overwritten):
  shares, average_cost, original_thesis_summary, thesis_status,
  last_review_date, notes

Auto-populated fields:
  company, sector, geography, current_price, current_value,
  portfolio_weight_pct, dividend_yield_pct
"""

import csv
import json
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.financial_quality.financial_metrics_model import CompanyFinancialMetrics

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO_FILE = PROJECT_ROOT / "portfolio" / "portfolio_snapshot.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Geography inference from exchange
# ---------------------------------------------------------------------------

EXCHANGE_TO_GEOGRAPHY = {
    "TSX": "Canada",
    "TSXV": "Canada",
    "NYSE": "United States",
    "NASDAQ": "United States",
    "ARCA": "United States",
    "NSE": "India",
    "BSE": "India",
}


def _infer_geography(exchange: str) -> str:
    return EXCHANGE_TO_GEOGRAPHY.get(exchange.upper(), "Unknown")


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

COMMENT_MARKER = "#"

def read_portfolio_csv(path: Path = PORTFOLIO_FILE) -> List[Dict[str, str]]:
    """
    Read portfolio_snapshot.csv, skipping comment lines (starting with #).
    Returns list of row dicts.
    """
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(line for line in f if not line.strip().startswith(COMMENT_MARKER))
        for row in reader:
            if row.get("ticker", "").strip():
                rows.append(dict(row))
    return rows


def write_portfolio_csv(rows: List[Dict[str, str]], path: Path = PORTFOLIO_FILE) -> None:
    """Write portfolio rows back to CSV, preserving header and comment block."""
    if not rows:
        return

    fieldnames = [
        "ticker", "company", "exchange", "currency", "shares", "average_cost",
        "current_price", "current_value", "portfolio_weight_pct", "sector",
        "geography", "dividend_yield_pct", "original_thesis_summary",
        "thesis_status", "last_review_date", "notes"
    ]

    # Read original file to preserve comment lines at top
    original_lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith(COMMENT_MARKER):
                original_lines.append(line)
            elif original_lines:
                break  # stop collecting comments once we hit the data header

    # Write: comments first, then header, then data
    with open(path, "w", newline="", encoding="utf-8") as f:
        # Preserve original comment lines (instructions)
        for line in original_lines:
            f.write(line)

        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Portfolio enrichment
# ---------------------------------------------------------------------------

def _safe_float(value: Optional[Any]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def enrich_portfolio(
    rows: List[Dict[str, str]],
    metrics_map: Dict[str, CompanyFinancialMetrics],
) -> List[Dict[str, str]]:
    """
    Enrich portfolio rows with data from normalized metrics.
    Preserves manual fields; only updates auto-populated fields.

    Returns enriched rows.
    """
    for row in rows:
        ticker = row.get("ticker", "").strip()
        if not ticker:
            continue

        m = metrics_map.get(ticker)
        if not m:
            continue

        # Company name (only update if currently empty)
        if not row.get("company") and m.company_name:
            row["company"] = m.company_name

        # Sector (only if empty)
        if not row.get("sector") and hasattr(m, "_yf_sector"):
            row["sector"] = m._yf_sector

        # Geography from exchange
        exchange = row.get("exchange", "")
        if not row.get("geography") and exchange:
            row["geography"] = _infer_geography(exchange)

        # Current price
        if m.current_price is not None:
            row["current_price"] = f"{m.current_price:.4f}"

        # Current value (if shares are known)
        shares = _safe_float(row.get("shares"))
        if shares and m.current_price:
            row["current_value"] = f"{shares * m.current_price:.2f}"

        # Dividend yield
        if m.dividend.current_yield_pct is not None:
            row["dividend_yield_pct"] = f"{m.dividend.current_yield_pct:.2f}%"
        elif not m.dividend.pays_dividend:
            row["dividend_yield_pct"] = "0.00%"

    # Recalculate portfolio weights after all prices updated
    total_value = 0.0
    for row in rows:
        val = _safe_float(row.get("current_value"))
        if val:
            total_value += val

    if total_value > 0:
        for row in rows:
            val = _safe_float(row.get("current_value"))
            if val:
                row["portfolio_weight_pct"] = f"{(val / total_value) * 100:.2f}%"
            elif row.get("portfolio_weight_pct", "").startswith("#"):
                row["portfolio_weight_pct"] = ""

    return rows


def recalculate_weights_from_user_values(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    If the user has populated portfolio_weight_pct manually (as in the current file),
    and shares/prices are not yet known, keep the user-provided weights.
    This is a fallback for the initial state before a full data refresh.
    """
    return rows  # weights already in the file from user


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def portfolio_summary(
    rows: List[Dict[str, str]],
    metrics_map: Dict[str, CompanyFinancialMetrics]
) -> Dict[str, Any]:
    """Generate a portfolio summary dict."""
    summary: Dict[str, Any] = {
        "as_of": datetime.utcnow().isoformat()[:10],
        "total_holdings": len(rows),
        "data_fetched": sum(1 for r in rows if metrics_map.get(r.get("ticker", ""), None)),
        "sector_weights": {},
        "geography_weights": {},
        "currency_weights": {},
        "data_quality_issues": [],
    }

    sector_vals: Dict[str, float] = {}
    geo_vals: Dict[str, float] = {}
    ccy_vals: Dict[str, float] = {}
    total_val = 0.0

    for row in rows:
        ticker = row.get("ticker", "")
        m = metrics_map.get(ticker)

        # Try to use weight from file if values not computed
        weight_str = row.get("portfolio_weight_pct", "").replace("%", "")
        weight = _safe_float(weight_str) or 0.0

        sector = row.get("sector") or (m._yf_sector if m and hasattr(m, "_yf_sector") else "Unknown")
        geo = row.get("geography") or _infer_geography(row.get("exchange", ""))
        ccy = row.get("currency", "Unknown")

        sector_vals[sector] = sector_vals.get(sector, 0) + weight
        geo_vals[geo] = geo_vals.get(geo, 0) + weight
        ccy_vals[ccy] = ccy_vals.get(ccy, 0) + weight

        # Data quality
        if m and m.data_quality_notes:
            for note in m.data_quality_notes:
                if "⚠" in note:
                    summary["data_quality_issues"].append(f"{ticker}: {note}")

    summary["sector_weights"] = {k: round(v, 2) for k, v in sorted(sector_vals.items(), key=lambda x: -x[1])}
    summary["geography_weights"] = {k: round(v, 2) for k, v in sorted(geo_vals.items(), key=lambda x: -x[1])}
    summary["currency_weights"] = {k: round(v, 2) for k, v in ccy_vals.items()}

    return summary


def save_processed_metrics(
    metrics_map: Dict[str, CompanyFinancialMetrics],
    filename: str = "portfolio_metrics.json"
) -> Path:
    """Save normalized metrics to processed/ for downstream use."""
    out = {}
    for ticker, m in metrics_map.items():
        out[ticker] = m.to_dict()

    path = PROCESSED_DIR / filename
    with open(path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    return path


def load_processed_metrics(filename: str = "portfolio_metrics.json") -> Dict[str, CompanyFinancialMetrics]:
    """Load previously saved normalized metrics."""
    path = PROCESSED_DIR / filename
    if not path.exists():
        return {}
    with open(path) as f:
        raw = json.load(f)
    return {ticker: CompanyFinancialMetrics.from_dict(data) for ticker, data in raw.items()}


# ---------------------------------------------------------------------------
# Watchlist updater
# ---------------------------------------------------------------------------

WATCHLIST_FILE = PROJECT_ROOT / "portfolio" / "watchlist.csv"

def read_watchlist_csv(path: Path = WATCHLIST_FILE) -> List[Dict[str, str]]:
    rows = []
    if not path.exists():
        return rows
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(line for line in f if not line.strip().startswith(COMMENT_MARKER))
        for row in reader:
            if row.get("ticker", "").strip():
                rows.append(dict(row))
    return rows


def update_watchlist_prices(
    rows: List[Dict[str, str]],
    metrics_map: Dict[str, CompanyFinancialMetrics]
) -> List[Dict[str, str]]:
    """Update current_price in watchlist rows from freshly fetched data."""
    for row in rows:
        ticker = row.get("ticker", "").strip()
        m = metrics_map.get(ticker)
        if m and m.current_price:
            row["current_price"] = f"{m.current_price:.4f}"
    return rows


if __name__ == "__main__":
    # Test with synthetic metrics (no network)
    from analytics.financial_quality.financial_metrics_model import DividendMetrics

    print("Testing portfolio_updater with synthetic data...")
    rows = [
        {
            "ticker": "TEST.TO", "company": "", "exchange": "TSX", "currency": "CAD",
            "shares": "1000", "average_cost": "40.00", "current_price": "",
            "current_value": "", "portfolio_weight_pct": "50%",
            "sector": "", "geography": "", "dividend_yield_pct": "",
            "original_thesis_summary": "Test thesis", "thesis_status": "Intact",
            "last_review_date": "2024-01-01", "notes": ""
        },
    ]

    m = CompanyFinancialMetrics(
        ticker="TEST.TO",
        company_name="Test Company",
        current_price=45.0,
    )
    m.dividend = DividendMetrics(pays_dividend=True, current_yield_pct=3.5)

    enriched = enrich_portfolio(rows, {"TEST.TO": m})
    print(f"  Current price updated: {enriched[0]['current_price']}")
    print(f"  Current value: {enriched[0]['current_value']}")
    print(f"  Dividend yield: {enriched[0]['dividend_yield_pct']}")
    print(f"  Geography: {enriched[0]['geography']}")
    print("portfolio_updater: OK")
