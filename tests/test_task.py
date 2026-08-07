import json
import subprocess
import tempfile
import os
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / ".just-demand/scripts/task.py"

def run(cwd, *args):
    env = {**os.environ, "JUST_DEMAND_ROOT": str(cwd)}
    return subprocess.run(["python3", str(SCRIPT), *args], cwd=cwd, env=env, text=True, capture_output=True, check=True)

def init_git(root):
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    (root / "README.md").write_text("base\n")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)

def test_lifecycle_and_json():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"; root.mkdir()
        result = json.loads(run(root, "create", "Demo task", "--request", "raw", "--expectation", "visible", "--acceptance", "check").stdout)
        assert result["status"] == "clarifying"
        task = result["task"]
        run(root, "activate", task, "--session", "s1")
        assert json.loads(run(root, "status", task).stdout)["title"] == "Demo task"
        assert json.loads(run(root, "transition", task, "planned").stdout)["status"] == "planned"

def test_warns_on_non_standard_transition_and_rejects_external_file():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"; root.mkdir()
        bad_file = subprocess.run(["python3", str(SCRIPT), "create", "Bad", "--request", "r", "--expectation", "e", "--acceptance", "a", "--files", "../outside"], cwd=root, env={**os.environ, "JUST_DEMAND_ROOT": str(root)}, text=True, capture_output=True)
        assert bad_file.returncode != 0
        task = json.loads(run(root, "create", "Valid", "--request", "r", "--expectation", "e", "--acceptance", "a").stdout)["task"]
        transition = json.loads(run(root, "transition", task, "completed").stdout)
        assert transition["status"] == "completed"
        assert transition["warnings"] == ["non-standard transition: clarifying -> completed"]

def test_activation_reports_concurrent_file_conflicts_without_blocking():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"; root.mkdir()
        first = json.loads(run(root, "create", "First", "--request", "r", "--expectation", "e", "--acceptance", "a", "--files", "src/shared.js").stdout)["task"]
        second = json.loads(run(root, "create", "Second", "--request", "r", "--expectation", "e", "--acceptance", "a", "--files", "src/shared.js").stdout)["task"]
        run(root, "activate", first, "--session", "one")
        result = json.loads(run(root, "activate", second, "--session", "two").stdout)
        assert result["conflicts"] == [{"task": first, "files": ["src/shared.js"]}]

def test_finish_creates_scoped_checkpoint_by_default():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "repo"; root.mkdir(); init_git(root)
        (root / "feature.txt").write_text("feature\n")
        (root / "unrelated.txt").write_text("keep outside checkpoint\n")
        task = json.loads(run(root, "create", "Checkpoint", "--request", "r", "--expectation", "e", "--acceptance", "a", "--files", "feature.txt").stdout)["task"]
        result = json.loads(run(root, "finish", task).stdout)
        assert result["checkpoint"]["committed"] is True
        committed = subprocess.run(["git", "show", "--format=", "--name-only", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout
        assert "feature.txt" in committed
        assert ".just-demand/tasks/checkpoint/task.json" in committed
        assert "unrelated.txt" not in committed
        assert (root / "unrelated.txt").exists()
