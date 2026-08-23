"""Shared helpers for agent bench launchers."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

OPENCODE_CONFIG = Path.home() / ".config" / "opencode" / "opencode.json"


def resolve_models(model_args: str | None, known: list[str] | None = None) -> list[str]:
    if model_args:
        return [m.strip() for m in model_args.split(",") if m.strip()]
    if OPENCODE_CONFIG.exists():
        try:
            data = json.loads(OPENCODE_CONFIG.read_text(encoding="utf-8"))
            providers = data.get("provider", {})
            models = []
            for prov_name, prov_data in providers.items():
                for model_name in prov_data.get("models", {}):
                    models.append(f"{prov_name}/{model_name}")
            if models:
                return models
        except (json.JSONDecodeError, KeyError):
            pass
    return known or []


def slugify(model_id: str) -> str:
    return model_id.replace("/", "__").replace(" ", "_").lower()


def clean_pycache(base: Path) -> None:
    for p in base.rglob("__pycache__"):
        shutil.rmtree(p, ignore_errors=True)


def run_opencode(sandbox: Path, model_id: str, agent: str, prompt: str,
                 timeout: int = 1800) -> dict:
    start = time.time()
    timeout_val = None if timeout == 0 else timeout
    try:
        result = subprocess.run(
            ["opencode", "run", "--pure",
             "--dir", str(sandbox),
             "--agent", agent,
             "--model", model_id,
             "--auto", "--format", "json",
             prompt],
            capture_output=True, text=True,
            timeout=timeout_val, cwd=str(sandbox),
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
        return {
            "model": model_id, "status": "timeout",
            "returncode": -1, "elapsed_s": round(time.time() - start, 1),
            "stdout": "", "stderr": f"Timeout after {timeout}s",
        }
    except FileNotFoundError:
        return {
            "model": model_id, "status": "error",
            "returncode": -1, "elapsed_s": 0,
            "stdout": "", "stderr": "opencode CLI not found",
        }
