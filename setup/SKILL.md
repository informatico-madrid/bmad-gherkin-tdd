---
name: 'bmad-gherkin-tdd-setup'
description: Sets up the BMAD Gherkin TDD module in a project. Use when the user requests to 'install bmad-gherkin-tdd module', 'configure BMAD Gherkin TDD', or 'setup BMAD Gherkin TDD'.
---

# Module Setup

## Overview

Installs, configures, **and upgrades** the BMAD Gherkin TDD module in a project. This
module adds a contract-first TDD development methodology: signed Gherkin dev-contracts,
a RED→GREEN→CLEAN→REFACTOR coordinator with per-scenario bitácora, and integration with
bmad-loop. Setup does two jobs — (1) register module config + help entries (using the
same merge scripts the official BMAD installer uses), and (2) install the module skills
into the project's skill tree and wire the `bmad-dev-auto` handoff to the coordinator.

The same skill handles both first-time setup and **upgrades**. A plain re-run on an
already-installed project is treated as an upgrade.

Module identity (name, code, version) comes from `./assets/module.yaml`. Collects user
preferences and writes them to three files:

- **`{project-root}/_bmad/config.yaml`** — shared project config: core settings at root
  plus a section per module with metadata and module-specific values.
- **`{project-root}/_bmad/config.user.yaml`** — personal settings intended to be
  gitignored.
- **`{project-root}/_bmad/module-help.csv`** — registers module capabilities for the
  help system.

Both config scripts use an anti-zombie pattern — existing entries for this module are
removed before writing fresh ones, so stale values never persist.

`{project-root}` is a **literal token** in config _values_ (the data written into the
files above) — never substitute it there. This does **not** apply to the filesystem path
_arguments_ passed to the scripts below: those are real paths, so you **must** resolve
`{project-root}` to the actual project root before running.

## On Activation

1. Read `./assets/module.yaml` for module metadata and variable definitions (the `code`
   field is the module identifier).
2. Check if `{project-root}/_bmad/config.yaml` exists — if a section matching the
   module's code is already present, inform the user this is an update.
3. **Decide fresh-install vs upgrade.** Treat it as an **upgrade** when **any** of these hold:
   - The user asked for one in their arguments — `upgrade`, `update`, or similar.
   - `{project-root}/_bmad/config.yaml` already has a `gherkin-tdd` section.
   - The `gherkin-author` or `bmad-tdd-coordinator` skill already exists in the target
     skill tree.
   Otherwise it is a **fresh install**. State the decision to the user before proceeding.

If the user provides arguments (e.g. `accept all defaults`, `--headless`, `upgrade`, or
inline values), map any provided values to config keys, use defaults for the rest, and
skip interactive prompting.

## Collect Configuration

Ask the user for values. Show defaults in brackets. Present all values together so the
user can respond once with only the values they want to change.

**Default priority** (highest wins): existing new config values > `./assets/module.yaml`
defaults.

**Module config**: Read each variable in `./assets/module.yaml` that has a `prompt`
field. Ask using that prompt with its default value.

## Write Files

Write a temp JSON file with the collected answers structured as `{"core": {...},
"module": {...}}` (omit `core` if it already exists). Values inside this JSON keep the
literal `{project-root}` token. Then run both scripts — they can run in parallel since
they write to different files.

In the commands below, replace `{project-root}` in every path argument with the actual
project root before running — these are filesystem paths, not config values.

```bash
python3 ./scripts/merge-config.py --config-path "{project-root}/_bmad/config.yaml" --user-config-path "{project-root}/_bmad/config.user.yaml" --module-yaml ./assets/module.yaml --answers {temp-file} --legacy-dir "{project-root}/_bmad"
python3 ./scripts/merge-help-csv.py --target "{project-root}/_bmad/module-help.csv" --source ./assets/module-help.csv --legacy-dir "{project-root}/_bmad" --module-code gherkin-tdd
```

Both scripts output JSON to stdout with results. If either exits non-zero, surface the
error and stop.

Run `./scripts/merge-config.py --help` or `./scripts/merge-help-csv.py --help` for full usage.

## Create Output Directories

After writing config, create any output directories that were configured (resolve the
`{project-root}` token to the actual project root and `mkdir -p` each path).

## Install Skills

The module ships these skills in the module's `skills/` directory:

- `gherkin-author` — distils ACs into signed `.feature` contracts.
- `bmad-tdd-coordinator` — orchestrates RED→GREEN→CLEAN→REFACTOR per @s.
- `tdd-red`, `tdd-green`, `tdd-clean`, `tdd-refactor` — the four TDD phase skills.

Copy each skill directory into the project's skill tree for the target CLI:

```text
{project-root}/.agents/skills/<skill-name>/     (opencode / codex / gemini / copilot)
{project-root}/.claude/skills/<skill-name>/     (claude)
```

On a fresh install, do NOT overwrite existing skill dirs (preserve any project-local
customization); on an upgrade, refresh the bundled copies but **never** touch
`{project-root}/_bmad/custom/<skill-name>.toml` (that is the project's own override layer).

Also install the `scripts/resolve_customization.py` resolver into
`{project-root}/_bmad/scripts/` (idempotent — overwrite with the bundled copy, it is the
canonical resolver).

## Wire the bmad-dev-auto Handoff

If the project uses bmad-dev-auto (the unattended dev primitive that bmad-loop drives),
install the override that routes implementation through the TDD coordinator. Write (or
merge into) `{project-root}/_bmad/custom/bmad-dev-auto.toml`:

- Set `[workflow] implementation_handoff` to invoke the `bmad-tdd-coordinator` skill
  synchronously (`dev this story {spec_file}`).
- Add the `activation_steps_append` gates: PILOT GATE, TDD DELEGATION GATE,
  TDD SUBAGENT TYPES GATE, VERIFICATION_PREEXISTING GATE, CLOSURE GATE.
- Add `persistent_facts` pointing at the module's docs.

The canonical override template ships in the module at `templates/custom/bmad-dev-auto.toml`.
**Do NOT overwrite an existing `_bmad/custom/bmad-dev-auto.toml`** — merge the module's
gates into the existing file if one is present, preserving the project's own
mission/paths.

## Wire the bmad-loop Adapter Profile

If the project uses bmad-loop (autonomous loop), install the dev adapter profile so
`bmad-loop run` drives the TDD coordinator instead of a plain subagent:

```toml
# {project-root}/.bmad-loop/profiles/opencode-http.toml
name = "opencode-http"
binary = "opencode"
prompt_template = "Use the bmad-tdd-coordinator skill now: dev this story {args}"
usage_parser = "none"
skill_tree = ".agents/skills"
```

Then point `[adapter.dev]` at that profile in `{project-root}/.bmad-loop/policy.toml`.
The template ships in `bmad-loop/profiles/opencode-http.toml`. Only write the profile
if it does not already exist; merging preserves any project-specific profile.

## Confirm

Use the script JSON output to display what was written — config values set, help entries
added, fresh install vs upgrade. Then report which skills were installed, whether the
bmad-dev-auto handoff was wired, and whether the bmad-loop profile was set.

Display the `module_greeting` from `./assets/module.yaml` to the user.

## Outcome

Once the user's `user_name` and `communication_language` are known, use them
consistently for the remainder of the session.
