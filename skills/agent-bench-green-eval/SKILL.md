---
name: agent-bench-green-eval
description: Evaluate and contrast TDD GREEN bench results. Runs gold+hidden tests, quality checks, cheat detection, and an LLM judge with Tier B SOLID/AP patterns. Use after agent-bench-green has produced a run.
---

# Agent Bench GREEN — evaluator

Contrasta las implementaciones generadas por cada modelo contra los **objetivos del GREEN**
y emite la comparación final. Combina tres capas:

1. **Mecánica** (determinista): pytest gold + hidden + cheat detection.
2. **Calidad** (determinista): HQG Tier A (SOLID + principles + antipatterns).
3. **Juez LLM** (cualitativa con Tier B): veredicto razonado contra contrato + STANDARDS + SOLID/AP Tier B.

## Input

El run dir producido por `agent-bench-green` (p.ej. `_bmad-output/agent-bench/runs/green/<id>/`).
Si no se indica, usa el más reciente (`--latest`).

## Workflow

### Paso 1 — Scoreboard mecánico
```bash
python3 -m agent_bench.green.eval.batch_eval --latest
```
- Evalúa cada implementación con: gold tests, hidden tests, quality (HQG Tier A), cheat detection.
- Escribe `scoreboard.json` e imprime la tabla.

### Paso 2 — Juez LLM (Tier A + Tier B)
```bash
python3 -m agent_bench.green.eval.judge --latest --judge-model <modelo-juez>
```
- `<modelo-juez>`: idealmente un modelo **distinto y fuerte**.
- El juez evalúa 7 dimensiones (1–5): contract_realization, minimality, correctness, green_discipline, solid_semantic, antipattern_semantic, standards_compliance.
- Recibe: impl + contrato + SPEC-PINS + STANDARDS + resultados gold/hidden.
- Escribe `judge_verdicts.json`.

### Paso 3 — Combinar y contrastar
Lee `scoreboard.json` y `judge_verdicts.json`. Para cada modelo, une:
- Score mecánico (visible + hidden + quality + penalties).
- Veredicto del juez (7 dims + overall + frase).

Detecta divergencias:
- visible alto + hidden bajo → **overfit** (memorizó el gold).
- quality bajo + hidden alto → **implementación sucia** (ignoró STANDARDS).
- solid_semantic bajo → **problemas arquitectónicos** (God class, tight coupling).
- antipattern_semantic bajo → **code smells** (Lava Flow, Boat Anchor, etc.).

### Paso 4 — Reportar
Presenta la tabla final y el contraste. Si el usuario pide recomendación, da el modelo con
mejor relación calidad/costo.

## Interpretación

- `no_output` en el scoreboard = el modelo **no cumplió la misión GREEN** (no escribió impl).
- `timeout` = el modelo no terminó en el tiempo dado.
- Cheat penalties > 0 = el modelo hizo trampas (test tamper, hardcode, mock in SUT, etc.).
- Hidden bajo = overfit. Visible alto + hidden bajo = memorización.

## Archivos

- `agent_bench/green/eval/batch_eval.py` (scoreboard)
- `agent_bench/green/eval/run_pytest.py` (gold + hidden)
- `agent_bench/green/eval/cheat_detect.py` (discipline)
- `agent_bench/green/eval/judge.py` (juez LLM con Tier B)
- `agent_bench/green/eval/surfaces.yaml` (matriz de superficies)
- Salidas: `<run_dir>/scoreboard.json`, `<run_dir>/judge_verdicts.json`
