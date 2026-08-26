"""Behavioral vectors + safety/determinism tests for ``scripts/red_test_advisor.py``.

The advisor is advisory-only calibration tooling (C4). These tests pin:

* the conservative ruleset verdicts over a shared vector corpus,
* path-security rejection (escapes, symlinks, output containment),
* atomic writes without temp leftovers, and
* byte-identical payloads across processes and PYTHONHASHSEED values.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "red_test_advisor.py"
VECTORS = Path(__file__).parent / "fixtures" / "red_test_advisor_vectors.json"

_spec = importlib.util.spec_from_file_location("red_test_advisor_under_test", SCRIPT)
assert _spec is not None and _spec.loader is not None
advisor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(advisor)


def _build_project(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def _analyze_args(root: Path, evidence: Path, targets: list[str], output: Path) -> list[str]:
    args = [
        "analyze",
        "--project-root",
        str(root),
        "--evidence-root",
        str(evidence),
        "--scenario-id",
        "@s1",
    ]
    for nodeid in targets:
        args.extend(["--target", nodeid])
    args.extend(["--output", str(output)])
    return args


def _run_analyze(
    root: Path, evidence: Path, targets: list[str], output_name: str = "advisor.json"
) -> tuple[int, dict | None, Path]:
    output = evidence / output_name
    rc = advisor.main(_analyze_args(root, evidence, targets, output))
    payload = json.loads(output.read_text(encoding="utf-8")) if output.exists() else None
    return rc, payload, output


def test_script_exists() -> None:
    assert SCRIPT.is_file()


@pytest.mark.parametrize(
    "case", json.loads(VECTORS.read_text(encoding="utf-8")), ids=lambda case: case["name"]
)
def test_vector_corpus(case: dict, tmp_path: Path) -> None:
    root = _build_project(tmp_path, case["files"])
    rc, payload, _ = _run_analyze(root, tmp_path / "evidence", case["targets"])

    assert rc == 0
    assert payload is not None
    assert payload["verdict"] == case["expected_verdict"]
    assert payload["semantic_uncertainty"] is True
    rules = {signal["rule_id"] for signal in payload["signals"]}
    for rule_id in case.get("expected_rule_ids", []):
        assert rule_id in rules, f"missing {rule_id} in {sorted(rules)}"
    for rule_id in case.get("forbidden_rule_ids", []):
        assert rule_id not in rules, f"unexpected {rule_id} in {sorted(rules)}"
    reasons = set(payload["unsupported_reasons"])
    for reason in case.get("expected_unsupported_reasons", []):
        assert reason in reasons
    expected_target = case.get("expected_entry_target")
    if expected_target is not None:
        assert [entry["target"] for entry in payload["targets"]] == [expected_target]


def test_duplicate_targets_dedupe(tmp_path: Path) -> None:
    root = _build_project(tmp_path, {"t.py": "def test_a():\n    assert make() == 1\n"})
    rc, payload, _ = _run_analyze(root, tmp_path / "evidence", ["t.py::test_a", "t.py::test_a"])
    assert rc == 0 and payload is not None
    assert len(payload["targets"]) == 1


def test_parametrized_ids_share_one_entry(tmp_path: Path) -> None:
    source = "def make():\n    return 1\n\n\ndef test_a():\n    assert make() == 1\n"
    root = _build_project(tmp_path, {"t.py": source})
    rc, payload, _ = _run_analyze(
        root, tmp_path / "evidence", ["t.py::test_a[a]", "t.py::test_a[b]"]
    )
    assert rc == 0 and payload is not None
    assert [entry["target"] for entry in payload["targets"]] == ["t.py::test_a"]


# ---------------------------------------------------------------------------
# Determinism


def _subprocess_analyze(root: Path, evidence: Path, seed: str) -> bytes:
    output = evidence / "advisor.json"
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *_analyze_args(root, evidence, ["t.py::test_a"], output)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.encode("utf-8")


def test_byte_identical_across_hash_seeds_and_processes(tmp_path: Path) -> None:
    source = "def make():\n    return 42\n\n\ndef test_a():\n    assert make() == 42\n"
    root = _build_project(tmp_path, {"t.py": source})
    first = _subprocess_analyze(root, tmp_path / "ev0", "0")
    second = _subprocess_analyze(root, tmp_path / "ev1", "12345")
    assert first == second


# ---------------------------------------------------------------------------
# Path security


def _error_rc(args: list[str], capsys: pytest.CaptureFixture[str]) -> int:
    rc = advisor.main(args)
    err = capsys.readouterr().err.strip()
    assert err.startswith("{") and "error" in json.loads(err)
    return rc


def test_target_escape_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _build_project(tmp_path, {"t.py": "def test_a():\n    pass\n"})
    evidence = tmp_path / "evidence"
    rc = _error_rc(
        _analyze_args(root, evidence, ["../outside.py::test_a"], evidence / "advisor.json"),
        capsys,
    )
    assert rc == 2


def test_absolute_target_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _build_project(tmp_path, {"t.py": "def test_a():\n    pass\n"})
    evidence = tmp_path / "evidence"
    rc = _error_rc(
        _analyze_args(root, evidence, ["/etc/passwd::x"], evidence / "advisor.json"), capsys
    )
    assert rc == 2


def test_symlinked_target_component_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    real = _build_project(tmp_path, {"real/t.py": "def test_a():\n    pass\n"})
    root = tmp_path / "project_link"
    root.symlink_to(real, target_is_directory=True)
    evidence = tmp_path / "evidence"
    rc = _error_rc(
        _analyze_args(root, evidence, ["t.py::test_a"], evidence / "advisor.json"), capsys
    )
    assert rc == 2


def test_output_outside_evidence_root_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _build_project(tmp_path, {"t.py": "def test_a():\n    assert 1 == 1\n"})
    rc = _error_rc(
        _analyze_args(root, tmp_path / "evidence", ["t.py::test_a"], tmp_path / "evil.json"),
        capsys,
    )
    assert rc == 2


def test_symlinked_output_parent_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _build_project(tmp_path, {"t.py": "def test_a():\n    assert 1 == 1\n"})
    evidence = tmp_path / "evidence"
    outside = tmp_path / "outside"
    outside.mkdir()
    evidence.mkdir()
    (evidence / "sub").symlink_to(outside, target_is_directory=True)
    rc = _error_rc(
        _analyze_args(root, evidence, ["t.py::test_a"], evidence / "sub" / "a.json"), capsys
    )
    assert rc == 2
    assert not (outside / "a.json").exists()


def test_atomic_write_leaves_no_temp_files(tmp_path: Path) -> None:
    root = _build_project(tmp_path, {"t.py": "def test_a():\n    assert 1 == 1\n"})
    evidence = tmp_path / "evidence"
    rc, _, _ = _run_analyze(root, evidence, ["t.py::test_a"])
    assert rc == 0
    leftovers = [p.name for p in evidence.iterdir() if p.name.startswith(".advisor-")]
    assert leftovers == []


# ---------------------------------------------------------------------------
# compare subcommand


def _prepare_compare_inputs(tmp_path: Path) -> tuple[Path, Path]:
    root = _build_project(tmp_path, {"t.py": "def test_a():\n    assert make() == 1\n"})
    evidence = tmp_path / "evidence"
    rc, _, advisor_out = _run_analyze(root, evidence, ["t.py::test_a"])
    assert rc == 0
    review = evidence / "review.txt"
    review.write_text(
        "MUTANT-HUNTING REVIEW: strong — exact assertion present.\n", encoding="utf-8"
    )
    return advisor_out, review


def test_compare_agreement_and_binding(tmp_path: Path) -> None:
    advisor_path, review = _prepare_compare_inputs(tmp_path)
    evidence = tmp_path / "evidence"
    out = evidence / "comparison.json"
    rc = advisor.main(
        [
            "compare",
            "--advisor",
            str(advisor_path),
            "--llm-verdict",
            "strong",
            "--llm-review",
            str(review),
            "--evidence-root",
            str(evidence),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["agreement"] is True
    assert payload["advisor_verdict"] == "strong"
    assert payload["calibration_only"] is True
    assert payload["advisor_file_sha256"].startswith("sha256:")
    assert payload["llm_review_sha256"].startswith("sha256:")
    assert payload["result_sha256"].startswith("sha256:")


def test_compare_disagreement(tmp_path: Path) -> None:
    advisor_path, review = _prepare_compare_inputs(tmp_path)
    evidence = tmp_path / "evidence"
    out = evidence / "comparison.json"
    rc = advisor.main(
        [
            "compare",
            "--advisor",
            str(advisor_path),
            "--llm-verdict",
            "weak",
            "--llm-review",
            str(review),
            "--evidence-root",
            str(evidence),
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["agreement"] is False
    assert payload["advisor_verdict"] == "strong"
    assert payload["llm_verdict"] == "weak"


def test_compare_rejects_unknown_label(tmp_path: Path) -> None:
    advisor_path, review = _prepare_compare_inputs(tmp_path)
    evidence = tmp_path / "evidence"
    with pytest.raises(SystemExit) as excinfo:
        advisor.main(
            [
                "compare",
                "--advisor",
                str(advisor_path),
                "--llm-verdict",
                "certified",
                "--llm-review",
                str(review),
                "--evidence-root",
                str(evidence),
                "--output",
                str(evidence / "comparison.json"),
            ]
        )
    assert excinfo.value.code == 2


def test_compare_review_escape_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    advisor_path, _ = _prepare_compare_inputs(tmp_path)
    evidence = tmp_path / "evidence"
    outside_review = tmp_path / "outside-review.txt"
    outside_review.write_text("raw\n", encoding="utf-8")
    rc = _error_rc(
        [
            "compare",
            "--advisor",
            str(advisor_path),
            "--llm-verdict",
            "strong",
            "--llm-review",
            str(outside_review),
            "--evidence-root",
            str(evidence),
            "--output",
            str(evidence / "comparison.json"),
        ],
        capsys,
    )
    assert rc == 2
