"""git-guard reads its transcript scan from skill_loaded.py beside it. Plugins install independently, so
this plugin ships its own copy (tested in test_skill_loaded.py); these tests pin the git-guard contract."""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..")


class VendoredScan(unittest.TestCase):
    def test_copy_exists_next_to_git_guard(self):
        self.assertTrue(os.path.isfile(os.path.join(HOOKS, "skill_loaded.py")))

    def test_git_guard_has_no_scan_of_its_own(self):
        with open(os.path.join(HOOKS, "git-guard")) as f:
            self.assertNotIn("_SKILL_LOADED", f.read())


if __name__ == "__main__":
    unittest.main()
