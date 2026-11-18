"""Helpers: a project repo and a user config directory, built for real in a temp dir."""
import os
from pathlib import Path

from layout_kit import PROC, commit, git, has, write  # noqa: F401
from resolver import ResolutionError, main as resolve_main, resolve, start_run  # noqa: F401

# A procedure that declares the policy keys it needs, and a stage that uses two of them.
BOUND = PROC.replace(
    "kpis:",
    "policy:\n  comms.channel: how nodes talk to each other\n  report.sink: where reports go\nkpis:",
    1,
).replace(
    "    metrics: [briefs-per-week]\n  create:",
    "    metrics: [briefs-per-week]\n    uses: [comms.channel, report.sink]\n  create:",
    1,
)
SPECIFICS = "---\nprocedure: campaign-ops\ncomms:\n  channel: slack:#campaigns\nreport:\n  sink: issues\n---\n"
OWNER_CHARTER = "---\nowner:\n  channel: chat\n  answer-path: signed reply\n---\n"


def env_for(tmp_path, files=None, name="cfg"):
    """A user config directory under `tmp_path`, and the environment that points at it."""
    root = Path(tmp_path) / name
    for rel, text in (files or {}).items():
        write(root / "agents", rel, text)
    return {"XDG_CONFIG_HOME": str(root), "HOME": str(Path(tmp_path) / "home")}


def project(tmp_path, files=None, *, git_repo=True, name="proj"):
    """A project directory holding exactly `files` (relative to its root), committed unless asked not to."""
    root = Path(tmp_path) / name
    root.mkdir(parents=True, exist_ok=True)
    for rel, text in (files or {}).items():
        write(root, rel, text)
    if git_repo:
        git(root, "init", "-q", "-b", "main")
        write(root, ".gitignore", ".agents/runs/\n")
        commit(root, "initial")
    return root


def agents(files):
    return {f".agents/{rel}": text for rel, text in files.items()}


def ok(result):
    assert result is not None and result["errors"] == [], result
    return result
