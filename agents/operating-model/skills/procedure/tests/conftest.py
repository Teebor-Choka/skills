collect_ignore = ["fixtures"]

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES = TESTS_DIR / "fixtures"
sys.path.insert(0, str(TESTS_DIR.parent / "scripts"))
