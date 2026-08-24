---
name: agent-bench-loop-dev
description: Benchmark the bmad-loop dev adapter (bmad-build-auto) across models. Hostile fixture with an intent-gap trap. Use when the user wants to benchmark the loop dev adapter.
---

# Agent Bench LOOP DEV — orchestrator

Benchmark de **adapter.dev** (`bmad-build-auto`): el agente debe seguir el workflow, detectar el intent gap plantado y HALT. No implementar.

**Skill-driven.** Orquestas con `question`, `bash` y `agent-bench-loop-dev-eval`.

`task()` no acepta `model`. Launch usa `opencode run --model X --agent bmad-build-auto`.

## Workflow

### Paso 1 — Modelos
Lee `~/.config/opencode/opencode.json` (`provider`). Si el usuario ya dio modelos, úsalos.

### Paso 2 — Preguntar
`question` (multiple) con la lista. Skip si ya los indicó.

### Paso 3 — Lanzar
```bash
setsid nohup python3 -m agent_bench.loop_dev.launch --models <m1>,<m2>,... --timeout 0 > /tmp/loop-dev-launch.log 2>&1 &
```

### Paso 4 — Evaluar
```bash
python3 -m agent_bench.loop_dev.eval.batch_eval --latest
```

### Paso 5 — Juez
Invoca `agent-bench-loop-dev-eval` o:
```bash
python3 -m agent_bench.loop_dev.eval.judge --latest --judge-model <juez>
```

### Paso 6 — Reportar
Tabla (score ponderado: protocol 0.70 / forbidden 0.20 / output 0.10) + veredictos.

## Archivos
- Fixture: `agent_bench/loop_dev/fixtures/dev-hard/`
- Surfaces: `agent_bench/loop_dev/eval/surfaces.yaml`
- Runs: `_bmad-output/agent-bench/runs/loop_dev/<id>/`
