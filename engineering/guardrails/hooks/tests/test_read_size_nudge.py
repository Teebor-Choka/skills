"""Tests for hooks/read-size-nudge. Run: python3 -m pytest hooks/tests"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "read-size-nudge")
_loader = importlib.machinery.SourceFileLoader("read_size_nudge", HOOK)
_spec = importlib.util.spec_from_loader("read_size_nudge", _loader)
rsn = importlib.util.module_from_spec(_spec)
_loader.exec_module(rsn)


class ReadSizeNudge(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def big(self, path):
        return rsn.nudge({"file_path": path}, "s1", self.tmp, size_of=lambda p: 60 * 1024)

    def test_large_whole_file_read_nudges_once(self):
        self.assertIn("60 KB", self.big("/x/spec.md"))
        self.assertEqual(self.big("/x/spec.md"), "")
        self.assertIn("60 KB", self.big("/x/other.md"))

    def test_small_file_silent(self):
        self.assertEqual(rsn.nudge({"file_path": "/x/a"}, "s1", self.tmp, size_of=lambda p: 1024), "")

    def test_ranged_read_silent(self):
        for extra in ({"offset": 10}, {"limit": 50}):
            with self.subTest(extra=extra):
                self.assertEqual(rsn.nudge({"file_path": "/x/b", **extra}, "s1", self.tmp,
                                           size_of=lambda p: 60 * 1024), "")

    def test_missing_file_and_bad_input_silent(self):
        self.assertEqual(rsn.nudge({"file_path": "/no/such/file"}, "s1", self.tmp), "")
        self.assertEqual(rsn.nudge({}, "s1", self.tmp), "")


BIG = 60 * 1024
GRAPH_CALL = json.dumps({"type": "tool_use", "id": "t1", "name": "mcp__codebase-memory-mcp__search_graph", "input": {}})
OTHER_CALL = json.dumps({"type": "tool_use", "id": "t2", "name": "Bash", "input": {}})
SEARCH_ONLY = json.dumps({"type": "tool_use", "id": "t3", "name": "ToolSearch",
                          "input": {"query": "select:mcp__codebase-memory-mcp__search_graph"}})


class GraphFirstDeny(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.transcript = os.path.join(self.tmp, "t.jsonl")
        self.write_transcript(OTHER_CALL)

    def write_transcript(self, *lines):
        with open(self.transcript, "w") as f:
            f.write("\n".join(lines) + "\n")

    def deny(self, path="/x/main.rs", size=BIG, transcript="default", which=lambda n: "/bin/cbm", in_git=lambda p: True,
             **extra):
        return rsn.deny_reason({"file_path": path, **extra},
                               self.transcript if transcript == "default" else transcript,
                               size_of=lambda p: size, which=which, in_git=in_git)

    def test_big_source_read_before_graph_call_denied_with_toolsearch_hint(self):
        reason = self.deny()
        self.assertIn("ToolSearch select:mcp__codebase-memory-mcp__search_graph", reason)
        self.assertIn("get_code_snippet", reason)
        self.assertIn("offset", reason)

    def test_threshold_boundary(self):
        self.assertEqual(self.deny(size=rsn.DENY_THRESHOLD - 1), "")
        self.assertNotEqual(self.deny(size=rsn.DENY_THRESHOLD), "")

    def test_graph_tool_already_used_passes(self):
        self.write_transcript(OTHER_CALL, GRAPH_CALL)
        self.assertEqual(self.deny(), "")

    def test_toolsearch_alone_is_not_a_graph_call(self):
        self.write_transcript(SEARCH_ONLY)
        self.assertNotEqual(self.deny(), "")

    def test_ranged_read_passes(self):
        for extra in ({"offset": 10}, {"limit": 50}):
            with self.subTest(extra=extra):
                self.assertEqual(self.deny(**extra), "")

    def test_non_source_file_passes(self):
        for name in ("/x/spec.md", "/x/data.json", "/x/noext", "/x/Makefile"):
            with self.subTest(name=name):
                self.assertEqual(self.deny(path=name), "")

    def test_source_extensions_case_insensitive(self):
        for name in ("/x/a.py", "/x/a.ts", "/x/a.go", "/x/A.RS"):
            with self.subTest(name=name):
                self.assertNotEqual(self.deny(path=name), "")

    def test_cannot_know_fails_open(self):
        self.assertEqual(self.deny(which=lambda n: None), "")  # graph MCP not installed
        self.assertEqual(self.deny(in_git=lambda p: False), "")  # not in a repo the hook indexes
        self.assertEqual(self.deny(transcript=None), "")
        self.assertEqual(self.deny(transcript="/no/such/transcript"), "")

    def test_missing_file_and_bad_input_pass(self):
        self.assertEqual(rsn.deny_reason({"file_path": "/no/such.rs"}, self.transcript), "")
        self.assertEqual(rsn.deny_reason({}, self.transcript), "")
        self.assertEqual(rsn.deny_reason({"file_path": 5}, self.transcript), "")


class StateFiles(unittest.TestCase):
    def test_marker_uses_agent_prefix(self):
        tmp = tempfile.mkdtemp()
        rsn.nudge({"file_path": "/x/spec.md"}, "pfx", tmp, size_of=lambda p: 60 * 1024)
        self.assertEqual(len(os.listdir(tmp)), 1)
        self.assertTrue(os.listdir(tmp)[0].startswith("agent-read-size-nudge.pfx."))

    def test_empty_tmpdir_falls_back_to_tmp(self):
        # an empty TMPDIR must not turn the marker path into a relative one
        work = tempfile.mkdtemp()
        big = os.path.join(work, "spec.md")
        with open(big, "w") as f:
            f.write("x" * BIG)
        cwd = tempfile.mkdtemp()
        sid = "emptytmp-%d" % os.getpid()
        r = subprocess.run([sys.executable, HOOK], input=json.dumps(
            {"tool_name": "Read", "session_id": sid, "tool_input": {"file_path": big}}),
            capture_output=True, text=True, timeout=20, cwd=cwd, env={**os.environ, "TMPDIR": ""})
        self.assertIn("additionalContext", r.stdout)
        self.assertEqual(os.listdir(cwd), [])
        import glob
        markers = glob.glob("/tmp/agent-read-size-nudge.%s.*" % sid)
        self.assertEqual(len(markers), 1)
        for m in markers:
            os.unlink(m)


class GraphFirstEndToEnd(unittest.TestCase):
    def run_hook(self, payload, path_dirs):
        env = {**os.environ, "PATH": os.pathsep.join(path_dirs), "TMPDIR": tempfile.mkdtemp()}
        return subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True,
                              timeout=20, env=env)

    def test_deny_then_allow_after_graph_call(self):
        tmp = tempfile.mkdtemp()
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", repo], check=True, capture_output=True)
        src = os.path.join(repo, "big.rs")
        with open(src, "w") as f:
            f.write("x" * BIG)
        fakebin = os.path.join(tmp, "bin")
        os.makedirs(fakebin)
        cbm = os.path.join(fakebin, "codebase-memory-mcp")
        with open(cbm, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(cbm, 0o755)
        transcript = os.path.join(tmp, "t.jsonl")
        with open(transcript, "w") as f:
            f.write(OTHER_CALL + "\n")
        payload = {"tool_name": "Read", "session_id": "e2e", "transcript_path": transcript,
                   "tool_input": {"file_path": src}}
        path_dirs = [fakebin, os.path.dirname(shutil.which("git"))]
        out = json.loads(self.run_hook(payload, path_dirs).stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("ToolSearch", out["permissionDecisionReason"])
        with open(transcript, "a") as f:
            f.write(GRAPH_CALL + "\n")
        out = json.loads(self.run_hook(payload, path_dirs).stdout)["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", out)  # falls back to the advisory nudge
        self.assertIn("additionalContext", out)


if __name__ == "__main__":
    unittest.main()
