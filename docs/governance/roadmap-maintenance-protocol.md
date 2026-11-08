# Roadmap Maintenance Protocol

| Field | Value |
|---|---|
| Last reviewed | 2026-10-11 |
| Status | **Baseline v1.0, awaiting Product Owner confirmation** |
| Applies to | Every feature, defect fix or scope change made to the AI Investment Decision Agent from now on, by any developer or AI assistant |
| Authoritative record | [Product Feature Inventory and Roadmap](../product/product-feature-inventory-and-roadmap.md) |
| Diagrams | [Architecture Diagrams](../architecture/architecture-diagrams.md) |

**The roadmap is a mandatory living artifact.** It is updated after **each individual feature** is implemented and successfully validated, never only at the end of a phase and never after several features have accumulated.

---

## 1. The lifecycle (eight steps, in order)

| Step | Name | What must happen | Output |
|---|---|---|---|
| 1 | Before implementation | Locate the roadmap item. Confirm scope, dependencies, acceptance criteria and definition of done. If the item is missing, add it with status Not implemented. If adding it changes agreed scope or priorities, **get the Product Owner's approval first.** | Confirmed scope |
| 2 | Implement | Work only within the approved scope. Do not change decision thresholds, investment criteria, prompts that affect runtime decisions or business rules unless the item explicitly authorises it. Do not fix unrelated defects; record them as findings. | Code and tests |
| 3 | Validate | Run the item's acceptance tests **and the full test suite** (see section 3). Do end-to-end checks where feasible. | Test output |
| 4 | Assess | Decide, criterion by criterion, whether acceptance criteria passed. Record failures, limitations and blocked checks honestly. | Pass/fail list |
| 5 | Update roadmap | Immediately set implementation status, validation status, evidence, test results, completion notes and remaining limitations. Add a revision-history row. Recompute the summary counts (section 5). | Roadmap edit |
| 6 | Update architecture | If the feature changes component boundaries, data flow, decision processing, persistence or interfaces, update the affected diagram in the same work item. | Diagram edit |
| 7 | Review consistency | Check that the roadmap, architecture document, README, phase documentation and technical docs do not contradict each other (checklist in section 6). | Consistency note |
| 8 | Report | Give the Product Owner the **completion checkpoint** (section 4). | Checkpoint |

**Do not begin the next feature until the current feature's validation result and roadmap update have been reported.** If a batch of features is requested, the checkpoint applies to every feature individually.

Do not claim a document was updated unless it was actually modified and the resulting content was re-read to verify it.

---

## 2. Rules for incomplete or failed validation

| Situation | Required recording |
|---|---|
| All acceptance criteria pass and the full suite shows no new failures | Implementation: Implemented. Validation: Validated. Move to the Completed section. |
| Some criteria pass, others fail | Validation: Partially validated. List the outstanding criteria in the item. |
| Implementation finished but validation cannot be done (no network, no key, no environment) | Implemented / **Blocked**. Name the dependency that blocks it. |
| A defect is found | Add a finding to the findings register with priority and linked features. Update the affected feature's validation status (Failed if it breaks acceptance). |
| Scope changes | Document the change in the item and the revision history. **Never silently rewrite the original acceptance criteria.** Get approval if the change affects agreed scope or priorities. |
| Tests pass but only on mocks or stored data | State this explicitly in the evidence. Do not describe it as a live end-to-end validation. |

Never mark a feature Validated merely because the implementation runs, because a developer report says so, or because the feature's **own** tests pass while other tests fail.

---

## 3. Validation standard

1. **Run the full suite**, not only the feature's test file. *Reason: the Phase 11B work reported 58 and then 68 passing tests while 56 tests elsewhere in the suite had regressed (FND-1, FND-2).* This full-suite requirement is the one addition this protocol makes beyond the original instruction; the Product Owner may amend it.
2. Compare results with the **last accepted baseline** (currently committed HEAD: 1,223 passed, 5 failed, 1 skipped, 3 collection errors). Any new failure blocks Validated status.
3. The known pre-existing failures are the 5 network-dependent tests in `tests/test_phase93b.py` and the 3 collection errors from helpers named `test()`. They must be listed, not ignored, until fixed (F14.2, F14.3).
4. **Quote counts from the pytest output.** Never type a count from memory. Paste the final summary line into the evidence.
5. Suggested command (from the project root, ideally in a virtual environment):
   ```
   python -m pytest tests -q -p no:cacheprovider
   ```
6. Distinguish what was **verified** from what could not be verified (for example no network, no API key, UI not launched).
7. Acceptance for behaviour that depends on the LLM or live data needs a live run by someone with network access and a key; until then the item is at most Partially validated or Blocked.
8. Do not trigger expensive external research, change production data, or make consequential changes merely to complete validation.

---

## 4. Mandatory completion checkpoint

Report the following **for each feature**, before starting the next:

```
Checkpoint: <Feature ID> <name>
Acceptance criteria passed: <list>
Acceptance criteria failed:  <list or "none">
Tests executed and results: <command and pasted pytest summary line; baseline comparison>
Known limitations: <list or "none">
Roadmap changes made: <sections and fields edited, new revision row>
Architecture/documentation changes: <files and what changed, or "none needed" with reason>
Ready for Product Owner review: <yes / no, and why>
```

---

## 5. Keeping the summary counts correct

The summary counts in the roadmap count **features (rows of the inventory), not test cases**. After every status change:

1. Edit the feature's row in section 7 of the roadmap, which is the source of the counts.
2. Move or update its entry in section 6 (roadmap by section). Completed features are **never deleted**.
3. Recount. The script below reads section 7 and prints the totals to paste into section 2:

```python
# Recount roadmap features from section 7 of the roadmap (first table of each area).
import re, sys, collections
IMPL = {"Implemented", "Partially implemented", "Not implemented", "Requires investigation", "Retired/superseded"}
VAL = {"Validated", "Partially validated", "Not validated", "Blocked", "Failed"}
impl, val, ids = collections.Counter(), collections.Counter(), []
sec7 = open(sys.argv[1], encoding="utf-8").read().split("\n## 7. Full feature inventory")[1].split("\n## 8. Unresolved")[0]
for line in sec7.splitlines():
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) == 6 and re.match(r"F\d+\.\d+$", cells[0]) and cells[3] in IMPL and cells[4] in VAL:
        ids.append(cells[0]); impl[cells[3]] += 1; val[cells[4]] += 1
print(len(ids), "features"); print(dict(impl)); print(dict(val))
```

Run it as `python count_roadmap.py docs/product/product-feature-inventory-and-roadmap.md` after saving the snippet outside the repo (or anywhere convenient). Features that are not implemented count under "Not validated".

---

## 6. Consistency checklist (step 7)

Tick each line or record why it does not apply.

| Check | Where to look |
|---|---|
| Roadmap status of the feature matches the code and the latest test run | roadmap sections 6 and 7 |
| Summary counts recomputed | roadmap section 2 |
| Architecture diagrams still match module boundaries and flow | `docs/architecture/architecture-diagrams.md` |
| Test totals quoted anywhere equal the latest pytest output | `docs/README.md`, `docs/engineering/test-status.md`, `docs/product/current-state.md` |
| Gate 5 and decision-rule descriptions agree with code | `docs/logic/decision-gates.md`, `docs/logic/investment-decision-flow.md`, `README.md` |
| Phase history does not contradict the roadmap | `docs/product/roadmap.md` |
| No document copies the roadmap's status tables (single source) | all docs |
| Findings register updated for defects found or closed | roadmap section 4 |

---

## 7. Roles and approvals

| Action | Who decides |
|---|---|
| Add or reprioritise a roadmap item that changes agreed scope | Product Owner approval required |
| Change a decision threshold, investment criterion, valuation rule or runtime prompt | Product Owner approval required, recorded in `docs/governance/decision-log.md` |
| Resolve a product decision (PD-n) | Product Owner |
| Create a Git commit, branch or push | Only when the Product Owner explicitly authorises it |
| Reset, clean or overwrite unrelated or uncommitted files | Never, without explicit authorisation |

---

## 8. Identifiers and conventions

- **Feature IDs** `F<area>.<n>` are permanent. A retired feature keeps its ID and its row with status Retired/superseded. New features take the next free number in their area.
- **Findings** `FND-n`, **product decisions** `PD-n`, **milestones** `M0` to `M6`. Never reuse an ID.
- Priorities P0 to P3 are defined in the roadmap. Do not invent dates or effort estimates without evidence.
- One authoritative status source: the roadmap. Other documents link to it and do not restate counts.
- Update the "Last reviewed" date and revision history in every document you edit.

---

## 9. What a completed update looks like

An example of the minimum record after finishing a feature:

| Field | Example |
|---|---|
| Feature | F10.3 Follow-up answers from stored assessment |
| Status change | Implemented / Failed to Implemented / Validated; section P to C |
| Evidence | "Full suite: <pasted pytest summary>. 56 previously failing tests pass; baseline comparison attached." |
| Limitations | "Live UI check not performed (no network)." |
| Docs updated | Roadmap sections 2, 4, 6, 7; revision row; `test-status.md` totals |
| Next | "Not started: F9.4 pending Product Owner go-ahead." |

---

## Revision history

| Date | Change |
|---|---|
| 2026-10-11 | Initial protocol created during discovery review (adds the full-suite validation requirement; subject to Product Owner confirmation) |
