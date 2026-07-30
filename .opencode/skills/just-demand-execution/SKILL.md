---
name: just-demand-execution
description: Use when a formal work item is ready for main-agent execution, when selectively dispatching just-demand-tester or just-demand-advisor, or when explicitly resuming a compatibility researcher/coder role.
---

# Workflow Execution

Execute formal work items in the main session or through selectively dispatched subagents, with script-owned state.

Canonical workflow spec: `docs/workflow-spec.md`. The spec is the reference for lifecycle, role model, context-package requirements, and the **task context as user-expectation contract** model. Context files capture what the user expects to see, feel, or operate — not just an implementation brief.

## Core Rules

- Main agent owns execution and may use subagents as selective accelerators.
- Subagents do not inherit full chat history.
- Scripts are the only write path for workflow machine state under `.just-demand/`.
- Plugins and agents may read state, but lifecycle transitions must go through scripts.
- Do not dispatch implementation before the user has confirmed the direction and the task is ready.
- Subagent dispatch is governed by six hard eligibility gates (goal stability, boundary independence, context compressibility, result verifiability, capability match, failure recoverability) and three net-benefit questions (total effort savings, drift-risk reduction, separable artifact). Dispatch only when all nine answers are "yes". Otherwise, the main agent executes — even for long-context or multi-file work.
- Small reads/edits (~几十行) and high-confidence, script-verifiable checks (bug detection, data analysis) remain in the main session without subagent dispatch.
- Main-session execution needs no dispatch override once the formal task is ready. Reassess the gates only when considering a new dispatch.
- When reporting progress or a result, lead with the user-visible effect or the decision the user needs to make; treat task state, mark commands, and checkpoint mechanics as supporting detail.
- If a suitable subagent is unavailable, ask the user to retry now or skip one turn rather than silently falling back.
- Implementation or verification must not start unless the current formal task already has the required task context files. Do not treat missing task context as a recoverable inline shortcut.
- If analysis, diagnosis, or advice turns into code modification, treat that as a boundary reset and return to clarification before writing unless the task already contains explicit execution readiness.
- Before dispatching a subagent or starting implementation, mark the task status with `mark`.
- Before ending a turn with unfinished work, mark the task `paused` with current progress and known impact.

## Role Dispatch Guide

- `just-demand-tester`: use for validation against the task brief, visible-effect checks, and low-risk local fixes after implementation or when a result needs review.
- `just-demand-advisor`: use for fresh-context diagnosis, repeated failures, cross-boundary framing, or when the main session needs an independent recommendation before choosing a path.
- The main agent owns research, repository inspection, product judgment, architecture, and implementation.
- `just-demand-researcher` and `just-demand-coder` are compatibility-only. Dispatch either only when the active legacy task already records the role or the user explicitly requested it; never infer permission from workload, file count, context length, or task type.
- For a user-explicit compatibility dispatch on a new task, prefix Requested Work with `JUST_DEMAND_EXPLICIT_LEGACY_ROLE`. The plugin strips this marker before injection. Never add it without an explicit user request.

Capability defaults:

- Fast models handle only mechanical tasks such as renames, bounded replacements, routine commands, and deterministic checks.
- Architecture, product interpretation, cross-module judgment, and frontend visual/interaction/copy quality stay with the main agent by default.
- Quality-sensitive work is dispatchable only when the observable target is explicit and the selected model can meet it.

- Approval words alone do not bypass readiness. A valid structured task authorization covers continuous execution, verification, and closeout; do not ask the user to approve internal lifecycle transitions.

## Output Handoff Rules

- Tester output should drive pass/fail, low-risk fixes, and closeout readiness.
- Advisor output should reframe the problem or sharpen the next decision, not replace execution.
- Compatibility researcher/coder output follows its historical handoff contract only when that path was explicitly enabled.

### No-Plugin Fallback Gate

When plugins are unavailable, disabled, or unstable, this skill is only best-effort and cannot hard-block tools. The agent must self-enforce the same preconditions before any write tool or execution subagent:

1. Run `just-demand . list-active`.
2. Confirm the intended formal task exists and is ready for execution.
3. Confirm required context files exist for the intended `just-demand-*` subagent.
4. If unfinished tasks exist but no current task is selected, recover with `just-demand . select-task <task-id>` or `just-demand . resume <task-id>`.
5. If any check still fails after selection, stop and route back to `socratic-clarification` or `just-demand-intake`; do not edit inline.

### Evidence-First Execution

- Evidence over stale memory. When information may be outdated or uncertain, verify against current codebase state.
- Prioritize business value over technical cleverness. Stability and maintainability over short-term speed.

### Dependency Justification

Before introducing a new dependency, briefly explain:

1. Why standard library or existing modules are insufficient
2. Maturity and ecosystem position
3. Alternatives considered
4. Why the benefit justifies maintenance cost

### Post-Change Structure Summary

After adding or modifying UI or a new feature, briefly list the main structure of the changed area:

- Changed components/modules (use actual names from code)
- Key containers
- Important props/state
- Entry points

Keep this summary short and structured. Prefer names as they appear in code. If names are unclear, propose concise labels based on the current structure.

### User-Facing Execution Updates

When reporting execution progress or subagent results to the user, follow the User-Facing Output Contract from `using-just-demand` and keep the first screen effect-first. Do not surface internal workflow labels like `Thought`, `Skill`, `Decision card`, `Validation card`, or full task-form fields in the opening block.

Result-first progress summary:

```text
Result: <what changed or what is happening now, in user-visible terms>
Status: <current state or concise progress>
Risk: <remaining risk or none>
Checks: <routine verification detail only if failed or explicitly needed>
```

- **User action**: usually "none" during execution unless a real product/architecture/risk decision is needed.
- **Continuous execution**: after task authorization is valid, do not end a turn merely because intake, promotion, implementation, verification, or closeout changed phase. Stop only for a material contract deviation, unresolved blocker, failed safety boundary, or completion.
- **Recommended default**: if blocked, state the recommended next move before alternatives.
- **Analysis summary shape**: for analysis or diagnosis updates, lead with the result and concise status before any verification details; keep checks and transcripts below the fold unless something failed.
- **Visible or diagram acceptance first**: for UI work, state the expected on-screen behavior, rejected anti-outcome, and visible side effects before routine checks; for diagram work, state the intended diagram meaning, diagram acceptance, and expression side effects before routine checks.
- **Review-ready detail**: when work is ready for review, keep expected effect, anti-outcome, checks run, and remaining risk in the report body, but defer routine tests/build/lint detail unless a check failed or the user asked for it.
- **Optional expansion**: changed files, structure summary, logs, and detailed rationale after the user-facing result.

When summarizing subagent work back to the user, preserve the subagent's role-specific payload:

- Researcher: scope, evidence, sources, recommendation.
- Coder: files changed, verification, concerns.
- Tester: findings, fixes applied, verification results, residual risk.
- Advisor: frame, key findings, confidence, recommendation, alternative explanations.

Do not make the user choose implementation details. Escalate only when the wrong guess would change user-visible behavior, architecture boundaries, compatibility, security, cost, or long-term maintenance.

## Subagent Routing

- `just-demand-tester`: verify requirements and fix only low-risk local issues within scope.
- `just-demand-advisor`: independent analysis and advisory for difficult or cross-boundary problems; no direct large-scale implementation.
- `just-demand-researcher` and `just-demand-coder`: compatibility-only roles for a recorded legacy assignment or explicit user request.
- Documentation, decisions, durable notes, research, implementation, and summaries are owned by the main agent. There is no standalone docs subagent.

## Subagent Unavailable Handling

If all dispatch gates pass but the selected workflow subagent is unavailable, dispatch fails, or the tool appears temporarily unusable, do not silently change the plan.

Immediate next step:

1. Tell the user the subagent path is currently unavailable.
2. Ask the user to choose one of these options:
   - retry now
   - skip one turn
3. If the user chooses retry, attempt the same subagent path again on the next turn and resume the prior subagent session when a `task_id` is available.
4. If the user chooses main-session execution, the main agent takes over that unit; this is not a workflow bypass.

Use the `question` tool when feasible so the user can answer with one click. Treat the failure as transient unless there is strong evidence the subagent path is structurally unavailable.

Subagent interruptions are often caused by model provider or network errors, so retrying the same session is usually the right first move.

## Task Marking Policy

Use `mark` for high-frequency, low-token state updates:

```text
just-demand . mark <task-id> <status> [--progress N] [--impact PATH] [--note TEXT]
```

### When to mark

- **Before dispatch/implementation**: mark `executing` with progress and impact scope.
- **Diagnosing failures**: mark `debugging` with note about what's being investigated.
- **Near completion, minor adjustments**: mark `tweaking` with high progress.
- **Turn ending with unfinished work**: mark `paused` with current progress and known impact.
- **Completion**: do not use `mark` to set `done`; completion must flow through verification so archive-on-done can preserve and close the task.

### Status semantics

- `debugging`: actively diagnosing or fixing; higher conflict/instability signal.
- `tweaking`: mostly complete, low-risk adjustment only; lower conflict signal.
- `paused`: not currently being modified; progress and impact remain visible.
- `executing`: actively implementing; standard conflict signal.

### Impact scope

List the main directories, modules, or files affected. Use short user-readable paths like `.just-demand/scripts/`, `tests/just_demand/`, or `.opencode/skills/just-demand-execution/`. This helps other agents avoid overestimating conflict risk.

### Selective Dispatch Check

Before dispatching, run through the six gates quickly in your head or note:

- **Goal stable?** The task goal is final, unambiguous, and user-approved.
- **Boundary independent?** No cascading decisions into other modules/scope.
- **Context compressible?** Essential context fits a subagent prompt without losing signal.
- **Result verifiable?** Acceptance criteria are concrete and checkable.
- **Capability match?** Subagent role cleanly fits the work shape.
- **Failure recoverable?** A failed result costs at most one retry.

If any gate fails or you are uncertain, keep the work in the main session. If all six pass, require "yes" to all three net-benefit questions:

1. Will dispatch save total effort after prompt writing, execution, review, and expected rework?
2. Will dispatch reduce rather than increase context-drift risk?
3. Will dispatch produce a cleanly separable, independently verifiable artifact?

Any "no" or uncertainty means main-session execution.

## Dispatch Prompt

Use this minimum dispatch package and keep each section short:

```text
Active task: <task-id>

Goal: <local result>
Scope: <allowed reads and writes>
Decided approach: <decisions the subagent must follow>
Constraints: <what must not change>
Acceptance: <objective pass/fail checks>
Return: <changes, checks, deviations, blockers>
```

`Active task:` is a fallback for context injection failures. Do not paste the full clarification artifact or duplicate the injected task context. If the six sections cannot stay short without losing critical signal, narrow the unit or keep it in the main session.

## Progressive Clarification Routing

Before execution, if the active task still contains unresolved uncertainty about the user's intended effect, observed phenomenon, boundaries, or tradeoffs, load `socratic-clarification` and route back to clarification. Do not dispatch implementation while the final expected effect and final implementation plan are not explicit.

If the gates and benefit judgment point to subagent dispatch, but no supported subagent is available right now, ask the user to retry now or skip one turn instead of silently falling back.

## Clarification Gate Before Execution

Before dispatching any implementation subagent, verify that the task is sufficiently clarified:

1. Check that `blocking_questions` in the task's clarification data is empty.
2. Check that `scope`, `expected_behavior`, and `actual_behavior` (for bug work) are non-empty.
3. For design and implementation tasks, check that `final_expected_effect`, `chosen_approach`, the agent-owned `final_implementation_plan`, and structured task authorization are present.
4. If any blocking question remains or critical fields are empty, DO NOT dispatch. Route back to clarification instead: update the intake with the gaps and ask the user.
5. Do not guess what the user wants to fill in missing fields. Ask.
6. When clarifying gaps, prefer the `question` tool for grouped decisions, approvals, and boundary capture when the answer can be expressed as concise options.

### Visual Interaction Execution Gate

Before dispatching UI, animation, layout, reveal, overflow, clipping, or quality/feel work, check that the task context names the intended user-visible solution shape. If containment, synchronized entrance, and layout/reflow would feel different, the chosen approach must say which one is primary.

Do not dispatch implementation when the plan only says "fix overflow" or "clip it" but the user's feedback is about foreground/background timing, entrance choreography, layout feel, hard cuts, or visual quality. Route back to `socratic-clarification` and present the relevant options.

If clipping, masking, opacity, or delayed drawing is used only as a safety guardrail, record the primary behavior separately so subagents do not mistake the guardrail for the design.

## Execution Loop

1. Confirm active formal work item.
2. Run `just-demand . list-active` and inspect all unfinished tasks for conflict risk.
3. Remember that `create-intake` alone will not appear in `list-active`; only promoted formal tasks do.
4. If `list-active` shows unfinished tasks but no current task is selected, pick the intended task with `just-demand . select-task <task-id>` or `just-demand . resume <task-id>`.
5. Ensure the current task package has the required files for the intended subagent.
6. Verify the clarification gate above passes. If not, route back to clarification.
7. Apply the six eligibility gates and three net-benefit questions. Dispatch the narrowest suitable subagent only when all nine answers are "yes". The main agent executes when any answer fails or is uncertain, including substantial code reading, multi-file editing, or extended verification. Small work always stays inline.
8. Review subagent output before moving to the next phase.
9. Run verification before claiming completion.

Quick recovery when execution is blocked by task selection state:

1. Run `just-demand . list-active`.
2. Choose the intended unfinished task.
3. Run `just-demand . select-task <task-id>` or `just-demand . resume <task-id>`.
4. Retry execution only after the task is current and its context files exist.

## Checkpoint Commit Policy

Every clean verification result should produce a checkpoint commit. The commit represents "this verified slice passed engineering checks", not permanent product finality. **Commits are the default, not the exception.** The script handles most of the work; the agent just needs to make sure the conditions are met and call the right command.

### Primary commit path: via `complete-verification`

When verification passes, the script-owned closure command creates the checkpoint commit automatically:

```text
just-demand . complete-verification <task-id> passed "<summary>"
```

That command records verification, runs the checkpoint-commit safety gate, and archives the task. Pass `--no-checkpoint-commit` only when the user explicitly asked to avoid committing.

### Standalone commit path: mid-task checkpoints

After any clean `just-demand-tester` result, create a mid-task checkpoint without closing the task:

```text
just-demand . checkpoint-commit <task-id>
```

This is useful for:
- Long tasks with multiple independently verified slices.
- After fixing issues found by `just-demand-tester` before moving to the next phase.
- Any time a safe, scoped commit would reduce risk.

### When to commit — proactively

Commit after **every** meaningful clean verification:

- After `just-demand-tester` passes with no unresolved findings.
- After fixing low-risk local issues and re-verifying.
- After the user expresses positive acceptance (e.g., `effective`, `good`, `OK`, `LGTM`, `works`, `looks good`, `valid`, `不错`, `有效`, `可以`, `没问题`, `达成`, `就这样`).
- Before ending a multi-step implementation turn, even if the full task is not done yet.

Do not wait for perfect conditions. If the verified slice is clean, commit it.

### Impact scope recommendation (not a gate)

At execution start, the script records existing worktree paths and diffs as a baseline. A later commit stages task-only hunks from shared files when they do not overlap the baseline. If Git cannot safely isolate a hunk, it commits the current full file and records it as a mixed hunk instead of leaving verified work uncommitted. Setting `impact` via `mark --impact PATH` further narrows the eligible paths. Legacy tasks without a baseline retain the all-non-generated-files fallback.

### When NOT to commit

- The user explicitly says to avoid committing.
- No agent-made changes exist yet (planning/discussion phase only).
- The task is in `debugging` or `tweaking` status with repeated unstable feedback (pause auto-commit until next clean check).
- Tests fail and the user has not overridden.

### Correction commits

- Small corrections: use follow-up commits on the same branch.
- Fundamentally wrong direction: use a revert commit.
- Do not rewrite history; prefer follow-up or revert commits.

### Pre-commit safety gate (script-owned, no manual steps needed)

The `create_checkpoint_commit` function in `workflow_core.py` handles the entire safety gate:

1. Reads git status and diffs the candidate paths.
2. Verifies the task directory exists and changes are scoped.
3. Stages only non-generated files (`__pycache__/`, `.pyc`, `.pytest_cache/`, `.opencode/node_modules/` are excluded automatically).
4. Creates a conventional commit message with the task title and type prefix.
5. Records the commit result in the task's `checkpoint_commit` field and emits events.

No manual `git status` / `git diff` / `git add` inspection is needed. The script owns the entire safety gate. Just call `complete-verification` or `checkpoint-commit` and the script handles it.

### Commit rules

- Creates a local commit with a detailed conventional message (`feat:`/`fix:`/`chore:` prefix plus the task title); the message does not include `checkpoint`.
- Never pushes automatically.
- Multiple commits per task are supported — each clean verification checkpoint creates a new commit.

## Debugging and Lesson Capture

When execution involves repeated debugging (>=3 attempts, or non-obvious root cause involving tools, frameworks, or state):

1. After the fix passes verification, route through the lesson-capture gate in `just-demand-verification` before claiming completion.
2. Reusable patterns should become skills via the project-native `capture-lessons` skill. Project-local lessons should extend an existing Just Demand skill when they are broadly useful; otherwise keep them archived with the task.
3. Do not skip the capture gate just because the user already accepted the fix. If a reusable pattern was discovered, record it.

### Circuit Breaker

After a delegated result drifts:

1. Retry once only when one small missing fact can be supplied precisely.
2. On capability mismatch, poor quality, or a second drift, stop delegating that unit and let the main agent take over.
3. Reassess the requirement, context, boundaries, tests, and assumptions.
4. Use an advisor only if that new dispatch independently passes all nine checks.

## Task Archival Expectation

Completed and verified tasks should be archived to `tasks/archive/` rather than destructively deleted. Durable decisions and verified lessons must be extracted before the task leaves the active set. This preserves task-local evidence for future reference. Runtime archive-on-done is script-owned by `complete_verification(..., result="passed")`; use `archive-task` only for manual retry of completed active tasks.

## Required Context Files

- `just-demand-tester`: `context.md`, `verify.md`
- `just-demand-advisor`: `context.md`

Compatibility dispatch retains the historical requirements: coder uses `context.md` and `implement.md`; researcher uses `context.md`. New tasks do not require these roles or projections.

If required files are missing, stop and create or refresh the task context package first.
