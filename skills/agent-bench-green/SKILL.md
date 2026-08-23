---
name: agent-bench-green
description: Benchmark the TDD GREEN agent across multiple LLM models. Launches tdd-green-ornith in parallel with different models on the same hostile fixture, then evaluates implementation quality. Use when the user wants to benchmark, compare, or pick a model for the GREEN phase.
---

# Agent Bench GREEN — orchestrator

Benchmark de la fase TDD **GREEN** (`tdd-green-ornith`): lanza el mismo agente con varios
modelos sobre el mismo fixture hostil y evalúa/contrasta las implementaciones generadas.

**Esto es skill-driven.** Tú (el agente que corre esta skill) orquestas con `question`,
`bash` y la skill `agent-bench-green-eval`. No hay nada que hacer manualmente.

## Restricción técnica clave

La herramienta `task()` **no acepta `model`** — el modelo de un subagente lo fija su
config. Por eso el mismo agente con distintos modelos se lanza vía
`opencode run --model <X> --agent tdd-green-ornith`, que `launch.py` paraleliza internamente.

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
python3 -m agent_bench.green.launch --models <m1>,<m2>,... --timeout 1800
```
- `launch.py` crea un sandbox por modelo, lanza los `opencode run` **en paralelo**
  y espera a que todos terminen.
- Timeout 1800s por defecto (GREEN itera más que RED). `--timeout 0` = sin timeout.
- Al terminar escribe `manifest.json` en `_bmad-output/agent-bench/runs/green/<id>/`.
- **IMPORTANTE**: usar `setsid nohup` para que el proceso no se cancele si el usuario interrumpe.

### Paso 4 — Evaluar (scoreboard completo)
```bash
python3 -m agent_bench.green.eval.batch_eval --latest
```
- Evalúa cada implementación: gold tests + hidden tests + quality (HQG Tier A) + cheat detection.
- Escribe `scoreboard.json` e imprime la tabla comparativa.

### Paso 5 — Contraste con juez LLM
Invoca la skill `agent-bench-green-eval` para el veredicto cualitativo (juez LLM) que
contrasta cada implementación contra los objetivos del GREEN (contrato, SPEC-PINS, STANDARDS,
SOLID Tier B, antipatterns Tier B). Pásale el run dir del Paso 3.

### Paso 6 — Reportar
Presenta al usuario:
- Tabla completa (score, visible, hidden, quality, penalties).
- Veredicto del juez por modelo (7 dimensiones: contract, minimality, correctness, discipline, SOLID, AP, standards).
- Divergencias: hidden bajo + visible alto = overfit; quality bajo = implementación sucia.

## Manejo de fallos

- Si un modelo **no escribe implementación** (`no_output`): reportarlo como fallo de la misión GREEN.
- Si un modelo **timeout**: ídem. El bench no reintenta automáticamente.
- Si `launch.py` falla por `opencode` no encontrado: avisar al usuario.

## Archivos

- Fixture: `agent_bench/green/fixtures/green-hard/` (contrato 8 @s + stub + gold test + STANDARDS)
- Launch: `agent_bench/green/launch.py` (paraleliza `opencode run`)
- Batch eval: `agent_bench/green/eval/batch_eval.py` (scoreboard)
- Run pytest: `agent_bench/green/eval/run_pytest.py` (gold + hidden)
- Cheat detect: `agent_bench/green/eval/cheat_detect.py`
- Judge: `agent_bench/green/eval/judge.py` (juez LLM con Tier B)
- Surfaces: `agent_bench/green/eval/surfaces.yaml` (matriz de superficies)
- Runs: `_bmad-output/agent-bench/runs/green/<id>/`

## Garantías

- No toca código de producción (`src/`, `tests/` del módulo).
- El gate TDD está inactivo en los sandboxes (sin sprint-status in-progress).
- `--pure`: sin plugins.
- El golden impl vive fuera del sandbox (nunca se copia).
- Los hidden tests viven fuera del sandbox (nunca se copian).
- Closed loop: benchmark no se lanza si golden no pasa gold+hidden 100%.
