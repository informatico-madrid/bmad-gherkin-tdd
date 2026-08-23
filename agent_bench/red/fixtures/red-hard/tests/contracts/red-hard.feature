# Status: APPROVED
# Approved-by: bench-synthetic
# Story-key: red-hard-001

Feature: Quota Broker — dispatch + normalize
  Kernel de política que acepta / rechaza / reenvía records.

  Background:
    Given un spec con threshold=50, active=true, visible=true
    And un sink mock que registra llamadas
    And un clock fijo que devuelve 1700000000

  @s1 @dispatch @fronteras @aritmetica @booleanos
  Scenario: accept on score above threshold, reject below, boundary at threshold
    Given records con scores [3, 7, 50, 51, 99]
    When apply(records, spec, sink, clock)
    Then accepted son 3 (scores 51, 99, 50 si threshold estricto)
    And rejected son 2 (scores 3, 7)
    And sink.emit fue llamado solo con los accepted
    And total weight acumulado es la suma de weights de accepted (asimétrico: 3+7+50 ≠ 3*7*50)

  @s1 @booleanos @stop_on_first
  Scenario: stop_on_first stops after first accept
    Given records [rejected, accepted, accepted]
    And spec con stop_on_first=true
    When apply(records, spec, sink, clock)
    Then sink.emit fue llamado 1 sola vez
    And el primer accepted fue procesado, el segundo no

  @s1 @truth_table
  Scenario: active and visible truth table
    Given records where active=True,visible=True and active=True,visible=False
    And records where active=False,visible=True and active=False,visible=False
    When apply(records, spec, sink, clock)
    Then only (active=True,visible=True) is accepted
    And the other 3 combinations are rejected
    And each Then maps to exactly one assertion about a specific combination

  @s2 @excepciones @none @empty @default @h15 @h18
  Scenario: empty records raises ValueError, None raises ValueError
    Given empty records []
    When apply([], spec, sink, clock)
    Then raises ValueError with message "records must not be empty"
    And normalize(None, fallback=10) returns 10
    And normalize(0, fallback=10) returns 0
    And normalize(False, fallback=10) returns 0
    And apply is callable WITHOUT timeout kwarg (default 600 observed via sink spy)

  @s3 @wiring @h1 @h3 @h7 @h10 @h2
  Scenario: wiring exacto, log exacto, argv orden, cache, clock
    Given records con 1 accepted y 1 rejected
    When apply(records, spec, sink, clock)
    Then sink.emit received (kind, record.key, str(score)) in that order
    And sink.emit was called with record object identity preserved (is record, not copy)
    And logger recorded "accepted {key} score={score}" with exact message
    And clock.now() was called exactly once
    And second call to apply with same record does NOT re-emit (cache)

  @s4 @sentinel @path_map @tipo_c @h6 @h20
  Scenario: SKIP sentinel, path_map identity, absent key, SinkError fallback
    Given record with kind=SKIP (sentinel object, not string)
    And path_map {"keep": None} (identity, not string)
    And spec missing "extra_key" field (type C default)
    When apply([skip_record], spec, sink, clock)
    Then SKIP sentinel is recognized via `is` not `==`
    And path_map None means identity pass-through
    And missing key triggers default path
    And SinkError from sink triggers Rejected fallback with exact message
    And all 4 Then map to separate assertions (not combined)
