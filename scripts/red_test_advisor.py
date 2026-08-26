"""Deterministic RED-test assertion-shape advisor (C4, advisory-only).

Static ``ast`` analysis of the exact pytest targets a RED phase wrote. It
classifies assertion SHAPES (exact-equality over a call-derived value, broad
truthiness, count-only mocks, ...) and records agreement with the LLM
mutant-hunting review. It never executes test code, never mutates repository
state, and never authorizes GREEN: every verdict is calibration evidence for
humans. ``strong`` means a mutation-sensitive SHAPE exists — it does not prove
the assertion covers the story's semantic subject.

Determinism: canonical JSON, sorted collections, no timestamps/locale/TTY in
the result; identical inputs yield byte-identical payloads across processes
and ``PYTHONHASHSEED`` values. Exit code 0 covers every analysis outcome
(including ``unsupported``); exit code 2 is reserved for malformed CLI usage,
path-security violations, and write failures.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

RULESET_ID = "red-test-advisor/v1"
SCHEMA_VERSION = 1

STRONG = "strong"
WEAK = "weak"
UNSUPPORTED = "unsupported"
LLM_LABELS = (STRONG, WEAK, UNSUPPORTED)

_RAISES_ATTR = "raises"
_BROAD_EXCEPTION_NAMES = frozenset({"Exception", "BaseException"})
_MOCK_EXACT_ARG_METHODS = frozenset(
    {"assert_called_with", "assert_called_once_with", "assert_any_call"}
)
_MOCK_COUNT_ONLY_METHODS = frozenset({"assert_called", "assert_called_once", "assert_not_called"})
_DYNAMIC_CALL_NAMES = frozenset({"exec", "eval", "compile", "__import__"})

_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[[^]\[]*\])?$")


class AdvisorError(Exception):
    """CLI misuse, path-security violation, or write failure (exit code 2)."""


class TargetUnsupported(Exception):
    """One target cannot be analyzed safely; carries a stable reason code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


# ---------------------------------------------------------------------------
# Canonical serialization and hashing


def canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_of_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_of_payload(payload: dict) -> str:
    return sha256_of_bytes(canonical_json(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# Path safety


def safe_relative(text: str) -> Path:
    if not text or "\x00" in text:
        raise AdvisorError("empty or NUL-containing path")
    if text.startswith("/") or text.startswith("~") or (len(text) > 1 and text[1] == ":"):
        raise AdvisorError(f"absolute path rejected: {text!r}")
    candidate = Path(*text.split("/"))
    for part in candidate.parts:
        if part in {"", ".", ".."}:
            raise AdvisorError(f"unsafe path component in {text!r}")
    return candidate


def _ensure_under(root: Path, candidate: Path) -> None:
    root_real = os.path.realpath(root)
    candidate_real = os.path.realpath(candidate)
    if candidate_real != root_real and not candidate_real.startswith(root_real + os.sep):
        raise AdvisorError(f"path escapes {root}: {candidate}")


def _reject_symlink_components(root: Path, relative: Path, include_leaf: bool) -> None:
    current = root
    parts = relative.parts if include_leaf else relative.parts[:-1]
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise AdvisorError(f"symlinked path component: {current}")


def _reject_symlinked_root(root: Path) -> None:
    if root.is_symlink():
        raise AdvisorError(f"symlinked root rejected: {root}")


def read_target_source(project_root: Path, relative: Path) -> bytes:
    _reject_symlinked_root(project_root)
    _ensure_under(project_root, project_root / relative)
    _reject_symlink_components(project_root, relative, include_leaf=True)
    path = project_root / relative
    if not path.is_file():
        raise TargetUnsupported("target-not-found", str(relative))
    try:
        return path.read_bytes()
    except OSError as exc:
        raise TargetUnsupported("source-inaccessible", str(exc)) from exc


def atomic_write_json(root: Path, output: Path, payload: dict) -> None:
    _reject_symlinked_root(root)
    root.mkdir(parents=True, exist_ok=True)
    _ensure_under(root, output)
    relative = output.relative_to(Path(os.path.realpath(root)))
    _reject_symlink_components(root, relative, include_leaf=False)
    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    text = canonical_json(payload)
    fd, temp_name = tempfile.mkstemp(dir=parent, prefix=".advisor-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_name, output)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        raise


# ---------------------------------------------------------------------------
# Nodeid parsing and AST selection


def parse_nodeid(nodeid: str) -> tuple[Path, list[str], str]:
    segments = nodeid.split("::")
    if len(segments) < 2:
        raise TargetUnsupported("unsupported-nodeid", nodeid)
    relative = safe_relative(segments[0])
    if relative.suffix != ".py":
        raise TargetUnsupported("non-python-file", str(relative))
    names: list[str] = []
    for segment in segments[1:]:
        match = _SEGMENT_RE.match(segment)
        if match is None:
            raise TargetUnsupported("unsupported-nodeid", segment)
        names.append(match.group(1))
    if not names:
        raise TargetUnsupported("unsupported-nodeid", nodeid)
    normalized = relative.as_posix() + "::" + "::".join(names)
    return relative, names, normalized


def select_function(tree: ast.Module, names: list[str]) -> ast.AST:
    containers: list[ast.AST] = [tree]
    for name in names[:-1]:
        matched = [
            child
            for container in containers
            for child in ast.iter_child_nodes(container)
            if isinstance(child, ast.ClassDef) and child.name == name
        ]
        if len(matched) != 1:
            raise TargetUnsupported("ambiguous-or-missing-target", name)
        containers = [matched[0]]
    functions = [
        child
        for container in containers
        for child in ast.iter_child_nodes(container)
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == names[-1]
    ]
    if len(functions) != 1:
        raise TargetUnsupported("ambiguous-or-missing-target", names[-1])
    return functions[0]


# ---------------------------------------------------------------------------
# Assertion-shape ruleset v1


def _collect_call_derived_names(func: ast.AST) -> set[str]:
    derived: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            value, targets = node.value, list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            value, targets = node.value, [node.target]
        else:
            continue
        if value is None:
            continue
        if any(isinstance(inner, ast.Call) for inner in ast.walk(value)):
            for target in targets:
                for inner in ast.walk(target):
                    if isinstance(inner, ast.Name):
                        derived.add(inner.id)
    return derived


def _is_call_derived(expression: ast.AST, derived: set[str]) -> bool:
    for node in ast.walk(expression):
        if isinstance(node, ast.Call):
            return True
        if isinstance(node, ast.Name) and node.id in derived:
            return True
    return False


def _const_like(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return isinstance(node.operand, ast.Constant)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(_const_like(element) for element in node.elts)
    if isinstance(node, ast.Dict):
        keys_ok = all(key is None or _const_like(key) for key in node.keys)
        values_ok = all(_const_like(value) for value in node.values)
        return keys_ok and values_ok
    return False


def _signal(
    rule_id: str,
    severity: str,
    target: str,
    node: ast.AST,
    explanation: str,
) -> dict:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "target": target,
        "line": getattr(node, "lineno", 0),
        "col": getattr(node, "col_offset", 0),
        "explanation": explanation,
    }


def _classify_raises(item: ast.withitem, node: ast.AST, target: str) -> dict | None:
    context = item.context_expr
    if not (
        isinstance(context, ast.Call)
        and isinstance(context.func, ast.Attribute)
        and context.func.attr == _RAISES_ATTR
    ):
        return None
    body_has_call = any(isinstance(inner, ast.Call) for inner in ast.walk(node))
    exception_node = context.args[0] if context.args else None
    broad = exception_node is None or (
        (isinstance(exception_node, ast.Name) and exception_node.id in _BROAD_EXCEPTION_NAMES)
        or (
            isinstance(exception_node, ast.Attribute)
            and exception_node.attr in _BROAD_EXCEPTION_NAMES
        )
    )
    has_match = any(keyword.arg == "match" for keyword in context.keywords)
    if not broad and has_match and body_has_call:
        return _signal(
            "raises-specific-with-match",
            STRONG,
            target,
            node,
            "pytest.raises with a specific exception and match wraps a call",
        )
    if broad:
        return _signal(
            "raises-broad-exception",
            WEAK,
            target,
            node,
            "pytest.raises(Exception)/BaseException accepts any failure",
        )
    if body_has_call:
        return _signal(
            "raises-specific-without-match",
            WEAK,
            target,
            node,
            "specific exception without match= does not pin the message contract",
        )
    return _signal(
        "raises-without-call",
        WEAK,
        target,
        node,
        "raises block wraps no subject call",
    )


def _is_none_node(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _classify_compare(test: ast.Compare, derived: set[str], target: str) -> dict | None:
    sides = [test.left, *test.comparators]
    if len(test.ops) != 1 or len(sides) != 2:
        return _signal(
            "chained-comparison", WEAK, target, test, "chained comparisons are not pinned"
        )
    op = test.ops[0]
    left, right = sides
    len_match = (
        isinstance(left, ast.Call)
        and isinstance(left.func, ast.Name)
        and left.func.id == "len"
        and len(left.args) == 1
        and isinstance(right, ast.Constant)
        and isinstance(right.value, int)
        and not isinstance(right.value, bool)
    )
    if len_match:
        if isinstance(op, ast.Eq) and _is_call_derived(left.args[0], derived):
            return _signal(
                "exact-cardinality-call-derived",
                STRONG,
                target,
                test,
                "len() of call-derived data equals a specific size",
            )
        return _signal(
            "loose-cardinality",
            WEAK,
            target,
            test,
            "cardinality comparison is inexact or not call-derived",
        )
    if _is_none_node(left) or _is_none_node(right):
        return _signal(
            "none-identity", WEAK, target, test, "None identity accepts aliased/mutated results"
        )
    if isinstance(op, (ast.Eq, ast.Is)):
        if _is_call_derived(left, derived) and _const_like(right):
            return _signal(
                "exact-equality-call-derived",
                STRONG,
                target,
                test,
                "call-derived value compared exactly against a specific constant",
            )
        if _is_call_derived(right, derived) and _const_like(left):
            return _signal(
                "exact-equality-call-derived",
                STRONG,
                target,
                test,
                "specific constant compared exactly against a call-derived value",
            )
        if _is_call_derived(left, derived) or _is_call_derived(right, derived):
            return _signal(
                "equality-without-expected-constant",
                WEAK,
                target,
                test,
                "equality between non-constant operands does not pin a value",
            )
        return _signal(
            "assertion-not-call-derived",
            WEAK,
            target,
            test,
            "equality involves neither the subject call nor its derived data",
        )
    if isinstance(op, (ast.In, ast.NotIn)):
        if isinstance(op, ast.In) and _is_call_derived(left, derived) and _const_like(right):
            return _signal(
                "membership-call-derived",
                STRONG,
                target,
                test,
                "call-derived value checked against specific collection contents",
            )
        return _signal(
            "loose-membership", WEAK, target, test, "membership check is not exact-content"
        )
    return _signal(
        "range-comparison", WEAK, target, test, "ordered comparison does not pin an exact result"
    )


def _classify_assert(test: ast.AST, derived: set[str], target: str) -> dict | None:
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _signal(
            "bare-truthiness", WEAK, target, test, "negated truthiness accepts many wrong results"
        )
    if isinstance(test, ast.Compare):
        return _classify_compare(test, derived, target)
    if (
        isinstance(test, ast.Call)
        and isinstance(test.func, ast.Name)
        and test.func.id == "isinstance"
    ):
        return _signal("type-only-check", WEAK, target, test, "isinstance pins type, not behavior")
    if isinstance(test, ast.BoolOp):
        for value in test.values:
            if isinstance(value, ast.Compare):
                return _classify_compare(value, derived, target)
    call_count = any(
        isinstance(node, ast.Attribute) and node.attr == "call_count" for node in ast.walk(test)
    )
    if call_count:
        return _signal(
            "mock-count-only", WEAK, target, test, "call_count ignores arguments and outcomes"
        )
    called = any(
        isinstance(node, ast.Attribute) and node.attr == "called" for node in ast.walk(test)
    )
    if called:
        return _signal(
            "mock-count-only", WEAK, target, test, ".called ignores arguments and outcomes"
        )
    if _const_like(test):
        return _signal(
            "constant-assertion", WEAK, target, test, "assertion about constants proves nothing"
        )
    return _signal("bare-truthiness", WEAK, target, test, "truthiness accepts many wrong results")


def analyze_function(func: ast.AST, target: str) -> list[dict]:
    derived = _collect_call_derived_names(func)
    signals: list[dict] = []
    assert_count = 0
    for node in ast.walk(func):
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                signal = _classify_raises(item, node, target)
                if signal is not None:
                    signals.append(signal)
            continue
        if isinstance(node, ast.Assert):
            assert_count += 1
            signal = _classify_assert(node.test, derived, target)
            if signal is not None:
                signals.append(signal)
            continue
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _DYNAMIC_CALL_NAMES:
                raise TargetUnsupported("dynamic-exec", target)
            if isinstance(node.func, ast.Attribute):
                attribute = node.func.attr
                if attribute in _MOCK_EXACT_ARG_METHODS and node.args:
                    signals.append(
                        _signal(
                            "interaction-exact-args",
                            STRONG,
                            target,
                            node,
                            "mock interaction asserted with expected arguments",
                        )
                    )
                elif (
                    attribute == "assert_has_calls"
                    and node.args
                    and not any(
                        keyword.arg == "any_order" and keyword.value is True
                        for keyword in node.keywords
                        if isinstance(keyword.value, ast.Constant)
                    )
                ):
                    signals.append(
                        _signal(
                            "interaction-exact-args",
                            STRONG,
                            target,
                            node,
                            "expected call sequence asserted in order",
                        )
                    )
                elif attribute in _MOCK_COUNT_ONLY_METHODS:
                    signals.append(
                        _signal(
                            "mock-count-only",
                            WEAK,
                            target,
                            node,
                            "count-only mock assertion ignores arguments/outcomes",
                        )
                    )
    if assert_count == 0 and not any(signal["severity"] == STRONG for signal in signals):
        signals.append(
            _signal("no-behavior-assertion", WEAK, target, func, "target contains no assertions")
        )
    return signals


# ---------------------------------------------------------------------------
# Commands


def _analyze_target(project_root: Path, nodeid: str) -> tuple[dict, list[dict]]:
    relative, names, normalized = parse_nodeid(nodeid)
    source = read_target_source(project_root, relative)
    try:
        tree = ast.parse(source.decode("utf-8"), filename=str(relative))
    except (SyntaxError, ValueError, UnicodeDecodeError) as exc:
        raise TargetUnsupported("syntax-error", str(exc)) from exc
    func = select_function(tree, names)
    signals = analyze_function(func, normalized)
    entry = {
        "target": normalized,
        "requested": nodeid,
        "path": relative.as_posix(),
        "source_sha256": sha256_of_bytes(source),
    }
    return entry, signals


def _aggregate(signals: list[dict]) -> str:
    severities = {signal["severity"] for signal in signals}
    if UNSUPPORTED in severities:
        return UNSUPPORTED
    if WEAK in severities or not signals:
        return WEAK
    return STRONG


def _normalizes_to(nodeid: str, key: str) -> bool:
    try:
        return parse_nodeid(nodeid)[2] == key
    except TargetUnsupported:
        return nodeid == key


def cmd_analyze(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    evidence_root = Path(args.evidence_root)
    _reject_symlinked_root(project_root)
    _reject_symlinked_root(evidence_root)
    if not project_root.is_dir():
        raise AdvisorError(f"project root is not a directory: {project_root}")
    # Dedupe by normalized nodeid; shape-invalid nodeids become their own
    # unsupported record (rc 0) instead of aborting the run.
    order: list[str] = []
    normalized_of: dict[str, str | None] = {}
    parse_errors: dict[str, TargetUnsupported] = {}
    for nodeid in args.target:
        try:
            _, _, normalized = parse_nodeid(nodeid)
        except TargetUnsupported as exc:
            if nodeid not in parse_errors:
                order.append(nodeid)
                parse_errors[nodeid] = exc
            continue
        if normalized not in normalized_of:
            order.append(normalized)
            normalized_of[normalized] = None
    entries: list[dict] = []
    signals: list[dict] = []
    for key in sorted(order):
        error = parse_errors.get(key)
        if error is not None:
            entry = {
                "target": key,
                "requested": key,
                "path": None,
                "source_sha256": None,
            }
            target_signals = [
                {
                    "rule_id": error.reason,
                    "severity": UNSUPPORTED,
                    "target": key,
                    "line": 0,
                    "col": 0,
                    "explanation": error.detail or error.reason,
                }
            ]
        else:
            original = next(nodeid for nodeid in args.target if _normalizes_to(nodeid, key))
            try:
                entry, target_signals = _analyze_target(project_root, original)
            except TargetUnsupported as exc:
                entry = {
                    "target": key,
                    "requested": original,
                    "path": None,
                    "source_sha256": None,
                }
                target_signals = [
                    {
                        "rule_id": exc.reason,
                        "severity": UNSUPPORTED,
                        "target": key,
                        "line": 0,
                        "col": 0,
                        "explanation": exc.detail or exc.reason,
                    }
                ]
        entry["status"] = _aggregate(target_signals)
        entries.append(entry)
        signals.extend(target_signals)
    signals.sort(key=lambda s: (s["target"], s["rule_id"], s["line"], s["col"]))
    unsupported_reasons = sorted({s["rule_id"] for s in signals if s["severity"] == UNSUPPORTED})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ruleset_id": RULESET_ID,
        "scenario_id": args.scenario_id,
        "request": {"scenario_id": args.scenario_id, "targets": sorted(order)},
        "targets": entries,
        "signals": signals,
        "unsupported_reasons": unsupported_reasons,
        "semantic_uncertainty": True,
        "verdict": _aggregate(signals),
    }
    payload["result_sha256"] = sha256_of_payload(payload)
    output = Path(args.output)
    atomic_write_json(evidence_root, output, payload)
    print(canonical_json(payload))
    return 0


def _load_advisor(advisor_path: Path, evidence_root: Path) -> dict:
    _ensure_under(evidence_root, advisor_path)
    _reject_symlink_components(evidence_root, advisor_path, include_leaf=True)
    raw = advisor_path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise AdvisorError(f"advisor artifact is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise AdvisorError("unsupported advisor schema_version")
    if payload.get("ruleset_id") != RULESET_ID:
        raise AdvisorError("advisor ruleset_id mismatch")
    return {**payload, "_file_sha256": sha256_of_bytes(raw)}


def cmd_compare(args: argparse.Namespace) -> int:
    evidence_root = Path(args.evidence_root)
    _reject_symlinked_root(evidence_root)
    advisor = _load_advisor(Path(args.advisor), evidence_root)
    review_path = Path(args.llm_review)
    _ensure_under(evidence_root, review_path)
    _reject_symlink_components(evidence_root, review_path, include_leaf=True)
    review_bytes = review_path.read_bytes()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ruleset_id": RULESET_ID,
        "scenario_id": advisor.get("scenario_id"),
        "advisor_path": args.advisor,
        "advisor_file_sha256": advisor["_file_sha256"],
        "advisor_result_sha256": advisor.get("result_sha256"),
        "advisor_verdict": advisor.get("verdict"),
        "llm_verdict": args.llm_verdict,
        "agreement": advisor.get("verdict") == args.llm_verdict,
        "llm_review_path": args.llm_review,
        "llm_review_sha256": sha256_of_bytes(review_bytes),
        "target_hashes": [
            {"target": entry.get("target"), "source_sha256": entry.get("source_sha256")}
            for entry in advisor.get("targets", [])
        ],
        "calibration_only": True,
    }
    payload["result_sha256"] = sha256_of_payload(payload)
    output = Path(args.output)
    atomic_write_json(evidence_root, output, payload)
    print(canonical_json(payload))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--project-root", required=True)
    analyze.add_argument("--evidence-root", required=True)
    analyze.add_argument("--scenario-id", required=True)
    analyze.add_argument("--target", action="append", required=True)
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=cmd_analyze)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--advisor", required=True)
    compare.add_argument("--llm-verdict", required=True, choices=list(LLM_LABELS))
    compare.add_argument("--llm-review", required=True)
    compare.add_argument("--evidence-root", required=True)
    compare.add_argument("--output", required=True)
    compare.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (AdvisorError, OSError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
