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

## Execution Loop

1. Confirm active formal work item.
2. Run `python3 .just-demand/scripts/task.py --root . list-active` and inspect all unfinished tasks for conflict risk.
3. Ensure the current task package has the required files for the intended subagent.
4. Dispatch the narrowest suitable subagent. If the work would require substantial code reading, multi-file editing, or long verification output, do not keep it in the main session.
5. Review subagent output before moving to the next phase.
6. Run verification before claiming completion.

## Checkpoint Commit Policy

A clean `just-demand-check` result (no findings or only fixed low-risk local issues) authorizes an automatic local checkpoint commit. The commit represents "this verified slice passed engineering checks", not permanent product finality. Positive user acceptance remains a valid commit trigger but is secondary.

### When to commit automatically

- After `just-demand-check` passes with no unresolved findings.
- After fixing low-risk local issues identified by `just-demand-check` and re-verifying.
- Positive user acceptance phrases (e.g., `effective`, `good`, `OK`, `LGTM`, `works`, `looks good`, `valid`, `不错`, `有效`, `可以`, `没问题`, `达成`, `就这样`) still authorize commit, but are not required.

Use the script-owned closure command for passed verification:

```text
python3 .just-demand/scripts/task.py --root . complete-verification <task-id> passed "<summary>"
```

That command records verification, runs the checkpoint-commit safety gate, and archives the task. Use `--no-checkpoint-commit` only when the user explicitly asked to avoid committing.

### Non-trigger cases

- The phrase occurs during planning or discussion, not after a change was made.
- The user explicitly says to avoid committing.
- The active task has no recent agent-made changes.
- Repeated unstable feedback or task in `debugging`/`tweaking` status (pause auto-commit until next clean check).

### Correction commits

- Small corrections: use follow-up commits on the same branch.
- Fundamentally wrong direction: use a revert commit.
- Do not rewrite history by default; prefer follow-up or revert commits.
- Repeated correction feedback/unstable task: mark task `debugging` or `tweaking` and pause automatic commits until another clean check passes.

### Pre-commit safety gate (mandatory)

Before staging or committing:

1. Run `git status`.
2. Inspect `git diff`.
3. Inspect recent commit style with `git log --oneline -10`.
4. Stage only files related to the active task.
5. Do not stage unrelated user changes, generated caches, `__pycache__/`, `.pyc`, `.pytest_cache/`, `.opencode/node_modules/`, secrets, or local-only artifacts.
6. Run relevant tests when feasible, or state why they were not run.

### Commit rules

- Create a local commit with a concise message matching repository style.
- Never push automatically.
- If boundaries are unclear, ask one short question instead of committing.
- If tests fail, do not commit unless the user explicitly overrides.
- Prefer multi-point commits for independently checked slices.

## Debugging and Lesson Capture

When execution involves repeated debugging (>=3 attempts, or non-obvious root cause involving tools, frameworks, or state):

1. After the fix passes verification, route through the lesson-capture gate in `just-demand-verification` before claiming completion.
2. Reusable patterns should become skills via the global `capture-lessons` skill. Project-local lessons go to workspace memory. Task-only lessons go to task `decisions.md`.
3. Do not skip the capture gate just because the user already accepted the fix. If a reusable pattern was discovered, record it.

## Task Archival Expectation

Completed and verified tasks should be archived to `tasks/archive/` rather than destructively deleted. Durable decisions and verified lessons must be extracted before the task leaves the active set. This preserves task-local evidence for future reference. Runtime archive-on-done is script-owned by `complete_verification(..., result="passed")`; use `archive-task` only for manual retry of completed active tasks.

## Required Context Files

- `just-demand-implement`: `context.md`, `implement.md`
- `just-demand-check`: `context.md`, `verify.md`
- `just-demand-docs`: `context.md`, `decisions.md`
- `just-demand-research`: `context.md`

If required files are missing, stop and create or refresh the task context package first.
