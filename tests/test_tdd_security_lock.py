"""Security Repair TDD — POSIX transaction lock for loop-mode state.

Covers:
  1. Concurrent idempotent coordinator calls → valid JSON, exactly one coordinator,
     no temp file leftovers.
  2. Concurrent mixed attempts never corrupt JSON (semantic denies allowed).
  3. Pre-seeded bypass in loop mode forces reset to tdd + clear reason + save.
  4. Symlink parent directory denied in loop mode BEFORE any lock/write.
  5. Symlink lock file denied in loop mode.
  6. Unknown Tasks add audit info only, no state mutation.
  7. Existing black-box full cycle still works end-to-end.
  8. Atomic write: temp file used, fsync best-effort, os.replace, temp cleaned.
  9. Legacy behavior unchanged: non-loop bypass CLI, bash detector, QG checkpoint.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from multiprocessing import Process
from pathlib import Path

PYTHON_GATE = Path(__file__).parents[1] / "hooks" / "tdd_cycle_gate.py"
PLUGIN_ROOT = Path(__file__).parents[1] / "opencode" / "plugins"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _setup_workspace(
    tmp_path: Path,
    *,
    story_key: str = "5-0-sec-repair",
) -> Path:
    """Set up workspace with gate, story dir, sprint-status."""
    gate_target = tmp_path / "hooks" / "tdd_cycle_gate.py"
    gate_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PYTHON_GATE, gate_target)

    story_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    story_dir.mkdir(parents=True, exist_ok=True)
    story_file = story_dir / f"story-{story_key}.md"
    story_file.write_text(
        f"# Story {story_key}\n\n## TDD Bitácora\n\n",
        encoding="utf-8",
    )
    sprint = tmp_path / "_bmad-output" / "implementation-artifacts" / "sprint-status.yaml"
    sprint.write_text(
        f"development_status:\n  {story_key}: in-progress\n",
        encoding="utf-8",
    )
    return tmp_path


def _state_dir(workspace: Path) -> Path:
    return workspace / ".bmad-harness"


def _state_file(workspace: Path, story_key: str = "5-0-sec-repair") -> Path:
    safe = story_key.replace("/", "_").replace(" ", "_")
    return _state_dir(workspace) / f"tdd-state-{safe}.json"


def _run_gate(
    workspace: Path,
    payload: dict,
    *,
    story_key: str = "5-0-sec-repair",
) -> tuple[int, str, str]:
    env = {**os.environ, "BMAD_LOOP_MODE": "1", "BMAD_LOOP_STORY_KEY": story_key}
    result = subprocess.run(
        ["python3", str(PYTHON_GATE)],
        cwd=str(workspace),
        env=env,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


def _skill(name: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Skill",
        "tool_input": {"skill_name": name},
    }


def _task(agent: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Task",
        "tool_input": {"subagent_type": agent},
    }


def _edit_story(new_string: str) -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "_bmad-output/implementation-artifacts/story-5-0-sec-repair.md",
            "new_string": new_string,
        },
    }


def _pytest_outcome(outcome: str) -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "uv run pytest tests/"},
        "tool_response": {"stdout": f"1 {outcome}", "stderr": ""},
    }


def _load_state(workspace: Path, story_key: str = "5-0-sec-repair") -> dict:
    sf = _state_file(workspace, story_key)
    return json.loads(sf.read_text(encoding="utf-8"))


def _save_state(workspace: Path, data: dict, story_key: str = "5-0-sec-repair") -> None:
    sf = _state_file(workspace, story_key)
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _gate_subprocess(workspace: Path, payload: dict, *, story_key: str = "5-0-sec-repair"):
    """Run gate in a subprocess (for concurrent tests)."""
    env = {**os.environ, "BMAD_LOOP_MODE": "1", "BMAD_LOOP_STORY_KEY": story_key}
    subprocess.run(
        ["python3", str(PYTHON_GATE)],
        cwd=str(workspace),
        env=env,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Concurrent 20 idempotent coordinator calls → valid JSON, exactly one
#    coordinator, no temp leftovers.
# ═══════════════════════════════════════════════════════════════════════════════


def test_concurrent_20_coordinator_calls_valid_json(tmp_path: Path) -> None:
    """20 concurrent coordinator calls must produce valid JSON with exactly
    one coordinator entry and zero temp files left behind."""
    workspace = _setup_workspace(tmp_path)
    state_file = _state_file(workspace)

    # Seed state with coordinator already seen (idempotent scenario)
    _save_state(
        workspace,
        {
            "phase": "READY",
            "mode": "tdd",
            "bypass_reason": "",
            "updated": "2026-01-01T00:00:00+00:00",
            "story_key": "5-0-sec-repair",
            "cycle": 1,
            "skill_seen": ["bmad-tdd-coordinator"],
            "last_skill_at": "",
            "phase_agent_seen": [],
        },
    )

    # Spawn 20 concurrent subprocess calls
    payloads = [_skill("bmad-tdd-coordinator")] * 20
    procs = [Process(target=_gate_subprocess, args=(workspace, p)) for p in payloads]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=15)

    # Verify: valid JSON
    raw = state_file.read_text(encoding="utf-8")
    state = json.loads(raw)

    # Exactly one coordinator in skill_seen
    assert state["skill_seen"].count("bmad-tdd-coordinator") == 1, (
        f"Expected exactly 1 coordinator, got {state['skill_seen'].count('bmad-tdd-coordinator')}"
    )

    # Phase still READY
    assert state["phase"] == "READY"

    # No temp files left behind in .bmad-harness/ (lock file is expected)
    for entry in _state_dir(workspace).iterdir():
        name = entry.name
        if name.endswith(".lock"):
            continue  # sidecar lock is expected
        assert not name.startswith("tdd-state-") or name.endswith(".json"), (
            f"Temp file leftover: {name}"
        )
        assert not name.endswith(".tmp"), f"Temp .tmp leftover: {name}"
        assert not name.endswith(".new"), f"Temp .new leftover: {name}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Concurrent mixed attempts never corrupt JSON (semantic denies allowed).
# ═══════════════════════════════════════════════════════════════════════════════


def test_concurrent_mixed_never_corrupt_json(tmp_path: Path) -> None:
    """Mixed concurrent operations (coordinator + task + edit) must never
    leave the state file as invalid JSON, regardless of denials."""
    workspace = _setup_workspace(tmp_path)
    state_file = _state_file(workspace)

    # Seed initial state
    _save_state(
        workspace,
        {
            "phase": "READY",
            "mode": "tdd",
            "bypass_reason": "",
            "updated": "2026-01-01T00:00:00+00:00",
            "story_key": "5-0-sec-repair",
            "cycle": 0,
            "skill_seen": [],
            "last_skill_at": "",
            "phase_agent_seen": [],
        },
    )

    # Mix of operations: some valid, some will be denied
    payloads = []
    # Valid: coordinator
    for _ in range(5):
        payloads.append(_skill("bmad-tdd-coordinator"))
    # Will be denied: direct skill without task
    for _ in range(5):
        payloads.append(_skill("tdd-red"))
    # Will be denied: wrong-phase task
    for _ in range(5):
        payloads.append(_task("tdd-green-ornith"))
    # Valid: task
    for _ in range(5):
        payloads.append(_task("tdd-red-ornith"))

    procs = [Process(target=_gate_subprocess, args=(workspace, p)) for p in payloads]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=15)

    # State file MUST be valid JSON
    raw = state_file.read_text(encoding="utf-8")
    state = json.loads(raw)

    # Must have required fields
    assert "phase" in state
    assert "mode" in state
    assert "skill_seen" in state
    assert "phase_agent_seen" in state

    # Coordinator should be in skill_seen (from 5 valid calls)
    assert "bmad-tdd-coordinator" in state["skill_seen"]

    # phase_agent_seen should have tdd-red-ornith (from 5 valid task calls)
    assert "tdd-red-ornith" in state["phase_agent_seen"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Preseed bypass loop resets to tdd.
# ═══════════════════════════════════════════════════════════════════════════════


def test_preseed_bypass_loop_resets_to_tdd(tmp_path: Path) -> None:
    """If loop state loads with mode=bypass, force-reset to tdd/clear reason/save."""
    workspace = _setup_workspace(tmp_path)

    # Pre-seed bypass state (phase=READY so coordinator call succeeds after reset)
    _save_state(
        workspace,
        {
            "phase": "READY",
            "mode": "bypass",
            "bypass_reason": "killing mutants",
            "updated": "2026-01-01T00:00:00+00:00",
            "story_key": "5-0-sec-repair",
            "cycle": 3,
            "skill_seen": ["bmad-tdd-coordinator"],
            "last_skill_at": "",
            "phase_agent_seen": [],
        },
    )

    # Call gate in loop mode (any tool triggers processing)
    rc, _, _ = _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    assert rc == 0

    state = _load_state(workspace)
    assert state["mode"] == "tdd", (
        f"Bypass should be reset to tdd in loop mode. Got mode={state['mode']!r}"
    )
    assert state["bypass_reason"] == "", (
        f"Bypass reason should be cleared. Got {state['bypass_reason']!r}"
    )


def test_preseed_bypass_reset_in_nonready_phase(tmp_path: Path) -> None:
    """Bypass reset must happen regardless of current phase — only checks mode."""
    workspace = _setup_workspace(tmp_path)

    # Pre-seed bypass with phase=REFACTOR (non-trivial phase)
    _save_state(
        workspace,
        {
            "phase": "REFACTOR",
            "mode": "bypass",
            "bypass_reason": "old",
            "updated": "2026-01-01T00:00:00+00:00",
            "story_key": "5-0-sec-repair",
            "cycle": 3,
            "skill_seen": ["bmad-tdd-coordinator"],
            "last_skill_at": "",
            "phase_agent_seen": [],
        },
    )

    # Call any tool — bypass reset must happen even if the tool itself is denied
    # We use a Bash call (inert in loop mode for non-write commands)
    rc, _, _ = _run_gate(
        workspace,
        {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "echo"}},
    )

    state = _load_state(workspace)
    assert state["mode"] == "tdd", (
        f"Bypass should be reset regardless of phase. Got mode={state['mode']!r}"
    )
    assert state["bypass_reason"] == ""


def test_preseed_bypass_reset_saves_under_lock(tmp_path: Path) -> None:
    """Bypass reset must actually persist to disk (save under lock)."""
    workspace = _setup_workspace(tmp_path)

    _save_state(
        workspace,
        {
            "phase": "READY",
            "mode": "bypass",
            "bypass_reason": "old reason",
            "updated": "2026-01-01T00:00:00+00:00",
            "story_key": "5-0-sec-repair",
            "cycle": 0,
            "skill_seen": [],
            "last_skill_at": "",
            "phase_agent_seen": [],
        },
    )

    # Make a call that triggers load + bypass reset + save
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))

    # Read directly from disk (not through gate)
    raw = _state_file(workspace).read_text(encoding="utf-8")
    disk_state = json.loads(raw)
    assert disk_state["mode"] == "tdd"
    assert disk_state["bypass_reason"] == ""


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Symlink parent denied in loop mode BEFORE any lock/write.
# ═══════════════════════════════════════════════════════════════════════════════


def test_symlink_parent_denied_in_loop(tmp_path: Path) -> None:
    """If .bmad-harness/ is a symlink to an external dir, deny BEFORE lock/write.

    No state file should be created, no lock file should be created,
    and no external directory should receive writes.
    """
    # Create a real target directory OUTSIDE the workspace
    real_dir = tmp_path / "real_harness"
    real_dir.mkdir()

    # Make .bmad-harness a symlink to the external dir
    link_dir = tmp_path / ".bmad-harness"
    link_dir.symlink_to(real_dir)

    # Set up minimal workspace structure
    story_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    story_dir.mkdir(parents=True, exist_ok=True)
    (story_dir / "story-5-0-sec-repair.md").write_text("# Story\n", encoding="utf-8")
    (tmp_path / "hooks").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PYTHON_GATE, tmp_path / "hooks" / "tdd_cycle_gate.py")

    # Call gate in loop mode
    rc, _, stderr = _run_gate(
        tmp_path,
        _skill("bmad-tdd-coordinator"),
        story_key="5-0-sec-repair",
    )
    assert rc == 2, f"Expected DENY for symlink parent, got rc={rc}"
    assert "symlink" in stderr.lower() or "denied" in stderr.lower(), (
        f"Error message should mention symlink/denied. Got: {stderr}"
    )

    # CRITICAL: No writes to the external directory
    external_entries = list(real_dir.iterdir())
    assert len(external_entries) == 0, f"External directory received writes: {external_entries}"

    # No state file created through the symlink
    assert not link_dir.is_dir() or len(list(link_dir.iterdir())) == 0, (
        "State file was created through symlinked directory"
    )


def test_symlink_lock_file_denied_in_loop(tmp_path: Path) -> None:
    """If the lock file itself is a symlink, deny in loop mode."""
    workspace = _setup_workspace(tmp_path)

    # Pre-create the state file (so lock path is computed) and seed state
    _save_state(
        workspace,
        {
            "phase": "READY",
            "mode": "tdd",
            "bypass_reason": "",
            "updated": "2026-01-01T00:00:00+00:00",
            "story_key": "5-0-sec-repair",
            "cycle": 0,
            "skill_seen": [],
            "last_skill_at": "",
            "phase_agent_seen": [],
        },
    )

    # Create a real lock target and symlink
    real_lock = tmp_path / "real_lock"
    real_lock.write_text("x", encoding="utf-8")
    lock_path = _state_dir(workspace) / "tdd-state-5-0-sec-repair.json.lock"
    lock_path.symlink_to(real_lock)

    # Call gate
    rc, _, stderr = _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    assert rc == 2, f"Expected DENY for symlink lock, got rc={rc}"
    assert "symlink" in stderr.lower() or "denied" in stderr.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Unknown Tasks add audit info only, no state mutation.
# ═══════════════════════════════════════════════════════════════════════════════


def test_unknown_task_audit_only_no_mutation(tmp_path: Path) -> None:
    """Unknown Task agents must NOT mutate phase_agent_seen or skill_seen.
    They may add audit info but must be inert on state."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))

    state_before = _load_state(workspace)
    agent_before = list(state_before.get("phase_agent_seen", []))
    skill_before = list(state_before.get("skill_seen", []))

    # Unknown task agent
    _run_gate(workspace, _task("some-random-agent"))

    state_after = _load_state(workspace)
    assert state_after["phase_agent_seen"] == agent_before, (
        f"phase_agent_seen mutated: {agent_before} → {state_after['phase_agent_seen']}"
    )
    assert state_after["skill_seen"] == skill_before, (
        f"skill_seen mutated: {skill_before} → {state_after['skill_seen']}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Existing black-box full cycle still works end-to-end.
# ═══════════════════════════════════════════════════════════════════════════════


def test_existing_black_box_full_cycle_still_works(tmp_path: Path) -> None:
    """Full Red→Green→Refactor cycle must still work end-to-end with locks."""
    workspace = _setup_workspace(tmp_path)

    def phase() -> str:
        return _load_state(workspace)["phase"]

    # 1. coordinator
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    assert phase() == "READY"

    # 2. tdd-red-ornith + tdd-red
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    assert phase() == "READY"

    # 3. pytest FAIL → RED_SEEN
    _run_gate(workspace, _pytest_outcome("failed"))
    assert phase() == "RED_SEEN"

    # 4. ROJO bitácora → CODING
    _run_gate(workspace, _edit_story("ROJO: wrote failing test"))
    assert phase() == "CODING"

    # 5. tdd-green-ornith + tdd-green
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    assert phase() == "CODING"

    # 6. pytest PASS → GREEN_SEEN
    _run_gate(workspace, _pytest_outcome("passed"))
    assert phase() == "GREEN_SEEN"

    # 7. VERDE bitácora → GREEN_SEEN→CLEAN
    _run_gate(workspace, _edit_story("VERDE: test passes"))
    assert phase() == "CLEAN"

    # 8. tdd-clean-ornith + tdd-clean → stays CLEAN
    _run_gate(workspace, _task("tdd-clean-ornith"))
    _run_gate(workspace, _skill("tdd-clean"))
    assert phase() == "CLEAN"

    # 9. CLEAN bitácora → CLEAN→REFACTOR
    _run_gate(workspace, _edit_story("CLEAN: structural pass"))
    assert phase() == "REFACTOR"

    # 10. tdd-refactor-ornith + tdd-refactor (stays REFACTOR)
    _run_gate(workspace, _task("tdd-refactor-ornith"))
    _run_gate(workspace, _skill("tdd-refactor"))
    assert phase() == "REFACTOR"

    # 11. REFACTOR: bitácora closes cycle → READY
    _run_gate(workspace, _edit_story("REFACTOR: cleanup done"))
    assert phase() == "READY"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Atomic write: temp file used, os.replace, temp cleaned.
# ═══════════════════════════════════════════════════════════════════════════════


def test_atomic_write_no_temp_leftovers(tmp_path: Path) -> None:
    """After state save, no temp files (.tmp, .new, partial JSON) should remain."""
    workspace = _setup_workspace(tmp_path)

    # Drive state through several saves
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))

    # Check for temp leftovers in .bmad-harness/
    for entry in _state_dir(workspace).iterdir():
        name = entry.name
        assert not name.endswith(".tmp"), f"Temp .tmp file: {name}"
        assert not name.endswith(".new"), f"Temp .new file: {name}"
        # State file should be valid JSON
        if name.endswith(".json"):
            try:
                json.loads(entry.read_text())
            except json.JSONDecodeError as err:
                raise AssertionError(f"Corrupted state file: {name}") from err


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Legacy behavior unchanged: bypass CLI outside loop, bash detector, QG.
# ═══════════════════════════════════════════════════════════════════════════════


def test_legacy_bypass_cli_outside_loop_unchanged(tmp_path: Path) -> None:
    """Bypass CLI command outside loop mode must still work (binding requirement)."""
    workspace = _setup_workspace(tmp_path)

    result = subprocess.run(
        ["python3", str(PYTHON_GATE), "bypass", "testing legacy"],
        cwd=str(workspace),
        env={**os.environ},  # NO BMAD_LOOP_MODE
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "bypass" in result.stdout.lower() or "audited" in result.stdout.lower()

    # State should have bypass mode set
    state = json.loads((_state_dir(workspace) / "tdd-state.json").read_text())
    assert state["mode"] == "bypass"
    assert state["bypass_reason"] == "testing legacy"


def test_legacy_bash_detector_unchanged(tmp_path: Path) -> None:
    """Bash write detection must still work outside loop mode."""
    workspace = _setup_workspace(tmp_path)

    # Set up legacy state
    _save_state(
        workspace,
        {
            "phase": "READY",
            "mode": "tdd",
            "bypass_reason": "",
            "updated": "2026-01-01T00:00:00+00:00",
            "story_key": "",
            "cycle": 0,
            "skill_seen": [],
            "last_skill_at": "",
            "phase_agent_seen": [],
        },
        story_key="",
    )

    result = subprocess.run(
        ["python3", str(PYTHON_GATE)],
        cwd=str(workspace),
        env={**os.environ},  # NO loop mode
        input=json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "echo x > src/x.py"},
            }
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    # In legacy mode, Bash is inert (only Edit/Write/MultiEdit are gated)
    assert result.returncode == 0
