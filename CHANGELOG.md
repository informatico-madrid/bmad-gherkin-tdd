# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Central coordinator gate-scope flags let polyglot projects keep the complete
  RED→GREEN→CLEAN→REFACTOR protocol while recording cleaner, coverage, or mutation
  as explicit N/A gates with auditable reasons when the stack lacks those tools.
- C4 deterministic RED-test advisor (`red_test_advisor.py`): a pure-stdlib AST
  analyzer that classifies RED-test assertion shapes (exact equality over a
  call-derived value, broad truthiness, count-only mocks, ...) and records
  agreement with the LLM mutant-hunting review. Advisory-only: it never
  executes test code, changes no hooks, and `strong` means strong assertion
  shape — the LLM review stays unconditional and solely authoritative. Shipped
  byte-identical in both consuming projects; installed by this module at
  `_bmad/gherkin-tdd/scripts/red_test_advisor.py` and wired through
  `{workflow.red_test_advisor_cmd}` plus the RED handoff contract (exact
  nodeids + failing pytest command).
- Coordinator workflow keys: `red_test_advisor_cmd` (default installed path)
  and `mutation_shadow_cmd` (empty = disabled; reserved for project-owned,
  measurement-only shadow mutation support).
- `bmad-dev-auto` override template ships a SCOPE SPLIT GATE: an oversized or
  multi-goal intent now HALTs with blocking condition `story split required`
  instead of continuing on a warning-only signal.
- The four TDD phase subagents in the OpenCode agent template deny the
  interactive `question` tool, so an unattended phase subagent fails fast
  instead of deadlocking on a prompt no human can answer.
- Full-scope mutation now runs ONCE at RELEASE, coordinator-owned (`{workflow.mutation_cmd}`,
  UNA vez tras el último `@s`, never delegated). `tdd-refactor` no longer runs or certifies
  mutation: it is behaviour-preserving structural refactor + confirm PASS; named-mutant
  inspection (`mutmut show <name>` / `mutmut run '<id>'`) remains the only mutation-related
  action outside RELEASE. The OpenCode subagent template denies full mutation commands in
  `permission.bash` for all four phase agents (a static mechanical guard in case the
  subagent session is not plugin-inherited), and the loop-mode gate denies full-scope
  mutation while a cycle is open.
- Tests: `test_tdd_mutation_scope.py` (deny mid-cycle / allow RELEASE / named inspection /
  path-scope semantics) and `test_agent_template_permissions` asserts the new denies.
- New `bmad-loop-coordinator` orchestration layer: a primary agent (in the OpenCode
  template) plus a matching skill it loads on bootstrap (installed via `installer.SKILL_NAMES`).
  The coordinator selects stories, launches and monitors `bmad-loop` runs with adaptive
  waits, intervenes on failures and reviews results; its interaction is gated on the
  project's `.bmad-loop/human-present` flag (unattended runs never block on a human
  prompt). README documents the agent, its skill, usage and configuration.

### Fixed
- The mechanical gate now observes a project-configured verification command and
  production/test prefixes using exact, non-composed command matching; the OpenCode
  bridge forwards the Bash exit code, so non-pytest runners such as `npm run verify`
  drive RED/GREEN reliably without accepting chained or unrelated commands.
- Gate now bridges subagent session isolation only when a matching `Task` has a
  successful, phase-specific `BMAD_TDD_PHASE_RESULT` response, so cycles routed
  through `task()` subagents (which do not inherit the plugin) no longer stall or
  advance from an unverified Task name.
- Gate now bridges subagent session isolation: a `Task` PostToolUse for a TDD
  phase agent advances the phase machine and records `skill_seen`, so cycles
  routed through `task()` subagents (which do not inherit the plugin) no longer
  stall.
- Full-mutation deny now also catches `python3 -m mutmut run` and bare
  `mutmut run`; the phase-subagent `permission.bash` denies cover arg-variant
  and `python*` spellings; loop-mode deny messages no longer suggest the
  disabled CLI `bypass`.
- Full-mutation detection is **clause-scoped**: a named-mutant inspection no
  longer masks a separate full-scope clause in the same command, while benign
  commands that merely mention `make mutation-check`/`mutmut run` (`git commit -m`,
  `grep`) are no longer false-denied; the `make` spell now tolerates leading flags
  (`-j8`, `-C dir`, `-f Makefile`, `--directory=`).
- The unattended `question`/`prompt` tool is now **mechanically denied** in loop
  mode without `human-present=yes` (opencode/plugins/tdd-cycle-gate.js) — the
  coordinator no longer relies on prompt prose to avoid the obs-21 deadlock.
- The `bmad-loop-coordinator` primary agent no longer grants `webfetch`/`websearch`
  (unused by its skill; removes a prompt-injection/context surface in unattended
  autonomous runs).
- `RED_VIOLATION` no longer false-triggers on a passing baseline pytest run
  before any RED test exists (`red_test_written` guard), and the gate's own
  `reset` CLI is allowed even in `RED_VIOLATION` so a violation is recoverable
  autonomously instead of deadlocking the run.

## [0.1.2] - 2026-08-12

### Fixed
- The OpenCode bridge now preserves interactive fail-open behavior while failing closed
  on gate crashes, signals and timeouts during autonomous `bmad-loop` runs.
- Installer transactions roll back newly written assets when registration fails.
- Reinstalls preserve user-modified skill ownership correctly, while exact bundled
  assets left by older interrupted installs can be adopted safely.
- Critical installer output paths reject symlink traversal before writing.
- `status` now reports missing and modified managed assets instead of trusting the
  manifest alone.
- CLEAN reports invalid Python as a structured JSON failure instead of emitting a
  traceback.

## [0.1.1] - 2026-08-12

### Documentation
- Clarified that `harness-quality-gate` is an optional sibling project, not an
  automatically installed runtime dependency. The bundled CLEAN toolchain remains
  self-contained; projects compose the full harness through their local overrides.
- Documented SwarmForge's conceptual influence on the CLEAN/hardening separation and
  clarified that this is an independent BMAD implementation.

## [0.1.0] - 2026-08-12

### Added
- Contract-first TDD methodology as an installable BMAD module.
- `gherkin-author` — distils story Acceptance Criteria into signed Gherkin dev-contracts
  (`tests/contracts/<story-key>.feature`) with stable `@s1..@sn` scenarios and an explicit
  signature-mode contract (interactive `human_required` vs autonomous-loop `loop_auto`).
- `bmad-tdd-coordinator` — orchestrates RED → GREEN → CLEAN → REFACTOR per scenario with
  a durable per-scenario bitácora and Pre-RED CLASSIFY gate
  (`development | verification_preexisting | ambiguous`).
- `tdd-red`, `tdd-green`, `tdd-clean`, `tdd-refactor` — the four phase skills.
- `hooks/tdd_cycle_gate.py` — mechanical enforcement of cycle order and timing, including
  the CLEAN phase and a `RED_VIOLATION` guard that blocks a development RED that passes.
- `bmad_gherkin_tdd` CLI — `install`, `upgrade`, `uninstall`, `status`; self-contained
  wheel (payload staged via `setup.py` build shim) + `MANIFEST.in`.
- bmad-loop integration: dev adapter profile routes through `bmad-dev-auto` (which owns
  Verify → Review → closure); `bmad-dev-auto` override template wires the coordinator.
- Official BMAD installer registration via `setup/scripts/merge-config.py` and
  `merge-help-csv.py` (config.yaml section, `modules` list, `_config/bmad-help.csv`).
- 137 regression tests (gate state machine, concurrency locks, symlink denial,
  coordinator consistency, installer, handoff).

### Fixed
- Coordinator no longer closes the story (`status: done` / `## Auto Run Result` /
  completion marker are owned by the outer `bmad-dev-auto` flow; the bmad-loop engine is
  the single-writer of `sprint-status.yaml`). Review now actually runs via
  `bmad-dev-auto` step-04 instead of being skipped.
- CLEAN is now a real gate phase: `tdd-refactor` cannot start before `tdd-clean` is seen
  and the CLEAN bitácora entry is written.
- `RED_VIOLATION`: a test that passes during RED no longer silently continues to `done`.
- bmad-loop dev profile no longer bypasses `bmad-dev-auto` by invoking the coordinator
  directly.

[Unreleased]: https://github.com/informatico-madrid/bmad-gherkin-tdd/compare/v0.1.3...HEAD
[0.1.2]: https://github.com/informatico-madrid/bmad-gherkin-tdd/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/informatico-madrid/bmad-gherkin-tdd/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/informatico-madrid/bmad-gherkin-tdd/releases/tag/v0.1.0
