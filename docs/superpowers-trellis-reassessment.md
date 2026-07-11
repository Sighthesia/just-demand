# Just Demand Design Reassessment

Date: 2026-07-11

References:

- `/home/Sighthesia/0_Files/Producing/Software/Workflows/superpowers`
- `/home/Sighthesia/0_Files/Producing/Software/Workflows/Trellis`
- `/home/Sighthesia/0_Files/Producing/Software/Workflows/just-demand`

## Executive Conclusion

Just Demand should remain a durable workflow runtime, not become another prompt-only skill bundle. Its target architecture should be:

```text
durable workflow kernel
  + OpenCode adapter
  + role-specific agent contracts
```

The strongest current mechanisms are the Python lifecycle, explicit verification closeout, checkpoint commits, reflection routing, and four-role agent model. The main weaknesses are authority drift between repository and globally installed plugins, heuristic natural-language gates carrying too much control responsibility, repeated policy across skills, workspace-global task selection, an active-task set that has become operationally noisy, and the absence of any durable cross-stage memory for multi-task roadmaps and user suggestions.

The first priority is to make the existing runtime reproducible and structurally trustworthy, and to establish a plan-ledger layer so the system can retain and surface multi-stage intent without relying on user memory.

## Corrected Baseline

Three initial observations required correction during review:

1. Just Demand does have four active global plugins under `/home/Sighthesia/.config/opencode/plugins/`; the repository `.opencode/plugins/` directory was **intentionally removed** on the `refactor-opencode-plugin` branch (commit `fccb676`), not accidentally lost. The main branch retains the historical originals. The removal was deliberate: the old plugins contained overly strict natural-language gates (regex-based lifecycle inference, model-authored workflow-skip authorization), confusing multi-layer context injection, and complex classification logic that produced fragile behavior. The assessment does **not** propose restoring those files. Instead, it defines a cleaner plugin boundary below.
2. `just-demand . list-active` currently reports 23 unfinished formal tasks, not 36.
3. The intake template has 28 headings, but a design task does not require all 28. Promotion requires `Scope`, `Final Expected Effect`, `Chosen Approach`, `Final Implementation Plan`, `Approval`, and no blocking questions.

### Branch Facts

| Branch | `.opencode/plugins/` state | Intent |
| --- | --- | --- |
| `main` | Contains four historical plugin files | Stable baseline before refactoring |
| `refactor-opencode-plugin` (current) | Deleted — commit `fccb676` removed all four files | **Intentional removal** of overly strict gates and confusing injection; this branch is the refactoring workspace |

The current branch is named for this purpose: `refactor-opencode-plugin`. Test failures against the missing repository source are expected during the refactoring phase and will be resolved when a new, cleaner plugin layer replaces the old one — not by reverting the deletion.

Evidence:

- Intentional removal commit: `git log --oneline refactor-opencode-plugin` shows `fccb676 refactor: remove opencode plugin files`.
- Plugin deployment manifest: `.just-demand/scripts/install.py:22-47`.
- Installer source directory: `.just-demand/scripts/install.py:416-451`.
- Tests import repository plugin sources: `tests/just_demand/test_opencode_plugins.mjs:42-53`.
- Intake headings: `.just-demand/scripts/workflow_core.py:286-315`.
- Promotion gates: `.just-demand/scripts/workflow_core.py:512-562`.
- Unfinished-task enumeration: `.just-demand/scripts/workflow_core.py:1525`.

## Mechanism Matrix

| Dimension | Just Demand | Superpowers | Trellis |
| --- | --- | --- | --- |
| Product shape | Durable workflow runtime | Prompt and skill discipline | Task/spec workflow framework |
| Agents | Four explicit roles: researcher, coder, tester, advisor | No OpenCode agent definitions; skills dispatch general subagents | Three roles: research, implement, check |
| Skills | Phase-oriented workflow skills with substantial repeated policy | One bootstrap skill routes to many technique skills | Workflow, task, spec, recovery, and collaboration skills |
| Bootstrap | Global system reminder plus workflow-state injection | One plugin injects `using-superpowers` into the first message | Session-start plus workflow-state injection |
| Runtime gates | CLI promotion gates plus plugin tool gates and language heuristics | Prompt discipline only | Task readiness plus plugin context routing |
| Task state | JSON lifecycle, events, locks, archive, checkpoint closeout | None | Per-task artifacts plus session runtime context |
| Subagent context | Role-specific context files injected before Task dispatch | Prompt templates inside skills | Task artifacts and selected JSONL context injected before dispatch |
| Cross-stage memory | **None currently** — each task starts fresh | None | None |
| Recovery | Select/resume, reflection, verification loop, archive | No durable recovery model | Session-scoped task resolution and explicit continue/finish commands |
| Main tradeoff | Strong control, high policy and state overhead | Low overhead, weak durability | Strong context routing, more framework surface |

## Agents

### Retain

Retain the four roles. The separation matches Just Demand's lifecycle better than either reference project:

- Researcher owns evidence gathering.
- Advisor owns interpretation, reframing, and cross-boundary decisions.
- Coder owns scoped implementation.
- Tester owns verification and only low-risk local repair.

The critical clarification is that researcher output is factual and advisor output is judgment. Their current overlap in option comparison should be removed. Tester reports should also separate verification evidence from any fixes it applies.

Global agent evidence is under `/home/Sighthesia/.config/opencode/agents/just-demand-{researcher,coder,tester,advisor}.md:16`.

### Do Not Copy

Do not copy Superpowers' fixed implementer plus multiple reviewer sequence for every subtask. It is useful for a stable, decomposed implementation plan, but it imposes too much dispatch and review overhead as a universal path. See `superpowers/skills/subagent-driven-development/SKILL.md:8-14`.

## Skills

### Current Problem

The phase names are reasonable, but policy ownership is not. `using-just-demand`, `socratic-clarification`, intake, execution, and verification repeatedly restate routing order, approval semantics, active-task checks, subagent failure handling, and closeout rules. This consumes prompt budget and creates drift between the canonical spec, AGENTS, skills, plugins, and CLI.

The intake skill also treats a rich presentation format as if it were the task data model. Runtime promotion is much smaller than the recommended artifact surface. The mismatch was visible during this audit: the intake template uses `Anti-Outcome`, while runtime context expects `Anti-Outcomes`, so the approved exclusion was omitted until explicitly repaired with `update-clarification`.

Evidence:

- Intake artifact requirements: `.opencode/skills/just-demand-intake/SKILL.md:44` in the installed/source skill tree.
- Runtime markdown mapping: `.just-demand/scripts/workflow_core.py:435-464`.
- Template heading: `.just-demand/scripts/workflow_core.py:294`.
- Runtime mapping expects plural `Anti-Outcomes`: `.just-demand/scripts/workflow_core.py:448`.

### Target Split

- `using-just-demand`: only bootstrap routing, risk classification, and recovery entry points.
- `socratic-clarification`: only uncertainty reduction and user-visible decision approval.
- `just-demand-intake`: only convert approved intent into the durable task contract.
- `just-demand-execution`: only task selection, context assembly, dispatch, and progress transitions.
- `just-demand-verification`: only evidence, correction routing, and closeout.
- `capture-lessons`: remain separate because reusable learning is optional and cross-task, but remove copied verification policy.

Keep the names during migration. Reduce duplication before considering merges.

Superpowers provides the right bootstrap lesson: inject one routing skill once, then load specialized skills on demand (`superpowers/.opencode/plugins/superpowers.js:55-139`). Its absolute "even a 1% chance" skill-loading rule and universal brainstorming approval should not be copied.

## Injection And Triggering

### Current Runtime Chain

The globally installed Just Demand adapter currently has four files:

1. `just-demand-session-start.js` injects a reminder and workflow-state block through `experimental.chat.system.transform` (`:37-49`).
2. `just-demand-state.js` classifies lifecycle and execution language with English and Chinese regexes (`:33-61`, `:87-154`).
3. `just-demand-subagent-context.js` enforces dispatch preconditions and injects role context in `tool.execute.before` (`:53-147`).
4. `just-demand-lib.js` reads task state, renders context, and implements tool gates.

This proves the plugin layer is operational from global copies. The repository copies were intentionally removed (commit `fccb676`) on the current `refactor-opencode-plugin` branch because the old plugin layer had fundamental design problems:

- **Overly strict natural-language gates**: the state plugin classified every user and model utterance into lifecycle phases using regex patterns, then blocked or allowed tool execution based on keyword matches. Language coverage is necessarily incomplete and false positives are unavoidable.
- **Model-authored workflow skip**: the most serious gate defect. The model could emit a phrase matching `EXPLICIT_WORKFLOW_SKIP_PATTERNS`, after which tool gates were bypassed. User authorization must not be inferred from the model's own narration.
- **Confusing multi-layer context injection**: the subagent context plugin injected workflow state, context files, and reminder blocks through multiple overlapping mechanisms, making the injection path hard to trace and debug.
- **Heuristic classification on every turn**: the plugin applied lifecycle intent patterns, code investigation patterns, neutral analysis patterns, and workflow entry narration patterns on every message, creating brittle behavior that varied unpredictably across model versions and phrasing.

The new plugin layer must not reintroduce these patterns. See the Gate Boundary design below.

There is a second deployment defect: global `just-demand-lib.js` derives `REPO_ROOT` from its own installed location and constructs `JUST_DEMAND_CLI` from that root (`/home/Sighthesia/.config/opencode/plugins/just-demand-lib.js:7-9`). In a global install this does not point to the repository or the PATH-installed CLI. Dynamic context rendering and packet lint therefore silently fall back when the derived CLI does not exist (`:1233-1256`, `:1344`).

### Gate Boundary

Hard gates are appropriate when they check structured facts:

- a formal task exists and is selected;
- the task status permits execution;
- required contract fields and role context files exist;
- a pending reflection blocks further writable execution;
- a verification pass is required before closeout.

Hard gates are not reliable when they infer authorization from prose. The state plugin classifies generic words such as start, continue, complete, skip, and implementation verbs. Those regexes are useful reminders and telemetry, but language coverage is necessarily incomplete and false positives are unavoidable.

Target rule:

```text
structured state + explicit tool action -> may block
natural-language heuristic           -> remind and observe only
```

### Adopt From Trellis

Adopt Trellis' session-scoped active-task resolution and role-specific context manifest. Its subagent hook resolves task context from the session, an explicit `Active task:` marker, or a controlled single-session fallback, then injects PRD/design/implementation and selected JSONL context (`Trellis/.opencode/plugins/inject-subagent-context.js:20-26`, `:380-511`).

Do not copy mandatory JSONL curation for every task. Use a generated manifest with optional explicit additions, so context selection does not become user work.

### New Plugin Architecture Principle

The replacement plugin layer must:

- Hold only structural preconditions (task exists, context files present, reflection not pending).
- Never block or allow based on keyword matching. Language heuristics are reminders and telemetry only.
- Use a single, traceable context injection path.
- Not carry workflow-authorization logic that the CLI already owns.

## Durable State And Lifecycle

### Retain

Retain the Python state machine, event history, locks, reflection mechanism, checkpoint commit, verification closeout, and archive-on-pass. `complete_verification` provides a real transactional boundary from verification evidence to checkpoint and archive (`.just-demand/scripts/workflow_core.py:2371-2494`). Neither reference project combines these properties as strongly.

### Redesign

Twenty-three unfinished tasks make the current rule to inspect all active tasks impractical. This is not evidence that durable state is wrong; it means the active set lacks lifecycle hygiene and selection scope.

Add:

- session-scoped current task as the primary pointer;
- workspace current task only as an explicit compatibility fallback;
- `abandoned` or `superseded` terminal paths that do not pretend verification passed;
- active-task triage by age, status, impact, and conflict;
- `list-active` defaulting to the current session, recent tasks, and conflicts, with `--all` for full history;
- periodic consistency checks across state IDs, active directories, session pointers, and archive entries.

Do not auto-archive stale tasks as if they completed. Staleness should prompt or support triage into `abandoned`, `superseded`, `resumed`, or genuinely completed states.

## Cross-Stage Plan Memory

### Problem

Just Demand currently has **no durable cross-stage memory**. Each formal task creates a fresh context, executes in isolation, and archives independently. When a goal requires multiple sequential tasks (a "campaign" or "roadmap"), the system cannot answer:

- What user suggestions are still pending?
- Which tasks have been completed, and which items did they cover?
- What is the next stage, and what blocks it?
- What was the original user intent, before any task decomposed it?

Without this layer, continuity depends entirely on the user repeating information across sessions.

### Plan Ledger — The Durable Source Of Truth

A **plan ledger** is a persistent record for a multi-stage goal. It is the single source of truth for a campaign and must **not** be archived or deleted when any individual task completes.

```
.just-demand/state/plan/
  <plan-id>/
    plan.json        — metadata, phases, suggestion items, dependency graph
    items/           — one JSON file per suggestion item (preserves original text)
    tasks/           — task-id → coverage mapping
    archive/         — closed/completed plan ledger snapshots
```

Key properties:

- **Survives individual task lifecycle**. The ledger is not owned by any single task. It persists across task creation, execution, verification, and archive.
- **Root-level identity**. The ledger has its own ID, separate from task IDs. A task's context can reference a ledger via parent/root/lineage fields, but the ledger does not depend on any task existing.
- **Created at campaign start**. The ledger is created when the first stage of a multi-stage plan is promoted. It is not retroactive.
- **Not a second lifecycle**. The plan ledger is data the CLI reads and writes — it has no independent state machine, event system, or locks. Status transitions within the ledger should reuse the existing `events.jsonl` log rather than creating a parallel audit trail. Existing task `lineage_task_ids`, `parent_task_id`, and `root_task_id` fields serve as the bridge between task-level lifecycle and plan-level state; a new `plan_id` field in the task JSON connects them without duplicating task state machinery.

### Suggestion Items

User suggestions are **never compressed into lossy summaries**. Each suggestion is stored as a structured item that preserves the user's original wording:

```json
{
  "item_id": "suggestion-001",
  "created_at": "2026-07-11T00:00:00Z",
  "source": "user message",
  "original_text": "<user's verbatim words>",
  "context_snapshot": "<the message context at time of suggestion, if available>",
  "status": "accepted",
  "status_history": [
    {"status": "new", "at": "2026-07-11T00:00:00Z"},
    {"status": "accepted", "at": "2026-07-11T00:05:00Z"}
  ],
  "covered_by": ["task-abc"],
  "dependency_ids": ["suggestion-003"],
  "evidence": ["task-abc completed verification at 2026-07-11T12:00:00Z"],
  "notes": ""
}
```

**Status values:**

| Status | Meaning |
| --- | --- |
| `new` | Recorded, not yet reviewed |
| `accepted` | Approved by user for implementation |
| `planned` | Scheduled for a specific phase/stage |
| `in-progress` | Currently being addressed |
| `completed` | Covered by a verified task |
| `deferred` | Postponed to a later phase (reason recorded) |
| `rejected` | Explicitly declined (reason recorded) |
| `superseded` | Replaced by a different approach (reference to superseding item) |

Status transitions are monotonic in the sense that every change is recorded in `status_history`. No transition is permanently forbidden — a deferred item may become accepted later — but the history preserves the audit trail.

**Anti-outcome**: user suggestions are never lossy-summarized. The original text is always preserved alongside any structured fields.

### Plan/Phase Structure

```json
{
  "plan_id": "plan-multi-stage-001",
  "title": "Just Demand plugin refactoring and plan memory",
  "created_at": "2026-07-11T00:00:00Z",
  "phases": [
    {
      "phase_id": "phase-1",
      "title": "Plan infrastructure and plugin boundary",
      "status": "planned",
      "suggestion_ids": ["suggestion-001", "suggestion-002"],
      "task_ids": ["task-abc"],
      "dependencies": []
    },
    {
      "phase_id": "phase-2",
      "title": "Plan-ledger injection and next-stage prompt",
      "status": "new",
      "suggestion_ids": ["suggestion-003"],
      "task_ids": [],
      "dependencies": ["phase-1"]
    }
  ],
  "next_phase_id": "phase-1",
  "blocker": ""
}
```

Phase states: `new`, `planned`, `in-progress`, `completed`, `blocked`, `abandoned`.

### Task ↔ Plan Association

Existing task JSON has `parent`, `root`, and `lineage` fields. The plan ledger extends this by:

1. Each task that belongs to a plan records `plan_id` in its task JSON.
2. Each task's `context.md` includes a **plan snapshot** showing the current phase, covered items, pending items, and next phase.
3. The plan ledger records which tasks cover which suggestion items.

### Task Snapshot → Context Files

When a task is dispatched, the plan ledger generates a **focused snapshot** written into `context.md` (and referenced in `implement.md` / `verify.md` as needed):

```markdown
## Plan Context

Plan: plan-multi-stage-001 — "Just Demand plugin refactoring and plan memory"
Phase: phase-1 — "Plan infrastructure and plugin boundary" (in-progress)

Items covered by this task:
  - suggestion-001: "纠正插件仅在 main 分支…" [accepted]
  - suggestion-002: "修订评估路线图…" [accepted]

Pending items after this task:
  - suggestion-003: "设计 plan ledger" [planned — phase-2]

Next phase after this task: phase-2 — "Plan-ledger injection and next-stage prompt"
  Dependency: phase-1 must complete verification

⚠ Recording future phases documents intent. It does not approve implementation.
```

This snapshot is machine-generated from the plan ledger, not hand-written. It tells the subagent exactly what this task covers and what comes next.

### Closeout → Ledger Update

When a task completes verification and closeout runs, the closeout step **must**:

1. Mark all suggestion items covered by this task as `completed`.
2. Record `evidence` for each item (the verification summary and task ID).
3. Advance the current phase to `completed`.
4. Check dependencies for the next phase — if all dependencies are met, set `next_phase_id` to the next planned phase.
5. If any item in the next phase is `accepted` or `planned`, generate a **mandatory next-stage report**.

### Mandatory Next-Stage Prompt

After closeout, if the plan ledger has any remaining `accepted` or `planned` items (in any phase whose dependencies are satisfied), the system **must** present:

```
[Plan Continuation]

Plan: <title>
Next stage: <phase title> (approved in original plan — lightweight)

Covered in this task:
  - item-1 [completed] — evidence: <verification summary>
  - item-2 [completed]

Remaining:
  - item-3 [planned] — <original text excerpt>
  - item-4 [deferred] — reason: <recorded reason>

Blockers before next stage:
  - (if any) <blocker description>

Transition:
  - If this phase was approved in the original plan: user affirms (yes/no) → system creates the task.
  - If this phase is recorded but not yet approved: use `just-demand . create-intake ...` and `promote` as usual.
```

This prompt is **mandatory** — the closeout must not simply report "task complete" when remaining plan items exist. The user must not be required to remember what comes next.

**Two transition paths:**

- **Approved-phase continuation**: when the next phase was defined in the user-approved plan, the transition is a lightweight user affirmation. The user confirms "yes", and the system creates a formal task referencing the existing plan ledger — no re-promotion needed. This is consistent with "after one approved plan, continue autonomously until a blocker, material scope change, architecture deviation, or verification failure requires user input" (see P1 item 7 below). The blocker list in the prompt determines whether autonomous continuation applies: if blockers exist, the system stops and explains why.

- **Unapproved-item promotion**: when the next phase or its suggestion items were recorded but never part of an approved plan, the standard intake → promotion → execution lifecycle applies. The prompt clearly labels which path each remaining item belongs to.

If the next phase has blockers (e.g., a dependency phase is not completed, or an item is deferred), the prompt lists them clearly and does not suggest proceeding until they are resolved.

### Recording ≠ Approval

The plan ledger records what the user suggested and what phases were discussed. **Recording a future phase or a suggestion does not approve its implementation.** The approval model distinguishes two cases:

- **Plan-level approval**: When the user approves the first phase of a multi-stage plan (via promotion), the approval covers all phases defined in that plan. Subsequent phases in the same plan do not require re-promotion — they use lightweight user affirmation via the next-stage prompt. This is consistent with P1 item 7: "After one approved plan, continue autonomously until a blocker, material scope change, architecture deviation, or verification failure requires user input."

- **Standalone suggestion approval**: Suggestions recorded but not belonging to any approved plan phase require standard intake → promotion → execution. Until the user explicitly promotes such a suggestion, its status is `new` or `accepted` (user said yes during discussion), but no work begins without a formal task.

The next-stage prompt always shows both cases clearly labelled. It invites the user to affirm or promote as appropriate. It does not auto-create tasks or auto-execute.

### Deferred / Rejected / Superseded

These are not dead ends. They are recorded with reasons and visible in the next-stage prompt:

- **Deferred**: "Postponed until phase-3 because dependency X is not ready." The item remains visible and can be promoted to a future phase.
- **Rejected**: "User explicitly chose not to implement this because…" The reason is recorded so the decision does not need to be remade.
- **Superseded**: "Replaced by suggestion-007 which takes a different approach." A reference to the superseding item allows traceability.

This prevents repeated discussion of previously settled decisions.

## Retain, Remove, Consolidate, Redesign

### Retain

- Python durable lifecycle and script-owned machine-state writes.
- Four role-specific agents.
- Promotion readiness based on approved user effect and blocking questions.
- Role-specific task context.
- Reflection after repeated correction.
- Independent verification, checkpoint commit, and archive-on-pass.
- Effect-first user communication.

### Remove

- Model-authored `skip workflow` as an execution authorization.
- Natural-language lifecycle regexes as hard blockers.
- Repeated copies of canonical rules across every skill.
- The legacy repository plugin sources (already removed on the current branch; the next plugin layer must not restore them).
- Default presentation of every optional intake field for every task shape.

### Consolidate

- Canonical lifecycle and role rules in `docs/workflow-spec.md` plus executable CLI invariants.
- Shared subagent failure and recovery policy in one referenced workflow section.
- Shared checkpoint and closeout policy in verification, referenced rather than copied by execution.
- Installed `.agents` content as a generated mirror, not a second authored source.
- Cross-stage plan memory into a plan-ledger module shared by context injection, closeout, and next-stage prompting.

### Redesign

- Repository-to-global plugin deployment and health checking.
- Plugin CLI discovery.
- Session/task identity.
- Hard-gate registry and unknown-write-tool handling.
- Intake data model as risk-shaped fields rather than 28 default headings.
- Role context as a generated manifest plus the user expectation contract.
- Active-task triage and terminal states.
- **Plan ledger**: durable cross-stage memory for multi-task roadmaps and user suggestions.

## Target Flow

```text
User request
    |
    v
One lightweight bootstrap/router
    |
    v
Risk classification
    |-----------------------------|
    v                             v
low risk                     material uncertainty
direct/read-only work        compact clarification
                                  |
                                  v
                           one explicit approval
                                  |
                                  v
                 CLI creates/selects session task
                 (plan ledger referenced if multi-stage)
                                  |
                                  v
                    role context manifest generated
                    (includes plan snapshot if in a plan)
                                  |
                                  v
                        focused subagent execution
                                  |
                                  v
                        fresh independent evidence
                                  |
                                  v
                     CLI closeout + archive or rework
                     (closeout writes back to plan ledger;
                      mandatory next-stage prompt if items remain)
```

Ownership:

- CLI owns lifecycle truth and authorization state.
- **Plan ledger** owns cross-stage memory; CLI reads and writes it during promotion, context generation, and closeout.
- Plugins own compact state hints, structural tool preconditions, and context injection.
- Skills teach phase-local behavior.
- Agents execute role-local contracts.
- Regexes provide reminders and telemetry only.

## Roadmap

### P0: Establish Plan Continuity And Plugin Boundary

1. **Define the plan-ledger data model**: `plan.json` schema, item schema, phase schema, task coverage mapping, dependency graph. Store as `.just-demand/state/plan/<plan-id>/`. Ship as a Python module in `.just-demand/scripts/plan_ledger.py` or equivalent, owned by the CLI lifecycle.
2. **Create the plugin boundary specification**: document the structural preconditions a replacement plugin may check (task exists, context files present, reflection not pending) and the constraints it must obey (no keyword-based blocking, single traceable injection path, no workflow-authorization logic duplicating the CLI).
3. **Verify the removal**: confirm that the current branch's plugin removal is correct and that the old plugin pattern is not treated as restore-worthy. The broken test suite (`node --test tests/just_demand/test_opencode_plugins.mjs`) is expected to fail until the new plugin layer replaces the old one.
4. **Stop deriving CLI from the global plugin directory**; resolve an install-manifest path or the PATH-installed `just-demand` executable and fail visibly when unavailable.
5. **Fix `Anti-Outcome` versus `Anti-Outcomes`** and audit every template-to-runtime field mapping.
6. **Remove model-authored one-shot skip authorization**. Store override authorization as structured workflow state originating from explicit user input or CLI action.
7. **Define an explicit host-tool capability registry**. Known writes are gated; unknown mutating capabilities fail closed or emit an actionable high-severity health error.

Dependencies: the plan-ledger data model must exist before P1 can generate plan snapshots in context files. The plugin boundary specification must exist before any new plugin code is written. No plugin redesign should precede a clear contract for what a plugin may and may not do.

### P1: Reduce Prompt And Interaction Cost + Plan Snapshot Injection

1. Compress per-turn injection to task, phase, next action, and blocking reason.
2. Make language heuristics reminders only; collect false-positive and false-negative samples before deleting or retaining individual patterns.
3. Remove duplicated policy from skills and leave each skill with one phase-local responsibility.
4. Introduce session-scoped task selection with explicit fallback provenance.
5. Generate role context manifests automatically; include a **plan snapshot** block when the task belongs to a plan ledger.
6. Separate runtime-required contract fields from optional presentation fields and render only fields relevant to the task's risk shape.
7. After one approved plan, continue autonomously until a blocker, material scope change, architecture deviation, or verification failure requires user input.
8. **Implementation**: wire the plan ledger into the context generation path. When a task has a `plan_id`, generate the plan-snapshot block in `context.md` (and reference in `implement.md` / `verify.md`).

### P2: Lifecycle Hygiene, Evolution, And Next-Stage Prompt

1. Add `abandoned` and `superseded` closure paths plus active-task triage.
2. Make `list-active` concise by default and add `--all` for the full set.
3. Reconcile state IDs, active directories, session pointers, leases, and archive entries in doctor/repair commands.
4. Measure reminder and gate behavior from events; remove heuristics that do not demonstrate value.
5. Keep OpenCode as the only supported adapter until this architecture is stable. Do not copy Trellis' cross-platform template surface prematurely.
6. **Implementation**: wire the plan ledger into closeout:
   - On task completion, mark covered items `completed`, record evidence, advance phase.
   - If any `accepted` or `planned` items remain, generate the mandatory next-stage prompt.
   - Render deferred/rejected/superseded items with reasons.
7. **Implementation**: add `just-demand plan` CLI subcommands for plan-ledger CRUD, status queries, and next-stage inspection.

## Reference Practices Not To Copy

### Superpowers

- No durable task state or recovery.
- Universal brainstorming and approval for all creative work.
- Mandatory multi-agent review topology for every small task.
- Prompt discipline as the only enforcement layer.

### Trellis

- Asking whether to create a task for every small change (`Trellis/.trellis/workflow.md:152`).
- Mandatory manual JSONL curation for routine work.
- Mandatory spec updates in every closeout.
- Broad cross-platform adapters before the OpenCode implementation is stable.

## Verification Notes

This was a read-only architecture audit apart from this report and task-state updates. No runtime source was changed apart from this document.

Verified observations:

- Four global Just Demand plugins exist and supplied the current session's reminder/state behavior.
- Repository `.opencode/plugins/` was **intentionally removed** on the `refactor-opencode-plugin` branch (commit `fccb676`). Main branch retains the historical originals.
- `node --test tests/just_demand/test_opencode_plugins.mjs` fails at import because repository plugin files are absent — expected during refactoring.
- `just-demand . list-active` returned 23 unfinished tasks during the audit.
- Promotion gates and template mappings were checked directly in `workflow_core.py`.
- Trellis and Superpowers plugin and workflow behaviors were checked from their local source trees.
- The current branch name (`refactor-opencode-plugin`) confirms the removal intent.
- Cross-stage plan memory (plan ledger, suggestion items, task snapshots, next-stage prompt) is a **new design addition** defined in this revision. No runtime code implements it yet.

Residual uncertainty: the provenance of the global plugin copies is not encoded in the current repository. They are preserved in the main branch's git history and should be treated as historical reference only — not as canonical sources to restore.
