import shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

S = Path(__file__).resolve().parent.parent / "scripts"

AUTO_VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.000 align:start position:0%
we raised<00:00:01.500><c> 42</c><c.colorE5E5E5><00:00:02.000><c> million</c>

00:00:03.000 --> 00:00:03.010 align:start position:0%
we raised 42 million

00:00:03.010 --> 00:00:05.000 align:start position:0%
we raised 42 million
in March 2024

00:00:05.000 --> 00:00:05.010 align:start position:0%
in March 2024

00:01:05.000 --> 00:01:07.000
Alice Smith said "no".
"""


def run(script, *args):
    return subprocess.run([sys.executable, "-I", str(S / script), *args],
                          capture_output=True, text=True)


class Vtt2Txt(unittest.TestCase):
    def test_dedupes_rolling_auto_captions_and_strips_tags(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "a.vtt"); p.write_text(AUTO_VTT)
            r = run("vtt2txt.py", str(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            "[00:00:01] we raised 42 million",
            "[00:00:03] in March 2024",
            '[00:01:05] Alice Smith said "no".',
        ])

    def test_empty_input_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d, "a.vtt"); p.write_text("WEBVTT\n\n")
            r = run("vtt2txt.py", str(p))
        self.assertNotEqual(r.returncode, 0)


class Coverage(unittest.TestCase):
    def check(self, transcript, summary):
        with tempfile.TemporaryDirectory() as d:
            t, s = Path(d, "t.txt"), Path(d, "s.md")
            t.write_text(transcript); s.write_text(summary)
            return run("check_coverage.py", str(t), str(s))

    def test_reports_missing_number_name_and_quote(self):
        r = self.check('[00:00:01] Alice Smith raised 42 million in 2024 and said "never again"\n',
                       "Raised funds in 2024.")
        self.assertEqual(r.returncode, 1)
        for missing in ("42", "Alice Smith", "never again"):
            self.assertIn(missing, r.stdout)
        self.assertNotIn("2024", r.stdout)

    def test_clean_when_everything_present(self):
        r = self.check("[00:00:01] Alice Smith raised 42 million\n",
                       "Alice Smith raised 42 million.")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_omitted_section_justifies_items(self):
        r = self.check("[00:00:01] Bob said 7 things\n",
                       "Bob spoke.\n\n## Omitted\n- 7: filler count\n")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_sentence_start_filler_before_a_name_is_not_part_of_it(self):
        r = self.check("[00:00:01] But Rich Dad said so. Meet David. Say Warren Buffett won.\n",
                       "Rich Dad, David and Warren Buffett.")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_contractions_and_possessives_are_not_names(self):
        r = self.check("[00:00:01] We think I'm right. That's fair. Azer's way. We'll see.\n",
                       "Azer.")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_comma_separated_names_stay_separate(self):
        r = self.check("[00:00:01] in Tokyo, New York, or Cairo.\n", "Tokyo; New York; Cairo.")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_real_missing_name_at_sentence_start_still_reported(self):
        r = self.check("[00:00:01] Alice Smith left.\n", "Alice left.")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Smith", r.stdout)

    def test_sentence_initial_capital_is_not_a_name(self):
        r = self.check("[00:00:01] Today we ship. Then we rest.\n", "We ship and rest.")
        self.assertEqual(r.returncode, 0, r.stdout)


@unittest.skipUnless(shutil.which("jq"), "jq needed")
class FetchPlaylist(unittest.TestCase):
    ENTRIES = ('{"id":"aaa","title":"One","duration":10,"playlist_index":1}\n'
               '{"id":"bbb","title":"Two","duration":20,"playlist_index":2}\n')

    def fetch(self, url, *flags):
        import os
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d, "yt-dlp")
            stub.write_text("#!/bin/sh\ncat <<'EOF'\n" + self.ENTRIES + "EOF\n"); stub.chmod(0o755)
            env = {**os.environ, "PATH": f"{d}:{os.environ['PATH']}", "MEDIA_DIGEST_IN_NIX": "1"}
            return subprocess.run(["sh", str(S / "fetch.sh"), url, *flags],
                                  capture_output=True, text=True, env=env)

    def test_playlist_url_lists_entries_instead_of_fetching_one_video(self):
        import json
        r = self.fetch("https://www.youtube.com/playlist?list=PLabc")
        self.assertEqual(r.returncode, 3, r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["status"], "playlist")
        self.assertEqual([e["id"] for e in out["entries"]], ["aaa", "bbb"])
        self.assertEqual(out["entries"][0]["url"], "https://www.youtube.com/watch?v=aaa")

    def test_watch_url_with_list_param_is_not_a_playlist(self):
        with tempfile.TemporaryDirectory() as out:
            r = self.fetch("https://www.youtube.com/watch?v=aaa&list=PLabc", "--out", out)
        self.assertNotIn('"playlist"', r.stdout)


class LinkTimestamps(unittest.TestCase):
    def link(self, text, meta):
        import json
        with tempfile.TemporaryDirectory() as d:
            sm, mt = Path(d, "s.md"), Path(d, "meta.json")
            sm.write_text(text); mt.write_text(json.dumps(meta))
            r = run("link_timestamps.py", str(sm), str(mt))
            return r, sm.read_text()

    YT = {"extractor": "Youtube", "url": "https://www.youtube.com/watch?v=abc123"}

    def test_youtube_point_and_range(self):
        r, out = self.link("A [00:01:05] b [00:02:00–00:03:00] c", self.YT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("[00:01:05](https://www.youtube.com/watch?v=abc123&t=65s)", out)
        self.assertIn("[00:02:00–00:03:00](https://www.youtube.com/watch?v=abc123&t=120s)", out)

    def test_idempotent(self):
        _, once = self.link("x [00:00:09] y", self.YT)
        _, twice = self.link(once, self.YT)
        self.assertEqual(once, twice)

    def test_vimeo_fragment(self):
        _, out = self.link("[00:00:10]", {"extractor": "Vimeo", "url": "https://vimeo.com/123"})
        self.assertIn("(https://vimeo.com/123#t=10s)", out)

    def test_unknown_site_and_article_unchanged(self):
        for meta in ({"extractor": "Generic", "url": "https://x.org/v"},
                     {"extractor": "trafilatura", "url": "https://x.org/a"}):
            _, out = self.link("see [00:00:10]", meta)
            self.assertEqual(out, "see [00:00:10]")


if __name__ == "__main__":
    unittest.main()
