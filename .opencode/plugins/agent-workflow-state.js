import { existsSync } from "node:fs"
import { buildWorkflowBreadcrumb, getActiveTask, readTaskJson, workflowRoot } from "./agent-workflow-lib.js"

export default async ({ directory }) => {
  return {
    "chat.message": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      if (input?.agent && String(input.agent).startsWith("workflow-")) return
      const taskId = getActiveTask(directory)
      const task = taskId ? readTaskJson(directory, taskId) : null
      if (!task || task.status === "done") return
      const breadcrumb = buildWorkflowBreadcrumb({ taskId, status: task?.status || "none" })
      if (!breadcrumb) return
      const parts = output?.parts || []
      const textPart = parts.find((part) => part.type === "text")
      if (textPart) textPart.text = `${breadcrumb}\n\n${textPart.text || ""}`
      else parts.unshift({ type: "text", text: breadcrumb })
    },
  }
}
