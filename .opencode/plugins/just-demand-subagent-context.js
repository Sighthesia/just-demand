import { existsSync } from "node:fs"
import {
  debugLog,
  enforceExecutionGate,
  getActiveTask,
  getMissingRequiredContextFiles,
  getLastSubagentDispatchTaskId,
  getRecoveredSubagentTaskId,
  getReminderState,
  getWorkflowSubagentName,
  appendDebugSessionTranscript,
  isDebugPromptFullEnabled,
  logPluginBootstrap,
  markSubagentUnavailablePending,
  recordLastSubagentDispatchTaskId,
  readTaskContext,
  readTaskJson,
  summarizeInjectedContextParts,
  writeDebugPromptDump,
  workflowRoot,
} from "./just-demand-lib.js"

const SUPPORTED = new Set(["just-demand-researcher", "just-demand-coder", "just-demand-tester", "just-demand-advisor"])
const WRITABLE_SUBAGENTS = new Set(["just-demand-coder", "just-demand-tester"])

// Markers to detect if prompt has already been injected with workflow context.
// Keep the legacy header to avoid duplicate injection across old prompts.
const INJECTION_MARKERS = ["# Just Demand Workflow", "# Injected Workflow Context"]

const argsKeys = (args) => args && typeof args === "object" ? Object.keys(args).sort() : []

export default async ({ directory }) => {
  logPluginBootstrap(directory || ".", "just-demand-subagent-context")
  return {
    "tool.execute.after": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      const toolName = String(input?.tool || "").toLowerCase()
      if (toolName !== "task") return

      const args = output?.args || input?.args
      const subagentName = getWorkflowSubagentName(args)
      if (!args || !SUPPORTED.has(subagentName)) return

      const taskId = getActiveTask(directory)
      if (!taskId) return

      const recoveredTaskId = getRecoveredSubagentTaskId(directory, taskId, subagentName, input, output)
      if (!recoveredTaskId) return

      recordLastSubagentDispatchTaskId(directory, taskId, subagentName, recoveredTaskId)
      debugLog("subagent.tool.after.record", { task_id: taskId, workflow_subagent: subagentName, resumed_task_id: recoveredTaskId }, directory)
    },
    "tool.execute.before": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) {
        debugLog("subagent.tool.before.skip", { reason: "missing_workflow_root" }, directory)
        return
      }
      const toolName = String(input?.tool || "").toLowerCase()
      const args = output?.args || input?.args
      enforceExecutionGate(directory, toolName, args, "subagent.gate")
      if (toolName !== "task") {
        debugLog("subagent.tool.before.skip", { reason: "not_task_tool", tool: toolName }, directory)
        return
      }
      const subagentName = getWorkflowSubagentName(args)
      debugLog("subagent.tool.before", { args_keys: argsKeys(args), workflow_subagent: subagentName }, directory)
      if (!args || !SUPPORTED.has(subagentName)) {
        debugLog("subagent.tool.before.skip", { reason: "unsupported_subagent", workflow_subagent: subagentName || null }, directory)
        return
      }

      // Skip if prompt already contains workflow context (duplicate injection protection)
      if (args.prompt && INJECTION_MARKERS.some((marker) => args.prompt.includes(marker))) {
        debugLog("subagent.tool.before.skip", { reason: "already_injected", workflow_subagent: subagentName }, directory)
        return
      }

      const taskId = getActiveTask(directory)
      if (!taskId) {
        debugLog("subagent.tool.before.skip", { reason: "no_active_task", workflow_subagent: subagentName }, directory)
        return
      }
      const reminderState = getReminderState(directory, input?.sessionID || "main")
      const resumedTaskId = reminderState.subagent_unavailable_pending
        ? getLastSubagentDispatchTaskId(directory, taskId, subagentName)
        : null
      if (!output.args && args) {
        output.args = args
      }
      if (resumedTaskId && !args.task_id) {
        output.args.task_id = resumedTaskId
        debugLog("subagent.tool.before.resume", { task_id: taskId, workflow_subagent: subagentName, resumed_task_id: resumedTaskId }, directory)
      }
      const missing = getMissingRequiredContextFiles(directory, taskId, subagentName)
      if (missing.length > 0) {
        markSubagentUnavailablePending(directory, input?.sessionID || "main")
        debugLog("subagent.tool.before.block", { reason: "missing_context", task_id: taskId, workflow_subagent: subagentName, missing }, directory)
        if (WRITABLE_SUBAGENTS.has(subagentName)) {
          throw new Error(
            `Blocked ${subagentName}: missing required task context files for active task ${taskId}: ${missing.join(", ")}`,
          )
        }
        args.prompt = `Active task: ${taskId}\n\n# BLOCKED\n\nMissing required task context files: ${missing.join(", ")}. Do not proceed until the main agent creates the required task context package files for this task.\n\n---\n\n# Requested Work\n\n${args.prompt || ""}`
        return
      }
      const context = readTaskContext(directory, taskId, subagentName)
      if (!context) {
        debugLog("subagent.tool.before.skip", { reason: "empty_context", task_id: taskId, workflow_subagent: subagentName }, directory)
        return
      }
      const requestedWork = args.prompt || ""
      args.prompt = `Active task: ${taskId}\n\n# Just Demand Workflow\n\n${context}\n\n---\n\n# Execution Rules\n\nComplete the requested work in this subagent.\nDo not call the Task tool.\nDo not dispatch another subagent.\n\n---\n\n# Requested Work\n\n${requestedWork}`
      const contextParts = summarizeInjectedContextParts(directory, taskId, subagentName)
      const injectLog = {
        task_id: taskId,
        workflow_subagent: subagentName,
        prompt_length: args.prompt.length,
        context_parts: contextParts,
      }
      if (isDebugPromptFullEnabled()) {
        injectLog.prompt_dump_path = writeDebugPromptDump(directory, {
          task_id: taskId,
          workflow_subagent: subagentName,
          prompt_length: args.prompt.length,
          context_parts: contextParts,
          requested_work: requestedWork,
          injected_context: context,
          prompt: args.prompt,
        })
        injectLog.transcript_path = appendDebugSessionTranscript(directory, {
          entry_type: "Subagent Prompt Injection",
          session_id: input?.sessionID || "main",
          task_id: taskId,
          source: "subagent-prompt-injection",
          workflow_subagent: subagentName,
          trigger_summary: [
            `just-demand subagent injection for ${subagentName}`,
            `active task ${taskId} context injected before Task dispatch`,
          ],
          requested_work: requestedWork,
          context_parts: contextParts,
          injected_context: context,
          prompt: args.prompt,
        })
      }
      debugLog("subagent.tool.before.inject", injectLog, directory)
    },
  }
}
