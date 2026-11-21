"""AT-3, AT-4, AT-5: no leakage, stratification, sizes and determinism of split.py."""

import json
import unittest
from collections import Counter

from mimic_fixtures import Sandbox, read_jsonl, synth_records, write_jsonl
import mimiclib  # noqa: E402  (path set by mimic_fixtures)


def ingest_split(sb, records, *split_args, persona="pat"):
    src = sb.root / f"{persona}.jsonl"
    write_jsonl(src, records)
    r = sb.run("ingest.py", "--persona", persona, src)
    assert r.returncode == 0, r.stderr
    return sb.run("split.py", "--persona", persona, *split_args)


def slices(sb, persona="pat"):
    d = sb.state(persona) / "split"
    return {k: read_jsonl(d / f"{k}.jsonl") for k in ("train", "dev", "test")}


class NoLeak(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def test_near_duplicates_of_held_out_items_never_reach_train(self):
        base = synth_records(60)
        variants = []
        for r in base:
            t = r["text"]
            variants.append(dict(r, text=t.upper()))
            variants.append(dict(r, text=t + "!!"))
            words = t.split()
            if len(words) > 6:
                variants.append(dict(r, text=" ".join(words[:-1] + ["changed"])))
        r = ingest_split(self.sb, base + variants)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = slices(self.sb)
        held = s["test"] + s["dev"]
        self.assertTrue(held)
        for h in held:
            for t in s["train"]:
                self.assertLess(mimiclib.similarity(h["text"], t["text"]), 0.7, (h["text"], t["text"]))
        manifest = json.loads((self.sb.state("pat") / "split" / "manifest.json").read_text())
        self.assertLess(manifest["max_cross_similarity"], 0.7)
        self.assertGreater(manifest["dropped_near_duplicates"], 0)

    def test_similarity_catches_case_and_punctuation(self):
        self.assertEqual(mimiclib.similarity("ok!", "OK"), 1.0)
        self.assertGreaterEqual(mimiclib.similarity("ship the staging db fix today please", "ship the staging db fix today pls"), 0.7)
        self.assertLess(mimiclib.similarity("ok", "okay sure"), 0.7)


class Stratification(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def test_each_stratum_is_proportional(self):
        recs = synth_records(150)
        r = ingest_split(self.sb, recs)
        self.assertEqual(r.returncode, 0, r.stderr)
        s = slices(self.sb)
        total = Counter((x["band"], x["channel"]) for k in s for x in s[k])
        test = Counter((x["band"], x["channel"]) for x in s["test"])
        n_test = len(s["test"])
        n_all = sum(total.values())
        for key, cnt in total.items():
            self.assertLessEqual(abs(test[key] - n_test * cnt / n_all), 1.0, key)

    def test_rare_short_band_still_gets_a_test_item(self):
        # 95 long + 2 short, T=20: largest remainder alone gives short 0 slots (0.41 < 0.59).
        recs = [r for r in synth_records(300) if r["channel"] == "email"][:95]
        recs += [{"text": "nope", "channel": "chat"}, {"text": "sure thing pal", "channel": "chat"}]
        r = ingest_split(self.sb, recs)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(slices(self.sb)["test"]), 20)
        self.assertIn("short", {x["band"] for x in slices(self.sb)["test"]})


class ShortNearDuplicates(unittest.TestCase):
    def test_short_variants_cluster(self):
        texts = ["sounds good to me", "sounds good to me then", "nope", "lol yes", "on it, back by 5"]
        roots = mimiclib.near_dup_clusters(texts)
        self.assertEqual(roots[0], roots[1])
        self.assertEqual(len(set(roots)), 4)


class ContextLeak(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def test_train_context_quoting_a_held_out_message_is_redacted(self):
        recs = synth_records(60)
        for i, r in enumerate(recs):
            r["id"] = f"m{i}"
            r.pop("reply_to", None)
        for i in range(1, 60):  # every message replies to the one before it, a self-reply chain
            recs[i]["reply_to"] = f"m{i - 1}"
        self.assertEqual(ingest_split(self.sb, recs).returncode, 0)
        s = slices(self.sb)
        held = [h["text"] for h in s["test"] + s["dev"]]
        for t in s["train"]:
            for h in held:
                self.assertNotIn(mimiclib.canonical(h), mimiclib.canonical(t["context"]) if t["context"] else "")
        manifest = json.loads((self.sb.state("pat") / "split" / "manifest.json").read_text())
        self.assertGreater(manifest["redacted_contexts"], 0)


class Sizes(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def test_60_messages_give_20_test_and_no_dev(self):
        self.assertEqual(ingest_split(self.sb, synth_records(60)).returncode, 0)
        s = slices(self.sb)
        self.assertEqual((len(s["train"]), len(s["dev"]), len(s["test"])), (40, 0, 20))

    def test_200_messages_give_a_dev_slice(self):
        self.assertEqual(ingest_split(self.sb, synth_records(200)).returncode, 0)
        s = slices(self.sb)
        self.assertEqual(len(s["test"]), 40)
        self.assertEqual(len(s["dev"]), 20)

    def test_same_seed_same_files_other_seed_differs(self):
        recs = synth_records(80)
        ingest_split(self.sb, recs, "--seed", "7")
        first = (self.sb.state("pat") / "split" / "test.jsonl").read_bytes()
        self.assertEqual(self.sb.run("split.py", "--persona", "pat", "--seed", "7").returncode, 0)
        self.assertEqual((self.sb.state("pat") / "split" / "test.jsonl").read_bytes(), first)
        self.assertEqual(self.sb.run("split.py", "--persona", "pat", "--seed", "8").returncode, 0)
        self.assertNotEqual((self.sb.state("pat") / "split" / "test.jsonl").read_bytes(), first)

    def test_sealed_split_refuses_to_resplit(self):
        ingest_split(self.sb, synth_records(60))
        (self.sb.state("pat") / "split" / "test.sealed").write_text("{}")
        r = self.sb.run("split.py", "--persona", "pat")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.sb.run("split.py", "--persona", "pat", "--force").returncode, 0)

    def test_a_profile_blocks_resplitting_and_a_forced_resplit_invalidates_it(self):
        ingest_split(self.sb, synth_records(80))
        self.assertEqual(self.sb.run("profile.py", "skeleton", "--persona", "pat").returncode, 0)
        r = self.sb.run("split.py", "--persona", "pat", "--seed", "8")
        self.assertEqual(r.returncode, 2)
        self.assertIn("profile.md", r.stderr)
        self.assertEqual(self.sb.run("split.py", "--persona", "pat", "--seed", "8", "--force").returncode, 0)
        v = self.sb.run("profile.py", "validate", "--persona", "pat")
        self.assertIn("another split", v.stdout)

    def test_no_corpus_exits_2(self):
        self.assertEqual(self.sb.run("split.py", "--persona", "nobody").returncode, 2)


if __name__ == "__main__":
    unittest.main()
