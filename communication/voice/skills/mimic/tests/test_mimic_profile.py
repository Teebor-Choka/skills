"""AT-6: profile skeleton and every validator failure path."""

import re
import unittest

from mimic_fixtures import Sandbox, build_state, read_jsonl

SECTIONS = ["Measured stats", "Mental model", "Habits", "Temperament", "Short messages", "Long messages",
            "Channels and audiences", "Lexicon", "Never", "Decisions and responses", "Worked examples"]
MODEL = ["Beliefs and values", "Framing", "Reasoning moves", "Emotional range", "Stance", "Compressed",
         "Expanded"]


class Profile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sb = Sandbox()
        cls.state = build_state(cls.sb)
        cls.good = (cls.state / "profile.md").read_text(encoding="utf-8")
        cls.train = read_jsonl(cls.state / "split" / "train.jsonl")
        cls.test = read_jsonl(cls.state / "split" / "test.jsonl")

    @classmethod
    def tearDownClass(cls):
        cls.sb.close()

    def validate(self, text):
        p = self.state / "candidate.md"
        p.write_text(text, encoding="utf-8")
        return self.sb.run("profile.py", "validate", "--persona", "pat", "--profile", p)

    def assertInvalid(self, text, needle):
        r = self.validate(text)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(needle, r.stdout + r.stderr)

    def test_skeleton_has_every_section_stats_and_train_examples(self):
        for s in SECTIONS:
            self.assertIn(f"## {s}\n", self.good)
        self.assertRegex(self.good, r"short: \d+ messages")
        ids = re.findall(r"- \[train:([0-9a-f]{12})\]", self.good)
        self.assertGreaterEqual(len(ids), 3)
        self.assertTrue(set(ids) <= {t["id"] for t in self.train})

    def test_skeleton_fails_on_todo(self):
        r = self.sb.run("profile.py", "validate", "--persona", "pat", "--profile", self.state / "missing.md")
        self.assertEqual(r.returncode, 2)
        self.assertInvalid(self.good.replace("## Habits\n", "## Habits\nTODO\n", 1), "TODO")

    def test_filled_profile_passes(self):
        r = self.validate(self.good)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_skeleton_refuses_to_overwrite(self):
        self.assertEqual(self.sb.run("profile.py", "skeleton", "--persona", "pat").returncode, 2)

    def test_missing_section(self):
        self.assertInvalid(self.good.replace("## Never\n", "## Nevermore\n"), "missing section: Never")

    def test_empty_section(self):
        text = re.sub(r"(## Lexicon\n)(.*?)(\n## )", r"\1\n\3", self.good, flags=re.S)
        self.assertInvalid(text, "empty section: Lexicon")

    def test_example_not_in_train(self):
        bad = self.good.replace("## Worked examples\n", "## Worked examples\n\n- [train:000000000000] made up line\n")
        self.assertInvalid(bad, "not in TRAIN")

    def test_example_text_differs_from_train(self):
        tid = self.train[0]["id"]
        bad = self.good.replace("## Worked examples\n", f"## Worked examples\n\n- [train:{tid}] edited words\n")
        self.assertInvalid(bad, "differs from TRAIN")

    def test_too_few_examples_and_no_short_example(self):
        head, _, _ = self.good.partition("## Worked examples\n")
        long_ex = next(t for t in self.train if t["band"] == "long")
        text = head + "## Worked examples\n\n- [train:{}] {}\n".format(long_ex["id"], long_ex["text"].replace("\n", "\\n"))
        r = self.validate(text)
        self.assertEqual(r.returncode, 1)
        self.assertIn("at least 3 worked examples", r.stdout)
        self.assertIn("short worked example", r.stdout)

    def test_channel_missing_from_matrix(self):
        text = self.good.replace("email", "mail")
        self.assertInvalid(text, "channel not in matrix: email")

    def test_held_out_text_leak(self):
        long_test = next(t for t in self.test if len(t["text"].split()) >= 8)
        bad = self.good.replace("## Lexicon\n", "## Lexicon\n\n" + long_test["text"] + "\n", 1)
        self.assertInvalid(bad, "held-out text")

    def test_skeleton_has_the_mental_model_subsections(self):
        model = self.good.split("## Mental model\n", 1)[1].split("\n## ", 1)[0]
        for sub in MODEL:
            self.assertIn(f"### {sub}\n", model)

    def test_missing_mental_model_subsection(self):
        self.assertInvalid(self.good.replace("### Reasoning moves\n", "### Moves\n"),
                           "missing mental model subsection: Reasoning moves")

    def test_empty_mental_model_subsection(self):
        text = re.sub(r"(### Stance\n)(.*?)(\n### )", r"\1\n\3", self.good, flags=re.S)
        self.assertInvalid(text, "empty mental model subsection: Stance")

    def test_at_most_six_worked_examples(self):
        shorts = [t for t in self.train if t["band"] == "short"][:7]
        lines = "".join(f"- [train:{t['id']}] {t['text']}\n" for t in shorts)
        head, _, _ = self.good.partition("## Worked examples\n")
        self.assertInvalid(head + "## Worked examples\n\n" + lines, "at most 6 worked examples")

    def test_stats_cover_the_analysis_measures(self):
        for key in ("hedging", "questions", "imperative", "person", "tense", "rhythm", "top words"):
            self.assertIn(key, self.good)

    def test_too_large(self):
        self.assertInvalid(self.good + "\nfiller words " * 2000, "16 KB")

    def test_split_hash_mismatch(self):
        self.assertInvalid(re.sub(r"split: \w+", "split: deadbeef", self.good), "split")

    def test_needs_a_split(self):
        r = self.sb.run("profile.py", "skeleton", "--persona", "nobody")
        self.assertEqual(r.returncode, 2)
        self.assertIn("split.py", r.stderr)


if __name__ == "__main__":
    unittest.main()
