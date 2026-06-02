#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_core import (
    archive_task,
    cleanup_completed_task,
    complete_verification,
    create_checkpoint_commit,
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


def invocation_hint(project_root: Path, command: str = "<cmd>") -> str:
    """Return a one-line invocation example for the given project root."""
    return f"  python3 {script_path()} --root {project_root} {command}"


def print_invocation_hint(project_root: Path, stream=None) -> None:
    """Print a 'how to invoke' hint to the given stream (default stdout)."""
    out = stream if stream is not None else sys.stdout
    out.write("\nProject invocation:\n")
    out.write(invocation_hint(project_root, "list-active") + "\n")
    out.write(f"  python3 {script_path()} where           # to find this script's path\n")


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

    checkpoint = sub.add_parser("checkpoint-commit", help="Create a checkpoint commit for a task (requires passed verification)")
    checkpoint.add_argument("task_id", help="Task ID to create a checkpoint commit for")

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
    uninstall.add_argument("--global", action="store_true", dest="global_uninstall", help="Uninstall globally")
    uninstall.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")

    where = sub.add_parser("where", help="Print the path of this task.py and a one-line invocation example")
    where.add_argument("--project", default=None, help="Optional project root to include in the invocation example")

    return parser


def execute_command(root: Path, args: list[str]) -> int:
    """Execute a single command with the given arguments."""
    try:
        parsed = build_parser().parse_args(args)
    except SystemExit:
        return 1
    
    try:
        if parsed.command == "create-intake":
            result = create_intake(root, parsed.title, parsed.raw_request, parsed.session)
        elif parsed.command == "checkpoint-commit":
            result = create_checkpoint_commit(root, parsed.task_id)
        elif parsed.command == "promote":
            criteria = parsed.acceptance or ["The formal task package exists and can be executed."]
            result = promote_to_task(root, parsed.intake_id, parsed.title, parsed.goal, parsed.type, criteria)
        elif parsed.command == "list-active":
            result = {"tasks": list_unfinished_tasks(root, verbose=getattr(parsed, "verbose", False))}
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
            # Format human-readable output for init
            if result.get("status") == "success":
                print(f"✓ {result['message']}")
                print()
                print(f"  Project root: {result['project_root']}")
                print(f"  Scripts deployed: {result.get('scripts_deployed', 0)}")
                print_numstat(result.get("numstat", []))
                print_invocation_hint(root)
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
                # Format human-readable output for install
                if result.get("status") == "success":
                    print(f"✓ {result['message']}")
                    results = result.get("results", {})
                    print()
                    print(f"  Config root: {result['config_root']}")
                    print(f"  Plugins deployed: {results.get('plugins_deployed', 0)}")
                    print(f"  Agents deployed: {results.get('agents_deployed', 0)}")
                    print(f"  Skills deployed: {results.get('skills_deployed', 0)}")
                    print(f"  Config deployed: {results.get('config_deployed', 0)}")
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
                # Format human-readable output for update
                if result.get("status") == "success":
                    print(f"✓ {result['message']}")
                    results = result.get("results", {})
                    print()
                    print(f"  Config root: {result['config_root']}")
                    print(f"  Plugins deployed: {results.get('plugins_deployed', 0)}")
                    print(f"  Agents deployed: {results.get('agents_deployed', 0)}")
                    print(f"  Skills deployed: {results.get('skills_deployed', 0)}")
                    print(f"  Config deployed: {results.get('config_deployed', 0)}")
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
        elif parsed.command == "sync-workspaces":
            # First update global installation to ensure latest scripts/plugins
            print("Updating global installation...")
            update_result = update_opencode_global()
            if update_result.get("status") == "success":
                results = update_result.get("results", {})
                total = results.get("total_deployed", 0)
                if total > 0:
                    print(f"✓ Updated {total} global files")
                else:
                    print("· Global installation already current")
                print_numstat(results.get("numstat", []))
                if results.get("warnings"):
                    for warning in results["warnings"]:
                        print(f"  ⚠ {warning}")
            else:
                print(f"⚠ Global update failed: {update_result.get('message', 'Unknown error')}")
            print()
            
            # Then sync workspaces
            search_roots = [Path(path) for path in parsed.search_root] if parsed.search_root else None
            result = sync_initialized_workspaces(search_roots)
            # Format human-readable output for sync-workspaces
            if result.get("status") == "success":
                print(f"✓ {result['message']}  (workflow {result['workflow_version']})")
                print()
                for ws in result["workspaces"]:
                    status = "✓ updated" if ws["updated"] else "· current"
                    details = []
                    if ws["scripts_synced"] > 0:
                        details.append(f"{ws['scripts_synced']} scripts")
                    if ws["legacy_removed"]:
                        details.append(f"removed: {', '.join(ws['legacy_removed'])}")
                    if ws["state_created"]:
                        details.append("state initialized")
                    if ws["gitignore_updated"]:
                        details.append("gitignore updated")
                    detail_str = f" ({', '.join(details)})" if details else ""
                    # Shorten path for readability
                    path = ws["project_root"]
                    try:
                        path = str(Path(path).relative_to(root))
                    except ValueError:
                        pass
                    print(f"  {status}{detail_str}  {path}")
                print_numstat(result.get("numstat", []))
                print()
            else:
                print(json.dumps(result, ensure_ascii=False))
            return 0 if result.get("status") == "success" else 1
        elif parsed.command == "doctor":
            config_root = Path(parsed.config_root) if parsed.config_root else None
            result = doctor_opencode_global(config_root, root)
            print(json.dumps(result, ensure_ascii=False))
            if isinstance(result, dict) and result.get("project", {}).get("just_demand_dir_exists"):
                print_invocation_hint(root, stream=sys.stderr)
            return 0 if (isinstance(result, dict) and result.get("status") != "error") else 1
        elif parsed.command == "where":
            target = Path(parsed.project).resolve() if parsed.project else None
            print(f"task.py path: {script_path()}")
            print(f"repo root:    {repo_root()}")
            if target is not None:
                print()
                print("To invoke against the project:")
                print(invocation_hint(target, "list-active"))
            else:
                print()
                print("To invoke against any project:")
                print(f"  python3 {script_path()} --root <project> <cmd>")
                print()
                print("Run with --project <path> to see a project-specific example.")
            return 0
        elif parsed.command == "uninstall":
            if not parsed.opencode or not parsed.global_uninstall:
                result = {"status": "error", "message": "Uninstall requires --opencode --global flags"}
            else:
                config_root = Path(parsed.config_root) if parsed.config_root else None
                result = uninstall_opencode_global(config_root)
        else:
            raise RuntimeError(f"Unsupported command: {parsed.command}")
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


def show_help():
    """Show available commands in interactive mode."""
    print("Available commands:")
    print("  list-active [--verbose]           List unfinished tasks")
    print("  create-intake <title> <request>   Create intake note")
    print("  promote <id> <title> <goal>       Promote intake to task")
    print("  mark <id> <status> [--progress N] Mark task status")
    print("  complete-verification <id> ...    Record verification result")
    print("  checkpoint-commit <id>            Create checkpoint commit")
    print("  archive-task <id>                 Archive completed task")
    print("  cleanup-task <id>                 Clean up completed task")
    print("  init                              Initialize project")
    print("  sync-workspaces                   Sync workflow scripts")
    print("  doctor                            Check installation status")
    print("  where [--project <path>]          Print task.py path and invocation example")
    print("  help                              Show this help")
    print("  exit / quit                       Exit interactive mode")
    print()


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
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()
    
    # Reconstruct command args (without --root) for execute_command
    cmd_args = []
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--root":
            i += 2  # Skip --root and its value
            continue
        elif arg.startswith("--root="):
            i += 1  # Skip --root=value
            continue
        cmd_args.append(arg)
        i += 1
    
    return execute_command(root, cmd_args)


if __name__ == "__main__":
    raise SystemExit(main())
