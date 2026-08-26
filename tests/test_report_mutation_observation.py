"""The C1 observation report is read-only telemetry: it must exit 0 always and
never claim reuse has been applied (it only reports prospective reuse)."""

from __future__ import annotations

import json

import pytest

import scripts.report_mutation_observation as rmo


@pytest.fixture()
def commands_root(tmp_path) -> str:
    d = tmp_path / "commands"
    for name, kind, cand, duration in [
        ("mutation-full-abc", "mutation-full", "sha256:aaaa", 131.0),
        ("mutation-full-abc", "mutation-full", "sha256:aaaa", 131.0),
        ("pytest-x", "pytest", "sha256:bbbb", 3.0),
    ]:
        (d / name).mkdir(parents=True, exist_ok=True)
        (d / name / "summary.json").write_text(
            json.dumps(
                {
                    "command_kind": kind,
                    "candidate_id": cand,
                    "gate_verdict": "pass" if kind == "mutation-full" else None,
                    "exit_code": 0,
                    "duration_s": duration,
                    "journal_paths": ["mutants/x.meta"] if kind == "mutation-full" else [],
                }
            )
        )
    return str(d)


def test_reports_prospective_reuse_only(commands_root, capsys) -> None:
    rc = rmo.main(["--commands-root", commands_root])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 unique candidate(s)" in out
    assert "duplicate" not in out.lower() or "aa" in out


def test_empty_evidence_exits_zero(tmp_path) -> None:
    rc = rmo.main(["--commands-root", str(tmp_path / "missing")])
    assert rc == 0
