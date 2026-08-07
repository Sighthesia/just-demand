#!/usr/bin/env python3
"""Create and transition just-demand task contracts."""
import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("JUST_DEMAND_ROOT", Path(__file__).resolve().parents[2])).resolve()
STATE = ROOT / ".just-demand"
TASKS = STATE / "tasks"
SESSIONS = STATE / "runtime" / "sessions"
STATUSES = {"clarifying", "planned", "implementing", "verifying", "awaiting_user", "reflecting", "paused", "completed"}
TRANSITIONS = {
    "clarifying": {"planned", "paused"}, "planned": {"clarifying", "implementing", "paused"},
    "implementing": {"verifying", "paused", "reflecting"}, "verifying": {"implementing", "awaiting_user", "reflecting", "paused"},
    "awaiting_user": {"clarifying", "completed", "paused"}, "reflecting": {"clarifying", "planned", "paused"},
    "paused": {"clarifying", "planned", "implementing", "verifying"}, "completed": set(),
}

def now():
    return datetime.now(timezone.utc).isoformat()

def slug(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return value[:80] or "task"

def load(task):
    path = TASKS / task / "task.json"
    if not path.exists(): raise SystemExit(f"task not found: {task}")
    return path, json.loads(path.read_text())

def save(path, data):
    data["updated_at"] = now()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

def active_conflicts(task, files):
    wanted = set(files)
    conflicts = []
    if not wanted or not SESSIONS.exists(): return conflicts
    for session_file in SESSIONS.glob("*.json"):
        try:
            other = json.loads(session_file.read_text()).get("task")
            if not other or other == task: continue
            _, data = load(other)
            if data["status"] == "completed": continue
            overlap = sorted(wanted.intersection(data.get("files", [])))
            if overlap: conflicts.append({"task": other, "files": overlap})
        except (OSError, ValueError, SystemExit, KeyError):
            continue
    return conflicts

def checkpoint_commit(task, data, task_path):
    scoped = data.get("files", []) + [str(task_path.relative_to(ROOT))]
    if not scoped:
        return {"committed": False, "warning": "no task files declared"}
    subprocess.run(["git", "add", "--", *scoped], cwd=ROOT, check=True)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet", "--", *scoped], cwd=ROOT)
    if staged.returncode == 0:
        return {"committed": False, "warning": "no changes in task scope"}
    subprocess.run(
        ["git", "commit", "--only", "-m", f"checkpoint: {data['title']}", "--", *scoped],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, check=True, text=True, capture_output=True)
    return {"committed": True, "commit": commit.stdout.strip()}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create"); create.add_argument("title"); create.add_argument("--request", required=True); create.add_argument("--expectation", required=True); create.add_argument("--acceptance", required=True); create.add_argument("--files", default="")
    activate = sub.add_parser("activate"); activate.add_argument("task"); activate.add_argument("--session", default=os.getenv("JUST_DEMAND_SESSION_ID", "default"))
    status = sub.add_parser("status"); status.add_argument("task")
    transition = sub.add_parser("transition"); transition.add_argument("task"); transition.add_argument("status", choices=sorted(STATUSES)); transition.add_argument("--note", default="")
    finish = sub.add_parser("finish"); finish.add_argument("task"); finish.add_argument("--no-commit", action="store_true", help="只完成任务，不创建 checkpoint commit")
    args = parser.parse_args()
    TASKS.mkdir(parents=True, exist_ok=True); SESSIONS.mkdir(parents=True, exist_ok=True)
    if args.command == "create":
        name = slug(args.title); directory = TASKS / name
        if directory.exists(): raise SystemExit(f"task already exists: {name}")
        files = [x.strip() for x in args.files.split(",") if x.strip()]
        for file in files:
            candidate = (ROOT / file).resolve()
            if candidate != ROOT and ROOT not in candidate.parents: raise SystemExit(f"file outside project: {file}")
        directory.mkdir(); data = {"title": args.title, "status": "clarifying", "request": args.request, "expectation": args.expectation, "clarifications": [], "files": files, "acceptance": args.acceptance, "progress": "未开始", "notes": [], "feedback": [], "conflicts": active_conflicts(name, files), "created_at": now(), "updated_at": now()}
        save(directory / "task.json", data); print(json.dumps({"task": name, **data}, ensure_ascii=False)); return
    if args.command == "activate":
        _, data = load(args.task); conflicts = active_conflicts(args.task, data.get("files", [])); (SESSIONS / f"{slug(args.session)}.json").write_text(json.dumps({"task": args.task, "conflicts": conflicts, "activated_at": now()}, indent=2) + "\n"); print(json.dumps({"task": args.task, "conflicts": conflicts}, ensure_ascii=False)); return
    path, data = load(args.task)
    if args.command == "status": print(json.dumps({"task": args.task, **data}, ensure_ascii=False)); return
    if args.command == "transition":
        warnings = []
        if args.status != data["status"] and args.status not in TRANSITIONS[data["status"]]:
            warnings.append(f"non-standard transition: {data['status']} -> {args.status}")
        data["status"] = args.status; data["progress"] = args.status
        if args.note: data["notes"].append({"at": now(), "text": args.note})
        save(path, data); print(json.dumps({"task": args.task, "warnings": warnings, **data}, ensure_ascii=False)); return
    if args.command == "finish":
        warnings = []
        if data["status"] != "awaiting_user": warnings.append(f"finishing from {data['status']} without awaiting_user review")
        data["status"] = "completed"; data["progress"] = "完成"; save(path, data)
        checkpoint = {"committed": False, "warning": "commit disabled"} if args.no_commit else checkpoint_commit(args.task, data, path)
        if checkpoint.get("warning"): warnings.append(checkpoint["warning"])
        print(json.dumps({"task": args.task, "warnings": warnings, "checkpoint": checkpoint, **data}, ensure_ascii=False))

if __name__ == "__main__": main()
