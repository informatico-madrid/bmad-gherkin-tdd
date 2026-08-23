# agent_bench — Benchmark suite for OpenCode TDD agents

Aislado del módulo de producción. No se instala, no se toca el gate, no cambia el workflow TDD.
Evalúa agentes de las 4 fases TDD contra varios modelos para elegir el más barato-efectivo por fase.

## Ciclo TDD cubierto

| Fase | Agente | Benchmark | Qué evalúa |
|------|--------|-----------|------------|
| RED | `tdd-red-ornith` | `agent_bench/red/` | Texto del test (AST × 51 superficies) |
| GREEN | `tdd-green-ornith` | `agent_bench/green/` | Impl vs contrato + hidden + quality local |
| CLEAN | `tdd-clean-ornith` | `agent_bench/clean/` | cleaner-gate + coverage + anti-cascarón |
| REFACTOR | `tdd-refactor-ornith` | `agent_bench/refactor/` | Diseño mejorado + gate PASS + hidden PASS |

## Flujo por fase (skill-driven)

Cada fase tiene 2 skills: orchestration + evaluation. Workflow idéntico:

1. **Paso 1-2**: Resolver modelos / preguntar (skip si ya los dio)
2. **Paso 3**: `python3 -m agent_bench.<phase>.launch --models ... --timeout 0`
3. **Paso 4**: `python3 -m agent_bench.<phase>.eval.batch_eval --latest`
4. **Paso 5**: `python3 -m agent_bench.<phase>.eval.judge --latest --judge-model <model>`
5. **Paso 6**: Reportar tabla + veredictos

## Estructura

```
agent_bench/
  common/__init__.py              # shared: resolve_models, slugify, run_opencode
  README.md

  red/
    fixtures/red-hard/            # hueco (NotImplementedError)
    eval/surfaces.yaml            # 51 superficies AST
    eval/static_score.py          # scorer estático
    launch.py

  green/
    fixtures/green-hard/          # test gold + stub + 8 @s contract
    eval/golden/quota_broker.py   # reference impl
    eval/hidden/test_heldout.py   # 37 tests held-out
    eval/surfaces.yaml            # 24 conductual + 16 quality + 12 cheat
    eval/quality_local.py         # AST checkers (no HQG dependency)
    launch.py

  clean/
    fixtures/clean-hard/          # semilla SUCIA (tests pass, gate FAIL)
    fixtures/clean-hard/scripts/  # cleaner_gate.py + principles.py + scan_mutation_sites.py
    eval/golden/quota_broker.py   # clean reference (gate PASS)
    eval/hidden/test_heldout.py   # 37 tests held-out
    launch.py

  refactor/
    fixtures/refactor-hard/       # semilla funcional (gate PASS, diseño pobre)
    eval/golden/quota_broker.py   # refactored reference
    eval/hidden/test_heldout.py   # 37 tests held-out
    launch.py
```

## Closed loop (antes de lanzar modelos)

Cada bench tiene que pasar esta tabla antes de ser usado:

| Estado | Tests | Hidden | Gate | Score |
|--------|-------|--------|------|-------|
| stub/semilla FAIL | 0% | 0% | FAIL | 0 |
| golden PASS | 100% | 100% | PASS | alto |

Si algún estado no se cumple → el bench no está listo.

## Evaluación por fase

**RED**: 100% estática. AST sobre `surfaces.yaml`. No ejecuta pytest contra impl.

**GREEN**: Gold tests (gate) + hidden tests (ranking) + quality local (AST) + cheat detect.
Fórmula: `0.30*vis + 0.45*hid + 0.15*quality + 0.10*mission - 5*penalty`.

**CLEAN**: cleaner-gate (KISS/DRY/YAGNI/LoD/CoI/scan) + hidden + anti-cascarón.
Fórmula: `0.40*gate + 0.35*hidden + 0.15*mission + 0.10*mission - 5*penalty`.

**REFACTOR**: hidden (design no puede romper) + gate (no puede romper) + juez (design improvement).
Fórmula: `0.45*hidden + 0.25*mission + 0.15*gate + 0.15*mission - 5*penalty`.

## Robustez

- **`setsid nohup`**: lanzar en background para que no se cancele por interrupción.
- **`--timeout 0`**: sin timeout para modelos lentos (bunker-local).
- **Cache reset**: autouse fixture en hidden tests para evitar leakage entre tests.
- **FIXTURE≠TARGET**: sin `alpha`/`beta`/`quota-lab` como expected values.
- **No toca producción**: ni `hooks/`, ni `plugins/`, ni `installer.py`, ni skills TDD.

## Lo que NO hace

- No ejecuta mutmut (RELEASE es del coordinador).
- No encadena salidas de un modelo como input de otro.
- No instala skills en el wheel.
- No modifica `opencode/agents/opencode.json.template`.
