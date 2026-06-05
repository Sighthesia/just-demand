# Minimal Phase Controller Design

## Status

Formal design spec derived from `2026-06-05-workflow-guard-taxonomy-phase-upgrade-assessment.md`.

This document defines the smallest credible phase controller that can sit on top of the current guard/blocker runtime without taking lifecycle ownership away from scripts.

## Purpose

The current runtime already behaves like an implicit phase machine:

- `just-demand-session-start.js` injects lightweight workflow reminders into the system prompt.
- `just-demand-state.js` appends per-turn reminders and two narrow blockers.
- `just-demand-lib.js` owns the task predicates and guard helpers.
- Scripts still own task lifecycle state and all durable workflow mutation.

The missing piece is a concrete controller contract that a future implementation task can follow without drifting into a full orchestrator.

## Design Goal

Introduce a **minimal phase controller** that:

- names the workflow phases explicitly,
- turns the existing execution and verification blockers into formal gates,
- preserves advisory reminder behavior for Clarify and Close,
- keeps false-positive guards intact,
- and leaves scripts as the authoritative owner of lifecycle state.

## Non-Goals

This spec does **not**:

- define a full orchestrator,
- move task lifecycle mutation into plugins,
- replace the main agent's reasoning loop,
- change the meaning of task scripts such as `create_intake`, `promote_to_task`, `start_execution`, `complete_verification`, `checkpoint-commit`, or archive flows,
- or remove the current text-sensitive guard behavior.

The controller is intentionally narrow. It classifies, guards, and gates; it does not run the whole workflow.

## Core Design Principle

**Plugins may shape conversation. Scripts own lifecycle.**

The controller may decide whether the current turn should be nudged, blocked, or allowed, but it must never become the source of truth for task status, verification status, checkpoint state, or assignment state.

## Phase Vocabulary

The minimal controller uses five phases.

### 1) Clarify

Purpose: reduce ambiguity before the work is routed into a formal execution path.

Current signals:

- request / bug / regression / mismatch / correction language,
- premise / assumption / root-cause language,
- repeated same-topic narrowing.

Controller posture:

- advisory only,
- never a hard gate in this pass,
- may emit reminders, but may not block the turn.

### 2) Route

Purpose: decide whether the work stays in the main session or should move into the supported task/subagent path.

Current signals:

- an active task exists,
- a workflow subagent is already assigned or not,
- the required task package files exist or are missing,
- the subagent-unavailable retry/skip state is pending.

Controller posture:

- advisory / pre-gate classification,
- not itself a lifecycle transition,
- used to determine whether the next turn belongs in Execute or should stay conversational.

### 3) Execute

Purpose: move concrete implementation/debugging/editing work into the routed task path.

Current signals:

- the active task is execution-oriented,
- the current turn sounds like implementation, debugging, editing, or direct main-session work,
- no supported workflow subagent is already assigned.

Controller posture:

- formal gate,
- the first hard boundary in the minimal controller,
- preserves the existing execution-needed blocker semantics.

### 4) Verify

Purpose: ensure that completion claims are backed by verification evidence.

Current signals:

- the current turn sounds like done / finished / ready to ship / close this out,
- task verification has not yet passed.

Controller posture:

- formal gate,
- preserves the existing verification-closeout blocker semantics,
- remains evidence-driven and script-aligned.

### 5) Close

Purpose: finish task hygiene after verification passes, including checkpoint follow-up.

Current signals:

- verification has passed,
- checkpoint commit is present or missing.

Controller posture:

- mostly advisory in this pass,
- checkpoint follow-up remains a reminder, not a gate,
- script-owned closeout remains authoritative.

## Which Phases Are Formal Gates

Only two phases deserve hard gating in the minimal controller:

1. **Execute**
   - gate type: `execution_needed`
   - blocks obvious execution work that should go through a supported `just-demand-*` subagent path.

2. **Verify**
   - gate type: `verification_closeout`
   - blocks obvious completion claims until `complete-verification` has been performed.

Clarify and Close remain advisory. Route is a controller decision point, but not yet a hard gate.

## Controller Contract

The minimal controller should be understood as a pure decision layer over the current turn, not as a state owner.

### Inputs

The controller reads, but does not mutate, the following classes of input:

- **Workspace lifecycle pointer**
  - `state.json.current_task_id`
  - current unfinished task selection

- **Task snapshot**
  - `task.json.status`
  - `task.json.current_step`
  - `task.json.assigned_subagents`
  - `task.json.verification_status`
  - `task.json.checkpoint_commit`

- **Task package presence**
  - `context.md`
  - `implement.md`
  - `verify.md`
  - `decisions.md`
  - `open_questions.md`

- **Current assistant turn text**
  - the message text being considered for reminder or blocker injection.

- **Transient controller memory**
  - last reminder type,
  - subagent-unavailable pending state,
  - same-topic fingerprint / turn count.

### Outputs

The controller should emit a small, explicit decision shape such as:

- **phase**: one of `clarify`, `route`, `execute`, `verify`, `close`
- **action**: `allow`, `remind`, or `block`
- **reason_code**: a stable label such as `clarify_hint`, `execution_needed`, `verification_closeout`, `checkpoint_followup`, `subagent_retry_or_skip`
- **message rewrite**: optional reminder or blocker text
- **quoted original response**: only for blockers

The controller does **not** emit lifecycle mutations, task reassignment, or verification results.

### Invariants

The controller must preserve all of the following:

- scripts remain the authoritative owner of task lifecycle state,
- plugins only shape the conversation surface,
- reminder injection is lightweight and deduplicated,
- hard blockers stay narrow and text-sensitive,
- false-positive suppression remains active,
- completion claims are not treated as authoritative without script-backed verification,
- and checkpoint hygiene remains script-owned.

## Responsibilities by Layer

### Scripts

Scripts own durable workflow mutation. They are responsible for:

- creating and promoting tasks,
- writing `state.json` and task JSON state,
- creating and reconciling task package files,
- assigning workflow subagents,
- recording verification outcomes,
- committing checkpoints,
- archiving completed tasks,
- and maintaining durable workflow state.

### Plugins

Plugins adapt the file-backed workflow into OpenCode runtime behavior. In this pass they may:

- inject the session-start reminder,
- add per-turn reminders,
- block a turn only through the Execute and Verify gates,
- and surface checkpoint follow-up reminders.

Plugins may not:

- decide durable task lifecycle transitions,
- write task state,
- synthesize verification success,
- or claim a task is closed.

### Subagents

Subagents execute scoped work only. They should receive the task package context, but they should not own routing, lifecycle mutation, or gate decisions.

### Task Files

Task files remain the canonical handoff surface between scripts, plugins, and subagents.

- `context.md` frames the work.
- `implement.md` guides execution.
- `verify.md` guides verification.
- `decisions.md` and `open_questions.md` keep durable task-local context.

The controller may require these files to exist before it treats a task as ready for a subagent path, but it does not author them.

## Guard Model Inside the Controller

The current runtime depends on false-positive suppression because it is text-sensitive rather than purely state-machine driven. The controller must keep those guards as internal implementation details, not user-facing phases.

### Guards That Must Remain

1. **Cross-sentence near-miss suppression**
   - Example class: the turn mentions execution or closeout language, but also says the speaker wants to confirm first or is not ready yet.
   - Purpose: avoid blocking ordinary reasoning or partial self-correction.

2. **Negation-aware execution filtering**
   - Example class: “I will implement this” versus “I will not implement this yet.”
   - Purpose: avoid false execution escalation.

3. **Negation-aware completion filtering**
   - Example class: “this is done” versus “not done yet.”
   - Purpose: avoid false verification closeout.

4. **Assigned-subagent suppression**
   - Purpose: once a workflow subagent is already assigned, execution-needed escalation should not keep firing as if the task were unrouted.

5. **Required context-file checks**
   - Purpose: a task should not be treated as ready for a subagent path if the required task package is incomplete.

6. **Reminder dedupe / same-reminder suppression**
   - Purpose: keep the conversation lightweight and avoid repeating the same reminder every turn.

7. **Subagent-unavailable priority guard**
   - Purpose: if retry-or-skip is pending, that guidance takes precedence over other reminder candidates.

8. **Same-topic accumulation / reset threshold**
   - Purpose: the reset reminder should be triggered only after repeated overlapping topic evidence, not by superficial repetition.

### Guard Priority

When multiple candidates compete, the controller should follow this priority order:

1. subagent retry/skip reminder if unavailable is pending,
2. verification closeout gate,
3. execution-needed gate,
4. checkpoint follow-up reminder,
5. clarification / premise / reset reminders,
6. no-op.

This preserves the current behavior that retry/skip guidance supersedes ordinary routing or closeout text.

## Formal Gate Semantics

### Execute Gate

The Execute gate should fire only when all of the following are true:

- there is an active unfinished task,
- the task is in an execution-relevant state,
- the current turn looks like direct execution work,
- the turn is not negated by a near-miss / “not yet” style phrase,
- no supported workflow subagent is already assigned,
- and required task package files indicate the subagent path is ready or can be made ready.

If the gate fires, the current turn should be rewritten into an `execution blocked` notice that preserves the original response.

### Verify Gate

The Verify gate should fire only when all of the following are true:

- there is an active unfinished task,
- the current turn looks like a completion claim,
- the claim is not negated,
- and verification has not yet passed.

If the gate fires, the current turn should be rewritten into a `closeout blocked` notice that preserves the original response.

### Close Handling

Once verification has passed, the controller should not try to own closeout lifecycle.

- If the checkpoint commit is missing, it may emit a reminder.
- It must not block the turn as a formal gate.
- Script-owned closeout remains the source of truth.

## Mapping From the Current Runtime

The controller is not inventing a new workflow. It is naming and stabilizing the current one.

### Existing Behavior That Remains Advisory

- session-start bootstrap reminder text,
- concrete request / bug / mismatch reminder,
- premise-check reminder,
- reset reminder,
- subagent retry/skip reminder,
- checkpoint-followup reminder.

These are still useful nudges. They should remain conversational, not authoritative.

### Existing Behavior That Becomes Formal Gate Logic

- execution-needed blocker,
- verification-closeout blocker.

These two already behave like hard boundaries. The controller simply makes their phase meaning explicit.

### Existing Behavior That Becomes Internal Guard Logic

- cross-sentence near-miss suppression,
- negation-aware execution/completion filtering,
- assigned-subagent suppression,
- required context-file checks,
- reminder dedupe,
- subagent-unavailable priority,
- same-topic reset threshold.

These should remain implementation guards inside the controller rather than user-visible workflow steps.

## Migration Path

This spec is intentionally designed so implementation can be incremental.

### Step 1: Freeze the vocabulary

Add tests and implementation notes that refer to the five phases explicitly:

- Clarify,
- Route,
- Execute,
- Verify,
- Close.

No behavior change is required yet.

### Step 2: Wrap the current blocker logic in phase terms

Treat the current `execution_needed` and `verification_closeout` logic as controller gates.

- keep the existing text heuristics,
- keep the current blockers’ message shape,
- but route them through the phase vocabulary.

This step changes naming and boundary clarity before changing semantics.

### Step 3: Centralize guard predicates

Keep the predicate logic in one place so the controller can ask questions such as:

- Is this a negated execution claim?
- Is this a negated completion claim?
- Is a workflow subagent already assigned?
- Are the required context files present?

That centralization should preserve the current false-positive behavior exactly unless tests intentionally change it.

### Step 4: Validate phase priority and false positives

Add or strengthen tests around:

- retry/skip priority over other reminders,
- near-miss execution and closeout wording,
- cross-sentence negation cases,
- assigned-subagent suppression,
- checkpoint-followup after verification passes,
- and no duplicate reminder injection.

### Step 5: Keep scripts authoritative

Do not move lifecycle mutation into the controller.

The only acceptable migration is from implicit phase behavior to explicit phase naming and explicit gate boundaries.

### Step 6: Stop at the minimal controller

Do not expand into a full orchestrator unless future evidence shows structural pressure such as:

- duplicated gate logic across multiple plugins,
- repeated phase ambiguity that cannot be solved with clearer guards,
- or a proven need for more controller-owned state than this minimal layer requires.

## Implementation-Ready Reference Shape

A future implementation task can treat the controller as a small decision module with this shape:

```text
inputs  -> current turn text, active task snapshot, task package presence, transient reminder memory
output  -> phase + action + reason code + optional rewrite text
```

That shape is intentionally small enough to fit into the current plugin runtime without re-architecting the workflow.

## Acceptance Criteria for the Minimal Controller

This design is satisfied when the implementation can:

- name the workflow phases explicitly,
- treat Execute and Verify as the only formal gates in this pass,
- preserve Clarify and Close as mostly advisory,
- keep scripts as the lifecycle authority,
- preserve false-positive guards and reminder dedupe,
- and map the current execution / verification blockers into a clear controller contract.

## Relationship to the Assessment Spec

This document is the implementation-facing continuation of the taxonomy assessment.

The assessment identified the layered runtime and recommended a minimal phase controller instead of a full orchestrator. This spec turns that recommendation into a concrete contract that future implementation work can follow directly.
