"""SKILL.md size rule of scripts/validate-skills.py: warn at 8 KB, fail at 16 KB unless allowlisted."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "validate-skills.py"
KB = 1024


def make_skill(root, name, body_bytes, ref_bytes=0):
    d = root / name
    d.mkdir(parents=True)
    head = f"---\nname: {name}\ndescription: A test skill.\n---\n"
    (d / "SKILL.md").write_text(head + "x" * (body_bytes - len(head)), encoding="utf-8")
    if ref_bytes:
        (d / "references").mkdir()
        (d / "references" / "big.md").write_text("y" * ref_bytes, encoding="utf-8")
    return d


def run(root, allow_lines=None):
    allow = root / "allow.txt"
    allow.write_text("\n".join(allow_lines or []) + "\n", encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(root), "--size-allow", str(allow)],
        capture_output=True, text=True,
    )


def test_small_skill_is_clean(tmp_path):
    make_skill(tmp_path, "small", 2 * KB)
    r = run(tmp_path)
    assert r.returncode == 0
    assert "WARN" not in r.stdout


def test_9kb_skill_warns_but_passes(tmp_path):
    make_skill(tmp_path, "mid", 9 * KB)
    r = run(tmp_path)
    assert r.returncode == 0
    assert "WARN" in r.stdout and "mid" in r.stdout


def test_exactly_8kb_does_not_warn(tmp_path):
    make_skill(tmp_path, "edge", 8 * KB)
    assert "WARN" not in run(tmp_path).stdout


def test_17kb_skill_fails(tmp_path):
    make_skill(tmp_path, "huge", 17 * KB)
    r = run(tmp_path)
    assert r.returncode == 1
    assert "FAIL huge" in r.stdout


def test_exactly_16kb_does_not_fail(tmp_path):
    make_skill(tmp_path, "edge", 16 * KB)
    assert run(tmp_path).returncode == 0


def test_allowlisted_17kb_skill_passes(tmp_path):
    make_skill(tmp_path, "huge", 17 * KB)
    r = run(tmp_path, ["huge | legacy monolith | split by phase into references/"])
    assert r.returncode == 0
    assert "FAIL" not in r.stdout


def test_allowlist_ignores_comments_and_blank_lines(tmp_path):
    make_skill(tmp_path, "huge", 17 * KB)
    r = run(tmp_path, ["# a comment", "", "huge | reason | split by X"])
    assert r.returncode == 0


def test_allowlist_entry_without_reason_is_rejected(tmp_path):
    make_skill(tmp_path, "huge", 17 * KB)
    r = run(tmp_path, ["huge"])
    assert r.returncode == 1


def test_references_size_is_ignored(tmp_path):
    make_skill(tmp_path, "refs", 2 * KB, ref_bytes=40 * KB)
    r = run(tmp_path)
    assert r.returncode == 0
    assert "WARN" not in r.stdout


def test_repo_allowlist_keeps_ci_green():
    repo = SCRIPT.parents[1]
    r = subprocess.run([sys.executable, str(SCRIPT), str(repo)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
