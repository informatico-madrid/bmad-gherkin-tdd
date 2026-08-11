"""Deterministic, idempotent installer for the BMAD Gherkin TDD module.

Installs the module's payload (skills, resolver, docs, hook, opencode assets,
bmad-loop profiles, override templates) into a BMAD project and registers the
module with the official BMAD merge scripts (config.yaml + module-help.csv).

Locating the payload:
  * Installed distribution (wheel): the build copies the payload into
    ``bmad_gherkin_tdd/payload/`` — this is the canonical source.
  * Source checkout: ``bmad_gherkin_tdd/`` lives at the repo root, so the
    payload dirs are the repo-root siblings (``skills/``, ``templates/``...).

The install is idempotent: re-running on an installed project refreshes the
bundled copies (upgrade) without touching the project's own ``_bmad/custom/*``
override layer. ``uninstall`` removes only files recorded in the manifest that
still byte-match the bundle — user-modified files are preserved and reported.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

MODULE_CODE = "gherkin-tdd"
MODULE_NAME = "BMAD Gherkin TDD"

# Payload directories installed into the project.
SKILL_NAMES = (
    "gherkin-author",
    "bmad-tdd-coordinator",
    "tdd-red",
    "tdd-green",
    "tdd-clean",
    "tdd-refactor",
)
PROFILE_NAMES = ("opencode-http.toml", "opencode-http-review.toml")
TEMPLATE_NAMES = ("bmad-dev-auto.toml", "bmad-tdd-coordinator.toml")

# Files installed at fixed project-relative paths (recorded for uninstall).
FILE_INSTALLS = {
    "_bmad/scripts/resolve_customization.py": "scripts/resolve_customization.py",
    "_bmad/gherkin-tdd/docs/contract-rules.md": "docs/contract-rules.md",
    "hooks/tdd_cycle_gate.py": "hooks/tdd_cycle_gate.py",
    "opencode/plugins/tdd-cycle-gate.js": "opencode/plugins/tdd-cycle-gate.js",
    "opencode/agents/opencode.json.template": "opencode/agents/opencode.json.template",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def module_root() -> Path:
    """Absolute path to the directory holding the payload dirs."""
    pkg = Path(__file__).resolve().parent
    payload = pkg / "payload"
    if payload.is_dir():
        return payload
    return pkg.parent


def payload(name: str) -> Path:
    """Path to a payload directory (``skills/``, ``templates/``, ...)."""
    return module_root() / name


def manifest_path(project: Path) -> Path:
    return project / "_bmad" / MODULE_CODE / "install.json"


def read_config(project: Path) -> dict:
    import yaml

    path = project / "_bmad" / "config.yaml"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def write_config(project: Path, config: dict) -> None:
    import yaml

    path = project / "_bmad" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _run_script(script: Path, args: list[str]) -> str:
    result = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"script {script.name} failed (rc={result.returncode}):\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
    return result.stdout


def _register_via_merge_scripts(project: Path) -> dict:
    """Reuse the official BMAD merge scripts (config.yaml + module-help.csv)."""
    base = payload("setup")
    answers = {"module": {"contracts_dir": "tests/contracts"}}
    answers_file = project / "_bmad" / MODULE_CODE / "answers.tmp.json"
    answers_file.parent.mkdir(parents=True, exist_ok=True)
    answers_file.write_text(json.dumps(answers), encoding="utf-8")
    try:
        _run_script(
            base / "scripts" / "merge-config.py",
            [
                "--config-path",
                str(project / "_bmad" / "config.yaml"),
                "--user-config-path",
                str(project / "_bmad" / "config.user.yaml"),
                "--module-yaml",
                str(base / "assets" / "module.yaml"),
                "--answers",
                str(answers_file),
                "--legacy-dir",
                str(project / "_bmad"),
            ],
        )
        _run_script(
            base / "scripts" / "merge-help-csv.py",
            [
                "--target",
                str(project / "_bmad" / "module-help.csv"),
                "--source",
                str(base / "assets" / "module-help.csv"),
                "--legacy-dir",
                str(project / "_bmad"),
                "--module-code",
                MODULE_CODE,
            ],
        )
    finally:
        answers_file.unlink(missing_ok=True)

    # Register the module in the top-level `modules` list (merge-config does not).
    config = read_config(project)
    modules = config.get("modules")
    if isinstance(modules, list) and MODULE_CODE not in modules:
        config["modules"] = modules + [MODULE_CODE]
        write_config(project, config)
    elif not isinstance(modules, list):
        config["modules"] = [MODULE_CODE]
        write_config(project, config)
    return {}


def install(project: Path, skills_dir: Path, force: bool = False) -> dict:
    """Install (or upgrade) the module payload into ``project``."""
    project = project.resolve()
    report: dict = {}

    # ── Skills ────────────────────────────────────────────────────────────────
    for name in SKILL_NAMES:
        src = payload("skills") / name
        dst = skills_dir / name
        if not src.is_dir():
            report[f"skill:{name}"] = "missing in bundle (skipped)"
            continue
        if dst.exists() and not force:
            report[f"skill:{name}"] = "exists (skipped, use --force to refresh)"
            continue
        shutil.copytree(src, dst, dirs_exist_ok=True)
        report[f"skill:{name}"] = "refreshed" if dst.exists() and force else "installed"

    # ── Single-file installs ──────────────────────────────────────────────────
    installed_files: dict[str, str] = {}
    for rel, src_rel in FILE_INSTALLS.items():
        src = payload(src_rel)
        if not src.is_file():
            report[f"file:{rel}"] = "missing in bundle (skipped)"
            continue
        dst = project / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        installed_files[rel] = _sha256(dst)
        report[f"file:{rel}"] = "installed"

    # ── bmad-loop profiles (never overwrite project-local profiles) ──────────
    profiles_dst = project / ".bmad-loop" / "profiles"
    for name in PROFILE_NAMES:
        src = payload("bmad-loop") / "profiles" / name
        dst = profiles_dst / name
        if not src.is_file():
            continue
        if dst.exists():
            report[f"profile:{name}"] = "exists (skipped)"
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        report[f"profile:{name}"] = "installed"

    # ── Override templates (never overwrite the project's own overrides) ─────
    custom_dst = project / "_bmad" / "custom"
    for name in TEMPLATE_NAMES:
        src = payload("templates") / "custom" / name
        dst = custom_dst / name
        if not src.is_file():
            continue
        if dst.exists():
            report[f"override:{name}"] = "exists (preserved)"
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        report[f"override:{name}"] = "installed"

    # ── Official BMAD registration (config + help) ───────────────────────────
    _register_via_merge_scripts(project)
    report["registration"] = "config.yaml + module-help.csv updated"

    # ── Manifest for upgrade/uninstall ───────────────────────────────────────
    manifest = {
        "module": MODULE_CODE,
        "name": MODULE_NAME,
        "version": "0.1.0",
        "installed_at": "",
        "skills_dir": str(skills_dir),
        "files": installed_files,
        "profiles": PROFILE_NAMES,
        "templates": TEMPLATE_NAMES,
    }
    mp = manifest_path(project)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    report["manifest"] = str(mp)
    return report


def _drop_module_from_config(project: Path) -> bool:
    config = read_config(project)
    changed = False
    if MODULE_CODE in config:
        del config[MODULE_CODE]
        changed = True
    modules = config.get("modules")
    if isinstance(modules, list) and MODULE_CODE in modules:
        config["modules"] = [m for m in modules if m != MODULE_CODE]
        changed = True
    if changed:
        write_config(project, config)
    return changed


def _drop_module_from_help(project: Path) -> bool:
    import csv
    from io import StringIO

    target = project / "_bmad" / "module-help.csv"
    if not target.exists():
        return False
    rows = list(csv.reader(StringIO(target.read_text(encoding="utf-8", newline=""))))
    if not rows:
        return False
    header, data = rows[0], rows[1:]
    kept = [r for r in data if not (r and r[0].strip() == MODULE_NAME)]
    if len(kept) == len(data):
        return False
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(kept)
    target.write_text(out.getvalue(), encoding="utf-8", newline="")
    return True


def uninstall(project: Path) -> dict:
    """Remove the module's installed files. User-modified files are preserved."""
    project = project.resolve()
    report: dict = {}

    mp = manifest_path(project)
    manifest = json.loads(mp.read_text(encoding="utf-8")) if mp.is_file() else {}

    # Remove single-file installs only if they still match the bundle hash.
    for rel, expected in (manifest.get("files") or {}).items():
        dst = project / rel
        if dst.is_file() and _sha256(dst) == expected:
            dst.unlink()
            report[f"removed:{rel}"] = "ok"
        elif dst.exists():
            report[f"removed:{rel}"] = "preserved (modified since install)"

    # Skills dir (only the skill directories we own).
    skills_dir = Path(manifest.get("skills_dir", ".agents/skills"))
    if not skills_dir.is_absolute():
        skills_dir = project / skills_dir
    for name in SKILL_NAMES:
        dst = skills_dir / name
        if dst.is_dir():
            shutil.rmtree(dst)
            report[f"removed:skill:{name}"] = "ok"

    # Module state dir (docs + manifest).
    module_dir = project / "_bmad" / MODULE_CODE
    if module_dir.is_dir():
        shutil.rmtree(module_dir)
        report["removed:_bmad/gherkin-tdd"] = "ok"

    # Registration cleanup.
    if _drop_module_from_config(project):
        report["config.yaml"] = "gherkin-tdd section removed"
    if _drop_module_from_help(project):
        report["module-help.csv"] = "gherkin-tdd rows removed"

    report["overrides"] = "preserved under _bmad/custom/ (project-owned)"
    return report


def status(project: Path) -> dict:
    mp = manifest_path(project)
    installed = mp.is_file()
    if not installed:
        return {"module": MODULE_CODE, "installed": False}
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    return {
        "module": MODULE_CODE,
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "installed": True,
        "skills_dir": manifest.get("skills_dir"),
        "files": len(manifest.get("files") or {}),
    }
