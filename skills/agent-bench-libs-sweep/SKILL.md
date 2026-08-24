---
name: agent-bench-libs-sweep
description: Benchmark the bmad-loop-sweep agent across multiple LLM models. Tests ability to classify deferred-work entries against actual code. Use when the user wants to benchmark sweep triage quality.
---

# Agent Bench SWEEP — orchestrator

Benchmark de **bmad-loop-sweep**: el agente debe clasificar cada entrada `open` de un ledger `deferred-work.md` contra el código real, en una de 5 categorías: already_resolved / bundles / blocked / skip / decisions.

## Workflow

### Paso 1-2 — Modelos (skip si ya los dio el usuario)
### Paso 3 — Lanzar
```bash
python3 -m agent_bench.bmad_libs_sweep.launch --models <m1>,<m2>,... --timeout 1800
```
### Paso 4 — Evaluar
```bash
python3 -m agent_bench.bmad_libs_sweep.eval.batch_eval --latest
```
### Paso 5 — Juez (calidad de intents, options, evidencia)
### Paso 6 — Reportar

## Cómo funciona
- Cada modelo corre `bmad-loop-sweep` en automation-mode sobre el fixture `sweep-hard`
- El modelo lee el ledger + código y escribe `result.json` con la partición
- La validación compara contra el golden (partición + schema + evidencia)

## Archivos
- Fixture: `agent_bench/bmad_libs_sweep/fixtures/sweep-hard/`
- Golden: `agent_bench/bmad_libs_sweep/eval/golden/result.json`
- Validator: `agent_bench/bmad_libs_sweep/eval/validate.py`
- Runs: `_bmad-output/agent-bench/runs/bmad_libs_sweep/<id>/`
