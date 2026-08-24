---
name: agent-bench-loop-review
description: Benchmark the bmad-loop review adapter across models. Hostile fixture with a planted bug and a pre-existing decoy. Use when the user wants to benchmark the loop review adapter.
---

# Agent Bench LOOP REVIEW — orchestrator

Benchmark de **adapter.review**: diagnosticar, escribir repair-brief, no implementar.

`task()` no acepta `model`. Launch usa `opencode run --model X --agent bmad-build-auto`.

## Workflow

### Paso 1-2 — Modelos / question (skip si ya los dio)

### Paso 3 — Lanzar
```bash
setsid nohup python3 -m agent_bench.loop_review.launch --models <m1>,<m2>,... --timeout 0 > /tmp/loop-review-launch.log 2>&1 &
```

### Paso 4 — Evaluar
```bash
python3 -m agent_bench.loop_review.eval.batch_eval --latest
```

### Paso 5 — Juez
Invoca `agent-bench-loop-review-eval` o:
```bash
python3 -m agent_bench.loop_review.eval.judge --latest --judge-model <juez>
```

### Paso 6 — Reportar

## Archivos
- Fixture: `agent_bench/loop_review/fixtures/review-hard/`
- Surfaces: `agent_bench/loop_review/eval/surfaces.yaml`
- Runs: `_bmad-output/agent-bench/runs/loop_review/<id>/`
