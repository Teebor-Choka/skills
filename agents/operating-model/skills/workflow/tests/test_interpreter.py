"""Acceptance tests for the OWS interpreter (U13a).

Brief items 1 to 7 first, then the runtime cases R1 to R25 of spec section 12.5 that
belong to U13a (R24 is U13b; K1 to K18 are U15). All runs use scripted hosts: no model,
a virtual clock, scripted event arrivals.

Spec tensions the tests settle (marked in the module under test):
- R7 says `acceptance failed`, R15 and 7.5 say a reject raises `decision rejected`. The
  run reports the raised error first. Both strings are asserted where they apply.
- R-case strings with a bare task name are asserted with the full key.
"""
import ast
import copy
import gc
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
FIX = HERE / "fixtures" / "validate_org"
sys.path.insert(0, str(SCRIPTS))

import interpreter as it  # noqa: E402
from interpreter import Interpreter, ProcessHost, ScriptedHost, StepOutcome  # noqa: E402

RID = "0123456789abcdef0123456789abcdef"
OWNER = "owner"


def _load(name):
    with open(FIX / name, encoding="utf-8") as f:
        return json.load(f)


CAT = _load("catalog.json")
MAN = _load("manifest.json")


# ---------------------------------------------------------------- builders


def wf(*tasks, name="t", **top):
    doc = {
        "document": {"dsl": "1.1.0", "namespace": "org", "name": name, "version": "0.1.0"},
        "do": [{n: t} for n, t in tasks],
    }
    doc.update(top)
    return doc


def leaf(command="work", acceptance=None, floor=False, role="worker", by="code", **extra):
    org = {"by": by, "role": role}
    if acceptance:
        org["acceptance"] = acceptance
    if floor:
        org["floor"] = True
    task = {"run": {"shell": {"command": command, "arguments": []}}, "metadata": {"org": org}}
    task.update(extra)
    return task


def chk(name="c"):
    return {"check": name}


def go(workflows, host=None, name=None, input=None, run_id=RID, catalog=None, manifest=None):
    host = host or ScriptedHost()
    if "do" in workflows and "document" in workflows:
        workflows = {workflows["document"]["name"]: workflows}
    name = name or next(iter(workflows))
    return Interpreter(workflows, host, catalog=catalog, manifest=manifest).run(name, input=input, run_id=run_id)


def starts(res, key):
    return [e for e in res.events if e["kind"] == "task-start" and e["key"] == key]


def kinds(res, kind):
    return [e for e in res.events if e["kind"] == kind]


def event(type_, data=None, signature=OWNER, **kw):
    e = {"type": type_, "data": dict(data or {}), "signature": signature}
    e.update(kw)
    return e


def decision(task, decision="approve", run=RID, item=None, type_="org.owner-decided", **kw):
    data = {"run": run, "task": task, "decision": decision}
    if item is not None:
        data["item"] = item
    return event(type_, data, **kw)


def gate(type_="org.owner-decided", after=None, role="owner", by="human", acceptance=None, floor=False, to="one"):
    flt = {"with": {"type": type_}}
    listen = {"to": {"one": flt}} if to == "one" else {"to": {to: [flt]}}
    org = {"by": by, "role": role, "acceptance": acceptance or [{"human": "decision"}]}
    if floor:
        org["floor"] = True
    return {"listen": listen, "timeout": {"after": after or {"hours": 1}}, "metadata": {"org": org}}


# ---------------------------------------------------------------- fixtures of the two processes


def sw_doc():
    """sw-development with the 12.6 changes 7 and 8 (the JSON fixture predates them)."""
    doc = copy.deepcopy(_load("sw-development.json"))
    for item in doc["do"]:
        (n, t), = item.items()
        if n == "cut":
            t["export"] = {"as": "${ $context + . }"}
        if n == "build":
            units = t["do"][0]["units"]
            units["for"]["in"] = "${ $context.units }"
            units["do"][0]["tdd"]["run"]["workflow"]["input"] = {"unit": "${ $unit }"}
    return doc


def tdd_doc():
    return copy.deepcopy(_load("tdd-unit.json"))


def improve_doc():
    doc = wf(("done", leaf("noop", [chk("every-proposal-is-within-its-rung")], role="improver")), name="improve")
    doc["do"][0]["done"]["metadata"]["org"]["metrics"] = ["escalations"]
    return doc


def fixture_workflows():
    return {"sw-development": sw_doc(), "tdd-unit": tdd_doc(), "improve": improve_doc()}


def sw_events(extra=(), review_at=10):  # noqa: D103
    return [(review_at, decision("review", item=0, type_="org.owner-review"))] + list(extra)


def sw_host(events=(), **kw):
    steps = {"cut": StepOutcome(output={"units": [{"id": "u1"}, {"id": "u2"}]})}
    steps.update(kw.pop("steps", {}))
    return ScriptedHost(steps=steps, events=list(events), **kw)


def sw_run(events=(), full=True, **kw):
    host = sw_host(sw_events(events), **kw)
    cm = {"catalog": CAT, "manifest": MAN} if full else {}
    return go(fixture_workflows(), host, name="sw-development", **cm), host


# ================================================================= brief item 1


def test_tdd_unit_passes_in_one_round():
    res = go({"tdd-unit": tdd_doc()}, ScriptedHost(), catalog=CAT, manifest=MAN)
    assert res.status == "success", res.errors
    assert res.accepted["cycle/unit-review"] is True
    assert len(starts(res, "cycle/red")) == 1
    assert starts(res, "exhausted") == []


def test_tdd_unit_failing_verdict_three_times_raises_the_escalation():
    host = ScriptedHost(judges={"cycle/unit-review": "fail"})
    res = go({"tdd-unit": tdd_doc()}, host, catalog=CAT, manifest=MAN)
    assert res.status == "error"
    assert [e["type"] for e in res.error_objects][0] == "https://org.example/errors/unit-not-accepted"
    assert len(starts(res, "cycle/red")) == 3  # the bound: never a fourth round
    assert len(starts(res, "exhausted")) == 1
    assert any(e["kind"] == "escalation" and e["to"] == "lead" for e in res.events)


def test_tdd_unit_two_failures_then_a_pass_ends_in_round_three_with_success():
    host = ScriptedHost(judges={"cycle/unit-review": ["fail", "fail", "pass"]})
    res = go({"tdd-unit": tdd_doc()}, host, catalog=CAT, manifest=MAN)
    assert res.status == "success", res.errors  # round 3 passed; earlier rounds were discarded
    assert len(starts(res, "cycle/red")) == 3


# ================================================================= brief item 2


def _counting_loop(n_in, while_src=None):
    f = {"each": "x", "in": list(range(n_in))}
    task = {"for": f, "do": [{"body": leaf("body")}]}
    if while_src:
        task["while"] = while_src
    return wf(("loop", task))


def test_while_loop_stops_at_the_bound_not_one_round_later():
    res = go(_counting_loop(3, "${ true }"))
    assert len(starts(res, "loop/body")) == 3


def test_for_without_while_runs_every_item_with_an_index_key():
    res = go(_counting_loop(4))
    assert [e["key"] for e in kinds(res, "task-start") if e["key"].startswith("loop/body")] == [
        "loop/body#0", "loop/body#1", "loop/body#2", "loop/body#3"]


def test_while_false_before_the_first_round_runs_no_round():
    res = go(_counting_loop(3, "${ false }"))
    assert starts(res, "loop/body") == []


def test_while_is_evaluated_before_each_round_so_a_pass_ends_the_loop_at_once():
    doc = wf(("loop", {"for": {"in": [1, 2, 3]}, "while": '${ $accepted["loop/body"] != true }',
                       "do": [{"body": leaf("body", [chk("c")])}]}))
    host = ScriptedHost(checks={"c": [False, True]})
    res = go(doc, host)
    assert len(starts(res, "loop/body")) == 2
    assert res.status == "success"


def test_for_in_over_the_cap_fails_before_the_first_iteration():  # R12
    doc = wf(("seed", {"set": {"units": list(range(1001))}, "export": {"as": "${ $context + . }"}}),
             ("units", {"for": {"each": "u", "in": "${ $context.units }"}, "do": [{"body": leaf()}]}))
    res = go(doc)
    assert res.status == "error"
    assert res.errors[0] == "units: for.in: 1001 items exceeds the cap of 1000"
    assert starts(res, "units/body#0") == []


def test_for_in_that_is_not_a_list_fails():
    doc = wf(("units", {"for": {"in": "${ . }"}, "do": [{"body": leaf()}]}))
    res = go(doc, input={"a": 1})
    assert res.errors[0] == "units: for.in: must evaluate to a list"


def test_cap_boundary_1000_items_is_allowed():
    doc = wf(("units", {"for": {"in": "${ . }"}, "do": [{"body": {"set": {"k": 1}}}]}))
    res = go(doc, input=list(range(1000)))
    assert res.status == "success"


def test_retry_attempt_count_is_the_number_of_retries_after_the_first_try():
    doc = wf(("guarded", {
        "try": [{"flaky": leaf("flaky")}],
        "catch": {"retry": {"limit": {"attempt": {"count": 2}}, "delay": {"seconds": 5}}},
    }))
    host = ScriptedHost(steps={"guarded/flaky": StepOutcome(exit_code=1, error="boom")})
    res = go(doc, host)
    assert len(starts(res, "guarded/flaky")) == 3  # 1 try + 2 retries, never a fourth
    assert res.now == 10.0  # two delays of five seconds on the virtual clock
    assert res.status == "success"  # the catch completed, so the failed step records `handled`
    assert res.statuses["guarded/flaky"] == "handled"


def test_try_catches_a_matching_error_and_runs_the_catch_tasks():
    doc = wf(("guarded", {
        "try": [{"flaky": leaf("flaky")}],
        "catch": {"errors": {"with": {"status": 500}}, "as": "err", "do": [{"recover": {"set": {"seen": "${ $err.status }"}}}]},
    }))
    host = ScriptedHost(steps={"guarded/flaky": StepOutcome(exit_code=1, error="boom")})
    res = go(doc, host)
    assert res.output == {"seen": 500}
    assert len(starts(res, "guarded/recover")) == 1


def test_try_does_not_catch_a_non_matching_error():
    doc = wf(("guarded", {
        "try": [{"flaky": leaf("flaky")}],
        "catch": {"errors": {"with": {"status": 404}}, "do": [{"recover": {"set": {"x": 1}}}]},
    }))
    host = ScriptedHost(steps={"guarded/flaky": StepOutcome(exit_code=1, error="boom")})
    res = go(doc, host)
    assert starts(res, "guarded/recover") == []
    assert res.status == "error"


# ================================================================= brief item 3


BAD = [
    ("call task", {"call": "http", "with": {"method": "get", "endpoint": "http://x"}}),
    ("run.container", {"run": {"container": {"image": "x"}}}),
    ("run.script", {"run": {"script": {"language": "python", "code": "print(1)"}}}),
]


@pytest.mark.parametrize("label,task", BAD, ids=[b[0] for b in BAD])
def test_a_node_outside_the_subset_is_refused_before_any_node_runs(label, task):
    host = ScriptedHost()
    doc = wf(("first", leaf("first")), ("bad", task))
    res = go(doc, host)
    assert res.status == "refused"
    assert res.errors[0].startswith("run refused: t: bad: ")
    assert host.calls == []
    assert kinds(res, "task-start") == []


def test_use_is_refused_before_any_node_runs():
    host = ScriptedHost()
    res = go(wf(("first", leaf()), use={"functions": {}}), host)
    assert res.status == "refused" and host.calls == []


def test_a_bad_workflow_that_is_only_called_is_refused_before_the_root_runs():
    root = wf(("first", leaf("first")), ("sub", {"run": {"workflow": {"namespace": "org", "name": "child", "version": "1"}}}), name="root")
    child = wf(("bad", {"call": "http", "with": {}}), name="child")
    host = ScriptedHost()
    res = go({"root": root, "child": child}, host, name="root")
    assert res.status == "refused" and host.calls == []
    assert "child" in res.errors[0]


def test_full_validation_refuses_a_workflow_that_fails_validate_org():
    sw = sw_doc()
    del sw["do"][0]["align"]["metadata"]["org"]["acceptance"]
    host = sw_host()
    wfs = fixture_workflows()
    wfs["sw-development"] = sw
    res = go(wfs, host, name="sw-development", catalog=CAT, manifest=MAN)
    assert res.status == "refused"
    assert any(e.startswith("run refused: sw-development: align: metadata.org.acceptance") for e in res.errors)
    assert host.calls == []


def test_unknown_start_workflow_is_refused():
    res = go(wf(("a", leaf())), name="nope")
    assert res.status == "refused"


# ================================================================= brief item 4


def _floor_doc_with(task_before):
    return wf(task_before, ("fl", leaf("fl", [chk()], floor=True)), ("after", leaf("after")))


def _full_refusal(mutate):
    sw = sw_doc()
    mutate(sw)
    wfs = fixture_workflows()
    wfs["sw-development"] = sw
    host = sw_host()
    res = go(wfs, host, name="sw-development", catalog=CAT, manifest=MAN)
    assert res.status == "refused", res.errors
    assert host.calls == []
    return res


def test_a_floor_cannot_be_given_an_if_static():
    def mutate(sw):
        sw["do"][1]["spec"]["if"] = "${ false }"
    res = _full_refusal(mutate)
    assert any("a floor may not have 'if'" in e for e in res.errors)


def test_then_exit_cannot_skip_a_floor_static():
    def mutate(sw):
        sw["do"][0]["align"]["then"] = "exit"
    res = _full_refusal(mutate)
    assert any("'exit' skips floor" in e for e in res.errors)


def test_a_switch_case_cannot_skip_a_floor_static():
    def mutate(sw):
        sw["do"][0]["align"] = {"switch": [{"c": {"when": "${ true }", "then": "review"}}]}
    res = _full_refusal(mutate)
    assert any("skips floor" in e for e in res.errors)


def test_floor_with_if_false_is_not_run_and_the_run_ends_in_error_runtime_backstop():
    doc = wf(("pre", leaf("pre")), ("fl", dict(leaf("fl", [chk()], floor=True), **{"if": "${ false }"})))
    res = go(doc)
    assert res.status == "error"
    assert "fl: floor-not-run" in res.errors


def test_floor_skipped_by_nested_then_exit_ends_in_floor_not_run():
    doc = wf(("grp", {"do": [{"x": dict(leaf("x"), then="exit")}, {"fl": leaf("fl", [chk()], floor=True)}]}))
    res = go(doc)
    assert res.status == "error"
    assert "grp/fl: floor-not-run" in res.errors


def test_floor_skipped_by_top_level_then_end_ends_in_floor_not_run():
    doc = wf(("x", dict(leaf("x"), then="end")), ("fl", leaf("fl", [chk()], floor=True)))
    res = go(doc)
    assert "fl: floor-not-run" in res.errors


def test_floor_skipped_by_a_switch_case_jump_ends_in_floor_not_run():
    doc = wf(("pick", {"switch": [{"go": {"when": "${ true }", "then": "after"}}]}),
             ("fl", leaf("fl", [chk()], floor=True)), ("after", leaf("after")))
    res = go(doc)
    assert "fl: floor-not-run" in res.errors
    assert starts(res, "fl") == []


def test_a_control_run_with_every_floor_run_and_passed_is_a_success():  # positive control for the above
    res = go(_floor_doc_with(("pre", leaf("pre"))))
    assert res.status == "success"


def test_floor_inside_for_over_empty_list_is_floor_not_run():  # R2
    doc = wf(("rework", {"for": {"in": "${ . }"}, "do": [{"fl": leaf("fl", [chk()], floor=True)}]}))
    res = go(doc, input=[])
    assert res.errors == ["rework/fl: floor-not-run"]


def test_a_failed_floor_raises_at_once_and_later_tasks_do_not_start():  # R16
    doc = wf(("spec", leaf("spec", [chk("sc")], floor=True)), ("next", leaf("next")))
    res = go(doc, ScriptedHost(checks={"sc": False}))
    assert res.errors == ["spec: acceptance failed"]
    assert starts(res, "next") == []
    assert res.accepted["spec"] is False


# ================================================================= brief item 5


def _gate_doc(**kw):
    return wf(("pre", leaf("pre")), ("merge-gate", gate(floor=True, **kw)), ("merge", leaf("merge")))


def test_gate_blocks_until_the_signed_owner_event_then_continues():
    ev = [(50, decision("merge-gate"))]
    res = go(_gate_doc(), ScriptedHost(events=ev))
    assert res.status == "success", res.errors
    end = [e for e in res.events if e["kind"] == "task-end" and e["key"] == "merge-gate"][0]
    assert end["t"] == 50
    assert starts(res, "merge")[0]["t"] == 50
    assert res.accepted["merge-gate"] is True


def test_gate_times_out_with_the_declared_action_a_timeout_error():  # R9
    doc = _gate_doc(after={"hours": 1})
    res = go(doc, ScriptedHost())
    assert res.status == "error"
    assert res.errors[0] == "merge-gate: timeout"
    assert res.error_objects[0]["type"].endswith("/errors/timeout")
    assert res.error_objects[0]["status"] == 408
    assert res.accepted["merge-gate"] is False
    assert res.now == 3600
    assert starts(res, "merge") == []


def test_gate_does_not_time_out_early_nor_late():
    ev = [(3599, decision("merge-gate"))]
    assert go(_gate_doc(after={"hours": 1}), ScriptedHost(events=ev)).status == "success"
    ev = [(3601, decision("merge-gate"))]
    assert go(_gate_doc(after={"hours": 1}), ScriptedHost(events=ev)).errors[0] == "merge-gate: timeout"


def test_unsigned_decision_is_ignored_and_the_gate_keeps_waiting():  # R6
    ev = [(10, decision("merge-gate", type_="org.owner-decided", signature=None)), (20, decision("merge-gate"))]
    res = go(_gate_doc(), ScriptedHost(events=ev))
    assert res.status == "success"
    ign = kinds(res, "ignored")
    assert len(ign) == 1
    assert ign[0]["text"].startswith("merge-gate: ignored event 'org.owner-decided': ")
    assert [e for e in res.events if e["kind"] == "task-end" and e["key"] == "merge-gate"][0]["t"] == 20


def test_forged_event_emitted_by_a_task_cannot_complete_a_decision_gate():
    doc = wf(("forge", {"emit": {"event": {"with": {"type": "org.owner-decided", "data": {"task": "merge-gate", "decision": "approve"}}}},
                        "metadata": {"org": {"by": "code", "role": "ci", "acceptance": [chk()]}}}),
             ("merge-gate", gate(floor=True)))
    res = go(doc)
    assert res.errors[0] == "forge: emit.event.with.type: 'org.owner-decided' uses the reserved prefix org.owner-"
    assert starts(res, "merge-gate") == []


def test_owner_reject_raises_decision_rejected_and_records_fail():  # R7 and R15
    doc = _gate_doc()
    res = go(doc, ScriptedHost(events=[(5, decision("merge-gate", "reject"))]))
    assert res.status == "error"
    assert res.errors[0] == "merge-gate: decision rejected"
    assert res.accepted["merge-gate"] is False
    assert starts(res, "merge") == []


def test_approve_naming_another_task_is_ignored():  # R8
    res = go(_gate_doc(), ScriptedHost(events=[(5, decision("some-other-key"))]))
    assert len(kinds(res, "ignored")) == 1
    assert res.errors[0] == "merge-gate: timeout"


def test_approve_for_another_run_is_ignored():  # R18
    res = go(_gate_doc(), ScriptedHost(events=[(5, decision("merge-gate", run="f" * 32))]))
    assert len(kinds(res, "ignored")) == 1
    assert res.errors[0] == "merge-gate: timeout"


def test_decision_value_must_be_approve_or_reject():
    res = go(_gate_doc(), ScriptedHost(events=[(5, decision("merge-gate", "maybe"))]))
    assert len(kinds(res, "ignored")) == 1


def test_event_of_another_type_is_not_even_logged_as_ignored():
    res = go(_gate_doc(), ScriptedHost(events=[(5, event("org.other", {"x": 1}))]))
    assert kinds(res, "ignored") == []


def test_plain_gate_completes_on_an_unsigned_event_with_the_run_id_and_runs_its_check():  # R14
    doc = wf(("join", {"listen": {"to": {"one": {"with": {"type": "org.ping"}}}}, "timeout": {"after": {"hours": 1}},
                       "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk("join-ok")]}}}))
    host = ScriptedHost(events=[(7, event("org.ping", {"run": RID}, signature=None))])
    res = go(doc, host)
    assert res.status == "success"
    assert ("check", "join-ok", "join") in [c[:3] for c in host.calls]


def test_plain_gate_ignores_an_event_of_another_run():
    doc = wf(("join", {"listen": {"to": {"one": {"with": {"type": "org.ping"}}}}, "timeout": {"after": {"seconds": 30}},
                       "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}))
    res = go(doc, ScriptedHost(events=[(7, event("org.ping", {"run": "e" * 32}, signature=None))]))
    assert res.errors[0] == "join: timeout"


def test_plain_gate_with_correlate_skips_the_run_id_test():
    flt = {"with": {"type": "org.ping"}, "correlate": {"unit": {"from": "${ .data.unit }", "expect": "u1"}}}
    doc = wf(("join", {"listen": {"to": {"one": flt}}, "timeout": {"after": {"seconds": 30}},
                       "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}))
    ev = [(3, event("org.ping", {"unit": "u2"}, signature=None)), (4, event("org.ping", {"unit": "u1"}, signature=None))]
    res = go(doc, ScriptedHost(events=ev))
    assert res.status == "success"
    assert [e for e in res.events if e["kind"] == "task-end" and e["key"] == "join"][0]["t"] == 4


def test_to_all_waits_for_every_filter():
    def f(t):
        return {"with": {"type": t}}
    doc = wf(("both", {"listen": {"to": {"all": [f("a"), f("b")]}}, "timeout": {"after": {"seconds": 60}},
                       "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}))
    ev = [(1, event("a", {"run": RID}, signature=None)), (9, event("b", {"run": RID}, signature=None))]
    res = go(doc, ScriptedHost(events=ev))
    assert [e for e in res.events if e["kind"] == "task-end" and e["key"] == "both"][0]["t"] == 9


# ================================================================= brief item 6


def _sample_run(judge="pass", rid=RID):
    host = ScriptedHost(judges={"cycle/unit-review": judge})
    return go({"tdd-unit": tdd_doc()}, host, catalog=CAT, manifest=MAN, run_id=rid)


def test_same_inputs_and_scripted_outputs_give_the_same_event_sequence():
    a, b = _sample_run(), _sample_run()
    assert a.events == b.events and a.events


def test_a_different_scripted_output_gives_a_different_sequence():
    assert _sample_run("pass").events != _sample_run("fail").events


def test_same_sequence_with_parallel_work_and_events():
    def once():
        host = ScriptedHost(steps={"fan/units/unit#0>work": StepOutcome(duration=5), "fan/units/unit#1>work": StepOutcome(duration=3)})
        return _fanout_run(2, host)
    a, b = once(), once()
    assert a.status == "success", a.errors
    assert starts(a, "fan/units/unit#0>work") and starts(a, "fan/units/unit#1>work")  # the subflow really ran
    assert a.events == b.events


# ================================================================= brief item 7


def test_imports_are_standard_library_or_the_two_sibling_modules():
    tree = ast.parse((SCRIPTS / "interpreter.py").read_text(encoding="utf-8"))
    allowed = set(sys.stdlib_module_names) | {"expr", "validate_org"}
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add(node.module.split(".")[0])
    assert names <= allowed, names - allowed
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            assert not (isinstance(f, ast.Name) and f.id in ("eval", "exec", "compile", "__import__")), f.id
            assert not (isinstance(f, ast.Attribute) and f.attr in ("system", "popen")), f.attr
            assert not any(k.arg == "shell" and getattr(k.value, "value", None) is True for k in node.keywords)


def test_no_local_paths_in_the_module():
    text = (SCRIPTS / "interpreter.py").read_text(encoding="utf-8")
    for needle in ("claude-" + "501", "/Us" + "ers/", "~/Fun/" + "plans", "/private/" + "tmp"):
        assert needle not in text


# ================================================================= acceptance items and sampling


def test_item_results_pass_fail_pending_and_the_task_fails_on_any_fail():
    items = [chk("a"), chk("b")]
    doc = wf(("t1", leaf("w", items)))
    res = go(doc, ScriptedHost(checks={"a": True, "b": False}))
    assert [e["result"] for e in kinds(res, "item")] == ["pass", "fail"]
    assert res.accepted["t1"] is False
    assert res.errors == ["t1: acceptance failed"]


def _draw(run_id, key, item):
    h = int.from_bytes(hashlib.sha256(f"{run_id}\n{key}\n{item}".encode()).digest()[:8], "big")
    return h / 2**64


def _rid_with(draw_below, key="t1", item=0, sample=0.2):
    for i in range(2000):
        rid = f"{i:032x}"
        if (_draw(rid, key, item) < sample) == draw_below:
            return rid
    raise AssertionError("no run id found")


def _rubric_doc(sample):
    return wf(("t1", leaf("w", [{"rubric": "criteria/x.md", "judge": "reviewer", "sample": sample}], role="worker")))


def test_sampling_draw_is_a_pure_function_of_run_id_and_full_key():  # R3
    undrawn, drawn = _rid_with(False), _rid_with(True)
    for _ in range(2):
        host = ScriptedHost()
        res = go(_rubric_doc(0.2), host, run_id=undrawn)
        assert [e["result"] for e in kinds(res, "item")] == ["pending"]
        assert res.status == "success" and res.accepted["t1"] is True
        assert not any(c[0] == "judge" for c in host.calls)
    host = ScriptedHost()
    res = go(_rubric_doc(0.2), host, run_id=drawn)
    assert [e["result"] for e in kinds(res, "item")] == ["pass"]
    assert any(c[0] == "judge" for c in host.calls)


def test_absent_sample_always_judges_and_sample_one_always_judges():
    for s in (None, 1):
        item = {"rubric": "criteria/x.md", "judge": "reviewer"}
        if s:
            item["sample"] = s
        host = ScriptedHost()
        go(wf(("t1", leaf("w", [item]))), host)
        assert any(c[0] == "judge" for c in host.calls)


def test_a_pending_item_does_not_make_the_task_fail_but_is_never_recorded_as_pass():
    res = go(_rubric_doc(0.2), run_id=_rid_with(False))
    assert [e["result"] for e in kinds(res, "item")] == ["pending"]
    assert "pass" not in [e["result"] for e in kinds(res, "item")]
    assert res.status == "success"


def test_owner_rubric_verdict_approve_and_reject():  # R19 first half
    doc = wf(("review", leaf("work", [{"rubric": "criteria/r.md", "judge": "owner"}], role="reviewer")))
    ok = go(doc, ScriptedHost(events=[(5, decision("review", item=0, type_="org.owner-review"))]))
    assert ok.status == "success"
    bad = go(doc, ScriptedHost(events=[(5, decision("review", "reject", item=0, type_="org.owner-review"))]))
    assert bad.errors == ["review: acceptance failed"]


def test_owner_rubric_decision_for_another_item_or_unsigned_is_ignored_and_the_wait_is_bounded_by_the_task_limit():
    doc = wf(("review", leaf("work", [{"rubric": "criteria/r.md", "judge": "owner"}], role="reviewer", timeout={"after": {"hours": 2}})))
    ev = [(5, decision("review", item=1)), (6, decision("review", item=0, signature=None))]
    res = go(doc, ScriptedHost(events=ev))
    assert res.errors[0] == "review: timeout"
    assert res.now == 7200


def test_model_judge_verdict_from_an_invocation_the_runtime_did_not_start_is_fail():  # R19 second half
    doc = wf(("t1", leaf("w", [{"rubric": "criteria/x.md", "judge": "reviewer"}])))

    def forged(req):
        return {"invocation": "someone-else", "type": "org.rubric-verdict",
                "data": {"run": req.run_id, "task": req.key, "item": req.item, "verdict": "pass"}}
    res = go(doc, ScriptedHost(judges={"t1": forged}))
    assert kinds(res, "item")[0]["result"] == "fail"


@pytest.mark.parametrize("field,value", [("run", "x"), ("task", "other"), ("item", 7), ("verdict", "maybe")])
def test_model_judge_verdict_with_a_mismatched_field_is_fail(field, value):
    doc = wf(("t1", leaf("w", [{"rubric": "criteria/x.md", "judge": "reviewer"}])))

    def reply(req):
        data = {"run": req.run_id, "task": req.key, "item": req.item, "verdict": "pass"}
        data[field] = value
        return {"invocation": req.invocation, "type": "org.rubric-verdict", "data": data}
    res = go(doc, ScriptedHost(judges={"t1": reply}))
    assert kinds(res, "item")[0]["result"] == "fail"


# ================================================================= $accepted and data flow


def test_step_output_and_export_cannot_set_accepted_r4():
    doc = wf(("s", dict(leaf("w", [chk("bad")]), export={"as": "${ $context + . }"})),
             ("probe", {"set": {"seen": '${ $accepted["s"] }'}}))
    host = ScriptedHost(steps={"s": StepOutcome(output={"accepted": True})}, checks={"bad": False})
    res = go(doc, host)
    assert res.accepted["s"] is False
    assert res.output == {"seen": False}
    assert res.context == {"accepted": True}  # ordinary data in the context
    assert res.errors == ["s: acceptance failed"]


def test_unrun_key_reads_null():
    doc = wf(("probe", {"set": {"seen": '${ $accepted["nothing"] }'}}))
    assert go(doc).output == {"seen": None}


def test_data_flow_input_from_output_as_export_as():
    doc = wf(("a", dict(leaf("w"), **{"input": {"from": "${ .x }"}, "output": {"as": "${ .y }"}, "export": {"as": "${ $context + {} }"}})))
    # `{}` is not in the subset: the export must be reported as an expression error, not crash.
    res = go(doc, ScriptedHost(steps={"a": StepOutcome(output={"y": 5})}), input={"x": 1})
    assert res.status == "error"
    assert "a: " in res.errors[0]
    assert res.error_objects[0]["type"].endswith("/errors/expression")
    assert res.error_objects[0]["status"] == 400


def test_data_flows_task_to_task_and_context_accumulates():
    doc = wf(("a", leaf("w", output={"as": "${ .y }"}, export={"as": "${ $context + . }"})),
             ("b", {"set": {"got": "${ . }", "ctx": "${ $context }"}}))
    res = go(doc, ScriptedHost(steps={"a": StepOutcome(output={"y": {"k": 5}})}))
    assert res.status == "success", res.errors
    assert res.output == {"got": {"k": 5}, "ctx": {"k": 5}}


def test_expression_error_is_the_ows_expression_error():
    doc = wf(("a", {"set": {"v": "${ .a | map(.) }"}}))
    res = go(doc)
    assert res.error_objects[0]["type"].endswith("/errors/expression")


def test_rework_loop_discards_results_after_while_and_before_the_round():  # R20
    seen = []

    def probe(req):
        seen.append(dict(req.accepted))
        return StepOutcome()
    doc = wf(("rework", {"for": {"in": [1, 2]}, "while": '${ $accepted["rework/spec"] != true }',
                         "do": [{"spec": leaf("spec", [chk("sc")], floor=True)}, {"probe": leaf("probe")}]}))
    host = ScriptedHost(steps={"rework/probe": probe, "rework/spec": probe}, checks={"sc": [False, True]})
    res = go(doc, host)
    assert res.status == "success", res.errors
    # request 0: spec round 1; 1: probe round 1; 2: spec round 2 (discarded: no key yet)
    assert "rework/spec" not in seen[2]
    assert seen[1]["rework/spec"] is False


def test_rework_loop_exempts_a_floor_the_while_reads_and_a_last_round_failure_ends_the_run():  # R1
    cond = '${ ($accepted["rework/spec"] == null) or ($accepted["rework/spec"] == true) }'
    doc = wf(("rework", {"for": {"in": [1, 2]}, "while": cond, "do": [{"spec": leaf("spec", [chk("sc")], floor=True)}]}))
    res = go(doc, ScriptedHost(checks={"sc": [True, False]}))
    assert len(starts(res, "rework/spec")) == 2
    assert res.errors == ["rework/spec: acceptance failed"]


def test_floor_in_a_loop_whose_while_does_not_read_it_raises_at_once():
    doc = wf(("rework", {"for": {"in": [1, 2]}, "while": "${ true }", "do": [{"spec": leaf("spec", [chk("sc")], floor=True)}]}))
    res = go(doc, ScriptedHost(checks={"sc": False}))
    assert len(starts(res, "rework/spec")) == 1
    assert res.errors == ["rework/spec: acceptance failed"]


def _task_with_check(doc, check_name):
    """The task path of the first task whose acceptance has `check_name` (fixture-agnostic)."""
    for item in doc["do"][0]["cycle"]["do"]:
        (n, t), = item.items()
        if any(i.get("check") == check_name for i in t["metadata"]["org"].get("acceptance", [])):
            return n
    raise KeyError(check_name)


def test_non_floor_failure_continues_and_the_run_still_ends_in_error():  # R5 shape
    doc = tdd_doc()
    failing = _task_with_check(doc, "red-evidence")
    host = ScriptedHost(checks={"red-evidence": [True, True, False]}, judges={"cycle/unit-review": ["fail", "fail", "pass"]})
    res = go({"tdd-unit": doc}, host, catalog=CAT, manifest=MAN)
    assert res.errors == [f"cycle/{failing}: acceptance failed"]
    assert len(starts(res, "cycle/red")) == 3
    assert starts(res, "exhausted") == []


def test_step_that_exits_non_zero_raises_and_records_fail():  # R21
    doc = wf(("s", leaf("work", [chk()])), ("next", leaf()))
    res = go(doc, ScriptedHost(steps={"s": StepOutcome(exit_code=2, error="bad input")}))
    assert res.status == "error"
    assert res.errors[0] == "s: bad input"
    assert res.error_objects[0]["type"].endswith("/errors/runtime")
    assert res.accepted["s"] is False
    assert starts(res, "next") == []


def test_step_without_a_timeout_is_limited_to_one_hour():  # R10
    doc = wf(("s", leaf("work", [chk()])))
    res = go(doc, ScriptedHost(steps={"s": StepOutcome(duration=3601)}))
    assert res.errors[0] == "s: timeout"
    assert res.accepted["s"] is False
    assert res.now == 3600


def test_step_at_exactly_the_limit_completes():
    res = go(wf(("s", leaf("work"))), ScriptedHost(steps={"s": StepOutcome(duration=3600)}))
    assert res.status == "success"


def test_inline_timeout_replaces_the_one_hour_limit():
    doc = wf(("s", dict(leaf("work"), timeout={"after": {"hours": 7}})))
    assert go(doc, ScriptedHost(steps={"s": StepOutcome(duration=3 * 3600)})).status == "success"
    doc = wf(("s", dict(leaf("work"), timeout={"after": {"minutes": 1}})))
    assert go(doc, ScriptedHost(steps={"s": StepOutcome(duration=61)})).errors[0] == "s: timeout"


def test_step_request_carries_role_and_brief_from_metadata_and_appends_them_to_argv():
    doc = wf(("a", {"run": {"shell": {"command": "agent-run", "arguments": ["--isolated"]}},
                    "metadata": {"org": {"by": "model", "role": "pm", "brief": "briefs/a.md"}}}))
    seen = []
    host = ScriptedHost(steps={"a": lambda req: seen.append(req) or StepOutcome()})
    go(doc, host)
    assert seen[0].argv[:-1] == ["agent-run", "--isolated", "--role", "pm", "--brief", "briefs/a.md", "--input"]


def test_agent_run_as_owner_is_refused_at_run_time_even_without_static_validation():
    doc = wf(("a", {"run": {"shell": {"command": "agent-run", "arguments": []}},
                    "metadata": {"org": {"by": "human", "role": "owner", "brief": "briefs/a.md"}}}))
    host = ScriptedHost()
    res = go(doc, host)
    assert res.errors[0] == "a: metadata.org.role: agent-run may not run as owner"
    assert not any(c[0] == "step" for c in host.calls)


def test_agent_run_with_a_role_flag_in_its_arguments_is_refused_at_run_time():
    doc = wf(("a", {"run": {"shell": {"command": "agent-run", "arguments": ["--role", "owner"]}},
                    "metadata": {"org": {"by": "model", "role": "pm", "brief": "briefs/a.md"}}}))
    host = ScriptedHost()
    res = go(doc, host)
    assert res.status == "error" and not any(c[0] == "step" for c in host.calls)


def test_brief_that_resolves_outside_the_org_root_fails_the_task_and_nothing_runs():  # R13 (scripted)
    doc = wf(("align", {"run": {"shell": {"command": "agent-run", "arguments": []}},
                        "metadata": {"org": {"by": "model", "role": "pm", "brief": "briefs/align.md"}}}))
    host = ScriptedHost(outside={"briefs/align.md"})
    res = go(doc, host)
    assert res.errors[0] == "align: metadata.org.brief: 'briefs/align.md' resolves outside the org root"
    assert not any(c[0] == "step" for c in host.calls)


# ================================================================= calls and subflows


def _chain(n):
    docs = {}
    for i in range(n + 1):
        name = f"w{i}"
        if i < n:
            docs[name] = wf(("c", {"run": {"workflow": {"namespace": "org", "name": f"w{i + 1}", "version": "1"}},
                                   "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}), name=name)
        else:
            docs[name] = wf(("end", leaf("end")), name=name)
    return docs


def test_call_depth_of_eight_calls_is_allowed():
    assert go(_chain(8), name="w0").status == "success"


def test_call_depth_exceeding_eight_fails_before_the_target_runs_r11():
    res = go(_chain(9), name="w0")
    assert res.status == "error"
    key = ">".join(["c"] * 9)
    assert res.errors[0] == f"{key}: run.workflow: call depth exceeds 8"
    assert starts(res, ">".join(["c"] * 9) + ">end") == []


def test_call_cycle_fails_before_the_target_runs_r11():
    a = wf(("c", {"run": {"workflow": {"namespace": "org", "name": "b", "version": "1"}}, "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}), name="a")
    b = wf(("c", {"run": {"workflow": {"namespace": "org", "name": "a", "version": "1"}}, "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}), name="b")
    res = go({"a": a, "b": b}, name="a")
    assert res.errors[0] == "c>c: run.workflow: call cycle 'a' -> 'b' -> 'a'"


def test_call_cycle_error_cannot_be_caught_by_a_try():
    a = wf(("guard", {"try": [{"c": {"run": {"workflow": {"namespace": "org", "name": "a", "version": "1"}},
                                      "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}}],
                      "catch": {"do": [{"swallow": {"set": {"x": 1}}}]}}), name="a")
    res = go({"a": a}, name="a")
    assert res.status == "error" and "call cycle" in res.errors[0]


def test_subflow_keys_use_the_caller_key_and_accepted_is_per_execution():
    child = wf(("inner", leaf("work", [chk()])), name="child")
    root = wf(("call", {"run": {"workflow": {"namespace": "org", "name": "child", "version": "1", "input": {"v": "${ $workflow.id }"}}},
                        "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk("ok")]}}}),
              ("probe", {"set": {"seen": '${ $accepted["inner"] }'}}), name="root")
    res = go({"root": root, "child": child}, name="root")
    assert starts(res, "call>inner")
    assert res.accepted["call"] is True
    assert "inner" not in res.accepted
    assert res.output == {"seen": None}


def test_subflow_receives_input_and_workflow_id_is_the_run_id():
    seen = []
    child = wf(("inner", leaf("work")), name="child")
    root = wf(("call", {"run": {"workflow": {"namespace": "org", "name": "child", "version": "1", "input": {"run": "${ $workflow.id }"}}},
                        "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}), name="root")
    host = ScriptedHost(steps={"inner": lambda req: seen.append(req.input) or StepOutcome()})
    go({"root": root, "child": child}, host, name="root")
    assert seen == [{"run": RID}]


def test_call_to_a_workflow_with_floors_inside_an_empty_for_is_floor_not_run():  # R22
    child = wf(("fl", leaf("fl", [chk()], floor=True)), name="child")
    root = wf(("each", {"for": {"in": "${ . }"}, "do": [{"c": {"run": {"workflow": {"namespace": "org", "name": "child", "version": "1"}},
                                                               "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}}]}), name="root")
    res = go({"root": root, "child": child}, name="root", input=[])
    assert "each/c: floor-not-run" in res.errors


def test_a_floor_of_a_called_workflow_that_never_runs_is_floor_not_run_with_the_call_prefix():
    child = wf(("fl", dict(leaf("fl", [chk()], floor=True), **{"if": "${ false }"})), name="child")
    root = wf(("c", {"run": {"workflow": {"namespace": "org", "name": "child", "version": "1"}},
                     "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}), name="root")
    res = go({"root": root, "child": child}, name="root")
    assert "c>fl: floor-not-run" in res.errors


def test_call_has_no_time_limit_of_its_own_r23():
    child = wf(("a", dict(leaf("work"), timeout={"hours": 1})), ("b", leaf("work")), name="child")
    child["do"][0]["a"]["timeout"] = {"after": {"hours": 1}}
    root = wf(("c", {"run": {"workflow": {"namespace": "org", "name": "child", "version": "1"}},
                     "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}), name="root")
    host = ScriptedHost(steps={"a": StepOutcome(duration=3500), "b": StepOutcome(duration=3500)})
    res = go({"root": root, "child": child}, host, name="root")
    assert res.status == "success", res.errors
    assert res.now == 7000


# ================================================================= fork, parallel work, joins


def test_fork_runs_branches_at_once_and_completes_when_all_complete():
    doc = wf(("par", {"fork": {"branches": [{"a": leaf("a")}, {"b": leaf("b")}]}}))
    host = ScriptedHost(steps={"par/a": StepOutcome(duration=10), "par/b": StepOutcome(duration=30)})
    res = go(doc, host)
    assert starts(res, "par/a")[0]["t"] == starts(res, "par/b")[0]["t"] == 0
    assert res.now == 30


def test_fork_compete_completes_on_the_first_branch_and_cancels_the_rest():
    doc = wf(("par", {"fork": {"compete": True, "branches": [{"a": leaf("a")}, {"b": leaf("b")}]}}), ("after", leaf("after")))
    host = ScriptedHost(steps={"par/a": StepOutcome(duration=10), "par/b": StepOutcome(duration=30)})
    res = go(doc, host)
    assert starts(res, "after")[0]["t"] == 10
    assert res.statuses["par/b"] == "cancelled"


def test_branches_ending_at_the_same_moment_do_not_overwrite_each_other_r25():
    doc = wf(("par", {"fork": {"branches": [{"a": leaf("a", [chk("ca")])}, {"b": leaf("b", [chk("cb")])}]}}))
    host = ScriptedHost(steps={"par/a": StepOutcome(duration=5), "par/b": StepOutcome(duration=5)},
                        checks={"ca": False, "cb": True})
    res = go(doc, host)
    assert res.accepted == {"par/a": False, "par/b": True}
    assert res.errors == ["par/a: acceptance failed"]


def test_a_failing_branch_error_cancels_the_other_branches():
    doc = wf(("par", {"fork": {"branches": [{"a": leaf("a")}, {"b": leaf("b")}]}}))
    host = ScriptedHost(steps={"par/a": StepOutcome(exit_code=1, error="x", duration=1), "par/b": StepOutcome(duration=50)})
    res = go(doc, host)
    assert res.errors[0] == "par/a: x"
    assert res.accepted.get("par/b") is False


def _fanout_doc(n, join_timeout=None, unit_floor=False):
    unit = {"run": {"workflow": {"namespace": "org", "name": "unit-wf", "version": "1", "input": {"unit": "${ $u }"}}, "await": False},
            "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk("unit-ok")]}}}
    join = {"listen": {"to": {"any": [{"with": {"type": "org.task-ended"}}],
                              "until": "${ ($events | length) == ($context.units | length) }"}},
            "timeout": join_timeout or {"after": {"hours": 1}},
            "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk("join-ok")]}}}
    return wf(("seed", {"set": {"units": list(range(n))}, "export": {"as": "${ $context + . }"}}),
              ("fan", {"do": [
                  {"units": {"for": {"each": "u", "in": "${ $context.units }"}, "do": [{"unit": unit}]}},
                  {"join": join}]}), name="fan-root")


def _fanout_run(n, host=None):
    docs = {"fan-root": _fanout_doc(n), "unit-wf": wf(("work", leaf("work")), name="unit-wf")}
    docs["fan-root"]["do"][1]["fan"]["do"][0]["units"]["do"][0]["unit"]["run"]["workflow"]["name"] = "unit-wf"
    return go(docs, host, name="fan-root")


def test_await_false_returns_at_once_and_units_run_concurrently():
    host = ScriptedHost(steps={"fan/units/unit#0>work": StepOutcome(duration=100), "fan/units/unit#1>work": StepOutcome(duration=100)})
    res = _fanout_run(2, host)
    assert res.status == "success", res.errors
    assert starts(res, "fan/units/unit#0")[0]["t"] == starts(res, "fan/units/unit#1")[0]["t"] == 0
    assert starts(res, "fan/units/unit#0>work")[0]["t"] == starts(res, "fan/units/unit#1>work")[0]["t"] == 0
    assert res.now == 100  # both ran at once: 100, not 200


def test_join_completes_only_when_every_unit_has_reported():
    host = ScriptedHost(steps={"fan/units/unit#0>work": StepOutcome(duration=10), "fan/units/unit#1>work": StepOutcome(duration=40)})
    res = _fanout_run(2, host)
    end = [e for e in res.events if e["kind"] == "task-end" and e["key"] == "fan/join"][0]
    assert end["t"] == 40


def test_join_over_zero_units_completes_at_once():
    res = _fanout_run(0)
    assert res.status == "success"


def test_each_unit_reports_once_so_the_join_never_double_counts():
    res = _fanout_run(3)
    ended = kinds(res, "event")
    ended = [e for e in ended if e["type"] == "org.task-ended"]
    assert sorted(e["event"]["data"]["task"] for e in ended) == [f"fan/units/unit#{i}" for i in range(3)]


def test_run_does_not_end_until_started_work_has_ended():
    doc = wf(("bg", dict(leaf("work"), run={"shell": {"command": "work", "arguments": []}, "await": False})), ("after", leaf("after")))
    host = ScriptedHost(steps={"bg": StepOutcome(duration=500)})
    res = go(doc, host)
    assert starts(res, "after")[0]["t"] == 0
    assert res.now == 500
    assert res.accepted["bg"] is True


def test_await_false_acceptance_is_recorded_when_the_work_ends():
    doc = wf(("bg", dict(leaf("work", [chk("late")]), run={"shell": {"command": "work", "arguments": []}, "await": False})))
    host = ScriptedHost(steps={"bg": StepOutcome(duration=500)}, checks={"late": False})
    res = go(doc, host)
    accept = [e for e in res.events if e["kind"] == "accept" and e["key"] == "bg"][0]
    assert accept["t"] == 500 and accept["ok"] is False
    assert res.errors == ["bg: acceptance failed"]


def test_decision_gate_inside_a_unit_completes_only_for_its_own_key_r17():
    unit_wf = wf(("approve", gate(after={"hours": 1}, acceptance=[{"human": "ok"}])), name="unit-wf")
    unit_wf["do"][0]["approve"]["metadata"]["org"]["role"] = "owner"
    docs = {"fan-root": _fanout_doc(2, join_timeout={"after": {"hours": 2}}), "unit-wf": unit_wf}
    ev = [(100, decision("fan/units/unit#0>approve"))]
    res = go(docs, ScriptedHost(events=ev), name="fan-root")
    ends = {e["key"]: e for e in res.events if e["kind"] == "task-end"}
    assert ends["fan/units/unit#0>approve"]["t"] == 100
    assert res.accepted["fan/units/unit#0"] is True
    assert res.accepted["fan/units/unit#1"] is False
    assert ends["fan/join"]["t"] == 3600  # unit 1 times out at one hour, then both have reported


# ================================================================= full process runs (sw-development)


def test_sw_development_runs_to_success_with_scripted_agents():
    res, host = sw_run(events=[(20, decision("merge-gate"))])
    assert res.status == "success", res.errors
    assert res.accepted["merge-gate"] is True
    assert res.accepted["merge"] is True
    assert len(starts(res, "build/units/tdd#0")) == 1 and len(starts(res, "build/units/tdd#1")) == 1
    assert starts(res, "build/units/tdd#0>cycle/red")


def test_owner_reject_stops_the_run_before_merge_r15():
    res, host = sw_run(events=[(20, decision("merge-gate", "reject"))])
    assert res.errors[0] == "merge-gate: decision rejected"
    assert starts(res, "merge") == []
    assert not any(c[:2] == ("step", "merge-change") for c in host.calls)


def test_unsigned_owner_decided_is_ignored_in_the_full_process_r6():
    res, _ = sw_run(events=[(15, decision("merge-gate", signature=None))])
    assert res.errors[0] == "merge-gate: timeout"
    assert kinds(res, "ignored")[0]["text"].startswith("merge-gate: ignored event 'org.owner-decided': ")


def test_failed_spec_floor_raises_at_once_in_the_full_process_r16():
    res, _ = sw_run(checks={"spec-check": False})
    assert res.errors == ["spec: acceptance failed"]
    assert starts(res, "acceptance-tests") == []


def test_acceptance_run_failing_in_both_build_rounds_reaches_not_accepted():
    res, _ = sw_run(checks={"acceptance-suite-green": False})
    assert len(starts(res, "build/acceptance-run")) == 2  # the bound of [1, 2]
    assert res.error_objects[0]["type"] == "https://org.example/errors/acceptance-not-met"
    assert starts(res, "review") == []


def test_merge_is_guarded_by_the_accepted_gate():
    res, _ = sw_run(events=[(20, decision("merge-gate"))])
    assert res.accepted["merge-gate"] is True and starts(res, "merge")


def test_improve_call_receives_the_run_id():
    seen = []
    res, _ = sw_run(events=[(20, decision("merge-gate"))], steps={"improve>done": lambda req: seen.append(req.input) or StepOutcome()})
    assert seen == [{"run": res.run_id}]


# ================================================================= control flow constructs


def test_switch_picks_the_first_true_case_and_jumps():
    doc = wf(("pick", {"switch": [{"no": {"when": "${ false }", "then": "a"}}, {"yes": {"when": "${ true }", "then": "c"}},
                                 {"other": {"then": "b"}}]}),
             ("a", leaf("a")), ("b", leaf("b")), ("c", leaf("c")))
    res = go(doc)
    assert [e["key"] for e in kinds(res, "task-start")] == ["pick", "c"]


def test_switch_default_case_has_no_when():
    doc = wf(("pick", {"switch": [{"no": {"when": "${ false }", "then": "a"}}, {"other": {"then": "c"}}]}),
             ("a", leaf("a")), ("b", leaf("b")), ("c", leaf("c")))
    assert [e["key"] for e in kinds(go(doc), "task-start")] == ["pick", "c"]


def test_then_name_jumps_forward_and_a_missing_name_fails():
    doc = wf(("a", dict(leaf("a"), then="c")), ("b", leaf("b")), ("c", leaf("c")))
    assert [e["key"] for e in kinds(go(doc), "task-start")] == ["a", "c"]
    res = go(wf(("a", dict(leaf("a"), then="zz")), ("b", leaf("b"))))
    assert res.status == "error" and "zz" in res.errors[0]


def test_then_end_in_a_subflow_ends_only_that_subflow():
    child = wf(("x", dict(leaf("x"), then="end")), ("y", leaf("y")), name="child")
    root = wf(("c", {"run": {"workflow": {"namespace": "org", "name": "child", "version": "1"}},
                    "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}), ("after", leaf("after")), name="root")
    res = go({"root": root, "child": child}, name="root")
    assert starts(res, "c>y") == [] and starts(res, "after")


def test_if_false_skips_the_task_and_passes_its_input_on():
    doc = wf(("a", dict(leaf("w"), **{"if": "${ false }"})), ("b", {"set": {"got": "${ . }"}}))
    res = go(doc, input={"v": 1})
    assert res.output == {"got": {"v": 1}}
    assert starts(res, "a") == []


def test_raise_ends_the_run_with_the_declared_error_and_logs_the_escalation():
    doc = wf(("boom", {"raise": {"error": {"type": "https://x/e", "status": 409, "title": "Nope"}}, "metadata": {"org": {"to": "lead"}}}), ("n", leaf()))
    res = go(doc)
    assert res.errors == ["boom: Nope"]
    assert res.error_objects[0]["status"] == 409
    assert kinds(res, "escalation")[0]["to"] == "lead"


def test_wait_advances_the_virtual_clock():
    res = go(wf(("w", {"wait": {"minutes": 2, "seconds": 3}})))
    assert res.now == 123


def test_emit_publishes_an_event_with_the_run_id_and_a_plain_gate_can_hear_it():
    doc = wf(("fan", {"fork": {"branches": [
        {"listener": {"listen": {"to": {"one": {"with": {"type": "org.ping"}}}}, "timeout": {"after": {"minutes": 5}},
                      "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}},
        {"sender": {"emit": {"event": {"with": {"type": "org.ping", "data": {"n": 1}}}},
                    "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}}]}}))
    res = go(doc)
    assert res.status == "success", res.errors
    assert kinds(res, "emit")[0]["event"]["data"] == {"n": 1, "run": RID}


def test_run_ends_in_success_only_if_every_leaf_last_result_passed():
    res = go(wf(("a", leaf("w", [chk("x")])), ("b", leaf())), ScriptedHost(checks={"x": False}))
    assert res.status == "error" and res.errors == ["a: acceptance failed"]


def test_several_failures_are_reported_in_pre_order_of_the_task_paths():
    doc = wf(("a", leaf("w", [chk("x")])), ("b", leaf("w", [chk("y")])), ("c", leaf("w", [chk("z")])))
    res = go(doc, ScriptedHost(checks={"x": False, "y": False, "z": False}))
    assert res.errors == ["a: acceptance failed", "b: acceptance failed", "c: acceptance failed"]


def test_run_id_is_128_random_bits_as_32_hex_digits_when_not_supplied():
    r1 = Interpreter({"t": wf(("a", leaf()))}, ScriptedHost()).run("t")
    r2 = Interpreter({"t": wf(("a", leaf()))}, ScriptedHost()).run("t")
    assert len(r1.run_id) == 32 and set(r1.run_id) <= set("0123456789abcdef")
    assert r1.run_id != r2.run_id


# ================================================================= evidence file (spec 6.1)


def _evidence_host(seen):
    def check(name, key, evidence):
        seen.append((name, key, copy.deepcopy(evidence)))
        return True
    return ScriptedHost(checks={"probe": check})


def test_evidence_holds_only_code_step_results_of_this_execution_never_model_output():
    doc = wf(("code-step", leaf("tdd-evidence", by="code")),
             ("model-step", leaf("agent-run", by="model", role="worker", brief="briefs/m.md")),
             ("checked", leaf("w", [chk("probe")], by="model")))
    doc["do"][1]["model-step"]["metadata"]["org"]["brief"] = "briefs/m.md"
    seen = []
    host = ScriptedHost(steps={"code-step": StepOutcome(exit_code=0, stdout="green"),
                               "model-step": StepOutcome(stdout="I wrote this, trust me")}, checks={"probe": lambda n, k, e: seen.append((n, k, e)) or True})
    res = go(doc, host)
    assert res.status == "success", res.errors
    (name, key, ev), = seen
    assert key == "checked"
    assert (ev["run"], ev["key"]) == (RID, "checked")
    assert ev["steps"] == {"code-step": {"exit": 0, "stdout": "green"}}  # never the model step's claim
    assert ev["outputs"]["model-step"]["stdout"] == "I wrote this, trust me"  # a claim, only in outputs


def test_evidence_keeps_the_last_execution_per_key_and_is_per_workflow_execution():
    child = wf(("c-step", leaf("w", by="code")), ("c-check", leaf("w", [chk("probe")], by="model")), name="child")
    root = wf(("r-step", leaf("w", by="code")),
              ("call", {"run": {"workflow": {"namespace": "org", "name": "child", "version": "1"}},
                        "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk("probe")]}}}), name="root")
    seen = []
    host = ScriptedHost(steps={"r-step": StepOutcome(stdout="r"), "c-step": StepOutcome(stdout="c")},
                        checks={"probe": lambda n, k, e: seen.append((k, e["steps"])) or True})
    go({"root": root, "child": child}, host, name="root")
    assert ("call>c-check", {"c-step": {"exit": 0, "stdout": "c"}}) in seen
    assert ("call", {"r-step": {"exit": 0, "stdout": "r"}}) in seen


def test_a_failed_code_step_leaves_its_exit_in_the_evidence_of_a_later_check_in_a_caught_flow():
    doc = wf(("g", {"try": [{"bad": leaf("w", by="code")}], "catch": {"do": [{"after": leaf("w", [chk("probe")], by="model")}]}}))
    seen = []
    host = ScriptedHost(steps={"g/bad": StepOutcome(exit_code=4, stdout="x", error="no")},
                        checks={"probe": lambda n, k, e: seen.append(e["steps"]) or True})
    go(doc, host)
    assert seen == [{"g/bad": {"exit": 4, "stdout": "x"}}]


def test_process_host_check_gets_the_evidence_file_and_the_three_environment_variables(org, tmp_path):
    _script(org / "bin" / "w", "echo green\n")
    out = tmp_path / "seen.json"
    (org / "checks" / "probe.py").write_text(
        "import json, os, sys\n"
        "ev = json.load(open(os.environ['ORG_EVIDENCE']))\n"
        f"json.dump({{'argv': sys.argv[1:], 'key': os.environ['ORG_KEY'], 'run': os.environ['ORG_RUN'], 'ev': ev, 'abs': os.path.isabs(os.environ['ORG_EVIDENCE'])}}, open({str(out)!r}, 'w'))\n"
        "sys.exit(0 if ev['key'] == os.environ['ORG_KEY'] and ev['run'] == os.environ['ORG_RUN'] else 2)\n")
    doc = wf(("s", leaf("w", by="code")), ("c", leaf("w", [chk("probe")], by="code")))
    res = go(doc, ProcessHost(str(org)))
    assert res.status == "success", res.errors
    seen = json.loads(out.read_text())
    assert seen["argv"] == ["c"] and seen["key"] == "c" and seen["run"] == RID and seen["abs"] is True
    assert seen["ev"]["steps"]["s"] == {"exit": 0, "stdout": "green\n"}


@pytest.mark.parametrize("code", [1, 2, 3])
def test_process_host_check_exit_one_two_or_other_is_fail(org, code):
    _script(org / "bin" / "w", "echo 1\n")
    (org / "checks" / "x.py").write_text(f"import sys\nsys.exit({code})\n")
    doc = wf(("s", leaf("w", [chk("x")], by="code")))
    assert go(doc, ProcessHost(str(org))).errors == ["s: acceptance failed"]


def test_process_host_removes_the_evidence_file_after_the_check(org, tmp_path):
    _script(org / "bin" / "w", "echo 1\n")
    path = tmp_path / "path.txt"
    (org / "checks" / "x.py").write_text(f"import os\nopen({str(path)!r}, 'w').write(os.environ['ORG_EVIDENCE'])\n")
    go(wf(("s", leaf("w", [chk("x")], by="code"))), ProcessHost(str(org)))
    assert not os.path.exists(path.read_text())


# ================================================================= ProcessHost (real argv exec, root confinement)


def _script(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def org(tmp_path):
    root = tmp_path / "root"
    (root / "bin").mkdir(parents=True)
    (root / "checks").mkdir()
    (root / "briefs").mkdir()
    return root


def test_process_host_runs_a_bin_command_by_argv_and_parses_json_output(org):
    _script(org / "bin" / "emit-json", 'echo \'{"args": "\'"$*"\'"}\'\n')
    doc = wf(("s", {"run": {"shell": {"command": "emit-json", "arguments": ["a b", "$HOME;ls"]}},
                    "metadata": {"org": {"by": "code", "role": "ci"}}}))
    res = go(doc, ProcessHost(str(org)))
    assert res.status == "success", res.errors
    assert res.output == {"args": "a b $HOME;ls"}  # arguments reach the command as argv, never through a shell


def test_process_host_refuses_a_command_that_is_not_agent_run_or_in_bin(org):
    doc = wf(("s", {"run": {"shell": {"command": "ls", "arguments": []}}, "metadata": {"org": {"by": "code", "role": "ci"}}}))
    res = go(doc, ProcessHost(str(org)))
    assert res.errors[0] == "s: run.shell.command: 'ls' is not agent-run or a file in bin/"


def test_process_host_nonzero_exit_fails_the_step(org):
    _script(org / "bin" / "bad", "echo oops >&2\nexit 2\n")
    doc = wf(("s", {"run": {"shell": {"command": "bad", "arguments": []}}, "metadata": {"org": {"by": "code", "role": "ci"}}}))
    res = go(doc, ProcessHost(str(org)))
    assert res.status == "error" and res.accepted["s"] is False
    assert "oops" in res.errors[0]


def test_process_host_kills_a_step_that_runs_past_its_limit(org):
    _script(org / "bin" / "slow", "sleep 30\n")
    doc = wf(("s", {"run": {"shell": {"command": "slow", "arguments": []}}, "timeout": {"after": {"seconds": 1}},
                    "metadata": {"org": {"by": "code", "role": "ci"}}}))
    res = go(doc, ProcessHost(str(org)))
    assert res.errors[0] == "s: timeout"


def test_process_host_agent_run_gets_role_and_brief_after_the_checks(org):
    stub = org.parent / "agent-run"
    _script(stub, 'echo "$@"\n')
    (org / "briefs" / "a.md").write_text("brief")
    doc = wf(("a", {"run": {"shell": {"command": "agent-run", "arguments": ["--isolated"]}},
                    "metadata": {"org": {"by": "model", "role": "pm", "brief": "briefs/a.md"}}}))
    res = go(doc, ProcessHost(str(org), agent_run=str(stub)))
    assert res.output.startswith("--isolated --role pm --brief briefs/a.md --input ")


def test_process_host_check_script_exit_code_is_the_verdict_and_gets_the_full_key(org):
    _script(org / "checks" / "ok.py", "")
    (org / "checks" / "ok.py").write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.exit(0 if sys.argv[1:] == ['s'] and len(sys.argv) == 2 else 1)\n")
    (org / "checks" / "ok.py").chmod(0o755)
    (org / "checks" / "bad.py").write_text("import sys\nsys.exit(3)\n")
    _script(org / "bin" / "w", "echo 1\n")
    step = lambda c: {"run": {"shell": {"command": "w", "arguments": []}}, "metadata": {"org": {"by": "code", "role": "ci", "acceptance": [chk(c)]}}}  # noqa: E731
    assert go(wf(("s", step("ok"))), ProcessHost(str(org))).status == "success"
    assert go(wf(("s", step("bad"))), ProcessHost(str(org))).errors == ["s: acceptance failed"]
    assert go(wf(("s", step("missing"))), ProcessHost(str(org))).errors == ["s: acceptance failed"]  # cannot start is fail


def test_process_host_brief_symlink_outside_the_root_is_refused_and_no_byte_is_read(org, tmp_path):  # R13
    secret = tmp_path / "outside.md"
    secret.write_text("SECRET")
    (org / "briefs" / "align.md").symlink_to(secret)
    marker = tmp_path / "ran"
    stub = tmp_path / "agent-run"
    _script(stub, f"touch {marker}\n")
    doc = wf(("align", {"run": {"shell": {"command": "agent-run", "arguments": []}},
                        "metadata": {"org": {"by": "model", "role": "pm", "brief": "briefs/align.md"}}}))
    res = go(doc, ProcessHost(str(org), agent_run=str(stub)))
    assert res.errors[0] == "align: metadata.org.brief: 'briefs/align.md' resolves outside the org root"
    assert not marker.exists()
    host = ProcessHost(str(org))
    reads = []
    real_read = os.read
    os.read = lambda fd, n: reads.append(fd) or real_read(fd, n)
    try:
        assert host.confined("briefs/align.md") is False
    finally:
        os.read = real_read
    assert reads == []


def test_process_host_symlink_that_stays_inside_the_root_is_allowed(org):
    (org / "briefs" / "real.md").write_text("x")
    (org / "briefs" / "alias.md").symlink_to(org / "briefs" / "real.md")
    assert ProcessHost(str(org)).confined("briefs/alias.md") is True
    assert ProcessHost(str(org)).confined("briefs/missing.md") is False


# ================================================================= update 1: spec updates 3 and 4 (R26 to R34)


def _ended(res):
    return [e["event"] for e in kinds(res, "event") if e["type"] == "org.task-ended"]


def test_r26_each_unit_end_emits_task_ended_and_until_sees_events_one_then_two():
    host = ScriptedHost(steps={"fan/units/unit#0>work": StepOutcome(duration=10), "fan/units/unit#1>work": StepOutcome(duration=40)})
    res = _fanout_run(2, host)
    ev = _ended(res)
    assert [e["data"] for e in ev] == [
        {"run": RID, "task": "fan/units/unit#0", "accepted": True},
        {"run": RID, "task": "fan/units/unit#1", "accepted": True}]
    untils = [(e["events"], e["result"]) for e in kinds(res, "until")]
    assert untils == [(0, False), (1, False), (2, True)]
    assert "org.unit-done" not in [e["type"] for e in kinds(res, "event")]


def test_task_ended_accepted_is_false_for_a_failed_unit_and_cancelled_work_emits_nothing():
    doc = wf(("bg", dict(leaf("work", [chk("late")]), run={"shell": {"command": "work", "arguments": []}, "await": False})))
    res = go(doc, ScriptedHost(checks={"late": False}))
    assert _ended(res)[0]["data"]["accepted"] is False


def test_r27_join_over_zero_units_completes_before_any_event_and_not_by_timeout():
    res = _fanout_run(0)
    end = [e for e in res.events if e["kind"] == "task-end" and e["key"] == "fan/join"][0]
    assert end["t"] == 0
    assert [(e["events"], e["result"]) for e in kinds(res, "until")] == [(0, True)]


def test_a_join_consumes_only_events_of_its_own_workflow_execution():
    child = wf(("w", dict(leaf("work"), run={"shell": {"command": "work", "arguments": []}, "await": False})),
               ("join", {"listen": {"to": {"any": [{"with": {"type": "org.task-ended"}}], "until": "${ ($events | length) == 1 }"}},
                         "timeout": {"after": {"hours": 1}},
                         "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}), name="child")
    root = wf(("bg", dict(leaf("work"), run={"shell": {"command": "work", "arguments": []}, "await": False})),
              ("c", {"run": {"workflow": {"namespace": "org", "name": "child", "version": "1"}},
                     "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}), name="root")
    host = ScriptedHost(steps={"bg": StepOutcome(duration=5), "c>w": StepOutcome(duration=10)})
    res = go({"root": root, "child": child}, host, name="root")
    end = [e for e in res.events if e["kind"] == "task-end" and e["key"] == "c>join"][0]
    assert end["t"] == 10  # root's `bg` ended at 5 and must not count


def test_a_join_ignores_task_ended_events_it_did_not_see_started_work_for():
    flt = {"with": {"type": "org.task-ended"}}
    doc = wf(("join", {"listen": {"to": {"any": [flt], "until": "${ ($events | length) == 1 }"}}, "timeout": {"after": {"seconds": 30}},
                       "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}))
    forged = event("org.task-ended", {"run": RID, "task": "x", "accepted": True}, signature=None)
    res = go(doc, ScriptedHost(events=[(3, forged)]))
    assert res.errors[0] == "join: timeout"


def test_emit_of_a_reserved_prefix_is_refused_at_run_time():
    for t in ("org.task-ended", "org.owner-decided"):
        doc = wf(("e", {"emit": {"event": {"with": {"type": t}}}, "metadata": {"org": {"by": "code", "role": "ci", "acceptance": [chk()]}}}))
        res = go(doc)
        prefix = "org.task-" if t.startswith("org.task-") else "org.owner-"
        assert res.errors[0] == f"e: emit.event.with.type: '{t}' uses the reserved prefix {prefix}"


# ---- R28: the runtime-owned input file, --network, runtime-only flags


def _agent(name="a", network=None, arguments=(), role="pm", **extra):
    org = {"by": "model", "role": role, "brief": "briefs/a.md"}
    if network is not None:
        org["network"] = network
    task = {"run": {"shell": {"command": "agent-run", "arguments": list(arguments)}}, "metadata": {"org": org}}
    task.update(extra)
    return task


def _capture(store, outcome=None):
    def fn(req):
        store.append((req, json.loads(Path(req.input_file).read_text())))
        return outcome or StepOutcome()
    return fn


def test_r28_agent_run_gets_input_file_role_brief_network_in_that_order():
    seen = []
    doc = wf(("design", _agent(network="none")))
    host = ScriptedHost(steps={"design": _capture(seen)})
    go(doc, host, input={"spec": "s"})
    req, body = seen[0]
    assert req.argv == ["agent-run", "--role", "pm", "--brief", "briefs/a.md", "--network", "none", "--input", req.input_file]
    assert body == {"run": RID, "key": "design", "input": {"spec": "s"}, "reasons": {}}


def test_r28_input_file_holds_the_input_after_input_from_and_is_read_only_outside_the_org_root(tmp_path):
    seen = []
    doc = wf(("design", dict(_agent(), input={"from": "${ .spec }"})))
    host = ScriptedHost(steps={"design": _capture(seen)}, root=str(tmp_path / "root"))
    go(doc, host, input={"spec": {"k": 1}})
    req, body = seen[0]
    assert body["input"] == {"k": 1}
    assert not os.access(req.input_file, os.W_OK) or os.geteuid() == 0
    assert not os.path.realpath(req.input_file).startswith(os.path.realpath(str(tmp_path / "root")) + os.sep)


def test_no_network_flag_when_the_step_declares_none():
    seen = []
    go(wf(("a", _agent())), ScriptedHost(steps={"a": _capture(seen)}))
    assert "--network" not in seen[0][0].argv


@pytest.mark.parametrize("args,text", [
    (["--network", "all"], "run.shell.arguments: --network is set by the runtime from metadata.org; remove it"),
    (["--network=all"], "run.shell.arguments: --network is set by the runtime from metadata.org; remove it"),
    (["--brief=x"], "run.shell.arguments: --brief is set by the runtime from metadata.org; remove it"),
    (["--input", "/etc/passwd"], "run.shell.arguments: --input is set by the runtime from the task input; remove it"),
    (["--input=/x"], "run.shell.arguments: --input is set by the runtime from the task input; remove it"),
    (["--isolated", "--isolated"], "run.shell.arguments: --isolated given more than once"),
    (["--verbose"], "run.shell.arguments: '--verbose' is not an allowed agent-run flag (allowed: --isolated)"),
])
def test_a_step_cannot_carry_a_runtime_flag(args, text):
    host = ScriptedHost()
    res = go(wf(("a", _agent(arguments=args))), host)
    assert res.errors[0] == f"a: {text}"
    assert not any(c[0] == "step" for c in host.calls)


def test_model_judge_input_file_holds_the_item_and_the_judged_output():
    seen = []

    def judge(req):
        seen.append((req, json.loads(Path(req.input_file).read_text())))
        return {"invocation": req.invocation, "type": "org.rubric-verdict",
                "data": {"run": req.run_id, "task": req.key, "item": req.item, "verdict": "pass"}}
    doc = wf(("t1", leaf("work", [{"rubric": "criteria/x.md", "judge": "reviewer"}])))
    go(doc, ScriptedHost(steps={"t1": StepOutcome(output={"diff": 3})}, judges={"t1": judge}))
    req, body = seen[0]
    assert body["input"]["item"] == 0
    assert body["input"]["output"] == {"exit": 0, "stdout": '{"diff": 3}'}  # the judged task's entry (6.1, P29)
    assert body["input"]["evidence"]["key"] == "t1" and body["input"]["evidence"]["output"] == body["input"]["output"]
    assert body["reasons"] == {}
    assert req.argv == ["agent-run", "--role", "reviewer", "--brief", "criteria/x.md", "--input", req.input_file]


# ---- R29: evidence is a snapshot from before the task started


def test_a_check_on_a_code_step_does_not_see_that_steps_own_result():
    seen = []
    doc = wf(("s", leaf("w", [chk("probe")], by="code")))
    go(doc, ScriptedHost(checks={"probe": lambda n, k, e: seen.append(e["steps"]) or True}))
    assert seen == [{}]


def test_r29_check_on_the_model_step_gets_no_entry_for_the_code_step_that_runs_after_it(org):
    _script(org / "bin" / "w", "echo 1\n")
    (org / "checks" / "red-evidence.py").write_text(
        "import json, os, sys\n"
        "ev = json.load(open(os.environ['ORG_EVIDENCE']))\n"
        "sys.exit(0 if 'red-evidence' in ev['steps'] else 2)\n")
    doc = wf(("red", leaf("w", [chk("red-evidence")], by="model", role="worker")),
             ("red-evidence", leaf("w", by="code", role="ci")))
    res = go(doc, ProcessHost(str(org)))
    assert res.accepted["red"] is False
    assert res.errors == ["red: acceptance failed"]


def test_a_rework_round_clears_the_evidence_of_earlier_rounds():
    seen = []
    doc = wf(("rework", {"for": {"in": [1, 2]}, "while": "${ true }",
                         "do": [{"chk": leaf("w", [chk("probe")], by="model")}, {"code": leaf("w", by="code")}]}))
    host = ScriptedHost(checks={"probe": lambda n, k, e: seen.append(sorted(e["steps"])) or True})
    go(doc, host)
    assert seen == [[], []]  # round 1's `code` ended before round 2's check; the new round discarded it


# ---- R30 handled, R31 cancelled


def test_r30_non_floor_gate_timing_out_inside_a_caught_try_records_handled_and_the_run_succeeds():
    doc = wf(("g", {"try": [{"waiter": gate(after={"minutes": 1}, role="lead", by="code", acceptance=[chk()])}],
                    "catch": {"errors": {"with": {"status": 408}}, "do": [{"fallback": {"set": {"ok": True}}}]}}))
    res = go(doc)
    assert res.status == "success", res.errors
    assert res.statuses["g/waiter"] == "handled"
    assert res.accepted["g/waiter"] is False


def test_a_catch_that_itself_raises_leaves_fail():
    doc = wf(("g", {"try": [{"waiter": gate(after={"minutes": 1}, role="lead", by="code", acceptance=[chk()])}],
                    "catch": {"do": [{"boom": {"raise": {"error": {"type": "https://x/e", "status": 500, "title": "again"}}}}]}}))
    res = go(doc)
    assert res.status == "error" and res.statuses["g/waiter"] == "fail"


def test_a_try_without_catch_do_also_records_handled():
    doc = wf(("g", {"try": [{"bad": leaf("w")}], "catch": {}}))
    res = go(doc, ScriptedHost(steps={"g/bad": StepOutcome(exit_code=1, error="x")}))
    assert res.statuses["g/bad"] == "handled" and res.status == "success"


def test_r31_losing_compete_branch_records_cancelled_and_the_run_succeeds():
    doc = wf(("race", {"fork": {"compete": True, "branches": [{"a": leaf("a")}, {"b": leaf("b", [chk("cb")])}]}}))
    host = ScriptedHost(steps={"race/a": StepOutcome(duration=1), "race/b": StepOutcome(duration=9)}, checks={"cb": False})
    res = go(doc, host)
    assert res.statuses == {"race/a": "pass", "race/b": "cancelled"}
    assert res.status == "success", res.errors


def test_r31_a_winner_that_fails_ends_the_run_in_error():
    doc = wf(("race", {"fork": {"compete": True, "branches": [{"a": leaf("a", [chk("ca")])}, {"b": leaf("b")}]}}))
    host = ScriptedHost(steps={"race/a": StepOutcome(duration=1), "race/b": StepOutcome(duration=9)}, checks={"ca": False})
    res = go(doc, host)
    assert res.errors == ["race/a: acceptance failed"]


# ---- R32 signer


def _signer_gate(signer="pm"):
    g = gate(role="lead", by="human", acceptance=[{"human": "ok"}])
    g["metadata"]["org"]["signer"] = signer
    return g


def test_r32_gate_with_a_signer_ignores_the_owner_and_accepts_the_signer():
    doc = wf(("gate", _signer_gate()))
    ev = [(1, decision("gate", signature="owner")), (2, decision("gate", signature="pm"))]
    res = go(doc, ScriptedHost(events=ev))
    assert res.status == "success", res.errors
    assert [e["reason"] for e in kinds(res, "ignored")] == ["not signed by the pm"]
    assert [e for e in res.events if e["kind"] == "task-end"][0]["t"] == 2


def test_a_signer_alone_makes_a_decision_gate():
    g = _signer_gate()
    g["metadata"]["org"]["acceptance"] = [chk()]
    g["metadata"]["org"]["role"] = "lead"
    unsigned = decision("gate", signature=None)  # a plain gate would complete on this: right run, no signature needed
    res = go(wf(("gate", g)), ScriptedHost(events=[(1, unsigned)]))
    assert res.errors[0] == "gate: timeout"
    assert kinds(res, "ignored")[0]["reason"] == "not signed by the pm"


def test_default_verifier_of_the_process_host_refuses_every_decision(org):
    doc = wf(("gate", gate(after={"seconds": 5})))
    host = ProcessHost(str(org), events=[(1, decision("gate"))])
    assert go(doc, host).errors[0] == "gate: timeout"


def test_injected_verifier_of_the_process_host_gets_the_event_and_the_signer(org):
    seen = []
    host = ProcessHost(str(org), events=[(1, decision("gate"))], verify=lambda e, s: seen.append(s) or True)
    assert go(wf(("gate", gate())), host).status == "success"
    assert seen == ["owner"]


# ---- R33 and R34: rework rounds


def _rework(body, n=3, cond=None):
    return wf(("rework", {"for": {"in": list(range(n))}, "while": cond or "${ true }", "do": body}))


def test_r33_new_round_cancels_unfinished_await_false_work_of_the_earlier_round():
    doc = _rework([{"bg": dict(leaf("work"), run={"shell": {"command": "work", "arguments": []}, "await": False})}], n=2)
    host = ScriptedHost(steps={"rework/bg": [StepOutcome(duration=100), StepOutcome(duration=1)]})
    res = go(doc, host)
    accepts = [e for e in kinds(res, "accept") if e["key"] == "rework/bg"]
    assert [e["status"] for e in accepts] == ["cancelled", "pass"]
    assert accepts[0]["t"] == 0  # cancelled at the start of round 2, not at 100
    ended = _ended(res)
    assert len(ended) == 1 and ended[0]["data"]["task"] == "rework/bg"
    assert res.now == 1


def test_r33_round_two_join_never_sees_round_one_work():
    join = {"listen": {"to": {"any": [{"with": {"type": "org.task-ended"}}], "until": "${ ($events | length) == 1 }"}},
            "timeout": {"after": {"hours": 1}}, "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}
    bg = dict(leaf("work"), run={"shell": {"command": "work", "arguments": []}, "await": False})
    doc = _rework([{"bg": bg}, {"pause": {"wait": {"seconds": 5}}}, {"join": join}], n=2)
    host = ScriptedHost(steps={"rework/bg": [StepOutcome(duration=2), StepOutcome(duration=3)]})
    res = go(doc, host)
    assert res.status == "success", res.errors  # a round-2 join that counted round 1's event would see 2 and time out
    assert [(e["events"], e["result"]) for e in kinds(res, "until") if e["t"] >= 5] == [(0, False), (1, True), (0, False), (1, True)]


def test_a_join_counts_work_that_ended_before_it_started_listening():
    res = _fanout_run(3)  # default scripted units end at once, before the join exists
    assert res.status == "success", res.errors
    assert [e["t"] for e in res.events if e["kind"] == "task-end" and e["key"] == "fan/join"] == [0.0]


def test_r34_reject_in_a_rework_loop_whose_while_names_the_gate_records_fail_without_raising():
    g = gate(role="lead", by="human", acceptance=[{"human": "ok"}])
    g["metadata"]["org"]["signer"] = "owner"
    doc = _rework([{"approve": g}, {"after": leaf("after")}], n=2, cond='${ $accepted["rework/approve"] != true }')
    ev = [(5, decision("rework/approve", "reject")), (9, decision("rework/approve"))]
    res = go(doc, ScriptedHost(events=ev))
    assert res.status == "success", res.errors
    accepts = [(e["t"], e["status"]) for e in kinds(res, "accept") if e["key"] == "rework/approve"]
    assert accepts == [(5, "fail"), (9, "pass")]
    assert len(starts(res, "rework/after")) == 2


def test_r34_reject_outside_such_a_loop_still_raises():
    res = go(_gate_doc(), ScriptedHost(events=[(5, decision("merge-gate", "reject"))]))
    assert res.errors[0] == "merge-gate: decision rejected"


def test_r28_reject_reason_reaches_the_next_rounds_input_file_reasons_map():
    seen = []
    g = gate(role="lead", by="human", acceptance=[{"human": "ok"}])
    doc = _rework([{"approve": g}, {"design": _agent("design")}], n=2, cond='${ $accepted["rework/approve"] != true }')
    ev = [(5, event("org.owner-decided", {"run": RID, "task": "rework/approve", "decision": "reject", "reason": "too vague"})),
          (9, decision("rework/approve"))]
    go(doc, ScriptedHost(events=ev, steps={"rework/design": _capture(seen)}))
    assert [b["reasons"] for _, b in seen] == [{}, {"rework/approve": "too vague"}]


# ---- final examples (12.6): sw-development in the W89 shape


def sw_w89_doc():
    doc = sw_doc()
    build = [t for item in doc["do"] for n, t in item.items() if n == "build"][0]
    build["do"][0]["units"]["do"][0]["tdd"]["run"]["await"] = False
    join = {"listen": {"to": {"any": [{"with": {"type": "org.task-ended"}}],
                              "until": "${ ($events | length) == ($context.units | length) }"}},
            "timeout": {"after": {"hours": 1}},
            "metadata": {"org": {"by": "code", "role": "lead", "metrics": ["escalations"], "acceptance": [chk("unit-verdict-is-pass")]}}}
    build["do"].insert(1, {"join": join})
    return doc


def test_sw_development_w89_fan_out_with_the_join_runs_to_success_on_the_final_examples():
    wfs = fixture_workflows()
    wfs["sw-development"] = sw_w89_doc()
    host = sw_host(sw_events([(120, decision("merge-gate"))], review_at=100),
                   steps={"build/units/tdd#0>cycle/red": StepOutcome(duration=30), "build/units/tdd#1>cycle/red": StepOutcome(duration=10)})
    res = go(wfs, host, name="sw-development", catalog=CAT, manifest=MAN)
    assert res.status == "success", res.errors
    join_end = [e["t"] for e in res.events if e["kind"] == "task-end" and e["key"] == "build/join"][0]
    assert join_end == 30  # the slower unit decides when the join completes
    assert len(_ended(res)) == 2


# ================================================================= review 1 and spec update 6


def _detached(command="work", acceptance=None, **extra):
    return dict(leaf(command, acceptance, **extra), run={"shell": {"command": command, "arguments": []}, "await": False})


def _call(name, **org):
    meta = {"by": "code", "role": "lead", "acceptance": [chk()]}
    meta.update(org)
    return {"run": {"workflow": {"namespace": "org", "name": name, "version": "1"}}, "metadata": {"org": meta}}


def _plain_gate(until=None, after=None, type_="org.task-ended"):
    to = {"any": [{"with": {"type": type_}}]}
    if until:
        to["until"] = until
    return {"listen": {"to": to}, "timeout": {"after": after or {"hours": 1}},
            "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}


def _evidence_of(res_host_checks, doc, **kw):
    seen = []
    host = ScriptedHost(checks={"probe": lambda n, k, e: seen.append((k, e)) or True}, **kw)
    return go(doc, host), seen


# ---- B1 to B6


def test_b1_reject_records_fail_when_the_gate_has_no_human_item_and_a_rework_loop_reads_it():
    g = gate(role="owner", by="human", acceptance=[chk()])
    doc = _rework([{"approve": g}], n=2, cond='${ $accepted["rework/approve"] != true }')
    ev = [(5, decision("rework/approve", "reject")), (9, decision("rework/approve"))]
    res = go(doc, ScriptedHost(events=ev))
    accepts = [(e["t"], e["status"]) for e in kinds(res, "accept") if e["key"] == "rework/approve"]
    assert accepts == [(5, "fail"), (9, "pass")]


def test_b2_a_rework_round_in_one_iteration_keeps_the_results_of_the_other_iterations():
    inner = {"rework": {"for": {"in": [1, 2]}, "while": "${ true }", "do": [{"x": leaf("w", [chk("c")])}]}}
    doc = wf(("outer", {"for": {"each": "i", "in": [0, 1]}, "do": [{"body": {"do": [inner]}}]}))
    res = go(doc)
    assert sorted(res.accepted) == ["outer/body#0/rework/x", "outer/body#1/rework/x"]
    assert res.status == "success"


def test_b2_index_attaches_to_the_body_task_so_descendants_keep_the_prefix():
    doc = wf(("outer", {"for": {"each": "i", "in": [0, 1]}, "do": [{"body": {"do": [{"leafy": leaf()}]}}]}))
    assert sorted(go(doc).accepted) == ["outer/body#0/leafy", "outer/body#1/leafy"]


def test_b3_detached_work_in_a_subflow_is_cancelled_by_the_callers_new_round():
    child = wf(("bg", _detached()), name="child")
    root = wf(("rework", {"for": {"in": [1, 2]}, "while": "${ true }", "do": [{"c": _call("child")}]}), name="root")
    host = ScriptedHost(steps={"bg": [StepOutcome(duration=100), StepOutcome(duration=1)]})
    res = go({"root": root, "child": child}, host, name="root")
    accepts = [(e["t"], e["status"]) for e in kinds(res, "accept") if e["key"] == "rework/c>bg"]
    assert accepts == [(0.0, "cancelled"), (1.0, "pass")]  # nothing lands at t=100 over round 2
    assert res.now == 1


def test_b4_a_matcher_error_is_a_run_error_against_the_gate_not_a_traceback():
    flt = {"with": {"type": "org.ping"}, "correlate": {"k": {"from": "${ .data.x.y }", "expect": "1"}}}
    doc = wf(("join", {"listen": {"to": {"one": flt}}, "timeout": {"after": {"seconds": 30}},
                       "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}))
    res = go(doc, ScriptedHost(events=[(3, event("org.ping", {"x": 5}, signature=None))]))
    assert res.status == "error" and res.errors[0].startswith("join: ")
    assert res.statuses["join"] == "fail"


def test_b4_an_error_in_a_matcher_reached_by_an_emit_is_charged_to_the_gate_not_the_emitter():
    flt = {"with": {"type": "org.ping"}, "correlate": {"k": {"from": "${ .data.x.y }", "expect": "1"}}}
    listener = {"listen": {"to": {"one": flt}}, "timeout": {"after": {"seconds": 30}},
                "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}
    sender = {"emit": {"event": {"with": {"type": "org.ping", "data": {"x": 5}}}},
              "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}
    doc = wf(("fan", {"fork": {"branches": [{"listener": listener}, {"sender": sender}]}}))
    res = go(doc)
    assert res.errors[0].startswith("fan/listener: ")
    assert res.statuses["fan/sender"] == "pass"


def test_b4_a_host_that_raises_is_a_located_run_error():
    for host in (ScriptedHost(steps={"s": lambda req: 1 / 0}), ScriptedHost(checks={"c": lambda n, k, e: 1 / 0})):
        res = go(wf(("s", leaf("w", [chk("c")]))), host)
        assert res.status == "error" and res.errors[0].startswith("s: host: ZeroDivisionError")


def test_b4_non_utf8_output_of_a_bin_program_is_decoded_with_replacement(org):
    _script(org / "bin" / "bad", "printf '\\377\\376ok'\n")
    res = go(wf(("s", leaf("bad"))), ProcessHost(str(org)))
    assert res.status == "success", res.errors
    assert res.output.endswith("ok") and "�" in res.output


def test_b4_an_event_with_values_json_cannot_hold_does_not_crash_the_run():
    doc = wf(("join", _plain_gate(after={"seconds": 5}, type_="org.ping")))
    res = go(doc, ScriptedHost(events=[(1, event("org.ping", {"x": {1, 2}}, signature=None))]))
    assert res.errors[0] == "join: timeout"


def test_b4_killpg_on_an_already_gone_process_group_is_not_a_crash(org, monkeypatch):
    _script(org / "bin" / "slow", "sleep 30\n")
    real = os.killpg

    def killpg(pid, sig):
        real(pid, sig)
        raise ProcessLookupError
    monkeypatch.setattr(os, "killpg", killpg)
    doc = wf(("s", dict(leaf("slow"), timeout={"after": {"seconds": 1}})))
    assert go(doc, ProcessHost(str(org))).errors[0] == "s: timeout"


def test_b4_shape_errors_without_validation_are_located_run_errors():
    res = go(wf(("g", {"try": [{"bad": leaf("w")}], "catch": {"retry": {"delay": {"seconds": 1}}}})),
             ScriptedHost(steps={"g/bad": StepOutcome(exit_code=1, error="x")}))
    assert res.status == "error" and res.errors[0].startswith("g: ")
    res = go(wf(("e", {"emit": {"event": {"with": "${ [1] }"}}, "metadata": {"org": {"by": "code", "role": "ci", "acceptance": [chk()]}}})))
    assert res.status == "error" and res.errors[0].startswith("e: ")


def test_b5_bin_command_runs_the_verified_file_not_a_path_swapped_after_the_check(org, tmp_path):
    _script(org / "bin" / "w", "echo good\n")
    _script(tmp_path / "evil", "echo evil\n")
    host = ProcessHost(str(org))

    def swap():
        (org / "bin" / "w").unlink()
        (org / "bin" / "w").symlink_to(tmp_path / "evil")
    host.after_verify = swap
    assert go(wf(("s", leaf("w", by="code"))), host).output == "good"


def test_b5_check_script_runs_the_verified_file_not_a_path_swapped_after_the_check(org, tmp_path):
    _script(org / "bin" / "w", "echo 1\n")
    (org / "checks" / "x.py").write_text("import sys\nsys.exit(0)\n")
    (tmp_path / "evil.py").write_text("import sys\nsys.exit(1)\n")
    host = ProcessHost(str(org))

    def swap():
        (org / "checks" / "x.py").unlink()
        (org / "checks" / "x.py").symlink_to(tmp_path / "evil.py")
    host.after_verify = swap
    assert go(wf(("s", leaf("w", [chk("x")], by="code"))), host).status == "success"


def _two_batches():
    def batch(label, n, until):
        return [{f"units{label}": {"for": {"each": "i", "in": list(range(n))}, "do": [{f"u{label}": _detached()}]}},
                {f"join{label}": _plain_gate(until)}]
    items = batch("a", 3, "${ ($events | length) == 3 }") + batch("b", 2, "${ ($events | length) == 2 }")
    return wf(("fan", {"do": items}))


def test_b6_a_second_join_does_not_replay_events_an_earlier_join_consumed():
    res = go(_two_batches())
    assert res.status == "success", res.errors
    last = [e for e in kinds(res, "until") if e["key"] == "fan/joinb"][-1]
    assert sorted(last["tasks"]) == ["fan/unitsb/ub#0", "fan/unitsb/ub#1"]
    assert last["events"] == 2


def test_b6_three_units_that_end_at_once_are_each_counted_once():
    res = _fanout_run(3)
    last = kinds(res, "until")[-1]
    assert last["events"] == 3 and len(set(last["tasks"])) == 3


def test_r35_join_replays_both_events_of_units_that_ended_before_it_started_listening():
    res = _fanout_run(2)
    assert [(e["events"], e["result"]) for e in kinds(res, "until")] == [(0, False), (1, False), (2, True)]
    assert [e["t"] for e in res.events if e["kind"] == "task-end" and e["key"] == "fan/join"] == [0.0]


# ---- should-fix


def test_s1_a_floor_that_a_try_handled_still_ends_the_run_in_error():
    doc = wf(("g", {"try": [{"fl": leaf("fl", [chk("x")], floor=True)}], "catch": {}}))
    res = go(doc, ScriptedHost(checks={"x": False}))
    assert res.status == "error" and "g/fl: acceptance failed" in res.errors


def test_s1_a_floor_in_a_losing_compete_branch_ends_the_run_in_error():
    doc = wf(("race", {"fork": {"compete": True, "branches": [{"a": leaf("a")}, {"b": leaf("b", [chk()], floor=True)}]}}))
    res = go(doc, ScriptedHost(steps={"race/a": StepOutcome(duration=1), "race/b": StepOutcome(duration=9)}))
    assert res.status == "error" and "race/b: acceptance failed" in res.errors


def test_s1_catalog_without_manifest_or_the_reverse_is_a_usage_error():
    with pytest.raises(ValueError):
        Interpreter({"t": wf(("a", leaf()))}, ScriptedHost(), catalog=CAT)
    with pytest.raises(ValueError):
        Interpreter({"t": wf(("a", leaf()))}, ScriptedHost(), manifest=MAN)


def test_s2_a_failed_detached_unit_of_an_earlier_round_reports_nothing():
    doc = _rework([{"bg": _detached()}, {"pause": {"wait": {"seconds": 5}}}], n=2)
    host = ScriptedHost(steps={"rework/bg": [StepOutcome(exit_code=1, error="x", duration=1), StepOutcome()]})
    res = go(doc, host)
    assert res.status == "success", res.errors


def test_s3_an_event_emitted_by_a_task_never_reaches_a_decision_gate():
    g = gate(type_="org.sign-off", role="owner", by="human", acceptance=[{"human": "ok"}], after={"seconds": 30})
    sender = {"emit": {"event": {"with": {"type": "org.sign-off", "signature": "owner",
                                          "data": {"task": "fan/g", "decision": "approve"}}}},
              "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}
    doc = wf(("fan", {"fork": {"branches": [{"g": g}, {"sender": sender}]}}))
    res = go(doc)
    assert res.errors[0] == "fan/g: timeout"


def test_s4_agent_run_on_a_code_task_is_refused_at_run_time():
    doc = wf(("a", {"run": {"shell": {"command": "agent-run", "arguments": []}},
                    "metadata": {"org": {"by": "code", "role": "pm", "brief": "briefs/a.md"}}}))
    host = ScriptedHost()
    res = go(doc, host)
    assert res.errors[0] == "a: metadata.org.by: agent-run may not run as by code"
    assert not any(c[0] == "step" for c in host.calls)


def test_s5_a_decision_with_a_non_string_reason_is_ignored():
    forged = event("org.owner-decided", {"run": RID, "task": "merge-gate", "decision": "reject", "reason": 5})
    res = go(_gate_doc(), ScriptedHost(events=[(5, forged)]))
    assert kinds(res, "ignored")[0]["reason"] == "data.reason must be a string"
    assert res.errors[0] == "merge-gate: timeout"


def test_s6_the_environment_cannot_override_runtime_variables(org):
    _script(org / "bin" / "env", 'echo "$PATH|$ORG_RUN|$FOO"\n')
    task = leaf("env")
    task["run"]["shell"]["environment"] = {"FOO": "bar", "PATH": "/evil", "ORG_RUN": "x"}
    res = go(wf(("s", task)), ProcessHost(str(org)))
    assert res.output == f"{os.environ['PATH']}|{RID}|bar"


@pytest.mark.parametrize("name", ["LD_PRELOAD", "DYLD_INSERT_LIBRARIES", "lower", "A-B", "1X"])
def test_s6_unsafe_environment_names_are_refused(org, name):
    _script(org / "bin" / "env", "echo hi\n")
    task = leaf("env")
    task["run"]["shell"]["environment"] = {name: "x"}
    res = go(wf(("s", task)), ProcessHost(str(org)))
    assert res.errors[0] == f"s: run.shell.environment: '{name}' is not an allowed name"


def test_s7_a_fifo_a_directory_or_a_nul_never_hangs_or_raises(org):
    os.mkfifo(org / "briefs" / "f.md")

    def hang(*a):
        raise AssertionError("os.open blocked on a FIFO")
    signal.signal(signal.SIGALRM, hang)
    signal.alarm(5)
    try:
        host = ProcessHost(str(org))
        assert host.confined("briefs/f.md") is False
        assert host.confined("briefs") is False
        assert host.confined("briefs/a\0.md") is False
    finally:
        signal.alarm(0)


def test_s8_a_command_must_be_a_file_directly_under_bin(org):
    _script(org / "bin" / "sub" / "x", "echo hi\n")
    _script(org / "checks" / "x", "echo hi\n")
    for cmd in ("sub/x", "../checks/x", "sub"):
        res = go(wf(("s", leaf(cmd))), ProcessHost(str(org)))
        assert res.errors[0] == f"s: run.shell.command: '{cmd}' is not agent-run or a file in bin/"


def test_s8_a_check_name_must_be_kebab_case_and_name_a_file_directly_under_checks(org):
    _script(org / "bin" / "w", "echo 1\n")
    (org / "checks" / "sub").mkdir()
    (org / "checks" / "sub" / "x.py").write_text("")
    (org / "checks" / "evil.py").write_text("")
    for name in ("sub/x", "sub/../evil", "../checks/evil", "Evil"):
        res = go(wf(("s", leaf("w", [chk(name)], by="code"))), ProcessHost(str(org)))
        assert res.errors == ["s: acceptance failed"], name


def test_s9_detached_work_started_in_a_losing_compete_branch_is_cancelled_with_it():
    b = {"do": [{"bg": _detached()}, {"slow": leaf("slow")}]}
    doc = wf(("race", {"fork": {"compete": True, "branches": [{"a": leaf("a")}, {"b": b}]}}))
    host = ScriptedHost(steps={"race/a": StepOutcome(duration=1), "race/b/bg": StepOutcome(duration=100),
                               "race/b/slow": StepOutcome(duration=50)})
    res = go(doc, host)
    assert res.statuses["race/b/bg"] == "cancelled" and res.statuses["race/b/slow"] == "cancelled"
    assert res.now == 1 and res.status == "success"


def test_s10_a_temp_directory_inside_the_org_root_is_refused(org, monkeypatch):
    (org / "tmpdir").mkdir()
    monkeypatch.setenv("TMPDIR", str(org / "tmpdir"))
    monkeypatch.setattr(tempfile, "tempdir", None)
    host = ScriptedHost(root=str(org))
    res = go(wf(("a", _agent())), host)
    assert res.errors[0].startswith("a: input file directory ") and res.errors[0].endswith("is inside the org root")
    assert not any(c[0] == "step" for c in host.calls)


def test_s11_step_output_is_capped_and_marked_truncated(org):
    _script(org / "bin" / "big", "head -c 5000 /dev/zero | tr '\\0' a\n")
    host = ProcessHost(str(org), output_cap=1000)
    out = host.run_step(it.StepRequest(key="s", command="big", argv=["big"], run_id=RID, input=None))
    assert len(out.stdout) == 1000 and out.truncated is True


def test_s11_nested_for_multiplication_is_capped_per_run():
    doc = wf(("outer", {"for": {"each": "i", "in": "${ . }"},
                        "do": [{"inner": {"for": {"each": "j", "in": "${ $input }"}, "do": [{"x": {"set": {"k": 1}}}]}}]}))
    inner_in = list(range(200))
    doc["do"][0]["outer"]["do"][0]["inner"]["for"]["in"] = inner_in
    res = go(doc, input=list(range(200)))
    assert res.status == "error" and any("iteration cap" in e for e in res.errors)


# ---- nits


def test_the_sampling_draw_is_compared_as_integers():
    assert it.drawn(2**64 - 1, 1) is True  # float division would give 1.0, and 1.0 < 1 is False
    assert it.drawn(0, 0.2) is True
    assert it.drawn(int(0.2 * 2**64) + 1, 0.2) is False


def test_a_deadlock_closes_its_work_before_run_end_and_appends_nothing_after_it():
    doc = wf(("g", {"listen": {"to": {"one": {"with": {"type": "org.never"}}}},
                    "metadata": {"org": {"by": "code", "role": "lead", "acceptance": [chk()]}}}))
    res = go(doc)
    assert any("deadlock" in e for e in res.errors)
    assert res.events[-1]["kind"] == "run-end"
    n = len(res.events)
    gc.collect()
    assert len(res.events) == n and res.events[-1]["kind"] == "run-end"


def test_an_owner_judged_rubric_without_a_task_timeout_waits_seven_days_not_one_hour():
    doc = wf(("review", leaf("work", [{"rubric": "criteria/r.md", "judge": "owner"}], role="reviewer")))
    ev = [(2 * 3600, decision("review", item=0, type_="org.owner-review"))]
    assert go(doc, ScriptedHost(events=ev)).status == "success"
    res = go(doc, ScriptedHost())
    assert res.errors[0] == "review: timeout" and res.now == 7 * 86400


def test_exit_inside_a_for_body_leaves_the_loop():
    doc = wf(("loop", {"for": {"in": [1, 2, 3]}, "do": [{"a": dict(leaf("a"), then="exit")}, {"b": leaf("b")}]}))
    res = go(doc)
    assert len(starts(res, "loop/a#0")) == 1 and not starts(res, "loop/a#1") and not starts(res, "loop/b#0")


def test_then_to_a_sibling_branch_inside_a_fork_is_a_located_run_error():
    doc = wf(("par", {"fork": {"branches": [{"a": dict(leaf("a"), then="b")}, {"b": leaf("b")}]}}))
    res = go(doc)
    assert res.errors[0] == "par/a: then: 'b' is not a later task in the same list"


def test_retry_limit_duration_bounds_the_whole_retry_sequence():
    doc = wf(("g", {"try": [{"flaky": leaf("flaky")}],
                    "catch": {"retry": {"limit": {"attempt": {"count": 10}, "duration": {"seconds": 12}}, "delay": {"seconds": 5}}}}))
    res = go(doc, ScriptedHost(steps={"g/flaky": StepOutcome(exit_code=1, error="x")}))
    assert len(starts(res, "g/flaky")) == 3  # attempts at 0, 5 and 10; a fourth at 15 would pass the 12 second limit


def test_retry_attempt_duration_bounds_each_attempt():
    doc = wf(("g", {"try": [{"slow": leaf("slow")}],
                    "catch": {"retry": {"limit": {"attempt": {"count": 1, "duration": {"seconds": 3}}}}}}))
    res = go(doc, ScriptedHost(steps={"g/slow": StepOutcome(duration=10)}))
    assert [e["t"] for e in kinds(res, "accept") if e["key"] == "g/slow"] == [3.0, 6.0]


def test_a_failure_of_an_earlier_attempt_is_handled_when_a_retry_later_succeeds():
    skip_after_fail = dict(leaf("a"), **{"if": '${ $accepted["g/a"] != false }'})
    doc = wf(("g", {"try": [{"a": skip_after_fail}, {"b": leaf("b")}],
                    "catch": {"retry": {"limit": {"attempt": {"count": 2}}}}}))
    host = ScriptedHost(steps={"g/a": StepOutcome(exit_code=1, error="x")})
    res = go(doc, host)
    assert res.statuses["g/a"] == "handled" and res.status == "success", res.errors


def test_the_check_timeout_is_a_parameter_and_a_timed_out_check_is_a_fail(org):
    _script(org / "bin" / "w", "echo 1\n")
    (org / "checks" / "slow.py").write_text("import time\ntime.sleep(30)\n")
    t0 = time.monotonic()
    res = go(wf(("s", leaf("w", [chk("slow")], by="code"))), ProcessHost(str(org), check_timeout=1))
    assert res.errors == ["s: acceptance failed"] and time.monotonic() - t0 < 10


@pytest.mark.parametrize("bad", ["short", "has space!!", "x" * 65, "../etc/passwd1"])
def test_a_caller_supplied_run_id_must_match_the_id_pattern(bad):
    with pytest.raises(ValueError):
        Interpreter({"t": wf(("a", leaf()))}, ScriptedHost()).run("t", run_id=bad)


def test_agent_run_without_a_role_is_a_run_error_not_a_type_error():
    doc = wf(("a", {"run": {"shell": {"command": "agent-run", "arguments": []}},
                    "metadata": {"org": {"by": "model", "brief": "briefs/a.md"}}}))
    assert go(doc).errors[0] == "a: metadata.org.role: required for agent-run"


# ---- spec update 6: the evidence file


def test_r36_shape_check_on_a_model_step_sees_the_agents_output_only_as_output_and_outputs():
    doc = wf(("spec", leaf("w", [chk("probe")], by="model")))
    res, seen = _evidence_of(None, doc, steps={"spec": StepOutcome(stdout='{"id": 1}')})
    (key, ev), = seen
    assert ev["output"] == {"exit": 0, "stdout": '{"id": 1}'}
    assert "spec" not in ev["steps"]


def test_r37_allowed_rungs_follow_the_role_rungs_default_and_owner(org):
    (org / "bin" / "noop").write_text("#!/bin/sh\necho 1\n")
    (org / "bin" / "noop").chmod(0o755)
    out = org.parent / "rungs.txt"
    (org / "checks" / "every-proposal-is-within-its-rung.py").write_text(
        f"import os\nopen({str(out)!r}, 'w').write(os.environ['ORG_ALLOWED_RUNGS'])\n")
    wfs = {"improve": improve_doc()}
    go(wfs, ProcessHost(str(org)), catalog=CAT, manifest=MAN)
    assert out.read_text() == "free,ordinary"
    man = copy.deepcopy(MAN)
    man["roles"]["improver"]["rungs"] = ["free"]
    go(wfs, ProcessHost(str(org)), catalog=CAT, manifest=man)
    assert out.read_text() == "free"
    g = gate(acceptance=[chk("every-proposal-is-within-its-rung")])
    go(wf(("gate", g)), ProcessHost(str(org), events=[(1, decision("gate"))], verify=lambda e, s: True))
    assert out.read_text() == "free,ordinary,protected,frozen"


def test_r38_call_and_emit_entries_appear_in_steps_and_the_call_entry_holds_exit_zero_or_one():
    child_ok = wf(("w", leaf("w")), name="ok")
    child_bad = wf(("w", leaf("w", [chk("bad")])), name="bad")
    emit = {"emit": {"event": {"with": {"type": "org.report", "data": {"n": 1}}}},
            "metadata": {"org": {"by": "code", "role": "ci", "acceptance": [chk()]}}}
    root = wf(("report", emit), ("good", _call("ok")), ("broken", _call("bad")), ("merge", leaf("w", [chk("probe")], by="model")), name="root")
    seen = []
    host = ScriptedHost(checks={"bad": False, "probe": lambda n, k, e: seen.append(e) or True})
    go({"root": root, "ok": child_ok, "bad": child_bad}, host, name="root")
    steps = seen[0]["steps"]
    assert steps["report"]["exit"] == 0 and json.loads(steps["report"]["stdout"]) == {"n": 1, "run": RID}
    assert steps["good"] == {"exit": 0, "stdout": ""}
    assert steps["broken"] == {"exit": 1, "stdout": ""}


def test_r39_change_carries_the_vcs_head_and_the_working_tree():
    doc = wf(("improve", leaf("w", [chk("probe")], role="improver")))
    res, seen = _evidence_of(None, doc, change={"head": "abc123", "worktree": "/work/tree"})
    assert seen[0][1]["change"] == {"head": "abc123", "worktree": "/work/tree"}


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_process_host_change_reads_the_git_head_and_worktree(org):
    run = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=org, check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    (org / "f").write_text("x")
    run("add", "f")
    run("commit", "-q", "-m", "m")
    ch = ProcessHost(str(org)).change()
    assert len(ch["head"]) == 40 and os.path.realpath(ch["worktree"]) == os.path.realpath(str(org))


def test_r40_judge_input_holds_item_output_and_the_current_rounds_evidence():
    seen = []

    def judge(req):
        seen.append(json.loads(Path(req.input_file).read_text()))
        return {"invocation": req.invocation, "type": "org.rubric-verdict",
                "data": {"run": req.run_id, "task": req.key, "item": req.item, "verdict": "pass"}}
    doc = wf(("pre", leaf("w", by="code")),
             ("spec", leaf("w", [chk("c"), {"rubric": "criteria/s.md", "judge": "reviewer"}], by="model")))
    host = ScriptedHost(steps={"pre": StepOutcome(stdout="g"), "spec": StepOutcome(stdout="claim")}, judges={"spec": judge})
    go(doc, host)
    body = seen[0]["input"]
    assert body["item"] == 1 and body["output"] == {"exit": 0, "stdout": "claim"}
    assert body["evidence"]["steps"]["pre"] == {"exit": 0, "stdout": "g"}
    assert body["evidence"]["output"] == body["output"]


def test_r41_decisions_come_from_the_verified_event_never_from_a_step():
    doc = wf(("merge-gate", gate(floor=True)), ("merge", leaf("w", [chk("probe")], by="model")))
    host = ScriptedHost(events=[(5, decision("merge-gate"))], change={"head": "h1", "worktree": "/w"},
                        checks={"probe": lambda n, k, e: seen.append(e) or True})
    seen = []
    go(doc, host)
    assert seen[0]["decisions"]["merge-gate"] == {"decision": "approve", "signer_role": "owner", "signature_verified": True,
                                                  "run": RID, "task": "merge-gate", "head": "h1"}


def test_r41_a_rejected_decision_is_recorded_too_inside_a_rework_loop():
    g = gate(role="lead", by="human", acceptance=[{"human": "ok"}])
    g["metadata"]["org"]["signer"] = "owner"
    seen = []
    doc = _rework([{"approve": g}, {"look": leaf("w", [chk("probe")], by="model")}], n=2, cond='${ $accepted["rework/approve"] != true }')
    host = ScriptedHost(events=[(5, decision("rework/approve", "reject")), (9, decision("rework/approve"))],
                        checks={"probe": lambda n, k, e: seen.append(e["decisions"]["rework/approve"]["decision"]) or True})
    go(doc, host)
    assert seen == ["reject", "approve"]


def test_r42_outputs_carry_an_earlier_models_claim_but_steps_do_not():
    doc = wf(("acceptance-tests", leaf("w", by="model")), ("acceptance-red", leaf("w", [chk("probe")], by="code")))
    res, seen = _evidence_of(None, doc, steps={"acceptance-tests": StepOutcome(stdout='{"tests": ["t1", "t2"]}')})
    ev = seen[0][1]
    assert json.loads(ev["outputs"]["acceptance-tests"]["stdout"]) == {"tests": ["t1", "t2"]}
    assert "acceptance-tests" not in ev["steps"]


# ---- update 7 items (P31 to P40) and fixture-agnostic rule checks


def test_p33_a_decision_event_is_consumed_once_per_run():
    g = gate(role="lead", by="human", acceptance=[{"human": "ok"}])
    g["metadata"]["org"]["signer"] = "owner"
    doc = _rework([{"approve": g}], n=2, cond='${ $accepted["rework/approve"] != true }')
    first = decision("rework/approve", "reject")
    again = copy.deepcopy(first)  # a replay of the same signed event in round 2
    ev = [(5, first), (6, again), (9, decision("rework/approve"))]
    res = go(doc, ScriptedHost(events=ev))
    assert [e["reason"] for e in kinds(res, "ignored")] == ["decision event already consumed"]
    assert [(e["t"], e["status"]) for e in kinds(res, "accept") if e["key"] == "rework/approve"] == [(5, "fail"), (9, "pass")]


def test_p35_a_call_is_a_floor_call_when_a_workflow_it_calls_has_floors():
    leafchild = wf(("fl", leaf("fl", [chk()], floor=True)), name="c")
    middle = wf(("down", _call("c")), name="b")
    root = wf(("each", {"for": {"in": "${ . }"}, "do": [{"c": _call("b")}]}), name="root")
    res = go({"root": root, "b": middle, "c": leafchild}, name="root", input=[])
    assert "each/c: floor-not-run" in res.errors


def test_p36_a_rework_loop_may_name_a_callee_floor_by_its_full_key():
    child = wf(("fl", leaf("fl", [chk("sc")], floor=True)), name="child")
    root = wf(("rework", {"for": {"in": [1, 2]}, "while": '${ $accepted["c>fl"] != true }', "do": [{"c": _call("child")}]}), name="root")
    res = go({"root": root, "child": child}, ScriptedHost(checks={"sc": [False, True]}), name="root")
    assert res.status == "success", res.errors
    assert len(starts(res, "rework/c>fl")) == 2


def test_the_fixture_tdd_unit_runs_to_success_whatever_its_check_layout():
    res = go({"tdd-unit": tdd_doc()}, ScriptedHost(), catalog=CAT, manifest=MAN)
    assert res.status == "success", res.errors
