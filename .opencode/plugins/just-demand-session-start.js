import {
  appendDebugSessionAudit,
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
  "Use just-demand subagents as selective accelerators, not mandatory sinks.",
  "Dispatch only when all six eligibility gates and all three net-benefit questions pass.",
  "Any gate failure or uncertain benefit → the main agent executes, even for long-context or multi-file work.",
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

      const workflowDirectory = directory || input?.directory || input?.root || input?.cwd || "."
      const sessionID = typeof input?.sessionID === "string" && input.sessionID ? input.sessionID : "main"

      if (isDebugPromptFullEnabled()) {
        const activeTaskId = getActiveTask(workflowDirectory)
        const systemText = Array.isArray(output.system) ? output.system.join("\n\n") : ""
        const dumpPath = writeDebugChatTurnDump(workflowDirectory, {
          session_id: sessionID,
          task_id: activeTaskId || "",
          phase: "system-transform",
          action: "inject",
          reason_code: "session_start_fallback",
          original_text: systemText,
          after_controller_text: systemText,
          final_text: systemText,
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
          final_text: systemText,
        })
        debugLog("session-start.dump", {
          session_id: sessionID,
          active_task_id: activeTaskId || null,
          dump_path: dumpPath,
          transcript_path: transcriptPath,
        }, workflowDirectory)
      }

      // Per-session injection audit (JUST_DEMAND_DEBUG, independent of PROMPT_FULL)
      appendDebugSessionAudit(workflowDirectory, sessionID, "visible", {
        source: "session-start",
        task_id: getActiveTask(workflowDirectory) || "",
        status: "applied",
        reason: "session_start_fallback",
        content: Array.isArray(output.system) ? output.system.filter((s) => !s.includes("<JUST_DEMAND_")).join("\n\n") : "(empty)",
      })
      appendDebugSessionAudit(workflowDirectory, sessionID, "complete", {
        source: "session-start",
        task_id: getActiveTask(workflowDirectory) || "",
        status: "applied",
        reason: "session_start_fallback",
        content: Array.isArray(output.system) ? output.system.join("\n\n") : "(empty)",
      })
    },
  }
}
