"""Tests for lint.py placeholder detection (E3).

Run: python3 -m pytest engineering/design/skills/architect/tests
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


# --- full tier: no per-node briefs (decompose files the per-unit items) ---

import os
import subprocess
import sys

SCAFFOLD = HERE.parent / "scripts" / "scaffold.py"


def _scaffold_full(tmp_path):
    root = tmp_path / "pkg"
    subprocess.run(
        [sys.executable, str(SCAFFOLD), "--slug", "demo", "--title", "Demo", "--tier", "full",
         "--dir", str(root)],
        check=True, capture_output=True,
    )
    return root


def _lint_fails(root):
    out = subprocess.run(
        [sys.executable, str(SCRIPT), str(root), "--tier", "full"],
        capture_output=True, text=True,
    ).stdout
    return sorted(line for line in out.splitlines() if line.startswith("FAIL"))


def test_full_scaffold_emits_no_agent_plans(tmp_path):
    root = _scaffold_full(tmp_path)
    assert not (root / "agent-plans").exists()
    assert (root / "invariants.md").exists()


def test_full_lint_does_not_require_agent_plans(tmp_path):
    root = _scaffold_full(tmp_path)
    fails = _lint_fails(root)
    assert not [f for f in fails if "E1" in f or "agent-plans" in f]


def test_stray_agent_plans_dir_does_not_change_lint(tmp_path):
    root = _scaffold_full(tmp_path)
    before = _lint_fails(root)
    (root / "agent-plans").mkdir(exist_ok=True)
    (root / "agent-plans" / "block-0.md").write_text("# Old brief\n\nNothing to lint.\n")
    assert _lint_fails(root) == before
