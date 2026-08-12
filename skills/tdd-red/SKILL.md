---
name: tdd-red
description: TDD RED Phase write failing test with PERSISTENT_PROMPT_CONSTRAINTS. Use when implementing TDD RED phase.
---

# TDD RED Phase

## Activation Sequence

1. Resolve customization: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`
2. Load persistent facts from `{project-root}/_bmad/custom/tdd-red.toml`
3. Load config from `{project-root}/_bmad/bmm/config.yaml`

## Owns

- Escritura de tests fallidos (RED phase)
- Ejecución del comando de test para confirmar FAIL
- Actualización de bitácora TDD (ROJO status)
- Derivación del comportamiento observable desde el `Then` del escenario @s<k>

### Owns: Reglas de escritura de tests

1. Nombre descriptivo: `test_{scenario}_{expected_behavior}`
2. Setup mínimo: solo lo necesario para el test
3. Assertion clara: un solo assertion por test (no assertion roulette)
4. Boundary testing: incluir casos límite
5. Edge cases: manejar `null`, `empty`, `invalid` input

## Workflow

0. **RE-ANCLAJE (V5):** re-leer `{contracts_dir}/<story-key>.feature`, escenario
   `@s<k>`. Este es el INPUT CANÓNICO — no paráfrasis, no story file. La
   compactación destruye la intención; solo el archivo persiste.
1. Read the SIGNED CONTRACT scenario, not the story prose: open
   `{contracts_dir}/<story-key>.feature` and copy the TEXT of the `@s<k>` scenario
   under work (Given/When/Then). ESE texto es la fuente de verdad del comportamiento.
2. Derive the testable behavior from the scenario's `Then` (must be observable/measurable)
3. Write failing test (RED phase)
4. Run test command -> confirm FAIL
5. Update bitacora TDD (ROJO status)
6. STOP -- return to coordinator

## Does Not Own

- Implementación de código (eso es GREEN)
- Refactorización (eso es REFACTOR)
- Ejecución de mutmut (eso lo hace REFACTOR)
- Modificación del contrato Gherkin (la firma la gestiona gherkin-author o el coordinator en loop_auto)
- Decisiones de arquitectura (eso lo hace architect-review)
- No ejecutes `tdd-green`, `tdd-clean` ni `tdd-refactor` desde aquí — el coordinador orquesta la secuencia

## Verification

- **Corre:** `{workflow.test_cmd} <test_file> -x` → debe mostrar FAIL (no PASS, no skip/xfail)
- **Delega a:** `tdd-green` (para PASS), `tdd-refactor` (para refactor)

## Constraints

- NUNCA implementar codigo hasta que test falle
- BITACORA OBLIGATORIA en cada @s
- El test se deriva del ESCENARIO del contrato firmado (@s), no de una paráfrasis del story file
- PERSISTENT_PROMPT_CONSTRAINTS cargado desde customize.toml (si el proyecto lo configura)
- Test debe verificar comportamiento observable, no implementacion

## Output

- Test file actualizado con nuevo test fallido
- Bitacora TDD actualizada (ROJO status)
- Confirmacion de que test FAIL

## Error Handling

- Si pytest no muestra FAIL: STOP y reportar
- Si hay error de sintaxis: Corregir y reintentar
- Si test pasa accidentalmente: STOP y reportar (no es RED valido)
