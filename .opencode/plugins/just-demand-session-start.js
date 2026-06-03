const SESSION_REMINDER = [
  "<JUST_DEMAND_REMINDER>",
  "Clarify new concrete work first.",
  "Check for a stronger explanation before adopting the user's framing.",
  "After 3+ same-topic turns, reset the problem model before continuing.",
  "</JUST_DEMAND_REMINDER>",
].join("\n")

export default async () => {
  return {
    "experimental.chat.system.transform": async (_input, output) => {
      if (!output || typeof output.text !== "string") return
      if (output.text.includes("<JUST_DEMAND_REMINDER>")) return
      output.text = `${output.text}\n\n${SESSION_REMINDER}`
    },
  }
}
