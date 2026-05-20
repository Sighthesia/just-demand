import { existsSync } from "node:fs"
import { getActiveTask, readTaskContext, workflowRoot } from "./agent-workflow-lib.js"

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
      const context = readTaskContext(directory, taskId, args.subagent_type)
      if (!context) return
      args.prompt = `Active task: ${taskId}\n\n# Injected Workflow Context\n\n${context}\n\n---\n\n# Requested Work\n\n${args.prompt || ""}`
    },
  }
}
