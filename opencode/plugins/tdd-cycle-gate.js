import { spawnSync } from "node:child_process";
import { isAbsolute, join } from "node:path";
import { existsSync, readFileSync } from "node:fs";

const PATCH_PATH_RE = /^\*\*\* (?:Add|Update|Delete) File: (.+)$/gm;

function parsePatchInput(patchText) {
  if (typeof patchText !== "string") return null;
  const paths = [...patchText.matchAll(PATCH_PATH_RE)].map((match) => match[1]);
  if (paths.length === 0) return null;
  return {
    toolName: "MultiEdit",
    toolInput: {
      edits: paths.map((filePath) => ({ file_path: filePath, new_string: patchText })),
    },
  };
}

function mapToolInput(tool, args) {
  if (tool === "apply_patch") return parsePatchInput(args.patchText);
  if (tool === "bash") {
    return { toolName: "Bash", toolInput: { command: args.command ?? "" } };
  }
  if (tool === "edit" || tool === "write") {
    return {
      toolName: tool === "edit" ? "Edit" : "Write",
      toolInput: {
        file_path: args.filePath ?? args.file_path,
        new_string: args.newString ?? args.new_string,
        content: args.content,
      },
    };
  }
  if (tool === "skill" || tool === "invoke_skill") {
    const name = args.name ?? args.skill_name ?? "";
    return { toolName: "Skill", toolInput: { skill_name: name } };
  }
  if (tool === "task") {
    // Phase 2 model-routing: Task agents route to Python tool_name="Task".
    // Extract ONLY subagent_type and prompt — no arbitrary fields.
    const subagent = args.subagent_type ?? args.agent ?? args.name ?? "";
    return { toolName: "Task", toolInput: { subagent_type: subagent, prompt: args.prompt ?? "" } };
  }
  if (tool === "multi_edit" || tool === "multiEdit" || tool === "multiedit") {
    // Support shapes: args (array), args.args (array fallback), args.edits (object shape).
    // If args is itself an array → use it directly.
    // If args.args is an array → use it.
    // If args.edits is an array → use it.
    // Otherwise → empty.
    let edits = [];
    if (Array.isArray(args)) {
      edits = args;
    } else if (args && typeof args === "object") {
      if (Array.isArray(args.args)) {
        edits = args.args;
      } else if (Array.isArray(args.edits)) {
        edits = args.edits;
      }
    }
    return { toolName: "MultiEdit", toolInput: { edits } };
  }
  return null;
}

function shouldDenyGateResult(result, loopMode) {
  if (result.status === 2) return true;
  return Boolean(
    loopMode && (result.error || result.signal || result.status !== 0),
  );
}

const questionTools = new Set(["question", "prompt", "confirm", "ask"]);

function resolveHumanPresentPath(directory) {
  const cfg = process.env.BMAD_TDD_HUMAN_PRESENT_PATH;
  return cfg
    ? (isAbsolute(cfg) ? cfg : join(directory, cfg))
    : join(directory, ".bmad-loop", "human-present");
}

function enforceUnattendedQuestionGate(directory) {
  // Mechanical question gate driven by the human-present FLAG, with the
  // loop-mode env as a fallback for sessions the engine exported the var to
  // (the dev engine sessions). Deny the interactive question/prompt tool when:
  //   (a) the flag file exists and says anything other than "yes", OR
  //   (b) the flag file is missing AND BMAD_LOOP_MODE=1 (loop without a human
  //       presence marker is unattended by definition).
  // A missing flag OUTSIDE loop mode is an interactive session → allow.
  const flag = resolveHumanPresentPath(directory);
  let hasFlag = false;
  let content = "";
  try {
    hasFlag = existsSync(flag);
    if (hasFlag) content = readFileSync(flag, { encoding: "utf8" }).trim().toLowerCase();
  } catch {
    hasFlag = false;
  }
  const loopMode = process.env.BMAD_LOOP_MODE === "1";
  const unattended = hasFlag ? content !== "yes" : loopMode;
  if (unattended) {
    throw new Error(
      "🚫 Unattended (human-present != yes): the interactive `question` tool is " +
        "DENIED mechanically (no human to answer); resolve from the planning corpus.",
    );
  }
}

function runPythonGate(directory, event, mapped, toolResponse = null, sessionId = "") {
  // Gate path is configurable via BMAD_TDD_GATE_PATH (absolute or repo-relative).
  // Default: project-relative "hooks/tdd_cycle_gate.py".
  const configured = process.env.BMAD_TDD_GATE_PATH;
  const gate = configured
    ? (isAbsolute(configured) ? configured : join(directory, configured))
    : join(directory, "hooks", "tdd_cycle_gate.py");
  const payload = {
    hook_event_name: event,
    tool_name: mapped.toolName,
    tool_input: mapped.toolInput,
  };
  if (typeof sessionId === "string" && sessionId) payload.session_id = sessionId;
  if (event === "PostToolUse") payload.tool_response = toolResponse;
  const result = spawnSync("python3", [gate], {
    cwd: directory,
    encoding: "utf8",
    input: JSON.stringify(payload),
    timeout: 5000,
  });
  const loopMode = process.env.BMAD_LOOP_MODE === "1";
  if (shouldDenyGateResult(result, loopMode)) {
    const detail = result.stderr || result.stdout || result.error?.message || "";
    throw new Error(detail.trim() || "TDD gate unavailable; failed closed in loop mode");
  }
  return {
    status: result.status,
    signal: result.signal,
    stderr: result.stderr,
  };
}

const createTddCycleGate = async ({ directory }) => ({
  async "tool.execute.before"(input, output) {
    // Unattended question gate (mechanical, not prose): in loop mode without a
    // human present, the interactive question/prompt tool is denied outright.
    if (questionTools.has(input.tool)) {
      enforceUnattendedQuestionGate(directory);
      return;
    }
    const mapped = mapToolInput(input.tool, output.args);
    if (mapped) runPythonGate(directory, "PreToolUse", mapped, null, input.sessionID);
  },

  async "tool.execute.after"(input, output) {
    const mapped = mapToolInput(input.tool, input.args);
    if (mapped) {
      runPythonGate(directory, "PostToolUse", mapped, {
        title: output.title,
        output: output.output,
        metadata: output.metadata,
      }, input.sessionID);
    }
  },
});

export const TddCycleGate = Object.assign(createTddCycleGate, {
  mapToolInput,
  parsePatchInput,
  shouldDenyGateResult,
});
