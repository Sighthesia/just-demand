from __future__ import annotations

import json
import re
import tempfile
import uuid
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


def task_event_path(root: Path, task_id: str) -> Path:
    return tasks_dir(root) / "active" / task_id / "events.jsonl"


def append_task_event(root: Path, task_id: str, event_type: str, summary: str, **extra: Any) -> dict[str, Any]:
    seq = next_event_seq(root)
    event = {
        "schema_version": SCHEMA_VERSION,
        "seq": seq,
        "id": f"evt_{seq:06d}",
        "type": event_type,
        "actor": extra.pop("actor", "main-agent"),
        "task_id": task_id,
        "correlation_id": extra.pop("correlation_id", None),
        "at": utc_now(),
        "before_status": extra.pop("before_status", None),
        "after_status": extra.pop("after_status", None),
        "summary": summary,
    }
    event.update(extra)
    events_path = task_event_path(root, task_id)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def default_task_json(
    task_id: str,
    intake_id: str,
    title: str,
    goal: str,
    task_type: str,
    acceptance_criteria: list[str],
) -> dict[str, Any]:
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


def promote_to_task(
    root: Path,
    intake_id: str,
    title: str,
    goal: str,
    task_type: str,
    acceptance_criteria: list[str],
) -> dict[str, str]:
    ensure_workspace(root)
    now = utc_now()

    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task_id = f"{date_prefix}-{slugify(title)}-task"

    task_data = default_task_json(task_id, intake_id, title, goal, task_type, acceptance_criteria)
    state_path = workspace_dir(root) / "state.json"
    state = read_json(state_path)

    task_data["last_event_seq"] = int(state.get("last_event_seq", 0))
    task_data["updated_at"] = now

    # Build task in a temp directory, then move into place atomically.
    active = tasks_dir(root) / "active"
    final_dir = active / task_id
    with tempfile.TemporaryDirectory(dir=active) as tmp:
        tmp_path = Path(tmp)
        write_json_atomic(tmp_path / "task.json", task_data)
        for name, content in {
            "context.md": "# Context\n\n",
            "decisions.md": "# Decisions\n\n",
            "open_questions.md": "# Open Questions\n\n",
            "implement.md": "# Implement\n\n",
            "verify.md": "# Verify\n\n",
        }.items():
            (tmp_path / name).write_text(content, encoding="utf-8")
        (tmp_path / "outputs").mkdir()
        (tmp_path / "research").mkdir()
        # events.jsonl starts empty
        (tmp_path / "events.jsonl").write_text("", encoding="utf-8")

        if final_dir.exists():
            raise FileExistsError(f"Task directory already exists: {final_dir}")
        tmp_path.rename(final_dir)

    # Append task-level event
    append_task_event(root, task_id, "task_promoted", f"Intake {intake_id} promoted to task {task_id}")

    # Update workspace state
    state["current_intake_id"] = None
    state["current_task_id"] = task_id
    active_ids = state.get("active_task_ids", [])
    if task_id not in active_ids:
        active_ids.append(task_id)
    state["active_task_ids"] = active_ids
    state["updated_at"] = now
    write_json_atomic(state_path, state)

    # Append workspace event
    append_workspace_event(
        root,
        "task_promoted",
        "task",
        task_id,
        f"Intake {intake_id} promoted to task {task_id}",
        after_status="planning",
    )

    # Update intake markdown status if it exists
    intake_md = workspace_dir(root) / "intake" / f"{intake_id}.md"
    if intake_md.is_file():
        lines = intake_md.read_text(encoding="utf-8").splitlines(keepends=True)
        lines = [
            line.replace("Status: clarifying", "Status: promoted", 1)
            if line.rstrip("\n") == "Status: clarifying"
            else line
            for line in lines
        ]
        intake_md.write_text("".join(lines), encoding="utf-8")

    return {"task_id": task_id, "path": str(final_dir)}


def create_intake(root: Path, title: str, raw_request: str, session_id: str) -> dict[str, str]:
    ensure_workspace(root)
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    intake_id = f"{date_prefix}-{slugify(title)}-intake"
    intake_path = workspace_dir(root) / "intake" / f"{intake_id}.md"
    now = utc_now()
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


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------


def locks_path(root: Path) -> Path:
    return workspace_dir(root) / "locks.json"


def acquire_lock(
    root: Path,
    scope: str,
    entity_id: str,
    owner: str,
    purpose: str,
    ttl_seconds: int = 300,
) -> dict[str, Any]:
    locks_file = locks_path(root)
    data = read_json(locks_file)
    now = datetime.now(timezone.utc)

    for existing in data.get("locks", []):
        if existing["scope"] == scope and existing["entity_id"] == entity_id:
            if existing["owner"] != owner:
                raise RuntimeError(
                    f"Lock already held: scope={scope} entity_id={entity_id} owner={existing['owner']}"
                )
            # Same owner re-acquiring: release first
            data["locks"] = [lk for lk in data["locks"] if lk["id"] != existing["id"]]
            break

    lock_id = f"lock-{uuid.uuid4().hex[:12]}"
    acquired_at = now.replace(microsecond=0).isoformat()
    expires_at = (now + timedelta(seconds=ttl_seconds)).replace(microsecond=0).isoformat()

    lock = {
        "id": lock_id,
        "scope": scope,
        "entity_id": entity_id,
        "owner": owner,
        "purpose": purpose,
        "acquired_at": acquired_at,
        "expires_at": expires_at,
    }
    data.setdefault("locks", []).append(lock)
    write_json_atomic(locks_file, data)
    return lock


def release_lock(root: Path, lock_id: str, owner: str) -> None:
    locks_file = locks_path(root)
    data = read_json(locks_file)
    target = None
    for lk in data.get("locks", []):
        if lk["id"] == lock_id:
            target = lk
            break

    if target is None:
        raise RuntimeError(f"Lock not found: {lock_id}")
    if target["owner"] != owner:
        raise RuntimeError(
            f"Cannot release lock owned by {target['owner']}: {lock_id}"
        )

    data["locks"] = [lk for lk in data["locks"] if lk["id"] != lock_id]
    write_json_atomic(locks_file, data)


# ---------------------------------------------------------------------------
# Task helpers
# ---------------------------------------------------------------------------


def task_path(root: Path, task_id: str) -> Path:
    return tasks_dir(root) / "active" / task_id


def update_task(root: Path, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    tpath = task_path(root, task_id) / "task.json"
    task = read_json(tpath)
    task.update(updates)
    task["updated_at"] = utc_now()
    write_json_atomic(tpath, task)
    return task


# ---------------------------------------------------------------------------
# Validation revision
# ---------------------------------------------------------------------------


def create_validation_revision(
    root: Path,
    task_id: str,
    one_sentence: str,
    quick_check: list[str],
    effect_card: list[str],
) -> dict[str, str]:
    tpath = task_path(root, task_id)
    task = read_json(tpath / "task.json")

    rev_num = int(task.get("validation_revision") or 0) + 1
    rev_tag = f"r{rev_num:03d}"

    outputs_dir = tpath / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Validation Revision {rev_tag}",
        "",
        f"Task: {task_id}",
        "",
        "## One Sentence",
        one_sentence,
        "",
        "## Quick Check",
    ]
    for item in quick_check:
        lines.append(f"- [ ] {item}")
    lines += ["", "## Effect Card"]
    for item in effect_card:
        lines.append(f"- {item}")
    lines.append("")

    rev_file = outputs_dir / f"validation-{rev_tag}.md"
    rev_file.write_text("\n".join(lines), encoding="utf-8")

    update_task(root, task_id, {"validation_revision": rev_tag})
    append_task_event(root, task_id, "validation_revision_created", f"Created validation revision {rev_tag}")

    return {"revision": rev_tag, "path": str(rev_file)}


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------


def start_execution(root: Path, task_id: str, subagents: list[str]) -> dict[str, Any]:
    tpath = task_path(root, task_id)
    required_files = ["context.md", "implement.md", "verify.md"]
    for name in required_files:
        if not (tpath / name).is_file():
            raise FileNotFoundError(f"Missing required file for execution: {name}")

    before_status = read_json(tpath / "task.json")["status"]

    updates = {
        "status": "executing",
        "current_step": "execute",
        "assigned_subagents": subagents,
    }

    task = update_task(root, task_id, updates)
    append_task_event(
        root,
        task_id,
        "execution_started",
        f"Execution started with subagents: {', '.join(subagents)}",
        before_status=before_status,
        after_status="executing",
    )
    append_workspace_event(
        root,
        "execution_started",
        "task",
        task_id,
        f"Execution started for {task_id}",
        before_status=before_status,
        after_status="executing",
    )
    return task


def complete_verification(
    root: Path,
    task_id: str,
    result: str,
    summary: str,
) -> dict[str, Any]:
    result_to_status = {
        "passed": "done",
        "failed": "changes_requested",
        "blocked": "blocked",
    }
    if result not in result_to_status:
        raise ValueError(f"Invalid verification result: {result}")

    # v1: allow convergence from executing, verifying, or changes_requested.
    # Check subagent may write back verification results directly.
    tpath = task_path(root, task_id)
    before_status = read_json(tpath / "task.json")["status"]
    new_status = result_to_status[result]

    task = update_task(
        root,
        task_id,
        {"status": new_status, "verification_status": result},
    )

    # Write verification output
    tdir = task_path(root, task_id)
    rev_tag = task.get("validation_revision", "unknown")
    outputs_dir = tdir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    vfile = outputs_dir / f"verification-{rev_tag}.md"
    lines = [
        f"# Verification: {result}",
        "",
        f"Task: {task_id}",
        f"Revision: {rev_tag}",
        f"Result: {result}",
        "",
        "## Summary",
        summary,
        "",
    ]
    vfile.write_text("\n".join(lines), encoding="utf-8")

    append_task_event(
        root,
        task_id,
        "verification_completed",
        f"Verification {result}: {summary}",
        before_status=before_status,
        after_status=new_status,
    )
    append_workspace_event(
        root,
        "verification_completed",
        "task",
        task_id,
        f"Verification {result} for {task_id}",
        before_status=before_status,
        after_status=new_status,
    )
    return task
