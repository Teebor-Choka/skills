"""Shared test helpers. The unique module name avoids the `conftest` collision that breaks
collection when CI runs every suite in one pytest session."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent / "scripts"))

import validate_procedure as _vp  # noqa: E402
from check_translation import check_translation, main as check_translation_main  # noqa: E402,F401

# Structure tests build minimal procedures with no metrics, so they run non-strict.
# `strict_*` and the CLI enforce the metrics, KPI and change-hypothesis rules.
strict_validate_text = _vp.validate_text
strict_validate_layers = _vp.validate_layers
main = _vp.main


def validate_text(text, src="<text>"):
    return _vp.validate_text(text, src, strict=False)


def validate_layers(base_text, delta_text, src="<delta>"):
    return _vp.validate_layers(base_text, delta_text, src, strict=False)


def has(errors, word):
    return any(word in e for e in errors)


CHANGE = "change:\n  reason: tested\n  metrics: [m]\n  direction: down\n  window: 5 runs\n"


def delta(body, change=CHANGE):
    """A delta overlay with a change hypothesis, the way every non-empty delta must come."""
    return f"---\n{change}{body}---\n"
