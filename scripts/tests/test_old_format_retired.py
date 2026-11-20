"""The old procedure format is gone: no file in the tree names it, and the plugin carries its 2.x name."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Built by concatenation so this file does not match itself.
OLD_TERMS = ("validate_" + "procedure", ".agents/" + "procedures")
PLUGIN_DIR = ROOT / "agents" / "operating-model"
NEW_NAME = "organization"


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


def test_old_skills_are_deleted():
    skills = PLUGIN_DIR / "skills"
    assert not (skills / "procedure").exists()
    assert not (skills / "agents-dir").exists()


def test_plugin_is_renamed_at_2_x_everywhere():
    plugin = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["source"] == "./agents/operating-model")
    assert plugin["name"] == entry["name"] == NEW_NAME
    assert plugin["version"] == entry["metadata"]["version"]
    assert plugin["version"].split(".")[0] == "2"
    readme = (ROOT / "README.md").read_text()
    assert f"| `{NEW_NAME}`" in readme and "| `operating-model`" not in readme
