#!/usr/bin/env python3
"""launch.py — Launch TDD CLEAN bench against multiple models."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from agent_bench.common import resolve_models, slugify, clean_pycache, run_opencode

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "clean-hard"
RUNS_BASE = Path(__file__).parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "clean"

CLEAN_PROMPT = (
    "Load skill tdd-clean. "
    "Contract: tests/contracts/clean-hard.feature — scenarios @s1 through @s8. "
    "Gold test already exists: tests/unit/test_clean_hard.py (DO NOT EDIT IT). "
    "src/quota_broker.py is a working but structurally dirty implementation. "
    "Run scripts/cleaner_gate.py src/quota_broker.py to see violations. "
    "Fix structural violations only: KISS, DRY, YAGNI, LoD, CoI, scan_mutation_sites. "
    "Keep pytest green. Coverage 100%. "
    "DO NOT write tests. DO NOT change behavior. DO NOT use # pragma: no mutate. "
    "DO NOT run mutmut. Update bitácora to CLEAN. STOP."
)


def _reset_fixture() -> None:
    """Restore the dirty seed so a previous golden copy cannot contaminate runs."""
    clean_pycache(FIXTURE_DIR)
    seed = Path(__file__).parent / "eval" / "seed" / "quota_broker.py"
    dest = FIXTURE_DIR / "src" / "quota_broker.py"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed, dest)


def _create_sandbox(run_dir: Path, model_id: str) -> Path:
    slug = slugify(model_id)
    sandbox = run_dir / slug
    if sandbox.exists():
        shutil.rmtree(sandbox)
    shutil.copytree(FIXTURE_DIR, sandbox)
    clean_pycache(sandbox)
    return sandbox


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch TDD CLEAN bench")
    parser.add_argument("--models", "-m")
    parser.add_argument("--timeout", "-t", type=int, default=1800)
    parser.add_argument("--dry-run", "-n", action="store_true")
    parser.add_argument("--parallel", "-p", type=int, default=0)
    args = parser.parse_args()

    models = _resolve_models_or_cli(args.models)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_BASE / run_id

    print(f"Run ID:    {run_id}")
    print(f"Run dir:   {run_dir}")
    print(f"Models:    {len(models)}")
    print(f"Fixture:   {FIXTURE_DIR}")
    print(f"Timeout:   {'unlimited' if args.timeout == 0 else f'{args.timeout}s'}")
    print()

    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=True)

    _reset_fixture()
    sandboxes = []
    for model_id in models:
        sb = _create_sandbox(run_dir, model_id)
        sandboxes.append((model_id, sb))
        print(f"  sandbox: {sb.name} → {model_id}")
    print()

    if args.dry_run:
        print("[dry-run] Not launching. Sandboxes created.")
        return

    max_workers = args.parallel if args.parallel > 0 else len(sandboxes)
    print(f"[launch] {len(sandboxes)} models, max {max_workers} in parallel")
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_opencode, sb, mid, "tdd-clean-ornith", CLEAN_PROMPT, args.timeout): mid
                   for mid, sb in sandboxes}
        for future in as_completed(futures):
            mid = futures[future]
            try: result = future.result()
            except Exception as exc: result = {"model": mid, "status": "error", "returncode": -1, "elapsed_s": 0, "stdout": "", "stderr": repr(exc)}
            results.append(result)
            print(f"[done]   {mid}: {result['status']} ({result['elapsed_s']}s)", flush=True)

    order = {m: i for i, m in enumerate(models)}
    results.sort(key=lambda r: order.get(r["model"], len(models)))
    manifest_path = run_dir / "manifest.json"
    manifest = {"run_id": run_id, "phase": "clean", "timestamp": datetime.now(timezone.utc).isoformat(),
                "fixture": str(FIXTURE_DIR), "timeout": args.timeout, "results": results}
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest: {manifest_path}")
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    print(f"\nSummary: {completed} completed, {failed} failed, {timeouts} timeout")


def _resolve_models_or_cli(model_args):
    if model_args:
        return [m.strip() for m in model_args.split(",") if m.strip()]
    return resolve_models(None)


if __name__ == "__main__":
    main()
