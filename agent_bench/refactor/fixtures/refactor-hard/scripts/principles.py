"""Small, dependency-free structural checks used by the CLEAN phase."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


class Visitor(ast.NodeVisitor):
    def __init__(self, file: Path) -> None:
        self.file = file
        self.functions: list[dict[str, Any]] = []
        self.classes: list[dict[str, Any]] = []
        self.imports: list[dict[str, Any]] = []
        self.used_names: set[str] = set()
        self.current_function: dict[str, Any] | None = None
        self.nesting = 0
        self.max_nesting = 0

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(
                {
                    "module": alias.name,
                    "alias": alias.asname or alias.name.split(".")[0],
                    "lineno": node.lineno,
                    "file": str(self.file),
                }
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "__future__":
            return
        for alias in node.names:
            self.imports.append(
                {
                    "module": f"{node.module}.{alias.name}",
                    "alias": alias.asname or alias.name,
                    "lineno": node.lineno,
                    "file": str(self.file),
                }
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self.used_names.add(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous = self.current_function
        previous_nesting = self.nesting
        previous_max = self.max_nesting
        self.current_function = {
            "file": str(self.file),
            "name": node.name,
            "lineno": node.lineno,
            "arity": len([arg for arg in node.args.args if arg.arg not in ("self", "cls")]),
            "complexity": 1,
            "max_nesting": 0,
        }
        self.nesting = 0
        self.max_nesting = 0
        self.generic_visit(node)
        self.current_function["max_nesting"] = self.max_nesting
        self.functions.append(self.current_function)
        self.current_function = previous
        self.nesting = previous_nesting
        self.max_nesting = previous_max

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases = [base.id for base in node.bases if isinstance(base, ast.Name)]
        self.classes.append(
            {"file": str(self.file), "name": node.name, "lineno": node.lineno, "bases": bases}
        )
        self.generic_visit(node)

    def _branch(self, node: ast.AST) -> None:
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        if self.current_function:
            self.current_function["complexity"] += 1
        self.generic_visit(node)
        self.nesting -= 1

    visit_If = _branch
    visit_For = _branch
    visit_While = _branch
    visit_ExceptHandler = _branch

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if self.current_function:
            self.current_function["complexity"] += len(node.values) - 1
        self.generic_visit(node)


def _visitors(files: list[Path]) -> list[Visitor]:
    visitors = []
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        visitor = Visitor(path)
        visitor.visit(tree)
        visitors.append(visitor)
    return visitors


def check_kiss(files: list[Path]) -> dict[str, Any]:
    violations = []
    for visitor in _visitors(files):
        for function in visitor.functions:
            for key, maximum in (("complexity", 10), ("max_nesting", 4), ("arity", 5)):
                if function[key] > maximum:
                    violations.append(
                        {
                            "file": function["file"],
                            "function": function["name"],
                            "lineno": function["lineno"],
                            "issue": f"{key}={function[key]} > {maximum}",
                        }
                    )
    return _result(violations)


def check_dry(files: list[Path]) -> dict[str, Any]:
    seen: dict[str, tuple[str, int]] = {}
    duplicates = []
    for path in files:
        lines = [
            line.rstrip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        for index in range(max(0, len(lines) - 5)):
            block = "\n".join(lines[index : index + 6])
            if len(block) <= 40:
                continue
            prior = seen.get(block)
            if prior and prior[0] != str(path):
                duplicates.append(
                    {
                        "file1": prior[0],
                        "line1": prior[1],
                        "file2": str(path),
                        "line2": index + 1,
                        "block_preview": block[:80],
                    }
                )
            else:
                seen[block] = (str(path), index + 1)
    return _result(duplicates)


def check_yagni(files: list[Path]) -> dict[str, Any]:
    unused = []
    for visitor in _visitors(files):
        unused.extend(item for item in visitor.imports if item["alias"] not in visitor.used_names)
    return _result(unused)


def check_lod(files: list[Path]) -> dict[str, Any]:
    violations = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            depth = 1
            current = node.value
            while isinstance(current, ast.Attribute):
                depth += 1
                current = current.value
            if depth > 3:
                violations.append({"file": str(path), "lineno": node.lineno, "chain_length": depth})
    return _result(violations)


def check_coi(files: list[Path]) -> dict[str, Any]:
    classes = [item for visitor in _visitors(files) for item in visitor.classes]
    class_map = {item["name"]: item for item in classes}

    def depth(name: str, visited: set[str]) -> int:
        if name in visited or name not in class_map:
            return 0
        bases = class_map[name]["bases"]
        return 0 if not bases else 1 + max(depth(base, visited | {name}) for base in bases)

    violations = [
        {**item, "inheritance_depth": depth(item["name"], set())}
        for item in classes
        if depth(item["name"], set()) > 2
    ]
    return _result(violations)


def _result(details: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "FAIL" if details else "PASS",
        "violations": len(details),
        "details": details[:20],
    }
