"""Shared test helpers. The unique module name avoids the `conftest` collision that breaks
collection when CI runs every suite in one pytest session."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent / "scripts"))

from validate_procedure import validate_layers, validate_text  # noqa: E402,F401


def has(errors, word):
    return any(word in e for e in errors)
