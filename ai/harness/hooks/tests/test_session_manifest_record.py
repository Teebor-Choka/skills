"""Tests for hooks/session-manifest-record.py. Run: python3 -m pytest hooks/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "session-manifest-record.py")


def touch(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class SessionManifest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = os.path.realpath(self._tmp.name)
        self.org = os.path.join(self.home, "src", "org")
        self.repo = os.path.join(self.org, "repo")
        self.global_skills = os.path.join(self.home, "global-skills")
        for name in ("g1", "g2"):
            touch(f"{self.global_skills}/{name}/SKILL.md", "global")
        touch(f"{self.org}/.claude/skills/orgskill/SKILL.md", "SECRET-BODY")
        touch(f"{self.org}/.claude/skills/notaskill/README.md", "no SKILL.md here")
        touch(f"{self.repo}/.claude/skills/reposkill/SKILL.md", "SECRET-BODY")
        touch(f"{self.org}/CLAUDE.md")
        touch(f"{self.repo}/AGENTS.md")
        touch(f"{self.home}/CLAUDE.md")
        subprocess.run(["git", "init", "-q", self.repo], check=True)

    def tearDown(self):
        self._tmp.cleanup()

    def run_hook(self, cwd, skills_dir="default", payload=None, raw=None, proc_cwd=None, **env):
        e = {k: v for k, v in os.environ.items()
             if not k.startswith("ANTHROPIC_") and not k.startswith("AGENT_") and k != "CLAUDE_PROJECT_DIR"}
        e["HOME"] = self.home
        if skills_dir == "default":
            e["AGENT_SKILLS_DIRS"] = self.global_skills
        elif skills_dir:
            e["AGENT_SKILLS_DIRS"] = skills_dir
        e.update(env)
        data = raw if raw is not None else json.dumps(payload if payload is not None else {"cwd": cwd})
        r = subprocess.run([sys.executable, HOOK], input=data, cwd=proc_cwd or cwd, env=e,
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        return out["additionalContext"]

    def test_one_line(self):
        self.assertNotIn("\n", self.run_hook(self.repo))

    def test_instruction_files_walk_up(self):
        ctx = self.run_hook(self.repo)
        for rel in ("~/src/org/repo/AGENTS.md", "~/src/org/CLAUDE.md", "~/CLAUDE.md"):
            self.assertIn(rel, ctx)

    def test_cwd_comes_from_the_payload_not_the_process(self):
        ctx = self.run_hook(self.repo, proc_cwd=self.home, CLAUDE_PROJECT_DIR=self.home)
        self.assertIn("~/src/org/repo/AGENTS.md", ctx)

    def test_env_is_the_fallback_when_the_payload_has_no_cwd(self):
        for kw in ({"payload": {}}, {"raw": "not json"}):
            with self.subTest(kw=kw):
                ctx = self.run_hook(self.repo, proc_cwd=self.home, CLAUDE_PROJECT_DIR=self.repo, **kw)
                self.assertIn("~/src/org/repo/AGENTS.md", ctx)

    def test_global_skill_count_from_env_dir(self):
        self.assertIn("2 skills in ~/global-skills", self.run_hook(self.repo))

    def test_d6_the_singular_name_is_an_alias(self):
        ctx = self.run_hook(self.repo, skills_dir=None, AGENT_SKILLS_DIR=self.global_skills)
        self.assertIn("2 skills in ~/global-skills", ctx)

    def test_d6_unconfigured_manifest_names_the_variable(self):
        ctx = self.run_hook(self.repo, skills_dir=None)
        self.assertIn("AGENT_SKILLS_DIRS", ctx)
        self.assertNotIn("\n", ctx)

    def test_without_a_configured_global_dir_no_count_is_claimed(self):
        ctx = self.run_hook(self.repo, skills_dir=None)
        self.assertNotIn(" skills in ", ctx)
        self.assertNotIn("global-skills", ctx)
        self.assertIn("provider:", ctx)

    def test_several_global_dirs_are_counted_each(self):
        other = os.path.join(self.home, "more")
        touch(f"{other}/g3/SKILL.md")
        ctx = self.run_hook(self.repo, skills_dir=os.pathsep.join([self.global_skills, other]))
        self.assertIn("2 skills in ~/global-skills", ctx)
        self.assertIn("1 skills in ~/more", ctx)

    def test_skill_dir_outside_git_root_listed_by_name(self):
        ctx = self.run_hook(self.repo)
        self.assertIn("~/src/org/.claude/skills", ctx)
        self.assertIn("orgskill", ctx)
        self.assertNotIn("notaskill", ctx)

    def test_skill_dir_inside_git_root_not_listed_by_name(self):
        ctx = self.run_hook(self.repo)
        self.assertIn("~/src/org/repo/.claude/skills (auto-loaded)", ctx)
        self.assertNotIn("reposkill", ctx)

    def test_the_configured_global_dir_is_not_listed_as_an_ancestor_dir(self):
        ctx = self.run_hook(self.repo, skills_dir=f"{self.org}/.claude/skills")
        self.assertIn("1 skills in ~/src/org/.claude/skills", ctx)
        self.assertNotIn("NOT auto-loaded", ctx)

    def test_never_inlines_bodies(self):
        self.assertNotIn("SECRET-BODY", self.run_hook(self.repo))

    def test_no_git_root_only_cwd_is_auto_loaded(self):
        ctx = self.run_hook(self.org)
        self.assertIn("~/src/org/.claude/skills (auto-loaded)", ctx)
        self.assertNotIn("orgskill", ctx)

    def test_provider_native(self):
        self.assertIn("provider: native Anthropic", self.run_hook(self.repo))

    def test_provider_custom_hides_credentials(self):
        ctx = self.run_hook(self.repo, ANTHROPIC_BASE_URL="https://user:hunter2@proxy.example.com:8080/v1")
        self.assertIn("provider: custom base URL (proxy.example.com)", ctx)
        self.assertNotIn("hunter2", ctx)
        self.assertNotIn("user", ctx.split("provider:")[1])

    def test_bare_directory_still_emits(self):
        bare = os.path.join(self.home, "empty")
        os.makedirs(bare)
        self.assertIn("provider:", self.run_hook(bare))

    def test_never_reads_the_home_claude_dir(self):
        touch(f"{self.home}/.claude/skills/homeskill/SKILL.md")
        ctx = self.run_hook(self.repo, skills_dir=None)
        self.assertNotIn("homeskill", ctx)  # the home dir is the harness's own user-level dir, not an ancestor
        self.assertNotIn(" skills in ", ctx)


if __name__ == "__main__":
    unittest.main()
