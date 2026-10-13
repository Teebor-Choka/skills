# fixtures/ holds sample repo doc trees used AS TEST DATA (copied into a tmp
# dir and mutated by test_validate_docs.py). They are markdown, not Python, so
# pytest would not collect them anyway, but ignore the dir explicitly to keep
# discovery from ever walking into it.
collect_ignore = ["fixtures"]

import shutil
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
FIXTURES = TESTS_DIR / "fixtures"
SCRIPTS = TESTS_DIR.parent / "scripts"

# Import the validator as a module (standard-library-only, no install step).
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture(scope="session")
def conformant_src() -> Path:
    return FIXTURES / "conformant"


@pytest.fixture
def make_repo(tmp_path):
    """Factory: copy the conformant fixture into a fresh tmp dir so a test can
    mutate exactly one thing and check that one rule fires."""

    def _make(name: str = "repo") -> Path:
        dest = tmp_path / name
        shutil.copytree(FIXTURES / "conformant", dest)
        return dest

    return _make
