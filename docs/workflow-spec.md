# Canonical Workflow Specification

This document is the canonical, repo-owned description of Just Demand workflow behavior and product philosophy. When other docs, skills, or prompts differ from this spec, this file is the reference point for lifecycle, ownership, recovery semantics, and the user-expectation contract model.

## Scope And Authority

- **Authoritative for**: lifecycle, role model, task-state transitions, clarification/intake/execution/verification/archive rules, context-package requirements, recovery, command ordering, checkpoint semantics, source-of-truth boundaries, and product philosophy.
- **Not authoritative for**: runtime code behavior details, task-specific implementation choices, or one-off decisions recorded in task archives.
- **Behavioral source of truth**: the `just-demand` CLI, `.just-demand/scripts/workflow_core.py`, and `.opencode/plugins/*.js` define executable behavior; this spec explains and aligns that behavior.
- **Design templates and detailed output examples**: see `docs/design.md` for annotated task-completion, plan-confirmation, and deviation-correction output templates.

## Product Philosophy

Just Demand is designed for the AI-assisted coding era. Users express needs and phenomena in natural language; the workflow clarifies real intent, manages task context, dispatches subagents, verifies outcomes, and reports visible effects without forcing users to inspect implementation details.

### Core Principles

1. **Default ambiguity.** User requests are inherently incomplete, casually expressed, and may drift from the user's mental model. The first statement of a need is never treated as the final requirement. Progressive clarification is mandatory before promotion or execution.

2. **User as boss, not code reviewer.** The user owns goals, constraints, tradeoff preferences, and final approval. The user does not own implementation mechanics, subagent orchestration, or workflow state management. The user's job is to recognize effect, not read code.

3. **Effect-first communication.** The agent leads with what the user can see, feel, or operate. Implementation details, files, dependencies, and internal mechanics are secondary and surface only when they affect a user decision.

4. **Minimum viable knowledge.** When the task touches an unfamiliar domain, the agent provides exactly enough plain-language context for the user to make a decision — not a tutorial, not a jargon dump.

5. **Lower user burden.** Automation that the agent can safely own (verification, checkpoint commits, context assembly) should default to agent ownership. The user approves direction and checks effect, not every intermediate step.

6. **Task context as user-expectation contract.** The task context files capture what the user expects to see, feel, or operate — not just an implementation brief. They form a durable reference that survives session resets and context compression.

7. **Long context belongs to subagents.** Broad code reading, multi-file implementation, extended debugging, and research that would consume significant main-session context must route through `just-demand-*` subagents by default. The main session coordinates and summarizes; it does not absorb full execution context inline.

8. **Mismatch feedback is optionized before re-implementation.** When the user reports a deviation (vague or precise), the agent does not guess the root cause and patch blindly. Instead it leads with options: locate the deviation dimension, then pin the target state via contrastive choices. The user click-selects rather than writing prose.

9. **Repeated mismatch triggers reflection.** If the same issue fails twice consecutively, the workflow stops blind patching, enters reflection, and routes to the `advisor` subagent for fresh-context analysis before any more implementation.

## System Model

Just Demand is a workflow runtime, not a one-shot prompt bundle.

The durable workflow truth lives in explicit state and scripts. Prompt-layer guidance stays light and role-specific so the main agent can route work without carrying the whole lifecycle in chat.

```text
human intent
  -> clarify
  -> intake
  -> promote
  -> context
  -> dispatch
  -> verify
  -> complete-verification
  -> archive
```

## Role Model

### User

The user is the **boss, product manager, and architecture approver** — not the code reviewer. The user:

- Defines goals, expected effects, constraints, and tradeoff preferences.
- Describes phenomena, mismatches, and desired outcomes in natural language; precise diagnosis is the agent's responsibility.
- Approves design direction and accepts or rejects observable results.
- Does **not** write implementation plans, read diffs line by line, or compose deviation descriptions from scratch.

### Main Agent

The main agent is the **workflow owner, delivery lead, and dispatcher**. The main agent:

- Recognizes that every user request starts as incomplete intent and must be progressively clarified.
- Leads clarification with effect-shaping questions ("what should you see?", "what happens now instead?"), not permission questions ("can I proceed?").
- Reveals the expected visible effect before task promotion or execution — the user approves what they will see, not how it will be built.
- Owns task shaping, routing, recovery, verification closeout, summaries, and the user-expectation contract.
- Reports in effect-first style: visible result, scope, acceptance cues, and next user choice — not implementation details.
- Delegates broad implementation, research, and verification to `just-demand-*` subagents by default.
- Routes vague mismatch feedback into optionized deviation resolution before re-implementing.
- Escalates consecutive failures to reflection/advisor instead of blind patching.

### Subagents

Subagents execute focused role contracts inside a task boundary. They do not create, promote, close, or re-route tasks.

- **Researcher**: evidence gathering, problem mapping, option comparison.
- **Coder**: scoped implementation inside the task boundary.
- **Tester**: acceptance verification and low-risk local fixes.
- **Advisor**: fresh-context framing and cross-boundary tradeoff analysis.

## Lifecycle And State Transitions

```text
no task
  -> intake created
  -> intake promoted
  -> active formal task
  -> context package present
  -> subagent dispatch / implementation
  -> verification
  -> complete-verification
  -> archive
```

Key meanings:

- `create-intake` creates intake only; it does not create a formal task.
- `promote` turns a prepared intake into an active formal task.
- `list-active` reflects active formal tasks only.
- `complete-verification` is the normal verified-closeout path and archives on pass.
- `checkpoint-commit` is the mid-task checkpoint path for a clean verified slice.

## Clarification, Intake, And Promotion

Clarification is a hard gate before promotion or execution when the intended effect is still ambiguous. This gate exists because **user requests are inherently incomplete intent** — the first expression of a need is never treated as the final requirement.

### Clarification Rules

- Use `socratic-clarification` to establish the final expected effect, boundaries, and tradeoffs.
- Lead with **effect-shaping questions** ("what should you see?", "what happens now instead?") over permission questions ("can I proceed?").
- Reveal the expected visible effect before promoting or executing — the user approves what they will see, not how it will be built.
- Move clarified work into the intake file before promotion.
- Treat blocking questions as promotion blockers.
- Do not guess missing scope, expected behavior, actual behavior, or approval fields.

For design and implementation work, promotion requires a clear decision surface: expected effect, chosen approach, implementation plan, and approval. For mismatch work, promotion requires the expected/actual/reproduction/scope shape that safely identifies the deviation.

### Mismatch Optioning

When correction feedback is vague or points to multiple possible fixes:

1. **Do not guess and patch blindly.** Infer the likely deviation from the implementation and expected effect.
2. **Lead with the two-stage option flow:**
   - Stage 1: locate the deviation dimension (color, spacing, motion, layout, logic, scope, data).
   - Stage 2: pin the target state via contrastive options ("currently X; do you want Y or Z?").
3. The user should be able to click-select through both stages rather than compose prose.
4. Reserve free-text only for reproduction steps, environmental conditions, and open-ended phenomena that cannot be reduced to options.

### Repeated Mismatch Reflection

If the same issue produces meaningful correction feedback twice consecutively:

1. **Stop modifying code directly.**
2. Exit the current execution loop.
3. Route to the `advisor` subagent for fresh-context analysis.
4. The advisor examines the full chain: user intent, clarification artifacts, coder context, tester output, and actual observed effect — without inheriting the main session's accumulated context.
5. Only resume implementation after the advisor recommends a path forward that the user approves.

## Execution And Context Packages

Execution belongs to the active formal task, not the intake thread.

Before implementation or verification:

1. Confirm the intended task is active.
2. Run `just-demand . list-active` and inspect unfinished tasks for conflict risk.
3. Select or resume the intended task if another unfinished task is current.
4. Ensure the task context package exists for the intended subagent.
5. Dispatch the narrowest suitable `just-demand-*` subagent when long-context work is involved.

Required task context files:

- `just-demand-coder`: `context.md`, `implement.md`
- `just-demand-tester`: `context.md`, `verify.md`
- `just-demand-researcher`: `context.md`
- `just-demand-advisor`: `context.md`

If required context files are missing, stop and refresh the package before execution.

## Verification, Checkpoints, And Archive

Verification must precede completion claims.

- Use `just-demand-tester` for task-brief validation when the result needs review.
- Treat the tester report as the active verification record.
- Use `complete-verification <task-id> passed ...` for the normal verified-closeout path.
- Use `checkpoint-commit <task-id>` for a clean mid-task checkpoint without closeout.
- Do not report completion until verification closeout has run.

Checkpoint semantics:

- Clean verification should normally produce a checkpoint commit through the script-owned closeout path.
- The script owns the safety gate, commit scoping, and archive-on-pass behavior.
- The agent should not hand-edit workflow state files.

## Recovery Model

Recovery is task-local and stateful.

- If `list-active` shows unfinished tasks but no current task is selected, select or resume the intended task first.
- If `promote` fails, update the same intake file and rerun the command rather than creating a new intake.
- If the current task lacks required context files, refresh the task package before execution.
- If workflow gates fail in no-plugin fallback, route back to clarification or intake instead of guessing.

## Command Ordering

Recommended order for real work:

```text
list-active
  -> select/resume if needed
  -> clarify
  -> create-intake / update intake
  -> promote
  -> ensure task context files
  -> dispatch subagent / implement
  -> verify
  -> complete-verification or checkpoint-commit
  -> archive
```

Additional rules:

- `create-intake` does not make a task active.
- `promote` must not happen before required intake fields are filled.
- `complete-verification` is the normal closeout path; `checkpoint-commit` is the partial checkpoint path.
- State writes go through CLI/script ownership, not manual edits.

## Source-Of-Truth Boundaries

- **CLI and scripts**: own durable workflow state and lifecycle transitions.
- **Plugins**: inject lightweight runtime guards, reminders, and task context.
- **Skills**: route the main agent and preserve concise operating rules.
- **Docs**: explain the model and reference the canonical spec.
- **Task archives**: preserve task-local history, decisions, and verified lessons.

Operational files such as `.just-demand/state/state.json`, `locks.json`, and `events.jsonl` are not hand-edited.

## Output Contract

Every main-agent output to the user follows an **effect-first** discipline. The user is boss, PM, and architect — not a code reviewer. Implementation detail is deferred by default.

### Default Report Shape

```text
<Effect or conclusion in one sentence.>
Status: <what changed or what is now known>
Risk: <remaining non-visible risk or none>
User action: <none / review / choose / approve>
```

### Principles

1. **Lead with the user-visible effect.** The first line states the result, observed phenomenon, or design intent before any context.
2. **Scope and acceptance cues next.** What is in scope, what is out, how the user can check it.
3. **Implementation detail last.** Files, code, tests, and internal mechanics surface only when they affect a user decision or the user explicitly asks.
4. **Minimum viable knowledge.** One plain-language sentence per unfamiliar term if needed for a decision.
5. **Options not prose for choices.** Present defaults and contrastive options; the user picks rather than writes.
6. **No internal workflow labels on the first screen.** `Thought`, `Skill`, `Decision card`, `Validation card`, and task-form field names belong below the fold or in optional expansions, not in the opening user-facing block.
7. **Consecutive failure routes to reflection.** After two failed attempts on the same issue, the agent reports the failure and routes to the advisor rather than continuing to patch.

### Verification Closeout Report

The closeout specialization follows the same shape:

```text
<Outcome in one sentence — passed, failed, or blocked.>

Result:
- Status: <what passed or what is now known>
- Risk: <remaining risk or none>
- Checks: <verification summary; omitted from first screen if all passed>
- User action: <none / review / choose>
Optional expansion:
- <files changed, logs, deeper rationale>
```

See `docs/design.md` for annotated output templates covering task completion, plan confirmation, and deviation correction.

## What May Stay Duplicated

Some short routing reminders remain duplicated on purpose in README, AGENTS, and skills so the right agent can still operate with minimal context. Those copies should stay brief and point back to this spec rather than reintroducing long lifecycle prose.
