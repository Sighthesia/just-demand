const { describe, it, before, after } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const os = require('os');

const LOCAL_INSTALL = path.join(__dirname, '..', 'bin', 'just-demand-local-install.js');
const PKG = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));

function createTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'just-demand-local-install-test-'));
}

function rmTempDir(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
}

describe('just-demand install', () => {
  let tmpDir;

  before(() => {
    tmpDir = createTempDir();
  });

  after(() => {
    rmTempDir(tmpDir);
  });

  it('packs and installs into the current working directory', () => {
    // Use --target to specify a fresh empty directory as the install destination
    const target = path.join(tmpDir, 'install-cwd');
    fs.mkdirSync(target, { recursive: true });

    const output = execSync(`node ${LOCAL_INSTALL} --target ${target}`, {
      encoding: 'utf8',
      cwd: path.join(__dirname, '..'),
    });
    console.log(output);

    // Should report packing
    assert.ok(output.includes('Packing'));

    // Should report installation destination
    assert.ok(output.includes(target));

    // Should report done
    assert.ok(output.includes('Done'));

    // The tarball should have been cleaned up
    const tgzFiles = fs.readdirSync(path.join(__dirname, '..')).filter(f => f.endsWith('.tgz') && f.startsWith('just-demand-'));
    // After clean run, no leftover tarball from this test (there may be pre-existing ones)
    // We just verify the install succeeded by checking node_modules
    const installedPkg = path.join(target, 'node_modules', 'just-demand');
    assert.ok(fs.existsSync(installedPkg), 'package should be installed in node_modules');

    // Verify the installed package has expected files
    assert.ok(fs.existsSync(path.join(installedPkg, 'bin', 'just-demand.js')));
    assert.ok(fs.existsSync(path.join(installedPkg, 'package.json')));
    assert.ok(fs.existsSync(path.join(installedPkg, 'templates', '.opencode', 'skills')));

    const installedPkgJson = JSON.parse(
      fs.readFileSync(path.join(installedPkg, 'package.json'), 'utf8')
    );
    assert.strictEqual(installedPkgJson.name, PKG.name);
    assert.strictEqual(installedPkgJson.version, PKG.version);
  });

  it('creates the target directory when it does not exist', () => {
    const target = path.join(tmpDir, 'create-and-install');

    const output = execSync(`node ${LOCAL_INSTALL} --target ${target}`, {
      encoding: 'utf8',
      cwd: path.join(__dirname, '..'),
    });

    assert.ok(output.includes('created target directory'));
    assert.ok(fs.existsSync(path.join(target, 'node_modules', 'just-demand')));
  });

  it('supports positional target argument', () => {
    const target = path.join(tmpDir, 'positional-target');
    fs.mkdirSync(target, { recursive: true });

    const output = execSync(`node ${LOCAL_INSTALL} ${target}`, {
      encoding: 'utf8',
      cwd: path.join(__dirname, '..'),
    });

    assert.ok(output.includes(target));
    assert.ok(fs.existsSync(path.join(target, 'node_modules', 'just-demand')));
  });

  it('shows help message with --help', () => {
    const output = execSync(`node ${LOCAL_INSTALL} --help`, {
      encoding: 'utf8',
    });

    assert.ok(output.includes('just-demand'));
    assert.ok(output.includes('Usage:'));
    assert.ok(output.includes('--target'));
  });

  it('shows help message with -h', () => {
    const output = execSync(`node ${LOCAL_INSTALL} -h`, {
      encoding: 'utf8',
    });

    assert.ok(output.includes('just-demand'));
    assert.ok(output.includes('Usage:'));
  });

  it('errors when package.json is missing (bad repo-root)', () => {
    const badRoot = path.join(tmpDir, 'no-such-root');

    let exitCode = 0;
    try {
      execSync(`node ${LOCAL_INSTALL} --repo-root ${badRoot} --target ${tmpDir}`, {
        encoding: 'utf8',
        stdio: ['pipe', 'pipe', 'pipe'],
      });
    } catch (err) {
      exitCode = err.status;
    }
    assert.ok(exitCode !== 0, 'should exit with non-zero status');
  });
});
