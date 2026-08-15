# Moat Analysis Research Template

## Purpose
Assess whether this company has a durable competitive advantage — and if so, what kind, how strong, and for how long.

## Critical Design Rules

1. **No conclusion without evidence.** Every moat claim must have at least one verifiable evidence item.
2. **Brand recognition alone is NOT a moat.** Brand must demonstrate pricing power, customer retention, or switching costs to qualify.
3. **ROIC supports but does not prove a moat.** High ROIC can indicate a moat exists, but you must identify the mechanism.
4. **Distinguish current vs. emerging vs. weakening.** A moat that is eroding is more dangerous than no moat at all.
5. **Threats must be considered.** A moat with no identified threats is a research gap, not a clean result.

## Research Prompt

**Ticker:** `{ticker}`
**ROIC (current):** `{roic_current}`
**ROIC (5yr avg):** `{roic_5yr_avg}`
**ROIC context note:** `{roic_moat_note}`

---

### Step 1 — Moat source investigation

Investigate each of the following moat source types. For each, either confirm absence or build the Claim → Evidence → Durability → Threats → Conclusion chain.

**Moat source types to investigate:**
- `network_effects` — value increases with more users/participants
- `switching_costs` — economic, technical, or psychological cost to leave
- `cost_advantage` — structurally lower costs than competitors (not just operational efficiency)
- `scale` — unit economics that improve with scale (purchasing power, fixed cost spreading)
- `brand` — pricing premium AND retention AND switching costs (all three required to qualify)
- `intellectual_property` — patents, proprietary technology, trade secrets
- `regulatory_barriers` — licenses, regulatory approvals, geographic restrictions
- `efficient_scale` — market too small for a second competitor to enter profitably
- `ecosystem` — platform/ecosystem lock-in
- `distribution_advantage` — preferential or exclusive access to distribution
- `data_advantage` — proprietary data that improves products in a way competitors cannot replicate

**For each investigated source, state:**

```
Moat Type: [name]
Claim: [one-sentence description of the claimed advantage]
Evidence: [list facts with source and tier]
Durability: [HIGH / MEDIUM / LOW] — [reasoning]
Threats: [what could erode this advantage]
Status: [CURRENT / EMERGING / WEAKENING / ABSENT]
Strength: [NONE / WEAK / MODERATE / STRONG / EXCEPTIONAL]
Conclusion: [one sentence]
```

---

### Step 2 — Overall moat assessment

Based on all sources investigated:

- **Overall strength:** [NONE / WEAK / MODERATE / STRONG / EXCEPTIONAL]
- **Overall durability:** [LOW / MEDIUM / HIGH]
- **Trajectory:** [STRENGTHENING / STABLE / WEAKENING / INSUFFICIENT_DATA]
- **Active sources:** [list the sources with CURRENT or EMERGING status]
- **Summary:** [2–3 sentence synthesis]

---

### Step 3 — ROIC consistency check

- Does the ROIC profile support the moat thesis?
- If ROIC is below preferred threshold (10%+), does this challenge the moat claim?
- If there is a divergence (claimed strong moat + weak ROIC), explain why.

---

### Step 4 — Current vs. emerging moats

- Are any identified advantages still building? (Emerging = possible moat but not yet proven)
- Are any established moats showing signs of weakening?

State this explicitly: "X is a current moat, Y is an emerging moat, Z was a moat but is weakening."

---

### Evidence quality requirements for moat claims

- **Tier 1 preferred** for any claim rated STRONG or EXCEPTIONAL
- At minimum **Tier 2** for MODERATE claims
- Moat claims with only Tier 3 evidence must be flagged as low-confidence
- If evidence is not available, classify as ABSENT or INSUFFICIENT_DATA — do not speculate

---

### What NOT to do

- Do NOT claim a moat based on market share alone (market share can reflect luck, not moat)
- Do NOT claim a brand moat unless pricing power, retention, AND switching costs are all evidenced
- Do NOT use ROIC as the sole basis for a moat claim
- Do NOT assess valuation here
- Do NOT make investment recommendations
