---
name: using-agent-workflow
description: Use at the start of work in this repository, when asked about the agent workflow itself, or when unsure which workflow-* skill to load. Routes to the right workflow skill without injecting long rules every turn.
---

# Using Agent Workflow

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
- Scripts are the write path for `.agent-workflow/` machine state.
- OpenCode plugins should inject only lightweight state or subagent context.
- Long-context-consumption work belongs to subagents. The main agent should not perform broad code reading, large multi-file edits, or extended verification inline when a `workflow-*` subagent can do it from a formal task package.

## Skill Routing

| Situation | Load |
| --- | --- |
| User proposes or clarifies work before a formal task exists | `workflow-intake` |
| A formal work item is ready for execution or subagent dispatch | `workflow-execution` |
| Reporting completion, failed verification, or correction feedback | `workflow-verification` |
| Recording durable decisions, preferences, facts, open questions, or deferred options | `workflow-memory` |

## Runtime Boundaries

- Main-session plugins should not inject workflow text when there is no active unfinished formal task.
- Active unfinished tasks get only a short `<workflow-state>` breadcrumb.
- Task context is injected only for supported `workflow-*` subagents.
- Restart OpenCode after changing `.opencode/plugins/`, `.opencode/agent/`, `.opencode/skills/`, or `.opencode/package.json`.

## Commands

- Python tests: `python3 -m unittest tests.agent_workflow.test_workflow_core -v`
- OpenCode plugin tests: `node --test tests/agent_workflow/test_opencode_plugins.mjs`
- Package config check: `python3 -m json.tool .opencode/package.json`
