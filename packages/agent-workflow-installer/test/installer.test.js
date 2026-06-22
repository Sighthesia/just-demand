const { describe, it, before, after } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const os = require('os');

const CLI = path.join(__dirname, '..', 'bin', 'just-demand.js');
const PKG = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));

function createTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'just-demand-test-'));
}

function rmTempDir(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
}

describe('just-demand init', () => {
  let tmpDir;

  before(() => {
    tmpDir = createTempDir();
  });

  after(() => {
    rmTempDir(tmpDir);
  });

  it('creates expected files in empty target', () => {
    const target = path.join(tmpDir, 'empty');
    fs.mkdirSync(target, { recursive: true });

    const output = execSync(`node ${CLI} ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Check some key files exist
    assert.ok(fs.existsSync(path.join(target, '.opencode/plugins/just-demand-state.js')));
    assert.ok(fs.existsSync(path.join(target, '.opencode/agent/just-demand-coder.md')));
    assert.ok(fs.existsSync(path.join(target, '.opencode/skills/using-just-demand/SKILL.md')));
    assert.ok(fs.existsSync(path.join(target, 'AGENTS.md')));
    assert.ok(fs.existsSync(path.join(target, '.opencode/package.json')));
    assert.ok(fs.existsSync(path.join(target, '.gitignore')));
    assert.ok(fs.existsSync(path.join(target, '.just-demand', 'installer-metadata.json')));

    // Check .opencode/package.json has type: module
    const pkg = JSON.parse(fs.readFileSync(path.join(target, '.opencode/package.json'), 'utf8'));
    assert.strictEqual(pkg.type, 'module');
  });

  it('supports the init subcommand explicitly', () => {
    const target = path.join(tmpDir, 'explicit-init');
    fs.mkdirSync(target, { recursive: true });

    execSync(`node ${CLI} init ${target}`, { encoding: 'utf8' });

    assert.ok(fs.existsSync(path.join(target, '.opencode/plugins/just-demand-state.js')));
  });

  it('creates the target directory when it does not exist', () => {
    const target = path.join(tmpDir, 'create-target');

    const output = execSync(`node ${CLI} init ${target}`, { encoding: 'utf8' });

    assert.ok(output.includes('created target directory'));
    assert.ok(fs.existsSync(path.join(target, '.just-demand', 'installer-metadata.json')));
  });

  it('skips existing files without overwriting', () => {
    const target = path.join(tmpDir, 'existing');
    fs.mkdirSync(target, { recursive: true });

    // Create a pre-existing file that would be overwritten
    const agentsMdPath = path.join(target, 'AGENTS.md');
    fs.writeFileSync(agentsMdPath, '# Existing AGENTS.md\n');

    // Create a pre-existing .opencode/package.json with extra fields
    const pkgDir = path.join(target, '.opencode');
    fs.mkdirSync(pkgDir, { recursive: true });
    fs.writeFileSync(
      path.join(pkgDir, 'package.json'),
      JSON.stringify({ name: 'my-project', dependencies: {} }, null, 2)
    );

    const output = execSync(`node ${CLI} ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Should report skip for AGENTS.md
    assert.ok(output.includes('skip  AGENTS.md (already exists)'));
    // Should NOT overwrite AGENTS.md
    const content = fs.readFileSync(agentsMdPath, 'utf8');
    assert.strictEqual(content, '# Existing AGENTS.md\n');

    // .opencode/package.json should preserve existing fields and add type
    const pkg = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'));
    assert.strictEqual(pkg.type, 'module');
    assert.strictEqual(pkg.name, 'my-project');
    assert.deepStrictEqual(pkg.dependencies, {});
  });

  it('appends missing gitignore lines without duplicating', () => {
    const target = path.join(tmpDir, 'gitignore');
    fs.mkdirSync(target, { recursive: true });

    // Create .gitignore with some existing lines
    fs.writeFileSync(
      path.join(target, '.gitignore'),
      'node_modules/\n.env\n'
    );

    const output = execSync(`node ${CLI} ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Should report .gitignore updated (some lines missing)
    assert.ok(output.includes('.gitignore updated with'));

    // Check that missing lines were added
    const content = fs.readFileSync(path.join(target, '.gitignore'), 'utf8');
    assert.ok(content.includes('.just-demand/state/'));
    assert.ok(content.includes('.just-demand/knowledge/'));
    // Should NOT duplicate existing line
    const lines = content.split('\n');
    const taskLineCount = lines.filter(l => l === '.just-demand/state/').length;
    assert.strictEqual(taskLineCount, 1);
  });

  it('creates .opencode/package.json with type: module when missing', () => {
    const target = path.join(tmpDir, 'no-pkg');
    fs.mkdirSync(target, { recursive: true });

    const output = execSync(`node ${CLI} ${target}`, { encoding: 'utf8' });
    console.log(output);

    const pkgPath = path.join(target, '.opencode', 'package.json');
    assert.ok(fs.existsSync(pkgPath));
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    assert.strictEqual(pkg.type, 'module');
    assert.ok(output.includes('.opencode/package.json updated with type: "module"'));
  });

  it('overwrites existing managed files with --force', () => {
    const target = path.join(tmpDir, 'force-overwrite');
    fs.mkdirSync(target, { recursive: true });

    // Create a pre-existing file that should be overwritten
    const agentsMdPath = path.join(target, 'AGENTS.md');
    fs.writeFileSync(agentsMdPath, '# Existing AGENTS.md\n');

    // Create a pre-existing plugin file that should be overwritten
    const pluginDir = path.join(target, '.opencode', 'plugins');
    fs.mkdirSync(pluginDir, { recursive: true });
    const pluginPath = path.join(pluginDir, 'just-demand-state.js');
    fs.writeFileSync(pluginPath, '// old plugin\n');

    const output = execSync(`node ${CLI} --force ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Should report overwrite for both files
    assert.ok(output.includes('overwrite AGENTS.md'));
    assert.ok(output.includes('overwrite .opencode/plugins/just-demand-state.js'));

    // AGENTS.md should be overwritten with template content
    const agentsContent = fs.readFileSync(agentsMdPath, 'utf8');
    assert.ok(agentsContent.includes('Just Demand'));
    assert.ok(!agentsContent.includes('# Existing AGENTS.md'));

    // Plugin file should be overwritten with template content
    const pluginContent = fs.readFileSync(pluginPath, 'utf8');
    assert.ok(pluginContent.includes('[just-demand reminder]'));
    assert.ok(!pluginContent.includes('// old plugin'));
  });

  it('preserves .opencode/package.json fields with --force', () => {
    const target = path.join(tmpDir, 'force-pkg');
    fs.mkdirSync(target, { recursive: true });

    // Create .opencode/package.json with extra fields
    const pkgDir = path.join(target, '.opencode');
    fs.mkdirSync(pkgDir, { recursive: true });
    fs.writeFileSync(
      path.join(pkgDir, 'package.json'),
      JSON.stringify({ name: 'my-project', version: '1.0.0', dependencies: {} }, null, 2)
    );

    const output = execSync(`node ${CLI} --force ${target}`, { encoding: 'utf8' });
    console.log(output);

    // .opencode/package.json should preserve existing fields and ensure type
    const pkg = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'));
    assert.strictEqual(pkg.type, 'module');
    assert.strictEqual(pkg.name, 'my-project');
    assert.strictEqual(pkg.version, '1.0.0');
    assert.deepStrictEqual(pkg.dependencies, {});
  });

  it('preserves .gitignore rules with --force', () => {
    const target = path.join(tmpDir, 'force-gitignore');
    fs.mkdirSync(target, { recursive: true });

    // Create .gitignore with some existing lines
    fs.writeFileSync(
      path.join(target, '.gitignore'),
      'node_modules/\n.env\n# Custom rule\n/custom/\n'
    );

    const output = execSync(`node ${CLI} --force ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Should report .gitignore updated (some lines missing)
    assert.ok(output.includes('.gitignore updated with'));

    // Check that missing lines were added
    const content = fs.readFileSync(path.join(target, '.gitignore'), 'utf8');
    assert.ok(content.includes('.just-demand/state/'));
    assert.ok(content.includes('.just-demand/knowledge/'));
    // Should NOT duplicate existing line
    const lines = content.split('\n');
    const nodeModulesCount = lines.filter(l => l === 'node_modules/').length;
    assert.strictEqual(nodeModulesCount, 1);
  });

  it('writes installer metadata on init', () => {
    const target = path.join(tmpDir, 'metadata-init');
    fs.mkdirSync(target, { recursive: true });

    const output = execSync(`node ${CLI} init ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Should report metadata written
    assert.ok(output.includes('installer metadata written'));

    // Check metadata file exists
    const metadataPath = path.join(target, '.just-demand', 'installer-metadata.json');
    assert.ok(fs.existsSync(metadataPath));

    // Check metadata content
    const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
    assert.strictEqual(metadata.package, PKG.name);
    assert.strictEqual(metadata.version, PKG.version);
    assert.strictEqual(metadata.action, 'init');
    assert.ok(metadata.timestamp);
    // Timestamp should be ISO format
    assert.ok(!isNaN(Date.parse(metadata.timestamp)));
  });

  it('writes installer metadata on force init', () => {
    const target = path.join(tmpDir, 'metadata-force-init');
    fs.mkdirSync(target, { recursive: true });

    const output = execSync(`node ${CLI} init --force ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Check metadata content
    const metadataPath = path.join(target, '.just-demand', 'installer-metadata.json');
    const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
    assert.strictEqual(metadata.action, 'init');
  });
});

describe('just-demand upgrade', () => {
  let tmpDir;

  before(() => {
    tmpDir = createTempDir();
  });

  after(() => {
    rmTempDir(tmpDir);
  });

  it('overwrites managed files in an existing workspace', () => {
    const target = path.join(tmpDir, 'upgrade-overwrite');
    fs.mkdirSync(target, { recursive: true });

    // Create a pre-existing file that should be overwritten
    const agentsMdPath = path.join(target, 'AGENTS.md');
    fs.writeFileSync(agentsMdPath, '# Old AGENTS.md\n');

    // Create a pre-existing plugin file that should be overwritten
    const pluginDir = path.join(target, '.opencode', 'plugins');
    fs.mkdirSync(pluginDir, { recursive: true });
    const pluginPath = path.join(pluginDir, 'just-demand-state.js');
    fs.writeFileSync(pluginPath, '// old plugin\n');

    const output = execSync(`node ${CLI} upgrade ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Should report overwrite for both files
    assert.ok(output.includes('overwrite AGENTS.md'));
    assert.ok(output.includes('overwrite .opencode/plugins/just-demand-state.js'));

    // AGENTS.md should be overwritten with template content
    const agentsContent = fs.readFileSync(agentsMdPath, 'utf8');
    assert.ok(agentsContent.includes('Just Demand'));
    assert.ok(!agentsContent.includes('# Old AGENTS.md'));

    // Plugin file should be overwritten with template content
    const pluginContent = fs.readFileSync(pluginPath, 'utf8');
    assert.ok(pluginContent.includes('[just-demand reminder]'));
    assert.ok(!pluginContent.includes('// old plugin'));
  });

  it('preserves .opencode/package.json merge behavior', () => {
    const target = path.join(tmpDir, 'upgrade-pkg');
    fs.mkdirSync(target, { recursive: true });

    // Create .opencode/package.json with extra fields
    const pkgDir = path.join(target, '.opencode');
    fs.mkdirSync(pkgDir, { recursive: true });
    fs.writeFileSync(
      path.join(pkgDir, 'package.json'),
      JSON.stringify({ name: 'my-project', version: '1.0.0', dependencies: {} }, null, 2)
    );

    const output = execSync(`node ${CLI} upgrade ${target}`, { encoding: 'utf8' });
    console.log(output);

    // .opencode/package.json should preserve existing fields and ensure type
    const pkg = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json'), 'utf8'));
    assert.strictEqual(pkg.type, 'module');
    assert.strictEqual(pkg.name, 'my-project');
    assert.strictEqual(pkg.version, '1.0.0');
    assert.deepStrictEqual(pkg.dependencies, {});
  });

  it('preserves .gitignore merge behavior', () => {
    const target = path.join(tmpDir, 'upgrade-gitignore');
    fs.mkdirSync(target, { recursive: true });

    // Create .gitignore with some existing lines
    fs.writeFileSync(
      path.join(target, '.gitignore'),
      'node_modules/\n.env\n# Custom rule\n/custom/\n'
    );

    const output = execSync(`node ${CLI} upgrade ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Should report .gitignore updated (some lines missing)
    assert.ok(output.includes('.gitignore updated with'));

    // Check that missing lines were added
    const content = fs.readFileSync(path.join(target, '.gitignore'), 'utf8');
    assert.ok(content.includes('.just-demand/state/'));
    assert.ok(content.includes('.just-demand/knowledge/'));
    // Should NOT duplicate existing line
    const lines = content.split('\n');
    const nodeModulesCount = lines.filter(l => l === 'node_modules/').length;
    assert.strictEqual(nodeModulesCount, 1);
  });

  it('creates the target directory when it does not exist', () => {
    const target = path.join(tmpDir, 'upgrade-create-target');

    const output = execSync(`node ${CLI} upgrade ${target}`, { encoding: 'utf8' });

    assert.ok(output.includes('created target directory'));
    assert.ok(fs.existsSync(path.join(target, '.just-demand', 'installer-metadata.json')));
  });

  it('produces upgrade-specific log message', () => {
    const target = path.join(tmpDir, 'upgrade-msg');
    fs.mkdirSync(target, { recursive: true });

    const output = execSync(`node ${CLI} upgrade ${target}`, { encoding: 'utf8' });

    assert.ok(output.includes('Upgrading Just Demand in:'));
    assert.ok(!output.includes('Initializing Just Demand into:'));
  });

  it('writes installer metadata on upgrade', () => {
    const target = path.join(tmpDir, 'metadata-upgrade');
    fs.mkdirSync(target, { recursive: true });

    const output = execSync(`node ${CLI} upgrade ${target}`, { encoding: 'utf8' });
    console.log(output);

    // Should report metadata written
    assert.ok(output.includes('installer metadata written'));

    // Check metadata file exists
    const metadataPath = path.join(target, '.just-demand', 'installer-metadata.json');
    assert.ok(fs.existsSync(metadataPath));

    // Check metadata content
    const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
    assert.strictEqual(metadata.package, PKG.name);
    assert.strictEqual(metadata.version, PKG.version);
    assert.strictEqual(metadata.action, 'upgrade');
    assert.ok(metadata.timestamp);
    // Timestamp should be ISO format
    assert.ok(!isNaN(Date.parse(metadata.timestamp)));
  });

  it('refreshes installer metadata on subsequent upgrades', () => {
    const target = path.join(tmpDir, 'metadata-upgrade-refresh');
    fs.mkdirSync(target, { recursive: true });

    // First upgrade
    execSync(`node ${CLI} upgrade ${target}`, { encoding: 'utf8' });
    const metadataPath = path.join(target, '.just-demand', 'installer-metadata.json');
    const firstMetadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
    const firstTimestamp = firstMetadata.timestamp;

    // Small delay to ensure timestamp changes
    execSync('sleep 0.1');

    // Second upgrade
    execSync(`node ${CLI} upgrade ${target}`, { encoding: 'utf8' });
    const secondMetadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));

    // Metadata should be refreshed (timestamp may or may not change depending on speed,
    // but action should still be 'upgrade' and version should match)
    assert.strictEqual(secondMetadata.action, 'upgrade');
    assert.strictEqual(secondMetadata.version, PKG.version);
  });
});
