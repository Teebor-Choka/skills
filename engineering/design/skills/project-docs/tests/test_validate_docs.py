"""Tests for scripts/validate_docs.py against the fixtures in tests/fixtures/.

The conformant fixture must pass clean. Each broken variant is built by copying
the conformant fixture and mutating exactly one thing, so the test proves that
mutation raises exactly its own rule and nothing else. CLI behavior (exit code,
--all, --json) is exercised through a real subprocess.

Pure standard library, no third-party deps beyond pytest itself.
"""

import json
import os
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


# --- optional process.md ------------------------------------------------------

PROCESS_DOC = (
    "---\n"
    "title: widgetd process\n"
    "kind: process\n"
    "project: widgetd\n"
    "updated: 2026-10-13\n"
    "---\n\n"
    "# widgetd process\n\n"
    "```mermaid\n"
    "flowchart LR\n"
    "    spec --> build --> review\n"
    "```\n"
)


def add_process(repo: Path, text: str = PROCESS_DOC) -> Path:
    doc = repo / "docs" / "process.md"
    doc.write_text(text)
    return doc


def test_conformant_fixture_carries_a_process_doc(conformant_src):
    assert (conformant_src / "docs" / "process.md").is_file()


def test_process_doc_is_always_optional(make_repo):
    repo = make_repo()
    (repo / "docs" / "process.md").unlink()
    assert validate_docs.validate_project(repo) == []


def test_valid_process_doc_passes(make_repo):
    repo = make_repo()
    add_process(repo)
    assert validate_docs.validate_project(repo) == []


@pytest.mark.parametrize(
    "old, new, rule",
    [
        pytest.param("kind: process", "kind: overview", "frontmatter-kind", id="wrong-kind"),
        pytest.param("project: widgetd", "project: other-name", "project-divergence",
                     id="divergent-project-name"),
        pytest.param("updated: 2026-10-13", "updated: Oct 2026", "frontmatter-updated",
                     id="bad-updated-date"),
        pytest.param("title: widgetd process\n", "", "frontmatter-key", id="missing-title"),
    ],
)
def test_process_doc_single_edit_raises_one_rule(make_repo, old, new, rule):
    repo = make_repo()
    assert old in PROCESS_DOC, f"fixture drift: {old!r}"
    add_process(repo, PROCESS_DOC.replace(old, new))
    findings = validate_docs.validate_project(repo)
    assert [f.rule for f in findings] == [rule]
    assert findings[0].file == "docs/process.md"


def test_process_doc_malformed_frontmatter(make_repo):
    repo = make_repo()
    # Opening fence never closed: treated as missing frontmatter.
    add_process(repo, "---\ntitle: widgetd process\nkind: process\n\n# body\n\n```mermaid\nflowchart LR\n    a --> b\n```\n")
    findings = validate_docs.validate_project(repo)
    assert [f.rule for f in findings] == ["frontmatter-missing"]
    assert findings[0].file == "docs/process.md"


def test_process_doc_without_mermaid(make_repo):
    repo = make_repo()
    start = PROCESS_DOC.index("```mermaid")
    add_process(repo, PROCESS_DOC[:start])
    assert rules(repo) == ["diagram"]


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
    "slack": "xo" + "xb-" + "123456789012-1234567890123-" + "abcdefghijABCDEFGHIJabcd",
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


@pytest.mark.parametrize(
    "text",
    [
        "AKIAIOSFODNN7EXAMPLE",  # AWS's documented example key
        "xoxb-your-token-here",
        "BAKIA" + "ABCDEFGHIJKLMNOP",  # embedded in a longer word
        "AKIA" + "ABCDEFGHIJKLMNOP" + "Q",
    ],
)
def test_secret_pattern_ignores_documented_examples_and_embedded_text(make_repo, text):
    repo = make_repo()
    p = repo / "docs" / "spec.md"
    p.write_text(p.read_text() + f"\nexample: {text}\n")
    assert rules(repo) == []


def test_four_space_indented_fence_is_not_a_fence(make_repo):
    repo = make_repo()
    set_overview_diagram(repo, "    ```mermaid\n    flowchart TD\n      a --> b\n    ```\n")
    assert rules(repo) == ["diagram"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
@pytest.mark.parametrize("sub", ["docs", "docs/decisions"])
def test_unreadable_doc_dir_is_a_finding_not_an_abort(make_repo, sub):
    repo = make_repo()
    d = repo / sub
    d.chmod(0)
    try:
        assert rules(repo) == ["unreadable-file"]
    finally:
        d.chmod(0o755)


# --- optional views: docs/views/<name>.html ------------------------------------

TEMPLATE = Path(validate_docs.__file__).parent.parent / "assets" / "view.template.html"


def fill_template(name: str = "process", updated: str = "2026-10-13") -> str:
    """The shipped template with its head placeholders filled, nothing else touched."""
    text = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (("SOURCE-NAME", name), ("YYYY-MM-DD", updated), ("TITLE", "widgetd process"),
                         ("PROJECT", "widgetd")):
        text = text.replace(token, value)
    return text


def add_view(repo: Path, text: str | None = None, name: str = "process") -> Path:
    """Write docs/views/<name>.html; the fixture's docs/process.md has updated 2026-10-13."""
    views = repo / "docs" / "views"
    views.mkdir(parents=True, exist_ok=True)
    view = views / f"{name}.html"
    view.write_text(fill_template(name) if text is None else text, encoding="utf-8")
    return view


def test_shipped_template_passes_once_its_head_is_filled(make_repo):
    # The asset and the validator cannot drift: a filled template is a conformant view.
    repo = make_repo()
    add_view(repo)
    assert validate_docs.validate_project(repo) == []


def test_views_are_optional(make_repo):
    repo = make_repo()
    assert not (repo / "docs" / "views").exists()
    assert validate_docs.validate_project(repo) == []


def test_non_html_files_in_views_are_ignored(make_repo):
    repo = make_repo()
    add_view(repo)
    (repo / "docs" / "views" / "notes.txt").write_text("<script src='https://x.example/a.js'>")
    assert validate_docs.validate_project(repo) == []


@pytest.mark.parametrize(
    "old, new, rule",
    [
        pytest.param("<title>widgetd process</title>", "<title> </title>", "view-title",
                     id="empty-title"),
        pytest.param("<title>widgetd process</title>", "", "view-title", id="missing-title"),
        pytest.param('<meta name="viewport"', '<meta name="viewpor"', "view-viewport",
                     id="missing-viewport"),
        pytest.param('<meta name="source" content="docs/process.md" />', "", "view-source",
                     id="missing-source"),
        pytest.param("docs/process.md", "docs/gone.md", "view-source", id="source-not-on-disk"),
        pytest.param("docs/process.md", "docs/overview.md", "view-source",
                     id="source-is-not-the-file-stem"),
        pytest.param("docs/process.md", "../process.md", "view-source", id="source-not-under-docs"),
        pytest.param('<meta name="updated" content="2026-10-13" />', "", "view-updated",
                     id="missing-updated"),
        pytest.param("2026-10-13", "13 Oct 2026", "view-updated", id="updated-not-iso"),
        pytest.param("2026-10-13", "2026-09-01", "view-updated", id="updated-differs-from-source"),
        pytest.param("prefers-color-scheme: dark", "prefers-contrast: more", "view-theme",
                     id="no-dark-theme"),
    ],
)
def test_view_single_edit_raises_one_rule(make_repo, old, new, rule):
    repo = make_repo()
    text = fill_template()
    assert old in text, f"template drift: {old!r}"
    add_view(repo, text.replace(old, new, 1))
    findings = validate_docs.validate_project(repo)
    assert [f.rule for f in findings] == [rule]
    assert findings[0].file == "docs/views/process.html"


@pytest.mark.parametrize(
    "snippet",
    [
        pytest.param('<script>alert(1)</script>', id="inline-script"),
        pytest.param('<script src="app.js"></script>', id="local-script"),
        pytest.param('<link rel="stylesheet" href="https://cdn.example/a.css">', id="remote-css"),
        pytest.param('<link rel="stylesheet" href="//cdn.example/a.css">', id="protocol-relative-css"),
        pytest.param('<link rel="stylesheet" href="local.css">', id="linked-local-css"),
        pytest.param('<img src="https://x.example/a.png">', id="remote-image"),
        pytest.param('<iframe src="https://x.example/"></iframe>', id="remote-frame"),
        pytest.param('<style>@import "https://x.example/a.css";</style>', id="css-import"),
        pytest.param('<style>body{background:url(https://x.example/a.png)}</style>', id="css-remote-url"),
    ],
)
def test_view_that_loads_anything_is_flagged(make_repo, snippet):
    repo = make_repo()
    text = fill_template().replace("</head>", snippet + "\n</head>", 1)
    add_view(repo, text)
    assert rules(repo) == ["view-external"]


def test_view_may_link_out_with_an_anchor_and_embed_data_uris(make_repo):
    # An <a href> navigates, it does not load. A data: URI is self-contained.
    repo = make_repo()
    body = ('<a href="https://example.com/spec">spec</a>'
            '<img alt="" src="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27/%3E">')
    add_view(repo, fill_template().replace("</body>", body + "\n</body>", 1))
    assert validate_docs.validate_project(repo) == []


def test_view_findings_name_every_broken_view(make_repo):
    repo = make_repo()
    add_view(repo, fill_template().replace("2026-10-13", "2026-01-01"))
    add_view(repo, fill_template("overview").replace("<title>widgetd process</title>", ""), name="overview")
    findings = validate_docs.validate_project(repo)
    assert sorted((f.file, f.rule) for f in findings) == [
        ("docs/views/overview.html", "view-title"),
        ("docs/views/process.html", "view-updated"),
    ]


def test_secret_in_a_view_is_flagged_without_echoing(make_repo):
    repo = make_repo()
    secret = "ghp_" + "a" * 36
    add_view(repo, fill_template().replace("</body>", f"<p>{secret}</p></body>", 1))
    findings = validate_docs.validate_project(repo)
    assert [f.rule for f in findings] == ["secret-pattern"]
    assert secret not in findings[0].message


def test_non_utf8_view_is_a_finding_not_a_crash(make_repo):
    repo = make_repo()
    view = add_view(repo)
    view.write_bytes(b"\xff\xfe\x00bad")
    assert rules(repo) == ["unreadable-file"]


# --- views: bypasses of "no script, no network" found in review ---------------


@pytest.mark.parametrize(
    "snippet",
    [
        pytest.param('<body onload="fetch(1)"></body>', id="onload-handler"),
        pytest.param('<img alt="" src="data:," onerror="fetch(1)">', id="onerror-handler"),
        pytest.param('<a href="javascript:fetch(1)">x</a>', id="javascript-url"),
        pytest.param('<a href=" JavaScript:fetch(1)">x</a>', id="javascript-url-padded"),
        pytest.param('<object data="https://x.example/a.svg"></object>', id="object-data"),
        pytest.param('<svg><image href="https://x.example/a.png"/></svg>', id="svg-image-href"),
        pytest.param('<svg><use href="https://x.example/s.svg#i"/></svg>', id="svg-use-href"),
        pytest.param('<svg><use xlink:href="https://x.example/s.svg#i"/></svg>', id="xlink-href"),
        pytest.param('<iframe srcdoc="<img src=https://x.example/a.png>"></iframe>', id="srcdoc"),
        pytest.param('<img alt="" srcset="data:image/png;base64,AA 1x, https://x.example/a.png 2x">',
                     id="srcset-second-candidate"),
        pytest.param('<base href="https://x.example/">', id="base-href"),
        pytest.param('<form action="https://x.example/post"></form>', id="form-action"),
        pytest.param('<style>body{background:url(" https://x.example/a.png")}</style>',
                     id="css-url-space-inside-quotes"),
        pytest.param('<style>body{background:image-set("https://x.example/a.png" 1x)}</style>',
                     id="css-image-set"),
        pytest.param('<style>@IMPORT url(a.css);</style>', id="css-import-uppercase"),
    ],
)
def test_view_bypasses_are_flagged(make_repo, snippet):
    repo = make_repo()
    add_view(repo, fill_template().replace("</body>", snippet + "\n</body>", 1))
    assert rules(repo) == ["view-external"]


@pytest.mark.parametrize(
    "snippet",
    [
        pytest.param("<style>/* @import url(https://x.example/a.css) */ p{color:red}</style>",
                     id="css-comment-mentions-import"),
        pytest.param('<img alt="" src="DATA:image/gif;base64,R0lGOD">', id="uppercase-data-uri"),
        pytest.param('<svg><use href="#icon"/></svg>', id="svg-use-fragment"),
        pytest.param('<img alt="" srcset="data:image/png;base64,AA 1x, data:image/png;base64,BB 2x">',
                     id="srcset-all-data"),
        pytest.param('<a href="#top">top</a><a href="../overview.md">overview</a>', id="plain-links"),
    ],
)
def test_view_legitimate_markup_is_not_flagged(make_repo, snippet):
    repo = make_repo()
    add_view(repo, fill_template().replace("</body>", snippet + "\n</body>", 1))
    assert validate_docs.validate_project(repo) == []


def test_view_meta_names_are_case_insensitive(make_repo):
    repo = make_repo()
    text = fill_template().replace('name="viewport"', 'name="Viewport"', 1)
    add_view(repo, text)
    assert validate_docs.validate_project(repo) == []


def test_svg_title_does_not_satisfy_view_title(make_repo):
    repo = make_repo()
    text = fill_template().replace("<title>widgetd process</title>", "", 1)
    add_view(repo, text.replace("</body>", "<svg><title>icon</title></svg></body>", 1))
    assert rules(repo) == ["view-title"]


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file modes")
def test_unreadable_view_source_is_a_finding_not_a_crash(make_repo):
    repo = make_repo()
    notes = repo / "docs" / "notes.md"
    notes.write_text("---\nupdated: 2026-10-13\n---\n# notes\n")
    add_view(repo, name="notes")
    notes.chmod(0)
    try:
        findings = validate_docs.validate_project(repo)
    finally:
        notes.chmod(0o644)
    assert [(f.rule, f.file) for f in findings] == [("unreadable-file", "docs/notes.md")]


def test_view_of_a_source_without_a_date_is_not_compared(make_repo):
    # Nothing to compare against: the contract only dates its own doc kinds.
    repo = make_repo()
    (repo / "docs" / "notes.md").write_text("# notes, no frontmatter\n")
    add_view(repo, name="notes")
    assert validate_docs.validate_project(repo) == []
