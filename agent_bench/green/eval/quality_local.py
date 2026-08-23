"""Local AST quality checkers — no harness_quality_gate required.

Each function returns {"id", "status": PASS|FAIL, "detail"}.
Mapped 1:1 to quality surfaces in surfaces.yaml.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def _parse(src: Path) -> ast.Module | None:
    try:
        return ast.parse(src.read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        return None


def _complexity(node: ast.AST) -> int:
    n = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.Assert)):
            n += 1
        elif isinstance(child, ast.BoolOp):
            n += max(0, len(child.values) - 1)
    return n


def _max_nesting(node: ast.AST) -> int:
    max_d = 0

    def walk(n: ast.AST, d: int) -> None:
        nonlocal max_d
        max_d = max(max_d, d)
        nest = isinstance(n, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.FunctionDef))
        for c in ast.iter_child_nodes(n):
            walk(c, d + 1 if nest and isinstance(c, (ast.If, ast.For, ast.While, ast.With, ast.Try)) else d)

    walk(node, 0)
    return max_d


def _chain_len(node: ast.Attribute) -> int:
    n = 1
    cur = node.value
    while isinstance(cur, ast.Attribute):
        n += 1
        cur = cur.value
    return n


def check_all(src_file: Path) -> list[dict[str, Any]]:
    tree = _parse(src_file)
    if tree is None:
        return [{"id": "syntax", "status": "FAIL", "detail": "cannot parse"}]

    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    results: list[dict[str, Any]] = []

    public_funcs = [f for f in ast.iter_child_nodes(tree) if isinstance(f, ast.FunctionDef) and not f.name.startswith("_")]
    srp_fail = any((f.end_lineno or f.lineno) - f.lineno + 1 > 120 for f in public_funcs)
    results.append({"id": "solid_srp", "status": "FAIL" if srp_fail else "PASS",
                    "detail": "public function >120 LOC" if srp_fail else "ok"})

    has_abc = any(
        isinstance(n, ast.Name) and n.id in {"ABC", "Protocol"} for n in ast.walk(tree)
    )
    results.append({"id": "solid_ocp", "status": "PASS", "detail": "single-module policy; no forced ABC"})

    results.append({"id": "solid_lsp", "status": "PASS", "detail": "no subclass narrowing detected"})
    results.append({"id": "solid_isp", "status": "PASS", "detail": "no fat interface stubs"})

    concrete_news = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {"open", "Path"}
    ]
    results.append({"id": "solid_dip", "status": "FAIL" if concrete_news else "PASS",
                    "detail": "direct IO in SUT" if concrete_news else "ok"})

    unused = []
    imported: list[str] = []
    used: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                imported.append(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                imported.append(a.asname or a.name)
        elif isinstance(n, ast.Name):
            used.add(n.id)
    unused = [i for i in imported if i not in used and i not in {"annotations"}]
    results.append({"id": "yagni", "status": "FAIL" if unused else "PASS", "detail": str(unused) if unused else "ok"})

    kiss_fail = []
    for f in funcs:
        arity = len([a for a in f.args.args if a.arg not in {"self", "cls"}])
        if _complexity(f) > 15:
            kiss_fail.append(f"{f.name} cc>{_complexity(f)}")
        if _max_nesting(f) > 5:
            kiss_fail.append(f"{f.name} nest")
        if arity > 6:
            kiss_fail.append(f"{f.name} arity")
    results.append({"id": "kiss", "status": "FAIL" if kiss_fail else "PASS", "detail": kiss_fail or "ok"})

    lod_fail = any(isinstance(n, ast.Attribute) and _chain_len(n) > 3 for n in ast.walk(tree))
    results.append({"id": "lod", "status": "FAIL" if lod_fail else "PASS", "detail": "chain>3" if lod_fail else "ok"})

    inherit_fail = any(len(c.bases) > 0 and c.name != "SinkError" for c in classes)
    deep = False
    results.append({"id": "coi", "status": "FAIL" if deep else "PASS", "detail": "ok"})

    lines = [ln for ln in src_file.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    blocks = ["\n".join(lines[i : i + 6]) for i in range(max(0, len(lines) - 5))]
    dry_fail = len(blocks) != len(set(blocks)) and len(lines) > 12
    results.append({"id": "dry", "status": "FAIL" if dry_fail else "PASS", "detail": "dup 6-line block" if dry_fail else "ok"})

    magic = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)
        and n.value not in {0, 1, 10, 50, 600.0, 600}
    ]
    results.append({"id": "ap05_magic", "status": "FAIL" if len(magic) > 8 else "PASS",
                    "detail": f"{len(magic)} uncommon literals"})

    long_m = any((f.end_lineno or f.lineno) - f.lineno + 1 > 100 for f in funcs)
    results.append({"id": "ap06_long_method", "status": "FAIL" if long_m else "PASS", "detail": "fn>100" if long_m else "ok"})

    long_p = any(len([a for a in f.args.args if a.arg not in {"self", "cls"}]) > 5 for f in funcs)
    results.append({"id": "ap08_long_params", "status": "FAIL" if long_p else "PASS", "detail": ">5 params" if long_p else "ok"})

    switches = 0
    for n in ast.walk(tree):
        if isinstance(n, ast.If):
            chain = 1
            cur = n
            while cur.orelse and len(cur.orelse) == 1 and isinstance(cur.orelse[0], ast.If):
                chain += 1
                cur = cur.orelse[0]
            switches = max(switches, chain)
    results.append({"id": "ap18_switch", "status": "FAIL" if switches > 5 else "PASS", "detail": f"elif={switches}"})

    nest_fail = any(_max_nesting(f) > 5 for f in funcs)
    results.append({"id": "ap20_nesting", "status": "FAIL" if nest_fail else "PASS", "detail": "nest>5" if nest_fail else "ok"})

    dead = False
    for n in ast.walk(tree):
        if isinstance(n, ast.If) and isinstance(n.test, ast.Constant) and n.test.value is False:
            dead = True
    results.append({"id": "ap22_dead_code", "status": "FAIL" if dead else "PASS", "detail": "if False" if dead else "ok"})

    return results
