"""Tests for the component-page rules in scripts/validate_docs.py (spec AT-5 to AT-10 and the rules
around them). Active only where docs/components/ exists."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import validate_docs  # noqa: E402  (path wired in conftest.py)
from docs_helpers import cargo_member, cargo_workspace, page_text, policy, write, write_page

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(validate_docs.__file__)


def rules(repo: Path) -> list[str]:
    return [f.rule for f in validate_docs.validate_project(repo)]


def run_cli(*args: str, cwd=None, python_flags=()) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *python_flags, str(SCRIPT), *args],
                          capture_output=True, text=True, timeout=60, cwd=cwd)


@pytest.fixture
def sandy(tmp_path) -> Path:
    """The conformant tree renamed to project `sandy`, plus the sandy-fsutil worked example."""
    repo = tmp_path / "sandy"
    shutil.copytree(FIXTURES / "conformant", repo)
    for md in (repo / "docs").rglob("*.md"):
        md.write_text(md.read_text().replace("project: widgetd", "project: sandy"))
    shutil.copytree(FIXTURES / "sandy-fsutil", repo, dirs_exist_ok=True)
    return repo


@pytest.fixture
def two(make_repo) -> Path:
    """Conformant repo with a workspace of crates a and b (b depends on a) and both pages."""
    repo = make_repo()
    cargo_workspace(repo)
    cargo_member(repo, "a")
    cargo_member(repo, "b", deps=("a",))
    write_page(repo, "a", "crates/a")
    write_page(repo, "b", "crates/b", depends=("a",))
    return repo


# --- AT-10: the worked example ------------------------------------------------


def test_worked_example_passes(sandy):
    assert validate_docs.validate_project(sandy) == []


# --- AT-5, AT-6: nothing changes where docs/components/ is absent -------------


def test_single_crate_without_components_dir_passes(make_repo):
    repo = make_repo()
    write(repo, "Cargo.toml", '[package]\nname = "widgetd"\n')
    assert validate_docs.validate_project(repo) == []


def test_unparseable_workspace_without_components_dir_is_not_resolved(make_repo):
    repo = make_repo()
    write(repo, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
    assert validate_docs.validate_project(repo) == []


# --- docs/generated/ is generated ---------------------------------------------


def test_generated_dir_is_exempt_from_frontmatter_view_and_size(two):
    write(two, "docs/generated/architecture.md", "<!-- generated -->\n" + "line\n" * 400)
    write(two, "docs/generated/index.html", "<html><script src='https://x.test/m.js'></script></html>")
    assert validate_docs.validate_project(two) == []


# --- AT-3: unresolved components ----------------------------------------------


def test_unresolved_components_is_a_finding_and_exit_1(make_repo):
    repo = make_repo()
    write(repo, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
    write_page(repo, "a", "packages/a")
    found = [f for f in validate_docs.validate_project(repo) if f.rule == "components-unresolved"]
    assert len(found) == 1
    assert "--components" in found[0].message and "docs.components.include" in found[0].message
    assert rules(repo) == ["components-unresolved"]
    assert run_cli(str(repo)).returncode == 1


# --- AT-7: page shape ----------------------------------------------------------


def edit(repo: Path, name: str, old: str, new: str) -> None:
    page = repo / "docs" / "components" / f"{name}.md"
    text = page.read_text()
    assert old in text, f"fixture drift: {old!r}"
    page.write_text(text.replace(old, new))


def test_missing_decisions_section(two):
    edit(two, "a", "## Decisions\n\n- **Keep it small.** Less to maintain.\n", "")
    assert rules(two) == ["component-sections"]


def test_sections_out_of_order(two):
    edit(two, "a", "## Interactions", "## TMP")
    edit(two, "a", "## Flow", "## Interactions")
    edit(two, "a", "## TMP", "## Flow")
    assert rules(two) == ["component-sections"]


def test_headings_inside_a_fence_do_not_count(two):
    edit(two, "a", "## Decisions", "```text\n## Decisions\n```\n\n## Other")
    assert rules(two) == ["component-sections"]


def test_no_mermaid_block(two):
    edit(two, "a", "```mermaid\nflowchart LR\n  A --> B\n```", "A --> B")
    assert rules(two) == ["component-mermaid"]


def pad_to(repo: Path, name: str, lines: int) -> None:
    page = repo / "docs" / "components" / f"{name}.md"
    text = page.read_text()
    extra = lines - len(text.splitlines())
    assert extra >= 0
    page.write_text(text.replace("Does one thing.\n", "Does one thing.\n" + "More\n" * extra, 1))
    assert len(page.read_text().splitlines()) == lines


def test_page_over_200_lines(two):
    pad_to(two, "a", 201)
    assert rules(two) == ["component-size"]


def test_page_at_200_lines_passes(two):
    pad_to(two, "a", 200)
    assert rules(two) == []


def test_page_over_12_kb(two):
    edit(two, "a", "Does one thing.", "Does one thing.\n" + ("x" * 119 + "\n") * 100)
    assert rules(two) == ["component-size"]


def test_public_api_over_25_rows(two):
    rows = tuple(f"`Item{i}` | does it" for i in range(26))
    write(two, "crates/a/src/lib.rs", "".join(f"pub fn Item{i}() {{}}\n" for i in range(26)))
    write_page(two, "a", "crates/a", api=rows)
    assert rules(two) == ["component-size"]


@pytest.mark.parametrize("old, new", [
    ("title: a\n", ""),
    ("kind: component", "kind: overview"),
    ("component: a\n", ""),
    ("updated: 2026-11-19", "updated: yesterday"),
    ("path: crates/a\n", ""),
    ("depends-on: []\n", ""),
    ("depends-on: []", "depends-on: nothing"),
], ids=["title", "kind", "component", "updated", "path", "depends-on-absent", "depends-on-not-a-list"])
def test_frontmatter_rules(two, old, new):
    edit(two, "a", old, new)
    assert "component-frontmatter" in rules(two)


def test_page_without_frontmatter(two):
    page = two / "docs/components/a.md"
    page.write_text(page.read_text().split("---\n", 2)[2])
    assert rules(two) == ["component-frontmatter"]


def test_project_divergence_covers_component_pages(two):
    edit(two, "a", "project: widgetd", "project: other")
    assert rules(two) == ["project-divergence"]


def test_secret_scan_covers_component_pages(two):
    edit(two, "a", "Does one thing.", "Key: -----BEGIN RSA PRIVATE KEY-----")
    assert rules(two) == ["secret-pattern"]


# --- component-missing / unknown ----------------------------------------------


def test_resolved_component_without_page(two):
    (two / "docs/components/b.md").unlink()
    assert rules(two) == ["component-missing"]


def test_exclude_entry_satisfies_missing(two):
    (two / "docs/components/b.md").unlink()
    policy(two, "docs:\n  components:\n    exclude:\n      b: internal helper")
    assert rules(two) == []


def test_single_component_needs_no_page(make_repo):
    repo = make_repo()
    write(repo, "Cargo.toml", '[package]\nname = "widgetd"\n')
    (repo / "docs/components").mkdir()
    assert rules(repo) == []


def test_single_component_page_that_exists_must_conform(make_repo):
    repo = make_repo()
    write(repo, "Cargo.toml", '[package]\nname = "widgetd"\n')
    write(repo, "src/lib.rs", "pub fn Thing() {}\n")
    write_page(repo, "widgetd", ".")
    assert rules(repo) == []
    edit(repo, "widgetd", "kind: component", "kind: spec")
    assert rules(repo) == ["component-frontmatter"]


def test_page_for_unknown_component(two):
    write_page(two, "ghost", "crates/ghost")
    assert rules(two) == ["component-unknown"]


def test_page_with_wrong_path_is_unknown(two):
    edit(two, "a", "path: crates/a", "path: crates/elsewhere")
    assert "component-unknown" in rules(two)


# --- AT-8: depends-on ----------------------------------------------------------


def test_depends_on_differs_from_manifest(two):
    cargo_member(two, "c")
    cargo_member(two, "b", deps=("a", "c"))
    write_page(two, "c", "crates/c")
    findings = [f for f in validate_docs.validate_project(two) if f.rule == "component-deps"]
    assert len(findings) == 1 and "a, c" in findings[0].message


def test_depends_on_extra_edge_not_in_manifest(two):
    edit(two, "a", "depends-on: []", "depends-on: [b]")
    assert rules(two) == ["component-deps"]


def test_dev_only_dependency_raises_nothing(two):
    cargo_member(two, "a", dev=("b",))
    assert rules(two) == []


# --- AT-9: Public API identifiers ----------------------------------------------


def test_api_identifier_absent_from_sources(two):
    write(two, "crates/a/src/lib.rs", "pub struct T;\nimpl T { pub fn a() {} }\n")
    write_page(two, "a", "crates/a", api=("`T::{a, b}` | does it",))
    found = [f for f in validate_docs.validate_project(two) if f.rule == "component-api-unknown"]
    assert len(found) == 1
    assert "'b'" in found[0].message and "'a'" not in found[0].message and "'T'" not in found[0].message


def test_api_identifier_must_be_a_whole_word(two):
    write(two, "crates/a/src/lib.rs", "pub fn open_or_create() {}\n")
    write_page(two, "a", "crates/a", api=("`open` | does it",))
    assert rules(two) == ["component-api-unknown"]


def test_api_scan_ignores_the_projects_docs_for_a_root_component(make_repo):
    repo = make_repo()
    write(repo, "Cargo.toml", '[package]\nname = "widgetd"\n')
    write(repo, "src/lib.rs", "pub fn real() {}\n")
    write_page(repo, "widgetd", ".", api=("`Thing` | does it",))  # `Thing` lives only in the page itself
    assert rules(repo) == ["component-api-unknown"]


# --- wiring --------------------------------------------------------------------


def test_cli_exit_1_on_component_finding_from_any_cwd(two, tmp_path):
    (two / "docs/components/b.md").unlink()
    run = run_cli(str(two), cwd=tmp_path, python_flags=("-I",))  # -I drops the script dir from sys.path
    assert run.returncode == 1
    assert "docs/components/b.md" in run.stdout


def test_validator_copied_alone_still_works_without_components_dir(make_repo, tmp_path):
    lone = tmp_path / "lone"
    lone.mkdir()
    shutil.copy(SCRIPT, lone / "validate_docs.py")
    run = subprocess.run([sys.executable, str(lone / "validate_docs.py"), str(make_repo())],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr


def test_validator_copied_alone_exits_2_when_it_needs_the_resolver(two, tmp_path):
    lone = tmp_path / "lone"
    lone.mkdir()
    shutil.copy(SCRIPT, lone / "validate_docs.py")
    run = subprocess.run([sys.executable, str(lone / "validate_docs.py"), str(two)],
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 2 and "components.py" in run.stderr


def test_broken_manifest_makes_the_validator_exit_2(two):
    write(two, "Cargo.toml", "[workspace\n")
    run = run_cli(str(two))
    assert run.returncode == 2 and "Cargo.toml" in run.stderr


def test_skeleton_filled_in_conforms(make_repo):
    repo = make_repo()
    write(repo, "Cargo.toml", '[package]\nname = "widgetd"\n')
    write(repo, "src/lib.rs", "pub fn Item() {}\n")
    skeleton = (Path(validate_docs.__file__).parent.parent / "assets" / "component.skeleton.md").read_text()
    filled = (skeleton.replace("COMPONENT", "widgetd").replace("PROJECT", "widgetd")
              .replace("YYYY-MM-DD", "2026-11-19").replace("DIR", "."))
    write(repo, "docs/components/widgetd.md", filled)
    assert rules(repo) == []
