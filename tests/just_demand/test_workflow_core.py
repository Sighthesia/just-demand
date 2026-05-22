import json
import tempfile
import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / ".just-demand" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_core import (
    acquire_lock,
    archive_task,
    cleanup_completed_task,
    complete_verification,
    create_intake,
    create_validation_revision,
    ensure_workspace,
    list_unfinished_tasks,
    locks_path,
    mark_task,
    promote_to_task,
    read_json,
    start_execution,
    tasks_dir,
    task_event_path,
    workspace_dir,
    write_json_atomic,
)


class WorkflowCoreTests(unittest.TestCase):
    def test_ensure_workspace_creates_state_and_memory_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            ensure_workspace(root)

            workflow = root / ".just-demand"
            self.assertTrue((workflow / "workspace" / "state.json").is_file())
            self.assertTrue((workflow / "workspace" / "preferences.md").is_file())
            self.assertTrue((workflow / "workspace" / "decisions.md").is_file())
            self.assertTrue((workflow / "workspace" / "deferred_options.md").is_file())
            self.assertTrue((workflow / "workspace" / "events.jsonl").is_file())
            state = read_json(workflow / "workspace" / "state.json")
            self.assertEqual(state["schema_version"], "1.0")
            self.assertIsNone(state["current_intake_id"])
            self.assertEqual(state["active_task_ids"], [])

    def test_create_intake_records_request_and_updates_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(
                root,
                title="Agent workflow",
                raw_request="Build an OpenCode-first agent workflow.",
                session_id="session-main",
            )

            workflow = root / ".just-demand"
            intake_path = workflow / "workspace" / "intake" / f"{result['intake_id']}.md"
            self.assertTrue(intake_path.is_file())
            intake_text = intake_path.read_text(encoding="utf-8")
            self.assertIn("Build an OpenCode-first agent workflow.", intake_text)
            self.assertIn("Status: clarifying", intake_text)

            state = read_json(workflow / "workspace" / "state.json")
            self.assertEqual(state["current_intake_id"], result["intake_id"])
            self.assertEqual(state["active_sessions"]["session-main"]["current_intake_id"], result["intake_id"])

            events = (workflow / "workspace" / "events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(events), 1)
            event = json.loads(events[0])
            self.assertEqual(event["type"], "intake_created")
            self.assertEqual(event["entity_id"], result["intake_id"])


    def test_promote_intake_to_task_creates_formal_package(self):
        from workflow_core import promote_to_task

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(
                root,
                title="Agent workflow",
                raw_request="Build an OpenCode-first agent workflow.",
                session_id="session-main",
            )

            result = promote_to_task(
                root,
                intake_id=intake["intake_id"],
                title="Agent workflow",
                goal="Build an OpenCode-first local workflow runtime.",
                task_type="design",
                acceptance_criteria=["Workspace intake can be promoted to a formal task."],
            )

            task_dir = root / ".just-demand" / "tasks" / "active" / result["task_id"]
            self.assertTrue((task_dir / "task.json").is_file())
            self.assertTrue((task_dir / "context.md").is_file())
            self.assertTrue((task_dir / "decisions.md").is_file())
            self.assertTrue((task_dir / "open_questions.md").is_file())
            self.assertTrue((task_dir / "implement.md").is_file())
            self.assertTrue((task_dir / "verify.md").is_file())
            self.assertTrue((task_dir / "outputs").is_dir())
            self.assertTrue((task_dir / "research").is_dir())

            task = read_json(task_dir / "task.json")
            self.assertEqual(task["source_intake_id"], intake["intake_id"])
            self.assertEqual(task["status"], "planning")
            self.assertEqual(task["goal"], "Build an OpenCode-first local workflow runtime.")
            self.assertEqual(task["acceptance_criteria"], ["Workspace intake can be promoted to a formal task."])

            state = read_json(root / ".just-demand" / "workspace" / "state.json")
            self.assertIsNone(state["current_intake_id"])
            self.assertEqual(state["current_task_id"], result["task_id"])
            self.assertIn(result["task_id"], state["active_task_ids"])


    def test_lock_acquire_and_release(self):
        from workflow_core import acquire_lock, release_lock

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            lock = acquire_lock(root, scope="task", entity_id="task-a", owner="session-main", purpose="test")
            self.assertEqual(lock["entity_id"], "task-a")

            with self.assertRaises(RuntimeError):
                acquire_lock(root, scope="task", entity_id="task-a", owner="other-session", purpose="test")

            release_lock(root, lock_id=lock["id"], owner="session-main")
            locks = read_json(root / ".just-demand" / "workspace" / "locks.json")
            self.assertEqual(locks["locks"], [])

    def test_lifecycle_and_validation_revision(self):
        from workflow_core import complete_verification, create_validation_revision, promote_to_task, start_execution

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Agent workflow", "Build workflow", "session-main")
            promoted = promote_to_task(root, intake["intake_id"], "Agent workflow", "Build workflow", "design", ["It can execute lifecycle transitions."])
            task_id = promoted["task_id"]

            revision = create_validation_revision(
                root,
                task_id=task_id,
                one_sentence="Build a local workflow runtime.",
                quick_check=["Intake exists", "Task exists", "Execution can start", "Verification can pass", "Corrections can reopen work"],
                effect_card=["Initial state is planning", "Start execution moves to executing", "Verification moves to done", "Failure moves to changes_requested", "Correction creates a new revision"],
            )
            self.assertEqual(revision["revision"], "r001")

            start_execution(root, task_id=task_id, subagents=["just-demand-implement"])
            task_path = root / ".just-demand" / "tasks" / "active" / task_id / "task.json"
            task = read_json(task_path)
            self.assertEqual(task["status"], "executing")
            self.assertEqual(task["validation_revision"], "r001")

            complete_verification(root, task_id=task_id, result="failed", summary="Validation mismatch")
            task = read_json(task_path)
            self.assertEqual(task["status"], "changes_requested")
            self.assertEqual(task["verification_status"], "failed")

            complete_verification(root, task_id=task_id, result="passed", summary="All checks passed", auto_archive=False)
            task = read_json(task_path)
            self.assertEqual(task["status"], "done")
            self.assertEqual(task["verification_status"], "passed")

    def test_task_event_before_status_records_real_transition(self):
        from workflow_core import complete_verification, promote_to_task, start_execution

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Test", "Test before_status", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Test", "Test before_status", "design", ["Check before_status"])
            task_id = promoted["task_id"]

            start_execution(root, task_id=task_id, subagents=["agent-a"])
            complete_verification(root, task_id=task_id, result="failed", summary="nope")
            complete_verification(root, task_id=task_id, result="passed", summary="ok", auto_archive=False)

            events_path = task_event_path(root, task_id)
            events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line]

            exec_evt = next(e for e in events if e["type"] == "execution_started")
            self.assertEqual(exec_evt["before_status"], "planning")
            self.assertEqual(exec_evt["after_status"], "executing")

            fail_evt = next(e for e in events if e["type"] == "verification_completed" and e["summary"].startswith("Verification failed"))
            self.assertEqual(fail_evt["before_status"], "executing")
            self.assertEqual(fail_evt["after_status"], "changes_requested")

            pass_evt = next(e for e in events if e["type"] == "verification_completed" and e["summary"].startswith("Verification passed"))
            self.assertEqual(pass_evt["before_status"], "changes_requested")
            self.assertEqual(pass_evt["after_status"], "done")


    def test_end_to_end_workflow_happy_path(self):
        from workflow_core import complete_verification, create_validation_revision, promote_to_task, start_execution

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Demo", "Build a demo workflow", "session-main")
            task = promote_to_task(root, intake["intake_id"], "Demo", "Build a demo workflow", "implementation", ["Lifecycle reaches done"])
            create_validation_revision(
                root,
                task["task_id"],
                "Build a demo workflow.",
                ["Intake", "Task", "Execution", "Verification", "Done"],
                ["Intake created", "Task promoted", "Execution starts", "Verification passes", "Task closes"],
            )
            start_execution(root, task["task_id"], ["just-demand-implement"])
            final_task = complete_verification(root, task["task_id"], "passed", "End-to-end path works")
            self.assertEqual(final_task["status"], "done")
            # Verify auto-archived
            self.assertTrue(final_task.get("archived"))

    def test_cli_create_intake(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "create-intake", "Agent workflow", "Build workflow", "--session", "session-main"],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("intake_id", result.stdout)
            state = read_json(root / ".just-demand" / "workspace" / "state.json")
            self.assertIsNotNone(state["current_intake_id"])

    def test_list_unfinished_tasks_and_cli_list_active(self):
        import json as std_json
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake_a = create_intake(root, "Task A", "First", "session-main")
            intake_b = create_intake(root, "Task B", "Second", "session-main")
            task_a = promote_to_task(root, intake_a["intake_id"], "Task A", "Goal A", "design", ["A"])
            task_b = promote_to_task(root, intake_b["intake_id"], "Task B", "Goal B", "design", ["B"])

            tasks = list_unfinished_tasks(root)
            task_ids = {task["id"] for task in tasks}
            self.assertIn(task_a["task_id"], task_ids)
            self.assertIn(task_b["task_id"], task_ids)

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "list-active"],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = std_json.loads(result.stdout)
            self.assertIn("tasks", payload)
            listed_ids = {task["id"] for task in payload["tasks"]}
            self.assertEqual(listed_ids, task_ids)

    def test_cleanup_completed_task_removes_dir_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Cleanup test", "Build cleanup", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Cleanup test", "Build cleanup", "design", ["Cleanup works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Cleanup test.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            state = read_json(workspace_dir(root) / "state.json")
            self.assertIn(task_id, state["active_task_ids"])
            self.assertEqual(state["current_task_id"], task_id)

            acquire_lock(root, scope="task", entity_id=task_id, owner="s1", purpose="test-lock")
            locks_data = read_json(locks_path(root))
            self.assertTrue(any(lk["entity_id"] == task_id for lk in locks_data["locks"]))

            result = cleanup_completed_task(root, task_id)
            self.assertTrue(result["cleaned"])
            self.assertEqual(result["task_id"], task_id)

            task_dir = root / ".just-demand" / "tasks" / "active" / task_id
            self.assertFalse(task_dir.exists())

            state = read_json(workspace_dir(root) / "state.json")
            self.assertNotIn(task_id, state["active_task_ids"])
            self.assertIsNone(state["current_task_id"])

            locks_data = read_json(locks_path(root))
            self.assertFalse(any(lk["entity_id"] == task_id for lk in locks_data["locks"]))

            events = (workspace_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            event_types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("task_cleaned_up", event_types)

    def test_cleanup_non_done_task_raises_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Not done", "Build not done", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Not done", "Build not done", "design", ["Not done yet"])
            task_id = promoted["task_id"]

            with self.assertRaises(RuntimeError):
                cleanup_completed_task(root, task_id)

            task_dir = root / ".just-demand" / "tasks" / "active" / task_id
            self.assertTrue(task_dir.exists())

    def test_cleanup_task_cli_success(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI cleanup", "Build CLI cleanup", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "CLI cleanup", "Build CLI cleanup", "design", ["CLI cleanup works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "CLI cleanup.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "cleanup-task", task_id],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["cleaned"])
            self.assertEqual(payload["task_id"], task_id)

    def test_cleanup_task_cli_fails_for_non_done(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI not done", "Build CLI not done", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "CLI not done", "Build CLI not done", "design", ["Not done"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "cleanup-task", task_id],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_archive_task_moves_to_archive_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Archive test", "Build archive", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Archive test", "Build archive", "design", ["Archive works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Archive test.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            # Verify task is still active before archive
            state = read_json(workspace_dir(root) / "state.json")
            self.assertIn(task_id, state["active_task_ids"])

            # Archive the task
            result = archive_task(root, task_id)
            self.assertTrue(result["archived"])
            self.assertEqual(result["task_id"], task_id)

            # Verify task moved to archive
            archive_dir = tasks_dir(root) / "archive" / task_id
            self.assertTrue(archive_dir.is_dir())
            self.assertTrue((archive_dir / "task.json").is_file())
            self.assertTrue((archive_dir / "outputs").is_dir())

            # Verify task no longer in active
            active_dir = tasks_dir(root) / "active" / task_id
            self.assertFalse(active_dir.exists())

            # Verify state cleaned up
            state = read_json(workspace_dir(root) / "state.json")
            self.assertNotIn(task_id, state["active_task_ids"])
            self.assertIsNone(state["current_task_id"])

            # Verify locks cleaned up
            locks_data = read_json(locks_path(root))
            self.assertFalse(any(lk["entity_id"] == task_id for lk in locks_data["locks"]))

            # Verify event emitted
            events = (workspace_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            event_types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("task_archived", event_types)

    def test_archive_task_extracts_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Decision extraction", "Build extraction", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Decision extraction", "Build extraction", "design", ["Extraction works"])
            task_id = promoted["task_id"]

            # Add some decisions to the task
            task_decisions_path = tasks_dir(root) / "active" / task_id / "decisions.md"
            task_decisions_path.write_text(
                "# Decisions\n\n## Decision: Use atomic writes\n\nStatus: accepted\n\nAll file writes should be atomic.\n",
                encoding="utf-8",
            )

            create_validation_revision(root, task_id, "Decision extraction.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            # Archive the task
            archive_task(root, task_id)

            # Verify decisions were extracted to workspace
            workspace_decisions = workspace_dir(root) / "decisions.md"
            content = workspace_decisions.read_text(encoding="utf-8")
            self.assertIn(f"## From Task: {task_id}", content)
            self.assertIn("Use atomic writes", content)

    def test_archive_task_extracts_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Fact extraction", "Build extraction", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Fact extraction", "Build extraction", "design", ["Extraction works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Fact extraction.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "Verification summary text", auto_archive=False)

            # Archive the task
            archive_task(root, task_id)

            # Verify facts were extracted to workspace
            workspace_facts = workspace_dir(root) / "facts.md"
            content = workspace_facts.read_text(encoding="utf-8")
            self.assertIn(task_id, content)
            self.assertIn("Fact extraction", content)

    def test_archive_task_preserves_original_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Preserve test", "Build preserve", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Preserve test", "Build preserve", "design", ["Preserve works"])
            task_id = promoted["task_id"]

            # Create some output files
            outputs_dir = tasks_dir(root) / "active" / task_id / "outputs"
            (outputs_dir / "custom-output.txt").write_text("custom content", encoding="utf-8")

            create_validation_revision(root, task_id, "Preserve test.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            # Archive the task
            archive_task(root, task_id)

            # Verify all original files are preserved in archive
            archive_dir = tasks_dir(root) / "archive" / task_id
            self.assertTrue((archive_dir / "task.json").is_file())
            self.assertTrue((archive_dir / "context.md").is_file())
            self.assertTrue((archive_dir / "decisions.md").is_file())
            self.assertTrue((archive_dir / "implement.md").is_file())
            self.assertTrue((archive_dir / "verify.md").is_file())
            self.assertTrue((archive_dir / "outputs" / "custom-output.txt").is_file())
            self.assertEqual((archive_dir / "outputs" / "custom-output.txt").read_text(encoding="utf-8"), "custom content")

    def test_archive_non_done_task_raises_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Not done archive", "Build not done", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Not done archive", "Build not done", "design", ["Not done yet"])
            task_id = promoted["task_id"]

            with self.assertRaises(RuntimeError):
                archive_task(root, task_id)

            # Verify task still in active
            task_dir = tasks_dir(root) / "active" / task_id
            self.assertTrue(task_dir.exists())

    def test_archive_existing_destination_raises_before_extraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Archive collision", "Build archive collision", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Archive collision", "Build archive collision", "design", ["Collision is safe"])
            task_id = promoted["task_id"]

            task_decisions_path = tasks_dir(root) / "active" / task_id / "decisions.md"
            task_decisions_path.write_text(
                "# Decisions\n\n## Decision: Collision guard\n\nDo not duplicate extracted memory.\n",
                encoding="utf-8",
            )

            create_validation_revision(root, task_id, "Archive collision.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            archive_destination = tasks_dir(root) / "archive" / task_id
            archive_destination.mkdir(parents=True)

            with self.assertRaises(FileExistsError):
                archive_task(root, task_id)

            self.assertTrue((tasks_dir(root) / "active" / task_id).is_dir())
            workspace_decisions = (workspace_dir(root) / "decisions.md").read_text(encoding="utf-8")
            self.assertNotIn("Collision guard", workspace_decisions)

    def test_complete_verification_auto_archives_on_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Auto archive test", "Build auto archive", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Auto archive test", "Build auto archive", "design", ["Auto archive works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Auto archive.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])

            # Complete verification with passed result (auto_archive=True by default)
            result = complete_verification(root, task_id, "passed", "All done")
            self.assertTrue(result.get("archived"))
            self.assertIn("archive_path", result)

            # Verify task is in archive
            archive_dir = tasks_dir(root) / "archive" / task_id
            self.assertTrue(archive_dir.is_dir())

            # Verify task not in active
            active_dir = tasks_dir(root) / "active" / task_id
            self.assertFalse(active_dir.exists())

    def test_complete_verification_reports_archive_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Auto archive failure", "Build auto archive failure", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Auto archive failure", "Build auto archive failure", "design", ["Failure is reported"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Auto archive failure.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])

            archive_destination = tasks_dir(root) / "archive" / task_id
            archive_destination.mkdir(parents=True)

            result = complete_verification(root, task_id, "passed", "All done")

            self.assertFalse(result["archived"])
            self.assertIn("archive_error", result)
            self.assertTrue((tasks_dir(root) / "active" / task_id).is_dir())

            events = (workspace_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            event_types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("task_archive_failed", event_types)

    def test_complete_verification_no_archive_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "No archive test", "Build no archive", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "No archive test", "Build no archive", "design", ["No archive works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "No archive.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])

            # Complete verification with failed result
            result = complete_verification(root, task_id, "failed", "Not done yet")
            self.assertFalse(result.get("archived"))

            # Verify task still in active
            task_dir = tasks_dir(root) / "active" / task_id
            self.assertTrue(task_dir.exists())

    def test_archive_task_cli_success(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI archive", "Build CLI archive", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "CLI archive", "Build CLI archive", "design", ["CLI archive works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "CLI archive.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "archive-task", task_id],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["archived"])
            self.assertEqual(payload["task_id"], task_id)

    def test_archive_task_cli_fails_for_non_done(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI archive not done", "Build CLI archive not done", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "CLI archive not done", "Build CLI archive not done", "design", ["Not done"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "archive-task", task_id],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_cleanup_archived_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Cleanup archived", "Build cleanup archived", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Cleanup archived", "Build cleanup archived", "design", ["Cleanup archived works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Cleanup archived.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            # Archive first
            archive_task(root, task_id)

            # Verify task is in archive
            archive_dir = tasks_dir(root) / "archive" / task_id
            self.assertTrue(archive_dir.is_dir())

            # Cleanup should work on archived task
            result = cleanup_completed_task(root, task_id)
            self.assertTrue(result["cleaned"])

            # Verify task directory is deleted
            self.assertFalse(archive_dir.exists())

    def test_mark_task_sets_status_and_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Mark test", "Build mark", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Mark test", "Build mark", "design", ["Mark works"])
            task_id = promoted["task_id"]

            result = mark_task(root, task_id, "debugging", progress=45, impact=[".just-demand/scripts/"], note="Diagnosing state issue")
            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "debugging")
            self.assertEqual(result["progress"], 45)

            task = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertEqual(task["status"], "debugging")
            self.assertEqual(task["progress"], 45)
            self.assertEqual(task["impact"], [".just-demand/scripts/"])
            self.assertEqual(task["last_note"], "Diagnosing state issue")

    def test_mark_task_invalid_status_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Invalid mark", "Build invalid", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Invalid mark", "Build invalid", "design", ["Invalid raises"])
            task_id = promoted["task_id"]

            with self.assertRaises(ValueError):
                mark_task(root, task_id, "invalid_status")

    def test_mark_task_rejects_done_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Mark done", "Build mark done", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Mark done", "Build mark done", "design", ["Done is not marked directly"])
            task_id = promoted["task_id"]

            with self.assertRaises(ValueError):
                mark_task(root, task_id, "done")

            task = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertEqual(task["status"], "planning")

    def test_mark_task_invalid_progress_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Progress mark", "Build progress", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Progress mark", "Build progress", "design", ["Progress raises"])
            task_id = promoted["task_id"]

            with self.assertRaises(ValueError):
                mark_task(root, task_id, "executing", progress=150)

    def test_mark_task_nonexistent_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)

            with self.assertRaises(FileNotFoundError):
                mark_task(root, "nonexistent-task", "executing")

    def test_mark_task_repeated_impact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Impact mark", "Build impact", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Impact mark", "Build impact", "design", ["Impact works"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "executing", impact=[".just-demand/scripts/", "tests/just_demand/"])
            task = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertEqual(task["impact"], [".just-demand/scripts/", "tests/just_demand/"])

    def test_mark_task_events_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Event mark", "Build event", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Event mark", "Build event", "design", ["Events work"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "tweaking", progress=90)

            task_events = [json.loads(line) for line in (task_event_path(root, task_id)).read_text(encoding="utf-8").splitlines() if line]
            mark_events = [e for e in task_events if e["type"] == "task_marked"]
            self.assertEqual(len(mark_events), 1)
            self.assertEqual(mark_events[0]["before_status"], "planning")
            self.assertEqual(mark_events[0]["after_status"], "tweaking")

            ws_events = [json.loads(line) for line in (workspace_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
            ws_mark = [e for e in ws_events if e["type"] == "task_marked"]
            self.assertEqual(len(ws_mark), 1)

    def test_list_active_concise_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Concise list", "Build concise", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Concise list", "Build concise", "design", ["Concise works"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "executing", progress=30, impact=[".just-demand/scripts/"])

            tasks = list_unfinished_tasks(root, verbose=False)
            self.assertEqual(len(tasks), 1)
            t = tasks[0]
            self.assertIn("id", t)
            self.assertIn("title", t)
            self.assertIn("status", t)
            self.assertIn("progress", t)
            self.assertIn("impact", t)
            self.assertNotIn("current_step", t)
            self.assertNotIn("path", t)

    def test_list_active_verbose_includes_step_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Verbose list", "Build verbose", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Verbose list", "Build verbose", "design", ["Verbose works"])
            task_id = promoted["task_id"]

            tasks = list_unfinished_tasks(root, verbose=True)
            self.assertEqual(len(tasks), 1)
            t = tasks[0]
            self.assertIn("current_step", t)
            self.assertIn("path", t)

    def test_list_active_backward_compat_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Compat list", "Build compat", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Compat list", "Build compat", "design", ["Compat works"])
            task_id = promoted["task_id"]

            # Simulate old task without progress/impact fields
            task_path = tasks_dir(root) / "active" / task_id / "task.json"
            task = read_json(task_path)
            del task["progress"]
            del task["impact"]
            write_json_atomic(task_path, task)

            tasks = list_unfinished_tasks(root, verbose=False)
            self.assertEqual(len(tasks), 1)
            t = tasks[0]
            self.assertIsNone(t["progress"])
            self.assertEqual(t["impact"], [])

    def test_mark_then_archive_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Mark archive", "Build mark archive", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "Mark archive", "Build mark archive", "design", ["Mark archive works"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "executing", progress=50, impact=["tests/"])
            mark_task(root, task_id, "tweaking", progress=95, note="Almost done")

            create_validation_revision(root, task_id, "Mark archive.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)
            archive_task(root, task_id)

            archive_dir = tasks_dir(root) / "archive" / task_id
            self.assertTrue(archive_dir.is_dir())
            archived_task = read_json(archive_dir / "task.json")
            self.assertEqual(archived_task["status"], "done")
            self.assertEqual(archived_task["progress"], 95)
            self.assertEqual(archived_task["impact"], ["tests/"])

    def test_mark_cli_success(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI mark", "Build CLI mark", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "CLI mark", "Build CLI mark", "design", ["CLI mark works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "mark", task_id, "debugging", "--progress", "42", "--impact", ".just-demand/scripts/", "--note", "debugging state"],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "debugging")
            self.assertEqual(payload["progress"], 42)

    def test_mark_cli_invalid_status(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI invalid mark", "Build CLI invalid", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "CLI invalid mark", "Build CLI invalid", "design", ["CLI invalid works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "mark", task_id, "bogus"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_list_active_cli_verbose(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI verbose list", "Build CLI verbose", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "CLI verbose list", "Build CLI verbose", "design", ["CLI verbose works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "list-active", "--verbose"],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(len(payload["tasks"]), 1)
            t = payload["tasks"][0]
            self.assertIn("current_step", t)
            self.assertIn("path", t)


if __name__ == "__main__":
    unittest.main()
