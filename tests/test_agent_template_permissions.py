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


FULL_MUTATION_DENIES = (
    "make mutation-check",
    "make mutation-check *",
    "make * mutation-check",
    "make mutation",
    "make mutation *",
    "uv run mutmut *",
    "uv run python -m mutmut *",
    "uv run python3 -m mutmut *",
    "python -m mutmut *",
    "python3 -m mutmut *",
    "mutmut *",
    "./.venv/bin/mutmut *",
    "uvx mutmut *",
    "uv run pytest && mutmut *",
    "uv run pytest && uvx mutmut *",
    "uv run pytest && ./.venv/bin/mutmut *",
)

# Chain denies must come AFTER the pytest allow (last-rule-wins in opencode) so
# `uv run pytest && make mutation-check` is denied, not swallowed by the allow.
REFACTOR_CHAIN_DENIES = (
    "uv run pytest && make mutation-check *",
    "uv run pytest && make mutation *",
    "uv run pytest && uv run mutmut *",
    "uv run pytest && uvx mutmut *",
    "uv run pytest && ./.venv/bin/mutmut *",
    "uv run pytest && python -m mutmut *",
    "uv run pytest && python3 -m mutmut *",
)


def test_every_phase_agent_denies_full_mutation() -> None:
    """Full-scope mutation is coordinator-owned at RELEASE.

    A Task subagent session does not inherit the Python ``tdd_cycle_gate``, so the
    deny must be mechanical in the agent template (permission.bash), not prose.
    """
    agents = _load_template()["agent"]
    for name in PHASE_AGENTS:
        permission = agents[name].get("permission", {})
        bash = permission.get("bash")
        assert isinstance(bash, dict), f"agent {name} must carry permission.bash"
        for cmd in FULL_MUTATION_DENIES:
            assert bash.get(cmd) == "deny", (
                f"agent {name} must deny `{cmd}` in permission.bash "
                f"(full mutation is the coordinator's RELEASE); found {bash!r}"
            )


def test_refactor_agent_allows_pytest_in_permission() -> None:
    """tdd-refactor-ornith runs pytest for its verification, so it must allow
    `uv run pytest` while still denying mutation commands (including the
    chained `uv run pytest && make mutation-check` form)."""
    bash = _load_template()["agent"]["tdd-refactor-ornith"]["permission"]["bash"]
    assert bash.get("uv run pytest *") == "allow"
    for cmd in FULL_MUTATION_DENIES:
        assert bash.get(cmd) == "deny"
    for cmd in REFACTOR_CHAIN_DENIES:
        assert bash.get(cmd) == "deny"


# ── bmad-loop-coordinator primary agent ───────────────────────────────────────

COORDINATOR_AGENT = "bmad-loop-coordinator"


def test_coordinator_primary_agent_present() -> None:
    """The template ships a primary agent named bmad-loop-coordinator that
    orchestrates bmad-loop runs (it is NOT one of the phase subagents)."""
    agents = _load_template()["agent"]
    assert COORDINATOR_AGENT in agents
    assert agents[COORDINATOR_AGENT].get("mode") == "primary"


def test_coordinator_agent_loads_skill_and_gates_on_human_presence() -> None:
    """The coordinator must (a) load its methodology skill on bootstrap and
    (b) gate interaction on the project's human-present flag in its prompt."""
    prompt = _load_template()["agent"][COORDINATOR_AGENT]["prompt"]
    assert "bmad-loop-coordinator" in prompt
    assert "skill" in prompt.lower()
    assert "human-present" in prompt
    assert "question" in prompt


def test_coordinator_agent_question_not_forbidden() -> None:
    """The coordinator's permission gate on `question` is driven by the runtime
    human-present flag (permitted to ask when a human is present), NOT a static
    deny like the phase subagents (which are always unattended)."""
    permission = _load_template()["agent"][COORDINATOR_AGENT]["permission"]
    assert permission.get("question") == "allow"


# ── bmad-loop-coordinator SKILL coherence ─────────────────────────────────────

SKILL_NAMES = (
    "bmad-loop-coordinator",
    "gherkin-author",
    "bmad-tdd-coordinator",
    "tdd-red",
    "tdd-green",
    "tdd-clean",
    "tdd-refactor",
)

SKILL_ROOT = MODULE_ROOT / "skills"


def test_loop_coordinator_skill_shipped() -> None:
    """The orchestrator skill that the bmad-loop-coordinator agent loads is part
    of the installed payload (installer.SKILL_NAMES) and ships SKILL + prompt."""
    skill_dir = SKILL_ROOT / "bmad-loop-coordinator"
    assert (skill_dir / "SKILL.md").is_file()
    assert (skill_dir / "customize.toml").is_file()
    assert (skill_dir / "prompt.txt").is_file()


def test_loop_coordinator_skill_bootstrap_and_human_gate() -> None:
    """The skill's bootstrap rule and human-present gate must be present, and its
    customize.toml must be a valid [workflow] surface for resolve_customization."""
    content = (SKILL_ROOT / "bmad-loop-coordinator" / "SKILL.md").read_text(encoding="utf-8")
    assert "skill({ name" in content or "skill({" in content
    assert "human-present" in content
    assert "question" in content
    assert "setsid" in content or "tmux" in content
    customize = (SKILL_ROOT / "bmad-loop-coordinator" / "customize.toml").read_text(
        encoding="utf-8"
    )
    assert "[workflow]" in customize
