"""Metric collectors: the registry seam keyed by the catalog's `reads` sources, and each built-in collector.

Collectors are pure functions of ledger and session-record bytes. These tests build the bytes by hand; the
runtime side (org.metric entries, the turn seam) is in test_org_runtime.py.
"""
import ast
import json
import math
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
W = HERE.parent
sys.path.insert(0, str(W / "scripts"))

import metric_collectors as mc  # noqa: E402
import validate_catalog as vc  # noqa: E402


def _catalog():
    out = {}
    for name in sorted(p.name for p in W.glob("metrics*.json")):
        out.update(json.loads((W / name).read_text()))
    return out


SHIPPED = _catalog()


# ---------------------------------------------------------------- ledger and record bytes


def ledger(*items):
    lines = []
    for n, (kind, body) in enumerate(items, 1):
        lines.append(json.dumps({"seq": n, "prev": f"m{n - 1}", "kind": kind, "body": body, "mac": f"m{n}"}))
    return ("\n".join(lines) + "\n").encode()


def log(kind, t=0.0, **kw):
    return ("log", {"kind": kind, "t": t, **kw})


def accept(key, status, t=0.0):
    return log("accept", t, key=key, ok=status == "pass", status=status)


def node_row(key, metric):
    return ("metric", {"key": key, "metric": metric, "value": 0})


def step(key, cost=None, output=None):
    out = output if output is not None else ({"cost": cost, "event": {}, "evidence": {}} if cost else None)
    return ("host", {"call": "step", "key": key, "result": {"exit_code": 0, "output": out, "stdout": None,
                                                            "duration": 1.0, "error": None, "timed_out": False,
                                                            "truncated": False}})


def rec(kind, seq, **fields):
    base = {"schema_version": "1", "harness": "claude-code", "session_id": "s", "seq": seq, "uuid": f"u{seq}",
            "parent_uuid": None, "timestamp": None, "kind": kind, "block_index": 0, "is_sidechain": False,
            "is_meta": False}
    return {**base, **fields}


def record(*records):
    return "".join(json.dumps(r) + "\n" for r in records).encode()


def compute(metric, *items, key=None, session=None, registry=None):
    inputs = {"run-ledger": ledger(*items)}
    if session is not None:
        inputs["session-record"] = session
    return (registry or mc.default_registry()).compute(metric, SHIPPED[metric], inputs, key)


# ---------------------------------------------------------------- catalog-derived collectors (run-ledger)


def test_escalations_counts_every_escalation_in_the_run_and_per_node():
    items = (log("run-start"), log("escalation", key="a", to="lead"), log("escalation", key="b", to="owner"),
             log("escalation", key="a", to="lead"), log("run-end", status="error"))
    assert compute("escalations", *items) == {"value": 3}
    assert compute("escalations", *items, key="a") == {"value": 2}
    assert compute("escalations", *items, key="zzz") == {"value": 0}


def test_green_rounds_counts_failed_green_evidence_per_unit_and_summed_over_the_run():
    g = "build/units/tdd#0>cycle/green-evidence"
    items = (accept(g, "fail"), accept(g, "fail"), accept(g, "pass"),
             accept("build/units/tdd#1>cycle/green-evidence", "fail"), accept("cycle/red-evidence", "fail"))
    assert compute("green-rounds", *items) == {"value": 3}
    assert compute("green-rounds", *items, key=g) == {"value": 2}


def test_acceptance_rounds_counts_rounds_until_the_first_pass_of_the_node():
    k = "spec-cycle/design-cycle/build-cycle/layer-run"
    items = (accept(k, "fail"), node_row(k, "acceptance-rounds"), accept(k, "fail"), node_row(k, "acceptance-rounds"),
             accept(k, "pass"), node_row(k, "acceptance-rounds"), accept(k, "pass"),
             accept("acceptance-run", "pass"), node_row("acceptance-run", "acceptance-rounds"))
    assert compute("acceptance-rounds", *items, key=k) == {"value": 3}
    assert compute("acceptance-rounds", *items, key="acceptance-run") == {"value": 1}
    assert compute("acceptance-rounds", *items) == {"value": 3}  # the run: the most rounds any node took


def test_acceptance_rounds_of_a_node_that_never_passed_is_every_round_it_ran():
    k = "layer-run"
    assert compute("acceptance-rounds", accept(k, "fail"), accept(k, "fail"), key=k) == {"value": 2}


def test_a_rounds_metric_no_node_of_the_run_carries_has_a_reason_not_a_zero():
    out = compute("acceptance-rounds", log("run-start"), accept("a", "pass"))
    assert set(out) == {"reason"} and "acceptance-rounds" in out["reason"]


def test_claim_review_rounds_counts_rounds_until_the_review_passed():
    k = "review-loop/claim-review"
    items = (accept(k, "fail"), node_row(k, "claim-review-rounds"), accept(k, "pass"),
             node_row(k, "claim-review-rounds"))
    assert compute("claim-review-rounds", *items, key=k) == {"value": 2}
    assert compute("claim-review-rounds", *items) == {"value": 2}


def test_lead_time_is_hours_from_run_start_to_the_first_pass_of_the_node():
    items = (log("run-start", 0.0), accept("merge", "fail", 3600.0), node_row("merge", "lead-time"),
             accept("merge", "pass", 7200.0), node_row("merge", "lead-time"),
             accept("deploy", "pass", 10800.0), node_row("deploy", "lead-time"))
    assert compute("lead-time", *items, key="merge") == {"value": 2.0}
    assert compute("lead-time", *items, key="deploy") == {"value": 3.0}
    assert compute("lead-time", *items) == {"value": 2.0}  # the earliest node that passed: the merge


def test_lead_time_with_no_passing_node_has_a_reason():
    out = compute("lead-time", log("run-start"), accept("merge", "fail", 60.0), node_row("merge", "lead-time"))
    assert set(out) == {"reason"}
    assert set(compute("lead-time", log("run-start"), accept("merge", "fail", 60.0), key="merge")) == {"reason"}


def test_question_turnaround_is_hours_to_the_published_note():
    items = (log("run-start", 0.0), accept("publish", "pass", 1800.0), node_row("publish", "question-turnaround"))
    assert compute("question-turnaround", *items) == {"value": 0.5}


def test_decision_latency_is_hours_from_gate_start_to_the_signed_decision():
    items = (log("task-start", 100.0, key="merge-gate", path="merge-gate"),
             ("decision-id", {"id": "e1", "key": "merge-gate"}), accept("merge-gate", "pass", 1900.0),
             log("task-start", 0.0, key="g2", path="g2"), ("decision-id", {"id": "e2", "key": "g2"}),
             accept("g2", "pass", 3600.0))
    assert compute("decision-latency", *items, key="merge-gate") == {"value": 0.5}
    assert compute("decision-latency", *items) == {"value": 0.75}  # mean over decided gates


def test_decision_latency_with_no_signed_decision_has_a_reason():
    out = compute("decision-latency", log("task-start", 0.0, key="g", path="g"), accept("g", "fail", 5.0))
    assert set(out) == {"reason"}


# ---------------------------------------------------------------- runtime catalog (metrics.runtime.json)


def test_run_duration_is_virtual_seconds_from_run_start_to_run_end():
    assert compute("run-duration", log("run-start", 5.0), accept("a", "pass", 10.0), log("run-end", 65.0)) == {
        "value": 60.0}
    assert compute("run-duration", log("run-start", 5.0), accept("a", "pass", 10.0)) == {"value": 5.0}


def test_model_calls_cost_and_tokens_come_from_journaled_agent_run_costs():
    items = (step("a", {"usd": 0.01, "seconds": 1.0, "input_tokens": 4, "output_tokens": 700}),
             step("b", {"usd": 0.02, "seconds": 2.0, "input_tokens": 2, "output_tokens": 300}),
             step("c"), step("d", output="plain text"))
    assert compute("model-calls", *items) == {"value": 2}
    assert compute("model-cost", *items)["value"] == pytest.approx(0.03)
    assert compute("model-tokens", *items) == {"value": 1006}


def test_model_tokens_without_any_token_count_has_a_reason():
    out = compute("model-tokens", step("a", {"usd": 0.01, "seconds": 1.0}))
    assert set(out) == {"reason"}
    assert compute("model-calls", step("c")) == {"value": 0}


def test_task_reruns_counts_every_start_after_the_first_per_key():
    items = (log("task-start", key="a", path="a"), log("task-start", key="b", path="b"),
             log("task-start", key="a", path="a"), log("task-start", key="a", path="a"))
    assert compute("task-reruns", *items) == {"value": 2}


def test_skipped_tasks_counts_task_skips():
    assert compute("skipped-tasks", log("task-skip", key="x"), log("task-skip", key="y"), log("task-start", key="z",
                                                                                              path="z")) == {"value": 2}


def test_check_and_judge_failures_count_failed_acceptance_items():
    items = (log("item", key="a", index=0, item="check", result="fail"),
             log("item", key="a", index=1, item="check", result="pass"),
             log("item", key="b", index=0, item="rubric", result="fail"),
             log("item", key="b", index=1, item="rubric", result="pending"),
             log("item", key="c", index=0, item="human", result="fail"))
    assert compute("check-failures", *items) == {"value": 1}
    assert compute("judge-failures", *items) == {"value": 1}


def test_gate_wait_sums_listen_and_decision_gate_durations_only():
    items = (log("task-start", 10.0, key="join", path="join"), log("until", 20.0, key="join", events=1, result=True,
                                                                    tasks=[]),
             accept("join", "pass", 70.0),
             log("task-start", 100.0, key="merge-gate", path="merge-gate"),
             ("decision-id", {"id": "e", "key": "merge-gate"}), accept("merge-gate", "pass", 160.0),
             log("task-start", 0.0, key="a", path="a"), accept("a", "pass", 50.0))
    assert compute("gate-wait", *items) == {"value": 120.0}


# ---------------------------------------------------------------- session record (U11)


SESSION = record(rec("user", 0, text="go"), rec("tool_call", 1, tool_use_id="t1", name="Read", input={}),
                 rec("tool_result", 2, tool_use_id="t1", content="x", is_error=True),
                 rec("tool_call", 3, tool_use_id="t2", name="Edit", input={}),
                 rec("tool_result", 4, tool_use_id="t2", content="ok", is_error=False),
                 rec("compaction", 5, text="summary"), rec("assistant_text", 6, text="done", model="m"))


def test_session_collectors_count_tool_calls_errors_and_compactions():
    assert compute("session-tool-calls", log("run-start"), session=SESSION) == {"value": 2}
    assert compute("session-tool-errors", log("run-start"), session=SESSION) == {"value": 1}
    assert compute("session-compactions", log("run-start"), session=SESSION) == {"value": 1}


def test_a_session_metric_without_a_session_record_input_has_a_reason():
    assert compute("session-tool-calls", log("run-start")) == {"reason": "no input for session-record"}


def test_a_malformed_session_record_is_an_error_never_a_zero():
    bad = record({"kind": "tool_call", "seq": 0})
    out = compute("session-tool-calls", log("run-start"), session=bad)
    assert set(out) == {"error"} and "tool_call" in out["error"]


# ---------------------------------------------------------------- the registry seam


class Fake:
    def __init__(self, source, metrics, parse=None):
        self.source, self.metrics = source, metrics
        self._parse = parse

    def parse(self, data):
        return self._parse(data) if self._parse else data


ENTRY = {"scope": "node", "unit": "count", "better": "lower", "formula": "f", "collector": "collectors/x.py"}


def test_a_metric_whose_source_has_no_collector_names_the_first_missing_source():
    reg = mc.default_registry()
    out = reg.compute("spec-rework", SHIPPED["spec-rework"], {"run-ledger": ledger(log("run-start"))})
    assert out == {"reason": "no collector for tracker-edit-history"}
    out = reg.compute("write-set-collisions", SHIPPED["write-set-collisions"], {"run-ledger": ledger()})
    assert out == {"reason": "no collector for item.json"}


def test_a_metric_no_registered_collector_computes_has_a_reason():
    reg = mc.Registry([Fake("run-ledger", {})])
    out = reg.compute("m", {**ENTRY, "reads": ["run-ledger"]}, {"run-ledger": b""})
    assert out == {"reason": "no collector computes m"}


def test_an_injected_fake_collector_is_used_and_gets_every_source_it_reads():
    seen = []

    def fn(data, key):
        seen.append((sorted(data), key))
        return len(data["a"]) + len(data["b"])

    reg = mc.Registry([Fake("a", {"m": fn}), Fake("b", {})])
    assert reg.compute("m", {**ENTRY, "reads": ["a", "b"]}, {"a": b"xx", "b": b"yyy"}, "k") == {"value": 5}
    assert seen == [(["a", "b"], "k")]


def test_a_collector_error_is_recorded_and_the_other_metrics_still_compute():
    def boom(data, key):
        raise RuntimeError("boom")

    reg = mc.Registry([Fake("run-ledger", {"bad": boom, "good": lambda d, k: 7})])
    cat = {"bad": {**ENTRY, "reads": ["run-ledger"]}, "good": {**ENTRY, "reads": ["run-ledger"]}}
    out = mc.collect(cat, reg, {"run-ledger": b""})
    assert out == {"bad": {"error": "RuntimeError: boom"}, "good": {"value": 7}}


def test_a_parse_error_is_an_error_row_for_every_metric_of_that_source():
    def bad_parse(data):
        raise ValueError("not a ledger")

    reg = mc.Registry([Fake("run-ledger", {"a": lambda d, k: 1, "b": lambda d, k: 2}, parse=bad_parse)])
    cat = {n: {**ENTRY, "reads": ["run-ledger"]} for n in ("a", "b")}
    assert mc.collect(cat, reg, {"run-ledger": b""}) == {"a": {"error": "ValueError: not a ledger"},
                                                         "b": {"error": "ValueError: not a ledger"}}


@pytest.mark.parametrize("bad", ["3", True, math.nan, math.inf, None, [1]])
def test_a_collector_that_returns_no_finite_number_is_an_error(bad):
    reg = mc.Registry([Fake("run-ledger", {"m": lambda d, k: bad})])
    out = reg.compute("m", {**ENTRY, "reads": ["run-ledger"]}, {"run-ledger": b""})
    assert set(out) == {"error"} and "finite number" in out["error"]


def test_a_collector_may_say_why_it_has_no_value():
    def fn(data, key):
        raise mc.NoValue("nothing merged yet")

    reg = mc.Registry([Fake("run-ledger", {"m": fn})])
    assert reg.compute("m", {**ENTRY, "reads": ["run-ledger"]}, {"run-ledger": b""}) == {
        "reason": "nothing merged yet"}


def test_two_collectors_for_one_source_are_refused():
    with pytest.raises(ValueError, match="run-ledger"):
        mc.Registry([Fake("run-ledger", {}), Fake("run-ledger", {})])


def test_the_default_registry_serves_run_ledger_and_session_record():
    assert sorted(mc.default_registry().sources()) == ["run-ledger", "session-record"]


# ---------------------------------------------------------------- the shipped catalogs


COMPUTED = {"escalations", "acceptance-rounds", "lead-time", "decision-latency", "green-rounds",
            "claim-review-rounds", "question-turnaround", "run-duration", "model-calls", "model-cost",
            "model-tokens", "task-reruns", "skipped-tasks", "check-failures", "judge-failures", "gate-wait",
            "session-tool-calls", "session-tool-errors", "session-compactions"}

RICH = (log("run-start", 0.0), log("task-start", 1.0, key="g", path="g"), ("decision-id", {"id": "e", "key": "g"}),
        accept("g", "pass", 3600.0), node_row("g", "decision-latency"),
        accept("layer-run", "pass", 3600.0), node_row("layer-run", "acceptance-rounds"),
        accept("claim-review", "pass", 3600.0), node_row("claim-review", "claim-review-rounds"),
        accept("merge", "pass", 7200.0), node_row("merge", "lead-time"),
        accept("publish", "pass", 7200.0), node_row("publish", "question-turnaround"),
        accept("cycle/green-evidence", "fail", 7200.0), log("escalation", 7200.0, key="x", to="lead"),
        step("s", {"usd": 0.5, "seconds": 3.0, "input_tokens": 1, "output_tokens": 2}),
        log("run-end", 7300.0, status="success"))


def test_every_shipped_metric_gets_a_value_or_an_explicit_reason():
    out = mc.collect(SHIPPED, mc.default_registry(), {"run-ledger": ledger(*RICH), "session-record": SESSION})
    assert sorted(out) == sorted(SHIPPED)
    assert {m for m, r in out.items() if "value" in r} == COMPUTED
    for m, r in out.items():
        assert len(r) == 1, (m, r)
        if m not in COMPUTED:
            assert r["reason"].startswith("no collector for "), (m, r)
            assert r["reason"][len("no collector for "):] in SHIPPED[m]["reads"]


def test_the_runtime_catalog_validates_and_names_existing_collector_files():
    doc = json.loads((W / "metrics.runtime.json").read_text())
    assert vc.validate_catalog([("metrics.runtime.json", doc)], str(W)) == []
    merged, errs = vc.merge_catalogs([(p.name, json.loads(p.read_text())) for p in sorted(W.glob("metrics*.json"))])
    assert errs == []


def test_collecting_twice_from_the_same_bytes_is_byte_identical():
    inputs = {"run-ledger": ledger(*RICH), "session-record": SESSION}
    a = json.dumps(mc.collect(SHIPPED, mc.default_registry(), inputs), sort_keys=True, separators=(",", ":"))
    b = json.dumps(mc.collect(SHIPPED, mc.default_registry(), dict(inputs)), sort_keys=True, separators=(",", ":"))
    assert a == b


def test_the_collector_module_uses_no_clock_network_environment_or_randomness():
    tree = ast.parse((W / "scripts" / "metric_collectors.py").read_text())
    banned = {"time", "datetime", "socket", "random", "secrets", "subprocess", "urllib", "http", "uuid"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & banned
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned
        elif isinstance(node, ast.Attribute):
            assert node.attr not in ("environ", "getenv", "open"), node.attr
        elif isinstance(node, ast.Name):
            assert node.id != "open"
