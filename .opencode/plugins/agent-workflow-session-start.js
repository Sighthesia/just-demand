import { existsSync } from "node:fs"
import { join } from "node:path"
import { readTextIfExists, workflowRoot } from "./agent-workflow-lib.js"

export default async ({ directory }) => {
  return {
    "chat.message": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      if (input?.agent && String(input.agent).startsWith("workflow-")) return
      const rulesPath = join(workflowRoot(directory), "global", "rules.md")
      const rules = readTextIfExists(rulesPath)
      if (!rules) return
      const parts = output?.parts || []
      const textPart = parts.find((part) => part.type === "text")
      const injection = `# Workflow Rules\n\n${rules}`
      if (textPart) textPart.text = `${injection}\n\n${textPart.text || ""}`
      else parts.unshift({ type: "text", text: injection })
    },
  }
}
