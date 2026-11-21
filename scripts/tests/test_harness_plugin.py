"""The policy skill lives in the `harness` plugin, and its loader resolves from there and from its callers."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "ai" / "harness"
LOADER = HARNESS / "skills" / "policy" / "policy_loader.py"
RESOLVE_INPUT = ROOT / "engineering/design/skills/architect/scripts/resolve_input.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_harness_is_declared_in_the_marketplace_with_a_valid_skill():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["source"] == "./ai/harness")
    plugin = json.loads((HARNESS / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == entry["name"] == "harness"
    assert plugin["version"] == entry["metadata"]["version"]
    skill = (HARNESS / "skills" / "policy" / "SKILL.md").read_text()
    assert skill.startswith("---\nname: policy\n")
    assert "| `harness`" in (ROOT / "README.md").read_text()


def test_loader_resolves_from_the_new_place(tmp_path):
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "policy.md").write_text("---\ngate: tests\n---\n")
    loader = load(LOADER, "policy_loader_harness")
    assert loader.get(loader.resolve(str(tmp_path)), "gate") == "tests"


def test_architect_finds_the_loader_in_the_repo_layout():
    resolve_input = load(RESOLVE_INPUT, "resolve_input_harness")
    found = resolve_input.find_loader()
    assert found is not None and Path(found).resolve() == LOADER.resolve()
