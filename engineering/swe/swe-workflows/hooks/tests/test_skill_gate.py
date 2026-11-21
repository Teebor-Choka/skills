"""Tests for hooks/skill-gate. Run: python3 -m pytest engineering/swe/swe-workflows/hooks/tests

The gate reads its rules from skill-gate.rules.json next to the script, so each plugin that ships the
gate contributes its own rows. Most tests run a copy of the hook in a temp dir with a fixture rules file.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
RULES = [
    {"pattern": r"(\.rs|(^|/)Cargo\.(toml|lock))$", "skill": "acme:rust"},
    {"pattern": r"(^|/)\.github/workflows/[^/]+\.ya?ml$", "skill": "acme:ci"},
]


def install(directory, rules=RULES):
    for name in ("skill-gate", "skill_loaded.py"):
        shutil.copy(os.path.join(HOOKS, name), directory)
    if rules is not None:
        with open(os.path.join(directory, "skill-gate.rules.json"), "w") as f:
            json.dump(rules, f) if not isinstance(rules, str) else f.write(rules)
    return os.path.join(directory, "skill-gate")


def run(hook, tmp, path, session="s1", agent=None, transcript=None, tool="Edit", raw=None):
    payload = {"tool_name": tool, "session_id": session, "tool_input": {"file_path": path}}
    if agent:
        payload["agent_id"] = agent
    if transcript:
        payload["transcript_path"] = transcript
    return subprocess.run([sys.executable, hook], input=raw if raw is not None else json.dumps(payload),
                          capture_output=True, text=True, timeout=20, env={**os.environ, "TMPDIR": tmp})


def out(r):
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout else None


def banner(path):
    return json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "text", "text": f"Base directory for this skill: {path}\n\n# body"}]}})


def skill_call(name):
    return json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Skill", "input": {"skill": name}}]}})


class SkillGate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = os.path.join(self._tmp.name, "tmp")
        self.dir = os.path.join(self._tmp.name, "hooks")
        os.makedirs(self.tmp)
        os.makedirs(self.dir)
        self.hook = install(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def hit(self, *a, **kw):
        return run(self.hook, self.tmp, *a, **kw)

    def write(self, rel, *lines):
        path = os.path.join(self._tmp.name, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write("".join(line + "\n" for line in lines))
        return path

    def test_rules_file_maps_paths_to_skills(self):
        cases = {"/r/src/main.rs": "acme:rust", "/r/Cargo.toml": "acme:rust",
                 "/r/.github/workflows/ci.yml": "acme:ci"}
        for i, (path, skill) in enumerate(cases.items()):
            with self.subTest(path=path):
                o = out(self.hit(path, session=f"t{i}"))
                self.assertEqual(o["permissionDecision"], "deny")
                self.assertIn(skill, o["permissionDecisionReason"])
                self.assertIn("Skill tool", o["permissionDecisionReason"])

    def test_rules_come_from_the_file_beside_the_script(self):
        install(self.dir, [{"pattern": r"\.zig$", "skill": "acme:zig"}])
        self.assertEqual(out(self.hit("/r/a.zig"))["permissionDecision"], "deny")
        self.assertIsNone(out(self.hit("/r/a.rs")))

    def test_one_bad_row_drops_only_that_row(self):
        d = os.path.join(self._tmp.name, "partial")
        os.makedirs(d)
        hook = install(d, [{"pattern": "(", "skill": "a:bad-regex"}, {"skill": "a:no-pattern"},
                           {"pattern": r"\.x$"}, "junk", {"pattern": r"\.rs$", "skill": "acme:rust"}])
        r = run(hook, self.tmp, "/r/a.rs")
        self.assertEqual(out(r)["permissionDecision"], "deny")
        self.assertIn("acme:rust", out(r)["permissionDecisionReason"])
        self.assertIn("skill-gate", r.stderr)  # the bad rows are noted, not silent

    def marker(self):
        names = [n for n in os.listdir(self.tmp) if n.startswith("agent-skill-gate-")]
        self.assertEqual(len(names), 1, names)
        return os.path.join(self.tmp, names[0])

    def test_a_marker_older_than_a_day_is_ignored(self):
        import time
        self.assertEqual(out(self.hit("/r/a.rs"))["permissionDecision"], "deny")
        marker = self.marker()
        self.assertIsNone(out(self.hit("/r/b.rs")))  # the one-nudge rule: a fresh marker passes
        old = time.time() - 25 * 3600
        os.utime(marker, (old, old))
        self.assertEqual(out(self.hit("/r/c.rs"))["permissionDecision"], "deny")  # stale: nudge again
        self.assertIsNone(out(self.hit("/r/d.rs")))  # and the retry passes again

    def test_a_marker_under_a_day_old_still_counts(self):
        import time
        self.hit("/r/a.rs")
        marker = self.marker()
        recent = time.time() - 23 * 3600
        os.utime(marker, (recent, recent))
        self.assertIsNone(out(self.hit("/r/b.rs")))

    def test_docstring_states_the_one_nudge_rule(self):
        with open(os.path.join(HOOKS, "skill-gate")) as f:
            doc = f.read().split('"""')[1]
        self.assertIn("one nudge", doc)

    def test_non_string_transcript_path_does_not_crash(self):
        for bad in (123, ["x"], {"a": 1}):
            with self.subTest(bad=bad):
                payload = {"tool_name": "Edit", "tool_input": {"file_path": "/r/a.rs"}, "session_id": "s",
                           "agent_id": "a", "transcript_path": bad}
                r = self.hit("", raw=json.dumps(payload))
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertNotIn("Traceback", r.stderr)

    def test_missing_or_broken_rules_file_fails_open(self):
        for rules in (None, "not json", "{}", '[{"pattern": "(", "skill": "a:b"}]', '[{"skill": "a:b"}]'):
            with self.subTest(rules=rules):
                d = os.path.join(self._tmp.name, f"h{abs(hash(str(rules)))}")
                os.makedirs(d)
                r = run(install(d, rules), self.tmp, "/r/a.rs")
                self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_unmatched_paths_pass(self):
        for path in ("/r/README.md", "/r/src/a.py", "/r/notes.rs.txt", "/r/.github/other.yml"):
            with self.subTest(path=path):
                self.assertIsNone(out(self.hit(path)))

    def test_one_denial_per_skill_per_agent_then_retry_passes(self):
        self.assertEqual(out(self.hit("/r/a.rs"))["permissionDecision"], "deny")
        self.assertIsNone(out(self.hit("/r/b.rs")))  # same skill, same agent
        self.assertEqual(out(self.hit("/r/.github/workflows/ci.yml"))["permissionDecision"], "deny")

    def test_agents_and_sessions_are_gated_separately(self):
        self.hit("/r/a.rs")
        self.assertEqual(out(self.hit("/r/a.rs", agent="sub1"))["permissionDecision"], "deny")
        self.assertEqual(out(self.hit("/r/a.rs", session="s2"))["permissionDecision"], "deny")

    def test_skill_already_loaded_in_transcript_passes_without_denial(self):
        tp = self.write("t.jsonl", skill_call("acme:rust"))
        self.assertIsNone(out(self.hit("/r/a.rs", transcript=tp)))

    def test_a_user_text_block_holding_the_banner_does_not_count(self):
        tp = self.write("t.jsonl", banner("/x/plugin-dirs/acme/skills/rust"))
        self.assertEqual(out(self.hit("/r/a.rs", transcript=tp))["permissionDecision"], "deny")

    def test_other_skill_in_transcript_does_not_count(self):
        tp = self.write("t.jsonl", skill_call("other:thing"))
        self.assertEqual(out(self.hit("/r/a.rs", transcript=tp))["permissionDecision"], "deny")

    def test_early_load_in_a_long_transcript_is_found(self):
        filler = json.dumps({"type": "user", "message": {"content": "x" * 4000}})
        tp = self.write("big.jsonl", skill_call("acme:rust"), *([filler] * 1500))  # load sits ~6 MB from the end
        self.assertIsNone(out(self.hit("/r/a.rs", transcript=tp)))

    def test_a_subagent_is_checked_against_its_own_transcript(self):
        parent = self.write("proj/sid.jsonl", skill_call("acme:rust"))
        self.write("proj/sid/subagents/agent-a1.jsonl", skill_call("other:thing"))
        self.write("proj/sid/subagents/agent-a2.jsonl", skill_call("acme:rust"))
        self.assertEqual(out(self.hit("/r/a.rs", session="sid", agent="a1", transcript=parent))["permissionDecision"],
                         "deny")  # the parent's load does not cover it
        self.assertIsNone(out(self.hit("/r/a.rs", session="sid", agent="a2", transcript=parent)))

    def test_session_and_agent_ids_cannot_escape_the_temp_dir(self):
        self.hit("/r/a.rs", session="../../evil", agent="../x")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "..", "..", "evil")))
        self.assertTrue(all("/" not in n for n in os.listdir(self.tmp)))

    def test_fails_open_on_junk_and_other_tools(self):
        for raw in ("", "not json", "[]", "null", json.dumps({"tool_name": "Edit"}),
                    json.dumps({"tool_name": "Edit", "tool_input": {"file_path": 5}})):
            with self.subTest(raw=raw):
                r = self.hit("", raw=raw)
                self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertIsNone(out(self.hit("/r/a.rs", tool="Read")))
        self.assertEqual(out(self.hit("/r/a.rs", session="w", tool="MultiEdit"))["permissionDecision"], "deny")


class ShippedRules(unittest.TestCase):
    """The rules this plugin contributes name only this plugin's own skills."""

    def test_rows_name_only_this_plugins_skills(self):
        with open(os.path.join(HOOKS, "skill-gate.rules.json")) as f:
            rows = json.load(f)
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row["skill"].startswith("swe-workflows:"), row)

    def test_process_documents_need_the_implement_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            hook = os.path.join(HOOKS, "skill-gate")
            for path in ("/r/.agents/policy.md", "/r/.agents/charter.md"):
                with self.subTest(path=path):
                    o = out(run(hook, tmp, path, session=path.replace("/", "_")))
                    self.assertEqual(o["permissionDecision"], "deny")
                    self.assertIn("swe-workflows:implement", o["permissionDecisionReason"])
            self.assertIsNone(out(run(hook, tmp, "/r/src/a.rs", session="other")))


if __name__ == "__main__":
    unittest.main()
