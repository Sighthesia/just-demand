import { existsSync, readdirSync, readFileSync } from "node:fs"
import { join } from "node:path"

const REMINDER_STATE = new Map()

const WORKFLOW_SUBAGENT_PREFIX = "just-demand-"
const COMPLETION_CLAIM_PATTERNS = [
  /\b(done|finished|complete(?:d)?|implemented|shipped|resolved|wrapped up)\b/i,
  /\b(all set|good to go|ready to close|ready to ship|that'?s it|we'?re done)\b/i,
  /\b(should be good|looks good|nothing else to do|no further changes)\b/i,
  /\b(in a good place|close this out|wrap this up)\b/i,
  /(?:已经)?(?:做完了?|完成了?)/,
]

const EXECUTION_CANDIDATE_PATTERNS = [
  /\b(i|we)\s+(am|'m|are|will|can|should|need to|need)\s+(implement|build|add|remove|refactor|update|fix|debug|investigate|trace|analy[sz]e|design|rework|extend|patch|change)\b/i,
  /\b(i|we)\s+(should|will|can|need to)\s+(implement|build|add|remove|refactor|update|fix|debug|investigate|trace|analy[sz]e|design|rework|extend|patch|change)\b/i,
  /\b(i|we)\s+(implemented|built|added|removed|refactored|updated|fixed|debugged|investigated|traced|analy[sz]ed|designed|reworked|extended|patched|changed)\b/i,
  /\b(i(?:'ll)?|we)\s+just\s+finish(?:\s+this)?\s+in\s+the\s+main\s+session\b/i,
  /直接在主会话里(?:实现|修复|调试|处理|修改)/,
]

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

export const hasAssignedWorkflowSubagents = (task) => {
  const subagents = task?.assigned_subagents
  return Array.isArray(subagents) && subagents.some((subagent) => typeof subagent === "string" && subagent.startsWith(WORKFLOW_SUBAGENT_PREFIX))
}

export const textLooksLikeCompletionClaim = (text) => {
  const value = String(text || "").trim()
  if (!value) return false
  return COMPLETION_CLAIM_PATTERNS.some((pattern) => pattern.test(value))
}

export const taskLooksLikeLongContextExecutionCandidate = (task, text) => {
  if (!task || task.status === "done") return false
  if (hasAssignedWorkflowSubagents(task)) return false

  const currentStep = String(task.current_step || "").toLowerCase()
  const status = String(task.status || "").toLowerCase()
  const body = String(text || "")
  const hasTaskSignal = EXECUTION_CANDIDATE_PATTERNS.some((pattern) => pattern.test(body))
  const taskSignalsExecution = ["execut", "implement", "verify", "changes_requested"].some((fragment) => currentStep.includes(fragment) || status.includes(fragment))

  return hasTaskSignal && taskSignalsExecution
}

export const taskNeedsVerificationCloseout = (task) => {
  if (!task) return false
  return String(task.verification_status || "").toLowerCase() !== "passed"
}

export const taskNeedsCheckpointFollowUp = (task) => {
  if (!task) return false
  if (String(task.verification_status || "").toLowerCase() !== "passed") return false
  return !(task.checkpoint_commit && task.checkpoint_commit.created)
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
