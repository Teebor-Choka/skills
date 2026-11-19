#!/usr/bin/env python3
"""Stub: the renderer's interface, so the P2 acceptance tests fail on behaviour. Replaced next commit."""

from __future__ import annotations

import sys
from pathlib import Path


def render(project: Path) -> dict[str, str]:
    return {}


def main(argv: list[str] | None = None, version=sys.version_info) -> int:
    return 0


if __name__ == "__main__":
    sys.exit(main())
