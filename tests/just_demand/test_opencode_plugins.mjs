import assert from "node:assert/strict"
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"

import {
  buildExecutionGateError,
  buildReflectionGateError,
  consumeIntakeFallbackPending,
  clearToolGateSkipOverride,
  debugLog,
  getActiveTask,
  getExecutionGateState,
  getMissingRequiredContextFiles,
  getMissingExecutionGateFields,
  getReflectionGateState,
  getWorkflowSubagentName,
  impactsOverlap,
  isExternalGitRepoCommand,
  isIntakeFilePath,
  isProbablySafeGitCommand,
  isWorkflowControlCommand,
  getApplyPatchTargetPath,
  getLastSubagentDispatchTaskId,
  recordLastSubagentDispatchTaskId,
  listUnfinishedTasks,
  looksLikeIntakeOperation,
  markSubagentUnavailablePending,
  getWriteToolRule,
  hasUnquotedShellRedirection,
  looksLikeBashWriteCommand,
  readJson,
  readLatestFollowup,
  readReflectionContext,
  readTaskContext,
  detectActiveContractsForTask,
  detectContractTriggers,
  setToolGateSkipOverride,
} from "../../.opencode/plugins/just-demand-lib.js"
import sessionStartFactory from "../../.opencode/plugins/just-demand-session-start.js"
import stateFactory, {
  CONTROLLER_ACTION,
  CONTROLLER_PHASE,
  buildControllerDecision,
  injectWorkflowStateBanner,
  textLooksLikeCodeInvestigationIntent,
  textLooksLikeExplicitWorkflowSkip,
  textLooksLikeWorkflowEntryNarration,
} from "../../.opencode/plugins/just-demand-state.js"
import subagentContextFactory from "../../.opencode/plugins/just-demand-subagent-context.js"

function makeRoot() {
  return mkdtempSync(join(tmpdir(), "just-demand-"))
}

function scaffoldWorkflow(root) {
  const base = join(root, ".just-demand")
  mkdirSync(join(base, "state"), { recursive: true })
  mkdirSync(join(base, "state", "active"), { recursive: true })
  writeFileSync(join(base, "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: "task-a" }))
}

function readWorkflowFailureGoldenTranscript() {
  const fixturePath = join(process.cwd(), "tests/just_demand/fixtures/workflow_failure_golden.md")
  const turns = []

  for (const line of readFileSync(fixturePath, "utf8").split(/\r?\n/)) {
    const match = line.match(/^\s*\d+\s*\|\s*([a-z-]+)\s*\|\s*(.+?)\s*$/i)
    if (match) {
      turns.push({ kind: match[1], text: match[2] })
    }
  }

  return turns
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

test("debugLog is quiet by default, emits to stderr when enabled, and writes to file", () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand"), { recursive: true })
  const originalDebug = process.env.JUST_DEMAND_DEBUG
  const originalError = console.error
  const messages = []
  console.error = (message) => messages.push(String(message))

  try {
    delete process.env.JUST_DEMAND_DEBUG
    debugLog("quiet", { tool: "task" }, root)
    assert.deepEqual(messages, [])

    process.env.JUST_DEMAND_DEBUG = "1"
    debugLog("enabled", { tool: "task", args_keys: ["agent"] }, root)
    assert.equal(messages.length, 1)
    assert.match(messages[0], /^\[just-demand debug\] /)
    assert.match(messages[0], /"event":"enabled"/)
    assert.match(messages[0], /"args_keys":\["agent"\]/)

    const logPath = join(root, ".just-demand", "debug.log")
    assert.equal(existsSync(logPath), true)
    const content = readFileSync(logPath, "utf8")
    assert.match(content, /"event":"enabled"/)
    assert.match(content, /"args_keys":\["agent"\]/)
    assert.equal(content.endsWith("\n"), true)
  } finally {
    if (originalDebug === undefined) delete process.env.JUST_DEMAND_DEBUG
    else process.env.JUST_DEMAND_DEBUG = originalDebug
    console.error = originalError
  }
})

test("plugin bootstrap logs debug env and target directory when debug is enabled", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const originalDebug = process.env.JUST_DEMAND_DEBUG
  const originalDebugFull = process.env.JUST_DEMAND_DEBUG_PROMPT_FULL
  process.env.JUST_DEMAND_DEBUG = "1"
  process.env.JUST_DEMAND_DEBUG_PROMPT_FULL = "1"

  try {
    await stateFactory({ directory: root })
    await subagentContextFactory({ directory: root })
    await sessionStartFactory({ directory: root })

    const log = readFileSync(join(root, ".just-demand", "debug.log"), "utf8")
    assert.match(log, /"event":"plugin\.bootstrap"/)
    assert.match(log, /"plugin":"just-demand-state"/)
    assert.match(log, /"plugin":"just-demand-subagent-context"/)
    assert.match(log, /"plugin":"just-demand-session-start"/)
    assert.match(log, /"debug_enabled":"1"/)
    assert.match(log, /"debug_prompt_full_enabled":"1"/)
    assert.match(log, /"debug_prompts_dir":"\.just-demand\/debug-prompts"/)
  } finally {
    if (originalDebug === undefined) delete process.env.JUST_DEMAND_DEBUG
    else process.env.JUST_DEMAND_DEBUG = originalDebug
    if (originalDebugFull === undefined) delete process.env.JUST_DEMAND_DEBUG_PROMPT_FULL
    else process.env.JUST_DEMAND_DEBUG_PROMPT_FULL = originalDebugFull
  }
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
// lib: readTaskContext - coder
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
  const context = readTaskContext(root, "task-a", "just-demand-coder")
  assert.match(context, /# Context/)
  assert.match(context, /# Execution Context/)
  assert.match(context, /## Goal/)
  assert.match(context, /Saving shows a toast/)
  assert.match(context, /## Current Reality/)
  assert.match(context, /Saving does nothing/)
  assert.match(context, /Save flow only/)
  assert.match(context, /# Implement/)
  assert.match(context, /Remaining Open Questions/)
  assert.doesNotMatch(context, /# Verify/)
})

test("readTaskContext includes open questions for just-demand-tester", () => {
  const root = makeRoot()
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "verify.md"), "# Verify\nCheck")
  writeFileSync(join(taskDir, "open_questions.md"), "# Open Questions\n\n## Remaining Open Questions\n\n- Is analytics coverage required?\n")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { expected_behavior: "Event fires once.", actual_behavior: "Event fires twice.", reproduction: "Submit the form once.", scope: "Analytics submit path.", non_blocking_questions: ["Is analytics coverage required?"] } }))
  const context = readTaskContext(root, "task-a", "just-demand-tester")
  assert.match(context, /# Execution Context/)
  assert.match(context, /Event fires once/)
  assert.match(context, /Event fires twice/)
  assert.match(context, /Remaining Open Questions/)
  assert.match(context, /analytics coverage/)
})

test("readTaskContext injects compact execution artifact for coder and tester", () => {
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

  const coderContext = readTaskContext(root, "task-a", "just-demand-coder")
  const testerContext = readTaskContext(root, "task-a", "just-demand-tester")

  for (const context of [coderContext, testerContext]) {
    assert.match(context, /# Execution Context/)
    assert.match(context, /## Goal/)
    assert.match(context, /User can save settings confidently/)
    assert.match(context, /Chosen Approach/)
    assert.match(context, /Approach A: inline save/)
    assert.match(context, /Implementation Plan/)
    assert.match(context, /Validation/)
    assert.doesNotMatch(context, /Approach Options/)
    assert.doesNotMatch(context, /Background save/)
    assert.doesNotMatch(context, /Approval/)
    assert.doesNotMatch(context, /User approved Approach A/)
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
  const context = readTaskContext(root, "task-a", "just-demand-coder")
  assert.match(context, /Remaining Open Questions/)
  assert.match(context, /fallback question be shown/)
})

// ---------------------------------------------------------------------------
// lib: readTaskContext - research
// ---------------------------------------------------------------------------
test("readTaskContext for just-demand-researcher includes workspace facts", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "decisions.md"), "# Decisions\n\n## Decision: Prefer task-local notes\n\nTask history stays in the archive.\n")
  const context = readTaskContext(root, "task-a", "just-demand-researcher")
  assert.match(context, /# Context/)
  assert.match(context, /task history stays in the archive/i)
  assert.doesNotMatch(context, /workspace facts/i)
})

test("readTaskContext for just-demand-researcher avoids absolute research path leakage", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "research"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const context = readTaskContext(root, "task-a", "just-demand-researcher")
  assert.match(context, /research outputs/i)
  assert.match(context, /local research\//i)
  assert.equal(context.includes(root), false)
})

// ---------------------------------------------------------------------------
// lib: readTaskContext - advisor
// ---------------------------------------------------------------------------
test("readTaskContext for just-demand-advisor includes task decisions", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "decisions.md"), "# Decisions\n\n## Decision: Use archive-only history\n\nReusable lessons belong in skills.\n")
  const context = readTaskContext(root, "task-a", "just-demand-advisor")
  assert.match(context, /# Context/)
  assert.match(context, /reusable lessons belong in skills/i)
  assert.doesNotMatch(context, /workspace facts/i)
})

test("readTaskContext for just-demand-advisor keeps archive-only lessons in decisions", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "decisions.md"), "# Decisions\n\n## Decision: Keep task history in archive\n\nReusable lessons belong in skills.\n")
  const context = readTaskContext(root, "task-a", "just-demand-advisor")
  assert.match(context, /keep task history in archive/i)
  assert.match(context, /reusable lessons belong in skills/i)
  assert.doesNotMatch(context, /workspace facts/i)
})

// ---------------------------------------------------------------------------
// lib: readLatestFollowup
// ---------------------------------------------------------------------------
test("readLatestFollowup returns null when followups directory missing", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a" }))
  assert.equal(readLatestFollowup(root, "task-a"), null)
})

test("readLatestFollowup returns null when followups directory is empty", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a" }))
  assert.equal(readLatestFollowup(root, "task-a"), null)
})

test("readLatestFollowup returns the latest follow-up file content", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a" }))
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: followup-001\n\nCorrection 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: followup-002\n\nCorrection 2")
  const result = readLatestFollowup(root, "task-a")
  assert.match(result, /Correction 2/)
  assert.doesNotMatch(result, /Correction 1/)
})

test("readLatestFollowup ignores non-followup files in the directory", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a" }))
  writeFileSync(join(taskDir, "followups", "readme.txt"), "not a follow-up")
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: followup-001\n\nReal follow-up")
  const result = readLatestFollowup(root, "task-a")
  assert.match(result, /Real follow-up/)
})

// ---------------------------------------------------------------------------
// lib: readReflectionContext
// ---------------------------------------------------------------------------
test("readReflectionContext returns null when reflection.md missing", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a" }))
  assert.equal(readReflectionContext(root, "task-a"), null)
})

test("readReflectionContext returns reflection.md content when present", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a" }))
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\n\n## Root Cause\nMissing validation.\n\n## Pattern\nAlways validate inputs.\n")
  const result = readReflectionContext(root, "task-a")
  assert.match(result, /Missing validation/)
  assert.match(result, /Always validate/)
})

// ---------------------------------------------------------------------------
// lib: readTaskContext includes latest follow-up for coder and tester
// ---------------------------------------------------------------------------
test("readTaskContext for coder includes latest follow-up context when present", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nBuild")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { scope: "Feature only." } }))
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: followup-001\n\nCorrection 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: followup-002\n\nCorrection 2")
  const context = readTaskContext(root, "task-a", "just-demand-coder")
  assert.match(context, /# Latest Follow-Up Context/)
  assert.match(context, /Correction 2/)
  assert.doesNotMatch(context, /Correction 1/)
})

test("readTaskContext for tester includes latest follow-up context when present", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "verify.md"), "# Verify\nCheck all")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { scope: "Feature only." } }))
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: followup-001\n\nCorrection 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: followup-002\n\nCorrection 2")
  const context = readTaskContext(root, "task-a", "just-demand-tester")
  assert.match(context, /# Latest Follow-Up Context/)
  assert.match(context, /Correction 2/)
  assert.doesNotMatch(context, /Correction 1/)
})

test("readTaskContext latest-only behavior: only the most recent follow-up is injected", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nBuild")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { scope: "Feature only." } }))
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: followup-001\n\nFirst correction")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: followup-002\n\nSecond correction")
  writeFileSync(join(taskDir, "followups", "followup-003.md"), "# Follow-Up: followup-003\n\nThird correction")
  const context = readTaskContext(root, "task-a", "just-demand-coder")
  // Should contain the latest (third)
  assert.match(context, /Third correction/)
  // Should not contain older ones
  assert.doesNotMatch(context, /First correction/)
  assert.doesNotMatch(context, /Second correction/)
})

test("readTaskContext for advisor includes reflection context when present", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: analyze pattern")
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\n\n## Root Cause\nRace condition\n")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a" }))
  const context = readTaskContext(root, "task-a", "just-demand-advisor")
  assert.match(context, /# Reflection Context/)
  assert.match(context, /Race condition/)
})

test("readTaskContext for advisor does not include follow-up context", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: analyze")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a" }))
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: followup-001\n\nCorrection")
  const context = readTaskContext(root, "task-a", "just-demand-advisor")
  assert.doesNotMatch(context, /# Latest Follow-Up Context/)
})

test("readTaskContext for coder does not include reflection context", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nBuild")
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\n\n## Root Cause\nDesign issue\n")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { scope: "Feature only." } }))
  const context = readTaskContext(root, "task-a", "just-demand-coder")
  assert.doesNotMatch(context, /# Reflection Context/)
})

test("readTaskContext missing follow-up preserves existing behavior for coder", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nBuild")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", clarification: { scope: "Feature only." } }))
  const context = readTaskContext(root, "task-a", "just-demand-coder")
  assert.doesNotMatch(context, /# Latest Follow-Up Context/)
  assert.doesNotMatch(context, /# Reflection Context/)
  assert.match(context, /# Context/)
  assert.match(context, /# Implement/)
})

test("readTaskContext missing reflection preserves existing behavior for advisor", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: analyze")
  writeFileSync(join(taskDir, "decisions.md"), "# Decisions\n\n## Decision: Use option A\n\nApproved.\n")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a" }))
  const context = readTaskContext(root, "task-a", "just-demand-advisor")
  assert.doesNotMatch(context, /# Reflection Context/)
  assert.match(context, /# Context/)
  assert.match(context, /Use option A/)
})

test("getMissingRequiredContextFiles reports missing coder context files", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  const missing = getMissingRequiredContextFiles(root, "task-a", "just-demand-coder")
  assert.deepEqual(missing, ["implement.md"])
})

test("write tool rule table identifies write-like tools and ignores read-only bash", () => {
  assert.equal(getWriteToolRule("apply_patch", {})?.label, "apply_patch")
  assert.equal(getWriteToolRule("task", { subagent_type: "just-demand-coder" })?.label, "Task")
  assert.equal(getWriteToolRule("task", { agent: "just-demand-coder" })?.label, "Task")
  assert.equal(getWriteToolRule("task", { agent_name: "just-demand-tester" })?.label, "Task")
  assert.equal(getWriteToolRule("task", { subagent_type: "just-demand-researcher" })?.needsExecutionGate({ subagent_type: "just-demand-researcher" }), false)
  assert.equal(getWriteToolRule("bash", { command: "mkdir -p out && touch out/file.txt" })?.label, "bash")
  assert.equal(getWriteToolRule("bash", { command: "python3 -m unittest tests.just_demand.test_workflow_core -v" }), null)
  assert.equal(getWriteToolRule("bash", { command: "python3 - <<'PY'\nif raw > 0:\n    print(raw)\nPY" }), null)
  assert.equal(looksLikeBashWriteCommand("mkdir -p out && touch out/file.txt"), true)
  assert.equal(looksLikeBashWriteCommand("python3 -m unittest tests.just_demand.test_workflow_core -v"), false)
  assert.equal(looksLikeBashWriteCommand("python3 - <<'PY'\nif raw > 0:\n    print(raw)\nPY"), false)
  assert.equal(looksLikeBashWriteCommand("just-demand . create-intake \"Threshold\" \"greater-than > 100ms\" --session abc"), false)
  assert.equal(looksLikeBashWriteCommand("just-demand . list-active > /tmp/tasks.txt"), true)
  assert.equal(hasUnquotedShellRedirection("just-demand . create-intake \"Threshold\" \"greater-than > 100ms\" --session abc"), false)
  assert.equal(hasUnquotedShellRedirection("python3 - <<'PY'\nif raw > 0:\n    print(raw)\nPY"), false)
  assert.equal(hasUnquotedShellRedirection("just-demand . list-active > /tmp/tasks.txt"), true)
  assert.equal(buildExecutionGateError("bash", { reason: "no_formal_task" }), "Blocked bash: there is no formal task yet.")
  assert.equal(
    buildExecutionGateError("bash", { reason: "no_current_task_selected" }),
    "Blocked bash: unfinished formal tasks exist, but no current task is selected. Use just-demand . select-task <task-id> (or resume <task-id>) first.",
  )
  assert.equal(
    buildExecutionGateError("apply_patch", { reason: "task_not_ready", taskId: "task-a", missing: ["Scope", "Approval"] }),
    'Blocked apply_patch: active task task-a is not ready for execution yet. Missing or incomplete fields: Scope, Approval. Use `just-demand . update-clarification task-a --field <name>="<value>"` or `--from-file <path>` to fill pending fields.',
  )
})

// ---------------------------------------------------------------------------
// lib: workflow-control command detection
// ---------------------------------------------------------------------------
test("isWorkflowControlCommand detects workflow-control CLI commands", () => {
  assert.equal(isWorkflowControlCommand("just-demand . mark task-a done"), true)
  assert.equal(isWorkflowControlCommand("just-demand . select-task task-b"), true)
  assert.equal(isWorkflowControlCommand("just-demand . complete-verification task-a passed Done"), true)
  assert.equal(isWorkflowControlCommand("just-demand . update-clarification task-a --field scope=test"), true)
  assert.equal(isWorkflowControlCommand("just-demand . list-active"), true)
  assert.equal(isWorkflowControlCommand("just-demand . create-intake Title Request"), true)
  assert.equal(isWorkflowControlCommand("just-demand . promote intake-1 Title Goal --type design"), true)
  assert.equal(isWorkflowControlCommand("just-demand . checkpoint-commit task-a"), true)
  assert.equal(isWorkflowControlCommand("just-demand . --help"), true)
  assert.equal(isWorkflowControlCommand("just-demand . -h"), true)
  assert.equal(isWorkflowControlCommand("just-demand . archive task-a"), true)
  assert.equal(isWorkflowControlCommand("just-demand . cleanup task-a"), true)
  assert.equal(isWorkflowControlCommand("just-demand . status"), true)
  assert.equal(isWorkflowControlCommand("just-demand . resume task-a"), true)
  assert.equal(isWorkflowControlCommand("just-demand . create-session"), true)
})

test("isWorkflowControlCommand does not fire on non-control commands", () => {
  assert.equal(isWorkflowControlCommand("git commit -m fix"), false)
  assert.equal(isWorkflowControlCommand("mkdir -p out && touch out/file.txt"), false)
  assert.equal(isWorkflowControlCommand("python3 -m unittest tests"), false)
  assert.equal(isWorkflowControlCommand(""), false)
  assert.equal(isWorkflowControlCommand(null), false)
  assert.equal(isWorkflowControlCommand("just-demand . implement"), false)
})

test("isWorkflowControlCommand does not fire on composite commands with write patterns", () => {
  assert.equal(isWorkflowControlCommand("just-demand . mark task-a done && touch out/file.txt"), false)
  assert.equal(isWorkflowControlCommand("just-demand . mark task-a done > /tmp/out.txt"), false)
})

// ---------------------------------------------------------------------------
// lib: impactsOverlap
// ---------------------------------------------------------------------------
test("impactsOverlap detects overlapping impact scopes", () => {
  assert.equal(impactsOverlap(["src/api/"], ["src/api/users"]), true)
  assert.equal(impactsOverlap(["src/api/users"], ["src/api/"]), true)
  assert.equal(impactsOverlap(["docs/"], ["docs/readme.md"]), true)
  assert.equal(impactsOverlap(["src/api/", "docs/"], ["src/api/users"]), true)
  assert.equal(impactsOverlap(["src/api/"], ["src/web/"]), false)
  assert.equal(impactsOverlap(["src/api/"], ["tests/"]), false)
})

test("impactsOverlap handles empty and invalid inputs", () => {
  assert.equal(impactsOverlap([], ["src/api/"]), false)
  assert.equal(impactsOverlap(["src/api/"], []), false)
  assert.equal(impactsOverlap([], []), false)
  assert.equal(impactsOverlap(null, ["src/api/"]), false)
  assert.equal(impactsOverlap(["src/api/"], null), false)
  assert.equal(impactsOverlap(["src/api/"], [123]), false)
})

// ---------------------------------------------------------------------------
// lib: intake path detection
// ---------------------------------------------------------------------------
test("isIntakeFilePath detects intake file paths", () => {
  assert.equal(isIntakeFilePath(".just-demand/state/intake/some-intake.md"), true)
  assert.equal(isIntakeFilePath(".just-demand/state/intake/2026-06-21-my-intake.md"), true)
  assert.equal(isIntakeFilePath("/absolute/path/.just-demand/state/intake/file.md"), true)
  assert.equal(isIntakeFilePath("src/app.js"), false)
  assert.equal(isIntakeFilePath(".just-demand/state/active/task-a/task.json"), false)
  assert.equal(isIntakeFilePath(".just-demand/state/locks.json"), false)
  assert.equal(isIntakeFilePath(null), false)
  assert.equal(isIntakeFilePath(""), false)
})

test("getApplyPatchTargetPath extracts file path from standard patch format", () => {
  const args = { patchText: "*** Update File: .just-demand/state/intake/demo-intake.md\nSome content\n*** End Patch" }
  assert.equal(getApplyPatchTargetPath(args), ".just-demand/state/intake/demo-intake.md")
})

test("getApplyPatchTargetPath extracts file path from unified diff format", () => {
  const args = { patchText: "--- a/.just-demand/state/intake/demo-intake.md\n+++ b/.just-demand/state/intake/demo-intake.md\n@@ -1 +1 @@\n-old\n+new" }
  assert.equal(getApplyPatchTargetPath(args), ".just-demand/state/intake/demo-intake.md")
})

test("getApplyPatchTargetPath returns null for non-matching args", () => {
  assert.equal(getApplyPatchTargetPath({ patchText: "some random text" }), null)
  assert.equal(getApplyPatchTargetPath({}), null)
  assert.equal(getApplyPatchTargetPath(null), null)
})

test("getApplyPatchTargetPath handles path with diff content markers", () => {
  const args = { patchText: "*** Update File: .just-demand/state/intake/test-intake.md\n## Updates\n- Change scope\n*** End Patch" }
  assert.equal(getApplyPatchTargetPath(args), ".just-demand/state/intake/test-intake.md")
})

test("looksLikeIntakeOperation detects apply_patch targeting intake file", () => {
  const args = { patchText: "*** Update File: .just-demand/state/intake/my-intake.md\ncontent\n*** End Patch" }
  assert.equal(looksLikeIntakeOperation("apply_patch", args), true)
})

test("looksLikeIntakeOperation does not fire for non-intake apply_patch", () => {
  const args = { patchText: "*** Update File: src/app.js\ncontent\n*** End Patch" }
  assert.equal(looksLikeIntakeOperation("apply_patch", args), false)
})

test("looksLikeIntakeOperation detects bash redirection to intake file", () => {
  const args = { command: "echo '## Scope\nTesting' >> .just-demand/state/intake/demo.md" }
  assert.equal(looksLikeIntakeOperation("bash", args), true)
})

test("looksLikeIntakeOperation does not fire for bash commands with non-intake redirection", () => {
  const args = { command: "just-demand . list-active > /tmp/tasks.txt" }
  assert.equal(looksLikeIntakeOperation("bash", args), false)
})

test("looksLikeIntakeOperation returns false for non-matching tools", () => {
  assert.equal(looksLikeIntakeOperation("Task", { subagent_type: "just-demand-coder" }), false)
  assert.equal(looksLikeIntakeOperation("apply_patch", {}), false)
  assert.equal(looksLikeIntakeOperation("bash", {}), false)
})

test("getExecutionGateState distinguishes no formal task from no selected current task", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const activeDir = join(root, ".just-demand", "state", "active")
  mkdirSync(join(activeDir, "task-a"), { recursive: true })
  writeFileSync(join(activeDir, "task-a", "task.json"), JSON.stringify({ id: "task-a", title: "Task A", status: "paused" }))
  const gateState = getExecutionGateState(root)
  assert.equal(gateState.reason, "no_current_task_selected")
  assert.equal(gateState.taskId, null)
  assert.equal(gateState.activeTaskCount, 1)
  assert.deepEqual(gateState.activeTaskIds, ["task-a"])
  assert.deepEqual(gateState.overlappingTaskIds, [])
  assert.equal(gateState.nonOverlappingActiveTaskCount, 0)
})

test("getExecutionGateState includes impact overlap info when task is selected with overlapping other tasks", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const activeDir = join(root, ".just-demand", "state", "active")
  // Task A (selected) has impact: src/api/
  mkdirSync(join(activeDir, "task-a"), { recursive: true })
  writeFileSync(join(activeDir, "task-a", "task.json"), JSON.stringify({ id: "task-a", title: "Task A", status: "executing", impact: ["src/api/"] }))
  // Task B has overlapping impact: src/api/users
  mkdirSync(join(activeDir, "task-b"), { recursive: true })
  writeFileSync(join(activeDir, "task-b", "task.json"), JSON.stringify({ id: "task-b", title: "Task B", status: "planning", impact: ["src/api/users"] }))
  // Task C has non-overlapping impact: docs/
  mkdirSync(join(activeDir, "task-c"), { recursive: true })
  writeFileSync(join(activeDir, "task-c", "task.json"), JSON.stringify({ id: "task-c", title: "Task C", status: "planning", impact: ["docs/"] }))

  const gateState = getExecutionGateState(root)
  assert.equal(gateState.reason, "ready")
  assert.equal(gateState.taskId, "task-a")
  assert.equal(gateState.activeTaskCount, 3)
  assert.deepEqual(gateState.overlappingTaskIds, ["task-b"])
  assert.equal(gateState.nonOverlappingActiveTaskCount, 1)
})

test("getExecutionGateState reports no overlap when other tasks lack impact scope", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const activeDir = join(root, ".just-demand", "state", "active")
  mkdirSync(join(activeDir, "task-a"), { recursive: true })
  writeFileSync(join(activeDir, "task-a", "task.json"), JSON.stringify({ id: "task-a", title: "Task A", status: "executing", impact: ["src/api/"] }))
  mkdirSync(join(activeDir, "task-b"), { recursive: true })
  writeFileSync(join(activeDir, "task-b", "task.json"), JSON.stringify({ id: "task-b", title: "Task B", status: "planning" }))

  const gateState = getExecutionGateState(root)
  assert.equal(gateState.reason, "ready")
  assert.equal(gateState.taskId, "task-a")
  assert.deepEqual(gateState.overlappingTaskIds, [])
  assert.equal(gateState.nonOverlappingActiveTaskCount, 1)
})

test("workflow subagent name supports current and compatibility argument keys", () => {
  assert.equal(getWorkflowSubagentName({ subagent_type: "just-demand-coder" }), "just-demand-coder")
  assert.equal(getWorkflowSubagentName({ agent: "just-demand-tester" }), "just-demand-tester")
  assert.equal(getWorkflowSubagentName({ agentName: "just-demand-advisor" }), "just-demand-advisor")
  assert.equal(getWorkflowSubagentName({ agent_name: "just-demand-researcher" }), "just-demand-researcher")
  assert.equal(getWorkflowSubagentName({ agent: "general" }), "")
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

test("controller decision shape exposes phase action reason and rewrite", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", current_step: "clarify", verification_status: "not_started", assigned_subagents: [] }))

  const redirectDecision = buildControllerDecision("Please fix the bug in the API.", { activeTask: null, same_topic_turns: 0, subagent_unavailable_pending: false })
  assert.deepEqual(redirectDecision, {
    phase: CONTROLLER_PHASE.route,
    action: CONTROLLER_ACTION.block,
    reason_code: "workflow_entry_required",
    rewrite: { mode: "replace", preserve_original: true },
  })

  const remindDecision = buildControllerDecision("Please fix the bug in the API.", { activeTask: { id: "task-a", status: "planning" }, same_topic_turns: 0, subagent_unavailable_pending: false })
  assert.deepEqual(remindDecision, {
    phase: CONTROLLER_PHASE.clarify,
    action: CONTROLLER_ACTION.remind,
    reason_code: "clarify_hint",
    rewrite: { mode: "append" },
  })

  const selectDecision = buildControllerDecision("Please fix the bug in the API.", { activeTask: null, hasUnselectedActiveTasks: true, same_topic_turns: 0, subagent_unavailable_pending: false })
  assert.deepEqual(selectDecision, {
    phase: CONTROLLER_PHASE.route,
    action: CONTROLLER_ACTION.remind,
    reason_code: "select_task_hint",
    rewrite: { mode: "append" },
  })

  const executionDecision = buildControllerDecision("I will implement the feature and debug the bug inline.", {
    activeTask: { id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })
  assert.equal(executionDecision.phase, CONTROLLER_PHASE.execute)
  assert.equal(executionDecision.action, CONTROLLER_ACTION.block)
  assert.equal(executionDecision.reason_code, "execution_needed")
  assert.deepEqual(executionDecision.rewrite, { mode: "replace", preserve_original: true })
})

test("controller decision allows workflow-entry narration before select-task hint when active tasks exist", () => {
  const decision = buildControllerDecision(
    "I am creating the workflow entry now: create-intake first, then promote, then list-active.",
    { activeTask: null, hasUnselectedActiveTasks: true, same_topic_turns: 0, subagent_unavailable_pending: false },
  )

  assert.deepEqual(decision, {
    phase: CONTROLLER_PHASE.route,
    action: CONTROLLER_ACTION.allow,
    reason_code: "no_op",
    rewrite: null,
  })
})

test("approval words do not unlock execution without concrete workflow intent", () => {
  const samples = [
    "批准，可以分析一下",
    "同意，先看看",
    "approved, go ahead with the analysis",
  ]

  for (const sample of samples) {
    const decision = buildControllerDecision(sample, { activeTask: null, same_topic_turns: 0, subagent_unavailable_pending: false })
    assert.equal(decision.action, CONTROLLER_ACTION.allow)
    assert.equal(decision.reason_code, "no_op")
  }
})

test("workflow-entry narration detector allows command narration but not inline execution intent", () => {
  assert.equal(textLooksLikeWorkflowEntryNarration("I am creating the workflow entry now: create-intake first, then promote, then list-active."), true)
  assert.equal(textLooksLikeWorkflowEntryNarration("Run just-demand . --help so we can verify the help path."), true)
  assert.equal(textLooksLikeWorkflowEntryNarration("I will implement the fix inline in the main session, then maybe run create-intake."), false)
})

// ---------------------------------------------------------------------------
// explicit workflow skip detector
// ---------------------------------------------------------------------------
test("textLooksLikeExplicitWorkflowSkip detects English skip-workflow override", () => {
  const samples = [
    "I will skip the workflow and implement this inline.",
    "I'm bypassing the workflow for this change.",
    "Let me do a workflow bypass and fix this directly.",
    "This is an explicit workflow skip override.",
    "I'm explicitly skipping workflow and proceeding inline.",
    "I will proceed outside the workflow.",
    "Doing this without the workflow.",
    "workflow override for this simple fix.",
  ]
  for (const sample of samples) {
    assert.equal(textLooksLikeExplicitWorkflowSkip(sample), true, `Expected true for: "${sample}"`)
  }
})

test("textLooksLikeExplicitWorkflowSkip detects Chinese skip-workflow override", () => {
  const samples = [
    "我跳过工作流直接做这个修改。",
    "绕过工作流，我直接改代码。",
    "不经过工作流，我先修一下。",
  ]
  for (const sample of samples) {
    assert.equal(textLooksLikeExplicitWorkflowSkip(sample), true, `Expected true for: "${sample}"`)
  }
})

test("textLooksLikeExplicitWorkflowSkip does not fire on ordinary work phrases", () => {
  const samples = [
    "I will implement the feature inline.",
    "Let me fix this in the main session.",
    "I'll just finish this here.",
    "Please build a dashboard.",
    "I need to read through the code first.",
  ]
  for (const sample of samples) {
    assert.equal(textLooksLikeExplicitWorkflowSkip(sample), false, `Expected false for: "${sample}"`)
  }
})

// ---------------------------------------------------------------------------
// injectWorkflowStateBanner
// ---------------------------------------------------------------------------
test("injectWorkflowStateBanner appends active task banner", () => {
  const text = "Hello."
  const result = injectWorkflowStateBanner(text, "task-a", { id: "task-a", status: "executing", title: "My Task" }, { reason: "ready" })
  assert.match(result, /Hello\./)
  assert.match(result, /\[workflow-state\]/)
  assert.match(result, /task=task-a \(executing\)/)
  assert.match(result, /phase=execution/)
  assert.match(result, /title: My Task/)
  assert.match(result, /next: continue execution, dispatch subagent/)
  assert.match(result, /blocked: start, complete, skip workflow/)
})

test("injectWorkflowStateBanner keeps active task title compact", () => {
  const text = "Hello."
  const longTitle = "A".repeat(100)
  const result = injectWorkflowStateBanner(text, "task-a", { id: "task-a", status: "executing", title: longTitle }, { reason: "ready" })
  assert.match(result, /title: A{77}\.\.\./)
  assert.doesNotMatch(result, /A{100}/)
})

test("injectWorkflowStateBanner appends no-task breadcrumb with allowed and blocked next actions", () => {
  const text = "Hello."
  const result = injectWorkflowStateBanner(text, null, null, { reason: "no_formal_task", taskId: null, activeTaskCount: 0 })
  assert.match(result, /Hello\./)
  assert.match(result, /\[workflow-state\]/)
  assert.match(result, /task=none/)
  assert.match(result, /phase=no-task/)
  assert.match(result, /next: enter workflow via clarification\/intake, answer simple questions, or explicit skip workflow/)
  assert.match(result, /blocked: start, continue, complete/)
})

test("injectWorkflowStateBanner appends select-task banner when unfinished tasks exist", () => {
  const text = "Hello."
  const result = injectWorkflowStateBanner(text, null, null, { reason: "no_current_task_selected", taskId: null, activeTaskCount: 2 })
  assert.match(result, /Hello\./)
  assert.match(result, /\[workflow-state\]/)
  assert.match(result, /task=selection pending/)
  assert.match(result, /phase=no-task/)
  assert.match(result, /next: select-task\/resume before execution; direct answer only for non-work/)
  assert.match(result, /blocked: start, continue, complete/)
})

test("injectWorkflowStateBanner deduplicates when marker already present", () => {
  const text = "Hello.\n\n[workflow-state] No active task"
  const result = injectWorkflowStateBanner(text, null, null, { reason: "no_formal_task" })
  assert.equal(result, text)
})

// ---------------------------------------------------------------------------
// P1-1: impact-overlap conflict warning in workflow-state banner
// ---------------------------------------------------------------------------
test("injectWorkflowStateBanner includes overlap warning when overlap exists", () => {
  const text = "Hello."
  const result = injectWorkflowStateBanner(text, "task-a", { id: "task-a", status: "executing", title: "My Task" }, { reason: "ready", overlappingTaskIds: ["task-b", "task-c"] })
  assert.match(result, /Hello\./)
  assert.match(result, /\[workflow-state\]/)
  assert.match(result, /task=task-a \(executing\)/)
  assert.match(result, /overlap: task-b, task-c/)
})

test("injectWorkflowStateBanner does not include overlap warning when no overlap exists", () => {
  const text = "Hello."
  const result = injectWorkflowStateBanner(text, "task-a", { id: "task-a", status: "executing", title: "My Task" }, { reason: "ready", overlappingTaskIds: [] })
  assert.match(result, /Hello\./)
  assert.match(result, /\[workflow-state\]/)
  assert.doesNotMatch(result, /overlap/)
})

test("injectWorkflowStateBanner does not include overlap warning when overlappingTaskIds is absent", () => {
  const text = "Hello."
  const result = injectWorkflowStateBanner(text, "task-a", { id: "task-a", status: "executing", title: "My Task" }, { reason: "ready" })
  assert.match(result, /Hello\./)
  assert.match(result, /\[workflow-state\]/)
  assert.doesNotMatch(result, /overlap/)
})

// ---------------------------------------------------------------------------
// controller decision: explicit workflow skip override
// ---------------------------------------------------------------------------
test("controller decision allows explicit workflow skip override when no active task", () => {
  const decision = buildControllerDecision(
    "I will skip the workflow and implement this inline.",
    { activeTask: null, same_topic_turns: 0, subagent_unavailable_pending: false },
  )
  assert.equal(decision.phase, CONTROLLER_PHASE.route)
  assert.equal(decision.action, CONTROLLER_ACTION.allow)
  assert.equal(decision.reason_code, "workflow_skip_override")
  assert.deepEqual(decision.rewrite, null)
})

test("controller decision allows explicit workflow skip override with active task (bypasses execution_needed)", () => {
  const decision = buildControllerDecision(
    "I will skip the workflow and implement this inline.",
    {
      activeTask: { id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] },
      same_topic_turns: 0,
      subagent_unavailable_pending: false,
    },
  )
  assert.equal(decision.phase, CONTROLLER_PHASE.route)
  assert.equal(decision.action, CONTROLLER_ACTION.allow)
  assert.equal(decision.reason_code, "workflow_skip_override")
})

test("controller decision blocks lifecycle drift by workflow phase", () => {
  const noTask = buildControllerDecision("start the task", { activeTask: null, same_topic_turns: 0, subagent_unavailable_pending: false })
  assert.equal(noTask.action, CONTROLLER_ACTION.block)
  assert.equal(noTask.reason_code, "workflow_entry_required")

  const executionTask = buildControllerDecision("complete the task now", {
    activeTask: { id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })
  assert.equal(executionTask.action, CONTROLLER_ACTION.block)
  assert.equal(executionTask.reason_code, "execution_needed")

  const closeoutTask = buildControllerDecision("start another change", {
    activeTask: { id: "task-a", status: "done", current_step: "verify", verification_status: "passed", checkpoint_commit: { created: true } },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })
  assert.equal(closeoutTask.action, CONTROLLER_ACTION.block)
  assert.equal(closeoutTask.reason_code, "verification_closeout")
})

// ---------------------------------------------------------------------------
// code investigation intent detector
// ---------------------------------------------------------------------------
test("textLooksLikeCodeInvestigationIntent detects English code investigation proposals", () => {
  const samples = [
    "Let me inspect the codebase first.",
    "I need to read through the source files.",
    "Let me search the codebase for similar patterns.",
    "I should trace the implementation first.",
    "Let me look at the existing implementation.",
    "Investigate the codebase before proceeding.",
    "I will read the code to understand the structure.",
    "Let me look through the code to find the right place.",
  ]
  for (const sample of samples) {
    assert.equal(textLooksLikeCodeInvestigationIntent(sample), true, `Expected true for: "${sample}"`)
  }
})

test("textLooksLikeCodeInvestigationIntent detects Chinese code investigation proposals", () => {
  const samples = [
    "我先查看一下代码。",
    "让我检查一下源码。",
    "我需要搜索一下代码库。",
    "让我阅读一下代码文件。",
  ]
  for (const sample of samples) {
    assert.equal(textLooksLikeCodeInvestigationIntent(sample), true, `Expected true for: "${sample}"`)
  }
})

test("textLooksLikeCodeInvestigationIntent does not fire on neutral analysis or workflow entry narration", () => {
  const samples = [
    "Quick status: I compared the tradeoffs and the analysis still points to option A.",
    "Summary: I am just documenting the reasoning and next steps; no action is needed yet.",
    "I am reviewing the current state and explaining the tradeoffs, not asking for any action yet.",
    "I am creating the workflow entry now: create-intake first, then promote, then list-active.",
    "Run just-demand . --help so we can verify the documented help path.",
    "I am looking at this from a product perspective, not the code.",
  ]
  for (const sample of samples) {
    assert.equal(textLooksLikeCodeInvestigationIntent(sample), false, `Expected false for: "${sample}"`)
  }
})

test("controller decision blocks code investigation intent when no active task", () => {
  const englishSamples = [
    "Let me inspect the codebase first.",
    "I need to read through the source files.",
    "Let me search the codebase for similar patterns.",
    "I should trace the implementation first.",
    "Let me look at the existing implementation.",
    "Investigate the codebase before proceeding.",
  ]
  for (const sample of englishSamples) {
    const decision = buildControllerDecision(sample, { activeTask: null, same_topic_turns: 0, subagent_unavailable_pending: false })
    assert.equal(decision.phase, CONTROLLER_PHASE.route)
    assert.equal(decision.action, CONTROLLER_ACTION.block)
    assert.equal(decision.reason_code, "workflow_entry_required")
  }
})

test("controller decision blocks Chinese code investigation intent when no active task", () => {
  const decision = buildControllerDecision("我先查看一下代码，了解一下当前的实现。", {
    activeTask: null,
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })
  assert.equal(decision.phase, CONTROLLER_PHASE.route)
  assert.equal(decision.action, CONTROLLER_ACTION.block)
  assert.equal(decision.reason_code, "workflow_entry_required")
})

test("controller decision allows workflow entry narration that mentions code investigation", () => {
  // The text matches code investigation patterns, but the workflow entry narration
  // takes precedence because it contains workflow entry commands.
  const samples = [
    "I am creating the workflow entry: run create-intake, then promote, then the code work happens in the subagent.",
    "Let me create the intake first: create-intake, then promote, then inspect the codebase inside the formal task.",
  ]
  for (const sample of samples) {
    const decision = buildControllerDecision(sample, { activeTask: null, same_topic_turns: 0, subagent_unavailable_pending: false })
    assert.equal(decision.phase, CONTROLLER_PHASE.route)
    assert.equal(decision.action, CONTROLLER_ACTION.allow)
    assert.equal(decision.reason_code, "no_op")
  }
})

test("state blocks English code investigation intent when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "Let me inspect the codebase first to understand how it works.",
    "I need to read through the source files before implementing.",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }
    await plugin["chat.message"]({ sessionID: `code-investigation-en-${index}` }, output)

    assert.match(output.parts[0].text, /\[just-demand workflow entry required\]/i)
    assert.match(output.parts[0].text, /no formal task yet/i)
    assert.match(output.parts[0].text, /just-demand-intake/i)
    assert.match(output.parts[0].text, /Original response:/i)
    assert.match(output.parts[0].text, /> /)
    assert.notEqual(output.parts[0].text, sample)
  }
})

test("state blocks Chinese code investigation intent when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "我先查看一下代码，了解一下当前的实现。",
    "让我检查一下源码再决定怎么改。",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }
    await plugin["chat.message"]({ sessionID: `code-investigation-zh-${index}` }, output)

    assert.match(output.parts[0].text, /\[just-demand workflow entry required\]/i)
    assert.match(output.parts[0].text, /no formal task yet/i)
    assert.match(output.parts[0].text, /just-demand-intake/i)
  }
})

test("state allows neutral analysis that mentions code", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "I reviewed the code and the structure seems reasonable, but I am just reporting, not proposing to implement anything.",
    "Quick analysis: the current implementation path is straightforward and needs no change.",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }
    await plugin["chat.message"]({ sessionID: `neutral-code-${index}` }, output)

    assert.ok(output.parts[0].text.includes(sample), `Expected text to contain sample: "${sample}"`)
    assert.match(output.parts[0].text, /\[workflow-state\]/)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand workflow entry required\]/i)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/i)
  }
})

test("state allows workflow-entry narration when active tasks exist but no current task is selected", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state", "active", "task-a"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  writeFileSync(
    join(root, ".just-demand", "state", "active", "task-a", "task.json"),
    JSON.stringify({ id: "task-a", title: "Task A", status: "paused" }),
  )

  const plugin = await stateFactory({ directory: root })
  const sample = "I am creating the workflow entry now: create-intake first, then promote, then list-active."
  const output = { parts: [{ type: "text", text: sample }] }

  await plugin["chat.message"]({ sessionID: "workflow-entry-with-unselected-task" }, output)

  assert.ok(output.parts[0].text.includes(sample))
  assert.match(output.parts[0].text, /\[workflow-state\]/)
  assert.match(output.parts[0].text, /select-task/i)
  assert.doesNotMatch(output.parts[0].text, /workflow entry required/i)
  assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/i)
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
  const output = { system: ["You are a helpful assistant."] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "s1" }, output)
  assert.equal(output.system[0], "You are a helpful assistant.")
  assert.equal(output.system.length, 2)
  assert.match(output.system[1], /<JUST_DEMAND_REMINDER>/)
  assert.match(output.system[1], /Load using-just-demand first/i)
  assert.match(output.system[1], /socratic-clarification second/i)
  assert.match(output.system[1], /Use just-demand subagents proactively/i)
  assert.match(output.system[1], /Long-context work means broad code reading, 3\+ files/i)
  assert.doesNotMatch(output.system[1], /<workflow-state>/i)
})

test("session-start leaves existing workflow marker text untouched", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  const output = { system: ["Existing <JUST_DEMAND_WORKFLOW>content</JUST_DEMAND_WORKFLOW>"] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "s1" }, output)
  assert.equal(output.system.length, 2)
  assert.match(output.system[0], /<JUST_DEMAND_WORKFLOW>content<\/JUST_DEMAND_WORKFLOW>/)
  assert.match(output.system[1], /<JUST_DEMAND_REMINDER>/)
})

test("session-start preserves existing system prompt content", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  const output = { system: ["Original system prompt."] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "s1" }, output)
  assert.equal(output.system[0], "Original system prompt.")
  assert.match(output.system[1], /retry now or skip one turn/i)
})

test("session-start avoids duplicate reminder injection", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await sessionStartFactory({ directory: root })
  const output = { system: ["Base prompt.\n\n<JUST_DEMAND_REMINDER>already there</JUST_DEMAND_REMINDER>"] }
  await plugin["experimental.chat.system.transform"]({ sessionID: "s1" }, output)
  assert.deepEqual(output.system, ["Base prompt.\n\n<JUST_DEMAND_REMINDER>already there</JUST_DEMAND_REMINDER>"])
})

test("skill docs expose Question Strategy Layer and final-card guidance", () => {
  const root = process.cwd()
  const socraticSkill = readFileSync(join(root, ".opencode", "skills", "socratic-clarification", "SKILL.md"), "utf8")
  const intakeSkill = readFileSync(join(root, ".opencode", "skills", "just-demand-intake", "SKILL.md"), "utf8")
  const verificationSkill = readFileSync(join(root, ".opencode", "skills", "just-demand-verification", "SKILL.md"), "utf8")

  assert.match(socraticSkill, /Question Strategy Layer/)
  assert.match(socraticSkill, /visible_effect/i)
  assert.match(socraticSkill, /ordered_flow/i)
  assert.match(socraticSkill, /safety_boundary/i)
  assert.match(socraticSkill, /observability/i)
  assert.match(socraticSkill, /final card/i)

  assert.match(intakeSkill, /final-card form/i)
  assert.match(intakeSkill, /final-card language/i)

  assert.match(verificationSkill, /final-card form/i)
  assert.match(verificationSkill, /observed effect/i)
})

// ---------------------------------------------------------------------------
// state: per-turn reminders stay lightweight and narrow
// ---------------------------------------------------------------------------
test("state appends clarification reminder for concrete request turns", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning" }))
  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Please fix the bug in the API." }] }
  await plugin["chat.message"]({}, output)
  assert.match(output.parts[0].text, /^Please fix the bug in the API\./)
  assert.match(output.parts[0].text, /Load using-just-demand first/i)
  assert.match(output.parts[0].text, /socratic-clarification second/i)
  assert.match(output.parts[0].text, /Use just-demand subagents proactively/i)
  assert.match(output.parts[0].text, /\[just-demand reminder\]/)
  assert.match(output.parts[0].text, /\[workflow-state\].*task-a/)
})

test("state hard redirects concrete workflow work when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Please build a dashboard for alerts." }] }

  await plugin["chat.message"]({ sessionID: "no-active-task" }, output)

  assert.match(output.parts[0].text, /\[just-demand workflow entry required\]/i)
  assert.match(output.parts[0].text, /no formal task yet/i)
  assert.match(output.parts[0].text, /Enter workflow/i)
  assert.match(output.parts[0].text, /Three routes/i)
  assert.match(output.parts[0].text, /using-just-demand/i)
  assert.match(output.parts[0].text, /socratic-clarification/i)
  assert.match(output.parts[0].text, /just-demand-intake/i)
  assert.match(output.parts[0].text, /direct answer/i)
  assert.match(output.parts[0].text, /skip workflow/i)
  assert.match(output.parts[0].text, /Original response:/i)
  assert.match(output.parts[0].text, /> Please build a dashboard for alerts\./)
  assert.notEqual(output.parts[0].text, "Please build a dashboard for alerts.")
  assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/i)
})

test("state hard redirects Chinese concrete workflow work when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "将 bar 右键菜单从当前的弹出样式改为和 tray menu 一样的 expanded 效果。" }] }

  await plugin["chat.message"]({ sessionID: "zh-no-active-task" }, output)

  assert.match(output.parts[0].text, /\[just-demand workflow entry required\]/i)
  assert.match(output.parts[0].text, /no formal task yet/i)
  assert.match(output.parts[0].text, /just-demand-intake/i)
})

test("state reminds to select a current task when unfinished tasks exist", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "paused" }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Please build a dashboard for alerts." }] }

  await plugin["chat.message"]({ sessionID: "select-task-hint" }, output)

  assert.match(output.parts[0].text, /^Please build a dashboard for alerts\./)
  assert.match(output.parts[0].text, /\[just-demand reminder\]/i)
  assert.match(output.parts[0].text, /no current task is selected/i)
  assert.match(output.parts[0].text, /select-task <task-id>/i)
  assert.doesNotMatch(output.parts[0].text, /workflow entry required/i)
})

test("state allows workflow-entry narration when no active task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "I am creating the workflow entry now: create-intake first, then promote once the intake is clarified.",
    "Run just-demand . --help in the repo root so we can verify the documented help path.",
    "我现在只是说明 workflow entry 步骤：先 create-intake，再 promote，之后再看 list-active。",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }
    await plugin["chat.message"]({ sessionID: `workflow-entry-narration-${index}` }, output)
    assert.ok(output.parts[0].text.includes(sample))
    assert.match(output.parts[0].text, /\[workflow-state\]/)
    assert.doesNotMatch(output.parts[0].text, /workflow entry required/i)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/i)
  }
})

test("state chat.message skips safely when output parts are missing", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  const plugin = await stateFactory({ directory: root })

  await assert.doesNotReject(plugin["chat.message"]({ sessionID: "missing-parts" }, {}))
})

test("state blocks apply_patch when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch: there is no formal task yet\./,
  )
})

test("state allows apply_patch targeting intake file without formal task", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  const output = { args: { patchText: "*** Update File: .just-demand/state/intake/demo-intake.md\n## Scope\nClarify the feature boundary.\n*** End Patch" } }
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, output),
  )
})

test("state allows apply_patch targeting intake file when active tasks exist but no current task selected", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "paused", clarification: { scope: "Scoped" } }))
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })

  const plugin = await stateFactory({ directory: root })
  const output = { args: { patchText: "*** Update File: .just-demand/state/intake/demo-intake.md\n## Scope\nClarify the feature boundary.\n*** End Patch" } }
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, output),
  )
})

test("state still blocks apply_patch on non-intake file when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: src/app.js\n*** End Patch" } }),
    /Blocked apply_patch: there is no formal task yet\./,
  )
})

test("state still blocks bash redirect to non-intake file when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "just-demand . list-active > /tmp/tasks.txt" } }),
    /Blocked bash: there is no formal task yet\./,
  )
})

test("state blocks apply_patch when unfinished tasks exist but no current task is selected", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "paused", clarification: { scope: "Scoped" } }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch: unfinished formal tasks exist, but no current task is selected\./,
  )
})

test("state blocks apply_patch when active task is not ready for execution (past planning)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "executing", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch: active task task-a is not ready for execution yet\./,
  )
})

test("state blocks coder task dispatch when active task is not ready for execution (past planning)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "executing", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "Task" }, { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }),
    /Blocked Task: active task task-a is not ready for execution yet\./,
  )
})

test("state blocks workflow task dispatch with real agent argument key when active task is not ready (past planning)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "executing", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "Task" }, { args: { agent: "just-demand-coder", prompt: "Do the work" } }),
    /Blocked Task: active task task-a is not ready for execution yet\./,
  )
})

test("state allows dispatch when task is ready even in non-standard status (dispatch exemption)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  // Task is in "paused" status (not in WRITE_ALLOWED_STATUSES) but IS ready (clarification complete)
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "paused",
    clarification: {
      scope: "Feature scope",
      final_expected_effect: "Feature works",
      chosen_approach: "Approach A",
      final_implementation_plan: "1. Build\n2. Test",
      approval: "Approved",
    },
  }))

  const plugin = await stateFactory({ directory: root })

  // Dispatch should succeed even though status is "paused"
  const output = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "Task" }, output),
  )
})

test("state still blocks apply_patch when task status is paused even if task is ready (no dispatch exemption for writes)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "paused",
    clarification: {
      scope: "Feature scope",
      final_expected_effect: "Feature works",
      chosen_approach: "Approach A",
      final_implementation_plan: "1. Build\n2. Test",
      approval: "Approved",
    },
  }))

  const plugin = await stateFactory({ directory: root })

  // apply_patch should still be blocked because it is not a dispatch
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch: active task task-a is in status 'paused', which does not allow writes\./,
  )
})

test("workflow-control bash command passes through gate when task is not ready", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "executing",
    clarification: { scope: "" },
  }))

  const plugin = await stateFactory({ directory: root })

  // Workflow-control command passes despite task not being ready
  const output = { args: { command: "just-demand . mark task-a done" } }
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "bash" }, output),
  )
})

test("workflow-control bash command passes through gate when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })

  // create-intake should work without a formal task
  const output = { args: { command: "just-demand . create-intake Test Title Request" } }
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "bash" }, output),
  )
})

test("write-like bash with workflow-control prefix in composite command still blocked when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })

  // Composite command with write pattern still blocked
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "just-demand . mark task-a done && touch out/file.txt" } }),
    /Blocked bash: there is no formal task yet\./,
  )
})

test("list-active without shell redirection passes through gate when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })

  // list-active should work without a formal task
  const output = { args: { command: "just-demand . list-active" } }
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "bash" }, output),
  )
})

test("state blocks write-like bash commands when active task is not ready for execution (past planning)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "executing", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
    /Blocked bash: active task task-a is not ready for execution yet\./,
  )
})

test("state allows read-only bash commands through the write gate", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "planning", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  const output = { args: { command: "python3 -m unittest tests.just_demand.test_workflow_core -v" } }
  await plugin["tool.execute.before"]({ tool: "bash" }, output)
  assert.equal(output.args.command, "python3 -m unittest tests.just_demand.test_workflow_core -v")
})

test("state allows read-only bash heredoc analysis through the write gate", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "paused", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  const command = "python3 - <<'PY'\nif raw > 0:\n    print(raw)\nPY"
  const output = { args: { command } }

  await plugin["tool.execute.before"]({ tool: "bash" }, output)
  assert.equal(output.args.command, command)
})

test("state allows quoted greater-than inside create-intake arguments", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "planning", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  const output = { args: { command: "just-demand . create-intake \"Redirect threshold\" \"Investigate p95 > 100ms\" --session test-session" } }
  await plugin["tool.execute.before"]({ tool: "bash" }, output)
  assert.equal(output.args.command, "just-demand . create-intake \"Redirect threshold\" \"Investigate p95 > 100ms\" --session test-session")
})

test("state still blocks real shell redirection outside quotes (past planning)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "executing", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "just-demand . list-active > /tmp/tasks.txt" } }),
    /Blocked bash: active task task-a is not ready for execution yet\./,
  )
})

test("state stays quiet for neutral turns", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Hello" }] }
  await plugin["chat.message"]({}, output)
  assert.match(output.parts[0].text, /^Hello/)
  assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/)
})

test("state stays quiet for ordinary analysis and status-summary language", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", current_step: "clarify", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "Quick status: I compared the tradeoffs and the analysis still points to option A.",
    "Summary: I am just documenting the reasoning and next steps; no action is needed yet.",
    "I am reviewing the current state and explaining the tradeoffs, not asking for any action yet.",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }

    await plugin["chat.message"]({ sessionID: `neutral-analysis-${index}` }, output)

    assert.ok(output.parts[0].text.includes(sample))
    assert.match(output.parts[0].text, /\[workflow-state\]/)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/)
    assert.doesNotMatch(output.parts[0].text, /execution work that should run through a just-demand-\* workflow subagent/i)
    assert.doesNotMatch(output.parts[0].text, /complete-verification/i)
    assert.doesNotMatch(output.parts[0].text, /Preparing final response|Thought|Decision card|Validation card/i)
  }
})

test("subagent skip applies only to the current turn and later code edits block again", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const first = { parts: [{ type: "text", text: "Continue with the main session." }] }
  const second = { parts: [{ type: "text", text: "I will inspect the codebase and implement the fix inline." }] }

  markSubagentUnavailablePending(root, "skip-scope")
  await plugin["chat.message"]({ sessionID: "skip-scope" }, first)
  await plugin["chat.message"]({ sessionID: "skip-scope" }, second)

  assert.match(first.parts[0].text, /retry now, or skip one turn/i)
  assert.match(first.parts[0].text, /\[workflow-state\]/)
  assert.match(second.parts[0].text, /\[just-demand execution blocked\]/i)
  assert.match(second.parts[0].text, /must run through a just-demand-\* workflow subagent/i)
})

test("workflow failure golden transcript keeps approval, skip scope, pivot gate, and closeout gate intact", async () => {
  const [analysisTurn, approvalTurn, skipTurn, pivotTurn, closeoutTurn] = readWorkflowFailureGoldenTranscript()

  assert.deepEqual(
    [analysisTurn.kind, approvalTurn.kind, skipTurn.kind, pivotTurn.kind, closeoutTurn.kind],
    ["analysis", "approval", "skip", "pivot", "closeout"],
  )

  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })

  const analysis = { parts: [{ type: "text", text: analysisTurn.text }] }
  await plugin["chat.message"]({ sessionID: "golden-transcript" }, analysis)
  assert.ok(analysis.parts[0].text.includes(analysisTurn.text))
  assert.match(analysis.parts[0].text, /\[workflow-state\]/)
  assert.doesNotMatch(analysis.parts[0].text, /\[just-demand execution blocked\]/i)
  assert.doesNotMatch(analysis.parts[0].text, /closeout blocked/i)

  const approvalDecision = buildControllerDecision(approvalTurn.text, {
    activeTask: { id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })
  assert.equal(approvalDecision.action, CONTROLLER_ACTION.allow)
  assert.equal(approvalDecision.reason_code, "no_op")

  markSubagentUnavailablePending(root, "golden-transcript")
  const skip = { parts: [{ type: "text", text: skipTurn.text }] }
  await plugin["chat.message"]({ sessionID: "golden-transcript" }, skip)
  assert.match(skip.parts[0].text, /retry now, or skip one turn/i)
  assert.match(skip.parts[0].text, /subagent was unavailable/i)

  const pivot = { parts: [{ type: "text", text: pivotTurn.text }] }
  await plugin["chat.message"]({ sessionID: "golden-transcript" }, pivot)
  assert.match(pivot.parts[0].text, /\[just-demand execution blocked\]/i)
  assert.match(pivot.parts[0].text, /must run through a just-demand-\* workflow subagent/i)
  assert.doesNotMatch(pivot.parts[0].text, /retry now, or skip one turn/i)

  const closeout = { parts: [{ type: "text", text: closeoutTurn.text }] }
  await plugin["chat.message"]({ sessionID: "golden-transcript" }, closeout)
  assert.match(closeout.parts[0].text, /closeout blocked/i)
  assert.match(closeout.parts[0].text, /complete-verification/i)
})

test("transcript drift keeps start execute complete phrasing pinned to workflow state", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const turns = [
    { sessionID: "drift-a", text: "please start the task" },
    { sessionID: "drift-b", text: "please continue execution" },
    { sessionID: "drift-c", text: "please complete the task" },
  ]

  for (const turn of turns) {
    const output = { parts: [{ type: "text", text: turn.text }] }
    await plugin["chat.message"]({ sessionID: turn.sessionID }, output)
    assert.match(output.parts[0].text, /\[workflow-state\]/)
    assert.match(output.parts[0].text, /phase=execution/)
  }

  assert.match(turns[0].text, /start/)
})

test("analysis-to-implementation pivot re-enters execution gating", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "After the analysis, I will implement the fix inline." }] }

  await plugin["chat.message"]({ sessionID: "pivot-reset" }, output)

  assert.match(output.parts[0].text, /\[just-demand execution blocked\]/i)
  assert.match(output.parts[0].text, /must run through a just-demand-\* workflow subagent/i)
})

test("completion claims are blocked until verification closeout", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "This is done and ready to ship." }] }

  await plugin["chat.message"]({ sessionID: "completion-block" }, output)

  assert.match(output.parts[0].text, /closeout blocked/i)
  assert.match(output.parts[0].text, /workflow closure is still incomplete/i)
  assert.match(output.parts[0].text, /complete-verification/i)
})

test("state appends premise-check reminder for narrow frame-check turns and deduplicates it", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  const plugin = await stateFactory({ directory: root })

  const first = { parts: [{ type: "text", text: "What if the premise is off?" }] }
  const second = { parts: [{ type: "text", text: "What if the premise is off?" }] }

  await plugin["chat.message"]({ sessionID: "premise-check" }, first)
  await plugin["chat.message"]({ sessionID: "premise-check" }, second)

  assert.match(first.parts[0].text, /\[just-demand reminder\]/)
  assert.match(first.parts[0].text, /Check whether the current frame is the right problem model/i)
  assert.match(first.parts[0].text, /Do not keep tuning a weak premise/i)
  assert.ok(second.parts[0].text.includes("What if the premise is off?"))
  assert.match(second.parts[0].text, /\[workflow-state\]/)
})

test("contract trigger detection covers visible effect, ordered flow, safety, and observability", () => {
  assert.ok(detectContractTriggers("Animate launcher rows with stagger fade").has("visible_effect"))
  assert.ok(detectContractTriggers("按顺序执行迁移步骤").has("ordered_flow"))
  assert.ok(detectContractTriggers("Delete files with rollback safety").has("safety_boundary"))
  assert.ok(detectContractTriggers("Add logging and metrics").has("observability"))
  assert.equal(detectContractTriggers("Update the README wording").size, 0)
})

test("execution gate requires visible lifecycle and safety boundary fields", () => {
  const visibleTask = {
    id: "task-ui",
    title: "Animate launcher rows",
    goal: "Make the list reveal feel smooth.",
    type: "implementation",
    clarification: {
      scope: "Launcher rows only.",
      blocking_questions: [],
      final_expected_effect: "Rows reveal with the launcher.",
      chosen_approach: "Staggered fade and slide.",
      final_implementation_plan: "1. Clarify lifecycle\n2. Implement animation",
      approval: "Approved.",
      needs_ui_visible_lifecycle_clarification: true,
    },
  }

  assert.ok(detectActiveContractsForTask(visibleTask).has("visible_effect"))
  const visibleMissing = getMissingExecutionGateFields(visibleTask)
  assert.ok(visibleMissing.includes("Opening"))
  assert.ok(visibleMissing.includes("During Transition"))
  assert.ok(visibleMissing.includes("After Open"))
  assert.ok(visibleMissing.includes("Interrupt Behavior"))
  assert.ok(visibleMissing.includes("Anti-Outcomes"))

  const safetyTask = {
    id: "task-safety",
    title: "Delete old backups safely",
    goal: "Run a destructive cleanup with rollback safety.",
    type: "implementation",
    clarification: {
      scope: "Backup cleanup only.",
      blocking_questions: [],
      final_expected_effect: "Old backups are cleaned safely.",
      chosen_approach: "Dry-run then delete.",
      final_implementation_plan: "1. List targets\n2. Delete approved targets",
      approval: "Approved.",
      active_contracts: ["safety_boundary"],
    },
  }

  assert.ok(detectActiveContractsForTask(safetyTask).has("safety_boundary"))
  assert.ok(getMissingExecutionGateFields(safetyTask).includes("Anti-Outcomes"))
})

test("execution gate error points contract tasks to recovery fields", () => {
  const error = buildExecutionGateError("apply_patch", { reason: "task_not_ready", taskId: "task-ui", missing: ["Opening", "Anti-Outcomes"] })
  assert.match(error, /Missing or incomplete fields: Opening, Anti-Outcomes/i)
  assert.match(error, /update-clarification task-ui/i)
})

test("state blocks obvious execution-needed replies on unrouted active tasks", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "I will implement the feature and debug the bug inline.",
    "I'll just finish this in the main session.",
    "先说明一下：I will implement the fix and debug the bug inline, 然后我再整理结果。",
    "中文说明一下，we should build this in the main session and keep the rest for later.",
    "我打算直接在主会话里实现这个修复并调试一下。",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }

    await plugin["chat.message"]({ sessionID: `execution-${index}` }, output)

    assert.match(output.parts[0].text, /\[just-demand execution blocked\]/i)
    assert.match(output.parts[0].text, /must run through a just-demand-\* workflow subagent/i)
    assert.match(output.parts[0].text, /Dispatch the supported just-demand-\* subagent/i)
    assert.match(output.parts[0].text, /skip workflow/i)
    assert.match(output.parts[0].text, /Original response:/i)
    assert.match(output.parts[0].text, /> /)
    assert.notEqual(output.parts[0].text, sample)
  }
})

test("state blocks additional common execution phrasings on unrouted active tasks", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    // "let me/us" patterns
    "Let me implement the fix now.",
    "Let me build the feature inline.",
    "Let me add the new endpoint here.",
    "Let me fix the regression directly.",
    "Let me debug the issue in the main session.",
    "Let me update the configuration.",
    // "I'll" patterns
    "I'll implement the feature.",
    "I'll fix the bug directly.",
    "I'll build the new component.",
    "I'll debug the issue inline.",
    // "I'm going to" patterns
    "I'm going to implement the fix now.",
    "I'm going to build this feature inline.",
    "I'm going to fix the broken test.",
    // Chinese "让我/我来" patterns
    "让我来实现这个修复。",
    "我来调试这个问题。",
    "我们来添加这个功能。",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }

    await plugin["chat.message"]({ sessionID: `broad-execution-${index}` }, output)

    assert.match(output.parts[0].text, /\[just-demand execution blocked\]/i, `Expected block for: "${sample}"`)
    assert.match(output.parts[0].text, /must run through a just-demand-\* workflow subagent/i)
    assert.match(output.parts[0].text, /skip workflow/i)
    assert.match(output.parts[0].text, /Original response:/i)
    assert.notEqual(output.parts[0].text, sample)
  }
})

test("state blocks code investigation intent inside active execution task without subagents", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "Let me inspect the codebase to understand the structure.",
    "I need to read through the source files before proceeding.",
    "Let me trace the implementation to find the bug.",
    "Let me search the codebase for similar patterns.",
    "Let me look at the existing implementation.",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }
    await plugin["chat.message"]({ sessionID: `code-investigation-exec-${index}` }, output)

    assert.match(output.parts[0].text, /\[just-demand execution blocked\]/i, `Expected block for: "${sample}"`)
    assert.match(output.parts[0].text, /must run through a just-demand-\* workflow subagent/i)
  }
})

test("state allows code investigation during planning (non-execution) status inside active task", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", current_step: "clarify", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Let me inspect the codebase to understand the current structure." }] }

  await plugin["chat.message"]({}, output)

  assert.ok(output.parts[0].text.includes("Let me inspect the codebase to understand the current structure."))
  assert.match(output.parts[0].text, /\[workflow-state\]/)
  assert.doesNotMatch(output.parts[0].text, /\[just-demand execution blocked\]/i)
  assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/i)
})

test("state allows neutral analysis with code investigation language inside active execution task", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "I am inspecting the code, but just reviewing and not proposing to implement anything.",
    "Quick review: I traced the implementation and the structure seems reasonable with no action needed.",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }
    await plugin["chat.message"]({ sessionID: `neutral-investigation-${index}` }, output)

    assert.ok(output.parts[0].text.includes(sample))
    assert.match(output.parts[0].text, /\[workflow-state\]/)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand execution blocked\]/i)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/i)
  }
})

test("explicit workflow skip overrides execution block for new patterns and code investigation", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "I will skip the workflow and implement the fix directly.",
    "I'm bypassing the workflow and inspecting the codebase now.",
    "workflow override — let me implement the change inline.",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }

    await plugin["chat.message"]({ sessionID: `skip-override-broad-${index}` }, output)

    assert.doesNotMatch(output.parts[0].text, /\[just-demand execution blocked\]/i, `Expected no block for: "${sample}"`)
    assert.doesNotMatch(output.parts[0].text, /must run through a just-demand-\* workflow subagent/i)
    assert.match(output.parts[0].text, /\[workflow-state\]/)
  }
})

test("state still blocks execution-needed text after workflow subagents were previously assigned", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", assigned_subagents: ["just-demand-coder"] }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "I will implement the feature and debug the bug inline." }] }

  await plugin["chat.message"]({}, output)

  assert.match(output.parts[0].text, /\[just-demand execution blocked\]/i)
  assert.match(output.parts[0].text, /must run through a just-demand-\* workflow subagent/i)
})

test("controller decision still blocks execution intent after workflow subagents were previously assigned", () => {
  const decision = buildControllerDecision("I will implement the feature and debug the bug inline.", {
    activeTask: {
      id: "task-a",
      status: "executing",
      current_step: "execute",
      verification_status: "not_started",
      assigned_subagents: ["just-demand-coder"],
    },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })

  assert.equal(decision.phase, CONTROLLER_PHASE.execute)
  assert.equal(decision.action, CONTROLLER_ACTION.block)
  assert.equal(decision.reason_code, "execution_needed")
  assert.deepEqual(decision.rewrite, { mode: "replace", preserve_original: true })
})

// ---------------------------------------------------------------------------
// P1-2: Soften execution gate for clarify/design steps
// ---------------------------------------------------------------------------
test("controller decision reminds (not blocks) execution intent when current_step is clarify", () => {
  const decision = buildControllerDecision("I will implement the fix now.", {
    activeTask: {
      id: "task-a",
      status: "executing",
      current_step: "clarify",
      verification_status: "not_started",
      assigned_subagents: [],
    },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })

  assert.equal(decision.phase, CONTROLLER_PHASE.execute)
  assert.equal(decision.action, CONTROLLER_ACTION.remind)
  assert.equal(decision.reason_code, "soft_execution_hint")
  assert.deepEqual(decision.rewrite, { mode: "append" })
})

test("controller decision reminds (not blocks) execution intent when current_step is design", () => {
  const decision = buildControllerDecision("Let me build the new feature.", {
    activeTask: {
      id: "task-a",
      status: "executing",
      current_step: "design",
      verification_status: "not_started",
      assigned_subagents: [],
    },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })

  assert.equal(decision.phase, CONTROLLER_PHASE.execute)
  assert.equal(decision.action, CONTROLLER_ACTION.remind)
  assert.equal(decision.reason_code, "soft_execution_hint")
  assert.deepEqual(decision.rewrite, { mode: "append" })
})

test("controller decision reminds (not blocks) code investigation intent when current_step is clarify", () => {
  const decision = buildControllerDecision("Let me inspect the codebase first.", {
    activeTask: {
      id: "task-a",
      status: "executing",
      current_step: "clarify",
      verification_status: "not_started",
      assigned_subagents: [],
    },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })

  assert.equal(decision.phase, CONTROLLER_PHASE.execute)
  assert.equal(decision.action, CONTROLLER_ACTION.remind)
  assert.equal(decision.reason_code, "soft_execution_hint")
  assert.deepEqual(decision.rewrite, { mode: "append" })
})

test("controller decision still blocks execution intent when current_step is execute (no soften)", () => {
  const decision = buildControllerDecision("I will implement the feature inline.", {
    activeTask: {
      id: "task-a",
      status: "executing",
      current_step: "execute",
      verification_status: "not_started",
      assigned_subagents: [],
    },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })

  assert.equal(decision.phase, CONTROLLER_PHASE.execute)
  assert.equal(decision.action, CONTROLLER_ACTION.block)
  assert.equal(decision.reason_code, "execution_needed")
  assert.deepEqual(decision.rewrite, { mode: "replace", preserve_original: true })
})

test("controller decision still blocks code investigation intent when current_step is execute (no soften)", () => {
  const decision = buildControllerDecision("Let me inspect the codebase to find the bug.", {
    activeTask: {
      id: "task-a",
      status: "executing",
      current_step: "execute",
      verification_status: "not_started",
      assigned_subagents: [],
    },
    same_topic_turns: 0,
    subagent_unavailable_pending: false,
  })

  assert.equal(decision.phase, CONTROLLER_PHASE.execute)
  assert.equal(decision.action, CONTROLLER_ACTION.block)
  assert.equal(decision.reason_code, "execution_needed")
  assert.deepEqual(decision.rewrite, { mode: "replace", preserve_original: true })
})

test("state reminds (not blocks) execution intent in clarify step", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "clarify", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "I will implement the feature now." }] }

  await plugin["chat.message"]({ sessionID: "clarify-reminder" }, output)

  assert.match(output.parts[0].text, /\[just-demand reminder\]/)
  assert.match(output.parts[0].text, /clarify\/design phase/)
  assert.match(output.parts[0].text, /\[workflow-state\]/)
  assert.doesNotMatch(output.parts[0].text, /\[just-demand execution blocked\]/i)
})

test("state still blocks execution intent in execute step (P0 safety preserved)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "I will implement the feature now." }] }

  await plugin["chat.message"]({ sessionID: "execute-block" }, output)

  assert.match(output.parts[0].text, /\[just-demand execution blocked\]/i)
  assert.match(output.parts[0].text, /must run through a just-demand-\* workflow subagent/i)
})

test("state blocks obvious verification closeout claims until complete-verification", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "done", current_step: "verify", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "This is done and ready to ship.",
    "这边已经 done 了，我觉得 we can close this out now.",
    "中文说明：it is ready to ship, so please run the closeout step before concluding.",
    "这个已经做完了，可以收尾了。",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }

    await plugin["chat.message"]({ sessionID: `verification-${index}` }, output)

    assert.match(output.parts[0].text, /closeout blocked/i)
    assert.match(output.parts[0].text, /This reads like a completion claim/i)
    assert.match(output.parts[0].text, /complete-verification/i)
    assert.match(output.parts[0].text, /Original response:/i)
    assert.match(output.parts[0].text, /> /)
    assert.notEqual(output.parts[0].text, sample)
  }
})

test("state leaves analysis and near-miss closeout replies unchanged", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "I am reviewing the tradeoffs and the analysis still points to option A.",
    "This looks ready, but I still want to confirm the scope first.",
    "I think it is in a good place, but not yet because one more check is needed.",
    "We should wrap this up, but not yet because we still need to confirm the open question.",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }

    await plugin["chat.message"]({ sessionID: `closeout-safe-${index}` }, output)

    assert.ok(output.parts[0].text.includes(sample))
    assert.match(output.parts[0].text, /\[workflow-state\]/)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand closeout blocked\]/i)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/i)
    assert.doesNotMatch(output.parts[0].text, /complete-verification/i)
  }
})

test("state stays quiet for Chinese near-miss execution and closeout wording", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "我先把思路整理清楚，再决定要不要改代码。",
    "我可能会直接在主会话里做，但现在先不动，我还要先确认一下边界。",
    "It looks like I could do this inline in the main session, but not yet — I want to confirm the scope first.",
    "这个看起来已经差不多了，我先再核对一遍边界。",
    "看起来已经 ready 了，不过我现在还不能收尾，要先再核对一次。",
    "This feels basically done, but I am not closing it out yet because one more check is still needed.",
    "我只是把结论再捋一遍，暂时不打算收尾。",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }

    await plugin["chat.message"]({ sessionID: `near-miss-${index}` }, output)

    assert.ok(output.parts[0].text.includes(sample))
    assert.match(output.parts[0].text, /\[workflow-state\]/)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/)
    assert.doesNotMatch(output.parts[0].text, /execution work that should run through a just-demand-\* workflow subagent/i)
    assert.doesNotMatch(output.parts[0].text, /complete-verification/i)
  }
})

test("state stays quiet for cross-sentence execution and closeout near-miss wording", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "I can implement this inline in the main session. But I still want to confirm the scope first.",
    "We should just finish this here in the main session. However, I want one more check before I say it is done.",
    "This looks ready to ship. But I am not ready to close it out yet because I still need to confirm one detail.",
    "It feels basically done. Still, I want to hold off on closing this out until the scope is confirmed.",
  ]

  for (const [index, sample] of samples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }

    await plugin["chat.message"]({ sessionID: `cross-sentence-${index}` }, output)

    assert.ok(output.parts[0].text.includes(sample))
    assert.match(output.parts[0].text, /\[workflow-state\]/)
    assert.doesNotMatch(output.parts[0].text, /\[just-demand reminder\]/)
    assert.doesNotMatch(output.parts[0].text, /execution work that should run through a just-demand-\* workflow subagent/i)
    assert.doesNotMatch(output.parts[0].text, /complete-verification/i)
  }
})

test("state appends checkpoint-followup reminder when verification passed but checkpoint commit is missing", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "done", current_step: "verify", verification_status: "passed", checkpoint_commit: { created: false }, assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "The work is finished." }] }

  await plugin["chat.message"]({}, output)

  assert.match(output.parts[0].text, /Verification is already passed/i)
  assert.match(output.parts[0].text, /checkpoint follow-up/i)
})

test("state prefers retry or skip over verification closeout when subagent was unavailable", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  markSubagentUnavailablePending(root, "priority-test")

  const output = { parts: [{ type: "text", text: "This is done." }] }

  await plugin["chat.message"]({ sessionID: "priority-test" }, output)

  assert.match(output.parts[0].text, /retry now, or skip one turn/i)
  assert.doesNotMatch(output.parts[0].text, /complete-verification/i)
})

test("state does not inject the same reminder type on consecutive turns", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const plugin = await stateFactory({ directory: root })
  const first = { parts: [{ type: "text", text: "Please fix the bug in the API." }] }
  const second = { parts: [{ type: "text", text: "Please fix the bug in the API." }] }

  await plugin["chat.message"]({ sessionID: "dedupe-test" }, first)
  await plugin["chat.message"]({ sessionID: "dedupe-test" }, second)

  assert.match(first.parts[0].text, /\[just-demand reminder\]/i)
  assert.ok(second.parts[0].text.includes("Please fix the bug in the API."))
  assert.match(second.parts[0].text, /\[workflow-state\]/)
})

test("state resets after three same-topic turns", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  const plugin = await stateFactory({ directory: root })
  const first = { parts: [{ type: "text", text: "Same topic alpha beta gamma" }] }
  const second = { parts: [{ type: "text", text: "Same topic alpha beta gamma" }] }
  const third = { parts: [{ type: "text", text: "Same topic alpha beta gamma" }] }
  const fourth = { parts: [{ type: "text", text: "Same topic alpha beta gamma" }] }

  await plugin["chat.message"]({ sessionID: "same-topic" }, first)
  await plugin["chat.message"]({ sessionID: "same-topic" }, second)
  await plugin["chat.message"]({ sessionID: "same-topic" }, third)
  await plugin["chat.message"]({ sessionID: "same-topic" }, fourth)

  assert.doesNotMatch(first.parts[0].text, /\[just-demand reminder\]/)
  assert.doesNotMatch(second.parts[0].text, /\[just-demand reminder\]/)
  assert.match(third.parts[0].text, /\[just-demand reminder\]/)
  assert.match(third.parts[0].text, /Reset the problem model/i)
  assert.ok(fourth.parts[0].text.includes("Same topic alpha beta gamma"))
  assert.match(fourth.parts[0].text, /\[workflow-state\]/)
})

test("state asks retry or skip after subagent becomes unavailable", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const subagentPlugin = await subagentContextFactory({ directory: root })
  const statePlugin = await stateFactory({ directory: root })

  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { scope: "Implement the approved feature." } }))

  const toolInput = { tool: "Task" }
  const toolOutput = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }
  await assert.rejects(
    subagentPlugin["tool.execute.before"](toolInput, toolOutput),
    /missing required task context files.*implement\.md/i,
  )

  const output = { parts: [{ type: "text", text: "Continue with the main session." }] }
  await statePlugin["chat.message"]({}, output)
  assert.match(output.parts[0].text, /retry now, or skip one turn/i)
  assert.match(output.parts[0].text, /subagent was unavailable/i)

  const second = { parts: [{ type: "text", text: "Continue with the main session." }] }
  await statePlugin["chat.message"]({}, second)
  assert.ok(second.parts[0].text.includes("Continue with the main session."))
  assert.match(second.parts[0].text, /\[workflow-state\]/)
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
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { expected_behavior: "Shortcut triggers the action.", actual_behavior: "Shortcut is ignored.", reproduction: "Press the shortcut once.", scope: "Keyboard shortcut handling.", non_blocking_questions: ["Should the old shortcut still work?"] } }))
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }
  await plugin["tool.execute.before"](input, output)
  assert.match(output.args.prompt, /Active task: task-a/)
  assert.match(output.args.prompt, /# Just Demand Workflow/)
  assert.match(output.args.prompt, /# Execution Rules/)
  assert.match(output.args.prompt, /Do not call the Task tool\./)
  assert.match(output.args.prompt, /# Context/)
  assert.match(output.args.prompt, /# Execution Context/)
  assert.match(output.args.prompt, /## Goal/)
  assert.match(output.args.prompt, /Shortcut triggers the action/)
  assert.match(output.args.prompt, /# Implement/)
  assert.match(output.args.prompt, /Remaining Open Questions/)
  assert.match(output.args.prompt, /# Requested Work/)
  assert.match(output.args.prompt, /Do the work/)
})

test("subagent-context debug log records injected context parts summary", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nSteps")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { scope: "Feature only." } }))

  const originalDebug = process.env.JUST_DEMAND_DEBUG
  process.env.JUST_DEMAND_DEBUG = "1"

  try {
    const plugin = await subagentContextFactory({ directory: root })
    const input = { tool: "Task" }
    const output = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }
    await plugin["tool.execute.before"](input, output)

    const log = readFileSync(join(root, ".just-demand", "debug.log"), "utf8")
    assert.match(log, /"event":"subagent\.tool\.before\.inject"/)
    assert.match(log, /"context_parts":\[/)
    assert.match(log, /"name":"context\.md"/)
    assert.match(log, /"name":"implement\.md"/)
    assert.match(log, /"prompt_length":/)
  } finally {
    if (originalDebug === undefined) delete process.env.JUST_DEMAND_DEBUG
    else process.env.JUST_DEMAND_DEBUG = originalDebug
  }
})

test("subagent-context writes full prompt dump when JUST_DEMAND_DEBUG_PROMPT_FULL is enabled", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nSteps")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { scope: "Feature only." } }))

  const originalDebug = process.env.JUST_DEMAND_DEBUG
  const originalDebugFull = process.env.JUST_DEMAND_DEBUG_PROMPT_FULL
  process.env.JUST_DEMAND_DEBUG = "1"
  process.env.JUST_DEMAND_DEBUG_PROMPT_FULL = "1"

  try {
    const plugin = await subagentContextFactory({ directory: root })
    const input = { tool: "Task" }
    const output = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }
    await plugin["tool.execute.before"](input, output)

    const debugPromptDir = join(root, ".just-demand", "debug-prompts")
    const files = readdirSync(debugPromptDir)
    const promptDumpFile = files.find((name) => name.includes("task-a-just-demand-coder"))
    assert.equal(typeof promptDumpFile, "string")
    const dump = readFileSync(join(debugPromptDir, promptDumpFile), "utf8")
    assert.match(dump, /# Prompt Debug Dump/)
    assert.match(dump, /## Original Requested Work/)
    assert.match(dump, /Do the work/)
    assert.match(dump, /workflow_subagent: just-demand-coder/)
    assert.match(dump, /context\.md: length=/)
    assert.match(dump, /## Injected Workflow Context/)
    assert.match(dump, /# Context/)
    assert.match(dump, /## Prompt/)
    assert.match(dump, /# Just Demand Workflow/)

    const log = readFileSync(join(root, ".just-demand", "debug.log"), "utf8")
    assert.match(log, /"prompt_dump_path":"\.just-demand\/debug-prompts\//)

    const transcript = readFileSync(join(debugPromptDir, "session-main.md"), "utf8")
    assert.match(transcript, /# Subagent Prompt Injection/)
    assert.match(transcript, /source: subagent-prompt-injection/)
    assert.match(transcript, /## Original Requested Work/)
    assert.match(transcript, /Do the work/)
    assert.match(transcript, /## Injected Workflow Context/)
    assert.match(transcript, /# Context/)
    assert.match(transcript, /## Final Prompt/)
  } finally {
    if (originalDebug === undefined) delete process.env.JUST_DEMAND_DEBUG
    else process.env.JUST_DEMAND_DEBUG = originalDebug
    if (originalDebugFull === undefined) delete process.env.JUST_DEMAND_DEBUG_PROMPT_FULL
    else process.env.JUST_DEMAND_DEBUG_PROMPT_FULL = originalDebugFull
  }
})

test("state writes full chat turn dump when JUST_DEMAND_DEBUG_PROMPT_FULL is enabled", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started", assigned_subagents: [] }))

  const originalDebug = process.env.JUST_DEMAND_DEBUG
  const originalDebugFull = process.env.JUST_DEMAND_DEBUG_PROMPT_FULL
  process.env.JUST_DEMAND_DEBUG = "1"
  process.env.JUST_DEMAND_DEBUG_PROMPT_FULL = "1"

  try {
    const plugin = await stateFactory({ directory: root })
    const output = { parts: [{ type: "text", text: "I will implement the feature inline." }] }
    await plugin["chat.message"]({ sessionID: "dump-session" }, output)

    const debugPromptDir = join(root, ".just-demand", "debug-prompts")
    const files = readdirSync(debugPromptDir).filter((name) => name.includes("chat-dump-session-task-a"))
    assert.equal(files.length, 1)
    const dump = readFileSync(join(debugPromptDir, files[0]), "utf8")
    assert.match(dump, /# Chat Turn Debug Dump/)
    assert.match(dump, /reason_code: execution_needed/)
    assert.match(dump, /## Original Text/)
    assert.match(dump, /I will implement the feature inline\./)
    assert.match(dump, /## After Controller/)
    assert.match(dump, /\[just-demand execution blocked\]/)
    assert.match(dump, /## Final Text/)
    assert.match(dump, /\[workflow-state\]/)

    const log = readFileSync(join(root, ".just-demand", "debug.log"), "utf8")
    assert.match(log, /"event":"state\.chat\.message\.dump"/)
    assert.match(log, /"dump_path":"\.just-demand\/debug-prompts\//)

    const transcript = readFileSync(join(debugPromptDir, "session-dump-session.md"), "utf8")
    assert.match(transcript, /# Main Session Chat Turn/)
    assert.match(transcript, /source: main-session-system-layer/)
    assert.match(transcript, /## Original Text/)
    assert.match(transcript, /I will implement the feature inline\./)
    assert.match(transcript, /## After Controller/)
    assert.match(transcript, /\[just-demand execution blocked\]/)
    assert.match(transcript, /## Final Text/)
    assert.match(transcript, /\[workflow-state\]/)
  } finally {
    if (originalDebug === undefined) delete process.env.JUST_DEMAND_DEBUG
    else process.env.JUST_DEMAND_DEBUG = originalDebug
    if (originalDebugFull === undefined) delete process.env.JUST_DEMAND_DEBUG_PROMPT_FULL
    else process.env.JUST_DEMAND_DEBUG_PROMPT_FULL = originalDebugFull
  }
})

test("subagent-context resumes prior subagent session after unavailable retry", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nSteps")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { scope: "Feature only." } }))
  recordLastSubagentDispatchTaskId(root, "task-a", "just-demand-coder", "opencode-task-123")
  markSubagentUnavailablePending(root, "main")

  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task", sessionID: "main" }
  const output = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }

  await plugin["tool.execute.before"](input, output)

  assert.equal(output.args.task_id, "opencode-task-123")
  assert.match(output.args.prompt, /Active task: task-a/)
})

test("subagent-context reuses parent subagent session for follow-up task lineage", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const parentDir = join(root, ".just-demand", "state", "active", "task-parent")
  const childDir = join(root, ".just-demand", "state", "active", "task-child")
  const followUpDir = join(root, ".just-demand", "state", "active", "task-followup")
  const unrelatedDir = join(root, ".just-demand", "state", "active", "task-unrelated")
  mkdirSync(parentDir, { recursive: true })
  mkdirSync(childDir, { recursive: true })
  mkdirSync(followUpDir, { recursive: true })
  mkdirSync(unrelatedDir, { recursive: true })
  writeFileSync(join(parentDir, "context.md"), "# Context\nParent")
  writeFileSync(join(parentDir, "implement.md"), "# Implement\nParent")
  writeFileSync(join(childDir, "context.md"), "# Context\nChild")
  writeFileSync(join(childDir, "implement.md"), "# Implement\nChild")
  writeFileSync(join(followUpDir, "context.md"), "# Context\nFollow-up")
  writeFileSync(join(followUpDir, "implement.md"), "# Implement\nFollow-up")
  writeFileSync(join(unrelatedDir, "context.md"), "# Context\nOther")
  writeFileSync(join(unrelatedDir, "implement.md"), "# Implement\nOther")
  writeFileSync(join(unrelatedDir, "task.json"), JSON.stringify({ id: "task-unrelated", status: "planning", clarification: { scope: "Unrelated scope." }, root_task_id: "task-unrelated", lineage_task_ids: [] }))
  writeFileSync(join(parentDir, "task.json"), JSON.stringify({ id: "task-parent", status: "planning", clarification: { scope: "Parent scope." }, root_task_id: "task-parent", lineage_task_ids: [] }))
  writeFileSync(join(childDir, "task.json"), JSON.stringify({ id: "task-child", status: "planning", clarification: { scope: "Child scope." }, parent_task_id: "task-parent", root_task_id: "task-parent", lineage_task_ids: ["task-parent"] }))
  writeFileSync(join(followUpDir, "task.json"), JSON.stringify({ id: "task-followup", status: "planning", clarification: { scope: "Follow-up scope." }, parent_task_id: "task-parent", root_task_id: "task-parent", lineage_task_ids: ["task-parent"] }))
  recordLastSubagentDispatchTaskId(root, "task-parent", "just-demand-coder", "opencode-task-parent")
  recordLastSubagentDispatchTaskId(root, "task-child", "just-demand-coder", "opencode-task-child")

  const plugin = await subagentContextFactory({ directory: root })

  const childInput = { tool: "Task" }
  const childOutput = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: "task-child" }))
  markSubagentUnavailablePending(root, "main")
  await plugin["tool.execute.before"](childInput, childOutput)
  assert.equal(childOutput.args.task_id, "opencode-task-child")

  const followUpInput = { tool: "Task" }
  const followUpOutput = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: "task-followup" }))
  markSubagentUnavailablePending(root, "main")
  await plugin["tool.execute.before"](followUpInput, followUpOutput)
  assert.equal(followUpOutput.args.task_id, "opencode-task-parent")

  const unrelatedInput = { tool: "Task" }
  const unrelatedOutput = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: "task-unrelated" }))
  markSubagentUnavailablePending(root, "main")
  await plugin["tool.execute.before"](unrelatedInput, unrelatedOutput)
  assert.equal(unrelatedOutput.args.task_id, undefined)
})

test("subagent-context records recovered task ids from task tool output", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nSteps")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { scope: "Feature only." } }))

  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" }, task_id: "opencode-task-456" }

  await plugin["tool.execute.after"](input, output)

  assert.equal(getLastSubagentDispatchTaskId(root, "task-a", "just-demand-coder"), "opencode-task-456")
})

test("subagent-context records recovered task ids from task tool input shape", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nSteps")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { scope: "Feature only." } }))

  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task", args: { subagent_type: "just-demand-coder", task_id: "opencode-task-input", prompt: "Do the work" } }
  const output = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }

  await plugin["tool.execute.after"](input, output)

  assert.equal(getLastSubagentDispatchTaskId(root, "task-a", "just-demand-coder"), "opencode-task-input")
})

test("subagent-context injects context when runtime uses agent argument key", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: build feature")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nSteps")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { scope: "Feature only." } }))
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { agent: "just-demand-coder", prompt: "Do the work" } }
  await plugin["tool.execute.before"](input, output)
  assert.match(output.args.prompt, /Active task: task-a/)
  assert.match(output.args.prompt, /# Just Demand Workflow/)
  assert.match(output.args.prompt, /# Implement/)
})

test("subagent-context avoids absolute path leakage for just-demand-researcher", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "research"), { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal: research topic")
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-researcher", prompt: "Investigate this" } }
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
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { scope: "Feature only." } }))
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-coder", prompt: "Do the work" } }
  await assert.rejects(
    plugin["tool.execute.before"](input, output),
    /Blocked just-demand-coder: missing required task context files.*implement\.md/,
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
  const output = { args: { subagent_type: "just-demand-researcher", prompt: "Investigate this" } }
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

test("subagent-context blocks workflow coder task when no formal task", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-coder", prompt: "Do work" } }
  await assert.rejects(
    plugin["tool.execute.before"](input, output),
    /Blocked Task: there is no formal task yet\./,
  )
  assert.equal(output.args.prompt, "Do work")
})

test("subagent-context blocks apply_patch when no formal task", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await subagentContextFactory({ directory: root })

  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch: there is no formal task yet\./,
  )
})

test("subagent-context allows apply_patch targeting intake file when no formal task", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await subagentContextFactory({ directory: root })

  const output = { args: { patchText: "*** Update File: .just-demand/state/intake/demo-intake.md\n## Scope\nSome scope.\n*** End Patch" } }
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, output),
  )
})

test("subagent-context blocks write-like bash when no formal task", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await subagentContextFactory({ directory: root })

  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
    /Blocked bash: there is no formal task yet\./,
  )
})

test("subagent-context skips when workflow root is missing", async () => {
  const root = makeRoot()
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  const output = { args: { subagent_type: "just-demand-coder", prompt: "Do work" } }
  await plugin["tool.execute.before"](input, output)
  assert.equal(output.args.prompt, "Do work")
  assert.equal(existsSync(join(root, ".just-demand")), false)
})

test("subagent-context skips when tool is not Task", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Bash" }
  const output = { args: { subagent_type: "just-demand-coder", prompt: "Run this" } }
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
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning", clarification: { scope: "Feature only." } }))
  const plugin = await subagentContextFactory({ directory: root })
  const input = { tool: "Task" }
  // Prompt already contains injection marker
  const existingContext = "# Injected Workflow Context\n\nExisting context"
  const output = { args: { subagent_type: "just-demand-coder", prompt: `${existingContext}\n\nDo the work` } }
  await plugin["tool.execute.before"](input, output)
  // Should not add duplicate injection
  assert.equal(output.args.prompt, `${existingContext}\n\nDo the work`)
  assert.doesNotMatch(output.args.prompt, /Active task: task-a/)
})

// ---------------------------------------------------------------------------
// Execution gate: status-based gating and planning deadlock recovery
// ---------------------------------------------------------------------------
test("state blocks writes during planning when clarification is incomplete (uses update-clarification instead)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  // Planning status with empty scope: previously allowed as deadlock recovery,
  // now blocked — the agent must use `update-clarification` CLI command first.
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "planning", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch: active task task-a is not ready for execution yet/,
  )
})

test("state blocks apply_patch when task status is done", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", status: "done" }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch: active task task-a is in status 'done', which does not allow writes\./,
  )
})

test("state blocks apply_patch when task status is blocked", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", status: "blocked" }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch: active task task-a is in status 'blocked', which does not allow writes\./,
  )
})

test("state blocks apply_patch when task status is paused", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", status: "paused" }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch: active task task-a is in status 'paused', which does not allow writes\./,
  )
})

test("enforceExecutionGate error message lists allowed statuses for status_not_allowed", () => {
  const error = buildExecutionGateError("apply_patch", { reason: "status_not_allowed", taskId: "task-a", status: "done" })
  assert.match(error, /status 'done', which does not allow writes/)
  assert.match(error, /planning, executing, verifying, changes_requested, tweaking, debugging/)
})

test("update-clarification bash command is not write-like and passes through gate naturally", () => {
  assert.equal(looksLikeBashWriteCommand("just-demand . update-clarification task-a --field scope=\"New scope\""), false)
  assert.equal(looksLikeBashWriteCommand("just-demand . update-clarification task-a --field chosen_approach=\"Approach A\" --field approval=\"Approved\""), false)
  assert.equal(getWriteToolRule("bash", { command: "just-demand . update-clarification task-a --field scope=\"New scope\"" }), null)
})

test("task_not_ready error message mentions update-clarification as recovery command", () => {
  const error = buildExecutionGateError("apply_patch", { reason: "task_not_ready", taskId: "task-b", missing: ["Scope"] })
  assert.match(error, /update-clarification/)
  assert.match(error, /task-b/)
  assert.match(error, /Missing or incomplete fields/)
  assert.match(error, /Scope/)
})

// ---------------------------------------------------------------------------
// Preference signaling: intake fallback warns about preferred path
// ---------------------------------------------------------------------------

test("intake gate comment notes update-intake-section as preferred path", () => {
  // This test verifies the intent is documented in the enforcement logic.
  // We read the source to confirm the comment mentions the preference.
  const source = readFileSync(new URL("../../.opencode/plugins/just-demand-lib.js", import.meta.url), "utf8")
  assert.match(source, /update-intake-section/)
  assert.match(source, /preferred intake editing path/)
  assert.match(source, /fallback path/)
})

test("intake fallback still succeeds without formal task", async () => {
  // apply_patch targeting intake file must still pass when no formal task exists
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const plugin = await stateFactory({ directory: root })

  const output = { args: { patchText: "*** Update File: .just-demand/state/intake/demo-intake.md\n## Scope\nFallback edit.\n*** End Patch" } }
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, output),
  )
})

test("intake fallback still succeeds with unselected active tasks", async () => {
  // When active tasks exist but no current task is selected, intake edits must still work
  const root = makeRoot()
  scaffoldWorkflow(root)
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "paused", clarification: { scope: "Scoped" } }))
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })

  const plugin = await stateFactory({ directory: root })
  const output = { args: { patchText: "*** Update File: .just-demand/state/intake/demo-intake.md\n## Scope\nFallback edit with unselected tasks.\n*** End Patch" } }
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, output),
  )
})

test("non-intake writes still blocked without formal task", async () => {
  // Non-intake write tools must still be blocked when no formal task exists
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: src/app.js\n*** End Patch" } }),
    /Blocked apply_patch: there is no formal task yet\./,
  )
})

test("non-intake bash writes still blocked without formal task", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
    /Blocked bash: there is no formal task yet\./,
  )
})

// ---------------------------------------------------------------------------
// Intake fallback one-time warning
// ---------------------------------------------------------------------------

test("consumeIntakeFallbackPending returns false when no fallback was used", () => {
  const root = makeRoot()
  assert.equal(consumeIntakeFallbackPending(root), false)
})

test("consumeIntakeFallbackPending returns true after intake operation passes gate", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  await plugin["tool.execute.before"](
    { tool: "apply_patch" },
    { args: { patchText: "*** Update File: .just-demand/state/intake/demo.md\nContent\n*** End Patch" } },
  )

  assert.equal(consumeIntakeFallbackPending(root), true)
})

test("consumeIntakeFallbackPending clears after consumption", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  await plugin["tool.execute.before"](
    { tool: "apply_patch" },
    { args: { patchText: "*** Update File: .just-demand/state/intake/demo.md\nContent\n*** End Patch" } },
  )

  // First consumption should return true
  assert.equal(consumeIntakeFallbackPending(root), true)
  // Second consumption should return false (already consumed)
  assert.equal(consumeIntakeFallbackPending(root), false)
})

test("intake fallback warning appears once in chat.message after intake gate", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })

  // Simulate tool execution that triggers intake fallback
  await plugin["tool.execute.before"](
    { tool: "apply_patch" },
    { args: { patchText: "*** Update File: .just-demand/state/intake/demo.md\n## Scope\nFallback edit.\n*** End Patch" } },
  )

  // The next chat.message should contain the intake fallback warning
  const output = { parts: [{ type: "text", text: "Let me update the intake scope." }] }
  await plugin["chat.message"]({ sessionID: "intake-warning-test" }, output)

  assert.match(output.parts[0].text, /\[just-demand reminder\]/)
  assert.match(output.parts[0].text, /update-intake-section/)
  assert.match(output.parts[0].text, /Raw file fallback still works/)
})

test("intake fallback warning does not repeat on second intake use", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state", "intake"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })

  // First intake operation
  await plugin["tool.execute.before"](
    { tool: "apply_patch" },
    { args: { patchText: "*** Update File: .just-demand/state/intake/demo.md\n## Scope\nFirst fallback.\n*** End Patch" } },
  )

  // First chat.message: warning should appear
  const firstOutput = { parts: [{ type: "text", text: "Continue" }] }
  await plugin["chat.message"]({ sessionID: "intake-dedup-test" }, firstOutput)
  assert.match(firstOutput.parts[0].text, /\[just-demand reminder\]/)
  assert.match(firstOutput.parts[0].text, /update-intake-section/)

  // Second intake operation
  await plugin["tool.execute.before"](
    { tool: "apply_patch" },
    { args: { patchText: "*** Update File: .just-demand/state/intake/demo.md\n## Scope\nSecond fallback.\n*** End Patch" } },
  )

  // Second chat.message: warning should NOT appear (one-time per session)
  const secondOutput = { parts: [{ type: "text", text: "Continue" }] }
  await plugin["chat.message"]({ sessionID: "intake-dedup-test" }, secondOutput)
  assert.doesNotMatch(secondOutput.parts[0].text, /\[just-demand reminder\]/)
  assert.doesNotMatch(secondOutput.parts[0].text, /update-intake-section/)
})

test("state still blocks non-intake writes even after intake fallback warning", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })

  // Trigger intake fallback first
  await plugin["tool.execute.before"](
    { tool: "apply_patch" },
    { args: { patchText: "*** Update File: .just-demand/state/intake/demo.md\n## Scope\nFallback edit.\n*** End Patch" } },
  )

  // Non-intake writes must still be blocked
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: src/app.js\n*** End Patch" } }),
    /Blocked apply_patch: there is no formal task yet\./,
  )
})

// ---------------------------------------------------------------------------
// Reflection gate: getReflectionGateState helper
// ---------------------------------------------------------------------------
test("getReflectionGateState returns null when task directory missing", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  assert.equal(getReflectionGateState(root, "nonexistent-task"), null)
})

test("getReflectionGateState returns null with no follow-ups and no reflection", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning" }))
  assert.equal(getReflectionGateState(root, "task-a"), null)
})

test("getReflectionGateState returns null with exactly one follow-up and no reflection", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: 1")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning" }))
  assert.equal(getReflectionGateState(root, "task-a"), null)
})

test("getReflectionGateState returns reflection_pending with 2+ follow-ups and no reflection.md", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: 2")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning" }))
  assert.equal(getReflectionGateState(root, "task-a"), "reflection_pending")
})

test("getReflectionGateState returns reflection_active with debugging status and reflection.md", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\nRoot cause found.")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "debugging" }))
  assert.equal(getReflectionGateState(root, "task-a"), "reflection_active")
})

test("getReflectionGateState returns null with debugging status but no reflection.md", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "debugging" }))
  assert.equal(getReflectionGateState(root, "task-a"), null)
})

test("getReflectionGateState returns null with reflection.md but non-debugging status", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\nSome content.")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "planning" }))
  assert.equal(getReflectionGateState(root, "task-a"), null)
})

test("getReflectionGateState scopes to current task, does not fire from another task's files", () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  // task-a has 2 follow-ups and no reflection (would be pending)
  const taskADir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskADir, { recursive: true })
  mkdirSync(join(taskADir, "followups"), { recursive: true })
  writeFileSync(join(taskADir, "followups", "followup-001.md"), "# Follow-Up: 1")
  writeFileSync(join(taskADir, "followups", "followup-002.md"), "# Follow-Up: 2")
  writeFileSync(join(taskADir, "task.json"), JSON.stringify({ id: "task-a", status: "planning" }))
  // task-b has no follow-ups (clean)
  const taskBDir = join(root, ".just-demand", "state", "active", "task-b")
  mkdirSync(taskBDir, { recursive: true })
  writeFileSync(join(taskBDir, "task.json"), JSON.stringify({ id: "task-b", status: "planning" }))

  // Should be null for task-b (clean) even though task-a triggers pending
  assert.equal(getReflectionGateState(root, "task-b"), null)
  // Should be pending for task-a
  assert.equal(getReflectionGateState(root, "task-a"), "reflection_pending")
})

// ---------------------------------------------------------------------------
// buildReflectionGateError
// ---------------------------------------------------------------------------
test("buildReflectionGateError produces correct messages", () => {
  const pendingError = buildReflectionGateError("Task", "task-a", "reflection_pending")
  assert.match(pendingError, /reflection is pending/)
  assert.match(pendingError, /task-a/)
  assert.match(pendingError, /start-reflection/)

  const activeError = buildReflectionGateError("apply_patch", "task-a", "reflection_active")
  assert.match(activeError, /reflection is active/)
  assert.match(activeError, /task-a/)
  assert.match(activeError, /just-demand-advisor/)
})

// ---------------------------------------------------------------------------
// Reflection gate: isWorkflowControlCommand detects start-reflection
// ---------------------------------------------------------------------------
test("isWorkflowControlCommand detects start-reflection CLI command", () => {
  assert.equal(isWorkflowControlCommand("just-demand . start-reflection task-a"), true)
  assert.equal(isWorkflowControlCommand("just-demand . start-reflection"), true)
})

// ---------------------------------------------------------------------------
// Reflection gate: pending blocks coder dispatch
// ---------------------------------------------------------------------------
test("reflection pending blocks coder task dispatch", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: 2")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "executing",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "Task" }, { args: { subagent_type: "just-demand-coder", prompt: "Do work" } }),
    /Blocked Task: reflection is pending for task task-a.*start-reflection/,
  )
})

// ---------------------------------------------------------------------------
// Reflection gate: pending blocks apply_patch
// ---------------------------------------------------------------------------
test("reflection pending blocks apply_patch", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: 2")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "executing",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: src/app.js\n*** End Patch" } }),
    /Blocked apply_patch: reflection is pending for task task-a/,
  )
})

// ---------------------------------------------------------------------------
// Reflection gate: pending blocks write-like bash
// ---------------------------------------------------------------------------
test("reflection pending blocks write-like bash", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: 2")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "executing",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
    /Blocked bash: reflection is pending for task task-a/,
  )
})

// ---------------------------------------------------------------------------
// Reflection gate: pending allows workflow-control (start-reflection)
// ---------------------------------------------------------------------------
test("reflection pending allows start-reflection workflow-control command", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: 2")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "executing",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "Task" }, { args: { subagent_type: "just-demand-tester", prompt: "Test" } }),
  )
})

// ---------------------------------------------------------------------------
// P0: Git read-only/low-risk commands do not false-trigger the write gate
// ---------------------------------------------------------------------------
test("looksLikeBashWriteCommand returns false for git status/log/diff/show", () => {
  const samples = [
    "git status",
    "git log --oneline -5",
    "git diff --cached",
    "git show HEAD",
    "git help add",
    "git version",
    "git blame src/app.js",
    "git grep pattern",
    "git config --list",
    "git rev-parse HEAD",
  ]
  for (const sample of samples) {
    assert.equal(looksLikeBashWriteCommand(sample), false, `Expected false for: "${sample}"`)
    // git config is not in the write pattern at all, so isProbablySafeGitCommand
    // would not normally be called for it. Only check for commands that match
    // the git write pattern.
    if (!sample.startsWith("git config")) {
      assert.equal(isProbablySafeGitCommand(sample), true, `Expected safe for: "${sample}"`)
    }
  }
})

test("looksLikeBashWriteCommand returns false for git stash list/show", () => {
  const samples = [
    "git stash list",
    "git stash show -p",
  ]
  for (const sample of samples) {
    assert.equal(looksLikeBashWriteCommand(sample), false, `Expected false for: "${sample}"`)
    assert.equal(isProbablySafeGitCommand(sample), true, `Expected safe for: "${sample}"`)
  }
})

test("looksLikeBashWriteCommand returns false for git branch listing", () => {
  const samples = [
    "git branch --list",
    "git branch -a",
    "git branch -r",
  ]
  for (const sample of samples) {
    assert.equal(looksLikeBashWriteCommand(sample), false, `Expected false for: "${sample}"`)
  }
})

test("looksLikeBashWriteCommand returns false for git checkout branch switching", () => {
  const samples = [
    "git checkout main",
    "git checkout -b feature-branch",
    "git checkout develop",
  ]
  for (const sample of samples) {
    assert.equal(looksLikeBashWriteCommand(sample), false, `Expected false for: "${sample}"`)
  }
})

test("looksLikeBashWriteCommand returns false for git switch branch", () => {
  const samples = [
    "git switch main",
    "git switch -c new-feature",
  ]
  for (const sample of samples) {
    assert.equal(looksLikeBashWriteCommand(sample), false, `Expected false for: "${sample}"`)
  }
})

test("looksLikeBashWriteCommand still returns true for destructive git commands", () => {
  const samples = [
    "git add .",
    "git commit -m fix",
    "git reset --hard HEAD",
    "git clean -fd",
    "git merge feature",
    "git rebase main",
    "git checkout -- src/app.js",
    "git checkout HEAD -- src/app.js",
    "git checkout .",
    "git stash",
    "git stash push -m msg",
    "git stash pop",
    "git stash drop",
    "git stash apply",
  ]
  for (const sample of samples) {
    assert.equal(looksLikeBashWriteCommand(sample), true, `Expected true for: "${sample}"`)
  }
})

// ---------------------------------------------------------------------------
// P0: External repository git operations bypass the gate
// ---------------------------------------------------------------------------
test("isExternalGitRepoCommand detects git -C outside repo root", () => {
  const root = makeRoot()
  const samples = [
    `git -C /tmp/other-repo status`,
    `git -C ../outside status`,
  ]
  for (const sample of samples) {
    assert.equal(isExternalGitRepoCommand(sample, root), true, `Expected external for: "${sample}"`)
  }
})

test("isExternalGitRepoCommand returns false for git -C inside repo root or missing", () => {
  const root = makeRoot()
  assert.equal(isExternalGitRepoCommand("git -C . status", root), false)
  assert.equal(isExternalGitRepoCommand("git -C .git status", root), false)
  assert.equal(isExternalGitRepoCommand("git status", root), false)
  assert.equal(isExternalGitRepoCommand("", root), false)
  assert.equal(isExternalGitRepoCommand(null, root), false)
})

// ---------------------------------------------------------------------------
// P0: Skip workflow tool gate override (one-shot per turn)
// ---------------------------------------------------------------------------
test("setToolGateSkipOverride and clearToolGateSkipOverride manage one-shot flag", () => {
  const root = makeRoot()
  setToolGateSkipOverride(root)
  // After set, clear should succeed silently
  clearToolGateSkipOverride(root)
  // Setting and clearing multiple times should not throw
  setToolGateSkipOverride(root)
  setToolGateSkipOverride(root)
  clearToolGateSkipOverride(root)
  clearToolGateSkipOverride(root)
})

test("state allows write-like bash after explicit workflow skip (one-shot)", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  // Set skip override: simulates the chat.message handler detecting skip workflow
  setToolGateSkipOverride(root)

  // Now a write-like command should pass through the gate
  const plugin = await stateFactory({ directory: root })
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
    "Write-like bash should pass through gate after explicit skip",
  )
})

test("state blocks write-like bash when skip override was consumed by previous call", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })

  // First call with skip override set
  setToolGateSkipOverride(root)
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
  )

  // Second call: skip override is consumed, should block again
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
    /Blocked bash: there is no formal task yet\./,
  )
})

test("skip workflow override in chat.message sets tool gate skip for same-turn", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })

  // Model says "skip workflow" — this should set the one-shot tool gate flag
  const skipOutput = { parts: [{ type: "text", text: "I will skip the workflow and implement this inline." }] }
  await plugin["chat.message"]({ sessionID: "skip-gate-test" }, skipOutput)

  // The chat text should pass through without block (already tested elsewhere)
  assert.doesNotMatch(skipOutput.parts[0].text, /\[just-demand execution blocked\]/i)

  // Now the next tool call should be allowed because of the skip flag
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
  )

  // But a second tool call should be blocked (one-shot consumed)
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
    /Blocked bash: there is no formal task yet\./,
  )
})

// ---------------------------------------------------------------------------
// P0: Unrelated active-task readiness softening
// ---------------------------------------------------------------------------
test("read-only bash commands pass the gate even when active task is not ready", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "executing", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "git status",
    "git log --oneline -5",
    "git diff",
    "git stash list",
    "ls -la",
    "python3 --version",
    "cat README.md",
    "wc -l src/app.js",
  ]
  for (const sample of samples) {
    const output = { args: { command: sample } }
    await assert.doesNotReject(
      plugin["tool.execute.before"]({ tool: "bash" }, output),
      `Expected read-only command to pass: "${sample}"`,
    )
  }
})

test("git read-only commands pass the gate even when active task is not ready", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "executing", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "git status",
    "git log --oneline -5",
    "git diff --cached",
    "git show HEAD",
    "git stash list",
    "git checkout main",
    "git checkout -b feature",
    "git switch develop",
  ]
  for (const sample of samples) {
    const output = { args: { command: sample } }
    await assert.doesNotReject(
      plugin["tool.execute.before"]({ tool: "bash" }, output),
      `Expected safe git command to pass: "${sample}"`,
    )
  }
})

test("true writes still blocked when active task is not ready", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", type: "design", status: "executing", clarification: { scope: "" } }))

  const plugin = await stateFactory({ directory: root })
  const samples = [
    "git add .",
    "git commit -m fix",
    "git reset --hard HEAD",
    "touch out/file.txt",
    "mkdir -p out && touch out/file.txt",
  ]
  for (const sample of samples) {
    await assert.rejects(
      plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: sample } }),
      /Blocked bash:/,
      `Expected write command to be blocked: "${sample}"`,
    )
  }
})

// ---------------------------------------------------------------------------
// P0: Closeout continuation protection remains intact
// ---------------------------------------------------------------------------
test("closeout continuation phrases still blocked when verification not passed", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "done", current_step: "verify", verification_status: "passed", checkpoint_commit: { created: true } }))

  const plugin = await stateFactory({ directory: root })
  const closeoutBlockedSamples = [
    "Continue the task.",
    "Let's wrap this up.",
  ]
  for (const [index, sample] of closeoutBlockedSamples.entries()) {
    const output = { parts: [{ type: "text", text: sample }] }
    await plugin["chat.message"]({ sessionID: `closeout-protect-${index}` }, output)
    assert.match(output.parts[0].text, /\[workflow-state\]/)
  }
})

test("closeout continuation false positives allowed when not in closeout phase", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", status: "executing", current_step: "execute", verification_status: "not_started" }))

  const plugin = await stateFactory({ directory: root })
  const output = { parts: [{ type: "text", text: "Let's continue with the implementation." }] }
  await plugin["chat.message"]({}, output)
  assert.ok(output.parts[0].text.includes("Let's continue with the implementation."))
  assert.doesNotMatch(output.parts[0].text, /closeout blocked/i)
})

// ---------------------------------------------------------------------------
// P0: Safety-critical hard blocks remain intact
// ---------------------------------------------------------------------------
test("writes still blocked when no formal task exists", async () => {
  const root = makeRoot()
  mkdirSync(join(root, ".just-demand", "state"), { recursive: true })
  writeFileSync(join(root, ".just-demand", "state", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: null }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: src/app.js\n*** End Patch" } }),
    /Blocked apply_patch: there is no formal task yet\./,
  )
})

test("writes still blocked when task status is done", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({ id: "task-a", title: "Task A", status: "done" }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: x\n*** End Patch" } }),
    /Blocked apply_patch:/,
  )
})

test("reflection pending still blocks coder dispatch", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: 2")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "executing",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "Task" }, { args: { subagent_type: "just-demand-coder", prompt: "Do work" } }),
    /Blocked Task: reflection is pending/,
  )
})

// ---------------------------------------------------------------------------
// Reflection gate: active blocks coder dispatch
// ---------------------------------------------------------------------------
test("reflection active blocks coder task dispatch", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\nRoot cause found.")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "debugging",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "Task" }, { args: { subagent_type: "just-demand-coder", prompt: "Do work" } }),
    /Blocked Task: reflection is active for task task-a.*just-demand-advisor/,
  )
})

// ---------------------------------------------------------------------------
// Reflection gate: active blocks apply_patch
// ---------------------------------------------------------------------------
test("reflection active blocks apply_patch", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\nRoot cause found.")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "debugging",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "apply_patch" }, { args: { patchText: "*** Update File: src/app.js\n*** End Patch" } }),
    /Blocked apply_patch: reflection is active for task task-a/,
  )
})

// ---------------------------------------------------------------------------
// Reflection gate: active blocks write-like bash
// ---------------------------------------------------------------------------
test("reflection active blocks write-like bash", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\nRoot cause found.")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "debugging",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.rejects(
    plugin["tool.execute.before"]({ tool: "bash" }, { args: { command: "mkdir -p out && touch out/file.txt" } }),
    /Blocked bash: reflection is active for task task-a/,
  )
})

// ---------------------------------------------------------------------------
// Reflection gate: active allows advisor dispatch
// ---------------------------------------------------------------------------
test("reflection active allows advisor dispatch", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\nRoot cause found.")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "debugging",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  // Advisor dispatch passes through because it does not match the write gate
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "Task" }, { args: { subagent_type: "just-demand-advisor", prompt: "Analyze" } }),
  )
})

// ---------------------------------------------------------------------------
// Reflection gate: active allows tester dispatch
// ---------------------------------------------------------------------------
test("reflection gate does not block tester dispatch for pending state", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  mkdirSync(join(taskDir, "followups"), { recursive: true })
  writeFileSync(join(taskDir, "followups", "followup-001.md"), "# Follow-Up: 1")
  writeFileSync(join(taskDir, "followups", "followup-002.md"), "# Follow-Up: 2")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "executing",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "Task" }, { args: { subagent_type: "just-demand-tester", prompt: "Test" } }),
  )
})

test("reflection gate does not block tester dispatch for active state", async () => {
  const root = makeRoot()
  scaffoldWorkflow(root)
  const taskDir = join(root, ".just-demand", "state", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "reflection.md"), "# Reflection\nRoot cause found.")
  writeFileSync(join(taskDir, "task.json"), JSON.stringify({
    id: "task-a",
    title: "Task A",
    type: "design",
    status: "debugging",
    clarification: { scope: "Scope", final_expected_effect: "Effect", chosen_approach: "Approach A", final_implementation_plan: "1. Build", approval: "Approved" },
  }))

  const plugin = await stateFactory({ directory: root })
  await assert.doesNotReject(
    plugin["tool.execute.before"]({ tool: "Task" }, { args: { subagent_type: "just-demand-tester", prompt: "Test" } }),
  )
})
