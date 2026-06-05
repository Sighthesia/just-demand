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

- Task 2026-05-30-align-workflow-implementation-with-design-philosophy-task (Align workflow implementation with design philosophy) completed with status 'done'.
  Verification summary: Phase 1 remediation passed: removed main-session bootstrap injection, aligned research permissions, and hardened missing-context blocking.

- Task 2026-05-30-broaden-subagent-permissions-by-responsibility-task (Broaden subagent permissions by responsibility) completed with status 'done'.
  Verification summary: Role-based subagent permissions and tool guidance verified; install and plugin tests passed

- Task 2026-05-31-work-item-task (主动偏差选项澄清) completed with status 'done'.
  Verification summary: 三个技能(socratic-clarification/just-demand-verification/just-demand-intake)在偏差与纠偏场景下改为 AI 主动两段式抛选项(维度定位+目标状态对比)为硬性默认,保留 free-text 逃逸口;未动脚本/插件/优先级路由;plugin 35 pass、install 32 ok;部署副本已同步

- Task 2026-05-31-bluf-task (最终报告 BLUF 优化) completed with status 'done'.
  Verification summary: just-demand-verification 的 Default Final Report 改为 BLUF 首句结论+极简要点+可选展开段,约300字默认目标,关键安全信息不因字数删除;Required Report 必报项改为一行/折叠呈现;plugin 35 pass、install 32 ok;部署副本已同步

- Task 2026-05-31-diff-task (脚本更新显示 diff 行数) completed with status 'done'.
  Verification summary: CLI 更新输出已显示按文件增删行统计，并且相关测试通过。

- Task 2026-06-02-zero-touch-bootstrap-and-half-migration-repair-task (Zero-touch bootstrap and half-migration repair) completed with status 'done'.
  Verification summary: Add where subcommand to task.py; print invocation hint after init (stdout) and after doctor (stderr to keep JSON clean); 5 new tests cover where / init-hint / doctor-hint / no-hint-when-uninitialized. workflow_core 68/68, install 32/32, package.json valid. in-flight 2026-05-23-fix-init-script-deployment-task verified untouched (task.json hash 3ea0d7e0a2c9cc553db1ae3f6a3b51ed3c068009 unchanged).

- Task 2026-06-04-add-workflow-guard-reminders-task (Add workflow guard reminders) completed with status 'done'.
  Verification summary: Workflow guard reminders verified with targeted plugin coverage.

- Task 2026-06-04-expand-workflow-guard-phrasing-coverage-task (Expand workflow guard phrasing coverage) completed with status 'done'.
  Verification summary: Expanded workflow guard tests with realistic phrasing coverage and minimal heuristic tweaks.

- Task 2026-06-04-expand-guard-false-positive-and-mixed-language-coverage-task (Expand guard false-positive and mixed-language coverage) completed with status 'done'.
  Verification summary: Added false-positive protection and English plus mixed-language guard coverage.

- Task 2026-06-04-expand-pure-chinese-and-near-miss-guard-coverage-task (Expand pure-Chinese and near-miss guard coverage) completed with status 'done'.
  Verification summary: Added pure-Chinese trigger coverage and near-miss false-positive protection for workflow guards.

- Task 2026-06-04-expand-adversarial-near-miss-guard-coverage-task (Expand adversarial near-miss guard coverage) completed with status 'done'.
  Verification summary: Added adversarial near-miss guard coverage and minimal false-positive suppression.

- Task 2026-06-04-expand-cross-sentence-near-miss-guard-coverage-task (Expand cross-sentence near-miss guard coverage) completed with status 'done'.
  Verification summary: Added cross-sentence near-miss guard coverage and minimal discourse-level suppression.

- Task 2026-06-04-tighten-verification-closeout-with-light-blocking-task (Tighten verification closeout with light blocking) completed with status 'done'.
  Verification summary: Added light verification closeout blocking for clear completion claims.

- Task 2026-06-05-tighten-execution-needed-with-light-blocking-task (Tighten execution-needed with light blocking) completed with status 'done'.
  Verification summary: Added light execution-needed blocking for clear inline execution claims.

- Task 2026-06-05-implement-minimal-phase-controller-task (Implement minimal phase controller) completed with status 'done'.
  Verification summary: Implemented explicit minimal controller decision layer in the state plugin; preserved blocker/reminder behavior and added controller-shape coverage in tests.


### From Task: 2026-06-05-design-minimal-phase-controller-task

## Baseline Recommendation

- Build from the workflow guard taxonomy assessment rather than re-deriving the architecture from scratch.

## Non-Goals

- Do not design a full orchestrator.
- Do not move lifecycle mutation authority into plugins.
- Do not discard existing guard/blocker behavior; explain how the controller subsumes or hosts it.

## Design Priorities

- Be concrete about controller responsibilities and boundaries.
- Make migration from the current runtime explicit.
- End with an implementation-ready next-step shape, not just conceptual framing.

- Task 2026-06-05-design-minimal-phase-controller-task (Design minimal phase controller) completed with status 'done'.
  Verification summary: Documented minimal phase controller design.


### From Task: 2026-06-05-document-workflow-guard-taxonomy-task

## Documentation Target

- Write the assessment as a formal design/spec document under `docs/superpowers/specs/` so future implementation work can cite it directly.

## Current Recommendation Direction

- Evaluate whether the current guard/blocker architecture is already sufficient for the present stage.
- Only recommend phase-based orchestration if the analysis shows the incremental blocker/guard model has become structurally hard to maintain.

## Output Priorities

- Be concrete about current layers.
- Be explicit about which rules should stay advisory versus which are candidates for formal phase gates.
- End with a clear recommendation and next-step path, not an open-ended discussion.

- Task 2026-06-05-document-workflow-guard-taxonomy-task (Document workflow guard taxonomy) completed with status 'done'.
  Verification summary: Documented workflow guard taxonomy and phase upgrade assessment.

- Task 2026-06-05-finalize-minimal-phase-controller-spec-checkpoint-task (Finalize minimal phase controller spec checkpoint) completed with status 'done'.
  Verification summary: Finalize minimal phase controller spec checkpoint.

- Task 2026-06-05-diagnose-unstable-workflow-prompt-injection-and-triggering-task (Diagnose unstable workflow prompt injection and triggering) completed with status 'done'.
  Verification summary: Add hard workflow-entry redirect for concrete work without an active task and cover it with plugin regression tests.
