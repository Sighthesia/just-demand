import json
import tempfile
import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / ".agent-workflow" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_core import (
    acquire_lock,
    cleanup_completed_task,
    complete_verification,
    create_intake,
    create_validation_revision,
    ensure_workspace,
    list_unfinished_tasks,
    locks_path,
    promote_to_task,
    read_json,
    start_execution,
    task_event_path,
    workspace_dir,
)


class WorkflowCoreTests(unittest.TestCase):
    def test_ensure_workspace_creates_state_and_memory_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            ensure_workspace(root)

            workflow = root / ".agent-workflow"
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

            workflow = root / ".agent-workflow"
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

            task_dir = root / ".agent-workflow" / "tasks" / "active" / result["task_id"]
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

            state = read_json(root / ".agent-workflow" / "workspace" / "state.json")
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
            locks = read_json(root / ".agent-workflow" / "workspace" / "locks.json")
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

            start_execution(root, task_id=task_id, subagents=["workflow-implement"])
            task_path = root / ".agent-workflow" / "tasks" / "active" / task_id / "task.json"
            task = read_json(task_path)
            self.assertEqual(task["status"], "executing")
            self.assertEqual(task["validation_revision"], "r001")

            complete_verification(root, task_id=task_id, result="failed", summary="Validation mismatch")
            task = read_json(task_path)
            self.assertEqual(task["status"], "changes_requested")
            self.assertEqual(task["verification_status"], "failed")

            complete_verification(root, task_id=task_id, result="passed", summary="All checks passed")
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
            complete_verification(root, task_id=task_id, result="passed", summary="ok")

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
            start_execution(root, task["task_id"], ["workflow-implement"])
            final_task = complete_verification(root, task["task_id"], "passed", "End-to-end path works")
            self.assertEqual(final_task["status"], "done")

    def test_cli_create_intake(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = REPO_ROOT / ".agent-workflow" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "create-intake", "Agent workflow", "Build workflow", "--session", "session-main"],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("intake_id", result.stdout)
            state = read_json(root / ".agent-workflow" / "workspace" / "state.json")
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

            script = REPO_ROOT / ".agent-workflow" / "scripts" / "task.py"
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
            start_execution(root, task_id, ["workflow-implement"])
            complete_verification(root, task_id, "passed", "All done")

            state = read_json(workspace_dir(root) / "state.json")
            self.assertIn(task_id, state["active_task_ids"])
            self.assertEqual(state["current_task_id"], task_id)

            acquire_lock(root, scope="task", entity_id=task_id, owner="s1", purpose="test-lock")
            locks_data = read_json(locks_path(root))
            self.assertTrue(any(lk["entity_id"] == task_id for lk in locks_data["locks"]))

            result = cleanup_completed_task(root, task_id)
            self.assertTrue(result["cleaned"])
            self.assertEqual(result["task_id"], task_id)

            task_dir = root / ".agent-workflow" / "tasks" / "active" / task_id
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

            task_dir = root / ".agent-workflow" / "tasks" / "active" / task_id
            self.assertTrue(task_dir.exists())

    def test_cleanup_task_cli_success(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI cleanup", "Build CLI cleanup", "s1")
            promoted = promote_to_task(root, intake["intake_id"], "CLI cleanup", "Build CLI cleanup", "design", ["CLI cleanup works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "CLI cleanup.", ["C1"], ["E1"])
            start_execution(root, task_id, ["workflow-implement"])
            complete_verification(root, task_id, "passed", "All done")

            script = REPO_ROOT / ".agent-workflow" / "scripts" / "task.py"
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

            script = REPO_ROOT / ".agent-workflow" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "cleanup-task", task_id],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
