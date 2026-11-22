"""The architect/decompose boundary: the architect designs and stops; decompose files the units.

Run: python3 -m pytest engineering/design/skills/architect/tests
"""
import pathlib
import re

SKILLS = pathlib.Path(__file__).resolve().parents[2]
ARCHITECT = SKILLS / "architect"
DECOMPOSE = SKILLS / "decompose"
LINK = re.compile(r"\(((?:references|scripts|assets)/[^)\s#]+)")


def test_the_architect_no_longer_files_work_items():
    text = (ARCHITECT / "SKILL.md").read_text()
    assert "file the work to the tracker" not in text
    assert "Filing ends" not in text


def test_the_architect_hands_the_package_to_decompose():
    text = (ARCHITECT / "references" / "workflow.md").read_text()
    step = text[text.index("7. **State status honestly"):text.index("8. ")]
    assert "decompose" in step and "work.tracker" not in step


def test_the_architects_filing_guide_is_gone():
    assert not (ARCHITECT / "references" / "filing.md").exists()


def test_no_architect_file_still_points_at_the_removed_guide():
    for path in ARCHITECT.rglob("*.md"):
        assert "references/filing.md" not in path.read_text(), path


def test_every_reference_the_architect_links_exists():
    text = (ARCHITECT / "SKILL.md").read_text()
    missing = [m for m in LINK.findall(text) if not (ARCHITECT / m).exists()]
    assert not missing, missing


def test_decompose_carries_the_filing_guide():
    guide = (DECOMPOSE / "references" / "filing.md").read_text()
    for needle in ("work.tracker", "none", "Blocked by", "coordination channel", "dependency order"):
        assert needle in guide, needle


def test_decompose_links_its_filing_guide_and_it_exists():
    text = (DECOMPOSE / "SKILL.md").read_text()
    assert "references/filing.md" in text
    assert all((DECOMPOSE / m).exists() for m in LINK.findall(text))


def test_a_single_unit_plan_is_handed_to_the_executor_without_a_cut():
    text = (ARCHITECT / "references" / "workflow.md").read_text()
    step = text[text.index("7. **State status honestly"):text.index("8. ")]
    assert "implement" in step
