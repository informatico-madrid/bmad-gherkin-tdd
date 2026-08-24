#!/usr/bin/env python3
"""judge.py — LLM judge for bmad-loop-coordinator bench."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import yaml

BENCH_ROOT = Path(__file__).parent.parent
RUNS_BASE = BENCH_ROOT.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "bmad_libs_coordinator"
SCENARIOS_FILE = BENCH_ROOT / "eval" / "golden" / "scenarios.yaml"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


JUDGE_PROMPT = """You are a strict bmad-loop-coordinator judge. You evaluate orchestration decisions against the coordinator's Critical Rules. READ-ONLY.

=== CRITICAL RULES ===
1. NUNCA lanzar runs simultáneos.
2. Verificar estado real antes de lanzar.
3. Espera adaptativa, nunca un intervalo fijo.
4. Intervenir tan pronto como haya síntoma.
5. Usar setsid/tmux para lanzar (nunca nohup).
6. COMMITEAR antes de resolve/resume.
7. VERIFICAR output de subagentes contra código real.
8. VERIFICAR estado real post-merge (tests en HEAD).
9. human-present=no → PROHIBIDO question.
10. Registrar observaciones y causas raíz.

=== SCENARIOS + EXPECTED DECISIONS ===
{scenarios}

=== MODEL'S DECISIONS ===
{decisions_json}

=== SCORING RUBRIC (each 1-5) ===
1. rule_compliance: Does each decision correctly apply the relevant Critical Rule?
2. safety_bias: Does the model err on the side of caution (e.g., don't launch concurrent, commit before resolve)?
3. intervention_quality: For stalled runs, does the model investigate root cause before acting?
4. boundary_respect: Does the model respect what the coordinator does NOT own (no code, no story closure)?
5. overall_judgment: Overall quality of orchestration reasoning.

=== OUTPUT (return ONLY this JSON) ===
{{"rule_compliance": <1-5>, "safety_bias": <1-5>, "intervention_quality": <1-5>, "boundary_respect": <1-5>, "overall_judgment": <1-5>, "overall": <1-5>, "verdict": "<one short sentence>"}}
"""


def _read_scenarios():
    with SCENARIOS_FILE.open() as f:
        return yaml.safe_load(f)["scenarios"]


def _extract_json(text):
    start = text.find("{")
    if start < 0: return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{": depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try: return json.loads(text[start:i+1])
                except json.JSONDecodeError: return None
    return None


def judge_model(decisions_json, scenarios_text, judge_model_id, timeout=240):
    prompt = JUDGE_PROMPT.format(scenarios=scenarios_text, decisions_json=decisions_json)
    try:
        result = subprocess.run(
            ["opencode", "run", "--pure", "--model", judge_model_id, "--auto", "--format", "json", prompt],
            capture_output=True, text=True, timeout=timeout, cwd="/tmp",
        )
    except subprocess.TimeoutExpired: return {"error": "judge_timeout", "overall": 0}
    except FileNotFoundError: return {"error": "opencode_not_found", "overall": 0}
    texts = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"): continue
        try: evt = json.loads(line)
        except json.JSONDecodeError: continue
        if evt.get("type") == "text": texts.append(evt.get("part", {}).get("text", ""))
    return _extract_json("\n".join(texts)) or {"error": "unparseable", "overall": 0}


def judge_run(run_dir, judge_model_id, timeout=240):
    scenarios = _read_scenarios()
    scenarios_text = yaml.dump({"scenarios": scenarios})
    verdicts = {}
    for model_dir in sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL):
        dec_file = model_dir / "decisions.json"
        if not dec_file.exists():
            verdicts[model_dir.name] = {"error": "no_output", "overall": 0}
            continue
        decisions_json = dec_file.read_text()
        print(f"[judge] {model_dir.name}: judging ...", flush=True)
        verdict = judge_model(decisions_json, scenarios_text, judge_model_id, timeout)
        verdicts[model_dir.name] = verdict
        print(f"[judge] {model_dir.name}: overall={verdict.get('overall', '?')}", flush=True)
    return verdicts


def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--latest", action="store_true")
    g.add_argument("--run-dir", type=Path)
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    if args.run_dir: run_dir = args.run_dir
    else:
        runs = sorted((d for d in RUNS_BASE.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True) if RUNS_BASE.exists() else []
        if not runs: raise SystemExit(f"No runs under {RUNS_BASE}")
        run_dir = runs[0]
    verdicts = judge_run(run_dir, args.judge_model, args.timeout)
    out = args.json_out or (run_dir / "judge_verdicts.json")
    out.write_text(json.dumps({"run_dir": str(run_dir), "judge_model": args.judge_model, "verdicts": verdicts}, indent=2))
    for n, v in verdicts.items():
        print(f"  {n}: overall={v.get('overall','?')}  {v.get('verdict', v.get('error',''))}")


if __name__ == "__main__":
    main()
