# agent_bench — Benchmark suite for OpenCode agents

Aislado del módulo de producción (`bmad-gherkin-tdd`). No se instala, no se toca el gate,
no cambia el workflow TDD. Su único propósito: **evaluar agentes** (de momento el RED de TDD)
contra varios modelos para elegir el más barato-efectivo por fase.

## Uso previsto (skill-driven)

En una sesión de OpenCode:
1. Invocar la skill **`agent-bench-red`** → pregunta qué modelos, lanza el agente RED en
   paralelo con cada uno sobre el mismo contrato sintético.
2. Al terminar, invoca **`agent-bench-red-eval`** → scoreboard mecánico + juez LLM que
   contrasta cada test contra los objetivos del RED.

Restricción técnica: `task()` no acepta `model`, así que el mismo agente con distintos
modelos se lanza vía `opencode run --model X --agent tdd-red-ornith`, que `launch.py`
paraleliza internamente (ThreadPoolExecutor).

## Estructura

```
agent_bench/
  README.md
  red/
    fixtures/red-hard/          # fixture sintético (Quota Broker), agnóstico de dominio
      PRODUCT-INTENT.md         # PRODUCT-INTENT ficticio (FIXTURE≠TARGET)
      tests/contracts/red-hard.feature   # 4 @s APPROVED
      src/quota_broker.py       # hueco (solo firmas + NotImplementedError)
      _bmad/custom/tdd-red.toml # persistent facts del sandbox
      .opencode/opencode.json   # agent RED como PRIMARY (para opencode run --agent)
      bitacora.md
    eval/
      surfaces.yaml             # matriz canónica (51 superficies de mutantes)
      static_score.py           # scorer estático (AST-based)
      batch_eval.py             # evalúa todos los modelos de un run + scoreboard
      judge.py                  # juez LLM (contrasta contra objetivos del RED)
      tests/test_static_score.py
    launch.py                   # resetea fixture, crea sandboxes, lanza en paralelo
```

## Ejecución manual (equivalente a las skills)

```bash
# 1. Lanzar en paralelo contra N modelos (timeout 600s c/u)
python3 -m agent_bench.red.launch --models nan/deepseek-v4-flash,nan/mimo-v2.5 --timeout 600

# 2. Scoreboard mecánico del último run
python3 -m agent_bench.red.eval.batch_eval --latest

# 3. Juez LLM (modelo juez distinto y fuerte)
python3 -m agent_bench.red.eval.judge --latest --judge-model nan/mimo-v2.5

# Dry run (solo crear sandboxes, sin lanzar opencode)
python3 -m agent_bench.red.launch --models nan/mimo-v2.5 --dry-run
```

Salidas por run en `_bmad-output/agent-bench/runs/<id>/`:
`manifest.json` (estado/elapsed por modelo), `scoreboard.json` (mecánico),
`judge_verdicts.json` (juez), y `<model-slug>/tests/unit/test_red_hard.py` (test generado).

## Evaluación

- **100% estática** (capa mecánica): AST sobre la matriz `surfaces.yaml`. No ejecuta pytest
  contra implementación (no hay impl; el SUT es un hueco). La calidad se mide en el TEXTO del test.
- **Operadores mutmut §2**: números, strings XX-wrap, comparaciones, bool, in/is, break/continue,
  return-None, defaults, kwargs, aritmética.
- **Técnicas §4**: densas, fronteras exactas, strings exactos, spies, defaults-sin-kwarg,
  acumulador asimétrico, contar iteraciones, truth table TF/FT, hypothesis, caplog, excepción tipada.
- **H-cases**: H1 wiring+is, H2 clock, H3 log, H4 truth table, H6 fallback, H7 argv-order,
  H8 stop-count, H10 cache, H11 límite, H14 XX-wrap, H15 None/0/False, H18 default,
  H19 unit-only, H20 pathmap.
- **Equivalentes §5**: A iter-count, B límite público, C clave ausente, D inalcanzable,
  E timeout-spy, G sentinel `__eq__`, H log-msg. (F roundtrip es `llm_only`, fuera del denominator.)
- **Forbiddens** (penalizan): loose `is not None`, loose `'x' in str(...)`, `len(x) > 0`,
  sample leak (`alpha`/`beta`/`quota-lab`), MagicMock como iterable.

## Robustez (lecciones aprendidas durante el desarrollo)

- **`_reset_fixture()`**: limpia el test-slot del fixture antes de cada run. Un fixture
  contaminado (con `test_red_hard.py` residual) hacía que el agente no reescribiera y todos
  los modelos puntuaran el mismo archivo viejo.
- **`_clean_test_slot()` por sandbox**: garantiza slate limpio aunque el fixture se contamine.
- **Agente RED como `primary`**: `opencode run --agent` rechaza subagentes y cae al default
  (ignorando `--model`). Se hizo primary para que el bench use el agente y modelo correctos.
- **Detección de fallos de misión**: `no_output` (el modelo no escribió test) y `timeout` se
  reportan como datos válidos, no como errores del bench.

## Lo que NO hace este módulo

- No toca `hooks/`, `opencode/plugins/`, `installer.py`, `templates/`.
- No añade skills al payload de instalación.
- No ejecuta mutmut ni golden impl.
- No modifica `opencode/agents/opencode.json.template`.
