"""Run dependency-free structural checks over exactly the supplied Python files."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from principles import check_coi, check_dry, check_kiss, check_lod, check_yagni
from scan_mutation_sites import THRESHOLD, python_files, scan_file


def main() -> int:
    files = python_files([Path(arg) for arg in sys.argv[1:]] or [Path("src")])
    if not files:
        print(json.dumps({"error": "no .py files found"}, indent=2))
        return 1

    root = Path.cwd().resolve()
    files = [
        path.resolve().relative_to(root) if path.resolve().is_relative_to(root) else path
        for path in files
    ]
    parse_errors = []
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), str(path))
        except (SyntaxError, UnicodeDecodeError) as error:
            parse_errors.append(
                {
                    "file": str(path),
                    "lineno": getattr(error, "lineno", None),
                    "offset": getattr(error, "offset", None),
                    "error": getattr(error, "msg", str(error)),
                }
            )
    if parse_errors:
        print(
            json.dumps(
                {
                    "overall": "FAIL",
                    "failed_checks": 1,
                    "checks": {
                        "parse": {
                            "status": "FAIL",
                            "violations": len(parse_errors),
                            "details": parse_errors,
                        }
                    },
                    "scoped_files": len(files),
                },
                indent=2,
            )
        )
        return 1
    checks = {
        "kiss": check_kiss(files),
        "dry": check_dry(files),
        "yagni": check_yagni(files),
        "lod": check_lod(files),
        "coi": check_coi(files),
    }
    flagged = [
        {"file": str(path), "sites": sites, "issue": f"{sites} > {THRESHOLD} mutation sites"}
        for path in files
        if (sites := scan_file(path)) > THRESHOLD
    ]
    checks["scan_mutation_sites"] = {
        "status": "FAIL" if flagged else "PASS",
        "violations": len(flagged),
        "details": flagged,
    }
    failed = sum(check["status"] != "PASS" for check in checks.values())
    print(
        json.dumps(
            {
                "overall": "FAIL" if failed else "PASS",
                "failed_checks": failed,
                "checks": checks,
                "scoped_files": len(files),
            },
            indent=2,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
