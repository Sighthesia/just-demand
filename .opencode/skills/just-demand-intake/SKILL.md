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
