# PRODUCT-INTENT — Quota Broker (benchmark fixture)

> Cargado como PRIMER persistent_fact. No sustituye el corpus: lo apunta.

## Misión (3 líneas)
- Quota Broker aplica reglas **declaradas** sobre records arbitrarios (texto, JSON, argv, archivos) y decide aceptar / rechazar / reenviar.
- El cliente final trae records que **nunca hemos visto** (campos nuevos, estructuras anidadas, valores extremos). Si el código solo funciona con el sample de lab, **está mal aunque todos los gates pasen**.
- Tesis: "prove the prover" — nada se declara funcionando; se demuestra con observación de la estructura exacta del resultado.

## Mapa al corpus
- Fuente de verdad: `tests/contracts/red-hard.feature` (contrato firmado).
- El test se deriva **exclusivamente** del `Then` del escenario `@s`, nunca del `.feature` como prosa general.

## FIXTURE ≠ TARGET (regla dura)
- `"alpha"`, `"beta"`, `"quota-lab"` son **muestras de laboratorio**, no el producto. Un literal de sample en una aserción de comportamiento es un DEFECTO.
- Check canónico: `grep -ril "alpha\|beta\|quota-lab" tests/unit/` → **0 líneas** en aserciones de valor esperado.
- MAL: `assert result.key == "alpha"` · BIEN: el `Then` habla de `record.key` observado / `spec.threshold` / valores de la entrada declarada.

## Las 3 formas históricas de cascarón (no las repitas)
1. **Mock del kernel entero**: mockear `apply()` en vez de testear la lógica de filtrado → el test no cubre ninguna frontera real.
2. **Acoplamiento a sample**: resolver "genérico" con strings fijos de `"alpha"` / `"beta"` → el test solo pasa con el fixture de lab.
3. **Evidencia fabricada**: marcar ROJO sin pytest FAIL; o testear PASS sin haber escrito aserciones.

## Reglas del benchmark
- Se evalúa el **código fuente** del test (AST + contrato), no su ejecución.
- La implementación del SUT es un hueco (`raise NotImplementedError`). Pytest no puntúa.
- El fixture de este benchmark es **agnóstico de dominio** — no hay PHP, legacy, ni targets concretos.
