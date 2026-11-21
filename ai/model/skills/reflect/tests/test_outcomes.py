"""outcomes.py: PR states from a faked `gh` on PATH (IM-16, IM-60). No network, no real gh."""
import json
import os
import stat

import pytest

from helpers import load, run_script, write

SHIM = """#!/bin/sh
# fake gh: gh pr view NUMBER --repo OWNER/REPO --json FIELDS
num="$3"
echo "$num" >> "$SHIM_DIR/calls.log"
n=$(grep -c "^$num$" "$SHIM_DIR/calls.log")
if [ -f "$SHIM_DIR/$num.once-ratelimit" ] && [ "$n" -eq 1 ]; then
  echo "API rate limit exceeded for user" >&2; exit 1
fi
if [ -f "$SHIM_DIR/$num.ratelimit" ]; then echo "API rate limit exceeded" >&2; exit 1; fi
if [ -f "$SHIM_DIR/$num.notfound" ]; then
  echo "GraphQL: Could not resolve to a PullRequest with the number of $num." >&2; exit 1
fi
cat "$SHIM_DIR/$num.json"
"""

MERGED = {"state": "MERGED", "createdAt": "2026-03-01T00:00:00Z", "mergedAt": "2026-03-01T12:00:00Z",
          "closedAt": "2026-03-01T12:00:00Z", "title": "SECRET TITLE", "body": "SECRET BODY",
          "reviews": [{"state": "CHANGES_REQUESTED"}, {"state": "COMMENTED"}, {"state": "APPROVED"}],
          "statusCheckRollup": [{"conclusion": "FAILURE"}, {"conclusion": "SUCCESS"}]}
CLOSED = {**MERGED, "state": "CLOSED", "mergedAt": None, "reviews": [], "statusCheckRollup": []}
OPEN = {**MERGED, "state": "OPEN", "mergedAt": None, "closedAt": None}


@pytest.fixture
def world(tmp_path):
    shim = tmp_path / "bin"
    shim.mkdir()
    gh = shim / "gh"
    gh.write_text(SHIM)
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
    data = tmp_path / "ghdata"
    data.mkdir()
    for num, body in ((1, MERGED), (2, CLOSED), (3, OPEN), (5, MERGED)):
        (data / f"{num}.json").write_text(json.dumps(body))
    (data / "4.notfound").write_text("")
    (data / "5.once-ratelimit").write_text("")
    (data / "6.ratelimit").write_text("")
    (data / "calls.log").write_text("")
    env = {**os.environ, "PATH": f"{shim}:{os.environ['PATH']}", "SHIM_DIR": str(data),
           "OUTCOMES_RETRY_SLEEP": "0"}
    return tmp_path, env, data


def records_file(tmp_path, refs):
    p = tmp_path / "records.jsonl"
    p.write_text(json.dumps({"session_id": "s", "prs": refs}) + "\n")
    return p


def run(world, refs, out=None):
    tmp_path, env, _ = world
    out = out or tmp_path / "outcomes.jsonl"
    r = run_script("outcomes.py", "--records", records_file(tmp_path, refs), "--out", out, env=env)
    assert r.returncode == 0, r.stderr
    rows = {row["ref"]: row for row in map(json.loads, out.read_text().splitlines())}
    return rows, out


def test_merged_closed_and_open_states(world):
    rows, _ = run(world, ["o/r#1", "o/r#2", "o/r#3"])
    assert rows["o/r#1"]["state"] == "MERGED" and rows["o/r#1"]["hours_to_merge"] == 12.0
    assert rows["o/r#1"]["review_rounds"] == 1 and rows["o/r#1"]["last_check"] == "SUCCESS"
    assert rows["o/r#2"]["state"] == "CLOSED" and rows["o/r#2"]["hours_to_merge"] is None
    assert rows["o/r#3"]["state"] == "OPEN"


def test_missing_pr_is_not_found_and_does_not_fail(world):
    rows, _ = run(world, ["o/r#4"])
    assert rows["o/r#4"]["state"] == "NOT_FOUND"


def test_rate_limit_retries_once_then_succeeds(world):
    rows, _ = run(world, ["o/r#5"])
    assert rows["o/r#5"]["state"] == "MERGED"
    assert world[2].joinpath("calls.log").read_text().split() == ["5", "5"]


def test_persistent_rate_limit_marks_unknown_after_one_retry(world):
    rows, _ = run(world, ["o/r#6"])
    assert rows["o/r#6"]["state"] == "UNKNOWN"
    assert world[2].joinpath("calls.log").read_text().split() == ["6", "6"]


def test_repeated_refs_are_one_lookup(world):
    run(world, ["o/r#1", "o/r#1"])
    assert world[2].joinpath("calls.log").read_text().split() == ["1"]


def test_final_states_are_cached_and_open_is_polled_again(world):
    rows, out = run(world, ["o/r#1", "o/r#3"])
    (world[2] / "calls.log").write_text("")
    run(world, ["o/r#1", "o/r#3"], out=out)
    assert world[2].joinpath("calls.log").read_text().split() == ["3"]


def test_titles_and_bodies_never_reach_the_file(world):
    _, out = run(world, ["o/r#1"])
    assert "SECRET" not in out.read_text()


def test_pr_refs_come_from_transcripts_too(world):
    tmp_path, env, _ = world
    t = write(tmp_path, [{"type": "pr-link", "prRepository": "o/r", "prNumber": 1,
                          "timestamp": "2026-03-01T00:00:00Z"},
                         {"type": "pr-link", "prRepository": "o/r", "prNumber": 1}], "t.jsonl")
    out = tmp_path / "o.jsonl"
    r = run_script("outcomes.py", t, "--out", out, env=env)
    assert r.returncode == 0 and json.loads(out.read_text())["state"] == "MERGED"


def test_missing_gh_marks_unknown_and_exits_zero(tmp_path):
    out = tmp_path / "o.jsonl"
    env = {"PATH": str(tmp_path), "HOME": str(tmp_path)}
    r = run_script("outcomes.py", "--records", records_file(tmp_path, ["o/r#1"]), "--out", out,
                   env=env)
    assert r.returncode == 0 and json.loads(out.read_text())["state"] == "UNKNOWN"


@pytest.mark.parametrize("states,label", [
    (["MERGED", "CLOSED"], "merged"), (["OPEN", "CLOSED"], "open"),
    (["UNKNOWN", "CLOSED"], "unknown"), (["CLOSED", "NOT_FOUND"], "closed"), ([], None)])
def test_session_label_from_its_pr_states(states, label):
    outcomes = load("outcomes.py")
    table = {f"o/r#{i}": {"state": s} for i, s in enumerate(states)}
    assert outcomes.session_label(list(table), table) == label
