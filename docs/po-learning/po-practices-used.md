# Product Owner Practices — Scorecard

> **Purpose:** Assess which PO practices have been used, how consistently, and what to strengthen next  
> **Status:** Self-assessment as of Phase 10.6

---

## Practice 1 — Writing acceptance criteria before implementation

**What good looks like:** Every phase brief includes explicit, testable acceptance criteria that the team can verify independently of the PO.

**Phase 10.5 example (strong):**
- "Force Refresh actually forces a fresh fetch" ✅
- "No technical strings exposed in UI error messages" ✅ (with 8 specific "must not contain" assertions)
- "Rate-limit error shows friendly message" ✅

**Phase 10.5 UX polish (weaker):** The UX polish was described at a level of detail (exact forbidden strings, desired message content) that made acceptance criteria implicit rather than a formal checklist. It worked, but the criteria lived in the brief description rather than a separate acceptance criteria table.

**Self-assessment: GOOD.** Criteria exist and are testable. Opportunity: make them explicit as a table in every brief, not embedded in prose.

---

## Practice 2 — Clear scope boundaries (in scope / out of scope)

**What good looks like:** Each phase brief explicitly states what is OUT of scope, preventing scope creep.

**Strengths observed:**
- Phase 10.6 specification explicitly states: "DOCUMENTATION ONLY. Do NOT modify production code. Do NOT refactor code. Do NOT 'fix' issues discovered during documentation."
- Phase 10.5 explicitly excluded: retrying on 429 in interactive path, multi-user support, persistence

**Self-assessment: STRONG.** Explicit out-of-scope statements are consistent. The Phase 10.6 specification is notably precise about what is forbidden.

---

## Practice 3 — Real-ticker validation (not just automated tests)

**What good looks like:** After each phase that touches valuation or financial calculation, verify a known-correct baseline against real data.

**Phase 9.9b (strong):** ITC.NS baseline established with specific numbers (EPS ₹16.05, FCF ₹12.04) and verified against real yfinance data.

**Gap:** No automated test asserts these numbers (Technical Debt D9). The baseline depends on manual re-verification after valuation changes.

**Self-assessment: GOOD.** The practice exists and has been used. Gap: it relies on manual steps and the PO's memory rather than an automated regression test.

---

## Practice 4 — Distinguishing IMPLEMENTED from PROPOSED

**What good looks like:** All documentation and product decisions clearly label what exists vs what is proposed or reconstructed.

**Phase 10.6 (strong):** All documents in `docs/` use consistent labelling: IMPLEMENTED, PROPOSED, RECONSTRUCTED, VERIFIED. The product backlog is explicitly marked "PROPOSED — no items are committed."

**Self-assessment: STRONG.** This is a notable strength of the Phase 10.6 documentation approach.

---

## Practice 5 — Decision recording

**What good looks like:** When a significant decision is made (technical or product), it is recorded with context and rationale.

**Strengths:** The README captures phase history. Architecture decisions are documented in ADRs (Phase 10.6). The decision log captures chronological decisions.

**Gap:** Before Phase 10.6, decision records existed only informally in README history and PHASE_10_5_DESIGN_RECOMMENDATION.md. There was no formal ADR or product decision log.

**Self-assessment: DEVELOPING.** Phase 10.6 establishes the practice. The next phase should use the ADR and product decision log from the start.

---

## Practice 6 — Phase briefs before implementation

**What good looks like:** No code is written until a phase brief exists, specifying the problem, decision, scope, and acceptance criteria.

**Evidence:** All phases from Phase 10 onwards have had explicit written briefs provided by the PO before implementation started. The inspector-first approach (Phase 10.5: "INSPECTION ONLY. No code changes.") is a strong example.

**Self-assessment: STRONG.**

---

## Practice 7 — Honest product maturity assessment

**What good looks like:** The PO can accurately describe the maturity of the product — what works, what doesn't, and what the real-world limitations are.

**Evidence:** `docs/product/current-state.md` includes a frank maturity assessment: "FUNCTIONAL MVP — not a prototype, not production-grade" with explicit caveats about single-user design and yfinance dependency. `docs/engineering/known-limitations.md` lists 12 known limitations without minimising them.

**Self-assessment: STRONG.**

---

## Practice 8 — Backlog management

**What good looks like:** There is a prioritised list of candidate improvements with effort estimates, and the PO can clearly articulate what is NOT being done and why.

**Evidence:** `docs/product/product-backlog.md` has 16 items across 7 themes with effort estimates and value hypotheses. A suggested priority order is included.

**Gap:** No formal prioritisation framework (e.g., WSJF, value/effort matrix). Priority is based on PO judgement.

**Self-assessment: DEVELOPING.** Backlog exists and is reasonably organised. Opportunity: apply a more systematic prioritisation method before Phase 11.

---

## Summary scorecard

| Practice | Rating |
|---------|--------|
| Acceptance criteria before implementation | GOOD |
| Clear scope boundaries | STRONG |
| Real-ticker validation | GOOD |
| IMPLEMENTED vs PROPOSED labelling | STRONG |
| Decision recording | DEVELOPING |
| Phase briefs before implementation | STRONG |
| Honest maturity assessment | STRONG |
| Backlog management | DEVELOPING |

---

## Top 3 PO development priorities

1. **Establish ADR and decision log practice from the start of Phase 11** — not retrospectively.
2. **Create an automated baseline test for ITC.NS** — remove reliance on manual verification after valuation changes.
3. **Apply a prioritisation framework to the backlog** — value/effort matrix or MoSCoW for Phase 11 planning.
