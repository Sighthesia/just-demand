# Agent Workflow Repository Instructions

This repo is an OpenCode-first local agent workflow runtime: Python scripts own workflow state, OpenCode plugins inject lightweight context, and project skills hold the detailed workflow rules.

## Commands

- Python workflow tests: `python3 -m unittest tests.agent_workflow.test_workflow_core -v`
- OpenCode plugin tests: `node --test tests/agent_workflow/test_opencode_plugins.mjs`
- Validate OpenCode plugin package config: `python3 -m json.tool .opencode/package.json`
- CLI smoke test: `tmpdir=$(mktemp -d) && python3 .agent-workflow/scripts/task.py --root "$tmpdir" create-intake "Agent workflow" "Build workflow" --session session-main`
- Create intake manually: `python3 .agent-workflow/scripts/task.py --root . create-intake "<title>" "<raw request>" --session <session-id>`
- Promote intake manually: `python3 .agent-workflow/scripts/task.py --root . promote <intake-id> "<title>" "<goal>" --type design --acceptance "<criterion>"`

Run Python and Node tests after changing `.agent-workflow/scripts/`, `.opencode/plugins/`, `.opencode/agent/`, or `.opencode/skills/`.

## Repository Structure

- `.agent-workflow/scripts/`: Python state-changing workflow core and CLI. This is the write path for workflow machine state.
- `.agent-workflow/workspace/`: durable preferences, decisions, deferred options, facts, open questions, state, events, and locks.
- `.agent-workflow/tasks/`: formal task packages under `active/` and archived work under `archive/`.
- `.opencode/plugins/`: OpenCode plugin adapters. These should read workflow state and mutate OpenCode messages/prompts only.
- `.opencode/agent/`: workflow subagent definitions.
- `.opencode/skills/`: on-demand workflow rules; keep detailed behavior here rather than injecting long prompts every turn.
- `tests/agent_workflow/`: Python and Node coverage for the workflow core and OpenCode plugins.
- `docs/superpowers/specs/` and `docs/superpowers/plans/`: design and implementation-plan history.

## Workflow State Rules

- Do not hand-edit `.agent-workflow/workspace/state.json`, `locks.json`, or event logs except through `.agent-workflow/scripts/` code.
- Main-session plugins should not inject anything when there is no active unfinished formal task.
- `agent-workflow-state.js` injects only a short `<workflow-state>` for active tasks whose status is not `done`.
- `agent-workflow-subagent-context.js` injects task context only when dispatching supported `workflow-*` subagents.
- `agent-workflow-session-start.js` intentionally does not inject long bootstrap/rules text.
- Restart OpenCode after changing `.opencode/plugins/`, `.opencode/agent/`, `.opencode/skills/`, or `.opencode/package.json`.

## Project Skills

| Skill | Use when |
| --- | --- |
| `.opencode/skills/using-agent-workflow/SKILL.md` | Start here when working in this repo, when unsure which workflow skill applies, or when changing the workflow runtime itself. |
| `.opencode/skills/workflow-intake/SKILL.md` | The user proposes or clarifies work before a formal task exists. |
| `.opencode/skills/workflow-execution/SKILL.md` | A formal work item is ready to execute or workflow subagents are being dispatched. |
| `.opencode/skills/workflow-verification/SKILL.md` | Reporting completion, handling failed verification, or processing user correction feedback. |
| `.opencode/skills/workflow-memory/SKILL.md` | Recording durable decisions, preferences, facts, open questions, or deferred options. |

## Subagent Boundaries

- `workflow-research`: research only; `edit: deny`, `bash: deny`.
- `workflow-implement`: scoped implementation only; no commits; do not modify `.agent-workflow/workspace/` except through designated workflow scripts.
- `workflow-check`: verify against the task brief; may fix only low-risk local issues related to the current task.
- `workflow-docs`: docs and durable notes only; no business-code changes; no commits.

## OpenCode / Node Notes

- `.opencode/package.json` must remain valid JSON with `{ "type": "module" }`; otherwise Node refuses to load `.opencode/plugins/*.js`.
- There is no root `package.json`; run plugin tests directly with `node --test tests/agent_workflow/test_opencode_plugins.mjs`.

## Git Hygiene

- Do not commit generated `__pycache__/`, `.pyc`, `.pytest_cache/`, or `.opencode/node_modules/` changes.
- `.cocoindex_code/` is intentionally ignored.
