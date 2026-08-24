---
name: agent-bench-libs-resolve
description: Benchmark the bmad-loop-resolve agent. Tests ability to disambiguate a frozen spec with a planted ambiguity and produce a valid resolution. Use when the user wants to benchmark resolve quality.
---

# Agent Bench RESOLVE — orchestrator

Benchmark de **bmad-loop-resolve** (adaptado a no-interactivo): el agente debe resolver una escalada CRITICAL desambiguando un spec frozen con una ambigüedad plantada.

## Workflow

### Paso 3 — Lanzar
```bash
python3 -m agent_bench.bmad_libs_resolve.launch --models <m1>,<m2>,... --timeout 600
```
### Paso 4 — Evaluar
```bash
python3 -m agent_bench.bmad_libs_resolve.eval.batch_eval --latest
```
### Paso 5 — Juez (calidad de la desambiguación, edición mínima del spec)
### Paso 6 — Reportar

## Cómo funciona
- Cada modelo lee `context.json` + spec frozen
- Decide la semántica correcta (deny precedence over allow en este fixture)
- Escribe `resolution.json` + edita el spec mínimamente
- La validación comprueba schema, semántica correcta, no-tocar sprint-status

## Archivos
- Fixture: `agent_bench/bmad_libs_resolve/fixtures/resolve-hard/`
- Golden: `agent_bench/bmad_libs_resolve/eval/golden/resolution.json`
- Validator: `agent_bench/bmad_libs_resolve/eval/validate.py`
- Runs: `_bmad-output/agent-bench/runs/bmad_libs_resolve/<id>/`
