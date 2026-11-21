"""Tests for hooks/context-reset-nudge.py (UserPromptSubmit). Run: python3 -m pytest hooks/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "context-reset-nudge.py")


def assistant(tokens, cache_read=None):
    """One assistant transcript line whose context size is `tokens` (input + cache create + cache read)."""
    cache_read = tokens - 1000 if cache_read is None else cache_read
    usage = {"input_tokens": 100, "cache_creation_input_tokens": tokens - 100 - cache_read,
             "cache_read_input_tokens": cache_read, "output_tokens": 50}
    return {"type": "assistant", "message": {"role": "assistant", "usage": usage}}


COMPACT = {"type": "system", "subtype": "compact_boundary", "content": "Conversation compacted"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.transcript = os.path.join(self.tmp.name, "t.jsonl")

    def write(self, lines):
        with open(self.transcript, "w") as f:
            for line in lines:
                f.write((line if isinstance(line, str) else json.dumps(line)) + "\n")

    def run_hook(self, session="s1", raw=None, tmpdir=None, payload=None):
        payload = payload if payload is not None else {
            "session_id": session, "transcript_path": self.transcript,
            "hook_event_name": "UserPromptSubmit", "prompt": "go"}
        return subprocess.run(
            [sys.executable, HOOK], input=raw if raw is not None else json.dumps(payload),
            capture_output=True, text=True, timeout=20,
            env={**os.environ, "TMPDIR": self.tmp.name if tmpdir is None else tmpdir})

    def context(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout:
            return None
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        return out["additionalContext"]


class Thresholds(Base):
    def test_below_700k_is_silent(self):
        self.write([assistant(699_000)])
        self.assertIsNone(self.context(self.run_hook()))

    def test_crossing_700k_nudges_a_handoff(self):
        self.write([assistant(701_000)])
        ctx = self.context(self.run_hook())
        self.assertIn("handoff", ctx)
        self.assertIn("15 lines", ctx)
        self.assertIn("keep working", ctx)

    def test_each_nudge_fires_once(self):
        self.write([assistant(701_000)])
        self.assertIsNotNone(self.context(self.run_hook()))
        self.assertIsNone(self.context(self.run_hook()))
        self.write([assistant(701_000), assistant(750_000)])
        self.assertIsNone(self.context(self.run_hook()))

    def test_800k_repeats_once(self):
        self.write([assistant(701_000)])
        self.run_hook()
        self.write([assistant(701_000), assistant(801_000)])
        ctx = self.context(self.run_hook())
        self.assertIn("800K", ctx)
        self.assertIsNone(self.context(self.run_hook()))

    def test_jump_past_both_thresholds_fires_one_message_then_silence(self):
        self.write([assistant(820_000)])
        self.assertIn("800K", self.context(self.run_hook()))
        self.assertIsNone(self.context(self.run_hook()))

    def test_uses_latest_usage_block_not_the_peak(self):
        self.write([assistant(900_000), COMPACT, assistant(30_000)])
        # one compaction and a small context now: nothing to say about size
        self.assertIsNone(self.context(self.run_hook()))

    def test_context_sums_input_and_cache_tokens(self):
        usage = {"input_tokens": 10, "cache_creation_input_tokens": 100_000, "cache_read_input_tokens": 600_000}
        self.write([{"type": "assistant", "message": {"usage": usage}}])
        self.assertIsNotNone(self.context(self.run_hook()))

    def test_sessions_are_independent(self):
        self.write([assistant(701_000)])
        self.assertIsNotNone(self.context(self.run_hook("a")))
        self.assertIsNotNone(self.context(self.run_hook("b")))


class CompactionScan(Base):
    def state(self, session="s1"):
        with open(os.path.join(self.tmp.name, "agent-context-reset-nudge." + session)) as f:
            return json.load(f)

    def test_e6_a_quoted_boundary_in_message_content_is_not_counted(self):
        quote = {"type": "assistant", "message": {"content": [{"type": "text",
                 "text": 'the entry {"type":"system","subtype":"compact_boundary"} looks like this'}],
                 "usage": {"input_tokens": 10}}}
        raw_quote = {"type": "user", "message": {"content": '{"subtype": "compact_boundary"}'}}
        self.write([quote, raw_quote, quote, raw_quote, assistant(30_000)])
        self.assertIsNone(self.context(self.run_hook()))

    def test_e6_only_a_system_entry_with_the_subtype_counts(self):
        wrong_type = {"type": "assistant", "subtype": "compact_boundary"}
        self.write([wrong_type, wrong_type, assistant(30_000)])
        self.assertIsNone(self.context(self.run_hook()))

    def test_e6_a_second_compaction_appended_later_is_found_incrementally(self):
        self.write([assistant(100_000), COMPACT, assistant(30_000)])
        self.assertIsNone(self.context(self.run_hook()))
        with open(self.transcript, "a") as f:
            f.write(json.dumps(COMPACT) + "\n" + json.dumps(assistant(20_000)) + "\n")
        self.assertIn("compact", self.context(self.run_hook()))

    def test_e6_the_scan_resumes_from_the_saved_offset_and_never_rereads_old_bytes(self):
        self.write([assistant(100_000), COMPACT, assistant(30_000)])
        self.run_hook()
        saved = self.state()
        self.assertIsInstance(saved, dict)
        self.assertEqual(saved["offset"], os.path.getsize(self.transcript))
        self.assertEqual(saved["compactions"], 1)
        # Corrupt the already-scanned prefix in place (same size): a rescan would lose the count.
        with open(self.transcript, "r+b") as f:
            f.write(b"X" * 40)
        with open(self.transcript, "a") as f:
            f.write(json.dumps(COMPACT) + "\n")
        self.assertIn("compact", self.context(self.run_hook()))

    def test_e6_a_partial_last_line_is_not_counted_until_it_is_complete(self):
        self.write([assistant(100_000), COMPACT])
        with open(self.transcript, "a") as f:
            f.write(json.dumps(COMPACT)[:20])
        self.assertIsNone(self.context(self.run_hook()))
        with open(self.transcript, "a") as f:
            f.write(json.dumps(COMPACT)[20:] + "\n")
        self.assertIn("compact", self.context(self.run_hook()))

    def test_e6_a_shrunk_or_replaced_transcript_resets_the_scan(self):
        self.write([assistant(100_000), COMPACT, assistant(80_000), COMPACT, assistant(30_000)])
        self.run_hook()
        self.write([assistant(1_000)])  # smaller than the saved offset
        self.assertIsNone(self.context(self.run_hook(session="s1")))
        self.assertEqual(self.state()["compactions"], 0)

    def test_e6_the_old_list_state_format_is_still_read(self):
        self.write([assistant(701_000)])
        with open(os.path.join(self.tmp.name, "agent-context-reset-nudge.s1"), "w") as f:
            json.dump(["700k"], f)
        self.assertIsNone(self.context(self.run_hook()))


class Compactions(Base):
    def test_first_compaction_is_silent(self):
        self.write([assistant(100_000), COMPACT, assistant(30_000)])
        self.assertIsNone(self.context(self.run_hook()))

    def test_second_compaction_nudges_once(self):
        self.write([assistant(100_000), COMPACT, assistant(80_000), COMPACT, assistant(30_000)])
        ctx = self.context(self.run_hook())
        self.assertIn("compact", ctx)
        self.assertIn("handoff", ctx)
        self.assertIsNone(self.context(self.run_hook()))

    def test_compaction_text_in_a_message_is_not_counted(self):
        text = {"type": "user", "message": {"content": "grep compact_boundary"}}
        self.write([text, text, assistant(30_000)])
        self.assertIsNone(self.context(self.run_hook()))

    def test_wall_clock_age_is_ignored(self):
        old = dict(assistant(30_000), timestamp="2026-01-01T00:00:00Z")
        self.write([old])
        os.utime(self.transcript, (1, 1))
        self.assertIsNone(self.context(self.run_hook()))


class FailOpen(Base):
    def test_malformed_input_is_silent(self):
        for raw in ("", "not json", "[]", "{}", '{"session_id":"x"}', '{"transcript_path": 5}'):
            with self.subTest(raw=raw):
                r = self.run_hook(raw=raw)
                self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_missing_or_garbage_transcript_is_silent(self):
        r = self.run_hook()  # transcript file absent
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.write(["garbage", "{", '{"type":"assistant","message":{"usage":"x"}}'])
        r = self.run_hook()
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_sidechain_usage_is_ignored(self):
        line = dict(assistant(900_000), isSidechain=True)
        self.write([assistant(10_000), line])
        self.assertIsNone(self.context(self.run_hook()))

    def test_session_id_cannot_escape_the_temp_dir(self):
        self.write([assistant(701_000)])
        self.run_hook(session="../../evil")
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "..", "..", "evil")))
        self.assertEqual(sorted(f for f in os.listdir(self.tmp.name) if f != "t.jsonl").__len__(), 1)

    def test_empty_tmpdir_does_not_write_into_the_project(self):
        self.write([assistant(701_000)])
        self.addCleanup(lambda: os.path.exists("/tmp/agent-context-reset-nudge.e1")
                        and os.remove("/tmp/agent-context-reset-nudge.e1"))
        with tempfile.TemporaryDirectory() as proj:
            payload = {"session_id": "e1", "transcript_path": self.transcript}
            subprocess.run([sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True,
                           cwd=proj, timeout=20, env={**os.environ, "TMPDIR": ""})
            self.assertEqual(os.listdir(proj), [])

    def test_unwritable_state_dir_stays_silent_rather_than_repeat(self):
        # The hook cannot remember what it said, so it says nothing (the code's documented choice).
        self.write([assistant(701_000)])
        r = self.run_hook(tmpdir="/nonexistent-dir-for-test")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_d8_a_planted_symlink_is_not_followed(self):
        self.write([assistant(701_000)])
        victim = os.path.join(self.tmp.name, "victim")
        with open(victim, "w") as f:
            f.write("VICTIM")
        os.symlink(victim, os.path.join(self.tmp.name, "agent-context-reset-nudge.s1"))
        r = self.run_hook()
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(victim) as f:
            self.assertEqual(f.read(), "VICTIM")

    def test_d8_state_file_is_private(self):
        self.write([assistant(701_000)])
        self.run_hook(session="s5")
        mode = os.stat(os.path.join(self.tmp.name, "agent-context-reset-nudge.s5")).st_mode & 0o777
        self.assertEqual(mode, 0o600)


class Namespace(Base):
    def test_state_file_uses_the_agent_prefix(self):
        self.write([assistant(701_000)])
        self.run_hook(session="s9")
        self.assertIn("agent-context-reset-nudge.s9", os.listdir(self.tmp.name))
        self.assertFalse([f for f in os.listdir(self.tmp.name) if f.startswith("claude-")])

    def test_transcript_not_in_claude_shape_fails_open(self):
        # Another harness's JSONL (no usage block, no compact_boundary): no nudge, no error. Only the scan
        # offset is remembered, so the next prompt does not read the file again.
        self.write([{"role": "assistant", "tokens": 900_000}, {"type": "token_count", "total": 900_000}])
        r = self.run_hook()
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(sorted(os.listdir(self.tmp.name)), ["agent-context-reset-nudge.s1", "t.jsonl"])
        with open(os.path.join(self.tmp.name, "agent-context-reset-nudge.s1")) as f:
            self.assertEqual(json.load(f)["done"], [])


if __name__ == "__main__":
    unittest.main()
