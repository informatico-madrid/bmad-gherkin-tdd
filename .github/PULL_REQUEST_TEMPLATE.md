## Summary

<!-- What this change does and why. Link the issue it closes. -->

## Test plan

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` passes
- [ ] `uv run ruff format --check .` passes
- [ ] If the installer changed: `uv build` still stages the payload into the wheel

## Checklist

- [ ] No secrets committed
- [ ] Behavior of `hooks/tdd_cycle_gate.py` not weakened (unless intentional + justified)
- [ ] Coordinator lifecycle unchanged: `bmad-dev-auto` still owns Verify → Review → closure
