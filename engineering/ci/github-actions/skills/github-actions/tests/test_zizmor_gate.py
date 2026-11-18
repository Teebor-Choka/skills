"""zizmor gate contract (issue #139): github-actions owns zizmor; security stage 4 only hands over."""
import re
from pathlib import Path

ENG = Path(__file__).resolve().parents[5]
GHA = (ENG / "ci/github-actions/skills/github-actions/SKILL.md").read_text()
SEC_DIR = ENG / "review/skills/security"
SEC = (SEC_DIR / "SKILL.md").read_text()


def _stage4_row():
    rows = [r for r in SEC.splitlines() if re.match(r"\|\s*4\s*\|", r)]
    assert len(rows) == 1, "security stage 4 row must exist exactly once (numbering stable)"
    return rows[0]


def test_stage4_runs_only_when_diff_touches_github():
    row = _stage4_row()
    assert "`.github/`" in row and "diff" in row


def test_stage4_delegates_to_github_actions_and_does_not_run_zizmor():
    row = _stage4_row()
    assert "github-actions" in row
    assert "zizmor" not in row.lower().replace("github-actions", "")
    assert "zizmor" not in (SEC_DIR / "scripts/run-static.sh").read_text()


def test_coverage_statement_names_the_handover():
    m = re.search(r"State coverage:.*", SEC, re.S)
    assert m and "github-actions" in m.group(0)


def test_zizmor_is_mandatory_on_every_workflow_edit():
    assert re.search(r"zizmor[^\n]*mandatory|mandatory[^\n]*zizmor", GHA, re.I)
    assert "skip it rather" not in GHA


def test_zizmor_fallback_order_path_then_nix():
    assert "nix run nixpkgs#zizmor --" in GHA
    assert GHA.index("on `PATH`") < GHA.index("nix run nixpkgs#zizmor --")


def test_no_zizmor_no_nix_reports_unvalidated_never_silent():
    assert "unvalidated" in GHA
    assert re.search(r"findings gate", GHA, re.I)
