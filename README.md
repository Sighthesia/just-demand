# Just Demand

Just Demand is an OpenCode-first local agent workflow runtime. My personal coding workflow.

Highly inspired by [Trellis](https://github.com/mindfold-ai/Trellis) and [superpowers](https://github.com/obra/superpowers)

- Python scripts own workflow state.
- OpenCode plugins inject lightweight context.
- Project skills hold detailed workflow rules.

Canonical workflow spec: [`docs/workflow-spec.md`](docs/workflow-spec.md) owns lifecycle, roles, transitions, recovery, and source-of-truth boundaries. README stays high-level and keeps only the orientation layer.

## Just Demand Workflow Philosophy

Just Demand is a workflow runtime, not a one-shot prompt bundle.

The canonical workflow spec lives in [`docs/workflow-spec.md`](docs/workflow-spec.md); this page summarizes the model for readers and install-time orientation.

It is written for two audiences:

- people evaluating whether an agent workflow is worth adopting
- people designing their own agent workflow and looking for reusable patterns

If you only want a clever prompt, this project is probably more structure than you need. If you need repeatable task handling, explicit handoffs, and a durable way to keep an agent from drifting, the layered model below is the point.

### Why An Agent Workflow Exists

A single prompt can start a task, but it usually cannot reliably carry the full lifecycle of real work.

Common pain points this workflow is meant to solve:

- **Memory fade**: the agent forgets earlier decisions after a few turns.
- **Role drift**: the same model starts acting like planner, implementer, and reviewer at once.
- **Hidden state**: progress exists only in conversation, so it is hard to resume or audit.
- **Prompt brittleness**: the more behavior you cram into a single prompt, the easier it is to break.
- **Unclear ownership**: nobody knows who is responsible for clarification, execution, verification, or closure.
- **Ad hoc handoffs**: subagents are spawned without a stable task boundary or success criteria.

### How Just Demand Solves Those Problems

Just Demand uses a layered workflow so each layer carries one kind of truth:

- **README / AGENTS / docs** explain the model and the rules of the game.
- **Skills** tell the main agent how to route work and when to slow down for clarification.
- **Plugins** keep the current task, workflow state, and execution gates visible in the runtime.
- **CLI + `.just-demand/` state** store the durable lifecycle record so work can survive sessions.

That layering keeps prompt text light while moving durable workflow truth into explicit state and scripts. The result is a system that can be resumed, verified, and archived without depending on the chat transcript alone.

### Guiding Principle

The system is designed to keep durable workflow truth in explicit state and scripts, while keeping prompt-layer guidance light, readable, and role-specific.

```text
user goal
  -> clarify
  -> intake
  -> promote
  -> context
  -> dispatch
  -> verify
  -> complete-verification
  -> archive
```

### Operating Model At A Glance

```text
User
  |  goals, constraints, approval
  v
Main agent
  |  clarifies, shapes, routes, verifies
  v
Subagent(s)
  |  focused execution inside a task boundary
  v
Verified result -> archive
```

#### Communication diagram

```text
user
  |  intent / constraints / approval
  v
main agent
  |  task shape / context / dispatch / closure
  +------------------------------+
  |                              |
  v                              v
researcher / coder / tester / advisor
  |  evidence / implementation / checks / tradeoffs
  +------------------------------+
                 v
          main agent consolidates
                 v
                user
```

#### Dispatch diagram

```text
request
  -> clarify
  -> promote to formal task
  -> attach task context
  -> dispatch the right subagent
  -> verify against acceptance criteria
  -> complete-verification
  -> archive
```

### Responsibility Table

| Role           | Owns                                                              | Does not own                                                                   |
| -------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **User**       | Goals, constraints, tradeoff preferences, final approval          | Internal routing mechanics, subagent orchestration, workflow state writes      |
| **Main agent** | Clarification, task shaping, dispatch, closure, summaries         | Broad implementation work that should be delegated when a task boundary exists |
| **Researcher** | Evidence gathering, problem mapping, source comparison            | Code changes, task promotion, verification closeout                            |
| **Coder**      | Scoped implementation inside the task boundary                    | Workflow ownership, task lifecycle decisions, cross-task re-planning           |
| **Tester**     | Acceptance verification, failure discovery, regression checking   | Rewriting the implementation plan or reassigning ownership                     |
| **Advisor**    | Fresh-context framing, tradeoff analysis, cross-boundary judgment | Executing the task or closing it unilaterally                                  |

The user defines goals, constraints, and final approval. The main agent owns workflow shape, routing, and closure. Subagents execute focused role contracts inside the task boundary.

### Main Agent Output Style

The main agent should optimize for low cognitive load:

- **Effect first**: lead with the user-visible result.
- **Defaults first**: mention the recommended path before alternatives.
- **Options only when needed**: present tradeoffs when the choice changes behavior, compatibility, cost, security, or long-term maintenance.
- **Implementation details last**: mention files and mechanics only when they help the decision or verification.

### Control Layers And Why They Exist

```text
docs / AGENTS / README
    -> explain the philosophy and roles

skills
    -> route the main agent and clarify intake/execution/verification habits

plugins
    -> inject lightweight runtime state, execution gates, and subagent context

CLI + .just-demand state
    -> durable source of truth for task lifecycle and archive history
```

This layered model exists because pure one-time injection fades after the first turn, and pure prompt-only control is too soft for durable task lifecycle and gatekeeping. The runtime needs persistent state, explicit promotion, and structured handoff between roles.

### What Each Layer Is For

- **Skills**: encode the main-agent identity, routing, clarification, intake, execution, verification, and lesson-capture habits.
- **Plugins**: inject the current workflow state, enforce execution gates, and attach the right task context to subagents.
- **CLI / `.just-demand/` state**: provide the durable lifecycle source of truth for active tasks, archives, and workflow transitions.
- **Task context files**: give each subagent the scoped facts it needs without re-reading the whole workspace.

### Main-Agent Identity Sources

The main agent’s working identity is reinforced from several places at once:

1. `AGENTS.md`
2. `using-just-demand`
3. the workflow-state plugin banner / guardrails
4. the current task context files
5. subagent prompts, for subagents only

These sources agree on the same role model so the main agent stays a dispatcher and workflow owner rather than drifting into an ad hoc helper.

### Subagent Inner Loops

Subagents are not miniature workflow owners. Their inner loops are role-specific execution contracts:

- **researcher**: gather evidence and map the problem space.
- **coder**: implement the scoped change.
- **tester**: verify the task against acceptance criteria.
- **advisor**: frame hard decisions and cross-boundary tradeoffs.

They do not independently create, promote, close, or re-route tasks. That keeps lifecycle ownership centralized and prevents role drift.

### Comparison With Simpler Patterns

| Pattern                 | What it is good at                         | Where it breaks down                                                           | Why Just Demand is different                                                             |
| ----------------------- | ------------------------------------------ | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| **One-shot prompting**  | Fast starts and small, self-contained asks | Loses context, collapses roles, and depends on the transcript staying readable | Separates durable workflow state from conversational prompting                           |
| **Prompt-only control** | Lightweight guidance when the task is tiny | Hard to enforce gates, ownership, and closure discipline                       | Moves the important workflow truth into explicit state, scripts, and plugins             |
| **Ad hoc subagents**    | Cheap parallelism for isolated chores      | Handoffs get messy and task boundaries blur                                    | Subagents are dispatched only after formal task shaping and with role-specific contracts |

### Practical Design Lessons For Custom Agent Workflows

If you are borrowing ideas from Just Demand for your own workflow, the reusable lessons are:

1. **Make lifecycle explicit.** State when work is clarified, promoted, verified, and archived.
2. **Separate policy from state.** Keep the instructions lightweight and store durable truth somewhere structured.
3. **Give each role one job.** The more roles overlap, the faster the agent starts to self-conflict.
4. **Require a task boundary before delegation.** Subagents work best when they receive a bounded brief, not a vague conversation.
5. **Keep ownership centralized.** Someone must own routing, closure, and recovery when the work goes sideways.
6. **Optimize for resume-ability.** If the session disappears, the workflow should still tell you what was happening.
7. **Prefer readable scaffolding over clever prompts.** A simple, durable system outlasts a denser but fragile prompt stack.

### Workflow Lifecycle And Handoff Shape

```text
clarify
  -> intake
  -> promote
  -> context
  -> dispatch
  -> verify
  -> complete-verification
  -> archive
```

Each step exists to reduce ambiguity before work starts, keep the active task explicit, and make closure durable enough to survive future sessions.

### Why Not One-Time Injection Or Prompt-Only Control

- **One-time injection** is easy to forget, easy to drift from, and weak across long sessions.
- **Prompt-only control** cannot reliably enforce gates, task state, or archival discipline.
- **Persistent runtime state** plus **lightweight prompt guidance** gives the best balance of durability, clarity, and operability.

### Scannable Mental Model

```text
human intent
  -> workflow policy
  -> state transition
  -> role-specific execution
  -> verification
  -> archived task history
```

Think of Just Demand as an operating system for agent work: the docs explain the model, skills teach the habits, plugins enforce the current frame, and the CLI/state layer records what actually happened.

## Install

### Primary Path: npm / pnpm

Install the published package globally:

```bash
npm install -g just-demand
# or
pnpm add -g just-demand
```

Then initialize a project explicitly:

```bash
just-demand "/path/to/project" init
```

You can also run it without a global install:

```bash
npm exec --yes --package just-demand -- just-demand "./demo-workspace" init
```

### Secondary Path: Source / Developer Mode

If you are developing Just Demand itself or testing directly from this repository, use the repo checkout as the installation source.

### Linux / macOS

#### 1. Install globally for OpenCode

From this repository root, run the installer package directly:

```bash
npm exec --yes --package ./packages/agent-workflow-installer -- just-demand "./demo-workspace" init
```

For a global OpenCode install, use the repository CLI:

```bash
just-demand install --opencode --global
```

This installs Just Demand runtime assets into the default OpenCode global config directory:

```text
~/.config/opencode/
```

Installed assets include:

- `plugins/`
- `agents/`
- `skills/`
- `package.json`

The workspace installer also mirrors the public reference surface into `.agents/skills` so humans and other agents can inspect the skills without OpenCode-specific context.

The installer also creates a persistent `just-demand` entry in a user-writable bin directory that is already on `PATH` when possible, so new shells can run `just-demand` directly.

Restart OpenCode after installation.

#### 2. Install to a custom OpenCode config root

Useful for testing or isolated setups:

```bash
just-demand install --opencode --global --config-root "/your/config/root"
```

### Windows

#### Prerequisites

- Python 3.11+ installed and on `PATH`.
- OpenCode installed (global plugins will be loaded from its config root).

#### 1. Install globally for OpenCode

Open **PowerShell** or **Command Prompt** in this repository root, run:

```powershell
just-demand install --opencode --global
```

If you have multiple Python versions, use the `py` launcher:

```powershell
py -3 just-demand install --opencode --global
```

Python accepts forward slashes in paths, so `scripts/task.py` works on Windows too.

The default OpenCode config root on Windows is:

```text
%USERPROFILE%\.config\opencode\
```

i.e. `C:\Users\<YourUsername>\.config\opencode\`

After installation, restart OpenCode.

#### 2. Install to a custom OpenCode config root

```powershell
just-demand install --opencode --global --config-root "C:\Users\You\.config\opencode"
```

## Enable In A Project

After either installation path, each project needs its own local `.just-demand/` state created by `init`.

Linux / macOS:

```bash
just-demand "/path/to/project" init
```

Windows:

```powershell
just-demand "C:\path\to\project" init
```

This creates:

```text
/path/to/project/.just-demand/
```

The normal model is:

- global install provides reusable OpenCode runtime capability
- each project stores its own local `.just-demand/` state and knowledge files
- `.agents/skills` is the public reference layer; `.opencode/skills` stays the runtime layer

No per-project `.opencode/` copy is required for the normal flow.

## Update

To refresh the global OpenCode install after pulling new changes in this repository:

Linux / macOS:

```bash
just-demand update --opencode --global
```

Windows:

```powershell
just-demand update --opencode --global
```

With a custom OpenCode config root:

```bash
just-demand update --opencode --global --config-root "/your/config/root"
```

```powershell
just-demand update --opencode --global --config-root "C:\Users\You\.config\opencode"
```

Project-local state usually does not need migration for this workflow change. If a project has not been initialized yet, run `init` for that project.

Existing initialized projects are left alone by package upgrades; rerun `init` explicitly only when you want to bootstrap a fresh project or deliberately refresh a workspace with `--force`.

```bash
just-demand "/target/project" init
```

```powershell
just-demand "C:\path\to\project" init
```

`update --opencode --global` refreshes only the global OpenCode runtime assets under the OpenCode config root. It does not fan out to previously initialized project workspaces because project workspaces only hold local state. `init` is idempotent and is the explicit project bootstrap step.

## License

This repository and the publishable npm package use the `MIT` license.

## Check Status

Check the current global install and the current project's activation status:

Linux / macOS:

```bash
just-demand doctor
```

Windows:

```powershell
just-demand doctor
```

Check another project explicitly:

```bash
just-demand "/path/to/project" doctor
```

```powershell
just-demand "C:\path\to\project" doctor
```

## Uninstall

Remove the global OpenCode installation:

```bash
just-demand uninstall --opencode --global
```

```powershell
just-demand uninstall --opencode --global
```

With a custom config root:

```bash
just-demand uninstall --opencode --global --config-root "/your/config/root"
```

```powershell
just-demand uninstall --opencode --global --config-root "C:\Users\You\.config\opencode"
```

The uninstaller removes Just Demand-managed files only.

It also removes the managed `just-demand` PATH entry that the installer created.

## Recommended Usage

### Linux / macOS

1. Install the published package once:

```bash
npm install -g just-demand
```

2. For each project you want to use Just Demand in:

```bash
just-demand "/target/project" init
```

3. Optional: if you are developing Just Demand itself, clone or keep this repository at a stable local path.

4. Source/developer mode global install from the repo:

```bash
just-demand install --opencode --global
```

5. After updating this repository in source/developer mode, refresh the global runtime assets:

```bash
just-demand update --opencode --global
```

### Windows

1. Install the published package once:

```powershell
npm install -g just-demand
```

2. For each project you want to use Just Demand in:

```powershell
just-demand "C:\path\to\target\project" init
```

3. Optional: if you are developing Just Demand itself, clone or keep this repository at a stable local path (e.g. `C:\Users\You\just-demand`).

4. Source/developer mode global install from the repo:

```powershell
just-demand install --opencode --global
```

5. After updating this repository in source/developer mode, refresh the global runtime assets:

```powershell
just-demand update --opencode --global
```

## Verification Commands

Linux / macOS:

```bash
python3 -m unittest tests.just_demand.test_workflow_core -v
python3 -m unittest tests.just_demand.test_install -v
node --test tests/just_demand/test_opencode_plugins.mjs
python3 -m json.tool .opencode/package.json
just-demand smoke
```

Windows:

```powershell
python -m unittest tests.just_demand.test_workflow_core -v
python -m unittest tests.just_demand.test_install -v
node --test tests/just_demand/test_opencode_plugins.mjs
python -m json.tool .opencode/package.json
just-demand smoke
```
