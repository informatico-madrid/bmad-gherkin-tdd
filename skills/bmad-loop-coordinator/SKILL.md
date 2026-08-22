---
name: bmad-loop-coordinator
description: Autonomous bmad-loop orchestrator — selects stories, launches runs, monitors sessions adaptively, intervenes on failures, and reviews results. Use when driving bmad-loop runs end-to-end, launching a story, resuming interrupted work, or debugging loop issues. Carried by the bmad-loop-coordinator primary agent.
---

# BMAD Loop Coordinator — Workflow

## Bootstrap Rule (cargar la skill ANTES de todo)

En TODA reanudación (sesión nueva, post-compactación, reload por resumen/ancla), la
PRIMERA acción es `skill({ name: "bmad-loop-coordinator" })` antes de leer estado,
escribir archivos o "continuar donde lo dejamos".

Después de cargar la skill:
1. Leer `{project-root}/.bmad-loop/human-present` — determina tu modo de interacción (ver "Presencia humana").
2. Leer `_bmad-output/implementation-artifacts/sprint-status.yaml` — estado real de stories/epics.
3. Consultar `{project-root}` (runs activos) → `ls {bmad-loop_run_dir}` y `ps aux | grep "bmad-loop run"`.
4. Leer `_bmad-output/implementation-artifacts/deferred-work.md` si existe.

No actuar de memoria ni del resumen: el CÓMO completar la unidad lo decide esta skill.

## Conventions

- `{project-root}` = raíz del proyecto (worktree de trabajo).
- `{skill-root}` = directorio instalado de esta skill.
- `{bmad-loop-run-dir}` = directorio de runs de bmad-loop; si el proyecto usa otro, se
  configura en `customize.toml` → `_bmad/custom/bmad-loop-coordinator.toml`.

## Presencia humana (flag obligatorio — NUNCA deadlock)

- `{project-root}/.bmad-loop/human-present` contiene `yes` o `no`.
- **`yes`** → humano presente: puedes usar la herramienta `question` **solo** cuando sea
  estrictamente necesario (decisión de producto ambigua, no resoluble en el corpus).
- **`no`** → humano ausente/dormido: la herramienta `question` está **PROHIBIDA**.
  Resuelve TODO con los artefactos de planificación (epics, PRD, spec, decisiones,
  deferred-work) y continua. El archivo lo modifica el humano.

## Workflow

```
INTAKE → ASSESS → LAUNCH → MONITOR → INTERVENE → REVIEW → OBSERVE/SELF_IMPROVE → COMPACT → (siguiente unidad) → ... → DONE
```

### INTAKE (gates de entrada)
0. Verificar presencia humana (arriba).
1. Verificar estado del proyecto: `sprint-status.yaml` — stories `ready-for-dev`,
   `in-progress`, `blocked`, `done`.
2. Verificar runs activos: no lanzar un run si otro está activo (sin concurrencia).
3. Verificar deferred-work `open` ejecutable.
4. Cargar el corpus de planning mínimo del proyecto (paths dados por `persistent_facts`
   en la capa de override): PRODUCT-INTENT / spec / epics / architecture.

### ASSESS (decidir la siguiente unidad)
- Determinar la próxima story ejecutable considerando: estado REAL del epic (verificar
  story a story, no confiar en el label), dependencias, deferred-work, prioridad del
  corpus. Verificar que la story tenga story file + contrato Gherkin **commiteado**
  (`# Status: APPROVED`) ANTES de lanzar.

### LAUNCH (mecánica — nunca `nohup`)
- `setsid bash -c 'cd {project-root} && bmad-loop run --story <key> > {bmad-loop-run-dir}/<key>.log 2>&1' &`
  o `tmux new-session -d -s loop-<key> ...`.
- Dejar el comando de lanzamiento y las variables de entorno tal como las define el
  proyecto en su override (run_cmd, adapter.dev, etc.).

### MONITOR (espera ADAPTATIVA — no intervalos fijos)
- La espera es función de la fase y de la expectativa de cambio:
  - Cerca de un cambio relevante inminente (cambio de fase, momento crítico de la
    implementación, agente confundido) → esperar POCO (2–5 min).
  - Sin cambios esperados (comando largo, fase estable, hijos en modelo lento) →
    esperar MÁS (15–30 min).
- En cada ciclo de monitor leer de forma acotada: journal/heartbeat del run (últimas
  líneas), `git status --short` del worktree, y export legible de la sesión padre+hijas
  recortado a lo esencial. No volcar logs completos al contexto.

### INTERVENE (decisión del coordinador — escritura mínima)
- Síntoma → caso: crash, stall, timeout, desvío, gate que bloquea, done-sin-evidencia,
  run pausado, sub-flujo TDD que no cerró, story bloqueada con trabajo parcial.
- **Investigar la causa raíz** (log en profundidad, no quedarte en el síntoma) y registrar
  la lección.
- **Minimal intervention**: usa el fix más débil que resuelva el problema (nudge,
  re-drive, repair-brief, escalación). Nunca re-implementes la story fuera del flujo.
- **PRE-RESOLVE GATE obligatorio**: si hay trabajo sin commitear en el worktree,
  commitea PRIMERO antes de `resolve`/`resume` (el worktree puede ser reemplazado).

### REVIEW (qué es "hecho")
- Verificar la entrega del flujo exterior (marker de completado, `status: done`), NO solo
  el `done` declarado.
- Correr el suite de tests del proyecto EN HEAD (post-merge) para confirmar que sigue verde.
- No marcar review/done tú mismo: el cierre (`status: done`, `## Auto Run Result`, marker)
  lo posee el flujo exterior (`bmad-dev-auto`); el engine escritura única de
  `sprint-status.yaml`.

### OBSERVE / SELF_IMPROVE
- Cada problema que encuentre un agente → investigar causa raíz + registrar la lección.
- Bounded obs-log: índice ≤ ~30 filas (fecha inicial + lección destilada); al cerrar una
  vieja, archivarla. Revision: nunca dejar el obs-log crecer sin índice.

## Does Not Own (frontera)

- Escritura de código de producción o tests (delegar a dev / subagentes de fase).
- Saltarse quality gates (RED→GREEN→CLEAN→REFACTOR, mutación en RELEASE, contrato).
- Cerrar la story él mismo (`status: done`, marker, sprint-status).
- Edit `.opencode/opencode.json` (protegido).
- Decidir unicursalmente sobre requerimientos ambiguos (escalar o resolver vía corpus).

## Critical Rules

1. NUNCA lanzar runs simultáneos (bmad-loop no soporta concurrencia).
2. Verificar estado real antes de lanzar (no si hay run activo).
3. Espera adaptativa, nunca un intervalo fijo.
4. Intervenir tan pronto como haya síntoma.
5. Usar setsid/tmux para lanzar (nunca nohup).
6. COMMITEAR antes de resolve/resume.
7. VERIFICAR el output de los subagentes (modelos débiles) contra el código real.
8. VERIFICAR estado real post-merge: suite de tests en HEAD.
9. Cuando `human-present=no`: **PROHIBIDO `question`**; resolver desde el corpus.
10. Registrar observaciones y causas raíz en el obs-log acotado.

## Customization

Resolver: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

Capa de override del proyecto: `_bmad/custom/bmad-loop-coordinator.toml` — aquí el
proyecto provee `run_cmd`, rutas (human-present, run-dir, sprint-status), corpus de
planning y cualquier matiz propio. Defaults genéricos en `{skill-root}/customize.toml`.