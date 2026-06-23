#!/usr/bin/env python3
"""Just Demand global OpenCode installation and project initialization."""
from __future__ import annotations

import json
import difflib
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

# Add the scripts directory to the path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from workflow_core import ensure_workspace

# Default OpenCode config root
DEFAULT_CONFIG_ROOT = Path.home() / ".config" / "opencode"
COMMANDS = {"init", "install", "update", "doctor", "uninstall"}
PATH_ENTRY_NAME = "just-demand.cmd" if os.name == "nt" else "just-demand"

# Files to deploy for global installation
DEPLOYED_FILES = {
    "plugins": [
        "just-demand-lib.js",
        "just-demand-session-start.js",
        "just-demand-state.js",
        "just-demand-subagent-context.js",
    ],
    "agents": [
        "just-demand-advisor.md",
        "just-demand-coder.md",
        "just-demand-researcher.md",
        "just-demand-tester.md",
    ],
    "skills": [
        "capture-lessons",
        "using-just-demand",
        "socratic-clarification",
        "just-demand-execution",
        "just-demand-intake",
        "just-demand-verification",
    ],
    "config": [
        "package.json",
    ],
}

STALE_DEPLOYED_FILES = [
    "agents/just-demand-check.md",
    "agents/just-demand-docs.md",
    "agents/just-demand-implement.md",
    "agents/just-demand-research.md",
]

# Manifest file to track managed files
MANIFEST_FILE = ".just-demand-manifest.json"


def get_repo_root() -> Path:
    """Get the repository root directory."""
    return Path(__file__).resolve().parents[2]


def get_repo_opencode_dir() -> Path:
    """Get the .opencode directory in the repository."""
    return get_repo_root() / ".opencode"


def get_config_root(config_root: Optional[Path] = None) -> Path:
    """Get the OpenCode config root, using provided or default."""
    return config_root or DEFAULT_CONFIG_ROOT


def get_preferred_bin_dir() -> Path:
    """Get a user-writable bin directory for the PATH shim."""
    xdg_bin = os.environ.get("XDG_BIN_HOME")
    if xdg_bin:
        return Path(xdg_bin).expanduser()
    if os.name == "nt":
        return Path.home() / "bin"
    return Path.home() / ".local" / "bin"


def find_path_bin_dir() -> tuple[Path, bool]:
    """Find a writable directory already on PATH, or fall back to a standard bin dir."""
    path_dirs: list[Path] = []
    for raw in os.environ.get("PATH", "").split(os.pathsep):
        if not raw:
            continue
        candidate = Path(raw).expanduser()
        if candidate.is_dir():
            path_dirs.append(candidate)

    for candidate in path_dirs:
        if os.access(candidate, os.W_OK | os.X_OK):
            return candidate, True

    fallback = get_preferred_bin_dir()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback, fallback in path_dirs


def build_path_entry_content(repo_root: Path) -> str:
    """Render the executable shim that forwards to the repository entrypoint."""
    entry = (repo_root / "just-demand").resolve()
    if os.name == "nt":
        repo_root_cmd = str(repo_root.resolve()).replace("/", "\\")
        entry_cmd = str(entry).replace("/", "\\")
        return "\r\n".join(
            [
                "@echo off",
                "setlocal",
                f"set \"JUST_DEMAND_REPO_ROOT={repo_root_cmd}\"",
                f'"{sys.executable}" "{entry_cmd}" %*',
                "",
            ]
        )

    return "\n".join(
        [
            "#!/bin/sh",
            "# just-demand PATH entry",
            f'exec "{entry}" "$@"',
            "",
        ]
    )


def deploy_path_entry(repo_root: Path, manifest: dict[str, Any], config_root: Path) -> tuple[bool, Optional[str], dict[str, Any]]:
    """Create or refresh the PATH-visible just-demand shim."""
    bin_dir, on_path = find_path_bin_dir()
    target = bin_dir / PATH_ENTRY_NAME
    content = build_path_entry_content(repo_root)
    previous_entry = manifest.get("path_entry")
    existing_text = target.read_text(encoding="utf-8") if target.exists() else None

    if target.exists() and existing_text != content and not (
        isinstance(previous_entry, dict) and previous_entry.get("path") == str(target)
    ):
        return False, f"Skipped existing unmanaged PATH entry: {target}", None

    target.parent.mkdir(parents=True, exist_ok=True)
    if existing_text != content:
        target.write_text(content, encoding="utf-8")
        if os.name != "nt":
            target.chmod(0o755)

    manifest["path_entry"] = {
        "path": str(target),
        "source": str((repo_root / "just-demand").resolve()),
        "on_path": on_path,
    }
    return existing_text != content, None, {
        "path": str(target),
        "on_path": on_path,
        "created": existing_text != content,
    }


def remove_path_entry(manifest: dict[str, Any]) -> Optional[str]:
    """Remove the PATH-visible just-demand shim if we manage one."""
    path_entry = manifest.get("path_entry")
    if not isinstance(path_entry, dict):
        return None

    target = Path(path_entry.get("path", ""))
    if target.exists():
        target.unlink()
        return str(target)
    return str(target)


def line_numstat(before: Optional[str], after: str) -> tuple[int, int]:
    """Count line additions and deletions between two text versions."""
    matcher = difflib.SequenceMatcher(a=[] if before is None else before.splitlines(), b=after.splitlines())
    additions = 0
    deletions = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            additions += j2 - j1
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "replace":
            additions += j2 - j1
            deletions += i2 - i1
    return additions, deletions


def make_numstat(path: str, additions: int, deletions: int) -> dict[str, Any]:
    return {"path": path, "additions": additions, "deletions": deletions}


def prune_manifest_entries(manifest: dict[str, Any]) -> dict[str, Any]:
    """Drop stale legacy workflow records that no longer belong to this runtime."""
    installed_files = manifest.get("installed_files")
    if not isinstance(installed_files, dict):
        manifest["installed_files"] = {}
        return manifest

    manifest["installed_files"] = {
        path: info
        for path, info in installed_files.items()
        if not (
            path.startswith("agents/workflow-") or
            path.startswith("skills/workflow-")
        )
    }
    return manifest


def load_manifest(config_root: Path) -> dict[str, Any]:
    """Load the installation manifest."""
    manifest_path = config_root / MANIFEST_FILE
    if not manifest_path.exists():
        return {"installed_files": {}, "version": "1.0"}
    try:
        return prune_manifest_entries(json.loads(manifest_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return {"installed_files": {}, "version": "1.0"}


def save_manifest(config_root: Path, manifest: dict[str, Any]) -> None:
    """Save the installation manifest."""
    manifest_path = config_root / MANIFEST_FILE
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = prune_manifest_entries(manifest)
    encoded = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    manifest_path.write_text(encoded, encoding="utf-8")


def deploy_file(source: Path, target: Path, manifest: dict[str, Any], config_root: Path) -> tuple[bool, Optional[dict[str, Any]]]:
    """Deploy a file from source to target, tracking in manifest.
    
    Returns True if file was actually copied (new or updated).
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")
    
    target.parent.mkdir(parents=True, exist_ok=True)
    before_text = target.read_text(encoding="utf-8") if target.exists() else None
    after_text = source.read_text(encoding="utf-8")
    
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
            return False, None
    
    shutil.copy2(str(source), str(target))
    try:
        relative_target = str(target.relative_to(config_root))
    except ValueError:
        relative_target = str(target)
    manifest["installed_files"][relative_target] = {
        "source": str(source),
        "checksum": str(source.stat().st_mtime),
    }
    additions, deletions = line_numstat(before_text, after_text)
    return True, make_numstat(relative_target, additions, deletions)


def deploy_config_file(source: Path, target: Path, manifest: dict[str, Any], config_root: Path) -> tuple[bool, Optional[str], Optional[dict[str, Any]]]:
    """Deploy a config file without taking ownership of an existing user file."""
    relative_target = str(target.relative_to(config_root))
    managed_files = manifest.setdefault("installed_files", {})

    if target.name == "package.json" and target.exists() and relative_target not in managed_files:
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            desired = json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False, f"Skipped existing unmanaged config file: {relative_target}", None

        merged = dict(existing)
        changed = False
        for key, value in desired.items():
            if key != "type":
                continue
            if merged.get(key) != value:
                merged[key] = value
                changed = True

        if not changed:
            return False, None, None

        before_text = target.read_text(encoding="utf-8")
        after_text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
        target.write_text(after_text, encoding="utf-8")
        existing_entry = managed_files.get(relative_target, {})
        managed_files[relative_target] = {
            "source": str(source),
            "checksum": str(source.stat().st_mtime),
            "preserve_on_uninstall": existing_entry.get("preserve_on_uninstall", True),
        }
        additions, deletions = line_numstat(before_text, after_text)
        return True, None, make_numstat(relative_target, additions, deletions)

    if target.exists() and relative_target not in managed_files:
        return False, f"Skipped existing unmanaged config file: {relative_target}", None

    copied, entry = deploy_file(source, target, manifest, config_root)
    return copied, None, entry


def remove_stale_deployed_files(config_root: Path, manifest: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]], list[str]]:
    """Remove managed files that no longer belong to the active role surface."""
    installed_files = manifest.setdefault("installed_files", {})
    removed: list[str] = []
    numstat: list[dict[str, Any]] = []
    warnings: list[str] = []

    for relative_path in STALE_DEPLOYED_FILES:
        info = installed_files.get(relative_path)
        if not isinstance(info, dict):
            continue
        if info.get("preserve_on_uninstall"):
            continue
        target = config_root / relative_path
        try:
            removed_lines = len(target.read_text(encoding="utf-8").splitlines()) if target.exists() else 0
            if target.exists():
                target.unlink()
                removed.append(relative_path)
                numstat.append(make_numstat(relative_path, 0, removed_lines))
            installed_files.pop(relative_path, None)
        except OSError as exc:
            warnings.append(f"Failed to remove stale managed file {relative_path}: {exc}")

    return removed, numstat, warnings


def deploy_directory(source_dir: Path, target_dir: Path, manifest: dict[str, Any], config_root: Path, exclude: list[str] | None = None) -> tuple[int, list[dict[str, Any]]]:
    """Deploy all files from source directory to target directory.
    
    Returns number of files actually copied.
    """
    exclude = exclude or []
    copied_count = 0
    numstat_entries: list[dict[str, Any]] = []
    
    if not source_dir.exists():
        return copied_count, numstat_entries
    
    for item in source_dir.iterdir():
        if item.name in exclude:
            continue
        
        if item.is_file():
            target_file = target_dir / item.name
            copied, entry = deploy_file(item, target_file, manifest, config_root)
            if copied:
                copied_count += 1
                if entry:
                    numstat_entries.append(entry)
        elif item.is_dir():
            target_subdir = target_dir / item.name
            child_count, child_entries = deploy_directory(item, target_subdir, manifest, config_root, exclude)
            copied_count += child_count
            numstat_entries.extend(child_entries)
    
    return copied_count, numstat_entries


def sync_public_skills(project_root: Path, force: bool = False) -> dict[str, Any]:
    """Mirror runtime skills into the public .agents/skills surface.

    The runtime source remains .opencode/skills; .agents/skills is a readable
    mirror for agent-neutral reference. Existing public files are preserved
    unless force is explicitly requested.
    """
    source_dir = project_root / ".opencode" / "skills"
    target_dir = project_root / ".agents" / "skills"

    result = {
        "source_exists": source_dir.exists(),
        "target_created": False,
        "files_copied": 0,
        "skipped_existing": [],
    }

    if not source_dir.exists():
        return result

    for source in source_dir.rglob("*"):
        if source.is_dir():
            continue
        relative = source.relative_to(source_dir)
        target = target_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not force:
            result["skipped_existing"].append(str(relative))
            continue
        shutil.copy2(source, target)
        result["files_copied"] += 1
        result["target_created"] = True

    return result


def install_opencode_global(config_root: Optional[Path] = None) -> dict[str, Any]:
    """Install Just Demand OpenCode runtime assets globally.
    
    Returns installation result.
    """
    config_root = get_config_root(config_root)
    repo_root = get_repo_root()
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
        "numstat": [],
        "warnings": [],
        "stale_removed": [],
    }

    stale_removed, stale_stats, stale_warnings = remove_stale_deployed_files(config_root, manifest)
    results["stale_removed"].extend(stale_removed)
    results["numstat"].extend(stale_stats)
    results["warnings"].extend(stale_warnings)

    # Deploy plugins
    plugins_dir = repo_opencode / "plugins"
    target_plugins = config_root / "plugins"
    results["plugins_deployed"], plugin_stats = deploy_directory(plugins_dir, target_plugins, manifest, config_root)
    results["numstat"].extend(plugin_stats)
    
    # Deploy agents
    agents_dir = repo_opencode / "agent"
    target_agents = config_root / "agents"  # Use agents (plural) for global
    results["agents_deployed"], agent_stats = deploy_directory(agents_dir, target_agents, manifest, config_root)
    results["numstat"].extend(agent_stats)
    
    # Deploy skills
    skills_dir = repo_opencode / "skills"
    target_skills = config_root / "skills"
    results["skills_deployed"], skill_stats = deploy_directory(skills_dir, target_skills, manifest, config_root)
    results["numstat"].extend(skill_stats)
    
    # Deploy config files (package.json)
    config_dir = repo_opencode
    for config_file in DEPLOYED_FILES.get("config", []):
        source = config_dir / config_file
        if source.exists():
            target = config_root / config_file
            copied, warning, entry = deploy_config_file(source, target, manifest, config_root)
            if copied:
                results["config_deployed"] += 1
            if entry:
                results["numstat"].append(entry)
            if warning:
                results["warnings"].append(warning)

    # Deploy a persistent PATH-visible entry for the CLI wrapper.
    path_entry_created, path_entry_warning, path_entry = deploy_path_entry(repo_root, manifest, config_root)
    results["path_entry"] = path_entry
    results["path_entry_created"] = path_entry_created
    if path_entry_warning:
        results["warnings"].append(path_entry_warning)

    results["total_deployed"] = (
        results["plugins_deployed"] +
        results["agents_deployed"] +
        results["skills_deployed"] +
        results["config_deployed"]
    )
    
    save_manifest(config_root, manifest)

    path_entry_path = path_entry.get("path") if isinstance(path_entry, dict) else None
    
    return {
        "status": "success",
        "config_root": str(config_root),
        "results": results,
        "message": (
            f"Installed {results['total_deployed']} files to {config_root}"
            + (f" and PATH entry at {path_entry_path}" if path_entry_path else "")
        ),
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
        if file_info.get("preserve_on_uninstall"):
            continue
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

    path_entry_path = remove_path_entry(manifest)
    if path_entry_path:
        removed_files.append(path_entry_path)
    
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
        "path_entry_removed": path_entry_path,
        "errors": errors,
        "message": (
            f"Removed {len(removed_files)} files from {config_root}"
            + (f" and PATH entry at {path_entry_path}" if path_entry_path else "")
        ),
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
        "workspace_state_exists": (project_root / ".just-demand" / "state" / "state.json").exists(),
        "active_tasks_count": 0,
    }
    
    if project_status["workspace_state_exists"]:
        try:
            state_path = project_root / ".just-demand" / "state" / "state.json"
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


def migrate_workspace(project_root: Path) -> dict[str, Any]:
    """Migrate workspace structure to latest layout.
    
    Handles:
    - Creating state/ directory
    - Moving state files from workspace/ to state/
    - Moving tasks from tasks/ to state/
    - Preserving legacy knowledge files without routing normal workflow through memory.md
    - Updating .gitignore with correct entries
    
    Returns migration result with details of what was migrated.
    """
    workflow_root = project_root / ".just-demand"
    old_workspace_dir = workflow_root / "workspace"
    old_tasks_dir = workflow_root / "tasks"
    state_dir = workflow_root / "state"
    knowledge_dir = workflow_root / "knowledge"
    
    result = {
        "state_dir_created": False,
        "files_moved": [],
        "knowledge_merged": False,
        "gitignore_updated": False,
    }
    
    # 1. Create state directory if it doesn't exist
    if not state_dir.exists():
        state_dir.mkdir(parents=True, exist_ok=True)
        result["state_dir_created"] = True
    
    # Ensure state subdirectories exist
    for subdir in ["active", "archive", "intake", "sessions"]:
        (state_dir / subdir).mkdir(parents=True, exist_ok=True)
    
    # 2. Move state files from workspace/ to state/ if old workspace exists
    if old_workspace_dir.exists():
        state_files = ["state.json", "events.jsonl", "locks.json"]
        for filename in state_files:
            source = old_workspace_dir / filename
            target = state_dir / filename
            if source.exists() and not target.exists():
                shutil.move(str(source), str(target))
                result["files_moved"].append(filename)
        
        # Move intake and sessions directories
        for dirname in ["intake", "sessions"]:
            source = old_workspace_dir / dirname
            target = state_dir / dirname
            if source.exists():
                if target.exists():
                    # Merge contents
                    for item in source.iterdir():
                        item_target = target / item.name
                        if not item_target.exists():
                            shutil.move(str(item), str(item_target))
                            result["files_moved"].append(f"{dirname}/{item.name}")
                else:
                    shutil.move(str(source), str(target))
                    result["files_moved"].append(dirname + "/")
        
        # Remove old workspace directory if empty
        try:
            if old_workspace_dir.exists() and not any(old_workspace_dir.iterdir()):
                old_workspace_dir.rmdir()
        except OSError:
            pass
    
    # 3. Move tasks from tasks/ to state/ if old tasks dir exists
    if old_tasks_dir.exists():
        for subdir_name in ["active", "archive"]:
            source_subdir = old_tasks_dir / subdir_name
            target_subdir = state_dir / subdir_name
            if source_subdir.exists():
                for item in source_subdir.iterdir():
                    item_target = target_subdir / item.name
                    if not item_target.exists():
                        shutil.move(str(item), str(item_target))
                        result["files_moved"].append(f"tasks/{subdir_name}/{item.name}")
        
        # Remove old tasks directory if empty
        try:
            if old_tasks_dir.exists() and not any(old_tasks_dir.iterdir()):
                old_tasks_dir.rmdir()
        except OSError:
            pass
    
    # 4. Preserve legacy knowledge files if old files exist
    if knowledge_dir.exists():
        old_knowledge_files = [
            "decisions.md",
            "deferred_options.md",
            "facts.md",
            "open_questions.md",
            "preferences.md",
        ]
        has_old_files = any((knowledge_dir / f).exists() for f in old_knowledge_files)

        if has_old_files:
            # Keep legacy files intact so archival history remains available.
            result["knowledge_merged"] = False
    
    # 5. Remove old global directory if it exists
    old_global_dir = workflow_root / "global"
    if old_global_dir.exists():
        try:
            shutil.rmtree(old_global_dir)
        except OSError:
            pass
    
    # 6. Update .gitignore
    gitignore_path = project_root / ".gitignore"
    gitignore_entries = [
        "# Workflow runtime state (ignore all runtime state)",
        ".just-demand/state/",
        "",
        "# Auto-generated placeholder files",
    ]
    gitignore_content = "\n".join(gitignore_entries) + "\n"
    
    if gitignore_path.exists():
        existing_content = gitignore_path.read_text(encoding="utf-8")
        # Check if old entries need updating
        has_old_entries = ".just-demand/workspace/" in existing_content or ".just-demand/tasks/" in existing_content
        has_new_entries = ".just-demand/state/" in existing_content
        
        if has_old_entries or not has_new_entries:
            # Replace old entries with new ones
            import re
            # Remove old just-demand entries
            existing_content = re.sub(
                r"\n?# Workflow runtime state.*?\n\.just-demand/(?:workspace|tasks)/[^\n]*\n?",
                "\n",
                existing_content,
            )
            existing_content = re.sub(
                r"\n?# Auto-generated placeholder files\n\.just-demand/global/[^\n]*\n(?:\.just-demand/global/[^\n]*\n)?",
                "\n",
                existing_content,
            )
            # Add new entries
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


def sync_workspace(project_root: Path) -> dict[str, Any]:
    """Sync workspace directory structure with the latest layout.

    The current layout keeps only project state and knowledge locally.
    Legacy script copies are removed, state directories are created, and old
    workspace/task directories are migrated into the current state layout.
    """
    workflow_root = project_root / ".just-demand"
    repo_root = get_repo_root()
    
    # Check if this is the repo itself (don't delete repo scripts)
    is_repo = project_root.resolve() == repo_root.resolve()
    
    result = {
        "scripts_synced": 0,
        "legacy_removed": [],
        "state_created": False,
        "gitignore_updated": False,
        "numstat": [],
    }
    
    # 1. Remove legacy scripts/ directory contents from older layouts
    if not is_repo:
        scripts_dir = workflow_root / "scripts"
        if scripts_dir.exists():
            for old_file in ["task.py", "install.py", "workflow_core.py"]:
                old_path = scripts_dir / old_file
                if old_path.exists():
                    removed_lines = len(old_path.read_text(encoding="utf-8").splitlines())
                    old_path.unlink()
                    result["legacy_removed"].append(f"scripts/{old_file}")
                    result["numstat"].append(make_numstat(f".just-demand/scripts/{old_file}", 0, removed_lines))
            try:
                if not any(scripts_dir.iterdir()):
                    scripts_dir.rmdir()
            except OSError:
                pass

    # 2. Create state/ directory structure
    state_dir = workflow_root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    
    for subdir in ["active", "archive", "intake", "sessions"]:
        (state_dir / subdir).mkdir(parents=True, exist_ok=True)
    
    # Create state files if missing
    state_json = state_dir / "state.json"
    if not state_json.exists():
        from workflow_core import default_workspace_state, write_json_atomic
        write_json_atomic(state_json, default_workspace_state())
        result["state_created"] = True
    
    for filename, default_content in [("events.jsonl", ""), ("locks.json", '{"schema_version": "1.0", "locks": []}\n')]:
        target = state_dir / filename
        if not target.exists():
            target.write_text(default_content, encoding="utf-8")
            result["state_created"] = True
    
    # 3. Remove legacy directories (only in project workspaces, not repo)
    if not is_repo:
        legacy_dirs = ["global", "workspace", "tasks"]
        for dirname in legacy_dirs:
            legacy_dir = workflow_root / dirname
            if legacy_dir.exists():
                try:
                    shutil.rmtree(str(legacy_dir))
                    result["legacy_removed"].append(dirname)
                except Exception:
                    pass
    
    # 4. Update .gitignore
    gitignore_path = project_root / ".gitignore"
    gitignore_entries = [
        "# Workflow runtime state (ignore all runtime state)",
        ".just-demand/state/",
    ]
    gitignore_content = "\n".join(gitignore_entries) + "\n"
    
    if gitignore_path.exists():
        existing_content = gitignore_path.read_text(encoding="utf-8")
        # Check if our entries already exist
        if ".just-demand/state/" in existing_content:
            # Already has our entries, no update needed
            result["gitignore_updated"] = False
        else:
            # Remove old entries
            import re
            existing_content = re.sub(
                r"\n?# (?:Workflow runtime state and task files|Workflow runtime state \(ignore all runtime state\)|Auto-generated placeholder files)\n\.just-demand/[^\n]*\n(?:\.just-demand/[^\n]*\n)*",
                "\n",
                existing_content,
            )
            # Add new entries
            if not existing_content.endswith("\n"):
                existing_content += "\n"
            existing_content += "\n" + gitignore_content
            gitignore_path.write_text(existing_content, encoding="utf-8")
            result["gitignore_updated"] = True
    else:
        gitignore_path.write_text(gitignore_content, encoding="utf-8")
        result["gitignore_updated"] = True
    
    result["updated"] = (
        result["scripts_synced"] > 0 or
        result["legacy_removed"] or
        result["state_created"] or
        result["gitignore_updated"]
    )
    
    return result
def init_project(project_root: Optional[Path] = None) -> dict[str, Any]:
    """Initialize project-local .just-demand state.
    
    Returns initialization result.
    """
    project_root = project_root or Path.cwd()
    
    try:
        ensure_workspace(project_root)
        skills_sync = sync_public_skills(project_root)
        sync_result = sync_workspace(project_root)
        return {
            "status": "success",
            "project_root": str(project_root),
            "just_demand_dir": str(project_root / ".just-demand"),
            "public_skills_synced": skills_sync["files_copied"],
            "scripts_synced": sync_result["scripts_synced"],
            "legacy_removed": sync_result["legacy_removed"],
            "numstat": sync_result["numstat"],
            "message": (
                f"Initialized project workspace in {project_root / '.just-demand'}; "
                "stored local state only, mirrored public skills into .agents/skills, "
                "and removed the need for workspace-local workflow scripts"
            ),
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
    
    parser = argparse.ArgumentParser(
        description="Just Demand installation and initialization tools",
        epilog="Use: just-demand [project-dir] <command> ...",
    )
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

    # doctor command
    doctor_parser = sub.add_parser("doctor", help="Report installation and activation status")
    
    # uninstall command
    uninstall_parser = sub.add_parser("uninstall", help="Remove global Just Demand installation")
    uninstall_parser.add_argument("--opencode", action="store_true", help="Uninstall OpenCode runtime assets")
    uninstall_parser.add_argument("--global", action="store_true", dest="global_uninstall", help="Uninstall global installation")
    
    return parser


def split_project_root(argv: list[str]) -> tuple[Path | None, list[str]]:
    """Split an optional leading project directory from command arguments."""
    if len(argv) >= 2 and argv[0] not in COMMANDS and not argv[0].startswith("-") and argv[1] in COMMANDS:
        return Path(argv[0]), argv[1:]
    return None, argv


def main() -> int:
    """Main entry point for install CLI."""
    project_root_arg, cmd_args = split_project_root(sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args(cmd_args)
    
    config_root = Path(args.config_root) if args.config_root else None
    project_root = (project_root_arg or Path(".")).resolve()
    
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
