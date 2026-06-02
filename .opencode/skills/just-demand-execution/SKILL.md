---
name: just-demand-execution
description: Use when a formal work item is ready to execute, when dispatching just-demand-research, just-demand-implement, just-demand-check, or just-demand-docs subagents, or when building context for focused execution.
---

# Workflow Execution

Execute formal work items through focused subagents and script-owned state.

## Core Rules

- Main agent coordinates; subagents execute focused work.
- Subagents do not inherit full chat history.
- Scripts are the only write path for workflow machine state under `.just-demand/`.
- Plugins and agents may read state, but lifecycle transitions must go through scripts.
- Do not dispatch implementation before the user has confirmed the direction and the task is ready.
- Long-context implementation, research, and verification must run through subagents. The main session should coordinate and summarize, not absorb the full execution context inline.
- Implementation or verification must not start unless the current formal task already has the required task context files. Do not treat missing task context as a recoverable inline shortcut.
- Before dispatching a subagent or starting implementation, mark the task status with `mark`.
- Before ending a turn with unfinished work, mark the task `paused` with current progress and known impact.

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

## Subagent Routing

- `just-demand-research`: research only; no code changes.
- `just-demand-implement`: scoped implementation; no commits.
- `just-demand-check`: verify requirements and fix only low-risk local issues within scope.
- `just-demand-docs`: update workflow docs and durable notes; no business-code changes.

## Task Marking Policy

Use `mark` for high-frequency, low-token state updates:

```text
python3 .just-demand/scripts/task.py --root . mark <task-id> <status> [--progress N] [--impact PATH] [--note TEXT]
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

## Dispatch Prompt

Start workflow subagent prompts with:

```text
Active task: <task-id>
```

This is a fallback for context injection failures.

## Progressive Clarification Routing

Before execution, if the active task still contains unresolved uncertainty about the user's intended effect, observed phenomenon, boundaries, or tradeoffs, load `socratic-clarification` and route back to clarification. Do not dispatch implementation while the final expected effect and final implementation plan are not explicit.

## Clarification Gate Before Execution

Before dispatching any implementation subagent, verify that the task is sufficiently clarified:

1. Check that `blocking_questions` in the task's clarification data is empty.
2. Check that `scope`, `expected_behavior`, and `actual_behavior` (for bug work) are non-empty.
3. For design and implementation tasks, check that `final_expected_effect`, `chosen_approach`, `final_implementation_plan`, and `approval` are non-empty.
4. If any blocking question remains or critical fields are empty, DO NOT dispatch. Route back to clarification instead: update the intake with the gaps and ask the user.
5. Do not guess what the user wants to fill in missing fields. Ask.
6. When clarifying gaps, prefer the `question` tool for grouped decisions, approvals, and boundary capture when the answer can be expressed as concise options.

### Visual Interaction Execution Gate

Before dispatching UI, animation, layout, reveal, overflow, clipping, or quality/feel work, check that the task context names the intended user-visible solution shape. If containment, synchronized entrance, and layout/reflow would feel different, the chosen approach must say which one is primary.

Do not dispatch implementation when the plan only says "fix overflow" or "clip it" but the user's feedback is about foreground/background timing, entrance choreography, layout feel, hard cuts, or visual quality. Route back to `socratic-clarification` and present the relevant options.

If clipping, masking, opacity, or delayed drawing is used only as a safety guardrail, record the primary behavior separately so subagents do not mistake the guardrail for the design.

## Execution Loop

1. Confirm active formal work item.
2. Run `python3 .just-demand/scripts/task.py --root . list-active` and inspect all unfinished tasks for conflict risk.
3. Ensure the current task package has the required files for the intended subagent.
4. Verify the clarification gate above passes. If not, route back to clarification.
5. Dispatch the narrowest suitable subagent. If the work would require substantial code reading, multi-file editing, or long verification output, do not keep it in the main session.
6. Review subagent output before moving to the next phase.
7. Run verification before claiming completion.

## Checkpoint Commit Policy

Every clean verification result should produce a checkpoint commit. The commit represents "this verified slice passed engineering checks", not permanent product finality. **Commits are the default, not the exception.** The script handles most of the work; the agent just needs to make sure the conditions are met and call the right command.

### Primary commit path: via `complete-verification`

When verification passes, the script-owned closure command creates the checkpoint commit automatically:

```text
python3 .just-demand/scripts/task.py --root . complete-verification <task-id> passed "<summary>"
```

That command records verification, runs the checkpoint-commit safety gate, and archives the task. Pass `--no-checkpoint-commit` only when the user explicitly asked to avoid committing.

### Standalone commit path: mid-task checkpoints

After any clean `just-demand-check` result, create a mid-task checkpoint without closing the task:

```text
python3 .just-demand/scripts/task.py --root . checkpoint-commit <task-id>
```

This is useful for:
- Long tasks with multiple independently verified slices.
- After fixing issues found by `just-demand-check` before moving to the next phase.
- Any time a safe, scoped commit would reduce risk.

### When to commit — proactively

Commit after **every** meaningful clean verification:

- After `just-demand-check` passes with no unresolved findings.
- After fixing low-risk local issues and re-verifying.
- After the user expresses positive acceptance (e.g., `effective`, `good`, `OK`, `LGTM`, `works`, `looks good`, `valid`, `不错`, `有效`, `可以`, `没问题`, `达成`, `就这样`).
- Before ending a multi-step implementation turn, even if the full task is not done yet.

Do not wait for perfect conditions. If the verified slice is clean, commit it.

### Impact scope recommendation (not a gate)

Setting `impact` via `mark --impact PATH` scopes the commit to only task-related files. If impact is not set, the script commits all non-generated changed files automatically. Impact scoping is **recommended** for precision but **not required** for the commit to proceed.

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

- Creates a local commit with a conventional message (`feat:`/`fix:`/`chore:` prefix matching task type).
- Never pushes automatically.
- Multiple commits per task are supported — each clean verification checkpoint creates a new commit.

## Debugging and Lesson Capture

When execution involves repeated debugging (>=3 attempts, or non-obvious root cause involving tools, frameworks, or state):

1. After the fix passes verification, route through the lesson-capture gate in `just-demand-verification` before claiming completion.
2. Reusable patterns should become skills via the global `capture-lessons` skill. Project-local lessons go to workspace memory. Task-only lessons go to task `decisions.md`.
3. Do not skip the capture gate just because the user already accepted the fix. If a reusable pattern was discovered, record it.

### Circuit Breaker

After two consecutive attempts fail to fix the same issue:

1. Stop modifying code directly.
2. Add necessary telemetry/logging to capture real context.
3. Reassess the requirement, context, boundaries, tests, and assumptions.
4. Escalate with options or use a subagent for independent analysis.

## Task Archival Expectation

Completed and verified tasks should be archived to `tasks/archive/` rather than destructively deleted. Durable decisions and verified lessons must be extracted before the task leaves the active set. This preserves task-local evidence for future reference. Runtime archive-on-done is script-owned by `complete_verification(..., result="passed")`; use `archive-task` only for manual retry of completed active tasks.

## Required Context Files

- `just-demand-implement`: `context.md`, `implement.md`
- `just-demand-check`: `context.md`, `verify.md`
- `just-demand-docs`: `context.md`, `decisions.md`
- `just-demand-research`: `context.md`

If required files are missing, stop and create or refresh the task context package first.
