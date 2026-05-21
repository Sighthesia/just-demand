import assert from "node:assert/strict"
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"

import {
  buildWorkflowBreadcrumb,
  getActiveTask,
  readJson,
  readTaskContext,
} from "../../.opencode/plugins/agent-workflow-lib.js"
import sessionStartFactory from "../../.opencode/plugins/agent-workflow-session-start.js"
import stateFactory from "../../.opencode/plugins/agent-workflow-state.js"
import subagentContextFactory from "../../.opencode/plugins/agent-workflow-subagent-context.js"

function makeRoot() {
  return mkdtempSync(join(tmpdir(), "agent-workflow-"))
}

function scaffoldWorkflow(root) {
  const base = join(root, ".agent-workflow")
  mkdirSync(join(base, "workspace"), { recursive: true })
  mkdirSync(join(base, "global"), { recursive: true })
  mkdirSync(join(base, "tasks", "active"), { recursive: true })
  writeFileSync(join(base, "workspace", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: "task-a" }))
  writeFileSync(join(base, "global", "rules.md"), "# Rules\n\nBe concise.")
  writeFileSync(join(base, "workspace", "facts.md"), "# Facts\n\nKey fact: system uses JSONL.")
  writeFileSync(join(base, "workspace", "decisions.md"), "# Decisions\n\nChose approach A.")
  writeFileSync(join(base, "workspace", "deferred_options.md"), "# Deferred\n\nOption X deferred.")
}

// ---------------------------------------------------------------------------
// lib: getActiveTask
// ---------------------------------------------------------------------------
test("getActiveTask reads current task from workspace state", () => {
  const root = makeRoot()
  mkdirSync(join(root, ".agent-workflow", "workspace"), { recursive: true })
  writeFileSync(join(root, ".agent-workflow", "workspace", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: "task-a" }))
  assert.equal(getActiveTask(root), "task-a")
})

test("getActiveTask returns null when state.json missing", () => {
  const root = makeRoot()
  mkdirSync(join(root, ".agent-workflow", "workspace"), { recursive: true })
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
// lib: buildWorkflowBreadcrumb
// ---------------------------------------------------------------------------
test("buildWorkflowBreadcrumb hides internal details", () => {
  const text = buildWorkflowBreadcrumb({ taskId: "task-a", status: "planning" })
  assert.match(text, /formal work item/i)
  assert.doesNotMatch(text, /repo_map/)
  assert.doesNotMatch(text, /JSONL/)
})

test("buildWorkflowBreadcrumb with no taskId returns empty string", () => {
  const text = buildWorkflowBreadcrumb({ taskId: null, status: "none" })
  assert.equal(text, "")
})

// ---------------------------------------------------------------------------
// lib: readTaskContext - implement
// ---------------------------------------------------------------------------
test("readTaskContext combines context and implement brief", () => {
  const root = makeRoot()
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nBuild")
  writeFileSync(join(taskDir, "verify.md"), "# Verify\nCheck")
  const context = readTaskContext(root, "task-a", "workflow-implement")
  assert.match(context, /# Context/)
  assert.match(context, /# Implement/)
  assert.doesNotMatch(context, /# Verify/)
})

// ---------------------------------------------------------------------------
// lib: readTaskContext - research
// ---------------------------------------------------------------------------
test("readTaskContext for workflow-research includes workspace facts", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const context = readTaskContext(root, "task-a", "workflow-research")
  assert.match(context, /# Context/)
  assert.match(context, /workspace facts/i)
  assert.match(context, /JSONL/)
})

test("readTaskContext for workflow-research includes research output path", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "research"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const context = readTaskContext(root, "task-a", "workflow-research")
  assert.match(context, /research output directory/i)
})

// ---------------------------------------------------------------------------
// lib: readTaskContext - docs
// ---------------------------------------------------------------------------
test("readTaskContext for workflow-docs includes workspace decisions", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const context = readTaskContext(root, "task-a", "workflow-docs")
  assert.match(context, /# Context/)
  assert.match(context, /workspace decisions/i)
  assert.match(context, /approach A/)
})

test("readTaskContext for workflow-docs includes deferred options", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const context = readTaskContext(root, "task-a", "workflow-docs")
  assert.match(context, /deferred options/i)
  assert.match(context, /Option X/)
})

// ---------------------------------------------------------------------------
// plugin factory: session-start returns hooks object
// ---------------------------------------------------------------------------
test("session-start factory returns hooks object with chat.message", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  assert.ok(plugin)
  assert.equal(typeof plugin["chat.message"], "function")
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
// session-start: no main-session bootstrap injection
// ---------------------------------------------------------------------------
test("session-start returns hook without injecting bootstrap", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Hello" }] }
  await plugin["chat.message"]({ sessionID: "s1" }, output)
  assert.equal(output.parts[0].text, "Hello")
})

test("session-start skips injection for workflow- agents", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Hello" }] }
  await plugin["chat.message"]({ agent: "workflow-implement", sessionID: "s-skip" }, output)
  assert.equal(output.parts[0].text, "Hello")
})

// ---------------------------------------------------------------------------
// state: injects breadcrumb into message
// ---------------------------------------------------------------------------
test("state injects breadcrumb with active task", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning" }))
  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Hello" }] }
  await plugin["chat.message"]({}, output)
  assert.match(output.parts[0].text, /Formal work item: task-a/)
  assert.match(output.parts[0].text, /Status: planning/)
  assert.match(output.parts[0].text, /Hello/)
})

test("state does not inject when no active task", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".agent-workflow", "workspace"), { recursive: true })
  writeFileSync(join(root, ".agent-workflow", "workspace", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Hello" }] }
  await plugin["chat.message"]({}, output)
  assert.equal(output.parts[0].text, "Hello")
})

test("state does not inject when active task is done", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "done" }))
  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Hello" }] }
  await plugin["chat.message"]({}, output)
  assert.equal(output.parts[0].text, "Hello")
})

// ---------------------------------------------------------------------------
// subagent-context: only injects for supported workflow subagents
// ---------------------------------------------------------------------------
test("subagent-context injects context for supported subagent type", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nSteps")
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "workflow-implement", prompt: "Do the work" } }
  await plugin["tool.execute.before"](input, output)
  assert.match(output.args.prompt, /Active task: task-a/)
  assert.match(output.args.prompt, /# Injected Workflow Context/)
  assert.match(output.args.prompt, /# Context/)
  assert.match(output.args.prompt, /# Implement/)
  assert.match(output.args.prompt, /# Requested Work/)
  assert.match(output.args.prompt, /Do the work/)
})

test("subagent-context skips non-supported subagent type", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
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
  mkdirSync(join(root, ".agent-workflow", "workspace"), { recursive: true })
  writeFileSync(join(root, ".agent-workflow", "workspace", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "workflow-implement", prompt: "Do work" } }
  await plugin["tool.execute.before"](input, output)
  assert.equal(output.args.prompt, "Do work")
})

test("subagent-context skips when tool is not Task", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Bash" }
  const output = { args: { subagent_type: "workflow-implement", prompt: "Run this" } }
  await plugin["tool.execute.before"](input, output)
  assert.equal(output.args.prompt, "Run this")
})
