# Conversation Architecture

> **Status:** IMPLEMENTED (Phase 10)  
> **Purpose:** How the Streamlit UI, session state, intent routing, and follow-up Q&A work together

---

## The conversational model

The system is not a chatbot — it is a single-purpose investment analysis tool with conversational follow-up. The distinction matters:

- There is exactly one active analysis at a time per browser tab
- Follow-up questions always refer to the most recently completed analysis
- Starting a new analysis for a different ticker replaces the previous session
- Follow-up questions do NOT re-run the analysis pipeline

---

## Components

```
ui/app.py                        ← Streamlit UI (display only)
  │
  └── ConversationManager        ← Orchestration layer
        │                           (conversation/manager.py)
        │
        ├── ConversationSession  ← Per-session state container
        │     (conversation/session.py)
        │     Fields: ticker, assessment, history, portfolio_weight_pct, last_error
        │
        ├── classify_intent()    ← Intent router
        │     (conversation/intent.py)
        │     Returns one of 6 INTENT_* constants
        │
        └── InvestmentAgent      ← Analysis + follow-up responses
              (analytics/agent/investment_agent.py)
              │
              ├── run_analysis_pipeline()   ← Full analysis (new tickers)
              │     (analytics/agent/pipeline.py)
              │
              └── chat()                   ← Follow-up answers (from session)
```

---

## Session state

`ConversationSession` (a Python dataclass) holds all state for one analysis session:

```python
@dataclass
class ConversationSession:
    ticker: str = ""
    assessment: Optional[InvestmentDecisionAssessment] = None
    history: List[ChatTurn] = field(default_factory=list)
    portfolio_weight_pct: Optional[float] = None
    last_error: Optional[str] = None          # friendly message (not raw error)
```

**Important:** `last_error` stores the user-facing friendly message. The raw technical error goes to `log.warning()` only. This was the Phase 10.5 UX polish fix — previously `last_error` was set to the raw pipeline error, which reached `st.error()` in the UI.

**Streamlit persistence:** `ConversationSession` is stored in `st.session_state`. It persists within a browser tab for the duration of the Streamlit server session. It does NOT persist across browser refreshes or server restarts.

---

## Intent classification

When the user types a message, `classify_intent(message, session)` categorises it:

| Intent constant | Meaning | Typical trigger |
|----------------|---------|----------------|
| `INTENT_ANALYZE` | New analysis request | "Analyse MSFT", "What about TD.TO?" |
| `INTENT_FOLLOW_UP` | Question about current analysis | "Why WATCH?", "Explain the decision" |
| `INTENT_METRIC_EXPLANATION` | "What does X mean?" | "What is ROIC?", "Explain EV/EBITDA" |
| `INTENT_EVIDENCE_REQUEST` | "Show me the evidence" | "What data supports this?", "Show financials" |
| `INTENT_SCENARIO_WHAT_IF` | Scenario question | "What if price drops 10%?", "What would change the decision?" |
| `INTENT_UNKNOWN_CLARIFICATION` | Not classified | Anything else |

**Routing:**
- `INTENT_ANALYZE` → `ConversationManager.run_analysis()` → full pipeline
- All others → `InvestmentAgent.chat(message, assessment)` → answer from session

---

## The analysis trigger

When `run_analysis()` is called:

1. `run_analysis_pipeline(ticker, portfolio_weight_pct, force_refresh)` is invoked
2. On success: `session.assessment` is updated with the new `InvestmentDecisionAssessment`
3. On failure: `session.last_error` is set to the friendly error message; `session.assessment` is cleared
4. The rendered report is returned to the UI

---

## Follow-up answer generation

When `InvestmentAgent.chat(message, assessment)` is called:

- The agent reads the existing `InvestmentDecisionAssessment` from the session
- It generates a natural-language answer by calling the renderer or the Anthropic API (for conversational elaboration)
- No new yfinance calls are made
- No new Claude research calls are made (unless the follow-up specifically triggers one)
- The answer is appended to `session.history` as a `ChatTurn`

**Key property:** A stale or rate-limited analysis can still answer follow-up questions. If the user got a WATCH decision 2 hours ago, they can still ask "what's the fair value?" and get an answer from the cached assessment.

---

## Chat history

`session.history` is a list of `ChatTurn` objects:

```python
@dataclass
class ChatTurn:
    role: str          # "user" or "assistant"
    content: str       # message text
    timestamp: str     # ISO timestamp
```

The full history is displayed in the chat panel. It is not used for intent classification (each message is classified independently).

---

## UI components (app.py)

The Streamlit UI renders five major areas:

1. **Sidebar or top panel:** Ticker selector, portfolio weight input, new position checkbox, force refresh checkbox
2. **Data status card:** Collapsible; shows cache freshness for the selected ticker (before analysis)
3. **Analyse button:** Triggers `ConversationManager.run_analysis()`
4. **Analysis output:** The rendered report from `PipelineResult.rendered_report`
5. **Chat panel:** Input box + history of `ChatTurn` objects

**Error display:** `st.error(session.last_error)` is called when `session.last_error` is set. This is the only place errors are shown to the user. It always shows the friendly message — never the raw error.

---

## What happens when the user changes ticker

When the user selects a different ticker from the dropdown (but has not clicked Analyse yet):
- The data status card updates to show freshness for the new ticker
- The existing analysis and chat history remain visible (they apply to the previous ticker)

When the user clicks Analyse for a new ticker:
- A new analysis is run
- `session.assessment` is replaced with the new assessment
- `session.history` is cleared
- The chat panel starts fresh

---

## Two-path problem (historical note)

Before the Phase 10.5 UX polish fix, there were two paths by which error messages were produced:

1. `ConversationManager._format_pipeline_error()` → produced a friendly message → returned as the conversation turn response
2. `session.last_error = pipeline_result.error` → set to the RAW error string → rendered by `st.error(session.last_error)` in `app.py`

Path 2 exposed the raw error (containing strings like `CANNOT_COMPLETE_LIVE_ANALYSIS`, `yfinance`, HTTP 429 details) directly in the UI.

**Fix:** `session.last_error = error_msg` (where `error_msg` is the already-formatted friendly message). The raw error is sent only to `log.warning()`.
