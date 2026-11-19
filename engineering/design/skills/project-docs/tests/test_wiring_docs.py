"""AT-35: the AGENTS pointer carries the mandatory render line and flow.md lists render after validate."""

import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent


def test_agents_pointer_has_the_mandatory_render_line():
    text = (SKILL / "assets" / "AGENTS.pointer.md").read_text()
    assert "docs/**/*.md" in text
    assert "render_docs.py" in text
    assert "docs/generated/*" in text
    assert "--pr-summary" in text
    assert "pre-push" in text and "CI" in text


def test_flow_lists_render_after_validate():
    text = (SKILL / "references" / "flow.md").read_text()
    finish = text[text.index("## Finish"):]
    assert finish.index("**Validate.**") < finish.index("**Render.**") < finish.index("**Paste the summary.**")


def test_enforcement_documents_the_wiring_and_no_longer_says_it_is_unbuilt():
    text = (SKILL / "references" / "enforcement.md").read_text()
    for needle in ("pre-push", "project-docs-render", "--no-trigger", "docs/generated/**", "components.py"):
        assert needle in text, needle
    assert "later phase" not in text
    assert not re.search(r"copy `components.py` by hand", text)
