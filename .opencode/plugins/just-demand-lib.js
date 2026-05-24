import { existsSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"

export const workflowRoot = (directory) => join(directory, ".just-demand")

export const readJson = (path) => {
  try {
    return JSON.parse(readFileSync(path, "utf8"))
  } catch {
    return null
  }
}

export const readTextIfExists = (path) => existsSync(path) ? readFileSync(path, "utf8") : ""

const renderClarificationContext = (task) => {
  const clarification = task?.clarification || {}
  const entries = [
    ["Current Understanding", clarification.current_understanding],
    ["Expected Behavior", clarification.expected_behavior],
    ["Actual Behavior", clarification.actual_behavior],
    ["Reproduction", clarification.reproduction],
    ["Scope", clarification.scope],
    ["Final Expected Effect", clarification.final_expected_effect],
    ["Approach Options", clarification.approach_options],
    ["Chosen Approach", clarification.chosen_approach],
    ["Final Implementation Plan", clarification.final_implementation_plan],
    ["Validation", clarification.validation],
    ["Approval", clarification.approval],
  ].filter(([, value]) => typeof value === "string" && value.trim())

  if (entries.length === 0) return ""

  return [
    "# Clarification",
    "",
    ...entries.flatMap(([label, value]) => [`## ${label}`, value.trim(), ""]),
  ].join("\n").trimEnd()
}

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

export const listUnfinishedTasks = (directory) => {
  const activeDir = join(workflowRoot(directory), "tasks", "active")
  if (!existsSync(activeDir)) return []
  try {
    const entries = readdirSync(activeDir, { withFileTypes: true })
    const tasks = []
    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      const taskPath = join(activeDir, entry.name, "task.json")
      const task = readJson(taskPath)
      if (!task || task.status === "done") continue
      tasks.push({
        id: task.id || entry.name,
        title: task.title || "",
        status: task.status || "unknown",
        current_step: task.current_step || null,
        path: join(activeDir, entry.name),
      })
    }
    return tasks
  } catch {
    return []
  }
}



export const readTaskContext = (directory, taskId, agentName) => {
  const taskDir = join(workflowRoot(directory), "tasks", "active", taskId)
  const workspaceDir = join(workflowRoot(directory), "workspace")
  const parts = []
  const task = readTaskJson(directory, taskId)

  const context = readTextIfExists(join(taskDir, "context.md"))
  if (context) parts.push(context)

  if (["just-demand-implement", "just-demand-check"].includes(agentName)) {
    const clarificationContext = renderClarificationContext(task)
    if (clarificationContext) parts.push(clarificationContext)
  }

  const decisions = readTextIfExists(join(taskDir, "decisions.md"))
  if (decisions) parts.push(decisions)

  const openQuestions = readTextIfExists(join(taskDir, "open_questions.md"))
  const clarificationQuestions = task?.clarification?.non_blocking_questions || []
  const hasRemainingOpenQuestions = /\S/.test(openQuestions.replace(/^# Open Questions\s*/i, "")) || clarificationQuestions.length > 0
  const renderedOpenQuestions = /\S/.test(openQuestions.replace(/^# Open Questions\s*/i, ""))
    ? openQuestions
    : `# Open Questions\n\n## Remaining Open Questions\n\n${clarificationQuestions.map((question) => `- ${question}`).join("\n")}\n`
  if (hasRemainingOpenQuestions && ["just-demand-implement", "just-demand-check"].includes(agentName)) {
    parts.push(renderedOpenQuestions)
  }

  switch (agentName) {
    case "just-demand-implement": {
      const implement = readTextIfExists(join(taskDir, "implement.md"))
      if (implement) parts.push(implement)
      break
    }
    case "just-demand-check": {
      const verify = readTextIfExists(join(taskDir, "verify.md"))
      if (verify) parts.push(verify)
      break
    }
    case "just-demand-research": {
      const facts = readTextIfExists(join(workspaceDir, "facts.md"))
      if (facts) parts.push(`# Workspace Facts\n\n${facts}`)
      const researchDir = join(taskDir, "research")
      if (existsSync(researchDir)) {
        parts.push("Research outputs: write any artifacts under this task's local research/ directory.")
      }
      break
    }
    case "just-demand-docs": {
      const wsDecisions = readTextIfExists(join(workspaceDir, "decisions.md"))
      if (wsDecisions) parts.push(`# Workspace Decisions\n\n${wsDecisions}`)
      const deferred = readTextIfExists(join(workspaceDir, "deferred_options.md"))
      if (deferred) parts.push(`# Deferred Options\n\n${deferred}`)
      break
    }
  }

  return parts.join("\n\n---\n\n")
}

export const getRequiredContextFiles = (agentName) => {
  switch (agentName) {
    case "just-demand-implement":
      return ["context.md", "implement.md"]
    case "just-demand-check":
      return ["context.md", "verify.md"]
    case "just-demand-docs":
      return ["context.md", "decisions.md"]
    case "just-demand-research":
      return ["context.md"]
    default:
      return []
  }
}

export const getMissingRequiredContextFiles = (directory, taskId, agentName) => {
  const taskDir = join(workflowRoot(directory), "tasks", "active", taskId)
  return getRequiredContextFiles(agentName).filter((file) => !existsSync(join(taskDir, file)))
}
