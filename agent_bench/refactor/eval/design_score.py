"""Design delta vs REFACTOR seed. Doing nothing must not score like a real refactor."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _complexity(fn: ast.FunctionDef) -> int:
    c = 1
    for n in ast.walk(fn):
        if isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
            c += 1
        if isinstance(n, ast.BoolOp):
            c += len(n.values) - 1
    return c


def _real_helpers(tree: ast.Module) -> list[str]:
    names = []
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("_"):
            continue
        body = [
            s
            for s in node.body
            if not isinstance(s, ast.Pass)
            and not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
        ]
        if len(body) >= 3:
            names.append(node.name)
    return names


def _apply_cc(tree: ast.Module) -> int:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "apply":
            return _complexity(node)
    return 99


def metrics(src: Path) -> dict[str, Any]:
    tree = ast.parse(src.read_text(encoding="utf-8"))
    helpers = _real_helpers(tree)
    return {
        "helpers": helpers,
        "n_helpers": len(helpers),
        "apply_cc": _apply_cc(tree),
    }


def design_pct(impl: Path, seed: Path) -> dict[str, Any]:
    a = metrics(impl)
    b = metrics(seed)
    helper_gain = max(0, a["n_helpers"] - b["n_helpers"])
    cc_drop = max(0, b["apply_cc"] - a["apply_cc"])
    shells = 0
    tree = ast.parse(impl.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_"):
            body = [
                s for s in node.body
                if not isinstance(s, ast.Pass)
                and not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
            ]
            if 0 < len(body) <= 2:
                shells += 1
    pct = min(100.0, 30.0 + 18.0 * helper_gain + 12.0 * cc_drop - 10.0 * shells)
    pct = max(0.0, pct)
    if a["n_helpers"] == b["n_helpers"] and a["apply_cc"] >= b["apply_cc"] and shells == 0:
        pct = min(pct, 30.0)
    return {
        "pct": round(pct, 1),
        "impl": a,
        "seed": b,
        "helper_gain": helper_gain,
        "cc_drop": cc_drop,
    }
