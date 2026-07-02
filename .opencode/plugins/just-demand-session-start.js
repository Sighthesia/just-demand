import {
  appendDebugSessionTranscript,
  debugLog,
  formatWorkflowStateLines,
  getActiveTask,
  getExecutionGateState,
  isDebugPromptFullEnabled,
  logPluginBootstrap,
  readTaskJson,
  writeDebugChatTurnDump,
} from "./just-demand-lib.js"

const SESSION_REMINDER = [
  "<JUST_DEMAND_REMINDER>",
  "Load using-just-demand first for repo workflow turns.",
  "Use socratic-clarification second for any request, bug, correction, or mismatch before intake.",
  "Use just-demand subagents proactively for long-context work.",
  "Long-context work means broad code reading, 3+ files, multi-step research/debugging, or extended verification.",
  "If a needed subagent is unavailable, ask whether to retry now or skip one turn; that skip applies only to the current turn.",
  "Subagent interruptions are often caused by model provider or network errors; retry can resume the prior session when available.",
  "</JUST_DEMAND_REMINDER>",
].join("\n")

const WORKFLOW_STATE_BLOCK_MARKER = "<JUST_DEMAND_WORKFLOW_STATE>"

const buildWorkflowStateSystemBlock = (directory) => {
  const activeTaskId = getActiveTask(directory)
  const activeTask = activeTaskId ? (readTaskJson(directory, activeTaskId) || { id: activeTaskId }) : null
  const gateState = getExecutionGateState(directory)
  return [
    WORKFLOW_STATE_BLOCK_MARKER,
    formatWorkflowStateLines(activeTaskId, activeTask, gateState),
    "</JUST_DEMAND_WORKFLOW_STATE>",
  ].join("\n")
}

export default async ({ directory } = {}) => {
  logPluginBootstrap(directory || ".", "just-demand-session-start")
  return {
    "experimental.chat.system.transform": async (input, output) => {
      if (!output || !Array.isArray(output.system)) return
      if (output.system.some((segment) => typeof segment === "string" && segment.includes("<JUST_DEMAND_REMINDER>"))) {
        if (!output.system.some((segment) => typeof segment === "string" && segment.includes(WORKFLOW_STATE_BLOCK_MARKER))) {
          output.system.push(buildWorkflowStateSystemBlock(directory || input?.directory || input?.root || input?.cwd || "."))
        }
      } else {
        output.system.push(SESSION_REMINDER)
        output.system.push(buildWorkflowStateSystemBlock(directory || input?.directory || input?.root || input?.cwd || "."))
      }

      if (isDebugPromptFullEnabled()) {
        const workflowDirectory = directory || input?.directory || input?.root || input?.cwd || "."
        const sessionID = typeof input?.sessionID === "string" && input.sessionID ? input.sessionID : "main"
        const activeTaskId = getActiveTask(workflowDirectory)
        const dumpPath = writeDebugChatTurnDump(workflowDirectory, {
          session_id: sessionID,
          task_id: activeTaskId || "",
          phase: "system-transform",
          action: "inject",
          reason_code: "session_start_fallback",
          original_text: Array.isArray(output.system) ? output.system.join("\n\n") : "",
          after_controller_text: Array.isArray(output.system) ? output.system.join("\n\n") : "",
          final_text: Array.isArray(output.system) ? output.system.join("\n\n") : "",
        })
        const transcriptPath = appendDebugSessionTranscript(workflowDirectory, {
          entry_type: "Main Session System Prompt",
          session_id: sessionID,
          task_id: activeTaskId || "",
          source: "main-session-system-layer",
          phase: "system-transform",
          action: "inject",
          reason_code: "session_start_fallback",
          trigger_summary: [
            "just-demand session-start fallback injected reminder and workflow-state system block",
            `active task at transform time: ${activeTaskId || "(none)"}`,
          ],
          final_text: Array.isArray(output.system) ? output.system.join("\n\n") : "",
        })
        debugLog("session-start.dump", {
          session_id: sessionID,
          active_task_id: activeTaskId || null,
          dump_path: dumpPath,
          transcript_path: transcriptPath,
        }, workflowDirectory)
      }
    },
  }
}
