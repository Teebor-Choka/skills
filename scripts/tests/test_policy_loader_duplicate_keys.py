"""A repeated frontmatter key at one level is an error, not a silent last-wins overwrite."""

import importlib.util
from pathlib import Path

import pytest

LOADER = Path(__file__).resolve().parents[2] / "ai/harness/skills/policy/policy_loader.py"
spec = importlib.util.spec_from_file_location("policy_loader", LOADER)
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


def test_a_repeated_key_at_the_same_level_names_the_key_and_line():
    block = "gate: tests\nmode: single\ngate: ci"
    with pytest.raises(loader.PolicyError, match=r"x\.md:3.*'gate'"):
        loader._parse_frontmatter(block, "x.md")


def test_a_repeated_nested_key_is_an_error():
    block = "stages:\n  review:\n    floor: true\n  review:\n    floor: false"
    with pytest.raises(loader.PolicyError, match=r"x\.md:4.*'review'"):
        loader._parse_frontmatter(block, "x.md")


def test_the_same_key_under_two_parents_stays_valid():
    block = "a:\n  floor: true\nb:\n  floor: false"
    assert loader._parse_frontmatter(block, "x.md") == {"a": {"floor": True}, "b": {"floor": False}}
