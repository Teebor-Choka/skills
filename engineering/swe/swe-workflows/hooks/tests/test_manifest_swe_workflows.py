"""Every hook the manifest declares exists, is executable and declares what it enforces; hooks.json calls
exactly those scripts. The full rendering check is the hooks-manifest flake check."""
import json
import os
import unittest

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def load(name):
    with open(os.path.join(HOOKS, name)) as f:
        return json.load(f)


class Manifest(unittest.TestCase):
    def test_scripts_exist_and_are_executable(self):
        for h in load("manifest.json")["hooks"]:
            with self.subTest(hook=h["id"]):
                path = os.path.join(HOOKS, "..", h["script"])
                self.assertTrue(os.access(path, os.X_OK), path)
                self.assertIn(h["enforce"], ("block", "warn"))

    def test_ids_are_unique(self):
        ids = [h["id"] for h in load("manifest.json")["hooks"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_hooks_json_runs_the_manifest_scripts(self):
        want = sorted(h["script"] for h in load("manifest.json")["hooks"])
        got = sorted(c["command"].replace('"${CLAUDE_PLUGIN_ROOT}/', "").rstrip('"')
                     for groups in load("hooks.json")["hooks"].values() for g in groups for c in g["hooks"])
        self.assertEqual(got, want)

    def test_hooks_that_deny_are_marked_block(self):
        # A hook that can deny must say so: the manifest, not the script, tells a harness whether to wait for it.
        blockers = {"git-guard", "git-guard-worktree", "pr-poll-reminder", "worktree-path-guard", "skill-gate",
                    "policy-gate"}
        for h in load("manifest.json")["hooks"]:
            if h["id"] in blockers:
                self.assertEqual(h["enforce"], "block", h["id"])


if __name__ == "__main__":
    unittest.main()
