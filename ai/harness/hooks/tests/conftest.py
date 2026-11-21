"""Tests must not inherit AGENT_* variables from the developer's environment."""
import os

import pytest


@pytest.fixture(autouse=True)
def _clean_agent_env(monkeypatch):
    for name in [n for n in os.environ if n.startswith("AGENT_")]:
        monkeypatch.delenv(name)
