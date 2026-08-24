"""Closed-loop tests for loop_dev eval. Baseline must be the fixture, not the sandbox."""

from __future__ import annotations

from pathlib import Path

from agent_bench.loop_dev.eval.batch_eval import check_surface, fixture_hashes

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "dev-hard"


def test_fixture_hashes_point_at_fixture_not_empty():
    h = fixture_hashes()
    assert h["src/quota_sync.py"]
    assert h["sprint-status.yaml"]


def test_src_edit_fails_against_fixture_baseline(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "quota_sync.py").write_text("I IMPLEMENTED IT\n")
    tests = tmp_path / "tests" / "unit"
    tests.mkdir(parents=True)
    (tests / "test_quota_sync.py").write_text((FIXTURE / "tests" / "unit" / "test_quota_sync.py").read_text())
    (tmp_path / "sprint-status.yaml").write_text((FIXTURE / "sprint-status.yaml").read_text())
    baseline = fixture_hashes()
    surface = {"id": "no_src_edit", "category": "forbidden", "check": ""}
    assert check_surface(surface, tmp_path, baseline, "") is False


def test_untouched_src_passes(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "quota_sync.py").write_text((FIXTURE / "src" / "quota_sync.py").read_text())
    baseline = fixture_hashes()
    surface = {"id": "no_src_edit", "category": "forbidden", "check": ""}
    assert check_surface(surface, tmp_path, baseline, "") is True
