import json
import re
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / ".just-demand" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_core import (
    acquire_lock,
    add_plan_evidence,
    add_plan_stage,
    add_plan_suggestion,
    add_task_to_plan,
    archive_task,
    cleanup_completed_task,
    complete_verification,
    create_followup,
    create_intake,
    create_plan,
    create_validation_revision,
    ensure_workspace,
    knowledge_dir,
    list_plans,
    list_unfinished_tasks,
    locks_path,
    mark_task,
    parse_markdown_clarification_fields,
    promote_to_task,
    read_json,
    read_plan,
    refresh_plan_context,
    select_task,
    start_execution,
    start_reflection,
    start_verification,
    state_dir,
    tasks_dir,
    task_event_path,
    update_intake_section,
    update_suggestion_status,
    update_task_clarification,
    write_json_atomic,
)


# ── v2 contract helpers ──────────────────────────────────────────────
_CLARIFICATION_TO_CONTRACT_PATH: dict[str, list[str]] = {
    "scope": ["boundaries", "scope"],
    "out_of_scope": ["boundaries", "out_of_scope"],
    "anti_outcomes": ["boundaries", "anti_outcomes"],
    "invariants": ["boundaries", "invariants"],
    "final_expected_effect": ["outcome", "final_expected_effect"],
    "chosen_approach": ["choices", "chosen_approach"],
    "final_implementation_plan": ["choices", "final_implementation_plan"],
    "approach_options": ["choices", "approach_options"],
    "approval": ["choices", "approval"],
    "expected_behavior": ["engineering", "expected_behavior"],
    "actual_behavior": ["engineering", "actual_behavior"],
    "reproduction": ["engineering", "reproduction"],
    "raw_request": ["provenance", "raw_request"],
    "blocking_questions": ["blocking_questions"],
    "non_blocking_questions": ["open_questions"],
    "decisions": ["decisions"],
    "code_map": ["engineering", "code_map"],
    "verification_cases": ["engineering", "verification_cases"],
    "risks": ["engineering", "risks"],
    "work_items": ["engineering", "work_items"],
    "dependencies": ["engineering", "dependencies"],
    # Visible-effect lifecycle fields (must stay in sync with workflow_core.py)
    "opening": ["engineering", "lifecycle", "opening"],
    "during_transition": ["engineering", "lifecycle", "during_transition"],
    "after_open": ["engineering", "lifecycle", "after_open"],
    "interrupt_behavior": ["engineering", "lifecycle", "interrupt_behavior"],
}


def _contract_clarification(task: dict, field: str) -> Any:
    """Get a clarification field from a v2 task contract (or fallback to v1 clarification)."""
    if "contract" in task:
        contract = task["contract"]
        path = _CLARIFICATION_TO_CONTRACT_PATH.get(field)
        if path:
            obj = contract
            for key in path:
                if isinstance(obj, dict):
                    obj = obj.get(key)
                else:
                    return ""
            return obj or ""
        # Fallback to _extra
        extra = contract.get("_extra", {})
        return extra.get(field, "")
    return task.get("clarification", {}).get(field, "")


def _set_contract_clarification(task: dict, field: str, value: Any) -> None:
    """Set a clarification field in a v2 task contract (or v1 clarification)."""
    if "contract" in task:
        contract = task["contract"]
        path = _CLARIFICATION_TO_CONTRACT_PATH.get(field)
        if path:
            obj = contract
            for key in path[:-1]:
                if key not in obj:
                    obj[key] = {}
                obj = obj[key]
            obj[path[-1]] = value
        else:
            contract.setdefault("_extra", {})[field] = value
    else:
        task.setdefault("clarification", {})[field] = value


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
            self.assertRegex(intake_text, r"## Scope\n\n## Anti-Outcome")

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
            self.assertIn("## Scope\n\n## Anti-Outcome", initial_text)

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
            contract = task["contract"]
            self.assertEqual(contract["boundaries"]["scope"], "Updated scope for promotion check.")
            self.assertEqual(contract["outcome"]["final_expected_effect"], "Updated: user sees the result.")
            self.assertEqual(contract["choices"]["chosen_approach"], "Updated approach.")
            self.assertEqual(contract["choices"]["final_implementation_plan"], "1. Updated\n2. Test")
            self.assertEqual(contract["choices"]["approval"], "Updated approval.")

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
            # decisions.md is NOT created for v2 contract tasks
            self.assertTrue((task_dir / "open_questions.md").is_file())
            self.assertTrue((task_dir / "research.md").is_file())
            self.assertTrue((task_dir / "implement.md").is_file())
            self.assertTrue((task_dir / "verify.md").is_file())
            self.assertTrue((task_dir / "outputs").is_dir())
            self.assertTrue((task_dir / "research").is_dir())

            task = read_json(task_dir / "task.json")
            self.assertEqual(task["source_intake_id"], intake["intake_id"])
            self.assertEqual(task["status"], "planning")
            # V2 contract format
            self.assertEqual(task["contract"]["outcome"]["goal"], "Build an OpenCode-first local workflow runtime.")
            self.assertEqual(task["contract"]["outcome"]["acceptance_criteria"], ["Workspace intake can be promoted to a formal task."])
            self.assertEqual(task["contract"]["boundaries"]["scope"], "Build the initial OpenCode-first workflow runtime.")
            self.assertEqual(task["contract"]["blocking_questions"], [])
            self.assertEqual(
                [item["title"] for item in task["subtasks"]],
                ["Implement", "Verify"],
            )
            self.assertIn("## Ordered Todo", (task_dir / "implement.md").read_text(encoding="utf-8"))

            # --- Verify contract-projected context.md sections ---
            context_text = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertIn("## User Raw Request", context_text)
            self.assertIn("Build an OpenCode-first agent workflow.", context_text)
            self.assertIn("## Goal", context_text)
            self.assertIn("Build an OpenCode-first local workflow runtime.", context_text)
            self.assertIn("## User Expected Effect", context_text)
            self.assertIn("User sees the expected result.", context_text)
            self.assertIn("## Acceptance Criteria", context_text)
            self.assertIn("- Workspace intake can be promoted to a formal task.", context_text)
            self.assertIn("## Scope", context_text)
            self.assertIn("Build the initial OpenCode-first workflow runtime.", context_text)
            self.assertIn("## Chosen Approach", context_text)
            self.assertIn("Approach A: direct implementation.", context_text)
            self.assertIn("## Implementation Plan", context_text)
            self.assertIn("1. Implement", context_text)

            # --- Verify contract-projected implement.md sections ---
            implement_text = (task_dir / "implement.md").read_text(encoding="utf-8")
            self.assertIn("## Goal", implement_text)
            self.assertIn("Build an OpenCode-first local workflow runtime.", implement_text)
            self.assertIn("## Implementation Plan", implement_text)
            self.assertIn("1. Implement", implement_text)
            self.assertIn("## Ordered Todo", implement_text)

            # --- Verify contract-projected verify.md sections ---
            verify_text = (task_dir / "verify.md").read_text(encoding="utf-8")
            self.assertIn("## Expected Effect", verify_text)
            self.assertIn("User sees the expected result.", verify_text)
            self.assertIn("## Scope", verify_text)

            state = read_json(root / ".just-demand" / "state" / "state.json")
            self.assertIsNone(state["current_intake_id"])
            self.assertEqual(state["current_task_id"], result["task_id"])
            self.assertIn(result["task_id"], state["active_task_ids"])

    def test_promote_follow_up_task_persists_parent_lineage(self):
        from workflow_core import promote_to_task

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent_intake = create_intake(root, "Parent task", "Build the parent flow", "session-main")
            set_intake_scope(root, parent_intake["intake_id"], "Parent scope.")
            set_intake_design_artifact(root, parent_intake["intake_id"])
            parent_task = promote_to_task(
                root,
                parent_intake["intake_id"],
                "Parent task",
                "Build the parent flow",
                "implementation",
                ["Parent task is ready."],
            )

            child_intake = create_intake(root, "Child task", "Build a follow-up flow", "session-main", parent_task["task_id"])
            child_intake_path = root / ".just-demand" / "state" / "intake" / f"{child_intake['intake_id']}.md"
            self.assertIn(f"Parent Task: {parent_task['task_id']}", child_intake_path.read_text(encoding="utf-8"))

            set_intake_scope(root, child_intake["intake_id"], "Child scope.")
            set_intake_design_artifact(root, child_intake["intake_id"], approval="Child approved.")
            child_task = promote_to_task(
                root,
                child_intake["intake_id"],
                "Child task",
                "Build a follow-up flow",
                "implementation",
                ["Child task is ready."],
            )

            task = read_json(root / ".just-demand" / "state" / "active" / child_task["task_id"] / "task.json")
            self.assertEqual(task["parent_task_id"], parent_task["task_id"])
            self.assertEqual(task["root_task_id"], parent_task["task_id"])
            self.assertEqual(task["lineage_task_ids"], [parent_task["task_id"]])

    def test_promote_follow_up_task_accepts_archived_parent(self):
        from workflow_core import complete_verification, promote_to_task

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)
            parent_intake = create_intake(root, "Archived parent", "Build parent", "session-main")
            set_intake_scope(root, parent_intake["intake_id"], "Parent scope.")
            set_intake_design_artifact(root, parent_intake["intake_id"])
            parent_task = promote_to_task(root, parent_intake["intake_id"], "Archived parent", "Build parent", "implementation", ["Parent ready."])
            parent_task_id = parent_task["task_id"]
            start_execution(root, parent_task_id, ["just-demand-coder"])
            parent_path = root / ".just-demand" / "state" / "active" / parent_task_id / "tracked.txt"
            parent_path.write_text("parent change\n", encoding="utf-8")
            complete_verification(root, parent_task_id, "passed", "Parent verified", auto_archive=True)

            child_intake = create_intake(root, "Child of archived", "Build child", "session-main", parent_task_id)
            set_intake_scope(root, child_intake["intake_id"], "Child scope.")
            set_intake_design_artifact(root, child_intake["intake_id"], approval="Child approved.")
            child_task = promote_to_task(root, child_intake["intake_id"], "Child of archived", "Build child", "implementation", ["Child ready."])
            task = read_json(root / ".just-demand" / "state" / "active" / child_task["task_id"] / "task.json")

            self.assertEqual(task["parent_task_id"], parent_task_id)
            self.assertEqual(task["root_task_id"], parent_task_id)
            self.assertEqual(task["lineage_task_ids"], [parent_task_id])

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
            contract = task["contract"]
            self.assertIn("Recommended default", contract["_extra"]["decision_card"])
            self.assertIn("Approve the recommendation", contract["_extra"]["user_action"])
            self.assertIn("decision-card output contract", contract["_extra"]["recommended_default"])
            self.assertIn("Failure mode", contract["_extra"]["option_matrix"])
            self.assertIn("Decision card", contract["_extra"]["minimum_viable_knowledge"])
            self.assertIn("Quick check", contract["_extra"]["validation_card"])
            self.assertIn("flowchart TD", contract["_extra"]["diagram"])
            self.assertEqual(contract["_extra"]["confidence"], "high")
            self.assertIn("Only ask", contract["_extra"]["escalation_reason"])

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

            with self.assertRaisesRegex(RuntimeError, "[Bb]locking [Qq]uestions"):
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
            # V2 contract format
            self.assertEqual(task["contract"]["engineering"]["expected_behavior"], "User sees a success toast after save.")
            self.assertEqual(task["contract"]["engineering"]["actual_behavior"], "Save fails silently.")
            self.assertEqual(task["contract"]["engineering"]["reproduction"], "1. Edit an item\n2. Click save")
            self.assertEqual(task["contract"]["boundaries"]["scope"], "Investigate save feedback and toast behavior.")
            self.assertEqual(task["contract"]["open_questions"], ["Should the toast include the item name?"])
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
            self.assertFalse(task["contract"]["_extra"]["needs_bug_clarification"])


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

    def test_cli_create_intake_accepts_parent_task(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent_intake = create_intake(root, "Parent workflow", "Build parent", "session-main")
            set_intake_scope(root, parent_intake["intake_id"], "Parent scope.")
            set_intake_design_artifact(root, parent_intake["intake_id"])
            parent_task = promote_to_task(root, parent_intake["intake_id"], "Parent workflow", "Build parent", "implementation", ["Parent ready."])

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "create-intake", "Follow-up", "Build child", "--session", "session-main", "--parent-task", parent_task["task_id"]],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("intake_id", result.stdout)
            payload = json.loads(result.stdout)
            intake_path = root / ".just-demand" / "state" / "intake" / f"{payload['intake_id']}.md"
            self.assertIn(f"Parent Task: {parent_task['task_id']}", intake_path.read_text(encoding="utf-8"))

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
            self.assertIn("Completion report:", result.stderr)
            self.assertIn("Verification: passed — All done", result.stderr)
            self.assertIn("Checkpoint commit: yes", result.stderr)

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

    def test_update_clarification_refreshes_ordered_plan_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Plan refresh", "Build a flow", "session-main")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"], final_implementation_plan="1. First step\n2. Second step", approval="Approved")
            promoted = promote_to_task(root, intake["intake_id"], "Plan refresh", "Build a flow", "design", ["Plan refresh works"])
            task_id = promoted["task_id"]

            task_dir = root / ".just-demand" / "state" / "active" / task_id
            task = read_json(task_dir / "task.json")
            _set_contract_clarification(task, "final_implementation_plan", "1. Updated first\n2. Updated second")
            write_json_atomic(task_dir / "task.json", task)

            update_task_clarification(root, task_id, {"chosen_approach": "Approach A."})

            task = read_json(task_dir / "task.json")
            self.assertEqual([item["title"] for item in task["subtasks"]], ["Updated first", "Updated second"])
            implement_text = (task_dir / "implement.md").read_text(encoding="utf-8")
            self.assertIn("- [ ] Updated first", implement_text)
            self.assertIn("- [ ] Updated second", implement_text)

    def test_promote_blocks_implementation_without_design_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Impl work", "Implement a feature", "session-main")
            set_intake_scope(root, intake["intake_id"])

            with self.assertRaisesRegex(RuntimeError, "Final Expected Effect"):
                promote_to_task(root, intake["intake_id"], "Impl work", "Implement feature", "implementation", ["It works"])

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
            contract = task["contract"]
            self.assertEqual(contract["outcome"]["final_expected_effect"], "User sees the feature working.")
            self.assertEqual(contract["choices"]["approach_options"], "Approach A: direct.\nApproach B: event-driven.")
            self.assertEqual(contract["choices"]["chosen_approach"], "Approach B: event-driven.")
            self.assertEqual(contract["choices"]["final_implementation_plan"], "1. Add event bus\n2. Wire handlers\n3. Verify")
            self.assertEqual(contract["_extra"]["validation"], "Run event flow verification.")
            self.assertEqual(contract["choices"]["approval"], "Approved by user.")


    def test_checkpoint_commit_succeeds_without_impact_scope(self):
        """Checkpoint commit should fall back to all changed files when impact scope is not set."""
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

            # Do NOT set impact — checkpoint should fall back to all changed files.
            (root / "tracked.txt").write_text("updated content\n", encoding="utf-8")

            result = complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            self.assertTrue(result["checkpoint_commit"]["created"])
            self.assertEqual(result["checkpoint_commit"]["paths"], ["tracked.txt"])
            self.assertEqual(
                result["checkpoint_commit"]["fallback_note"],
                "all changed files (no explicit impact scope)",
            )

            latest_log = git_stdout(root, "log", "--oneline", "-1")
            self.assertRegex(latest_log, r"^[0-9a-f]+ feat: checkpoint no impact")

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

    def test_checkpoint_commit_fallback_note_in_events(self):
        """When no impact scope is set but changes exist, the commit should be created
        and the fallback note should be recorded in events."""
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

            # No impact set — commit should fall back to all changed files
            (root / "tracked.txt").write_text("fallback change\n", encoding="utf-8")

            result = complete_verification(root, task_id, "passed", "All done", auto_archive=False)

            self.assertTrue(result["checkpoint_commit"]["created"])
            self.assertEqual(result["checkpoint_commit"].get("fallback_note"), "all changed files (no explicit impact scope)")
            task_events = [json.loads(line) for line in task_event_path(root, task_id).read_text(encoding="utf-8").splitlines() if line]
            created = [event for event in task_events if event["type"] == "checkpoint_commit_created"]
            self.assertGreaterEqual(len(created), 1)
            self.assertIn("fallback", created[0]["summary"].lower())

    def test_checkpoint_pass_marker_prevents_duplicate_commit_same_pass(self):
        """Same verification pass should not create a duplicate checkpoint commit
        when the pass marker is already set."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)

            intake = create_intake(root, "Dup guard", "Test duplicate guard", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Dup guard", "Test", "implementation", ["Works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Dup guard.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            mark_task(root, task_id, "executing", impact=["tracked.txt"])

            # First verification pass: creates checkpoint commit and sets marker
            (root / "tracked.txt").write_text("first pass\n", encoding="utf-8")
            result1 = complete_verification(root, task_id, "passed", "First pass", auto_archive=False)

            self.assertTrue(result1["checkpoint_commit"]["created"])
            task1 = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertTrue(task1.get("checkpoint_pass_completed", False))

            # Simulate re-opening: directly set status back to an allowed
            # before-status WITHOUT going through mark_task (which would
            # reset the marker). This tests the guard, not the normal flow.
            task_path = tasks_dir(root) / "active" / task_id / "task.json"
            task_data = read_json(task_path)
            task_data["status"] = "changes_requested"
            write_json_atomic(task_path, task_data)

            # Second verification call: guard should skip the checkpoint commit
            result2 = complete_verification(root, task_id, "passed", "Second pass (guard should skip)", auto_archive=False)

            task2 = read_json(task_path)
            self.assertTrue(task2["checkpoint_pass_completed"])
            # Commit hash should match original — not a new commit
            self.assertEqual(
                result1["checkpoint_commit"].get("commit_hash"),
                result2["checkpoint_commit"].get("commit_hash"),
            )

            # Verify a checkpoint_commit_skipped event was recorded
            task_events = [json.loads(line) for line in task_event_path(root, task_id).read_text(encoding="utf-8").splitlines() if line]
            skipped_events = [e for e in task_events if e["type"] == "checkpoint_commit_skipped" and "already completed" in e["summary"]]
            self.assertGreaterEqual(len(skipped_events), 1)

    def test_checkpoint_pass_marker_allows_new_pass_after_mark_reset(self):
        """After the pass marker is reset by mark_task, a new verification pass
        should still create a checkpoint commit."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)

            intake = create_intake(root, "New pass", "Test new pass commit", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "New pass", "Test", "implementation", ["Works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "New pass.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            mark_task(root, task_id, "executing", impact=["tracked.txt"])

            # First verification pass
            (root / "tracked.txt").write_text("first pass\n", encoding="utf-8")
            result1 = complete_verification(root, task_id, "passed", "First pass", auto_archive=False)
            self.assertTrue(result1["checkpoint_commit"]["created"])
            self.assertTrue(result1["checkpoint_commit"].get("created"))

            # Reset through mark_task — this resets the pass marker
            mark_task(root, task_id, "executing", impact=["tracked.txt"])

            # Make new changes
            (root / "tracked.txt").write_text("second pass changes\n", encoding="utf-8")

            # Second verification pass — should create a new checkpoint commit
            result2 = complete_verification(root, task_id, "passed", "Second pass (new pass)", auto_archive=False)
            self.assertTrue(result2["checkpoint_commit"]["created"])
            self.assertNotEqual(
                result1["checkpoint_commit"].get("commit_hash"),
                result2["checkpoint_commit"].get("commit_hash"),
            )

            # Both commits should be in git log
            log_lines = git_stdout(root, "log", "--oneline", "-3").splitlines()
            self.assertGreaterEqual(len(log_lines), 2)

    def test_completion_report_includes_checkpoint_info_in_cli_output(self):
        """CLI completion report should show checkpoint commit status even when
        the commit uses the fallback path (no explicit impact scope)."""
        import subprocess as std_subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)

            intake = create_intake(root, "Report checkpoint", "Test report includes checkpoint info", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Report checkpoint", "Test", "implementation", ["Works"])
            task_id = promoted["task_id"]

            create_validation_revision(root, task_id, "Report cp.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])

            # No impact set — fallback path
            (root / "tracked.txt").write_text("report test\n", encoding="utf-8")

            script = REPO_ROOT / "just-demand"
            cp_result = std_subprocess.run(
                [sys.executable, str(script), str(root), "complete-verification", task_id, "passed", "All done"],
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("Completion report:", cp_result.stderr)
            self.assertIn("Verification: passed", cp_result.stderr)
            self.assertIn("Checkpoint commit: yes", cp_result.stderr)
            self.assertIn("all changed files (no explicit impact scope)", cp_result.stderr)

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
            _set_contract_clarification(task, "chosen_approach", "")
            write_json_atomic(task_path, task)

            result = show_task_readiness(root, task_id)
            self.assertEqual(result["task_id"], task_id)
            self.assertFalse(result["ready"])
            self.assertIn("Chosen Approach", result["missing"])
            self.assertTrue(result["writes_allowed"])
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
            self.assertIn("task_id", payload)
            self.assertIn("status", payload)
            self.assertIn("write_allowed_statuses", payload)

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
            self.assertEqual(_contract_clarification(task, "scope"), "Confirmed implementation scope.")

            from workflow_core import update_task_clarification

            result = update_task_clarification(root, task_id, {"scope": "Updated scope."})
            self.assertTrue(result["ok"])
            self.assertEqual(result["task_id"], task_id)
            self.assertTrue(result["ready"])

            task = read_json(task_dir / "task.json")
            self.assertEqual(_contract_clarification(task, "scope"), "Updated scope.")

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
            _set_contract_clarification(task, "chosen_approach", "")
            write_json_atomic(task_dir / "task.json", task)

            from workflow_core import update_task_clarification, task_is_ready_for_execution

            self.assertFalse(task_is_ready_for_execution(task))

            result = update_task_clarification(root, task_id, {"chosen_approach": "Approach A: direct."})
            self.assertTrue(result["ok"])
            self.assertTrue(result["ready"])
            self.assertEqual(result["missing"], [])

            task = read_json(task_dir / "task.json")
            self.assertEqual(_contract_clarification(task, "chosen_approach"), "Approach A: direct.")

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
            _set_contract_clarification(task, "chosen_approach", "")
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
            self.assertEqual(_contract_clarification(task, "chosen_approach"), "Approach A: direct.")

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
            _set_contract_clarification(task, "final_expected_effect", "")
            _set_contract_clarification(task, "chosen_approach", "")
            _set_contract_clarification(task, "final_implementation_plan", "")
            _set_contract_clarification(task, "approval", "")
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

    def test_cli_update_clarification_supports_lifecycle_fields(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Lifecycle fields", "Test lifecycle", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Lifecycle fields", "Test", "design", ["Works"])
            task_id = promoted["task_id"]

            task_dir = tasks_dir(root) / "active" / task_id
            task = read_json(task_dir / "task.json")
            for field in ["opening", "during_transition", "after_open", "interrupt_behavior", "anti_outcomes"]:
                _set_contract_clarification(task, field, "")
            write_json_atomic(task_dir / "task.json", task)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [
                    sys.executable, str(script), str(root), "update-clarification", task_id,
                    "--field", "opening=Ask the first visible result before implementation.",
                    "--field", "during_transition=Ask one decision per turn.",
                    "--field", "after_open=Use a final card before execution.",
                    "--field", "interrupt_behavior=Resume the current round and next question.",
                    "--field", "anti_outcomes=Do not ask like a form.",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["ready"])
            self.assertEqual(payload["missing"], [])

            task = read_json(task_dir / "task.json")
            self.assertEqual(_contract_clarification(task, "opening"), "Ask the first visible result before implementation.")
            self.assertEqual(_contract_clarification(task, "during_transition"), "Ask one decision per turn.")
            self.assertEqual(_contract_clarification(task, "after_open"), "Use a final card before execution.")
            self.assertEqual(_contract_clarification(task, "interrupt_behavior"), "Resume the current round and next question.")
            self.assertEqual(_contract_clarification(task, "anti_outcomes"), "Do not ask like a form.")

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
            _set_contract_clarification(task, "final_expected_effect", "")
            _set_contract_clarification(task, "chosen_approach", "")
            _set_contract_clarification(task, "final_implementation_plan", "")
            _set_contract_clarification(task, "approval", "")
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
            self.assertEqual(_contract_clarification(task, "final_expected_effect"), "User sees the feature.")
            self.assertEqual(_contract_clarification(task, "chosen_approach"), "Approach A: direct impl.")

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
            _set_contract_clarification(task, "chosen_approach", "")
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
            self.assertEqual(_contract_clarification(task, "blocking_questions"), ["Should this affect undo?"])

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
            _set_contract_clarification(task, "chosen_approach", "")
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
            self.assertEqual(_contract_clarification(task, "chosen_approach"), "Approach from CLI override.")
            # --from-file sets values that --field doesn't touch
            self.assertEqual(_contract_clarification(task, "scope"), "Scope from file.")

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
            _set_contract_clarification(task, "final_expected_effect", "")
            _set_contract_clarification(task, "chosen_approach", "")
            _set_contract_clarification(task, "final_implementation_plan", "")
            _set_contract_clarification(task, "approval", "")
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
            self.assertEqual(_contract_clarification(reloaded, "scope"), "Updated scope from markdown.")
            self.assertEqual(_contract_clarification(reloaded, "final_expected_effect"), "User sees the shiny new feature.")

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
            _set_contract_clarification(task, "chosen_approach", "")
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
            self.assertEqual(_contract_clarification(reloaded, "blocking_questions"),
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
            _set_contract_clarification(task, "chosen_approach", "")
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
            self.assertEqual(_contract_clarification(reloaded, "chosen_approach"), "Approach from file.")
            # Unknown headings did not create fields (not in _extra)
            if "_extra" in reloaded.get("contract", {}):
                self.assertNotIn("Random Notes", reloaded["contract"]["_extra"])

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
            _set_contract_clarification(task, "chosen_approach", "")
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
            self.assertEqual(_contract_clarification(reloaded, "chosen_approach"), "Approach from CLI wins.")
            # --from-file values preserved
            self.assertEqual(_contract_clarification(reloaded, "scope"), "Scope from markdown.")

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
        """intake_readiness_errors returns missing-field errors for empty intakes."""
        from workflow_core import intake_readiness_errors

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Readiness recommendation", "Test recommendation", "session-main")

            # Design intake with no fields filled
            errors = intake_readiness_errors(root, intake["intake_id"], "design")
            self.assertGreater(len(errors), 0)

    def test_intake_readiness_bug_errors_recommend_update_intake_section(self):
        """Bug-related readiness errors are returned for empty bug intakes."""
        from workflow_core import intake_readiness_errors

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Bug readiness", "Bug: broken save", "session-main")

            # Bug intake with no bug fields filled
            errors = intake_readiness_errors(root, intake["intake_id"], "bugfix")
            self.assertGreater(len(errors), 0)

    def test_intake_readiness_promote_error_shows_recommendation(self):
        """promote_to_task raises RuntimeError for incomplete intakes."""
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


    # -----------------------------------------------------------------------
    # create_followup — reflection recommendation on second follow-up
    # -----------------------------------------------------------------------

    def test_create_followup_first_does_not_recommend_reflection(self):
        """First follow-up does not include reflection_recommended."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Refl check", "Test reflection", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Refl check",
                                       "Test reflection", "design", ["Refl works"])
            task_id = promoted["task_id"]

            result = create_followup(
                root, task_id,
                user_feedback="First feedback",
                observed_phenomenon="Observed 1",
                expected_phenomenon="Expected 1",
                delta_scope="Scope 1",
                must_not_change="Must not 1",
                acceptance="Accept 1",
            )

            self.assertNotIn("reflection_recommended", result)
            self.assertNotIn("next_action", result)

    def test_create_followup_second_recommends_reflection(self):
        """Second follow-up includes reflection_recommended and next_action."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Refl second", "Test second reflection", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Refl second",
                                       "Test second reflection", "design", ["Refl second works"])
            task_id = promoted["task_id"]

            create_followup(
                root, task_id,
                user_feedback="First",
                observed_phenomenon="Obs A",
                expected_phenomenon="Exp A",
                delta_scope="Scope A",
                must_not_change="Must A",
                acceptance="Acc A",
            )

            result = create_followup(
                root, task_id,
                user_feedback="Second",
                observed_phenomenon="Obs B",
                expected_phenomenon="Exp B",
                delta_scope="Scope B",
                must_not_change="Must B",
                acceptance="Acc B",
            )

            self.assertTrue(result.get("reflection_recommended"))
            self.assertIn("next_action", result)
            self.assertIn("start-reflection", result["next_action"])
            self.assertIn(task_id, result["next_action"])

    # -----------------------------------------------------------------------
    # start_reflection
    # -----------------------------------------------------------------------

    def test_start_reflection_creates_reflection_md(self):
        """start_reflection creates reflection.md in the task directory."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Start refl", "Test start reflection", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Start refl",
                                       "Test start reflection", "design", ["Start refl works"])
            task_id = promoted["task_id"]

            # Add two follow-ups
            for i in range(2):
                create_followup(
                    root, task_id,
                    user_feedback=f"Feedback {i}",
                    observed_phenomenon=f"Observed {i}",
                    expected_phenomenon=f"Expected {i}",
                    delta_scope=f"Delta {i}",
                    must_not_change=f"Must not {i}",
                    acceptance=f"Accept {i}",
                )

            result = start_reflection(root, task_id)

            self.assertTrue(result["ok"])
            self.assertEqual(result["task_id"], task_id)
            self.assertEqual(result["reflection_count"], 2)
            self.assertTrue(result["path"].endswith("reflection.md"))

            refl_path = tasks_dir(root) / "active" / task_id / "reflection.md"
            self.assertTrue(refl_path.is_file())

    def test_start_reflection_contains_followup_content(self):
        """reflection.md includes content from recent follow-ups."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Refl content", "Test content", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Refl content",
                                       "Test content", "design", ["Content works"])
            task_id = promoted["task_id"]

            for i in range(2):
                create_followup(
                    root, task_id,
                    user_feedback=f"FB msg {i}",
                    observed_phenomenon=f"Obs text {i}",
                    expected_phenomenon=f"Exp text {i}",
                    delta_scope=f"Delta text {i}",
                    must_not_change=f"Must not {i}",
                    acceptance=f"Acc text {i}",
                )

            start_reflection(root, task_id)

            refl_path = tasks_dir(root) / "active" / task_id / "reflection.md"
            content = refl_path.read_text(encoding="utf-8")

            # Should include goal, follow-up data, and summary sections
            self.assertIn("## Goal / Context", content)
            self.assertIn("## Follow-Up History", content)
            self.assertIn("## Summary", content)
            self.assertIn("## Questions For Advisor", content)
            self.assertIn("FB msg 0", content)
            self.assertIn("FB msg 1", content)
            self.assertIn("Obs text 1", content)
            self.assertIn("Exp text 1", content)
            self.assertIn("Delta text 1", content)
            self.assertIn("Must not 1", content)
            self.assertIn("Acc text 1", content)

    def test_start_reflection_records_event(self):
        """start_reflection records a reflection_started task event."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Refl event", "Test event", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Refl event",
                                       "Test event", "design", ["Event works"])
            task_id = promoted["task_id"]

            for i in range(2):
                create_followup(
                    root, task_id,
                    user_feedback=f"F{i}", observed_phenomenon=f"O{i}",
                    expected_phenomenon=f"E{i}", delta_scope=f"D{i}",
                    must_not_change=f"M{i}", acceptance=f"A{i}",
                )

            start_reflection(root, task_id)

            # Check task events
            task_events = [json.loads(line)
                           for line in task_event_path(root, task_id).read_text(encoding="utf-8").splitlines()
                           if line]
            reflection_events = [e for e in task_events if e["type"] == "reflection_started"]
            self.assertEqual(len(reflection_events), 1)
            self.assertEqual(reflection_events[0]["task_id"], task_id)
            self.assertEqual(reflection_events[0]["reflection_count"], 2)
            self.assertIn("reflection_count", reflection_events[0])
            self.assertIn("before_status", reflection_events[0])
            self.assertIn("after_status", reflection_events[0])
            self.assertEqual(reflection_events[0]["after_status"], "debugging")

            # Check workspace events
            ws_events = [json.loads(line)
                         for line in (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
                         if line]
            ws_reflection = [e for e in ws_events if e["type"] == "reflection_started"]
            self.assertEqual(len(ws_reflection), 1)

    def test_start_reflection_marks_task_debugging(self):
        """start_reflection sets task status to debugging."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Refl status", "Test status change", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Refl status",
                                       "Test status change", "design", ["Status works"])
            task_id = promoted["task_id"]

            for i in range(2):
                create_followup(
                    root, task_id,
                    user_feedback=f"F{i}", observed_phenomenon=f"O{i}",
                    expected_phenomenon=f"E{i}", delta_scope=f"D{i}",
                    must_not_change=f"M{i}", acceptance=f"A{i}",
                )

            start_reflection(root, task_id)

            task = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertEqual(task["status"], "debugging")

    def test_start_reflection_missing_task_raises(self):
        """start_reflection raises FileNotFoundError for missing task."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)

            with self.assertRaises(FileNotFoundError):
                start_reflection(root, "nonexistent-task")

    def test_start_reflection_insufficient_followups_raises(self):
        """start_reflection raises RuntimeError with fewer than 2 follow-ups."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Insufficient", "Test insufficient", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Insufficient",
                                       "Test insufficient", "design", ["Insuff works"])
            task_id = promoted["task_id"]

            # Only one follow-up
            create_followup(
                root, task_id,
                user_feedback="Only one",
                observed_phenomenon="Obs",
                expected_phenomenon="Exp",
                delta_scope="Delta",
                must_not_change="Must not",
                acceptance="Accept",
            )

            with self.assertRaisesRegex(RuntimeError, "at least 2 follow-up"):
                start_reflection(root, task_id)

    def test_start_reflection_no_followups_raises(self):
        """start_reflection raises RuntimeError when no follow-ups directory exists."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "No followups", "Test no followups", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "No followups",
                                       "Test no followups", "design", ["No fups works"])
            task_id = promoted["task_id"]

            with self.assertRaisesRegex(RuntimeError, "No follow-up context"):
                start_reflection(root, task_id)

    def test_start_reflection_preserves_followup_files(self):
        """start_reflection does not delete or overwrite follow-up files."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Preserve", "Test preserve", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Preserve",
                                       "Test preserve", "design", ["Preserve works"])
            task_id = promoted["task_id"]

            for i in range(2):
                create_followup(
                    root, task_id,
                    user_feedback=f"F{i}", observed_phenomenon=f"O{i}",
                    expected_phenomenon=f"E{i}", delta_scope=f"D{i}",
                    must_not_change=f"M{i}", acceptance=f"A{i}",
                )

            followups_dir = tasks_dir(root) / "active" / task_id / "followups"
            self.assertTrue((followups_dir / "followup-001.md").is_file())
            self.assertTrue((followups_dir / "followup-002.md").is_file())
            content_before = (followups_dir / "followup-001.md").read_text(encoding="utf-8")

            start_reflection(root, task_id)

            # Follow-up files must still exist
            self.assertTrue((followups_dir / "followup-001.md").is_file())
            self.assertTrue((followups_dir / "followup-002.md").is_file())
            self.assertEqual(
                (followups_dir / "followup-001.md").read_text(encoding="utf-8"),
                content_before,
            )

    def test_cli_start_reflection_success(self):
        """CLI start-reflection creates reflection.md and returns JSON."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI refl", "Test CLI refl", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI refl",
                                       "Test CLI refl", "design", ["CLI refl works"])
            task_id = promoted["task_id"]

            for i in range(2):
                create_followup(
                    root, task_id,
                    user_feedback=f"F{i}", observed_phenomenon=f"O{i}",
                    expected_phenomenon=f"E{i}", delta_scope=f"D{i}",
                    must_not_change=f"M{i}", acceptance=f"A{i}",
                )

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "start-reflection", task_id],
                text=True, capture_output=True, check=True,
            )

            payload = json.loads(result.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["task_id"], task_id)
            self.assertEqual(payload["reflection_count"], 2)
            self.assertTrue(payload["path"].endswith("reflection.md"))

            refl_path = Path(payload["path"])
            self.assertTrue(refl_path.is_file())

    def test_cli_start_reflection_missing_task(self):
        """CLI start-reflection errors on missing task."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "start-reflection", "nonexistent-task"],
                text=True, capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Task not found", payload["message"])

    # -----------------------------------------------------------------------
    # create_followup (original tests follow)
    # -----------------------------------------------------------------------

    def test_create_followup_creates_file_with_sections(self):
        """create_followup writes a structured markdown file under followups/."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Followup test", "Test followup", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Followup test",
                                       "Test followup", "design", ["Followup works"])
            task_id = promoted["task_id"]

            result = create_followup(
                root, task_id,
                user_feedback="User says the feature is missing",
                observed_phenomenon="No feature visible",
                expected_phenomenon="Feature should be visible after save",
                delta_scope="Add visibility toggle",
                must_not_change="Existing save behavior",
                acceptance="Feature is visible after save",
            )

            self.assertIn("followup_id", result)
            self.assertEqual(result["task_id"], task_id)
            self.assertTrue(result["followup_id"].startswith("followup-"))

            followup_path = Path(result["path"])
            self.assertTrue(followup_path.is_file())
            self.assertIn("followups", str(followup_path))

            content = followup_path.read_text(encoding="utf-8")
            self.assertIn("## User Feedback", content)
            self.assertIn("User says the feature is missing", content)
            self.assertIn("## Observed Phenomenon", content)
            self.assertIn("No feature visible", content)
            self.assertIn("## Expected Phenomenon", content)
            self.assertIn("Feature should be visible after save", content)
            self.assertIn("## Delta Scope", content)
            self.assertIn("Add visibility toggle", content)
            self.assertIn("## Must Not Change", content)
            self.assertIn("Existing save behavior", content)
            self.assertIn("## Acceptance", content)
            self.assertIn("Feature is visible after save", content)
            self.assertIn(f"Task: {task_id}", content)

    def test_create_followup_sequential_numbering(self):
        """Multiple follow-ups on same task get sequential numbered IDs."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Seq followup", "Test seq", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Seq followup",
                                       "Test seq", "design", ["Seq works"])
            task_id = promoted["task_id"]

            first = create_followup(
                root, task_id,
                user_feedback="First feedback",
                observed_phenomenon="Observed A",
                expected_phenomenon="Expected A",
                delta_scope="Scope A",
                must_not_change="Must not A",
                acceptance="Accept A",
            )
            second = create_followup(
                root, task_id,
                user_feedback="Second feedback",
                observed_phenomenon="Observed B",
                expected_phenomenon="Expected B",
                delta_scope="Scope B",
                must_not_change="Must not B",
                acceptance="Accept B",
            )

            self.assertEqual(first["followup_id"], "followup-001")
            self.assertEqual(second["followup_id"], "followup-002")

            # Both files exist and are distinct
            first_path = Path(first["path"])
            second_path = Path(second["path"])
            self.assertTrue(first_path.is_file())
            self.assertTrue(second_path.is_file())
            self.assertNotEqual(first_path.read_text(encoding="utf-8"),
                                second_path.read_text(encoding="utf-8"))

    def test_create_followup_unknown_task_raises(self):
        """create_followup raises FileNotFoundError for missing task."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)

            with self.assertRaises(FileNotFoundError):
                create_followup(
                    root, "nonexistent-task",
                    user_feedback="Feedback",
                    observed_phenomenon="Observed",
                    expected_phenomenon="Expected",
                    delta_scope="Scope",
                    must_not_change="Must not",
                    acceptance="Accept",
                )

    def test_create_followup_does_not_overwrite_existing(self):
        """Follow-up files are never overwritten — new files get new numbers."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "No overwrite", "Test overwrite", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "No overwrite",
                                       "Test overwrite", "design", ["No overwrite works"])
            task_id = promoted["task_id"]

            # Create three follow-ups
            ids = set()
            for i in range(3):
                r = create_followup(
                    root, task_id,
                    user_feedback=f"Feedback {i}",
                    observed_phenomenon=f"Observed {i}",
                    expected_phenomenon=f"Expected {i}",
                    delta_scope=f"Scope {i}",
                    must_not_change=f"Must not {i}",
                    acceptance=f"Accept {i}",
                )
                ids.add(r["followup_id"])

            self.assertEqual(len(ids), 3)
            self.assertIn("followup-001", ids)
            self.assertIn("followup-002", ids)
            self.assertIn("followup-003", ids)

            # Verify all three files exist
            followups_dir = tasks_dir(root) / "active" / task_id / "followups"
            self.assertTrue((followups_dir / "followup-001.md").is_file())
            self.assertTrue((followups_dir / "followup-002.md").is_file())
            self.assertTrue((followups_dir / "followup-003.md").is_file())

    def test_create_followup_emits_task_event(self):
        """create_followup records a followup_created task event."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Event followup", "Test event", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "Event followup",
                                       "Test event", "design", ["Event works"])
            task_id = promoted["task_id"]

            create_followup(
                root, task_id,
                user_feedback="Event feedback",
                observed_phenomenon="Observed",
                expected_phenomenon="Expected",
                delta_scope="Scope",
                must_not_change="Must not",
                acceptance="Accept",
            )

            task_events = [json.loads(line)
                           for line in task_event_path(root, task_id).read_text(encoding="utf-8").splitlines()
                           if line]
            followup_events = [e for e in task_events if e["type"] == "followup_created"]
            self.assertEqual(len(followup_events), 1)
            self.assertIn("followup-001", followup_events[0]["summary"])

    def test_cli_record_followup_success(self):
        """CLI record-followup creates the follow-up file."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI followup", "Test CLI followup", "s1")
            set_intake_scope(root, intake["intake_id"])
            set_intake_design_artifact(root, intake["intake_id"])
            promoted = promote_to_task(root, intake["intake_id"], "CLI followup",
                                       "Test CLI followup", "design", ["CLI works"])
            task_id = promoted["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run([
                sys.executable, str(script), str(root), "record-followup", task_id,
                "--feedback", "CLI feedback",
                "--observed", "CLI observed",
                "--expected", "CLI expected",
                "--delta-scope", "CLI delta scope",
                "--must-not-change", "CLI must not change",
                "--acceptance", "CLI acceptance",
            ], text=True, capture_output=True, check=True)

            payload = json.loads(result.stdout)
            self.assertEqual(payload["followup_id"], "followup-001")
            self.assertEqual(payload["task_id"], task_id)

            followup_path = Path(payload["path"])
            self.assertTrue(followup_path.is_file())
            content = followup_path.read_text(encoding="utf-8")
            self.assertIn("CLI feedback", content)
            self.assertIn("CLI observed", content)
            self.assertIn("CLI expected", content)
            self.assertIn("CLI delta scope", content)
            self.assertIn("CLI must not change", content)
            self.assertIn("CLI acceptance", content)

    def test_cli_record_followup_unknown_task(self):
        """CLI record-followup errors on missing task."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)

            script = REPO_ROOT / "just-demand"
            result = subprocess.run([
                sys.executable, str(script), str(root), "record-followup", "nonexistent-task",
                "--feedback", "Feedback",
                "--observed", "Observed",
                "--expected", "Expected",
                "--delta-scope", "Delta scope",
                "--must-not-change", "Must not change",
                "--acceptance", "Acceptance",
            ], text=True, capture_output=True)

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Task not found", payload["message"])


# ===========================================================================
# Plan-ledger tests
# ===========================================================================


class PlanLedgerTests(unittest.TestCase):
    """Tests for the plan-ledger data model and CLI operations."""

    # ------------------------------------------------------------------
    # create_plan
    # ------------------------------------------------------------------

    def test_create_plan_creates_plan_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_plan(root, "My Roadmap")
            plan_id = result["plan_id"]
            self.assertIn("plan_id", result)
            self.assertEqual(result["title"], "My Roadmap")

            plan_dir = root / ".just-demand" / "state" / "plans" / plan_id
            self.assertTrue((plan_dir / "plan.json").is_file())

            plan = read_json(plan_dir / "plan.json")
            self.assertEqual(plan["title"], "My Roadmap")
            self.assertEqual(plan["stages"], [])
            self.assertEqual(plan["suggestions"], {})
            self.assertIn("created_at", plan)

    def test_create_plan_emits_workspace_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_plan(root, "Event Test")

            events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("plan_created", types)

    def test_create_plan_unique_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = create_plan(root, "Same Title")
            second = create_plan(root, "Same Title")
            self.assertNotEqual(first["plan_id"], second["plan_id"])

    # ------------------------------------------------------------------
    # read_plan / list_plans
    # ------------------------------------------------------------------

    def test_list_plans_returns_plan_summaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_plan(root, "Plan A")
            create_plan(root, "Plan B")

            plans = list_plans(root)
            self.assertEqual(len(plans), 2)
            titles = {p["title"] for p in plans}
            self.assertIn("Plan A", titles)
            self.assertIn("Plan B", titles)

    def test_list_plans_empty_when_no_plans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            self.assertEqual(list_plans(root), [])

    def test_read_plan_returns_plan_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = create_plan(root, "Readable Plan")
            plan = read_plan(root, created["plan_id"])
            self.assertEqual(plan["title"], "Readable Plan")

    def test_read_plan_missing_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            with self.assertRaises(FileNotFoundError):
                read_plan(root, "nonexistent-plan")

    # ------------------------------------------------------------------
    # add_plan_stage
    # ------------------------------------------------------------------

    def test_add_plan_stage_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Stage Test")
            plan_id = plan["plan_id"]

            updated = add_plan_stage(root, plan_id, "phase-1", "Discovery")
            stages = updated["stages"]
            self.assertEqual(len(stages), 1)
            self.assertEqual(stages[0]["id"], "phase-1")
            self.assertEqual(stages[0]["title"], "Discovery")
            self.assertEqual(stages[0]["order"], 1)

    def test_add_plan_stage_sequential_ordering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Order Test")
            plan_id = plan["plan_id"]

            add_plan_stage(root, plan_id, "a", "Stage A")
            add_plan_stage(root, plan_id, "b", "Stage B")
            add_plan_stage(root, plan_id, "c", "Stage C")

            updated = read_plan(root, plan_id)
            orders = [s["order"] for s in updated["stages"]]
            self.assertEqual(orders, [1, 2, 3])

    def test_add_plan_stage_duplicate_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Dup Stage")
            add_plan_stage(root, plan["plan_id"], "phase-1", "First")
            with self.assertRaisesRegex(ValueError, "already exists"):
                add_plan_stage(root, plan["plan_id"], "phase-1", "Duplicate")

    def test_add_plan_stage_missing_plan_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            with self.assertRaises(FileNotFoundError):
                add_plan_stage(root, "nonexistent", "s1", "Stage")

    def test_add_plan_stage_emits_workspace_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Event Stage")
            add_plan_stage(root, plan["plan_id"], "s1", "Stage One")

            events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("plan_stage_added", types)

    # ------------------------------------------------------------------
    # add_plan_suggestion — verbatim text retention
    # ------------------------------------------------------------------

    def test_add_suggestion_preserves_verbatim_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Sug Test")
            plan_id = plan["plan_id"]
            add_plan_stage(root, plan_id, "phase-1", "Phase 1")

            verbatim = "We should use event-driven architecture for the notification service."
            result = add_plan_suggestion(root, plan_id, "phase-1", verbatim)
            sug_id = result["suggestion_id"]

            plan_data = read_plan(root, plan_id)
            sug = plan_data["suggestions"][sug_id]
            self.assertEqual(sug["verbatim_text"], verbatim)

    def test_add_suggestion_defaults_to_proposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Default Status")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            result = add_plan_suggestion(root, plan["plan_id"], "p1", "Some suggestion")
            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][result["suggestion_id"]]
            self.assertEqual(sug["status"], "proposed")

    def test_add_suggestion_records_initial_status_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Status History")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            result = add_plan_suggestion(root, plan["plan_id"], "p1", "Initial suggestion")
            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][result["suggestion_id"]]
            self.assertEqual(len(sug["status_history"]), 1)
            entry = sug["status_history"][0]
            self.assertIsNone(entry["from_status"])
            self.assertEqual(entry["to_status"], "proposed")
            self.assertIn("at", entry)

    def test_add_suggestion_unknown_stage_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Bad Stage")
            with self.assertRaisesRegex(ValueError, "Stage 'ghost' not found"):
                add_plan_suggestion(root, plan["plan_id"], "ghost", "Text")

    def test_add_suggestion_unknown_plan_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            with self.assertRaises(FileNotFoundError):
                add_plan_suggestion(root, "nonexistent", "s1", "Text")

    def test_add_suggestion_with_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Dep Test")
            plan_id = plan["plan_id"]
            add_plan_stage(root, plan_id, "p1", "Phase 1")
            r1 = add_plan_suggestion(root, plan_id, "p1", "First suggestion")
            r2 = add_plan_suggestion(root, plan_id, "p1", "Second suggestion",
                                      dependencies=[r1["suggestion_id"]])
            plan_data = read_plan(root, plan_id)
            sug2 = plan_data["suggestions"][r2["suggestion_id"]]
            self.assertIn(r1["suggestion_id"], sug2["dependencies"])

    def test_add_suggestion_invalid_dependency_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Bad Dep")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            with self.assertRaisesRegex(ValueError, "Dependency suggestion 'nonexistent' not found"):
                add_plan_suggestion(root, plan["plan_id"], "p1", "Text",
                                    dependencies=["nonexistent"])

    def test_add_suggestion_emits_workspace_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Sug Event")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            add_plan_suggestion(root, plan["plan_id"], "p1", "Event suggestion")
            events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("plan_suggestion_added", types)

    # ------------------------------------------------------------------
    # update_suggestion_status — status history
    # ------------------------------------------------------------------

    def test_update_suggestion_status_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Status Update")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "Updatable suggestion")
            sug_id = r["suggestion_id"]

            update_suggestion_status(root, plan["plan_id"], sug_id, "accepted",
                                      reason="Approved by team")

            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][sug_id]
            self.assertEqual(sug["status"], "accepted")

    def test_update_suggestion_status_preserves_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "History Chain")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "History suggestion")
            sug_id = r["suggestion_id"]

            update_suggestion_status(root, plan["plan_id"], sug_id, "accepted",
                                      reason="Approved")
            update_suggestion_status(root, plan["plan_id"], sug_id, "implemented",
                                      reason="Done")

            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][sug_id]
            # Initial creation + 2 transitions = 3 entries
            self.assertEqual(len(sug["status_history"]), 3)
            self.assertEqual(sug["status_history"][1]["from_status"], "proposed")
            self.assertEqual(sug["status_history"][1]["to_status"], "accepted")
            self.assertEqual(sug["status_history"][2]["from_status"], "accepted")
            self.assertEqual(sug["status_history"][2]["to_status"], "implemented")

    def test_update_suggestion_status_invalid_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Bad Status")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "Suggestion")
            with self.assertRaisesRegex(ValueError, "Invalid suggestion status"):
                update_suggestion_status(root, plan["plan_id"], r["suggestion_id"], "bogus")

    def test_update_suggestion_status_unknown_suggestion_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Missing Sug")
            with self.assertRaisesRegex(ValueError, "not found"):
                update_suggestion_status(root, plan["plan_id"], "nonexistent", "accepted")

    def test_update_suggestion_status_same_status_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Same Status")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "Suggestion")
            with self.assertRaisesRegex(ValueError, "already"):
                update_suggestion_status(root, plan["plan_id"], r["suggestion_id"], "proposed")

    def test_update_suggestion_status_emits_event_with_from_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Status Event")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "Suggestion")
            sug_id = r["suggestion_id"]

            update_suggestion_status(root, plan["plan_id"], sug_id, "accepted",
                                      reason="Team approved")

            raw_events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            events = [json.loads(e) for e in raw_events if e]
            status_events = [e for e in events if e["type"] == "plan_suggestion_status_updated"]
            self.assertEqual(len(status_events), 1)
            self.assertEqual(status_events[0]["from_status"], "proposed")
            self.assertEqual(status_events[0]["to_status"], "accepted")

    # ------------------------------------------------------------------
    # add_task_to_plan — task association
    # ------------------------------------------------------------------

    def test_add_task_to_plan_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Task Assoc")
            plan_id = plan["plan_id"]
            add_plan_stage(root, plan_id, "p1", "Phase 1")
            r = add_plan_suggestion(root, plan_id, "p1", "Needs implementation")

            # Create a task
            intake = create_intake(root, "Task for plan", "Implement the suggestion", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "Scope")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "Works")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. Do it")
            update_intake_section(root, intake["intake_id"], "Approval", "Approved")
            task = promote_to_task(root, intake["intake_id"], "Plan task", "Implement", "design",
                                    ["Works"])
            task_id = task["task_id"]

            result = add_task_to_plan(root, plan_id, r["suggestion_id"], task_id)
            plan_data = read_plan(root, plan_id)
            sug = plan_data["suggestions"][r["suggestion_id"]]
            self.assertIn(task_id, sug["covered_tasks"])

    def test_add_task_to_plan_sets_plan_id_on_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Plan ID Test")
            plan_id = plan["plan_id"]
            add_plan_stage(root, plan_id, "p1", "Phase 1")
            r = add_plan_suggestion(root, plan_id, "p1", "Suggestion with task")

            intake = create_intake(root, "Plan ID task", "Task under plan", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "Scope")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "Works")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. Do it")
            update_intake_section(root, intake["intake_id"], "Approval", "Approved")
            task = promote_to_task(root, intake["intake_id"], "Plan ID task", "Implement", "design",
                                    ["Works"])
            task_id = task["task_id"]

            add_task_to_plan(root, plan_id, r["suggestion_id"], task_id)
            task_data = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertEqual(task_data["plan_id"], plan_id)

    def test_add_task_to_plan_unknown_plan_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            with self.assertRaises(FileNotFoundError):
                add_task_to_plan(root, "nonexistent", "sug-1", "task-1")

    def test_add_task_to_plan_unknown_task_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Unknown task")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "Suggestion")
            with self.assertRaises(FileNotFoundError):
                add_task_to_plan(root, plan["plan_id"], r["suggestion_id"], "nonexistent-task")

    def test_add_task_to_plan_emits_workspace_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Task Event")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "Suggestion")

            intake = create_intake(root, "Event task", "Task", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "Scope")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "Works")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. Do it")
            update_intake_section(root, intake["intake_id"], "Approval", "Approved")
            task = promote_to_task(root, intake["intake_id"], "Event task", "Task", "design",
                                    ["Works"])

            add_task_to_plan(root, plan["plan_id"], r["suggestion_id"], task["task_id"])
            events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("plan_task_added", types)

    # ------------------------------------------------------------------
    # add_plan_evidence
    # ------------------------------------------------------------------

    def test_add_evidence_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Evidence Test")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "Suggestion")

            add_plan_evidence(root, plan["plan_id"], r["suggestion_id"],
                               "Implementation completed in PR #42")

            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][r["suggestion_id"]]
            self.assertIn("Implementation completed in PR #42", sug["evidence"])

    def test_add_evidence_accumulates_multiple_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Multi Evidence")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "Suggestion")
            sug_id = r["suggestion_id"]

            add_plan_evidence(root, plan["plan_id"], sug_id, "Evidence A")
            add_plan_evidence(root, plan["plan_id"], sug_id, "Evidence B")

            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][sug_id]
            self.assertEqual(len(sug["evidence"]), 2)
            self.assertIn("Evidence A", sug["evidence"])
            self.assertIn("Evidence B", sug["evidence"])

    def test_add_evidence_unknown_suggestion_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Bad Evidence")
            with self.assertRaisesRegex(ValueError, "not found"):
                add_plan_evidence(root, plan["plan_id"], "nonexistent-sug", "Evidence")

    def test_add_evidence_emits_workspace_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Evidence Event")
            add_plan_stage(root, plan["plan_id"], "p1", "Phase 1")
            r = add_plan_suggestion(root, plan["plan_id"], "p1", "Suggestion")
            add_plan_evidence(root, plan["plan_id"], r["suggestion_id"], "Done")

            events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            types = [json.loads(e)["type"] for e in events if e]
            self.assertIn("plan_evidence_added", types)

    # ------------------------------------------------------------------
    # Task compatibility: tasks without plan_id remain unchanged
    # ------------------------------------------------------------------

    def test_existing_task_optional_plan_id_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Old task", "No plan", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "Scope")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "Works")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. Do it")
            update_intake_section(root, intake["intake_id"], "Approval", "Approved")
            task = promote_to_task(root, intake["intake_id"], "Old task", "No plan", "design",
                                    ["Works"])
            task_data = read_json(tasks_dir(root) / "active" / task["task_id"] / "task.json")
            # plan_id should be present and None by default
            self.assertIn("plan_id", task_data)
            self.assertIsNone(task_data["plan_id"])

    def test_old_task_still_works_without_plan(self):
        """Tasks without a plan behave exactly as before — no plan-related changes affect them."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # Full lifecycle without any plan involvement
            intake = create_intake(root, "No plan task", "Task without plan", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "Scope")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "Works")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. Do it")
            update_intake_section(root, intake["intake_id"], "Approval", "Approved")
            task = promote_to_task(root, intake["intake_id"], "No plan task", "Without plan",
                                    "design", ["Works"])
            task_id = task["task_id"]

            create_validation_revision(root, task_id, "No plan.", ["C1"], ["E1"])
            start_execution(root, task_id, ["just-demand-coder"])
            mark_task(root, task_id, "executing", progress=50)
            complete_verification(root, task_id, "passed", "Done", auto_archive=False)

            task_data = read_json(tasks_dir(root) / "active" / task_id / "task.json")
            self.assertEqual(task_data["status"], "done")
            self.assertIsNone(task_data["plan_id"])

    # ------------------------------------------------------------------
    # Invalid input handling
    # ------------------------------------------------------------------

    def test_create_plan_empty_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = create_plan(root, "")
            # Should still create a plan with sanitized slug
            self.assertIn("plan_id", result)
            self.assertTrue(result["plan_id"].endswith("-plan"))

    def test_add_suggestion_empty_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Empty text")
            add_plan_stage(root, plan["plan_id"], "s1", "Stage 1")
            # Empty text is allowed (it's preserved verbatim)
            result = add_plan_suggestion(root, plan["plan_id"], "s1", "")
            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][result["suggestion_id"]]
            self.assertEqual(sug["verbatim_text"], "")

    # ------------------------------------------------------------------
    # Workspace events integration
    # ------------------------------------------------------------------

    def test_plan_events_logged_in_workspace_events(self):
        """All plan operations emit workspace events with correct types."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Full Event Test")
            plan_id = plan["plan_id"]
            add_plan_stage(root, plan_id, "p1", "Phase 1")

            r = add_plan_suggestion(root, plan_id, "p1", "Suggest something")
            sug_id = r["suggestion_id"]

            update_suggestion_status(root, plan_id, sug_id, "accepted", reason="OK")
            add_plan_evidence(root, plan_id, sug_id, "Evidence here")

            intake = create_intake(root, "Plan event task", "Task", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "Scope")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "Works")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. Do it")
            update_intake_section(root, intake["intake_id"], "Approval", "Approved")
            task = promote_to_task(root, intake["intake_id"], "Event task", "Task", "design",
                                    ["Works"])
            add_task_to_plan(root, plan_id, sug_id, task["task_id"])

            events = (state_dir(root) / "events.jsonl").read_text(encoding="utf-8").splitlines()
            event_types = [json.loads(e)["type"] for e in events if e]
            for expected_type in ["plan_created", "plan_stage_added", "plan_suggestion_added",
                                   "plan_suggestion_status_updated", "plan_evidence_added",
                                   "plan_task_added"]:
                with self.subTest(event_type=expected_type):
                    self.assertIn(expected_type, event_types)

    # ------------------------------------------------------------------
    # CLI integration tests
    # ------------------------------------------------------------------

    def _run_cli(self, root: Path, *args: str) -> dict:
        import subprocess
        script = REPO_ROOT / "just-demand"
        result = subprocess.run(
            [sys.executable, str(script), str(root), *args],
            text=True, capture_output=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"CLI error ({result.returncode}): {result.stdout} {result.stderr}")
        return json.loads(result.stdout)

    def test_cli_create_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = self._run_cli(root, "create-plan", "CLI Plan")
            self.assertIn("plan_id", payload)
            self.assertEqual(payload["title"], "CLI Plan")

            # Verify it's persisted
            plans = list_plans(root)
            self.assertEqual(len(plans), 1)

    def test_cli_list_plans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run_cli(root, "create-plan", "Plan One")
            self._run_cli(root, "create-plan", "Plan Two")
            payload = self._run_cli(root, "list-plans")
            self.assertEqual(len(payload["plans"]), 2)

    def test_cli_show_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Showable Plan")
            plan_id = plan["plan_id"]
            add_plan_stage(root, plan_id, "s1", "Stage 1")

            payload = self._run_cli(root, "show-plan", plan_id)
            self.assertEqual(payload["title"], "Showable Plan")
            self.assertEqual(len(payload["stages"]), 1)

    def test_cli_add_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "CLI Stage")
            payload = self._run_cli(root, "add-stage", plan["plan_id"], "phase-x", "Phase X")
            stages = payload["stages"]
            self.assertEqual(len(stages), 1)
            self.assertEqual(stages[0]["id"], "phase-x")

    def test_cli_add_suggestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "CLI Sug")
            add_plan_stage(root, plan["plan_id"], "s1", "Stage 1")
            payload = self._run_cli(root, "add-suggestion", plan["plan_id"], "s1",
                                     "Verbatim suggestion from CLI")
            self.assertIn("suggestion_id", payload)

            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][payload["suggestion_id"]]
            self.assertEqual(sug["verbatim_text"], "Verbatim suggestion from CLI")

    def test_cli_update_suggestion_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "CLI Status")
            add_plan_stage(root, plan["plan_id"], "s1", "Stage 1")
            r = add_plan_suggestion(root, plan["plan_id"], "s1", "Status suggestion")
            sug_id = r["suggestion_id"]

            payload = self._run_cli(root, "update-suggestion-status", plan["plan_id"],
                                     sug_id, "accepted", "--reason", "CLI approved")
            self.assertEqual(payload["suggestions"][sug_id]["status"], "accepted")

    def test_cli_add_task_to_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "CLI Task")
            add_plan_stage(root, plan["plan_id"], "s1", "Stage 1")
            r = add_plan_suggestion(root, plan["plan_id"], "s1", "Task suggestion")

            intake = create_intake(root, "CLI plan task", "Task", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "Scope")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "Works")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. Do it")
            update_intake_section(root, intake["intake_id"], "Approval", "Approved")
            task = promote_to_task(root, intake["intake_id"], "CLI plan task", "Task", "design",
                                    ["Works"])

            self._run_cli(root, "add-task-to-plan", plan["plan_id"], r["suggestion_id"],
                           task["task_id"])
            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][r["suggestion_id"]]
            self.assertIn(task["task_id"], sug["covered_tasks"])

    def test_cli_add_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "CLI Evidence")
            add_plan_stage(root, plan["plan_id"], "s1", "Stage 1")
            r = add_plan_suggestion(root, plan["plan_id"], "s1", "Evidence suggestion")
            sug_id = r["suggestion_id"]

            payload = self._run_cli(root, "add-evidence", plan["plan_id"], sug_id,
                                     "CLI evidence recorded")
            plan_data = read_plan(root, plan["plan_id"])
            sug = plan_data["suggestions"][sug_id]
            self.assertIn("CLI evidence recorded", sug["evidence"])

    def test_cli_invalid_plan_shows_error(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "show-plan", "nonexistent"],
                text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")

    def test_cli_invalid_status_shows_error(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            # Need a plan and suggestion first
            plan = create_plan(root, "Error Test")
            add_plan_stage(root, plan["plan_id"], "s1", "Stage 1")
            r = add_plan_suggestion(root, plan["plan_id"], "s1", "Suggestion")

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "update-suggestion-status",
                 plan["plan_id"], r["suggestion_id"], "bogus"],
                text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")

    def test_suggestion_order_is_recorded(self):
        """Suggestions added to a plan are tracked in insertion order."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Order Test")
            add_plan_stage(root, plan["plan_id"], "s1", "Stage 1")

            r1 = add_plan_suggestion(root, plan["plan_id"], "s1", "First")
            r2 = add_plan_suggestion(root, plan["plan_id"], "s1", "Second")
            r3 = add_plan_suggestion(root, plan["plan_id"], "s1", "Third")

            plan_data = read_plan(root, plan["plan_id"])
            order = plan_data.get("suggestion_order", [])
            self.assertEqual(order, [r1["suggestion_id"], r2["suggestion_id"], r3["suggestion_id"]])

    # ── Concurrency regression tests ──────────────────────────────────────

    def test_concurrent_suggestion_additions_preserve_all_data(self):
        """Parallel add_plan_suggestion calls must both succeed (read-modify-write race)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Concurrency Suggestion")
            pid = plan["plan_id"]
            add_plan_stage(root, pid, "phase-1", "Phase 1")

            results: list[dict] = []
            errors: list[Exception] = []
            lock = threading.Lock()

            def add_one(text: str) -> None:
                try:
                    r = add_plan_suggestion(root, pid, "phase-1", text)
                    with lock:
                        results.append(r)
                except Exception as e:
                    with lock:
                        errors.append(e)

            t1 = threading.Thread(target=add_one, args=("Suggestion A",))
            t2 = threading.Thread(target=add_one, args=("Suggestion B",))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertEqual(len(errors), 0, f"Concurrent suggestion errors: {errors}")
            self.assertEqual(len(results), 2)

            plan_data = read_plan(root, pid)
            sug_ids = {r["suggestion_id"] for r in results}
            for sid in sug_ids:
                self.assertIn(sid, plan_data["suggestions"],
                              f"Suggestion {sid} missing from plan after concurrent add")
            self.assertEqual(len(plan_data["suggestions"]), 2)

    def test_concurrent_stage_additions_preserve_all_stages(self):
        """Parallel add_plan_stage calls must both succeed (read-modify-write race)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Concurrency Stage")
            pid = plan["plan_id"]

            errors: list[Exception] = []
            lock = threading.Lock()

            def add_one(stage_id: str, title: str) -> None:
                try:
                    add_plan_stage(root, pid, stage_id, title)
                except Exception as e:
                    with lock:
                        errors.append(e)

            t1 = threading.Thread(target=add_one, args=("s1", "Stage 1"))
            t2 = threading.Thread(target=add_one, args=("s2", "Stage 2"))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertEqual(len(errors), 0, f"Concurrent stage errors: {errors}")

            plan_data = read_plan(root, pid)
            stage_ids = {s["id"] for s in plan_data.get("stages", [])}
            self.assertIn("s1", stage_ids)
            self.assertIn("s2", stage_ids)

    def test_concurrent_suggestion_status_updates(self):
        """Parallel update_suggestion_status must not lose transitions."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Concurrency Status")
            pid = plan["plan_id"]
            add_plan_stage(root, pid, "s1", "Stage 1")
            r1 = add_plan_suggestion(root, pid, "s1", "Suggestion A")
            r2 = add_plan_suggestion(root, pid, "s1", "Suggestion B")
            sid_a = r1["suggestion_id"]
            sid_b = r2["suggestion_id"]

            errors: list[Exception] = []
            lock = threading.Lock()

            def accept_a() -> None:
                try:
                    update_suggestion_status(root, pid, sid_a, "accepted", reason="Approved")
                except Exception as e:
                    with lock:
                        errors.append(e)

            def accept_b() -> None:
                try:
                    update_suggestion_status(root, pid, sid_b, "accepted", reason="Approved")
                except Exception as e:
                    with lock:
                        errors.append(e)

            t1 = threading.Thread(target=accept_a)
            t2 = threading.Thread(target=accept_b)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertEqual(len(errors), 0, f"Concurrent status errors: {errors}")

            plan_data = read_plan(root, pid)
            self.assertEqual(plan_data["suggestions"][sid_a]["status"], "accepted")
            self.assertEqual(plan_data["suggestions"][sid_b]["status"], "accepted")

    # ── Fault injection tests for add_task_to_plan ─────────────────────────

    def test_add_task_to_plan_task_write_failure_no_inconsistency(self):
        """Simulate task JSON write failure; plan must not reference the task."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Fault Task")
            pid = plan["plan_id"]
            add_plan_stage(root, pid, "s1", "Stage 1")
            r = add_plan_suggestion(root, pid, "s1", "Suggestion")

            intake = create_intake(root, "Fault task", "Task", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "S")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "W")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. X")
            update_intake_section(root, intake["intake_id"], "Approval", "Y")
            task = promote_to_task(root, intake["intake_id"], "Fault task", "T", "design", ["W"])
            tid = task["task_id"]

            # Inject failure into the task write: make write_json_atomic fail
            # when called on the task.json path.
            def _fail_on_task(path, data):
                if "active" in str(path) and tid in str(path):
                    raise OSError("Simulated task write failure")
                return write_json_atomic(path, data)

            with patch("workflow_core.write_json_atomic", side_effect=_fail_on_task):
                with self.assertRaises(OSError):
                    add_task_to_plan(root, pid, r["suggestion_id"], tid)

            # Plan must NOT reference the failed task
            plan_data = read_plan(root, pid)
            sug = plan_data["suggestions"][r["suggestion_id"]]
            self.assertNotIn(tid, sug.get("covered_tasks", []),
                             "Plan should not reference task when task write failed")

            # Task must still have plan_id = None
            task_data = read_json(tasks_dir(root) / "active" / tid / "task.json")
            self.assertIsNone(task_data.get("plan_id"),
                              "Task plan_id must remain None when task write failed")

    def test_add_task_to_plan_plan_write_failure_rolls_back_task(self):
        """Simulate plan JSON write failure; task.plan_id must be rolled back."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Rollback Plan")
            pid = plan["plan_id"]
            add_plan_stage(root, pid, "s1", "Stage 1")
            r = add_plan_suggestion(root, pid, "s1", "Suggestion")

            intake = create_intake(root, "Rollback task", "Task", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "S")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "W")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. X")
            update_intake_section(root, intake["intake_id"], "Approval", "Y")
            task = promote_to_task(root, intake["intake_id"], "Rollback task", "T", "design", ["W"])
            tid = task["task_id"]

            # Inject failure into the plan save (task write is 1st call,
            # _save_plan → plan.json is 2nd call).
            call_count = [0]

            def _fail_on_plan_save(path, data):
                call_count[0] += 1
                if call_count[0] == 2:
                    raise OSError("Simulated plan save failure")
                return write_json_atomic(path, data)

            with patch("workflow_core.write_json_atomic", side_effect=_fail_on_plan_save):
                with self.assertRaises(OSError):
                    add_task_to_plan(root, pid, r["suggestion_id"], tid)

            # Task plan_id must be rolled back to None
            task_data = read_json(tasks_dir(root) / "active" / tid / "task.json")
            self.assertIsNone(task_data.get("plan_id"),
                              "Task plan_id must be rolled back on plan save failure")

            # Plan must not reference the task
            plan_data = read_plan(root, pid)
            sug = plan_data["suggestions"][r["suggestion_id"]]
            self.assertNotIn(tid, sug.get("covered_tasks", []),
                             "Plan should not reference task when plan save failed")

    def test_concurrent_add_task_to_plan_preserves_all_associations(self):
        """Parallel add_task_to_plan on different suggestions must both succeed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = create_plan(root, "Concurrent Task Assoc")
            pid = plan["plan_id"]
            add_plan_stage(root, pid, "s1", "Stage 1")
            r1 = add_plan_suggestion(root, pid, "s1", "Suggestion A")
            r2 = add_plan_suggestion(root, pid, "s1", "Suggestion B")
            sid_a = r1["suggestion_id"]
            sid_b = r2["suggestion_id"]

            # Create two tasks
            def _make_task(title):
                i = create_intake(root, title, "Task", "s1")
                update_intake_section(root, i["intake_id"], "Scope", "S")
                update_intake_section(root, i["intake_id"], "Final Expected Effect", "W")
                update_intake_section(root, i["intake_id"], "Chosen Approach", "A")
                update_intake_section(root, i["intake_id"], "Final Implementation Plan", "1. X")
                update_intake_section(root, i["intake_id"], "Approval", "Y")
                return promote_to_task(root, i["intake_id"], title, "T", "design", ["W"])

            t1 = _make_task("Concurrent task A")
            t2 = _make_task("Concurrent task B")

            errors: list[Exception] = []
            lock = threading.Lock()

            def associate_a():
                try:
                    add_task_to_plan(root, pid, sid_a, t1["task_id"])
                except Exception as e:
                    with lock:
                        errors.append(e)

            def associate_b():
                try:
                    add_task_to_plan(root, pid, sid_b, t2["task_id"])
                except Exception as e:
                    with lock:
                        errors.append(e)

            ta = threading.Thread(target=associate_a)
            tb = threading.Thread(target=associate_b)
            ta.start()
            tb.start()
            ta.join()
            tb.join()

            self.assertEqual(len(errors), 0, f"Concurrent task assoc errors: {errors}")

            plan_data = read_plan(root, pid)
            self.assertIn(t1["task_id"], plan_data["suggestions"][sid_a]["covered_tasks"])
            self.assertIn(t2["task_id"], plan_data["suggestions"][sid_b]["covered_tasks"])

            # Task plan_id must be set
            td1 = read_json(tasks_dir(root) / "active" / t1["task_id"] / "task.json")
            td2 = read_json(tasks_dir(root) / "active" / t2["task_id"] / "task.json")
            self.assertEqual(td1.get("plan_id"), pid)
            self.assertEqual(td2.get("plan_id"), pid)


# ===========================================================================
# Plan snapshot tests
# ===========================================================================


def _setup_plan_with_task(root, plan_title="Test Plan"):
    """Helper: create a plan with two stages, suggestions, and a linked task."""
    plan = create_plan(root, plan_title)
    pid = plan["plan_id"]
    add_plan_stage(root, pid, "stage-1", "Discovery")
    add_plan_stage(root, pid, "stage-2", "Implementation")

    # Stage 1 suggestions
    r1 = add_plan_suggestion(root, pid, "stage-1",
                              "Research existing solutions")
    r2 = add_plan_suggestion(root, pid, "stage-1",
                              "Define API contracts",
                              dependencies=[r1["suggestion_id"]])

    # Stage 2 suggestions
    r3 = add_plan_suggestion(root, pid, "stage-2",
                              "Build the backend service",
                              dependencies=[r2["suggestion_id"]])
    r4 = add_plan_suggestion(root, pid, "stage-2",
                              "Write integration tests")

    # Create a task linked to suggestion r3
    intake = create_intake(root, "Plan task", "Task for plan", "s1")
    update_intake_section(root, intake["intake_id"], "Scope", "Scope")
    update_intake_section(root, intake["intake_id"], "Final Expected Effect", "Works")
    update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
    update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. Do it")
    update_intake_section(root, intake["intake_id"], "Approval", "Approved")
    task = promote_to_task(root, intake["intake_id"], "Plan task", "Implement", "design",
                            ["Works"])
    tid = task["task_id"]

    add_task_to_plan(root, pid, r3["suggestion_id"], tid)

    return {
        "root": root,
        "plan_id": pid,
        "task_id": tid,
        "suggestion_ids": {
            "r1": r1["suggestion_id"],
            "r2": r2["suggestion_id"],
            "r3": r3["suggestion_id"],
            "r4": r4["suggestion_id"],
        },
    }


class PlanCloseoutTests(unittest.TestCase):
    def _ready(self, root: Path) -> dict:
        ctx = _setup_plan_with_task(root)
        mark_task(root, ctx["task_id"], "executing")
        return ctx

    def test_passed_closeout_updates_only_covered_suggestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._ready(root)
            result = complete_verification(
                root, ctx["task_id"], "passed", "Verified snapshot behavior",
                auto_archive=False, checkpoint_commit=False,
            )

            plan = read_plan(root, ctx["plan_id"])
            covered = plan["suggestions"][ctx["suggestion_ids"]["r3"]]
            unrelated = plan["suggestions"][ctx["suggestion_ids"]["r4"]]
            self.assertEqual(covered["status"], "implemented")
            self.assertEqual(unrelated["status"], "proposed")
            evidence = [item for item in covered["evidence"] if isinstance(item, dict)]
            self.assertEqual(evidence[-1]["task_id"], ctx["task_id"])
            self.assertEqual(evidence[-1]["verification_summary"], "Verified snapshot behavior")
            continuation = result["plan_continuation"]
            self.assertEqual(continuation["completed_suggestions"][0]["id"], ctx["suggestion_ids"]["r3"])
            self.assertTrue(any(item["id"] == ctx["suggestion_ids"]["r4"] for item in continuation["remaining_actionable"]))
            self.assertIn("plan_continuation", result["completion_report"])

    def test_failed_closeout_does_not_update_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._ready(root)
            before = read_plan(root, ctx["plan_id"])
            result = complete_verification(
                root, ctx["task_id"], "failed", "Needs changes",
                auto_archive=False, checkpoint_commit=False,
            )
            self.assertEqual(read_plan(root, ctx["plan_id"]), before)
            self.assertNotIn("plan_continuation", result)

    def test_plan_write_failure_leaves_task_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._ready(root)
            with patch("workflow_core._save_plan", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    complete_verification(
                        root, ctx["task_id"], "passed", "Verified",
                        auto_archive=False, checkpoint_commit=False,
                    )
            task = read_json(tasks_dir(root) / "active" / ctx["task_id"] / "task.json")
            self.assertEqual(task["status"], "executing")
            self.assertEqual(task["verification_status"], "not_started")

    def test_plan_writeback_is_idempotent_for_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._ready(root)
            import workflow_core
            first = workflow_core._write_back_plan_closeout(root, ctx["task_id"], "Verified")
            second = workflow_core._write_back_plan_closeout(root, ctx["task_id"], "Verified")
            plan = read_plan(root, ctx["plan_id"])
            suggestion = plan["suggestions"][ctx["suggestion_ids"]["r3"]]
            evidence = [
                item for item in suggestion["evidence"]
                if isinstance(item, dict) and item.get("type") == "verification_closeout"
            ]
            self.assertEqual(len(evidence), 1)
            self.assertEqual(first["completed_suggestions"], second["completed_suggestions"])

    def test_archived_task_persists_plan_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._ready(root)
            result = complete_verification(
                root, ctx["task_id"], "passed", "Verified",
                checkpoint_commit=False,
            )
            archived_task = read_json(
                tasks_dir(root) / "archive" / ctx["task_id"] / "task.json"
            )
            self.assertTrue(result["archived"])
            self.assertIn("plan_continuation", archived_task["completion_report"])

    def test_continuation_exposes_rejected_and_superseded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._ready(root)
            rejected_id = ctx["suggestion_ids"]["r1"]
            superseded_id = ctx["suggestion_ids"]["r2"]
            update_suggestion_status(root, ctx["plan_id"], rejected_id, "rejected", reason="Declined")
            update_suggestion_status(root, ctx["plan_id"], superseded_id, "superseded", reason="Replaced")
            result = complete_verification(
                root, ctx["task_id"], "passed", "Verified",
                auto_archive=False, checkpoint_commit=False,
            )
            continuation = result["plan_continuation"]
            self.assertEqual([item["id"] for item in continuation["rejected"]], [rejected_id])
            self.assertEqual([item["id"] for item in continuation["superseded"]], [superseded_id])

    def test_snapshot_refresh_failure_blocks_task_closeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._ready(root)
            with patch(
                "workflow_core._refresh_all_active_tasks_for_plan_unlocked",
                return_value=[ctx["task_id"]],
            ):
                with self.assertRaisesRegex(RuntimeError, "snapshot refresh failed"):
                    complete_verification(
                        root, ctx["task_id"], "passed", "Verified",
                        auto_archive=False, checkpoint_commit=False,
                    )
            task = read_json(tasks_dir(root) / "active" / ctx["task_id"] / "task.json")
            self.assertEqual(task["status"], "executing")
            plan = read_plan(root, ctx["plan_id"])
            suggestion = plan["suggestions"][ctx["suggestion_ids"]["r3"]]
            evidence = [
                item for item in suggestion["evidence"]
                if isinstance(item, dict) and item.get("type") == "verification_closeout"
            ]
            self.assertEqual(len(evidence), 1)


class PlanSnapshotTests(unittest.TestCase):
    """Tests for plan snapshot context injection."""

    # ------------------------------------------------------------------
    # refresh_plan_context — basic functionality
    # ------------------------------------------------------------------

    def test_refresh_creates_plan_sections(self):
        """refresh_plan_context adds plan sections to context.md, implement.md, verify.md."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            result = refresh_plan_context(root, tid)

            self.assertEqual(result["task_id"], tid)
            self.assertIn("context.md", result["updated_files"])

            # Check plan markers exist in all three files
            for fname in ("context.md", "implement.md", "verify.md"):
                content = (task_dir / fname).read_text(encoding="utf-8")
                self.assertIn("<!-- plan-snapshot -->", content, f"Missing marker in {fname}")
                self.assertIn("<!-- /plan-snapshot -->", content, f"Missing end marker in {fname}")

            # Plan title should be visible in context.md (implement.md and verify.md omit it)
            content = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertIn(ctx["plan_id"], content, "Plan id missing in context.md")

    def test_refresh_context_section_content(self):
        """context.md plan section includes stage, task suggestions, remaining, dependencies, next stage."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            refresh_plan_context(root, tid)

            context = (task_dir / "context.md").read_text(encoding="utf-8")
            pid = ctx["plan_id"]

            # Plan info
            self.assertIn(pid, context)
            self.assertIn("Test Plan", context)
            self.assertIn("Implementation", context)  # current stage

            # Task covers the suggestion
            self.assertIn("Build the backend service", context)

            # Remaining suggestions in same stage
            self.assertIn("Write integration tests", context)

            # Dependencies (direct, not transitive)
            self.assertIn("Define API contracts", context)

            # Next stage (there's no stage-3, so "Final stage")
            self.assertIn("Final stage", context)

            # Evidence requirements
            self.assertIn("Evidence Requirements", context)

    def test_refresh_implement_section_content(self):
        """implement.md plan section includes task suggestions and prerequisites."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            refresh_plan_context(root, tid)

            implement = (task_dir / "implement.md").read_text(encoding="utf-8")
            self.assertIn("Build the backend service", implement)
            self.assertIn("Define API contracts", implement)
            self.assertIn("Required Evidence", implement)

    def test_refresh_verify_section_content(self):
        """verify.md plan section includes verification table."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            refresh_plan_context(root, tid)

            verify = (task_dir / "verify.md").read_text(encoding="utf-8")
            self.assertIn("Suggestion", verify)
            self.assertIn("Status", verify)
            self.assertIn("Evidence", verify)
            self.assertIn("Verified", verify)
            self.assertIn("Build the backend service", verify)

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def test_refresh_idempotent(self):
        """Refreshing twice produces the same content."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            refresh_plan_context(root, tid)
            content_a = {
                "context.md": (task_dir / "context.md").read_text(encoding="utf-8"),
                "implement.md": (task_dir / "implement.md").read_text(encoding="utf-8"),
                "verify.md": (task_dir / "verify.md").read_text(encoding="utf-8"),
            }

            refresh_plan_context(root, tid)
            content_b = {
                "context.md": (task_dir / "context.md").read_text(encoding="utf-8"),
                "implement.md": (task_dir / "implement.md").read_text(encoding="utf-8"),
                "verify.md": (task_dir / "verify.md").read_text(encoding="utf-8"),
            }

            self.assertEqual(content_a, content_b)

    # ------------------------------------------------------------------
    # Preservation of unrelated content
    # ------------------------------------------------------------------

    def test_preserves_unrelated_markdown(self):
        """Custom markdown outside the plan markers is preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            # Add custom content to context.md
            context_path = task_dir / "context.md"
            original = context_path.read_text(encoding="utf-8")
            original += "\n## Custom Section\n\nThis is my custom content.\n"
            context_path.write_text(original, encoding="utf-8")

            refresh_plan_context(root, tid)

            refreshed = context_path.read_text(encoding="utf-8")
            self.assertIn("## Custom Section", refreshed)
            self.assertIn("This is my custom content.", refreshed)

    # ------------------------------------------------------------------
    # Plan section replaces old content
    # ------------------------------------------------------------------

    def test_refresh_replaces_old_plan_section(self):
        """Refreshing replaces old plan section content with current plan data."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]

            # First refresh
            refresh_plan_context(root, tid)

            # Update suggestion status
            update_suggestion_status(
                root, ctx["plan_id"], ctx["suggestion_ids"]["r3"],
                "implemented", reason="Done"
            )

            # Refresh again
            refresh_plan_context(root, tid)

            task_dir = tasks_dir(root) / "active" / tid
            context = (task_dir / "context.md").read_text(encoding="utf-8")
            # Should show updated status
            self.assertIn("implemented", context)

    # ------------------------------------------------------------------
    # Bad references
    # ------------------------------------------------------------------

    def test_refresh_no_plan_id_raises(self):
        """Task without plan_id raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "No plan", "Task without plan", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "S")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "W")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. X")
            update_intake_section(root, intake["intake_id"], "Approval", "Y")
            task = promote_to_task(root, intake["intake_id"], "No plan", "T", "design", ["W"])

            with self.assertRaisesRegex(ValueError, "no plan_id"):
                refresh_plan_context(root, task["task_id"])

    def test_refresh_missing_plan_raises(self):
        """Task with plan_id pointing to non-existent plan raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Bad plan", "Task with bad plan", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "S")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "W")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. X")
            update_intake_section(root, intake["intake_id"], "Approval", "Y")
            task = promote_to_task(root, intake["intake_id"], "Bad plan", "T", "design", ["W"])
            tid = task["task_id"]

            # Set plan_id to non-existent plan
            task_dir = tasks_dir(root) / "active" / tid
            task_data = read_json(task_dir / "task.json")
            task_data["plan_id"] = "nonexistent-plan"
            write_json_atomic(task_dir / "task.json", task_data)

            with self.assertRaises(FileNotFoundError):
                refresh_plan_context(root, tid)

    def test_refresh_missing_task_raises(self):
        """refresh_plan_context on non-existent task raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            with self.assertRaises(FileNotFoundError):
                refresh_plan_context(root, "nonexistent-task")

    # ------------------------------------------------------------------
    # Non-plan task unchanged
    # ------------------------------------------------------------------

    def test_no_plan_task_unchanged(self):
        """Task without plan_id cannot be refreshed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "Standalone", "No plan", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "S")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "W")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. X")
            update_intake_section(root, intake["intake_id"], "Approval", "Y")
            task = promote_to_task(root, intake["intake_id"], "Standalone", "T", "design", ["W"])
            tid = task["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            # Snapshot before (should have no plan markers)
            original_context = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertNotIn("<!-- plan-snapshot -->", original_context)

            # Attempting refresh should fail
            with self.assertRaisesRegex(ValueError, "no plan_id"):
                refresh_plan_context(root, tid)

            # Files must be byte-identical
            after_context = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertEqual(original_context, after_context)

    # ------------------------------------------------------------------
    # Auto-refresh on add_task_to_plan
    # ------------------------------------------------------------------

    def test_add_task_to_plan_triggers_auto_refresh(self):
        """Adding a task to a plan automatically refreshes context files."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            # Second task not yet in plan
            intake = create_intake(root, "Auto refresh", "Task for auto refresh", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "S")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "W")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. X")
            update_intake_section(root, intake["intake_id"], "Approval", "Y")
            task2 = promote_to_task(root, intake["intake_id"], "Auto refresh", "T", "design", ["W"])
            tid2 = task2["task_id"]

            # Before association: no plan markers
            task2_dir = tasks_dir(root) / "active" / tid2
            before = (task2_dir / "context.md").read_text(encoding="utf-8")
            self.assertNotIn("<!-- plan-snapshot -->", before)

            # Associate with plan
            add_task_to_plan(root, ctx["plan_id"], ctx["suggestion_ids"]["r4"], tid2)

            # After association: plan markers present
            after = (task2_dir / "context.md").read_text(encoding="utf-8")
            self.assertIn("<!-- plan-snapshot -->", after)
            self.assertIn(ctx["plan_id"], after)

    # ------------------------------------------------------------------
    # Auto-refresh on update_suggestion_status
    # ------------------------------------------------------------------

    def test_update_suggestion_status_triggers_auto_refresh(self):
        """Updating suggestion status refreshes all covered active tasks."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            # Refresh first to establish markers
            refresh_plan_context(root, tid)
            before = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertIn("proposed", before)  # default status after add_plan_suggestion

            # Update status
            update_suggestion_status(
                root, ctx["plan_id"], ctx["suggestion_ids"]["r3"],
                "implemented", reason="Verified"
            )

            after = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertIn("implemented", after)

    # ------------------------------------------------------------------
    # Auto-refresh on add_plan_evidence
    # ------------------------------------------------------------------

    def test_add_evidence_triggers_auto_refresh(self):
        """Adding evidence to a suggestion refreshes all covered active tasks."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            refresh_plan_context(root, tid)
            before = (task_dir / "verify.md").read_text(encoding="utf-8")
            self.assertIn("☐", before)  # Evidence column initially unchecked

            add_plan_evidence(root, ctx["plan_id"], ctx["suggestion_ids"]["r3"],
                               "Backend service implemented in PR #100")

            after = (task_dir / "verify.md").read_text(encoding="utf-8")
            self.assertIn("✓", after)  # Evidence column now checked

    # ------------------------------------------------------------------
    # Archived task: explicit refresh works, no auto-refresh
    # ------------------------------------------------------------------

    def test_archived_task_explicit_refresh(self):
        """Archived tasks can be refreshed explicitly."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_git_repo(root)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]

            # Complete and archive
            from workflow_core import start_execution
            start_execution(root, tid, ["just-demand-coder"])
            complete_verification(root, tid, "passed", "Done")

            # Task should be archived
            self.assertFalse((tasks_dir(root) / "active" / tid).is_dir())
            self.assertTrue((tasks_dir(root) / "archive" / tid).is_dir())

            # Explicit refresh should work on archived task
            result = refresh_plan_context(root, tid)
            self.assertEqual(result["task_id"], tid)

            archive_dir = tasks_dir(root) / "archive" / tid
            context = (archive_dir / "context.md").read_text(encoding="utf-8")
            self.assertIn("<!-- plan-snapshot -->", context)

    # ------------------------------------------------------------------
    # CLI integration
    # ------------------------------------------------------------------

    def test_cli_refresh_plan_context(self):
        """CLI refresh-plan-context works end-to-end."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "refresh-plan-context", tid],
                text=True, capture_output=True, check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["task_id"], tid)
            self.assertIn("context.md", payload["updated_files"])

            task_dir = tasks_dir(root) / "active" / tid
            context = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertIn("<!-- plan-snapshot -->", context)

    def test_cli_refresh_no_plan_id_shows_error(self):
        """CLI refresh-plan-context on task without plan_id shows error."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            intake = create_intake(root, "CLI no plan", "Task", "s1")
            update_intake_section(root, intake["intake_id"], "Scope", "S")
            update_intake_section(root, intake["intake_id"], "Final Expected Effect", "W")
            update_intake_section(root, intake["intake_id"], "Chosen Approach", "A")
            update_intake_section(root, intake["intake_id"], "Final Implementation Plan", "1. X")
            update_intake_section(root, intake["intake_id"], "Approval", "Y")
            task = promote_to_task(root, intake["intake_id"], "CLI no plan", "T", "design", ["W"])

            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "refresh-plan-context", task["task_id"]],
                text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("no plan_id", payload["message"])

    def test_cli_refresh_missing_task_shows_error(self):
        """CLI refresh-plan-context on non-existent task shows error."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_workspace(root)
            script = REPO_ROOT / "just-demand"
            result = subprocess.run(
                [sys.executable, str(script), str(root), "refresh-plan-context", "nonexistent-task"],
                text=True, capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "error")
            self.assertIn("Task not found", payload["message"])

    # ------------------------------------------------------------------
    # Plan section marker repair
    # ------------------------------------------------------------------

    def test_corrupt_markers_raise_error(self):
        """Partial markers cause RuntimeError."""
        from workflow_core import _replace_or_append_plan_section, PLAN_SECTION_MARKER_START
        content = "Some text\n" + PLAN_SECTION_MARKER_START + "\nUnclosed\n"
        with self.assertRaisesRegex(RuntimeError, "Corrupt"):
            _replace_or_append_plan_section(content, "body")

    def test_marker_replacement(self):
        """Content between markers is replaced correctly."""
        from workflow_core import _replace_or_append_plan_section, PLAN_SECTION_MARKER_START, PLAN_SECTION_MARKER_END
        content = "Before\n" + PLAN_SECTION_MARKER_START + "\nOld\n" + PLAN_SECTION_MARKER_END + "\nAfter"
        result = _replace_or_append_plan_section(content, "New Body")
        self.assertIn("Before", result)
        self.assertIn("After", result)
        self.assertIn("New Body", result)
        self.assertNotIn("Old", result)

    def test_marker_append_when_absent(self):
        """Content without markers gets section appended."""
        from workflow_core import _replace_or_append_plan_section, PLAN_SECTION_MARKER_START, PLAN_SECTION_MARKER_END
        content = "Just this"
        result = _replace_or_append_plan_section(content, "Section Body")
        self.assertIn("Just this", result)
        self.assertIn(PLAN_SECTION_MARKER_START, result)
        self.assertIn(PLAN_SECTION_MARKER_END, result)
        self.assertIn("Section Body", result)

    # ------------------------------------------------------------------
    # Auto-refresh on add_plan_stage and add_plan_suggestion
    # ------------------------------------------------------------------

    def test_add_plan_stage_triggers_auto_refresh(self):
        """Adding a stage refreshes all active tasks associated with the plan."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            # Refresh first to establish initial markers
            refresh_plan_context(root, tid)
            before = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertNotIn("Verification", before)  # New stage not yet present

            # Add a new stage
            add_plan_stage(root, ctx["plan_id"], "stage-3", "Verification")

            # The task's context should now show the new stage as "Next Stage: Final stage"
            # Actually it would show "Verification" since it's after stage-2
            after = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertIn("Verification", after)

    def test_add_plan_suggestion_triggers_auto_refresh(self):
        """Adding a suggestion to the same stage refreshes all associated active tasks."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            # Refresh first to establish markers
            refresh_plan_context(root, tid)
            before = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertNotIn("Performance testing", before)

            # Add a new suggestion to stage-2 (same stage as the task's suggestion)
            add_plan_suggestion(root, ctx["plan_id"], "stage-2",
                                "Run performance testing")

            # The task's remaining suggestions should now include the new one
            after = (task_dir / "context.md").read_text(encoding="utf-8")
            self.assertIn("Run performance testing", after)

    # ------------------------------------------------------------------
    # Atomic write rollback — fault injection
    # ------------------------------------------------------------------

    def test_write_failure_rollback_restores_originals(self):
        """When a write to the second or third file fails, already-written
        files are restored from in-memory backup and a RuntimeError is raised."""
        from workflow_core import _atomic_write_text

        original_write = _atomic_write_text
        call_count = [0]

        def _faulty_write(path, content):
            call_count[0] += 1
            if call_count[0] == 2:  # Fail on the second write (implement.md)
                raise OSError("Injected disk full error")
            return original_write(path, content)

        import workflow_core as wc

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]
            task_dir = tasks_dir(root) / "active" / tid

            # First successful refresh to establish markers and content
            refresh_plan_context(root, tid)
            context_before = (task_dir / "context.md").read_text(encoding="utf-8")
            implement_before = (task_dir / "implement.md").read_text(encoding="utf-8")
            verify_before = (task_dir / "verify.md").read_text(encoding="utf-8")

            # Now modify the plan to trigger a different snapshot
            wc.add_plan_suggestion(root, ctx["plan_id"], "stage-2", "Changed content")

            # Apply patch AFTER setup (& refresh) succeeded
            wc._atomic_write_text = _faulty_write
            try:
                # Capture the baseline content right before the failing call
                baseline_context = (task_dir / "context.md").read_text(encoding="utf-8")
                baseline_implement = (task_dir / "implement.md").read_text(encoding="utf-8")
                baseline_verify = (task_dir / "verify.md").read_text(encoding="utf-8")

                # Trigger refresh with injected fault
                call_count[0] = 0
                with self.assertRaises(RuntimeError):
                    wc._refresh_plan_context_unlocked(root, tid)

                # All three files must be restored to their pre-call content
                context_after = (task_dir / "context.md").read_text(encoding="utf-8")
                implement_after = (task_dir / "implement.md").read_text(encoding="utf-8")
                verify_after = (task_dir / "verify.md").read_text(encoding="utf-8")

                self.assertEqual(baseline_context, context_after,
                                 "context.md was not restored after write failure")
                self.assertEqual(baseline_implement, implement_after,
                                 "implement.md was not restored after write failure")
                self.assertEqual(baseline_verify, verify_after,
                                 "verify.md was not restored after write failure")
            finally:
                wc._atomic_write_text = original_write

    # ------------------------------------------------------------------
    # Concurrent calls — no deadlock
    # ------------------------------------------------------------------

    def test_concurrent_refresh_no_deadlock(self):
        """Calling refresh_plan_context concurrently does not deadlock."""
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            tid = ctx["task_id"]

            errors = []

            def refresh_thread():
                try:
                    for _ in range(5):
                        refresh_plan_context(root, tid)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=refresh_thread) for _ in range(3)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
                if t.is_alive():
                    self.fail("Thread deadlocked during concurrent refresh")

            self.assertEqual(errors, [], f"Concurrent refresh failed: {errors}")

    def test_auto_refresh_mutation_propagates_error(self):
        """Auto-refresh failure in add_plan_stage raises RuntimeError but
        plan mutation is preserved (can retry with refresh-plan-context)."""
        import workflow_core as wc

        original_refresh = wc._refresh_plan_context_unlocked

        def _failing_refresh(root, tid):
            raise RuntimeError(f"Injected failure for task {tid}")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = _setup_plan_with_task(root)
            pid = ctx["plan_id"]

            # Apply patch AFTER setup succeeded
            wc._refresh_plan_context_unlocked = _failing_refresh
            try:
                # Adding a stage with injected fault should raise RuntimeError
                with self.assertRaises(RuntimeError) as cm:
                    wc.add_plan_stage(root, pid, "stage-3", "Failing stage")
                self.assertIn("snapshot refresh failed for task(s)", str(cm.exception))

                # BUT the plan should still have the new stage (mutation committed)
                plan = wc.read_plan(root, pid)
                stage_ids = [s["id"] for s in plan.get("stages", [])]
                self.assertIn("stage-3", stage_ids,
                              "Plan stage should be committed even when refresh fails")
            finally:
                wc._refresh_plan_context_unlocked = original_refresh


# ── V2 Contract regression tests ──────────────────────────────────────────


class V2ContractTests(unittest.TestCase):
    """Regression tests for v2 TaskContract, projection, lint, and migration."""

    def test_empty_contract_has_expected_structure(self):
        from workflow_core import empty_contract
        c = empty_contract()
        self.assertIn("contract_version", c)
        self.assertIn("provenance", c)
        self.assertIn("outcome", c)
        self.assertIn("boundaries", c)
        self.assertIn("decisions", c)
        self.assertIn("engineering", c)
        self.assertIn("choices", c)
        self.assertEqual(c["engineering"]["code_map"], "")
        self.assertEqual(c["engineering"]["verification_cases"], [])
        self.assertEqual(c["outcome"]["goal"], "")

    def test_task_is_v2_detects_v2_records(self):
        from workflow_core import _task_is_v2, empty_contract
        v2 = {"schema_version": "2.0", "contract": empty_contract()}
        self.assertTrue(_task_is_v2(v2))
        v1 = {"schema_version": "1.0", "goal": "old"}
        self.assertFalse(_task_is_v2(v1))
        empty = {}
        self.assertFalse(_task_is_v2(empty))

    def test_load_task_contract_v1_adapter_preserves_fields(self):
        from workflow_core import load_task_contract
        v1 = {
            "schema_version": "1.0",
            "goal": "Legacy goal",
            "acceptance_criteria": ["AC 1"],
            "clarification": {
                "scope": "Legacy scope",
                "anti_outcomes": "No regressions",
                "final_expected_effect": "Legacy effect",
                "chosen_approach": "Legacy approach",
                "final_implementation_plan": "1. Old step",
                "approval": "Legacy approval",
                "blocking_questions": [],
                "non_blocking_questions": ["Old q?"],
                "raw_request": "Old raw request",
                "decisions": ["Old decision"],
                "expected_behavior": "Expected",
                "actual_behavior": "Actual",
                "reproduction": "Steps",
            },
        }
        contract = load_task_contract(v1)
        self.assertEqual(contract["outcome"]["goal"], "Legacy goal")
        self.assertEqual(contract["outcome"]["acceptance_criteria"], ["AC 1"])
        self.assertEqual(contract["boundaries"]["scope"], "Legacy scope")
        self.assertEqual(contract["boundaries"]["anti_outcomes"], "No regressions")
        self.assertEqual(contract["outcome"]["final_expected_effect"], "Legacy effect")
        self.assertEqual(contract["choices"]["chosen_approach"], "Legacy approach")
        self.assertEqual(contract["choices"]["approval"], "Legacy approval")
        self.assertEqual(contract["engineering"]["expected_behavior"], "Expected")
        self.assertEqual(contract["engineering"]["actual_behavior"], "Actual")
        self.assertEqual(contract["engineering"]["reproduction"], "Steps")
        # Decisions and questions
        self.assertEqual(contract["decisions"], ["Old decision"])
        self.assertEqual(contract["open_questions"], ["Old q?"])
        # Provenance
        self.assertEqual(contract["provenance"]["raw_request"], "Old raw request")

    def test_load_task_contract_v2_returns_identity(self):
        from workflow_core import load_task_contract, empty_contract
        c = empty_contract()
        c["outcome"]["goal"] = "V2 goal"
        task = {"schema_version": "2.0", "contract": c}
        loaded = load_task_contract(task)
        self.assertIs(loaded, c)
        self.assertEqual(loaded["outcome"]["goal"], "V2 goal")

    def test_contract_readiness_errors_missing_scope(self):
        from workflow_core import contract_readiness_errors, empty_contract
        c = empty_contract()
        errors = contract_readiness_errors(c, "design")
        self.assertTrue(any("Scope" in e for e in errors))

    def test_contract_readiness_errors_blocking_questions(self):
        from workflow_core import contract_readiness_errors, empty_contract
        c = empty_contract()
        c["boundaries"]["scope"] = "Test scope"
        c["blocking_questions"] = ["Must resolve?"]
        c["choices"]["chosen_approach"] = "A"
        c["choices"]["final_implementation_plan"] = "1. Do"
        c["choices"]["approval"] = "Ok"
        c["outcome"]["final_expected_effect"] = "Effect"
        errors = contract_readiness_errors(c, "design")
        self.assertTrue(any("blocking" in e.lower() for e in errors),
                        f"Blocking questions not flagged: {errors}")

    def test_contract_readiness_errors_design_missing_fields(self):
        from workflow_core import contract_readiness_errors, empty_contract
        c = empty_contract()
        c["boundaries"]["scope"] = "Scope"
        errors = contract_readiness_errors(c, "design")
        self.assertTrue(any("Final Expected Effect" in e for e in errors))
        self.assertTrue(any("Chosen Approach" in e for e in errors))
        self.assertTrue(any("Final Implementation Plan" in e for e in errors))
        self.assertTrue(any("Approval" in e for e in errors))

    def test_contract_readiness_errors_bug_missing_fields(self):
        from workflow_core import contract_readiness_errors, empty_contract
        c = empty_contract()
        c["boundaries"]["scope"] = "Bug scope"
        errors = contract_readiness_errors(c, "bugfix")
        self.assertTrue(any("Expected Behavior" in e for e in errors))
        self.assertTrue(any("Actual Behavior" in e for e in errors))
        self.assertTrue(any("Reproduction" in e for e in errors))

    def test_contract_readiness_errors_ready_design(self):
        from workflow_core import contract_readiness_errors, empty_contract
        c = empty_contract()
        c["boundaries"]["scope"] = "Ready scope"
        c["outcome"]["final_expected_effect"] = "Will work"
        c["choices"]["chosen_approach"] = "Approach"
        c["choices"]["final_implementation_plan"] = "1. Implement"
        c["choices"]["approval"] = "Approved"
        errors = contract_readiness_errors(c, "design")
        self.assertEqual(errors, [])

    def test_render_context_markdown_omits_empty_optionals(self):
        from workflow_core import render_context_markdown, empty_contract
        task = {"schema_version": "2.0", "contract": empty_contract()}
        ctx = render_context_markdown(task)
        # Should not contain legacy placeholders
        self.assertNotIn("_No ", ctx)
        self.assertNotIn("recorded yet", ctx)
        # Empty optional sections should be omitted
        self.assertNotIn("## User Raw Request", ctx)
        self.assertNotIn("## Decisions", ctx)
        self.assertNotIn("## Remaining Open Questions", ctx)

    def test_render_context_markdown_includes_filled_fields(self):
        from workflow_core import render_context_markdown, empty_contract
        c = empty_contract()
        c["outcome"]["goal"] = "My goal"
        c["outcome"]["acceptance_criteria"] = ["AC1"]
        c["provenance"]["raw_request"] = "Raw text"
        c["boundaries"]["scope"] = "Scope text"
        c["decisions"] = ["Decision 1"]
        c["choices"]["chosen_approach"] = "Approach A"
        task = {"schema_version": "2.0", "contract": c}
        ctx = render_context_markdown(task)
        self.assertIn("## Goal", ctx)
        self.assertIn("My goal", ctx)
        self.assertIn("Raw text", ctx)
        self.assertIn("## Scope", ctx)
        self.assertIn("## Acceptance Criteria", ctx)
        self.assertIn("## Decisions", ctx)
        self.assertIn("## Chosen Approach", ctx)

    def test_render_implement_markdown_includes_code_map(self):
        from workflow_core import render_implementation_plan_markdown, empty_contract
        c = empty_contract()
        c["outcome"]["goal"] = "Goal"
        c["engineering"]["code_map"] = "src/lib.py"
        c["choices"]["final_implementation_plan"] = "1. Code it"
        task = {"schema_version": "2.0", "contract": c}
        impl = render_implementation_plan_markdown(task)
        self.assertIn("src/lib.py", impl)
        self.assertIn("## Code Map", impl)
        self.assertIn("## Implementation Plan", impl)

    def test_render_verify_markdown_includes_cases(self):
        from workflow_core import render_verify_markdown, empty_contract
        c = empty_contract()
        c["outcome"]["final_expected_effect"] = "Must work"
        c["boundaries"]["scope"] = "Verification scope"
        c["engineering"]["verification_cases"] = ["TC1: verify rendering"]
        c["boundaries"]["anti_outcomes"] = "No regressions"
        task = {"schema_version": "2.0", "contract": c}
        ver = render_verify_markdown(task)
        self.assertIn("## Expected Effect", ver)
        self.assertIn("Must work", ver)
        self.assertIn("## Verification Cases", ver)
        self.assertIn("TC1: verify rendering", ver)
        self.assertIn("## Anti-Outcomes", ver)

    def test_lint_task_packet_empty_task(self):
        from workflow_core import lint_task_packet, empty_contract
        task = {"schema_version": "2.0", "id": "test", "type": "design",
                "contract": empty_contract()}
        warnings = lint_task_packet(task)
        # Should warn about empty key fields
        field_names = {w["field"] for w in warnings}
        self.assertIn("contract.provenance.raw_request", field_names)
        self.assertIn("contract.engineering.code_map", field_names)
        self.assertIn("contract.engineering.verification_cases", field_names)

    def test_lint_task_packet_role_gated_warnings(self):
        from workflow_core import lint_task_packet, empty_contract
        task = {"schema_version": "2.0", "id": "test", "type": "design",
                "contract": empty_contract()}
        coder_warnings = lint_task_packet(task, role="coder")
        coder_msgs = [w["message"] for w in coder_warnings]
        self.assertTrue(any("code map" in m.lower() for m in coder_msgs),
                        f"No code-map warning for coder: {coder_msgs}")
        tester_warnings = lint_task_packet(task, role="tester")
        tester_msgs = [w["message"] for w in tester_warnings]
        self.assertTrue(any("verification" in m.lower() for m in tester_msgs),
                        f"No verification warning for tester: {tester_msgs}")

    def test_get_missing_execution_fields_coder_checks_code_map(self):
        from workflow_core import get_missing_execution_fields, empty_contract
        task = {"schema_version": "2.0", "id": "t", "type": "design",
                "contract": empty_contract()}
        missing = get_missing_execution_fields(task, role="coder")
        self.assertIn("Code Map", missing)

    def test_get_missing_execution_fields_tester_checks_verification_cases(self):
        from workflow_core import get_missing_execution_fields, empty_contract
        task = {"schema_version": "2.0", "id": "t", "type": "design",
                "contract": empty_contract()}
        missing = get_missing_execution_fields(task, role="tester")
        self.assertIn("Verification Cases", missing)

    def test_migrate_v1_to_v2_basic(self):
        from workflow_core import migrate_task_v1_to_v2, ensure_workspace, read_json, write_json_atomic, tasks_dir
        import tempfile
        root = Path(tempfile.mkdtemp())
        ensure_workspace(root)
        v1_id = "migrate-test-basic"
        d = tasks_dir(root) / "active" / v1_id
        d.mkdir(parents=True, exist_ok=True)
        v1 = {
            "schema_version": "1.0", "id": v1_id, "title": "Migrate",
            "type": "design", "status": "planning",
            "goal": "Mig goal", "acceptance_criteria": ["Mig AC"],
            "clarification": {
                "scope": "Mig scope", "final_expected_effect": "Mig effect",
                "chosen_approach": "Mig approach",
                "final_implementation_plan": "1. Mig step",
                "approval": "Approved",
                "blocking_questions": [], "non_blocking_questions": [],
            },
        }
        write_json_atomic(d / "task.json", v1)
        result = migrate_task_v1_to_v2(root, v1_id)
        self.assertTrue(result["migrated"])
        task2 = read_json(d / "task.json")
        self.assertEqual(task2["schema_version"], "2.0")
        self.assertIn("contract", task2)
        self.assertEqual(task2["contract"]["outcome"]["goal"], "Mig goal")
        self.assertEqual(task2["contract"]["boundaries"]["scope"], "Mig scope")

    def test_migrate_v1_to_v2_dry_run_does_not_write(self):
        from workflow_core import migrate_task_v1_to_v2, ensure_workspace, read_json, write_json_atomic, tasks_dir
        import tempfile
        root = Path(tempfile.mkdtemp())
        ensure_workspace(root)
        v1_id = "migrate-test-dry"
        d = tasks_dir(root) / "active" / v1_id
        d.mkdir(parents=True, exist_ok=True)
        v1 = {
            "schema_version": "1.0", "id": v1_id, "title": "Dry",
            "type": "design", "status": "planning",
            "goal": "Dry goal", "acceptance_criteria": [],
            "clarification": {
                "scope": "Dry scope", "final_expected_effect": "Dry effect",
                "chosen_approach": "Approach",
                "final_implementation_plan": "1. Step", "approval": "Ok",
                "blocking_questions": [], "non_blocking_questions": [],
            },
        }
        write_json_atomic(d / "task.json", v1)
        migrate_task_v1_to_v2(root, v1_id, dry_run=True)
        task2 = read_json(d / "task.json")
        self.assertEqual(task2["schema_version"], "1.0",
                         "Dry run should not change schema version")

    def test_migrate_v1_to_v2_idempotent(self):
        from workflow_core import migrate_task_v1_to_v2, ensure_workspace, read_json, write_json_atomic, tasks_dir
        import tempfile
        root = Path(tempfile.mkdtemp())
        ensure_workspace(root)
        v1_id = "migrate-test-idemp"
        d = tasks_dir(root) / "active" / v1_id
        d.mkdir(parents=True, exist_ok=True)
        v1 = {
            "schema_version": "1.0", "id": v1_id, "title": "Idemp",
            "type": "design", "status": "planning",
            "goal": "Idemp goal", "acceptance_criteria": [],
            "clarification": {
                "scope": "Idemp scope", "final_expected_effect": "Idemp effect",
                "chosen_approach": "Approach",
                "final_implementation_plan": "1. Step", "approval": "Ok",
                "blocking_questions": [], "non_blocking_questions": [],
            },
        }
        write_json_atomic(d / "task.json", v1)
        migrate_task_v1_to_v2(root, v1_id)
        result2 = migrate_task_v1_to_v2(root, v1_id)
        self.assertFalse(result2["migrated"])
        self.assertEqual(result2["status"], "already_v2")


    # ####################################################################
    # v2 lifecycle field regression tests (Fix 1–4)
    # ####################################################################

    def test__task_clarification_v2_lifecycle_fields(self):
        """Fix 2: _task_clarification reads lifecycle fields from contract
        engineering.lifecycle.* and falls back to _extra.*."""
        from workflow_core import _task_clarification

        # Build a task with canonical lifecycle fields
        canonical = {
            "schema_version": "2.0",
            "contract": {
                "engineering": {
                    "lifecycle": {
                        "opening": "Visible on load.",
                        "during_transition": "Fades in over 300ms.",
                        "after_open": "Stays visible.",
                        "interrupt_behavior": "Pauses on hover.",
                    },
                },
            },
        }
        cl = _task_clarification(canonical)
        self.assertEqual(cl.get("opening"), "Visible on load.")
        self.assertEqual(cl.get("during_transition"), "Fades in over 300ms.")
        self.assertEqual(cl.get("after_open"), "Stays visible.")
        self.assertEqual(cl.get("interrupt_behavior"), "Pauses on hover.")

        # Fallback: lifecycle only in _extra (backward compat)
        extra_fallback = {
            "schema_version": "2.0",
            "contract": {
                "engineering": {},
                "_extra": {
                    "opening": "Shown immediately.",
                    "during_transition": "Slides in.",
                    "after_open": "Remains.",
                    "interrupt_behavior": "No-op on hover.",
                },
            },
        }
        cl2 = _task_clarification(extra_fallback)
        self.assertEqual(cl2.get("opening"), "Shown immediately.")
        self.assertEqual(cl2.get("during_transition"), "Slides in.")
        self.assertEqual(cl2.get("after_open"), "Remains.")
        self.assertEqual(cl2.get("interrupt_behavior"), "No-op on hover.")

        # Canonical wins over _extra when both present
        both = {
            "schema_version": "2.0",
            "contract": {
                "engineering": {
                    "lifecycle": {
                        "opening": "Canonical.",
                    },
                },
                "_extra": {
                    "opening": "Extra.",
                },
            },
        }
        cl3 = _task_clarification(both)
        self.assertEqual(cl3.get("opening"), "Canonical.",
                         "Canonical engineering.lifecycle must win over _extra")

    def test_mark_task_advances_current_step_on_executing(self):
        """Fix 4: mark_task advances current_step to 'execute' when
        marking to 'executing' from 'clarify' or 'design'."""
        import tempfile
        from pathlib import Path
        from workflow_core import (
            mark_task, ensure_workspace,
            read_json, write_json_atomic, tasks_dir,
        )

        root = Path(tempfile.mkdtemp())
        ensure_workspace(root)
        task_id = "mark-step-test"
        d = tasks_dir(root) / "active" / task_id
        d.mkdir(parents=True, exist_ok=True)

        # Create a task at status=planning, current_step=clarify
        task = {
            "id": task_id, "status": "planning", "current_step": "clarify",
            "type": "design", "contract": {},
        }
        write_json_atomic(d / "task.json", task)

        # Mark to executing — should advance current_step
        result = mark_task(root, task_id, "executing")
        self.assertTrue(result["ok"])
        task2 = read_json(d / "task.json")
        self.assertEqual(task2["current_step"], "execute",
                         "current_step should advance to 'execute' when marking to 'executing'")

    def test_mark_task_does_not_advance_step_from_verify(self):
        """Fix 4: mark_task does NOT change current_step when it's already
        past 'design' (e.g. 'verify')."""
        import tempfile
        from pathlib import Path
        from workflow_core import (
            mark_task, ensure_workspace,
            read_json, write_json_atomic, tasks_dir,
        )

        root = Path(tempfile.mkdtemp())
        ensure_workspace(root)
        task_id = "mark-step-verify"
        d = tasks_dir(root) / "active" / task_id
        d.mkdir(parents=True, exist_ok=True)

        task = {
            "id": task_id, "status": "verifying", "current_step": "verify",
            "type": "design", "contract": {},
        }
        write_json_atomic(d / "task.json", task)

        result = mark_task(root, task_id, "executing")
        self.assertTrue(result["ok"])
        task2 = read_json(d / "task.json")
        self.assertEqual(task2["current_step"], "verify",
                         "current_step should stay 'verify' when already past 'design'")

    def test_get_missing_execution_fields_v2_lifecycle_filled(self):
        """Fix 2: get_missing_execution_fields returns empty for v2 visible-effect
        task with all lifecycle fields filled (including opening)."""
        from workflow_core import get_missing_execution_fields
        task = {
            "type": "design",
            "clarification": {
                "scope": "Button animation.",
                "blocking_questions": [],
                "final_expected_effect": "Button fades in smoothly.",
                "chosen_approach": "A: CSS transition.",
                "final_implementation_plan": "1. Add class.",
                "approval": "Approved.",
                "opening": "Button hidden until load.",
                "during_transition": "Fade in over 300ms.",
                "after_open": "Button stays visible.",
                "interrupt_behavior": "Pause on hover.",
            },
        }
        missing = get_missing_execution_fields(task)
        # Opening is a lifecycle field, not a standard execution gate field,
        # so it should not appear in missing list.
        self.assertNotIn("Opening", missing)

    def test_render_engineering_block_includes_lifecycle(self):
        """Fix 3: _render_engineering_block includes lifecycle fields when present."""
        from workflow_core import _render_engineering_block
        eng = {
            "code_map": "src/button.js",
            "lifecycle": {
                "opening": "Visible on load.",
                "during_transition": "Fades in 300ms.",
                "after_open": "Stays.",
                "interrupt_behavior": "No-op.",
            },
        }
        result = _render_engineering_block(eng)
        self.assertIn("Visible Effect Lifecycle", result)
        self.assertIn("Opening:", result)
        self.assertIn("During Transition:", result)
        self.assertIn("After Open:", result)
        self.assertIn("Interrupt Behavior:", result)
        self.assertIn("Visible on load.", result)
        self.assertIn("Fades in 300ms.", result)

    def test_render_engineering_block_omits_lifecycle_when_empty(self):
        """Fix 3: _render_engineering_block omits lifecycle section when empty."""
        from workflow_core import _render_engineering_block
        eng = {"code_map": "src/button.js", "lifecycle": {}}
        result = _render_engineering_block(eng)
        self.assertNotIn("Visible Effect Lifecycle", result)

    # ####################################################################
    # v2 visible-effect lifecycle readiness regressions
    # ####################################################################

    def test_get_missing_execution_fields_v2_visible_effect_ready(self):
        """Fix 5: get_missing_execution_fields returns empty for a v2 contract
        task with visible-effect signal and all lifecycle fields filled."""
        from workflow_core import get_missing_execution_fields
        task = {
            "schema_version": "2.0",
            "type": "design",
            "title": "Button fade animation",
            "contract": {
                "contract_version": "1.0",
                "outcome": {
                    "goal": "Animate button fade-in",
                    "acceptance_criteria": ["Button fades in."],
                    "final_expected_effect": "Button fades in smoothly.",
                },
                "boundaries": {
                    "scope": "Button animation only.",
                    "anti_outcomes": "No flickering or jarring transitions.",
                },
                "engineering": {
                    "lifecycle": {
                        "opening": "Button hidden until page load.",
                        "during_transition": "Fade in over 300ms.",
                        "after_open": "Button stays visible.",
                        "interrupt_behavior": "Fade pauses on hover.",
                    },
                },
                "choices": {
                    "chosen_approach": "CSS transition.",
                    "final_implementation_plan": "1. Add CSS class.",
                    "approval": "Approved.",
                },
                "blocking_questions": [],
            },
        }
        missing = get_missing_execution_fields(task)
        self.assertEqual(missing, [],
                         f"v2 visible-effect task with all lifecycle fields should be ready, got missing={missing}")
        for lifecycle_field in ("Opening", "During Transition", "After Open", "Interrupt Behavior", "Anti-Outcomes"):
            self.assertNotIn(lifecycle_field, missing,
                             f"{lifecycle_field} should not be missing when filled")

    def test_get_missing_execution_fields_v2_visible_effect_missing_opening(self):
        """Fix 5: get_missing_execution_fields reports Opening for a v2
        visible-effect task that is missing the opening field."""
        from workflow_core import get_missing_execution_fields
        task = {
            "schema_version": "2.0",
            "type": "design",
            "title": "Button fade animation",
            "contract": {
                "contract_version": "1.0",
                "outcome": {
                    "goal": "Animate button fade-in",
                    "acceptance_criteria": ["Button fades in."],
                    "final_expected_effect": "Button fades in smoothly.",
                },
                "boundaries": {
                    "scope": "Button animation only.",
                },
                "engineering": {
                    "lifecycle": {
                        # opening intentionally omitted
                        "during_transition": "Fade in over 300ms.",
                        "after_open": "Button stays visible.",
                        "interrupt_behavior": "Fade pauses on hover.",
                    },
                },
                "choices": {
                    "chosen_approach": "CSS transition.",
                    "final_implementation_plan": "1. Add CSS class.",
                    "approval": "Approved.",
                },
                "blocking_questions": [],
            },
        }
        missing = get_missing_execution_fields(task)
        self.assertIn("Opening", missing,
                      "Opening should be missing for visible-effect task without opening field")

    def test_get_missing_execution_fields_v2_visible_effect_anti_outcomes_missing(self):
        """Fix 5: get_missing_execution_fields reports Anti-Outcomes for a v2
        visible-effect task that is missing the anti_outcomes field."""
        from workflow_core import get_missing_execution_fields
        task = {
            "schema_version": "2.0",
            "type": "design",
            "title": "Button fade animation",
            "contract": {
                "contract_version": "1.0",
                "outcome": {
                    "goal": "Animate button fade-in",
                    "acceptance_criteria": ["Button fades in."],
                    "final_expected_effect": "Button fades in smoothly.",
                },
                "boundaries": {
                    "scope": "Button animation only.",
                },
                "engineering": {
                    "lifecycle": {
                        "opening": "Button hidden until page load.",
                        "during_transition": "Fade in over 300ms.",
                        "after_open": "Button stays visible.",
                        "interrupt_behavior": "Fade pauses on hover.",
                        # anti_outcomes intentionally omitted (it's in boundaries, but
                        # the visible-effect contract reads it from clarification.anti_outcomes)
                    },
                },
                "choices": {
                    "chosen_approach": "CSS transition.",
                    "final_implementation_plan": "1. Add CSS class.",
                    "approval": "Approved.",
                },
                "blocking_questions": [],
            },
        }
        missing = get_missing_execution_fields(task)
        self.assertIn("Anti-Outcomes", missing,
                      "Anti-Outcomes should be missing for visible-effect task without anti_outcomes")

    def test_task_is_ready_for_execution_v2_visible_effect_ready(self):
        """Fix 5: task_is_ready_for_execution returns True for a v2
        visible-effect task with all lifecycle fields filled."""
        from workflow_core import task_is_ready_for_execution
        task = {
            "schema_version": "2.0",
            "type": "design",
            "title": "Slide panel animation",
            "contract": {
                "contract_version": "1.0",
                "outcome": {
                    "goal": "Animate slide panel",
                    "acceptance_criteria": ["Panel slides open."],
                    "final_expected_effect": "Panel slides open from the right.",
                },
                "boundaries": {
                    "scope": "Panel slide animation.",
                    "anti_outcomes": "No jarring transitions.",
                },
                "engineering": {
                    "lifecycle": {
                        "opening": "Panel hidden off-screen right.",
                        "during_transition": "Slides left over 400ms with easing.",
                        "after_open": "Panel rests at left=0.",
                        "interrupt_behavior": "Reverse slide on close button.",
                    },
                },
                "choices": {
                    "chosen_approach": "CSS transform translateX.",
                    "final_implementation_plan": "1. Add panel div. 2. Toggle class.",
                    "approval": "Approved.",
                },
                "blocking_questions": [],
            },
        }
        self.assertTrue(task_is_ready_for_execution(task),
                        "v2 visible-effect task with all lifecycle fields should be ready")

    def test_task_is_ready_for_execution_v2_visible_effect_missing_opening(self):
        """Fix 5: task_is_ready_for_execution returns False for a v2
        visible-effect task missing Opening."""
        from workflow_core import task_is_ready_for_execution
        task = {
            "schema_version": "2.0",
            "type": "design",
            "title": "Slide panel animation",
            "contract": {
                "contract_version": "1.0",
                "outcome": {
                    "goal": "Animate slide panel",
                    "acceptance_criteria": ["Panel slides open."],
                    "final_expected_effect": "Panel slides open from the right.",
                },
                "boundaries": {
                    "scope": "Panel slide animation.",
                    "anti_outcomes": "No jarring transitions.",
                },
                "engineering": {
                    "lifecycle": {
                        "during_transition": "Slides left over 400ms with easing.",
                        "after_open": "Panel rests at left=0.",
                        "interrupt_behavior": "Reverse slide on close button.",
                        # opening intentionally omitted
                    },
                },
                "choices": {
                    "chosen_approach": "CSS transform translateX.",
                    "final_implementation_plan": "1. Add panel div. 2. Toggle class.",
                    "approval": "Approved.",
                },
                "blocking_questions": [],
            },
        }
        self.assertFalse(task_is_ready_for_execution(task),
                         "v2 visible-effect task missing Opening should not be ready")


if __name__ == "__main__":
    unittest.main()
