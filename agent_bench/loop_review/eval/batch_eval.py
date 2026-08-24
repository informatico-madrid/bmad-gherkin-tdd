#!/usr/bin/env python3
"""batch_eval.py — Scoreboard for loop_review bench."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

RUNS_BASE = Path(__file__).parent.parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "loop_review"
SURFACES_PATH = Path(__file__).parent / "surfaces.yaml"
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "review-hard"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


def _load_surfaces():
    with SURFACES_PATH.open() as f:
        return yaml.safe_load(f)["surfaces"]


def _model_dirs(run_dir):
    return sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL)


def _file_hash(path: Path) -> str:
    if path.exists():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return ""


def _baseline_hashes(sandbox: Path) -> dict:
    return {
        "src/quota_calc.py": _file_hash(sandbox / "src" / "quota_calc.py"),
        "tests/unit/test_quota_calc.py": _file_hash(sandbox / "tests" / "unit" / "test_quota_calc.py"),
        "sprint-status.yaml": _file_hash(sandbox / "sprint-status.yaml"),
    }


def _find_repair_brief(sandbox: Path) -> str:
    ia = sandbox / "_bmad-output" / "implementation-artifacts"
    if not ia.exists():
        return ""
    for f in sorted(ia.glob("repair-brief-*.md")):
        return f.read_text()
    return ""


def _read_spec_frontmatter(sandbox: Path) -> dict:
    spec = sandbox / "_bmad-output" / "implementation-artifacts" / "spec-quota-calc.md"
    if not spec.exists():
        return {}
    content = spec.read_text()
    if "---" in content:
        parts = content.split("---")
        if len(parts) >= 3:
            try:
                return yaml.safe_load(parts[1]) or {}
            except Exception:
                return {}
    return {}


def _check_stdout(model_dir: Path) -> str:
    manifest_path = model_dir.parent / "manifest.json"
    if not manifest_path.exists():
        return ""
    try:
        manifest = json.loads(manifest_path.read_text())
        for r in manifest.get("results", []):
            if model_dir.name in r.get("model", ""):
                return r.get("stdout", "") + r.get("stderr", "")
    except Exception:
        pass
    return ""


def _check_surface(surface: dict, sandbox: Path, baseline: dict, stdout: str) -> bool:
    sid = surface["id"]

    if sid == "repair_brief_created":
        return bool(_find_repair_brief(sandbox))

    if sid == "bug_found_in_brief":
        brief = _find_repair_brief(sandbox)
        brief_lower = brief.lower()
        return "remaining" in brief_lower and ("sign" in brief_lower or "error" in brief_lower or "used-total" in brief_lower or "total-used" in brief_lower)

    if sid == "preexisting_deferred":
        brief = _find_repair_brief(sandbox)
        brief_lower = brief.lower()
        # rate_limiter should NOT be in patch findings
        if "rate_limiter" in brief_lower or "rate limiter" in brief_lower:
            # Check if it's classified as patch (bad) vs defer (ok)
            return "defer" in brief_lower and "rate_limit" in brief_lower
        return True  # not mentioned = ok (deferred by omission)

    if sid == "spec_stays_done":
        fm = _read_spec_frontmatter(sandbox)
        return fm.get("status") == "done"

    if sid == "no_src_edit":
        return _file_hash(sandbox / "src" / "quota_calc.py") == baseline["src/quota_calc.py"]

    if sid == "no_test_edit":
        return _file_hash(sandbox / "tests" / "unit" / "test_quota_calc.py") == baseline["tests/unit/test_quota_calc.py"]

    if sid == "no_tdd_invoked":
        return "bmad-tdd-coordinator" not in stdout and "tdd-red" not in stdout and "tdd-green" not in stdout

    if sid == "no_pytest_run":
        return "pytest" not in stdout and "ruff" not in stdout and "mypy" not in stdout

    if sid == "no_question_asked":
        return "question" not in stdout.lower()

    if sid == "triage_correct":
        brief = _find_repair_brief(sandbox)
        return "patch" in brief.lower() or "defer" in brief.lower() or "reject" in brief.lower()

    if sid == "followup_recommended_false":
        fm = _read_spec_frontmatter(sandbox)
        return fm.get("followup_review_recommended") is False

    return False


def evaluate_run(run_dir: Path) -> dict:
    surfaces = _load_surfaces()
    rows = []
    for model_dir in _model_dirs(run_dir):
        row = {"model_dir": model_dir.name}
        sandbox = model_dir
        baseline = _baseline_hashes(sandbox)
        stdout = _check_stdout(model_dir)

        results = []
        for s in surfaces:
            passed = _check_surface(s, sandbox, baseline, stdout)
            results.append({"surface": s["id"], "passed": passed})

        passed_count = sum(1 for r in results if r["passed"])
        total = len(surfaces)
        score = round(100 * passed_count / total, 1) if total else 0

        row.update({
            "status": "completed",
            "score": score,
            "passed": passed_count,
            "total": total,
            "results": results,
        })
        rows.append(row)

    rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return {"run_dir": str(run_dir), "models": len(rows), "rows": rows}


def print_table(sb):
    rows = sb["rows"]
    print(f"\nLoop Review bench: {sb['run_dir']}  Models: {sb['models']}\n")
    h = f"{'#':<3} {'model':<40} {'score':>6} {'pass':>5} {'total':>5} {'status':<12}"
    print(h)
    print("-" * len(h))
    for r in rows:
        print(f"{r['rank']:<3} {r['model_dir']:<40} {r.get('score',0):>6} "
              f"{r.get('passed',0):>5} {r.get('total',0):>5} {r.get('status','?'):<12}")
    print()


def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--latest", action="store_true")
    g.add_argument("--run-dir", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.run_dir:
        run_dir = args.run_dir
    else:
        runs = sorted((d for d in RUNS_BASE.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True) if RUNS_BASE.exists() else []
        if not runs:
            raise SystemExit(f"No runs under {RUNS_BASE}")
        run_dir = runs[0]
    sb = evaluate_run(run_dir)
    out = args.json_out or (run_dir / "scoreboard.json")
    out.write_text(json.dumps(sb, indent=2))
    print_table(sb)
    print(f"Scoreboard: {out}")


if __name__ == "__main__":
    main()
