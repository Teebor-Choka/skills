import subprocess, sys, tempfile, unittest
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

    def test_sentence_initial_capital_is_not_a_name(self):
        r = self.check("[00:00:01] Today we ship. Then we rest.\n", "We ship and rest.")
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
