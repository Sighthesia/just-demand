import json
import tempfile
import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / ".just-demand" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from install import (
    sync_initialized_workspaces,
    init_project,
    install_opencode_global,
    update_opencode_global,
    doctor_opencode_global,
    uninstall_opencode_global,
    get_repo_root,
    get_repo_opencode_dir,
    load_manifest,
    save_manifest,
    deploy_config_file,
    DEPLOYED_FILES,
)


class InstallCoreTests(unittest.TestCase):
    def test_init_project_creates_just_demand_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = init_project(root)
            
            self.assertEqual(result["status"], "success")
            self.assertTrue((root / ".just-demand").exists())
            self.assertTrue((root / ".just-demand" / "workspace" / "state.json").exists())
            self.assertTrue((root / ".just-demand" / "workspace" / "preferences.md").exists())
            self.assertTrue((root / ".just-demand" / "scripts" / "task.py").exists())
            self.assertTrue((root / ".just-demand" / "scripts" / "install.py").exists())
            self.assertTrue((root / ".just-demand" / "scripts" / "workflow_core.py").exists())

    def test_init_project_creates_only_project_workflow_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)

            self.assertEqual([path.name for path in root.iterdir()], [".just-demand"])
    
    def test_init_project_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result1 = init_project(root)
            result2 = init_project(root)
            
            self.assertEqual(result1["status"], "success")
            self.assertEqual(result2["status"], "success")
            # Should not fail on second run

    def test_init_project_refreshes_changed_local_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = SCRIPT_DIR / "task.py"

            init_project(root)
            target = root / ".just-demand" / "scripts" / "task.py"
            target.write_text("stale\n", encoding="utf-8")

            result = init_project(root)

            self.assertEqual(result["status"], "success")
            self.assertGreater(result["scripts_deployed"], 0)
            self.assertEqual(target.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))

    def test_sync_initialized_workspaces_refreshes_all_discovered_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            search_root = Path(tmp)
            project_a = search_root / "project-a"
            project_b = search_root / "nested" / "project-b"
            project_a.mkdir(parents=True)
            project_b.mkdir(parents=True)
            init_project(project_a)
            init_project(project_b)

            source_task = SCRIPT_DIR / "task.py"
            source_core = SCRIPT_DIR / "workflow_core.py"
            target_task = project_a / ".just-demand" / "scripts" / "task.py"
            target_core = project_b / ".just-demand" / "scripts" / "workflow_core.py"
            target_task.write_text("stale task\n", encoding="utf-8")
            target_core.write_text("stale core\n", encoding="utf-8")

            result = sync_initialized_workspaces([search_root])

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["workspaces_found"], 2)
            self.assertEqual(result["workspaces_updated"], 2)
            self.assertGreaterEqual(result["total_scripts_deployed"], 2)
            self.assertEqual(target_task.read_text(encoding="utf-8"), source_task.read_text(encoding="utf-8"))
            self.assertEqual(target_core.read_text(encoding="utf-8"), source_core.read_text(encoding="utf-8"))

    def test_sync_initialized_workspaces_returns_empty_result_when_none_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            search_root = Path(tmp)

            result = sync_initialized_workspaces([search_root])

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["workspaces_found"], 0)
            self.assertEqual(result["workspaces_updated"], 0)
            self.assertEqual(result["total_scripts_deployed"], 0)
    
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
            target.write_text('{"dependencies":{"keep":"1.0.0"}}\n', encoding="utf-8")
            manifest = {"installed_files": {}, "version": "1.0"}

            copied, warning = deploy_config_file(source, target, manifest, config_root)

            self.assertFalse(copied)
            self.assertIn("package.json", warning)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"dependencies":{"keep":"1.0.0"}}\n')
            self.assertNotIn("package.json", manifest["installed_files"])
    
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
        
        self.assertIn("just-demand-check.md", DEPLOYED_FILES["agents"])
        self.assertIn("just-demand-docs.md", DEPLOYED_FILES["agents"])
        self.assertIn("just-demand-implement.md", DEPLOYED_FILES["agents"])
        self.assertIn("just-demand-research.md", DEPLOYED_FILES["agents"])
        
        self.assertIn("using-just-demand", DEPLOYED_FILES["skills"])
        self.assertIn("socratic-clarification", DEPLOYED_FILES["skills"])
        self.assertIn("just-demand-execution", DEPLOYED_FILES["skills"])
        self.assertIn("just-demand-intake", DEPLOYED_FILES["skills"])
        self.assertIn("just-demand-memory", DEPLOYED_FILES["skills"])
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
            self.assertTrue((config_root / "agents" / "just-demand-implement.md").exists())
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

    def test_install_opencode_global_deploys_expected_agent_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            install_opencode_global(config_root)

            implement_agent = (config_root / "agents" / "just-demand-implement.md").read_text(encoding="utf-8")
            check_agent = (config_root / "agents" / "just-demand-check.md").read_text(encoding="utf-8")
            docs_agent = (config_root / "agents" / "just-demand-docs.md").read_text(encoding="utf-8")

            for content in (implement_agent, check_agent):
                self.assertIn('"*": ask', content)
                self.assertIn('"git status": allow', content)
                self.assertIn('"git diff *": allow', content)
                self.assertIn('"git log *": allow', content)
                self.assertIn('"python3 .just-demand/scripts/task.py --root . list-active": allow', content)
                self.assertIn('"python3 -m unittest tests.just_demand.test_workflow_core -v": allow', content)
                self.assertIn('"python3 -m unittest tests.just_demand.test_install -v": allow', content)
                self.assertIn('"node --test tests/just_demand/test_opencode_plugins.mjs": allow', content)
                self.assertIn('"python3 -m json.tool .opencode/package.json": allow', content)

            self.assertIn('bash: deny', docs_agent)
    
    def test_install_opencode_global_creates_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            install_opencode_global(config_root)
            
            manifest_path = config_root / ".just-demand-manifest.json"
            self.assertTrue(manifest_path.exists())
            
            manifest = load_manifest(config_root)
            self.assertGreater(len(manifest["installed_files"]), 0)
    
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

    def test_install_preserves_existing_unmanaged_package_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            package_json = config_root / "package.json"
            package_json.write_text('{"dependencies":{"keep":"1.0.0"}}\n', encoding="utf-8")

            result = install_opencode_global(config_root)
            manifest = load_manifest(config_root)

            self.assertEqual(result["status"], "success")
            self.assertEqual(package_json.read_text(encoding="utf-8"), '{"dependencies":{"keep":"1.0.0"}}\n')
            self.assertNotIn("package.json", manifest["installed_files"])
            self.assertTrue(result["results"]["warnings"])

    def test_uninstall_preserves_existing_unmanaged_package_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            package_json = config_root / "package.json"
            package_json.write_text('{"dependencies":{"keep":"1.0.0"}}\n', encoding="utf-8")

            install_opencode_global(config_root)
            uninstall_opencode_global(config_root)

            self.assertTrue(package_json.exists())
            self.assertEqual(package_json.read_text(encoding="utf-8"), '{"dependencies":{"keep":"1.0.0"}}\n')


class InstallCLITests(unittest.TestCase):
    def test_cli_init(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "init"],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "success")
            self.assertTrue((root / ".just-demand").exists())
            self.assertTrue((root / ".just-demand" / "scripts" / "task.py").exists())
    
    def test_cli_install_requires_flags(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
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
            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "install", "--opencode", "--global", "--config-root", str(config_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "success")
            self.assertTrue((config_root / "plugins" / "just-demand-lib.js").exists())
    
    def test_cli_update_opencode_global(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            config_root = Path(tmp)
            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            
            # Install first
            subprocess.run(
                [sys.executable, str(script), "install", "--opencode", "--global", "--config-root", str(config_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            
            # Update
            result = subprocess.run(
                [sys.executable, str(script), "update", "--opencode", "--global", "--config-root", str(config_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "success")

    def test_cli_sync_workspaces(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            search_root = Path(tmp)
            project_root = search_root / "project"
            project_root.mkdir()
            init_project(project_root)

            source = SCRIPT_DIR / "task.py"
            target = project_root / ".just-demand" / "scripts" / "task.py"
            target.write_text("stale\n", encoding="utf-8")

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "sync-workspaces", "--search-root", str(search_root)],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)

            self.assertEqual(payload["status"], "success")
            self.assertEqual(payload["workspaces_found"], 1)
            self.assertEqual(payload["workspaces_updated"], 1)
            self.assertGreater(payload["total_scripts_deployed"], 0)
            self.assertEqual(target.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
    
    def test_cli_doctor(self):
        import subprocess
        
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root)
            
            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "doctor"],
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
            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            
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
