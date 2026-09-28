"""
Intent Classifier — Phase 10
==============================
Extended intent classifier for the conversational layer.

Architecture:
  Wraps analytics.agent.intent_parser (3 intents: ANALYZE, FOLLOW_UP, UNKNOWN)
  and adds 4 new intent types needed for the Phase 10 journeys:
    METRIC_EXPLANATION  — "What is ROIC?", "Explain FCF conversion"
    EVIDENCE_REQUEST    — "What is your source?", "Show me the evidence"
    SCENARIO_WHAT_IF    — "What if EPS grows 10%?", "What price makes this a buy?"
    UNKNOWN_CLARIFICATION — anything else

For intents ANALYZE and FOLLOW_UP, this module delegates back to the
existing parse_intent() from analytics.agent.intent_parser — those
routes are fully handled by InvestmentAgent.chat() and the existing
renderer.  No duplication.

Design rule:
  Do NOT build a sophisticated NLP framework.
  Use pattern matching sufficient for the Phase 10 acceptance-test catalogue.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Intent constants (Phase 10 superset of existing 3-intent taxonomy)
# ---------------------------------------------------------------------------

# Existing (from intent_parser.py) — delegated to InvestmentAgent.chat()
INTENT_ANALYZE               = "ANALYZE"
INTENT_FOLLOW_UP             = "FOLLOW_UP"

# New — handled by ConversationManager directly
INTENT_METRIC_EXPLANATION    = "METRIC_EXPLANATION"
INTENT_EVIDENCE_REQUEST      = "EVIDENCE_REQUEST"
INTENT_SCENARIO_WHAT_IF      = "SCENARIO_WHAT_IF"
INTENT_UNKNOWN_CLARIFICATION = "UNKNOWN_CLARIFICATION"

# ---------------------------------------------------------------------------
# Pattern sets for new intents
# ---------------------------------------------------------------------------

# METRIC_EXPLANATION — generic financial term questions, not stock-specific
_METRIC_TERMS = re.compile(
    r"\b(what\s+is|what\s+are|define|definition\s+of|explain\s+what|"
    r"what\s+does\s+\w+\s+mean|how\s+is\s+\w+\s+calculated?|"
    r"how\s+do\s+you\s+calculate)\b",
    re.IGNORECASE,
)
_METRIC_KEYWORDS = re.compile(
    r"\b(roic|return\s+on\s+invested\s+capital|"
    r"fcf\s+conversion|free\s+cash\s+flow\s+conversion|"
    r"ev/ebitda|ebitda\s+multiple|enterprise\s+value|"
    r"p/e\s+ratio|price[\s-]to[\s-]earnings|"
    r"p/fcf|price[\s-]to[\s-]fcf|"
    r"margin\s+of\s+safety|discount\s+rate|"
    r"normaliz(?:ed|ation)|weighted\s+average\s+cost\s+of\s+capital|wacc|"
    r"dcf|discounted\s+cash\s+flow|"
    r"operating\s+leverage|financial\s+leverage|"
    r"capm|beta|cost\s+of\s+equity|cost\s+of\s+debt)\b",
    re.IGNORECASE,
)

# EVIDENCE_REQUEST — asking for sources behind a claim
_EVIDENCE_RE = re.compile(
    r"\b(source|evidence|citation|reference|where\s+did\s+you\s+get|"
    r"how\s+do\s+you\s+know|what\s+is\s+your\s+basis|"
    r"show\s+me\s+the\s+(data|evidence|proof|numbers)|"
    r"back\s+(that|this)\s+up|support\s+(that|this)|"
    r"prove|substantiate|verify|what\s+supports)\b",
    re.IGNORECASE,
)

# SCENARIO_WHAT_IF — hypothetical / at-what-price questions
_SCENARIO_RE = re.compile(
    r"\b(what\s+if|suppose|hypothetically|if\s+the\s+price|"
    r"if\s+(?:eps|fcf|roic|revenue|growth)\s+(?:were?|was|grew?|fell?|drops?|rises?)|"
    r"at\s+what\s+price|what\s+price\s+would|"
    r"if\s+(?:the\s+)?company|what\s+would\s+(?:happen|change)\s+if|"
    r"scenario|sensitivity|under\s+(?:the\s+)?(?:bull|bear|base)\s+case|"
    r"break[\s-]?even|entry\s+point|target\s+price)\b",
    re.IGNORECASE,
)

# METRIC_EXPLANATION — bare definition question at sentence start, not a comparison.
# Matches "What is X", "What are X", "Define X", "Explain X" but NOT
# "Explain why…", "Explain how…", "What if…", "What about…" etc.
_BARE_DEFINITION_RE = re.compile(
    r"^\s*(what\s+(?:is|are)|define|explain)\s+(?!why\b|how\b|when\b|where\b|if\b)",
    re.IGNORECASE,
)

# FOLLOW_UP — "What about X?" pattern not caught by existing _FOLLOW_UP_TRIGGERS
_WHAT_ABOUT_RE = re.compile(r"\bwhat\s+about\b", re.IGNORECASE)

# Ticker pattern (same as intent_parser.py)
_TICKER_RE = re.compile(r"\b([A-Z]{1,6}(?:\.[A-Z]{1,2})?)\b")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_intent(text: str) -> str:
    """
    Classify user input into one of 6 intents.

    Priority order:
    1. ANALYZE — ticker + explicit analyze verb (has_analyze_verb=True)
    2. Intercept FOLLOW_UP for new sub-types before returning it:
         - SCENARIO_WHAT_IF  ("what if", "what would happen if")
         - METRIC_EXPLANATION ("what is TERM", "explain TERM")
         - EVIDENCE_REQUEST  ("what is your source", etc.)
    3. For false-ticker / UNKNOWN results from existing parser:
         - METRIC_EXPLANATION, EVIDENCE_REQUEST, SCENARIO_WHAT_IF
         - FOLLOW_UP ("what about X?" pattern)
    4. UNKNOWN_CLARIFICATION — fallback

    Note on false tickers: the existing parser picks up any ALLCAPS word
    not in its _COMMON_WORDS list as a ticker candidate (e.g. "SHOW", "ROIC",
    "LUNCH", "EPS").  Without an explicit analyze verb those are false positives.
    This classifier checks `has_analyze_verb` before trusting INTENT_ANALYZE.

    Parameters
    ----------
    text : raw user input

    Returns
    -------
    One of the INTENT_* constants defined above.
    """
    from analytics.agent.intent_parser import (
        parse_intent, INTENT_ANALYZE, INTENT_FOLLOW_UP, INTENT_UNKNOWN,
    )

    existing = parse_intent(text)

    # RULE 1 — only trust ANALYZE when there is an explicit analyze verb.
    if existing.intent_type == INTENT_ANALYZE and getattr(existing, "has_analyze_verb", False):
        return INTENT_ANALYZE

    # RULE 2 — existing parser returned FOLLOW_UP (matched "what is", "explain",
    # "what if", "what are", etc.).  Check new intent types before returning it.
    if existing.intent_type == INTENT_FOLLOW_UP:
        # Scenario questions embedded in follow-up triggers ("what if", "what would … if")
        if _SCENARIO_RE.search(text):
            return INTENT_SCENARIO_WHAT_IF
        # Generic definition of a financial term ("What is ROIC?", "Explain FCF conversion")
        if _BARE_DEFINITION_RE.search(text) and _METRIC_KEYWORDS.search(text):
            return INTENT_METRIC_EXPLANATION
        # Evidence/source requests phrased as "what is" questions ("What is your source?")
        if _EVIDENCE_RE.search(text):
            return INTENT_EVIDENCE_REQUEST
        return INTENT_FOLLOW_UP

    # RULE 3 — false-ticker (has_analyze_verb=False) or UNKNOWN.
    # "SHOW", "ROIC", "EPS", "LUNCH" all look like tickers to the existing parser.
    # Apply new patterns before giving up.
    if _BARE_DEFINITION_RE.search(text) and _METRIC_KEYWORDS.search(text):
        return INTENT_METRIC_EXPLANATION

    if _EVIDENCE_RE.search(text):
        return INTENT_EVIDENCE_REQUEST

    if _SCENARIO_RE.search(text):
        return INTENT_SCENARIO_WHAT_IF

    # "What about the dividend?" — conversational follow-up not in existing triggers
    if _WHAT_ABOUT_RE.search(text):
        return INTENT_FOLLOW_UP

    return INTENT_UNKNOWN_CLARIFICATION


# ---------------------------------------------------------------------------
# Financial term explanations (for METRIC_EXPLANATION responses)
# Used by ConversationManager — not by the analytics engine.
# ---------------------------------------------------------------------------

_METRIC_EXPLANATIONS: dict[str, str] = {
    "roic": (
        "ROIC (Return on Invested Capital) measures how efficiently a company "
        "generates profit from its total invested capital (equity + debt). "
        "Formula: NOPAT ÷ Invested Capital. "
        "A ROIC consistently above 15% over many years is strong evidence of "
        "a durable competitive advantage — it shows the business earns well "
        "above its cost of capital. "
        "[GENERAL FINANCIAL EXPLANATION — not specific to the current analysis]"
    ),
    "fcf": (
        "Free Cash Flow (FCF) = Operating Cash Flow − Capital Expenditure. "
        "It measures how much cash a business generates after maintaining and "
        "growing its asset base. Unlike net income, FCF cannot be easily "
        "manipulated by accounting choices. "
        "FCF conversion = FCF ÷ Net Income — a ratio consistently above 80% "
        "indicates high earnings quality. "
        "[GENERAL FINANCIAL EXPLANATION — not specific to the current analysis]"
    ),
    "dcf": (
        "DCF (Discounted Cash Flow) estimates intrinsic value by projecting "
        "future free cash flows and discounting them to present value using a "
        "required rate of return (discount rate). "
        "Inputs: revenue growth rate, FCF margin, terminal growth rate, "
        "discount rate. Small changes in the discount rate or terminal growth "
        "produce large changes in the output — DCF is most useful as a "
        "sanity check alongside multiple-based methods, not as a standalone answer. "
        "[GENERAL FINANCIAL EXPLANATION — not specific to the current analysis]"
    ),
    "p/e": (
        "P/E (Price-to-Earnings) = Current Price ÷ Earnings Per Share. "
        "It tells you how much the market is paying for each rupee/dollar of "
        "earnings. A high P/E can mean the market expects strong growth, or "
        "that the stock is overvalued. Normalised P/E uses an average EPS "
        "over several years to smooth out one-time items. "
        "[GENERAL FINANCIAL EXPLANATION — not specific to the current analysis]"
    ),
    "p/fcf": (
        "P/FCF (Price-to-Free-Cash-Flow) = Current Price ÷ FCF per Share. "
        "Often preferred over P/E because FCF is harder to manipulate than "
        "reported earnings. A lower P/FCF than P/E implies that a portion of "
        "earnings is not converting to cash — possibly due to capex intensity "
        "or working capital consumption. "
        "[GENERAL FINANCIAL EXPLANATION — not specific to the current analysis]"
    ),
    "ev/ebitda": (
        "EV/EBITDA = Enterprise Value ÷ EBITDA. "
        "Enterprise Value = Market Cap + Debt − Cash. "
        "EBITDA = Earnings Before Interest, Tax, Depreciation & Amortisation. "
        "EV/EBITDA is useful for comparing companies with different capital "
        "structures or depreciation policies. It is capital-structure-neutral. "
        "[GENERAL FINANCIAL EXPLANATION — not specific to the current analysis]"
    ),
    "margin of safety": (
        "Margin of Safety = (Fair Value − Current Price) ÷ Fair Value. "
        "It measures how much the stock's price is below your estimate of "
        "intrinsic value. A higher margin of safety reduces the cost of being "
        "wrong in your assumptions. A common rule of thumb: require at least "
        "20–30% margin of safety before buying. "
        "[GENERAL FINANCIAL EXPLANATION — not specific to the current analysis]"
    ),
}

_KEYWORD_TO_TERM = {
    # Compound / specific keys FIRST to prevent substring false-matches.
    # e.g. "p/fcf" contains "fcf" — check "p/fcf" before "fcf".
    "p/fcf": "p/fcf", "price to fcf": "p/fcf", "price-to-fcf": "p/fcf",
    "p/e": "p/e", "pe ratio": "p/e", "price to earnings": "p/e",
    "ev/ebitda": "ev/ebitda", "ebitda": "ev/ebitda",
    "margin of safety": "margin of safety",
    "fcf conversion": "fcf", "free cash flow conversion": "fcf",
    "free cash flow": "fcf",
    "return on invested capital": "roic",
    "discounted cash flow": "dcf",
    # Single-term keys last (shortest, most likely to hit false substrings)
    "roic": "roic",
    "fcf": "fcf",
    "dcf": "dcf",
}


def explain_metric(text: str) -> str:
    """
    Return a general financial explanation for the metric mentioned in text.
    Falls back to a generic "ask about the current analysis" message.
    """
    lower = text.lower()
    for keyword, term in _KEYWORD_TO_TERM.items():
        if keyword in lower:
            return _METRIC_EXPLANATIONS.get(term, "")

    return (
        "I can explain financial metrics such as ROIC, FCF, DCF, P/E, P/FCF, "
        "EV/EBITDA, and margin of safety. "
        "Ask me about one of these, or ask a follow-up question about the "
        "current analysis (e.g. 'Why is P/FCF lower than P/E for this stock?')."
    )
