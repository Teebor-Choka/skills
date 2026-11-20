"""The old procedure format is gone: no tracked file names it, and the plugin carries its 2.0.0 name."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Built by concatenation so this file does not match itself.
OLD_TERMS = ("validate_" + "procedure", ".agents/" + "procedures")
PLUGIN_DIR = ROOT / "agents" / "operating-model"
NEW_NAME = "organization"


def tracked_text_files():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
    for rel in out.decode().split("\0"):
        path = ROOT / rel
        if rel and path.is_file() and not path.is_symlink():
            try:
                yield rel, path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue


def test_no_tracked_file_refers_to_the_old_format():
    hits = [f"{rel}: {term}" for rel, text in tracked_text_files() for term in OLD_TERMS if term in text]
    assert hits == []


def test_old_skills_are_deleted():
    skills = PLUGIN_DIR / "skills"
    assert not (skills / "procedure").exists()
    assert not (skills / "agents-dir").exists()


def test_plugin_is_renamed_at_2_0_0_everywhere():
    plugin = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["source"] == "./agents/operating-model")
    assert (plugin["name"], plugin["version"]) == (NEW_NAME, "2.0.0")
    assert (entry["name"], entry["metadata"]["version"]) == (NEW_NAME, "2.0.0")
    readme = (ROOT / "README.md").read_text()
    assert f"| `{NEW_NAME}`" in readme and "| `operating-model`" not in readme
