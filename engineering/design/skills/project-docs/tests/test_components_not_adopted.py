"""Tests for the `components-not-adopted` rule (spec AT-30): a repo that resolves to two or more
components and has no docs/components/ is flagged, unless `docs.components.adopt` is false."""

import shutil
import subprocess
import sys

import validate_docs  # noqa: E402  (path wired in conftest.py)
from helpers import cargo_member, cargo_workspace, policy, write, write_page

SCRIPT = validate_docs.__file__


def rules(repo) -> list[str]:
    return [f.rule for f in validate_docs.validate_project(repo)]


def two_crates(make_repo):
    repo = make_repo()
    cargo_workspace(repo)
    cargo_member(repo, "a")
    cargo_member(repo, "b", deps=("a",))
    return repo


def test_two_components_without_components_dir_are_flagged(make_repo):
    repo = two_crates(make_repo)
    found = [f for f in validate_docs.validate_project(repo) if f.rule == "components-not-adopted"]
    assert len(found) == 1
    assert found[0].file == "docs/components"
    assert "a" in found[0].message and "b" in found[0].message
    assert "docs.components.adopt" in found[0].message


def test_adopt_false_silences_the_rule(make_repo):
    repo = two_crates(make_repo)
    policy(repo, "docs:\n  components:\n    adopt: false")
    assert rules(repo) == []


def test_adopt_true_or_other_value_still_flags(make_repo):
    repo = two_crates(make_repo)
    policy(repo, "docs:\n  components:\n    adopt: true")
    assert rules(repo) == ["components-not-adopted"]


def test_single_component_is_not_flagged(make_repo):
    repo = make_repo()
    write(repo, "Cargo.toml", '[package]\nname = "widgetd"\n')
    assert rules(repo) == []


def test_exclude_leaving_one_component_is_not_flagged(make_repo):
    repo = two_crates(make_repo)
    policy(repo, "docs:\n  components:\n    exclude:\n      b: internal helper")
    assert rules(repo) == []


def test_existing_components_dir_uses_the_page_rules_not_this_one(make_repo):
    repo = two_crates(make_repo)
    write_page(repo, "a", "crates/a")
    assert rules(repo) == ["component-missing"]


def test_adopting_clears_the_finding(make_repo):
    repo = two_crates(make_repo)
    write_page(repo, "a", "crates/a")
    write_page(repo, "b", "crates/b", depends=("a",))
    assert rules(repo) == []


def test_unresolvable_workspace_without_components_dir_is_not_flagged(make_repo):
    repo = make_repo()
    write(repo, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
    assert rules(repo) == []


def test_broken_manifest_without_components_dir_is_not_flagged(make_repo):
    repo = two_crates(make_repo)
    write(repo, "Cargo.toml", "[workspace\n")
    assert rules(repo) == []


def test_cli_exits_1_naming_the_rule(make_repo):
    repo = two_crates(make_repo)
    run = subprocess.run([sys.executable, SCRIPT, str(repo)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 1 and "components-not-adopted" in run.stdout


def test_validator_copied_alone_still_passes_a_multi_component_repo(make_repo, tmp_path):
    lone = tmp_path / "lone"
    lone.mkdir()
    shutil.copy(SCRIPT, lone / "validate_docs.py")
    run = subprocess.run([sys.executable, str(lone / "validate_docs.py"), str(two_crates(make_repo))],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
