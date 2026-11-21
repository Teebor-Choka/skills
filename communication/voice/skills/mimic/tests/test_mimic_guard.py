"""AT-1: personal data never lands where git would track it; the state dir is private."""

import stat
import subprocess
import unittest

from mimic_fixtures import Sandbox, synth_records, write_jsonl


def git_repo(path, ignore=None):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if ignore is not None:
        (path / ".gitignore").write_text(ignore)
    return path


class StateDirGuard(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.src = self.sb.root / "samples.jsonl"
        write_jsonl(self.src, synth_records(10))

    def tearDown(self):
        self.sb.close()

    def test_default_dir_is_under_config_agents_state_and_private(self):
        r = self.sb.run("ingest.py", "--persona", "pat", self.src)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.sb.home / ".config" / "agents" / "state" / "voice" / "pat"
        self.assertEqual(stat.S_IMODE(d.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((d / "corpus.jsonl").stat().st_mode), 0o600)

    def test_env_override(self):
        base = self.sb.root / "elsewhere"
        r = self.sb.run("ingest.py", "--persona", "pat", self.src, env={"MIMIC_STATE_HOME": str(base)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((base / "pat" / "corpus.jsonl").is_file())

    def test_refuses_an_unignored_path_inside_a_work_tree(self):
        repo = git_repo(self.sb.root / "repo")
        r = self.sb.run("ingest.py", "--state-dir", repo / "state" / "pat", self.src)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("git work tree", r.stderr)
        self.assertFalse((repo / "state").exists(), "nothing may be written before the refusal")

    def test_allows_an_ignored_path_inside_a_work_tree(self):
        repo = git_repo(self.sb.root / "agents", ignore="/*\n!/.gitignore\n!/AGENTS.md\n")
        r = self.sb.run("ingest.py", "--state-dir", repo / "state" / "voice" / "pat", self.src)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((repo / "state" / "voice" / "pat" / "corpus.jsonl").is_file())

    def test_default_dir_inside_a_dotagents_style_repo(self):
        git_repo(self.sb.home / ".config" / "agents", ignore="/*\n!/.gitignore\n")
        r = self.sb.run("ingest.py", "--persona", "pat", self.src)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_refuses_when_the_repo_tracks_the_state_path(self):
        git_repo(self.sb.home / ".config" / "agents", ignore="/*\n!/state/\n")
        r = self.sb.run("ingest.py", "--persona", "pat", self.src)
        self.assertEqual(r.returncode, 3)

    def test_explicit_flag_lets_it_through(self):
        repo = git_repo(self.sb.root / "repo3")
        r = self.sb.run("ingest.py", "--state-dir", repo / "s", "--allow-git-worktree", self.src)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((repo / "s" / "corpus.jsonl").is_file())

    def test_a_dot_git_file_without_a_resolvable_repo_is_refused(self):
        wt = self.sb.root / "worktree"
        wt.mkdir()
        (wt / ".git").write_text("gitdir: /nonexistent/elsewhere\n")
        self.assertEqual(self.sb.run("ingest.py", "--state-dir", wt / "s", self.src).returncode, 3)

    def test_every_writer_has_the_guard(self):
        repo = git_repo(self.sb.root / "repo4")
        for script, args in (("split.py", []), ("profile.py", ["skeleton"]), ("evaluate.py", ["run", "--slice", "test"])):
            r = self.sb.run(script, *args, "--state-dir", repo / "s")
            self.assertEqual(r.returncode, 3, f"{script}: {r.stderr}")

    def test_bad_persona_name_exits_2(self):
        r = self.sb.run("ingest.py", "--persona", "../etc", self.src)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
