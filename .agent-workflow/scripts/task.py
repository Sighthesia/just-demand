#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_core import cleanup_completed_task, create_intake, list_unfinished_tasks, promote_to_task


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

    sub.add_parser("list-active", help="List all unfinished formal tasks")

    cleanup = sub.add_parser("cleanup-task", help="Clean up a completed task and remove its runtime references")
    cleanup.add_argument("task_id", help="Task ID to clean up (must be status 'done')")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).resolve()
    if args.command == "create-intake":
        result = create_intake(root, args.title, args.raw_request, args.session)
    elif args.command == "promote":
        criteria = args.acceptance or ["The formal task package exists and can be executed."]
        result = promote_to_task(root, args.intake_id, args.title, args.goal, args.type, criteria)
    elif args.command == "list-active":
        result = {"tasks": list_unfinished_tasks(root)}
    elif args.command == "cleanup-task":
        result = cleanup_completed_task(root, args.task_id)
    else:
        raise RuntimeError(f"Unsupported command: {args.command}")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
