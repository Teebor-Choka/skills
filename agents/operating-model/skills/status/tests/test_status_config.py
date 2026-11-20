"""Portability: where the site reads from and writes to, with no home, session or scratchpad path built in."""

import argparse
import json
import re

import pytest

from status_testlib import ORG_ROOT, SKILL, load


def resolve(argv, env):
    config = load("config")
    ap = argparse.ArgumentParser()
    config.add_args(ap)
    return config.resolve(ap.parse_args(argv), env=env)


def test_data_dir_defaults_to_xdg_state_home(tmp_path):
    cfg = resolve([], {"XDG_STATE_HOME": str(tmp_path / "state"), "HOME": str(tmp_path / "home")})
    assert cfg.data_dir == tmp_path / "state" / "org-status"
    assert cfg.out_dir == tmp_path / "state" / "org-status" / "data"
    assert cfg.ingest_log == tmp_path / "state" / "org-status" / "ingest" / "events.jsonl"


def test_data_dir_falls_back_to_local_state_under_home(tmp_path):
    cfg = resolve([], {"HOME": str(tmp_path)})
    assert cfg.data_dir == tmp_path / ".local" / "state" / "org-status"
    assert SKILL not in cfg.data_dir.parents


def test_org_root_defaults_to_the_sibling_workflow_skill(tmp_path):
    cfg = resolve([], {"HOME": str(tmp_path)})
    assert cfg.org_root == ORG_ROOT
    assert (cfg.org_root / "manifest.json").is_file()


def test_work_package_and_live_sources_are_optional(tmp_path):
    cfg = resolve([], {"HOME": str(tmp_path)})
    assert cfg.work_package is None
    assert cfg.ledgers == [] and cfg.state_dirs == []


def test_org_root_without_a_manifest_is_refused(tmp_path):
    config = load("config")
    with pytest.raises(config.ConfigError, match="manifest.json"):
        resolve(["--org-root", str(tmp_path)], {"HOME": str(tmp_path)})


def test_missing_work_package_is_refused(tmp_path):
    config = load("config")
    with pytest.raises(config.ConfigError, match="work package"):
        resolve(["--work-package", str(tmp_path / "nope")], {"HOME": str(tmp_path)})


def test_config_file_paths_resolve_against_the_file_and_flags_win(tmp_path):
    (tmp_path / "wp").mkdir()
    cfgfile = tmp_path / "status.json"
    cfgfile.write_text(json.dumps({"data_dir": "site-state", "work_package": "wp", "ledgers": ["runs/*.ledger"],
                                   "state_dirs": ["org-state"], "repo": "owner/name"}))
    cfg = resolve(["--config", str(cfgfile), "--ledger", "/abs/x.ledger", "--repo", "other/repo"], {"HOME": str(tmp_path)})
    assert cfg.data_dir == tmp_path / "site-state"
    assert cfg.work_package == tmp_path / "wp"
    assert cfg.ledgers == [str(tmp_path / "runs/*.ledger"), "/abs/x.ledger"]
    assert cfg.state_dirs == [str(tmp_path / "org-state")]
    assert cfg.repo == "other/repo"


def test_unknown_config_key_is_refused(tmp_path):
    config = load("config")
    cfgfile = tmp_path / "status.json"
    cfgfile.write_text(json.dumps({"ledger": ["typo"]}))
    with pytest.raises(config.ConfigError, match="unknown key"):
        resolve(["--config", str(cfgfile)], {"HOME": str(tmp_path)})


def test_no_gh_disables_the_pull_request_source(tmp_path):
    cfg = resolve(["--no-gh", "--repo", "owner/name"], {"HOME": str(tmp_path)})
    assert cfg.repo is None


def test_round_trip_to_argv(tmp_path):
    config = load("config")
    cfg = resolve(["--data-dir", str(tmp_path), "--ledger", "/a.ledger", "--state-dir", "/s", "--no-gh"], {"HOME": str(tmp_path)})
    again = resolve(config.to_argv(cfg), {"HOME": "/elsewhere"})
    assert again == cfg


BUILT_IN = re.compile(r"/Users/|/home/[a-z]|/private/tmp|claude-501|scratchpad|~/Fun|Path\.home\(\) / \"Fun")


def test_no_source_names_a_home_session_or_scratchpad_path():
    hits = []
    for p in SKILL.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".js", ".html", ".css", ".md", ".json") and "__pycache__" not in p.parts:
            if p.name == "test_status_config.py":
                continue
            for i, line in enumerate(p.read_text().splitlines(), 1):
                if BUILT_IN.search(line):
                    hits.append("%s:%d: %s" % (p.relative_to(SKILL), i, line.strip()[:100]))
    assert hits == []
