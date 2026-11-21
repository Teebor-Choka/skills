"""zizmor gate contract (issue #139): the ci skill owns zizmor; security stage 4 only hands over."""
import re
from pathlib import Path

ENG = Path(__file__).resolve().parents[5]
CI_SKILL = ENG / "infra/devops/skills/ci"
GHA = (CI_SKILL / "references/github-actions/guide.md").read_text()
SEC_DIR = ENG / "infra/devops/skills/security"
SEC = (SEC_DIR / "SKILL.md").read_text()
TOOLS = (SEC_DIR / "references/tools.md").read_text()


def _stage4_row():
    rows = [r for r in SEC.splitlines() if re.match(r"\|\s*4\s*\|", r)]
    assert len(rows) == 1, "security stage 4 row must exist exactly once (numbering stable)"
    return rows[0]


def test_stage4_runs_only_when_diff_touches_github():
    assert "only if the diff touches `.github/`" in _stage4_row()


def test_stage4_delegates_to_ci():
    assert "`ci` skill" in _stage4_row()


def test_security_never_invokes_zizmor():
    assert "zizmor" not in _stage4_row().lower()
    assert "zizmor" not in (SEC_DIR / "scripts/run-static.sh").read_text()
    for text in (SEC, TOOLS):
        assert not re.search(r"(?m)^\s*zizmor\s", text), "no zizmor command line"


def test_coverage_statement_names_the_handover():
    m = re.search(r"State coverage:[^\n]*(?:\n {3}[^\n]*)*", SEC)
    assert m and "`ci`" in m.group(0)


def test_zizmor_is_mandatory_on_every_workflow_edit():
    assert re.search(r"zizmor[^\n]*mandatory|mandatory[^\n]*zizmor", GHA, re.I)
    assert "skip it rather" not in GHA


def test_zizmor_fallback_order_path_then_nix_then_unvalidated():
    path = GHA.index("1. `zizmor --format plain")
    nix = GHA.index("nix run nixpkgs#zizmor --")
    unvalidated = GHA.index("unvalidated")
    assert path < nix < unvalidated


def test_no_report_is_unvalidated_never_silent():
    assert "Never skip silently" in GHA
    assert "no step produces a zizmor report" in GHA
    assert re.search(r"findings gate", GHA, re.I)


def test_stage4_handover_is_read_only():
    assert "make no edits" in GHA


def test_ci_skill_routes_to_the_github_actions_guide():
    text = (CI_SKILL / "SKILL.md").read_text()
    assert "references/github-actions/guide.md" in text
    assert "references/github-actions/lint-hooks.md" in text
    assert (CI_SKILL / "references/github-actions/lint-hooks.md").is_file()
