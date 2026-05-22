---
name: using-just-demand
description: Use at the start of work in this repository, when asked about the agent workflow itself, or when unsure which workflow-* skill to load. Routes to the right workflow skill without injecting long rules every turn.
---

# Using Just Demand

Use this repository as an OpenCode-first local agent workflow runtime.

## First Move

Before shaping work, identify the current situation:

```text
No active formal task -> use workflow-intake.
Formal task ready to execute -> use workflow-execution.
Implementation/check output needs verification -> use workflow-verification.
Durable preferences, decisions, facts, open questions, or deferred options appear -> use workflow-memory.
```

Do not expose internal workflow mechanics to the user unless they are explicitly designing the workflow runtime.

## Operating Model

- User owns goals, preferences, constraints, and final approval.
- Main agent owns clarification, options, tradeoffs, task shaping, dispatch, and summaries.
- Subagents execute focused work from injected task context.
- Scripts are the write path for `.just-demand/` machine state.
- OpenCode plugins should inject only lightweight state or subagent context.
- Long-context-consumption work belongs to subagents. The main agent should not perform broad code reading, large multi-file edits, or extended verification inline when a `workflow-*` subagent can do it from a formal task package.
- Before modifying code, or before dispatching a subagent that may modify or verify code, ensure the current formal task already has the required task context files and inspect all unfinished tasks for conflict risk.

## Skill Routing

| Situation | Load |
| --- | --- |
| User proposes or clarifies work before a formal task exists | `workflow-intake` |
| A formal work item is ready for execution or subagent dispatch | `workflow-execution` |
| Reporting completion, failed verification, or correction feedback | `workflow-verification` |
| Recording durable decisions, preferences, facts, open questions, or deferred options | `workflow-memory` |
| Non-trivial debugging produced a reusable pattern (>=3 attempts, architectural trap) | `capture-lessons` (global skill) via `workflow-verification` or `workflow-execution` |

## Runtime Boundaries

- Main-session plugins should not inject workflow text when there is no active unfinished formal task.
- Active unfinished tasks do not get a `<workflow-state>` breadcrumb in main-session messages. Tasks should be inspected explicitly via list-active scripts.
- Task context is injected only for supported `workflow-*` subagents.
- Execution must not start until the current task context files exist. Use `python3 .just-demand/scripts/task.py --root . list-active` to inspect unfinished tasks before dispatch.
- Restart OpenCode after changing `.opencode/plugins/`, `.opencode/agent/`, `.opencode/skills/`, or `.opencode/package.json`.

## Commands

- Python tests: `python3 -m unittest tests.just_demand.test_workflow_core -v`
- OpenCode plugin tests: `node --test tests/just_demand/test_opencode_plugins.mjs`
- Package config check: `python3 -m json.tool .opencode/package.json`
- List unfinished tasks: `python3 .just-demand/scripts/task.py --root . list-active`
