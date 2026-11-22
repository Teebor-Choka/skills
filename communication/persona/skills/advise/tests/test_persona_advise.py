"""persona:advise: the grounding helper and the skill text. Run: python3 -m pytest communication/persona/skills/advise/tests"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[3]
VALIDATOR = REPO / "ai" / "model" / "skills" / "extension-author" / "scripts" / "validate_skill.py"
SCRIPT = SKILL / "scripts" / "grounding.py"
sys.path.insert(0, str(SKILL / "scripts"))
import grounding  # noqa: E402


def node(nid, conf, ev):
    return {"id": nid, "type": "belief", "text": f"text {nid}", "confidence": conf,
            "evidence": [f"i{k}" for k in range(ev)], "created": 0, "updated": 0}


def mapof(*nodes):
    return {"version": 1, "persona": "pat", "step": 3, "nodes": list(nodes), "edges": []}


class Grounding(unittest.TestCase):
    def test_thin_evidence_is_low_even_with_high_confidence(self):
        r = grounding.summarize(mapof(node("b1", 0.9, 1), node("b2", 0.8, 1)), ["b1", "b2"])
        self.assertEqual(r["level"], "low")
        self.assertIn("low confidence", r["line"])

    def test_low_confidence_is_low(self):
        r = grounding.summarize(mapof(node("b1", 0.2, 6)), ["b1"])
        self.assertEqual(r["level"], "low")

    def test_well_supported_nodes_are_high(self):
        r = grounding.summarize(mapof(node("b1", 0.9, 5), node("b2", 0.8, 4)), ["b1", "b2"])
        self.assertEqual(r["level"], "high")
        self.assertIn("b1 (0.90, 5)", r["line"])

    def test_unknown_ids_are_flagged(self):
        r = grounding.summarize(mapof(node("b1", 0.9, 5)), ["b1", "ghost"])
        self.assertEqual(r["unknown"], ["ghost"])
        self.assertIn("ghost", r["line"])

    def test_empty_map_and_no_ids(self):
        r = grounding.summarize(mapof(), [])
        self.assertEqual(r["level"], "none")
        self.assertIn("outside the map", r["line"])
        r = grounding.summarize(mapof(), ["b1"])
        self.assertEqual(r["unknown"], ["b1"])

    def test_cli_exit_codes_and_no_writes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "map.json"
            p.write_text(json.dumps(mapof(node("b1", 0.9, 5))))
            before = sorted(x.name for x in Path(d).iterdir())
            ok = subprocess.run([sys.executable, str(SCRIPT), "--map", str(p), "b1"], capture_output=True, text=True)
            bad = subprocess.run([sys.executable, str(SCRIPT), "--map", str(p), "b1", "nope"], capture_output=True, text=True)
            gone = subprocess.run([sys.executable, str(SCRIPT), "--map", str(p) + ".x", "b1"], capture_output=True, text=True)
            self.assertEqual(sorted(x.name for x in Path(d).iterdir()), before)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("Grounding:", ok.stdout)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("nope", bad.stdout + bad.stderr)
        self.assertEqual(gone.returncode, 2)


class SkillText(unittest.TestCase):
    def setUp(self):
        self.text = (SKILL / "SKILL.md").read_text()

    def test_validates(self):
        r = subprocess.run([sys.executable, str(VALIDATOR), str(SKILL)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_frontmatter(self):
        fm = re.match(r"---\n(.*?)\n---\n", self.text, re.S).group(1)
        self.assertRegex(fm, r"(?m)^name: advise$")
        desc = re.search(r"(?m)^description: (.+)$", fm).group(1)
        self.assertLess(len(desc), 1024)
        for t in ("ask the persona advisor", "what would the persona advise", "advise me as the persona",
                  "persona:write", "persona:build"):
            self.assertIn(t, desc)

    def test_stays_short(self):
        self.assertLessEqual(len(self.text.splitlines()), 75)

    def test_states_the_rules(self):
        low = self.text.lower()
        for needle in ("simulation", "never invent", "never claim to be", "outside the map",
                       "low confidence", "grounding.py", "never write", "living private"):
            self.assertIn(needle, low)

    def test_never_directs_the_model_to_other_personas_or_the_sealed_slice(self):
        """Canary: the skill may name sealed files only to forbid them, and loads one persona."""
        for line in re.split(r"\n(?=\d+\. |- |#)", self.text):
            line = " ".join(line.split())
            low = line.lower()
            for bad in ("test.jsonl", "items.jsonl", "test.sealed", "final/", "corpus.jsonl", "log.jsonl"):
                if bad in low:
                    self.assertRegex(low, r"\b(never|not|do not)\b", line)
            self.assertNotRegex(low, r"\b(list|ls|scan|glob|browse)\b.*state/persona/?\s*$", line)
            self.assertNotIn("state/persona/*", low)
            if not re.search(r"\b(never|not)\b", low):
                self.assertNotRegex(low, r"(read|load|open) (the )?(other|every|all) persona", line)

    def test_trigger_evals(self):
        ev = json.loads((SKILL / "evals" / "evals.json").read_text())
        self.assertEqual(ev["skill_name"], "persona:advise")
        t = ev["trigger_evals"]
        self.assertGreaterEqual(sum(e["should_trigger"] for e in t), 3)
        self.assertGreaterEqual(sum(not e["should_trigger"] for e in t), 3)


if __name__ == "__main__":
    unittest.main()
