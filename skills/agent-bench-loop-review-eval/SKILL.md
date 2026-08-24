---
name: agent-bench-loop-review-eval
description: Evaluate loop_review bench runs. Deterministic surfaces + LLM judge. Use after agent-bench-loop-review produced a run.
---

# Agent Bench LOOP REVIEW — evaluator

1. `python3 -m agent_bench.loop_review.eval.batch_eval --latest`
2. `python3 -m agent_bench.loop_review.eval.judge --latest --judge-model <juez>`
3. Contrastar: sin repair-brief = no hizo el trabajo; src editado = violó el rol.
