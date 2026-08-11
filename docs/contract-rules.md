# Contract rules — Gherkin dev-contracts (non-negotiable)

These are the binding rules for the `.feature` contract files this module
enforces. Projects may ADD rules via `_bmad/custom/gherkin-author.toml` but may
not weaken these.

## Non-negotiables

1. **One `Scenario` per observable behaviour** — error paths included (invalid
   input, crash, empty/unparseable output, refusal paths).
2. **Every `Then` asserts something measurable** — an exit code, a message, a
   value, a recorded artifact. "The system works" is forbidden.
3. **Exactly one `When` per scenario** — two actions = two scenarios.
4. **No implementation details** — no function/class/variable names. Observable
   behaviour only.
5. **Tags `@s1..@sn` are stable identifiers** — the TDD bitácora and the Process
   Auditor cite them. Never renumber on edit; retire tags instead.
6. **Every AC covered by ≥1 scenario** — always present the AC → @s coverage map.
7. **PREGUNTA ABIERTA for anything not expressible** in Given/When/Then — refine
   the AC with the human; never paper over it.
8. **The contract is a spec artifact, NOT an executable BDD suite.** The `@s → test`
   map is produced later by dev-story's TDD bitácora.
9. **DISTINCT from Tier-A oracle `.feature`s** (Behat/Mink/Playwright, legacy
   equivalence). Never mix the two; never place oracle features in the contracts dir.

## Signature header (the dev-story gate greps this)

```gherkin
# Contract: <story-key>
# Status: DRAFT | APPROVED
# Approved-by: <name>            (only when APPROVED)
# Date: <YYYY-MM-DD>             (approval date)
# Source: <story file path>
# Retrofit: post-implementation  (retrofit mode only)
```

## Authoring for the local implementer

- **Few scenarios per story.** A long story forces context compaction, which
  erases product intent. >10 scenarios signals the STORY is too big — raise it.
- **Each `Then` is a command + expected output**, not a quality adjective.
  Prefer mechanical, greppable Thens.
- **Behaviour, still not implementation** — but observable enough that the RED
  phase writes a test by *transcribing* the Then, not by guessing.

## Project-specific product rules

The `gherkin-author` skill loads project product rules from
`_bmad/custom/gherkin-author.toml`. Common additions:

- Anti-coupling scenarios (a behaviour that could be faked by hardcoding
  project-specific specifics MUST get an explicit anti-coupling scenario with a
  mechanical `Then`).
- Product mission / fixture-vs-target rules (project-defined).
