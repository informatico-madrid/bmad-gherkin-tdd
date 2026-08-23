#!/usr/bin/env python3
"""launch.py — Launch TDD RED bench against multiple models.

Copies the fixture to a run directory, then invokes `opencode run --pure`
for each selected model with the tdd-red-ornith agent.

Usage:
    python -m agent_bench.red.launch --models deepseek/deepseek-v4-flash,cefprovider/bunker-local

    Or interactively (reads opencode.json providers):
    python -m agent_bench.red.launch
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "red-hard"
RUNS_BASE = Path(__file__).parent.parent.parent / "_bmad-output" / "agent-bench" / "runs"
OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"

# Known providers from opencode.json
KNOWN_PROVIDERS = [
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-flash-0731",
    "cefprovider/bunker-local",
    "nan/mimo-v2.5",
    "nan/deepseek-v4-flash",
    "nan/gemma4",
    "tokenrouter/qwen/qwen3.7-max",
    "tokenrouter/grok-4.6",
    "tokenrouter/deepseek/deepseek-v4-flash",
    "tencent-tokenhub/glm-5.3",
    "tencent-tokenhub/deepseek-v4-flash",
    "google/gemini-3.7-flash",
]

RED_PROMPT = (
    "Load skill tdd-red. "
    "Contract: tests/contracts/red-hard.feature — scenarios @s1, @s2, @s3, @s4. "
    "Write failing tests for ALL 4 scenarios in a single tests/unit/test_red_hard.py. "
    "Each scenario maps to a test function. "
    "Follow PERSISTENT_PROMPT_CONSTRAINTS and MUTANT_KILLING_GUIDE. "
    "FIXTURE≠TARGET: do not use 'alpha', 'beta', or 'quota-lab' as expected values. "
    "Use dense assertions. "
    "Confirm pytest FAIL. Update bitácora to ROJO. STOP."
)


def _resolve_models(model_args: str | None) -> list[str]:
    """Resolve model list from args or opencode.json."""
    if model_args:
        return [m.strip() for m in model_args.split(",") if m.strip()]

    # Try to read from opencode.json
    if OPENCODE_CONFIG.exists():
        try:
            data = json.loads(OPENCODE_CONFIG.read_text(encoding="utf-8"))
            providers = data.get("provider", {})
            models = []
            for prov_name, prov_data in providers.items():
                models_config = prov_data.get("models", {})
                for model_name in models_config:
                    models.append(f"{prov_name}/{model_name}")
            if models:
                return models
        except (json.JSONDecodeError, KeyError):
            pass

    return KNOWN_PROVIDERS


def _slugify(model_id: str) -> str:
    """Turn model ID into filesystem-safe slug."""
    return model_id.replace("/", "__").replace(" ", "_").lower()


def _clean_test_slot(base: Path) -> None:
    """Remove any pre-existing test_red_hard.py + pycache under a fixture/sandbox root.

    The agent MUST start from an empty test slot. If a stale test file is present the
    agent may skip writing its own, silently making every model score the same old file.
    """
    stale = base / "tests" / "unit" / "test_red_hard.py"
    if stale.exists():
        stale.unlink()
    for pycache in base.rglob("__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)


def _reset_fixture() -> None:
    """Clean the fixture's test slot + bitácora before copying, so a contaminated
    fixture can never propagate a stale test into a sandbox."""
    _clean_test_slot(FIXTURE_DIR)
    bitacora = FIXTURE_DIR / "bitacora.md"
    if bitacora.exists():
        bitacora.write_text(
            "# Bitácora TDD — red-hard-001\n\n| @s | Fase | Status | Test file |\n|----|------|--------|-----------|\n",
            encoding="utf-8",
        )


def _create_sandbox(run_dir: Path, model_id: str) -> Path:
    """Copy fixture to a sandbox directory for one model, then force a clean slate.

    The sandbox MUST start with no pre-existing test file: if test_red_hard.py is
    already present the agent may skip writing it, which silently makes every model
    score the same stale file. We delete it (and any pycache / filled bitácora) so
    each run is idempotent even if the fixture were ever contaminated.
    """
    slug = _slugify(model_id)
    sandbox = run_dir / slug
    if sandbox.exists():
        shutil.rmtree(sandbox)
    shutil.copytree(FIXTURE_DIR, sandbox)

    # Defensive clean: guarantee the agent starts from an empty test slot.
    _clean_test_slot(sandbox)
    bitacora = sandbox / "bitacora.md"
    if bitacora.exists():
        bitacora.write_text(
            "# Bitácora TDD — red-hard-001\n\n| @s | Fase | Status | Test file |\n|----|------|--------|-----------|\n",
            encoding="utf-8",
        )
    return sandbox


def _run_opencode(sandbox: Path, model_id: str, timeout: int = 600) -> dict:
    """Run opencode with tdd-red-ornith agent on a sandbox."""
    start = time.time()
    try:
        result = subprocess.run(
            [
                "opencode", "run",
                "--pure",
                "--dir", str(sandbox),
                "--agent", "tdd-red-ornith",
                "--model", model_id,
                "--auto",
                "--format", "json",
                RED_PROMPT,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(sandbox),
        )
        elapsed = time.time() - start
        return {
            "model": model_id,
            "status": "completed" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "elapsed_s": round(elapsed, 1),
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {
            "model": model_id,
            "status": "timeout",
            "returncode": -1,
            "elapsed_s": round(elapsed, 1),
            "stdout": "",
            "stderr": f"Timeout after {timeout}s",
        }
    except FileNotFoundError:
        return {
            "model": model_id,
            "status": "error",
            "returncode": -1,
            "elapsed_s": 0,
            "stdout": "",
            "stderr": "opencode CLI not found",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Launch TDD RED bench")
    parser.add_argument(
        "--models", "-m",
        help="Comma-separated model IDs (e.g. deepseek/deepseek-v4-flash,cefprovider/bunker-local)",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int, default=600,
        help="Timeout per model in seconds (default: 600)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Print sandboxes without running",
    )
    parser.add_argument(
        "--parallel", "-p",
        type=int, default=0,
        help="Max parallel launches (default: all models at once)",
    )
    args = parser.parse_args()

    models = _resolve_models(args.models)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_BASE / run_id

    print(f"Run ID:    {run_id}")
    print(f"Run dir:   {run_dir}")
    print(f"Models:    {len(models)}")
    print(f"Fixture:   {FIXTURE_DIR}")
    print()

    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=True)

    # Clean the fixture's test slot so a contaminated fixture never propagates.
    _reset_fixture()

    # Create sandboxes
    sandboxes: list[tuple[str, Path]] = []
    for model_id in models:
        sandbox = _create_sandbox(run_dir, model_id)
        sandboxes.append((model_id, sandbox))
        print(f"  sandbox: {sandbox.name} → {model_id}")

    print()

    if args.dry_run:
        print("[dry-run] Not launching opencode. Sandboxes created.")
        return

    # Launch in parallel (ThreadPoolExecutor; each worker blocks on its own opencode run)
    max_workers = args.parallel if args.parallel > 0 else len(sandboxes)
    print(f"[launch] {len(sandboxes)} models, max {max_workers} in parallel")
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_model = {
            pool.submit(_run_opencode, sandbox, model_id, args.timeout): model_id
            for model_id, sandbox in sandboxes
        }
        for future in as_completed(future_to_model):
            model_id = future_to_model[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                result = {
                    "model": model_id,
                    "status": "error",
                    "returncode": -1,
                    "elapsed_s": 0,
                    "stdout": "",
                    "stderr": f"launcher exception: {exc!r}",
                }
            results.append(result)
            print(f"[done]   {model_id}: {result['status']} ({result['elapsed_s']}s)", flush=True)

    # Preserve the original model order in the manifest
    order = {m: i for i, m in enumerate(models)}
    results.sort(key=lambda r: order.get(r["model"], len(models)))

    # Write manifest
    manifest_path = run_dir / "manifest.json"
    manifest = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fixture": str(FIXTURE_DIR),
        "results": results,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest: {manifest_path}")

    # Summary
    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    errors = sum(1 for r in results if r["status"] == "error")
    print(f"\nSummary: {completed} completed, {failed} failed, {timeouts} timeout, {errors} error")


if __name__ == "__main__":
    main()
