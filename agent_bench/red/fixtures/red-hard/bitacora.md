# Bitácora TDD — red-hard-001

| @s | Fase | Status | Test file |
|----|------|--------|-----------|
| @s1 | RED | ROJO | tests/unit/test_red_hard.py (test_s1_accept_above_reject_below_boundary_strict_threshold) |
| @s2 | RED | ROJO | tests/unit/test_red_hard.py (test_s2_empty_and_none_records_raise_valueerror, test_s2_normalize_none_zero_false_edge_cases, test_s2_apply_callable_without_timeout_kwarg) |
| @s3 | RED | ROJO | tests/unit/test_red_hard.py (test_s3_wiring_log_clock_and_cache) |
| @s4 | RED | ROJO | tests/unit/test_red_hard.py (test_s4_skip_sentinel_identity_path_map_absent_key_sink_error) |

## Resumen

- **Fase**: RED (tests fallidos, implementación es hollow stub)
- **Test file**: `tests/unit/test_red_hard.py` — 6 test functions covering 4 scenarios
- **pytest result**: 6 FAILED / 0 PASSED (NotImplementedError from hollow stub)
- **Cobertura**:
  - @s1: threshold inclusivity (>=), sum accumulator, identity, emit wiring (1 test)
  - @s2: empty/None ValueError, normalize(None/0/False), default timeout (3 tests)
  - @s3: emit argv order, record identity, exact log, clock count, cache (1 test)
  - @s4: SKIP sentinel `is` check, path_map None identity, missing key default, SinkError fallback (1 test)
- **FIXTURE ≠ TARGET**: No se usan 'alpha', 'beta', 'quota-lab' como valores esperados
- **Mutant-killing**: assertions densas con cardinalidad exacta, tipos, identidad (`is`), sum vs product, boundary values