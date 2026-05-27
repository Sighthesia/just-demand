#!/usr/bin/env python3
"""Just Demand global OpenCode installation and project initialization."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

# Add the scripts directory to the path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_core import ensure_workspace

# Default OpenCode config root
DEFAULT_CONFIG_ROOT = Path.home() / ".config" / "opencode"

# Files to deploy for global installation
DEPLOYED_FILES = {
    "plugins": [
        "just-demand-lib.js",
        "just-demand-session-start.js",
        "just-demand-state.js",
        "just-demand-subagent-context.js",
    ],
    "agents": [
        "just-demand-check.md",
        "just-demand-docs.md",
        "just-demand-implement.md",
        "just-demand-research.md",
    ],
    "skills": [
        "using-just-demand",
        "socratic-clarification",
        "just-demand-execution",
        "just-demand-intake",
        "just-demand-memory",
        "just-demand-verification",
    ],
    "config": [
        "package.json",
    ],
}

# Manifest file to track managed files
MANIFEST_FILE = ".just-demand-manifest.json"


def get_repo_root() -> Path:
    """Get the repository root directory."""
    return Path(__file__).resolve().parents[2]


def get_repo_opencode_dir() -> Path:
    """Get the .opencode directory in the repository."""
    return get_repo_root() / ".opencode"


def get_repo_scripts_dir() -> Path:
    """Get the project-local workflow scripts directory in the repository."""
    return get_repo_root() / ".just-demand" / "scripts"


def get_config_root(config_root: Optional[Path] = None) -> Path:
    """Get the OpenCode config root, using provided or default."""
    return config_root or DEFAULT_CONFIG_ROOT


def load_manifest(config_root: Path) -> dict[str, Any]:
    """Load the installation manifest."""
    manifest_path = config_root / MANIFEST_FILE
    if not manifest_path.exists():
        return {"installed_files": {}, "version": "1.0"}
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"installed_files": {}, "version": "1.0"}


def save_manifest(config_root: Path, manifest: dict[str, Any]) -> None:
    """Save the installation manifest."""
    manifest_path = config_root / MANIFEST_FILE
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    manifest_path.write_text(encoded, encoding="utf-8")


def deploy_file(source: Path, target: Path, manifest: dict[str, Any], config_root: Path) -> bool:
    """Deploy a file from source to target, tracking in manifest.
    
    Returns True if file was actually copied (new or updated).
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    
    target.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if file needs updating
    if target.exists():
        if source.read_bytes() == target.read_bytes():
            # File already up to date
            try:
                relative_target = str(target.relative_to(config_root))
            except ValueError:
                relative_target = str(target)
            manifest["installed_files"][relative_target] = {
                "source": str(source),
                "checksum": str(source.stat().st_mtime),
            }
            return False
    
    shutil.copy2(str(source), str(target))
    try:
        relative_target = str(target.relative_to(config_root))
    except ValueError:
        relative_target = str(target)
    manifest["installed_files"][relative_target] = {
        "source": str(source),
        "checksum": str(source.stat().st_mtime),
    }
    return True


def deploy_config_file(source: Path, target: Path, manifest: dict[str, Any], config_root: Path) -> tuple[bool, Optional[str]]:
    """Deploy a config file without taking ownership of an existing user file."""
    relative_target = str(target.relative_to(config_root))
    managed_files = manifest.setdefault("installed_files", {})

    if target.exists() and relative_target not in managed_files:
        return False, f"Skipped existing unmanaged config file: {relative_target}"

    return deploy_file(source, target, manifest, config_root), None


def deploy_directory(source_dir: Path, target_dir: Path, manifest: dict[str, Any], config_root: Path, exclude: list[str] | None = None) -> int:
    """Deploy all files from source directory to target directory.
    
    Returns number of files actually copied.
    """
    exclude = exclude or []
    copied_count = 0
    
    if not source_dir.exists():
        return copied_count
    
    for item in source_dir.iterdir():
        if item.name in exclude:
            continue
        
        if item.is_file():
            target_file = target_dir / item.name
            if deploy_file(item, target_file, manifest, config_root):
                copied_count += 1
        elif item.is_dir():
            target_subdir = target_dir / item.name
            copied_count += deploy_directory(item, target_subdir, manifest, config_root, exclude)
    
    return copied_count


def install_opencode_global(config_root: Optional[Path] = None) -> dict[str, Any]:
    """Install Just Demand OpenCode runtime assets globally.
    
    Returns installation result.
    """
    config_root = get_config_root(config_root)
    repo_opencode = get_repo_opencode_dir()
    
    manifest = load_manifest(config_root)
    manifest["version"] = "1.0"
    manifest["installed_at"] = str(Path(__file__).resolve())
    
    results = {
        "plugins_deployed": 0,
        "agents_deployed": 0,
        "skills_deployed": 0,
        "config_deployed": 0,
        "total_deployed": 0,
        "warnings": [],
    }
    
    # Deploy plugins
    plugins_dir = repo_opencode / "plugins"
    target_plugins = config_root / "plugins"
    results["plugins_deployed"] = deploy_directory(plugins_dir, target_plugins, manifest, config_root)
    
    # Deploy agents
    agents_dir = repo_opencode / "agent"
    target_agents = config_root / "agents"  # Use agents (plural) for global
    results["agents_deployed"] = deploy_directory(agents_dir, target_agents, manifest, config_root)
    
    # Deploy skills
    skills_dir = repo_opencode / "skills"
    target_skills = config_root / "skills"
    results["skills_deployed"] = deploy_directory(skills_dir, target_skills, manifest, config_root)
    
    # Deploy config files (package.json)
    config_dir = repo_opencode
    for config_file in DEPLOYED_FILES.get("config", []):
        source = config_dir / config_file
        if source.exists():
            target = config_root / config_file
            copied, warning = deploy_config_file(source, target, manifest, config_root)
            if copied:
                results["config_deployed"] += 1
            if warning:
                results["warnings"].append(warning)
    
    results["total_deployed"] = (
        results["plugins_deployed"] +
        results["agents_deployed"] +
        results["skills_deployed"] +
        results["config_deployed"]
    )
    
    save_manifest(config_root, manifest)
    
    return {
        "status": "success",
        "config_root": str(config_root),
        "results": results,
        "message": f"Installed {results['total_deployed']} files to {config_root}",
    }


def update_opencode_global(config_root: Optional[Path] = None) -> dict[str, Any]:
    """Update an existing global installation with current runtime assets.
    
    Returns update result.
    """
    # Update is essentially a reinstall that only copies changed files
    return install_opencode_global(config_root)


def uninstall_opencode_global(config_root: Optional[Path] = None) -> dict[str, Any]:
    """Remove only Just Demand-managed global install files.
    
    Returns uninstall result.
    """
    config_root = get_config_root(config_root)
    manifest = load_manifest(config_root)
    
    removed_files = []
    errors = []
    
    for file_path, file_info in manifest.get("installed_files", {}).items():
        full_path = config_root / file_path
        try:
            if full_path.exists():
                # For directories, check if empty after removal
                if full_path.is_dir():
                    # Only remove if empty
                    if not any(full_path.iterdir()):
                        full_path.rmdir()
                        removed_files.append(file_path)
                else:
                    full_path.unlink()
                    removed_files.append(file_path)
        except OSError as e:
            errors.append(f"Failed to remove {file_path}: {e}")
    
    # Remove manifest file
    manifest_path = config_root / MANIFEST_FILE
    if manifest_path.exists():
        try:
            manifest_path.unlink()
            removed_files.append(MANIFEST_FILE)
        except OSError as e:
            errors.append(f"Failed to remove manifest: {e}")
    
    # Clean up empty directories (but not the root config directory)
    dirs_to_check = ["plugins", "agents", "skills"]
    for dir_name in dirs_to_check:
        dir_path = config_root / dir_name
        if dir_path.exists() and dir_path.is_dir():
            try:
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    removed_files.append(dir_name + "/")
            except OSError:
                pass
    
    return {
        "status": "success" if not errors else "partial",
        "config_root": str(config_root),
        "removed_files": removed_files,
        "errors": errors,
        "message": f"Removed {len(removed_files)} files from {config_root}",
    }


def doctor_opencode_global(config_root: Optional[Path] = None, project_root: Optional[Path] = None) -> dict[str, Any]:
    """Report global install status and current project activation status.
    
    Returns diagnostic information.
    """
    config_root = get_config_root(config_root)
    project_root = project_root or Path.cwd()
    
    # Check global installation
    manifest = load_manifest(config_root)
    installed_files = manifest.get("installed_files", {})
    
    global_status = {
        "config_root": str(config_root),
        "manifest_exists": (config_root / MANIFEST_FILE).exists(),
        "installed_files_count": len(installed_files),
        "plugins_present": [],
        "agents_present": [],
        "skills_present": [],
    }
    
    # Check which files are actually present
    for file_path in installed_files:
        full_path = config_root / file_path
        if file_path.startswith("plugins/"):
            global_status["plugins_present"].append({
                "file": file_path,
                "present": full_path.exists(),
            })
        elif file_path.startswith("agents/"):
            global_status["agents_present"].append({
                "file": file_path,
                "present": full_path.exists(),
            })
        elif file_path.startswith("skills/"):
            global_status["skills_present"].append({
                "file": file_path,
                "present": full_path.exists(),
            })
    
    # Check project activation
    project_status = {
        "project_root": str(project_root),
        "just_demand_dir_exists": (project_root / ".just-demand").exists(),
        "workspace_state_exists": (project_root / ".just-demand" / "workspace" / "state.json").exists(),
        "active_tasks_count": 0,
    }
    
    if project_status["workspace_state_exists"]:
        try:
            state_path = project_root / ".just-demand" / "workspace" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            project_status["active_tasks_count"] = len(state.get("active_task_ids", []))
            project_status["current_task_id"] = state.get("current_task_id")
        except (json.JSONDecodeError, OSError):
            pass
    
    return {
        "global": global_status,
        "project": project_status,
        "healthy": (
            global_status["manifest_exists"] and
            global_status["installed_files_count"] > 0 and
            project_status["just_demand_dir_exists"]
        ),
    }


def sync_project_scripts(project_root: Path) -> int:
    """Copy the repo's project-local workflow scripts into a workspace.

    `init` is the workspace-level sync entrypoint, so rerunning it refreshes any
    managed script copies from the currently invoked repository checkout.
    """
    workflow_root = project_root / ".just-demand"
    source_scripts = get_repo_scripts_dir()
    target_scripts = workflow_root / "scripts"
    manifest = {"installed_files": {}, "version": "1.0"}
    return deploy_directory(source_scripts, target_scripts, manifest, workflow_root, exclude=["__pycache__"])


def migrate_workspace(project_root: Path) -> dict[str, Any]:
    """Migrate workspace structure to latest layout.
    
    Handles:
    - Creating knowledge/ directory
    - Moving knowledge files from workspace/ to knowledge/
    - Updating .gitignore with correct entries
    
    Returns migration result with details of what was migrated.
    """
    workflow_root = project_root / ".just-demand"
    workspace_dir = workflow_root / "workspace"
    knowledge_dir = workflow_root / "knowledge"
    
    result = {
        "knowledge_dir_created": False,
        "files_moved": [],
        "gitignore_updated": False,
    }
    
    # 1. Create knowledge directory if it doesn't exist
    if not knowledge_dir.exists():
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        result["knowledge_dir_created"] = True
    
    # 2. Move knowledge files from workspace/ to knowledge/ if they exist
    knowledge_files = [
        "decisions.md",
        "deferred_options.md",
        "facts.md",
        "open_questions.md",
        "preferences.md",
    ]
    
    for filename in knowledge_files:
        source = workspace_dir / filename
        target = knowledge_dir / filename
        if source.exists() and not target.exists():
            shutil.move(str(source), str(target))
            result["files_moved"].append(filename)
    
    # 3. Update .gitignore
    gitignore_path = project_root / ".gitignore"
    gitignore_entries = [
        "# Workflow runtime state and task files",
        ".just-demand/tasks/",
        ".just-demand/workspace/",
        "",
        "# Auto-generated placeholder files",
        ".just-demand/global/architecture.md",
        ".just-demand/global/glossary.md",
    ]
    gitignore_content = "\n".join(gitignore_entries) + "\n"
    
    if gitignore_path.exists():
        existing_content = gitignore_path.read_text(encoding="utf-8")
        # Check if .just-demand/workspace/ is already in .gitignore
        if ".just-demand/workspace/" not in existing_content:
            # Append just-demand entries
            if not existing_content.endswith("\n"):
                existing_content += "\n"
            existing_content += "\n" + gitignore_content
            gitignore_path.write_text(existing_content, encoding="utf-8")
            result["gitignore_updated"] = True
    else:
        # Create new .gitignore
        gitignore_path.write_text(gitignore_content, encoding="utf-8")
        result["gitignore_updated"] = True
    
    return result


def discover_initialized_workspaces(search_root: Path) -> list[Path]:
    """Find initialized project roots beneath a search root."""
    resolved_root = search_root.resolve()
    if not resolved_root.exists():
        raise FileNotFoundError(f"Search root not found: {resolved_root}")

    discovered: set[Path] = set()
    for state_path in resolved_root.rglob(".just-demand/workspace/state.json"):
        discovered.add(state_path.parents[2].resolve())
    return sorted(discovered)


def sync_initialized_workspaces(search_roots: Optional[list[Path]] = None) -> dict[str, Any]:
    """Refresh local workflow scripts for all initialized workspaces under search roots."""
    roots = search_roots or [Path.cwd()]
    resolved_search_roots = [root.resolve() for root in roots]
    workspaces: list[dict[str, Any]] = []
    seen_projects: set[Path] = set()

    for search_root in resolved_search_roots:
        for project_root in discover_initialized_workspaces(search_root):
            if project_root in seen_projects:
                continue
            seen_projects.add(project_root)
            scripts_deployed = sync_project_scripts(project_root)
            migration = migrate_workspace(project_root)
            workspaces.append(
                {
                    "project_root": str(project_root),
                    "scripts_deployed": scripts_deployed,
                    "files_moved": migration["files_moved"],
                    "gitignore_updated": migration["gitignore_updated"],
                    "updated": scripts_deployed > 0 or migration["files_moved"] or migration["gitignore_updated"],
                }
            )

    total_scripts_deployed = sum(item["scripts_deployed"] for item in workspaces)
    updated_count = sum(1 for item in workspaces if item["updated"])
    return {
        "status": "success",
        "search_roots": [str(root) for root in resolved_search_roots],
        "workspaces_found": len(workspaces),
        "workspaces_updated": updated_count,
        "total_scripts_deployed": total_scripts_deployed,
        "workspaces": workspaces,
        "message": f"Synchronized local workflow scripts in {updated_count} of {len(workspaces)} initialized workspaces",
    }


def init_project(project_root: Optional[Path] = None) -> dict[str, Any]:
    """Initialize project-local .just-demand state.
    
    Returns initialization result.
    """
    project_root = project_root or Path.cwd()
    
    try:
        ensure_workspace(project_root)
        scripts_deployed = sync_project_scripts(project_root)
        return {
            "status": "success",
            "project_root": str(project_root),
            "just_demand_dir": str(project_root / ".just-demand"),
            "scripts_deployed": scripts_deployed,
            "message": f"Initialized project workspace in {project_root / '.just-demand'} and synchronized local workflow scripts",
        }
    except Exception as e:
        return {
            "status": "error",
            "project_root": str(project_root),
            "message": f"Failed to initialize project: {e}",
            "error": str(e),
        }


def build_parser() -> Any:
    """Build argument parser for install CLI."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Just Demand installation and initialization tools")
    parser.add_argument("--root", default=".", help="Project root (for project commands)")
    parser.add_argument("--config-root", default=None, help="OpenCode config root (default: ~/.config/opencode)")
    
    sub = parser.add_subparsers(dest="command", required=True)
    
    # init command
    init_parser = sub.add_parser("init", help="Initialize project-local .just-demand state")
    
    # install command
    install_parser = sub.add_parser("install", help="Install Just Demand globally for OpenCode")
    install_parser.add_argument("--opencode", action="store_true", help="Install OpenCode runtime assets")
    install_parser.add_argument("--global", action="store_true", dest="global_install", help="Install globally")
    
    # update command
    update_parser = sub.add_parser("update", help="Update existing global installation")
    update_parser.add_argument("--opencode", action="store_true", help="Update OpenCode runtime assets")
    update_parser.add_argument("--global", action="store_true", dest="global_update", help="Update global installation")

    sync_parser = sub.add_parser("sync-workspaces", help="Refresh local workflow scripts in initialized workspaces")
    sync_parser.add_argument("--search-root", action="append", default=None, help="Directory tree to scan for initialized workspaces (repeatable, default: current directory)")
    
    # doctor command
    doctor_parser = sub.add_parser("doctor", help="Report installation and activation status")
    
    # uninstall command
    uninstall_parser = sub.add_parser("uninstall", help="Remove global Just Demand installation")
    uninstall_parser.add_argument("--opencode", action="store_true", help="Uninstall OpenCode runtime assets")
    uninstall_parser.add_argument("--global", action="store_true", dest="global_uninstall", help="Uninstall global installation")
    
    return parser


def main() -> int:
    """Main entry point for install CLI."""
    parser = build_parser()
    args = parser.parse_args()
    
    config_root = Path(args.config_root) if args.config_root else None
    project_root = Path(args.root).resolve()
    
    if args.command == "init":
        result = init_project(project_root)
    elif args.command == "install":
        if not args.opencode or not args.global_install:
            result = {"status": "error", "message": "Install requires --opencode --global flags"}
        else:
            result = install_opencode_global(config_root)
    elif args.command == "update":
        if not args.opencode or not args.global_update:
            result = {"status": "error", "message": "Update requires --opencode --global flags"}
        else:
            result = update_opencode_global(config_root)
    elif args.command == "sync-workspaces":
        search_roots = [Path(path) for path in args.search_root] if args.search_root else None
        result = sync_initialized_workspaces(search_roots)
    elif args.command == "doctor":
        result = doctor_opencode_global(config_root, project_root)
    elif args.command == "uninstall":
        if not args.opencode or not args.global_uninstall:
            result = {"status": "error", "message": "Uninstall requires --opencode --global flags"}
        else:
            result = uninstall_opencode_global(config_root)
    else:
        result = {"status": "error", "message": f"Unknown command: {args.command}"}
    
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
