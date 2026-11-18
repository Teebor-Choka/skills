"""The deploy stage contract (issue #109): the sections it must state and the rules the adversarial test needs."""
import json
import re
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"
PLUGIN = Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"
SECTIONS = ("Consumes", "Produces", "In scope", "Must not", "Hand-off", "Escalation", "Tier")


def _text():
    return SKILL.read_text()


def _section(name):
    m = re.search(rf"^## {name}\n(.*?)(?=^## |\Z)", _text(), re.S | re.M)
    assert m, f"missing section '## {name}'"
    return m.group(1)


def test_frontmatter_names_the_skill():
    head = _text().split("---")[1]
    assert re.search(r"^name: deploy$", head, re.M)
    assert "description:" in head


def test_stage_contract_sections_exist_in_order():
    heads = re.findall(r"^## (.+)$", _text(), re.M)
    assert [h for h in heads if h in SECTIONS] == list(SECTIONS)


def test_consumes_a_released_or_integrated_revision():
    s = _section("Consumes")
    assert "released" in s and "integrated" in s


def test_must_not_deploy_a_revision_whose_checks_failed():
    assert "checks did not pass" in _section("Must not")


def test_must_not_skip_the_repo_defined_diff():
    assert "diff" in _section("Must not")


def test_verification_reads_real_state_not_code():
    s = _section("In scope")
    assert "logs or state" in s and "reading code" in s


def test_failed_verification_leaves_the_stage_open_with_evidence():
    s = _section("Hand-off")
    assert "stays open" in s and "evidence" in s and "commands and output" in s


def test_produces_deployed_target_and_evidence():
    s = _section("Produces")
    assert "deployed target" in s and "evidence" in s


def test_insertion_and_tier_are_stated():
    assert "needs: [release]" in _text() and "needs: [integrate]" in _text()
    assert re.search(r"execution", _section("Tier"))


def test_plugin_manifest_matches_the_skill():
    assert json.loads(PLUGIN.read_text())["name"] == "deploy"
