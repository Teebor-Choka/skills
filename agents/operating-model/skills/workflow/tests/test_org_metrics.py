"""The runtime side of metrics: `org.metric` entries at run end and at a turn, and the P61 turn seam.

The ledger stays append-only, hash-chained and MAC'd: these entries go through `RunLedger.append` like every other.
Helpers (a small org root, a fake key ring, `runtime`) come from test_org_runtime.py.
"""
import gc
import hashlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))

import metric_collectors as mc  # noqa: E402
import org_runtime as ort  # noqa: E402
from interpreter import ScriptedHost  # noqa: E402
from test_org_runtime import KEY, RID, doc, leaf, make_root, runtime, summary  # noqa: E402

ENTRY = {"scope": "node", "unit": "count", "better": "lower", "formula": "f"}
CATALOG = {"m1": {**ENTRY, "collector": "collectors/m1.py", "reads": ["run-ledger"]},
           "m2": {**ENTRY, "collector": "collectors/m2.py", "reads": ["run-ledger", "tracker"]},
           "m3": {**ENTRY, "collector": "collectors/m3.py", "reads": ["session-record"]}}
RECORD = b'{"kind": "x"}\n{"kind": "y"}\n'


class Fake:
    def __init__(self, source, metrics):
        self.source, self.metrics = source, metrics

    def parse(self, data):
        return data


def lines(d, k):
    return len(d["run-ledger"].splitlines())


def registry(m1=lines, m3=lambda d, k: d["session-record"].count(b"\n")):
    return mc.Registry([Fake("run-ledger", {"m1": m1}), Fake("session-record", {"m3": m3})])


def root_with(tmp, wf=None):
    root = make_root(tmp, wf=wf, catalog=CATALOG)
    for n in ("m2", "m3"):
        (root / "collectors" / f"{n}.py").write_text("print(0)\n")
    return root


def entries(tmp):
    return ort.RunLedger(tmp / "run.ledger", KEY).read()


def org_metrics(tmp, at=None):
    return [e for e in entries(tmp) if e["kind"] == "org.metric" and (at is None or e["body"]["at"] == at)]


def result_of(body):
    return {k: body[k] for k in ("value", "reason", "error") if k in body}


def canon(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"))


def prefix(tmp, n):
    return b"".join(l + b"\n" for l in (tmp / "run.ledger").read_bytes().split(b"\n")[:n])


def full_turn(tb, turn="t1", record=RECORD):
    tb.export(turn, record)
    tb.collect(turn, record)
    tb.reflect(turn, "improve:lesson-1")
    return tb.complete(turn)


# ---------------------------------------------------------------- org.metric at run end


def test_run_end_appends_one_org_metric_entry_per_catalog_metric_after_the_run_end_event(tmp_path):
    rt = runtime(tmp_path, root=root_with(tmp_path), registry=registry())
    assert rt.run("t", run_id=RID).status == "success"
    es = entries(tmp_path)
    om = [e for e in es if e["kind"] == "org.metric"]
    assert [e["body"]["metric"] for e in om] == ["m1", "m2", "m3"]
    assert all(e["body"]["at"] == "run-end" and "turn" not in e["body"] for e in om)
    first = om[0]["seq"]
    before = es[first - 2]
    assert before["kind"] == "log" and before["body"]["kind"] == "run-end"
    boundary = {"seq": first - 1, "mac": before["mac"]}
    assert all(e["body"]["inputs"] == {"run-ledger": boundary} for e in om)
    assert result_of(om[0]["body"]) == {"value": first - 1}  # m1 saw exactly the ledger up to the boundary
    assert result_of(om[1]["body"]) == {"reason": "no collector for tracker"}
    assert result_of(om[2]["body"]) == {"reason": "no input for session-record"}


def test_a_collector_error_is_recorded_and_never_aborts_the_run(tmp_path):
    def boom(d, k):
        raise RuntimeError("boom")

    rt = runtime(tmp_path, root=root_with(tmp_path), registry=registry(m1=boom))
    assert rt.run("t", run_id=RID).status == "success"
    assert [result_of(e["body"]) for e in org_metrics(tmp_path)] == [
        {"error": "RuntimeError: boom"}, {"reason": "no collector for tracker"},
        {"reason": "no input for session-record"}]


def test_a_failed_run_still_gets_its_run_end_metrics(tmp_path):
    rt = runtime(tmp_path, root=root_with(tmp_path), registry=registry(),
                 host=ScriptedHost(steps={"b": {"exit_code": 1, "error": "boom"}}))
    assert rt.run("t", run_id=RID).status == "error"
    assert len(org_metrics(tmp_path, "run-end")) == 3


def test_replay_never_appends_org_metric_entries(tmp_path):
    root = root_with(tmp_path)
    live = runtime(tmp_path, root=root, registry=registry()).run("t", run_id=RID)
    n = len(entries(tmp_path))
    again = runtime(tmp_path, root=root, registry=registry()).replay()
    assert summary(again) == summary(live)
    assert len(entries(tmp_path)) == n


class Killed(BaseException):
    pass


def test_a_kill_between_run_end_rows_records_each_metric_once_with_the_first_boundary(tmp_path):
    cat = {"m1": CATALOG["m1"], "m4": {**CATALOG["m1"], "collector": "collectors/m4.py"}}
    root = make_root(tmp_path, catalog=cat)
    (root / "collectors" / "m4.py").write_text("print(0)\n")

    def die(d, k):
        raise Killed()

    rt = runtime(tmp_path, root=root, registry=mc.Registry([Fake("run-ledger", {"m1": lines, "m4": die})]))
    with pytest.raises(Killed):
        rt.run("t", run_id=RID)
    del rt
    gc.collect()
    assert [e["body"]["metric"] for e in org_metrics(tmp_path)] == ["m1"]
    healthy = mc.Registry([Fake("run-ledger", {"m1": lines, "m4": lines})])
    runtime(tmp_path, root=root, registry=healthy).resume()
    om = org_metrics(tmp_path)
    assert [e["body"]["metric"] for e in om] == ["m1", "m4"]
    assert len({canon(e["body"]["inputs"]) for e in om}) == 1
    assert result_of(om[1]["body"]) == result_of(om[0]["body"])  # m4 saw the same bytes m1 saw


def test_resuming_a_finished_run_adds_no_second_set_of_run_end_rows(tmp_path):
    root = root_with(tmp_path)
    runtime(tmp_path, root=root, registry=registry()).run("t", run_id=RID)
    runtime(tmp_path, root=root, registry=registry()).resume()
    assert len(org_metrics(tmp_path, "run-end")) == 3


def test_replaying_a_ledger_recomputes_byte_identical_metric_values(tmp_path):
    root = root_with(tmp_path)
    rt = runtime(tmp_path, root=root, registry=registry())
    rt.run("t", run_id=RID)
    full_turn(rt.turn_boundary())
    om = org_metrics(tmp_path)
    assert {e["body"]["at"] for e in om} == {"run-end", "turn"}
    for e in om:
        b = e["body"]
        inputs = {"run-ledger": prefix(tmp_path, b["inputs"]["run-ledger"]["seq"])}
        if "session-record" in b["inputs"]:
            assert b["inputs"]["session-record"] == {"sha256": hashlib.sha256(RECORD).hexdigest()}
            inputs["session-record"] = RECORD
        again = registry().compute(b["metric"], CATALOG[b["metric"]], inputs)
        assert canon(again) == canon(result_of(b))


# ---------------------------------------------------------------- the ledger stays a verified chain


def test_the_ledger_verifies_with_metric_and_turn_complete_entries(tmp_path):
    root = root_with(tmp_path)
    rt = runtime(tmp_path, root=root, registry=registry())
    live = rt.run("t", run_id=RID)
    full_turn(rt.turn_boundary())
    led = ort.RunLedger(tmp_path / "run.ledger", KEY)
    es = led.read()
    led.verify_head(es)
    assert {e["kind"] for e in es} >= {"org.metric", "org.session-export", "org.reflection", "org.turn-complete"}
    assert summary(runtime(tmp_path, root=root, registry=registry()).replay()) == summary(live)


def test_tampering_with_a_metric_entry_breaks_the_chain(tmp_path):
    rt = runtime(tmp_path, root=root_with(tmp_path), registry=registry())
    rt.run("t", run_id=RID)
    full_turn(rt.turn_boundary())
    path = tmp_path / "run.ledger"
    raw = path.read_bytes().split(b"\n")
    i = next(i for i, l in enumerate(raw) if l and json.loads(l)["kind"] == "org.metric")
    e = json.loads(raw[i])
    e["body"]["value"] = 999
    raw[i] = json.dumps(e, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(b"\n".join(raw))
    with pytest.raises(ort.LedgerError, match="bad signature"):
        ort.RunLedger(path, KEY).read()
    assert rt.turn_boundary().compaction_allowed("t1") is False


def test_an_old_ledger_without_metric_entries_still_verifies_and_replays(tmp_path):
    root = root_with(tmp_path)
    live = runtime(tmp_path, root=root, registry=registry()).run("t", run_id=RID)
    old = tmp_path / "old"
    old.mkdir()
    led = ort.RunLedger(old / "run.ledger", KEY)
    for e in entries(tmp_path):
        if not e["kind"].startswith("org."):
            led.append(e["kind"], e["body"])
    es = ort.RunLedger(old / "run.ledger", KEY).read()
    ort.RunLedger(old / "run.ledger", KEY).verify_head(es)
    assert not any(e["kind"].startswith("org.") for e in es)
    rt = runtime(old, root=root, registry=registry())
    assert summary(rt.replay()) == summary(live)
    assert rt.turn_boundary().compaction_allowed("t1") is False


# ---------------------------------------------------------------- the P61 turn seam


def test_turn_complete_records_the_export_the_metrics_and_the_reflection(tmp_path):
    rt = runtime(tmp_path, root=root_with(tmp_path), registry=registry())
    rt.run("t", run_id=RID)
    tb = rt.turn_boundary()
    assert tb.compaction_allowed("t1") is False
    done = full_turn(tb)
    assert tb.compaction_allowed("t1") is True
    assert tb.compaction_allowed("t2") is False
    es = {e["seq"]: e for e in entries(tmp_path)}
    b = done["body"]
    assert done["kind"] == "org.turn-complete" and b["turn"] == "t1"
    exp, refl = es[b["export"]["seq"]], es[b["reflection"]["seq"]]
    assert exp["kind"] == "org.session-export" and exp["mac"] == b["export"]["mac"]
    assert exp["body"] == {"turn": "t1", "sha256": hashlib.sha256(RECORD).hexdigest(), "bytes": len(RECORD)}
    assert refl["kind"] == "org.reflection" and refl["body"] == {"turn": "t1", "ref": "improve:lesson-1"}
    rows = [es[r["seq"]] for r in b["metrics"]]
    assert [r["body"]["metric"] for r in rows] == ["m1", "m2", "m3"]
    assert all(r["kind"] == "org.metric" and r["body"]["at"] == "turn" and r["body"]["turn"] == "t1" for r in rows)
    assert [r["mac"] for r in rows] == [m["mac"] for m in b["metrics"]]
    assert b["export"]["seq"] < b["metrics"][0]["seq"] and b["metrics"][-1]["seq"] < b["reflection"]["seq"]
    assert result_of(rows[2]["body"]) == {"value": 2}  # m3 read the exported session record


def _refused(tmp, call):
    n = len(entries(tmp))
    with pytest.raises(ort.TurnOrderError):
        call()
    assert len(entries(tmp)) == n, "a refused call appends nothing"


def test_turn_complete_out_of_order_is_refused(tmp_path):
    rt = runtime(tmp_path, root=root_with(tmp_path), registry=registry())
    rt.run("t", run_id=RID)
    tb = rt.turn_boundary()
    _refused(tmp_path, lambda: tb.complete("t1"))  # nothing yet
    _refused(tmp_path, lambda: tb.collect("t1", RECORD))  # metrics before the export
    _refused(tmp_path, lambda: tb.reflect("t1", "r"))  # reflection before anything
    tb.export("t1", RECORD)
    _refused(tmp_path, lambda: tb.export("t1", RECORD))  # one export per turn
    _refused(tmp_path, lambda: tb.reflect("t1", "r"))  # reflection before the metrics
    _refused(tmp_path, lambda: tb.complete("t1"))  # no metrics, no reflection
    _refused(tmp_path, lambda: tb.collect("t1", RECORD + b"x"))  # not the exported record
    tb.collect("t1", RECORD)
    _refused(tmp_path, lambda: tb.collect("t1", RECORD))  # metrics once per turn
    _refused(tmp_path, lambda: tb.complete("t1"))  # no reflection
    assert tb.compaction_allowed("t1") is False
    tb.reflect("t1", "r")
    tb.complete("t1")
    _refused(tmp_path, lambda: tb.complete("t1"))  # once
    _refused(tmp_path, lambda: tb.export("t1", RECORD))  # a completed turn is closed
    assert tb.compaction_allowed("t1") is True


def test_turns_are_independent(tmp_path):
    rt = runtime(tmp_path, root=root_with(tmp_path), registry=registry())
    rt.run("t", run_id=RID)
    tb = rt.turn_boundary()
    tb.export("t1", RECORD)
    full_turn(tb, "t2")
    assert tb.compaction_allowed("t2") is True and tb.compaction_allowed("t1") is False
    _refused(tmp_path, lambda: tb.complete("t1"))


@pytest.mark.parametrize("turn", ["", None, 5, "x" * 201])
def test_a_turn_id_must_be_a_short_string(tmp_path, turn):
    rt = runtime(tmp_path, root=root_with(tmp_path), registry=registry())
    rt.run("t", run_id=RID)
    _refused(tmp_path, lambda: rt.turn_boundary().export(turn, RECORD))


def test_compaction_allowed_reads_the_ledger_not_memory(tmp_path):
    rt = runtime(tmp_path, root=root_with(tmp_path), registry=registry())
    rt.run("t", run_id=RID)
    tb = rt.turn_boundary()
    full_turn(tb)
    path = tmp_path / "run.ledger"
    raw = path.read_bytes().split(b"\n")
    raw = [l for l in raw if not (l and json.loads(l)["kind"] == "org.turn-complete")]
    path.write_bytes(b"\n".join(raw))  # cut the turn-complete line: the head file no longer matches
    assert tb.compaction_allowed("t1") is False


# ---------------------------------------------------------------- per-node rows go through the registry by default


def test_the_default_node_collector_uses_the_registry(tmp_path):
    root = root_with(tmp_path, wf=doc(("a", leaf(metrics=("m1",))), ("b", leaf(metrics=("m2",)))))
    rt = runtime(tmp_path, root=root, registry=registry(), collector=None)
    assert rt.run("t", run_id=RID).status == "success"
    rows = {e["body"]["key"]: e["body"] for e in entries(tmp_path) if e["kind"] == "metric"}
    assert isinstance(rows["a"].get("value"), int) and rows["a"]["value"] > 0
    assert rows["b"] == {"key": "b", "metric": "m2", "reason": "no collector for tracker"}
