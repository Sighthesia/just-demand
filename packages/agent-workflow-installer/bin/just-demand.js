#!/usr/bin/env node

/**
 * Just Demand CLI
 *
 * Installs or upgrades the Just Demand runtime templates in a target workspace.
 * Templates are derived from the Just Demand runtime in this repository:
 * https://github.com/Sighthesia/on-demand
 *
 * Default behavior: skip existing files, report created/skipped.
 */

const fs = require('fs');
const path = require('path');

const TEMPLATES_DIR = path.join(__dirname, '..', 'templates');

// Files to copy from templates to target root
const COPY_MAP = {
  '.just-demand/scripts': '.just-demand/scripts',
  '.just-demand/global/rules.md': '.just-demand/global/rules.md',
  '.just-demand/workspace/decisions.md': '.just-demand/workspace/decisions.md',
  '.just-demand/workspace/deferred_options.md': '.just-demand/workspace/deferred_options.md',
  '.just-demand/workspace/facts.md': '.just-demand/workspace/facts.md',
  '.just-demand/workspace/open_questions.md': '.just-demand/workspace/open_questions.md',
  '.just-demand/workspace/preferences.md': '.just-demand/workspace/preferences.md',
  '.opencode/plugins': '.opencode/plugins',
  '.opencode/agent': '.opencode/agent',
  '.opencode/skills': '.opencode/skills',
  'AGENTS.md': 'AGENTS.md',
};

// Lines to ensure in .gitignore
const GITIGNORE_LINES = [
  '# CocoIndex Code (ccc)',
  '/.cocoindex_code/',
  '',
  '# Python caches',
  '__pycache__/',
  '*.pyc',
  '',
  '# Python test cache',
  '.pytest_cache/',
  '',
  '# OpenCode local dependencies',
  '.opencode/node_modules/',
  '',
  '# Workflow runtime state and task files',
  '.just-demand/tasks/',
  '.just-demand/workspace/state.json',
  '.just-demand/workspace/events.jsonl',
  '.just-demand/workspace/locks.json',
  '.just-demand/workspace/intake/',
  '.just-demand/workspace/sessions/',
  '',
  '# Auto-generated placeholder files',
  '.just-demand/global/architecture.md',
  '.just-demand/global/glossary.md',
];

function parseArgs(argv) {
  const args = argv.slice(2);
  let command = 'init';
  let target = '.';
  let force = false;
  for (let i = 0; i < args.length; i++) {
    if (args[i] === 'init') {
      command = 'init';
    } else if (args[i] === 'upgrade') {
      command = 'upgrade';
      force = true;
    } else if (args[i] === '--force') {
      force = true;
    } else if (args[i] === '--target' && args[i + 1]) {
      target = args[i + 1];
      i++;
    } else if (!args[i].startsWith('-')) {
      target = args[i];
    }
  }
  return { command, target, force };
}

function ensureDirSync(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function copyTemplateRecursive(srcRel, destRoot, stats, force = false) {
  const srcAbs = path.join(TEMPLATES_DIR, srcRel);
  const destAbs = path.join(destRoot, srcRel);

  if (stats.isDirectory()) {
    ensureDirSync(destAbs);
    for (const child of fs.readdirSync(srcAbs)) {
      const childStats = fs.statSync(path.join(srcAbs, child));
      copyTemplateRecursive(path.join(srcRel, child), destRoot, childStats, force);
    }
    return;
  }

  // File: skip if exists (unless force)
  if (fs.existsSync(destAbs)) {
    if (force) {
      fs.copyFileSync(srcAbs, destAbs);
      console.log(`  overwrite ${srcRel}`);
    } else {
      console.log(`  skip  ${srcRel} (already exists)`);
    }
    return;
  }

  ensureDirSync(path.dirname(destAbs));
  fs.copyFileSync(srcAbs, destAbs);
  console.log(`  create ${srcRel}`);
}

function mergeGitignore(targetRoot) {
  const gitignorePath = path.join(targetRoot, '.gitignore');
  let existing = '';
  if (fs.existsSync(gitignorePath)) {
    existing = fs.readFileSync(gitignorePath, 'utf8');
  }

  const linesToAdd = GITIGNORE_LINES.filter(line => {
    if (line === '') return false; // skip blank lines for dedup
    return !existing.includes(line);
  });

  if (linesToAdd.length === 0) {
    console.log('  .gitignore already contains workflow ignore rules');
    return;
  }

  const toAppend = linesToAdd.join('\n') + '\n';
  const separator = existing.endsWith('\n') ? '' : '\n';
  fs.appendFileSync(gitignorePath, separator + toAppend);
  console.log(`  .gitignore updated with ${linesToAdd.length} new rule(s)`);
}

function mergeOpencodePackageJson(targetRoot) {
  const pkgPath = path.join(targetRoot, '.opencode', 'package.json');
  let pkg = {};
  if (fs.existsSync(pkgPath)) {
    try {
      pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    } catch (e) {
      console.warn(`  warning: could not parse .opencode/package.json, will overwrite`);
      pkg = {};
    }
  }

  const changed = !pkg.type || pkg.type !== 'module';
  pkg.type = 'module';

  ensureDirSync(path.dirname(pkgPath));
  fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');
  if (changed) {
    console.log('  .opencode/package.json updated with type: "module"');
  } else {
    console.log('  .opencode/package.json already has type: "module"');
  }
}

/**
 * Write installer version metadata into the target workspace.
 * Records which installer version last touched this workspace.
 */
function writeInstallerMetadata(targetRoot, command) {
  const metadataPath = path.join(targetRoot, '.just-demand', 'installer-metadata.json');
  const pkgPath = path.join(__dirname, '..', 'package.json');
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));

  const metadata = {
    package: pkg.name,
    version: pkg.version,
    action: command,
    timestamp: new Date().toISOString(),
  };

  ensureDirSync(path.dirname(metadataPath));
  fs.writeFileSync(metadataPath, JSON.stringify(metadata, null, 2) + '\n');
  console.log(`  installer metadata written to .just-demand/installer-metadata.json`);
}

function main() {
  const { command, target, force } = parseArgs(process.argv);

  if (command !== 'init' && command !== 'upgrade') {
    console.error(`Error: unsupported command: ${command}`);
    process.exit(1);
  }

  const targetRoot = path.resolve(target);

  if (command === 'upgrade') {
    console.log(`Upgrading Just Demand in: ${targetRoot}`);
  } else {
    console.log(`Initializing Just Demand into: ${targetRoot}${force ? ' (force)' : ''}`);
  }

  if (!fs.existsSync(targetRoot)) {
    ensureDirSync(targetRoot);
    console.log('  created target directory');
  }

  // Copy templates
  for (const [srcRel] of Object.entries(COPY_MAP)) {
    const srcAbs = path.join(TEMPLATES_DIR, srcRel);
    if (!fs.existsSync(srcAbs)) {
      console.warn(`  warning: template missing: ${srcRel}`);
      continue;
    }
    const stats = fs.statSync(srcAbs);
    copyTemplateRecursive(srcRel, targetRoot, stats, force);
  }

  // Merge .opencode/package.json
  mergeOpencodePackageJson(targetRoot);

  // Append .gitignore rules
  mergeGitignore(targetRoot);

  // Write installer metadata
  writeInstallerMetadata(targetRoot, command);

  console.log('Done.');
}

main();
