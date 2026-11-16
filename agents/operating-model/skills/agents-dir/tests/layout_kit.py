"""Helpers: build a real temporary git repo with a `.agents/` directory."""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from agents_dir import check_agents_dir, main, process_revision  # noqa: E402,F401

PROC = (SKILLS / "procedure" / "assets" / "example-campaign-ops.md").read_text()
POLICY = "---\nmode: single\nprocedure: campaign-ops\n---\n"
CHARTER = (
    "---\nowner:\n  channel: chat\n  answer-path: signed reply\nprocedure: campaign-ops\n"
    "triggers:\n  quarter-start: campaign-ops\n---\nThe standing agreement.\n"
)
ITER = (
    "---\nchange:\n  reason: tighten review\n  metrics: [creative-rework]\n  direction: down\n"
    "  window: 3 stages\ntouches: [procedures/campaign-ops.md]\noutcome: pending\n---\nWhy.\n"
)


def has(errors, word):
    return any(word in e for e in errors)


def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def write(repo, rel, text):
    path = Path(repo) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def commit(repo, message="change"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def make_repo(tmp_path, *, files=None, ignore_runs=True):
    """A git repo with a valid `.agents/` and one commit. `files` overrides or adds paths."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    layout = {
        ".agents/policy.md": POLICY,
        ".agents/charter.md": CHARTER,
        ".agents/procedures/campaign-ops.md": PROC,
        ".agents/iterations/0001-initial.md": ITER,
    }
    layout.update(files or {})
    if ignore_runs:
        layout[".gitignore"] = ".agents/runs/\n"
    for rel, text in layout.items():
        if text is not None:
            write(repo, rel, text)
    commit(repo, "initial")
    return repo
