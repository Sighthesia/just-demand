# Just Demand Memory

## Decisions

### D003: Duplicate critical gates across same-hook plugins

Type: workflow-runtime
Scope: workspace
Status: accepted
Date: 2026-06-08
Source Task: 2026-05-24-raise-socratic-clarification-priority-task
Supersedes: none

Decision:
Critical `tool.execute.before` enforcement must not assume every plugin registering the same hook will run in real OpenCode sessions. If another plugin on the same hook can be the only effective runtime path, the hard gate must be shared and called from that plugin before any local skip logic.

Reason:
Real debug logs showed only `just-demand-subagent-context` events for non-Task tools while `just-demand-state` gate events were absent. Duplicating the shared execution gate into the subagent-context hook prevents inline `apply_patch`, write-like `bash`, or gated workflow `Task` dispatch from bypassing formal task requirements when same-hook plugin behavior differs from isolated unit tests.

### D004: Reinforce workflow through visible routing, not hidden authority

Type: workflow-runtime
Scope: workspace
Status: accepted
Date: 2026-06-22
Source Task: 2026-06-22-analyze-stronger-workflow-rule-injection-and-reinforcement-task
Supersedes: none

Decision:
Harden workflow discipline by layering visible runtime routing and narrow execution gates before introducing any session-owned authority model. Prefer unconditional `workflow-state` injection, explicit workflow-skip override phrases, mandatory subagent routing for long-context execution, action-type classification (`workflow-control`, `dispatch`, `execution-write`), and lightweight subagent output contracts. Do not use execution lease as the default authority model.

Reason:
Testing showed execution-lease style authority causes serious session conflict and friction. The higher-value fixes came from making workflow identity visible every turn, making inline bypass explicit, separating control-plane actions from real execution writes, and stabilizing subagent outputs.

### D005: Do not persist weak workflow state unless it has clear continuity value and zero authority impact

Type: workflow-runtime
Scope: workspace
Status: accepted
Date: 2026-06-22
Source Task: 2026-06-22-analyze-weak-workflow-state-persistence-task
Supersedes: none

Decision:
Do not add weak workflow state persistence by default. Process-local reminder dedupe, topic counters, and subagent-unavailable prompts should remain ephemeral unless a future continuity problem justifies persistence. Any future persistence must stay continuity-only and must not become hidden execution authority, locking, or coordination state.

Reason:
After workflow-state injection, false-positive reduction, mandatory long-context subagent routing, and minimal subagent output contracts, the remaining ephemeral state has low recovery cost and low user impact. Persisting it now would add complexity and risk recreating authority-like conflicts for little benefit.

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

- Task 2026-05-23-fix-init-script-deployment-task (Fix init script deployment) completed with status 'done'.
  Verification summary: Switched project init to local-state-only architecture and removed workspace script copies

- Task 2026-06-06-global-cli-only-workflow-entry-task (Global CLI only workflow entry) completed with status 'done'.
  Verification summary: Removed sync-workspaces, pruned stale workflow manifest entries, and verified install/workflow/plugin test suites pass.

- Task 2026-06-06-remove-root-flag-from-cli-task (Remove root flag from CLI) completed with status 'done'.
  Verification summary: CLI now uses optional leading project-dir positional argument; --root removed; docs, plugins, and tests updated.

- Task 2026-06-07-add-runtime-workflow-gate-task (Add runtime workflow gate) completed with status 'done'.
  Verification summary: Runtime now blocks concrete requests without an active task and redirects them to workflow entry; skill text now says routing guidance is not enforcement.

- Task 2026-06-07-harden-workflow-safety-first-batch-task (Harden workflow safety first batch) completed with status 'done'.
  Verification summary: First-batch workflow safety hardening implemented; workflow core tests 71/71 and plugin tests 60/60 passed.

- Task 2026-06-07-add-workflow-state-locks-task (Add workflow state locks) completed with status 'done'.
  Verification summary: Second-batch workflow reliability hardening implemented; workflow core tests 73/73 and plugin tests 60/60 passed.

- Task 2026-05-24-raise-socratic-clarification-priority-task (Raise socratic clarification priority) completed with status 'done'.
  Verification summary: Shared execution gate now runs from both state and subagent-context hooks, Chinese workflow-entry routing is covered, chat.message skip path is safe, and install/plugin verification passed.

- Task 2026-06-08-strengthen-skill-only-workflow-fallback-task (Strengthen skill-only workflow fallback) completed with status 'done'.
  Verification summary: Skill-only fallback guidance now mirrors Superpowers-style bootstrap discipline: using-just-demand first, socratic-clarification second, approach approval enters task flow rather than inline editing, no-plugin writes require list-active/context checks, and guidance clearly states skills are best-effort while plugins remain hard enforcement. Plugin tests 64/64, install tests 37/37, package JSON valid.

- Task 2026-06-08-optimize-subagent-task-context-task (Optimize subagent task context) completed with status 'done'.
  Verification summary: Optimized subagent context injection to compact execution context and verified plugin tests plus package JSON.

- Task 2026-06-08-fix-workflow-entry-and-cli-consistency-task (Fix workflow entry and CLI consistency) completed with status 'done'.
  Verification summary: Fixed CLI/help project-dir consistency, workflow-entry narration false blocks, and create-intake vs promote verification guidance; core/install/plugin tests passed.

- Task 2026-06-08-fix-quoted-redirect-false-positive-in-workflow-guard-task (Fix quoted redirect false positive in workflow guard) completed with status 'done'.
  Verification summary: Fixed bash guard false positive for quoted greater-than text in workflow-entry commands; plugin and workflow-core tests passed.

- Task 2026-06-08-improve-task-selection-and-gate-messaging-task (Improve task selection and gate messaging) completed with status 'done'.
  Verification summary: Added explicit task selection and resume commands, clarified execution-gate errors, and switched missing-current-task chat behavior to reminder-first; workflow-core and plugin tests passed.

- Task 2026-06-09-fill-workflow-prompt-handling-gaps-task (Fill workflow prompt handling gaps) completed with status 'done'.
  Verification summary: Added prompt-layer guidance for intake completion, promote retry recovery, and current-task selection fallback; plugin tests and package validation passed.

- Task 2026-06-09-reduce-workflow-clarification-cognitive-load-task (Reduce workflow clarification cognitive load) completed with status 'done'.
  Verification summary: Low-reading-cost clarification artifacts implemented and verified: decision cards, MVK, validation cards, diagrams, template parsing, and tests.

- Task 2026-06-09-implement-user-facing-output-contract-task (Implement user-facing output contract) completed with status 'done'.
  Verification summary: User-facing output contract implemented and verified with workflow core, install, plugin, and package JSON checks.

- Task 2026-06-16-add-cli-next-action-hints-task (Add CLI next-action hints) completed with status 'done'.
  Verification summary: Added structured next_actions to promote/select/resume CLI outputs, clarified long-context work in the session reminder, fixed package.json merge preservation, and verified workflow_core/install/plugin tests plus package JSON.

- Task 2026-06-02-enhance-visual-interaction-workflow-prompts-task (Enhance visual interaction workflow prompts) completed with status 'done'.
  Verification summary: Visible-effect approval card guidance added for UI/layout/animation workflow outputs; plugin tests, package JSON validation, and diff whitespace checks passed

- Task 2026-06-16-generalize-diagram-approval-cards-task (Generalize diagram approval cards) completed with status 'done'.
  Verification summary: Diagram-intent approval card guidance added for flowcharts, architecture diagrams, state diagrams, and data-flow/API diagrams; plugin tests, package JSON validation, and diff whitespace checks passed

- Task 2026-06-09-analyze-workflow-prompt-completeness-task (Analyze workflow prompt completeness) completed with status 'done'.
  Verification summary: Research identified a post-approval code-investigation gap when plugin guardrails are degraded and recommended minimal prompt-layer plus plugin-layer fixes.

- Task 2026-06-18-close-post-approval-workflow-drift-gap-task (Close post-approval workflow drift gap) completed with status 'done'.
  Verification summary: Post-approval code-investigation drift guard implemented and verified: prompt fallback now treats codebase investigation as execution work before promotion; state plugin blocks English/Chinese code-investigation intent without a formal task; plugin tests 80/80 and package JSON validation passed.

- Task 2026-06-22-analyze-stronger-workflow-rule-injection-and-reinforcement-task (Analyze stronger workflow rule injection and reinforcement) completed with status 'done'.
  Verification summary: Repository-grounded comparison completed: identified workflow-state injection, explicit override routing, mandatory subagent dispatch, and output contracts as the strongest improvements for just-demand.

- Task 2026-06-22-implement-workflow-reinforcement-core-skeleton-task (Implement workflow reinforcement core skeleton) completed with status 'done'.
  Verification summary: Implemented first-batch workflow reinforcement: unconditional workflow-state injection, explicit workflow-skip override, and stronger no-task routing with plugin tests passing.

- Task 2026-06-22-implement-workflow-gate-false-positive-reduction-batch-task (Implement workflow gate false-positive reduction batch) completed with status 'done'.
  Verification summary: Reduced gate false positives by classifying workflow-control, dispatch, and execution-write behavior and narrowing conflict handling toward impact overlap; tests passed.

- Task 2026-06-22-implement-mandatory-subagent-dispatch-for-long-context-execution-task (Implement mandatory subagent dispatch for long-context execution) completed with status 'done'.
  Verification summary: Main-session long-context execution now routes toward just-demand subagents by default while preserving workflow-control, dispatch, and explicit override paths; tests passed.

- Task 2026-06-22-implement-minimal-subagent-output-contracts-task (Implement minimal subagent output contracts) completed with status 'done'.
  Verification summary: Added lightweight output contracts for just-demand research, implement, and check subagents; install, plugin, and core tests passed.

- Task 2026-06-22-analyze-weak-workflow-state-persistence-task (Analyze weak workflow state persistence) completed with status 'done'.
  Verification summary: Read-only evaluation concluded weak workflow state persistence is not worth adding now; continuity-only state remains lower value than its added complexity and authority risk.

- Task 2026-06-22-redesign-agent-team-roles-task (Redesign agent team roles) completed with status 'done'.
  Verification summary: Team-style agent role redesign verified: active roles are researcher/coder/tester/advisor, docs role removed from active surface, advisor added as fresh-context advisory helper, plugin/install/workflow tests passed.

- Task 2026-06-22-add-agent-inner-loop-contracts-task (Add agent inner-loop contracts) completed with status 'done'.
  Verification summary: Agent inner-loop contracts verified: all four active agent prompts define role-specific mission, inputs, workflow loop, boundaries, output contract, and escalation rules; execution and verification guidance align; install/plugin/package checks passed.

- Task 2026-06-22-audit-workflow-boss-pm-experience-task (Audit workflow boss-PM experience) completed with status 'done'.
  Verification summary: Boss/PM workflow experience audit and prompt alignment verified: prompts now emphasize user-visible effects, proactive defaults/options, low user burden, and main-agent coordination of the subagent team; plugin and package checks passed.

- Task 2026-06-23-document-just-demand-workflow-philosophy-task (Document Just Demand workflow philosophy) completed with status 'done'.
  Verification summary: README.md and AGENTS.md now contain the same comprehensive Just Demand Workflow Philosophy section covering lifecycle, identities, skills/plugins/CLI layers, main-agent identity sources, subagent inner loops, and output principles; documentation verification passed.

- Task 2026-06-23-expand-readme-workflow-positioning-task (Expand README workflow positioning) completed with status 'done'.
  Verification summary: README.md expanded for workflow evaluators and custom agent workflow builders with pain-point analysis, communication/dispatch diagrams, responsibility tables, comparisons, and design lessons; README markdown check passed; unrelated pre-existing working-tree changes remain.
