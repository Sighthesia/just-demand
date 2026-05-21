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
```

## Outcome-Language Correction

Accept feedback like:

```text
[component] is wrong.
It currently feels like [current feeling].
I want it to feel more like [target feeling].
```

Translate that internally into implementation changes. Ask only contrast questions when the feedback is ambiguous.

## Required Report

When reporting verification, include:

- Commands run.
- Pass/fail result.
- Remaining risks.
- Whether a new validation revision was created.
