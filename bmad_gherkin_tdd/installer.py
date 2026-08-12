"""Deterministic installer for the BMAD Gherkin TDD module."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

MODULE_CODE = "gherkin-tdd"
MODULE_NAME = "BMAD Gherkin TDD"
MODULE_VERSION = "0.1.0"

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

FILE_INSTALLS = {
    "_bmad/scripts/resolve_customization.py": "scripts/resolve_customization.py",
    "_bmad/gherkin-tdd/docs/contract-rules.md": "docs/contract-rules.md",
    "_bmad/gherkin-tdd/scripts/cleaner_gate.py": "scripts/cleaner_gate.py",
    "_bmad/gherkin-tdd/scripts/principles.py": "scripts/principles.py",
    "_bmad/gherkin-tdd/scripts/scan_mutation_sites.py": "scripts/scan_mutation_sites.py",
    "hooks/tdd_cycle_gate.py": "hooks/tdd_cycle_gate.py",
    ".opencode/plugins/tdd-cycle-gate.js": "opencode/plugins/tdd-cycle-gate.js",
    "opencode/agents/opencode.json.template": "opencode/agents/opencode.json.template",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(child.relative_to(path).as_posix().encode())
        digest.update(b"\0")
        digest.update(_sha256(child).encode())
        digest.update(b"\0")
    return digest.hexdigest()


def module_root() -> Path:
    package = Path(__file__).resolve().parent
    bundled = package / "payload"
    return bundled if bundled.is_dir() else package.parent


def payload(name: str) -> Path:
    return module_root() / name


def manifest_path(project: Path) -> Path:
    return project / "_bmad" / MODULE_CODE / "install.json"


def read_yaml(path: Path) -> dict:
    import yaml

    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def write_yaml(path: Path, data: dict) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, default_flow_style=False, allow_unicode=True, sort_keys=False)


def read_config(project: Path) -> dict:
    return read_yaml(project / "_bmad" / "config.yaml")


def write_config(project: Path, config: dict) -> None:
    write_yaml(project / "_bmad" / "config.yaml", config)


def _inside(project: Path, candidate: Path) -> bool:
    try:
        return candidate.resolve().is_relative_to(project.resolve())
    except (OSError, ValueError):
        return False


def _project_path(project: Path, value: str) -> Path | None:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project / candidate
    return candidate if _inside(project, candidate) else None


def _relative(project: Path, path: Path) -> str:
    return path.resolve().relative_to(project.resolve()).as_posix()


def _read_manifest(project: Path) -> dict:
    path = manifest_path(project)
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


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


def _register(project: Path) -> None:
    base = payload("setup")
    answers_path = project / "_bmad" / MODULE_CODE / "answers.tmp.json"
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text(
        json.dumps({"module": {"contracts_dir": "tests/contracts"}}), encoding="utf-8"
    )
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
                str(answers_path),
                "--legacy-dir",
                str(project / "_bmad"),
            ],
        )
        _run_script(
            base / "scripts" / "merge-help-csv.py",
            [
                "--target",
                str(project / "_bmad" / "_config" / "bmad-help.csv"),
                "--source",
                str(base / "assets" / "module-help.csv"),
                "--legacy-dir",
                str(project / "_bmad"),
                "--module-code",
                MODULE_CODE,
            ],
        )
    finally:
        answers_path.unlink(missing_ok=True)

    config = read_config(project)
    modules = config.get("modules")
    if not isinstance(modules, list):
        modules = []
    if MODULE_CODE not in modules:
        config["modules"] = [*modules, MODULE_CODE]
        write_config(project, config)

    implementation_artifacts = config.get(
        "implementation_artifacts", "_bmad-output/implementation-artifacts"
    )
    write_yaml(
        project / "_bmad" / MODULE_CODE / "config.yaml",
        {
            "contracts_dir": "{project-root}/tests/contracts",
            "implementation_artifacts": (
                implementation_artifacts
                if str(implementation_artifacts).startswith("{project-root}")
                else f"{{project-root}}/{str(implementation_artifacts).lstrip('/')}"
            ),
        },
    )


def _install_file(
    project: Path,
    rel: str,
    source: Path,
    previous_files: dict,
    report: dict,
) -> str | None:
    destination = _project_path(project, rel)
    if destination is None:
        raise ValueError(f"bundle destination escapes project: {rel}")
    previous_hash = previous_files.get(rel)
    if destination.exists():
        if not destination.is_file() or destination.is_symlink():
            report[f"file:{rel}"] = "exists (preserved)"
            return None
        if not isinstance(previous_hash, str) or _sha256(destination) != previous_hash:
            report[f"file:{rel}"] = "exists (preserved)"
            return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    report[f"file:{rel}"] = "refreshed" if previous_hash else "installed"
    return _sha256(destination)


def install(project: Path, skills_dir: Path, force: bool = False) -> dict:
    project = project.resolve()
    skills_dir = skills_dir.resolve()
    if not _inside(project, skills_dir):
        raise ValueError("skills_dir must be inside project")

    previous = _read_manifest(project)
    previous_files = previous.get("files") if isinstance(previous.get("files"), dict) else {}
    previous_skills = previous.get("skills") if isinstance(previous.get("skills"), dict) else {}
    report: dict = {}
    installed_skills: dict[str, dict[str, str]] = {}

    for name in SKILL_NAMES:
        source = payload("skills") / name
        destination = skills_dir / name
        prior = previous_skills.get(name)
        owned = isinstance(prior, dict) and prior.get("path") == _relative(project, destination)
        if destination.is_symlink():
            report[f"skill:{name}"] = "exists (preserved)"
            continue
        if destination.exists() and not owned:
            report[f"skill:{name}"] = "exists (preserved)"
            continue
        if destination.exists() and not force:
            report[f"skill:{name}"] = "exists (skipped, use --force to refresh)"
        else:
            shutil.copytree(source, destination, dirs_exist_ok=True)
            report[f"skill:{name}"] = "refreshed" if owned else "installed"
        installed_skills[name] = {
            "path": _relative(project, destination),
            "sha256": _tree_sha256(destination),
        }

    installed_files: dict[str, str] = {}
    for rel, source_rel in FILE_INSTALLS.items():
        source = payload(source_rel)
        if not source.is_file():
            report[f"file:{rel}"] = "missing in bundle (skipped)"
            continue
        digest = _install_file(project, rel, source, previous_files, report)
        if digest:
            installed_files[rel] = digest

    for name in PROFILE_NAMES:
        rel = (Path(".bmad-loop") / "profiles" / name).as_posix()
        source = payload("bmad-loop") / "profiles" / name
        digest = _install_file(project, rel, source, previous_files, report)
        if digest:
            installed_files[rel] = digest

    custom_dir = project / "_bmad" / "custom"
    for name in TEMPLATE_NAMES:
        source = payload("templates") / "custom" / name
        destination = custom_dir / name
        if destination.exists():
            report[f"override:{name}"] = "exists (preserved)"
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        report[f"override:{name}"] = "installed (project-owned)"

    _register(project)
    report["registration"] = "config.yaml + _config/bmad-help.csv updated"
    module_config_rel = f"_bmad/{MODULE_CODE}/config.yaml"
    module_config = project / module_config_rel
    installed_files[module_config_rel] = _sha256(module_config)

    manifest = {
        "module": MODULE_CODE,
        "name": MODULE_NAME,
        "version": MODULE_VERSION,
        "skills": installed_skills,
        "files": installed_files,
    }
    path = manifest_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    report["manifest"] = str(path)
    return report


def _drop_module_from_config(project: Path) -> bool:
    config = read_config(project)
    changed = False
    if MODULE_CODE in config:
        del config[MODULE_CODE]
        changed = True
    modules = config.get("modules")
    if isinstance(modules, list) and MODULE_CODE in modules:
        config["modules"] = [module for module in modules if module != MODULE_CODE]
        changed = True
    if changed:
        write_config(project, config)
    return changed


def _drop_module_from_help(project: Path) -> bool:
    import csv
    from io import StringIO

    target = project / "_bmad" / "_config" / "bmad-help.csv"
    if not target.exists():
        return False
    with target.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return False
    kept = [row for row in rows[1:] if not (row and row[0].strip() == MODULE_NAME)]
    if len(kept) == len(rows) - 1:
        return False
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(rows[0])
    writer.writerows(kept)
    with target.open("w", encoding="utf-8", newline="") as handle:
        handle.write(output.getvalue())
    return True


def _remove_empty_parents(path: Path, project: Path) -> None:
    parent = path.parent
    while parent != project and _inside(project, parent):
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def uninstall(project: Path) -> dict:
    project = project.resolve()
    manifest = _read_manifest(project)
    report: dict = {}

    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    for rel, expected in files.items():
        destination = _project_path(project, rel)
        if destination is None:
            report[f"invalid:{rel}"] = "ignored (path escapes project)"
            continue
        if (
            destination.is_file()
            and not destination.is_symlink()
            and _sha256(destination) == expected
        ):
            destination.unlink()
            report[f"removed:{rel}"] = "ok"
            _remove_empty_parents(destination, project)
        elif destination.exists():
            report[f"removed:{rel}"] = "preserved (modified since install)"

    skills = manifest.get("skills") if isinstance(manifest.get("skills"), dict) else {}
    for name, metadata in skills.items():
        raw_path = metadata.get("path") if isinstance(metadata, dict) else None
        destination = _project_path(project, raw_path) if isinstance(raw_path, str) else None
        if destination is None:
            report[f"invalid:skill:{name}"] = "ignored (path escapes project)"
            continue
        expected = metadata.get("sha256")
        if (
            destination.is_dir()
            and not destination.is_symlink()
            and _tree_sha256(destination) == expected
        ):
            shutil.rmtree(destination)
            report[f"removed:skill:{name}"] = "ok"
            _remove_empty_parents(destination, project)
        elif destination.exists():
            report[f"removed:skill:{name}"] = "preserved (modified since install)"

    path = manifest_path(project)
    path.unlink(missing_ok=True)
    module_dir = project / "_bmad" / MODULE_CODE
    if module_dir.is_dir() and not module_dir.is_symlink():
        with suppress(OSError):
            module_dir.rmdir()

    if _drop_module_from_config(project):
        report["config.yaml"] = "gherkin-tdd section removed"
    if _drop_module_from_help(project):
        report["bmad-help.csv"] = "gherkin-tdd rows removed"
    report["overrides"] = "preserved under _bmad/custom/ (project-owned)"
    return report


def status(project: Path) -> dict:
    manifest = _read_manifest(project)
    if not manifest:
        return {"module": MODULE_CODE, "installed": False}
    return {
        "module": MODULE_CODE,
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "installed": True,
        "skills": len(manifest.get("skills") or {}),
        "files": len(manifest.get("files") or {}),
    }
