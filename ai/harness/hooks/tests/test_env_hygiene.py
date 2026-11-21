"""The suite runs with AGENT_* cleared. Try: AGENT_SKILLS_DIRS=/x python3 -m pytest hooks/tests"""
import os
import unittest


class EnvHygiene(unittest.TestCase):
    def test_no_agent_variables_leak_into_the_tests(self):
        self.assertEqual([n for n in os.environ if n.startswith("AGENT_")], [])
