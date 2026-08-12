from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "opencode" / "plugins" / "tdd-cycle-gate.js"


def _node(script: str) -> object:
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(result.stdout)


def test_auto_discovered_plugin_exports_only_factory() -> None:
    script = f"""
      import * as pluginModule from {json.dumps(PLUGIN.as_uri())};
      console.log(JSON.stringify(Object.keys(pluginModule).sort()));
    """
    assert _node(script) == ["TddCycleGate"]


def test_gate_result_policy_preserves_interactive_fail_open_and_loop_fail_closed() -> None:
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(PLUGIN.as_uri())};
      const {{ shouldDenyGateResult }} = TddCycleGate;
      const results = [
        {{ status: 0, signal: null, error: null }},
        {{ status: 2, signal: null, error: null }},
        {{ status: 1, signal: null, error: null }},
        {{ status: null, signal: null, error: null }},
        {{ status: null, signal: "SIGTERM", error: null }},
        {{ status: null, signal: null, error: new Error("spawn failed") }},
      ];
      console.log(JSON.stringify({{
        interactive: results.map((result) => shouldDenyGateResult(result, false)),
        loop: results.map((result) => shouldDenyGateResult(result, true)),
      }}));
    """
    assert _node(script) == {
        "interactive": [False, True, False, False, False, False],
        "loop": [False, True, True, True, True, True],
    }


def test_broken_python_gate_denies_only_in_loop_mode(tmp_path: Path) -> None:
    broken_gate = tmp_path / "broken-gate.py"
    broken_gate.write_text("this is invalid python !!!\n", encoding="utf-8")
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(PLUGIN.as_uri())};
      process.env.BMAD_TDD_GATE_PATH = {json.dumps(str(broken_gate))};
      const hooks = await TddCycleGate({{ directory: {json.dumps(str(tmp_path))} }});
      const invoke = async (loopMode) => {{
        if (loopMode) process.env.BMAD_LOOP_MODE = "1";
        else delete process.env.BMAD_LOOP_MODE;
        try {{
          await hooks["tool.execute.before"](
            {{ tool: "bash" }},
            {{ args: {{ command: "git status" }} }},
          );
          return "allowed";
        }} catch (error) {{
          return error.message;
        }}
      }};
      console.log(JSON.stringify({{
        interactive: await invoke(false),
        loop: await invoke(true),
      }}));
    """
    result = _node(script)
    assert isinstance(result, dict)
    assert result["interactive"] == "allowed"
    assert "SyntaxError: invalid syntax" in result["loop"]


def test_absolute_gate_path_is_not_joined_to_project(tmp_path: Path) -> None:
    gate = tmp_path / "external" / "gate.py"
    gate.parent.mkdir()
    gate.write_text(
        "import json, pathlib, sys\n"
        "payload = json.load(sys.stdin)\n"
        "pathlib.Path('gate-observed.json').write_text(json.dumps(payload))\n",
        encoding="utf-8",
    )
    script = f"""
      import {{ TddCycleGate }} from {json.dumps(PLUGIN.as_uri())};
      process.env.BMAD_TDD_GATE_PATH = {json.dumps(str(gate))};
      const hooks = await TddCycleGate({{ directory: {json.dumps(str(tmp_path))} }});
      await hooks["tool.execute.before"](
        {{ tool: "bash" }},
        {{ args: {{ command: "git status" }} }},
      );
      console.log(JSON.stringify(JSON.parse(
        await (await import("node:fs/promises")).readFile(
          {json.dumps(str(tmp_path / "gate-observed.json"))}, "utf8"
        )
      )));
    """
    assert _node(script) == {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
    }
