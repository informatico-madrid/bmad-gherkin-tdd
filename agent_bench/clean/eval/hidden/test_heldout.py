"""TDD GREEN — hidden test suite for Quota Broker (green-hard-001).

These tests are NEVER shown to the agent. They run AFTER the gold tests
to detect overfitting and hardcoding. Each test uses DIFFERENT literal
values than the gold test.

Contract: tests/contracts/green-hard.feature (8 @s, 24 pins)
Values: threshold=80, weights 11/17, scores 79/80/81, max_emit=3
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quota_broker import SKIP, SinkError, apply, normalize  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cache():
    if hasattr(apply, "_cache"):
        apply._cache.clear()
    yield
    if hasattr(apply, "_cache"):
        apply._cache.clear()

# ── Held-out constants (DIFFERENT from gold) ────────────────────────
H_THRESHOLD = 80
H_WEIGHT_A = 11
H_WEIGHT_B = 17
H_TIMEOUT = 600  # same as default (can't change the SUT default)


# ── Helpers (mirror gold, independent) ──────────────────────────────

def make_record(key, score, *, kind="work", weight=None, active=True, visible=True):
    return SimpleNamespace(
        key=key, score=score, kind=kind,
        weight=score if weight is None else weight,
        active=active, visible=visible,
    )

def make_spec(**overrides):
    spec = SimpleNamespace(
        threshold=H_THRESHOLD, active=True, visible=True,
        stop_on_first=False, path_map=None,
    )
    for k, v in overrides.items():
        setattr(spec, k, v)
    return spec

class RecordingSink:
    def __init__(self):
        self.calls = []
    def emit(self, kind, key, score_str, *args, **kwargs):
        timeout = kwargs.get("timeout", args[0] if args else None)
        self.calls.append(SimpleNamespace(kind=kind, key=key, score_str=score_str, timeout=timeout))

class RecordingClock:
    def __init__(self, ts=1700000000):
        self.now_count = 0
        self._ts = ts
    def now(self):
        self.now_count += 1
        return self._ts

class FailingSink:
    def __init__(self, msg="no-slot"):
        self.msg = msg
        self.calls = []
    def emit(self, kind, key, score_str, *args, **kwargs):
        self.calls.append(SimpleNamespace(kind=kind, key=key))
        raise SinkError(self.msg)

class EqualToAnything:
    def __eq__(self, other): return True
    def __hash__(self): return 0


# ── Hidden tests (one per surface) ─────────────────────────────────

class TestHeldOutThresholdInclusive:
    """P1: threshold inclusivity with H_THRESHOLD=80."""

    def test_boundary_79_80_81(self):
        """Three-point boundary: below, at, above H_THRESHOLD."""
        r79 = make_record("h_79", 79)
        r80 = make_record("h_80", 80)
        r81 = make_record("h_81", 81)
        spec = make_spec(threshold=H_THRESHOLD)
        sink = RecordingSink()
        clock = RecordingClock()

        result = apply([r79, r80, r81], spec, sink, clock)
        accepted, rejected, _ = result

        assert len(accepted) == 2
        assert [r.key for r in accepted] == ["h_80", "h_81"]
        assert r79.key in [r.key for r in rejected]

    def test_threshold_strictly_inclusive(self):
        """score == threshold → accepted (>= not >)."""
        r = make_record("h_eq", H_THRESHOLD)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 1


class TestHeldOutTruthTable:
    """P2: truth table with H_THRESHOLD."""

    def test_tt_tf_ft_ff(self):
        r_tt = make_record("tt", 90, active=True, visible=True)
        r_tf = make_record("tf", 90, active=True, visible=False)
        r_ft = make_record("ft", 90, active=False, visible=True)
        r_ff = make_record("ff", 90, active=False, visible=False)
        spec = make_spec(threshold=H_THRESHOLD)
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r_tt, r_tf, r_ft, r_ff], spec, sink, clock)
        accepted, rejected, _ = result
        assert len(accepted) == 1
        assert accepted[0].key == "tt"
        assert len(rejected) == 3


class TestHeldOutStopOnFirst:
    """P3: stop_on_first."""

    def test_stop_after_first(self):
        r1 = make_record("s_rej", 70)
        r2 = make_record("s_acc1", 90)
        r3 = make_record("s_acc2", 95)
        spec = make_spec(stop_on_first=True)
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r1, r2, r3], spec, sink, clock)
        _, _, _ = result
        assert len(sink.calls) == 1
        assert sink.calls[0].key == "s_acc1"


class TestHeldOutReturnShape:
    """P4: return shape is (tuple, tuple, int)."""

    def test_return_types(self):
        r = make_record("ret", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], tuple)
        assert isinstance(result[1], tuple)
        assert isinstance(result[2], int)


class TestHeldOutIdentity:
    """P5: object identity preserved."""

    def test_is_not_copy(self):
        r = make_record("id_test", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert result[0][0] is r


class TestHeldOutEmitWiring:
    """P6: emit argv order."""

    def test_emit_kind_key_str_score(self):
        r = make_record("wire", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        apply([r], spec, sink, clock)
        assert len(sink.calls) == 1
        assert sink.calls[0].kind == "work"
        assert sink.calls[0].key == "wire"
        assert sink.calls[0].score_str == "90"


class TestHeldOutDefaultTimeout:
    """P7: default timeout 600 via spy."""

    def test_timeout_in_calls(self):
        r = make_record("to", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        apply([r], spec, sink, clock)
        assert sink.calls[0].timeout == 600


class TestHeldOutNormalizeFalsy:
    """P8: normalize falsy values (separate assertions)."""

    def test_none_returns_fallback(self):
        assert normalize(None, fallback=7) == 7

    def test_zero_returns_zero(self):
        assert normalize(0, fallback=7) == 0

    def test_false_returns_zero(self):
        assert normalize(False, fallback=7) == 0


class TestHeldOutEmptyRecords:
    """P9: empty/None records → ValueError."""

    def test_empty_list(self):
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        with pytest.raises(ValueError, match=re.escape("records must not be empty")):
            apply([], spec, sink, clock)

    def test_none(self):
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        with pytest.raises(ValueError, match=re.escape("records must not be empty")):
            apply(None, spec, sink, clock)


class TestHeldOutAccumulator:
    """P10: asymmetric accumulator with weights 11 and 17."""

    def test_sum_not_product(self):
        r1 = make_record("w1", 90, weight=H_WEIGHT_A)
        r2 = make_record("w2", 95, weight=H_WEIGHT_B)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r1, r2], spec, sink, clock)
        _, _, tw = result
        assert tw == H_WEIGHT_A + H_WEIGHT_B
        assert tw != H_WEIGHT_A * H_WEIGHT_B


class TestHeldOutClockOnce:
    """P11: clock.now() called once per apply."""

    def test_now_count(self):
        r1 = make_record("c1", 90)
        r2 = make_record("c2", 91)
        r3 = make_record("c3", 92)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        apply([r1, r2, r3], spec, sink, clock)
        assert clock.now_count == 1


class TestHeldOutCache:
    """P12: cache per key, second call same key → no re-emit."""

    def test_same_key_no_reemit(self):
        r = make_record("cache_h", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        apply([r], spec, sink, clock)
        apply([r], spec, sink, clock)
        assert len(sink.calls) == 1


class TestHeldOutSkipSentinel:
    """P13: SKIP via `is`, decoy __eq__ doesn't fool."""

    def test_decoy_accepted_real_skip_rejected(self):
        decoy = make_record("decoy_h", 90, kind=EqualToAnything())
        skip_rec = make_record("skip_h", 90, kind=SKIP)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([decoy, skip_rec], spec, sink, clock)
        accepted, rejected, _ = result
        assert len(accepted) == 1
        assert accepted[0] is decoy
        assert len(rejected) == 1
        assert rejected[0] is skip_rec


class TestHeldOutPathMap:
    """P14: None keeps key; string remaps emit key."""

    def test_path_map_none_identity(self):
        r = make_record("pm_h", 90)
        spec = make_spec(path_map={"pm_h": None})
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 1
        assert sink.calls[0].key == "pm_h"

    def test_path_map_remaps_emit_key(self):
        r = make_record("pm_src_h", 90)
        spec = make_spec(path_map={"pm_src_h": "omega_alias"})
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 1
        assert sink.calls[0].key == "omega_alias"


class TestHeldOutAbsentKey:
    """P15: absent extra_key = no tag filter; present extra_key filters."""

    def test_spec_without_extra(self):
        r = make_record("ak_h", 90)
        spec = make_spec()
        assert not hasattr(spec, "extra_key")
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 1

    def test_spec_with_extra_filters_tag(self):
        ok = make_record("ak_ok", 90)
        ok.tag = "sigma"
        bad = make_record("ak_bad", 90)
        bad.tag = "nope"
        spec = make_spec(extra_key="sigma")
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([ok, bad], spec, sink, clock)
        assert result[0] == (ok,)
        assert bad in result[1]


class TestHeldOutSinkError:
    """P16: SinkError fallback."""

    def test_sink_error_rejects(self):
        r = make_record("se_h", 90)
        spec = make_spec()
        sink = FailingSink("h_no_slot")
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 0
        assert len(result[1]) == 1


class TestHeldOutTypeError:
    """P16b: TypeError propagates."""

    def test_type_error_not_swallowed(self):
        class TypeSink:
            def emit(self, *a, **kw):
                raise TypeError("h_broken")
        r = make_record("te_h", 90)
        spec = make_spec()
        clock = RecordingClock()
        with pytest.raises(TypeError):
            apply([r], spec, TypeSink(), clock)


class TestHeldOutLogExact:
    """P17: log exact message."""

    def test_log_message(self, caplog):
        r = make_record("log_h", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        with caplog.at_level(logging.INFO, logger="quota_broker"):
            apply([r], spec, sink, clock)
        messages = [rec.getMessage() for rec in caplog.records if rec.name == "quota_broker"]
        assert messages == ["accepted log_h score=90"]


class TestHeldOutCapsys:
    """P18: capsys exact line."""

    def test_stdout_dispatch(self, capsys):
        r = make_record("cs_h", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        apply([r], spec, sink, clock)
        captured = capsys.readouterr()
        assert captured.out.strip() == "dispatch cs_h work"


class TestHeldOutMaxEmit:
    """P19: max_emit bounds loop."""

    def test_max_emit_3(self):
        records = [make_record(f"me_{i}", 90) for i in range(5)]
        spec = make_spec(max_emit=3)
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply(records, spec, sink, clock)
        accepted, rejected, _ = result
        assert len(sink.calls) == 3
        assert len(accepted) == 3
        assert len(rejected) == 2


class TestHeldOutTraceRoundtrip:
    """P20: trace_id roundtrip."""

    def test_trace_id_written_and_readable(self):
        r = make_record("tr_h", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        accepted, _, _ = result
        assert accepted[0].trace_id == "trace_tr_h"

        twin = make_record("tr_h", 90)
        apply([twin], spec, sink, clock)
        assert twin.trace_id == "trace_tr_h"
        assert len(sink.calls) == 1


class TestHeldOutOrCompound:
    """P21: mode==strict or flag truth table."""

    def test_tt_strict_flag(self):
        r = make_record("or_tt", H_THRESHOLD)
        spec = make_spec(mode="strict", flag=True)
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 1

    def test_tf_strict_no_flag(self):
        r = make_record("or_tf", H_THRESHOLD)
        spec = make_spec(mode="strict", flag=False)
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 1

    def test_ft_relaxed_flag(self):
        r = make_record("or_ft", H_THRESHOLD)
        spec = make_spec(mode="relaxed", flag=True)
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 1

    def test_ff_relaxed_no_flag_rejected(self):
        r = make_record("or_ff", H_THRESHOLD)
        spec = make_spec(mode="relaxed", flag=False)
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 0
        assert r in result[1]


class TestHeldOutPublicLimit:
    """P22: public limit — score at threshold."""

    def test_at_threshold_accepted(self):
        r = make_record("pl_h", H_THRESHOLD)
        spec = make_spec(threshold=H_THRESHOLD)
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 1

    def test_below_threshold_rejected(self):
        r = make_record("pl_hb", H_THRESHOLD - 1)
        spec = make_spec(threshold=H_THRESHOLD)
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([r], spec, sink, clock)
        assert len(result[0]) == 0


class TestHeldOutKindMembership:
    """@s5: deny wins even when kind is also in allow."""

    def test_deny_overrides_allow(self):
        rec = make_record("km_both", 90, kind="omega")
        spec = make_spec(allow=["omega", "sigma"], deny=["omega"])
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([rec], spec, sink, clock)
        assert len(result[0]) == 0
        assert rec in result[1]

    def test_allow_without_deny_accepts(self):
        rec = make_record("km_ok", 90, kind="sigma")
        spec = make_spec(allow=["sigma"], deny=["omega"])
        sink = RecordingSink()
        clock = RecordingClock()
        result = apply([rec], spec, sink, clock)
        assert result[0] == (rec,)


class TestHeldOutCacheIsolation:
    """P23: cache per-key, different key not affected."""

    def test_different_keys_independent(self):
        r1 = make_record("ci_a", 90)
        r2 = make_record("ci_b", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        apply([r1], spec, sink, clock)
        apply([r2], spec, sink, clock)
        assert len(sink.calls) == 2

    def test_third_call_same_key_still_cached(self):
        r = make_record("ci_c", 90)
        spec = make_spec()
        sink = RecordingSink()
        clock = RecordingClock()
        apply([r], spec, sink, clock)
        apply([r], spec, sink, clock)
        apply([r], spec, sink, clock)
        assert len(sink.calls) == 1
