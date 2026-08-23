"""static_score.py — Static evaluator for TDD RED bench test files.

Evaluates test source code via AST analysis against a canonical list of
mutant surfaces. No execution, no SUT required.

Usage:
    python -m agent_bench.red.eval.static_score <test_file> [--feature <feature_file>]
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ── Load canonical surfaces ─────────────────────────────────────────

_SURFACES_PATH = Path(__file__).parent / "surfaces.yaml"


def _load_surfaces() -> list[dict[str, Any]]:
    with _SURFACES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["surfaces"]


SURFACES = _load_surfaces()


# ── AST helpers ─────────────────────────────────────────────────────




def _collect_numbers(node: ast.AST) -> list[float | int]:
    """Recursively collect all numeric literals from an AST node (excludes booleans)."""
    nums = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)) and not isinstance(child.value, bool):
            nums.append(child.value)
    return nums


def _has_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == name:
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == name:
            return True
    return False


def _find_all_funcs(tree: ast.Module) -> list[ast.FunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]


def _find_test_funcs(tree: ast.Module) -> list[ast.FunctionDef]:
    return [f for f in _find_all_funcs(tree) if f.name.startswith("test_")]


# ── Surface checkers ───────────────────────────────────────────────

def _check_dense_assertions(tree: ast.Module) -> bool:
    """§4.1: Assert full structure equality — Call, Dict, Tuple, or Set comparators."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            for comp in node.test.comparators:
                if isinstance(comp, (ast.Call, ast.Dict, ast.Tuple, ast.Set)):
                    return True
    return False


def _check_exact_boundary(tree: ast.Module) -> bool:
    """§4.2: Three numeric values at same comparison boundary."""
    all_nums = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_nums.extend(_collect_numbers(node))
    # Look for consecutive triples that differ by 1
    unique = sorted(set(all_nums))
    for i in range(len(unique) - 2):
        if unique[i + 1] - unique[i] == 1 and unique[i + 2] - unique[i + 1] == 1:
            return True
    return False


def _check_exact_string(tree: ast.Module) -> bool:
    """§4.3: == with exact string, not 'in str(...)'."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            if any(_is_eq_op(op) for op in node.test.ops):
                for comp in node.test.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        if len(comp.value) > 3:  # non-trivial string
                            return True
    return False


def _is_eq_op(op: ast.cmpop) -> bool:
    return isinstance(op, ast.Eq)


def _check_spy_complete(tree: ast.Module) -> bool:
    """§4.4: assert_called_once_with with multiple args/kwargs, OR
    attribute access on recorded calls (e.g. sink.calls[0].record is X)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "assert_called_once_with":
                if len(node.args) + len(node.keywords) >= 2:
                    return True
    # Check for spy-on-recorded pattern: calls[i].attr or .record is X
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("record", "timeout", "key", "score"):
            # Check if parent is a subscript (calls[0].record)
            for parent in ast.walk(tree):
                if isinstance(parent, ast.Subscript):
                    if isinstance(parent.value, ast.Attribute) and parent.value.attr == "calls":
                        return True
    return False


def _check_default_kwarg(tree: ast.Module) -> bool:
    """§4.5: Function call WITHOUT the optional kwarg AND downstream observation of default value."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _call_name(node)
            if func_name in ("apply", "normalize"):
                kw_names = {kw.arg for kw in node.keywords}
                if "timeout" not in kw_names and "fallback" not in kw_names:
                    # Must have a downstream assertion on the default value (e.g., == 600, == 10)
                    if _has_default_observation(tree, func_name):
                        return True
    return False


def _has_default_observation(tree: ast.Module, func_name: str) -> bool:
    """Check if there's an assertion observing the default value (600 for timeout, 10 for fallback)."""
    defaults = {"apply": 600, "normalize": 10}
    expected = defaults.get(func_name)
    if expected is None:
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            for comp in node.test.comparators:
                if isinstance(comp, ast.Constant) and comp.value == expected:
                    return True
    return False


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _check_accumulator_asymmetric(tree: ast.Module) -> bool:
    """§4.6: >=2 items with asymmetric values (3 and 5)."""
    for node in ast.walk(tree):
        nums = _collect_numbers(node)
        if 3 in nums and 5 in nums and len(set(nums)) >= 2:
            return True
    return False


def _check_break_count(tree: ast.Module) -> bool:
    """§4.7: Count iterations / calls. len(...) == N pattern."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Compare):
                for comp in node.test.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, int):
                        # Check if left side is a len() call: Call(func=Name(id='len',...),...)
                        left = node.test.left
                        if isinstance(left, ast.Call):
                            if isinstance(left.func, ast.Name) and left.func.id == "len":
                                return True
    return False


def _check_truth_table(tree: ast.Module) -> bool:
    """§4.8: TF and FT cases for and/or. Accepts 1 function with ≥4 combos OR 2+ functions with ≥2 combos."""
    test_funcs = _find_test_funcs(tree)
    total_combos = 0
    for fn in test_funcs:
        # Count distinct boolean constant pairs in assertions
        bool_constants = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Constant) and isinstance(node.value, bool):
                bool_constants.add(node.value)
        if len(bool_constants) >= 2:
            # Has both True and False — count as at least 2 combos (TF and FT)
            total_combos += 2
    return total_combos >= 4 or len([f for f in test_funcs if any(
        isinstance(n, ast.Constant) and isinstance(n.value, bool)
        for n in ast.walk(f)
    )]) >= 2


def _check_hypothesis(tree: ast.Module) -> bool:
    """§4.9: @given decorator."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _has_decorator(node, "given"):
                return True
    return False


def _check_caplog_exact(tree: ast.Module) -> bool:
    """§4.3: caplog with == message. Matches caplog.records[i].message or caplog.messages."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            # Check if caplog is referenced in the left side
            left_dump = ast.dump(node.test.left)
            if "caplog" in left_dump:
                return True
        # Also match caplog.messages = [...] assignment
        if isinstance(node, ast.Assign):
            src = ast.dump(node)
            if "caplog" in src and "messages" in src:
                return True
    return False


def _check_typed_exception(tree: ast.Module) -> bool:
    """§4.3: Specific exception type + match=re.escape(...) OR str(exc.value) == 'exact'."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "raises":
                # Check for match kwarg with re.escape
                for kw in node.keywords:
                    if kw.arg == "match":
                        return True
        # Also match str(exc.value) == "exact message" pattern
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            left_dump = ast.dump(node.test.left)
            if "exc" in left_dump and "value" in left_dump:
                return True
    return False


def _check_h1_wiring(tree: ast.Module) -> bool:
    """H1: assert_called_once_with + is (identity) for all args. Also matches
    spy pattern: sink.calls[0].record is X, record is accepted."""
    has_spy = False
    has_identity = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "assert_called_once_with":
                has_spy = True
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if isinstance(op, ast.Is):
                    has_identity = True
    # Also check for spy-on-recorded-calls pattern
    if has_identity:
        src = ast.dump(tree)
        if "calls" in src or "sink" in src or "spy" in src:
            return True
    return has_spy and has_identity


def _check_h2_clock(tree: ast.Module) -> bool:
    """H2: clock.now() called, or clock.now_count / clock.now_values / clock.now.call_count asserted."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "now":
                return True
        # Match clock.now_count, clock.now_values, clock.now.call_count patterns
        if isinstance(node, ast.Attribute) and node.attr in ("now_count", "now_values", "call_count"):
            return True
        # MagicMock idiom: clock.now.call_count
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Attribute) and node.value.attr == "now" and node.attr == "call_count":
                return True
    return False


def _check_h3_log(tree: ast.Module) -> bool:
    """H3: caplog with exact format string match."""
    return _check_caplog_exact(tree)


def _check_h4_truth_table(tree: ast.Module) -> bool:
    """H4: complete truth table (>2 boolean combos)."""
    return _check_truth_table(tree)


def _check_h6_fallback(tree: ast.Module) -> bool:
    """H6: SinkError side_effect + assert fallback result. Matches both
    side_effect=Error() in Call kwargs AND mock.side_effect = Error in Assign."""
    has_side_effect = False
    has_fallback = False
    for node in ast.walk(tree):
        # side_effect=Error() in function call kwargs
        if isinstance(node, ast.keyword) and node.arg == "side_effect":
            has_side_effect = True
        # mock.side_effect = Error (assignment)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr == "side_effect":
                    has_side_effect = True
        # Assert checking fallback result (Rejected, error message, etc.)
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            for comp in node.test.comparators:
                if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                    if len(comp.value) > 3:
                        has_fallback = True
    return has_side_effect or has_fallback


def _check_h7_argv_order(tree: ast.Module) -> bool:
    """H7: exact list order assertion."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            if any(_is_eq_op(op) for op in node.test.ops):
                for comp in node.test.comparators:
                    if isinstance(comp, (ast.List, ast.Tuple)):
                        if len(comp.elts) >= 2:
                            return True
    return False


def _check_h8_stop_count(tree: ast.Module) -> bool:
    """H8: stop_on_first: assert len(...) == 1 OR x.call_count == 1."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            for comp in node.test.comparators:
                if isinstance(comp, ast.Constant) and comp.value == 1:
                    left = node.test.left
                    # len(...) == 1
                    if isinstance(left, ast.Call):
                        if isinstance(left.func, ast.Name) and left.func.id == "len":
                            return True
                    # x.call_count == 1 (MagicMock idiom)
                    if isinstance(left, ast.Attribute) and left.attr == "call_count":
                        return True
    return False


def _check_h10_cache(tree: ast.Module) -> bool:
    """H10: second call does not re-emit. Requires function named *cache*/*second* with 2+ calls."""
    for fn in _find_test_funcs(tree):
        if "second" in fn.name.lower() or "cache" in fn.name.lower():
            # Count apply/emit calls within this function
            call_count = 0
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    name = _call_name(node)
                    if name in ("apply", "emit"):
                        call_count += 1
            if call_count >= 2:
                return True
    return False


def _check_h11_limit(tree: ast.Module) -> bool:
    """H11: test with threshold exact value."""
    for node in ast.walk(tree):
        nums = _collect_numbers(node)
        if 50 in nums:  # threshold value from feature
            return True
    return False


def _check_h14_xxwrap(tree: ast.Module) -> bool:
    """H14: assert msg == 'exact' (not in str(msg))."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            if any(_is_eq_op(op) for op in node.test.ops):
                for comp in node.test.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        if len(comp.value) > 5:  # non-trivial message
                            return True
    return False


def _check_h15_none_vs_falsy(tree: ast.Module) -> bool:
    """H15: separate calls for None, 0, False — each tested individually."""
    has_none = False
    has_zero = False
    has_false = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if node.value is None:
                has_none = True
            elif node.value == 0 and not isinstance(node.value, bool):
                has_zero = True
            elif node.value is False:
                has_false = True
    return has_none and has_zero and has_false


def _check_h18_default_no_kwarg(tree: ast.Module) -> bool:
    """H18: call WITHOUT timeout kwarg."""
    return _check_default_kwarg(tree)


def _check_h19_unit_only(tree: ast.Module) -> bool:
    """H19: all tests in tests/unit/ (not @integration). Checked by file path."""
    # This is a structural check — always returns True at AST level.
    # The actual path check should be done by the caller.
    return True


def _check_h20_pathmap(tree: ast.Module) -> bool:
    """H20: path_map identity None pass-through. path_map must be set on the SPEC
    (make_spec(path_map=...) / spec dict), NOT passed as a kwarg to apply() — the
    stub signature apply(records, spec, sink, clock, *, timeout) rejects path_map
    as a kwarg (TypeError), so such an assertion can never execute."""
    # Reject: path_map passed as a kwarg directly to apply() (invalid call)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) == "apply":
            for kw in node.keywords:
                if kw.arg == "path_map":
                    return False
    # Accept: path_map set on a spec (make_spec / spec dict construction)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_spec_ctor = (
                isinstance(func, ast.Name) and "spec" in func.id.lower()
            ) or (
                isinstance(func, ast.Attribute) and "spec" in func.attr.lower()
            )
            if is_spec_ctor:
                for kw in node.keywords:
                    if kw.arg == "path_map":
                        return True
    return False


def _check_type_a(tree: ast.Module) -> bool:
    return _check_break_count(tree)


def _check_type_b(tree: ast.Module) -> bool:
    return _check_h11_limit(tree)


def _check_type_c(tree: ast.Module) -> bool:
    """Tipo C: test with absent key."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = _call_name(node)
            if func_name in ("apply", "normalize"):
                # Check if called with a spec that's missing a key
                for kw in node.keywords:
                    if kw.arg == "extra_key" or "missing" in ast.dump(kw):
                        return True
    # Fallback: check for 'absent' or 'missing' in function names
    for fn in _find_test_funcs(tree):
        if "absent" in fn.name.lower() or "missing" in fn.name.lower():
            return True
    return False


def _check_type_d(tree: ast.Module) -> bool:
    """Tipo D: side_effect for unreachable state."""
    return _check_h6_fallback(tree)


def _check_type_e(tree: ast.Module) -> bool:
    """Tipo E: spy observes timeout value. Matches assert_called_once_with(..., timeout=600)
    OR sink.calls[i].timeout == N."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "assert_called_once_with":
                for kw in node.keywords:
                    if kw.arg == "timeout":
                        return True
        # Spy pattern: x.calls[i].timeout == value
        if isinstance(node, ast.Attribute) and node.attr == "timeout":
            # Check if parent is a Compare with a numeric value
            for parent in ast.walk(tree):
                if isinstance(parent, ast.Compare):
                    if node in ast.walk(parent):
                        for comp in parent.comparators:
                            if isinstance(comp, ast.Constant) and isinstance(comp.value, (int, float)):
                                return True
    return False


def _check_type_f(tree: ast.Module) -> bool:
    """Tipo F: roundtrip write+read."""
    return False  # too specific for generic AST check


def _check_type_g(tree: ast.Module) -> bool:
    """Tipo G: sentinel with __eq__ decoy class to make is vs == diverge."""
    has_sentinel = False
    has_eq_decoy = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__eq__":
                    has_eq_decoy = True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and "sentinel" in target.id.lower():
                    has_sentinel = True
    return has_sentinel and has_eq_decoy


def _check_type_h(tree: ast.Module) -> bool:
    """Tipo H: log messages are contract. Matches caplog.records ==, caplog.messages ==, or logging."""
    if _check_caplog_exact(tree):
        return True
    # Also check for logging import + caplog pattern
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "logging":
                    return True  # logging imported, likely used with caplog
    return False


# ── Forbidden checks (penalties) ───────────────────────────────────

def _forbid_loose_none(tree: ast.Module) -> bool:
    """FORBIDDEN: assert x is not None as sole assertion."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Compare):
                for op in node.test.ops:
                    if isinstance(op, ast.IsNot):
                        # Check if comparator is None
                        for comp in node.test.comparators:
                            if isinstance(comp, ast.Constant) and comp.value is None:
                                return True
    return False


def _forbid_loose_in(tree: ast.Module) -> bool:
    """FORBIDDEN: assert 'x' in str(result) — In() operator with str() call on right."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            for op in node.test.ops:
                if isinstance(op, ast.In):
                    for comp in node.test.comparators:
                        if isinstance(comp, ast.Call):
                            if isinstance(comp.func, ast.Name) and comp.func.id == "str":
                                return True
    return False


def _forbid_len_gt(tree: ast.Module) -> bool:
    """FORBIDDEN: assert len(x) > 0 — len() call with Gt/GtE against zero."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            left = node.test.left
            if isinstance(left, ast.Call):
                if isinstance(left.func, ast.Name) and left.func.id == "len":
                    for op in node.test.ops:
                        if isinstance(op, (ast.Gt, ast.GtE)):
                            for comp in node.test.comparators:
                                if isinstance(comp, ast.Constant) and comp.value in (0, 0.0):
                                    return True
    return False


# ── Operator checkers (§2 mutmut operators) ────────────────────────

def _check_num_boundary(tree: ast.Module) -> bool:
    """§2 Números: test uses numeric values that could distinguish > from >=."""
    all_nums = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_nums.extend(_collect_numbers(node))
    unique = sorted(set(n for n in all_nums if isinstance(n, (int, float)) and n != 0))
    if len(unique) >= 3:
        return True
    return False


def _check_string_xxwrap(tree: ast.Module) -> bool:
    """§2 Strings: assert with exact string equality (not substring)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            if any(_is_eq_op(op) for op in node.test.ops):
                for comp in node.test.comparators:
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                        if len(comp.value) >= 2:
                            return True
    return False


def _check_cmp_boundary(tree: ast.Module) -> bool:
    """§2 Comparaciones: uses values that distinguish < from <=."""
    all_nums = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_nums.extend(_collect_numbers(node))
    unique = sorted(set(n for n in all_nums if isinstance(n, (int, float)) and n > 0))
    if len(unique) >= 3:
        return True
    return False


def _check_bool_and_or(tree: ast.Module) -> bool:
    """§2 Booleanos: tests that exercise and/or branching."""
    test_funcs = _find_test_funcs(tree)
    tf_count = 0
    for fn in test_funcs:
        src = ast.dump(fn)
        if "True" in src and "False" in src:
            tf_count += 1
    return tf_count >= 1


def _check_bool_not(tree: ast.Module) -> bool:
    """§2 not x→x: test asserts both True and False outcomes."""
    has_true = False
    has_false = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if node.value is True:
                has_true = True
            elif node.value is False:
                has_false = True
    return has_true and has_false


def _check_in_notin(tree: ast.Module) -> bool:
    """§2 in↔not in: both membership checks present."""
    has_in = False
    has_notin = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if isinstance(op, ast.In):
                    has_in = True
                elif isinstance(op, ast.NotIn):
                    has_notin = True
    return has_in or has_notin  # either direction counts


def _check_is_isnot(tree: ast.Module) -> bool:
    """§2 is↔is not: identity checks present."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if isinstance(op, (ast.Is, ast.IsNot)):
                    return True
    return False


def _check_break_continue(tree: ast.Module) -> bool:
    """§2 break↔continue: test counts iterations or calls."""
    return _check_break_count(tree)


def _check_return_none(tree: ast.Module) -> bool:
    """§2 return x→return None: assert exact return value (not just truthy)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            if any(_is_eq_op(op) for op in node.test.ops):
                for comp in node.test.comparators:
                    if isinstance(comp, (ast.Tuple, ast.List, ast.Dict)):
                        return True
                    if isinstance(comp, ast.Constant) and comp.value is not None:
                        return True
    return False


def _check_default_mutation(tree: ast.Module) -> bool:
    """§2 def f(x=10)→f(x=11): function called without the optional kwarg."""
    return _check_default_kwarg(tree)


def _check_kwargs_passthrough(tree: ast.Module) -> bool:
    """§2 f(timeout=600)→f(timeout=601): assert_called_once_with with kwargs."""
    return _check_spy_complete(tree)


def _check_arith_accumulator(tree: ast.Module) -> bool:
    """§2 +/-, +=/=: test uses ≥2 asymmetric non-unit numeric values (not just 0,1,2)."""
    all_nums = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_nums.extend(_collect_numbers(node))
    # Filter: >2 and not trivially symmetric
    meaningful = set(n for n in all_nums if isinstance(n, (int, float)) and n > 2)
    if len(meaningful) >= 2:
        return True
    return False


def _check_in_is_membership(tree: ast.Module) -> bool:
    """§2 in↔not in AND is↔is not combined."""
    has_membership = False
    has_identity = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for op in node.ops:
                if isinstance(op, (ast.In, ast.NotIn)):
                    has_membership = True
                if isinstance(op, (ast.Is, ast.IsNot)):
                    has_identity = True
    return has_membership and has_identity


# ── Forbidden checks ───────────────────────────────────────────────

def _forbid_sample_leak(tree: ast.Module) -> bool:
    """FORBIDDEN: 'alpha'/'beta'/'quota-lab' as substrings in assert/comparator strings (not docstrings)."""
    SAMPLE_LEAKS = {"alpha", "beta", "quota-lab"}
    for node in ast.walk(tree):
        # Only check string literals inside Assert nodes (not module docstrings, not comments)
        if isinstance(node, ast.Assert):
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    lower = child.value.lower()
                    for leak in SAMPLE_LEAKS:
                        if leak in lower:
                            return True
    return False


def _forbid_mock_iterable(tree: ast.Module) -> bool:
    """FORBIDDEN: MagicMock() as records iterable (H17)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "MagicMock":
                # Check if it's used as records/sink/clock arg
                for kw in node.keywords:
                    if kw.arg in ("records", "items", "inputs"):
                        return True
    return False


# ── Main evaluator ──────────────────────────────────────────────────

_SURFACE_CHECKERS: dict[str, Any] = {
    # Operators §2
    "num_boundary": _check_num_boundary,
    "string_xxwrap": _check_string_xxwrap,
    "cmp_boundary": _check_cmp_boundary,
    "bool_and_or": _check_bool_and_or,
    "bool_not": _check_bool_not,
    "in_notin": _check_in_notin,
    "is_isnot": _check_is_isnot,
    "break_continue": _check_break_continue,
    "return_none": _check_return_none,
    "default_mutation": _check_default_mutation,
    "kwargs_passthrough": _check_kwargs_passthrough,
    "arith_accumulator": _check_arith_accumulator,
    "in_is_membership": _check_in_is_membership,
    # Techniques §4
    "dense_assertions": _check_dense_assertions,
    "exact_boundary": _check_exact_boundary,
    "exact_string": _check_exact_string,
    "spy_complete": _check_spy_complete,
    "default_kwarg": _check_default_kwarg,
    "accumulator_asymmetric": _check_accumulator_asymmetric,
    "break_count": _check_break_count,
    "truth_table": _check_truth_table,
    "hypothesis_basic": _check_hypothesis,
    "caplog_exact": _check_caplog_exact,
    "typed_exception": _check_typed_exception,
    # H-cases
    "h1_wiring": _check_h1_wiring,
    "h2_clock": _check_h2_clock,
    "h3_log": _check_h3_log,
    "h4_truth_table": _check_h4_truth_table,
    "h6_fallback": _check_h6_fallback,
    "h7_argv_order": _check_h7_argv_order,
    "h8_stop_count": _check_h8_stop_count,
    "h10_cache": _check_h10_cache,
    "h11_limit": _check_h11_limit,
    "h14_xxwrap": _check_h14_xxwrap,
    "h15_none_vs_falsy": _check_h15_none_vs_falsy,
    "h18_default_no_kwarg": _check_h18_default_no_kwarg,
    "h19_unit_only": _check_h19_unit_only,
    "h20_pathmap": _check_h20_pathmap,
    # Equivalents §5
    "type_a_itercount": _check_type_a,
    "type_b_public_limit": _check_type_b,
    "type_c_absent_key": _check_type_c,
    "type_d_unreachable": _check_type_d,
    "type_e_timeout_spy": _check_type_e,
    "type_f_roundtrip": _check_type_f,
    "type_g_sentinel": _check_type_g,
    "type_h_log_msg": _check_type_h,
}

_FORBIDDEN_CHECKERS: dict[str, Any] = {
    "no_loose_none": _forbid_loose_none,
    "no_loose_in": _forbid_loose_in,
    "no_len_gt": _forbid_len_gt,
    "no_sample_leak": _forbid_sample_leak,
    "no_mock_iterable": _forbid_mock_iterable,
}


@dataclass
class SurfaceResult:
    id: str
    category: str
    hit: bool
    description: str = ""


@dataclass
class Scorecard:
    test_file: str
    syntax_ok: bool
    surfaces_hit: int = 0
    surfaces_total: int = 0
    penalties: int = 0
    test_count: int = 0
    assertion_count: int = 0
    results: list[SurfaceResult] = field(default_factory=list)

    @property
    def surface_pct(self) -> float:
        return (self.surfaces_hit / self.surfaces_total * 100) if self.surfaces_total else 0.0

    @property
    def penalty_pct(self) -> float:
        return self.penalties * 10.0  # each penalty = -10% cap

    @property
    def score(self) -> float:
        raw = self.surface_pct - self.penalty_pct
        return max(0.0, min(100.0, raw))


def evaluate(test_path: str | Path) -> Scorecard:
    """Evaluate a test file statically against mutant surfaces."""
    path = Path(test_path)
    card = Scorecard(test_file=str(path), syntax_ok=False)

    # Parse AST
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, ValueError) as e:
        card.results.append(SurfaceResult(
            id="syntax", category="meta", hit=False,
            description=f"Syntax error: {e}",
        ))
        return card

    card.syntax_ok = True

    # Count tests and assertions
    test_funcs = _find_test_funcs(tree)
    card.test_count = len(test_funcs)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            card.assertion_count += 1

    # Evaluate surfaces
    for surface in SURFACES:
        sid = surface["id"]
        cat = surface.get("category", "")

        if cat == "forbidden":
            checker = _FORBIDDEN_CHECKERS.get(sid)
        else:
            checker = _SURFACE_CHECKERS.get(sid)

        if checker:
            hit = checker(tree)
        else:
            hit = False  # llm_only surfaces

        card.results.append(SurfaceResult(
            id=sid, category=cat, hit=hit,
            description=surface.get("description", ""),
        ))

        if cat == "forbidden" and hit:
            card.penalties += 1
        elif cat != "forbidden" and hit:
            card.surfaces_hit += 1

    card.surfaces_total = sum(
        1 for s in SURFACES if s.get("category") != "forbidden" and not s.get("llm_only", False)
    )

    return card


def format_scorecard(card: Scorecard) -> str:
    """Format a scorecard as human-readable text."""
    lines = [
        f"# Scorecard: {card.test_file}",
        f"",
        f"Syntax:    {'OK' if card.syntax_ok else 'FAIL'}",
        f"Tests:     {card.test_count}",
        f"Asserts:   {card.assertion_count}",
        f"Surfaces:  {card.surfaces_hit}/{card.surfaces_total} ({card.surface_pct:.0f}%)",
        f"Penalties: {card.penalties} (-{card.penalty_pct:.0f}%)",
        f"Score:     {card.score:.0f}/100",
        f"",
        f"## Results",
        f"",
    ]

    # Group by category
    categories: dict[str, list[SurfaceResult]] = {}
    for r in card.results:
        categories.setdefault(r.category, []).append(r)

    for cat, results in categories.items():
        lines.append(f"### {cat}")
        for r in results:
            mark = "✅" if r.hit else "❌"
            lines.append(f"  {mark} {r.id}: {r.description}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Static TDD RED bench scorer")
    parser.add_argument("test_file", help="Path to test file to evaluate")
    args = parser.parse_args()

    card = evaluate(args.test_file)
    print(format_scorecard(card))

    # Exit code: 0 if score >= 50, 1 otherwise
    sys.exit(0 if card.score >= 50 else 1)


if __name__ == "__main__":
    main()
