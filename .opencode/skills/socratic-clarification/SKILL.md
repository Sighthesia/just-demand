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
- Approval words like `批准`, `继续`, `同意`, `approved`, and `go ahead` only authorize workflow entry and readiness checks; they do not authorize code changes on their own.
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
9. **Reset on pivot** -- when analysis, advice, or diagnosis turns into implementation/code edits, re-open clarification and confirm the new boundary before editing.

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
Decision: continue inside the current frame, or switch to a broader explanation.
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

Default to a low-reading-cost recommendation block, not a long analysis. The user should usually be able to approve, reject, or adjust the recommendation after reading one compact block. Do not surface internal workflow labels like `Decision card` on the first screen; keep the opening block in user language.

```text
Recommendation:
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
Falsifier: <what next evidence would weaken or overturn this conclusion>
```

Use this shape when:

- the user keeps providing new samples under the same framing
- the conversation has already spent 3 or more turns on the same phenomenon
- the user is asking for narrower tuning while the premise is still uncertain

This is not just a reporting nicety. It is a guard against long-context drift, overconfidence, and adopting the user's preferred explanation too early.

Example shapes:

```text
Approach A: Continue local tuning
  - What you get: faster short-term iteration if the premise is already right
  - Trade-offs: wastes time if the real problem is structural or the data is not comparable

Approach B: Validate the premise first
  - What you get: confidence that later tuning advice is solving the right problem
  - Trade-offs: one extra validation step before optimization
  - Recommended: yes, when the current evidence cannot rule out a stronger alternative explanation

Approach C: Reframe the metric
  - What you get: evaluation based on a signal that better matches the real control objective
  - Trade-offs: may change the user's current test habit or reporting format
```

If the evidence suggests the user's metric or experiment cannot answer the stated question, say so directly and recommend a premise-validation or metric-change path before more tuning.

### Visual And Interaction Drift

For UI, animation, layout, reveal, overflow, clipping, masking, or "quality/feel" problems, do not collapse the symptom into the first containment fix. The approach comparison must distinguish user-visible solution shapes when they would feel different:

- **Containment**: clip, hide, mask, or delay drawing so the bad state is not visible. Good for strict bounds; risky when it feels like hard cutting.
- **Synchronized entrance**: make foreground content follow the same expansion, anchor, timing, or direction as its background. Good when the issue is content arriving before its container.
- **Layout/reflow**: change spacing, anchoring, available size, or row reveal so the content naturally fits. Good when clipping would make text or controls feel broken.

If the user's anti-outcome mentions hard cuts, visible clipping, premature content, jank, mismatch between foreground/background, or "not good quality", treat the approach choice as blocking. Ask the user to approve the intended feel before implementing.

Do not present a containment fix as the default just because it is easiest to verify. If containment remains as a safety boundary, name the primary user-visible behavior separately, such as "slide in from the tray anchor with clip only as a guardrail".

For UI, layout, animation, reveal, overflow, clipping, masking, or quality/feel approvals, the approval surface is a **visible-effect card**, not an engineering-plan card. The first screen should let the user answer: "Is this the behavior I want?"

- Lead with the expected on-screen phenomenon, not files, tests, or implementation steps.
- Include a compact current-vs-target ASCII diagram when layout, height, padding, anchor, parent-container impact, overflow, reveal direction, or motion shape matters.
- Prefer `Touchpoints` over verbose scope in the user-facing card: one short line naming concrete files/modules/components when known, plus explicit exclusions.
- Prefer `Visible acceptance` over validation in the user-facing card: only what the user can see, feel, or operate to confirm the result.
- Treat routine engineering checks as agent obligations. Tests, builds, lint, JSON validation, and diff checks belong in execution/final-report detail unless they fail or require user action.
- Prefer `Visible side effect` over risk for expected side effects. Describe the screen phenomenon, such as "the dockzone grows while lyrics are shown"; do not introduce an unchosen alternate solution there.

Use this compact shape when a UI/layout/animation approval would otherwise be ambiguous:

```text
Recommended: <one sentence describing the visible effect>

Current:
+-- <component/region> h=<current height> --+
| <current visible problem>                  |
+--------------------------------------------+

Target:
+-- <component/region> h=<target/content> ---+
| padTop=<value or existing variable>         |
| <primary content>                           |
| <secondary/revealed content>                |
| padBottom=<value or existing variable>      |
+--------------------------------------------+
<parent or surrounding region effect>

Touchpoints: `<file/module>` and `<component>`; not changing <explicit exclusion>.
Visible acceptance: <1-2 visible or operational checks>.
Visible side effect: <expected on-screen side effect, or none>.
```

### Diagram Intent Cards

For flowcharts, architecture diagrams, state diagrams, data-flow/API diagrams, or other explanatory diagrams, treat the diagram as a decision surface. The user is approving what the diagram communicates, not your drawing mechanics.

- Lead with the intended diagram meaning: relationship, process, boundary, ownership, state transition, or data direction.
- Use a compact ASCII or Mermaid sketch before prose when the shape is easier to validate visually.
- Use `Diagram acceptance` instead of generic validation: what the user should be able to identify by looking at the diagram.
- Use `Expression side effect` instead of risk when the concern is representational: what the diagram emphasizes, collapses, hides, or intentionally omits.
- Keep routine engineering checks out of the first-screen diagram approval unless they failed or require user action.
- Do not force UI-specific height, padding, anchor, or motion language onto non-UI diagrams.

Use this compact shape when a diagram-heavy approval would otherwise be ambiguous:

```text
Recommended: this diagram will show <core relationship/process/boundary/state/data direction>.

Current / problem:
+-------------+      ?
| A           | ---> |
+-------------+      |
  Missing boundary, owner, branch, state, or data direction

Target:
+-------------+   <relation/flow>   +-------------+
| A: role     |  ---------------->  | B: role     |
+-------------+                     +-------------+
       |                                   |
       +-- <owner / branch / state note> --+

Touchpoints: `<module/doc>` and `<diagram area>`; not changing <explicit exclusion>.
Diagram acceptance: <what the user can identify from the diagram>.
Expression side effect: <what is emphasized, collapsed, hidden, or intentionally omitted>.
```

Diagram-type acceptance cues:

- **Flowchart**: entry point, decision points, success path, failure/rollback path, terminal states.
- **Architecture diagram**: module boundaries, dependency direction, ownership, external systems, trust/security boundary when relevant.
- **State diagram**: states, transitions, triggers, guards, terminal/error states.
- **Data-flow/API diagram**: source, transform, destination, data owner, protocol/API boundary, trust/security boundary when relevant.

## Final Artifact Shape

Before execution, capture this artifact and get explicit user approval.

Present it under the same Output Style rules as the approach comparison: BLUF, user language, effect first. The `Final implementation plan` is the only section that names steps; keep even those at the level of observable behavior plus referenced files/symbols by name, not line-by-line code. Push internal mechanics into an optional expand section.

```text
Recommendation:
- Intent: <one-sentence interpretation>
- Recommended default: <chosen path unless user changes it>
- Why: <short rationale>
- User action: <approve / choose / correct / no action needed>
- Confidence: <high|medium|low when useful>
- Escalation reason: <why the user must decide, or "none">

Option matrix:
- <2-3 choices with best-for, pros, cons, and failure mode; omit if no real choice remains>

Final expected effect:
- <user-visible outcome in user language>

Touchpoints / scope:
- <one short line naming concrete files/modules/components when known, plus explicit exclusions; keep the formal `Scope` field for runtime readiness>

Anti-outcomes:
- <what would feel wrong even if technically complete>

Chosen approach:
- <selected approach with brief rationale>

Final implementation plan:
1. <step, stated as effect or named file/symbol, not code>
2. <step>
3. <verification step>

Visible acceptance:
- <what the user can see, feel, or operate to confirm the result>

Diagram acceptance:
- <for diagram-heavy work, what the user can identify from the diagram: flow, boundary, owner, state, transition, source, transform, or destination>

Quick checks:
- <observable expectation 1>
- <observable expectation 2>
- <observable expectation 3>

Visible side effect:
- <expected screen/operational side effect, or "none"; do not introduce alternate unchosen solutions here>

Expression side effect:
- <for diagram-heavy work, what the diagram emphasizes, collapses, hides, or intentionally omits>

Diagram:
- <ASCII or Mermaid diagram when UI, layout, workflow, architecture, state, data flow, or process shape would otherwise be ambiguous; for UI layout prefer current-vs-target ASCII with size/padding/anchor/parent impact labels; for explanatory diagrams prefer a diagram-intent sketch with relationship/process/boundary/state/data labels>

Open questions:
- <any remaining non-blocking questions, or "none">
```

## Minimum Viable Knowledge

A proposal the user cannot read is a failed proposal, even if it is technically complete. When the proposal contains any term, concept, or mechanism the user may not know, give the minimum knowledge needed to evaluate it.

- **Every unfamiliar term gets one plain-language sentence** inline or in a short glossary block. Example: "continuous tuning = the system finds its own control parameters so you don't hand-tune them."
- **Drop pure-symbol jargon entirely.** Symbols like `Ku`, `Tu`, `Kp/Ki/Kd`, raw type names, or internal field names carry no decision value for the user. Omit them from the main proposal.
- **Explain a tradeoff's stakes, not just its name.** If an option is "less safe", say what unsafe looks like in practice.
- Keep MVK proportional: one sentence per term, not a tutorial. If the user already demonstrated the knowledge, skip it.

Use this compact shape when any option depends on unfamiliar terms:

```text
Minimum viable knowledge:
- <term>: <one plain-language sentence explaining only what the user needs to decide>
```

## Diagram Trigger

Use a simple diagram when it lets the user validate shape faster than prose. Prefer Mermaid or ASCII, and keep it small.

- UI/layout: show current vs target regions, height/width when relevant, padding, anchors, reveal direction, overflow boundary, and parent-container impact.
- Workflow/process: show entry points, decision points, success path, failure/rollback path, and terminal states.
- Architecture: show module boundaries, dependency direction, ownership, external systems, and trust/security boundaries when relevant.
- State/mode behavior: show states, transitions, triggers, guards, and terminal/error states.
- Data/API flow: show source, transform, destination, owner, protocol/API boundary, and trust/security boundary when relevant.

Skip the diagram when the request is local, textual, or the diagram would repeat obvious prose.

## Question Filtering Gate

Not every uncertainty you hold is a user decision. Before presenting open questions or a `question` call, run each candidate through the Question Threshold below. A candidate reaches the user ONLY if guessing wrong would change product behavior, architecture/module boundaries, compatibility, or security/cost/long-term maintenance.

Everything else is engineering uncertainty that YOU resolve:

- If reading code, docs, or running a command would answer it, resolve it yourself before proposing. Do not outsource discoverable facts to the user.
- If it is a pure implementation preference with no user-visible effect, decide it, and at most note the decision in one line.
- Do not pad the open-questions list with engineering choices to look thorough. Each extra question raises reading cost and dilutes the real decision.

When in doubt, ask: "Would a wrong guess here produce a user-visible mismatch or an irreversible/expensive consequence?" If no, do not ask.

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

For visual quality corrections like "still overflows", "裁剪效果不好", "feels clipped", "janky", "foreground arrives early", or "not synchronized", stop patching the existing technique. Re-open the approach comparison and offer containment, synchronized entrance, and layout/reflow options when relevant.

## Question Threshold

Ask implementation questions only when they affect:

- Product behavior or user-visible outcomes
- Architecture decisions or module boundaries
- Compatibility with existing systems or data
- Security, cost, or long-term maintenance

Do not ask about implementation details that are purely engineering preferences when they do not affect the above categories.

This threshold is enforced by the Question Filtering Gate (near the Final Artifact Shape): run every candidate open question through these four categories before it reaches the user, and resolve discoverable engineering facts yourself instead of asking.

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

## Question Strategy Layer

Translate risk-shaped contracts into conversation, not a form. Default to: understand first, ask one decision per turn, offer a recommended default, show contrastive options, then assemble a final card before execution.

- **visible_effect**: start with the first observable frame, first visible result, or what the user should notice on screen before asking about polish details.
- **ordered_flow**: start with entry state, single-step order, and transition handoff; only then ask about follow-up states or recovery ordering.
- **safety_boundary**: start with protected resources, confirmation gates, rollback/undo, and irreversible actions; do not bury the boundary inside a wider feature question.
- **observability**: use success signals, logs, or checkpoints as supporting evidence, not as the primary question when the visible effect or boundary is still unclear.
- **final card**: summarize intent, recommended default, contrastive options, anti-outcomes, and approval in one compact decision surface before execution.

If a task only needs a light check, keep the round small and stop at the minimum decision that changes behavior. Do not turn the user into a field-by-field reviewer.

## Routing Rule

When the clarified work will consume long context, promote it to a formal work item and route execution through `just-demand-*` subagents. Do not keep long-context work in the main session.

## No Main-Session Injection

This skill does not inject workflow mechanics or bootstrap text into the main session. It provides clarification guidance that the agent applies when triggering conditions are met.
