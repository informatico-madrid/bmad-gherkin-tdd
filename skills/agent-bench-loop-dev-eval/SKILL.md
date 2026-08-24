---
name: agent-bench-loop-dev-eval
description: Evaluate loop_dev bench runs. Deterministic surfaces + LLM judge. Use after agent-bench-loop-dev produced a run.
---

# Agent Bench LOOP DEV — evaluator

1. `python3 -m agent_bench.loop_dev.eval.batch_eval --latest`
2. `python3 -m agent_bench.loop_dev.eval.judge --latest --judge-model <juez>`
3. Contrastar: protocol bajo = no detectó el intent gap; forbidden bajo = tocó src/ o sprint-status.
