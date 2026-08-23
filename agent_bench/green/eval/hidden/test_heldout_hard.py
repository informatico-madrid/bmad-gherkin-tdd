"""Held-out HARD suite — interaction pins the easy suite does not hit.

Re-eval only: does not require re-running agents.
"""

from __future__ import annotations

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


def rec(key, score, **kw):
    return SimpleNamespace(
        key=key,
        score=score,
        kind=kw.get("kind", "work"),
        weight=kw.get("weight", score),
        active=kw.get("active", True),
        visible=kw.get("visible", True),
        tag=kw.get("tag", None),
    )


def spec(**kw):
    s = SimpleNamespace(threshold=kw.pop("threshold", 80), stop_on_first=False, path_map=None)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


class Sink:
    def __init__(self):
        self.calls = []

    def emit(self, kind, key, score_str, *a, **kw):
        self.calls.append((kind, key, score_str, kw.get("timeout", a[0] if a else None)))


class Clock:
    def __init__(self):
        self.n = 0

    def now(self):
        self.n += 1
        return 1


class BoomSink(Sink):
    def emit(self, *a, **kw):
        super().emit(*a, **kw)
        raise SinkError("no-slot")


class TestHardCacheIsNotForceAccept:
    def test_cached_key_with_failing_score_is_not_accepted(self):
        """Cache = no re-emit, not 'same key always accepted'."""
        s = spec(threshold=80)
        sink = Sink()
        clock = Clock()
        apply([rec("k", 90)], s, sink, clock)
        low = rec("k", 10)
        acc, rej, _ = apply([low], s, sink, clock)
        assert len(sink.calls) == 1
        assert low not in acc


class TestHardStopOnFirstRemainder:
    def test_unprocessed_accept_not_in_accepted(self):
        s = spec(threshold=80, stop_on_first=True)
        a = rec("r", 10)
        b = rec("a1", 90)
        c = rec("a2", 91)
        acc, rej, _ = apply([a, b, c], s, Sink(), Clock())
        assert b in acc
        assert c not in acc
        assert len(acc) == 1


class TestHardMaxEmitZero:
    def test_max_emit_zero_rejects_all_qualifying(self):
        s = spec(threshold=80, max_emit=0)
        r = rec("z", 90)
        acc, rej, w = apply([r], s, Sink(), Clock())
        assert acc == ()
        assert r in rej
        assert w == 0


class TestHardSinkErrorNotCached:
    def test_failed_emit_retries_next_apply(self):
        s = spec(threshold=80)
        r1 = rec("e", 90)
        boom = BoomSink()
        acc, rej, _ = apply([r1], s, boom, Clock())
        assert r1 in rej
        ok = Sink()
        r2 = rec("e", 90)
        acc2, _, _ = apply([r2], s, ok, Clock())
        assert len(ok.calls) == 1
        assert r2 in acc2


class TestHardClockEmpty:
    def test_empty_raises_before_clock(self):
        clock = Clock()
        with pytest.raises(ValueError):
            apply([], spec(), Sink(), clock)
        assert clock.n == 0


class TestHardClockPerApply:
    def test_each_apply_ticks_clock_once(self):
        clock = Clock()
        s = spec(threshold=80)
        apply([rec("a", 90)], s, Sink(), clock)
        apply([rec("b", 90)], s, Sink(), clock)
        assert clock.n == 2


class TestHardComboGates:
    def test_allow_deny_extra_and_mode_together(self):
        s = spec(
            threshold=80,
            allow=["omega"],
            deny=["omega"],
            extra_key="vip",
            mode="strict",
            flag=False,
        )
        r = rec("x", 90, kind="omega", tag="vip")
        acc, rej, _ = apply([r], s, Sink(), Clock())
        assert r in rej
        assert acc == ()


class TestHardNormalizeNeg:
    def test_negative_int_preserved(self):
        assert normalize(-3, fallback=10) == -3


class TestHardWeightOnlyAccepted:
    def test_rejected_weight_not_in_total(self):
        s = spec(threshold=80)
        hi = rec("h", 90, weight=11)
        lo = rec("l", 10, weight=17)
        _, _, w = apply([hi, lo], s, Sink(), Clock())
        assert w == 11


class TestHardCacheHitNoReemitInvariant:
    def test_second_apply_same_key_does_not_reemit_or_reweight(self):
        """P12: cache hit = no re-emit. Weight must not be double-counted."""
        s = spec(threshold=80)
        sink = Sink()
        _, _, w1 = apply([rec("dup", 90, weight=11)], s, sink, Clock())
        assert w1 == 11
        _, _, w2 = apply([rec("dup", 90, weight=11)], s, sink, Clock())
        assert len(sink.calls) == 1
        assert w2 != w1 + 11


class TestHardMaxEmitOverflowWeight:
    def test_overflow_not_weighted(self):
        s = spec(threshold=80, max_emit=1)
        a = rec("m1", 90, weight=11)
        b = rec("m2", 91, weight=17)
        acc, rej, w = apply([a, b], s, Sink(), Clock())
        assert acc == (a,)
        assert rej == (b,)
        assert w == 11


class TestHardPartialSinkFailure:
    def test_only_failing_record_rejected(self):
        class PickSink(Sink):
            def emit(self, kind, key, score_str, *a, **kw):
                if key == "bad":
                    raise SinkError("no-slot")
                super().emit(kind, key, score_str, *a, **kw)

        s = spec(threshold=80)
        bad = rec("bad", 90)
        ok = rec("ok", 91)
        sink = PickSink()
        acc, rej, _ = apply([bad, ok], s, sink, Clock())
        assert len(sink.calls) == 1
        assert acc == (ok,)
        assert rej == (bad,)


class TestHardPathMapRemapIdentity:
    def test_emit_alias_but_record_key_and_trace_original(self):
        s = spec(threshold=80, path_map={"src": "alias"})
        r = rec("src", 90)
        sink = Sink()
        acc, _, _ = apply([r], s, sink, Clock())
        assert sink.calls[0][1] == "alias"
        assert acc[0].key == "src"
        assert acc[0].trace_id == "trace_src"


class TestHardStopOnFirstRejectThenAccept:
    def test_reject_counted_before_break(self):
        s = spec(threshold=80, stop_on_first=True)
        r = rec("s_r", 10)
        a1 = rec("s_a1", 90)
        a2 = rec("s_a2", 91)
        acc, rej, _ = apply([r, a1, a2], s, Sink(), Clock())
        assert rej == (r,)
        assert acc == (a1,)
        assert a2 not in acc


class TestHardClockOnceMixed:
    def test_single_tick_with_mixed_outcomes(self):
        s = spec(threshold=80, deny=["spam"])
        clock = Clock()
        apply([rec("c1", 10), rec("c2", 90, kind="spam"), rec("c3", 90)], s, Sink(), clock)
        assert clock.n == 1


class TestHardNormalizeStringDigit:
    def test_string_digit_normalized(self):
        assert normalize("7", fallback=10) == 7


class TestHardMultiRecordPartition:
    def test_full_gate_partition(self):
        """8 records across every gate; assert exact accepted/rejected partition."""
        s = spec(
            threshold=80,
            allow=["work", "urgent"],
            deny=["urgent"],
            extra_key="vip",
            mode="strict",
            flag=False,
        )
        recs = [
            rec("p1", 90, kind="work", tag="vip"),      # pass all -> accepted
            rec("p2", 70, kind="work", tag="vip"),      # score<thresh -> rejected
            rec("p3", 90, kind="urgent", tag="vip"),    # in deny -> rejected
            rec("p4", 90, kind="noise", tag="vip"),     # not in allow -> rejected
            rec("p5", 90, kind="work", tag="other"),    # tag!=extra_key -> rejected
            rec("p6", 90, kind="work", tag="vip", active=False),  # not active -> rejected
            rec("p7", 90, kind="work", tag="vip", visible=False), # not visible -> rejected
            rec("p8", 90, kind="work", tag="vip", weight=7),      # accepted, weight 7
        ]
        sink = Sink()
        acc, rej, w = apply(recs, s, sink, Clock())
        assert acc == (recs[0], recs[7])
        assert rej == (recs[1], recs[2], recs[3], recs[4], recs[5], recs[6])
        assert w == 90 + 7
        assert len(sink.calls) == 2


class TestHardSkipHighScore:
    def test_skip_rejected_even_if_qualifying(self):
        s = spec(threshold=80)
        r = rec("sk", 99, kind=SKIP)
        acc, rej, _ = apply([r], s, Sink(), Clock())
        assert acc == ()
        assert rej == (r,)


class TestHardNormalizeBool:
    def test_bool_true_is_one(self):
        assert normalize(True, fallback=10) == 1


class TestHardAcceptedOrderPreserved:
    def test_accepted_keeps_input_order(self):
        s = spec(threshold=80)
        a = rec("o1", 85)
        b = rec("o2", 95)
        c = rec("o3", 81)
        acc, _, _ = apply([a, b, c], s, Sink(), Clock())
        assert acc == (a, b, c)
