---
name: agent-bench-libs-coordinator
description: Benchmark the bmad-loop-coordinator agent. Tests orchestration decisions against 6 scenarios derived from the coordinator's Critical Rules. Use when the user wants to benchmark coordinator decision quality.
---

# Agent Bench COORDINATOR — orchestrator

Benchmark de **bmad-loop-coordinator**: el agente recibe 6 escenarios con un estado de proyecto simulado y debe tomar la decisión de orquestación correcta, derivada de las Critical Rules del coordinator.

## Workflow

### Paso 3 — Lanzar
```bash
python3 -m agent_bench.bmad_libs_coordinator.launch --models <m1>,<m2>,... --timeout 600
```
### Paso 4 — Evaluar
```bash
python3 -m agent_bench.bmad_libs_coordinator.eval.batch_eval --latest
```
### Paso 5 — Juez (calidad de las decisiones, rigor de las reglas)
### Paso 6 — Reportar

## Cómo funciona
- Cada modelo recibe 6 escenarios + las Critical Rules del coordinator
- Produce `decisions.json` con su decisión por escenario
- El evaluador compara contra el expected_decision usando heurísticas deterministas
- El juez evalúa la calidad y rigor de las decisiones

## Archivos
- Fixture: `agent_bench/bmad_libs_coordinator/fixtures/coordinator-hard/`
- Scenarios: `agent_bench/bmad_libs_coordinator/eval/golden/scenarios.yaml`
- Batch eval: `agent_bench/bmad_libs_coordinator/eval/batch_eval.py`
- Runs: `_bmad-output/agent-bench/runs/bmad_libs_coordinator/<id>/`
