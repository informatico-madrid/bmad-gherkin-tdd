"""Regression tests for the bmad-gherkin-tdd installer CLI.

Covers: fresh install into a throwaway project, idempotent re-install (upgrade),
official BMAD registration (config.yaml section + modules list + module-help.csv),
and uninstall that removes recorded files while preserving user-modified ones and
the project's `_bmad/custom/` overrides.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bmad_gherkin_tdd import installer

PROJECT_ROOT = Path(__file__).parents[1]


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "_bmad").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _load_config(project: Path) -> dict:
    return installer.read_config(project)


def test_install_copies_skills(project: Path) -> None:
    installer.install(project, project / ".agents" / "skills")
    skills_dir = project / ".agents" / "skills"
    for name in installer.SKILL_NAMES:
        assert (skills_dir / name / "SKILL.md").is_file(), name


def test_install_copies_support_files(project: Path) -> None:
    installer.install(project, project / ".agents" / "skills")
    assert (project / "hooks" / "tdd_cycle_gate.py").is_file()
    assert (project / "_bmad" / "scripts" / "resolve_customization.py").is_file()
    assert (project / "_bmad" / "gherkin-tdd" / "docs" / "contract-rules.md").is_file()
    assert (project / ".opencode" / "plugins" / "tdd-cycle-gate.js").is_file()
    assert (project / "opencode" / "agents" / "opencode.json.template").is_file()
    assert (project / "_bmad" / "gherkin-tdd" / "scripts" / "cleaner_gate.py").is_file()
    assert (project / "_bmad" / "gherkin-tdd" / "scripts" / "principles.py").is_file()
    assert (project / "_bmad" / "gherkin-tdd" / "scripts" / "scan_mutation_sites.py").is_file()
    for name in installer.PROFILE_NAMES:
        assert (project / ".bmad-loop" / "profiles" / name).is_file()
    for name in installer.TEMPLATE_NAMES:
        assert (project / "_bmad" / "custom" / name).is_file()


def test_install_registers_module(project: Path) -> None:
    installer.install(project, project / ".agents" / "skills")

    config = _load_config(project)
    assert installer.MODULE_CODE in config, "config.yaml must carry the gherkin-tdd section"
    assert installer.MODULE_CODE in config.get("modules", []), (
        "modules list must include gherkin-tdd"
    )

    help_target = project / "_bmad" / "_config" / "bmad-help.csv"
    assert help_target.is_file()
    text = help_target.read_text(encoding="utf-8")
    assert "BMAD Gherkin TDD" in text and "TDD Coordinator" in text


def test_reinstall_is_idempotent_and_upgradeable(project: Path) -> None:
    installer.install(project, project / ".agents" / "skills")
    skills_dir = project / ".agents" / "skills"
    marker = skills_dir / "bmad-tdd-coordinator" / "SKILL.md"
    marker.write_text("# project-local customization\n", encoding="utf-8")

    # Re-install (no force) must NOT overwrite the project-local skill copy.
    installer.install(project, skills_dir)
    assert "project-local customization" in marker.read_text(encoding="utf-8")

    # Force (upgrade) refreshes the bundled copy.
    installer.install(project, skills_dir, force=True)
    assert "project-local customization" not in marker.read_text(encoding="utf-8")


def test_uninstall_removes_and_preserves(project: Path) -> None:
    installer.install(project, project / ".agents" / "skills")

    # Modify an installed file → uninstall must preserve it.
    resolver = project / "_bmad" / "scripts" / "resolve_customization.py"
    resolver.write_text("# user patch\n", encoding="utf-8")

    report = installer.uninstall(project)

    assert not (project / "hooks" / "tdd_cycle_gate.py").exists()
    assert not (project / "_bmad" / "gherkin-tdd").exists()
    for name in installer.SKILL_NAMES:
        assert not (project / ".agents" / "skills" / name).exists()
    assert resolver.exists(), "modified file must be preserved"
    assert "preserved" in report.get("removed:_bmad/scripts/resolve_customization.py", "")

    config = _load_config(project)
    assert installer.MODULE_CODE not in config
    assert installer.MODULE_CODE not in config.get("modules", [])

    help_target = project / "_bmad" / "_config" / "bmad-help.csv"
    if help_target.exists():
        assert "BMAD Gherkin TDD" not in help_target.read_text(encoding="utf-8")


def test_status_reflects_install(project: Path) -> None:
    assert installer.status(project)["installed"] is False
    installer.install(project, project / ".agents" / "skills")
    st = installer.status(project)
    assert st["installed"] is True
    assert st["version"] == "0.1.1"
    assert installer.manifest_path(project).is_file()


def test_cli_install_and_status(tmp_path: Path) -> None:
    from bmad_gherkin_tdd.cli import main

    project = tmp_path
    assert main(["install", "--project", str(project)]) == 0
    assert main(["status", "--project", str(project)]) == 0
    assert main(["uninstall", "--project", str(project)]) == 0
    assert main(["status", "--project", str(project)]) == 0


def test_install_preserves_and_does_not_claim_preexisting_assets(project: Path) -> None:
    plugin = project / ".opencode" / "plugins" / "tdd-cycle-gate.js"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("// project plugin\n", encoding="utf-8")
    skill = project / ".agents" / "skills" / "tdd-red"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# project skill\n", encoding="utf-8")

    report = installer.install(project, project / ".agents" / "skills", force=True)
    manifest = json.loads(installer.manifest_path(project).read_text(encoding="utf-8"))

    assert plugin.read_text(encoding="utf-8") == "// project plugin\n"
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "# project skill\n"
    assert ".opencode/plugins/tdd-cycle-gate.js" not in manifest["files"]
    assert "tdd-red" not in manifest["skills"]
    assert report["file:.opencode/plugins/tdd-cycle-gate.js"] == "exists (preserved)"
    assert report["skill:tdd-red"] == "exists (preserved)"

    installer.uninstall(project)
    assert plugin.read_text(encoding="utf-8") == "// project plugin\n"
    assert (skill / "SKILL.md").read_text(encoding="utf-8") == "# project skill\n"


def test_uninstall_rejects_tampered_manifest_paths(project: Path, tmp_path: Path) -> None:
    installer.install(project, project / ".agents" / "skills")
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("keep\n", encoding="utf-8")
    manifest_path = installer.manifest_path(project)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["../outside.txt"] = installer._sha256(outside)
    manifest["skills"]["evil"] = {"path": str(outside), "sha256": installer._sha256(outside)}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = installer.uninstall(project)

    assert outside.read_text(encoding="utf-8") == "keep\n"
    assert report["invalid:../outside.txt"] == "ignored (path escapes project)"
    assert report["invalid:skill:evil"] == "ignored (path escapes project)"


def test_install_rejects_skills_dir_outside_project(project: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-external-skills"
    with pytest.raises(ValueError, match="skills_dir must be inside project"):
        installer.install(project, outside)


def test_force_install_preserves_symlinked_skill(project: Path, tmp_path: Path) -> None:
    skills_dir = project / ".agents" / "skills"
    skills_dir.mkdir(parents=True)
    outside = tmp_path.parent / f"{tmp_path.name}-external-skill"
    outside.mkdir()
    marker = outside / "SKILL.md"
    marker.write_text("# external skill\n", encoding="utf-8")
    (skills_dir / "tdd-red").symlink_to(outside, target_is_directory=True)

    report = installer.install(project, skills_dir, force=True)
    manifest = json.loads(installer.manifest_path(project).read_text(encoding="utf-8"))

    assert marker.read_text(encoding="utf-8") == "# external skill\n"
    assert report["skill:tdd-red"] == "exists (preserved)"
    assert "tdd-red" not in manifest["skills"]


def test_install_writes_current_bmad_module_config(project: Path) -> None:
    installer.install(project, project / ".agents" / "skills")

    module_config = installer.read_yaml(project / "_bmad" / "gherkin-tdd" / "config.yaml")
    assert module_config == {
        "contracts_dir": "{project-root}/tests/contracts",
        "implementation_artifacts": "{project-root}/_bmad-output/implementation-artifacts",
    }
