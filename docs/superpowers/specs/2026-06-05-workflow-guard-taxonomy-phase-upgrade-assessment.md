# Workflow Guard Taxonomy and Phase Upgrade Assessment

## Status

Draft design spec for the current just-demand runtime. This document describes the system as it exists today and defines the smallest credible next architectural step.

## Purpose

The current runtime already behaves like a layered control system, but the model is implicit:

- `session-start` injects lightweight workflow reminders into the system prompt.
- `just-demand-state.js` rewrites or appends per-turn reminders and light blockers.
- `just-demand-lib.js` owns reminder state, task lookup, task-context assembly, and guard predicates.
- `tests/just_demand/test_opencode_plugins.mjs` codifies the expected boundaries and false-positive protections.

This spec makes that model explicit so later implementation work can cite a stable design instead of re-deriving it from heuristics.

## Evidence Base

Primary sources:

- `.opencode/plugins/just-demand-state.js`
- `.opencode/plugins/just-demand-lib.js`
- `.opencode/plugins/just-demand-session-start.js`
- `.opencode/skills/just-demand-execution/SKILL.md`
- `tests/just_demand/test_opencode_plugins.mjs`
- Existing workflow design material under `docs/superpowers/specs/`

The conclusions below reflect the current implementation, not an aspirational control model.

## Current Runtime Taxonomy

The runtime has four distinct control layers.

### 1) Reminder Layer

Reminder behavior is lightweight, advisory, and intentionally non-authoritative.

Current reminder surfaces:

- **Session bootstrap reminder**: `just-demand-session-start.js` appends a compact `<JUST_DEMAND_REMINDER>` block to the system prompt.
  - It reminds the model to load `using-just-demand` first.
  - It reminds the model to use `socratic-clarification` second for requests, bugs, corrections, or mismatches.
  - It reminds the model to prefer subagents for long-context work.
  - It reminds the model to ask retry-vs-skip when a needed subagent is unavailable.
  - It explicitly avoids injecting a workflow state dump.

- **Clarification reminder**: `just-demand-state.js` appends a reminder for concrete request language such as request / feature / bug / regression / mismatch / correction / implement / fix / refactor / change.

- **Premise-check reminder**: turns containing premise / assumption / root-cause framing are nudged toward re-checking the problem model.

- **Reset reminder**: after three same-topic turns, the runtime asks for a reset of the problem model before more narrow tuning.

- **Checkpoint-followup reminder**: when verification has passed but the checkpoint commit is missing, the runtime reminds the user to confirm the checkpoint path before treating the task as fully closed.

- **Subagent retry/skip reminder**: when a required subagent was unavailable on the previous turn, the runtime reminds the user to retry now or skip one turn.

Reminder semantics:

- Do not rewrite the conversation into workflow state.
- Do not claim task completion.
- Do not force a phase transition.
- Avoid repetition via last-reminder dedupe.

### 2) False-Positive Guard Layer

This layer protects the reminder/blocker system from over-triggering.

Current false-positive guards:

- **Cross-sentence near-miss guard**: if the message says something like “I still want to confirm first” or “not yet,” the runtime suppresses reminder/blocker escalation even if the first sentence looks like execution or closeout.

- **Negated execution guard**: `just-demand-lib.js` refuses to classify execution claims when the text explicitly says the speaker is holding off, still confirming, or not acting yet.

- **Negated completion guard**: completion-claim detection is suppressed when the text explicitly says the work is not done, not closing, or not ready to ship.

- **Assigned-subagent guard**: execution-needed detection is disabled once the task already has workflow subagents assigned.

- **Header dedupe guard**: the blocker/reminder blocks are only injected once per turn because they are marked with explicit headers.

- **Same-topic fingerprint guard**: the “reset” reminder is only triggered after overlapping topic fingerprints accumulate enough evidence; it is not based on raw repetition alone.

- **Subagent-unavailable priority guard**: when retry/skip is pending, it takes priority over other reminder candidates.

These guards are important because the runtime is text-sensitive, not state-machine-pure. Without them, ordinary analysis or partial self-correction would be incorrectly blocked.

### 3) Light Blocker Layer

The runtime has two genuine blockers today:

- **Execution-needed blocker**: if the active task looks like a long-context implementation / debugging / editing task and no workflow subagent is assigned, the runtime rewrites the response into an `execution blocked` notice and quotes the original response.

- **Verification-closeout blocker**: if the response reads like a completion claim while the task has not passed verification closeout, the runtime rewrites the response into a `closeout blocked` notice and quotes the original response.

These are “light blockers” because they still operate at the message layer rather than at a centralized lifecycle engine. They block the current turn, but they do not own the canonical task lifecycle themselves.

### 4) Supporting State Mechanisms

The runtime depends on small supporting state mechanisms rather than a full orchestration state machine.

Current support state:

- **Workspace state pointer**: `state.json.current_task_id` identifies the active task.
- **Task state**: `task.json` carries status, current step, assigned subagents, verification status, and checkpoint commit metadata.
- **In-memory reminder state**: `just-demand-lib.js` keeps a process-local `REMINDER_STATE` map for reminder dedupe and unavailable-subagent tracking.
- **Topic memory**: `just-demand-state.js` keeps a process-local fingerprint map to detect same-topic turns.
- **Task package files**: `context.md`, `implement.md`, `verify.md`, `decisions.md`, and `open_questions.md` feed subagent context assembly.
- **Required context-file checks**: `getMissingRequiredContextFiles()` enforces that the right task package exists before a subagent is expected to run.

Important limitation:

- None of the in-memory maps are durable workflow state. They are only transient control aids for a single OpenCode process.

## Explicit Workflow Phase Model

The current runtime maps cleanly to five phases.

### Phase 1: Clarify

Intent: reduce ambiguity before committing to a formal work path.

Signals:

- request / bug / correction / mismatch language
- premise / assumption / root-cause language
- repeated same-topic narrowing

Current controls:

- Clarification reminder
- Premise-check reminder
- Reset reminder

Recommendation:

- Keep this phase advisory.
- Do not turn it into a hard blocker in the plugin layer.
- Clarify remains a human-led reasoning phase, not a machine gate.

### Phase 2: Route

Intent: decide whether the work should stay in the main session or move into a task/subagent path.

Signals:

- active task exists
- subagent availability
- task already has assigned workflow subagents
- task package completeness

Current controls:

- Session bootstrap reminder to use the routing skills
- Subagent retry/skip reminder
- Assigned-subagent guard suppressing false execution escalation
- Required-context checks in `just-demand-lib.js`

Recommendation:

- This phase is the best candidate for a minimal phase controller, but only as a thin router.
- It should decide “main session vs subagent path,” not own all task lifecycle semantics.

### Phase 3: Execute

Intent: move concrete work into the scoped execution path.

Signals:

- task status indicates execution-oriented work
- current text sounds like implementation / debugging / editing
- no workflow subagent is already assigned

Current controls:

- Execution-needed blocker
- Long-context execution guidance in `just-demand-execution`

Recommendation:

- This phase is a strong candidate for a formal phase gate.
- The gate should remain narrow: “dispatch through the supported subagent path,” not “orchestrate every implementation detail.”

### Phase 4: Verify

Intent: ensure that completion claims are backed by verification evidence.

Signals:

- the message sounds like “done / finished / ready to ship / close this out”
- task verification status is not passed

Current controls:

- Verification-closeout blocker
- `complete-verification` script contract in the execution skill

Recommendation:

- This phase is also a strong candidate for a formal phase gate.
- Verification should remain script-owned and evidence-driven, not prompt-owned.

### Phase 5: Close

Intent: finish the task with checkpoint commit / archival hygiene after verification passes.

Signals:

- verification has passed
- checkpoint commit is present or missing

Current controls:

- Checkpoint-followup reminder
- `complete-verification` / `checkpoint-commit` / archive scripts

Recommendation:

- Close should stay mostly outside the plugin runtime.
- The plugin can remind, but the authoritative close action should remain script-owned.

## Rule Map: Current Behavior and Recommended Classification

| Rule / behavior | Current layer | Phase | Keep advisory? | Candidate for formal phase gate? |
| --- | --- | --- | --- | --- |
| Session bootstrap reminder | Reminder | Clarify / Route | Yes | No |
| Concrete request / bug / mismatch reminder | Reminder | Clarify | Yes | No |
| Premise-check reminder | Reminder | Clarify | Yes | No |
| Reset after 3 same-topic turns | Reminder | Clarify | Yes | No |
| Subagent retry/skip reminder | Reminder | Route | Yes | No |
| Execution-needed blocker | Light blocker | Execute | No, this is already a blocker | Yes |
| Verification-closeout blocker | Light blocker | Verify | No, this is already a blocker | Yes |
| Checkpoint-followup reminder | Reminder | Close | Yes | Maybe, but only in script-owned closeout logic |
| Cross-sentence near-miss suppression | False-positive guard | All phases | N/A | Yes, as a guardrail inside any future controller |
| Negated completion / execution filters | False-positive guard | Verify / Execute | N/A | Yes |
| Assigned-subagent suppression | False-positive guard | Execute | N/A | Yes |
| Task package required-file checks | Supporting state | Route / Execute | N/A | Yes |

Interpretation:

- The only behaviors that already justify hard gating are the execution-needed and verification-closeout blockers.
- The rest are advisory or guardrail behaviors that prevent false positives and keep the session conversational.

## Why This Is Not Yet A Full Orchestrator

The repository should **not** jump directly to a full orchestrator.

Reasons:

1. **The canonical lifecycle already lives in scripts**
   - State mutation is script-owned.
   - The plugin layer should not duplicate lifecycle authority.

2. **The runtime is intentionally text-sensitive**
   - The current system still relies on phrasing, near-miss suppression, and user-facing reminders.
   - A full orchestrator would have to either re-implement that nuance or drop it.

3. **The current system is already working as an implicit phase machine**
   - The main gap is naming and boundary clarity, not missing orchestration machinery.

4. **A full orchestrator would add state duplication too early**
   - It would create a second lifecycle brain before the first one is fully formalized.
   - That would increase maintenance cost without solving a demonstrated scaling problem.

5. **The current false-positive policy is still valuable**
   - The near-miss and negation guards show the runtime is better treated as a layered control system than as a strict deterministic workflow engine.

## Recommendation: Minimal Phase Controller, Not Full Orchestrator

The next architectural step should be a **minimal phase controller design**, not a full orchestrator.

That controller should:

- name the phases explicitly,
- define entry and exit conditions,
- preserve the current advisory reminders,
- keep false-positive guards intact,
- and let scripts remain the source of truth for task state.

It should **not**:

- replace the main-agent reasoning loop,
- rewrite task lifecycle ownership out of scripts,
- or move all conversational heuristics into a rigid engine.

## What Should Stay Advisory Versus Formal

### Stay Advisory

- Clarify reminder
- Premise-check reminder
- Reset reminder
- Subagent retry/skip reminder
- Checkpoint-followup reminder
- session-start bootstrap reminder text

These are useful nudges, but they should remain non-authoritative because they preserve conversational flexibility.

### Become Formal Phase Gates

- Execution-needed blocker
- Verification-closeout blocker

These are already the strongest phase-aligned controls in the runtime and are the best candidates to become formal gates in a minimal phase controller.

### Become Controller Guards, Not User-Facing Rules

- Cross-sentence near-miss suppression
- Negation-aware completion/execution filters
- Assigned-subagent suppression
- Required context-file checks

These should be implementation guards inside the controller, not user-visible phases.

## Recommended Next-Step Path

1. **Keep the current guard/blocker architecture in place.**
   - Do not replace it with a full orchestrator yet.

2. **Introduce a minimal phase vocabulary in design docs and tests.**
   - Clarify / Route / Execute / Verify / Close is sufficient.

3. **Treat Execute and Verify as the first formal gates.**
   - Preserve the existing text heuristics as guardrails around them.

4. **Leave Clarify and Close mostly advisory for now.**
   - Clarify is a reasoning aid.
   - Close remains script-owned and evidence-driven.

5. **Only consider a fuller orchestrator if future work shows structural pressure.**
   - Examples of pressure: repeated phase ambiguity, many new phase-specific exceptions, or duplicated gate logic across plugins and scripts.

## Implementation Reference Notes

Future implementation tasks should cite this spec when they need to:

- justify a minimal phase controller,
- distinguish advisory reminders from hard gates,
- preserve the current false-positive suppression behavior,
- or explain why the runtime should remain script-owned rather than fully orchestrated.

When implementing, keep the following invariant:

- **Plugins may shape conversation. Scripts own lifecycle.**
