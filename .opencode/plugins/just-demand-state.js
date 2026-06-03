const MESSAGE_REMINDER = [
  "[just-demand reminder]",
  "- Clarify new concrete work first.",
  "- Check for a stronger explanation before adopting the user's framing.",
  "- After 3+ same-topic turns, reset the problem model.",
].join("\n")

const appendReminder = (text) => {
  if (typeof text !== "string") return text
  if (text.includes("[just-demand reminder]")) return text
  return `${text}\n\n${MESSAGE_REMINDER}`
}

export default async () => {
  return {
    "chat.message": async (_input, output) => {
      // Keep main-session injection lightweight: reminder only, no task state dump.
      if (!output || !Array.isArray(output.parts)) return
      const textPart = output.parts.find((part) => part?.type === "text" && typeof part.text === "string")
      if (!textPart) return
      textPart.text = appendReminder(textPart.text)
    },
  }
}
