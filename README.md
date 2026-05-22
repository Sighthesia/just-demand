# Just Demand

Just Demand is an OpenCode-first local agent workflow runtime.

- Python scripts own workflow state.
- OpenCode plugins inject lightweight context.
- Project skills hold detailed workflow rules.

## Install

Just Demand is not yet published as an npm, uv, or pipx package.

Use this repository directly as the installation source.

### 1. Install globally for OpenCode

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

### 2. Install to a custom OpenCode config root

Useful for testing or isolated setups:

```bash
python3 .just-demand/scripts/task.py install --opencode --global --config-root "/your/config/root"
```

## Enable In A Project

After the global install, each project only needs local workflow state.

From this repository or any location that can reference the script path, run:

```bash
python3 /path/to/just-demand/.just-demand/scripts/task.py --root "/path/to/project" init
```

This creates:

```text
/path/to/project/.just-demand/
```

The normal model is:

- global install provides reusable OpenCode runtime capability
- each project stores its own local `.just-demand/` state

No per-project `.opencode/` copy is required for the normal flow.

## Update

To refresh the global OpenCode install after pulling new changes in this repository:

```bash
python3 .just-demand/scripts/task.py update --opencode --global
```

If you use a custom OpenCode config root:

```bash
python3 .just-demand/scripts/task.py update --opencode --global --config-root "/your/config/root"
```

Project-local state usually does not need migration for this workflow change. If a project has not been initialized yet, run `init` for that project.

## Check Status

Check the current global install and the current project's activation status:

```bash
python3 .just-demand/scripts/task.py --root . doctor
```

Check another project explicitly:

```bash
python3 /path/to/just-demand/.just-demand/scripts/task.py --root "/path/to/project" doctor
```

## Uninstall

Remove the global OpenCode installation:

```bash
python3 .just-demand/scripts/task.py uninstall --opencode --global
```

With a custom config root:

```bash
python3 .just-demand/scripts/task.py uninstall --opencode --global --config-root "/your/config/root"
```

The uninstaller removes Just Demand-managed files only.

## Recommended Usage

1. Clone or keep this repository at a stable local path.
2. Install globally once:

```bash
python3 .just-demand/scripts/task.py install --opencode --global
```

3. For each project you want to use Just Demand in:

```bash
python3 /stable/path/to/just-demand/.just-demand/scripts/task.py --root "/target/project" init
```

4. After updating this repository, refresh the global install:

```bash
python3 .just-demand/scripts/task.py update --opencode --global
```

## Verification Commands

```bash
python3 -m unittest tests.just_demand.test_workflow_core -v
python3 -m unittest tests.just_demand.test_install -v
node --test tests/just_demand/test_opencode_plugins.mjs
python3 -m json.tool .opencode/package.json
```
