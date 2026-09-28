# Product Owner Learning Guide

> **Purpose:** A structured guide to the PO skills used in this project — what they are, where they appear, and how to develop them further  
> **Audience:** The Product Owner (Mapla) — reflects on what you've done and helps you grow

---

## How to use this guide

This is not a checklist to complete. It is a reference for self-development. When you start a new phase, look at the practices in Section 2 and ask: "Am I doing these?" When you review a completed phase, look at what worked and what didn't.

---

## Section 1 — The PO role in this project

In a conventional product team, the Product Owner:
- Represents the user/customer
- Defines what to build (not how)
- Prioritises the backlog
- Accepts or rejects completed work
- Maintains the product vision

In this project, you are the PO AND the sole user AND the domain expert (investor philosophy). This creates unusual advantages and risks:

**Advantages:**
- Deep domain knowledge — you know more about what the system needs than any external PO would
- Fast feedback loops — you can test and respond immediately
- No translation layer — your intent goes directly into the brief

**Risks:**
- Absence of challenge — there is no customer or colleague to push back on your decisions
- PO/developer blurring — when the same person writes the brief and reviews the implementation, it is easy to unconsciously accept work that doesn't fully meet the brief
- Documentation neglect — when the PO is also the primary user, it is easy to skip documentation because you "already know"

**Mitigation:** Write briefs as if you were handing them to someone who would never ask you a question. Write acceptance criteria as if you would not be reviewing the result until a week later with fresh eyes.

---

## Section 2 — Core PO practices used in this project

### 2.1 — The phase brief

Every phase should have a written brief before any work starts. A good brief answers:
- **Problem statement:** What problem does this phase solve?
- **Scope:** What is IN scope and OUT of scope?
- **Acceptance criteria:** How will you know it's done and correct?
- **Constraints:** What must not change?
- **Safety rules:** What must this phase never do?

**Where to see this in practice:**
- Phase 10.5 brief — explicit 6 decisions, 33 ticker universe, acceptance criteria table
- Phase 10.6 brief — explicit "DOCUMENTATION ONLY," 24 specified document sections, forbidden actions

**Development opportunity:** Try writing the acceptance criteria first (before the rest of the brief). If you can't write measurable acceptance criteria, the scope isn't clear enough.

---

### 2.2 — Acceptance criteria

Acceptance criteria are the test of whether a phase is done. They should be:
- **Testable:** Someone else should be able to verify them without asking you
- **Specific:** "Friendly error message" is not testable; "error message does not contain the string 'yfinance'" is testable
- **Pre-agreed:** Written before implementation, not after

**Best example in this project:** Phase 10.5 UX polish — 8 specific "must not contain" assertions for the error message. This level of specificity made the acceptance unambiguous.

**Development opportunity:** For each acceptance criterion, ask: "Could I verify this in 5 minutes without running the code?" If not, it's not specific enough.

---

### 2.3 — Real-ticker validation

Financial analysis code is uniquely difficult to test with automated tests alone because the correct answer requires domain knowledge (is this a reasonable valuation?) not just structural correctness (did the function return a number?).

Real-ticker validation means: run the system on a known company, with known financial data, and verify the output makes sense.

**Best example in this project:** ITC.NS Phase 9.9b baseline — specific numbers (EPS ₹16.05, FCF ₹12.04) verified against actual yfinance data, with a specific explanation for the continuing-ops NI exclusion.

**Development opportunity:** Establish a "golden test set" of 3–5 tickers where you know the expected output. Re-verify these after any change to the valuation or normalisation logic.

---

### 2.4 — Scope discipline

Scope creep is the most common cause of phase failure. In this project, the biggest risk is that a bug or improvement discovered during one phase is fixed within that phase, obscuring the change and bypassing the normal acceptance process.

**Phase 10.6 addresses this explicitly:** "Do NOT modify production code. Do NOT refactor code. Do NOT 'fix' issues discovered during documentation."

**Development opportunity:** Keep a running list during each phase of "things I noticed but did not fix." Add them to the backlog at the end of the phase. This discipline is more important than the individual items.

---

### 2.5 — Technical comprehension without technical depth

As PO, you don't need to write the code — but you need enough technical comprehension to:
- Evaluate whether the implementation matches the brief
- Understand the trade-offs in architectural decisions
- Spot when a proposed solution is simpler than what the brief requires (a warning sign)
- Ask useful questions when something seems wrong

**What this project demonstrates:**
- Understanding the 3-layer architecture (L1/L2/L3) helps you evaluate whether a change to the data layer could affect the decision layer
- Understanding TTL-based caching helps you know when to pre-warm before a demo
- Understanding the gate model helps you evaluate whether a proposed "simplification" would weaken a safety property

**Development opportunity:** When a phase report describes what was built, try to re-explain it in your own words without reading the code. If you can't, ask clarifying questions before accepting the phase.

---

### 2.6 — Investment domain knowledge applied to PO decisions

This project sits at the intersection of software product management and investment analysis. Your investment domain knowledge directly informs better PO decisions:

**Examples where domain knowledge shaped the product:**
- The sunk-cost protection rule (Gate 4) — your awareness of behavioural finance biases
- Continuing-operations NI preference — your understanding that reported EPS ≠ operational EPS
- Sequential gates (quality before valuation) — your investment philosophy, not a software choice
- The adversarial Gate 5 — your awareness that bull cases can be invalidated by single thesis breakers

**Development opportunity:** When a phase produces an unexpected recommendation for a real ticker (e.g., WATCH when you expected ACCUMULATE), trace the decision logic. Use it as an opportunity to verify whether the system's reasoning matches yours — and if not, whether the system is wrong or you are.

---

## Section 3 — PO resources

### On product ownership and backlogs
- Scrum Guide (scrum.org/resources/scrum-guide) — short, foundational
- "Continuous Discovery Habits" (Teresa Torres) — strong on discovery and acceptance criteria
- "Impact Mapping" (Gojko Adzic) — useful for connecting features to business outcomes

### On investment analysis (relevant to this project)
- "The Intelligent Investor" (Benjamin Graham) — value investing foundation
- "Quality Investing" (Lawrence Cunningham et al.) — quality-before-price philosophy
- "Invested" (Danielle Town) — accessible bridge between investing and business analysis

### On technical comprehension for non-developers
- "The Pragmatic Programmer" (Hunt & Thomas) — helps understand software development principles
- "Accelerate" (Forsgren et al.) — research-backed view of engineering quality metrics

---

## Section 4 — Next phase checklist (PO self-review)

Before starting Phase 11:

- [ ] Read `docs/product/product-backlog.md` — what's in the backlog?
- [ ] Identify the single most valuable problem to solve next
- [ ] Write a one-paragraph problem statement (not a solution)
- [ ] Draft acceptance criteria before writing the full brief
- [ ] Confirm scope boundaries — what is explicitly out of scope?
- [ ] Confirm safety constraints — what must this phase never change?
- [ ] Check `docs/governance/decision-log.md` — any open decisions that affect Phase 11?
- [ ] Check `docs/engineering/technical-debt.md` — any high-priority debt that should be addressed?
