"""AT-W5, AT-W6, AT-W10, AT-W11: patches, cap and consolidation, math, render and validate."""

import copy
import json
import unittest

from persona_world_fixtures import Sandbox, opts, read_jsonl, split_state, stream_ids, stub
import world  # noqa: E402

SEEN = {"a1", "a2", "a3"}


def node(nid, typ="belief", text=None, conf=0.5, ev=("a1",), **kw):
    return dict({"id": nid, "type": typ, "text": text or f"text of {nid}", "confidence": conf,
                 "evidence": list(ev), "created": 0, "updated": 0}, **kw)


def base_map():
    mp = world.empty_map("pat")
    mp["nodes"] = [node("b1"), node("b2", conf=0.9),
                   node("f1", "format_rule", band="short", channel="chat")]
    mp["edges"] = [{"from": "b1", "to": "b2", "type": "supports"}]
    return mp


def apply(mp, patches, item="a3", max_nodes=120):
    return world.apply_patches(mp, patches, item, SEEN, 5, max_nodes)


class Patches(unittest.TestCase):
    def test_each_op_applies_and_tags_the_current_item(self):
        mp = base_map()
        applied, rejected = apply(mp, [
            {"op": "add", "node": {"id": "e1", "type": "entity", "text": "a side project", "confidence": 0.6}},
            {"op": "strengthen", "id": "b1"},
            {"op": "weaken", "id": "b2", "by": 0.3},
            {"op": "revise", "id": "f1", "text": "one line, no period"},
            {"op": "add_edge", "edge": {"from": "f1", "to": "e1", "type": "applies-to"}},
        ])
        self.assertEqual(rejected, [])
        self.assertEqual(len(applied), 5)
        by = {n["id"]: n for n in mp["nodes"]}
        self.assertAlmostEqual(by["b1"]["confidence"], 0.6)
        self.assertAlmostEqual(by["b2"]["confidence"], 0.6)
        self.assertEqual(by["f1"]["text"], "one line, no period")
        for nid in ("e1", "b1", "b2", "f1"):
            self.assertIn("a3", by[nid]["evidence"])
            self.assertEqual(by[nid]["updated"], 5)
        self.assertIn({"from": "f1", "to": "e1", "type": "applies-to"}, mp["edges"])
        self.assertEqual(world.validate_map(mp, SEEN), [])

    def test_remove_merge_and_remove_edge(self):
        mp = base_map()
        mp["nodes"].append(node("b3", ev=("a2",)))
        mp["edges"].append({"from": "b3", "to": "f1", "type": "applies-to"})
        applied, rejected = apply(mp, [
            {"op": "merge", "ids": ["b1", "b3"], "into": {"id": "b13", "type": "belief", "text": "merged"}},
            {"op": "remove_edge", "edge": {"from": "b13", "to": "b2", "type": "supports"}},
            {"op": "remove", "id": "f1"},
        ])
        self.assertEqual(rejected, [])
        by = {n["id"]: n for n in mp["nodes"]}
        self.assertEqual(sorted(by), ["b13", "b2"])
        self.assertEqual(sorted(by["b13"]["evidence"]), ["a1", "a2", "a3"])
        self.assertEqual(mp["edges"], [])  # rewired supports edge removed, f1's edge went with f1

    def test_bad_patches_are_rejected_and_the_rest_apply(self):
        bad = [
            {"op": "explode", "id": "b1"},
            {"op": "add", "node": {"id": "b1", "type": "belief", "text": "duplicate id"}},
            {"op": "add", "node": {"id": "Bad Id", "type": "belief", "text": "x"}},
            {"op": "add", "node": {"id": "z1", "type": "mood", "text": "x"}},
            {"op": "add", "node": {"id": "z2", "type": "belief", "text": ""}},
            {"op": "add", "node": {"id": "z3", "type": "belief", "text": "x" * 281}},
            {"op": "add", "node": {"id": "z4", "type": "belief", "text": "x", "confidence": 1.5}},
            {"op": "add", "node": {"id": "z5", "type": "format_rule", "text": "x"}},  # no band, channel
            {"op": "add", "node": {"id": "z6", "type": "belief", "text": "x", "evidence": ["sealed1"]}},
            {"op": "strengthen", "id": "nope"},
            {"op": "add_edge", "edge": {"from": "b1", "to": "nope", "type": "supports"}},
            {"op": "add_edge", "edge": {"from": "b1", "to": "b1", "type": "supports"}},
            {"op": "add_edge", "edge": {"from": "b1", "to": "b2", "type": "supports"}},  # duplicate
            {"op": "add_edge", "edge": {"from": "b1", "to": "b2", "type": "causes"}},
            {"op": "merge", "ids": ["b1"], "into": {"id": "m", "type": "belief", "text": "x"}},
            "not a patch",
        ]
        good = {"op": "add", "node": {"id": "ok1", "type": "lexicon", "text": "says 'kk' for yes"}}
        mp = base_map()
        applied, rejected = apply(mp, bad[:8] + [good] + bad[8:])
        self.assertEqual(len(rejected), len(bad))
        self.assertTrue(all(r["reason"] for r in rejected))
        self.assertEqual(applied, [good])
        self.assertEqual(world.validate_map(mp, SEEN), [])

    def test_malformed_ids_are_rejected_not_raised(self):
        good = {"op": "add", "node": {"id": "ok2", "type": "belief", "text": "fine"}}
        bad = [{"op": "strengthen", "id": ["b1"]},
               {"op": "add_edge", "edge": {"from": ["b1"], "to": "b2", "type": "supports"}},
               {"op": "merge", "ids": [["b1"], "b2"], "into": {"id": "m1", "type": "belief", "text": "x"}},
               {"op": "merge", "ids": ["b1", "b2"], "into": {"id": ["m1"], "type": "belief", "text": "x"}},
               {"op": "add", "node": {"id": {"x": 1}, "type": "belief", "text": "x"}}]
        mp = base_map()
        applied, rejected = apply(mp, bad + [good])
        self.assertEqual(applied, [good])
        self.assertEqual(len(rejected), len(bad))
        broken = base_map()
        broken["nodes"][0]["id"] = ["b1"]
        broken["edges"].append({"from": ["b1"], "to": "b2", "type": "supports"})
        self.assertTrue(world.validate_map(broken, SEEN))

    def test_reply_patch_limit_and_consolidation_rules(self):
        many = [{"op": "strengthen", "id": "b1", "by": 0.01} for _ in range(30)]
        mp = base_map()
        applied, rejected = apply(mp, many)
        self.assertEqual((len(applied), len(rejected)), (24, 6))
        mp = base_map()
        applied, rejected = world.apply_patches(mp, [
            {"op": "add", "node": {"id": "c1", "type": "belief", "text": "x"}},
            {"op": "strengthen", "id": "b1", "evidence": ["a2"]},
            {"op": "merge", "ids": ["b1", "b2"], "into": {"id": "m", "type": "belief", "text": "x", "evidence": ["a2"]}},
            {"op": "remove", "id": "f1"},
        ], None, SEEN, 5, 120, world.CONSOLIDATE_OPS)
        self.assertEqual(applied, [{"op": "remove", "id": "f1"}])
        self.assertEqual(len(rejected), 3)

    def test_evidence_must_be_seen(self):
        mp = base_map()
        _, rejected = apply(mp, [{"op": "strengthen", "id": "b1", "evidence": ["future9"]}])
        self.assertEqual(len(rejected), 1)
        self.assertIn("evidence", rejected[0]["reason"])


class Cap(unittest.TestCase):
    def test_adds_past_the_cap_are_rejected(self):
        mp = base_map()
        patches = [{"op": "add", "node": {"id": f"n{i}", "type": "belief", "text": f"b {i}"}} for i in range(5)]
        applied, rejected = apply(mp, patches, max_nodes=5)
        self.assertEqual(len(mp["nodes"]), 5)
        self.assertEqual(len(applied), 2)
        self.assertTrue(all("cap" in r["reason"] for r in rejected))

    def test_prune_is_deterministic_and_ordered(self):
        mp = base_map()
        mp["nodes"] += [node("w1", conf=0.1), node("w2", conf=0.1, ev=("a1", "a2")), node("s1", conf=0.95)]
        mp["edges"].append({"from": "w1", "to": "b2", "type": "supports"})
        a, b = copy.deepcopy(mp), copy.deepcopy(mp)
        b["nodes"].reverse()
        world.prune(a, 4)
        world.prune(b, 4)
        self.assertEqual(a, b)
        ids = {n["id"] for n in a["nodes"]}
        self.assertEqual(len(ids), 4)
        self.assertNotIn("w1", ids)  # lowest confidence, fewest evidence goes first
        self.assertNotIn("w2", ids)
        self.assertTrue(all(e["from"] in ids and e["to"] in ids for e in a["edges"]))


class Consolidation(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def _run(self, script, **kw):
        d = split_state(self.sb)
        world.init(d)
        world.run(d, stub(dict({"score_default": 1}, **script)), opts(**kw))
        return d, json.loads((d / "map.json").read_text()), read_jsonl(d / "log.jsonl")

    def test_consolidation_reduces_size_and_the_cap_holds(self):
        d, mp, log = self._run({}, max_nodes=8, consolidate_every=5)
        self.assertLessEqual(len(mp["nodes"]), 8)
        cons = [r["consolidate"] for r in log if r.get("consolidate")]
        self.assertTrue(cons)
        self.assertTrue(any(c["after"] < c["before"] for c in cons))
        self.assertEqual(world.validate_map(mp, set(stream_ids(d)), max_nodes=8), [])

    def test_cap_reached_triggers_consolidation_before_the_schedule(self):
        d, mp, log = self._run({}, max_nodes=4, consolidate_every=1000)
        self.assertTrue(any(r.get("consolidate") for r in log))
        self.assertLessEqual(len(mp["nodes"]), 4)

    def test_garbage_consolidator_still_respects_the_cap(self):
        d, mp, log = self._run({"consolidate": "garbage"}, max_nodes=5, consolidate_every=3)
        self.assertLessEqual(len(mp["nodes"]), 5)
        self.assertTrue(any(r["consolidate"].get("pruned") for r in log if r.get("consolidate")))


class Math(unittest.TestCase):
    def test_surprise(self):
        self.assertEqual(world.surprise(0, 5.0), 0.0)
        self.assertEqual(world.surprise(1, 0.0), 1.0)
        self.assertAlmostEqual(world.surprise(1, 4.0), 0.6)
        self.assertAlmostEqual(world.surprise(0, 2.5), 0.25)

    def test_curve_rolling_window_first_and_last(self):
        rows = []
        for i in range(10):
            hit = 1 if i < 5 else 0
            rubric = 2.0 if i < 5 else 4.0
            rows.append({"step": i, "excluded": None, "hit": hit, "rubric": rubric,
                         "surprise": world.surprise(hit, rubric)})
        rows.insert(3, {"step": 99, "excluded": "error", "hit": None, "rubric": None, "surprise": None})
        c = world.curve(rows, 4)
        pts = c["points"]
        self.assertEqual(len(pts), 10)  # the excluded row is not on the curve
        self.assertEqual(pts[0]["n"], 1)
        self.assertAlmostEqual(pts[5]["id_rate"], (1 + 1 + 1 + 0) / 4)  # scored steps 2..5
        self.assertAlmostEqual(pts[5]["rubric"], (2 + 2 + 2 + 4) / 4)
        self.assertEqual(c["first"]["id_rate"], 1.0)
        self.assertEqual(c["last"]["id_rate"], 0.0)
        self.assertEqual(c["last"]["rubric"], 4.0)
        self.assertEqual(c["window"], 4)

    def test_curve_shorter_than_a_window(self):
        rows = [{"step": 0, "excluded": None, "hit": 1, "rubric": 3.0, "surprise": 0.7}]
        c = world.curve(rows, 20)
        self.assertEqual(c["first"]["n"], 1)
        self.assertEqual(c["last"]["n"], 1)
        self.assertEqual(world.curve([], 20)["points"], [])


class RenderAndValidate(unittest.TestCase):
    def test_render_is_deterministic_and_order_free(self):
        mp = base_map()
        mp["nodes"] += [node("l1", "lexicon"), node("nd1", "never_do", conf=0.8),
                        node("f2", "format_rule", band="long", channel="email")]
        other = copy.deepcopy(mp)
        other["nodes"].reverse()
        a, b = world.render(mp), world.render(other)
        self.assertEqual(a, b)
        self.assertEqual(a, world.render(copy.deepcopy(mp)))
        order = [a.index(h) for h in ("## Entities", "## Beliefs", "## Decision rules", "## Reaction patterns",
                                      "## Format rules", "## Lexicon", "## Never do", "## Edges")]
        self.assertEqual(order, sorted(order))
        self.assertLess(a.index("[b2]"), a.index("[b1]"))  # higher confidence first

    def test_validate_flags_each_schema_error(self):
        cases = {
            "duplicate node id": lambda mp: mp["nodes"].append(node("b1")),
            "type": lambda mp: mp["nodes"][0].update(type="mood"),
            "confidence": lambda mp: mp["nodes"][0].update(confidence=-0.1),
            "evidence": lambda mp: mp["nodes"][0].update(evidence=[]),
            "unseen": lambda mp: mp["nodes"][0].update(evidence=["zz"]),
            "band": lambda mp: mp["nodes"][2].pop("band"),
            "edge": lambda mp: mp["edges"].append({"from": "b1", "to": "gone", "type": "supports"}),
            "nodes": lambda mp: mp["nodes"].extend(node(f"x{i}") for i in range(200)),
        }
        self.assertEqual(world.validate_map(base_map(), SEEN), [])
        for word, mutate in cases.items():
            with self.subTest(word):
                mp = base_map()
                mutate(mp)
                errs = world.validate_map(mp, SEEN)
                self.assertTrue(any(word in e for e in errs), errs)

    def test_validate_flags_an_oversized_render(self):
        mp = base_map()
        mp["nodes"] += [node(f"x{i}", text="y" * 270) for i in range(100)]
        errs = world.validate_map(mp, SEEN, max_map_bytes=4096)
        self.assertTrue(any("bytes" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
