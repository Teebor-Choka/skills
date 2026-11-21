"""render-hooks.sh: renders <plugin>/hooks/manifest.json to hooks/hooks.json, rejects bad input."""

import json
import os
import shutil
import subprocess

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
SCRIPT = os.path.join(ROOT, "scripts", "render-hooks.sh")
PLUGIN = os.path.join(ROOT, "engineering", "swe", "swe-workflows")


def run(*args):
    return subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True)


def test_needs_an_argument():
    assert run().returncode == 2


def test_rejects_a_directory_without_a_manifest(tmp_path):
    r = run(str(tmp_path))
    assert r.returncode == 2
    assert "hooks/manifest.json" in r.stderr


@pytest.mark.skipif(shutil.which("nix") is None or not os.path.exists(os.path.join(ROOT, ".git")),
                    reason="needs nix and a checkout (the pinned agent-env input)")
def test_regenerates_the_committed_hooks_json(tmp_path):
    plugin = tmp_path / "plugin"
    shutil.copytree(PLUGIN, plugin)
    (plugin / "hooks" / "hooks.json").write_text("{}")
    r = run(str(plugin))
    assert r.returncode == 0, r.stderr
    with open(os.path.join(PLUGIN, "hooks", "hooks.json")) as f:
        want = json.load(f)
    assert json.loads((plugin / "hooks" / "hooks.json").read_text()) == want
