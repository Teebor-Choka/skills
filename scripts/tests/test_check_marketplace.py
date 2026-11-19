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


def test_hooks_only_plugin_passes():
    r = run({".claude-plugin/marketplace.json": marketplace(), "d/p/.claude-plugin/plugin.json": PLUGIN_JSON,
             "d/p/hooks/hooks.json": "{}"})
    assert r.returncode == 0, r.stderr


def test_plugin_with_neither_skills_nor_hooks_fails():
    r = run({".claude-plugin/marketplace.json": marketplace(), "d/p/.claude-plugin/plugin.json": PLUGIN_JSON})
    assert r.returncode == 1
    assert "no skills" in r.stderr
