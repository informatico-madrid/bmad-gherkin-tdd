# Adversarial review v2 — `static_score.py` (second pass after bug fixes)

Date: 2026-08-23
Reviewed: `agent_bench/red/eval/static_score.py` (925 L), `agent_bench/red/eval/surfaces.yaml` (273 L)
Samples: DS = `nan__deepseek-v4-flash/tests/unit/test_red_hard.py` (reported 96/100 = 43/45),
MM = `nan__mimo-v2.5/tests/unit/test_red_hard.py` (reported 73/100 = 33/45)
Refs: `SS:n` static_score.py, `SY:n` surfaces.yaml, `DS:n`/`MM:n` test files, `STUB:n` `agent_bench/red/fixtures/red-hard/src/quota_broker.py`.
Every claim below was re-executed against the current code (probes P1–P13, §6). Scores reproduce exactly (96, 73).

## Fixed since v1 (re-verified)

- `_collect_numbers` excludes bools (SS:44) — v1 4.1 gone.
- `dense_assertions` accepts Tuple/Set (SS:73) — v1 2.5/4.8 gone.
- `no_loose_in` / `no_len_gt` are real AST now (SS:526-551) — v1 4.2 dead penalties gone.
- `no_sample_leak` substring-based, assert-scoped (SS:697-709) — v1 4.9 gone.
- MM `default_mutation`/`default_kwarg`/`h18`/`type_e`/`type_g` FPs gone (correctly missed now); MM `h2_clock`/`truth_table`/`h4` FNs fixed.
- `type_f_roundtrip` moved to `llm_only` (SY:237) and excluded from the denominator (SS:871-873) — no more uniform −2.17 deflation.
- MM `h6_fallback` now hits via the real `side_effect =` Assign idiom (SS:304-308, MM:336).

---

## A. Remaining false positives

**1. MM `h20_pathmap` (2.2 pts) — TRUE FP, unchanged from v1 1.4.**
`MM:315` calls `apply([rec], spec, sink, clock, path_map=path_map)`. The stub API is
`apply(records, spec, sink, clock, *, timeout)` (STUB:21-28) — no `path_map` parameter.
The call raises `TypeError` before `MM:317` (`accepted[0] is rec`) can ever run, against
the stub *and* any conformant implementation. H20 behavior is not covered. The checker
(SS:412-422) credits it on "None"+"path_map" substrings in the fixture dict. The feature's
own `When` clause (`red-hard.feature:64`) uses the 4-positional form; path_map belongs on
the spec (DS does this correctly at DS:360). Root cause: no signature cross-check (v1 4.10).

**2. MM `type_c_absent_key` (2.2 pts) — borderline FP, unchanged from v1 1.5.**
Fired by "missing" in the test name alone; probe P8 confirms name-only suffices. Body
asserts counts only (MM:329-330 `len(accepted)==1`, `len(rejected)==0`); a Tipo C mutant
that changes the emitted *kind* on the default path without changing counts survives.
DS pins the full tuple (DS:383-387) + `not hasattr` (DS:378).

**3. MM `h14_xxwrap` — coincidental mechanism.**
Fires on `== "accepted"` (MM:246, wiring kind), not on any error message. MM never asserts
the SinkError message via `==` (injected at MM:336, never observed) and covers exact-message
only via `match=re.escape` (MM:170/179, credited under `typed_exception`). Borderline.

**4. Both: `exact_boundary` fires on the (0,1,2) count-triple, not the threshold boundary.**
DS: 0/1/2 from `len==0` (DS:339), `len==1` (DS:180), `len==2` (DS:112). MM: same (MM:296/113/81).
Neither file contains 49/50/51 or 50/51/52. Probe P1: a file with only `assert len(x) == 0/1/2`
hits `exact_boundary`. Surfaces are genuinely covered by both files (3/7/50/51/99), so no
score distortion — but the trigger is pure coincidence (v1 1.6 persists in new form).

**5. DS `spy_complete` + `kwargs_passthrough` — coincidental mechanism.**
DS contains **no** `assert_called_once_with`. Hit via branch 2 (SS:116-124): any
Attribute named record/timeout/key/score + any `x.calls[...]` subscript anywhere —
decoupled, probe P7b fires even through a local alias (`c = sink.calls[0]; assert c.key == "x"`).
Result happens to be right (RecordingSink captures all 5 args; each is asserted, DS:144-148/253/271-275).

**6. MM `h2_clock` / `h8_stop_count` — the v1 fix was over-broad.**
SS:276 matches *any* `.call_count` attribute on *any* mock: probe P6 (`m.other.call_count == 1`,
no clock anywhere) hits both `h2_clock` and `h8_stop_count`. MM's real evidence
(`clock.now.call_count == 1`, MM:261) exists, so the score is right, the mechanism is not.

**7. Both: `truth_table`/`h4_truth_table`/`bool_and_or` are presence-based, not combination-based.**
The v1 FN fix (SS:187-203) counts a function with *any* True+False as 2 "combos", and the
fallback branch fires when 2 test functions contain *any* bool constant. Probe P3: a single
TT/FF-only function (no TF/FT — the exact case the surface excludes, SY:32) plus one unrelated
`x = True` test credits all three surfaces. Both samples have genuine 4-combo tables
(DS:197-213, MM:123-154) so no distortion, but the check cannot distinguish.

## B. Remaining false negatives

**8. Both: `accumulator_asymmetric` — TRUE FN, unchanged from v1 2.2.**
SS:167 still hardcodes `3 in nums and 5 in nums`. Neither file contains the literal 5, yet
both have real asymmetric accumulators: DS:152-167 (`total_weight == 200` from 50/51/99 —
kills `+→*`, `+=→=`), MM:91-93 (`total_weight == 120` plus explicit guard
`40 + 50 + 30 != 40 * 50 * 30`). SY:109 itself says "(or other non-symmetric pair)".
~2.2 pts deflated on each file. This is the only true FN in either sample.
(Other misses verified correct: `hypothesis_basic` — no `@given`; MM `in_notin`/`caplog`/
`h3`/`type_e`/`type_g` — genuinely absent.)

**9. `type_f_roundtrip` — scored nowhere; yaml contract unmet.**
Now `llm_only` (SY:237) so the denominator is right, but there is no juez-LLM path in the
code (SS:856-859: unknown/llm_only → `hit=False`, silently skipped). SY:9-11 promises
"scored via the juez LLM". The surface is now simply unscoreable rather than mis-scored —
impact 0, contract still broken.

## C. Checker bugs still present (all probe-verified)

**10. `h19_unit_only` (SS:405-409) is still `return True`.** `evaluate()` (SS:821-875) never
inspects the file path. Every submission gets +2.2 pts free, including files under
`tests/integration/`. Unchanged from v1 4.3.

**11. `no_loose_none` still over-penalizes (v1 1.7).** SY:252 says "as **sole** assertion";
SS:512-523 flags *any* `is not None`. Probe P4: test with `assert x is not None` **and**
`assert x == 5` → penalty fires (−10). No penalty in the two samples, bug live.

**12. `in_notin` is `or`, surface requires both.** SS:627 `return has_in or has_notin` vs
SY:43 "positive and negative membership". Probe P5: `not in` alone hits.

**13. `typed_exception` credits bare substring match.** SS:237-239 accepts any `match=` kwarg;
SY:134 requires `re.escape(...)`. Probe P9: `match="must be"` hits. A partial-substring
matcher does not kill the XXwrap/message mutants the surface targets.

**14. `h6_fallback`/`type_d` use OR and a vacuous `has_fallback`.** SS:315
`has_side_effect or has_fallback`; `has_fallback` = any `== 'str'` assert >3 chars.
Probe P10: one `assert x.status == "Rejected by policy engine"` with no side_effect anywhere
credits **five** surfaces at once (`h6_fallback`, `type_d_unreachable`, `h14_xxwrap`,
`exact_string`, `string_xxwrap`). Both samples have real H6 tests, so scores are right.

**15. `default_kwarg`/`default_mutation`/`h18` cross-test contamination + fixture coupling.**
`_has_default_observation` (SS:141-152) scans the whole file: probe P12 — `apply(...)` without
timeout that observes nothing + an unrelated `assert 600 == 600` in another test → all three
surfaces hit. Also hardcodes this fixture's names/values (`apply`→600, `normalize`→10).

**16. Numeric surfaces polluted by non-test helpers (v1 4.7 persists).**
SS:559-562/584-587/671-673 collect numbers from *all* FunctionDefs (helpers included).
Probe P13: helper defaults `threshold=50, limit=99` + two `len==` asserts → `num_boundary`,
`cmp_boundary`, `arith_accumulator`, `h11_limit`, `type_b_public_limit` all hit with zero
boundary/accumulator testing. `h11_limit`/`type_b` also hardcode the literal 50 (SS:367).

**17. `h10_cache` still name + call-count only.** SS:347-360: function named `*second*`/
`*cache*` with ≥2 `apply`/`emit` calls and a vacuous body (probe P11: `assert 1 == 1`) hits.
Improved over v1 (body is now counted), still no evidence of the no-re-emit *assertion*.

**18. `h1_wiring` and `spy_complete` triggers decoupled from real spy evidence.**
Probe P7c: a single `assert x is None` + the word "sink" in the dump → `h1_wiring`.
Probe P7b: one field of one call via alias → `spy_complete`/`kwargs_passthrough`.
Plus the O(n²) nested `ast.walk` in SS:120-123 and 467-472.

**19. `no_mock_iterable` still constructor-only (v1 gap 7) + `h20` half-dead.**
SS:712-721 only matches `MagicMock(records=|items=|inputs=)`; the actual H17 idiom
`records = MagicMock(); apply(records, ...)` is invisible. SS:420: `has_mangled` computed,
never used — the `'XXkeyXX' not in path_map` half of SY:205 is uncheckable (v1 4.4).

**20. No SUT-signature cross-check (v1 4.10).** The evaluator parses only the test file, so
impossible calls (finding 1) and name-claimed coverage (MM:233 "logger" test asserting sink
args — correctly missed on `caplog_exact` only by absence) can never be caught. Design
limitation with direct scoring consequences.

## D. Missing surfaces from MUTANT_KILLING_GUIDE (all v1 §3 gaps — none added)

Verified absent from surfaces.yaml (no H5/H9/capsys/`!=`/chdir entries):
- **H5 over-mocked orchestrator** (forbidden): `mock.patch("quota_broker.apply")` / patching
  SUT internals still scores ~100 with zero signal.
- **H9 / Tipo I** timeout loop-exit mutants: no surface.
- **§4.3 `capsys`** full-line stdout comparison: no surface.
- **§2 `==`↔`!=`**: `cmp_boundary` covers only ordering flips.
- **Forbidden: bare `assert_called()`/`assert_called_once()`** as sole spy evidence — MM:204
  does exactly this (entire "default timeout" test evidence) with no penalty.
- **Forbidden: `monkeypatch.chdir` in unit tests** (H13): no surface.

## Score impact

| | reported | true FPs | true FNs | substantively |
|---|---|---|---|---|
| DeepSeek | 96 (43/45) | 0 (3 coincidental-mechanism hits: exact_boundary, spy_complete, h6) | 1 (accumulator_asymmetric) | 44/45 ≈ **98** — under-scored ~2 pts |
| MiMo | 73 (33/45) | 1 (h20) + 1 borderline (type_c) | 1 (accumulator_asymmetric) | 32/45 ≈ **71** — over-scored ~2 pts |

v1's biggest MiMo FPs (type_e, type_g, h18, default_mutation) are fixed and now correctly
missed; the residual over-scoring is concentrated in `h20` (broken test invisible to a
file-only AST scorer) and `type_c` (name-only trigger). The single systemic under-scoring
remaining is the hardcoded 3/5 in `accumulator_asymmetric`. Highest-value fixes, in order:
(1) value-agnostic `accumulator_asymmetric`; (2) signature cross-check against the stub or
at least a kwarg-against-API lint (kills finding 1); (3) implement or delete `h19` path
check; (4) scope `h2`/`h8`/`default_kwarg`/`break_count` evidence to the relevant test
function and the relevant mock.

## Probe appendix (all executed against current code)

- P1: docstring + `len==0/1/2` only → `exact_boundary`, `h8_stop_count`, `break_count` ✅ (bug 4/6)
- P2: three distinct literals only → `num_boundary`, `cmp_boundary` ✅ (bug 16)
- P3: TT/FF-only fn + unrelated `True` → `truth_table`, `h4_truth_table`, `bool_and_or` ✅ (bug 7)
- P4: `is not None` + real assert → `no_loose_none` penalty ✅ (bug 11)
- P5: `not in` only → `in_notin` ✅ (bug 12)
- P6: `m.other.call_count == 1`, no clock → `h2_clock` + `h8_stop_count` ✅ (bug 6)
- P7b: `c.key` via alias + `sink.calls[0]` → `spy_complete` + `kwargs_passthrough` ✅ (bug 5/18)
- P7c: `is None` + word "sink" → `h1_wiring` ✅ (bug 18)
- P8: `def test_missing_key_something(): assert 1 == 1` → `type_c_absent_key` ✅ (bug 2)
- P9: `match="must be"` (no re.escape) → `typed_exception` ✅ (bug 13)
- P10: one string `==` assert, no side_effect → `h6_fallback`+`type_d`+`h14`+`exact_string`+`string_xxwrap` ✅ (bug 14)
- P11: `test_no_reemit_on_second_apply` + 2 calls + `assert 1==1` → `h10_cache` ✅ (bug 17)
- P12: no-kwarg call + `600` in unrelated test → `default_kwarg`+`default_mutation`+`h18` ✅ (bug 15)
- P13: helper defaults 50/99 + counts → `num_boundary`+`cmp_boundary`+`arith_accumulator`+`h11_limit`+`type_b` ✅ (bug 16)
