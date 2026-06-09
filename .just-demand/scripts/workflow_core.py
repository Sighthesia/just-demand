from __future__ import annotations

import json
import fcntl
import re
import shutil
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


SCHEMA_VERSION = "1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or "work-item"


def unique_readable_id(directories: list[Path], base_id: str, suffix: str = "") -> str:
    def _exists(candidate_id: str) -> bool:
        return any((directory / f"{candidate_id}{suffix}").exists() for directory in directories)

    if not _exists(base_id):
        return base_id
    for _ in range(100):
        candidate = f"{base_id}-{uuid.uuid4().hex[:6]}"
        if not _exists(candidate):
            return candidate
    raise RuntimeError(f"Could not generate unique id for {base_id}")


def workflow_dir(root: Path) -> Path:
    return root / ".just-demand"


def state_dir(root: Path) -> Path:
    return workflow_dir(root) / "state"


def knowledge_dir(root: Path) -> Path:
    return workflow_dir(root) / "knowledge"


def tasks_dir(root: Path) -> Path:
    return state_dir(root)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(encoded)
        temp_path = Path(handle.name)
    temp_path.replace(path)


@contextmanager
def workflow_mutation_lock(root: Path):
    lock_dir = state_dir(root)
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / ".mutation.lock"
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
        base / "state" / "intake",
        base / "state" / "sessions",
        base / "state" / "active",
        base / "state" / "archive",
        base / "knowledge",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    memory_files = {
        base / "knowledge" / "memory.md": "# Just Demand Memory\n\n## Decisions\n\n## Facts\n\n## Preferences\n\n## Deferred Options\n\n## Open Questions\n\n",
        base / "state" / "events.jsonl": "",
        base / "state" / "locks.json": json.dumps({"schema_version": SCHEMA_VERSION, "locks": []}, indent=2) + "\n",
    }
    for path, content in memory_files.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    state_path = base / "state" / "state.json"
    if not state_path.exists():
        write_json_atomic(state_path, default_workspace_state())


def next_event_seq(root: Path) -> int:
    with workflow_mutation_lock(root):
        state_path = state_dir(root) / "state.json"
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
    events_path = state_dir(root) / "events.jsonl"
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


VALID_TASK_STATUSES = frozenset({
    "planning",
    "executing",
    "verifying",
    "changes_requested",
    "blocked",
    "done",
    "paused",
    "tweaking",
    "debugging",
})
MARKABLE_TASK_STATUSES = VALID_TASK_STATUSES - {"done"}


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
        "clarification": {
            "current_understanding": "",
            "expected_behavior": "",
            "actual_behavior": "",
            "reproduction": "",
            "scope": "",
            "final_expected_effect": "",
            "approach_options": "",
            "chosen_approach": "",
            "final_implementation_plan": "",
            "validation": "",
            "approval": "",
            "blocking_questions": [],
            "non_blocking_questions": [],
        },
        "validation_revision": None,
        "verification_status": "not_started",
        "related_files": [],
        "context_sources": [],
        "decision_refs": [],
        "deferred_option_refs": [],
        "subtasks": [],
        "locks": [],
        "progress": None,
        "impact": [],
        "last_note": None,
        "last_event_seq": 0,
        "created_at": now,
        "updated_at": now,
    }


INTAKE_SECTION_ORDER = [
    "Raw Request",
    "Current Understanding",
    "Expected Outcome",
    "Expected Behavior",
    "Actual Behavior",
    "Reproduction",
    "Scope",
    "Anti-Outcome",
    "Final Expected Effect",
    "Approach Options",
    "Chosen Approach",
    "Final Implementation Plan",
    "Validation",
    "Approval",
    "Decisions",
    "Deferred Options",
    "Blocking Questions",
    "Non-Blocking Questions",
    "Open Questions",
]


def parse_markdown_sections(text: str) -> dict[str, str]:
    section_pattern = re.compile(r"^## (?P<name>.+)$", re.MULTILINE)
    matches = list(section_pattern.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group("name").strip()] = text[start:end].strip()
    return sections


def parse_question_block(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned or cleaned.lower() in {"none", "n/a", "na"}:
        return []
    questions: list[str] = []
    for line in cleaned.splitlines():
        item = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        if item:
            questions.append(item)
    return questions


def read_intake_sections(root: Path, intake_id: str) -> dict[str, str]:
    intake_md = state_dir(root) / "intake" / f"{intake_id}.md"
    if not intake_md.is_file():
        return {}
    return parse_markdown_sections(intake_md.read_text(encoding="utf-8"))


def intake_needs_bug_clarification(task_type: str, raw_request: str, sections: dict[str, str]) -> bool:
    bug_types = {"bug", "bugfix", "fix", "incident"}
    if task_type.strip().lower() in bug_types:
        return True
    if any(
        sections.get(name, "").strip()
        for name in ("Actual Behavior", "Reproduction")
    ):
        return True
    signal_text = "\n".join(
        [
            raw_request,
            sections.get("Current Understanding", ""),
        ]
    ).lower()
    strong_keywords = ["bug", "broken", "regression", "mismatch", "crash", "error", "fails", "failing"]
    if any(keyword in signal_text for keyword in strong_keywords):
        return True
    mismatch_patterns = [
        r"\bexpected\b.+\b(?:but|got|received)\b",
        r"\bgot\b.+\binstead\b",
        r"\bactual\b.+\bexpected\b",
    ]
    return any(re.search(pattern, signal_text) for pattern in mismatch_patterns)


def build_clarification_payload(root: Path, intake_id: str, task_type: str) -> dict[str, Any]:
    sections = read_intake_sections(root, intake_id)
    raw_request = sections.get("Raw Request", "")
    blocking_questions = parse_question_block(sections.get("Blocking Questions", ""))
    non_blocking_questions = parse_question_block(
        sections.get("Non-Blocking Questions", sections.get("Open Questions", ""))
    )
    return {
        "current_understanding": sections.get("Current Understanding", ""),
        "expected_behavior": sections.get("Expected Behavior", sections.get("Expected Outcome", "")),
        "actual_behavior": sections.get("Actual Behavior", ""),
        "reproduction": sections.get("Reproduction", ""),
        "scope": sections.get("Scope", ""),
        "final_expected_effect": sections.get("Final Expected Effect", ""),
        "approach_options": sections.get("Approach Options", ""),
        "chosen_approach": sections.get("Chosen Approach", ""),
        "final_implementation_plan": sections.get("Final Implementation Plan", ""),
        "validation": sections.get("Validation", ""),
        "approval": sections.get("Approval", ""),
        "blocking_questions": blocking_questions,
        "non_blocking_questions": non_blocking_questions,
        "needs_bug_clarification": intake_needs_bug_clarification(task_type, raw_request, sections),
    }


def intake_readiness_errors(root: Path, intake_id: str, task_type: str) -> list[str]:
    clarification = build_clarification_payload(root, intake_id, task_type)
    errors: list[str] = []
    if not clarification["scope"].strip():
        errors.append("Scope is required before promotion.")
    if clarification["needs_bug_clarification"]:
        if not clarification["expected_behavior"].strip():
            errors.append("Expected Behavior is required for bug or mismatch work before promotion.")
        if not clarification["actual_behavior"].strip():
            errors.append("Actual Behavior is required for bug or mismatch work before promotion.")
        if not clarification["reproduction"].strip():
            errors.append("Reproduction is required for bug or mismatch work before promotion.")
    # Hard gate for design and implementation tasks: final expected effect,
    # chosen approach, final implementation plan, and approval are required.
    design_impl_types = {"design", "implementation", "feature", "feat", "refactor", "architecture"}
    if task_type.strip().lower() in design_impl_types:
        if not clarification["final_expected_effect"].strip():
            errors.append("Final Expected Effect is required for design or implementation work before promotion.")
        if not clarification["chosen_approach"].strip():
            errors.append("Chosen Approach is required for design or implementation work before promotion.")
        if not clarification["final_implementation_plan"].strip():
            errors.append("Final Implementation Plan is required for design or implementation work before promotion.")
        if not clarification["approval"].strip():
            errors.append("Approval is required for design or implementation work before promotion.")
    if clarification["blocking_questions"]:
        errors.append("Blocking Questions must be cleared before promotion.")
    return errors


def render_open_questions_markdown(non_blocking_questions: list[str]) -> str:
    if not non_blocking_questions:
        return "# Open Questions\n\n"
    lines = ["# Open Questions", "", "## Remaining Open Questions", ""]
    lines.extend([f"- {question}" for question in non_blocking_questions])
    lines.append("")
    return "\n".join(lines)


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
    readiness_errors = intake_readiness_errors(root, intake_id, task_type)
    if readiness_errors:
        raise RuntimeError("Promotion blocked: " + " ".join(readiness_errors))

    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task_id = unique_readable_id(
        [tasks_dir(root) / "active", tasks_dir(root) / "archive"],
        f"{date_prefix}-{slugify(title)}-task",
    )

    task_data = default_task_json(task_id, intake_id, title, goal, task_type, acceptance_criteria)
    task_data["clarification"] = build_clarification_payload(root, intake_id, task_type)
    state_path = state_dir(root) / "state.json"
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
            "open_questions.md": render_open_questions_markdown(task_data["clarification"]["non_blocking_questions"]),
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
    with workflow_mutation_lock(root):
        state = read_json(state_path)
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
    intake_md = state_dir(root) / "intake" / f"{intake_id}.md"
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
    intake_id = unique_readable_id(
        [state_dir(root) / "intake"],
        f"{date_prefix}-{slugify(title)}-intake",
        suffix=".md",
    )
    intake_path = state_dir(root) / "intake" / f"{intake_id}.md"
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
                "## Expected Behavior",
                "",
                "## Actual Behavior",
                "",
                "## Reproduction",
                "",
                "## Scope",
                "",
                "## Anti-Outcome",
                "",
                "## Final Expected Effect",
                "",
                "## Approach Options",
                "",
                "## Chosen Approach",
                "",
                "## Final Implementation Plan",
                "",
                "## Validation",
                "",
                "## Approval",
                "",
                "## Decisions",
                "",
                "## Deferred Options",
                "",
                "## Blocking Questions",
                "",
                "## Non-Blocking Questions",
                "",
                "## Open Questions",
                "",
            ]
        ),
        encoding="utf-8",
    )

    state_path = state_dir(root) / "state.json"
    with workflow_mutation_lock(root):
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
    return state_dir(root) / "locks.json"


def acquire_lock(
    root: Path,
    scope: str,
    entity_id: str,
    owner: str,
    purpose: str,
    ttl_seconds: int = 300,
) -> dict[str, Any]:
    with workflow_mutation_lock(root):
        locks_file = locks_path(root)
        data = read_json(locks_file)
        now = datetime.now(timezone.utc)

        active_locks = []
        for existing in data.get("locks", []):
            expires_at = existing.get("expires_at")
            if expires_at:
                try:
                    if datetime.fromisoformat(expires_at) <= now:
                        continue
                except ValueError:
                    pass
            active_locks.append(existing)
        data["locks"] = active_locks

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
    with workflow_mutation_lock(root):
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


def list_unfinished_tasks(root: Path, verbose: bool = False) -> list[dict[str, Any]]:
    active_dir = tasks_dir(root) / "active"
    if not active_dir.exists():
        return []

    tasks = []
    for task_dir in sorted(active_dir.iterdir(), key=lambda path: path.name):
        if not task_dir.is_dir():
            continue
        task_json = task_dir / "task.json"
        if not task_json.is_file():
            continue
        task = read_json(task_json)
        if task.get("status") == "done":
            continue
        entry: dict[str, Any] = {
            "id": task.get("id", task_dir.name),
            "title": task.get("title", ""),
            "status": task.get("status", "unknown"),
            "progress": task.get("progress"),
            "impact": task.get("impact", []),
        }
        if verbose:
            entry["current_step"] = task.get("current_step", "")
            entry["path"] = str(task_dir)
        tasks.append(entry)
    return tasks


def select_task(root: Path, task_id: str) -> dict[str, Any]:
    ensure_workspace(root)
    tpath = task_path(root, task_id) / "task.json"
    if not tpath.is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    task = read_json(tpath)
    status = str(task.get("status") or "")
    if status == "done":
        raise RuntimeError(f"Cannot select task {task_id}: task is already done")

    state_path = state_dir(root) / "state.json"
    with workflow_mutation_lock(root):
        state = read_json(state_path)
        active_ids = state.get("active_task_ids", [])
        if task_id not in active_ids:
            active_ids.append(task_id)
        state["active_task_ids"] = active_ids
        state["current_intake_id"] = None
        state["current_task_id"] = task_id
        state["updated_at"] = utc_now()
        write_json_atomic(state_path, state)

    append_task_event(root, task_id, "task_selected", f"Selected task {task_id} as current task")
    append_workspace_event(root, "task_selected", "task", task_id, f"Selected task {task_id} as current task")
    return {"ok": True, "task_id": task_id, "status": status, "current_task_id": task_id}


def mark_task(
    root: Path,
    task_id: str,
    status: str,
    *,
    progress: int | None = None,
    impact: list[str] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Mark task status, progress, impact scope, and note.

    Returns a compact result dict for low-token CLI output.
    """
    if status not in MARKABLE_TASK_STATUSES:
        raise ValueError(
            f"Invalid mark status '{status}'. Valid: {', '.join(sorted(MARKABLE_TASK_STATUSES))}"
        )

    if progress is not None and (progress < 0 or progress > 100):
        raise ValueError(f"Progress must be 0-100, got {progress}")

    tpath = task_path(root, task_id) / "task.json"
    if not tpath.is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    task = read_json(tpath)
    before_status = task.get("status")

    updates: dict[str, Any] = {"status": status}
    if progress is not None:
        updates["progress"] = progress
    if impact is not None:
        updates["impact"] = impact
    if note is not None:
        updates["last_note"] = note

    task = update_task(root, task_id, updates)

    state_path = state_dir(root) / "state.json"
    with workflow_mutation_lock(root):
        state = read_json(state_path)
        if status in {"planning", "executing", "verifying", "changes_requested", "tweaking", "debugging"}:
            state["current_intake_id"] = None
            state["current_task_id"] = task_id
        elif status in {"paused", "blocked"} and state.get("current_task_id") == task_id:
            state["current_task_id"] = None
        state["updated_at"] = utc_now()
        write_json_atomic(state_path, state)

    summary_parts = [f"status={status}"]
    if progress is not None:
        summary_parts.append(f"progress={progress}")
    if impact:
        summary_parts.append(f"impact={','.join(impact)}")
    if note:
        summary_parts.append(f"note={note}")

    append_task_event(
        root,
        task_id,
        "task_marked",
        f"Marked: {' '.join(summary_parts)}",
        before_status=before_status,
        after_status=status,
    )
    append_workspace_event(
        root,
        "task_marked",
        "task",
        task_id,
        f"Marked {task_id}: {' '.join(summary_parts)}",
        before_status=before_status,
        after_status=status,
    )

    return {"ok": True, "id": task_id, "status": status, "progress": task.get("progress")}


def update_task(root: Path, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    with workflow_mutation_lock(root):
        tpath = task_path(root, task_id) / "task.json"
        task = read_json(tpath)
        task.update(updates)
        task["updated_at"] = utc_now()
        write_json_atomic(tpath, task)
        return task


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )


def _normalize_repo_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.endswith("/"):
        normalized = normalized[:-1]
    return normalized


def _parse_git_status_paths(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if len(line) < 4:
            continue
        candidate = line[3:].strip()
        if not candidate:
            continue
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1].strip()
        normalized = _normalize_repo_path(candidate)
        if normalized:
            paths.append(normalized)
    return paths


def _path_matches_scope(path: str, scope: str) -> bool:
    normalized_path = _normalize_repo_path(path)
    normalized_scope = _normalize_repo_path(scope)
    if not normalized_path or not normalized_scope:
        return False
    return normalized_path == normalized_scope or normalized_path.startswith(normalized_scope + "/")


def _is_disallowed_checkpoint_path(path: str) -> bool:
    normalized = _normalize_repo_path(path)
    if normalized.endswith(".pyc"):
        return True
    parts = normalized.split("/")
    if "__pycache__" in parts:
        return True
    # Internal workflow runtime state — churns on every operation, not meaningful checkpoints
    if normalized == ".just-demand":
        return True
    if normalized.startswith(".just-demand/state/") and normalized.endswith((".json", ".jsonl")):
        return True
    return normalized.startswith(".pytest_cache/") or normalized.startswith(".opencode/node_modules/")


def _checkpoint_commit_message(task: dict[str, Any]) -> str:
    task_type = str(task.get("type", "")).strip().lower()
    if task_type in {"bug", "bugfix", "fix", "incident"}:
        prefix = "fix"
    elif task_type in {"implementation", "feature", "feat"}:
        prefix = "feat"
    else:
        prefix = "chore"
    subject = slugify(str(task.get("title") or task.get("id") or "task")).replace("-", " ")
    return f"{prefix}: checkpoint {subject}"


def _record_checkpoint_commit_result(root: Path, task_id: str, result: dict[str, Any]) -> dict[str, Any]:
    stored = dict(result)
    stored["attempted_at"] = utc_now()
    update_task(root, task_id, {"checkpoint_commit": stored})

    if stored.get("created"):
        summary = f"Checkpoint commit created: {stored.get('commit_hash')} ({stored.get('message')})"
        event_type = "checkpoint_commit_created"
    else:
        summary = f"Checkpoint commit skipped: {stored.get('reason', 'unknown')}"
        event_type = "checkpoint_commit_skipped"

    append_task_event(root, task_id, event_type, summary)
    append_workspace_event(root, event_type, "task", task_id, summary)
    return stored


def create_checkpoint_commit(root: Path, task_id: str) -> dict[str, Any]:
    tpath = task_path(root, task_id) / "task.json"
    if not tpath.is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    task = read_json(tpath)

    repo_check = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if repo_check.returncode != 0 or repo_check.stdout.strip() != "true":
        return _record_checkpoint_commit_result(
            root,
            task_id,
            {"created": False, "reason": "not_git_repo", "paths": []},
        )

    status_result = _run_git(root, "status", "--short")
    if status_result.returncode != 0:
        return _record_checkpoint_commit_result(
            root,
            task_id,
            {"created": False, "reason": "git_status_failed", "paths": []},
        )

    all_changed = _parse_git_status_paths(status_result.stdout)
    impact_scope = [
        _normalize_repo_path(entry)
        for entry in task.get("impact", [])
        if isinstance(entry, str) and _normalize_repo_path(entry)
    ]

    if impact_scope:
        candidate_paths = [
            path
            for path in all_changed
            if any(_path_matches_scope(path, scope) for scope in impact_scope)
            and not _is_disallowed_checkpoint_path(path)
        ]
        fallback_note = None
    else:
        return _record_checkpoint_commit_result(
            root,
            task_id,
            {"created": False, "reason": "missing_impact_scope", "paths": []},
        )

    candidate_paths = list(dict.fromkeys(candidate_paths))
    if not candidate_paths:
        return _record_checkpoint_commit_result(
            root,
            task_id,
            {"created": False, "reason": "no_task_scoped_changes", "paths": []},
        )

    def _with_fallback(d: dict[str, Any]) -> dict[str, Any]:
        if fallback_note:
            d["fallback_note"] = fallback_note
        return d

    diff_result = _run_git(root, "diff", "--", *candidate_paths)
    if diff_result.returncode != 0:
        return _record_checkpoint_commit_result(
            root,
            task_id,
            _with_fallback({"created": False, "reason": "git_diff_failed", "paths": candidate_paths}),
        )

    log_result = _run_git(root, "log", "--oneline", "-10")
    if log_result.returncode != 0:
        return _record_checkpoint_commit_result(
            root,
            task_id,
            _with_fallback({"created": False, "reason": "git_log_failed", "paths": candidate_paths}),
        )

    add_result = _run_git(root, "add", "--", *candidate_paths)
    if add_result.returncode != 0:
        return _record_checkpoint_commit_result(
            root,
            task_id,
            _with_fallback({"created": False, "reason": "git_add_failed", "paths": candidate_paths}),
        )

    message = _checkpoint_commit_message(task)
    commit_result = _run_git(root, "commit", "-m", message, "--", *candidate_paths)
    if commit_result.returncode != 0:
        reason = "git_commit_failed"
        failure_output = "\n".join(part for part in [commit_result.stdout, commit_result.stderr] if part).lower()
        if "nothing to commit" in failure_output:
            reason = "no_task_scoped_changes"
        return _record_checkpoint_commit_result(
            root,
            task_id,
            _with_fallback({"created": False, "reason": reason, "message": message, "paths": candidate_paths}),
        )

    head_result = _run_git(root, "rev-parse", "HEAD")
    commit_hash = head_result.stdout.strip() if head_result.returncode == 0 else None
    return _record_checkpoint_commit_result(
        root,
        task_id,
        _with_fallback({
            "created": True,
            "reason": None,
            "commit_hash": commit_hash,
            "message": message,
            "paths": candidate_paths,
        }),
    )


def cleanup_completed_task(root: Path, task_id: str) -> dict[str, Any]:
    """Remove a completed task and clean up all runtime references.

    For archived tasks, this deletes the archived task package.
    For active tasks with status 'done', this deletes the active task package.
    """
    ensure_workspace(root)

    # Check if task is in archive first
    archive_dir = tasks_dir(root) / "archive"
    archive_task_dir = archive_dir / task_id
    active_dir = tasks_dir(root) / "active"
    active_task_dir = active_dir / task_id

    task_dir = None
    if archive_task_dir.is_dir():
        task_dir = archive_task_dir
    elif active_task_dir.is_dir():
        task_dir = active_task_dir
    else:
        raise FileNotFoundError(f"Task not found: {task_id}")

    task_json_path = task_dir / "task.json"
    if not task_json_path.is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    task_data = read_json(task_json_path)
    if task_data.get("status") != "done":
        raise RuntimeError(
            f"Cannot cleanup task {task_id}: status is '{task_data.get('status')}', expected 'done'"
        )

    # 1. Delete the entire task directory
    shutil.rmtree(task_dir)

    # 2. Remove from workspace state
    with workflow_mutation_lock(root):
        state_path = state_dir(root) / "state.json"
        state = read_json(state_path)

        active_ids = state.get("active_task_ids", [])
        if task_id in active_ids:
            active_ids.remove(task_id)
        state["active_task_ids"] = active_ids

        if state.get("current_task_id") == task_id:
            state["current_task_id"] = None

        # 3. Clear current_task_id in active_sessions
        for session in state.get("active_sessions", {}).values():
            if session.get("current_task_id") == task_id:
                session["current_task_id"] = None

        state["updated_at"] = utc_now()
        write_json_atomic(state_path, state)

        # 4. Remove locks where entity_id matches task_id
        locks_file = locks_path(root)
        locks_data = read_json(locks_file)
        locks_data["locks"] = [
            lk for lk in locks_data.get("locks", []) if lk.get("entity_id") != task_id
        ]
        write_json_atomic(locks_file, locks_data)

    # 5. Append workspace event
    append_workspace_event(
        root,
        "task_cleaned_up",
        "task",
        task_id,
        f"Cleaned up completed task {task_id}",
    )

    return {"task_id": task_id, "cleaned": True}


def _extract_task_decisions(root: Path, task_dir: Path) -> Optional[str]:
    """Extract meaningful decisions from task decisions.md.

    Returns the extracted content if there are actual decisions beyond the header,
    otherwise returns None.
    """
    decisions_path = task_dir / "decisions.md"
    if not decisions_path.is_file():
        return None

    content = decisions_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Skip header lines (# Decisions and blank lines after it)
    decision_lines = []
    header_passed = False
    for line in lines:
        if not header_passed:
            if line.startswith("# "):
                header_passed = True
                continue
            elif line.strip() == "":
                continue
            else:
                header_passed = True
        if header_passed:
            decision_lines.append(line)

    # Check if there's meaningful content (not just blank lines)
    meaningful_content = "\n".join(decision_lines).strip()
    if not meaningful_content:
        return None

    return meaningful_content


def _extract_task_facts(root: Path, task_dir: Path) -> Optional[str]:
    """Extract verification summary and task info as facts.

    Returns a formatted string suitable for knowledge memory.md,
    or None if there's nothing useful to extract.
    """
    task_json_path = task_dir / "task.json"
    if not task_json_path.is_file():
        return None

    task_data = read_json(task_json_path)
    task_id = task_data.get("id", "")
    title = task_data.get("title", "")
    verification_status = task_data.get("verification_status", "")
    status = task_data.get("status", "")

    # Find verification output file
    outputs_dir = task_dir / "outputs"
    verification_file = None
    if outputs_dir.is_dir():
        for f in outputs_dir.iterdir():
            if f.name.startswith("verification-") and f.name.endswith(".md"):
                verification_file = f
                break

    lines = []
    lines.append(f"- Task {task_id} ({title}) completed with status '{status}'.")

    if verification_file:
        # Read verification summary
        vcontent = verification_file.read_text(encoding="utf-8")
        summary = None
        in_summary = False
        for line in vcontent.splitlines():
            if line.startswith("## Summary"):
                in_summary = True
                continue
            if in_summary:
                if line.startswith("##") or line.strip() == "":
                    if summary:
                        break
                    continue
                summary = line.strip()
                break
        if summary:
            lines.append(f"  Verification summary: {summary}")

    return "\n".join(lines)


def archive_task(root: Path, task_id: str) -> dict[str, Any]:
    """Archive a completed task by moving it to state/archive/.

    This preserves the full task directory while removing it from active state.
    Durable decisions and facts are extracted to knowledge/memory.md before archival.
    """
    ensure_workspace(root)

    active_dir = tasks_dir(root) / "active"
    task_dir = active_dir / task_id
    task_json_path = task_dir / "task.json"

    if not task_json_path.is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    task_data = read_json(task_json_path)
    if task_data.get("status") != "done":
        raise RuntimeError(
            f"Cannot archive task {task_id}: status is '{task_data.get('status')}', expected 'done'"
        )

    archive_dir = tasks_dir(root) / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_task_dir = archive_dir / task_id
    if archive_task_dir.exists():
        raise FileExistsError(f"Archive destination already exists: {archive_task_dir}")

    # 1. Extract durable knowledge before moving
    extraction_errors = []

    # Extract decisions
    try:
        decisions_content = _extract_task_decisions(root, task_dir)
        if decisions_content:
            knowledge_memory = knowledge_dir(root) / "memory.md"
            with knowledge_memory.open("a", encoding="utf-8") as f:
                f.write(f"\n\n### From Task: {task_id}\n\n{decisions_content}\n")
    except Exception as e:
        extraction_errors.append(f"decisions extraction failed: {e}")

    # Extract facts
    try:
        facts_content = _extract_task_facts(root, task_dir)
        if facts_content:
            knowledge_memory = knowledge_dir(root) / "memory.md"
            with knowledge_memory.open("a", encoding="utf-8") as f:
                f.write(f"\n{facts_content}\n")
    except Exception as e:
        extraction_errors.append(f"facts extraction failed: {e}")

    # 2. Move task directory to archive
    try:
        shutil.move(str(task_dir), str(archive_task_dir))
    except Exception as e:
        # If move fails, report error but keep task in active state
        raise RuntimeError(f"Failed to archive task {task_id}: {e}")

    # 3. Update workspace state
    with workflow_mutation_lock(root):
        state_path = state_dir(root) / "state.json"
        state = read_json(state_path)

        active_ids = state.get("active_task_ids", [])
        if task_id in active_ids:
            active_ids.remove(task_id)
        state["active_task_ids"] = active_ids

        if state.get("current_task_id") == task_id:
            state["current_task_id"] = None

        # Clear current_task_id in active_sessions
        for session in state.get("active_sessions", {}).values():
            if session.get("current_task_id") == task_id:
                session["current_task_id"] = None

        state["updated_at"] = utc_now()
        write_json_atomic(state_path, state)

        # 4. Remove locks where entity_id matches task_id
        locks_file = locks_path(root)
        locks_data = read_json(locks_file)
        locks_data["locks"] = [
            lk for lk in locks_data.get("locks", []) if lk.get("entity_id") != task_id
        ]
        write_json_atomic(locks_file, locks_data)

    # 5. Append workspace event
    append_workspace_event(
        root,
        "task_archived",
        "task",
        task_id,
        f"Archived completed task {task_id}",
    )

    result = {"task_id": task_id, "archived": True, "archive_path": str(archive_task_dir)}
    if extraction_errors:
        result["extraction_warnings"] = extraction_errors

    return result


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

    state_path = state_dir(root) / "state.json"
    with workflow_mutation_lock(root):
        state = read_json(state_path)
        state["current_intake_id"] = None
        state["current_task_id"] = task_id
        state["updated_at"] = utc_now()
        write_json_atomic(state_path, state)

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
    auto_archive: bool = True,
    checkpoint_commit: bool = True,
) -> dict[str, Any]:
    """Complete verification for a task.

    When result='passed' and auto_archive=True, the task is automatically archived.
    """
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
    allowed_before_statuses = {"executing", "verifying", "changes_requested", "debugging", "tweaking"}
    if before_status not in allowed_before_statuses:
        raise RuntimeError(
            f"Cannot complete verification for task {task_id}: status is '{before_status}', "
            f"expected one of {', '.join(sorted(allowed_before_statuses))}"
        )
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

    checkpoint_result = None
    if result == "passed" and checkpoint_commit:
        checkpoint_result = create_checkpoint_commit(root, task_id)

    # Auto-archive when verification passes
    archive_result = None
    archive_error = None
    if result == "passed" and auto_archive:
        try:
            archive_result = archive_task(root, task_id)
        except Exception as e:
            archive_error = str(e)
            # If archival fails, task stays active but verification is still recorded
            append_workspace_event(
                root,
                "task_archive_failed",
                "task",
                task_id,
                f"Failed to archive task {task_id}: {e}",
            )

    result_data = task
    if checkpoint_result is not None:
        result_data["checkpoint_commit"] = checkpoint_result
    if archive_result:
        result_data["archived"] = True
        result_data["archive_path"] = archive_result.get("archive_path")
        if "extraction_warnings" in archive_result:
            result_data["extraction_warnings"] = archive_result["extraction_warnings"]
    else:
        result_data["archived"] = False
        if archive_error:
            result_data["archive_error"] = archive_error

    return result_data
