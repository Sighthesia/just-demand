---
name: just-demand-intake
description: Use when the user proposes a new goal, feature, bugfix, design, refactor, research item, UI request, or any unclear work that may become a formal work item. Clarifies the user's need before task creation.
---

# Workflow Intake

Clarify the user's need before exposing workflow mechanics.

## Core Rules

- Focus on the user's described outcome, expected behavior, anti-outcomes, constraints, and tradeoffs.
- Advance one user-understandable topic per turn.
- Ask several related questions when the topic needs exploration.
- Prefer choices, contrasts, and recommended defaults over open-ended interrogation.
- Do not discuss task packages, repo maps, JSONL, context injection, or subagent mechanics unless the user is explicitly designing those mechanisms.

## Process

1. Restate the user's goal and suspected anti-outcome.
2. Identify the requirement type: UI, workflow, bugfix, architecture, docs, research, or implementation.
3. Extract what the user already specified.
4. Ask only questions whose answers would prevent user-visible mismatch.
5. Summarize confirmed expectations and remaining gaps.
6. Suggest promoting to a formal work item only after the user confirms the direction.

Record clarification in user-language buckets that can later become task data:

- expected behavior
- actual behavior
- reproduction
- scope
- blocking questions
- non-blocking questions

Treat blocking questions as promotion blockers. Non-blocking questions may stay open if execution can still proceed safely.

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
