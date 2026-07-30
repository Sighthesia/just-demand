import { existsSync } from "node:fs"
import {
  appendDebugSessionAudit,
  bindWorkflowControlCommandToSession,
  debugLog,
  enforceExecutionGate,
  getActiveTask,
  getMissingRequiredContextFiles,
  getExecutionAuditReadinessErrors,
  getLastSubagentDispatchTaskId,
  getRecoveredSubagentTaskId,
  getReminderState,
  getWorkflowSubagentName,
  appendDebugSessionTranscript,
  isDebugPromptFullEnabled,
  logPluginBootstrap,
  markSubagentUnavailablePending,
  recordLastSubagentDispatchTaskId,
  readTaskContext,
  readTaskJson,
  summarizeInjectedContextParts,
  writeDebugPromptDump,
  workflowRoot,
} from "./just-demand-lib.js"

const SUPPORTED = new Set(["just-demand-researcher", "just-demand-coder", "just-demand-tester", "just-demand-advisor"])
const WRITABLE_SUBAGENTS = new Set(["just-demand-coder", "just-demand-tester"])
const COMPATIBILITY_ONLY_SUBAGENTS = new Set(["just-demand-researcher", "just-demand-coder"])
const EXPLICIT_COMPATIBILITY_MARKER = "JUST_DEMAND_EXPLICIT_LEGACY_ROLE"

// Markers to detect if prompt has already been injected with workflow context.
// Keep the legacy header to avoid duplicate injection across old prompts.
const INJECTION_MARKERS = ["# Just Demand Workflow", "# Injected Workflow Context"]

const argsKeys = (args) => args && typeof args === "object" ? Object.keys(args).sort() : []

export default async ({ directory }) => {
  logPluginBootstrap(directory || ".", "just-demand-subagent-context")
  return {
    "tool.execute.after": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      const toolName = String(input?.tool || "").toLowerCase()
      if (toolName !== "task") return

      const args = output?.args || input?.args
      const subagentName = getWorkflowSubagentName(args)
      if (!args || !SUPPORTED.has(subagentName)) return

      const sessionId = input?.sessionID || "main"
      const taskId = getActiveTask(directory, sessionId)
      if (!taskId) return

      const recoveredTaskId = getRecoveredSubagentTaskId(directory, taskId, subagentName, input, output)
      if (!recoveredTaskId) return

      recordLastSubagentDispatchTaskId(directory, taskId, subagentName, recoveredTaskId)
      debugLog("subagent.tool.after.record", { task_id: taskId, workflow_subagent: subagentName, resumed_task_id: recoveredTaskId }, directory)
    },
    "tool.execute.before": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) {
        debugLog("subagent.tool.before.skip", { reason: "missing_workflow_root" }, directory)
        return
      }
      const toolName = String(input?.tool || "").toLowerCase()
      const args = output?.args || input?.args
      const sessionId = input?.sessionID || "main"
      if (toolName === "bash" && args?.command) {
        args.command = bindWorkflowControlCommandToSession(args.command, sessionId)
      }
      enforceExecutionGate(directory, toolName, args, "subagent.gate", sessionId)
      if (toolName !== "task") {
        debugLog("subagent.tool.before.skip", { reason: "not_task_tool", tool: toolName }, directory)
        return
      }
      const subagentName = getWorkflowSubagentName(args)
      debugLog("subagent.tool.before", { args_keys: argsKeys(args), workflow_subagent: subagentName }, directory)
      if (!args || !SUPPORTED.has(subagentName)) {
        debugLog("subagent.tool.before.skip", { reason: "unsupported_subagent", workflow_subagent: subagentName || null }, directory)
        return
      }

      // Skip if prompt already contains workflow context (duplicate injection protection)
      if (args.prompt && INJECTION_MARKERS.some((marker) => args.prompt.includes(marker))) {
        debugLog("subagent.tool.before.skip", { reason: "already_injected", workflow_subagent: subagentName }, directory)
        appendDebugSessionAudit(directory, sessionId, "complete", {
          source: "subagent-injection",
          task_id: getActiveTask(directory, sessionId) || "",
          agent: subagentName,
          status: "skipped",
          reason: "already_injected",
          content: `Subagent ${subagentName} prompt already contains workflow context markers. Injection skipped.`,
        })
        return
      }

      const taskId = getActiveTask(directory, sessionId)
      if (!taskId) {
        debugLog("subagent.tool.before.skip", { reason: "no_active_task", workflow_subagent: subagentName }, directory)
        appendDebugSessionAudit(directory, sessionId, "complete", {
          source: "subagent-injection",
          agent: subagentName,
          status: "skipped",
          reason: "no_active_task",
          content: `Subagent ${subagentName} dispatch: no active task selected. Injection skipped.`,
        })
        return
      }
      const task = readTaskJson(directory, taskId)
      const assignedSubagents = Array.isArray(task?.assigned_subagents) ? task.assigned_subagents : []
      const legacyTask = !task?.subagent_routing
      const explicitlyRequested = String(args.prompt || "").includes(EXPLICIT_COMPATIBILITY_MARKER)
      if (
        COMPATIBILITY_ONLY_SUBAGENTS.has(subagentName)
        && !legacyTask
        && !assignedSubagents.includes(subagentName)
        && !explicitlyRequested
      ) {
        debugLog("subagent.tool.before.block", { reason: "compatibility_only_role", task_id: taskId, workflow_subagent: subagentName }, directory)
        throw new Error(
          `Blocked ${subagentName}: this compatibility-only role is not part of the default route for new tasks. The main agent owns research and implementation. Use tester/advisor when selective dispatch is beneficial, or include ${EXPLICIT_COMPATIBILITY_MARKER} only when the user explicitly requested this legacy role.`,
        )
      }
      if (explicitlyRequested) {
        args.prompt = String(args.prompt || "").replace(EXPLICIT_COMPATIBILITY_MARKER, "").trim()
      }
      const reminderState = getReminderState(directory, sessionId)
      const resumedTaskId = reminderState.subagent_unavailable_pending
        ? getLastSubagentDispatchTaskId(directory, taskId, subagentName)
        : null
      if (!output.args && args) {
        output.args = args
      }
      if (resumedTaskId && !args.task_id) {
        output.args.task_id = resumedTaskId
        debugLog("subagent.tool.before.resume", { task_id: taskId, workflow_subagent: subagentName, resumed_task_id: resumedTaskId }, directory)
      }
      const missing = getMissingRequiredContextFiles(directory, taskId, subagentName)
      if (missing.length > 0) {
        markSubagentUnavailablePending(directory, sessionId)
        debugLog("subagent.tool.before.block", { reason: "missing_context", task_id: taskId, workflow_subagent: subagentName, missing }, directory)
        appendDebugSessionAudit(directory, sessionId, "complete", {
          source: "subagent-injection",
          task_id: taskId,
          agent: subagentName,
          status: "blocked",
          reason: "missing_context_files",
          content: `Blocked ${subagentName}: missing required task context files for task ${taskId}: ${missing.join(", ")}`,
        })
        if (WRITABLE_SUBAGENTS.has(subagentName)) {
          throw new Error(
            `Blocked ${subagentName}: missing required task context files for active task ${taskId}: ${missing.join(", ")}`,
          )
        }
        args.prompt = `Active task: ${taskId}\n\n# BLOCKED\n\nMissing required task context files: ${missing.join(", ")}. Do not proceed until the main agent creates the required task context package files for this task.\n\n---\n\n# Requested Work\n\n${args.prompt || ""}`
        return
      }
      const auditErrors = getExecutionAuditReadinessErrors(directory, taskId, subagentName)
      if (auditErrors.length > 0) {
        markSubagentUnavailablePending(directory, sessionId)
        debugLog("subagent.tool.before.block", { reason: "missing_execution_audit", task_id: taskId, workflow_subagent: subagentName, missing: auditErrors }, directory)
        throw new Error(
          `Blocked ${subagentName}: main-agent execution audit is incomplete for active task ${taskId}: ${auditErrors.join(", ")}. Run \`just-demand . update-audit ${taskId} --objective ... --strategy ... --rationale ...\` before review dispatch.`,
        )
      }
      const context = readTaskContext(directory, taskId, subagentName)
      if (!context) {
        debugLog("subagent.tool.before.skip", { reason: "empty_context", task_id: taskId, workflow_subagent: subagentName }, directory)
        appendDebugSessionAudit(directory, sessionId, "complete", {
          source: "subagent-injection",
          task_id: taskId,
          agent: subagentName,
          status: "skipped",
          reason: "empty_context",
          content: `Subagent ${subagentName} dispatch for task ${taskId}: empty context returned. Injection skipped.`,
        })
        return
      }
      const requestedWork = args.prompt || ""
      args.prompt = `Active task: ${taskId}\n\n# Just Demand Workflow\n\n${context}\n\n---\n\n# Execution Rules\n\nComplete the requested work in this subagent.\nDo not call the Task tool.\nDo not dispatch another subagent.\n\n---\n\n# Requested Work\n\n${requestedWork}`
      const contextParts = summarizeInjectedContextParts(directory, taskId, subagentName)
      const injectLog = {
        task_id: taskId,
        workflow_subagent: subagentName,
        prompt_length: args.prompt.length,
        context_parts: contextParts,
      }
      if (isDebugPromptFullEnabled()) {
        injectLog.prompt_dump_path = writeDebugPromptDump(directory, {
          task_id: taskId,
          workflow_subagent: subagentName,
          prompt_length: args.prompt.length,
          context_parts: contextParts,
          requested_work: requestedWork,
          injected_context: context,
          prompt: args.prompt,
        })
        injectLog.transcript_path = appendDebugSessionTranscript(directory, {
          entry_type: "Subagent Prompt Injection",
          session_id: sessionId,
          task_id: taskId,
          source: "subagent-prompt-injection",
          workflow_subagent: subagentName,
          trigger_summary: [
            `just-demand subagent injection for ${subagentName}`,
            `active task ${taskId} context injected before Task dispatch`,
          ],
          requested_work: requestedWork,
          context_parts: contextParts,
          injected_context: context,
          prompt: args.prompt,
        })
      }

      // Per-session injection audit (JUST_DEMAND_DEBUG, independent of PROMPT_FULL)
      appendDebugSessionAudit(directory, sessionId, "complete", {
        source: "subagent-injection",
        task_id: taskId,
        agent: subagentName,
        status: "applied",
        reason: "successful_injection",
        content: `Subagent ${subagentName} dispatch for task ${taskId}: context injected (${args.prompt.length} chars, ${contextParts.length} context parts).\n\n## Injected Context\n\n${context}\n\n## Full Prompt\n\n${args.prompt}`,
      })
      appendDebugSessionAudit(directory, sessionId, "subagent", {
        source: "subagent-injection",
        task_id: taskId,
        agent: subagentName,
        status: "applied",
        reason: "successful_injection",
        content: `# Subagent Prompt: ${subagentName} / Task: ${taskId}\n\n## Context Parts\n${contextParts.map((part) => `- ${part.name}: length=${part.length}`).join("\n")}\n\n## Injected Context\n\n${context}\n\n## Full Prompt\n\n${args.prompt}`,
      })

      debugLog("subagent.tool.before.inject", injectLog, directory)
    },
  }
}
