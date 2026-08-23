---
name: agent-bench-refactor-eval
description: Evaluate TDD REFACTOR bench results. Use after agent-bench-refactor has produced a run.
---

# Agent Bench REFACTOR — evaluator

## Workflow

### Paso 1 — Scoreboard
```bash
python3 -m agent_bench.refactor.eval.batch_eval --latest
```

### Paso 2 — Juez LLM (compares semilla vs refactored impl)
```bash
python3 -m agent_bench.refactor.eval.judge --latest --judge-model <model>
```

### Paso 3 — Combinar y reportar
