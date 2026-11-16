#!/usr/bin/env python3
"""Resolve a run's process documents from the project and the user's config. Stdlib only.

    resolver.py PROJECT [--procedure NAME] [--allow-dirty]

For each document the project's `.agents/` wins over the user's `$XDG_CONFIG_HOME/agents/`. With
neither, there is nothing to resolve and the tool does nothing. Stub.
"""
import sys

__all__ = ("resolve", "start_run", "ResolutionError", "main")


class ResolutionError(Exception):
    """The documents cannot start a run. `errors` lists why."""

    def __init__(self, errors):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


def resolve(project, *, environ=None, name=None, allow_dirty=False):
    return None


def start_run(project, *, environ=None, name=None, allow_dirty=False, trust="claims", run_id=None):
    return None


def main(argv=None):
    return 0


if __name__ == "__main__":
    sys.exit(main())
