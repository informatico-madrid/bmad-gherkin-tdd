# C1 + C4 Safe-Speed Cross-Repository Implementation Plan

**Status:** REVIEWED - no unresolved critical/high findings; human implementation go required  
**Date:** 2026-08-26  
**Decision owner:** Human project owner  
**Operational reference:** `/mnt/bunker_data/rompehielos`  
**Portable module:** `/mnt/bunker_data/bmad-gherkin-tdd`  
**Research source:** `_bmad-output/planning-artifacts/research/technical-tdd-en-la-era-del-desarrollo-autonomo-gu-2026-08-25/research.md`  
**Curated recommendations:** `_bmad-output/planning-artifacts/research/technical-tdd-en-la-era-del-desarrollo-autonomo-gu-2026-08-25/curas-bmad-gherkin-tdd.md`  
**Prerequisite plan:** `plans/p1-full-mutation-to-release.md`

## 1. Purpose

Implement two measurement-first improvements without weakening the TDD or
release contract:

1. **C1 - incremental mutation shadow:** characterize mutmut 3.7.0 on the real
   Rompehielos corpus and run incremental mutation only when a same-run,
   same-worktree full cache is demonstrably warm. Compare it with a fresh full;
   only the fresh full decides RELEASE.
2. **C4 - deterministic RED-test advisor:** add a conservative static assertion-
   shape classifier before the current LLM mutant-hunting review, record
   agreement, and leave the LLM review unconditional and authoritative.

The plan also measures whether a coordinator full and pre-commit full are bound
to the same candidate. It **does not skip the pre-commit full in this delivery**:
the current coordinator artifacts are writable by the same agent being gated and
therefore are not a trusted execution witness. Removing that duplicate requires
an engine/plugin-owned or cryptographically signed witness in a separately
reviewed amendment.

This is a control-plane program. Implement it directly with focused regression
tests; do not route it through product-story Gherkin/TDD ceremony. Normal product
stories retain `RED -> GREEN -> CLEAN -> REFACTOR -> RELEASE`.

## 2. Closed Decisions

| ID | Decision | Consequence |
|---|---|---|
| D-01 | Scope is C1 + C4. C2 and C3 are out. | No unrelated model-routing or test-generation work. |
| D-02 | Rompehielos is the operational reference; bmad-gherkin-tdd is the portable distillation. | Prove behavior on the real project, then package only reusable surfaces. |
| D-03 | Fresh full mutation remains coordinator-owned and authoritative in RELEASE. | Incremental output never closes RELEASE or authorizes commit. |
| D-04 | C1 uses the real Rompehielos corpus. | No synthetic mutmut project and no mutmut dependency in standalone. |
| D-05 | Rompehielos pins `mutmut==3.7.0`. | Characterize one exact release; no open-ended 3.7 range. |
| D-06 | C1 compares exact raw mutant ID/exit-code maps and full exported stats. | MSI-only equality is insufficient. |
| D-07 | Shadow runs only with proven warm-cache provenance and always before the fresh full. | First RELEASE in a worktree skips shadow; the full then seeds a possible later same-run sample. |
| D-08 | Candidate-bound reuse remains observation-only in this delivery. | Pre-commit validates hypothetical reuse, records `would_reuse`, then executes the live full regardless. |
| D-09 | A future skip requires a witness outside the model's writable artifact path. | Agent-authored JSON/digests cannot authorize omission of an execution gate. |
| D-10 | C4 is advisory for the entire delivery. | No hook changes for C4, no GREEN authorization, and no LLM bypass, including `strong`. |
| D-11 | C4 ships as two byte-identical pure-Python scripts and vector corpora. | No shared runtime package or speculative `gate_core`. |
| D-12 | C4 `strong` means strong assertion **shape**, not proof that the assertion covers the story's semantic subject. | The LLM remains responsible for subject/contract adequacy. |
| D-13 | `agent_bench/red/**` is out of scope. | It benchmarks RED agents; it is not a runtime TDD gate. |
| D-14 | Generated/installed copies are not source files. | Edit tracked canonical sources and test installation separately. |
| D-15 | Standalone release target is 0.1.4. | Update package, installer, tests, changelog, and wheel assertions together. |
| D-16 | No implementation starts until this v3 passes adversarial re-review and the human gives the implementation go. | Current task changes planning only. |

## 3. Non-Negotiable Invariants

1. Preserve `RED -> GREEN -> CLEAN -> REFACTOR` and an observed RED for every
   `development` scenario.
2. Preserve `verification_preexisting` and its candidate-bound evidence rules.
3. Run one fresh canonical `make mutation-check` in coordinator RELEASE and the
   existing live pre-commit full until a separately approved trusted-witness
   design exists.
4. Preserve `msi_minimum = 85`, `no_tests == 0`, the current per-file zero-
   survivor ratchet, and current treatment of documented survivors/timeouts.
5. Do not game MSI with exclusions, deleted negative tests, or
   `# pragma: no mutate`.
6. Preserve `mutants/mutmut-cicd-stats.json` as canonical exported stats and read
   every recursive `.meta` journal. Never use `mutmut results` as evidence.
7. Keep `persistent_gate_cache = false`. Caches and evidence do not cross run,
   story, or worktree boundaries.
8. A cold, missing, stale, corrupt, cross-run, cross-worktree, or ineligible cache
   skips the **shadow**, not the full.
9. Identical recognized survivors/timeouts on both C1 arms are valid parity;
   malformed or unrecognized exit codes are inconclusive. Existing full-gate
   policy remains unchanged.
10. C4 cannot alter hook state, `phase_agent_seen`, bitacora closure, GREEN
    dispatch, release status, or commit eligibility.
11. A C1/C4 advisory failure continues the authoritative full/LLM path.
12. Authority changes, threshold reductions, or broader scope require a human
    amendment.

## 4. Source Ownership And No-Touch Boundaries

### 4.1 Canonical sources

| Concern | bmad-gherkin-tdd | Rompehielos |
|---|---|---|
| Coordinator | `skills/bmad-tdd-coordinator/{SKILL.md,prompt.txt,customize.toml}` | `tools/skills/bmad-tdd-coordinator/{SKILL.md,prompt.txt}` + `_bmad/custom/bmad-tdd-coordinator.toml` |
| RED handoff | `skills/tdd-red/{SKILL.md,prompt.txt}` | `tools/skills/tdd-red/{SKILL.md,prompt.txt}` |
| C4 advisor | `scripts/red_test_advisor.py` | `scripts/red_test_advisor.py` |
| C4 vectors/tests | `tests/fixtures/red_test_advisor_vectors.json`, `tests/test_red_test_advisor.py` | `tools/bmad-harness/tests/fixtures/red_test_advisor_vectors.json`, `tools/bmad-harness/tests/test_red_test_advisor.py` |
| Hooks | `hooks/tdd_cycle_gate.py`, `opencode/plugins/tdd-cycle-gate.js` | `tools/bmad-harness/hooks/tdd_cycle_gate.py`, `tools/bmad-harness/opencode/plugins/tdd-cycle-gate.js` |
| Installer | `bmad_gherkin_tdd/installer.py`, `setup.py`, `pyproject.toml` | Not applicable |
| Mutation implementation | Portable command surface only | `Makefile`, `pyproject.toml`, `uv.lock`, `scripts/check_mutation.py`, `scripts/run_evidence.py`, project plugin |

### 4.2 Do not edit as source

- `/mnt/bunker_data/rompehielos/.agents/skills/**`
- `/mnt/bunker_data/rompehielos/.opencode/plugins/**`
- `/mnt/bunker_data/rompehielos/.bmad-loop/runs/**`
- `/mnt/bunker_data/rompehielos/mutants/**`
- `/mnt/bunker_data/bmad-gherkin-tdd/{build,dist}/**`
- `/mnt/bunker_data/bmad-gherkin-tdd/bmad_gherkin_tdd/payload/**`
- `/mnt/bunker_data/bmad-gherkin-tdd/agent_bench/red/**`
- Installed bmad-loop package/cache sources under the user home directory.

C4 changes no hook. The Rompehielos hooks have substantial legitimate custom
behavior and must never be replaced by standalone copies.

## 5. Verified Baseline And Corrected Premises

### 5.1 C1 baseline

- Rompehielos declares `mutmut>=3.5.0`; `uv.lock` resolves 3.6.0.
- `make mutation` runs mutmut without deleting `mutants/` and without exporting
  canonical stats.
- `make mutation-check` deletes `mutants/`, runs mutmut, exports stats, and runs
  `scripts/check_mutation.py`.
- Current aggregate pass is `no_tests == 0` and MSI >= the environment threshold,
  followed by the per-file zero-survivor ratchet. It does **not** require all
  project mutants to be killed.
- A recent canonical passing full contained approximately 85 survivors and three
  timeouts. Phase 0 records the exact run ID/counts because the corpus can drift.
  Therefore empty survivor/undetermined lists are not a valid manifest or
  comparator precondition.
- Current demonstrated non-survivor codes are `1`, `3`, and `37`; `0` is
  survived; other recognized statuses include timeout, no-tests, skipped,
  suspicious, interrupted, and segfault. Boolean/non-integer values are corrupt.
- `scripts/run_evidence.py` writes candidate-bound bounded output but does not
  preserve a complete raw map or journal manifest before the next command.
- `same_run_passing_evidence()` currently scans oldest-first and ignores current
  environment identity; it has no production consumer.
- `record_gate_activity()` is Phase 0 observational and hard-codes
  `would_reuse = false`.
- Fresh bmad-loop story worktrees have no gitignored `mutants/` cache. The first
  RELEASE shadow would be cold and is therefore skipped by this plan.

### 5.2 Mutmut 3.7 premises to verify, not assume

Primary-source review indicates 3.7.0 adds per-function hashes, cross-call
invalidation, config fingerprints, git detection for non-Python dependencies,
and `on_dependency_change`. The implementation must inspect the installed 3.7.0
source before using any key because:

- Default `on_dependency_change = "warn"` may retain stale results rather than
  rerun.
- Python test-content changes may not participate in source-function or non-
  Python git invalidation.
- Some result-affecting options may be outside the config fingerprint.
- A file outside `only_mutate` cannot demonstrate caller invalidation unless its
  caller/callee pair is actually represented in the mutated graph.

The experiment records those behaviors as `VALIDATED`, `REFUTED`, or
`INCONCLUSIVE`; it does not predeclare safe invalidation.

### 5.3 C4 baseline

- The coordinator performs an LLM `MUTANT-HUNTING REVIEW` after RED and before
  GREEN.
- No deterministic assertion-shape artifact or agreement record exists.
- RED handoff does not consistently return exact changed test paths/nodeids.
- Static text tests can prove instruction presence but not agent compliance;
  runtime compliance must be observed in pilot telemetry.

## 6. Target Design

## 6.1 C1 compatibility and journal contract

### 6.1.1 Pin and inspect mutmut 3.7.0

1. Change Rompehielos to `mutmut==3.7.0`.
2. Run `uv lock --upgrade-package mutmut`; allow only mutmut and dependency-
   closure changes attributable to the 3.7 requirement delta, and reject
   unrelated project upgrades.
3. Verify installed version and inspect its actual `configuration.py`, cache
   implementation, `status_by_exit_code`, stats exporter, function hashes,
   caller invalidation, watched-file rules, and default dependency action.
4. Persist those facts in the C1 characterization report with source hashes.
5. Run focused parser/gate tests, `make test-pr`, and a fresh
   `make mutation-check`.

If baseline tests, journals, stats, status semantics, or MSI regress without an
explained product change, mark the migration `REFUTED`, restore 3.6.0, and leave
C1 disabled. C4 may continue independently.

### 6.1.2 Centralize journal parsing

Add `scripts/mutation_journal.py` in Rompehielos and import it from
`scripts/check_mutation.py` and `scripts/run_evidence.py` rather than duplicating
exit-code parsing.

It must:

- Load every sorted recursive `.meta` file under an explicit journal root.
- Reject path escapes, symlinks, duplicate mutant IDs, missing/empty/non-dict
  `exit_code_by_key`, booleans, non-integer/non-null values, and unrecognized 3.7
  exit codes. Accept JSON `null` as the legitimate `not_checked` status.
- Preserve each raw `mutant_id -> exit_code` exactly.
- Classify using a frozen table derived from the inspected 3.7 source, including
  the observed last-wins handling of duplicate `-24` mapping.
- Expose separate predicates for demonstrated non-survivor, survivor, recognized
  non-kill, and corrupt/unrecognized data.
- Derive counts by raw exit code and by mutmut status for reconciliation with the
  complete exported stats JSON.
- Preserve `scripts/check_mutation.py` aggregate and zero-survivor behavior.

Tests must compare the frozen table with the installed 3.7 status table and use
a real copied 3.7 journal tree as a golden fixture. If mutmut changes the table,
the pin/update fails explicitly.

## 6.2 C1 mutation artifacts

Extend `scripts/run_evidence.py` additively; existing summary consumers and the
stdout-summary == disk-summary invariant remain unchanged.

For `--command-kind mutation-shadow|mutation-full`, write in this order:

```text
stdout.txt
stderr.txt
mutation-status-map.json
mutation-manifest.json
summary.json                    # written last; command rc still preserved
```

Every sidecar uses same-directory temporary write + `os.replace`. A partial set,
missing sidecar, or digest mismatch is typed infra/inconclusive. No file grants
release authority.

### 6.2.1 Status map schema v1

```json
{
  "schema_version": 1,
  "command_kind": "mutation-full",
  "candidate_id": "sha256:<complete-id>",
  "mutmut_version": "3.7.0",
  "entries": [
    {"mutant_id": "<stable-id>", "exit_code": 1, "status": "killed"}
  ],
  "counts_by_exit_code": {"1": 1},
  "counts_by_status": {"killed": 1},
  "journal_manifest": [
    {
      "path": "mutants/src/example.py.meta",
      "semantic_sha256": "sha256:<stable-projection-digest>",
      "raw_sha256": "sha256:<run-specific-file-digest>"
    }
  ],
  "journal_manifest_sha256": "sha256:<digest>"
}
```

Rules:

- Sort entries by mutant ID and journals by repository-relative path.
- Define each `semantic_sha256` over canonical JSON containing only stable
  mutation semantics (`exit_code_by_key` and `type_check_error_by_key` when
  present). Exclude `durations_by_key`, `estimated_durations_by_key`, mtimes and
  other run-timing data. `journal_manifest_sha256` hashes sorted relative paths
  plus semantic digests. Raw digests detect same-artifact tampering but are never
  compared across distinct runs.
- Normalize `type_check_error_by_key` to LF newlines, strip trailing line
  whitespace, and replace resolved worktree prefixes with repository-relative
  paths before cross-run hashing. If the pinned 3.7 format cannot be normalized
  without ambiguity, exclude those messages from cross-run equality and retain
  them only in same-artifact raw hashes.
- Include all recognized statuses, including equal survivors/timeouts on both
  arms; do not collapse them into kills or reject parity solely for their
  presence.
- Reconcile the full exported stats dictionary against map-derived status counts
  using the frozen 3.7 table. Keep all stats keys; do not invent a reduced bucket
  contract.
- Pin the 3.7 exporter identity explicitly: each exported status key equals its
  map-derived count, while `total` equals the sum of exported non-total buckets
  plus map-only `caught_by_type_check` and `not_checked` counts omitted by the
  exporter. A code-37 and a not-checked fixture are mandatory.
- Any unrecognized/malformed code is infra and cannot produce a comparable map.

### 6.2.2 Manifest schema v1

`mutation-manifest.json` is calibration evidence, **not a trusted receipt**:

```json
{
  "schema_version": 1,
  "run_id": "<run-id>",
  "run_dir": "<resolved-run-dir>",
  "worktree": "<resolved-worktree>",
  "candidate_id": "sha256:<complete-id>",
  "command": ["make", "mutation-check"],
  "command_kind": "mutation-full",
  "wrapped_returncode": 0,
  "gate_verdict": "pass",
  "mutmut_version": "3.7.0",
  "environment_id": "sha256:<digest>",
  "config_sha256": "sha256:<digest>",
  "lock_sha256": "sha256:<digest>",
  "msi_minimum": 85.0,
  "stats_path": "mutants/mutmut-cicd-stats.json",
  "stats_sha256": "sha256:<digest>",
  "status_map_path": "<run-relative-path>",
  "status_map_sha256": "sha256:<digest>",
  "journal_manifest_sha256": "sha256:<digest>",
  "stdout_sha256": "sha256:<digest>",
  "stderr_sha256": "sha256:<digest>",
  "survivor_ids": ["<documented-id>"],
  "recognized_non_kill_ids": ["<timeout-or-other-id>"]
}
```

`gate_verdict` mirrors the actual canonical command and current gate policy:
command rc, full stats, `MSI_MINIMUM`, no-tests rule, per-file ratchet, and the
plugin's stdout/stderr predicate. Survivors/timeouts are recorded, not required
empty.

`config_sha256` covers canonicalized `[tool.mutmut]`, relevant pytest config,
the zero-survivor claim set, full command arguments/parallelism, `MSI_MINIMUM`,
and every mutmut/pytest-affecting environment variable read by the pinned source.
`environment_id` reuses the gate-activity environment identity. The manifest
also binds the complete raw journal manifest.

Because the model can write all these bytes, self-consistent hashes prove only
artifact consistency. They do not prove that mutmut executed.

## 6.3 C1 warm-cache eligibility and state

### 6.3.1 Dedicated shadow command

Add a project-only `make mutation-shadow` target backed by
`scripts/run_mutation_shadow.py`.

The script:

1. Does **not** delete `mutants/`.
2. Runs the same pinned mutmut command/parallelism as the full.
3. Executes `mutmut export-cicd-stats` even when mutation returns a nonzero result
   for observed survivors, while preserving the mutation rc unless export itself
   fails.
4. Makes no authority decision; `run_evidence.py` captures all output/artifacts.

Unit tests mock subprocess results to prove export-after-nonzero, rc precedence,
and no cache deletion. The coordinator invokes one shell-operator-free command:

```bash
uv run python scripts/run_evidence.py \
  --out-dir "$BMAD_LOOP_RUN_DIR/evidence/commands/mutation-shadow" \
  --cwd . --candidate-id <sha256:id> \
  --command-kind mutation-shadow \
  --json-stats mutants/mutmut-cicd-stats.json \
  -- make mutation-shadow
```

The shadow temporarily overwrites `mutants/mutmut-cicd-stats.json`; its evidence
wrapper captures that file before the fresh full deletes `mutants/`. A crash in
between leaves only non-authoritative shadow data, and the next full deletes it
before producing canonical evidence.

### 6.3.2 Cache-origin and pilot state

After every successful fresh full, write advisory
`mutation-cache-origin.json` under the full evidence directory and a copy under
`mutants/`. It contains run ID, resolved worktree, full candidate ID, candidate
file hashes, mutmut/config/lock/environment IDs, stable journal-manifest digest,
the pinned mutmut function fingerprints, and mutated call-graph digest.

Add `scripts/assess_mutation_shadow.py`. It compares the origin with the current
candidate using the pinned 3.7 function-hash/call-graph representation and emits
`eligible`, `ineligible:<reason>`, or `unknown:<reason>` plus changed functions
and change-shape metadata. It proves only cache provenance/scope, never semantic
adequacy of production behavior. Every source-edit sample is tagged
`semantic_uncertainty=true`; future authority cannot rely on these samples alone.

The assessor is strictly read-only. It must not call mutmut generation functions
or touch mutant files, `.spans`, `.meta`, stats, or mtimes. Implement a pinned
read-only replica of 3.7's per-function hashing for changed source files. In a
disposable test tree only, run mutmut generation and compare its persisted
function hashes with the replica's output. A production assessor test hashes all
bytes/metadata under `mutants/` before and after and requires no change.

Before any shadow, require:

- Same nonempty run ID and resolved worktree.
- A complete prior full candidate different from the current candidate.
- Current `mutants/` stable semantic journal manifest (per section 6.2.1) exactly
  matches the prior full origin.
- Same mutmut/config/lock/environment identities.
- The only candidate changes since origin are inside confirmed `only_mutate`
  Python functions covered by the validated 3.7 hash/call model.
- No changed/untracked test, fixture, `conftest.py`, root pytest config,
  mutmut config, Makefile, lockfile, copied dependency, or non-`only_mutate`
  source file.

The first RELEASE, a no-origin worktree, or any uncertain diff skips shadow and
runs the full. Cache bytes are never used as release evidence.

Track the bounded pilot in
`$BMAD_LOOP_RUN_DIR/evidence/mutation-shadow-state.json`:

```json
{
  "schema_version": 1,
  "status": "observing",
  "candidates_observed": 0,
  "eligible_samples": 0,
  "diagnostic_samples": 0,
  "max_samples": 5,
  "max_candidates": 15,
  "last_verdict": null,
  "disabled_reason": null
}
```

- `REFUTED` sets `status=disabled`; every later candidate skips shadow.
- `INCONCLUSIVE` does not increment and allows one investigated retry only.
- Five `VALIDATED` samples set `status=complete`; shadow then turns off.
- C1-03..06 forced runs are `diagnostic_only=true`, increment only
  `diagnostic_samples`, and can never increment `eligible_samples`.
- C1-00 is a matrix-only same-candidate control and never increments pilot
  samples.
- At 15 observed candidates with zero eligible transitions, set
  `status=complete`, keep shadow off, and record
  `disabled_reason=no-eligible-transition-window` rather than observing forever.
- Missing/corrupt state fails safe by skipping shadow.
- State transitions are advisory and covered by deterministic tests.

## 6.4 C1 comparator and matrix

### 6.4.1 Comparator

Add `scripts/compare_mutation_evidence.py`. It verifies schemas, containment,
symlinks, semantic journal hashes, run/worktree/candidate/config identities,
cache provenance, and that shadow started before full. It compares:

- Exact sorted mutant ID sets and raw exit codes, with separate diagnostics for
  function-prefix/ordinal renumbering versus stale/missing results.
- Complete exported stats dictionaries.
- Map-derived status counts against each side's stats.
- Mutmut/config/lock/environment identities.

It emits two verdict dimensions:

- `result_parity=VALIDATED`: exact raw-map/stats parity, including identical recognized
  survivors/timeouts.
- `result_parity=REFUTED`: deterministic mismatch, missing/extra mutant, changed exit code,
  false-green/stale result, or eligibility violation discovered after execution.
- `result_parity=INCONCLUSIVE`: cold cache, malformed/unrecognized status, timeout on only one
  arm, infra failure, unsupported config, or inability to prove provenance.
- `selectivity=VALIDATED|INCONCLUSIVE`: whether 3.7 exposes a reliable rerun set
  or selective function-cache change. If no direct rerun set exists, compare
  pinned function-cache hashes plus journal semantic digests/mtimes before and
  after shadow. If no reliable discriminator exists, selectivity is
  `INCONCLUSIVE`; final-map parity alone does not prove incremental speed.
  Journal mtime alone is never sufficient: 3.7 may rewrite a whole `.meta` file.
  Use it only with a characterized subset-specific cache/hash signal; otherwise
  return `INCONCLUSIVE`.

The comparator writes a bounded diff, durations, rerun mutant IDs/count if mutmut
exposes them, cache state, and reason codes. Timing never converts mismatch to
success.

### 6.4.2 Characterization matrix

Use isolated same-commit worktrees for the manual A/B characterization:

- Arm A: fresh full warm-up, apply exact patch, run shadow.
- Arm B: apply the byte-identical patch in a fresh worktree, run fresh full.
- Preserve Arm A map/stats before any full overwrites the cache.
- Record patch SHA-256 and prove resulting candidate snapshots are identical.

| Case | Discriminating change | Acceptance |
|---|---|---|
| C1-00 | No change after warm-up | Exact map/stats; records no-op floor and rerun set. |
| C1-01 | Semantics-preserving change inside one covered `only_mutate` function that changes its mutant set | Exact map/stats plus `selectivity=VALIDATED`; if no reliable rerun signal exists, selectivity is `INCONCLUSIVE` and no operational pilot starts. |
| C1-02 | Change in a caller/callee pair where **both functions are confirmed in the mutated call graph** | Exact map/stats and observed cross-call invalidation; otherwise `INCONCLUSIVE`, never substitute `node.py`. |
| C1-03 | Test-only edit deliberately chosen to change at least one fresh-full mutant outcome | Operational eligibility must reject shadow. A forced diagnostic run records whether 3.7 would be stale. |
| C1-04 | Result-affecting mutmut/pytest config edit | Eligibility rejects shadow; forced run characterizes config invalidation. |
| C1-05 | Non-Python/copied dependency edit deliberately affecting a test outcome | Eligibility rejects shadow; forced run characterizes git/dependency behavior. |
| C1-06 | Lock/tool/environment/threshold edit | Eligibility rejects shadow; forced run characterizes dependency action. |
| C1-07 | Missing/corrupt/cross-run/cross-worktree cache-origin or state | Shadow is skipped without invoking mutmut incremental. |

Malformed `.meta`, unknown status, duplicate ID, and map/stats mismatch belong to
Phase 4 unit tests, not two-worktree A/B cases.

The C1-03..06 forced diagnostics are explicitly ineligible and cannot contribute
to promotion/pilot statistics even if their raw maps happen to match.

Select the C1-02 pair only after graph/source confirmation. The initial
`slice_scope.py`/`node.py` pair is invalid because `node.py` is outside
`only_mutate`.

Persist compact results at:

```text
docs/bmad-harness/evidence/c1-mutmut-37-characterization.json
docs/bmad-harness/evidence/c1-mutmut-37-characterization.md
```

The report records source/lock hashes, actual 3.7 config/status tables, patches,
commands, cache provenance, rerun sets, maps/stats hashes, durations, verdicts,
and gitignored raw artifact paths.

Repeat C1-00 through C1-02 at least three paired, interleaved times on the same
machine. Report medians and spread; report warm-up cost separately. A future
speed proposal may require >=20% median marginal savings, but timing is not an
enablement or authority criterion in this measurement-only delivery.

## 6.5 Candidate-bound duplicate-full observation

### 6.5.1 Trust boundary

`mutation-manifest.json`, status maps, stats, journals, stdout, and stderr are all
writable by the coordinator agent. Candidate IDs and self-consistent digests do
not prove command execution. Therefore:

- Do not add or enable a skip flag.
- Do not call an agent-authored artifact a trusted receipt.
- Do not bypass `_run_hard_commit_gates()`.
- Keep the pre-commit live full as today.

### 6.5.2 Observational validator

Add a validator used only to compute `would_reuse` before pre-commit. It checks:

- Latest event/manifest, same run, resolved worktree and complete candidate.
- Current environment/config/lock/threshold identity.
- Canonical command and current full gate predicate.
- Stats, map, output, stable journal-manifest digests, and same-artifact raw
  digests where applicable.
- No path escape, symlink, malformed schema, missing artifact, or stale file.

Then pre-commit **always runs the live full**. Afterward, the plugin uses
`mutation_journal.py` to write a post-full map/manifest under
`evidence/commands/mutation-precommit/`, compares rc/output/stats/stable journal
semantics with the coordinator manifest, and records whether hypothetical reuse
would have preserved the outcome. Capture/comparison failure is telemetry only
and cannot alter the live gate result.

Update `scripts/gate_activity.py`:

- `same_run_passing_evidence()` searches newest-first.
- It requires current environment identity. For the current candidate/command/
  environment, inspect the latest matching event only: return it if passing and
  return `None` immediately if failing. No separate revocation event is needed.
- Before adding its first production caller, correct the misleading current
  docstring/order and add a regression proving no existing caller consumes the
  oldest-first behavior.
- Candidate identity includes untracked root `pytest.ini`, `setup.cfg`,
  `tox.ini`, `.coveragerc`, root `conftest.py`, and other files actually consulted
  by pytest/mutmut.
- `record_gate_activity(..., would_reuse=False)` accepts the observational value.
- Events explicitly retain `reuse_applied = false`; if that changes the JSON
  shape, bump and test the schema.
- Appending an event invalidates or fully refreshes `_EVENT_CACHE`; a same-process
  pass-then-fail test must observe the failure as latest.

No validator exception may prevent the live full. Re-snapshot candidate and
artifacts after the live full before returning from pre-commit; drift vetoes as
today. Record the residual commit window explicitly.

### 6.5.3 Future trusted-witness gate, out of scope

Skipping pre-commit may be reconsidered only when one exists:

1. Engine/plugin executes or directly witnesses the RELEASE full and writes an
   event outside the model's write path; or
2. Engine/plugin signs the evidence with an ephemeral/private key unavailable to
   model tools and pre-commit verifies a pinned trust anchor.

That future plan must threat-model model access, nonce/key lifecycle, replay,
environment/config binding, revocation, and TOCTOU, and requires a human authority
amendment. Observational agreement alone is insufficient.

## 6.6 C4 deterministic advisor

### 6.6.1 Interface and safe output

Create byte-identical standard-library-only `scripts/red_test_advisor.py` and
vector files in both repos.

```bash
python scripts/red_test_advisor.py analyze \
  --project-root . \
  --evidence-root "$BMAD_LOOP_RUN_DIR/evidence/red-test-advisor" \
  --scenario-id @s1 \
  --target tests/path/test_file.py::TestClass::test_name \
  --output "$BMAD_LOOP_RUN_DIR/evidence/red-test-advisor/advisor-story-s1.json"
```

Repeat `--target` for every test written/changed by RED. The script must:

- Reject target and output path escapes, absolute escapes, symlinks, missing
  files, NUL, `.`/`..`, and unsafe path components.
- Require resolved output containment below `--evidence-root`, reject symlinked
  parents, and use same-directory temp + `os.replace`.
- Parse with `ast`; never import or execute tests.
- Parse nodeids by `::` segment, safely strip parameter suffixes from class and
  function segments, and return `unsupported` for ambiguous/escaped shapes.
- Hash normalized repository-relative targets and source bytes; exclude resolved
  project/evidence roots, output path, timestamp, locale and TTY from result hash.
- Emit stable ordering under different `PYTHONHASHSEED` values.

### 6.6.2 Conservative assertion-shape ruleset v1

Each signal has `rule_id`, path, line/column, and explanation.

`strong` means a mutation-sensitive **shape** exists over a call-derived value:

- Exact equality/identity against a specific expected value.
- Exact cardinality/membership/content.
- `pytest.raises(SpecificError, match=...)` around a call.
- Precise interaction assertion with expected arguments.

`weak` includes bare truthiness/falsiness, `is not None`, type-only checks,
`len(x) > 0`, broad `pytest.raises(Exception)`, called/count-only mocks,
assertions about setup/constants, or no behavior assertion.

`unsupported` includes ambiguous target selection, dynamic generation/data flow,
syntax errors, non-Python tests, unsupported nodeids, or inaccessible source.

Precedence is `unsupported > weak > strong` where uncertainty affects the
assertion. The advisor does not know the semantic subject. Vectors must include
exact equality on an unrelated call and fixture attribute; these may be shape-
strong but are explicitly **not** semantic certification. Future bypass requires
adding subject binding and proving its data flow.

### 6.6.3 Artifacts and coordinator flow

`advisor.json` schema v1 includes ruleset ID, normalized request/hash, scenario,
targets/source hashes, verdict, signals, unsupported reasons, and result hash.

After the existing LLM review:

```bash
python scripts/red_test_advisor.py compare \
  --advisor <advisor.json> \
  --llm-verdict strong \
  --llm-review <bounded-raw-review.txt> \
  --evidence-root <same-root> \
  --output <comparison.json>
```

The comparison binds advisor artifact/hash, raw LLM review hash, explicit LLM
label, scenario, target hashes, agreement, and ruleset. It is calibration only.

For every `development` RED:

1. RED returns exact changed paths/nodeids and failing command/result.
2. Run advisor analyze.
3. Run the existing full LLM mutant-hunting review regardless of advisor result.
4. Persist bounded raw LLM review and explicit label; run compare.
5. Apply only the LLM decision: weak returns to RED; strong may proceed to GREEN.
6. Record artifact paths/hashes and agreement in scenario evidence.

Static instruction tests prove the text requires this order, not runtime
compliance. Pilot telemetry must show the LLM artifact exists for every advisor
artifact, including advisor infra/unsupported cases.

No automatic bypass is in scope. A future proposal requires subject binding,
at least 35 manually adjudicated supported cases, zero observed false-strong
semantic claims, a >=0.90 95% Wilson lower bound for strong precision, and human
approval. Agreement alone is insufficient.

## 7. Implementation Sequence

Each phase is an atomic review boundary in isolated implementation worktrees.
Inspect git state and never revert unrelated changes. Do not commit unless the
implementation task explicitly requests it.

### Phase 0 - Freeze baselines

**Both repos; no behavior changes.**

1. Record HEADs, tool versions, lock/config hashes, policy values, and focused
   test results.
2. In Rompehielos, run/preserve a current 3.6 full summary, complete stats,
   journal map, survivor/timeout counts, and resolved worktree cwd.
3. Confirm tracked sources versus generated installed copies.
4. Freeze v3 artifact schemas and C4 vocabulary in test fixtures.

Stop on conflicting canonical-file edits, unexplained failing baselines, or an
unreproducible current full.

### Phase 1 - Build C4 analyzer in Rompehielos

**Files:**

- `scripts/red_test_advisor.py` (new)
- `tools/bmad-harness/tests/fixtures/red_test_advisor_vectors.json` (new)
- `tools/bmad-harness/tests/test_red_test_advisor.py` (new)

Tests cover every rule/precedence, unrelated-call shapes, fixtures, exact and
parametrized nodeids (class and function), dynamic/ambiguous tests, malformed AST,
target/output escapes, symlinks, atomic writes, canonical hashes, compare labels,
and raw-review binding. A subprocess test runs identical vectors with
`PYTHONHASHSEED=0` and `1`.

### Phase 2 - Wire C4 advisory in Rompehielos

**Files:**

- `tools/skills/tdd-red/{SKILL.md,prompt.txt}`
- `tools/skills/bmad-tdd-coordinator/{SKILL.md,prompt.txt}`
- `_bmad/custom/bmad-tdd-coordinator.toml`
- `tools/bmad-harness/tests/test_coordinator_instruction_consistency.py`

Instruction tests assert exact RED target handoff, analyzer-before-LLM order,
unconditional LLM wording, explicit raw review/label, no `certified`, and no
advisor authority. Do not change Python/JS hooks or `agent_bench/red/**`.

Runtime acceptance is observational: in each pilot RED, every advisor artifact
must have a later LLM review/comparison artifact before GREEN dispatch.

### Phase 3 - Pin and baseline mutmut 3.7.0

**Files:**

- `pyproject.toml`
- `uv.lock`
- `scripts/mutation_journal.py` (new)
- `scripts/check_mutation.py`
- `tests/quality/test_check_mutation_gate.py`
- `tools/bmad-harness/tests/test_mutation_journal.py` (new)
- `tools/bmad-harness/tests/test_run_evidence_mutation.py`

**Commands:**

```bash
uv lock --upgrade-package mutmut
uv sync --frozen
uv run pytest tests/quality/test_check_mutation_gate.py tools/bmad-harness/tests/test_mutation_journal.py tools/bmad-harness/tests/test_run_evidence_mutation.py -q
make test-pr
make mutation-check
```

Acceptance: exact 3.7.0, no unrelated lock upgrades, inspected source/config
table recorded, parser table matches pin, complete real journals/stats, unchanged
gate predicate, and no unexplained MSI regression.

Rollback includes dependency, lock, 3.7-dependent parser/table/tests, followed by
`uv sync --frozen`, focused tests, and a 3.6 `make mutation-check`. Do not leave
3.7-only expectations behind.

### Phase 4 - Add C1 evidence, shadow command, comparator and state

**Files:**

- `Makefile`
- `scripts/run_mutation_shadow.py` (new)
- `scripts/assess_mutation_shadow.py` (new)
- `scripts/run_evidence.py`
- `scripts/compare_mutation_evidence.py` (new)
- `tools/bmad-harness/tests/test_run_mutation_shadow.py` (new)
- `tools/bmad-harness/tests/test_assess_mutation_shadow.py` (new)
- `tools/bmad-harness/tests/test_run_evidence_{mutation,cli}.py`
- `tools/bmad-harness/tests/test_compare_mutation_evidence.py` (new)

Test matrix includes complete maps, recognized survivors/timeouts, every 3.7
status, `-24`, duplicate/boolean/non-integer/unknown codes, real stats
reconciliation, journal manifest changes, partial/missing sidecars, map/stats
hashes, stdout==disk summary, shadow stats after nonzero, cold/warm provenance,
run/worktree/candidate/config mismatch, order inversion, exact parity, map
mismatch, state transitions, and deterministic output.

Selectivity tests cover: direct rerun-set present; rerun-set absent with a
regenerated-only function-cache subset; whole-file `.meta` rewrite or
indistinguishable deltas yielding `INCONCLUSIVE`; and proof that final maps alone never
synthesize a rerun set or `selectivity=VALIDATED`.

Eligibility tests cover one-function hunks, multi-function/boundary hunks,
decorator/class/module edits, a function absent from the pinned 3.7 hash graph,
whitespace-only changes, added/removed `only_mutate` files, every non-
`only_mutate`/test/config/untracked exclusion, and origin/current hash mismatch.
They run against the exact C1-03..06 patch corpus before pilot enablement.
They also compare the read-only hash replica with 3.7 output in a disposable tree
and prove assessor execution leaves the operational `mutants/` tree byte- and
metadata-identical.

### Phase 5 - Execute C1 matrix and bounded warm-only pilot

**Files:**

- `tools/skills/bmad-tdd-coordinator/{SKILL.md,prompt.txt}`
- `_bmad/custom/bmad-tdd-coordinator.toml`
- `tools/bmad-harness/tests/test_coordinator_instruction_consistency.py`
- `docs/bmad-harness/evidence/c1-mutmut-37-characterization.{json,md}`

Observe defaults before selecting configuration. Do not claim safe invalidation
for test/config/dependency edits; the eligibility classifier excludes them.
Configure `mutation_shadow_cmd = "make mutation-shadow"` only after C1-00..02,
selectivity, and eligibility negatives pass. Collect up to five actual eligible
same-run, same-worktree transitions; first/cold candidates skip shadow. End the
pilot after 15 observed candidates even if no eligible transition occurred, and
report zero eligible samples as an operational-value `INCONCLUSIVE`, not success.

Any deterministic mismatch disables the pilot. Full runs on every candidate.

### Phase 6 - Candidate-bound duplicate-full observation

**Files:**

- `scripts/gate_activity.py`
- `tests/unit/test_gate_activity.py`
- `.bmad-loop/plugins/rompehielos-gates/rompehielos_gates.py`
- `.bmad-loop/plugins/rompehielos-gates/test_plugin.py`
- Plugin telemetry documentation/settings if needed

Tests cover newest-event selection, later-failure revocation, environment/config
binding, expanded untracked identity, missing run env, path/symlink escape,
malformed/missing/stale manifest/stats/map/journal/output, command mismatch,
survivor/timeout-preserving gate equivalence, threshold drift, candidate drift,
telemetry failure, duplicate manifests, same-process pass-then-fail cache
invalidation, post-full map equality/difference, and post-full capture failure.

Every case, including a hypothetical hit, asserts `_run_external("make",
"mutation-check")` still runs exactly once at pre-commit. No skip setting exists.

### Phase 7 - Distill/package standalone 0.1.4

**Files:**

- `scripts/red_test_advisor.py` and mirrored vectors/tests
- `skills/tdd-red/{SKILL.md,prompt.txt}`
- `skills/bmad-tdd-coordinator/{SKILL.md,prompt.txt,customize.toml}`
- `templates/custom/bmad-tdd-coordinator.toml`
- `tests/test_coordinator_instruction_consistency.py`
- `bmad_gherkin_tdd/installer.py`
- `tests/test_installer.py`
- `pyproject.toml`, `CHANGELOG.md`, `README.md`, `.github/workflows/ci.yml`

Add portable settings without changing the existing `mutation_cmd` contract:

```toml
[workflow]
red_test_advisor_cmd = "python _bmad/gherkin-tdd/scripts/red_test_advisor.py"
mutation_shadow_cmd = ""
```

An empty shadow command is disabled. Standalone explains that a project-owned
shadow is advisory and requires warm-cache/evidence support. It ships no mutmut,
Rompehielos parser, comparator, or evidence dependency.
Document that the existing default `mutation_cmd = "make mutation-check"`
requires each consumer to provide or override that project-owned command; this
plan does not silently change the published default.

Install mapping:

```text
_bmad/gherkin-tdd/scripts/red_test_advisor.py <- scripts/red_test_advisor.py
```

Bump `project.version` and `MODULE_VERSION` to 0.1.4; update status assertions,
changelog, temp install/force-upgrade/uninstall, and CI wheel payload check.
`setup.py` already stages `scripts/` and changes only if a build disproves that.

While touching installer path handling, add a regression for lexical managed
paths replaced by symlinks: status/uninstall must reject the symlink itself and
must never resolve then delete its in-project target.

### Phase 8 - Cross-repo parity and final review

1. `cmp` and SHA-256 the advisor source and vector bytes.
2. Compare normalized vector output tuples `(verdict, rule_ids, normalized vector
   name, source hashes, result hash)`, not run-dependent JSON bytes.
3. Temp-install standalone and execute the installed advisor.
4. Verify Rompehielos product-specific coordinator instructions remain present
   and no generated copy is tracked.
5. Run all final gates.
6. Adversarially review implementation security, evidence freshness, authority,
   regression risk, and test gaps before merge/release.

## 8. Verification Commands

### 8.1 bmad-gherkin-tdd

```bash
uv sync --frozen --extra dev
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest
uv build
```

Require wheel member:

```text
bmad_gherkin_tdd/payload/scripts/red_test_advisor.py
```

### 8.2 Rompehielos focused

```bash
uv run pytest tests/quality/test_check_mutation_gate.py -q
uv run pytest tools/bmad-harness/tests/test_mutation_journal.py -q
uv run pytest tools/bmad-harness/tests/test_run_mutation_shadow.py -q
uv run pytest tools/bmad-harness/tests/test_assess_mutation_shadow.py -q
uv run pytest tools/bmad-harness/tests/test_run_evidence_mutation.py -q
uv run pytest tools/bmad-harness/tests/test_run_evidence_cli.py -q
uv run pytest tools/bmad-harness/tests/test_compare_mutation_evidence.py -q
uv run pytest tests/unit/test_gate_activity.py -q
uv run pytest .bmad-loop/plugins/rompehielos-gates/test_plugin.py -q
uv run pytest tools/bmad-harness/tests/test_red_test_advisor.py -q
uv run pytest tools/bmad-harness/tests/test_coordinator_instruction_consistency.py -q
uv run pytest tests/test_tdd_cycle_gate.py -q
uv run ruff check scripts/red_test_advisor.py scripts/mutation_journal.py scripts/run_mutation_shadow.py scripts/assess_mutation_shadow.py scripts/run_evidence.py scripts/compare_mutation_evidence.py
```

### 8.3 Rompehielos final authority

```bash
make test-pr
make mutation-check
```

The final mutation command is fresh. Shadow and candidate-bound observation
cannot satisfy it or suppress the existing pre-commit live full.

### 8.4 Cross-repo advisor parity

```bash
cmp /mnt/bunker_data/bmad-gherkin-tdd/scripts/red_test_advisor.py /mnt/bunker_data/rompehielos/scripts/red_test_advisor.py
cmp /mnt/bunker_data/bmad-gherkin-tdd/tests/fixtures/red_test_advisor_vectors.json /mnt/bunker_data/rompehielos/tools/bmad-harness/tests/fixtures/red_test_advisor_vectors.json
sha256sum /mnt/bunker_data/bmad-gherkin-tdd/scripts/red_test_advisor.py /mnt/bunker_data/rompehielos/scripts/red_test_advisor.py
sha256sum /mnt/bunker_data/bmad-gherkin-tdd/tests/fixtures/red_test_advisor_vectors.json /mnt/bunker_data/rompehielos/tools/bmad-harness/tests/fixtures/red_test_advisor_vectors.json
```

## 9. Rollout And Rollback

| Surface | Rollout | Automatic stop | Rollback |
|---|---|---|---|
| mutmut 3.7.0 | Pin, inspect and baseline before C1 | Baseline/journal/MSI/config incompatibility | Revert pin, lock, 3.7 parser/table/tests; sync and rerun 3.6 full |
| C1 shadow | Manual matrix, then warm-only bounded pilot | Any parity mismatch, corrupt state, ineligible/cold cache | Empty `mutation_shadow_cmd`; full unchanged |
| Duplicate-full observation | Validation telemetry only; live pre-commit full always runs | Validator suppresses/delays full or misstates outcomes | Remove observation call; existing full remains |
| C4 advisor | Advisory on every development RED | Path/security defect or disruptive retries | Empty advisor command/remove advisory instruction; LLM unchanged |
| Standalone 0.1.4 | Temp install and wheel verification | Managed-file/payload regression | Do not release; test consumer may reinstall 0.1.3 |

Rollback preserves evidence and unrelated changes. It restores prior authority
paths, not a compatibility shim.

## 10. Telemetry And Success Measures

### 10.1 C1

Record per candidate:

- Run/worktree/candidate/cache-origin IDs.
- Shadow eligibility or skip reason.
- Candidates observed, eligible samples, diagnostic-only samples, and terminal
  no-eligible-window disposition.
- Tool/config/lock/environment hashes.
- Shadow/full durations, raw-map/stats/journal hashes, and rerun sets.
- Comparator verdict/reasons.
- Hypothetical pre-commit `would_reuse` result and actual live-full result.
- Number of live fulls; expected count remains current behavior in this delivery.

Success:

- No cold/cross-run/cross-worktree/ineligible shadow invocation.
- Exact parity for every accepted sample, including recognized survivor/timeouts.
- Any mismatch disables shadow while the full continues.
- Every pre-commit executes the live full; telemetry never authorizes a skip.
- Current aggregate MSI/no-tests/per-file ratchet remains unchanged.

### 10.2 C4

Record ruleset/target hashes, advisor verdict/signals, raw LLM review/hash, LLM
label, agreement, RED revision, and whether GREEN followed only the LLM result.

Success means deterministic artifacts and one LLM review artifact for every
advisor invocation, including infra/unsupported cases. It does not authorize
advisor replacement.

## 11. Stop Conditions And Experiment Ledger

Every premise is `VALIDATED`, `REFUTED`, or `INCONCLUSIVE` before dependent
behavior is enabled.

| Premise | Validation | Fallback |
|---|---|---|
| 3.7 preserves full-gate semantics | Pin-source inspection + baseline full | Restore complete 3.6 phase; C1 off |
| Raw map/parser matches 3.7 | Frozen-table check + real journal golden | Artifact infra; full unchanged |
| Cache is warm and eligible | Origin/state/journal/worktree/config checks | Skip shadow |
| Function-scope eligibility is mechanical | Pinned function-hash/call-graph analyzer + C1-03..07 negatives | Mark unknown and skip shadow |
| Incremental parity for scoped edits | C1-00..02 exact repeated A/B | Disable shadow |
| Unsafe changes are excluded | C1-03..07 eligibility tests | Skip shadow and run full |
| Coordinator/full duplicate appears reusable | Observation followed by live pre-commit comparison | No skip; collect mismatch reason |
| Trusted witness exists | Separate engine/plugin/signature design and threat review | Keep duplicate live full |
| C4 is deterministic/conservative | Mirrored vectors, hash-seed tests, pilot telemetry | Unsupported + LLM review |
| Standalone preserves advisor behavior | Source/vector parity, normalized outputs, temp install | Do not release 0.1.4 |

Any requested authority, phase, MSI, or advisory-scope change stops for a human
amendment.

## 12. Traceability

| Goal | Implementation | Mechanical evidence |
|---|---|---|
| Characterize C1 safely | 3.7 pin, warm provenance, isolated A/B, raw maps/stats | Characterization report + comparator tests |
| Preserve RELEASE | Fresh coordinator full and unchanged pre-commit full | Instruction/plugin tests + final commands |
| Evaluate duplicate full honestly | Non-authorizing validator followed by live result | `would_reuse` vs actual event telemetry |
| Deterministic C4 signal | Pure AST advisor and common vectors | Byte-identical source/vectors + normalized output parity |
| Preserve LLM authority | Unconditional LLM instructions and pilot artifacts | Static tests + one LLM artifact per advisor artifact |
| Portable distribution | Installer 0.1.4 mapping and wheel payload | Installer lifecycle + temp install + wheel inspection |
| Prevent drift | Explicit ownership and cross-repo hashes | Recorded source/vector SHA-256 |

## 13. Adversarial Review Record

Round 1 rejected v1:

- Architecture: `ses_fc2fb687cfferoUM5cGP5wWys5`
- Security: `ses_fc2fb67e9ffeg9r1mTxw3tIvdQ`
- Verification: `ses_fc2fb6714ffeIqSlwP9yPSlRLz`

Material corrections incorporated in v2:

1. Removed empty-survivor/timeout preconditions; parity preserves recognized
   current full-gate statuses.
2. Replaced assumed cold operational shadow with same-run/same-worktree warm-only
   eligibility and bounded state.
3. Added a shadow command that exports stats before the fresh full wipes cache.
4. Replaced invalid caller pair and predeclared dependency outcomes with
   discriminating eligibility/diagnostic cases.
5. Centralized 3.7 status mapping and raw journal manifest reconciliation.
6. Removed pre-commit skip from scope because agent-authored evidence lacks a
   trust anchor; changed it to observation followed by mandatory live full.
7. Added environment/config/lock/journal binding, latest-event/failure rules,
   expanded candidate identity, and post-gate drift checks.
8. Narrowed C4 `strong` to assertion shape, secured output paths/nodeids, added
   raw LLM binding and honest static-vs-runtime acceptance.
9. Clarified normalized cross-repo output parity and hash-seed execution.
10. Added complete 3.7 rollback and installer lexical-symlink regression.

Round 2 approved the v2 authority architecture and requested localized
measurement corrections in the same sessions. Material v3 corrections:

1. Defined stable semantic journal projections that exclude run durations.
2. Added the exact 3.7 stats-total identity for map-only type-check/not-checked
   statuses.
3. Added the mechanical function-scope eligibility analyzer and its negative
   test matrix.
4. Split result parity from selectivity, added rerun-observability fallback, and
   separated diagnostic-only samples.
5. Added a 15-candidate zero-eligibility horizon and explicit terminal outcome.
6. Defined latest-event failure semantics/cache invalidation without an
   ambiguous separate revocation event.
7. Added plugin-owned post-live-full capture for observational comparison.
8. Bound command parallelism/environment and documented transient shadow stats.

Round 3 final dispositions in the same sessions:

- Security: approved with no unresolved critical/high/material-medium findings.
- Architecture: all prior findings resolved; requested a read-only pinned hash
  implementation and explicit `not_checked` handling.
- Verification: all prior critical/high findings resolved; requested explicit
  selectivity-branch tests and stale-label cleanup.

Final corrections added the non-invasive hash replica/golden test, operational
cache immutability assertion, nullable `not_checked` contract, normalized type-
check projection, and selectivity negative cases. No authority path changed.

## 14. Re-Review Checklist

The final reviewer must answer:

1. Can any shadow/advisor/manifest alter RELEASE, GREEN, or commit authority?
2. Is every operational shadow demonstrably warm, same-run, same-worktree and
   limited to validated source edits?
3. Are survivors/timeouts handled as current policy data rather than impossible
   empty-list requirements?
4. Does exact parity compare raw IDs/codes, complete stats, and journal manifests?
5. Can any observation validator suppress or delay the live pre-commit full?
6. Is the lack of trusted receipt authorship explicit and safely deferred?
7. Does C4 avoid executing tests and constrain both target and output paths?
8. Is C4's assertion-shape claim no stronger than its inputs can prove?
9. Are all LLM reviews still unconditional and observable?
10. Are rollback, installer lifecycle, and cross-repo parity mechanically tested?

Implementation is ready only with no unresolved critical/high findings and human
approval.
