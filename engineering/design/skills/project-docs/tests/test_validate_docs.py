"""Tests for scripts/validate_docs.py against the fixtures in tests/fixtures/.

The conformant fixture must pass clean. Each broken variant is built by copying
the conformant fixture and mutating exactly one thing, so the test proves that
mutation raises exactly its own rule and nothing else. CLI behavior (exit code,
--all, --json) is exercised through a real subprocess.

Pure standard library, no third-party deps beyond pytest itself.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import validate_docs  # noqa: E402  (path wired in conftest.py)

SCRIPT = Path(validate_docs.__file__)


def rules(repo: Path) -> list[str]:
    return [f.rule for f in validate_docs.validate_project(repo)]


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


# --- conformant ---------------------------------------------------------------


def test_conformant_passes_clean(conformant_src):
    assert validate_docs.validate_project(conformant_src) == []


def test_conformant_cli_exit_zero(conformant_src):
    result = run_cli(str(conformant_src))
    assert result.returncode == 0, result.stdout + result.stderr


# --- broken variants, one rule each -------------------------------------------


def test_missing_overview(make_repo):
    repo = make_repo()
    (repo / "docs" / "overview.md").unlink()
    assert rules(repo) == ["missing-overview"]


def test_missing_decisions_index(make_repo):
    repo = make_repo()
    (repo / "docs" / "decisions" / "README.md").unlink()
    # Removing the index also removes the forward-link source, so the ADR can no
    # longer be shown as linked. The tree rule is the one under test; assert it
    # is raised (index-drift naturally follows from a deleted index).
    assert "missing-decisions-index" in rules(repo)


def test_missing_adr(make_repo):
    repo = make_repo()
    (repo / "docs" / "decisions" / "use-sqlite.md").unlink()
    # The index still links the now-missing ADR, so reverse drift also fires;
    # the rule under test is the absence of any ADR.
    assert "missing-adr" in rules(repo)


def test_bad_frontmatter_key(make_repo):
    repo = make_repo()
    overview = repo / "docs" / "overview.md"
    text = overview.read_text().replace("title: widgetd overview\n", "")
    overview.write_text(text)
    assert rules(repo) == ["frontmatter-key"]


@pytest.mark.parametrize(
    "relpath, old, new, rule",
    [
        pytest.param("docs/overview.md", "updated: 2026-10-13", "updated: Oct 2026",
                     "frontmatter-updated", id="bad-updated-date"),
        pytest.param("docs/decisions/use-sqlite.md", "status: accepted", "status: approved",
                     "frontmatter-status", id="unknown-status"),
        pytest.param("docs/decisions/use-sqlite.md", "status: accepted", "status: rejected",
                     "frontmatter-status", id="discarded-status-is-not-a-file-status"),
        pytest.param("docs/spec.md", "project: widgetd", "project: other-name",
                     "project-divergence", id="divergent-project-name"),
    ],
)
def test_single_edit_raises_one_rule(make_repo, relpath, old, new, rule):
    # Each mutates exactly one field in one file and must raise exactly its rule.
    repo = make_repo()
    target = repo / relpath
    text = target.read_text()
    assert old in text, f"fixture drift: {old!r} not in {relpath}"
    target.write_text(text.replace(old, new))
    assert rules(repo) == [rule]


def test_non_kebab_adr_filename(make_repo):
    repo = make_repo()
    decisions = repo / "docs" / "decisions"
    (decisions / "use-sqlite.md").rename(decisions / "Use_SQLite.md")
    # Keep the index in sync so only the filename rule fires, not index drift.
    readme = decisions / "README.md"
    readme.write_text(readme.read_text().replace("(use-sqlite.md)", "(Use_SQLite.md)"))
    assert rules(repo) == ["adr-filename"]


def test_missing_adr_section(make_repo):
    repo = make_repo()
    adr = repo / "docs" / "decisions" / "use-sqlite.md"
    # Rename the Consequences label so only Context and Decision remain.
    adr.write_text(adr.read_text().replace("**Consequences.**", "**Outcomes.**"))
    assert rules(repo) == ["adr-section"]


def test_adr_sections_out_of_order(make_repo):
    repo = make_repo()
    adr = repo / "docs" / "decisions" / "use-sqlite.md"
    text = adr.read_text()
    # Swap the Context and Decision labels: all three present, wrong order.
    text = (text.replace("**Context.**", "<<TMP>>")
                .replace("**Decision.**", "**Context.**")
                .replace("<<TMP>>", "**Decision.**"))
    adr.write_text(text)
    assert rules(repo) == ["adr-section-order"]


def test_adr_footnote_missing_definition(make_repo):
    repo = make_repo()
    adr = repo / "docs" / "decisions" / "use-sqlite.md"
    text = adr.read_text()
    # Drop the [^pg] definition, leaving the reference in the Decision dangling.
    adr.write_text(text[: text.index("[^pg]:")].rstrip() + "\n")
    assert rules(repo) == ["adr-footnote"]


def test_index_drift_forward_adr_not_linked(make_repo):
    repo = make_repo()
    # Add a fully conformant ADR but do not link it from the index.
    extra = repo / "docs" / "decisions" / "use-async-writes.md"
    extra.write_text(
        "---\n"
        "title: Use async writes\n"
        "status: proposed\n"
        "repo: widgetd\n"
        "updated: 2026-10-13\n"
        "---\n\n"
        "# Use async writes\n\n"
        "**Context.** Sync writes bound throughput.\n\n"
        "**Decision.** Batch writes asynchronously.\n\n"
        "**Consequences.** Higher throughput, weaker durability.\n\n"
        "**Alternatives.** Keep sync writes; rejected for throughput.\n"
    )
    assert rules(repo) == ["index-drift"]


def test_index_drift_reverse_dangling_link(make_repo):
    repo = make_repo()
    readme = repo / "docs" / "decisions" / "README.md"
    readme.write_text(readme.read_text() + "\n2. [Ghost decision](ghost-decision.md)\n")
    assert rules(repo) == ["index-drift"]


def test_agents_missing_pointer(make_repo):
    repo = make_repo()
    agents = repo / "AGENTS.md"
    # Drop the decisions pointer; keep the overview pointer.
    text = agents.read_text().replace(
        "Decisions live under [`docs/decisions`](docs/decisions/); read them before changing load-bearing behavior.",
        "",
    )
    agents.write_text(text)
    assert rules(repo) == ["agents-md"]


def test_missing_mermaid_in_overview(make_repo):
    repo = make_repo()
    overview = repo / "docs" / "overview.md"
    text = overview.read_text()
    start = text.index("```mermaid")
    end = text.index("```\n", start + 3) + 4
    overview.write_text(text[:start] + text[end:])
    assert rules(repo) == ["diagram"]


def test_repo_alias_accepted(make_repo):
    # `repo` is a deprecated alias for `project`. Swapping the key keeps the same
    # value, so the name requirement is met and no divergence is raised.
    repo = make_repo()
    overview = repo / "docs" / "overview.md"
    overview.write_text(overview.read_text().replace("project: widgetd", "repo: widgetd"))
    assert validate_docs.validate_project(repo) == []


def test_undocumented_repo_no_docs_dir(tmp_path):
    repo = tmp_path / "bare"
    (repo / ".git").mkdir(parents=True)
    findings = validate_docs.validate_project(repo)
    assert [f.rule for f in findings] == ["undocumented"]
    assert findings[0].severity == "warning"


# --- optional spec.md: absence is fine ---------------------------------------


def test_spec_is_optional(make_repo):
    repo = make_repo()
    (repo / "docs" / "spec.md").unlink()
    assert validate_docs.validate_project(repo) == []


# --- extra docs under docs/ are ignored --------------------------------------


def test_extra_docs_are_ignored(make_repo):
    repo = make_repo()
    design = repo / "docs" / "design"
    design.mkdir()
    # No frontmatter at all; the contract says the validator ignores extra docs.
    (design / "notes.md").write_text("# just some notes\n")
    assert validate_docs.validate_project(repo) == []


# --- CLI: --all and --json ----------------------------------------------------


def test_cli_all_summarizes_per_repo(make_repo, tmp_path):
    # One passing repo, one failing repo, under a shared root.
    good = make_repo("good")
    bad = make_repo("bad")
    (bad / "docs" / "overview.md").unlink()
    root = good.parent  # tmp_path, holds good/ and bad/

    result = run_cli("--all", str(root))
    assert result.returncode != 0  # bad repo fails the whole run
    assert "bad/docs/overview.md" in result.stdout
    assert "FAIL" in result.stderr and "PASS" in result.stderr


def test_find_projects_includes_nested_under_documented_root(make_repo):
    # A portfolio root that is itself documented must not hide a subproject: both
    # are found, and a project's own docs/ subtree is never a project.
    root = make_repo("portfolio")
    child = make_repo("child")
    nested = root / "sub"
    shutil.move(str(child), str(nested))

    found = set(validate_docs.find_projects(root))
    assert root in found
    assert nested in found
    assert not any(p.name in {"docs", "decisions"} for p in found)


def test_cli_all_validates_nested_under_documented_root(make_repo):
    root = make_repo("portfolio")
    nested = root / "sub"
    shutil.move(str(make_repo("child")), str(nested))
    (nested / "docs" / "overview.md").unlink()  # break only the nested one

    result = run_cli("--all", str(root))
    assert result.returncode != 0
    assert "sub/docs/overview.md" in result.stdout


def test_find_projects_does_not_descend_into_a_nested_git_repo(make_repo):
    # A git repo below the root owns its subtree: its vendored docs/ must not be
    # discovered as separate projects (the repo's own gate validates it).
    root = make_repo("portfolio")
    repo = root / "sub"
    shutil.move(str(make_repo("child")), str(repo))
    (repo / ".git").mkdir()
    vendored = repo / "vendor" / "pkg" / "docs"
    vendored.mkdir(parents=True)
    (vendored / "overview.md").write_text("x\n")

    found = set(validate_docs.find_projects(root))
    assert root in found and repo in found
    assert not any("vendor" in p.parts for p in found)


def test_cli_all_discovers_undocumented_git_repo(tmp_path):
    repo = tmp_path / "bare"
    (repo / ".git").mkdir(parents=True)
    result = run_cli("--all", str(tmp_path))
    assert result.returncode != 0
    assert "no docs/ directory" in result.stdout


def test_cli_json_schema(make_repo):
    repo = make_repo()
    (repo / "docs" / "overview.md").unlink()
    result = run_cli(str(repo), "--json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list) and len(payload) == 1
    entry = payload[0]
    assert set(entry) == {"project", "file", "rule", "message", "severity"}
    assert entry["rule"] == "missing-overview"
    assert entry["severity"] == "error"


def test_cli_json_empty_on_pass(conformant_src):
    result = run_cli(str(conformant_src), "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout) == []


# --- hardening: exit codes, dates, diagrams, supersede, secrets ----------------

import re  # noqa: E402

DIAGRAM_BLOCK_RE = re.compile(r"```mermaid\n.*?```\n", re.DOTALL)


def set_overview_diagram(repo: Path, block: str) -> None:
    overview = repo / "docs" / "overview.md"
    text = overview.read_text()
    assert DIAGRAM_BLOCK_RE.search(text)
    overview.write_text(DIAGRAM_BLOCK_RE.sub(lambda _: block, text, count=1))


def test_cli_all_with_no_projects_exits_two(tmp_path):
    result = run_cli("--all", str(tmp_path))
    assert result.returncode == 2
    assert "no projects found under" in result.stderr
    assert "ok: all checks passed" not in result.stderr


def test_non_utf8_doc_is_a_finding_not_a_crash(make_repo):
    repo = make_repo()
    (repo / "docs" / "overview.md").write_bytes(b"\xff\xfe\x00 not utf-8 \x80")
    assert rules(repo) == ["unreadable-file"]


def test_cli_all_continues_after_an_unreadable_doc(make_repo, tmp_path):
    bad = make_repo("bad")
    (bad / "docs" / "overview.md").write_bytes(b"\xff\xfe\x00 \x80")
    make_repo("good")
    result = run_cli("--all", str(tmp_path))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "unreadable" in result.stdout
    assert "PASS" in result.stderr and "FAIL" in result.stderr


def test_unexpected_exception_exits_two(make_repo, monkeypatch, capsys):
    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(validate_docs, "validate_project", boom)
    assert validate_docs.main([str(make_repo())]) == 2
    assert "boom" in capsys.readouterr().err


def test_updated_must_be_a_real_calendar_date(make_repo):
    repo = make_repo()
    p = repo / "docs" / "overview.md"
    p.write_text(re.sub(r"(?m)^updated: .*$", "updated: 2026-13-45", p.read_text(), count=1))
    assert rules(repo) == ["frontmatter-updated"]


@pytest.mark.parametrize("block", ["```mermaid\n```\n", "```mermaid\n   \n\n```\n", "~~~mermaid\n~~~\n"])
def test_empty_mermaid_fence_does_not_satisfy_diagram(make_repo, block):
    repo = make_repo()
    set_overview_diagram(repo, block)
    assert rules(repo) == ["diagram"]


@pytest.mark.parametrize(
    "block",
    [
        "~~~mermaid\nflowchart TD\n  a --> b\n~~~\n",
        "````mermaid\nflowchart TD\n  a --> b\n````\n",
    ],
)
def test_real_mermaid_fences_of_other_styles_pass(make_repo, block):
    repo = make_repo()
    set_overview_diagram(repo, block)
    assert rules(repo) == []


def test_mermaid_nested_in_a_longer_fence_does_not_count(make_repo):
    repo = make_repo()
    set_overview_diagram(
        repo, "````markdown\n```mermaid\nflowchart TD\n  a --> b\n```\n````\n"
    )
    assert rules(repo) == ["diagram"]


def add_adr(repo: Path, slug: str, extra_fm: str = "") -> None:
    src = (repo / "docs" / "decisions" / "use-sqlite.md").read_text()
    src = src.replace("status: accepted\n", "status: accepted\n" + extra_fm, 1)
    (repo / "docs" / "decisions" / f"{slug}.md").write_text(src)
    idx = repo / "docs" / "decisions" / "README.md"
    idx.write_text(idx.read_text() + f"2. [{slug}]({slug}.md)\n")


def set_fm(repo: Path, slug: str, line: str) -> None:
    p = repo / "docs" / "decisions" / f"{slug}.md"
    p.write_text(p.read_text().replace("status: accepted\n", f"status: accepted\n{line}\n", 1))


def test_supersede_links_to_existing_adrs_pass(make_repo):
    repo = make_repo()
    add_adr(repo, "use-postgres", "supersedes: use-sqlite\n")
    set_fm(repo, "use-sqlite", "superseded-by: use-postgres")
    assert rules(repo) == []


def test_supersedes_missing_target_is_flagged(make_repo):
    repo = make_repo()
    set_fm(repo, "use-sqlite", "supersedes: no-such-adr")
    assert rules(repo) == ["adr-supersede"]


def test_superseded_by_list_flags_only_the_missing_target(make_repo):
    repo = make_repo()
    add_adr(repo, "use-postgres")
    set_fm(repo, "use-sqlite", "superseded-by: [use-postgres, ghost]")
    found = [f for f in validate_docs.validate_project(repo) if f.rule == "adr-supersede"]
    assert len(found) == 1 and "ghost" in found[0].message


# Secrets are assembled at runtime so this file holds no literal token.
SECRETS = {
    "pem": "-----BEGIN " + "RSA PRIVATE KEY-----",
    "aws": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "gh": "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
    "ghpat": "github" + "_pat_" + "a1B2c3D4e5F6g7H8i9J0k1",
    "slack": "xo" + "xb-" + "1234567890-abcdefghij",
}


@pytest.mark.parametrize("secret", SECRETS.values(), ids=SECRETS.keys())
def test_secret_pattern_flags_without_echoing(make_repo, secret):
    repo = make_repo()
    p = repo / "docs" / "spec.md"
    p.write_text(p.read_text() + f"\nconfig: {secret}\n")
    assert rules(repo) == ["secret-pattern"]
    plain = run_cli(str(repo))
    as_json = run_cli(str(repo), "--json")
    assert plain.returncode != 0 and as_json.returncode != 0
    for out in (plain, as_json):
        assert secret not in out.stdout + out.stderr
    assert "secret-pattern" in [f["rule"] for f in json.loads(as_json.stdout)]


def test_secret_pattern_ignores_prose_and_short_examples(make_repo):
    repo = make_repo()
    p = repo / "docs" / "spec.md"
    p.write_text(
        p.read_text()
        + "\nThe password is read from the vault. Example: AKIA1234, ghp_short,"
        " xoxb-1, github_pat_x, a PRIVATE KEY lives in the secret store.\n"
    )
    assert rules(repo) == []
