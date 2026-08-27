---
name: tdd-refactor
description: TDD REFACTOR Phase preserves behavior and confirms tests; full mutation is owned by the coordinator at RELEASE. Use when implementing TDD REFACTOR phase.
---

# TDD REFACTOR Phase

Mutation applicability is owned centrally by the coordinator customization in
`{project-root}/_bmad/custom/bmad-tdd-coordinator.toml`. This phase customization
supplies commands only; do not add a contradictory phase-local `mutation_applicable`
flag. The coordinator records the central `mutation_na_reason` as RELEASE N/A when
mutation is disabled.

## Activation Sequence

1. Resolve customization: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`
2. Load persistent facts from `{project-root}/_bmad/custom/tdd-refactor.toml`
3. Load config from `{project-root}/_bmad/bmm/config.yaml`

## Owns

- Refactorización del código GREEN preservando comportamiento
- Aplicación de SOLID, DRY, YAGNI, KISS, Tell-Don't-Ask, Composition over Inheritance
- Ejecución del comando de test para confirmar que el comportamiento se preserva
- Actualización de bitácora TDD (REFACTOR status)
- NUNCA ejecutar el comando de mutación completo del proyecto ni
  `uv run mutmut run` sin un mutant ID (eso es RELEASE del coordinador)

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
3. Refactor structure while preserving behavior
4. Run `{workflow.test_cmd}` -> confirm PASS
5. Actualizar bitácora TDD (REFACTOR status). No certificar MSI aquí; si la
   mutación no aplica, la razón N/A la registra el coordinador en RELEASE.
6. STOP -- return to coordinator. Full mutation is coordinator-owned at RELEASE.

## Does Not Own

- Escritura de tests (eso es RED)
- Implementación de comportamiento nuevo (eso es GREEN)
- Cambios que alteren comportamiento observable (el refactor preserva)
- Añadir `# pragma: no mutate` — PROHIBIDO. Usar el mutant-register del proyecto para documentar sobrevivientes.
- Checks estructurales previos a mutación (eso es CLEAN: cleaner-gate + coverage)
- Modificación del contrato Gherkin (la firma la gestiona gherkin-author o el coordinator en loop_auto)
- Decisiones de arquitectura (eso lo hace architect-review)
- No ejecutes `tdd-red`, `tdd-green`, ni `tdd-clean` desde aquí — el coordinador orquesta la secuencia

## Verification

- **Corre:** `{workflow.test_cmd}` → debe seguir mostrando PASS tras el refactor.
- **Delega a:** el coordinador en RELEASE (mutación completa, MSI o N/A según el
  scope central).

## Constraints

- El test DEBE pasar despues de refactor
- BITACORA OBLIGATORIA en cada @s
- MUTANT_KILLING_GUIDE cargado desde customize.toml (si el proyecto lo configura)
- standards.md cargado desde customize.toml (si el proyecto lo configura)
- Respetar la arquitectura declarada del proyecto
- PROHIBIDO: `# pragma: no mutate`. Documentar sobrevivientes en el mutant-register.
- PROHIBIDO: el comando de mutación completo del proyecto y `uv run mutmut run` sin un
  mutant ID — la mutación completa es exclusiva del coordinador y corre UNA vez en RELEASE.

## Output

- Codigo refactorizado (mejor diseno)
- Bitacora TDD actualizada (REFACTOR status)
- No certificar MSI en esta fase; el coordinador registra MSI o N/A en RELEASE
- Confirmacion de que test PASS
- Antes de devolver el control, emitir exactamente una línea de evidencia para el
  coordinador: `BMAD_TDD_PHASE_RESULT: {"agent":"tdd-refactor-ornith","phase":"REFACTOR","status":"PASS","test_exit":0,"bitacora":"REFACTOR"}`.

## Error Handling

- Si el comando de test muestra FAIL despues de refactor: Revertir cambio
- Si hay error de sintaxis: Corregir y reintentar
- Si test pasa pero hay warnings: Continuar
