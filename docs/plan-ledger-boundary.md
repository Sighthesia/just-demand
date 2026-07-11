# Plan-Ledger Boundary

## Status — Stages 1 & 3 Complete

This document records the explicit boundary between the implemented stages (plan-ledger core schema and CLI, plan-context injection into task files) and the remaining stages that are deferred to follow-up work.

## What Is Implemented

### Stage 1 — Plan-Ledger Core

- **Plan schema**: atomic JSON storage under `.just-demand/state/plans/<plan_id>/plan.json`
- **Plan stages**: ordered stage definitions within a plan (`id`, `title`, `order`)
- **Suggestions**: verbatim user text preserved as-is; auto-assigned ID; `status` with full `status_history` (timestamped transitions)
- **Dependencies**: suggestion-to-suggestion dependency validation (IDs must exist)
- **Task association**: `covered_tasks` list on each suggestion; `plan_id` set on task JSON
- **Evidence**: free-text evidence strings appended to a suggestion
- **CLI commands**: `create-plan`, `show-plan`, `list-plans`, `add-stage`, `add-suggestion`, `update-suggestion-status`, `add-task-to-plan`, `add-evidence`
- **Workspace events**: every plan mutation emits structured events into `events.jsonl`
- **Task compatibility**: tasks without a `plan_id` remain fully unchanged; the field is `None` by default

### Stage 3 — Plan-Context Injection (Snapshot)

- Render suggestion statuses, stages, and dependencies into agent context
- Wire plan data into `context.md`, `implement.md`, and `verify.md` sections for subagent consumption
- Make plan evidence visible during verification
- Idempotent refresh via stable `<!-- plan-snapshot -->` / `<!-- /plan-snapshot -->` markers that never replace unrelated content
- Atomic write with rollback on failure (all three files always stay consistent)
- Explicit `refresh-plan-context` CLI command
- Automatic snapshot refresh after: `add-task-to-plan`, `update-suggestion-status`, `add-plan-evidence`, `add-plan-stage`, `add-plan-suggestion`
- Active-archived distinction: refresh works for both active and archived plan-linked tasks
- Bad references (missing plan, missing stage, missing suggestion) produce clear actionable errors
- Tasks without `plan_id` are never touched

## Remaining Stages (Not Implemented)

The following are explicitly deferred; no hooks, imports, or code pathways reach them yet.

### Stage 2 — Plugin Integration

- Provide plan-aware guardrails in OpenCode plugins (e.g., `just-demand-state.js`)
- Surface plan summary in task state banner
- Inject enhanced plan context via plugin (Stage 3 provides the context-file path; plugin integration builds on it)

### Stage 4 — Closeout Auto-Continuation

- Detect when a suggestion transitions to `implemented` and auto-create follow-up tasks
- Record closeout evidence linked to verification pass
- Offer "next stage" suggestion prompt on plan completion

## Plugin Boundary

The current plan-ledger + snapshot layers do **not**:

- Import, depend on, or modify any `.opencode/plugins/*.js` file
- Modify `package.json` or any OpenCode package metadata
- Create or modify subagent definitions
- Touch the session start, state, or subagent-context plugins
- Implement `complete-verification` auto-continuation or suggestion-completion wiring

Any future plugin that reads plan data should do so via the existing `read_plan()` / `list_plans()` Python API, or by reading the plan JSON files at `.just-demand/state/plans/<plan_id>/plan.json`. The schema is stable at `schema_version: "1.0"`.

## Storage Layout

```
.just-demand/state/plans/
  <plan_id>/
    plan.json            # Full plan data: stages, suggestions, metadata
```

## Write Order and Consistency

`add_task_to_plan` writes to two files inside one mutation lock:

1. **Task JSON** (sets `plan_id` convenience field) — written first
2. **Plan JSON** (appends to `covered_tasks` — authoritative record) — written last

If the task write fails, the exception propagates before the plan is saved, so no inconsistency can arise. If the plan save fails after the task was written, the task write is rolled back (`plan_id` restored to `None`) inside the same `except` block while the lock is still held. The plan is always the single source of truth: `covered_tasks` on each suggestion is the canonical record of task-plan association.

### Event Ordering

Workspace events are appended **outside** the mutation lock in every plan-ledger operation. This means a concurrent mutation's event may be interleaved with another's in `events.jsonl`. This is acceptable because:

- Events are append-only with sequential `seq` numbers and `at` timestamps.
- The canonical state lives in `plan.json`, not in the event stream.
- The event stream is an audit log, not an ordering oracle.

If strict event ordering by mutation becomes required in Stage 4 (closeout auto-continuation), the event append should be moved inside the lock. That change is deferred because it would extend lock hold time during file I/O.

## Dependencies

The plan-ledger reuses these existing systems:

- `write_json_atomic` for atomic file writes
- `workflow_mutation_lock` for concurrent-safety
- `append_workspace_event` for event stream integration
- `unique_readable_id` / `slugify` for ID generation
- `find_task_json_path` for task validation
