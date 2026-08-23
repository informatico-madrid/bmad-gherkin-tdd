---
name: agent-bench-clean-eval
description: Evaluate TDD CLEAN bench results. Use after agent-bench-clean has produced a run.
---

# Agent Bench CLEAN — evaluator

Contrasta las implementaciones contra cleaner-gate + behavior + discipline.

## Workflow

### Paso 1 — Scoreboard
```bash
python3 -m agent_bench.clean.eval.batch_eval --latest
```

### Paso 2 — Juez LLM
```bash
python3 -m agent_bench.clean.eval.judge --latest --judge-model <model>
```

### Paso 3 — Combinar y reportar

## Archivos
- `agent_bench/clean/eval/batch_eval.py`
- `agent_bench/clean/eval/judge.py`
