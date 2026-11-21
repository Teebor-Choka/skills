"""Tests for hooks/hook-doctor.py. Run: python3 -m pytest hooks/tests

hook-doctor checks the plugin(s) it can see: the manifest is valid, every script it names exists and is
executable, and hooks.json points at scripts that exist. It never reads ~/.claude/settings.json.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "hook-doctor.py")
GOOD = {"hooks": [
    {"id": "a", "event": "tool.before", "tools": ["shell"], "script": "hooks/a.sh", "enforce": "block"},
    {"id": "b", "event": "session.start", "matcher": "startup", "script": "hooks/b.py", "timeout": 10,
     "enforce": "warn"},
]}


def hooks_json(*scripts):
    return {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": f'"${{CLAUDE_PLUGIN_ROOT}}/{s}"'} for s in scripts]}]}}


class HookDoctor(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.n = 0

    def plugin(self, manifest=GOOD, hooks=None, scripts=("hooks/a.sh", "hooks/b.py"), executable=True,
               raw_manifest=None):
        self.n += 1
        root = os.path.join(self.tmp.name, f"plugin{self.n}")
        os.makedirs(os.path.join(root, "hooks"))
        if raw_manifest is not None:
            with open(os.path.join(root, "hooks", "manifest.json"), "w") as f:
                f.write(raw_manifest)
        elif manifest is not None:
            with open(os.path.join(root, "hooks", "manifest.json"), "w") as f:
                json.dump(manifest, f)
        if hooks is None:
            hooks = hooks_json("hooks/a.sh")
        with open(os.path.join(root, "hooks", "hooks.json"), "w") as f:
            json.dump(hooks, f)
        for s in scripts:
            path = os.path.join(root, s)
            with open(path, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(path, 0o755 if executable else 0o644)
        return root

    def run_hook(self, *roots, env=None, stdin="{}", check=True):
        roots = ("--check", *roots) if check else roots
        e = {**{k: v for k, v in os.environ.items() if not k.startswith(("AGENT_", "CLAUDE_"))},
             "HOME": os.path.join(self.tmp.name, "nohome"), **(env or {})}
        return subprocess.run([sys.executable, HOOK, *roots], input=stdin, capture_output=True, text=True,
                              timeout=20, env=e)

    def test_clean_plugin_is_silent_and_zero(self):
        r = self.run_hook(self.plugin())
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_e1_hook_mode_reports_as_additional_context_and_exits_zero(self):
        # Claude Code adds SessionStart stdout to the context only on exit 0.
        r = self.run_hook(self.plugin(scripts=("hooks/a.sh",)), check=False)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn("hooks/b.py", out["additionalContext"])

    def test_e1_hook_mode_is_silent_when_clean(self):
        r = self.run_hook(self.plugin(), check=False)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_e1_check_flag_prints_plain_text_and_exits_one(self):
        r = self.run_hook(self.plugin(scripts=("hooks/a.sh",)))
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith(self.tmp.name), r.stdout)

    def test_e5_plugin_root_commands_in_settings_are_unverifiable_not_missing(self):
        path = self.settings(self.settings_hooks('"${CLAUDE_PLUGIN_ROOT}/hooks/x.sh"', "$CLAUDE_PLUGIN_ROOT/y.sh"))
        r = self.run_hook(self.plugin(), "--settings", path)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertIn("unverifiable", r.stdout)
        self.assertNotIn("does not exist", r.stdout)

    def test_e5_a_set_plugin_root_is_used_to_resolve(self):
        root = self.plugin()
        path = self.settings(self.settings_hooks('"${CLAUDE_PLUGIN_ROOT}/hooks/a.sh"'))
        self.assertEqual(self.run_hook(root, "--settings", path, env={"CLAUDE_PLUGIN_ROOT": root}).stdout, "")
        bad = self.settings(self.settings_hooks('"${CLAUDE_PLUGIN_ROOT}/hooks/gone.sh"'), "b.json")
        r = self.run_hook(root, "--settings", bad, env={"CLAUDE_PLUGIN_ROOT": root})
        self.assertEqual(r.returncode, 1)
        self.assertIn("gone.sh", r.stdout)

    def test_missing_script_is_named(self):
        r = self.run_hook(self.plugin(scripts=("hooks/a.sh",)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("hooks/b.py", r.stdout)
        self.assertIn("does not exist", r.stdout)

    def test_script_that_is_not_executable_is_named(self):
        r = self.run_hook(self.plugin(executable=False))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not executable", r.stdout)

    def test_hooks_json_target_must_exist(self):
        r = self.run_hook(self.plugin(hooks=hooks_json("hooks/a.sh", "hooks/gone.sh")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("hooks.json", r.stdout)
        self.assertIn("gone.sh", r.stdout)

    def test_manifest_that_is_not_json_is_reported(self):
        r = self.run_hook(self.plugin(raw_manifest="{"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("manifest.json", r.stdout)

    def test_manifest_rules(self):
        cases = {
            "missing id": ({"event": "tool.before", "script": "hooks/a.sh", "enforce": "warn"}, "id"),
            "unknown event": ({"id": "x", "event": "bogus", "script": "hooks/a.sh", "enforce": "warn"}, "event"),
            "bad enforce": ({"id": "x", "event": "stop", "script": "hooks/a.sh", "enforce": "maybe"}, "enforce"),
            "absolute script": ({"id": "x", "event": "stop", "script": "/etc/x", "enforce": "warn"}, "script"),
            "dotdot script": ({"id": "x", "event": "stop", "script": "../x", "enforce": "warn"}, "script"),
            "dollar in script": ({"id": "x", "event": "stop", "script": "hooks/$a", "enforce": "warn"}, "script"),
            "tools on session": ({"id": "x", "event": "session.start", "tools": ["shell"], "script": "hooks/a.sh",
                                  "enforce": "warn"}, "tools"),
            "unknown tool": ({"id": "x", "event": "tool.before", "tools": ["nope"], "script": "hooks/a.sh",
                              "enforce": "warn"}, "tool"),
            "compact with matcher": ({"id": "x", "event": "compact", "matcher": "m", "script": "hooks/a.sh",
                                      "enforce": "warn"}, "compact"),
        }
        for name, (hook, needle) in cases.items():
            with self.subTest(name):
                r = self.run_hook(self.plugin(manifest={"hooks": [hook]}))
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(needle, r.stdout)

    def test_duplicate_ids_are_reported(self):
        h = {"id": "a", "event": "stop", "script": "hooks/a.sh", "enforce": "warn"}
        r = self.run_hook(self.plugin(manifest={"hooks": [h, h]}))
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate", r.stdout)

    def test_checks_every_root_given_and_labels_the_problem(self):
        good, bad = self.plugin(), self.plugin(scripts=("hooks/a.sh",))
        r = self.run_hook(good, bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn(bad, r.stdout)
        self.assertNotIn(good, r.stdout)

    def test_roots_from_the_env_list(self):
        bad = self.plugin(scripts=("hooks/a.sh",))
        r = self.run_hook(env={"AGENT_PLUGIN_ROOTS": os.pathsep.join([self.plugin(), bad])})
        self.assertEqual(r.returncode, 1)
        self.assertIn(bad, r.stdout)

    def test_default_root_is_the_plugin_that_holds_the_script(self):
        # Run with no roots: the doctor checks its own plugin (this one), which must be healthy.
        r = self.run_hook()
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def settings(self, doc, name="settings.json", raw=None):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w") as f:
            f.write(raw if raw is not None else json.dumps(doc))
        return path

    @staticmethod
    def settings_hooks(*cmds, event="PreToolUse"):
        return {"hooks": {event: [{"matcher": "Bash", "hooks": [{"type": "command", "command": c} for c in cmds]}]}}

    def test_never_reads_settings_unless_told_to(self):
        home = os.path.join(self.tmp.name, "nohome")
        os.makedirs(os.path.join(home, ".claude"))
        with open(os.path.join(home, ".claude", "settings.json"), "w") as f:
            json.dump(self.settings_hooks("/no/such/hook"), f)
        r = self.run_hook(self.plugin())
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_d5_settings_files_come_from_the_flag_or_the_env(self):
        bad = self.settings(self.settings_hooks("/no/such/hook-xyz"), "a.json")
        for r in (self.run_hook(self.plugin(), "--settings", bad),
                  self.run_hook(self.plugin(), env={"AGENT_SETTINGS_FILES": bad})):
            self.assertEqual(r.returncode, 1)
            self.assertIn("/no/such/hook-xyz", r.stdout)
            self.assertIn("PreToolUse", r.stdout)
            self.assertIn(bad, r.stdout)

    def test_d5_home_and_tilde_are_expanded_in_settings_commands(self):
        home = os.path.join(self.tmp.name, "nohome")
        os.makedirs(os.path.join(home, "hooks"))
        present = os.path.join(home, "hooks", "present")
        open(present, "w").close()
        ok = self.settings(self.settings_hooks("$HOME/hooks/present", "~/hooks/present --flag", "${HOME}/hooks/present"))
        r = self.run_hook(self.plugin(), "--settings", ok)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        bad = self.settings(self.settings_hooks("$HOME/hooks/gone-d5"), "b.json")
        r = self.run_hook(self.plugin(), "--settings", bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn("gone-d5", r.stdout)

    def test_d5_bare_commands_resolve_on_path(self):
        ok = self.settings(self.settings_hooks("true", "python3 -c pass"))
        self.assertEqual(self.run_hook(self.plugin(), "--settings", ok).returncode, 0)
        bad = self.settings(self.settings_hooks("no-such-command-d5"), "b.json")
        r = self.run_hook(self.plugin(), "--settings", bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no-such-command-d5", r.stdout)
        self.assertIn("PATH", r.stdout)

    def test_d5_malformed_files_are_problems_not_tracebacks(self):
        shapes = {"top-level list": "[]", "string group": '{"hooks": {"Stop": ["x"]}}',
                  "hooks is a list": '{"hooks": []}', "hook entry is a string": '{"hooks": {"Stop": [{"hooks": ["x"]}]}}',
                  "command is a number": '{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": 5}]}]}}',
                  "not json": "{", "null": "null"}
        for name, raw in shapes.items():
            with self.subTest(name):
                path = self.settings(None, "m.json", raw=raw)
                r = self.run_hook(self.plugin(), "--settings", path)
                self.assertNotIn("Traceback", r.stderr)
                self.assertEqual(r.stderr, "")
                self.assertIn(r.returncode, (0, 1))
        self.assertEqual(self.run_hook(self.plugin(), "--settings", self.settings(None, "n.json", raw="{")).returncode, 1)

    def test_d5_malformed_plugin_hooks_json_is_reported(self):
        for hooks in ([], {"hooks": {"PreToolUse": ["x"]}}, {"hooks": []}, {"hooks": {"PreToolUse": [{"hooks": "x"}]}}):
            with self.subTest(hooks=hooks):
                root = self.plugin(hooks=hooks)
                r = self.run_hook(root)
                self.assertEqual(r.stderr, "")
                self.assertNotIn("Traceback", r.stdout)
        root = self.plugin(hooks=[])
        self.assertEqual(self.run_hook(root).returncode, 1)

    def test_d5_missing_explicit_settings_file_is_reported(self):
        r = self.run_hook(self.plugin(), "--settings", os.path.join(self.tmp.name, "absent.json"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("absent.json", r.stdout)

    def test_a_root_without_hooks_is_reported_not_crashed(self):
        empty = os.path.join(self.tmp.name, "empty")
        os.makedirs(empty)
        r = self.run_hook(empty)
        self.assertEqual(r.returncode, 1)
        self.assertIn("manifest.json", r.stdout)
        self.assertEqual(r.stderr, "")


if __name__ == "__main__":
    unittest.main()
