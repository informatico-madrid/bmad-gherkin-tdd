from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _workflow(skill: str) -> dict[str, object]:
    path = ROOT / "skills" / skill / "customize.toml"
    with path.open("rb") as handle:
        return tomllib.load(handle)["workflow"]


def test_default_phase_gates_remain_applicable_for_existing_projects() -> None:
    clean = _workflow("tdd-clean")
    refactor = _workflow("tdd-refactor")
    coordinator = _workflow("bmad-tdd-coordinator")

    assert clean["coverage_cmd"] == "uv run pytest --cov --cov-report=term-missing"
    assert "cleaner_applicable" not in clean
    assert "coverage_applicable" not in clean
    assert "mutation_applicable" not in refactor
    assert coordinator["cleaner_applicable"] is True
    assert coordinator["coverage_applicable"] is True
    assert coordinator["mutation_applicable"] is True
    assert coordinator["cleaner_na_reason"] == ""
    assert coordinator["coverage_na_reason"] == ""
    assert coordinator["mutation_na_reason"] == ""


def test_phase_skills_define_auditable_not_applicable_paths() -> None:
    clean = (ROOT / "skills" / "tdd-clean" / "SKILL.md").read_text(encoding="utf-8")
    refactor = (ROOT / "skills" / "tdd-refactor" / "SKILL.md").read_text(encoding="utf-8")
    coordinator = (ROOT / "skills" / "bmad-tdd-coordinator" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    for key in ("cleaner_applicable", "coverage_applicable"):
        assert key in clean
        assert key in coordinator
    assert "mutation_applicable" in refactor
    assert "mutation_applicable" in coordinator
    assert "N/A" in clean
    assert "N/A" in refactor
    assert "N/A" in coordinator
    assert "central" in clean.lower()
    assert "coordinator" in refactor.lower()


def test_opencode_phase_prompts_are_test_runner_agnostic() -> None:
    template = (ROOT / "opencode" / "agents" / "opencode.json.template").read_text(encoding="utf-8")
    lower = template.lower()

    assert "failing pytest test" not in template
    assert "pytest PASS" not in template
    assert "when `mutation_applicable = false`, record mutation as n/a" in lower
    assert "when clean gates are not applicable, record them as n/a" in lower
