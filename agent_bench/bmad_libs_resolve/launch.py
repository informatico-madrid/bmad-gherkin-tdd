#!/usr/bin/env python3
"""launch.py — Launch bmad-loop-resolve bench against multiple models.

Pattern: same as TDD benchmarks. Uses run_opencode from common.
"""

from __future__ import annotations

import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from agent_bench.common import resolve_models, slugify, clean_pycache, run_opencode

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "resolve-hard"
RUNS_BASE = Path(__file__).parent.parent.parent / "_bmad-output" / "agent-bench" / "runs" / "bmad_libs_resolve"

RESOLVE_PROMPT = (
    "Load skill bmad-loop-resolve. "
    "Read context.json first for the escalation details. "
    "Read the frozen spec at _bmad-output/implementation-artifacts/spec-4-2-quota-dispatch.md. "
    "The escalation is about the allow/deny precedence ambiguity. "
    "Resolve it: decide the correct semantics, update the frozen spec's "
    "<frozen-after-approval> block to encode the decision unambiguously. "
    "Write resolution.json to _bmad-output/implementation-artifacts/resolve/4-2-quota-dispatch/resolution.json. "
    "Do NOT edit sprint-status.yaml. Do NOT set the spec status field. "
    "Do NOT implement code. Minimal spec edit only."
)


def _create_sandbox(run_dir: Path, model_id: str) -> Path:
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

    max_workers = args.parallel if args.parallel > 0 else len(sandboxes)
    print(f"[launch] {len(sandboxes)} models, max {max_workers} in parallel")
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(run_opencode, sb, mid, "bmad-loop-resolve", RESOLVE_PROMPT, args.timeout): mid
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
    manifest = {"run_id": run_id, "phase": "bmad_libs_resolve", "timestamp": datetime.now(timezone.utc).isoformat(),
                "fixture": str(FIXTURE_DIR), "timeout": args.timeout, "results": results}
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    print(f"\nSummary: {completed} completed, {failed} failed, {timeouts} timeout")


if __name__ == "__main__":
    main()
