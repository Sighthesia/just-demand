# Just Demand Design Reassessment

Date: 2026-07-10

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

The strongest current mechanisms are the Python lifecycle, explicit verification closeout, checkpoint commits, reflection routing, and four-role agent model. The main weaknesses are authority drift between repository and globally installed plugins, heuristic natural-language gates carrying too much control responsibility, repeated policy across skills, workspace-global task selection, and an active-task set that has become operationally noisy.

The first priority is not to add more workflow behavior. It is to make the existing runtime reproducible and structurally trustworthy.

## Corrected Baseline

Three initial observations required correction during review:

1. Just Demand does have four active global plugins under `/home/Sighthesia/.config/opencode/plugins/`; the problem is that the repository's expected `.opencode/plugins/` source directory is absent.
2. `just-demand . list-active` currently reports 23 unfinished formal tasks, not 36.
3. The intake template has 28 headings, but a design task does not require all 28. Promotion requires `Scope`, `Final Expected Effect`, `Chosen Approach`, `Final Implementation Plan`, `Approval`, and no blocking questions.

Evidence:

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

This proves the plugin layer is operational, but not reproducible from the current repository. The installer and tests expect repository plugin source files, while only global copies exist. The plugin test currently fails at module import because `.opencode/plugins/just-demand-lib.js` is missing.

There is a second deployment defect: global `just-demand-lib.js` derives `REPO_ROOT` from its own installed location and constructs `JUST_DEMAND_CLI` from that root (`/home/Sighthesia/.config/opencode/plugins/just-demand-lib.js:7-9`). In a global install this does not point to the repository or the PATH-installed CLI. Dynamic context rendering and packet lint therefore silently fall back when the derived CLI does not exist (`:1233-1256`, `:1344`).

### Gate Boundary

Hard gates are appropriate when they check structured facts:

- a formal task exists and is selected;
- the task status permits execution;
- required contract fields and role context files exist;
- a pending reflection blocks further writable execution;
- a verification pass is required before closeout.

Hard gates are not reliable when they infer authorization from prose. The state plugin classifies generic words such as start, continue, complete, skip, and implementation verbs. Those regexes are useful reminders and telemetry, but language coverage is necessarily incomplete and false positives are unavoidable.

The most serious example is the one-shot workflow override. The model can emit a phrase matching `EXPLICIT_WORKFLOW_SKIP_PATTERNS`, after which the next tool gate is bypassed. User authorization must not be inferred from the model's own narration.

Target rule:

```text
structured state + explicit tool action -> may block
natural-language heuristic           -> remind and observe only
```

### Adopt From Trellis

Adopt Trellis' session-scoped active-task resolution and role-specific context manifest. Its subagent hook resolves task context from the session, an explicit `Active task:` marker, or a controlled single-session fallback, then injects PRD/design/implementation and selected JSONL context (`Trellis/.opencode/plugins/inject-subagent-context.js:20-26`, `:380-511`).

Do not copy mandatory JSONL curation for every task. Use a generated manifest with optional explicit additions, so context selection does not become user work.

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
- The assumption that the global plugin directory is a valid source of truth.
- Default presentation of every optional intake field for every task shape.

### Consolidate

- Canonical lifecycle and role rules in `docs/workflow-spec.md` plus executable CLI invariants.
- Shared subagent failure and recovery policy in one referenced workflow section.
- Shared checkpoint and closeout policy in verification, referenced rather than copied by execution.
- Installed `.agents` content as a generated mirror, not a second authored source.

### Redesign

- Repository-to-global plugin deployment and health checking.
- Plugin CLI discovery.
- Session/task identity.
- Hard-gate registry and unknown-write-tool handling.
- Intake data model as risk-shaped fields rather than 28 default headings.
- Role context as a generated manifest plus the user expectation contract.
- Active-task triage and terminal states.

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
                                  |
                                  v
                    role context manifest generated
                                  |
                                  v
                       focused subagent execution
                                  |
                                  v
                       fresh independent evidence
                                  |
                                  v
                     CLI closeout + archive or rework
```

Ownership:

- CLI owns lifecycle truth and authorization state.
- Plugins own compact state hints, structural tool preconditions, and context injection.
- Skills teach phase-local behavior.
- Agents execute role-local contracts.
- Regexes provide reminders and telemetry only.

## Roadmap

### P0: Restore Trust And Reproducibility

1. Restore the four repository plugin source files from a reviewed provenance, then verify that project source, tests, installer manifest, and global copies agree.
2. Add `just-demand doctor` checks for missing source, checksum drift, broken imports, plugin load health, and installed CLI discovery.
3. Stop deriving the CLI from the global plugin directory; resolve an install-manifest path or the PATH-installed `just-demand` executable and fail visibly when unavailable.
4. Fix `Anti-Outcome` versus `Anti-Outcomes` and audit every template-to-runtime field mapping.
5. Remove model-authored one-shot skip authorization. Store override authorization as structured workflow state originating from explicit user input or CLI action.
6. Define an explicit host-tool capability registry. Known writes are gated; unknown mutating capabilities fail closed or emit an actionable high-severity health error.
7. Restore the currently broken plugin test suite before changing behavior.

Dependencies: plugin provenance must be established before global files are overwritten. No other redesign should precede a green, reproducible adapter baseline.

### P1: Reduce Prompt And Interaction Cost

1. Compress per-turn injection to task, phase, next action, and blocking reason.
2. Make language heuristics reminders only; collect false-positive and false-negative samples before deleting or retaining individual patterns.
3. Remove duplicated policy from skills and leave each skill with one phase-local responsibility.
4. Introduce session-scoped task selection with explicit fallback provenance.
5. Generate role context manifests automatically; allow optional curated additions without requiring JSONL maintenance.
6. Separate runtime-required contract fields from optional presentation fields and render only fields relevant to the task's risk shape.
7. After one approved plan, continue autonomously until a blocker, material scope change, architecture deviation, or verification failure requires user input.

### P2: Lifecycle Hygiene And Evolution

1. Add `abandoned` and `superseded` closure paths plus active-task triage.
2. Make `list-active` concise by default and add `--all` for the full set.
3. Reconcile state IDs, active directories, session pointers, leases, and archive entries in doctor/repair commands.
4. Measure reminder and gate behavior from events; remove heuristics that do not demonstrate value.
5. Keep OpenCode as the only supported adapter until this architecture is stable. Do not copy Trellis' cross-platform template surface prematurely.

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

This was a read-only architecture audit apart from this report and task-state updates. No runtime source was changed.

Verified observations:

- Four global Just Demand plugins exist and supplied the current session's reminder/state behavior.
- Repository `.opencode/plugins/` is absent while installer and tests still require it.
- `node --test tests/just_demand/test_opencode_plugins.mjs` fails at import because repository plugin files are absent.
- `just-demand . list-active` returned 23 unfinished tasks during the audit.
- Promotion gates and template mappings were checked directly in `workflow_core.py`.
- Trellis and Superpowers plugin and workflow behaviors were checked from their local source trees.

Residual uncertainty: the provenance of the global plugin copies is not encoded in the current repository. They may be recoverable from git history or another installation source, but they must not be accepted as canonical without review.
