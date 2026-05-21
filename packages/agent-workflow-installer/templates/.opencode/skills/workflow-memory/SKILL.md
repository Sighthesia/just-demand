---
name: workflow-memory
description: Use when recording durable preferences, decisions, deferred options, workspace facts, open questions, or when the user chooses a lightweight path over a more robust option.
---

# Workflow Memory

Persist durable knowledge without turning exploratory chat into permanent policy by accident.

## What To Persist

- Workspace preferences: long-lived defaults for future work.
- Workspace decisions: accepted architecture or workflow choices.
- Deferred options: robust or broader approaches intentionally postponed.
- Task decisions: choices that apply only to the current formal work item.
- Open questions: unresolved items that block or shape future work.

## Deferred Option Rule

When the user chooses a minimal or fast path, record the more robust option if it matters later:

```markdown
## Deferred Option: <name>

Id: O001
Scope: workspace | task
Status: deferred
Chosen Instead: <chosen path>
Reason: <why not now>
Risk: <risk of deferring>
Source Task: <task-id or none>
Revisit When:
- <trigger>
```

## Boundaries

- Do not store secrets, credentials, tokens, cookies, or private keys.
- Prefer references to secure locations over copying sensitive values.
- Promote a task-local decision to workspace memory only when the user confirms it should become a default.
