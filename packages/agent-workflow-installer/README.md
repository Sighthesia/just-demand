# just-demand

Published npm package for the [Just Demand](https://github.com/Sighthesia/just-demand) runtime — an OpenCode-first local agent workflow installer and project bootstrapper. It bootstraps a workspace explicitly, and upgrades the tool itself without silently rewriting already-initialized project files.

Source: https://github.com/Sighthesia/just-demand

## Install from registry

```bash
npm install -g just-demand
# or
pnpm add -g just-demand
```

## Install locally

```bash
# From the repo root
cd packages/agent-workflow-installer
npm install
```

## Pack (pre-publish test)

```bash
npm pack
# Produces just-demand-0.1.0.tgz
```

## Install from tarball

```bash
npm install ./just-demand-0.1.0.tgz
# or
pnpm add ./just-demand-0.1.0.tgz
```

## Usage

```bash
# Run directly from the package (npm/pnpm friendly)
npm exec --yes --package just-demand -- just-demand "./my-project" init
pnpm dlx just-demand just-demand "./my-project" init

# Install globally, then run the CLI from PATH
npm install -g .
just-demand "./my-project" init

# Force overwrite of existing managed files
just-demand --force "./my-project"
just-demand "./my-project" init --force

# Refresh managed template files in an installed workspace
just-demand upgrade
just-demand "./my-project" upgrade
```

This copies the Just Demand runtime templates (OpenCode plugins, agents, runtime skills, and AGENTS guidance) into the target directory, then mirrors the public agent-neutral skills surface into `.agents/skills`. The installer accepts the same project-first form as the repo-local CLI: `just-demand "<project>" init` and `just-demand "<project>" upgrade`. Without `--force`, existing files are skipped; with `--force`, managed template files are overwritten. `upgrade` now behaves like a non-destructive refresh for already-initialized workspaces unless you pass `--force`. `.gitignore` rules and `.opencode/package.json` are only written when the target file does not already exist.

Both `init` and `upgrade` write installer version metadata to `.just-demand/installer-metadata.json`. This file records which installer version last touched the workspace, enabling future commands to compare installed vs. current versions.

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

- `.opencode/plugins/`
- `.opencode/agent/`
- `.opencode/skills/`
- `AGENTS.md`

The runtime package mirrors `.opencode/skills` into `.agents/skills` at install time so the public skills surface stays readable without duplicating the source of truth in the package itself.

The script skips `__pycache__/` directories and `.pyc` files.

### What is in templates/

```
templates/
├── .opencode/
│   ├── agent/
│   ├── plugins/
│   └── skills/
└── AGENTS.md
```

## Files in the npm package

Only `bin/` and `templates/` are shipped. Scripts and tests are excluded from the published package.
