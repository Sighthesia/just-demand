import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"

export const workflowRoot = (directory) => join(directory, ".agent-workflow")

export const readJson = (path) => {
  try {
    return JSON.parse(readFileSync(path, "utf8"))
  } catch {
    return null
  }
}

export const readTextIfExists = (path) => existsSync(path) ? readFileSync(path, "utf8") : ""

export const getActiveTask = (directory) => {
  const statePath = join(workflowRoot(directory), "workspace", "state.json")
  if (!existsSync(statePath)) return null
  const state = readJson(statePath)
  if (!state) return null
  return state.current_task_id || null
}

export const readTaskJson = (directory, taskId) => {
  const path = join(workflowRoot(directory), "tasks", "active", taskId, "task.json")
  return existsSync(path) ? readJson(path) : null
}

export const buildWorkflowBreadcrumb = ({ taskId, status }) => {
  if (!taskId) {
    return "<workflow-state>\nNo formal work item is active. Clarify the user's need before suggesting a formal work item.\n</workflow-state>"
  }
  return `<workflow-state>\nFormal work item: ${taskId}\nStatus: ${status}\nNext: keep the user-facing conversation focused on goals, expected behavior, tradeoffs, and approval.\n</workflow-state>`
}

export const readTaskContext = (directory, taskId, agentName) => {
  const taskDir = join(workflowRoot(directory), "tasks", "active", taskId)
  const workspaceDir = join(workflowRoot(directory), "workspace")
  const parts = []

  const context = readTextIfExists(join(taskDir, "context.md"))
  if (context) parts.push(context)

  const decisions = readTextIfExists(join(taskDir, "decisions.md"))
  if (decisions) parts.push(decisions)

  switch (agentName) {
    case "workflow-implement": {
      const implement = readTextIfExists(join(taskDir, "implement.md"))
      if (implement) parts.push(implement)
      break
    }
    case "workflow-check": {
      const verify = readTextIfExists(join(taskDir, "verify.md"))
      if (verify) parts.push(verify)
      break
    }
    case "workflow-research": {
      const facts = readTextIfExists(join(workspaceDir, "facts.md"))
      if (facts) parts.push(`# Workspace Facts\n\n${facts}`)
      const researchDir = join(taskDir, "research")
      if (existsSync(researchDir)) {
        parts.push(`Research output directory: ${researchDir}`)
      }
      break
    }
    case "workflow-docs": {
      const wsDecisions = readTextIfExists(join(workspaceDir, "decisions.md"))
      if (wsDecisions) parts.push(`# Workspace Decisions\n\n${wsDecisions}`)
      const deferred = readTextIfExists(join(workspaceDir, "deferred_options.md"))
      if (deferred) parts.push(`# Deferred Options\n\n${deferred}`)
      break
    }
  }

  return parts.join("\n\n---\n\n")
}
