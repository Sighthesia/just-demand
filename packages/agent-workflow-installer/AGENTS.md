# Just Demand Repository Instructions

This package is a Just Demand workspace installer: the `just-demand` CLI seeds workspace metadata and OpenCode assets, while the runtime state remains local to the target project.

## Design Philosophy

- Keep the user focused on goals, constraints, preferences, and final decisions, not workflow mechanics.
- Use the `just-demand` CLI for workspace setup, plugins for lightweight injection, and skills for detailed process rules.
- Share durable facts and decisions through files, not long chat history.
- Inject as little as possible into the main session: no active unfinished formal task means no workflow prompt injection.
- Inject rich context only for the subagent actively executing a formal task.
- Long-context-consumption work must be delegated to subagents. If a task needs broad code reading, multi-file implementation, extended verification, or any context that would bloat the main session, the main agent should shape and dispatch it instead of doing it inline.
- Before modifying code, or before dispatching any subagent that may modify or verify code, there must be a current formal task and its required task context files must already exist.
- Invisible closure: completed verified tasks should be archived, not left active. Positive user acceptance after a change authorizes a safe local commit (status/diff/log check, scoped staging, no auto-push). Non-trivial debugging triggers automatic lesson capture into skills. The user judges product-level quality; the agent handles engineering closure.

## Ideal Workflow

1. User proposes a goal or problem.
2. Main agent clarifies the need in user language and records durable decisions or deferred options when needed.
3. Once direction is confirmed, promote intake to a formal task package under `.just-demand/state/active/`.
4. Before execution, inspect all unfinished formal tasks to avoid cross-task conflicts.
5. Ensure the current task package has the required context files for the intended subagent.
6. Main agent dispatches focused `just-demand-*` subagents with injected task context. Long-context implementation, research, and verification should happen here, not inline in the main session.
7. `just-demand-check` verifies against the task brief and active validation revision before completion is claimed.
8. Main agent summarizes outcomes, remaining risks, and any durable memory updates.

## Commands

- Python workflow tests: `python3 -m unittest tests.just_demand.test_workflow_core -v`
- OpenCode plugin tests: `node --test tests/just_demand/test_opencode_plugins.mjs`
- Validate OpenCode plugin package config: `python3 -m json.tool .opencode/package.json`
- CLI smoke test: `tmpdir=$(mktemp -d) && just-demand --root "$tmpdir" create-intake "Agent workflow" "Build workflow" --session session-main`
- Create intake manually: `just-demand --root . create-intake "<title>" "<raw request>" --session <session-id>`
- Promote intake manually: `just-demand --root . promote <intake-id> "<title>" "<goal>" --type design --acceptance "<criterion>"`
- List unfinished tasks: `just-demand --root . list-active`
- Mark task status/progress/impact: `just-demand --root . mark <task-id> <status> [--progress N] [--impact PATH] [--note TEXT]`
- Archive completed task: `just-demand --root . archive-task <task-id>`
- Clean up completed task: `just-demand --root . cleanup-task <task-id>`

Run Python and Node tests after changing `.just-demand/scripts/`, `.opencode/plugins/`, `.opencode/agent/`, or `.opencode/skills/`.

## Repository Structure

- `.just-demand/scripts/`: Python workflow core used by the global CLI.
- `.just-demand/state/`: runtime state, task packages, events, and locks.
- `.just-demand/knowledge/`: durable memory that survives tasks.
- `.opencode/plugins/`: OpenCode plugin adapters. These should read workflow state and mutate OpenCode messages/prompts only.
- `.opencode/agent/`: workflow subagent definitions.
- `.opencode/skills/`: on-demand workflow rules; keep detailed behavior here rather than injecting long prompts every turn.
- `tests/just_demand/`: Python and Node coverage for the workflow core and OpenCode plugins.
- `docs/superpowers/specs/` and `docs/superpowers/plans/`: design and implementation-plan history.

## Workflow State Rules

- Do not hand-edit `.just-demand/state/state.json`, `locks.json`, or event logs except through the `just-demand` CLI.
- Main-session plugins should not inject anything when there is no active unfinished formal task.
- `just-demand-state.js` does not inject any `<workflow-state>` into main-session messages. Tasks should be inspected explicitly via `list-active`.
- `just-demand-subagent-context.js` injects task context only when dispatching supported `just-demand-*` subagents.
- `just-demand-implement` requires `context.md` and `implement.md`; `just-demand-check` requires `context.md` and `verify.md`; `just-demand-docs` requires `context.md` and `decisions.md`; `just-demand-research` requires `context.md`.
- If required task context files are missing, implementation or verification must not proceed. The plugin intentionally injects a blocking notice instead of silent fallback.
- Before implementation or subagent dispatch, use `just-demand --root . list-active` to inspect all unfinished tasks and avoid cross-task conflicts.
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

## Subagent Boundaries

- `just-demand-research`: research only; `edit: deny`, `bash: deny`.
- `just-demand-implement`: scoped implementation only; no commits; do not modify `.just-demand/state/` except through the `just-demand` CLI.
- `just-demand-check`: verify against the task brief; may fix only low-risk local issues related to the current task.
- `just-demand-docs`: docs and durable notes only; no business-code changes; no commits.

Main-session rule: do not consume long implementation or verification context inline when a `just-demand-*` subagent can own it.

## OpenCode / Node Notes

- `.opencode/package.json` must remain valid JSON with `{ "type": "module" }`; otherwise Node refuses to load `.opencode/plugins/*.js`.
- There is no root `package.json`; run plugin tests directly with `node --test tests/just_demand/test_opencode_plugins.mjs`.

## Git Hygiene

- Do not commit generated `__pycache__/`, `.pyc`, `.pytest_cache/`, or `.opencode/node_modules/` changes.
- `.cocoindex_code/` is intentionally ignored.
