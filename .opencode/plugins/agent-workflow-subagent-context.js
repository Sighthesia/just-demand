import { existsSync } from "node:fs"
import { getActiveTask, getMissingRequiredContextFiles, readTaskContext, workflowRoot } from "./agent-workflow-lib.js"

const SUPPORTED = new Set(["workflow-research", "workflow-implement", "workflow-check", "workflow-docs"])

export default async ({ directory }) => {
  return {
    "tool.execute.before": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      if (String(input?.tool || "").toLowerCase() !== "task") return
      const args = output?.args
      if (!args || !SUPPORTED.has(args.subagent_type)) return
      const taskId = getActiveTask(directory)
      if (!taskId) return
      const missing = getMissingRequiredContextFiles(directory, taskId, args.subagent_type)
      if (missing.length > 0) {
        args.prompt = `Active task: ${taskId}\n\n# BLOCKED\n\nMissing required task context files: ${missing.join(", ")}. Do not implement or modify code until the main agent creates the required task context package files for this task.\n\n---\n\n# Requested Work\n\n${args.prompt || ""}`
        return
      }
      const context = readTaskContext(directory, taskId, args.subagent_type)
      if (!context) return
      args.prompt = `Active task: ${taskId}\n\n# Injected Workflow Context\n\n${context}\n\n---\n\n# Execution Rules\n\nComplete the requested work in this subagent.\nDo not call the Task tool.\nDo not dispatch another subagent.\n\n---\n\n# Requested Work\n\n${args.prompt || ""}`
    },
  }
}
