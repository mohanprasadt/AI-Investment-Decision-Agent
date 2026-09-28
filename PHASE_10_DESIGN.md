# Phase 10 — Conversational Investment Agent
## Architecture & MVP Design

*Based on inspection of the Phase 9.9b verified repository. No files modified.*
*Design date: 2026-08-15*

---

## 1. Executive Summary

The existing investment engine is more complete than a typical pre-productization codebase. A conversational REPL (`run_agent.py`, lines 474–490), a session-state object (`AgentSession`), an intent parser (`intent_parser.py`), and a 1,367-line follow-up renderer (`renderer.py`) already exist and work.

Phase 10 is therefore not "build a conversational layer from scratch." It is:

**Expose what already works through a proper UI, close the three specific gaps between the current CLI REPL and a complete product, and do so with minimal disruption to the existing engine.**

The three gaps are:

1. **No GUI** — interaction is a raw `input(">")` loop in a terminal.
2. **Analysis cannot be triggered from within the chat** — `InvestmentAgent.chat()` returns an error message when no prior `analyze()` call has been made. A UI user must know to call `analyze()` first.
3. **Intent taxonomy is thin** — the parser has three intents (ANALYZE, FOLLOW_UP, UNKNOWN). Several user journeys (SCENARIO/WHAT_IF, DATA_QUALITY, EVIDENCE_REQUEST) fall into UNKNOWN and get no useful response.

The recommended MVP closes these three gaps only. Everything else stays unchanged.

**Recommended technology:** Streamlit (single Python file, no JavaScript, compatible with the existing pure-Python stack, runs locally today without deployment infrastructure).

**Estimated complexity:** Medium (the hardest part is the full-stack `analyze()` call path in the UI, not the UI itself).

---

## 2. Current Architecture Assessment

### 2.1 Repository Inventory (as-found)

```
run_agent.py              CLI entry point + while-True REPL (494 lines)
run_analysis.py           Alternative CLI entry point with demo/live routing
analytics/
  agent/
    investment_agent.py   InvestmentAgent: chat() / analyze() / last_assessment
    intent_parser.py      parse_intent() → Intent(ANALYZE|FOLLOW_UP|UNKNOWN)
    renderer.py           render_assessment() + render_followup() (1,367 lines)
    data_loader.py        load_ticker() → DataLoadResult (yfinance → metrics → FQ)
    valuation_builder.py  build_valuation_input() (493 lines)
    research_orchestrator.py  ResearchOrchestrator + quantitative_executor
    anthropic_researcher.py   AnthropicResearcher (calls Claude API)
  decision/
    decision_synthesizer.py  make_investment_decision() — 5 gates (1,550 lines)
    decision_models.py        InvestmentDecisionAssessment, DecisionAction, etc.
    gate1–gate5.py            Individual gate evaluators
  financial_quality/
    quality_engine.py         assess_financial_quality()
    financial_metrics_model.py CompanyFinancialMetrics (all financial data)
    calculations.py           Deterministic calculations
    thresholds_engine.py      Threshold loading + classification
  valuation/
    valuation_synthesizer.py  run_valuation() — 4 methods → weighted FV
    multiples_engine.py       P/E, P/FCF, EV/EBITDA, historical multiples
    dcf_engine.py             DCF with bear/base/bull scenarios
    margin_of_safety.py       MOS + zone classification
    method_selector.py        Method applicability rules
    valuation_models.py       ValuationInput, ValuationAssessment, FairValueRange
  business_research/
    research_models.py        BusinessResearchAssessment, MoatAssessment, etc.
    research_synthesizer.py   Synthesises qualitative research
    moat_analyzer.py          Competitive advantage classification
  portfolio/
    portfolio_models.py       WeightOnlyPortfolioContext, PortfolioPositionContext
    portfolio_synthesizer.py  build_portfolio_context()
    portfolio_calculator.py   Concentration + allocation calculations
    concentration_analyzer.py Position size risk evaluation
    incremental_scenarios.py  What-if scenarios for position changes
  data_freshness.py           DataFreshnessAssessment + build_freshness_assessment()
data/ingestion/
  fetcher.py                  yfinance fetch with local cache (data/cache/*.json)
  normalizer.py               Raw yfinance → CompanyFinancialMetrics
config/
  thresholds.yaml             Financial quality thresholds
  valuation_config.yaml       DCF assumptions, zone boundaries
  investment_philosophy.md    Investor profile and decision principles
agent/prompts/               Markdown prompt templates for Claude API research steps
tests/                       1,072 tests; 1,071 pass; 3 pre-existing errors
```

### 2.2 Installed Dependencies (Confirmed)

```
yfinance  1.5.2   ✓ installed
requests  2.34.2  ✓ installed

anthropic         NOT installed  (required for AnthropicResearcher)
streamlit         NOT installed
gradio            NOT installed
flask             NOT installed
fastapi           NOT installed
```

The `anthropic` package is imported with a try/except guard in `run_agent.py` (lines 53–58). If unavailable, `quantitative_executor` is used and Gate 1 produces `WAIT_INSUFFICIENT_EVIDENCE`. This is correct behaviour and must be preserved.

### 2.3 Current Architecture Map

```
User (terminal)
     │
     │  python run_agent.py --ticker ITC.NS [--weight 4.1]
     ▼
run_agent.py                          ← CLI entry point
  │
  ├─ CNR.TO demo path:
  │    _build_cnr_metrics()
  │    _build_cnr_research()
  │    _build_cnr_valuation()
  │    _load_cnr_demo()
  │
  └─ Live path:
       load_ticker()                  ← data_loader.py
         fetcher.fetch_ticker()       ← yfinance (cached in data/cache/)
         normalizer.normalize()       ← CompanyFinancialMetrics
         assess_financial_quality()   ← FinancialQualityAssessment
         │
       ResearchOrchestrator           ← research_orchestrator.py
         AnthropicResearcher OR       ← anthropic_researcher.py (Claude API)
         quantitative_executor        ← always returns None → Gate 1 blocks
         │
       build_valuation_input()        ← valuation_builder.py
       run_valuation()                ← valuation_synthesizer.py
         ├─ DCF (dcf_engine.py)
         ├─ P/E + P/FCF + EV/EBITDA  (multiples_engine.py)
         └─ weighted FairValueRange
         │
  InvestmentAgent.analyze()          ← investment_agent.py
    make_investment_decision()        ← decision_synthesizer.py
      Gate 1: business understanding
      Gate 2: financial quality
      Gate 3: valuation zone
      Gate 4: portfolio fit
      Gate 5: adversarial stress
      → InvestmentDecisionAssessment
    render_assessment()              ← renderer.py
    → str (printed to terminal)
     │
     │  print(report)
     │
     └─ while True: input("> ")     ← REPL loop
          agent.chat(text)
            parse_intent(text)
            → INTENT_FOLLOW_UP → render_followup() ← renderer.py
            → INTENT_ANALYZE   → (returns error — no live fetch in chat())
            → INTENT_UNKNOWN   → help text
          print(response)
```

### 2.4 Where the Conversational Layer Fits

The insertion point is **between the user and `InvestmentAgent`**. Nothing in `analytics/` needs to change. The existing `InvestmentAgent.chat()` / `InvestmentAgent.analyze()` interface is the stable boundary.

```
User (browser or terminal)
     │
     ▼
[NEW] Streamlit UI / conversation_manager.py   ← Phase 10 additions
     │
     ├─ Full analysis trigger → InvestmentAgent.analyze()  [gap 2 fix]
     ├─ Richer intent routing → ConversationManager       [gap 3 fix]
     └─ Session state         → ConversationSession        [gap 1 UI]
     │
     ▼
InvestmentAgent (unchanged)
     │
     ▼
Existing analytics stack (unchanged)
```

---

## 3. Product Objective

Build the smallest viable conversational interface that makes the existing investment engine usable as a product, not just as a backend library.

**What this means concretely:**

- A user opens a URL (or runs `streamlit run run_ui.py`) and sees a clean interface.
- They type "Analyze ITC.NS" and the engine runs, fetches data, runs the research, computes valuation, synthesises a decision, and presents the structured result.
- They can ask follow-up questions in natural language without repeating context.
- They can challenge the recommendation, ask about evidence, explore valuation assumptions, and understand data gaps.
- The conversational layer never weakens the engine's epistemic standards (no fabrication, no invented moat claims, no unsupported accounting attribution).

**What this does not mean:**

- Building a second investment analysis engine in the UI layer.
- Storing analyses in a database.
- Supporting multiple simultaneous users.
- Deploying to the cloud.
- Adding authentication.

---

## 4. User Journeys

### Journey 1 — Initial Analysis
```
User:   Analyze ITC.NS
Agent:  [full investment summary: decision, valuation, thesis, risks, data quality]
```
**Current state:** Works via `run_agent.py --ticker ITC.NS` CLI. Cannot be triggered from within `chat()`. The UI must close this gap by calling `InvestmentAgent.analyze()` directly when a ticker is detected.

### Journey 2 — Decision Explanation
```
User:   Why are you recommending WAIT?
Agent:  [explanation of gate outcomes + valuation zone + philosophy alignment]
```
**Current state:** Handled by `render_followup()` via `_answer_why()`. Works today.

### Journey 3 — Valuation Explanation
```
User:   Why is the P/FCF valuation lower than P/E?
Agent:  [per-method breakdown with FCF/EPS comparison]
```
**Current state:** Handled by `render_followup()` via `_answer_valuation_method()` + `_answer_fcf_eps()` after the Phase 9.9b routing fix. Works today.

### Journey 4 — Assumption Challenge
```
User:   Which assumptions have the greatest impact on your fair value?
Agent:  [key assumptions from assessment + sensitivity notes]
```
**Current state:** Handled by `_answer_valuation()` which reads `d.key_assumptions`. Works today.

### Journey 5 — Risk Analysis
```
User:   What is the strongest argument against your recommendation?
Agent:  [thesis breakers + bear case + key risks]
```
**Current state:** Handled by `_answer_risks()`. Works today.

### Journey 6 — Data Quality
```
User:   What important information is missing or unreliable?
Agent:  [data_quality_limitations + research_gaps + freshness assessment]
```
**Current state:** Handled by `_answer_data_quality()`. Works today.

### Journey 7 — Decision Threshold
```
User:   At what price would ITC become attractive?
Agent:  [fair value range bear/base/bull with zone explanation]
```
**Current state:** `render_followup()` routes "what price" questions to `_answer_valuation()`. The fair value range (bear/base/bull) is stored in `InvestmentDecisionAssessment` and surfaced. Works today, though the phrasing could be more direct. A small improvement in routing is the only gap.

### Journey 8 — Scenario / What-If
```
User:   What would change your recommendation?
Agent:  [what_would_change_conclusion from assessment]
```
**Current state:** Handled by `_answer_what_would_change()`. Works today.

### Journey 9 — Conversational Continuity
```
User:   What about the dividend?
User:   How does that affect the recommendation?
```
**Current state:** Session state (`AgentSession.last_assessment`) preserves ITC.NS context across turns. Both questions route to `render_followup()` which reads from the stored assessment. Works today.

**Summary:** 7 of 9 journeys work today in the CLI REPL. Journey 1 (trigger analysis from within chat) and the UI itself (Journey 0: open a browser and see something useful) are the primary gaps.

---

## 5. Proposed Architecture

### 5.1 Architecture Diagram

```
┌─────────────────────────────────────────┐
│              Streamlit UI               │  ui/app.py   [NEW]
│   Ticker input │ Analyze button         │
│   Analysis panel (structured)           │
│   Conversation panel (chat history)     │
│   Input box + Submit                    │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│         ConversationManager             │  conversation/manager.py  [NEW]
│                                         │
│  ┌─────────────────────────────────┐    │
│  │       ConversationSession        │    │  conversation/session.py  [NEW]
│  │  ticker, analysis, timestamp,    │    │
│  │  chat_history, analysis_pending  │    │
│  └─────────────────────────────────┘    │
│                                         │
│  route(user_input)                      │
│    → classify_intent()  [EXTENDED]      │  conversation/intent.py   [NEW]
│    → handle_analysis()                  │
│    → handle_followup()                  │
│    → handle_unknown()                   │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          InvestmentAgent                │  analytics/agent/investment_agent.py
│          (UNCHANGED)                    │  [EXISTING — DO NOT MODIFY]
│                                         │
│  analyze(ticker, …) → str               │
│  chat(text)         → str               │
│  last_assessment    → IDA               │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│      Existing Analytics Stack           │  analytics/  [ALL UNCHANGED]
│  DataLoader → ResearchOrchestrator      │
│  ValuationBuilder → DecisionSynthesizer │
│  Renderer (render_assessment/followup)  │
└─────────────────────────────────────────┘
```

### 5.2 What Remains Unchanged

Every file in `analytics/` stays exactly as-is:
- `investment_agent.py`, `intent_parser.py`, `renderer.py`, `data_loader.py`
- `valuation_builder.py`, `research_orchestrator.py`, `anthropic_researcher.py`
- All `decision/`, `financial_quality/`, `valuation/`, `business_research/`, `portfolio/`
- All `data/ingestion/` files
- All `config/` files
- All `tests/` files
- `run_agent.py` and `run_analysis.py` (still work as before)

### 5.3 What Is New

Three new modules and one entry point:

| Path | Purpose |
|---|---|
| `conversation/session.py` | ConversationSession dataclass (richer than AgentSession) |
| `conversation/manager.py` | ConversationManager: routes input, calls agent, formats response |
| `conversation/intent.py` | Extended intent classifier (14 intents vs 3 current) |
| `ui/app.py` | Streamlit application |
| `run_ui.py` | Entry point: `streamlit run run_ui.py` |

### 5.4 What Should NOT Be Duplicated

- **Do not re-implement analysis logic in the UI or ConversationManager.** All decisions come from `InvestmentAgent.analyze()` → `make_investment_decision()`.
- **Do not re-implement follow-up rendering.** All follow-up responses come from `InvestmentAgent.chat()` → `render_followup()`.
- **Do not create a second session state.** `ConversationSession` wraps `InvestmentAgent`'s session; it does not replace it.
- **Do not create a second intent parser for the intents `intent_parser.py` already handles.** The extended `intent.py` enriches classification for routing but delegates the actual response to the existing renderer.

---

## 6. Conversation-State Model

### 6.1 ConversationSession

```python
@dataclass
class ConversationSession:
    # What we're talking about
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    analysis_timestamp: Optional[str] = None

    # The full structured result (source of truth for all follow-ups)
    # This is InvestmentDecisionAssessment from the engine — never replicated.
    assessment: Optional[object] = None   # InvestmentDecisionAssessment

    # Chat history for display (not for re-feeding to the engine)
    history: List[ChatTurn] = field(default_factory=list)

    # Portfolio context supplied by the user
    portfolio_weight_pct: Optional[float] = None

    # State flags
    analysis_in_progress: bool = False
    last_error: Optional[str] = None

@dataclass
class ChatTurn:
    role: str             # "user" | "agent"
    text: str
    intent: str           # The classified intent for this turn
    timestamp: str
    response_type: str    # "ANALYSIS" | "FOLLOWUP" | "ERROR" | "CLARIFICATION"
```

### 6.2 What Is Stored vs Reconstructed

**Stored in ConversationSession:**
- `assessment` (the full `InvestmentDecisionAssessment`) — the single source of truth
- `history` (list of `ChatTurn`) — for display only
- `ticker`, `company_name`, `analysis_timestamp` — for context display in UI
- `portfolio_weight_pct` — so the user does not need to repeat it

**Not stored (reconstructed on demand):**
- Rendered report text — reconstructed from `assessment` via `render_assessment()`
- Follow-up answers — reconstructed from `assessment` via `render_followup()`
- Financial metrics, valuation methods, gate details — all inside `assessment`

**Not stored (not applicable for MVP):**
- Multiple tickers
- Analysis history across sessions
- Database records
- User preferences

No database is required. In-memory state held in Streamlit session state (`st.session_state`) is sufficient for the single-user local MVP.

---

## 7. Intent / Routing Model

### 7.1 Extended Intent Taxonomy (14 intents)

The current parser produces 3 intents. The extended classifier produces 14, but the first 3 map directly to the existing parser's output and can be delegated to it.

| Intent | Trigger Examples | Handler |
|---|---|---|
| `INITIAL_ANALYSIS` | "Analyze ITC.NS", "Run ITC.NS" | `handle_analysis()` → `agent.analyze()` |
| `DECISION_EXPLANATION` | "Why WAIT?", "Why that recommendation?" | `agent.chat()` → `_answer_why()` |
| `VALUATION_EXPLANATION` | "Why P/FCF < P/E?", "What's the fair value?" | `agent.chat()` → `_answer_valuation_method()` |
| `FINANCIAL_QUALITY` | "Is the ROIC good?", "What's the FCF conversion?" | `agent.chat()` → default/why handler |
| `BUSINESS_QUALITY` | "Tell me about the business", "What do they do?" | `agent.chat()` → `_answer_why()` |
| `MOAT` | "What's the moat?", "Is the competitive advantage durable?" | `agent.chat()` → `_answer_why()` (moat in thesis) |
| `RISK_ADVERSARIAL` | "What are the risks?", "What could go wrong?" | `agent.chat()` → `_answer_risks()` |
| `DATA_QUALITY` | "What's missing?", "How fresh is the data?" | `agent.chat()` → `_answer_data_quality()` |
| `PORTFOLIO_CONTEXT` | "How does this fit my portfolio?" | `agent.chat()` → `_answer_portfolio()` |
| `SCENARIO_WHAT_IF` | "What if EPS grows 10%?", "What price makes this a buy?" | `agent.chat()` → `_answer_what_would_change()` + FV display |
| `METRIC_EXPLANATION` | "What is ROIC?", "Explain FCF conversion" | [NEW] general financial explanation |
| `EVIDENCE_REQUEST` | "What is your source for the moat claim?", "Show me the evidence" | `agent.chat()` → `_answer_confidence()` |
| `FOLLOW_UP` | "What about the dividend?", "How does that affect it?" | `agent.chat()` → existing follow-up routing |
| `UNKNOWN_CLARIFICATION` | anything else | clarification prompt |

### 7.2 Routing Logic

```
classify_intent(user_input)
  │
  ├─ Contains ticker + analyze verb?   → INITIAL_ANALYSIS
  │
  ├─ Contains ticker without verb?     → (contextual: if session active, FOLLOW_UP)
  │
  ├─ Matches follow-up patterns?       → delegate to existing parse_intent()
  │     (already handles ~10 subtypes within FOLLOW_UP)
  │
  ├─ "What is X?" / "Explain X"       → METRIC_EXPLANATION
  │     (X is a financial term, not about this stock)
  │
  ├─ "Evidence" / "Source" / "How do you know"  → EVIDENCE_REQUEST
  │
  ├─ "What if" / "Suppose" / "scenario"  → SCENARIO_WHAT_IF
  │
  └─ No match + no active session     → UNKNOWN_CLARIFICATION
```

### 7.3 Key Design Rule

For intents `DECISION_EXPLANATION` through `FOLLOW_UP`, the `ConversationManager` passes the raw user text to `InvestmentAgent.chat()` and returns the result. It does not attempt to parse the text further or generate a custom response. The 1,367-line `renderer.py` already handles the sub-routing.

The `ConversationManager` only generates its own response for:
- `INITIAL_ANALYSIS` — must call `agent.analyze()` with live data pipeline
- `METRIC_EXPLANATION` — general financial term explanation (engine has no stored context for these)
- `UNKNOWN_CLARIFICATION` — user needs guidance
- Error/loading states

---

## 8. Response Architecture

### 8.1 Response Types

Every response from the agent should be classified as one of:

| Type | Meaning | Source |
|---|---|---|
| `ANALYSIS` | Full structured investment report | `render_assessment()` |
| `FACT` | Direct read from stored assessment field | `render_followup()` |
| `CALCULATION` | Arithmetic derived from stored fields (e.g., EPS−FCF gap) | `render_followup()` |
| `INFERENCE` | Assessment field marked as inference/interpretation | `render_followup()` |
| `ASSUMPTION` | A named assumption from the assessment | `render_followup()` |
| `GENERAL_EXPLANATION` | Financial term explanation not tied to this stock | ConversationManager |
| `UNAVAILABLE` | Requested data not in stored assessment | `render_followup()` (explicit gap flagging) |
| `ERROR` | Pipeline error, network failure, invalid input | ConversationManager |

### 8.2 Where Responses Come From

```
ANALYSIS response:
  render_assessment(agent.last_assessment)
  → already formats: decision, valuation, thesis, risks, data quality, freshness

FACT/CALCULATION/INFERENCE/ASSUMPTION responses:
  render_followup(user_text, agent.last_assessment)
  → already labels what is directly observed vs calculated vs unavailable
  → renderer.py already marks gaps with "not stored" / "not available" phrasing
  → Phase 9.9b strengthened this: no fabricated reconciliation items

GENERAL_EXPLANATION responses:
  ConversationManager generates these for financial term definitions
  ("What is ROIC?", "Explain FCF conversion")
  These are not analysis — they are educational context
  Clearly labelled as general financial explanation, not stock-specific

ERROR responses:
  ConversationManager catches pipeline exceptions and data-fetch failures
  Returns friendly message with next-step suggestion
```

### 8.3 Preserving Epistemic Standards

The conversational layer must not weaken what Phase 9.9b strengthened. Concretely:

- The UI never generates financial conclusions itself. All conclusions come from `InvestmentDecisionAssessment`.
- The `ConversationManager` never interpolates metric values into response text itself. It passes text to `render_followup()` which reads from the structured assessment.
- `GENERAL_EXPLANATION` responses are clearly labelled as general financial education, not specific to the analysed stock.
- If the assessment is `None` (no analysis run yet), follow-up responses must say so explicitly rather than fabricating a general answer.

---

## 9. UI Technology Recommendation

### 9.1 Evaluation Matrix

| Criterion | Streamlit | Gradio | Flask + HTML | CLI REPL (current) |
|---|---|---|---|---|
| Install complexity | pip install streamlit | pip install gradio | pip install flask + HTML/JS | already exists |
| Compatibility with Python stack | native Python | native Python | native Python | native Python |
| Speed to MVP | 1–2 days | 1 day | 3–5 days | 0 days |
| Conversational UX | good (st.chat_message) | good (gr.ChatInterface) | requires custom JS | poor (raw terminal) |
| Structured analysis display | excellent (columns, metrics, expanders) | limited | excellent (custom HTML) | poor (text only) |
| Charts/tables later | excellent (st.plotly_chart, st.dataframe) | limited | excellent | no |
| Local execution | `streamlit run app.py` | `python app.py` | `python app.py` + browser | `python run_agent.py` |
| Future deployment | Streamlit Cloud or Docker | Hugging Face Spaces or Docker | any cloud | not applicable |
| Maintenance burden | low | low | medium (own the full stack) | none (but not a product) |
| Long analysis output display | excellent (st.expander, st.markdown) | limited | excellent | poor (scrolling terminal) |

### 9.2 Recommendation: Streamlit

**Reason 1: Structural fit.** The analysis output is a structured document (decision + valuation + thesis + risks + data quality). Streamlit's `st.expander`, `st.metric`, `st.columns`, and `st.markdown` map directly to these sections without custom CSS.

**Reason 2: Chat support.** `st.chat_message` and `st.chat_input` provide a native chat UX in ~20 lines of code.

**Reason 3: Single file.** The entire MVP UI can live in `ui/app.py` as a single Python file. No JavaScript, no templates, no REST API.

**Reason 4: Future path.** Adding charts (Plotly), dataframes (valuation tables), and multi-ticker comparison requires only additional Streamlit widgets — no architecture change.

**Reason 5: Local default, cloud optional.** Streamlit Cloud deployment is a `git push` away if needed later. For now, `streamlit run run_ui.py` is the only command the Product Owner needs.

**Why not Flask:** Flask requires building and maintaining the entire frontend (HTML, CSS, JS, templates). The maintenance burden is disproportionate for a single-user local tool.

**Why not Gradio:** Gradio is optimised for ML model demos with simple inputs. Displaying a structured 64-line investment report with collapsible sections, valuation tables, and chat history requires fighting Gradio's opinionated layout. Streamlit handles this naturally.

**Why not "CLI REPL as intermediate MVP":** The CLI REPL already exists. Building it further delays the actual goal, which is to see the engine as a product in a browser.

---

## 10. MVP Screen Design

### 10.1 Main Screen Layout

```
┌─────────────────────────────────────────────────────────┐
│  🔬 AI Investment Decision Agent          [sidebar ►]   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ANALYSE A COMPANY                                      │
│  ┌──────────────────────────────────┐  [Portfolio %]   │
│  │  ITC.NS                          │  [ 4.1% ]        │
│  └──────────────────────────────────┘                  │
│  [ Analyse ]    [ New Position ]    [ Force Refresh ]  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ITC.NS  —  ITC Limited           2026-08-15            │
│  ──────────────────────────────────────────────────     │
│  ▌ DECISION    WAIT                                     │
│  ▌ Confidence  MEDIUM                                   │
│  ▌ Price       ₹278.20          Fair Value  ₹233.02    │
│  ▌ Zone        Price above base FV — not attractive    │
│                                                         │
│  ┌─ Business Quality ──────────────────────────┐       │
│  │  STRONG  │  FMCG + Agribusiness + Hotels     │       │
│  └──────────────────────────────────────────────┘       │
│  ┌─ Valuation ─────────────────────────────────┐       │
│  │  Bear ₹154.66  │  Base ₹233.02  │  Bull ₹332.53│    │
│  │  P/E: ₹288.85  │  P/FCF: ₹216.67  │  ...       │   │
│  └──────────────────────────────────────────────┘       │
│  ▼ Full Analysis  [expand]                              │
│  ▼ Risks & Thesis Breakers  [expand]                   │
│  ▼ Data & Research Limitations  [expand]               │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  CONVERSATION                                           │
│                                                         │
│  ┌──────────────────────────────────────────────┐      │
│  │  You: Why are you recommending WAIT?          │      │
│  └──────────────────────────────────────────────┘      │
│  ┌──────────────────────────────────────────────┐      │
│  │  Agent:                                       │      │
│  │  The WAIT recommendation reflects two factors:│      │
│  │  1. Business quality is STRONG (Gate 2 pass)  │      │
│  │  2. Current price (₹278.20) is above the base │      │
│  │     fair value (₹233.02) — Gate 3 finds the   │      │
│  │     valuation zone UNATTRACTIVE at this price. │      │
│  │  ...                                           │      │
│  └──────────────────────────────────────────────┘      │
│                                                         │
│  ┌──────────────────────────────────────────────┐      │
│  │  Ask a follow-up question...            [Send]│      │
│  └──────────────────────────────────────────────┘      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 10.2 Sidebar (Collapsed by Default)

```
┌─ Settings ──────────────────────┐
│  ANTHROPIC_API_KEY  [set in .env]│
│  Data cache: ITC.NS  2026-08-15  │
│  [ Clear cache ]                 │
│                                  │
│  Portfolio privacy notice:       │
│  Only weight % is used.          │
│  No shares, cost, or account     │
│  value is stored or requested.   │
└──────────────────────────────────┘
```

### 10.3 Key UI Decisions

- **Analysis panel and conversation panel coexist.** The analysis is not replaced by the conversation — it stays visible as the user asks questions.
- **Structured display, not raw text.** The full `render_assessment()` string output goes into an `st.expander`. The headline metrics (decision, price, FV, zone) are displayed as `st.metric` widgets at the top.
- **Streaming feedback during analysis.** A `st.spinner` or `st.status` widget shows pipeline progress (fetching → researching → valuing → deciding). Analysis takes 15–60 seconds with the Anthropic API.
- **Chat history persists.** `st.session_state.chat_history` accumulates turns within a session. Cleared when a new ticker is analysed.
- **Error surface.** Network failures and invalid tickers produce `st.error()` — not blank output.

---

## 11. Product Owner Acceptance-Test Catalogue

For each test: **User Input → Expected Routing → Source/Component → Response Characteristics → Key Assertion**

### A. Basic Analysis

| Field | Value |
|---|---|
| Input | `Analyze ITC.NS` |
| Routing | `INITIAL_ANALYSIS` → `handle_analysis()` → `agent.analyze()` |
| Source | Full pipeline: `data_loader` → `research_orchestrator` → `valuation_builder` → `decision_synthesizer` |
| Response | Structured report: decision, price, FV, thesis, risks |
| Key assertion | `agent.last_assessment.ticker == "ITC.NS"` AND `action != None` |

### B. Decision Explanation

| Field | Value |
|---|---|
| Input | `Why are you recommending WAIT?` |
| Routing | `FOLLOW_UP` → `agent.chat()` → `_answer_why()` |
| Source | `InvestmentDecisionAssessment.gate_results` + `executive_conclusion` |
| Response | Gate-by-gate explanation, references to specific gates that blocked or constrained |
| Key assertion | Response cites the specific gate (Gate 3 valuation zone) that produced WAIT; does not fabricate a new reason |

### C. Valuation Explanation — FCF vs P/E

| Field | Value |
|---|---|
| Input | `Why is P/FCF lower than P/E?` |
| Routing | `FOLLOW_UP` → `agent.chat()` → `_answer_valuation_method()` |
| Source | `ValuationAssessment.method_assessments` |
| Response | Actual FCF/share and EPS values, period-alignment note, weights |
| Key assertion | Response shows actual computed values, not generic text; says "SAME-PERIOD BASIS" for ITC.NS |

### D. Financial Metric Explanation

| Field | Value |
|---|---|
| Input | `What is ROIC and why does it matter?` |
| Routing | `METRIC_EXPLANATION` → ConversationManager general explanation |
| Source | ConversationManager (not the engine — this is generic financial education) |
| Response | Definition of ROIC, why it indicates moat, clearly labelled as general explanation |
| Key assertion | Response does NOT include ITC.NS-specific numbers unless specifically tied to a stored assessment field |

### E. Business/Moat Question

| Field | Value |
|---|---|
| Input | `What is ITC's competitive advantage?` |
| Routing | `FOLLOW_UP` → `agent.chat()` → `_answer_why()` (moat in business thesis) |
| Source | `InvestmentDecisionAssessment.business_thesis` + `business_quality_conclusion` |
| Response | Moat sources, strength, durability — from research assessment, not fabricated |
| Key assertion | Response is sourced from stored assessment; if research was `quantitative_executor`, response explicitly flags that qualitative moat research was not performed |

### F. Risk Challenge

| Field | Value |
|---|---|
| Input | `What is the strongest argument against investing in ITC right now?` |
| Routing | `FOLLOW_UP` → `agent.chat()` → `_answer_risks()` |
| Source | `thesis_breakers` + `bear_case` + `key_risks` |
| Response | Thesis breakers with likelihood, bear case narrative |
| Key assertion | At least one thesis breaker is listed; response does not assert the risks are low unless explicitly assessed as such |

### G. Missing-Data Question

| Field | Value |
|---|---|
| Input | `What important data is missing or unreliable?` |
| Routing | `FOLLOW_UP` → `agent.chat()` → `_answer_data_quality()` |
| Source | `data_quality_limitations` + `research_gaps` + `data_freshness` |
| Response | Explicit list of gaps; freshness status of financial statements and price |
| Key assertion | If peers are absent, this is flagged. If analyst estimates were unavailable, this is flagged. Response does not say "no gaps" |

### H. What-If Scenario

| Field | Value |
|---|---|
| Input | `At what price would ITC become attractive?` |
| Routing | `FOLLOW_UP` → `agent.chat()` → `_answer_valuation()` + FV range |
| Source | `FairValueRange` (bear/base/bull) from stored assessment |
| Response | Bear FV as entry zone; base FV as fair value; bear/base/bull prices named explicitly |
| Key assertion | Response uses stored FV numbers (₹154.66/₹233.02/₹332.53 for ITC.NS); does not recalculate |

### I. Follow-Up Context Retention

| Field | Value |
|---|---|
| Input | Turn 1: `Analyze ITC.NS` → Turn 2: `What about the dividend?` → Turn 3: `Does it affect the recommendation?` |
| Routing | Turn 2: `FOLLOW_UP` (session retains ITC.NS) → Turn 3: `FOLLOW_UP` |
| Source | `InvestmentDecisionAssessment` stored from Turn 1 |
| Response | Turn 2 answers dividend question from stored assessment; Turn 3 links dividend to decision |
| Key assertion | At no point does the agent ask the user "which stock?" — context is retained through the session |

### J. Invalid / Unknown Question

| Field | Value |
|---|---|
| Input | `What should I cook for dinner?` |
| Routing | `UNKNOWN_CLARIFICATION` |
| Source | ConversationManager |
| Response | Friendly clarification: explains what the agent can help with, suggests examples |
| Key assertion | No error thrown; no investment content fabricated; response is helpful, not dismissive |

### K. Missing Ticker

| Field | Value |
|---|---|
| Input | `Analyze this company for me` (no ticker) |
| Routing | `UNKNOWN_CLARIFICATION` |
| Source | ConversationManager |
| Response | Asks user to specify a ticker symbol (e.g. ITC.NS, CNR.TO) |
| Key assertion | Does not attempt to guess a ticker; does not use previous session's ticker |

### L. Data Freshness Issue

| Field | Value |
|---|---|
| Input | Analyse a ticker where yfinance cache is >30 days old |
| Routing | `INITIAL_ANALYSIS` → normal path, but `DataFreshnessAssessment` flags staleness |
| Source | `build_freshness_assessment()` → `data_freshness_cap_applied = True` |
| Response | Analysis runs, but decision panel shows staleness warning; confidence capped at LOW |
| Key assertion | `⚠ One or more data inputs are STALE` warning appears in decision panel |

### M. Contradictory Evidence

| Field | Value |
|---|---|
| Input | `Analyze a ticker with strong ROIC but weak moat research` |
| Routing | `INITIAL_ANALYSIS` → Gate 2 passes (financial quality) but Gate 1 is weaker |
| Source | `supporting_evidence` vs `contradictory_evidence` in `InvestmentDecisionAssessment` |
| Response | Highlights the tension: good financial metrics, but research gaps on moat durability |
| Key assertion | Both supporting and contradictory evidence are surfaced; recommendation reflects uncertainty |

### N. Explicit Recommendation Challenge

| Field | Value |
|---|---|
| Input | `I disagree with your WAIT recommendation. ITC is clearly undervalued.` |
| Routing | `FOLLOW_UP` → `agent.chat()` → `_answer_why()` or `_answer_what_would_change()` |
| Source | `gate_results` + `is_current_price_attractive` + `what_would_change_conclusion` |
| Response | States the specific valuation evidence for WAIT; explains what would change the recommendation (price below ₹233.02 base FV); does not capitulate or change its conclusion |
| Key assertion | The recommendation is defended with specific numbers from the stored assessment, not vague language; response does not change the recommendation based on user pushback alone |

---

## 12. Example End-to-End Conversation (ITC.NS)

*This example uses actual ITC.NS Phase 9.9b verified numbers.*

---

**User:** Analyze ITC.NS

**Agent:**
```
════════════════════════════════════════════════════════════
  Investment Decision: ITC Limited (ITC.NS)
  Analysis date: 2026-08-15
════════════════════════════════════════════════════════════

Current price:      278.20 INR  [FRESH]

ATTRACTIVENESS SUMMARY
──────────────────────────────────────────────────────────
  Business Quality (BQ):      STRONG
  Valuation Attractiveness:   LOW
  Investment Attractiveness:  LOW

DECISION
──────────────────────────────────────────────────────────
  Qualitative view:  High-quality conglomerate; price above fair value
  Final action:      WAIT
  Confidence:        MEDIUM

VALUATION
──────────────────────────────────────────────────────────
  Weighted fair value:  Bear ₹154.66  /  Base ₹233.02  /  Bull ₹332.53
  Current price ₹278.20 is above base fair value — zone: UNATTRACTIVE
  P/E implied:    ₹192.56 – ₹401.18    (Normalised EPS ₹16.05; cont-ops basis)
  P/FCF implied:  ₹144.45 – ₹300.93    (FCF/share ₹12.04; FY2024–FY2026 avg)
  EV/EBITDA:      ₹158.86 – ₹321.17
  DCF:            ₹128.77 – ₹349.79

INVESTMENT THESIS
──────────────────────────────────────────────────────────
  ...
```

---

**User:** Why WAIT?

**Agent:**
```
The WAIT recommendation reflects the combination of two gate outcomes:

Gate 2 — Financial Quality: PASS (quality tier: STRONG)
  ITC has demonstrated consistent financial quality. ROIC, FCF conversion,
  and margin stability all pass. Earnings quality is high; the FY2025 
  discontinued-ops gain (ITC Hotels demerger) is correctly excluded from
  the normalised EPS calculation.

Gate 3 — Valuation: CONSTRAINING
  The current price of ₹278.20 is above the base weighted fair value of
  ₹233.02. This puts the stock in the UNATTRACTIVE valuation zone. The
  philosophy states: "Do not initiate or add to a position when price 
  materially exceeds fair value."

Gates 1, 4, 5 did not force an override in either direction.

If the price were to fall to the bear fair value (₹154.66) with the thesis
intact, the recommendation would reconsider to START_SMALL or ACCUMULATE.
```

---

**User:** Why is P/FCF much lower than P/E?

**Agent:**
```
FCF/EPS RECONCILIATION for ITC Limited (ITC.NS):

DIRECTLY OBSERVED (stored in this assessment):
  EPS used in P/E valuation:          INR 16.05/share
  EPS normalization basis:            Normalized EPS: 3-year average of 
                                      continuing-ops derived EPS; years: 
                                      FY2024, FY2025, FY2026
  FCF/share used in P/FCF valuation:  INR 12.04/share
  FCF/share derivation:               3yr avg FY2024–FY2026

  Observed gap (EPS − FCF/share):     INR 4.01/share

NORMALIZATION BASIS:
  ✓ SAME-PERIOD BASIS — EPS and FCF/share both cover FY2024–FY2026.
  This gap is not a period-alignment artefact.

THE GAP (INR 4.01/share) CANNOT BE FULLY RECONCILED from stored data:
  Available line items for bridge:
    OCF (FY2024): ...  Capex (FY2024): ...
  Missing line items (not stored in this assessment):
    D&A  —  not stored
    Working capital changes  —  not stored
    Tax timing items  —  not stored

The FCF/share (₹12.04) is lower than EPS (₹16.05) primarily because FCF
subtracts capital expenditure that is not deducted in net income. ITC's
capex intensity is a known characteristic of its diversified business.
[INFERENCE — exact capex decomposition requires data not in this assessment]
```

---

**User:** What is the biggest weakness in your analysis?

**Agent:**
```
Key limitations of this ITC.NS analysis:

DATA GAPS:
  • No analyst consensus EPS estimates available — forward growth assumptions
    rely on historical CAGR only.
  • Peer data not available — EV/EBITDA and P/FCF peer comparison could not
    be performed. Peer valuation method excluded from weighted synthesis.
  • D&A and working capital breakdown not available from yfinance — FCF/EPS
    reconciliation is partial.

RESEARCH GAPS:
  [Depends on whether AnthropicResearcher was used]
  If qualitative research was performed:
  • Management quality evidence was rated T2/T3 — no primary source 
    confirmation from recent investor day or filing.
  If quantitative fallback was used:
  • All qualitative dimensions (moat, management, industry) are research gaps.
    Gate 1 blocked → recommendation is WAIT_INSUFFICIENT_EVIDENCE, not WAIT.

STRUCTURAL LIMITATION:
  • The FY2025 ITC Hotels demerger is a one-time event. The FY2026 continuing-
    ops picture is the first "clean" post-demerger year. A 3-year average that 
    includes FY2024 (pre-demerger) may not fully reflect the new ITC structure.
    This is flagged as an assumption, not a finding.
```

---

**User:** At what price would ITC become attractive?

**Agent:**
```
Based on the current Phase 9.9b verified valuation for ITC.NS:

  Bear fair value:  ₹154.66  ← START_SMALL zone entry
  Base fair value:  ₹233.02  ← ACCUMULATE zone entry
  Bull fair value:  ₹332.53  ← upper bound

  Current price:    ₹278.20  ← UNATTRACTIVE zone (above base)

A price below ₹233.02 (base FV) with the thesis intact would move the
recommendation to WATCH → ACCUMULATE. Below ₹154.66 (bear FV), the
investment becomes attractively priced even under conservative assumptions,
suggesting START_SMALL.

These are valuation thresholds only. The thesis (business quality, moat,
risk profile) must remain intact at the time of purchase — a price decline
caused by a thesis-breaker event (e.g. ROIC declining below 12%) would not
make ITC attractive even at ₹154.66.
```

---

**User:** What would change your recommendation?

**Agent:**
```
WHAT WOULD CHANGE THE CONCLUSION

Towards ACCUMULATE / START_SMALL:
  • Price falls below ₹233.02 (base FV) with no adverse change in business quality.
  • Price falls below ₹154.66 (bear FV) — clearly attractive under conservative assumptions.
  • New information materially improves the FCF growth outlook (e.g. confirmed 
    FMCG margin expansion, Hotels demerger synergies realised).

Towards REDUCE / EXIT:
  • ROIC declining below 12% for 3 consecutive years — moat erosion signal.
  • Sustained regulatory action on ITC's cigarette business impairing pricing power.
  • ITC Hotels demerger creates unexpected capital allocation deterioration.
  • Management announces acquisition that destroys capital (dilutive at low returns).

These triggers are taken directly from the stored thesis breakers and 
what_would_change_conclusion fields. [FACT — sourced from assessment]
```

---

*Note: The above responses are what the EXISTING engine produces. No new capability was described. The METRIC_EXPLANATION intent (Journey 4, "What is ROIC?") is the only new response type that Phase 10 adds outside the existing renderer.*

---

## 13. Security / Privacy Considerations

### 13.1 What Could the Conversational Layer Accidentally Expose?

| Risk | Current Exposure | Mitigation |
|---|---|---|
| ANTHROPIC_API_KEY | In environment variable; never in `InvestmentDecisionAssessment` | Keep env var handling in `run_agent.py` / `ConversationManager`. Never pass key through session state. Never display in UI. |
| Portfolio data (`portfolio_snapshot.csv`) | Gitignored; never loaded by current pipeline | Do not add CSV loading to `ConversationManager`. Portfolio weight only, via UI input field. |
| Raw yfinance cache JSON | Local only; gitignored; contains real financial data | Do not expose file paths or raw JSON in UI. |
| Data cache file paths | Internal paths visible in `DataLoadResult` | `ConversationManager` must not pass raw `DataLoadResult` to UI. Only pass `InvestmentDecisionAssessment`. |
| Internal prompts (`agent/prompts/*.md`) | Local only | Do not expose prompt text in UI. |
| `InvestmentDecisionAssessment` fields | All fields are analysis output, not personal data | Acceptable to display all assessment fields in UI. |
| Debug traces | Python tracebacks from pipeline errors | `ConversationManager` must catch all exceptions and render a clean error message. Never expose a stack trace to the UI. |
| `decisions/` JSON files | Generated output; gitignored | Do not load from decisions/ in the UI. Session-only state is sufficient. |

### 13.2 Minimum Safeguards for MVP

1. **`ANTHROPIC_API_KEY` from environment only** — never from UI input field, never stored in session state.
2. **Portfolio weight only** — the UI's portfolio input accepts a percentage (e.g. "4.1") and passes it as `portfolio_weight_pct`. No other portfolio field.
3. **Exception boundary** — `ConversationManager.route()` wraps all pipeline calls in try/except. Errors produce a clean message string, not a traceback.
4. **No file-path exposure** — data cache paths stay inside the pipeline. The UI only sees the `InvestmentDecisionAssessment` output.
5. **No database** — session state lives in `st.session_state` only. No write to disk by the UI layer.
6. **Gitignore verified** — the existing `.gitignore` covers: `data/cache/`, `data/output/`, `portfolio/`, `decisions/`, `.env`. No additions needed for Phase 10 unless new output files are introduced.

---

## 14. Phase 10 Scope

### MUST HAVE — Phase 10 MVP

1. `run_ui.py` entry point (`streamlit run run_ui.py`)
2. `ui/app.py` Streamlit application
   - Ticker input + portfolio weight input
   - Analyse button → calls `ConversationManager.run_analysis(ticker, weight)`
   - Decision panel: action, confidence, price, FV (headline metrics)
   - Full analysis expander (renders `render_assessment()` output)
   - Chat panel: conversation history + input box
3. `conversation/session.py` — `ConversationSession` + `ChatTurn`
4. `conversation/manager.py` — `ConversationManager` with:
   - `run_analysis(ticker, weight)` — calls full pipeline (fix for Gap 2)
   - `route(user_text)` — routes to `agent.chat()` or own handlers
   - Exception boundary (fix for Gap 3 edge cases)
5. `conversation/intent.py` — extended intent classifier (14 intents)
   - METRIC_EXPLANATION handler (general financial terms)
   - UNKNOWN_CLARIFICATION handler
   - All other intents delegate to `agent.chat()`
6. Loading state during analysis (spinner/status)
7. Error display (clean messages, no tracebacks)
8. Session state: chat history preserved within ticker session; cleared on new ticker

### SHOULD HAVE — Phase 10 if Low Effort

- Valuation method breakdown table (P/E / P/FCF / EV/EBITDA / DCF in a 4-column `st.columns` layout)
- Data freshness indicator in the decision panel header
- "Reload" button to re-print full analysis without re-fetching
- "New ticker" button that clears session and returns to analysis input
- `--no-browser` flag for `run_ui.py` (headless mode for testing)

### FUTURE — Phase 11+

- Multi-ticker comparison
- Watchlist with saved analyses
- Charts (fair value vs price over time, valuation method comparison)
- Portfolio-aware conversations (what is the right position size given my full portfolio?)
- Saved analyses on disk with retrieval
- Historical analysis comparison (did the thesis hold?)
- Scenario analysis with user-adjustable DCF parameters
- Cloud deployment and authentication
- Email/export of analysis report
- Automatic re-analysis on price alerts

---

## 15. File-Level Implementation Plan

### NEW FILES

| Path | Purpose |
|---|---|
| `run_ui.py` | Entry point: `streamlit run run_ui.py`. Minimal — sets up sys.path and calls `ui/app.py`. |
| `ui/__init__.py` | Package marker |
| `ui/app.py` | Streamlit application. Analysis panel + conversation panel. Reads from `ConversationSession`. Writes to `st.session_state`. No analytics logic. |
| `conversation/__init__.py` | Package marker |
| `conversation/session.py` | `ConversationSession` dataclass + `ChatTurn` dataclass. Pure data — no analytics. |
| `conversation/manager.py` | `ConversationManager`. Owns: `run_analysis()` pipeline call path, `route()` intent dispatch, exception boundary. Uses `InvestmentAgent` as the analytics engine. |
| `conversation/intent.py` | `classify_intent()` — 14-intent classifier. Wraps `parse_intent()` from `analytics/agent/intent_parser.py` for ANALYZE/FOLLOW_UP intents; adds METRIC_EXPLANATION, EVIDENCE_REQUEST, SCENARIO_WHAT_IF, UNKNOWN_CLARIFICATION. |
| `tests/test_phase10_conversation.py` | Unit tests for `ConversationSession`, `ConversationManager.route()`, intent classification |
| `tests/test_phase10_ui.py` | Smoke tests for `ConversationManager.run_analysis()` using CNR.TO demo data |

### MODIFIED FILES

| Path | Why |
|---|---|
| `requirements.txt` (new if not exists) | Add `streamlit`, `anthropic` as explicit dependencies. Currently no requirements file exists — this is a gap. |

That is the complete list of modifications. No other files change.

### UNCHANGED CORE FILES

| Path | Why Not Touched |
|---|---|
| `analytics/agent/investment_agent.py` | The `InvestmentAgent` interface is the stable boundary. `chat()` and `analyze()` are called, not modified. |
| `analytics/agent/intent_parser.py` | The existing 3-intent parser is wrapped, not replaced. |
| `analytics/agent/renderer.py` | All 1,367 lines stay. The UI calls `render_assessment()` and `render_followup()` via `InvestmentAgent`. |
| `analytics/agent/data_loader.py` | Called by `ConversationManager` via `InvestmentAgent.analyze()`. |
| `analytics/agent/valuation_builder.py` | Called inside the pipeline. No changes. |
| `analytics/agent/research_orchestrator.py` | No changes. |
| `analytics/agent/anthropic_researcher.py` | No changes. |
| All `analytics/decision/` | All gate evaluators unchanged. |
| All `analytics/financial_quality/` | No changes. |
| All `analytics/valuation/` | No changes. |
| All `analytics/business_research/` | No changes. |
| All `analytics/portfolio/` | No changes. |
| `data/ingestion/` | No changes. |
| `config/` | No changes. |
| `run_agent.py` | Still works as before. Parallel entry point. |
| `run_analysis.py` | Still works as before. |
| All existing `tests/` | No changes. Phase 9.9b baseline must remain PASS. |

### How New Files Interact with the Existing Architecture

```
run_ui.py
  └─ imports ui/app.py

ui/app.py
  ├─ st.session_state["session"] = ConversationSession()
  ├─ st.session_state["manager"] = ConversationManager()
  ├─ calls manager.run_analysis(ticker, weight) on button click
  └─ calls manager.route(user_text) on chat submit

conversation/manager.py
  ├─ from analytics.agent.investment_agent import InvestmentAgent
  ├─ from analytics.agent.data_loader import load_ticker
  ├─ from analytics.agent.research_orchestrator import ResearchOrchestrator
  ├─ from analytics.agent.valuation_builder import build_valuation_input
  ├─ from analytics.valuation.valuation_synthesizer import run_valuation
  ├─ from conversation.intent import classify_intent
  └─ from conversation.session import ConversationSession, ChatTurn

conversation/intent.py
  └─ from analytics.agent.intent_parser import parse_intent, INTENT_ANALYZE, INTENT_FOLLOW_UP
     (delegates ANALYZE and FOLLOW_UP classification to existing parser)
```

---

## 16. Testing Strategy

### 1. Unit Tests (new, in `tests/test_phase10_conversation.py`)

- `ConversationSession`: initialises correctly; ticker/assessment set correctly after analysis
- `ConversationManager.route()`: each of the 14 intents routes to the correct handler
- `classify_intent()`: 14 intent classifications covering representative inputs
- Exception boundary: pipeline exception → clean error string, not raised
- Context retention: follow-up after analysis uses stored assessment, not re-running pipeline

### 2. Conversation-Routing Tests

- All 9 journeys (Part 2) route to the correct handler with the correct source
- METRIC_EXPLANATION does not use `agent.last_assessment` when no analysis has run
- UNKNOWN_CLARIFICATION never fabricates analysis content

### 3. State / Context Tests

- `ConversationSession.chat_history` accumulates correctly across turns
- After new-ticker analysis, previous history is cleared
- `portfolio_weight_pct` is preserved across follow-up turns without user re-entering it
- `assessment` is `None` before first analysis; populated after; updated on re-analysis

### 4. Integration Tests

- `ConversationManager.run_analysis("CNR.TO", weight=None)` using CNR.TO demo path (no network)
- `ConversationManager.route("Why WAIT?")` after CNR.TO analysis → returns non-empty string
- `ConversationManager.route("Analyze XYZ.FAKETHIS")` with failing fetch → clean error message

### 5. UI Smoke Tests

- Streamlit app imports without error
- `ui/app.py` contains expected widget definitions (ticker input, chat input, analyse button)
- No test requires a running browser (use `streamlit.testing.v1.AppTest` if available)

### 6. End-to-End Acceptance Tests

The Phase 10 acceptance-test catalogue (Part 11, sections A–N) serves as the end-to-end acceptance test list. These are run manually through the UI during Product Owner testing.

### Regression Protection

After Phase 10 implementation:
```
python -m pytest                          # must still produce 1071 passed, 0 failed
python -m pytest tests/test_phase99.py   # Phase 9.9b suite must remain PASS
python -m pytest tests/test_phase10_*.py # Phase 10 new tests must pass
```

No existing test file may be modified to make Phase 10 pass.

---

## 17. Implementation Sequence

### Step 1 — Conversation Contracts
Create `conversation/session.py`: `ConversationSession` + `ChatTurn` dataclasses. No logic. Write unit tests first.

### Step 2 — Intent Classifier
Create `conversation/intent.py`: `classify_intent()` wrapping `parse_intent()` and adding 4 new intents. Write tests. Confirm existing 10-intent FOLLOW_UP subtypes still delegate correctly.

### Step 3 — Conversation Manager (without UI)
Create `conversation/manager.py`: `ConversationManager` with `run_analysis()` and `route()`. The `run_analysis()` method replicates the live-fetch path from `run_agent.py` (lines 383–465) as a callable function. Test with CNR.TO demo data. Confirm exception boundary works.

### Step 4 — Streamlit UI
Create `ui/app.py`: analysis panel + conversation panel. Wire to `ConversationManager`. Test manually with CNR.TO demo (no API key required).

### Step 5 — Entry Point
Create `run_ui.py`. Confirm `streamlit run run_ui.py` opens browser and shows the interface.

### Step 6 — Live Path Testing
Test with a real ticker (ITC.NS) with `ANTHROPIC_API_KEY` set. Confirm full pipeline runs, analysis appears in UI, and follow-up questions work.

### Step 7 — Acceptance Testing
Run Phase 10 acceptance-test catalogue (A–N) manually. Fix routing gaps discovered. Confirm Phase 9.9b regression test still passes.

---

## 18. Risks and Trade-offs

### Risk 1: Analysis latency in the UI
**Problem:** A full analysis (yfinance fetch + Anthropic API research for 7 steps + valuation + decision) takes 15–60 seconds. Streamlit re-runs the entire script on every interaction.

**Mitigation:** `st.session_state` caches the completed `InvestmentDecisionAssessment`. The analysis pipeline only runs when the Analyse button is clicked, not on follow-up question submission. Use `st.status` to show incremental progress during analysis.

### Risk 2: ConversationManager duplicates run_agent.py logic
**Problem:** `run_agent.py` lines 383–465 contain the live-fetch + research + valuation + decision pipeline. `ConversationManager.run_analysis()` must replicate this. Duplication risks divergence.

**Mitigation:** Extract the pipeline into a standalone function `analytics/agent/pipeline.py` (or `run_pipeline()`) that both `run_agent.py` and `ConversationManager` call. This is a refactor, not a rewrite. The function signature mirrors `run_agent.py`'s logic exactly.

### Risk 3: Streamlit's session state model
**Problem:** Streamlit session state is per-browser-tab. If the user opens two tabs, they get independent sessions. This is actually correct for a single-user local tool, but could confuse the Product Owner.

**Mitigation:** Document this behaviour. No fix needed for MVP.

### Risk 4: Anthropic package not installed
**Problem:** `anthropic` is not currently installed in the development environment (confirmed). The UI must work without it (quantitative fallback path).

**Mitigation:** The existing try/except guard in `run_agent.py` already handles this. `ConversationManager` replicates the same guard. The UI shows a clear notice when qualitative research is unavailable.

### Risk 5: Chat input re-routing the intent incorrectly
**Problem:** The existing `intent_parser.py` was designed for the CLI REPL. Some phrasing that works in the terminal may not route correctly when typed into a chat box.

**Mitigation:** The acceptance-test catalogue (A–N) covers edge cases. The extended `classify_intent()` in Phase 10 adds a second layer of classification for the new intents. Existing follow-up routing inside `renderer.py` is unchanged and has 1,071 passing tests behind it.

---

## 19. Future Extension Points

The Phase 10 architecture is designed to support these without restructuring:

| Future Capability | Extension Point |
|---|---|
| Multi-ticker comparison | `ConversationSession` adds `assessments: Dict[str, IDA]`; UI adds a ticker selector |
| Saved analyses | `ConversationManager.save_analysis()` writes `InvestmentDecisionAssessment` to `data/output/`; `load_analysis()` reads it |
| Charts (FV vs price over time) | Streamlit: `st.plotly_chart()` call in `ui/app.py`; data from `data/cache/*.json` price history |
| DCF scenario sliders | UI: `st.slider()` inputs for growth/discount rate; `ConversationManager` calls `run_valuation()` with modified `ValuationInput` |
| Portfolio-aware conversations | `ConversationManager` reads `portfolio/portfolio_snapshot.csv` (weight %) and passes to `build_portfolio_context()` |
| Watchlist | `ConversationSession` adds `watchlist: List[str]`; persisted in `portfolio/watchlist.csv` |
| Cloud deployment | `run_ui.py` unchanged; add a `Dockerfile` and `streamlit.toml` |
| Authentication | Streamlit Authenticator or external auth proxy; no analytics code changes |
| Historical analysis | `data/output/` JSON files indexed by ticker + date; new `history/` loader |

---

## 20. Final Recommendation

### Recommended Architecture
Thin conversational layer over the existing `InvestmentAgent`. Three new modules (`conversation/session.py`, `conversation/manager.py`, `conversation/intent.py`) plus a Streamlit UI (`ui/app.py`). Everything in `analytics/` unchanged.

### Recommended UI Technology
**Streamlit.** Install: `pip install streamlit`. Single Python file. No JavaScript. Handles structured analysis display, chat UX, and future chart integration natively.

### MVP Scope
- Streamlit UI with analysis panel + conversation panel
- `ConversationManager` with `run_analysis()` (fix for Gap 2) and `route()` (fixes for Gap 3)
- Extended intent classifier (14 intents; 10 delegate to existing renderer)
- Session state in `st.session_state` (no database)
- Full pipeline working end-to-end through the UI

### Files Expected to Change
- **New:** `run_ui.py`, `ui/__init__.py`, `ui/app.py`, `conversation/__init__.py`, `conversation/session.py`, `conversation/manager.py`, `conversation/intent.py`, `tests/test_phase10_conversation.py`, `tests/test_phase10_ui.py`, `requirements.txt`
- **Modified:** None from the existing codebase
- **Unchanged:** All `analytics/`, `data/`, `config/`, `tests/test_phase*.py`, `run_agent.py`, `run_analysis.py`

### Major Risks
1. Analysis latency (15–60s) — mitigated by session caching and st.status progress
2. `run_agent.py` pipeline logic duplication — mitigated by extracting a `run_pipeline()` function
3. `anthropic` package not installed — mitigated by existing try/except guard

### Estimated Implementation Complexity
**Medium** — the analytics engine is complete and tested. The hard part is the `ConversationManager.run_analysis()` path, which extracts and wraps the existing `run_agent.py` live-fetch logic. The UI itself is straightforward Streamlit. The intent classifier extension is low-risk because it wraps, not replaces, the existing parser.

---

*Phase 10 design complete. No files modified. No commits created. Awaiting authorization to implement.*
