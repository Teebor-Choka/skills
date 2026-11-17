import json
import os

import pytest
from layout_kit import git, write
from policy_loader import PolicyError, _split_frontmatter, main, resolve

USER = "---\nwork:\n  tracker: github\nlocked: [work.tracker]\n---\n"


def _repo(tmp_path, project_policy):
    repo = tmp_path / "proj"
    write(repo, ".agents/policy.md", project_policy)
    user = tmp_path / "user.md"
    user.write_text(USER)
    return str(repo), str(user)


def test_a_locked_user_key_is_not_overridden_on_the_loader_read_path(tmp_path):
    repo, user = _repo(tmp_path, "---\nwork:\n  tracker: jira\n---\n")
    assert resolve(repo, global_path=user)["work"]["tracker"] == "github"


def test_a_lock_also_holds_against_per_skill_and_per_file_shadows_in_the_loader(tmp_path):
    repo, user = _repo(tmp_path, "---\nwork:\n  tracker: github\nramble:\n  work:\n    tracker: jira\n---\n")
    got = resolve(repo, global_path=user)
    assert "work" not in got.get("ramble", {})


def test_the_loader_can_report_instead_of_enforce_so_the_resolver_can_error(tmp_path):
    repo, user = _repo(tmp_path, "---\nwork:\n  tracker: jira\n---\n")
    assert resolve(repo, global_path=user, enforce_locks=False)["work"]["tracker"] == "jira"


def test_the_cli_get_prints_the_locked_value(tmp_path, capsys):
    repo, user = _repo(tmp_path, "---\nwork:\n  tracker: jira\n---\n")
    assert main([repo, "--global", user, "--get", "work.tracker"]) == 0
    assert capsys.readouterr().out.strip() == "github"


@pytest.mark.parametrize("sep", ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85", " ", " ", "\x00"])
def test_a_separator_git_does_not_see_is_an_error_not_a_hidden_key(sep):
    with pytest.raises(PolicyError, match="line"):
        _split_frontmatter(f"---\nnote: see docs{sep}procedure: other\n---\n", "p.md")


def test_ordinary_crlf_and_tabs_still_parse():
    assert _split_frontmatter("---\r\nnote:\tvalue\r\n---\r\n", "p.md") is not None


def test_a_lock_also_holds_against_a_per_file_override_in_the_loader(tmp_path):
    repo, user = _repo(tmp_path, '---\nfiles:\n  "*":\n    work:\n      tracker: jira\n---\n')
    got = resolve(repo, global_path=user)
    assert "work" not in got.get("files", {}).get("*", {})
