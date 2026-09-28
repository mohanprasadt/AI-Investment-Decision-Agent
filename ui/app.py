"""
AI Investment Decision Agent — Streamlit UI
============================================
Phase 10 MVP conversational interface.

Run with:
    streamlit run run_ui.py

Architecture:
  This file is presentation-only.  All analysis logic lives in analytics/.
  The UI calls ConversationManager which delegates to InvestmentAgent.
  No investment conclusions are generated here.

Session state keys used:
  st.session_state["manager"]  — ConversationManager instance
  st.session_state["running"]  — bool: analysis in progress
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path when run via streamlit
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from conversation.manager import ConversationManager
from data.mvp_tickers import MVP_TICKERS, get_display_name
from ui.data_status import get_ticker_cache_status, render_status_badge


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Investment Decision Agent",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

def _init_session() -> None:
    if "manager" not in st.session_state:
        st.session_state["manager"] = ConversationManager()
    if "running" not in st.session_state:
        st.session_state["running"] = False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def _render_sidebar(manager: ConversationManager) -> None:
    with st.sidebar:
        st.markdown("### Settings & Privacy")

        # API key status (read-only — never accept key through UI)
        import os
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
        if has_key:
            st.success("✓ ANTHROPIC_API_KEY set — qualitative research enabled")
        else:
            st.warning(
                "ANTHROPIC_API_KEY not set.\n\n"
                "Qualitative research (moat, management, risk) requires the "
                "Anthropic API key. Without it, Gate 1 will produce "
                "WAIT_INSUFFICIENT_EVIDENCE.\n\n"
                "Set the key in your `.env` file or shell environment — "
                "never paste it here."
            )

        st.markdown("---")
        st.markdown("### Portfolio Privacy")
        st.info(
            "This agent accepts **portfolio weight (%) only**.\n\n"
            "Shares held, average cost, account value, and transaction history "
            "are never requested, stored, or used in any analysis."
        )

        if manager.has_analysis:
            st.markdown("---")
            st.markdown("### Active Analysis")
            session = manager.session
            st.write(f"**Ticker:** {session.ticker}")
            st.write(f"**Company:** {session.company_name or '—'}")
            st.write(f"**Date:** {session.analysis_timestamp or '—'}")
            st.write(f"**Research:** {session.research_mode or '—'}")
            if session.portfolio_weight_pct is not None:
                st.write(f"**Portfolio weight:** {session.portfolio_weight_pct}%")

        st.markdown("---")
        st.caption("Phase 9.9b verified baseline | Phase 10 MVP")
        st.caption("Decision-support only. Not financial advice.")


# ---------------------------------------------------------------------------
# Analysis input panel
# ---------------------------------------------------------------------------

def _render_analysis_panel(manager: ConversationManager) -> None:
    st.markdown("## Analyse a Company")

    # ── Ticker selection ──────────────────────────────────────────────────────
    # Build dropdown options: one entry per MVP ticker + a "Custom" sentinel
    _CUSTOM_LABEL = "✏️  Custom ticker…"
    _dropdown_options = [
        f"{t['ticker']}  —  {t['name']}"
        for t in MVP_TICKERS
    ] + [_CUSTOM_LABEL]

    # Default selection: try to match the session's last ticker, else first option
    _session_ticker = manager.session.ticker or ""
    _default_idx = 0
    for _i, _opt in enumerate(_dropdown_options):
        if _opt.startswith(_session_ticker + "  "):
            _default_idx = _i
            break

    col_ticker, col_weight, col_new = st.columns([3, 1.5, 1.5])

    with col_ticker:
        selected_option = st.selectbox(
            "Ticker",
            options=_dropdown_options,
            index=_default_idx,
            label_visibility="collapsed",
            key="ticker_selectbox",
        )

        if selected_option == _CUSTOM_LABEL:
            ticker_input = st.text_input(
                "Custom ticker",
                value="",
                placeholder="e.g. AAPL, CNR.TO, RELIANCE.NS",
                label_visibility="collapsed",
                key="ticker_custom_input",
            ).strip().upper()
        else:
            # Extract just the ticker symbol (before the first "  —  ")
            ticker_input = selected_option.split("  —  ")[0].strip()

    with col_weight:
        weight_input = st.text_input(
            "Portfolio weight %",
            value=(
                str(manager.session.portfolio_weight_pct)
                if manager.session.portfolio_weight_pct is not None
                else ""
            ),
            placeholder="Weight % (optional)",
            label_visibility="collapsed",
            key="weight_input",
        )

    with col_new:
        new_position = st.checkbox("New position", value=False, key="new_position")

    col_btn, col_refresh, _ = st.columns([2, 2, 4])

    with col_btn:
        analyse_clicked = st.button(
            "🔍 Analyse",
            use_container_width=True,
            disabled=st.session_state.get("running", False),
        )

    with col_refresh:
        force_refresh = st.checkbox("Force refresh", value=False, key="force_refresh")

    # ── Data status card ──────────────────────────────────────────────────────
    if ticker_input:
        _status = get_ticker_cache_status(ticker_input)
        _badge = render_status_badge(_status)
        with st.expander(f"Data status: {_badge}", expanded=False):
            _info = _status["info"]
            _fin = _status["financials"]
            _hist = _status["history"]
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric(
                    "Company info",
                    "✅ Fresh" if _info["fresh"] else ("⚠️ Stale" if _info["present"] else "⬜ None"),
                    help=f"Age: {_status['age_display']}",
                )
            with col_b:
                st.metric(
                    "Financials",
                    "✅ Fresh" if _fin["fresh"] else ("⚠️ Stale" if _fin["present"] else "⬜ None"),
                )
            with col_c:
                st.metric(
                    "Price history",
                    "✅ Fresh" if _hist["fresh"] else ("⚠️ Stale" if _hist["present"] else "⬜ None"),
                )
            if _status["overall_status"] == "EMPTY":
                st.info(
                    "No cached data found. Analysis will fetch live data from Yahoo Finance — "
                    "this may take 15–60 seconds and could hit rate limits if many tickers "
                    "were recently fetched."
                )
            elif not _status["ready"]:
                st.warning(
                    "Some data is stale or missing. Analysis will re-fetch from Yahoo Finance "
                    "for the missing parts. Use **Force refresh** to refresh all data."
                )

    if analyse_clicked and ticker_input:
        _run_analysis(manager, ticker_input, weight_input, new_position, force_refresh)


def _run_analysis(
    manager: ConversationManager,
    ticker: str,
    weight_str: str,
    new_position: bool,
    force_refresh: bool,
) -> None:
    """Parse UI inputs and trigger the pipeline."""
    # Parse portfolio weight
    weight = None
    if weight_str.strip() and not new_position:
        try:
            weight = float(weight_str.replace("%", "").strip())
        except ValueError:
            st.warning(f"Could not parse portfolio weight '{weight_str}' — ignoring.")

    st.session_state["running"] = True

    with st.spinner(f"Analysing {ticker.upper()}… this may take 15–60 seconds."):
        try:
            manager.run_analysis(
                ticker=ticker,
                portfolio_weight_pct=weight,
                ignore_portfolio=new_position,
                force_refresh=force_refresh,
            )
        except Exception as exc:
            st.error(f"Unexpected error: {exc}")
        finally:
            st.session_state["running"] = False

    st.rerun()


# ---------------------------------------------------------------------------
# Decision / summary panel
# ---------------------------------------------------------------------------

def _render_decision_panel(manager: ConversationManager) -> None:
    session = manager.session

    if not session.has_active_analysis():
        if session.last_error:
            st.error(session.last_error)
        else:
            st.info(
                "Enter a ticker above and click **Analyse** to run the full "
                "investment pipeline. You can also type 'Analyze ITC.NS' in the "
                "chat below."
            )
        return

    assessment = session.assessment
    if assessment is None:
        st.warning("Analysis completed but no assessment was produced.")
        return

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(f"## {assessment.ticker}  —  {assessment.company_name}")
    st.caption(f"Analysis date: {assessment.analysis_date}")

    # ── Headline metrics ──────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)

    action_val = assessment.action.value if assessment.action else "—"
    confidence_val = (
        assessment.decision_confidence.value
        if assessment.decision_confidence else "—"
    )
    price_val = (
        f"{assessment.current_price:.2f} {assessment.price_currency}"
        if assessment.current_price else "Unknown"
    )
    bq_val = assessment.business_quality_label or "—"
    va_val = assessment.valuation_attractiveness_label or "—"

    with col1:
        st.metric("Decision", action_val)
    with col2:
        st.metric("Confidence", confidence_val)
    with col3:
        st.metric("Current Price", price_val)
    with col4:
        st.metric("Business Quality", bq_val)
    with col5:
        st.metric("Valuation", va_val)

    # Freshness / staleness warnings
    if getattr(assessment, "price_suppression_applied", False):
        st.warning(
            "⚠ Price data is STALE or UNKNOWN. Transactional action suppressed "
            "to WATCH_PENDING_DATA. Refresh the price and re-run."
        )
    elif getattr(assessment, "data_freshness_cap_applied", False):
        st.warning(
            "⚠ One or more data inputs are STALE. Confidence capped at LOW. "
            "The action direction is intact — refresh is recommended."
        )

    # Research mode notice
    if session.research_mode == "QUANTITATIVE_FALLBACK":
        st.info(
            "ℹ ANTHROPIC_API_KEY not set or unavailable. "
            "Qualitative research (moat, management, risk) was not performed. "
            "Gate 1 may have blocked with WAIT_INSUFFICIENT_EVIDENCE."
        )

    st.markdown("---")

    # ── Valuation ─────────────────────────────────────────────────────────────
    with st.expander("📊 Valuation", expanded=True):
        st.markdown(f"**{assessment.valuation_conclusion}**")

        # Fair value range from gate results
        fv_bear, fv_base, fv_bull = _extract_fair_value(assessment)
        if fv_bear or fv_base or fv_bull:
            fv_col1, fv_col2, fv_col3 = st.columns(3)
            ccy = assessment.price_currency or ""
            with fv_col1:
                st.metric("Bear FV", f"{ccy} {fv_bear:.2f}" if fv_bear else "—")
            with fv_col2:
                st.metric("Base FV", f"{ccy} {fv_base:.2f}" if fv_base else "—")
            with fv_col3:
                st.metric("Bull FV", f"{ccy} {fv_bull:.2f}" if fv_bull else "—")

        if assessment.is_current_price_attractive:
            st.markdown(f"*{assessment.is_current_price_attractive}*")

    # ── Investment Thesis ──────────────────────────────────────────────────────
    with st.expander("🧠 Investment Thesis"):
        if assessment.business_thesis:
            for part in assessment.business_thesis.split(" | "):
                st.write(f"• {part.strip()}")
        st.markdown(f"**Why attractive/unattractive:** {assessment.why_attractive_or_unattractive}")
        st.markdown(f"**Biggest reason TO invest:** {assessment.biggest_reason_to_invest}")
        st.markdown(f"**Biggest reason NOT to invest:** {assessment.biggest_reason_not_to_invest}")
        if assessment.what_would_change_conclusion:
            st.markdown("**What would change the conclusion:**")
            for line in assessment.what_would_change_conclusion.split("\n"):
                if line.strip():
                    st.write(f"• {line.strip()}")

    # ── Risks & Thesis Breakers ───────────────────────────────────────────────
    with st.expander("⚠️ Risks & Thesis Breakers"):
        if assessment.thesis_breakers:
            st.markdown("**Thesis Breakers:**")
            for tb in assessment.thesis_breakers[:5]:
                likelihood = getattr(tb, "likelihood", "?")
                condition  = getattr(tb, "condition", str(tb))
                monitor    = getattr(tb, "monitoring_indicator", "")
                st.write(f"  [{likelihood}] {condition}")
                if monitor:
                    st.caption(f"  Monitor: {monitor}")
        if assessment.key_risks:
            st.markdown("**Key Risks:**")
            for r in assessment.key_risks[:5]:
                st.write(f"• {r}")
        if assessment.bear_case:
            st.markdown(f"**Bear Case:** {assessment.bear_case}")

    # ── Data & Research Limitations ───────────────────────────────────────────
    limitations = (assessment.data_quality_limitations or []) + (assessment.research_gaps or [])
    if limitations:
        with st.expander("📋 Data & Research Limitations"):
            for lim in limitations[:8]:
                st.write(f"• {lim}")

    # ── Full Analysis (raw rendered report) ───────────────────────────────────
    with st.expander("📄 Full Analysis Report"):
        st.markdown("```\n" + session.rendered_report + "\n```")


# ---------------------------------------------------------------------------
# Conversation panel
# ---------------------------------------------------------------------------

def _render_conversation_panel(manager: ConversationManager) -> None:
    st.markdown("---")
    st.markdown("## Conversation")

    session = manager.session

    # Display chat history
    for turn in session.history:
        if turn.response_type == "ANALYSIS":
            # Analysis is displayed in the decision panel — skip here
            continue
        with st.chat_message("user" if turn.role == "user" else "assistant"):
            st.markdown(turn.text)

    # Chat input
    prompt = st.chat_input(
        "Ask a follow-up question, or type 'Analyze TICKER' to start a new analysis…",
        disabled=st.session_state.get("running", False),
    )

    if prompt:
        # Display user message immediately
        with st.chat_message("user"):
            st.markdown(prompt)

        # Route and display agent response
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    response = manager.route(prompt)
                except Exception as exc:
                    response = f"Error processing your question: {exc}"
            st.markdown(response)

        st.rerun()


# ---------------------------------------------------------------------------
# Fair value extraction helper
# ---------------------------------------------------------------------------

def _extract_fair_value(assessment) -> tuple:
    """
    Extract (bear, base, bull) fair values from InvestmentDecisionAssessment.
    Returns (None, None, None) if unavailable.
    """
    # Try gate_results (Gate 3 carries the FV range)
    if assessment.gate_results:
        for gr in assessment.gate_results:
            if getattr(gr, "gate_number", None) == 3:
                # Gate 3 summary often contains FV — fall through to direct fields
                break

    # Try direct fields on the assessment (populated by decision_synthesizer)
    fv_bear = getattr(assessment, "fair_value_bear", None)
    fv_base = getattr(assessment, "fair_value_base", None)
    fv_bull = getattr(assessment, "fair_value_bull", None)

    if fv_base is not None:
        return fv_bear, fv_base, fv_bull

    # Try the valuation_conclusion string as a last resort
    # (valuation_conclusion is set by decision_synthesizer and often contains
    # the FV range in the format "Weighted FV: bear/base/bull")
    conclusion = getattr(assessment, "valuation_conclusion", "") or ""
    import re
    # Match patterns like "₹154.66 / ₹233.02 / ₹332.53" or "$154 / $233 / $332"
    numbers = re.findall(r"[\$₹]?\s*([\d,]+\.?\d*)", conclusion)
    if len(numbers) >= 3:
        try:
            vals = [float(n.replace(",", "")) for n in numbers[:3]]
            return vals[0], vals[1], vals[2]
        except ValueError:
            pass

    return None, None, None


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    _init_session()
    manager: ConversationManager = st.session_state["manager"]

    # Title
    st.title("🔬 AI Investment Decision Agent")
    st.caption(
        "Decision-support only. This tool does not execute trades. "
        "See sidebar for privacy notice."
    )

    # Sidebar
    _render_sidebar(manager)

    # Analysis input
    _render_analysis_panel(manager)

    # Decision / summary (only when analysis exists)
    _render_decision_panel(manager)

    # Conversation
    _render_conversation_panel(manager)


if __name__ == "__main__":
    main()
