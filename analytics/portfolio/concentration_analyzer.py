"""
Concentration Analyzer — Phase 6
===================================
Identifies concentration across four dimensions:
  1. Individual position size
  2. Sector concentration
  3. Geographic concentration
  4. Economic group overlap (e.g., multiple Canadian bank holdings)

Design rules:
  - Flags are CONTEXT and AWARENESS only — not automatic rejection rules.
  - A concentrated position in a high-quality, well-understood business is
    a legitimate deliberate choice. Phase 7 weighs concentration against
    quality and conviction.
  - Geographic concentration thresholds are deliberately lenient for Canadian
    home-market investors (CAD portfolio, TSX listings, tax efficiency).
  - "Other" economic group is excluded from economic-group flags
    (it indicates unclassified, not a real group).

This module does NOT say whether to add to / reduce any position.
"""

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from analytics.portfolio.portfolio_models import (
    ConcentrationFlag, ConcentrationFlagType, FlagSeverity, Portfolio,
)


# ---------------------------------------------------------------------------
# Thresholds — context flags, not hard limits
# ---------------------------------------------------------------------------

# Individual position as % of portfolio
_POSITION_NOTE     =  5.0
_POSITION_ELEVATED =  8.0
_POSITION_HIGH     = 12.0

# Single sector as % of portfolio
_SECTOR_NOTE     = 25.0
_SECTOR_ELEVATED = 35.0
_SECTOR_HIGH     = 45.0

# Single geography as % of portfolio
# Canadian home bias is common and expected — thresholds set accordingly
_GEO_NOTE = 65.0
_GEO_HIGH = 80.0

# Economic group (e.g. "Canadian Banks") as % of portfolio
_ECON_GROUP_NOTE     = 20.0
_ECON_GROUP_ELEVATED = 30.0
_ECON_GROUP_HIGH     = 40.0


# ---------------------------------------------------------------------------
# Individual dimensions
# ---------------------------------------------------------------------------

def _position_flag(
    ticker: str,
    weight_pct: float,
) -> List[ConcentrationFlag]:
    flags = []
    if weight_pct >= _POSITION_HIGH:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.POSITION_SIZE,
            severity=FlagSeverity.HIGH,
            dimension=ticker,
            current_pct=weight_pct,
            description=(
                f"{ticker} is {weight_pct:.1f}% of the portfolio — "
                f"a high individual-position concentration."
            ),
        ))
    elif weight_pct >= _POSITION_ELEVATED:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.POSITION_SIZE,
            severity=FlagSeverity.ELEVATED,
            dimension=ticker,
            current_pct=weight_pct,
            description=(
                f"{ticker} is {weight_pct:.1f}% of the portfolio — "
                f"elevated individual-position concentration."
            ),
        ))
    elif weight_pct >= _POSITION_NOTE:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.POSITION_SIZE,
            severity=FlagSeverity.NOTE,
            dimension=ticker,
            current_pct=weight_pct,
            description=(
                f"{ticker} is {weight_pct:.1f}% of the portfolio."
            ),
        ))
    return flags


def _sector_flag(sector: str, sector_weight_pct: float) -> List[ConcentrationFlag]:
    if not sector or sector == "Unclassified":
        return []
    flags = []
    if sector_weight_pct >= _SECTOR_HIGH:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.SECTOR,
            severity=FlagSeverity.HIGH,
            dimension=sector,
            current_pct=sector_weight_pct,
            description=(
                f"{sector} sector is {sector_weight_pct:.1f}% of the portfolio — "
                f"high sector concentration."
            ),
        ))
    elif sector_weight_pct >= _SECTOR_ELEVATED:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.SECTOR,
            severity=FlagSeverity.ELEVATED,
            dimension=sector,
            current_pct=sector_weight_pct,
            description=(
                f"{sector} sector is {sector_weight_pct:.1f}% of the portfolio — "
                f"elevated sector concentration."
            ),
        ))
    elif sector_weight_pct >= _SECTOR_NOTE:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.SECTOR,
            severity=FlagSeverity.NOTE,
            dimension=sector,
            current_pct=sector_weight_pct,
            description=(
                f"{sector} sector is {sector_weight_pct:.1f}% of the portfolio."
            ),
        ))
    return flags


def _geography_flag(geography: str, geo_weight_pct: float) -> List[ConcentrationFlag]:
    if not geography or geography == "Unclassified":
        return []
    flags = []
    if geo_weight_pct >= _GEO_HIGH:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.GEOGRAPHY,
            severity=FlagSeverity.HIGH,
            dimension=geography,
            current_pct=geo_weight_pct,
            description=(
                f"{geography} is {geo_weight_pct:.1f}% of the portfolio — "
                f"highly concentrated in a single geography."
            ),
        ))
    elif geo_weight_pct >= _GEO_NOTE:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.GEOGRAPHY,
            severity=FlagSeverity.NOTE,
            dimension=geography,
            current_pct=geo_weight_pct,
            description=(
                f"{geography} is {geo_weight_pct:.1f}% of the portfolio. "
                f"Canadian home-market exposure is expected in a CAD portfolio."
                if geography == "Canada"
                else f"{geography} is {geo_weight_pct:.1f}% of the portfolio."
            ),
        ))
    return flags


def _economic_group_flag(
    group: str,
    group_weight_pct: float,
) -> List[ConcentrationFlag]:
    if not group or group in ("Other", "Unclassified"):
        return []
    flags = []
    if group_weight_pct >= _ECON_GROUP_HIGH:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.ECONOMIC_GROUP,
            severity=FlagSeverity.HIGH,
            dimension=group,
            current_pct=group_weight_pct,
            description=(
                f"'{group}' economic group is {group_weight_pct:.1f}% of the portfolio — "
                f"high correlated exposure."
            ),
        ))
    elif group_weight_pct >= _ECON_GROUP_ELEVATED:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.ECONOMIC_GROUP,
            severity=FlagSeverity.ELEVATED,
            dimension=group,
            current_pct=group_weight_pct,
            description=(
                f"'{group}' economic group is {group_weight_pct:.1f}% of the portfolio — "
                f"elevated correlated exposure."
            ),
        ))
    elif group_weight_pct >= _ECON_GROUP_NOTE:
        flags.append(ConcentrationFlag(
            flag_type=ConcentrationFlagType.ECONOMIC_GROUP,
            severity=FlagSeverity.NOTE,
            dimension=group,
            current_pct=group_weight_pct,
            description=(
                f"'{group}' economic group is {group_weight_pct:.1f}% of the portfolio. "
                f"Positions in this group move with similar economic drivers."
            ),
        ))
    return flags


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def analyze_concentration(
    ticker: str,
    sector: str,
    geography: str,
    economic_group: str,
    position_weight_pct: float,
    sector_weight_pct: float,
    geography_weight_pct: float,
    economic_group_weight_pct: float,
) -> List[ConcentrationFlag]:
    """
    Evaluate concentration across all four dimensions.
    Returns a list of ConcentrationFlag objects (may be empty).

    Flags are awareness signals only.
    Phase 7 integrates these with business quality and conviction to determine
    whether the concentration is appropriate for this investor's strategy.
    """
    flags: List[ConcentrationFlag] = []
    flags.extend(_position_flag(ticker, position_weight_pct))
    flags.extend(_sector_flag(sector, sector_weight_pct))
    flags.extend(_geography_flag(geography, geography_weight_pct))
    flags.extend(_economic_group_flag(economic_group, economic_group_weight_pct))
    return flags
