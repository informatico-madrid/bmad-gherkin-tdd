"""Regression guard — coordinator-facing sources must NOT direct inline
`invoke skill: tdd-red|tdd-green|tdd-clean|tdd-refactor`.

The canonical protocol (see the bmad-gherkin-tdd module's model-routing
contract) requires that every coordinator-facing document identify the
Task agents `tdd-red-ornith / tdd-green-ornith / tdd-clean-ornith / tdd-refactor-ornith` where
sequencing is prescribed. Inline `invoke skill:` directives are stale and
contradict the Task→Skill routing contract.

Additionally, each coordinator source must use the EXACT dispatch directive
syntax (`invoke task: tdd-red-ornith`) rather than bare agent names, must
enforce RED→GREEN→CLEAN→REFACTOR ordering, and prompt.txt must describe all three
CLASSIFY outcomes (development, verification_preexisting, ambiguous/STOP).

Sources under audit (coordinator-facing, consumed by the orchestrator):
  - skills/bmad-tdd-coordinator/SKILL.md
  - skills/bmad-tdd-coordinator/prompt.txt

This test does NOT modify any of those files — it only asserts their content
conforms to the Task-agent naming convention.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]

# Sources to audit — all coordinator-facing, all must use Task agent names.
COORDINATOR_SOURCES: list[tuple[str, Path]] = [
    (
        "bmad-tdd-coordinator/SKILL.md",
        PROJECT_ROOT / "skills" / "bmad-tdd-coordinator" / "SKILL.md",
    ),
    (
        "bmad-tdd-coordinator/prompt.txt",
        PROJECT_ROOT / "skills" / "bmad-tdd-coordinator" / "prompt.txt",
    ),
]

# Stale inline `invoke skill:` patterns that must NOT appear.
STALE_PATTERNS: list[str] = [
    "invoke skill: tdd-red",
    "invoke skill: tdd-green",
    "invoke skill: tdd-refactor",
]

# Required Task agent names that MUST appear where sequencing is prescribed.
REQUIRED_TASK_AGENTS: list[str] = [
    "tdd-red-ornith",
    "tdd-green-ornith",
    "tdd-clean-ornith",
    "tdd-refactor-ornith",
]

# Exact dispatch directive forms required in every coordinator source.
# Pattern: `invoke task: <agent>` (with flexible whitespace).
EXACT_DIRECTIVE_PATTERN = re.compile(
    r"invoke\s+task\s*:\s*(tdd-red-ornith|tdd-green-ornith|tdd-clean-ornith|tdd-refactor-ornith)",
    re.IGNORECASE,
)

# Robust regex for stale inline skill directives — catches case/spacing
# variations that simple substring checks miss (e.g. "Invoke Skill: tdd-red",
# "invoke  skill  :  tdd-green", "INVOKE TASK: TDD-RED-ORNITH").
STALE_SKILL_DIRECTIVE_RE = re.compile(
    r"invoke\s+skill\s*:\s*tdd-(?:red|green|clean|refactor)\b",
    re.IGNORECASE,
)

# Classification vocabulary that MUST appear in prompt.txt.
# These are the three CLASSIFY outcomes from the coordinator protocol:
#   A) development      — standard RED→GREEN→CLEAN→REFACTOR
#   B) verification_preexisting — skip RED, GREEN→REFACTOR only
#   C) ambiguous        — STOP, report evidence gap
CLASSIFICATION_VOCAB: list[str] = [
    "development",
    "verification_preexisting",
    "ambiguous",
    "STOP",
]


@pytest.mark.parametrize("label, path", COORDINATOR_SOURCES, ids=lambda p: str(p))
def test_no_stale_invoke_skill_directive(label: str, path: Path) -> None:
    """Each coordinator source must NOT contain inline `invoke skill: tdd-*`.

    These stale directives must be replaced with Task agent references
    (tdd-red-ornith / tdd-green-ornith / tdd-refactor-ornith).
    """
    assert path.exists(), f"Coordinator source missing: {path}"
    content = path.read_text(encoding="utf-8")

    violations: list[str] = []
    for pattern in STALE_PATTERNS:
        # Search case-insensitively for the exact directive form.
        lower = content.lower()
        if pattern.lower() in lower:
            violations.append(pattern)

    assert not violations, (
        f"Coordinator source '{label}' ({path.name}) contains stale "
        f"`invoke skill:` directives:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nThese must reference Task agents instead:"
        + "\n".join(f"  - {a}" for a in REQUIRED_TASK_AGENTS)
    )


@pytest.mark.parametrize("label, path", COORDINATOR_SOURCES, ids=lambda p: str(p))
def test_no_stale_skill_directive_robust_regex(label: str, path: Path) -> None:
    """Stale `invoke skill:` directives must not appear in ANY case/spacing
    variation. Uses a robust regex that catches:
      - ``invoke skill: tdd-red``
      - ``Invoke Skill: tdd-green``
      - ``INVOKE  SKILL  :  TDD-REFACOR``
      - ``invoke skill:tdd-red`` (no space after colon)

    This is stricter than the substring check in test_no_stale_invoke_skill_directive,
    catching formatting variations that naive ``in`` checks might miss.
    """
    assert path.exists(), f"Coordinator source missing: {path}"
    content = path.read_text(encoding="utf-8")

    matches = STALE_SKILL_DIRECTIVE_RE.findall(content)
    assert not matches, (
        f"Coordinator source '{label}' ({path.name}) contains stale "
        f"`invoke skill:` directives (regex match):\n"
        + "\n".join(f"  - invoke skill: {m}" for m in matches)
    )


@pytest.mark.parametrize("label, path", COORDINATOR_SOURCES, ids=lambda p: str(p))
def test_exact_dispatch_directives_present(label: str, path: Path) -> None:
    """Each coordinator source must contain the EXACT dispatch directive
    syntax `invoke task: <agent>` for all three Task agents.

    Bare agent names (e.g. just "tdd-red-ornith") are insufficient — the
    protocol requires the explicit `invoke task:` form to distinguish
    dispatch from mere mention.
    """
    assert path.exists(), f"Coordinator source missing: {path}"
    content = path.read_text(encoding="utf-8")

    missing: list[str] = []
    for agent in REQUIRED_TASK_AGENTS:
        directive = f"invoke task: {agent}"
        if not re.search(
            rf"invoke\s+task\s*:\s*{re.escape(agent)}\b",
            content,
            re.IGNORECASE,
        ):
            missing.append(directive)

    assert not missing, (
        f"Coordinator source '{label}' ({path.name}) is missing exact "
        f"dispatch directives:\n"
        + "\n".join(f"  - {item}" for item in missing)
        + "\n\nRequired form: `invoke task: <agent-name>`"
    )


@pytest.mark.parametrize("label, path", COORDINATOR_SOURCES, ids=lambda p: str(p))
def test_red_green_clean_refactor_ordering(label: str, path: Path) -> None:
    """Each coordinator source must prescribe RED→GREEN→CLEAN→REFACTOR in that
    order. The position of `tdd-red-ornith` must precede `tdd-green-ornith`,
    which must precede `tdd-refactor-ornith`.

    This prevents sources from listing agents in arbitrary order or
    suggesting non-canonical sequences (e.g. GREEN before RED).
    """
    assert path.exists(), f"Coordinator source missing: {path}"
    content = path.read_text(encoding="utf-8")

    red_pos = _first_match_position(content, "tdd-red-ornith")
    green_pos = _first_match_position(content, "tdd-green-ornith")
    clean_pos = _first_match_position(content, "tdd-clean-ornith")
    refactor_pos = _first_match_position(content, "tdd-refactor-ornith")

    assert red_pos >= 0, f"'tdd-red-ornith' not found in '{label}'"
    assert green_pos >= 0, f"'tdd-green-ornith' not found in '{label}'"
    assert clean_pos >= 0, f"'tdd-clean-ornith' not found in '{label}'"
    assert refactor_pos >= 0, f"'tdd-refactor-ornith' not found in '{label}'"

    assert red_pos < green_pos, (
        f"Coordinator source '{label}' ({path.name}) has tdd-green-ornith "
        f"(pos {green_pos}) BEFORE tdd-red-ornith (pos {red_pos}). "
        f"RED must come before GREEN."
    )
    assert green_pos < clean_pos < refactor_pos, (
        f"Coordinator source '{label}' ({path.name}) must order GREEN, CLEAN, REFACTOR; "
        f"found positions {green_pos}, {clean_pos}, {refactor_pos}."
    )


def test_no_stale_three_phase_protocol_text() -> None:
    sources = [
        PROJECT_ROOT / "skills" / "bmad-tdd-coordinator" / "SKILL.md",
        PROJECT_ROOT / "skills" / "bmad-tdd-coordinator" / "prompt.txt",
        PROJECT_ROOT / "templates" / "custom" / "bmad-dev-auto.toml",
        PROJECT_ROOT / "templates" / "custom" / "bmad-tdd-coordinator.toml",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "setup" / "SKILL.md",
    ]
    stale = re.compile(r"RED\s*(?:→|->|/)\s*GREEN\s*(?:→|->|/)\s*REFACTOR", re.IGNORECASE)
    matches = [
        str(path.relative_to(PROJECT_ROOT)) for path in sources if stale.search(path.read_text())
    ]
    assert matches == []


@pytest.mark.parametrize("label, path", COORDINATOR_SOURCES, ids=lambda p: str(p))
def test_classification_vocabulary_coverage(label: str, path: Path) -> None:
    """Each coordinator source must reference the CLASSIFY outcomes:
    development, verification_preexisting, and ambiguous.

    These are the three possible classifications from the Pre-RED
    Classification Gate. Sources that omit any of these lack the
    vocabulary needed to describe the full protocol.
    """
    assert path.exists(), f"Coordinator source missing: {path}"
    content = path.read_text(encoding="utf-8")

    missing: list[str] = []
    for term in ("development", "verification_preexisting", "ambiguous"):
        if term not in content:
            missing.append(term)

    assert not missing, (
        f"Coordinator source '{label}' ({path.name}) is missing CLASSIFY "
        f"vocabulary:\n"
        + "\n".join(f"  - {item}" for item in missing)
        + "\n\nRequired terms: development, verification_preexisting, ambiguous"
    )


@pytest.mark.parametrize("label, path", COORDINATOR_SOURCES, ids=lambda p: str(p))
def test_stop_keyword_for_ambiguous(label: str, path: Path) -> None:
    """Each coordinator source must describe the STOP action for the
    ambiguous classification outcome. When evidence is partial or
    contradictory, the protocol mandates STOP — never invent RED.
    """
    assert path.exists(), f"Coordinator source missing: {path}"
    content = path.read_text(encoding="utf-8")

    # Case-insensitive search for STOP keyword in context of ambiguous handling.
    # Patterns: "ambiguous.*STOP", "STOP.*ambiguous", or standalone "STOP" near
    # classification-related text.
    has_ambiguous_stop = bool(
        re.search(
            r"ambiguous\b[\s\S]{0,200}?STOP\b",
            content,
            re.IGNORECASE,
        )
        or re.search(
            r"STOP\b[\s\S]{0,200}?ambiguous\b",
            content,
            re.IGNORECASE,
        )
    )

    assert has_ambiguous_stop, (
        f"Coordinator source '{label}' ({path.name}) must describe STOP "
        f"action for ambiguous classification. The protocol mandates STOP "
        f"when evidence is incomplete — never invent RED."
    )


@pytest.mark.parametrize("label, path", COORDINATOR_SOURCES, ids=lambda p: str(p))
def test_verification_preexisting_skip_red_described(label: str, path: Path) -> None:
    """The verification_preexisting classification must describe skipping RED.
    This is the core behavioral difference from the default development path.
    """
    assert path.exists(), f"Coordinator source missing: {path}"
    content = path.read_text(encoding="utf-8")

    # Must mention that verification_preexisting skips or bypasses RED.
    has_skip_description = bool(
        re.search(
            r"verification_preexisting\b[\s\S]{0,300}?(?:skip|bypass|without|omit|saltar)\b",
            content,
            re.IGNORECASE,
        )
        or re.search(
            r"skip\b[\s\S]{0,300}?verification_preexisting\b",
            content,
            re.IGNORECASE,
        )
    )

    assert has_skip_description, (
        f"Coordinator source '{label}' ({path.name}) must describe that "
        f"verification_preexisting skips/bypasses RED. This is the key "
        f"behavioral distinction from the default development path."
    )


def _first_match_position(content: str, needle: str) -> int:
    """Return the byte position of the first occurrence of `needle` in
    `content`, or -1 if not found. Case-sensitive match.
    """
    pos = content.find(needle)
    return pos if pos >= 0 else -1
