---
name: bmad-tdd-coordinator
description: BMAD TDD Coordinator orchestrates RED GREEN CLEAN REFACTOR phases with phase-specialized skills. Use when implementing TDD workflow.
---

# BMAD TDD Coordinator

## Overview

This skill manages TDD story execution by classifying each @s as either **development** (full RED→GREEN→CLEAN→REFACTOR) or **verification_preexisting** (skip RED when prior story already mutation-tested the function), routing to the appropriate path before code touches. Acts as a TDD discipline enforcer with a Pre-RED classification gate that prevents redundant test creation while preserving the configured MSI threshold (default 85%, with 100% kill-or-justified preferred). Use when the user says "dev this story" or "implement the next story in the sprint plan". Produces a mutation-clean, release-gated story implementation with full bitácora traceability.

## Conventions

- Bare paths (e.g. `references/guide.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
- `{contracts_dir}` is the configured project-root-relative contract directory (default `tests/contracts`).
- `{implementation_artifacts}` resolves from `_bmad/bmm/config.yaml` (default `_bmad-output/implementation-artifacts`).

## On Activation

### Step 1: Resolve the Workflow Block

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

If the script fails, resolve the `workflow` block yourself by reading these three files in base → team → user order and applying structural merge rules: `{skill-root}/customize.toml`, `{project-root}/_bmad/custom/{skill-name}.toml`, `{project-root}/_bmad/custom/{skill-name}.user.toml`. Scalars override, tables deep-merge, arrays of tables keyed by `code`/`id` replace matching entries and append new ones, all other arrays append.

### Step 2: Execute Prepend Steps

Execute each entry in `{workflow.activation_steps_prepend}` in order before proceeding.

### Step 3: Load Persistent Facts

Treat every entry in `{workflow.persistent_facts}` as foundational context for the whole run. Entries prefixed `file:` are paths or globs — load the referenced contents as facts. All other entries are facts verbatim.

### Step 4: Load Config

Load available config from `{project-root}/_bmad/config.yaml` and `{project-root}/_bmad/config.user.yaml` if present. Use sensible defaults for anything not configured.

### Step 5: Execute Append Steps

Execute each entry in `{workflow.activation_steps_append}` in order before entering the workflow's first stage.

## Workflow

1. User: "dev this story {story-file}.md"
2. Coordinator invokes bmad-tdd-coordinator (BMAD skill)
3. BMAD Activation: resolve_customization.py -> persistent_facts -> workflow
4. State Machine: GHERKIN_GATE -> INTAKE -> PLAN -> CLASSIFY -> IMPLEMENT_LOOP -> INTEGRATE -> RELEASE -> DONE

GHERKIN_GATE (contrato autónomo — ejecutar ANTES de INTAKE):
  El loop debe poder ejecutar una story entera sin intervención humana, incluyendo
  la creación y aprobación del contrato Gherkin (el modo loop es 100% autónomo,
  el humano puede estar ausente/durmiendo).

  Modos de firma (ver gherkin-author → Signature modes):
    - loop_auto (BMAD_LOOP_MODE=1): el coordinator genera + auto-aprueba con
      `Approved-by: coordinator-auto`. NUNCA preguntar al humano.
    - human_required (sin BMAD_LOOP_MODE): si el contrato no existe o está DRAFT,
      HALT y pedir /gherkin-author para la firma humana. NUNCA auto-aprobar fuera
      de loop mode.

  Procedimiento (loop_auto):
   1. Verificar si `{contracts_dir}/<story-key>.feature` existe y
      tiene `# Status: APPROVED` en cabecera.
      - Si existe y está APPROVED → logear "GHERKIN_GATE: contract already approved"
        → pasar a INTAKE.
   2. Si NO existe o está en DRAFT → GENERAR/completar el contrato:
     a. Leer la story file completa: Story, Acceptance Criteria, Tasks, scope
        boundaries (do-NOT-implement), Dev Notes.
     b. Leer `{project-root}/_bmad/gherkin-tdd/docs/contract-rules.md` — reglas del .feature, non-negotiable.
     c. Destilar un Scenario por cada comportamiento observable de los AC,
        incluyendo error paths. Cada Then debe ser medible (exit code, mensaje,
        valor, artifact). Un When por escenario. Sin detalles de implementación.
     d. Tags @s1..@sn como identificadores estables.
     e. Incluir el AC → @s coverage map como comentario en cabecera.
     f. Escribir el archivo con `# Status: DRAFT`.
  3. REVISAR el contrato generado (auto-revisión):
     a. ¿Cada AC está cubierto por ≥1 escenario? Si no → añadir escenario.
     b. ¿Cada Then es medible y mecánico? Si no → reformular.
     c. ¿Hay exactamente un When por escenario? Si no → dividir.
     d. ¿Hay detalles de implementación (nombres de función/clase)? Si sí → eliminar.
     e. ¿El número de escenarios es razonable para un modelo local (≤10)? Si no →
        la story es demasiado grande, reportar pero continuar.
  4. Si la revisión pasa → estampar:
     ```
     # Status: APPROVED
     # Approved-by: coordinator-auto
     # Date: <YYYY-MM-DD>
     ```
     Logear: "GHERKIN_GATE: contract auto-generated and auto-approved (N scenarios)"
  5. Si la revisión encuentra problemas → corregir y re-revisar (máx 2 iteraciones).
     Si tras 2 iteraciones aún hay problemas → HALT y reportar (escalación CRITICAL
     del loop, no pregunta al humano).
  6. El .feature aprobado es el INPUT CANÓNICO de cada fase RED. Cada @s de RED
     se deriva del TEXTO del escenario del contrato, no del story file.

INTAKE (gates de entrada — ejecutar ANTES de PLAN, HALT si fallan):
  - G0 Puerta Gherkin (verificación post-GHERKIN_GATE): confirma que GHERKIN_GATE
      produjo un contrato APPROVED.
      bash: head -5 {contracts_dir}/<story-key>.feature
      Si no existe o no es APPROVED → HALT (fallo interno de GHERKIN_GATE).
      El .feature aprobado (sus escenarios @s) es el INPUT CANÓNICO de cada fase
      RED, no solo el story file.
  - G1 Verificación-en-consumo: si la story depende de una capacidad de una story previa,
      NO confíes en `status: done` — verifica ejecutando el probe/verificación que la
      capacidad declare en su spec. Si la capacidad consumida no responde → HALT y
      reporta: la dependencia no es real.

CLASSIFY (nuevo gate entre PLAN e IMPLEMENT_LOOP — ejecutar ANTES de cualquier @s):
  Para CADA @s, determinar su clasificación antes de invocar phase skills:

  A) **development** (default):
     Entry conditions (ANY of these means development):
       - Function/class under test does NOT exist in `{prod_package}` (configurable)
       - Cannot locate a prior bitácora line documenting TDD completion for this function
       - Cannot identify implementing commit hash showing the function in its diff
       - Function file has been modified since the last implementing commit
     Action: Standard RED → GREEN → CLEAN → REFACTOR.

  B) **verification_preexisting** (skip RED only if ALL 5 conditions hold):
     All conditions MUST be satisfied simultaneously:
       (a) Function/class under test EXISTS in the production package
       (b) A prior story implementation artifact contains a bitácora line documenting
           TDD completion (RED/GREEN/CLEAN/REFACTOR) for that EXACT function
       (c) The implementing commit is IDENTIFIABLE by hash and shows the function in its diff
       (d) Mutation stats for the function's MODULE report MSI >= {workflow.verification_preexisting_threshold}
           (default 100, per NFR-13); MSI MUST be verified by running the project's
           mutation command or reading the committed mutation stats — NEVER trusted
           from bitácora alone
       (e) `git diff <implementing_commit>..HEAD -- <function_file>` returns EMPTY
           (function unchanged since implementation)
     Action: Skip RED. Invoke tdd-green with 'verification_preexisting' context to confirm
     existing implementation still passes, then run CLEAN and REFACTOR verification without
     changing production behavior. Document classification evidence (commit hash, bitácora path:line,
     MSI source) in the bitácora for this @s. NO new production code, NO new test code unless
     an existing test regresses.

  C) **ambiguous** (cannot satisfy ALL 5 verification_preexisting conditions AND cannot
     confirm development — e.g., evidence missing or contradictory):
     Entry conditions: partial evidence exists but not all 5 conditions can be verified
     Action: STOP. Report the specific evidence gap to the user. Do NOT invent RED.
     Do NOT skip phases. ambiguous_action = {workflow.ambiguous_action} (default: STOP).

For each @s in story (derivado del escenario @s del contrato firmado), AFTER CLASSIFY:

**IMPORTANTE — Mecanismo de invocación:** Las fases TDD se ejecutan como SUBAGENTES.
El coordinador NUNCA escribe tests ni código directamente. Usar SIEMPRE la herramienta
`task()` con `subagent_type` correspondiente. No usar `skill()` para las fases.
La directiva canónica de dispatch es `invoke task: <agent>` — la secuencia prescrita
es: `invoke task: tdd-red-ornith` → `invoke task: tdd-green-ornith` →
`invoke task: tdd-clean-ornith` → `invoke task: tdd-refactor-ornith`.

  - If classification = development:
      ```
      task(
        subagent_type="tdd-red-ornith",
        description="RED phase @s<k>",
        prompt="[contexto: scenario @s<k> del .feature + instructions del coordinador]"
      )
      ```
      El subagente tdd-red-ornith tiene su propio contexto y puede escribir archivos de test.
      Esperar a que complete (test escrito + pytest FAIL confirmado).

      **C4 ADVISOR — RED TEST ANALYSIS (coordinador, obligatorio, no bloqueante):**
          Con los paths/nodeids EXACTOS del RED handoff contract, ejecutar ANTES del
          review LLM (un comando, sin operadores de shell):

              python _bmad/gherkin-tdd/scripts/red_test_advisor.py analyze \
                --project-root . \
                --evidence-root <run-dir>/evidence/red-test-advisor \
                --scenario-id @s<k> \
                --target <nodeid-exacto> \
                --output <run-dir>/evidence/red-test-advisor/advisor-<story>-s<k>.json

          (El script exacto sale de `{workflow.red_test_advisor_cmd}`; en loop el
          run-dir es `$BMAD_LOOP_RUN_DIR`.) El veredicto (`strong|weak|unsupported`)
          es SHAPE estático: registra calibración y NO sustituye el review.
          Fallo/infra → registrar y continuar; reintentos máx 1 por error de
          invocación obvio.

      **MUTANT-HUNTING REVIEW (coordinador, NO delegar):**
          ANTES de pasar a GREEN, el coordinador DEBE revisar el test del RED:
          1. Leer el archivo de test completo
          2. Deducir mutantes potenciales (SIN ejecutar mutmut):
             - Mutantes de frontera: ¿cubre 0, 1, -1, max, min, empty, None?
             - Mutantes condicionales: ¿cubre ambas ramas de if/else?
             - Mutantes aritméticos: ¿verifica +, -, *, / con valores específicos?
             - Mutantes de retorno: ¿assertea valores exactos, no solo tipos?
             - Mutantes de negación: ¿verificaría si `not` se añade/elimina?
             - Mutantes de operador: ¿distinguiría `==` vs `!=`, `<` vs `<=`?
          3. Evaluar robustez:
             - ¿Assertions EXACTAS (assert x == 42) o LOOSE (assert x is not None)?
             - ¿Cardinalidad exacta (len(x) == 3) o vaga (len(x) > 0)?
             - ¿Tipos explícitos (isinstance(x, tuple))?
          4. Si el test NO es robusto:
             - Enviar instrucciones específicas al RED para mejorar el test
             - Esperar a que el RED complete las mejoras
             - Repetir la revisión hasta que sea robusto
          5. Si el test ES robusto:
             - Documentar la revisión en la bitácora
             - Pasar a GREEN

      **C4 ADVISOR — COMPARISON (SIEMPRE tras el review, regardless of the advisor verdict):**
          Persistir el texto bounded del review + su label explícito
          (`strong|weak|unsupported`) y ejecutar:

              python _bmad/gherkin-tdd/scripts/red_test_advisor.py compare \
                --advisor <advisor.json> \
                --llm-verdict <label> \
                --llm-review <review.txt> \
                --evidence-root <run-dir>/evidence/red-test-advisor \
                --output <comparison.json>

          Calibración only: el advisor verdict never authorizes GREEN — la decisión
          de volver a RED o pasar a GREEN sigue siendo EXCLUSIVAMENTE el review LLM.
          Registrar paths/hashes de ambos artifacts en la bitácora; NUNCA usar
          `certified` ni ningún claim de certificación.

      ```
      task(
        subagent_type="tdd-green-ornith",
        description="GREEN phase @s<k>",
        prompt="[contexto: test RED escrito + scenario @s<k> + instrucciones]"
      )
      ```
      El subagente tdd-green-ornith implementa código mínimo para hacer PASS el test.
      Esperar a que complete (pytest PASS confirmado).

      ```
      task(
        subagent_type="tdd-clean-ornith",
        description="CLEAN phase @s<k>",
        prompt="[contexto: test pasando + código actual + instrucciones de limpieza estructural]"
      )
      ```
      El subagente tdd-clean-ornith ejecuta el cleaner-gate estructural + cobertura.
      Esperar a que complete (cleaner PASS + coverage).

      ```
      task(
        subagent_type="tdd-refactor-ornith",
        description="REFACTOR phase @s<k>",
        prompt="[contexto: test pasando + código actual + instrucciones de limpieza]"
      )
      ```
      El subagente tdd-refactor-ornith limpia el código manteniendo pytest PASS.
      Esperar a que complete (pytest PASS confirmado). La mutación completa NO es de
      esta fase — el coordinador la corre UNA vez en RELEASE.

  - If classification = verification_preexisting:
      ```
      task(
        subagent_type="tdd-green-ornith",
        description="GREEN phase @s<k> [verification_preexisting]",
        prompt="[marker: classification=verification_preexisting + evidencia (commit hash, bitácora path:line, MSI source)]"
      )
      ```
      El subagente confirma que la implementación existente sigue pasando.
      Esperar a que complete.

      ```
      task(
        subagent_type="tdd-clean-ornith",
        description="CLEAN phase @s<k> [verification_preexisting]",
        prompt="[contexto: implementación existente verde + evidencia de clasificación]"
      )
      ```
      El subagente ejecuta el gate estructural sin cambiar comportamiento.

      ```
      task(
        subagent_type="tdd-refactor-ornith",
        description="REFACTOR phase @s<k> [verification_preexisting]",
        prompt="[contexto: test pasando + CLEAN verificado + evidencia de clasificación]"
      )
      ```
      Re-ancla; no ejecuta mutación ni certifica MSI aquí — la mutación completa es del
      coordinador y corre UNA vez en RELEASE. Refactor estructural solo si el diff lo
      requiere; no añade comportamiento nuevo.

RELEASE (gates de salida — ejecutar DESPUÉS del último @s; el coordinator es
  implementation-only y NO cierra la story):

  RELEASE SCOPE (determinar ANTES de ejecutar cualquier gate):
    - Los gates aplicables se declaran en la configuración del proyecto
      (`_bmad/custom/bmad-tdd-coordinator.toml` o el fichero de configuración del módulo).
    - Los gates N/A se registran como "N/A — skipped" y se omiten.
    - NUNCA escalar por un gate determinado N/A. Escalar solo por gates aplicables que fallan.

  Gates (los comandos exactos salen de la configuración del proyecto; los siguientes son
  los que el módulo define por defecto — un proyecto los sobreescribe en su override layer):
  - Mutation Gate: `{workflow.mutation_cmd}` (default `make mutation-check`) — SOLO coordinador,
    NUNCA delegar el veredicto a subagentes. MSI >= {workflow.msi_minimum} (default 85). Los mutantes
    sobrevivientes deben estar documentados en el mutant-register. PROHIBIDO añadir
    `# pragma: no mutate` — usar registro de mutantes.
  - Test Gate: `{workflow.test_cmd}` (default `uv run pytest`) — toda la suite pasa.
  - Release gates adicionales del proyecto (anti-fixture, puerto real, sonda de capacidad)
    se ejecutan si están declarados en el override layer del proyecto.
  - **Cierre = el flujo exterior (contrato bmad-loop):** el coordinator NO marca
    `status: done`, NO escribe `## Auto Run Result`, NO crea el completion marker
    `bmad-dev-auto-result-*` y NO edita sprint-status.yaml. Son responsabilidades
    del flujo exterior y del engine:
      * `bmad-dev-auto` (flujo genérico) ejecuta Verify y el step-04 Review, que
        escribe `## Auto Run Result`, fija `followup_review_recommended`, pone
        `status: done`, commitea y crea el marker (su `WORKFLOW_COMPLETION_CONTRACT`).
      * El engine de bmad-loop es single-writer de sprint-status.yaml
        (`_post_dev_state_sync`): avanza la story a `done` cuando el spec alcanza
        su estado de éxito. El coordinator no debe tocarlo.
    Si el coordinator editara esos artefactos, robaría el cierre al flujo exterior
    y el review de bmad-dev-auto (step-04) nunca correría.
  - Report: el coordinator reporta EVIDENCIA (salidas de los gates pegadas,
    demostrar, no afirmar) y DEVUELVE el control al flujo exterior (bmad-dev-auto);
    no termina el attempt. Después del report, el flujo exterior continúa Verify → Review.

Post-compactación / reanudación: ANTES de tocar código, releer
`{contracts_dir}/<story-key>.feature` + el spec de la story
(`{implementation_artifacts}/<story-key>.md`). La compactación destruye la intención;
solo el archivo persiste.

## State Machine

GHERKIN_GATE -> INTAKE -> PLAN -> CLASSIFY -> IMPLEMENT_LOOP -> INTEGRATE -> RELEASE -> [return to bmad-dev-auto: Verify -> Review -> DONE]
                |
                |--- GHERKIN_GATE: generate + review + auto-approve contract if missing (coordinator-auto)
                |--- For each @s: classify as development | verification_preexisting | ambiguous
                |--- development: RED -> GREEN -> CLEAN -> REFACTOR
                |--- verification_preexisting: GREEN (confirm) -> CLEAN -> REFACTOR (if modified)
                |--- ambiguous: STOP + report evidence gap
                |--- RELEASE: gates verdes + reporte de evidencia; el coordinator termina
                    su attempt aquí y devuelve el control. DONE lo cierra bmad-dev-auto
                    (step-04) y el engine (sprint-status).

## Gates

GHERKIN_GATE (antes de INTAKE):
0a. Contrato Gherkin autónomo: si no existe o está DRAFT → generar desde AC + revisar
    + auto-aprobar con `Approved-by: coordinator-auto`. Reglas de docs/contract-rules.md
    son non-negotiable. Máx 2 iteraciones de auto-revisión; luego HALT (escalación).

INTAKE:
0. Gherkin Gate (verificación): `{contracts_dir}/<story>.feature` con `# Status: APPROVED`
   — si GHERKIN_GATE no lo produjo, HALT (fallo interno, no pedir firma humana: modo loop
   es 100% autónomo)
0b. Consumo Gate: dependencia de capacidad previa se verifica ejecutando la verificación, no leyendo status

CLASSIFY (antes de cada @s):
0c. Pre-RED Classification Gate: determine scenario type per CLASSIFY rules above
    - development: proceed to RED
    - verification_preexisting: skip RED, proceed to GREEN with context
    - ambiguous: STOP and report evidence gap

Por @s:
1. RED Gate (development only): Test debe fallar (FAIL) antes de pasar a GREEN
1b. MUTANT-HUNTING REVIEW Gate (coordinador, NO delegar): ANTES de pasar a GREEN,
    el coordinador DEBE revisar el test del RED para verificar que es robusto y
    mata todos los mutantes potenciales. Si el test no es robusto, el coordinador
    DEBE enviar instrucciones específicas al RED para mejorarlo y repetir la revisión.
2. GREEN Gate: Test debe pasar (PASS) antes de pasar a CLEAN
2b. CLEAN Gate (estructural, NO delegar): ANTES de pasar a REFACTOR,
    el coordinador DEBE validar el output del tdd-clean con los 10 checks abajo.
    Si algún check FAIL → el coordinador decide: reintentar CLEAN (max 1 vez) o
    registrar gap en deferred-work (complejidad conocida, no cascarón).
3. REFACTOR Gate: pytest debe pasar. Full mutation is NOT part of REFACTOR; do not
   close a scenario on targeted `uv run mutmut run '<id>'` evidence alone.
4. Verification Preexisting Gate: ALL 5 conditions must hold to skip RED; MSI verified via
   el comando de mutación del proyecto o el fichero de stats, NEVER from bitácora alone

CLEAN Gate — validaciones del coordinador (NO delegar al modelo):

ESTRUCTURALES (qué dicen las herramientas):
  C1. `cleaner-gate` PASS en los checks (KISS, DRY, YAGNI, LoD, CoI, coverage, scan_sites)
  C2. Coverage = 100% en archivos del diff
  C3. `pytest` verde tras los cambios del CLEAN

SEMÁNTICAS (anti-cascarón):
  C4. Cambios solo estructurales, no de comportamiento (verificar diff)
  C5. Código sigue siendo ÚTIL — no cascarón vacío (pass, return None, stub sin lógica)
      → grep en diff: funciones de ≤2 líneas que solo delegan → REJECT
  C6. Funciones extraídas tienen cuerpo real — no middle-man que solo pasa parámetros
  C7. Split de archivos no rompió cohesión — cada nuevo archivo tiene responsabilidad clara

DE PRODUCTO (contrato):
  C8. Intención del producto intacta — cross-check contra spec + ACs del .feature
      → ¿los `Then` del escenario @s siguen siendo verificables tras el CLEAN?
  C9. Sigue planificación — no abstracciones no planificadas (YAGNI: si no está
      en el spec de ESTA story, no se añade en CLEAN)
  C10. Dependencias entre módulos respetan la arquitectura declarada del proyecto

Decisión del coordinador:
  - C1–C10 PASS → proceder a REFACTOR (invocar task tdd-refactor-ornith)
  - FAIL en C1–C3 → reintentar CLEAN (max 1 vez) con instrucción específica
  - FAIL en C4–C10 → REJECT: documentar gap en deferred-work, NO pasar a REFACTOR
    (es mejor complejidad conocida y documentada que cascarón con 100% MSI falso)

RELEASE (todos deben pasar para que el flujo exterior cierre la story):
4. Mutation Gate: `{workflow.mutation_cmd}` (SOLO coordinador, UNA vez tras el último @s —
   NUNCA delegar a subagentes). MSI >= {workflow.msi_minimum} (configurable, default 85) con
   100% coverage. Los mutantes sobrevivientes deben estar documentados en mutant-register.md.
   Inspección de mutantes conocidos: `mutmut show <name>` / `mutmut run '<name>'`
   (coordinador-owned, dirigida). No certificar con `mutmut results`.
   PROHIBIDO añadir `# pragma: no mutate` — usar registro de mutantes en su lugar.
5. Test Gate: `{workflow.test_cmd}` pasa (toda la suite).
6. Gates adicionales del proyecto (declarados en el override layer) — solo los aplicables.
7. Un AC de ejecución en vivo cerrado con SKIPPED/XFAIL es ROJO — la story se marca blocked.

> Los gates son la diferencia entre "los tests del stub pasan" (cascarón) y "el producto
> hace algo real". El coordinator NO marca `done` por sí mismo: los gates verdes son la
> condición necesaria para que el flujo exterior (bmad-dev-auto step-04) cierre la story.

## Constraints

- NUNCA delegar el MUTATION GATE de RELEASE a subagentes — el veredicto final MSI lo
  ejecuta el coordinador directamente, UNA vez tras el último @s. El subagente
  tdd-refactor-ornith NO ejecuta el comando de mutación durante REFACTOR: la mutación
  completa es propiedad de RELEASE. Para matar un mutante específico, el coordinador
  inspecciona con `mutmut show <name>` / `mutmut run '<name>'` (dirigida) — nunca corre
  el gate completo desde una fase.
- NUNCA skip phases in development scenarios (RED->GREEN->CLEAN->REFACTOR is mandatory)
  - Exception: verification_preexisting classification permits skipping RED only when ALL 5
    CLASSIFY conditions are satisfied AND evidence is documented in bitácora
  - CLEAN nunca se salta — es el gate estructural antes de mutation
  - ambiguous classification requires STOP — never invent RED, never skip phases
  - A RED that PASSES instead of failing is a protocol violation → STOP, no inventes un
    RED ni sigas; el gate mecánico lo bloquea con RED_VIOLATION.
- ALWAYS preserve protocol fidelity
- BITACORA OBLIGATORIA en cada @s (ROJO/VERDE/CLEAN/REFACTOR status; for verification_preexisting:
  document WHY classification was accepted — all 5 evidence points: commit hash, bitácora path:line,
  MSI source, function existence, unchanged status)
- PROHIBIDO `# pragma: no mutate`. Usar registro de mutantes para documentar sobrevivientes.

## Error Handling

- Si un test no falla en RED: STOP y reportar al usuario
- Si un test no pasa en GREEN: STOP y reportar al usuario
- Si mutmut falla en RELEASE: STOP y reportar al usuario con lista de survived mutants

## Output

- Bitacora TDD actualizada en story file
- Reporte de EVIDENCIA al flujo exterior (bmad-dev-auto): resultados de cada @s y salidas de los gates pegadas
- El cierre (Auto Run Result, status: done, marker, sprint-status.yaml) lo hace el flujo exterior / el engine
