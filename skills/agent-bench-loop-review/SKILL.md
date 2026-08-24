---
name: agent-bench-loop-review
description: Benchmark the Build Auto review adapter across multiple LLM models. Tests review protocol compliance against hostile fixture with bug detection, triage, and role discipline traps. Use when the user wants to benchmark the review adapter.
---

# Agent Bench LOOP REVIEW — orchestrator

Benchmark de **adapter.review** (bmad-build-auto step-04): lanza el mismo agente con varios modelos sobre el mismo fixture hostil y evalúa si sigue el protocolo de review correctamente.

## Workflow

### Paso 1 — Resolver modelos
### Paso 2 — Preguntar qué modelos benchear
### Paso 3 — Lanzar en paralelo
```bash
python3 -m agent_bench.loop_review.launch --models <m1>,<m2>,... --timeout 600
```
### Paso 4 — Evaluar
```bash
python3 -m agent_bench.loop_review.eval.batch_eval --latest
```
### Paso 5 — Juez LLM
```bash
python3 -m agent_bench.loop_review.eval.judge --latest --judge-model <modelo-juez>
```
### Paso 6 — Reportar

## Archivos
- Fixture: `agent_bench/loop_review/fixtures/review-hard/`
- Surfaces: `agent_bench/loop_review/eval/surfaces.yaml`
- Batch eval: `agent_bench/loop_review/eval/batch_eval.py`
- Judge: `agent_bench/loop_review/eval/judge.py`
- Runs: `_bmad-output/agent-bench/runs/loop_review/<id>/`
