# Contributing to BMAD Gherkin TDD

Thanks for considering a contribution. This document describes the ground rules so
everyone can move fast without breaking the module's contract.

## Code of Conduct

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## How to contribute

1. Open an issue first for anything non-trivial (bug, feature, design discussion) so
   we agree on the direction before you invest time.
2. Fork the repository and create a feature branch (`git checkout -b feat/your-change`).
3. Make your change with tests. The module enforces TDD itself — write a failing test
   first, then make it pass.
4. Run the local quality gate (see below).
5. Open a pull request referencing the issue.

## Local development

```bash
uv sync --extra dev        # or: pip install -e ".[dev]"
uv run pytest              # full test suite
uv run ruff check .        # lint
uv run ruff format .       # format
uv build                   # build sdist + wheel (verifies the payload stages)
```

## What to keep in mind

- **Python 3.11+ only**, stdlib-first. The gate and resolver run on plain `python3`
  (no framework), matching what a BMAD project will invoke them with.
- **Never weaken the gate.** `hooks/tdd_cycle_gate.py` is the forcing function for the
  TDD bitácora. Behavior-preserving refactors are welcome; relaxing enforcement is not.
- **CLI must stay self-contained.** If you add a payload asset, also stage it in the
  `setup.py` build shim and the `MANIFEST.in`; the installed wheel must be able to run
  `bmad-gherkin-tdd install --project <path>` with no checkout present.
- **No secrets.** Never commit keys, tokens, or credentials.
- **Keep commits small and conventional** (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`).

## Testing conventions

- New gate transitions need a black-box test in `tests/test_tdd_cycle_gate_fb70.py` or
  `tests/test_tdd_security_lock.py`.
- New installer behavior needs a test in `tests/test_installer.py` against a `tmp_path`
  project.
- Coordinator wording changes must keep `tests/test_coordinator_instruction_consistency.py`
  and `tests/test_bmad_dev_auto_handoff.py` green.
