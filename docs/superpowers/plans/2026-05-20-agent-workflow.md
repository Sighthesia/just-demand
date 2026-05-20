# Agent Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal OpenCode-first local agent workflow runtime with file-backed intake, task promotion, lifecycle state, locks, validation revisions, and context injection hooks.

**Architecture:** Implement the state-changing core in Python scripts under `.agent-workflow/scripts/`, with tests using Python `unittest` and temporary directories. Implement OpenCode plugins as thin JavaScript adapters that read workflow state and inject main-session breadcrumbs or subagent context without mutating `.agent-workflow/` state.

**Tech Stack:** Python 3 standard library, Node.js standard library, OpenCode plugin files, Markdown task/context files, JSON/JSONL state.

---

## File Structure

- Create `.agent-workflow/scripts/workflow_core.py`: pure Python workflow functions for directories, atomic JSON writes, events, intake creation, task promotion, locks, lifecycle transitions, and validation revisions.
- Create `.agent-workflow/scripts/task.py`: CLI wrapper around `workflow_core.py` for manual and agent-driven workflow actions.
- Create `.agent-workflow/global/rules.md`: stable user-facing workflow rules.
- Create `.agent-workflow/workspace/preferences.md`, `.agent-workflow/workspace/decisions.md`, `.agent-workflow/workspace/deferred_options.md`, `.agent-workflow/workspace/facts.md`, `.agent-workflow/workspace/open_questions.md`: workspace-level durable memory files.
- Create `.opencode/plugins/agent-workflow-lib.js`: shared JavaScript helpers for reading workflow state and task files.
- Create `.opencode/plugins/agent-workflow-session-start.js`: injects main-session startup context.
- Create `.opencode/plugins/agent-workflow-state.js`: injects per-turn workflow breadcrumb.
- Create `.opencode/plugins/agent-workflow-subagent-context.js`: injects task package context into workflow subagent prompts.
- Create `.opencode/agent/workflow-research.md`, `.opencode/agent/workflow-implement.md`, `.opencode/agent/workflow-check.md`, `.opencode/agent/workflow-docs.md`: OpenCode subagent definitions.
- Create `tests/agent_workflow/test_workflow_core.py`: Python tests for workflow state and lifecycle.
- Create `tests/agent_workflow/test_opencode_plugins.mjs`: Node tests for plugin helper behavior.

Current workspace note: `/home/Sighthesia/0_Files/Producing/Software/Workflows/on-demand` is not a git repository. Commit steps are included for execution inside a git-backed project; skip them in this current non-git workspace.

---

### Task 1: Python Workflow Core Skeleton And Intake Creation

**Files:**
- Create: `.agent-workflow/scripts/workflow_core.py`
- Create: `tests/agent_workflow/test_workflow_core.py`

- [ ] **Step 1: Write failing tests for directory initialization and intake creation**

Create `tests/agent_workflow/test_workflow_core.py` with this content:

```python
import json
import tempfile
import unittest
from pathlib import Path

import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / ".agent-workflow" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from workflow_core import create_intake, ensure_workspace, read_json


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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify they fail because `workflow_core` does not exist**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'workflow_core'`.

- [ ] **Step 3: Implement workspace initialization and intake creation**

Create `.agent-workflow/scripts/workflow_core.py` with this content:

```python
from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "work-item"


def workflow_dir(root: Path) -> Path:
    return root / ".agent-workflow"


def workspace_dir(root: Path) -> Path:
    return workflow_dir(root) / "workspace"


def tasks_dir(root: Path) -> Path:
    return workflow_dir(root) / "tasks"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(encoded)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def default_workspace_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "current_intake_id": None,
        "current_task_id": None,
        "active_task_ids": [],
        "active_sessions": {},
        "last_event_seq": 0,
        "locks_summary": [],
        "updated_at": "",
    }


def ensure_workspace(root: Path) -> None:
    base = workflow_dir(root)
    for directory in [
        base / "global",
        base / "workspace" / "intake",
        base / "workspace" / "sessions",
        base / "tasks" / "active",
        base / "tasks" / "archive",
        base / "scripts",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    memory_files = {
        base / "global" / "rules.md": "# Agent Workflow Rules\n\n",
        base / "global" / "architecture.md": "# Agent Workflow Architecture\n\n",
        base / "global" / "glossary.md": "# Agent Workflow Glossary\n\n",
        base / "workspace" / "preferences.md": "# Preferences\n\n",
        base / "workspace" / "decisions.md": "# Decisions\n\n",
        base / "workspace" / "deferred_options.md": "# Deferred Options\n\n",
        base / "workspace" / "facts.md": "# Facts\n\n",
        base / "workspace" / "open_questions.md": "# Open Questions\n\n",
        base / "workspace" / "events.jsonl": "",
        base / "workspace" / "locks.json": json.dumps({"schema_version": SCHEMA_VERSION, "locks": []}, indent=2) + "\n",
    }
    for path, content in memory_files.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    state_path = base / "workspace" / "state.json"
    if not state_path.exists():
        write_json_atomic(state_path, default_workspace_state())


def next_event_seq(root: Path) -> int:
    state_path = workspace_dir(root) / "state.json"
    state = read_json(state_path)
    next_seq = int(state.get("last_event_seq", 0)) + 1
    state["last_event_seq"] = next_seq
    state["updated_at"] = utc_now()
    write_json_atomic(state_path, state)
    return next_seq


def append_workspace_event(root: Path, event_type: str, entity_type: str, entity_id: str, summary: str, **extra: Any) -> dict[str, Any]:
    seq = next_event_seq(root)
    event = {
        "schema_version": SCHEMA_VERSION,
        "seq": seq,
        "id": f"evt_{seq:06d}",
        "type": event_type,
        "actor": extra.pop("actor", "main-agent"),
        "entity_type": entity_type,
        "entity_id": entity_id,
        "correlation_id": extra.pop("correlation_id", None),
        "at": utc_now(),
        "before_status": extra.pop("before_status", None),
        "after_status": extra.pop("after_status", None),
        "summary": summary,
    }
    event.update(extra)
    events_path = workspace_dir(root) / "events.jsonl"
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def create_intake(root: Path, title: str, raw_request: str, session_id: str) -> dict[str, str]:
    ensure_workspace(root)
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    intake_id = f"{date_prefix}-{slugify(title)}-intake"
    intake_path = workspace_dir(root) / "intake" / f"{intake_id}.md"
    now = utc_now()
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat()
    intake_path.write_text(
        "\n".join(
            [
                f"# Intake: {title}",
                "",
                f"Id: {intake_id}",
                "Status: clarifying",
                f"Created At: {now}",
                f"Session: {session_id}",
                "",
                "## Raw Request",
                raw_request.strip(),
                "",
                "## Current Understanding",
                "The main agent has not summarized this intake yet.",
                "",
                "## Expected Outcome",
                "",
                "## Anti-Outcome",
                "",
                "## Decisions",
                "",
                "## Deferred Options",
                "",
                "## Open Questions",
                "",
            ]
        ),
        encoding="utf-8",
    )

    state_path = workspace_dir(root) / "state.json"
    state = read_json(state_path)
    state["current_intake_id"] = intake_id
    state.setdefault("active_sessions", {})[session_id] = {
        "current_intake_id": intake_id,
        "current_task_id": None,
        "updated_at": now,
    }
    state["updated_at"] = now
    write_json_atomic(state_path, state)

    append_workspace_event(
        root,
        "intake_created",
        "intake",
        intake_id,
        f"Created intake {intake_id}",
        after_status="clarifying",
    )
    return {"intake_id": intake_id, "path": str(intake_path)}
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core -v`

Expected: PASS, 2 tests run.

- [ ] **Step 5: Commit if inside a git repository**

Run: `git rev-parse --is-inside-work-tree`

Expected in this workspace: FAIL because the current directory is not a git repository.

If running in a git repository, run:

```bash
git add .agent-workflow/scripts/workflow_core.py tests/agent_workflow/test_workflow_core.py
git commit -m "feat: add workflow intake core"
```

---

### Task 2: Task Promotion And Formal Task Package

**Files:**
- Modify: `.agent-workflow/scripts/workflow_core.py`
- Modify: `tests/agent_workflow/test_workflow_core.py`

- [ ] **Step 1: Add failing tests for intake promotion**

Append this test method inside `WorkflowCoreTests` before the `if __name__ == "__main__"` block:

```python
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
```

- [ ] **Step 2: Run the test and verify it fails because `promote_to_task` is missing**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core.WorkflowCoreTests.test_promote_intake_to_task_creates_formal_package -v`

Expected: FAIL with `ImportError` or `AttributeError` for `promote_to_task`.

- [ ] **Step 3: Implement task promotion helpers**

Append this code to `.agent-workflow/scripts/workflow_core.py`:

```python

def append_task_event(root: Path, task_id: str, event_type: str, summary: str, **extra: Any) -> dict[str, Any]:
    task_path = tasks_dir(root) / "active" / task_id
    task_json_path = task_path / "task.json"
    task_data = read_json(task_json_path) if task_json_path.exists() else {"last_event_seq": 0}
    seq = int(task_data.get("last_event_seq", 0)) + 1
    task_data["last_event_seq"] = seq
    if task_json_path.exists():
        task_data["updated_at"] = utc_now()
        write_json_atomic(task_json_path, task_data)
    event = {
        "schema_version": SCHEMA_VERSION,
        "seq": seq,
        "id": f"evt_{seq:06d}",
        "type": event_type,
        "actor": extra.pop("actor", "main-agent"),
        "entity_type": "task",
        "entity_id": task_id,
        "correlation_id": extra.pop("correlation_id", None),
        "at": utc_now(),
        "before_status": extra.pop("before_status", None),
        "after_status": extra.pop("after_status", None),
        "summary": summary,
    }
    event.update(extra)
    with (task_path / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def default_task_json(task_id: str, intake_id: str, title: str, goal: str, task_type: str, acceptance_criteria: list[str]) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "id": task_id,
        "source_intake_id": intake_id,
        "title": title,
        "type": task_type,
        "status": "planning",
        "current_step": "clarify",
        "owner_session": "main",
        "assigned_subagents": [],
        "goal": goal,
        "constraints": [],
        "acceptance_criteria": acceptance_criteria,
        "validation_revision": None,
        "verification_status": "not_started",
        "related_files": [],
        "context_sources": [],
        "decision_refs": [],
        "deferred_option_refs": [],
        "subtasks": [],
        "locks": [],
        "last_event_seq": 0,
        "created_at": now,
        "updated_at": now,
    }


def promote_to_task(root: Path, intake_id: str, title: str, goal: str, task_type: str, acceptance_criteria: list[str]) -> dict[str, str]:
    ensure_workspace(root)
    task_id = f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{slugify(title)}"
    active_root = tasks_dir(root) / "active"
    final_dir = active_root / task_id
    temp_dir = active_root / f".{task_id}.tmp"
    if final_dir.exists():
        raise FileExistsError(f"Task already exists: {task_id}")
    if temp_dir.exists():
        raise FileExistsError(f"Temporary task directory already exists: {temp_dir}")

    temp_dir.mkdir(parents=True)
    (temp_dir / "outputs").mkdir()
    (temp_dir / "research").mkdir()
    write_json_atomic(temp_dir / "task.json", default_task_json(task_id, intake_id, title, goal, task_type, acceptance_criteria))
    (temp_dir / "context.md").write_text(f"# Context\n\n## Goal\n{goal}\n", encoding="utf-8")
    (temp_dir / "decisions.md").write_text("# Decisions\n\n", encoding="utf-8")
    (temp_dir / "open_questions.md").write_text("# Open Questions\n\n", encoding="utf-8")
    (temp_dir / "implement.md").write_text(f"# Implement Brief\n\nBuild: {goal}\n", encoding="utf-8")
    (temp_dir / "verify.md").write_text("# Verify Brief\n\nVerify the acceptance criteria in task.json.\n", encoding="utf-8")
    (temp_dir / "events.jsonl").write_text("", encoding="utf-8")
    temp_dir.replace(final_dir)

    state_path = workspace_dir(root) / "state.json"
    state = read_json(state_path)
    state["current_intake_id"] = None
    state["current_task_id"] = task_id
    active_task_ids = list(dict.fromkeys(state.get("active_task_ids", []) + [task_id]))
    state["active_task_ids"] = active_task_ids
    state["updated_at"] = utc_now()
    write_json_atomic(state_path, state)

    append_task_event(root, task_id, "task_promoted", f"Promoted intake {intake_id} to task {task_id}", correlation_id=intake_id, before_status="task_candidate", after_status="planning")
    append_workspace_event(root, "task_promoted", "task", task_id, f"Promoted intake {intake_id} to task {task_id}", correlation_id=intake_id, before_status="task_candidate", after_status="planning")
    intake_path = workspace_dir(root) / "intake" / f"{intake_id}.md"
    if intake_path.exists():
        text = intake_path.read_text(encoding="utf-8")
        text = text.replace("Status: clarifying", "Status: promoted")
        intake_path.write_text(text, encoding="utf-8")
    return {"task_id": task_id, "path": str(final_dir)}
```

- [ ] **Step 4: Run the full Python tests and verify they pass**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core -v`

Expected: PASS, 3 tests run.

- [ ] **Step 5: Commit if inside a git repository**

Run: `git rev-parse --is-inside-work-tree`

Expected in this workspace: FAIL because the current directory is not a git repository.

If running in a git repository, run:

```bash
git add .agent-workflow/scripts/workflow_core.py tests/agent_workflow/test_workflow_core.py
git commit -m "feat: promote intakes to workflow tasks"
```

---

### Task 3: Locks, Lifecycle Transitions, And Validation Revisions

**Files:**
- Modify: `.agent-workflow/scripts/workflow_core.py`
- Modify: `tests/agent_workflow/test_workflow_core.py`

- [ ] **Step 1: Add failing tests for locks and lifecycle transitions**

Append these test methods inside `WorkflowCoreTests` before the `if __name__ == "__main__"` block:

```python
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
```

- [ ] **Step 2: Run the new lifecycle test and verify it fails because functions are missing**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core.WorkflowCoreTests.test_lifecycle_and_validation_revision -v`

Expected: FAIL with missing imports for lifecycle functions.

- [ ] **Step 3: Implement locks, validation revisions, and lifecycle functions**

Append this code to `.agent-workflow/scripts/workflow_core.py`:

```python

def locks_path(root: Path) -> Path:
    return workspace_dir(root) / "locks.json"


def acquire_lock(root: Path, scope: str, entity_id: str, owner: str, purpose: str, ttl_seconds: int = 300) -> dict[str, Any]:
    ensure_workspace(root)
    path = locks_path(root)
    data = read_json(path)
    now = utc_now()
    for lock in data.get("locks", []):
        if lock["scope"] == scope and lock["entity_id"] == entity_id and lock["owner"] != owner:
            raise RuntimeError(f"Lock conflict for {scope}:{entity_id}")
    lock_id = f"lock_{scope}_{slugify(entity_id)}"
    data["locks"] = [lock for lock in data.get("locks", []) if lock["id"] != lock_id]
    lock = {
        "id": lock_id,
        "scope": scope,
        "entity_id": entity_id,
        "owner": owner,
        "purpose": purpose,
        "acquired_at": now,
        "expires_at": expires_at,
        "ttl_seconds": ttl_seconds,
    }
    data["locks"].append(lock)
    write_json_atomic(path, data)
    append_workspace_event(root, "lock_acquired", scope, entity_id, f"Acquired lock {lock_id}", actor=owner)
    return lock


def release_lock(root: Path, lock_id: str, owner: str) -> None:
    path = locks_path(root)
    data = read_json(path)
    kept = []
    released = None
    for lock in data.get("locks", []):
        if lock["id"] == lock_id:
            if lock["owner"] != owner:
                raise RuntimeError(f"Cannot release lock owned by {lock['owner']}")
            released = lock
        else:
            kept.append(lock)
    data["locks"] = kept
    write_json_atomic(path, data)
    if released:
        append_workspace_event(root, "lock_released", released["scope"], released["entity_id"], f"Released lock {lock_id}", actor=owner)


def task_path(root: Path, task_id: str) -> Path:
    return tasks_dir(root) / "active" / task_id


def update_task(root: Path, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    path = task_path(root, task_id) / "task.json"
    task = read_json(path)
    task.update(updates)
    task["updated_at"] = utc_now()
    write_json_atomic(path, task)
    return task


def create_validation_revision(root: Path, task_id: str, one_sentence: str, quick_check: list[str], effect_card: list[str]) -> dict[str, str]:
    output_dir = task_path(root, task_id) / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(output_dir.glob("validation-r*.md"))
    revision = f"r{len(existing) + 1:03d}"
    path = output_dir / f"validation-{revision}.md"
    quick = "\n".join(f"- {item}" for item in quick_check)
    card = "\n".join(f"{index}. {item}" for index, item in enumerate(effect_card, start=1))
    path.write_text(
        f"# Validation Revision {revision}\n\nStatus: approved\nApproved At: {utc_now()}\n\n## One-Sentence Intent\n{one_sentence}\n\n## Five-Point Quick Check\n{quick}\n\n## Effect Validation Card\n{card}\n",
        encoding="utf-8",
    )
    update_task(root, task_id, {"validation_revision": revision})
    append_task_event(root, task_id, "validation_revision_created", f"Created validation revision {revision}", after_status="planning")
    return {"revision": revision, "path": str(path)}


def start_execution(root: Path, task_id: str, subagents: list[str]) -> dict[str, Any]:
    package_dir = task_path(root, task_id)
    for required in ["context.md", "implement.md", "verify.md"]:
        if not (package_dir / required).exists():
            append_task_event(root, task_id, "execution_start_rejected", f"Missing {required}")
            raise FileNotFoundError(required)
    before = read_json(package_dir / "task.json")["status"]
    task = update_task(root, task_id, {"status": "executing", "current_step": "execute", "assigned_subagents": subagents})
    append_task_event(root, task_id, "execution_started", f"Started execution for {task_id}", before_status=before, after_status="executing")
    state_path = workspace_dir(root) / "state.json"
    state = read_json(state_path)
    state["active_task_ids"] = list(dict.fromkeys(state.get("active_task_ids", []) + [task_id]))
    state["updated_at"] = utc_now()
    write_json_atomic(state_path, state)
    return task


def complete_verification(root: Path, task_id: str, result: str, summary: str) -> dict[str, Any]:
    if result not in {"passed", "failed", "blocked"}:
        raise ValueError("result must be passed, failed, or blocked")
    before = read_json(task_path(root, task_id) / "task.json")["status"]
    after = {"passed": "done", "failed": "changes_requested", "blocked": "blocked"}[result]
    task = update_task(root, task_id, {"status": after, "verification_status": result})
    outputs_dir = task_path(root, task_id) / "outputs"
    outputs_dir.mkdir(exist_ok=True)
    verification_path = outputs_dir / f"verification-{task.get('validation_revision') or 'unversioned'}.md"
    verification_path.write_text(f"# Verification Result\n\nResult: {result}\n\nSummary: {summary}\n", encoding="utf-8")
    append_task_event(root, task_id, "verification_completed", summary, before_status=before, after_status=after)
    return task
```

- [ ] **Step 4: Run the full Python tests and verify they pass**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core -v`

Expected: PASS, 5 tests run.

- [ ] **Step 5: Commit if inside a git repository**

Run: `git rev-parse --is-inside-work-tree`

Expected in this workspace: FAIL because the current directory is not a git repository.

If running in a git repository, run:

```bash
git add .agent-workflow/scripts/workflow_core.py tests/agent_workflow/test_workflow_core.py
git commit -m "feat: add workflow lifecycle controls"
```

---

### Task 4: CLI Wrapper For Workflow Scripts

**Files:**
- Create: `.agent-workflow/scripts/task.py`
- Modify: `tests/agent_workflow/test_workflow_core.py`

- [ ] **Step 1: Add a failing CLI smoke test**

Append this test method inside `WorkflowCoreTests` before the `if __name__ == "__main__"` block:

```python
    def test_cli_create_intake(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = REPO_ROOT / ".agent-workflow" / "scripts" / "task.py"
            result = subprocess.run(
                [sys.executable, str(script), "create-intake", "Agent workflow", "Build workflow", "--session", "session-main", "--root", str(root)],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("intake_id", result.stdout)
            state = read_json(root / ".agent-workflow" / "workspace" / "state.json")
            self.assertIsNotNone(state["current_intake_id"])
```

- [ ] **Step 2: Run the CLI smoke test and verify it fails because `task.py` does not exist**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core.WorkflowCoreTests.test_cli_create_intake -v`

Expected: FAIL with an error that `.agent-workflow/scripts/task.py` cannot be opened.

- [ ] **Step 3: Implement the CLI wrapper**

Create `.agent-workflow/scripts/task.py` with this content:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from workflow_core import create_intake, promote_to_task


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent workflow task tools")
    parser.add_argument("--root", default=".", help="Workspace root")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-intake", help="Create a workspace intake note")
    create.add_argument("title")
    create.add_argument("raw_request")
    create.add_argument("--session", default="main")

    promote = sub.add_parser("promote", help="Promote an intake to a formal task")
    promote.add_argument("intake_id")
    promote.add_argument("title")
    promote.add_argument("goal")
    promote.add_argument("--type", default="design")
    promote.add_argument("--acceptance", action="append", default=[])
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    if args.command == "create-intake":
        result = create_intake(root, args.title, args.raw_request, args.session)
    elif args.command == "promote":
        criteria = args.acceptance or ["The formal task package exists and can be executed."]
        result = promote_to_task(root, args.intake_id, args.title, args.goal, args.type, criteria)
    else:
        raise RuntimeError(f"Unsupported command: {args.command}")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the full Python tests and verify they pass**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core -v`

Expected: PASS, 6 tests run.

- [ ] **Step 5: Commit if inside a git repository**

Run: `git rev-parse --is-inside-work-tree`

Expected in this workspace: FAIL because the current directory is not a git repository.

If running in a git repository, run:

```bash
git add .agent-workflow/scripts/task.py tests/agent_workflow/test_workflow_core.py
git commit -m "feat: add workflow task cli"
```

---

### Task 5: OpenCode Plugin Helpers And Subagent Context Injection

**Files:**
- Create: `.opencode/plugins/agent-workflow-lib.js`
- Create: `.opencode/plugins/agent-workflow-session-start.js`
- Create: `.opencode/plugins/agent-workflow-state.js`
- Create: `.opencode/plugins/agent-workflow-subagent-context.js`
- Create: `tests/agent_workflow/test_opencode_plugins.mjs`

- [ ] **Step 1: Write failing Node tests for plugin helper behavior**

Create `tests/agent_workflow/test_opencode_plugins.mjs` with this content:

```javascript
import assert from "node:assert/strict"
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"

import { buildWorkflowBreadcrumb, getActiveTask, readTaskContext } from "../../.opencode/plugins/agent-workflow-lib.js"

test("getActiveTask reads current task from workspace state", () => {
  const root = mkdtempSync(join(tmpdir(), "agent-workflow-"))
  mkdirSync(join(root, ".agent-workflow", "workspace"), { recursive: true })
  writeFileSync(join(root, ".agent-workflow", "workspace", "state.json"), JSON.stringify({ schema_version: "1.0", current_task_id: "task-a" }))
  assert.equal(getActiveTask(root), "task-a")
})

test("buildWorkflowBreadcrumb hides internal details", () => {
  const text = buildWorkflowBreadcrumb({ taskId: "task-a", status: "planning" })
  assert.match(text, /formal work item/)
  assert.doesNotMatch(text, /repo_map/)
  assert.doesNotMatch(text, /JSONL/)
})

test("readTaskContext combines context and implement brief", () => {
  const root = mkdtempSync(join(tmpdir(), "agent-workflow-"))
  const taskDir = join(root, ".agent-workflow", "tasks", "active", "task-a")
  mkdirSync(taskDir, { recursive: true })
  writeFileSync(join(taskDir, "context.md"), "# Context\nGoal")
  writeFileSync(join(taskDir, "implement.md"), "# Implement\nBuild")
  writeFileSync(join(taskDir, "verify.md"), "# Verify\nCheck")
  const context = readTaskContext(root, "task-a", "workflow-implement")
  assert.match(context, /# Context/)
  assert.match(context, /# Implement/)
  assert.doesNotMatch(context, /# Verify/)
})
```

- [ ] **Step 2: Run the Node tests and verify they fail because plugin helper is missing**

Run: `node --test tests/agent_workflow/test_opencode_plugins.mjs`

Expected: FAIL with module not found for `.opencode/plugins/agent-workflow-lib.js`.

- [ ] **Step 3: Implement the shared plugin helper**

Create `.opencode/plugins/agent-workflow-lib.js` with this content:

```javascript
import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"

export const workflowRoot = (directory) => join(directory, ".agent-workflow")

export const readJson = (path) => JSON.parse(readFileSync(path, "utf8"))

export const readTextIfExists = (path) => existsSync(path) ? readFileSync(path, "utf8") : ""

export const getActiveTask = (directory) => {
  const statePath = join(workflowRoot(directory), "workspace", "state.json")
  if (!existsSync(statePath)) return null
  const state = readJson(statePath)
  return state.current_task_id || null
}

export const readTaskJson = (directory, taskId) => {
  const path = join(workflowRoot(directory), "tasks", "active", taskId, "task.json")
  return existsSync(path) ? readJson(path) : null
}

export const buildWorkflowBreadcrumb = ({ taskId, status }) => {
  if (!taskId) {
    return "<workflow-state>\nNo formal work item is active. Clarify the user's need before suggesting a formal work item.\n</workflow-state>"
  }
  return `<workflow-state>\nFormal work item: ${taskId}\nStatus: ${status}\nNext: keep the user-facing conversation focused on goals, expected behavior, tradeoffs, and approval.\n</workflow-state>`
}

export const readTaskContext = (directory, taskId, agentName) => {
  const taskDir = join(workflowRoot(directory), "tasks", "active", taskId)
  const parts = []
  const context = readTextIfExists(join(taskDir, "context.md"))
  if (context) parts.push(context)
  const decisions = readTextIfExists(join(taskDir, "decisions.md"))
  if (decisions) parts.push(decisions)
  if (agentName === "workflow-implement") {
    const implement = readTextIfExists(join(taskDir, "implement.md"))
    if (implement) parts.push(implement)
  }
  if (agentName === "workflow-check") {
    const verify = readTextIfExists(join(taskDir, "verify.md"))
    if (verify) parts.push(verify)
  }
  return parts.join("\n\n---\n\n")
}
```

- [ ] **Step 4: Implement the three OpenCode plugins**

Create `.opencode/plugins/agent-workflow-session-start.js` with this content:

```javascript
import { existsSync } from "node:fs"
import { join } from "node:path"
import { buildWorkflowBreadcrumb, getActiveTask, readTaskJson, workflowRoot } from "./agent-workflow-lib.js"

export default async ({ directory }) => {
  return {
    "chat.message": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      if (input?.agent && String(input.agent).startsWith("workflow-")) return
      const taskId = getActiveTask(directory)
      const task = taskId ? readTaskJson(directory, taskId) : null
      const breadcrumb = buildWorkflowBreadcrumb({ taskId, status: task?.status || "none" })
      const rulesPath = join(workflowRoot(directory), "global", "rules.md")
      const rules = existsSync(rulesPath) ? `\n\n${breadcrumb}` : breadcrumb
      const parts = output?.parts || []
      const textPart = parts.find((part) => part.type === "text")
      if (textPart) textPart.text = `${rules}\n\n${textPart.text || ""}`
      else parts.unshift({ type: "text", text: rules })
    },
  }
}
```

Create `.opencode/plugins/agent-workflow-state.js` with this content:

```javascript
import { existsSync } from "node:fs"
import { buildWorkflowBreadcrumb, getActiveTask, readTaskJson, workflowRoot } from "./agent-workflow-lib.js"

export default async ({ directory }) => {
  return {
    "chat.message": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      if (input?.agent && String(input.agent).startsWith("workflow-")) return
      const taskId = getActiveTask(directory)
      const task = taskId ? readTaskJson(directory, taskId) : null
      const breadcrumb = buildWorkflowBreadcrumb({ taskId, status: task?.status || "none" })
      const parts = output?.parts || []
      const textPart = parts.find((part) => part.type === "text")
      if (textPart) textPart.text = `${breadcrumb}\n\n${textPart.text || ""}`
      else parts.unshift({ type: "text", text: breadcrumb })
    },
  }
}
```

Create `.opencode/plugins/agent-workflow-subagent-context.js` with this content:

```javascript
import { existsSync } from "node:fs"
import { getActiveTask, readTaskContext, workflowRoot } from "./agent-workflow-lib.js"

const SUPPORTED = new Set(["workflow-research", "workflow-implement", "workflow-check", "workflow-docs"])

export default async ({ directory }) => {
  return {
    "tool.execute.before": async (input, output) => {
      if (!existsSync(workflowRoot(directory))) return
      if (String(input?.tool || "").toLowerCase() !== "task") return
      const args = output?.args
      if (!args || !SUPPORTED.has(args.subagent_type)) return
      const taskId = getActiveTask(directory)
      if (!taskId) return
      const context = readTaskContext(directory, taskId, args.subagent_type)
      if (!context) return
      args.prompt = `Active task: ${taskId}\n\n# Injected Workflow Context\n\n${context}\n\n---\n\n# Requested Work\n\n${args.prompt || ""}`
    },
  }
}
```

- [ ] **Step 5: Run the Node tests and verify they pass**

Run: `node --test tests/agent_workflow/test_opencode_plugins.mjs`

Expected: PASS, 3 tests run.

- [ ] **Step 6: Commit if inside a git repository**

Run: `git rev-parse --is-inside-work-tree`

Expected in this workspace: FAIL because the current directory is not a git repository.

If running in a git repository, run:

```bash
git add .opencode/plugins tests/agent_workflow/test_opencode_plugins.mjs
git commit -m "feat: add opencode workflow plugins"
```

---

### Task 6: Agent Definitions And Workspace Memory Files

**Files:**
- Create: `.opencode/agent/workflow-research.md`
- Create: `.opencode/agent/workflow-implement.md`
- Create: `.opencode/agent/workflow-check.md`
- Create: `.opencode/agent/workflow-docs.md`
- Create: `.agent-workflow/global/rules.md`
- Create: `.agent-workflow/workspace/preferences.md`
- Create: `.agent-workflow/workspace/decisions.md`
- Create: `.agent-workflow/workspace/deferred_options.md`
- Create: `.agent-workflow/workspace/facts.md`
- Create: `.agent-workflow/workspace/open_questions.md`

- [ ] **Step 1: Create OpenCode subagent definitions**

Create `.opencode/agent/workflow-research.md` with this content:

```markdown
---
description: Researches a focused workflow question and writes findings without changing code.
mode: subagent
permission:
  edit: deny
  bash: ask
---

You are the workflow research agent. Answer only the focused research request you were given. Use the injected task context and write concise findings. Do not modify code or workflow state. If the request needs implementation, report that it is outside your role.
```

Create `.opencode/agent/workflow-implement.md` with this content:

```markdown
---
description: Implements one scoped workflow task from injected context without committing.
mode: subagent
permission:
  edit: allow
  bash: ask
---

You are the workflow implement agent. Implement only the scoped task in the injected context. Do not expand scope, do not commit, and do not modify `.agent-workflow/workspace/` machine state directly. Report files changed, verification run, and any concerns.
```

Create `.opencode/agent/workflow-check.md` with this content:

```markdown
---
description: Verifies workflow changes against the task brief and fixes only low-risk local issues.
mode: subagent
permission:
  edit: allow
  bash: ask
---

You are the workflow check agent. Review changes against the injected verification brief, acceptance criteria, and active validation revision. You may fix low-risk local issues within scope. Do not introduce a new approach, expand the task, or commit. Report findings, fixes, and verification results.
```

Create `.opencode/agent/workflow-docs.md` with this content:

```markdown
---
description: Updates workflow documentation and durable notes without changing business code.
mode: subagent
permission:
  edit: allow
  bash: ask
---

You are the workflow docs agent. Update documentation, decisions, deferred options, or summaries as requested. Do not change application code. Keep durable decisions separate from task-local notes.
```

- [ ] **Step 2: Create workspace memory files**

Create `.agent-workflow/global/rules.md` with this content:

```markdown
# Agent Workflow Rules

- Clarify the user's need before exposing workflow mechanics.
- Advance one user-understandable topic per turn.
- Ask several related questions when the topic needs exploration.
- Record durable decisions and deferred options so important tradeoffs are not lost.
- Promote an intake to a formal work item only after the user confirms the direction.
- Subagents execute focused tasks from injected context and do not inherit full chat history.
- Scripts are the only write path for workflow machine state.
```

Create `.agent-workflow/workspace/preferences.md` with this content:

```markdown
# Preferences

## P001: User-centered clarification

Scope: workspace
Status: accepted

Prefer requirement clarification that focuses on the user's described outcome, expected behavior, anti-outcomes, and tradeoffs. Avoid exposing task package, repo map, context injection, or subagent mechanics unless the user is explicitly designing those mechanisms.
```

Create `.agent-workflow/workspace/decisions.md` with this content:

```markdown
# Decisions

## D001: OpenCode-first local workflow

Type: architecture
Scope: workspace
Status: accepted
Date: 2026-05-20
Source Task: none
Supersedes: none

Decision:
Build the first version as an OpenCode-first local framework.

Reason:
The first version should prove the workflow loop before adding multi-platform abstraction, installer polish, or migration machinery.
```

Create `.agent-workflow/workspace/deferred_options.md` with this content:

```markdown
# Deferred Options

## Deferred Option: Multi-platform protocol layer

Id: O001
Scope: workspace
Status: deferred
Chosen Instead: OpenCode-first local workflow
Reason: Validate the local workflow loop before abstracting platform adapters.
Risk: Later platform support will require an adapter layer.
Source Task: none
Revisit When:
- The OpenCode runtime is stable.
- The task package schema stops changing frequently.
- There is a concrete need for Claude, Codex, or another platform.
```

Create `.agent-workflow/workspace/facts.md` with this content:

```markdown
# Facts

- The initial workflow runtime targets OpenCode.
- The current design separates workspace intake from formal task lifecycle.
```

Create `.agent-workflow/workspace/open_questions.md` with this content:

```markdown
# Open Questions

No blocking workspace-level questions are open for the first implementation plan.
```

- [ ] **Step 3: Run syntax and smoke checks**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core -v`

Expected: PASS, 6 tests run.

Run: `node --test tests/agent_workflow/test_opencode_plugins.mjs`

Expected: PASS, 3 tests run.

- [ ] **Step 4: Commit if inside a git repository**

Run: `git rev-parse --is-inside-work-tree`

Expected in this workspace: FAIL because the current directory is not a git repository.

If running in a git repository, run:

```bash
git add .opencode/agent .agent-workflow/global .agent-workflow/workspace
git commit -m "feat: add workflow agents and memory files"
```

---

### Task 7: End-To-End Verification

**Files:**
- Modify: `tests/agent_workflow/test_workflow_core.py`

- [ ] **Step 1: Add an end-to-end workflow test**

Append this test method inside `WorkflowCoreTests` before the `if __name__ == "__main__"` block:

```python
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
```

- [ ] **Step 2: Run full verification commands**

Run: `python3 -m unittest tests.agent_workflow.test_workflow_core -v`

Expected: PASS, 7 tests run.

Run: `node --test tests/agent_workflow/test_opencode_plugins.mjs`

Expected: PASS, 3 tests run.

- [ ] **Step 3: Run a manual CLI smoke test in a temporary directory**

Run: `tmpdir=$(mktemp -d) && python3 .agent-workflow/scripts/task.py --root "$tmpdir" create-intake "Agent workflow" "Build workflow" --session session-main`

Expected: JSON output containing `intake_id` and `path`.

- [ ] **Step 4: Commit if inside a git repository**

Run: `git rev-parse --is-inside-work-tree`

Expected in this workspace: FAIL because the current directory is not a git repository.

If running in a git repository, run:

```bash
git add tests/agent_workflow/test_workflow_core.py
git commit -m "test: verify workflow runtime end to end"
```

---

## Self-Review Checklist

- Spec coverage: Tasks 1-4 implement file-backed intake, task promotion, lifecycle state, events, locks, and validation revisions.
- Spec coverage: Task 5 implements OpenCode runtime plugin boundaries and subagent context injection.
- Spec coverage: Task 6 implements subagent role files and workspace-level durable memory files.
- Spec coverage: Task 7 verifies the core happy path.
- No new third-party dependencies are introduced.
- Scripts remain the write path for workflow machine state.
- Plugins read state and inject context only.
- User-facing language stays separate from internal runtime contract.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-20-agent-workflow.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
