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

Translate clear correction feedback internally into implementation changes. If the correction feedback is vague, conflicting, or could point to multiple fixes, stop and route back to `socratic-clarification` before implementing.

Do not wait for the user to write a full description of the deviation. The default is for YOU to lead with options: proactively infer the likely mismatch and present the two-stage option flow from `socratic-clarification` (Proactive Deviation Options) -- Stage 1 locates the deviation dimension, Stage 2 pins the target state via an "currently X, want Y or Z" contrast. The user should be able to click through rather than compose prose; only ask for free-text when no option fits or the phenomenon is open-ended.

When correction feedback is vague, conflicting, or shows behavior drift without enough detail to act safely, load `socratic-clarification` before more execution. The next validation revision must be based on the clarified final expected effect and final implementation plan, not a guessed fix. Re-establish:

- expected behavior
- actual behavior
- reproduction or triggering conditions when relevant
- scope of the correction
- final expected effect and final implementation plan (updated for the correction)
- which questions are blocking versus non-blocking

Use `socratic-clarification` for the questioning cadence. For deviation and correction scenarios, leading with proactively inferred options is the default (see Proactive Deviation Options); use free-text only for phenomena, nuanced descriptions, or answers that cannot be safely reduced to options.

If the user says the result is "not quite right," "still off," or otherwise reports drift, do not guess at the next implementation step. Clarify the mismatch first, then create or update the next validation revision.

## Progressive Clarification Routing

When correction feedback is vague, conflicting, or shows behavior drift without enough detail to act safely, load `socratic-clarification` before more implementation. The next validation revision must be based on the clarified final expected effect and final implementation plan, not a guessed fix.

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

The following items must be COVERED, but coverage means a scannable mention, not a paragraph each. Most collapse to a single line or fold into the optional expand section:

- Commands run.
- Pass/fail result.
- Remaining risks.
- Whether a new validation revision was created.
- Whether a lesson was captured (and where).
- Whether the task is ready for archival.
- Whether checkpoint commit was created, skipped, or blocked, with reason.

### Default Final Report

Users skim; output past ~300 characters is usually not read closely. Write the final report bottom-line-up-front (BLUF) and scannable:

1. **First line is the conclusion.** State the outcome in one sentence before any context. The user should get the result from line one alone.
2. **Then a few terse bullets**: what changed, verification result, remaining risk or next decision. Lead each bullet with the information-carrying word.
3. **Default target: keep the whole report under ~300 characters.** This is a target for the main body, not a hard cut. If a required item does not fit, move it into the optional expand section below -- never drop a safety-relevant item (remaining risk, unverified area, checkpoint-commit status) just to hit the length.

Put non-essential detail (root cause, detailed tradeoffs, Minimum Viable Knowledge, analogy, full command transcripts) in an optional expand section AFTER the bullets, clearly marked so the user can stop reading once the bullets are done. Only surface that detail inline when the task involved debugging, architecture changes, new mechanisms, or the user explicitly asks for deeper analysis.
