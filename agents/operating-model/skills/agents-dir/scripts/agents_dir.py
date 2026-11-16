#!/usr/bin/env python3
"""Validate a project's `.agents/` directory against the layout contract. Stdlib only.

    agents_dir.py REPO [--base REF]

Without `--base` it checks the files as they are. With `--base` it also checks the change since that
ref: a change to the process documents must add an iteration record.
"""
import sys

__all__ = ("check_agents_dir", "process_revision", "main")


def check_agents_dir(repo, base=None):
    """Return a list of error strings for the `.agents/` directory of `repo`. Stub."""
    return []


def process_revision(repo):
    """The commit that last changed the process documents, or None. Stub."""
    return None


def main(argv=None):
    return 0


if __name__ == "__main__":
    sys.exit(main())
