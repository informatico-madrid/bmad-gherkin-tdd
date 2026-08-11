"""Command-line interface for the BMAD Gherkin TDD module installer.

Usage:
    bmad-gherkin-tdd install   [--project PATH] [--skills-dir PATH] [--claude] [--force]
    bmad-gherkin-tdd upgrade   [--project PATH] [--skills-dir PATH] [--claude]
    bmad-gherkin-tdd uninstall [--project PATH]
    bmad-gherkin-tdd status    [--project PATH]
    bmad-gherkin-tdd --version
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .installer import install, uninstall
from .installer import status as install_status


def _print_report(report: dict) -> None:
    for key, value in report.items():
        print(f"  {key}: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bmad-gherkin-tdd",
        description="Install / upgrade / uninstall the BMAD Gherkin TDD module into a BMAD project.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd in ("install", "upgrade", "uninstall", "status"):
        p = sub.add_parser(cmd, help=f"{cmd} the module in a project")
        p.add_argument("--project", default=".", help="project root (default: cwd)")
        p.add_argument(
            "--skills-dir",
            default=None,
            help="skills tree relative to the project (default: .agents/skills)",
        )
        p.add_argument(
            "--claude",
            action="store_true",
            help="use the .claude/skills tree instead of .agents/skills",
        )
        if cmd in ("install", "upgrade"):
            p.add_argument(
                "--force",
                action="store_true",
                help="refresh bundled skill copies even if the target exists",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = Path(args.project).resolve()
    if not project.is_dir():
        print(f"error: project not found: {project}", file=sys.stderr)
        return 1

    skills_dir = Path(args.skills_dir or (".claude/skills" if args.claude else ".agents/skills"))
    if not skills_dir.is_absolute():
        skills_dir = Path(project) / skills_dir

    try:
        if args.command in ("install", "upgrade"):
            report = install(project, skills_dir, force=args.force or args.command == "upgrade")
            print(f"BMAD Gherkin TDD {args.command} — {project}")
            _print_report(report)
        elif args.command == "uninstall":
            report = uninstall(project)
            print(f"BMAD Gherkin TDD uninstall — {project}")
            _print_report(report)
        elif args.command == "status":
            print(json.dumps(install_status(project), indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
