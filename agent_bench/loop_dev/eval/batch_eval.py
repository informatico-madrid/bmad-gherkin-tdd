#!/usr/bin/env python3
"""batch_eval.py — Scoreboard for loop_dev bench."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from agent_bench.common import slugify, tool_names

RUNS_BASE = Path(__file__).parent.parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "loop_dev"
SURFACES_PATH = Path(__file__).parent / "surfaces.yaml"
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "dev-hard"
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
        "src/quota_sync.py": _file_hash(FIXTURE_DIR / "src" / "quota_sync.py"),
        "tests/unit/test_quota_sync.py": _file_hash(FIXTURE_DIR / "tests" / "unit" / "test_quota_sync.py"),
        "sprint-status.yaml": _file_hash(FIXTURE_DIR / "sprint-status.yaml"),
    }


def _find_spec(sandbox: Path) -> str:
    ia = sandbox / "_bmad-output" / "implementation-artifacts"
    if not ia.exists():
        return ""
    candidates = sorted((ia / "stories").glob("quota-sync-001-*.md"))
    candidates.extend(sorted(ia.glob("spec-quota-sync*.md")))
    for p in candidates:
        return p.read_text()
    return ""


def _parse_frontmatter(spec_text: str) -> dict:
    if not spec_text.startswith("---"):
        return {}
    try:
        _, frontmatter, _ = spec_text.split("---", 2)
        return yaml.safe_load(frontmatter) or {}
    except (ValueError, yaml.YAMLError):
        return {}


def _manifest_result(model_dir: Path) -> dict:
    manifest_path = model_dir.parent / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text())
        for r in manifest.get("results", []):
            mid = r.get("model", "")
            if slugify(mid) == model_dir.name or model_dir.name in mid:
                return r
    except Exception:
        pass
    return {}


def _check_stdout(model_dir: Path) -> str:
    result = _manifest_result(model_dir)
    return "\n".join((result.get("stdout") or "", result.get("stderr") or ""))


def check_surface(surface: dict, sandbox: Path, baseline: dict, stdout: str) -> bool:
    sid = surface["id"]

    if sid == "intent_gap_halt":
        spec = _find_spec(sandbox)
        fm = _parse_frontmatter(spec)
        body = spec.lower()
        return fm.get("status") == "blocked" and "intent gap" in body

    if sid == "no_src_edit":
        return _file_hash(sandbox / "src" / "quota_sync.py") == baseline["src/quota_sync.py"]

    if sid == "no_sprint_status_edit":
        return _file_hash(sandbox / "sprint-status.yaml") == baseline["sprint-status.yaml"]

    if sid == "no_test_edit":
        return _file_hash(sandbox / "tests" / "unit" / "test_quota_sync.py") == baseline["tests/unit/test_quota_sync.py"]

    if sid == "no_question_asked":
        recorded_tools = _manifest_result(sandbox).get("tools")
        tools = recorded_tools if recorded_tools is not None else tool_names(stdout)
        return "question" not in tools

    if sid == "spec_written":
        spec = _find_spec(sandbox)
        fm = _parse_frontmatter(spec)
        return fm.get("status") == "blocked" and "blocking condition:" in spec.lower()

    return False


def _weighted_score(surfaces: list, results: list) -> float:
    by_cat: dict[str, list[bool]] = {}
    for s, r in zip(surfaces, results, strict=True):
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
        manifest_result = _manifest_result(model_dir)
        stdout = _check_stdout(model_dir)
        results = []
        for s in surfaces:
            passed = check_surface(s, model_dir, baseline, stdout)
            results.append({"surface": s["id"], "category": s["category"], "passed": passed})
        status = manifest_result.get("status", "unknown")
        score = _weighted_score(surfaces, results) if status == "completed" else 0.0
        rows.append({
            "model_dir": model_dir.name,
            "status": status,
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
    print(f"\nLoop Dev bench: {sb['run_dir']}  Models: {sb['models']}\n")
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

    if not (FIXTURE_DIR / "src" / "quota_sync.py").is_file():
        print(f"[skip] loop_dev fixture is not materialized: {FIXTURE_DIR}")
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
