# Adversarial review — GREEN agent benchmark (surface effectiveness)

> **Remediation (same day):** P14 remap, P15 tag filter, P21 FF reject + or/and kill,
> P17 exact caplog (no fallback), deny∩allow test, local quality checkers,
> proportional visible, quality gated on gold pass>0. Probe re-run: former FPs now fail hidden.

Date: 2026-08-23
Reviewed files:
- Surfaces: `agent_bench/green/eval/surfaces.yaml` (250 lines, 24 conductual + 16 quality + 12 cheat)
- Golden impl: `agent_bench/green/eval/golden/quota_broker.py` (197 lines)
- Hidden suite: `agent_bench/green/eval/hidden/test_heldout.py` (467 lines, 32 test methods)
- Gold suite: `agent_bench/green/fixtures/green-hard/tests/unit/test_green_hard.py` (612 lines, 22 test functions)
- Contract: `tests/contracts/green-hard.feature` (8 @s), `SPEC-PINS.md` (P1–P24)
- Harness: `eval/cheat_detect.py`, `eval/batch_eval.py`, `eval/run_pytest.py`, `eval/judge.py`, `launch.py`

Method (same as `agent_bench/red/eval/tests/adversarial-report.md`): execute probes, do not infer.
Probes ran against copies of the **golden** impl mutated in the way each surface describes, then
gold (`22 passed`) and hidden (`32 passed`) suites re-run. Control probes confirm the method:
P1 `>=`→`>` (mutate `rec.score < threshold`→`<=`) is killed by BOTH suites (gold 3 failed,
hidden 2 failed) and P2 `and`→`or` is killed by both — so the harness *can* catch real pins.

Line citations: `GO:n` = golden/quota_broker.py, `GO-TEST:n` = gold test_green_hard.py,
`HID:n` = hidden test_heldout.py, `SY:n` = surfaces.yaml, `BE:n` = batch_eval.py, `CD:n` = cheat_detect.py.

---

## 1. FALSE POSITIVES (surface claimed hit, mutant survives)

### 1.1 P14 `path_map` (SY:83-85) — MUTANT SURVIVES (probe)
Golden:106-110 loops `path_map.items()` and executes `if v is None: pass`. **No observable behavior
exists for path_map in the SUT.** Gold (G-TEST:388-397 `test_s4_path_map_identity`) and hidden
(HID:287-296 `test_path_map_none_identity`) only assert `len(accepted) == 1`.
**PROBE:** deleted the whole path_map block (GOOD:105-110) from golden → gold `22 passed`,
hidden `32 passed`. The "identity pass-through" is a tautology of "no-op", so any mutant in
path_map keeps the same behavior. Claimed surface = not killed.

### 1.2 P15 `absent_key` (SY:88-90) — MUTANT SURVIVES (probe)
Golden:113 `_has_extra = hasattr(spec, "extra_key")` is **write-only**: assigned, never read
(verified by occurrence search; only occurrence is GOOD:113). There is no default-path branch,
so "absent key → default path (Tipo C)" is unimplemented. Tests only assert `len(accepted) == 1`
plus an input-side `assert not hasattr(spec, "extra_key")` (G-TEST:405, HID:305) that never
observes the SUT.
**PROBE:** deleted the `_has_extra` line (GOOD:113) from the same mutation set → gold 22 passed,
hidden 32 passed.

### 1.3 P21 `or_compound` (SY:122-125) — MUTANT SURVIVES (probe)
Golden:128-133: → both branches `pass`. `mode`/`flag` are **no-ops**; every record follows the
same accept path regardless. Gold (G-TEST:498-540 `test_s7_or_compound_truth_table`) asserts
all 4 combos accepted; hidden (HID:401-415) asserts TT/TF/FT accepted (no FF combo at all).
Because ALL combos produce the identical outcome, the `or`↔`and` mutant is invisible.
**PROBE:** mutated `if mode == "strict" or flag:` → `... and flag:` → hidden or_compound `3 passed`,
gold or_compound `1 passed`. (The feature's own Then at feature:107-109 even *contradicts* the
golden, demanding rejection for relaxed+no-flag — see §4.2.)

### 1.4 P17 `log_exact` (SY:103-105) — MUTANT SURVIVES (probe)
- Gold: there is **no log assertion anywhere** — `test_s3_wiring_exacto` docstring claims "P17: log exact"
  (G-TEST:318) but its body (G-TEST:317-342) asserts only emit args/identity/clock/capsys. No `caplog`.
- Hidden (HID:342-353): `found = any("accepted log_h score=90" in msg ...)` **then a fallback**:
  `if not found: assert len(sink.calls)==1 ...` (HID:350-353) — i.e., if no log line exists at all,
  the test still passes as long as the sink was called.
**PROBE:** removed `logger.info("accepted %s score=%s", rec.key, rec.score)` (GOOD:183) from golden
→ hidden `TestHeldOutLogExact` passes (`1 passed`), gold suite passes (`22 passed`). An impl that
never logs scores full credit for a "log exact" surface. Also note the check is substring (`in msg`),
not `==`, so wrong-format logs also survive when caplog is non-empty.

### 1.5 P21's 3 hidden tests are *credit without behavior* (scoring consequence)
`TestHeldOutOrCompound` contributes 3 of the 32 hidden test slots (~9.4% of hidden credit) for a
behavior that cannot change any observable outcome. Combined with P14+P15+P17 hidden tests
(HID:290-297, 302-309, 342-353) the **vacuous hidden credit is 6/32 ≈ 18.7%** that a stub can earn
without implementing the pinned behavior.

### 1.6 P18 `capsys_exact` overclaims "exact" (SY:108-110)
Both tests use substring, not exact equality: gold `assert "dispatch mid_77 work" in captured.out`
(G-TEST:342, also 461) and hidden `assert "dispatch cs_h work" in captured.out` (HID:366).
The print-absence mutant **is** killed (probe: removal fails both suites), but a mutant printing
extra trailing text on the line survives. Severity: low (absence is what most mutants hit, and that
is covered).

---

## 2. FALSE NEGATIVES / DEAD PINS in golden

### 2.1 Dead-code pins — confirmed
| Pin | Golden lines | Observable? | Evidence |
|---|---|---|---|
| P14 path_map loop | GOOD:106-110 | No (`pass` body) | probe §1.1 |
| P15 `_has_extra` | GOOD:113 | No (write-only) | grep shows single occurrence |
| P21 mode/flag compound | GOOD:128-133 | No (both branches pass) | probe §1.3 |
| deny steering | GOOD:139-141 | **No effective test** | probe below |

### 2.2 `deny` branch (allow/deny @s5) — dead even against gold
**PROBE:** removed the deny block (GOOD:139-141) from golden → all 32 hidden pass, and gold
`test_s5_kind_in_allow_not_in_deny` still passes (G-TEST:435-461) because `spam` (denied) is also
**not in allow**, so the allow check rejects it first. No test anywhere exercises a kind that is
in-allow AND in-deny. Add: also, hidden suite has **no allow/deny test at all**.

### 2.3 Quality surfaces are structurally dead (see §5.1) — 16 declared, 0 scored.

### 2.4 P20 trace_roundtrip roundtrip-part unobservable
HID:387-395 asserts `trace_id == f"trace_{key}"` on the same record object returned; since there is
no read function, "roundtrip" is a second read of an attribute that was just set — cannot observe a
"write-only" mutant. Write side-effect IS covered; the roundtrip half is decorative
(contract Then "second read returns same trace_id", feature:99 — satisfied trivially).

---

## 3. TAUTOLOGIES in gold/hidden

### 3.1 Gold test tautologies — confirmed (G-TEST, lines 184 / 186-188)
- G-TEST:188 `assert 3 + 5 + 11 == 19` — local arithmetic, no SUT reference; passes regardless of `apply`.
- G-TEST:189 `assert 3 + 5 + 11 != 3 * 5 * 11` — same.
- G-TEST:198-200 `assert THRESHOLD - 1 == 49` / `assert THRESHOLD == 50` / `assert THRESHOLD + 1 == 51`
  — pins on a module constant, not the SUT.

Impact is limited: the real accumulator assertion G-TEST:187 `assert total_weight == 19` does kill
`+`↔`*` (probe: `>=` control also failed, so the boundary is genuinely pinned), and P1 is genuinely
lied. The tautologies inflate assertion counts but do not mask the kill for these specific pins —
they are redundant noise, not the kill. They do, however, contradict the SPEC-PINS claim
("No pin is 'the test sums 3+5 locally'", SPEC-PINS:4).

### 3.2 Hidden tautologies
- HID:305 `assert not hasattr(spec, "extra_key")` — input check, not SUT (and P15's SUT behavior is dead anyway, §1.2).
- Hidden or_compound all-accept asserts (HID:401-423) — tautological given GOOD:128-133 no-op.

---

## 4. GAPS (MUTANT_KILLING_GUIDE / contract Then with no effective test)

1. **@s5 allow/deny has NO surface id** in surfaces.yaml (grep: only P6 mentions "kind" indirectly;
   no "allow"/"deny"/"membership" surface). The @s5 core behavior is invisible to the matrix, and the
   deny half is untested (§2.2). Hidden suite omits it (HID has no allow/deny test).
2. **P24 fixture_not_target (SY:137-140) is a dead surface id** — grep: not referenced by any `.py`
   (its function is only subsumed by the separate `sample_leak` cheat, CD:124-128). No
   `TestHeldOutFixtureNotTarget` exists in the hidden suite (confirmed absent). The surface is
   decorative.
3. **Contract probe (feature:108) "relaxed + no flag → rejected"** is not implemented by the golden
   (golden accepts FF) and no test enforces it. Either the contract or the golden is wrong; the
   current state means the FF combination of P21 is *specified-rejected* but *implemented+tested-
   accepted*.
4. **Hidden suite lacks a cache-reset fixture.** Golden's `_cache` is module-global
   (GOOD:145, 178-180). Gold suite resets it autouse G-TEST:31-38; hidden does **not** (HID has no
   autouse/clear; verified by grep). Hidden keys are currently unique (cache_hit, ci_a/b/c, …), so
   no live cross-test leak in the shipped suite, but the suite silently relies on global cache state
   surviving between classes; a future hidden test re-using a key would leak between tests.
5. **capsys + log are claimed as "exact" (P17/P18) but tested as substring** — the "exact" requirement
   (SPEC-PINS P17 `==`, P18 "full line equality") has no enforcing test (§1.4, §1.6).

---

## 5. EVAL HARNESS bugs

### 5.1 `_check_quality` fails closed → ALL quality surfaces always 0/0, score capped at 85
`BE:88-89` catches `ImportError` and returns `{"passed":0,"total":0,"pct":0,...}`.
**PROBE:** in the current eval environment `import harness_quality_gate` fails
(ModuleNotFoundError). So every row gets `quality: 0/0`, `quality_pct: 0`, and the `0.15*quality`
term (score formula `BE:128-131`) is always 0 — maximum achievable score elsewhere 85, never 100.
All 16 quality surfaces (SY:143-219) are, in practice, never scored.

### 5.2 surfaces.yaml is never consumed by any evaluator
`grep -rln "surfaces.yaml" eval/` matches only the file's own header comment. `batch_eval.py` does
gold-pytest pass/fail + hidden-pytest pass/fail + 7 aggregate quality booleans; **nothing iterates
surfaces.yaml**. The conductual surface matrix is documentation; scoring cannot distinguish "P14
test passed" from "P14 test vacuous". (The per-pin mapping G-TEST docstrings → surfaces is
ungaffered; the red bench at least AST-scored surfaces — green's green bench has *no* per-surface
checker.)

### 5.3 hidden denominator hardcodes 32 and weights per-method, not per-surface
`HIDDEN_TEST_TOTAL = 32` (BE:25) matches the count of test methods (computed: 32), so the
denominator is right. But surfaces with 3 methods (or_compound x3, normalize x3) get 3x
credit; dead-surface methods (§1.5, ~18.7%) inflate hidden credit for unbuilt behavior.

### 5.4 visible score is binary
`visible_pct = 100.0 if (gold pass and fail==0) else 0.0` (BE:113) — a single failing gold test
zeroes the whole 30% term; no partial credit edge although the contract has 8 independent scenarios.
(Design choice, but it makes the visible axis a hard gate, and the field `visible` then shows
`pass/total` while `visible_pct` is 0 — inconsistent reporting (BE:137-139).

### 5.5 `run_pytest.py` uses `-x` (maxfail=1)
Run gold/hidden with `-x -q` (RP:36): after a first failure pytest stops; the parsed counts reflect
only tests run before the failure. With `-x`, pass counts for a failing impl are under-represented
in the "passed/F" fraction... actually fine for score, but `run_gold` also composes status only
from returncode; a collection error (0 passed, 1 error) returns status "fail" with no counts with
"passed"/"failed" lines — safe, but `fail_count` stays 0 and `pass_count` stays 0, so the diagnostic
strings ("0/0") are misleading (BE:137). A collection error in gold therefore shows `visible: 0/0`
which is ambiguous with "no output".

### 5.6 cheat_detect
- `sample_leak` uses substring `label in content` (CD:11-11) — more robust than red's whole-literal
  version; but substring `"alpha"` also matches harmless words like "alphabet" / "alpha_numeric" in
  comments — possible false-positive noise (minor).
- `bare_except` regex (CD:33-111) only inspects the first non-comment line of each `except
  Exception` block for "raise"; a multi-line `except Exception:` where `raise` sits on line 2 or
  later is missed (minor).
- No `-k` isolation in `run_gold` — sandbox init `_clean_impl_slot` deletes `src/quota_broker.py`
  which `opencode` will re-create, so `run_pytest` against a post-run sandbox works. ok.

### 5.7 quality surfaces count vs checkers mismatch
Even when HQG is installed, `_check_quality` exposes 5 principle + 1 solid + 1 antipattern
aggregates (BE:16-85) — not the 16 declared condad... quality surfaces. The declared
solid_srp/solid_ocp/.../ap22_dead_code ids (SY:143-219) have no per-id scorer mapping anywhere.

---

## 6. PRIORITIZED FIX LIST

1. **(P0) Kill the vacuous P14/P15/P21/P17 pins or make them observable.**
   - Give path_map a real observable (e.g., `extra_key` default value / renamed-kind dispatch that
     drops records, or a pass-through that returns `None`-sentinel) and assert it (gold + hidden).
   - Give `mode/flag` a real gate per the contract (G0: "relaxed+no-flag → rejected") — the contract
     and golden currently contradict; resolve and test FF.
   - Remove the empty fallback in HID:350-353 and assert `caplog.messages[0] == exact` so P17 kills.
   - Implement `_has_extra`-driven default branch, then test it.
2. **(P0)** Add an allow/deny surface + hidden variant, and a test where a record is **in allow AND
   in deny** (both must be observable) to make the deny branch killable.
3. **(P0)** Wire surfaces.yaml into the evaluator (or drop the matrix claim): per-surface verdicts
   so a vacuous pass is distinguishable from a kill (both red's AST approach and/or a mutation-mode
   on CI).
4. **(P1)** Fix `_check_quality`: make harness_quality_gate a hard dependency with clear per-surface
   scoring, or remove the 16 quality surfaces from surfaces.yaml until they map to real checks.
5. **(P1)** Add a cache-reset fixture to the hidden suite.
6. **(P1)** Update SURFACES metadata: remove/de-dup `fixture_not_target` (dead id) vs `sample_leak`;
   update P18/P17 descriptions from "exact" to "contains".
7. **(P2)** Change `visible_pct` from binary to proportional (or document the hard gate); make
   `run_pytest` distinguish collection-error from 0-fail; handle the `-x` interaction in reported
   counts.

---

## Appendix — probe log (all executed, 2026-08-23, python3.14 / pytest 9.0.2)

| # | Mutation on golden | Suite | Result |
|---|---|---|---|
| 0 | none (baseline) | gold / hidden | 22 pass / 32 pass |
| 1 | delete P14 path_map block (GOOD:106-110), P15 `_has_extra` (GOOD:113), P21 compound (GOOD:128-133) | gold / hidden | 22 pass / 32 pass → all 3 pins dead |
| 2 | delete `logger.info` (GOOD:183) | hidden TestHeldOutLogExact / gold | 1 pass / 22 pass → P17 survives |
| 3 | rec.score `<` → `<=` (P1) | gold / hidden | 3 fail / 2 fail → P1 killed (control) |
| 4 | `and` → `or` truth table (GOOD:124) | gold / hidden | 1 fail / 1 fail → P2 killed (control) |
| 5 | delete deny block (GOOD:139-141) | hidden / gold | 32 pass / 22 pass → deny dead |
| 6 | delete `print` dispatch (GOOD:186) | hidden / gold | 1 fail / 2 fail → print-absence killed |
| 7 | SKIP `is` → `==` (GOOD:101) | hidden / gold | 1 fail / 1 fail → P13 killed (control) |
| 8 | `or` → `and` at GOOD:128 | hidden / gold | 3 pass / 1 pass → P21 survives |
| 9 | HQG import probe | n/a | ModuleNotFoundError → quality 0/0 |none||