"""The output style may only name commands and skills this plugin ships. Run: python3 -m pytest communication/voice/tests"""
import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def read(*rel):
    with open(os.path.join(ROOT, *rel)) as f:
        return f.read()


class OutputStyle(unittest.TestCase):
    def test_e8_names_no_skill_absent_from_the_plugin(self):
        shipped = set(os.listdir(os.path.join(ROOT, "skills")))
        style = read("output-styles", "unslop.md")
        for name in re.findall(r"`([A-Za-z0-9:_-]+)`\s+skill\b", style):
            self.assertIn(name.split(":")[-1], shipped, f"style names skill {name!r} the plugin does not ship")
        self.assertNotIn("references/", style)
        self.assertNotIn("ste100", style)

    def test_e8_names_the_mode_command_by_its_plugin_name(self):
        style = read("output-styles", "unslop.md")
        self.assertIn("/voice:unslop-mode", style)
        self.assertNotRegex(style, r"(?<!voice:)/unslop-mode")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "commands", "unslop-mode.md")))

    def test_e8_the_command_names_no_skill_either(self):
        self.assertNotRegex(read("commands", "unslop-mode.md"), r"`unslop`\s+skill")


if __name__ == "__main__":
    unittest.main()
