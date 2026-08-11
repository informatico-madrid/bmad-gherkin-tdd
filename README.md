# BMAD Gherkin TDD

Contract-first TDD development methodology for BMAD projects, extracted from the
Rompehielos custom harness into a standalone, installable BMAD module.

**What you get in any BMAD project that installs this module:**

- **Signed Gherkin dev-contracts** — `gherkin-author` distils a story's Acceptance
  Criteria into `tests/contracts/<story-key>.feature` with stable `@s1..@sn`
  scenarios, walked through human (or auto, in loop mode) signature before any
  production code.
- **A strict TDD coordinator** — `bmad-tdd-coordinator` classifies each @s
  (`development` | `verification_preexisting` | `ambiguous`) and drives
  RED → GREEN → CLEAN → REFACTOR per scenario, with a durable per-scenario bitácora.
- **Four phase skills** — `tdd-red`, `tdd-green`, `tdd-clean`, `tdd-refactor`
  (mutation killing + mutant register).
- **Mechanical enforcement** — `hooks/tdd_cycle_gate.py` forces the order and
  timing of each Red→Green→Refactor cycle (the bitácora can't be back-filled).
- **bmad-loop integration** — dev adapter profile routes `bmad-loop run` through
  the TDD coordinator; the `bmad-dev-auto` handoff template wires the same.

## What it is NOT

This module does **not** contain business rules, pipeline architecture, product
mission, or stack-specific gates from any single project. Commands (test, mutation,
cleaner) are **configurable per project** via the `_bmad/custom/` override layer —
the module ships generic defaults (`uv run pytest`, `make mutation-check`,
`uv run mutmut run`) that a project overrides.

## Install

```bash
# 1. Clone the module (or vendor the skills/ dir).
git clone https://github.com/your-org/bmad-gherkin-tdd.git

# 2. Install into the project's skill tree:
#    - skills/gherkin-author → {project}/.agents/skills/gherkin-author (or .claude/skills)
#    - skills/bmad-tdd-coordinator → {project}/.agents/skills/bmad-tdd-coordinator
#    - skills/tdd-red|green|clean|refactor → {project}/.agents/skills/<name>
#    - scripts/resolve_customization.py → {project}/_bmad/scripts/

# 3. Register the module (official BMAD installer mechanism):
#    run the bmad-gherkin-tdd-setup skill, or directly:
python3 setup/scripts/merge-config.py \
  --config-path "{project}/_bmad/config.yaml" \
  --user-config-path "{project}/_bmad/config.user.yaml" \
  --module-yaml setup/assets/module.yaml \
  --answers {answers.json} --legacy-dir "{project}/_bmad"
python3 setup/scripts/merge-help-csv.py \
  --target "{project}/_bmad/module-help.csv" \
  --source setup/assets/module-help.csv \
  --legacy-dir "{project}/_bmad" --module-code gherkin-tdd
```

## Wire the TDD coordinator into your dev flow

1. **bmad-dev-auto** (if used): copy `templates/custom/bmad-dev-auto.toml` into
   `{project}/_bmad/custom/bmad-dev-auto.toml` and merge with any existing overrides.
   This routes every unattended implementation through the TDD coordinator.
2. **OpenCode subagents** (if you use the `task()` tool for phases): copy the four
   `tdd-*-ornith` definitions from `opencode/agents/opencode.json.template` into your
   `.opencode/opencode.json`, replacing the model placeholders.
3. **bmad-loop** (if you run autonomous loops): copy
   `bmad-loop/profiles/opencode-http.toml` into `{project}/.bmad-loop/profiles/` and
   point `[adapter.dev]` at it in `{project}/.bmad-loop/policy.toml`.
4. **Mechanical gate** (optional but recommended): install `hooks/tdd_cycle_gate.py`
   as a pre-tool hook keyed to the edit/bash tools of your coding CLI, and configure
   `BMAD_TDD_PROD_PREFIX` / `BMAD_TDD_TEST_PREFIX` / `BMAD_TDD_SPRINT_STATUS` for
   your layout.

## Project override layer

Each skill reads `{project-root}/_bmad/custom/<skill-name>.toml` (team) and
`.user.toml` (personal) on top of its bundled `customize.toml` defaults, via
`scripts/resolve_customization.py`. That is where a project supplies its real
commands, paths, mission files, and product rules.

## Layout

```
skills/                          # the six methodology skills (gherkin-author, coordinator, 4 phases)
setup/                           # official BMAD installer surface (module.yaml, merge scripts, setup skill)
hooks/tdd_cycle_gate.py          # mechanical RED/GREEN/REFACTOR timing gate (env-parameterized)
scripts/resolve_customization.py # 3-layer TOML customization resolver
templates/custom/bmad-dev-auto.toml        # routes bmad-dev-auto through the coordinator
templates/custom/bmad-tdd-coordinator.toml # the TDD coordination routine + release gates
bmad-loop/profiles/*.toml        # bmad-loop adapter profiles (dev → coordinator)
opencode/agents/opencode.json.template  # tdd-*-ornith subagent definitions
opencode/plugins/tdd-cycle-gate.js      # opencode tool-mapping + gate relay
docs/contract-rules.md           # binding Gherkin contract rules
tests/                           # regression tests for the gate, resolver, coordinator consistency
```
