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
    build_execution_packet,
    cleanup_completed_task,
    complete_verification,
    create_intake,
    create_validation_revision,
    ensure_workspace,
    knowledge_dir,
    list_unfinished_tasks,
    locks_path,
    mark_task,
    parse_markdown_clarification_fields,
    promote_to_task,
    read_json,
    select_task,
    render_execution_packet_markdown,
    start_execution,
    start_verification,
    state_dir,
    tasks_dir,
    task_event_path,
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
        root / ".just-demand" / "state" / "intake" / f"{intake_id}.md",
        "Scope",
        scope,
    )


def set_intake_design_artifact(
    root: Path,
    intake_id: str,
    *,
    final_expected_effect: str = "User sees the expected result.",
    approach_options: str = "Approach A: direct implementation. Approach B: staged implementation.",
    chosen_approach: str = "Approach A: direct implementation.",
    final_implementation_plan: str = "1. Implement\n2. Verify",
    validation: str = "Run relevant tests.",
    approval: str = "Approved by user.",
) -> None:
    intake_path = root / ".just-demand" / "state" / "intake" / f"{intake_id}.md"
    replace_intake_section(intake_path, "Final Expected Effect", final_expected_effect)
    replace_intake_section(intake_path, "Approach Options", approach_options)
    replace_intake_section(intake_path, "Chosen Approach", chosen_approach)
    replace_intake_section(intake_path, "Final Implementation Plan", final_implementation_plan)
    replace_intake_section(intake_path, "Validation", validation)
    replace_intake_section(intake_path, "Approval", approval)


def set_intake_low_reading_artifacts(root: Path, intake_id: str) -> None:
    intake_path = root / ".just-demand" / "state" / "intake" / f"{intake_id}.md"
    replace_intake_section(intake_path, "Decision Card", "Intent: make clarification easier. Recommended default: use a concise decision card.")
    replace_intake_section(intake_path, "User Action", "Approve the recommendation or choose another option.")
    replace_intake_section(intake_path, "Recommended Default", "Use the concise decision-card output contract.")
    replace_intake_section(intake_path, "Option Matrix", "A: decision card; Pros: quick; Cons: less detail; Failure mode: misses edge nuance.")
    replace_intake_section(intake_path, "Minimum Viable Knowledge", "Decision card = a short approval aid with recommendation and tradeoffs.")
    replace_intake_section(intake_path, "Validation Card", "Quick check: user can approve, reject, or adjust the recommendation without reading long analysis.")
    replace_intake_section(intake_path, "Diagram", "flowchart TD\n  Need --> Card\n  Card --> Approval")
    replace_intake_section(intake_path, "Confidence", "high")
    replace_intake_section(intake_path, "Escalation Reason", "Only ask when product behavior, risk, or long-term maintenance changes.")


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
    def test_ensure_workspace_creates_state_and_knowledge_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            ensure_workspace(root)

            workflow = root / ".just-demand"
            self.assertTrue((workflow / "state" / "state.json").is_file())
            self.assertTrue((workflow / "knowledge").is_dir())
            self.assertFalse((workflow / "knowledge" / "memory.md").exists())
            self.assertTrue((workflow / "state" / "events.jsonl").is_file())
            state = read_json(workflow / "state" / "state.json")
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
            intake_path = workflow / "state" / "intake" / f"{result['intake_id']}.md"
            self.assertTrue(intake_path.is_file())
            intake_text = intake_path.read_text(encoding="utf-8")
            self.assertIn("Build an OpenCode-first agent workflow.", intake_text)
            self.assertIn("Status: clarifying", intake_text)

            state = read_json(workflow / "state" / "state.json")
            self.assertEqual(state["current_intake_id"], result["intake_id"])
            self.assertEqual(state["active_sessions"]["session-main"]["current_intake_id"], result["intake_id"])

            events = (workflow / "state" / "events.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(events), 1)
            event = json.loads(events[0])
            self.assertEqual(event["type"], "intake_created")
            self.assertEqual(event["entity_id"], result["intake_id"])

    def test_create_intake_generates_unique_ids_for_duplicate_titles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            first = create_intake(root, "Duplicate title", "First request", "session-main")
            second = create_intake(root, "Duplicate title", "Second request", "session-main")

            self.assertNotEqual(first["intake_id"], second["intake_id"])
            self.assertTrue(first["intake_id"].endswith("duplicate-title-intake"))
            self.assertRegex(second["intake_id"], r"duplicate-title-intake-[0-9a-f]{6}$")
            self.assertTrue((root / ".just-demand" / "state" / "intake" / f"{first['intake_id']}.md").is_file())
            self.assertTrue((root / ".just-demand" / "state" / "intake" / f"{second['intake_id']}.md").is_file())

    def test_create_intake_includes_clarification_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(root, "Bug report", "Feature breaks on save", "session-main")
            intake_path = root / ".just-demand" / "state" / "intake" / f"{result['intake_id']}.md"
            intake_text = intake_path.read_text(encoding="utf-8")
            self.assertIn("## Expected Behavior", intake_text)
            self.assertIn("## Actual Behavior", intake_text)
            self.assertIn("## Reproduction", intake_text)
            self.assertIn("## Scope", intake_text)
            self.assertIn("## Decision Card", intake_text)
            self.assertIn("## User Action", intake_text)
            self.assertIn("## Recommended Default", intake_text)
            self.assertIn("## Option Matrix", intake_text)
            self.assertIn("## Minimum Viable Knowledge", intake_text)
            self.assertIn("## Validation Card", intake_text)
            self.assertIn("## Diagram", intake_text)
            self.assertIn("## Confidence", intake_text)
            self.assertIn("## Escalation Reason", intake_text)
            self.assertIn("## Blocking Questions", intake_text)
            self.assertIn("## Non-Blocking Questions", intake_text)

    def test_create_intake_leaves_scope_blank_for_clarification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(root, "Feature request", "Add a keyboard shortcut", "session-main")
            intake_path = root / ".just-demand" / "state" / "intake" / f"{result['intake_id']}.md"
            intake_text = intake_path.read_text(encoding="utf-8")
            self.assertRegex(intake_text, r"## Scope\n\n## Opening")

    # -----------------------------------------------------------------------
    # update_intake_section
    # -----------------------------------------------------------------------

    def test_update_intake_section_updates_body_in_place(self):
        from workflow_core import update_intake_section

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(root, "Test intake", "Raw request text", "session-main")
            intake_id = result["intake_id"]
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake_id}.md"

            # Initially Scope is empty
            initial_text = intake_path.read_text(encoding="utf-8")
            self.assertIn("## Scope\n\n## Opening", initial_text)

            # Update the Scope section
            up_result = update_intake_section(root, intake_id, "Scope", "Confirmed scope.")

            self.assertTrue(up_result["ok"])
            self.assertEqual(up_result["intake_id"], intake_id)
            self.assertEqual(up_result["section"], "Scope")
            self.assertEqual(up_result["body"], "Confirmed scope.")

            # Verify the file was updated in place
            updated_text = intake_path.read_text(encoding="utf-8")
            self.assertIn("## Scope\nConfirmed scope.\n\n", updated_text)
            # Other sections remain intact
            self.assertIn("## Raw Request\nRaw request text\n\n", updated_text)

    def test_update_intake_section_preserves_adjoining_sections(self):
        from workflow_core import update_intake_section

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(root, "Adjoining test", "Raw text", "session-main")
            intake_id = result["intake_id"]
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake_id}.md"

            # Update a middle section
            update_intake_section(root, intake_id, "Approach Options", "Approach A: direct.")

            text = intake_path.read_text(encoding="utf-8")
            # Adjoining empty sections should still appear with their headings
            self.assertIn("## Approach Options\nApproach A: direct.\n\n", text)
            # The next section heading should still be present
            self.assertIn("## Chosen Approach\n\n## Final Implementation Plan", text)

    def test_update_intake_section_missing_intake_raises(self):
        from workflow_core import update_intake_section

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            with self.assertRaises(FileNotFoundError):
                update_intake_section(root, "nonexistent-intake", "Scope", "value")

    def test_update_intake_section_unknown_section_raises(self):
        from workflow_core import update_intake_section

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Unknown section test", "Raw", "session-main")
            intake_id = intake["intake_id"]

            with self.assertRaisesRegex(ValueError, "Unknown intake section"):
                update_intake_section(root, intake_id, "Nonexistent Section", "value")

    def test_update_intake_section_blank_values_preserved(self):
        """Updating a section to empty string should clear it (not break format)."""
        from workflow_core import update_intake_section

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(root, "Blank update test", "Raw", "session-main")
            intake_id = result["intake_id"]
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake_id}.md"

            # Start with a non-empty value, then clear it
            update_intake_section(root, intake_id, "Validation Card", "Some content")
            update_intake_section(root, intake_id, "Validation Card", "")

            text = intake_path.read_text(encoding="utf-8")
            # Section heading should still exist; next section heading should follow
            self.assertIn("## Validation Card", text)
            self.assertIn("## Diagram", text)
            # The section body should not contain the old content
            self.assertNotIn("Some content", text)

    def test_update_intake_section_supports_multi_line_values(self):
        from workflow_core import update_intake_section

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(root, "Multi-line", "Raw", "session-main")
            intake_id = result["intake_id"]
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake_id}.md"

            multi_line = "- Step 1\n- Step 2\n- Step 3"
            update_intake_section(root, intake_id, "Reproduction", multi_line)

            text = intake_path.read_text(encoding="utf-8")
            self.assertIn("- Step 1", text)
            self.assertIn("- Step 2", text)
            # Ensure the section boundary is intact
            self.assertRegex(text, r"## Reproduction\n- Step 1\n- Step 2\n- Step 3\n\n## Scope")

    def test_promotion_observes_updated_intake_sections(self):
        """After update_intake_section, promote_to_task should read the updated values."""
        from workflow_core import update_intake_section

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(
                root,
                "Updated intake",
                "Use updated section values",
                "session-main",
            )
            intake_id = intake["intake_id"]

            # Fill required sections via update_intake_section
            update_intake_section(root, intake_id, "Scope", "Updated scope for promotion check.")
            update_intake_section(root, intake_id, "Final Expected Effect", "Updated: user sees the result.")
            update_intake_section(root, intake_id, "Chosen Approach", "Updated approach.")
            update_intake_section(root, intake_id, "Final Implementation Plan", "1. Updated\n2. Test")
            update_intake_section(root, intake_id, "Approval", "Updated approval.")

            # Promote and verify updated values appear in task clarification
            promoted = promote_to_task(
                root,
                intake_id=intake_id,
                title="Updated intake",
                goal="Verify updated sections flow through promotion",
                task_type="design",
                acceptance_criteria=["Updated sections appear in task data."],
            )

            task = read_json(
                root / ".just-demand" / "state" / "active" / promoted["task_id"] / "task.json"
            )
            self.assertEqual(task["clarification"]["scope"], "Updated scope for promotion check.")
            self.assertEqual(task["clarification"]["final_expected_effect"], "Updated: user sees the result.")
            self.assertEqual(task["clarification"]["chosen_approach"], "Updated approach.")
            self.assertEqual(task["clarification"]["final_implementation_plan"], "1. Updated\n2. Test")
            self.assertEqual(task["clarification"]["approval"], "Updated approval.")

    def test_cli_update_intake_section_success(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI section update", "Raw", "session-main")
            intake_id = intake["intake_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-intake-section", intake_id, "Scope", "CLI-updated scope."],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["intake_id"], intake_id)
            self.assertEqual(payload["section"], "Scope")
            self.assertEqual(payload["body"], "CLI-updated scope.")

            # Verify file
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake_id}.md"
            text = intake_path.read_text(encoding="utf-8")
            self.assertIn("## Scope\nCLI-updated scope.\n\n", text)

    def test_cli_create_intake_emits_structured_summary_on_stderr(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "create-intake", "Readable intake", "Write a readable CLI summary.", "--session", "session-main"],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertIn("intake_id", payload)
            self.assertIn("Result: intake created", result.stderr)
            self.assertIn("Intake ID:", result.stderr)
            self.assertIn("Next action:", result.stderr)

    def test_cli_list_active_emits_structured_summary_on_stderr(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Readable list", "List me", "session-main")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promote_to_task(root, intake["intake_id"], "Readable list", "Build readable output", "design", ["Readable summary"])

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "list-active"],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(len(payload["tasks"]), 1)
            self.assertIn("Result: 1 unfinished task", result.stderr)
            self.assertIn("Tasks:", result.stderr)
            self.assertIn("Next action:", result.stderr)

    def test_cli_promote_and_select_include_next_action_summary(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Readable flow", "Promote me", "session-main")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            script = REPO_ROOT / "just-demand"

            promote_result = subprocess.run(
                [sys.executable, str(script), str(root), "promote", intake["intake_id"], "Readable flow", "Promote readable output", "--type", "implementation", "--acceptance", "Summary is obvious."],
                text=True,
                capture_output=True,
                check=True,
            )
            promote_payload = json.loads(promote_result.stdout)
            self.assertIn("next_actions", promote_payload)
            self.assertIn("Result: task promoted", promote_result.stderr)
            self.assertIn("Next actions:", promote_result.stderr)

            mark_task(root, promote_payload["task_id"], "paused")
            select_result = subprocess.run(
                [sys.executable, str(script), str(root), "select-task", promote_payload["task_id"]],
                text=True,
                capture_output=True,
                check=True,
            )
            select_payload = json.loads(select_result.stdout)
            self.assertTrue(select_payload["ok"])
            self.assertIn("Result: task selected", select_result.stderr)
            self.assertIn("Next actions:", select_result.stderr)

    def test_cli_show_readiness_emits_clear_recovery_summary(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Readiness summary", "Check readiness", "session-main")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Readiness summary", "Check readiness", "design", ["Ready summary"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "show-readiness", task_id],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertTrue(payload["ready"])
            self.assertIn("Current:", result.stderr)
            self.assertIn("Safe to continue: yes", result.stderr)
            self.assertIn("Recommended next:", result.stderr)

    def test_cli_update_intake_section_missing_intake(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-intake-section", "nonexistent-intake", "Scope", "value"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Intake not found", payload["message"])

    def test_cli_update_intake_section_unknown_section(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Unknown CLI section", "Raw", "session-main")
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-intake-section", intake["intake_id"], "Bogus Section", "value"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Unknown intake section", payload["message"])


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
            set_intake_design_artifact(root, intake["intake_id"])

            result = promote_to_task(
                root,
                intake_id=intake["intake_id"],
                title="Agent workflow",
                goal="Build an OpenCode-first local workflow runtime.",
                task_type="design",
                acceptance_criteria=["Workspace intake can be promoted to a formal task."],
            )

            task_dir = root / ".just-demand" / "state" / "active" / result["task_id"]
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

            state = read_json(root / ".just-demand" / "state" / "state.json")
            self.assertIsNone(state["current_intake_id"])
            self.assertEqual(state["current_task_id"], result["task_id"])
            self.assertIn(result["task_id"], state["active_task_ids"])

    def test_promote_carries_low_reading_clarification_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Decision cards", "Make clarification lighter", "session-main")
            set_intake_scope(root, intake["intake_id"], "Improve clarification prompts only.")
            set_intake_design_artifact(root, intake["intake_id"])
            set_intake_low_reading_artifacts(root, intake["intake_id"])

            promoted = promote_to_task(
                root,
                intake["intake_id"],
                "Decision cards",
                "Make clarification lighter",
                "implementation",
                ["Clarification artifacts are carried into task data."],
            )

            task = read_json(root / ".just-demand" / "state" / "active" / promoted["task_id"] / "task.json")
            clarification = task["clarification"]
            self.assertIn("Recommended default", clarification["decision_card"])
            self.assertIn("Approve the recommendation", clarification["user_action"])
            self.assertIn("decision-card output contract", clarification["recommended_default"])
            self.assertIn("Failure mode", clarification["option_matrix"])
            self.assertIn("Decision card", clarification["minimum_viable_knowledge"])
            self.assertIn("Quick check", clarification["validation_card"])
            self.assertIn("flowchart TD", clarification["diagram"])
            self.assertEqual(clarification["confidence"], "high")
            self.assertIn("Only ask", clarification["escalation_reason"])

    def test_promote_generates_unique_task_ids_for_duplicate_titles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake_a = create_intake(root, "Duplicate task A", "First", "session-main")
            intake_b = create_intake(root, "Duplicate task B", "Second", "session-main")
            set_intake_scope(root, intake_a["intake_id"], "Scope A")
            set_intake_scope(root, intake_b["intake_id"], "Scope B")
            set_intake_design_artifact(root, intake_a["intake_id"])
            set_intake_design_artifact(root, intake_b["intake_id"])

            first = promote_to_task(root, intake_a["intake_id"], "Duplicate task", "Goal A", "design", ["A"])
            second = promote_to_task(root, intake_b["intake_id"], "Duplicate task", "Goal B", "design", ["B"])

            self.assertNotEqual(first["task_id"], second["task_id"])
            self.assertTrue(first["task_id"].endswith("duplicate-task-task"))
            self.assertRegex(second["task_id"], r"duplicate-task-task-[0-9a-f]{6}$")
            self.assertTrue((tasks_dir(root) / "active" / first["task_id"]).is_dir())
            self.assertTrue((tasks_dir(root) / "active" / second["task_id"]).is_dir())

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
            set_intake_design_artifact(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
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
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            replace_intake_section(intake_path, "Scope", "Investigate save feedback and toast behavior.")
            replace_intake_section(intake_path, "Expected Behavior", "User sees a success toast after save.")
            replace_intake_section(intake_path, "Actual Behavior", "Save fails silently.")
            replace_intake_section(intake_path, "Reproduction", "1. Edit an item\n2. Click save")
            replace_intake_section(intake_path, "Non-Blocking Questions", "- Should the toast include the item name?")

            promoted = promote_to_task(root, intake["intake_id"], "Mismatch", "Fix save feedback", "bugfix", ["Save feedback matches behavior"])
            task_dir = root / ".just-demand" / "state" / "active" / promoted["task_id"]
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
            set_intake_design_artifact(root, intake["intake_id"])

            promoted = promote_to_task(
                root,
                intake["intake_id"],
                "Label cleanup",
                "Improve settings labels",
                "design",
                ["Labels are clearer in settings."],
            )

            task = read_json(root / ".just-demand" / "state" / "active" / promoted["task_id"] / "task.json")
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
            locks = read_json(root / ".just-demand" / "state" / "locks.json")
            self.assertEqual(locks["locks"], [])

    def test_expired_lock_does_not_block_new_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)

            expired = acquire_lock(root, scope="task", entity_id="task-a", owner="owner-a", purpose="expired", ttl_seconds=-1)
            self.assertEqual(expired["owner"], "owner-a")

            replacement = acquire_lock(root, scope="task", entity_id="task-a", owner="owner-b", purpose="replacement")

            self.assertEqual(replacement["owner"], "owner-b")
            locks = read_json(locks_path(root))
            self.assertEqual(len(locks["locks"]), 1)
            self.assertEqual(locks["locks"][0]["owner"], "owner-b")

    def test_concurrent_workspace_events_allocate_unique_sequences(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)

            code = (
                "import os, sys; "
                "from pathlib import Path; "
                f"sys.path.insert(0, {str(SCRIPT_DIR)!r}); "
                "from workflow_core import append_workspace_event; "
                f"root = Path({str(root)!r}); "
                "[append_workspace_event(root, 'concurrent_event', 'test', f'{os.getpid()}-{i}', 'concurrent event') for i in range(20)]"
            )
            processes = [
                subprocess.Popen([sys.executable, "-c", code], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                for _ in range(8)
            ]

            for process in processes:
                stdout, stderr = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, msg=f"stdout={stdout}\nstderr={stderr}")

            events = [json.loads(line) for line in (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
            seqs = [event["seq"] for event in events]

            self.assertEqual(len(seqs), 160)
            self.assertEqual(len(set(seqs)), 160)
            self.assertEqual(sorted(seqs), list(range(1, 161)))
            state = read_json(state_dir(root) / "state.json")
            self.assertEqual(state["last_event_seq"], 160)

    def test_lifecycle_and_validation_revision(self):
        from workflow_core import complete_verification, create_validation_revision, promote_to_task, start_execution

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Agent workflow", "Build workflow", "session-main")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
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

            start_execution(root, task_id=task_id, subagents=["just-demand-coder"])
            task_path = root / ".just-demand" / "state" / "active" / task_id / "task.json"
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
            set_intake_design_artifact(root, intake["intake_id"])
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
            set_intake_design_artifact(root, intake["intake_id"])
            task = promote_to_task(root, intake["intake_id"], "Demo", "Build a demo workflow", "implementation", ["Lifecycle reaches done"])
            create_validation_revision(
                root,
                task["task_id"],
                "Build a demo workflow.",
                ["Intake", "Task", "Execution", "Verification", "Done"],
                ["Intake created", "Task promoted", "Execution starts", "Verification passes", "Task closes"],
            )
            start_execution(root, task["task_id"], ["just-demand-coder"])
            final_task = complete_verification(root, task["task_id"], "passed", "End-to-end path works")
            self.assertEqual(final_task["status"], "done")
            # Verify auto-archived
            self.assertTrue(final_task.get("archived"))

    def test_cli_create_intake(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "create-intake", "Agent workflow", "Build workflow", "--session", "session-main"],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("intake_id", result.stdout)
            state = read_json(root / ".just-demand" / "state" / "state.json")
            self.assertIsNotNone(state["current_intake_id"])

    def test_create_intake_does_not_create_active_task_or_list_active_entry(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Agent workflow", "Build workflow", "session-main")

            self.assertTrue((root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md").is_file())
            self.assertEqual(list_unfinished_tasks(root), [])

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "list-active"],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["tasks"], [])

    def test_cli_help_accepts_project_dir_dot(self):
        import subprocess

        script = REPO_ROOT / "just-demand"
        result = subprocess.run(
            [sys.executable, str(script), ".", "--help"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("Just Demand task tools", result.stdout)
        self.assertIn("Project path form: just-demand [project-dir]", result.stdout)
        self.assertIn("just-demand [project-dir] --help", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_cli_help_lists_smoke_command(self):
        import task as task_cli

        help_text = task_cli.build_parser().format_help()
        self.assertIn("smoke", help_text)
        self.assertIn("Run the repo smoke validation checks", help_text)

    def test_smoke_command_runs_expected_checks(self):
        import task as task_cli

        calls = []

        class FakeCompletedProcess:
            def __init__(self, returncode: int = 0):
                self.returncode = returncode
                self.stdout = ""
                self.stderr = ""

        def fake_run(command, cwd=None, text=None, capture_output=None):
            calls.append({
                "command": tuple(command),
                "cwd": Path(cwd) if cwd is not None else None,
                "text": text,
                "capture_output": capture_output,
            })
            return FakeCompletedProcess()

        original_run = task_cli.subprocess.run
        task_cli.subprocess.run = fake_run
        try:
            result = task_cli.execute_command(REPO_ROOT, ["smoke"])
        finally:
            task_cli.subprocess.run = original_run

        self.assertEqual(result, 0)
        self.assertEqual(len(calls), 6)
        self.assertEqual(calls[0]["command"], (sys.executable, "-m", "unittest", "tests.just_demand.test_workflow_core", "-v"))
        self.assertEqual(calls[1]["command"], (sys.executable, "-m", "unittest", "tests.just_demand.test_install", "-v"))
        self.assertEqual(calls[2]["command"], ("node", "--test", "tests/just_demand/test_opencode_plugins.mjs"))
        self.assertEqual(calls[3]["command"], (sys.executable, "-m", "json.tool", ".opencode/package.json"))
        self.assertEqual(calls[4]["command"], (sys.executable, str(REPO_ROOT / "just-demand"), "--help"))
        self.assertEqual(calls[5]["command"], (sys.executable, str(REPO_ROOT / "just-demand"), ".", "--help"))
        for call in calls:
            self.assertEqual(call["cwd"], REPO_ROOT.resolve())
            self.assertTrue(call["text"])
            self.assertTrue(call["capture_output"])

    def test_cli_promote_reports_readiness_errors(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Broken save", "Bug: save is broken", "session-main")
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "promote", intake["intake_id"], "Broken save", "Fix save", "--type", "bugfix", "--acceptance", "Saving works"],
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
            set_intake_design_artifact(root, intake_a["intake_id"])
            set_intake_design_artifact(root, intake_b["intake_id"])
            task_a = promote_to_task(root, intake_a["intake_id"], "Task A", "Goal A", "design", ["A"])
            task_b = promote_to_task(root, intake_b["intake_id"], "Task B", "Goal B", "design", ["B"])

            tasks = list_unfinished_tasks(root)
            task_ids = {task["id"] for task in tasks}
            self.assertIn(task_a["task_id"], task_ids)
            self.assertIn(task_b["task_id"], task_ids)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "list-active"],
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Cleanup test", "Build cleanup", "design", ["Cleanup works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Cleanup test.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            state = read_json(state_dir(root) / "state.json")
            self.assertIn(task_id, state["active_task_ids"])
            self.assertEqual(state["current_task_id"], task_id)

            acquire_lock(root, scope="task", entity_id=task_id, owner="s1", purpose="test-lock")
            locks_data = read_json(locks_path(root))
            self.assertTrue(any(lk["entity_id"] == task_id for lk in locks_data["locks"]))

            result = cleanup_completed_task(root, task_id)
            self.assertTrue(result["cleaned"])
            self.assertEqual(result["task_id"], task_id)

            task_dir = root / ".just-demand" / "state" / "active" / task_id
            self.assertFalse(task_dir.exists())

            state = read_json(state_dir(root) / "state.json")
            self.assertNotIn(task_id, state["active_task_ids"])
            self.assertIsNone(state["current_task_id"])

            locks_data = read_json(locks_path(root))
            self.assertFalse(any(lk["entity_id"] == task_id for lk in locks_data["locks"]))

            events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            event_types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("task_cleaned_up", event_types)

    def test_cleanup_non_done_task_raises_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Not done", "Build not done", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Not done", "Build not done", "design", ["Not done yet"])
            task_id = promoted["task_id"]

            with self.assertRaises(RuntimeError):
                cleanup_completed_task(root, task_id)

            task_dir = root / ".just-demand" / "state" / "active" / task_id
            self.assertTrue(task_dir.exists())

    def test_cleanup_task_cli_success(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI cleanup", "Build CLI cleanup", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI cleanup", "Build CLI cleanup", "design", ["CLI cleanup works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "CLI cleanup.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "cleanup-task", task_id],
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI not done", "Build CLI not done", "design", ["Not done"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "cleanup-task", task_id],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_archive_task_moves_to_archive_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Archive test", "Build archive", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Archive test", "Build archive", "design", ["Archive works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Archive test.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            # Verify task is still active before archive
            state = read_json(state_dir(root) / "state.json")
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
            state = read_json(state_dir(root) / "state.json")
            self.assertNotIn(task_id, state["active_task_ids"])
            self.assertIsNone(state["current_task_id"])

            # Verify locks cleaned up
            locks_data = read_json(locks_path(root))
            self.assertFalse(any(lk["entity_id"] == task_id for lk in locks_data["locks"]))

            # Verify event emitted
            events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            event_types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("task_archived", event_types)

    def test_archive_task_preserves_decisions_without_memory_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Decision extraction", "Build extraction", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Decision extraction", "Build extraction", "design", ["Extraction works"])
            task_id = promoted["task_id"]

            # Add some decisions to the task
            task_decisions_path = tasks_dir(root) / "active" / task_id / "decisions.md"
            task_decisions_path.write_text(
                "# Decisions\n\n## Decision: Use atomic writes\n\nStatus: accepted\n\nAll file writes should be atomic.\n",
                encoding="utf-8",
            )

            create_validation_revision(root, task_id, "Decision extraction.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            # Archive the task
            archive_task(root, task_id)

            archive_dir = tasks_dir(root) / "archive" / task_id
            self.assertTrue((archive_dir / "decisions.md").is_file())
            self.assertFalse((knowledge_dir(root) / "memory.md").exists())
            self.assertIn("Use atomic writes", (archive_dir / "decisions.md").read_text(encoding="utf-8"))

    def test_archive_task_preserves_facts_without_memory_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Fact extraction", "Build extraction", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Fact extraction", "Build extraction", "design", ["Extraction works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Fact extraction.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "Verification summary text", auto_archive=False)

            # Archive the task
            archive_task(root, task_id)

            archive_dir = tasks_dir(root) / "archive" / task_id
            self.assertTrue((archive_dir / "outputs").is_dir())
            self.assertFalse((knowledge_dir(root) / "memory.md").exists())
            self.assertIn(task_id, (archive_dir / "task.json").read_text(encoding="utf-8"))

    def test_archive_task_preserves_original_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Preserve test", "Build preserve", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Preserve test", "Build preserve", "design", ["Preserve works"])
            task_id = promoted["task_id"]

            # Create some output files
            outputs_dir = tasks_dir(root) / "active" / task_id / "outputs"
            (outputs_dir / "custom-output.txt").write_text("custom content", encoding="utf-8")

            create_validation_revision(root, task_id, "Preserve test.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
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
            set_intake_design_artifact(root, intake["intake_id"])
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Archive collision", "Build archive collision", "design", ["Collision is safe"])
            task_id = promoted["task_id"]

            task_decisions_path = tasks_dir(root) / "active" / task_id / "decisions.md"
            task_decisions_path.write_text(
                "# Decisions\n\n## Decision: Collision guard\n\nDo not duplicate extracted memory.\n",
                encoding="utf-8",
            )

            create_validation_revision(root, task_id, "Archive collision.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            archive_destination = tasks_dir(root) / "archive" / task_id
            archive_destination.mkdir(parents=True)

            with self.assertRaises(FileExistsError):
                archive_task(root, task_id)

            self.assertTrue((tasks_dir(root) / "active" / task_id).is_dir())
            self.assertFalse((knowledge_dir(root) / "memory.md").exists())

    def test_complete_verification_auto_archives_on_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Auto archive test", "Build auto archive", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Auto archive test", "Build auto archive", "design", ["Auto archive works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Auto archive.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])

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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Scoped commit", "Build scoped commit", "implementation", ["Scoped commit works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Scoped commit.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI checkpoint", "Build CLI checkpoint", "implementation", ["CLI checkpoint works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "CLI checkpoint.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            mark_task(root, task_id, "executing", impact=["tracked.txt"])

            (root / "tracked.txt").write_text("updated from cli\n", encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "complete-verification", task_id, "passed", "All done"],
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Auto archive failure", "Build auto archive failure", "design", ["Failure is reported"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Auto archive failure.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])

            archive_destination = tasks_dir(root) / "archive" / task_id
            archive_destination.mkdir(parents=True)

            result = complete_verification(root, task_id, "passed", "All done")

            self.assertFalse(result["archived"])
            self.assertIn("archive_error", result)
            self.assertTrue((tasks_dir(root) / "active" / task_id).is_dir())

            events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            event_types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("task_archive_failed", event_types)

    def test_complete_verification_no_archive_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "No archive test", "Build no archive", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "No archive test", "Build no archive", "design", ["No archive works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "No archive.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])

            # Complete verification with failed result
            result = complete_verification(root, task_id, "failed", "Not done yet")
            self.assertFalse(result.get("archived"))

            # Verify task still in active
            task_dir = tasks_dir(root) / "active" / task_id
            self.assertTrue(task_dir.exists())

    def test_complete_verification_rejects_invalid_lifecycle_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Invalid closeout", "Build invalid closeout", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Invalid closeout", "Build invalid closeout", "design", ["Invalid closeout blocked"])
            task_id = promoted["task_id"]

            with self.assertRaisesRegex(RuntimeError, "Cannot complete verification"):
                complete_verification(root, task_id, "passed", "Should not close", auto_archive=False)

            mark_task(root, task_id, "blocked")
            with self.assertRaisesRegex(RuntimeError, "status is 'blocked'"):
                complete_verification(root, task_id, "blocked", "Still blocked", auto_archive=False)

    def test_archive_task_cli_success(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI archive", "Build CLI archive", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI archive", "Build CLI archive", "design", ["CLI archive works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "CLI archive.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "archive-task", task_id],
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI archive not done", "Build CLI archive not done", "design", ["Not done"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "archive-task", task_id],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_cleanup_archived_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Cleanup archived", "Build cleanup archived", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Cleanup archived", "Build cleanup archived", "design", ["Cleanup archived works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Cleanup archived.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
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
            set_intake_design_artifact(root, intake["intake_id"])
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

            state = read_json(root / ".just-demand" / "state" / "state.json")
            self.assertEqual(state["current_task_id"], task_id)
            self.assertIsNone(state["current_intake_id"])

    def test_mark_task_pause_clears_current_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Pause task", "Track pause", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Pause task", "Track pause", "design", ["Task can pause"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "executing")
            mark_task(root, task_id, "paused")

            state = read_json(root / ".just-demand" / "state" / "state.json")
            self.assertIsNone(state["current_task_id"])

    def test_select_task_sets_current_task_without_removing_active_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake_a = create_intake(root, "Task A", "First task", "s1")
            intake_b = create_intake(root, "Task B", "Second task", "s1")
            set_intake_scope(root, intake_a["intake_id"], "Scope A")
            set_intake_scope(root, intake_b["intake_id"], "Scope B")
            set_intake_design_artifact(root, intake_a["intake_id"])
            set_intake_design_artifact(root, intake_b["intake_id"])
            task_a = promote_to_task(root, intake_a["intake_id"], "Task A", "Goal A", "design", ["A"])["task_id"]
            task_b = promote_to_task(root, intake_b["intake_id"], "Task B", "Goal B", "design", ["B"])["task_id"]

            mark_task(root, task_b, "paused")
            state = read_json(root / ".just-demand" / "state" / "state.json")
            self.assertIsNone(state["current_task_id"])
            self.assertIn(task_a, state["active_task_ids"])
            self.assertIn(task_b, state["active_task_ids"])

            result = select_task(root, task_a)

            self.assertTrue(result["ok"])
            self.assertEqual(result["current_task_id"], task_a)
            state = read_json(root / ".just-demand" / "state" / "state.json")
            self.assertEqual(state["current_task_id"], task_a)
            self.assertIn(task_a, state["active_task_ids"])
            self.assertIn(task_b, state["active_task_ids"])

    def test_resume_command_selects_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Resume task", "Resume work", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            task_id = promote_to_task(root, intake["intake_id"], "Resume task", "Resume work", "design", ["Resume works"])["task_id"]
            mark_task(root, task_id, "paused")
            script = SCRIPT_DIR / "task.py"

            result = subprocess.run(
                [sys.executable, str(script), str(root), "resume", task_id],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertIn("next_actions", payload)
            self.assertTrue(any("list-active" in action for action in payload["next_actions"]))
            self.assertTrue(any("just-demand-* subagent" in action for action in payload["next_actions"]))
            self.assertEqual(read_json(root / ".just-demand" / "state" / "state.json")["current_task_id"], task_id)

    def test_cli_promote_and_select_task_include_next_actions_as_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI hints", "Add task guidance", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            script = SCRIPT_DIR / "task.py"

            promote_result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(root),
                    "promote",
                    intake["intake_id"],
                    "CLI hints",
                    "Add task guidance",
                    "--type",
                    "implementation",
                    "--acceptance",
                    "CLI output includes next actions.",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            promote_payload = json.loads(promote_result.stdout)
            task_id = promote_payload["task_id"]
            self.assertIn("next_actions", promote_payload)
            self.assertTrue(any("list-active" in action for action in promote_payload["next_actions"]))
            self.assertTrue(any("3+ files" in action for action in promote_payload["next_actions"]))
            self.assertTrue(any("context files" in action for action in promote_payload["next_actions"]))

            mark_task(root, task_id, "paused")
            select_result = subprocess.run(
                [sys.executable, str(script), str(root), "select-task", task_id],
                text=True,
                capture_output=True,
                check=True,
            )

            select_payload = json.loads(select_result.stdout)
            self.assertTrue(select_payload["ok"])
            self.assertIn("next_actions", select_payload)
            self.assertEqual(select_payload["next_actions"], promote_payload["next_actions"])

    def test_start_execution_sets_current_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake_a = create_intake(root, "Task A", "First task", "s1")
            intake_b = create_intake(root, "Task B", "Second task", "s1")
            set_intake_scope(root, intake_a["intake_id"], "Scope A")
            set_intake_scope(root, intake_b["intake_id"], "Scope B")
            set_intake_design_artifact(root, intake_a["intake_id"])
            set_intake_design_artifact(root, intake_b["intake_id"])
            task_a = promote_to_task(root, intake_a["intake_id"], "Task A", "Goal A", "design", ["A"])["task_id"]
            task_b = promote_to_task(root, intake_b["intake_id"], "Task B", "Goal B", "design", ["B"])["task_id"]
            self.assertEqual(read_json(root / ".just-demand" / "state" / "state.json")["current_task_id"], task_b)

            start_execution(root, task_a, ["just-demand-coder"])

            state = read_json(root / ".just-demand" / "state" / "state.json")
            self.assertEqual(state["current_task_id"], task_a)

    def test_mark_task_invalid_status_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Invalid mark", "Build invalid", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Invalid mark", "Build invalid", "design", ["Invalid raises"])
            task_id = promoted["task_id"]

            with self.assertRaises(ValueError):
                mark_task(root, task_id, "invalid_status")

    def test_mark_task_rejects_done_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Mark done", "Build mark done", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
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
            set_intake_design_artifact(root, intake["intake_id"])
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
            set_intake_design_artifact(root, intake["intake_id"])
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Event mark", "Build event", "design", ["Events work"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "tweaking", progress=90)

            task_events = [json.loads(line) for line in (task_event_path(root, task_id)).read_text(encoding="utf-8").splitlines() if line]
            mark_events = [e for e in task_events if e["type"] == "task_marked"]
            self.assertEqual(len(mark_events), 1)
            self.assertEqual(mark_events[0]["before_status"], "planning")
            self.assertEqual(mark_events[0]["after_status"], "tweaking")

            ws_events = [json.loads(line) for line in (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines() if line]
            ws_mark = [e for e in ws_events if e["type"] == "task_marked"]
            self.assertEqual(len(ws_mark), 1)

    def test_list_active_concise_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Concise list", "Build concise", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
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
            set_intake_design_artifact(root, intake["intake_id"])
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
            set_intake_design_artifact(root, intake["intake_id"])
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Mark archive", "Build mark archive", "design", ["Mark archive works"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "executing", progress=50, impact=["tests/"])
            mark_task(root, task_id, "tweaking", progress=95, note="Almost done")

            create_validation_revision(root, task_id, "Mark archive.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI mark", "Build CLI mark", "design", ["CLI mark works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "mark", task_id, "debugging", "--progress", "42", "--impact", ".just-demand/scripts/", "--note", "debugging state"],
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI invalid mark", "Build CLI invalid", "design", ["CLI invalid works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "mark", task_id, "bogus"],
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
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI verbose list", "Build CLI verbose", "design", ["CLI verbose works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "list-active", "--verbose"],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(len(payload["tasks"]), 1)
            t = payload["tasks"][0]
            self.assertIn("current_step", t)
            self.assertIn("path", t)

    def test_create_intake_includes_design_artifact_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_intake(root, "Design work", "Build a new feature", "session-main")
            intake_path = root / ".just-demand" / "state" / "intake" / f"{result['intake_id']}.md"
            intake_text = intake_path.read_text(encoding="utf-8")
            self.assertIn("## Final Expected Effect", intake_text)
            self.assertIn("## Approach Options", intake_text)
            self.assertIn("## Chosen Approach", intake_text)
            self.assertIn("## Final Implementation Plan", intake_text)
            self.assertIn("## Validation", intake_text)
            self.assertIn("## Approval", intake_text)

    def test_promote_blocks_design_without_final_expected_effect(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Design work", "Build a new feature", "session-main")
            set_intake_scope(root, intake["intake_id"])
            # Set chosen approach and plan but leave final expected effect empty
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            replace_intake_section(intake_path, "Chosen Approach", "Approach A")
            replace_intake_section(intake_path, "Final Implementation Plan", "1. Implement\n2. Verify")
            replace_intake_section(intake_path, "Approval", "Approved")

            with self.assertRaisesRegex(RuntimeError, "Final Expected Effect"):
                promote_to_task(root, intake["intake_id"], "Design work", "Build feature", "design", ["It works"])

    def test_promote_blocks_design_without_chosen_approach(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Design work", "Build a new feature", "session-main")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            replace_intake_section(intake_path, "Final Expected Effect", "User sees the feature.")
            replace_intake_section(intake_path, "Final Implementation Plan", "1. Implement\n2. Verify")
            replace_intake_section(intake_path, "Approval", "Approved")

            with self.assertRaisesRegex(RuntimeError, "Chosen Approach"):
                promote_to_task(root, intake["intake_id"], "Design work", "Build feature", "design", ["It works"])

    def test_promote_blocks_design_without_final_implementation_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Design work", "Build a new feature", "session-main")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            replace_intake_section(intake_path, "Final Expected Effect", "User sees the feature.")
            replace_intake_section(intake_path, "Chosen Approach", "Approach A")
            replace_intake_section(intake_path, "Approval", "Approved")

            with self.assertRaisesRegex(RuntimeError, "Final Implementation Plan"):
                promote_to_task(root, intake["intake_id"], "Design work", "Build feature", "design", ["It works"])

    def test_promote_blocks_design_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Design work", "Build a new feature", "session-main")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            replace_intake_section(intake_path, "Final Expected Effect", "User sees the feature.")
            replace_intake_section(intake_path, "Chosen Approach", "Approach A")
            replace_intake_section(intake_path, "Final Implementation Plan", "1. Implement\n2. Verify")

            with self.assertRaisesRegex(RuntimeError, "Approval"):
                promote_to_task(root, intake["intake_id"], "Design work", "Build feature", "design", ["It works"])

    def test_promote_blocks_implementation_without_design_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Impl work", "Implement a feature", "session-main")
            set_intake_scope(root, intake["intake_id"])

            with self.assertRaisesRegex(RuntimeError, "Final Expected Effect"):
                promote_to_task(root, intake["intake_id"], "Impl work", "Implement feature", "implementation", ["It works"])

    def test_real_launcher_stagger_request_requires_visible_lifecycle_golden_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_request = "试实现打开启动器（包括剪切板）时，列表项使用stagger效果排列淡入展现"
            intake = create_intake(root, "Launcher stagger", raw_request, "session-main")
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            set_intake_scope(root, intake["intake_id"], "Launcher and clipboard list reveal behavior only.")
            set_intake_design_artifact(
                root,
                intake["intake_id"],
                final_expected_effect="Launcher and clipboard rows reveal with staggered fade-in.",
                chosen_approach="Use visible lifecycle clarification before implementation.",
                final_implementation_plan="1. Confirm lifecycle\n2. Implement reveal\n3. Verify interaction",
                validation="Verify opening, transition, steady state, and interrupts.",
                approval="Approved by user.",
            )

            with self.assertRaisesRegex(RuntimeError, "Opening.*During Transition.*After Open.*Interrupt Behavior.*Anti-Outcomes"):
                promote_to_task(root, intake["intake_id"], "Launcher stagger", raw_request, "implementation", ["Rows reveal correctly"])

            replace_intake_section(intake_path, "Opening", "First frame shows the launcher shell with stable row positions.")
            replace_intake_section(intake_path, "During Transition", "Visible rows fade in with staggered timing from below.")
            replace_intake_section(intake_path, "After Open", "The steady list matches the existing launcher and clipboard UI.")
            replace_intake_section(intake_path, "Interrupt Behavior", "Typing, keyboard navigation, closing, or switching pages cancels or completes the reveal without replay.")
            replace_intake_section(intake_path, "Anti-Outcomes", "No direct implementation without clarification, flash, text jump, clipping, layout reflow, or repeated replay.")

            promoted = promote_to_task(root, intake["intake_id"], "Launcher stagger", raw_request, "implementation", ["Rows reveal correctly"])
            task = read_json(root / ".just-demand" / "state" / "active" / promoted["task_id"] / "task.json")
            clarification = task["clarification"]
            self.assertTrue(clarification["needs_ui_visible_lifecycle_clarification"])
            self.assertIn("stable row positions", clarification["opening"])
            self.assertIn("staggered timing", clarification["during_transition"])
            self.assertIn("existing launcher", clarification["after_open"])
            self.assertIn("keyboard navigation", clarification["interrupt_behavior"])
            self.assertIn("No direct implementation", clarification["anti_outcomes"])

    def test_promote_allows_bugfix_without_design_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Bug fix", "Fix the broken save", "session-main")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            replace_intake_section(intake_path, "Expected Behavior", "Save succeeds.")
            replace_intake_section(intake_path, "Actual Behavior", "Save fails silently.")
            replace_intake_section(intake_path, "Reproduction", "1. Click save")

            # Bugfix should NOT require design artifact fields
            result = promote_to_task(root, intake["intake_id"], "Bug fix", "Fix save", "bugfix", ["Save works"])
            self.assertIn("task_id", result)

    def test_promote_carry_design_artifact_into_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Design carry", "Build design carry", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(
                root,
                intake["intake_id"],
                final_expected_effect="User sees the feature working.",
                approach_options="Approach A: direct.\nApproach B: event-driven.",
                chosen_approach="Approach B: event-driven.",
                final_implementation_plan="1. Add event bus\n2. Wire handlers\n3. Verify",
                validation="Run event flow verification.",
                approval="Approved by user.",
            )

            promoted = promote_to_task(root, intake["intake_id"], "Design carry", "Build design carry", "design", ["Carry works"])
            task_dir = root / ".just-demand" / "state" / "active" / promoted["task_id"]
            task = read_json(task_dir / "task.json")
            self.assertEqual(task["clarification"]["final_expected_effect"], "User sees the feature working.")
            self.assertEqual(task["clarification"]["approach_options"], "Approach A: direct.\nApproach B: event-driven.")
            self.assertEqual(task["clarification"]["chosen_approach"], "Approach B: event-driven.")
            self.assertEqual(task["clarification"]["final_implementation_plan"], "1. Add event bus\n2. Wire handlers\n3. Verify")
            self.assertEqual(task["clarification"]["validation"], "Run event flow verification.")
            self.assertEqual(task["clarification"]["approval"], "Approved by user.")


    def test_checkpoint_commit_skips_without_impact_scope(self):
        """Checkpoint commit should require explicit impact scope."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)

            intake = create_intake(root, "No impact commit", "Test commit without impact", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "No impact", "Test", "implementation", ["Works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "No impact.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])

            # Do NOT set impact — checkpoint should skip to avoid unrelated changes.
            (root / "tracked.txt").write_text("updated content\n", encoding="utf-8")

            result = complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            self.assertFalse(result["checkpoint_commit"]["created"])
            self.assertEqual(result["checkpoint_commit"]["reason"], "missing_impact_scope")
            self.assertEqual(result["checkpoint_commit"]["paths"], [])

            latest_log = git_stdout(root, "log", "--oneline", "-1")
            self.assertRegex(latest_log, r"^[0-9a-f]+ chore: seed repo")

    def test_multiple_checkpoint_commits_per_task(self):
        """Same task should support multiple checkpoint commits over its lifecycle."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)

            intake = create_intake(root, "Multi commit", "Test multiple commits", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Multi commit", "Test", "implementation", ["Works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Multi commit.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])

            # First change + checkpoint
            (root / "file_a.txt").write_text("first change\n", encoding="utf-8")
            mark_task(root, task_id, "executing", impact=["file_a.txt"])
            complete_verification(root, task_id, "passed", "First checkpoint", auto_archive=False)

            task = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertTrue(task["checkpoint_commit"]["created"])
            self.assertEqual(task["checkpoint_commit"]["paths"], ["file_a.txt"])

            # Set task back to executing for second round
            mark_task(root, task_id, "executing", impact=["file_b.txt"])
            (root / "file_b.txt").write_text("second change\n", encoding="utf-8")

            complete_verification(root, task_id, "passed", "Second checkpoint", auto_archive=False)

            task = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertTrue(task["checkpoint_commit"]["created"])
            self.assertEqual(task["checkpoint_commit"]["paths"], ["file_b.txt"])

            # Both commits should be in git log
            log_lines = git_stdout(root, "log", "--oneline", "-3").splitlines()
            self.assertGreaterEqual(len(log_lines), 2)
            first_msg = log_lines[-1] if len(log_lines) >= 2 else log_lines[0]
            second_msg = log_lines[0]
            self.assertIn("multi commit", second_msg.lower())

    def test_standalone_checkpoint_commit_cli(self):
        """Standalone checkpoint-commit CLI should create a commit without archiving."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)

            intake = create_intake(root, "Standalone cp", "Test standalone", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Standalone cp", "Test", "implementation", ["Works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Standalone.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])

            # Mark verification as passed so the checkpoint-commit script doesn't fail
            from workflow_core import update_task
            update_task(root, task_id, {"verification_status": "passed"})

            # Make a scoped change
            (root / "tracked.txt").write_text("standalone change\n", encoding="utf-8")
            mark_task(root, task_id, "executing", impact=["tracked.txt"])

            script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "checkpoint-commit", task_id],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)

            self.assertTrue(payload["created"])
            self.assertIn("tracked.txt", payload["paths"])

            # Task should still be active (not archived)
            active_dir = tasks_dir(root) / "active" / task_id
            self.assertTrue(active_dir.is_dir())

            latest_log = git_stdout(root, "log", "--oneline", "-1")
            self.assertRegex(latest_log, r"^[0-9a-f]+ feat: checkpoint standalone cp")

    def test_checkpoint_commit_missing_impact_reason_present_in_events(self):
        """When no impact scope is set, the skip reason should be recorded in events."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)

            intake = create_intake(root, "Fallback test", "Test fallback note", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Fallback test", "Test", "implementation", ["Works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Fallback.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])

            # No impact set
            (root / "tracked.txt").write_text("fallback change\n", encoding="utf-8")

            result = complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            self.assertFalse(result["checkpoint_commit"]["created"])
            self.assertEqual(result["checkpoint_commit"].get("reason"), "missing_impact_scope")
            task_events = [json.loads(line) for line in task_event_path(root, task_id).read_text(encoding="utf-8").splitlines() if line]
            skipped = [event for event in task_events if event["type"] == "checkpoint_commit_skipped"]
            self.assertEqual(len(skipped), 1)
            self.assertIn("missing_impact_scope", skipped[0]["summary"])

    def test_where_cli_prints_script_path_and_repo_root(self):
        import subprocess

        script = REPO_ROOT / ".just-demand" / "scripts" / "task.py"
        result = subprocess.run(
            [sys.executable, str(script), "where"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("global CLI: just-demand", result.stdout)
        self.assertIn("just-demand", result.stdout)
        self.assertIn("repo root:", result.stdout)
        self.assertIn(str(REPO_ROOT.resolve()), result.stdout)
        self.assertIn("To invoke against a project:", result.stdout)
        self.assertIn(f"just-demand {REPO_ROOT.resolve()} list-active", result.stdout)

    def test_where_cli_project_flag_includes_invocation(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(project), "where"],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("To invoke against a project:", result.stdout)
            self.assertIn(str(project.resolve()), result.stdout)
            self.assertIn("list-active", result.stdout)

    def test_init_cli_output_includes_invocation_hint(self):
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
            self.assertIn("Project invocation:", result.stdout)
            self.assertIn(str(root.resolve()), result.stdout)
            self.assertIn("list-active", result.stdout)

    def test_doctor_cli_includes_invocation_hint_on_stderr(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = REPO_ROOT / "just-demand"
            # First init so the project has a .just-demand directory
            subprocess.run(
                [sys.executable, str(script), str(root), "init"],
                text=True,
                capture_output=True,
                check=True,
            )
            # Now doctor: stdout must remain valid JSON; stderr carries the hint
            result = subprocess.run(
                [sys.executable, str(script), str(root), "doctor"],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["project"]["just_demand_dir_exists"])
            self.assertIn("Project invocation:", result.stderr)
            self.assertIn("just-demand", result.stderr)
            self.assertIn(str(root.resolve()), result.stderr)

    def test_doctor_cli_no_invocation_hint_when_project_not_initialized(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fresh"
            root.mkdir()
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "doctor"],
                text=True,
                capture_output=True,
                check=True,
            )
            # No project state, so no hint should be emitted
            self.assertNotIn("Project invocation:", result.stderr)

    # -----------------------------------------------------------------------
    # task_is_ready_for_execution
    # -----------------------------------------------------------------------

    def test_task_is_ready_for_execution_ready_design(self):
        from workflow_core import task_is_ready_for_execution

        task = {
            "type": "design",
            "clarification": {
                "scope": "Settings flow only.",
                "blocking_questions": [],
                "final_expected_effect": "User can save settings.",
                "chosen_approach": "Approach A.",
                "final_implementation_plan": "1. Add handler",
                "approval": "Approved.",
            },
        }
        self.assertTrue(task_is_ready_for_execution(task))

    def test_task_is_ready_for_execution_missing_scope(self):
        from workflow_core import task_is_ready_for_execution

        task = {
            "type": "design",
            "clarification": {
                "scope": "",
                "blocking_questions": [],
                "final_expected_effect": "User can save settings.",
                "chosen_approach": "Approach A.",
                "final_implementation_plan": "1. Add handler",
                "approval": "Approved.",
            },
        }
        self.assertFalse(task_is_ready_for_execution(task))

    def test_task_is_ready_for_execution_blocking_questions(self):
        from workflow_core import task_is_ready_for_execution

        task = {
            "type": "design",
            "clarification": {
                "scope": "Settings flow only.",
                "blocking_questions": ["Should this affect the undo stack?"],
                "final_expected_effect": "User can save settings.",
                "chosen_approach": "Approach A.",
                "final_implementation_plan": "1. Add handler",
                "approval": "Approved.",
            },
        }
        self.assertFalse(task_is_ready_for_execution(task))

    def test_task_is_ready_for_execution_missing_design_fields(self):
        from workflow_core import task_is_ready_for_execution

        task = {
            "type": "design",
            "clarification": {
                "scope": "Settings flow only.",
                "blocking_questions": [],
                "final_expected_effect": "",
                "chosen_approach": "",
                "final_implementation_plan": "",
                "approval": "",
            },
        }
        self.assertFalse(task_is_ready_for_execution(task))

    def test_task_is_ready_for_execution_bugfix_needs_expected_actual_reproduction(self):
        from workflow_core import task_is_ready_for_execution

        task = {
            "type": "bugfix",
            "clarification": {
                "scope": "Save flow.",
                "blocking_questions": [],
                "expected_behavior": "Save succeeds.",
                "actual_behavior": "Save fails.",
                "reproduction": "1. Click save.",
            },
        }
        self.assertTrue(task_is_ready_for_execution(task))

        task["clarification"]["expected_behavior"] = ""
        self.assertFalse(task_is_ready_for_execution(task))

    def test_task_is_ready_for_execution_ui_visible_lifecycle_fields(self):
        from workflow_core import task_is_ready_for_execution

        task = {
            "title": "Animate launcher rows",
            "goal": "Make the list reveal feel smooth.",
            "type": "design",
            "clarification": {
                "scope": "Launcher rows only.",
                "blocking_questions": [],
                "final_expected_effect": "Rows reveal with the launcher.",
                "chosen_approach": "Staggered fade and slide.",
                "final_implementation_plan": "1. Clarify lifecycle\n2. Implement animation",
                "approval": "Approved.",
                "opening": "First frame shows the launcher shell with the first row barely visible.",
                "during_transition": "Rows fade up in staggered order from the launcher anchor.",
                "after_open": "The steady list matches the existing layout.",
                "interrupt_behavior": "Typing or closing cancels the animation cleanly.",
                "anti_outcomes": "No flash, clipping, or repeated replay.",
                "needs_ui_visible_lifecycle_clarification": True,
            },
        }
        self.assertTrue(task_is_ready_for_execution(task))

        task["clarification"]["anti_outcomes"] = ""
        self.assertFalse(task_is_ready_for_execution(task))

    # -----------------------------------------------------------------------
    # get_missing_execution_fields
    # -----------------------------------------------------------------------

    def test_get_missing_execution_fields_scope_only(self):
        from workflow_core import get_missing_execution_fields

        task = {
            "type": "design",
            "clarification": {
                "scope": "",
                "blocking_questions": [],
                "final_expected_effect": "Works.",
                "chosen_approach": "A.",
                "final_implementation_plan": "1. Do it",
                "approval": "Approved.",
            },
        }
        self.assertEqual(get_missing_execution_fields(task), ["Scope"])

    def test_get_missing_execution_fields_all_design_fields(self):
        from workflow_core import get_missing_execution_fields

        task = {
            "type": "design",
            "clarification": {
                "scope": "",
                "blocking_questions": [],
                "final_expected_effect": "",
                "chosen_approach": "",
                "final_implementation_plan": "",
                "approval": "",
            },
        }
        missing = get_missing_execution_fields(task)
        self.assertIn("Scope", missing)
        self.assertIn("Final Expected Effect", missing)
        self.assertIn("Chosen Approach", missing)
        self.assertIn("Final Implementation Plan", missing)
        self.assertIn("Approval", missing)

    def test_get_missing_execution_fields_blocking_questions(self):
        from workflow_core import get_missing_execution_fields

        task = {
            "type": "bugfix",
            "clarification": {
                "scope": "Save flow.",
                "blocking_questions": ["Should this affect undo?"],
                "expected_behavior": "Save works.",
                "actual_behavior": "Save fails.",
                "reproduction": "1. Click save.",
            },
        }
        self.assertIn("Blocking Questions", get_missing_execution_fields(task))

    def test_get_missing_execution_fields_returns_empty_for_ready_bugfix(self):
        from workflow_core import get_missing_execution_fields

        task = {
            "type": "bugfix",
            "clarification": {
                "scope": "Save flow.",
                "blocking_questions": [],
                "expected_behavior": "Save works.",
                "actual_behavior": "Save fails.",
                "reproduction": "1. Click save.",
            },
        }
        self.assertEqual(get_missing_execution_fields(task), [])

    def test_get_missing_execution_fields_returns_empty_for_ready_design(self):
        from workflow_core import get_missing_execution_fields

        task = {
            "type": "design",
            "clarification": {
                "scope": "Settings.",
                "blocking_questions": [],
                "final_expected_effect": "User can save.",
                "chosen_approach": "A.",
                "final_implementation_plan": "1. Add handler.",
                "approval": "Approved.",
            },
        }
        self.assertEqual(get_missing_execution_fields(task), [])

    def test_get_missing_execution_fields_ui_visible_lifecycle_fields(self):
        from workflow_core import get_missing_execution_fields

        task = {
            "title": "Reveal launcher rows",
            "goal": "Make the rows animate in.",
            "type": "implementation",
            "clarification": {
                "scope": "Launcher rows only.",
                "blocking_questions": [],
                "final_expected_effect": "Rows reveal with the tray.",
                "chosen_approach": "Fade and slide.",
                "final_implementation_plan": "1. Add animation\n2. Verify.",
                "approval": "Approved.",
                "opening": "First frame shows the tray with hidden rows.",
                "during_transition": "Rows fade and slide in from below.",
                "after_open": "Stable state matches the current list.",
                "interrupt_behavior": "Typing cancels the reveal.",
                "anti_outcomes": "No flash or clipping.",
                "needs_ui_visible_lifecycle_clarification": True,
            },
        }
        self.assertEqual(get_missing_execution_fields(task), [])

        task["clarification"]["opening"] = ""
        self.assertIn("Opening", get_missing_execution_fields(task))

    # -----------------------------------------------------------------------
    # Contract registry: active_contracts and gate levels
    # -----------------------------------------------------------------------

    def test_contract_detection_visible_effect_from_text(self):
        """Text with UI/animation keywords triggers visible_effect contract."""
        from workflow_core import _detect_active_contracts
        self.assertIn("visible_effect", _detect_active_contracts("Animate the launcher rows with stagger"))
        self.assertIn("visible_effect", _detect_active_contracts("fade in the new UI elements"))
        self.assertNotIn("visible_effect", _detect_active_contracts("Update the database schema"))

    def test_contract_detection_visible_effect_from_task_type(self):
        """Task type 'ui' or 'ux' triggers visible_effect."""
        from workflow_core import _detect_active_contracts_for_intake
        contracts = _detect_active_contracts_for_intake("ui", "Build a new panel", {})
        self.assertIn("visible_effect", contracts)
        contracts = _detect_active_contracts_for_intake("implementation", "Fix database query", {})
        self.assertNotIn("visible_effect", contracts)

    def test_contract_detection_ordered_flow(self):
        """Text with sequential/ordered keywords triggers ordered_flow contract."""
        from workflow_core import _detect_active_contracts
        self.assertIn("ordered_flow", _detect_active_contracts("This must run in strict sequential order"))
        self.assertIn("ordered_flow", _detect_active_contracts("Step-by-step dependency chain"))
        self.assertIn("ordered_flow", _detect_active_contracts("串行执行任务"))
        self.assertNotIn("ordered_flow", _detect_active_contracts("Update the database schema"))

    def test_contract_detection_safety_boundary(self):
        """Text with safety/destructive keywords triggers safety_boundary contract."""
        from workflow_core import _detect_active_contracts
        self.assertIn("safety_boundary", _detect_active_contracts("This is a destructive irreversible operation"))
        self.assertIn("safety_boundary", _detect_active_contracts("Implement rollback and revert logic"))
        self.assertIn("safety_boundary", _detect_active_contracts("破坏性操作需要权限"))
        self.assertNotIn("safety_boundary", _detect_active_contracts("Update the database schema"))

    def test_contract_detection_observability(self):
        """Text with logging/monitoring keywords triggers observability contract."""
        from workflow_core import _detect_active_contracts
        self.assertIn("observability", _detect_active_contracts("Add logging and monitoring"))
        self.assertIn("observability", _detect_active_contracts("Implement tracing and metrics"))
        self.assertIn("observability", _detect_active_contracts("配置监控和告警"))
        self.assertNotIn("observability", _detect_active_contracts("Update the database schema"))

    def test_contract_false_positive_low_risk_task(self):
        """Ordinary low-risk task text should not trigger any contract."""
        from workflow_core import _detect_active_contracts
        text = "Update the database schema for the new user table"
        contracts = _detect_active_contracts(text)
        self.assertEqual(len(contracts), 0)

    def test_contract_registry_in_build_clarification_payload(self):
        """Promoted task should carry active_contracts and contract_gate_levels."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Stagger animation", "Animate rows with stagger fade-in", "session-main")
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            set_intake_scope(root, intake["intake_id"], "Launcher reveal only.")
            set_intake_design_artifact(
                root,
                intake["intake_id"],
                final_expected_effect="Rows reveal with staggered fade.",
                chosen_approach="Use lifecycle clarification first.",
                final_implementation_plan="1. Confirm lifecycle\n2. Implement",
                validation="Verify lifecycle behavior.",
                approval="Approved.",
            )
            replace_intake_section(intake_path, "Opening", "Shell visible, rows hidden.")
            replace_intake_section(intake_path, "During Transition", "Rows fade in staggered.")
            replace_intake_section(intake_path, "After Open", "Stable list matches UI.")
            replace_intake_section(intake_path, "Interrupt Behavior", "Typing cancels reveal.")
            replace_intake_section(intake_path, "Anti-Outcomes", "No flash or clipping.")

            promoted = promote_to_task(root, intake["intake_id"], "Stagger animation", "Animate rows", "implementation", ["Works"])
            task = read_json(root / ".just-demand" / "state" / "active" / promoted["task_id"] / "task.json")
            clarification = task["clarification"]
            self.assertIn("visible_effect", clarification.get("active_contracts", []))
            gate_levels = clarification.get("contract_gate_levels", {})
            self.assertEqual(gate_levels.get("visible_effect"), "hard")
            self.assertTrue(clarification.get("needs_ui_visible_lifecycle_clarification"))

    def test_contract_registry_ordered_flow_does_not_block_promotion(self):
        """ordered_flow contract with reminder gate should not block promotion."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Ordered task", "This must run in strict sequential order", "session-main")
            set_intake_scope(root, intake["intake_id"], "Ordered execution.")
            set_intake_design_artifact(root, intake["intake_id"])
            # Should promote fine even though ordered_flow is detected
            promoted = promote_to_task(root, intake["intake_id"], "Ordered task", "Ordered execution", "implementation", ["Works"])
            task = read_json(root / ".just-demand" / "state" / "active" / promoted["task_id"] / "task.json")
            clarification = task["clarification"]
            self.assertIn("ordered_flow", clarification.get("active_contracts", []))
            self.assertEqual(clarification.get("contract_gate_levels", {}).get("ordered_flow"), "reminder")

    # -----------------------------------------------------------------------
    # show_task_readiness
    # -----------------------------------------------------------------------

    def test_show_task_readiness_ready_design(self):
        from workflow_core import show_task_readiness

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Readiness ready", "Ready task", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Readiness ready", "Ready task", "design", ["Ready"])
            task_id = promoted["task_id"]

            result = show_task_readiness(root, task_id)
            self.assertEqual(result["task_id"], task_id)
            self.assertEqual(result["status"], "planning")
            self.assertTrue(result["ready"])
            self.assertEqual(result["missing"], [])
            self.assertTrue(result["writes_allowed"])
            self.assertIn("execution-ready", result["recommended_recovery"])
            self.assertEqual(result["current_state"], "planning")
            self.assertTrue(result["safe_to_continue"])
            self.assertEqual(result["blocked_reason"], "")
            self.assertEqual(result["recommended_next"], "Task is execution-ready. Start execution when ready.")

    def test_show_task_readiness_not_ready_missing_fields(self):
        from workflow_core import show_task_readiness, write_json_atomic

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Not ready", "Not ready task", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Not ready", "Not ready", "implementation", ["Not ready"])
            task_id = promoted["task_id"]

            # Clear chosen_approach to make the task not-ready while keeping it active
            task_path = tasks_dir(root) / "active" / task_id / "task.json"
            task = read_json(task_path)
            task["clarification"]["chosen_approach"] = ""
            write_json_atomic(task_path, task)

            result = show_task_readiness(root, task_id)
            self.assertEqual(result["task_id"], task_id)
            self.assertFalse(result["ready"])
            self.assertIn("Chosen Approach", result["missing"])
            self.assertTrue(result["writes_allowed"])
            self.assertIn("update-clarification", result["recommended_recovery"])
            self.assertEqual(result["current_state"], "planning")
            self.assertFalse(result["safe_to_continue"])
            self.assertIn("Missing required clarification fields", result["blocked_reason"])
            self.assertEqual(result["recommended_next"], result["recommended_recovery"])

    def test_show_task_readiness_ui_visible_lifecycle_missing_fields(self):
        from workflow_core import show_task_readiness, write_json_atomic

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "UI readiness", "Animate launcher rows with stagger fade", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            replace_intake_section(root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md", "Opening", "First frame shows the launcher shell.")
            replace_intake_section(root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md", "During Transition", "Rows fade and slide in.")
            replace_intake_section(root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md", "After Open", "Stable list matches current UI.")
            replace_intake_section(root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md", "Interrupt Behavior", "Typing cancels the reveal.")
            replace_intake_section(root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md", "Anti-Outcomes", "No flash or clipping.")
            promoted = promote_to_task(root, intake["intake_id"], "UI readiness", "Animate launcher rows with stagger fade", "implementation", ["UI works"])
            task_id = promoted["task_id"]

            task_path = tasks_dir(root) / "active" / task_id / "task.json"
            task = read_json(task_path)
            task["clarification"]["opening"] = ""
            write_json_atomic(task_path, task)

            result = show_task_readiness(root, task_id)
            self.assertFalse(result["ready"])
            self.assertIn("Opening", result["missing"])
            self.assertIn("update-clarification", result["recommended_recovery"])

    def test_show_task_readiness_writes_not_allowed_in_paused(self):
        from workflow_core import mark_task, show_task_readiness

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Paused readiness", "Paused task", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Paused readiness", "Paused task", "design", ["Paused"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "paused")
            result = show_task_readiness(root, task_id)
            self.assertEqual(result["status"], "paused")
            self.assertFalse(result["writes_allowed"])
            self.assertIn("change status", result["recommended_recovery"])

    def test_show_task_readiness_writes_not_allowed_in_blocked(self):
        from workflow_core import mark_task, show_task_readiness

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Blocked readiness", "Blocked task", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Blocked readiness", "Blocked task", "design", ["Blocked"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "blocked")
            result = show_task_readiness(root, task_id)
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["writes_allowed"])
            self.assertIn("change status", result["recommended_recovery"])

    def test_show_task_readiness_writes_not_allowed_in_done(self):
        from workflow_core import complete_verification, create_validation_revision, show_task_readiness, start_execution

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Done readiness", "Done task", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Done readiness", "Done task", "design", ["Done"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Done readiness.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            result = show_task_readiness(root, task_id)
            self.assertEqual(result["status"], "done")
            self.assertFalse(result["writes_allowed"])
            self.assertIn("complete", result["recommended_recovery"])

    def test_show_task_readiness_missing_task(self):
        from workflow_core import show_task_readiness

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)

            with self.assertRaises(FileNotFoundError):
                show_task_readiness(root, "nonexistent-task")

    def test_show_task_readiness_cli_ready(self):
        import subprocess

        from workflow_core import promote_to_task

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI readiness", "CLI ready", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI readiness", "CLI ready", "design", ["CLI ready"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "show-readiness", task_id],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["task_id"], task_id)
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["missing"], [])
            self.assertTrue(payload["writes_allowed"])
            self.assertTrue(payload["safe_to_continue"])
            self.assertIn("task_id", payload)
            self.assertIn("status", payload)
            self.assertIn("write_allowed_statuses", payload)
            self.assertIn("current_state", payload)
            self.assertIn("blocked_reason", payload)
            self.assertIn("recommended_next", payload)

            self.assertIn("Current:", result.stderr)
            self.assertIn("Safe to continue: yes", result.stderr)
            self.assertIn("Recommended next:", result.stderr)

    def test_show_task_readiness_cli_blocked_outputs_diagnostic_card(self):
        import subprocess

        from workflow_core import promote_to_task, write_json_atomic

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI blocked", "CLI blocked", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI blocked", "CLI blocked", "implementation", ["CLI blocked"])
            task_id = promoted["task_id"]

            task_path = tasks_dir(root) / "active" / task_id / "task.json"
            task = read_json(task_path)
            task["clarification"]["chosen_approach"] = ""
            write_json_atomic(task_path, task)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "show-readiness", task_id],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ready"])
            self.assertFalse(payload["safe_to_continue"])
            self.assertIn("blocked_reason", payload)
            self.assertIn("recommended_next", payload)
            self.assertIn("Why blocked:", result.stderr)
            self.assertIn("Safe to continue: no", result.stderr)
            self.assertIn("Missing fields:", result.stderr)
            self.assertIn("Recommended next:", result.stderr)

    def test_show_task_readiness_cli_missing_task(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "show-readiness", "nonexistent-task"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("not found", payload["message"])

    # -----------------------------------------------------------------------
    # execution packet
    # -----------------------------------------------------------------------

    def test_build_execution_packet_prefers_selected_subtask_and_role_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Packet task", "Build packet", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Packet task", "Build packet", "design", ["Works"])
            task_id = promoted["task_id"]

            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["subtasks"] = [
                {"id": "sub-1", "title": "Patch helper", "status": "done", "scope": "Old work"},
                {"id": "sub-2", "title": "Implement packet", "status": "open", "scope": "Current work"},
            ]
            write_json_atomic(task_dir / "task.json", task)

            packet = build_execution_packet(root, task_id, role="coder", hints={"focus": "Keep scope tight."})

            self.assertTrue(packet["ready"])
            self.assertEqual(packet["selected_subtask"]["id"], "sub-2")
            self.assertIn("Keep scope tight.", packet["focus"])
            self.assertIn("Current work", packet["focus"])
            self.assertGreaterEqual(len(packet["subtasks"]), 2)

    def test_build_execution_packet_flags_overweight_background(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Packet lint", "Build packet lint", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Packet lint", "Build packet lint", "design", ["Works"])
            task_id = promoted["task_id"]

            packet = build_execution_packet(
                root,
                task_id,
                role="tester",
                hints={"background_notes": ["x" * 500, "y" * 500, "z" * 500]},
            )

            self.assertTrue(any(item["code"] == "background_overweight" for item in packet["lint"]))
            rendered = render_execution_packet_markdown(packet)
            self.assertIn("## Lint", rendered)
            self.assertIn("background notes are too large", rendered.lower())

    def test_build_packet_cli_renders_markdown(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Packet CLI", "Build packet CLI", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Packet CLI", "Build packet CLI", "design", ["Works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "build-packet", task_id, "--role", "tester", "--format", "markdown"],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("# Execution Packet", result.stdout)
            self.assertIn("## Testing Targets", result.stdout)

    def test_render_context_cli_renders_markdown(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Render context", "Render packet markdown", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Render context", "Render packet markdown", "design", ["Works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "render-context", task_id, "--role", "coder"],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("# Execution Packet", result.stdout)
            self.assertIn("## Implementation Targets", result.stdout)

    def test_lint_packet_cli_reports_findings_and_exit_code(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Lint packet", "Lint packet CLI", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Lint packet", "Lint packet CLI", "design", ["Works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(root),
                    "lint-packet",
                    task_id,
                    "--hint",
                    "background_notes=" + ("x" * 1000),
                ],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["task_id"], task_id)
            self.assertTrue(payload["ready"])
            self.assertTrue(any(item["code"] == "background_overweight" for item in payload["lint"]))

    # -----------------------------------------------------------------------
    # update_task_clarification
    # -----------------------------------------------------------------------

    def test_update_task_clarification_string_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Clarify update", "Test update", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Clarify update", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            self.assertEqual(task["clarification"]["scope"], "Confirmed implementation scope.")

            from workflow_core import update_task_clarification

            result = update_task_clarification(root, task_id, {"scope": "Updated scope."})
            self.assertTrue(result["ok"])
            self.assertEqual(result["task_id"], task_id)
            self.assertTrue(result["ready"])

            task = read_json(task_dir / "task.json")
            self.assertEqual(task["clarification"]["scope"], "Updated scope.")

    def test_update_task_clarification_fills_missing_fields_and_becomes_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Fill gaps", "Test fill gaps", "s1")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            # Fill Final Expected Effect
            for heading, body in [
                ("Final Expected Effect", "User sees the expected result."),
                ("Chosen Approach", "Approach A: direct."),
                ("Final Implementation Plan", "1. Implement\n2. Verify"),
                ("Approval", "Approved."),
            ]:
                replace_intake_section(intake_path, heading, body)

            promoted = promote_to_task(root, intake["intake_id"], "Fill gaps", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            # Now strip a critical field to simulate incomplete task
            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["chosen_approach"] = ""
            write_json_atomic(task_dir / "task.json", task)

            from workflow_core import update_task_clarification, task_is_ready_for_execution

            self.assertFalse(task_is_ready_for_execution(task))

            result = update_task_clarification(root, task_id, {"chosen_approach": "Approach A: direct."})
            self.assertTrue(result["ok"])
            self.assertTrue(result["ready"])
            self.assertEqual(result["missing"], [])

            task = read_json(task_dir / "task.json")
            self.assertEqual(task["clarification"]["chosen_approach"], "Approach A: direct.")

    def test_update_task_clarification_invalid_field_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Invalid field", "Test invalid", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Invalid field", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            from workflow_core import update_task_clarification

            with self.assertRaisesRegex(ValueError, "Unknown clarification field"):
                update_task_clarification(root, task_id, {"nonexistent_field": "value"})

    def test_update_task_clarification_regenerates_open_questions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Open questions", "Test OQ", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Open questions", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            task_dir = tasks_dir(root) / "active" / task_id
            oq_path = task_dir / "open_questions.md"
            # Should start empty (no non_blocking_questions)
            self.assertNotIn("Should this feature", oq_path.read_text(encoding="utf-8"))

            from workflow_core import update_task_clarification

            update_task_clarification(root, task_id, {"non_blocking_questions": '["Should this feature be optional?"]'})
            oq_content = oq_path.read_text(encoding="utf-8")
            self.assertIn("Should this feature be optional?", oq_content)
            self.assertIn("Remaining Open Questions", oq_content)

    def test_update_task_clarification_nonexistent_task_raises(self):
        from workflow_core import update_task_clarification

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            with self.assertRaises(FileNotFoundError):
                update_task_clarification(root, "nonexistent-task", {"scope": "Test"})

    def test_update_task_clarification_blocked_on_done_status(self):
        from workflow_core import complete_verification, update_task_clarification

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Done task", "Test done", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Done task", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            from workflow_core import start_execution

            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "Done", auto_archive=False)

            with self.assertRaises(RuntimeError):
                update_task_clarification(root, task_id, {"scope": "Updated."})

    # -----------------------------------------------------------------------
    # update-clarification CLI
    # -----------------------------------------------------------------------

    def test_cli_update_clarification_success(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI update", "Test CLI update", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI update", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            # Strip chosen_approach to make task non-ready
            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["chosen_approach"] = ""
            write_json_atomic(task_dir / "task.json", task)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--field", "chosen_approach=Approach A: direct."],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["missing"], [])

            task = read_json(task_dir / "task.json")
            self.assertEqual(task["clarification"]["chosen_approach"], "Approach A: direct.")

    def test_cli_update_clarification_multiple_fields(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI multi", "Test multi CLI update", "s1")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            for heading, body in [
                ("Final Expected Effect", "User sees result."),
                ("Chosen Approach", "Approach A: direct."),
                ("Final Implementation Plan", "1. Implement\n2. Verify"),
                ("Approval", "Approved."),
            ]:
                replace_intake_section(intake_path, heading, body)
            promoted = promote_to_task(root, intake["intake_id"], "CLI multi", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            # Strip all design fields
            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["final_expected_effect"] = ""
            task["clarification"]["chosen_approach"] = ""
            task["clarification"]["final_implementation_plan"] = ""
            task["clarification"]["approval"] = ""
            write_json_atomic(task_dir / "task.json", task)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [
                    sys.executable, str(script), str(root), "update-clarification", task_id,
                    "--field", "final_expected_effect=User sees the result.",
                    "--field", "chosen_approach=Approach A.",
                    "--field", "final_implementation_plan=1. Do it.",
                    "--field", "approval=Approved.",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["ready"])

    def test_cli_update_clarification_unknown_field_rejected(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI unknown", "Test unknown", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI unknown", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--field", "bogus_field=value"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Unknown clarification field", payload["message"])

    def test_cli_update_clarification_invalid_field_format(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI format", "Test format", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI format", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--field", "no_equals"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Invalid --field format", result.stdout)

    # -----------------------------------------------------------------------
    # update-clarification --from-file
    # -----------------------------------------------------------------------

    def test_cli_update_clarification_from_file_updates_fields(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "From file", "Test from file", "s1")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            for heading, body in [
                ("Final Expected Effect", "User sees result."),
                ("Chosen Approach", "Approach A: direct."),
                ("Final Implementation Plan", "1. Implement\n2. Verify"),
                ("Approval", "Approved."),
            ]:
                replace_intake_section(intake_path, heading, body)
            promoted = promote_to_task(root, intake["intake_id"], "From file", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            # Strip fields to make task non-ready
            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["final_expected_effect"] = ""
            task["clarification"]["chosen_approach"] = ""
            task["clarification"]["final_implementation_plan"] = ""
            task["clarification"]["approval"] = ""
            write_json_atomic(task_dir / "task.json", task)

            # Write a JSON file with all fields
            clar_file = root / "clar-update.json"
            clar_file.write_text(json.dumps({
                "final_expected_effect": "User sees the feature.",
                "chosen_approach": "Approach A: direct impl.",
                "final_implementation_plan": "1. Do it.",
                "approval": "Approved.",
            }), encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--from-file", str(clar_file)],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["missing"], [])

            task = read_json(task_dir / "task.json")
            self.assertEqual(task["clarification"]["final_expected_effect"], "User sees the feature.")
            self.assertEqual(task["clarification"]["chosen_approach"], "Approach A: direct impl.")

    def test_cli_update_clarification_from_file_with_list_fields(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "From file list", "Test from file list", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "From file list", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            # Strip chosen_approach to make non-ready; add blocking questions via file
            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["chosen_approach"] = ""
            write_json_atomic(task_dir / "task.json", task)

            clar_file = root / "clar-list.json"
            clar_file.write_text(json.dumps({
                "chosen_approach": "Approach A: direct.",
                "blocking_questions": ["Should this affect undo?"],
            }), encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--from-file", str(clar_file)],
                text=True,
                capture_output=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["ready"])
            self.assertIn("Blocking Questions", payload["missing"])

            task = read_json(task_dir / "task.json")
            self.assertEqual(task["clarification"]["blocking_questions"], ["Should this affect undo?"])

    def test_cli_update_clarification_from_file_and_field_override(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "From file override", "Test override", "s1")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            for heading, body in [
                ("Final Expected Effect", "User sees result."),
                ("Chosen Approach", "Approach A: direct."),
                ("Final Implementation Plan", "1. Implement\n2. Verify"),
                ("Approval", "Approved."),
            ]:
                replace_intake_section(intake_path, heading, body)
            promoted = promote_to_task(root, intake["intake_id"], "From file override", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            # Strip only chosen_approach to test override — leave other required fields intact
            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["chosen_approach"] = ""
            write_json_atomic(task_dir / "task.json", task)

            # File sets a value (and fills other required fields for readiness),
            # --field overrides the file value for the same key
            clar_file = root / "clar-override.json"
            clar_file.write_text(json.dumps({
                "chosen_approach": "Approach from file.",
                "scope": "Scope from file.",
            }), encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [
                    sys.executable, str(script), str(root), "update-clarification", task_id,
                    "--from-file", str(clar_file),
                    "--field", "chosen_approach=Approach from CLI override.",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["ready"])

            task = read_json(task_dir / "task.json")
            # --field wins over --from-file for same key
            self.assertEqual(task["clarification"]["chosen_approach"], "Approach from CLI override.")
            # --from-file sets values that --field doesn't touch
            self.assertEqual(task["clarification"]["scope"], "Scope from file.")

    def test_cli_update_clarification_from_file_missing_path(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Missing file", "Test missing", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Missing file", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--from-file", "/nonexistent/path.json"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Clarification file not found", payload["message"])

    def test_cli_update_clarification_from_file_invalid_json(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Invalid json", "Test invalid json", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Invalid json", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            clar_file = root / "bad.json"
            clar_file.write_text("this is not json", encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--from-file", str(clar_file)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("not valid JSON", payload["message"])

    def test_cli_update_clarification_from_file_non_object(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Non object", "Test non object", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Non object", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            clar_file = root / "array.json"
            clar_file.write_text('["this", "is", "an", "array"]', encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--from-file", str(clar_file)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("must contain a JSON object", payload["message"])

    def test_cli_update_clarification_from_file_rejects_unknown_fields(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Unknown field", "Test unknown field", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Unknown field", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            clar_file = root / "unknown.json"
            clar_file.write_text(json.dumps({
                "scope": "Updated scope.",
                "nonexistent_field": "should be rejected",
            }), encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--from-file", str(clar_file)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Unknown clarification field", payload["message"])

    # -----------------------------------------------------------------------
    # update-clarification --from-file markdown section import
    # -----------------------------------------------------------------------

    def test_parse_markdown_clarification_fields_basic(self):
        """parse_markdown_clarification_fields maps recognised headings."""
        text = """\
## Scope
Test scope content

## Chosen Approach
Approach B: markdown import.

## Final Expected Effect
User sees the feature.
"""
        fields = parse_markdown_clarification_fields(text)
        self.assertEqual(fields["scope"], "Test scope content")
        self.assertEqual(fields["chosen_approach"], "Approach B: markdown import.")
        self.assertEqual(fields["final_expected_effect"], "User sees the feature.")

    def test_parse_markdown_clarification_fields_with_lists(self):
        """Blocking/Non-Blocking Questions headings become list fields."""
        text = """\
## Scope
Works with lists.

## Blocking Questions
- What about undo?
- Does it handle empty state?

## Non-Blocking Questions
- Could we improve perf later?
"""
        fields = parse_markdown_clarification_fields(text)
        self.assertEqual(fields["scope"], "Works with lists.")
        self.assertEqual(fields["blocking_questions"], ["What about undo?", "Does it handle empty state?"])
        self.assertEqual(fields["non_blocking_questions"], ["Could we improve perf later?"])

    def test_parse_markdown_clarification_fields_empty(self):
        """Empty text raises RuntimeError."""
        with self.assertRaises(RuntimeError) as ctx:
            parse_markdown_clarification_fields("")
        self.assertIn("No markdown sections", str(ctx.exception))

    def test_parse_markdown_clarification_fields_no_matches(self):
        """Text with ## headings but none recognised raises RuntimeError."""
        text = """\
## Totally Unknown Heading
Some body text.

## Another Bogus Section
More text.
"""
        with self.assertRaises(RuntimeError) as ctx:
            parse_markdown_clarification_fields(text)
        self.assertIn("No recognised clarification headings", str(ctx.exception))

    def test_parse_markdown_clarification_fields_expected_outcome_alias(self):
        """Expected Outcome maps to expected_behavior (same as Expected Behavior)."""
        text = """\
## Scope
Alias test.

## Expected Outcome
The system should do X.
"""
        fields = parse_markdown_clarification_fields(text)
        self.assertEqual(fields["expected_behavior"], "The system should do X.")

    def test_parse_markdown_clarification_fields_open_questions_alias(self):
        """Open Questions maps to non_blocking_questions (same as Non-Blocking Questions)."""
        text = """\
## Scope
Alias test.

## Open Questions
- Question one?
- Question two?
"""
        fields = parse_markdown_clarification_fields(text)
        self.assertEqual(fields["non_blocking_questions"], ["Question one?", "Question two?"])

    def test_cli_update_clarification_from_markdown_file(self):
        """--from-file with a ##-section markdown file works."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "MD file", "Test from markdown", "s1")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            for heading, body in [
                ("Final Expected Effect", "User sees result."),
                ("Chosen Approach", "Approach A."),
                ("Final Implementation Plan", "1. Impl"),
                ("Approval", "Approved."),
            ]:
                replace_intake_section(intake_path, heading, body)
            promoted = promote_to_task(root, intake["intake_id"], "MD file", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            # Strip fields to make non-ready
            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["final_expected_effect"] = ""
            task["clarification"]["chosen_approach"] = ""
            task["clarification"]["final_implementation_plan"] = ""
            task["clarification"]["approval"] = ""
            write_json_atomic(task_dir / "task.json", task)

            # Write a markdown section file
            md_file = root / "clar-update.md"
            md_file.write_text("""\
## Scope
Updated scope from markdown.

## Final Expected Effect
User sees the shiny new feature.

## Chosen Approach
Approach from markdown file.

## Final Implementation Plan
1. Write code
2. Test

## Approval
Approved by review.
""", encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--from-file", str(md_file)],
                text=True, capture_output=True, check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["missing"], [])
            reloaded = read_json(task_dir / "task.json")
            self.assertEqual(reloaded["clarification"]["scope"], "Updated scope from markdown.")
            self.assertEqual(reloaded["clarification"]["final_expected_effect"], "User sees the shiny new feature.")

    def test_cli_update_clarification_from_markdown_with_list_fields(self):
        """Markdown file with Blocking Questions heading works."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "MD lists", "Test md lists", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "MD lists", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["chosen_approach"] = ""
            write_json_atomic(task_dir / "task.json", task)

            md_file = root / "clar-list.md"
            md_file.write_text("""\
## Chosen Approach
Approach B: markdown.

## Blocking Questions
- Should this affect undo?
- Does it handle race conditions?
""", encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--from-file", str(md_file)],
                text=True, capture_output=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            # Blocking questions present -> not ready
            self.assertFalse(payload["ready"])
            self.assertIn("Blocking Questions", payload["missing"])
            reloaded = read_json(task_dir / "task.json")
            self.assertEqual(reloaded["clarification"]["blocking_questions"],
                             ["Should this affect undo?", "Does it handle race conditions?"])

    def test_cli_update_clarification_from_markdown_unknown_headings_ignored(self):
        """Unknown headings in markdown are silently ignored (not rejected)."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "MD unknown", "Test unknown headings", "s1")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            for heading, body in [
                ("Final Expected Effect", "User sees result."),
                ("Chosen Approach", "Approach A."),
                ("Final Implementation Plan", "1. Impl"),
                ("Approval", "Approved."),
            ]:
                replace_intake_section(intake_path, heading, body)
            promoted = promote_to_task(root, intake["intake_id"], "MD unknown", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            # Strip a field
            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["chosen_approach"] = ""
            write_json_atomic(task_dir / "task.json", task)

            # Write markdown with a mix of recognised and unknown headings
            md_file = root / "clar-unknown.md"
            md_file.write_text("""\
## Chosen Approach
Approach from file.

## Random Notes
This is an unknown heading body.

## User Preference
Some preference text.
""", encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-clarification", task_id, "--from-file", str(md_file)],
                text=True, capture_output=True, check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            reloaded = read_json(task_dir / "task.json")
            self.assertEqual(reloaded["clarification"]["chosen_approach"], "Approach from file.")
            # Unknown headings did not create fields
            self.assertNotIn("Random Notes", reloaded["clarification"])

    def test_cli_update_clarification_from_markdown_then_field_override(self):
        """--field overrides markdown file values for same key."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "MD override", "Test md override", "s1")
            set_intake_scope(root, intake["intake_id"])
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake['intake_id']}.md"
            for heading, body in [
                ("Final Expected Effect", "User sees result."),
                ("Chosen Approach", "Approach A."),
                ("Final Implementation Plan", "1. Impl"),
                ("Approval", "Approved."),
            ]:
                replace_intake_section(intake_path, heading, body)
            promoted = promote_to_task(root, intake["intake_id"], "MD override", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            # Strip chosen_approach only
            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            task["clarification"]["chosen_approach"] = ""
            write_json_atomic(task_dir / "task.json", task)

            md_file = root / "clar-override.md"
            md_file.write_text("""\
## Scope
Scope from markdown.

## Chosen Approach
Approach from markdown (should be overridden).
""", encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [
                    sys.executable, str(script), str(root), "update-clarification", task_id,
                    "--from-file", str(md_file),
                    "--field", "chosen_approach=Approach from CLI wins.",
                ],
                text=True, capture_output=True, check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["ready"])
            reloaded = read_json(task_dir / "task.json")
            # --field wins
            self.assertEqual(reloaded["clarification"]["chosen_approach"], "Approach from CLI wins.")
            # --from-file values preserved
            self.assertEqual(reloaded["clarification"]["scope"], "Scope from markdown.")

    # -----------------------------------------------------------------------
    # start_verification
    # -----------------------------------------------------------------------

    def test_start_verification_from_executing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "SV exec", "Start verification", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "SV exec", "Start verification", "design", ["SV works"])
            task_id = promoted["task_id"]

            start_execution(root, task_id, ["just-demand-coder"])
            result = start_verification(root, task_id)

            self.assertEqual(result["status"], "verifying")
            task = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertEqual(task["status"], "verifying")

    def test_start_verification_from_tweaking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "SV tweak", "Start verification", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "SV tweak", "Start verification", "design", ["SV tweak works"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "tweaking")
            result = start_verification(root, task_id)

            self.assertEqual(result["status"], "verifying")

    def test_start_verification_from_debugging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "SV debug", "Start verification", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "SV debug", "Start verification", "design", ["SV debug works"])
            task_id = promoted["task_id"]

            mark_task(root, task_id, "debugging")
            result = start_verification(root, task_id)

            self.assertEqual(result["status"], "verifying")

    def test_start_verification_blocked_from_planning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "SV plan", "Start verification", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "SV plan", "Start verification", "design", ["SV plan blocked"])
            task_id = promoted["task_id"]

            with self.assertRaisesRegex(RuntimeError, "Cannot start verification"):
                start_verification(root, task_id)

    def test_start_verification_blocked_from_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "SV done", "Start verification", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "SV done", "Start verification", "design", ["SV done blocked"])
            task_id = promoted["task_id"]

            start_execution(root, task_id, ["just-demand-coder"])
            complete_verification(root, task_id, "passed", "Done", auto_archive=False)

            with self.assertRaisesRegex(RuntimeError, "Cannot start verification"):
                start_verification(root, task_id)

    def test_start_verification_cli_success(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "SV CLI", "Start verification via CLI", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "SV CLI", "Start verification via CLI", "design", ["SV CLI works"])
            task_id = promoted["task_id"]

            start_execution(root, task_id, ["just-demand-coder"])

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "start-verification", task_id],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "verifying")

    def test_start_verification_cli_blocked_from_planning(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "SV CLI plan", "Start verification via CLI", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "SV CLI plan", "Start verification via CLI", "design", ["SV CLI plan blocked"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "start-verification", task_id],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Cannot start verification", payload["message"])

    # -----------------------------------------------------------------------
    # intake_readiness_errors: recommends update-intake-section
    # -----------------------------------------------------------------------

    def test_intake_readiness_errors_recommends_update_intake_section(self):
        """intake_readiness_errors must recommend update-intake-section for empty fields."""
        from workflow_core import intake_readiness_errors

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Readiness recommendation", "Test recommendation", "session-main")

            # Design intake with no fields filled
            errors = intake_readiness_errors(root, intake["intake_id"], "design")
            self.assertGreater(len(errors), 0)

            # Every missing-field error should recommend update-intake-section
            for error in errors:
                with self.subTest(error=error):
                    self.assertIn("update-intake-section", error,
                                  f"Error should recommend update-intake-section: {error}")

    def test_intake_readiness_bug_errors_recommend_update_intake_section(self):
        """Bug-related readiness errors must also recommend update-intake-section."""
        from workflow_core import intake_readiness_errors

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Bug readiness", "Bug: broken save", "session-main")

            # Bug intake with no bug fields filled
            errors = intake_readiness_errors(root, intake["intake_id"], "bugfix")
            self.assertGreater(len(errors), 0)

            # Expected Behavior, Actual Behavior, Reproduction should all recommend update-intake-section
            for error in errors:
                with self.subTest(error=error):
                    if "is required" in error:
                        self.assertIn("update-intake-section", error,
                                      f"Bug error should recommend update-intake-section: {error}")

    def test_intake_readiness_promote_error_shows_recommendation(self):
        """The RuntimeError from promote_to_task should include update-intake-section."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Promote recommendation", "Test promote recommendation", "session-main")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "promote", intake["intake_id"],
                 "Promote recommendation", "Test promote", "--type", "design", "--acceptance", "Works"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            # The error message must recommend update-intake-section
            self.assertIn("update-intake-section", payload["message"])

    def test_update_intake_section_fallback_still_succeeds(self):
        """Direct patch/edit of intake file (the fallback) must still succeed."""
        from workflow_core import update_intake_section

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Fallback intake", "Test fallback", "session-main")
            intake_id = intake["intake_id"]

            # Use the preferred command path — this must succeed
            result = update_intake_section(root, intake_id, "Scope", "Updated via update-intake-section command.")
            self.assertTrue(result["ok"])
            self.assertEqual(result["body"], "Updated via update-intake-section command.")

            # Verify the intake file was updated
            intake_path = root / ".just-demand" / "state" / "intake" / f"{intake_id}.md"
            text = intake_path.read_text(encoding="utf-8")
            self.assertIn("Updated via update-intake-section command.", text)


if __name__ == "__main__":
    unittest.main()
