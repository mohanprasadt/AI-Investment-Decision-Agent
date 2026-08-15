"""
Intent Parser — Phase 8
========================
Parse a free-text user message into a structured Intent.

Portfolio privacy rules enforced here:
  - Never ask for or extract: shares held, average cost, total portfolio value,
    purchase price, other holdings, or account information.
  - The only portfolio information extracted is:
      * Whether a position exists (detected from "I hold" / "I own" language)
      * Portfolio weight percentage, if the user voluntarily provides it

Ticker detection: supports formats such as CNR.TO, CSU.TO, TOI.V, TD.TO, AAPL.
"""

import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Intent types
# ---------------------------------------------------------------------------

INTENT_ANALYZE  = "ANALYZE"
INTENT_FOLLOW_UP = "FOLLOW_UP"
INTENT_UNKNOWN  = "UNKNOWN"


@dataclass
class Intent:
    """Structured result of parsing one user message."""
    intent_type: str                           # ANALYZE | FOLLOW_UP | UNKNOWN

    # --- Analyze fields ---
    ticker: Optional[str] = None               # e.g. "CNR.TO"
    portfolio_weight_pct: Optional[float] = None  # None → no portfolio context
    is_existing_position: bool = False         # True if user says "I hold …"
    ignore_portfolio: bool = False             # True if user says "without my portfolio"

    # True when the message contained an explicit analyze verb ("analyze", "run", etc.).
    # Used by InvestmentAgent to distinguish a genuine re-analysis request from a
    # conceptual question that happens to mention the ticker.
    has_analyze_verb: bool = False

    raw_text: str = ""


# ---------------------------------------------------------------------------
# Pattern sets
# ---------------------------------------------------------------------------

# Words that indicate a follow-up question rather than a new analysis
_FOLLOW_UP_TRIGGERS = re.compile(
    r"\b(why|explain|how|what\s+are|what\s+is|what\s+would|what\s+if"
    r"|biggest\s+risk|key\s+risk|main\s+risk"
    r"|what\s+drove|what\s+driv|tell\s+me\s+more"
    r"|assumption|fair\s+value|stale|uncertain|confidence"
    r"|peer|comparable|thesis\s+break|breaker"
    r"|change\s+(the\s+)?(conclusion|decision|recommendation)"
    r"|more\s+about|elaborate"
    # Investment-horizon / holding-period questions.
    # These are unambiguous follow-up signals: no stock ticker starts with digits,
    # and no genuine new-analysis request contains "10 years" or "buy and hold".
    r"|\d+\s+years?"                    # "10 years", "15 year"
    r"|long[\s-]term"                   # "long-term", "long term"
    r"|buy\s+and\s+hold"               # "buy and hold"
    r"|holding\s+period"               # "holding period"
    r"|investment\s+horizon"           # "investment horizon"
    r"|time\s+horizon"                 # "time horizon"
    r"|hold\s+(this|it|the\s+stock)"   # "hold this stock", "hold it for"
    # Valuation-method questions — always follow-ups; never a new-analysis request.
    # These patterns appear in "Which method makes X look expensive?" and similar.
    r"|which\s+(valuation\s+)?method"  # "which method", "which valuation method"
    r"|what\s+(valuation\s+)?method"   # "what method", "what valuation method"
    r"|what\s+methods"                 # "what methods are used"
    r"|most\s+expensive"               # "look most expensive", "most expensive method"
    r"|look\s+expensive"               # "makes it look expensive"
    r"|p\/e\b|pe\s+ratio|pe\s+multiple"           # P/E ratio questions
    r"|ev\/ebitda|ebitda\s+multiple"              # EV/EBITDA questions
    r"|p\/fcf|price[\s-]to[\s-]fcf"              # P/FCF questions
    r"|which\s+method|what\s+method"              # catch-all for method questions
    r")\b",
    re.IGNORECASE,
)

# Ticker: 1–6 uppercase letters optionally followed by . and 1–2 uppercase letters
_TICKER_RE = re.compile(r"\b([A-Z]{1,6}(?:\.[A-Z]{1,2})?)\b")

# Portfolio weight: "5%", "5 percent", "five percent" (we only handle numeric)
_WEIGHT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)

# Signals that the user has an existing position
_EXISTING_SIGNALS = re.compile(
    r"\b(i\s+(currently\s+)?(hold|own|have|bought|purchased)"
    r"|i\s+am\s+(currently\s+)?holding"
    r"|existing\s+position"
    r"|already\s+(hold|own|have))\b",
    re.IGNORECASE,
)

# Signals that portfolio context should be ignored
_IGNORE_PORTFOLIO_RE = re.compile(
    r"\b(without\s+(considering\s+)?(my\s+)?portfolio"
    r"|ignore\s+(my\s+)?portfolio"
    r"|no\s+portfolio\s+(context|consideration)"
    r"|treat\s+(as|it\s+as)\s+(a\s+)?new\s+position)\b",
    re.IGNORECASE,
)

# Words that strongly suggest "analyze" intent when no follow-up trigger matched
_ANALYZE_TRIGGERS = re.compile(
    r"\b(analyze|analyse|run|check|assess|evaluate|look\s+at|research|review)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_intent(text: str) -> Intent:
    """
    Parse a user message into a structured Intent.

    Rules (in priority order):
    1. If the message matches follow-up patterns → INTENT_FOLLOW_UP
    2. If a ticker is found → INTENT_ANALYZE with extracted portfolio context
    3. Otherwise → INTENT_UNKNOWN
    """
    stripped = text.strip()
    upper   = stripped.upper()

    # -----------------------------------------------------------------
    # 1. Check for follow-up
    # -----------------------------------------------------------------
    if _FOLLOW_UP_TRIGGERS.search(stripped):
        # Extra check: if it also contains a ticker AND an analyze verb,
        # it's probably a fresh analysis request, not a follow-up.
        has_analyze = bool(_ANALYZE_TRIGGERS.search(stripped))
        has_ticker  = bool(_TICKER_RE.search(upper))
        if not (has_analyze and has_ticker):
            return Intent(intent_type=INTENT_FOLLOW_UP, raw_text=stripped)

    # -----------------------------------------------------------------
    # 2. Extract ticker (search on uppercased text for case-insensitive match)
    # -----------------------------------------------------------------
    ticker = None
    for m in _TICKER_RE.finditer(upper):
        candidate = m.group(1)
        # Skip common English words that match the ticker pattern
        if candidate in _COMMON_WORDS:
            continue
        ticker = candidate
        break

    if ticker is None:
        return Intent(intent_type=INTENT_UNKNOWN, raw_text=stripped)

    # -----------------------------------------------------------------
    # 3. Portfolio weight (only what the user explicitly provides)
    # -----------------------------------------------------------------
    weight_match = _WEIGHT_RE.search(stripped)
    weight = float(weight_match.group(1)) if weight_match else None

    # -----------------------------------------------------------------
    # 4. Existing position signal
    # -----------------------------------------------------------------
    is_existing = bool(_EXISTING_SIGNALS.search(stripped)) or (weight is not None)

    # -----------------------------------------------------------------
    # 5. Ignore-portfolio signal
    # -----------------------------------------------------------------
    ignore = bool(_IGNORE_PORTFOLIO_RE.search(stripped))
    if ignore:
        # Explicit override: treat as new position
        weight      = None
        is_existing = False

    has_analyze = bool(_ANALYZE_TRIGGERS.search(stripped))

    return Intent(
        intent_type=INTENT_ANALYZE,
        ticker=ticker,
        portfolio_weight_pct=weight,
        is_existing_position=is_existing,
        ignore_portfolio=ignore,
        has_analyze_verb=has_analyze,
        raw_text=stripped,
    )


# ---------------------------------------------------------------------------
# Common English words that happen to look like tickers — skip these
# ---------------------------------------------------------------------------
_COMMON_WORDS = {
    # 1–2 letter words
    "A", "AN", "AT", "BE", "BY", "DO", "GO", "HI", "I", "IF",
    "IN", "IS", "IT", "ME", "MY", "NO", "OF", "ON", "OR", "SO",
    "TO", "UP", "US", "WE",
    # 3-letter common words
    "ALL", "AND", "ARE", "BUT", "CAN", "FOR", "GET", "HAS", "HOW",
    "ITS", "NOT", "NOW", "THE", "USE", "WAS", "WHO", "WHY", "YOU",
    # 4-letter common words
    "ALSO", "BEEN", "BUYS", "CALL", "DOES", "EACH", "ELSE", "FIND",
    "GIVE", "GOOD", "HAVE", "HELP", "HOLD", "JUST", "KEEP", "KNOW",
    "LIKE", "MAKE", "MANY", "MINE", "MUCH", "NEED", "ONCE", "ONLY",
    "OWNS", "SAID", "SELL", "SOME", "SUCH", "SURE", "TAKE", "THAN",
    "THAT", "THEM", "THEN", "THEY", "THIS", "THUS", "TILL", "TOLD",
    "VERY", "WANT", "WELL", "WERE", "WHAT", "WHEN", "WHOM", "WILL",
    "WITH", "WORK", "YOUR",
    # 5-letter common words (likely false ticker matches)
    "ABOUT", "ABOVE", "AFTER", "AGAIN", "COULD", "DOING", "EARLY",
    "EVERY", "FIRST", "FOUND", "FROM", "GIVEN", "GOING", "GREAT",
    "HELLO", "HENCE", "HERES", "MIGHT", "NEVER", "OTHER", "OUGHT",
    "MAYBE", "PLACE", "RIGHT", "SHALL", "SINCE", "SHALL", "STILL",
    "THERE", "THESE", "THINK", "THOSE", "THREE", "TODAY", "UNDER",
    "UNTIL", "USING", "VOICE", "WEEKS", "WHERE", "WHICH", "WHILE",
    "WHOLE", "WHOSE", "WOULD",
    # Domain-specific words common in investing conversation
    "HOLD", "OWNS", "SELL", "BUYS", "GIVE", "TOLD",
    "CURRENT", "EXISTING", "POSITION", "PORTFOLIO",
    "ANALYZE", "ANALYSE", "CHECK", "REVIEW", "ASSESS",
    "PLEASE", "COULD", "WOULD", "SHOULD", "MIGHT",
    "CURRENTLY", "WITHOUT", "CONSIDERING",
    "BASED", "REACH", "THINK", "ABOVE", "BELOW",
    # Common 2–3 letter words that look like tickers
    "DID", "GET", "GOT", "HAD", "HER", "HIM", "HIS", "LET", "MAY",
    "OUR", "OWN", "PUT", "SAY", "SEE", "SET", "SHE", "TRY", "TWO",
    "YET", "AGO", "ASK", "BIG", "DAY", "FEW", "GOD", "OLD", "NEW",
    "OWE", "PAY", "PER", "RUN", "TOO", "WAY",
    # Valuation-domain words (≤6 chars) that are never real tickers.
    # These appear in method-question follow-ups such as:
    #   "Which valuation METHOD makes ITC LOOK MOST expensive?"
    #   "Which METHOD is MAKING ITC LOOK expensive?"
    # Without these, _TICKER_RE would pick up METHOD, MAKES, LOOK, etc.
    # as false ticker candidates before reaching the real symbol.
    "METHOD", "MAKES", "MAKING", "MOST", "LOOK", "LOOKS",
    "CHEAP", "PRICEY", "DRIVES", "DRIVER", "VALUED", "VALUES",
    "WEIGHT", "METRIC", "RATIOS", "RATIO", "TIMES", "LEAST",
}
