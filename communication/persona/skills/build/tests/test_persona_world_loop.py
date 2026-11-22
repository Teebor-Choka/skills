"""AT-W1 to AT-W4, AT-W7, AT-W12, AT-W13: stream, order and resume, leaks, threshold, guard, end to end."""

import json
import subprocess
import unittest

from persona_world_fixtures import (CANARY_LATER, CANARY_NOW, CANARY_SEALED, Recorder, Sandbox, opts, plant,
                                    read_jsonl, split_state, stream_ids, stub, synth_records)
import world  # noqa: E402


HOT = {"score_default": 1}  # high surprise: every step updates


class Crash(BaseException):
    """A kill mid-step: not an Exception, so nothing in the loop may swallow it."""


class CrashAt:
    def __init__(self, inner, step, role):
        self.inner, self.step, self.role = inner, step, role

    def complete(self, role, model, system, prompt, meta):
        if meta.get("step") == self.step and role == self.role:
            raise Crash()
        return self.inner.complete(role, model, system, prompt, meta)


class Base(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()


class Stream(Base):
    def test_chronological_when_every_ts_parses(self):
        recs = synth_records(40)
        for i, r in enumerate(recs):
            # mixed formats, reverse of the file order
            r["ts"] = (f"2026-03-{31 - i:02d}T10:00:00" if i % 2 else
                       f"Mon, {31 - i:02d} Mar 2026 10:00:00 +0000") if i < 30 else f"2026-02-{40 - i:02d}"
        d = split_state(self.sb, records=recs)
        s = world.init(d)
        self.assertEqual(s["order"], "chronological")
        train = {r["id"]: r for r in read_jsonl(d / "split" / "train.jsonl")}
        stamps = [world.parse_ts(train[i]["ts"]) for i in s["ids"]]
        self.assertEqual(stamps, sorted(stamps))

    def test_seeded_when_a_ts_is_missing_and_recorded(self):
        recs = synth_records(40)
        for r in recs:
            r["ts"] = "sometime last week"
        d = split_state(self.sb, records=recs)
        s1 = world.init(d)
        self.assertEqual(s1["order"], "seeded")
        self.assertIn("ts", s1["reason"])
        s2 = world.init(d, force=True)
        self.assertEqual(s1["ids"], s2["ids"])
        s3 = world.init(d, seed=99, force=True)
        self.assertNotEqual(s1["ids"], s3["ids"])
        self.assertEqual(sorted(s1["ids"]), sorted(s3["ids"]))

    def test_stream_is_train_only_and_init_twice_needs_force(self):
        d = split_state(self.sb)
        s = world.init(d)
        test_ids = {r["id"] for r in read_jsonl(d / "split" / "test.jsonl")}
        self.assertEqual(set(s["sealed"]), test_ids)
        self.assertFalse(test_ids & set(s["ids"]))
        self.assertEqual(sorted(s["ids"]), sorted(r["id"] for r in read_jsonl(d / "split" / "train.jsonl")))
        with self.assertRaises(world.m.Fail):
            world.init(d)

    def test_resplit_after_init_is_refused(self):
        d = split_state(self.sb)
        world.init(d)
        r = self.sb.run("split.py", "--persona", "pat", "--seed", "7")
        self.assertEqual(r.returncode, 0, r.stderr)
        with self.assertRaises(world.m.Fail) as e:
            world.run(d, stub(), opts())
        self.assertIn("split", str(e.exception))


class OrderAndResume(Base):
    def test_steps_follow_the_stream_and_max_steps_resume(self):
        d = split_state(self.sb)
        world.init(d)
        rec = Recorder(stub())
        self.assertEqual(world.run(d, rec, opts(), max_steps=5), 5)
        with self.assertRaises(world.m.Fail):
            world.run(d, rec, opts(), max_steps=1)  # needs --resume
        world.run(d, rec, opts(), resume=True)
        ids = stream_ids(d)
        seen = [c["meta"]["item_id"] for c in rec.calls if c["role"] == "extract" and c["meta"].get("attempt") == 1]
        self.assertEqual(seen, ids)
        self.assertEqual([r["step"] for r in read_jsonl(d / "log.jsonl")], list(range(len(ids))))
        st = json.loads((d / "state.json").read_text())
        self.assertEqual(st["next"], len(ids))

    def _uninterrupted(self):
        sb = Sandbox()
        try:
            d = split_state(sb)
            world.init(d)
            world.run(d, stub(HOT), opts(consolidate_every=4))
            return (d / "map.json").read_bytes(), (d / "log.jsonl").read_bytes()
        finally:
            sb.close()

    def test_crash_mid_step_repeats_only_that_step(self):
        want = self._uninterrupted()
        for role in ("extract", "predict", "identify", "score", "update", "consolidate"):
            with self.subTest(role=role):
                sb = Sandbox()
                try:
                    d = split_state(sb)
                    world.init(d)
                    step = 7 if role == "consolidate" else 5  # consolidation runs after steps 3, 7, ...
                    with self.assertRaises(Crash):
                        world.run(d, CrashAt(stub(HOT), step, role), opts(consolidate_every=4))
                    self.assertEqual(json.loads((d / "state.json").read_text())["next"], step)
                    world.run(d, stub(HOT), opts(consolidate_every=4), resume=True)
                    self.assertEqual(((d / "map.json").read_bytes(), (d / "log.jsonl").read_bytes()), want)
                finally:
                    sb.close()

    def test_crash_after_the_state_commit_finishes_the_rename(self):
        d = split_state(self.sb)
        world.init(d)
        world.run(d, stub(), opts(), max_steps=3)
        st = json.loads((d / "state.json").read_text())
        # simulate: map.next.json written and state committed, rename not done
        (d / "map.next.json").write_bytes((d / "map.json").read_bytes())
        (d / "map.json").write_text('{"version": 1, "persona": "pat", "step": 2, "nodes": [], "edges": []}\n')
        world.run(d, stub(), opts(), resume=True, max_steps=0)
        self.assertFalse((d / "map.next.json").exists())
        self.assertEqual(world.file_hash(d / "map.json"), st["map_hash"])

    def test_hand_edited_map_is_refused(self):
        d = split_state(self.sb)
        world.init(d)
        world.run(d, stub(), opts(), max_steps=2)
        mp = json.loads((d / "map.json").read_text())
        mp["nodes"][0]["text"] = "edited by hand"
        (d / "map.json").write_text(json.dumps(mp))
        with self.assertRaises(world.m.Fail) as e:
            world.run(d, stub(), opts(), resume=True)
        self.assertIn("map.json", str(e.exception))


class Leaks(Base):
    def test_predict_never_sees_the_current_or_a_later_item(self):
        d = split_state(self.sb)
        world.init(d)
        ids = stream_ids(d)
        train = {r["id"]: i for i, r in enumerate(read_jsonl(d / "split" / "train.jsonl"))}
        now, later = ids[6], ids[12]
        plant(d, "train.jsonl", train[now], CANARY_NOW)
        plant(d, "train.jsonl", train[later], CANARY_LATER)
        world.init(d, force=True)  # ids are content hashes of ingest; the split file text changed only
        rec = Recorder(stub({"score_default": 1}))  # every step updates
        world.run(d, rec, opts())
        for c in rec.calls:
            if c["role"] == "predict":
                blob = c["prompt"] + c["system"] + json.dumps(c["meta"])
                if c["step"] <= 6:
                    self.assertNotIn(CANARY_NOW, blob, c["step"])
                if c["step"] <= 12:
                    self.assertNotIn(CANARY_LATER, blob, c["step"])
        # the update of step 6 does see it: the loop learns after predicting
        self.assertTrue(any(CANARY_NOW in c["prompt"] for c in rec.calls if c["role"] == "update" and c["step"] == 6))

    def test_judge_exemplars_are_earlier_items_only(self):
        d = split_state(self.sb)
        world.init(d)
        ids = stream_ids(d)
        world.run(d, stub(), opts())
        for row in read_jsonl(d / "log.jsonl"):
            before = set(ids[:row["step"]])
            self.assertTrue(set(row.get("exemplars") or []) <= before, row["step"])

    def test_sealed_canary_reaches_no_prompt_and_no_file(self):
        d = split_state(self.sb)
        plant(d, "test.jsonl", 0, CANARY_SEALED)
        world.init(d)
        rec = Recorder(stub())
        world.run(d, rec, opts(consolidate_every=5))
        for c in rec.calls:
            self.assertNotIn(CANARY_SEALED, c["prompt"] + c["system"] + json.dumps(c["meta"]))
        for f in ("map.json", "map.md", "log.jsonl", "curve.json", "state.json", "stream.json"):
            self.assertNotIn(CANARY_SEALED, (d / f).read_text(encoding="utf-8"), f)


class Threshold(Base):
    def test_low_surprise_skips_the_update_but_not_on_a_new_entity_or_belief(self):
        d = split_state(self.sb)
        world.init(d)
        ids = stream_ids(d)
        script = {"identify_default": "wrong", "score_default": 5,
                  "entities": {ids[2]: ["Orbitron project"]}, "missed": {ids[3]: ["belief"]}}
        world.run(d, stub(script), opts(threshold=0.3), max_steps=5)
        log = read_jsonl(d / "log.jsonl")
        self.assertEqual([r["surprise"] for r in log], [0.0] * 5)
        self.assertEqual(log[0]["update"], "update")  # empty map: everything is new
        self.assertEqual(log[1]["update"], "skip")
        self.assertEqual(log[1]["skip"], "low_surprise")
        self.assertEqual(log[2]["update"], "update")  # new entity
        self.assertEqual(log[3]["update"], "update")  # missed belief
        self.assertEqual(log[4]["update"], "skip")

    def test_high_surprise_updates(self):
        d = split_state(self.sb)
        world.init(d)
        world.run(d, stub({"identify_default": "correct", "score_default": 1}), opts(), max_steps=3)
        log = read_jsonl(d / "log.jsonl")
        self.assertTrue(all(r["update"] == "update" for r in log))
        self.assertAlmostEqual(log[1]["surprise"], 0.5 * 1 + 0.5 * (1 - 1 / 5))

    def test_excluded_step_is_unscored_but_updates(self):
        d = split_state(self.sb)
        world.init(d)
        ids = stream_ids(d)
        rec = Recorder(stub({"extract": {ids[1]: "quote"}}))
        world.run(d, rec, opts(), max_steps=3)
        row = read_jsonl(d / "log.jsonl")[1]
        self.assertEqual(row["excluded"], "point_leak")
        self.assertIsNone(row["surprise"])
        self.assertEqual(row["update"], "update")
        self.assertFalse(any(c["role"] in ("predict", "identify", "score") and c["step"] == 1 for c in rec.calls))


class Guard(Base):
    def test_state_dir_inside_a_git_work_tree_exits_3_and_writes_nothing(self):
        repo = self.sb.root / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        target = repo / "state"
        r = self.sb.run("world.py", "init", "--state-dir", target)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(target.exists())
        r = self.sb.run("world.py", "run", "--state-dir", target, "--runner", "stub")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertFalse(target.exists())


class EndToEnd(Base):
    def test_forty_items_through_init_run_final(self):
        split_state(self.sb, n=40)
        steps = [("init",), ("run", "--runner", "stub", "--max-steps", "10"),
                 ("run", "--runner", "stub", "--resume"), ("status",), ("validate",), ("render",),
                 ("final", "--runner", "stub")]
        out = {}
        for s in steps:
            r = self.sb.run("world.py", s[0], "--persona", "pat", *s[1:])
            self.assertEqual(r.returncode, 0, f"{s}: {r.stdout}\n{r.stderr}")
            out[s[0]] = r.stdout
        self.assertIn("valid", out["validate"])
        self.assertIn("verdict: INCONCLUSIVE", out["final"])
        self.assertIn("curve", out["final"])
        self.assertIn("cost", out["final"])
        d = self.sb.state("pat")
        rep = json.loads((d / "final" / "report.json").read_text())
        self.assertEqual(rep["n_total"], 16)
        self.assertIn("by_band", rep)
        r = self.sb.run("world.py", "final", "--persona", "pat", "--runner", "stub")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--rerun-test", r.stderr)
        r = self.sb.run("evaluate.py", "run", "--persona", "pat", "--slice", "test", "--runner", "stub")
        self.assertEqual(r.returncode, 2)  # the slice is used, whichever tool used it
        r = self.sb.run("world.py", "final", "--persona", "pat", "--runner", "stub", "--rerun-test", "stub check")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_final_before_the_loop_ends_is_refused(self):
        split_state(self.sb, n=40)
        self.sb.run("world.py", "init", "--persona", "pat")
        self.sb.run("world.py", "run", "--persona", "pat", "--runner", "stub", "--max-steps", "3")
        r = self.sb.run("world.py", "final", "--persona", "pat", "--runner", "stub")
        self.assertEqual(r.returncode, 2)
        self.assertFalse((self.sb.state("pat") / "split" / "test.sealed").exists())


if __name__ == "__main__":
    unittest.main()
