#!/usr/bin/env python3
"""batch_eval.py — Evaluate all models in a bench run and produce a scoreboard.

Scans a run directory for model sandboxes, runs the static scorer on each
model's generated test file, and writes a scoreboard (JSON + printed table).

Usage:
    python -m agent_bench.red.eval.batch_eval --latest
    python -m agent_bench.red.eval.batch_eval --run-dir <path>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_bench.red.eval.static_score import evaluate, Scorecard

RUNS_BASE = Path(__file__).parent.parent.parent.parent / "_bmad-output" / "agent-bench" / "runs"
TEST_REL = Path("tests") / "unit" / "test_red_hard.py"

# Files/dirs inside a run dir that are NOT model sandboxes
_NON_MODEL = {"manifest.json", "scoreboard.json", ".git"}


def _latest_run_dir() -> Path:
    runs = sorted(
        (d for d in RUNS_BASE.iterdir() if d.is_dir()),
        key=lambda d: d.name,
        reverse=True,
    )
    if not runs:
        raise SystemExit(f"No runs found under {RUNS_BASE}")
    return runs[0]


def _model_dirs(run_dir: Path) -> list[Path]:
    return sorted(
        d for d in run_dir.iterdir()
        if d.is_dir() and d.name not in _NON_MODEL
    )


def evaluate_run(run_dir: Path) -> dict:
    """Evaluate every model sandbox in a run dir. Returns the scoreboard dict."""
    rows = []
    for model_dir in _model_dirs(run_dir):
        test_file = model_dir / TEST_REL
        row = {
            "model_dir": model_dir.name,
            "test_file": str(test_file),
        }
        if not test_file.exists():
            row.update({
                "status": "no_output",
                "note": "agent did not write the test file",
                "score": 0,
                "surfaces_hit": 0,
                "surfaces_total": 0,
                "penalties": 0,
            })
        else:
            card: Scorecard = evaluate(test_file)
            row.update({
                "status": "completed" if card.syntax_ok else "syntax_error",
                "score": round(card.score, 1),
                "surfaces_hit": card.surfaces_hit,
                "surfaces_total": card.surfaces_total,
                "surface_pct": round(card.surface_pct, 1),
                "penalties": card.penalties,
                "tests": card.test_count,
                "asserts": card.assertion_count,
                "missed": [r.id for r in card.results if not r.hit and r.category != "forbidden"],
                "violations": [r.id for r in card.results if r.hit and r.category == "forbidden"],
            })
        rows.append(row)

    # Rank by score desc, then surfaces desc
    rows.sort(key=lambda r: (r["score"], r["surfaces_hit"]), reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = i

    scoreboard = {
        "run_dir": str(run_dir),
        "models": len(rows),
        "rows": rows,
    }
    return scoreboard


def print_table(scoreboard: dict) -> None:
    """Print a human-readable comparison table."""
    rows = scoreboard["rows"]
    print()
    print(f"Bench run: {scoreboard['run_dir']}")
    print(f"Models evaluated: {scoreboard['models']}")
    print()
    header = f"{'#':<3} {'model':<40} {'score':>6} {'surfaces':>10} {'tests':>6} {'pen':>4} {'status':<12}"
    print(header)
    print("-" * len(header))
    for row in rows:
        surfaces = f"{row['surfaces_hit']}/{row['surfaces_total']}"
        print(
            f"{row['rank']:<3} {row['model_dir']:<40} {row['score']:>6} "
            f"{surfaces:>10} {row.get('tests', 0):>6} {row['penalties']:>4} {row['status']:<12}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-evaluate a bench run")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true", help="Evaluate the most recent run")
    group.add_argument("--run-dir", type=Path, help="Explicit run directory")
    parser.add_argument("--json-out", type=Path, default=None, help="Write scoreboard JSON here")
    args = parser.parse_args()

    run_dir = args.run_dir if args.run_dir else _latest_run_dir()
    if not run_dir.is_dir():
        raise SystemExit(f"Run dir not found: {run_dir}")

    scoreboard = evaluate_run(run_dir)

    out_path = args.json_out or (run_dir / "scoreboard.json")
    out_path.write_text(json.dumps(scoreboard, indent=2), encoding="utf-8")

    print_table(scoreboard)
    print(f"Scoreboard: {out_path}")


if __name__ == "__main__":
    main()
