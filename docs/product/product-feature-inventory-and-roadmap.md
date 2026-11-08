# Product Feature Inventory and Roadmap (authoritative, living)

> **This is the single authoritative record of feature status for the AI Investment Decision Agent.** Other documents may link here but must not copy its status tables. Maintenance rules: [Roadmap Maintenance Protocol](../governance/roadmap-maintenance-protocol.md). Diagrams: [Architecture Diagrams](../architecture/architecture-diagrams.md).

| Field | Value |
|---|---|
| Last reviewed | 2026-11-06 |
| Document status | **Baseline v1.0, awaiting Product Owner review** (priorities, scope and sequencing are proposals, not agreed commitments) |
| Repository baseline | Branch `main`, 1 commit ahead of `origin/main`. HEAD `f6c3502` (2026-09-28, 'Phase 10-10.6'), parent `03ef8b1` (Phase 9.9b). Working tree: 14 modified and 6 untracked files (all Phase 11A/11B work), none committed |
| Scope | Whole product: data, research, valuation, portfolio, five gates, Gate 5, trace, chat, scenarios, UI, persistence, tests, docs, operations |
| Inspection method | Code, tests, configuration, persisted outputs and docs read directly; tests executed in scratch copies of the working tree and of `git archive HEAD` (the user's repo and Git state were not modified by test runs) |

## 1. How to read this document

**Counts below are counts of roadmap features (rows in the inventory), not test cases.** Features that are not implemented are counted under validation status 'Not validated' because there is nothing to validate yet.

**Implementation status:** Implemented = functionality exists in the code. Partially implemented = some exists, meaningful requirements remain. Not implemented = absent. Requires investigation = implementation or intended behaviour unclear. Retired/superseded = no longer in the agreed direction.

**Validation status:** Validated = relevant tests or acceptance checks show intended behaviour. Partially validated = some aspects pass, coverage or runtime validation incomplete. Not validated = no adequate evidence. Blocked = cannot be validated because of an identified dependency or environment limit. Failed = validation exposed an unresolved defect. *Implemented does not mean validated.*

**Priorities (proposed):**

| Priority | Meaning | Typical examples |
|---|---|---|
| P0 | Decision correctness or evidence integrity is at risk now, or the baseline cannot be trusted. Do before any new capability. | Regression in follow-ups, unstable Gate 5 outcome, full-suite gate |
| P1 | Materially affects trust, explainability or the core journey; do soon after P0. | Evidence boundary, cross-surface consistency, persistence provenance |
| P2 | Valuable improvement with contained risk; schedule after P1. | Concentration alert, CI, pinned dependencies |
| P3 | Opportunity or housekeeping; no near-term risk if deferred. | Alerts, extra data providers, session persistence |

Priorities weigh user impact, decision correctness, evidence integrity, risk, dependencies and effort. No dates or effort estimates are given because there is no evidence to support them.

## 2. Summary counts (roadmap features, not test cases)

**Total features inventoried: 84** in 17 functional areas.

| Implementation status | Features |
|---|---|
| Implemented | 51 |
| Partially implemented | 5 |
| Not implemented | 22 |
| Requires investigation | 6 |
| Retired/superseded | 0 |
| **Total** | 84 |

| Validation status | Features |
|---|---|
| Validated | 29 |
| Partially validated | 16 |
| Not validated | 36 |
| Blocked | 1 |
| Failed | 2 |
| **Total** | 84 |

**Implementation x validation matrix** (rows = implementation, columns = validation):

| Implementation \ Validation | Validated | Partially validated | Not validated | Blocked | Failed | Total |
|---|---|---|---|---|---|---|
| Implemented | 29 | 15 | 4 | 1 | 2 | 51 |
| Partially implemented | 0 | 1 | 4 | 0 | 0 | 5 |
| Not implemented | 0 | 0 | 22 | 0 | 0 | 22 |
| Requires investigation | 0 | 0 | 6 | 0 | 0 | 6 |
| Retired/superseded | 0 | 0 | 0 | 0 | 0 | 0 |

| Roadmap section | Features |
|---|---|
| Completed and validated | 29 |
| Implemented but awaiting validation | 21 |
| In progress (work in the uncommitted tree or failing validation) | 3 |
| Planned: foundational correctness and reliability | 6 |
| Planned: product capability and user experience | 4 |
| Planned: auditability and governance | 4 |
| Planned: operational readiness | 5 |
| Backlog / future opportunities | 11 |
| Blocked or awaiting a product decision | 1 |
| **Total** | 84 |

| Priority | Features |
|---|---|
| P0 | 14 |
| P1 | 33 |
| P2 | 23 |
| P3 | 14 |
| **Total** | 84 |

**Test-suite evidence (separate from the feature counts above):** 1,309 tests collected. Working tree: 1,247 passed, 61 failed, 1 skipped, 3 collection errors. Committed HEAD: 1,223 passed, 5 failed, 1 skipped, 3 collection errors. The 56 additional failures exist only in the uncommitted tree (see FND-1). **Update 2026-11-06:** after the FND-1 fix, working tree: 1,326 passed, 5 failed, 1 skipped, 3 collection errors (the 5 and 3 are identical to HEAD: F14.2, F14.3); includes 23 new routing regression tests; not committed.

## 3. Key findings (verify-and-record, not fixes)

Previously reported issues were treated as items to verify. Status of each is stated below. Detailed register in section 4.

| Topic requested | What was verified | Result |
|---|---|---|
| Gate 5 work | Severity thresholds unchanged and documented; UNKNOWN counted as MEDIUM-equivalent; 68 Phase 11B tests pass | Logic matches the reports. Outcome is unstable between runs (FND-3) |
| Severity breakers vs monitoring indicators | `is_monitoring_only` set at creation, persisted, honoured by trace and renderer; tests pass | Implemented; only verified on unit tests and stored JSON, not a fresh live run |
| Unavailable financial metrics | Searched for a single contract across engine, gates, renderer, trace, JSON | No single contract found; recorded as F4.4 'Requires investigation' |
| Narrative evidence boundaries | Read the fix and the report; checked where `unsupported_evidence` goes | Two narrow patterns; the audit field is not persisted anywhere in the code inspected (FND-5) |
| Conversational formatting | Read `_md_safe`; searched for `$` handling | Only `<` and `>` are escaped; dollar-sign handling is absent (hypothesis, FND-4) |
| Full-suite health | Ran the entire suite on tree and on HEAD | 56 regressions caused by an over-broad substring match (FND-1) |

## 4. Findings register

| ID | Priority | Finding and evidence | Features affected | Recommended action |
|---|---|---|---|---|
| FND-1 | P0 | Over-broad substring match in the 'why ... low/medium/high/unknown' intercept (`renderer.py:287`, `_LIKELIHOOD_TOKENS` at line 46) captures ordinary words such as 'lower'. FCF-vs-EPS reconciliation questions are answered with 'No thesis breakers are recorded ...'. Passes at HEAD; 56 tests fail in the working tree. | F8.5, F10.3, F5.4 | Fix with word-boundary matching and add negative tests. Needs owner approval to change feature code. **RESOLVED 2026-11-06 (validated, not committed):** whole-word matching plus breaker-context test and whole-word fuzzy matcher in `renderer.py`; 23 regression tests in `tests/test_phase11b_routing_regression.py`; the 56 regressed tests pass. |
| FND-2 | P0 | Completion reports cite only their own test files (58, then 68 tests) while the full suite regressed; docs still say 1,228 passing. No CI or pre-commit gate exists. | F14.1, F15.2, F16.3 | Adopt full-suite gate in the protocol (done in the protocol document) and add a one-command runner. **Outstanding 2026-11-06:** correction of the historical Phase 11B reports (carried over from F10.3) is not yet done. |
| FND-3 | P0 | The LLM regenerates thesis breakers each run. Persisted CNQ.TO outputs: Sep 30 HOLD (Gate 5 HIGH), Oct 1 and Oct 2 REDUCE (Gate 5 SEVERE) with entirely different breaker lists. With UNKNOWN counted as MEDIUM, four UNKNOWN items plus one MEDIUM reach SEVERE. Reports state CNQ remains HOLD, true only for the Sep 30 file. | F8.1, F8.2, F3.1, F12.4 | Measure repeatability and decide PD-1. No threshold change. |
| FND-4 | P1 | Streamlit may treat text between two `$` as LaTeX. The observed symptom `<40/bblornaturalgassustained<2 USD/MMBtu` has run-together words consistent with that. `_md_safe` escapes only `<` and `>`; no `$` escaping exists; the UI makes 41 markdown/text render calls. | F9.4, F13.3 | Reproduce, then fix centrally. Hypothesis, not confirmed here. |
| FND-5 | P1 | Evidence boundary is pattern-based (5-year CAGR, carbon price). The fallback signal is the label text '[5yr baseline unavailable]' produced in `calculations.py` and parsed in `research_orchestrator.py` (string coupling). `unsupported_evidence` is set in `research_orchestrator.py:551` and referenced nowhere else; it is absent from the persisted JSON. | F3.4, F4.2, F12.1 | Persist the field; decide PD-3; consider a structured flag. |
| FND-6 | P1 | Documentation contradicts code on Gate 5. Older docs (`data-flow.md:90`, `test-status.md:74`, `decision-log.md:106`, `investment-decision-flow.md:64`, `README.md:61`) say SEVERE forces 'REDUCE or EXIT'. Code (`decision_synthesizer.py:450+`) gives REDUCE or HOLD for existing positions; EXIT only when quality is CONCERN, the position exists and risk is SEVERE. The uncommitted edit to `docs/logic/decision-gates.md` already states the code behaviour. | F7.5, F15.1 | Reconcile docs after M0; confirm intent with PD-5. |
| FND-7 | P1 | No offline evidence for ITC.NS classification and live-data paths: 5 network tests fail without internet (also at HEAD); no recorded fixtures; live checks were impossible in this review (proxy 403). | F14.2, F2.3, F14.5 | Record fixtures; owner-run live acceptance. |
| FND-8 | P3 | Three test files define a helper named `test()` that pytest collects as a test (3 collection errors). | F14.3 | Rename helper. |
| FND-9 | P2 | `.env.example` omits `ANTHROPIC_API_KEY` and lists three keys no code uses. | F1.3, F2.6 | Align with code. |
| FND-10 | P1 | Persistence gaps: same-day reruns overwrite; no schema version, model/prompt/code/data provenance, trace, or scenario results; write failures are logged and swallowed; outputs are git-ignored. | F12.1, F12.4 | Design persistence v2. |
| FND-11 | P0 | All Phase 11A/11B work (14 modified, 6 untracked files) is uncommitted; `main` is one commit ahead of origin. Risk of loss or confusion about what is accepted. | F15.2, F9.1, F11.1 | Owner to authorise a commit strategy after M0 (PD-7). No commit made in this review. |
| FND-12 | P2 | Maintenance cost: `renderer.py` (1,846 lines) and `decision_synthesizer.py` (1,552 lines) mix text building with rules; `ui/app.py:443-455` contains an overwritten duplicate override computation; two legacy run scripts (909 and 1,812 lines) and four diagnostic scripts sit in the repo root. | F13.1, F15.5, F11.2 | Track as debt; clean after M1. |
| FND-13 | P2 | About 25 other `x in q` substring checks remain in `renderer.py` `render_followup` (18 inside `any(...)`), e.g. 'break' matches 'breakdown', 'risk' matches 'brisk'. Same defect class as FND-1; not changed. | F8.5, F10.3, F10.2 | Separate backlog item for Product Owner review: shared whole-word helper plus negative tests. |

## 5. Proposed milestones (sequence is a proposal for owner review)

| Milestone | Intent | Features |
|---|---|---|
| M0 | Stabilise the baseline: fix the regression, restore a green full suite, commit state with owner approval | F8.5, F10.3, F14.1, F15.3 |
| M1 | Evidence integrity and cross-surface consistency | F2.3, F2.4, F3.4, F4.3, F4.4, F5.5, F8.1, F8.3, F9.4, F9.5, F14.2, F14.3, F14.5 |
| M2 | Persistence, provenance and governance | F3.1, F9.3, F12.1, F12.2, F12.4, F15.1, F15.2, F15.4, F17.3 |
| M3 | UI quality and automated UI tests | F9.2, F11.2, F13.1, F13.2, F13.3 |
| M4 | Operational readiness | F1.3, F2.5, F6.6, F8.4, F12.3, F15.5, F16.1, F16.2, F16.3, F16.4, F16.5 |
| M5 | Product capability extensions | F5.7, F6.5, F10.5, F17.4 |
| M6 | Backlog (not scheduled) | F2.6, F2.7, F2.8, F3.5, F4.5, F5.6, F6.4, F11.3, F16.6, F17.1, F17.2 |

*Why this order:* a trustworthy baseline (M0) is needed before further correctness work; evidence integrity and consistency (M1) protect decision quality, which the product exists to deliver; persistence and provenance (M2) make instability measurable; UI and operations follow; capability extensions and the backlog come last.

## 6. Roadmap by section

### 6.1 Completed and validated (29)

| ID | Feature | Priority | Implementation | Validation | Milestone |
|---|---|---|---|---|---|
| F1.1 | Investment philosophy and threshold configuration | P2 | Implemented | Validated | M6 |
| F1.2 | MVP ticker universe (33 tickers) and custom ticker fallback | P2 | Implemented | Validated | M6 |
| F2.1 | Yahoo Finance fetch with local JSON cache and TTLs | P1 | Implemented | Validated | M6 |
| F2.2 | Fail-fast 429 handling and cache-poisoning protection | P1 | Implemented | Validated | M6 |
| F3.2 | Quantitative fallback without API key (Gate 1 fails safe) | P1 | Implemented | Validated | M6 |
| F3.3 | Business research models, moat analyzer and synthesizer | P2 | Implemented | Validated | M6 |
| F4.1 | Financial quality engine and thresholds (7 dimensions) | P1 | Implemented | Validated | M6 |
| F4.2 | Honest CAGR labelling (3-year fallback labelled, 5-year only when real) | P1 | Implemented | Validated | M6 |
| F5.1 | DCF engine (bear/base/bull, excluded for financial institutions) | P1 | Implemented | Validated | M6 |
| F5.2 | Multiples engines (P/E, P/FCF, EV/EBITDA) | P1 | Implemented | Validated | M6 |
| F5.3 | Method selector, weighted synthesis and margin-of-safety zones | P1 | Implemented | Validated | M6 |
| F5.4 | Valuation input builder with EPS/FCF same-period alignment | P0 | Implemented | Validated | M6 |
| F6.1 | Weight-only portfolio context and privacy rule | P1 | Implemented | Validated | M6 |
| F6.2 | Concentration analysis and incremental scenarios | P2 | Implemented | Validated | M6 |
| F6.3 | Sunk-cost protection (average cost excluded from decision) | P1 | Implemented | Validated | M6 |
| F7.1 | Gate 1: business understanding | P0 | Implemented | Validated | M6 |
| F7.2 | Gate 2: financial quality | P0 | Implemented | Validated | M6 |
| F7.3 | Gate 3: valuation attractiveness | P0 | Implemented | Validated | M6 |
| F7.4 | Gate 4: portfolio fit | P1 | Implemented | Validated | M6 |
| F7.5 | Decision synthesis, 8 actions and confidence | P0 | Implemented | Validated | M6 |
| F8.2 | UNKNOWN likelihood semantics (preserved, conservative for severity) | P0 | Implemented | Validated | M6 |
| F9.1 | Decision Trace builder and renderer | P0 | Implemented | Validated | M6 |
| F10.1 | ConversationManager, session state and error handling | P1 | Implemented | Validated | M6 |
| F10.2 | Intent classification (6 intents, regex patterns) | P1 | Implemented | Validated | M6 |
| F10.4 | Metric explanations and evidence requests in chat | P2 | Implemented | Validated | M6 |
| F11.1 | Scenario engine: breaker likelihood overrides recalculate Gate 5 and action | P1 | Implemented | Validated | M6 |
| F14.4 | Never-raise pipeline and friendly error messages | P1 | Implemented | Validated | M6 |
| F8.5 | Gate 5 explanation and breaker-specific Q&A | P0 | Implemented | Validated | M0 |
| F10.3 | Follow-up answers from stored assessment (FCF vs EPS, valuation, risks, data quality) | P0 | Implemented | Validated | M0 |

_Completed items remain listed permanently. Items marked uncommitted exist only in the working tree. Detail: section 7._

#### F8.5: Gate 5 explanation and breaker-specific Q&A

| Field | Content |
|---|---|
| User problem / opportunity | User can ask why Gate 5 is SEVERE or why a breaker is MEDIUM. |
| Expected outcome | Met. Validated 2026-11-06 (FND-1 resolved). |
| Scope and acceptance criteria | Word-boundary matching; questions containing 'lower', 'below', 'follow', 'allow' no longer route to the breaker answer; the 68 Phase 11B tests and all 56 regressed tests pass. |
| Dependencies | F10.3 |
| Priority / milestone | P0 / M0 |
| Implementation / validation | Implemented / Validated |
| Evidence for status | RESOLVED 2026-11-06 (FND-1): whole-word matching plus breaker-context test in renderer.py; tests/test_phase11b_routing_regression.py added (23 tests); 56 regressed tests pass; full suite 1,326 passed / 5 failed (F14.2) / 3 errors (F14.3), no failure that is not also at HEAD. Original finding: renderer._answer_gate5_explanation, _answer_breaker_specific, _answer_breaker_likelihood_question; their own tests pass (test_phase11b). The likelihood intercept at renderer.py:287 matches 'low', 'medium', 'high' or 'unknown' as substrings of the question, so any question with 'why' and a word like 'lower' is captured (FND-1). |
| Known limitations | Headless live-app smoke test passed 2026-11-06 (real run_ui.py session, cached CNQ.TO analysis, 3 fixture breakers injected because no LLM key was available): ordinary, genuine, paraphrased, Gate 5 and UNKNOWN questions routed as the 23 regression tests expect, with no Streamlit exceptions. No browser visual check was performed. Paraphrased breaker questions that share no words with a stored breaker and use no breaker vocabulary fall through to generic handlers (by design, option B). Dollar-sign rendering in breaker answers is a separate open item under F9.4. About 25 other substring checks remain in renderer.py (FND-13). |
| Definition of done | Full suite green except the 5 known network tests. Plus the checkpoint in the maintenance protocol. |
| Key risks | Over-correcting could break the intended breaker questions. |
| Open product decision | None. |

#### F10.3: Follow-up answers from stored assessment (FCF vs EPS, valuation, risks, data quality)

| Field | Content |
|---|---|
| User problem / opportunity | Answers questions without new data calls. |
| Expected outcome | Met. Validated 2026-11-06 (FND-1 resolved). |
| Scope and acceptance criteria | All 56 regressed tests pass; the full suite shows only the 5 known network-test failures and 3 collection errors. |
| Dependencies | F8.5 |
| Priority / milestone | P0 / M0 |
| Implementation / validation | Implemented / Validated |
| Evidence for status | RESOLVED 2026-11-06 (FND-1): whole-word matching plus breaker-context test in renderer.py; tests/test_phase11b_routing_regression.py added (23 tests); 56 regressed tests pass; full suite 1,326 passed / 5 failed (F14.2) / 3 errors (F14.3), no failure that is not also at HEAD. Original finding: At committed HEAD 5 tests fail (known network tests). In the working tree 61 fail: test_phase96 (22), test_phase95 (14), test_phase97 (8), test_phase99 (5), test_phase94d (5), test_phase98 (2), plus the 5 network tests. Example output for 'Why is FCF/share lower than EPS specifically? Please reconcile by capex' is 'No thesis breakers are recorded for ITC Ltd ...'. |
| Known limitations | Headless live-app smoke test passed 2026-11-06 (real run_ui.py session, cached CNQ.TO analysis, 3 fixture breakers injected because no LLM key was available): ordinary, genuine, paraphrased, Gate 5 and UNKNOWN questions routed as the 23 regression tests expect, with no Streamlit exceptions. No browser visual check was performed. **Outstanding, tracked under FND-2:** the historical Phase 11B reports (docs/phase11b_corrective_final_report.md and docs/phase11b_evidence_boundary_final_report.md) cite only the 58/68 tests of their own file, not the full suite; they have not yet been corrected. |
| Definition of done | Suite output attached to roadmap; reports corrected (the report correction is outstanding and tracked under FND-2; acceptance criteria are met). Plus the checkpoint in the maintenance protocol. |
| Key risks | None beyond FND-1. |
| Open product decision | None. |

### 6.2 Implemented but awaiting validation (21)

| ID | Feature | Priority | Implementation | Validation | Milestone |
|---|---|---|---|---|---|
| F1.3 | Secrets and environment configuration | P1 | Partially implemented | Not validated | M4 |
| F2.3 | Normalization to CompanyFinancialMetrics (incl. continuing-ops NI) | P1 | Implemented | Partially validated | M1 |
| F2.4 | Data freshness assessment and WATCH_PENDING_DATA path | P2 | Implemented | Partially validated | M1 |
| F2.5 | Pre-warm script and cache status panel | P2 | Implemented | Blocked | M4 |
| F3.1 | Claude API business research (moat, management, industry, risks, bull/bear) | P1 | Implemented | Partially validated | M2 |
| F4.3 | ROIC computation and dividend-yield correction (Phase 11A) | P1 | Implemented | Partially validated | M1 |
| F5.5 | Valuation assumptions disclosure and assumption-break monitoring | P2 | Implemented | Partially validated | M1 |
| F6.6 | Portfolio snapshot updater and refresh script | P3 | Requires investigation | Not validated | M4 |
| F8.1 | Gate 5 severity model (n_high, n_medium_equiv, n_bear thresholds) | P0 | Implemented | Partially validated | M1 |
| F8.4 | Thesis-breaker generation with structured details and plain-string fallback | P1 | Implemented | Partially validated | M4 |
| F9.2 | Trace surfaced in the Streamlit UI (Why this decision?) | P1 | Implemented | Not validated | M3 |
| F9.3 | Evidence tiers and provenance in outputs | P1 | Implemented | Partially validated | M2 |
| F10.5 | Natural-language what-if (price, EPS, growth) in chat | P2 | Partially implemented | Not validated | M5 |
| F11.2 | What-if panel in the Streamlit UI | P1 | Implemented | Not validated | M3 |
| F12.1 | Decision JSON persistence | P1 | Implemented | Partially validated | M2 |
| F13.1 | Streamlit UI: ticker dropdown, weight input, Analyse, Force Refresh, data status | P1 | Implemented | Not validated | M3 |
| F14.1 | Automated test suite | P0 | Implemented | Partially validated | M0 |
| F15.1 | Phase 10.6 documentation pack (31 docs) | P1 | Implemented | Partially validated | M2 |
| F15.2 | Phase 11A/11B reports | P1 | Implemented | Partially validated | M2 |
| F15.3 | Living roadmap, architecture diagrams and maintenance protocol | P0 | Implemented | Not validated | M0 |
| F16.1 | Local run paths (streamlit via run_ui.py, CLI via run_agent.py) | P2 | Implemented | Partially validated | M4 |

#### F1.3: Secrets and environment configuration

| Field | Content |
|---|---|
| User problem / opportunity | API keys are kept out of source control and the app fails safe without them. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Align .env.example with real configuration (FND-9). |
| Scope and acceptance criteria | Given a clean checkout, a new user can identify every required and optional key from .env.example and the README; the app starts and reports research mode correctly with and without the key. |
| Dependencies | None |
| Priority / milestone | P1 / M4 |
| Implementation / validation | Partially implemented / Not validated |
| Evidence for status | .env is git-ignored (.gitignore line 13) and no .env exists in the folder; ANTHROPIC_API_KEY is read from the environment (pipeline.py:165, anthropic_researcher.py:381). .env.example lists only FMP, Alpha Vantage and Polygon keys, none of which are referenced by any Python file (grep). |
| Known limitations | .env.example does not mention ANTHROPIC_API_KEY, the one key the product needs, and lists three unused keys. run_ui.py loads .env through python-dotenv only if that package is installed (run_ui.py:37-40); the CLI path was not checked. |
| Definition of done | Config documented in one place; .env.example matches code; verified by a clean-environment start. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low risk. |
| Open product decision | None. |

#### F2.3: Normalization to CompanyFinancialMetrics (incl. continuing-ops NI)

| Field | Content |
|---|---|
| User problem / opportunity | Typed, auditable financial inputs for every downstream stage. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Recorded-response fixtures (FND-7, F14.2). |
| Scope and acceptance criteria | Recorded yfinance payloads for at least ITC.NS, CNQ.TO and TD.TO normalize to asserted values; a missing expected field raises a visible data-quality warning. |
| Dependencies | F2.1 |
| Priority / milestone | P1 / M1 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | normalizer.py (626 lines, modified in working tree); test_ingestion 14, test_phase99 core alignment tests and test_phase11a (12) pass. test_phase93b (5) fail, but they call the live network and fail identically at committed HEAD. |
| Known limitations | Hard-coded yfinance field names; a rename silently yields None (technical debt D8). The 5 network-dependent tests give no offline evidence for the ITC.NS classification checks. |
| Definition of done | Fixtures committed; the 5 network tests replaced or marked as live-only; roadmap and test-status updated. Plus the checkpoint in the maintenance protocol. |
| Key risks | Fixtures can go stale as Yahoo changes. |
| Open product decision | None. |

#### F2.4: Data freshness assessment and WATCH_PENDING_DATA path

| Field | Content |
|---|---|
| User problem / opportunity | Stale or unknown prices never produce a confident action. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Targeted review of freshness assertions. |
| Scope and acceptance criteria | Stale price, unknown price and fresh price each map to the documented action behaviour in a dedicated, named test. |
| Dependencies | F2.3 |
| Priority / milestone | P2 / M1 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | analytics/data_freshness.py (328 lines); referenced in tests/test_decision.py, test_agent.py, test_phase9.py, test_phase99.py, test_phase10_*.py, test_phase11a.py. |
| Known limitations | Not individually traced in this review; coverage was inferred from file references, not from assertions read one by one. |
| Definition of done | Named tests exist and pass; limitation recorded. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F2.5: Pre-warm script and cache status panel

| Field | Content |
|---|---|
| User problem / opportunity | The demo/daily workflow starts with warm data. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Run on the user's machine to re-baseline cache state. |
| Scope and acceptance criteria | On the owner's machine the pre-warm script completes for the 33 tickers and the status panel reports the result. |
| Dependencies | F2.1; network |
| Priority / milestone | P2 / M4 |
| Implementation / validation | Implemented / Blocked |
| Evidence for status | scripts/prewarm_mvp.py (253 lines), ui/data_status.py (247 lines); status-reading tests in test_phase105. |
| Known limitations | The pre-warm script is network-dependent and was not run. Cache-status counts in docs (32 of 33 ready, Aug 2026) are stale. Cache expires in 24-48h. |
| Definition of done | Run log recorded in roadmap evidence. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F3.1: Claude API business research (moat, management, industry, risks, bull/bear)

| Field | Content |
|---|---|
| User problem / opportunity | Qualitative understanding required by Gate 1 and Gate 5. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Live acceptance on one ticker by the owner; add model/prompt provenance (F12.4). |
| Scope and acceptance criteria | A live run on at least two tickers completes, produces structured research, and records model id, prompt version and timestamp in the persisted artifact. |
| Dependencies | ANTHROPIC_API_KEY |
| Priority / milestone | P1 / M2 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | anthropic_researcher.py (553 lines, modified), research_orchestrator.py (567 lines, modified), business_research package; test_business_research (73) passes using mocks. |
| Known limitations | No live API call was made in this review (no key, network blocked). Default model is claude-haiku-4-5-20251001 (anthropic_researcher.py:72). LLM output varies run to run (FND-3). Prompts are not versioned in persisted output. |
| Definition of done | Live run evidence attached to roadmap; provenance fields persisted and tested. Plus the checkpoint in the maintenance protocol. |
| Key risks | Cost and nondeterminism. |
| Open product decision | None. |

#### F4.3: ROIC computation and dividend-yield correction (Phase 11A)

| Field | Content |
|---|---|
| User problem / opportunity | Accurate quality and income metrics. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Owner to confirm ROIC/yield on 2-3 known tickers after live data is available. |
| Scope and acceptance criteria | ROIC and dividend yield for ITC.NS, CNQ.TO and TD.TO match independently sourced values within an agreed tolerance. |
| Dependencies | F2.3 |
| Priority / milestone | P1 / M1 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | calculations.py and financial_metrics_model.py (modified); test_phase11a tests 4-9 pass (synthetic inputs). Uncommitted. |
| Known limitations | No real-ticker baseline comparison was run here, so correctness on live data is unconfirmed. |
| Definition of done | Comparison recorded in roadmap evidence; fixtures added. Plus the checkpoint in the maintenance protocol. |
| Key risks | Source disagreement between Yahoo and filings. |
| Open product decision | None. |

#### F5.5: Valuation assumptions disclosure and assumption-break monitoring

| Field | Content |
|---|---|
| User problem / opportunity | User can see which assumptions drive value. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Include in cross-surface consistency tests (F9.5). |
| Scope and acceptance criteria | Assumptions shown identically in report, chat and JSON; test asserts equality. |
| Dependencies | F5.3 |
| Priority / milestone | P2 / M1 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | key_assumptions is persisted in decision JSON; a valuation-assumption monitoring indicator is added in gate5_adversarial.extract_thesis_breakers (display only). |
| Known limitations | The monitoring indicator text embeds the discount-rate derivation; its value to the user is unvalidated. |
| Definition of done | Tests merged. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F6.6: Portfolio snapshot updater and refresh script

| Field | Content |
|---|---|
| User problem / opportunity | Keeps weights current. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Owner to confirm whether this is still used. |
| Scope and acceptance criteria | Owner confirms whether the updater is in use; if yes, a named test covers it; if not, it is archived. |
| Dependencies | Local CSV |
| Priority / milestone | P3 / M4 |
| Implementation / validation | Requires investigation / Not validated |
| Evidence for status | data/ingestion/portfolio_updater.py (329 lines) and scripts/refresh_portfolio.py exist; not exercised, no matching named tests were identified. |
| Known limitations | Purpose and current use unclear; depends on git-ignored local CSV. |
| Definition of done | Decision recorded. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F8.1: Gate 5 severity model (n_high, n_medium_equiv, n_bear thresholds)

| Field | Content |
|---|---|
| User problem / opportunity | A credible severe risk overrides optimistic gates. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Investigate stability and evidence behind UNKNOWN-driven SEVERE; owner decision PD-1. No threshold change without approval. |
| Scope and acceptance criteria | (1) A written explanation, from persisted evidence, of why CNQ.TO moved from HOLD to REDUCE. (2) A repeatability measurement: the same ticker and data analysed N times, with the distribution of Gate 5 severity and action reported. (3) Owner decision recorded on PD-1. |
| Dependencies | F3.1; F8.2 |
| Priority / milestone | P0 / M1 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | gate5_adversarial.py (354 lines, modified); thresholds verbatim in docs/logic/decision-gates.md; test_phase11b groups 1-3 pass (68 total). |
| Known limitations | Output is unstable across runs because the LLM regenerates breakers: persisted CNQ.TO runs show Sep 30 HOLD (Gate 5 HIGH; 1 MEDIUM + 2 UNKNOWN = 3 medium-equivalent), Oct 1 REDUCE (SEVERE; 2 MEDIUM + 2 UNKNOWN = 4, meeting the >=4 SEVERE rule) and Oct 2 REDUCE (SEVERE; 1 MEDIUM + 4 UNKNOWN = 5). Each run lists different breaker conditions (FND-3). The reports claiming CNQ stays HOLD rest on the Sep 30 file. |
| Definition of done | Analysis committed to docs; decision logged; thresholds unchanged unless approved. Plus the checkpoint in the maintenance protocol. |
| Key risks | Repeatability runs cost API calls and need owner approval. |
| Open product decision | PD-1: keep UNKNOWN as MEDIUM-equivalent, cap UNKNOWN's contribution, or require evidence before UNKNOWN counts. |

#### F8.4: Thesis-breaker generation with structured details and plain-string fallback

| Field | Content |
|---|---|
| User problem / opportunity | Specific, monitorable conditions with likelihood and evidence. |
| Expected outcome | Item meets the acceptance criteria below. Next action: See F8.1. |
| Scope and acceptance criteria | Structured-detail and plain-string paths both covered by tests; live run shows breakers with likelihood and evidence. |
| Dependencies | F3.1 |
| Priority / milestone | P1 / M4 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | research_orchestrator parses thesis_breaker_details; fallback path covered by test_phase11b group 3. |
| Known limitations | Content quality depends on the LLM; breaker sets vary between runs. |
| Definition of done | Tests pass and live run recorded. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F9.2: Trace surfaced in the Streamlit UI (Why this decision?)

| Field | Content |
|---|---|
| User problem / opportunity | Explainability where the user looks. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Cover in UI smoke test. |
| Scope and acceptance criteria | A UI test analyses a cached ticker and finds the trace section with the final action. |
| Dependencies | F13.3 |
| Priority / milestone | P1 / M3 |
| Implementation / validation | Implemented / Not validated |
| Evidence for status | ui/app.py:388-395 renders the trace with st.code. |
| Known limitations | No automated UI tests exist. |
| Definition of done | Test passes in the suite. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F9.3: Evidence tiers and provenance in outputs

| Field | Content |
|---|---|
| User problem / opportunity | Distinguish filings, databases and model-derived claims. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Fold into F9.5 and F12.4. |
| Scope and acceptance criteria | Every evidence line in the report carries a tier label or is explicitly marked unsupported. |
| Dependencies | F3.4 |
| Priority / milestone | P1 / M2 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | Tiering described in docs and models; evidence_sources, supporting_evidence and contradictory_evidence persisted. |
| Known limitations | No end-to-end check that each displayed claim maps to a source; LLM figures can lack provenance (see F3.4). |
| Definition of done | Tests plus docs. Plus the checkpoint in the maintenance protocol. |
| Key risks | Medium. |
| Open product decision | None. |

#### F10.5: Natural-language what-if (price, EPS, growth) in chat

| Field | Content |
|---|---|
| User problem / opportunity | Ask hypothetical valuation questions. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Decision PD-4 on scope. |
| Scope and acceptance criteria | Defined by PD-4 once the owner chooses scope. |
| Dependencies | F11.1 |
| Priority / milestone | P2 / M5 |
| Implementation / validation | Partially implemented / Not validated |
| Evidence for status | Intent SCENARIO_WHAT_IF exists; manager._handle_scenario forwards to existing renderer answers ('at what price', 'what would change'). No engine recalculates valuation for 'what if EPS grows 10%'. |
| Known limitations | Name overlap with the Phase 11B likelihood scenario engine (F11.1) is confusing. |
| Definition of done | Defined by PD-4. Plus the checkpoint in the maintenance protocol. |
| Key risks | Scope creep. |
| Open product decision | PD-4: keep chat what-if informational, extend scenario engine to valuation inputs, or retire the intent. |

#### F11.2: What-if panel in the Streamlit UI

| Field | Content |
|---|---|
| User problem / opportunity | Interactive scenario testing. |
| Expected outcome | Item meets the acceptance criteria below. Next action: UI smoke test, then tidy. |
| Scope and acceptance criteria | UI test applies an override and sees baseline vs scenario action; unchanged selections disable Apply. |
| Dependencies | F11.1; F13.3 |
| Priority / milestone | P1 / M3 |
| Implementation / validation | Implemented / Not validated |
| Evidence for status | ui/app.py:399-471 builds BreakerOverride objects and calls run_scenario. A leftover duplicate override computation (lines 443-455) is overwritten by a simplified loop. |
| Known limitations | No UI tests; dead code present. |
| Definition of done | Test passes; dead code removed. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F12.1: Decision JSON persistence

| Field | Content |
|---|---|
| User problem / opportunity | Audit trail and regression artifacts. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Design persistence v2 (R/F12.4). |
| Scope and acceptance criteria | Persisted artifact contains schema version, run id, model id, prompt version, data timestamps, trace, unsupported evidence; repeat runs never overwrite silently; round-trip test. |
| Dependencies | F7.5 |
| Priority / milestone | P1 / M2 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | pipeline._persist_decision writes data/output/{TICKER}_{DATE}_decision.json; five files exist (CNQ x3, TD x2); to_dict covers action, gates, breakers with is_monitoring_only and evidence. |
| Known limitations | A second run for the same ticker and date overwrites the first. No schema version, no model/prompt/data-snapshot identifiers, no decision trace, no unsupported_evidence, no scenario results. data/output/*.json is git-ignored. Failures are logged and swallowed. |
| Definition of done | Schema doc and tests merged; old files remain readable. Plus the checkpoint in the maintenance protocol. |
| Key risks | Format migration. |
| Open product decision | None. |

#### F13.1: Streamlit UI: ticker dropdown, weight input, Analyse, Force Refresh, data status

| Field | Content |
|---|---|
| User problem / opportunity | Usable without developer help. |
| Expected outcome | Item meets the acceptance criteria below. Next action: UI smoke test (F13.3); owner walkthrough. |
| Scope and acceptance criteria | A scripted run loads the app, selects a cached ticker and renders analysis, trace and chat. |
| Dependencies | F2.5 |
| Priority / milestone | P1 / M3 |
| Implementation / validation | Implemented / Not validated |
| Evidence for status | ui/app.py (631 lines), ui/data_status.py (247), run_ui.py; Phase 10.5 reported acceptance; behaviour backed by manager-level tests only. |
| Known limitations | No automated UI test. This review did not launch the app (no network/API key; built-in browser not used). |
| Definition of done | Smoke test in suite. Plus the checkpoint in the maintenance protocol. |
| Key risks | Streamlit testing API limits. |
| Open product decision | None. |

#### F14.1: Automated test suite

| Field | Content |
|---|---|
| User problem / opportunity | Regression safety. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Adopt the full-suite gate (FND-2). |
| Scope and acceptance criteria | Suite green apart from documented live-network tests; the count is generated, not hand-typed. |
| Dependencies | None |
| Priority / milestone | P0 / M0 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | 1,309 tests collected across 28 files. Run in a scratch copy (Python 3.10.12, deps installed in a venv outside the repo): working tree 1,247 passed, 61 failed, 1 skipped, 3 errors; committed HEAD 1,223 passed, 5 failed, 1 skipped, 3 errors. |
| Known limitations | docs/engineering/test-status.md still states 1,228 passed. Reports for Phase 11B cite only their own file. |
| Definition of done | Protocol step 3 followed. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F15.1: Phase 10.6 documentation pack (31 docs)

| Field | Content |
|---|---|
| User problem / opportunity | Product Owner can understand the product without reading code. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Reconcile after M0 (protocol step 7). |
| Scope and acceptance criteria | Each stale statement is updated or points to the authoritative roadmap; a consistency check lists no contradictions. |
| Dependencies | None |
| Priority / milestone | P1 / M2 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | docs/ has 31 Markdown files across product, architecture, logic, engineering, governance, po-learning. |
| Known limitations | Stale versus code: docs/README says Phase 10.6 current and 1,228 passing tests; roadmap.md says Phase 11 not started; current-state.md predates Phase 11; test-status.md predates Phase 11; Gate 5 behaviour differs between docs (see FND-6). |
| Definition of done | Docs updated and cross-checked. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F15.2: Phase 11A/11B reports

| Field | Content |
|---|---|
| User problem / opportunity | Record of what changed and why. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Add correction notes after M0. |
| Scope and acceptance criteria | Reports carry a dated correction pointing to the roadmap. |
| Dependencies | F10.3 |
| Priority / milestone | P1 / M2 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | docs/phase11b_corrective_final_report.md and phase11b_evidence_boundary_final_report.md (untracked). |
| Known limitations | State 58 and 68 passing tests and CNQ stays HOLD; full suite and the Oct 1/2 persisted REDUCE runs contradict the overall picture. |
| Definition of done | Edits made and verified. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F15.3: Living roadmap, architecture diagrams and maintenance protocol

| Field | Content |
|---|---|
| User problem / opportunity | One authoritative record, updated after every feature. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Owner review. |
| Scope and acceptance criteria | Owner confirms structure, priorities and protocol. |
| Dependencies | None |
| Priority / milestone | P0 / M0 |
| Implementation / validation | Implemented / Not validated |
| Evidence for status | Created by this review (three new Markdown documents). |
| Known limitations | Awaiting owner review; validation = owner acceptance of structure and priorities. |
| Definition of done | Owner sign-off recorded in the revision history. Plus the checkpoint in the maintenance protocol. |
| Key risks | None. |
| Open product decision | None. |

#### F16.1: Local run paths (streamlit via run_ui.py, CLI via run_agent.py)

| Field | Content |
|---|---|
| User problem / opportunity | Single-user local operation. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Owner confirms. |
| Scope and acceptance criteria | Owner starts the UI and the CLI from a clean checkout following the README. |
| Dependencies | None |
| Priority / milestone | P2 / M4 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | run_ui.py (48 lines), run_agent.py (494 lines). |
| Known limitations | Not run in this review. |
| Definition of done | Confirmation recorded. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

### 6.3 In progress (work in the uncommitted tree or failing validation) (3)

| ID | Feature | Priority | Implementation | Validation | Milestone |
|---|---|---|---|---|---|
| F3.4 | Narrative evidence boundary (5-year CAGR, carbon-price claims) and evidence segregation | P0 | Partially implemented | Partially validated | M1 |
| F8.3 | Severity-contributing breakers vs monitoring-only indicators | P0 | Implemented | Partially validated | M1 |
| F9.4 | Rendering safety for conditions containing < > and $ | P1 | Implemented | Partially validated | M1 |

#### F3.4: Narrative evidence boundary (5-year CAGR, carbon-price claims) and evidence segregation

| Field | Content |
|---|---|
| User problem / opportunity | Unsupported figures must not appear as trusted evidence. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Decide the boundary strategy (PD-3) and persist the audit field. |
| Scope and acceptance criteria | (1) Unsupported-evidence strings are persisted and visible in the audit trail. (2) The chosen boundary strategy is documented, with its known gaps. (3) A live CNQ.TO regeneration shows no 5-year CAGR or carbon-price figure in trusted evidence. |
| Dependencies | F3.1; F12.1 |
| Priority / milestone | P0 / M1 |
| Implementation / validation | Partially implemented / Partially validated |
| Evidence for status | research_orchestrator._build_context and _parse_bull_bear (modified, uncommitted); test_phase11b tests 53-64 pass; docs/phase11b_evidence_boundary_final_report.md. |
| Known limitations | Pattern-based: two specific patterns only (5-year CAGR phrasing and carbon-price $/tonne). Any other unsupported fact passes as trusted evidence. Segregated strings go to unsupported_evidence, but no module other than research_orchestrator.py references that field (grep), and it is absent from the persisted decision JSON, so the report's statement that these strings are kept for audit is not backed by persistence in the code inspected. Acceptance was run against stored JSON, not a live regeneration. |
| Definition of done | Persistence and live acceptance evidence recorded; no change to Gate 5 thresholds. Plus the checkpoint in the maintenance protocol. |
| Key risks | Pattern lists do not generalize; a structured-claims approach is larger work. |
| Open product decision | PD-3: pattern validators (current), allow-list of context-derived claims, or structured claim schema. See Decisions. |

#### F8.3: Severity-contributing breakers vs monitoring-only indicators

| Field | Content |
|---|---|
| User problem / opportunity | The user sees which risks drove the verdict and which are only watch items. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Run a live acceptance after F9.5 is built. |
| Scope and acceptance criteria | Report, chat answers, trace and JSON agree on which breakers are severity-contributing; a monitoring item never changes severity. |
| Dependencies | F8.1 |
| Priority / milestone | P0 / M1 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | is_monitoring_only is set in gate5_adversarial.extract_thesis_breakers and persisted in JSON; routed in decision_trace and renderer; test_phase11b tests 53, 54, 58, 66 pass. Monitoring items are not passed to evaluate_gate5 (per report; the persisted Oct 1/2 files show 1 monitoring item each). |
| Known limitations | Uncommitted. The persisted Sep 30 file (pre-11B) shows the same indicator as a normal breaker. Latest live acceptance of the split was done on stored JSON, not a fresh run. |
| Definition of done | Cross-surface tests (F9.5) pass. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F9.4: Rendering safety for conditions containing < > and $

| Field | Content |
|---|---|
| User problem / opportunity | Breaker text such as 'Brent <$40/bbl' must display faithfully. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Reproduce in the built-in browser or Streamlit AppTest, then fix once for all render paths (FND-4). |
| Scope and acceptance criteria | Breaker conditions containing $ and < render exactly as stored in the Streamlit UI; verified with an automated or browser test. |
| Dependencies | None |
| Priority / milestone | P1 / M1 |
| Implementation / validation | Implemented / Partially validated |
| Evidence for status | renderer._md_safe escapes < and > only (renderer.py); test 67-68 pass. The earlier live symptom ('<40/bblornaturalgassustained<2 USD/MMBtu') shows words run together, which is typical of Streamlit treating text between two dollar signs as LaTeX math. No dollar-sign escaping exists in renderer.py or ui/app.py (grep) and 41 markdown/text render calls exist in the UI. |
| Known limitations | Hypothesis, not yet reproduced here: the dollar-sign pairs, not the angle brackets, may be the main cause. The current fix may not resolve the visible symptom. **Observed 2026-11-06 (headless live-app smoke test):** a breaker-likelihood answer for 'Sustained crude oil prices below $60/bbl for 12+ months' contains two unescaped '$' in one message (breaker line and Note line), which Streamlit will likely render as math. Not confirmed visually (no browser check). Pre-existing, not caused by FND-1; open and not fixed. |
| Definition of done | Test added; fix applied centrally. Plus the checkpoint in the maintenance protocol. |
| Key risks | Escaping in the wrong layer could double-escape. |
| Open product decision | None. |

### 6.4 Planned: foundational correctness and reliability (6)

| ID | Feature | Priority | Implementation | Validation | Milestone |
|---|---|---|---|---|---|
| F4.4 | Handling of unavailable metrics (None vs UNKNOWN vs zero) end to end | P1 | Requires investigation | Not validated | M1 |
| F9.5 | Cross-surface consistency (report, chat, trace, JSON agree) | P1 | Requires investigation | Not validated | M1 |
| F13.3 | UI automated smoke tests | P1 | Not implemented | Not validated | M3 |
| F14.2 | Network-dependent tests (test_phase93b, 5) | P2 | Implemented | Failed | M1 |
| F14.3 | Collection errors in three script-style test files | P3 | Implemented | Failed | M1 |
| F14.5 | Live end-to-end acceptance harness | P1 | Not implemented | Not validated | M1 |

#### F4.4: Handling of unavailable metrics (None vs UNKNOWN vs zero) end to end

| Field | Content |
|---|---|
| User problem / opportunity | Missing data must never look like a measured value. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Audit and document one contract; add cross-surface tests (F9.5). |
| Scope and acceptance criteria | A table of every financial metric lists its unavailable representation in the quality engine, gate text, chat answers, trace and JSON; tests prove no path shows a missing metric as 0 or as measured. |
| Dependencies | F4.1; F7.2 |
| Priority / milestone | P1 / M1 |
| Implementation / validation | Requires investigation / Not validated |
| Evidence for status | Calculations return None for missing values; gates and renderer use varied wording (e.g. 'UNAVAILABLE' appears 7 times in calculations.py, once in renderer.py, never in quality_engine.py). No single contract was found. |
| Known limitations | Not verified that every path (quality engine, gates, renderer, trace, JSON) treats missing metrics identically. |
| Definition of done | Audit document merged; tests pass; roadmap evidence updated. Plus the checkpoint in the maintenance protocol. |
| Key risks | May expose behaviour changes needing owner approval. |
| Open product decision | None. |

#### F9.5: Cross-surface consistency (report, chat, trace, JSON agree)

| Field | Content |
|---|---|
| User problem / opportunity | The same facts everywhere. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Create a consistency test suite. |
| Scope and acceptance criteria | For fixtures covering HOLD, REDUCE, ACCUMULATE and WATCH, report, chat answers, trace and JSON expose identical action, confidence, Gate 5 severity and breaker lists. |
| Dependencies | F9.1; F12.1 |
| Priority / milestone | P1 / M1 |
| Implementation / validation | Requires investigation / Not validated |
| Evidence for status | Individual surfaces are tested; no test compares action, Gate 5 severity, breaker partitions and assumptions across all four. The FND-1 regression shows chat answers can drift from the report. |
| Known limitations | Unverified. |
| Definition of done | Tests in suite; roadmap updated. Plus the checkpoint in the maintenance protocol. |
| Key risks | May reveal further inconsistencies. |
| Open product decision | None. |

#### F13.3: UI automated smoke tests

| Field | Content |
|---|---|
| User problem / opportunity | Catch UI regressions. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Streamlit AppTest or Playwright. |
| Scope and acceptance criteria | Tests cover start-up, analysis of a cached fixture, trace expander, what-if panel and rendering of $ and < text. |
| Dependencies | F13.1 |
| Priority / milestone | P1 / M3 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog B14 / debt D5; none exist. |
| Known limitations | None. |
| Definition of done | Tests run offline in the suite. Plus the checkpoint in the maintenance protocol. |
| Key risks | Tooling choice. |
| Open product decision | None. |

#### F14.2: Network-dependent tests (test_phase93b, 5)

| Field | Content |
|---|---|
| User problem / opportunity | Deterministic tests. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Replace with recorded fixtures. |
| Scope and acceptance criteria | The 5 tests pass offline from fixtures. |
| Dependencies | F2.3 |
| Priority / milestone | P2 / M1 |
| Implementation / validation | Implemented / Failed |
| Evidence for status | Fail at HEAD and in working tree with HTTP 403 from the sandbox proxy; known debt D1. |
| Known limitations | No offline evidence for ITC.NS classification. |
| Definition of done | Fixtures committed. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F14.3: Collection errors in three script-style test files

| Field | Content |
|---|---|
| User problem / opportunity | Clean test output. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Rename helper. |
| Scope and acceptance criteria | Suite reports zero collection errors. |
| Dependencies | None |
| Priority / milestone | P3 / M1 |
| Implementation / validation | Implemented / Failed |
| Evidence for status | ERROR tests/test_calculations.py::test, test_ingestion.py::test, test_quality_engine.py::test: a helper named test() is collected. |
| Known limitations | Cosmetic; real tests in those files run. |
| Definition of done | Rename merged. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F14.5: Live end-to-end acceptance harness

| Field | Content |
|---|---|
| User problem / opportunity | Prove behaviour on real data. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Owner-run live acceptance script for 2 tickers after M0. |
| Scope and acceptance criteria | A documented command runs one cached ticker and one live ticker and checks action, trace, persisted JSON and chat in one pass. |
| Dependencies | Network, API key |
| Priority / milestone | P1 / M1 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Live acceptance so far was manual or run on stored JSON. This review had no network/API access to run any live check. |
| Known limitations | Sandbox limits validation. |
| Definition of done | Script and output recorded in roadmap. Plus the checkpoint in the maintenance protocol. |
| Key risks | API cost. |
| Open product decision | None. |

### 6.5 Planned: product capability and user experience (4)

| ID | Feature | Priority | Implementation | Validation | Milestone |
|---|---|---|---|---|---|
| F5.7 | Valuation method for financial institutions (P/BV, P/TBV, ROE-COE) | P2 | Not implemented | Not validated | M5 |
| F6.5 | Concentration alert in the UI | P2 | Not implemented | Not validated | M5 |
| F13.2 | Usability review of long reports and chat formatting | P2 | Requires investigation | Not validated | M3 |
| F17.4 | Ticker universe expansion and governance (B6, B7) | P2 | Not implemented | Not validated | M5 |

#### F5.7: Valuation method for financial institutions (P/BV, P/TBV, ROE-COE)

| Field | Content |
|---|---|
| User problem / opportunity | 8 of 33 MVP tickers are financials and have no DCF. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Owner to approve methods. |
| Scope and acceptance criteria | For TD.TO, BNS.TO and one insurer, the new method yields a documented range with asserted inputs and appears in the report and trace. |
| Dependencies | Product decision on methods |
| Priority / milestone | P2 / M5 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog B16; DCF excluded for banks/insurers (confirmed in docs; not re-read in code). |
| Known limitations | Financials rely on multiples only. |
| Definition of done | Tests, docs, roadmap updated; thresholds unchanged unless approved. Plus the checkpoint in the maintenance protocol. |
| Key risks | New valuation logic is a product-rule change that needs approval. |
| Open product decision | Which method(s) and weights for banks vs insurers. |

#### F6.5: Concentration alert in the UI

| Field | Content |
|---|---|
| User problem / opportunity | Prevents inadvertent over-concentration. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Small UI change after F13.3 smoke tests exist. |
| Scope and acceptance criteria | Entering a weight above the configured concentration threshold shows a warning that cites the threshold; below it shows none. |
| Dependencies | F6.2 |
| Priority / milestone | P2 / M5 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | No concentration reference in ui/app.py (grep). |
| Known limitations | Logic exists, display does not. |
| Definition of done | UI test passes; roadmap and docs updated. Plus the checkpoint in the maintenance protocol. |
| Key risks | Threshold ownership: use the existing configured value, do not invent one. |
| Open product decision | None. |

#### F13.2: Usability review of long reports and chat formatting

| Field | Content |
|---|---|
| User problem / opportunity | Readable output for a busy investor. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Short owner-led review once FND-1 and FND-4 are fixed. |
| Scope and acceptance criteria | Owner reviews 3 tickers and lists issues; agreed items are added to the roadmap. |
| Dependencies | F13.1 |
| Priority / milestone | P2 / M3 |
| Implementation / validation | Requires investigation / Not validated |
| Evidence for status | Report renderer.py is 1,846 lines; recent formatting issues (FND-4, and 6-vs-5 breaker count defect D4 fixed in 11B). |
| Known limitations | No structured usability review exists. |
| Definition of done | Findings logged. Plus the checkpoint in the maintenance protocol. |
| Key risks | Subjective; needs owner time. |
| Open product decision | None. |

#### F17.4: Ticker universe expansion and governance (B6, B7)

| Field | Content |
|---|---|
| User problem / opportunity | Cover more of the real portfolio. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Owner supplies tickers and rule. |
| Scope and acceptance criteria | Approved add/remove rule is documented; new tickers pre-warmed. |
| Dependencies | F2.5 |
| Priority / milestone | P2 / M5 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog. |
| Known limitations | None. |
| Definition of done | mvp_tickers updated with tests. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

### 6.6 Planned: auditability and governance (4)

| ID | Feature | Priority | Implementation | Validation | Milestone |
|---|---|---|---|---|---|
| F12.2 | Decision history, thesis tracking and journal | P2 | Not implemented | Not validated | M2 |
| F12.4 | Run provenance and reproducibility metadata | P1 | Not implemented | Not validated | M2 |
| F15.4 | Agent instructions (AGENTS.md) | P2 | Partially implemented | Not validated | M2 |
| F17.3 | Thesis change detection (B2) | P2 | Not implemented | Not validated | M2 |

#### F12.2: Decision history, thesis tracking and journal

| Field | Content |
|---|---|
| User problem / opportunity | Compare today's view with earlier ones and detect thesis drift. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Decide storage (PD-2) after persistence v2. |
| Scope and acceptance criteria | Each analysis is stored once with its inputs; two runs of a ticker can be compared and differences listed. |
| Dependencies | F12.1; PD-2 |
| Priority / milestone | P2 / M2 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | decisions/current and decisions/history are empty; journal/TEMPLATE_journal_entry.json and portfolio/thesis/TEMPLATE_thesis.json are unused templates (D7, B1, B2). |
| Known limitations | No history exists; the CNQ instability (FND-3) cannot even be tracked systematically. |
| Definition of done | Reader and comparison renderer tested; templates integrated or removed. Plus the checkpoint in the maintenance protocol. |
| Key risks | Storage choice (JSON files vs SQLite). |
| Open product decision | PD-2: JSON files (simple, git-ignored) vs SQLite (queryable). |

#### F12.4: Run provenance and reproducibility metadata

| Field | Content |
|---|---|
| User problem / opportunity | Know exactly what produced a decision. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Include in persistence v2. |
| Scope and acceptance criteria | Every persisted decision lists model id, prompt hash, git commit, cache timestamps. |
| Dependencies | F12.1 |
| Priority / milestone | P1 / M2 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | No LLM model id, prompt version, code version or data snapshot hash is stored in the persisted JSON (key list inspected). |
| Known limitations | Needed to explain run-to-run variation (FND-3). |
| Definition of done | Fields populated and tested. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F15.4: Agent instructions (AGENTS.md)

| Field | Content |
|---|---|
| User problem / opportunity | Standing rules for future AI-assisted work. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Point AGENTS.md at the maintenance protocol (needs approval). |
| Scope and acceptance criteria | AGENTS.md references the protocol and the full-suite gate. |
| Dependencies | F15.3 |
| Priority / milestone | P2 / M2 |
| Implementation / validation | Partially implemented / Not validated |
| Evidence for status | AGENTS.md is 47 bytes ('Imported Claude Cowork project instructions' only). |
| Known limitations | The protocol exists in docs but is not wired into the agent instructions. |
| Definition of done | File updated and reviewed. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F17.3: Thesis change detection (B2)

| Field | Content |
|---|---|
| User problem / opportunity | Spot drift between runs. |
| Expected outcome | Item meets the acceptance criteria below. Next action: After persistence v2. |
| Scope and acceptance criteria | Two stored runs produce a list of changed moat, quality, severity and breaker fields. |
| Dependencies | F12.2 |
| Priority / milestone | P2 / M2 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog B2; depends on history. |
| Known limitations | None. |
| Definition of done | Renderer and tests. Plus the checkpoint in the maintenance protocol. |
| Key risks | Run-to-run LLM variation will generate noise. |
| Open product decision | None. |

### 6.7 Planned: operational readiness (5)

| ID | Feature | Priority | Implementation | Validation | Milestone |
|---|---|---|---|---|---|
| F12.3 | Session persistence across browser refresh | P3 | Not implemented | Not validated | M4 |
| F16.2 | Dependency pinning and reproducible environment | P2 | Partially implemented | Not validated | M4 |
| F16.3 | Continuous integration | P2 | Not implemented | Not validated | M4 |
| F16.4 | Logging and observability | P3 | Requires investigation | Not validated | M4 |
| F16.5 | Scheduled cache refresh | P2 | Not implemented | Not validated | M4 |

#### F12.3: Session persistence across browser refresh

| Field | Content |
|---|---|
| User problem / opportunity | Do not lose the conversation. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | F12.2 |
| Priority / milestone | P3 / M4 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog B12; session is st.session_state only. |
| Known limitations | None. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F16.2: Dependency pinning and reproducible environment

| Field | Content |
|---|---|
| User problem / opportunity | Same results on another machine. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Pin tested versions. |
| Scope and acceptance criteria | A fresh venv built from the pinned file runs the suite with the same result. |
| Dependencies | None |
| Priority / milestone | P2 / M4 |
| Implementation / validation | Partially implemented / Not validated |
| Evidence for status | requirements.txt uses open lower bounds (>=) only; no lock file. |
| Known limitations | yfinance and streamlit behaviour can change between installs. |
| Definition of done | Pinned file merged. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F16.3: Continuous integration

| Field | Content |
|---|---|
| User problem / opportunity | Automatic full-suite run on every change. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Add a CI or local pre-commit full-suite command. |
| Scope and acceptance criteria | A single command runs the full suite and fails on regressions. |
| Dependencies | F14.2 |
| Priority / milestone | P2 / M4 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | No .github, tox, pytest.ini, setup.cfg or pyproject found. |
| Known limitations | Regression FND-1 reached the working tree unnoticed. |
| Definition of done | Command documented in protocol. Plus the checkpoint in the maintenance protocol. |
| Key risks | Low. |
| Open product decision | None. |

#### F16.4: Logging and observability

| Field | Content |
|---|---|
| User problem / opportunity | Diagnose failures. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Define one logging setup. |
| Scope and acceptance criteria | One logging setup is documented and used by UI, CLI and scripts. |
| Dependencies | None |
| Priority / milestone | P3 / M4 |
| Implementation / validation | Requires investigation / Not validated |
| Evidence for status | basicConfig only in fetcher.py:35 and prewarm_mvp.py:218; other modules use logging.getLogger. |
| Known limitations | Logging configuration is implicit and import-order dependent. |
| Definition of done | Setup merged; documented. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F16.5: Scheduled cache refresh

| Field | Content |
|---|---|
| User problem / opportunity | Warm data without manual work. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Windows Task Scheduler wrapper. |
| Scope and acceptance criteria | A scheduled run refreshes the 33-ticker cache and logs result. |
| Dependencies | F2.5 |
| Priority / milestone | P2 / M4 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog B13. |
| Known limitations | Manual prewarm every 24-48h. |
| Definition of done | Documented and verified over two cycles. Plus the checkpoint in the maintenance protocol. |
| Key risks | Rate limiting. |
| Open product decision | None. |

### 6.8 Backlog / future opportunities (11)

| ID | Feature | Priority | Implementation | Validation | Milestone |
|---|---|---|---|---|---|
| F2.6 | Alternative / secondary data providers (FMP, Alpha Vantage, Polygon) | P3 | Not implemented | Not validated | M6 |
| F2.7 | Source reliability scoring and cross-source reconciliation | P3 | Not implemented | Not validated | M6 |
| F2.8 | Automatic peer data acquisition | P2 | Not implemented | Not validated | M6 |
| F3.5 | Sector/industry context in research prompts | P3 | Not implemented | Not validated | M6 |
| F4.5 | D&A and working-capital persistence for FCF reconciliation | P3 | Not implemented | Not validated | M6 |
| F5.6 | Peer-relative valuation | P2 | Not implemented | Not validated | M6 |
| F6.4 | Portfolio-level summary across positions | P3 | Not implemented | Not validated | M6 |
| F11.3 | Scenario persistence and audit | P3 | Not implemented | Not validated | M6 |
| F16.6 | Multi-user deployment and authentication | P3 | Not implemented | Not validated | M6 |
| F17.1 | Price-target alerts (B10) | P3 | Not implemented | Not validated | M6 |
| F17.2 | Earnings-release refresh trigger (B11) | P3 | Not implemented | Not validated | M6 |

#### F2.6: Alternative / secondary data providers (FMP, Alpha Vantage, Polygon)

| Field | Content |
|---|---|
| User problem / opportunity | Redundancy against Yahoo outages and field gaps. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer until the evidence-integrity milestones are done. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | Product decision on providers and budget |
| Priority / milestone | P3 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Only .env.example placeholders exist; no code references the keys (grep). |
| Known limitations | No second source, so no cross-checking of Yahoo values. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F2.7: Source reliability scoring and cross-source reconciliation

| Field | Content |
|---|---|
| User problem / opportunity | Flags suspect inputs before they reach a decision. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Revisit after F2.6. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | F2.6 |
| Priority / milestone | P3 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | No module found. Evidence tiers exist for research (see F9.3) but not for market data. |
| Known limitations | None. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F2.8: Automatic peer data acquisition

| Field | Content |
|---|---|
| User problem / opportunity | Peer-relative valuation instead of absolute target multiples. |
| Expected outcome | Item meets the acceptance criteria below. Next action: See F5.6. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | Peer-universe definition |
| Priority / milestone | P2 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | PeerData model exists; nothing populates it (docs: backlog B5, debt D3). |
| Known limitations | Wrong peer sets can be worse than none. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F3.5: Sector/industry context in research prompts

| Field | Content |
|---|---|
| User problem / opportunity | Better moat and risk judgement. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | F3.1 |
| Priority / milestone | P3 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog B15; no sector context found in prompts. |
| Known limitations | None. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F4.5: D&A and working-capital persistence for FCF reconciliation

| Field | Content |
|---|---|
| User problem / opportunity | Complete FCF-vs-earnings reconciliation. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | F2.3 |
| Priority / milestone | P3 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog B4 / debt D4; normalizer discards these fields. |
| Known limitations | Reconciliation shows OCF and capex only. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F5.6: Peer-relative valuation

| Field | Content |
|---|---|
| User problem / opportunity | More defensible multiples. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer behind evidence-integrity work. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | F2.8 |
| Priority / milestone | P2 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog B5 / debt D3. |
| Known limitations | None. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | Wrong peers degrade quality. |
| Open product decision | None. |

#### F6.4: Portfolio-level summary across positions

| Field | Content |
|---|---|
| User problem / opportunity | See WATCH/HOLD/REDUCE for all holdings at once. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | F12.2 |
| Priority / milestone | P3 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog B8; requires decision persistence. |
| Known limitations | None. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F11.3: Scenario persistence and audit

| Field | Content |
|---|---|
| User problem / opportunity | Record what-ifs the user explored. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | F12.1 |
| Priority / milestone | P3 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Scenario results are not written to disk (no persistence call found). |
| Known limitations | None. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F16.6: Multi-user deployment and authentication

| Field | Content |
|---|---|
| User problem / opportunity | Not required for single-user MVP. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | Product decision |
| Priority / milestone | P3 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Docs state out of MVP scope. |
| Known limitations | None. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F17.1: Price-target alerts (B10)

| Field | Content |
|---|---|
| User problem / opportunity | Be notified when a WATCH name enters the buy zone. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | F12.2; scheduler |
| Priority / milestone | P3 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog only. |
| Known limitations | None. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

#### F17.2: Earnings-release refresh trigger (B11)

| Field | Content |
|---|---|
| User problem / opportunity | Avoid stale fundamentals after earnings. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Defer. |
| Scope and acceptance criteria | To be defined when the item is promoted from backlog and scope is approved by the owner. |
| Dependencies | Event calendar |
| Priority / milestone | P3 / M6 |
| Implementation / validation | Not implemented / Not validated |
| Evidence for status | Backlog only. |
| Known limitations | None. |
| Definition of done | Defined at promotion. Plus the checkpoint in the maintenance protocol. |
| Key risks | None identified. |
| Open product decision | None. |

### 6.9 Blocked or awaiting a product decision (1)

| ID | Feature | Priority | Implementation | Validation | Milestone |
|---|---|---|---|---|---|
| F15.5 | Repository hygiene (root-level diagnostics, legacy scripts, phase reports) | P3 | Requires investigation | Not validated | M4 |

#### F15.5: Repository hygiene (root-level diagnostics, legacy scripts, phase reports)

| Field | Content |
|---|---|
| User problem / opportunity | Findable, maintainable repo. |
| Expected outcome | Item meets the acceptance criteria below. Next action: Decide keep, move to docs/archive, or remove. |
| Scope and acceptance criteria | A list of files with keep/archive/remove decisions is approved by the owner. |
| Dependencies | Owner decision |
| Priority / milestone | P3 / M4 |
| Implementation / validation | Requires investigation / Not validated |
| Evidence for status | Root holds 4 diagnostic scripts, 4 .bat files, 3 diagnostic JSON outputs, 16 PHASE_* reports and legacy run_analysis.py (909 lines) and run_phase77_analysis.py (1,812 lines). run_agent.py contains the demo path (D6). |
| Known limitations | Unclear which scripts are still used. |
| Definition of done | Moves committed with owner authorization. Plus the checkpoint in the maintenance protocol. |
| Key risks | Deleting something still used. |
| Open product decision | PD-6: archive in place, move under docs/archive, or delete. |

## 7. Full feature inventory by functional area

Each feature has two rows: status and value (first table) and evidence, limitations, dependencies and next action (second table).

### 1. Product foundation and configuration

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F1.1 | Investment philosophy and threshold configuration | Decision rules are explicit, editable and not buried in code. | Implemented | Validated | P2 |
| F1.2 | MVP ticker universe (33 tickers) and custom ticker fallback | Pre-approved, pre-warmed universe covering the investor's markets (CA, US, IN). | Implemented | Validated | P2 |
| F1.3 | Secrets and environment configuration | API keys are kept out of source control and the app fails safe without them. | Partially implemented | Not validated | P1 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F1.1 | config/investment_philosophy.md, thresholds.yaml, valuation_config.yaml exist; loaded by thresholds_engine.py; test_quality_engine (17) and test_valuation (89) pass. | Philosophy is prose; only the YAML thresholds are machine-enforced. No config schema validation was found. | None | None. Threshold changes need explicit approval (see protocol). |
| F1.2 | data/mvp_tickers.py (115 lines); ticker-list integrity tests in test_phase105.py (43 pass). | No governance process for adding or removing tickers (backlog B7). | None | See F17.4 for expansion and governance. |
| F1.3 | .env is git-ignored (.gitignore line 13) and no .env exists in the folder; ANTHROPIC_API_KEY is read from the environment (pipeline.py:165, anthropic_researcher.py:381). .env.example lists only FMP, Alpha Vantage and Polygon keys, none of which are referenced by any Python file (grep). | .env.example does not mention ANTHROPIC_API_KEY, the one key the product needs, and lists three unused keys. run_ui.py loads .env through python-dotenv only if that package is installed (run_ui.py:37-40); the CLI path was not checked. | None | Align .env.example with real configuration (FND-9). |

### 2. Financial data acquisition, normalization and freshness

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F2.1 | Yahoo Finance fetch with local JSON cache and TTLs | Fast repeat analyses and resilience to short outages. | Implemented | Validated | P1 |
| F2.2 | Fail-fast 429 handling and cache-poisoning protection | No frozen spinners and no failed fetches served as valid data. | Implemented | Validated | P1 |
| F2.3 | Normalization to CompanyFinancialMetrics (incl. continuing-ops NI) | Typed, auditable financial inputs for every downstream stage. | Implemented | Partially validated | P1 |
| F2.4 | Data freshness assessment and WATCH_PENDING_DATA path | Stale or unknown prices never produce a confident action. | Implemented | Partially validated | P2 |
| F2.5 | Pre-warm script and cache status panel | The demo/daily workflow starts with warm data. | Implemented | Blocked | P2 |
| F2.6 | Alternative / secondary data providers (FMP, Alpha Vantage, Polygon) | Redundancy against Yahoo outages and field gaps. | Not implemented | Not validated | P3 |
| F2.7 | Source reliability scoring and cross-source reconciliation | Flags suspect inputs before they reach a decision. | Not implemented | Not validated | P3 |
| F2.8 | Automatic peer data acquisition | Peer-relative valuation instead of absolute target multiples. | Not implemented | Not validated | P2 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F2.1 | data/ingestion/fetcher.py (454 lines); test_fetcher_p0_p1.py (50 pass); test_ingestion.py (14 pass). | Single unofficial data source (yfinance), no service-level guarantee. Live fetch could not be exercised here (proxy returned HTTP 403 for Yahoo). | yfinance | None for the unit-tested logic. Live validation: see F14.5. |
| F2.2 | pipeline.py fail-fast path with is_rate_limited flag; P0/P1 fixes; test_phase105 and test_fetcher_p0_p1 pass. | Behaviour against live Yahoo rate-limiting was not re-verified in this review (network blocked). | F2.1 | None. |
| F2.3 | normalizer.py (626 lines, modified in working tree); test_ingestion 14, test_phase99 core alignment tests and test_phase11a (12) pass. test_phase93b (5) fail, but they call the live network and fail identically at committed HEAD. | Hard-coded yfinance field names; a rename silently yields None (technical debt D8). The 5 network-dependent tests give no offline evidence for the ITC.NS classification checks. | F2.1 | Recorded-response fixtures (FND-7, F14.2). |
| F2.4 | analytics/data_freshness.py (328 lines); referenced in tests/test_decision.py, test_agent.py, test_phase9.py, test_phase99.py, test_phase10_*.py, test_phase11a.py. | Not individually traced in this review; coverage was inferred from file references, not from assertions read one by one. | F2.3 | Targeted review of freshness assertions. |
| F2.5 | scripts/prewarm_mvp.py (253 lines), ui/data_status.py (247 lines); status-reading tests in test_phase105. | The pre-warm script is network-dependent and was not run. Cache-status counts in docs (32 of 33 ready, Aug 2026) are stale. Cache expires in 24-48h. | F2.1; network | Run on the user's machine to re-baseline cache state. |
| F2.6 | Only .env.example placeholders exist; no code references the keys (grep). | No second source, so no cross-checking of Yahoo values. | Product decision on providers and budget | Defer until the evidence-integrity milestones are done. |
| F2.7 | No module found. Evidence tiers exist for research (see F9.3) but not for market data. | None. | F2.6 | Revisit after F2.6. |
| F2.8 | PeerData model exists; nothing populates it (docs: backlog B5, debt D3). | Wrong peer sets can be worse than none. | Peer-universe definition | See F5.6. |

### 3. Business understanding and research

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F3.1 | Claude API business research (moat, management, industry, risks, bull/bear) | Qualitative understanding required by Gate 1 and Gate 5. | Implemented | Partially validated | P1 |
| F3.2 | Quantitative fallback without API key (Gate 1 fails safe) | The app never invents qualitative research. | Implemented | Validated | P1 |
| F3.3 | Business research models, moat analyzer and synthesizer | Structured, testable qualitative inputs. | Implemented | Validated | P2 |
| F3.4 | Narrative evidence boundary (5-year CAGR, carbon-price claims) and evidence segregation | Unsupported figures must not appear as trusted evidence. | Partially implemented | Partially validated | P0 |
| F3.5 | Sector/industry context in research prompts | Better moat and risk judgement. | Not implemented | Not validated | P3 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F3.1 | anthropic_researcher.py (553 lines, modified), research_orchestrator.py (567 lines, modified), business_research package; test_business_research (73) passes using mocks. | No live API call was made in this review (no key, network blocked). Default model is claude-haiku-4-5-20251001 (anthropic_researcher.py:72). LLM output varies run to run (FND-3). Prompts are not versioned in persisted output. | ANTHROPIC_API_KEY | Live acceptance on one ticker by the owner; add model/prompt provenance (F12.4). |
| F3.2 | Documented and tested safe-failure mode (test_phase105); renderer messages at renderer.py:1664/1786 instruct to set ANTHROPIC_API_KEY. | Result is WAIT_INSUFFICIENT_EVIDENCE for every ticker without a key, which limits offline usefulness. | F3.1 | None. |
| F3.3 | research_models.py (795 lines), moat_analyzer.py, research_synthesizer.py; test_business_research 73 pass. | Models are well tested; the quality of LLM content is not measurable by these tests. | None | None. |
| F3.4 | research_orchestrator._build_context and _parse_bull_bear (modified, uncommitted); test_phase11b tests 53-64 pass; docs/phase11b_evidence_boundary_final_report.md. | Pattern-based: two specific patterns only (5-year CAGR phrasing and carbon-price $/tonne). Any other unsupported fact passes as trusted evidence. Segregated strings go to unsupported_evidence, but no module other than research_orchestrator.py references that field (grep), and it is absent from the persisted decision JSON, so the report's statement that these strings are kept for audit is not backed by persistence in the code inspected. Acceptance was run against stored JSON, not a live regeneration. | F3.1; F12.1 | Decide the boundary strategy (PD-3) and persist the audit field. |
| F3.5 | Backlog B15; no sector context found in prompts. | None. | F3.1 | Defer. |

### 4. Financial quality and metrics

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F4.1 | Financial quality engine and thresholds (7 dimensions) | Deterministic, threshold-based quality tiers. | Implemented | Validated | P1 |
| F4.2 | Honest CAGR labelling (3-year fallback labelled, 5-year only when real) | Prevents a short window being presented as 5-year growth. | Implemented | Validated | P1 |
| F4.3 | ROIC computation and dividend-yield correction (Phase 11A) | Accurate quality and income metrics. | Implemented | Partially validated | P1 |
| F4.4 | Handling of unavailable metrics (None vs UNKNOWN vs zero) end to end | Missing data must never look like a measured value. | Requires investigation | Not validated | P1 |
| F4.5 | D&A and working-capital persistence for FCF reconciliation | Complete FCF-vs-earnings reconciliation. | Not implemented | Not validated | P3 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F4.1 | quality_engine.py (945 lines, modified), thresholds_engine.py, calculations.py; test_quality_engine 17, test_calculations 14, plus quality gate tests in test_decision (308) pass. | Three script-style test files emit collection errors for a helper named test() (FND-8) but their real tests run. | F1.1 | None. |
| F4.2 | calculations.py (modified); test_phase11a tests 1-3 pass. Uncommitted. | Relies on the label text '[5yr baseline unavailable]' as the fallback signal in research_orchestrator (string coupling). | F2.3 | Consider a structured flag instead of label parsing (see F9.5 / FND-5). |
| F4.3 | calculations.py and financial_metrics_model.py (modified); test_phase11a tests 4-9 pass (synthetic inputs). Uncommitted. | No real-ticker baseline comparison was run here, so correctness on live data is unconfirmed. | F2.3 | Owner to confirm ROIC/yield on 2-3 known tickers after live data is available. |
| F4.4 | Calculations return None for missing values; gates and renderer use varied wording (e.g. 'UNAVAILABLE' appears 7 times in calculations.py, once in renderer.py, never in quality_engine.py). No single contract was found. | Not verified that every path (quality engine, gates, renderer, trace, JSON) treats missing metrics identically. | F4.1; F7.2 | Audit and document one contract; add cross-surface tests (F9.5). |
| F4.5 | Backlog B4 / debt D4; normalizer discards these fields. | Reconciliation shows OCF and capex only. | F2.3 | Defer. |

### 5. Valuation and valuation assumptions

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F5.1 | DCF engine (bear/base/bull, excluded for financial institutions) | Intrinsic value estimate with scenarios. | Implemented | Validated | P1 |
| F5.2 | Multiples engines (P/E, P/FCF, EV/EBITDA) | Market-based cross-check on value. | Implemented | Validated | P1 |
| F5.3 | Method selector, weighted synthesis and margin-of-safety zones | A single fair-value range and zone. | Implemented | Validated | P1 |
| F5.4 | Valuation input builder with EPS/FCF same-period alignment | Prevents the ITC.NS-style period mismatch. | Implemented | Validated | P0 |
| F5.5 | Valuation assumptions disclosure and assumption-break monitoring | User can see which assumptions drive value. | Implemented | Partially validated | P2 |
| F5.6 | Peer-relative valuation | More defensible multiples. | Not implemented | Not validated | P2 |
| F5.7 | Valuation method for financial institutions (P/BV, P/TBV, ROE-COE) | 8 of 33 MVP tickers are financials and have no DCF. | Not implemented | Not validated | P2 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F5.1 | dcf_engine.py (406 lines); test_valuation 89 pass. | DCF is intentionally not applied to banks and insurers. | F1.1 | None. |
| F5.2 | multiples_engine.py (749 lines); test_valuation, test_phase91-98 pass (except renderer-level failures, see F10.3). | Target multiples are absolute, not peer-relative (D3). | F1.1 | See F5.6. |
| F5.3 | method_selector.py, valuation_synthesizer.py, margin_of_safety.py; test_valuation 89 pass. | Weights come from configuration; no sensitivity analysis is surfaced to the user. | F5.1; F5.2 | None. |
| F5.4 | valuation_builder.py (493 lines); test_phase99 alignment tests for the builder pass. Documented baseline ITC.NS normalised EPS 16.05 and FCF/share 12.04. | The user-facing reconciliation answers fail in the working tree (see F10.3). No test was confirmed to assert 16.05 and 12.04 at builder level; debt item D9 may be partly stale because test_phase99 asserts 12.04 in rendered text. | F2.3 | Confirm D9 status when fixtures are added (F2.3). |
| F5.5 | key_assumptions is persisted in decision JSON; a valuation-assumption monitoring indicator is added in gate5_adversarial.extract_thesis_breakers (display only). | The monitoring indicator text embeds the discount-rate derivation; its value to the user is unvalidated. | F5.3 | Include in cross-surface consistency tests (F9.5). |
| F5.6 | Backlog B5 / debt D3. | None. | F2.8 | Defer behind evidence-integrity work. |
| F5.7 | Backlog B16; DCF excluded for banks/insurers (confirmed in docs; not re-read in code). | Financials rely on multiples only. | Product decision on methods | Owner to approve methods. |

### 6. Portfolio context and privacy

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F6.1 | Weight-only portfolio context and privacy rule | No shares, cost basis or account value ever enter the system. | Implemented | Validated | P1 |
| F6.2 | Concentration analysis and incremental scenarios | Position sizing awareness. | Implemented | Validated | P2 |
| F6.3 | Sunk-cost protection (average cost excluded from decision) | Decisions are forward-looking. | Implemented | Validated | P1 |
| F6.4 | Portfolio-level summary across positions | See WATCH/HOLD/REDUCE for all holdings at once. | Not implemented | Not validated | P3 |
| F6.5 | Concentration alert in the UI | Prevents inadvertent over-concentration. | Not implemented | Not validated | P2 |
| F6.6 | Portfolio snapshot updater and refresh script | Keeps weights current. | Requires investigation | Not validated | P3 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F6.1 | portfolio_models.py, portfolio_synthesizer.py; test_portfolio 108 pass; conversation layer passes only portfolio_weight_pct (manager.py header). | portfolio/portfolio_snapshot.csv and watchlist.csv are git-ignored local files; their contents were not inspected. | None | None. |
| F6.2 | concentration_analyzer.py, incremental_scenarios.py; test_portfolio pass. | Not surfaced as a UI alert (F6.5). | F6.1 | None. |
| F6.3 | cost_basis_excluded_note is emitted in persisted JSON; documented test coverage in test_decision. | None. | F6.1 | None. |
| F6.4 | Backlog B8; requires decision persistence. | None. | F12.2 | Defer. |
| F6.5 | No concentration reference in ui/app.py (grep). | Logic exists, display does not. | F6.2 | Small UI change after F13.3 smoke tests exist. |
| F6.6 | data/ingestion/portfolio_updater.py (329 lines) and scripts/refresh_portfolio.py exist; not exercised, no matching named tests were identified. | Purpose and current use unclear; depends on git-ignored local CSV. | Local CSV | Owner to confirm whether this is still used. |

### 7. Five-gate decision architecture and action synthesis

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F7.1 | Gate 1: business understanding | Stops analysis when the business is not understood. | Implemented | Validated | P0 |
| F7.2 | Gate 2: financial quality | Quality is the primary filter and caps the action. | Implemented | Validated | P0 |
| F7.3 | Gate 3: valuation attractiveness | Valuation is the timing filter. | Implemented | Validated | P0 |
| F7.4 | Gate 4: portfolio fit | Adjusts action for existing exposure. | Implemented | Validated | P1 |
| F7.5 | Decision synthesis, 8 actions and confidence | One explainable action with confidence. | Implemented | Validated | P0 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F7.1 | gate1_understanding.py (198 lines); test_decision 308 pass. | None. | F3.1 | None. |
| F7.2 | gate2_quality.py (420 lines); test_decision pass. | Missing-metric handling still needs the audit in F4.4. | F4.1 | See F4.4. |
| F7.3 | gate3_valuation.py; test_decision pass. | None. | F5.3 | None. |
| F7.4 | gate4_portfolio.py; test_decision and test_portfolio pass. | None. | F6.1 | None. |
| F7.5 | decision_synthesizer.py (1,552 lines; 2-line uncommitted change); 8 DecisionAction values confirmed in decision_models.py; test_decision 308 pass in both HEAD and working tree. | Very large module with many text builders mixed with rule logic; maintenance cost. Gate 5 SEVERE semantics differ between older docs and current code (FND-6). | F7.1-F7.4; F8.1 | None for logic. Documentation reconciliation in F15.1. |

### 8. Adversarial challenge and thesis breakers

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F8.1 | Gate 5 severity model (n_high, n_medium_equiv, n_bear thresholds) | A credible severe risk overrides optimistic gates. | Implemented | Partially validated | P0 |
| F8.2 | UNKNOWN likelihood semantics (preserved, conservative for severity) | Admits uncertainty without hiding it. | Implemented | Validated | P0 |
| F8.3 | Severity-contributing breakers vs monitoring-only indicators | The user sees which risks drove the verdict and which are only watch items. | Implemented | Partially validated | P0 |
| F8.4 | Thesis-breaker generation with structured details and plain-string fallback | Specific, monitorable conditions with likelihood and evidence. | Implemented | Partially validated | P1 |
| F8.5 | Gate 5 explanation and breaker-specific Q&A | User can ask why Gate 5 is SEVERE or why a breaker is MEDIUM. | Implemented | Validated | P0 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F8.1 | gate5_adversarial.py (354 lines, modified); thresholds verbatim in docs/logic/decision-gates.md; test_phase11b groups 1-3 pass (68 total). | Output is unstable across runs because the LLM regenerates breakers: persisted CNQ.TO runs show Sep 30 HOLD (Gate 5 HIGH; 1 MEDIUM + 2 UNKNOWN = 3 medium-equivalent), Oct 1 REDUCE (SEVERE; 2 MEDIUM + 2 UNKNOWN = 4, meeting the >=4 SEVERE rule) and Oct 2 REDUCE (SEVERE; 1 MEDIUM + 4 UNKNOWN = 5). Each run lists different breaker conditions (FND-3). The reports claiming CNQ stays HOLD rest on the Sep 30 file. | F3.1; F8.2 | Investigate stability and evidence behind UNKNOWN-driven SEVERE; owner decision PD-1. No threshold change without approval. |
| F8.2 | decision_models.ThesisBreaker; test_phase11b group 2 and test 65 pass; displayed as UNKNOWN in report and trace. | Conservative counting can on its own produce SEVERE (see F8.1). | None | Decision PD-1. |
| F8.3 | is_monitoring_only is set in gate5_adversarial.extract_thesis_breakers and persisted in JSON; routed in decision_trace and renderer; test_phase11b tests 53, 54, 58, 66 pass. Monitoring items are not passed to evaluate_gate5 (per report; the persisted Oct 1/2 files show 1 monitoring item each). | Uncommitted. The persisted Sep 30 file (pre-11B) shows the same indicator as a normal breaker. Latest live acceptance of the split was done on stored JSON, not a fresh run. | F8.1 | Run a live acceptance after F9.5 is built. |
| F8.4 | research_orchestrator parses thesis_breaker_details; fallback path covered by test_phase11b group 3. | Content quality depends on the LLM; breaker sets vary between runs. | F3.1 | See F8.1. |
| F8.5 | RESOLVED 2026-11-06 (FND-1): whole-word matching plus breaker-context test in renderer.py; tests/test_phase11b_routing_regression.py added (23 tests); 56 regressed tests pass; full suite 1,326 passed / 5 failed (F14.2) / 3 errors (F14.3), no failure that is not also at HEAD. Original finding: renderer._answer_gate5_explanation, _answer_breaker_specific, _answer_breaker_likelihood_question; their own tests pass (test_phase11b). The likelihood intercept at renderer.py:287 matches 'low', 'medium', 'high' or 'unknown' as substrings of the question, so any question with 'why' and a word like 'lower' is captured (FND-1). | Headless live-app smoke test passed 2026-11-06 (real run_ui.py session, cached CNQ.TO analysis, 3 fixture breakers injected because no LLM key was available): ordinary, genuine, paraphrased, Gate 5 and UNKNOWN questions routed as the 23 regression tests expect, with no Streamlit exceptions. No browser visual check was performed. Paraphrased breaker questions that share no words with a stored breaker and use no breaker vocabulary fall through to generic handlers (by design, option B). Dollar-sign rendering in breaker answers is a separate open item under F9.4. About 25 other substring checks remain in renderer.py (FND-13). | F10.3 | Commit FND-1 after owner approval (validated, uncommitted). FND-13 and F9.4 are separate items. |

### 9. Decision Trace and explainability

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F9.1 | Decision Trace builder and renderer | Gate-by-gate audit trail of why the action was chosen. | Implemented | Validated | P0 |
| F9.2 | Trace surfaced in the Streamlit UI (Why this decision?) | Explainability where the user looks. | Implemented | Not validated | P1 |
| F9.3 | Evidence tiers and provenance in outputs | Distinguish filings, databases and model-derived claims. | Implemented | Partially validated | P1 |
| F9.4 | Rendering safety for conditions containing < > and $ | Breaker text such as 'Brent <$40/bbl' must display faithfully. | Implemented | Partially validated | P1 |
| F9.5 | Cross-surface consistency (report, chat, trace, JSON agree) | The same facts everywhere. | Requires investigation | Not validated | P1 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F9.1 | analytics/decision/decision_trace.py (296 lines, untracked); test_phase11a tests 10-12 and test_phase11b trace tests pass. Uncommitted. | Trace is rebuilt on demand and is not stored in the decision JSON. | F7.5; F8.3 | Persist alongside the decision (F12.1). |
| F9.2 | ui/app.py:388-395 renders the trace with st.code. | No automated UI tests exist. | F13.3 | Cover in UI smoke test. |
| F9.3 | Tiering described in docs and models; evidence_sources, supporting_evidence and contradictory_evidence persisted. | No end-to-end check that each displayed claim maps to a source; LLM figures can lack provenance (see F3.4). | F3.4 | Fold into F9.5 and F12.4. |
| F9.4 | renderer._md_safe escapes < and > only (renderer.py); test 67-68 pass. The earlier live symptom ('<40/bblornaturalgassustained<2 USD/MMBtu') shows words run together, which is typical of Streamlit treating text between two dollar signs as LaTeX math. No dollar-sign escaping exists in renderer.py or ui/app.py (grep) and 41 markdown/text render calls exist in the UI. | Hypothesis, not yet reproduced here: the dollar-sign pairs, not the angle brackets, may be the main cause. The current fix may not resolve the visible symptom. **Observed 2026-11-06 (headless live-app smoke test):** a breaker-likelihood answer for 'Sustained crude oil prices below $60/bbl for 12+ months' contains two unescaped '$' in one message (breaker line and Note line), which Streamlit will likely render as math. Not confirmed visually (no browser check). Pre-existing, not caused by FND-1; open and not fixed. | None | Reproduce in the built-in browser or Streamlit AppTest, then fix once for all render paths (FND-4). |
| F9.5 | Individual surfaces are tested; no test compares action, Gate 5 severity, breaker partitions and assumptions across all four. The FND-1 regression shows chat answers can drift from the report. | Unverified. | F9.1; F12.1 | Create a consistency test suite. |

### 10. Conversational interface, intents and follow-ups

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F10.1 | ConversationManager, session state and error handling | Single entry point; friendly errors; no tracebacks to the UI. | Implemented | Validated | P1 |
| F10.2 | Intent classification (6 intents, regex patterns) | Routes analyse, follow-up, metric, evidence, what-if, unknown. | Implemented | Validated | P1 |
| F10.3 | Follow-up answers from stored assessment (FCF vs EPS, valuation, risks, data quality) | Answers questions without new data calls. | Implemented | Validated | P0 |
| F10.4 | Metric explanations and evidence requests in chat | Teaches terms and cites sources. | Implemented | Validated | P2 |
| F10.5 | Natural-language what-if (price, EPS, growth) in chat | Ask hypothetical valuation questions. | Partially implemented | Not validated | P2 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F10.1 | conversation/manager.py (412), session.py; test_phase10_conversation 43 and test_phase10_ui 21 pass (these exercise the manager, not Streamlit). | Session state is in memory only (F12.3). | None | None. |
| F10.2 | conversation/intent.py (279 lines); tests pass. | Pattern matching only; by design not NLP. | None | None. |
| F10.3 | RESOLVED 2026-11-06 (FND-1): whole-word matching plus breaker-context test in renderer.py; tests/test_phase11b_routing_regression.py added (23 tests); 56 regressed tests pass; full suite 1,326 passed / 5 failed (F14.2) / 3 errors (F14.3), no failure that is not also at HEAD. Original finding: At committed HEAD 5 tests fail (known network tests). In the working tree 61 fail: test_phase96 (22), test_phase95 (14), test_phase97 (8), test_phase99 (5), test_phase94d (5), test_phase98 (2), plus the 5 network tests. Example output for 'Why is FCF/share lower than EPS specifically? Please reconcile by capex' is 'No thesis breakers are recorded for ITC Ltd ...'. | Headless live-app smoke test passed 2026-11-06 (real run_ui.py session, cached CNQ.TO analysis, 3 fixture breakers injected because no LLM key was available): ordinary, genuine, paraphrased, Gate 5 and UNKNOWN questions routed as the 23 regression tests expect, with no Streamlit exceptions. No browser visual check was performed. **Outstanding, tracked under FND-2:** the historical Phase 11B reports (docs/phase11b_corrective_final_report.md and docs/phase11b_evidence_boundary_final_report.md) cite only the 58/68 tests of their own file, not the full suite; they have not yet been corrected. | F8.5 | Correct the historical Phase 11B reports (FND-2). |
| F10.4 | intent.explain_metric; manager handlers; test_phase10_conversation passes. | Generic explanations only. | None | None. |
| F10.5 | Intent SCENARIO_WHAT_IF exists; manager._handle_scenario forwards to existing renderer answers ('at what price', 'what would change'). No engine recalculates valuation for 'what if EPS grows 10%'. | Name overlap with the Phase 11B likelihood scenario engine (F11.1) is confusing. | F11.1 | Decision PD-4 on scope. |

### 11. Scenario analysis and what-if functionality

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F11.1 | Scenario engine: breaker likelihood overrides recalculate Gate 5 and action | Test how the decision changes if a risk becomes more or less likely. | Implemented | Validated | P1 |
| F11.2 | What-if panel in the Streamlit UI | Interactive scenario testing. | Implemented | Not validated | P1 |
| F11.3 | Scenario persistence and audit | Record what-ifs the user explored. | Not implemented | Not validated | P3 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F11.1 | analytics/decision/scenario_engine.py (273 lines, untracked); test_phase11b group 5 passes; baseline is never mutated (per design contract and tests). Uncommitted. | Only likelihood overrides; no valuation or fundamentals inputs. | F8.1 | None. |
| F11.2 | ui/app.py:399-471 builds BreakerOverride objects and calls run_scenario. A leftover duplicate override computation (lines 443-455) is overwritten by a simplified loop. | No UI tests; dead code present. | F11.1; F13.3 | UI smoke test, then tidy. |
| F11.3 | Scenario results are not written to disk (no persistence call found). | None. | F12.1 | Defer. |

### 12. Persistence and auditability

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F12.1 | Decision JSON persistence | Audit trail and regression artifacts. | Implemented | Partially validated | P1 |
| F12.2 | Decision history, thesis tracking and journal | Compare today's view with earlier ones and detect thesis drift. | Not implemented | Not validated | P2 |
| F12.3 | Session persistence across browser refresh | Do not lose the conversation. | Not implemented | Not validated | P3 |
| F12.4 | Run provenance and reproducibility metadata | Know exactly what produced a decision. | Not implemented | Not validated | P1 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F12.1 | pipeline._persist_decision writes data/output/{TICKER}_{DATE}_decision.json; five files exist (CNQ x3, TD x2); to_dict covers action, gates, breakers with is_monitoring_only and evidence. | A second run for the same ticker and date overwrites the first. No schema version, no model/prompt/data-snapshot identifiers, no decision trace, no unsupported_evidence, no scenario results. data/output/*.json is git-ignored. Failures are logged and swallowed. | F7.5 | Design persistence v2 (R/F12.4). |
| F12.2 | decisions/current and decisions/history are empty; journal/TEMPLATE_journal_entry.json and portfolio/thesis/TEMPLATE_thesis.json are unused templates (D7, B1, B2). | No history exists; the CNQ instability (FND-3) cannot even be tracked systematically. | F12.1; PD-2 | Decide storage (PD-2) after persistence v2. |
| F12.3 | Backlog B12; session is st.session_state only. | None. | F12.2 | Defer. |
| F12.4 | No LLM model id, prompt version, code version or data snapshot hash is stored in the persisted JSON (key list inspected). | Needed to explain run-to-run variation (FND-3). | F12.1 | Include in persistence v2. |

### 13. UI/UX and usability

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F13.1 | Streamlit UI: ticker dropdown, weight input, Analyse, Force Refresh, data status | Usable without developer help. | Implemented | Not validated | P1 |
| F13.2 | Usability review of long reports and chat formatting | Readable output for a busy investor. | Requires investigation | Not validated | P2 |
| F13.3 | UI automated smoke tests | Catch UI regressions. | Not implemented | Not validated | P1 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F13.1 | ui/app.py (631 lines), ui/data_status.py (247), run_ui.py; Phase 10.5 reported acceptance; behaviour backed by manager-level tests only. | No automated UI test. This review did not launch the app (no network/API key; built-in browser not used). | F2.5 | UI smoke test (F13.3); owner walkthrough. |
| F13.2 | Report renderer.py is 1,846 lines; recent formatting issues (FND-4, and 6-vs-5 breaker count defect D4 fixed in 11B). | No structured usability review exists. | F13.1 | Short owner-led review once FND-1 and FND-4 are fixed. |
| F13.3 | Backlog B14 / debt D5; none exist. | None. | F13.1 | Streamlit AppTest or Playwright. |

### 14. Testing, reliability and error handling

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F14.1 | Automated test suite | Regression safety. | Implemented | Partially validated | P0 |
| F14.2 | Network-dependent tests (test_phase93b, 5) | Deterministic tests. | Implemented | Failed | P2 |
| F14.3 | Collection errors in three script-style test files | Clean test output. | Implemented | Failed | P3 |
| F14.4 | Never-raise pipeline and friendly error messages | No tracebacks reach the user. | Implemented | Validated | P1 |
| F14.5 | Live end-to-end acceptance harness | Prove behaviour on real data. | Not implemented | Not validated | P1 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F14.1 | 1,309 tests collected across 28 files. Run in a scratch copy (Python 3.10.12, deps installed in a venv outside the repo): working tree 1,247 passed, 61 failed, 1 skipped, 3 errors; committed HEAD 1,223 passed, 5 failed, 1 skipped, 3 errors. | docs/engineering/test-status.md still states 1,228 passed. Reports for Phase 11B cite only their own file. | None | Adopt the full-suite gate (FND-2). |
| F14.2 | Fail at HEAD and in working tree with HTTP 403 from the sandbox proxy; known debt D1. | No offline evidence for ITC.NS classification. | F2.3 | Replace with recorded fixtures. |
| F14.3 | ERROR tests/test_calculations.py::test, test_ingestion.py::test, test_quality_engine.py::test: a helper named test() is collected. | Cosmetic; real tests in those files run. | None | Rename helper. |
| F14.4 | pipeline.PipelineResult always returned; manager catches exceptions; test_phase105. | Persistence failures are only logged (F12.1). | None | None. |
| F14.5 | Live acceptance so far was manual or run on stored JSON. This review had no network/API access to run any live check. | Sandbox limits validation. | Network, API key | Owner-run live acceptance script for 2 tickers after M0. |

### 15. Documentation and product governance

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F15.1 | Phase 10.6 documentation pack (31 docs) | Product Owner can understand the product without reading code. | Implemented | Partially validated | P1 |
| F15.2 | Phase 11A/11B reports | Record of what changed and why. | Implemented | Partially validated | P1 |
| F15.3 | Living roadmap, architecture diagrams and maintenance protocol | One authoritative record, updated after every feature. | Implemented | Not validated | P0 |
| F15.4 | Agent instructions (AGENTS.md) | Standing rules for future AI-assisted work. | Partially implemented | Not validated | P2 |
| F15.5 | Repository hygiene (root-level diagnostics, legacy scripts, phase reports) | Findable, maintainable repo. | Requires investigation | Not validated | P3 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F15.1 | docs/ has 31 Markdown files across product, architecture, logic, engineering, governance, po-learning. | Stale versus code: docs/README says Phase 10.6 current and 1,228 passing tests; roadmap.md says Phase 11 not started; current-state.md predates Phase 11; test-status.md predates Phase 11; Gate 5 behaviour differs between docs (see FND-6). | None | Reconcile after M0 (protocol step 7). |
| F15.2 | docs/phase11b_corrective_final_report.md and phase11b_evidence_boundary_final_report.md (untracked). | State 58 and 68 passing tests and CNQ stays HOLD; full suite and the Oct 1/2 persisted REDUCE runs contradict the overall picture. | F10.3 | Add correction notes after M0. |
| F15.3 | Created by this review (three new Markdown documents). | Awaiting owner review; validation = owner acceptance of structure and priorities. | None | Owner review. |
| F15.4 | AGENTS.md is 47 bytes ('Imported Claude Cowork project instructions' only). | The protocol exists in docs but is not wired into the agent instructions. | F15.3 | Point AGENTS.md at the maintenance protocol (needs approval). |
| F15.5 | Root holds 4 diagnostic scripts, 4 .bat files, 3 diagnostic JSON outputs, 16 PHASE_* reports and legacy run_analysis.py (909 lines) and run_phase77_analysis.py (1,812 lines). run_agent.py contains the demo path (D6). | Unclear which scripts are still used. | Owner decision | Decide keep, move to docs/archive, or remove. |

### 16. Deployment, setup and operational readiness

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F16.1 | Local run paths (streamlit via run_ui.py, CLI via run_agent.py) | Single-user local operation. | Implemented | Partially validated | P2 |
| F16.2 | Dependency pinning and reproducible environment | Same results on another machine. | Partially implemented | Not validated | P2 |
| F16.3 | Continuous integration | Automatic full-suite run on every change. | Not implemented | Not validated | P2 |
| F16.4 | Logging and observability | Diagnose failures. | Requires investigation | Not validated | P3 |
| F16.5 | Scheduled cache refresh | Warm data without manual work. | Not implemented | Not validated | P2 |
| F16.6 | Multi-user deployment and authentication | Not required for single-user MVP. | Not implemented | Not validated | P3 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F16.1 | run_ui.py (48 lines), run_agent.py (494 lines). | Not run in this review. | None | Owner confirms. |
| F16.2 | requirements.txt uses open lower bounds (>=) only; no lock file. | yfinance and streamlit behaviour can change between installs. | None | Pin tested versions. |
| F16.3 | No .github, tox, pytest.ini, setup.cfg or pyproject found. | Regression FND-1 reached the working tree unnoticed. | F14.2 | Add a CI or local pre-commit full-suite command. |
| F16.4 | basicConfig only in fetcher.py:35 and prewarm_mvp.py:218; other modules use logging.getLogger. | Logging configuration is implicit and import-order dependent. | None | Define one logging setup. |
| F16.5 | Backlog B13. | Manual prewarm every 24-48h. | F2.5 | Windows Task Scheduler wrapper. |
| F16.6 | Docs state out of MVP scope. | None. | Product decision | Defer. |

### 17. Future capabilities and unresolved product decisions

| ID | Feature | Intended user value | Implementation | Validation | Priority |
|---|---|---|---|---|---|
| F17.1 | Price-target alerts (B10) | Be notified when a WATCH name enters the buy zone. | Not implemented | Not validated | P3 |
| F17.2 | Earnings-release refresh trigger (B11) | Avoid stale fundamentals after earnings. | Not implemented | Not validated | P3 |
| F17.3 | Thesis change detection (B2) | Spot drift between runs. | Not implemented | Not validated | P2 |
| F17.4 | Ticker universe expansion and governance (B6, B7) | Cover more of the real portfolio. | Not implemented | Not validated | P2 |

| ID | Evidence | Known limitations or defects | Dependencies | Recommended next action |
|---|---|---|---|---|
| F17.1 | Backlog only. | None. | F12.2; scheduler | Defer. |
| F17.2 | Backlog only. | None. | Event calendar | Defer. |
| F17.3 | Backlog B2; depends on history. | None. | F12.2 | After persistence v2. |
| F17.4 | Backlog. | None. | F2.5 | Owner supplies tickers and rule. |

## 8. Unresolved product decisions (options and trade-offs, no decision taken)

| ID | Question | Options | Trade-offs | Related |
|---|---|---|---|---|
| PD-1 | How should UNKNOWN breaker likelihood count toward Gate 5 severity? | (a) Keep: UNKNOWN = MEDIUM-equivalent (current; conservative, but four UNKNOWN items can force SEVERE with no evidence). (b) Cap UNKNOWN's contribution. (c) Require evidence before UNKNOWN counts. | (a) is simple and safe-sided but amplifies LLM variance. (b)/(c) change investment rules and need approval. | F8.1, F8.2 |
| PD-2 | Storage for decision history and journal | (a) Dated JSON files. (b) SQLite. | JSON is simple and git-friendly; SQLite supports comparisons and querying. | F12.2, F12.1 |
| PD-3 | Evidence-boundary strategy | (a) Keep pattern validators and add patterns on demand. (b) Allow-list: LLM figures must match values in the structured context. (c) Structured claim schema from the LLM. | (a) cheap but never complete; (b) stronger, some false positives; (c) largest change. | F3.4 |
| PD-4 | What 'what-if' should mean | (a) Likelihood overrides only (current). (b) Add valuation inputs (price, EPS, growth). (c) Retire the chat what-if intent. | (b) adds value but new logic and tests; (c) simplifies. | F10.5, F11.1 |
| PD-5 | Gate 5 SEVERE semantics | Confirm intended behaviour: REDUCE or HOLD for existing positions (code today), EXIT only with CONCERN quality; new positions capped at WATCH. Or require SEVERE alone to be able to produce EXIT. | Code and updated gate doc agree; older docs disagree. Changing behaviour is a rule change. | F7.5, F8.1 |
| PD-6 | Repository hygiene | (a) Leave. (b) Archive under docs/archive. (c) Delete after review. | Deleting risks removing a script still in use. | F15.5 |
| PD-7 | Commit and branch strategy for Phase 11 work | (a) One commit after M0. (b) Feature branch with separate commits per feature. (c) Split into 11A and 11B commits. | Needs explicit owner authorisation; none made. | FND-11 |

## 9. Sources inspected

- Git: branch, `git status`, `git diff --stat`, last commits, `git archive HEAD` snapshot.
- Code: `analytics/` (agent, decision, business_research, financial_quality, valuation, portfolio), `conversation/`, `data/ingestion/`, `ui/`, `scripts/`, entry points `run_ui.py`, `run_agent.py`; deeper reads of `pipeline.py`, `manager.py`, `intent.py`, `scenario_engine.py`, `decision_trace.py`, `gate5_adversarial.py`, parts of `decision_synthesizer.py` and `renderer.py`.
- Tests: all 28 files in `tests/` executed; failures classified.
- Persisted outputs: five JSON files in `data/output/` compared.
- Config: `config/`, `requirements.txt`, `.env.example`, `.gitignore`.
- Docs: `docs/` index, roadmap, current-state, backlog, test-status, technical-debt, Phase 11B reports, decision-gates diff.

## 10. Validation limitations and assumptions

- No network egress to Yahoo Finance (HTTP 403 from the sandbox proxy) and no Anthropic API key: **no live data or live LLM run was performed.** All LLM-dependent behaviour is validated only through mocks and stored JSON.
- The Streamlit app was not launched; UI status rests on code reading and manager-level tests.
- Tests ran with Python 3.10.12 in a venv outside the repo using unpinned latest dependency versions; the owner's environment versions were not available.
- Not every module was read line by line. Statuses for modules reviewed by tests and file structure only are labelled accordingly in the evidence column.
- The 33-ticker cache state was not re-measured.
- Assumption: tests passing at HEAD represent the last accepted baseline (Phase 10.6).

## 11. Known open questions

1. Is the Oct 2 CNQ.TO REDUCE considered a correct outcome? (PD-1, FND-3)
2. Is `portfolio_updater.py` still used? (F6.6)
3. Which of the root-level scripts and reports may be archived? (F15.5)
4. Should the owner's real portfolio tickers drive the next universe expansion? (F17.4)
5. Are older docs stating 'REDUCE or EXIT' the intended behaviour? (PD-5)

## 12. Links

Source modules: `analytics/decision/`, `analytics/agent/`, `conversation/`, `ui/app.py`. Tests: `tests/test_phase11a.py`, `tests/test_phase11b.py`, `tests/test_decision.py`. Supporting docs: [Roadmap (phase history)](roadmap.md), [Product Backlog (original B-items)](product-backlog.md), [Current State](current-state.md), [Known Limitations](../engineering/known-limitations.md), [Technical Debt](../engineering/technical-debt.md), [Phase 11B corrective report](../phase11b_corrective_final_report.md), [Phase 11B evidence boundary report](../phase11b_evidence_boundary_final_report.md).

## 13. Revision history

| Date | Version | Change | Roadmap item(s) |
|---|---|---|---|
| 2026-10-11 | 1.0 | Baseline created by discovery review; no feature code changed | All |
| 2026-11-06 | 1.1 | FND-1 resolved and validated (uncommitted): F8.5 and F10.3 Failed to Validated, moved from 6.3 to 6.1; counts in section 2 updated; FND-13 added | F8.5, F10.3 |
| 2026-11-06 | 1.2 | Known-limitations wording for F8.5 and F10.3 updated for the headless live-app smoke test (no browser visual check); F10.3 stays Validated with the report correction tracked under FND-2; dollar-sign observation recorded under F9.4 (status unchanged) | F8.5, F10.3, F9.4, FND-2 |
