#!/usr/bin/env python3
"""Outcome labels for sessions that touched pull requests: state, hours to merge, review
rounds and last check state per distinct PR (references/metrics.md, north star).

    outcomes.py [PATH ...] [--records FILE] --out outcomes.jsonl

PATH is a transcript or folder; --records is a JSONL file of session records with a `prs` list
(metrics.py scan output). A PR is `owner/repo#number`; repeats are one lookup. OUT is also the
cache: a MERGED, CLOSED or NOT_FOUND row is final and never polled again; OPEN and UNKNOWN rows
are polled on every run.

One `gh pr view` per PR, asking only for state, times, review states and check results, so a PR
title or body never reaches the file. A rate limit is retried once, then the PR is UNKNOWN. Any
other failure is UNKNOWN. The script always exits 0: a missing `gh` or a bad PR never stops a
weekly job. It is the only script here that uses the network, and only through `gh`.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works under python -I
import metrics  # noqa: E402
import reflectlib as lib  # noqa: E402

FINAL = ("MERGED", "CLOSED", "NOT_FOUND")
FIELDS = "state,createdAt,mergedAt,closedAt,reviews,statusCheckRollup"
RATE_RE = re.compile(r"rate limit", re.I)
NOT_FOUND_RE = re.compile(r"Could not resolve|HTTP 404|not found", re.I)
PRECEDENCE = ("MERGED", "OPEN", "UNKNOWN")


def session_label(refs, table):
    """merged, open, unknown or closed for a session's PRs (best state wins), None without PRs."""
    states = {table.get(r, {}).get("state", "UNKNOWN") for r in refs}
    for state in PRECEDENCE:
        if state in states:
            return state.lower()
    return "closed" if states else None


def _gh(repo, number):
    """(json dict, None) or (None, stderr text). Retries one rate-limited call."""
    for attempt in (1, 2):
        try:
            p = subprocess.run(["gh", "pr", "view", str(number), "--repo", repo, "--json", FIELDS],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            return None, str(e)
        if p.returncode == 0:
            try:
                return json.loads(p.stdout), None
            except ValueError:
                return None, "unparseable gh output"
        if attempt == 1 and RATE_RE.search(p.stderr):
            time.sleep(float(os.environ.get("OUTCOMES_RETRY_SLEEP", "2")))
            continue
        return None, p.stderr
    return None, "rate limit"


def _hours(a, b):
    ta, tb = lib.parse_ts(a), lib.parse_ts(b)
    return None if ta is None or tb is None else round((tb - ta) / 3600, 2)


def lookup(ref):
    repo, number = ref.rsplit("#", 1)
    data, err = _gh(repo, number)
    row = {"ref": ref, "repo": repo, "number": int(number), "state": "UNKNOWN", "created": None,
           "merged": None, "closed": None, "hours_to_merge": None, "review_rounds": None,
           "last_check": None}
    if data is None:
        if err and NOT_FOUND_RE.search(err) and not RATE_RE.search(err):
            row["state"] = "NOT_FOUND"
        return row
    reviews = [r for r in data.get("reviews") or [] if isinstance(r, dict)]
    checks = [c for c in data.get("statusCheckRollup") or [] if isinstance(c, dict)]
    last = checks[-1] if checks else {}
    row.update(
        state=str(data.get("state") or "UNKNOWN").upper(),
        created=data.get("createdAt"), merged=data.get("mergedAt"), closed=data.get("closedAt"),
        review_rounds=sum(1 for r in reviews if r.get("state") == "CHANGES_REQUESTED"),
        last_check=last.get("conclusion") or last.get("state"))
    if row["merged"]:
        row["hours_to_merge"] = _hours(row["created"], row["merged"])
    return row


def refs_of(paths, records):
    refs = set()
    for p in lib.collect_files(paths):
        try:
            refs.update(metrics.full_record(p)["prs"])
        except (OSError, ValueError):
            continue
    if records:
        with open(records, errors="replace") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict) and isinstance(rec.get("prs"), list):
                    refs.update(r for r in rec["prs"] if isinstance(r, str) and "#" in r)
    return sorted(refs)


def read_cache(path):
    cache = {}
    try:
        with open(path) as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("state") in FINAL and row.get("ref"):
                    cache[row["ref"]] = row
    except OSError:
        pass
    return cache


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--records")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    refs = refs_of(a.paths, a.records)
    cache = read_cache(a.out)
    rows = {r: cache[r] if r in cache else lookup(r) for r in refs}
    with open(a.out, "w") as fh:
        for r in refs:
            fh.write(json.dumps(rows[r], sort_keys=True) + "\n")
    counts = {}
    for row in rows.values():
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    print(json.dumps({"prs": len(refs), "states": dict(sorted(counts.items())),
                      "polled": len(refs) - sum(1 for r in refs if r in cache)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
