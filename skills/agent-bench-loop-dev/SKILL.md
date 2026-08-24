---
name: agent-bench-loop-dev
description: Benchmark the Build Auto dev adapter across multiple LLM models. Tests protocol compliance against hostile fixture with intent gap, dirty tree, and sprint-status traps. Use when the user wants to benchmark the dev adapter.
---

# Agent Bench LOOP DEV — orchestrator

Benchmark de **adapter.dev** (bmad-build-auto): lanza el mismo agente con varios modelos sobre el mismo fixture hostil y evalúa si sigue el protocolo correctamente.

## Workflow

### Paso 1 — Resolver modelos
### Paso 2 — Preguntar qué modelos benchear
### Paso 3 — Lanzar en paralelo
```bash
python3 -m agent_bench.loop_dev.launch --models <m1>,<m2>,... --timeout 600
```
### Paso 4 — Evaluar
```bash
python3 -m agent_bench.loop_dev.eval.batch_eval --latest
```
### Paso 5 — Juez LLM
```bash
python3 -m agent_bench.loop_dev.eval.judge --latest --judge-model <modelo-juez>
```
### Paso 6 — Reportar

## Archivos
- Fixture: `agent_bench/loop_dev/fixtures/dev-hard/`
- Surfaces: `agent_bench/loop_dev/eval/surfaces.yaml`
- Batch eval: `agent_bench/loop_dev/eval/batch_eval.py`
- Judge: `agent_bench/loop_dev/eval/judge.py`
- Runs: `_bmad-output/agent-bench/runs/loop_dev/<id>/`
