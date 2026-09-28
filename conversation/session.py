"""
ConversationSession — Phase 10
================================
Holds the state for one UI conversation session.

This is a thin data model. No analytics logic lives here.
All structured analysis content comes from InvestmentDecisionAssessment,
which is set by ConversationManager after calling run_analysis_pipeline().

Design rules:
  - Portfolio weight only — never shares, cost, or account value.
  - One active ticker per session. A new analysis clears chat history.
  - No database. State lives in Streamlit st.session_state for the MVP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Chat turn
# ---------------------------------------------------------------------------

@dataclass
class ChatTurn:
    """One exchange in the conversation."""
    role: str               # "user" | "agent"
    text: str
    intent: str = ""        # classified intent for this turn
    timestamp: str = ""
    response_type: str = "" # "ANALYSIS" | "FOLLOWUP" | "ERROR" | "CLARIFICATION"


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

@dataclass
class ConversationSession:
    """
    State for one conversation session.

    Cleared fields on new ticker:
      - history, assessment, rendered_report, research_mode, load_description

    Preserved across follow-up turns:
      - ticker, company_name, analysis_timestamp, portfolio_weight_pct,
        assessment (the authoritative InvestmentDecisionAssessment)
    """
    # What we're analysing
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    analysis_timestamp: Optional[str] = None

    # The full structured result (source of truth for all follow-up rendering)
    # Type: InvestmentDecisionAssessment | None
    assessment: Optional[object] = None

    # Full rendered report text (from render_assessment())
    rendered_report: str = ""

    # Chat history (display only — not re-fed to the engine)
    history: List[ChatTurn] = field(default_factory=list)

    # Portfolio context (preserved so user doesn't re-enter after follow-ups)
    portfolio_weight_pct: Optional[float] = None

    # Research mode used for the active analysis
    research_mode: str = ""   # "ANTHROPIC" | "QUANTITATIVE_FALLBACK"

    # Load summary (data completeness / freshness description)
    load_description: str = ""

    # Error from last operation
    last_error: Optional[str] = None

    # True while analysis is running (for UI spinner control)
    analysis_in_progress: bool = False

    def clear_for_new_ticker(self) -> None:
        """Reset all analysis-specific state when a new ticker is requested."""
        self.company_name        = None
        self.analysis_timestamp  = None
        self.assessment          = None
        self.rendered_report     = ""
        self.history             = []
        self.research_mode       = ""
        self.load_description    = ""
        self.last_error          = None

    def has_active_analysis(self) -> bool:
        """True when an analysis has been completed for the current ticker."""
        return self.assessment is not None

    def add_turn(self, role: str, text: str, intent: str = "",
                 response_type: str = "") -> None:
        """Append one chat turn to the conversation history."""
        from datetime import datetime, timezone
        self.history.append(ChatTurn(
            role=role,
            text=text,
            intent=intent,
            timestamp=datetime.now(timezone.utc).strftime("%H:%M:%S"),
            response_type=response_type,
        ))
