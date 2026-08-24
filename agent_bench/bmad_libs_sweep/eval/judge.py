#!/usr/bin/env python3
"""judge.py — LLM judge for bmad-loop-sweep bench."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

BENCH_ROOT = Path(__file__).parent.parent
FIXTURE_DIR = BENCH_ROOT / "fixtures" / "sweep-hard"
RUNS_BASE = BENCH_ROOT.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "bmad_libs_sweep"
_RESULT_FILE = Path("result.json")
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


JUDGE_PROMPT = """You are a strict bmad-loop-sweep judge. You evaluate a model's deferred-work triage result.json against the actual ledger and code. READ-ONLY.

=== DEFERRED-WORK LEDGER ===
{ledger}

=== SOURCE CODE (src/) ===
{source_code}

=== RESULT TO JUDGE ===
{result_json}

=== SCORING RUBRIC (each 1-5) ===
1. classification_correctness: Are all open entries correctly classified? Does every entry appear in exactly one category? Are done entries excluded from open_ids?
2. evidence_quality: For already_resolved — is the evidence concrete (file:line / commit hash)? For blocked — is the blocker a real story name?
3. bundle_coherence: Are bundled entries truly related (same touchpoint)? Are bundle names valid kebab-case? Are intents 2-6 sentences?
4. decision_quality: Are decisions correctly identified as human-territory? Do they have 2-4 options with build/close/keep-open effects? Is there a recommendation?
5. boundary_discipline: Does the model NOT edit the ledger, code, or sprint-status? Read-only compliance?

=== OUTPUT (return ONLY this JSON) ===
{{"classification_correctness": <1-5>, "evidence_quality": <1-5>, "bundle_coherence": <1-5>, "decision_quality": <1-5>, "boundary_discipline": <1-5>, "overall": <1-5>, "verdict": "<one short sentence>"}}
"""


def _read_fixture():
    ledger = (FIXTURE_DIR / "_bmad-output" / "implementation-artifacts" / "deferred-work.md").read_text()
    sources = []
    for f in sorted((FIXTURE_DIR / "src").glob("*.py")):
        sources.append(f"--- {f.name} ---\n{f.read_text()}")
    return ledger, "\n\n".join(sources)


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


def judge_model(result_json: str, ledger: str, source_code: str, judge_model_id: str, timeout: int = 240):
    prompt = JUDGE_PROMPT.format(ledger=ledger, source_code=source_code, result_json=result_json)
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
    ledger, source_code = _read_fixture()
    verdicts = {}
    for model_dir in sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL):
        result_file = model_dir / _RESULT_FILE
        if not result_file.exists():
            verdicts[model_dir.name] = {"error": "no_output", "overall": 0}
            continue
        result_json = result_file.read_text()
        print(f"[judge] {model_dir.name}: judging ...", flush=True)
        verdict = judge_model(result_json, ledger, source_code, judge_model_id, timeout)
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
