# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/informatico-madrid/bmad-gherkin-tdd/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/informatico-madrid/bmad-gherkin-tdd/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/informatico-madrid/bmad-gherkin-tdd/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/informatico-madrid/bmad-gherkin-tdd/releases/tag/v0.1.0
