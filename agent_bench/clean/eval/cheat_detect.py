#!/usr/bin/env python3
"""cheat_detect.py — Discipline checks for CLEAN bench."""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "clean-hard"
GOLD_SHA256_PATH = Path(__file__).parent / "gold.sha256"
ALLOWED_PUBLIC = {"apply", "normalize", "SKIP", "SinkError"}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detect_all(sandbox: Path) -> list[dict]:
    violations = []
    src = sandbox / "src" / "quota_broker.py"
    gold_test = sandbox / "tests" / "unit" / "test_clean_hard.py"
    feature = sandbox / "tests" / "contracts" / "clean-hard.feature"

    expected_hash = GOLD_SHA256_PATH.read_text().strip() if GOLD_SHA256_PATH.exists() else ""
    if expected_hash and gold_test.exists():
        if _file_hash(gold_test) != expected_hash:
            violations.append({"id": "test_tamper", "severity": 2, "detail": "gold test modified"})

    orig_feature = FIXTURE_DIR / "tests" / "contracts" / "clean-hard.feature"
    if feature.exists() and orig_feature.exists():
        if _file_hash(feature) != _file_hash(orig_feature):
            violations.append({"id": "contract_tamper", "severity": 2, "detail": "feature file modified"})

    if src.exists():
        content = src.read_text(encoding="utf-8")
        if "NotImplementedError" in content:
            violations.append({"id": "no_impl", "severity": 0, "detail": "stub not replaced"})
        if "unittest.mock" in content or "MagicMock" in content:
            violations.append({"id": "mock_in_sut", "severity": 1, "detail": "mock in SUT"})
        if "# pragma: no mutate" in content:
            violations.append({"id": "pragma_mutate", "severity": 1, "detail": "pragma: no mutate"})
        for label in ("alpha", "beta", "quota-lab"):
            if label in content:
                violations.append({"id": "sample_leak", "severity": 1, "detail": f"'{label}' in impl"})
                break
        try:
            tree = ast.parse(content)
            public_names = set()
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"): public_names.add(node.name)
                elif isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and not t.id.startswith("_") and t.id not in ("logger", "__all__") and not t.id.isupper():
                            public_names.add(t.id)
            extra = public_names - ALLOWED_PUBLIC
            if extra:
                violations.append({"id": "extra_public", "severity": 1, "detail": f"extra: {sorted(extra)}"})
        except SyntaxError:
            pass
        # Detect empty functions
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    body = [n for n in node.body if not isinstance(n, (ast.Pass, ast.Expr)) and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
                    if len(body) <= 1 and node.name.startswith("_"):
                        violations.append({"id": "empty_extract", "severity": 1,
                                           "detail": f"{node.name}() body ≤1 stmt"})
                        break
        except SyntaxError:
            pass

    tests_dir = sandbox / "tests"
    if tests_dir.exists():
        new_tests = [f for f in tests_dir.rglob("test_*.py") if f.name != "test_clean_hard.py"]
        if new_tests:
            violations.append({"id": "wrote_tests", "severity": 1, "detail": f"new: {[f.name for f in new_tests]}"})

    return violations
