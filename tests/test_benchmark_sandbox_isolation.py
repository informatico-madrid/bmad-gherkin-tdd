from pathlib import Path

import pytest

from agent_bench.clean import launch as clean_launch
from agent_bench.green import launch as green_launch
from agent_bench.red import launch as red_launch
from agent_bench.refactor import launch as refactor_launch


def _snapshot(base: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(base): path.read_bytes()
        for path in base.rglob("*")
        if path.is_file()
    }


def _fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "fixture"
    (fixture / "src").mkdir(parents=True)
    (fixture / "tests" / "unit").mkdir(parents=True)
    (fixture / "src" / "quota_broker.py").write_text("fixture source\n")
    (fixture / "bitacora.md").write_text("contaminated bitacora\n")
    (fixture / "__pycache__").mkdir()
    (fixture / "__pycache__" / "stale.pyc").write_bytes(b"stale")
    return fixture


@pytest.mark.parametrize(
    "module",
    (red_launch, green_launch, clean_launch, refactor_launch),
)
def test_launchers_have_no_fixture_mutating_reset(module):
    assert not hasattr(module, "_reset_fixture")


def test_red_cleans_only_the_sandbox(tmp_path: Path, monkeypatch):
    fixture = _fixture(tmp_path)
    stale_test = fixture / "tests" / "unit" / "test_red_hard.py"
    stale_test.write_text("stale test\n")
    before = _snapshot(fixture)
    monkeypatch.setattr(red_launch, "FIXTURE_DIR", fixture)
    run_dir = tmp_path / "runs"
    run_dir.mkdir()

    sandbox = red_launch._create_sandbox(run_dir, "test/model")

    assert _snapshot(fixture) == before
    assert not (sandbox / "tests" / "unit" / "test_red_hard.py").exists()
    assert "| @s | Fase | Status | Test file |" in (
        sandbox / "bitacora.md"
    ).read_text()
    assert not list(sandbox.rglob("__pycache__"))


def test_green_cleans_only_the_sandbox(tmp_path: Path, monkeypatch):
    fixture = _fixture(tmp_path)
    seed = tmp_path / "green-seed.py"
    seed.write_text("canonical green stub\n")
    before = _snapshot(fixture)
    monkeypatch.setattr(green_launch, "FIXTURE_DIR", fixture)
    monkeypatch.setattr(green_launch, "SEED_FILE", seed)
    run_dir = tmp_path / "runs"
    run_dir.mkdir()

    sandbox = green_launch._create_sandbox(run_dir, "test/model")

    assert _snapshot(fixture) == before
    assert (
        sandbox / "src" / "quota_broker.py"
    ).read_text() == "canonical green stub\n"
    assert "| @s | Fase | Status | Test file |" in (
        sandbox / "bitacora.md"
    ).read_text()
    assert not list(sandbox.rglob("__pycache__"))


@pytest.mark.parametrize("module", (clean_launch, refactor_launch))
def test_seed_is_restored_only_in_clean_and_refactor_sandboxes(
    module, tmp_path: Path, monkeypatch
):
    fixture = _fixture(tmp_path)
    seed = tmp_path / "seed.py"
    seed.write_text("canonical seed\n")
    before = _snapshot(fixture)
    monkeypatch.setattr(module, "FIXTURE_DIR", fixture)
    monkeypatch.setattr(module, "SEED_FILE", seed, raising=False)
    run_dir = tmp_path / "runs"
    run_dir.mkdir()

    sandbox = module._create_sandbox(run_dir, "test/model")

    assert _snapshot(fixture) == before
    assert (sandbox / "src" / "quota_broker.py").read_text() == "canonical seed\n"
    assert not list(sandbox.rglob("__pycache__"))


@pytest.mark.parametrize("module", (green_launch, clean_launch, refactor_launch))
def test_real_seed_matches_checked_in_fixture(module):
    fixture_source = module.FIXTURE_DIR / "src" / "quota_broker.py"

    assert module.SEED_FILE.is_file()
    assert module.SEED_FILE.read_bytes() == fixture_source.read_bytes()
