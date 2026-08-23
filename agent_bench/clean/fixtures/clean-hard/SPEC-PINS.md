# SPEC-PINS — Semantic pins for green-hard

Every pin is **observable in the SUT** (return value, spy, log, stdout, exception).
No pin is "the test sums 3+5 locally". All assertions below are against the golden impl.

## P1 — Threshold inclusivity
`record.score >= spec.threshold` → accept. 50 ≥ 50 → accept.
Mutant `>` vs `>=`: pin 1 uses score=50 at threshold=50.

## P2 — Truth table (1st compound)
`record.active and record.visible` — TT accept, TF/FT/FF reject.
Each Then maps to one assertion about one combination.
Mutant `and`↔`or`: all 4 combos must be tested independently.

## P3 — stop_on_first
After the first accept, no more records are processed.
Mutant `break`↔`continue`: assert `len(sink.calls) == 1` (H8).

## P4 — Return shape
`(accepted: tuple, rejected: tuple, total_weight: int)`
Mutant `return None` / `return x`: full structural equality.

## P5 — Object identity
Records in accepted/rejected are the same objects (`is`, not copy).
Mutant clone: `accepted[0] is record` for each.

## P6 — sink.emit wiring
`emit(kind, record.key, str(score), *, timeout=...)`
Only accepted records are emitted. Exact argv order (H7).
Mutant reorder argv: pin order of args.

## P7 — Default timeout (H18)
Call `apply(...)` WITHOUT `timeout=` kwarg.
Observe `timeout=600` in `sink.calls[0].timeout`.
Mutant `600→601`: assert value downstream.

## P8 — normalize falsy (H15)
Separate calls: `normalize(None, fallback=10) → 10`, `normalize(0) → 0`, `normalize(False) → 0`.
Mutant collapse falsy: three independent assertions.

## P9 — Empty/None records
`apply([], ...)` → `ValueError("records must not be empty")`
`apply(None, ...)` → same ValueError.
Exact string message via `match=re.escape(...)`.
Mutant XX-wrap: exact string comparison.

## P10 — Accumulator asymmetric (§4.6)
`total_weight` is the SUT's sum of `record.weight` for accepted records.
Use weights 3 and 5: `result[2] == 8` and `result[2] != 15`.
Mutant `+`↔`*`: asymmetric values break commutativity.

## P11 — Clock once (H2)
`clock.now()` called exactly once per `apply()` call (not per record).
Mutant extra call: `clock.now_count == 1`.

## P12 — Cache (H10)
Second `apply()` with the same `record.key` does NOT re-emit to sink.
Different key DOES emit. (H10b: cache is per-key, not global.)
Mutant no-cache: assert sink call count unchanged on 2nd call.

## P13 — SKIP sentinel (Tipo G)
`record.kind is SKIP` (identity, not equality).
Decoy: object with `__eq__` returning True — still not SKIP via `is`.
Mutant `is`↔`==`: decoy would be accepted under `==`.

## P14 — path_map remaps emit key (H20)
`path_map[rec.key] is None` → emit uses original key.
`path_map[rec.key] == "alias"` → emit key is `"alias"`.
Deleting the path_map block fails the remap assertion.

## P15 — extra_key filters rec.tag (Tipo C)
Absent `extra_key` → no tag filter (default path).
Present `extra_key="vip"` → only `rec.tag == "vip"` accepted.

## P16 — SinkError fallback (H6)
`sink.emit` raises `SinkError("no-slot")` → record goes to rejected.
Exact error message preserved in fallback.
Mutant swallow error: SinkError, not generic Exception.

## P16b — TypeError NOT swallowed
If sink raises `TypeError` (not `SinkError`), it propagates.
Mutant swallow: only SinkError triggers fallback.

## P17 — Log exact (H3)
Logger records `"accepted {key} score={score}"` with exact format.
`caplog.messages[0] == "accepted mid_77 score=77"`.
Mutant substring: `==` not `in`.

## P18 — capsys exact (§4.3)
Stdout contains exactly one line per dispatch: `"dispatch {key} {kind}"`.
Full line equality, not substring.

## P19 — max_emit loop bound (H9)
`spec.max_emit = 2` → after 2 emits, loop stops even if more records qualify.
Mutant timeout/infinite: fast boundary (3 qualifies, emit only 2).

## P20 — Trace roundtrip (Tipo F)
`apply` writes `record.trace_id` (internal side-effect).
Second read of same record returns same `trace_id`.
Mutant write-only: assert roundtrip.

## P21 — 2nd compound (or) is a hard gate
Applied only when spec has `mode` or `flag`.
Accept iff `mode=="strict" or flag`. FF (relaxed + False) is rejected.
`or`→`and` fails TF (strict, flag=False).

## P22 — Public limit (H11 / Tipo B)
Call API at boundary that "should not pass" — still works.
Mutant unreachable: exact boundary value pin.

## P23 — Cache isolation (H10b)
Key `A` cached; key `B` still emits. Cache is per-key.
Mutant global cache: second key triggers emit.

## P24 — FIXTURE≠TARGET
No `alpha`/`beta`/`quota-lab` as expected values in assertions.
Values derive from contract, not sample labels.
