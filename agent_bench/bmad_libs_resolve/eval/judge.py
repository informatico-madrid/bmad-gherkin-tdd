#!/usr/bin/env python3
"""judge.py — LLM judge for bmad-loop-resolve bench."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

BENCH_ROOT = Path(__file__).parent.parent
FIXTURE_DIR = BENCH_ROOT / "fixtures" / "resolve-hard"
RUNS_BASE = BENCH_ROOT.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "bmad_libs_resolve"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


JUDGE_PROMPT = """You are a strict bmad-loop-resolve judge. You evaluate a model's resolution of a CRITICAL escalation against a frozen spec. READ-ONLY.

=== ESCALATION CONTEXT ===
{context}

=== FROZEN SPEC ===
{spec}

=== GOLDEN RESOLUTION ===
{golden}

=== MODEL'S RESOLUTION ===
{resolution_json}

=== SCORING RUBRIC (each 1-5) ===
1. ambiguity_identification: Did the model correctly identify the specific ambiguity (allow vs deny precedence)?
2. decision_quality: Is the chosen resolution reasonable and well-justified? Does it align with the safe default (deny > allow)?
3. spec_edit_minimality: Did the model make the smallest possible change to the frozen spec to remove the ambiguity?
4. boundary_discipline: Did the model avoid editing sprint-status, setting spec status, implementing code, or widening scope?
5. marker_validity: Is the resolution.json well-formed with all required fields?

=== OUTPUT (return ONLY this JSON) ===
{{"ambiguity_identification": <1-5>, "decision_quality": <1-5>, "spec_edit_minimality": <1-5>, "boundary_discipline": <1-5>, "marker_validity": <1-5>, "overall": <1-5>, "verdict": "<one short sentence>"}}
"""


def _read_fixture():
    context = (FIXTURE_DIR / "context.json").read_text()
    spec = (FIXTURE_DIR / ".bmad-output" / "implementation-artifacts" / "spec-4-2-quota-dispatch.md").read_text()
    golden = (BENCH_ROOT / "eval" / "golden" / "resolution.json").read_text()
    return context, spec, golden


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


def judge_model(resolution_json, context, spec, golden, judge_model_id, timeout=240):
    prompt = JUDGE_PROMPT.format(context=context, spec=spec, golden=golden, resolution_json=resolution_json)
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
    context, spec, golden = _read_fixture()
    verdicts = {}
    for model_dir in sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL):
        res_file = model_dir / "resolution.json"
        if not res_file.exists():
            verdicts[model_dir.name] = {"error": "no_output", "overall": 0}
            continue
        resolution_json = res_file.read_text()
        print(f"[judge] {model_dir.name}: judging ...", flush=True)
        verdict = judge_model(resolution_json, context, spec, golden, judge_model_id, timeout)
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
