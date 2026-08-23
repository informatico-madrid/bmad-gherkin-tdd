# Adversarial review — `static_score.py` (TDD RED bench evaluator)

Date: 2026-08-23
Reviewed files:
- Evaluator: `agent_bench/red/eval/static_score.py` (897 lines)
- Surfaces: `agent_bench/red/eval/surfaces.yaml` (272 lines, 51 surfaces: 46 scored + 5 forbidden)
- Sample A: `_bmad-output/agent-bench/runs/20260823-005100/nan__deepseek-v4-flash/tests/unit/test_red_hard.py` (reported 89/100)
- Sample B: `_bmad-output/agent-bench/runs/20260823-011004/nan__mimo-v2.5/tests/unit/test_red_hard.py` (reported 74/100)
- Ground truth consulted: `MUTANT_KILLING_GUIDE/` (guide 2, 4, 5, 0; H1–H21), `fixtures/red-hard/src/quota_broker.py` (stub), `fixtures/red-hard/tests/contracts/red-hard.feature`, `PRODUCT-INTENT.md`

Method: re-ran the evaluator (scores reproduce exactly: 89 and 74), then instrumented every disputed checker against the real ASTs and against synthetic minimal files. All "verified" claims below were executed, not inferred.

Line numbers: `SS:n` = static_score.py, `SY:n` = surfaces.yaml, `DS:n` / `MM:n` = the DeepSeek / MiMo test files, `STUB:n` = fixture stub.

---

## 1. FALSE POSITIVES (surface = hit, mutant class NOT actually covered)

### 1.1 MiMo: `default_mutation` + `h18_default_no_kwarg` (2 surfaces, ~4.3 pts) — TRUE FP
`MM:194-205` (`test_apply_callable_without_timeout_kwarg`) calls `apply([rec], spec, sink, clock)` without `timeout` but **never observes the default**. The only "600" tokens in the whole file are a docstring (`MM:195`) and a comment (`MM:203`) — zero assertions on the value. The guide is explicit (H18, §4.5): the kill requires calling *without* the kwarg **and observing the default's effect** ("llama omitiendo el argumento y observa un efecto del valor por defecto"). `timeout: float = 600.0 → 601.0` (`STUB:27`) survives MiMo's suite. The checker (SS:148-158) fires on the bare call shape alone — verified with a synthetic file (`apply(...)` + `assert len(result) == 1`, no 600 anywhere) → still True.
Contrast: DeepSeek does it right (`DS:253` `assert sink.calls[0].timeout == 600`).

### 1.2 MiMo: `type_e_timeout_spy` (~2.2 pts) — TRUE FP
The surface is "spy observes timeout value" (`SY:228-231`). MiMo has no assertion on any timeout value. The checker's branch 1 (SS:442-447, `assert_called_once_with(..., timeout=...)`) is False for MiMo; the hit comes from branch 2 (SS:449-451): `"timeout" in src and "==" in src and ("calls" in src or "sink" in src)`. Verified: "timeout" comes from the *function name* `test_apply_callable_without_timeout_kwarg`, "==" comes from the *docstring prose* at `MM:286` (`"recognized via `is` not `==`"`) — `ast.dump` renders real `Eq()` operators as `Eq()`, so a literal `"=="` in the dump can only ever come from a string constant. The hit is 100% prose coincidence; the timeout mutant survives.

### 1.3 MiMo: `type_g_sentinel` (~2.2 pts) — TRUE FP
Fired purely by the substring "sentinel" in the test name (SS:472-474, `MM:285` `test_skip_sentinel_is_recognized_via_is_not_eq`). The Type G kill requires a decoy object whose `__eq__` says "yes" while `is` says "no" (guide §5 Tipo G). MiMo feeds only `kind=SKIP` and plain string kinds, plus `fake_skip = object()` with `assert fake_skip is not SKIP` (`MM:301-303`) — which is a tautology about `object()`, not a test of the SUT's operator. Under the `is SKIP → == SKIP` mutation, `SKIP == SKIP` is True (identity fallback of `object()`), the record is still skipped, and all three assertions (`MM:296-298`) still pass → mutant survives. DeepSeek has the real kill (`DS:88-90` `EqualToSentinel.__eq__`, `DS:347` decoy record, `DS:353-356` assertions).

### 1.4 MiMo: `h20_pathmap` (~2.2 pts) — TRUE FP (malformed test, invisible to the evaluator)
`MM:315` calls `apply([rec], spec, sink, clock, path_map=path_map)`. The SUT signature (`STUB:21-28`) is `apply(records, spec, sink, clock, *, timeout)` — **there is no `path_map` parameter**. This call raises `TypeError: apply() got an unexpected keyword argument 'path_map'` at call-binding time, against the stub *and* against any correct implementation, so `MM:317` (`accepted[0] is rec`) can never run. The path_map identity behavior is not actually covered. The evaluator awards the hit via per-node substrings "None" + "path_map" (SS:399-402) because it never cross-checks the test's calls against the SUT signature (design limitation — the stub is never consulted). DeepSeek does it correctly via a spec field (`DS:360` `make_spec(path_map={"keep": None})`).

### 1.5 MiMo: `type_c_absent_key` (~2.2 pts) — BORDERLINE FP
Fired by "missing" in the test name (SS:427-429, `MM:319`). The body only asserts *counts* (`MM:329-330`: `len(accepted) == 1`, `len(rejected) == 0`) and never pins which default path/kind was taken. A Tipo C default-value mutation that changes the emitted kind without changing accept/reject survives. DeepSeek pins the full tuple (`DS:383-387`) and additionally asserts the key is truly absent (`DS:378` `not hasattr(spec, "extra_key")`).

### 1.6 Both files — hits that fired for the WRONG reason (result happens to be right here; mechanism is broken)
- `exact_boundary`: the triple that fires for both files is **`(False, True, 2)`** — booleans plus the literal 2 — not any threshold boundary. See bug 4.1. Both files genuinely test 3/7/50/51/99, so no score change here, but the surface is crediting `assert len(x) == 2` + any boolean code.
- `spy_complete` (DeepSeek): branch 1 False (the file contains **no** `assert_called_once_with` at all); hit via branch 2 (SS:143) `"calls" in src and "is " in src` — "is " matched inside the module *docstring* ("The SUT is a hollow stub", `DS:12`). Verified FP on a synthetic docstring-only file.
- `h6_fallback` (both): fired by the substring "fallback" inside `normalize(None, fallback=10)` asserts (`DS:233`, `MM:184/188/192`) — not by the actual SinkError-fallback test. A file testing only `normalize(fallback=...)` with no error-fallback coverage would score h6. (Both files do have real H6 tests — `DS:390-401`, `MM:332-344` — so the score is right, the mechanism is a coincidence.)
- `h8_stop_count` (MiMo): fired on unrelated `len(accepted) == 1` / `len(rejected) == 1` asserts in *other* tests (`MM:138, 316, 329, 343`), not on the stop_on_first test, which uses `sink.emit.call_count == 1` (`MM:113`) — a pattern the checker cannot see (bug 4.7). Remove the other tests and the surface flips to miss despite real coverage.
- `h11_limit` / `type_b_public_limit` (MiMo): the literal 50 that triggers also appears as a *weight* (`MM:67` `weight=50`); coincidentally MiMo also tests score=50 at the boundary, but a file using 50 only as incidental data would hit.

### 1.7 Penalty false-positives (over-penalization)
- `no_loose_none` (SS:493-504): description says penalty "as **sole** assertion" (SY:249-252), but the checker flags *any* `is not None` assert. Verified: a test with `assert x is not None` **and** `assert x == 5` still returns True (−10 pts) despite the non-None check not being the sole assertion.

---

## 2. FALSE NEGATIVES (surface = missed, mutant class IS covered)

### 2.1 Both files: `truth_table` + `h4_truth_table` (2 surfaces each, ~4.3 pts each)
Both files contain a **complete 4-combination truth table (TT/TV/FT/FF) with one assertion per combination** — exactly the feature's own style ("each Then maps to exactly one assertion about a specific combination", feature line 37):
- DeepSeek `DS:197-213`: four records, `len(sink.calls) == 1`, `calls[0].record is tt`, and one `not in` per rejected combo.
- MiMo `MM:123-154`: four records, set-equality on rejected keys, plus four per-combination `any(...)` asserts.

The checker requires **≥2 test functions** each containing both `True` and `False` (SS:193-202). Verified: in both files exactly ONE test function matches (`test_s1_active_visible_truth_table_one_assertion_per_combination` / `test_active_visible_truth_table`), so the count is 1 → miss. A single function carrying the full table (or a parametrized test, which is one function) is a canonical, legitimate way to write §4.8. This is the largest systematic deflation in the scorer: 4 lost surface-credits across the two samples.

### 2.2 Both files: `accumulator_asymmetric` (~2.2 pts each)
The checker hardcodes the literals **3 and 5** (SS:173), but the yaml's own ast_hint says "numeric literals 3 and 5 **(or other non-symmetric pair)**" (SY:109) and the guide says "valores asimétricos: `2+2 == 2*2`; con 3 y 5 no hay empate" (guide 4, §4.6) — 3/5 is an *example*, not the pattern.
- DeepSeek `DS:152-167`: `assert results.total_weight == 200` from weights 50/51/99 — kills `+=→=`, `+→*`, `+→-`. No literal 5 exists anywhere in the file → miss.
- MiMo `MM:91-93`: `assert total_weight == 120  # 40 + 50 + 30` plus the explicit asymmetry guard `assert 40 + 50 + 30 != 40 * 50 * 30` → miss.

### 2.3 MiMo: `h2_clock` (~2.2 pts)
`MM:261` `assert clock.now.call_count == 1` is verbatim the feature's Then ("clock.now() was called exactly once") and kills extra/removed `clock.now()` calls. The checker only recognizes a literal `.now()` *call*, `now_count`/`now_values` attributes, or a dead third branch (SS:270-281) — it does not recognize the MagicMock idiom `clock.now.call_count` / `.call_args`. DeepSeek's equivalent uses custom attributes (`DS:310-311` `now_count`/`now_values`) and scores; MiMo's equivalent is missed. Same test quality, opposite verdict.

### 2.4 Both files: `type_f_roundtrip` — unattainable surface
The checker is hardcoded `return False` (SS:456-457, comment "too specific for generic AST check") and the surface is **not** marked `llm_only`, so it is in the denominator for every file (SS:843-845). Every submission permanently loses ~2.17 pts on a surface it cannot score. Neither file actually exercises an internal write+read string-key roundtrip (the fixture has no such contract in the feature), so this is less a "missed credit" than a structural defect — reported here because it uniformly deflates all scores.

### 2.5 MiMo: `dense_assertions` — BORDERLINE FN
`MM:144` `assert rejected_keys == {"tf", "ft", "ff"}` (full set equality) and `MM:78/82/87` (full list equalities) are not counted because the checker accepts only `Call`/`Dict` comparators (SS:93) — not `Tuple` or `Set` (verified: `assert (a, b, c) == (1, 2, 3)` → False). MiMo's file is genuinely mostly field-by-field, so the miss is defensible, but the Tuple blind spot directly contradicts DeepSeek, whose canonical dense asserts *are* tuples (`DS:271-275`, `DS:383-387`) and which only scores because of an unrelated `sorted(...)` Call comparator at `DS:146-148`.

---

## 3. GAPS — mutant classes in MUTANT_KILLING_GUIDE with no surface in surfaces.yaml

1. **H5 — over-mocked orchestrator** ("mutantes DENTRO de lo mockeado jamás mueren"; mock de `_run_*` colaborador → supervivencia silenciosa). PRODUCT-INTENT names "Mock del kernel entero" as hollow form #1 of the three historical failure modes. No surface or forbidden detects `mock.patch("quota_broker.apply")` / patching SUT internals. An agent that mocks the SUT itself would score near-100 on the other surfaces and get zero signal on this one.
2. **H9 / Tipo I — ⏰ timeout mutants** (mutation creates an infinite loop; kill requires a *fast, specific boundary test of the loop-exit condition*). No surface. Related: the 🤔 suspicious/flaky class (cache-clear fixtures, `lru_cache` between tests) also has no surface.
3. **§4.3 `capsys`** — guide 4 names "stdout/stderr: `capsys` y comparar la línea completa" as a first-class exact-string technique. No surface, no checker.
4. **§2 `==` ↔ `!=`** — the Comparison row of guide 2 lists `<↔<=, >↔>=, ==↔!=`. `cmp_boundary` (SY:25-28) covers only the ordering pair. The equality-flip mutant needs an assert on *both* sides of the equality (a value that matches and one that doesn't, each pinned) — no surface pins that explicitly.
5. **Forbidden: bare `assert_called()` / `assert_called_once()` without full args** — guide 4 §4.4: "**Asersión de la llamada completa, nunca `assert_called()`.**" MiMo does exactly this at `MM:204` as the *entire* spy evidence of its default-timeout test, and receives no penalty. There is no forbidden surface for it.
6. **Forbidden: `monkeypatch.chdir` in unit tests** — H13 declares it prohibited in this repo (breaks mutmut stats). Statically detectable (Attribute access `chdir` on `monkeypatch`); no surface.
7. **H17 (`no_mock_iterable`) is too narrow to catch the actual H17 pattern** — the checker (SS:684-693) only matches `MagicMock(records=…|items=…|inputs=…)`, i.e., the *constructor call site*. The real H17 poison (guide: "mockear el **input** con un `MagicMock`") is `records = MagicMock()` … `apply(records, …)` — a variable assignment the checker cannot see. Both samples mock *collaborators* (sink/clock), which is legitimate, so no scoring harm here, but the forbidden as written does not implement the guide it cites.
8. Considered and judged **correctly absent** (process-level, not test-content surfaces): H12 (debugging your own tests), H13 as a *runtime* phenomenon (but see gap 6 for its test-authoring rule), H16 (SIGXCPU flake triage), H21 (refactor-smell taxonomy), Tipo J (genuine case-insensitive equivalents — a "do NOT test, refactor or pragma" triage decision, which a coverage scorer should not credit either way).

---

## 4. CHECKER BUGS (AST patterns that give wrong results on edge cases)

### 4.1 Booleans counted as integers (systemic, highest-impact)
`_collect_numbers` (SS:50-56) accepts `bool` because `isinstance(True, int)` is True. Verified: `sorted(set([False, True, 2])) == [False, True, 2]` and the consecutive-triple scan returns True on it.
- `_check_exact_boundary` (SS:98-109, no value filter at all): fires for **both** sample files on `(False, True, 2)` — i.e., *any* file containing `True`, `False` and the literal `2` (or any adjacent pair plus a bool) hits, with no boundary testing. The actual 49/50/51-style triples are never the trigger.
- `_check_num_boundary` (SS:539): filter is `n != 0`, which drops `False` but **not** `True` (=1) → bool pollution.
- `_check_cmp_boundary` (SS:563): filter `n > 0` → `True` leaks in.
Fix: `isinstance(child.value, (int, float)) and not isinstance(child.value, bool)`.

### 4.2 Substring conditions on `ast.dump` that can never match real syntax (dead or accidental)
`ast.dump` renders operators as class names (`Eq()`, `In()`, `Is()`) and names as `Name(id='x')`. Verified: `ast.dump(ast.parse("assert a == b"))` contains no `==`.
- **`_forbid_loose_in` (SS:512)** — `"in str(" in src`: `x in str(y)` dumps as `ops=[In()], comparators=[Call(func=Name(id='str')…` — the substring `"in str("` can only ever come from prose in a string literal. Verified on the exact target pattern `assert "k" in str(result)` → returns **False**. The penalty can never fire.
- **`_forbid_len_gt` (SS:522)** — `"len(" in src`: `len(x)` dumps as `Name(id='len')` — no `"len("`. Verified on `assert len(x) > 0` → returns **False**. The penalty can never fire.
- **`_check_type_e` branch 2 (SS:450)** — `"==" in src`: only ever true because a *docstring/string literal* contains `==` (DeepSeek `DS:9`, MiMo `MM:286`). Real `timeout == 600` spy comparisons never contribute. Both samples' `type_e` hits are prose accidents (see 1.2).
- **`_check_h15_none_vs_falsy` (SS:378, 380)** — `"==" in src` is dead for the same reason, so the zero/false branches silently degrade to: `"0" in src and "normalize" in src`. Two consequences, both verified: (a) the checker is **hardwired to this fixture's function name** `normalize` — in any other feature `has_zero`/`has_false` can never be True; (b) `"0"` is a substring of `10`, `50`, `600`, `1700000000` — a file that never uses 0 as an input still gets `has_zero` (verified: `normalize(50, …)` + `normalize(None, …)` + `normalize(False, …)` → True).

### 4.3 Vacuous surfaces
- **`_check_h19_unit_only` (SS:390-392)**: `return True` with the comment "checked by file path in scorer" — no such check exists anywhere; `evaluate()` (SS:793-847) never inspects the path. A test file under `tests/integration/` scores the h19 credit. +2.17 pts guaranteed for every submission.
- **`_check_type_f_roundtrip` (SS:456-457)**: `return False` — see 2.4.
- The yaml header (SY:9-11) promises that surfaces without AST predicates are "scored via the juez LLM (marked `llm_only: true`)". The code has **no LLM path**: unknown ids get `hit=False` (SS:828-831) and still count in the denominator (SS:843-845). Any future `llm_only` surface would silently deflate every score by 2.17 pts with no judge ever running.

### 4.4 Dead code / unreachable branches
- `_check_h2_clock` (SS:277-280): `left = node.test.left if isinstance(node, ast.Assert) else node.left` inside a loop whose branch condition is `isinstance(node, ast.Compare)` — the `ast.Assert` side is unreachable; the whole third branch is redundant with the attribute check at SS:275.
- `_check_h20_pathmap` (SS:403-405): `has_mangled` is computed and **never used** — the surface's second half (`'XXkeyXX' not in path_map`, SY:205) is uncheckable as written; the comment even admits "partial".
- `_is_assert_call` (SS:68-74) and `_iter_compare_ops` (SS:124-126): defined, never called (verified by occurrence count).

### 4.5 Wrong-idiom blindness (misses the standard MagicMock patterns)
- **`_check_h2_clock` (SS:270-281)**: misses `clock.now.call_count` / `.call_args` (see 2.3).
- **`_check_h8_stop_count` (SS:320-331)**: only matches `len(...) == 1`; misses `x.call_count == 1`. Verified misattribution on MiMo (fired on `len(accepted) == 1` in unrelated tests, 1.6).
- **`_check_h6_fallback` (SS:298-305)**: `has_side_effect` only matches `side_effect` as a `ast.keyword` *inside a Call* — the ubiquitous idiom `mock.attr.side_effect = X` (an `Assign`, MiMo's actual pattern at `MM:336`) is invisible. So the fallback surface is simultaneously FP-prone (the "fallback" kwarg substring, 1.6) and FN-prone (the Assign idiom).
- **`_check_break_count` (SS:180-190)**: matches *any* `len(x) == int`, including input-side counts (verified: `assert len(records) == 5` → True). An assert about the *input* list size says nothing about iteration count.

### 4.6 Over-loose structural triggers (name/prose only)
- **`_check_spy_complete` (SS:143)**: `"calls" in src and "is " in src` — `"is "` matches English prose in any docstring; `"calls"` matches any mention of a `calls` attribute. Verified FP on a synthetic file whose only content is a docstring ("This is a smoke test of the sink calls"), one `sink.calls` comparison, and one `x is x`. DeepSeek's hit is exactly this (1.6).
- **`_check_h1_wiring` (SS:256-265)**: one `is` comparison *anywhere in the file* (including helper code or tautologies like `MM:302`) + the dump containing "calls"/"sink"/"spy" → hit. A file whose only spy evidence is a bare `assert_called()` still scores h1.
- **`_check_h10_cache` (SS:340)**: a function *named* `test_second_*` or `test_*cache*` hits with zero body inspection (verified: `def test_second_thing(): assert 1 == 1` → True). The second branch (`"apply" in src and src.count("apply") >= 2`) is fixture-name-coupled and fires on *any* double call, including two unrelated `apply` invocations.
- **`_check_type_c` (SS:427-429)**: "absent"/"missing" in the test name hits with no body requirement (see 1.5).
- **`_check_h7_argv_order` (SS:310-317)**: any `assert x == [a, b]` / `== (a, b)` hits — including `sorted(x) == [...]`, which *cannot* kill an order mutant (verified: `assert sorted(keys) == ['a', 'b']` → True). Order is only real when the LHS is an unsorted extraction.
- **`_check_default_kwarg` (SS:148-158)**: see 1.1 — fires with no downstream observation; also hardcodes the SUT's function names `apply`/`normalize` (as does `type_c` SS:421 and the `50` in `h11_limit` SS:351). The module docstring (SS:1-7) presents this as a generic "TDD RED bench" scorer, but at least four checkers are coupled to this one fixture's names/values.

### 4.7 Helper-function pollution of numeric/boolean surfaces
`_check_exact_boundary`, `_check_num_boundary`, `_check_cmp_boundary`, `_check_arith_accumulator` collect numbers from **all** `FunctionDef`s (SS:100-103, 535-538, 559-562, 647-650) — including non-test helpers. Fixture data like `make_spec(threshold=50)` (`DS:46-53`) or `_record(weight=1)` / `_spec(threshold=50)` defaults (`MM:30-35`), and even `RecordingClock`'s counter (`DS:83`), feed the "boundary/accumulator" evidence. Verified: a file containing only two helpers with numeric defaults plus `assert len(items) == 3` hits `num_boundary` with zero boundary testing. Boolean defaults in helper signatures (`active: bool = True, visible: bool = True`) likewise feed `bool_not`/`bool_and_or` (SS:584-590 scans the whole module for `True`/`False` constants — a single helper default plus one literal `False` anywhere hits).

### 4.8 `dense_assertions` comparator whitelist is both too narrow and too loose
(SS:87-95.) Accepts only `Call`/`Dict` comparators:
- Misses `Tuple` and `Set` — the exact shapes DeepSeek's canonical dense asserts use (`DS:271-275`, `DS:383-387`) and MiMo's set equality (`MM:144`). Verified False on `assert (a, b, c) == (1, 2, 3)`.
- Accepts *any* Call comparator — e.g., `sorted(...)` (see 4.6), a shape that is structurally unable to kill order mutants.

### 4.9 Forbidden-check mismatches with the cited rules
- `no_loose_none` over-penalizes (1.7) — "sole assertion" is in the surface description (SY:252) but not in the code.
- `no_sample_leak` (SS:673-681) matches whole literals only (`s.lower() in {"alpha","beta","quota-lab"}`); the guide's canonical check is a *substring* grep (`grep -ril "alpha\|beta\|quota-lab"` per PRODUCT-INTENT line 16). Verified: `assert result.key == "alpha_beta"` escapes the penalty.
- `no_mock_iterable` — see gap 7.

### 4.10 No cross-file signature validation (design limit with scoring consequences)
The evaluator parses only the test file. It cannot detect that MiMo's `apply(..., path_map=path_map)` (`MM:315`) is an impossible call against the stub (`STUB:21-28`), yet it credits `h20_pathmap` (1.4). Similarly it cannot detect that MiMo's "logger exact message" test (`MM:233-248`) asserts on the *sink's* args while its name claims log coverage — that one is correctly missed on `caplog_exact` only because no caplog appears.

---

## 5. Score impact

| | reported | true FPs | true FNs | substantively |
|---|---|---|---|---|
| DeepSeek | 89 (41/46) | 0 (but 5 coincidental-mechanism hits: exact_boundary, spy_complete, h6, type_e, h8-analog) | truth_table, h4_truth_table, accumulator_asymmetric | ~44/46 ≈ **96** — under-scored by ~7 pts |
| MiMo | 74 (34/46) | default_mutation, h18_default_no_kwarg, type_e_timeout_spy, type_g_sentinel, h20_pathmap (+borderline type_c) | h2_clock, truth_table, h4_truth_table, accumulator_asymmetric | ~33/46 ≈ **72** — over-scored by ~2 pts |
| both | — | — | type_f_roundtrip (unattainable, hardcoded False) | every file permanently −2.17 pts |

The headroom in both directions also means the *profile* is wrong even where the total is close: MiMo is credited for surfaces it does not cover (timeout default, sentinel, path_map) and penalized for surfaces it does (clock, truth table, accumulation), so per-surface diagnostics — the point of a surface matrix — are unreliable.

Correct misses (no action needed, listed for completeness): `hypothesis_basic` (both — no `@given`), `caplog_exact`/`h3_log`/`type_h_log_msg` (MiMo — no caplog; the "log" test asserts sink args instead), `in_notin`/`in_is_membership` (MiMo — no membership asserts at all).

## 6. Recommended fixes (priority order)

1. Fix `_collect_numbers` to exclude `bool` (4.1) — one line, removes the most pervasive false signal.
2. Replace dump-substring heuristics with real AST structure: match `In` on a `Call(func=Name('str'))` for `no_loose_in`; `Call(func=Name('len'))` with `Gt/GtE` for `no_len_gt`; `Eq`/`Is` operators instead of `"=="`/`"is "` substrings (4.2, 4.6). All three forbidden/surface pairs are one-pattern rewrites.
3. Make `accumulator_asymmetric` value-agnostic (any ≥2 asymmetric non-unit values in an accumulation-assertion context), make `truth_table`/`h4` combination-aware (count distinct (bool,bool) input pairs per function, accept one function with ≥4 combos or two functions with ≥2 combos each) (2.1, 2.2).
4. Teach `h2`/`h8` the MagicMock idioms (`.call_count`, `.call_args`) (2.3, 4.5).
5. Implement or remove `h19` path check and `type_f`; if `type_f` stays, mark it `llm_only` and implement the documented llm_only flow so such surfaces don't sit in the AST denominator (4.3).
6. Add the missing surfaces from §3: H5 over-mock forbidden, H9/Type I, capsys, `==↔!=` pin, bare-`assert_called()` forbidden, `monkeypatch.chdir` forbidden; widen `no_mock_iterable` to the assignment idiom (3).
7. Add a call-signature cross-check against the stub (or at least the fixture's declared API) to catch `apply(path_map=...)`-class broken tests (1.4, 4.10).
8. Delete dead code: `_is_assert_call`, `_iter_compare_ops`, the `_check_h2_clock` third branch, `has_mangled` (4.4).
