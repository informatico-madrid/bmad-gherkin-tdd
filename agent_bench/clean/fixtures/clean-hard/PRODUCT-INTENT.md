# PRODUCT-INTENT — Quota Broker (GREEN benchmark fixture)

> Cargado como PRIMER persistent_fact. No sustituye el corpus: lo apunta.

## Misión (3 líneas)
- Quota Broker aplica reglas **declaradas** sobre records arbitrarios y decide aceptar / rechazar / reenviar.
- El cliente final trae records que **nunca hemos visto**. Si el código solo funciona con el sample de lab, **está mal aunque todos los gates pasen**.
- Tesis: "prove the prover" — nada se declara funcionando; se demuestra con observación de la estructura exacta del resultado.

## Mapa al corpus
- Fuente de verdad: `tests/contracts/green-hard.feature` (contrato firmado, 8 @s).
- La implementación se deriva **exclusivamente** del contrato y los SPEC-PINS.md.
- El test visible (gold) ya existe. La implementación debe hacerlo pasar.

## FIXTURE ≠ TARGET (regla dura)
- `"alpha"`, `"beta"`, `"quota-lab"` son **muestras de laboratorio**, no el producto.
- Un literal de sample en una aserción de comportamiento es un DEFECTO en el test o en la implementación.

## Las 3 formas de fallo de GREEN (no las repitas)
1. **Hardcode del gold**: memorizar `if score in (3,7,50,51,99)` en vez de implementar la política real.
2. **Mockear el SUT**: parchear `apply()` en vez de implementar la lógica.
3. **Overfit**: pasar el gold pero fallar contra valores nuevos (hidden tests).

## Reglas del benchmark
- Se evalúa la **implementación del SUT**, no el test.
- El test visible (gold) es un gate, no un ranking.
- Los hidden tests son el ranking de verdad.
- La implementación debe ser **mínima** y **correcta**, sin features extra.
