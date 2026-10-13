"""Tests for scripts/validate_docs.py against the fixtures in tests/fixtures/.

The conformant fixture must pass clean. Each broken variant is built by copying
the conformant fixture and mutating exactly one thing, so the test proves that
mutation raises exactly its own rule and nothing else. CLI behavior (exit code,
--all, --json) is exercised through a real subprocess.

Pure standard library, no third-party deps beyond pytest itself.
"""

import json
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
