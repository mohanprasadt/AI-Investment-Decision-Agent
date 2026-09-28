"""
Data Status — Phase 10.5
=========================
Cache status reader for the MVP ticker universe.

Reads disk-based JSON cache files to determine what data is available locally
for each ticker. No network calls, no yfinance imports.

Cache file naming convention (from data/ingestion/fetcher.py):
  {TICKER_SAFE}_info.json          — yfinance .info dict
  {TICKER_SAFE}_financials.json    — income statement, balance sheet, cash flow
  {TICKER_SAFE}_history_5y.json    — 5-year price history

where TICKER_SAFE = ticker.replace(".", "_")

Each file contains at minimum:
  _fetch_success : bool
  _fetched_at    : ISO-8601 datetime string (UTC)
  _fetch_error   : str or None

Public API:
  get_ticker_cache_status(ticker) -> dict
  get_mvp_universe_status()       -> list[dict]
  render_status_badge(status)     -> str   (for Streamlit markdown)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CACHE_DIR = _PROJECT_ROOT / "data" / "cache"

# TTL constants — mirrors data/ingestion/fetcher.py so status reflects reality
_TTL_INFO_HOURS = 24
_TTL_FINANCIALS_HOURS = 48
_TTL_HISTORY_HOURS = 24


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ticker_safe(ticker: str) -> str:
    """Convert ticker to cache-file-safe name (dots → underscores)."""
    return ticker.replace(".", "_")


def _read_cache_file(ticker: str, suffix: str) -> Optional[Dict[str, Any]]:
    """
    Read a single cache JSON file. Returns None if the file doesn't exist,
    can't be parsed, or has _fetch_success=False.
    """
    path = _CACHE_DIR / f"{_ticker_safe(ticker)}_{suffix}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data


def _age_hours(fetched_at_iso: Optional[str]) -> Optional[float]:
    """Return age in hours of a cached item, or None if timestamp is missing."""
    if not fetched_at_iso:
        return None
    try:
        dt = datetime.fromisoformat(fetched_at_iso)
        # Make timezone-aware if naive (assume UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - dt).total_seconds() / 3600
    except (ValueError, TypeError):
        return None


def _file_status(data: Optional[Dict[str, Any]], ttl_hours: float) -> Dict[str, Any]:
    """
    Summarise a single cache file into a status dict:
      present   : bool — file exists and was parsed
      success   : bool — _fetch_success is True
      age_hours : float | None
      fresh     : bool — within TTL
      fetched_at: str | None — ISO datetime
      error     : str | None — _fetch_error if present
    """
    if data is None:
        return {"present": False, "success": False, "age_hours": None,
                "fresh": False, "fetched_at": None, "error": None}

    success = bool(data.get("_fetch_success", False))
    fetched_at = data.get("_fetched_at")
    age = _age_hours(fetched_at)
    fresh = success and age is not None and age < ttl_hours

    return {
        "present": True,
        "success": success,
        "age_hours": age,
        "fresh": fresh,
        "fetched_at": fetched_at,
        "error": data.get("_fetch_error"),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_ticker_cache_status(ticker: str) -> Dict[str, Any]:
    """
    Return a comprehensive cache status dict for a single ticker.

    Keys
    ----
    ticker          : str
    company_name    : str — from cached info, or ticker itself if unavailable
    info            : dict — status of *_info.json
    financials      : dict — status of *_financials.json
    history         : dict — status of *_history_5y.json
    ready           : bool — all three files present, successful, and fresh
    any_data        : bool — at least info is fresh (enough to show something)
    overall_status  : str — "READY" | "PARTIAL" | "STALE" | "EMPTY"
    age_display     : str — human-readable age of the info file (e.g. "3h ago")
    source_label    : str — "Cache (fresh)" | "Cache (stale)" | "Not cached"
    """
    info_data = _read_cache_file(ticker, "info")
    fin_data = _read_cache_file(ticker, "financials")
    hist_data = _read_cache_file(ticker, "history_5y")

    info_st = _file_status(info_data, _TTL_INFO_HOURS)
    fin_st = _file_status(fin_data, _TTL_FINANCIALS_HOURS)
    hist_st = _file_status(hist_data, _TTL_HISTORY_HOURS)

    # Company name: prefer cached longName
    company_name = ticker
    if info_data and info_data.get("_fetch_success"):
        company_name = (
            info_data.get("longName")
            or info_data.get("shortName")
            or ticker
        )

    ready = info_st["fresh"] and fin_st["fresh"] and hist_st["fresh"]
    any_data = info_st["fresh"]

    # Overall status
    if ready:
        overall_status = "READY"
    elif any_data:
        overall_status = "PARTIAL"
    elif info_st["present"] or fin_st["present"] or hist_st["present"]:
        overall_status = "STALE"
    else:
        overall_status = "EMPTY"

    # Human-readable age
    age_h = info_st["age_hours"]
    if age_h is None:
        age_display = "—"
    elif age_h < 1:
        age_display = f"{int(age_h * 60)}m ago"
    elif age_h < 24:
        age_display = f"{age_h:.1f}h ago"
    else:
        age_display = f"{age_h / 24:.1f}d ago"

    # Source label
    if info_st["fresh"]:
        source_label = "Cache (fresh)"
    elif info_st["present"]:
        source_label = "Cache (stale)"
    else:
        source_label = "Not cached"

    return {
        "ticker": ticker,
        "company_name": company_name,
        "info": info_st,
        "financials": fin_st,
        "history": hist_st,
        "ready": ready,
        "any_data": any_data,
        "overall_status": overall_status,
        "age_display": age_display,
        "source_label": source_label,
    }


def get_mvp_universe_status() -> List[Dict[str, Any]]:
    """
    Return get_ticker_cache_status() for every ticker in the MVP universe,
    in the canonical order defined in data/mvp_tickers.py.
    """
    from data.mvp_tickers import MVP_TICKER_SYMBOLS  # type: ignore
    return [get_ticker_cache_status(t) for t in MVP_TICKER_SYMBOLS]


def render_status_badge(status: Dict[str, Any]) -> str:
    """
    Return a short Streamlit-markdown-friendly status badge string.

      READY   → ✅ Cache (fresh)  – 3.2h ago
      PARTIAL → ⚠️ Partial cache – 3.2h ago
      STALE   → 🕐 Stale cache   – 26.1h ago
      EMPTY   → ⬜ Not cached
    """
    os_ = status.get("overall_status", "EMPTY")
    age = status.get("age_display", "—")
    if os_ == "READY":
        return f"✅ Cache (fresh) — {age}"
    if os_ == "PARTIAL":
        return f"⚠️ Partial cache — {age}"
    if os_ == "STALE":
        return f"🕐 Stale — {age}"
    return "⬜ Not cached"


def summarize_universe_readiness() -> Dict[str, Any]:
    """
    Return a compact summary of how many MVP tickers are cached.

    Keys: total, ready, partial, stale, empty
    """
    statuses = get_mvp_universe_status()
    counts: Dict[str, int] = {"READY": 0, "PARTIAL": 0, "STALE": 0, "EMPTY": 0}
    for s in statuses:
        counts[s["overall_status"]] = counts.get(s["overall_status"], 0) + 1
    return {
        "total": len(statuses),
        "ready": counts["READY"],
        "partial": counts["PARTIAL"],
        "stale": counts["STALE"],
        "empty": counts["EMPTY"],
    }
