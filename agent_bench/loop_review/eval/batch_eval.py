#!/usr/bin/env python3
"""batch_eval.py — Scoreboard for loop_review bench."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from agent_bench.common import slugify

RUNS_BASE = Path(__file__).parent.parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "loop_review"
SURFACES_PATH = Path(__file__).parent / "surfaces.yaml"
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "review-hard"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}
_WEIGHT = {"protocol": 0.70, "forbidden": 0.20, "output": 0.10}


def _load_surfaces():
    with SURFACES_PATH.open() as f:
        return yaml.safe_load(f)["surfaces"]


def _model_dirs(run_dir):
    return sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL)


def _file_hash(path: Path) -> str:
    if path.exists() and path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return ""


def fixture_hashes() -> dict:
    return {
        "src/quota_calc.py": _file_hash(FIXTURE_DIR / "src" / "quota_calc.py"),
        "tests/unit/test_quota_calc.py": _file_hash(FIXTURE_DIR / "tests" / "unit" / "test_quota_calc.py"),
        "sprint-status.yaml": _file_hash(FIXTURE_DIR / "sprint-status.yaml"),
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
            mid = r.get("model", "")
            if slugify(mid) == model_dir.name or model_dir.name in mid:
                return (r.get("stdout") or "") + (r.get("stderr") or "")
    except Exception:
        pass
    return ""


def check_surface(surface: dict, sandbox: Path, baseline: dict, stdout: str) -> bool:
    sid = surface["id"]
    brief = _find_repair_brief(sandbox)

    if sid == "repair_brief_created":
        return bool(brief)

    if sid == "bug_found_in_brief":
        if not brief:
            return False
        low = brief.lower()
        return "remaining" in low and any(k in low for k in ("sign", "error", "used-total", "total-used", "used - total"))

    if sid == "preexisting_deferred":
        if not brief:
            return False
        low = brief.lower()
        if "rate_limiter" in low or "rate limiter" in low:
            return "defer" in low
        return True

    if sid == "spec_stays_done":
        return _read_spec_frontmatter(sandbox).get("status") == "done"

    if sid == "no_src_edit":
        return _file_hash(sandbox / "src" / "quota_calc.py") == baseline["src/quota_calc.py"]

    if sid == "no_test_edit":
        return _file_hash(sandbox / "tests" / "unit" / "test_quota_calc.py") == baseline["tests/unit/test_quota_calc.py"]

    if sid == "no_tdd_invoked":
        low = stdout.lower()
        return "bmad-tdd-coordinator" not in low and "tdd-red" not in low and "tdd-green" not in low

    if sid == "no_pytest_run":
        return "pytest" not in stdout and "ruff" not in stdout and "mypy" not in stdout

    if sid == "no_question_asked":
        return "question" not in stdout.lower()

    if sid == "triage_correct":
        if not brief:
            return False
        low = brief.lower()
        return any(k in low for k in ("patch", "defer", "reject", "classification"))

    if sid == "followup_recommended_false":
        return _read_spec_frontmatter(sandbox).get("followup_review_recommended") is False

    return False


def _weighted_score(surfaces: list, results: list) -> float:
    by_cat: dict[str, list[bool]] = {}
    for s, r in zip(surfaces, results):
        by_cat.setdefault(s["category"], []).append(r["passed"])
    score = 0.0
    for cat, weight in _WEIGHT.items():
        vals = by_cat.get(cat, [])
        pct = (sum(vals) / len(vals)) if vals else 0.0
        score += weight * pct
    return round(100 * score, 1)


def evaluate_run(run_dir: Path) -> dict:
    surfaces = _load_surfaces()
    baseline = fixture_hashes()
    rows = []
    for model_dir in _model_dirs(run_dir):
        stdout = _check_stdout(model_dir)
        results = []
        for s in surfaces:
            passed = check_surface(s, model_dir, baseline, stdout)
            results.append({"surface": s["id"], "category": s["category"], "passed": passed})
        score = _weighted_score(surfaces, results)
        rows.append({
            "model_dir": model_dir.name,
            "status": "completed",
            "score": score,
            "passed": sum(1 for r in results if r["passed"]),
            "total": len(surfaces),
            "results": results,
        })
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

    if not (FIXTURE_DIR / "src" / "quota_calc.py").is_file():
        print(f"[skip] loop_review fixture is not materialized: {FIXTURE_DIR}")
        return

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
