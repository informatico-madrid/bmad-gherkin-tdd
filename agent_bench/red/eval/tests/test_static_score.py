"""Tests for the static_score.py evaluator.

The scorer must score itself — no SUT, no execution, 100% AST-based.
Tests are synthetic: good tests and bad tests as pytest fixtures.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agent_bench.red.eval.static_score import (
    evaluate,
    format_scorecard,
)


# ── Fixtures: synthetic test sources ────────────────────────────────

GOOD_TEST = textwrap.dedent("""\
    import pytest
    from quota_broker import apply, normalize, SKIP, SinkError

    def test_accept_above_threshold():
        spec = {"threshold": 50, "active": True, "visible": True, "stop_on_first": False}
        records = [
            {"key": "r1", "kind": "work", "score": 51, "weight": 3},
            {"key": "r2", "kind": "work", "score": 3, "weight": 7},
            {"key": "r3", "kind": "work", "score": 50, "weight": 50},
        ]
        sink = MagicMock()
        clock = MagicMock()
        clock.now.return_value = 1700000000
        result = apply(records, spec, sink, clock)
        accepted = [r for r in result if r.status == "accepted"]
        rejected = [r for r in result if r.status == "rejected"]
        assert len(accepted) == 3
        assert len(rejected) == 2
        assert sink.emit.call_count == 3

    def test_truth_table_tf_ft():
        spec_tt = {"threshold": 50, "active": True, "visible": True}
        records_tt = [
            {"key": "a", "kind": "w", "score": 60, "weight": 3, "active": True, "visible": False},
            {"key": "b", "kind": "w", "score": 60, "weight": 5, "active": False, "visible": True},
        ]
        sink_tt = MagicMock()
        result_tt = apply(records_tt, spec_tt, sink_tt, MagicMock())
        assert len(result_tt) == 0

    def test_boundary_at_threshold():
        spec_b = {"threshold": 50, "active": True, "visible": True}
        assert apply([{"key": "x", "kind": "w", "score": 49, "weight": 3}], spec_b, MagicMock(), MagicMock())[0].status == "rejected"
        assert apply([{"key": "x", "kind": "w", "score": 50, "weight": 3}], spec_b, MagicMock(), MagicMock())[0].status == "accepted"
        assert apply([{"key": "x", "kind": "w", "score": 51, "weight": 3}], spec_b, MagicMock(), MagicMock())[0].status == "accepted"

    def test_normalize_none_uses_fallback():
        assert normalize(None, fallback=10) == 10
        assert normalize(0, fallback=10) == 0
        assert normalize(False, fallback=10) == 0

    def test_wiring_h1():
        sink_w = MagicMock()
        rec = {"key": "r", "kind": "w", "score": 60, "weight": 3}
        apply([rec], {"threshold": 50, "active": True, "visible": True}, sink_w, MagicMock())
        sink_w.emit.assert_called_once_with("accepted", rec, 60.0)
        assert sink_w.emit.call_args.args[1] is rec

    def test_stop_on_first():
        spec_s = {"threshold": 10, "active": True, "visible": True, "stop_on_first": True}
        records_s = [{"key": "a", "kind": "w", "score": 20, "weight": 3}, {"key": "b", "kind": "w", "score": 30, "weight": 5}]
        sink_s = MagicMock()
        apply(records_s, spec_s, sink_s, MagicMock())
        assert sink_s.emit.call_count == 1

    def test_sentinel_is_not_eq():
        assert SKIP is not None
        assert SKIP != SKIP  # sentinel object __eq__
        sentinel = object()
        assert sentinel is not sentinel

    def test_exception_exact_match():
        with pytest.raises(ValueError, match="records must not be empty"):
            apply([], {"threshold": 50}, MagicMock(), MagicMock())

    def test_sink_error_fallback():
        sink_e = MagicMock()
        sink_e.emit.side_effect = SinkError("down")
        result_e = apply([{"key": "r", "kind": "w", "score": 60, "weight": 3}],
                         {"threshold": 50, "active": True, "visible": True},
                         sink_e, MagicMock())
        assert result_e[0].status == "rejected"

    def test_caplog_exact(caplog):
        import logging
        with caplog.at_level(logging.INFO):
            apply([{"key": "k", "kind": "w", "score": 60, "weight": 3}],
                  {"threshold": 50, "active": True, "visible": True},
                  MagicMock(), MagicMock())
        assert any("accepted k score=60.0" in r.message for r in caplog.records)
""")

BAD_TEST = textwrap.dedent("""\
    import pytest
    from quota_broker import apply

    def test_it_works():
        result = apply([], {}, None, None)
        assert result is not None

    def test_something():
        assert "alpha" in str(apply([], {}, None, None))

    def test_len():
        assert len(apply([], {}, None, None)) > 0
""")

SYNTAX_ERROR_TEST = textwrap.dedent("""\
    def test_broken(
        x = 1
""")

NO_SAMPLE_LEAK = textwrap.dedent("""\
    from quota_broker import apply

    def test_fancy():
        result = apply(
            [{"key": "k", "kind": "w", "score": 60, "weight": 3}],
            {"threshold": 50, "active": True, "visible": True},
            __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
            __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(),
        )
        assert result[0].status == "accepted"
        assert result[0].key == "k"
""")

SAMPLE_LEAK = textwrap.dedent("""\
    from quota_broker import apply

    def test_alpha():
        assert apply([], {}, None, None) == "alpha"
""")


@pytest.fixture
def good_test_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_good.py"
    p.write_text(GOOD_TEST, encoding="utf-8")
    return p


@pytest.fixture
def bad_test_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_bad.py"
    p.write_text(BAD_TEST, encoding="utf-8")
    return p


@pytest.fixture
def syntax_error_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_broken.py"
    p.write_text(SYNTAX_ERROR_TEST, encoding="utf-8")
    return p


@pytest.fixture
def no_leak_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_noleak.py"
    p.write_text(NO_SAMPLE_LEAK, encoding="utf-8")
    return p


@pytest.fixture
def leak_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_leak.py"
    p.write_text(SAMPLE_LEAK, encoding="utf-8")
    return p


# ── Tests ───────────────────────────────────────────────────────────

class TestSyntaxDetection:
    def test_good_syntax(self, good_test_file: Path) -> None:
        card = evaluate(good_test_file)
        assert card.syntax_ok

    def test_syntax_error(self, syntax_error_file: Path) -> None:
        card = evaluate(syntax_error_file)
        assert not card.syntax_ok
        assert card.score == 0.0


class TestSurfaceCoverage:
    def test_good_covers_many_surfaces(self, good_test_file: Path) -> None:
        card = evaluate(good_test_file)
        assert card.surfaces_hit >= 10, f"Expected >= 10 surfaces, got {card.surfaces_hit}"

    def test_bad_covers_few_surfaces(self, bad_test_file: Path) -> None:
        card = evaluate(bad_test_file)
        assert card.surfaces_hit <= 15, f"Expected <= 15 surfaces, got {card.surfaces_hit}"

    def test_good_beats_bad(self, good_test_file: Path, bad_test_file: Path) -> None:
        g = evaluate(good_test_file)
        b = evaluate(bad_test_file)
        assert g.score > b.score


class TestPenalties:
    def test_sample_leak_detected(self, leak_file: Path) -> None:
        card = evaluate(leak_file)
        assert card.penalties >= 1

    def test_no_sample_leak(self, no_leak_file: Path) -> None:
        card = evaluate(no_leak_file)
        # Should have 0 penalties related to sample leak
        penalty_ids = [r.id for r in card.results if r.hit and r.category == "forbidden"]
        assert "no_sample_leak" not in penalty_ids

    def test_bad_has_penalties(self, bad_test_file: Path) -> None:
        card = evaluate(bad_test_file)
        assert card.penalties >= 2, f"Expected >= 2 penalties, got {card.penalties}"


class TestScoreRange:
    def test_score_bounded_0_100(self, good_test_file: Path) -> None:
        card = evaluate(good_test_file)
        assert 0 <= card.score <= 100


class TestFormatScorecard:
    def test_output_is_string(self, good_test_file: Path) -> None:
        card = evaluate(good_test_file)
        text = format_scorecard(card)
        assert isinstance(text, str)
        assert "Score:" in text
        assert "Syntax:" in text
