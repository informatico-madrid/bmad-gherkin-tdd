---
name: agent-bench-red-eval
description: Evaluate and contrast TDD RED bench results. Runs the mechanical scorer over every model's test and an LLM judge against the RED objectives, then produces the final comparison. Use after agent-bench-red has produced a run.
---

# Agent Bench RED — evaluator

Contrasta los tests generados por cada modelo contra los **objetivos del RED** y emite
la comparación final. Combina dos capas:

1. **Mecánica** (determinista): scorer estático AST sobre la matriz de superficies de mutantes.
2. **Juez LLM** (cualitativa): veredicto razonado contra PRODUCT-INTENT + contrato + guía.

## Input

El run dir producido por `agent-bench-red` (p.ej. `_bmad-output/agent-bench/runs/<id>/`).
Si no se indica, usa el más reciente (`--latest`).

## Workflow

### Paso 1 — Scoreboard mecánico
```bash
python3 -m agent_bench.red.eval.batch_eval --latest
```
- Evalúa cada test con `static_score.py` (AST, sin ejecutar pytest contra impl).
- Escribe `scoreboard.json` e imprime la tabla (score, superficies, tests, penalizaciones).

### Paso 2 — Juez LLM
```bash
python3 -m agent_bench.red.eval.judge --latest --judge-model <modelo-juez>
```
- `<modelo-juez>`: idealmente un modelo **distinto y fuerte** (para no sesgar). Pregunta al
  usuario si hay duda. Con los modelos actuales, `nan/mimo-v2.5` sirve de juez.
- El juez lee cada test + PRODUCT-INTENT + contrato + principios de mutantes y devuelve un
  veredicto JSON por dimensión (1-5): contract_fidelity, assertion_density, mutant_coverage,
  fixture_discipline, correctness, overall + una frase de veredicto.
- Escribe `judge_verdicts.json`.

### Paso 3 — Combinar y contrastar
Lee `scoreboard.json` y `judge_verdicts.json`. Para cada modelo, une:
- Score mecánico + superficies cubiertas + penalizaciones.
- Veredicto del juez (overall + frase).

Detecta divergencias: si el scorer dice alto y el juez bajo (o viceversa), señálalo — suele
indicar un test que "cubre superficies" pero con aserciones débiles, o al revés.

### Paso 4 — Reportar
Presenta la tabla final y el contraste. Si el usuario pide recomendación, da el modelo con
mejor relación calidad/costo (superficies + juez alto, costo bajo).

## Interpretación

- `no_output` en el scoreboard = el modelo **no cumplió la misión RED** (no escribió test).
  Es un dato válido, no un error del bench.
- `timeout` = el modelo no terminó en el tiempo dado.
- Penalizaciones > 0 = el test incurrió en antipatrones (loose asserts, sample leak, etc.).

## Archivos

- `agent_bench/red/eval/batch_eval.py` (scoreboard mecánico)
- `agent_bench/red/eval/judge.py` (juez LLM)
- `agent_bench/red/eval/static_score.py` (scorer AST)
- `agent_bench/red/eval/surfaces.yaml` (matriz de superficies)
- Salidas: `<run_dir>/scoreboard.json`, `<run_dir>/judge_verdicts.json`
