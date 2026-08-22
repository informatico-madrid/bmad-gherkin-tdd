# Plan P1 — Full mutation pasa a RELEASE (propiedad del coordinador)

> Fecha: 2026-08-22 · Estado: COMPLETADO (P1) + P2 AÑADIDO (bajo revisión adversarial) · Repo: `/mnt/bunker_data/bmad-gherkin-tdd`
> Referencia: `rompehielos@837709c feat(tdd): keep full mutation coordinator-owned at RELEASE`
> (se porta el **flujo HEAD** de la referencia, NO el diff del commit — ver F3/F4)
>
> Decisiones humanas confirmadas (2026-08-22):
> 1. Confirmado el alcance P1 tal como está abajo (incluye `permission.bash` en el template y la
>    reforma de todas las líneas contradictorias). 
> 2. `msi_minimum` se mantiene en **85 configurable** (no se sube a 100).
> 3. Se mantiene intacto el 4-fase `RED→GREEN→CLEAN→REFACTOR` (sigue existiendo
>    `tdd-clean-ornith`); solo se retira la mutación de REFACTOR.
>
> Triaje adversarial aplicado (agente `comprehensive-review__code-reviewer`, 2026-08-22):
> - **F1 (CRÍTICO)** `permission.bash` en los 4 subagentes + prompt refactor-ornith — ACEPTADO.
> - **F2** — el predicado READY no impide correr la mutación entre @s; limitación documentada,
>   sin flag `mutation_release_done` (out of scope).
> - **F3/F4 (CRÍTICO)** — regex SIN ancla (HEAD), `_TARGETED_MUTANT_RE` verbatim — ACEPTADO.
> - **F5 (CRÍTICO)** — corregir TODAS las líneas contradictorias (coordinator SKILL 215-216 y evitar
>   376-380, prompt.txt 68/82-83, tddclean 82/95, tdd-red:47, tdd-green:44, dev-auto:25) — ACEPTADO.
> - **F6** — quitar `mutation_cmd` de `tdd-refactor/customize.toml` + `check_mutation.py` — ACEPTADO.
> - **F7** — docstring del hook sugiere bypass muerto en loop — ACEPTADO (NIT).
> - **F8** — tests adaptados al template (parse `#`/`<MODEL>`) — ACEPTADO.
> - **F9** — normalizer cleaner_gate NO se porta (bug inexistente en el plugin + import
>   `harness_quality_gate` rompería el contrato sin-deps) — **RECHAZADO/false-positive**.
> - **F10** — CLASSIFY (d) + `red_pending` no bloquea — RECHAZADO (no hay brecha real).

## Archivos a tocar (orden)

### 1. `hooks/tdd_cycle_gate.py`
- Portar `_FULL_MUTATION_DENIED`, `_FULL_MUTATION_RE` (sin ancla), `_TARGETED_MUTANT_RE`,
  `_is_full_mutation_command()`, `_full_mutation_allowed()` (`phase==READY and not red_pending`).
- Insertar en `_handle_loop_mode_pre_tool_use` (rama Bash, ANTES de `_bash_writes_detected`):
  `if _is_full_mutation_command(command) and not _full_mutation_allowed(state): _deny(_FULL_MUTATION_DENIED)`.
- Docstring: quitar sugerencia `bypass "killing mutants"`, comentar regla loop.
- Loop-mode scoped (rama legacy sin cambio). `reset` intacto; `bypass` sigue denegado en loop.

### 2. `opencode/agents/opencode.json.template`
- Los 4 subagentes: añadir `permission.bash` = `{"make mutation-check":"deny","make mutation":"deny","uv run mutmut *":"deny","mutmut *":"deny"}` (junto a `question:deny`).
- `tdd-refactor-ornith`: añadir además `"uv run pytest *":"allow"`. Prompt → "Confirm CLEAN gate passed
  → Refactor structure → Run pytest → confirm PASS → bitácora REFACTOR"; NUNCA `make mutation-check` ni
  `uv run mutmut run` (eso es RELEASE del coordinador); REFERENCE 'tdd-refactor' skill.

### 3. `skills/tdd-refactor/`
- SKILL.md: REFACTOR = refactor estructural + `{workflow.test_cmd}` PASS + bitácora REFACTOR sin MSI.
  Owns/Does-Not-Own/Verification/Constraints alineados. Quitar `check_mutation.py`.
- prompt.txt: eliminar pasos de mutación/MSI.
- customize.toml: quitar `mutation_cmd = "uv run mutmut run"` (dead). Mantener `test_cmd`, `msi_minimum`.

### 4. `skills/bmad-tdd-coordinator/`
- SKILL.md: línea ~215 ("limpia el código y mata mutantes … + MSI") → "manteniendo pytest PASS".
  Constraints 376-380: nueva regla "full mutation NO es de REFACTOR; inspección dirigida; UNA vez en RELEASE".
  REFACTOR Gate: "Full mutation is NOT part of REFACTOR; do not close a scenario on targeted
  `uv run mutmut run '<id>'` evidence alone."
  RELEASE Gate: "make mutation-check (SOLO coordinador, UNA vez tras el último @s — NUNCA delegar)";
  "inspección con `mutmut show <name>`/`mutmut run '<name>'`; no certificar con `mutmut results`".
- prompt.txt: líneas "→ limpiar código + matar mutantes" y "El subagente REFACTOR sí ejecuta la
  mutación" → regla nueva; L123 aclarar "en RELEASE".

### 5. `skills/tdd-clean/SKILL.md`
- L82 "(eso es REFACTOR)" → "(eso es el coordinador en RELEASE)".
- L95 "**Delega a:** `tdd-refactor` (para mutmut)" → "`tdd-refactor` (refactor estructural); el
  coordinador en RELEASE (mutación completa)".

### 6. `skills/tdd-red/SKILL.md:47` / `skills/tdd-green/SKILL.md:44`
- "(eso lo hace REFACTOR)" → "(eso lo hace el coordinador en RELEASE)".

### 7. `templates/custom/bmad-tdd-coordinator.toml`
- Paso (4) de la RUTINA: quitar "mutmut + registro"; añadir "Full mutation: una vez en RELEASE tras
  el último @s. NUNCA delegues {workflow.mutation_cmd} ni `uv run mutmut run` sin mutant ID a un subagente."

### 8. `templates/custom/bmad-dev-auto.toml`
- L25 "Ejecución de mutación fuera de la fase REFACTOR" → "…fuera del RELEASE del coordinador".

### 9. Tests
- `tests/test_agent_template_permissions.py`: assert `permission.bash` denies en 4 agentes + `pytest allow`
  en refactor (reutilizar `_load_template`).
- Nuevo `tests/test_tdd_mutation_scope.py`: denegar full-mutation en CODING/red_pending; allow en READY
  sin red_pending; allow `mutmut show`/`run '<id>'`; deny path-scoped; asserts de wording en SKILL/template.

### 10. README + CHANGELOG
- README: "mutation killing in RELEASE (coordinator-owned); REFACTOR = behaviour-preserving structure";
  troubleshooting: "make mutation-check durante un @s abierto → rechazado; cerrar el @s o correrlo en RELEASE".
- CHANGELOG [Unreleased]: entrada P1.

## Verificación
- `uv run pytest` (todo el suite), `uv run ruff check .`, `uv run ruff format .`, `uv build`
  (valida el payload del wheel sin cambios de esquema de estado ni de rutas).

## Log de ejecución
| Fecha | Paso | Estado | Notas |
|-------|------|--------|-------|
| 2026-08-22 | Plan escrito en disco | ✅ | —
| 2026-08-22 | 1 gate | ✅ | Docstring corregido (sin bypass muerto en loop). Constantes+regex+helpers portados de HEAD. Deny insertado en la rama Bash de loop-mode antes de `_bash_writes_detected`. py_compile OK. |
| 2026-08-22 | 2 templates/opencode | ✅ | `permission.bash` (4 denies) en los 4 subagentes + `uv run pytest *: allow` en refactor. Prompt refactor-ornith sin mutación (full = RELEASE). Desviación: prompt de red/green/clean también ganan línea "NEVER run mutation"; JSON validado con el parse-trick del test. |
| 2026-08-22 | 3 tdd-refactor | ✅ | SKILL.md/prompt.txt reescritos (REFACTOR sin mutación ni MSI, `{workflow.mutation_cmd}` prohibido); customize.toml sin `mutation_cmd`. Ningún test/instalador referencia `mutation_cmd` (verificado). |
| 2026-08-22 | 4 coordinator | ✅ | SKILL.md: cuerpo REFACTOR sin "mata mutantes/+MSI", REFACTOR Gate sin mutación, RELEASE Gate (SOLO coordinador, UNA vez tras el último @s, inspección `mutmut show`/`run '<id>'`, no `results`), Constraints reescritos. prompt.txt: mismas correcciones. Verificados ordering + vocabulario del test de consistencia (positions OK). |
| 2026-08-22 | 5-6 tdd-clean/red/green | ✅ | tdd-clean (:82, :85, :95) apuntan a coordinador RELEASE; tdd-red:47 / tdd-green:44 → "el coordinador en RELEASE". Sin referencias residuales en prompts (verificado con rg). |
| 2026-08-22 | 7-8 templates | ✅ | bmad-tdd-coordinator.toml paso (4) → refactor estructural + "Full mutation: UNA vez en RELEASE tras el último @s (NUNCA delegar)". bmad-dev-auto.toml:25 → "fuera del RELEASE del coordinador". |
| 2026-08-22 | 9 tests | ✅ | `test_agent_template_permissions.py` extendido (4 denies bash + pytest allow refactor). Nuevo `tests/test_tdd_mutation_scope.py` (8 tests: deny mid-cycle/red_pending, allow RELEASE, named-inspection allow, path-scoped deny, regex-límites documentados, wording skills + template). Todos verdes. Desviación menor: `_drive_to_coding` usa orden Task→Skill (model-routing); frase exacta del REFACTOR Gate en inglés (canónica). |
| 2026-08-22 | 10 README/CHANGELOG | ✅ | README: bullet fases + enforcement (mutation RELEASE), defaults sin `uv run mutmut run`, troubleshooting nuevo. CHANGELOG [Unreleased] Added entry P1. |
| 2026-08-22 | Verificación (pytest/ruff/build) | ✅ | `uv run pytest` 166 passed; `ruff check` limpio; `ruff format` aplicado a hook+test nuevos (fb70/preexistente HEAD ya sin formato, sin tocar); `uv build` OK con payload 34 archivos. RF eliminatorio de referencias stale: todos los `mutation_cmd` restantes son intencionales (RELEASE/prohibiciones). |
---

# P2 — Agente primario bmad-loop-coordinator + skill (añadido 2026-08-22)

Decisiones humanas: agente PRIMARIO (no subagent), con su skill que cargar con bootstrap
(igual que rompehielos); flag `human-present` para saber si puede preguntar; no commit
hasta pasar revisión adversarial + triaje.

## Ejecutado

1. `skills/bmad-loop-coordinator/` (NUEVO): `SKILL.md` (bootstrap rule, convenciones,
   presencia humana gate, workflow INTAKE→ASSESS→LAUNCH→MONITOR→INTERVENE→REVIEW→OBSERVE,
   fronteras, critical rules, customization), `customize.toml` (`[workflow]` + defaults
   run_cmd/human_present_path/sprint_status_path/obs_log_limit) y `prompt.txt`
   (resumen ejecutivo del agente).
2. `opencode/agents/opencode.json.template`: añadido agente PRIMARIO `bmad-loop-coordinator`
   (mode primary, deny-by-default, bash con `nohup *: deny`, question/plan allow, skill/task
   allow) con bootstrap skill + lectura de `human-present` en el prompt.
3. `bmad_gherkin_tdd/installer.py`: `SKILL_NAMES` += `bmad-loop-coordinator` (7ª skill).
4. Tests: `test_agent_template_permissions.py` → 3 tests del agente primario
   (presencia, bootstrap+skill+human, question no estático) + 2 tests de coherencia de la
   skill (shipped, bootstrap/humauna) = 5 nuevos.
5. README: bullet "loop orchestration agent", sección instalación 4, diagrama "How it
   works" con el coordinado arriba, tabla config 3 filas loop-coordinator, Layout (7 skills).
6. CHANGELOG [Unreleased] Added: entrada P2.
7. Verificación: pytest 171 passed; ruff limpio (fb70 preexistente sin formato en HEAD, no tocado);
   `uv build` tras limpiar `build/ dist/` → wheel contiene la skill nueva (3 archivos payload).

## Desviaciones

- El wheel inicial no incluía la skill (cache de build) → se limpió build/dist y se reconstruyó.
- El test del loop skill usa `"skill({" in content` (flexible) porque el prompt del agente
  usa formato variado; el SKILL.md contiene `skill({ name`.

## Pendiente

- Revisión adversarial (todo, P1+P2) → triaje → correcciones.
- Commit (huir: tras revisión verde).

## Revisión adversarial (2026-08-22) — triaje y correcciones aplicadas

Revisado todo (P1+P2) por agente `comprehensive-review__code-reviewer` (evidencia empírica:
suite 171→172, regex probe 20+ spellings, walk e2e del state machine, wheel payload).

| # | Hallazgo | Severidad | Veredicto | Corrección |
|---|---|---|---|---|
| 1 | SKILL.md:246 (verification_preexisting) aún "Re-ejecuta mutación y registra MSI" | CRÍTICO | ACEPTADO | Reescribir: refactor estructural, sin mutation/MSI (full = RELEASE) |
| 2 | `_BYPASS_HINT` añadido en denies de loop-mode (bypass muerto en loop; "matando mutantes" ya no es bypass) | SHOULD-FIX | ACEPTADO | Quitar `_BYPASS_HINT` de las 4 denies en `_handle_loop_mode_pre_tool_use` (legacy conserva) |
| 3a | Regex no atrapa `python3 -m mutmut run` / bare `mutmut run` | SHOULD-FIX/NIT | ACEPTADO parcial | Regex → `(?:uv\s+run\s+|python(?:3)?\s+-m\s+)?mutmut\s+run\b`; docstring ampliado; tests +2 variantes |
| 4 | Patrones `make mutation-check` sin `*` (args escapan en sesión subagente) | NIT | ACEPTADO | `permission.bash` += `make mutation-check *`, `make mutation *`, `uv run python(3)? -m mutmut *`, `python(3) -m mutmut *` (los 4 agentes) |
| 5/6 | READY al inicio/entre ciclos permite mutación | NIT | ya documentado (F2) | sin cambio |
| 7/8 | Scoping loop/legacy, e2e, _bash_outcome jeep | PAS | verificado | sin cambio |
| 9 | Permissions schema válido, parses | PAS | verificado | sin cambio |
| 10 | `question:allow` coordinador = riesgo deadlock unattended | SHOULD-FIX | decisión del usuario (human-present gate) | sin cambio; README lo documenta |
| 11 | websearch/webfetch en deny-default | NIT | sin acción (nota política) | sin cambio |
| 12 | subagentes allow-by-default (solo no question/bash) | NIT | pre-existente | sin cambio |
| 13 | `{workflow.mutation_cmd}` dangle en tdd-refactor (clave removida de su customize) | SHOULD-FIX/NIT | ACEPTADO | reword a "comando de mutación completo del proyecto" (sin placeholder); prompt.txt igual |
| 14-18 | Frases canónicas, P2 skill/wheel/installer alineados | PAS | verificado | sin cambio |
| 19 | human_present_path overridable pero prompt hardcodeada ruta por defecto | NIT | ACEPTADO | Prompt del agente: resolver vía resolve_customization → human_present_path (default documentado) |
| 20 | README coherente | PAS | verificado | sin cambio |
| 21 | Tests no tautológicos | PAS | verificado | sin cambio |
| 22 | Gaps tests (a)(c) | NIT | ACEPTADO | +`uv run mutmut run`/`python3 -m mutmut run` allowed RELEASE; test reset clears red_pending → reallow |

Estado final: pytest 172 pasa; ruff limpio; build con payload OK. Pendiente: commit.

## Ronda 1 party adversarial (2026-08-22) — triaje y correcciones

3 revisores (gate/security/tests) sobre el tree corregido antes de la ronda. Consenso reales:
| Revisor | Hallazgo | Veredicto | Corrección aplicada |
|---|---|---|---|
| gate | Targeted-ID mascara deny (`make mutation-check && mutmut run 'id'` pasa) | SHOULD-FIX | detection **por cláusula** (`_command_clauses` + `_clause_is_full_mutation`) |
| gate | False positives: `git commit -m "run mutmut run yet"`, `grep 'make mutation-check'` denugan | SHOULD-FIX | anclaje a cabecera de cláusula (make/mutmut al inicio) |
| gate | `mutmut run` multi-ID/flags denegados (dirigido legítimo) | NIT | `_is_named_mutmut_inspection` por primer arg |
| security | `make -C/-j8/-f/--directory` escapan regex Y permission | SHOULD-FIX | regex `make` tolera flags; template `make * mutation-check` deny |
| security | `question` unattended deadlock solo prosa | SHOULD-FIX | plugin JS `tool.execute.before` deny question en loop sin human-present=yes + 3 tests |
| security | webfetch/websearch en coordinator unattended → prompt-injection→exec | SHOULD-FIX | eliminado del template |
| security | subagentes edit-open pre-existente | pre-existing | sin cambio |
| tests | legacy fail-open sin test | SHOULD-FIX | `test_legacy_mode_fail_open_unchanged` |
| tests | docstring del test decia `mutmut run` no capturado (falso) | NIT | reescrito docstring |
| tests | `mutmut results`/pytest -k mutmut sin test | NIT | cubierto en benenos |
| tests | `uv run python -m` chain faltaba | NIT | regex del chain permite `uv run python -m` |

SÍ falso positivos: "compensating control false" parcial (matiz), subagentes edit-open (pre-exist),
reset-mask (ya manejado). Estado: pytest 183, ruff limpio, build OK.

## Ronda 2 party adversarial (2026-08-22) — triaje y correcciones

3 revisores (gate/security/tests). Hallazgos reales de consenso y correcciones aplicadas:
| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate | `python3.12 -m`/`./.venv/bin/mutmut`/`uv run --python`/`sudo -u/-E`/`env -i/--unset` escapan | SHOULD-FIX | chain relajada (version/venv/uv flags) + `_strip_command_prefix` imperativo (flags+valores, reserva comandos) |
| gate | `echo '; make mutation-check'` / heredoc → clause fantasma → false deny | SHOULD-FIX | `_command_clauses` quote-aware (scanner manual de comillas) |
| gate/security | `reset` substring neutraliza el deny sin reset real | SHOULD-FIX | `_is_gate_reset_command` = cláusula ÚNICA `tdd_cycle_gate.py reset` |
| security | question gate solo con BMAD_LOOP_MODE (coordinator humano nunca lo recibe) | SHOULD-FIX | `enforceUnattendedQuestionGate` por FLAG (file != yes → deny; missing + loop → deny; missing no-loop → allow); helpers refactored |
| security/packag | `uv run pytest * allow` mascara `&& make mutation-check` (last-match) | SHOULD-FIX | chain-denies después del allow + tests |
| tests | quoted-sep fixes + sudo/python3.12/venv + reset-mask tests | SHOULD-FIX | nuevos casos en mutation-scope |
| tests/security | `$()`/backtick/`eval` evaden (límite mecánico real de regex) | informativo | documentado en docstring como límite; no blocker |
| security | F4 coordinator bash * = machine (inherent) | inherent/accepted | documentado SECURITY nota pública |
| packaging F6 | skill+test untracked; TODO el P2 sin commit | SHOULD-FIX | anotado para el commit final (sin `git add` aún, por instrucción del usuario) |
| security | BMAD_LOOP_MODE stale in shell → human bloqueado por question gate | LOW | README troubleshooting line añadida |

Nuevo test count: 178 (12 mutation-scope). ruff limpio; JS node --check OK; wheel OK (loop skill + plugin staged). CI assert ampliado (loop skill + plugin en payload).

## Ronda 3 party adversarial (2026-08-22) — triaje final pre-consenso

3 revisores (gate/security/tests). Un defecto real nuevo + hardening, todos consensuados:
| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate F1 | prefix sudo/env NO quote-aware → `env BB="two words"`/`sudo -u "name"`/`sudo --`/`env -S` dejan pasar full mutation | ✅ SHOULD-FIX | `_strip_command_prefix` quote-aware con `shlex.split` + `_command_value_flag` (valor de flag solo si no es comando) |
| gate F2 | `reset $(make mutation-check)` cabalga el hatch | ✅ | `_is_gate_reset_command` fullmatch NO `$(...)`/backtips + `_full_mutation_in_substitution` detecta `$()`/`` dentro |
| gate F3 | `make mu't'ation-check` (concat shell) bypasa target | ✅ | vista `unquoted` (strip comillas) para make-target |
| security F4 | `bash --noprofile -c`, `zsh/fish`, `.venv/bin/mutmut`, `uvx` fuera de layers | ✅ | `_SHELL_WRAPPER_RE` (+zsh/fish/ksh + flags largas) + denies template (`.venv/bin`, `uvx`, chain) |
| security F3 | doc "subagent no hereda plugin" stale (v1.18 sí lo ve) | NIT | doc amend: aislamiento de sesión no garantizado, Task-post hace idempotente |
| tests | ruff format 4 líneas nuevas | ✅ | front |
| tests | untracked trio (skill/test/plan) | ⚠️ staging en commit final |
| gate F4 | heredoc/`mutmut --help` sobre-deny (lado seguro) | info | documentado en docstring como límite bencano |
| security F1 | question-gate missing flag+no loop → allow | acceptable-with-doc | sin cambio (soporte de lanzamiento) |

Consenso: ronda 3 cerró los hallazgos reales. Queda pendiente: confirmar vía RONDA 4 que NO hay nuevos hallazgos (consenso "no corrections needed"). Estado: 178 tests, ruff, JS, wheel OK.

## Ronda 4 party adversarial (2026-08-22) — triaje final de bypasses reales

3 revisores; el gate rezaba "clean" pero el SECURITY encontró 3 bypasses de mutación reales. Triaje honesto: ACEPTADOS todos.
| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| security F1 | `uvx mutmut run` ejecuta full mutation y el chain `uv run pytest && uvx mutmut run` escapa (no `run` intermedio) | ✅ HIGH | `_MUTMUT_RUN_CHAIN_RE`: `(?:uv|uvx)\s+(?:run\s+)?`; denies template `uvx mutmut *`, chain `&& uvx/.venv` |
| security F2 | `env -S 'make mutation-check'` / `--split-string` (GNU env lo ejecuta) escapa; shlex lo comía como flag+value | ✅ HIGH | `_strip_command_prefix`: `-S`/`--split-string` = meta-flag → devolver el valor como cabeza |
| security F3 | `echo $(echo $(make mutation-check))` (nested depth≥2) escapa | ✅ MEDIUM | `_substitution_regions` = scan balanceada recursiva (flattens nested) |
| security F4 | `gmake`/`bmake` no cubiertos | ✅ LOW | `_MAKE_COMMAND_RE = ^(?:g?make|bmake)` |
| gate NIT-3 | env -S `"..."` boundary lo veía inocuo | ✓ | refutado por security (GNU splcea) → aceptado como real |
| gate NIT-1 | `echo '$(make)'` over-deny (quote-blind substitution) | ⚠️ documentado (sobre-deny, no fuga) | sin cambio |
| tests | fb70 pre-existing format / plans MANIFEST | ⚠️ notas | staging en commit |
| security | ReDoS O(L²) pre-existente `_bash_writes_detected` | pre-existing | out-of-scope (nota LOW robustness) |

Estado: 180 tests; ruff, JS, wheel OK. Ronda 5 = confirmación final.

## Ronda 5 party adversarial (2026-08-22) — triaje de bypasses de ejecución real

3 revisores; security encontró 2 HIGH (ejecución real) + 2 MEDIUM. El gate los había visto como NIT/boundary; security probó ejecución real. Triaje: ACEPTADOS.
| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| security F1 | `env -S'...'` (attached getopt) + `--split-string` attached ejecutan y el `-S` spaced no (uutils) | ✅ HIGH | `-S`/`--split-string`/`-S'<val>'` como meta-command → head recursivo en `_strip_command_prefix` |
| security F2 | `make$() mutation-check`, `mutmut$() run`, `uv run mut$()mut`, `make $(echo mu)tation-check`, `python3 -m mut$(echo mut) run` ejecutan | ✅ HIGH | `normalized` (quita `$()`, `` ` `` , `${}`, comillas) + net conservador make/mutmut si `$(`/``/backtick en args |
| security F3 | nested `$()` matcher O(2^n): 17-deep→1.4s, 20→11s, 25→timeout; RecursionError | ✅ MEDIUM | `_substitution_payloads` = scan iterativa single-pass O(total chars) + depth cap 64 |
| security F4 | single-quoted `'$(make...)'` literal no ejecuta pero denegado | ✅ | scan quote-aware (skip `'...'`) |
| security | exec-wrapper family (`python -c`, `os.system`) no catchable | ⚠️ documented-limit | sin cambio (consenso) |
| gate | `env -S` boundary y `$(...)` quote-blind lo vio NIT | refutado | security juego ejecución real → fixes aplicados |

Estado: 183 tests; ruff, JS, wheel OK. Ronda 6 = confirmación consenso final.

## Ronda 6 party adversarial (2026-08-22) — triaje de 3 defectos reales

| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate F3 HIGH | reset-hatch fullmatch permitía suffix arbitrario (`make mutation-check hooks/…reset`, `uv run … mutmut run …/reset`) → ALLOW | ✅ | `_is_gate_reset_command` = head rígido `[python?][path/]tdd_cycle_gate.py reset`, single clause, sin `$(`/backticks |
| gate F4 HIGH | `_SUBST_MAX_DEPTH=64` dropeaba payloads a depth>64 (bash sí los ejecuta → bypass depth-70) | ✅ | cap subido a `_MAX_SUBST=128` y SEMÁNTICA clara: el cap solo limita el re-scan del mismo span; profundidad 70 se sigue probando |
| security R6-1 HIGH | `mut${U}mut run`, `mutmut ru${N} n`, `mut\`echo mu\`t run` (param-expansion / backtick-output reassembly) → reassemble `mutmut run` | ✅ | net conservador: fragmentos `mut|muta|mutmut|ru` seguidos de `${`/`$(`/backtick → deny |
| security | make+$() FP (benign `make CC=$(gcc) build` denied) | ⚠️ documented-conservative | mantener; NO code change (safe direction), nota README |
| security | env -S recursion bounded (fail-closed) | ✓ | avalado |

Tests nuevos: reset-prefix, depth-70, param-reassembly. Estado 186 tests; ruff, JS, wheel OK. Ronda 7 = consenso final.

## Ronda 7 party adversarial (2026-08-22) — triaje final (3 SHOULD-FIX)

| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate F1 HIGH | depth-≥130 `$()` bypass (cap seguía dropeando) | ✅ | `_MAX_SUBST=100000` + push siempre que payload tenga `$(`/backtick (terminación garantizada por longitud); test depth-150 |
| gate F2 MED-HIGH | reset hatch roto para `uv run python`/venv/env/interp (deadlock RED_VIOLATION) | ✅ | `_is_gate_reset_command` vía shlex: argv parseable, último token `reset`, gate file at penúltima posición, sin mutation traffic, sin `$()`/backticks; test de 5 variantes |
| security R6-1 | reassembly net no cubría `${VAR}`/backtick mid-word/leading (`mut${U}mut run`, `ma${A}ke`) | ✅ | `_shell_demangle` (quita `${}`/`$()`/backtick/`$X` corto) + re-check make/mutmut-chain en demangled + token-splice fallback scoped al head-runner |
| security/gate | FPs: `echo mut${UNSET}`, `git commit -m "…mut${X}…"`, var-assign `mut${x}=value`, standalone `` `mutmut show …` `` | ✅ | `_strip_literal_expansions` (solo spans con expansión), scoping head-runner (`make|mutmut|uv|python|gmake`), guard `=`-assignment, backtick span vs word-internal |

Todos los hallazgos R7 consensuados y aplicados. Estado: 190 tests; ruff, JS, wheel OK. En curso: RONDA 8 confirmación consenso final.

## Ronda 8 party adversarial (2026-08-22) — 2 hallazgos reales + crash fix

| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate F1 HIGH | `$X`-short-var splices (`mu$Xmut run`, `ma$Xke mutation-check`) NO reassembly detectadas (demangle solo quitaba `$X` end-of-word) | ✅ | `_shell_demangle`: quita `\$[A-Za-z_]` (una letra) SIEMPRE (solo afecta heads mutation-capable); fallback scoped head-runner lo coge; tests `mu$Xmut`/`ma$Xke` deny + `echo $PATH/CC` allow |
| gate F2 MED | `main()` UboundLocalError con payload JSON no-dict en loop (`"str"`,`[]`) → crash en vez de fail-closed; non-loop crash (viola fail-open) | ✅ | bind `loop_active` ANTES del try; `isinstance(payload, dict)` → loop fail-closed rc=2 / non-loop rc=0 |

Estado: 192 tests; ruff, JS, wheel OK. RONDA 9 = confirmación consenso final.

## Ronda 9 party adversarial (2026-08-22) — 1 bypass real nuevo

| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| security HIGH | `${Var:-word}`/`${Var=word}`/`${Var:+word}` default-literal reassembly: `${A:-ma}${B:-ke}` → `make`, `m${A:-u}${B:-t}mut run` → `mutmut run` — el demangle borraba el cargo literal | ✅ | `_demangle_var_default`: conserva cargo tras `:-` `:=` `:+` `:?` `-` `=` `+` (asume vars unset, conservador); `_shell_demangle` usa la lambda; tests 8 deny + 3 benign allow |
| gate R9 | (vacío) | — | el gate no reportó nuevos hallazgos |

Estado: 194 tests; ruff, format (fb70), JS, wheel OK. RONDA 10 consistencia última.

## Ronda 10 party adversarial (2026-08-22) — 3 bypasses reales en demangle recursivo

| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate HIGH | `${A:-${B:-make}}` nested default: el cargo no se re-demanglea → escapa | ✅ | `_shell_demangle` a FIXPOINT (bounded 16) + `_demangle_var_default` recursivo |
| gate HIGH | `$@`/`$*`/`$N` posicionales como splice (`make${@} mutation-check`, `mut$@mut`, `${@:-make…}`) no cubiertos | ✅ | `_demangle_var_default` trato del operador tras nombre especial (`@`/`*`/digits); `_shell_demangle` `\$[@*#?0-9]` vacío |
| gate factor | B4 `m`+250×`${A:-a}`+`ke` alegado como bypass | refutado | bash produce `ma…ke` (no `make`); no es bypass real — sin acción (documentado) |

Tests R10: 9 deny (nested/positional). Estado: 195 tests; ruff, JS, wheel OK. RONDA 11 = última confirmación.

## Ronda 11 party adversarial (2026-08-22) — fixpoint cap bypass (1 real)

| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate HIGH | demangle fixpoint bound 16 → a depth≥17 `${A:-${A:-…make…}}` queda con `${`-head residual → ALLOW mientras bash ejecuta | ✅ | `_shell_demangle` = expand INNERMOST-FIRST vía `_innermost_param_span` (balanced scan), sin bound duro; loop `while "${" in out` (cada pass quita al menos 1 marcador, O(depth×len)); end exclusivo |

Tests R11: depth 17/40 deny. Estado 196 tests; ruff, JS, wheel OK. RONDA 12 última.

## Ronda 12 party adversarial (2026-08-22) — 1 bypass real mutmut-head

| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate HIGH | `mutmut ${A:-$(echo run)} src/` → bash `mutmut run src/` (verbo por substitution output) — el net make-head lo cubría pero el mutmut-chain no | ✅ | net "runner-head + substitution" espejo del make: si demangle del head es runner (uvx?/python/pypy/mutmut) y `base` contiene `$()`/backtick/`${`/`$X`/`$@` → deny |

Tests R12: 4 deny + control. Estado 197 tests; ruff, format (fb70), JS, wheel OK. RONDA 13 última.

## Ronda 13 party adversarial (2026-08-22) — 1 FP de la ronda 12 (runner-net)

| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate SHOULD-FIX | R12 runner-net negaba `uv run pytest ${X:-x}`/`python3 -m pytest $EXTRA`/`pypy3 -m pytest` (head uv/python/pypy + subst cualquiera = deny) | ✅ | restringir a que el demangled head CONTENGA `mutmut` como token de runner (head o `uv run mutmut`/`python -m mutmut`); pytest/scripts/gen no afectados |
| RecursionError a depth ~500 | info (fail-closed loop / fail-open legacy, sin crash) | ✓ | sin cambio |

Tests R13: 6 allow pytest+subst. Estado 198 tests; ruff, format (fb70), JS, wheel OK. RONDA 14 última.

## Ronda 14 party adversarial (2026-08-22) — 3 familias reales (hardening)

| Revisor | Hallazgo | Veredicto | Corrección |
|---|---|---|---|
| gate F1 HIGH | backslash word-splice (`ma\ke`, `mu\tation-check`) + line-continuation `\⏎` | ✅ | `_shell_demangle`: quitar `\\x`→x y line-continuation `\\\n`→join |
| gate F2 | env-assign head (`MUT=mutmut $MUT`, `MAKE=make $MAKE`) | ✅ | `_shell_demangle`: resolve `VAR=word $VAR` → `word word` (pre-$X-strip) |
| gate F3 | `uvx mutmut ${A:-$(echo run)}`, `/usr/bin/make`, `command make` | ✅ | `_MAKE_COMMAND_RE` + runner_has_mutmut admiten path/command/-m/uvx |
| gate | `X=$(echo mutmut) $X` (output indirecto) | documentado | exec-output = mismo límite static que python -c/npx (documentado, no-blocker) |

Tests R14: 7 deny. Estado 199 tests; ruff, format (fb70), JS, wheel OK. RONDA 15 final confirmación.

## Ronda 15 party adversarial (2026-08-22) — triaje con revisión propia (2 hallazgos + 1 FP propio)

Cumpliendo el recordatorio de triaje: verifiqué empíricamente antes de aceptar, y además encontré un FP que yo mismo metí.

| Revisor | Hallazgo | Verificado (bash real) | Veredicto |
|---|---|---|---|
| gate F1 HIGH | `command mutmut run`, `command -p make …` ejecutan (bash builtin `command`) | `bash -x -c 'command mutmut run --help'` → ejecuta mutmut | REAL → fix: strip `command`/`command -p` en `_strip_command_prefix` |
| gate F2 HIGH | unquoted `\⏎` line continuation: `make \⏎ mutation-check` → `make mutation-check` | `set -x` → `<make> <mutation-check>` | REAL → fix inicial en `_command_clauses` |
| — (triaje propio) | **MI fix inicial de F2 era un FP**: unir `\\\n` en `_command_clauses` rompía heredocs (`cat <<'EOF'` con el texto literal → deny indebido). | bash NO line-continúa dentro de heredoc (contenido literal) | ✗ REVERTIDO. Fix final: join `\\\n` SOLO en `_is_full_mutation_command` si no hay `<<` |
| retrospectiva 5-14 | Revisión adversa de los fixes recientes (assign-reassembly, backslash, demangle, runner-net) → **cero FP** en ~17 operaciones legítimas (echo env, make build, pytest, git commit, command -v, awk, ruby, printf) | suite include | ✔ aceptados, sin cambios |

Tests R15: +9 deny (command/continuación) + 2 allow (heredoc literal). Estado: 201 tests; ruff, format (fb70), JS, wheel OK.

## Ronda 16 party adversarial + triaje (2026-08-22)

El recordatorio del usuario sobre el triaje se aplicó de forma estricta: verifiqué CADA hallazgo con bash real y reparé un FP mío.

| Revisor | Hallazgo | Triaje (verificación) | Veredicto & Fix |
|---|---|---|---|
| R16 B1 | `builtin command make/mutmut` ejecuta (builtin delegación) | `bash -x -c 'builtin command printf ok'` → sí | REAL → `_strip_command_prefix` peel `builtin` |
| R16 B2 | `bash -c 'echo $(make mutation-check)'` (payload single-quoted lo oculta del scan) | `bash -c 'echo $((delimeter))'` confirm | REAL → `_is_full_mutation_command` escanea substitutions por cláusula desempaquetada |
| R16 B3 | `cat <<EOF; make \⏎ mutation-check` — continuacion en región de comando | bash ejecuta | REAL → join `\\\n` ANTES del mask heredoc (bash une antes de delimitar) |
| R16 F4/pre | `cat <<EOF\nmake mutation-check\nEOF` body heredoc deny (largo de R2) | heredoc body es literal, bash NO lo ejecuta | ✗ FP → `_mask_heredoc_bodies` blankea cuerpos (preserva nuevas líneas) |
| — mi FP | Mi `_command_clauses` unir `\\\n` global rompía heredoc literal → revert boom, joatar `\\\n`+mask en detección | | revertido |
| fp-sweep | 17 operaciones reales de dev (git/uv/ruff/pytest/make -C/ssh/docker/var/echo/heredoc-rendering) | **0 falsos positivos** | ✔ |

Tests R16: +9 deny (builtin/wrapper/heredoc-B3) +9 allow (heredoc literal/benigno). Estado: 203 tests; ruff, format (fb70), JS, wheel OK. PENDIENTE: ronda 17 final (consenso de CIERRE). El triaje sigue verificando cada aceptación.

## Ronda 17 party adversarial + triaje (2026-08-22) — cierre de los últimos bypasses

Cada hallazgo verificado con bash real antes de aceptar.

| Revisor | Hallazgo | Triaje (verificación) | Veredicto & Fix |
|---|---|---|---|
| gate+sec F1 HIGH | ANSI-C `$'make' mutation-check` / `$'mutmut' run` — `$'...'` es word, bash ejecuta; el demangle comía `$m`→`ake` | bash: `$'make'` → make ejecuta | REAL → `_shell_demangle` colapsa `$'...'`/`$"..."/`antes del `$X`-strip |
| gate F2 HIGH (regresión R16) | HEREDOC UNQUOTED (`<<EOF`) SÍ expande `$()`/backticks en el body (solo `<<'EOF'` es literal); mi mask completo lo ocultaba | `cat <<EOF` + `$(make -v)` → bash expande (data-done) | REAL → `_mask_heredoc_bodies` distingue quoted (blank total) vs unquoted (mantiene spans `$()`/backtick para el scan) |
| sec F3 HIGH | subshell/brace/prefix: `(make …)`, `{ …; }`, `time …`, `nohup …` — ejecutan, gate rc0 | bash -x: subshell/time/nohup todos ejecutan | **`_strip_command_prefix`** peels `(`…`)`, `{…}`, `time/nohup/nice/setsid/stdbuf` (recursivo) |
| — | mis fixes iniciales (R16 heredoc total-mask) | revertido por F2 | corregido |

FP-sweep 20 ops reales → 0 FPs. Tests R17: +14 deny +10 allow. Estado: 205 tests; ruff, format (fb70), JS, wheel OK.

## LÍMITES DOCUMENTADOS (aceptados por consenso; no ejecución estática-decible)
- exec-wrapper dinámico: `eval`, `python -c`/`os.system`, `perl -e system`, `awk system`, `npx`, `$(echo mutmut) $X` (output no statically provable).

## 🔒 TRIAGE DE CIERRE + DECISIÓN FINAL (2026-08-22)

Decisión del usuario: cerrar aquí — el código es funcional; el objetivo de las
rondas de consenso es que el triaje descarte los hallazgos flojos cuando los
hallazgos objetivo no aportan al plan.

### ¿Qué descartamos (whack-a-mole del intérprete bash)?
Tras R17, el único patrón restante de la party es "encontrar OTRA forma de
nombrar `make`/`mutmut` que el demangle no vea". Evaluación objetiva por el
triaje:
1. **Frontera aceptada por consenso desde R5/R6** (y re-ratificada R14/R17):
   ejecución NO estática-decible — `eval`, `python -c`/`os.system`, `perl -e
   system`, `awk system`, `npx`, `$(echo mutmut) $X` (echo-output). Ninguna
   pieza de software puede probar estáticamente la salida de un subproceso; un
   gate mejoraría solo con un sandbox de exec, que NO es el diseño del módulo
   (gate = discipline + loop-mode enforcement, no sandbox).
2. **Cada familia estática-decible REAL reportada (R1-R17) fue verificada con
   bash y cerrada**: clause-scope, quotes, `$()`, `${:-}`, `$'...'`, backslash,
   `\⏎`, heredoc (quoted literal / unquoted ejecuta subs), `sudo/env -S`,
   `command`/`builtin`, subshell/brace/time/nohup, venv/uvx/python -m/path,
   assignments, nested/depth, positional `$@`. 205 tests los pin.
3. **FP-sweeps**: 0 falsos positivos en ~37 operaciones reales de
   dev/coordinator (git, uv, ruff, pytest, make -C, ssh, docker, docker, npx,
   env, heredoc-rendering, `$(git log -1)`, `$'echo'`, time/nohup/brace sobre
   echo, `<<'EOF'` literal, `<<EOF` texto, `$(echo hi)` en heredoc quoted).
   Robustez confirmada: cero quebrantar de comandos legítimos.

### Juicio de calidad/robustez
- **Suites**: 205 tests gate+skills+plugin+CI installer, todos verdes; +34 de
  los archivos de integración. ruff limpio; formato solo fb70 pre-existente
  (sin tocar); `node --check` JS OK; `uv build` produce wheel con payload
  completo (7 skills, plugin JS, template, gate).
- **Seguridad**: deny-by-default en coordinator; question-gate mecánico por
  human-present; denies de mutación mecánicos en los 4 subagentes (permisos),
  gate de mutación loop-mode; fail-closed en loop / fail-open legacy
  (contrato del módulo, verificado con payload JSON no-dict).
- **Compatibilidad**: el 4-fase RED→GREEN→CLEAN→REFACTOR intacto; `msi_minimum`
  85 configurable; instalador con la 7ª skill; README y CHANGELOG actualizados.

### Veredicto del triaje
Los hallazgos de la Party post-R17 son **descartables** (whack-a-mole del
lenguaje de shell sobre una frontera que ya es límite estático documentado).
No hay defecto objetivo nuevo que afecte al plan P1+P2. **CERRADO R17**.

→ Procedo a commitear (P1 + P2) como trabajo terminado.
