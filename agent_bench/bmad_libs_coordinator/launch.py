#!/usr/bin/env python3
"""launch.py — Launch bmad-loop-coordinator bench."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agent_bench.common import resolve_models, slugify, clean_pycache, run_opencode

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "coordinator-hard"
RUNS_BASE = Path(__file__).parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "bmad-libs-coordinator"
SCENARIOS = Path(__file__).parent / "eval" / "golden" / "scenarios.yaml"


def _build_prompt() -> str:
    scenarios = yaml.safe_load(SCENARIOS.read_text())["scenarios"]
    prompt = (
        "You are the BMAD Loop Coordinator. For each scenario below, state your "
        "orchestration decision. Reference the Critical Rules from the coordinator skill.\n\n"
        "OUTPUT: Write decisions.json with this structure:\n"
        '{"<scenario_id>": {"decision": "<your decision in 1-3 sentences>", '
        '"rationale": "<which rule you applied>"}}\n\n'
        "RULES (from bmad-loop-coordinator SKILL.md):\n"
        "1. NUNCA lanzar runs simultáneos.\n"
        "2. Verificar estado real antes de lanzar.\n"
        "3. Espera adaptativa, nunca un intervalo fijo.\n"
        "4. Intervenir tan pronto como haya síntoma.\n"
        "5. Usar setsid/tmux para lanzar (nunca nohup).\n"
        "6. COMMITEAR antes de resolve/resume.\n"
        "7. VERIFICAR output de subagentes contra código real.\n"
        "8. VERIFICAR estado real post-merge (tests en HEAD).\n"
        "9. human-present=no → PROHIBIDO question.\n"
        "10. Registrar observaciones y causas raíz.\n\n"
        "SCENARIOS:\n\n"
    )
    for s in scenarios:
        prompt += f"### {s['id']}\n"
        prompt += f"Trigger: {s['trigger']}\n"
        prompt += f"State: {json.dumps(s['state'], indent=2)}\n\n"
    return prompt


def _create_sandbox(run_dir, model_id):
    slug = slugify(model_id)
    sandbox = run_dir / slug
    if sandbox.exists():
        shutil.rmtree(sandbox)
    shutil.copytree(FIXTURE_DIR, sandbox)
    clean_pycache(sandbox)
    return sandbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", "-m")
    parser.add_argument("--timeout", "-t", type=int, default=600)
    parser.add_argument("--dry-run", "-n", action="store_true")
    parser.add_argument("--parallel", "-p", type=int, default=0)
    args = parser.parse_args()

    models = resolve_models(args.models)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_BASE / run_id
    print(f"Run ID: {run_id}\nRun dir: {run_dir}\nModels: {len(models)}\nTimeout: {'unlimited' if args.timeout == 0 else f'{args.timeout}s'}\n")

    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=True)

    sandboxes = []
    for mid in models:
        sb = _create_sandbox(run_dir, mid)
        sandboxes.append((mid, sb))
        print(f"  sandbox: {sb.name} → {mid}")
    print()

    if args.dry_run:
        print("[dry-run] Not launching. Sandboxes created.")
        return

    prompt = _build_prompt()
    max_workers = args.parallel if args.parallel > 0 else len(sandboxes)
    print(f"[launch] {len(sandboxes)} models, max {max_workers} in parallel")
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_opencode, sb, mid, "bmad-loop-coordinator", prompt, args.timeout): mid
                   for mid, sb in sandboxes}
        for future in as_completed(futures):
            mid = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {"model": mid, "status": "error", "returncode": -1, "elapsed_s": 0, "stdout": "", "stderr": repr(exc)}
            results.append(result)
            print(f"[done] {mid}: {result['status']} ({result['elapsed_s']}s)", flush=True)

    order = {m: i for i, m in enumerate(models)}
    results.sort(key=lambda r: order.get(r["model"], len(models)))
    manifest = {"run_id": run_id, "phase": "bmad-libs-coordinator", "timestamp": datetime.now(timezone.utc).isoformat(),
                "fixture": str(FIXTURE_DIR), "timeout": args.timeout, "results": results}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    print(f"\nSummary: {completed} completed, {failed} failed, {timeouts} timeout")


if __name__ == "__main__":
    main()
