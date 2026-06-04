import {
  getActiveTask,
  clearSubagentUnavailablePending,
  getReminderState,
  readTaskJson,
  updateReminderState,
} from "./just-demand-lib.js"

const REMINDER_HEADER = "[just-demand reminder]"

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

export default async ({ directory } = {}) => {
  return {
    "chat.message": async (input, output) => {
      // Keep main-session injection lightweight: reminder only, no task state dump.
      if (!output || !Array.isArray(output.parts)) return
      const textPart = output.parts.find((part) => part?.type === "text" && typeof part.text === "string")
      if (!textPart) return

      const sessionID = typeof input?.sessionID === "string" && input.sessionID ? input.sessionID : "main"
      const workflowDirectory = directory || input?.directory || input?.root || input?.cwd || "."
      const activeTaskId = getActiveTask(workflowDirectory)
      const activeTask = activeTaskId ? readTaskJson(workflowDirectory, activeTaskId) : null
      if (!activeTaskId || activeTask?.status === "done") return
      const reminderState = getReminderState(workflowDirectory, sessionID)
      reminderState.directory = workflowDirectory
      reminderState.sessionID = sessionID

      const currentText = extractCurrentText(output)
      updateTopicTurns(`${workflowDirectory}::${sessionID}`, currentText, reminderState)

      const reminderType = chooseReminderType(currentText, reminderState)
      textPart.text = appendReminder(textPart.text, reminderState, reminderType)

      if (reminderType !== "subagent_retry_or_skip") {
        clearSubagentUnavailablePending(workflowDirectory, sessionID)
      }
    },
  }
}
