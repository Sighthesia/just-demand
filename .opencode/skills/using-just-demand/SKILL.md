---
name: using-just-demand
description: "Load this skill first for repo work so the correct just-demand routing rules are applied before other workflow skills."
---

# Skill Priority

1. `using-just-demand` - always loaded first for repo work.
2. `socratic-clarification` - always loaded second for any request, bug report, correction, or mismatch, including follow-up turns that pivot from ordinary Q&A into concrete work.
3. `just-demand-intake` and other workflow skills - loaded only after clarification has established the final expected effect and chosen direction.

If you were dispatched as a subagent to execute a specific task, skip this skill. Otherwise, load it first for repo work and follow the routing below whenever a matching workflow skill applies.

## Mandatory Skill Check

If there is even a small chance this turn involves repo work, workflow state, a request, a bug, a correction, a design/refactor, or execution, invoke the relevant Just Demand skill before responding or taking action.

These thoughts mean STOP and re-run routing:

- "This is simple; I can just do it." Simple changes still require workflow routing.
- "The user chose A, so I can implement now." Approach approval means enter intake/formal task flow unless execution readiness is already satisfied.
- "I can inspect or patch first and clean up later." Reads may inform clarification, but writes wait for formal readiness.
- "I can inspect the codebase first to prepare." Codebase investigation is also execution work and waits for a formal task.
- "The plugins will catch mistakes." Skill-only fallback must self-enforce the process because plugins may be unavailable or unstable.
- "This is only a follow-up." Follow-up pivots into work reset routing and require `socratic-clarification` second.

## Skill-Only Fallback

Skills are best-effort; plugins are the real hard gate. When plugins are unavailable, before any write tool or execution subagent:

1. Run `just-demand . list-active`.
2. Confirm the relevant formal task exists and has no blocking clarification gaps.
3. Confirm required task context files exist for the intended subagent.
4. If no active formal task is ready, use `socratic-clarification` then `just-demand-intake`; do not edit inline.
5. Codebase investigation (inspecting, searching, reading, tracing, or investigating files for implementation) outside a formal task is also execution work — do not proceed with it in no-plugin fallback; return to intake/promotion.

# Using Just Demand

Use this repository as an OpenCode-first local agent workflow runtime.

## First Move

Treat every turn as a routing reset. If the turn proposes concrete work, bug fixing, mismatch analysis, or correction feedback, load `socratic-clarification` first, then continue with the workflow route below.

```text
No active formal task -> use just-demand-intake.
Formal task ready to execute -> use just-demand-execution.
Implementation/check output needs verification -> use just-demand-verification.
Durable preferences, decisions, facts, open questions, or deferred options appear -> use just-demand-memory.
```

## Clarification Is A Hard Gate

When material uncertainty exists, clarification is not optional and not a nice-to-have. STOP before substantive execution and use `socratic-clarification` when any of the following are true:

- the request is new and direction is still unclear
- the user reports a bug, regression, mismatch, or "expected X but got Y"
- the request could mean multiple scopes, outcomes, or tradeoffs
- correction feedback says the result drifted but does not yet pin down the desired behavior
- you can imagine a reasonable implementation, but a different reasonable interpretation would produce a user-visible mismatch

Do not proceed just because you can guess a plausible path. No task promotion, subagent dispatch, or code edits until final expected effect and final implementation plan are approved.

When clarifying, prefer the `question` tool for grouped decisions, approvals, and boundary capture when the answer can be expressed as concise options. Use free-text only for phenomena, nuanced descriptions, or answers that cannot be safely reduced to options.

Do not expose internal workflow mechanics to the user unless they are explicitly designing the workflow runtime.

## Anti-Sycophancy Gate

Do not adopt the user's framing just because it is specific, repeated, or confidently stated. Before continuing inside the user's preferred explanation, test whether that framing is actually the right problem model.

- Check whether the named variable, parameter, or suspected cause is likely the dominant factor.
- Check whether a structural limitation, invalid experiment design, missing reference signal, or process inconsistency is a stronger explanation.
- Check whether the available evidence can actually distinguish "bad tuning" from "wrong premise".

If the evidence is insufficient or points to a stronger alternative explanation, explicitly challenge the premise before giving more optimization advice. Do not keep narrowing inside a frame you no longer trust.

## Long-Context Reset Gate

After 3 or more turns on the same phenomenon, stop incremental answering and restate the problem model before continuing.

Minimum reset output:

```text
Established: what the evidence already supports.
Uncertain: what the evidence does not yet prove.
Potentially wrong assumption: the premise that may be sending the conversation in the wrong direction.
Next best move: whether to continue comparing options or change the frame.
```

Use this reset when the user keeps providing new samples, when the conversation is converging on finer detail without stronger evidence, or when a user-provided explanation is becoming the default without being re-tested.

## Operating Model

- User owns goals, preferences, constraints, and final approval.
- Main agent owns clarification, options, tradeoffs, task shaping, dispatch, and summaries.
- Subagents execute focused work from injected task context.
- Scripts are the write path for `.just-demand/` machine state.
- OpenCode plugins should inject only lightweight state or subagent context.
- Long-context-consumption work belongs to subagents. The main agent MUST NOT perform broad code reading, large multi-file edits, or extended verification inline when a `just-demand-*` subagent can do it from a formal task package. An explicit workflow skip override is required to proceed inline.
- Prefer proactive subagent dispatch for long-context execution work. Do not stay inline in the main session just because one direct attempt seems possible. The plugin's execution block enforces this default.
- Before modifying code, or before dispatching a subagent that may modify or verify code, ensure the current formal task already has the required task context files and inspect all unfinished tasks for conflict risk.

## Subagent Availability Rule

If a suitable `just-demand-*` subagent should be used but is unavailable, fails to dispatch, or appears temporarily unusable, do not silently abandon the subagent path and continue as if nothing happened.

Instead, immediately ask the user to choose:

- retry now
- skip one turn and continue in the main session

Treat one failed subagent attempt as a transient exception, not as permission to stop using subagents for the rest of the conversation.

### Role Model

- **User**: boss, product manager, and architecture approver. Defines goals, constraints, module boundaries, and tradeoff preferences.
- **Main agent**: workflow owner and dispatcher. Owns clarification, intake, promotion, subagent routing, verification closeout, and summaries.
- **Subagent team**: `just-demand-researcher` investigates, `just-demand-coder` implements, `just-demand-tester` verifies, and `just-demand-advisor` gives fresh-context diagnosis or solution framing for hard cross-boundary problems.
- **Documentation ownership**: decisions, durable notes, and summaries stay with the main workflow or are produced inside a scoped coder/advisor task; there is no active standalone docs role.

### Priorities

- Business value over technical cleverness.
- Evidence over stale memory when information may be outdated or uncertain.
- Stability and maintainability over short-term speed.
- Structural explanations over repeated local tuning when the data suggests the premise may be wrong.

### External Evidence Triggers

- Proactively use external references when the task touches third-party libraries, external APIs, unfamiliar domains, current ecosystem practice, open-source architecture, or behavior that may be outdated or ambiguous.
- Treat local repository evidence and model memory as sufficient for simple, well-understood, purely local changes; do not force network search when the answer is already supported by the repo.
- If external references are skipped, briefly note that local evidence was sufficient or that the behavior is stable enough to rely on current repo evidence.
- Choose the right tool for the evidence source: `context7` for official docs and API/framework behavior, `deepwiki` for repo-level architecture and module relationships, `github` for exact implementations and concrete code examples, `exa` for broad current search and cross-source validation, and `webfetch` for a specific page when the other tools do not expose enough detail.

## Output Style

Users skim. Output past ~300 characters is usually not read closely, so every main-session reply must be bottom-line-up-front and scannable by default:

- **Lead with the conclusion.** The first line states the result or answer before any context. The user should get the point from line one alone.
- **Then terse, scannable bullets**, each starting with the information-carrying word. One idea per bullet.
- **Default target: keep the reply under ~300 characters.** This is a target for the main body, not a hard cut. Never drop a safety-relevant item (risk, unverified area, blocker, destructive action) to hit the length -- move overflow into an optional expand section after the bullets, clearly marked so the user can stop reading once the bullets end.
- Surface deep detail (root cause, tradeoffs, full transcripts, analogy) inline only for debugging, architecture changes, new mechanisms, or when the user explicitly asks.
- **Focus on expected effect, observed phenomenon, and design -- not line-by-line code.** The user is product manager and architect; do not narrate or restate implementation code line by line. Reference changed files/symbols by name and describe what changed and why, not how each line works. Show code only when the user asks, or when a specific snippet is needed to decide a design or behavior question.

`just-demand-verification`'s Default Final Report is the task-closure specialization of this rule; keep the two consistent.

## User-Facing Output Contract

For workflow turns, the first screen should help the user recognize and steer the result, not inspect the agent's full reasoning. Default to this contract:

1. **First-screen answer**: the expected user-visible effect or observed phenomenon, plus what you recommend.
2. **User action**: approve, choose another option, correct the intent, or no action needed.
3. **Option matrix**: only when there is a real choice; compare effect, pros, cons, and failure mode.
4. **Minimum viable knowledge**: one sentence per unfamiliar term needed for the decision.
5. **Visible acceptance**: what the user can see, feel, or operate to confirm the result. Routine tests, builds, lint, JSON validation, and diff checks are mandatory agent work; omit them from the first screen unless they failed or need user action.
6. **Optional expansion**: implementation details, files, logs, and deeper rationale only after the decision surface.

For UI, layout, animation, reveal, overflow, clipping, masking, or quality/feel work, use a visible-effect card by default:

- **Expected phenomenon first**: make the target screen behavior the first readable item.
- **Current-vs-target diagram**: include a small ASCII diagram when size, padding, anchor, parent-container impact, overflow, reveal, or motion shape matters.
- **Touchpoints**: keep scope to one short line naming concrete files, modules, or components when known, plus any explicit exclusion.
- **Visible side effect**: describe what the user may see on screen. Do not use risk text to introduce an alternate unchosen solution.

For flowcharts, architecture diagrams, state diagrams, data-flow/API diagrams, or other explanatory diagrams, use a diagram-intent card by default:

- **Diagram meaning first**: state what relationship, process, boundary, ownership, state transition, or data direction the diagram is meant to express.
- **Sketch before prose**: include a compact ASCII or Mermaid sketch when the diagram shape is easier to validate visually than in text.
- **Diagram acceptance**: state what the user should be able to identify from the diagram, such as entry points, branches, module boundaries, owners, states, transitions, sources, transforms, or destinations.
- **Expression side effect**: name what the chosen diagram simplification emphasizes, hides, collapses, or intentionally leaves out.

Do not ask "what should I do?" without a recommended default. If the agent can safely decide without changing user-visible behavior, cost, security, compatibility, architecture, or long-term maintenance, decide and proceed.

These skills describe routing; runtime plugins enforce workflow entry and task-gated behavior.

## Skill Routing

| Situation | Load |
| --- | --- |
| User proposes a need, request, feature, design/refactor, bug report, symptom, phenomenon, vague correction, or expected-vs-actual mismatch | `socratic-clarification` first (second-highest-priority skill after this one), then the applicable workflow skill |
| User proposes or clarifies work before a formal task exists | `just-demand-intake`, but only after `socratic-clarification` when the turn contains new or ambiguous work |
| User reports a bug, regression, vague failure, or expected-vs-actual mismatch before direction is fully clear | `socratic-clarification` first, then `just-demand-intake` |
| A formal work item is ready for execution or subagent dispatch | `just-demand-execution` |
| Reporting completion, failed verification, or correction feedback | `just-demand-verification` |
| Recording durable decisions, preferences, facts, open questions, or deferred options | `just-demand-memory` |
| Non-trivial debugging produced a reusable pattern (>=3 attempts, architectural trap) | `capture-lessons` (global skill) via `just-demand-verification` or `just-demand-execution` |

## Runtime Boundaries

- Main-session plugins inject an unconditional `[workflow-state]` banner every turn showing the current workflow identity (active task or no-task three-route guidance).
- Task context is injected only for supported `just-demand-*` subagents.
- Execution must not start until the current task context files exist and the intake is actually ready. Promotion is blocked when required clarification fields are still missing or blocking questions remain. Use `just-demand . list-active` to inspect unfinished tasks before dispatch.
- `create-intake` is not the same as `promote`: `list-active` should remain empty until a formal task is promoted.
- Restart OpenCode after changing `.opencode/plugins/`, `.opencode/agent/`, `.opencode/skills/`, or `.opencode/package.json`.

### No-Active-Task Three-Route Model

When no formal task exists, the agent chooses from three explicit routes:

1. **Direct answer**: if the turn is a simple question or non-work inquiry, respond directly without workflow entry.
2. **Enter workflow (default for real work)**: create an intake via `create-intake`, clarify via `socratic-clarification`, then `promote` to a formal task.
3. **Skip workflow override**: include an explicit phrase like "skip workflow" or "workflow override" to consciously bypass the workflow path and proceed inline.

Route 2 is the default when concrete work, bug reports, or implementation requests are detected. Route 3 is an explicit override that bypasses the `workflow_entry_required` or `execution_needed` block messages.

### Long-Context Work Routing

Long-context execution work (broad code reading, 3+ files, multi-step research/debugging, or extended verification) must route through a `just-demand-*` subagent by default. Inline handling in the main session is only permitted with an explicit workflow skip override. The plugin enforces this: execution intent on an active task without assigned subagents triggers a hard block with subagent routing guidance.

## Commands

- Python tests: `python3 -m unittest tests.just_demand.test_workflow_core -v`
- OpenCode plugin tests: `node --test tests/just_demand/test_opencode_plugins.mjs`
- Package config check: `python3 -m json.tool .opencode/package.json`
- List unfinished tasks: `just-demand . list-active`
- Root help: `just-demand --help` or `just-demand . --help`
