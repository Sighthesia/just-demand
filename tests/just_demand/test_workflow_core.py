import json
import re
import subprocess
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


def replace_intake_section(path: Path, heading: str, body: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = rf"(^## {re.escape(heading)}\n)(.*?)(?=^## |\Z)"
    updated = re.sub(
        pattern,
        lambda match: f"{match.group(1)}{body.rstrip()}\n\n",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    path.write_text(updated, encoding="utf-8")


def set_intake_scope(root: Path, intake_id: str, scope: str = "Confirmed implementation scope.") -> None:
    replace_intake_section(
        root / ".just-demand" / "workspace" / "intake" / f"{intake_id}.md",
        "Scope",
        scope,
    )


def init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Just Demand Tests"], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=root, text=True, capture_output=True, check=True)
    tracked = root / "tracked.txt"
    tracked.write_text("initial\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "chore: seed repo"], cwd=root, text=True, capture_output=True, check=True)


def git_stdout(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
    return result.stdout


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

    def test_create_intake_includes_clarification_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(root, "Bug report", "Feature breaks on save", "session-main")
            intake_path = root / ".just-demand" / "workspace" / "intake" / f"{result['intake_id']}.md"
            intake_text = intake_path.read_text(encoding="utf-8")
            self.assertIn("## Expected Behavior", intake_text)
            self.assertIn("## Actual Behavior", intake_text)
            self.assertIn("## Reproduction", intake_text)
            self.assertIn("## Scope", intake_text)
            self.assertIn("## Blocking Questions", intake_text)
            self.assertIn("## Non-Blocking Questions", intake_text)

    def test_create_intake_leaves_scope_blank_for_clarification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(root, "Feature request", "Add a keyboard shortcut", "session-main")
            intake_path = root / ".just-demand" / "workspace" / "intake" / f"{result['intake_id']}.md"
            intake_text = intake_path.read_text(encoding="utf-8")
            self.assertRegex(intake_text, r"## Scope\n\n## Anti-Outcome")


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
            set_intake_scope(root, intake["intake_id"], "Build the initial OpenCode-first workflow runtime.")

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
            self.assertEqual(task["clarification"]["scope"], "Build the initial OpenCode-first workflow runtime.")
            self.assertEqual(task["clarification"]["blocking_questions"], [])

            state = read_json(root / ".just-demand" / "workspace" / "state.json")
            self.assertIsNone(state["current_intake_id"])
            self.assertEqual(state["current_task_id"], result["task_id"])
            self.assertIn(result["task_id"], state["active_task_ids"])

    def test_promote_blocks_when_scope_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Workflow", "Build workflow", "session-main")

            with self.assertRaisesRegex(RuntimeError, "Scope is required"):
                promote_to_task(root, intake["intake_id"], "Workflow", "Build workflow", "design", ["It works"])

    def test_promote_blocks_when_blocking_questions_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Workflow", "Build workflow", "session-main")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "workspace" / "intake" / f"{intake['intake_id']}.md"
            replace_intake_section(intake_path, "Blocking Questions", "- Should this affect archived tasks?")

            with self.assertRaisesRegex(RuntimeError, "Blocking Questions"):
                promote_to_task(root, intake["intake_id"], "Workflow", "Build workflow", "design", ["It works"])

    def test_promote_blocks_bug_work_without_expected_actual_and_reproduction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Broken save", "Bug: saving fails instead of persisting changes", "session-main")

            with self.assertRaisesRegex(RuntimeError, "Expected Behavior"):
                promote_to_task(root, intake["intake_id"], "Broken save", "Fix save", "bugfix", ["Saving works"])

    def test_promote_carries_clarification_questions_into_task_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Mismatch", "Bug: expected success toast but got silent failure", "session-main")
            intake_path = root / ".just-demand" / "workspace" / "intake" / f"{intake['intake_id']}.md"
            replace_intake_section(intake_path, "Scope", "Investigate save feedback and toast behavior.")
            replace_intake_section(intake_path, "Expected Behavior", "User sees a success toast after save.")
            replace_intake_section(intake_path, "Actual Behavior", "Save fails silently.")
            replace_intake_section(intake_path, "Reproduction", "1. Edit an item\n2. Click save")
            replace_intake_section(intake_path, "Non-Blocking Questions", "- Should the toast include the item name?")

            promoted = promote_to_task(root, intake["intake_id"], "Mismatch", "Fix save feedback", "bugfix", ["Save feedback matches behavior"])
            task_dir = root / ".just-demand" / "tasks" / "active" / promoted["task_id"]
            task = read_json(task_dir / "task.json")
            self.assertEqual(task["clarification"]["expected_behavior"], "User sees a success toast after save.")
            self.assertEqual(task["clarification"]["actual_behavior"], "Save fails silently.")
            self.assertEqual(task["clarification"]["reproduction"], "1. Edit an item\n2. Click save")
            self.assertEqual(task["clarification"]["scope"], "Investigate save feedback and toast behavior.")
            self.assertEqual(task["clarification"]["non_blocking_questions"], ["Should the toast include the item name?"])
            self.assertIn("Should the toast include the item name?", (task_dir / "open_questions.md").read_text(encoding="utf-8"))

    def test_feature_request_with_expected_wording_is_not_treated_as_bug(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(
                root,
                "Label cleanup",
                "Add clearer labels and use the expected product names instead of abbreviations.",
                "session-main",
            )
            set_intake_scope(root, intake["intake_id"], "Update labels in the current settings flow only.")

            promoted = promote_to_task(
                root,
                intake["intake_id"],
                "Label cleanup",
                "Improve settings labels",
                "design",
                ["Labels are clearer in settings."],
            )

            task = read_json(root / ".just-demand" / "tasks" / "active" / promoted["task_id"] / "task.json")
            self.assertFalse(task["clarification"]["needs_bug_clarification"])


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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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

    def test_cli_promote_reports_readiness_errors(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Broken save", "Bug: save is broken", "session-main")
            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "promote", intake["intake_id"], "Broken save", "Fix save", "--type", "bugfix", "--acceptance", "Saving works"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Expected Behavior", payload["message"])

    def test_list_unfinished_tasks_and_cli_list_active(self):
        import json as std_json
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake_a = create_intake(root, "Task A", "First", "session-main")
            intake_b = create_intake(root, "Task B", "Second", "session-main")
            set_intake_scope(root, intake_a["intake_id"], "Scope A")
            set_intake_scope(root, intake_b["intake_id"], "Scope B")
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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

    def test_complete_verification_creates_checkpoint_commit_for_task_scoped_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)

            intake = create_intake(root, "Scoped commit", "Build scoped commit", "s1")
            set_intake_scope(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Scoped commit", "Build scoped commit", "implementation", ["Scoped commit works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Scoped commit.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            mark_task(root, task_id, "executing", impact=["tracked.txt"])

            (root / "tracked.txt").write_text("updated\n", encoding="utf-8")
            (root / "unrelated.txt").write_text("leave me out\n", encoding="utf-8")

            result = complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            self.assertTrue(result["checkpoint_commit"]["created"])
            self.assertEqual(result["checkpoint_commit"]["paths"], ["tracked.txt"])

            task = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertTrue(task["checkpoint_commit"]["created"])

            latest_log = git_stdout(root, "log", "--oneline", "-1")
            self.assertRegex(latest_log, r"^[0-9a-f]+ feat: checkpoint scoped commit")

            committed_files = [line for line in git_stdout(root, "show", "--name-only", "--format=", "HEAD").splitlines() if line.strip()]
            self.assertEqual(committed_files, ["tracked.txt"])

            status_output = git_stdout(root, "status", "--short")
            self.assertIn("?? unrelated.txt", status_output)

    def test_complete_verification_cli_creates_checkpoint_commit_and_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)

            intake = create_intake(root, "CLI checkpoint", "Build CLI checkpoint", "s1")
            set_intake_scope(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI checkpoint", "Build CLI checkpoint", "implementation", ["CLI checkpoint works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "CLI checkpoint.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-implement"])
            mark_task(root, task_id, "executing", impact=["tracked.txt"])

            (root / "tracked.txt").write_text("updated from cli\n", encoding="utf-8")

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "--root", str(root), "complete-verification", task_id, "passed", "All done"],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)

            self.assertTrue(payload["archived"])
            self.assertTrue(payload["checkpoint_commit"]["created"])
            self.assertTrue((tasks_dir(root) / "archive" / task_id).is_dir())

            latest_log = git_stdout(root, "log", "--oneline", "-1")
            self.assertRegex(latest_log, r"^[0-9a-f]+ feat: checkpoint cli checkpoint")

    def test_complete_verification_reports_archive_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Auto archive failure", "Build auto archive failure", "s1")
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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

            state = read_json(root / ".just-demand" / "workspace" / "state.json")
            self.assertEqual(state["current_task_id"], task_id)
            self.assertIsNone(state["current_intake_id"])

    def test_mark_task_pause_clears_current_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Pause task", "Track pause", "s1")
            set_intake_scope(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Pause task", "Track pause", "design", ["Task can pause"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "executing")
            mark_task(root, task_id, "paused")

            state = read_json(root / ".just-demand" / "workspace" / "state.json")
            self.assertIsNone(state["current_task_id"])

    def test_start_execution_sets_current_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake_a = create_intake(root, "Task A", "First task", "s1")
            intake_b = create_intake(root, "Task B", "Second task", "s1")
            set_intake_scope(root, intake_a["intake_id"], "Scope A")
            set_intake_scope(root, intake_b["intake_id"], "Scope B")
            task_a = promote_to_task(root, intake_a["intake_id"], "Task A", "Goal A", "design", ["A"])["task_id"]
            task_b = promote_to_task(root, intake_b["intake_id"], "Task B", "Goal B", "design", ["B"])["task_id"]
            self.assertEqual(read_json(root / ".just-demand" / "workspace" / "state.json")["current_task_id"], task_b)

            start_execution(root, task_a, ["just-demand-implement"])

            state = read_json(root / ".just-demand" / "workspace" / "state.json")
            self.assertEqual(state["current_task_id"], task_a)

    def test_mark_task_invalid_status_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Invalid mark", "Build invalid", "s1")
            set_intake_scope(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Invalid mark", "Build invalid", "design", ["Invalid raises"])
            task_id = promoted["task_id"]

            with self.assertRaises(ValueError):
                mark_task(root, task_id, "invalid_status")

    def test_mark_task_rejects_done_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Mark done", "Build mark done", "s1")
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Impact mark", "Build impact", "design", ["Impact works"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "executing", impact=[".just-demand/scripts/", "tests/just_demand/"])
            task = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertEqual(task["impact"], [".just-demand/scripts/", "tests/just_demand/"])

    def test_mark_task_events_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Event mark", "Build event", "s1")
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
            set_intake_scope(root, intake["intake_id"])
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
