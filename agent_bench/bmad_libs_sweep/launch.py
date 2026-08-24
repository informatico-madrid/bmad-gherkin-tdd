#!/usr/bin/env python3
"""launch.py — Launch bmad-loop-sweep bench against multiple models.

Each model runs the sweep skill against the same deferred-work ledger.
The sweep skill checks BMAD_LOOP_MODE=1 and writes result.json.
"""

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

from agent_bench.common import resolve_models, slugify, clean_pycache, run_opencode

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sweep-hard"
RUNS_BASE = Path(__file__).parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "bmad_libs_sweep"

SWEEP_PROMPT = (
    "Load skill bmad-loop-sweep. "
    "You are running in automation mode (BMAD_LOOP_MODE=1). "
    "Read the deferred-work ledger at _bmad-output/implementation-artifacts/deferred-work.md. "
    "Read the source code in src/ to verify each open entry. "
    "Classify every open entry into exactly one category: "
    "already_resolved, bundles, blocked, skip, or decisions. "
    "Write the result.json to the run_dir as specified by automation-mode.md. "
    "Do NOT edit the ledger, code, or sprint-status. Read-only except for result.json."
)


def _reset_fixture() -> None:
    clean_pycache(FIXTURE_DIR)


def _create_sandbox(run_dir: Path, model_id: str) -> Path:
    slug = slugify(model_id)
    sandbox = run_dir / slug
    if sandbox.exists():
        shutil.rmtree(sandbox)
    shutil.copytree(FIXTURE_DIR, sandbox)
    clean_pycache(sandbox)
    return sandbox


def _run_sweep(sandbox: Path, model_id: str, timeout: int = 1800) -> dict:
    """Run the sweep via opencode with BMAD_LOOP env vars."""
    run_dir = sandbox
    task_dir = run_dir / "tasks" / "sweep-1"
    task_dir.mkdir(parents=True, exist_ok=True)
    result_path = task_dir / "result.json"

    env = os.environ.copy()
    env["BMAD_LOOP_MODE"] = "1"
    env["BMAD_LOOP_RUN_DIR"] = str(run_dir)
    env["BMAD_LOOP_TASK_ID"] = "sweep-1"

    start = time.time()
    timeout_val = None if timeout == 0 else timeout
    try:
        result = subprocess.run(
            ["opencode", "run", "--pure",
             "--dir", str(sandbox),
             "--agent", "bmad-loop-sweep",
             "--model", model_id,
             "--auto", "--format", "json",
             SWEEP_PROMPT],
            capture_output=True, text=True,
            timeout=timeout_val, cwd=str(sandbox), env=env,
        )
        return {
            "model": model_id,
            "status": "completed" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "elapsed_s": round(time.time() - start, 1),
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"model": model_id, "status": "timeout", "returncode": -1,
                "elapsed_s": round(time.time() - start, 1), "stdout": "", "stderr": f"Timeout {timeout}s"}
    except FileNotFoundError:
        return {"model": model_id, "status": "error", "returncode": -1,
                "elapsed_s": 0, "stdout": "", "stderr": "opencode CLI not found"}


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

    _reset_fixture()
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
        futures = {pool.submit(_run_sweep, sb, mid, args.timeout): mid for mid, sb in sandboxes}
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
    manifest = {"run_id": run_id, "phase": "bmad_libs_sweep", "timestamp": datetime.now(timezone.utc).isoformat(),
                "fixture": str(FIXTURE_DIR), "timeout": args.timeout, "results": results}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    print(f"\nSummary: {completed} completed, {failed} failed, {timeouts} timeout")


if __name__ == "__main__":
    main()
