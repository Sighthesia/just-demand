import {
  getActiveTask,
  clearSubagentUnavailablePending,
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

const STOPWORDS = new Set([
  "about", "after", "again", "also", "am", "are", "because", "before", "can", "could", "did",
  "do", "does", "doing", "for", "from", "have", "has", "how", "i", "is", "it", "just", "let",
  "like", "me", "need", "please", "should", "that", "the", "their", "there", "this", "to", "was",
  "we", "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
])

const SHORT_SIGNAL_WORDS = new Set(["api", "bug", "css", "db", "llm", "ui", "ux", "json", "task"])

const CONCRETE_WORK_PATTERNS = [
  /\b(request|feature|bug|regression|mismatch|correction|implement|update|add|remove|fix|refactor|change|improve)\b/i,
  /\b(expected|actual|broken|fail|failing)\b/i,
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

const chooseReminderType = (text, reminderState) => {
  if (reminderState.subagent_unavailable_pending) return "subagent_retry_or_skip"

  if (CROSS_SENTENCE_NEAR_MISS_PATTERNS.some((pattern) => pattern.test(text))) return null

  const activeTask = reminderState.activeTask
  if (activeTask) {
    if (taskNeedsCheckpointFollowUp(activeTask)) return "checkpoint_followup"
    if (textLooksLikeCompletionClaim(text) && taskNeedsVerificationCloseout(activeTask)) return "verification_closeout"
    if (taskLooksLikeLongContextExecutionCandidate(activeTask, text)) return "execution_needed"
  }

  if (reminderState.same_topic_turns >= 3) return "reset"
  if (CONCRETE_WORK_PATTERNS.some((pattern) => pattern.test(text))) return "clarify"
  if (PREMISE_PATTERNS.some((pattern) => pattern.test(text))) return "premise_check"
  return null
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
        "- Run `python3 .just-demand/scripts/task.py --root . complete-verification <task-id> passed \"<summary>\"` before concluding the task.",
      ]
    case "checkpoint_followup":
      return [
        "- Verification is already passed, but the successful checkpoint follow-up is still missing.",
        "- Confirm the checkpoint commit path completed successfully before treating the task as fully closed.",
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
    "- Run `python3 .just-demand/scripts/task.py --root . complete-verification <task-id> passed \"<summary>\"` before concluding the task.",
    "",
    "Original response:",
    quotedText,
  ].join("\n")
}

export default async ({ directory } = {}) => {
  return {
    "chat.message": async (input, output) => {
      // Keep main-session injection lightweight: reminder only, no task state dump.
      // This layer is best-effort: some OpenCode versions do not expose usable text
      // parts to chat.message, so Layer 1 system prompt injection remains the primary path.
      if (!output || !Array.isArray(output.parts)) return
      const textPart = output.parts.find((part) => part?.type === "text" && typeof part.text === "string")
      if (!textPart) return

      const sessionID = typeof input?.sessionID === "string" && input.sessionID ? input.sessionID : "main"
      const workflowDirectory = directory || input?.directory || input?.root || input?.cwd || "."
      const activeTaskId = getActiveTask(workflowDirectory)
      const activeTask = activeTaskId ? (readTaskJson(workflowDirectory, activeTaskId) || { id: activeTaskId }) : null
      if (!activeTaskId) return
      const reminderState = getReminderState(workflowDirectory, sessionID)
      reminderState.directory = workflowDirectory
      reminderState.sessionID = sessionID
      reminderState.activeTask = activeTask

      const currentText = extractCurrentText(output)
      updateTopicTurns(`${workflowDirectory}::${sessionID}`, currentText, reminderState)

      const reminderType = chooseReminderType(currentText, reminderState)
      if (reminderType === "verification_closeout") {
        textPart.text = blockVerificationCloseout(textPart.text, reminderState)
      } else {
        textPart.text = appendReminder(textPart.text, reminderState, reminderType)
      }

      if (reminderType !== "subagent_retry_or_skip") {
        clearSubagentUnavailablePending(workflowDirectory, sessionID)
      }
    },
  }
}
