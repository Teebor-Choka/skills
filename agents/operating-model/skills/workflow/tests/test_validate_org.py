"""Acceptance tests for validate_org, derived from the org-documents spec (section 12.1 and 12.4).

Case ids (W1, W2, ...) are the spec's. Every negative case asserts an exact error prefix.
"""
import copy
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "scripts", "validate_org.py")
FIX = os.path.join(HERE, "fixtures", "validate_org")
sys.path.insert(0, os.path.dirname(SCRIPT))

import validate_org as vo  # noqa: E402


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


SW = _load("sw-development.json")
TDD = _load("tdd-unit.json")
CAT = _load("catalog.json")
MAN = _load("manifest.json")


def find(doc, name):
    """Return the task named `name`, searching every nested task list."""
    stack = [doc["do"]]
    while stack:
        for item in stack.pop():
            (n, t), = item.items()
            if n == name:
                return t
            if isinstance(t.get("do"), list):
                stack.append(t["do"])
            if isinstance(t.get("try"), list):
                stack.append(t["try"])
            if isinstance(t.get("catch"), dict) and isinstance(t["catch"].get("do"), list):
                stack.append(t["catch"]["do"])
            if isinstance(t.get("fork"), dict):
                stack.append(t["fork"]["branches"])
    raise KeyError(name)


def org(d, n):
    return find(d, n)["metadata"]["org"]


def shell(d, n):
    return find(d, n)["run"]["shell"]


def manifest_with(fn):
    m = copy.deepcopy(MAN)
    fn(m)
    return m


MAN_TF = manifest_with(lambda m: m["workflows"]["tdd-unit"].__setitem__("floors", ["red"]))


def append_try(d, retry):
    d["do"].append({"retrying": {"try": [{"inner": {"set": {"a": 1}}}], "catch": {"retry": retry}}})


def gate_type(d, t):
    find(d, "merge-gate")["listen"]["to"]["one"]["with"]["type"] = t


def emit_type(d, t):
    find(d, "report")["emit"]["event"]["with"]["type"] = t


def index_of(d, name):
    return next(i for i, x in enumerate(d["do"]) if name in x)


def w21(d):
    find(d, "units")["do"].append({"align": copy.deepcopy(find(d, "align"))})


def w23(d):
    r = find(d, "merge")["run"]
    r["container"] = {"image": "x"}
    r.pop("shell")


def w40(d):
    find(d, "spec")["then"] = "acceptance-red"
    find(d, "align")["then"] = "design"


def w42(d):
    d["do"].append({"par": {"fork": {"branches": [d["do"].pop(index_of(d, "review"))]}}})


def w54(d):
    i = index_of(d, "spec")
    d["do"][i] = {"wrap": {"if": "${ true }", "do": [d["do"][i]]}}


def w59(d):
    lst = d["do"]
    for i in range(16):
        new = {"n%d" % i: {"do": []}}
        lst.append(new)
        lst = new["n%d" % i]["do"]
    lst.append({"s15": {"set": {"a": 1}}})


def w60(d):
    i = index_of(d, "review")
    rv = d["do"].pop(i)
    d["do"].insert(i, {"stage": {"do": [{"early": {"set": {"a": 1}, "then": "exit"}}, rv]}})


def w69(d):
    deep = []
    for _ in range(134):
        deep = [deep]
    d["do"].append({"deep": {"set": {"a": deep}}})


def w84(d):
    i = index_of(d, "review")
    rest = d["do"][i:]
    del d["do"][i:]
    d["do"].append({"tail": {"do": rest, "then": "end"}})


def w88(kind):
    def f(d):
        lst = d["do"]
        for i in range(15):
            inner = []
            if kind == "fork":
                lst.append({"f%d" % i: {"fork": {"branches": inner}}})
            else:
                lst.append({"t%d" % i: {"try": [{"x%d" % i: {"set": {"a": 1}}}], "catch": {"do": inner}}})
            lst = inner
        lst.append({"leaf": {"set": {"a": {"b": {"c": 1}}}}})
    return f


def join_gate(type_, correlate=None, name="join"):
    one = {"with": {"type": type_}}
    if correlate:
        one["correlate"] = correlate
    return {name: {"listen": {"to": {"one": one}}, "timeout": {"after": {"hours": 1}},
                     "metadata": {"org": {"by": "code", "role": "lead", "metrics": ["escalations"],
                                          "acceptance": [{"check": "workers-done"}]}}}}


def w89(d):
    """Parallel units (7.11): `tdd` does not wait, and a counted plain gate joins them."""
    find(d, "tdd")["run"]["await"] = False
    join = join_gate("org.unit-done")
    gate = join["join"]
    del gate["listen"]["to"]["one"]
    gate["listen"]["to"]["any"] = [{"with": {"type": "org.task-ended"}}]
    gate["listen"]["to"]["until"] = "${ ($events | length) == ($context.units | length) }"
    find(d, "build")["do"].insert(1, join)


def w100(d):
    d["do"].append({"par": {"fork": {"branches": [{"tdd2": copy.deepcopy(find(d, "tdd"))}]}}})


def rework(d):
    spec = d["do"].pop(1)
    align = d["do"].pop(0)
    d["do"].insert(0, {"rework": {"for": {"each": "r", "in": [1, 2, 3]},
                                  "while": '${ $accepted["rework/spec"] != true }', "do": [align, spec]}})


def deep_ok(d):
    lst = d["do"]
    for i in range(15):
        new = {"n%d" % i: {"do": []}}
        lst.append(new)
        lst = new["n%d" % i]["do"]
    lst.append({"s14": {"set": {"a": 1}}})


def w39(d):
    d["schedule"] = {True: d["schedule"].pop("on")}


def w46(d):
    find(d, "merge-gate")["foreach"] = {"do": []}


def w41(d):
    d["do"].insert(2, {"pick": {"switch": [{"skip": {"when": "${ .x }", "then": "end"}},
                                           {"default": {"then": "continue"}}]}})


def w49(d):
    find(d, "align")["emit"] = {"event": {"with": {"type": "x"}}}


def w32(d):
    find(d, "not-accepted").pop("metadata")


def w82(d):
    find(d, "tdd")["if"] = "${ true }"


# (id, base, mutation, expected prefix or None for valid, manifest)
CASES = [
    ("W1", SW, lambda d: org(d, "tdd").__setitem__("flor", True), "build/units/tdd: metadata.org: unknown key 'flor'", MAN),
    ("W2", SW, lambda d: org(d, "align").__setitem__("by", "robot"), "align: metadata.org.by: 'robot' is not one of code, human, model", MAN),
    ("W3", SW, lambda d: find(d, "align")["metadata"].__setitem__("org", ["by", "model"]), "align: metadata.org: must be a map", MAN),
    ("W4", SW, lambda d: org(d, "align").__setitem__("kind", "step"), "align: metadata.org.kind: kind is derived from the task key; do not declare it", MAN),
    ("W5", SW, lambda d: org(d, "align").pop("by"), "align: metadata.org.by: required for kind step", MAN),
    ("W6", SW, lambda d: org(d, "merge-gate").pop("acceptance"), "merge-gate: metadata.org.acceptance: required for kind gate", MAN),
    ("W7", SW, lambda d: org(d, "report").__setitem__("metrics", []), "report: metadata.org.metrics: must not be empty", MAN),
    ("W8", SW, lambda d: find(d, "build").__setitem__("metadata", {"org": {"by": "code"}}), "build: metadata.org.by: not allowed on kind container", MAN),
    ("W9", SW, lambda d: find(d, "units").__setitem__("while", "${ .x }"), "build/units: for: unbounded loop: 'while' needs an inline 'in' array", MAN),
    ("W10", SW, lambda d: append_try(d, {"delay": {"seconds": 1}}), "retrying: catch.retry: needs limit.attempt.count, a positive integer", MAN),
    ("W11", SW, lambda d: org(d, "spec")["acceptance"][1].pop("judge"), "spec: metadata.org.acceptance[1]: rubric needs judge", MAN),
    ("W12", SW, lambda d: org(d, "merge")["acceptance"][0].__setitem__("judge", "lead"), "merge: metadata.org.acceptance[0]: judge needs rubric", MAN),
    ("W13", SW, lambda d: org(d, "merge")["acceptance"][0].__setitem__("human", "x"), "merge: metadata.org.acceptance[0]: exactly one of check, rubric, human", MAN),
    ("W14", SW, lambda d: org(d, "align").__setitem__("metrics", ["escalation"]), "align: metadata.org.metrics: unknown metric 'escalation'", MAN),
    ("W15", SW, lambda d: org(d, "align").__setitem__("role", "pmm"), "align: metadata.org.role: unknown role 'pmm'", MAN),
    ("W16", SW, lambda d: org(d, "spec")["acceptance"][1].__setitem__("judge", "auditor"), "spec: metadata.org.acceptance[1].judge: unknown role 'auditor'", MAN),
    ("W17", SW, lambda d: org(d, "not-accepted").__setitem__("to", "boss"), "not-accepted: metadata.org.to: unknown role 'boss'", MAN),
    ("W18", SW, lambda d: org(d, "review").pop("floor"), "review: listed as a floor in the manifest but floor is not true", MAN),
    ("W19", SW, lambda d: org(d, "align").__setitem__("floor", True), "align: floor is true but the manifest does not list it as a floor", MAN),
    ("W20", SW, lambda d: find(d, "spec").__setitem__("if", "${ true }"), "spec: a floor may not have 'if'", MAN),
    ("W21", SW, w21, "build/units/align: duplicate task name 'align' (first at align)", MAN),
    ("W22", SW, lambda d: d["do"].insert(0, {"fetch": {"call": "http", "with": {"method": "get", "endpoint": "https://x"}}}), "fetch: task 'call' is not in the accepted subset", MAN),
    ("W23", SW, w23, "merge: task 'run.container' is not in the accepted subset", MAN),
    ("W24", SW, lambda d: d.__setitem__("use", {"secrets": ["x"]}), "use: not in the accepted subset", MAN),
    ("W25", SW, lambda d: find(d, "merge").__setitem__("then", "align"), "merge: then: 'align' is not later in the same list; a backward jump is an unbounded loop", MAN),
    ("W26", SW, lambda d: find(d, "design").__setitem__("then", "end"), "design: then: 'end' skips floor 'review'", MAN),
    ("W27", SW, lambda d: find(d, "merge-gate").pop("timeout"), "merge-gate: kind gate needs an inline timeout", MAN),
    ("W28", SW, lambda d: d["document"].__setitem__("name", "sw-dev"), "document.name: workflow 'sw-dev' is not in manifest.workflows", MAN),
    ("W29", SW, lambda d: org(d, "review")["acceptance"][0].__setitem__("sample", True), "review: metadata.org.acceptance[0].sample: must be a number in (0, 1]", MAN),
    ("W30", SW, lambda d: org(d, "review").__setitem__("floor", "yes"), "review: metadata.org.floor: must be true or false", MAN),
    ("W31", SW, lambda d: org(d, "not-accepted").__setitem__("by", "code"), "not-accepted: metadata.org.by: not allowed on kind escalation", MAN),
    ("W32", SW, w32, "not-accepted: metadata.org.to: required for kind escalation", MAN),
    ("W33", SW, lambda d: shell(d, "align").__setitem__("arguments", ["--role", "pm"]), "align: run.shell.arguments: --role is set by the runtime from metadata.org; remove it", MAN),
    ("W34", SW, lambda d: find(d, "improve")["run"]["workflow"].__setitem__("name", "improver"), "improve: run.workflow: workflow 'org/improver' is not in manifest.workflows", MAN),
    ("W35", SW, lambda d: org(d, "review").__setitem__("sample", 0.1), "review: metadata.org: unknown key 'sample'", MAN),
    ("W36", SW, lambda d: find(d, "align")["metadata"].__setitem__("orgs", {}), "align: metadata: unknown namespace 'orgs'; only 'org' is allowed", MAN),
    ("W37", SW, lambda d: d["document"]["metadata"]["org"].__setitem__("policy", ["tracker"]), "document.metadata.org.policy: must be a list of dotted names like vcs.remote", MAN),
    ("W38", SW, lambda d: d["do"].append({"Report_2": {"set": {"x": 1}}}), "Report_2: task name must be kebab-case", MAN),
    ("W39", SW, w39, "schedule: key True is not a string (YAML 1.1 reads on, off, yes and no as booleans; quote it)", MAN),
    ("W40", SW, w40, "align: then: 'design' skips floor in 'spec'", MAN),
    ("W41", SW, w41, "pick: switch[0].skip.then: 'end' skips floor 'review'", MAN),
    ("W42", SW, w42, "par/review: a floor may not sit inside fork or try 'par'", MAN),
    ("W43", SW, lambda d: d.__setitem__("schedule", {"cron": "0 0 * * *"}), "schedule.cron: not in the accepted subset", MAN),
    ("W44", SW, lambda d: find(d, "spec")["output"]["schema"]["resource"].__setitem__("endpoint", "https://x/item.json"), "spec: output.schema.resource.endpoint: must be a relative path under schemas/ ending .json", MAN),
    ("W45", SW, lambda d: d["document"]["metadata"]["org"].__setitem__("stack", "x"), "document.metadata.org: unknown key 'stack'", MAN),
    ("W46", SW, w46, "merge-gate: foreach: not in the accepted subset", MAN),
    ("W47", SW, lambda d: find(d, "not-accepted").__setitem__("then", "end"), None, MAN),
    ("W48", SW, lambda d: find(d, "align").__setitem__("kind", "step"), "align: kind is derived from the task key; do not declare it", MAN),
    ("W49", SW, w49, "align: not one OWS task; found task keys ['emit', 'run']", MAN),
    ("W50", SW, lambda d: find(d, "merge")["run"].__setitem__("workflow", {"namespace": "org", "name": "improve"}), "merge: run: needs exactly one of container, script, shell, workflow", MAN),
    ("W51", SW, lambda d: org(d, "align").__setitem__("metrics", ["escalations", "escalations"]), "align: metadata.org.metrics: duplicate metric", MAN),
    ("W52", SW, lambda d: find(d, "merge").__setitem__("then", "nowhere"), "merge: then: 'nowhere' is not a task in the same list", MAN),
    ("W53", SW, lambda d: find(d, "review")["run"].__setitem__("await", False), "review: a floor may not have run.await: false", MAN),
    ("W54", SW, w54, "wrap/spec: a floor may not sit inside 'wrap', which has 'if'", MAN),
    ("W55", SW, lambda d: find(d, "merge-gate").__setitem__("timeout", "gate-timeout"), "merge-gate: timeout: a named timeout needs 'use', which is refused; write it inline", MAN),
    ("W56", SW, lambda d: append_try(d, "default"), "retrying: catch.retry: a named retry policy needs 'use', which is refused; write it inline", MAN),
    ("W57", SW, lambda d: d.__setitem__("evaluate", {"mode": "loose"}), "evaluate.mode: not in the accepted subset", MAN),
    ("W58", SW, lambda d: d["document"].__setitem__("namespace", "acme"), "document.namespace: 'acme' differs from manifest namespace", MAN),
    ("W59", SW, w59, "n0/n1/n2/n3/n4/n5/n6/n7/n8/n9/n10/n11/n12/n13/n14/n15/s15: nesting deeper than 16 task lists", MAN),
    ("W60", SW, w60, "stage/early: then: 'exit' skips floor in 'stage/review'", MAN),
    ("W61", SW, lambda d: shell(d, "align").__setitem__("arguments", ["--brief=briefs/align.md"]), "align: run.shell.arguments: --brief is set by the runtime from metadata.org; remove it", MAN),
    ("W62", SW, lambda d: find(d, "improve")["run"]["workflow"].__setitem__("name", "sw-development"), "improve: run.workflow: a workflow may not call itself", MAN),
    ("W63", SW, lambda d: d.__setitem__("export", {"as": "x"}), "export: unknown top-level key", MAN),
    ("W64", SW, lambda d: shell(d, "align").__setitem__("arguments", ["--role=pm"]), "align: run.shell.arguments: --role is set by the runtime from metadata.org; remove it", MAN),
    ("W65", SW, lambda d: shell(d, "align").__setitem__("arguments", ["--verbose"]), "align: run.shell.arguments: '--verbose' is not an allowed agent-run flag (allowed: --isolated)", MAN),
    ("W66", SW, lambda d: shell(d, "align").__setitem__("command", "./agent-run"), "align: run.shell.command: must be a bare command name with no path, space or arguments", MAN),
    ("W67", SW, lambda d: org(d, "align").__setitem__("by", 1), "align: metadata.org.by: 1 is not one of code, human, model", MAN),
    ("W68", SW, lambda d: find(d, "not-accepted")["raise"].__setitem__("error", "acceptance-not-met"), "not-accepted: raise.error: a named error needs 'use', which is refused; write it inline", MAN),
    ("W69", SW, w69, "do[13].deep.set.a" + "[0]" * 123 + ": value nested deeper than 128 levels", MAN),
    ("W70", SW, lambda d: org(d, "spec")["acceptance"][0].__setitem__("check", "Spec_OK"), "spec: metadata.org.acceptance[0].check: must be a kebab-case check name", MAN),
    ("W71", SW, lambda d: org(d, "review")["acceptance"][0].__setitem__("sample", 0.5), "review: metadata.org.acceptance[0].sample: a floor item must be judged every run; remove sample", MAN),
    ("W72", SW, lambda d: org(d, "merge-gate").__setitem__("by", "model"), "merge-gate: metadata.org.by: role owner requires by human", MAN),
    ("W73", SW, lambda d: emit_type(d, "org.owner-decided"), "report: emit.event.with.type: 'org.owner-decided' uses the reserved prefix org.owner-", MAN),
    ("W74", SW, lambda d: emit_type(d, "${ .t }"), "report: emit.event.with.type: must be a literal event type", MAN),
    ("W75", SW, lambda d: gate_type(d, "org.run-reported"), "report: emit.event.with.type: 'org.run-reported' is listened on by gate 'merge-gate'", MAN),
    ("W76", SW, lambda d: shell(d, "merge").__setitem__("command", "sh"), "merge: run.shell.command: 'sh' is a shell or wrapper and is refused", MAN),
    ("W77", SW, lambda d: shell(d, "merge").__setitem__("command", "agent-run --role owner"), "merge: run.shell.command: must be a bare command name with no path, space or arguments", MAN),
    ("W78", SW, lambda d: None, "document.name: workflow 'sw-development' is not in manifest.workflows",
     manifest_with(lambda m: m.__setitem__("workflows", "sw-development tdd-unit improve"))),
    ("W79", SW, lambda d: find(d, "merge-gate")["timeout"].__setitem__("after", {"seconds": 0}), "merge-gate: timeout.after: duration must be greater than zero", MAN),
    ("W80", SW, lambda d: find(d, "merge-gate")["timeout"].__setitem__("after", "${ .t }"), "merge-gate: timeout.after: duration must be a literal map of days, hours, minutes, seconds, milliseconds", MAN),
    ("W81", TDD, lambda d: d["do"].insert(0, {"pause": {"wait": "PT5S"}}), "pause: wait: duration must be a literal map of days, hours, minutes, seconds, milliseconds", MAN),
    ("W82", SW, w82, "build/units/tdd: a call to a workflow with floors may not have 'if'", MAN_TF),
    ("W83", SW, lambda d: find(d, "design").__setitem__("then", "end"), "design: then: 'end' skips floor 'tdd'", MAN_TF),
    ("W84", SW, w84, None, MAN),
    ("W85", SW, lambda d: find(d, "merge").__setitem__("then", 5), "merge: then: must be a string", MAN),
    ("W86", SW, lambda d: org(d, "align").__setitem__("brief", "briefs/a\x01.md"), "align: metadata.org.brief: must be a relative path under briefs/ ending .md", MAN),
    ("W87", SW, lambda d: find(d, "spec").__setitem__("timeout", {"after": {"minutes": -1}}), "spec: timeout.after: duration must be a literal map", MAN),
    ("W88-fork", SW, w88("fork"), None, MAN),
    ("W88-try", SW, w88("try"), None, MAN),
    ("W89", SW, w89, None, MAN),
    ("W90", SW, lambda d: find(d, "units")["for"].__setitem__("each", "accepted"), "build/units: for.each: 'accepted' is a reserved variable name", MAN),
    ("W91", SW, lambda d: org(d, "align").update({"role": "owner", "by": "human"}), "align: metadata.org.role: agent-run may not run as owner", MAN),
    ("W92", SW, lambda d: org(d, "align").pop("brief"), "align: metadata.org.brief: required for agent-run", MAN),
    ("W93", SW, lambda d: shell(d, "align").__setitem__("stdin", "x"), "align: run.shell.stdin: not allowed on agent-run; the runtime sets it", MAN),
    ("W94", SW, lambda d: shell(d, "align").__setitem__("environment", {"ROLE": "owner"}), "align: run.shell.environment: not allowed on agent-run; the runtime sets it", MAN),
    ("W95", SW, lambda d: shell(d, "review").__setitem__("arguments", ["--isolated", "--isolated"]), "review: run.shell.arguments: --isolated given more than once", MAN),
    ("W96", SW, lambda d: find(d, "merge-gate")["listen"].__setitem__("to", {"any": [{"with": {"type": "org.owner-decided"}}]}), "merge-gate: listen.to: a decision gate listens with to.one only", MAN),
    ("W97", SW, lambda d: gate_type(d, "${ .t }"), "merge-gate: listen.to.one.with.type: must be a literal event type", MAN),
    ("W98", SW, lambda d: d["schedule"]["on"]["one"]["with"].__setitem__("type", "${ .t }"), "schedule.on: event filter 0 needs a literal with.type", MAN),
    ("W99", SW, lambda d: org(d, "align")["acceptance"].append({"human": "pm agrees"}), "align: metadata.org.acceptance[1]: a human item is allowed only on a gate", MAN),
    ("W100", SW, w100, "par/tdd2: a call to a workflow with floors may not sit inside fork or try 'par'", MAN_TF),
    ("W101", SW, lambda d: find(d, "tdd")["run"].__setitem__("await", False), "build/units/tdd: a call to a workflow with floors may not have run.await: false", MAN_TF),
    ("W102", SW, lambda d: append_try(d, {"limit": {"attempt": {"count": 101}}}), "retrying: catch.retry: limit.attempt.count must be at most 100", MAN),
    ("W103", SW, lambda d: find(d, "merge-gate")["timeout"].__setitem__("after", {"days": 31}), "merge-gate: timeout.after: duration must be at most 30 days", MAN),
    ("W104", SW, lambda d: d["do"].append(join_gate("org.unit-done", {"unit": {"from": "${ .unit }"}}, name="join2")), None, MAN),
    ("W105", SW, lambda d: None, "manifest: workflows.sw-development.floors: floor 'ghost' is not a task in the workflow",
     manifest_with(lambda m: m["workflows"]["sw-development"]["floors"].append("ghost"))),
    ("W106", SW, lambda d: find(d, "merge-gate")["timeout"].__setitem__("after", {"days": 30}), None, MAN),
    # positive controls named in the spec after the table
    ("P-then-improve", SW, lambda d: find(d, "merge").__setitem__("then", "improve"), None, MAN),
    ("P-wait-first", TDD, lambda d: d["do"].insert(0, {"pause": {"wait": {"seconds": 5}}}), None, MAN),
    ("P-rework-floor", SW, rework, None, MAN),
    ("P-isolated", SW, lambda d: shell(d, "align").__setitem__("arguments", ["--isolated"]), None, MAN),
    ("P-depth-16", SW, deep_ok, None, MAN),
]


@pytest.mark.parametrize("cid,base,mut,prefix,man", CASES, ids=[c[0] for c in CASES])
def test_spec_case(cid, base, mut, prefix, man):
    d = copy.deepcopy(base)
    mut(d)
    errs = vo.validate_org(d, CAT, man)
    if prefix is None:
        assert errs == []
    else:
        assert any(e.startswith(prefix) for e in errs), (prefix, errs)


# ---------------------------------------------------------------- acceptance 10: the examples pass

def test_examples_pass():
    assert vo.validate_org(copy.deepcopy(SW), CAT, MAN) == []
    assert vo.validate_org(copy.deepcopy(TDD), CAT, MAN) == []


def test_example_counts_match_spec_section_4():
    sw_kinds = _kinds(SW)
    assert sw_kinds == {"step": 9, "call": 2, "gate": 1, "emit": 1, "escalation": 1, "container": 2}
    assert _kinds(TDD) == {"step": 6, "escalation": 1, "container": 1}


def _kinds(doc):
    out = {}

    def walk(lst):
        for item in lst:
            (_, t), = item.items()
            if "for" in t or ("do" in t and "run" not in t):
                k = "container"
            elif "run" in t:
                k = "step" if "shell" in t["run"] else "call"
            else:
                k = {"listen": "gate", "emit": "emit", "raise": "escalation"}[next(x for x in ("listen", "emit", "raise") if x in t)]
            out[k] = out.get(k, 0) + 1
            if isinstance(t.get("do"), list):
                walk(t["do"])
    walk(doc["do"])
    return out


# ---------------------------------------------------------------- acceptance 1: every nested list is walked

BAD_STEP = {"bad": {"run": {"shell": {"command": "tdd-evidence"}}}}
NESTINGS = {
    "do": ({"c": {"do": [BAD_STEP]}}, "c/bad"),
    "for.do": ({"c": {"for": {"each": "x", "in": [1]}, "do": [BAD_STEP]}}, "c/bad"),
    "fork.branches": ({"c": {"fork": {"branches": [BAD_STEP]}}}, "c/bad"),
    "try.try": ({"c": {"try": [BAD_STEP], "catch": {}}}, "c/bad"),
    "try.catch.do": ({"c": {"try": [{"ok": {"set": {"a": 1}}}], "catch": {"do": [BAD_STEP]}}}, "c/bad"),
}


@pytest.mark.parametrize("where", sorted(NESTINGS))
def test_error_inside_each_nested_task_list_is_found(where):
    task, path = NESTINGS[where]
    d = copy.deepcopy(TDD)
    d["do"].append(copy.deepcopy(task))
    errs = vo.validate_org(d, CAT, MAN)
    assert f"{path}: metadata.org.by: required for kind step" in errs, errs


# ---------------------------------------------------------------- never raises on any JSON value

GARBAGE = [None, True, 0, 1.5, "x", [], {}, [None], {"do": "x"}, {"do": [1]}, {"do": [{}]}, {"do": [{"a": 1}]},
           {"do": [{"a": {}}]}, {"do": [{"a": {"run": 1}}]}, {"do": [{"a": {"run": {"shell": 1}}}]},
           {"do": [{"a": {"run": {"shell": {"command": 1, "arguments": "x"}}}}]},
           {"do": [{"a": {"for": 1, "do": 2}}]}, {"do": [{"a": {"try": 1, "catch": 2}}]},
           {"do": [{"a": {"fork": 1}}]}, {"do": [{"a": {"switch": 1, "then": []}}]},
           {"do": [{"a": {"listen": 1, "timeout": []}}]}, {"do": [{"a": {"emit": []}}]},
           {"do": [{"a": {"raise": []}}]}, {"do": [{"a": {"wait": []}}]},
           {"do": [{"a": {"set": 1, "metadata": {"org": {"acceptance": [1, [], {"rubric": []}]}}}}]},
           {"document": [], "schedule": 1, "evaluate": 1, "timeout": 1, "do": []},
           {"document": {"name": [], "metadata": 1}, "do": []}]


@pytest.mark.parametrize("doc", GARBAGE, ids=[str(i) for i in range(len(GARBAGE))])
@pytest.mark.parametrize("cat,man", [(CAT, MAN), (None, None), ([], "x"), ({"a": 1}, {"workflows": [], "roles": 3})],
                         ids=["real", "none", "list-str", "odd"])
def test_never_raises(doc, cat, man):
    errs = vo.validate_org(copy.deepcopy(doc), cat, man)
    assert isinstance(errs, list) and all(isinstance(e, str) for e in errs)


def test_non_map_workflow_gives_only_the_root_error():
    assert vo.validate_org([], CAT, MAN) == ["(root): workflow must be a map"]


def _reverse_keys(v):
    if isinstance(v, dict):
        return {k: _reverse_keys(x) for k, x in reversed(list(v.items()))}
    if isinstance(v, list):
        return [_reverse_keys(x) for x in v]
    return v


def test_deterministic():
    d = copy.deepcopy(SW)
    org(d, "align")["by"] = "robot"
    org(d, "spec")["metrics"] = ["nope"]
    find(d, "merge")["then"] = "align"
    org(d, "report")["acceptance"] = []
    first = vo.validate_org(copy.deepcopy(d), CAT, MAN)
    assert len(first) >= 4
    assert vo.validate_org(copy.deepcopy(d), CAT, MAN) == first
    # key order is not part of the contract, but the set of errors is
    assert sorted(vo.validate_org(_reverse_keys(d), CAT, MAN)) == sorted(first)


def test_does_not_mutate_inputs():
    d, c, m = copy.deepcopy(SW), copy.deepcopy(CAT), copy.deepcopy(MAN)
    vo.validate_org(d, c, m)
    assert (d, c, m) == (SW, CAT, MAN)


# ---------------------------------------------------------------- command line

def run_cli(*args, code=None):
    code = code or "import runpy,sys; sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')"
    return subprocess.run([sys.executable, "-c", code, SCRIPT, *args], capture_output=True, text=True, timeout=120)


def fx(name):
    return os.path.join(FIX, name)


def test_cli_valid_prints_nothing_and_exits_0():
    p = run_cli("--catalog", fx("catalog.json"), "--manifest", fx("manifest.json"),
                fx("sw-development.json"), fx("tdd-unit.json"))
    assert (p.returncode, p.stdout, p.stderr) == (0, "", "")


def test_cli_invalid_workflow_is_prefixed_with_file_and_exits_1(tmp_path):
    d = copy.deepcopy(SW)
    org(d, "align")["by"] = "robot"
    f = tmp_path / "bad.json"
    f.write_text(json.dumps(d))
    p = run_cli("--catalog", fx("catalog.json"), "--manifest", fx("manifest.json"), str(f))
    assert p.returncode == 1
    assert f"ERROR: {f}: align: metadata.org.by: 'robot' is not one of code, human, model" in p.stderr.splitlines()


def test_cli_catalog_merge_error_has_no_file_prefix_and_skips_workflows(tmp_path):
    a, b = tmp_path / "metrics.json", tmp_path / "metrics.research.json"
    a.write_text(json.dumps(CAT))
    b.write_text(json.dumps({"lead-time": CAT["lead-time"]}))
    p = run_cli("--catalog", str(a), "--catalog", str(b), "--manifest", fx("manifest.json"), fx("sw-development.json"))
    assert p.returncode == 1
    assert p.stderr.splitlines() == [f"ERROR: catalog: lead-time: defined in {a} and {b}"]


def test_cli_catalog_file_that_is_not_a_map(tmp_path):
    a = tmp_path / "m.json"
    a.write_text("[]")
    p = run_cli("--catalog", str(a), "--manifest", fx("manifest.json"), fx("sw-development.json"))
    assert p.returncode == 1
    assert p.stderr.splitlines() == [f"ERROR: catalog {a}: must be a map of metric names"]


def test_cli_several_catalogs_merge(tmp_path):
    names = sorted(CAT)
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({n: CAT[n] for n in names[:8]}))
    b.write_text(json.dumps({n: CAT[n] for n in names[8:]}))
    p = run_cli("--catalog", str(a), "--catalog", str(b), "--manifest", fx("manifest.json"), fx("sw-development.json"))
    assert (p.returncode, p.stderr) == (0, "")


@pytest.mark.parametrize("args", [
    [],
    ["--manifest", "manifest.json", "w.json"],
    ["--catalog", "c.json", "w.json"],
    ["--catalog", "c.json", "--manifest", "manifest.json"],
    ["--bogus"],
], ids=["none", "no-catalog", "no-manifest", "no-workflow", "unknown-flag"])
def test_cli_usage_errors_exit_2(args):
    assert run_cli(*args).returncode == 2


def test_cli_unknown_extension_is_usage_error(tmp_path):
    f = tmp_path / "w.txt"
    f.write_text("{}")
    p = run_cli("--catalog", fx("catalog.json"), "--manifest", fx("manifest.json"), str(f))
    assert p.returncode == 2


def test_cli_unreadable_file_is_load_error_exit_1(tmp_path):
    p = run_cli("--catalog", fx("catalog.json"), "--manifest", fx("manifest.json"), str(tmp_path / "nope.json"))
    assert p.returncode == 1 and p.stderr.startswith("ERROR: ")


# ---------------------------------------------------------------- loader (spec 2.1, cases L1 to L11)

def load_error(tmp_path, name, text):
    f = tmp_path / name
    f.write_text(text)
    p = run_cli("--catalog", fx("catalog.json"), "--manifest", fx("manifest.json"), str(f))
    assert p.returncode == 1, p.stderr
    return f, p.stderr.splitlines()


JSON_LOAD = [
    ("L1", "dup.json", '{"a": 1, "a": 2}', "duplicate key 'a'"),
    ("L3", "nan.json", '{"a": NaN}', "non-finite number NaN"),
    ("L6", "big.json", '{"a": 1e999}', "non-finite number 1e999"),
    ("L7", "deep.json", "[" * 100000 + "]" * 100000, "nesting too deep to load"),
    ("L9", "bigint.json", '{"a": ' + "9" * 5000 + "}", "integer longer than 4300 digits"),
]


@pytest.mark.parametrize("cid,name,text,msg", JSON_LOAD, ids=[c[0] for c in JSON_LOAD])
def test_loader_json(tmp_path, cid, name, text, msg):
    f, lines = load_error(tmp_path, name, text)
    assert lines == [f"ERROR: {f}: {msg}"]


def test_loader_infinity_and_minus_infinity(tmp_path):
    for text, tok in (('{"a": Infinity}', "Infinity"), ('{"a": -Infinity}', "-Infinity")):
        f, lines = load_error(tmp_path, "inf.json", text)
        assert lines == [f"ERROR: {f}: non-finite number {tok}"]


YAML_LOAD = [
    ("L2", "dup.yaml", "a: 1\na: 2\n", "duplicate key 'a'"),
    ("L5", "alias.yaml", "a: &x [1]\nb: *x\n", "alias '*x' is not accepted; write the value out"),
    ("L8", "merge.yaml", "b:\n  <<: {a: 1}\n  c: 2\n", "merge key '<<' is not accepted; write the keys out"),
    ("L10", "bigint.yaml", "a: " + "9" * 5000 + "\n", "integer longer than 4300 digits"),
]


@pytest.mark.parametrize("cid,name,text,msg", YAML_LOAD, ids=[c[0] for c in YAML_LOAD])
def test_loader_yaml(tmp_path, cid, name, text, msg):
    pytest.importorskip("yaml", reason="PyYAML not installed; run with uv run --with pyyaml")
    f, lines = load_error(tmp_path, name, text)
    assert lines == [f"ERROR: {f}: {msg}"]


def test_loader_yaml_parse_error_l11(tmp_path):
    pytest.importorskip("yaml", reason="PyYAML not installed; run with uv run --with pyyaml")
    f, lines = load_error(tmp_path, "broken.yaml", "a: [\n")
    assert len(lines) == 1 and lines[0].startswith(f"ERROR: {f}: parse error: ")


def test_loader_yaml_keeps_on_yes_and_dates_as_strings():
    pytest.importorskip("yaml", reason="PyYAML not installed; run with uv run --with pyyaml")
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        f = os.path.join(t, "d.yaml")
        with open(f, "w") as fh:
            fh.write("a: 2026-11-19\nb: on\nc: yes\n")
        assert vo.load_file(f) == {"a": "2026-11-19", "b": "on", "c": "yes"}


def test_loader_does_not_change_pyyaml_for_other_users():
    yaml = pytest.importorskip("yaml", reason="PyYAML not installed; run with uv run --with pyyaml")
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        f = os.path.join(t, "d.yaml")
        with open(f, "w") as fh:
            fh.write("b: on\n")
        vo.load_file(f)
    assert yaml.safe_load("b: on") == {"b": True}


def test_loader_l4_yaml_without_pyyaml_exits_2(tmp_path):
    f = tmp_path / "w.yaml"
    f.write_text("do: []\n")
    code = "import sys; sys.modules['yaml'] = None; import runpy; sys.argv = sys.argv[1:]; runpy.run_path(sys.argv[0], run_name='__main__')"
    p = run_cli("--catalog", fx("catalog.json"), "--manifest", fx("manifest.json"), str(f), code=code)
    assert p.returncode == 2
    assert p.stderr.startswith(f"ERROR: {f}: reading YAML needs PyYAML; run with uv run --with pyyaml, or convert the file to JSON")


def test_cli_validates_a_yaml_workflow_end_to_end(tmp_path):
    pytest.importorskip("yaml", reason="PyYAML not installed; run with uv run --with pyyaml")
    f = tmp_path / "wf.yaml"
    f.write_text("document: {dsl: 1.1.0, namespace: org, name: improve, version: 0.1.0}\ndo: []\n")
    p = run_cli("--catalog", fx("catalog.json"), "--manifest", fx("manifest.json"), str(f))
    assert (p.returncode, p.stderr) == (0, "")


# ---------------------------------------------------------------- repo hygiene

def test_script_imports_only_the_standard_library():
    with open(SCRIPT, encoding="utf-8") as f:
        lines = f.read().splitlines()
    top, nested = set(), set()
    for line in lines:
        s = line.strip()
        target = top if line == s else nested
        if s.startswith("import "):
            target |= {m.strip().split(" ")[0].split(".")[0] for m in s[7:].split(",")}
        elif s.startswith("from "):
            target.add(s.split()[1].split(".")[0])
    assert top <= set(sys.stdlib_module_names), top - set(sys.stdlib_module_names)
    assert nested <= set(sys.stdlib_module_names) | {"yaml"}, nested


def test_no_local_paths_in_this_unit():
    root = os.path.dirname(HERE)
    needles = ("claude-" + "501", "/Users" + "/", "~/Fun" + "/plans", "/private" + "/tmp")
    for dp, _, fs in os.walk(root):
        for fn in fs:
            if fn.endswith((".py", ".json", ".md")):
                with open(os.path.join(dp, fn), encoding="utf-8") as fh:
                    text = fh.read()
                assert not any(n in text for n in needles), os.path.join(dp, fn)


# ================================================================ review 1 additions

import time  # noqa: E402


def check_cases(cases):
    for cid, base, mut, prefix, man in cases:
        d = copy.deepcopy(base)
        mut(d)
        errs = vo.validate_org(d, CAT, man)
        if prefix is None:
            assert errs == [], cid
        else:
            assert any(e.startswith(prefix) for e in errs), (cid, prefix, errs)


def with_alarm(seconds):
    import signal

    def handler(*_):
        raise AssertionError(f"did not finish in {seconds}s")
    signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)


def rename_task(d, old, new):
    i = index_of(d, old)
    d["do"][i] = {new: d["do"][i][old]}


# B1: `$` in a pattern accepts a trailing newline, so every pattern must match the whole string
B1_CASES = [
    ("B1-sh", SW, lambda d: shell(d, "merge").__setitem__("command", "sh\n"),
     "merge: run.shell.command: must be a bare command name with no path, space or arguments", MAN),
    ("B1-agent-run", SW, lambda d: shell(d, "align").__setitem__("command", "agent-run\n"),
     "align: run.shell.command: must be a bare command name with no path, space or arguments", MAN),
    ("B1-task-name", SW, lambda d: d["do"].append({"a\n": {"set": {"x": 1}}}), "a\n: task name must be kebab-case", MAN),
    ("B1-check", SW, lambda d: org(d, "spec")["acceptance"][0].__setitem__("check", "spec-ok\n"),
     "spec: metadata.org.acceptance[0].check: must be a kebab-case check name", MAN),
    ("B1-policy", SW, lambda d: d["document"]["metadata"]["org"].__setitem__("policy", ["vcs.remote\n"]),
     "document.metadata.org.policy: must be a list of dotted names like vcs.remote", MAN),
    ("B1-brief", SW, lambda d: org(d, "align").__setitem__("brief", "briefs/align.md\n"),
     "align: metadata.org.brief: must be a relative path under briefs/ ending .md", MAN),
    ("B1-rubric", SW, lambda d: org(d, "spec")["acceptance"][1].__setitem__("rubric", "criteria/spec.md\n"),
     "spec: metadata.org.acceptance[1].rubric: must be a relative path under criteria/ ending .md", MAN),
    ("B1-namespace", SW, lambda d: d["document"].__setitem__("namespace", "org\n"),
     "document.namespace: 'org\\n' differs from manifest namespace", MAN),
]


@pytest.mark.parametrize("case", B1_CASES, ids=[c[0] for c in B1_CASES])
def test_trailing_newline_is_not_accepted_by_any_pattern(case):
    check_cases([case])


# B2: numbers that overflow float conversion must not raise
BIG = 10 ** 400
B2_DOCS = [
    {"do": [{"a": {"set": 1, "metadata": {"org": {"acceptance": [{"rubric": "criteria/x.md", "judge": "owner",
                                                                   "sample": BIG}]}}}}]},
    {"do": [{"a": {"set": 1, "metadata": {"org": {"by": 10 ** 5000, "role": 10 ** 5000, "floor": 10 ** 5000}}}}]},
    {"document": {"name": 10 ** 5000, "namespace": 10 ** 5000}, "do": []},
    {"do": [{"a": {"wait": BIG}}, {"b": {"wait": {"days": BIG}}}]},
    {"do": [{"a": {"try": [], "catch": {"retry": {"limit": {"attempt": {"count": BIG}}}}}}]},
]


@pytest.mark.parametrize("doc", B2_DOCS, ids=range(len(B2_DOCS)))
def test_huge_integers_do_not_raise(doc):
    errs = vo.validate_org(copy.deepcopy(doc), CAT, MAN)
    assert all(isinstance(e, str) for e in errs)


def test_huge_sample_is_an_error():
    d = copy.deepcopy(SW)
    org(d, "review")["acceptance"][0]["sample"] = BIG
    assert any(e.startswith("review: metadata.org.acceptance[0].sample: must be a number in (0, 1]")
               for e in vo.validate_org(d, CAT, MAN))


# B3: schema endpoints at root level and on `export`
B3_CASES = [
    ("B3-root-input", SW, lambda d: d.__setitem__("input", {"schema": {"resource": {"endpoint": "https://evil/x.json"}}}),
     "input.schema.resource.endpoint: must be a relative path under schemas/ ending .json", MAN),
    ("B3-root-output", SW, lambda d: d.__setitem__("output", {"schema": {"resource": {"endpoint": "../x.json"}}}),
     "output.schema.resource.endpoint: must be a relative path under schemas/ ending .json", MAN),
    ("B3-task-export", SW, lambda d: find(d, "spec").__setitem__("export", {"schema": {"resource": {"endpoint": "/etc/x.json"}}}),
     "spec: export.schema.resource.endpoint: must be a relative path under schemas/ ending .json", MAN),
    ("B3-task-input", SW, lambda d: find(d, "spec").__setitem__("input", {"schema": {"resource": {"endpoint": "x.json"}}}),
     "spec: input.schema.resource.endpoint: must be a relative path under schemas/ ending .json", MAN),
    ("B3-no-endpoint", SW, lambda d: d.__setitem__("input", {"schema": {"resource": {}}}),
     "input.schema.resource.endpoint: must be a relative path under schemas/ ending .json", MAN),
    ("B3-ok-root", SW, lambda d: d.__setitem__("input", {"schema": {"resource": {"endpoint": "schemas/in.json"}}}), None, MAN),
    ("B3-ok-export", SW, lambda d: find(d, "spec").__setitem__("export", {"schema": {"resource": {"endpoint": "schemas/e.json"}}}), None, MAN),
    ("B3-inline-schema-ok", SW, lambda d: d.__setitem__("input", {"schema": {"format": "json", "document": {"type": "object"}}}), None, MAN),
]


@pytest.mark.parametrize("case", B3_CASES, ids=[c[0] for c in B3_CASES])
def test_schema_endpoints_are_checked_everywhere(case):
    check_cases([case])


# S1: only the integer-conversion error is the 4300-digit message
def _cli_load_error(tmp_path, name, data):
    f = tmp_path / name
    if isinstance(data, bytes):
        f.write_bytes(data)
    else:
        f.write_text(data)
    p = run_cli("--catalog", fx("catalog.json"), "--manifest", fx("manifest.json"), str(f))
    return f, p


def test_json_syntax_error_at_char_4300_is_a_parse_error(tmp_path):
    f, p = _cli_load_error(tmp_path, "w.json", '{"a": 1,' + " " * (4300 - 8) + "x")
    assert p.returncode == 1
    assert p.stderr.startswith(f"ERROR: {f}: parse error: ")
    assert "4300 digits" not in p.stderr


def test_bad_utf8_byte_at_offset_4300_is_a_parse_error(tmp_path):
    f, p = _cli_load_error(tmp_path, "w.json", b'{"a": "' + b"x" * (4300 - 7) + b'\xff"}')
    assert p.returncode == 1
    assert p.stderr.startswith(f"ERROR: {f}: parse error: ")
    assert "4300 digits" not in p.stderr


def test_directory_as_workflow_file_is_a_load_error(tmp_path):
    d = tmp_path / "d.json"
    d.mkdir()
    p = run_cli("--catalog", fx("catalog.json"), "--manifest", fx("manifest.json"), str(d))
    assert p.returncode == 1
    assert p.stderr.startswith(f"ERROR: {d}: ") and "Traceback" not in p.stderr


# S2: cyclic and exponentially shared values
def test_cyclic_document_returns_an_error():
    with_alarm(20)
    a = {}
    a["x"] = a
    a["y"] = a
    errs = vo.validate_org(a, CAT, MAN)
    assert any("refers to itself" in e for e in errs), errs


def test_exponentially_shared_document_is_capped():
    with_alarm(20)
    node = []
    for _ in range(60):
        node = [node, node]
    errs = vo.validate_org({"do": [{"a": {"set": node}}]}, CAT, MAN)
    assert any(e.startswith("(root): document has more than 1000000 values") for e in errs), errs


# S3: task cap and linear scans
def test_task_count_is_capped_with_a_located_error():
    with_alarm(60)
    d = copy.deepcopy(TDD)
    d["do"] = [{f"t{i}": {"set": {"a": 1}}} for i in range(10001)]
    errs = vo.validate_org(d, CAT, MAN)
    assert "t10000: more than 10000 tasks in the workflow" in errs


def test_wide_workflow_validates_quickly():
    with_alarm(60)
    d = copy.deepcopy(SW)
    tasks = []
    for i in range(9000):
        t = {"set": {"a": 1}, "then": f"t{i + 1}"}
        if i % 30 == 0:
            t = {"emit": {"event": {"with": {"type": f"org.x-{i}"}}},
                 "metadata": {"org": {"floor": True}}}
        tasks.append({f"t{i}": t})
    d["do"] = tasks
    start = time.time()
    errs = vo.validate_org(d, CAT, MAN)
    assert time.time() - start < 10, "validation is not linear"
    assert errs


# S4: author values print with repr
S4_CASES = [
    ("S4-name", SW, lambda d: d["document"].__setitem__("name", 5), "document.name: workflow 5 is not in manifest.workflows", MAN),
    ("S4-name-none", SW, lambda d: d["document"].pop("name"), "document.name: workflow None is not in manifest.workflows", MAN),
    ("S4-namespace", SW, lambda d: d["document"].__setitem__("namespace", 5), "document.namespace: 5 differs from manifest namespace", MAN),
    ("S4-floor", SW, lambda d: None, "manifest: workflows.sw-development.floors: floor 5 is not a task in the workflow",
     manifest_with(lambda m: m["workflows"]["sw-development"]["floors"].append(5))),
    ("S4-role", SW, lambda d: org(d, "align").__setitem__("role", 5), "align: metadata.org.role: unknown role 5", MAN),
]


@pytest.mark.parametrize("case", S4_CASES, ids=[c[0] for c in S4_CASES])
def test_author_values_are_printed_with_repr(case):
    check_cases([case])


# S5: spec rules that had no test
S5_CASES = [
    ("document.metadata non-map", SW, lambda d: d["document"].__setitem__("metadata", "x"), "document.metadata: must be a map", MAN),
    ("document.metadata.org non-map", SW, lambda d: d["document"]["metadata"].__setitem__("org", []), "document.metadata.org: must be a map", MAN),
    ("duplicate policy", SW, lambda d: d["document"]["metadata"]["org"].__setitem__("policy", ["vcs.remote", "vcs.remote"]),
     "document.metadata.org.policy: duplicate name", MAN),
    ("evaluate.language", SW, lambda d: d.__setitem__("evaluate", {"language": "jsonata"}), "evaluate.language: not in the accepted subset", MAN),
    ("schedule.every", SW, lambda d: d.__setitem__("schedule", {"every": {"hours": 1}}), "schedule.every: not in the accepted subset", MAN),
    ("schedule.after", SW, lambda d: d.__setitem__("schedule", {"after": {"hours": 1}}), "schedule.after: not in the accepted subset", MAN),
    ("root timeout named", SW, lambda d: d.__setitem__("timeout", "t"),
     "timeout: a named timeout needs 'use', which is refused; write it inline", MAN),
    ("root timeout zero", SW, lambda d: d.__setitem__("timeout", {"after": {"seconds": 0}}), "timeout.after: duration must be greater than zero", MAN),
    ("root timeout 31 days", SW, lambda d: d.__setitem__("timeout", {"after": {"days": 31}}), "timeout.after: duration must be at most 30 days", MAN),
    ("root timeout 30 days ok", SW, lambda d: d.__setitem__("timeout", {"after": {"days": 30}}), None, MAN),
    ("wait 31 days", TDD, lambda d: d["do"].insert(0, {"pause": {"wait": {"days": 31}}}), "pause: wait: duration must be at most 30 days", MAN),
    ("retry delay", SW, lambda d: append_try(d, {"limit": {"attempt": {"count": 1}}, "delay": "PT1S"}),
     "retrying: catch.retry.delay: duration must be a literal map of days, hours, minutes, seconds, milliseconds", MAN),
    ("retry limit.duration", SW, lambda d: append_try(d, {"limit": {"attempt": {"count": 1}, "duration": {"seconds": 0}}}),
     "retrying: catch.retry.limit.duration: duration must be greater than zero", MAN),
    ("retry attempt.duration", SW, lambda d: append_try(d, {"limit": {"attempt": {"count": 1, "duration": {"days": 31}}}}),
     "retrying: catch.retry.limit.attempt.duration: duration must be at most 30 days", MAN),
    ("for.at reserved", SW, lambda d: find(d, "units")["for"].__setitem__("at", "input"),
     "build/units: for.at: 'input' is a reserved variable name", MAN),
    ("catch.as reserved", SW, lambda d: d["do"].append({"retrying": {"try": [{"inner": {"set": {"a": 1}}}], "catch": {"as": "task"}}}),
     "retrying: catch.as: 'task' is a reserved variable name", MAN),
    ("catch.then", SW, lambda d: d["do"].append({"retrying": {"try": [{"inner": {"set": {"a": 1}}}], "catch": {"then": "nowhere"}}}),
     "retrying: catch.then: 'nowhere' is not a task in the same list", MAN),
    ("top-level exit", SW, lambda d: find(d, "design").__setitem__("then", "exit"), "design: then: 'exit' skips floor 'review'", MAN),
    ("floor call under if", SW, lambda d: find(d, "build").__setitem__("if", "${ true }"),
     "build/units/tdd: a call to a workflow with floors may not sit inside 'build', which has 'if'", MAN_TF),
    ("task metadata non-map", SW, lambda d: find(d, "align").__setitem__("metadata", "x"), "align: metadata: must be a map", MAN),
]


@pytest.mark.parametrize("case", S5_CASES, ids=[c[0] for c in S5_CASES])
def test_previously_untested_spec_rules(case):
    check_cases([case])


VALUE_CASES = [
    ({"x": {1, 2}}, "x: value of type set is not JSON"),
    ({"x": object()}, "x: value of type object is not JSON"),
    ({"x": float("nan")}, "x: non-finite number"),
    ({"x": [float("inf")]}, "x[0]: non-finite number"),
    ({1: "a"}, "(root): key 1 is not a string (YAML 1.1 reads on, off, yes and no as booleans; quote it)"),
]


@pytest.mark.parametrize("doc,msg", VALUE_CASES, ids=[m[:24] for _, m in VALUE_CASES])
def test_value_errors_stop_other_checks(doc, msg):
    assert vo.validate_org(doc, CAT, MAN) == [msg]


# nits: wrong container types and bare-string arguments
NIT_CASES = [
    ("root timeout list", SW, lambda d: d.__setitem__("timeout", []), "timeout: must be a map", MAN),
    ("schedule string", SW, lambda d: d.__setitem__("schedule", "x"), "schedule: must be a map", MAN),
    ("evaluate list", SW, lambda d: d.__setitem__("evaluate", []), "evaluate: must be a map", MAN),
    ("task timeout list", SW, lambda d: find(d, "merge").__setitem__("timeout", []), "merge: timeout: must be a map", MAN),
    ("for string", SW, lambda d: find(d, "units").__setitem__("for", "x"), "build/units: for: must be a map", MAN),
    ("fork string", SW, lambda d: d["do"].append({"par": {"fork": "x"}}), "par: fork: must be a map", MAN),
    ("arguments string", SW, lambda d: shell(d, "align").__setitem__("arguments", "--isolated"),
     "align: run.shell.arguments: must be a list", MAN),
]


@pytest.mark.parametrize("case", NIT_CASES, ids=[c[0] for c in NIT_CASES])
def test_wrong_container_types_are_reported(case):
    check_cases([case])


# update 2: the examples carry 12.6 changes 7 to 9
def test_fixtures_carry_spec_12_6_changes_7_to_9():
    assert find(SW, "tdd")["run"]["workflow"]["input"] == {"unit": "${ $unit }"}
    assert find(SW, "cut")["export"] == {"as": "${ $context + . }"}
    assert find(SW, "units")["for"]["in"] == "${ $context.units }"
    assert find(SW, "review")["timeout"] == {"after": {"days": 7}}
    assert "await" not in find(SW, "tdd")["run"]


def test_join_is_a_plain_gate_so_it_needs_the_gate_keys():
    d = copy.deepcopy(SW)
    w89(d)
    org(d, "join").pop("acceptance")
    assert any(e.startswith("build/join: metadata.org.acceptance: required for kind gate")
               for e in vo.validate_org(d, CAT, MAN))
    d = copy.deepcopy(SW)
    w89(d)
    find(d, "join").pop("timeout")
    assert "build/join: kind gate needs an inline timeout" in vo.validate_org(d, CAT, MAN)


# CI py313: nesting depth must not depend on the interpreter's recursion limit
def _json_file(tmp_path, text):
    f = tmp_path / "n.json"
    f.write_text(text)
    return f


@pytest.mark.parametrize("text", ["[" * 100000, '{"a":' * 100000, "[" * 600 + "]" * 600,
                                  '{"a":' * 600 + "1" + "}" * 600], ids=["array-open", "object-open", "array-600", "object-600"])
def test_json_nesting_over_512_is_refused_on_any_interpreter(tmp_path, text):
    f = _json_file(tmp_path, text)
    with pytest.raises(vo.LoadError) as e:
        vo.load_file(str(f))
    assert str(e.value) == f"{f}: nesting too deep to load"


def test_json_nesting_of_100_still_loads(tmp_path):
    f = _json_file(tmp_path, "[" * 100 + "]" * 100)
    assert vo.load_file(str(f)) is not None


def test_json_brackets_inside_strings_do_not_count(tmp_path):
    f = _json_file(tmp_path, json.dumps({"a": "[" * 5000, "b": "\\" + '"' + "[" * 5000}))
    assert vo.load_file(str(f))["a"] == "[" * 5000


def test_json_nesting_of_exactly_512_loads_and_513_does_not(tmp_path):
    assert vo.load_file(str(_json_file(tmp_path, "[" * 512 + "]" * 512))) is not None
    with pytest.raises(vo.LoadError):
        vo.load_file(str(_json_file(tmp_path, "[" * 513 + "]" * 513)))


# update 3: spec W90 (events), W107 to W116 (P11, P12, P14, P18, P19)
def pm_gate():
    return {"pm-accepts": {"listen": {"to": {"one": {"with": {"type": "org.pm-decided"}}}},
                           "timeout": {"after": {"days": 1}},
                           "metadata": {"org": {"by": "human", "role": "pm", "signer": "pm", "metrics": ["escalations"],
                                                "acceptance": [{"human": "pm accepts"}]}}}}


def w116(d):
    d["do"].append(pm_gate())
    emit_type(d, "org.pm-decided")


U3_CASES = [
    ("W90-events", SW, lambda d: find(d, "units")["for"].__setitem__("each", "events"),
     "build/units: for.each: 'events' is a reserved variable name", MAN),
    ("W90-events-catch", SW, lambda d: d["do"].append({"r": {"try": [{"i": {"set": {"a": 1}}}], "catch": {"as": "events"}}}),
     "r: catch.as: 'events' is a reserved variable name", MAN),
    ("W107", SW, lambda d: emit_type(d, "org.task-ended"),
     "report: emit.event.with.type: 'org.task-ended' uses the reserved prefix org.task-", MAN),
    ("W108", SW, lambda d: org(d, "align").__setitem__("network", "allowlist"),
     "align: metadata.org.network: must be a dotted policy name like research.source-allowlist", MAN),
    ("W108-newline", SW, lambda d: org(d, "align").__setitem__("network", "a.b\n"),
     "align: metadata.org.network: must be a dotted policy name like research.source-allowlist", MAN),
    ("W109", SW, lambda d: org(d, "merge-gate").__setitem__("network", "research.source-allowlist"),
     "merge-gate: metadata.org.network: not allowed on kind gate", MAN),
    ("W109-call", SW, lambda d: org(d, "improve").__setitem__("network", "research.source-allowlist"),
     "improve: metadata.org.network: not allowed on kind call", MAN),
    ("W110", SW, lambda d: org(d, "align").__setitem__("network", "research.source-allowlist"), None, MAN),
    ("W111", SW, lambda d: shell(d, "align").__setitem__("arguments", ["--network", "research.source-allowlist"]),
     "align: run.shell.arguments: --network is set by the runtime from metadata.org; remove it", MAN),
    ("W111-eq", SW, lambda d: shell(d, "align").__setitem__("arguments", ["--network=x.y"]),
     "align: run.shell.arguments: --network is set by the runtime from metadata.org; remove it", MAN),
    ("W112", SW, lambda d: shell(d, "align").__setitem__("arguments", ["--input=x.json"]),
     "align: run.shell.arguments: --input is set by the runtime from the task input; remove it", MAN),
    ("W112-bare", SW, lambda d: shell(d, "align").__setitem__("arguments", ["--input", "x.json"]),
     "align: run.shell.arguments: --input is set by the runtime from the task input; remove it", MAN),
    ("W113", SW, lambda d: org(d, "merge-gate").__setitem__("signer", "boss"),
     "merge-gate: metadata.org.signer: unknown role 'boss'", MAN),
    ("W114", SW, lambda d: org(d, "align").__setitem__("signer", "pm"),
     "align: metadata.org.signer: not allowed on kind step", MAN),
    ("W115", SW, lambda d: d["do"].append(pm_gate()), None, MAN),
    ("W116", SW, w116, "report: emit.event.with.type: 'org.pm-decided' is listened on by gate 'pm-accepts'", MAN),
    ("signer-owner-ok", SW, lambda d: org(d, "merge-gate").__setitem__("signer", "owner"), None, MAN),
    ("signer-makes-decision-gate", SW,
     lambda d: d["do"].append({"g": {"listen": {"to": {"any": [{"with": {"type": "org.x"}}]}}, "timeout": {"after": {"hours": 1}},
                                     "metadata": {"org": {"by": "code", "role": "lead", "signer": "lead",
                                                          "metrics": ["escalations"], "acceptance": [{"check": "workers-done"}]}}}}),
     "g: listen.to: a decision gate listens with to.one only", MAN),
]


@pytest.mark.parametrize("case", U3_CASES, ids=[c[0] for c in U3_CASES])
def test_update_3_cases(case):
    check_cases([case])


# update 6: check classes (P25), cases W117 to W119
def w117(d):
    org(d, "red")["acceptance"].append({"check": "red-evidence"})


U6_CASES = [
    ("W117", TDD, w117,
     "cycle/red: metadata.org.acceptance[1].check: fact check 'red-evidence' may sit only on a by: code task; "
     "put it on the code step that produces the fact", MAN),
    ("W117-gate", SW, lambda d: org(d, "merge-gate")["acceptance"].append({"check": "acceptance-suite-green"}),
     "merge-gate: metadata.org.acceptance[1].check: fact check 'acceptance-suite-green' may sit only on a by: code task; "
     "put it on the code step that produces the fact", MAN),
    ("W117-code-ok", TDD, lambda d: org(d, "green-evidence")["acceptance"].append({"check": "red-evidence"}), None, MAN),
    ("W118", SW, lambda d: org(d, "spec")["acceptance"].append({"check": "write-sets-are-disjoint"}), None, MAN),
    ("W119", SW, lambda d: org(d, "merge")["acceptance"].append({"check": "no-such-check"}),
     "merge: metadata.org.acceptance[1].check: unknown check 'no-such-check' (not in manifest.checks)", MAN),
    ("W119-no-checks-map", SW, lambda d: None,
     "spec: metadata.org.acceptance[0].check: unknown check 'spec-check' (not in manifest.checks)",
     manifest_with(lambda m: m.pop("checks", None))),
    ("W119-checks-not-a-map", SW, lambda d: None,
     "spec: metadata.org.acceptance[0].check: unknown check 'spec-check' (not in manifest.checks)",
     manifest_with(lambda m: m.__setitem__("checks", ["spec-check"]))),
]


@pytest.mark.parametrize("case", U6_CASES, ids=[c[0] for c in U6_CASES])
def test_update_6_cases(case):
    check_cases([case])


def test_manifest_fixture_has_checks_for_every_example_check():
    names = set()

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("check"), str):
                names.add(x["check"])
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(SW)
    walk(TDD)
    assert names <= set(MAN["checks"]) and set(MAN["checks"].values()) <= {"fact", "shape"}
