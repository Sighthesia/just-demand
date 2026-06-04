const SESSION_REMINDER = [
  "<JUST_DEMAND_REMINDER>",
  "Load using-just-demand first for repo workflow turns.",
  "Use socratic-clarification second for any request, bug, correction, or mismatch before intake.",
  "Use just-demand subagents proactively for long-context work.",
  "If a needed subagent is unavailable, ask whether to retry now or skip one turn.",
  "</JUST_DEMAND_REMINDER>",
].join("\n")

export default async () => {
  return {
    "experimental.chat.system.transform": async (_input, output) => {
      if (!output || !Array.isArray(output.system)) return
      if (output.system.some((segment) => typeof segment === "string" && segment.includes("<JUST_DEMAND_REMINDER>"))) {
        return
      }
      output.system.push(SESSION_REMINDER)
    },
  }
}
