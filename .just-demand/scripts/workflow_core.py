from __future__ import annotations

import json
import fcntl
import re
import shutil
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


SCHEMA_VERSION = "1.0"

# ---------------------------------------------------------------------------
# TaskContract v2 — single semantic fact source for task context.
#
# Version scheme:
#   TASK_RECORD_VERSION  — task.json envelope format ("2.0" for contract tasks)
#   TASK_CONTRACT_VERSION — contract schema inside the "contract" field
#   PROJECTION_VERSION    — rendered role-view format
# ---------------------------------------------------------------------------
TASK_RECORD_VERSION_V2 = "2.0"
TASK_CONTRACT_VERSION = "1.1"
PROJECTION_VERSION = "1.0"

# Contract field names that form the shared semantic core.
CONTRACT_SHARED_FIELDS = frozenset({
    "goal",
    "acceptance_criteria",
    "scope",
    "out_of_scope",
    "invariants",
    "anti_outcomes",
    "decisions",
    "open_questions",
})

# Contract field names that describe engineering / execution context.
CONTRACT_ENGINEERING_FIELDS = frozenset({
    "code_map",
    "risks",
    "verification_cases",
    "work_items",
    "dependencies",
})

# All known contract fields.
CONTRACT_ALL_FIELDS = CONTRACT_SHARED_FIELDS | CONTRACT_ENGINEERING_FIELDS

MATERIAL_AUTHORIZATION_FIELDS = frozenset({
    "scope",
    "out_of_scope",
    "invariants",
    "anti_outcomes",
    "final_expected_effect",
    "chosen_approach",
    "decisions",
    "acceptance_criteria",
})

# Role-to-required-projection-files mapping.
ROLE_PROJECTION_FILES: dict[str, list[str]] = {
    "advisor":    ["context.md"],
    "researcher": ["research.md"],
    "coder":      ["context.md", "implement.md"],
    "tester":     ["context.md", "verify.md"],
}

# Mapping from intake section heading -> contract field name.
# Same semantics as MARKDOWN_TO_CLARIFICATION_FIELD but for v2.
INTAKE_TO_CONTRACT_FIELD: dict[str, str] = {
    "Goal": "goal",
    "Raw Request": "raw_request",
    "Current Understanding": "current_understanding",
    "Expected Outcome": "expected_outcome",
    "Scope": "scope",
    "Out Of Scope": "out_of_scope",
    "Anti-Outcomes": "anti_outcomes",
    "Decisions": "decisions",
    "Open Questions": "open_questions",
    "Final Expected Effect": "final_expected_effect",
    "Chosen Approach": "chosen_approach",
    "Final Implementation Plan": "final_implementation_plan",
    "Approach Options": "approach_options",
    "Validation": "validation",
    "Approval": "approval",
    "Blocking Questions": "blocking_questions",
    "Non-Blocking Questions": "non_blocking_questions",
}

# ---------------------------------------------------------------------------
# Contract helpers
# ---------------------------------------------------------------------------


def empty_contract() -> dict[str, Any]:
    """Return a blank v2 task contract."""
    return {
        "contract_version": TASK_CONTRACT_VERSION,
        "contract_revision": 1,
        "authorization": {
            "status": "pending",
            "scope": "task",
            "approved_at": "",
            "approved_by": "",
            "approved_revision": 0,
            "source": "",
        },
        "provenance": {
            "raw_request": "",
            "intake_id": "",
            "approved_at": "",
        },
        "outcome": {
            "goal": "",
            "acceptance_criteria": [],
            "final_expected_effect": "",
        },
        "boundaries": {
            "scope": "",
            "out_of_scope": "",
            "invariants": "",
            "anti_outcomes": "",
        },
        "decisions": [],
        "blocking_questions": [],
        "open_questions": [],
        "engineering": {
            "code_map": "",
            "risks": "",
            "verification_cases": [],
            "work_items": [],
            "dependencies": [],
            "expected_behavior": "",
            "actual_behavior": "",
            "reproduction": "",
        },
        "choices": {
            "chosen_approach": "",
            "final_implementation_plan": "",
            "approach_options": "",
            "approval": "",
        },
    }


def _safe_str(value: Any) -> str:
    return str(value).strip() if value else ""


def _safe_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip() for line in value.strip().splitlines() if line.strip()]
    return []


def contract_authorization_is_valid(contract: dict[str, Any]) -> bool:
    """Return whether the user authorization covers the current contract revision."""
    authorization = contract.get("authorization")
    if not isinstance(authorization, dict):
        return (
            str(contract.get("contract_version", "1.0")) < TASK_CONTRACT_VERSION
            and bool(_safe_str(contract.get("choices", {}).get("approval", "")))
        )
    revision = int(contract.get("contract_revision", 1) or 1)
    return (
        authorization.get("status") == "approved"
        and int(authorization.get("approved_revision", 0) or 0) == revision
    )


def load_task_contract(task: dict[str, Any]) -> dict[str, Any]:
    """Load the semantic contract from a task record.

    v2 tasks have a top-level ``contract`` dict.
    v1 tasks are adapted from the legacy ``clarification`` / ``goal`` /
    ``acceptance_criteria`` fields — the adapter is read-only and does not
    mutate the stored task data.
    """
    task_record_version = str(task.get("schema_version", "1.0"))
    if task_record_version >= "2.0" and "contract" in task:
        return task["contract"]

    # v1 adapter — build a best-effort contract from legacy fields.
    # Preserves original values faithfully (no fallback chaining) so that
    # readiness checks detect genuinely missing fields.
    clarification = task.get("clarification", {}) or {}
    goal = _safe_str(task.get("goal", ""))
    acceptance = _safe_list(task.get("acceptance_criteria", []))
    scope = _safe_str(clarification.get("scope", ""))
    anti_outcomes = _safe_str(clarification.get("anti_outcomes", ""))
    final_expected_effect = _safe_str(clarification.get("final_expected_effect", ""))
    chosen_approach = _safe_str(clarification.get("chosen_approach", ""))
    impl_plan = _safe_str(clarification.get("final_implementation_plan", ""))
    approach_options = _safe_str(clarification.get("approach_options", ""))
    approval = _safe_str(clarification.get("approval", ""))
    blocking = _safe_list(clarification.get("blocking_questions", []))
    non_blocking = _safe_list(clarification.get("non_blocking_questions", []))
    raw_req = _safe_str(clarification.get("raw_request", ""))
    current_understanding = _safe_str(clarification.get("current_understanding", ""))

    # Collect decisions from intake if possible
    decisions: list[str] = _safe_list(clarification.get("decisions", []))

    return {
        "contract_version": TASK_CONTRACT_VERSION,
        "contract_revision": 1,
        "authorization": {
            "status": "approved" if approval else "pending",
            "scope": "task",
            "approved_at": "",
            "approved_by": "user" if approval else "",
            "approved_revision": 1 if approval else 0,
            "source": "legacy_approval" if approval else "",
        },
        "provenance": {
            "raw_request": raw_req,
            "intake_id": _safe_str(task.get("source_intake_id", "")),
            "approved_at": "",
        },
        "outcome": {
            "goal": goal,
            "acceptance_criteria": acceptance,
            "final_expected_effect": final_expected_effect,
        },
        "boundaries": {
            "scope": scope,
            "out_of_scope": "",
            "invariants": "",
            "anti_outcomes": anti_outcomes,
        },
        "decisions": decisions,
        "blocking_questions": blocking,
        "open_questions": non_blocking,
        "engineering": {
            "code_map": "",
            "risks": "",
            "verification_cases": [],
            "work_items": [],
            "dependencies": [],
            "expected_behavior": _safe_str(clarification.get("expected_behavior", "")),
            "actual_behavior": _safe_str(clarification.get("actual_behavior", "")),
            "reproduction": _safe_str(clarification.get("reproduction", "")),
        },
        "choices": {
            "chosen_approach": chosen_approach,
            "final_implementation_plan": impl_plan,
            "approach_options": approach_options,
            "approval": approval,
        },
    }


def contract_readiness_errors(contract: dict[str, Any], task_type: str) -> list[str]:
    """Check whether a contract has all required fields for execution readiness.

    Returns a list of error messages (empty = ready).
    Mirrors legacy ``intake_readiness_errors`` and ``task_is_ready_for_execution``.
    """
    errors: list[str] = []
    boundaries = contract.get("boundaries", {}) or {}
    outcome = contract.get("outcome", {}) or {}
    choices = contract.get("choices", {}) or {}
    provenance = contract.get("provenance", {}) or {}
    engineering = contract.get("engineering", {}) or {}

    if not _safe_str(boundaries.get("scope", "")):
        errors.append("Scope is required before execution.")

    blocking = contract.get("blocking_questions", contract.get("open_questions", []))
    if isinstance(blocking, list) and len(blocking) > 0:
        errors.append("Blocking questions must be cleared before execution.")

    design_impl_types = {"design", "implementation", "feature", "feat", "refactor", "architecture"}
    bug_fix_types = {"bug", "bugfix", "fix", "incident"}
    task_type_lower = task_type.strip().lower()

    if task_type_lower in bug_fix_types:
        if not _safe_str(engineering.get("expected_behavior", "")):
            errors.append("Expected Behavior is required for bug or mismatch work.")
        if not _safe_str(engineering.get("actual_behavior", "")):
            errors.append("Actual Behavior is required for bug or mismatch work.")
        if not _safe_str(engineering.get("reproduction", "")):
            errors.append("Reproduction is required for bug or mismatch work.")

    if task_type_lower in design_impl_types:
        if not _safe_str(outcome.get("final_expected_effect", "")):
            errors.append("Final Expected Effect is required for design or implementation work.")
        if not _safe_str(choices.get("chosen_approach", "")):
            errors.append("Chosen Approach is required for design or implementation work.")
        if not _safe_str(choices.get("final_implementation_plan", "")):
            errors.append("Final Implementation Plan is required for design or implementation work.")
        if not _safe_str(choices.get("approval", "")):
            errors.append("Approval is required for design or implementation work.")

    return errors


def intake_readiness_errors(root: Path, intake_id: str, task_type: str) -> list[str]:
    """Compatibility wrapper for tests and direct callers.

    Reads the intake file and returns readiness errors via the new
    contract-based function.
    """
    clarification = build_clarification_payload(root, intake_id, task_type)
    temp_task = {
        "schema_version": SCHEMA_VERSION,
        "type": task_type,
        "goal": "",
        "acceptance_criteria": [],
        "clarification": clarification,
    }
    contract = load_task_contract(temp_task)
    return contract_readiness_errors(contract, task_type)


# ---------------------------------------------------------------------------
# Dual-access helpers (v1/v2 transparent)
# ---------------------------------------------------------------------------


def _task_is_v2(task: dict[str, Any]) -> bool:
    """Return True if the task record uses v2 contract format."""
    return str(task.get("schema_version", "1.0")) >= "2.0" and "contract" in task


def _task_goal(task: dict[str, Any]) -> str:
    """Read task goal from contract (v2) or top-level (v1)."""
    if _task_is_v2(task):
        return _safe_str(task.get("contract", {}).get("outcome", {}).get("goal", ""))
    return _safe_str(task.get("goal", ""))


def _task_acceptance(task: dict[str, Any]) -> list[str]:
    """Read acceptance criteria from contract (v2) or top-level (v1)."""
    if _task_is_v2(task):
        return _safe_list(task.get("contract", {}).get("outcome", {}).get("acceptance_criteria", []))
    return _safe_list(task.get("acceptance_criteria", []))


def _task_clarification(task: dict[str, Any]) -> dict[str, Any]:
    """Read clarification dict from contract (v2) or top-level (v1).

    For v2 tasks, this maps the structured contract back to flat
    clarification-style field names so callers work transparently.
    """
    if _task_is_v2(task):
        contract = task.get("contract", {}) or {}
        eng = contract.get("engineering", {}) or {}
        choices = contract.get("choices", {}) or {}
        outcome = contract.get("outcome", {}) or {}
        boundaries = contract.get("boundaries", {}) or {}
        extra = contract.get("_extra", {}) or {}
        # Read lifecycle fields from canonical location (engineering.lifecycle)
        # with fallback to _extra for backward-compatible migration.
        lifecycle = eng.get("lifecycle", {}) or {}
        result = {
            "scope": _safe_str(boundaries.get("scope", "")),
            "anti_outcomes": _safe_str(boundaries.get("anti_outcomes", "")),
            "raw_request": _safe_str(contract.get("provenance", {}).get("raw_request", "")),
            "final_expected_effect": _safe_str(outcome.get("final_expected_effect", "")),
            "chosen_approach": _safe_str(choices.get("chosen_approach", "")),
            "final_implementation_plan": _safe_str(choices.get("final_implementation_plan", "")),
            "approach_options": _safe_str(choices.get("approach_options", "")),
            "approval": _safe_str(choices.get("approval", "")),
            "blocking_questions": _safe_list(contract.get("blocking_questions", [])),
            "non_blocking_questions": _safe_list(contract.get("open_questions", [])),
            "expected_behavior": _safe_str(eng.get("expected_behavior", "")),
            "actual_behavior": _safe_str(eng.get("actual_behavior", "")),
            "reproduction": _safe_str(eng.get("reproduction", "")),
            "decisions": _safe_list(contract.get("decisions", [])),
            "code_map": _safe_str(eng.get("code_map", "")),
            "verification_cases": _safe_list(eng.get("verification_cases", [])),
            # Visible-effect lifecycle fields: canonical location, then _extra fallback
            "opening": _safe_str(lifecycle.get("opening", extra.get("opening", ""))),
            "during_transition": _safe_str(lifecycle.get("during_transition", extra.get("during_transition", ""))),
            "after_open": _safe_str(lifecycle.get("after_open", extra.get("after_open", ""))),
            "interrupt_behavior": _safe_str(lifecycle.get("interrupt_behavior", extra.get("interrupt_behavior", ""))),
        }
        return result
    return dict(task.get("clarification", {}) or {})


# ---------------------------------------------------------------------------
# v1 → v2 migration
# ---------------------------------------------------------------------------


def migrate_task_v1_to_v2(root: Path, task_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Migrate a single active v1 task to v2 contract format.

    The migration is idempotent — v2 tasks are silently skipped, v1 tasks
    receive a ``contract`` field and are updated to ``schema_version = "2.0"``.
    The original v1 fields (``goal``, ``acceptance_criteria``, ``clarification``)
    are kept for backward-compatible reads but are no longer the authoritative
    semantic source.

    Archive tasks are always refused — use ``find_task_json_path`` to verify
    the task is active before calling this function.

    Args:
        root: Project root.
        task_id: Active task id (must be in active/ directory).
        dry_run: When True, report what would change without writing.

    Returns:
        Dict with task_id, migrated (bool), status, and any warnings.

    Raises:
        FileNotFoundError: Task not found or not active.
        RuntimeError: Task is in archive or has non-migratable status.
    """
    ensure_workspace(root)
    active_dir = tasks_dir(root) / "active"
    task_dir = active_dir / task_id
    task_json_path = task_dir / "task.json"

    if not task_json_path.is_file():
        raise FileNotFoundError(f"Active task not found: {task_id}")

    task = read_json(task_json_path)

    # Already v2 — idempotent skip
    if _task_is_v2(task):
        return {"task_id": task_id, "migrated": False, "status": "already_v2"}

    # Refuse done tasks that should be archived instead
    status = str(task.get("status") or "").strip().lower()
    if status == "done":
        raise RuntimeError(f"Task {task_id} is 'done' — archive it before migration (or use --force to override)")

    # Build contract from existing v1 fields.
    contract = load_task_contract(task)

    # Build the updated v2 record.
    task["schema_version"] = TASK_RECORD_VERSION_V2
    task["contract"] = contract
    # Preserve original fields for backward compat but mark them secondary.

    warnings: list[str] = []
    # Detect gaps in the v1 source data
    eng = contract.get("engineering", {}) or {}
    if not _safe_str(eng.get("code_map", "")):
        warnings.append("No code_map — coder will lack file-level guidance.")
    if not _safe_list(eng.get("verification_cases", [])):
        warnings.append("No verification_cases — tester will lack specific checks.")

    if dry_run:
        return {
            "task_id": task_id,
            "migrated": True,
            "status": "dry_run",
            "warnings": warnings,
            "contract_version": TASK_CONTRACT_VERSION,
        }

    # Write the updated task record atomically.
    write_json_atomic(task_json_path, task)

    # Regenerate projections from the new contract.
    (task_dir / "context.md").write_text(render_context_markdown(task), encoding="utf-8")
    (task_dir / "research.md").write_text(render_research_markdown(task), encoding="utf-8")
    (task_dir / "implement.md").write_text(render_implementation_plan_markdown(task), encoding="utf-8")
    (task_dir / "verify.md").write_text(render_verify_markdown(task), encoding="utf-8")

    append_task_event(
        root, task_id, "task_migrated",
        f"Migrated v1→v2 contract (schema_version={TASK_RECORD_VERSION_V2})",
    )

    return {
        "task_id": task_id,
        "migrated": True,
        "status": "migrated",
        "warnings": warnings,
        "contract_version": TASK_CONTRACT_VERSION,
    }


def migrate_v1_tasks(root: Path, task_ids: list[str] | None = None, *, dry_run: bool = False) -> dict[str, Any]:
    """Batch-migrate active v1 tasks to v2 contract format.

    Args:
        root: Project root.
        task_ids: Optional list of task IDs to migrate. If None or empty,
            all active v1 tasks are migrated.
        dry_run: When True, report what would change without writing.

    Returns:
        Dict with:
          - migrated: list of migrated task summaries
          - skipped: list of skipped task summaries (already v2, not found, etc.)
          - errors: list of error dicts with task_id and error message
          - total_count: int
          - dry_run: bool
    """
    ensure_workspace(root)
    active_dir = tasks_dir(root) / "active"
    if not active_dir.is_dir():
        return {"migrated": [], "skipped": [], "errors": [], "total_count": 0, "dry_run": dry_run}

    # Resolve task IDs if not provided or empty list
    if not task_ids:
        task_ids = sorted(
            d.name for d in active_dir.iterdir()
            if d.is_dir() and (d / "task.json").is_file()
        )

    migrated_list: list[dict[str, Any]] = []
    skipped_list: list[dict[str, Any]] = []
    errors_list: list[dict[str, Any]] = []

    for tid in task_ids:
        try:
            result = migrate_task_v1_to_v2(root, tid, dry_run=dry_run)
            if result.get("migrated") and result.get("status") in ("migrated", "dry_run"):
                migrated_list.append(result)
            else:
                skipped_list.append(result)
        except (FileNotFoundError, RuntimeError) as exc:
            errors_list.append({"task_id": tid, "error": str(exc)})

    return {
        "migrated": migrated_list,
        "skipped": skipped_list,
        "errors": errors_list,
        "total_count": len(task_ids),
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Code-map readiness
# ---------------------------------------------------------------------------


def code_map_readiness_errors(contract: dict[str, Any]) -> list[str]:
    """Check whether a code-dependent task has a usable code map."""
    eng = contract.get("engineering", {}) or {}
    code_map = _safe_str(eng.get("code_map", ""))
    if not code_map:
        return ["Code map is empty — coder will not have file-level guidance."]
    return []


def verification_readiness_errors(contract: dict[str, Any]) -> list[str]:
    """Check whether verification cases are available."""
    eng = contract.get("engineering", {}) or {}
    cases = _safe_list(eng.get("verification_cases", []))
    if not cases:
        return ["No verification cases defined — tester cannot verify against specific checks."]
    return []


# ---------------------------------------------------------------------------
# Deterministic role projections
# ---------------------------------------------------------------------------


def _render_provenance_block(provenance: dict[str, Any]) -> str:
    lines = []
    raw = _safe_str(provenance.get("raw_request", ""))
    if raw:
        lines += ["## User Raw Request", "", raw, ""]
    intake_id = _safe_str(provenance.get("intake_id", ""))
    if intake_id:
        lines += ["**Source intake:** " + intake_id]
    return "\n".join(lines)


def _render_outcome_block(outcome: dict[str, Any]) -> str:
    lines = []
    goal = _safe_str(outcome.get("goal", ""))
    if goal:
        lines += ["## Goal", "", goal, ""]
    effect = _safe_str(outcome.get("final_expected_effect", ""))
    if effect:
        lines += ["## User Expected Effect", "", effect, ""]
    acceptance = _safe_list(outcome.get("acceptance_criteria", []))
    if acceptance:
        lines += ["## Acceptance Criteria", ""]
        for c in acceptance:
            lines.append(f"- {c}")
        lines.append("")
    return "\n".join(lines)


def _render_boundaries_block(boundaries: dict[str, Any]) -> str:
    lines = []
    scope = _safe_str(boundaries.get("scope", ""))
    if scope:
        lines += ["## Scope", "", scope, ""]
    oos = _safe_str(boundaries.get("out_of_scope", ""))
    if oos:
        lines += ["## Out Of Scope", "", oos, ""]
    invariants = _safe_str(boundaries.get("invariants", ""))
    if invariants:
        lines += ["## Invariants", "", invariants, ""]
    anti = _safe_str(boundaries.get("anti_outcomes", ""))
    if anti:
        lines += ["## Anti-Outcomes", "", anti, ""]
    return "\n".join(lines)


def _render_decisions_block(decisions: list[str]) -> str:
    if not decisions:
        return ""
    lines = ["## Decisions", ""]
    for d in decisions:
        lines.append(f"- {_safe_str(d)}")
    lines.append("")
    return "\n".join(lines)


def _render_open_questions_block(questions: list[str]) -> str:
    if not questions:
        return ""
    lines = ["## Remaining Open Questions", ""]
    for q in questions:
        lines.append(f"- {_safe_str(q)}")
    lines.append("")
    return "\n".join(lines)


def _render_engineering_block(eng: dict[str, Any], *, include_code_map: bool = True, include_verification: bool = True) -> str:
    lines = []
    code_map = _safe_str(eng.get("code_map", ""))
    if include_code_map and code_map:
        lines += ["## Code Map", "", code_map, ""]

    # Visible-effect lifecycle fields (render for coder and advisor; tester sees them implicitly)
    lifecycle = eng.get("lifecycle", {}) or {}
    opening = _safe_str(lifecycle.get("opening", ""))
    during_transition = _safe_str(lifecycle.get("during_transition", ""))
    after_open = _safe_str(lifecycle.get("after_open", ""))
    interrupt_behavior = _safe_str(lifecycle.get("interrupt_behavior", ""))
    if opening or during_transition or after_open or interrupt_behavior:
        lines += ["## Visible Effect Lifecycle", ""]
        if opening:
            lines += ["- **Opening:** " + opening, ""]
        if during_transition:
            lines += ["- **During Transition:** " + during_transition, ""]
        if after_open:
            lines += ["- **After Open:** " + after_open, ""]
        if interrupt_behavior:
            lines += ["- **Interrupt Behavior:** " + interrupt_behavior, ""]

    # Bug/mismatch fields
    expected = _safe_str(eng.get("expected_behavior", ""))
    if expected:
        lines += ["## Expected Behavior", "", expected, ""]
    actual = _safe_str(eng.get("actual_behavior", ""))
    if actual:
        lines += ["## Actual Behavior", "", actual, ""]
    reproduction = _safe_str(eng.get("reproduction", ""))
    if reproduction:
        lines += ["## Reproduction", "", reproduction, ""]

    risks = _safe_str(eng.get("risks", ""))
    if risks:
        lines += ["## Known Risks", "", risks, ""]
    work_items = _safe_list(eng.get("work_items", []))
    if work_items:
        lines += ["## Work Items", ""]
        for item in work_items:
            lines.append(f"- {item}")
        lines.append("")
    deps = _safe_list(eng.get("dependencies", []))
    if deps:
        lines += ["## Dependencies", ""]
        for d in deps:
            lines.append(f"- {d}")
        lines.append("")
    cases = _safe_list(eng.get("verification_cases", []))
    if include_verification and cases:
        lines += ["## Verification Cases", ""]
        for case in cases:
            lines.append(f"- [ ] {case}")
        lines.append("")
    return "\n".join(lines)


def _render_choices_block(choices: dict[str, Any]) -> str:
    lines = []
    approach = _safe_str(choices.get("chosen_approach", ""))
    if approach:
        lines += ["## Chosen Approach", "", approach, ""]
    plan = _safe_str(choices.get("final_implementation_plan", ""))
    if plan:
        lines += ["## Implementation Plan", "", plan, ""]
    options = _safe_str(choices.get("approach_options", ""))
    if options:
        lines += ["## Approach Options", "", options, ""]
    approval = _safe_str(choices.get("approval", ""))
    if approval:
        lines += ["## Approval", "", approval, ""]
    return "\n".join(lines)


def render_contract_projection(contract: dict[str, Any], role: str, task: dict[str, Any] | None = None) -> str:
    """Render the contract as a deterministic markdown view for the given role.

    ``role`` is one of ``advisor``, ``researcher``, ``coder``, ``tester``.
    Returns a self-contained markdown string.
    """
    provenance = contract.get("provenance", {}) or {}
    outcome = contract.get("outcome", {}) or {}
    boundaries = contract.get("boundaries", {}) or {}
    decisions = _safe_list(contract.get("decisions", []))
    open_questions = _safe_list(contract.get("open_questions", []))
    engineering = contract.get("engineering", {}) or {}
    choices = contract.get("choices", {}) or {}

    parts = ["# Context\n"]

    # Provenance -> only advisor/researcher see raw request
    if role in ("advisor", "researcher"):
        prov = _render_provenance_block(provenance)
        if prov:
            parts.append(prov)

    # Outcome -> everyone sees goal and acceptance
    parts.append(_render_outcome_block(outcome))

    # Boundaries -> everyone sees scope and anti-outcomes
    parts.append(_render_boundaries_block(boundaries))

    # Decisions -> advisor/researcher see decisions
    if role in ("advisor", "researcher"):
        parts.append(_render_decisions_block(decisions))

    # Open questions -> advisor (all), others (only non-empty)
    if role == "advisor":
        parts.append(_render_open_questions_block(open_questions))

    # Engineering context
    include_code_map = role in ("coder",)
    include_verification = role in ("tester",)
    parts.append(_render_engineering_block(engineering, include_code_map=include_code_map, include_verification=include_verification))

    # Choices
    if role in ("coder", "advisor"):
        parts.append(_render_choices_block(choices))

    result = "\n".join(part for part in parts if part.strip())
    return result


def render_context_markdown(task: dict[str, Any]) -> str:
    """Render context.md for a task (advisor role view)."""
    return render_contract_projection(load_task_contract(task), "advisor", task)


def render_research_markdown(task: dict[str, Any]) -> str:
    """Render research.md for a task (researcher role view)."""
    contract = load_task_contract(task)
    outcome = contract.get("outcome", {}) or {}
    boundaries = contract.get("boundaries", {}) or {}

    parts = [
        "# Research Context\n",
        "## Goal\n",
        _safe_str(outcome.get("goal", "")) or "_No goal recorded._",
        "",
        "## Scope\n",
        _safe_str(boundaries.get("scope", "")) or "_No scope recorded._",
        "",
        "## Open Questions\n",
    ]
    open_qs = _safe_list(contract.get("open_questions", []))
    if open_qs:
        for q in open_qs:
            parts.append(f"- {q}")
    else:
        parts.append("_No open questions._")
    parts.append("")

    engineering = contract.get("engineering", {}) or {}
    code_map = _safe_str(engineering.get("code_map", ""))
    if code_map:
        parts += ["## Code Map", "", code_map, ""]

    return "\n".join(parts)


def render_implementation_plan_markdown(task: dict[str, Any], subtasks: list[dict[str, Any]] | None = None) -> str:
    """Render implement.md for a task (coder role view)."""
    contract = load_task_contract(task)
    outcome = contract.get("outcome", {}) or {}
    boundaries = contract.get("boundaries", {}) or {}
    choices = contract.get("choices", {}) or {}
    engineering = contract.get("engineering", {}) or {}

    plan_text = _safe_str(choices.get("final_implementation_plan", ""))
    goal = _safe_str(outcome.get("goal", ""))
    scope = _safe_str(boundaries.get("scope", ""))
    anti = _safe_str(boundaries.get("anti_outcomes", ""))
    code_map = _safe_str(engineering.get("code_map", ""))
    chosen_approach = _safe_str(choices.get("chosen_approach", ""))

    if subtasks is None:
        subtasks = task.get("subtasks", []) or build_implementation_plan_subtasks(plan_text)

    lines = [
        "# Implement",
        "",
        "## Goal",
        "",
        goal or "_No goal recorded._",
        "",
        "## Scope",
        "",
        scope or "_No scope recorded._",
        "",
        "## Anti-Outcomes",
        "",
        anti or "_No anti-outcomes recorded._",
        "",
    ]
    if chosen_approach:
        lines += ["## Chosen Approach", "", chosen_approach, ""]
    if code_map:
        lines += ["## Code Map", "", code_map, ""]
    lines += [
        "## Implementation Plan",
        "",
        plan_text or "_No implementation plan recorded._",
        "",
        "## Ordered Todo",
        "",
    ]
    if subtasks:
        for sub in subtasks:
            status = str(sub.get("status", "todo") or "todo").strip().lower()
            marker = "x" if status == "done" else " "
            lines.append(f"- [{marker}] {sub.get('title', '').strip()}")
    else:
        lines.append("- [ ] No ordered steps captured yet.")
    lines.append("")
    return "\n".join(lines)


def render_verify_markdown(task: dict[str, Any]) -> str:
    """Render verify.md for a task (tester role view)."""
    contract = load_task_contract(task)
    outcome = contract.get("outcome", {}) or {}
    boundaries = contract.get("boundaries", {}) or {}
    engineering = contract.get("engineering", {}) or {}

    effect = _safe_str(outcome.get("final_expected_effect", ""))
    scope = _safe_str(boundaries.get("scope", ""))
    anti = _safe_str(boundaries.get("anti_outcomes", ""))
    cases = _safe_list(engineering.get("verification_cases", []))
    risks = _safe_str(engineering.get("risks", ""))

    lines = [
        "# Verify",
        "",
        "## Expected Effect",
        "",
        effect or "_No expected effect recorded._",
        "",
        "## Scope",
        "",
        scope or "_No scope recorded._",
        "",
    ]
    if anti:
        lines += ["## Anti-Outcomes", "", anti, ""]
    if cases:
        lines += ["## Verification Cases", ""]
        for case in cases:
            lines.append(f"- [ ] {case}")
        lines.append("")
    if risks:
        lines += ["## Known Risks", "", risks, ""]
    return "\n".join(lines)


PLAN_STEP_PATTERN = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(?P<title>.+?)\s*$")


def extract_ordered_plan_steps(plan_text: str) -> list[str]:
    text = str(plan_text or "")
    steps: list[str] = []
    for line in text.splitlines():
        match = PLAN_STEP_PATTERN.match(line)
        if match:
            title = match.group("title").strip()
            if title:
                steps.append(title)

    if steps:
        return steps

    fallback = [line.strip() for line in text.splitlines() if line.strip()]
    if fallback:
        return fallback

    stripped = text.strip()
    return [stripped] if stripped else []


def _render_open_questions_simple(questions: list[str]) -> str:
    """Render a simple open-questions markdown block."""
    if not questions:
        return "# Open Questions\n\n"
    lines = ["# Open Questions", "", "## Remaining Open Questions", ""]
    lines.extend(f"- {q}" for q in questions)
    lines.append("")
    return "\n".join(lines)


def build_implementation_plan_subtasks(plan_text: str) -> list[dict[str, Any]]:
    """Build ordered subtask list from implementation plan text."""
    steps = extract_ordered_plan_steps(plan_text)
    return [
        {
            "id": f"plan-step-{order}",
            "order": order,
            "title": title,
            "status": "todo",
        }
        for order, title in enumerate(steps, start=1)
    ]


# ---------------------------------------------------------------------------
# Packet-lint — structured validation of a task packet.
# ---------------------------------------------------------------------------


def lint_task_packet(task: dict[str, Any], role: str | None = None) -> list[dict[str, str]]:
    """Run structured lint checks on a task packet.

    Returns a list of warning dicts with keys:
      - field: dotted path to the field
      - severity: "error" or "warning"
      - message: human-readable description
    """
    warnings: list[dict[str, str]] = []
    contract = load_task_contract(task)
    task_type = _safe_str(task.get("type", ""))
    eng = contract.get("engineering", {}) or {}
    provenance = contract.get("provenance", {}) or {}
    outcome = contract.get("outcome", {}) or {}
    boundaries = contract.get("boundaries", {}) or {}
    choices = contract.get("choices", {}) or {}

    # Envelope-level checks
    if not task.get("id"):
        warnings.append({"field": "id", "severity": "error", "message": "Task has no id."})
    if not task_type:
        warnings.append({"field": "type", "severity": "error", "message": "Task has no type."})

    # Provenance
    if not _safe_str(provenance.get("raw_request", "")):
        warnings.append({"field": "contract.provenance.raw_request", "severity": "warning", "message": "No raw request recorded."})

    # Outcome
    if not _safe_str(outcome.get("goal", "")):
        warnings.append({"field": "contract.outcome.goal", "severity": "warning", "message": "Goal is empty."})

    # Boundaries
    if not _safe_str(boundaries.get("scope", "")):
        warnings.append({"field": "contract.boundaries.scope", "severity": "error", "message": "Scope is required."})

    # Engineering
    if not _safe_str(eng.get("code_map", "")):
        warnings.append({"field": "contract.engineering.code_map", "severity": "warning", "message": "Code map is empty."})
    if not _safe_list(eng.get("verification_cases", [])):
        warnings.append({"field": "contract.engineering.verification_cases", "severity": "warning", "message": "No verification cases defined."})

    # Choices for design/implementation
    design_types = {"design", "implementation", "feature", "feat", "refactor", "architecture"}
    if task_type.lower() in design_types:
        if not _safe_str(choices.get("final_implementation_plan", "")):
            warnings.append({"field": "contract.choices.final_implementation_plan", "severity": "error", "message": "Implementation plan is required for design/implementation tasks."})
        if not _safe_str(choices.get("chosen_approach", "")):
            warnings.append({"field": "contract.choices.chosen_approach", "severity": "error", "message": "Chosen approach is required for design/implementation tasks."})
        if not _safe_str(choices.get("approval", "")):
            warnings.append({"field": "contract.choices.approval", "severity": "error", "message": "Approval is required for design/implementation tasks."})

    # Role-filtered warnings
    if role == "coder" and not _safe_str(eng.get("code_map", "")):
        warnings.append({"field": "contract.engineering.code_map", "severity": "warning", "message": "Coder will lack file-level guidance without a code map."})
    if role == "tester" and not _safe_list(eng.get("verification_cases", [])):
        warnings.append({"field": "contract.engineering.verification_cases", "severity": "warning", "message": "Tester will lack verification targets without verification cases."})

    return warnings


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


def normalize_task_id(value: Any) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    return None


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
        base / "state" / "plans",
        base / "knowledge",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    for path, content in {
        base / "state" / "events.jsonl": "",
        base / "state" / "locks.json": json.dumps({"schema_version": SCHEMA_VERSION, "locks": []}, indent=2) + "\n",
    }.items():
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


# ---------------------------------------------------------------------------
# v2 contract builder from intake
# ---------------------------------------------------------------------------


def build_contract_from_intake(
    root: Path,
    intake_id: str,
    title: str,
    goal: str,
    task_type: str,
    acceptance_criteria: list[str],
) -> dict[str, Any]:
    """Build a v2 TaskContract by reading an intake markdown file.

    Returns the ``contract`` dict ready to be stored in a v2 task record.
    All fields are populated from intake sections; missing sections yield
    empty defaults (not placeholders).
    """
    sections = read_intake_sections(root, intake_id)
    raw_request = sections.get("Raw Request", "")
    blocking_questions = parse_question_block(sections.get("Blocking Questions", ""))
    non_blocking_questions = parse_question_block(
        sections.get("Non-Blocking Questions", sections.get("Open Questions", ""))
    )
    decisions_raw = parse_question_block(sections.get("Decisions", "")) or []
    # Handle Anti-Outcome / Anti-Outcomes alias
    anti_outcomes = sections.get("Anti-Outcomes", "") or sections.get("Anti-Outcome", "")
    expected_behavior = sections.get("Expected Behavior", sections.get("Expected Outcome", ""))
    actual_behavior = sections.get("Actual Behavior", "")
    reproduction = sections.get("Reproduction", "")
    current_understanding = sections.get("Current Understanding", "")
    final_expected_effect = sections.get("Final Expected Effect", "")
    approach_options = sections.get("Approach Options", "")
    chosen_approach = sections.get("Chosen Approach", "")
    impl_plan = sections.get("Final Implementation Plan", "")
    validation = sections.get("Validation", "")
    approval = sections.get("Approval", "")
    scope = sections.get("Scope", "")
    out_of_scope = sections.get("Out Of Scope", "")
    invariants = sections.get("Invariants", "")

    # Collect extra fields (clarification fields not mapped to contract paths)
    extra: dict[str, Any] = {}
    extra_fields = {
        "current_understanding": sections.get("Current Understanding", current_understanding),
        "decision_card": sections.get("Decision Card", ""),
        "user_action": sections.get("User Action", ""),
        "recommended_default": sections.get("Recommended Default", ""),
        "option_matrix": sections.get("Option Matrix", ""),
        "minimum_viable_knowledge": sections.get("Minimum Viable Knowledge", ""),
        "validation_card": sections.get("Validation Card", ""),
        "diagram": sections.get("Diagram", ""),
        "confidence": sections.get("Confidence", ""),
        "escalation_reason": sections.get("Escalation Reason", ""),
        "validation": sections.get("Validation", validation),
        "needs_bug_clarification": intake_needs_bug_clarification(task_type, raw_request, sections),
    }
    for ek, ev in extra_fields.items():
        if ev or ek in {"needs_bug_clarification"}:
            extra[ek] = ev

    contract: dict[str, Any] = {
        "contract_version": TASK_CONTRACT_VERSION,
        "contract_revision": 1,
        "authorization": {
            "status": "approved" if approval else "pending",
            "scope": "task",
            "approved_at": utc_now() if approval else "",
            "approved_by": "user" if approval else "",
            "approved_revision": 1 if approval else 0,
            "source": "explicit_user_approval" if approval else "",
        },
        "provenance": {
            "raw_request": raw_request,
            "intake_id": intake_id,
            "approved_at": "",
        },
        "outcome": {
            "goal": goal,
            "acceptance_criteria": acceptance_criteria,
            "final_expected_effect": final_expected_effect,
        },
        "boundaries": {
            "scope": scope,
            "out_of_scope": out_of_scope,
            "invariants": invariants,
            "anti_outcomes": anti_outcomes,
        },
        "decisions": decisions_raw,
        "blocking_questions": blocking_questions,
        "open_questions": non_blocking_questions,
        "engineering": {
            "code_map": "",
            "risks": "",
            "verification_cases": [],
            "work_items": [],
            "dependencies": [],
            "expected_behavior": expected_behavior,
            "actual_behavior": actual_behavior,
            "reproduction": reproduction,
        },
        "choices": {
            "chosen_approach": chosen_approach,
            "final_implementation_plan": impl_plan,
            "approach_options": approach_options,
            "approval": approval,
        },
    }
    if extra:
        contract["_extra"] = extra
    return contract


def default_task_json_v2(
    task_id: str,
    intake_id: str,
    title: str,
    task_type: str,
    contract: dict[str, Any],
    *,
    parent_task_id: str | None = None,
    root_task_id: str | None = None,
    lineage_task_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Create a v2 task record with a ``contract`` field.

    No top-level ``goal``, ``acceptance_criteria``, or ``clarification``
    fields — the contract is the single semantic source.
    """
    now = utc_now()
    return {
        "schema_version": TASK_RECORD_VERSION_V2,
        "id": task_id,
        "source_intake_id": intake_id,
        "parent_task_id": parent_task_id,
        "root_task_id": root_task_id or task_id,
        "lineage_task_ids": list(lineage_task_ids or []),
        "title": title,
        "type": task_type,
        "status": "planning",
        "current_step": "clarify",
        "owner_session": "main",
        "assigned_subagents": [],
        "subagent_routing": "main-agent-default",
        "contract": contract,
        "constraints": [],
        "validation_revision": None,
        "verification_status": "not_started",
        "related_files": [],
        "context_sources": [],
        "decision_refs": [],
        "deferred_option_refs": [],
        "subtasks": [],
        "plan_id": None,
        "locks": [],
        "progress": None,
        "impact": [],
        "checkpoint_pass_completed": False,
        "last_note": None,
        "last_event_seq": 0,
        "created_at": now,
        "updated_at": now,
    }


def read_latest_followup_text(root: Path, task_id: str) -> str | None:
    """Read the latest follow-up markdown content for a task, if any."""
    followups_dir = tasks_dir(root) / "active" / task_id / "followups"
    if not followups_dir.is_dir():
        return None
    entries = sorted(followups_dir.glob("followup-???.md"))
    if not entries:
        return None
    return entries[-1].read_text(encoding="utf-8").strip() or None


def read_reflection_text(root: Path, task_id: str) -> str | None:
    """Read the reflection.md content for a task, if any."""
    path = tasks_dir(root) / "active" / task_id / "reflection.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


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

# Statuses that allow write/modification actions.
# Planning is included for task-package clarification recovery:
# the task can be edited to fill required clarification fields without
# already being fully execution-ready.
# Paused and blocked tasks should not receive edits until resumed/unblocked.
WRITE_ALLOWED_STATUSES = frozenset({
    "planning",
    "executing",
    "verifying",
    "changes_requested",
    "tweaking",
    "debugging",
})


def default_task_json(
    task_id: str,
    intake_id: str,
    title: str,
    goal: str,
    task_type: str,
    acceptance_criteria: list[str],
    *,
    parent_task_id: str | None = None,
    root_task_id: str | None = None,
    lineage_task_ids: list[str] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "id": task_id,
        "source_intake_id": intake_id,
        "parent_task_id": parent_task_id,
        "root_task_id": root_task_id or task_id,
        "lineage_task_ids": list(lineage_task_ids or []),
        "title": title,
        "type": task_type,
        "status": "planning",
        "current_step": "clarify",
        "owner_session": "main",
        "assigned_subagents": [],
        "subagent_routing": "main-agent-default",
        "goal": goal,
        "constraints": [],
        "acceptance_criteria": acceptance_criteria,
        "clarification": {
            "current_understanding": "",
            "expected_behavior": "",
            "actual_behavior": "",
            "reproduction": "",
            "scope": "",
            "decision_card": "",
            "user_action": "",
            "recommended_default": "",
            "option_matrix": "",
            "final_expected_effect": "",
            "approach_options": "",
            "chosen_approach": "",
            "final_implementation_plan": "",
            "minimum_viable_knowledge": "",
            "validation": "",
            "validation_card": "",
            "diagram": "",
            "confidence": "",
            "escalation_reason": "",
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
        "plan_id": None,
        "locks": [],
        "progress": None,
        "impact": [],
        "checkpoint_pass_completed": False,
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
    "Decision Card",
    "User Action",
    "Recommended Default",
    "Option Matrix",
    "Final Expected Effect",
    "Approach Options",
    "Chosen Approach",
    "Final Implementation Plan",
    "Minimum Viable Knowledge",
    "Validation",
    "Validation Card",
    "Diagram",
    "Confidence",
    "Escalation Reason",
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


def read_intake_parent_task_id(root: Path, intake_id: str) -> str | None:
    intake_md = state_dir(root) / "intake" / f"{intake_id}.md"
    if not intake_md.is_file():
        return None

    for line in intake_md.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        if line.startswith("Parent Task:"):
            return normalize_task_id(line.partition(":")[2])
    return None


def find_task_json_path(root: Path, task_id: str) -> Path | None:
    for base in (tasks_dir(root) / "active", tasks_dir(root) / "archive"):
        candidate = base / task_id / "task.json"
        if candidate.is_file():
            return candidate
    return None


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
        "raw_request": raw_request,
        "scope": sections.get("Scope", ""),
        "opening": sections.get("Opening", ""),
        "during_transition": sections.get("During Transition", ""),
        "after_open": sections.get("After Open", ""),
        "interrupt_behavior": sections.get("Interrupt Behavior", ""),
        "anti_outcomes": sections.get("Anti-Outcomes", ""),
        "decision_card": sections.get("Decision Card", ""),
        "user_action": sections.get("User Action", ""),
        "recommended_default": sections.get("Recommended Default", ""),
        "option_matrix": sections.get("Option Matrix", ""),
        "final_expected_effect": sections.get("Final Expected Effect", ""),
        "approach_options": sections.get("Approach Options", ""),
        "chosen_approach": sections.get("Chosen Approach", ""),
        "final_implementation_plan": sections.get("Final Implementation Plan", ""),
        "minimum_viable_knowledge": sections.get("Minimum Viable Knowledge", ""),
        "validation": sections.get("Validation", ""),
        "validation_card": sections.get("Validation Card", ""),
        "diagram": sections.get("Diagram", ""),
        "confidence": sections.get("Confidence", ""),
        "escalation_reason": sections.get("Escalation Reason", ""),
        "approval": sections.get("Approval", ""),
        "blocking_questions": blocking_questions,
        "non_blocking_questions": non_blocking_questions,
        "needs_bug_clarification": intake_needs_bug_clarification(task_type, raw_request, sections),
    }


# Heading-to-field mapping for markdown import into clarification.
# Mirrors the mapping in build_clarification_payload.
MARKDOWN_TO_CLARIFICATION_FIELD: dict[str, str] = {
    "Current Understanding": "current_understanding",
    "Expected Behavior": "expected_behavior",
    "Expected Outcome": "expected_behavior",
    "Actual Behavior": "actual_behavior",
    "Reproduction": "reproduction",
    "Scope": "scope",
    "Opening": "opening",
    "During Transition": "during_transition",
    "After Open": "after_open",
    "Interrupt Behavior": "interrupt_behavior",
    "Anti-Outcomes": "anti_outcomes",
    "Decision Card": "decision_card",
    "User Action": "user_action",
    "Recommended Default": "recommended_default",
    "Option Matrix": "option_matrix",
    "Final Expected Effect": "final_expected_effect",
    "Approach Options": "approach_options",
    "Chosen Approach": "chosen_approach",
    "Final Implementation Plan": "final_implementation_plan",
    "Minimum Viable Knowledge": "minimum_viable_knowledge",
    "Validation": "validation",
    "Validation Card": "validation_card",
    "Diagram": "diagram",
    "Confidence": "confidence",
    "Escalation Reason": "escalation_reason",
    "Approval": "approval",
}


def parse_markdown_clarification_fields(text: str) -> dict[str, Any]:
    """Parse a markdown/intake-style section file into clarification fields.

    Recognizes ``## Heading`` sections, maps known headings to clarification
    field names via MARKDOWN_TO_CLARIFICATION_FIELD, and handles list-typed
    fields (Blocking Questions, Non-Blocking Questions, Open Questions) via
    parse_question_block. Unknown headings are silently ignored.

    Raises:
        RuntimeError: If no ``##`` sections are found or no recognised
            clarification headings match.
    """
    sections = parse_markdown_sections(text)
    if not sections:
        raise RuntimeError(
            "No markdown sections (## Heading) found in file. "
            "Provide a file with ## headings or a JSON object."
        )

    fields: dict[str, Any] = {}
    for heading, body in sections.items():
        stripped_heading = heading.strip()
        # List-type headings
        if stripped_heading == "Blocking Questions":
            fields["blocking_questions"] = parse_question_block(body)
            continue
        if stripped_heading in ("Non-Blocking Questions", "Open Questions"):
            fields["non_blocking_questions"] = parse_question_block(body)
            continue
        # Scalar headings
        field_name = MARKDOWN_TO_CLARIFICATION_FIELD.get(stripped_heading)
        if field_name is not None:
            fields[field_name] = body.strip()
            # continue (implicit)

    if not fields:
        known = sorted(MARKDOWN_TO_CLARIFICATION_FIELD.keys())
        raise RuntimeError(
            f"No recognised clarification headings found in markdown file. "
            f"Known headings: {', '.join(known)}"
        )

    return fields


def build_clarification_payload_from_intake(root: Path, intake_id: str) -> dict[str, Any]:
    """Build a clarification payload by reading an intake file directly.

    Used by `update-intake-section` flow to get current state before update.
    """
    intake_path = root / "state" / "intake" / f"{intake_id}.md"
    if not intake_path.exists():
        raise RuntimeError(f"Intake file not found: {intake_path}")
    return parse_clarification_markdown_file(intake_path)


def sync_implementation_plan_context(
    root: Path,
    task_id: str,
    *,
    task: dict[str, Any] | None = None,
    require_plan: bool = False,
    mark_done: bool = False,
) -> dict[str, Any]:
    tpath = task_path(root, task_id)
    task_json_path = tpath / "task.json"
    if task is None:
        task = read_json(task_json_path)

    task_type = str(task.get("type", "") or "").strip().lower()
    if task_type not in {"design", "implementation", "feature", "feat", "refactor", "architecture"}:
        return task

    clarification = _task_clarification(task)
    plan_text = str(clarification.get("final_implementation_plan", "") or "").strip()
    if require_plan and not plan_text:
        raise RuntimeError(
            f"Cannot capture approved plan for task {task_id}: Final Implementation Plan is empty"
        )

    subtasks = build_implementation_plan_subtasks(plan_text)
    if mark_done:
        completed_at = utc_now()
        subtasks = [
            {**subtask, "status": "done", "completed_at": completed_at}
            for subtask in subtasks
        ]

    task_updates = {"subtasks": subtasks}
    task = update_task(root, task_id, task_updates)
    (tpath / "implement.md").write_text(render_implementation_plan_markdown(task, subtasks), encoding="utf-8")
    return task


def build_completion_report(
    task: dict[str, Any],
    result: str,
    summary: str,
    plan_continuation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    subtasks = task.get("subtasks", []) or []
    completed_items = [
        str(subtask.get("title", "")).strip()
        for subtask in subtasks
        if str(subtask.get("status", "") or "").strip().lower() == "done" and str(subtask.get("title", "") or "").strip()
    ]
    if result == "passed" and not completed_items:
        completed_items = [
            str(subtask.get("title", "")).strip()
            for subtask in subtasks
            if str(subtask.get("title", "") or "").strip()
        ]

    clarification = _task_clarification(task)
    remaining_risks = [
        str(item).strip()
        for item in (clarification.get("non_blocking_questions", []) or [])
        if str(item).strip()
    ]
    if not remaining_risks:
        remaining_risks = ["None noted."]

    # Include checkpoint commit summary in the completion report so the CLI
    # can display whether a commit was created, skipped, or not attempted.
    checkpoint = task.get("checkpoint_commit")
    checkpoint_info: dict[str, Any] = {"attempted": checkpoint is not None}
    if checkpoint:
        checkpoint_info["created"] = checkpoint.get("created", False)
        if not checkpoint.get("created"):
            checkpoint_info["reason"] = checkpoint.get("reason", "unknown")
        else:
            checkpoint_info["hash"] = checkpoint.get("commit_hash")
            checkpoint_info["message"] = checkpoint.get("message")
            if checkpoint.get("fallback_note"):
                checkpoint_info["note"] = checkpoint["fallback_note"]

    report = {
        "completed_items": completed_items,
        "verification_result": result,
        "verification_summary": summary,
        "remaining_risks": remaining_risks,
        "checkpoint": checkpoint_info,
    }
    if plan_continuation is not None:
        report["plan_continuation"] = plan_continuation
    return report


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

    # Build a proper v2 contract from the intake for readiness checking.
    contract = build_contract_from_intake(root, intake_id, title, goal, task_type, acceptance_criteria)
    readiness_errors = contract_readiness_errors(contract, task_type)
    if readiness_errors:
        raise RuntimeError("Promotion blocked: " + " ".join(readiness_errors))

    parent_task_id = read_intake_parent_task_id(root, intake_id)
    root_task_id = None
    lineage_task_ids: list[str] = []
    if parent_task_id:
        parent_task_path = find_task_json_path(root, parent_task_id)
        if parent_task_path is None:
            raise FileNotFoundError(f"Parent task not found: {parent_task_id}")
        parent_task = read_json(parent_task_path)
        root_task_id = normalize_task_id(parent_task.get("root_task_id")) or normalize_task_id(parent_task.get("id")) or parent_task_id
        lineage_task_ids = [parent_task_id]
        parent_lineage = parent_task.get("lineage_task_ids", [])
        if isinstance(parent_lineage, list):
            for ancestor_id in parent_lineage:
                normalized = normalize_task_id(ancestor_id)
                if normalized and normalized not in lineage_task_ids:
                    lineage_task_ids.append(normalized)
        if root_task_id and root_task_id not in lineage_task_ids:
            lineage_task_ids.append(root_task_id)

    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task_id = unique_readable_id(
        [tasks_dir(root) / "active", tasks_dir(root) / "archive"],
        f"{date_prefix}-{slugify(title)}-task",
    )

    # Build contract one final time (readiness check already validated).
    contract = build_contract_from_intake(root, intake_id, title, goal, task_type, acceptance_criteria)
    task_data = default_task_json_v2(
        task_id,
        intake_id,
        title,
        task_type,
        contract,
        parent_task_id=parent_task_id,
        root_task_id=root_task_id,
        lineage_task_ids=lineage_task_ids,
    )
    impl_plan = str(contract.get("choices", {}).get("final_implementation_plan", "") or "")
    task_data["subtasks"] = build_implementation_plan_subtasks(impl_plan)
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
            "context.md": render_context_markdown(task_data),
            "open_questions.md": _render_open_questions_simple(contract.get("open_questions", [])),
            "implement.md": render_implementation_plan_markdown(task_data, task_data["subtasks"]),
            "verify.md": render_verify_markdown(task_data),
        }.items():
            (tmp_path / name).write_text(content, encoding="utf-8")
        (tmp_path / "outputs").mkdir()
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


def update_intake_section(root: Path, intake_id: str, section_name: str, value: str) -> dict[str, Any]:
    """Update a named section in an existing intake markdown file in place.

    Args:
        root: Project root path.
        intake_id: Intake id (filename stem within state/intake/).
        section_name: Section heading name (e.g. "Scope", "Chosen Approach").
        value: New body content for the section.

    Returns:
        Dict with ok, intake_id, section, and the updated section body.

    Raises:
        FileNotFoundError: If the intake markdown file does not exist.
        ValueError: If section_name is not a known intake section.
        RuntimeError: If the section heading is not found in the file content.
    """
    ensure_workspace(root)
    intake_path = state_dir(root) / "intake" / f"{intake_id}.md"
    if not intake_path.is_file():
        raise FileNotFoundError(f"Intake not found: {intake_id}")

    known_sections = set(INTAKE_SECTION_ORDER)
    if section_name.strip() not in known_sections:
        raise ValueError(
            f"Unknown intake section: '{section_name}'. "
            f"Known sections: {', '.join(INTAKE_SECTION_ORDER)}"
        )

    text = intake_path.read_text(encoding="utf-8")
    section_name_escaped = re.escape(section_name.strip())
    pattern = re.compile(
        rf"(^## {section_name_escaped}\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if not pattern.search(text):
        raise RuntimeError(
            f"Section '## {section_name.strip()}' not found in intake {intake_id}"
        )

    new_body = value.strip()
    updated = pattern.sub(
        lambda match: f"{match.group(1)}{new_body}\n\n",
        text,
    )
    intake_path.write_text(updated, encoding="utf-8")

    append_workspace_event(
        root,
        "intake_section_updated",
        "intake",
        intake_id,
        f"Updated section '{section_name.strip()}' on intake {intake_id}",
    )

    return {
        "ok": True,
        "intake_id": intake_id,
        "section": section_name.strip(),
        "body": new_body,
    }


def create_intake(
    root: Path,
    title: str,
    raw_request: str,
    session_id: str,
    parent_task_id: str | None = None,
) -> dict[str, str]:
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
                *([f"Parent Task: {parent_task_id}"] if parent_task_id else []),
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
                "## Decision Card",
                "",
                "## User Action",
                "",
                "## Recommended Default",
                "",
                "## Option Matrix",
                "",
                "## Final Expected Effect",
                "",
                "## Approach Options",
                "",
                "## Chosen Approach",
                "",
                "## Final Implementation Plan",
                "",
                "## Minimum Viable Knowledge",
                "",
                "## Validation",
                "",
                "## Validation Card",
                "",
                "## Diagram",
                "",
                "## Confidence",
                "",
                "## Escalation Reason",
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
# Risk-shaped contract registry (mirrors just-demand-lib.js CONTRACT_REGISTRY)
# ---------------------------------------------------------------------------
CONTRACT_SIGNAL_PATTERNS: dict[str, list[re.Pattern]] = {
    "visible_effect": [
        re.compile(r"\b(ui|ux|animation|animated|animate|motion|reveal|stagger|fade|slide)\b", re.I),
        re.compile(r"(动效|动画|淡入|淡出|展开|收起|错峰|闪烁|抖动|过渡|首帧|打断|结束状态)"),
    ],
    "safety_boundary": [
        re.compile(r"\b(safety|destructive|irreversible|irreversibl|data\s+loss|rollback|revert|permission|authorization|auth[sz]|权限)\b", re.I),
        re.compile(r"(安全|破坏性|不可逆|数据丢失|回滚|恢复|授权)"),
    ],
}

CONTRACT_REGISTRY: list[dict[str, Any]] = [
    {
        "name": "visible_effect",
        "label": "Visible Effect",
        "gate_level": "hard",
        "signal_keys": ["visible_effect"],
        "execution_fields": [
            ("opening", "Opening"),
            ("during_transition", "During Transition"),
            ("after_open", "After Open"),
            ("interrupt_behavior", "Interrupt Behavior"),
            ("anti_outcomes", "Anti-Outcomes"),
        ],
    },
    {
        "name": "safety_boundary",
        "label": "Safety Boundary",
        "gate_level": "soft",
        "signal_keys": ["safety_boundary"],
        "execution_fields": [
            ("anti_outcomes", "Anti-Outcomes"),
        ],
    },
]


def detect_contract_triggers(text: str) -> set[str]:
    """Detect which contract types are triggered by text signals.

    Mirrors JS ``detectContractTriggers`` in just-demand-lib.js.
    """
    value = str(text or "").strip()
    if not value:
        return set()
    active: set[str] = set()
    for contract_name, patterns in CONTRACT_SIGNAL_PATTERNS.items():
        if any(p.search(value) for p in patterns):
            active.add(contract_name)
    return active


def detect_active_contracts_for_task(task: dict[str, Any]) -> set[str]:
    """Detect which risk-shaped contracts are active for a task.

    Mirrors JS ``detectActiveContractsForTask`` in just-demand-lib.js.
    Reads active_contracts from ``clarification.active_contracts``,
    legacy ``needs_ui_visible_lifecycle_clarification``, and text-based
    signal detection for visible_effect.
    """
    if not task:
        return set()
    clarification = _task_clarification(task)
    active: set[str] = set()

    # Read stored active_contracts array (v2 contract._extra or v1 clarification)
    stored = task.get("contract", {}).get("_extra", {}).get("active_contracts",
               clarification.get("active_contracts", None))
    if isinstance(stored, list):
        for name in stored:
            if isinstance(name, str):
                active.add(name.strip())

    # Legacy boolean flag
    if clarification.get("needs_ui_visible_lifecycle_clarification", False):
        active.add("visible_effect")

    # Text-based detection for visible_effect
    if "visible_effect" not in active:
        text_parts = [
            _safe_str(task.get("title", "")),
            _safe_str(clarification.get("goal", "")),
            _safe_str(clarification.get("current_understanding", "")),
            _safe_str(clarification.get("scope", "")),
            _safe_str(clarification.get("final_expected_effect", "")),
        ]
        combined = "\n".join(p for p in text_parts if p)
        if combined:
            text_triggers = detect_contract_triggers(combined)
            active.update(text_triggers)

    return active


def task_has_visible_effect_contract(task: dict[str, Any]) -> bool:
    """Return True if the task has an active visible-effect contract."""
    return "visible_effect" in detect_active_contracts_for_task(task)


# ---------------------------------------------------------------------------
# Execution readiness
# ---------------------------------------------------------------------------


def task_is_ready_for_execution(task: dict[str, Any]) -> bool:
    """Check if a task has all required clarification fields for execution.

    Works with both v1 (clarification dict) and v2 (contract) task records.
    Mirrors the JS taskIsReadyForExecution logic so both runtimes agree
    on what execution readiness means.
    """
    clarification = _task_clarification(task)
    missing = []

    if not str(clarification.get("scope", "") or "").strip():
        missing.append("Scope")

    blocking_questions = clarification.get("blocking_questions", []) or []
    if isinstance(blocking_questions, list) and len(blocking_questions) > 0:
        missing.append("Blocking Questions")

    task_type = str(task.get("type", "") or "").strip().lower()
    bug_types = {"bug", "bugfix", "fix", "incident"}
    design_types = {"design", "implementation", "feature", "feat", "refactor", "architecture"}

    needs_bug = task_type in bug_types or bool(clarification.get("needs_bug_clarification", False))
    if needs_bug:
        if not str(clarification.get("expected_behavior", "") or "").strip():
            missing.append("Expected Behavior")
        if not str(clarification.get("actual_behavior", "") or "").strip():
            missing.append("Actual Behavior")
        if not str(clarification.get("reproduction", "") or "").strip():
            missing.append("Reproduction")

    if task_type in design_types:
        if not str(clarification.get("final_expected_effect", "") or "").strip():
            missing.append("Final Expected Effect")
        if not str(clarification.get("chosen_approach", "") or "").strip():
            missing.append("Chosen Approach")
        if not str(clarification.get("final_implementation_plan", "") or "").strip():
            missing.append("Final Implementation Plan")
        if _task_is_v2(task):
            if not contract_authorization_is_valid(task.get("contract", {}) or {}):
                missing.append("Authorization")
        elif not str(clarification.get("approval", "") or "").strip():
            missing.append("Approval")

    # Contract-based execution checks (visible effect, safety boundary, etc.)
    # Mirrors JS getMissingExecutionGateFields contract loop.
    active_contracts = detect_active_contracts_for_task(task)
    for contract_def in CONTRACT_REGISTRY:
        cname = contract_def["name"]
        gate = contract_def.get("gate_level", "")
        if cname not in active_contracts:
            continue
        if gate not in ("hard", "soft"):
            continue
        for field_name, heading in contract_def.get("execution_fields", []):
            if not str(clarification.get(field_name, "") or "").strip():
                if heading not in missing:
                    missing.append(heading)

    return len(missing) == 0


def get_missing_execution_fields(task: dict[str, Any], role: str | None = None) -> list[str]:
    """Return list of missing required clarification field names for this task.

    Works with both v1 (clarification dict) and v2 (contract) task records.
    Mirrors the JS getMissingExecutionGateFields logic so both runtimes agree
    on what is missing for execution readiness.

    When ``role`` is ``"coder"``, also checks for a code map.
    When ``role`` is ``"tester"``, also checks for verification cases.
    """
    clarification = _task_clarification(task)
    missing: list[str] = []

    if not str(clarification.get("scope", "") or "").strip():
        missing.append("Scope")

    blocking_questions = clarification.get("blocking_questions", []) or []
    if isinstance(blocking_questions, list) and len(blocking_questions) > 0:
        missing.append("Blocking Questions")

    task_type = str(task.get("type", "") or "").strip().lower()
    bug_types = {"bug", "bugfix", "fix", "incident"}
    design_types = {"design", "implementation", "feature", "feat", "refactor", "architecture"}

    needs_bug = task_type in bug_types or bool(clarification.get("needs_bug_clarification", False))
    if needs_bug:
        if not str(clarification.get("expected_behavior", "") or "").strip():
            missing.append("Expected Behavior")
        if not str(clarification.get("actual_behavior", "") or "").strip():
            missing.append("Actual Behavior")
        if not str(clarification.get("reproduction", "") or "").strip():
            missing.append("Reproduction")

    if task_type in design_types:
        if not str(clarification.get("final_expected_effect", "") or "").strip():
            missing.append("Final Expected Effect")
        if not str(clarification.get("chosen_approach", "") or "").strip():
            missing.append("Chosen Approach")
        if not str(clarification.get("final_implementation_plan", "") or "").strip():
            missing.append("Final Implementation Plan")
        if _task_is_v2(task):
            if not contract_authorization_is_valid(task.get("contract", {}) or {}):
                missing.append("Authorization")
        elif not str(clarification.get("approval", "") or "").strip():
            missing.append("Approval")

    # Code-map readiness (role-gated: coder)
    if role == "coder" and not str(clarification.get("code_map", "") or "").strip():
        missing.append("Code Map")

    # Verification cases readiness (role-gated: tester)
    if role == "tester":
        cases = clarification.get("verification_cases", []) or []
        if not isinstance(cases, list) or len(cases) == 0:
            missing.append("Verification Cases")

    # Contract-based execution checks (visible effect, safety boundary, etc.)
    # Mirrors JS getMissingExecutionGateFields contract loop.
    active_contracts = detect_active_contracts_for_task(task)
    for contract_def in CONTRACT_REGISTRY:
        cname = contract_def["name"]
        gate = contract_def.get("gate_level", "")
        if cname not in active_contracts:
            continue
        if gate not in ("hard", "soft"):
            continue
        for field_name, heading in contract_def.get("execution_fields", []):
            if not str(clarification.get(field_name, "") or "").strip():
                if heading not in missing:
                    missing.append(heading)

    return missing


# ---------------------------------------------------------------------------
# Readiness diagnostics
# ---------------------------------------------------------------------------


def show_task_readiness(root: Path, task_id: str) -> dict[str, Any]:
    """Return structured readiness diagnostics for a task.

    Read-only: does not mutate any state.

    Returns a dict with:
      - task_id
      - status: current status string
      - ready: bool, whether the task is execution-ready
      - missing: list of missing field names (empty when ready)
      - writes_allowed: bool, whether writes are allowed in current status
      - write_allowed_statuses: list of statuses that allow writes
      - recommended_recovery: str, next recovery step suggestion
    """
    ensure_workspace(root)
    tpath = task_path(root, task_id) / "task.json"
    if not tpath.is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    task = read_json(tpath)
    status = task.get("status", "unknown")
    ready = task_is_ready_for_execution(task)
    missing = [] if ready else get_missing_execution_fields(task)
    writes_allowed = status in WRITE_ALLOWED_STATUSES

    # Determine recommended recovery step
    recommended_recovery: str
    if status == "done":
        recommended_recovery = "No recovery needed — task is complete."
    elif not writes_allowed:
        recommended_recovery = (
            f"Recovery: change status to a writable status first "
            f"(e.g., `mark {task_id} planning`), then run "
            f"`update-clarification {task_id} --field key=value`."
        )
    elif not ready:
        recommended_recovery = (
            f"Recovery: run `update-clarification {task_id} --field key=value` "
            f"for each missing field. "
            f"Missing fields: {', '.join(missing)}"
        )
    else:
        recommended_recovery = (
            "Task is execution-ready. "
            "Start execution when ready."
        )

    return {
        "task_id": task_id,
        "status": status,
        "ready": ready,
        "missing": missing,
        "writes_allowed": writes_allowed,
        "write_allowed_statuses": sorted(WRITE_ALLOWED_STATUSES),
        "recommended_recovery": recommended_recovery,
    }


CLARIFICATION_UPDATE_FIELDS = frozenset({
    "current_understanding",
    "expected_behavior",
    "actual_behavior",
    "reproduction",
    "scope",
    "out_of_scope",
    "invariants",
    "opening",
    "during_transition",
    "after_open",
    "interrupt_behavior",
    "anti_outcomes",
    "decision_card",
    "user_action",
    "recommended_default",
    "option_matrix",
    "final_expected_effect",
    "approach_options",
    "chosen_approach",
    "final_implementation_plan",
    "minimum_viable_knowledge",
    "validation",
    "validation_card",
    "diagram",
    "confidence",
    "escalation_reason",
    "approval",
    "acceptance_criteria",
    "decisions",
    "blocking_questions",
    "non_blocking_questions",
})

# Mapping from clarification field name to contract nested path (list of keys).
# Fields not in this map are stored in contract._extra.
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
    "acceptance_criteria": ["outcome", "acceptance_criteria"],
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
    # Visible-effect lifecycle fields — stored canonically in engineering.lifecycle
    "opening": ["engineering", "lifecycle", "opening"],
    "during_transition": ["engineering", "lifecycle", "during_transition"],
    "after_open": ["engineering", "lifecycle", "after_open"],
    "interrupt_behavior": ["engineering", "lifecycle", "interrupt_behavior"],
}


def _parse_clarification_value(key: str, value: Any) -> Any:
    """Parse a clarification field value (list or scalar)."""
    if key in {"blocking_questions", "non_blocking_questions", "decisions", "acceptance_criteria", "verification_cases", "work_items", "dependencies"}:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
                return [value]
            except (json.JSONDecodeError, TypeError):
                return [value]
        return [str(value)]
    return str(value).strip() if value else ""


def _set_contract_field(contract: dict[str, Any], key: str, value: Any) -> None:
    """Set a field in the nested contract dict using the known path mapping."""
    path = _CLARIFICATION_TO_CONTRACT_PATH.get(key)
    if path is None:
        # Store unknown fields in _extra
        contract.setdefault("_extra", {})[key] = value
        return
    target = contract
    for segment in path[:-1]:
        if segment not in target:
            target[segment] = {}
        target = target[segment]
    target[path[-1]] = value


def update_task_clarification(root: Path, task_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Update clarification fields on an active task and refresh derived package files.

    Args:
        root: Project root path.
        task_id: Active task id.
        fields: Dict of field_name -> value. String values for most fields;
            for list-typed fields (blocking_questions, non_blocking_questions),
            accepts a JSON array string or a Python list.

    Returns:
        Dict with ok, task_id, ready, missing fields, and the task data.

    Raises:
        FileNotFoundError if task does not exist.
        RuntimeError if task status does not allow updates.
        ValueError if an unknown field name is given.
    """
    ensure_workspace(root)
    tpath = task_path(root, task_id)
    task_json_path = tpath / "task.json"
    if not task_json_path.is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    task = read_json(task_json_path)
    status = task.get("status", "")
    if status not in WRITE_ALLOWED_STATUSES:
        raise RuntimeError(
            f"Cannot update clarification for task {task_id}: "
            f"status is '{status}'. "
            f"Allowed statuses: {', '.join(sorted(WRITE_ALLOWED_STATUSES))}"
        )

    is_v2 = _task_is_v2(task)

    if is_v2:
        # v2 path — write fields into the structured contract.
        contract = deepcopy(task.get("contract", empty_contract()))
        material_change = False
        for key, value in fields.items():
            if key not in CLARIFICATION_UPDATE_FIELDS:
                raise ValueError(f"Unknown clarification field: {key}")
            parsed = _parse_clarification_value(key, value)

            path = _CLARIFICATION_TO_CONTRACT_PATH.get(key)
            current = contract
            if path:
                for segment in path:
                    current = current.get(segment) if isinstance(current, dict) else None
            if key in MATERIAL_AUTHORIZATION_FIELDS and current != parsed:
                material_change = True

            # Map to contract path
            _set_contract_field(contract, key, parsed)

        if material_change:
            contract["contract_version"] = TASK_CONTRACT_VERSION
            contract["contract_revision"] = int(contract.get("contract_revision", 1) or 1) + 1
            contract["authorization"] = {
                "status": "pending",
                "scope": "task",
                "approved_at": "",
                "approved_by": "",
                "approved_revision": 0,
                "source": "material_contract_change",
            }

        approval = _safe_str(contract.get("choices", {}).get("approval", ""))
        if "approval" in fields:
            contract["contract_version"] = TASK_CONTRACT_VERSION
            if approval:
                revision = int(contract.get("contract_revision", 1) or 1)
                contract["authorization"] = {
                    "status": "approved",
                    "scope": "task",
                    "approved_at": utc_now(),
                    "approved_by": "user",
                    "approved_revision": revision,
                    "source": "explicit_user_approval",
                }
            else:
                contract["authorization"] = {
                    "status": "pending",
                    "scope": "task",
                    "approved_at": "",
                    "approved_by": "",
                    "approved_revision": 0,
                    "source": "approval_cleared",
                }

        update_task(root, task_id, {"contract": contract})
    else:
        # v1 path — write flat clarification dict.
        clarification = dict(task.get("clarification", {}) or {})
        for key, value in fields.items():
            if key not in CLARIFICATION_UPDATE_FIELDS:
                raise ValueError(f"Unknown clarification field: {key}")
            parsed = _parse_clarification_value(key, value)
            clarification[key] = parsed

        task["clarification"] = clarification
        update_task(root, task_id, {"clarification": clarification})

    task = sync_implementation_plan_context(root, task_id, task=task)

    # Packet-level atomic write: pre-compute all projection content first,
    # then write task.json + projections with rollback on failure.
    task = read_json(task_json_path)
    projection_contents: dict[str, str] = {
        "context.md": render_context_markdown(task),
        "research.md": render_research_markdown(task),
        "implement.md": render_implementation_plan_markdown(task),
        "verify.md": render_verify_markdown(task),
    }
    # Regenerate open_questions.md from non_blocking_questions
    clarification = _task_clarification(task)
    non_blocking = clarification.get("non_blocking_questions", []) or []
    projection_contents["open_questions.md"] = _render_open_questions_simple(
        non_blocking if isinstance(non_blocking, list) else []
    )

    # Read originals for rollback
    originals: dict[str, str | None] = {}
    for name in projection_contents:
        p = tpath / name
        originals[name] = p.read_text(encoding="utf-8") if p.is_file() else None

    written_files: list[str] = []
    try:
        for name, content in projection_contents.items():
            (tpath / name).write_text(content, encoding="utf-8")
            written_files.append(name)
    except Exception as write_err:
        # Rollback: restore originals for written files
        for name in written_files:
            p = tpath / name
            original = originals.get(name)
            if original is not None:
                p.write_text(original, encoding="utf-8")
            elif p.exists():
                p.unlink()
        raise RuntimeError(
            f"Projection write failed after task.json update for task {task_id}: {write_err}. "
            f"Files restored from originals: {', '.join(written_files)}"
        ) from write_err

    append_task_event(
        root,
        task_id,
        "clarification_updated",
        f"Updated clarification fields: {', '.join(sorted(fields.keys()))}",
    )

    task = read_json(task_json_path)
    ready = task_is_ready_for_execution(task)
    missing = get_missing_execution_fields(task) if not ready else []

    return {
        "ok": True,
        "task_id": task_id,
        "ready": ready,
        "missing": missing,
    }


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
    # Reset checkpoint-pass marker when task transitions to a pre-verification
    # status, indicating new work or a new verification pass has begun.
    pre_verification_statuses = {"planning", "executing", "verifying", "changes_requested", "tweaking", "debugging"}
    if status in pre_verification_statuses:
        updates["checkpoint_pass_completed"] = False
    # When marking to executing, also advance current_step from clarify/design to execute
    # so the plugin gate sees consistent state. This prevents self-locking where
    # status=executing but current_step=clarify causes soft-step fallback.
    if status == "executing":
        current_step = _safe_str(task.get("current_step", ""))
        if current_step in ("clarify", "design", ""):
            updates["current_step"] = "execute"
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
    return f"{prefix}: {subject}"


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
    baseline = task.get("worktree_baseline", {})
    baseline_paths = {
        _normalize_repo_path(path)
        for path in baseline.get("paths", [])
        if isinstance(path, str) and _normalize_repo_path(path)
    }
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
            and path not in baseline_paths
            and not _is_disallowed_checkpoint_path(path)
        ]
        fallback_note = None
    else:
        # A task baseline keeps unrelated worktree changes out of later commits.
        # Legacy tasks without a baseline preserve the historical all-path fallback.
        candidate_paths = [
            path
            for path in all_changed
            if path not in baseline_paths
            if not _is_disallowed_checkpoint_path(path)
        ]
        if candidate_paths:
            fallback_note = (
                "changed since execution baseline (no explicit impact scope)"
                if baseline
                else "all changed files (no explicit impact scope)"
            )
        else:
            fallback_note = None

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


def archive_task(root: Path, task_id: str) -> dict[str, Any]:
    """Archive a completed task by moving it to state/archive/.

    This preserves the full task directory while removing it from active state.
    Archive preserves task history directly; reusable lessons are captured elsewhere.
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

    # 1. Move task directory to archive
    try:
        shutil.move(str(task_dir), str(archive_task_dir))
    except Exception as e:
        # If move fails, report error but keep task in active state
        raise RuntimeError(f"Failed to archive task {task_id}: {e}")

    # 2. Update workspace state
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

    # 3. Append workspace event
    append_workspace_event(
        root,
        "task_archived",
        "task",
        task_id,
        f"Archived completed task {task_id}",
    )

    return {"task_id": task_id, "archived": True, "archive_path": str(archive_task_dir)}


# ---------------------------------------------------------------------------
# Validation revision
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Follow-up correction context
# ---------------------------------------------------------------------------


def create_followup(
    root: Path,
    task_id: str,
    user_feedback: str,
    observed_phenomenon: str,
    expected_phenomenon: str,
    delta_scope: str,
    must_not_change: str,
    acceptance: str,
) -> dict[str, str]:
    """Create a follow-up correction context file for an active task.

    Stores user correction feedback as a structured markdown file under
    the task's ``followups/`` directory. Files are sequentially numbered
    and never overwrite existing files.

    Args:
        root: Project root path.
        task_id: Active task id.
        user_feedback: User's correction feedback.
        observed_phenomenon: What was observed (current behavior/output).
        expected_phenomenon: What was expected (target behavior/output).
        delta_scope: Scope of the correction/delta.
        must_not_change: Things that must not be altered.
        acceptance: Acceptance criteria for the correction.

    Returns:
        Dict with followup_id, path, and task_id.

    Raises:
        FileNotFoundError: If task does not exist.
    """
    ensure_workspace(root)
    tpath = task_path(root, task_id)
    if not (tpath / "task.json").is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    followups_dir = tpath / "followups"
    followups_dir.mkdir(parents=True, exist_ok=True)

    # Determine next sequential number to avoid overwriting
    existing = sorted(f for f in followups_dir.iterdir() if f.suffix == ".md" and f.stem.startswith("followup-"))
    next_num = len(existing) + 1
    followup_id = f"followup-{next_num:03d}"

    followup_path = followups_dir / f"{followup_id}.md"

    lines = [
        f"# Follow-Up: {followup_id}",
        "",
        f"Task: {task_id}",
        "",
        "## User Feedback",
        user_feedback.strip(),
        "",
        "## Observed Phenomenon",
        observed_phenomenon.strip(),
        "",
        "## Expected Phenomenon",
        expected_phenomenon.strip(),
        "",
        "## Delta Scope",
        delta_scope.strip(),
        "",
        "## Must Not Change",
        must_not_change.strip(),
        "",
        "## Acceptance",
        acceptance.strip(),
        "",
    ]
    followup_path.write_text("\n".join(lines), encoding="utf-8")

    append_task_event(
        root,
        task_id,
        "followup_created",
        f"Created follow-up {followup_id}",
    )

    result: dict[str, Any] = {
        "followup_id": followup_id,
        "path": str(followup_path),
        "task_id": task_id,
    }

    # When this is at least the second follow-up, signal reflection guidance
    # so the main agent can convert repeated corrections into structured analysis.
    if len(existing) >= 1:
        result["reflection_recommended"] = True
        result["next_action"] = (
            f"This task now has {len(existing) + 1} follow-up corrections. "
            f"Use `start-reflection {task_id}` to create a structured "
            f"reflection context for advisor analysis."
        )

    return result


# ---------------------------------------------------------------------------
# Reflection
# ---------------------------------------------------------------------------


def start_reflection(root: Path, task_id: str) -> dict[str, Any]:
    """Create a structured reflection context for a task with repeated follow-ups.

    Generates ``reflection.md`` under the active task directory, records a
    ``reflection_started`` event, and marks the task as ``debugging`` so the
    main agent has a clear point to ask the advisor for analysis before further
    implementation.

    Args:
        root: Project root path.
        task_id: Active task id with at least 2 follow-up contexts.

    Returns:
        Dict with ok, task_id, path, and reflection_count.

    Raises:
        FileNotFoundError: If the task does not exist.
        RuntimeError: If the task has fewer than 2 follow-up contexts.
    """
    ensure_workspace(root)
    tpath = task_path(root, task_id)
    task_json_path = tpath / "task.json"
    if not task_json_path.is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    task = read_json(task_json_path)
    clarification = task.get("clarification", {}) or {}
    goal = str(task.get("goal", "") or "")
    current_understanding = str(clarification.get("current_understanding", "") or "")

    # Check follow-up existence and count
    followups_dir = tpath / "followups"
    if not followups_dir.is_dir():
        raise RuntimeError(
            f"No follow-up context found for task {task_id}. "
            f"Reflection requires at least two follow-ups."
        )

    existing_followups = sorted(
        f for f in followups_dir.iterdir()
        if f.suffix == ".md" and f.stem.startswith("followup-")
    )
    if len(existing_followups) < 2:
        raise RuntimeError(
            f"Reflection requires at least 2 follow-up contexts, "
            f"but task {task_id} has {len(existing_followups)}. "
            f"Record more follow-ups with `record-followup {task_id}`."
        )

    # Parse the two most recent follow-ups
    recent = existing_followups[-2:]
    followup_sections: list[dict[str, str]] = []
    followup_ids: list[str] = []
    for fup_path in recent:
        content = fup_path.read_text(encoding="utf-8")
        followup_ids.append(fup_path.stem)
        sections = parse_markdown_sections(content)
        followup_sections.append(sections)

    # Build reflection.md
    lines = [
        "# Reflection",
        "",
        f"Task: {task_id}",
        "",
        "## Goal / Context",
        "",
        goal or "_No goal recorded._",
        "",
        "## Current Understanding",
        "",
        current_understanding or "_No current understanding recorded._",
        "",
        "## Follow-Up History",
        "",
    ]

    for idx, sections in enumerate(followup_sections):
        fol_id = followup_ids[idx] if idx < len(followup_ids) else f"followup-{idx + 1:03d}"
        lines.append(f"### {fol_id}")
        lines.append("")

        for heading, body in sections.items():
            lines.append(f"**{heading}:**")
            lines.append(body)
            lines.append("")

    # Summary
    lines += [
        "## Summary",
        "",
        f"- Total follow-up corrections: {len(existing_followups)}",
        "- Repeated corrections detected — analysis recommended before further implementation.",
        "",
        "## Questions For Advisor",
        "",
        "_What underlying issue is causing repeated corrections? "
        "Is the current approach still valid, or does scope need adjustment? "
        "What is the safest next step?_",
        "",
    ]

    reflection_path = tpath / "reflection.md"
    reflection_path.write_text("\n".join(lines), encoding="utf-8")

    # Record reflection_started events
    reflection_count = len(existing_followups)
    append_task_event(
        root,
        task_id,
        "reflection_started",
        f"Started reflection for {task_id} ({reflection_count} follow-ups)",
        before_status=task.get("status", ""),
        after_status="debugging",
        reflection_count=reflection_count,
    )
    append_workspace_event(
        root,
        "reflection_started",
        "task",
        task_id,
        f"Started reflection for {task_id} ({reflection_count} follow-ups)",
        before_status=task.get("status", ""),
        after_status="debugging",
    )

    # Mark task as debugging — a reflection-compatible status
    mark_task(root, task_id, "debugging", note="Reflection started — repeated follow-ups detected")

    return {
        "ok": True,
        "task_id": task_id,
        "path": str(reflection_path),
        "reflection_count": reflection_count,
    }


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

    task = read_json(tpath / "task.json")
    task = sync_implementation_plan_context(root, task_id, task=task, require_plan=True)
    before_status = task["status"]

    updates = {
        "status": "executing",
        "current_step": "execute",
        "assigned_subagents": subagents,
    }
    if "worktree_baseline" not in task:
        repo_check = _run_git(root, "rev-parse", "--is-inside-work-tree")
        status_result = _run_git(root, "status", "--short")
        if repo_check.returncode == 0 and repo_check.stdout.strip() == "true" and status_result.returncode == 0:
            updates["worktree_baseline"] = {
                "captured_at": utc_now(),
                "paths": _parse_git_status_paths(status_result.stdout),
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

    # === Plan write-back for passed plan-linked tasks ===
    # Must happen BEFORE marking the task done so that any failure prevents
    # lifecycle progress (done/checkpoint/archive).
    plan_continuation: dict[str, Any] | None = None
    if result == "passed":
        plan_continuation = _write_back_plan_closeout(root, task_id, summary)
        # On failure, exception propagates — task is NOT marked done.

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
        # Guard: skip duplicate checkpoint commit if this verification pass
        # already completed checkpoint closeout for this task.
        existing_pass_marker = task.get("checkpoint_pass_completed", False)
        if existing_pass_marker:
            append_task_event(
                root, task_id, "checkpoint_commit_skipped",
                "Duplicate checkpoint commit prevented: already completed for this verification pass"
            )
            checkpoint_result = task.get("checkpoint_commit")
        else:
            checkpoint_result = create_checkpoint_commit(root, task_id)
            if checkpoint_result and checkpoint_result.get("created"):
                update_task(root, task_id, {"checkpoint_pass_completed": True})

    if result == "passed":
        task = sync_implementation_plan_context(root, task_id, task=task, mark_done=True)

    # Reload checkpoint/plan updates, then persist the completion report before
    # archive so continuation survives in the archived task package.
    task = read_json(task_path(root, task_id) / "task.json")
    completion_report = build_completion_report(task, result, summary, plan_continuation)
    task = update_task(root, task_id, {"completion_report": completion_report})

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

    result_data["completion_report"] = completion_report
    if plan_continuation is not None:
        result_data["plan_continuation"] = plan_continuation

    return result_data


def start_verification(root: Path, task_id: str) -> dict[str, Any]:
    """Transition a task from executing/tweaking/debugging toward verification.

    This creates an explicit post-write transition so the task does not remain
    open for unrestricted edits after implementation or debugging completes.
    After this transition, the task should move toward verification closeout.
    """
    tpath = task_path(root, task_id)
    task = read_json(tpath / "task.json")
    allowed_pre = {"executing", "tweaking", "debugging"}

    before_status = task.get("status")
    if before_status not in allowed_pre:
        raise RuntimeError(
            f"Cannot start verification for {task_id}: "
            f"status is '{before_status}', "
            f"expected one of {', '.join(sorted(allowed_pre))}"
        )

    return mark_task(root, task_id, "verifying", note="Starting verification phase")


# ---------------------------------------------------------------------------
# Plan-ledger — lightweight roadmap and suggestion data model
# ---------------------------------------------------------------------------

VALID_SUGGESTION_STATUSES = frozenset({
    "proposed",
    "accepted",
    "deferred",
    "rejected",
    "implemented",
    "superseded",
})


def plans_dir(root: Path) -> Path:
    return state_dir(root) / "plans"


def plan_path(root: Path, plan_id: str) -> Path:
    return plans_dir(root) / plan_id


def default_plan_data(plan_id: str, title: str) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "id": plan_id,
        "title": title,
        "stages": [],
        "suggestions": {},
        "suggestion_order": [],
        "created_at": now,
        "updated_at": now,
    }


def default_suggestion_data(
    suggestion_id: str,
    stage_id: str,
    verbatim_text: str,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "id": suggestion_id,
        "stage_id": stage_id,
        "verbatim_text": verbatim_text,
        "status": "proposed",
        "status_history": [
            {
                "from_status": None,
                "to_status": "proposed",
                "at": now,
                "reason": "Created",
            }
        ],
        "dependencies": [],
        "covered_tasks": [],
        "evidence": [],
        "created_at": now,
        "updated_at": now,
    }


def create_plan(root: Path, title: str) -> dict[str, Any]:
    """Create a new plan with an optional initial stage.

    Args:
        root: Project root.
        title: Human-readable plan title.

    Returns:
        Dict with plan_id, title, and stages.

    Raises:
        RuntimeError if the plan cannot be created.
    """
    ensure_workspace(root)
    now = utc_now()
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with workflow_mutation_lock(root):
        plan_id = unique_readable_id(
            [plans_dir(root)],
            f"{date_prefix}-{slugify(title)}-plan",
            suffix="",
        )

        plan_dir = plan_path(root, plan_id)
        plan_dir.mkdir(parents=True, exist_ok=False)

        plan_data = default_plan_data(plan_id, title)
        write_json_atomic(plan_dir / "plan.json", plan_data)

    append_workspace_event(
        root,
        "plan_created",
        "plan",
        plan_id,
        f"Created plan '{title}' ({plan_id})",
    )

    return {
        "plan_id": plan_id,
        "title": title,
        "stages": [],
    }


def _load_plan(root: Path, plan_id: str) -> dict[str, Any]:
    """Load plan data, raising FileNotFoundError if missing."""
    pdir = plan_path(root, plan_id)
    json_path = pdir / "plan.json"
    if not json_path.is_file():
        raise FileNotFoundError(f"Plan not found: {plan_id}")
    return read_json(json_path)


def _save_plan(root: Path, plan_data: dict[str, Any]) -> None:
    """Atomically write plan data to disk."""
    pdir = plan_path(root, plan_data["id"])
    pdir.mkdir(parents=True, exist_ok=True)
    plan_data["updated_at"] = utc_now()
    write_json_atomic(pdir / "plan.json", plan_data)


def read_plan(root: Path, plan_id: str) -> dict[str, Any]:
    """Read and return plan data."""
    return _load_plan(root, plan_id)


def list_plans(root: Path) -> list[dict[str, Any]]:
    """List all plans with summary info."""
    ensure_workspace(root)
    pdir = plans_dir(root)
    if not pdir.exists():
        return []
    result = []
    for entry in sorted(pdir.iterdir()):
        if not entry.is_dir():
            continue
        json_path = entry / "plan.json"
        if not json_path.is_file():
            continue
        plan = read_json(json_path)
        result.append({
            "plan_id": plan.get("id", entry.name),
            "title": plan.get("title", ""),
            "stage_count": len(plan.get("stages", [])),
            "suggestion_count": len(plan.get("suggestions", {})),
            "created_at": plan.get("created_at", ""),
            "updated_at": plan.get("updated_at", ""),
        })
    return result


def add_plan_stage(
    root: Path,
    plan_id: str,
    stage_id: str,
    title: str,
) -> dict[str, Any]:
    """Add a stage to an existing plan.

    Args:
        root: Project root.
        plan_id: Existing plan id.
        stage_id: Machine-readable stage id (e.g. 'phase-1').
        title: Human-readable stage title.

    Returns:
        Updated plan data.

    Raises:
        FileNotFoundError: Plan does not exist.
        ValueError: Stage id already exists in plan.
    """
    with workflow_mutation_lock(root):
        plan = _load_plan(root, plan_id)
        stages = plan.setdefault("stages", [])
        if any(s["id"] == stage_id for s in stages):
            raise ValueError(
                f"Stage '{stage_id}' already exists in plan '{plan_id}'"
            )
        order = len(stages) + 1
        stages.append({
            "id": stage_id,
            "title": title,
            "order": order,
        })
        _save_plan(root, plan)

        # Auto-refresh all active tasks (stage change affects current/pending/next)
        failed = _refresh_all_active_tasks_for_plan_unlocked(root, plan_id)

    append_workspace_event(
        root,
        "plan_stage_added",
        "plan",
        plan_id,
        f"Added stage '{stage_id}' to plan '{plan_id}'",
    )

    if failed:
        raise RuntimeError(
            f"Stage '{stage_id}' added to plan '{plan_id}', "
            f"but snapshot refresh failed for task(s): {', '.join(failed)}. "
            f"Use refresh-plan-context to retry."
        )

    return plan


def add_plan_suggestion(
    root: Path,
    plan_id: str,
    stage_id: str,
    verbatim_text: str,
    *,
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    """Add a verbatim suggestion to a plan stage.

    The suggestion text is preserved verbatim as provided. A suggestion id
    is auto-generated from the plan and stage.

    Args:
        root: Project root.
        plan_id: Existing plan id.
        stage_id: Existing stage id within the plan.
        verbatim_text: The exact user original text, preserved as-is.
        dependencies: Optional list of existing suggestion ids this depends on.

    Returns:
        Dict with suggestion_id and updated plan data.

    Raises:
        FileNotFoundError: Plan does not exist.
        ValueError: Stage id not found.
    """
    with workflow_mutation_lock(root):
        plan = _load_plan(root, plan_id)
        stages = plan.get("stages", [])
        if not any(s["id"] == stage_id for s in stages):
            raise ValueError(
                f"Stage '{stage_id}' not found in plan '{plan_id}'. "
                f"Known stages: {', '.join(s['id'] for s in stages)}"
            )

        suggestions = plan.setdefault("suggestions", {})
        suggestion_order = plan.setdefault("suggestion_order", [])

        # Build suggestion id
        slug = slugify(verbatim_text[:40])
        base_id = f"sug-{slug}"
        suggestion_id = base_id
        existing_ids = set(suggestions.keys())
        if suggestion_id in existing_ids:
            for _ in range(100):
                candidate = f"{base_id}-{uuid.uuid4().hex[:6]}"
                if candidate not in existing_ids:
                    suggestion_id = candidate
                    break
            else:
                raise RuntimeError(f"Could not generate unique suggestion id")

        # Validate dependencies point to existing suggestions
        if dependencies:
            for dep_id in dependencies:
                if dep_id not in suggestions:
                    raise ValueError(
                        f"Dependency suggestion '{dep_id}' not found in plan '{plan_id}'"
                    )

        sug_data = default_suggestion_data(suggestion_id, stage_id, verbatim_text)
        if dependencies:
            sug_data["dependencies"] = list(dependencies)
        suggestions[suggestion_id] = sug_data
        suggestion_order.append(suggestion_id)
        _save_plan(root, plan)

        # Auto-refresh all active tasks (new suggestion changes remaining-in-stage)
        failed = _refresh_all_active_tasks_for_plan_unlocked(root, plan_id)

    append_workspace_event(
        root,
        "plan_suggestion_added",
        "plan",
        plan_id,
        f"Added suggestion '{suggestion_id}' to stage '{stage_id}'",
    )

    if failed:
        raise RuntimeError(
            f"Suggestion '{suggestion_id}' added to plan '{plan_id}', "
            f"but snapshot refresh failed for task(s): {', '.join(failed)}. "
            f"Use refresh-plan-context to retry."
        )

    return {
        "suggestion_id": suggestion_id,
        "plan": plan,
    }


def update_suggestion_status(
    root: Path,
    plan_id: str,
    suggestion_id: str,
    new_status: str,
    *,
    reason: str | None = None,
) -> dict[str, Any]:
    """Update suggestion status, preserving history.

    Args:
        root: Project root.
        plan_id: Existing plan id.
        suggestion_id: Existing suggestion id within the plan.
        new_status: One of VALID_SUGGESTION_STATUSES.
        reason: Optional human-readable reason for the transition.

    Returns:
        Updated plan data.

    Raises:
        FileNotFoundError: Plan does not exist.
        ValueError: Invalid status or suggestion not found.
    """
    if new_status not in VALID_SUGGESTION_STATUSES:
        raise ValueError(
            f"Invalid suggestion status '{new_status}'. "
            f"Valid: {', '.join(sorted(VALID_SUGGESTION_STATUSES))}"
        )

    with workflow_mutation_lock(root):
        plan = _load_plan(root, plan_id)
        suggestions = plan.get("suggestions", {})
        if suggestion_id not in suggestions:
            raise ValueError(
                f"Suggestion '{suggestion_id}' not found in plan '{plan_id}'"
            )

        sug = suggestions[suggestion_id]
        from_status = sug["status"]
        if from_status == new_status:
            raise ValueError(
                f"Suggestion '{suggestion_id}' status is already '{new_status}'"
            )

        now = utc_now()
        sug["status"] = new_status
        history = sug.setdefault("status_history", [])
        history.append({
            "from_status": from_status,
            "to_status": new_status,
            "at": now,
            "reason": reason or "",
        })
        sug["updated_at"] = now
        suggestions[suggestion_id] = sug
        _save_plan(root, plan)

        # Auto-refresh plan context for all active tasks associated with this suggestion
        _refresh_active_tasks_for_suggestion(root, plan_id, suggestion_id)

    append_workspace_event(
        root,
        "plan_suggestion_status_updated",
        "plan",
        plan_id,
        f"Updated suggestion '{suggestion_id}' status: {from_status} -> {new_status}",
        from_status=from_status,
        to_status=new_status,
    )

    return plan


def add_task_to_plan(
    root: Path,
    plan_id: str,
    suggestion_id: str,
    task_id: str,
) -> dict[str, Any]:
    """Associate an existing task with a plan suggestion.

    The plan is the authoritative source of truth for task-plan association
    (via each suggestion's ``covered_tasks`` list). The task's ``plan_id``
    is a convenience field set before the plan save, so a write failure
    never leaves the plan referencing a task whose ``plan_id`` is stale.
    If the plan save fails after the task was updated, the task write is
    rolled back.  All writes happen inside the same mutation lock.

    Args:
        root: Project root.
        plan_id: Existing plan id.
        suggestion_id: Existing suggestion id within the plan.
        task_id: Existing task id (active or archived).

    Returns:
        Updated plan data.

    Raises:
        FileNotFoundError: Plan or task not found.
        ValueError: Suggestion not found in plan.
    """
    # Verify task exists (validation before lock -- cheap idempotent check)
    tpath = find_task_json_path(root, task_id)
    if tpath is None:
        raise FileNotFoundError(f"Task not found: {task_id}")

    with workflow_mutation_lock(root):
        plan = _load_plan(root, plan_id)
        suggestions = plan.get("suggestions", {})
        if suggestion_id not in suggestions:
            raise ValueError(
                f"Suggestion '{suggestion_id}' not found in plan '{plan_id}'"
            )

        sug = suggestions[suggestion_id]
        covered = sug.setdefault("covered_tasks", [])
        if task_id not in covered:
            covered.append(task_id)
        suggestions[suggestion_id] = sug

        # Write task.plan_id FIRST (non-authoritative convenience field).
        # If this write fails the exception propagates before the plan is
        # saved, so there is no inconsistency.
        active_path = tasks_dir(root) / "active" / task_id / "task.json"
        task_was_modified = False
        if active_path.is_file():
            task_data = read_json(active_path)
            if task_data.get("plan_id") is None:
                task_data["plan_id"] = plan_id
                write_json_atomic(active_path, task_data)
                task_was_modified = True

        # Save plan LAST (authoritative commit point).
        try:
            _save_plan(root, plan)
        except Exception:
            # Rollback: restore task.plan_id if we changed it.
            if task_was_modified and active_path.is_file():
                task_data = read_json(active_path)
                task_data["plan_id"] = None
                write_json_atomic(active_path, task_data)
            raise

        # Auto-refresh plan context for the associated task (only if active).
        # Plan is already committed — if refresh fails, task files are
        # restored by _refresh_plan_context_unlocked's rollback but the
        # plan association is preserved for retry via refresh-plan-context.
        if active_path.is_file():
            _refresh_plan_context_unlocked(root, task_id)

    append_workspace_event(
        root,
        "plan_task_added",
        "plan",
        plan_id,
        f"Associated task '{task_id}' with suggestion '{suggestion_id}'",
    )

    return plan


def add_plan_evidence(
    root: Path,
    plan_id: str,
    suggestion_id: str,
    evidence_text: str,
) -> dict[str, Any]:
    """Record completion evidence for a suggestion.

    Args:
        root: Project root.
        plan_id: Existing plan id.
        suggestion_id: Existing suggestion id within the plan.
        evidence_text: Evidence of completion.

    Returns:
        Updated plan data.

    Raises:
        FileNotFoundError: Plan does not exist.
        ValueError: Suggestion not found.
    """
    with workflow_mutation_lock(root):
        plan = _load_plan(root, plan_id)
        suggestions = plan.get("suggestions", {})
        if suggestion_id not in suggestions:
            raise ValueError(
                f"Suggestion '{suggestion_id}' not found in plan '{plan_id}'"
            )

        sug = suggestions[suggestion_id]
        evidence = sug.setdefault("evidence", [])
        if evidence_text not in evidence:
            evidence.append(evidence_text)
        sug["updated_at"] = utc_now()
        suggestions[suggestion_id] = sug
        _save_plan(root, plan)

        # Auto-refresh plan context for all active tasks associated with this suggestion
        _refresh_active_tasks_for_suggestion(root, plan_id, suggestion_id)

    append_workspace_event(
        root,
        "plan_evidence_added",
        "plan",
        plan_id,
        f"Added evidence to suggestion '{suggestion_id}'",
    )

    return plan


def _write_back_plan_closeout(
    root: Path,
    task_id: str,
    verification_summary: str,
) -> dict[str, Any] | None:
    """Write verification closeout evidence back to the plan ledger.

    Called only for passed verification results on plan‑linked tasks.
    Inside a mutation lock:
      1. Validates the task is listed in at least one suggestion's
         ``covered_tasks``.
      2. Transitions covered suggestions (proposed/accepted) to implemented,
         with terminal‑state safety (rejected/superseded untouched).
      3. Appends structured closeout evidence (task_id, summary, timestamp,
         revision, commit hash when available).
      4. Saves the plan atomically.
      5. Computes continuation data (remaining items, next stage, blockers).
      6. Refreshes remaining active task snapshots.

    Returns a continuation dict, or *None* if the task has no ``plan_id``.
    Raises on any failure — the caller must NOT mark the task done.

    Continuation dict shape::

        {
            "plan_id": str,
            "plan_title": str,
            "completed_suggestions": [{"id": str, "text": str, "status": str}],
            "skipped_suggestions": [{"id": str, "text": str, "reason": str}],
            "remaining_actionable": [{"id": str, "text": str, "status": str}],
            "deferred": [{"id": str, "text": str, "status": str}],
            "rejected": [{"id": str, "text": str, "status": str}],
            "superseded": [{"id": str, "text": str, "status": str}],
            "next_stage": {"id": str, "title": str} | None,
            "is_plan_complete": bool,
            "blockers": [{"id": str, "text": str, "status": str}],
            "continue_action": str,
        }
    """
    tpath = task_path(root, task_id) / "task.json"
    if not tpath.is_file():
        raise FileNotFoundError(f"Task not found: {task_id}")

    task = read_json(tpath)
    plan_id = task.get("plan_id")
    if not plan_id:
        return None

    # Best‑effort HEAD commit hash
    commit_hash: str | None = None
    try:
        head = _run_git(root, "rev-parse", "HEAD")
        if head.returncode == 0:
            commit_hash = head.stdout.strip()
    except Exception:
        pass

    rev_tag = str(task.get("validation_revision") or "unknown")
    now = utc_now()

    # Identify covered suggestions and transition inside a single lock
    with workflow_mutation_lock(root):
        plan = _load_plan(root, plan_id)
        suggestions = plan.setdefault("suggestions", {})
        suggestion_order = plan.get("suggestion_order", [])

        covered_ids: list[str] = []
        for sug_id in suggestion_order:
            sug = suggestions.get(sug_id)
            if sug is None:
                continue
            if task_id in sug.get("covered_tasks", []):
                covered_ids.append(sug_id)

        if not covered_ids:
            raise ValueError(
                f"Task {task_id} is linked to plan {plan_id} "
                f"but is not listed in any suggestion's covered_tasks"
            )

        completed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for sug_id in covered_ids:
            sug = suggestions[sug_id]
            current_status = sug.get("status", "proposed")
            verbatim = sug.get("verbatim_text", "")[:80]

            # Idempotent recovery: a previous write-back may have committed the
            # plan before a later task/checkpoint/archive step failed.
            existing_evidence = next(
                (
                    entry for entry in sug.get("evidence", [])
                    if isinstance(entry, dict)
                    and entry.get("type") == "verification_closeout"
                    and entry.get("task_id") == task_id
                ),
                None,
            )
            if current_status == "implemented" and existing_evidence is not None:
                completed.append({"id": sug_id, "text": verbatim, "status": "implemented"})
                continue

            # Terminal / idempotent guards
            if current_status == "implemented":
                skipped.append({"id": sug_id, "text": verbatim, "reason": "already_implemented"})
                continue
            if current_status in ("rejected", "superseded"):
                skipped.append({"id": sug_id, "text": verbatim, "reason": f"terminal_state_{current_status}"})
                continue
            if current_status not in ("proposed", "accepted"):
                # Defensive: any other status we don't recognise — skip
                skipped.append({"id": sug_id, "text": verbatim, "reason": f"not_transitionable_{current_status}"})
                continue

            # Transition to implemented
            from_status = sug["status"]
            sug["status"] = "implemented"
            history = sug.setdefault("status_history", [])
            history.append({
                "from_status": from_status,
                "to_status": "implemented",
                "at": now,
                "reason": f"Verification passed for task {task_id}",
            })
            evidence = sug.setdefault("evidence", [])
            evidence.append({
                "type": "verification_closeout",
                "task_id": task_id,
                "verification_summary": verification_summary,
                "at": now,
                "revision": rev_tag,
                "commit_hash": commit_hash,
            })
            sug["updated_at"] = now
            suggestions[sug_id] = sug
            completed.append({"id": sug_id, "text": verbatim, "status": "implemented"})

        _save_plan(root, plan)

    # --- outside the lock: compute continuation, refresh snapshots, emit event ---

    plan = _load_plan(root, plan_id)
    suggestions_data = plan.get("suggestions", {})
    stages = plan.get("stages", [])

    # Determine current stage from the first covered suggestion
    current_stage_id: str | None = None
    for sug_id in covered_ids:
        sug = suggestions_data.get(sug_id, {})
        sid = sug.get("stage_id", "")
        if sid:
            current_stage_id = sid
            break

    # Find next stage
    next_stage: dict[str, Any] | None = None
    found = False
    for st in stages:
        if found:
            next_stage = {"id": st["id"], "title": st["title"]}
            break
        if st["id"] == current_stage_id:
            found = True

    # Classify remaining suggestions
    remaining_actionable: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    superseded: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []

    for sug_id in suggestion_order:
        sug = suggestions_data.get(sug_id)
        if sug is None:
            continue
        status = sug.get("status", "")
        verbatim = sug.get("verbatim_text", "")[:80]

        if status == "proposed":
            remaining_actionable.append({"id": sug_id, "text": verbatim, "status": "proposed"})
        elif status == "accepted":
            remaining_actionable.append({"id": sug_id, "text": verbatim, "status": "accepted"})
        elif status == "deferred":
            deferred.append({"id": sug_id, "text": verbatim, "status": "deferred"})
        elif status == "rejected":
            rejected.append({"id": sug_id, "text": verbatim, "status": "rejected"})
        elif status == "superseded":
            superseded.append({"id": sug_id, "text": verbatim, "status": "superseded"})

        # Blockers belong to remaining actionable suggestions, not to work that
        # has just completed.
        if status in ("proposed", "accepted"):
            for dep_id in sug.get("dependencies", []):
                dep_sug = suggestions_data.get(dep_id, {})
                dep_status = dep_sug.get("status", "")
                if dep_status != "implemented" and not any(b["id"] == dep_id for b in blockers):
                    dep_text = dep_sug.get("verbatim_text", "")[:80]
                    blockers.append({"id": dep_id, "text": dep_text, "status": dep_status})

    is_plan_complete = (
        len(remaining_actionable) == 0
        and len(deferred) == 0
        and len(blockers) == 0
    )

    # Build human‑readable continue action
    continue_action: str
    if is_plan_complete:
        continue_action = (
            "All plan suggestions are implemented. The plan is complete. "
            "No further tasks required."
        )
    elif blockers:
        block_names = [b["id"] for b in blockers]
        continue_action = (
            f"Blocked by unimplemented suggestion{'s' if len(block_names) > 1 else ''}: "
            f"{', '.join(block_names)}. "
            f"Resolve blockers before continuing."
        )
    elif remaining_actionable and next_stage:
        continue_action = (
            f"Next stage: '{next_stage['title']}'. "
            f"Review the remaining suggestions, then create or select a formal task "
            f"for the approved next stage. No task was started automatically."
        )
    elif remaining_actionable:
        continue_action = (
            f"{len(remaining_actionable)} actionable suggestion(s) remain in the current stage. "
            f"Create additional tasks to cover remaining suggestions."
        )
    else:
        continue_action = "No remaining actionable items."

    # Refresh active task snapshots for this plan
    failed = _refresh_all_active_tasks_for_plan_unlocked(root, plan_id)
    if failed:
        append_workspace_event(
            root,
            "plan_snapshot_refresh_failed",
            "plan",
            plan_id,
            f"Snapshot refresh failed for task(s): {', '.join(failed)}",
        )
        raise RuntimeError(
            f"Plan closeout snapshot refresh failed for task(s): {', '.join(failed)}. "
            "The plan write-back is committed and idempotent; repair the task context "
            "and retry complete-verification."
        )

    append_workspace_event(
        root,
        "plan_closeout_written",
        "plan",
        plan_id,
        f"Closeout written for task {task_id} on plan {plan_id}: "
        f"{len(completed)} implemented, {len(skipped)} skipped",
    )

    return {
        "plan_id": plan_id,
        "plan_title": plan.get("title", ""),
        "completed_suggestions": completed,
        "skipped_suggestions": skipped,
        "remaining_actionable": remaining_actionable,
        "deferred": deferred,
        "rejected": rejected,
        "superseded": superseded,
        "next_stage": next_stage,
        "is_plan_complete": is_plan_complete,
        "blockers": blockers,
        "continue_action": continue_action,
    }


# ---------------------------------------------------------------------------
# Plan snapshot — context file injection
# ---------------------------------------------------------------------------

PLAN_SECTION_MARKER_START = "<!-- plan-snapshot -->"
PLAN_SECTION_MARKER_END = "<!-- /plan-snapshot -->"


def _atomic_write_text(path: Path, content: str) -> None:
    """Write a text file atomically using temp-file + rename (POSIX atomic)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _refresh_plan_context_unlocked(root: Path, task_id: str) -> dict[str, Any]:
    """Generate or refresh plan snapshot sections — no lock, for internal use.

    Plan data is read fresh from disk.  Task context files are pre-computed
    in memory and written atomically.  If any write fails, already-updated
    files are restored from in-memory backup.

    NOTE: Does NOT emit ``plan_context_refreshed`` events because callers
    may already hold ``workflow_mutation_lock`` (and ``append_task_event``
    acquires the same lock via ``next_event_seq``).  The public wrapper
    ``refresh_plan_context`` emits the event after releasing the lock.

    Raises:
        FileNotFoundError: Task or plan not found.
        ValueError: Task has no plan_id, or plan references are damaged.
        RuntimeError: Any write failure (original content restored).
    """
    ensure_workspace(root)

    # Find task (active or archived)
    tpath = find_task_json_path(root, task_id)
    if tpath is None:
        raise FileNotFoundError(f"Task not found: {task_id}")

    task = read_json(tpath)
    plan_id = task.get("plan_id")
    if not plan_id:
        raise ValueError(f"Task {task_id} has no plan_id set")

    # Build the snapshot (validates plan, stages, suggestions)
    snapshot = _build_plan_snapshot(root, task)

    # Render sections
    context_section = _render_plan_context_section(snapshot)
    implement_section = _render_plan_implement_section(snapshot)
    verify_section = _render_plan_verify_section(snapshot)

    task_dir = tpath.parent

    # Read or create each file
    context_path = task_dir / "context.md"
    implement_path = task_dir / "implement.md"
    verify_path = task_dir / "verify.md"

    # Base content: read existing or render default
    if context_path.is_file():
        context_content = context_path.read_text(encoding="utf-8")
    else:
        context_content = render_context_markdown(task)

    if implement_path.is_file():
        implement_content = implement_path.read_text(encoding="utf-8")
    else:
        subtasks = task.get("subtasks", [])
        implement_content = render_implementation_plan_markdown(task, subtasks)

    if verify_path.is_file():
        verify_content = verify_path.read_text(encoding="utf-8")
    else:
        verify_content = render_verify_markdown(task)

    # Merge plan sections (pure computation, no I/O)
    context_content = _replace_or_append_plan_section(context_content, context_section)
    implement_content = _replace_or_append_plan_section(implement_content, implement_section)
    verify_content = _replace_or_append_plan_section(verify_content, verify_section)

    # --- Atomic write with rollback ---
    files_to_write = {
        context_path: context_content,
        implement_path: implement_content,
        verify_path: verify_content,
    }
    originals: dict[Path, str] = {}
    for path in files_to_write:
        if path.is_file():
            originals[path] = path.read_text(encoding="utf-8")

    written: list[Path] = []
    try:
        for path, content in files_to_write.items():
            _atomic_write_text(path, content)
            written.append(path)
    except Exception as write_err:
        # Restore already-written files from in-memory backup
        for path in written:
            try:
                if path in originals:
                    _atomic_write_text(path, originals[path])
                else:
                    path.unlink(missing_ok=True)
            except Exception:
                pass  # Best-effort restore
        raise RuntimeError(
            f"Plan snapshot write failed for task {task_id}: {write_err}. "
            f"Original content restored for {len(written)} file(s). "
            f"Use refresh-plan-context to retry."
        ) from write_err

    updated_files = ["context.md", "implement.md", "verify.md"]

    return {
        "task_id": task_id,
        "plan_id": plan_id,
        "updated_files": updated_files,
        "is_active": (tasks_dir(root) / "active" / task_id / "task.json").is_file(),
    }


def refresh_plan_context(root: Path, task_id: str) -> dict[str, Any]:
    """Generate or refresh plan snapshot sections in a task's context files.

    Public API — acquires the workflow mutation lock before writing, so it
    is safe to call directly (e.g. from the CLI or tests).  Internal callers
    that already hold the lock must use ``_refresh_plan_context_unlocked``.

    Reads the plan data and generates plan context sections for context.md,
    implement.md, and verify.md.  Uses stable markers to only replace the
    generated content, preserving unrelated markdown.  Writes are atomic
    with rollback on failure.

    Args:
        root: Project root.
        task_id: Task id (must have a plan_id set).

    Returns:
        Dict with task_id, plan_id, and the updated files list.

    Raises:
        FileNotFoundError: Task or plan not found.
        ValueError: Task has no plan_id, or plan references are damaged.
        RuntimeError: Write failure (original content restored).
    """
    with workflow_mutation_lock(root):
        result = _refresh_plan_context_unlocked(root, task_id)

    # Emit event outside the lock (append_task_event acquires the same lock)
    if result.get("is_active"):
        append_task_event(
            root, task_id, "plan_context_refreshed",
            f"Refreshed plan context from plan '{result['plan_id']}' for task {task_id}",
        )

    return result


def _refresh_all_active_tasks_for_plan_unlocked(root: Path, plan_id: str) -> list[str]:
    """Refresh all active (non-archived) tasks associated with a plan.

    This is an internal unlocked helper meant to be called from mutation
    functions that already hold ``workflow_mutation_lock`` or have just
    released it.  It collects all ``covered_tasks`` across every suggestion
    in the plan and refreshes each one that is still active.

    Args:
        root: Project root.
        plan_id: The plan whose active tasks should be refreshed.

    Returns:
        A list of task IDs that failed to refresh (empty on full success).
    """
    try:
        plan = _load_plan(root, plan_id)
    except Exception:
        return [f"<cannot load plan {plan_id}>"]

    suggestions = plan.get("suggestions", {})
    active_tasks: set[str] = set()
    for sug in suggestions.values():
        for tid in sug.get("covered_tasks", []):
            if (tasks_dir(root) / "active" / tid / "task.json").is_file():
                active_tasks.add(tid)

    failed: list[str] = []
    for tid in sorted(active_tasks):
        try:
            _refresh_plan_context_unlocked(root, tid)
        except Exception:
            failed.append(tid)

    return failed


def _refresh_active_tasks_for_suggestion(root: Path, plan_id: str, suggestion_id: str) -> None:
    """Refresh plan context for all active tasks covered by a suggestion.

    Uses the unlocked variant to avoid lock contention when called from a
    context that has already released ``workflow_mutation_lock``.

    Best-effort: errors are silently caught so the caller's mutation is not
    rolled back by a render failure.
    """
    try:
        plan = _load_plan(root, plan_id)
    except Exception:
        return
    sug = plan.get("suggestions", {}).get(suggestion_id)
    if sug is None:
        return
    for tid in sug.get("covered_tasks", []):
        if not (tasks_dir(root) / "active" / tid / "task.json").is_file():
            continue
        try:
            _refresh_plan_context_unlocked(root, tid)
        except Exception:
            pass


def _build_plan_snapshot(root: Path, task: dict[str, Any]) -> dict[str, Any]:
    """Build structured plan snapshot data for a task.
    
    Returns a dict with plan context information, raising errors for
    missing or damaged references.
    
    Raises:
        FileNotFoundError: Plan not found.
        ValueError: Task has no plan_id, no covered suggestions, or bad stage ref.
    """
    ensure_workspace(root)
    plan_id = task.get("plan_id")
    if not plan_id:
        raise ValueError(f"Task {task.get('id', 'unknown')} has no plan_id")

    plan = _load_plan(root, plan_id)
    task_id = task.get("id", "")
    suggestions = plan.get("suggestions", {})
    stages = plan.get("stages", [])
    suggestion_order = plan.get("suggestion_order", [])

    # Find all suggestions that cover this task
    task_suggestions: list[dict[str, Any]] = []
    for sug_id in suggestion_order:
        sug = suggestions.get(sug_id)
        if sug is None:
            continue
        if task_id in sug.get("covered_tasks", []):
            task_suggestions.append({**sug, "id": sug_id})

    if not task_suggestions:
        raise ValueError(
            f"Task {task_id} is associated with plan {plan_id} "
            f"but is not listed in any suggestion's covered_tasks"
        )

    # Get the stage for this task (use the first suggestion's stage)
    current_stage_id = task_suggestions[0].get("stage_id", "")
    current_stage = None
    for st in stages:
        if st["id"] == current_stage_id:
            current_stage = st
            break
    if current_stage is None:
        raise ValueError(
            f"Stage '{current_stage_id}' referenced by suggestion "
            f"'{task_suggestions[0]['id']}' not found in plan '{plan_id}'"
        )

    # Remaining suggestions in the same stage (not covered by this task)
    remaining_suggestions: list[dict[str, Any]] = []
    for sug_id in suggestion_order:
        sug = suggestions.get(sug_id)
        if sug is None:
            continue
        if sug.get("stage_id") == current_stage_id and task_id not in sug.get("covered_tasks", []):
            remaining_suggestions.append({**sug, "id": sug_id})

    # Dependencies: collect all dependencies from our task's suggestions
    dep_ids: list[str] = []
    for ts in task_suggestions:
        for dep in ts.get("dependencies", []):
            if dep not in dep_ids:
                dep_ids.append(dep)

    dep_suggestions: list[dict[str, Any]] = []
    for dep_id in dep_ids:
        dep_sug = suggestions.get(dep_id)
        if dep_sug is not None:
            dep_suggestions.append({**dep_sug, "id": dep_id})

    # Next stage
    next_stage = None
    found_current = False
    for st in stages:
        if found_current:
            next_stage = st
            break
        if st["id"] == current_stage_id:
            found_current = True

    return {
        "plan_id": plan_id,
        "plan_title": plan.get("title", ""),
        "current_stage": current_stage,
        "next_stage": next_stage,
        "task_suggestions": task_suggestions,
        "remaining_suggestions": remaining_suggestions,
        "dependencies": dep_suggestions,
        "stages": stages,
    }


def _render_suggestion_bullets(suggestions: list[dict[str, Any]], indent: str = "") -> list[str]:
    """Render suggestions as markdown bullet items with status."""
    if not suggestions:
        return [f"{indent}_None._"]
    lines = []
    for sug in suggestions:
        text = sug.get("verbatim_text", "").strip()
        status = sug.get("status", "unknown")
        lines.append(f"{indent}- {text} [{status}]")
    return lines


def _render_plan_context_section(snapshot: dict[str, Any]) -> str:
    """Render the plan snapshot section for context.md."""
    lines = [
        "## Plan Context",
        "",
        f"**Plan:** {snapshot['plan_title']} ({snapshot['plan_id']})",
        "",
        f"**Current Stage:** {snapshot['current_stage']['title']}",
        "",
        "**This Task Covers:**",
        "",
    ]
    lines.extend(_render_suggestion_bullets(snapshot["task_suggestions"]))
    lines.append("")

    if snapshot["remaining_suggestions"]:
        lines.append("**Remaining In Stage:**")
        lines.append("")
        lines.extend(_render_suggestion_bullets(snapshot["remaining_suggestions"]))
        lines.append("")

    if snapshot["dependencies"]:
        lines.append("**Dependencies:**")
        lines.append("")
        lines.extend(_render_suggestion_bullets(snapshot["dependencies"]))
        lines.append("")

    next_stage = snapshot.get("next_stage")
    if next_stage:
        lines.append(f"**Next Stage:** {next_stage['title']}")
    else:
        lines.append("**Next Stage:** _Final stage_")
    lines.append("")

    # Evidence requirements
    lines.append("**Evidence Requirements:**")
    lines.append("")
    for sug in snapshot["task_suggestions"]:
        text = sug.get("verbatim_text", "").strip()
        short = (text[:60] + "...") if len(text) > 60 else text
        ev_count = len(sug.get("evidence", []))
        lines.append(f"- {short}: {ev_count} evidence item(s)")
    if not snapshot["task_suggestions"]:
        lines.append("_None._")
    lines.append("")

    return "\n".join(lines)


def _render_plan_implement_section(snapshot: dict[str, Any]) -> str:
    """Render the plan snapshot section for implement.md."""
    lines = [
        "## Plan Context",
        "",
        "**Task Suggestions:**",
        "",
    ]
    lines.extend(_render_suggestion_bullets(snapshot["task_suggestions"]))
    lines.append("")

    if snapshot["dependencies"]:
        lines.append("**Prerequisites:**")
        lines.append("")
        lines.extend(_render_suggestion_bullets(snapshot["dependencies"]))
        lines.append("")

    lines.append("**Required Evidence:**")
    lines.append("")
    for sug in snapshot["task_suggestions"]:
        text = sug.get("verbatim_text", "").strip()
        status = sug.get("status", "unknown")
        lines.append(f"- [{status}] {text}")
    if not snapshot["task_suggestions"]:
        lines.append("_None._")
    lines.append("")

    return "\n".join(lines)


def _render_plan_verify_section(snapshot: dict[str, Any]) -> str:
    """Render the plan snapshot section for verify.md."""
    lines = [
        "## Plan Context",
        "",
        "| Suggestion | Status | Evidence | Verified |",
        "|---|---|---|---|",
    ]
    for sug in snapshot["task_suggestions"]:
        text = sug.get("verbatim_text", "").strip()
        short = (text[:40] + "...") if len(text) > 40 else text
        status = sug.get("status", "unknown")
        ev_count = len(sug.get("evidence", []))
        verified = "✓" if ev_count > 0 else "☐"
        lines.append(f"| {short} | {status} | {ev_count} | {verified} |")

    if snapshot["remaining_suggestions"]:
        lines.append("")
        lines.append("**Remaining Suggestions (not covered by this task):**")
        lines.append("")
        lines.extend(_render_suggestion_bullets(snapshot["remaining_suggestions"]))

    lines.append("")
    return "\n".join(lines)


def _replace_or_append_plan_section(content: str, section_body: str) -> str:
    """Replace content between plan snapshot markers, or append at end.
    
    If the marker pair is found, content between them is replaced.
    If no markers exist, the section is appended at the end.
    If only one marker is found, RuntimeError is raised (corrupt state).
    """
    marker_start = PLAN_SECTION_MARKER_START
    marker_end = PLAN_SECTION_MARKER_END

    start_idx = content.find(marker_start)
    end_idx = content.find(marker_end)

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        # Replace content between markers
        before = content[:start_idx + len(marker_start)]
        after = content[end_idx:]
        return before + "\n" + section_body.strip() + "\n" + after
    elif start_idx != -1 or end_idx != -1:
        raise RuntimeError(
            "Corrupt plan snapshot markers: found only one of the start/end pair"
        )
    else:
        # No markers — append at end
        stripped = content.rstrip()
        return stripped + "\n\n" + marker_start + "\n" + section_body.strip() + "\n" + marker_end + "\n"
