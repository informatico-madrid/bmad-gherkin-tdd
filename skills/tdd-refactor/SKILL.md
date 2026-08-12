---
name: tdd-refactor
description: TDD REFACTOR Phase clean up code with MUTANT_KILLING_GUIDE. Use when implementing TDD REFACTOR phase.
---

# TDD REFACTOR Phase

## Activation Sequence

1. Resolve customization: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`
2. Load persistent facts from `{project-root}/_bmad/custom/tdd-refactor.toml`
3. Load config from `{project-root}/_bmad/bmm/config.yaml`

## Owns

- Refactorización del código GREEN preservando comportamiento
- Aplicación de SOLID, DRY, YAGNI, KISS, Tell-Don't-Ask, Composition over Inheritance
- Ejecución del comando de test para confirmar que el comportamiento se preserva
- Ejecución del comando de mutación para verificar MSI (max 3 intentos por mutante sobreviviente)
- Documentación de mutantes sobrevivientes en `mutant-register.md`
- Actualización de bitácora TDD (REFACTOR status)

### Owns: Reglas de refactorización

1. Test debe pasar: si falla, revertir cambio
2. SOLID principles: seguir SOLID, DRY, YAGNI, KISS
3. Tell-Don't-Ask: no violar principio de Information Expert
4. Composition over Inheritance: preferir composición
5. Extract methods: código legible sin comentarios

## Workflow

0. **RE-ANCLAJE (V5):** re-leer `{contracts_dir}/<story-key>.feature`, escenario
   `@s<k>`. El contrato es el INPUT CANÓNICO — el refactor preserva el
   comportamiento contratado, no una paráfrasis recordada. La compactación
   destruye la intención; solo el archivo persiste.
1. Read story file (@s identifier) — confirmar que CLEAN gate pasó (bitácora CLEAN status)
2. Review current implementation (GREEN + CLEAN phases)
3. Run `{workflow.mutation_cmd}` sobre archivos del diff
4. Para cada mutante sobreviviente (max 3 intentos):
   a. Analizar el mutante
   b. Diseñar estrategia para matarlo (mejorar test RED, refactorizar código)
   c. Aplicar cambio y re-ejecutar mutación
   d. Si sobrevive tras 3 intentos → DOCUMENTAR en `{implementation_artifacts}/mutant-register.md`:
      archivo:línea, nombre del mutante, estrategias intentadas, razón de fracaso
   e. NUNCA añadir `# pragma: no mutate`
5. Run `{workflow.test_cmd}` -> confirm PASS
6. Actualizar bitácora TDD (REFACTOR status + MSI % + sobrevivientes documentados)
7. STOP -- return to coordinator

## Does Not Own

- Escritura de tests (eso es RED)
- Implementación de comportamiento nuevo (eso es GREEN)
- Cambios que alteren comportamiento observable (el refactor preserva)
- Añadir `# pragma: no mutate` — PROHIBIDO. Usar `mutant-register.md` para documentar sobrevivientes.
- Checks estructurales previos a mutación (eso es CLEAN: cleaner-gate + coverage)
- Modificación del contrato Gherkin (la firma la gestiona gherkin-author o el coordinator en loop_auto)
- Decisiones de arquitectura (eso lo hace architect-review)
- No ejecutes `tdd-red`, `tdd-green`, ni `tdd-clean` desde aquí — el coordinador orquesta la secuencia

## Verification

- **Corre:** `{workflow.test_cmd} <test_file> -x` → debe seguir mostrando PASS tras el refactor
- **Corre:** `{workflow.mutation_cmd}` → MSI >= {workflow.msi_minimum} (default 85), coverage 100%

## Constraints

- El test DEBE pasar despues de refactor
- BITACORA OBLIGATORIA en cada @s
- MUTANT_KILLING_GUIDE cargado desde customize.toml (si el proyecto lo configura)
- standards.md cargado desde customize.toml (si el proyecto lo configura)
- Respetar la arquitectura declarada del proyecto
- PROHIBIDO: `# pragma: no mutate`. Documentar sobrevivientes en `mutant-register.md`
- Maximo 3 intentos por mutante sobreviviente. Tras 3 intentos → registro, no bloqueo
- MSI minimo configurable via `{workflow.msi_minimum}` (default 85%), coverage 100% requerido

## Output

- Codigo refactorizado (mejor diseno)
- Bitacora TDD actualizada (REFACTOR status)
- Confirmacion de que test PASS

## Error Handling

- Si pytest muestra FAIL despues de refactor: Revertir cambio
- Si hay error de sintaxis: Corregir y reintentar
- Si test pasa pero hay warnings: Continuar
