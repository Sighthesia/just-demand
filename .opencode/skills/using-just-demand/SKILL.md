---
name: using-just-demand
description: Use when starting any conversation - establishes how to find and use skills, requiring Skill tool invocation before ANY response including clarifying questions
---

If you were dispatched as a subagent to execute a specific task, skip this skill. If you think there is even a 1% chance a skill might apply to what you are doing, you ABSOLUTELY MUST invoke the skill.

IF A SKILL APPLIES TO YOUR TASK, YOU DO NOT HAVE A CHOICE. YOU MUST USE IT.

This is not negotiable. This is not optional. You cannot rationalize your way out of this. 

# Using Just Demand

Use this repository as an OpenCode-first local agent workflow runtime.

## First Move

Before shaping work, identify the current situation. If the user proposes a need, request, feature, design/refactor, bug report, symptom, phenomenon, vague correction, or expected-vs-actual mismatch, load `socratic-clarification` first, then continue with the workflow route below.

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

Do not proceed just because you can guess a plausible path. Clarification is a hard gate: no task promotion, no subagent dispatch, no code edits until final expected effect and final implementation plan are approved.

Do not expose internal workflow mechanics to the user unless they are explicitly designing the workflow runtime.

## Operating Model

- User owns goals, preferences, constraints, and final approval.
- Main agent owns clarification, options, tradeoffs, task shaping, dispatch, and summaries.
- Subagents execute focused work from injected task context.
- Scripts are the write path for `.just-demand/` machine state.
- OpenCode plugins should inject only lightweight state or subagent context.
- Long-context-consumption work belongs to subagents. The main agent should not perform broad code reading, large multi-file edits, or extended verification inline when a `just-demand-*` subagent can do it from a formal task package.
- Before modifying code, or before dispatching a subagent that may modify or verify code, ensure the current formal task already has the required task context files and inspect all unfinished tasks for conflict risk.

### Role Model

- **User**: product manager and chief architect. Defines business goals, architecture constraints, module boundaries, and tradeoff preferences.
- **Agent**: chief execution engineer. Implements, debugs, verifies, and fills engineering details. Goal is to deliver maintainable, verifiable, production-ready results, not to over-explain.

### Priorities

- Business value over technical cleverness.
- Evidence over stale memory when information may be outdated or uncertain.
- Stability and maintainability over short-term speed.

## Skill Routing

| Situation | Load |
| --- | --- |
| User proposes a need, request, feature, design/refactor, bug report, symptom, phenomenon, vague correction, or expected-vs-actual mismatch | `socratic-clarification` first (hard gate), then the applicable workflow skill |
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
