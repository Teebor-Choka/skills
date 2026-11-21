"""Tests for hooks/long-command-nudge.py. Run: python3 -m pytest hooks/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "long-command-nudge.py")

SLOW = [
    "nix build .#myhost",
    "nix flake check -L",
    "nix --extra-experimental-features flakes build",
    "cargo build --release",
    "cargo test --workspace",
    "cargo nextest run",
    "docker build -t x .",
    "docker buildx build .",
    "pytest -x",
    "python3 -m pytest tests",
    "npm test",
    "go test ./...",
    "make test",
    "cd repo && timeout 600 nix build",
    "FOO=1 cargo build",
    "uv run pytest",
    "uv run cargo build --release",
    "uvx pytest",
    "env FOO=1 nix build",
    "timeout 600 cargo test",
    "sudo nix build",
    "nice -n 5 cargo build",
    "time cargo test",
    "nohup nix flake check",
    "cat <<< x; nix build",
    "echo $((1 << 3)); cargo test",
    "x=$((1 << 3)) && nix build",
]
FAST = [
    "ls -la",
    "git status",
    "nix fmt",
    "nix eval .#x",
    "cargo check",
    "cargo fmt",
    "docker ps",
    "echo nix build",
    'echo "cargo test"',
    "git commit -F - <<'EOF'\nrun nix build and cargo test\nEOF",
    "grep -r 'nix build' docs",
    "ssh host nix build",
    "ssh host 'cargo test'",
    "uv pip install pytest",
    "uv run python -c 'print(1)'",
    "env FOO=1 ls",
    "timeout 5 echo nix build",
    "nice -n 5 git status",
    "cat <<< 'nix build'",
]


def payload(command, session="s1", **extra):
    return {"tool_name": "Bash", "session_id": session, "tool_input": {"command": command, **extra}}


class LongCommandExpectation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def run_hook(self, data=None, raw=None, tmpdir=None):
        env = {**os.environ, "TMPDIR": self.tmp if tmpdir is None else tmpdir}
        return subprocess.run([sys.executable, HOOK], input=raw if raw is not None else json.dumps(data),
                              capture_output=True, text=True, timeout=20, env=env)

    def context(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", out)  # advisory only
        return out["additionalContext"]

    def assert_silent(self, r):
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def test_slow_shapes_advise(self):
        for cmd in SLOW:
            with self.subTest(cmd=cmd):
                text = self.context(self.run_hook(payload(cmd, session="slow-" + str(abs(hash(cmd))))))
                for needle in ("expected duration", "deadline", "run_in_background"):
                    self.assertIn(needle, text)

    def test_e4_here_string_and_shift_do_not_start_a_heredoc(self):
        # `<<<` and `1 << 3` must not swallow the lines after them: a real build on the next line is seen.
        for cmd in ("cat <<< x\nnix build", "echo $((1 << 3))\ncargo test", "x=$((1 << 3))\nnix build"):
            with self.subTest(cmd=cmd):
                self.context(self.run_hook(payload(cmd, session="e4-" + str(abs(hash(cmd))))))

    def test_e4_shift_assign_does_not_start_a_heredoc(self):
        self.context(self.run_hook(payload("x=1; x <<= 2\nnix build", session="e4-shl")))

    def test_e4_a_real_heredoc_body_is_still_text(self):
        self.assert_silent(self.run_hook(payload("cat <<EOF\nnix build\nEOF", session="e4-real")))
        self.assert_silent(self.run_hook(payload("cat <<-'EOF'\n\tcargo test\n\tEOF", session="e4-real2")))

    def test_fast_commands_silent(self):
        for cmd in FAST:
            with self.subTest(cmd=cmd):
                self.assert_silent(self.run_hook(payload(cmd, session="fast-" + str(abs(hash(cmd))))))

    def test_background_run_silent(self):
        self.assert_silent(self.run_hook(payload("nix build", run_in_background=True)))

    def test_once_per_session(self):
        self.context(self.run_hook(payload("nix build")))
        self.assert_silent(self.run_hook(payload("cargo test")))
        self.context(self.run_hook(payload("cargo test", session="s2")))

    def test_silent_command_does_not_use_up_the_session_advice(self):
        self.assert_silent(self.run_hook(payload("ls")))
        self.context(self.run_hook(payload("nix build")))

    def test_marker_uses_the_agent_prefix(self):
        self.context(self.run_hook(payload("nix build", session="s7")))
        self.assertEqual(os.listdir(self.tmp), ["agent-long-command-expectation.s7"])

    def test_hostile_session_id_stays_inside_tmpdir(self):
        self.context(self.run_hook(payload("nix build", session="../../etc/x y")))
        self.assertEqual(os.listdir(self.tmp)[0].count("/"), 0)
        self.assertEqual(len(os.listdir(self.tmp)), 1)

    def test_empty_tmpdir_falls_back(self):
        # TMPDIR="" must not make the marker a relative path in the cwd.
        before = set(os.listdir(os.getcwd()))
        self.addCleanup(lambda: os.path.exists("/tmp/agent-long-command-expectation.empty-tmp-" + os.path.basename(self.tmp))
                        and os.remove("/tmp/agent-long-command-expectation.empty-tmp-" + os.path.basename(self.tmp)))
        self.context(self.run_hook(payload("nix build", session="empty-tmp-" + os.path.basename(self.tmp)), tmpdir=""))
        self.assertEqual(set(os.listdir(os.getcwd())), before)

    def test_d8_a_planted_symlink_is_not_followed(self):
        victim = os.path.join(self.tmp, "victim")
        with open(victim, "w") as f:
            f.write("VICTIM")
        os.symlink(victim, os.path.join(self.tmp, "agent-long-command-expectation.s1"))
        r = self.run_hook(payload("nix build"))
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(victim) as f:
            self.assertEqual(f.read(), "VICTIM")

    def test_d8_a_dangling_symlink_is_not_written_through(self):
        target = os.path.join(self.tmp, "created-by-attacker")
        os.symlink(target, os.path.join(self.tmp, "agent-long-command-expectation.s1"))
        r = self.run_hook(payload("nix build"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(os.path.exists(target))

    def test_d8_session_less_marker_name_includes_the_uid(self):
        self.context(self.run_hook({"tool_name": "Bash", "tool_input": {"command": "nix build"}}))
        self.assertEqual(os.listdir(self.tmp), [f"agent-long-command-expectation.nosession-{os.getuid()}"])

    def test_unwritable_marker_dir_fails_open(self):
        self.assert_silent(self.run_hook(payload("nix build"), tmpdir="/nonexistent/dir"))

    def test_other_tool_and_malformed_input_fail_open(self):
        self.assert_silent(self.run_hook({"tool_name": "Read", "tool_input": {"command": "nix build"}}))
        self.assert_silent(self.run_hook({"tool_name": "Bash", "tool_input": {}}))
        self.assert_silent(self.run_hook({"tool_name": "Bash", "tool_input": {"command": 5}}))
        self.assert_silent(self.run_hook(payload("echo 'unterminated nix build")))
        for raw in ("", "not json", "[]", '{"tool_name":"Bash"}'):
            with self.subTest(raw=raw):
                self.assert_silent(self.run_hook(raw=raw))


if __name__ == "__main__":
    unittest.main()
