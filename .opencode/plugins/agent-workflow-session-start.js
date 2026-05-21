import { existsSync } from "node:fs"
import { workflowRoot } from "./agent-workflow-lib.js"

const injectedSessions = new Set()

const BOOTSTRAP = `# Agent Workflow Bootstrap

Use project skills instead of relying on long injected rules:
- Load \`workflow-intake\` when the user proposes or clarifies work.
- Load \`workflow-execution\` before dispatching workflow subagents or executing a formal work item.
- Load \`workflow-verification\` before reporting completion or handling correction feedback.
- Load \`workflow-memory\` when recording durable decisions, preferences, facts, open questions, or deferred options.`

export default async ({ directory }) => {
  return {
    "chat.message": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      if (input?.agent && String(input.agent).startsWith("workflow-")) return
      const sessionID = input?.sessionID || "default"
      if (injectedSessions.has(sessionID)) return
      const parts = output?.parts || []
      const textPart = parts.find((part) => part.type === "text")
      const injection = BOOTSTRAP
      if (textPart) textPart.text = `${injection}\n\n${textPart.text || ""}`
      else parts.unshift({ type: "text", text: injection })
      injectedSessions.add(sessionID)
    },
  }
}
