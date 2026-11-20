"""Acceptance tests for the event dispatcher (U18). Model use is scripted; the fake runtime records every start."""
import json
import re
import secrets
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

import dispatcher as dp  # noqa: E402
import interpreter as it  # noqa: E402
import org_runtime as ort  # noqa: E402
from interpreter import ScriptedHost, StepOutcome  # noqa: E402

KEY = b"k" * 32
RUN_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
CATALOG = {"m1": {"scope": "node", "unit": "count", "better": "lower", "formula": "f",
                  "collector": "collectors/m1.py", "reads": ["run-ledger"]}}
ORG = {"by": "code", "role": "worker", "metrics": ["m1"], "acceptance": [{"check": "c"}]}


def leaf():
    return {"run": {"shell": {"command": "work", "arguments": []}}, "metadata": {"org": dict(ORG)}}


def emit(etype, **data):
    return {"emit": {"event": {"with": {"type": etype, "data": data}}}, "metadata": {"org": dict(ORG)}}


def doc(name, on, *tasks):
    d = {"document": {"dsl": "1.1.0", "namespace": "org", "name": name, "version": "0.1.0"},
         "do": [{n: t} for n, t in tasks]}
    if on is not None:
        d["schedule"] = {"on": on}
    return d


def one(etype):
    return {"one": {"with": {"type": etype}}}


def write_root(tmp, docs, name="org"):
    """docs: {workflow name: workflow document}. Returns the org root."""
    root = tmp / name
    for d in ("workflows", "collectors", "checks", "briefs", "criteria", "bin"):
        (root / d).mkdir(parents=True, exist_ok=True)
    man = {"owner": "teebor", "namespace": "org", "vetoes": ["v"], "checks": {"c": "shape"},
           "roles": {"worker": {"escalates-to": "owner"}, "improver": {"escalates-to": "owner"}},
           "workflows": {n: {"path": f"workflows/{n}.json", "floors": []} for n in docs}}
    (root / "manifest.json").write_text(json.dumps(man))
    (root / "metrics.json").write_text(json.dumps(CATALOG))
    (root / "checks" / "c.py").write_text("import sys\nsys.exit(0)\n")
    (root / "collectors" / "m1.py").write_text("print(1)\n")
    (root / "bin" / "work").write_text("#!/bin/sh\nexit 0\n")
    for n, d in docs.items():
        (root / "workflows" / f"{n}.json").write_text(json.dumps(d))
    return root


class FakeRuntime:
    """Stands in for OrgRuntime: records each run and answers with the emits the test scripted."""

    def __init__(self, log, emits):
        self.log, self.emits = log, emits

    def run(self, name, input=None, run_id=None, feed=None):
        rid = secrets.token_hex(16)
        self.log.append((name, input, rid))
        events = [{"seq": i + 1, "kind": "emit", "key": f"e{i}", "event": dict(e, data=dict(e.get("data", {}), run=rid))}
                  for i, e in enumerate(self.emits.get(name, []))]
        return it.RunResult(status="success", run_id=rid, events=events)


def fake(tmp, root, emits=None, **kw):
    log = []
    d = dp.Dispatcher(root, tmp / "state.json", tmp / "ledgers",
                      lambda ledger_path: FakeRuntime(log, emits or {}), **kw)
    return d, log


def real(tmp, root, host, **kw):
    def make(ledger_path):
        return ort.OrgRuntime(root, ledger_path=ledger_path, ledger_key=KEY, ring=ort.KeyRing({}),
                              host=host, snapshots=ort.UNENFORCED, frozen=ort.NO_OUTSIDE,
                              collector=lambda *a, **k: 0)
    return dp.Dispatcher(root, tmp / "state.json", tmp / "ledgers", make, **kw)


def started(records):
    return [r["workflow"] for r in records if r["outcome"] == "started"]


def header(tmp, record):
    path = tmp / "ledgers" / record["ledger"]
    return ort.RunLedger(path, KEY).read()[0]["body"]


def event(etype="org.work-item-ready", id="ev-1", **data):
    return {"id": id, "type": etype, "data": data}


# ---------------------------------------------------------------- 1. the three start paths


def pipeline_root(tmp):
    catch = {"try": [{"verify": leaf()}],
             "catch": {"do": [{"report": emit("org.bug-reported", subject="deploy failed")}]}}
    return write_root(tmp, {
        "improvement-scan": doc("improvement-scan", one("org.scan-requested"), ("scan", leaf()),
                                ("file", emit("org.work-item-ready", subject="x"))),
        "sw-development": doc("sw-development", one("org.work-item-ready"), ("build", leaf())),
        "bug": doc("bug", one("org.bug-reported"), ("fix", leaf())),
        "deploy-verify": doc("deploy-verify", one("org.deploy-requested"), ("guard", catch)),
    })


def test_work_item_ready_starts_sw_development_with_the_event_as_input(tmp_path):
    d = real(tmp_path, pipeline_root(tmp_path), ScriptedHost())
    recs = d.deliver(event())
    assert started(recs) == ["sw-development"]
    rec = recs[0]
    assert RUN_ID.fullmatch(rec["run_id"]) and rec["status"] == "success", rec["errors"]
    h = header(tmp_path, rec)
    assert h["workflow"] == "sw-development" and h["run_id"] == rec["run_id"]
    assert h["input"] == {"event": event()}


def test_an_emitted_event_starts_the_next_workflow_one_hop_deeper(tmp_path):
    d = real(tmp_path, pipeline_root(tmp_path), ScriptedHost())
    recs = d.deliver(event("org.scan-requested", id="scan-1"))
    assert started(recs) == ["improvement-scan", "sw-development"]
    sw = recs[1]
    assert sw["depth"] == 1
    got = header(tmp_path, sw)["input"]["event"]
    assert got["type"] == "org.work-item-ready" and got["data"]["chain"] == 1
    assert got["data"]["run"] == recs[0]["run_id"] and got["id"]  # the runtime names an id for an emit without one


def test_a_failed_deploy_verification_emits_bug_reported_and_starts_bug(tmp_path):
    host = ScriptedHost(steps={"guard/verify": StepOutcome(exit_code=1, error="boom")})
    d = real(tmp_path, pipeline_root(tmp_path), host)
    recs = d.deliver(event("org.deploy-requested", id="dep-1"))
    assert started(recs) == ["deploy-verify", "bug"]
    assert header(tmp_path, recs[1])["input"]["event"]["type"] == "org.bug-reported"


# ---------------------------------------------------------------- 2. [A] once per (event id, workflow)


def test_the_same_event_id_twice_starts_one_run(tmp_path):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    first = d.deliver(event())
    second = d.deliver(event())
    assert started(first) == ["sw-development"]
    assert started(second) == [] and second[0]["outcome"] == "duplicate"
    assert len(log) == 1


def test_a_restart_on_the_same_state_file_still_starts_one(tmp_path):
    root = pipeline_root(tmp_path)
    d1, log1 = fake(tmp_path, root)
    d1.deliver(event())
    d2, log2 = fake(tmp_path, root)
    again = d2.deliver(event())
    assert log1 and not log2 and again[0]["outcome"] == "duplicate"


def test_a_pair_is_recorded_before_the_run_so_a_crash_cannot_start_it_twice(tmp_path):
    root = pipeline_root(tmp_path)

    class Crash(FakeRuntime):
        def run(self, *a, **k):
            raise KeyboardInterrupt

    d = dp.Dispatcher(root, tmp_path / "state.json", tmp_path / "ledgers", lambda p: Crash([], {}))
    with pytest.raises(KeyboardInterrupt):
        d.deliver(event())
    d2, log = fake(tmp_path, root)
    assert d2.deliver(event())[0]["outcome"] == "duplicate" and not log


def test_two_events_with_different_ids_start_two_runs(tmp_path):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    d.deliver(event(id="a"))
    d.deliver(event(id="b"))
    assert len(log) == 2


def test_an_event_without_a_string_id_is_refused_and_starts_nothing(tmp_path):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    for bad in ({"type": "org.work-item-ready", "data": {}}, {"id": "", "type": "org.work-item-ready"},
                {"id": 5, "type": "org.work-item-ready"}):
        recs = d.deliver(bad)
        assert recs[0]["outcome"] == "refused" and "id" in recs[0]["reason"]
    assert not log


# ---------------------------------------------------------------- 3. [A] chain bounds


def chain_root(tmp, n):
    return write_root(tmp, {f"w{i}": doc(f"w{i}", one(f"org.hop-{i}"), ("a", leaf())) for i in range(n)})


def test_a_chain_of_nine_hops_is_refused_at_the_ninth_and_recorded(tmp_path):
    root = chain_root(tmp_path, 12)
    emits = {f"w{i}": [{"type": f"org.hop-{i + 1}"}] for i in range(12)}
    d, log = fake(tmp_path, root, emits)
    recs = d.deliver({"id": "root", "type": "org.hop-0", "data": {}})
    assert [n for n, *_ in log] == [f"w{i}" for i in range(9)]  # depths 0..8 start
    refused = [r for r in recs if r["outcome"] == "refused"]
    assert len(refused) == 1 and refused[0]["depth"] == 9 and "depth" in refused[0]["reason"]
    assert d.state()["refusals"][-1]["reason"] == refused[0]["reason"]


def test_an_emitted_event_cannot_reset_its_own_chain_counter(tmp_path):
    root = chain_root(tmp_path, 12)
    emits = {f"w{i}": [{"type": f"org.hop-{i + 1}", "data": {"chain": 0}}] for i in range(12)}
    d, log = fake(tmp_path, root, emits)
    d.deliver({"id": "root", "type": "org.hop-0", "data": {}})
    assert len(log) == 9
    assert [i["event"]["data"].get("chain", 0) for _, i, _ in log] == list(range(9))


@pytest.mark.parametrize("chain", [-1, "3", 1.5, True, None, [1]])
def test_a_host_event_with_a_malformed_chain_is_refused(tmp_path, chain):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    recs = d.deliver(event(chain=chain))
    assert recs[0]["outcome"] == "refused" and "chain" in recs[0]["reason"] and not log


def test_a_host_event_already_beyond_the_depth_limit_is_refused(tmp_path):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    assert started(d.deliver(event(id="ok", chain=8))) == ["sw-development"]
    over = d.deliver(event(id="over", chain=9))
    assert over[0]["outcome"] == "refused" and len(log) == 1


def test_the_101st_start_for_one_event_is_refused_and_recorded(tmp_path):
    root = write_root(tmp_path, {f"w{i:03}": doc(f"w{i:03}", one("org.fanout"), ("a", leaf())) for i in range(101)})
    d, log = fake(tmp_path, root)
    recs = d.deliver({"id": "big", "type": "org.fanout", "data": {}})
    assert len(log) == 100
    refused = [r for r in recs if r["outcome"] == "refused"]
    assert len(refused) == 1 and "100" in refused[0]["reason"]
    assert refused[0]["workflow"] == "w100"  # the sorted-last one; refusal is recorded, not raised


def test_the_start_budget_survives_a_restart_and_covers_the_whole_chain(tmp_path):
    root = write_root(tmp_path, {f"w{i:03}": doc(f"w{i:03}", one("org.fanout"), ("a", leaf())) for i in range(101)})
    d1, log1 = fake(tmp_path, root)
    d1.deliver({"id": "big", "type": "org.fanout", "data": {}})
    d2, log2 = fake(tmp_path, root)
    again = d2.deliver({"id": "big", "type": "org.fanout", "data": {}})
    assert not log2 and {r["outcome"] for r in again} <= {"duplicate", "refused"}


def test_a_chain_started_by_one_event_shares_one_budget(tmp_path):
    root = write_root(tmp_path, {
        "root": doc("root", one("org.go"), ("a", leaf())),
        **{f"l{i:03}": doc(f"l{i:03}", one("org.leaf"), ("a", leaf())) for i in range(60)}})
    emits = {"root": [{"type": "org.leaf", "id": "m1"}, {"type": "org.leaf", "id": "m2"}]}
    d, log = fake(tmp_path, root, emits)
    recs = d.deliver({"id": "orig", "type": "org.go", "data": {}})
    assert len(log) == 100  # 1 root + 99 of the 120 leaf starts
    assert sum(r["outcome"] == "refused" for r in recs) == 21


# ---------------------------------------------------------------- 4. [A] reserved prefixes never start a run


@pytest.mark.parametrize("etype", ["org.owner-decided", "org.task-ended"])
def test_reserved_prefix_events_start_nothing_even_when_a_workflow_listens(tmp_path, etype):
    root = write_root(tmp_path, {"w": doc("w", one(etype), ("a", leaf()))})  # the static validator would refuse this
    d, log = fake(tmp_path, root)
    recs = d.deliver({"id": "x", "type": etype, "data": {"run": "r", "task": "t"}})
    assert not log and recs[0]["outcome"] == "refused" and "reserved" in recs[0]["reason"]


def test_a_reserved_event_in_a_finished_runs_emits_starts_nothing(tmp_path):
    root = write_root(tmp_path, {"a": doc("a", one("org.go"), ("x", leaf())),
                                 "b": doc("b", one("org.task-ended"), ("x", leaf()))})
    d, log = fake(tmp_path, root, {"a": [{"type": "org.task-ended", "id": "m"}]})
    recs = d.deliver({"id": "r", "type": "org.go", "data": {}})
    assert [n for n, *_ in log] == ["a"] and recs[-1]["outcome"] == "refused"


# ---------------------------------------------------------------- 5. non-starts with a reason


def reasons(recs):
    return " | ".join(str(r.get("reason")) for r in recs)


def test_an_unknown_event_type_starts_nothing_with_a_reason(tmp_path):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    recs = d.deliver(event("org.never-heard-of-it"))
    assert not log and recs[0]["outcome"] == "skipped" and "no workflow" in recs[0]["reason"]


@pytest.mark.parametrize("etype", [None, 5, ["org.work-item-ready"], {"a": 1}, "${ 1 }"])
def test_an_event_whose_type_is_not_a_literal_string_starts_nothing(tmp_path, etype):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    recs = d.deliver({"id": "x", "type": etype, "data": {}})
    assert not log and recs[0]["outcome"] == "refused" and "type" in recs[0]["reason"]


def test_a_workflow_with_a_non_literal_schedule_type_is_not_started_and_says_why(tmp_path):
    root = write_root(tmp_path, {"w": doc("w", one("${ .x }"), ("a", leaf()))})
    d, log = fake(tmp_path, root)
    recs = d.deliver(event("${ .x }", id="e"))
    assert not log and "literal" in reasons(recs)
    recs = d.deliver(event("org.work-item-ready", id="e2"))
    assert not log and "literal" in reasons(recs)


@pytest.mark.parametrize("on", [
    {"any": [{"with": {"type": "org.work-item-ready"}}]},
    {"all": [{"with": {"type": "org.work-item-ready"}}]},
    {"one": {"with": {"type": "org.work-item-ready"}}, "any": [{"with": {"type": "org.work-item-ready"}}]},
    {"one": {"with": {"type": "org.work-item-ready", "source": "x"}}},
    {"one": {"with": {}}}, {"one": "org.work-item-ready"}, "org.work-item-ready", [], {}])
def test_schedule_on_forms_other_than_one_with_a_literal_type_are_not_started(tmp_path, on):
    root = write_root(tmp_path, {"w": doc("w", on, ("a", leaf()))})
    d, log = fake(tmp_path, root)
    d.deliver(event())
    assert not log


def test_a_workflow_without_a_schedule_is_never_started_by_an_event(tmp_path):
    root = write_root(tmp_path, {"w": doc("w", None, ("a", leaf()))})
    d, log = fake(tmp_path, root)
    assert d.deliver(event())[0]["outcome"] == "skipped" and not log


def test_a_missing_manifest_starts_nothing_with_a_reason(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    d, log = fake(tmp_path, root)
    recs = d.deliver(event())
    assert not log and recs[0]["outcome"] == "refused" and "manifest" in recs[0]["reason"]


def test_a_manifest_entry_whose_file_is_missing_or_outside_the_root_is_skipped_with_a_reason(tmp_path):
    root = pipeline_root(tmp_path)
    (root / "workflows" / "sw-development.json").unlink()
    man = json.loads((root / "manifest.json").read_text())
    man["workflows"]["escape"] = {"path": "../outside.json", "floors": []}
    (root / "manifest.json").write_text(json.dumps(man))
    (tmp_path / "outside.json").write_text(json.dumps(doc("escape", one("org.work-item-ready"), ("a", leaf()))))
    d, log = fake(tmp_path, root)
    recs = d.deliver(event())
    assert not log
    text = reasons(recs)
    assert "sw-development" in text or "cannot" in text.lower()
    assert "escape" in text


def test_a_workflow_that_calls_for_a_workflow_not_in_the_manifest_is_still_judged_by_the_runtime(tmp_path):
    # the dispatcher routes; the runtime refuses. A refused run is recorded, not raised.
    root = write_root(tmp_path, {"w": doc("w", one("org.work-item-ready"), ("a", {"run": {"shell": {"command": "nope"}}}))})
    d = real(tmp_path, root, ScriptedHost())
    recs = d.deliver(event())
    assert recs[0]["outcome"] == "started" and recs[0]["status"] == "refused" and recs[0]["errors"]


# ---------------------------------------------------------------- state file and run ids


def test_a_corrupt_state_file_fails_closed(tmp_path):
    root = pipeline_root(tmp_path)
    (tmp_path / "state.json").write_text("{not json")
    d, log = fake(tmp_path, root)
    with pytest.raises(dp.DispatcherError):
        d.deliver(event())
    assert not log


def test_runtime_errors_while_starting_are_recorded_not_raised(tmp_path):
    root = pipeline_root(tmp_path)

    class Broken(FakeRuntime):
        def run(self, *a, **k):
            raise ort.LedgerError("the ledger already holds a run")

    d = dp.Dispatcher(root, tmp_path / "state.json", tmp_path / "ledgers", lambda p: Broken([], {}))
    recs = d.deliver(event())
    assert recs[0]["outcome"] == "refused" and "ledger" in recs[0]["reason"]


def test_each_run_gets_its_own_ledger_and_the_runtime_names_the_run_id(tmp_path):
    d = real(tmp_path, pipeline_root(tmp_path), ScriptedHost())
    a = d.deliver(event(id="a"))[0]
    b = d.deliver(event(id="b"))[0]
    assert a["ledger"] != b["ledger"] and a["run_id"] != b["run_id"]
    assert RUN_ID.fullmatch(a["run_id"]) and RUN_ID.fullmatch(b["run_id"])


def test_the_dispatcher_does_not_choose_the_run_id(tmp_path):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    d.deliver(event())
    assert log and all(len(x) == 3 for x in log)  # FakeRuntime.run takes no run_id from the dispatcher


# ---------------------------------------------------------------- state methods the command line calls


def test_set_outside_check_records_the_flag_without_touching_the_rest(tmp_path):
    d, _ = fake(tmp_path, pipeline_root(tmp_path))
    d.deliver(event("org.work-item-ready"))
    before = d.state()
    d.set_outside_check(False)
    assert d.state()["outside_check"] == "disabled"
    d.set_outside_check(True)
    after = d.state()
    assert after.pop("outside_check") == "enabled"
    assert after == before


def test_set_outside_check_on_a_new_state_file_keeps_the_shape(tmp_path):
    d, _ = fake(tmp_path, pipeline_root(tmp_path))
    d.set_outside_check(True)
    assert d.state() == {"pairs": {}, "starts": {}, "refusals": [], "outside_check": "enabled"}


def test_finish_pair_marks_a_starting_pair_done_and_keeps_the_error_reason(tmp_path):
    d, _ = fake(tmp_path, pipeline_root(tmp_path))
    d.deliver(event("org.work-item-ready"))
    (key,) = d.state()["pairs"]
    st = d.state()
    st["pairs"][key]["state"] = "starting"
    d._write(st)
    res = it.RunResult(status="error", run_id="r-1", errors=["boom", "bang"])
    assert d.finish_pair(key, res) == []
    pair = d.state()["pairs"][key]
    assert (pair["state"], pair["run_id"], pair["status"], pair["reason"]) == ("done", "r-1", "error", "boom; bang")


def test_record_reason_sets_it_on_one_pair_and_ignores_an_unknown_pair(tmp_path):
    d, _ = fake(tmp_path, pipeline_root(tmp_path))
    d.deliver(event("org.work-item-ready"))
    (key,) = d.state()["pairs"]
    d.record_reason(key, "why")
    d.record_reason("nope\nnothing", "ignored")
    st = d.state()
    assert st["pairs"][key]["reason"] == "why" and list(st["pairs"]) == [key]


# ---------------------------------------------------------------- a run resumed after a crash dispatches its emits


def emit_result(run_id, *types):
    events = [{"seq": i + 1, "kind": "emit", "key": f"e{i}", "event": {"type": t, "data": {"run": run_id}}}
              for i, t in enumerate(types)]
    return it.RunResult(status="success", run_id=run_id, events=events)


def leave_starting(d, key):
    st = d.state()
    st["pairs"][key].update(state="starting")
    st["pairs"][key].pop("run_id", None)
    d._write(st)


def test_finish_pair_dispatches_the_emits_one_hop_deeper_than_the_pair(tmp_path):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    d.deliver(event("org.scan-requested", id="scan-1", chain=3))
    (key,) = d.state()["pairs"]
    assert d.state()["pairs"][key]["depth"] == 3
    leave_starting(d, key)
    del log[:]
    recs = d.finish_pair(key, emit_result("run-9", "org.work-item-ready"))
    assert started(recs) == ["sw-development"] and recs[0]["depth"] == 4
    assert log[0][1]["event"]["data"]["chain"] == 4 and log[0][1]["event"]["id"] == "run-9:1"
    st = d.state()
    assert st["pairs"][key]["state"] == "done" and st["starts"]["scan-1"] == 2


def test_finish_pair_twice_starts_the_downstream_workflow_once(tmp_path):
    d, log = fake(tmp_path, pipeline_root(tmp_path))
    d.deliver(event("org.scan-requested", id="scan-1"))
    (key,) = d.state()["pairs"]
    leave_starting(d, key)
    res = emit_result("run-9", "org.work-item-ready")
    assert started(d.finish_pair(key, res)) == ["sw-development"]
    again = d.finish_pair(key, res)
    assert started(again) == [] and [r["outcome"] for r in again] == ["duplicate"]
    assert [n for n, _, _ in log].count("sw-development") == 1


def test_finish_pair_past_the_bound_refuses_the_emit(tmp_path):
    d, log = fake(tmp_path, pipeline_root(tmp_path), max_depth=2)
    d.deliver(event("org.scan-requested", id="scan-1", chain=2))
    (key,) = d.state()["pairs"]
    leave_starting(d, key)
    recs = d.finish_pair(key, emit_result("run-9", "org.work-item-ready"))
    assert [(r["outcome"], r["reason"]) for r in recs] == [("refused", "chain depth 3 exceeds 2")]
    assert [n for n, _, _ in log] == ["improvement-scan"]
    assert d.state()["refusals"][-1]["reason"] == "chain depth 3 exceeds 2"
