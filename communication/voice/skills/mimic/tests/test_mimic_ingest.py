"""AT-2: ingest formats, normalization that keeps voice features, dedup, bands, input errors."""

import json
import unittest

from mimic_fixtures import Sandbox, read_jsonl

EML = """From: Pat Example <pat@example.invalid>
To: team@example.invalid
Subject: offsite dates
Content-Type: text/plain; charset=utf-8

works for me, book it

On Mon, Jan 5, 2026 at 10:00, Sam wrote:
> can we do the 12th?
> or the 19th

--\x20
Pat
"""

MBOX = """From pat@example.invalid Mon Jan  5 10:00:00 2026
From: Pat Example <pat@example.invalid>
Subject: one
Content-Type: text/plain

first mail body here

From sam@example.invalid Mon Jan  5 11:00:00 2026
From: Sam Other <sam@example.invalid>
Subject: two
Content-Type: text/plain

not pat at all

From pat@example.invalid Mon Jan  5 12:00:00 2026
From: Pat Example <pat@example.invalid>
Subject: three
Content-Type: text/plain

> quoted line
second mail body
"""


class Ingest(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()

    def tearDown(self):
        self.sb.close()

    def ingest(self, *files, extra=()):
        r = self.sb.run("ingest.py", "--persona", "pat", *extra, *files)
        self.assertEqual(r.returncode, 0, r.stderr)
        return read_jsonl(self.sb.state("pat") / "corpus.jsonl"), r

    def write(self, name, text):
        p = self.sb.root / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_txt_separator_and_blank_line_modes(self):
        a = self.write("a.txt", "one — two\n---\nLOL ok 😂\n---\n\n")
        b = self.write("b.txt", "first para\nsame msg\n\nsecond para\n")
        recs, _ = self.ingest(a, b)
        texts = [r["text"] for r in recs]
        self.assertEqual(texts, ["one — two", "LOL ok 😂", "first para\nsame msg", "second para"])

    def test_md_front_matter_skipped(self):
        p = self.write("n.md", "---\ntitle: x\n---\nhello there\n\nbye now\n")
        recs, _ = self.ingest(p)
        self.assertEqual([r["text"] for r in recs], ["hello there", "bye now"])

    def test_jsonl_fields_reply_to_by_id_and_text_and_author_filter(self):
        rows = [
            {"id": "m1", "text": "is the build green?", "author": "sam", "channel": "chat"},
            {"id": "m2", "text": "yep", "author": "pat", "reply_to": "m1", "channel": "chat", "audience": "peers", "ts": "t1"},
            {"text": "nah", "author": "pat", "reply_to": "want lunch?"},
            {"text": "  ", "author": "pat"},
        ]
        p = self.write("c.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
        recs, r = self.ingest(p, extra=["--author", "pat"])
        self.assertEqual([x["text"] for x in recs], ["yep", "nah"])
        self.assertEqual(recs[0]["context"], "is the build green?")
        self.assertEqual(recs[0]["channel"], "chat")
        self.assertEqual(recs[0]["audience"], "peers")
        self.assertEqual(recs[1]["context"], "want lunch?")
        self.assertEqual(recs[1]["channel"], "default")
        self.assertIn("empty 1", r.stdout)

    def test_json_array(self):
        p = self.write("d.json", json.dumps([{"text": "a"}, {"text": "b"}]))
        recs, _ = self.ingest(p)
        self.assertEqual(len(recs), 2)

    def test_duplicates_collapse_with_count_and_keep_casing(self):
        p = self.write("e.txt", "LGTM\n---\nLGTM \n---\nlgtm\n")
        recs, r = self.ingest(p)
        by = {x["text"]: x for x in recs}
        self.assertEqual(by["LGTM"]["count"], 2)
        self.assertEqual(by["lgtm"]["count"], 1)
        self.assertIn("duplicates 1", r.stdout)

    def test_band_and_ids(self):
        long_text = " ".join(["word"] * 26)
        p = self.write("f.txt", f"short one\n---\n{long_text}\n")
        recs, _ = self.ingest(p)
        self.assertEqual([x["band"] for x in recs], ["short", "long"])
        self.assertEqual([x["words"] for x in recs], [2, 26])
        self.assertRegex(recs[0]["id"], r"^[0-9a-f]{12}$")

    def test_eml_strips_quotes_and_signature(self):
        recs, _ = self.ingest(self.write("g.eml", EML))
        self.assertEqual(recs[0]["text"], "works for me, book it")
        self.assertEqual(recs[0]["channel"], "email")
        self.assertIn("offsite dates", recs[0]["context"])

    def test_mbox_with_author_filter(self):
        recs, _ = self.ingest(self.write("h.mbox", MBOX), extra=["--author", "pat@example.invalid"])
        self.assertEqual([x["text"] for x in recs], ["first mail body here", "second mail body"])

    def test_bad_json_line_exits_2_with_location(self):
        p = self.write("bad.jsonl", '{"text": "ok"}\n{nope\n')
        r = self.sb.run("ingest.py", "--persona", "pat", p)
        self.assertEqual(r.returncode, 2)
        self.assertIn("bad.jsonl:2", r.stderr)

    def test_missing_text_field_exits_2(self):
        p = self.write("bad2.jsonl", '{"msg": "ok"}\n')
        self.assertEqual(self.sb.run("ingest.py", "--persona", "pat", p).returncode, 2)

    def test_unknown_extension_exits_2(self):
        p = self.write("x.docx", "hi")
        self.assertEqual(self.sb.run("ingest.py", "--persona", "pat", p).returncode, 2)


if __name__ == "__main__":
    unittest.main()
