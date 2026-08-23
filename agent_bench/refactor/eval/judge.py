#!/usr/bin/env python3
"""judge.py — LLM judge for REFACTOR bench: design improvement + behavior preservation."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

BENCH_ROOT = Path(__file__).parent.parent
FIXTURE_DIR = BENCH_ROOT / "fixtures" / "refactor-hard"
RUNS_BASE = BENCH_ROOT.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "refactor"
IMPL_REL = Path("src") / "quota_broker.py"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


JUDGE_PROMPT = """You are a strict TDD REFACTOR-phase judge. The code was already GREEN+CLEAN (tests pass, gate pass). You evaluate whether the REFACTOR improved design. READ-ONLY.

=== PRODUCT INTENT ===
{product_intent}

=== CONTRACT ===
{contract}

=== SPEC-PINS ===
{spec_pins}

=== STANDARDS ===
{standards}

=== SEMILLA (before refactoring) ===
{seed_code}

=== REFACTORED IMPLEMENTATION ===
{impl_code}

=== GOLD TEST RESULTS ===
{gold_results}

=== HIDDEN TEST RESULTS ===
{hidden_results}

=== CLEANER-GATE RESULT ===
{gate_result}

=== SCORING RUBRIC (each 1-5) ===
1. behavior_preservation: gold+hidden still pass?
2. structural_improvement: Did the refactoring ACTUALLY improve structure vs semilla? (split functions, extract helpers, reduce cc, etc.)
3. shell_resistance: No empty helpers, no pass-through wrappers?
4. contract_intact: All 8 @s still honored?
5. refactor_discipline: No pragma, no tests written, no mutation run?
6. solid_improvement: SRP better? OCP improved? Less coupling?
7. antipattern_reduction: Less nesting, shorter methods, less duplication?
8. standards_compliance: Guard clauses, named constants, specific exceptions?

=== OUTPUT (return ONLY this JSON) ===
{{"behavior_preservation": <1-5>, "structural_improvement": <1-5>, "shell_resistance": <1-5>, "contract_intact": <1-5>, "refactor_discipline": <1-5>, "solid_improvement": <1-5>, "antipattern_reduction": <1-5>, "standards_compliance": <1-5>, "overall": <1-5>, "verdict": "<one short sentence>"}}
"""


def _read_fixture(rel):
    p = FIXTURE_DIR / rel
    return p.read_text(encoding="utf-8") if p.exists() else "(missing)"


def _read_impl(sandbox):
    impl = sandbox / IMPL_REL
    return impl.read_text(encoding="utf-8") if impl.exists() else "(no impl)"


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


def judge_model(seed_code, impl_code, gold_results, hidden_results, gate_result, judge_model_id, timeout=240):
    prompt = JUDGE_PROMPT.format(
        product_intent=_read_fixture("PRODUCT-INTENT.md"),
        contract=_read_fixture("tests/contracts/refactor-hard.feature"),
        spec_pins=_read_fixture("SPEC-PINS.md"),
        standards=_read_fixture("STANDARDS.md"),
        seed_code=seed_code[:4000],
        impl_code=impl_code[:4000],
        gold_results=json.dumps(gold_results, indent=2),
        hidden_results=json.dumps(hidden_results, indent=2),
        gate_result=json.dumps(gate_result, indent=2),
    )
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
    from agent_bench.refactor.eval.run_pytest import run_gold, run_hidden, run_cleaner_gate

    semilla = FIXTURE_DIR / "src" / "quota_broker.py"
    seed_code = semilla.read_text(encoding="utf-8") if semilla.exists() else "(missing)"

    verdicts = {}
    for model_dir in sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL):
        impl_code = _read_impl(model_dir)
        if impl_code == "(no impl)":
            verdicts[model_dir.name] = {"error": "no_impl", "overall": 0}
            continue
        print(f"[judge] {model_dir.name}: judging ...", flush=True)
        gold = run_gold(model_dir)
        hidden = run_hidden(model_dir)
        gate = run_cleaner_gate(model_dir)
        verdict = judge_model(seed_code, impl_code, gold, hidden, gate, judge_model_id, timeout)
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
    run_dir = args.run_dir or _latest_run_dir()
    if not run_dir.is_dir(): raise SystemExit(f"Not found: {run_dir}")
    verdicts = judge_run(run_dir, args.judge_model, args.timeout)
    out = args.json_out or (run_dir / "judge_verdicts.json")
    out.write_text(json.dumps({"run_dir": str(run_dir), "judge_model": args.judge_model, "verdicts": verdicts}, indent=2))
    for n, v in verdicts.items():
        print(f"  {n}: overall={v.get('overall','?')}  {v.get('verdict', v.get('error',''))}")


def _latest_run_dir():
    if not RUNS_BASE.exists(): raise SystemExit(f"No runs under {RUNS_BASE}")
    runs = sorted((d for d in RUNS_BASE.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True)
    return runs[0] if runs else (_ for _ in ()).throw(SystemExit("No runs"))


if __name__ == "__main__":
    main()
