#!/usr/bin/env python3
"""batch_eval.py — Scoreboard for bmad-loop-sweep bench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_bench.bmad_libs_sweep.eval.validate import validate

RUNS_BASE = Path(__file__).parent.parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "bmad_libs_sweep"
GOLDEN = Path(__file__).parent / "golden" / "result.json"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


def _model_dirs(run_dir):
    return sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL)


def evaluate_run(run_dir):
    golden = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else None
    rows = []
    for model_dir in _model_dirs(run_dir):
        row = {"model_dir": model_dir.name}
        result_file = model_dir / "result.json"
        if not result_file.exists():
            row.update({"status": "no_output", "score": 0})
            rows.append(row)
            continue
        try:
            result = json.loads(result_file.read_text())
        except json.JSONDecodeError:
            row.update({"status": "invalid_json", "score": 0})
            rows.append(row)
            continue

        report = validate(result, golden)
        row.update({
            "status": "completed",
            "score": report["score"],
            "passed": report["passed"],
            "violations": len(report["violations"]),
            "violation_details": report["violations"],
        })
        rows.append(row)

    rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return {"run_dir": str(run_dir), "models": len(rows), "rows": rows}


def print_table(scoreboard):
    rows = scoreboard["rows"]
    print(f"\nSweep bench: {scoreboard['run_dir']}  Models: {scoreboard['models']}\n")
    header = f"{'#':<3} {'model':<40} {'score':>6} {'viol':>5} {'status':<12}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['rank']:<3} {r['model_dir']:<40} {r.get('score',0):>6} "
              f"{r.get('violations',0):>5} {r.get('status','?'):<12}")
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
    scoreboard = evaluate_run(run_dir)
    out = args.json_out or (run_dir / "scoreboard.json")
    out.write_text(json.dumps(scoreboard, indent=2))
    print_table(scoreboard)
    print(f"Scoreboard: {out}")


if __name__ == "__main__":
    main()
