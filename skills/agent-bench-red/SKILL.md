---
name: agent-bench-red
description: Benchmark the TDD RED agent across multiple LLM models. Launches tdd-red-ornith in parallel with different models on the same synthetic contract, then evaluates and compares. Use when the user wants to benchmark, compare, or pick a model for the RED phase.
---

# Agent Bench RED — orchestrator

Benchmark de la fase TDD **RED** (`tdd-red-ornith`): lanza el mismo agente con varios
modelos sobre el mismo contrato sintético y evalúa/contrasta los tests generados.

**Esto es skill-driven.** Tú (el agente que corre esta skill) orquestas con `question`,
`bash` y la skill `agent-bench-red-eval`. No hay nada que hacer manualmente.

## Restricción técnica clave

La herramienta `task()` **no acepta `model`** — el modelo de un subagente lo fija su
config. Por eso el mismo agente con distintos modelos se lanza vía
`opencode run --model <X> --agent tdd-red-ornith`, que `launch.py` paraleliza internamente.

## Workflow

### Paso 1 — Resolver modelos disponibles
Lee los proveedores de `~/.config/opencode/opencode.json` (clave `provider`) y construye
la lista `<provider>/<model>`. Si el usuario ya dio modelos, úsalos directamente.

### Paso 2 — Preguntar qué modelos benchear
Usa la herramienta `question` (multiple: true) con la lista de modelos disponibles.
Ofrece también "Type your own answer" para modelos custom. Si el usuario ya los indicó,
salta este paso.

### Paso 3 — Lanzar en paralelo
```bash
python3 -m agent_bench.red.launch --models <m1>,<m2>,... --timeout 600
```
- `launch.py` crea un sandbox por modelo, lanza los `opencode run` **en paralelo**
  y espera a que todos terminen. Bloquea hasta completar.
- Timeout 600s por modelo (el agente RED con reasoning xhigh tarda 2-6 min).
- Al terminar escribe `manifest.json` en `_bmad-output/agent-bench/runs/<id>/`.

### Paso 4 — Evaluar (scoreboard mecánico)
```bash
python3 -m agent_bench.red.eval.batch_eval --latest
```
- Evalúa el test de cada modelo con el scorer estático (AST).
- Marca `no_output` si un modelo no escribió test; `timeout`/`failed` según manifest.
- Escribe `scoreboard.json` e imprime la tabla comparativa.

### Paso 5 — Contraste con juez LLM
Invoca la skill `agent-bench-red-eval` para el veredicto cualitativo (juez LLM) que
contrasta cada test contra los objetivos del RED (PRODUCT-INTENT + contrato + guía de
mutantes). Pásale el run dir del Paso 3.

### Paso 6 — Reportar
Presenta al usuario:
- Tabla mecánica (score, superficies cubiertas, tests, penalizaciones).
- Veredicto del juez por modelo.
- Recomendación (mejor relación calidad/costo) si el usuario la pide.

## Manejo de fallos

- Si un modelo **no escribe test** (`no_output`): reportarlo como fallo de la misión RED,
  no como error del bench. Es un dato válido (ese modelo no cumple la misión).
- Si un modelo **timeout**: ídem, reportarlo. El bench no reintenta automáticamente.
- Si `launch.py` falla por `opencode` no encontrado: avisar al usuario.

## Archivos

- Fixture: `agent_bench/red/fixtures/red-hard/` (contrato + hueco + PRODUCT-INTENT)
- Launch: `agent_bench/red/launch.py` (paraleliza `opencode run`)
- Batch eval: `agent_bench/red/eval/batch_eval.py` (scoreboard)
- Scorer: `agent_bench/red/eval/static_score.py` (AST, 100% estático)
- Surfaces: `agent_bench/red/eval/surfaces.yaml` (matriz de superficies de mutantes)
- Runs: `_bmad-output/agent-bench/runs/<id>/`

## Garantías

- No toca código de producción (`src/`, `tests/` del módulo).
- El gate TDD está inactivo en los sandboxes (sin sprint-status in-progress).
- `--pure`: sin plugins.
- El scorer es 100% estático: no ejecuta pytest contra implementación (no hay impl).
