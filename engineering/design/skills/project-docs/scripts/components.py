#!/usr/bin/env python3
"""Resolve a project's components. STUB: the red commit; the real resolver follows."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Component:
    name: str
    path: str
    depends_on: tuple[str, ...]
    source: str


class NeedsInput(Exception):
    def __init__(self, missing: list[dict]) -> None:
        super().__init__("needs-input")
        self.missing = missing


class ManifestError(Exception):
    pass


def page_name(name: str) -> str:
    return name


def policy_options(project: Path):
    return None, {}


def resolve(project: Path, include=None, exclude=None) -> list[Component]:
    return []


def main(argv: list[str] | None = None) -> int:
    print(json.dumps({"status": "ok", "components": []}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
