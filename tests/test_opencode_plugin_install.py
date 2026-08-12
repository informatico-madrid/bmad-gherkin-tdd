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
