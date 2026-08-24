#!/usr/bin/env python3
"""batch_eval.py — Scoreboard for bmad-loop-coordinator bench."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

RUNS_BASE = Path(__file__).parent.parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "bmad_libs_coordinator"
SCENARIOS = Path(__file__).parent / "golden" / "scenarios.yaml"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


def _load_scenarios():
    with SCENARIOS.open() as f:
        return yaml.safe_load(f)["scenarios"]


def _model_dirs(run_dir):
    return sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL)


def _score_scenario(decision_text: str, scenario: dict) -> dict:
    """Score a coordinator decision against the expected decision (deterministic heuristics)."""
    expected = scenario["expected_decision"].lower()
    decision = decision_text.lower()
    rule = scenario["rule_violated_if_wrong"]
    correct = True
    notes = []

    if "concurrent" in expected and ("launch" in decision or "launch" in expected):
        if "not" in decision or "wait" in decision or "no" in decision.split()[:3]:
            correct = True
        elif "launch" in decision and "not" not in decision[:50]:
            correct = False
            notes.append("launched concurrent run")

    if "intervene" in expected and "interven" not in decision:
        correct = False
        notes.append("did not intervene on stalled run")

    if "human-present" in scenario.get("state", {}) and scenario["state"]["human_present"] == "no":
        if "question" in decision and "not" not in decision[:80]:
            correct = False
            notes.append("used question tool when human absent")

    if "setsid" in expected or "tmux" in expected:
        uses_nohup = ("nohup" in decision and "not" not in decision[:80] and "never" not in decision[:200])
        mentions_setsid_or_tmux = ("setsid" in decision or "tmux" in decision)
        if uses_nohup and not mentions_setsid_or_tmux:
            correct = False
            notes.append("used nohup without setsid/tmux")

    if "commit" in expected.split()[:5] or "commit first" in expected:
        if "commit" not in decision[:200]:
            correct = False
            notes.append("did not mention committing before resolve")

    if "test suite" in expected or "verify" in expected.split()[:5]:
        if "test" not in decision[:300] and "verify" not in decision[:300]:
            correct = False
            notes.append("did not mention running tests or verifying")

    score = 100.0 if correct else 0.0
    return {"score": score, "correct": correct, "notes": notes, "rule": rule}


def evaluate_run(run_dir):
    scenarios = _load_scenarios()
    rows = []
    for model_dir in _model_dirs(run_dir):
        row = {"model_dir": model_dir.name}
        decisions_file = model_dir / "decisions.json"
        if not decisions_file.exists():
            row.update({"status": "no_output", "score": 0})
            rows.append(row)
            continue
        try:
            decisions = json.loads(decisions_file.read_text())
        except json.JSONDecodeError:
            row.update({"status": "invalid_json", "score": 0})
            rows.append(row)
            continue

        total_score = 0
        results = []
        for scenario in scenarios:
            sid = scenario["id"]
            dec = decisions.get(sid, {})
            decision_text = dec.get("decision", dec.get("rationale", ""))
            report = _score_scenario(decision_text, scenario)
            total_score += report["score"]
            results.append({"scenario": sid, **report})

        n = len(scenarios) if scenarios else 1
        avg_score = round(total_score / n, 1)
        correct_count = sum(1 for r in results if r["correct"])

        row.update({
            "status": "completed",
            "score": avg_score,
            "correct": correct_count,
            "total": n,
            "results": results,
        })
        rows.append(row)

    rows.sort(key=lambda r: r.get("score", 0), reverse=True)
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return {"run_dir": str(run_dir), "models": len(rows), "rows": rows}


def print_table(scoreboard):
    rows = scoreboard["rows"]
    print(f"\nCoordinator bench: {scoreboard['run_dir']}  Models: {scoreboard['models']}\n")
    header = f"{'#':<3} {'model':<40} {'score':>6} {'correct':>8} {'status':<12}"
    print(header); print("-" * len(header))
    for r in rows:
        print(f"{r['rank']:<3} {r['model_dir']:<40} {r.get('score',0):>6} "
              f"{r.get('correct',0):>4}/{r.get('total',0):<3} {r.get('status','?'):<12}")
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
        if not runs: raise SystemExit(f"No runs under {RUNS_BASE}")
        run_dir = runs[0]
    scoreboard = evaluate_run(run_dir)
    out = args.json_out or (run_dir / "scoreboard.json")
    out.write_text(json.dumps(scoreboard, indent=2))
    print_table(scoreboard)
    print(f"Scoreboard: {out}")


if __name__ == "__main__":
    main()
