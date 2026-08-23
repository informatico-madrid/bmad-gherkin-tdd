---
name: agent-bench-clean
description: Benchmark the TDD CLEAN agent across multiple LLM models. Launches tdd-clean-ornith in parallel with different models on the same dirty semilla, then evaluates cleaner-gate + behavior preservation. Use when the user wants to benchmark, compare, or pick a model for the CLEAN phase.
---

# Agent Bench CLEAN — orchestrator

Benchmark de la fase TDD **CLEAN** (`tdd-clean-ornith`): lanza el mismo agente con varios
modelos sobre la misma semilla sucia y evalúa si arreglan el cleaner-gate sin romper tests.

**Esto es skill-driven.** Orquesta con `question`, `bash` y la skill `agent-bench-clean-eval`.

## Workflow

### Paso 1 — Resolver modelos disponibles
Lee `~/.config/opencode/opencode.json` o usa los que el usuario ya dio.

### Paso 2 — Preguntar (skip si ya los indicó)

### Paso 3 — Lanzar en paralelo
```bash
python3 -m agent_bench.clean.launch --models <m1>,<m2>,... --timeout 1800
```
- Timeout 1800s por defecto; `--timeout 0` = sin timeout.
- `setsid nohup` para no cancelar por interrupción.

### Paso 4 — Evaluar
```bash
python3 -m agent_bench.clean.eval.batch_eval --latest
```
- Scoreboard: gate + hidden + visible + cheat.

### Paso 5 — Juez LLM (Tier A + Tier B)
```bash
python3 -m agent_bench.clean.eval.judge --latest --judge-model <model>
```
- 8 dimensiones: behavior_preservation, structural_only, shell_resistance, contract_intact, clean_discipline, solid_semantic, antipattern_semantic, standards_compliance.

### Paso 6 — Reportar
Tabla + veredicto del juez por modelo.

## Archivos

- Fixture: `agent_bench/clean/fixtures/clean-hard/`
- Launch: `agent_bench/clean/launch.py`
- Batch eval: `agent_bench/clean/eval/batch_eval.py`
- Judge: `agent_bench/clean/eval/judge.py`
- Runs: `_bmad-output/agent-bench/runs/clean/<id>/`
