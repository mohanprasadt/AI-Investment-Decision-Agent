# Architecture Diagrams: Current Implementation and Proposed Target

| Field | Value |
|---|---|
| Last reviewed | 2026-10-11 |
| Baseline | `main` at `f6c3502` plus the uncommitted Phase 11A/11B working tree (14 modified, 6 untracked files) |
| Authoritative status | [Product Feature Inventory and Roadmap](../product/product-feature-inventory-and-roadmap.md) |
| Maintenance rules | [Roadmap Maintenance Protocol](../governance/roadmap-maintenance-protocol.md) |
| Complements | [Architecture Overview](architecture-overview.md) (Phase 10.6 narrative, ASCII), [Component Architecture](component-architecture.md), [Data Flow](data-flow.md) |

This document holds the maintained diagrams. The older overview documents describe Phase 10.6 and do not show the Decision Trace, scenario engine or Phase 11B evidence handling.

**Important reading notes**

- The product is **one Python process** (Streamlit) plus optional command-line scripts. Boxes are **modules and packages**, not services. There is no database, queue or network service of the product's own.
- Arrow legend: solid arrow = control flow or call; labelled "data" = object passed; dashed arrow = persistence or optional path.
- Modules marked `(uncommitted)` exist only in the working tree.
- Only the relationships I verified by reading code are drawn. The reading was deep for the pipeline, manager, agent, Gate 5, trace, scenario engine and synthesizer sequencing, and lighter for valuation and portfolio internals.

---

## Diagram A: Current implementation architecture

```mermaid
flowchart TB
    User(["User / Product Owner"])

    subgraph Entry["Entry points"]
        RunUI["run_ui.py<br/>starts Streamlit"]
        RunAgent["run_agent.py<br/>CLI, includes CNR.TO demo path"]
        Prewarm["scripts/prewarm_mvp.py<br/>cache pre-warm"]
    end

    subgraph UI["ui/ (Streamlit, one process)"]
        App["ui/app.py<br/>ticker dropdown, weight, Analyse,<br/>Force Refresh, chat, trace expander,<br/>what-if panel"]
        DataStatus["ui/data_status.py<br/>cache status reader"]
    end

    subgraph Conv["conversation/"]
        Manager["manager.py<br/>ConversationManager"]
        Intent["intent.py<br/>6 intents, regex"]
        Session["session.py<br/>in-memory state"]
    end

    subgraph AgentPkg["analytics/agent/"]
        IParser["intent_parser.py"]
        InvAgent["investment_agent.py<br/>InvestmentAgent: analyze, chat"]
        Pipeline["pipeline.py<br/>run_analysis_pipeline<br/>never raises, fail-fast 429"]
        Loader["data_loader.py"]
        Orch["research_orchestrator.py<br/>context build + bull/bear parse<br/>evidence-boundary validator (uncommitted edits)"]
        Researcher["anthropic_researcher.py<br/>Claude API client"]
        ValBuilder["valuation_builder.py<br/>EPS/FCF same-period alignment"]
        Renderer["renderer.py<br/>report + follow-up answers<br/>_md_safe"]
    end

    subgraph DataPkg["data/ingestion/"]
        Fetcher["fetcher.py<br/>yfinance + JSON cache"]
        Normalizer["normalizer.py<br/>CompanyFinancialMetrics"]
    end

    subgraph Analytics["analytics/ (analysis engines)"]
        FQ["financial_quality/<br/>quality_engine, thresholds,<br/>calculations"]
        BR["business_research/<br/>models, moat, synthesizer"]
        Val["valuation/<br/>DCF, multiples, method selector,<br/>margin of safety, synthesizer"]
        Port["portfolio/<br/>weight-only context,<br/>concentration, scenarios"]
        Fresh["data_freshness.py"]
    end

    subgraph Gates["analytics/decision/"]
        Synth["decision_synthesizer.py<br/>make_investment_decision<br/>_select_action, confidence,<br/>freshness cap, price suppression"]
        G1["gate1_understanding"]
        G2["gate2_quality"]
        G3["gate3_valuation"]
        G4["gate4_portfolio"]
        G5["gate5_adversarial<br/>evaluate_gate5 + extract_thesis_breakers"]
        Trace["decision_trace.py (uncommitted)<br/>build + render trace"]
        Scen["scenario_engine.py (uncommitted)<br/>run_scenario, baseline immutable"]
        Models["decision_models.py<br/>InvestmentDecisionAssessment,<br/>ThesisBreaker, ScenarioResult"]
    end

    subgraph Cfg["config/"]
        Thresholds["thresholds.yaml<br/>valuation_config.yaml<br/>investment_philosophy.md"]
    end

    subgraph Store["Local storage (git-ignored)"]
        Cache[("data/cache/*.json<br/>TTL 24-48h")]
        Output[("data/output/<br/>TICKER_DATE_decision.json")]
    end

    subgraph Ext["External services"]
        Yahoo["Yahoo Finance via yfinance<br/>unofficial, rate-limited"]
        Claude["Anthropic API<br/>needs ANTHROPIC_API_KEY"]
    end

    User --> RunUI --> App
    User --> RunAgent
    App -->|"analyse / chat text"| Manager
    App --> DataStatus
    DataStatus -.->|"reads"| Cache
    Manager --> Intent
    Intent --> IParser
    Manager --> Session
    Manager -->|"run_analysis"| Pipeline
    Manager -->|"follow-up"| InvAgent
    RunAgent --> Pipeline
    InvAgent --> IParser
    InvAgent -->|"follow-up text + stored assessment"| Renderer

    Pipeline --> Loader --> Fetcher
    Fetcher <-->|"HTTP"| Yahoo
    Fetcher <-.->|"read / write"| Cache
    Loader --> Normalizer --> FQ
    Pipeline --> Orch
    Orch --> Researcher
    Researcher <-->|"HTTPS, optional"| Claude
    Orch --> BR
    Pipeline --> ValBuilder --> Val
    Pipeline -->|"analyze"| InvAgent
    InvAgent --> Port
    InvAgent --> Synth
    Fresh --> Synth
    Synth --> G1 --> G2 --> G3 --> G4 --> G5
    G5 --> Synth
    Synth --> Models
    FQ --> Thresholds
    Val --> Thresholds
    InvAgent -->|"assessment"| Renderer
    Renderer -->|"report text"| Pipeline
    Pipeline -.->|"_persist_decision"| Output
    Pipeline -->|"PipelineResult"| Manager
    App -->|"Why this decision?"| Trace
    Trace -->|"reads"| Models
    App -->|"Apply Scenario"| Scen
    Scen -->|"reads, never mutates"| Models
    Prewarm --> Fetcher
```

**What the diagram shows, and what it does not**

| Observation | Evidence |
|---|---|
| Pipeline is the only place that assembles the full sequence; manager and CLI both call it | `pipeline.py` header; `manager.py` header |
| Gates run in order 1, 2, 3, 4, 5, then `_select_action` | `decision_synthesizer.py:169-210` |
| `extract_thesis_breakers` runs after action selection; monitoring-only items are display-only | `decision_synthesizer.py:225`; `gate5_adversarial.py:284-312` |
| The UI calls the trace builder and scenario engine directly, bypassing the manager | `ui/app.py:391, 460` |
| The persisted JSON does not contain the trace, `unsupported_evidence` or scenario results | key list of persisted files; grep (FND-5, FND-10) |
| Scenario results and trace are recomputed on demand and never stored | no persistence call found |
| `.env.example` lists FMP, Alpha Vantage and Polygon keys but no code uses them, so those providers are **not** shown | grep |

---

## Diagram B: Decision-processing flow

```mermaid
flowchart TD
    Start(["User asks to analyse a ticker"]) --> Intent{"Intent?"}
    Intent -->|"follow-up on stored result"| FollowUp["Answer from stored assessment<br/>no new data calls"]
    Intent -->|"unknown"| Clarify["Friendly clarification prompt"]
    Intent -->|"analyse"| Load["Load ticker data<br/>cache first, else Yahoo"]

    Load -->|"HTTP 429"| RateErr["PipelineResult.is_rate_limited<br/>friendly message, no retry"]
    Load -->|"fetch error"| FetchErr["Friendly data error<br/>raw text only in logs"]
    Load -->|"ok"| Norm["Normalize to CompanyFinancialMetrics<br/>quality assessment"]

    Norm --> Key{"API key and<br/>researcher available?"}
    Key -->|"yes"| LLM["Claude research:<br/>moat, management, industry,<br/>bull/bear, thesis breakers"]
    Key -->|"no"| Quant["Quantitative fallback<br/>no qualitative research"]
    LLM --> Boundary["Evidence-boundary validator:<br/>5-year CAGR and carbon-price patterns<br/>violations moved to unsupported_evidence"]
    Boundary --> Val
    Quant --> Val["Build valuation input<br/>EPS/FCF same-period alignment<br/>run 4 valuation methods"]

    Val --> G1{"Gate 1<br/>business understood?"}
    G1 -->|"no"| Early["Early stop:<br/>WAIT_INSUFFICIENT_EVIDENCE"]
    G1 -->|"yes"| G2["Gate 2 quality"]
    G2 --> G3["Gate 3 valuation"]
    G3 --> G4["Gate 4 portfolio fit<br/>weight % only"]
    G4 --> G5["Gate 5 adversarial<br/>severity from breaker likelihoods<br/>UNKNOWN counts as MEDIUM-equivalent"]
    G5 --> Select["Select action<br/>8 possible actions"]
    Select --> Conf["Compute confidence"]
    Conf --> Breakers["Extract thesis breakers<br/>add monitoring-only indicators"]
    Breakers --> Fresh{"Price stale<br/>or unknown?"}
    Fresh -->|"yes"| Pending["WATCH_PENDING_DATA<br/>freshness confidence cap"]
    Fresh -->|"no"| Narr["Build narrative and conclusions"]
    Pending --> Narr
    Early --> Render
    Narr --> Render["Render report"]
    Render --> Persist["Persist decision JSON<br/>non-fatal on failure"]
    Persist --> Resp(["Response in UI + chat enabled"])

    Resp --> Why["Why this decision?<br/>Decision Trace rebuilt on demand"]
    Resp --> WhatIf["What-if panel:<br/>override breaker likelihoods"]
    WhatIf --> Scn["Recalculate Gate 5 severity and action<br/>baseline untouched, nothing stored"]
    Resp --> FollowUp
    FollowUp --> Route{"Follow-up router<br/>renderer.render_followup"}
    Route -->|"breaker / likelihood question"| Brk["Breaker-specific answer"]
    Route -->|"other topics"| Other["Valuation, risks, FCF vs EPS,<br/>data quality, why"]
```

**Failure and insufficient-evidence paths present in code:** rate-limit short-circuit, fetch error, Gate 1 early stop, missing API key (quantitative fallback leads to Gate 1 stop), stale/unknown price (WATCH_PENDING_DATA), persistence failure (logged, ignored), unknown intent (clarification).

**Known defect on this flow (FND-1):** in the working tree the follow-up router sends questions containing "why" and a word such as "lower" to the breaker-likelihood answer, so an FCF-vs-EPS question can return "No thesis breakers are recorded".

---

## Diagram C: Proposed target architecture (PROPOSED, NOT IMPLEMENTED)

Included because the current architecture has gaps that the roadmap already treats as work: persisted output lacks provenance and audit fields, evidence validation is scattered and pattern-based, rendering safety is per-call, and there are no cross-surface tests. **Nothing in this diagram exists today.** Every proposed element is tied to a roadmap item and is subject to owner decisions (PD-1 to PD-7).

```mermaid
flowchart TB
    subgraph Today["Existing modules (unchanged)"]
        Pipe["pipeline.py"]
        Orch2["research_orchestrator.py"]
        Synth2["decision_synthesizer + gates"]
        Rend2["renderer.py"]
        App2["ui/app.py"]
    end

    subgraph Proposed["PROPOSED, NOT IMPLEMENTED"]
        Claims["Evidence boundary component<br/>one module, one contract<br/>supported / unsupported / hypothesis<br/>roadmap F3.4, decision PD-3"]
        RunStore["Run store v2<br/>schema version, run id, model id,<br/>prompt version, code version,<br/>data timestamps, trace,<br/>unsupported_evidence, scenario results<br/>no silent overwrite<br/>roadmap F12.1, F12.4, decision PD-2"]
        History["History reader and comparer<br/>thesis change detection<br/>roadmap F12.2, F17.3"]
        Safe["Central render-safety helper<br/>$, &lt;, &gt; and markdown escape<br/>one place for UI and chat<br/>roadmap F9.4"]
        Contract["Cross-surface contract tests<br/>report = chat = trace = JSON<br/>roadmap F9.5, F14.5"]
        Stable["Gate 5 stability measurement<br/>repeat-run harness and report<br/>roadmap F8.1, decision PD-1"]
    end

    Orch2 --> Claims
    Claims --> Synth2
    Synth2 --> RunStore
    Pipe --> RunStore
    RunStore --> History
    Rend2 --> Safe
    App2 --> Safe
    Contract -.->|"verifies"| Rend2
    Contract -.->|"verifies"| RunStore
    Stable -.->|"measures"| Synth2
```

| Proposed element | Why it is needed (evidence) | Roadmap item |
|---|---|---|
| Evidence boundary component | Two narrow patterns; fallback detected by label text; `unsupported_evidence` not persisted (FND-5) | F3.4 |
| Run store v2 | Same-day rerun overwrites; no provenance; trace and scenarios not stored (FND-10) | F12.1, F12.4 |
| History reader and comparer | CNQ.TO changed HOLD to REDUCE across runs and nothing records why (FND-3) | F12.2, F17.3 |
| Central render-safety helper | `_md_safe` escapes `<` and `>` only; `$` unhandled in 41 render calls (FND-4) | F9.4 |
| Cross-surface contract tests | 56 follow-up regressions reached the tree unnoticed (FND-1, FND-2) | F9.5 |
| Stability measurement | Gate 5 outcome varies with LLM-regenerated breakers (FND-3) | F8.1 |

Deliberately **not** proposed: a database server, a microservice split, an agent framework or a new UI stack. The evidence does not justify them for a single-user local tool.

---

## Key design decisions currently embodied in the code

| Decision | Where | Status |
|---|---|---|
| Sequential gates instead of a weighted score | `decision_synthesizer.py` | Implemented; validated by `test_decision.py` |
| Portfolio privacy: weight % only | `manager.py`, `portfolio_models.py` | Implemented; validated |
| Follow-ups reuse stored assessment, no new data calls | `investment_agent.py`, `renderer.py` | Implemented; **currently regressed** (FND-1) |
| Fail-fast on HTTP 429 in the interactive path | `pipeline.py` | Implemented; validated by unit tests |
| Scenario engine never mutates the baseline | `scenario_engine.py` | Implemented; validated |
| UNKNOWN likelihood is MEDIUM-equivalent for severity only | `gate5_adversarial.py` | Implemented; open question PD-1 |
| Monitoring-only breakers excluded from severity | `gate5_adversarial.py` | Implemented; awaiting live acceptance |

## Maintenance

Update the affected diagram **in the same work item** whenever a feature changes module boundaries, data flow, decision processing, persistence or interfaces (protocol step 6). Diagram C elements move into Diagram A only when the related roadmap item is Implemented **and** Validated; then remove the "PROPOSED" label for that element.

## Revision history

| Date | Change | Roadmap item(s) |
|---|---|---|
| 2026-10-11 | Initial diagrams from discovery review | F15.3 |
