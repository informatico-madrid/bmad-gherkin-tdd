from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _copy_tools(project: Path) -> Path:
    scripts = project / "_bmad" / "gherkin-tdd" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("cleaner_gate.py", "principles.py", "scan_mutation_sites.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    return scripts / "cleaner_gate.py"


def test_cleaner_runs_without_harness_quality_gate_dependency(tmp_path: Path) -> None:
    cleaner = _copy_tools(tmp_path)
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir()
    source.write_text("def add(left: int, right: int) -> int:\n    return left + right\n")

    result = subprocess.run(
        [sys.executable, str(cleaner), str(source)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["overall"] == "PASS"
    assert payload["scoped_files"] == 1
    assert list(payload["checks"]) == ["kiss", "dry", "yagni", "lod", "coi", "scan_mutation_sites"]


def test_cleaner_reports_yagni_details_for_exact_file_scope(tmp_path: Path) -> None:
    cleaner = _copy_tools(tmp_path)
    source = tmp_path / "src" / "sample.py"
    sibling = tmp_path / "src" / "unrelated.py"
    source.parent.mkdir()
    source.write_text("import os\n\ndef answer() -> int:\n    return 42\n")
    sibling.write_text("import sys\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(cleaner), str(source)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["checks"]["yagni"] == {
        "status": "FAIL",
        "violations": 1,
        "details": [{"module": "os", "alias": "os", "lineno": 1, "file": "src/sample.py"}],
    }
