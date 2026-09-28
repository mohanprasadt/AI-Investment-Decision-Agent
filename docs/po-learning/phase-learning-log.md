# Phase Learning Log

> **Purpose:** Capture what was learned in each phase — not what was built, but what the PO now knows that they didn't before  
> **Format:** Per-phase reflection — insight, evidence, implication

---

## Phase 9.9b — EPS/FCF Period Alignment

### What was learned

**The gap between EPS and FCF can be an artifact of mismatched calculation windows, not a real business gap.**

Before Phase 9.9b, the system averaged EPS over years A–C and FCF over years B–D. The resulting "gap" was partly methodological — not all of it reflected real differences between earnings and cash generation.

**Evidence:** Once the common-window fix was applied, the ITC.NS FCF/EPS gap changed materially. The corrected numbers (EPS ₹16.05, FCF ₹12.04 on the same FY2024–FY2026 window) are meaningfully different from the numbers produced before the fix.

**Implication:** Never compare normalised metrics unless you verify they use the same calculation window. This applies in the system and in any external financial analysis you do.

---

### Continuing-operations NI is not the same as net income

ITC.NS FY2025 reported:
- Total net income: ₹347.47B
- Continuing-operations net income: ₹197.31B
- Difference: ₹150.16B one-time demerger gain

Using total NI for EPS normalisation would have produced an EPS ~76% higher than the correct figure. A recommendation based on that inflated EPS would have been systematically too optimistic.

**Implication:** When reading financial reports, always check whether headline "net income" includes discontinued operations or one-time items. The operating business's earnings power is what matters for long-term valuation.

---

## Phase 10.x — Yahoo Finance Reliability

### Rate limiting is structural, not occasional

During Phase 10.x, 4 diagnostic scripts were run and 5 detailed reports produced to understand Yahoo Finance's rate-limiting behaviour. The key finding: rate limiting is not a rare edge case — it is a predictable consequence of making too many requests in too short a time.

**Implication:** Any system that depends on yfinance for live data must be designed around this constraint. The design response in Phase 10.5 (fail-fast + pre-warm) is not a workaround — it is the correct architecture for this dependency.

---

### Failed fetches silently poisoning the cache

Before Phase 10.x, failed fetches were being cached. The next read of the cache returned the empty failed-fetch data as if it were valid. The analysis then proceeded with empty data and produced lower-quality (but not obviously wrong) output.

**Implication:** Data pipelines must distinguish between "data not available" and "data was available and has a known value." A null value that means "we didn't try" must be stored differently from a null that means "we tried and it's genuinely missing."

---

## Phase 10.5 — MVP Usability

### The "Force Refresh" bug: a silent failure

Force Refresh was wired in the UI but the flag was not propagating to `fetch_ticker()`. The UI showed a checkbox that appeared to work but did nothing. This was discovered during Phase 10.5 inspection.

**Lesson:** Silently broken features are more dangerous than features that visibly fail. A feature that appears to work but doesn't will erode trust when the user finally realises it's broken.

**Implication for PO:** When accepting a phase, verify that new features actually work, not just that they appear in the UI.

---

### The two-path error problem

The Phase 10.5 UX polish revealed that the friendly error message existed in one code path (the conversation turn response) but the raw error was simultaneously being set in `session.last_error` and reaching the UI. Two code paths, both producing output, only one of which was friendly.

**Lesson:** When specifying error-handling requirements, trace ALL paths by which an error string can reach the user. It is not sufficient to fix one path if another path carries the same raw string.

**Implication for PO:** "No technical strings in the UI" must be verified by looking at all places where error messages are rendered — not just the primary path.

---

## Phase 10.6 — Documentation

### You cannot manage what you cannot comprehend

At the start of Phase 10.6, the project had 10+ phases of work, scattered across a README, several phase design documents, and the source code itself. A new observer (or a returning PO after a break) would have significant difficulty understanding what the system does, why it was built this way, and what the known limitations are.

**Lesson:** Documentation is not optional for a product that will be maintained and extended. Without it, every phase starts from a higher cost of re-understanding.

**Implication:** The docs/ directory created in Phase 10.6 should be updated at the start and end of every future phase — not left to accumulate another debt over 10 more phases.

---

### RECONSTRUCTED vs IMPLEMENTED — honesty about gaps

Some early phases (1–8) could not be fully documented from direct evidence. The [RECONSTRUCTED] label was used to clearly signal this.

**Lesson:** Honest documentation that acknowledges its own gaps is more valuable than confident documentation that presents reconstruction as fact. The [RECONSTRUCTED] label is not a weakness in the docs — it is an integrity signal.

---

## Phase 7 — Decision Architecture (RECONSTRUCTED)

### Quality before price is a philosophical commitment, not a software choice

The sequential gate structure (quality → valuation → portfolio) reflects a deeply held investment principle: a company must first be a quality business before you consider whether its shares are cheap. This is not an arbitrary implementation choice — it is a statement about what kind of investor this product is for.

**Implication:** Any suggested change to gate ordering should be examined from this principle first, not from implementation convenience.

---

### Sunk-cost protection must be designed in, not hoped for

The decision to explicitly exclude average cost from Gate 4 was a design decision, not a default. Without this explicit exclusion, it would have been natural (and easy) to incorporate cost basis into the recommendation — "don't sell, you're down 20%."

**Lesson:** Design biases that are easy to fall into (like sunk-cost reasoning) must be explicitly prevented by the system, not trusted to user discipline alone.
