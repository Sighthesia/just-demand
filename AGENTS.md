# Just Demand

OpenCode-first local agent workflow runtime: Python scripts own workflow state, OpenCode plugins inject lightweight guardrails/context, and `.opencode/skills/` hold the detailed workflow rules.

## Workflow Model

- Treat this repo as a workflow runtime, not a normal app. The primary behavior is the lifecycle around `.just-demand/` state, plugin guardrails, and `just-demand-*` subagents.
- Working flow: clarify -> intake -> promote to formal task -> inspect unfinished tasks -> ensure required task context files exist -> dispatch `just-demand-*` subagent -> verify -> `complete-verification` -> checkpoint commit -> archive -> extract durable memory.
- Do not skip the clarification gate. In this repo, `using-just-demand` routes first and `socratic-clarification` is the hard gate before promotion, subagent dispatch, or code edits.
- Main-agent default: lead with the likely effect and the recommended option first, then ask only for the decision that would change visible behavior, architecture, compatibility, security, cost, or long-term maintainability.
- Long-context implementation, research, and verification belong in `just-demand-*` subagents, not inline in the main session.
- The user is the boss/product lead/architecture approver; the main agent owns workflow dispatch, verification, and closure.
- Subagent inner loops are execution contracts, not autonomous lifecycle owners: they may research, implement, verify, or advise within scope, but they do not create/promote/close tasks or dispatch other subagents.

## Skill-Only Fallback

- If OpenCode plugins are unavailable, disabled, or unstable, skill guidance is only best-effort; it cannot hard-block tools. Plugin gates remain the reliable enforcement layer.
- Even without plugin support, every repo-work turn must start by loading `using-just-demand` when workflow rules might apply.
- Any request, bug, correction, design/refactor, implementation approval, or Q&A-to-work pivot must then load `socratic-clarification` before intake, execution, or code edits.
- Treat user approval of an approach as approval to enter intake/formal task flow, not permission to edit inline unless formal execution readiness is satisfied.
- Post-approval/pre-promotion codebase investigation (inspecting, searching, reading, tracing, or investigating files for implementation) is also execution work and must wait for a formal task. In no-plugin fallback, this behavior is mandatory: do not read or inspect codebase files outside a formal task context.
- Before any write tool or execution subagent in no-plugin fallback mode, run `just-demand . list-active` and verify the required task context files exist.

## Source Of Truth

- Trust executable behavior over prose: the `just-demand` CLI, `.just-demand/scripts/workflow_core.py`, and `.opencode/plugins/*.js` are the real workflow spec.
- Do not hand-edit `.just-demand/state/state.json`, `locks.json`, or `events.jsonl`; change workflow state only through the `just-demand` CLI.
- Main-session plugins should stay lightweight. `just-demand-state.js` should not inject a task-state dump; task inspection is explicit via `list-active`.

## Required Commands

- Core tests: `python3 -m unittest tests.just_demand.test_workflow_core -v`
- Install tests: `python3 -m unittest tests.just_demand.test_install -v`
- Plugin tests: `node --test tests/just_demand/test_opencode_plugins.mjs`
- Validate Node package file: `python3 -m json.tool .opencode/package.json`
- List unfinished formal tasks before execution: `just-demand . list-active`
- Select or resume a task: `just-demand . select-task <task-id>` or `just-demand . resume <task-id>`
- Create intake: `just-demand . create-intake "<title>" "<raw request>" --session <session-id>`
- Promote intake: `just-demand . promote <intake-id> "<title>" "<goal>" --type design --acceptance "<criterion>"`
- Root help: `just-demand --help` or `just-demand . --help`
- Mark task status/progress/impact: `just-demand . mark <task-id> <status> [--progress N] [--impact PATH] [--note TEXT]`
- Close verified work: `just-demand . complete-verification <task-id> passed "<summary>"`
- Mid-task checkpoint: `just-demand . checkpoint-commit <task-id>`

## Command Order That Matters

- After changing `.just-demand/scripts/`, run both Python test modules.
- After changing `.opencode/plugins/`, `.opencode/agent/`, `.opencode/skills/`, or `.opencode/package.json`, run plugin tests and `python3 -m json.tool .opencode/package.json`, then restart OpenCode.
- Before any implementation or verification dispatch, run `list-active` to inspect unfinished tasks for conflict risk.
- `create-intake` only creates an intake. `list-active` stays empty until `promote` creates a formal task.
- Prompt-layer recovery details belong in `just-demand-intake` and `just-demand-execution`; keep AGENTS at the rule/command level.
- After `create-intake`, fill the created intake markdown at `.just-demand/state/intake/<intake-id>.md`; promotion is not the next legal step until the required sections are written there.
- If `promote` fails with missing-field or blocking-question errors, update the same intake file to fill the named sections, clear blocking questions, then rerun `just-demand . promote ...`; do not create a second intake just to recover.
- If `list-active` shows unfinished formal tasks but no current task is selected, recover by choosing the right task with `just-demand . select-task <task-id>` or `just-demand . resume <task-id>` before dispatch or inline edits.
- Do not report a task as complete until `complete-verification` has run. In this repo, verification closeout is a real workflow step, not wording.

## Task Context Rules

- Required files are enforced by plugin injection:
- `just-demand-coder`: `context.md`, `implement.md`
- `just-demand-tester`: `context.md`, `verify.md`
- `just-demand-researcher`: `context.md`
- `just-demand-advisor`: `context.md`
- If required files are missing, stop and create/refresh the task context package; do not silently continue inline.

## Repository Map

- `.just-demand/scripts/`: workflow CLI and state transitions; the only write path for workflow machine state.
- `.just-demand/knowledge/`: durable memory that survives tasks.
- `.just-demand/state/`: runtime state only; includes `intake/`, `active/`, `archive/`, event logs, and locks.
- `.opencode/plugins/`: OpenCode guardrails and task-context injection.
- `.opencode/agent/`: subagent definitions for `just-demand-*` roles.
- `.opencode/skills/`: detailed workflow policy; load these instead of duplicating long rules in chat.
- `tests/just_demand/`: Python coverage for workflow scripts plus Node coverage for plugins.

## Subagent Boundaries

- `just-demand-researcher`: research only; no code changes.
- `just-demand-coder`: scoped implementation only; no commits; do not mutate `.just-demand/state/` except through scripts.
- `just-demand-tester`: verify against the task brief; may fix only low-risk local issues.
- `just-demand-advisor`: independent analysis and advisory for difficult or cross-boundary problems; no direct large-scale implementation.
- Documentation, decisions, durable notes, and summaries are owned by the main agent or produced as part of a `coder`/`advisor` task. There is no standalone docs subagent.
- If a suitable `just-demand-*` subagent should be used but is unavailable, ask whether to retry now or skip one turn; do not quietly abandon the subagent path.

## Commit And Archive Expectations

- Checkpoint commits are the default after clean verification. Use `complete-verification` for the normal path; it records verification, attempts the checkpoint commit, and archives on pass.
- `impact` on `mark` is recommended because checkpoint commits can scope to task-related paths, but the script will fall back to all non-generated changed files when impact is absent.
- Completed tasks should be archived, not destructively removed first. Durable decisions/facts are extracted to `.just-demand/knowledge/memory.md` during archival.

## OpenCode / Node Gotchas

- There is no root `package.json`; plugin tests run directly with `node --test tests/just_demand/test_opencode_plugins.mjs`.
- `.opencode/package.json` must remain valid JSON and keep `{ "type": "module" }`, or Node will stop loading `.opencode/plugins/*.js`.

## Skills To Load

| Skill | Use when |
| --- | --- |
| `.opencode/skills/using-just-demand/SKILL.md` | First step for repo workflow turns or runtime changes. |
| `.opencode/skills/socratic-clarification/SKILL.md` | Any request, bug, correction, or mismatch before intake/execution. |
| `.opencode/skills/just-demand-intake/SKILL.md` | Shaping clarified work into a promotable intake/task. |
| `.opencode/skills/just-demand-execution/SKILL.md` | Dispatching subagents or executing a formal task. |
| `.opencode/skills/just-demand-verification/SKILL.md` | Completion claims, failed checks, or correction feedback. |
| `.opencode/skills/just-demand-memory/SKILL.md` | Recording durable decisions, facts, preferences, or deferred options. |
| `.agents/skills/capture-lessons/SKILL.md` | After non-trivial debugging produced a reusable pattern. |
