#!/usr/bin/env python3
"""launch.py — Launch loop_dev bench against multiple models."""

from __future__ import annotations

import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from agent_bench.common import resolve_models, slugify, clean_pycache, run_opencode

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "dev-hard"
RUNS_BASE = Path(__file__).parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "loop_dev"

DEV_PROMPT = (
    "Run the bmad-build-auto skill on this story now: "
    "/bmad-build-auto quota-sync-001 — "
    "sprint-status.yaml is owned by the orchestrator: never write it, and never revert a change to it. "
    "A row at done or awaiting-operator is the orchestrator's own bookkeeping — not a defect to fix, "
    "and not proof that the work is verified."
)


def _create_sandbox(run_dir: Path, model_id: str) -> Path:
    slug = slugify(model_id)
    sandbox = run_dir / slug
    if sandbox.exists():
        shutil.rmtree(sandbox)
    shutil.copytree(FIXTURE_DIR, sandbox, ignore=shutil.ignore_patterns("__pycache__", ".git"))
    import subprocess
    env = {"GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@local",
           "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "bench@local"}
    subprocess.run(["git", "init"], capture_output=True, cwd=str(sandbox), check=False)
    subprocess.run(["git", "add", "-A"], capture_output=True, cwd=str(sandbox), check=False)
    subprocess.run(["git", "commit", "-m", "initial"], capture_output=True, cwd=str(sandbox),
                   env={**__import__("os").environ, **env}, check=False)
    clean_pycache(sandbox)
    return sandbox


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", "-m")
    parser.add_argument("--timeout", "-t", type=int, default=600)
    parser.add_argument("--dry-run", "-n", action="store_true")
    parser.add_argument("--parallel", "-p", type=int, default=0)
    args = parser.parse_args()

    if not (FIXTURE_DIR / "src" / "quota_sync.py").is_file():
        print(f"[skip] loop_dev fixture is not materialized: {FIXTURE_DIR}")
        return

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
        print(f"  sandbox: {sb.name} -> {mid}")
    print()

    if args.dry_run:
        print("[dry-run] Not launching. Sandboxes created.")
        return

    max_workers = args.parallel if args.parallel > 0 else len(sandboxes)
    print(f"[launch] {len(sandboxes)} models, max {max_workers} in parallel")
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_opencode, sb, mid, "bmad-build-auto", DEV_PROMPT, args.timeout): mid
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
    manifest = {"run_id": run_id, "phase": "loop_dev", "timestamp": datetime.now(timezone.utc).isoformat(),
                "fixture": str(FIXTURE_DIR), "timeout": args.timeout, "results": results}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    print(f"\nSummary: {completed} completed, {failed} failed, {timeouts} timeout")


if __name__ == "__main__":
    main()
