import { existsSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"

const REMINDER_STATE = new Map()

const defaultReminderState = () => ({
  same_topic_turns: 0,
  last_reminder_type: null,
  subagent_unavailable_pending: false,
})

const reminderStateKey = (directory, sessionID) => `${workflowRoot(directory)}::${sessionID || "main"}`

export const workflowRoot = (directory) => join(directory, ".just-demand")

export const readJson = (path) => {
  try {
    return JSON.parse(readFileSync(path, "utf8"))
  } catch {
    return null
  }
}

export const readTextIfExists = (path) => existsSync(path) ? readFileSync(path, "utf8") : ""

export const getReminderState = (directory, sessionID) => {
  const key = reminderStateKey(directory, sessionID)
  if (!REMINDER_STATE.has(key)) {
    REMINDER_STATE.set(key, defaultReminderState())
  }
  return REMINDER_STATE.get(key)
}

export const markSubagentUnavailablePending = (directory, sessionID) => {
  const state = getReminderState(directory, sessionID)
  state.subagent_unavailable_pending = true
  state.last_reminder_type = null
  return state
}

export const clearSubagentUnavailablePending = (directory, sessionID) => {
  const state = getReminderState(directory, sessionID)
  state.subagent_unavailable_pending = false
  return state
}

export const updateReminderState = (directory, sessionID, updater) => {
  const state = getReminderState(directory, sessionID)
  updater(state)
  return state
}

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
  const statePath = join(workflowRoot(directory), "state", "state.json")
  if (!existsSync(statePath)) return null
  const state = readJson(statePath)
  if (!state) return null
  return state.current_task_id || null
}

export const readTaskJson = (directory, taskId) => {
  const path = join(workflowRoot(directory), "state", "active", taskId, "task.json")
  return existsSync(path) ? readJson(path) : null
}

export const listUnfinishedTasks = (directory) => {
  const activeDir = join(workflowRoot(directory), "state", "active")
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
  const taskDir = join(workflowRoot(directory), "state", "active", taskId)
  const knowledgeDir = join(workflowRoot(directory), "knowledge")
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
      const facts = readTextIfExists(join(knowledgeDir, "memory.md"))
      if (facts) parts.push(`# Workspace Facts\n\n${facts}`)
      const researchDir = join(taskDir, "research")
      if (existsSync(researchDir)) {
        parts.push("Research outputs: write any artifacts under this task's local research/ directory.")
      }
      break
    }
    case "just-demand-docs": {
      const wsDecisions = readTextIfExists(join(knowledgeDir, "memory.md"))
      if (wsDecisions) parts.push(`# Workspace Decisions\n\n${wsDecisions}`)
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
  const taskDir = join(workflowRoot(directory), "state", "active", taskId)
  return getRequiredContextFiles(agentName).filter((file) => !existsSync(join(taskDir, file)))
}
