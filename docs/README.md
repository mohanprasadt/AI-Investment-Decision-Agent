# AI Investment Decision Agent — Documentation Index

**Phase 10.6 documentation pack. Created August 2026.**  
**Audience: Product Owner (Mapla) and future collaborators.**

This documentation exists for two purposes:
1. Enable the Product Owner to understand, manage, and make decisions about the product without reading source code.
2. Provide a learning record of Product Owner practices applied throughout the project.

> **Note:** Documentation reflects the repository as inspected at Phase 10.6. All claims are grounded in actual code or established project history. Proposed items are clearly labelled `PROPOSED`. Reconstructed items are labelled `[RECONSTRUCTED]`.

---

## Quick orientation

| Question | Where to look |
|----------|---------------|
| What problem are we solving? | [Product Vision](product/product-vision.md) |
| What is the MVP? | [MVP Definition](product/mvp-definition.md) |
| Where are we in the roadmap? | [Roadmap](product/roadmap.md) |
| What do we actually have today? | [Current State](product/current-state.md) |
| How does the system work? | [Architecture Overview](architecture/architecture-overview.md) |
| How does the decision get made? | [Investment Decision Flow](logic/investment-decision-flow.md) |
| What can users do? | [User Journeys](product/user-journeys.md) |
| What are the risks? | [Assumptions, Risks, Dependencies](governance/assumptions-risks-dependencies.md) |
| What's in the backlog? | [Product Backlog](product/product-backlog.md) |
| Why were decisions made? | [Architecture Decisions](governance/architecture-decisions.md) |
| How do I practice PO skills? | [PO Learning Guide](po-learning/product-owner-learning-guide.md) |

---

## Recommended reading order

### First — understand the product
1. [Product Vision](product/product-vision.md) — problem, user, vision
2. [MVP Definition](product/mvp-definition.md) — what is and isn't in scope
3. [Roadmap](product/roadmap.md) — full phase history and where we are
4. [Current State](product/current-state.md) — what you actually have today

### Then — understand how it works
5. [Architecture Overview](architecture/architecture-overview.md) — system in business and technical terms
6. [Investment Decision Flow](logic/investment-decision-flow.md) — how decisions are produced
7. [User Journeys](product/user-journeys.md) — what users can do end-to-end

### Then — understand quality and risk
8. [Testing Strategy](engineering/testing-strategy.md) — what is tested and what it proves
9. [Test Status](engineering/test-status.md) — current numbers and known failures
10. [Assumptions, Risks, Dependencies](governance/assumptions-risks-dependencies.md)

### For product governance
11. [Product Decisions](governance/product-decisions.md)
12. [Architecture Decisions](governance/architecture-decisions.md)
13. [Decision Log](governance/decision-log.md)

### For PO learning
14. [PO Learning Guide](po-learning/product-owner-learning-guide.md)
15. [Phase Learning Log](po-learning/phase-learning-log.md)
16. [PO Practice Scorecard](po-learning/po-practices-used.md)

---

## Document map

```
docs/
├── README.md                          ← You are here
│
├── product/
│   ├── product-vision.md              ← Problem, user, vision, mission
│   ├── product-goals-and-success-measures.md
│   ├── mvp-definition.md              ← Scope: in / out / post-MVP
│   ├── roadmap.md                     ← Full phase history + next
│   ├── current-state.md               ← What exists today
│   ├── product-backlog.md             ← Prioritised work items
│   ├── user-journeys.md               ← What users can do
│   └── acceptance-strategy.md         ← PO acceptance framework
│
├── architecture/
│   ├── architecture-overview.md       ← Business + technical view
│   ├── component-architecture.md      ← Module-by-module reference
│   ├── data-flow.md                   ← Data journey from ticker to decision
│   ├── data-ingestion-and-cache.md    ← yfinance, cache, TTLs, 429
│   └── conversation-architecture.md   ← UI, session, intent, renderer
│
├── logic/
│   ├── investment-decision-flow.md    ← End-to-end decision explanation
│   ├── valuation-logic.md             ← DCF, P/E, EV/EBITDA, P/FCF
│   ├── financial-quality-logic.md     ← Quality engine and thresholds
│   ├── decision-gates.md              ← Five gates in plain language
│   └── portfolio-context.md           ← How portfolio weight is used
│
├── engineering/
│   ├── testing-strategy.md            ← What is tested and why it matters
│   ├── test-status.md                 ← Current pass/fail numbers
│   ├── external-dependencies.md       ← yfinance, Anthropic API
│   ├── known-limitations.md           ← Honest list of current limits
│   └── technical-debt.md              ← Known debt items
│
├── governance/
│   ├── architecture-decisions.md      ← ADRs for key technical choices
│   ├── product-decisions.md           ← PO-level decisions
│   ├── assumptions-risks-dependencies.md ← RAID register
│   └── decision-log.md                ← Chronological decision record
│
└── po-learning/
    ├── product-owner-learning-guide.md ← PO skills by phase
    ├── phase-learning-log.md           ← Phase-by-phase reflection
    └── po-practices-used.md            ← Scorecard and next steps
```

---

## Current phase

**Phase 10.6 — Documentation & Product Governance Foundation**  
Previous: Phase 10.5 (MVP Usability, Cache Readiness, UX Polish) — **ACCEPTED**  
Next: Phase 11 — to be defined by Product Owner

## Key numbers (as of Phase 10.6 inspection)

| Metric | Value |
|--------|-------|
| MVP ticker universe | 33 tickers |
| Cached tickers (ready) | 32 of 33 |
| Test suite | 1,228 passed, 1 skipped, 3 collection errors (pre-existing) |
| Pre-existing test failures | 5 (test_phase93b, network-dependent) |
| Decision actions supported | 8 |
| Valuation methods | 4 |
| Decision gates | 5 |

---

*Maintained by: Product Owner (Mapla)*  
*Update after every phase: see [Documentation Maintenance](governance/decision-log.md#maintenance-process)*
