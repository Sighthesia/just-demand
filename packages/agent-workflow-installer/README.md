# agent-workflow-installer

Local installer for the agent workflow runtime. Copies the workflow templates into a target workspace via `agent-workflow init`.

Source: https://github.com/Sighthesia/on-demand

## Install locally

```bash
# From the repo root
cd packages/agent-workflow-installer
npm install
```

## Pack

```bash
npm pack
# Produces agent-workflow-installer-0.1.0.tgz
```

## Install from tarball

```bash
npm install ./agent-workflow-installer-0.1.0.tgz
# or
pnpm add ./agent-workflow-installer-0.1.0.tgz
```

## Usage

```bash
# Initialize workflow into current directory
npx agent-workflow init

# Initialize into a specific directory
npx agent-workflow init ./my-project

# Force overwrite of existing managed files
npx agent-workflow init --force
npx agent-workflow init --force ./my-project

# Refresh managed template files in an installed workspace
npx agent-workflow upgrade
npx agent-workflow upgrade ./my-project
```

This copies the workflow runtime templates (scripts, plugins, agents, skills, rules) into the target directory. Without `--force`, existing files are skipped; with `--force`, managed template files are overwritten. `upgrade` always overwrites managed template files (equivalent to `init --force`). `.gitignore` rules and `.opencode/package.json` are always merged (never blindly overwritten).

Both `init` and `upgrade` write installer version metadata to `.agent-workflow/installer-metadata.json`. This file records which installer version last touched the workspace, enabling future commands to compare installed vs. current versions.

## Test

```bash
npm test
# or
node --test test/*.test.js
```

## Sync templates

Templates are committed copies of the source runtime files in this repository. After changing any of the source files, run the sync script to refresh `templates/`:

```bash
npm run sync-templates
```

This rebuilds `templates/` from:

- `.agent-workflow/scripts/` (Python workflow core)
- `.agent-workflow/global/rules.md`
- `.agent-workflow/workspace/*.md` (seed files only)
- `.opencode/plugins/`
- `.opencode/agent/`
- `.opencode/skills/`
- `AGENTS.md`

The script skips `__pycache__/` directories and `.pyc` files.

### What is in templates/

```
templates/
├── .agent-workflow/
│   ├── global/rules.md
│   ├── scripts/task.py
│   └── workspace/*.md
├── .opencode/
│   ├── agent/
│   ├── plugins/
│   └── skills/
└── AGENTS.md
```

## Files in the npm package

Only `bin/` and `templates/` are shipped. Scripts and tests are excluded from the published package.
