---
name: using-just-demand
description: Use at the start of work.
---

# Using Just Demand

Use this repository as an OpenCode-first local agent workflow runtime.

## First Move

Before shaping work, identify the current situation:

```text
No active formal task -> use just-demand-intake.
Formal task ready to execute -> use just-demand-execution.
Implementation/check output needs verification -> use just-demand-verification.
Durable preferences, decisions, facts, open questions, or deferred options appear -> use just-demand-memory.
```

Default to `just-demand-intake` before substantive execution when any of the following are true:

- the request is new and direction is still unclear
- the user reports a bug, regression, mismatch, or "expected X but got Y"
- the request could mean multiple scopes, outcomes, or tradeoffs
- correction feedback says the result drifted but does not yet pin down the desired behavior

Do not expose internal workflow mechanics to the user unless they are explicitly designing the workflow runtime.

## Operating Model

- User owns goals, preferences, constraints, and final approval.
- Main agent owns clarification, options, tradeoffs, task shaping, dispatch, and summaries.
- Subagents execute focused work from injected task context.
- Scripts are the write path for `.just-demand/` machine state.
- OpenCode plugins should inject only lightweight state or subagent context.
- Long-context-consumption work belongs to subagents. The main agent should not perform broad code reading, large multi-file edits, or extended verification inline when a `just-demand-*` subagent can do it from a formal task package.
- Before modifying code, or before dispatching a subagent that may modify or verify code, ensure the current formal task already has the required task context files and inspect all unfinished tasks for conflict risk.

## Skill Routing

| Situation | Load |
| --- | --- |
| User proposes or clarifies work before a formal task exists | `just-demand-intake` |
| User reports a bug, regression, vague failure, or expected-vs-actual mismatch before direction is fully clear | `just-demand-intake` |
| A formal work item is ready for execution or subagent dispatch | `just-demand-execution` |
| Reporting completion, failed verification, or correction feedback | `just-demand-verification` |
| Recording durable decisions, preferences, facts, open questions, or deferred options | `just-demand-memory` |
| Non-trivial debugging produced a reusable pattern (>=3 attempts, architectural trap) | `capture-lessons` (global skill) via `just-demand-verification` or `just-demand-execution` |

## Runtime Boundaries

- Main-session plugins should not inject workflow text when there is no active unfinished formal task.
- Active unfinished tasks do not get a `<workflow-state>` breadcrumb in main-session messages. Tasks should be inspected explicitly via list-active scripts.
- Task context is injected only for supported `just-demand-*` subagents.
- Execution must not start until the current task context files exist and the intake is actually ready. Promotion is blocked when required clarification fields are still missing or blocking questions remain. Use `python3 .just-demand/scripts/task.py --root . list-active` to inspect unfinished tasks before dispatch.
- Restart OpenCode after changing `.opencode/plugins/`, `.opencode/agent/`, `.opencode/skills/`, or `.opencode/package.json`.

## Commands

- Python tests: `python3 -m unittest tests.just_demand.test_workflow_core -v`
- OpenCode plugin tests: `node --test tests/just_demand/test_opencode_plugins.mjs`
- Package config check: `python3 -m json.tool .opencode/package.json`
- List unfinished tasks: `python3 .just-demand/scripts/task.py --root . list-active`
