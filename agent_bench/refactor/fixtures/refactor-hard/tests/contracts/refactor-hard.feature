# Status: APPROVED
# Approved-by: bench-synthetic
# Story-key: refactor-hard-001

Feature: Quota Broker — dispatch + normalize (GREEN-hard)
  Kernel de política que acepta / rechaza / reenvía records.
  Superserie hostil: 8 escenarios que obligan a cada clase de mutante.

  Background:
    Given un spec con threshold=50, active=true, visible=true, stop_on_first=false, path_map=null
    And un sink mock que registra llamadas
    And un clock fijo que devuelve 1700000000

  @s1 @dispatch @fronteras @aritmetica @booleanos
  Scenario: accept on score above threshold, reject below, boundary at threshold inclusive
    Given records con scores [3, 7, 50, 51, 99] y weights [3, 7, 50, 5, 11]
    When apply(records, spec, sink, clock)
    Then accepted son 3 (scores 50, 51, 99) — threshold es inclusivo
    And rejected son 2 (scores 3, 7)
    And sink.emit fue llamado solo con los accepted, en orden
    And total_weight es la suma de weights de accepted (no el producto: 3+5+11 = 19, ≠ 3*5*11)
    And each accepted record is the same object (identity, not copy)

  @s1 @stop_on_first
  Scenario: stop_on_first stops after first accept
    Given records [rejected(score=3), accepted(score=80), accepted(score=90)]
    And spec con stop_on_first=true
    When apply(records, spec, sink, clock)
    Then sink.emit fue llamado 1 sola vez
    And el primer accepted fue procesado, el segundo no

  @s1 @truth_table
  Scenario: active and visible truth table — TT accept, TF/FT/FF reject
    Given records where (active=True,visible=True,score=80)
    And records where (active=True,visible=False,score=80)
    And records where (active=False,visible=True,score=80)
    And records where (active=False,visible=False,score=80)
    When apply(records, spec, sink, clock)
    Then only (active=True,visible=True) is accepted
    And the other 3 combinations are rejected
    And each Then maps to exactly one assertion about a specific combination

  @s2 @excepciones @none @empty @default @h15 @h18
  Scenario: empty records raises ValueError, None raises ValueError, normalize falsy, default timeout
    Given empty records []
    When apply([], spec, sink, clock)
    Then raises ValueError with message "records must not be empty"
    And apply(None, spec, sink, clock) raises same ValueError
    And normalize(None, fallback=10) returns 10
    And normalize(0, fallback=10) returns 0
    And normalize(False, fallback=10) returns 0
    And apply is callable WITHOUT timeout kwarg (default 600 observed via sink spy)

  @s3 @wiring @h1 @h3 @h7 @h10 @h2
  Scenario: wiring exacto, log exacto, clock once, cache, argv order
    Given records con 1 accepted (score=77) y 1 rejected (score=3)
    When apply(records, spec, sink, clock)
    Then sink.emit received (kind, record.key, str(score)) in that order
    And sink.emit was called with record object identity preserved (is record, not copy)
    And logger recorded "accepted mid_77 score=77" with exact message
    And clock.now() was called exactly once
    And second call to apply with same record does NOT re-emit (cache)
    And stdout contains exactly "dispatch mid_77 work" (capsys, exact line)

  @s4 @sentinel @path_map @tipo_c @h6 @h20
  Scenario: SKIP sentinel, path_map identity, absent key, SinkError fallback
    Given record with kind=SKIP (sentinel object, not string)
    And path_map {"keep": None} (identity, not string)
    And spec missing "extra_key" field (type C default)
    When apply([skip_record], spec, sink, clock)
    Then SKIP sentinel is recognized via `is` not `==`
    And path_map None means identity pass-through
    And missing key triggers default path
    And SinkError from sink triggers Rejected fallback with exact message "no-slot"
    And all 4 Then map to separate assertions (not combined)

  @s5 @pertenencia @igualdad @capsys
  Scenario: kind in allow, kind not in deny, equality edge, capsys exact
    Given spec with allow=["work","urgent"] and deny=["spam"]
    And record kind="work" (in allow, not in deny) with score=60
    And record kind="spam" (in deny) with score=60
    And record kind="unknown" (not in allow) with score=60
    When apply([work_rec, spam_rec, unknown_rec], spec, sink, clock)
    Then work_rec is accepted (kind in allow AND not in deny)
    And spam_rec is rejected (kind in deny)
    And unknown_rec is rejected (kind not in allow)
    And sink.emit called exactly once (only work_rec)
    And stdout contains "dispatch work_rec work" (exact line, capsys)

  @s6 @loop_bound @roundtrip @h9 @tipo_f
  Scenario: max_emit bounds the loop, trace_id roundtrip
    Given spec with max_emit=2
    And 4 records all qualifying (scores 60, 70, 80, 90)
    When apply(records, spec, sink, clock)
    Then only 2 records were emitted (max_emit caps the loop)
    And accepted contains exactly 2 records
    And rejected contains 2 records (the overflow)
    And each accepted record has trace_id set (write side-effect)
    And second read of same record returns same trace_id (roundtrip)

  @s7 @or_compound @public_limit @h11
  Scenario: mode strict or flag truth table, public API at boundary
    Given spec with mode="strict" and flag=false
    And record with score=50 (exactly at threshold)
    When apply([record], spec, sink, clock)
    Then record is accepted (score >= threshold AND mode==strict)
    And spec with mode="relaxed" and flag=true → record accepted (flag=true short-circuit)
    And spec with mode="relaxed" and flag=false → record rejected (both false)
    And spec with mode="strict" and flag=true → record accepted (both true)
    And calling apply with score=49 always rejects regardless of mode/flag

  @s8 @error_isolation @cache_isolation
  Scenario: TypeError propagates, cache isolated by key
    Given sink that raises TypeError on emit for kind="broken"
    And record kind="broken" score=60
    When apply([broken_rec], spec, sink, clock)
    Then TypeError propagates (NOT caught, only SinkError triggers fallback)
    And record kind="good" score=60 is cached under key "good_key"
    And record kind="other" score=60 with different key is NOT affected by cache
    And third call to apply with same "good_key" still returns cached result
