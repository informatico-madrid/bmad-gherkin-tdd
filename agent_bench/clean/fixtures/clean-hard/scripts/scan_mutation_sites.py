"""Count approximate Python mutation sites without running mutation tests."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

THRESHOLD = 100


class MutationSiteVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.count = 0

    def visit_Compare(self, node: ast.Compare) -> None:
        self.count += len(node.ops)
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.count += len(node.values) - 1
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        self.count += 1
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        self.count += 1
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, (bool, int, float, type(None))):
            self.count += 1
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.count += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.count += 1
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.count += len(node.decorator_list)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.count += len(node.decorator_list)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.count += len(node.decorator_list)
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:
        self.count += 1
        self.generic_visit(node)


def scan_file(path: Path) -> int:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return 0
    visitor = MutationSiteVisitor()
    visitor.visit(tree)
    return visitor.count


def python_files(paths: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files.add(path)
        elif path.is_dir():
            files.update(path.rglob("*.py"))
    return sorted(files)


def main() -> int:
    files = python_files([Path(arg) for arg in sys.argv[1:]] or [Path("src")])
    counts = {str(path): scan_file(path) for path in files}
    print(json.dumps(counts, indent=2))
    return 1 if any(count > THRESHOLD for count in counts.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
