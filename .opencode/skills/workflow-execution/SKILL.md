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
2. Ensure the task package has `context.md`, `implement.md`, and `verify.md`.
3. Dispatch the narrowest suitable subagent.
4. Review subagent output before moving to the next phase.
5. Run verification before claiming completion.
