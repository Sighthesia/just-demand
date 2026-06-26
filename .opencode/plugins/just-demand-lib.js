import { execFileSync } from "node:child_process"
import { appendFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { join, resolve } from "node:path"

const REMINDER_STATE = new Map()
const PLUGIN_DIR = resolve(fileURLToPath(new URL(".", import.meta.url)))
const REPO_ROOT = resolve(PLUGIN_DIR, "..", "..")
const JUST_DEMAND_CLI = join(REPO_ROOT, "just-demand")

const WORKFLOW_SUBAGENT_PREFIX = "just-demand-"
const WORKFLOW_SUBAGENTS = new Set(["just-demand-researcher", "just-demand-coder", "just-demand-tester", "just-demand-advisor"])
const EXECUTION_GATED_SUBAGENTS = new Set(["just-demand-coder", "just-demand-tester"])
const LAST_SUBAGENT_DISPATCH_FILE = "last_subagent_dispatch.json"
const DEBUG_ENV_VALUES = new Set(["1", "true", "yes", "on"])
const DESIGN_OR_IMPLEMENTATION_TASK_TYPES = new Set([
  "design",
  "implementation",
  "feature",
  "feat",
  "refactor",
  "architecture",
])
const BUG_OR_MISMATCH_TASK_TYPES = new Set(["bug", "bugfix", "fix", "incident"])
// ---------------------------------------------------------------------------
// Risk-shaped contract registry (mirrors workflow_core.py CONTRACT_REGISTRY)
// ---------------------------------------------------------------------------
const CONTRACT_SIGNAL_PATTERNS = {
  visible_effect: [
    // English keywords: \b word boundaries work fine
    /\b(ui|ux|animation|animated|animate|motion|reveal|stagger|fade|slide)\b/i,
    // CJK keywords: \b is unreliable between CJK chars, so omit it
    /(动效|动画|淡入|淡出|展开|收起|错峰|闪烁|抖动|过渡|首帧|打断|结束状态)/,
  ],
  ordered_flow: [
    /\b(sequential|strict\s+order|ordered\s+sequence|ordered\s+flow|step\s+by\s+step|ordered|must\s+complete|before\s+proceeding|dependency\s+chain)\b/i,
    /(顺序|串行|依赖|先后|步骤|前置|条件|串行执行|按顺序)/,
  ],
  safety_boundary: [
    /\b(safety|destructive|irreversible|irreversibl|data\s+loss|rollback|revert|permission|authorization|auth[sz]|权限)\b/i,
    /(安全|破坏性|不可逆|数据丢失|回滚|恢复|授权)/,
  ],
  observability: [
    /\b(logging|monitoring|observability|telemetry|tracing|trace|metric|metrics|instrumentation|dashboard|alert|告警)\b/i,
    /(日志|监控|可观测|指标|链路|遥测|看板)/,
  ],
}

const CONTRACT_REGISTRY = Object.freeze([
  {
    name: "visible_effect",
    label: "Visible Effect",
    gate_level: "hard",
    signal_keys: ["visible_effect"],
    legacy_flag: "needs_ui_visible_lifecycle_clarification",
    promotion_fields: [
      ["opening", "Opening"],
      ["during_transition", "During Transition"],
      ["after_open", "After Open"],
      ["interrupt_behavior", "Interrupt Behavior"],
      ["anti_outcomes", "Anti-Outcomes"],
    ],
    execution_fields: [
      ["opening", "Opening"],
      ["during_transition", "During Transition"],
      ["after_open", "After Open"],
      ["interrupt_behavior", "Interrupt Behavior"],
      ["anti_outcomes", "Anti-Outcomes"],
    ],
  },
  {
    name: "ordered_flow",
    label: "Ordered Flow",
    gate_level: "reminder",
    signal_keys: ["ordered_flow"],
    promotion_fields: [],
    execution_fields: [],
  },
  {
    name: "safety_boundary",
    label: "Safety Boundary",
    gate_level: "soft",
    signal_keys: ["safety_boundary"],
    promotion_fields: [],
    execution_fields: [
      ["anti_outcomes", "Anti-Outcomes"],
    ],
  },
  {
    name: "observability",
    label: "Observability",
    gate_level: "reminder",
    signal_keys: ["observability"],
    promotion_fields: [],
    execution_fields: [],
  },
])
const WRITE_TOOL_RULES = Object.freeze([
  {
    name: "apply_patch",
    label: "apply_patch",
    match: (toolName) => toolName === "apply_patch",
    needsExecutionGate: () => true,
  },
  {
    name: "task:workflow-subagent",
    label: "Task",
    match: (toolName, args) => toolName === "task" && WORKFLOW_SUBAGENTS.has(getWorkflowSubagentName(args)),
    needsExecutionGate: (args) => EXECUTION_GATED_SUBAGENTS.has(getWorkflowSubagentName(args)),
  },
  {
    name: "bash:write-like",
    label: "bash",
    match: (toolName, args) => {
      if (toolName !== "bash") return false
      const cmd = String(args?.command || "")
      // Workflow-control CLI commands are not execution writes
      if (isWorkflowControlCommand(cmd)) return false
      return looksLikeBashWriteCommand(cmd)
    },
    needsExecutionGate: () => true,
  },
])

const INTAKE_PATH_MARKER = ".just-demand/state/intake/"

const WRITE_ALLOWED_STATUSES = new Set([
  "planning",
  "executing",
  "verifying",
  "changes_requested",
  "tweaking",
  "debugging",
])

const WORKFLOW_CONTROL_CLI_COMMANDS = new Set([
  "mark",
  "select-task",
  "resume",
  "complete-verification",
  "update-clarification",
  "checkpoint-commit",
  "create-intake",
  "promote",
  "list-active",
  "--help",
  "-h",
  "archive",
  "cleanup",
  "status",
  "create-session",
])

const BASH_WRITE_PATTERNS = [
  /(^|[;&|])\s*(?:mkdir|touch|rm|mv|cp|ln|install|chmod|chown)\b/i,
  /(^|[;&|])\s*git\s+(?:add|commit|amend|reset|clean|stash|checkout|switch|merge|rebase)\b/i,
  /(^|[;&|])\s*(?:sed|perl)\s+-i\b/i,
  /(^|[;&|])\s*tee\b/i,
  /(^|[;&|])\s*truncate\b/i,
  /(^|[;&|])\s*apply_patch\b/i,
]
const COMPLETION_CLAIM_PATTERNS = [
  /\b(done|finished|complete(?:d)?|implemented|shipped|resolved|wrapped up)\b/i,
  /\b(all set|good to go|ready to close|ready to ship|that'?s it|we'?re done)\b/i,
  /\b(should be good|looks good|nothing else to do|no further changes)\b/i,
  /\b(in a good place|close this out|wrap this up)\b/i,
  /(?:已经)?(?:做完了?|完成了?)/,
]

const NEGATED_COMPLETION_PATTERNS = [
  /\b(not yet|no(?:t)?\s+closing|not\s+closing\s+it\s+out|not\s+closing\s+out|not\s+done|not\s+finished|not\s+complete(?:d)?|not\s+ready\s+to\s+ship)\b/i,
  /\b(not\s+ready\s+to\s+close(?:\s+it\s+out)?\s+yet|hold\s+off\s+on\s+closing(?:\s+it\s+out)?|not\s+closing(?:\s+it\s+out)?\s+yet|can't\s+close(?:\s+it\s+out)?\s+yet|won't\s+close(?:\s+it\s+out)?\s+yet)\b/i,
  /\b(暂不|先不|还不|还不能|不能|不打算|不准备)\s*(?:收尾|结束|关闭|close|close\s+out|ship|done|完成|结束)/i,
]

const NEGATED_EXECUTION_PATTERNS = [
  /\b(still\s+want\s+to\s+confirm|want\s+to\s+confirm\s+.*\s+first|need\s+to\s+confirm\s+.*\s+first|hold\s+off\s+on|not\s+yet|before\s+i\s+(?:say|do)|before\s+we\s+(?:say|do))\b/i,
  /\b(暂时|先|还要|还需要)\s*(?:确认|核对|确认一下|核对一下|再确认|再核对)\b/i,
]

const EXPLICIT_WORKFLOW_SKIP_PATTERNS = [
  /\b(skip(?:ping)?\s+the?\s+workflow|bypass(?:ing)?\s+the?\s+workflow|workflow\s+(?:skip|bypass|override)|explicit(?:ly)?\s+(?:skip(?:ping)?|bypass(?:ing)?)\s+workflow|doing\s+this\s+(?:outside|without)\s+the?\s+workflow|proceed(?:ing)?\s+(?:outside|without)\s+the?\s+workflow)\b/i,
  /(?:跳过工作流|绕过工作流|不经过工作流)/,
]

const EXECUTION_CANDIDATE_PATTERNS = [
  /\b(i|we)\s+(am|'m|are|will|can|should|need to|need)\s+(implement|build|add|remove|refactor|update|fix|debug|investigate|trace|analy[sz]e|design|rework|extend|patch|change)\b/i,
  /\b(i|we)\s+(should|will|can|need to)\s+(implement|build|add|remove|refactor|update|fix|debug|investigate|trace|analy[sz]e|design|rework|extend|patch|change)\b/i,
  /\b(i|we)\s+(implemented|built|added|removed|refactored|updated|fixed|debugged|investigated|traced|analy[sz]ed|designed|reworked|extended|patched|changed)\b/i,
  /\b(i(?:'ll)?|we)\s+just\s+finish(?:\s+this)?\s+in\s+the\s+main\s+session\b/i,
  // "let me/us" patterns — common agent phrasing for inline execution intent
  /\b(let\s+me|let's|lets)\s+(implement|build|add|remove|refactor|update|fix|debug|investigate|trace|analy[sz]e|design|rework|extend|patch|change)\b/i,
  // "I'll" patterns
  /\bi'[gl]l\s+(implement|build|add|remove|refactor|update|fix|debug|investigate|trace|analy[sz]e|design|rework|extend|patch|change)\b/i,
  // "I'm going to" patterns
  /\bi'm\s+going\s+to\s+(implement|build|add|remove|refactor|update|fix|debug|investigate|trace|analy[sz]e|design|rework|extend|patch|change)\b/i,
  // Chinese: "让我/我来" patterns
  /(?:让我|我来|我们来)\s*(?:实现|修复|调试|排查|添加|修改|重构|更新|构建|创建|配置)/i,
  /直接在主会话里(?:实现|修复|调试|处理|修改)/,
]

const defaultReminderState = () => ({
  same_topic_turns: 0,
  last_reminder_type: null,
  subagent_unavailable_pending: false,
  intake_fallback_warning_shown: false,
})

const _intakeFallbackRecentlyUsed = new Map()

export const consumeIntakeFallbackPending = (directory) => {
  const key = workflowRoot(directory)
  if (_intakeFallbackRecentlyUsed.has(key)) {
    _intakeFallbackRecentlyUsed.delete(key)
    return true
  }
  return false
}

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

export const debugLog = (event, fields = {}, directory = null) => {
  const enabled = DEBUG_ENV_VALUES.has(String(globalThis.process?.env?.JUST_DEMAND_DEBUG || "").toLowerCase())
  if (!enabled) return

  let line
  try {
    line = JSON.stringify({ event, ...fields })
  } catch {
    line = event
  }

  console.error(`[just-demand debug] ${line}`)

  if (directory) {
    try {
      const logPath = join(workflowRoot(directory), "debug.log")
      appendFileSync(logPath, `${line}\n`, "utf8")
    } catch {
      // best-effort file log
    }
  }
}

export const getReminderState = (directory, sessionID) => {
  const key = reminderStateKey(directory, sessionID)
  if (!REMINDER_STATE.has(key)) {
    REMINDER_STATE.set(key, defaultReminderState())
  }
  return REMINDER_STATE.get(key)
}

export const getWorkflowSubagentName = (args) => {
  const candidates = [
    args?.subagent_type,
    args?.subagent,
    args?.agent,
    args?.agentName,
    args?.agent_name,
  ]
  for (const candidate of candidates) {
    const value = String(candidate || "").trim()
    if (value.startsWith(WORKFLOW_SUBAGENT_PREFIX)) return value
  }
  return ""
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

const getLastSubagentDispatchPath = (directory) => join(workflowRoot(directory), "state", LAST_SUBAGENT_DISPATCH_FILE)

const readLastSubagentDispatchState = (directory) => readJson(getLastSubagentDispatchPath(directory)) || {}

const dedupeStrings = (values) => {
  const seen = new Set()
  const result = []
  for (const value of values) {
    const text = String(value || "").trim()
    if (!text || seen.has(text)) continue
    seen.add(text)
    result.push(text)
  }
  return result
}

const getTaskDispatchLookupTaskIds = (directory, workflowTaskId) => {
  if (!workflowTaskId) return []
  const task = readTaskJson(directory, workflowTaskId)
  if (!task) return [workflowTaskId]

  const lineage = [
    task.parent_task_id,
    ...(Array.isArray(task.lineage_task_ids) ? task.lineage_task_ids : []),
    task.root_task_id,
  ]
  return dedupeStrings([workflowTaskId, ...lineage])
}

const extractTaskIdFromValue = (value, depth = 0) => {
  if (depth > 4 || value == null) return null

  if (typeof value === "string") {
    const text = value.trim()
    if (!text) return null

    if ((text.startsWith("{") && text.endsWith("}")) || (text.startsWith("[") && text.endsWith("]"))) {
      try {
        return extractTaskIdFromValue(JSON.parse(text), depth + 1)
      } catch {
        // fall through to pattern matching
      }
    }

    const directMatch = text.match(/\b(?:task[_-]?id|session[_-]?id)\s*[:=]\s*([A-Za-z0-9._:-]+)/i)
    if (directMatch) return directMatch[1]
    return null
  }

  if (Array.isArray(value)) {
    for (const item of value) {
      const found = extractTaskIdFromValue(item, depth + 1)
      if (found) return found
    }
    return null
  }

  if (typeof value === "object") {
    for (const key of ["task_id", "taskId", "session_id", "sessionId"]) {
      if (key in value) {
        const raw = value[key]
        if (typeof raw === "string") {
          const trimmed = raw.trim()
          if (trimmed) return trimmed
        }
        const found = extractTaskIdFromValue(raw, depth + 1)
        if (found) return found
      }
    }

    for (const key of ["result", "output", "response", "data", "message", "parts", "content"]) {
      if (key in value) {
        const found = extractTaskIdFromValue(value[key], depth + 1)
        if (found) return found
      }
    }

    for (const nested of Object.values(value)) {
      const found = extractTaskIdFromValue(nested, depth + 1)
      if (found) return found
    }
  }

  return null
}

export const getLastSubagentDispatchTaskId = (directory, workflowTaskId, subagentName) => {
  if (!workflowTaskId || !subagentName) return null
  const state = readLastSubagentDispatchState(directory)
  for (const taskId of getTaskDispatchLookupTaskIds(directory, workflowTaskId)) {
    const taskDispatch = state?.[taskId]?.[subagentName]?.task_id
    if (taskDispatch) return taskDispatch
  }
  return null
}

export const recordLastSubagentDispatchTaskId = (directory, workflowTaskId, subagentName, taskId) => {
  if (!workflowTaskId || !subagentName || !taskId) return null

  const path = getLastSubagentDispatchPath(directory)
  const state = readLastSubagentDispatchState(directory)
  const current = state[workflowTaskId] || {}
  current[subagentName] = {
    task_id: taskId,
    recorded_at: new Date().toISOString(),
  }
  state[workflowTaskId] = current

  mkdirSync(join(workflowRoot(directory), "state"), { recursive: true })
  writeFileSync(path, `${JSON.stringify(state, null, 2)}\n`, "utf8")
  return current[subagentName]
}

export const getRecoveredSubagentTaskId = (directory, workflowTaskId, subagentName, input = null, output = null) => {
  const fromInput = extractTaskIdFromValue(input)
  if (fromInput) return fromInput
  const fromOutput = extractTaskIdFromValue(output)
  if (fromOutput) return fromOutput
  return getLastSubagentDispatchTaskId(directory, workflowTaskId, subagentName)
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

export const detectContractTriggers = (text) => {
  const value = String(text || "")
  if (!value.trim()) return new Set()
  const active = new Set()
  for (const [contractName, patterns] of Object.entries(CONTRACT_SIGNAL_PATTERNS)) {
    if (patterns.some((pattern) => pattern.test(value))) {
      active.add(contractName)
    }
  }
  return active
}

export const detectActiveContractsForTask = (task) => {
  if (!task) return new Set()
  const clarification = task?.clarification || {}
  const active = new Set()

  // Read stored active_contracts array
  const stored = clarification.active_contracts
  if (Array.isArray(stored)) {
    for (const name of stored) {
      active.add(name)
    }
  }

  // Legacy boolean flag
  if (clarification.needs_ui_visible_lifecycle_clarification) {
    active.add("visible_effect")
  }

  // Text-based detection for visible_effect
  if (!active.has("visible_effect")) {
    const text = [
      task.title,
      task.goal,
      clarification.current_understanding,
      clarification.scope,
      clarification.final_expected_effect,
    ]
      .filter((value) => typeof value === "string" && value.trim())
      .join("\n")
    if (text.trim()) {
      const textTriggers = detectContractTriggers(text)
      for (const name of textTriggers) {
        active.add(name)
      }
    }
  }

  return active
}

export const taskLooksLikeUIVisibleLifecycleWork = (task) => {
  const active = detectActiveContractsForTask(task)
  return active.has("visible_effect")
}

export const textLooksLikeCompletionClaim = (text) => {
  const value = String(text || "").trim()
  if (!value) return false
  if (NEGATED_COMPLETION_PATTERNS.some((pattern) => pattern.test(value))) return false
  return COMPLETION_CLAIM_PATTERNS.some((pattern) => pattern.test(value))
}

export const textLooksLikeExplicitWorkflowSkip = (text) => {
  const body = String(text || "")
  if (!body.trim()) return false
  return EXPLICIT_WORKFLOW_SKIP_PATTERNS.some((pattern) => pattern.test(body))
}

export const taskLooksLikeLongContextExecutionCandidate = (task, text) => {
  if (!task || task.status === "done") return false

  const currentStep = String(task.current_step || "").toLowerCase()
  const status = String(task.status || "").toLowerCase()
  const body = String(text || "")
  if (NEGATED_EXECUTION_PATTERNS.some((pattern) => pattern.test(body))) return false
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

export const isWorkflowControlCommand = (command) => {
  const trimmed = String(command || "").trim()
  if (!trimmed) return false
  // Must match a just-demand CLI workflow-control command
  const match = trimmed.match(/^just-demand\s+\.\s+(\S+)/)
  if (!match || !WORKFLOW_CONTROL_CLI_COMMANDS.has(match[1])) return false
  // Must not also be a write-like command (composite commands like "mark && touch x" still gate)
  return !BASH_WRITE_PATTERNS.some((pattern) => pattern.test(trimmed)) && !hasUnquotedShellRedirection(trimmed)
}

export const impactsOverlap = (impactsA, impactsB) => {
  if (!Array.isArray(impactsA) || !Array.isArray(impactsB)) return false
  if (impactsA.length === 0 || impactsB.length === 0) return false
  for (const a of impactsA) {
    if (typeof a !== "string") continue
    for (const b of impactsB) {
      if (typeof b !== "string") continue
      // Path-prefix overlap: one impact scope starts with the other
      if (a.startsWith(b) || b.startsWith(a) || a === b) return true
    }
  }
  return false
}

export const looksLikeBashWriteCommand = (command) => {
  const trimmed = String(command || "").trim()
  if (!trimmed) return false
   return BASH_WRITE_PATTERNS.some((pattern) => pattern.test(trimmed)) || hasUnquotedShellRedirection(trimmed)
}

export const hasUnquotedShellRedirection = (command) => {
  let inSingleQuote = false
  let inDoubleQuote = false

  for (let index = 0; index < command.length; index += 1) {
    const char = command[index]

    if (char === "\\") {
      if (!inSingleQuote && index + 1 < command.length) index += 1
      continue
    }

    if (char === "'" && !inDoubleQuote) {
      inSingleQuote = !inSingleQuote
      continue
    }

    if (char === '"' && !inSingleQuote) {
      inDoubleQuote = !inDoubleQuote
      continue
    }

    if (char === ">" && !inSingleQuote && !inDoubleQuote) return true
  }

  return false
}

export const isIntakeFilePath = (filePath) => {
  if (!filePath || typeof filePath !== "string") return false
  const normalized = filePath.replace(/\\/g, "/")
  return normalized.includes(INTAKE_PATH_MARKER)
}

export const getApplyPatchTargetPath = (args) => {
  const patchText = String(args?.patchText || args?.patches || args?.diff || "").trim()
  if (!patchText) return null

  // Standard format: "*** Update File: path/to/file"
  const standardMatch = patchText.match(/\*\*\*\s*Update\s+File:\s+(.+?)(?:\n|$)/)
  if (standardMatch) return standardMatch[1].trim()

  // Unified diff format: "--- a/path/to/file"
  const unifiedMatch = patchText.match(/^---\s+(?:a\/)?(.+?)$/m)
  if (unifiedMatch) return unifiedMatch[1].trim()

  return null
}

export const looksLikeIntakeOperation = (toolName, args) => {
  if (!args || typeof args !== "object") return false

  if (toolName === "apply_patch") {
    const targetPath = getApplyPatchTargetPath(args)
    return isIntakeFilePath(targetPath)
  }

  if (toolName === "bash") {
    const command = String(args?.command || "").trim()
    if (!command) return false
    // Check for shell redirection to an intake file
    const redirectMatch = command.match(/[>]\s*(['"]?)((?:\.\.\/)*\.just-demand\/state\/intake\/[^'">\s]+)\1/)
    if (redirectMatch) return isIntakeFilePath(redirectMatch[2])
    // Broader match: command references intake path directly
    if (command.includes(INTAKE_PATH_MARKER)) return true
  }

  return false
}

export const getWriteToolRule = (toolName, args) => WRITE_TOOL_RULES.find((rule) => rule.match(toolName, args)) || null

export const enforceExecutionGate = (directory, toolName, args, logPrefix = "state.tool.before") => {
  const normalizedToolName = String(toolName || "").toLowerCase()
  debugLog(logPrefix, {
    tool: normalizedToolName,
    args_keys: args && typeof args === "object" ? Object.keys(args).sort() : [],
    workflow_subagent: getWorkflowSubagentName(args),
  }, directory)

  const rule = getWriteToolRule(normalizedToolName, args)
  if (!rule) {
    debugLog(`${logPrefix}.allow`, { reason: "no_write_rule", tool: normalizedToolName }, directory)
    return null
  }

  // Intake file operations bypass the execution gate entirely as a fallback path.
  // The preferred intake editing path is `update-intake-section` via the CLI.
  // Direct intake markdown edits remain available for recovery but the command
  // path is recommended for routine clarification updates.
  if (looksLikeIntakeOperation(normalizedToolName, args)) {
    debugLog(`${logPrefix}.allow`, { reason: "intake_path_allowed", rule: rule.name, tool: normalizedToolName, note: "prefer update-intake-section CLI command for intake edits" }, directory)
    // Record that intake fallback was used so the next chat.message can emit a
    // concise one-time preference reminder pointing to update-intake-section.
    _intakeFallbackRecentlyUsed.set(workflowRoot(directory), true)
    return rule
  }

  // Gate 1: Is there a selected active task?
  const gateState = getExecutionGateState(directory)
  if (gateState.reason !== "ready") {
    debugLog(`${logPrefix}.block`, { reason: gateState.reason, rule: rule.name, label: rule.label, active_task_count: gateState.activeTaskCount }, directory)
    throw new Error(buildExecutionGateError(rule.label, gateState))
  }

  const taskId = gateState.taskId
  const task = readTaskJson(directory, taskId)
  const taskStatus = String(task?.status || "").toLowerCase()

  // Gate 2: Is the task in a write-allowed status?
  // Dispatch exemption: subagent dispatch is not subject to status gating.
  // Status gating applies to execution-write tools (apply_patch, bash).
  // Readiness is enforced separately in Gate 3 for dispatch.
  const isDispatch = rule.name === "task:workflow-subagent"
  if (rule.needsExecutionGate(args) && !isDispatch && !WRITE_ALLOWED_STATUSES.has(taskStatus)) {
    debugLog(`${logPrefix}.block`, { reason: "status_not_allowed", rule: rule.name, task_id: taskId, status: taskStatus }, directory)
    throw new Error(buildExecutionGateError(rule.label, { reason: "status_not_allowed", taskId, status: taskStatus }))
  }

  // Gate 3: Execution readiness check.
  // Non-ready tasks are blocked from write tools. Use the dedicated
  // `update-clarification` CLI command to fill required clarification fields.
  // Applies to both dispatch and execution-write: dispatch requires a ready task.
  if (rule.needsExecutionGate(args) && !taskIsReadyForExecution(task)) {
    const missing = getMissingExecutionGateFields(task)
    debugLog(`${logPrefix}.block`, { reason: "task_not_ready", rule: rule.name, task_id: taskId, missing }, directory)
    throw new Error(buildExecutionGateError(rule.label, { reason: "task_not_ready", taskId, missing }))
  }

  debugLog(`${logPrefix}.allow`, { reason: "gate_passed", rule: rule.name, task_id: taskId }, directory)
  return rule
}

export const getExecutionGateState = (directory) => {
  const activeTasks = listUnfinishedTasks(directory)
  const taskId = getActiveTask(directory)
  if (taskId) {
    // Check impact overlap between current task and other active tasks
    const currentTask = readTaskJson(directory, taskId)
    const currentImpacts = currentTask?.impact || []
    const overlappingTaskIds = []
    let nonOverlappingCount = 0
    for (const t of activeTasks) {
      if (t.id === taskId) continue
      const otherTask = readTaskJson(directory, t.id)
      if (impactsOverlap(currentImpacts, otherTask?.impact || [])) {
        overlappingTaskIds.push(t.id)
      } else {
        nonOverlappingCount += 1
      }
    }
    return {
      reason: "ready",
      taskId,
      activeTaskCount: activeTasks.length,
      overlappingTaskIds,
      nonOverlappingActiveTaskCount: nonOverlappingCount,
    }
  }
  if (activeTasks.length > 0) {
    return {
      reason: "no_current_task_selected",
      taskId: null,
      activeTaskCount: activeTasks.length,
      activeTaskIds: activeTasks.map((task) => task.id),
      overlappingTaskIds: [],
      nonOverlappingActiveTaskCount: 0,
    }
  }
  return { reason: "no_formal_task", taskId: null, activeTaskCount: 0, activeTaskIds: [], overlappingTaskIds: [], nonOverlappingActiveTaskCount: 0 }
}

const _buildContractHints = (task) => {
  if (!task) return ""
  const active = detectActiveContractsForTask(task)
  const hints = []
  for (const contract of CONTRACT_REGISTRY) {
    if (!active.has(contract.name)) continue
    if (contract.gate_level === "reminder") continue
    if (contract.name === "visible_effect") {
      hints.push("For Visible Effect work, fill Opening → During Transition → After Open → Interrupt Behavior → Anti-Outcomes first")
    } else if (contract.execution_fields.length > 0) {
      const fieldLabels = contract.execution_fields.map(([, heading]) => heading).join(", ")
      hints.push(`For ${contract.label} work, fill ${fieldLabels} first`)
    }
  }
  return hints.length > 0 ? ` ${hints.join(". ")}.` : ""
}

export const buildExecutionGateError = (toolLabel, gate, missing = []) => {
  const normalized = typeof gate === "object" && gate !== null
    ? gate
    : gate
      ? { reason: "task_not_ready", taskId: gate, missing }
      : { reason: "no_formal_task" }

  const suffix = normalized.reason === "task_not_ready"
    ? `active task ${normalized.taskId} is not ready for execution yet. Missing or incomplete fields: ${normalized.missing.join(", ")}. Use \`just-demand . update-clarification ${normalized.taskId} --field <name>="<value>"\` or \`--from-file <path>\` to fill pending fields.`
    : normalized.reason === "status_not_allowed"
      ? `active task ${normalized.taskId} is in status '${normalized.status}', which does not allow writes. Allowed statuses: planning, executing, verifying, changes_requested, tweaking, debugging.`
      : normalized.reason === "no_current_task_selected"
        ? "unfinished formal tasks exist, but no current task is selected. Use just-demand . select-task <task-id> (or resume <task-id>) first."
        : "there is no formal task yet."
  return `Blocked ${toolLabel}: ${suffix}`
}

export const getMissingExecutionGateFields = (task) => {
  if (!task) return ["active formal task"]

  const clarification = task?.clarification || {}
  const missing = []

  if (!String(clarification.scope || "").trim()) {
    missing.push("Scope")
  }

  if (Array.isArray(clarification.blocking_questions) && clarification.blocking_questions.length > 0) {
    missing.push("Blocking Questions")
  }

  const taskType = String(task.type || "").trim().toLowerCase()
  const needsBugClarification = Boolean(clarification.needs_bug_clarification) || BUG_OR_MISMATCH_TASK_TYPES.has(taskType)
  if (needsBugClarification) {
    if (!String(clarification.expected_behavior || "").trim()) missing.push("Expected Behavior")
    if (!String(clarification.actual_behavior || "").trim()) missing.push("Actual Behavior")
    if (!String(clarification.reproduction || "").trim()) missing.push("Reproduction")
  }

  if (DESIGN_OR_IMPLEMENTATION_TASK_TYPES.has(taskType)) {
    if (!String(clarification.final_expected_effect || "").trim()) missing.push("Final Expected Effect")
    if (!String(clarification.chosen_approach || "").trim()) missing.push("Chosen Approach")
    if (!String(clarification.final_implementation_plan || "").trim()) missing.push("Final Implementation Plan")
    if (!String(clarification.approval || "").trim()) missing.push("Approval")
  }

  // Contract-based execution checks
  const activeContracts = detectActiveContractsForTask(task)
  for (const contract of CONTRACT_REGISTRY) {
    const cname = contract.name
    const gate = contract.gate_level
    if (!activeContracts.has(cname)) continue
    if (gate !== "hard" && gate !== "soft") continue
    for (const [fieldName, heading] of contract.execution_fields) {
      if (!String(clarification[fieldName] || "").trim()) missing.push(heading)
    }
  }

  return [...new Set(missing)]
}

export const taskIsReadyForExecution = (task) => getMissingExecutionGateFields(task).length === 0

const renderClarificationContext = (task) => {
  const clarification = task?.clarification || {}
  const entries = [
    ["Goal", clarification.final_expected_effect || clarification.expected_behavior || clarification.current_understanding],
    ["Current Reality", [clarification.actual_behavior, clarification.reproduction].filter((value) => typeof value === "string" && value.trim()).join("\n\n")],
    ["Scope", clarification.scope],
    ["Opening", clarification.opening],
    ["During Transition", clarification.during_transition],
    ["After Open", clarification.after_open],
    ["Interrupt Behavior", clarification.interrupt_behavior],
    ["Anti-Outcomes", clarification.anti_outcomes || clarification.anti_outcome],
    ["Chosen Approach", clarification.chosen_approach],
    ["Implementation Plan", clarification.final_implementation_plan],
    ["Validation", clarification.validation],
  ].filter(([, value]) => typeof value === "string" && value.trim())

  if (entries.length === 0) return ""

  return [
    "# Execution Context",
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



const packetRoleForAgent = (agentName) => {
  switch (agentName) {
    case "just-demand-coder":
      return "coder"
    case "just-demand-tester":
      return "tester"
    case "just-demand-advisor":
      return "advisor"
    case "just-demand-researcher":
      return "researcher"
    default:
      return null
  }
}

const isCompletedSubtaskStatus = (status) => {
  const normalized = String(status || "").trim().toLowerCase()
  return normalized === "done" || normalized === "complete" || normalized === "completed"
}

const selectPacketSubtaskId = (task) => {
  const subtasks = Array.isArray(task?.subtasks) ? task.subtasks : []
  if (subtasks.length === 0) return null

  const currentStep = String(task?.current_step || "").trim()
  if (currentStep) {
    const matched = subtasks.find((subtask) => {
      const id = String(subtask?.id || subtask?.subtask_id || "").trim()
      const title = String(subtask?.title || subtask?.name || subtask?.goal || "").trim()
      return currentStep === id || currentStep === title
    })
    if (matched) {
      return String(matched.id || matched.subtask_id || "").trim() || null
    }
  }

  const openSubtasks = subtasks.filter((subtask) => !isCompletedSubtaskStatus(subtask?.status))
  if (openSubtasks.length === 1) {
    return String(openSubtasks[0].id || openSubtasks[0].subtask_id || "").trim() || null
  }

  return null
}

const buildPacketHintArgs = (task) => {
  const args = []
  const currentStep = String(task?.current_step || "").trim()
  if (currentStep) {
    args.push("--hint", `focus=${currentStep}`)
  }

  const impacts = Array.isArray(task?.impact) ? task.impact : []
  for (const impact of impacts) {
    const text = String(impact || "").trim()
    if (text) {
      args.push("--hint", `recent_diff=${text}`)
    }
  }

  return args
}

const readRenderedTaskContext = (directory, taskId, agentName, task = null) => {
  const role = packetRoleForAgent(agentName)
  if (!role || !existsSync(JUST_DEMAND_CLI)) return null

  try {
    const subtaskId = selectPacketSubtaskId(task)
    const hintArgs = buildPacketHintArgs(task)
    const command = [JUST_DEMAND_CLI, directory, "render-context", taskId, "--role", role]
    if (subtaskId) command.push("--subtask-id", subtaskId)
    command.push(...hintArgs)
    const rendered = execFileSync("python3", command, {
      cwd: REPO_ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    })
    return String(rendered || "").trim() || null
  } catch {
    return null
  }
}

const readPacketLintWarnings = (directory, taskId, agentName, task = null) => {
  const role = packetRoleForAgent(agentName)
  if (!role || !existsSync(JUST_DEMAND_CLI)) return []

  try {
    const subtaskId = selectPacketSubtaskId(task)
    const hintArgs = buildPacketHintArgs(task)
    const command = [JUST_DEMAND_CLI, directory, "lint-packet", taskId, "--role", role]
    if (subtaskId) command.push("--subtask-id", subtaskId)
    command.push(...hintArgs)
    const raw = execFileSync("python3", command, {
      cwd: REPO_ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    })
    const payload = JSON.parse(String(raw || "{}"))
    if (!Array.isArray(payload?.lint)) return []
    return payload.lint
      .filter((item) => item && item.severity === "warning" && item.message)
      .map((item) => `- [WARNING] ${item.message}`)
  } catch {
    return []
  }
}



export const readTaskContext = (directory, taskId, agentName) => {
  const task = readTaskJson(directory, taskId)
  const renderedContext = readRenderedTaskContext(directory, taskId, agentName, task)
  if (renderedContext) {
    const lintWarnings = readPacketLintWarnings(directory, taskId, agentName, task)
    if (lintWarnings.length > 0) {
      return `${renderedContext}\n\n## Packet Warnings\n${lintWarnings.join("\n")}`
    }
    return renderedContext
  }

  const taskDir = join(workflowRoot(directory), "state", "active", taskId)
  const parts = []

  const context = readTextIfExists(join(taskDir, "context.md"))
  if (context) parts.push(context)

  if (["just-demand-coder", "just-demand-tester"].includes(agentName)) {
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
  if (hasRemainingOpenQuestions && ["just-demand-coder", "just-demand-tester"].includes(agentName)) {
    parts.push(renderedOpenQuestions)
  }

  switch (agentName) {
    case "just-demand-coder": {
      const implement = readTextIfExists(join(taskDir, "implement.md"))
      if (implement) parts.push(implement)
      break
    }
    case "just-demand-tester": {
      const verify = readTextIfExists(join(taskDir, "verify.md"))
      if (verify) parts.push(verify)
      break
    }
    case "just-demand-researcher": {
      const researchDir = join(taskDir, "research")
      if (existsSync(researchDir)) {
        parts.push("Research outputs: write any artifacts under this task's local research/ directory.")
      }
      break
    }
    case "just-demand-advisor": {
      const advisorDir = join(taskDir, "advisor")
      if (existsSync(advisorDir)) {
        parts.push("Advisory outputs: write any analysis artifacts under this task's local advisor/ directory.")
      }
      break
    }
  }

  return parts.join("\n\n---\n\n")
}

export const getRequiredContextFiles = (agentName) => {
  switch (agentName) {
    case "just-demand-coder":
      return ["context.md", "implement.md"]
    case "just-demand-tester":
      return ["context.md", "verify.md"]
    case "just-demand-researcher":
      return ["context.md"]
    case "just-demand-advisor":
      return ["context.md"]
    default:
      return []
  }
}

export const getMissingRequiredContextFiles = (directory, taskId, agentName) => {
  const taskDir = join(workflowRoot(directory), "state", "active", taskId)
  return getRequiredContextFiles(agentName).filter((file) => !existsSync(join(taskDir, file)))
}
