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

    READY ──(pytest RED)──▶ RED_SEEN ──(story edit "ROJO:")──▶ CODING
      ▲                                                           │
      │                                            (Edit src/** allowed)
      │                                                           ▼
      │                                                (pytest GREEN)──▶ GREEN_SEEN
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

Observed PostToolUse events (advance the machine, never block):
  • Bash running pytest (not mutmut): RED in READY → RED_SEEN; GREEN in CODING → GREEN_SEEN.
  • Bash reporting PASS in READY while tdd-red is pending (loop mode): READY → RED_VIOLATION.
  • Edit/Write to the story ``.md``: "ROJO:"@RED_SEEN→CODING, "VERDE:"@GREEN_SEEN→CLEAN,
    "CLEAN:"@CLEAN→REFACTOR, "REFACTOR:"@REFACTOR→READY (cycle closed).

Activation: the gate is **active only while a story is ``in-progress``** in the sprint-status
file (configured via ``BMAD_TDD_SPRINT_STATUS``, default
``_bmad-output/implementation-artifacts/sprint-status.yaml`` — a state the dev flow sets
mechanically). Outside a dev-story run it is inert. During non-TDD phases inside a story
(mutation hardening, large refactors, chores) use the audited bypass:
    python3 hooks/tdd_cycle_gate.py bypass "killing mutants"
    python3 hooks/tdd_cycle_gate.py resume

Loop Mode (fb70 bypass closure): when ``BMAD_LOOP_MODE=1`` and ``BMAD_LOOP_STORY_KEY`` is set,
the gate activates unconditionally regardless of sprint-status. It additionally:
  - Observes Tool Skill invocations and enforces the coordinator→red→green→refactor order.
  - Keeps per-story state isolated (``tdd-state-<safe>.json``).
  - Blocks direct Bash writes to src/tests (expanded practical closure).
  - Disables the CLI ``bypass`` command.
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
import sys
import uuid
from collections.abc import Mapping
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# ── Locations (relative to the repo root = the hook's cwd) ────────────────────
# Parameterized via environment variables with generic defaults so the gate is
# project-agnostic (bmad-gherkin-tdd module). A project may override any of these
# in its own environment (e.g. a `.env` loaded by the harness or CI).
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

# Production and test source prefixes. Generic defaults assume a conventional
# layout (``src/``, ``tests/``); a project overrides via BMAD_TDD_PROD_PREFIX /
# BMAD_TDD_TEST_PREFIX to match its own tree.
_PROD_PREFIX = os.environ.get("BMAD_TDD_PROD_PREFIX", "src/")
_TEST_PREFIX = os.environ.get("BMAD_TDD_TEST_PREFIX", "tests/")

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
    # RED-pending guard: True once tdd-red-ornith is invoked in READY, cleared
    # when a FAIL is observed or the cycle closes. A pytest PASS while
    # red_pending is True is a protocol violation → RED_VIOLATION.
    red_pending: bool = False
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
                "red_pending",
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


def handle_pre_tool_use(tool_name: str, tool_input: dict, state: State) -> None:
    if _is_loop_mode():
        _handle_loop_mode_pre_tool_use(tool_name, tool_input, state)
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


def _handle_loop_mode_pre_tool_use(tool_name: str, tool_input: dict, state: State) -> None:
    """Loop-mode PreToolUse handler: observes skills, blocks bash writes, enforces cycle."""
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
        _process_loop_skill(skill_name, state)
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

        # Known TDD phase agents and their required phases
        _TASK_AGENT_PHASE = {
            "tdd-red-ornith": READY,
            "tdd-green-ornith": CODING,
            "tdd-clean-ornith": CLEAN,
            "tdd-refactor-ornith": REFACTOR,
        }

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
            # Record green task, transition READY→CODING, save+audit
            if "tdd-green-ornith" not in state.phase_agent_seen:
                state.phase_agent_seen.append("tdd-green-ornith")
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

        # Record the Task agent in phase_agent_seen (only Task handler mutates this)
        if subagent_type not in state.phase_agent_seen:
            state.phase_agent_seen.append(subagent_type)
        if subagent_type == "tdd-red-ornith":
            state.red_pending = True
        state.save()
        sys.exit(0)

    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
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
                _deny(_NEXT_TEST_FIX.format(phase=state.phase) + _BYPASS_HINT)

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
                _deny(_ROJO_FIX + _BYPASS_HINT)
            elif state.phase == GREEN_SEEN:
                if "tdd-green" in state.skill_seen:
                    sys.exit(0)
                _deny(_VERDE_FIX + _BYPASS_HINT)
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
                _deny(_RED_FIX.format(phase=state.phase) + _BYPASS_HINT)
        sys.exit(0)

    sys.exit(0)


def _process_loop_skill(skill_name: str, state: State) -> None:
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

_PYTEST_RE = re.compile(r"\bpytest\b")
_FAIL_RE = re.compile(r"\b(\d+ failed|\d+ error|errors?\b|FAILED|ERROR)\b")
_PASS_RE = re.compile(r"\b\d+ passed\b")


def _bash_outcome(command: str, output: str) -> str | None:
    """Return 'red', 'green', or None for a Bash command that ran pytest (not mutmut)."""
    if not _PYTEST_RE.search(command) or "mutmut" in command:
        return None
    if _FAIL_RE.search(output):
        return "red"
    if _PASS_RE.search(output):
        return "green"
    return None


def handle_post_tool_use(
    tool_name: str, tool_input: dict, tool_response: object, state: State
) -> None:
    changed = False
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        outcome = _bash_outcome(command, _stringify(tool_response))
        if outcome == "red" and state.phase == READY:
            state.phase = RED_SEEN
            state.red_pending = False
            changed = True
        elif outcome == "green" and state.phase == CODING:
            state.phase = GREEN_SEEN
            state.red_pending = False
            changed = True
        elif outcome == "green" and state.phase == READY and _is_loop_mode() and state.red_pending:
            # Protocol violation: a development RED passed instead of failing.
            state.phase = RED_VIOLATION
            changed = True
            _audit("RED_VIOLATION: pytest PASS during RED phase in READY")
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
    if changed:
        state.save()
    sys.exit(0)


def _handle_loop_post_tool_use(paths: list[str], tool_input: dict, state: State) -> bool:
    """Loop-mode PostToolUse: story bitácora transitions require matching skill."""
    changed = False
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
            changed = True
            _audit("WARNING: REFACTOR→READY transition (out-of-order bitácora check)")
    return changed


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
    "src/",
    "tests/",
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

    try:
        event = payload.get("hook_event_name", "")
        tool_name = payload.get("tool_name", "")
        tool_input = payload.get("tool_input", {}) or {}
        loop_active = _is_loop_mode()
        story_key = _current_story_key()

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

            if event == "PreToolUse":
                handle_pre_tool_use(tool_name, tool_input, state)
            elif event == "PostToolUse":
                handle_post_tool_use(tool_name, tool_input, payload.get("tool_response"), state)
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
