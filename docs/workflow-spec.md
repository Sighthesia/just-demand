# Canonical Workflow Specification

This document is the canonical, repo-owned description of Just Demand workflow behavior. When other docs, skills, or prompts differ from this spec, this file is the reference point for lifecycle, ownership, and recovery semantics.

## Scope And Authority

- **Authoritative for**: lifecycle, role model, task-state transitions, clarification/intake/execution/verification/archive rules, context-package requirements, recovery, command ordering, checkpoint semantics, and source-of-truth boundaries.
- **Not authoritative for**: runtime code behavior details, task-specific implementation choices, or one-off decisions recorded in task archives.
- **Behavioral source of truth**: the `just-demand` CLI, `.just-demand/scripts/workflow_core.py`, and `.opencode/plugins/*.js` define executable behavior; this spec explains and aligns that behavior.

## System Model

Just Demand is a workflow runtime, not a one-shot prompt bundle.

The durable workflow truth lives in explicit state and scripts. Prompt-layer guidance stays light and role-specific so the main agent can route work without carrying the whole lifecycle in chat.

```text
human intent
  -> clarify
  -> intake
  -> promote
  -> context
  -> dispatch
  -> verify
  -> complete-verification
  -> archive
```

## Roles

- **User**: defines goals, constraints, tradeoffs, and final approval.
- **Main agent**: owns workflow shape, routing, recovery, verification closeout, and summaries.
- **Subagents**: execute focused role contracts inside a task boundary.

Role boundaries:

- **Researcher**: evidence gathering, problem mapping, option comparison.
- **Coder**: scoped implementation inside the task boundary.
- **Tester**: acceptance verification and low-risk local fixes.
- **Advisor**: fresh-context framing and cross-boundary tradeoff analysis.

Subagents do not create, promote, close, or re-route tasks.

## Lifecycle And State Transitions

```text
no task
  -> intake created
  -> intake promoted
  -> active formal task
  -> context package present
  -> subagent dispatch / implementation
  -> verification
  -> complete-verification
  -> archive
```

Key meanings:

- `create-intake` creates intake only; it does not create a formal task.
- `promote` turns a prepared intake into an active formal task.
- `list-active` reflects active formal tasks only.
- `complete-verification` is the normal verified-closeout path and archives on pass.
- `checkpoint-commit` is the mid-task checkpoint path for a clean verified slice.

## Clarification, Intake, And Promotion

Clarification is a hard gate before promotion or execution when the intended effect is still ambiguous.

- Use `socratic-clarification` to establish the final expected effect, boundaries, and tradeoffs.
- Move clarified work into the intake file before promotion.
- Treat blocking questions as promotion blockers.
- Do not guess missing scope, expected behavior, actual behavior, or approval fields.

For design and implementation work, promotion requires a clear decision surface: expected effect, chosen approach, implementation plan, and approval. For mismatch work, promotion requires the expected/actual/reproduction/scope shape that safely identifies the deviation.

## Execution And Context Packages

Execution belongs to the active formal task, not the intake thread.

Before implementation or verification:

1. Confirm the intended task is active.
2. Run `just-demand . list-active` and inspect unfinished tasks for conflict risk.
3. Select or resume the intended task if another unfinished task is current.
4. Ensure the task context package exists for the intended subagent.
5. Dispatch the narrowest suitable `just-demand-*` subagent when long-context work is involved.

Required task context files:

- `just-demand-coder`: `context.md`, `implement.md`
- `just-demand-tester`: `context.md`, `verify.md`
- `just-demand-researcher`: `context.md`
- `just-demand-advisor`: `context.md`

If required context files are missing, stop and refresh the package before execution.

## Verification, Checkpoints, And Archive

Verification must precede completion claims.

- Use `just-demand-tester` for task-brief validation when the result needs review.
- Treat the tester report as the active verification record.
- Use `complete-verification <task-id> passed ...` for the normal verified-closeout path.
- Use `checkpoint-commit <task-id>` for a clean mid-task checkpoint without closeout.
- Do not report completion until verification closeout has run.

Checkpoint semantics:

- Clean verification should normally produce a checkpoint commit through the script-owned closeout path.
- The script owns the safety gate, commit scoping, and archive-on-pass behavior.
- The agent should not hand-edit workflow state files.

## Recovery Model

Recovery is task-local and stateful.

- If `list-active` shows unfinished tasks but no current task is selected, select or resume the intended task first.
- If `promote` fails, update the same intake file and rerun the command rather than creating a new intake.
- If the current task lacks required context files, refresh the task package before execution.
- If workflow gates fail in no-plugin fallback, route back to clarification or intake instead of guessing.

## Command Ordering

Recommended order for real work:

```text
list-active
  -> select/resume if needed
  -> clarify
  -> create-intake / update intake
  -> promote
  -> ensure task context files
  -> dispatch subagent / implement
  -> verify
  -> complete-verification or checkpoint-commit
  -> archive
```

Additional rules:

- `create-intake` does not make a task active.
- `promote` must not happen before required intake fields are filled.
- `complete-verification` is the normal closeout path; `checkpoint-commit` is the partial checkpoint path.
- State writes go through CLI/script ownership, not manual edits.

## Source-Of-Truth Boundaries

- **CLI and scripts**: own durable workflow state and lifecycle transitions.
- **Plugins**: inject lightweight runtime guards, reminders, and task context.
- **Skills**: route the main agent and preserve concise operating rules.
- **Docs**: explain the model and reference the canonical spec.
- **Task archives**: preserve task-local history, decisions, and verified lessons.

Operational files such as `.just-demand/state/state.json`, `locks.json`, and `events.jsonl` are not hand-edited.

## What May Stay Duplicated

Some short routing reminders remain duplicated on purpose in README, AGENTS, and skills so the right agent can still operate with minimal context. Those copies should stay brief and point back to this spec rather than reintroducing long lifecycle prose.
