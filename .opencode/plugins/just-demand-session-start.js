import { existsSync, readFileSync } from "node:fs"
import { join, dirname } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))
const skillsDir = join(__dirname, "..", "skills")

const extractAndStripFrontmatter = (content) => {
  const match = content.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/)
  if (!match) return { frontmatter: {}, content }
  const frontmatterStr = match[1]
  const body = match[2]
  const frontmatter = {}
  for (const line of frontmatterStr.split("\n")) {
    const colonIdx = line.indexOf(":")
    if (colonIdx > 0) {
      const key = line.slice(0, colonIdx).trim()
      const value = line.slice(colonIdx + 1).trim().replace(/^["']|["']$/g, "")
      frontmatter[key] = value
    }
  }
  return { frontmatter, content: body }
}

let _bootstrapCache = undefined

const getBootstrapContent = () => {
  if (_bootstrapCache !== undefined) return _bootstrapCache

  const skillPath = join(skillsDir, "using-just-demand", "SKILL.md")
  if (!existsSync(skillPath)) {
    _bootstrapCache = null
    return null
  }

  const fullContent = readFileSync(skillPath, "utf8")
  const { content } = extractAndStripFrontmatter(fullContent)

  _bootstrapCache = `<JUST_DEMAND_WORKFLOW>
You have workflow skills available for this repository.

**IMPORTANT: The using-just-demand skill content is included below. It is ALREADY LOADED - you are currently following it. Do NOT use the skill tool to load "using-just-demand" again - that would be redundant.**

${content}
</JUST_DEMAND_WORKFLOW>`

  return _bootstrapCache
}

export default async () => {
  return {
    "experimental.chat.system.transform": async (_input, output) => {
      const bootstrap = getBootstrapContent()
      if (!bootstrap) return

      // Guard: skip if system prompt already contains bootstrap
      if (output.text && output.text.includes("JUST_DEMAND_WORKFLOW")) return

      // Append bootstrap to system prompt
      output.text = output.text ? `${output.text}\n\n${bootstrap}` : bootstrap
    },
  }
}
