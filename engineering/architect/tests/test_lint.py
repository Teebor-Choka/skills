"""Tests for lint.py placeholder detection (E3).

Run: python3 -m pytest engineering/architect/tests
"""
import importlib.util
import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "lint.py"


def _load():
    spec = importlib.util.spec_from_file_location("architect_lint", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lint = _load()


def _errs(text):
    errs = []
    lint.check_placeholders("doc.md", text, errs)
    return errs


@pytest.mark.parametrize(
    "text",
    [
        "Open items: FILL-IN",
        "owner is <name> until assigned",
        "TODO write this",
        "# <Title>",
        "see $slug-spec.md",
    ],
)
def test_bare_placeholder_is_flagged(text):
    assert _errs(text), text


@pytest.mark.parametrize(
    "text",
    [
        "Name the file `<slug>-plan.md` in the repo.",
        "Use the `<name>` field as the key.",
        "```\n<name>: TODO example\n```",
        "Mixed: `<n>` is fine but plain prose is clean.",
    ],
)
def test_placeholder_in_code_is_not_flagged(text):
    assert _errs(text) == [], text


def test_bare_placeholder_next_to_code_is_still_flagged():
    assert _errs("Valid `<name>` here, but <name> is left over.")


def test_unclosed_fence_does_not_hide_a_bare_placeholder_before_it():
    assert _errs("TODO now\n```\nnever closed")
