"""Regressions from the security review: hostile ledger and ingest lines, untrusted worktree paths, deep inputs."""

import json
import subprocess

import pytest

from status_testlib import load


def ledger(path, entries):
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))


def header(seq=1, **body):
    return {"seq": seq, "prev": None, "kind": "header", "mac": "m%d" % seq, "body": dict({"run_id": "r1", "workflow": "tdd-unit", "input": {}}, **body)}


@pytest.mark.parametrize("bad", [[1], 5, "x", {"seq": 2, "prev": "m1", "kind": "log", "body": {"kind": "task-start", "key": ["a"], "t": "soon"}},
                                 {"seq": 2, "prev": "m1", "kind": "host", "body": {"call": "step", "key": "k", "result": {"duration": "long", "output": {"cost": {"usd": "free"}}}}}])
def test_a_malformed_ledger_line_is_a_problem_not_a_crash(tmp_path, bad):
    live = load("live")
    p = tmp_path / "a.ledger"
    ledger(p, [header(), bad, {"seq": 3, "prev": "m2", "kind": "log", "mac": "m3", "body": {"kind": "run-end", "status": "success"}}])
    lv = live.Live({"ledgers": [str(p)]})
    lv.poll()
    run = lv.snapshot()["runs"][0]
    assert run["problems"]
    assert run["end_status"] == "success"


def test_a_header_with_a_non_text_run_id_does_not_crash(tmp_path):
    live = load("live")
    p = tmp_path / "a.ledger"
    ledger(p, [header(run_id=7)])
    lv = live.Live({"ledgers": [str(p)]})
    lv.poll()
    lv.snapshot()


def test_a_run_id_cannot_walk_out_of_the_sessions_folder(tmp_path):
    live = load("live")
    (tmp_path / "x.calls.jsonl").write_text(json.dumps({"usd": 99}) + "\n")
    (tmp_path / "runs" / "sessions").mkdir(parents=True)
    p = tmp_path / "runs" / "a.ledger"
    ledger(p, [header(run_id="../../x")])
    lv = live.Live({"ledgers": [str(p)]})
    lv.poll()
    assert lv.snapshot()["runs"][0]["cost_usd"] == 0


def test_a_dispatcher_ledger_name_cannot_leave_the_ledgers_folder(tmp_path):
    live = load("live")
    sd = tmp_path / "state"
    (sd / "ledgers").mkdir(parents=True)
    ledger(tmp_path / "outside.ledger", [header()])
    (sd / "dispatcher.json").write_text(json.dumps({"pairs": {"e\nw": {"ledger": "../../outside.ledger"}}}))
    lv = live.Live({"state_dirs": [str(sd)]})
    lv.poll()
    assert lv.snapshot()["runs"] == []


def git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def change_ledger(path, wt):
    ledger(path, [header(), {"seq": 2, "prev": "m1", "kind": "host", "mac": "m2",
                             "body": {"call": "change", "key": "k", "result": {"worktree": str(wt), "head": "abc"}}}])


def hostile_repo(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    git("init", "-q", cwd=wt)
    marker = tmp_path / "pwned"
    git("config", "core.fsmonitor", "touch %s; false" % marker, cwd=wt)
    (wt / "f.txt").write_text("x")
    return wt, marker


def test_a_worktree_outside_the_allowed_roots_is_never_inspected(tmp_path):
    live = load("live")
    wt, marker = hostile_repo(tmp_path)
    p = tmp_path / "a.ledger"
    change_ledger(p, wt)
    lv = live.Live({"ledgers": [str(p)]})
    lv.poll(now=1e9)
    ch = lv.snapshot()["runs"][0]["change"]
    assert ch["files"] is None and "worktree-root" in ch["note"]
    assert not marker.exists()


def test_an_allowed_worktree_never_runs_its_fsmonitor(tmp_path):
    live = load("live")
    wt, marker = hostile_repo(tmp_path)
    p = tmp_path / "a.ledger"
    change_ledger(p, wt)
    lv = live.Live({"ledgers": [str(p)], "worktree_roots": [str(tmp_path)]})
    lv.poll(now=1e9)
    ch = lv.snapshot()["runs"][0]["change"]
    assert ch["files"] == [{"status": "??", "path": "f.txt"}]
    assert not marker.exists()


def chained(n):
    # newest first, so the first unit projected sits at the end of the chain
    return {"U%d" % i: {"unit": "U%d" % i, "state": "queued", "deps": ["U%d" % (i - 1)] if i > 1 else [], "at": i, "seq": i} for i in range(n, 0, -1)}


def test_a_long_dependency_chain_gets_waves_without_recursion(tmp_path):
    ingest = load("ingest")
    units = {u["id"]: u for u in ingest.project_units([], chained(3000), [], {})}
    assert units["U1"]["w"] == 1 and units["U3000"]["w"] == 3000


def test_a_dependency_cycle_still_gets_waves():
    ingest = load("ingest")
    ing = {"U1": {"unit": "U1", "state": "queued", "deps": ["U2"], "at": 1, "seq": 1},
           "U2": {"unit": "U2", "state": "queued", "deps": ["U1"], "at": 2, "seq": 2}}
    units = {u["id"]: u for u in ingest.project_units([], ing, [], {})}
    assert units["U1"]["w"] >= 1 and units["U2"]["w"] >= 1


def test_a_chained_line_that_fails_validation_breaks_the_log(tmp_path):
    ingest = load("ingest")
    log = tmp_path / "events.jsonl"
    ingest.append({"unit": "U1", "state": "building"}, "test", log)
    st = ingest.read(log)
    line = {"seq": 2, "prev": st["head"], "at": 1.0, "src": "file", "state": "bogus"}
    line["hash"] = ingest._hash(st["head"], line)
    with open(log, "a") as f:
        f.write(json.dumps(line) + "\n")
    r = ingest.read(log)
    assert r["broken"] and len(r["events"]) == 1


def test_gen_writes_data_only_the_owner_can_read(tmp_path):
    pytest.importorskip("yaml")
    from status_testlib import fixture_argv

    gen = load("gen")
    assert gen.main(fixture_argv(tmp_path / "state")) == 0
    out = tmp_path / "state" / "data"
    assert (out.stat().st_mode & 0o077) == 0
    assert all((p.stat().st_mode & 0o077) == 0 for p in out.iterdir())
