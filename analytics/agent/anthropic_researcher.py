"""
Anthropic Research Executor — Phase 9.1
========================================
Implements `AnthropicResearcher`, a pluggable research executor that satisfies
the injectable executor contract used by `ResearchOrchestrator`:

    researcher(step_name: str, context: dict) -> Optional[dict]

Returns a structured dict for the given research step, or None when the API is
unavailable, the response is malformed, or the model signals insufficient data.

Architecture constraints (strictly enforced)
--------------------------------------------
1.  L1/L2/L3 boundary: this module produces only L1 (quantitative facts) and
    L2 (qualitative interpretations).  L3 investment conclusions are never
    produced here — that is Phase 7's job.

2.  No fabrication: if the model cannot support a claim with a cited source,
    the response must leave that field blank or return a research gap flag.
    The caller (ResearchOrchestrator) treats a None return as an explicit gap.

3.  Gate 1 safety: if business_understanding returns a result with rating
    INSUFFICIENT, that propagates through Gate 1 → WAIT_INSUFFICIENT_EVIDENCE.
    The orchestrator enforces this; we just surface what the model says honestly.

4.  Structured JSON only: responses are parsed as JSON against a declared
    schema.  Free-form text parsing is never used.  Malformed responses → None.

5.  Fail gracefully: missing API key, missing `anthropic` package, network
    error, or API error all result in None (the quantitative fallback takes
    over). Errors are logged at WARNING level; never raised to the caller.

6.  Ticker-agnostic: no hard-coded company names, tickers, or conclusions.

Evidence tiers
--------------
  T1 — Primary source: annual report, regulatory filing, investor presentation
  T2 — Secondary: reputable financial database, industry research report
  T3 — Supporting: investor commentary, news, general knowledge

The model is asked to self-report its source tier.  T3 evidence is accepted
as supporting context but NEVER used as the sole basis for a moat or
management claim.

Usage
-----
    from analytics.agent.anthropic_researcher import AnthropicResearcher

    researcher = AnthropicResearcher()           # uses ANTHROPIC_API_KEY env var
    if researcher.is_available():
        result = researcher("business_understanding", context)

    # Or inject into ResearchOrchestrator:
    from analytics.agent.research_orchestrator import ResearchOrchestrator
    orchestrator = ResearchOrchestrator(research_executor=researcher)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default model — cheapest capable model; can be overridden at construction.
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 2048
_RETRY_ATTEMPTS = 2
_RETRY_DELAY_S = 2.0

# ---------------------------------------------------------------------------
# Per-step JSON schemas (sent to the model as the required output format)
# ---------------------------------------------------------------------------

_STEP_SCHEMAS: Dict[str, dict] = {
    "business_understanding": {
        "description": "What this company does, how it earns money, and whether it is understandable.",
        "fields": {
            "what_it_does": "string — plain-language description of operations (3–5 sentences)",
            "how_it_makes_money": "string — revenue model and profit mechanism",
            "main_products_services": "array of strings",
            "main_customer_groups": "array of strings",
            "revenue_sources": "array of strings (name each revenue stream)",
            "major_cost_drivers": "array of strings",
            "understandability_rating": "one of: Sufficient | Borderline | Insufficient",
            "understandability_note": "string — explain the rating",
            "confidence": "one of: High | Medium | Low",
            "evidence": "array of {fact, source, source_tier, confidence} — cite sources",
        },
        "required": ["what_it_does", "understandability_rating"],
    },
    "moat_analysis": {
        "description": "Competitive advantage assessment using the Claim→Evidence→Durability→Threats→Conclusion framework.",
        "fields": {
            "active_sources": "array of strings — moat types with positive conclusion (e.g. switching_costs, cost_advantage). Empty array if no moat.",
            "overall_strength": "one of: None | Weak | Moderate | Strong | Exceptional",
            "overall_durability": "one of: Low | Medium | High",
            "trajectory": "one of: Strengthening | Stable | Weakening | Insufficient Data",
            "moat_summary": "string — full reasoning paragraph. Be specific about evidence.",
            "roic_consistency_note": "string — does the provided ROIC data support or challenge the moat thesis?",
            "confidence": "one of: High | Medium | Low",
            "research_gaps": "array of strings — what could not be verified",
        },
        "required": ["overall_strength", "moat_summary"],
    },
    "industry_analysis": {
        "description": "Industry-level structural attractiveness.",
        "fields": {
            "industry_name": "string",
            "classification": "one of: Attractive | Neutral | Challenging",
            "classification_reasoning": "string — explain why",
            "technology_disruption_risk": "string — current and credible disruption threats",
            "capital_intensity": "string — High / Medium / Low with context",
            "confidence": "one of: High | Medium | Low",
        },
        "required": ["classification", "classification_reasoning"],
    },
    "growth_analysis": {
        "description": "Quality and sustainability of growth. Do NOT make investment conclusions.",
        "fields": {
            "revenue_growth_quality": "string — is growth organic, sustainable, driven by what factors?",
            "organic_vs_inorganic": "string — proportion organic vs acquisition-driven",
            "growth_sustainability_assessment": "string — can this growth rate be maintained? Why?",
            "growth_drivers": "array of strings",
            "growth_ceiling_risks": "array of strings — factors that could cap growth",
            "confidence": "one of: High | Medium | Low",
        },
        "required": ["revenue_growth_quality"],
    },
    "management_analysis": {
        "description": "Capital allocation track record, integrity, and alignment. Investor sentiment is supporting evidence only.",
        "fields": {
            "capital_allocation": "string — how does management allocate capital? Buybacks, dividends, M&A, capex?",
            "execution_track_record": "string — has management delivered on stated plans?",
            "overall_rating": "one of: Strong | Good | Mixed | Weak | Insufficient Data",
            "management_summary": "string — concise summary of the evidence",
            "confidence": "one of: High | Medium | Low",
        },
        "required": ["overall_rating", "management_summary"],
    },
    "risk_analysis": {
        "description": "Key risks, classified as temporary or structural where possible.",
        "fields": {
            "risk_summary": "string — concise overview of the main risk factors",
            "overall_level": "one of: Low | Moderate | High",
            "temporary_vs_structural_note": "string — which risks are cyclical vs permanent?",
            "confidence": "one of: High | Medium | Low",
        },
        "required": ["risk_summary", "overall_level"],
    },
    "bull_bear_analysis": {
        "description": "Bull and bear cases with mandatory devil's advocate. The bear case must be actively researched, not theoretical.",
        "fields": {
            "bull_case_title": "string — short title for the bull thesis",
            "bull_case_narrative": "string — narrative paragraph for the bull case",
            "bear_case_title": "string — short title for the bear thesis",
            "bear_case_narrative": "string — narrative paragraph for the bear case (mandatory)",
            "thesis_breakers": (
                "array of objects — each with: "
                "condition (string — what would break the thesis), "
                "likelihood (one of: LOW | MEDIUM | HIGH | UNKNOWN — see rules below), "
                "evidence (array of strings — specific quantitative facts from the provided "
                "financial context that support this likelihood, e.g. payout ratio, FCF, "
                "credit metrics), "
                "likelihood_rationale (string — one sentence: why this level vs alternatives; "
                "for UNKNOWN: what specific evidence is missing). "
                "LIKELIHOOD RULES: "
                "Assign LOW, MEDIUM, or HIGH ONLY when the available financial/operational "
                "data in this context supports that assessment. "
                "Assign UNKNOWN when the available evidence is insufficient to make a "
                "defensible assessment — for example, when credit-rating data, regulatory "
                "filings, or other required evidence are not present in the provided context. "
                "Do NOT default to MEDIUM because evidence is missing — that is UNKNOWN."
            ),
            "devils_advocate_research_note": "string — what evidence was found AGAINST the thesis?",
            "confirmation_bias_check": "string — what would disprove the thesis?",
        },
        "required": ["bear_case_narrative", "thesis_breakers"],
    },
}

# ---------------------------------------------------------------------------
# System prompt (shared across all steps)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a financial research assistant supporting an investment analysis pipeline.

Your role is to provide STRUCTURED RESEARCH for a single step of a multi-step \
investment research workflow. You return ONLY valid JSON matching the schema \
provided in the user message — no preamble, no explanation, no markdown fences.

STRICT RULES (violation → pipeline rejects your output):
1. Return ONLY a single JSON object. No text before or after.
2. Never invent facts. If you cannot support a claim with a cited source, \
   leave that field empty ("") or omit it.
3. Output is L1 (quantitative facts) or L2 (qualitative interpretations) ONLY. \
   Do NOT produce L3 investment conclusions such as "this is a BUY" or \
   "the stock is undervalued."
4. For material claims (moat, management quality, competitive position), cite \
   the source tier: T1 = regulatory filing/annual report; T2 = reputable \
   financial database or industry report; T3 = general knowledge or news.
5. If you cannot support a positive moat or management rating with T1 or T2 \
   evidence, set the rating to "Insufficient Data" or "None" and explain why \
   in the relevant text field.
6. Research gaps are acceptable and expected. Flag them explicitly in \
   research_gaps fields rather than filling them with model assumptions.
7. Do not use information that could identify specific portfolio sizes, \
   cost bases, or share counts — these are private.
"""

# ---------------------------------------------------------------------------
# Context formatter
# ---------------------------------------------------------------------------

def _format_context(step_name: str, context: Dict[str, Any]) -> str:
    """
    Build the user-turn message: financial context + step schema + instructions.
    """
    ticker       = context.get("ticker", "UNKNOWN")
    company_name = context.get("company_name", "Unknown Company")
    analysis_date = context.get("analysis_date", "")

    schema = _STEP_SCHEMAS.get(step_name, {})
    schema_desc   = schema.get("description", "")
    schema_fields = schema.get("fields", {})
    required      = schema.get("required", [])

    # Financial context block (quantitative facts only)
    quant_lines = [
        f"Ticker: {ticker}",
        f"Company: {company_name}",
        f"Analysis date: {analysis_date}",
    ]
    # Phase 11B P0-2: metrics that must always be explicitly labelled — even when absent —
    # so the LLM cannot silently reconstruct them from training knowledge.
    # "always_report" keys are emitted as "UNAVAILABLE — <reason>" when None; all others
    # are omitted when None (unchanged behaviour).
    _ALWAYS_REPORT = {
        "revenue_cagr_5yr": "5-year baseline data not available in provided context",
        "roic_5yr_avg":     "5-year ROIC average not available in provided context",
    }
    for key in [
        "currency", "current_price", "market_cap", "pe_ratio", "ev_ebitda",
        "revenue_cagr_3yr", "revenue_cagr_3yr_label", "revenue_cagr_5yr", "annual_revenues",
        "gross_margin", "operating_margin", "net_margin",
        "fcf_current", "annual_fcf",
        "total_debt", "net_debt", "interest_coverage",
        "roic_current", "roic_5yr_avg",
    ]:
        val = context.get(key)
        if val is not None:
            quant_lines.append(f"{key}: {val}")
        elif key in _ALWAYS_REPORT:
            quant_lines.append(f"{key}: UNAVAILABLE — {_ALWAYS_REPORT[key]}")

    # Schema block
    field_lines = "\n".join(
        f'  "{k}": {v}' for k, v in schema_fields.items()
    )
    required_str = ", ".join(f'"{r}"' for r in required) if required else "(none)"

    # Phase 11B P0-2: evidence-boundary instruction for bull_bear_analysis step.
    # This step is the source of CAGR fabrication: the LLM uses training knowledge
    # to fill UNAVAILABLE metrics.  The instruction below explicitly forbids this.
    _extra_reminders = ""
    if step_name == "bull_bear_analysis":
        _extra_reminders = (
            "- EVIDENCE BOUNDARY: You MUST NOT reference or reconstruct any metric "
            "that is labelled UNAVAILABLE in the Company Financial Context above. "
            "If revenue_cagr_5yr is UNAVAILABLE, do NOT state a 5-year CAGR figure "
            "in any narrative or evidence field — not even if you believe you know the "
            "value from training data.  Use only the metrics explicitly provided above. "
            "If a metric is missing, note the gap explicitly rather than filling it.\n"
        )

    return (
        f"## Research Step: {step_name}\n\n"
        f"**Purpose:** {schema_desc}\n\n"
        f"## Company Financial Context (L1 — quantitative facts only)\n\n"
        + "\n".join(quant_lines)
        + "\n\n"
        f"## Required JSON Output Schema\n\n"
        f"Return a JSON object with these fields:\n"
        f"{{\n{field_lines}\n}}\n\n"
        f"Required fields: {required_str}\n\n"
        f"## Important reminders\n"
        f"- Return ONLY valid JSON. No markdown, no preamble.\n"
        f"- Do not make investment conclusions (no BUY/SELL/HOLD).\n"
        f"- Leave fields empty rather than inventing content.\n"
        f"- Cite sources; flag gaps in research_gaps where applicable.\n"
        + _extra_reminders
    )


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Optional[dict]:
    """
    Extract a JSON object from the model response.
    Handles: bare JSON, JSON inside ```json fences, JSON inside ``` fences.
    Returns None if no valid JSON object can be extracted.
    """
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find any {...} block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _validate_required(parsed: dict, step_name: str) -> bool:
    """Return True if all required fields for the step are present and non-empty."""
    schema   = _STEP_SCHEMAS.get(step_name, {})
    required = schema.get("required", [])
    for field in required:
        val = parsed.get(field)
        if val is None or val == "" or val == []:
            log.warning(
                "AnthropicResearcher: step=%s missing required field '%s'",
                step_name, field,
            )
            return False
    return True


# ---------------------------------------------------------------------------
# AnthropicResearcher
# ---------------------------------------------------------------------------

class AnthropicResearcher:
    """
    Pluggable research executor that calls the Anthropic API.

    Satisfies the injectable executor contract:
        __call__(step_name: str, context: dict) -> Optional[dict]

    Parameters
    ----------
    api_key : str, optional
        Anthropic API key. Defaults to ``ANTHROPIC_API_KEY`` env var.
    model : str, optional
        Model ID. Defaults to ``claude-haiku-4-5-20251001``.
    max_tokens : int, optional
        Max tokens per response. Default 2048.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _MAX_TOKENS,
    ) -> None:
        self._api_key   = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model     = model
        self._max_tokens = max_tokens
        self._client    = None   # lazy-initialised

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """
        Return True if the researcher can make API calls:
        - ``anthropic`` package is installed
        - API key is non-empty
        """
        if not self._api_key:
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    # ------------------------------------------------------------------
    # Lazy client initialisation
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return (and lazily create) the Anthropic client."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic package is not installed. "
                    "Install with: pip install anthropic"
                ) from exc
        return self._client

    # ------------------------------------------------------------------
    # Executor contract
    # ------------------------------------------------------------------

    def __call__(
        self,
        step_name: str,
        context: Dict[str, Any],
    ) -> Optional[dict]:
        """
        Execute a single research step and return a structured dict.

        Returns None when:
        - API key is missing or invalid
        - ``anthropic`` package is not installed
        - API call fails after retries
        - Response is malformed JSON
        - Required fields are absent from the response

        Never raises — all errors are logged at WARNING level.
        """
        if not self._api_key:
            log.warning(
                "AnthropicResearcher: ANTHROPIC_API_KEY not set — "
                "returning None for step=%s (quantitative fallback will apply)",
                step_name,
            )
            return None

        if step_name not in _STEP_SCHEMAS:
            log.warning(
                "AnthropicResearcher: unknown step_name=%s — returning None",
                step_name,
            )
            return None

        user_message = _format_context(step_name, context)

        for attempt in range(1, _RETRY_ATTEMPTS + 1):
            try:
                result = self._call_api(user_message)
                if result is not None:
                    return result
            except Exception as exc:
                log.warning(
                    "AnthropicResearcher: API error (attempt %d/%d) "
                    "for step=%s ticker=%s: %s",
                    attempt, _RETRY_ATTEMPTS,
                    step_name, context.get("ticker", "?"), exc,
                )
                if attempt < _RETRY_ATTEMPTS:
                    time.sleep(_RETRY_DELAY_S)

        log.warning(
            "AnthropicResearcher: all retries exhausted for step=%s ticker=%s",
            step_name, context.get("ticker", "?"),
        )
        return None

    def _call_api(self, user_message: str) -> Optional[dict]:
        """
        Make a single API call and parse/validate the response.
        Returns the parsed dict, or None on parse/validation failure.
        Raises on network/API errors (caller handles retries).
        """
        # Extract step_name from user_message for validation
        step_name = ""
        m = re.search(r"## Research Step: (\S+)", user_message)
        if m:
            step_name = m.group(1)

        client = self._get_client()
        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                raw_text += block.text

        if not raw_text.strip():
            log.warning(
                "AnthropicResearcher: empty response for step=%s", step_name
            )
            return None

        parsed = _extract_json(raw_text)
        if parsed is None:
            log.warning(
                "AnthropicResearcher: malformed JSON response for step=%s. "
                "Raw text (first 200 chars): %s",
                step_name, raw_text[:200],
            )
            return None

        if step_name and not _validate_required(parsed, step_name):
            log.warning(
                "AnthropicResearcher: response for step=%s failed "
                "required-field validation — returning None",
                step_name,
            )
            return None

        log.info(
            "AnthropicResearcher: step=%s completed successfully",
            step_name,
        )
        return parsed


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def make_anthropic_researcher(
    api_key: Optional[str] = None,
    model: str = _DEFAULT_MODEL,
) -> Optional[AnthropicResearcher]:
    """
    Create an AnthropicResearcher if the API key is available.
    Returns None if key is absent or the anthropic package is missing,
    so callers can do:

        researcher = make_anthropic_researcher() or quantitative_executor
    """
    r = AnthropicResearcher(api_key=api_key, model=model)
    if r.is_available():
        return r
    return None
