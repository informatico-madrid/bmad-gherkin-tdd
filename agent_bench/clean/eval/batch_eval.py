#!/usr/bin/env python3
"""batch_eval.py — Scoreboard for CLEAN bench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import yaml

from agent_bench.clean.eval.run_pytest import run_gold, run_hidden, run_cleaner_gate
from agent_bench.clean.eval.cheat_detect import detect_all

RUNS_BASE = Path(__file__).parent.parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "clean"
_SURFACES_PATH = Path(__file__).parent / "surfaces.yaml"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


def _load_surfaces():
    with _SURFACES_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)["surfaces"]


def _model_dirs(run_dir):
    return sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL)


def _gate_pct(gate_data):
    checks = gate_data.get("checks", {})
    if not checks:
        return 0.0
    passed = sum(1 for c in checks.values() if c.get("status") == "PASS")
    return round(100 * passed / len(checks), 1)


def evaluate_run(run_dir):
    rows = []
    surfaces = _load_surfaces()
    for model_dir in _model_dirs(run_dir):
        row = {"model_dir": model_dir.name}
        impl = model_dir / "src" / "quota_broker.py"
        if not impl.exists():
            row.update({"status": "no_output", "score": 0, "visible": "0/0", "hidden": "0/0", "gate": "0/0"})
            rows.append(row)
            continue

        gold = run_gold(model_dir)
        gold_total = gold["pass"] + gold["fail"]
        visible_pct = round(100 * gold["pass"] / gold_total, 1) if gold_total else 0.0

        hidden = run_hidden(model_dir)
        hidden_total = hidden["pass"] + hidden["fail"]
        hidden_pct = round(100 * hidden["pass"] / hidden_total, 1) if hidden_total else 0

        gate = run_cleaner_gate(model_dir)
        gate_p = _gate_pct(gate)

        violations = detect_all(model_dir)
        penalty = sum(v["severity"] for v in violations)

        mission_ok = 1.0 if gold["fail"] == 0 and gold["pass"] > 0 else 0.0
        if gold["pass"] == 0: hidden_pct = 0.0

        score = 100 * (
            0.40 * (gate_p / 100) + 0.35 * (hidden_pct / 100) + 0.15 * mission_ok + 0.10 * mission_ok
        ) - 5 * penalty
        score = max(0, round(score, 1))

        gate_checks = gate.get("checks", {})
        gate_passed = sum(1 for c in gate_checks.values() if c.get("status") == "PASS")
        gate_total = len(gate_checks)

        row.update({
            "status": "completed", "score": score,
            "visible": f"{gold['pass']}/{gold_total}" if gold_total else "0/0",
            "visible_pct": visible_pct,
            "hidden": f"{hidden['pass']}/{hidden_total}" if hidden_total else "0/0",
            "hidden_pct": hidden_pct,
            "gate": f"{gate_passed}/{gate_total}", "gate_pct": gate_p,
            "gate_overall": gate.get("overall", "UNKNOWN"),
            "cheat_penalty": penalty,
            "cheat_violations": [v["id"] for v in violations],
        })
        rows.append(row)

    rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    for i, row in enumerate(rows, 1): row["rank"] = i
    return {"run_dir": str(run_dir), "models": len(rows), "rows": rows}


def print_table(scoreboard):
    rows = scoreboard["rows"]
    print()
    print(f"Bench run: {scoreboard['run_dir']}")
    print(f"Models: {scoreboard['models']}")
    print()
    header = f"{'#':<3} {'model':<40} {'score':>6} {'vis':>6} {'hid':>6} {'gate':>6} {'pen':>4} {'status':<10}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['rank']:<3} {r['model_dir']:<40} {r.get('score',0):>6} "
              f"{r.get('visible','?'):>6} {r.get('hidden','?'):>6} "
              f"{r.get('gate','?'):>6} {r.get('cheat_penalty',0):>4} {r.get('status','?'):<10}")
    print()


def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--latest", action="store_true")
    g.add_argument("--run-dir", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.run_dir: run_dir = args.run_dir
    else:
        runs = sorted((d for d in RUNS_BASE.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True) if RUNS_BASE.exists() else []
        if not runs: raise SystemExit(f"No runs under {RUNS_BASE}")
        run_dir = runs[0]
    scoreboard = evaluate_run(run_dir)
    out = args.json_out or (run_dir / "scoreboard.json")
    out.write_text(json.dumps(scoreboard, indent=2))
    print_table(scoreboard)
    print(f"Scoreboard: {out}")


if __name__ == "__main__":
    main()
