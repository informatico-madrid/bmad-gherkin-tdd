---
name: tdd-green
description: TDD GREEN Phase make test pass with standards.md. Use when implementing TDD GREEN phase.
---

# TDD GREEN Phase

## Activation Sequence

1. Resolve customization: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`
2. Load persistent facts from `{project-root}/_bmad/custom/tdd-green.toml`
3. Load config from `{project-root}/_bmad/bmm/config.yaml`

## Owns

- Implementación del código MÍNIMO que hace pasar el test RED
- Ejecución del comando de test para confirmar PASS
- Actualización de bitácora TDD (VERDE status)

### Owns: Reglas de implementación

1. Mínimo viable: solo implementar lo que el test requiere
2. Sin features extra: no agregar funcionalidad no solicitada
3. Sin refactor: dejar código feo si es necesario para pasar
4. Test debe pasar: si no pasa, seguir iterando

## Workflow

0. **RE-ANCLAJE (V5):** re-leer `{contracts_dir}/<story-key>.feature`, escenario
   `@s<k>`, y el test ROJO escrito en la fase RED. El contrato es el INPUT
   CANÓNICO — no paráfrasis, no story file. La compactación destruye la intención;
   solo el archivo persiste.
1. Read story file (@s identifier)
2. Find failing test from RED phase
3. Implement MINIMAL code to make test pass
4. Run test command -> confirm PASS
5. Update bitacora TDD (VERDE status)
6. STOP -- return to coordinator

## Does Not Own

- Escritura de tests (eso es RED)
- Refactorización (eso es REFACTOR — aquí se permite código feo)
- Ejecución de mutmut (eso lo hace el coordinador en RELEASE)
- Modificación del contrato Gherkin (la firma la gestiona gherkin-author o el coordinator en loop_auto)
- Decisiones de arquitectura (eso lo hace architect-review)
- No ejecutes `tdd-red`, `tdd-clean` ni `tdd-refactor` desde aquí — el coordinador orquesta la secuencia

## Verification

- **Corre exactamente:** `{workflow.test_cmd}` → debe terminar con PASS para el test ROJO
  de la fase anterior. El proyecto incluye cualquier selección o flags en `test_cmd`.
- **Delega a:** `tdd-refactor` (para limpieza)

## Constraints

- CODIGO MINIMO -- Solo lo necesario para pasar el test
- NUNCA refactorizar en esta fase
- BITACORA OBLIGATORIA en cada @s
- standards.md cargado desde customize.toml (si el proyecto lo configura)
- Respetar la arquitectura declarada del proyecto (si aplica)

## Output

- Codigo implementado (minimo viable)
- Bitacora TDD actualizada (VERDE status)
- Confirmacion de que test PASS
- Antes de devolver el control, emitir exactamente una línea de evidencia para el
  coordinador: `BMAD_TDD_PHASE_RESULT: {"agent":"tdd-green-ornith","phase":"GREEN","status":"PASS","test_exit":0,"bitacora":"VERDE"}`.

## Error Handling

- Si el comando de test termina con FAIL despues de implementar: Revisar implementacion
- Si hay error de sintaxis: Corregir y reintentar
- Si test pasa pero hay warnings: Continuar (no es GREEN valido si no pasa)
