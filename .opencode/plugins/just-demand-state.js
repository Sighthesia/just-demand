import {
  getActiveTask,
  clearSubagentUnavailablePending,
  debugLog,
  enforceExecutionGate,
  getExecutionGateState,
  getReminderState,
  readTaskJson,
  taskLooksLikeLongContextExecutionCandidate,
  taskNeedsCheckpointFollowUp,
  taskNeedsVerificationCloseout,
  textLooksLikeCompletionClaim,
  updateReminderState,
} from "./just-demand-lib.js"

const REMINDER_HEADER = "[just-demand reminder]"
const CLOSEOUT_BLOCKED_HEADER = "[just-demand closeout blocked]"
const EXECUTION_BLOCKED_HEADER = "[just-demand execution blocked]"
const WORKFLOW_ENTRY_BLOCKED_HEADER = "[just-demand workflow entry required]"

const CONTROLLER_PHASE = Object.freeze({
  clarify: "clarify",
  route: "route",
  execute: "execute",
  verify: "verify",
  close: "close",
})

const CONTROLLER_ACTION = Object.freeze({
  allow: "allow",
  remind: "remind",
  block: "block",
})

const STOPWORDS = new Set([
  "about", "after", "again", "also", "am", "are", "because", "before", "can", "could", "did",
  "do", "does", "doing", "for", "from", "have", "has", "how", "i", "is", "it", "just", "let",
  "like", "me", "need", "please", "should", "that", "the", "their", "there", "this", "to", "was",
  "we", "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
])

const SHORT_SIGNAL_WORDS = new Set(["api", "bug", "css", "db", "llm", "ui", "ux", "json", "task"])

const CONCRETE_WORK_PATTERNS = [
  /\b(request|feature|bug|regression|mismatch|correction|implement|update|add|remove|fix|refactor|change|improve|build|create|make|support|setup|set up)\b/i,
  /\b(expected|actual|broken|fail|failing)\b/i,
  /(请求|需求|功能|缺陷|问题|回归|不一致|修复|修正|调试|排查|实现|新增|添加|删除|移除|重构|改造|修改|更改|更新|优化|改进|支持|创建|构建|接入|设置|配置|将.+改为|把.+改成)/,
]

const PREMISE_PATTERNS = [
  /\b(what if|could it be|assumption|premise|root cause)\b/i,
  /\b(seems? like|appears? to be)\b/i,
]

const EXECUTION_NEAR_MISS_PATTERNS = [
  /\b(still\s+want\s+to\s+confirm|want\s+to\s+confirm\s+.*\s+first|need\s+to\s+confirm\s+.*\s+first|hold\s+off\s+on|not\s+yet|before\s+i\s+(?:say|do)|before\s+we\s+(?:say|do))\b/i,
  /\b(暂时|先|还要|还需要)\s*(?:确认|核对|确认一下|核对一下|再确认|再核对)\b/i,
]

const CROSS_SENTENCE_NEAR_MISS_PATTERNS = [
  /\b(still\s+want\s+to\s+confirm|want\s+to\s+confirm\s+.*\s+first|need\s+to\s+confirm\s+.*\s+first|one\s+more\s+check|hold\s+off\s+on|not\s+yet|before\s+i\s+(?:say|do)|before\s+we\s+(?:say|do))\b/i,
  /\b(暂时|先|还要|还需要)\s*(?:确认|核对|确认一下|核对一下|再确认|再核对)\b/i,
]

const WORKFLOW_ENTRY_COMMAND_PATTERNS = [
  /\bcreate-intake\b/i,
  /\bpromote\b/i,
  /\blist-active\b/i,
  /\bjust-demand\b/i,
  /(^|\s)--help\b/i,
  /(^|\s)-h\b/i,
]

const WORKFLOW_ENTRY_NARRATION_PATTERNS = [
  /\b(workflow\s+entry|intake\s+creation|formal\s+task\s+promotion|help\s+check|help\s+path)\b/i,
  /\b(create|creating|created|promote|promoting|promoted|list|listing|listed|check|checking|checked|run|running|validate|validating|validated|describe|describing|described|mention|mentioned|document|documenting|explain|explaining|narrate|narrating|walk\s+through)\b/i,
  /(创建|创建中|提升|提升为任务|列出|检查|验证|说明|描述|记录|解释|先跑|运行).*(create-intake|promote|list-active|just-demand|--help|-h)/i,
]

const INLINE_EXECUTION_INTENT_PATTERNS = [
  /\b(implement\s+.*inline|debug\s+.*inline|finish\s+this\s+in\s+the\s+main\s+session|build\s+this\s+in\s+the\s+main\s+session|do\s+this\s+inline|main\s+session\s+.*\b(?:implement|build|fix|debug))\b/i,
  /(直接在主会话里(?:实现|修复|调试)|主会话里(?:实现|修复|调试|做这个))/,
]

const textLooksLikeWorkflowEntryNarration = (text) => {
  const body = String(text || "")
  if (!body.trim()) return false
  if (!WORKFLOW_ENTRY_COMMAND_PATTERNS.some((pattern) => pattern.test(body))) return false
  if (INLINE_EXECUTION_INTENT_PATTERNS.some((pattern) => pattern.test(body))) return false
  return WORKFLOW_ENTRY_NARRATION_PATTERNS.some((pattern) => pattern.test(body))
}

const normalizeWords = (text) => {
  const cleaned = String(text || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim()

  if (!cleaned) return []

  const words = []
  for (const word of cleaned.split(/\s+/)) {
    if (!word || STOPWORDS.has(word)) continue
    if (word.length < 4 && !SHORT_SIGNAL_WORDS.has(word)) continue
    words.push(word)
  }
  return [...new Set(words)].slice(0, 8)
}

const fingerprint = (text) => normalizeWords(text).join("|")

const joinTextParts = (parts) => {
  if (!Array.isArray(parts)) return ""
  return parts
    .filter((part) => part?.type === "text" && typeof part.text === "string")
    .map((part) => part.text)
    .join("\n")
}

const extractCurrentText = (output) => {
  const messageText = typeof output?.message?.text === "string" ? output.message.text : ""
  const outputText = joinTextParts(output?.parts)
  return [messageText, outputText].filter(Boolean).join("\n").trim()
}

const argsKeys = (args) => args && typeof args === "object" ? Object.keys(args).sort() : []

const topicMemory = new Map()

const updateTopicTurns = (sessionKey, text, reminderState) => {
  const currentFingerprint = fingerprint(text)
  const previousFingerprint = topicMemory.get(sessionKey)
  topicMemory.set(sessionKey, currentFingerprint)

  if (!currentFingerprint) {
    reminderState.same_topic_turns = 0
    return reminderState
  }

  if (!previousFingerprint) {
    reminderState.same_topic_turns = 1
    return reminderState
  }

  const currentWords = new Set(currentFingerprint.split("|").filter(Boolean))
  const previousWords = new Set(previousFingerprint.split("|").filter(Boolean))
  let overlap = 0
  for (const word of currentWords) {
    if (previousWords.has(word)) overlap += 1
  }

  reminderState.same_topic_turns = overlap >= 2 ? reminderState.same_topic_turns + 1 : 1
  return reminderState
}

const reminderTypeFromReasonCode = (reasonCode) => {
  switch (reasonCode) {
    case "subagent_retry_or_skip":
    case "checkpoint_followup":
    case "reset":
    case "premise_check":
      return reasonCode
    case "clarify_hint":
      return "clarify"
    case "select_task_hint":
      return "select_task_hint"
    default:
      return null
  }
}

const buildControllerDecision = (text, reminderState) => {
  if (reminderState.subagent_unavailable_pending) {
    return {
      phase: CONTROLLER_PHASE.route,
      action: CONTROLLER_ACTION.remind,
      reason_code: "subagent_retry_or_skip",
      rewrite: { mode: "append" },
    }
  }

  if (CROSS_SENTENCE_NEAR_MISS_PATTERNS.some((pattern) => pattern.test(text))) {
    return {
      phase: CONTROLLER_PHASE.route,
      action: CONTROLLER_ACTION.allow,
      reason_code: "no_op",
      rewrite: null,
    }
  }

  const activeTask = reminderState.activeTask
  if (activeTask) {
    if (textLooksLikeCompletionClaim(text) && taskNeedsVerificationCloseout(activeTask)) {
      return {
        phase: CONTROLLER_PHASE.verify,
        action: CONTROLLER_ACTION.block,
        reason_code: "verification_closeout",
        rewrite: { mode: "replace", preserve_original: true },
      }
    }

    if (taskLooksLikeLongContextExecutionCandidate(activeTask, text)) {
      return {
        phase: CONTROLLER_PHASE.execute,
        action: CONTROLLER_ACTION.block,
        reason_code: "execution_needed",
        rewrite: { mode: "replace", preserve_original: true },
      }
    }

    if (taskNeedsCheckpointFollowUp(activeTask)) {
      return {
        phase: CONTROLLER_PHASE.close,
        action: CONTROLLER_ACTION.remind,
        reason_code: "checkpoint_followup",
        rewrite: { mode: "append" },
      }
    }
  }

  if (CONCRETE_WORK_PATTERNS.some((pattern) => pattern.test(text)) && !activeTask) {
    if (reminderState.hasUnselectedActiveTasks) {
      return {
        phase: CONTROLLER_PHASE.route,
        action: CONTROLLER_ACTION.remind,
        reason_code: "select_task_hint",
        rewrite: { mode: "append" },
      }
    }

    if (textLooksLikeWorkflowEntryNarration(text)) {
      return {
        phase: CONTROLLER_PHASE.route,
        action: CONTROLLER_ACTION.allow,
        reason_code: "no_op",
        rewrite: null,
      }
    }

    return {
      phase: CONTROLLER_PHASE.route,
      action: CONTROLLER_ACTION.block,
      reason_code: "workflow_entry_required",
      rewrite: { mode: "replace", preserve_original: true },
    }
  }

  if (reminderState.same_topic_turns >= 3) {
    return {
      phase: CONTROLLER_PHASE.clarify,
      action: CONTROLLER_ACTION.remind,
      reason_code: "reset",
      rewrite: { mode: "append" },
    }
  }

  if (CONCRETE_WORK_PATTERNS.some((pattern) => pattern.test(text))) {
    return {
      phase: CONTROLLER_PHASE.clarify,
      action: CONTROLLER_ACTION.remind,
      reason_code: "clarify_hint",
      rewrite: { mode: "append" },
    }
  }

  if (PREMISE_PATTERNS.some((pattern) => pattern.test(text))) {
    return {
      phase: CONTROLLER_PHASE.clarify,
      action: CONTROLLER_ACTION.remind,
      reason_code: "premise_check",
      rewrite: { mode: "append" },
    }
  }

  return {
    phase: CONTROLLER_PHASE.route,
    action: CONTROLLER_ACTION.allow,
    reason_code: "no_op",
    rewrite: null,
  }
}

const buildReminderLines = (type) => {
  switch (type) {
    case "subagent_retry_or_skip":
      return [
        "- A needed subagent was unavailable on the last turn.",
        "- Choose: retry now, or skip one turn and continue in the main session.",
      ]
    case "reset":
      return [
        "- We have stayed on the same topic for 3+ turns.",
        "- Reset the problem model before adding another narrow fix.",
      ]
    case "clarify":
      return [
        "- Load using-just-demand first for repo workflow turns.",
        "- Use socratic-clarification second for any request, bug, correction, or mismatch before intake.",
        "- Use just-demand subagents proactively for long-context work.",
      ]
    case "premise_check":
      return [
        "- Check whether the current frame is the right problem model before narrowing further.",
        "- Do not keep tuning a weak premise without re-testing it.",
      ]
    case "execution_needed":
      return [
        "- This looks like execution work that should run through a just-demand-* workflow subagent.",
        "- Dispatch the supported subagent path instead of continuing the long-context work inline.",
      ]
    case "verification_closeout":
      return [
        "- This sounds like a completion claim, but the task has not been closed with complete-verification yet.",
        "- Run `just-demand . complete-verification <task-id> passed \"<summary>\"` before concluding the task.",
      ]
    case "checkpoint_followup":
      return [
        "- Verification is already passed, but the successful checkpoint follow-up is still missing.",
        "- Confirm the checkpoint commit path completed successfully before treating the task as fully closed.",
      ]
    case "workflow_entry_required":
      return [
        "- This is concrete workflow work, but there is no formal task yet.",
        "- Return to the workflow entry path first: use `using-just-demand`, then `socratic-clarification`, then `just-demand-intake` before continuing.",
      ]
    case "select_task_hint":
      return [
        "- Unfinished formal tasks already exist, but no current task is selected.",
        "- Run `just-demand . list-active`, then `just-demand . select-task <task-id>` (or `resume <task-id>`) before continuing write or execution work.",
      ]
    default:
      return []
  }
}

const appendReminder = (text, reminderState, reminderType) => {
  if (typeof text !== "string") return text
  if (!reminderType) return text
  if (text.includes(REMINDER_HEADER)) return text
  if (reminderState.last_reminder_type === reminderType) return text

  updateReminderState(reminderState.directory, reminderState.sessionID, (state) => {
    state.last_reminder_type = reminderType
    if (reminderType === "subagent_retry_or_skip") {
      state.subagent_unavailable_pending = false
    }
  })

  return `${text}\n\n${[REMINDER_HEADER, ...buildReminderLines(reminderType)].join("\n")}`
}

const applyControllerDecision = (text, reminderState, decision) => {
  if (decision.action === CONTROLLER_ACTION.block) {
    if (decision.reason_code === "verification_closeout") return blockVerificationCloseout(text, reminderState)
    if (decision.reason_code === "execution_needed") return blockExecutionNeeded(text, reminderState)
    if (decision.reason_code === "workflow_entry_required") return blockWorkflowEntryRequired(text, reminderState)
  }

  if (decision.action === CONTROLLER_ACTION.remind) {
    return appendReminder(text, reminderState, reminderTypeFromReasonCode(decision.reason_code))
  }

  return text
}

const blockVerificationCloseout = (text, reminderState) => {
  if (typeof text !== "string") return text
  if (text.includes(CLOSEOUT_BLOCKED_HEADER)) return text

  updateReminderState(reminderState.directory, reminderState.sessionID, (state) => {
    state.last_reminder_type = "verification_closeout"
  })

  const trimmed = text.trim()
  const quotedText = trimmed
    ? `> ${trimmed.replace(/\n/g, "\n> ")}`
    : "> (empty response)"

  return [
    CLOSEOUT_BLOCKED_HEADER,
    "- This reads like a completion claim, but the task has not passed verification closeout yet.",
    "- Run `just-demand . complete-verification <task-id> passed \"<summary>\"` before concluding the task.",
    "",
    "Original response:",
    quotedText,
  ].join("\n")
}

const blockExecutionNeeded = (text, reminderState) => {
  if (typeof text !== "string") return text
  if (text.includes(EXECUTION_BLOCKED_HEADER)) return text

  updateReminderState(reminderState.directory, reminderState.sessionID, (state) => {
    state.last_reminder_type = "execution_needed"
  })

  const trimmed = text.trim()
  const quotedText = trimmed
    ? `> ${trimmed.replace(/\n/g, "\n> ")}`
    : "> (empty response)"

  return [
    EXECUTION_BLOCKED_HEADER,
    "- This reads like execution work that should run through a just-demand-* workflow subagent.",
    "- Dispatch the supported just-demand-* subagent path before continuing the long-context work inline.",
    "",
    "Original response:",
    quotedText,
  ].join("\n")
}

const blockWorkflowEntryRequired = (text, reminderState) => {
  if (typeof text !== "string") return text
  if (text.includes(WORKFLOW_ENTRY_BLOCKED_HEADER)) return text

  updateReminderState(reminderState.directory, reminderState.sessionID, (state) => {
    state.last_reminder_type = "workflow_entry_required"
  })

  const trimmed = text.trim()
  const quotedText = trimmed
    ? `> ${trimmed.replace(/\n/g, "\n> ")}`
    : "> (empty response)"

  return [
    WORKFLOW_ENTRY_BLOCKED_HEADER,
    "- This is concrete workflow work, but there is no formal task yet.",
    "- Return to the workflow entry path first: use `using-just-demand`, then `socratic-clarification`, then `just-demand-intake` before continuing.",
    "",
    "Original response:",
    quotedText,
  ].join("\n")
}

export default async ({ directory } = {}) => {
  return {
    "tool.execute.before": async (input, output) => {
      const workflowDirectory = directory || input?.directory || input?.root || input?.cwd || "."
      if (!workflowDirectory) return

      enforceExecutionGate(workflowDirectory, input?.tool, output?.args, "state.tool.before")
    },

    "chat.message": async (input, output) => {
      const workflowDirectory = directory || input?.directory || input?.root || input?.cwd || "."
      // Keep main-session injection lightweight: reminder only, no task state dump.
      // This layer is best-effort: some OpenCode versions do not expose usable text
      // parts to chat.message, so Layer 1 system prompt injection remains the primary path.
      if (!output || !Array.isArray(output.parts)) {
        debugLog("state.chat.message.skip", { reason: "missing_parts" }, workflowDirectory)
        return
      }
      const textPart = output.parts.find((part) => part?.type === "text" && typeof part.text === "string")
      if (!textPart) {
        debugLog("state.chat.message.skip", { reason: "missing_text_part", part_types: output.parts.map((part) => part?.type).filter(Boolean) }, workflowDirectory)
        return
      }

      const sessionID = typeof input?.sessionID === "string" && input.sessionID ? input.sessionID : "main"
      const activeTaskId = getActiveTask(workflowDirectory)
      const activeTask = activeTaskId ? (readTaskJson(workflowDirectory, activeTaskId) || { id: activeTaskId }) : null
      const reminderState = getReminderState(workflowDirectory, sessionID)
      const gateState = getExecutionGateState(workflowDirectory)
      reminderState.directory = workflowDirectory
      reminderState.sessionID = sessionID
      reminderState.activeTask = activeTask
      reminderState.hasUnselectedActiveTasks = gateState.reason === "no_current_task_selected"

      const currentText = extractCurrentText(output)
      updateTopicTurns(`${workflowDirectory}::${sessionID}`, currentText, reminderState)

      const controllerDecision = buildControllerDecision(currentText, reminderState)
      debugLog("state.chat.message.decision", {
        session_id: sessionID,
        active_task_id: activeTaskId || null,
        phase: controllerDecision.phase,
        action: controllerDecision.action,
        reason_code: controllerDecision.reason_code,
      }, workflowDirectory)
      textPart.text = applyControllerDecision(textPart.text, reminderState, controllerDecision)

      if (controllerDecision.reason_code !== "subagent_retry_or_skip") {
        clearSubagentUnavailablePending(workflowDirectory, sessionID)
      }
    },
  }
}

export { applyControllerDecision, buildControllerDecision, CONTROLLER_ACTION, CONTROLLER_PHASE, textLooksLikeWorkflowEntryNarration }
