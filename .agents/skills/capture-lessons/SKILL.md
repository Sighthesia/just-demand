---
name: capture-lessons
description: Use after verified non-trivial debugging or a reusable workflow lesson to convert experience into a skill, extend an existing skill, or leave the result archived.
---

# Skill: capture-lessons

Turn hard-won experience into retrieval-friendly skill guidance.

## When to use

- After verification passes and the work exposed a reusable pattern.
- After repeated debugging, a tool/state-machine trap, or an architectural mistake that is likely to recur.
- When a task produced a lesson that should shape future Just Demand behavior.

## Choose the destination

1. **New skill**: the lesson is portable across modules, projects, or repos.
2. **Extend an existing skill**: the lesson refines current Just Demand workflow guidance.
3. **Archive only**: the lesson is task-specific, one-off, or not yet reusable.

## Capture shape

Write lessons as instructions that help the next agent retrieve and apply them quickly:

- Name the trigger conditions.
- State the user-visible failure mode or success cue.
- Give the preferred action in Just Demand terms.
- Keep the description short enough to scan during future routing.

## Boundaries

- Do not capture raw logs, secrets, or unverified guesses.
- Do not turn one-off business detail into a reusable skill.
- Preserve task archives as the historical record for task-only context.

## Outcome

The result of capture-lessons should be one of:

- a new or updated skill under `.opencode/skills/`
- an archive-only lesson recorded with the task
- no change when the experience is not yet reusable
