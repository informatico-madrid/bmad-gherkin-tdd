#!/usr/bin/env python3
"""run_pytest.py — Run visible (gold) and hidden tests against a sandbox impl.

Runs pytest in the sandbox for the gold tests, then runs the hidden suite
against the same impl in a temp copy. Returns structured results.

Usage:
    python -m agent_bench.green.eval.run_pytest --sandbox <path>
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "green-hard"
HIDDEN_DIR = Path(__file__).parent / "hidden"
GOLD_TEST = Path("tests") / "unit" / "test_green_hard.py"
HIDDEN_TEST = Path("test_heldout.py")


def _run_pytest_in_dir(test_path: Path, cwd: Path, timeout: int = 120) -> dict:
    """Run pytest on a single test file in a given directory."""
    # Use relative path from cwd to avoid path resolution issues
    try:
        rel_path = test_path.relative_to(cwd)
    except ValueError:
        rel_path = test_path
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(rel_path), "-q", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-3000:] if result.stdout else "",
            "stderr": result.stderr[-1000:] if result.stderr else "",
            "status": "pass" if result.returncode == 0 else "fail",
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "timeout", "status": "timeout"}


def run_gold(sandbox: Path) -> dict:
    """Run gold tests in the sandbox."""
    test_file = sandbox / GOLD_TEST
    if not test_file.exists():
        return {"status": "no_test_file", "pass": 0, "fail": 0, "error": "gold test missing"}

    r = _run_pytest_in_dir(test_file, sandbox)
    # Parse pass/fail counts from pytest output
    pass_count = 0
    fail_count = 0
    for line in r["stdout"].splitlines():
        if "passed" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "passed":
                    pass_count = int(parts[i - 1])
        if "failed" in line:
            parts = line.split()
            for i, p in enumerate(parts):
                if p == "failed":
                    fail_count = int(parts[i - 1])

    return {
        "status": r["status"],
        "pass": pass_count,
        "fail": fail_count,
        "returncode": r["returncode"],
    }


def run_hidden(sandbox: Path) -> dict:
    """Run hidden tests against the sandbox impl in a temp dir."""
    with tempfile.TemporaryDirectory(prefix="green_hidden_") as tmp:
        tmp_path = Path(tmp)

        # Copy impl from sandbox
        src_dir = sandbox / "src"
        if not src_dir.exists():
            return {"status": "no_impl", "pass": 0, "fail": 0, "error": "src/ missing"}

        shutil.copytree(src_dir, tmp_path / "src")

        # Copy conftest
        conftest = FIXTURE_DIR / "tests" / "conftest.py"
        if conftest.exists():
            shutil.copy(conftest, tmp_path / "conftest.py")

        # Copy hidden test
        hidden_test = HIDDEN_DIR / "test_heldout.py"
        shutil.copy(hidden_test, tmp_path / "test_heldout.py")

        # Create pytest.ini
        (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = src\n")

        r = _run_pytest_in_dir(tmp_path / "test_heldout.py", tmp_path)

        pass_count = 0
        fail_count = 0
        for line in r["stdout"].splitlines():
            if "passed" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "passed":
                        pass_count = int(parts[i - 1])
            if "failed" in line:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "failed":
                        fail_count = int(parts[i - 1])

        return {
            "status": r["status"],
            "pass": pass_count,
            "fail": fail_count,
            "returncode": r["returncode"],
        }


def main():
    parser = argparse.ArgumentParser(description="Run gold + hidden tests on a sandbox")
    parser.add_argument("--sandbox", required=True, type=Path, help="Sandbox directory")
    parser.add_argument("--json-out", type=Path, help="Write results JSON")
    args = parser.parse_args()

    if not args.sandbox.is_dir():
        raise SystemExit(f"Sandbox not found: {args.sandbox}")

    gold = run_gold(args.sandbox)
    hidden = run_hidden(args.sandbox)

    results = {"gold": gold, "hidden": hidden}

    if args.json_out:
        args.json_out.write_text(json.dumps(results, indent=2))
    else:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
