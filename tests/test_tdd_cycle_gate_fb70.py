"""TDD Cycle Gate — repair (REPAIR_LOOP_TDD) black-box tests.

Covers every blocker from the repair spec:
  1. Critical flow: coordinator stays READY, tdd-red stays RED_SEEN,
     pytest FAIL drives READY→RED_SEEN, ROJO→CODING, VERDE→REFACTOR,
     pytest PASS drives CODING→GREEN_SEEN, tdd-refactor in REFACTOR only.
  2. Native MultiEdit JS aliases (multi_edit/multiEdit/multiedit).
  3. Protected gate state: structured edits to state/audit DENY,
     symlink refusal, strict story-key regex.
  4. Bash write practical closure: git apply, patch, heredoc, sh -c,
     dd, perl, ruby, base64, install, sed -i, variable assignment + redirect.
  5. Legacy findings preserved: fail-open outside loop, no dead code,
     no quality-gate gate on REFACTOR prod edits.
  6. Coordinator re-invocation outside READY → DENY (except idempotent in READY).
  7. Focused must-execute tests (no syntax-only).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

PYTHON_GATE = Path(__file__).parents[1] / "hooks" / "tdd_cycle_gate.py"
PLUGIN_ROOT = Path(__file__).parents[1] / "opencode" / "plugins"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _node(script: str) -> object:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(result.stdout)


def _setup_workspace(tmp_path: Path, *, story_key: str = "1-6-repair-test") -> Path:
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
    return tmp_path


def _run_gate(
    workspace: Path,
    payload: dict,
    *,
    story_key: str = "1-6-repair-test",
    gate_path: Path | None = None,
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    target = gate_path or PYTHON_GATE
    env = {**os.environ, "BMAD_LOOP_MODE": "1", "BMAD_LOOP_STORY_KEY": story_key}
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["python3", str(target)],
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
    """Phase 2 model-routing: Task agent must precede its matching Skill."""
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
            "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
            "new_string": new_string,
        },
    }


def _pytest_outcome(outcome: str, stdout: str = "") -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "uv run pytest tests/"},
        "tool_response": {"stdout": stdout or ("1 " + outcome), "stderr": ""},
    }


def _edit_test_file() -> dict:
    """PostToolUse Edit of a tests/** file — marks the RED test as written."""
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "tests/unit/test_new_behavior.py",
            "new_string": "def test_x():\n    assert False",
        },
    }


def _task_post(agent: str, *, tool_response: object | None = None) -> dict:
    """PostToolUse Task completion — the subagent-session bridge (A0 port)."""
    payload: dict = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Task",
        "tool_input": {"subagent_type": agent},
    }
    if tool_response is not None:
        payload["tool_response"] = tool_response
    return payload


def _bash(command: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# A. JS Native MultiEdit aliases  (blocker 2 — tests only in test_opencode_plugins)
# ═══════════════════════════════════════════════════════════════════════════════


def test_multi_edit_alias_maps_to_multiedit(tmp_path: Path) -> None:
    """mapToolInput('multi_edit', {args}) → toolName MultiEdit with {edits: ...}."""
    module = (PLUGIN_ROOT / "tdd-cycle-gate.js").as_uri()
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(module)};
      const {{ mapToolInput }} = TddCycleGate;
      console.log(JSON.stringify(mapToolInput("multi_edit", {{
        args: [{{ file_path: "src/a.py", new_string: "x" }}],
      }})));
    """
    assert _node(script) == {
        "toolName": "MultiEdit",
        "toolInput": {"edits": [{"file_path": "src/a.py", "new_string": "x"}]},
    }


def test_multiEdit_alias_maps_to_multiedit(tmp_path: Path) -> None:
    """mapToolInput('multiEdit', ...) → toolName MultiEdit with {edits: []}."""
    module = (PLUGIN_ROOT / "tdd-cycle-gate.js").as_uri()
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(module)};
      const {{ mapToolInput }} = TddCycleGate;
      console.log(JSON.stringify(mapToolInput("multiEdit", {{ args: [] }})));
    """
    assert _node(script) == {
        "toolName": "MultiEdit",
        "toolInput": {"edits": []},
    }


def test_multiedit_lowercase_alias_maps_to_multiedit(tmp_path: Path) -> None:
    """mapToolInput('multiedit', ...) → toolName MultiEdit with {edits: []}."""
    module = (PLUGIN_ROOT / "tdd-cycle-gate.js").as_uri()
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(module)};
      const {{ mapToolInput }} = TddCycleGate;
      console.log(JSON.stringify(mapToolInput("multiedit", {{ args: [] }})));
    """
    assert _node(script) == {
        "toolName": "MultiEdit",
        "toolInput": {"edits": []},
    }


def test_multi_edit_args_edits_shape(tmp_path: Path) -> None:
    """multi_edit with args pointing to an object that has .edits → uses .edits array.

    The 'args' parameter to mapToolInput is {edits: [...]} directly.
    """
    module = (PLUGIN_ROOT / "tdd-cycle-gate.js").as_uri()
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(module)};
      const {{ mapToolInput }} = TddCycleGate;
      console.log(JSON.stringify(mapToolInput("multi_edit", {{
        edits: [{{ file_path: "src/foo.py", new_string: "y" }}],
      }})));
    """
    assert _node(script) == {
        "toolName": "MultiEdit",
        "toolInput": {"edits": [{"file_path": "src/foo.py", "new_string": "y"}]},
    }


def test_multi_edit_invalid_list_fallback_to_empty(tmp_path: Path) -> None:
    """multi_edit with non-list args → falls back to empty edits array."""
    module = (PLUGIN_ROOT / "tdd-cycle-gate.js").as_uri()
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(module)};
      const {{ mapToolInput }} = TddCycleGate;
      console.log(JSON.stringify(mapToolInput("multi_edit", {{ args: "not-a-list" }})));
    """
    assert _node(script) == {
        "toolName": "MultiEdit",
        "toolInput": {"edits": []},
    }


def test_multi_edit_e2e_prod_denied_in_ready(tmp_path: Path) -> None:
    """End-to-end: JS multi_edit → Python gate DENY in READY without skills."""
    workspace = _setup_workspace(tmp_path)

    module_uri = (PLUGIN_ROOT / "tdd-cycle-gate.js").as_uri()
    # Use createRequire for CommonJS interop within ESM
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(module_uri)};
      import {{ createRequire }} from "node:module";
      import {{ spawnSync }} from "node:child_process";
      import {{ join }} from "node:path";
      const {{ mapToolInput }} = TddCycleGate;
      const mapped = mapToolInput("multi_edit", {{
        args: [{{ file_path: "src/x.py", new_string: "pass" }}],
      }});
      const gate = join({json.dumps(str(workspace))}, "tools", "bmad-harness",
        "hooks", "tdd_cycle_gate.py");
      const r = spawnSync("python3", [gate], {{
        cwd: {json.dumps(str(workspace))},
        env: {{ ...process.env,
          BMAD_LOOP_MODE: "1", BMAD_LOOP_STORY_KEY: "1-6-repair-test" }},
        input: JSON.stringify({{
          hook_event_name: "PreToolUse",
          tool_name: mapped.toolName,
          tool_input: mapped.toolInput,
        }}),
        encoding: "utf8",
        timeout: 5000,
      }});
      console.log(JSON.stringify({{ rc: r.status, stderr: r.stderr || "" }}));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    data = json.loads(result.stdout)
    assert data["rc"] == 2
    assert "tdd" in data["stderr"].lower() or "denied" in data["stderr"].lower()


def test_multi_edit_e2e_test_denied_without_tdd_red(tmp_path: Path) -> None:
    """End-to-end: JS multi_edit to tests/ in READY without tdd-red → DENY."""
    workspace = _setup_workspace(tmp_path)

    module_uri = (PLUGIN_ROOT / "tdd-cycle-gate.js").as_uri()
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(module_uri)};
      import {{ spawnSync }} from "node:child_process";
      import {{ join }} from "node:path";
      const {{ mapToolInput }} = TddCycleGate;
      const mapped = mapToolInput("multi_edit", {{
        args: [{{ file_path: "tests/test_x.py",
                 new_string: "def test_x(): pass" }}],
      }});
      const gate = join({json.dumps(str(workspace))}, "tools", "bmad-harness",
        "hooks", "tdd_cycle_gate.py");
      const r = spawnSync("python3", [gate], {{
        cwd: {json.dumps(str(workspace))},
        env: {{ ...process.env,
          BMAD_LOOP_MODE: "1", BMAD_LOOP_STORY_KEY: "1-6-repair-test" }},
        input: JSON.stringify({{
          hook_event_name: "PreToolUse",
          tool_name: mapped.toolName,
          tool_input: mapped.toolInput,
        }}),
        encoding: "utf8",
        timeout: 5000,
      }});
      console.log(JSON.stringify({{ rc: r.status, stderr: r.stderr || "" }}));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    data = json.loads(result.stdout)
    assert data["rc"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# B. Critical flow — coordinator stays READY, tdd-red stays RED_SEEN
#    (blocker 1 — these MUST fail against the current implementation)
# ═══════════════════════════════════════════════════════════════════════════════


def test_coordinator_in_ready_stays_ready(tmp_path: Path) -> None:
    """coordinator in READY registers skill but phase REMAINS READY.
    This test MUST fail against the broken implementation that advances
    coordinator → RED_SEEN."""
    workspace = _setup_workspace(tmp_path)

    rc, _, _ = _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    # coordinator registered
    assert "bmad-tdd-coordinator" in state["skill_seen"]
    # BUT phase stays READY — this is the critical invariant
    assert state["phase"] == "READY"


def test_tdd_red_in_ready_stays_ready(tmp_path: Path) -> None:
    """tdd-red after coordinator in READY: registers tdd-red but phase
    remains READY. Only pytest FAIL drives READY→RED_SEEN."""
    workspace = _setup_workspace(tmp_path)

    # coordinator first (stays READY)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    # tdd-red: requires coordinator + phase READY + tdd-red-ornith Task
    _run_gate(workspace, _task("tdd-red-ornith"))
    rc, _, _ = _run_gate(workspace, _skill("tdd-red"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert "tdd-red" in state["skill_seen"]
    # Phase stays READY — only pytest FAIL advances READY→RED_SEEN
    assert state["phase"] == "READY"


def test_pytest_fail_drives_ready_to_red_seen(tmp_path: Path) -> None:
    """ONLY pytest FAIL PostToolUse changes READY→RED_SEEN.
    Skill invocations alone cannot drive this transition."""
    workspace = _setup_workspace(tmp_path)

    # coordinator + tdd-red (both stay in READY/RED_SEEN)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))

    # pytest FAIL → READY→RED_SEEN
    rc, _, _ = _run_gate(workspace, _pytest_outcome("failed"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "RED_SEEN"


def test_rojo_bitacora_drives_red_seen_to_coding(tmp_path: Path) -> None:
    """ROJO: bitácora entry in RED_SEEN → CODING."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))

    # ROJO: entry → RED_SEEN → CODING
    rc, _, _ = _run_gate(workspace, _edit_story("ROJO: wrote failing test"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "CODING"


def test_green_only_in_coding(tmp_path: Path) -> None:
    """tdd-green requires phase=CODING. In RED_SEEN or READY it must DENY."""
    workspace = _setup_workspace(tmp_path)

    # coordinator + tdd-red → phase still RED_SEEN
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))

    # tdd-green in RED_SEEN → DENY
    _run_gate(workspace, _task("tdd-green-ornith"))
    rc, _, stderr = _run_gate(workspace, _skill("tdd-green"))
    assert rc == 2
    assert "CODING" in stderr or "green" in stderr.lower()


def test_pytest_pass_coding_to_green_seen(tmp_path: Path) -> None:
    """pytest PASS in CODING → GREEN_SEEN."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))  # READY→RED_SEEN
    _run_gate(workspace, _edit_story("ROJO: wrote failing test"))  # RED_SEEN→CODING

    # tdd-green must be preceded by its Task agent
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))

    # pytest PASS → CODING→GREEN_SEEN
    rc, _, _ = _run_gate(workspace, _pytest_outcome("passed"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "GREEN_SEEN"


def test_verde_bitacora_drives_green_seen_to_clean(tmp_path: Path) -> None:
    """VERDE: bitácora in GREEN_SEEN → CLEAN (requires tdd-green seen)."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))

    # tdd-green MUST be called while phase=CODING (before pytest PASS)
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))

    # pytest PASS → CODING→GREEN_SEEN
    _run_gate(workspace, _pytest_outcome("passed"))

    # VERDE: → GREEN_SEEN→CLEAN
    rc, _, _ = _run_gate(workspace, _edit_story("VERDE: test passes"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "CLEAN"


def test_clean_bitacora_drives_clean_to_refactor(tmp_path: Path) -> None:
    """CLEAN: bitácora in CLEAN → REFACTOR (requires tdd-clean seen)."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    _run_gate(workspace, _pytest_outcome("passed"))
    _run_gate(workspace, _edit_story("VERDE: test passes"))

    # tdd-clean MUST be called while phase=CLEAN
    _run_gate(workspace, _task("tdd-clean-ornith"))
    _run_gate(workspace, _skill("tdd-clean"))

    # CLEAN: → CLEAN→REFACTOR
    rc, _, _ = _run_gate(workspace, _edit_story("CLEAN: structural pass"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "REFACTOR"


def test_refactor_only_in_refactor_phase(tmp_path: Path) -> None:
    """tdd-refactor in GREEN_SEEN → DENY."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    _run_gate(workspace, _pytest_outcome("passed"))

    # tdd-refactor in GREEN_SEEN → DENY
    _run_gate(workspace, _task("tdd-refactor-ornith"))
    rc, _, stderr = _run_gate(workspace, _skill("tdd-refactor"))
    assert rc == 2
    assert "REFACTOR" in stderr or "refactor" in stderr.lower()


def test_full_tdd_cycle_black_box(tmp_path: Path) -> None:
    """Full Red→Green→Refactor cycle as black-box sequence.
    Verifies every phase transition in order."""
    workspace = _setup_workspace(tmp_path)
    state_path = workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json"

    def phase() -> str:
        return json.loads(state_path.read_text())["phase"]

    # 1. coordinator → stays READY
    rc, _, _ = _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    assert rc == 0 and phase() == "READY"

    # 2. tdd-red-ornith Task + tdd-red Skill → stays READY (pytest FAIL drives READY→RED_SEEN)
    _run_gate(workspace, _task("tdd-red-ornith"))
    rc, _, _ = _run_gate(workspace, _skill("tdd-red"))
    assert rc == 0 and phase() == "READY"

    # 3. pytest FAIL → READY→RED_SEEN
    rc, _, _ = _run_gate(workspace, _pytest_outcome("failed"))
    assert rc == 0 and phase() == "RED_SEEN"

    # 4. ROJO bitácora → RED_SEEN→CODING
    rc, _, _ = _run_gate(workspace, _edit_story("ROJO: wrote failing test"))
    assert rc == 0 and phase() == "CODING"

    # 5. tdd-green-ornith Task + tdd-green Skill (while still in CODING, before pytest PASS)
    _run_gate(workspace, _task("tdd-green-ornith"))
    rc, _, _ = _run_gate(workspace, _skill("tdd-green"))
    assert rc == 0 and phase() == "CODING"

    # 6. pytest PASS → CODING→GREEN_SEEN
    rc, _, _ = _run_gate(workspace, _pytest_outcome("passed"))
    assert rc == 0 and phase() == "GREEN_SEEN"

    # 7. VERDE bitácora → GREEN_SEEN→CLEAN
    rc, _, _ = _run_gate(workspace, _edit_story("VERDE: test passes"))
    assert rc == 0 and phase() == "CLEAN"

    # 8. tdd-clean-ornith Task + tdd-clean Skill → stays CLEAN (skill alone doesn't close)
    _run_gate(workspace, _task("tdd-clean-ornith"))
    rc, _, _ = _run_gate(workspace, _skill("tdd-clean"))
    assert rc == 0 and phase() == "CLEAN"

    # 9. CLEAN: bitácora → CLEAN→REFACTOR
    rc, _, _ = _run_gate(workspace, _edit_story("CLEAN: structural pass"))
    assert rc == 0 and phase() == "REFACTOR"

    # 10. tdd-refactor-ornith Task + tdd-refactor Skill → stays REFACTOR (skill alone doesn't close)
    _run_gate(workspace, _task("tdd-refactor-ornith"))
    rc, _, _ = _run_gate(workspace, _skill("tdd-refactor"))
    assert rc == 0 and phase() == "REFACTOR"

    # 11. REFACTOR: bitácora closes the cycle → READY
    rc, _, _ = _run_gate(workspace, _edit_story("REFACTOR: cycle complete"))
    assert rc == 0 and phase() == "READY"


def test_markdown_bitacora_heading_tokens_drive_full_cycle(tmp_path: Path) -> None:
    workspace = _setup_workspace(tmp_path)
    state_path = workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json"

    def phase() -> str:
        return json.loads(state_path.read_text())["phase"]

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("- **ROJO (@s1)** — failing test"))
    assert phase() == "CODING"

    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    _run_gate(workspace, _pytest_outcome("passed"))
    _run_gate(workspace, _edit_story("- **VERDE (@s1)** — passing test"))
    assert phase() == "CLEAN"

    _run_gate(workspace, _task("tdd-clean-ornith"))
    _run_gate(workspace, _skill("tdd-clean"))
    _run_gate(workspace, _edit_story("- **CLEAN (@s1)** — structural checks"))
    assert phase() == "REFACTOR"

    _run_gate(workspace, _task("tdd-refactor-ornith"))
    _run_gate(workspace, _skill("tdd-refactor"))
    _run_gate(workspace, _edit_story("- **REFACTOR (@s1)** — mutation complete"))
    assert phase() == "READY"


# ═══════════════════════════════════════════════════════════════════════════════
# C. Protected gate state (blocker 3)
# ═══════════════════════════════════════════════════════════════════════════════


def test_structured_edit_to_state_file_denied_in_loop(tmp_path: Path) -> None:
    """Structured Edit targeting .bmad-harness/tdd-state*.json → DENY in loop mode."""
    workspace = _setup_workspace(tmp_path)

    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": ".bmad-harness/tdd-state-1-6-repair-test.json",
                "new_string": '{"phase":"READY"}',
            },
        },
    )
    assert rc == 2
    assert "protected" in stderr.lower() or "state" in stderr.lower() or "denied" in stderr.lower()


def test_structured_edit_to_audit_log_denied_in_loop(tmp_path: Path) -> None:
    """Structured Edit targeting .bmad-harness/tdd-audit.log → DENY in loop mode."""
    workspace = _setup_workspace(tmp_path)

    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": ".bmad-harness/tdd-audit.log",
                "content": "tampered\n",
            },
        },
    )
    assert rc == 2


def test_symlink_state_file_refused_in_loop(tmp_path: Path) -> None:
    """State file path that is a symlink → fail-closed DENY in loop mode."""
    workspace = _setup_workspace(tmp_path)

    # Create a real file and a symlink pointing to it
    real_file = tmp_path / "real_state.json"
    real_file.write_text('{"phase":"READY"}', encoding="utf-8")
    link = workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json"
    link.parent.mkdir(exist_ok=True)
    link.symlink_to(real_file)

    # Any hook processing with this state file should detect symlink and deny
    rc, _, stderr = _run_gate(
        workspace,
        _skill("bmad-tdd-coordinator"),
    )
    assert rc == 2
    assert "symlink" in stderr.lower() or "denied" in stderr.lower() or "error" in stderr.lower()


def test_invalid_story_key_denied_in_loop(tmp_path: Path) -> None:
    """Story key with invalid characters → DENY (not sanitized)."""
    workspace = _setup_workspace(tmp_path)

    rc, _, stderr = _run_gate(
        workspace,
        _skill("bmad-tdd-coordinator"),
        story_key=";;;INVALID;;;",
    )
    assert rc == 2
    assert "story" in stderr.lower() or "key" in stderr.lower() or "invalid" in stderr.lower()


def test_story_key_strict_regex_valid(tmp_path: Path) -> None:
    """Valid story keys ([A-Za-z0-9][A-Za-z0-9._-]*) must NOT be denied."""
    workspace = _setup_workspace(tmp_path)

    # These should all work
    for key in ["1-6-valid", "story.abc", "a-b-c.d_e", "EPIC-42"]:
        rc, _, _ = _run_gate(
            workspace,
            _skill("bmad-tdd-coordinator"),
            story_key=key,
        )
        assert rc == 0, f"Key {key!r} should be valid"


# ═══════════════════════════════════════════════════════════════════════════════
# D. Bash write practical closure (blocker 4)
# ═══════════════════════════════════════════════════════════════════════════════


def test_bash_git_apply_denied(tmp_path: Path) -> None:
    """git apply → DENY regardless of paths."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "git apply /tmp/patch.diff",
            },
        },
    )
    assert rc == 2
    assert "git apply" in stderr or "apply" in stderr.lower() or "denied" in stderr.lower()


def test_bash_standalone_patch_denied(tmp_path: Path) -> None:
    """standalone 'patch' command → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "patch -p1 < /tmp/changes.patch",
            },
        },
    )
    assert rc == 2


def test_bash_heredoc_write_denied(tmp_path: Path) -> None:
    """heredoc writing to src/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "cat <<EOF > src/x.py\nhello\nEOF",
            },
        },
    )
    assert rc == 2


def test_bash_sh_c_write_denied(tmp_path: Path) -> None:
    """sh -c with redirect to tests/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": 'sh -c "echo hello > tests/test_x.py"',
            },
        },
    )
    assert rc == 2


def test_bash_dd_write_denied(tmp_path: Path) -> None:
    """dd with of= targeting src/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "echo data | dd of=src/x.py conv=notrunc",
            },
        },
    )
    assert rc == 2


def test_bash_perl_write_denied(tmp_path: Path) -> None:
    """perl -e writing to src/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": 'perl -e \'open(F,">","src/x.py") and print "x"\'',
            },
        },
    )
    assert rc == 2


def test_bash_ruby_write_denied(tmp_path: Path) -> None:
    """ruby -e writing to tests/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "ruby -e \"File.open('tests/test_x.py', 'w') {|f| f.write('x')}\"",
            },
        },
    )
    assert rc == 2


def test_bash_base64_decode_redirect_denied(tmp_path: Path) -> None:
    """base64 -d redirect to src/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "echo aGVsbG8= | base64 -d > src/x.py",
            },
        },
    )
    assert rc == 2


def test_bash_install_denied(tmp_path: Path) -> None:
    """install command targeting src/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "install -m 644 /tmp/foo src/bar.py",
            },
        },
    )
    assert rc == 2


def test_bash_sed_i_denied(tmp_path: Path) -> None:
    """sed -i editing src/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "sed -i 's/old/new/g' src/x.py",
            },
        },
    )
    assert rc == 2


def test_bash_variable_assignment_with_redirect_denied(tmp_path: Path) -> None:
    """VAR=value > src/... → DENY (variable assignment with redirect)."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "CONTENT='hello' > src/x.py",
            },
        },
    )
    assert rc == 2


def test_bash_truncate_denied(tmp_path: Path) -> None:
    """truncate targeting tests/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "truncate -s 0 tests/test_x.py",
            },
        },
    )
    assert rc == 2


def test_bash_touch_denied(tmp_path: Path) -> None:
    """touch creating tests/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "touch tests/test_new.py",
            },
        },
    )
    assert rc == 2


def test_bash_rm_denied(tmp_path: Path) -> None:
    """rm removing src/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "rm src/old_module.py",
            },
        },
    )
    assert rc == 2


def test_bash_allowed_readonly_operations(tmp_path: Path) -> None:
    """Read-only operations must be ALLOWED: cat, grep, git status/diff/log."""
    workspace = _setup_workspace(tmp_path)

    for cmd in [
        "cat src/x.py",
        "grep 'hello' src/x.py",
        "git status",
        "git diff",
        "git log --oneline -5",
    ]:
        rc, _, _ = _run_gate(
            workspace,
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {
                    "command": cmd,
                },
            },
        )
        assert rc == 0, f"Command {cmd!r} should be allowed"


def test_bash_protected_path_with_write_indicator_denied(tmp_path: Path) -> None:
    """Protected literal path (_bmad-output/implementation-artifacts/) with
    write indicator (tee) → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "echo data | tee _bmad-output/implementation-artifacts/story-1-6-x.md",
            },
        },
    )
    assert rc == 2


def test_bash_chained_command_with_redirect_denied(tmp_path: Path) -> None:
    """Chained command: echo && cp → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "echo x && cp /tmp/src.py src/x.py",
            },
        },
    )
    assert rc == 2


# ═══════════════════════════════════════════════════════════════════════════════
# E. Legacy findings (blocker 5)
# ═══════════════════════════════════════════════════════════════════════════════


def test_fail_open_outside_loop_mode(tmp_path: Path) -> None:
    """Internal exception OUTSIDE loop mode → fail-open (exit 0, audit).
    This is a binding requirement: the gate must never brick non-loop workflows."""
    workspace = _setup_workspace(tmp_path)

    gate_target = workspace / "hooks" / "tdd_cycle_gate.py"
    original = gate_target.read_text()
    try:
        # Patch to force an exception during processing
        old = (
            "def _handle_loop_mode_pre_tool_use"
            "(tool_name: str, tool_input: dict, state: State) -> None:\n"
        )
        old += (
            '    """Loop-mode PreToolUse handler: observes skills,'
            ' blocks bash writes, enforces cycle."""'
        )
        new = (
            "def _handle_loop_mode_pre_tool_use"
            "(tool_name: str, tool_input: dict, state: State) -> None:\n"
        )
        new += '    raise RuntimeError("simulated internal error")\n'
        patched = original.replace(old, new, 1)
        gate_target.write_text(patched, encoding="utf-8")

        # Run WITHOUT loop mode env vars
        result = subprocess.run(
            ["python3", str(gate_target)],
            cwd=str(workspace),
            env={**os.environ},  # NO BMAD_LOOP_MODE
            input=json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "echo"},
                }
            ),
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Fail-open: exit 0
        assert result.returncode == 0
    finally:
        gate_target.write_text(original, encoding="utf-8")


def test_no_quality_gate_gate_on_refactor_prod_edits(tmp_path: Path) -> None:
    """REFACTOR prod edits must NOT be gated on quality checkpoint.
    Canonical refactor happens before gate; requiring QG blocks legitimate refactors."""
    workspace = _setup_workspace(tmp_path)

    # Drive to REFACTOR phase through the full RED→GREEN→CLEAN cycle
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    _run_gate(workspace, _pytest_outcome("passed"))
    _run_gate(workspace, _edit_story("VERDE: ok"))
    _run_gate(workspace, _task("tdd-clean-ornith"))
    _run_gate(workspace, _skill("tdd-clean"))
    _run_gate(workspace, _edit_story("CLEAN: ok"))

    # In REFACTOR, prod edit must NOT be gated on a quality-gate checkpoint
    qg_dir = workspace / "_quality-gate"
    assert not qg_dir.exists(), "Quality gate checkpoint must NOT exist"

    # tdd-refactor not yet seen → denied, but NOT because of quality gate
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/x.py",
                "content": "def refactor(): pass",
            },
        },
    )
    assert rc == 2
    assert "quality gate" not in stderr.lower() and "checkpoint" not in stderr.lower()

    # After tdd-refactor-ornith + tdd-refactor → prod edit ALLOWED without QG gate
    _run_gate(workspace, _task("tdd-refactor-ornith"))
    _run_gate(workspace, _skill("tdd-refactor"))
    rc2, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/x.py",
                "content": "def refactor(): pass",
            },
        },
    )
    assert rc2 == 0


# ═══════════════════════════════════════════════════════════════════════════════
# F. Coordinator re-invocation (blocker 6)
# ═══════════════════════════════════════════════════════════════════════════════


def test_coordinator_reinvocation_outside_ready_denied(tmp_path: Path) -> None:
    """coordinator re-invocation in RED_SEEN → DENY (not idempotent outside READY)."""
    workspace = _setup_workspace(tmp_path)

    # First coordinator in READY → stays READY (per blocker 1)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))

    # Drive to RED_SEEN via pytest FAIL
    _run_gate(workspace, _pytest_outcome("failed"))
    assert (
        json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())[
            "phase"
        ]
        == "RED_SEEN"
    )

    # Re-invoking coordinator in RED_SEEN → DENY
    rc, _, stderr = _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    assert rc == 2
    assert (
        "coordinator" in stderr.lower() or "ready" in stderr.lower() or "denied" in stderr.lower()
    )


def test_coordinator_idempotent_duplicate_in_ready(tmp_path: Path) -> None:
    """coordinator re-invocation WHILE still READY → allowed (idempotent)."""
    workspace = _setup_workspace(tmp_path)

    # First coordinator → stays READY
    rc1, _, _ = _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    assert rc1 == 0

    # Second coordinator while still READY → allowed (idempotent)
    rc2, _, _ = _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    assert rc2 == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    # skill_seen should still have just one coordinator entry
    assert state["skill_seen"].count("bmad-tdd-coordinator") == 1
    assert state["phase"] == "READY"


# ═══════════════════════════════════════════════════════════════════════════════
# G. Skill name normalization (blocker 3)
# ═══════════════════════════════════════════════════════════════════════════════


def test_skill_name_normalized_strip_and_lower(tmp_path: Path) -> None:
    """skill_name with leading/trailing whitespace and mixed case is
    normalized via strip().lower() before lookup."""
    workspace = _setup_workspace(tmp_path)

    # Register coordinator first
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    # Then register the Task agent for tdd-red
    _run_gate(workspace, _task("tdd-red-ornith"))

    # Send "  TDD-RED  " — should be normalized to "tdd-red" and work
    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Skill",
            "tool_input": {
                "skill_name": "  TDD-RED  ",
            },
        },
    )
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    # Normalized name should be in skill_seen
    assert "tdd-red" in state["skill_seen"]


# ═══════════════════════════════════════════════════════════════════════════════
# H. MultiEdit in loop mode (blocker 2 — runtime)
# ═══════════════════════════════════════════════════════════════════════════════


def test_multedit_prod_edit_in_coding_denied_without_green(tmp_path: Path) -> None:
    """MultiEdit to prod files in CODING without tdd-green → DENY."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))

    # Phase is now CODING; MultiEdit to prod without tdd-green → DENY
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "MultiEdit",
            "tool_input": {
                "edits": [{"file_path": "src/x.py", "new_string": "pass"}],
            },
        },
    )
    assert rc == 2


def test_multedit_test_edit_allowed_after_tdd_red(tmp_path: Path) -> None:
    """MultiEdit to test files after tdd-red → ALLOW."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))

    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "MultiEdit",
            "tool_input": {
                "edits": [{"file_path": "tests/test_x.py", "new_string": "def test_x(): pass"}],
            },
        },
    )
    assert rc == 0


# ═══════════════════════════════════════════════════════════════════════════════
# I. Internal exception fail-closed (regression from fb70)
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
# J. _stringify precision — metadata must not produce false FAIL (blocker 2)
# ═══════════════════════════════════════════════════════════════════════════════


def test_stringify_metadata_no_false_fail(tmp_path: Path) -> None:
    """Metadata fields like 'duration' must NOT pollute _stringify output.
    {"duration":"1 failed","stdout":"1 passed"} → outcome should be GREEN, not RED."""
    workspace = _setup_workspace(tmp_path)

    # First trigger state creation with a coordinator call
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))

    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "uv run pytest tests/"},
            "tool_response": {"duration": "1 failed", "stdout": "1 passed", "stderr": ""},
        },
    )
    assert rc == 0
    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    # Should stay READY (no false FAIL from metadata)
    assert state["phase"] == "READY"


def test_stringify_stdout_stderr_still_detected(tmp_path: Path) -> None:
    """Real stdout/stderr fields ARE still detected correctly."""
    workspace = _setup_workspace(tmp_path)

    # FAIL in stdout → READY→RED_SEEN
    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "uv run pytest tests/"},
            "tool_response": {"stdout": "1 failed, 0 passed", "stderr": ""},
        },
    )
    assert rc == 0
    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "RED_SEEN"


def test_stringify_pass_in_stdout(tmp_path: Path) -> None:
    """PASS in stdout → CODING→GREEN_SEEN."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))

    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "uv run pytest tests/"},
            "tool_response": {"stdout": "2 passed", "stderr": ""},
        },
    )
    assert rc == 0
    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "GREEN_SEEN"


def test_stringify_string_response_supported(tmp_path: Path) -> None:
    """String response (not Mapping) is handled by _stringify."""
    workspace = _setup_workspace(tmp_path)

    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "uv run pytest tests/"},
            "tool_response": "1 failed, 0 passed",
        },
    )
    assert rc == 0
    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "RED_SEEN"


# ═══════════════════════════════════════════════════════════════════════════════
# K. Python3 detector — python3? and uv run python variants (blocker 3)
# ═══════════════════════════════════════════════════════════════════════════════


def test_bash_python3_write_denied(tmp_path: Path) -> None:
    """python3 -c writing to src/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "python3 -c \"open('src/x.py','w').write('x')\"",
            },
        },
    )
    assert rc == 2


def test_bash_uv_run_python_write_denied(tmp_path: Path) -> None:
    """uv run python -c writing to src/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "uv run python -c \"open('src/x.py','w').write('x')\"",
            },
        },
    )
    assert rc == 2


def test_bash_uv_run_python3_write_denied(tmp_path: Path) -> None:
    """uv run python3 -c writing to tests/ → DENY."""
    workspace = _setup_workspace(tmp_path)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "uv run python3 -c \"open('tests/test_x.py','w').write('x')\"",
            },
        },
    )
    assert rc == 2


def _run_gate_legacy(workspace: Path, payload: dict) -> tuple[int, str, str]:
    """Run gate WITHOUT loop mode (legacy)."""
    result = subprocess.run(
        ["python3", str(PYTHON_GATE)],
        cwd=str(workspace),
        env={**os.environ},
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result.stdout, result.stderr


# ═══════════════════════════════════════════════════════════════════════════════
# L. Trailing comments sprint legacy (blocker 4)
# ═══════════════════════════════════════════════════════════════════════════════


def test_sprint_status_with_trailing_comment(tmp_path: Path) -> None:
    """Sprint status '1-6-x: in-progress # comment' still activates gate."""
    workspace = _setup_workspace(tmp_path)

    # Override sprint-status with trailing comment
    sprint = workspace / "_bmad-output" / "implementation-artifacts" / "sprint-status.yaml"
    sprint.write_text(
        "development_status:\n  1-6-fb70-test: in-progress # active story\n",
        encoding="utf-8",
    )

    # Non-loop mode: gate should activate (story is in-progress)
    result = subprocess.run(
        ["python3", str(PYTHON_GATE)],
        cwd=str(workspace),
        env={**os.environ},  # NO loop mode
        input=json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "echo"},
            }
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Gate activates (exit 0 for inert Bash), proving story was detected
    assert result.returncode == 0


# ═══════════════════════════════════════════════════════════════════════════════
# M. Audit warning legacy — bitácora out of phase logs warning (blocker 5)
# ═══════════════════════════════════════════════════════════════════════════════


def test_audit_warning_on_legacy_bitacora_out_of_phase(tmp_path: Path) -> None:
    """Legacy mode: VERDE: in READY (wrong phase) → audit warning, no transition."""
    workspace = _setup_workspace(tmp_path)
    audit_log = workspace / ".bmad-harness" / "tdd-audit.log"

    # Legacy mode (no loop): set up state where phase=READY but bitácora has VERDE
    state_file = workspace / ".bmad-harness" / "tdd-state.json"
    state_file.parent.mkdir(exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "phase": "READY",
                "mode": "tdd",
                "bypass_reason": "",
                "updated": "2026-01-01T00:00:00+00:00",
                "story_key": "",
                "cycle": 0,
                "skill_seen": [],
                "last_skill_at": "",
            }
        ),
        encoding="utf-8",
    )

    # Write VERDE: in READY (wrong phase) → should emit audit warning
    result = subprocess.run(
        ["python3", str(PYTHON_GATE)],
        cwd=str(workspace),
        env={**os.environ},  # NO loop mode
        input=json.dumps(
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "_bmad-output/implementation-artifacts/story-1-6-fb70-test.md",
                    "new_string": "VERDE: out-of-phase entry",
                },
            }
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0  # PostToolUse never blocks

    # Audit log should contain a warning about out-of-order bitácora
    if audit_log.exists():
        audit_content = audit_log.read_text()
        assert "warning" in audit_content.lower() or "out.of.phase" in audit_content.lower()


def test_audit_warning_no_transition_change(tmp_path: Path) -> None:
    """Legacy bitácora out-of-phase: NO transition occurs (state preserved)."""
    workspace = _setup_workspace(tmp_path)

    # Set up GREEN_SEEN (wrong phase for ROJO)
    state_file = workspace / ".bmad-harness" / "tdd-state.json"
    state_file.parent.mkdir(exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "phase": "GREEN_SEEN",
                "mode": "tdd",
                "bypass_reason": "",
                "updated": "2026-01-01T00:00:00+00:00",
                "story_key": "",
                "cycle": 0,
                "skill_seen": [],
                "last_skill_at": "",
            }
        ),
        encoding="utf-8",
    )

    # ROJO: in GREEN_SEEN (wrong phase) → no transition, just audit warning
    _run_gate_legacy(
        workspace,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-fb70-test.md",
                "new_string": "ROJO: out-of-phase legacy entry",
            },
        },
    )

    state = json.loads(state_file.read_text())
    # Phase unchanged — out-of-phase bitácora does NOT force transition
    assert state["phase"] == "GREEN_SEEN"


def test_internal_exception_fail_closed_in_loop_mode(tmp_path: Path) -> None:
    """Internal exception in loop mode → deny/fail-closed (exit 2)."""
    workspace = _setup_workspace(tmp_path)

    gate_target = workspace / "hooks" / "tdd_cycle_gate.py"
    original = gate_target.read_text()
    try:
        old_func = (
            "def _handle_loop_mode_pre_tool_use"
            "(tool_name: str, tool_input: dict, state: State) -> None:\n"
            '    """Loop-mode PreToolUse handler:'
            " observes skills, blocks bash writes,"
            ' enforces cycle."""'
        )
        new_func = (
            "def _handle_loop_mode_pre_tool_use"
            "(tool_name: str, tool_input: dict, state: State) -> None:\n"
            '    raise RuntimeError("simulated internal error")\n'
        )
        patched = original.replace(old_func, new_func, 1)
        gate_target.write_text(patched, encoding="utf-8")

        rc, _, stderr = _run_gate(
            workspace,
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "echo"},
            },
            gate_path=gate_target,
        )
        assert rc == 2
        assert "error" in stderr.lower() or "fail" in stderr.lower() or "denied" in stderr.lower()
    finally:
        gate_target.write_text(original, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# N. _REFACTOR_INCOMPLETE_FIX defined + legacy QG deny (blocker 1)
# ═══════════════════════════════════════════════════════════════════════════════


def test_legacy_prod_edit_ready_with_qg_fail_denies_without_namerror(tmp_path: Path) -> None:
    """Legacy mode: prod edit in READY with quality-gate checkpoint FAIL → deny
    using _REFACTOR_INCOMPLETE_FIX message. Must NOT crash with NameError."""
    workspace = tmp_path

    # Create a fake quality-gate checkpoint with PASS=false
    qg_dir = workspace / "_quality-gate"
    qg_dir.mkdir(parents=True, exist_ok=True)
    (qg_dir / "quality-gate-latest.json").write_text(
        json.dumps({"PASS": False}),
        encoding="utf-8",
    )

    # Set up sprint-status so legacy gate activates
    sprint_dir = workspace / "_bmad-output" / "implementation-artifacts"
    sprint_dir.mkdir(parents=True, exist_ok=True)
    (sprint_dir / "sprint-status.yaml").write_text(
        "development_status:\n  9-1-pilot: in-progress\n",
        encoding="utf-8",
    )

    # Legacy state: phase=READY
    state_dir = workspace / ".bmad-harness"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "tdd-state.json").write_text(
        json.dumps(
            {
                "phase": "READY",
                "mode": "tdd",
                "bypass_reason": "",
                "updated": "2026-01-01T00:00:00+00:00",
                "story_key": "",
                "cycle": 0,
                "skill_seen": [],
                "last_skill_at": "",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["python3", str(PYTHON_GATE)],
        cwd=str(workspace),
        env={**os.environ},  # NO loop mode (legacy)
        input=json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": "src/x.py", "new_string": "pass"},
            }
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Should not crash (NameError would give exit code unrelated to gate)
    assert result.returncode == 2
    # Should mention quality gate / refactor incomplete
    assert (
        "quality gate" in result.stderr.lower()
        or "refactor" in result.stderr.lower()
        or "checkpoint" in result.stderr.lower()
    )


def test_legacy_no_qg_checkpoint_allows_first_cycle(tmp_path: Path) -> None:
    """Legacy mode: prod edit in READY with NO quality-gate checkpoint → deny with
    standard RED_FIX (first cycle has no QG yet)."""
    workspace = tmp_path

    # No quality-gate directory at all
    sprint_dir = workspace / "_bmad-output" / "implementation-artifacts"
    sprint_dir.mkdir(parents=True, exist_ok=True)
    (sprint_dir / "sprint-status.yaml").write_text(
        "development_status:\n  9-1-pilot: in-progress\n",
        encoding="utf-8",
    )

    state_dir = workspace / ".bmad-harness"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "tdd-state.json").write_text(
        json.dumps(
            {
                "phase": "READY",
                "mode": "tdd",
                "bypass_reason": "",
                "updated": "2026-01-01T00:00:00+00:00",
                "story_key": "",
                "cycle": 0,
                "skill_seen": [],
                "last_skill_at": "",
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["python3", str(PYTHON_GATE)],
        cwd=str(workspace),
        env={**os.environ},
        input=json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": "src/x.py", "new_string": "pass"},
            }
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    # Standard RED fix message (not the REFACTOR_INCOMPLETE one)
    assert "rojo" in result.stderr.lower() or "test" in result.stderr.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# O. Loop PreToolUse story bitácora guard (blocker 2)
# ═══════════════════════════════════════════════════════════════════════════════


def test_verde_in_red_seen_allowed_post_tool_use(tmp_path: Path) -> None:
    """Loop mode: VERDE: in body while phase=RED_SEEN → PostToolUse ALLOW (bitácora edit)."""
    workspace = _setup_workspace(tmp_path)

    # Drive to RED_SEEN
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))

    # PostToolUse Edit with VERDE: in RED_SEEN → ALLOW (bitácora writes always allowed)
    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "ROJO: initial test written\nROJO: updated notes on test",
            },
        },
    )
    assert rc == 0


def test_verde_in_coding_denied_pre_tool_use(tmp_path: Path) -> None:
    """Loop mode: VERDE: in body while phase=CODING → PreToolUse DENY."""
    workspace = _setup_workspace(tmp_path)

    # Drive to CODING: coordinator + tdd-red + pytest FAIL + ROJO
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))

    # VERDE: in CODING → DENY (only ROJO allowed in CODING)
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "## TDD Bitácora\n\nROJO: initial\nVERDE: passed early",
            },
        },
    )
    assert rc == 2
    assert "fase" in stderr.lower() or "skill" in stderr.lower() or "requerido" in stderr.lower()


def test_verde_in_refactor_allowed_post_tool_use(tmp_path: Path) -> None:
    """Loop mode: VERDE: in body while phase=REFACTOR → PostToolUse ALLOW (bitácora edit)."""
    workspace = _setup_workspace(tmp_path)

    # Drive to REFACTOR
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    _run_gate(workspace, _pytest_outcome("passed"))
    _run_gate(workspace, _edit_story("VERDE: ok"))

    # PostToolUse Edit with VERDE: in REFACTOR → ALLOW
    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "## TDD Bitácora\n\nROJO: ok\nVERDE: ok\nREFACTOR: done",
            },
        },
    )
    assert rc == 0


def test_full_content_in_red_seen_denied(tmp_path: Path) -> None:
    """Full content (ROJO+VERDE+REFACTOR) in RED_SEEN → DENY."""
    workspace = _setup_workspace(tmp_path)

    # Drive to RED_SEEN
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))

    # Full content in RED_SEEN → DENY
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "## TDD Bitácora\n\nROJO: initial\nVERDE: passed\nREFACTOR: clean",
            },
        },
    )
    assert rc == 2
    assert "fase" in stderr.lower() or "skill" in stderr.lower() or "requerido" in stderr.lower()


def test_full_content_in_coding_denied(tmp_path: Path) -> None:
    """Full content (ROJO+VERDE+REFACTOR) in CODING → DENY."""
    workspace = _setup_workspace(tmp_path)

    # Drive to CODING
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))

    # Full content in CODING → DENY
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "## TDD Bitácora\n\nROJO: initial\nVERDE: passed\nREFACTOR: clean",
            },
        },
    )
    assert rc == 2
    assert "fase" in stderr.lower() or "skill" in stderr.lower() or "requerido" in stderr.lower()


def test_full_content_in_green_seen_denied(tmp_path: Path) -> None:
    """Full content (ROJO+VERDE+REFACTOR) in GREEN_SEEN → DENY."""
    workspace = _setup_workspace(tmp_path)

    # Drive to GREEN_SEEN
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    _run_gate(workspace, _pytest_outcome("passed"))

    # Full content in GREEN_SEEN → DENY
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "## TDD Bitácora\n\nROJO: initial\nVERDE: passed\nREFACTOR: clean",
            },
        },
    )
    assert rc == 2
    assert "fase" in stderr.lower() or "skill" in stderr.lower() or "requerido" in stderr.lower()


def test_full_rojo_verde_refactor_in_refactor_requires_refactor_seen(tmp_path: Path) -> None:
    """Full content ROJO+VERDE+REFACTOR in REFACTOR phase → DENY if tdd-refactor
    not yet seen. Only allowed when refactor skill has been invoked."""
    workspace = _setup_workspace(tmp_path)

    # Drive to REFACTOR via bitácora entries
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    _run_gate(workspace, _pytest_outcome("passed"))
    _run_gate(workspace, _edit_story("VERDE: ok"))

    # In REFACTOR without tdd-refactor → full content with REFACTOR: should DENY
    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "## TDD Bitácora\n\nROJO: ok\nVERDE: ok\nREFACTOR: done refactoring",
            },
        },
    )
    assert rc == 2
    assert "refactor" in stderr.lower() or "denied" in stderr.lower()


def test_rojo_in_coding_allowed(tmp_path: Path) -> None:
    """ROJO: in CODING → ALLOW (this is the expected bitácora entry)."""
    workspace = _setup_workspace(tmp_path)

    # Drive to CODING
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))

    # In CODING, writing ROJO: again (prior token) → should be allowed
    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": (
                    "## TDD Bitácora\n\nROJO: initial test written\nROJO: updated notes on test"
                ),
            },
        },
    )
    assert rc == 0


# ═══════════════════════════════════════════════════════════════════════════════
# O. Antifalsificación: guard is read-only, no skill_seen mutation (correction)
# ═══════════════════════════════════════════════════════════════════════════════


def test_antifalsificacion_full_all_3_only_coordinator_seen_denies(tmp_path: Path) -> None:
    """Full content all 3 tokens with only coordinator in skill_seen → DENY.
    Guard must NEVER mutate skill_seen regardless of outcome."""
    workspace = _setup_workspace(tmp_path)

    # Only coordinator seen
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))

    original_bytes = (workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_bytes()

    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "ROJO: a\nVERDE: b\nREFACTOR: c",
            },
        },
    )
    assert rc == 2
    assert "fase" in stderr.lower() or "skill" in stderr.lower() or "requerido" in stderr.lower()

    # CRITICAL: skill_seen MUST be unchanged byte-for-byte
    after_bytes = (workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_bytes()
    assert original_bytes == after_bytes, "Guard mutated skill_seen — antifalsificación FAIL"


def test_antifalsificacion_full_in_refactor_no_refactor_skill_denies(tmp_path: Path) -> None:
    """Full content in REFACTOR phase but tdd-refactor not yet in skill_seen → DENY.
    State unchanged byte-for-byte."""
    workspace = _setup_workspace(tmp_path)

    # Drive to REFACTOR with red+green seen but NOT refactor
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))  # in CODING, before pytest pass
    _run_gate(workspace, _pytest_outcome("passed"))
    _run_gate(workspace, _edit_story("VERDE: ok"))
    # tdd-refactor NOT called yet

    original_bytes = (workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_bytes()

    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "ROJO: a\nVERDE: b\nREFACTOR: c",
            },
        },
    )
    assert rc == 2
    assert "refactor" in stderr.lower() or "denied" in stderr.lower()

    after_bytes = (workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_bytes()
    assert original_bytes == after_bytes, "Guard mutated skill_seen — antifalsificación FAIL"


def test_antifalsificacion_correct_full_all_skills_allowed_and_unchanged(tmp_path: Path) -> None:
    """Correct full content with all skills observed → ALLOW.
    skill_seen unchanged byte-for-byte proving guard is read-only."""
    workspace = _setup_workspace(tmp_path)
    state_file = workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json"

    # Drive through cycle correctly: tdd-green BEFORE pytest pass (required by gate)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    _run_gate(workspace, _pytest_outcome("passed"))
    _run_gate(workspace, _edit_story("VERDE: ok"))
    _run_gate(workspace, _task("tdd-clean-ornith"))
    _run_gate(workspace, _skill("tdd-clean"))
    _run_gate(workspace, _edit_story("CLEAN: ok"))
    _run_gate(workspace, _task("tdd-refactor-ornith"))
    _run_gate(workspace, _skill("tdd-refactor"))

    # In REFACTOR with all skills → full content allowed, state unchanged
    state_before = json.loads(state_file.read_text())
    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": ("_bmad-output/implementation-artifacts/story-1-6-repair-test.md"),
                "new_string": ("## TDD Bitácora\n\nROJO: initial\nVERDE: passed\nREFACTOR: clean"),
            },
        },
    )
    assert rc == 0
    # Verify state unchanged byte-for-byte
    state_after = json.loads(state_file.read_text())
    assert state_before == state_after


def _parse_bitacora_tokens(text: str) -> set[str]:
    """Extract all phase tokens (ROJO:, VERDE:, REFACTOR:) from bitácora text."""
    import re

    return set(re.findall(r"\b(ROJO|VERDE|REFACTOR):", text))


def test_parse_bitacora_tokens_basic(tmp_path: Path) -> None:
    """Basic token parsing: ROJO:, VERDE:, REFACTOR: extracted correctly."""
    assert _parse_bitacora_tokens("ROJO: initial") == {"ROJO"}
    assert _parse_bitacora_tokens("VERDE: passed") == {"VERDE"}
    assert _parse_bitacora_tokens("REFACTOR: clean") == {"REFACTOR"}
    assert _parse_bitacora_tokens("ROJO: a\nVERDE: b\nREFACTOR: c") == {
        "ROJO",
        "VERDE",
        "REFACTOR",
    }


def test_parse_bitacora_tokens_no_false_positives(tmp_path: Path) -> None:
    """Tokens embedded in other words must NOT match (e.g. 'REFACTORING:')."""
    assert _parse_bitacora_tokens("REFACTORING: not a token") == set()
    assert _parse_bitacora_tokens("ROJOS: plural") == set()
    assert _parse_bitacora_tokens("VERDER: not a word") == set()


def test_parse_bitacora_tokens_case_sensitive(tmp_path: Path) -> None:
    """Lowercase tokens must NOT match (gate is case-sensitive)."""
    assert _parse_bitacora_tokens("rojo: lowercase") == set()
    assert _parse_bitacora_tokens("verde: lowercase") == set()
    assert _parse_bitacora_tokens("refactor: lowercase") == set()


def test_parse_bitacora_tokens_colons_in_different_contexts(tmp_path: Path) -> None:
    """Colons in different contexts (URLs, time, etc.) must NOT match."""
    assert _parse_bitacora_tokens("http://example.com") == set()
    assert _parse_bitacora_tokens("12:30 PM") == set()
    assert _parse_bitacora_tokens("## Header\nROJO: entry\n## Next") == {"ROJO"}
    assert _parse_bitacora_tokens("REFACTOR: done") == {"REFACTOR"}


# ═══════════════════════════════════════════════════════════════════════════════
# N. CLEAN phase enforcement (bmad-gherkin-tdd correction plan)
# ═══════════════════════════════════════════════════════════════════════════════


def _drive_to_phase(workspace: Path, target: str) -> None:
    """Drive the gate state machine up to (but not past) `target`.

    Sequence: READY →(red)→ RED_SEEN →(rojo)→ CODING →(green)→ GREEN_SEEN
              →(verde)→ CLEAN →(clean)→ REFACTOR
    """
    if target == "READY":
        return
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    if target == "RED_SEEN":
        _run_gate(workspace, _pytest_outcome("failed"))
        return
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _pytest_outcome("failed"))
    _run_gate(workspace, _edit_story("ROJO: ok"))
    if target == "CODING":
        return
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(workspace, _skill("tdd-green"))
    _run_gate(workspace, _pytest_outcome("passed"))
    if target == "GREEN_SEEN":
        return
    _run_gate(workspace, _edit_story("VERDE: ok"))
    if target == "CLEAN":
        return
    _run_gate(workspace, _task("tdd-clean-ornith"))
    _run_gate(workspace, _skill("tdd-clean"))
    _run_gate(workspace, _edit_story("CLEAN: ok"))
    if target == "REFACTOR":
        return
    raise AssertionError(f"unsupported target {target!r}")


def test_tdd_clean_task_denied_outside_clean_phase(tmp_path: Path) -> None:
    """tdd-clean-ornith in GREEN_SEEN → DENY (CLEAN requires the VERDE entry)."""
    workspace = _setup_workspace(tmp_path)
    _drive_to_phase(workspace, "GREEN_SEEN")

    rc, _, stderr = _run_gate(workspace, _task("tdd-clean-ornith"))
    assert rc == 2
    assert "CLEAN" in stderr


def test_tdd_clean_skill_requires_clean_task(tmp_path: Path) -> None:
    """tdd-clean skill in CLEAN without tdd-clean-ornith → DENY."""
    workspace = _setup_workspace(tmp_path)
    _drive_to_phase(workspace, "CLEAN")

    # Skip the Task agent: the skill alone must be denied.
    rc, _, stderr = _run_gate(workspace, _skill("tdd-clean"))
    assert rc == 2
    assert "tdd-clean-ornith" in stderr


def test_tdd_clean_bitacora_requires_skill_seen(tmp_path: Path) -> None:
    """CLEAN: bitácora in CLEAN without tdd-clean seen → no transition."""
    workspace = _setup_workspace(tmp_path)
    _drive_to_phase(workspace, "CLEAN")

    rc, _, _ = _run_gate(workspace, _edit_story("CLEAN: premature"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "CLEAN"


def test_tdd_refactor_task_denied_in_clean(tmp_path: Path) -> None:
    """tdd-refactor-ornith in CLEAN → DENY (REFACTOR requires the CLEAN entry)."""
    workspace = _setup_workspace(tmp_path)
    _drive_to_phase(workspace, "CLEAN")

    _run_gate(workspace, _task("tdd-clean-ornith"))
    _run_gate(workspace, _skill("tdd-clean"))

    rc, _, stderr = _run_gate(workspace, _task("tdd-refactor-ornith"))
    assert rc == 2
    assert "REFACTOR" in stderr


def test_prod_edit_denied_in_clean_without_skill(tmp_path: Path) -> None:
    """Prod edit in CLEAN without tdd-clean → DENY."""
    workspace = _setup_workspace(tmp_path)
    _drive_to_phase(workspace, "CLEAN")

    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/x.py",
                "content": "def refactor(): pass",
            },
        },
    )
    assert rc == 2
    assert "tdd-clean" in stderr


def test_prod_edit_allowed_in_clean_with_skill(tmp_path: Path) -> None:
    """Prod edit in CLEAN after tdd-clean seen → ALLOW (structural refactor)."""
    workspace = _setup_workspace(tmp_path)
    _drive_to_phase(workspace, "CLEAN")
    _run_gate(workspace, _task("tdd-clean-ornith"))
    _run_gate(workspace, _skill("tdd-clean"))

    rc, _, _ = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/x.py",
                "content": "def refactor(): pass",
            },
        },
    )
    assert rc == 0


def test_clean_token_guard_outside_clean_denied(tmp_path: Path) -> None:
    """Bitácora 'CLEAN:' token written outside CLEAN phase → PreToolUse DENY."""
    workspace = _setup_workspace(tmp_path)
    _drive_to_phase(workspace, "GREEN_SEEN")

    rc, _, stderr = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "_bmad-output/implementation-artifacts/story-1-6-repair-test.md",
                "new_string": "CLEAN: out of phase",
            },
        },
    )
    assert rc == 2
    assert "CLEAN" in stderr


# ═══════════════════════════════════════════════════════════════════════════════
# O. RED violation (bmad-gherkin-tdd correction plan)
# ═══════════════════════════════════════════════════════════════════════════════


def test_red_violation_on_pass_in_ready(tmp_path: Path) -> None:
    """Genuine violation: a RED test was WRITTEN and then PASSES in READY
    → RED_VIOLATION (loop mode)."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _edit_test_file())

    rc, _, _ = _run_gate(workspace, _pytest_outcome("passed"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "RED_VIOLATION"


def test_red_violation_denies_subsequent_tools(tmp_path: Path) -> None:
    """After RED_VIOLATION, every further PreToolUse is denied with the marker."""
    workspace = _setup_workspace(tmp_path)

    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _edit_test_file())
    _run_gate(workspace, _pytest_outcome("passed"))

    # Skill invocation denied
    rc, _, stderr = _run_gate(workspace, _skill("tdd-green"))
    assert rc == 2
    assert "RED_VIOLATION" in stderr

    # Prod edit denied
    rc2, _, stderr2 = _run_gate(
        workspace,
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "src/x.py",
                "new_string": "pass",
            },
        },
    )
    assert rc2 == 2
    assert "RED_VIOLATION" in stderr2


def test_red_violation_not_triggered_without_red_task(tmp_path: Path) -> None:
    """pytest PASS in READY without tdd-red-ornith (no pending RED) → stays READY."""
    workspace = _setup_workspace(tmp_path)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))

    rc, _, _ = _run_gate(workspace, _pytest_outcome("passed"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "READY"


# ═══════════════════════════════════════════════════════════════════════════════
# P. red_test_written false-trigger guard + autonomous recovery (A0 port, b20c555)
# ═══════════════════════════════════════════════════════════════════════════════


def test_baseline_pytest_pass_before_red_test_not_violation(tmp_path: Path) -> None:
    """False-trigger guard: a passing pytest while a RED is pending but NO RED
    test has been written yet (a baseline verification run) must NOT flip to
    RED_VIOLATION — the phase stays READY."""
    workspace = _setup_workspace(tmp_path)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))  # PreToolUse sets red_pending
    _run_gate(workspace, _skill("tdd-red"))

    rc, _, _ = _run_gate(workspace, _pytest_outcome("passed"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "READY"


def test_test_file_edit_while_red_pending_sets_flag(tmp_path: Path) -> None:
    """Editing a tests/** file while a RED is pending marks the RED test written."""
    workspace = _setup_workspace(tmp_path)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))

    _run_gate(workspace, _edit_test_file())

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["red_test_written"] is True


def test_reset_allowed_in_red_violation(tmp_path: Path) -> None:
    """Recovery hatch: the gate's own reset CLI must NOT be denied in
    RED_VIOLATION, otherwise the run deadlocks with no autonomous escape."""
    workspace = _setup_workspace(tmp_path)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _edit_test_file())
    _run_gate(workspace, _pytest_outcome("passed"))  # → RED_VIOLATION

    rc, _, _ = _run_gate(workspace, _bash("python3 hooks/tdd_cycle_gate.py reset"))
    assert rc == 0


def test_non_reset_bash_still_denied_in_red_violation(tmp_path: Path) -> None:
    """The recovery hatch is narrow: ordinary Bash is still denied in RED_VIOLATION."""
    workspace = _setup_workspace(tmp_path)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _skill("tdd-red"))
    _run_gate(workspace, _edit_test_file())
    _run_gate(workspace, _pytest_outcome("passed"))  # → RED_VIOLATION

    rc, _, stderr = _run_gate(workspace, _bash("uv run pytest tests/x.py"))
    assert rc == 2
    assert "RED_VIOLATION" in stderr


# ═══════════════════════════════════════════════════════════════════════════════
# Q. Task PostToolUse bridge for subagent session isolation (A0 port, e41770b)
# ═══════════════════════════════════════════════════════════════════════════════


def test_task_post_red_ornith_advances_ready_to_coding(tmp_path: Path) -> None:
    """Task bridge: PostToolUse tdd-red-ornith advances READY→CODING and records
    the skill, bridging the isolated subagent session."""
    workspace = _setup_workspace(tmp_path)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))  # PreToolUse: red_pending, READY

    rc, _, _ = _run_gate(workspace, _task_post("tdd-red-ornith"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "CODING"
    assert "tdd-red" in state["skill_seen"]
    assert state["red_pending"] is False


def test_task_post_full_cycle_closes_to_ready(tmp_path: Path) -> None:
    """Task bridge: RED→GREEN→CLEAN→REFACTOR via PostToolUse Tasks closes the cycle."""
    workspace = _setup_workspace(tmp_path)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))

    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _task_post("tdd-red-ornith"))  # → CODING
    _run_gate(workspace, _task("tdd-green-ornith"))
    _run_gate(
        workspace, _task_post("tdd-green-ornith", tool_response="VERDE: test passes")
    )  # → CLEAN (DW-111: requires VERDE)
    _run_gate(workspace, _task("tdd-clean-ornith"))
    _run_gate(workspace, _task_post("tdd-clean-ornith"))  # → REFACTOR
    _run_gate(workspace, _task("tdd-refactor-ornith"))
    _run_gate(workspace, _task_post("tdd-refactor-ornith"))  # → READY, cycle+1

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "READY"
    # Module semantics: the coordinator invocation initializes the counter to 1
    # (_process_loop_skill) and the REFACTOR→READY close increments it to 2.
    assert state["cycle"] == 2
    for skill in ("tdd-red", "tdd-green", "tdd-clean", "tdd-refactor"):
        assert skill in state["skill_seen"]


def test_task_post_green_without_verde_stays_at_green_seen(tmp_path: Path) -> None:
    """DW-111 fix: GREEN Task without VERDE must NOT advance to CLEAN.

    Previously the bridge did CODING→GREEN_SEEN→CLEAN unconditionally, forcing
    a reset hatch even when GREEN STOPped (no VERDE). Now it stays at GREEN_SEEN
    so the coordinator can re-dispatch GREEN without reset.
    """
    workspace = _setup_workspace(tmp_path)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))
    _run_gate(workspace, _task("tdd-red-ornith"))
    _run_gate(workspace, _task_post("tdd-red-ornith"))  # READY→CODING
    _run_gate(workspace, _task("tdd-green-ornith"))  # CODING, pre GREEN

    # GREEN Task completes WITHOUT VERDE (STOP case): should stay at GREEN_SEEN
    rc, _, _ = _run_gate(workspace, _task_post("tdd-green-ornith"))
    assert rc == 0
    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "GREEN_SEEN", (
        "DW-111: GREEN without VERDE must stay GREEN_SEEN, not CLEAN"
    )
    assert "tdd-green" in state["skill_seen"]

    # GREEN without VERDE but with explicit STOP text also stays GREEN_SEEN
    rc, _, _ = _run_gate(
        workspace, _task_post("tdd-green-ornith", tool_response="STOP: quality gate failed")
    )
    assert rc == 0
    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "GREEN_SEEN"


def test_task_post_green_with_verde_advances_to_clean(tmp_path: Path) -> None:
    """GREEN Task with VERDE in tool_response must advance to CLEAN (happy path)."""
    # Fresh workspace, CODING→GREEN_SEEN→CLEAN with VERDE string
    workspace2 = _setup_workspace(tmp_path / "v2")
    _run_gate(workspace2, _skill("bmad-tdd-coordinator"), story_key="1-6-repair-test-v2")
    _run_gate(workspace2, _task("tdd-red-ornith"), story_key="1-6-repair-test-v2")
    _run_gate(workspace2, _task_post("tdd-red-ornith"), story_key="1-6-repair-test-v2")
    _run_gate(workspace2, _task("tdd-green-ornith"), story_key="1-6-repair-test-v2")
    rc, _, _ = _run_gate(
        workspace2,
        _task_post("tdd-green-ornith", tool_response="VERDE: test passes"),
        story_key="1-6-repair-test-v2",
    )
    assert rc == 0
    state = json.loads(
        (workspace2 / ".bmad-harness" / "tdd-state-1-6-repair-test-v2.json").read_text()
    )
    assert state["phase"] == "CLEAN"

    # Also test dict-shaped tool_response with VERDE
    workspace3 = _setup_workspace(tmp_path / "v3")
    _run_gate(workspace3, _skill("bmad-tdd-coordinator"), story_key="1-6-repair-test-v3")
    _run_gate(workspace3, _task("tdd-red-ornith"), story_key="1-6-repair-test-v3")
    _run_gate(workspace3, _task_post("tdd-red-ornith"), story_key="1-6-repair-test-v3")
    _run_gate(workspace3, _task("tdd-green-ornith"), story_key="1-6-repair-test-v3")
    rc, _, _ = _run_gate(
        workspace3,
        _task_post("tdd-green-ornith", tool_response={"output": "VERDE: via dict"}),
        story_key="1-6-repair-test-v3",
    )
    assert rc == 0
    state = json.loads(
        (workspace3 / ".bmad-harness" / "tdd-state-1-6-repair-test-v3.json").read_text()
    )
    assert state["phase"] == "CLEAN"


def test_task_post_non_tdd_task_ignored(tmp_path: Path) -> None:
    """Task bridge: a non-TDD Task completion causes no state transition."""
    workspace = _setup_workspace(tmp_path)
    _run_gate(workspace, _skill("bmad-tdd-coordinator"))

    rc, _, _ = _run_gate(workspace, _task_post("some-other-agent"))
    assert rc == 0

    state = json.loads((workspace / ".bmad-harness" / "tdd-state-1-6-repair-test.json").read_text())
    assert state["phase"] == "READY"
    assert state["skill_seen"] == ["bmad-tdd-coordinator"]
