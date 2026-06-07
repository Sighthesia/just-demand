import { existsSync } from "node:fs"
import {
  debugLog,
  getActiveTask,
  getMissingRequiredContextFiles,
  getWorkflowSubagentName,
  markSubagentUnavailablePending,
  readTaskContext,
  readTaskJson,
  workflowRoot,
} from "./just-demand-lib.js"

const SUPPORTED = new Set(["just-demand-research", "just-demand-implement", "just-demand-check", "just-demand-docs"])
const WRITABLE_SUBAGENTS = new Set(["just-demand-implement", "just-demand-check", "just-demand-docs"])

// Markers to detect if prompt has already been injected with workflow context.
// Keep the legacy header to avoid duplicate injection across old prompts.
const INJECTION_MARKERS = ["# Just Demand Workflow", "# Injected Workflow Context"]

const argsKeys = (args) => args && typeof args === "object" ? Object.keys(args).sort() : []

export default async ({ directory }) => {
  return {
    "tool.execute.before": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) {
        debugLog("subagent.tool.before.skip", { reason: "missing_workflow_root" })
        return
      }
      const toolName = String(input?.tool || "").toLowerCase()
      if (toolName !== "task") {
        debugLog("subagent.tool.before.skip", { reason: "not_task_tool", tool: toolName })
        return
      }
      const args = output?.args
      const subagentName = getWorkflowSubagentName(args)
      debugLog("subagent.tool.before", { args_keys: argsKeys(args), workflow_subagent: subagentName })
      if (!args || !SUPPORTED.has(subagentName)) {
        debugLog("subagent.tool.before.skip", { reason: "unsupported_subagent", workflow_subagent: subagentName || null })
        return
      }

      // Skip if prompt already contains workflow context (duplicate injection protection)
      if (args.prompt && INJECTION_MARKERS.some((marker) => args.prompt.includes(marker))) {
        debugLog("subagent.tool.before.skip", { reason: "already_injected", workflow_subagent: subagentName })
        return
      }

      const taskId = getActiveTask(directory)
      if (!taskId) {
        debugLog("subagent.tool.before.skip", { reason: "no_active_task", workflow_subagent: subagentName })
        return
      }
      const missing = getMissingRequiredContextFiles(directory, taskId, subagentName)
      if (missing.length > 0) {
        markSubagentUnavailablePending(directory, input?.sessionID || "main")
        debugLog("subagent.tool.before.block", { reason: "missing_context", task_id: taskId, workflow_subagent: subagentName, missing })
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
        debugLog("subagent.tool.before.skip", { reason: "empty_context", task_id: taskId, workflow_subagent: subagentName })
        return
      }
      args.prompt = `Active task: ${taskId}\n\n# Just Demand Workflow\n\n${context}\n\n---\n\n# Execution Rules\n\nComplete the requested work in this subagent.\nDo not call the Task tool.\nDo not dispatch another subagent.\n\n---\n\n# Requested Work\n\n${args.prompt || ""}`
      debugLog("subagent.tool.before.inject", { task_id: taskId, workflow_subagent: subagentName })
    },
  }
}
