"""Tests for the component-docs skill (spec AT-26 to AT-29): the resolve/scaffold helper and the
skill's structure. The skill text itself is prose; these pin what can be checked deterministically."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
RESOLVE = SKILL / "scripts" / "resolve.py"
PROJECT_DOCS = SKILL.parents[3] / "design" / "skills" / "project-docs"
CONFORMANT = PROJECT_DOCS / "tests" / "fixtures" / "conformant"


def run(*args, script=RESOLVE, env=None):
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True,
                          text=True, timeout=60, env=env)


def validator_rules(repo: Path) -> list[str]:
    out = subprocess.run([sys.executable, str(PROJECT_DOCS / "scripts" / "validate_docs.py"), str(repo), "--json"],
                         capture_output=True, text=True, timeout=60)
    return sorted(f["rule"] for f in json.loads(out.stdout))


def write(repo: Path, rel: str, text: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(text)


def crate(repo: Path, name: str, deps=()) -> None:
    body = f'[package]\nname = "{name}"\nversion = "0.1.0"\n'
    if deps:
        body += "[dependencies]\n" + "".join(f'{d} = {{ path = "../{d}" }}\n' for d in deps)
    write(repo, f"crates/{name}/Cargo.toml", body)
    write(repo, f"crates/{name}/src/lib.rs", "pub fn thing() {}\n")


@pytest.fixture
def repo(tmp_path) -> Path:
    dest = tmp_path / "repo"
    shutil.copytree(CONFORMANT, dest)
    write(dest, "Cargo.toml", '[workspace]\nmembers = ["crates/*"]\n')
    crate(dest, "a")
    crate(dest, "b", deps=("a",))
    return dest


def pages(repo: Path) -> list[str]:
    d = repo / "docs" / "components"
    return sorted(p.name for p in d.glob("*.md")) if d.is_dir() else []


# --- AT-26: non-interactive run on a fixture workspace ------------------------


def test_resolve_prints_the_components_unchanged(repo):
    out = run(repo)
    assert out.returncode == 0, out.stderr
    assert [c["name"] for c in json.loads(out.stdout)["components"]] == ["a", "b"]


def test_scaffold_writes_one_page_per_component_with_manifest_frontmatter(repo):
    out = run(repo, "--scaffold")
    assert out.returncode == 0, out.stderr
    assert pages(repo) == ["a.md", "b.md"]
    page = (repo / "docs/components/b.md").read_text()
    for line in ("title: b", "kind: component", "project: widgetd", "component: b",
                 "path: crates/b", "depends-on: [a]"):
        assert line in page
    assert re.search(r"^updated: \d{4}-\d{2}-\d{2}$", page, re.M)


def test_scaffolded_pages_pass_every_rule_but_the_placeholder_api_row(repo):
    run(repo, "--scaffold")
    assert validator_rules(repo) == ["component-api-unknown", "component-api-unknown"]


def test_scaffold_never_overwrites_a_page(repo):
    run(repo, "--scaffold")
    page = repo / "docs/components/a.md"
    page.write_text(page.read_text() + "\nhand written\n")
    before = page.read_text()
    assert run(repo, "--scaffold").returncode == 0
    assert page.read_text() == before


# --- AT-27: unsupported workspace ---------------------------------------------


def test_unsupported_workspace_returns_needs_input_unchanged_and_writes_nothing(repo):
    shutil.rmtree(repo / "crates")
    write(repo, "pnpm-workspace.yaml", "packages:\n  - 'packages/*'\n")
    direct = subprocess.run([sys.executable, str(PROJECT_DOCS / "scripts" / "components.py"), str(repo)],
                            capture_output=True, text=True, timeout=60)
    assert direct.returncode == 3
    for args in ((), ("--scaffold",)):
        out = run(repo, *args)
        assert out.returncode == 3
        assert out.stdout == direct.stdout
        assert json.loads(out.stdout)["status"] == "needs-input"
    assert pages(repo) == []


# --- AT-28: project-docs tooling absent ---------------------------------------


@pytest.fixture
def isolated_script(tmp_path):
    """A copy of resolve.py outside the marketplace layout, with HOME and the env var cleared."""
    lone = tmp_path / "lone" / "resolve.py"
    lone.parent.mkdir()
    shutil.copy(RESOLVE, lone)
    env = {"HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin"}
    return lone, env


def test_missing_docs_tooling_halts_with_needs_input_field_project_docs(repo, isolated_script):
    lone, env = isolated_script
    out = run(repo, script=lone, env=env)
    assert out.returncode == 3
    result = json.loads(out.stdout)
    assert result["status"] == "needs-input"
    assert [m["field"] for m in result["missing"]] == ["project-docs"]
    assert any("--project-docs" in s for s in result["missing"][0]["supply"])
    assert pages(repo) == []


def test_project_docs_flag_supplies_the_tooling(repo, isolated_script):
    lone, env = isolated_script
    out = run(repo, "--project-docs", PROJECT_DOCS, script=lone, env=env)
    assert out.returncode == 0, out.stdout + out.stderr


def test_project_docs_env_var_supplies_the_tooling(repo, isolated_script):
    lone, env = isolated_script
    out = run(repo, script=lone, env={**env, "PROJECT_DOCS_DIR": str(PROJECT_DOCS)})
    assert out.returncode == 0, out.stdout + out.stderr


def test_flag_naming_a_dir_without_the_resolver_halts(repo, tmp_path):
    out = run(repo, "--project-docs", tmp_path)
    assert out.returncode == 3 and json.loads(out.stdout)["missing"][0]["field"] == "project-docs"


# --- AT-29: never a page for an unlisted component ----------------------------


def test_scaffold_skips_excluded_and_non_member_directories(repo):
    write(repo, "crates/not-a-crate/README.md", "no manifest\n")
    crate(repo, "helper")
    write(repo, ".agents/policy.md", "---\ndocs:\n  components:\n    exclude:\n      helper: test helper\n---\n")
    assert run(repo, "--scaffold").returncode == 0
    assert pages(repo) == ["a.md", "b.md"]


def test_scaffold_without_a_project_name_halts(repo):
    (repo / "docs/overview.md").unlink()
    out = run(repo, "--scaffold")
    assert out.returncode == 3
    assert json.loads(out.stdout)["missing"][0]["field"] == "project"
    assert pages(repo) == []


# --- skill structure ----------------------------------------------------------


def split(text: str):
    _, fm, body = text.split("---", 2)
    return fm, body


def test_frontmatter_names_the_skill_and_its_triggers():
    fm, _ = split((SKILL / "SKILL.md").read_text())
    assert re.search(r"^name: component-docs$", fm, re.M)
    desc = " ".join(fm.split("description:", 1)[1].split())
    assert "public API" in desc and "adding a component" in desc


def test_skill_is_concise_and_references_exist():
    text = (SKILL / "SKILL.md").read_text()
    assert len(text) < 6000
    for rel in re.findall(r"\]\((references/[^)]+)\)", text):
        assert (SKILL / rel).is_file(), rel


def test_skill_covers_the_authoring_duties():
    skill = (SKILL / "SKILL.md").read_text()
    text = (skill + "".join(p.read_text() for p in (SKILL / "references").glob("*.md"))).lower()
    for needle in ("docs-unchanged:", "needs-input", "decisions", "current state", "--scaffold"):
        assert needle in text, needle
    assert "--interactive" not in skill  # asking is never a required step


def test_no_cross_plugin_skill_names():
    skill = (SKILL / "SKILL.md").read_text()
    refs = "".join(p.read_text() for p in (SKILL / "references").glob("*.md"))
    for banned in ("design:", "swe:", "by-angle", "architect"):
        assert banned not in skill + refs, banned
    # The tooling is named only as the halt's field and flag, never as a skill, and not in SKILL.md.
    assert "project-docs" not in skill
