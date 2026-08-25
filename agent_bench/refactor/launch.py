#!/usr/bin/env python3
"""launch.py — Launch TDD REFACTOR bench against multiple models."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from agent_bench.common import resolve_models, slugify, clean_pycache, run_opencode

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "refactor-hard"
SEED_FILE = Path(__file__).parent / "eval" / "seed" / "quota_broker.py"
RUNS_BASE = Path(__file__).parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "refactor"

REFACTOR_PROMPT = (
    "Load skill tdd-refactor. "
    "Contract: tests/contracts/refactor-hard.feature — scenarios @s1 through @s8. "
    "Gold test already exists: tests/unit/test_refactor_hard.py (DO NOT EDIT IT). "
    "src/quota_broker.py is a working implementation with poor design. "
    "CLEAN gate already passes. Now IMPROVE DESIGN: "
    "split apply() into smaller helpers, extract concerns, improve naming, "
    "apply SOLID principles, Tell-Don't-Ask, reduce coupling. "
    "DO NOT write tests. DO NOT change behavior. DO NOT use # pragma: no mutate. "
    "DO NOT run mutmut. Keep pytest green. "
    "Run scripts/cleaner_gate.py to verify gate still passes. "
    "Update bitácora to REFACTOR. STOP."
)


def _create_sandbox(run_dir, model_id):
    slug = slugify(model_id)
    sandbox = run_dir / slug
    if sandbox.exists():
        shutil.rmtree(sandbox)
    shutil.copytree(FIXTURE_DIR, sandbox)
    seed_dest = sandbox / "src" / "quota_broker.py"
    seed_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SEED_FILE, seed_dest)
    clean_pycache(sandbox)
    return sandbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", "-m")
    parser.add_argument("--timeout", "-t", type=int, default=1800)
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

    max_workers = args.parallel if args.parallel > 0 else len(sandboxes)
    print(f"[launch] {len(sandboxes)} models, max {max_workers} in parallel")
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_opencode, sb, mid, "tdd-refactor-ornith", REFACTOR_PROMPT, args.timeout): mid
                   for mid, sb in sandboxes}
        for future in as_completed(futures):
            mid = futures[future]
            try: result = future.result()
            except Exception as exc: result = {"model": mid, "status": "error", "returncode": -1, "elapsed_s": 0, "stdout": "", "stderr": repr(exc)}
            results.append(result)
            print(f"[done] {mid}: {result['status']} ({result['elapsed_s']}s)", flush=True)

    order = {m: i for i, m in enumerate(models)}
    results.sort(key=lambda r: order.get(r["model"], len(models)))
    manifest = {"run_id": run_id, "phase": "refactor", "timestamp": datetime.now(timezone.utc).isoformat(),
                "fixture": str(FIXTURE_DIR), "timeout": args.timeout, "results": results}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    print(f"\nSummary: {completed} completed, {failed} failed, {timeouts} timeout")


if __name__ == "__main__":
    main()
