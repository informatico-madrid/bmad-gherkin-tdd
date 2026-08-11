import { spawnSync } from "node:child_process";
import { join } from "node:path";

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

function runPythonGate(directory, event, mapped, toolResponse = null) {
  // Gate path is configurable via BMAD_TDD_GATE_PATH (absolute or repo-relative).
  // Default: project-relative "hooks/tdd_cycle_gate.py".
  const configured = process.env.BMAD_TDD_GATE_PATH;
  const gate = configured
    ? join(directory, configured)
    : join(directory, "hooks", "tdd_cycle_gate.py");
  const payload = {
    hook_event_name: event,
    tool_name: mapped.toolName,
    tool_input: mapped.toolInput,
  };
  if (event === "PostToolUse") payload.tool_response = toolResponse;
  const result = spawnSync("python3", [gate], {
    cwd: directory,
    encoding: "utf8",
    input: JSON.stringify(payload),
    timeout: 5000,
  });
  if (result.status === 2) {
    throw new Error((result.stderr || result.stdout).trim() || "TDD gate denied the tool call");
  }
  return {
    status: result.status,
    signal: result.signal,
    stderr: result.stderr,
  };
}

const createTddCycleGate = async ({ directory }) => ({
  async "tool.execute.before"(input, output) {
    const mapped = mapToolInput(input.tool, output.args);
    if (mapped) runPythonGate(directory, "PreToolUse", mapped);
  },

  async "tool.execute.after"(input, output) {
    const mapped = mapToolInput(input.tool, input.args);
    if (mapped) runPythonGate(directory, "PostToolUse", mapped, output.output);
  },
});

export const TddCycleGate = Object.assign(createTddCycleGate, {
  mapToolInput,
  parsePatchInput,
});
