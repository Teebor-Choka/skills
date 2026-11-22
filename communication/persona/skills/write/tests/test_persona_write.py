"""The write skill file validates and states the profile path convention. Run: python3 -m pytest communication/persona/skills/write/tests"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[3]
VALIDATOR = REPO / "ai" / "model" / "skills" / "extension-author" / "scripts" / "validate_skill.py"


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return m.group(1)


class WriteSkill(unittest.TestCase):
    def setUp(self):
        self.text = (SKILL / "SKILL.md").read_text()

    def test_validates(self):
        r = subprocess.run([sys.executable, str(VALIDATOR), str(SKILL)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_name_matches_the_directory_and_description_fits(self):
        fm = frontmatter(self.text)
        self.assertRegex(fm, r"(?m)^name: write$")
        desc = re.search(r"(?m)^description: (.+)$", fm).group(1)
        self.assertLess(len(desc), 1024)
        for trigger in ("write as the persona", "draft this in the persona's voice", "reply as the persona"):
            self.assertIn(trigger, desc)
        self.assertIn("writing:unslop", desc)

    def test_refers_to_the_profile_path_convention(self):
        for needle in ("~/.config/agents/state/persona/<persona>/", "PERSONA_STATE_HOME", "profile.md", "map.md"):
            self.assertIn(needle, self.text)
        self.assertNotIn("state/voice", self.text)

    def test_states_the_honesty_contract(self):
        low = self.text.lower()
        self.assertIn("simulation", low)
        self.assertIn("never invent a quote", low)
        self.assertIn("never claim to be the person", low)

    def test_stays_short(self):
        self.assertLessEqual(len(self.text.splitlines()), 70)

    def test_trigger_evals_are_well_formed_and_balanced(self):
        evals = json.loads((SKILL / "evals" / "evals.json").read_text())
        self.assertEqual(evals["skill_name"], "persona:write")
        trig = evals["trigger_evals"]
        self.assertTrue(all(isinstance(e["query"], str) and isinstance(e["should_trigger"], bool) for e in trig))
        self.assertTrue(any(e["should_trigger"] for e in trig))
        self.assertTrue(any(not e["should_trigger"] for e in trig))


if __name__ == "__main__":
    unittest.main()
