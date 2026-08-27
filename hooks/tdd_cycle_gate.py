#!/usr/bin/env python3
"""bmad-gherkin-tdd — mechanical TDD-cycle gate (the forcing function for the TDD Bitácora).

This is the *gate* the TDD methodology needs. Advisory prose in the coordinator's override
layer and a completeness DoD check at dev-story Step 9 both failed: advisory context loses
to numbered gated steps, and an end-of-run completeness check is satisfiable by writing the
whole bitácora at the end. This script enforces the **order and timing** of each
Red→Green→Refactor cycle mechanically, as CLI hooks — it does NOT police the *content* (the
agent still writes the rich reasoning/decisions that are the spirit of the bitácora; we only
force *when* it is written).

State machine (one open ``@s`` cycle at a time), persisted in the state dir
(``BMAD_TDD_STATE_DIR``, default ``.bmad-harness/tdd-state.json``):

    READY ──(test FAIL)──▶ RED_SEEN ──(story edit "ROJO:")──▶ CODING
      ▲                                                           │
      │                                            (Edit src/** allowed)
      │                                                           ▼
      │                                                (test PASS)──▶ GREEN_SEEN
      │                                                                     │
      │                                                          (story edit "VERDE:") ▼
      └──(story edit "REFACTOR:")── REFACTOR ◀─(story edit "CLEAN:")── CLEAN ────────────┘
                                                        ▲  (tdd-clean gate:
                                                        │   cleaner + coverage)

  A ``development`` RED that PASSES instead of failing (loop mode) is a protocol
  violation: the gate moves to ``RED_VIOLATION`` and denies every further tool
  until the cycle is reset (``python3 hooks/tdd_cycle_gate.py reset``).

Enforced PreToolUse chokepoints (deny = exit 2, reason on stderr → fed back to the agent):
  • Edit/Write/MultiEdit to production (``src/**``):
        READY         → deny (write a failing test first — TDD Law 1)
        RED_SEEN      → deny (log the ROJO entry before writing production)
        CODING        → ALLOW (minimal code to pass)
        GREEN_SEEN    → deny (log VERDE before continuing)
        CLEAN         → allow if tdd-clean seen (structural refactor only)
        REFACTOR      → allow if tdd-refactor seen (no quality-gate gate)
        RED_VIOLATION → deny (RED passed; cycle must be reset)
  • Edit/Write/MultiEdit creating a new test (``tests/**``) while GREEN_SEEN/CLEAN:
        → deny (close the current @s — log VERDE + CLEAN + REFACTOR — before the next test)

Observed PostToolUse events (advance the machine; invalid loop evidence is denied):
  • Bash running pytest or the configured test command: FAIL in READY → RED_SEEN;
    PASS in CODING → GREEN_SEEN.
  • Task completion: a known phase agent advances only with a successful,
    phase-specific ``BMAD_TDD_PHASE_RESULT`` marker and a matching pending Task.
  • Bash test PASS in READY while tdd-red is pending (loop mode): READY → RED_VIOLATION.
  • Edit/Write to the story ``.md``: "ROJO:"@RED_SEEN→CODING, "VERDE:"@GREEN_SEEN→CLEAN,
    "CLEAN:"@CLEAN→REFACTOR, "REFACTOR:"@REFACTOR→READY (cycle closed).

Activation: the gate is **active only while a story is ``in-progress``** in the sprint-status
file (configured via ``BMAD_TDD_SPRINT_STATUS``, default
``_bmad-output/implementation-artifacts/sprint-status.yaml`` — a state the dev flow sets
mechanically). Outside a dev-story run it is inert. During non-TDD phases inside a story
(mutation, large refactors, chores) OUTSIDE loop mode, use the audited bypass:
    python3 hooks/tdd_cycle_gate.py bypass "killing mutants"
    python3 hooks/tdd_cycle_gate.py resume
In loop mode the bypass is disabled and full mutation is coordinator-owned at RELEASE
(once after the last @s); a full-scope mutation run while a @s cycle is open is denied.

Loop Mode (fb70 bypass closure): when ``BMAD_LOOP_MODE=1`` and ``BMAD_LOOP_STORY_KEY`` is set,
the gate activates unconditionally regardless of sprint-status. It additionally:
  - Observes Tool Skill invocations and enforces the coordinator→red→green→refactor order.
  - Keeps per-story state isolated (``tdd-state-<safe>.json``).
  - Blocks direct Bash writes to src/tests (expanded practical closure).
  - Disables the CLI ``bypass`` command.
  - Denies full-scope mutation commands (``make mutation-check``, unscoped
    ``uv run mutmut run``) except at RELEASE (READY with no RED in flight) —
    see _FULL_MUTATION_DENIED; named-mutant inspection stays allowed.
  - Fails-closed on internal exceptions.

CLI:  status | reset | bypass "<reason>" | resume   (also runnable as a hook via stdin JSON)

Fail-open: any internal error allows the tool call (the gate must never brick the workflow);
the error is appended to the audit log.
Exception: in BMAD_LOOP_MODE=1, internal errors fail-closed (exit 2 / deny).
This is a binding requirement — non-loop workflows must never be blocked by gate bugs.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import sys
import tomllib
import uuid
from collections.abc import Mapping
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# ── Locations (relative to the repo root = the hook's cwd) ────────────────────


def _load_project_workflow() -> dict[str, object]:
    """Load gate-facing scalar overrides from the coordinator customization."""
    workflow: dict[str, object] = {}
    for path in (
        Path("_bmad/custom/bmad-tdd-coordinator.toml"),
        Path("_bmad/custom/bmad-tdd-coordinator.user.toml"),
    ):
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        configured = data.get("workflow")
        if isinstance(configured, Mapping):
            workflow.update(configured)
    return workflow


_PROJECT_WORKFLOW = _load_project_workflow()


def _workflow_string(key: str, env_name: str, default: str) -> str:
    """Resolve an environment override, then project customization, then default."""
    value = os.environ.get(env_name)
    if value is None:
        value = _PROJECT_WORKFLOW.get(key, default)
    return value.strip() if isinstance(value, str) and value.strip() else default


# Environment variables remain the highest-precedence runtime override.
_STATE_DIR = Path(os.environ.get("BMAD_TDD_STATE_DIR", ".bmad-harness"))
_STATE_FILE = _STATE_DIR / "tdd-state.json"
_AUDIT_LOG = _STATE_DIR / "tdd-audit.log"
_QUALITY_GATE_CHECKPOINT = Path(
    os.environ.get("BMAD_TDD_QUALITY_GATE", "_quality-gate/quality-gate-latest.json")
)
_SPRINT_STATUS = Path(
    os.environ.get(
        "BMAD_TDD_SPRINT_STATUS",
        "_bmad-output/implementation-artifacts/sprint-status.yaml",
    )
)

# A story key looks like ``1-6-model-...`` (number-number-name); epics are ``epic-N``.
# The gate activates only for an in-progress *story*, never an in-progress epic.
_STORY_IN_PROGRESS_RE = re.compile(r"^\d+-\d+-\S.*:\s*in-progress\b")

# Production and test source prefixes. A project may configure these under the
# coordinator's workflow table or override them at runtime via environment.
_PROD_PREFIX = _workflow_string("prod_prefix", "BMAD_TDD_PROD_PREFIX", "src/")
_TEST_PREFIX = _workflow_string("test_prefix", "BMAD_TDD_TEST_PREFIX", "tests/")


def _validate_gate_scope() -> None:
    """Reject un-auditable N/A gates before a loop can mutate its state."""
    errors: list[str] = []
    for gate in ("cleaner", "coverage", "mutation"):
        applicable_key = f"{gate}_applicable"
        reason_key = f"{gate}_na_reason"
        applicable = _PROJECT_WORKFLOW.get(applicable_key, True)
        reason = _PROJECT_WORKFLOW.get(reason_key, "")
        if not isinstance(applicable, bool):
            errors.append(f"{applicable_key} must be a TOML boolean")
        elif not applicable and (not isinstance(reason, str) or not reason.strip()):
            errors.append(f"{reason_key} is required when {applicable_key}=false")

    if errors:
        _deny("🚫 Configuración de gates inválida: " + "; ".join(errors) + "\n")


# Phases of one Red→Green→Clean→Refactor cycle.
READY, RED_SEEN, CODING, GREEN_SEEN, CLEAN, REFACTOR, RED_VIOLATION = (
    "READY",
    "RED_SEEN",
    "CODING",
    "GREEN_SEEN",
    "CLEAN",
    "REFACTOR",
    "RED_VIOLATION",
)

# TDD phase Tasks are routed by exact agent name. The phase labels in the
# completion marker are deliberately separate from the state-machine labels.
_TASK_AGENT_PHASE = {
    "tdd-red-ornith": READY,
    "tdd-green-ornith": CODING,
    "tdd-clean-ornith": CLEAN,
    "tdd-refactor-ornith": REFACTOR,
}
_TASK_RESULT_EXPECTATIONS = {
    "tdd-red-ornith": ("RED", "ROJO"),
    "tdd-green-ornith": ("GREEN", "VERDE"),
    "tdd-clean-ornith": ("CLEAN", "CLEAN"),
    "tdd-refactor-ornith": ("REFACTOR", "REFACTOR"),
}

# Required skill order (index-based enforcement).
_SKILL_ORDER = tuple(
    os.environ.get(
        "BMAD_TDD_SKILL_ORDER",
        "bmad-tdd-coordinator,tdd-red,tdd-green,tdd-clean,tdd-refactor",
    ).split(",")
)

# Strict story-key regex: must start with alphanumeric, then alnum/./_-
_STORY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Protected state files (structured edits to these are always denied in loop mode).
_PROTECTED_STATE_PATHS = (
    os.environ.get("BMAD_TDD_STATE_DIR", ".bmad-harness") + "/tdd-state",
    os.environ.get("BMAD_TDD_STATE_DIR", ".bmad-harness") + "/tdd-audit.log",
)


def _sanitize_for_filename(key: str) -> str:
    """Sanitize a story key for use in a filesystem filename."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", key)


def _state_file_for(story_key: str | None) -> Path:
    """Return the state file path. Loop mode uses per-story files."""
    if story_key:
        safe = _sanitize_for_filename(story_key)
        return _STATE_DIR / f"tdd-state-{safe}.json"
    return _STATE_FILE


def _lock_file_for(state_file: Path) -> Path:
    """Return the sidecar lock file path, adjacent to the state file."""
    return state_file.with_suffix(".json.lock")


@contextmanager
def _file_lock(state_file: Path):
    """Acquire exclusive fcntl flock on a sidecar lock file adjacent to state_file.

    Creates parent dirs, opens (or creates) the lock file, acquires LOCK_EX.
    Releases on normal exit, SystemExit, or exception.
    State.save() assumes caller holds the lock (no nested acquire).
    """
    lock_path = _lock_file_for(state_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            with suppress(OSError):
                fcntl.flock(lock_fd, fcntl.LOCK_UN)


def _is_loop_mode() -> bool:
    mode = os.environ.get("BMAD_LOOP_MODE", "") == "1"
    key = bool(os.environ.get("BMAD_LOOP_STORY_KEY", ""))
    return mode and key


def _current_story_key() -> str | None:
    return os.environ.get("BMAD_LOOP_STORY_KEY") or None


@dataclass
class State:
    phase: str = READY
    mode: str = "tdd"  # "tdd" (gate enforced) | "bypass" (allow + audit)
    bypass_reason: str = ""
    updated: str = ""
    # Story-specific fields (loop mode).
    story_key: str = ""
    cycle: int = 0
    skill_seen: list[str] = field(default_factory=list)
    last_skill_at: str = ""
    # Model-routing gate: Task→Skill routing.
    # phase_agent_seen records which Task agent was invoked for the current phase.
    phase_agent_seen: list[str] = field(default_factory=list)
    # The coordinator Task whose completion is still awaiting evidence. A
    # PostToolUse Task cannot advance the machine without this pairing.
    pending_task: str = ""
    # OpenCode supplies the parent session id so a matching Skill in a child
    # session does not consume the parent's pending Task pairing.
    pending_task_session_id: str = ""
    # RED-pending guard: True once tdd-red-ornith is invoked in READY, cleared
    # when a FAIL is observed or the cycle closes. A pytest PASS while
    # red_pending is True is a protocol violation → RED_VIOLATION.
    red_pending: bool = False
    # Set when a test file is edited while a RED is pending. RED_VIOLATION only
    # fires if this is True, so a passing *baseline* pytest run before any RED
    # test exists is not misread as a passing RED (false-trigger guard).
    red_test_written: bool = False
    # Internal: track which file was loaded from, for save().
    _state_file: Path = field(default=_STATE_FILE, repr=False)

    @classmethod
    def load(cls, state_file: Path) -> State:
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            fields = (
                "phase",
                "mode",
                "bypass_reason",
                "updated",
                "story_key",
                "cycle",
                "skill_seen",
                "last_skill_at",
                "phase_agent_seen",
                "pending_task",
                "pending_task_session_id",
                "red_pending",
                "red_test_written",
            )
            known = {k: data[k] for k in fields if k in data}
            obj = cls(**known)
            obj._state_file = state_file
            return obj
        except (OSError, ValueError, TypeError):
            obj = cls()
            obj._state_file = state_file
            return obj

    def save(self) -> None:
        """Atomic state write: temp file in same dir → fsync best-effort → os.replace.

        Caller MUST hold the sidecar lock (see _file_lock). No nested acquire.
        """
        self.updated = datetime.now(UTC).isoformat()
        sf = self._state_file
        sf.parent.mkdir(parents=True, exist_ok=True)
        d = asdict(self)
        d.pop("_state_file", None)
        payload = json.dumps(d, indent=2)

        # Atomic write: unique temp file → fsync → os.replace → cleanup temp
        tmp = sf.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                with suppress(OSError):
                    os.fsync(fh.fileno())  # fsync best-effort
            os.replace(tmp, sf)
            tmp.unlink(missing_ok=True)
        except Exception:
            # If os.replace fails, clean up temp to avoid leftovers
            with suppress(OSError):
                tmp.unlink(missing_ok=True)
            raise


def _audit(msg: str) -> None:
    """Append a timestamped line to the audit log (best-effort; never raises)."""
    try:
        _STATE_DIR.mkdir(exist_ok=True)
        with _AUDIT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(UTC).isoformat()} {msg}\n")
    except OSError:
        pass


def _has_quality_gate_checkpoint() -> bool:
    """True if a quality-gate checkpoint exists (i.e. at least one REFACTOR ran it)."""
    return _QUALITY_GATE_CHECKPOINT.exists()


def _check_quality_gate_pass() -> bool | None:
    """Return True/False if checkpoint exists, None if no checkpoint (first cycle)."""
    if not _has_quality_gate_checkpoint():
        return None
    try:
        data = json.loads(_QUALITY_GATE_CHECKPOINT.read_text(encoding="utf-8"))
        return bool(data.get("PASS", False))
    except (OSError, ValueError, TypeError):
        return False


def _story_in_progress() -> bool:
    """The gate is active iff some story is ``in-progress`` in sprint-status.yaml."""
    try:
        text = _SPRINT_STATUS.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(_STORY_IN_PROGRESS_RE.match(line.strip()) for line in text.splitlines())


def _target_paths(tool_input: dict) -> list[str]:
    """Extract edited file path(s) from an Edit/Write/MultiEdit tool input."""
    paths: list[str] = []
    fp = tool_input.get("file_path")
    if isinstance(fp, str):
        paths.append(fp)
    # MultiEdit / batched shapes occasionally carry edits with their own paths.
    for edit in tool_input.get("edits", []) or []:
        if isinstance(edit, dict) and isinstance(edit.get("file_path"), str):
            paths.append(edit["file_path"])
    return paths


def _classify(paths: list[str]) -> str:
    """Return 'prod', 'test', 'other', or 'protected' for the set of edited paths."""
    norm = [p.replace("\\", "/") for p in paths]
    # Check protected paths first
    for pp in _PROTECTED_STATE_PATHS:
        if any(pp in p for p in norm):
            return "protected"
    if any(_PROD_PREFIX in p for p in norm):
        return "prod"
    if any(_TEST_PREFIX in p for p in norm):
        return "test"
    return "other"


def _deny(reason: str) -> None:
    """Block the tool call: exit 2 with the reason on stderr (Claude Code PreToolUse protocol)."""
    sys.stderr.write(reason)
    sys.exit(2)


# ── PreToolUse messages ───────────────────────────────────────────────────────

_RED_FIX = (
    "🔴 Puerta TDD (bmad-gherkin-tdd). Escribe un test que falle y obsérvalo "
    "en ROJO antes de tocar producción (Ley 1 del TDD). Estado del ciclo: {phase}."
)
_ROJO_FIX = (
    "🔴 Puerta TDD: hay un ROJO sin registrar. Escribe la entrada ROJO en la sección "
    "'### TDD Bitácora' del story (línea que empiece con 'ROJO:') ANTES de escribir producción. "
    "Sin ese Edit confirmado, el ciclo ROJO no ha ocurrido."
)
_VERDE_FIX = (
    "🟢 Puerta TDD: el test ya pasa pero VERDE no está registrado. Añade la línea 'VERDE:' a la "
    "bitácora del story antes de seguir tocando producción."
)
_NEXT_TEST_FIX = (
    "🧪 Puerta TDD: cierra el @s actual antes del siguiente test. Registra 'VERDE:', 'CLEAN:' "
    "y 'REFACTOR:' (o 'REFACTOR: nada') en la bitácora del story. Estado del ciclo: {phase}."
)
_BYPASS_HINT = (
    "\n(Si NO estás en un ciclo TDD —matando mutantes, refactor masivo, chore— usa el bypass "
    'auditado: python3 hooks/tdd_cycle_gate.py bypass "<razón>")'
)

_COORDINATOR_MUST_BE_READY = (
    "🚫 Puerta TDD (loop mode): bmad-tdd-coordinator solo puede invocarse en fase READY "
    "(inicio de ciclo). Fase actual: {phase}. Espera a que el ciclo se cierre (REFACTOR → READY)."
)

# ── Full-mutation ownership (coordinator-owned at RELEASE) ────────────────────

_FULL_MUTATION_DENIED = (
    "🚫 Full mutation is coordinator-owned at RELEASE. Phase subagents cannot run "
    "`make mutation-check` or unscoped `uv run mutmut run`. Inspect a known mutant ID "
    "with `uv run mutmut show <name>` or `uv run mutmut run '<name>'` from the coordinator, "
    "then run one canonical `make mutation-check` after the last @s."
)
# Full-scope mutation detection, evaluated PER CLAUSE (a command is split on
# ``;``/``&&``/``||``/``|`` and shell wrappers — quote-aware), so that a
# targeted-mutant clause in the same command does NOT mask a separate full-scope
# clause (e.g. ``make mutation-check && mutmut run '<name__mutmut_1>'`` must STILL
# be denied), and so that benign commands that only *mention* the text
# (``git commit -m "run mutmut run yet"``, ``grep 'make mutation-check' docs/``,
# ``echo '; make mutation-check next'``) are NOT blocked.
#
# Detection is anchored to the clause's leading command: the clause must begin
# (after an optional ``sudo``/``env VAR=...`` prefix, flags allowed on both) with
# ``make`` (any flag/value disposition) whose args include a ``mutation(-check)``
# target, or with a ``mutmut run`` command chain. The mutmut chain tolerates:
#   - ``uv run mutmut run`` and ``uv run --<flag> <arg> mutmut run``
#   - ``python3.12 -m mutmut run`` (any versioned interpreter)
#   - the venv binary directly: ``./.venv/bin/mutmut run``
# A ``mutmut run`` that is a *named* inspection (first arg is a mutant ID like
# ``x__mutmut_1``) is excluded per clause; bare/path-scoped/flag-driven
# ``mutmut run`` invocations are full scope.
_MUTMUT_RUN_CHAIN_RE = re.compile(
    r"^(?:(?:uv|uvx)\s+(?:run\s+)?(?:--[\w=-]+\s+[^\s]+\s+)*)?"
    r"(?:(?:python(?:3(?:\.\d+)?|\.\d+)?|pypy(?:3)?)\s+-m\s+)?"
    r"(?:[\w./-]+/)?mutmut\s+run\b",
    re.IGNORECASE,
)
_MAKE_MUTATION_TARGET_RE = re.compile(
    r"\b(?:muta(?:\{t,\})?tion(?:-check)?)\b",
    re.IGNORECASE,
)
_MAKE_COMMAND_RE = re.compile(
    r"^(?:command\s+)?(?:/[\w./-]+/)?(?:g?make|bmake)(?:\s|$)",
    re.IGNORECASE,
)
_MUTANT_ID_RE = re.compile(r"[\w./\\-]+__mutmut_\d+", re.IGNORECASE)
# Compliance: quote-free command words (used by the sudo/env prefix stripper).
_COMMAND_WORD_RE = re.compile(
    r"^(?:make|mutmut|uvx?|npx|python(?:3(?:\.\d+)?|\.\d+)?|pypy(?:3)?|sh|bash)$",
    re.IGNORECASE,
)
_SHELL_WRAPPER_RE = re.compile(
    r"(?:/bin/)?(?:sh|bash|zsh|fish|ksh)\s+(?:--?[A-Za-z][\w-]*\s+)*"
    r"(?:-c\s*(?:['\"]|(?=\S))|['\"])",
    re.IGNORECASE,
)


def _strip_command_prefix(clause: str) -> str:
    """Strip a leading ``sudo``/``env`` prefix (flags, flag-values and ``VAR=...``
    assignments) so the clause head is the actual command (make / mutmut / python
    / uv). Quote-aware: ``env AA=1 BB="two words" make mutation-check`` must stop
    at ``make``. Flag values are consumed only when they are NOT a reserved
    command word (so ``sudo -E make mutation-check`` stops at ``make``).

    ``env -S STRING`` / ``env -S'STRING'`` / ``env --split-string=STRING`` is a
    meta-flag: GNU/uutils env splits STRING into argv and executes its first
    word, so the STRING IS the real command. We return it (plus any remaining
    tokens) unchanged so the make/mutmut checks run against the real head.
    ``-S'…'`` (attached, single shell word via getopt) is also supported.
    """
    try:
        tokens = shlex.split(clause, posix=True)
    except ValueError:
        tokens = clause.split()  # unbalanced quotes → fall back to naive
    if not tokens:
        return clause.strip()
    # Shell grouping / process-prefix wrappers (R17 F3): `(make mutation-check)`
    # runs `make` in a subshell, `{ make mutation-check; }` in a group, and
    # `time`/`nohup`/`nice`/`setsid`/`stdbuf` run the rest as a prefix. All are
    # the SAME command — peel them to expose the real head (recursive, so
    # `( time make … )` / `time nohup make …` also resolve).
    head = clause.strip()
    while True:
        changed = False
        low = head.lower()
        if low.startswith("(") and not low.startswith("(("):
            # `( cmd ... )` — subshell
            inner = head[1:].lstrip()
            # drop a trailing `)` group after the args
            if inner.endswith(")") and "(" not in inner:
                inner = inner[:-1].rstrip()
            head = inner
            changed = True
        elif low.startswith("{ ") or low == "{":
            # `{ cmd ... ; }` — group; peel `{` and a trailing `; }`
            inner = head[1:].lstrip()
            if inner.endswith(("; }", "}")):
                inner = inner[:-2].rstrip("; ") if ";" in inner else inner.rstrip("}")
            head = inner
            changed = True
        else:
            for word in ("time ", "nohup ", "nice ", "setsid ", "stdbuf "):
                if low.startswith(word):
                    head = head[len(word) :].strip()
                    changed = True
                    break
        if not changed:
            break
    if head != clause.strip():
        return _strip_command_prefix(head)
    if tokens[0].lower() == "builtin":
        # `builtin <cmd>` runs a builtin; `builtin command …` delegates to the
        # command builtin. Peeling `builtin` is FP-safe (`builtin echo hi`,
        # `builtin command -v pytest` stay fine).
        rest = tokens[1:]
        return _strip_command_prefix(" ".join(rest).strip()) if rest else clause.strip()
    if tokens[0].lower() == "command":
        # `command` (and `command -p`) is a bash builtin that runs the next
        # command: `command mutmut run` IS `mutmut run`. Strip it and recurse.
        rest = tokens[1:]
        if rest and rest[0] in ("-p", "-v", "-V", "--"):
            rest = rest[1:]
        return _strip_command_prefix(" ".join(rest).strip()) if rest else clause.strip()
    if tokens[0].lower() not in ("sudo", "env"):
        return clause.strip()
    i = 1  # consumed sudo/env
    while i < len(tokens):
        tok = tokens[i]
        # Split-string meta-flag (GNU/coreutils + uutils): the value is a command.
        if tok == "-S" or tok == "-s" or tok == "--split-string":
            rest = " ".join(tokens[i + 1 :])
            return _strip_command_prefix(rest) if rest else clause.strip()
        m = re.match(r"^-S|^--split-string=", tok)
        if m:
            # Attached forms handled here: `-S'…'` may tokenize with a leading
            # space (quoted value became one token `-S make …`). Treat nearest
            # option-letter boundary after `-S` as the value start.
            if tok.startswith("-S") and tok != "-S":
                value = tok[2:]
                if value.startswith(" "):
                    value = value.lstrip()
                return _strip_command_prefix(" ".join([value, *tokens[i + 1 :]]).strip())
            if "=" in tok:
                value = tok.split("=", 1)[1]
                return _strip_command_prefix(" ".join([value, *tokens[i + 1 :]]).strip())
        # Nested env/sudo chain: recursively strip the next level.
        if tok.lower() in ("sudo", "env"):
            return _strip_command_prefix(" ".join(tokens[i:]))
        # Long/short flag (`--dir`, `-j`, `--unset=FOO`).
        if re.match(r"^--?[A-Za-z][\w-]*(?:=\S+)?$", tok):
            if "=" not in tok and _command_value_flag(tokens, i):
                i += 1  # consume the flag's separate value (e.g. `-u root`)
            i += 1
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tok):
            i += 1  # env VAR=... assignment (quoted value already one token)
        elif not _COMMAND_WORD_RE.match(tok):
            i += 1  # bare non-command word (env binary target?) — tolerate
        else:
            break  # command head reached (make / mutmut / python / ...)
    return " ".join(tokens[i:])


def _command_value_flag(tokens: list[str], i: int) -> bool:
    """True if tokens[i] is a flag whose value is the NEXT token (and that value
    is not itself a command word / flag)."""
    if (i + 1) >= len(tokens):
        return False
    nxt = tokens[i + 1]
    if re.match(r"^--?[A-Za-z]", nxt):
        return False  # next is another flag → current is a boolean flag
    return not _COMMAND_WORD_RE.match(nxt)


def _command_clauses(command: str) -> list[str]:
    """Split a command into top-level clauses (quote-aware).

    Splits on ``;``/``&&``/``||``/``|``/newlines that are OUTSIDE any quoted
    string (single or double quote, incl. here-heredocs treated conservatively),
    then unpacks ``sh -c``/``bash -c`` payloads as their own clause.

    NOTE: a backslash before a newline (``\\\n``) is handled at DETECTION time
    (see ``_mut_clauses_after_continuations``), NOT here: joining it here would
    corrupt the inside of heredocs (whose content is literal — bash does NOT
    line-continue inside ``<<'EOF'``), causing a false deny on a doc that merely
    mentions ``make \⏎ mutation-check`` as text.
    """
    clauses: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = 0
    n = len(command)
    while i < n:
        char = command[i]
        if char in ("'", '"'):
            quote = None if quote == char else (quote or char)
            current.append(char)
        elif char in ";&|\n" and quote is None:
            clause = "".join(current).strip()
            if clause:
                clauses.append(clause)
            current = []
        else:
            current.append(char)
        i += 1
    if current:
        clause = "".join(current).strip()
        if clause:
            clauses.append(clause)

    expanded: list[str] = []
    for clause in clauses:
        match = _SHELL_WRAPPER_RE.search(clause)
        if match:
            inner = clause[match.end() :].strip()
            if inner.startswith(("'", '"')):
                q = inner[0]
                end = inner.find(q, 1)
                if end != -1:
                    inner = inner[1:end]
            expanded.extend(_command_clauses(inner))
        else:
            expanded.append(clause)
    return expanded


def _is_named_mutmut_inspection(clause: str) -> bool:
    """True if a ``mutmut run`` clause is a *named* inspection (first arg is a
    mutant ID). Path-scoped or flag-driven ``mutmut run`` is NOT."""
    match = _MUTMUT_RUN_CHAIN_RE.match(clause)
    if not match:
        return False
    rest = clause[match.end() :].strip()
    if not rest or rest.startswith(("-", "--")):
        return False
    token = rest.split(None, 1)[0].strip("'\"")
    return bool(_MUTANT_ID_RE.search(token))


def _clause_is_full_mutation(clause: str) -> bool:
    """True if a single clause is canonical full-scope mutation.

    Because the head may be produced by an ``env -S``/``-S'…'`` meta-flag whose
    value is itself a wrapped command (``env -S '/bin/sh -c make …'``), the
    stripped base is re-expanded through ``_command_clauses`` so shell-wrapper
    payloads are unpacked before matching.
    """
    base = _strip_command_prefix(clause)
    if not base:
        return False
    return any(_clause_head_is_full_mutation(head) for head in _command_clauses(base))


def _innermost_param_span(text: str) -> tuple[int, int, str] | None:
    """Return (start, end, body) of the INNERMOST `${…}` span (no nested `${`
    inside), or None. Required because nested `${A:-${B:-make}}` has an inner
    `}` that a single `[^}]*` regex cannot balance."""
    start = text.find("${")
    if start == -1:
        return None
    i = start + 2
    depth = 1
    while i < len(text):
        if text.startswith("${", i):
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1, text[start + 2 : i]
        i += 1
    # Unbalanced (misformed) — leave it as-is; caller stops.
    return None


def _demangle_var_default(body: str) -> str:
    """Return the literal CARGO of a `${...}` expansion, or "" if none.

    Bash's parameter expansion: ``${Var:-word}`` / ``${Var=word}`` /
    ``${Var:+word}`` / ``${Var:?word}`` / ``${Var-word}`` expand to ``word``
    (or, for ``:+``, to ``word`` when the var is set) — when the var is
    unset/set accordingly, the WORD becomes part of argv. Also covers special
    parameters (`${@:-word}`, `${*:-word}`). The demangle is conservative
    (assumes unset vars / empty positional args): it keeps the literal cargo and
    recurses on nested `${…}` within it. Plain `${Var}` / `${@}` (no operator)
    and removal patterns (`#pat`/`%pat`) have no cargo.
    """
    # Find the first operator; the NAME may be `@`, `*`, digits, `-`, `?`, etc.
    idx = len(body)
    op = None
    for candidate in (":-", ":+", ":?", ":=", "-", "+", "="):
        j = body.find(candidate)
        if j != -1 and j < idx:
            idx = j
            op = candidate
    if op is not None:
        cargo = body[idx + len(op) :]
        return _shell_demangle(cargo)
    return ""


def _shell_demangle(text: str) -> str:
    """Strip shell expansions enough to reconstruct the argv a command yields.

    Conservative (assumes unset vars / empty positional args, the attacker's own
    tool). Applies to a FIXPOINT so nested ``${…:-${…:-make}}`` and positional
    splices (``make${@}``, ``mut$@mut``, ``${@:-make}``) collapse to the
    reassembled argv: `${…}` default/alternate Cargo is kept and re-demangled
    recursively; `$@`/`$*`/`$N` (positional) have no cargo and vanish; ``$X``
    short vars are stripped; backticks/quotes removed. Used only by nets already
    scoped to mutation-capable clause heads, so aggressive stripping does not
    affect benign ``echo $PATH …`` passages.
    """
    out = text
    # Demangle nested `${…}` to a FULL fixpoint by expanding INNERMOST-first.
    # `re.sub` can't handle nested `${…:-${…}…}` (the `}` inside breaks `[^}]*`),
    # so we scan for the innermost balanced `${…}` span and expand it outward.
    # Each pass removes at least one `${…}` marker, so the loop terminates in
    # O(depth × len) — no hard depth bound, closing the depth≥17 bypass.
    while "${" in out:
        inner = _innermost_param_span(out)
        if inner is None:
            break
        start, end, body = inner
        out = out[:start] + _demangle_var_default(body) + out[end:]
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)=\$\(([^()]*)\)\s+[$]\1\b",
        r"\2 \2",
        out,
    )
    out = re.sub(r"\$\([^()]*\)", "", out)
    # Env-assignment head reassembly: `MUT=mutmut $MUT run` executes `mutmut run`
    # (the assignment then `$VAR`). Resolve `VAR=word $VAR …` FIRST (before the
    # `$X` strip erases the var name) by substituting the value for the var use.
    out = re.sub(
        r"\b([A-Za-z_][A-Za-z0-9_]*)=(\S+)\s+[$]\1\b",
        r"\2 \2",
        out,
    )
    # `@`, `*`, `#`, `?`, digits are not [A-Za-z_]; strip them too (positional / special).
    out = re.sub(r"\$[@*#?0-9]", "", out)
    # ANSI-C quoting: `$'make'` / `$"make"` is `make` as a shell word (the `$`
    # is NOT a variable ref here). Collapse before the `$X` strip so `$'make'`
    # → `make`, never `ake` (which would hide the runner head).
    out = re.sub(r"\$(?:'[^']*'|\"[^\"]*\")", lambda m: m.group(0)[1:], out)
    out = re.sub(r"\$[A-Za-z_]", "", out)  # any single-letter `$X` short var
    out = out.replace("`", "")
    # Backslash escapes: bash folds `ma\ke` → `make` and `\n`+newline is a line
    # continuation (joined before execution), so collapse `\x` → x and strip a
    # trailing `\` before a newline. This closes the backslash word-splice.
    out = re.sub(r"\\(\n|\r\n)", "", out)  # line continuation → join
    out = out.replace("\\", "")
    return out.replace("'", "").replace('"', "")


def _strip_literal_expansions(text: str) -> str:
    """Remove the content of single-quoted spans that CONTAIN an expansion
    (``$``/backtick), leaving plain quoted text (e.g. ``'name__mutmut_5'``)
    untouched. A literal ``'$(make …)'`` / ``'`make …`'`` must not be mistaken
    for a real expansion; a named-mutant ID stays intact."""
    return re.sub(r"'[^']*[${`][^']*'", "''", text)


def _clause_head_is_full_mutation(base: str) -> bool:
    """True if a *stripped* clause head is canonical full-scope mutation."""
    # Single-quoted spans containing expansions are literal in bash — drop their
    # content first so ``'$(make …)'``/``'`make …`'`` never trip the nets.
    base = _strip_literal_expansions(base)
    # Shell-argv-normalized view for the checks, so that quote splices
    # (``mu't'tation-check``) and empty command-substitution splices
    # (``make$() mutation-check``, ``mutmut$() run``) both collapse to the real
    # token before matching.
    normalized = re.sub(r"\$\(\)|`[^`]*`|\$\{\}", "", base)
    normalized = normalized.replace("'", "").replace('"', "")
    # ``make ... mutation(-check)`` at clause head (any flag/value disposition).
    if _MAKE_COMMAND_RE.match(normalized) and _MAKE_MUTATION_TARGET_RE.search(normalized):
        return True
    # Conservative net for the make-head + command-substitution family: ``make
    # $(echo mu)tation-check`` executes `make mutation-check`. Any `make` head
    # whose args contain a substitution is a potential target splice → deny.
    if _MAKE_COMMAND_RE.match(normalized) and re.search(r"\$\(|`|\$\{|\$[A-Za-z]", base):
        return True
    # ``(uv | uvx | python3.12 -m | ./.venv/bin/)... mutmut run`` at the head,
    # and NOT a named inspection.
    if _MUTMUT_RUN_CHAIN_RE.match(normalized):
        return not _is_named_mutmut_inspection(normalized)
    # Conservative net for the mutmut-chain head + substitution family (mirror
    # of the make-head net above): a substitution whose OUTPUT is the verb
    # (``mutmut ${A:-$(echo run)} src/`` → bash runs ``mutmut run src/``) is not
    # observable in the demangled view (the ``$()`` payload disappears), so any
    # mutmut-runner head carrying ``$()``/backtick/``${``/``$X`` is a potential
    # verb splice → deny (over-denial = safe direction; named inspection with
    # NONE of those markers still allowed).
    # Only a head that demangles into a `mutmut`-chain (or plainly contains
    # `mutmut`) is a mutmut verb-splice risk. `uv run`/`python -m` heads WITHOUT
    # `mutmut` are NOT mutation runners (e.g. `uv run pytest ${X:-x}` is benign)
    # — they must not be denied by this net. The demangled clause is used (it
    # strips `$(…)`/`${…}`/backticks correctly), and the runner tokens are the
    # first ones: `mutmut`, `uv run mutmut`, `python3 -m mutmut`. Substitution
    # payloads that merely mention the word (e.g. ``cmd $(mutmut show …)``)
    # vanish in the demangle and never trip this.
    runner_words = _shell_demangle(base)
    runner_head_has_mutmut = bool(
        re.match(
            r"^\s*(?:(?:command\s+)?(?:[\w./-]+/)?(?:uvx?|python(?:3(?:\.\d+)?)?|pypy(?:3)?)\s+"
            r"(?:(?:-m|run)\s+)?(?:[\w./-]+/)?mutmut\b"
            r"|(?:command\s+)?(?:[\w./-]+/)?mutmut\b)",
            runner_words,
            re.IGNORECASE,
        )
        or runner_words.strip().startswith("mutmut")
        or re.match(
            r"^\s*(?:uvx?|python(?:3(?:\.\d+)?)?|pypy(?:3)?)\s+(?:-m\s+)?mutmut\b",
            runner_words,
            re.IGNORECASE,
        )
    )
    if runner_head_has_mutmut and re.search(r"\$\(|`|\$\{|\$[A-Za-z@*]", base):
        return True
    # Conservative REASSEMBLY net (round 6-7): parameter expansion / backtick /
    # $var can reassemble `make` or `mutmut ... run` across variable splices
    # (`mu$Umut`, `ma$Xke`, `m${A}ut${B}mut`). We demangle the raw head and
    # re-run the two canonical checks against the demangled shell view. The net
    # is scoped to the clause HEAD (not a `git commit -m "..."` message) and
    # single-quoted literal mentions were already skipped by the clause splitter.
    demangled = _shell_demangle(base)
    if _MAKE_COMMAND_RE.match(demangled) and _MAKE_MUTATION_TARGET_RE.search(demangled):
        return True
    if _MUTMUT_RUN_CHAIN_RE.match(demangled):
        return not _is_named_mutmut_inspection(demangled)
    # Token-splice fallback (round 7): when the CLAUSE HEAD is a mutation-capable
    # command (`make`/`mutmut`/`uv`/`python`/…), a leading head token that
    # demangles into a `mu`/`ma`/`ru` stem with a $/backtick splice
    # (`mu${T}mut`, `ma${X}ke`) can reassemble a mutation argv at runtime. The
    # whole net is guarded on the FIRST token being a mutation-capable runner, so
    # a benign `echo mut${UNSET}` / `git commit -m "…${mut}…"` message is NOT
    # blocked (its head is echo/git, not make/mutmut). A demangled stem trips it
    # only when it is a plausible reassembled mutation WORD (>=4 chars, or the
    # verb `mut`/`run`).
    head_word = _shell_demangle(base.split(None, 1)[0] if base.split() else "")
    if re.match(
        r"^(?:make|mutmut|mut|uv|uvx|python|pypy|gmake|bmake)[\w-]*$", head_word, re.IGNORECASE
    ) or re.match(r"^mu\w*mut$", head_word, re.IGNORECASE):
        for token in base.split()[:3]:
            if "=" in token:
                continue  # variable assignment, not a command token
            if "$" not in token and "`" not in token:
                continue
            if "$" not in token and "`" in token and not re.search(r"\w`\w", token):
                continue  # standalone backtick span
            stem = _shell_demangle(token)
            if not re.match(r"^(?:mu|ma|ru)", stem, re.IGNORECASE):
                continue
            # Within a mutation-capable head, ANY `ru`/`mu` stem with a splice is
            # a reassembly risk (`mutmut ru${N} n` → `mutmut run`, `mu$Tmut`).
            if re.match(r"^(?:ru|mu|mut|ma)", stem, re.IGNORECASE):
                return True
    return False


# Substitution scan: every ``$(...)``/backtick payload region is collected and
# TESTED — never dropped, regardless of nesting depth (bash executes the whole
# tree, so a 200-deep payload must be checked). `_MAX_SUBST` is only a
# pathological-input guard preventing unbounded recursion on adversarial input;
# the termination guarantee is that each level strips >=2 chars, so the scan is
# bounded by command length. We push beyond the cap whenever the payload still
# contains ``$(``/backtick — dropping there would be a bypass window.
_MAX_SUBST = 100000


def _substitution_payloads(command: str) -> list[str]:
    """Scan a command ONCE and return every ``$(...)``/backtick payload region,
    including nested ones, at any quote-valid context. Single-quoted spans are
    skipped (bash treats ``'...$(...)...'`` as literal), so benign literal
    mentions are not false-denied. Iterative (explicit stack), O(total chars),
    no exponential re-scanning. A payload is pushed for scanning whenever it
    still contains ``$(``/backtick, so deep nesting (up to ``_MAX_SUBST`` levels,
    > command length in practice) is always covered — no depth window.
    """
    results: list[str] = []
    stack: list[tuple[str, int]] = [(command, 0)]
    while stack:
        text, depth = stack.pop()
        i = 0
        n = len(text)
        single = False  # inside a single-quoted span → `$(` / backtick are literal
        while i < n:
            ch = text[i]
            if ch == "'":
                single = not single
                i += 1
                continue
            if single:
                i += 1
                continue
            if ch == "`":
                end = text.find("`", i + 1)
                if end == -1:
                    break
                payload = text[i + 1 : end]
                if payload and payload not in results:
                    results.append(payload)
                    if depth < _MAX_SUBST and ("$(" in payload or "`" in payload):
                        stack.append((payload, depth + 1))
                i = end + 1
            elif text.startswith("$(", i):
                depth_paren = 1
                j = i + 2
                while j < n and depth_paren:
                    if text.startswith("$(", j):
                        depth_paren += 1
                    elif text[j] == ")":
                        depth_paren -= 1
                        if depth_paren == 0:
                            break
                    j += 1
                payload = text[i + 2 : j]
                if payload and payload not in results:
                    results.append(payload)
                    if depth < _MAX_SUBST and ("$(" in payload or "`" in payload):
                        stack.append((payload, depth + 1))
                i = j + 1 if depth_paren == 0 else n
            else:
                i += 1
    return results


def _full_mutation_in_substitution(command: str) -> bool:
    """Detect full-scope mutation hidden inside shell command substitution
    (``$(...)`` or backticks), which bash runs *before* the outer command.

    Single-pass: each region is tested with the CHEAP clause matcher (not the
    recursive ``_is_full_mutation_command``, which would re-scan nested regions
    exponentially). Regions at every nesting depth are already produced as
    siblings by ``_substitution_payloads``, so nested substitution is covered
    without re-entering full detection per depth.
    """
    for payload in _substitution_payloads(command):
        if any(_clause_is_full_mutation(c) for c in _command_clauses(payload)):
            return True
    return False


def _mask_heredoc_bodies(command: str) -> str:
    """Blank out the body of heredocs, preserving executable substitutions.

    Heredoc quoting rules:
      - QUOTED delimiter (`<<'EOF'` / `<<"EOF"`): the whole body is LITERAL —
        nothing in it executes. Blank everything (preserving newline shape).
      - UNQUOTED delimiter (`<<EOF` / `<<-EOF`): plain text stays data (never a
        command), but command substitutions ``$(…)`` and backticks ARE executed
        by bash (their output feeds the reader). So for unquoted heredocs we
        blank the body but KEEP the inner ``$(…)``/backtick spans, letting the
        substitution scan detect ``$(make mutation-check)`` inside the body while
        plain ``make mutation-check`` text never trips a command clause.
    This is why the earlier "mask everything" pass was wrong: it hid the
    executed ``$(…)`` of unquoted heredocs (R17 F2).
    """
    masked = command
    for m in re.finditer(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", command):
        label = m.group(2)
        quoted = bool(m.group(1))
        body_start = command.find("\n", m.end())
        if body_start == -1:
            return masked  # unterminated line → nothing to mask
        body_start += 1
        cursor = body_start
        while True:
            line_end = masked.find("\n", cursor)
            if line_end == -1:
                line = masked[cursor:]
                if line.strip() == label and not quoted:
                    # unquoted → keep $(...) spans only
                    masked = _blank_keep_subs(masked, body_start, cursor + len(line))
                elif line.strip() == label:
                    body = masked[body_start : cursor + len(line)]
                    masked = (
                        masked[:body_start]
                        + ("\n" * body.count("\n"))
                        + masked[cursor + len(line) :]
                    )
                return masked  # unterminated heredoc → ignore rest (or masked prior)
            line = masked[cursor:line_end]
            if line.strip() == label:
                if quoted:
                    body = masked[body_start : line_end + 1]
                    masked = (
                        masked[:body_start] + ("\n" * body.count("\n")) + masked[line_end + 1 :]
                    )
                else:
                    masked = _blank_keep_subs(masked, body_start, line_end + 1)
                break
            cursor = line_end + 1
    return masked


def _blank_keep_subs(text: str, start: int, end: int) -> str:
    """Blank [start,end) of ``text`` preserving ``$(…)``/backtick spans inside
    (they are executed in an unquoted heredoc body)."""
    region = text[start:end]
    keep = re.findall(r"\$\([^()]*\)|`[^`]*`", region)
    if not keep:
        blank = "\n" * region.count("\n")
        return text[:start] + blank + text[end:]
    # Rebuild: blank each line except the spans (place them back in place).
    out = []
    idx = 0
    for span in re.finditer(r"\$\([^()]*\)|`[^`]*`", region):
        out.append("\n" * region[idx : span.start()].count("\n"))
        out.append(region[span.start() : span.end()])
        idx = span.end()
    out.append("\n" * region[idx:].count("\n"))
    return text[:start] + "".join(out) + text[end:]


def _is_full_mutation_command(command: str) -> bool:
    """True if ANY clause (or command substitution within it) is a canonical
    full-scope mutation command. A named inspection in one clause never masks a
    full-scope clause elsewhere.

    Two preprocessing steps run against the FINAL detection view (NOT the raw
    clause splitter, which must stay intact for bitácora / reset semantics):
      1. Backslash-newline (``\\\n``) line continuations are joined FIRST —
         bash resolves them BEFORE delimiting a heredoc, so `<<EOF; make \⏎
         mutation-check` is one command line whose heredoc body starts on the
         FOLLOWING line.
      2. Heredoc bodies are MASKED (literal; never executed) — only run after
         the continuation join so a literal ``\⏎`` inside a heredoc body (now a
         plain space) can never be mistaken for a joined command.
    """
    view = re.sub(r"\\\n", " ", command)
    view = _mask_heredoc_bodies(view)
    clauses = _command_clauses(view)
    if any(_clause_is_full_mutation(c) for c in clauses):
        return True
    # Substitutions can hide inside a shell-wrapper payload (`bash -c 'echo
    # $(make mutation-check)'`): the -c payload is unpacked as its own clause by
    # `_command_clauses`, so scan substitutions per-clause too, not just over the
    # original command string (which would treat the wrapper's single quotes as
    # a literal and skip the inner `$(…)`).
    for cl in clauses:
        if _full_mutation_in_substitution(cl):
            return True
    return _full_mutation_in_substitution(view)


def _full_mutation_allowed(state: State) -> bool:
    """Coordinator RELEASE runs after a closed cycle: READY and no RED in flight."""
    return state.phase == READY and not state.red_pending


# ── Legacy refactor-incomplete message ────────────────────────────────────────

_REFACTOR_INCOMPLETE_FIX = (
    "🚫 Refactor incompleto: la calidad del checkpoint falló. "
    "No se permite editar producción hasta que el ciclo TDD esté completo."
)

# ── Skill ordering and processing ─────────────────────────────────────────────


def _parse_bitacora_tokens(body: str) -> set[str]:
    """Extract bitácora tokens from edit text using colon-delimited markers.

    Detects 'ROJO:', 'VERDE:', 'CLEAN:', 'REFACTOR:' substrings — reliable
    substring match, not regex word-boundary (which can fail after punctuation).
    """
    tokens: set[str] = set()
    for tok in ("ROJO", "VERDE", "CLEAN", "REFACTOR"):
        if re.search(rf"(?:{tok}:|\*\*{tok}(?:\s+\(@s[^)]+\))?\*\*)", body):
            tokens.add(tok)
    return tokens


def _verify_preexisting_marker(prompt_text: str) -> bool:
    """Verify the exact standalone machine marker in a Task prompt.

    The marker `classification=verification_preexisting` must appear as a
    standalone token (surrounded by whitespace or string boundaries).
    Partial matches, case mutations, and embedded occurrences are rejected.
    The prompt must also contain nonempty evidence text beyond the marker.
    """
    MARKER = "classification=verification_preexisting"
    # Standalone token check: word boundary before and after the marker
    pattern = r"\b" + re.escape(MARKER) + r"\b"
    if not re.search(pattern, prompt_text):
        return False
    # Must have nonempty evidence text beyond the marker itself
    evidence = prompt_text.replace(MARKER, "", 1).strip()
    return len(evidence) > 0


def _bitacora_guard(state: State, tool_input: dict) -> None:
    """Read-only PreToolUse guard: reject out-of-phase bitácora tokens.

    NEVER mutates phase or skill_seen. Only observes state and denies if rules violated.
    Skill registration is exclusively handled by the Skill tool handler.
    Phase transitions are exclusively handled by PostToolUse.

    Rules:
    - REFACTOR token present: require phase==REFACTOR AND tdd-refactor in skill_seen.
    - CLEAN token present: require phase==CLEAN AND tdd-clean in skill_seen.
    - VERDE token (not full content): require phase in {GREEN_SEEN, CLEAN, REFACTOR} AND tdd-green.
    - ROJO token: require phase in {RED_SEEN, CODING, GREEN_SEEN, CLEAN, REFACTOR} AND tdd-red.
    - Full content (all 3 tokens) in REFACTOR: allow only if red+green+refactor all seen.
    """
    parts = [
        str(tool_input.get("edit_body", "")),
        str(tool_input.get("new_string", "")),
        str(tool_input.get("old_string", "")),
    ]
    edit_body = "\n".join(parts)
    tokens = _parse_bitacora_tokens(edit_body)
    if not tokens:
        return

    has_refactor = "REFACTOR" in tokens
    has_clean = "CLEAN" in tokens
    has_verde = "VERDE" in tokens
    has_rojo = "ROJO" in tokens
    is_full = has_refactor and has_verde and has_rojo

    # ── REFACTOR token: strictest check ──────────────────────────────────
    if has_refactor and (state.phase != REFACTOR or "tdd-refactor" not in state.skill_seen):
        _deny(
            "🚫 REFACTOR fuera de fase o sin skill visto. "
            f"Fase actual: {state.phase} (requerido REFACTOR). "
            f"tdd-refactor en skill_seen: {'tdd-refactor' in state.skill_seen}. "
            "El token REFACTOR solo es válido en fase REFACTOR con el skill registrado."
        )
        return

    # ── Full content (all 3 tokens) ──────────────────────────────────────
    if is_full:
        # In REFACTOR with all skills → allowed (no mutation)
        if "tdd-red" in state.skill_seen and "tdd-green" in state.skill_seen:
            return
        _deny(
            "🚫 Bitácora completa requiere 'tdd-red' + 'tdd-green' + 'tdd-refactor' "
            "ya registrados en skill_seen. Ningún campo del estado es modificado por este guard."
        )
        return

    # ── CLEAN token (partial) ────────────────────────────────────────────
    if has_clean and (state.phase != CLEAN or "tdd-clean" not in state.skill_seen):
        _deny(
            f"🚫 CLEAN fuera de fase o sin skill visto. "
            f"Fase actual: {state.phase} (requerido CLEAN). "
            f"tdd-clean en skill_seen: {'tdd-clean' in state.skill_seen}."
        )
        return

    # ── VERDE token (partial) ────────────────────────────────────────────
    if has_verde and (
        # tdd-green validates in CODING path without tdd-red (verification_preexisting).
        # Require only phase in {GREEN_SEEN, CLEAN, REFACTOR} AND tdd-green seen.
        state.phase not in {GREEN_SEEN, CLEAN, REFACTOR} or "tdd-green" not in state.skill_seen
    ):
        _deny(
            f"🚫 VERDE fuera de fase o sin skill visto. "
            f"Fase actual: {state.phase} (requerido GREEN_SEEN, CLEAN o REFACTOR). "
            f"tdd-green en skill_seen: {'tdd-green' in state.skill_seen}."
        )
        return

    # ── ROJO token (partial) ─────────────────────────────────────────────
    if has_rojo:
        red_required_phases = {RED_SEEN, CODING, GREEN_SEEN, CLEAN, REFACTOR}
        if state.phase not in red_required_phases or "tdd-red" not in state.skill_seen:
            _deny(
                f"🚫 ROJO fuera de fase o sin skill visto. "
                f"Fase actual: {state.phase} "
                f"(requerido RED_SEEN/CODING/GREEN_SEEN/REFACTOR). "
                f"tdd-red en skill_seen: {'tdd-red' in state.skill_seen}."
            )
            return


def _validate_skill_order(state: State, skill_name: str) -> tuple[bool, str]:
    """Check if invoking skill_name is valid given current state.

    Phase 2 model-routing gate: each Skill requires its matching Task agent
    to have been recorded in phase_agent_seen BEFORE the Skill can proceed.
    Returns (ok, reason). ok=False means DENY with reason.

    For the verification_preexisting CODING path: tdd-green validates in CODING
    with tdd-green-ornith as phase_agent_seen WITHOUT requiring tdd-red.
    For the REFACTOR path after VERDE: tdd-refactor validates in REFACTOR with
    tdd-refactor-ornith as phase_agent_seen WITHOUT requiring all three predecessors.
    Normal development enforcement and all security invariants are preserved.
    """
    # coordinator: only valid in READY (except idempotent duplicate)
    if skill_name == "bmad-tdd-coordinator":
        if state.phase != READY:
            return False, _COORDINATOR_MUST_BE_READY.format(phase=state.phase)
        # Idempotent: if already seen in READY, allow (no-op)
        return True, ""

    # tdd-red: requires coordinator seen + tdd-red-ornith Task seen + phase READY
    if skill_name == "tdd-red":
        if "bmad-tdd-coordinator" not in state.skill_seen:
            return False, (
                "🚫 Orden TDD violado: 'tdd-red' requiere 'bmad-tdd-coordinator' antes. "
                "Skill order obligatorio: coordinator → red → green → refactor."
            )
        if "tdd-red-ornith" not in state.phase_agent_seen:
            return False, (
                "🚫 tdd-red requiere primero invocar el Task 'tdd-red-ornith'. "
                "El Skill NO puede invocarse directamente sin el Task intermedio."
            )
        if state.phase != READY:
            return False, (
                f"🚫 tdd-red solo válido en fase READY (requiere coordinator + tdd-red-ornith). "
                f"Fase actual: {state.phase}."
            )
        return True, ""

    # tdd-green: requires coordinator + tdd-green-ornith + phase CODING.
    # In the verification_preexisting CODING path, tdd-red is NOT required.
    if skill_name == "tdd-green":
        if "bmad-tdd-coordinator" not in state.skill_seen:
            return False, (
                "🚫 Orden TDD violado: 'tdd-green' requiere 'bmad-tdd-coordinator' antes. "
                "Skill order obligatorio: coordinator → red → green → clean → refactor."
            )
        if "tdd-green-ornith" not in state.phase_agent_seen:
            return False, (
                "🚫 tdd-green requiere primero invocar el Task 'tdd-green-ornith'. "
                "El Skill NO puede invocarse directamente sin el Task intermedio."
            )
        if state.phase != CODING:
            return False, (
                f"🚫 tdd-green solo válido en fase CODING (requiere Task "
                f"'tdd-green-ornith'). Fase actual: {state.phase}."
            )
        return True, ""

    # tdd-clean: requires coordinator + tdd-clean-ornith + phase CLEAN.
    if skill_name == "tdd-clean":
        if "bmad-tdd-coordinator" not in state.skill_seen:
            return False, (
                "🚫 Orden TDD violado: 'tdd-clean' requiere 'bmad-tdd-coordinator' antes. "
                "Skill order obligatorio: coordinator → red → green → clean → refactor."
            )
        if "tdd-clean-ornith" not in state.phase_agent_seen:
            return False, (
                "🚫 tdd-clean requiere primero invocar el Task 'tdd-clean-ornith'. "
                "El Skill NO puede invocarse directamente sin el Task intermedio."
            )
        if state.phase != CLEAN:
            return False, (
                f"🚫 tdd-clean solo válido en fase CLEAN (requiere bitácora VERDE). "
                f"Fase actual: {state.phase}."
            )
        return True, ""

    # tdd-refactor: requires coordinator + tdd-refactor-ornith + phase REFACTOR.
    # After VERDE→CLEAN→REFACTOR transitions, refactor proceeds without requiring
    # all three predecessors.
    if skill_name == "tdd-refactor":
        if "bmad-tdd-coordinator" not in state.skill_seen:
            return False, (
                "🚫 Orden TDD violado: 'tdd-refactor' requiere 'bmad-tdd-coordinator' antes. "
                "Skill order obligatorio: coordinator → red → green → clean → refactor."
            )
        if "tdd-refactor-ornith" not in state.phase_agent_seen:
            return False, (
                "🚫 tdd-refactor requiere primero invocar el Task 'tdd-refactor-ornith'. "
                "El Skill NO puede invocarse directamente sin el Task intermedio."
            )
        if state.phase != REFACTOR:
            return False, (
                f"🚫 tdd-refactor solo válido en fase REFACTOR "
                f"(requiere tdd-clean + bitácora CLEAN). "
                f"Fase actual: {state.phase}."
            )
        return True, ""

    # Unknown skill — allow but don't process
    return True, ""


def handle_pre_tool_use(
    tool_name: str,
    tool_input: dict,
    state: State,
    hook_session_id: str = "",
) -> None:
    if _is_loop_mode():
        _handle_loop_mode_pre_tool_use(tool_name, tool_input, state, hook_session_id)
        return

    # Legacy mode: unchanged behaviour
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        sys.exit(0)
    kind = _classify(_target_paths(tool_input))
    if kind == "other" or kind == "protected":
        sys.exit(0)

    if kind == "prod":
        if state.phase in (CODING, CLEAN, REFACTOR):
            sys.exit(0)  # legitimate: writing-to-green / clean-refactor / refactor-in-green
        if state.phase == READY:
            qg_pass = _check_quality_gate_pass()
            if qg_pass is False:
                _deny(_REFACTOR_INCOMPLETE_FIX)
            _deny(_RED_FIX.format(phase=state.phase) + _BYPASS_HINT)
        if state.phase == RED_SEEN:
            _deny(_ROJO_FIX + _BYPASS_HINT)
        if state.phase == GREEN_SEEN:
            _deny(_VERDE_FIX + _BYPASS_HINT)
    elif kind == "test" and state.phase in (GREEN_SEEN, CLEAN, REFACTOR):
        _deny(_NEXT_TEST_FIX.format(phase=state.phase) + _BYPASS_HINT)
    sys.exit(0)


def _is_gate_reset_command(command: str) -> bool:
    """True if the command is SOLELY the TDD gate's own ``reset`` CLI.

    This is the autonomous recovery hatch: it must be allowed even in
    RED_VIOLATION, otherwise a (possibly false) violation deadlocks the run —
    the reset needed to escape is itself blocked. Hard requirements:
      - a single clause only (no ``&&``/``;``/``|``),
      - no command substitution (``reset $(…)``) or backticks,
      - shlex-parseable argv whose LAST token is exactly ``reset`` and that ends
        in ``tdd_cycle_gate.py ... reset`` with NO mutation-bearing traffic
        (``make …``/``mutmut …``) anywhere in the command,
      - the interpreter/runner prefix is limited to python/uv/venv/sudo/env.
    This keeps the hatch usable (`uv run python hooks/…reset`,
    `./.venv/bin/python …`, `env X=1 python3 …`) while closing the R6 suffix-rider
    (``make mutation-check …/tdd_cycle_gate.py reset``) escape.
    """
    if re.search(r"\$\(|`", command):
        return False
    clauses = _command_clauses(command)
    if len(clauses) != 1:
        return False
    try:
        argv = shlex.split(clauses[0])
    except ValueError:
        return False
    if not argv or argv[-1] != "reset":
        return False
    joined = " ".join(argv)
    # Reject any mutation-bearing traffic in the command.
    if re.search(r"\b(?:mutmut|muta(?:\{t,\})?tion(?:-check)?)\b", joined, re.IGNORECASE):
        return False
    # The gate file must appear as an argument (not necessarily argv[0]).
    gate_idx = next(
        (i for i, a in enumerate(argv) if a.endswith("tdd_cycle_gate.py")),
        None,
    )
    if gate_idx is None:
        return False
    # Nothing may follow the gate besides `reset`.
    return gate_idx == len(argv) - 2


def _handle_loop_mode_pre_tool_use(
    tool_name: str,
    tool_input: dict,
    state: State,
    hook_session_id: str = "",
) -> None:
    """Loop-mode PreToolUse handler: observes skills, blocks bash writes, enforces cycle."""
    # Recovery hatch: the gate's own reset CLI is always allowed (even in
    # RED_VIOLATION) so a false or genuine violation can be recovered
    # autonomously instead of deadlocking the run.
    if tool_name == "Bash" and _is_gate_reset_command(str(tool_input.get("command", ""))):
        sys.exit(0)

    if state.phase == RED_VIOLATION:
        _deny(
            "🚫 RED_VIOLATION: un test pasó durante la fase RED cuando debía fallar "
            "(pytest PASS en READY con tdd-red pendiente). El ciclo está bloqueado. "
            "STOP: reporta la violación al orquestador — no inventes un RED. "
            "Recuperación: python3 hooks/tdd_cycle_gate.py reset"
        )

    if tool_name == "Skill":
        skill_name = (tool_input.get("skill_name", "") or "").strip().lower()
        if not skill_name:
            sys.exit(0)  # no skill name → inert

        # Unknown skill: allow but don't advance state
        if skill_name not in (
            "bmad-tdd-coordinator",
            "tdd-red",
            "tdd-green",
            "tdd-clean",
            "tdd-refactor",
        ):
            sys.exit(0)

        # Validate ordering (includes phase_agent_seen check for Phase 2 routing)
        ok, reason = _validate_skill_order(state, skill_name)
        if not ok:
            _deny(reason)

        # Process the skill
        _process_loop_skill(skill_name, state, hook_session_id)
        state.save()
        sys.exit(0)

    if tool_name == "Task":
        # Phase 2 model-routing gate: Task agents are the ONLY gateway into Skills.
        # Each Task records its agent in phase_agent_seen for the current phase.
        # Wrong-phase Tasks are denied. Unknown non-TDD Tasks pass through inertly.
        subagent_type = (tool_input.get("subagent_type", "") or "").strip().lower()
        prompt_text = str(tool_input.get("prompt", "") or "")
        if not subagent_type:
            sys.exit(0)  # no subagent_type → inert

        if subagent_type not in _TASK_AGENT_PHASE:
            # Unknown non-TDD Task: audit only, no state mutation
            _audit(f"UNKNOWN_TASK: subagent_type={subagent_type!r}")
            sys.exit(0)

        required_phase = _TASK_AGENT_PHASE[subagent_type]

        # verification_preexisting path: tdd-green-ornith in READY with exact
        # standalone marker + nonempty evidence text → accept, transition READY→CODING.
        # All other READY green Tasks remain denied. Do not trust partial/case-mutated markers.
        if (
            subagent_type == "tdd-green-ornith"
            and state.phase == READY
            and "bmad-tdd-coordinator" in state.skill_seen
            and _verify_preexisting_marker(prompt_text)
        ):
            if state.pending_task and state.pending_task != subagent_type:
                _deny(
                    f"🚫 Ya existe un Task TDD pendiente: {state.pending_task}. "
                    "Espera su evidencia de finalización antes de iniciar otra fase."
                )
            # Record green task, transition READY→CODING, save+audit
            if "tdd-green-ornith" not in state.phase_agent_seen:
                state.phase_agent_seen.append("tdd-green-ornith")
            state.pending_task = subagent_type
            state.pending_task_session_id = hook_session_id
            state.phase = CODING
            state.save()
            _audit("TDD_GREEN_VERIFIED: phase READY→CODING (marker valid, prompt evidence present)")
            sys.exit(0)

        if state.phase != required_phase:
            _deny(
                f"🚫 Tarea '{subagent_type}' fuera de fase. "
                f"Se requiere fase {required_phase} pero la fase actual es {state.phase}. "
                "Cada Task agent solo es válido en su fase correspondiente."
            )

        if state.pending_task and state.pending_task != subagent_type:
            _deny(
                f"🚫 Ya existe un Task TDD pendiente: {state.pending_task}. "
                "Espera su evidencia de finalización antes de iniciar otra fase."
            )

        # Record the Task agent in phase_agent_seen (only Task handler mutates this)
        if subagent_type not in state.phase_agent_seen:
            state.phase_agent_seen.append(subagent_type)
        state.pending_task = subagent_type
        state.pending_task_session_id = hook_session_id
        if subagent_type == "tdd-red-ornith":
            state.red_pending = True
        state.save()
        sys.exit(0)

    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        # Full mutation is coordinator-owned at RELEASE: deny it while a @s cycle
        # is open (or RED in flight) in loop mode. Named-mutant inspection passes.
        if _is_full_mutation_command(command) and not _full_mutation_allowed(state):
            _deny(_FULL_MUTATION_DENIED)
        if _bash_writes_detected(command):
            _deny(
                "🚫 Escritura directa Bash bloqueada en loop mode. "
                "Usa las skills TDD (edit/write/multi_edit) para modificar archivos. "
                f"Comando detectado: {command[:120]}"
            )
        sys.exit(0)

    # For Edit/Write/MultiEdit: enforce checks in loop mode
    if tool_name in ("Edit", "Write", "MultiEdit"):
        paths = _target_paths(tool_input)

        # Worktree containment: every path must resolve inside cwd
        contained, reason = _check_paths_contained(paths)
        if not contained:
            _deny(reason)

        kind = _classify(paths)

        # Protected state files: always deny in loop mode
        if kind == "protected":
            _deny(
                "🔒 Archivo de estado protegido. No se permiten ediciones estructuradas "
                f"a {_PROTECTED_STATE_PATHS[0]}* ni {_PROTECTED_STATE_PATHS[1]} en loop mode. "
                "El estado del ciclo es administrado exclusivamente por el gate."
            )

        # ── Bitácora token guard (loop mode only) ────────────────────────────────
        # Prevents out-of-phase bitácora tokens from driving false transitions.
        # Full-cycle edits (ROJO+VERDE+REFACTOR together) are allowed.
        _bitacora_guard(state, tool_input)

        if kind == "other":
            sys.exit(0)

        if kind == "test":
            # New test while the current @s is still open (GREEN_SEEN/CLEAN):
            # close the cycle first — log VERDE + CLEAN + REFACTOR.
            if state.phase in (GREEN_SEEN, CLEAN):
                _deny(_NEXT_TEST_FIX.format(phase=state.phase))

            # Test edits require tdd-red seen (TDD Law 1) — UNLESS this is the
            # verification_preexisting path (tdd-green-ornith invoked with the
            # exact `classification=verification_preexisting` marker, no RED
            # ever): completing/fixing the Given of an EXISTING test is not
            # writing a new failing test (DW-78 / observation #24). The marker
            # is enforced in the Task handler (READY→CODING), so a dev cannot
            # reach here through tdd-green-ornith without a valid marker.
            is_verification_path = (
                "tdd-green-ornith" in state.phase_agent_seen
                and "tdd-red-ornith" not in state.phase_agent_seen
                and "tdd-green" in state.skill_seen
            )
            if "tdd-red" not in state.skill_seen and not is_verification_path:
                _deny(
                    "🔴 Puerta TDD (loop mode). Escribe un test que falle y obsérvalo en ROJO "
                    "antes de tocar producción (Ley 1 del TDD). "
                    "Estado del ciclo: READY. Necesitas invocar tdd-red primero."
                )
        elif kind == "prod":
            # Permission model: each skill unlocks prod edits for its phase.
            #   - RED_SEEN: always deny
            #   - GREEN_SEEN: allow if tdd-green seen (writing-to-green)
            #   - CODING: allow if tdd-green seen
            #   - CLEAN: allow if tdd-clean seen (structural refactor)
            #   - REFACTOR: allow if tdd-refactor seen
            #   - READY (post-cycle): allow if tdd-green or tdd-refactor seen
            if state.phase == RED_SEEN:
                _deny(_ROJO_FIX)
            elif state.phase == GREEN_SEEN:
                if "tdd-green" in state.skill_seen:
                    sys.exit(0)
                _deny(_VERDE_FIX)
            elif state.phase == CODING:
                if "tdd-green" in state.skill_seen:
                    sys.exit(0)
                _deny(
                    "🟢 Puerta TDD (loop mode): el test ya pasa pero "
                    "VERDE no está registrado. "
                    "Añade la línea 'VERDE:' a la bitácora del story "
                    "antes de seguir tocando producción."
                )
            elif state.phase == CLEAN:
                if "tdd-clean" in state.skill_seen:
                    sys.exit(0)
                _deny(
                    "🧹 Puerta TDD (loop mode): "
                    "necesitas invocar tdd-clean antes de refactorizar estructura."
                )
            elif state.phase == REFACTOR:
                if "tdd-refactor" in state.skill_seen:
                    sys.exit(0)
                _deny(
                    "🧪 Puerta TDD (loop mode): "
                    "necesitas invocar tdd-refactor antes de refactorizar."
                )
            else:  # READY
                if "tdd-green" in state.skill_seen or "tdd-refactor" in state.skill_seen:
                    sys.exit(0)  # post-cycle: unlock persists
                _deny(_RED_FIX.format(phase=state.phase))
        sys.exit(0)

    sys.exit(0)


def _process_loop_skill(skill_name: str, state: State, hook_session_id: str = "") -> None:
    """Process a recognized skill invocation.

    Skills register in skill_seen. Phase transitions follow the canonical flow:
      - coordinator in READY: registers, stays READY
      - tdd-red in READY: registers, stays READY (pytest FAIL drives READY→RED_SEEN)
      - tdd-green in CODING: registers, stays CODING (pytest PASS drives CODING→GREEN_SEEN)
      - tdd-clean in CLEAN: registers, stays CLEAN (CLEAN: bitácora drives CLEAN→REFACTOR)
      - tdd-refactor in REFACTOR: registers ONLY — does NOT close cycle early.
        Only the REFACTOR: bitácora entry closes the cycle.
    """
    now = datetime.now(UTC).isoformat()

    # Keep pending_task until the matching Task completes when the Skill runs in
    # a different OpenCode child session. Legacy hook callers without session
    # ids retain the original same-session behavior.
    task_for_skill = {
        "tdd-red": "tdd-red-ornith",
        "tdd-green": "tdd-green-ornith",
        "tdd-clean": "tdd-clean-ornith",
        "tdd-refactor": "tdd-refactor-ornith",
    }.get(skill_name)
    if task_for_skill == state.pending_task and not (
        hook_session_id
        and state.pending_task_session_id
        and hook_session_id != state.pending_task_session_id
    ):
        state.pending_task = ""
        state.pending_task_session_id = ""

    if skill_name == "bmad-tdd-coordinator":
        if "bmad-tdd-coordinator" not in state.skill_seen:
            state.skill_seen.append("bmad-tdd-coordinator")
            state.last_skill_at = now
            state.cycle += 1
        # Phase: stays READY

    elif skill_name == "tdd-red":
        if "tdd-red" not in state.skill_seen:
            state.skill_seen.append("tdd-red")
            state.last_skill_at = now
        # Phase: stays RED_SEEN (pytest FAIL drives READY→RED_SEEN)

    elif skill_name == "tdd-green":
        if "tdd-green" not in state.skill_seen:
            state.skill_seen.append("tdd-green")
            state.last_skill_at = now
        # Phase: stays CODING (pytest PASS drives CODING→GREEN_SEEN)

    elif skill_name == "tdd-clean":
        if "tdd-clean" not in state.skill_seen:
            state.skill_seen.append("tdd-clean")
            state.last_skill_at = now
        # Phase: stays CLEAN (CLEAN: bitácora drives CLEAN→REFACTOR)

    elif skill_name == "tdd-refactor" and "tdd-refactor" not in state.skill_seen:
        state.skill_seen.append("tdd-refactor")
        state.last_skill_at = now
        # Phase: MUST STAY REFACTOR. Cycle is closed ONLY by REFACTOR: bitácora entry.


# ── PostToolUse: advance the machine ──────────────────────────────────────────

_FAIL_RE = re.compile(r"\b(\d+ failed|\d+ error|errors?\b|FAILED|ERROR)\b")
_PASS_RE = re.compile(r"\b\d+ passed\b")
_VERIFY_CMD = _workflow_string("test_cmd", "BMAD_TDD_VERIFY_CMD", "")
_SHELL_CONTROL_RE = re.compile(r"[;&|<>`$()]|\r|\n")
_PYTHON_LAUNCHER_RE = re.compile(r"^(?:python|pypy)(?:\d+(?:\.\d+)*)?$")


def _command_tokens(command: str) -> list[str] | None:
    """Split a command only when it contains no shell composition syntax."""
    if not command or _SHELL_CONTROL_RE.search(command):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    return tokens or None


def _starts_with_command(command: str, configured: str) -> bool:
    """Match the configured verifier as one exact argv, never as a prefix."""
    if not configured:
        return False
    actual = _command_tokens(command)
    expected = _command_tokens(configured)
    if actual is None or expected is None:
        return False
    return actual == expected


def _is_standalone_pytest_command(command: str) -> bool:
    """Recognize legacy pytest invocations without matching arbitrary output text."""
    tokens = _command_tokens(command)
    if tokens is None:
        return False

    executable_index: int | None = None
    first = Path(tokens[0]).name
    if first in {"pytest", "py.test"}:
        executable_index = 0
    elif len(tokens) >= 3 and (
        (
            _PYTHON_LAUNCHER_RE.fullmatch(Path(tokens[0]).name) is not None
            and tokens[1:3] == ["-m", "pytest"]
        )
        or (Path(tokens[0]).name == "uv" and tokens[1:3] == ["run", "pytest"])
    ):
        executable_index = 2

    if executable_index is None:
        return False
    return not any(
        option in {"-h", "--help", "--version"} for option in tokens[executable_index + 1 :]
    )


def _is_verification_command(command: str) -> bool:
    if _VERIFY_CMD:
        return _starts_with_command(command, _VERIFY_CMD)
    return _is_standalone_pytest_command(command)


def _response_exit(tool_response: object) -> tuple[bool, int | None]:
    """Return whether OpenCode supplied shell exit metadata and its value."""
    if not isinstance(tool_response, Mapping):
        return False, None
    metadata = tool_response.get("metadata")
    if not isinstance(metadata, Mapping) or "exit" not in metadata:
        return False, None
    value = metadata.get("exit")
    if isinstance(value, int) and not isinstance(value, bool):
        return True, value
    return True, None


def _bash_outcome(command: str, tool_response: object) -> str | None:
    """Return RED/GREEN for a recognized test command, preferring its exit code."""
    if not _is_verification_command(command) or "mutmut" in command:
        return None
    has_exit, exit_code = _response_exit(tool_response)
    if has_exit:
        if exit_code is None:
            return None
        return "green" if exit_code == 0 else "red"
    output = _stringify(tool_response)
    if _FAIL_RE.search(output):
        return "red"
    if _PASS_RE.search(output):
        return "green"
    return None


def handle_post_tool_use(
    tool_name: str,
    tool_input: dict,
    tool_response: object,
    state: State,
    hook_session_id: str = "",
) -> None:
    changed = False
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        outcome = _bash_outcome(command, tool_response)
        if outcome == "red" and state.phase == READY:
            state.phase = RED_SEEN
            state.red_pending = False
            state.red_test_written = False
            changed = True
        elif outcome == "green" and state.phase == CODING:
            state.phase = GREEN_SEEN
            state.red_pending = False
            state.red_test_written = False
            changed = True
        elif (
            outcome == "green"
            and state.phase == READY
            and _is_loop_mode()
            and state.red_pending
            and state.red_test_written
        ):
            # Protocol violation: a development RED passed instead of failing.
            state.phase = RED_VIOLATION
            changed = True
            _audit("RED_VIOLATION: test command passed during RED in READY (RED test was written)")
    elif tool_name in ("Edit", "Write", "MultiEdit"):
        paths = _target_paths(tool_input)
        if _is_loop_mode():
            # Worktree containment: every path must resolve inside cwd
            contained, reason = _check_paths_contained(paths)
            if not contained:
                _deny(reason)
            changed = _handle_loop_post_tool_use(paths, tool_input, state)
        else:
            changed = _handle_legacy_post_tool_use(paths, tool_input, state)
    elif tool_name == "Task" and _is_loop_mode():
        changed = _handle_task_post_tool_use(tool_input, tool_response, state, hook_session_id)
    if changed:
        state.save()
    sys.exit(0)


def _handle_loop_post_tool_use(paths: list[str], tool_input: dict, state: State) -> bool:
    """Loop-mode PostToolUse: story bitácora transitions require matching skill."""
    changed = False
    # Track RED test authorship: a test-file edit while a RED is pending marks the
    # RED test as written. RED_VIOLATION then only fires on a passing pytest once a
    # real RED test exists — a pre-test baseline run can no longer false-trigger it.
    if state.red_pending and not state.red_test_written and _classify(paths) == "test":
        state.red_test_written = True
        changed = True
    if any(_is_story_md(p) for p in paths):
        body = _edit_body(tool_input)
        tokens = _parse_bitacora_tokens(body)
        if "ROJO" in tokens and state.phase == RED_SEEN and "tdd-red" in state.skill_seen:
            state.phase = CODING
            changed = True
        elif "VERDE" in tokens and state.phase == GREEN_SEEN and "tdd-green" in state.skill_seen:
            state.phase = CLEAN
            changed = True
        elif "CLEAN" in tokens and state.phase == CLEAN and "tdd-clean" in state.skill_seen:
            state.phase = REFACTOR
            changed = True
        elif (
            "REFACTOR" in tokens and state.phase == REFACTOR and "tdd-refactor" in state.skill_seen
        ):
            # Cycle closed: phase resets to READY, cycle counter increments.
            # phase_agent_seen and skill_seen persist across cycles so that
            # cross-cycle Skill validation (e.g. tdd-red requiring coordinator)
            # continues to work without coordinator re-invocation.
            state.phase = READY
            state.cycle += 1
            state.red_pending = False
            state.red_test_written = False
            changed = True
            _audit("WARNING: REFACTOR→READY transition (out-of-order bitácora check)")
    return changed


_TASK_RESULT_PREFIX = "BMAD_TDD_PHASE_RESULT:"


def _tool_response_has_verde(resp: object) -> bool:
    """Check if a Task tool_response contains a VERDE bitacora token."""
    text = _stringify(resp)
    if not text:
        return False
    try:
        tokens = _parse_bitacora_tokens(text)
        if "VERDE" in tokens:
            return True
    except Exception:
        pass
    for line in text.splitlines():
        marker = line.strip()
        if not marker.startswith(_TASK_RESULT_PREFIX):
            continue
        try:
            evidence = json.loads(marker[len(_TASK_RESULT_PREFIX) :].strip())
        except (TypeError, ValueError):
            continue
        if isinstance(evidence, Mapping) and evidence.get("bitacora") == "VERDE":
            return True
    return "VERDE:" in text or "**VERDE" in text


def _task_phase_evidence(tool_response: object, subagent_type: str) -> bool:
    """Validate the coordinator-visible completion marker for a phase Task."""
    if isinstance(tool_response, Mapping):
        metadata = tool_response.get("metadata")
        if isinstance(metadata, Mapping) and "exit" in metadata:
            task_exit = metadata.get("exit")
            if not isinstance(task_exit, int) or isinstance(task_exit, bool) or task_exit != 0:
                return False
        output = tool_response.get("output")
    elif isinstance(tool_response, str):
        output = tool_response
    else:
        return False

    if not isinstance(output, str):
        return False
    marker_lines = [
        stripped[len(_TASK_RESULT_PREFIX) :].strip()
        for line in output.splitlines()
        if (stripped := line.strip()).startswith(_TASK_RESULT_PREFIX)
    ]
    if len(marker_lines) != 1:
        return False
    try:
        evidence = json.loads(marker_lines[0])
    except (TypeError, ValueError):
        return False
    if not isinstance(evidence, Mapping):
        return False

    expected_phase, expected_bitacora = _TASK_RESULT_EXPECTATIONS[subagent_type]
    test_exit = evidence.get("test_exit")
    return (
        evidence.get("agent") == subagent_type
        and evidence.get("phase") == expected_phase
        and evidence.get("status") == "PASS"
        and evidence.get("bitacora") == expected_bitacora
        and isinstance(test_exit, int)
        and not isinstance(test_exit, bool)
        and ((test_exit != 0) if subagent_type == "tdd-red-ornith" else test_exit == 0)
    )


def _handle_task_post_tool_use(
    tool_input: dict,
    tool_response: object,
    state: State,
    hook_session_id: str = "",
) -> bool:
    """Bridge isolated phase Tasks only after validated completion evidence.

    The coordinator owns this bridge because child sessions may not expose the
    same gate state consistently. The bridge is deliberately fail-closed: a
    successful Task call without the exact phase result marker is not evidence
    that the phase completed.
    """
    subagent_type = (tool_input.get("subagent_type", "") or "").strip().lower()
    if subagent_type not in _TASK_AGENT_PHASE:
        return False  # non-TDD task → no transition

    if state.pending_task != subagent_type:
        _deny(
            f"🚫 Finalización de Task sin solicitud pendiente para {subagent_type}. "
            "El gate no acepta un PostToolUse aislado como evidencia de fase."
        )
    if (
        state.pending_task_session_id
        and hook_session_id
        and state.pending_task_session_id != hook_session_id
    ):
        _deny(
            f"🚫 Finalización de Task desde una sesión no coincidente para {subagent_type}. "
            "La evidencia debe volver a la sesión que abrió el Task."
        )
    if not _task_phase_evidence(tool_response, subagent_type):
        _deny(
            f"🚫 Evidencia de fase inválida para {subagent_type}. "
            "La respuesta debe incluir una línea única "
            "'BMAD_TDD_PHASE_RESULT: <JSON>' con agente, fase, status PASS, "
            "test_exit y bitacora coherentes."
        )

    state.pending_task = ""
    state.pending_task_session_id = ""

    if subagent_type == "tdd-red-ornith":
        # RED subagent: READY → RED_SEEN → CODING.
        if state.phase not in {READY, RED_SEEN, CODING}:
            _deny(f"🚫 Finalización de Task '{subagent_type}' fuera de fase: {state.phase}.")
        if state.phase == READY:
            state.phase = RED_SEEN
        if state.phase == RED_SEEN:
            state.phase = CODING
        state.red_pending = False
        state.red_test_written = False
        if "tdd-red" not in state.skill_seen:
            state.skill_seen.append("tdd-red")
        _audit(f"TASK_POST: tdd-red-ornith completed → phase={state.phase}")
        return True

    if subagent_type == "tdd-green-ornith":
        # GREEN subagent: CODING → GREEN_SEEN → CLEAN; VERDE is required.
        if state.phase not in {CODING, GREEN_SEEN, CLEAN}:
            _deny(f"🚫 Finalización de Task '{subagent_type}' fuera de fase: {state.phase}.")
        if state.phase == CODING:
            state.phase = GREEN_SEEN
        if state.phase == GREEN_SEEN and _tool_response_has_verde(tool_response):
            state.phase = CLEAN
        if "tdd-green" not in state.skill_seen:
            state.skill_seen.append("tdd-green")
        if _tool_response_has_verde(tool_response):
            _audit(f"TASK_POST: tdd-green-ornith completed with VERDE → phase={state.phase}")
        else:
            _audit(
                f"TASK_POST: tdd-green-ornith completed without VERDE → phase stays {state.phase}"
            )
        return True

    if subagent_type == "tdd-clean-ornith":
        # CLEAN subagent: CLEAN → REFACTOR.
        if state.phase not in {CLEAN, REFACTOR}:
            _deny(f"🚫 Finalización de Task '{subagent_type}' fuera de fase: {state.phase}.")
        if state.phase == CLEAN:
            state.phase = REFACTOR
        if "tdd-clean" not in state.skill_seen:
            state.skill_seen.append("tdd-clean")
        _audit(f"TASK_POST: tdd-clean-ornith completed → phase={state.phase}")
        return True

    # REFACTOR subagent: REFACTOR → READY (cycle closed).
    if state.phase not in {REFACTOR, READY}:
        _deny(f"🚫 Finalización de Task '{subagent_type}' fuera de fase: {state.phase}.")
    if state.phase == REFACTOR:
        state.phase = READY
        state.cycle += 1
        state.red_pending = False
        state.red_test_written = False
    if "tdd-refactor" not in state.skill_seen:
        state.skill_seen.append("tdd-refactor")
    _audit(f"TASK_POST: tdd-refactor-ornith completed → phase={state.phase}, cycle={state.cycle}")
    return True


def _handle_legacy_post_tool_use(paths: list[str], tool_input: dict, state: State) -> bool:
    """Legacy PostToolUse: story bitácora transitions (no skill requirement).

    Audit warning emitted when bitácora token appears outside expected phase,
    but transitions are NOT blocked (preserves legacy semantics — binding decision).
    """
    changed = False
    if any(_is_story_md(p) for p in paths):
        body = _edit_body(tool_input)
        if "ROJO:" in body and state.phase == RED_SEEN:
            # Expected: ROJO in RED_SEEN is fine
            state.phase = CODING
            changed = True
        elif "ROJO:" in body and state.phase != RED_SEEN:
            _audit(
                f"WARNING: legacy bitácora 'ROJO:' out of phase "
                f"(phase={state.phase}, expected RED_SEEN). "
                f"Transition skipped to preserve state integrity."
            )
        elif "VERDE:" in body and state.phase == GREEN_SEEN:
            state.phase = CLEAN
            changed = True
        elif "VERDE:" in body and state.phase != GREEN_SEEN:
            _audit(
                f"WARNING: legacy bitácora 'VERDE:' out of phase "
                f"(phase={state.phase}, expected GREEN_SEEN). "
                f"Transition skipped to preserve state integrity."
            )
        elif "CLEAN:" in body and state.phase == CLEAN:
            state.phase = REFACTOR
            changed = True
        elif "CLEAN:" in body and state.phase != CLEAN:
            _audit(
                f"WARNING: legacy bitácora 'CLEAN:' out of phase "
                f"(phase={state.phase}, expected CLEAN). "
                f"Transition skipped to preserve state integrity."
            )
        elif "REFACTOR:" in body and state.phase == REFACTOR:
            qg_pass = _check_quality_gate_pass()
            if qg_pass is None or qg_pass is True:
                state.phase = READY
                changed = True
            else:
                _audit(
                    "BLOCKED: REFACTOR → READY denied — quality gate "
                    f"checkpoint = FAIL (file: {_QUALITY_GATE_CHECKPOINT})"
                )
        elif "REFACTOR:" in body and state.phase != REFACTOR:
            _audit(
                f"WARNING: legacy bitácora 'REFACTOR:' out of phase "
                f"(phase={state.phase}, expected REFACTOR). "
                f"Transition skipped to preserve state integrity."
            )
    return changed


def _is_story_md(path: str) -> bool:
    p = path.replace("\\", "/")
    return "_bmad-output/implementation-artifacts/" in p and p.endswith(".md")


def _edit_body(tool_input: dict) -> str:
    """All text an Edit/Write/MultiEdit is adding (where the bitácora tokens would appear)."""
    parts: list[str] = []
    for key in ("new_string", "content"):
        val = tool_input.get(key)
        if isinstance(val, str):
            parts.append(val)
    for edit in tool_input.get("edits", []) or []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            parts.append(edit["new_string"])
    return "\n".join(parts)


def _stringify(resp: object) -> str:
    """Convert a tool response to a string for bash_outcome detection.

    For Mappings, ONLY concatenate known output fields (stdout, stderr, output).
    Metadata fields like 'duration', 'exitCode', etc. must NOT pollute detection.
    For strings, return as-is. Fallback: JSON serialize or str().
    """
    if isinstance(resp, str):
        return resp
    if isinstance(resp, Mapping):
        # Only known output fields — kills metadata false positives
        parts = []
        for key in ("stdout", "stderr", "output"):
            val = resp.get(key)
            if isinstance(val, str) and val:
                parts.append(val)
        if parts:
            return "\n".join(parts)
    try:
        return json.dumps(resp, default=str)
    except (TypeError, ValueError):
        return str(resp)


# ── Bash write detector (loop mode) — practical closure ──────────────────────

# Protected literal paths that, when combined with write indicators, trigger denial.
_PROTECTED_LITERALS = [
    _PROD_PREFIX,
    _TEST_PREFIX,
    "_bmad-output/implementation-artifacts/",
    ".bmad-harness/tdd-state",
    ".bmad-harness/tdd-audit",
]

# Write-indicator patterns (each is a regex fragment matched against the command).
# NOTE: r">(?!&)\s*" matches redirect > but NOT stderr redirects like 2>&1 or >&2.
_WRITE_INDICATORS = [
    r">(?!&)\s*",  # redirect > (but NOT 2>&1 or >&2)
    r">>(?!&)\s*",  # append >> (but NOT >>&2)
    r"\btee\b",  # tee
    r"\bcp\b\s+",  # cp
    r"\bmv\b\s+",  # mv
    r"\binstall\b\s+",  # install
    r"\bdd\b.*\bof=",  # dd with of=
    r"\bsed\b\s+-i\b",  # sed -i
    r"\bperl\b\s+-e\b",  # perl -e
    r"\bruby\b\s+-e\b",  # ruby -e
    r"\bbase64\b\s+-d\b",  # base64 -d
    r"\btruncate\b",  # truncate
    r"\btouch\b",  # touch
    r"\brm\b\s+",  # rm
    r"\bpython3?\s+-c\b",  # python -c / python3 -c
    r"\buv\s+run\s+python3?\s+-c\b",  # uv run python -c / uv run python3 -c
]


def _bash_writes_detected(command: str) -> bool:
    """Detect if a bash command performs a direct write to protected paths.

    Catches: git apply, standalone patch, heredocs, sh -c, dd, perl, ruby,
    base64, install, sed -i, variable assignment + redirect, truncate, touch,
    rm, and any protected literal path combined with a write indicator.

    Limitation: arbitrary external scripts cannot be statically proven to write.
    This is best-effort detection, not a sandbox. Documented for audit friction.
    """
    cmd_lower = command.lower()

    # Standalone dangerous commands (regardless of paths)
    if re.search(r"\bgit\s+apply\b", cmd_lower):
        return True
    if re.search(r"(?<!\w)patch\b(?!\s+-p)", cmd_lower):
        # Match standalone 'patch' but not 'patch -p1' ... actually patch -p1 IS dangerous
        # Let's match both: standalone patch or patch with any args
        pass
    # Actually: deny ANY 'patch' command
    if re.search(r"(?<!\w)patch\s", cmd_lower) or cmd_lower.strip() == "patch":
        return True
    # Also catch 'patch -p1 < ...'
    if re.search(r"(?<!\w)patch\b", cmd_lower):
        return True

    # Heredoc detection: cat <<EOF > target or similar
    if "<<EOF" in command or "<<-" in command or "<<'" in command or '<<"' in command:
        # Check if heredoc redirects to a protected path
        # NOTE: use regex to match > but NOT 2>&1 or >&2
        has_redirect = re.search(r">(?!&)", command) is not None
        for lit in _PROTECTED_LITERALS:
            if lit in command and (has_redirect or "tee" in command):
                return True

    # sh -c with redirect to protected path
    if "sh -c" in cmd_lower:
        for lit in _PROTECTED_LITERALS:
            if lit in command:
                return True

    # Check variable assignment with redirect: VAR=value > path
    if re.search(r"[A-Za-z_][A-Za-z0-9_]*=\S*\s*>", command):
        for lit in _PROTECTED_LITERALS:
            if lit in command:
                return True

    # Chained commands: check each segment for write patterns
    segments = re.split(r";\s*|&&\s*|\|\|\s*", command)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        # Check protected literal + write indicator
        has_protected = any(lit in seg for lit in _PROTECTED_LITERALS)
        if has_protected:
            for wi in _WRITE_INDICATORS:
                if re.search(wi, seg, re.IGNORECASE):
                    return True

    # Direct check: any protected literal + any write indicator in full command
    has_protected = any(lit in command for lit in _PROTECTED_LITERALS)
    if has_protected:
        for wi in _WRITE_INDICATORS:
            if re.search(wi, command, re.IGNORECASE):
                return True

    return False


# ── Worktree containment ──────────────────────────────────────────────────────


def _is_path_contained(path_str: str, worktree: Path) -> bool:
    """Return True if ``path_str`` resolves INSIDE ``worktree``.

    Handles: relative paths (resolved against cwd), absolute paths,
    ``..`` segments, and symlinks (both sides are resolved).
    A path that resolves to exactly ``worktree`` itself is considered contained.
    """
    try:
        target = Path(path_str).resolve()
        return target == worktree or target.is_relative_to(worktree)
    except (OSError, ValueError):
        return False


def _check_paths_contained(paths: list[str]) -> tuple[bool, str]:
    """Validate that every path stays inside the current worktree.

    Returns ``(True, "")`` when all paths are contained, or
    ``(False, reason)`` on the first escape found.
    """
    worktree = Path.cwd().resolve()
    for p in paths:
        if not _is_path_contained(p, worktree):
            return False, (
                f"🚫 Containment violation: path {p!r} escapes the worktree "
                f"(cwd={worktree}). Structured writes must stay within the "
                f"current working directory."
            )
    return True, ""


# ── CLI control surface ───────────────────────────────────────────────────────


def _cli(argv: list[str]) -> int:
    # In loop mode, bypass is disabled regardless of state
    if _is_loop_mode() and argv and argv[0] == "bypass":
        print("bypass deshabilitado en BMAD_LOOP_MODE=1", file=sys.stderr)
        return 3

    state_file = _state_file_for(_current_story_key())
    state = State.load(state_file)
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        active = _story_in_progress() if not _is_loop_mode() else True
        print(
            f"phase={state.phase} mode={state.mode} active={active} "
            f"bypass_reason={state.bypass_reason!r} updated={state.updated}"
        )
        return 0
    if cmd == "reset":
        State(phase=READY, mode="tdd", _state_file=state_file).save()
        _audit("CLI reset → READY/tdd")
        print("TDD gate reset: phase=READY mode=tdd")
        return 0
    if cmd == "bypass":
        reason = argv[1] if len(argv) > 1 else "(no reason given)"
        state.mode = "bypass"
        state.bypass_reason = reason
        state.save()
        _audit(f"BYPASS ON — {reason}")
        print(f"TDD gate BYPASSED (audited): {reason}")
        return 0
    if cmd == "resume":
        state.mode = "tdd"
        state.bypass_reason = ""
        state.save()
        _audit("BYPASS OFF — resumed tdd enforcement")
        print(f"TDD gate resumed: phase={state.phase} mode=tdd")
        return 0
    print(f"unknown command: {cmd}; use status|reset|bypass <reason>|resume", file=sys.stderr)
    return 1


# ── Entrypoint: hook (stdin JSON) vs CLI (argv) ───────────────────────────────


def main() -> int:
    # CLI mode when invoked with args and not fed a hook JSON payload.
    if len(sys.argv) > 1:
        return _cli(sys.argv[1:])

    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except ValueError:
        return 0  # not a hook payload → do nothing

    # Bind mode-derived values before any risky work so the error handler can
    # always branch on them (a non-dict payload must not crash in loop mode).
    loop_active = _is_loop_mode()

    try:
        if not isinstance(payload, dict):
            if loop_active:
                _audit("ERROR (fail-closed deny): hook payload is not a JSON object")
                sys.stderr.write("🚫 TDD gate error (fail-closed): payload is not a JSON object\n")
                sys.exit(2)
            return 0  # fail-open outside loop
        event = payload.get("hook_event_name", "")
        tool_name = payload.get("tool_name", "")
        tool_input = payload.get("tool_input", {}) or {}
        story_key = _current_story_key()

        if loop_active:
            _validate_gate_scope()

        # Validate story key in loop mode (strict regex, no sanitize collision)
        if loop_active and story_key and not _STORY_KEY_RE.match(story_key):
            _deny(
                f"🚫 Clave de story inválida: {story_key!r}. "
                "Debe coincidir con [A-Za-z0-9][A-Za-z0-9._-]* (sin sanitización por colisiones)."
            )

        state_file = _state_file_for(story_key)

        # ── Security: symlink denial BEFORE any lock/write ──────────────────
        # State file path must not be a symlink (prevents reading/writing external files).
        if loop_active and state_file.exists() and state_file.is_symlink():
            _deny(
                f"🚫 Symlink denegado para archivo de estado: {state_file}. "
                "El gate niega archivos enlazados para proteger la integridad del estado."
            )

        # Parent directory must not be a symlink (prevents writing to external dirs).
        state_parent = state_file.parent
        if loop_active and state_parent.exists() and state_parent.is_symlink():
            _deny(
                f"🚫 Symlink denegado para directorio padre del estado: {state_parent}. "
                "El gate niega directorios enlazados para proteger la integridad del estado."
            )

        # Lock file itself must not be a symlink.
        lock_path = _lock_file_for(state_file)
        if loop_active and lock_path.exists() and lock_path.is_symlink():
            _deny(
                f"🚫 Symlink denegado para archivo de bloqueo: {lock_path}. "
                "El gate niega enlaces simbólicos para proteger la integridad del estado."
            )

        # ── Transactional lock: acquire BEFORE load, hold through all saves ─
        with _file_lock(state_file):
            # Load state — migrate legacy state if story key changed
            loaded = State.load(state_file)

            if loop_active:
                if loaded.story_key and loaded.story_key != story_key:
                    # Different story: start fresh
                    state = State(
                        phase=READY,
                        mode="tdd",
                        story_key=story_key or "",
                        _state_file=state_file,
                    )
                    _audit(f"MIGRATE state for story {story_key}")
                elif not loaded.story_key:
                    # Legacy state without story_key in loop mode: reset to READY
                    state = State(
                        phase=READY,
                        mode="tdd",
                        story_key=story_key or "",
                        _state_file=state_file,
                    )
                    _audit("MIGRATE legacy state → fresh state for loop mode")
                else:
                    state = loaded

                # SECURITY: Loop mode cannot persist bypass from preexisting state.
                # Force-reset to tdd/clear reason/save under lock.
                if state.mode == "bypass":
                    state.mode = "tdd"
                    state.bypass_reason = ""
                    state.save()
                    _audit("RESET bypass→tdd in loop mode (cannot persist from preexisting state)")
            else:
                state = loaded

            # Activation: loop mode always active; non-loop needs sprint-status
            if not _is_loop_mode() and not _story_in_progress():
                return 0

            # Bypass mode (non-loop only; loop disables bypass — already reset above)
            if state.mode == "bypass" and not loop_active:
                if event == "PreToolUse" and tool_name in ("Edit", "Write", "MultiEdit"):
                    kind = _classify(_target_paths(tool_input))
                    if kind in ("prod", "test"):
                        _audit(
                            f"BYPASS allow {kind} edit: {_target_paths(tool_input)} "
                            f"(reason: {state.bypass_reason})"
                        )
                return 0

            hook_session_id = str(payload.get("session_id", "") or "")
            if event == "PreToolUse":
                handle_pre_tool_use(tool_name, tool_input, state, hook_session_id)
            elif event == "PostToolUse":
                handle_post_tool_use(
                    tool_name,
                    tool_input,
                    payload.get("tool_response"),
                    state,
                    hook_session_id,
                )
        return 0

    except SystemExit:
        raise  # _deny / explicit exits propagate
    except Exception as exc:  # noqa: BLE001
        if loop_active:
            # Fail-closed in loop mode
            sys.stderr.write(f"🚫 TDD gate error (fail-closed): {exc!r}\n")
            _audit(f"ERROR (fail-closed deny): {exc!r}")
            sys.exit(2)
        else:
            # Fail-open outside loop mode (binding requirement: gate must never
            # brick non-loop workflows due to internal bugs)
            _audit(f"ERROR (fail-open allow): {exc!r}")
            return 0


if __name__ == "__main__":
    sys.exit(main())
