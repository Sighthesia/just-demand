---
name: just-demand-intake
description: Use when the user proposes a new goal, feature, bugfix, design, refactor, research item, UI request, or any unclear work that may become a formal work item. Shapes work into task-ready intake after socratic-clarification has handled requests, bugs, pivots from ordinary Q&A, and other material uncertainty.
---

# Workflow Intake

Clarify the user's need before exposing workflow mechanics.

## Core Rules

- Focus on the user's described outcome, expected behavior, anti-outcomes, constraints, and tradeoffs.
- Use `socratic-clarification` for progressive questioning before shaping new or ambiguous work.
- Do not outrank `socratic-clarification`. Intake starts after clarification has established the intended effect and direction for the current turn.
- Keep the turn user-understandable, but do not use brevity as a reason to skip material uncertainty.
- Prefer the `question` tool for grouped decisions, approvals, and boundary capture when the answer can be expressed as concise options. Use free-text only for phenomena, nuanced descriptions, or answers that cannot be safely reduced to options.
- Do not discuss task packages, repo maps, JSONL, context injection, or subagent mechanics unless the user is explicitly designing those mechanisms.

## Process

1. Restate the user's goal and suspected anti-outcome.
2. Identify the requirement type: UI, workflow, bugfix, architecture, docs, research, or implementation.
3. Extract what the user already specified.
4. Apply the final artifact from `socratic-clarification` when present.
5. Record confirmed expectations, remaining gaps, and non-blocking questions.
6. Promote to a formal work item only after required fields and approval are present.

Record clarification in user-language buckets that can later become task data:

- expected behavior
- actual behavior
- reproduction
- scope
- blocking questions
- non-blocking questions

Treat blocking questions as promotion blockers. Non-blocking questions may stay open if execution can still proceed safely.

## Final Artifact Requirements

For design and implementation work, the intake must include the final artifact before promotion:

- **Final Expected Effect**: user-visible outcome in user language
- **Approach Options**: 2-3 approaches with trade-offs (informational, does not block promotion)
- **Chosen Approach**: selected approach with brief rationale
- **Final Implementation Plan**: ordered steps including verification
- **Validation**: how we will verify the result matches the expected effect
- **Approval**: explicit user approval of the final artifact

Promotion is blocked for design/implementation tasks when Final Expected Effect, Chosen Approach, Final Implementation Plan, or Approval are missing.

## Blocking Questions Policy

A question is blocking when guessing the answer could change implementation path, validation criteria, user-facing behavior, or acceptable scope. Blocking questions include unresolved choices about expected behavior, actual behavior, reproduction conditions, affected scope, anti-outcomes, data loss/risk tolerance, or which tradeoff the user prefers.

Do not demote a question to non-blocking just because a likely answer exists. Only proceed without asking when the user already answered it, the repository has an explicit durable decision, or the implementation is safely reversible and user-visible behavior will not change.

## Question Threshold

Ask implementation questions only when they affect:

- Product behavior or user-visible outcomes
- Architecture decisions or module boundaries
- Compatibility with existing systems or data
- Security, cost, or long-term maintenance

Do not ask about implementation details that are purely engineering preferences when they do not affect the above categories.

## Intake Recording Shape

When `socratic-clarification` has produced a final artifact, record it in this shape:

```text
Final Expected Effect: <user-visible outcome>
Approach Options: <2-3 options with trade-offs>
Chosen Approach: <selected approach and rationale>
Final Implementation Plan: <ordered implementation and verification steps>
Validation: <how the result will be checked>
Approval: <explicit user approval or authorization>
```

Avoid vague placeholders:

```text
Approved.
TBD.
Do the obvious thing.
```

## Questioning Patterns

### Bug, regression, or expected-vs-actual mismatch

Drive toward this shape:

```text
Expected behavior: what should happen.
Actual behavior: what happens instead.
Reproduction: when or how it shows up.
Scope: who, what path, or which environments are affected.
Blocking questions: anything that prevents safe implementation.
```

Preferred prompts:

- "What did you expect to happen here?"
- "What happens now instead?"
- "Can you reproduce it reliably, and if so with which steps or conditions?"
- "Is this isolated or does it affect multiple paths/users/environments?"
- "Which missing detail would make us likely fix the wrong thing?"

For expected-vs-actual mismatches, do not make the user compose the deviation description. Default to leading with the two-stage option flow from `socratic-clarification` (Proactive Deviation Options): Stage 1 options to locate the deviation dimension, Stage 2 "currently X, want Y or Z" contrast options to pin the target state. Reserve free-text for reproduction and other open-ended phenomena.

### Feature, workflow, or implementation request

Drive toward this shape:

```text
Desired outcome: what should be true when done.
Scope: what is in and out.
Anti-outcome: what would feel wrong even if technically complete.
Blocking questions: unresolved choices that would change the implementation path.
Non-blocking questions: polish or preference details that can remain open.
```

Preferred prompts:

- "What should a successful result let you do that you cannot do now?"
- "What is the smallest acceptable scope for this pass?"
- "What should we explicitly avoid changing?"
- "Which choice would materially change the implementation path if guessed wrong?"
- "Which details are nice-to-have and can stay open until execution?"

## Progressive Clarification Routing

When the user proposes a need, request, feature, design/refactor, bug report, symptom, phenomenon, vague correction, or expected-vs-actual mismatch, load `socratic-clarification` before shaping or promoting work. That skill owns progressive questioning, overlooked boundary discovery, final expected effect, and final implementation plan.

## Routing Rule

When the clarified work will consume long context, do not keep it in the main session after shaping. Promote it to a formal work item and route execution through `just-demand-*` subagents.

Typical triggers:

- multi-file implementation
- broad codebase reading
- complex UI or interaction work with many states
- extended verification or review
- research that would produce long notes or comparisons

Before any later implementation or verification phase begins, the promoted task must have its current task context files written. The main agent must not improvise by directly editing code from intake context alone.

## High-Detail Requests

For detailed UI or interaction requests, do not restart discovery. Use this pattern:

```text
Known: what the user already specified.
Gaps: the few details likely to cause drift.
Default: the agent's recommended behavior if the user does not care.
```

Before implementation, provide a low-reading-cost validation summary:

- One-sentence intent.
- Five-point quick check.
- Effect validation card when the request is visual or interaction-heavy.
