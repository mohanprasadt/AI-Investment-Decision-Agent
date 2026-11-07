"""
Renderer — Phase 8
===================
Formats an InvestmentDecisionAssessment as a concise, human-readable report.

Architecture boundary:
  This is a presentation-only layer.
  It reads from the structured InvestmentDecisionAssessment — it does NOT
  create, modify, or override any L3 conclusion.
  It does NOT perform further analysis or reasoning.
"""

from typing import Optional
from analytics.decision.decision_models import InvestmentDecisionAssessment, DecisionAction


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_assessment(
    d: InvestmentDecisionAssessment,
    portfolio_mode: str = "NONE",  # "NONE" | "WEIGHT_ONLY"
) -> str:
    """
    Render a full InvestmentDecisionAssessment as a human-readable executive view.

    Parameters
    ----------
    d              : The structured assessment (authoritative L3 source)
    portfolio_mode : How portfolio context was provided
    """
    lines = []

    # Header
    lines.append(f"{'=' * 64}")
    lines.append(f"  Investment Decision: {d.company_name} ({d.ticker})")
    lines.append(f"  Analysis date: {d.analysis_date}")
    lines.append(f"{'=' * 64}")

    # Price & freshness
    freshness_status = _freshness_status(d)
    if d.current_price:
        lines.append(f"\nCurrent price:      {d.current_price:.2f} {d.price_currency}"
                     f"  [{freshness_status}]")
        if d.price_date:
            lines.append(f"Price date:         {d.price_date}")
    else:
        lines.append(f"\nCurrent price:      Unknown  [{freshness_status}]")

    # Portfolio mode note
    if portfolio_mode == "WEIGHT_ONLY":
        ctx = d.data_freshness or {}
        lines.append(
            f"\nPortfolio context:  WEIGHT_ONLY mode — existing position.\n"
            f"                    Average cost, shares, and account value are not\n"
            f"                    used in this analysis (privacy protection)."
        )
    elif portfolio_mode == "NONE":
        lines.append(f"\nPortfolio context:  None — evaluated as a new-position candidate.")

    # Three-way attractiveness
    lines.append(f"\n{'─' * 64}")
    lines.append(f"ATTRACTIVENESS SUMMARY")
    lines.append(f"{'─' * 64}")
    lines.append(f"  Business Quality (BQ):      {d.business_quality_label}")
    lines.append(f"  Valuation Attractiveness:   {d.valuation_attractiveness_label}")
    lines.append(f"  Investment Attractiveness:  {d.investment_attractiveness_label}")
    if d.investment_attractiveness_note:
        lines.append(f"  Note: {d.investment_attractiveness_note}")

    # Decision — the key block
    lines.append(f"\n{'─' * 64}")
    lines.append(f"DECISION")
    lines.append(f"{'─' * 64}")
    lines.append(f"  Qualitative view:  {d.qualitative_investment_view or '—'}")
    lines.append(f"  Final action:      {d.action.value}")
    lines.append(f"  Confidence:        {d.decision_confidence.value}")

    if d.price_suppression_applied:
        lines.append(
            f"\n  ⚠  Price data is STALE or UNKNOWN. The transactional action has been\n"
            f"     suppressed to WATCH_PENDING_DATA. Refresh the current market price\n"
            f"     and re-run the analysis to confirm the valuation zone.\n"
            f"     Qualitative view, fair value, and thesis remain valid."
        )
    elif d.data_freshness_cap_applied:
        lines.append(
            f"\n  ⚠  One or more data inputs are STALE. Confidence is capped at LOW.\n"
            f"     The action direction is intact but refresh is recommended."
        )

    # Fair value & zone
    fvr = (d.data_freshness or {})
    lines.append(f"\n{'─' * 64}")
    lines.append(f"VALUATION")
    lines.append(f"{'─' * 64}")
    lines.append(f"  {d.valuation_conclusion}")

    # Try to get fair value range from gate results or direct fields
    fv_text = _fair_value_text(d)
    if fv_text:
        lines.append(f"\n{fv_text}")

    # Narrative
    lines.append(f"\n{'─' * 64}")
    lines.append(f"INVESTMENT THESIS")
    lines.append(f"{'─' * 64}")
    if d.business_thesis:
        for part in d.business_thesis.split(" | "):
            lines.append(f"  {part.strip()}")

    lines.append(f"\n  Why attractive/unattractive:")
    lines.append(f"    {d.why_attractive_or_unattractive}")

    lines.append(f"\n  Biggest reason TO invest:")
    lines.append(f"    {d.biggest_reason_to_invest}")

    lines.append(f"\n  Biggest reason NOT to invest:")
    lines.append(f"    {d.biggest_reason_not_to_invest}")

    # Thesis breakers
    if d.thesis_breakers:
        lines.append(f"\n{'─' * 64}")
        lines.append(f"THESIS BREAKERS  ({len(d.thesis_breakers)})")
        lines.append(f"{'─' * 64}")
        for tb in d.thesis_breakers[:5]:
            likelihood = getattr(tb, "likelihood", "?")
            condition  = getattr(tb, "condition", str(tb))
            lines.append(f"  [{likelihood}] {condition}")

    # What would change the conclusion
    if d.what_would_change_conclusion:
        lines.append(f"\n{'─' * 64}")
        lines.append(f"WHAT WOULD CHANGE THE CONCLUSION")
        lines.append(f"{'─' * 64}")
        for line in d.what_would_change_conclusion.split("\n"):
            lines.append(f"  {line.strip()}")

    # Data / research limitations
    limitations = (d.data_quality_limitations or []) + (d.research_gaps or [])
    if limitations:
        lines.append(f"\n{'─' * 64}")
        lines.append(f"DATA & RESEARCH LIMITATIONS")
        lines.append(f"{'─' * 64}")
        for lim in limitations[:6]:
            lines.append(f"  • {lim}")

    # Recommended next step
    if d.recommended_next_step:
        lines.append(f"\n{'─' * 64}")
        lines.append(f"RECOMMENDED NEXT STEP")
        lines.append(f"{'─' * 64}")
        lines.append(f"  {d.recommended_next_step}")

    # Footer
    lines.append(f"\n{'─' * 64}")
    lines.append(f"  [Decision-support only. This analysis does not execute trades.]")
    lines.append(f"  [Average cost, shares, and account value excluded per privacy policy.]")
    lines.append(f"{'=' * 64}")

    return "\n".join(lines)


def render_followup(question: str, d: InvestmentDecisionAssessment) -> str:
    """
    Answer a follow-up question using the stored InvestmentDecisionAssessment.

    Architecture boundary:
      Answers come from the structured assessment fields only.
      This function does NOT re-run the pipeline or generate new analysis.
      It does NOT create a new L3 conclusion that could conflict with d.action.
    """
    q = question.lower()

    # --- Risk / thesis breakers ---
    if any(kw in q for kw in ("risk", "breaker", "break", "concern", "downside", "bear")):
        return _answer_risks(d)

    # --- Specific valuation-method questions (checked before generic valuation catch) ---
    # Triggers on named methods or "why expensive / cheap / overvalued / undervalued"
    # and "which method" / "what drives valuation".  Routes to the per-method breakdown
    # which explains the weighted combination rather than stopping at a single metric.
    _METHOD_KEYWORDS = (
        "p/e", "pe ratio", "pe multiple", "price-to-earnings", "price to earnings",
        "p/fcf", "price-to-fcf", "price to fcf", "fcf multiple",
        "ev/ebitda", "ev ebitda", "ebitda multiple", "enterprise value",
        # "expensive/cheap/overvalued/undervalued" as standalone words capture
        # "why is it expensive?", "considered expensive", "seems overvalued" etc.
        "expensive", "overvalued", "undervalued",
        "which method", "what method", "what drives", "drives valuation",
        "weighted", "what methods", "method breakdown", "method weight",
    )
    if any(kw in q for kw in _METHOD_KEYWORDS):
        return _answer_valuation_method(d, question)

    # --- Assumptions / fair value (generic) ---
    if any(kw in q for kw in ("assumption", "fair value", "intrinsic", "valuation", "dcf", "multiple", "ebitda")):
        return _answer_valuation(d)

    # --- What would change the conclusion ---
    if any(kw in q for kw in ("change", "different", "upgrade", "downgrade", "flip", "reconsider")):
        return _answer_what_would_change(d)

    # --- FCF/EPS reconciliation — 'explain the gap by component' (Phase 9.8) ---
    # Must be checked BEFORE the generic stale/data/gap catch-all, because
    # reconciliation questions mention "data" ("financial-statement data") and
    # "difference"/"gap" but are substantively about the EPS↔FCF bridge.
    # Trigger: "fcf" in question AND at least one reconciliation-specific term.
    _RECONCIL_TERMS = (
        "capex", "working capital", "depreciation", "d&a", "amortization",
        "amortisation", "tax", "reconcil", "decompose",
        "explain the difference", "explain the gap", "bridge", "line item",
        "financial-statement", "financial statement",
    )
    if "fcf" in q and any(kw in q for kw in _RECONCIL_TERMS):
        return _answer_fcf_reconciliation(d, question)

    # --- Stale data / uncertainty ---
    if any(kw in q for kw in ("stale", "uncertain", "data", "fresh", "old", "limitation", "gap")):
        return _answer_data_quality(d)

    # --- Confidence (check before generic "how/why" to avoid "how confident" mismatch) ---
    if any(kw in q for kw in ("confident", "confidence", "certain", "sure", "conviction")):
        return _answer_confidence(d)

    # --- Peer / comparable ---
    if any(kw in q for kw in ("peer", "comparable", "compare", "competitor", "relative")):
        return _answer_peers(d)

    # --- FCF / free-cash-flow as a financial metric (not as a valuation multiple) ---
    # "p/fcf" (valuation multiple) is already caught by _METHOD_KEYWORDS above.
    # This block catches FCF as a per-share financial metric: FCF/share vs EPS,
    # why they differ, how FCF is calculated.
    _FCF_METRIC_KEYWORDS = (
        "free cash flow", "free-cash-flow", "fcf/share", "fcf per share",
        "cash flow per share",
    )
    _fcf_in_q = "fcf" in q
    _fcf_context = _fcf_in_q and any(kw in q for kw in (
        "eps", "earnings per share", "per share", "calculat", "lower", "higher",
        "differ", "gap", "only", "while", "versus", " vs ", "explain", "why",
    ))
    if any(kw in q for kw in _FCF_METRIC_KEYWORDS) or _fcf_context:
        return _answer_fcf_eps(d, question)

    # --- Why this decision ---
    if any(kw in q for kw in ("why", "reason", "rationale", "explain", "how did", "how does")):
        return _answer_why(d)

    # --- Investment horizon / holding period ---
    # Catches questions like "does the recommendation change if I hold for 10 years?",
    # "what if I'm investing for 15 years?", "how does a long-term view change things?"
    if any(kw in q for kw in (
        "year", "years", "long-term", "long term", "buy and hold",
        "holding period", "investment horizon", "time horizon", "decade",
    )):
        return _answer_holding_horizon(d)

    # --- Growth / attractiveness / business segments ---
    # Catches questions like "aren't they growing?", "is the FMCG division growing?",
    # "does segment X make this more attractive?", "what about growth prospects?"
    if any(kw in q for kw in (
        "grow", "growth", "growing", "grew",
        "attractive", "attractiveness",
        "division", "segment", "business unit",
        "fmcg", "tech", "subsidiary",
    )):
        return _answer_growth_attractiveness(d)

    # Default: executive conclusion
    return (
        f"Based on the stored {d.ticker} analysis (date: {d.analysis_date}):\n\n"
        f"{d.executive_conclusion}\n\n"
        f"Ask me about: risks, assumptions, what would change the conclusion, "
        f"confidence, or stale data."
    )


# ---------------------------------------------------------------------------
# Follow-up answer builders — all read from structured assessment fields
# ---------------------------------------------------------------------------

def _answer_risks(d: InvestmentDecisionAssessment) -> str:
    parts = [f"Key risks and thesis breakers for {d.company_name} ({d.ticker}):\n"]

    if d.thesis_breakers:
        parts.append("THESIS BREAKERS:")
        for tb in d.thesis_breakers:
            likelihood = getattr(tb, "likelihood", "?")
            condition  = getattr(tb, "condition", str(tb))
            monitor    = getattr(tb, "monitoring_indicator", "")
            parts.append(f"  [{likelihood}] {condition}")
            if monitor:
                parts.append(f"         Monitor: {monitor}")
    if d.key_risks:
        parts.append("\nKEY RISKS (from quality & adversarial gates):")
        for r in d.key_risks[:5]:
            parts.append(f"  • {r}")
    if d.bear_case:
        parts.append(f"\nBEAR CASE:\n  {d.bear_case}")
    parts.append(
        f"\nThis analysis is from {d.analysis_date}. "
        f"[Decision-support only — no trades are executed.]"
    )
    return "\n".join(parts)


def _answer_fcf_reconciliation(d: InvestmentDecisionAssessment, question: str = "") -> str:
    """
    Dedicated FCF/EPS gap reconciliation handler (Phase 9.8 / 9.9).

    Attempts to bridge EPS → OCF/share → FCF/share using only stored assessment data.
    Each value is explicitly labelled:
      DIRECTLY OBSERVED  — stored in the IDA verbatim
      CALCULATED         — derived arithmetically from stored fields
      CANNOT RECONCILE   — requires data not stored in this assessment

    Phase 9.9 improvements:
      - Shows the normalization basis for BOTH EPS and FCF/share.
      - Warns prominently when EPS and FCF/share are from different periods
        (TTM vs multi-year average) rather than burying the mismatch as a footnote.
      - Uses persisted annual_ocf from the breakdown when available.

    Architecture boundary:
      Reads from InvestmentDecisionAssessment only.
      Does NOT fetch new data and does NOT invent values for D&A, WC, or taxes.
      If exact per-component attribution is impossible, says so explicitly and
      lists the missing line items instead of fabricating an explanation.
    """
    currency     = d.price_currency or ""
    parts        = [f"FCF/EPS RECONCILIATION for {d.company_name} ({d.ticker}):\n"]
    fcf_ps       = getattr(d, "fcf_per_share_used",      None)
    fcf_note     = getattr(d, "fcf_normalization_note",  "") or ""
    eps_val      = getattr(d, "eps_used_in_valuation",   None)
    eps_note     = getattr(d, "eps_normalization_note",  "") or ""
    breakdown    = getattr(d, "fcf_annual_breakdown",    None) or []
    shares_total = getattr(d, "fcf_shares_outstanding",  None)

    # ── SECTION 1: Directly observed values ──────────────────────────────────
    parts.append("DIRECTLY OBSERVED (stored in this assessment):")
    if eps_val is not None:
        parts.append(f"  EPS used in P/E valuation:          {currency} {eps_val:.2f}/share")
        if eps_note:
            parts.append(f"  EPS normalization basis:            {eps_note}")
    else:
        parts.append("  EPS used in valuation:               not stored")
    if fcf_ps is not None:
        parts.append(f"  FCF/share used in P/FCF valuation:  {currency} {fcf_ps:.2f}/share")
        if fcf_note:
            parts.append(f"  FCF/share derivation:               {fcf_note}")
    else:
        parts.append("  FCF/share used in valuation:         not stored")
    if eps_val is not None and fcf_ps is not None:
        gap = eps_val - fcf_ps
        parts.append(f"  Observed gap (EPS − FCF/share):     {currency} {gap:.2f}/share")

    # ── NORMALIZATION BASIS NOTE ──────────────────────────────────────────────
    # Phase 9.9b: compare the actual fiscal-year sets, not just text keywords.
    # A TTM-vs-multi-year mismatch is invalid as an economic bridge.
    # A multi-year EPS window that uses DIFFERENT years than the FCF window is
    # equally invalid.  Only identical year sets warrant ✓ SAME-PERIOD BASIS.
    if eps_val is not None and fcf_ps is not None:
        import re as _re

        # Parse year lists from normalization notes.
        # EPS note format (Phase 9.9b): "... years: FY2024, FY2025, FY2026"
        # FCF note format: "3yr avg FY2024–FY2026" or "3yr avg to 2026"
        def _parse_eps_years(note: str):
            """Return sorted list of int years from 'years: FY2024, FY2025, ...'"""
            m = _re.search(r"years:\s*(.+)$", note, _re.IGNORECASE)
            if not m:
                return []
            return sorted(int(y) for y in _re.findall(r"\d{4}", m.group(1)))

        def _parse_fcf_years(note: str, n_years: int = 3):
            """Return sorted list of int years from FCF normalization note."""
            # Try "FY2024–FY2026" range pattern first
            m_range = _re.search(r"FY(\d{4})[–\-]FY(\d{4})", note)
            if m_range:
                lo, hi = int(m_range.group(1)), int(m_range.group(2))
                return list(range(lo, hi + 1))
            # Try "3yr avg to YYYY"
            m_to = _re.search(r"(\d+)yr avg to (\d{4})", note, _re.IGNORECASE)
            if m_to:
                end = int(m_to.group(2))
                n   = int(m_to.group(1))
                return list(range(end - n + 1, end + 1))
            return []

        eps_years = _parse_eps_years(eps_note)
        fcf_years = _parse_fcf_years(fcf_note)

        eps_is_ttm = "ttm" in eps_note.lower() or not eps_note

        if eps_is_ttm:
            parts.append(
                "\n⚠ PERIOD MISMATCH: EPS is TTM (trailing 12 months) while FCF/share"
                " is a multi-year average.\n"
                f"  The {currency} {gap:.2f}/share gap reflects different normalization"
                " windows, not a same-period earnings-to-cash bridge.\n"
                "  Treat this difference as indicative only, not as a precise"
                " economic reconciliation."
            )
        elif eps_years and fcf_years and set(eps_years) == set(fcf_years):
            yr_str = f"FY{min(eps_years)}–FY{max(eps_years)}"
            parts.append(
                f"\n✓ SAME-PERIOD BASIS: both EPS and FCF/share cover {yr_str} "
                f"({len(eps_years)}-year average).\n"
                f"  The {currency} {gap:.2f}/share gap is a valid same-period"
                f" EPS → FCF/share comparison."
            )
        elif eps_years and fcf_years and set(eps_years) != set(fcf_years):
            eps_only = sorted(set(eps_years) - set(fcf_years))
            fcf_only = sorted(set(fcf_years) - set(eps_years))
            diff_parts = []
            if eps_only:
                diff_parts.append(f"EPS includes {[f'FY{y}' for y in eps_only]} not in FCF")
            if fcf_only:
                diff_parts.append(f"FCF includes {[f'FY{y}' for y in fcf_only]} not in EPS")
            parts.append(
                f"\n⚠ PERIOD MISMATCH: EPS and FCF/share cover different fiscal years.\n"
                f"  EPS years: {[f'FY{y}' for y in eps_years]}\n"
                f"  FCF years: {[f'FY{y}' for y in fcf_years]}\n"
                f"  Difference: {'; '.join(diff_parts)}.\n"
                f"  The {currency} {gap:.2f}/share gap is not a valid same-period bridge."
            )
        else:
            # Could not parse year sets; fall back to generic multi-year note
            parts.append(
                f"\n  Both EPS and FCF/share are multi-year averages. "
                f"Gap of {currency} {gap:.2f}/share is driven by the structural"
                f" difference between accounting income and operating cash flow."
            )

    # ── SECTION 2: Calculated from annual OCF / capex / FCF breakdown ────────
    have_breakdown = bool(breakdown and shares_total)
    if have_breakdown:
        recent = [r for r in breakdown if r.get("fcf") is not None][:3]
        if recent:
            # averages — guard against missing sub-fields
            ocf_vals   = [r["ocf"]   for r in recent if r.get("ocf")   is not None]
            capex_vals = [r["capex"] for r in recent if r.get("capex") is not None]
            avg_ocf    = sum(ocf_vals)   / len(ocf_vals)   if ocf_vals   else None
            avg_capex  = sum(capex_vals) / len(capex_vals) if capex_vals else None
            avg_fcf    = sum(r["fcf"] for r in recent) / len(recent)
            yrs        = ", ".join(str(r["year"]) for r in recent)

            ocf_ps_c   = avg_ocf   / shares_total if avg_ocf   is not None else None
            capex_ps_c = abs(avg_capex) / shares_total if avg_capex is not None else None
            fcf_ps_c   = avg_fcf   / shares_total

            parts.append(
                f"\nCALCULATED (from persisted annual OCF/capex/FCF,"
                f" {len(recent)}-yr avg: {yrs}):"
            )
            parts.append(
                f"  {'Year':<6}  {'OCF':>14}  {'Capex':>14}  {'FCF':>14}"
            )
            parts.append(f"  {'─'*6}  {'─'*14}  {'─'*14}  {'─'*14}")
            for row in breakdown:
                yr    = row.get("year", "?")
                ocf_v = row.get("ocf")
                cap_v = row.get("capex")
                fcf_v = row.get("fcf")
                ocf_s   = f"{currency} {ocf_v/1e9:.1f}B"       if ocf_v  is not None else "N/A"
                capex_s = f"−{currency} {abs(cap_v)/1e9:.1f}B" if cap_v  is not None else "N/A"
                fcf_s   = f"{currency} {fcf_v/1e9:.1f}B"       if fcf_v  is not None else "N/A"
                parts.append(f"  {yr:<6}  {ocf_s:>14}  {capex_s:>14}  {fcf_s:>14}")

            parts.append(
                f"\n  Per-share ({len(recent)}-yr avg, shares = {shares_total/1e9:.3f}B):"
            )
            if ocf_ps_c is not None:
                parts.append(f"  Average OCF/share:    {currency} {ocf_ps_c:.2f}/share")
            if capex_ps_c is not None:
                parts.append(
                    f"  Average capex/share:  {currency} {capex_ps_c:.2f}/share"
                    f"  (deducted OCF → FCF)"
                )
            parts.append(f"  Calculated FCF/share: {currency} {fcf_ps_c:.2f}/share")
            if fcf_ps is not None:
                diff_pct = abs(fcf_ps_c - fcf_ps) / max(abs(fcf_ps), 0.01) * 100
                if diff_pct < 5:
                    parts.append(
                        f"  ✓ Consistent with stored FCF/share: {currency} {fcf_ps:.2f}"
                    )
                else:
                    parts.append(
                        f"  Note: stored FCF/share = {currency} {fcf_ps:.2f}"
                        f" (normalization period or rounding differs)"
                    )

            # Partial gap attribution: EPS → OCF step vs OCF → FCF step
            if eps_val is not None and ocf_ps_c is not None and capex_ps_c is not None:
                eps_to_ocf  = ocf_ps_c - eps_val    # negative = OCF below EPS
                ocf_to_fcf  = -capex_ps_c           # always negative
                total_bridg = eps_to_ocf + ocf_to_fcf
                stored_gap  = -(fcf_ps - eps_val) if fcf_ps is not None else None

                parts.append("\nPARTIAL GAP ATTRIBUTION (from stored data):")
                parts.append(
                    f"  Step 1 — EPS ({currency} {eps_val:.2f}) → OCF/share"
                    f" ({currency} {ocf_ps_c:.2f}):  {eps_to_ocf:+.2f}/share"
                )
                parts.append(
                    f"           Driver: net of D&A add-back, working-capital"
                    f" movements, other non-cash items"
                )
                parts.append(
                    f"           (individual sub-components NOT stored — see below)"
                )
                parts.append(
                    f"  Step 2 — OCF/share ({currency} {ocf_ps_c:.2f}) → FCF/share"
                    f" ({currency} {fcf_ps_c:.2f}):  {ocf_to_fcf:+.2f}/share"
                )
                parts.append(
                    f"           Driver: capex deduction"
                    f" (−{currency} {capex_ps_c:.2f}/share, from stored breakdown)"
                )
                parts.append(f"  {'─'*58}")
                parts.append(
                    f"  Calculated EPS → FCF bridge:  {total_bridg:+.2f}/share"
                )
                if stored_gap is not None:
                    diff = abs(total_bridg - stored_gap)
                    if diff < 0.15:
                        parts.append(
                            f"  ✓ Calculated bridge ({total_bridg:+.2f}/share) matches"
                            f" observed gap of {stored_gap:+.2f}/share (within rounding)"
                        )
                    else:
                        # Only flag a residual mismatch if not already explained by
                        # a period difference (which is called out in the basis note above)
                        parts.append(
                            f"  Residual: calculated bridge ({total_bridg:+.2f}/share)"
                            f" differs from observed gap ({stored_gap:+.2f}/share)."
                            f" Likely due to normalization-period or rounding differences"
                            f" — see PERIOD BASIS note above."
                        )

    # ── SECTION 3: Cannot reconcile ──────────────────────────────────────────
    parts.append("\nCANNOT RECONCILE FROM STORED DATA:")
    if have_breakdown and shares_total:
        parts.append(
            "  The stored data splits the EPS → FCF/share bridge into two steps:\n"
            "    (a) EPS → OCF/share  — total shown, but cannot be decomposed into:\n"
            "        • D&A (depreciation & amortisation) per share\n"
            "        • Working-capital changes (inventory, receivables, payables) per share\n"
            "        • Tax-timing differences and provisions per share\n"
            "        • Other non-cash adjustments per share\n"
            "    (b) OCF/share → FCF/share  — capex deduction, computable from stored data\n"
            "\n"
            "  An exact per-component attribution of the EPS/FCF gap cannot be confirmed\n"
            "  without the above sub-items, which are not stored in this assessment."
        )
    else:
        parts.append(
            "  The annual OCF/capex/FCF series is not stored in this assessment.\n"
            "  Without it, none of OCF/share, capex/share, or the EPS → OCF step\n"
            "  can be shown from currently available data.\n"
            "\n"
            "  Missing for a full reconciliation:\n"
            "    • Annual Operating Cash Flow — not available (not stored)\n"
            "    • Annual Capital Expenditure — not available (not stored)\n"
            "    • D&A per share — not extracted from financial statements\n"
            "    • Working-capital changes per share — not extracted\n"
            "    • Tax-timing differences per share — not extracted"
        )

    # ── SECTION 4: Structural explanation (always, clearly labelled general) ─
    parts.append("\nSTRUCTURAL EXPLANATION (general mechanism — not {}-specific data):".format(
        d.ticker
    ))
    parts.append(
        "  EPS  = Net income ÷ diluted shares\n"
        "  FCF  = Operating Cash Flow (OCF) − Capital Expenditure (Capex)\n"
        "  FCF/share = FCF ÷ diluted shares\n"
        "\n"
        "  EPS → OCF: add back non-cash charges, adjust for working capital\n"
        "    + D&A             (non-cash, raises OCF above net income)\n"
        "    ± WC changes      (can increase or decrease OCF)\n"
        "    ± Tax timing etc. (can increase or decrease OCF)\n"
        "\n"
        "  OCF → FCF: deduct capital expenditure\n"
        "    − Capex           (cash outflow, lowers FCF below OCF)\n"
        "\n"
        "  The relative size of capex vs the D&A add-back drives the gap:\n"
        "  if capex is not fully offset by D&A, FCF/share will fall below EPS.\n"
        "  Working-capital movements can widen or narrow the gap further.\n"
        "  No single item can be assumed to explain the full gap without\n"
        "  the per-share line-item data."
    )

    parts.append(
        f"\n[Source: stored {d.ticker} assessment (date: {d.analysis_date})."
        f" No new financial data was generated."
        f" Structural explanation is general and not company-specific.]"
    )
    return "\n".join(parts)


def _answer_fcf_eps(d: InvestmentDecisionAssessment, question: str = "") -> str:
    """
    Answer questions about FCF vs EPS: per-share values, why they differ, how FCF is calculated.

    Architecture boundary:
      Reads only from the stored InvestmentDecisionAssessment.
      Priority order:
        1. Phase 9.6 annual breakdown (fcf_annual_breakdown, fcf_shares_outstanding)
           → full OCF / capex / FCF chain shown when available
        2. Phase 9.5 provenance (fcf_per_share_used, eps_used_in_valuation)
           → stored valuation inputs shown when breakdown is absent
        3. Generic structural explanation — always shown; clearly labelled as general
      Capex is shown as a data fact when present in the breakdown.
      The specific per-share contribution of capex vs WC vs tax is NOT
      claimed unless explicitly derivable from the stored data.
      Does NOT invent any financial values.
    """
    currency = d.price_currency or ""
    parts = [f"FCF vs EPS for {d.company_name} ({d.ticker}):\n"]

    # ── Retrieve Phase 9.5/9.6 fields ───────────────────────────────────────
    fcf_ps       = getattr(d, "fcf_per_share_used", None)
    fcf_note     = getattr(d, "fcf_normalization_note", "") or ""
    eps_val      = getattr(d, "eps_used_in_valuation", None)
    breakdown    = getattr(d, "fcf_annual_breakdown", None) or []
    shares_total = getattr(d, "fcf_shares_outstanding", None)

    # ── Section 1: Annual calculation chain (Phase 9.6) ─────────────────────
    if breakdown:
        parts.append(f"FCF CALCULATION CHAIN — {d.ticker} (from financial statements):")
        parts.append(
            f"  {'Year':<6}  {'OCF':>10}  {'Capex':>10}  {'FCF':>10}"
        )
        parts.append(f"  {'─'*6}  {'─'*10}  {'─'*10}  {'─'*10}")
        for row in breakdown:
            yr    = row.get("year", "?")
            fcf_v = row.get("fcf")
            cap_v = row.get("capex")
            ocf_v = row.get("ocf")
            ocf_s   = f"{currency} {ocf_v/1e9:.1f}B"  if ocf_v  is not None else "N/A"
            capex_s = f"−{currency} {abs(cap_v)/1e9:.1f}B" if cap_v is not None else "N/A"
            fcf_s   = f"{currency} {fcf_v/1e9:.1f}B"  if fcf_v  is not None else "N/A"
            parts.append(f"  {yr:<6}  {ocf_s:>10}  {capex_s:>10}  {fcf_s:>10}")

        # 3-yr average using the 3 most recent rows (already sorted desc)
        recent = [r for r in breakdown if r.get("fcf") is not None][:3]
        if recent:
            avg_fcf = sum(r["fcf"] for r in recent) / len(recent)
            yrs_str = ", ".join(str(r["year"]) for r in recent)
            parts.append(
                f"\n  {len(recent)}-year avg FCF ({yrs_str}):  {currency} {avg_fcf/1e9:.1f}B"
            )
            if shares_total:
                shares_b = shares_total / 1e9
                computed_fcf_ps = avg_fcf / shares_total
                parts.append(
                    f"  Shares outstanding:                {shares_b:.3f}B"
                )
                parts.append(
                    f"  FCF/share  =  {currency} {avg_fcf/1e9:.1f}B ÷ {shares_b:.3f}B"
                    f"  =  {currency} {computed_fcf_ps:.2f}"
                )
                # Cross-check against stored value
                if fcf_ps is not None:
                    diff_pct = abs(computed_fcf_ps - fcf_ps) / max(abs(fcf_ps), 0.01) * 100
                    if diff_pct < 5:
                        parts.append(
                            f"  ✓ Consistent with stored valuation engine value:"
                            f" {currency} {fcf_ps:.2f}/share"
                        )
                    else:
                        parts.append(
                            f"  Note: stored valuation engine used {currency} {fcf_ps:.2f}/share"
                            f" (different normalization period or rounding)."
                        )
                if fcf_note:
                    parts.append(f"  Derivation note: {fcf_note}")

        # EPS comparison
        if eps_val is not None and fcf_ps is not None:
            gap = eps_val - fcf_ps
            parts.append(
                f"\n  EPS used in P/E valuation:  {currency} {eps_val:.2f}"
                f"  (may be multi-year normalised average)"
            )
            parts.append(
                f"  FCF/share (P/FCF method):   {currency} {fcf_ps:.2f}"
            )
            parts.append(
                f"  Gap:                        {currency} {gap:.2f}/share"
            )
            parts.append(
                "\n  INTERPRETATION: The annual data above shows OCF and total capex\n"
                "  deducted each year. Capex is visible in the chain and is one factor\n"
                "  in the OCF → FCF step. However, the stored assessment does not\n"
                "  break out how much of the {}{:.2f}/share gap is attributable to\n"
                "  capex vs working-capital movements vs tax timing vs D&A add-backs.\n"
                "  All four factors contribute; their relative sizes require per-share\n"
                "  decomposition not stored in this assessment.".format(currency, gap)
            )
        elif eps_val is not None:
            parts.append(
                f"\n  EPS used in P/E valuation:  {currency} {eps_val:.2f}"
            )

    # ── Section 2: Phase 9.5 provenance (fallback when no annual breakdown) ──
    elif fcf_ps is not None or eps_val is not None:
        parts.append(f"STORED VALUATION METRICS FOR {d.ticker}:")
        if fcf_ps is not None:
            parts.append(
                f"  FCF/share used in P/FCF valuation:  {currency} {fcf_ps:.2f}"
            )
            if fcf_note:
                parts.append(f"  Derivation: {fcf_note}")
        if eps_val is not None:
            parts.append(
                f"  EPS used in P/E valuation:           {currency} {eps_val:.2f}"
                "\n  (This may be a multi-year normalised average, not TTM EPS alone.)"
            )
        if fcf_ps is not None and eps_val is not None:
            gap = eps_val - fcf_ps
            parts.append(
                f"\n  Observed gap:  {currency} {eps_val:.2f} EPS  −"
                f"  {currency} {fcf_ps:.2f} FCF/share  =  {currency} {gap:.2f}/share"
            )
            parts.append(
                "  The stored assessment does not contain the annual OCF / capex / FCF\n"
                "  series needed to show the calculation chain. The structural\n"
                "  explanation below covers the typical drivers of this gap."
            )
    else:
        parts.append(
            "STORED VALUATION METRICS: Not available.\n"
            "  No FCF/share, EPS, or annual breakdown is stored for this assessment.\n"
            "  The generic structural explanation below applies."
        )

    # ── Section 3: Structural explanation (always shown, labelled as general) ──
    parts.append("\nSTRUCTURAL DIFFERENCE: EPS vs FREE CASH FLOW")
    parts.append(
        "  EPS (Earnings Per Share)  = Net income ÷ diluted shares outstanding\n"
        "  FCF (Free Cash Flow)      = Operating Cash Flow − Capital Expenditure\n"
        "  FCF/share                 = FCF ÷ diluted shares outstanding\n"
        "\n"
        "EPS and FCF/share commonly diverge because:\n"
        "  • Capex reduces FCF immediately but is capitalised and depreciated over\n"
        "    years in the income statement — so capex reduces FCF more than EPS\n"
        "    in capital-spending years.\n"
        "  • Working capital movements (inventory, receivables, payables) flow\n"
        "    through Operating Cash Flow but do not affect EPS.\n"
        "  • Non-cash charges (D&A) are added back in OCF but already deducted\n"
        "    in net income — this partially offsets the capex drag on FCF.\n"
        "  • Tax timing and provisions can widen or narrow the gap further.\n"
        "\n"
        "None of these factors alone determines the size of the gap — the annual\n"
        "data above (when available) shows what actually happened at the OCF and\n"
        "capex level, but per-share attribution to individual drivers requires\n"
        "detailed line-item decomposition beyond what is stored here."
    )

    # ── Supplementary: assumptions / method summary ──────────────────────────
    eps_fcf_assumptions = [
        a for a in (d.key_assumptions or [])
        if any(kw in a.lower() for kw in (
            "eps", "earnings per share", "fcf", "free cash flow", "cash flow"
        ))
    ]
    if eps_fcf_assumptions:
        parts.append("\nKEY ASSUMPTIONS (stored):")
        for a in eps_fcf_assumptions:
            parts.append(f"  • {a}")

    pfcf_lines = [
        line for line in (getattr(d, "per_method_valuation_summary", None) or [])
        if "fcf" in line.lower()
    ]
    if pfcf_lines:
        parts.append("\nP/FCF METHOD SUMMARY (implied share price ranges, not raw FCF):")
        for line in pfcf_lines:
            parts.append(f"  {line}")

    from analytics.decision.decision_models import DecisionEvidenceItem  # noqa: F401
    fcf_evidence = [
        e for e in (d.supporting_evidence or [])
        if any(kw in e.observation.lower() for kw in (
            "eps", "fcf", "free cash flow", "earnings per share", "cash flow"
        ))
    ]
    if fcf_evidence:
        parts.append("\nSUPPORTING EVIDENCE REFERENCING FCF/EPS:")
        for e in fcf_evidence[:3]:
            parts.append(f"  [{e.source_phase}] {e.observation}")

    # ── Valuation context ────────────────────────────────────────────────────
    if d.valuation_conclusion:
        parts.append(f"\nVALUATION CONTEXT:\n  {d.valuation_conclusion}")

    parts.append(
        f"\n[Source: stored {d.ticker} assessment (date: {d.analysis_date})."
        f" No new financial data was generated.]"
    )
    return "\n".join(parts)


def _parse_method_values(method_lines, prefix):
    """
    Extract (bear, mid, bull) implied fair values from a per-method valuation summary line.

    Expects lines of the form:
        "P/FCF: bear INR 184.17 | mid INR 216.67 | bull INR 249.17  [reliability: MEDIUM, ...]"
        "Normalised P/E: bear INR 242.51 | mid INR 285.30 | bull INR 328.10  [...]"

    Parameters
    ----------
    method_lines : list[str] — the per_method_valuation_summary lines from the IDA
    prefix       : str      — the prefix to match (case-insensitive, e.g. "p/fcf", "normalised p/e")

    Returns
    -------
    (bear, mid, bull) as floats, or None if the prefix is not found / values cannot be parsed.
    """
    import re
    for line in (method_lines or []):
        if line.strip().lower().startswith(prefix.lower()):
            m = re.search(
                r'bear\s+\S+\s+([\d.]+)\s*\|\s*mid\s+\S+\s+([\d.]+)\s*\|\s*bull\s+\S+\s+([\d.]+)',
                line, re.IGNORECASE,
            )
            if m:
                return float(m.group(1)), float(m.group(2)), float(m.group(3))
    return None


def _answer_valuation_method(d: InvestmentDecisionAssessment, question: str = "") -> str:
    """
    Answer a specific valuation-method question (P/E, EV/EBITDA, P/FCF, "why expensive" …).

    Uses per_method_valuation_summary to surface the contribution of each applicable method
    and explains why a single metric (e.g. "P/E is only 18x") may not determine the conclusion
    on its own — the WAIT/WATCH zone is driven by the weighted aggregate, not one method.

    Architecture boundary: reads stored assessment data only — no new calculations.
    """
    q = question.lower()
    parts = [f"Valuation method breakdown for {d.company_name} ({d.ticker}):\n"]

    # ── Identify which method the user is asking about ──────────────────────
    asked_pe    = any(kw in q for kw in ("p/e", "pe ratio", "pe multiple", "price-to-earnings", "price to earnings"))
    asked_ev    = any(kw in q for kw in ("ev/ebitda", "ev ebitda", "ebitda multiple", "enterprise value"))
    asked_pfcf  = any(kw in q for kw in ("p/fcf", "price-to-fcf", "price to fcf", "fcf multiple"))
    asked_why   = any(kw in q for kw in ("expensive", "overvalued", "undervalued", "cheap"))

    # ── Core explanation header ──────────────────────────────────────────────
    action_label = d.action.value if d.action else "WATCH"
    val_label    = d.valuation_attractiveness_label or ""

    if asked_pe and not asked_ev and not asked_pfcf:
        parts.append(
            f"P/E is one of several valuation methods used for {d.ticker}. "
            f"It is not the sole determinant of the {action_label} conclusion. "
            f"The final fair value estimate is a weighted combination of all applicable methods — "
            f"each with a reliability weight that reflects data quality and method applicability. "
            f"A lower-weight method with a price near or above fair value does not override "
            f"higher-weight methods that point to a lower implied value."
        )
    elif asked_ev:
        parts.append(
            f"EV/EBITDA is a key method for {d.ticker} — typically assigned higher reliability weight "
            f"when EBITDA data is available. It converts the enterprise-level multiple into an "
            f"equity-per-share value via the EV bridge: implied equity = EBITDA × multiple − debt + cash."
        )
    elif asked_pfcf:
        # ── Phase 9.7: detailed P/FCF calculation chain ──────────────────────
        currency     = d.price_currency or ""
        fcf_ps       = getattr(d, "fcf_per_share_used", None)
        price        = d.current_price
        method_lines = getattr(d, "per_method_valuation_summary", None) or []
        pfcf_vals    = _parse_method_values(method_lines, "p/fcf")
        pe_vals      = _parse_method_values(method_lines, "normalised p/e")
        if pe_vals is None:
            pe_vals  = _parse_method_values(method_lines, "p/e")

        parts.append(
            f"P/FCF (Price-to-Free-Cash-Flow) for {d.company_name} ({d.ticker})\n"
            f"This method capitalises free cash flow per share to derive an implied equity value."
        )

        # ── Current P/FCF ratio ───────────────────────────────────────────────
        if fcf_ps is not None and price is not None:
            current_pfcf = price / fcf_ps
            parts.append(
                f"\nCURRENT P/FCF RATIO (derived from stored assessment):"
                f"\n  FCF/share used by engine:  {currency} {fcf_ps:.2f}"
                f"\n  Current market price:       {currency} {price:.2f}"
                f"\n  Current P/FCF:              {price:.2f} ÷ {fcf_ps:.2f}  =  {current_pfcf:.1f}×"
            )
        elif fcf_ps is None:
            parts.append(
                "\nFCF/share is not stored in this assessment; "
                "the current P/FCF ratio cannot be computed."
            )

        # ── Implied multiples and midpoint calculation ────────────────────────
        if pfcf_vals is not None:
            p_bear, p_mid, p_bull = pfcf_vals
            if fcf_ps is not None:
                bear_m = p_bear / fcf_ps
                mid_m  = p_mid  / fcf_ps
                bull_m = p_bull / fcf_ps
                parts.append(
                    f"\nP/FCF MULTIPLES AND IMPLIED FAIR VALUES"
                    f"\n(multiples derived from stored fair values ÷ FCF/share — not hard-coded):"
                    f"\n  Bear: {currency} {fcf_ps:.2f} × {bear_m:.0f}×  =  {currency} {p_bear:.2f}"
                    f"\n  Mid:  {currency} {fcf_ps:.2f} × {mid_m:.0f}×   =  {currency} {p_mid:.2f}"
                    f"  ← base-case fair value"
                    f"\n  Bull: {currency} {fcf_ps:.2f} × {bull_m:.0f}×  =  {currency} {p_bull:.2f}"
                )
            else:
                parts.append(
                    f"\nP/FCF FAIR VALUE RANGE (from stored valuation summary):"
                    f"\n  Bear: {currency} {p_bear:.2f}  |  Mid: {currency} {p_mid:.2f}"
                    f"  |  Bull: {currency} {p_bull:.2f}"
                )

            # ── Price vs midpoint, two framings ──────────────────────────────
            if price is not None:
                gap          = price - p_mid
                pct_vs_fv    = gap / p_mid  * 100
                pct_vs_price = gap / price  * 100
                direction    = "above" if gap > 0 else "below"
                parts.append(
                    f"\nCURRENT PRICE vs P/FCF MIDPOINT:"
                    f"\n  Current price:    {currency} {price:.2f}"
                    f"\n  P/FCF midpoint:   {currency} {p_mid:.2f}"
                    f"\n  Gap:              {currency} {abs(gap):.2f} ({direction} midpoint)"
                    f"\n"
                    f"\n  Two ways to frame the same gap (different denominators):"
                    f"\n  • {abs(pct_vs_fv):.1f}% above P/FCF fair value"
                    f"   (gap ÷ fair value:   {abs(gap):.2f} ÷ {p_mid:.2f})"
                    f"\n  • {abs(pct_vs_price):.1f}% of current price"
                    f"       (gap ÷ market price: {abs(gap):.2f} ÷ {price:.2f})"
                    f"\n"
                    f"\n  P/FCF therefore views {currency} {price:.2f} as"
                    f" {abs(pct_vs_fv):.1f}% above its midpoint fair value of {currency} {p_mid:.2f}."
                )

        elif price is not None:
            parts.append(
                "\nP/FCF bear/mid/bull values are not stored in this assessment. "
                "Re-run the analysis with valuation inputs to see the full breakdown."
            )

        # ── P/E comparison ────────────────────────────────────────────────────
        if pfcf_vals is not None and pe_vals is not None:
            _pb, _pm, _pbull = pfcf_vals
            pe_bear, pe_mid, pe_bull = pe_vals
            eps_val = getattr(d, "eps_used_in_valuation", None)
            parts.append(
                f"\nWHY P/FCF SHOWS A LOWER FAIR VALUE THAN P/E:"
                f"\n  P/FCF midpoint:  {currency} {_pm:.2f}"
                f"\n  P/E midpoint:    {currency} {pe_mid:.2f}"
            )
            if price is not None:
                pfcf_pct = (price - _pm)    / _pm    * 100
                pe_pct   = (price - pe_mid) / pe_mid * 100
                pfcf_dir = "above" if pfcf_pct > 0 else "below"
                pe_dir   = "above" if pe_pct   > 0 else "below"
                parts.append(
                    f"\n  Current price ({currency} {price:.2f}) vs P/FCF mid: "
                    f"{abs(pfcf_pct):.1f}% {pfcf_dir}"
                    f"\n  Current price ({currency} {price:.2f}) vs P/E mid:   "
                    f"{abs(pe_pct):.1f}% {pe_dir}"
                    f"\n\n  P/E midpoint is closer to the current price than P/FCF midpoint."
                )
            if fcf_ps is not None and eps_val is not None:
                parts.append(
                    f"\n  STRUCTURAL REASON:"
                    f"\n  P/FCF uses FCF/share ({currency} {fcf_ps:.2f});"
                    f" P/E uses normalised EPS ({currency} {eps_val:.2f})."
                    f"\n  EPS is higher than FCF/share because EPS does not deduct the full cash"
                    f"\n  cost of capex in the year it is spent — depreciation spreads the book"
                    f"\n  charge over many years, while FCF deducts actual capex cash outflow"
                    f"\n  immediately. The same market multiple applied to a lower per-share"
                    f"\n  metric produces a lower implied fair value."
                )
            elif fcf_ps is not None:
                parts.append(
                    f"\n  STRUCTURAL REASON:"
                    f"\n  P/FCF uses FCF/share ({currency} {fcf_ps:.2f}), which is lower than EPS."
                    f"\n  The same market multiple applied to a lower per-share metric produces"
                    f"\n  a lower implied fair value."
                )
    elif asked_why:
        parts.append(
            f"The {val_label or action_label} conclusion is driven by the weighted average of all "
            f"applicable valuation methods — not by any single metric. "
            f"A method like P/E may appear moderate (e.g. ~18x) while other methods "
            f"(EV/EBITDA, P/FCF, DCF) point to a lower implied value, pulling the weighted "
            f"average below the current price."
        )
    else:
        parts.append(
            f"The {action_label} conclusion reflects the weighted combination of all applicable "
            f"valuation methods. Each method is assigned a reliability weight (HIGH=1.0, "
            f"MEDIUM=0.6, LOW=0.3) and a bear/mid/bull implied value range."
        )

    # ── Per-method breakdown ─────────────────────────────────────────────────
    method_lines = getattr(d, "per_method_valuation_summary", None)
    if method_lines:
        parts.append("\nPER-METHOD FAIR VALUE BREAKDOWN:")
        for line in method_lines:
            parts.append(f"  {line}")
        parts.append(
            f"\nThe 'Weighted average' line above is the base fair value used to classify "
            f"the accumulation zone. When the current price exceeds the weighted average base "
            f"fair value, the zone is WAIT and valuation attractiveness is NEGATIVE."
        )
    else:
        # No per-method data stored — explain why without fabricating values
        parts.append(
            "\nPer-method breakdown is not available in this stored assessment. "
            "To see the full method breakdown, re-run the analysis — the valuation "
            "transparency data is populated when valuation inputs are present."
        )

    # ── Valuation conclusion from assessment ─────────────────────────────────
    if d.valuation_conclusion:
        parts.append(f"\nVALUATION CONCLUSION:")
        parts.append(f"  {d.valuation_conclusion}")

    # ── Key assumptions (up to 4) ────────────────────────────────────────────
    if d.key_assumptions:
        parts.append("\nKEY ASSUMPTIONS BEHIND THE METHODS:")
        for a in d.key_assumptions[:4]:
            if a:
                parts.append(f"  • {a}")

    parts.append(
        f"\n[The per-method values are estimates, not price targets. "
        f"Reliability weights reflect data quality, not conviction. "
        f"Analysis date: {d.analysis_date}.]"
    )
    return "\n".join(parts)


def _answer_valuation(d: InvestmentDecisionAssessment) -> str:
    parts = [f"Valuation detail for {d.company_name} ({d.ticker}):\n"]
    parts.append(d.valuation_conclusion)

    # Per-method breakdown (Phase 9.4)
    if getattr(d, "per_method_valuation_summary", None):
        parts.append("\nPER-METHOD FAIR VALUE BREAKDOWN:")
        for line in d.per_method_valuation_summary:
            parts.append(f"  {line}")

    fv = _fair_value_text(d)
    if fv:
        parts.append(f"\n{fv}")

    if d.key_assumptions:
        parts.append("\nKEY VALUATION ASSUMPTIONS:")
        for a in d.key_assumptions[:6]:
            if a:
                parts.append(f"  • {a}")

    parts.append(f"\nValuation confidence embedded in final confidence: {d.decision_confidence.value}")
    parts.append(
        f"\n[The fair-value range is an estimate, not a target price. "
        f"It is derived from Phase 5 valuation methods applied to the data as of {d.analysis_date}.]"
    )
    return "\n".join(parts)


def _answer_what_would_change(d: InvestmentDecisionAssessment) -> str:
    parts = [f"What would change the conclusion for {d.company_name} ({d.ticker}):\n"]
    if d.what_would_change_conclusion:
        parts.append(d.what_would_change_conclusion)
    if d.what_would_change_decision:
        parts.append("\nSpecific change triggers:")
        for item in d.what_would_change_decision[:6]:
            parts.append(f"  • {item}")
    parts.append(
        f"\n[Current action: {d.action.value}. "
        f"Qualitative view: {d.qualitative_investment_view}.]"
    )
    return "\n".join(parts)


def _answer_data_quality(d: InvestmentDecisionAssessment) -> str:
    parts = [f"Data quality and freshness for {d.company_name} ({d.ticker}):\n"]

    freshness = _freshness_status(d)
    parts.append(f"Overall freshness:  {freshness}")

    if d.data_freshness_cap_applied:
        parts.append("Confidence cap:     Applied — one or more inputs are STALE.")
    if d.price_suppression_applied:
        parts.append(
            "Price suppression:  Active — transactional action suppressed to WATCH_PENDING_DATA\n"
            "                    because the market price is STALE or UNKNOWN."
        )

    if d.data_freshness:
        stale = d.data_freshness.get("stale_inputs", [])
        if stale:
            parts.append(f"\nStale inputs:  {', '.join(stale)}")
        refresh = d.data_freshness.get("refresh_priorities", [])
        if refresh:
            parts.append("\nRefresh priorities:")
            for r in refresh[:4]:
                parts.append(f"  • {r}")

    if d.data_quality_limitations:
        parts.append("\nData quality limitations:")
        for lim in d.data_quality_limitations[:4]:
            parts.append(f"  • {lim}")
    if d.research_gaps:
        parts.append("\nResearch gaps:")
        for gap in d.research_gaps[:4]:
            parts.append(f"  • {gap}")

    return "\n".join(parts)


def _answer_confidence(d: InvestmentDecisionAssessment) -> str:
    parts = [
        f"Confidence for {d.company_name} ({d.ticker}): {d.decision_confidence.value}\n"
    ]
    if d.data_freshness_cap_applied:
        parts.append(
            "Confidence is capped at LOW because one or more critical data inputs are STALE.\n"
            "The investment thesis quality may warrant higher confidence with fresh data."
        )
    parts.append(
        f"\nThe confidence level reflects the quality of evidence across all analytical gates:\n"
        f"  Gate 1 (Understanding), Gate 2 (Quality), Gate 3 (Valuation),\n"
        f"  Gate 4 (Portfolio context), Gate 5 (Adversarial challenge).\n"
        f"\nFinal action: {d.action.value}  |  Qualitative view: {d.qualitative_investment_view}"
    )
    return "\n".join(parts)


def _answer_peers(d: InvestmentDecisionAssessment) -> str:
    parts = [f"Peer / comparable information for {d.company_name} ({d.ticker}):\n"]
    # Peer transparency is on the valuation assessment, not the decision.
    # We surface what the decision assessment knows.
    parts.append(
        "The peer data status is recorded in the valuation assessment (Phase 5).\n"
        "If peer_valuation_result was NOT_PERFORMED, no live peer data was available\n"
        "and any EV/EBITDA multiple used is a configured assumption, not derived from\n"
        "a named peer group. The agent does not invent peer comparisons.\n"
        "\nTo see full peer transparency details, inspect:\n"
        "  valuation.peer_transparency()  — returns peer_valuation_status, peers_used,\n"
        "  ev_ebitda_assumption, and source."
    )
    return "\n".join(parts)


def _answer_holding_horizon(d: InvestmentDecisionAssessment) -> str:
    """
    Answer questions about the effect of a long holding horizon (10+ years).

    Architecture boundary:
      Reads only from the stored InvestmentDecisionAssessment.
      Does NOT re-run the pipeline, does NOT invent new research.
      Explicitly separates two distinct questions:
        A. Does the business thesis hold over a 10+ year horizon?
        B. Does the current valuation / entry timing change with a longer horizon?
    """
    parts = [
        f"Effect of a long-term (10+ year) holding horizon on {d.company_name} ({d.ticker}):\n"
    ]

    # -----------------------------------------------------------------------
    # A. Business / thesis dimension
    # -----------------------------------------------------------------------
    parts.append("─── A. BUSINESS THESIS (10+ year view) ─────────────────────────")

    thesis_text = d.business_thesis or d.why_attractive_or_unattractive or ""
    if thesis_text:
        parts.append(
            "The stored business thesis is the primary input here. A longer holding period\n"
            "reduces sensitivity to short-term price moves and amplifies the compounding\n"
            "of any durable competitive advantage (moat) identified in the assessment.\n"
        )
        parts.append(f"Stored thesis:\n  {thesis_text}")
    else:
        parts.append(
            "No business thesis is stored in this assessment.\n"
            "To evaluate long-term business quality, Phase 4 research (moat, growth,\n"
            "management) is required. Set ANTHROPIC_API_KEY and re-run the pipeline."
        )

    if d.thesis_breakers:
        parts.append("\nThesis breakers are more important on a long horizon — they")
        parts.append("represent conditions that would invalidate the thesis before it can compound:")
        for tb in d.thesis_breakers[:3]:
            parts.append(f"  [{tb.likelihood}] {tb.condition}")
        if len(d.thesis_breakers) > 3:
            parts.append(f"  … and {len(d.thesis_breakers) - 3} more (see full assessment)")

    if d.what_would_change_conclusion:
        parts.append(f"\nWhat would change the long-term conclusion:\n  {d.what_would_change_conclusion}")

    # -----------------------------------------------------------------------
    # B. Valuation / entry-timing dimension
    # -----------------------------------------------------------------------
    parts.append("\n─── B. VALUATION / ENTRY TIMING (current price) ────────────────")

    if d.valuation_conclusion:
        parts.append(d.valuation_conclusion)
    else:
        parts.append("No valuation conclusion available in the stored assessment.")

    parts.append(
        "\nKey principle (from investment philosophy):\n"
        "  A longer holding period reduces — but does not eliminate — the penalty\n"
        "  of paying above fair value. If the business compounds at 12–15% annually\n"
        "  the entry price matters less over 10+ years than over 1–2 years.\n"
        "  However, if the current price is at or above fair value, even a long horizon\n"
        "  may not recover a poor entry — this depends on the moat and growth durability."
    )

    # Per-method breakdown (Phase 9.4)
    if getattr(d, "per_method_valuation_summary", None):
        parts.append("\nPER-METHOD FAIR VALUE BREAKDOWN:")
        for line in d.per_method_valuation_summary:
            parts.append(f"  {line}")

    fv = _fair_value_text(d)
    if fv:
        parts.append(f"\n{fv}")

    # -----------------------------------------------------------------------
    # C. Net verdict from stored assessment
    # -----------------------------------------------------------------------
    parts.append("\n─── C. STORED DECISION (unchanged) ─────────────────────────────")
    parts.append(
        f"The stored action ({d.action.value}) was produced using the current analysis\n"
        f"date ({d.analysis_date}) and reflects near-term attractiveness. A 10+ year\n"
        f"horizon does NOT automatically change the action — it changes the weight you\n"
        f"place on valuation precision vs. business quality:"
    )
    parts.append(
        "  • If action is START_SMALL / ACCUMULATE: a long horizon reinforces the case\n"
        "    (less need for perfect entry timing; compounding works in your favour).\n"
        "  • If action is WATCH: price is approaching fair value — on a 10-year view\n"
        "    a small premium may be acceptable if the thesis is strong.\n"
        "  • If action is WAIT_INSUFFICIENT_EVIDENCE: horizon is irrelevant until\n"
        "    business quality is established. Complete the research first."
    )

    parts.append(
        f"\n[This answer is drawn from the stored {d.ticker} assessment "
        f"(date: {d.analysis_date}). No new research was generated.]"
    )
    return "\n".join(parts)


def _answer_growth_attractiveness(d: InvestmentDecisionAssessment) -> str:
    """
    Answer questions about growth, segment attractiveness, or business divisions.

    Architecture boundary:
      Only surfaces evidence already stored in the assessment.
      Does NOT invent new facts, does NOT re-run research.
      If the assessment lacks growth research, explicitly says so and names the gap.
    """
    from analytics.decision.decision_models import DecisionAction

    parts = [f"Growth and attractiveness for {d.company_name} ({d.ticker}):\n"]

    # --- Surface stored growth/attractiveness evidence ---
    has_evidence = False

    if d.why_attractive_or_unattractive:
        parts.append(f"Overall attractiveness:\n  {d.why_attractive_or_unattractive}")
        has_evidence = True

    if d.biggest_reason_to_invest:
        parts.append(f"\nStrongest investment case:\n  {d.biggest_reason_to_invest}")
        has_evidence = True

    if d.business_thesis:
        parts.append(f"\nBusiness thesis:\n  {d.business_thesis}")
        has_evidence = True

    # Surface any growth-relevant evidence items
    growth_evidence = [
        e for e in (d.supporting_evidence or [])
        if any(kw in (e.dimension + e.observation).lower()
               for kw in ("growth", "revenue", "expand", "segment", "division", "fmcg", "tech"))
    ]
    if growth_evidence:
        parts.append("\nGrowth-relevant evidence from the pipeline:")
        for e in growth_evidence[:4]:
            parts.append(f"  [{e.source_phase} / {e.dimension}] {e.observation}")
        has_evidence = True

    # --- If research was not completed, say so explicitly ---
    if not has_evidence or d.action == DecisionAction.WAIT_INSUFFICIENT_EVIDENCE:
        parts.append(
            "\n⚠  Growth and segment attractiveness were NOT assessed in the stored analysis.\n"
            "   This requires Phase 4 business research (GrowthAssessment) which was not\n"
            "   completed for this ticker."
        )
        if d.research_gaps:
            parts.append(f"   Missing dimensions: {', '.join(d.research_gaps)}")
        parts.append(
            "\n   To answer this question: set ANTHROPIC_API_KEY and re-run the pipeline.\n"
            "   The qualitative executor will fill growth, segment, and attractiveness\n"
            "   dimensions — the decision will then reflect that evidence."
        )

    parts.append(
        f"\n[This answer is drawn from the stored {d.ticker} assessment "
        f"(date: {d.analysis_date}). No new facts were generated.]"
    )
    return "\n".join(parts)


def _answer_why(d: InvestmentDecisionAssessment) -> str:
    # Phase 11A-2: surface gate-by-gate Decision Trace first, then narrative summary
    from analytics.decision.decision_trace import build_decision_trace, render_decision_trace
    try:
        trace = build_decision_trace(d)
        trace_text = render_decision_trace(trace)
    except Exception:
        trace_text = "[Decision trace unavailable]"

    parts = [
        trace_text,
        "\nNARRATIVE SUMMARY",
        "─" * 40,
        d.executive_conclusion,
        f"\nBusiness quality ({d.business_quality_label}): {d.business_quality_conclusion}",
        f"\nValuation ({d.valuation_attractiveness_label}): {d.valuation_conclusion}",
        f"\nPortfolio context: {d.portfolio_context_conclusion}",
    ]
    if d.philosophy_alignment_notes:
        parts.append("\nPhilosophy alignment notes:")
        for note in d.philosophy_alignment_notes[:3]:
            parts.append(f"  • {note}")
    parts.append(
        f"\n[This reasoning is produced by the Phase 7 hierarchical gate system.\n"
        f" Gate results are stored in decision.gate_results for full audit trail.]"
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _freshness_status(d: InvestmentDecisionAssessment) -> str:
    if d.data_freshness:
        return d.data_freshness.get("overall_status", "UNKNOWN")
    return "UNKNOWN"


def _fair_value_text(d: InvestmentDecisionAssessment) -> str:
    """
    Build a fair-value summary line from gate results or stored fields.
    The decision assessment does not store fair value range directly —
    that lives in ValuationAssessment.  We reconstruct what we can from
    the evidence items and valuation conclusion.
    """
    # Try to extract zone info from gate 3
    g3 = next((g for g in (d.gate_results or []) if g.gate_number == 3), None)
    if g3:
        supporting = (g3.supporting_evidence or [])[:3]
        if supporting:
            return "Valuation evidence (Gate 3):\n" + "\n".join(f"  • {s}" for s in supporting)
    return ""
