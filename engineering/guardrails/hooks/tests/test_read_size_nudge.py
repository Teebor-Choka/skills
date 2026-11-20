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

    def assistant_call(self, name):
        return json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t9", "name": name, "input": {}}]}})

    def test_graph_call_at_the_start_of_a_huge_transcript_is_still_seen(self):
        with open(self.transcript, "w") as f:
            f.write(self.assistant_call("mcp__codebase-memory-mcp__search_graph") + "\n")
            filler = json.dumps({"type": "user", "message": {"content": "x" * 100_000}}) + "\n"
            for _ in range(50):  # 5 MB after the graph call, past the old 4 MB tail window
                f.write(filler)
        self.assertEqual(self.deny(), "")

    def test_assistant_tool_use_line_counts(self):
        with open(self.transcript, "w") as f:
            f.write(self.assistant_call("mcp__codebase-memory-mcp__trace_path") + "\n")
        self.assertEqual(self.deny(), "")

    def test_quoted_tool_name_in_a_tool_result_or_user_text_does_not_count(self):
        quoted = [
            json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t",
                        "content": 'grep found: "name": "mcp__codebase-memory-mcp__search_graph"'}]}}),
            json.dumps({"type": "user", "message": {"content": 'use "name": "mcp__codebase-memory-mcp__x"'}}),
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": '"name": "mcp__codebase-memory-mcp__search_graph"'}]}}),
            'not json "name": "mcp__codebase-memory-mcp__search_graph"',
        ]
        for line in quoted:
            with self.subTest(line=line[:60]):
                self.write_transcript(OTHER_CALL, line)
                self.assertIn("ToolSearch", self.deny())

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


class NonSourceFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def nudge(self, name, **extra):
        return rsn.nudge({"file_path": "/x/" + name, **extra}, "s-" + name, self.tmp, size_of=lambda p: BIG,
                         which=lambda n: "/bin/" + n)

    def test_binary_and_document_formats_are_not_nudged(self):
        for name in ("a.pdf", "a.png", "a.JPG", "a.jpeg", "a.gif", "a.webp", "a.ipynb", "a.svg", "a.mp4", "a.mov",
                     "a.zip", "a.ico", "a.mp3", "a.wav"):
            with self.subTest(name=name):
                self.assertEqual(self.nudge(name), "")

    def test_a_pages_request_is_not_nudged(self):
        self.assertEqual(self.nudge("big.md", pages="1-5"), "")
        self.assertEqual(self.nudge("big.pdf", pages="1-5"), "")

    def test_text_files_still_are(self):
        self.assertIn("60 KB", self.nudge("big.md"))


class StateFiles(unittest.TestCase):
    def test_marker_uses_agent_prefix(self):
        tmp = tempfile.mkdtemp()
        rsn.nudge({"file_path": "/x/spec.md"}, "pfx", tmp, size_of=lambda p: 60 * 1024)
        self.assertEqual(len(os.listdir(tmp)), 1)
        self.assertTrue(os.listdir(tmp)[0].startswith("agent-read-size-nudge.pfx."))

    def test_empty_tmpdir_falls_back_to_tmp(self):
        # an empty TMPDIR must not turn the marker path into a relative one
        for value in ("", None):
            with self.subTest(tmpdir=value):
                saved = os.environ.pop("TMPDIR", None)
                try:
                    if value is not None:
                        os.environ["TMPDIR"] = value
                    self.assertEqual(rsn.tmp_root(), "/tmp")
                finally:
                    os.environ.pop("TMPDIR", None)
                    if saved is not None:
                        os.environ["TMPDIR"] = saved

    def test_tmpdir_is_used_when_set(self):
        saved = os.environ.get("TMPDIR")
        os.environ["TMPDIR"] = "/somewhere"
        try:
            self.assertEqual(rsn.tmp_root(), "/somewhere")
        finally:
            if saved is None:
                os.environ.pop("TMPDIR", None)
            else:
                os.environ["TMPDIR"] = saved


class GraphClaims(unittest.TestCase):
    """The text only talks about the code graph when the graph binary is on PATH."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def nudge(self, found):
        return rsn.nudge({"file_path": "/x/spec.md"}, "s", self.tmp, size_of=lambda p: BIG,
                         which=(lambda n: "/bin/" + n) if found else (lambda n: None))

    def test_nudge_names_the_graph_only_when_the_binary_exists(self):
        self.assertIn("search_graph", self.nudge(found=True))
        self.tmp = tempfile.mkdtemp()
        self.assertNotIn("search_graph", self.nudge(found=False))
        self.assertNotIn("indexed", self.nudge(found=False) or "")

    def test_deny_claims_indexed_only_when_the_binary_exists(self):
        with open(os.path.join(self.tmp, "t.jsonl"), "w") as f:
            f.write("{}\n")
        t = os.path.join(self.tmp, "t.jsonl")
        big = os.path.join(self.tmp, "x.rs")
        with open(big, "w") as f:
            f.write("x" * BIG)
        text = rsn.deny_reason({"file_path": big}, t, which=lambda n: "/bin/" + n, in_git=lambda p: True)
        self.assertIn("indexed", text)
        self.assertEqual(rsn.deny_reason({"file_path": big}, t, which=lambda n: None, in_git=lambda p: True), "")


class StatePathSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.big = os.path.join(self.tmp, "spec.md")
        with open(self.big, "w") as f:
            f.write("x" * BIG)

    def run_hook(self, payload):
        return subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True,
                              timeout=20, env={**os.environ, "TMPDIR": self.tmp})

    def markers(self):
        return sorted(n for n in os.listdir(self.tmp) if n.startswith("agent-read-size-nudge."))

    def test_no_session_id_gets_a_per_user_per_cwd_marker(self):
        for cwd in ("/a", "/b"):
            self.run_hook({"tool_name": "Read", "cwd": cwd, "tool_input": {"file_path": self.big}})
        names = self.markers()
        self.assertEqual(len(names), 2)
        for name in names:
            self.assertTrue(name.startswith("agent-read-size-nudge.nosession-%d-" % os.getuid()), name)

    def test_session_id_is_sanitised_like_the_other_hooks(self):
        self.run_hook({"tool_name": "Read", "session_id": "../../evil x", "tool_input": {"file_path": self.big}})
        names = self.markers()
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith("agent-read-size-nudge._.._evil_x."), names)

    def test_planted_symlink_is_not_followed(self):
        import hashlib
        victim = os.path.join(self.tmp, "victim")
        with open(victim, "w") as f:
            f.write("keep")
        digest = hashlib.sha1(self.big.encode()).hexdigest()[:12]
        os.symlink(victim, os.path.join(self.tmp, "agent-read-size-nudge.sl." + digest))
        r = self.run_hook({"tool_name": "Read", "session_id": "sl", "tool_input": {"file_path": self.big}})
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(victim) as f:
            self.assertEqual(f.read(), "keep")


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
