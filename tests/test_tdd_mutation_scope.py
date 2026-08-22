"""Full-mutation ownership — tdd_cycle_gate denies full-scope mutation commands
while a @s cycle is open (loop mode) and lets the coordinator run them at RELEASE.

Mirrors the reference `keep full mutation coordinator-owned at RELEASE` change:

- Full-scope commands (`make [-flags] mutation-check`, `[uv run [python3 -m]]`
  `mutmut run`, bare `mutmut run`, `sh -c`/`bash -c` wrappers, brace-spelling
  `make muta{t,}tion-check`, and `env X=1 make mutation-check`) are DENIED while a
  cycle is open (loop mode) unless the phase is READY with no RED in flight (the
  coordinator's RELEASE point).
- Named-mutant inspection (`uv run mutmut show <name>`) and targeted
  `uv run mutmut run '<id>'` (``<id>`` matches ``\\w+__mutmut_\\d+``) stay allowed
  from any phase, and do NOT mask a separate full-scope clause in the same command.
- Clause-scoped: benign commands that merely mention the mutation text
  (``git commit -m "run mutmut run yet"``, ``grep 'make mutation-check' docs/``)
  are not denied. Legacy (non-loop) mode remains FAIL-OPEN by design.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

PYTHON_GATE = Path(__file__).parents[1] / "hooks" / "tdd_cycle_gate.py"


def _setup_workspace(tmp_path: Path, *, story_key: str = "1-6-mutation-scope") -> Path:
    gate_target = tmp_path / "hooks" / "tdd_cycle_gate.py"
    gate_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PYTHON_GATE, gate_target)

    story_dir = tmp_path / "_bmad-output" / "implementation-artifacts"
    story_dir.mkdir(parents=True, exist_ok=True)
    story_file = story_dir / f"story-{story_key}.md"
    story_file.write_text(f"# Story {story_key}\n\n## TDD Bitácora\n\n", encoding="utf-8")
    return tmp_path


def _run_gate(
    workspace: Path,
    payload: dict,
    *,
    story_key: str = "1-6-mutation-scope",
    env_extra: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    env = {**os.environ, "BMAD_LOOP_MODE": "1", "BMAD_LOOP_STORY_KEY": story_key}
    if env_extra:
        env.update(env_extra)
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
            "file_path": "_bmad-output/implementation-artifacts/story-1-6-mutation-scope.md",
            "new_string": new_string,
        },
    }


def _pytest(outcome: str) -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "uv run pytest tests/"},
        "tool_response": {"stdout": "1 " + outcome, "stderr": ""},
    }


def _bash(command: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


_MUTATION_DENY_MSG = "Full mutation is coordinator-owned at RELEASE"


def _drive_to_coding(workspace: Path) -> None:
    """RED flow → phase RED_SEEN → ROJO edit → CODING, with a RED test written."""
    # Model-routing order: coordinator Skill → Task tdd-red-ornith → Skill tdd-red.
    assert _run_gate(workspace, _skill("bmad-tdd-coordinator"))[0] == 0
    assert _run_gate(workspace, _task("tdd-red-ornith"))[0] == 0  # red_pending True
    assert _run_gate(workspace, _skill("tdd-red"))[0] == 0
    # write the RED test (marks red_test_written), then fail it
    test_edit = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "tests/unit/test_new_behavior.py",
            "new_string": "def test_x():\n    assert False",
        },
    }
    assert _run_gate(workspace, test_edit)[0] == 0
    assert _run_gate(workspace, _pytest("failed"), env_extra={"BMAD_LOOP_MODE": "1"})[0] == 0
    # ROJO bitácora → CODING
    assert _run_gate(workspace, _edit_story("**ROJO (@s1)** — RED confirmed"))[0] == 0


def test_full_mutation_denied_mid_cycle(tmp_path: Path) -> None:
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)  # phase == CODING, RED in flight
    for command in [
        "make mutation-check",
        "make mutation",
        "uv run mutmut run",
        "uv run python -m mutmut run",
        "python3 -m mutmut run",
        "python -m mutmut run",
        "sh -c 'make mutation-check'",
        'bash -c "uv run mutmut run"',
        "env X=1 make mutation-check",
        "make muta{t,}tion-check",
        # make with leading flags (realistic parallel / dir variants):
        "make -j8 mutation-check",
        "make -C . mutation-check",
        "make -C sub mutation-check",
        "make --directory=. mutation-check",
        "make -j 8 mutation-check",
        "make -f Makefile mutation-check",
        # alternative make binaries:
        "gmake mutation-check",
        "bmake mutation-check",
        # sudo / env with flags (round-2 hardening):
        "sudo -u root make mutation-check",
        "sudo -E make mutation-check",
        "env -i PATH=/usr/bin make mutation-check",
        "env --unset=FOO make mutation-check",
        # quote-aware sudo/env prefix (round-3 hardening):
        'env AA=1 BB="two words" make mutation-check',
        'env X="a b" make mutation-check',
        'sudo -u "user name" make mutation-check',
        "sudo -- make mutation-check",
        # quote-spliced make target (shell concatenation):
        "make mu't'ation-check",
        "make mut''ation-check",
        # wrappers widen (long flags / other shells):
        "bash --noprofile -c 'make mutation-check'",
        "zsh -c 'uv run mutmut run'",
        # versioned interpreters / venv binary / uv flags:
        "python3.12 -m mutmut run",
        "python3.13 -m mutmut run",
        "./.venv/bin/mutmut run",
        "uv run --python 3.12 mutmut run",
        "uvx mutmut run",
        "uv run pytest && uvx mutmut run",
        # targeted inspection never masks a separate full-scope clause:
        "make mutation-check && mutmut run 'name_x__mutmut_1'",
        "mutmut run 'name_x__mutmut_1' && make mutation-check",
        "uv run mutmut run 'name_x__mutmut_1' && uv run mutmut run",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY (rc 2) for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err, f"deny message missing for {command!r}: {err}"


def test_benign_mutation_mention_not_denied_mid_cycle(tmp_path: Path) -> None:
    """Commands that merely mention mutation text must NOT be denied (clause-scoped)."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)  # phase == CODING, RED in flight
    for command in [
        'git commit -m "do not run mutmut run yet"',
        "grep -r 'make mutation-check' docs/",
        "python3 -c \"print('mutmut run in log')\"",
        "uv run pytest -k mutmut tests/",
        "uv run mutmut show mutants/0001_x__mutmut_1",
        "uv run mutmut results",
        "mutmut results",
        # quoted separators that merely mention the text MUST NOT spawn clauses:
        "echo 'run; make mutation-check next'",
        "git commit -m 'done; make mutation-check next'",
        "echo 'x | make mutation-check'",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW (rc 0) for {command!r}, got rc={rc}"


def test_full_mutation_denied_while_red_pending(tmp_path: Path) -> None:
    ws = _setup_workspace(tmp_path)
    # Fresh READY, but a RED task is pending → full mutation must be refused.
    assert _run_gate(ws, _skill("bmad-tdd-coordinator"))[0] == 0
    assert _run_gate(ws, _task("tdd-red-ornith"))[0] == 0  # red_pending True
    rc, _out, err = _run_gate(ws, _bash("make mutation-check"))
    assert rc == 2
    assert _MUTATION_DENY_MSG in err


def _run_gate_cli(workspace: Path, *args: str, story_key: str = "1-6-mutation-scope") -> int:
    env = {**os.environ, "BMAD_LOOP_MODE": "1", "BMAD_LOOP_STORY_KEY": story_key}
    result = subprocess.run(
        ["python3", str(PYTHON_GATE), *args],
        cwd=str(workspace),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode


def test_full_mutation_allowed_at_release_ready(tmp_path: Path) -> None:
    ws = _setup_workspace(tmp_path)
    # Coordinator RELEASE: READY with no RED in flight and the coordinator seen.
    assert _run_gate(ws, _skill("bmad-tdd-coordinator"))[0] == 0
    for command in [
        "make mutation-check",
        "uv run mutmut run",
        "uv run python -m mutmut run",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, (
            f"full mutation must be allowed at RELEASE (READY, no red pending) "
            f"for {command!r}; got rc={rc}"
        )


def test_reset_clears_red_pending_reallows_mutation(tmp_path: Path) -> None:
    """Recovery hatch: `gate reset` clears red_pending so the coordinator can
    run mutation at RELEASE again after a violation/false RED."""
    ws = _setup_workspace(tmp_path)
    assert _run_gate(ws, _skill("bmad-tdd-coordinator"))[0] == 0
    assert _run_gate(ws, _task("tdd-red-ornith"))[0] == 0  # red_pending True → deny
    rc, _out, err = _run_gate(ws, _bash("make mutation-check"))
    assert rc == 2
    assert _MUTATION_DENY_MSG in err
    # reset → red_pending False → full mutation allowed again
    assert _run_gate_cli(ws, "reset") == 0
    rc, _out, _err = _run_gate(ws, _bash("make mutation-check"))
    assert rc == 0, "after reset at READY, full mutation must be allowed at RELEASE"


def test_reset_only_alone_does_not_mask_mutation(tmp_path: Path) -> None:
    """The reset hatch must be a single-clause, single-command invocation; a command
    that chains (or uses substitution with) mutation is NOT allowed to ride it."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)  # phase == CODING
    for command in [
        "echo tdd_cycle_gate.py reset; make mutation-check",
        "echo 'tdd_cycle_gate.py reset' > /tmp/x && make mutation-check",
        "python3 hooks/tdd_cycle_gate.py reset $(make mutation-check)",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_named_mutant_inspection_allowed_mid_cycle(tmp_path: Path) -> None:
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)  # CODING, red in flight
    for command in [
        "uv run mutmut show mutants/0001_xxx__mutmut_1",
        "uv run mutmut run 'name__mutmut_5'",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"named-mutant inspection must be allowed for {command!r}, got rc={rc}"


def test_path_scoped_mutmut_is_full_and_denied(tmp_path: Path) -> None:
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    # A path-scoped `mutmut run 'tests/x.py'` is NOT a named-mutant inspection and
    # must be treated as full-scope → denied mid-cycle.
    rc, _out, err = _run_gate(ws, _bash("uv run mutmut run 'tests/test_new_behavior.py'"))
    assert rc == 2
    assert _MUTATION_DENY_MSG in err


def test_make_flag_spellings_are_denied(tmp_path: Path) -> None:
    """make mutation-check with leading flags (-C, -j, -f) is now caught by the
    clause-scoped regex (hardened after the adversarial round), not a bypass."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "make -C . mutation-check",
        "make --directory=. mutation-check",
        "make -j8 mutation-check",
        "make -f Makefile mutation-check",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_legacy_mode_fail_open_unchanged(tmp_path: Path) -> None:
    """Outside loop mode the gate is FAIL-OPEN by design: mutation commands are
    not denied (the audited bypass / non-loop contract owns that decision)."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)  # sets loop-mode files, but we will run WITHOUT the loop env
    # Run the gate WITHOUT BMAD_LOOP_MODE → legacy path, mutation must pass.
    env = {**os.environ}
    for key in ("BMAD_LOOP_MODE", "BMAD_LOOP_STORY_KEY"):
        env.pop(key, None)
    result = subprocess.run(
        ["python3", str(PYTHON_GATE)],
        cwd=str(ws),
        env=env,
        input=json.dumps(_bash("make mutation-check")),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"legacy mode must remain fail-open; got rc={result.returncode}"


def test_refactor_skill_wording_points_to_release() -> None:
    """Assert the shipped wording drives the new contract: REFACTOR does not
    run/certify full mutation; RELEASE is the owner."""
    project_root = Path(__file__).parents[1]
    refactor_skill = (project_root / "skills" / "tdd-refactor" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    refactor_prompt = (project_root / "skills" / "tdd-refactor" / "prompt.txt").read_text(
        encoding="utf-8"
    )
    coordinator = (project_root / "skills" / "bmad-tdd-coordinator" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "Full mutation is coordinator-owned at RELEASE" in refactor_skill
    assert "coordinador" in refactor_skill and "RELEASE" in refactor_skill
    assert "RELEASE del coordinador" in refactor_prompt or "RELEASE" in refactor_prompt
    assert "UNA vez" in coordinator
    assert "Full mutation is NOT part of REFACTOR" in coordinator
    assert "mutmut results" in coordinator  # never certify with `results`


def test_refactor_agent_template_denies_full_mutation() -> None:
    """The OpenCode template's tdd-refactor-ornith denies full mutation in
    permission.bash and its prompt routes it to the coordinator's RELEASE."""
    lines = (
        (Path(__file__).parents[1] / "opencode" / "agents" / "opencode.json.template")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    template = json.loads("\n".join(line for line in lines if not line.lstrip().startswith("#")))
    agent = template["agent"]["tdd-refactor-ornith"]
    bash = agent["permission"]["bash"]
    assert bash.get("make mutation-check") == "deny"
    assert bash.get("uv run mutmut *") == "deny"
    assert bash.get("uv run pytest *") == "allow"
    assert "RELEASE" in agent["prompt"]


def test_round4_security_bypasses_closed(tmp_path: Path) -> None:
    """Round-4 security fixes: uvx chain is a full runner; env -S STRING makes
    the string the real command (GNU coreutils); gmake/bmake are make; nested
    $(...) substitution is scanned for full scope midline."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "uvx mutmut run",
        "env -S 'make mutation-check'",
        "env -S 'python3 -m mutmut run'",
        "env --split-string='make mutation-check'",
        "echo $(make mutation-check)",
        "echo $(echo $(make mutation-check))",
        "bash -lc 'make mutation-check'",
        "sh -lc 'uv run mutmut run'",
        "gmake mutation-check",
        "bmake mutation-check",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_round4_benign_substitution_allowed(tmp_path: Path) -> None:
    """Substitution with benign content / named inspection stays allowed."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "echo $(git log -1)",
        "cmd $(mutmut show x__mutmut_1)",
        "cmd `mutmut show x__mutmut_1`",
        "env -S 'echo hi'",
        "env -S 'git status'",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW for {command!r}, got rc={rc}"


def test_round5_bypasses_closed(tmp_path: Path) -> None:
    """Round-5 fixes: env -S attached/split, substitution splices, unquoted -c,
    and nested substitution all DENY mid-cycle."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "env -S' make mutation-check'",
        "env -S 'sudo -n make mutation-check'",
        "env -S 'env A=1 make mutation-check'",
        "env -S '/bin/sh -c make mutation-check'",
        "env -S' make mutation-check'",
        "make$() mutation-check",
        "mutmut$() run",
        "uv run mut$()mut run",
        "make $(echo mu)tation-check",
        "python3 -m mut$(echo mut) run",
        "sh -c make mutation-check",
        "/bin/sh -c make mutation-check",
        "/bin/bash -c make mutation-check",
        "echo $(echo $(echo $(echo $(make mutation-check))))",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_round5_single_quoted_literal_mention_allowed(tmp_path: Path) -> None:
    """Single-quoted `'$(...)'` / backticks are LITERAL in bash → not denied."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "echo 'literal $(make mutation-check) text'",
        "echo '`make mutation-check`'",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW for {command!r}, got rc={rc}"


def test_round5_nested_substitution_is_fast(tmp_path: Path) -> None:
    """Nested ${...} must not stall the gate (single-pass scanner, O(n))."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    depth = 22
    payload = "make mutation-check"
    for _ in range(depth):
        payload = f"$( {payload} )"
    deep = "echo " + payload
    import time

    start = time.monotonic()
    rc, _out, err = _run_gate(ws, _bash(deep))
    elapsed = time.monotonic() - start
    assert rc == 2, f"expected DENY (single-pass) for deep nesting, got rc={rc}"
    assert elapsed < 2.0, f"gate too slow on {depth}-deep nesting: {elapsed:.2f}s"


def test_round6_reset_hatch_not_ridden_by_prefix(tmp_path: Path) -> None:
    """reset must be the WHOLE head — a mutation-bearing command with a trailing
    `…/tdd_cycle_gate.py reset` cannot ride the recovery hatch."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "make mutation-check hooks/tdd_cycle_gate.py reset",
        "uv run --python 3.12 mutmut run hooks/tdd_cycle_gate.py reset",
        "python3 hooks/tdd_cycle_gate.py reset && make mutation-check",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
    # Plain reset still allowed
    assert _run_gate_cli(ws, "reset") == 0


def test_round6_deep_substitution_past_cap_still_denied(tmp_path: Path) -> None:
    """Bash executes substitution at any depth; the cap must not drop payloads."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    depth = 70
    payload = "make mutation-check"
    for _ in range(depth):
        payload = f"$( {payload} )"
    rc, _out, err = _run_gate(ws, _bash("echo " + payload))
    assert rc == 2, f"expected DENY for depth-{depth} nesting, got rc={rc}"


def test_round6_mutmut_param_reassembly_denied(tmp_path: Path) -> None:
    """Parameter-expansion / backtick can reassemble `mutmut run` at runtime."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "mut${U}mut run",
        "mutmut ru${N} n",
        "python3 -m mut${U}mut run",
        "uv run mut${U}mut run",
        "python3 -m mut`echo mu`t run",
        "uv run mut`echo mu`t run",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"


def test_round7_reset_variants_allowed(tmp_path: Path) -> None:
    """Recovery hatch stays usable for project-natural invocation forms."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "uv run python hooks/tdd_cycle_gate.py reset",
        "./.venv/bin/python hooks/tdd_cycle_gate.py reset",
        "env X=1 python3 hooks/tdd_cycle_gate.py reset",
        "python3 hooks/tdd_cycle_gate.py reset",
        "./hooks/tdd_cycle_gate.py reset",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW (hatch) for {command!r}, got rc={rc}"


def test_round7_deep_150_substitution_still_denied(tmp_path: Path) -> None:
    """Bash executes substitution at any depth; no depth window may drop it."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    depth = 150
    payload = "make mutation-check"
    for _ in range(depth):
        payload = f"$( {payload} )"
    rc, _out, err = _run_gate(ws, _bash("echo " + payload))
    assert rc == 2, f"expected DENY for depth-{depth} nesting, got rc={rc}"


def test_round7_demangle_reassembly_denied(tmp_path: Path) -> None:
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "mu${T}mut run",
        "mu${T}mut run",
        "m${A}ut${B}mut run",
        "python3 -m mu${T}mut run",
        "m${A}ake mutation-check",
        "mut${X}utation-check make",
        "u${V}v run mut${N}mut run",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"


def test_round7_benign_heads_not_blocked(tmp_path: Path) -> None:
    """git commit / echo / var-assign with ${mut} in body must NOT be blocked."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        'git commit -m "I will run mut${X}test"',
        "grep 'mut${U}mut' docs/",
        "echo mut${UNSET}",
        "mut${unset}=value",
        "echo 'run${N} build'",
        "printf '%s\\n' 'mut${U}mut run'",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW for {command!r}, got rc={rc}"


def test_round8_bare_var_splice_denied(tmp_path: Path) -> None:
    """`$X` short-var splices reassemble mutation argv at runtime."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "mu$Xmut run",
        "ma$Xke mutation-check",
        "mut$Tmut run",
        "python3 -m mu$Xmut run",
        "mut$X mutation-check",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"


def test_round8_benign_path_splice_allowed(tmp_path: Path) -> None:
    """A benign `$VAR` (single- or multi-char) in a NON-mutation head stays allowed."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "echo $PATH make build",
        "echo $CC build",
        "git commit -m 'ma$Xke later'",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW for {command!r}, got rc={rc}"


def test_round9_default_value_reassembly_denied(tmp_path: Path) -> None:
    """${Var:-word}/${Var=word}/${Var:+word} literal cargo reassembles argv.

    With the var unset (attacker's own names), `${A:-ma}${B:-ke}` expands to
    `make`; the deny must still fire mid-cycle for the canonical full forms.
    """
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "m${A:-a}k${B:-e} mutation-check",
        "${A:-ma}${B:-ke} mutation-check",
        "m${A:-u}${B:-t}mut run",
        "python3 -m m${A:-u}${B:-t}mut run",
        "uv run m${A:-u}${B:-t}mut run",
        "u${v:-v} run m${A:-u}${B:-t}mut run",
        "m${A:=a}k${B:=e} mutation-check",
        "m${A:-u}${B:-m}ut run",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_round9_benign_default_var_heads_allowed(tmp_path: Path) -> None:
    """Benign ${Var:-word} in a NON-mutation head stays allowed (no crash)."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "echo ${A:-hi}",
        "git commit -m '${A:-done}'",
        "ls ${HOME:-/tmp}",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW for {command!r}, got rc={rc}"


def test_round10_nested_default_and_positional_reassembly_denied(tmp_path: Path) -> None:
    """Nested `${:-${:-…}}` default cargo and `$@`/`$*` positional splices
    reassemble `make`/`mutmut` argv and must DENY mid-cycle."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "${A:-${B:-make mutation-check}}",
        "${A:-ma${B:-ke} mutation-check}",
        "${A:-${B:-mu}${C:-t}mut run}",
        "make${@} mutation-check",
        "mut${@}mut run",
        "mut${*}mut run",
        "make$@ mutation-check",
        "mut$@mut run",
        "${@:-make mutation-check}",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_round11_deep_nested_default_reassembly_denied(tmp_path: Path) -> None:
    """Nested ${A:-${…}} default cargo at depth >16 (the old fixpoint cap) must
    still reassemble `make`/`mutmut` and DENY mid-cycle."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for depth in (17, 40):
        mk = "make mutation-check"
        for _ in range(depth):
            mk = f"${{A:-{mk}}}"
        rc, _out, err = _run_gate(ws, _bash(mk))
        assert rc == 2, f"expected DENY depth-{depth}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_round12_mutmut_head_substitution_verb_denied(tmp_path: Path) -> None:
    """A mutmut-runner head whose verb is supplied by `${Var:-$(…)}` output
    (``mutmut ${A:-$(echo run)} src/`` → bash runs `mutmut run src/`) must DENY
    mid-cycle (mirror of the make-head substitution net)."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "mutmut ${A:-$(echo run)} src/",
        "uv run mutmut ${A:-$(echo run)}",
        "mutmut $A${B:-$(echo run)} src/",
        "python3 -m mutmut ${A:-$(echo run)} src/",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err
    # Control: a plain full-scope mutmut run is denied; named inspection allowed.
    rc, _out, err = _run_gate(ws, _bash("uv run mutmut run src/"))
    assert rc == 2
    rc, _out, _err = _run_gate(ws, _bash("uv run mutmut run 'name__mutmut_5'"))
    assert rc == 0


def test_round13_runner_net_no_fp_on_pytest(tmp_path: Path) -> None:
    """uv/python/pypy heads with substitutions that are NOT mutmut must not be
    denied (the R12 runner-head net must only fire on mutmut-headed clauses)."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "uv run pytest ${A:-x} tests/",
        "python3 -m pytest ${X:-inject} tests/",
        "uv run pytest $EXTRA tests/",
        "python3 scripts/gen.py ${PROFILE}",
        "uv run python scripts/x.py ${A}",
        "pypy3 -m pytest tests/ ${A:-x}",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW for {command!r}, got rc={rc}"


def test_round14_backslash_envassign_uvx_head_denied(tmp_path: Path) -> None:
    """Backslash word-splices, direct env-assignment heads and uvx/path/command
    head forms all reassemble `make`/`mutmut` argv and must DENY mid-cycle.
    (Indirect `$(echo …)`-output assignment remains the documented static
    exec-output limit, same class as `python -c`/`npx`.)"""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "ma\\ke mutation-check",
        "make mu\\tation-check",
        "MUT=mutmut $MUT run",
        "MAKE=make $MAKE mutation-check",
        "uvx mutmut ${A:-$(echo run)}",
        "/usr/bin/make mutation-check",
        "command make mutation-check",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_round15_command_and_line_continuation_denied(tmp_path: Path) -> None:
    """`command`-prefixed mutmut/make heads and unquoted backslash-newline line
    continuations reassemble `make`/`mutmut` argv and must DENY mid-cycle."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "command mutmut run src/",
        "command uv run mutmut run",
        "command python3 -m mutmut run",
        "command -p make mutation-check",
        "make \\\nmutation-check",
        "make \\\n mutation-check",
        "mutmut \\\n run",
        "uv run mutmut \\\n run",
        "MUT=mutmut \\\n $MUT run",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_round15_heredoc_literal_mention_not_denied(tmp_path: Path) -> None:
    """Inside a heredoc the content is LITERAL (no line continuation), so a doc
    that merely prints `make \⏎ mutation-check` as TEXT is not a mutation run."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "cat <<'EOF'\nmake \\\nmutation-check\nEOF",
        "cat <<EOF\nmutmut \\\n run\nEOF",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW (heredoc literal) for {command!r}, got rc={rc}"


def test_round16_builtin_wrapper_heredoc_b3_denied(tmp_path: Path) -> None:
    """`builtin command`, `-c` wrapper payload substitution, and heredoc-marked
    line continuations that bash really executes must DENY mid-cycle."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "builtin command make mutation-check",
        "builtin command mutmut run src/",
        "builtin command -p make mutation-check",
        "bash -c 'echo $(make mutation-check)'",
        "sh -c 'echo $(make mutation-check)'",
        "bash -lc 'x=$(make mutation-check)'",
        "bash -c 'echo $(uv run mutmut run)'",
        "cat <<EOF; make \\\nmutation-check\ntext\nEOF",
        "cat <<EOF && make \\\nmutation-check\nbody\nEOF",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_round16_heredoc_literal_and_wrapper_benign_allowed(tmp_path: Path) -> None:
    """Heredoc bodies are literal (never executed, incl. `\⏎` inside), and
    benign -c wrappers / builtin usages must be allowed."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "cat <<'EOF'\nmake \\\nmutation-check\nEOF",
        "cat <<EOF\nmake mutation-check\nEOF",
        "cat <<EOF\nuv run mutmut run\nEOF",
        "cat <<EOF\nmake build\nEOF",
        "bash -c 'echo $(git log -1)'",
        "sh -c 'echo $(git log -1)'",
        "builtin echo hi",
        "builtin command echo hi",
        "builtin command -v pytest",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW for {command!r}, got rc={rc}"


def test_round17_ansi_subshell_heredocunq_denied(tmp_path: Path) -> None:
    """R17 closures: ANSI-C quoted heads, subshell/brace/time/nohup wrappers, and
    `$(…)` inside UNQUOTED heredoc bodies (which bash expands) all DENY."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "$'make' mutation-check",
        "$'mutmut' run",
        "bash -c \"$'make' mutation-check\"",
        "cat <<EOF\n$(make mutation-check)\nEOF",
        "cat <<-EOF\n\t`mutmut run`\n\tEOF",
        "(make mutation-check)",
        "( make mutation-check )",
        "{ make mutation-check; }",
        "(uv run mutmut run)",
        "{ uv run mutmut run; }",
        "time make mutation-check",
        "time uv run mutmut run",
        "nohup make mutation-check",
        "nohup mutmut run src/",
    ]:
        rc, _out, err = _run_gate(ws, _bash(command))
        assert rc == 2, f"expected DENY for {command!r}, got rc={rc}"
        assert _MUTATION_DENY_MSG in err


def test_round17_heredoc_quoted_and_subst_benign_allowed(tmp_path: Path) -> None:
    """Quoted heredoc is fully literal; unquoted plain text stays data; and
    benign `$(…)` (no mutation) / wrappers stay allowed."""
    ws = _setup_workspace(tmp_path)
    _drive_to_coding(ws)
    for command in [
        "cat <<'EOF'\nmake mutation-check\nEOF",
        "cat <<EOF\nmake mutation-check\nEOF",
        "cat <<EOF\nmake build\nEOF",
        "bash -c 'echo $(git log -1)'",
        "$'echo' hi",
        "$(git log -1)",
        "time echo hi",
        "nohup echo hi",
        "{ echo hi; }",
        "( echo hi )",
    ]:
        rc, _out, _err = _run_gate(ws, _bash(command))
        assert rc == 0, f"expected ALLOW for {command!r}, got rc={rc}"
