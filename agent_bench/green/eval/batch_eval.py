#!/usr/bin/env python3
"""batch_eval.py — Evaluate all models in a GREEN bench run and produce a scoreboard.

Scans a run directory for model sandboxes, runs gold + hidden tests, quality
checks (HQG Tier A), and cheat detection on each model's implementation.

Usage:
    python -m agent_bench.green.eval.batch_eval --run-dir <path>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from agent_bench.green.eval.run_pytest import run_gold, run_hidden
from agent_bench.green.eval.cheat_detect import detect_all
from agent_bench.green.eval.quality_local import check_all as quality_local_check

RUNS_BASE = Path(__file__).parent.parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "green"
_IMPL_REL = Path("src") / "quota_broker.py"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}

_SURFACES_PATH = Path(__file__).parent / "surfaces.yaml"


def _load_surfaces() -> list[dict]:
    with _SURFACES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["surfaces"]


def _model_dirs(run_dir: Path) -> list[Path]:
    return sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL)


def _check_quality(sandbox: Path) -> dict:
    """Score quality surfaces via local AST checkers (HQG not required)."""
    src = sandbox / "src" / "quota_broker.py"
    if not src.exists():
        return {"passed": 0, "total": 0, "pct": 0, "details": "no impl"}
    checks = quality_local_check(src)
    passed = sum(1 for c in checks if c["status"] == "PASS")
    total = len(checks)
    details = {c["id"]: c["status"] for c in checks}
    return {
        "passed": passed,
        "total": total,
        "pct": round(100 * passed / total, 1) if total else 0,
        "details": details,
    }


def evaluate_run(run_dir: Path) -> dict:
    """Evaluate every model sandbox in a run dir."""
    rows = []
    for model_dir in _model_dirs(run_dir):
        row = {"model_dir": model_dir.name}

        impl = model_dir / _IMPL_REL
        if not impl.exists():
            row.update({
                "status": "no_output",
                "score": 0,
                "visible": "0/0",
                "hidden": "0/0",
                "quality": "0/0",
                "cheat_penalty": 0,
            })
            rows.append(row)
            continue

        gold = run_gold(model_dir)
        gold_total = gold["pass"] + gold["fail"]
        visible_pct = round(100 * gold["pass"] / gold_total, 1) if gold_total else 0.0

        hidden = run_hidden(model_dir)
        hidden_total = hidden["pass"] + hidden["fail"]
        hidden_hit = hidden["pass"]
        hidden_pct = round(100 * hidden_hit / hidden_total, 1) if hidden_total else 0

        # Quality (HQG Tier A)
        quality = _check_quality(model_dir)

        # Cheat detection
        violations = detect_all(model_dir)
        penalty = sum(v["severity"] for v in violations)

        # GREEN: behavioral correctness is the core. Hidden dominates; each
        # behavioral bug (hidden failure) costs extra on top of hidden_pct.
        mission_ok = 1.0 if gold["fail"] == 0 and gold["pass"] > 0 else 0.0
        quality_pct = quality.get("pct", 0)
        if gold["pass"] == 0:
            quality_pct = 0.0
        hidden_fail = hidden_total - hidden_hit
        score = 100 * (
            0.05 * (visible_pct / 100)
            + 0.70 * (hidden_pct / 100)
            + 0.15 * (quality_pct / 100)
            + 0.10 * mission_ok
        ) - 5 * penalty - 3 * hidden_fail
        score = max(0, round(score, 1))

        row.update({
            "status": "completed",
            "score": score,
            "visible": f"{gold['pass']}/{gold_total}" if gold_total else "0/0",
            "visible_pct": visible_pct,
            "hidden": f"{hidden_hit}/{hidden_total}" if hidden_total else "0/0",
            "hidden_pct": hidden_pct,
            "quality": f"{quality.get('passed', 0)}/{quality.get('total', 0)}",
            "quality_pct": quality_pct,
            "quality_details": quality.get("details"),
            "surfaces_declared": len(_load_surfaces()),
            "cheat_penalty": penalty,
            "cheat_violations": [v["id"] for v in violations],
        })
        rows.append(row)

    rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = i

    return {"run_dir": str(run_dir), "models": len(rows), "rows": rows}


def print_table(scoreboard: dict) -> None:
    rows = scoreboard["rows"]
    print()
    print(f"Bench run: {scoreboard['run_dir']}")
    print(f"Models evaluated: {scoreboard['models']}")
    print()
    header = f"{'#':<3} {'model':<40} {'score':>6} {'visible':>8} {'hidden':>8} {'quality':>8} {'pen':>4} {'status':<12}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['rank']:<3} {row['model_dir']:<40} {row.get('score', 0):>6} "
            f"{row.get('visible', '?'):>8} {row.get('hidden', '?'):>8} "
            f"{row.get('quality', '?'):>8} {row.get('cheat_penalty', 0):>4} "
            f"{row.get('status', '?'):<12}"
        )
    print()


def main():
    parser = argparse.ArgumentParser(description="Batch-evaluate a GREEN bench run")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true")
    group.add_argument("--run-dir", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    if args.run_dir:
        run_dir = args.run_dir
    else:
        runs = sorted((d for d in RUNS_BASE.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True) if RUNS_BASE.exists() else []
        if not runs:
            raise SystemExit(f"No runs found under {RUNS_BASE}")
        run_dir = runs[0]

    scoreboard = evaluate_run(run_dir)

    out_path = args.json_out or (run_dir / "scoreboard.json")
    out_path.write_text(json.dumps(scoreboard, indent=2), encoding="utf-8")

    print_table(scoreboard)
    print(f"Scoreboard: {out_path}")


if __name__ == "__main__":
    main()
