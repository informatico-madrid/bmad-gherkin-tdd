"""Regression guard — the four TDD phase subagents shipped in the OpenCode
agent template must deny the interactive ``question`` tool.

In unattended ``bmad-loop`` runs there is no human to answer a ``question``
prompt, so a subagent that invokes it deadlocks until the session times out
(observation #21). The mechanical fix is a per-agent permission deny — it does
not rely on the model obeying a prose prohibition.

The template carries ``#`` instruction comments and ``<MODEL>`` placeholders,
so the comment lines are stripped before parsing; the placeholders are valid
JSON strings and survive parsing unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

MODULE_ROOT = Path(__file__).parents[1]

AGENT_TEMPLATE = MODULE_ROOT / "opencode" / "agents" / "opencode.json.template"

PHASE_AGENTS = (
    "tdd-red-ornith",
    "tdd-green-ornith",
    "tdd-clean-ornith",
    "tdd-refactor-ornith",
)


def _load_template() -> dict:
    lines = AGENT_TEMPLATE.read_text(encoding="utf-8").splitlines()
    json_text = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
    return json.loads(json_text)


def test_agent_template_exists() -> None:
    assert AGENT_TEMPLATE.is_file(), f"missing agent template: {AGENT_TEMPLATE}"


def test_every_phase_agent_denies_question() -> None:
    """Each TDD phase subagent must carry permission.question == "deny"."""
    agents = _load_template()["agent"]
    for name in PHASE_AGENTS:
        assert name in agents, f"agent {name} missing from template"
        permission = agents[name].get("permission")
        assert isinstance(permission, dict), (
            f"agent {name} has no permission block; `question` must be denied "
            f"mechanically for unattended runs"
        )
        assert permission.get("question") == "deny", (
            f"agent {name} must deny the `question` tool (unattended deadlock, "
            f"obs #21); found permission={permission!r}"
        )
