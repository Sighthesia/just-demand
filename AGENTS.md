# Just Demand Repository Instructions

This repo is an OpenCode-first local agent workflow runtime: Python scripts own workflow state, OpenCode plugins inject lightweight context, and project skills hold the detailed workflow rules.

## Design Philosophy

- Keep the user focused on goals, constraints, preferences, and final decisions, not workflow mechanics.
- Use scripts for machine state, plugins for lightweight injection, and skills for detailed process rules.
- Share durable facts and decisions through files, not long chat history.
- Inject as little as possible into the main session: no active unfinished formal task means no workflow prompt injection.
- Inject rich context only for the subagent actively executing a formal task.
- Long-context-consumption work must be delegated to subagents. If a task needs broad code reading, multi-file implementation, extended verification, or any context that would bloat the main session, the main agent should shape and dispatch it instead of doing it inline.
- Before modifying code, or before dispatching any subagent that may modify or verify code, there must be a current formal task and its required task context files must already exist.
- Checkpoint commits are the default, not the exception. Every clean verified slice produces a local checkpoint commit via `complete-verification` or `checkpoint-commit`. Impact scoping is recommended but not required. Multiple commits per task are supported. Later corrections use follow-up or revert commits. Repeated unstable feedback pauses auto-commit until the next clean check passes. Non-trivial debugging triggers automatic lesson capture into skills. The user judges product-level quality; the agent handles engineering closure.

## Operating Principles

- **Role model**: The user is the product manager and chief architect; the agent is the chief execution engineer.
- **Priorities**: Business value over technical cleverness. Evidence over stale memory. Stability and maintainability over short-term speed.
- **Communication**: Be concise. Lead with the result. Ask implementation questions only when they affect product behavior, architecture, compatibility, security, cost, or long-term maintenance.
- **Quality**: Follow repo style. Separate tests from production code unless ecosystem convention says otherwise. Use comments only to explain non-obvious intent or tradeoffs.
- **Circuit breaker**: After two failed direct fixes, stop patching blindly. Add telemetry/logging if needed. Reassess requirements, context, boundaries, tests, and assumptions. Escalate options or use independent subagent analysis.

## Ideal Workflow

1. User proposes a goal or problem.
2. Main agent clarifies the need in user language and records durable decisions or deferred options when needed.
3. Once direction is confirmed, promote intake to a formal task package under `.just-demand/tasks/active/`.
4. Before execution, inspect all unfinished formal tasks to avoid cross-task conflicts.
5. Ensure the current task package has the required context files for the intended subagent.
6. Main agent dispatches focused `just-demand-*` subagents with injected task context. Long-context implementation, research, and verification should happen here, not inline in the main session.
7. `just-demand-check` verifies against the task brief and active validation revision before completion is claimed.
8. Main agent summarizes outcomes, remaining risks, and any durable memory updates.

## Commands

- Python workflow tests: `python3 -m unittest tests.just_demand.test_workflow_core -v`
- Python install tests: `python3 -m unittest tests.just_demand.test_install -v`
- OpenCode plugin tests: `node --test tests/just_demand/test_opencode_plugins.mjs`
- Validate OpenCode plugin package config: `python3 -m json.tool .opencode/package.json`
- CLI smoke test: `tmpdir=$(mktemp -d) && python3 .just-demand/scripts/task.py --root "$tmpdir" create-intake "Agent workflow" "Build workflow" --session session-main`
- Create intake manually: `python3 .just-demand/scripts/task.py --root . create-intake "<title>" "<raw request>" --session <session-id>`
- Promote intake manually: `python3 .just-demand/scripts/task.py --root . promote <intake-id> "<title>" "<goal>" --type design --acceptance "<criterion>"`
- List unfinished tasks: `python3 .just-demand/scripts/task.py --root . list-active`
- Mark task status/progress/impact: `python3 .just-demand/scripts/task.py --root . mark <task-id> <status> [--progress N] [--impact PATH] [--note TEXT]`
- Complete verification + checkpoint commit + archive: `python3 .just-demand/scripts/task.py --root . complete-verification <task-id> passed "<summary>"`
- Create standalone mid-task checkpoint commit: `python3 .just-demand/scripts/task.py --root . checkpoint-commit <task-id>`
- Archive completed task: `python3 .just-demand/scripts/task.py --root . archive-task <task-id>`
- Clean up completed task: `python3 .just-demand/scripts/task.py --root . cleanup-task <task-id>`

### Installation Commands

- Initialize project: `python3 .just-demand/scripts/task.py --root <project-root> init`
- Refresh local scripts in initialized workspaces: `python3 .just-demand/scripts/task.py sync-workspaces [--search-root <path>]`
- Install globally: `python3 .just-demand/scripts/task.py install --opencode --global [--config-root <path>]`
- Update global install: `python3 .just-demand/scripts/task.py update --opencode --global [--config-root <path>]`
- Check status: `python3 .just-demand/scripts/task.py --root <project-root> doctor [--config-root <path>]`
- Uninstall globally: `python3 .just-demand/scripts/task.py uninstall --opencode --global [--config-root <path>]`

Run Python and Node tests after changing `.just-demand/scripts/`, `.opencode/plugins/`, `.opencode/agent/`, or `.opencode/skills/`.

## Repository Structure

- `.just-demand/scripts/`: Python state-changing workflow core and CLI. This is the write path for workflow machine state.
- `.just-demand/workspace/`: runtime state (state.json, events.jsonl, locks.json, intake/, sessions/). Ignored by git.
- `.just-demand/knowledge/`: durable preferences, decisions, deferred options, facts, open questions. Version-controlled.
- `.just-demand/tasks/`: formal task packages under `active/` and archived work under `archive/`.
- `.opencode/plugins/`: OpenCode plugin adapters. These should read workflow state and mutate OpenCode messages/prompts only.
- `.opencode/agent/`: workflow subagent definitions.
- `.opencode/skills/`: on-demand workflow rules; keep detailed behavior here rather than injecting long prompts every turn.
- `tests/just_demand/`: Python and Node coverage for the workflow core and OpenCode plugins.
- `docs/superpowers/specs/` and `docs/superpowers/plans/`: design and implementation-plan history.

## Workflow State Rules

- Do not hand-edit `.just-demand/workspace/state.json`, `locks.json`, or event logs except through `.just-demand/scripts/` code.
- Main-session plugins should not inject anything when there is no active unfinished formal task.
- `just-demand-state.js` does not inject any `<workflow-state>` into main-session messages. Tasks should be inspected explicitly via list-active scripts.
- `just-demand-subagent-context.js` injects task context only when dispatching supported `just-demand-*` subagents.
- `just-demand-implement` requires `context.md` and `implement.md`; `just-demand-check` requires `context.md` and `verify.md`; `just-demand-docs` requires `context.md` and `decisions.md`; `just-demand-research` requires `context.md`.
- If required task context files are missing, implementation or verification must not proceed. The plugin intentionally injects a blocking notice instead of silent fallback.
- Before implementation or subagent dispatch, use `python3 .just-demand/scripts/task.py --root . list-active` to inspect all unfinished tasks and avoid cross-task conflicts.
- `just-demand-session-start.js` intentionally does not inject long bootstrap/rules text.
- Restart OpenCode after changing `.opencode/plugins/`, `.opencode/agent/`, `.opencode/skills/`, or `.opencode/package.json`.

## Project Skills

| Skill | Use when |
| --- | --- |
| `.opencode/skills/using-just-demand/SKILL.md` | Start here when working in this repo, when unsure which workflow skill applies, or when changing the workflow runtime itself. |
| `.opencode/skills/just-demand-intake/SKILL.md` | The user proposes or clarifies work before a formal task exists. |
| `.opencode/skills/just-demand-execution/SKILL.md` | A formal work item is ready to execute or workflow subagents are being dispatched. |
| `.opencode/skills/just-demand-verification/SKILL.md` | Reporting completion, handling failed verification, or processing user correction feedback. |
| `.opencode/skills/just-demand-memory/SKILL.md` | Recording durable decisions, preferences, facts, open questions, or deferred options. |
| Global `capture-lessons` (`.agents/skills/capture-lessons/SKILL.md`) | After non-trivial debugging (>=3 attempts, architectural traps, reusable methodology) to extract a pattern-based reusable skill. Used by just-demand-verification and just-demand-execution. |

## Subagent Boundaries

- `just-demand-research`: research only; `edit: deny`, `bash: deny`.
- `just-demand-implement`: scoped implementation only; no commits; do not modify `.just-demand/workspace/` except through designated workflow scripts.
- `just-demand-check`: verify against the task brief; may fix only low-risk local issues related to the current task.
- `just-demand-docs`: docs and durable notes only; no business-code changes; no commits.

Main-session rule: do not consume long implementation or verification context inline when a `just-demand-*` subagent can own it.

## OpenCode / Node Notes

- `.opencode/package.json` must remain valid JSON with `{ "type": "module" }`; otherwise Node refuses to load `.opencode/plugins/*.js`.
- There is no root `package.json`; run plugin tests directly with `node --test tests/just_demand/test_opencode_plugins.mjs`.

## Git Hygiene

- Do not commit generated `__pycache__/`, `.pyc`, `.pytest_cache/`, or `.opencode/node_modules/` changes.
- `.cocoindex_code/` is intentionally ignored.
