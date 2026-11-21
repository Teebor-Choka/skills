"""Tests for hooks/code-graph-reindex (Stop). Run: python3 -m pytest hooks/tests"""
import json
import os
import signal
import time
import unittest

from cg_support import Sandbox, git, make_repo

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "code-graph-reindex")
INDEX_HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "code-graph-index")


class GitReindex(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def dirty(self):
        with open(os.path.join(self.sb.repo, "a.txt"), "w") as f:
            f.write("x")

    def test_dirty_tree_triggers_one_background_index(self):
        self.dirty()
        r = self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        calls = self.sb.calls_seen(wait=5)
        time.sleep(1.0)  # long enough for a stray second call to land
        calls = self.sb.calls_seen()
        self.assertEqual(len(calls), 1)
        self.assertIn("index_repository", calls[0])
        self.assertIn(self.sb.repo, calls[0])

    def test_clean_tree_does_nothing(self):
        r = self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(self.sb.calls_seen(wait=0.5), [])

    def test_lock_is_released_after_the_index_finishes(self):
        self.dirty()
        self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.sb.calls_seen(wait=5)
        for _ in range(50):
            if not self.sb.locks():
                break
            time.sleep(0.1)
        self.assertEqual(self.sb.locks(), [])

    def test_payload_cwd_wins_over_project_dir_env(self):
        self.dirty()
        self.sb.run(HOOK, {"cwd": self.sb.repo}, CLAUDE_PROJECT_DIR="/nonexistent")
        self.assertEqual(len(self.sb.calls_seen(wait=5)), 1)

    def test_falls_back_to_project_dir_env_without_cwd(self):
        self.dirty()
        self.sb.run(HOOK, {}, CLAUDE_PROJECT_DIR=self.sb.repo)
        self.assertEqual(len(self.sb.calls_seen(wait=5)), 1)

    def test_linked_worktree_edits_leave_the_main_checkout_clean(self):
        wt = os.path.join(self.sb.tmp, "wt")
        git("worktree", "add", "-q", "-b", "feat", wt, cwd=self.sb.repo)
        with open(os.path.join(wt, "b.txt"), "w") as f:
            f.write("x")
        self.sb.run(HOOK, {"cwd": wt})
        self.assertEqual(self.sb.calls_seen(wait=0.5), [])

    def test_silent_outside_a_repo_and_without_binary(self):
        plain = os.path.join(self.sb.tmp, "plain")
        os.makedirs(plain)
        self.assertEqual(self.sb.run(HOOK, {"cwd": plain}).returncode, 0)
        sb = Sandbox(with_binary=False)
        self.addCleanup(sb.cleanup)
        with open(os.path.join(sb.repo, "a.txt"), "w") as f:
            f.write("x")
        r = sb.run(HOOK, {"cwd": sb.repo})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(sb.calls_seen(wait=0.3), [])


def dirty(repo):
    with open(os.path.join(repo, "a.txt"), "w") as f:
        f.write("x")


def args_of(call):
    """The JSON argument the fake graph binary was given."""
    return json.loads(call.partition(" index_repository ")[2])


class Detached(unittest.TestCase):
    """The hook must return while a slow indexer still runs, and must not leave its stdout open."""

    def test_stop_hook_returns_promptly_while_indexing_runs(self):
        sb = Sandbox(slow=3)
        self.addCleanup(sb.cleanup)
        dirty(sb.repo)
        start = time.time()
        r = sb.run(HOOK, {"cwd": sb.repo})
        self.assertLess(time.time() - start, 1.0)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(len(sb.calls_seen(wait=3)), 1)

    def test_session_start_hook_returns_promptly_while_indexing_runs(self):
        sb = Sandbox(slow=3)
        self.addCleanup(sb.cleanup)
        start = time.time()
        r = sb.run(INDEX_HOOK, {"cwd": sb.repo})
        self.assertLess(time.time() - start, 1.0)
        self.assertIn("additionalContext", r.stdout)


class Lock(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(slow=3)
        self.addCleanup(self.sb.cleanup)
        dirty(self.sb.repo)

    def start(self):
        self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.sb.calls_seen(wait=3)

    def lock_pid_file(self):
        (lock,) = self.sb.locks()
        return lock, os.path.join(lock, "pid")

    def test_lock_records_a_live_pid(self):
        self.start()
        _, pid_file = self.lock_pid_file()
        with open(pid_file) as f:
            pid = int(f.read())
        os.kill(pid, 0)  # raises when not alive

    def test_second_run_while_locked_starts_nothing(self):
        self.start()
        self.sb.run(HOOK, {"cwd": self.sb.repo})
        time.sleep(0.7)
        self.assertEqual(len(self.sb.calls_seen()), 1)

    def test_lock_of_a_dead_process_is_reclaimed(self):
        self.start()
        _, pid_file = self.lock_pid_file()
        with open(pid_file) as f:
            os.kill(int(f.read()), signal.SIGKILL)  # no trap runs: the lock stays behind
        time.sleep(0.3)
        self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.assertEqual(len(self.sb.calls_seen(wait=3, n=2)), 2)

    def test_lock_older_than_six_hours_is_reclaimed_even_if_the_pid_is_alive(self):
        self.start()
        lock, pid_file = self.lock_pid_file()
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))  # alive, but the lock is ancient
        old = time.time() - 7 * 3600
        os.utime(lock, (old, old))
        self.sb.run(HOOK, {"cwd": self.sb.repo})
        self.assertEqual(len(self.sb.calls_seen(wait=3, n=2)), 2)

    def test_fresh_lock_of_a_live_foreign_pid_is_respected(self):
        self.start()
        _, pid_file = self.lock_pid_file()
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
        self.sb.run(HOOK, {"cwd": self.sb.repo})
        time.sleep(0.7)
        self.assertEqual(len(self.sb.calls_seen()), 1)

    def test_session_start_hook_takes_the_same_lock(self):
        self.start()
        r = self.sb.run(INDEX_HOOK, {"cwd": self.sb.repo})
        self.assertIn("additionalContext", r.stdout)  # still gives the directive
        time.sleep(0.7)
        self.assertEqual(len(self.sb.calls_seen()), 1)

    def test_lock_names_do_not_collide_for_paths_that_differ_by_slash_or_space(self):
        a = make_repo(os.path.join(self.sb.tmp, "r a"))
        b = make_repo(os.path.join(self.sb.tmp, "r_a"))
        dirty(a)
        dirty(b)
        self.sb.run(HOOK, {"cwd": a})
        self.sb.run(HOOK, {"cwd": b})
        self.assertEqual(len(self.sb.calls_seen(wait=3, n=2)), 2)
        time.sleep(0.5)
        self.assertEqual(len(self.sb.locks()), 2)


class JsonArgument(unittest.TestCase):
    EVIL = 'x","k":"v'

    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)
        self.repo = make_repo(os.path.join(self.sb.tmp, self.EVIL))
        dirty(self.repo)

    def test_reindex_builds_the_argument_with_jq(self):
        self.sb.run(HOOK, {"cwd": self.repo})
        (call,) = self.sb.calls_seen(wait=5)
        self.assertEqual(args_of(call), {"repo_path": self.repo})

    def test_index_builds_the_argument_with_jq(self):
        r = self.sb.run(INDEX_HOOK, {"cwd": self.repo})
        self.assertEqual(r.returncode, 0, r.stderr)
        (call,) = self.sb.calls_seen(wait=5)
        self.assertEqual(args_of(call), {"repo_path": self.repo})


if __name__ == "__main__":
    unittest.main()
