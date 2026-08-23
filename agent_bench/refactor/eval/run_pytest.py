#!/usr/bin/env python3
"""run_pytest.py — Run visible (gold) and hidden tests against a sandbox impl."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "refactor-hard"
HIDDEN_DIR = Path(__file__).parent / "hidden"
GOLD_TEST = Path("tests") / "unit" / "test_refactor_hard.py"
HIDDEN_TEST = Path("test_heldout.py")


def _run_pytest_in_dir(test_path: Path, cwd: Path, timeout: int = 120) -> dict:
    try:
        rel_path = test_path.relative_to(cwd)
    except ValueError:
        rel_path = test_path
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(rel_path), "-q", "--tb=short"],
            capture_output=True, text=True, timeout=timeout, cwd=str(cwd),
        )
        return {"returncode": result.returncode, "stdout": result.stdout[-3000:] or "",
                "stderr": result.stderr[-1000:] or "", "status": "pass" if result.returncode == 0 else "fail"}
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "timeout", "status": "timeout"}


def _parse_counts(stdout: str) -> tuple[int, int]:
    pass_count = fail_count = 0
    for line in stdout.splitlines():
        tok = line.replace(",", " ").split()
        for i, p in enumerate(tok):
            if p == "passed" and i > 0 and tok[i - 1].isdigit():
                pass_count = int(tok[i - 1])
            if p == "failed" and i > 0 and tok[i - 1].isdigit():
                fail_count = int(tok[i - 1])
    return pass_count, fail_count


def run_gold(sandbox: Path) -> dict:
    test_file = sandbox / GOLD_TEST
    if not test_file.exists():
        return {"status": "no_test_file", "pass": 0, "fail": 0, "error": "gold test missing"}
    r = _run_pytest_in_dir(test_file, sandbox)
    p, f = _parse_counts(r["stdout"])
    return {"status": r["status"], "pass": p, "fail": f, "returncode": r["returncode"]}


def run_hidden(sandbox: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="clean_hidden_") as tmp:
        tmp_path = Path(tmp)
        src_dir = sandbox / "src"
        if not src_dir.exists():
            return {"status": "no_impl", "pass": 0, "fail": 0, "error": "src/ missing"}
        shutil.copytree(src_dir, tmp_path / "src")
        for name in ("test_heldout.py", "test_heldout_hard.py"):
            src_t = HIDDEN_DIR / name
            if src_t.exists():
                shutil.copy(src_t, tmp_path / name)
        shutil.copy(FIXTURE_DIR / "tests" / "conftest.py", tmp_path / "conftest.py")
        (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = src\n")
        r = _run_pytest_in_dir(tmp_path, tmp_path)
        p, f = _parse_counts(r["stdout"])
        return {"status": r["status"], "pass": p, "fail": f, "returncode": r["returncode"]}


def run_cleaner_gate(sandbox: Path) -> dict:
    src = sandbox / "src" / "quota_broker.py"
    if not src.exists():
        return {"status": "no_impl", "overall": "FAIL", "checks": {}}
    scripts_dir = sandbox / "scripts"
    if not scripts_dir.exists():
        scripts_dir = FIXTURE_DIR / "scripts"
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(scripts_dir.resolve()) + ":" + env.get("PYTHONPATH", "")
    try:
        result = subprocess.run(
            [sys.executable, str((scripts_dir / "cleaner_gate.py").resolve()), str(src.resolve())],
            capture_output=True, text=True, timeout=30,
            cwd=str(sandbox.resolve()), env=env,
        )
        data = json.loads(result.stdout) if result.stdout.strip() else {"overall": "FAIL"}
        return data
    except Exception as e:
        return {"overall": "ERROR", "error": str(e)}
