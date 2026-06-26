import json
import os
import tempfile
import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / ".just-demand" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from install import (
    init_project,
    install_opencode_global,
    update_opencode_global,
    doctor_opencode_global,
    uninstall_opencode_global,
    get_preferred_bin_dir,
    get_repo_root,
    get_repo_opencode_dir,
    load_manifest,
    save_manifest,
    deploy_config_file,
    sync_public_skills,
    DEPLOYED_FILES,
)


class InstallCoreTests(unittest.TestCase):
    def test_init_project_creates_just_demand_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = init_project(root)

            self.assertEqual(result["status"], "success")
            self.assertIn("stored local state only", result["message"])
            self.assertTrue((root / ".just-demand").exists())
            self.assertTrue((root / ".just-demand" / "state" / "state.json").exists())
            self.assertTrue((root / ".just-demand" / "knowledge").is_dir())
            self.assertFalse((root / ".just-demand" / "knowledge" / "memory.md").exists())

    def test_init_project_keeps_global_cli_entrypoints_outside_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            init_project(root)

            self.assertFalse((root / ".just-demand" / "scripts" / "install.py").exists())

    def test_init_project_creates_only_project_workflow_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)

            # init creates .just-demand and .gitignore
            files = [path.name for path in root.iterdir()]
            self.assertIn(".just-demand", files)
            self.assertIn(".gitignore", files)
    
    def test_init_project_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result1 = init_project(root)
            result2 = init_project(root)
            
            self.assertEqual(result1["status"], "success")
            self.assertEqual(result2["status"], "success")
            # Should not fail on second run

    def test_init_project_is_idempotent_and_keeps_workspace_runtime_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)

            result = init_project(root)

            self.assertEqual(result["status"], "success")
            self.assertFalse((root / ".just-demand" / "scripts").exists())

    def test_split_project_root_accepts_project_before_command(self):
        from install import split_project_root

        project_root, cmd_args = split_project_root(["/tmp/demo", "init"])

        self.assertEqual(project_root, Path("/tmp/demo"))
        self.assertEqual(cmd_args, ["init"])

    def test_split_project_root_leaves_normal_command_form_unchanged(self):
        from install import split_project_root

        project_root, cmd_args = split_project_root(["init", "/tmp/demo"])

        self.assertIsNone(project_root)
        self.assertEqual(cmd_args, ["init", "/tmp/demo"])

    def test_sync_public_skills_mirrors_runtime_skills_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / ".opencode" / "skills" / "example"
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("example skill\n", encoding="utf-8")

            result = sync_public_skills(root)

            self.assertEqual(result["files_copied"], 1)
            self.assertTrue((root / ".agents" / "skills" / "example" / "SKILL.md").exists())
            self.assertEqual(
                (root / ".agents" / "skills" / "example" / "SKILL.md").read_text(encoding="utf-8"),
                "example skill\n",
            )
    
    def test_get_repo_root_returns_path(self):
        repo_root = get_repo_root()
        self.assertTrue(repo_root.exists())
        self.assertTrue((repo_root / ".just-demand").exists())
    
    def test_get_repo_opencode_dir_returns_path(self):
        opencode_dir = get_repo_opencode_dir()
        self.assertTrue(opencode_dir.exists())
        self.assertTrue(opencode_dir.is_dir())
    
    def test_load_manifest_returns_empty_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            manifest = load_manifest(config_root)
            self.assertEqual(manifest["installed_files"], {})
            self.assertEqual(manifest["version"], "1.0")
    
    def test_save_and_load_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            manifest = {
                "installed_files": {"plugins/test.js": {"source": "/source", "checksum": "123"}},
                "version": "1.0"
            }
            save_manifest(config_root, manifest)
            
            loaded = load_manifest(config_root)
            self.assertEqual(loaded, manifest)

    def test_load_manifest_prunes_stale_workflow_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            (config_root / ".just-demand-manifest.json").write_text(
                json.dumps(
                    {
                        "installed_files": {
                            "plugins/just-demand-lib.js": {"source": "/source", "checksum": "123"},
                            "agents/workflow-research.md": {"source": "/old", "checksum": "456"},
                            "skills/workflow-intake/SKILL.md": {"source": "/old", "checksum": "789"},
                        },
                        "version": "1.0",
                    }
                ),
                encoding="utf-8",
            )

            loaded = load_manifest(config_root)

            self.assertIn("plugins/just-demand-lib.js", loaded["installed_files"])
            self.assertNotIn("agents/workflow-research.md", loaded["installed_files"])
            self.assertNotIn("skills/workflow-intake/SKILL.md", loaded["installed_files"])
    
    def test_doctor_reports_global_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            project_root = Path(tmp) / "project"
            project_root.mkdir()
            
            result = doctor_opencode_global(config_root, project_root)
            
            self.assertIn("global", result)
            self.assertIn("project", result)
            self.assertIn("healthy", result)
            self.assertFalse(result["healthy"])  # No installation yet
    
    def test_doctor_reports_project_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            
            result = doctor_opencode_global(root, root)
            
            self.assertTrue(result["project"]["just_demand_dir_exists"])
            self.assertTrue(result["project"]["workspace_state_exists"])
            self.assertNotIn("workflow", json.dumps(result["global"]))
    
    def test_uninstall_removes_managed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            
            # Create a fake manifest
            manifest = {
                "installed_files": {
                    "plugins/test.js": {"source": "/source", "checksum": "123"},
                    "package.json": {"source": "/source", "checksum": "456"},
                },
                "version": "1.0"
            }
            save_manifest(config_root, manifest)
            
            # Create the files
            (config_root / "plugins").mkdir()
            (config_root / "plugins" / "test.js").write_text("test")
            (config_root / "package.json").write_text("{}")
            
            # Also create an unrelated file
            (config_root / "unrelated.txt").write_text("should not be removed")
            
            result = uninstall_opencode_global(config_root)
            
            self.assertEqual(result["status"], "success")
            # These files should be removed because they're in the manifest
            self.assertIn("plugins/test.js", result["removed_files"])
            self.assertIn("package.json", result["removed_files"])
            # Unrelated file should not be removed
            self.assertTrue((config_root / "unrelated.txt").exists())

    def test_deploy_config_file_skips_existing_unmanaged_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            source = config_root / "source-package.json"
            target = config_root / "package.json"
            source.write_text('{"type":"module"}\n', encoding="utf-8")
            target.write_text('not-json\n', encoding="utf-8")
            manifest = {"installed_files": {}, "version": "1.0"}

            copied, warning, entry = deploy_config_file(source, target, manifest, config_root)

            self.assertFalse(copied)
            self.assertIn("package.json", warning)
            self.assertIsNone(entry)
            self.assertEqual(target.read_text(encoding="utf-8"), 'not-json\n')
            self.assertNotIn("package.json", manifest["installed_files"])

    def test_deploy_config_file_merges_existing_unmanaged_package_json_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            source = config_root / "source-package.json"
            target = config_root / "package.json"
            source.write_text('{"type":"module"}\n', encoding="utf-8")
            target.write_text('{"type":"commonjs","dependencies":{"keep":"1.0.0"}}\n', encoding="utf-8")
            manifest = {"installed_files": {}, "version": "1.0"}

            copied, warning, entry = deploy_config_file(source, target, manifest, config_root)

            self.assertTrue(copied)
            self.assertIsNone(warning)
            self.assertIsNotNone(entry)
            merged = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(merged["type"], "module")
            self.assertEqual(merged["dependencies"], {"keep": "1.0.0"})
            self.assertIn("package.json", manifest["installed_files"])
            self.assertTrue(manifest["installed_files"]["package.json"]["preserve_on_uninstall"])
    
    def test_deployed_files_constant(self):
        self.assertIn("plugins", DEPLOYED_FILES)
        self.assertIn("agents", DEPLOYED_FILES)
        self.assertIn("skills", DEPLOYED_FILES)
        self.assertIn("config", DEPLOYED_FILES)
        
        # Check that all expected files are listed
        self.assertIn("just-demand-lib.js", DEPLOYED_FILES["plugins"])
        self.assertIn("just-demand-session-start.js", DEPLOYED_FILES["plugins"])
        self.assertIn("just-demand-state.js", DEPLOYED_FILES["plugins"])
        self.assertIn("just-demand-subagent-context.js", DEPLOYED_FILES["plugins"])
        
        self.assertIn("just-demand-advisor.md", DEPLOYED_FILES["agents"])
        self.assertIn("just-demand-coder.md", DEPLOYED_FILES["agents"])
        self.assertIn("just-demand-researcher.md", DEPLOYED_FILES["agents"])
        self.assertIn("just-demand-tester.md", DEPLOYED_FILES["agents"])
        self.assertNotIn("just-demand-docs.md", DEPLOYED_FILES["agents"])
        
        self.assertIn("using-just-demand", DEPLOYED_FILES["skills"])
        self.assertIn("socratic-clarification", DEPLOYED_FILES["skills"])
        self.assertLess(DEPLOYED_FILES["skills"].index("using-just-demand"), DEPLOYED_FILES["skills"].index("socratic-clarification"))
        self.assertIn("just-demand-execution", DEPLOYED_FILES["skills"])
        self.assertIn("just-demand-intake", DEPLOYED_FILES["skills"])
        self.assertIn("capture-lessons", DEPLOYED_FILES["skills"])
        self.assertIn("just-demand-verification", DEPLOYED_FILES["skills"])


class InstallIntegrationTests(unittest.TestCase):
    def test_install_opencode_global_deploys_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            result = install_opencode_global(config_root)
            
            self.assertEqual(result["status"], "success")
            self.assertGreater(result["results"]["total_deployed"], 0)
            
            # Check that files were deployed
            self.assertTrue((config_root / "plugins" / "just-demand-lib.js").exists())
            self.assertTrue((config_root / "agents" / "just-demand-coder.md").exists())
            self.assertTrue((config_root / "skills" / "using-just-demand").exists())
            self.assertTrue((config_root / "package.json").exists())

    def test_install_opencode_global_deploys_expected_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            install_opencode_global(config_root)

            for plugin in DEPLOYED_FILES["plugins"]:
                with self.subTest(plugin=plugin):
                    self.assertTrue((config_root / "plugins" / plugin).exists())
            for agent in DEPLOYED_FILES["agents"]:
                with self.subTest(agent=agent):
                    self.assertTrue((config_root / "agents" / agent).exists())
            for skill in DEPLOYED_FILES["skills"]:
                with self.subTest(skill=skill):
                    self.assertTrue((config_root / "skills" / skill / "SKILL.md").exists())

    def test_install_opencode_global_removes_stale_managed_agent_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            stale_agent = config_root / "agents" / "just-demand-docs.md"
            stale_agent.parent.mkdir(parents=True)
            stale_agent.write_text("legacy docs agent\n", encoding="utf-8")
            save_manifest(
                config_root,
                {
                    "version": "1.0",
                    "installed_files": {
                        "agents/just-demand-docs.md": {"source": "legacy"},
                    },
                },
            )

            result = install_opencode_global(config_root)

            self.assertFalse(stale_agent.exists())
            self.assertIn("agents/just-demand-docs.md", result["results"]["stale_removed"])
            manifest = load_manifest(config_root)
            self.assertNotIn("agents/just-demand-docs.md", manifest["installed_files"])
            self.assertTrue((config_root / "agents" / "just-demand-advisor.md").exists())

    def test_install_opencode_global_deploys_socratic_clarification_before_intake(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            install_opencode_global(config_root)

            deployed_skills = DEPLOYED_FILES["skills"]
            self.assertLess(deployed_skills.index("using-just-demand"), deployed_skills.index("socratic-clarification"))
            self.assertLess(deployed_skills.index("socratic-clarification"), deployed_skills.index("just-demand-intake"))
            self.assertTrue((config_root / "skills" / "socratic-clarification" / "SKILL.md").exists())

    def test_install_opencode_global_deploys_skill_guidance_for_routing_reset_and_subagent_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            install_opencode_global(config_root)

            using_skill = (config_root / "skills" / "using-just-demand" / "SKILL.md").read_text(encoding="utf-8")
            socratic_skill = (config_root / "skills" / "socratic-clarification" / "SKILL.md").read_text(encoding="utf-8")
            execution_skill = (config_root / "skills" / "just-demand-execution" / "SKILL.md").read_text(encoding="utf-8")
            intake_skill = (config_root / "skills" / "just-demand-intake" / "SKILL.md").read_text(encoding="utf-8")
            verification_skill = (config_root / "skills" / "just-demand-verification" / "SKILL.md").read_text(encoding="utf-8")

            self.assertIn("`socratic-clarification` - always loaded second", using_skill)
            self.assertIn("follow-up turns that pivot from ordinary Q&A into concrete work", using_skill)
            self.assertIn("analysis, diagnosis, tuning, experiment review, or root-cause replies", using_skill)
            self.assertIn("reset the problem model", socratic_skill)
            self.assertIn("retry now", using_skill)
            self.assertIn("skip one turn", using_skill)
            self.assertIn("retry now or skip one turn", execution_skill)
            self.assertIn("analysis or diagnosis updates, lead with the result and concise status", execution_skill)
            self.assertIn("analysis, diagnosis, tuning, experiment-review, or root-cause conclusions", verification_skill)
            self.assertIn("socratic-clarification", intake_skill)
            self.assertIn("Do not outrank `socratic-clarification`", intake_skill)

    def test_install_opencode_global_deploys_expected_agent_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            install_opencode_global(config_root)

            coder_agent = (config_root / "agents" / "just-demand-coder.md").read_text(encoding="utf-8")
            tester_agent = (config_root / "agents" / "just-demand-tester.md").read_text(encoding="utf-8")
            advisor_agent = (config_root / "agents" / "just-demand-advisor.md").read_text(encoding="utf-8")
            researcher_agent = (config_root / "agents" / "just-demand-researcher.md").read_text(encoding="utf-8")

            for content in (coder_agent, tester_agent):
                self.assertIn('bash: allow', content)
                self.assertIn('## Workflow Loop', content)
                self.assertIn('## Stop / Escalation Rules', content)
                self.assertIn('task: deny', content)

            for content in (researcher_agent, advisor_agent):
                self.assertIn('read: allow', content)
                self.assertIn('glob: allow', content)
                self.assertIn('grep: allow', content)
                self.assertIn('bash: deny', content)
                self.assertIn('write: deny', content)
                self.assertIn('edit: deny', content)
            self.assertIn('Prefer dedicated read-only tools first', researcher_agent)
            self.assertIn('fresh context', advisor_agent)
            self.assertIn('does **not** replace the main workflow owner', advisor_agent)

            # Output contract coverage
            self.assertIn('## Output Contract', researcher_agent)
            self.assertIn('**Key findings**', researcher_agent)
            self.assertIn('## Output Contract', advisor_agent)
            self.assertIn('**Recommendation**', advisor_agent)
            self.assertIn('## Output Contract', coder_agent)
            self.assertIn('**Files changed**', coder_agent)
            self.assertIn('**Concerns**', coder_agent)
            self.assertIn('## Output Contract', tester_agent)
            self.assertIn('**Findings**', tester_agent)
            self.assertIn('**Residual risk**', tester_agent)
    
    def test_install_opencode_global_creates_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            install_opencode_global(config_root)

            manifest_path = config_root / ".just-demand-manifest.json"
            self.assertTrue(manifest_path.exists())

            manifest = load_manifest(config_root)
            self.assertGreater(len(manifest["installed_files"]), 0)

    def test_install_opencode_global_creates_path_entry_in_preferred_bin_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "config"
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()

            original_path = os.environ.get("PATH", "")
            original_xdg_bin = os.environ.get("XDG_BIN_HOME")
            try:
                os.environ["PATH"] = str(bin_dir)
                os.environ.pop("XDG_BIN_HOME", None)

                result = install_opencode_global(config_root)

                entry = result["results"]["path_entry"]
                self.assertEqual(Path(entry["path"]).parent, bin_dir)
                self.assertTrue(Path(entry["path"]).exists())
                self.assertTrue(entry["on_path"])
                self.assertIn("PATH entry", result["message"])
                self.assertIn("path_entry", result["results"])
            finally:
                os.environ["PATH"] = original_path
                if original_xdg_bin is None:
                    os.environ.pop("XDG_BIN_HOME", None)
                else:
                    os.environ["XDG_BIN_HOME"] = original_xdg_bin

    def test_uninstall_removes_managed_path_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "config"
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()

            original_path = os.environ.get("PATH", "")
            original_xdg_bin = os.environ.get("XDG_BIN_HOME")
            try:
                os.environ["PATH"] = str(bin_dir)
                os.environ.pop("XDG_BIN_HOME", None)

                install_result = install_opencode_global(config_root)
                entry_path = Path(install_result["results"]["path_entry"]["path"])
                self.assertTrue(entry_path.exists())

                uninstall_result = uninstall_opencode_global(config_root)

                self.assertEqual(uninstall_result["status"], "success")
                self.assertFalse(entry_path.exists())
                self.assertIn(str(entry_path), uninstall_result["removed_files"])
                self.assertEqual(uninstall_result["path_entry_removed"], str(entry_path))
            finally:
                os.environ["PATH"] = original_path
                if original_xdg_bin is None:
                    os.environ.pop("XDG_BIN_HOME", None)
                else:
                    os.environ["XDG_BIN_HOME"] = original_xdg_bin

    def test_install_preserves_existing_unmanaged_path_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "config"
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            existing_entry = bin_dir / "just-demand"
            existing_entry.write_text("#!/bin/sh\necho custom\n", encoding="utf-8")

            original_path = os.environ.get("PATH", "")
            original_xdg_bin = os.environ.get("XDG_BIN_HOME")
            try:
                os.environ["PATH"] = str(bin_dir)
                os.environ.pop("XDG_BIN_HOME", None)

                result = install_opencode_global(config_root)

                self.assertIn("Skipped existing unmanaged PATH entry", " ".join(result["results"]["warnings"]))
                self.assertEqual(existing_entry.read_text(encoding="utf-8"), "#!/bin/sh\necho custom\n")
                self.assertNotIn("path_entry", load_manifest(config_root).get("installed_files", {}))
            finally:
                os.environ["PATH"] = original_path
                if original_xdg_bin is None:
                    os.environ.pop("XDG_BIN_HOME", None)
                else:
                    os.environ["XDG_BIN_HOME"] = original_xdg_bin
    
    def test_update_opencode_global_refreshes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            
            # Initial install
            result1 = install_opencode_global(config_root)
            self.assertEqual(result1["status"], "success")
            
            # Update
            result2 = update_opencode_global(config_root)
            self.assertEqual(result2["status"], "success")

    def test_update_opencode_global_restores_changed_managed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            target = config_root / "plugins" / "just-demand-lib.js"
            source = REPO_ROOT / ".opencode" / "plugins" / "just-demand-lib.js"

            install_opencode_global(config_root)
            target.write_text("stale", encoding="utf-8")
            result = update_opencode_global(config_root)

            self.assertEqual(result["status"], "success")
            self.assertEqual(target.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
    
    def test_uninstall_opencode_global_removes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            
            # Install first
            install_opencode_global(config_root)
            
            # Verify files exist
            self.assertTrue((config_root / "plugins" / "just-demand-lib.js").exists())
            
            # Uninstall
            result = uninstall_opencode_global(config_root)
            self.assertEqual(result["status"], "success")
            
            # Verify files removed
            self.assertFalse((config_root / "plugins" / "just-demand-lib.js").exists())
            self.assertFalse((config_root / ".just-demand-manifest.json").exists())
    
    def test_install_with_custom_config_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp) / "custom" / "opencode"
            result = install_opencode_global(config_root)
            
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["config_root"], str(config_root))

    def test_install_merges_existing_unmanaged_package_json_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            package_json = config_root / "package.json"
            package_json.write_text('{"type":"commonjs","dependencies":{"keep":"1.0.0"}}\n', encoding="utf-8")
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()

            original_path = os.environ.get("PATH", "")
            original_xdg_bin = os.environ.get("XDG_BIN_HOME")
            try:
                os.environ["PATH"] = str(bin_dir)
                os.environ.pop("XDG_BIN_HOME", None)

                result = install_opencode_global(config_root)
                manifest = load_manifest(config_root)

                self.assertEqual(result["status"], "success")
                merged = json.loads(package_json.read_text(encoding="utf-8"))
                self.assertEqual(merged["type"], "module")
                self.assertEqual(merged["dependencies"], {"keep": "1.0.0"})
                self.assertIn("package.json", manifest["installed_files"])
                self.assertFalse(result["results"]["warnings"])
            finally:
                os.environ["PATH"] = original_path
                if original_xdg_bin is None:
                    os.environ.pop("XDG_BIN_HOME", None)
                else:
                    os.environ["XDG_BIN_HOME"] = original_xdg_bin

    def test_uninstall_preserves_existing_unmanaged_package_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            package_json = config_root / "package.json"
            package_json.write_text('{"type":"commonjs","dependencies":{"keep":"1.0.0"}}\n', encoding="utf-8")

            install_opencode_global(config_root)
            uninstall_opencode_global(config_root)

            self.assertTrue(package_json.exists())
            merged = json.loads(package_json.read_text(encoding="utf-8"))
            self.assertEqual(merged["type"], "module")
            self.assertEqual(merged["dependencies"], {"keep": "1.0.0"})


class InstallCLITests(unittest.TestCase):
    def test_cli_init(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "init"],
                text=True,
                capture_output=True,
                check=True,
            )
            # Check for success indicators in human-readable output
            self.assertIn("✓", result.stdout)
            self.assertTrue((root / ".just-demand").exists())
            self.assertTrue((root / ".just-demand" / "state" / "state.json").exists())
    
    def test_cli_install_requires_flags(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), "install", "--config-root", str(config_root)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
    
    def test_cli_install_opencode_global(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), "install", "--opencode", "--global", "--config-root", str(config_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            # Check for success indicators in human-readable output
            self.assertIn("✓", result.stdout)
            self.assertIn("Diff summary:", result.stdout)
            self.assertTrue((config_root / "plugins" / "just-demand-lib.js").exists())
    
    def test_cli_update_opencode_global(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            script = REPO_ROOT / "just-demand"
            
            # Install first
            subprocess.run(
                [sys.executable, str(script), "install", "--opencode", "--global", "--config-root", str(config_root)],
                text=True,
                capture_output=True,
                check=True,
            )

            # Change a managed file so update produces diff stats
            managed = config_root / "plugins" / "just-demand-lib.js"
            managed.write_text("stale\n", encoding="utf-8")
            
            # Update
            result = subprocess.run(
                [sys.executable, str(script), "update", "--opencode", "--global", "--config-root", str(config_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            # Check for success indicators in human-readable output
            self.assertIn("✓", result.stdout)
            self.assertIn("Diff summary:", result.stdout)

    def test_cli_doctor(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "doctor"],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertIn("global", payload)
            self.assertIn("project", payload)
            self.assertTrue(payload["project"]["just_demand_dir_exists"])
    
    def test_cli_uninstall_opencode_global(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            script = REPO_ROOT / "just-demand"
            
            # Install first
            subprocess.run(
                [sys.executable, str(script), "install", "--opencode", "--global", "--config-root", str(config_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            
            # Uninstall
            result = subprocess.run(
                [sys.executable, str(script), "uninstall", "--opencode", "--global", "--config-root", str(config_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "success")
            self.assertFalse((config_root / "plugins" / "just-demand-lib.js").exists())


if __name__ == "__main__":
    unittest.main()
