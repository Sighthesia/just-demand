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

After the global install, each project needs its own local `.just-demand/` state created by `init`.

Linux / macOS:

```bash
just-demand --root "/path/to/project" init
```

Windows:

```powershell
just-demand --root "C:\path\to\project" init
```

This creates:

```text
/path/to/project/.just-demand/
```

The normal model is:

- global install provides reusable OpenCode runtime capability
- each project stores its own local `.just-demand/` state and knowledge files

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

If you have existing initialized projects, rerun `init` for each project from the updated repository checkout to refresh local state if needed:

```bash
just-demand --root "/target/project" init
```

```powershell
just-demand --root "C:\path\to\project" init
```

`update --opencode --global` refreshes only the global OpenCode runtime assets under the OpenCode config root. It does not fan out to previously initialized project workspaces because project workspaces only hold local state. `init` is idempotent and is the explicit project bootstrap step.

If you want one explicit command that refreshes all initialized workspaces under one or more directory trees, use `sync-workspaces`:

```bash
just-demand sync-workspaces --search-root "/projects" --search-root "/more-projects"
```

```powershell
just-demand sync-workspaces --search-root "C:\Projects" --search-root "D:\Shared"
```

If you omit `--search-root`, the command scans the current working directory recursively.

## Check Status

Check the current global install and the current project's activation status:

Linux / macOS:

```bash
just-demand --root . doctor
```

Windows:

```powershell
just-demand --root . doctor
```

Check another project explicitly:

```bash
just-demand --root "/path/to/project" doctor
```

```powershell
just-demand --root "C:\path\to\project" doctor
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

## Recommended Usage

### Linux / macOS

1. Clone or keep this repository at a stable local path.
2. Install globally once:

```bash
just-demand install --opencode --global
```

3. For each project you want to use Just Demand in:

```bash
just-demand --root "/target/project" init
```

4. After updating this repository, refresh the global runtime assets:

```bash
just-demand update --opencode --global
```

5. Refresh local state in all initialized workspaces:

```bash
just-demand sync-workspaces --search-root "/path/to/projects/parent"
```

### Windows

1. Clone or keep this repository at a stable local path (e.g. `C:\Users\You\just-demand`).

2. Install globally once:

```powershell
just-demand install --opencode --global
```

3. For each project you want to use Just Demand in:

```powershell
just-demand --root "C:\path\to\target\project" init
```

4. After updating this repository, refresh the global runtime assets:

```powershell
just-demand update --opencode --global
```

5. Refresh local workflow scripts in all initialized workspaces:

```powershell
just-demand sync-workspaces --search-root "C:\path\to\projects\parent"
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
