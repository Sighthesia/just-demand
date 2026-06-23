---
name: just-demand-verification
description: Use after implementation, after just-demand-tester output, when verification fails, when the user gives correction feedback, or before claiming a workflow task is done.
---

# Workflow Verification

Verify outcomes against the task brief and active validation revision.

## Core Rules

- No completion claim without fresh verification evidence.
- Verification failure must not be collapsed into done.
- User correction after implementation creates a new validation revision unless it is purely explanatory.
- The user may correct drift in outcome language without knowing implementation details.
- When `just-demand-tester` is used, treat its report as the active verification record: it should name findings, any low-risk fixes applied, verification results, and residual risk.

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

### Visual Quality Corrections

For UI, animation, layout, reveal, overflow, clipping, masking, or quality/feel feedback, treat "works but feels bad" as a validation failure of the chosen approach, not as a routine polish tweak. Examples include "裁剪效果不好", "still clips", "foreground appears before the glass/background", "janky", "not synchronized", or "hard cut".

When this happens, stop extending the same technique. Re-open the solution-shape choice through `socratic-clarification` and compare the relevant user-visible alternatives:

- containment: keep content hidden outside bounds
- synchronized entrance: make foreground move/reveal with the container
- layout/reflow: change spacing, anchoring, or available size so clipping is not the visible effect

Only continue implementation after the next expected effect and final implementation plan name the chosen feel. If a clip remains, verify whether it is the intended primary effect or only a safety guardrail.

## Progressive Clarification Routing

When correction feedback is vague, conflicting, or shows behavior drift without enough detail to act safely, load `socratic-clarification` before more implementation. The next validation revision must be based on the clarified final expected effect and final implementation plan, not a guessed fix.

## Analysis Conclusion Confidence Gate

For analysis, diagnosis, tuning, experiment-review, root-cause, or "which option is best" conclusions, do not present the result as an unconditional fact unless the evidence truly closes the question.

Analysis-style conclusions must explicitly cover:

- **Confidence**: high, medium, or low
- **Evidence basis**: which observations directly support the conclusion
- **Alternative explanations**: what else could explain the same data
- **Falsifier**: what future evidence would weaken or overturn the current conclusion

Purpose:

- prevent stage-by-stage guesses from hardening into fake certainty
- make evidence strength visible to the user
- resist long-context drift where an early hypothesis gets repeated until it sounds proven
- resist sycophancy when the user strongly frames the problem around a preferred variable or explanation

If the available evidence cannot distinguish between a tuning problem, a structural limitation, a bad metric, or an inconsistent experiment setup, say so directly. In that case, verification should prefer "insufficient evidence" or "current best explanation with medium/low confidence" over a falsely definitive conclusion.

### Required Shape For Analysis Conclusions

Use this compact structure when the task result is primarily analytical rather than a code change:

```text
Conclusion: <current best explanation or recommendation>
Confidence: <high|medium|low>
Evidence: <key observations that directly support it>
Alternative explanations: <other plausible explanations still alive>
Falsifier: <what next evidence would weaken or overturn this conclusion>
```

This does not require long prose. Keep it scannable, but do not omit the uncertainty boundary.

## Lesson Capture Gate

After verification passes, check whether the task involved non-trivial debugging. If any of the following are true, load the project-native `capture-lessons` skill and use its pattern before final closure:

- The same issue required at least three meaningful fix attempts.
- Repeated debugging was needed to reach the root cause.
- The root cause was non-obvious or involved a tool, framework, state machine, cache, concurrency, or permission issue.

### How to route

1. If the lesson is clearly reusable across modules or projects, use the project-native `capture-lessons` skill to create a new pattern-based skill under `.opencode/skills/<pattern-name>/SKILL.md`.
2. If the lesson is durable but Just Demand-specific, extend the relevant existing `.opencode/skills/` guidance instead of creating a memory layer.
3. If the lesson is task-only, keep it in the task archive and task-local notes.

### Capture boundaries

Do not create a skill for:

- One-off business rules.
- Current module-only details.
- Unverified hypotheses, raw logs, secrets, or credentials.

### Output

When reporting completion, state:

- Whether `capture-lessons` was used.
- Where the lesson was stored (new skill path, updated skill, or archive-only).
- If skipped, why the lesson was not reusable or skill-worthy enough.

If the debugging was trivial or the lesson is one-off, skip this gate.

## Task Archival Expectation

After verification passes and the user accepts (or the task is confirmed done), the script-owned verification path archives the task package rather than destructively cleaning it up. Extract durable decisions and verified lessons first. Preserve the full task package; do not destructively delete. Use `archive-task` only for manual retry of completed active tasks.

## Checkpoint Commit Expectation

After `just-demand-tester` passes with no unresolved findings, the main agent should create a local checkpoint commit using the safety gate in `just-demand-execution`. This records that the verified slice passed engineering checks; it does not mean auto-push or irreversible product finality.

Use the script-owned closure path instead of inventing an inline sequence:

```text
just-demand . complete-verification <task-id> passed "<summary>"
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
- For analysis-style conclusions: confidence, live alternative explanations, and what evidence would overturn the current conclusion.

When the verification work is coming from `just-demand-tester`, preserve the tester's short report shape and use it as the evidence record for main-agent closeout:

- **Findings**: what passed or failed.
- **Fixes applied**: low-risk local fixes only, if any.
- **Verification results**: commands or checks and their outcomes.
- **Residual risk**: anything that still might feel wrong even if the checks pass.

### Default Final Report

This is the task-closure specialization of the global Output Style rule in `using-just-demand`. Users skim; output past ~300 characters is usually not read closely. Write the final report bottom-line-up-front (BLUF) and scannable:

1. **First line is the conclusion.** State the outcome in one sentence before any context. The user should get the result from line one alone.
2. **Then a validation card**: expected effect, anti-outcome, visible/diagram acceptance, visible/expression side effect, checks passed, remaining risk, and user action. Keep it short. For UI/layout/animation and diagram work, user-facing behavior or diagram meaning comes before routine engineering checks.
3. **Then a few terse bullets if needed**: what changed, verification result, remaining risk or next decision. Lead each bullet with the information-carrying word. For "what changed", describe the effect and design intent and reference changed files/symbols by name; do not paste implementation code line by line unless the user asks or a snippet is needed to pin a decision.
4. **Default target: keep the whole report under ~300 characters.** This is a target for the main body, not a hard cut. If a required item does not fit, move it into the optional expand section below -- never drop a safety-relevant item (remaining risk, unverified area, checkpoint-commit status) just to hit the length.

Use this shape by default, and keep the conclusion/validation card as the first screen the user sees:

```text
<Conclusion in one sentence.>

Validation card:
- Expected: <user-visible result>
- Anti-outcome: <what should not happen>
- Visible acceptance: <what the user can see, feel, or operate>
- Visible side effect: <expected screen/operational side effect, or none>
- Diagram acceptance: <for diagram work, what the user can identify from the diagram>
- Expression side effect: <for diagram work, what the diagram emphasizes, collapses, hides, or intentionally omits>
- Checked: <tests/review passed; omit routine detail from first screen unless failed>
- Risk: <remaining non-visible risk or none>
- User action: <none / review / choose / approve>
```

When the verification work is coming from `just-demand-tester`, preserve the tester's short report shape and use it as the evidence record for main-agent closeout. The tester report should still start with the user-visible effect/result, not with command transcripts:

- **Findings**: what passed or failed.
- **Fixes applied**: low-risk local fixes only, if any.
- **Verification results**: commands or checks and their outcomes.
- **Residual risk**: anything that still might feel wrong even if the checks pass.

Put non-essential detail (root cause, detailed tradeoffs, Minimum Viable Knowledge, analogy, full command transcripts) in an optional expand section AFTER the bullets, clearly marked so the user can stop reading once the bullets are done. Only surface that detail inline when the task involved debugging, architecture changes, new mechanisms, or the user explicitly asks for deeper analysis.
