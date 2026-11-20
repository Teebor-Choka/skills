"""Where the site reads from and writes to. Standard library only.

Every script takes the same options (flags win over the config file, list flags add to it):

  --config FILE        JSON with any of the keys below; relative paths resolve against the file's folder
  --org-root DIR       the workflow skill to draw (manifest.json, workflows/); default: ../workflow beside this skill
  --data-dir DIR       generated data (data/) and the ingest log (ingest/events.jsonl);
                       default: $XDG_STATE_HOME/org-status, else ~/.local/state/org-status
  --ledger GLOB        a run ledger to follow (repeatable)
  --state-dir DIR      an `org.py serve --state DIR` folder: dispatcher.json and ledgers/*.ledger (repeatable)
  --work-package DIR   optional: status-units.json, run-log.md, owner-decisions.md, agent-plans/, findings/, site.json
  --repo OWNER/NAME    GitHub repository for `gh pr list`; default: the org root's origin remote
  --no-gh              do not call gh
  --language-page FILE optional HTML page whose sections the language view shows
  --layout FILE        segments and components; default: assets/org-layout.json
  --ingest FILE        read another ingest log (gen.py only; simulations)
"""

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
ASSETS = SKILL / "assets"
KEYS = {"org_root", "data_dir", "ledgers", "state_dirs", "work_package", "repo", "language_page", "layout"}


class ConfigError(ValueError):
    pass


@dataclass
class Config:
    org_root: Path
    data_dir: Path
    layout: Path
    ledgers: list = field(default_factory=list)
    state_dirs: list = field(default_factory=list)
    work_package: Path = None
    repo: str = None
    language_page: Path = None
    ingest: Path = None

    @property
    def out_dir(self):
        return self.data_dir / "data"

    @property
    def ingest_log(self):
        return self.ingest or self.data_dir / "ingest" / "events.jsonl"


def add_args(ap):
    g = ap.add_argument_group("sources")
    g.add_argument("--config", help="JSON file with org_root, data_dir, ledgers, state_dirs, work_package, repo, language_page, layout")
    g.add_argument("--org-root", help="workflow skill to draw (default: ../workflow beside this skill)")
    g.add_argument("--data-dir", help="generated data and ingest log (default: $XDG_STATE_HOME/org-status)")
    g.add_argument("--ledger", action="append", default=[], help="run ledger file or glob (repeatable)")
    g.add_argument("--state-dir", action="append", default=[], help="org.py serve state folder (repeatable)")
    g.add_argument("--work-package", help="optional folder with status-units.json, run-log.md, owner-decisions.md, site.json")
    g.add_argument("--repo", help="OWNER/NAME for gh pr list (default: the org root's origin)")
    g.add_argument("--no-gh", action="store_true", help="do not call gh")
    g.add_argument("--language-page", help="optional HTML page for the language view")
    g.add_argument("--layout", help="segments and components JSON (default: assets/org-layout.json)")
    g.add_argument("--ingest", help=argparse.SUPPRESS)


def default_data_dir(env):
    xdg = env.get("XDG_STATE_HOME")
    if xdg and os.path.isabs(xdg):
        return Path(xdg) / "org-status"
    home = env.get("HOME") or str(Path.home())
    return Path(home) / ".local" / "state" / "org-status"


def _path(v, base, env):
    if v is None:
        return None
    s = str(v)
    if s.startswith("~"):
        s = (env.get("HOME") or str(Path.home())) + s[1:]
    p = Path(s)
    return p if p.is_absolute() else (base / p)


def repo_of(org_root):
    """OWNER/NAME of the org root's origin remote when it is on GitHub, else None."""
    try:
        p = subprocess.run(["git", "-C", str(org_root), "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$", p.stdout.strip())
    return m.group(1) if p.returncode == 0 and m else None


def resolve(ns, env=None):
    env = os.environ if env is None else env
    file = {}
    base = Path.cwd()
    if ns.config:
        cf = _path(ns.config, Path.cwd(), env)
        try:
            file = json.loads(cf.read_text())
        except (OSError, ValueError) as e:
            raise ConfigError("config %s: %s" % (cf, e))
        if not isinstance(file, dict):
            raise ConfigError("config %s: not a JSON object" % cf)
        extra = set(file) - KEYS
        if extra:
            raise ConfigError("config %s: unknown key %s" % (cf, ", ".join(sorted(extra))))
        base = cf.parent

    def pick(flag, key):
        if flag is not None:
            return _path(flag, Path.cwd(), env)
        return _path(file.get(key), base, env)

    org_root = pick(ns.org_root, "org_root") or SKILL.parent / "workflow"
    if not (org_root / "manifest.json").is_file():
        raise ConfigError("org root %s has no manifest.json; pass --org-root" % org_root)
    wp = pick(ns.work_package, "work_package")
    if wp is not None and not wp.is_dir():
        raise ConfigError("work package %s is not a folder" % wp)
    lp = pick(ns.language_page, "language_page")
    if lp is not None and not lp.is_file():
        raise ConfigError("language page %s is not a file" % lp)
    layout = pick(ns.layout, "layout") or ASSETS / "org-layout.json"
    if not layout.is_file():
        raise ConfigError("layout %s is not a file" % layout)
    lists = {}
    for key, flags in (("ledgers", ns.ledger), ("state_dirs", ns.state_dir)):
        vals = file.get(key) or []
        if not isinstance(vals, list) or not all(isinstance(x, str) for x in vals):
            raise ConfigError("config key %s must be a list of paths" % key)
        lists[key] = [str(_path(x, base, env)) for x in vals] + [str(_path(x, Path.cwd(), env)) for x in flags or []]
    if ns.no_gh:
        repo = None
    else:
        repo = ns.repo or file.get("repo") or repo_of(org_root)
        if repo is not None and not re.match(r"^[\w.-]+/[\w.-]+$", repo):
            raise ConfigError("repo must be OWNER/NAME, got %r" % repo)
    return Config(org_root=org_root.resolve(), data_dir=(pick(ns.data_dir, "data_dir") or default_data_dir(env)).resolve(),
                  layout=layout.resolve(), ledgers=lists["ledgers"], state_dirs=lists["state_dirs"],
                  work_package=wp.resolve() if wp else None, repo=repo, language_page=lp.resolve() if lp else None,
                  ingest=_path(getattr(ns, "ingest", None), Path.cwd(), env))


def to_argv(cfg):
    """Flags that resolve to the same Config, for a child process (serve.py runs gen.py)."""
    argv = ["--org-root", str(cfg.org_root), "--data-dir", str(cfg.data_dir), "--layout", str(cfg.layout)]
    for x in cfg.ledgers:
        argv += ["--ledger", x]
    for x in cfg.state_dirs:
        argv += ["--state-dir", x]
    if cfg.work_package:
        argv += ["--work-package", str(cfg.work_package)]
    if cfg.language_page:
        argv += ["--language-page", str(cfg.language_page)]
    if cfg.ingest:
        argv += ["--ingest", str(cfg.ingest)]
    argv += ["--repo", cfg.repo] if cfg.repo else ["--no-gh"]
    return argv
