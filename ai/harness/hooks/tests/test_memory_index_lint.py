"""Tests for hooks/memory-index-lint.py. Run: python3 -m pytest hooks/tests

Inputs come from the SessionStart payload (transcript_path: the memory index sits beside it in
memory/MEMORY.md) and from the environment (AGENT_MEMORY_FILES, AGENT_SKILLS_DIRS), never from ~/.claude.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memory-index-lint.py")
DANGLING = ("All prior entries superseded: distilled into the `ghost-skill` skill's "
            "`references/notes.md`.\n")


class MemoryIndexLint(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        self.skills = os.path.join(self.root, "skills")
        os.makedirs(self.skills)

    def memory(self, project, text):
        """A memory index at <root>/projects/<project>/memory/MEMORY.md; returns (path, transcript_path)."""
        pdir = os.path.join(self.root, "projects", project)
        os.makedirs(os.path.join(pdir, "memory"), exist_ok=True)
        path = os.path.join(pdir, "memory", "MEMORY.md")
        with open(path, "w") as f:
            f.write(text)
        return path, os.path.join(pdir, "session.jsonl")

    def skill(self, *rel):
        d = os.path.join(self.skills, *rel)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write("---\nname: x\n---\n")

    def run_hook(self, transcript=None, skills="default", payload=None, raw=None, check=True, **env):
        e = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_")}
        e["HOME"] = os.path.join(self.root, "nohome")  # a hook that reads ~/.claude would find nothing
        if skills == "default":
            e["AGENT_SKILLS_DIRS"] = self.skills
        elif skills:
            e["AGENT_SKILLS_DIRS"] = skills
        e.update(env)
        if payload is None:
            payload = {"transcript_path": transcript} if transcript else {}
        return subprocess.run([sys.executable, HOOK, *(["--check"] if check else [])], input=raw if raw is not None else json.dumps(payload),
                              capture_output=True, text=True, timeout=20, env=e)

    def test_dangling_skill_is_reported_with_file_and_name(self):
        path, transcript = self.memory("-p1", DANGLING)
        r = self.run_hook(transcript)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ghost-skill", r.stdout)
        self.assertIn(path, r.stdout)
        self.assertNotIn("notes", r.stdout.replace(path, ""))  # a reference path is not a skill

    def test_e1_hook_mode_reports_as_additional_context_and_exits_zero(self):
        _, transcript = self.memory("-p1", DANGLING)
        r = self.run_hook(transcript, check=False)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn("ghost-skill", out["additionalContext"])

    def test_e1_hook_mode_is_silent_when_clean_and_says_when_unconfigured(self):
        _, transcript = self.memory("-p1", DANGLING)
        self.skill("ghost-skill")
        self.assertEqual(self.run_hook(transcript, check=False).stdout, "")
        r = self.run_hook(transcript, skills=None, check=False)
        self.assertEqual(r.returncode, 0)
        self.assertIn("AGENT_SKILLS_DIRS", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_existing_skill_is_quiet(self):
        _, transcript = self.memory("-p1", DANGLING)
        self.skill("ghost-skill")
        r = self.run_hook(transcript)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_plugin_skill_with_namespace_resolves_on_its_last_part(self):
        _, transcript = self.memory("-p1", "Use the `git:workflow` skill for PRs.\n")
        self.skill("git", "skills", "workflow")
        self.assertEqual(self.run_hook(transcript).stdout, "")

    def test_namespaced_skill_missing_is_reported(self):
        _, transcript = self.memory("-p1", "Use the `git:workflow` skill for PRs.\n")
        r = self.run_hook(transcript)
        self.assertEqual(r.returncode, 1)
        self.assertIn("git:workflow", r.stdout)

    def test_skill_name_before_the_word_form_is_found(self):
        _, transcript = self.memory("-p1", "Load skill `ghost-skill` first.\n")
        self.assertIn("ghost-skill", self.run_hook(transcript).stdout)

    def test_backticked_words_that_are_not_skills_are_ignored(self):
        _, transcript = self.memory("-p1", "Run `nix build`, read `references/a.md`. The `foo` tool and a skill list.\n")
        r = self.run_hook(transcript)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_each_dangling_name_is_listed_once_per_file(self):
        _, transcript = self.memory("-p1", DANGLING + "Again the `ghost-skill` skill.\n")
        self.assertEqual(self.run_hook(transcript).stdout.count("ghost-skill"), 1)

    def test_memory_files_from_the_env_glob(self):
        path, _ = self.memory("-p1", DANGLING)
        self.memory("-p2", "The `other-ghost` skill.\n")
        r = self.run_hook(None, AGENT_MEMORY_FILES=os.path.join(self.root, "projects", "*", "memory", "MEMORY.md"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("ghost-skill", r.stdout)
        self.assertIn("other-ghost", r.stdout)

    def test_only_the_session_memory_is_read_when_given_a_transcript(self):
        _, t1 = self.memory("-p1", DANGLING)
        self.memory("-p2", "The `other-ghost` skill.\n")
        out = self.run_hook(t1).stdout
        self.assertIn("ghost-skill", out)
        self.assertNotIn("other-ghost", out)

    def test_d6_without_skill_roots_one_line_names_the_variable(self):
        _, transcript = self.memory("-p1", DANGLING)
        r = self.run_hook(transcript, skills=None)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertEqual(len(r.stdout.strip().splitlines()), 1)
        self.assertIn("AGENT_SKILLS_DIRS", r.stdout)

    def test_d6_the_singular_name_is_an_alias(self):
        _, transcript = self.memory("-p1", DANGLING)
        r = self.run_hook(transcript, skills=None, AGENT_SKILLS_DIR=self.skills)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ghost-skill", r.stdout)
        self.skill("ghost-skill")
        self.assertEqual(self.run_hook(transcript, skills=None, AGENT_SKILLS_DIR=self.skills).stdout, "")

    def test_never_reads_home_claude(self):
        self.skill("anything")
        home = os.path.join(self.root, "nohome")
        os.makedirs(os.path.join(home, ".claude", "projects", "-p9", "memory"))
        with open(os.path.join(home, ".claude", "projects", "-p9", "memory", "MEMORY.md"), "w") as f:
            f.write(DANGLING)
        r = self.run_hook(None)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_memory_file_is_never_modified(self):
        path, transcript = self.memory("-p1", DANGLING)
        before = os.stat(path)
        self.run_hook(transcript)
        after = os.stat(path)
        self.assertEqual((before.st_mtime_ns, before.st_size), (after.st_mtime_ns, after.st_size))
        with open(path) as f:
            self.assertEqual(f.read(), DANGLING)

    def test_no_memory_and_junk_input_are_quiet(self):
        for kw in ({"payload": {"transcript_path": os.path.join(self.root, "none", "s.jsonl")}},
                   {"raw": "not json"}, {"raw": "[]"}, {"raw": ""}):
            with self.subTest(kw=kw):
                r = self.run_hook(None, **kw)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_empty_unreadable_and_non_utf8_memory_files_do_not_crash(self):
        _, t1 = self.memory("-p1", "")
        path2, _ = self.memory("-p2", DANGLING)
        os.chmod(path2, 0)
        self.addCleanup(os.chmod, path2, 0o644)
        path3, _ = self.memory("-p3", "")
        with open(path3, "wb") as f:
            f.write(b"\xff\xfe`x` skill\n")
        r = self.run_hook(None, AGENT_MEMORY_FILES=os.path.join(self.root, "projects", "*", "memory", "MEMORY.md"))
        self.assertEqual((r.returncode, r.stderr), (1, ""))
        self.assertIn("skill `x` not found", r.stdout)  # the non-UTF-8 file is still linted
        self.assertNotIn(path2, r.stdout)  # the unreadable file is skipped


if __name__ == "__main__":
    unittest.main()
