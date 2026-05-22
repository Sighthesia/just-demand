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

## Lesson Storage Tiers

When extracting durable knowledge from debugging or exploration, choose the right tier:

| Tier | Use when | Destination |
| --- | --- | --- |
| Global reusable skill | Pattern applies across modules, projects, or repos; triggers `capture-lessons` conditions (>=3 attempts, architectural trap, reusable methodology) | `.agents/skills/<pattern-name>/SKILL.md` via `capture-lessons` |
| Workspace memory | Durable but project-local: this repo's conventions, scripts, architecture decisions, verified local facts | `.just-demand/workspace/decisions.md` or `.just-demand/workspace/facts.md` |
| Task decisions | Task-only or one-off: not reusable beyond the current work item | Task `decisions.md` |

Do not promote a lesson to global skill tier unless it is clearly pattern-based and portable. When in doubt, keep it workspace-local.

## Task-Local Extraction Before Archival

When a task is about to leave the active set (archived or cleaned up), extract durable knowledge first:

- Copy reusable decisions from task `decisions.md` to workspace memory if they apply beyond the task.
- Route reusable patterns through `capture-lessons` if they meet the global skill threshold.
- Keep one-off business details, raw logs, secrets, and unverified guesses out of skills and workspace memory.
- If extraction fails, preserve the full task package in archive rather than losing information.

## Boundaries

- Do not store secrets, credentials, tokens, cookies, or private keys.
- Prefer references to secure locations over copying sensitive values.
- Promote a task-local decision to workspace memory only when the user confirms it should become a default.
