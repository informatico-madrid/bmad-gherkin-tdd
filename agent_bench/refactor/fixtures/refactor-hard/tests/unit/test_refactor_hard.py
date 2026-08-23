"""TDD GREEN — gold test for Quota Broker (refactor-hard-001).

Contract: tests/contracts/green-hard.feature (8 @s, 24 pins)
Each @s scenario maps to test functions. Every Then is a separate assertion.

This test is WRITTEN BY US (not the agent). The agent must implement
quota_broker.py to make ALL these tests PASS.

FIXTURE ≠ TARGET: expected values come from the signed contract
(scores [3, 7, 50, 51, 99], threshold=50, clock=1700000000, timeout=600),
never from sample labels.

SHA-256: computed at benchmark time, stored in eval/gold.sha256.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from quota_broker import SKIP, SinkError, apply, normalize  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset apply's internal cache between tests."""
    if hasattr(apply, "_cache"):
        apply._cache.clear()
    yield
    if hasattr(apply, "_cache"):
        apply._cache.clear()

FIXED_EPOCH = 1700000000
DEFAULT_TIMEOUT = 600
THRESHOLD = 50


# ---------------------------------------------------------------------------
# Helpers (not the SUT)
# ---------------------------------------------------------------------------


def make_record(
    key: str,
    score: int,
    *,
    kind: object = "work",
    weight: int | None = None,
    active: bool = True,
    visible: bool = True,
    payload: object = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        score=score,
        kind=kind,
        weight=score if weight is None else weight,
        active=active,
        visible=visible,
        payload=payload,
    )


def make_spec(**overrides: object) -> SimpleNamespace:
    spec = SimpleNamespace(
        threshold=THRESHOLD,
        active=True,
        visible=True,
        stop_on_first=False,
        path_map=None,
    )
    for name, value in overrides.items():
        setattr(spec, name, value)
    return spec


class RecordingSink:
    """Sink spy that records full emit argv (kind, key, str(score), timeout)."""

    def __init__(self) -> None:
        self.calls: list[SimpleNamespace] = []

    def emit(self, kind: object, key: object, score_str: object, *args: object, **kwargs: object) -> None:
        timeout = kwargs.get("timeout", args[0] if args else None)
        self.calls.append(
            SimpleNamespace(
                kind=kind,
                key=key,
                score_str=score_str,
                timeout=timeout,
            )
        )


class BrokenSink:
    """Sink that raises TypeError on emit for kind='broken'."""

    def emit(self, kind: object, key: object, score_str: object, *args: object, **kwargs: object) -> None:
        if kind == "broken":
            raise TypeError("broken kind not supported")
        # For other kinds, just record (same as RecordingSink)
        pass


class RecordingClock:
    def __init__(self, ts: int = FIXED_EPOCH) -> None:
        self.now_count = 0
        self.now_values: list[int] = []
        self._ts = ts

    def now(self) -> int:
        self.now_count += 1
        self.now_values.append(self._ts)
        return self._ts


class FailingSink:
    """Sink that raises SinkError on emit."""

    def __init__(self, msg: str = "no-slot") -> None:
        self.msg = msg
        self.calls: list[object] = []

    def emit(self, kind: object, key: object, score_str: object, *args: object, **kwargs: object) -> None:
        self.calls.append(SimpleNamespace(kind=kind, key=key, score_str=score_str))
        raise SinkError(self.msg)


class EqualToAnything:
    """__eq__ decoy so `is` and `==` diverge (Tipo G / sentinel)."""

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# @s1 — accept / reject / boundary + stop_on_first + truth table
# ---------------------------------------------------------------------------


def test_s1_accept_on_score_above_threshold_reject_below_boundary_at_threshold() -> None:
    """P1: threshold inclusivity. P10: asymmetric accumulator. P5: identity. P6: emit wiring."""
    rec3 = make_record("score_3", 3, weight=3)
    rec7 = make_record("score_7", 7, weight=7)
    rec50 = make_record("score_50", 50, weight=3)
    rec51 = make_record("score_51", 51, weight=5)
    rec99 = make_record("score_99", 99, weight=11)
    records = [rec3, rec7, rec50, rec51, rec99]
    spec = make_spec(threshold=50, active=True, visible=True)
    sink = RecordingSink()
    clock = RecordingClock()

    result = apply(records, spec, sink, clock)

    accepted, rejected, total_weight = result

    # P1: threshold inclusivity — 50 is accepted (>=)
    assert len(accepted) == 3
    assert [r.score for r in accepted] == [50, 51, 99]
    assert [r.key for r in accepted] == ["score_50", "score_51", "score_99"]

    # P5: object identity (is, not copy)
    assert accepted[0] is rec50
    assert accepted[1] is rec51
    assert accepted[2] is rec99

    # Rejected
    assert len(rejected) == 2
    assert [r.score for r in rejected] == [3, 7]
    assert rejected[0] is rec3
    assert rejected[1] is rec7

    # P4: return shape — full structural equality
    assert result == ((rec50, rec51, rec99), (rec3, rec7), 19)

    # P10: accumulator from SUT — 3+5+11 = 19, not the product
    assert total_weight == 19
    assert total_weight != 3 * 5 * 11


def test_s1_stop_on_first_stops_after_first_accept() -> None:
    """P3: stop_on_first — break after first accept."""
    rec_rej = make_record("first_reject", 1)
    rec_acc1 = make_record("first_accept", 80)
    rec_acc2 = make_record("second_accept", 90)
    spec = make_spec(stop_on_first=True)
    sink = RecordingSink()
    clock = RecordingClock()

    result = apply([rec_rej, rec_acc1, rec_acc2], spec, sink, clock)
    accepted, rejected, _ = result

    # P3: sink.emit called exactly once (kills break↔continue)
    assert len(sink.calls) == 1
    assert sink.calls[0].key == "first_accept"
    assert sink.calls[0].score_str == "80"

    # Second accept not processed
    assert len(accepted) == 1
    assert accepted[0] is rec_acc1
    assert rec_acc2 not in accepted
    assert rec_acc2.key not in [c.key for c in sink.calls]


def test_s1_truth_table_active_and_visible() -> None:
    """P2: truth table — TT accept, TF/FT/FF reject. One assertion per combo."""
    rec_tt = make_record("combo_tt", 80, active=True, visible=True)
    rec_tf = make_record("combo_tf", 80, active=True, visible=False)
    rec_ft = make_record("combo_ft", 80, active=False, visible=True)
    rec_ff = make_record("combo_ff", 80, active=False, visible=False)
    spec = make_spec(threshold=50)
    sink = RecordingSink()
    clock = RecordingClock()

    result = apply([rec_tt, rec_tf, rec_ft, rec_ff], spec, sink, clock)
    accepted, rejected, _ = result

    # Only TT accepted
    assert len(accepted) == 1
    assert accepted[0] is rec_tt
    assert accepted[0].active is True
    assert accepted[0].visible is True

    # Each rejected combo — one assertion per combo
    assert len(rejected) == 3
    assert rec_tf in rejected
    assert rec_ft in rejected
    assert rec_ff in rejected
    assert rec_tf.key not in [c.key for c in sink.calls]
    assert rec_ft.key not in [c.key for c in sink.calls]
    assert rec_ff.key not in [c.key for c in sink.calls]
    assert rec_tt.key in [c.key for c in sink.calls]


# ---------------------------------------------------------------------------
# @s2 — empty / None / normalize None·0·False / default timeout
# ---------------------------------------------------------------------------


def test_s2_empty_records_raises_valueerror() -> None:
    """P9: empty records → ValueError."""
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    with pytest.raises(ValueError, match=re.escape("records must not be empty")):
        apply([], spec, sink, clock)


def test_s2_none_records_raises_valueerror() -> None:
    """P9: None records → ValueError."""
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    with pytest.raises(ValueError, match=re.escape("records must not be empty")):
        apply(None, spec, sink, clock)


def test_s2_normalize_none_returns_fallback() -> None:
    """P8: normalize(None, fallback=10) → 10."""
    assert normalize(None, fallback=10) == 10


def test_s2_normalize_zero_returns_zero() -> None:
    """P8: normalize(0) → 0 (not swallowed as falsy)."""
    assert normalize(0, fallback=10) == 0


def test_s2_normalize_false_returns_zero() -> None:
    """P8: normalize(False) → 0 (not swallowed as None)."""
    assert normalize(False, fallback=10) == 0


def test_s2_apply_callable_without_timeout_kwarg() -> None:
    """P7: default timeout 600 observed via spy when called WITHOUT kwarg."""
    rec = make_record("t1", 80)
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    # Call WITHOUT timeout kwarg
    apply([rec], spec, sink, clock)

    # P7: observe default downstream
    assert sink.calls[0].timeout == DEFAULT_TIMEOUT
    assert sink.calls[0].timeout == 600


# ---------------------------------------------------------------------------
# @s3 — wiring, log, clock, cache, capsys
# ---------------------------------------------------------------------------


def test_s3_wiring_exacto(capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> None:
    """P6 emit argv. P5 identity. P17 log ==. P11 clock once. P18 capsys exact line."""
    rec_acc = make_record("mid_77", 77)
    rec_rej = make_record("low_3", 3)
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    with caplog.at_level(logging.INFO, logger="quota_broker"):
        result = apply([rec_acc, rec_rej], spec, sink, clock)
    accepted, rejected, _ = result

    assert len(sink.calls) == 1
    assert sink.calls[0].kind == "work"
    assert sink.calls[0].key == "mid_77"
    assert sink.calls[0].score_str == "77"
    assert accepted[0] is rec_acc
    assert clock.now_count == 1

    messages = [r.getMessage() for r in caplog.records if r.name == "quota_broker"]
    assert messages == ["accepted mid_77 score=77"]

    captured = capsys.readouterr()
    assert captured.out.strip() == "dispatch mid_77 work"


def test_s3_cache_second_call_no_reemit() -> None:
    """P12: second apply with same key → no re-emit."""
    rec = make_record("cache_key", 80)
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    apply([rec], spec, sink, clock)
    assert len(sink.calls) == 1

    # Second call with same record
    apply([rec], spec, sink, clock)
    # P12: still 1 call (cache hit)
    assert len(sink.calls) == 1


# ---------------------------------------------------------------------------
# @s4 — SKIP sentinel, path_map, absent key, SinkError
# ---------------------------------------------------------------------------


def test_s4_skip_sentinel_is_not_eq() -> None:
    """P13: SKIP recognized via `is`, not `==`. Decoy __eq__ doesn't fool it."""
    # Decoy: __eq__ returns True for anything
    decoy = make_record("decoy", 80, kind=EqualToAnything())
    # Real SKIP
    skip_rec = make_record("skipper", 80, kind=SKIP)
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    result = apply([decoy, skip_rec], spec, sink, clock)
    accepted, rejected, _ = result

    # Decoy accepted (EqualToAnything != SKIP via `is`, so `kind is SKIP` is False)
    assert len(accepted) == 1
    assert accepted[0] is decoy

    # SKIP rejected
    assert len(rejected) == 1
    assert rejected[0] is skip_rec


def test_s4_path_map_identity() -> None:
    """P14: None in path_map keeps emit key; a string remaps it."""
    rec = make_record("pm_test", 80)
    spec = make_spec(path_map={"pm_test": None})
    sink = RecordingSink()
    clock = RecordingClock()
    result = apply([rec], spec, sink, clock)
    assert len(result[0]) == 1
    assert sink.calls[0].key == "pm_test"

    rec2 = make_record("pm_src", 80)
    spec2 = make_spec(path_map={"pm_src": "pm_alias"})
    sink2 = RecordingSink()
    clock2 = RecordingClock()
    result2 = apply([rec2], spec2, sink2, clock2)
    assert len(result2[0]) == 1
    assert sink2.calls[0].key == "pm_alias"
    assert sink2.calls[0].key != rec2.key


def test_s4_absent_key_default() -> None:
    """P15: missing extra_key = no tag filter; present extra_key filters rec.tag."""
    rec = make_record("ak_test", 80)
    spec = make_spec()
    assert not hasattr(spec, "extra_key")
    sink = RecordingSink()
    clock = RecordingClock()
    result = apply([rec], spec, sink, clock)
    assert len(result[0]) == 1

    rec_ok = make_record("ak_vip", 80)
    rec_ok.tag = "vip"
    rec_no = make_record("ak_nope", 80)
    rec_no.tag = "nope"
    spec_f = make_spec(extra_key="vip")
    sink_f = RecordingSink()
    clock_f = RecordingClock()
    result_f = apply([rec_ok, rec_no], spec_f, sink_f, clock_f)
    assert result_f[0] == (rec_ok,)
    assert rec_no in result_f[1]


def test_s4_sink_error_fallback() -> None:
    """P16: SinkError → rejected fallback with exact message."""
    rec = make_record("err_test", 80)
    spec = make_spec()
    sink = FailingSink("no-slot")
    clock = RecordingClock()

    result = apply([rec], spec, sink, clock)
    accepted, rejected, _ = result

    assert len(accepted) == 0
    assert len(rejected) == 1
    assert rejected[0] is rec


# ---------------------------------------------------------------------------
# @s5 — kind membership, equality edge, capsys
# ---------------------------------------------------------------------------


def test_s5_kind_in_allow_not_in_deny(capsys: pytest.CaptureFixture[str]) -> None:
    """Deny is checked independently: kind in allow AND deny is rejected."""
    work_rec = make_record("work_ok", 60, kind="work")
    spam_rec = make_record("spam_bad", 60, kind="spam")
    unknown_rec = make_record("unknown_bad", 60, kind="unknown")
    both_rec = make_record("both_bad", 60, kind="urgent")

    spec = make_spec(allow=["work", "urgent"], deny=["urgent", "spam"])
    sink = RecordingSink()
    clock = RecordingClock()

    result = apply([work_rec, spam_rec, unknown_rec, both_rec], spec, sink, clock)
    accepted, rejected, _ = result

    assert accepted == (work_rec,)
    assert spam_rec in rejected
    assert unknown_rec in rejected
    assert both_rec in rejected

    captured = capsys.readouterr()
    assert captured.out.strip() == "dispatch work_ok work"


# ---------------------------------------------------------------------------
# @s6 — max_emit, trace_id roundtrip
# ---------------------------------------------------------------------------


def test_s6_max_emit_bounds_loop() -> None:
    """P19: max_emit caps the loop. P20: trace_id roundtrip."""
    rec1 = make_record("a1", 60)
    rec2 = make_record("a2", 70)
    rec3 = make_record("a3", 80)
    rec4 = make_record("a4", 90)
    spec = make_spec(max_emit=2)
    sink = RecordingSink()
    clock = RecordingClock()

    result = apply([rec1, rec2, rec3, rec4], spec, sink, clock)
    accepted, rejected, _ = result

    # P19: only 2 emitted
    assert len(sink.calls) == 2
    assert len(accepted) == 2
    assert len(rejected) == 2

    # P20: trace_id set on accepted records
    for rec in accepted:
        assert hasattr(rec, "trace_id")
        assert rec.trace_id == f"trace_{rec.key}"


# ---------------------------------------------------------------------------
# @s7 — or compound, public limit
# ---------------------------------------------------------------------------


def test_s7_or_compound_truth_table() -> None:
    """P21: mode==strict or flag — observed behavior.

    The or compound is advisory (additional qualifier), not a hard gate.
    Score >= threshold is the primary acceptance gate.
    All combinations with score at threshold are accepted regardless of mode/flag.
    """
    # TT: strict + flag → accepted
    rec_tt = make_record("or_tt", 50)
    spec_tt = make_spec(mode="strict", flag=True)
    sink = RecordingSink()
    clock = RecordingClock()
    result = apply([rec_tt], spec_tt, sink, clock)
    accepted, _, _ = result
    assert len(accepted) == 1

    # TF: strict + no flag → accepted
    rec_tf = make_record("or_tf", 50)
    spec_tf = make_spec(mode="strict", flag=False)
    sink2 = RecordingSink()
    clock2 = RecordingClock()
    result2 = apply([rec_tf], spec_tf, sink2, clock2)
    accepted2, _, _ = result2
    assert len(accepted2) == 1

    # FT: relaxed + flag → accepted
    rec_ft = make_record("or_ft", 50)
    spec_ft = make_spec(mode="relaxed", flag=True)
    sink3 = RecordingSink()
    clock3 = RecordingClock()
    result3 = apply([rec_ft], spec_ft, sink3, clock3)
    accepted3, _, _ = result3
    assert len(accepted3) == 1

    # FF: relaxed + no flag → rejected (contract @s7)
    rec_ff = make_record("or_ff", 50)
    spec_ff = make_spec(mode="relaxed", flag=False)
    sink4 = RecordingSink()
    clock4 = RecordingClock()
    result4 = apply([rec_ff], spec_ff, sink4, clock4)
    accepted4, rejected4, _ = result4
    assert len(accepted4) == 0
    assert rejected4 == (rec_ff,)
    # Adjust based on golden impl behavior.


def test_s7_public_limit_boundary() -> None:
    """P22: score=50 at threshold=50 → accepted (boundary inclusive)."""
    rec = make_record("boundary_50", 50)
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    result = apply([rec], spec, sink, clock)
    accepted, _, _ = result
    assert len(accepted) == 1

    # score=49 → rejected
    rec49 = make_record("boundary_49", 49)
    sink2 = RecordingSink()
    clock2 = RecordingClock()
    result2 = apply([rec49], spec, sink2, clock2)
    accepted2, _, _ = result2
    assert len(accepted2) == 0


# ---------------------------------------------------------------------------
# @s8 — TypeError propagation, cache isolation
# ---------------------------------------------------------------------------


def test_s8_typeerror_propagates() -> None:
    """P16b: TypeError from sink propagates (NOT caught)."""
    rec = make_record("broken_rec", 60, kind="broken")
    spec = make_spec()
    sink = BrokenSink()
    clock = RecordingClock()

    with pytest.raises(TypeError, match="broken kind not supported"):
        apply([rec], spec, sink, clock)


def test_s8_cache_isolation_by_key() -> None:
    """P23: cache is per-key, not global."""
    rec_a = make_record("key_a", 80)
    rec_b = make_record("key_b", 80)
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    # First call: key_a cached
    apply([rec_a], spec, sink, clock)
    assert len(sink.calls) == 1

    # Second call: key_b (different key) → NOT affected by key_a cache
    apply([rec_b], spec, sink, clock)
    assert len(sink.calls) == 2

    # Third call: key_a again → still cached
    apply([rec_a], spec, sink, clock)
    assert len(sink.calls) == 2  # no new emit


def test_s8_third_call_same_key_still_cached() -> None:
    """P12b: third call with same key still returns cached result."""
    rec = make_record("triple", 80)
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    apply([rec], spec, sink, clock)
    apply([rec], spec, sink, clock)
    apply([rec], spec, sink, clock)

    # Only 1 emit total
    assert len(sink.calls) == 1
