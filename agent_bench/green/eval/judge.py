#!/usr/bin/env python3
"""judge.py — LLM judge for the GREEN bench with Tier B quality evaluation.

Evaluates the IMPLEMENTATION (not the test) against:
1. Contract realization (does the impl implement the policy?)
2. Minimality (is it the minimal code?)
3. Correctness (does it pass gold+hidden?)
4. GREEN discipline (no test writing, no mutation, no refactoring)
5. SOLID Tier B (semantic: SRP, OCP, LSP, ISP, DIP)
6. Antipattern Tier B (semantic: Divergent Change, Lava Flow, Boat Anchor, etc.)
7. Standards compliance (guard clauses, named constants, specific exceptions)

Usage:
    python -m agent_bench.green.eval.judge --run-dir <path> --judge-model <model>
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

BENCH_ROOT = Path(__file__).parent.parent
FIXTURE_DIR = BENCH_ROOT / "fixtures" / "green-hard"
RUNS_BASE = BENCH_ROOT.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "green"
_IMPL_REL = Path("src") / "quota_broker.py"
_NON_MODEL = {"manifest.json", "scoreboard.json", "judge_verdicts.json", ".git"}


JUDGE_PROMPT_TEMPLATE = """You are a strict TDD GREEN-phase judge. You evaluate an IMPLEMENTATION against the GREEN mission and code quality standards. You are READ-ONLY: reason about the provided text and return a verdict. Do NOT write code, do NOT run anything.

=== PRODUCT INTENT (the mission) ===
{product_intent}

=== SIGNED CONTRACT (8 scenarios) ===
{contract}

=== SPEC-PINS (semantic pins) ===
{spec_pins}

=== STANDARDS (code quality) ===
{standards}

=== SOLID TIER B — Semantic Red Flags ===
- SRP: >7 public methods handling different concerns? Multiple concerns in __init__?
- OCP: Adding a new behavior requires editing an if-chain? No ABC/Protocol?
- LSP: Narrowed return types? Strengthened preconditions?
- ISP: Fat interfaces with empty implementations? Many unused method stubs?
- DIP: Direct instantiation of concrete classes in domain code?

=== ANTIPATTERN TIER B — Semantic Patterns ===
- AP14 Divergent Change: One class changed for many different reasons
- AP15 Shotgun Surgery: One change requires editing many files
- AP19 Temporary Field: Instance variables only set conditionally
- AP28 Comments as Deodorant: Comments explain bad code instead of fixing it
- AP29 Inappropriate Intimacy: Excessive access to class internals
- AP34 Lava Flow: Dead code from experiments
- AP36 Golden Hammer: Same solution for every problem
- AP37 Reinvent the Wheel: Custom implementation of stdlib functionality
- AP38 Boat Anchor: Unused code kept "just in case"

=== IMPLEMENTATION TO JUDGE ===
{impl_code}

=== GOLD TEST RESULTS ===
{gold_results}

=== HIDDEN TEST RESULTS ===
{hidden_results}

=== SCORING RUBRIC (each 1-5) ===
1. contract_realization: Does the impl implement ALL 8 @s scenarios? Does it follow the SPEC-PINS (threshold inclusive, truth tables, stop_on_first, SKIP identity, cache, path_map, etc.)?
2. minimality: Is it the MINIMAL code? No features extra? No over-engineering?
3. correctness: Does it pass gold tests? Hidden tests? No hardcoded literals?
4. green_discipline: Did it avoid writing tests? Did it avoid mutation? Did it update bitácora?
5. solid_semantic: SRP, OCP, LSP, ISP, DIP — semantic violations only (Tier A handles AST).
6. antipattern_semantic: AP14-AP38 violations only (Tier A handles AP01-AP25).
7. standards_compliance: Guard clauses? Named constants? Specific exceptions? No bare except?

=== OUTPUT (return ONLY this JSON, no other text) ===
{{"contract_realization": <1-5>, "minimality": <1-5>, "correctness": <1-5>, "green_discipline": <1-5>, "solid_semantic": <1-5>, "antipattern_semantic": <1-5>, "standards_compliance": <1-5>, "overall": <1-5>, "verdict": "<one short sentence>"}}
"""


def _read_fixture_file(rel: str) -> str:
    p = FIXTURE_DIR / rel
    return p.read_text(encoding="utf-8") if p.exists() else "(missing)"


def _read_impl(sandbox: Path) -> str:
    impl = sandbox / _IMPL_REL
    return impl.read_text(encoding="utf-8") if impl.exists() else "(no implementation)"


def _latest_run_dir() -> Path:
    if not RUNS_BASE.exists():
        raise SystemExit(f"No runs found under {RUNS_BASE}")
    runs = sorted((d for d in RUNS_BASE.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True)
    if not runs:
        raise SystemExit(f"No runs found under {RUNS_BASE}")
    return runs[0]


def _model_dirs(run_dir: Path) -> list[Path]:
    return sorted(d for d in run_dir.iterdir() if d.is_dir() and d.name not in _NON_MODEL)


def _extract_json(text: str) -> dict | None:
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


def judge_model(impl_code: str, gold_results: dict, hidden_results: dict, judge_model_id: str, timeout: int = 240) -> dict:
    """Run the judge for one implementation. Returns the parsed verdict dict."""
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        product_intent=_read_fixture_file("PRODUCT-INTENT.md"),
        contract=_read_fixture_file("tests/contracts/green-hard.feature"),
        spec_pins=_read_fixture_file("SPEC-PINS.md"),
        standards=_read_fixture_file("STANDARDS.md"),
        impl_code=impl_code[:8000],  # truncate if too long
        gold_results=json.dumps(gold_results, indent=2),
        hidden_results=json.dumps(hidden_results, indent=2),
    )

    try:
        result = subprocess.run(
            ["opencode", "run", "--pure",
             "--model", judge_model_id,
             "--auto", "--format", "json",
             prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd="/tmp",
        )
    except subprocess.TimeoutExpired:
        return {"error": "judge_timeout", "overall": 0}
    except FileNotFoundError:
        return {"error": "opencode_not_found", "overall": 0}

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
    from agent_bench.green.eval.run_pytest import run_gold, run_hidden

    verdicts = {}
    for model_dir in _model_dirs(run_dir):
        impl_code = _read_impl(model_dir)
        if impl_code == "(no implementation)":
            verdicts[model_dir.name] = {"error": "no_impl", "overall": 0}
            print(f"[judge] {model_dir.name}: no impl, skipping")
            continue

        print(f"[judge] {model_dir.name}: judging ...", flush=True)

        # Run gold + hidden for context
        gold = run_gold(model_dir)
        hidden = run_hidden(model_dir)

        verdict = judge_model(impl_code, gold, hidden, judge_model_id, timeout)
        verdicts[model_dir.name] = verdict
        overall = verdict.get("overall", "?")
        print(f"[judge] {model_dir.name}: overall={overall}", flush=True)

    return verdicts


def main():
    parser = argparse.ArgumentParser(description="Judge GREEN bench results")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true")
    group.add_argument("--run-dir", type=Path)
    parser.add_argument("--judge-model", required=True, help="Model ID for the judge")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()

    run_dir = args.run_dir if args.run_dir else _latest_run_dir()
    if not run_dir.is_dir():
        raise SystemExit(f"Run dir not found: {run_dir}")

    verdicts = judge_run(run_dir, args.judge_model, args.timeout)

    out_path = args.json_out or (run_dir / "judge_verdicts.json")
    result = {"run_dir": str(run_dir), "judge_model": args.judge_model, "verdicts": verdicts}
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\nJudge verdicts: {out_path}")
    for name, v in verdicts.items():
        overall = v.get("overall", "?")
        verdict_text = v.get("verdict", v.get("error", "unknown"))
        print(f"  {name}: overall={overall}  {verdict_text}")


if __name__ == "__main__":
    main()
