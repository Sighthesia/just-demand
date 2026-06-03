import assert from "node:assert/strict"
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"

import {
  getActiveTask,
  getMissingRequiredContextFiles,
  listUnfinishedTasks,
  readJson,
  readTaskContext,
} from "../../.opencode/plugins/just-demand-lib.js"
import sessionStartFactory from "../../.opencode/plugins/just-demand-session-start.js"
import stateFactory from "../../.opencode/plugins/just-demand-state.js"
import subagentContextFactory from "../../.opencode/plugins/just-demand-subagent-context.js"

function makeRoot() {
  return mkdtempSync(join(tmpdir(), "just-demand-"))
}

function scaffoldWorkflow(root) {
  const base = join(root, ".just-demand")
  mkdirSync(join(base, "state"), { recursive: true })
  mkdirSync(join(base, "knowledge"), { recursive: true })
  mkdirSync(join(base, "state", "active"), { recursive: true })
  writeFileSync(join(base, "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: "task-a" }))
  writeFileSync(join(base, "knowledge", "memory.md"), "# Just Demand Memory\n\n## Facts\n\nKey fact: system uses JSONL.\n\n## Decisions\n\nChose approach A.\n\n## Deferred Options\n\nOption X deferred.\n")
}

// ---------------------------------------------------------------------------
// lib: getActiveTask
// ---------------------------------------------------------------------------
test("getActiveTask reads current task from workspace state", () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: "task-a" }))
  assert.equal(getActiveTask(root), "task-a")
})

test("getActiveTask returns null when state.json missing", () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  assert.equal(getActiveTask(root), null)
})

// ---------------------------------------------------------------------------
// lib: readJson fault tolerance
// ---------------------------------------------------------------------------
test("readJson returns null for invalid JSON", () => {
  const root = makeRoot()
  const p = join(root, "bad.json")
  writeFileSync(p, "{not valid json")
  assert.equal(readJson(p), null)
})

test("readJson returns null for missing file", () => {
  assert.equal(readJson("/nonexistent/path.json"), null)
})

// ---------------------------------------------------------------------------
// lib: listUnfinishedTasks
// ---------------------------------------------------------------------------
test("listUnfinishedTasks returns only unfinished tasks", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const activeDir = join(root, ".just-demand", "state", "active")
  mkdirSync(join(activeDir, "task-done"), { recursive: true })
  writeFileSync(join(activeDir, "task-done", "task.json"), JSON.stringify({ id: "task-done", title: "Done task", status: "done" }))
  mkdirSync(join(activeDir, "task-active"), { recursive: true })
  writeFileSync(join(activeDir, "task-active", "task.json"), JSON.stringify({ id: "task-active", title: "Active task", status: "planning", current_step: "step1" }))

  const result = listUnfinishedTasks(root)
  assert.equal(result.length, 1)
  assert.equal(result[0].id, "task-active")
  assert.equal(result[0].title, "Active task")
  assert.equal(result[0].status, "planning")
  assert.equal(result[0].current_step, "step1")
  assert.ok(result[0].path.includes("task-active"))
})

test("listUnfinishedTasks skips directories with missing task.json", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const activeDir = join(root, ".just-demand", "state", "active")
  mkdirSync(join(activeDir, "task-nojson"), { recursive: true })
  mkdirSync(join(activeDir, "task-ok"), { recursive: true })
  writeFileSync(join(activeDir, "task-ok", "task.json"), JSON.stringify({ id: "task-ok", status: "implementing" }))

  const result = listUnfinishedTasks(root)
  assert.equal(result.length, 1)
  assert.equal(result[0].id, "task-ok")
})

test("listUnfinishedTasks skips directories with corrupt task.json", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const activeDir = join(root, ".just-demand", "state", "active")
  mkdirSync(join(activeDir, "task-bad"), { recursive: true })
  writeFileSync(join(activeDir, "task-bad", "task.json"), "{not valid json")
  mkdirSync(join(activeDir, "task-ok"), { recursive: true })
  writeFileSync(join(activeDir, "task-ok", "task.json"), JSON.stringify({ id: "task-ok", status: "design" }))

  const result = listUnfinishedTasks(root)
  assert.equal(result.length, 1)
  assert.equal(result[0].id, "task-ok")
})

test("listUnfinishedTasks returns empty array when active dir missing", () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  const result = listUnfinishedTasks(root)
  assert.deepEqual(result, [])
})



// ---------------------------------------------------------------------------
// lib: readTaskContext - implement
// ---------------------------------------------------------------------------
test("readTaskContext combines context and implement brief", () => {
  const root = makeRoot()
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nBuild")
  writeFileSync(join(taskDir, "open_questions.md"), "# Open Questions\n\n## Remaining Open Questions\n\n- Should we keep the legacy label?\n")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { expected_behavior: "Saving shows a toast.", actual_behavior: "Saving does nothing.", reproduction: "1. Click save", scope: "Save flow only.", non_blocking_questions: ["Should we keep the legacy label?"] } }))
  writeFileSync(join(taskDir, "verify.md"), "# Verify\nCheck")
  const context = readTaskContext(root, "task-a", "just-demand-implement")
  assert.match(context, /# Context/)
  assert.match(context, /# Clarification/)
  assert.match(context, /Saving shows a toast/)
  assert.match(context, /Saving does nothing/)
  assert.match(context, /Save flow only/)
  assert.match(context, /# Implement/)
  assert.match(context, /Remaining Open Questions/)
  assert.doesNotMatch(context, /# Verify/)
})

test("readTaskContext includes open questions for just-demand-check", () => {
  const root = makeRoot()
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "verify.md"), "# Verify\nCheck")
  writeFileSync(join(taskDir, "open_questions.md"), "# Open Questions\n\n## Remaining Open Questions\n\n- Is analytics coverage required?\n")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { expected_behavior: "Event fires once.", actual_behavior: "Event fires twice.", reproduction: "Submit the form once.", scope: "Analytics submit path.", non_blocking_questions: ["Is analytics coverage required?"] } }))
  const context = readTaskContext(root, "task-a", "just-demand-check")
  assert.match(context, /# Clarification/)
  assert.match(context, /Event fires once/)
  assert.match(context, /Event fires twice/)
  assert.match(context, /Remaining Open Questions/)
  assert.match(context, /analytics coverage/)
})

test("readTaskContext includes final design artifact for implement and check", () => {
  const root = makeRoot()
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nBuild")
  writeFileSync(join(taskDir, "verify.md"), "# Verify\nCheck")
  writeFileSync(join(taskDir, "open_questions.md"), "# Open Questions\n\n")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    clarification: {
      scope: "Settings flow only.",
      final_expected_effect: "User can save settings confidently.",
      approach_options: "A. Inline save\nB. Background save",
      chosen_approach: "Approach A: inline save.",
      final_implementation_plan: "1. Add save handler\n2. Verify save feedback",
      validation: "Run save flow test.",
      approval: "User approved Approach A.",
    },
  }))

  const implementContext = readTaskContext(root, "task-a", "just-demand-implement")
  const checkContext = readTaskContext(root, "task-a", "just-demand-check")

  for (const context of [implementContext, checkContext]) {
    assert.match(context, /Final Expected Effect/)
    assert.match(context, /User can save settings confidently/)
    assert.match(context, /Chosen Approach/)
    assert.match(context, /Approach A: inline save/)
    assert.match(context, /Final Implementation Plan/)
    assert.match(context, /Approval/)
  }
})

test("readTaskContext falls back to task clarification questions when open_questions is just a header", () => {
  const root = makeRoot()
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nBuild")
  writeFileSync(join(taskDir, "open_questions.md"), "# Open Questions\n\n")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { non_blocking_questions: ["Should the fallback question be shown?"] } }))
  const context = readTaskContext(root, "task-a", "just-demand-implement")
  assert.match(context, /Remaining Open Questions/)
  assert.match(context, /fallback question be shown/)
})

// ---------------------------------------------------------------------------
// lib: readTaskContext - research
// ---------------------------------------------------------------------------
test("readTaskContext for just-demand-research includes workspace facts", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const context = readTaskContext(root, "task-a", "just-demand-research")
  assert.match(context, /# Context/)
  assert.match(context, /workspace facts/i)
  assert.match(context, /JSONL/)
})

test("readTaskContext for just-demand-research avoids absolute research path leakage", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "research"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const context = readTaskContext(root, "task-a", "just-demand-research")
  assert.match(context, /research outputs/i)
  assert.match(context, /local research\//i)
  assert.equal(context.includes(root), false)
})

// ---------------------------------------------------------------------------
// lib: readTaskContext - docs
// ---------------------------------------------------------------------------
test("readTaskContext for just-demand-docs includes workspace decisions", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const context = readTaskContext(root, "task-a", "just-demand-docs")
  assert.match(context, /# Context/)
  assert.match(context, /workspace decisions/i)
  assert.match(context, /approach A/)
})

test("readTaskContext for just-demand-docs includes deferred options", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const context = readTaskContext(root, "task-a", "just-demand-docs")
  assert.match(context, /deferred options/i)
  assert.match(context, /Option X/)
})

test("getMissingRequiredContextFiles reports missing implement context files", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const missing = getMissingRequiredContextFiles(root, "task-a", "just-demand-implement")
  assert.deepEqual(missing, ["implement.md"])
})

// ---------------------------------------------------------------------------
// plugin factory: session-start returns hooks object
// ---------------------------------------------------------------------------
test("session-start factory returns hooks object with experimental.chat.system.transform", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  assert.ok(plugin)
  assert.equal(typeof plugin["experimental.chat.system.transform"], "function")
})

// ---------------------------------------------------------------------------
// plugin factory: state returns hooks object
// ---------------------------------------------------------------------------
test("state factory returns hooks object with chat.message", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await stateFactory({ directory: root })
  assert.ok(plugin)
  assert.equal(typeof plugin["chat.message"], "function")
})

// ---------------------------------------------------------------------------
// plugin factory: subagent-context returns hooks object
// ---------------------------------------------------------------------------
test("subagent-context factory returns hooks object with tool.execute.before", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await subagentContextFactory({ directory: root })
  assert.ok(plugin)
  assert.equal(typeof plugin["tool.execute.before"], "function")
})

// ---------------------------------------------------------------------------
// session-start: no visible main-session injection
// ---------------------------------------------------------------------------
test("session-start does not inject workflow bootstrap into system prompt", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  const output = { text: "You are a helpful assistant." }
  await plugin["experimental.chat.system.transform"]({ sessionID: "s1" }, output)
  assert.match(output.text, /^You are a helpful assistant\./)
  assert.match(output.text, /<JUST_DEMAND_REMINDER>/)
  assert.match(output.text, /Clarify new concrete work first/i)
  assert.doesNotMatch(output.text, /<workflow-state>/i)
})

test("session-start leaves existing workflow marker text untouched", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  const output = { text: "Existing <JUST_DEMAND_WORKFLOW>content</JUST_DEMAND_WORKFLOW>" }
  await plugin["experimental.chat.system.transform"]({ sessionID: "s1" }, output)
  assert.match(output.text, /<JUST_DEMAND_WORKFLOW>content<\/JUST_DEMAND_WORKFLOW>/)
  assert.match(output.text, /<JUST_DEMAND_REMINDER>/)
})

test("session-start preserves existing system prompt content", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  const output = { text: "Original system prompt." }
  await plugin["experimental.chat.system.transform"]({ sessionID: "s1" }, output)
  assert.match(output.text, /^Original system prompt\./)
  assert.match(output.text, /stronger explanation/i)
})

test("session-start avoids duplicate reminder injection", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  const output = { text: "Base prompt.\n\n<JUST_DEMAND_REMINDER>already there</JUST_DEMAND_REMINDER>" }
  await plugin["experimental.chat.system.transform"]({ sessionID: "s1" }, output)
  assert.equal(output.text, "Base prompt.\n\n<JUST_DEMAND_REMINDER>already there</JUST_DEMAND_REMINDER>")
})

// ---------------------------------------------------------------------------
// state: main-session does not inject workflow state
// ---------------------------------------------------------------------------
test("state does not inject workflow state into main-session messages", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning" }))
  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Hello" }] }
  await plugin["chat.message"]({}, output)
  assert.match(output.parts[0].text, /^Hello/)
  assert.match(output.parts[0].text, /\[just-demand reminder\]/)
  assert.doesNotMatch(output.parts[0].text, /task-a/)
})

test("state does not inject when no active task", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Hello" }] }
  await plugin["chat.message"]({}, output)
  assert.match(output.parts[0].text, /^Hello/)
  assert.match(output.parts[0].text, /Clarify new concrete work first/i)
})

test("state does not inject when active task is done", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "done" }))
  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Hello" }] }
  await plugin["chat.message"]({}, output)
  assert.match(output.parts[0].text, /^Hello/)
  assert.match(output.parts[0].text, /reset the problem model/i)
})

test("state avoids duplicate reminder injection", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await stateFactory({ directory: root })
  const text = "Hello\n\n[just-demand reminder]\n- already there"
  const output = { parts: [{ type: "text", text }] }
  await plugin["chat.message"]({}, output)
  assert.equal(output.parts[0].text, text)
})

// ---------------------------------------------------------------------------
// subagent-context: only injects for supported workflow subagents
// ---------------------------------------------------------------------------
test("subagent-context injects context for supported subagent type", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nSteps")
  writeFileSync(join(taskDir, "open_questions.md"), "# Open Questions\n\n## Remaining Open Questions\n\n- Should the old shortcut still work?\n")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { expected_behavior: "Shortcut triggers the action.", actual_behavior: "Shortcut is ignored.", reproduction: "Press the shortcut once.", scope: "Keyboard shortcut handling.", non_blocking_questions: ["Should the old shortcut still work?"] } }))
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-implement", prompt: "Do the work" } }
  await plugin["tool.execute.before"](input, output)
  assert.match(output.args.prompt, /Active task: task-a/)
  assert.match(output.args.prompt, /# Just Demand Workflow/)
  assert.match(output.args.prompt, /# Execution Rules/)
  assert.match(output.args.prompt, /Do not call the Task tool\./)
  assert.match(output.args.prompt, /# Context/)
  assert.match(output.args.prompt, /# Clarification/)
  assert.match(output.args.prompt, /Shortcut triggers the action/)
  assert.match(output.args.prompt, /# Implement/)
  assert.match(output.args.prompt, /Remaining Open Questions/)
  assert.match(output.args.prompt, /# Requested Work/)
  assert.match(output.args.prompt, /Do the work/)
})

test("subagent-context avoids absolute path leakage for just-demand-research", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "research"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: research topic")
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-research", prompt: "Investigate this" } }
  await plugin["tool.execute.before"](input, output)
  assert.match(output.args.prompt, /research outputs/i)
  assert.match(output.args.prompt, /local research\//i)
  assert.equal(output.args.prompt.includes(root), false)
})

test("subagent-context throws when writable subagent required context files are missing", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-implement", prompt: "Do the work" } }
  await assert.rejects(
    plugin["tool.execute.before"](input, output),
    /Blocked just-demand-implement: missing required task context files.*implement\.md/,
  )
  assert.equal(output.args.prompt, "Do the work")
})

test("subagent-context still annotates read-only research subagent when required context files are missing", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-research", prompt: "Investigate this" } }
  await plugin["tool.execute.before"](input, output)
  assert.match(output.args.prompt, /# BLOCKED/)
  assert.match(output.args.prompt, /context\.md/)
})

test("subagent-context skips non-supported subagent type", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "generic-agent", prompt: "Do something" } }
  await plugin["tool.execute.before"](input, output)
  assert.equal(output.args.prompt, "Do something")
})

test("subagent-context skips when no active task", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-implement", prompt: "Do work" } }
  await plugin["tool.execute.before"](input, output)
  assert.equal(output.args.prompt, "Do work")
})

test("subagent-context skips when workflow root is missing", async () => {
  const root = makeRoot()
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-implement", prompt: "Do work" } }
  await plugin["tool.execute.before"](input, output)
  assert.equal(output.args.prompt, "Do work")
  assert.equal(existsSync(join(root, ".just-demand")), false)
})

test("subagent-context skips when tool is not Task", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Bash" }
  const output = { args: { subagent_type: "just-demand-implement", prompt: "Run this" } }
  await plugin["tool.execute.before"](input, output)
  assert.equal(output.args.prompt, "Run this")
})

// ---------------------------------------------------------------------------
// subagent-context: duplicate injection protection
// ---------------------------------------------------------------------------
test("subagent-context avoids duplicate injection when prompt already contains workflow context", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nSteps")
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  // Prompt already contains injection marker
  const existingContext = "# Injected Workflow Context\n\nExisting context"
  const output = { args: { subagent_type: "just-demand-implement", prompt: `${existingContext}\n\nDo the work` } }
  await plugin["tool.execute.before"](input, output)
  // Should not add duplicate injection
  assert.equal(output.args.prompt, `${existingContext}\n\nDo the work`)
  assert.doesNotMatch(output.args.prompt, /Active task: task-a/)
})
