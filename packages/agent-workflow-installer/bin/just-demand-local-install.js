#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const PACKAGE_ROOT = path.join(__dirname, '..');

function printHelp() {
  console.log('just-demand-local-install');
  console.log('Usage: node bin/just-demand-local-install.js [--target <dir>] [dir]');
}

function parseArgs(argv) {
  const args = argv.slice(2);
  let target = null;
  let repoRoot = null;

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (arg === '--help' || arg === '-h') {
      return { help: true };
    }
    if (arg === '--target' && args[i + 1]) {
      target = args[i + 1];
      i += 1;
      continue;
    }
    if (arg === '--repo-root' && args[i + 1]) {
      repoRoot = args[i + 1];
      i += 1;
      continue;
    }
    if (!arg.startsWith('-') && !target) {
      target = arg;
    }
  }

  return { help: false, target: target || '.', repoRoot };
}

function ensurePackageRoot(repoRoot) {
  const root = repoRoot ? path.resolve(repoRoot) : PACKAGE_ROOT;
  const packageJson = path.join(root, 'package.json');
  if (!fs.existsSync(packageJson)) {
    throw new Error(`package.json not found at ${root}`);
  }
  return root;
}

function ensureTargetDir(targetPath) {
  if (!fs.existsSync(targetPath)) {
    fs.mkdirSync(targetPath, { recursive: true });
    console.log('created target directory');
  }
}

function main() {
  const parsed = parseArgs(process.argv);
  if (parsed.help) {
    printHelp();
    return 0;
  }

  const packageRoot = ensurePackageRoot(parsed.repoRoot);
  const targetDir = path.resolve(parsed.target);
  ensureTargetDir(targetDir);

  console.log(`Packing just-demand for ${targetDir}`);
  const tarballName = execFileSync('npm', ['pack'], {
    cwd: packageRoot,
    encoding: 'utf8',
  }).trim().split('\n').pop();

  const tarballPath = path.join(packageRoot, tarballName);
  try {
    execFileSync('npm', ['install', tarballPath], {
      cwd: targetDir,
      encoding: 'utf8',
    });
  } finally {
    if (fs.existsSync(tarballPath)) {
      fs.unlinkSync(tarballPath);
    }
  }

  console.log(`Installed into ${targetDir}`);
  console.log('Done');
  return 0;
}

try {
  process.exit(main());
} catch (error) {
  console.error(String(error.message || error));
  process.exit(1);
}
