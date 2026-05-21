---
name: workflow-execution
description: Use when a formal work item is ready to execute, when dispatching workflow-research, workflow-implement, workflow-check, or workflow-docs subagents, or when building context for focused execution.
---

# Workflow Execution

Execute formal work items through focused subagents and script-owned state.

## Core Rules

- Main agent coordinates; subagents execute focused work.
- Subagents do not inherit full chat history.
- Scripts are the only write path for workflow machine state under `.agent-workflow/`.
- Plugins and agents may read state, but lifecycle transitions must go through scripts.
- Do not dispatch implementation before the user has confirmed the direction and the task is ready.
- Long-context implementation, research, and verification must run through subagents. The main session should coordinate and summarize, not absorb the full execution context inline.
- Implementation or verification must not start unless the current formal task already has the required task context files. Do not treat missing task context as a recoverable inline shortcut.

## Subagent Routing

- `workflow-research`: research only; no code changes.
- `workflow-implement`: scoped implementation; no commits.
- `workflow-check`: verify requirements and fix only low-risk local issues within scope.
- `workflow-docs`: update workflow docs and durable notes; no business-code changes.

## Dispatch Prompt

Start workflow subagent prompts with:

```text
Active task: <task-id>
```

This is a fallback for context injection failures.

## Execution Loop

1. Confirm active formal work item.
2. Run `python3 .agent-workflow/scripts/task.py --root . list-active` and inspect all unfinished tasks for conflict risk.
3. Ensure the current task package has the required files for the intended subagent.
4. Dispatch the narrowest suitable subagent. If the work would require substantial code reading, multi-file editing, or long verification output, do not keep it in the main session.
5. Review subagent output before moving to the next phase.
6. Run verification before claiming completion.

## Required Context Files

- `workflow-implement`: `context.md`, `implement.md`
- `workflow-check`: `context.md`, `verify.md`
- `workflow-docs`: `context.md`, `decisions.md`
- `workflow-research`: `context.md`

If required files are missing, stop and create or refresh the task context package first.
