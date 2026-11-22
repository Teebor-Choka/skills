#!/usr/bin/env python3
"""Predictive world-model loop (skeleton: the interface the tests drive, no behaviour yet)."""

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import personalib as m  # noqa: E402


@dataclass
class Opts:
    models: dict = field(default_factory=dict)
    threshold: float = 0.3
    window: int = 20
    consolidate_every: int = 10
    max_nodes: int = 120
    max_map_bytes: int = 16384
    exemplars: int = 4
    seed: int = 1337


def _todo(*_a, **_k):
    raise NotImplementedError("world.py: not implemented yet")


init = run = apply_patches = prune = render = validate_map = surprise = curve = parse_ts = file_hash = _todo
empty_map = _todo

if __name__ == "__main__":
    m.main_wrapper(_todo)
