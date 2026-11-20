#!/usr/bin/env python3
"""Check every-proposal-is-within-its-rung. See README.md in this directory for what it reads."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

import os
import subprocess
import sys

RUNGS = ("free", "ordinary", "protected", "frozen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))


def git(worktree, *args, stdin=None):
    return subprocess.run(["git", "-C", worktree, *args], input=stdin, capture_output=True, check=True).stdout


def base_files(worktree, head):
    """Files committed at head, as path -> bytes."""
    listing = git(worktree, "ls-tree", "-r", "-z", head).split(b"\0")
    entries = [e.split(b"\t", 1) for e in listing if e]
    shas = [meta.split()[2] for meta, _path in entries]
    blobs = {}
    for sha in shas:
        blobs[sha] = git(worktree, "cat-file", "blob", sha.decode())
    return {path.decode(): blobs[meta.split()[2]] for meta, path in entries}


def work_files(worktree):
    """Regular files in the working tree, skipping .git. A symlink is refused."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(worktree):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                raise ValueError(f"symlink in the working tree: {os.path.relpath(full, worktree)}")
            with open(full, "rb") as f:
                out[os.path.relpath(full, worktree).replace(os.sep, "/")] = f.read()
    return out


def check(ev):
    allowed = {r for r in os.environ.get("ORG_ALLOWED_RUNGS", "").split(",") if r}
    if not allowed or not allowed <= set(RUNGS):
        return ["ORG_ALLOWED_RUNGS must name the rungs the runtime allows (set by the runtime, never by evidence)"]
    change = ev.change()
    try:
        from check_change import check_change
    except ImportError as e:
        return [f"cannot import check_change (scripts/check_change.py): {e}"]
    try:
        base = base_files(change["worktree"], change["head"])
        new = work_files(change["worktree"])
        both_base = {p: base.get(p) for p in set(base) | set(new)}
        both_new = {p: new.get(p) for p in set(base) | set(new)}
        entries, refused = check_change(both_base, both_new, allowed)
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        return [f"the change cannot be classified: {e!r}"]
    if not entries:
        return ["the change is empty: the working tree equals the head"]
    return [f"{path}: rung '{rung}' ({row}); allowed: {sorted(allowed)}" for path, _task, row, rung in refused]


if __name__ == "__main__":
    _lib.run(check, parse_output=False)
