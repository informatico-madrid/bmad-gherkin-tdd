"""TDD RED — failing tests for Quota Broker scenarios @s1 @s2 @s3 @s4.

Contract: tests/contracts/red-hard.feature (4 scenarios)
Each scenario maps to one test function. Every Then is a separate assertion.

FIXTURE ≠ TARGET: expected values are derived from the contract (scores [3,7,50,51,99],
threshold=50, clock=1700000000, timeout=600), never from sample labels like alpha/beta.

Implementation is a hollow stub (NotImplementedError) → tests MUST fail.
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

FIXED_EPOCH = 1700000000
DEFAULT_TIMEOUT = 600
THRESHOLD = 50


# ---------------------------------------------------------------------------
# Helpers (not the SUT) — fixture objects, NOT expected values
# ---------------------------------------------------------------------------


def make_record(
    key: str,
    score: int,
    *,
    kind: object = "work",
    weight: int | None = None,
    active: bool = True,
    visible: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        score=score,
        kind=kind,
        weight=score if weight is None else weight,
        active=active,
        visible=visible,
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
    """Sink spy that records full emit argv (kind, key, score_str, timeout)."""

    def __init__(self) -> None:
        self.calls: list[SimpleNamespace] = []

    def emit(
        self,
        kind: object,
        key: object,
        score_str: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        timeout = kwargs.get("timeout", args[0] if args else None)
        self.calls.append(
            SimpleNamespace(
                kind=kind,
                key=key,
                score_str=score_str,
                timeout=timeout,
            )
        )


class RecordingClock:
    """Clock spy that counts now() calls and records return values."""

    def __init__(self, ts: int = FIXED_EPOCH) -> None:
        self.now_count = 0
        self._ts = ts

    def now(self) -> int:
        self.now_count += 1
        return self._ts


class FailingSink:
    """Sink that raises SinkError on emit."""

    def __init__(self, msg: str = "no-slot") -> None:
        self.msg = msg

    def emit(self, kind: object, key: object, score_str: object, *args: object, **kwargs: object) -> None:
        raise SinkError(self.msg)


# ---------------------------------------------------------------------------
# @s1 — accept on score above threshold, reject below, boundary at threshold
# Then 1: accepted son 3 (scores 51, 99, 50 si threshold estricto)
# Then 2: rejected son 2 (scores 3, 7)
# Then 3: sink.emit fue llamado solo con los accepted
# Then 4: total weight acumulado es la suma de weights de accepted (asimetrico)
# ---------------------------------------------------------------------------


def test_s1_accept_above_reject_below_boundary_strict_threshold() -> None:
    """Contract @s1: threshold inclusivity (>=), accumulator is sum not product."""
    rec3 = make_record("s1_3", 3, weight=3)
    rec7 = make_record("s1_7", 7, weight=7)
    rec50 = make_record("s1_50", 50, weight=3)
    rec51 = make_record("s1_51", 51, weight=5)
    rec99 = make_record("s1_99", 99, weight=11)
    records = [rec3, rec7, rec50, rec51, rec99]

    spec = make_spec(threshold=50, active=True, visible=True)
    sink = RecordingSink()
    clock = RecordingClock()

    accepted, rejected, total_weight = apply(records, spec, sink, clock)

    # Then 1: exactly 3 accepted with specific scores
    assert len(accepted) == 3
    assert [r.score for r in accepted] == [50, 51, 99]

    # Then 1b: object identity preserved (is, not copy)
    assert accepted[0] is rec50
    assert accepted[1] is rec51
    assert accepted[2] is rec99

    # Then 2: exactly 2 rejected with specific scores
    assert len(rejected) == 2
    assert [r.score for r in rejected] == [3, 7]

    # Then 3: sink.emit called ONLY with accepted records — 3 calls
    assert len(sink.calls) == 3

    # Then 3b: emitted keys match accepted keys
    emitted_keys = {c.key for c in sink.calls}
    accepted_keys = {r.key for r in accepted}
    assert emitted_keys == accepted_keys

    # Then 4: total weight = sum of weights of accepted (3+5+11=19), NOT product (3*5*11=165)
    assert isinstance(total_weight, int)
    assert total_weight == 19
    assert total_weight != 3 * 5 * 11


# ---------------------------------------------------------------------------
# @s2 — empty records raises ValueError, None raises ValueError,
#        normalize(None/0/False), default timeout without kwarg
# ---------------------------------------------------------------------------


def test_s2_empty_and_none_records_raise_valueerror() -> None:
    """Contract @s2: empty [] and None records both raise ValueError."""
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    # Then 1: empty list raises ValueError with specific message
    with pytest.raises(ValueError, match=re.escape("records must not be empty")):
        apply([], spec, sink, clock)

    # Then 2: None raises ValueError with same message
    with pytest.raises(ValueError, match=re.escape("records must not be empty")):
        apply(None, spec, sink, clock)


def test_s2_normalize_none_zero_false_edge_cases() -> None:
    """Contract @s2: normalize(None)→10, normalize(0)→0, normalize(False)→0."""
    # Then 1: normalize(None, fallback=10) returns 10
    assert normalize(None, fallback=10) == 10
    # Then 2: normalize(0, fallback=10) returns 0 (not swallowed as falsy)
    assert normalize(0, fallback=10) == 0
    # Then 3: normalize(False, fallback=10) returns 0 (not swallowed as None)
    assert normalize(False, fallback=10) == 0


def test_s2_apply_callable_without_timeout_kwarg() -> None:
    """Contract @s2: apply is callable WITHOUT timeout kwarg, default 600 observed."""
    rec = make_record("s2_default_timeout", 80)
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    # Call WITHOUT timeout kwarg — should use default 600
    apply([rec], spec, sink, clock)

    # Then: observe default timeout passed downstream via sink spy
    assert len(sink.calls) == 1
    assert sink.calls[0].timeout == 600
    assert sink.calls[0].timeout == DEFAULT_TIMEOUT


# ---------------------------------------------------------------------------
# @s3 — wiring exact, log exact, argv order, cache, clock
# ---------------------------------------------------------------------------


def test_s3_wiring_log_clock_and_cache(capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> None:
    """Contract @s3: emit argv order, record identity, exact log message, clock count, cache."""
    rec_acc = make_record("s3_77", 77)
    rec_rej = make_record("s3_3", 3)
    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    with caplog.at_level(logging.INFO, logger="quota_broker"):
        accepted, rejected, _ = apply([rec_acc, rec_rej], spec, sink, clock)

    # Then 1: sink.emit received (kind, record.key, str(score)) in that order
    assert len(sink.calls) == 1
    assert sink.calls[0].kind == "work"
    assert sink.calls[0].key == "s3_77"
    assert sink.calls[0].score_str == "77"

    # Then 2: record object identity preserved (is record, not copy)
    assert len(accepted) == 1
    assert accepted[0] is rec_acc

    # Then 3: logger recorded "accepted {key} score={score}" with exact message
    messages = [r.getMessage() for r in caplog.records if r.name == "quota_broker"]
    assert messages == ["accepted s3_77 score=77"]

    # Then 4: clock.now() called exactly once
    assert clock.now_count == 1

    # Then 5: second call with same record does NOT re-emit (cache)
    apply([rec_acc], spec, sink, clock)
    assert len(sink.calls) == 1  # still 1, cache hit


# ---------------------------------------------------------------------------
# @s4 — SKIP sentinel, path_map identity, absent key, SinkError fallback
# Then 1: SKIP recognized via `is` not `==`
# Then 2: path_map None means identity pass-through
# Then 3: missing key triggers default path (all records accepted)
# Then 4: SinkError from sink triggers Rejected fallback with exact message
# ---------------------------------------------------------------------------


def test_s4_skip_sentinel_identity_path_map_absent_key_sink_error() -> None:
    """Contract @s4: SKIP is sentinel (is not ==), path_map None, missing key, SinkError."""
    # ---- Then 1: SKIP recognized via `is`, not `==` ----
    # Create a decoy record that lies about equality (returns True for any ==)
    class EqualToAnything:
        """Decoy class where __eq__ returns True for anything — but is diverges."""

        def __eq__(self, other: object) -> bool:
            return True

        def __hash__(self) -> int:
            return 0

    decoy_record = make_record("s4_decoy", 80, kind=EqualToAnything())
    skip_record = make_record("s4_skip", 80, kind=SKIP)

    spec = make_spec()
    sink = RecordingSink()
    clock = RecordingClock()

    result_acc, result_rej, _ = apply([decoy_record, skip_record], spec, sink, clock)

    # Decoy with EqualToAnything kind is accepted (EqualToAnything != SKIP via `is`)
    assert len(result_acc) == 1
    assert result_acc[0] is decoy_record

    # SKIP record is rejected (kind is SKIP → True, so rejected)
    assert len(result_rej) == 1
    assert result_rej[0] is skip_record

    # ---- Then 2: path_map None means identity pass-through ----
    rec_identity = make_record("s4_identity", 80)
    spec_identity = make_spec(path_map={"s4_identity": None})
    sink_identity = RecordingSink()
    clock_identity = RecordingClock()

    apply([rec_identity], spec_identity, sink_identity, clock_identity)

    # path_map key→None: emitted key should be the original record key (identity pass-through)
    assert len(sink_identity.calls) == 1
    assert sink_identity.calls[0].key == "s4_identity"

    # ---- Then 3: missing extra_key triggers default path (no tag filter) ----
    # When spec does NOT have "extra_key" attribute, all records pass through
    assert not hasattr(spec, "extra_key")

    rec_pass = make_record("s4_pass", 80)
    sink_default = RecordingSink()
    clock_default = RecordingClock()

    accepted_default, rejected_default, _ = apply([rec_pass], spec, sink_default, clock_default)

    # Missing extra_key → no tag filtering → record accepted
    assert len(accepted_default) == 1
    assert accepted_default[0] is rec_pass
    assert len(rejected_default) == 0

    # ---- Then 4: SinkError from sink triggers Rejected fallback ----
    rec_err = make_record("s4_err", 80)
    sink_err = FailingSink("no-slot")
    clock_err = RecordingClock()

    accepted_err, rejected_err, _ = apply([rec_err], spec, sink_err, clock_err)

    # SinkError → record moved to rejected
    assert len(accepted_err) == 0
    assert len(rejected_err) == 1
    assert rejected_err[0] is rec_err