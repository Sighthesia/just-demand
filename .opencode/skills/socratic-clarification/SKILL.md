---
name: socratic-clarification
description: Use when the user proposes a need, request, feature, design/refactor, bug report, symptom, phenomenon, vague correction, or expected-vs-actual mismatch before implementation. This is the second-priority skill after using-just-demand, including when a conversation pivots from ordinary Q&A to a concrete request, bug, or correction.
---

# Socratic Clarification

Force progressive clarification and design approval before any implementation work begins. This is a hard gate, not optional guidance.

This skill is the required second routing step after `using-just-demand`. If a turn changes from ordinary Q&A into concrete work, bug fixing, mismatch analysis, or correction feedback, this skill takes priority before intake, execution, or verification routing continues.

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

Use the `question` tool to gather intent and expected outcomes when the answer can be expressed as options. Group related decisions when feasible.

- "What should a successful result let you do that you cannot do now?"
- "What is the desired end state when this is complete?"
- "What would feel wrong even if technically complete?"
- "What is the smallest acceptable scope for this pass?"

When multiple intent questions are independent, batch them into one `question` call. For example:

```text
question: "What success means for this request:"
options: ["Fix the immediate bug", "Improve the feature", "Refactor the component", "Add new capability"]
```

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

## Proactive Deviation Options

When the work shows a deviation between actual and expected effect -- a bug, regression, mismatch, low fidelity, or any correction feedback (vague or detailed) -- the DEFAULT is for YOU to lead with options, not to wait for the user to write a description. This applies to both first-pass clarification and post-implementation correction.

This is a hard default, not a conditional. Do NOT fall back to "let the user describe the deviation first" just because the deviation is hard to express. Infer the likely deviation from the implementation and the expected effect, then present it as a two-stage option flow:

1. **Stage 1 - Locate the deviation dimension.** Use the `question` tool to offer the dimensions the deviation likely lives in (e.g., color, spacing, motion/timing, copy, layout, logic, scope, data). The user picks the dimension instead of composing a description.
2. **Stage 2 - Pin the target state.** For the chosen dimension, present a contrast: "Currently it is X; do you want Y or Z?" The user selects the target state instead of articulating it from scratch.

Rules:

- Base the dimension options on a real inference from the implementation and expected effect, not random guesses. Bad options add reading cost.
- Keep each stage to 2-5 scannable options.
- Always include a free-text escape hatch for when no option fits.
- Do NOT force option form onto open-ended phenomena (reproduction steps, environmental conditions, how something feels). Those stay free-text per the patterns below.

The goal is to minimize what the user has to type: most of the time they should be able to click through Stage 1 and Stage 2 rather than write prose.

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

When correction feedback is vague, contrastive, or could point to multiple fixes, do NOT push the user to write a fuller description. Lead with the two-stage option flow from Proactive Deviation Options:

1. Restate the correction feedback in your own words
2. Proactively present Stage 1 dimension options to locate the deviation, then Stage 2 contrast options to pin the target state
3. Use those answers to fix the expected vs. actual gap; only ask for free-text when no option fits
4. Determine blocking vs. non-blocking questions
5. Summarize the correction scope before proceeding

## Question Threshold

Ask implementation questions only when they affect:

- Product behavior or user-visible outcomes
- Architecture decisions or module boundaries
- Compatibility with existing systems or data
- Security, cost, or long-term maintenance

Do not ask about implementation details that are purely engineering preferences when they do not affect the above categories.

## Question Tool Preference

Use the `question` tool proactively for structured clarification when the answer can be expressed as concise options, choices, or approvals. Prefer grouped question rounds over one-question-at-a-time text prompting.

For deviation and correction scenarios specifically, leading with options is the default, not a conditional: proactively infer and present options (see Proactive Deviation Options) instead of waiting for the user to describe the mismatch. Falling back to "let the user describe it first" is only acceptable for the open-ended phenomena listed under "When to use free-text".

### When to use the question tool

- **Grouped decisions**: When multiple tightly-related blocking uncertainties can be captured in one structured call (e.g., scope choices, boundary decisions, tradeoff preferences).
- **Approvals**: When seeking explicit approval on approaches, final artifacts, or implementation plans.
- **Boundary capture**: When exploring constraints, anti-outcomes, or edge cases that can be reduced to option sets.
- **Tradeoff selection**: When presenting 2-3 approaches and the user needs to choose.
- **Progress checks**: When confirming understanding or validating assumptions before proceeding.

### When to use free-text

- **Symptom description**: When the user needs to describe what happens, how it feels, or what they observe.
- **Phenomenon description**: When explaining reproduction steps, conditions, or environmental details.
- **Nuanced explanations**: When the answer requires context, reasoning, or cannot be safely reduced to options.
- **Open-ended exploration**: When the uncertainty is too broad to predefine choices.

### Grouping strategy

When several blocking uncertainties exist:

1. Group tightly-related questions into one `question` call when the answers are independent and the user can respond without excessive cognitive load.
2. Keep question groups focused: 2-5 options per question, 1-3 questions per call maximum.
3. If questions are sequential (each answer affects the next), ask them in sequence but still prefer the `question` tool for each.
4. Always allow a free-text escape hatch when options feel restrictive.

### Approval capture

Use the `question` tool for explicit approval at key checkpoints:

- After presenting 2-3 approaches with trade-offs.
- After capturing the final artifact.
- When confirming scope or boundary decisions.

Example approval pattern:

```text
question: "Approach A is recommended for speed. Approve?"
options: ["Approach A: direct implementation", "Approach B: staged implementation", "Approach C: different approach"]
```

### Question prompt brevity

Keep `question` tool prompt text short and scannable. Do NOT dump full implementation plans, long descriptions, or verbose context into the prompt text. The prompt should be a concise label or summary. Full details belong in the chat message preceding the question tool call, not inside the tool prompt itself.

Bad: a 300-word plan pasted into the question prompt field.
Good: a one-sentence summary in the prompt, with the full plan in the preceding chat message.

## Routing Rule

When the clarified work will consume long context, promote it to a formal work item and route execution through `just-demand-*` subagents. Do not keep long-context work in the main session.

## No Main-Session Injection

This skill does not inject workflow mechanics or bootstrap text into the main session. It provides clarification guidance that the agent applies when triggering conditions are met.
