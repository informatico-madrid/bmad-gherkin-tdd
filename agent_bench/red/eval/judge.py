#!/usr/bin/env python3
"""judge.py — LLM judge for the TDD RED bench.

For each model in a run dir, an LLM judge contrasts the generated test against the
RED mission (PRODUCT-INTENT + contract + mutant-killing guide) and emits a JSON
verdict. The judge is read-only: it receives the test + reference text embedded in
the prompt, reasons about it, and returns structured scores. No file writes, no
execution.

Usage:
    python -m agent_bench.red.eval.judge --latest --judge-model nan/mimo-v2.5
    python -m agent_bench.red.eval.judge --run-dir <path> --judge-model <model>
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

BENCH_ROOT = Path(__file__).parent.parent
FIXTURE_DIR = BENCH_ROOT / "fixtures" / "red-hard"
RUNS_BASE = BENCH_ROOT.parent.parent / "_bmad-output" / "agent-bench" / "runs"
TEST_REL = Path("tests") / "unit" / "test_red_hard.py"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}

JUDGE_PROMPT_TEMPLATE = """You are a strict TDD RED-phase judge. You evaluate a generated pytest test file against the RED mission. You are READ-ONLY: reason about the provided text and return a verdict. Do NOT write code, do NOT run anything.

=== PRODUCT INTENT (the mission) ===
{product_intent}

=== SIGNED CONTRACT (the source of truth) ===
{contract}

=== MUTANT-KILLING PRINCIPLES (excerpt) ===
{mutant_guide}

=== GENERATED TEST TO JUDGE ===
{test_code}

=== SCORING RUBRIC (each 1-5) ===
1. contract_fidelity: Does every @s scenario's Then map to a real, separate assertion? Are all 4 scenarios (@s1-@s4) covered?
2. assertion_density: Are assertions dense and exact (full structure equality, exact cardinality, types, spy full-args)? Or loose (is not None, 'x' in str, len>0)?
3. mutant_coverage: Does the test cover the mutant classes (boundaries, truth-table TF/FT, defaults-without-kwarg, sentinel identity, exact strings, asymmetric accumulators)?
4. fixture_discipline: Does it avoid fixture literals ('alpha'/'beta'/'quota-lab') as expected values? Does it derive from the contract, not samples?
5. correctness: Is the test syntactically valid, RED (fails against hollow stub), and free of anti-patterns (mocking the SUT, parametrize to dodge boundaries, generic Exception)?

=== OUTPUT (return ONLY this JSON, no other text) ===
{{"contract_fidelity": <1-5>, "assertion_density": <1-5>, "mutant_coverage": <1-5>, "fixture_discipline": <1-5>, "correctness": <1-5>, "overall": <1-5>, "verdict": "<one short sentence>"}}
"""


def _read_fixture_file(rel: str) -> str:
    p = FIXTURE_DIR / rel
    return p.read_text(encoding="utf-8") if p.exists() else "(missing)"


def _latest_run_dir() -> Path:
    runs = sorted((d for d in RUNS_BASE.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True)
    if not runs:
        raise SystemExit(f"No runs found under {RUNS_BASE}")
    return runs[0]


def _model_dirs(run_dir: Path) -> list[Path]:
    return sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL)


def _extract_json(text: str) -> dict | None:
    """Extract the first balanced {...} JSON object from the judge's reply."""
    # Find the first { and try to parse progressively
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    return None
    return None


def judge_model(test_code: str, judge_model_id: str, timeout: int = 240) -> dict:
    """Run the judge for one test file. Returns the parsed verdict dict."""
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        product_intent=_read_fixture_file("PRODUCT-INTENT.md"),
        contract=_read_fixture_file("tests/contracts/red-hard.feature"),
        mutant_guide="Dense exact assertions; boundaries (below/at/above); truth table TF+FT; "
        "call defaults WITHOUT the kwarg and observe the value; spy assert_called_once_with full args; "
        "sentinel via is + __eq__ decoy; exact strings (== or re.escape, never substring); "
        "asymmetric accumulator values (not 0/1/2); never mock the SUT; specific exception types.",
        test_code=test_code,
    )

    try:
        result = subprocess.run(
            [
                "opencode", "run", "--pure",
                "--model", judge_model_id,
                "--auto", "--format", "json",
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="/tmp",
        )
    except subprocess.TimeoutExpired:
        return {"error": "judge_timeout", "overall": 0}
    except FileNotFoundError:
        return {"error": "opencode_not_found", "overall": 0}

    # Collect the final text output from the JSON event stream
    texts = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        if evt.get("type") == "text":
            texts.append(evt.get("part", {}).get("text", ""))
    reply = "\n".join(texts)

    verdict = _extract_json(reply)
    if verdict is None:
        return {"error": "unparseable_verdict", "raw": reply[:500], "overall": 0}
    return verdict


def judge_run(run_dir: Path, judge_model_id: str, timeout: int = 240) -> dict:
    """Judge every model in a run dir. Returns {model_dir: verdict}."""
    verdicts = {}
    for model_dir in _model_dirs(run_dir):
        test_file = model_dir / TEST_REL
        if not test_file.exists():
            verdicts[model_dir.name] = {"error": "no_test_file", "overall": 0}
            print(f"[judge] {model_dir.name}: no test file, skipping")
            continue
        test_code = test_file.read_text(encoding="utf-8")
        print(f"[judge] {model_dir.name}: judging ...", flush=True)
        verdict = judge_model(test_code, judge_model_id, timeout=timeout)
        verdicts[model_dir.name] = verdict
        print(f"[judge] {model_dir.name}: overall={verdict.get('overall', '?')}")
    return verdicts


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM judge for a RED bench run")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true", help="Judge the most recent run")
    group.add_argument("--run-dir", type=Path, help="Explicit run directory")
    parser.add_argument("--judge-model", required=True, help="Model ID to use as the judge")
    parser.add_argument("--timeout", type=int, default=240, help="Per-judge timeout seconds")
    args = parser.parse_args()

    run_dir = args.run_dir if args.run_dir else _latest_run_dir()
    if not run_dir.is_dir():
        raise SystemExit(f"Run dir not found: {run_dir}")

    verdicts = judge_run(run_dir, args.judge_model, timeout=args.timeout)

    out_path = run_dir / "judge_verdicts.json"
    out_path.write_text(
        json.dumps({"run_dir": str(run_dir), "judge_model": args.judge_model, "verdicts": verdicts}, indent=2),
        encoding="utf-8",
    )
    print(f"\nJudge verdicts: {out_path}")

    # Print a compact summary
    print("\nJudge summary:")
    for model_dir, v in verdicts.items():
        overall = v.get("overall", "?")
        verdict = v.get("verdict", v.get("error", ""))
        print(f"  {model_dir:<40} overall={overall}  {verdict}")


if __name__ == "__main__":
    main()
