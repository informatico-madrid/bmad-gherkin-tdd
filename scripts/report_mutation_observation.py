"""C1 observation report (read-only).

Phase-0 telemetry over a completed mutmut full-gate evidence directory: it
never reuse-applies anything, it only reports what a future proportional-to-
change reuse WOULD have saved, so the authority invariant (full in live runs
once, inconditionally) is untouched.

Reads ``evidence/commands/*/summary.json`` produced by ``run_evidence.py`` and
prints a compact table keyed by ``candidate_id``. Reuse is only ever
*prospective*: a candidate is reported as reuse-eligible when its full-gate run
already exists in this evidence tree with the same non-empty ``journal_paths``
signature (the shared journal digest signalling the change was contained).

Exit 0 always; this tool has no gate authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_KIND = "mutation-full"


def _load_summaries(commands_root: Path) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for summary in sorted(commands_root.glob("*/summary.json")):
        try:
            with summary.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        if data.get("command_kind") != _KIND:
            continue
        data["_dir"] = summary.parent.name
        out.append(data)
    return out


def _report(summaries: list[dict[str, object]]) -> None:
    print(f"{'run':<22} {'rc':<3} {'dur_s':<7} {'candidate':<18} {'journals':<4} verdict")
    print("-" * 82)
    seen: set[str] = set()
    for s in summaries:
        cand = str(s.get("candidate_id", ""))
        dup = cand in seen
        seen.add(cand)
        journals = s.get("journal_paths") or []
        verdict = s.get("gate_verdict") or s.get("verdict") or ""
        try:
            duration = float(s.get("duration_s", 0))
        except (TypeError, ValueError):
            duration = 0.0
        print(
            f"{str(s.get('_dir', '')):<22} {str(s.get('exit_code', '')):<3} "
            f"{duration:<7.1f} "
            f"{(cand[:16]) + ('…' if len(cand) > 16 else ''):<18} "
            f"{len(journals):<4} {verdict}{'  (dup)' if dup else ''}"
        )
    print("-" * 82)
    print(f"Summary: {len(summaries)} full-gate evidence run(s); {len(seen)} unique candidate(s).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--commands-root", required=True, help="Path to evidence/commands")
    args = parser.parse_args(argv)
    root = Path(args.commands_root)
    if not root.is_dir():
        print(f"no evidence commands root at {root}")
        return 0
    _report(_load_summaries(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
