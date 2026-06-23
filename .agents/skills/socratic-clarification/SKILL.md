---
name: socratic-clarification
description: Use when the user proposes a need, request, feature, design/refactor, bug report, symptom, phenomenon, vague correction, or expected-vs-actual mismatch before implementation. This is the second-priority skill after using-just-demand, including when a conversation pivots from ordinary Q&A to a concrete request, bug, or correction.
---

# Socratic Clarification

Force progressive clarification and design approval before implementation. This is a hard gate, not optional guidance, but it should feel like a short decision surface: default to options, defaults, and the smallest sufficient artifact before asking for prose.

This skill is the required second step after `using-just-demand`. When a turn pivots from Q&A into a request, bug, correction, or mismatch, reset here before intake, execution, or verification. In skill-only fallback mode, self-enforce the same rule: approval enters intake/formal-task flow, not inline editing, and codebase investigation (inspecting, searching, reading, tracing, or investigating files for implementation) is also execution work that must wait for a formal task.

<HARD-GATE>
Do NOT promote a task, dispatch a subagent, edit files, or finalize an implementation plan until you have presented a final expected effect, compared 2-3 approaches, captured the chosen approach and final implementation plan, and received explicit user approval. This applies to EVERY request regardless of perceived simplicity. Keep that surface compact: lead with the user-visible effect, then one recommended default, then a small option set or decision card when needed.
</HARD-GATE>

## Anti-Pattern: "This Is Too Simple To Need Clarification"

Every request goes through this process. "Simple" requests still need a short final artifact and explicit approval.

## Anti-Rationalization Rules

Do NOT rationalize skipping any of these:

- "I already know what the user wants" -- you still present the final artifact and get approval.
- "The user said to just do it" -- you still present the final expected effect and get explicit approval before code changes.
- "This is a small change" -- small changes cause mismatches too. Present the artifact.
- "I can fix this while clarifying" -- no. Clarify first, then implement.
- "The user is in a hurry" -- a short artifact is faster than a mismatched implementation.
- "I'll clarify as I go" -- no. Blocking questions are promotion blockers.

## Anti-Sycophancy And Premise Check

When the user frames the work around a preferred variable, parameter, suspected root cause, or preferred solution family, do not adopt that frame by default.

Before continuing inside the user's frame, explicitly test:

- whether the framed variable is actually the dominant factor
- whether a structural limitation or experiment flaw better explains the phenomenon
- whether the current evidence can distinguish between a tuning problem and a wrong premise

If the user's frame is weak, incomplete, or contradicted by stronger explanations, challenge the premise before proposing narrower advice.

## Checklist

You MUST complete these steps in order. Do not skip steps.

1. **Identify trigger** -- determine what the user actually needs (feature, bugfix, refactor, design, investigation, correction).
2. **Round 1: Intent and expected outcome** -- clarify what success looks like in user language, and capture the shortest decision card that still lets the user approve or redirect.
3. **Round 2: Current reality** -- when relevant, clarify what happens now instead.
4. **Round 3: Constraints and boundaries** -- explore tradeoffs, edge cases, anti-outcomes.
5. **Propose 2-3 approaches** -- with trade-offs and your recommendation, using defaults and concise options before asking for free-text explanation.
6. **Capture final artifact** -- final expected effect, scope, anti-outcomes, chosen approach, final implementation plan, validation criteria, open questions.
7. **Get user approval** -- explicit approval on the final artifact before any execution.
8. **Promote or execute** -- only after approval, promote to a formal task when no ready task exists; begin execution only when formal execution readiness is satisfied.

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
  |-- yes --> promote to task, or execute only if a formal task is already ready
```

## Progressive Questioning Rounds

Use the rounds as a state machine. Ask only the rounds that still contain unknowns. If a later answer opens a new uncertainty, loop back to the relevant round.

### Long-Context Reset Trigger

If the conversation has spent 3 or more turns on the same phenomenon, or if the user keeps providing new samples under the same assumed explanation, pause incremental answering and reset the problem model before continuing.

Minimum reset structure:

```text
Established: what the current evidence supports.
Uncertain: what the evidence still cannot distinguish.
Assumption at risk: which premise may be wrong.
Next best move: whether to continue comparing options or change the frame.
```

Do this before proposing another narrow adjustment, another comparison, or another interpretation inside the same frame.

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

For analysis or experiment-review work, also clarify whether the data can support the intended conclusion:

- "What evidence would distinguish a tuning issue from a structural limitation?"
- "Is the experiment setup consistent enough to compare runs directly?"
- "What alternative explanation would invalidate the current comparison?"

### Round 3: Constraints, Tradeoffs, and Edge Cases

Explore boundaries and risks:

- "What constraints or limitations should we respect?"
- "What should we explicitly avoid changing?"
- "Which choice would materially change the implementation path if guessed wrong?"
- "What are the security, cost, or long-term maintenance considerations?"

## 2-3 Approach Comparison

After gathering enough context, propose 2-3 different approaches with trade-offs. Present your recommendation and explain why.

This proposal is the highest-information moment of the turn, so it MUST follow the Output Style rules in `using-just-demand` (BLUF, scannable, user language). The user is the product manager and architect, not the implementer.

Default to a low-reading-cost decision card, not a long analysis. The user should usually be able to approve, reject, or adjust the recommendation after reading one compact block.

```text
Decision card:
- Intent: <one sentence in user language>
- Recommended default: <the path you would take if the user does not care>
- Why this default: <one practical reason>
- User action: approve, choose another option, or correct the intent
- Confidence: <high|medium|low, only when it helps calibrate trust>
- Escalation reason: <why this needs user input instead of agent decision, or "none">
```

- **Lead with effect, not implementation.** The first line of the proposal states what the user will be able to do, in user language. Do NOT open with an internal concern, file name, type, or dependency.
- **Subject is the user or the system's observable behavior**, never the implementation artifact. Write "you get X" / "the system does Y", not "the CLI module calls Z".
- **Trade-offs describe user-facing consequences** (speed, safety, cost, what could go wrong, what it feels like), not raw technical attributes. "Smaller change, but if it crashes mid-run it may stay in auto mode" beats "reuses global Arc<Mutex> mode".
- **Name the failure mode.** Each option should say what bad outcome it risks in practical terms, so the user is not left inferring the downside.
- **Implementation detail (files, dependencies, internal structure, symbol names) does not belong in the main proposal.** Fold it into an optional expand section the user can skip, or omit entirely.

```text
Option matrix:
| Option | Best for | Pros | Cons | Failure mode |
| --- | --- | --- | --- | --- |
| A | <when to choose it> | <benefit> | <cost> | <what wrong looks like> |
```

Use the table form when it is easier to compare. Use the shorter list form when there are only two simple options.

```text
Approach A: <name>
  - What you get: <user-visible effect in user language>
  - Pros: <why this is good for the user>
  - Cons: <what the user gives up>
  - Failure mode: <what wrong looks like in practice>
  - Recommended: <yes/no with reasoning>

Approach B: <name>
  - What you get: <user-visible effect>
  - Pros: <why this is good for the user>
  - Cons: <what the user gives up>
  - Failure mode: <what wrong looks like in practice>

Approach C: <name> (optional)
  - What you get: <user-visible effect>
  - Pros: <why this is good for the user>
  - Cons: <what the user gives up>
  - Failure mode: <what wrong looks like in practice>
```

Wait for the user to choose or approve your recommendation before proceeding.

### Analysis And Tuning Tasks

For analysis, diagnosis, tuning, experiment review, or "which parameter is best" requests, do not jump straight to parameter comparison. First compare 2-3 explanation paths when the premise is not yet secure.

Before continuing a long analysis thread or recommending more tuning, summarize the current state using an uncertainty-aware conclusion shape. This keeps the problem model stable and prevents early guesses from turning into assumed facts.

Required shape:

```text
Conclusion: <current best explanation or recommendation>
Confidence: <high|medium|low>
Evidence: <key observations that directly support it>
Alternative explanations: <other plausible explanations still alive>
