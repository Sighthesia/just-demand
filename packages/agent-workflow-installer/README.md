# just-demand-installer

Local installer for the Just Demand runtime. Copies the workflow templates into a target workspace via `just-demand init`.

Source: https://github.com/Sighthesia/on-demand

## Install locally

```bash
# From the repo root
cd packages/just-demand-installer
npm install
```

## Pack

```bash
npm pack
# Produces just-demand-installer-0.1.0.tgz
```

## Install from tarball

```bash
npm install ./just-demand-installer-0.1.0.tgz
# or
pnpm add ./just-demand-installer-0.1.0.tgz
```

## Usage

```bash
# Initialize workflow into current directory
npx just-demand init

# Initialize into a specific directory
npx just-demand init ./my-project

# Force overwrite of existing managed files
npx just-demand init --force
npx just-demand init --force ./my-project

# Refresh managed template files in an installed workspace
npx just-demand upgrade
npx just-demand upgrade ./my-project
```

This copies the Just Demand runtime templates (OpenCode plugins, agents, skills, and AGENTS guidance) into the target directory. Without `--force`, existing files are skipped; with `--force`, managed template files are overwritten. `upgrade` always overwrites managed template files (equivalent to `init --force`). `.gitignore` rules and `.opencode/package.json` are always merged (never blindly overwritten).

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
