import {
  consumeIntakeFallbackPending,
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
  textLooksLikeExplicitWorkflowSkip,
  updateReminderState,
  workflowRoot,
} from "./just-demand-lib.js"

const REMINDER_HEADER = "[just-demand reminder]"
const CLOSEOUT_BLOCKED_HEADER = "[just-demand closeout blocked]"
const EXECUTION_BLOCKED_HEADER = "[just-demand execution blocked]"
const WORKFLOW_ENTRY_BLOCKED_HEADER = "[just-demand workflow entry required]"

const WORKFLOW_PHASE = Object.freeze({
  noTask: "no-task",
  clarification: "clarification/intake",
  execution: "execution",
  verification: "verification",
  closeout: "closeout",
})

const WORKFLOW_PHASE_ACTIONS = Object.freeze({
  [WORKFLOW_PHASE.noTask]: {
    allowed: ["enter workflow", "direct answer", "skip workflow"],
    blocked: ["start", "continue", "complete"],
  },
  [WORKFLOW_PHASE.clarification]: {
    allowed: ["continue clarification", "start execution"],
    blocked: ["complete", "skip workflow"],
  },
  [WORKFLOW_PHASE.execution]: {
    allowed: ["continue execution", "dispatch subagent"],
    blocked: ["start", "complete", "skip workflow"],
  },
  [WORKFLOW_PHASE.verification]: {
    allowed: ["complete-verification", "continue verification"],
    blocked: ["start", "continue", "skip workflow"],
  },
  [WORKFLOW_PHASE.closeout]: {
    allowed: ["checkpoint-commit", "archive"],
    blocked: ["start", "continue", "complete-verification"],
  },
})

const WORKFLOW_LIFECYCLE_INTENTS = [
  {
    kind: "complete",
    patterns: [
      /\b(complete|completed|finish|finished|wrap up|wrap this up|close out|close this out)\b/i,
      /(?:已经)?(?:完成|收尾|结束)/,
    ],
  },
  {
    kind: "continue",
    patterns: [
      /\b(continue|resume|carry on|pick up|proceed|go on)\b/i,
      /(?:继续|接着|继续做|继续推进)/,
    ],
  },
  {
    kind: "start",
    patterns: [
      /\b(start|begin|kick off|initiate|launch)\b/i,
      /(?:开始|启动|着手|开工)/,
    ],
  },
  {
    kind: "skip",
    patterns: [
      /\b(skip|bypass|omit)\b/i,
      /(?:跳过|绕过|不经过)/,
    ],
  },
]

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

const CODE_INVESTIGATION_INTENT_PATTERNS = [
  // "inspect the code/codebase/source" — allow optional adjective before target
  /\b(inspect)\s+(?:the\s+)?(?:\w+\s+)?(?:code|codebase|source)\b/i,
  // "trace through the code/implementation" / "trace the code"
  /\b(trace)\s+(?:through\s+)?(?:the\s+)?(?:\w+\s+)?(?:code|codebase|source|implementation)\b/i,
  // "search the codebase/source"
  /\b(search)\s+(?:the\s+)?(?:\w+\s+)?(?:codebase|source)\b/i,
  // "read through/over the code/source/files/implementation" / "read the code"
  /\bread\s+(?:(?:through|over)\s+)?(?:the\s+)?(?:\w+\s+)?(?:code|source|files|implementation)\b/i,
  // "look/go through the code/source/files/implementation"
  /\b(?:look|go)\s+(?:through|over)\s+(?:the\s+)?(?:\w+\s+)?(?:code|source|files|implementation)\b/i,
  // "look at the code/codebase/source/implementation"
  /\blook\s+at\s+(?:the\s+)?(?:\w+\s+)?(?:code|codebase|source|implementation)\b/i,
  // "investigate the codebase/implementation/code"
  /\binvestigate\s+(?:the\s+)?(?:\w+\s+)?(?:codebase|implementation|code)\b/i,
  // Chinese: inspect/check/search/trace/read  code/source/codebase/files
  /(?:查看|检查|搜索|跟踪|阅读|检索)\s*(?:一下|一遍)?\s*(?:代码|源码|代码库|源文件|文件)/i,
]

const NEUTRAL_ANALYSIS_PATTERNS = [
  // Self-described neutral analysis: "just reporting/analyzing/reviewing..."
  /\bjust\s+(?:reporting|analyzing|reviewing|documenting|narrating|explaining|summarizing|describing)\b/i,
  // Negated implementation intent: "not proposing/planning to implement/change..."
  /\bnot\s+(?:proposing|planning|intending|trying)\s+to\s+(?:implement|change|fix|build|modify|edit)\b/i,
  // Explicit "no action/change/work" — optionally followed by "needed/required"
  /\bno\s+(?:action|change|work)(?:\s+(?:needed|required|planned))?\b/i,
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

const textLooksLikeCodeInvestigationIntent = (text) => {
  const body = String(text || "")
  if (!body.trim()) return false
  return CODE_INVESTIGATION_INTENT_PATTERNS.some((pattern) => pattern.test(body))
}

const textLooksLikeNeutralAnalysis = (text) => {
  const body = String(text || "")
  if (!body.trim()) return false
  return NEUTRAL_ANALYSIS_PATTERNS.some((pattern) => pattern.test(body))
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

const normalizeWorkflowText = (text) => String(text || "").trim()

const currentWorkflowPhase = (activeTask, gateState) => {
  if (!activeTask) return WORKFLOW_PHASE.noTask

  const status = String(activeTask.status || "").toLowerCase()
  const step = String(activeTask.current_step || "").toLowerCase()
  const verification = String(activeTask.verification_status || "").toLowerCase()

  if (verification === "passed") return WORKFLOW_PHASE.closeout
  if (step.includes("verify") || status.includes("verify")) return WORKFLOW_PHASE.verification
  if (["execut", "implement", "changes_requested", "tweak", "debug"].some((fragment) => status.includes(fragment) || step.includes(fragment))) {
    return WORKFLOW_PHASE.execution
  }

  return gateState?.reason === "no_current_task_selected" ? WORKFLOW_PHASE.noTask : WORKFLOW_PHASE.clarification
}

const workflowStateActions = (phase) => WORKFLOW_PHASE_ACTIONS[phase] || WORKFLOW_PHASE_ACTIONS[WORKFLOW_PHASE.noTask]

const detectWorkflowLifecycleIntent = (text) => {
  const body = normalizeWorkflowText(text)
  if (!body) return null

  for (const intent of WORKFLOW_LIFECYCLE_INTENTS) {
    if (intent.patterns.some((pattern) => pattern.test(body))) return intent.kind
  }

  return null
}

const lifecycleTransitionBlocked = (intent, activeTask, gateState) => {
  const phase = currentWorkflowPhase(activeTask, gateState)
  if (!intent) return null

  if (phase === WORKFLOW_PHASE.noTask) {
    return {
      phase: CONTROLLER_PHASE.route,
      action: CONTROLLER_ACTION.block,
      reason_code: gateState?.reason === "no_current_task_selected" ? "select_task_hint" : "workflow_entry_required",
      rewrite: { mode: "replace", preserve_original: true },
    }
  }

  if (intent === "complete" && phase !== WORKFLOW_PHASE.closeout) {
    return {
      phase: CONTROLLER_PHASE.close,
      action: CONTROLLER_ACTION.block,
      reason_code: phase === WORKFLOW_PHASE.verification ? "verification_closeout" : "execution_needed",
      rewrite: { mode: "replace", preserve_original: true },
    }
  }

  if ((intent === "start" || intent === "continue") && phase === WORKFLOW_PHASE.closeout) {
    return {
      phase: CONTROLLER_PHASE.close,
      action: CONTROLLER_ACTION.block,
      reason_code: taskNeedsCheckpointFollowUp(activeTask) ? "checkpoint_followup" : "verification_closeout",
      rewrite: { mode: "replace", preserve_original: true },
    }
  }

  if (intent === "skip" && phase !== WORKFLOW_PHASE.noTask) {
    return {
      phase: CONTROLLER_PHASE.route,
      action: CONTROLLER_ACTION.block,
      reason_code: phase === WORKFLOW_PHASE.verification || phase === WORKFLOW_PHASE.closeout ? "verification_closeout" : "execution_needed",
      rewrite: { mode: "replace", preserve_original: true },
    }
  }

  return null
}

const formatWorkflowStateLines = (activeTaskId, activeTask, gateState) => {
  const phase = currentWorkflowPhase(activeTask, gateState)
  const actions = workflowStateActions(phase)
  const taskLabel = activeTaskId || (gateState?.reason === "no_current_task_selected" ? "selection pending" : "none")
  const status = activeTask ? String(activeTask.status || "unknown") : null
  const title = String(activeTask?.title || activeTask?.goal || "").trim()
  const nextActions = actions.allowed.join(", ")
  const blockedActions = actions.blocked.join(", ")

  const statusSuffix = status ? ` (${status})` : ""
  const lines = [`${WORKFLOW_STATE_MARKER} task=${taskLabel}${statusSuffix}; phase=${phase}`]
  if (activeTaskId && activeTask && title) {
    const shortTitle = title.length > 80 ? `${title.slice(0, 77)}...` : title
    lines.push(`    title: ${shortTitle}`)
  }

  if (!activeTaskId && gateState?.reason === "no_current_task_selected") {
    lines.push("    next: select-task/resume before execution; direct answer only for non-work")
  } else if (!activeTaskId) {
    lines.push("    next: enter workflow via clarification/intake, answer simple questions, or explicit skip workflow")
  } else {
    lines.push(`    next: ${nextActions}`)
  }

  if (blockedActions) {
    lines.push(`    blocked: ${blockedActions}`)
  }
  return lines.join("\n")
}

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

  // Explicit workflow skip override: agent consciously overrides the workflow
  // route to proceed inline. Overrides execution_needed, workflow_entry_required,
  // and select_task_hint. Does not override subagent_unavailable_pending above.
  if (textLooksLikeExplicitWorkflowSkip(text)) {
    return {
      phase: CONTROLLER_PHASE.route,
      action: CONTROLLER_ACTION.allow,
      reason_code: "workflow_skip_override",
      rewrite: null,
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

  // Neutral analysis/status-summary text must be checked before any active task
  // execution detection. Text that explicitly declares itself as neutral (e.g.
  // "just reviewing, no action needed") should not be blocked by execution
  // candidate patterns that incidentally match past-tense verbs like "traced".
  if (textLooksLikeNeutralAnalysis(text)) {
    return {
      phase: CONTROLLER_PHASE.route,
      action: CONTROLLER_ACTION.allow,
      reason_code: "no_op",
      rewrite: null,
    }
  }

  const activeTask = reminderState.activeTask
  const lifecycleDecision = lifecycleTransitionBlocked(detectWorkflowLifecycleIntent(text), activeTask, reminderState)
  if (lifecycleDecision) {
    return lifecycleDecision
  }

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

    // Block code investigation intent inside active execution tasks without
    // assigned subagents — reading/tracing/inspecting code to execute a task
    // is also long-context work that should route through a subagent.
    if (textLooksLikeCodeInvestigationIntent(text) && !textLooksLikeNeutralAnalysis(text)) {
      const currentStep = String(activeTask.current_step || "").toLowerCase()
      const status = String(activeTask.status || "").toLowerCase()
      const taskSignalsExecution = ["execut", "implement", "verify", "changes_requested"].some(
        (fragment) => currentStep.includes(fragment) || status.includes(fragment),
      )
      if (taskSignalsExecution) {
        return {
          phase: CONTROLLER_PHASE.execute,
          action: CONTROLLER_ACTION.block,
          reason_code: "execution_needed",
          rewrite: { mode: "replace", preserve_original: true },
        }
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

  if ((CONCRETE_WORK_PATTERNS.some((pattern) => pattern.test(text)) || textLooksLikeCodeInvestigationIntent(text)) && !activeTask) {
    const workflowEntryNarration = textLooksLikeWorkflowEntryNarration(text)
    if (workflowEntryNarration) {
      return {
        phase: CONTROLLER_PHASE.route,
        action: CONTROLLER_ACTION.allow,
        reason_code: "no_op",
        rewrite: null,
      }
    }

    if (reminderState.hasUnselectedActiveTasks) {
      return {
        phase: CONTROLLER_PHASE.route,
        action: CONTROLLER_ACTION.remind,
        reason_code: "select_task_hint",
        rewrite: { mode: "append" },
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
        "- This is usually a transient model provider or network error.",
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
        "- A one-turn skip does not carry forward: later code edits or long-context analysis need routing again unless you state a fresh explicit override.",
      ]
    case "verification_closeout":
      return [
        "- This sounds like a completion claim, but the task has not been closed with complete-verification yet.",
        "- Run `just-demand . complete-verification <task-id> passed \"<summary>\"` before concluding the task.",
        "- Treat implementation checks as done, but do not present workflow closure as complete until verification closeout runs.",
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
    case "intake_fallback":
      return [
        "- Prefer `update-intake-section` via the CLI for routine intake edits.",
        "- Raw file fallback still works but is meant for recovery—use the CLI path when possible.",
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
    "- If the implementation is done, say that checks are done but workflow closure is still incomplete.",
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
    "- This reads like execution work that must run through a just-demand-* workflow subagent, not inline in the main session.",
    "- Dispatch the supported just-demand-* subagent for the current task.",
    "- A skip only covers this turn; later analysis or code edits need a fresh routing decision unless you state a new explicit override.",
    "- To explicitly override the workflow path and continue inline, include \"skip workflow\" or \"workflow override\" in your response.",
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
    "- Three routes:",
    "  · Enter workflow (recommended): `using-just-demand` → `socratic-clarification` → `just-demand-intake`",
    "  · Direct answer: if this is a simple question or non-work inquiry, restate it without work intent.",
    "  · Skip workflow: include \"skip workflow\" or \"workflow override\" to proceed inline.",
    "",
    "Original response:",
    quotedText,
  ].join("\n")
}

const WORKFLOW_STATE_MARKER = "[workflow-state]"

const injectWorkflowStateBanner = (text, activeTaskId, activeTask, gateState) => {
  if (typeof text !== "string") return text
  if (text.includes(WORKFLOW_STATE_MARKER)) return text
  return `${text}\n\n${formatWorkflowStateLines(activeTaskId, activeTask, gateState)}`
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

      // One-time per-session intake fallback warning: if the tool execution gate
      // detected an intake fallback on the previous tool call, surface a concise
      // reminder pointing to update-intake-section as the preferred path.
      if (consumeIntakeFallbackPending(workflowDirectory)) {
        if (!reminderState.intake_fallback_warning_shown) {
          updateReminderState(workflowDirectory, sessionID, (state) => {
            state.intake_fallback_warning_shown = true
          })
          textPart.text = appendReminder(textPart.text, reminderState, "intake_fallback")
        }
      }

      if (controllerDecision.reason_code !== "subagent_retry_or_skip") {
        clearSubagentUnavailablePending(workflowDirectory, sessionID)
      }

      // Unconditional workflow-state injection: visible every turn.
      textPart.text = injectWorkflowStateBanner(textPart.text, activeTaskId, activeTask, gateState)
    },
  }
}

export { applyControllerDecision, buildControllerDecision, CONTROLLER_ACTION, CONTROLLER_PHASE, injectWorkflowStateBanner, textLooksLikeCodeInvestigationIntent, textLooksLikeExplicitWorkflowSkip, textLooksLikeNeutralAnalysis, textLooksLikeWorkflowEntryNarration }
