# Just Demand

Just Demand is an OpenCode-first local agent workflow runtime.

- Python scripts own workflow state.
- OpenCode plugins inject lightweight context.
- Project skills hold detailed workflow rules.

## Install

Just Demand is not yet published as an npm, uv, or pipx package.

Use this repository directly as the installation source.

### Linux / macOS

#### 1. Install globally for OpenCode

From this repository root, run:

```bash
python3 .just-demand/scripts/task.py install --opencode --global
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

Restart OpenCode after installation.

#### 2. Install to a custom OpenCode config root

Useful for testing or isolated setups:

```bash
python3 .just-demand/scripts/task.py install --opencode --global --config-root "/your/config/root"
```

### Windows

#### Prerequisites

- Python 3.11+ installed and on `PATH`.
- OpenCode installed (global plugins will be loaded from its config root).

#### 1. Install globally for OpenCode

Open **PowerShell** or **Command Prompt** in this repository root, run:

```powershell
python .just-demand/scripts/task.py install --opencode --global
```

If you have multiple Python versions, use the `py` launcher:

```powershell
py -3 .just-demand/scripts/task.py install --opencode --global
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
python .just-demand/scripts/task.py install --opencode --global --config-root "C:\Users\You\.config\opencode"
```

## Enable In A Project

After the global install, each project needs its own local `.just-demand/` state and the managed `.just-demand/scripts/` snapshot created by `init`.

Linux / macOS:

```bash
python3 /path/to/just-demand/.just-demand/scripts/task.py --root "/path/to/project" init
```

Windows:

```powershell
python C:\path\to\just-demand\.just-demand\scripts\task.py --root "C:\path\to\project" init
```

This creates:

```text
/path/to/project/.just-demand/
```

The normal model is:

- global install provides reusable OpenCode runtime capability
- each project stores its own local `.just-demand/` state and local workflow script snapshot

No per-project `.opencode/` copy is required for the normal flow.

## Update

To refresh the global OpenCode install after pulling new changes in this repository:

Linux / macOS:

```bash
python3 .just-demand/scripts/task.py update --opencode --global
```

Windows:

```powershell
python .just-demand/scripts/task.py update --opencode --global
```

With a custom OpenCode config root:

```bash
python3 .just-demand/scripts/task.py update --opencode --global --config-root "/your/config/root"
```

```powershell
python .just-demand/scripts/task.py update --opencode --global --config-root "C:\Users\You\.config\opencode"
```

Project-local state usually does not need migration for this workflow change. If a project has not been initialized yet, run `init` for that project.

If you have existing initialized projects and want to refresh their local `.just-demand/scripts/` after pulling repository changes, rerun `init` for each project from the updated repository checkout:

```bash
python3 /stable/path/to/just-demand/.just-demand/scripts/task.py --root "/target/project" init
```

```powershell
python C:\path\to\just-demand\.just-demand\scripts\task.py --root "C:\path\to\project" init
```

`update --opencode --global` refreshes only the global OpenCode runtime assets under the OpenCode config root. It does not fan out to previously initialized project workspaces because those workspaces hold their own local `.just-demand/scripts/` copies. `init` is idempotent and now acts as the explicit workspace script sync step.

If you want one explicit command that refreshes all initialized workspaces under one or more directory trees, use `sync-workspaces`:

```bash
python3 .just-demand/scripts/task.py sync-workspaces --search-root "/projects" --search-root "/more-projects"
```

```powershell
python .just-demand/scripts/task.py sync-workspaces --search-root "C:\Projects" --search-root "D:\Shared"
```

If you omit `--search-root`, the command scans the current working directory recursively.

## Check Status

Check the current global install and the current project's activation status:

Linux / macOS:

```bash
python3 .just-demand/scripts/task.py --root . doctor
```

Windows:

```powershell
python .just-demand/scripts/task.py --root . doctor
```

Check another project explicitly:

```bash
python3 /path/to/just-demand/.just-demand/scripts/task.py --root "/path/to/project" doctor
```

```powershell
python C:\path\to\just-demand\.just-demand\scripts\task.py --root "C:\path\to\project" doctor
```

## Uninstall

Remove the global OpenCode installation:

```bash
python3 .just-demand/scripts/task.py uninstall --opencode --global
```

```powershell
python .just-demand/scripts/task.py uninstall --opencode --global
```

With a custom config root:

```bash
python3 .just-demand/scripts/task.py uninstall --opencode --global --config-root "/your/config/root"
```

```powershell
python .just-demand/scripts/task.py uninstall --opencode --global --config-root "C:\Users\You\.config\opencode"
```

The uninstaller removes Just Demand-managed files only.

## Recommended Usage

### Linux / macOS

1. Clone or keep this repository at a stable local path.
2. Install globally once:

```bash
python3 .just-demand/scripts/task.py install --opencode --global
```

3. For each project you want to use Just Demand in:

```bash
python3 /stable/path/to/just-demand/.just-demand/scripts/task.py --root "/target/project" init
```

4. After updating this repository, refresh the global runtime assets:

```bash
python3 .just-demand/scripts/task.py update --opencode --global
```

5. Refresh local workflow scripts in all initialized workspaces:

```bash
python3 .just-demand/scripts/task.py sync-workspaces --search-root "/path/to/projects/parent"
```

### Windows

1. Clone or keep this repository at a stable local path (e.g. `C:\Users\You\just-demand`).

2. Install globally once:

```powershell
python C:\Users\You\just-demand\.just-demand\scripts\task.py install --opencode --global
```

3. For each project you want to use Just Demand in:

```powershell
python C:\Users\You\just-demand\.just-demand\scripts\task.py --root "C:\path\to\target\project" init
```

4. After updating this repository, refresh the global runtime assets:

```powershell
python C:\Users\You\just-demand\.just-demand\scripts\task.py update --opencode --global
```

5. Refresh local workflow scripts in all initialized workspaces:

```powershell
python C:\Users\You\just-demand\.just-demand\scripts\task.py sync-workspaces --search-root "C:\path\to\projects\parent"
```

## Verification Commands

Linux / macOS:

```bash
python3 -m unittest tests.just_demand.test_workflow_core -v
python3 -m unittest tests.just_demand.test_install -v
node --test tests/just_demand/test_opencode_plugins.mjs
python3 -m json.tool .opencode/package.json
```

Windows:

```powershell
python -m unittest tests.just_demand.test_workflow_core -v
python -m unittest tests.just_demand.test_install -v
node --test tests/just_demand/test_opencode_plugins.mjs
python -m json.tool .opencode/package.json
```
