"""The old procedure format is gone: no file in the tree names it."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Built by concatenation so this file does not match itself.
OLD_TERMS = ("validate_" + "procedure", ".agents/" + "procedures")


SKIP_DIRS = {".git", ".direnv", ".claude", "node_modules", "__pycache__", ".pytest_cache"}


def text_files():
    """Every text file in the repo tree. Walks the disk because the Nix sandbox copy has no .git."""
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath, name)
            if path.is_symlink():
                continue
            try:
                yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue


def test_no_file_refers_to_the_old_format():
    hits = [f"{rel}: {term}" for rel, text in text_files() for term in OLD_TERMS if term in text]
    assert hits == []
