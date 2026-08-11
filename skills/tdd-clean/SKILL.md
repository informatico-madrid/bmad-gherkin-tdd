---
name: tdd-clean
description: TDD CLEAN Phase structural quality gate before mutation. Runs cleaner-gate (KISS/DRY/YAGNI/LoD/CoI/scan_sites) + coverage, refactors violations while preserving behavior. Use between GREEN and REFACTOR.
---

# TDD CLEAN Phase

## Activation Sequence

1. Resolve customization: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`
2. Load persistent facts from `{project-root}/_bmad/custom/tdd-clean.toml`
3. Load config from `{project-root}/_bmad/bmm/config.yaml`

## Owns

- Ejecucion del cleaner-gate del proyecto sobre archivos del diff de la story
- Ejecucion de `pytest --cov` para verificar 100% cobertura en archivos del diff
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
9. Asegurar 100% coverage en diff: si falta cobertura, NO inventar tests — reportar gap

## Workflow

0. **RE-ANCLAJE (V5):** re-leer `{contracts_dir}/<story-key>.feature` + spec de la story.
   El CLEAN no cambia comportamiento — solo estructura. Releer el contrato asegura
   que el refactor no elimina logica que cumple un AC.

1. Identificar archivos del diff: `git diff --name-only HEAD~1` o desde el contexto de la story

2. Ejecutar cleaner gate:
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

5. Coverage check:
   ```bash
   {workflow.test_cmd} --cov=<diff_files> --cov-report=term-missing <test_files>
   ```
   - Coverage debe ser 100% en archivos del diff
   - Si <100% → reportar gap (el tdd-red ya debio cubrirlo)
   - NO añadir tests nuevos aqui (eso es RED)

6. Actualizar bitacora TDD (CLEAN status):
   ```
   ## @s<k> CLEAN — <fecha>
   cleaner-gate: PASS (KISS ✓, DRY ✓, YAGNI ✓, LoD ✓, CoI ✓, scan ✓)
   coverage: 100%
   cambios: [lista de archivos y refactors aplicados]
   ```

## Does Not Own

- NO ejecuta `mutmut run` (eso es REFACTOR)
- NO escribe tests nuevos (eso es RED)
- NO cambia comportamiento (eso requeriria nuevo RED→GREEN)
- NO anade `# pragma: no mutate` (PROHIBIDO — usar registro de mutantes en REFACTOR)
- NO ejecuta `tdd-red`, `tdd-green`, ni `tdd-refactor` desde aqui
- NO modifica el contrato Gherkin o el spec de la story
- NO toma decisiones de arquitectura (eso es architect-review)

## Verification

- **Corre:** `{workflow.cleaner_cmd} <diff_files>` → debe dar PASS en los checks
- **Corre:** `{workflow.test_cmd} --cov=<diff_files>` → debe dar 100% coverage + todos los tests PASS
- **Corre:** `{workflow.cleaner_cmd} <diff_files>` → re-chequeo post-refactor
- **Delega a:** `tdd-refactor` (para mutmut), `tdd-red` (si faltan tests)

## Constraints

- NUNCA uses `# pragma: no mutate` — esta PROHIBIDO.
- Verifica que el test sigue verde DESPUES de CADA refactor individual
- Manten los refactors atomicos (un archivo/una funcion a la vez)
- Si el coverage no llega a 100% → reporta el gap, NO lo arregles con tests nuevos
- Si una violacion no se puede resolver tras 3 intentos → documenta y reporta al coordinador

## Output

- cleaner-gate: PASS en todos los checks aplicables al diff
- coverage: 100% en archivos del diff
- tests: todos los tests del diff PASS
- bitacora: CLEAN status con detalle de cambios y metricas
- STOP -- return to coordinator with PASS/FAIL + bitacora
