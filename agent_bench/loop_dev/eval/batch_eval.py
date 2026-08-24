#!/usr/bin/env python3
"""batch_eval.py — Scoreboard for loop_dev bench."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import yaml

RUNS_BASE = Path(__file__).parent.parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "loop_dev"
SURFACES_PATH = Path(__file__).parent / "surfaces.yaml"
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "dev-hard"
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
    """Hash files that must NOT change."""
    return {
        "src/quota_sync.py": _file_hash(sandbox / "src" / "quota_sync.py"),
        "tests/unit/test_quota_sync.py": _file_hash(sandbox / "tests" / "unit" / "test_quota_sync.py"),
        "sprint-status.yaml": _file_hash(sandbox / "sprint-status.yaml"),
    }


def _find_spec(sandbox: Path) -> str:
    """Find the spec file and read it."""
    for name in ["spec-quota-sync.md", "spec-quota-sync-final.md"]:
        p = sandbox / "_bmad-output" / "implementation-artifacts" / name
        if p.exists():
            return p.read_text()
    return ""


def _parse_frontmatter(spec_text: str) -> dict:
    """Parse YAML frontmatter from a markdown file."""
    if "---" not in spec_text:
        return {}
    parts = spec_text.split("---")
    if len(parts) >= 3:
        try:
            return yaml.safe_load(parts[1]) or {}
        except Exception:
            return {}
    return {}


def _find_marker(sandbox: Path) -> str:
    """Find any result marker under implementation-artifacts."""
    ia = sandbox / "_bmad-output" / "implementation-artifacts"
    if not ia.exists():
        return ""
    for f in sorted(ia.glob("bmad-build-auto-result-*.md")):
        return f.read_text()
    for f in sorted(ia.glob("*.md")):
        if f.name.startswith("spec-") or f.name == "stories.yaml" or f.name == "SPEC.md":
            continue
        return f.read_text()
    return ""


def _check_stdout(model_dir: Path) -> str:
    """Read stdout/stderr from the manifest for this model."""
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
    """Check a single surface against the sandbox state."""
    sid = surface["id"]
    check = surface["check"]

    if sid == "intent_gap_halt":
        spec = _find_spec(sandbox)
        fm = _parse_frontmatter(spec)
        bc = str(fm.get("blocking_condition", "")).lower()
        return fm.get("status") == "blocked" and "intent gap" in bc

    if sid == "dirty_tree_halt":
        spec = _find_spec(sandbox)
        fm = _parse_frontmatter(spec)
        bc = str(fm.get("blocking_condition", "")).lower()
        return fm.get("status") == "blocked" and "dirty" in bc

    if sid == "no_src_edit":
        return _file_hash(sandbox / "src" / "quota_sync.py") == baseline["src/quota_sync.py"]

    if sid == "no_sprint_status_edit":
        return _file_hash(sandbox / "sprint-status.yaml") == baseline["sprint-status.yaml"]

    if sid == "no_test_edit":
        return _file_hash(sandbox / "tests" / "unit" / "test_quota_sync.py") == baseline["tests/unit/test_quota_sync.py"]

    if sid == "no_question_asked":
        return "question" not in stdout.lower() or "question" not in check

    if sid == "marker_written":
        marker = _find_marker(sandbox)
        fm = _parse_frontmatter(marker)
        return bool(fm.get("status"))

    if sid == "spec_written":
        spec = _find_spec(sandbox)
        fm = _parse_frontmatter(spec)
        return bool(fm.get("blocking_condition")) or fm.get("status") == "blocked"

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
