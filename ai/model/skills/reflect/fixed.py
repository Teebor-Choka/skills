#!/usr/bin/env python3
"""Mark findings FIXED when their last occurrence predates the fix commit.

Input: a JSON list of findings, each {"id", "files": [paths the finding names: a hook,
skill, setting], "last_seen": ISO time of its last occurrence in a transcript}. For each
finding, `git log -1` on its files gives the newest commit touching them. The finding is
FIXED when it was last seen before that commit, OPEN when seen after, UNKNOWN when it names
no tracked file or has no last_seen. A FIXED mark is a lead: read the commit subject before
you drop the finding, since an unrelated later edit moves the date too.

Usage: fixed.py REPO FINDINGS.json
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works under python -I
import reflectlib as lib  # noqa: E402


def last_commit(repo, path):
    """(sha, committer date, subject) of the newest commit touching path, else None."""
    out = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%H%x09%cI%x09%s", "--",
                          path], capture_output=True, text=True)
    line = out.stdout.strip()
    if out.returncode != 0 or not line:
        return None
    sha, date, subject = line.split("\t", 2)
    return {"sha": sha, "date": date, "subject": subject, "file": path}


def mark(findings, repo):
    result = []
    for f in findings:
        seen = lib.parse_ts(f.get("last_seen"))
        commits = [c for c in (last_commit(repo, p) for p in f.get("files") or []) if c]
        if seen is None or not commits:
            result.append({**f, "status": "UNKNOWN"})
            continue
        newest = max(commits, key=lambda c: lib.parse_ts(c["date"]))
        if seen < lib.parse_ts(newest["date"]):
            result.append({**f, "status": "FIXED", "fix": newest})
        else:
            result.append({**f, "status": "OPEN", "fix": None})
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[1]) as fh:
        findings = json.load(fh)
    json.dump(mark(findings, argv[0]), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
