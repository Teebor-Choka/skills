"""git-guard and skill-gate share one transcript scan. Plugins install independently, so each ships its own
copy of skill_loaded.py; these tests pin this copy to the swe-workflows one and to the git-guard contract."""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..")
SIBLING = os.path.join(HERE, "..", "..", "..", "..", "swe", "swe-workflows", "hooks", "skill_loaded.py")


class VendoredScan(unittest.TestCase):
    def test_copy_exists_next_to_git_guard(self):
        self.assertTrue(os.path.isfile(os.path.join(HOOKS, "skill_loaded.py")))

    @unittest.skipUnless(os.path.isfile(SIBLING), "swe-workflows is not in this checkout")
    def test_copy_is_byte_identical_to_the_swe_workflows_one(self):
        with open(os.path.join(HOOKS, "skill_loaded.py"), "rb") as a, open(SIBLING, "rb") as b:
            self.assertEqual(a.read(), b.read(), "update both copies together")

    def test_git_guard_has_no_scan_of_its_own(self):
        with open(os.path.join(HOOKS, "git-guard")) as f:
            self.assertNotIn("_SKILL_LOADED", f.read())


if __name__ == "__main__":
    unittest.main()
