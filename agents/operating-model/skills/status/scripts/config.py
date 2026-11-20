"""Where the site reads from and writes to. Placeholder with the snapshot's built-in locations."""

from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    pass


def add_args(ap):
    for flag in ("--config", "--org-root", "--data-dir", "--work-package", "--repo", "--language-page", "--layout", "--ingest"):
        ap.add_argument(flag)
    ap.add_argument("--ledger", action="append", default=[])
    ap.add_argument("--state-dir", action="append", default=[])
    ap.add_argument("--no-gh", action="store_true")


class Config:
    def __init__(self):
        self.org_root = Path.home() / "Fun/my.fun/skills/.claude/worktrees/w3base/agents/operating-model/skills/workflow"
        self.data_dir = SKILL
        self.out_dir = SKILL / "data"
        self.ingest_log = SKILL / "ingest" / "events.jsonl"
        self.work_package = SKILL.parent / "work-package"
        self.ledgers, self.state_dirs = [], []
        self.repo = "Teebor-Choka/skills"


def resolve(ns, env=None):
    return Config()


def to_argv(cfg):
    return []
