#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_core import (
    archive_task,
    cleanup_completed_task,
    complete_verification,
    create_intake,
    list_unfinished_tasks,
    mark_task,
    promote_to_task,
)
from install import (
    sync_initialized_workspaces,
    init_project,
    install_opencode_global,
    update_opencode_global,
    doctor_opencode_global,
    uninstall_opencode_global,
)


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

    list_active = sub.add_parser("list-active", help="List all unfinished formal tasks")
    list_active.add_argument("--verbose", action="store_true", help="Include current_step and path")

    mark = sub.add_parser("mark", help="Mark task status, progress, impact, and note")
    mark.add_argument("task_id", help="Task ID to mark")
    mark.add_argument("status", help="New status (planning,executing,verifying,changes_requested,blocked,paused,tweaking,debugging)")
    mark.add_argument("--progress", type=int, default=None, help="Progress 0-100")
    mark.add_argument("--impact", action="append", default=None, help="Affected path/module (repeatable)")
    mark.add_argument("--note", default=None, help="Short note for current state")

    cleanup = sub.add_parser("cleanup-task", help="Clean up a completed task and remove its runtime references")
    cleanup.add_argument("task_id", help="Task ID to clean up (must be status 'done')")

    archive = sub.add_parser("archive-task", help="Archive a completed task to tasks/archive/")
    archive.add_argument("task_id", help="Task ID to archive (must be status 'done')")

    complete = sub.add_parser("complete-verification", help="Record verification result and optionally create a checkpoint commit")
    complete.add_argument("task_id", help="Task ID to complete verification for")
    complete.add_argument("result", choices=["passed", "failed", "blocked"])
    complete.add_argument("summary", help="Short verification summary")
    complete.add_argument("--no-auto-archive", action="store_true", help="Keep passed task active instead of archiving it")
    complete.add_argument("--no-checkpoint-commit", action="store_true", help="Skip automatic checkpoint commit on passed verification")

    # Installation commands
    init = sub.add_parser("init", help="Initialize project-local .just-demand state")
    
    install = sub.add_parser("install", help="Install Just Demand globally for OpenCode")
    install.add_argument("--opencode", action="store_true", help="Install OpenCode runtime assets")
    install.add_argument("--global", action="store_true", dest="global_install", help="Install globally")
    install.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")
    
    update = sub.add_parser("update", help="Update existing global installation")
    update.add_argument("--opencode", action="store_true", help="Update OpenCode runtime assets")
    update.add_argument("--global", action="store_true", dest="global_update", help="Update global installation")
    update.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")

    sync = sub.add_parser("sync-workspaces", help="Refresh local workflow scripts in initialized workspaces")
    sync.add_argument("--search-root", action="append", default=None, help="Directory tree to scan for initialized workspaces (repeatable, default: current directory)")
    
    doctor = sub.add_parser("doctor", help="Report installation and activation status")
    doctor.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")
    
    uninstall = sub.add_parser("uninstall", help="Remove global Just Demand installation")
    uninstall.add_argument("--opencode", action="store_true", help="Uninstall OpenCode runtime assets")
    uninstall.add_argument("--global", action="store_true", dest="global_uninstall", help="Uninstall global installation")
    uninstall.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    
    try:
        if args.command == "create-intake":
            result = create_intake(root, args.title, args.raw_request, args.session)
        elif args.command == "promote":
            criteria = args.acceptance or ["The formal task package exists and can be executed."]
            result = promote_to_task(root, args.intake_id, args.title, args.goal, args.type, criteria)
        elif args.command == "list-active":
            result = {"tasks": list_unfinished_tasks(root, verbose=getattr(args, "verbose", False))}
        elif args.command == "mark":
            result = mark_task(
                root,
                args.task_id,
                args.status,
                progress=args.progress,
                impact=args.impact,
                note=args.note,
            )
        elif args.command == "cleanup-task":
            result = cleanup_completed_task(root, args.task_id)
        elif args.command == "archive-task":
            result = archive_task(root, args.task_id)
        elif args.command == "complete-verification":
            result = complete_verification(
                root,
                args.task_id,
                args.result,
                args.summary,
                auto_archive=not args.no_auto_archive,
                checkpoint_commit=not args.no_checkpoint_commit,
            )
        elif args.command == "init":
            result = init_project(root)
        elif args.command == "install":
            if not args.opencode or not args.global_install:
                result = {"status": "error", "message": "Install requires --opencode --global flags"}
            else:
                config_root = Path(args.config_root) if args.config_root else None
                result = install_opencode_global(config_root)
        elif args.command == "update":
            if not args.opencode or not args.global_update:
                result = {"status": "error", "message": "Update requires --opencode --global flags"}
            else:
                config_root = Path(args.config_root) if args.config_root else None
                result = update_opencode_global(config_root)
        elif args.command == "sync-workspaces":
            search_roots = [Path(path) for path in args.search_root] if args.search_root else None
            result = sync_initialized_workspaces(search_roots)
        elif args.command == "doctor":
            config_root = Path(args.config_root) if args.config_root else None
            result = doctor_opencode_global(config_root, root)
        elif args.command == "uninstall":
            if not args.opencode or not args.global_uninstall:
                result = {"status": "error", "message": "Uninstall requires --opencode --global flags"}
            else:
                config_root = Path(args.config_root) if args.config_root else None
                result = uninstall_opencode_global(config_root)
        else:
            raise RuntimeError(f"Unsupported command: {args.command}")
    except Exception as exc:
        result = {"status": "error", "message": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    # Return 0 for success, 1 for error status
    if isinstance(result, dict):
        if result.get("status") == "success":
            return 0
        elif result.get("status") == "error":
            return 1
        # For other results (task operations), assume success
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
