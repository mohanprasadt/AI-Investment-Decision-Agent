"""
MVP Ticker Universe — Phase 10.5
==================================
Single source of truth for the 33 approved MVP tickers.

This module is the canonical definition of the controlled ticker universe.
It is intentionally free of network calls, yfinance imports, and file I/O.
The metadata (name, market, sector) is hardcoded as a stable fallback.
When a ticker's info is cached locally, the UI prefers the cache's longName
over the hardcoded name here.

Usage:
    from data.mvp_tickers import MVP_TICKERS, MVP_TICKER_MAP, MVP_TICKER_SYMBOLS
"""

from __future__ import annotations
from typing import List, Dict, Any

# ---------------------------------------------------------------------------
# Canonical MVP ticker list
# One entry per ticker. No duplicates.
# ---------------------------------------------------------------------------

MVP_TICKERS: List[Dict[str, Any]] = [
    # ── Canadian — Energy ─────────────────────────────────────────────────
    {"ticker": "ENB.TO",      "name": "Enbridge Inc.",                "market": "Canada", "sector": "Energy"},
    {"ticker": "SU.TO",       "name": "Suncor Energy Inc.",           "market": "Canada", "sector": "Energy"},
    {"ticker": "CNQ.TO",      "name": "Canadian Natural Resources",   "market": "Canada", "sector": "Energy"},
    {"ticker": "TOU.TO",      "name": "Tourmaline Oil Corp.",         "market": "Canada", "sector": "Energy"},
    {"ticker": "TPZ.TO",      "name": "Topaz Energy Corp.",           "market": "Canada", "sector": "Energy"},
    {"ticker": "ARX.TO",      "name": "ARC Resources Ltd.",           "market": "Canada", "sector": "Energy"},
    {"ticker": "PPL.TO",      "name": "Pembina Pipeline Corp.",       "market": "Canada", "sector": "Energy"},
    # ── Canadian — Utilities ───────────────────────────────────────────────
    {"ticker": "CPX.TO",      "name": "Capital Power Corp.",          "market": "Canada", "sector": "Utilities"},
    {"ticker": "FTS.TO",      "name": "Fortis Inc.",                  "market": "Canada", "sector": "Utilities"},
    # ── Canadian — Financials ──────────────────────────────────────────────
    {"ticker": "EQB.TO",      "name": "EQB Inc.",                     "market": "Canada", "sector": "Financials"},
    {"ticker": "TD.TO",       "name": "The Toronto-Dominion Bank",    "market": "Canada", "sector": "Financials"},
    {"ticker": "POW.TO",      "name": "Power Corporation of Canada",  "market": "Canada", "sector": "Financials"},
    {"ticker": "MFC.TO",      "name": "Manulife Financial Corp.",     "market": "Canada", "sector": "Financials"},
    {"ticker": "BN.TO",       "name": "Brookfield Corporation",       "market": "Canada", "sector": "Financials"},
    {"ticker": "FFH.TO",      "name": "Fairfax Financial Holdings",   "market": "Canada", "sector": "Financials"},
    {"ticker": "BAM.TO",      "name": "Brookfield Asset Management",  "market": "Canada", "sector": "Financials"},
    {"ticker": "CM.TO",       "name": "Canadian Imperial Bank (CIBC)","market": "Canada", "sector": "Financials"},
    {"ticker": "BNS.TO",      "name": "Bank of Nova Scotia",          "market": "Canada", "sector": "Financials"},
    # ── Canadian — Real Estate ─────────────────────────────────────────────
    {"ticker": "REI.UN.TO",   "name": "RioCan Real Estate Inv. Trust","market": "Canada", "sector": "Real Estate"},
    # ── Canadian — Consumer / Retail ──────────────────────────────────────
    {"ticker": "ATD.TO",      "name": "Alimentation Couche-Tard",     "market": "Canada", "sector": "Consumer"},
    {"ticker": "NWC.TO",      "name": "North West Company",           "market": "Canada", "sector": "Consumer"},
    {"ticker": "DOL.TO",      "name": "Dollarama Inc.",               "market": "Canada", "sector": "Consumer"},
    # ── Canadian — Telecom ────────────────────────────────────────────────
    {"ticker": "T.TO",        "name": "TELUS Corp.",                  "market": "Canada", "sector": "Telecom"},
    # ── Canadian — Technology ─────────────────────────────────────────────
    {"ticker": "CSU.TO",      "name": "Constellation Software Inc.",  "market": "Canada", "sector": "Technology"},
    # ── Canadian — Other ──────────────────────────────────────────────────
    {"ticker": "ABXX.TO",     "name": "ABXX.TO",                     "market": "Canada", "sector": "Other"},
    # ── United States ─────────────────────────────────────────────────────
    {"ticker": "AMZN",        "name": "Amazon.com Inc.",              "market": "USA",    "sector": "Technology"},
    {"ticker": "MSFT",        "name": "Microsoft Corp.",              "market": "USA",    "sector": "Technology"},
    {"ticker": "ASML",        "name": "ASML Holding N.V.",            "market": "USA",    "sector": "Technology"},
    {"ticker": "GOOG",        "name": "Alphabet Inc. (Google)",       "market": "USA",    "sector": "Technology"},
    {"ticker": "TSM",         "name": "Taiwan Semiconductor (ADR)",   "market": "USA",    "sector": "Technology"},
    # ── India ─────────────────────────────────────────────────────────────
    {"ticker": "ITC.NS",      "name": "ITC Limited",                  "market": "India",  "sector": "Consumer"},
    {"ticker": "TATASTEEL.NS","name": "Tata Steel Limited",           "market": "India",  "sector": "Materials"},
    {"ticker": "KTKBANK.NS",  "name": "Karnataka Bank Ltd.",          "market": "India",  "sector": "Financials"},
]

# ---------------------------------------------------------------------------
# Derived lookups — generated once at import time
# ---------------------------------------------------------------------------

# ticker symbol → full metadata dict
MVP_TICKER_MAP: Dict[str, Dict[str, Any]] = {t["ticker"]: t for t in MVP_TICKERS}

# ordered list of ticker symbols only
MVP_TICKER_SYMBOLS: List[str] = [t["ticker"] for t in MVP_TICKERS]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_display_name(ticker: str) -> str:
    """Return the display name for a ticker, or the ticker itself if unknown."""
    meta = MVP_TICKER_MAP.get(ticker)
    return meta["name"] if meta else ticker


def is_mvp_ticker(ticker: str) -> bool:
    """Return True if ticker is in the canonical MVP universe."""
    return ticker.upper().strip() in MVP_TICKER_MAP


def tickers_by_market(market: str) -> List[Dict[str, Any]]:
    """Return all MVP tickers for a given market (e.g. 'Canada', 'USA', 'India')."""
    return [t for t in MVP_TICKERS if t["market"] == market]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate() -> None:
    """Called at import time to catch accidental duplicates."""
    symbols = [t["ticker"] for t in MVP_TICKERS]
    seen = set()
    for s in symbols:
        if s in seen:
            raise ValueError(f"Duplicate MVP ticker detected: {s}")
        seen.add(s)
    assert len(symbols) == 33, f"Expected 33 MVP tickers, got {len(symbols)}"


_validate()
