#!/usr/bin/env node

/**
 * Sync templates/ from the canonical repo source files.
 *
 * Usage: node scripts/sync-templates.js [repo-root]
 *
 * If repo-root is omitted, assumes this package lives at
 * packages/just-demand-installer/ inside the repo (two levels up).
 *
 * This script:
 *  1. Removes the existing templates/ tree.
 *  2. Copies each source path into templates/ preserving directory structure.
 *  3. Skips __pycache__/ directories and .pyc files.
 *  4. Reports created files.
 */

const fs = require('fs');
const path = require('path');

const PACKAGE_DIR = path.resolve(__dirname, '..');
const DEFAULT_REPO_ROOT = path.resolve(PACKAGE_DIR, '..', '..');

// Source paths relative to repo root → destination paths relative to templates/
const SYNC_MAP = [
  { src: '.just-demand/scripts', dest: '.just-demand/scripts', recursive: true },
  { src: '.just-demand/global/rules.md', dest: '.just-demand/global/rules.md', recursive: false },
  { src: '.just-demand/workspace', dest: '.just-demand/workspace', recursive: true, filter: (name) => name.endsWith('.md') },
  { src: '.opencode/plugins', dest: '.opencode/plugins', recursive: true },
  { src: '.opencode/agent', dest: '.opencode/agent', recursive: true },
  { src: '.opencode/skills', dest: '.opencode/skills', recursive: true },
  { src: 'AGENTS.md', dest: 'AGENTS.md', recursive: false },
];

function shouldSkip(name) {
  return name === '__pycache__' || name.endsWith('.pyc') || name === '.pytest_cache';
}

function copyFile(src, dest) {
  const destDir = path.dirname(dest);
  if (!fs.existsSync(destDir)) {
    fs.mkdirSync(destDir, { recursive: true });
  }
  fs.copyFileSync(src, dest);
}

function copyDir(src, dest, filter) {
  if (!fs.existsSync(dest)) {
    fs.mkdirSync(dest, { recursive: true });
  }
  for (const entry of fs.readdirSync(src)) {
    if (shouldSkip(entry)) continue;
    if (filter && !filter(entry)) continue;

    const srcPath = path.join(src, entry);
    const destPath = path.join(dest, entry);
    const stat = fs.statSync(srcPath);

    if (stat.isDirectory()) {
      copyDir(srcPath, destPath, filter);
    } else {
      copyFile(srcPath, destPath);
    }
  }
}

function cleanTemplates() {
  const templatesDir = path.join(PACKAGE_DIR, 'templates');
  if (fs.existsSync(templatesDir)) {
    fs.rmSync(templatesDir, { recursive: true, force: true });
  }
  fs.mkdirSync(templatesDir, { recursive: true });
}

function sync(repoRoot) {
  const templatesDir = path.join(PACKAGE_DIR, 'templates');
  let count = 0;

  for (const { src, dest, recursive, filter } of SYNC_MAP) {
    const srcAbs = path.join(repoRoot, src);
    const destAbs = path.join(templatesDir, dest);

    if (!fs.existsSync(srcAbs)) {
      console.warn(`  warning: source missing: ${src}`);
      continue;
    }

    const stat = fs.statSync(srcAbs);
    if (stat.isDirectory() && recursive) {
      copyDir(srcAbs, destAbs, filter);
    } else if (stat.isFile()) {
      copyFile(srcAbs, destAbs);
    } else {
      console.warn(`  warning: unexpected type for: ${src}`);
      continue;
    }

    count++;
    console.log(`  synced ${src}`);
  }

  return count;
}

function main() {
  const repoRoot = process.argv[2]
    ? path.resolve(process.argv[2])
    : DEFAULT_REPO_ROOT;

  if (!fs.existsSync(path.join(repoRoot, 'AGENTS.md'))) {
    console.error(`Error: AGENTS.md not found at ${repoRoot}`);
    console.error('Pass the repo root as an argument if this package is not at packages/just-demand-installer/');
    process.exit(1);
  }

  console.log(`Syncing templates from: ${repoRoot}`);
  cleanTemplates();
  const count = sync(repoRoot);
  console.log(`Done. Synced ${count} source paths.`);
}

main();
