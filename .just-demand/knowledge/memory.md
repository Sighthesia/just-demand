# Just Demand Memory

## Decisions

### D001: OpenCode-first local workflow

Type: architecture
Scope: workspace
Status: accepted
Date: 2026-05-20
Source Task: none
Supersedes: none

Decision:
Build the first version as an OpenCode-first local framework.

Reason:
The first version should prove the workflow loop before adding multi-platform abstraction, installer polish, or migration machinery.

### D002: Checkpoint commit policy

Type: workflow
Scope: workspace
Status: accepted
Date: 2026-05-22
Source Task: 2026-05-22-checkpoint-commit-after-clean-check-task
Supersedes: none

Decision:
A clean `just-demand-check` result (no findings or only fixed low-risk local issues) authorizes an automatic local checkpoint commit. Positive user acceptance remains a valid commit trigger but is secondary. Later corrections use follow-up commits for small fixes or revert commits for fundamentally wrong direction; do not rewrite history by default. Repeated unstable feedback pauses auto-commit until another clean check passes.

Reason:
This balances engineering closure with recoverability. Checkpoint commits after verification provide evidence of verified slices while allowing easy correction via follow-up or revert commits.

### From Task: 2026-05-22-global-just-demand-install-task

- Use global OpenCode installation for reusable runtime assets and explicit project-local initialization for `.just-demand` state.
- Keep plugin writes out of ordinary startup; scripts remain the write path for workflow state.
- First implementation should be local/in-repo CLI behavior, not package publication.

### From Task: 2026-05-23-integrate-agents-ref-rules-task

- Treat the reference as a durable workflow philosophy update, not a one-off task preference.
- Keep always-loaded text concise and move operational detail into targeted skills.

## Facts

- The initial workflow runtime targets OpenCode.
- The current design separates workspace intake from formal task lifecycle.
- Task 2026-05-22-global-just-demand-install-task (Global just-demand install) completed with status 'done'.
  Verification summary: Global OpenCode install and explicit project init implementation verified by Python and Node test suites.

- Task 2026-05-23-increase-clarification-proactiveness-task (Increase clarification proactiveness) completed with status 'done'.
  Verification summary: Prompt and runtime gates now prioritize blocking clarification before execution; Python and Node checks passed.

- Task 2026-05-23-integrate-agents-ref-rules-task (Integrate AGENTS_REF rules) completed with status 'done'.
  Verification summary: AGENTS_REF principles integrated into concise workflow docs and targeted skills; core/plugin checks passed; install suite has an unrelated pre-existing agent permission assertion failure.

- Task 2026-05-24-create-socratic-clarification-skill-task (Create Socratic clarification skill) completed with status 'done'.
  Verification summary: Standalone socratic-clarification skill added and routed from just-demand skills; tests and validation passed.

- Task 2026-05-24-harden-socratic-clarification-workflow-task (Harden Socratic clarification workflow) completed with status 'done'.
  Verification summary: Socratic clarification now uses a brainstorming-style hard gate with final artifact readiness; all Python, Node, config, and whitespace checks passed.

- Task 2026-05-24-increase-question-tool-driven-clarification-task (Increase question tool driven clarification) completed with status 'done'.
  Verification summary: Socratic clarification now prefers grouped question-tool decisions and approvals where feasible; workflow and plugin tests passed.

- Task 2026-05-27-work-item-task (调研其他工作流状态管理方法) completed with status 'done'.
  Verification summary: 调研完成，产出575行详细调研报告，包含5个工作流项目的状态管理方法对比分析

## Preferences

### P001: User-centered clarification

Scope: workspace
Status: accepted

Prefer requirement clarification that focuses on the user's described outcome, expected behavior, anti-outcomes, and tradeoffs. Avoid exposing task package, repo map, context injection, or subagent mechanics unless the user is explicitly designing those mechanisms.

## Deferred Options

### Deferred Option: Multi-platform protocol layer

Id: O001
Scope: workspace
Status: deferred
Chosen Instead: OpenCode-first local workflow
Reason: Validate the local workflow loop before abstracting platform adapters.
Risk: Later platform support will require an adapter layer.
Source Task: none
Revisit When:
- The OpenCode runtime is stable.
- The task package schema stops changing frequently.
- There is a concrete need for Claude, Codex, or another platform.

## Open Questions

No blocking workspace-level questions are open for the first implementation plan.

- Task 2026-05-28-just-demand-task (重构 .just-demand 目录结构) completed with status 'done'.
  Verification summary: 目录结构重构完成，所有测试通过
