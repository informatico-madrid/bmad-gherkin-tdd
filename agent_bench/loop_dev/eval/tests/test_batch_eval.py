"""Closed-loop tests for loop_dev eval. Baseline must be the fixture, not the sandbox."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agent_bench.common import tool_names
from agent_bench.loop_dev.eval.batch_eval import (
    _find_spec,
    check_surface,
    evaluate_run,
    fixture_hashes,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "dev-hard"
pytestmark = pytest.mark.skipif(
    not (FIXTURE / "src" / "quota_sync.py").is_file(),
    reason="optional loop_dev fixture is not materialized",
)


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


def test_find_spec_prefers_canonical_story_writeback(tmp_path: Path):
    artifacts = tmp_path / "_bmad-output" / "implementation-artifacts"
    stories = artifacts / "stories"
    stories.mkdir(parents=True)
    (artifacts / "spec-quota-sync-001.md").write_text("---\nstatus: draft\n---\n")
    story = stories / "quota-sync-001-quota-sync.md"
    story.write_text("---\nstatus: blocked\n---\nintent gap\n")

    assert _find_spec(tmp_path) == story.read_text()


def test_find_spec_falls_back_to_legacy_root_spec(tmp_path: Path):
    artifacts = tmp_path / "_bmad-output" / "implementation-artifacts"
    artifacts.mkdir(parents=True)
    spec = artifacts / "spec-quota-sync-001.md"
    spec.write_text("---\nstatus: blocked\n---\n")

    assert _find_spec(tmp_path) == spec.read_text()


def test_question_text_is_not_a_question_tool_invocation(tmp_path: Path):
    surface = {"id": "no_question_asked", "category": "forbidden", "check": ""}

    assert check_surface(
        surface,
        tmp_path,
        {},
        json.dumps({"type": "text", "part": {"text": "Questions requiring resolution"}}),
    ) is True


def test_question_tool_invocation_fails_surface(tmp_path: Path):
    surface = {"id": "no_question_asked", "category": "forbidden", "check": ""}

    assert check_surface(
        surface,
        tmp_path,
        {},
        json.dumps({"type": "tool_use", "part": {"tool": "question"}}),
    ) is False


def test_tool_names_reads_full_opencode_jsonl():
    output = "\n".join(
        (
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "read"}}),
            json.dumps({"type": "text", "part": {"type": "text", "text": "done"}}),
            json.dumps({"type": "tool_use", "part": {"type": "tool", "tool": "question"}}),
        )
    )

    assert tool_names(output) == ["question", "read"]


def test_blocked_spec_without_blocking_reason_fails_output_surface(tmp_path: Path):
    artifacts = tmp_path / "_bmad-output" / "implementation-artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "spec-quota-sync-001.md").write_text("---\nstatus: blocked\n---\n")
    surface = {"id": "spec_written", "category": "output", "check": ""}

    assert check_surface(surface, tmp_path, {}, "") is False


def test_canonical_blocked_story_passes_protocol_and_output(tmp_path: Path):
    stories = tmp_path / "_bmad-output" / "implementation-artifacts" / "stories"
    stories.mkdir(parents=True)
    (stories / "quota-sync-001-quota-sync.md").write_text(
        "---\nstatus: blocked\n---\nBlocking condition: intent gap\n"
    )

    for surface_id in ("intent_gap_halt", "spec_written"):
        surface = {"id": surface_id, "category": "protocol", "check": ""}
        assert check_surface(surface, tmp_path, {}, "") is True


def test_timeout_manifest_forces_zero_score(tmp_path: Path):
    shutil.copytree(FIXTURE, tmp_path / "nan__test")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"results": [{"model": "nan/test", "status": "timeout"}]})
    )

    row = evaluate_run(tmp_path)["rows"][0]

    assert row["status"] == "timeout"
    assert row["score"] == 0.0
