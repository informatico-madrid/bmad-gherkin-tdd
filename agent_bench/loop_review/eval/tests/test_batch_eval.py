"""Closed-loop tests for loop_review eval."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_bench.loop_review.eval.batch_eval import check_surface, fixture_hashes

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "review-hard"
pytestmark = pytest.mark.skipif(
    not (FIXTURE / "src" / "quota_calc.py").is_file(),
    reason="optional loop_review fixture is not materialized",
)


def test_src_edit_fails_against_fixture(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "quota_calc.py").write_text("fixed remaining()\n")
    baseline = fixture_hashes()
    surface = {"id": "no_src_edit", "category": "forbidden", "check": ""}
    assert check_surface(surface, tmp_path, baseline, "") is False


def test_no_brief_fails_protocol(tmp_path: Path):
    ia = tmp_path / "_bmad-output" / "implementation-artifacts"
    ia.mkdir(parents=True)
    baseline = fixture_hashes()
    assert check_surface({"id": "repair_brief_created"}, tmp_path, baseline, "") is False
    assert check_surface({"id": "bug_found_in_brief"}, tmp_path, baseline, "") is False
    assert check_surface({"id": "preexisting_deferred"}, tmp_path, baseline, "") is False
