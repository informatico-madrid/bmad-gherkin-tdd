"""Regression guard — the module's bmad-dev-auto override template must resolve,
through the module's resolve_customization.py, into a handoff that routes the
unattended dev primitive through the TDD coordinator.

Builds a throwaway project under tmp_path:
  {tmp}/_bmad/custom/bmad-dev-auto.toml      <- copied from templates/custom/
  {tmp}/_bmad/custom/bmad-tdd-coordinator.toml <- empty (no project overrides)
  {tmp}/_bmad/scripts/resolve_customization.py <- module resolver
  {tmp}/skills/bmad-dev-auto/customize.toml     <- layer-3 default (empty)
  {tmp}/skills/bmad-tdd-coordinator/customize.toml <- layer-3 default
  {tmp}/skills/bmad-tdd-coordinator/SKILL.md / prompt.txt
  {tmp}/_bmad/  (project root marker for the resolver)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).parents[1]


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Assemble a minimal BMAD project that exercises the module's templates."""
    # Project marker + custom override layer.
    bmad = tmp_path / "_bmad"
    custom = bmad / "custom"
    custom.mkdir(parents=True, exist_ok=True)
    scripts = bmad / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)

    # The override template under test.
    shutil.copy2(
        MODULE_ROOT / "templates" / "custom" / "bmad-dev-auto.toml",
        custom / "bmad-dev-auto.toml",
    )
    # The coordinator override template (the coordination routine that lists the
    # phase subagents and the frontier clauses).
    shutil.copy2(
        MODULE_ROOT / "templates" / "custom" / "bmad-tdd-coordinator.toml",
        custom / "bmad-tdd-coordinator.toml",
    )
    # The resolver.
    shutil.copy2(
        MODULE_ROOT / "scripts" / "resolve_customization.py", scripts / "resolve_customization.py"
    )

    # Layer-3 skill defaults for bmad-dev-auto (upstream shape: empty workflow
    # so the override layer is the only source of the handoff).
    dev_auto_skill = tmp_path / "skills" / "bmad-dev-auto"
    dev_auto_skill.mkdir(parents=True, exist_ok=True)
    (dev_auto_skill / "customize.toml").write_text(
        "[workflow]\nactivation_steps_prepend = []\n"
        'activation_steps_append = []\npersistent_facts = []\non_complete = ""\n',
        encoding="utf-8",
    )

    # Layer-3 skill defaults + content for the coordinator (its customize.toml
    # and the two audited sources).
    coord_skill = tmp_path / "skills" / "bmad-tdd-coordinator"
    coord_skill.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        MODULE_ROOT / "skills" / "bmad-tdd-coordinator" / "customize.toml",
        coord_skill / "customize.toml",
    )
    shutil.copy2(
        MODULE_ROOT / "skills" / "bmad-tdd-coordinator" / "SKILL.md",
        coord_skill / "SKILL.md",
    )
    shutil.copy2(
        MODULE_ROOT / "skills" / "bmad-tdd-coordinator" / "prompt.txt",
        coord_skill / "prompt.txt",
    )
    return tmp_path


def _resolve(project: Path, skill_dir: Path, key: str | None = None) -> dict:
    args = [
        sys.executable,
        str(project / "_bmad" / "scripts" / "resolve_customization.py"),
        "-s",
        str(skill_dir),
    ]
    if key:
        args += ["-k", key]
    result = subprocess.run(
        args,
        cwd=str(project),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"resolve_customization.py failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    return json.loads(result.stdout)


def _resolved_handoff(project: Path) -> str:
    data = _resolve(
        project, project / "skills" / "bmad-dev-auto", "workflow.implementation_handoff"
    )
    assert "workflow.implementation_handoff" in data, list(data.keys())
    return data["workflow.implementation_handoff"]


def _resolved_workflow(project: Path) -> dict:
    return _resolve(project, project / "skills" / "bmad-dev-auto")


def _resolved_coordinator_text(project: Path) -> str:
    data = _resolve(project, project / "skills" / "bmad-tdd-coordinator")
    wf = data.get("workflow", {})
    parts: list[str] = []
    for key in ("activation_steps_prepend", "activation_steps_append", "persistent_facts"):
        parts.extend(wf.get(key, []) or [])
    parts.append(wf.get("on_complete", "") or "")
    return "\n".join(parts)


def test_toml_contains_implementation_handoff_key(project: Path) -> None:
    """The template MUST define implementation_handoff explicitly."""
    content = (project / "_bmad" / "custom" / "bmad-dev-auto.toml").read_text(encoding="utf-8")
    assert "implementation_handoff" in content


def test_handoff_references_tdd_coordinator_skill(project: Path) -> None:
    """Resolved handoff MUST invoke bmad-tdd-coordinator by name."""
    assert "bmad-tdd-coordinator" in _resolved_handoff(project)


def test_handoff_contains_spec_file_placeholder(project: Path) -> None:
    """Resolved handoff MUST contain literal {spec_file} for runtime substitution."""
    assert "{spec_file}" in _resolved_handoff(project)


def test_handoff_invokes_dev_this_story_phrase(project: Path) -> None:
    """Resolved handoff MUST contain exact phrase 'dev this story {spec_file}'."""
    assert "dev this story {spec_file}" in _resolved_handoff(project)


def test_handoff_does_not_contain_generic_subagent_default(project: Path) -> None:
    """Resolved handoff MUST NOT be the upstream generic default."""
    handoff = _resolved_handoff(project)
    assert "Launch a subagent with no prior conversation context" not in handoff
    assert "Read {spec_file} fully and implement it" not in handoff


def test_resolved_workflow_has_tdd_delegation_gates(project: Path) -> None:
    """The append steps must carry the TDD delegation gates."""
    wf = _resolved_workflow(project)
    steps = "\n".join(wf.get("workflow", {}).get("activation_steps_append", []) or [])
    for gate in ("TDD DELEGATION GATE", "TDD SUBAGENT TYPES GATE", "CLOSURE GATE"):
        assert gate in steps, f"missing gate {gate}"
    assert "RED -> GREEN -> CLEAN -> REFACTOR" in steps
    assert "durable four-phase bitacora" in steps


def test_handoff_returns_to_outer_workflow_in_order(project: Path) -> None:
    """The TDD subflow must return to the real outer Verify→Review path."""
    handoff = _resolved_handoff(project)
    required = [
        "return to bmad-dev-auto",
        "resume bmad-dev-auto step-03 Implement at Verify",
        "then read and follow ./step-04-review.md",
        "do not end the outer turn",
    ]
    missing = [p for p in required if p not in handoff]
    assert missing == [], f"implementation_handoff missing required phrase(s): {missing}\n{handoff}"
    positions = [handoff.index(p) for p in required]
    assert positions == sorted(positions), (
        f"implementation_handoff must order phrases as {required}, "
        f"found positions {positions}\n{handoff}"
    )


def test_on_complete_requires_completion_contract_clauses(project: Path) -> None:
    """on_complete must run the WORKFLOW_COMPLETION_CONTRACT."""
    on_complete = _resolved_workflow(project)["workflow"]["on_complete"]
    required = [
        "WORKFLOW_COMPLETION_CONTRACT",
        "status: done",
        "Auto Run Result",
        "bmad-dev-auto-result-",
        "{implementation_artifacts}",
    ]
    missing = [c for c in required if c not in on_complete]
    assert missing == [], (
        f"workflow.on_complete missing required clause(s): {missing}\n{on_complete!r}"
    )


def test_coordinator_frontier_present_in_resolved_workflow(project: Path) -> None:
    """The coordinator's resolved workflow must carry the implementation-only
    subflow frontier and the TDD subagent routing."""
    resolved_text = _resolved_coordinator_text(project)
    required = [
        "tdd-red-ornith",
        "tdd-green-ornith",
        "tdd-refactor-ornith",
        "tdd-clean-ornith",
    ]
    missing = [c for c in required if c not in resolved_text]
    assert missing == [], (
        f"Resolved bmad-tdd-coordinator workflow missing clause(s): {missing}\n{resolved_text}"
    )
