"""check-marketplace.py: a plugin needs at least one skill or a hooks/hooks.json."""

import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "check-marketplace.py")


def run(files):
    with tempfile.TemporaryDirectory() as root:
        for rel, body in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(body)
        return subprocess.run([sys.executable, SCRIPT, root], capture_output=True, text=True)


def marketplace():
    plugin = {"name": "p", "source": "./d/p"}
    return json.dumps({"name": "m", "plugins": [plugin]})


PLUGIN_JSON = json.dumps({"name": "p", "version": "1.0.0"})


def test_plugin_with_neither_skills_nor_hooks_fails():
    r = run({".claude-plugin/marketplace.json": marketplace(), "d/p/.claude-plugin/plugin.json": PLUGIN_JSON})
    assert r.returncode == 1
    assert "no skills" in r.stderr


HOOKS_OK = json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}})
MANIFEST_OK = json.dumps({"hooks": [{"id": "a", "event": "stop", "script": "hooks/a", "enforce": "warn"}]})


def hooks_plugin(hooks_json, manifest):
    files = {".claude-plugin/marketplace.json": marketplace(), "d/p/.claude-plugin/plugin.json": PLUGIN_JSON}
    if hooks_json is not None:
        files["d/p/hooks/hooks.json"] = hooks_json
    if manifest is not None:
        files["d/p/hooks/manifest.json"] = manifest
    return run(files)


def test_hooks_plugin_with_valid_hooks_and_manifest_passes():
    r = hooks_plugin(HOOKS_OK, MANIFEST_OK)
    assert r.returncode == 0, r.stderr


def test_invalid_hooks_json_fails():
    r = hooks_plugin("{not json", MANIFEST_OK)
    assert r.returncode == 1
    assert "hooks.json" in r.stderr


def test_empty_object_hooks_json_fails():
    r = hooks_plugin("{}", MANIFEST_OK)
    assert r.returncode == 1
    assert "hooks.json" in r.stderr


def test_hooks_object_without_events_fails():
    r = hooks_plugin(json.dumps({"hooks": {}}), MANIFEST_OK)
    assert r.returncode == 1
    assert "hooks.json" in r.stderr


def test_hooks_json_without_manifest_fails():
    r = hooks_plugin(HOOKS_OK, None)
    assert r.returncode == 1
    assert "manifest.json" in r.stderr


def test_invalid_manifest_json_fails():
    r = hooks_plugin(HOOKS_OK, "{nope")
    assert r.returncode == 1
    assert "manifest.json" in r.stderr


def test_empty_manifest_fails():
    for body in (json.dumps({"hooks": []}), "{}", json.dumps({"hooks": {}})):
        r = hooks_plugin(HOOKS_OK, body)
        assert r.returncode == 1, body
        assert "manifest.json" in r.stderr
