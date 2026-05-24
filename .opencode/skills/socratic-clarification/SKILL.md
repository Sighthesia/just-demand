---
name: socratic-clarification
description: Use when the user proposes a need, request, feature, design/refactor, bug report, symptom, phenomenon, vague correction, or expected-vs-actual mismatch before implementation.
---

# Socratic Clarification

Force progressive clarification and design approval before any implementation work begins. This is a hard gate, not optional guidance.

<HARD-GATE>
Do NOT promote a task, dispatch a subagent, edit files, or finalize an implementation plan until you have presented a final expected effect, compared 2-3 approaches, captured the chosen approach and final implementation plan, and received explicit user approval. This applies to EVERY request regardless of perceived simplicity.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need Clarification"

Every request goes through this process. A one-line fix, a config change, a single-function addition -- all of them. "Simple" requests are where unexamined assumptions cause the most wasted work. The clarification can be short (a few sentences for truly simple requests), but you MUST present the final artifact and get approval.

## Anti-Rationalization Rules

Do NOT rationalize skipping any of these:

- "I already know what the user wants" -- you still present the final artifact and get approval.
- "The user said to just do it" -- you still present the final expected effect and get explicit approval before code changes.
- "This is a small change" -- small changes cause mismatches too. Present the artifact.
- "I can fix this while clarifying" -- no. Clarify first, then implement.
- "The user is in a hurry" -- a short artifact is faster than a mismatched implementation.
- "I'll clarify as I go" -- no. Blocking questions are promotion blockers.

## Checklist

You MUST complete these steps in order. Do not skip steps.

1. **Identify trigger** -- determine what the user actually needs (feature, bugfix, refactor, design, investigation, correction).
2. **Round 1: Intent and expected outcome** -- clarify what success looks like in user language.
3. **Round 2: Current reality** -- when relevant, clarify what happens now instead.
4. **Round 3: Constraints and boundaries** -- explore tradeoffs, edge cases, anti-outcomes.
5. **Propose 2-3 approaches** -- with trade-offs and your recommendation.
6. **Capture final artifact** -- final expected effect, scope, anti-outcomes, chosen approach, final implementation plan, validation criteria, open questions.
7. **Get user approval** -- explicit approval on the final artifact before any execution.
8. **Promote or execute** -- only after approval, promote to formal task or begin execution.

## Process Flow

```text
Identify trigger
  |
  v
Round 1: Intent & expected outcome
  |
  v
Round 2: Current reality (if relevant)
  |
  v
Round 3: Constraints & boundaries
  |
  v
Propose 2-3 approaches with recommendation
  |
  v
User chooses or approves approach
  |
  v
Capture final artifact
  |
  v
User approves final artifact?
  |-- no --> revise artifact, re-approve
  |-- yes --> promote to task or begin execution
```

## Progressive Questioning Rounds

Use the rounds as a state machine. Ask only the rounds that still contain unknowns. If a later answer opens a new uncertainty, loop back to the relevant round.

### Round 1: Intent and Expected Outcome

One primary question per turn when the user must decide. Use multiple choice or recommended defaults when possible.

- "What should a successful result let you do that you cannot do now?"
- "What is the desired end state when this is complete?"
- "What would feel wrong even if technically complete?"
- "What is the smallest acceptable scope for this pass?"

Minimum output of this round:

```text
User wants: <goal in user language>
Expected effect: <observable outcome>
Success criteria: <how the user will judge it>
Anti-outcome: <what would feel wrong>
```

### Round 2: Current Reality and Phenomenon

When relevant, clarify the current state:

- "What happens now instead of the desired behavior?"
- "Can you reproduce it reliably, and if so with which steps or conditions?"
- "Is this isolated or does it affect multiple paths/users/environments?"

### Round 3: Constraints, Tradeoffs, and Edge Cases

Explore boundaries and risks:

- "What constraints or limitations should we respect?"
- "What should we explicitly avoid changing?"
- "Which choice would materially change the implementation path if guessed wrong?"
- "What are the security, cost, or long-term maintenance considerations?"

## 2-3 Approach Comparison

After gathering enough context, propose 2-3 different approaches with trade-offs. Present your recommendation and explain why.

```text
Approach A: <name>
  - What it does: <description>
  - Trade-offs: <pros/cons>
  - Recommended: <yes/no with reasoning>

Approach B: <name>
  - What it does: <description>
  - Trade-offs: <pros/cons>

Approach C: <name> (optional)
  - What it does: <description>
  - Trade-offs: <pros/cons>
```

Wait for the user to choose or approve your recommendation before proceeding.

## Final Artifact Shape

Before execution, capture this artifact and get explicit user approval:

```text
Final expected effect:
- <user-visible outcome in user language>

Scope:
- In: <what is included>
- Out: <what is explicitly excluded>

Anti-outcomes:
- <what would feel wrong even if technically complete>

Chosen approach:
- <selected approach with brief rationale>

Final implementation plan:
1. <step>
2. <step>
3. <verification step>

Validation:
- <how we will verify the result matches the expected effect>

Open questions:
- <any remaining non-blocking questions, or "none">
```

## Questioning Patterns

### Bug, Regression, or Expected-vs-Actual Mismatch

Drive toward this shape:

```text
Expected behavior: what should happen.
Actual behavior: what happens instead.
Reproduction: when or how it shows up.
Scope: who, what path, or which environments are affected.
Blocking questions: anything that prevents safe implementation.
```

### Feature, Workflow, or Implementation Request

Drive toward this shape:

```text
Desired outcome: what should be true when done.
Scope: what is in and out.
Anti-outcome: what would feel wrong even if technically complete.
Blocking questions: unresolved choices that would change the implementation path.
Non-blocking questions: polish or preference details that can remain open.
```

### Vague Correction Feedback

When correction feedback is vague, contrastive, or could point to multiple fixes:

1. Restate the correction feedback in your own words
2. Ask for clarification on the specific mismatch
3. Explore the expected vs. actual behavior
4. Determine blocking vs. non-blocking questions
5. Summarize the correction scope before proceeding

## Question Threshold

Ask implementation questions only when they affect:

- Product behavior or user-visible outcomes
- Architecture decisions or module boundaries
- Compatibility with existing systems or data
- Security, cost, or long-term maintenance

Do not ask about implementation details that are purely engineering preferences when they do not affect the above categories.

## Routing Rule

When the clarified work will consume long context, promote it to a formal work item and route execution through `just-demand-*` subagents. Do not keep long-context work in the main session.

## No Main-Session Injection

This skill does not inject workflow mechanics or bootstrap text into the main session. It provides clarification guidance that the agent applies when triggering conditions are met.
