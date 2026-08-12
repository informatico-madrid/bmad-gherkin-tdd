<div align="center">

# BMAD Gherkin TDD

**Contract-first TDD methodology for BMAD projects** — signed Gherkin dev-contracts, a
strict RED → GREEN → CLEAN → REFACTOR coordinator with a durable per-scenario bitácora,
and plug-in integration with `bmad-loop`.

[![CI](https://github.com/informatico-madrid/bmad-gherkin-tdd/actions/workflows/ci.yml/badge.svg)](https://github.com/informatico-madrid/bmad-gherkin-tdd/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](#requirements)

</div>

---

## What it is

A BMAD module that makes TDD mechanical instead of aspirational. When a BMAD project
installs it, every story is driven through:

- **Signed Gherkin dev-contracts** — `gherkin-author` distils a story's Acceptance
  Criteria into `tests/contracts/<story-key>.feature` with stable `@s1..@sn` scenarios.
  The contract is the *canonical input* for every RED phase — the agent transcribes the
  scenario text, it never paraphrases the story file.
- **A strict TDD coordinator** — `bmad-tdd-coordinator` classifies each `@s`
  (`development | verification_preexisting | ambiguous`) and drives
  RED → GREEN → CLEAN → REFACTOR per scenario, with a durable four-phase bitácora.
- **Four phase skills** — `tdd-red`, `tdd-green`, `tdd-clean`, `tdd-refactor`
  (cleaner-gate + coverage in CLEAN, mutation killing + mutant register in REFACTOR).
- **Mechanical enforcement** — `hooks/tdd_cycle_gate.py` forces the order and timing of
  each cycle: a test must fail in RED before production can be touched, CLEAN must run
  before REFACTOR, and a development RED that *passes* trips a hard `RED_VIOLATION`
  block instead of silently continuing.
- **bmad-loop integration** — the dev adapter profile routes `bmad-loop run` through
  `bmad-dev-auto`, which owns the outer Verify → Review → closure
  (`## Auto Run Result`, `followup_review_recommended`, `status: done`, completion
  marker). The coordinator is implementation-only and never closes the story itself.

## What it is NOT

This module does **not** contain business rules, pipeline architecture, product mission,
or stack-specific gates from any single project. Test, mutation and cleaner commands are
**configurable per project** via the `_bmad/custom/` override layer — the module ships
generic defaults (`uv run pytest`, `make mutation-check`, `uv run mutmut run`) that a
project overrides.

## Requirements

- Python 3.11+ (for the installer CLI and the customization resolver).
- A BMAD project (the `bmm` module) and, for autonomous loops, `bmad-loop`.
- A coding CLI whose skill tree this module installs into (OpenCode `.agents/skills`,
  Claude `.claude/skills`).

### Optional quality-gate sibling

`bmad-gherkin-tdd` does **not** install
[`harness-quality-gate`](https://github.com/informatico-madrid/harness-quality-gate) and
does not declare it as a Python dependency. The module is usable on its own: its CLEAN
phase ships a self-contained structural checker, and test, mutation and cleaner commands
are supplied through project overrides.

Projects that need the full polyglot quality and security harness may install
`harness-quality-gate` separately and point their `_bmad/custom/*.toml` commands and
context files at that sibling checkout. This separation keeps the methodology module
portable while allowing projects such as Rompehielos to compose both tools.

## Install

### 1. Install the module package

```bash
# From GitHub
git clone https://github.com/informatico-madrid/bmad-gherkin-tdd.git
uv tool install ./bmad-gherkin-tdd
```

### 2. Install the module into your project

```bash
cd /path/to/your/bmad-project
bmad-gherkin-tdd install --project .
# Claude projects:
bmad-gherkin-tdd install --project . --claude
```

`install` is idempotent: it copies the skills, resolver, docs, hook, OpenCode assets,
bmad-loop profiles and override templates, then registers the module with the official
BMAD merge scripts (config.yaml section + `modules` list + `_bmad/_config/bmad-help.csv`). Use
`bmad-gherkin-tdd upgrade` to refresh bundled copies, `bmad-gherkin-tdd uninstall` to
remove it (user-modified files are preserved), and `bmad-gherkin-tdd status` to inspect.

### 3. Wire bmad-loop (optional but recommended)

If you run autonomous loops, the installer drops the dev profiles into
`.bmad-loop/profiles/`. Point the dev adapter at the `opencode-http` profile in
`.bmad-loop/policy.toml`:

```toml
[adapter]
name = "opencode-http"   # routes dev through bmad-dev-auto → TDD coordinator

[adapter.dev]
model = "deepseek/deepseek-v4-flash"   # whatever your project uses
```

The mechanical gate (`hooks/tdd_cycle_gate.py`) can be wired as a pre-tool hook of your
coding CLI; it activates only while a story is `in-progress` (or in `BMAD_LOOP_MODE=1`).

## How it works

```
Story (spec) ──▶ gherkin-author ──▶ tests/contracts/<story>.feature   (# Status: APPROVED)
                                          │  (canonical input, @s1..@sn)
                                          ▼
bmad-loop ──▶ bmad-dev-auto ──▶ bmad-tdd-coordinator
                                   ├─ CLASSIFY each @s: development | verification_preexisting | ambiguous
                                   ├─ development: RED → GREEN → CLEAN → REFACTOR  (per @s, bitácora row each)
                                   ├─ verification_preexisting: GREEN(confirm) → CLEAN → REFACTOR (if modified)
                                   ├─ ambiguous: STOP + evidence gap
                                   └─ RELEASE: mutation gate + test gate (+ project gates) → report evidence
                                                      │
                                                      ▼
                                bmad-dev-auto: Verify → Review → Auto Run Result → status: done → marker
```

Two independent layers keep the methodology honest:

1. **The skills** tell the agent *what* to do.
2. **The gate** (`hooks/tdd_cycle_gate.py`) mechanically enforces *when* it may do it —
   bitácora tokens must appear in the right phase, production edits are blocked until a
   failing test is observed, and RED violations stop the cycle.

## Configuration

Module variables come from `setup/assets/module.yaml`; the installer writes them into
`_bmad/config.yaml`:

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `contracts_dir` | `{project-root}/tests/contracts` | where `.feature` dev-contracts live |

Each skill reads a 3-layer customization stack via `scripts/resolve_customization.py`:
skill-default `customize.toml` → project `_bmad/custom/<skill>.toml` → personal
`_bmad/custom/<skill>.user.toml`. That is where a project supplies its real commands,
paths, mission files and product rules:

| Skill | Key | Default |
| ----- | --- | ------- |
| `bmad-tdd-coordinator` | `test_cmd` | `uv run pytest` |
| `bmad-tdd-coordinator` | `mutation_cmd` | `make mutation-check` |
| `bmad-tdd-coordinator` | `msi_minimum` | `85` |
| `bmad-tdd-coordinator` | `verification_preexisting_threshold` | `100` |
| `tdd-clean` | `cleaner_cmd` | `uv run python _bmad/gherkin-tdd/scripts/cleaner_gate.py` |
| `tdd-red` / `tdd-green` / `tdd-refactor` | `test_cmd` | `uv run pytest` |

## Layout

```
bmad_gherkin_tdd/             installer package (CLI + installer + payload staging)
skills/                       the six methodology skills (gherkin-author, coordinator, 4 phases)
setup/                        official BMAD installer surface (module.yaml, merge scripts, setup skill)
hooks/tdd_cycle_gate.py       mechanical RED/GREEN/CLEAN/REFACTOR timing gate (env-parameterized)
scripts/resolve_customization.py  # 3-layer TOML customization resolver
templates/custom/bmad-dev-auto.toml        # routes bmad-dev-auto through the coordinator
templates/custom/bmad-tdd-coordinator.toml # TDD coordination routine + release gates
bmad-loop/profiles/*.toml     bmad-loop adapter profiles (dev → bmad-dev-auto → coordinator)
opencode/agents/opencode.json.template  # tdd-*-ornith subagent definitions
.opencode/plugins/tdd-cycle-gate.js     # installed project plugin (auto-discovered)
scripts/{cleaner_gate,principles,scan_mutation_sites}.py # self-contained CLEAN toolchain
docs/contract-rules.md        binding Gherkin contract rules
tests/                        regression tests for the gate, resolver, coordinator, installer
```

## Development

```bash
uv sync --extra dev
uv run pytest         # full suite
uv run ruff check .   # lint
uv run ruff format .  # format
uv build              # sdist + wheel (verifies the payload stages into the wheel)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

## Influences

The separation between behavior-preserving CLEAN work and later mutation hardening was
inspired by the role pipeline described by Robert C. Martin's
[`unclebob/swarm-forge`](https://github.com/unclebob/swarm-forge). This project is an
independent implementation for BMAD: it adds signed per-scenario contracts, a durable TDD
bitácora, configurable MSI enforcement and a mechanical cycle gate. It is not affiliated
with or endorsed by SwarmForge.

## Troubleshooting

- **`uv run mutmut` fails with `ModuleNotFoundError`** — run it via `uv run` (the venv
  has the project deps); the system Python is not the target environment.
- **The run pauses with `spec status is ''`** — the coordinator (or a custom flow) wrote
  an unrecognized status. The coordinator must end its attempt by returning evidence to
  `bmad-dev-auto`; the *outer* flow writes `status: done` + the completion marker.
- **A test passes during RED** — that is a protocol violation. The gate blocks further
  tools (`RED_VIOLATION`); recover with `python3 hooks/tdd_cycle_gate.py reset` and
  re-classify the scenario (it may be `verification_preexisting`).
- **Contract is DRAFT / not APPROVED** — interactive: run `/gherkin-author` for human
  signature. In `bmad-loop` mode the coordinator auto-generates and auto-approves
  (`Approved-by: coordinator-auto`).

## Security

See [SECURITY.md](SECURITY.md) for the supported-versions policy and how to report a
vulnerability. The gate fails closed in loop mode and fails open outside it; never weaken
either behavior.

## License

[MIT](LICENSE)
