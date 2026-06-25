#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import shlex
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_core import (
    archive_task,
    build_execution_packet,
    cleanup_completed_task,
    complete_verification,
    create_checkpoint_commit,
    create_intake,
    list_unfinished_tasks,
    mark_task,
    parse_markdown_clarification_fields,
    promote_to_task,
    render_execution_packet_markdown,
    render_task_readiness_card,
    select_task,
    show_task_readiness,
    start_verification,
    update_intake_section,
    update_task_clarification,
)
from install import (
    init_project,
    install_opencode_global,
    update_opencode_global,
    doctor_opencode_global,
    uninstall_opencode_global,
)


COMMANDS = {
    "archive-task",
    "build-packet",
    "checkpoint-commit",
    "cleanup-task",
    "complete-verification",
    "create-intake",
    "doctor",
    "init",
    "install",
    "lint-packet",
    "list-active",
    "mark",
    "promote",
    "render-context",
    "resume",
    "select-task",
    "show-readiness",
    "smoke",
    "start-verification",
    "uninstall",
    "update",
    "update-clarification",
    "update-intake-section",
    "where",
}

GLOBAL_COMMANDS = {"install", "update", "uninstall", "where"}
HELP_FLAGS = {"-h", "--help"}
TASK_SELECTION_NEXT_ACTIONS = [
    "Run `just-demand . list-active` before execution.",
    "If execution needs broad code reading, 3+ files, multi-step research/debugging, or extended verification, dispatch a just-demand-* subagent.",
    "Confirm required task context files exist before implementation or verification.",
]

SUMMARY_COMMANDS = {
    "archive-task",
    "checkpoint-commit",
    "create-intake",
    "list-active",
    "mark",
    "promote",
    "resume",
    "select-task",
    "show-readiness",
    "smoke",
    "start-verification",
    "update-intake-section",
    "complete-verification",
    "cleanup-task",
}


def _parse_field_args(raw_fields: list[str]) -> dict[str, str]:
    """Parse --field key=value arguments into a dict."""
    fields: dict[str, str] = {}
    for raw in raw_fields:
        if "=" not in raw:
            raise ValueError(f"Invalid --field format: '{raw}'. Expected key=value")
        key, _, value = raw.partition("=")
        key = key.strip()
        if not key:
            raise ValueError(f"Empty key in --field '{raw}'")
        fields[key] = value
    return fields


def with_task_selection_next_actions(result: dict) -> dict:
    """Attach concise, machine-readable workflow guidance to task selection results."""
    if isinstance(result, dict):
        result = dict(result)
        result["next_actions"] = TASK_SELECTION_NEXT_ACTIONS
    return result


def _print_summary_line(label: str, value: object, *, stream) -> None:
    if value is None:
        return
    if isinstance(value, list):
        if not value:
            return
        stream.write(f"{label}:\n")
        for item in value:
            stream.write(f"  - {item}\n")
        return
    stream.write(f"{label}: {value}\n")


def print_structured_summary(command: str, result: dict[str, Any], stream=None) -> None:
    """Emit a concise, stable success summary to stderr for fast scanning."""
    if not isinstance(result, dict) or result.get("status") == "error":
        return

    out = stream if stream is not None else sys.stderr
    lines: list[str] = []

    if command == "create-intake":
        lines.extend([
            "Result: intake created",
            f"Intake ID: {result.get('intake_id', '')}",
            f"Path: {result.get('path', '')}",
            "Next action: fill in Scope and the remaining clarification fields.",
        ])
    elif command == "update-intake-section":
        lines.extend([
            "Result: intake section updated",
            f"Intake ID: {result.get('intake_id', '')}",
            f"Section: {result.get('section', '')}",
            "Next action: continue filling the remaining intake sections.",
        ])
    elif command == "promote":
        lines.extend([
            "Result: task promoted",
            f"Task ID: {result.get('task_id', '')}",
            f"Path: {result.get('path', '')}",
        ])
        next_actions = result.get("next_actions") or []
        if next_actions:
            lines.append("Next actions:")
            lines.extend([f"  - {action}" for action in next_actions])
    elif command in {"select-task", "resume"}:
        lines.extend([
            "Result: task selected",
            f"Task ID: {result.get('task_id', '')}",
            f"Status: {result.get('status', '')}",
        ])
        next_actions = result.get("next_actions") or []
        if next_actions:
            lines.append("Next actions:")
            lines.extend([f"  - {action}" for action in next_actions])
    elif command == "list-active":
        tasks = result.get("tasks", []) or []
        lines.append(f"Result: {len(tasks)} unfinished task{'s' if len(tasks) != 1 else ''}")
        if tasks:
            lines.append("Tasks:")
            for task in tasks:
                progress = task.get("progress")
                progress_text = f"{progress}%" if progress is not None else "n/a"
                impact = task.get("impact") or []
                impact_text = ", ".join(impact) if impact else "none"
                title = task.get("title", "")
                lines.append(
                    f"  - {task.get('id', '')} | {task.get('status', '')} | {progress_text} | {title}"
                )
                lines.append(f"    Impact: {impact_text}")
            lines.append("Next action: select a task with `just-demand . select-task <task-id>` or `resume <task-id>`.")
        else:
            lines.append("Tasks: none")
            lines.append("Next action: create an intake when new work arrives.")
    elif command == "show-readiness":
        lines.extend(render_task_readiness_card(result).rstrip().splitlines())
    elif command == "mark":
        lines.extend([
            "Result: task marked",
            f"Task ID: {result.get('id', '')}",
            f"Status: {result.get('status', '')}",
        ])
        if result.get("progress") is not None:
            lines.append(f"Progress: {result.get('progress')}%")
    elif command == "start-verification":
        lines.extend([
            "Result: verification started",
            f"Task ID: {result.get('id', result.get('task_id', ''))}",
            f"Status: {result.get('status', '')}",
            "Next action: complete verification with `just-demand . complete-verification`.",
        ])
    elif command == "complete-verification":
        verification_status = result.get("verification_status", result.get("status", ""))
        lines.extend([
            f"Result: verification {verification_status}",
            f"Task ID: {result.get('id', result.get('task_id', ''))}",
            f"Status: {result.get('status', '')}",
            f"Archived: {'yes' if result.get('archived') else 'no'}",
        ])
        checkpoint = result.get("checkpoint_commit") or {}
        if isinstance(checkpoint, dict) and checkpoint:
            checkpoint_state = "created" if checkpoint.get("created") else f"skipped ({checkpoint.get('reason', 'unknown')})"
            lines.append(f"Checkpoint commit: {checkpoint_state}")
    elif command == "checkpoint-commit":
        created = bool(result.get("created"))
        lines.extend([
            f"Result: checkpoint commit {'created' if created else 'skipped'}",
            f"Task ID: {result.get('task_id', '')}",
        ])
        if result.get("commit_hash"):
            lines.append(f"Commit: {result.get('commit_hash')}")
        if result.get("reason"):
            lines.append(f"Reason: {result.get('reason')}")
    elif command in {"archive-task", "cleanup-task"}:
        lines.extend([
            f"Result: task {'archived' if command == 'archive-task' else 'cleaned up'}",
            f"Task ID: {result.get('task_id', '')}",
        ])
        if command == "archive-task":
            lines.append(f"Archive path: {result.get('archive_path', '')}")
    elif command == "smoke":
        checks = result.get("checks", []) or []
        lines.append("Result: smoke validation passed")
        if checks:
            lines.append("Checks:")
            for check in checks:
                lines.append(f"  - {check.get('name', '')}")
    else:
        lines.append(f"Result: {result.get('status', 'success')}")
        for key, value in result.items():
            if key == "status":
                continue
            if key == "next_actions":
                _print_summary_line("Next actions", value, stream=out)
                continue
            _print_summary_line(key.replace("_", " ").title(), value, stream=out)
        return

    for line in lines:
        out.write(line + "\n")
    out.flush()


def split_project_root(argv: list[str]) -> tuple[Path | None, list[str]]:
    """Split an optional leading project directory from command arguments."""
    if len(argv) >= 2 and argv[0] not in COMMANDS and not argv[0].startswith("-") and (argv[1] in COMMANDS or argv[1] in HELP_FLAGS):
        return Path(argv[0]), argv[1:]
    return None, argv


def format_project_invocation(project_root: Path | None, command: str = "list-active") -> str:
    if project_root is None:
        return f"  just-demand [project-dir] {command}"
    return f"  just-demand {project_root} {command}"


def print_project_invocation(project_root: Path | None, stream=None) -> None:
    out = stream if stream is not None else sys.stdout
    out.write("\nProject invocation:\n")
    out.write(format_project_invocation(project_root) + "\n")
    out.write("  (omit [project-dir] to use the current directory)\n")


def smoke_checks() -> list[tuple[str, list[str]]]:
    repo = repo_root()
    task_cli = str(repo / "just-demand")
    return [
        ("workflow core tests", [sys.executable, "-m", "unittest", "tests.just_demand.test_workflow_core", "-v"]),
        ("install tests", [sys.executable, "-m", "unittest", "tests.just_demand.test_install", "-v"]),
        ("OpenCode plugin tests", ["node", "--test", "tests/just_demand/test_opencode_plugins.mjs"]),
        ("package JSON", [sys.executable, "-m", "json.tool", ".opencode/package.json"]),
        ("CLI help", [sys.executable, task_cli, "--help"]),
        ("project CLI help", [sys.executable, task_cli, ".", "--help"]),
    ]


def run_smoke_checks() -> dict[str, Any]:
    repo = repo_root()
    checks: list[dict[str, Any]] = []
    for name, command in smoke_checks():
        completed = subprocess.run(command, cwd=repo, text=True, capture_output=True)
        check_result = {
            "name": name,
            "command": command,
            "cwd": str(repo),
            "returncode": completed.returncode,
        }
        checks.append(check_result)
        if completed.returncode != 0:
            raise RuntimeError(
                "Smoke check failed: "
                f"{name} (rc={completed.returncode})\n"
                f"Command: {' '.join(command)}\n"
                f"stdout:\n{completed.stdout or ''}\n"
                f"stderr:\n{completed.stderr or ''}"
            )
    return {"status": "success", "checks": checks}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Just Demand task tools",
        epilog=(
            "Use: just-demand <command> ...\n"
            "Project path form: just-demand [project-dir] <command> ...\n"
            "Help: just-demand --help | just-demand [project-dir] --help | just-demand <command> --help"
        ),
    )
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

    list_active = sub.add_parser("list-active", help="List all unfinished formal tasks")
    list_active.add_argument("--verbose", action="store_true", help="Include current_step and path")

    select_task_parser = sub.add_parser("select-task", help="Select an unfinished formal task as current")
    select_task_parser.add_argument("task_id", help="Task ID to make current")

    resume = sub.add_parser("resume", help="Resume an unfinished formal task by selecting it as current")
    resume.add_argument("task_id", help="Task ID to resume")

    mark = sub.add_parser("mark", help="Mark task status, progress, impact, and note")
    mark.add_argument("task_id", help="Task ID to mark")
    mark.add_argument("status", help="New status (planning,executing,verifying,changes_requested,blocked,paused,tweaking,debugging)")
    mark.add_argument("--progress", type=int, default=None, help="Progress 0-100")
    mark.add_argument("--impact", action="append", default=None, help="Affected path/module (repeatable)")
    mark.add_argument("--note", default=None, help="Short note for current state")

    checkpoint = sub.add_parser("checkpoint-commit", help="Create a checkpoint commit for a task (requires passed verification)")
    checkpoint.add_argument("task_id", help="Task ID to create a checkpoint commit for")

    packet = sub.add_parser("build-packet", help="Build an execution packet for a task")
    packet.add_argument("task_id", help="Task ID to build a packet for")
    packet.add_argument("--role", default="coder", choices=["coder", "tester", "advisor", "researcher"], help="Role-specific packet view")
    packet.add_argument("--subtask-id", default=None, help="Select a specific subtask for the packet")
    packet.add_argument("--hint", action="append", default=[], help="Supplemental hint (format: key=value, repeatable)")
    packet.add_argument("--format", default="json", choices=["json", "markdown"], help="Output format")

    render_context = sub.add_parser("render-context", help="Render compact role-specific context for a task")
    render_context.add_argument("task_id", help="Task ID to render context for")
    render_context.add_argument("--role", default="coder", choices=["coder", "tester", "advisor", "researcher"], help="Role-specific context view")
    render_context.add_argument("--subtask-id", default=None, help="Select a specific subtask for the rendered context")
    render_context.add_argument("--hint", action="append", default=[], help="Supplemental hint (format: key=value, repeatable)")

    lint_packet = sub.add_parser("lint-packet", help="Lint an execution packet for a task")
    lint_packet.add_argument("task_id", help="Task ID to lint packet for")
    lint_packet.add_argument("--role", default="coder", choices=["coder", "tester", "advisor", "researcher"], help="Role-specific packet view")
    lint_packet.add_argument("--subtask-id", default=None, help="Select a specific subtask for the packet")
    lint_packet.add_argument("--hint", action="append", default=[], help="Supplemental hint (format: key=value, repeatable)")

    cleanup = sub.add_parser("cleanup-task", help="Clean up a completed task and remove its runtime references")
    cleanup.add_argument("task_id", help="Task ID to clean up (must be status 'done')")

    archive = sub.add_parser("archive-task", help="Archive a completed task to tasks/archive/")
    archive.add_argument("task_id", help="Task ID to archive (must be status 'done')")

    start_verif = sub.add_parser("start-verification", help="Transition a task from executing/tweaking/debugging toward verification")
    start_verif.add_argument("task_id", help="Task ID to transition to verification")

    complete = sub.add_parser("complete-verification", help="Record verification result and optionally create a checkpoint commit")
    complete.add_argument("task_id", help="Task ID to complete verification for")
    complete.add_argument("result", choices=["passed", "failed", "blocked"])
    complete.add_argument("summary", help="Short verification summary")
    complete.add_argument("--no-auto-archive", action="store_true", help="Keep passed task active instead of archiving it")
    complete.add_argument("--no-checkpoint-commit", action="store_true", help="Skip automatic checkpoint commit on passed verification")

    sub.add_parser("init", help="Initialize project-local .just-demand state")

    install = sub.add_parser("install", help="Install Just Demand globally for OpenCode")
    install.add_argument("--opencode", action="store_true", help="Install OpenCode runtime assets")
    install.add_argument("--global", action="store_true", dest="global_install", help="Install globally")
    install.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")

    update = sub.add_parser("update", help="Update existing global installation")
    update.add_argument("--opencode", action="store_true", help="Update OpenCode runtime assets")
    update.add_argument("--global", action="store_true", dest="global_update", help="Update global installation")
    update.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")

    doctor = sub.add_parser("doctor", help="Report installation and activation status")
    doctor.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")

    uninstall = sub.add_parser("uninstall", help="Remove global Just Demand installation")
    uninstall.add_argument("--opencode", action="store_true", help="Uninstall OpenCode runtime assets")
    uninstall.add_argument("--global", action="store_true", dest="global_uninstall", help="Uninstall globally")
    uninstall.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")

    update_clar = sub.add_parser("update-clarification", help="Update clarification fields on an active task to resolve readiness gaps")
    update_clar.add_argument("task_id", help="Task ID to update")
    update_clar.add_argument("--field", action="append", default=[], help="Clarification field to update (format: key=value, repeatable)")
    update_clar.add_argument("--from-file", default=None, help="Path to a JSON object file or a markdown section file (## headings) containing clarification field updates")

    update_intake_sec = sub.add_parser("update-intake-section", help="Update a named section in an existing intake markdown file")
    update_intake_sec.add_argument("intake_id", help="Intake ID to update")
    update_intake_sec.add_argument("section", help="Section heading name (e.g. 'Scope', 'Chosen Approach')")
    update_intake_sec.add_argument("value", help="New body content for the section")

    show_readiness = sub.add_parser("show-readiness", help="Show readiness diagnostics for a task")
    show_readiness.add_argument("task_id", help="Task ID to check readiness for")

    sub.add_parser("smoke", help="Run the repo smoke validation checks")

    sub.add_parser("where", help="Print the global CLI path and invocation example")

    return parser


def execute_command(root: Path, args: list[str]) -> int:
    """Execute a single command with the given arguments."""
    try:
        parsed = build_parser().parse_args(args)
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        return 0 if code is None else 1

    try:
        if parsed.command == "create-intake":
            result = create_intake(root, parsed.title, parsed.raw_request, parsed.session)
        elif parsed.command == "update-intake-section":
            result = update_intake_section(root, parsed.intake_id, parsed.section, parsed.value)
        elif parsed.command == "checkpoint-commit":
            result = create_checkpoint_commit(root, parsed.task_id)
        elif parsed.command in {"build-packet", "render-context", "lint-packet"}:
            hints: dict[str, Any] = {}
            for raw_hint in parsed.hint:
                if "=" not in raw_hint:
                    raise ValueError(f"Invalid --hint format: '{raw_hint}'. Expected key=value")
                key, _, value = raw_hint.partition("=")
                key = key.strip()
                if not key:
                    raise ValueError(f"Empty key in --hint '{raw_hint}'")
                hints.setdefault(key, [])
                if key == "focus":
                    hints[key] = value
                else:
                    hints[key].append(value)
            packet = build_execution_packet(root, parsed.task_id, role=parsed.role, subtask_id=parsed.subtask_id, hints=hints)
            if parsed.command == "lint-packet":
                result = {
                    "task_id": packet.get("task_id"),
                    "role": packet.get("role"),
                    "requested_subtask_id": packet.get("requested_subtask_id"),
                    "selected_subtask_id": (packet.get("selected_subtask") or {}).get("id"),
                    "ready": packet.get("ready"),
                    "lint": packet.get("lint", []),
                }
                print(json.dumps(result, ensure_ascii=False))
                return 0 if packet.get("ready") else 2
            if parsed.command == "render-context":
                print(render_execution_packet_markdown(packet), end="")
                return 0 if packet.get("ready") else 2
            if parsed.format == "markdown":
                print(render_execution_packet_markdown(packet), end="")
            else:
                print(json.dumps(packet, ensure_ascii=False))
            return 0 if packet.get("ready") else 2
        elif parsed.command == "update-clarification":
            fields: dict[str, Any] = {}
            # Load from-file first (base), then --field overrides on top
            if parsed.from_file:
                from_path = Path(parsed.from_file)
                if not from_path.is_file():
                    raise RuntimeError(f"Clarification file not found: {from_path}")
                raw_text = from_path.read_text(encoding="utf-8")
                try:
                    raw = json.loads(raw_text)
                except json.JSONDecodeError:
                    # Not valid JSON — try markdown section parsing
                    try:
                        raw = parse_markdown_clarification_fields(raw_text)
                    except RuntimeError as md_err:
                        raise RuntimeError(
                            f"Invalid clarification file: not valid JSON "
                            f"and markdown parsing failed: {md_err}"
                        )
                if not isinstance(raw, dict):
                    raise RuntimeError(
                        f"Clarification file must contain a JSON object "
                        f"or markdown sections, got {type(raw).__name__}"
                    )
                fields.update(raw)
            if parsed.field:
                field_args = _parse_field_args(parsed.field)
                fields.update(field_args)
            result = update_task_clarification(root, parsed.task_id, fields)
        elif parsed.command == "start-verification":
            result = start_verification(root, parsed.task_id)
        elif parsed.command == "promote":
            criteria = parsed.acceptance or ["The formal task package exists and can be executed."]
            result = with_task_selection_next_actions(
                promote_to_task(root, parsed.intake_id, parsed.title, parsed.goal, parsed.type, criteria)
            )
        elif parsed.command == "list-active":
            result = {"tasks": list_unfinished_tasks(root, verbose=getattr(parsed, "verbose", False))}
        elif parsed.command in {"select-task", "resume"}:
            result = with_task_selection_next_actions(select_task(root, parsed.task_id))
        elif parsed.command == "mark":
            result = mark_task(
                root,
                parsed.task_id,
                parsed.status,
                progress=parsed.progress,
                impact=parsed.impact,
                note=parsed.note,
            )
        elif parsed.command == "cleanup-task":
            result = cleanup_completed_task(root, parsed.task_id)
        elif parsed.command == "archive-task":
            result = archive_task(root, parsed.task_id)
        elif parsed.command == "complete-verification":
            result = complete_verification(
                root,
                parsed.task_id,
                parsed.result,
                parsed.summary,
                auto_archive=not parsed.no_auto_archive,
                checkpoint_commit=not parsed.no_checkpoint_commit,
            )
        elif parsed.command == "init":
            result = init_project(root)
            if result.get("status") == "success":
                print(f"✓ {result['message']}")
                print()
                print(f"  Project root: {result['project_root']}")
                print(f"  Scripts deployed: {result.get('scripts_deployed', 0)}")
                print_numstat(result.get("numstat", []))
                print_project_invocation(root)
                print()
            else:
                print(json.dumps(result, ensure_ascii=False))
            return 0 if result.get("status") == "success" else 1
        elif parsed.command == "install":
            if not parsed.opencode or not parsed.global_install:
                result = {"status": "error", "message": "Install requires --opencode --global flags"}
            else:
                config_root = Path(parsed.config_root) if parsed.config_root else None
                result = install_opencode_global(config_root)
                if result.get("status") == "success":
                    print(f"✓ {result['message']}")
                    results = result.get("results", {})
                    print()
                    print(f"  Config root: {result['config_root']}")
                    print(f"  Plugins deployed: {results.get('plugins_deployed', 0)}")
                    print(f"  Agents deployed: {results.get('agents_deployed', 0)}")
                    print(f"  Skills deployed: {results.get('skills_deployed', 0)}")
                    print(f"  Config deployed: {results.get('config_deployed', 0)}")
                    path_entry = results.get("path_entry") or {}
                    if path_entry.get("path"):
                        print(f"  PATH entry: {path_entry.get('path')}")
                    print_numstat(results.get("numstat", []))
                    if results.get("warnings"):
                        print()
                        print("  Warnings:")
                        for warning in results["warnings"]:
                            print(f"    ⚠ {warning}")
                    print()
                else:
                    print(json.dumps(result, ensure_ascii=False))
                return 0 if result.get("status") == "success" else 1
        elif parsed.command == "update":
            if not parsed.opencode or not parsed.global_update:
                result = {"status": "error", "message": "Update requires --opencode --global flags"}
            else:
                config_root = Path(parsed.config_root) if parsed.config_root else None
                result = update_opencode_global(config_root)
                if result.get("status") == "success":
                    print(f"✓ {result['message']}")
                    results = result.get("results", {})
                    print()
                    print(f"  Config root: {result['config_root']}")
                    print(f"  Plugins deployed: {results.get('plugins_deployed', 0)}")
                    print(f"  Agents deployed: {results.get('agents_deployed', 0)}")
                    print(f"  Skills deployed: {results.get('skills_deployed', 0)}")
                    print(f"  Config deployed: {results.get('config_deployed', 0)}")
                    path_entry = results.get("path_entry") or {}
                    if path_entry.get("path"):
                        print(f"  PATH entry: {path_entry.get('path')}")
                    print_numstat(results.get("numstat", []))
                    if results.get("warnings"):
                        print()
                        print("  Warnings:")
                        for warning in results["warnings"]:
                            print(f"    ⚠ {warning}")
                    print()
                else:
                    print(json.dumps(result, ensure_ascii=False))
                return 0 if result.get("status") == "success" else 1
        elif parsed.command == "doctor":
            config_root = Path(parsed.config_root) if parsed.config_root else None
            result = doctor_opencode_global(config_root, root)
            print(json.dumps(result, ensure_ascii=False))
            if isinstance(result, dict) and result.get("project", {}).get("just_demand_dir_exists"):
                print_project_invocation(root, stream=sys.stderr)
            return 0 if (isinstance(result, dict) and result.get("status") != "error") else 1
        elif parsed.command == "where":
            print("global CLI: just-demand")
            print(f"repo root:    {repo_root()}")
            print()
            print("To invoke against a project:")
            print(format_project_invocation(root, "list-active"))
            print("  (omit [project-dir] to use the current directory)")
            print()
            print("To install / update / uninstall globally:")
            print("  just-demand install --opencode --global")
            print("  just-demand update --opencode --global")
            print("  just-demand uninstall --opencode --global")
            return 0
        elif parsed.command == "uninstall":
            if not parsed.opencode or not parsed.global_uninstall:
                result = {"status": "error", "message": "Uninstall requires --opencode --global flags"}
            else:
                config_root = Path(parsed.config_root) if parsed.config_root else None
                result = uninstall_opencode_global(config_root)
        elif parsed.command == "show-readiness":
            result = show_task_readiness(root, parsed.task_id)
        elif parsed.command == "smoke":
            result = run_smoke_checks()
        else:
            raise RuntimeError(f"Unsupported command: {parsed.command}")
    except Exception as exc:
        result = {"status": "error", "message": str(exc)}

    if parsed.command in SUMMARY_COMMANDS:
        print_structured_summary(parsed.command, result, stream=sys.stderr)
    print(json.dumps(result, ensure_ascii=False))
    if isinstance(result, dict):
        if result.get("status") == "success":
            return 0
        elif result.get("status") == "error":
            return 1
        return 0
    return 0


def show_help():
    """Show available commands in interactive mode."""
    print("Available commands:")
    print("  list-active [--verbose]           List unfinished tasks")
    print("  create-intake <title> <request>   Create intake note")
    print("  promote <id> <title> <goal>       Promote intake to task")
    print("  build-packet <id>                Build execution packet for a task")
    print("  render-context <id>              Render role-specific packet markdown")
    print("  lint-packet <id>                 Lint execution packet for a task")
    print("  select-task <id>                  Select current task")
    print("  resume <id>                       Resume/select current task")
    print("  mark <id> <status> [--progress N] Mark task status")
    print("  complete-verification <id> ...    Record verification result")
    print("  checkpoint-commit <id>            Create checkpoint commit")
    print("  archive-task <id>                 Archive completed task")
    print("  cleanup-task <id>                 Clean up completed task")
    print("  update-clarification <id>          Update task clarification fields (JSON or ## markdown file via --from-file)")
    print("  show-readiness <id>                Show task readiness diagnostics and recovery guidance")
    print("  smoke                             Run repo smoke validation checks")
    print("  init                              Initialize project")
    print("  doctor                            Check installation status")
    print("  where                             Print global CLI invocation example")
    print("  help                              Show this help")
    print("  exit / quit                       Exit interactive mode")
    print()


def print_numstat(numstat: list[dict[str, object]]) -> None:
    if not numstat:
        return
    print()
    print("  Diff summary:")
    for entry in numstat:
        additions = entry.get("additions", 0)
        deletions = entry.get("deletions", 0)
        path = entry.get("path", "")
        print(f"    {additions}\t{deletions}\t{path}")


def script_path() -> Path:
    """Return the absolute path of the running task.py script."""
    return Path(__file__).resolve()


def repo_root() -> Path:
    """Return the just-demand source repo root (parent of .just-demand/)."""
    return script_path().parents[2]


def interactive_mode(root: Path):
    """Run in interactive mode."""
    print("Just Demand Task CLI (interactive mode)")
    print(f"Working directory: {root}")
    print("Type 'help' for available commands, 'exit' to quit.")
    print()
    
    while True:
        try:
            line = input("just-demand> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        
        if not line:
            continue
        
        if line in ("exit", "quit"):
            break
        
        if line == "help":
            show_help()
            continue
        
        try:
            args = shlex.split(line)
        except ValueError as e:
            print(f"Error parsing command: {e}")
            continue
        
        execute_command(root, args)


def main() -> int:
    # If no arguments provided, enter interactive mode
    if len(sys.argv) == 1:
        root = Path(".").resolve()
        interactive_mode(root)
        return 0
    
    # Otherwise, parse arguments and execute single command
    project_root_arg, cmd_args = split_project_root(sys.argv[1:])
    root = (project_root_arg or Path(".")).resolve()

    parser = build_parser()
    if not cmd_args:
        parser.print_help()
        return 1
    if cmd_args[0] in GLOBAL_COMMANDS and project_root_arg is not None:
        # Project directories are ignored for global commands.
        pass

    return execute_command(root, cmd_args)


if __name__ == "__main__":
    raise SystemExit(main())
