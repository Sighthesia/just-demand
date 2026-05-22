---
name: workflow-verification
description: Use after implementation, after workflow-check output, when verification fails, when the user gives correction feedback, or before claiming a workflow task is done.
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

Translate that internally into implementation changes. Ask only contrast questions when the feedback is ambiguous.

## Lesson Capture Gate

After verification passes, check whether the task involved non-trivial debugging. If any of the following are true, run a lesson-capture gate before final closure:

- The same issue required at least two meaningful fix attempts.
- Repeated debugging was needed to reach the root cause.
- The root cause was non-obvious or involved a tool, framework, state machine, cache, concurrency, or permission issue.

### Capture rules

- Capture only abstract, reusable knowledge: diagnostic order, symptoms, likely causes, reliable fixes, avoid-this paths, environmental or tool constraints.
- Write to the most relevant skill when the pattern is clearly reusable across tasks or repositories.
- If not clearly global, write to task `decisions.md` or workspace memory instead.
- Never store secrets, raw private logs, one-off business specifics, or unverified guesses.
- Use the pattern shape from the `capture-lessons` skill when writing to a skill.

If the debugging was trivial or the lesson is one-off, skip this gate.

## Task Archival Expectation

After verification passes and the user accepts (or the task is confirmed done), the script-owned verification path archives the task package rather than destructively cleaning it up. Extract durable decisions and verified lessons first. Preserve the full task package; do not destructively delete. Use `archive-task` only for manual retry of completed active tasks.

## Required Report

When reporting verification, include:

- Commands run.
- Pass/fail result.
- Remaining risks.
- Whether a new validation revision was created.
- Whether a lesson was captured (and where).
- Whether the task is ready for archival.
