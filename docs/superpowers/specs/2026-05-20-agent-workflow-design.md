# Agent Workflow Design

## Vision

Build an OpenCode-first local agent workflow that makes AI collaboration feel like a small, well-run product and engineering team.

The user remains responsible for goals, preferences, constraints, and final decisions. The main agent is responsible for understanding the user's intent, shaping options, making tradeoffs explicit, coordinating subagents, and summarizing outcomes. Subagents execute focused work from standardized context packages. Scripts own context packaging, workspace state, injection, and persistence.

The system should share durable facts and decisions, not messy chat history.

## Scope

This first version is a local framework for OpenCode. It is not a general multi-platform product, installable CLI framework, or Trellis replacement.

In scope:

- OpenCode-first workflow structure.
- Workspace intake before formal task creation.
- Requirement clarification and brainstorming protocol.
- Standard task package structure.
- Workspace-level decisions, preferences, deferred options, and event logs.
- Main-agent orchestration and subagent execution roles.
- Hook/plugin responsibilities for session context, workflow state, and subagent context injection.
- Low-reading-cost validation summaries for complex requirements.
- Outcome-language correction after implementation drift.

Out of scope for v1:

- Multi-platform adapters beyond OpenCode.
- Public CLI packaging and update/migration system.
- Full productized installer.
- Automated visual diffing or browser preview infrastructure.
- Complex distributed locking beyond simple local workspace coordination.

## Source References

- Superpowers reference: `/home/Sighthesia/0_Files/Producing/Software/Workflows/superpowers`, especially the design-before-implementation workflow, skill gating, and subagent-driven development model.
- Trellis reference: `/home/Sighthesia/0_Files/Producing/Software/Workflows/Trellis`, especially `.trellis/workflow.md`, task directories, context JSONL, workspace state, and OpenCode hook-based context injection.

This design borrows the high-level flow from Superpowers and the file-backed workflow/runtime approach from Trellis, but narrows the first version to a local OpenCode-first framework and adds a stronger user-centered clarification layer.

## Core Roles

### User

The user provides goals, preferences, constraints, examples, corrections, and final approval. The user should not need to understand task packages, context injection, repo maps, subagent prompts, or workflow state files.

### Main Agent

The main agent is the product/engineering lead for the session. It:

- Restates and clarifies user needs.
- Identifies missing details that may cause outcome mismatch.
- Presents user-facing options with tradeoffs and a recommendation.
- Records durable decisions and deferred options.
- Decides when an intake is ready to become a formal work item.
- Dispatches focused subagents after the work item is ready.
- Integrates and summarizes subagent results.
- Handles user-facing correction when implementation output diverges from expectation.

### Subagents

Subagents execute focused tasks from standardized context. They should not inherit the full main-session chat history and should not take over user interaction.

Initial roles:

- `workflow-research`: investigate and report, without modifying code.
- `workflow-implement`: implement a scoped task, without committing.
- `workflow-check`: verify changes against requirements, specs, and tests; may fix low-risk local issues within scope, but must not introduce a new approach or expand the task.
- `workflow-docs`: update or consolidate documentation, without changing business logic.

### Scripts

Scripts are the source of truth for state mutation. They create tasks, build context packages, update workspace state, append events, maintain locks, and provide context to hooks.

### OpenCode Plugins

Plugins adapt the file-backed workflow into OpenCode runtime behavior. They should inject only the context needed for the current execution path, not make product decisions.

## Directory Structure

```text
.agent-workflow/
  global/
    rules.md
    architecture.md
    glossary.md

  workspace/
    state.json
    preferences.md
    decisions.md
    deferred_options.md
    facts.md
    open_questions.md
    events.jsonl
    locks.json
    intake/
    sessions/

  tasks/
    active/
      <task-id>/
        task.json
        context.md
        repo_map.json
        decisions.md
        open_questions.md
        implement.md
        verify.md
        outputs/
        research/
        events.jsonl
    archive/

  scripts/
    task.py
    context.py
    state.py
    lock.py
    inject.py

.opencode/
  plugins/
    agent-workflow-session-start.js
    agent-workflow-state.js
    agent-workflow-subagent-context.js

  agent/
    workflow-research.md
    workflow-implement.md
    workflow-check.md
    workflow-docs.md
```

## Workspace Intake Flow

Early discussion should not immediately become a formal task. The system first records a lightweight workspace intake note, then promotes it only when the need is clear enough.

Intake states:

```text
capturing -> clarifying -> task_candidate -> discarded / promoted
```

Formal task states:

```text
planning -> ready -> executing -> verifying -> changes_requested -> executing
                                      |              |
                                      v              v
                                     done          blocked
```

The main agent should suggest promotion when:

- The goal can be stated in one sentence.
- The expected result is mostly clear.
- Scope and non-scope are initially defined.
- At least one concrete deliverable exists.
- The conversation has moved beyond open-ended exploration.
- The user confirms that the direction can become a formal work item.

User-facing promotion language should avoid internal mechanics:

```text
This direction is now clear enough to become a formal work item. I suggest turning it into a design draft first, then breaking it into execution steps. Confirm?
```

## Lifecycle Contracts

Lifecycle transitions must be script-driven and atomic from the main agent's point of view. The main agent decides what should happen, then calls the script API. Plugins read state and inject context, but must not infer lifecycle transitions or write workflow state.

### `create_intake`

Purpose: start recording requirement exploration without creating a formal task.

Input:

- Raw user request.
- Current session id.
- Optional title suggested by the main agent.

Writes:

- `.agent-workflow/workspace/intake/<intake-id>.md`
- `workspace/state.json.current_intake_id`
- `workspace/events.jsonl`

Postconditions:

- Intake status is `capturing` or `clarifying`.
- No formal task directory exists yet.
- The intake note contains raw request, current understanding, open questions, and any confirmed preferences.

Failure handling:

- If the intake note cannot be written, do not update `workspace/state.json`.
- If `workspace/state.json` update fails after note creation, append a recovery event on the next successful script run and re-point `current_intake_id` if the note is valid.

### `promote_to_task`

Purpose: convert a sufficiently clarified intake into a formal work item.

Preconditions:

- Intake status is `task_candidate`.
- User has confirmed promotion in user-facing terms.
- No blocking open question remains.
- A concrete deliverable exists.

Writes:

- `.agent-workflow/tasks/active/<task-id>/task.json`
- `.agent-workflow/tasks/active/<task-id>/context.md`
- `.agent-workflow/tasks/active/<task-id>/decisions.md`
- `.agent-workflow/tasks/active/<task-id>/open_questions.md`
- `.agent-workflow/tasks/active/<task-id>/events.jsonl`
- `workspace/state.json.current_task_id`
- `workspace/state.json.current_intake_id = null`
- `workspace/events.jsonl`

Carry-forward rules:

- Raw request and summarized outcome move into `task.json.goal` and `context.md`.
- Task-local decisions move into the task's `decisions.md`.
- Durable decisions and preferences remain in workspace-level files and are referenced by id.
- Deferred options remain in `workspace/deferred_options.md` and are referenced by id when relevant.
- Non-blocking open questions move into task `open_questions.md`; blocking questions prevent promotion.

Postconditions:

- Intake status is `promoted`.
- Task status is `planning`.
- The task references `source_intake_id`.
- A `task_promoted` event links intake id and task id.

Failure handling:

- Create the task directory in a temporary path, then rename into `tasks/active/` after required files are written.
- If the rename fails, leave the intake unchanged and emit no promotion event.
- If state update fails after task creation, the next script run must reconcile by reading the `task_promoted` event in the task event log.

### `start_execution`

Purpose: mark a planned task as ready for subagent execution.

Preconditions:

- Task status is `planning` or `ready`.
- `context.md`, `implement.md`, and `verify.md` exist.
- Acceptance criteria or validation revision exists.
- User has confirmed the current validation summary when required.

Writes:

- `task.json.status = executing`
- `task.json.current_step`
- `task.json.assigned_subagents`
- task `events.jsonl`
- `workspace/state.json.active_task_ids`

Failure handling:

- If required task package files are missing, keep status unchanged and emit `execution_start_rejected`.

### `complete_verification`

Purpose: close the implementation/check loop based on verification evidence.

Inputs:

- Verification result: `passed`, `failed`, or `blocked`.
- Commands run and their outputs or summaries.
- Reviewer findings.
- Optional user correction.

State transitions:

```text
verifying + passed  -> done
verifying + failed  -> changes_requested
verifying + blocked -> blocked
changes_requested   -> executing, after the main agent accepts a rework plan
blocked             -> planning or executing, after the blocker is resolved
```

Writes:

- `task.json.status`
- `task.json.verification_status`
- `verify.md` or `outputs/verification-<revision>.md`
- task `events.jsonl`

Failure handling:

- Verification failure must not be collapsed into `done`.
- User correction after implementation creates a new validation revision and moves the task to `changes_requested` unless the correction is purely explanatory.

## State Schemas

All machine-readable state files include `schema_version`. Scripts must reject unknown future major versions and should tolerate additive fields on the same major version.

### `workspace/state.json`

Minimum v1 shape:

```json
{
  "schema_version": "1.0",
  "current_intake_id": null,
  "current_task_id": null,
  "active_task_ids": [],
  "active_sessions": {},
  "last_event_seq": 0,
  "locks_summary": [],
  "updated_at": ""
}
```

Field roles:

- `current_intake_id`: intake currently being clarified by the main session.
- `current_task_id`: primary task for the main session.
- `active_task_ids`: tasks with status other than `done` or archived.
- `active_sessions`: session id to current intake/task pointer.
- `last_event_seq`: last workspace event sequence applied.
- `locks_summary`: non-authoritative summary; `locks.json` is authoritative.

### `task.json`

Minimum v1 shape:

```json
{
  "schema_version": "1.0",
  "id": "2026-05-20-agent-workflow",
  "source_intake_id": "2026-05-20-agent-workflow-intake",
  "title": "Build agent workflow",
  "type": "design",
  "status": "planning",
  "current_step": "clarify",
  "owner_session": "main",
  "assigned_subagents": [],
  "goal": "",
  "constraints": [],
  "acceptance_criteria": [],
  "validation_revision": null,
  "verification_status": "not_started",
  "related_files": [],
  "context_sources": [],
  "decision_refs": [],
  "deferred_option_refs": [],
  "subtasks": [],
  "locks": [],
  "last_event_seq": 0,
  "created_at": "",
  "updated_at": ""
}
```

Allowed `status` values:

```text
planning, ready, executing, verifying, changes_requested, blocked, done
```

Allowed `verification_status` values:

```text
not_started, running, passed, failed, blocked
```

`task.type` influences recommended flow but does not create separate lifecycle states. Initial values: `design`, `implementation`, `research`, `docs`, `bugfix`, `refactor`.

### `events.jsonl`

Every event line must include:

```json
{
  "schema_version": "1.0",
  "seq": 1,
  "id": "evt_000001",
  "type": "task_promoted",
  "actor": "main-agent",
  "entity_type": "task",
  "entity_id": "2026-05-20-agent-workflow",
  "correlation_id": "2026-05-20-agent-workflow-intake",
  "at": "",
  "before_status": "task_candidate",
  "after_status": "planning",
  "summary": "Promoted intake to formal task"
}
```

Events are append-only. Scripts assign `seq`; agents and plugins must not hand-edit event logs.

## Concurrency And Locking

The v1 locking model is local and single-machine only. It is intended to prevent accidental concurrent writes, not to solve distributed coordination.

Only scripts may write `.agent-workflow/` machine state. Main agents request changes through scripts. Plugins are read-only except for OpenCode runtime mutation of prompts/messages. Subagents may write task outputs assigned to them, but must not edit workspace state directly.

Minimum `locks.json` shape:

```json
{
  "schema_version": "1.0",
  "locks": [
    {
      "id": "lock_task_2026-05-20-agent-workflow",
      "scope": "task",
      "entity_id": "2026-05-20-agent-workflow",
      "owner": "session-id-or-subagent-id",
      "purpose": "promote_to_task",
      "acquired_at": "",
      "expires_at": "",
      "ttl_seconds": 300
    }
  ]
}
```

Lock scopes:

- `workspace`: changes to `workspace/state.json`, workspace decisions, or global preferences.
- `intake`: changes to one intake note.
- `task`: changes to task status or task package files.
- `output`: subagent-owned output files under one task.

Conflict policy:

- Lock acquisition failure returns a conflict to the main agent; do not spin or silently overwrite.
- Expired locks may be reclaimed by scripts after recording `lock_reclaimed`.
- Releasing a lock records `lock_released`.
- A session may renew only locks it owns.
- If two sessions both try to promote the same intake, only one may acquire the intake lock; the loser must re-read state and report the conflict.

## Sensitive Information Handling

The framework is local, but it still stores durable context. Agents must avoid writing secrets or sensitive personal data into workspace facts, events, task briefs, or subagent prompts unless explicitly required and approved.

Default rules:

- Do not store API keys, tokens, passwords, private keys, cookies, or credentials.
- Redact secret-looking values before writing `events.jsonl`, `facts.md`, `context.md`, `implement.md`, or `verify.md`.
- Prefer references to secure locations over copying sensitive content.
- If sensitive information is necessary for a task, record only the handling instruction, not the value.
- Subagent context packages should include the minimum required facts.

## Requirement Clarification State Machine

The main agent clarifies the user's need, not the workflow implementation.

Internal states:

```text
S0 Receive
  Receive the user's raw request.

S1 Understand
  Restate the desired outcome, suspected anti-outcome, and key point.

S2 Clarify Need
  Ask topic-focused question groups about the user's described need.

S3 Shape Options
  Present 2-3 user-facing approaches when more questioning has diminishing returns.

S4 Capture Choice
  Record the chosen approach, deferred alternatives, risks, and revisit triggers.

S5 Promote Candidate
  Decide whether the discussion is ready to become a formal work item.

S6 Ready For Work
  Move into design, planning, research, implementation, or verification.
```

Allowed regressions:

- `Shape Options -> Clarify Need` when options miss the user's intent.
- `Capture Choice -> Shape Options` when the user changes the tradeoff.
- `Promote Candidate -> Clarify Need` when a blocking ambiguity remains.
- `Ready For Work -> Clarify Need` when implementation or review reveals a requirement mismatch.

## User-Facing Clarification Rules

The old rule "ask at most one key question" is rejected. It loses important detail and can prevent users from clarifying their own expectations.

The replacement rule is:

```text
Advance one user-understandable topic per turn. Within that topic, ask several related questions when needed.
```

Default behavior:

- Ask 3-6 related questions when the topic needs exploration.
- Prefer confirmation, choice, and comparison questions.
- Ask about expected behavior, expected feeling, unacceptable outcomes, priorities, and tradeoffs.
- Do not expose internal workflow mechanics unless the user is explicitly designing those mechanics.
- After the user answers, summarize what is confirmed, what is unacceptable, what becomes a durable preference, and what remains open.

Avoid default questions about:

- Task package structure.
- Repo maps.
- JSONL files.
- Context injection.
- Ready gates.
- Subagent prompt mechanics.
- File structure or implementation internals.

Prefer user-facing wording:

| Internal concept | User-facing wording |
| --- | --- |
| intake note | record this requirement exploration |
| task | formal work item |
| ready gate | ready to start making it real |
| workspace decision | a decision to follow by default in future work |
| task decision | a decision for this work item only |
| deferred option | a postponed option worth revisiting |
| subagent | focused executor / specialist agent |
| context package | task brief for the executor |
| repo map | relevant code area |
| acceptance criteria | how you will judge that it is done |
| anti-outcome | a result you explicitly do not want |

## Question Generator

The question generator is a requirement completeness checker and low-friction confirmation tool.

Before asking questions, the main agent should internally:

1. Identify the need type.
2. Extract details the user already gave.
3. Identify gaps that may cause outcome mismatch.
4. Rank gaps by risk.
5. Ask only the highest-value questions.
6. Provide a recommended default so the user can say "use the default".

Question priority levels:

```text
P0 Blocking question: cannot design correctly without it.
P1 High-drift question: likely to produce an unsatisfactory result if skipped.
P2 Preference question: result can be built, but style/taste may drift.
P3 Implementation detail: the agent should decide unless explicitly constrained.
```

Default policy:

- Ask P0 and P1.
- Ask P2 only when the user wants fine control or when it strongly affects perception.
- Do not ask P3 unless the user's constraint makes it business-, architecture-, compatibility-, cost-, or maintenance-relevant.

For every generated question, check:

- Would skipping this likely cause user-visible mismatch?
- Is this a user decision rather than implementation detail?
- Can this be asked as a choice, confirmation, or contrast?

Stop asking and move to options or validation when:

- The desired outcome is stated or has an accepted default.
- The anti-outcome is stated or has an accepted default.
- The main path is clear.
- The most important boundary states are either confirmed or explicitly deferred.
- The user has enough information to choose between 2-3 approaches.

For high-detail requirements, the main agent should not ask more than two consecutive question groups without either summarizing the current interpretation or presenting a validation card. This prevents clarification from becoming a burden.

## High-Detail Requirement Handling

When the user gives a highly specific requirement, especially for complex UI, the main agent must not restart discovery from scratch. It should use a "known - gap - default" flow.

### Step 1: Summarize Known Details

Compress what the user already specified:

```text
Layout:
- ...

Components:
- ...

Interactions:
- ...

Animations:
- ...

Linkages:
- ...
```

Then say that these will not be re-asked unless misunderstood.

### Step 2: Identify High-Risk Gaps

Complex UI high-risk gaps include:

- First impression and visual hero.
- Core user path.
- Initial state.
- Component linkage rules.
- Animation trigger conditions.
- Animation timing and sequencing.
- Animation conflict handling.
- Empty, loading, error, disabled, and permission states.
- Long content and too-much-data behavior.
- Responsive behavior.
- Acceptable degradation.
- Explicitly unwanted visual style.

### Step 3: Ask One Gap Theme At A Time

For complex UI, recommended question themes are:

1. First impression and visual hero.
2. Core operation path.
3. Linkage and animation timing.
4. Boundary states.
5. Responsive behavior and degradation.

Example for linkage and animation timing:

```text
I want to confirm the linkage and animation timing, since this is where implementation often drifts:

1. When the user triggers A, should B/C respond at the same time or in sequence?
2. Which component is the main action, and which components follow?
3. If the user acts quickly several times, should the old animation be interrupted or finish first?
4. Should the motion feel light and responsive, or complete and ceremonial?
5. Which animation is essential, and which can be simplified?

My recommended default:
- The directly operated component responds first.
- Related components follow after 80-120ms.
- Rapid repeated actions interrupt the old animation and transition to the latest state.
- Essential motion is preserved; decorative motion is weakened.
```

## Handling User-Provided Implementation Details

When the user gives concrete implementation details, the main agent must distinguish hard requirements from implementation suggestions.

Hard requirement indicators:

- "must"
- "only"
- "do not use"
- "must use"
- "required"
- clear platform, dependency, compatibility, or design-system constraints

Implementation suggestion indicators:

- "could"
- "for example"
- "maybe"
- "consider"
- concrete technical detail without a reason

If unclear, ask:

```text
Is X a hard constraint, or is it mainly a way to describe the effect you want?
```

Default policy:

- Optimize for the intended outcome.
- Use the user's technology choice when it is a hard requirement.
- If it is only a suggestion, choose the most stable approach for the current codebase and explain only if the choice affects tradeoffs.

## Low-Reading-Cost Validation

For complex or high-detail requirements, the main agent should present validation in three layers:

```text
Layer 1: One-sentence intent.
Layer 2: Five-point quick check.
Layer 3: Detailed design, only when useful or requested.
```

Example:

```text
One sentence:
I will make this UI feel like a main-card-driven interaction where the side panel extends from the card and the background stays atmospheric but quiet.

Quick check:
- First glance: the user sees the main card and core action first.
- Main path: clicking the card expands it, then the side panel extends after it.
- Linkage: the background changes subtly and never steals attention.
- Motion: quick and responsive; repeated clicks interrupt old motion.
- Narrow screens: the main path becomes vertical and the side panel becomes a drawer.
```

Before implementation, the main agent should ask for confirmation in user-facing terms:

```text
If these five points match your expectation, I will turn this into an implementation task.
```

## Outcome-Language Correction

After implementation, the user should be able to correct drift without knowing implementation details.

Every complex or high-detail requirement should have a validation revision before implementation. The revision is the baseline for later verification and correction.

Validation revision file:

```text
.agent-workflow/tasks/active/<task-id>/outputs/validation-r001.md
```

Minimum content:

```markdown
# Validation Revision r001

Status: approved
Approved At: <timestamp>

## One-Sentence Intent
...

## Five-Point Quick Check
- ...

## Effect Validation Card
1. Initial state: ...
2. Main action: ...
3. Linkage: ...
4. Motion rhythm: ...
5. Boundary behavior: ...
```

`task.json.validation_revision` points to the active revision. Corrections create `r002`, `r003`, and so on instead of overwriting prior approved expectations.

User feedback template:

```text
[Position/component] is wrong.
It currently feels like [current feeling].
I want it to feel more like [target feeling].
```

Example:

```text
The right panel is wrong. It currently feels like a separate popup. I want it to feel like it naturally extends from the main card.
```

The main agent should translate this into implementation changes internally, without requiring the user to specify state management, animation APIs, CSS primitives, or component structure.

If feedback is vague, ask a contrast question:

```text
When you say the animation feels strange, I see two likely causes:

A. Timing problem: too fast, too slow, or awkward pauses.
B. Spatial continuity problem: it appears from the wrong place or feels disconnected.

I think it is closer to B. I will first fix the spatial continuity unless you disagree.
```

Common feedback mapping:

| User feedback | Likely meaning | Default correction |
| --- | --- | --- |
| Too sudden | Missing transition or too-short timing | Add entrance transition, extend by 50-120ms |
| Too slow | Animation too long or queued | Shorten timing, interrupt old motion |
| Too busy | Too many visual changes | Reduce background/decorative motion |
| Not responsive | Feedback delay | Add immediate feedback before detailed motion |
| Not unified | Components lack continuity | Add shared visual anchor or transition relationship |
| Steals attention | Supporting element hierarchy too strong | Reduce contrast or motion strength |
| Too cramped | Density too high | Add grouping, collapse, or spacing |
| Not what I described | Requirement interpretation drift | Return to the validation card and re-align |

Correction flow:

```text
user correction
  -> classify drift
  -> compare against active validation revision
  -> if correction changes expected behavior, create next validation revision
  -> set task status to changes_requested
  -> write correction summary to outputs/correction-rNNN.md
  -> re-enter executing after the main agent accepts the rework plan
```

If the correction only clarifies language without changing expected behavior, the main agent may update `outputs/correction-rNNN.md` without changing task status.

## Decisions And Deferred Options

Durable choices must not disappear when the user chooses a faster or lighter approach.

Record durable decisions at the workspace level when they affect future work. Record task-local decisions inside the task directory. Record postponed but important alternatives as deferred options.

Workspace files:

```text
.agent-workflow/workspace/preferences.md
.agent-workflow/workspace/decisions.md
.agent-workflow/workspace/deferred_options.md
```

Decision entry format:

```markdown
## D001: <short name>

Type: preference | architecture | workflow | task-local
Scope: workspace | task
Status: accepted | superseded | rejected
Date: <YYYY-MM-DD>
Source Task: <task-id or none>
Supersedes: <decision-id or none>

Decision:
...

Reason:
...
```

Workspace decisions override workspace preferences when they conflict. Task-local decisions override workspace defaults only for that task. If a task-local decision should become a default for future work, the main agent must explicitly promote it to a workspace decision instead of relying on implicit memory.

Deferred option format:

```markdown
## Deferred Option: <name>

Id: O001
Scope: workspace | task
Status: deferred
Chosen Instead: <chosen path>
Reason: <why not now>
Risk: <risk of deferring>
Source Task: <task-id or none>
Revisit When:
- <trigger>
- <trigger>
```

When the user chooses a minimal implementation, the main agent must record:

- The more robust option being deferred.
- Why it is not being done now.
- The risk created by deferral.
- The conditions that should trigger revisiting it.

## Formal Task Package

After an intake is promoted, a formal task directory contains:

```text
task.json
context.md
repo_map.json
decisions.md
open_questions.md
implement.md
verify.md
outputs/
research/
events.jsonl
```

`task.json` is the machine-readable source of truth:

```json
{
  "id": "2026-05-20-agent-workflow",
  "title": "Build agent workflow",
  "status": "planning",
  "owner_session": "main",
  "goal": "",
  "constraints": [],
  "acceptance_criteria": [],
  "related_files": [],
  "context_sources": [],
  "subtasks": [],
  "locks": [],
  "created_at": "",
  "updated_at": ""
}
```

`context.md` is a concise model-readable summary. It should not be treated as machine state.

`repo_map.json` is a generated cache of relevant code areas. It is useful for execution, but scripts may regenerate it when stale. If unavailable, subagents fall back to `context.md`, `implement.md`, and targeted code search.

`implement.md` is the execution brief for the implementation subagent.

`verify.md` is the verification brief for the check subagent.

`events.jsonl` is append-only and supports debugging, session sync, and retrospective review.

`workspace/sessions/` stores per-session pointers and lightweight summaries. Session files are runtime aids, not durable project memory. Durable facts belong in workspace files or task files.

## OpenCode Runtime Responsibilities

### Session Start Plugin

Injects global rules, workspace summary, active intake/task summary, and relevant preferences at the start of a main-agent session.

It skips subagent turns to avoid drowning subagent-specific context.

### Workflow State Plugin

Does not inject `<workflow-state>` into main-agent turns. Main-session task awareness should come from explicit `list-active` script checks before execution, not per-turn prompt injection.

### Subagent Context Plugin

Intercepts subagent task dispatch and injects context based on the active task and subagent type.

The plugin is read-only with respect to workflow state. It may mutate the outgoing subagent prompt, but it must not create intakes, promote tasks, change task status, or append decisions.

## Internal Runtime Contract

This section is internal-only. The main agent and plugins may rely on it, but user-facing conversation should use the friendlier terms defined earlier.

Required dispatch convention:

```text
Active task: <task path or id>
```

The prompt line is a fallback when hook/session resolution fails.

Context injection rules:

- `workflow-research` receives the research question, relevant workspace facts, and the task research output path.
- `workflow-implement` receives `context.md`, `implement.md`, relevant decisions, relevant deferred options, active validation revision, and selected code context.
- `workflow-check` receives `context.md`, `verify.md`, active validation revision, relevant decisions, and changed-file context.
- Plugins do not decide whether dispatch should happen; the main agent decides and calls the subagent.
- Scripts are the only write path for `.agent-workflow/` machine state.

Internal artifacts such as `repo_map.json`, `events.jsonl`, validation revision ids, and dispatch hints should not appear in normal user-facing explanations unless the user is explicitly reviewing runtime design.

## Execution And Verification Flow

After a task is ready:

```text
main agent
  -> dispatch workflow-research when research is needed
  -> dispatch workflow-implement for scoped implementation
  -> dispatch workflow-check for verification
  -> integrate results
  -> summarize outcome to user
  -> capture decisions or lessons if needed
```

Subagents should receive only the context they need:

- Requirements and acceptance signals.
- Relevant files or repo areas.
- Durable preferences that affect this task.
- Deferred options and non-goals that prevent overbuilding.
- Verification expectations.

Subagents should not receive unrelated chat history.

## Risks

- The first version is OpenCode-first, so platform portability is deferred.
- Topic-based clarification can feel heavier for very small requests; an explicit lightweight bypass may be needed later.
- Complex UI validation without visual mockups still relies on textual alignment.
- Local file locks may be insufficient for heavy multi-session concurrent editing.
- Durable preferences can become stale if not reviewed periodically.

## Deferred Capabilities

### Multi-Platform Protocol Layer

Status: deferred
Chosen Instead: OpenCode-first local runtime.
Reason: The first version should validate the workflow loop before abstracting platform adapters.
Risk: Later platform support will require an adapter layer.
Revisit When:
- The OpenCode runtime is stable.
- The task package schema stops changing frequently.
- There is a concrete need for Claude, Codex, or another platform.

### Productized CLI Installer

Status: deferred
Chosen Instead: local directory and script framework.
Reason: Installation, update, and migration support would expand v1 beyond the core workflow problem.
Risk: Manual setup may be less polished.
Revisit When:
- The local framework is used repeatedly.
- More than one workspace needs the same setup.

### Visual Companion For Complex UI

Status: deferred
Chosen Instead: textual validation cards and correction protocol.
Reason: Textual summaries are enough for first-version alignment and cheaper to implement.
Risk: Highly visual requirements may still drift.
Revisit When:
- UI drift remains frequent after validation cards.
- Browser preview or mockup support becomes a repeated need.

## Acceptance Criteria

The design is ready for implementation planning when:

- It defines the OpenCode-first local framework boundary.
- It separates workspace intake from formal task lifecycle.
- It defines the main agent, subagent, script, and plugin responsibilities.
- It defines the requirement clarification state machine.
- It defines the question generator and high-detail requirement handling.
- It defines how durable decisions and deferred options are persisted.
- It defines how complex UI expectations are validated with low reading cost.
- It defines how users can correct implementation drift in outcome language.
- It identifies deferred capabilities and revisit triggers.
