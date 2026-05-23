---
name: just-demand-verification
description: Use after implementation, after just-demand-check output, when verification fails, when the user gives correction feedback, or before claiming a workflow task is done.
---

# Workflow Verification

Verify outcomes against the task brief and active validation revision.

## Core Rules

- No completion claim without fresh verification evidence.
- Verification failure must not be collapsed into done.
- User correction after implementation creates a new validation revision unless it is purely explanatory.
- The user may correct drift in outcome language without knowing implementation details.

## Status Flow

```text
executing -> verifying
verifying + passed  -> done
verifying + failed  -> changes_requested
verifying + blocked -> blocked
changes_requested   -> executing after a rework plan is accepted
debugging           -> executing after diagnosis completes
tweaking            -> executing or done after adjustments finish
paused              -> resuming to any active status
```

## Outcome-Language Correction

Accept feedback like:

```text
[component] is wrong.
It currently feels like [current feeling].
I want it to feel more like [target feeling].
```

Translate clear correction feedback internally into implementation changes. If the correction feedback is vague, contrastive, or could point to multiple fixes, stop and clarify before implementing.

When correction feedback is vague, conflicting, or shows behavior drift without enough detail to act safely, route back into clarification-style questioning before more execution. In particular, re-establish:

- expected behavior
- actual behavior
- reproduction or triggering conditions when relevant
- scope of the correction
- which questions are blocking versus non-blocking

Ask the related clarification questions together in one turn rather than one timid question. If the user says the result is "not quite right," "still off," or otherwise reports drift, do not guess at the next implementation step. Clarify the mismatch first, then create or update the next validation revision.

## Lesson Capture Gate

After verification passes, check whether the task involved non-trivial debugging. If any of the following are true, load the global `capture-lessons` skill and use its pattern before final closure:

- The same issue required at least three meaningful fix attempts.
- Repeated debugging was needed to reach the root cause.
- The root cause was non-obvious or involved a tool, framework, state machine, cache, concurrency, or permission issue.

### How to route

1. If the lesson is clearly reusable across modules or projects, use `capture-lessons` to create a new pattern-based skill under `.agents/skills/<pattern-name>/SKILL.md`. Update the skills index if creating a new skill.
2. If the lesson is durable but project-local (e.g., this repo's conventions, scripts, or architecture), store it in workspace memory instead.
3. If the lesson is task-only, write to the task's `decisions.md`.

### Capture boundaries

Do not create a skill for:

- One-off business rules.
- Current module-only details.
- Unverified hypotheses, raw logs, secrets, or credentials.

### Output

When reporting completion, state:

- Whether `capture-lessons` was used.
- Where the lesson was stored (new skill path, workspace memory key, or task decisions).
- If skipped, why the lesson was not reusable or global enough.

If the debugging was trivial or the lesson is one-off, skip this gate.

## Task Archival Expectation

After verification passes and the user accepts (or the task is confirmed done), the script-owned verification path archives the task package rather than destructively cleaning it up. Extract durable decisions and verified lessons first. Preserve the full task package; do not destructively delete. Use `archive-task` only for manual retry of completed active tasks.

## Checkpoint Commit Expectation

After `just-demand-check` passes with no unresolved findings, the main agent should create a local checkpoint commit using the safety gate in `just-demand-execution`. This records that the verified slice passed engineering checks; it does not mean auto-push or irreversible product finality.

Use the script-owned closure path instead of inventing an inline sequence:

```text
python3 .just-demand/scripts/task.py --root . complete-verification <task-id> passed "<summary>"
```

This command records the verification result, applies the checkpoint-commit safety gate, and archives the task when appropriate.

- If later feedback requires a small correction, use a follow-up commit after the next clean check.
- If the direction was fundamentally wrong, prefer a revert commit over history rewrite.
- If feedback becomes repeatedly unstable, mark the task `debugging` or `tweaking` and pause auto-commit until another clean check passes.

## Required Report

When reporting verification, include:

- Commands run.
- Pass/fail result.
- Remaining risks.
- Whether a new validation revision was created.
- Whether a lesson was captured (and where).
- Whether the task is ready for archival.
- Whether checkpoint commit was created, skipped, or blocked, with reason.

### Default Final Report

Unless the task involved debugging, architecture changes, new mechanisms, or explicit analysis is requested, keep the final report brief:

1. **What changed**
2. **Verification result**
3. **Remaining risk or next decision** (if any)

Only include root cause, detailed tradeoffs, Minimum Viable Knowledge, or analogy when the task involved debugging, architecture changes, new mechanisms, or the user explicitly asks for deeper analysis.
