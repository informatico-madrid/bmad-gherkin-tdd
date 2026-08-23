---
name: agent-bench-refactor
description: Benchmark the TDD REFACTOR agent across multiple LLM models. Launches tdd-refactor-ornith in parallel with different models on the same working implementation, then evaluates design improvement + behavior preservation. Use when the user wants to benchmark, compare, or pick a model for the REFACTOR phase.
---

# Agent Bench REFACTOR — orchestrator

Benchmark de la fase TDD **REFACTOR** (`tdd-refactor-ornith`): lanza el mismo agente con varios
modelos sobre una implementación funcional pero de diseño pobre, y evalúa si mejora el diseño sin romper tests.

## Workflow

### Paso 1 — Resolver modelos
### Paso 2 — Preguntar (skip si ya los indicó)
### Paso 3 — Lanzar
```bash
python3 -m agent_bench.refactor.launch --models <m1>,<m2>,... --timeout 1800
```
### Paso 4 — Evaluar
```bash
python3 -m agent_bench.refactor.eval.batch_eval --latest
```
### Paso 5 — Juez LLM
```bash
python3 -m agent_bench.refactor.eval.judge --latest --judge-model <model>
```
### Paso 6 — Reportar

## Archivos
- Fixture: `agent_bench/refactor/fixtures/refactor-hard/`
- Launch: `agent_bench/refactor/launch.py`
- Batch eval: `agent_bench/refactor/eval/batch_eval.py`
- Judge: `agent_bench/refactor/eval/judge.py`
- Runs: `_bmad-output/agent-bench/runs/refactor/<id>/`
