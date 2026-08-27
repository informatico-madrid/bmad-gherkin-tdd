---
name: tdd-clean
description: TDD CLEAN Phase structural quality gate before mutation. Runs the project's applicable cleaner and coverage gates, refactors violations while preserving behavior, and records N/A gates explicitly. Use between GREEN and REFACTOR.
---

# TDD CLEAN Phase

Gate applicability is owned centrally by the coordinator customization in
`{project-root}/_bmad/custom/bmad-tdd-coordinator.toml`. This phase customization
supplies commands only; do not add contradictory phase-local `*_applicable` flags.
When a gate is disabled, the central `*_na_reason` is required and must be copied
into the bitacora's N/A entry.

## Activation Sequence

1. Resolve customization: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`
2. Load persistent facts from `{project-root}/_bmad/custom/tdd-clean.toml`
3. Load config from `{project-root}/_bmad/bmm/config.yaml`

## Owns

- Ejecucion del cleaner-gate del proyecto cuando el scope central declara
  `cleaner_applicable = true`
- Ejecucion del comando de cobertura cuando el scope central declara
  `coverage_applicable = true`
- Registro explícito `N/A` con `*_na_reason` cuando uno de esos gates no aplica al stack
- Interpretacion de violaciones de los 7 checks (KISS, DRY, YAGNI, LoD, CoI, coverage, scan_mutation_sites)
- Refactorizacion estructural (simplificar, split, eliminar dead code) preservando comportamiento
- Verificacion de que el test sigue verde despues de cada refactor
- Actualizacion de bitacora TDD (CLEAN status)

### Owns: Reglas de refactorizacion

1. Solo cambios estructurales — NUNCA cambiar comportamiento
2. Simplificar funciones con `complexity > 10` (KISS): extraer metodo, aplanar nesting
3. Reducir `arity > 5`: agrupar parametros en dataclass/dict
4. Eliminar dead code reportado por YAGNI (funciones/clases sin llamadas)
5. Unificar codigo duplicado reportado por DRY (>6 lineas identicas)
6. Romper cadenas de atributos reportadas por LoD (>3 niveles)
7. Reducir herencia profunda reportada por CoI (>2 niveles): composicion sobre herencia
8. Split de archivos con >100 mutation sites (scan_mutation_sites): partir en modulos cohesivos
9. Si coverage aplica, asegurar 100% en diff; si falta, NO inventar tests — reportar gap

## Workflow

0. **RE-ANCLAJE (V5):** re-leer `{contracts_dir}/<story-key>.feature` + spec de la story.
   El CLEAN no cambia comportamiento — solo estructura. Releer el contrato asegura
   que el refactor no elimina logica que cumple un AC.

1. Identificar archivos del diff: `git diff --name-only HEAD~1` o desde el contexto de la story

2. Resolver aplicabilidad del cleaner gate:
    - Leer `cleaner_applicable` y `cleaner_na_reason` del `[workflow]` de la
      personalización `bmad-tdd-coordinator`, no de una personalización de esta fase.
    - Si `cleaner_applicable = false` → NO ejecutar `cleaner_cmd`; registrar
      `cleaner-gate: N/A — skipped (<cleaner_na_reason>)` y pasar al paso 5.
    - Si `cleaner_applicable = true` → ejecutar:
   ```bash
   {workflow.cleaner_cmd} <diff_files>
   ```
   Si PASS → saltar a coverage (paso 5)
   Si FAIL → analizar violaciones, priorizar por severidad:
   - ALTA: complexity > 15, nesting > 5, >200 mutation sites
   - MEDIA: complexity 11-15, arity 6-7, duplicates
   - BAJA: complexity 10, arity 5, chain length 3

3. Refactorizar violaciones ALTA → MEDIA → BAJA, una por una:
   - Aplicar refactor
   - Ejecutar el test → confirmar verde
   - Re-ejecutar el cleaner-gate sobre el archivo → confirmar mejora
   - Si el check empeora o pytest falla → revertir, intentar estrategia alternativa

4. Maximo 3 ciclos de refactor por archivo. Si tras 3 intentos una violacion persiste:
   - Documentar en bitacora: archivo, violacion, intentos, razon
   - NO ocultar con pragma
   - Reportar al coordinador como "cleaner-stuck"

5. Resolver aplicabilidad de coverage:
    - Leer `coverage_applicable` y `coverage_na_reason` del `[workflow]` de la
      personalización `bmad-tdd-coordinator`.
    - Si `coverage_applicable = false` → NO fabricar una métrica; registrar
      `coverage: N/A — skipped (<coverage_na_reason>)`.
    - Si `coverage_applicable = true` → ejecutar exactamente:
   ```bash
   {workflow.coverage_cmd}
   ```
   - Coverage debe ser 100% en archivos del diff
   - Si <100% → reportar gap (el tdd-red ya debio cubrirlo)
   - NO añadir tests nuevos aqui (eso es RED)

   En ambos casos ejecutar `{workflow.test_cmd}` y confirmar que el comportamiento
   contratado sigue verde.

6. Actualizar bitacora TDD (CLEAN status):
   ```
   ## @s<k> CLEAN — <fecha>
    cleaner-gate: PASS (...) | N/A — skipped (<cleaner_na_reason>)
    coverage: 100% | N/A — skipped (<coverage_na_reason>)
   tests: PASS ({workflow.test_cmd})
   cambios: [lista de archivos y refactors aplicados]
   ```

## Does Not Own

- NO ejecuta `mutmut run` ni `make mutation-check` (eso es el coordinador en RELEASE)
- NO escribe tests nuevos (eso es RED)
- NO cambia comportamiento (eso requeriria nuevo RED→GREEN)
- NO anade `# pragma: no mutate` (PROHIBIDO — usar registro de mutantes, lo gestiona el coordinador en RELEASE)
- NO ejecuta `tdd-red`, `tdd-green`, ni `tdd-refactor` desde aqui
- NO modifica el contrato Gherkin o el spec de la story
- NO toma decisiones de arquitectura (eso es architect-review)

## Verification

- Si el scope central declara `cleaner_applicable = true`, corre `{workflow.cleaner_cmd}
  <diff_files>` y exige PASS; si es `false`, registra N/A con la razón central.
- Si el scope central declara `coverage_applicable = true`, corre `{workflow.coverage_cmd}`
  y exige 100%; si es `false`, registra N/A con la razón central.
- **Siempre corre:** `{workflow.test_cmd}` → todos los tests PASS.
- Re-chequea `{workflow.cleaner_cmd} <diff_files>` post-refactor únicamente cuando
  `cleaner_applicable = true`.
- **Delega a:** `tdd-refactor` (refactor estructural), el coordinador en RELEASE
  (mutación completa). No ejecuta ni delega mutación desde CLEAN.

## Constraints

- NUNCA uses `# pragma: no mutate` — esta PROHIBIDO.
- Verifica que el test sigue verde DESPUES de CADA refactor individual
- Manten los refactors atomicos (un archivo/una funcion a la vez)
- Si el coverage no llega a 100% → reporta el gap, NO lo arregles con tests nuevos
- Si una violacion no se puede resolver tras 3 intentos → documenta y reporta al coordinador

## Output

- cleaner-gate: PASS o N/A explícito según configuración
- coverage: 100% o N/A explícito según configuración
- tests: todos los tests del diff PASS
- bitacora: CLEAN status con detalle de cambios y metricas
- Antes de devolver el control, emitir exactamente una línea de evidencia para el
  coordinador: `BMAD_TDD_PHASE_RESULT: {"agent":"tdd-clean-ornith","phase":"CLEAN","status":"PASS","test_exit":0,"bitacora":"CLEAN"}`.
- STOP -- return to coordinator with PASS/FAIL + bitacora
