import { existsSync } from "node:fs"
import { getActiveTask, getMissingRequiredContextFiles, readTaskContext, workflowRoot } from "./just-demand-lib.js"

const SUPPORTED = new Set(["just-demand-research", "just-demand-implement", "just-demand-check", "just-demand-docs"])
const WRITABLE_SUBAGENTS = new Set(["just-demand-implement", "just-demand-check", "just-demand-docs"])

// Markers to detect if prompt has already been injected with workflow context.
// Keep the legacy header to avoid duplicate injection across old prompts.
const INJECTION_MARKERS = ["# Just Demand Workflow", "# Injected Workflow Context"]

export default async ({ directory }) => {
  return {
    "tool.execute.before": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      if (String(input?.tool || "").toLowerCase() !== "task") return
      const args = output?.args
      if (!args || !SUPPORTED.has(args.subagent_type)) return

      // Skip if prompt already contains workflow context (duplicate injection protection)
      if (args.prompt && INJECTION_MARKERS.some((marker) => args.prompt.includes(marker))) {
        return
      }

      const taskId = getActiveTask(directory)
      if (!taskId) return
      const missing = getMissingRequiredContextFiles(directory, taskId, args.subagent_type)
      if (missing.length > 0) {
        if (WRITABLE_SUBAGENTS.has(args.subagent_type)) {
          throw new Error(
            `Blocked ${args.subagent_type}: missing required task context files for active task ${taskId}: ${missing.join(", ")}`,
          )
        }
        args.prompt = `Active task: ${taskId}\n\n# BLOCKED\n\nMissing required task context files: ${missing.join(", ")}. Do not proceed until the main agent creates the required task context package files for this task.\n\n---\n\n# Requested Work\n\n${args.prompt || ""}`
        return
      }
      const context = readTaskContext(directory, taskId, args.subagent_type)
      if (!context) return
      args.prompt = `Active task: ${taskId}\n\n# Just Demand Workflow\n\n${context}\n\n---\n\n# Execution Rules\n\nComplete the requested work in this subagent.\nDo not call the Task tool.\nDo not dispatch another subagent.\n\n---\n\n# Requested Work\n\n${args.prompt || ""}`
    },
  }
}
