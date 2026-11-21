"""Shared programs carry no private markers: no owner identity, home paths or machine-local temp paths.

Scans SCOPES. More markers (host names, private repo names) come from PRIVATE_MARKERS, comma-separated,
so the list itself never lands in this public repo.
"""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ("engineering/tools/ows",)
# Built by concatenation so this file does not match itself.
MARKERS = ("tee" + "bor", "tib" + "or", "cs" + "óka", "cs" + "oka", "kau" + "ki")
PATTERNS = (re.compile(r"/Users/[A-Za-z]"), re.compile(r"/home/[a-z]"), re.compile(r"/private/(tmp|var)/"),
            re.compile(r"claude-\d{3}"))
SKIP_DIRS = {"__pycache__", ".pytest_cache"}


def markers():
    extra = [m.strip().lower() for m in os.environ.get("PRIVATE_MARKERS", "").split(",") if m.strip()]
    return tuple(MARKERS) + tuple(extra)


def hits(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath, name)
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            low = (path.relative_to(root).as_posix() + "\n" + text).lower()
            found += [f"{path}: {m}" for m in markers() if m in low]
            found += [f"{path}: {p.pattern}" for p in PATTERNS if p.search(text)]
    return found


def test_scopes_exist():
    assert all((ROOT / s).is_dir() for s in SCOPES)


def test_no_private_markers_in_shared_programs():
    assert [h for s in SCOPES for h in hits(ROOT / s)] == []


def test_scan_finds_a_planted_marker(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    assert hits(tmp_path) == []
    (tmp_path / "b.json").write_text('{"owner": "' + "Kau" + 'ki"}\n')
    (tmp_path / "c.md").write_text("see " + "/Users" + "/someone/x\n")
    assert len(hits(tmp_path)) == 2


def test_extra_markers_come_from_the_environment(tmp_path, monkeypatch):
    (tmp_path / "a.md").write_text("built on hostname-one\n")
    assert hits(tmp_path) == []
    monkeypatch.setenv("PRIVATE_MARKERS", "Hostname-One, ")
    assert len(hits(tmp_path)) == 1
