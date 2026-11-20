#!/usr/bin/env python3
"""Validate an OWS workflow's org governance (`metadata.org`) against a metric catalog and a manifest.

    validate_org.py --catalog FILE [--catalog FILE ...] --manifest FILE WORKFLOW [WORKFLOW ...]

Files are JSON, or YAML when PyYAML is importable. A valid run prints nothing and exits 0.
Exit 1: invalid, or a load error. Exit 2: usage error (bad arguments, unknown extension, YAML without PyYAML).

`validate_org(doc, catalog, manifest) -> list[str]` works on parsed values and never raises. It does not
validate the catalog or the manifest; a malformed one reads as empty, so every reference into it is unresolved.
Rules and messages follow the org-documents spec (sections 2 to 7).
"""
import argparse
import bisect
import json
import math
import re
import sys

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
POLICY = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")
COMMAND = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
CTRL = re.compile(r"[\x00-\x1f\x7f]")
OWNER = "owner"
BY = ("code", "human", "model")
TASK_KEYS = ("call", "do", "emit", "for", "fork", "listen", "raise", "run", "set", "switch", "try", "wait")
LEAF = ("step", "call", "gate", "emit")
ROOT_KEYS = ("document", "input", "output", "timeout", "schedule", "evaluate", "do")
MAX_LISTS = 16
MAX_VALUE_DEPTH = 128
MAX_VALUES = 1000000  # values visited by the document walk; bounds shared sub-values
MAX_TASKS = 10000  # tasks per workflow; the spec's scale target is 1000
WRAPPERS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "env", "exec", "eval", "command", "sudo", "nohup",
            "nice", "timeout", "xargs"}
RESERVED_VARS = {"accepted", "authorization", "context", "input", "output", "runtime", "secrets", "task",
                 "workflow", "events"}
DUR_MS = {"days": 86400000, "hours": 3600000, "minutes": 60000, "seconds": 1000, "milliseconds": 1}
ORG_KEYS = {"by", "role", "metrics", "acceptance", "brief", "floor", "to", "network", "signer"}
LEAF_KEYS = {"by", "role", "metrics", "acceptance", "brief", "floor"}
ALLOWED = {k: LEAF_KEYS for k in LEAF}
ALLOWED["step"] = LEAF_KEYS | {"network"}
ALLOWED["gate"] = LEAF_KEYS | {"signer"}
ALLOWED["escalation"] = {"to", "metrics"}
for _k in ("container", "branch", "assign", "wait"):
    ALLOWED[_k] = {"metrics"}
REQUIRED = {k: ("by", "role", "metrics", "acceptance") for k in LEAF}
REQUIRED["escalation"] = ("to",)
RUN_FORMS = ("container", "script", "shell", "workflow")
A_FLOOR = "a floor"
A_FLOOR_CALL = "a call to a workflow with floors"


def _map(v):
    return v if isinstance(v, dict) else {}


def _str_in(v, coll):
    return isinstance(v, str) and v in coll


def _num(v):
    # isfinite() converts to float, which overflows for a huge int: test floats only
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return not isinstance(v, float) or math.isfinite(v)


def _r(v):
    """repr of an author value (spec 2.3 rule 4); a huge int has no repr, so it must not raise."""
    try:
        return repr(v)
    except ValueError:
        return "<integer longer than 4300 digits>"


def _s(v):
    return v if isinstance(v, str) else _r(v)


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _literal(v):
    return isinstance(v, str) and "${" not in v


def _relpath(p, prefix, suffix):
    # An empty stem under a subdirectory (`briefs/sw/.md`) is accepted; only a bare `briefs/.md` is not.
    return (isinstance(p, str) and not CTRL.search(p) and p.startswith(prefix) and p.endswith(suffix)
            and len(p) > len(prefix) + len(suffix) and "\\" not in p and not p.startswith("/")
            and all(seg not in ("", ".", "..") for seg in p.split("/")))


def _value_errors(root):
    """Spec 2.1 rule 6: string keys, JSON values, finite numbers, depth cap. Iterative.

    A container that contains itself is an error, and a walk over more than MAX_VALUES values stops,
    so a hand-built document cannot make the walk run for ever.
    """
    errs, deep, seen = [], False, 0
    on_path = set()
    stack = [(root, "", 1)]
    while stack:
        item = stack.pop()
        if len(item) == 1:  # leaving a container
            on_path.discard(item[0])
            continue
        v, loc, lvl = item
        where = loc or "(root)"
        seen += 1
        if seen > MAX_VALUES:
            errs.append(f"(root): document has more than {MAX_VALUES} values")
            break
        if lvl > MAX_VALUE_DEPTH:
            if not deep:
                errs.append(f"{where}: value nested deeper than {MAX_VALUE_DEPTH} levels")
                deep = True
            continue
        if isinstance(v, (dict, list)):
            if id(v) in on_path:
                errs.append(f"{where}: value refers to itself")
                continue
            on_path.add(id(v))
            stack.append((id(v),))
        if isinstance(v, dict):
            items = []
            for k, x in v.items():
                if isinstance(k, str):
                    items.append((x, f"{loc}.{k}" if loc else k, lvl + 1))
                else:
                    errs.append(f"{where}: key {_r(k)} is not a string "
                                "(YAML 1.1 reads on, off, yes and no as booleans; quote it)")
            stack.extend(reversed(items))
        elif isinstance(v, list):
            stack.extend(reversed([(x, f"{loc}[{i}]", lvl + 1) for i, x in enumerate(v)]))
        elif v is not None and not isinstance(v, (str, int, float, bool)):
            errs.append(f"{where}: value of type {type(v).__name__} is not JSON")
        elif isinstance(v, float) and not math.isfinite(v):
            errs.append(f"{where}: non-finite number")
    return errs


def _derive_kind(task):
    """Return the kind. Refused forms give 'refused:<what>'; a bad run gives 'badrun'; no single task gives None."""
    keys = [k for k in TASK_KEYS if k in task]
    if set(keys) == {"for", "do"}:
        return "container"
    if len(keys) != 1:
        return None
    k = keys[0]
    if k == "run":
        forms = [f for f in RUN_FORMS if f in _map(task["run"])]
        if len(forms) != 1:
            return "badrun"
        return {"shell": "step", "workflow": "call"}.get(forms[0], "refused:run." + forms[0])
    if k == "call":
        return "refused:call"
    return {"listen": "gate", "emit": "emit", "raise": "escalation", "for": "container", "try": "container",
            "do": "container", "fork": "container", "switch": "branch", "set": "assign", "wait": "wait"}[k]


def _child_lists(task):
    out = []
    if "do" in task:
        out.append(task["do"])
    if "fork" in task:
        out.append(_map(task["fork"]).get("branches", []))
    if "try" in task:
        out.append(task["try"])
        if "do" in _map(task.get("catch")):
            out.append(task["catch"]["do"])
    return out


class _TooManyTasks(Exception):
    pass


def _walk(lst, prefix, depth, errs, nodes, parent):
    """Pre-order walk of one task list. Each node records its list id, index and parent for later rules."""
    if not isinstance(lst, list):
        errs.append(f"{prefix or 'do'}: task list must be a list")
        return
    for i, item in enumerate(lst):
        if not (isinstance(item, dict) and len(item) == 1):
            errs.append(f"{prefix + '/' if prefix else ''}[{i}]: task item must be a map with one name")
            continue
        (name, task), = item.items()
        path = f"{prefix}/{name}" if prefix else name
        if depth > MAX_LISTS:
            errs.append(f"{path}: nesting deeper than {MAX_LISTS} task lists")
            return
        if len(nodes) >= MAX_TASKS:
            raise _TooManyTasks(path)
        if not isinstance(task, dict):
            errs.append(f"{path}: task must be a map")
            continue
        kind = _derive_kind(task)
        node = {"path": path, "name": name, "task": task, "kind": kind, "list": id(lst), "index": i,
                "parent": parent, "order": len(nodes)}
        nodes.append(node)
        if kind == "container":
            for sub in _child_lists(task):
                _walk(sub, path, depth + 1, errs, nodes, node)


def _ancestors(n):
    out, p = [], n["parent"]
    while p:
        out.append(p)
        p = p["parent"]
    return out


def _is_ancestor(a, n):
    return any(x is a for x in _ancestors(n))


def _duration(v, prefix, key, errs):
    loc = f"{prefix}: {key}" if prefix else key
    if not (isinstance(v, dict) and v and all(k in DUR_MS for k in v) and all(_int(x) and x >= 0 for x in v.values())):
        errs.append(f"{loc}: duration must be a literal map of days, hours, minutes, seconds, milliseconds")
    elif sum(v.values()) == 0:
        errs.append(f"{loc}: duration must be greater than zero")
    elif sum(DUR_MS[k] * x for k, x in v.items()) > 30 * DUR_MS["days"]:
        errs.append(f"{loc}: duration must be at most 30 days")


def _event_types(to):
    """Literal event types in a `listen.to` map."""
    to = _map(to)
    out = []
    if "one" in to:
        out.append(_map(_map(to["one"]).get("with")).get("type"))
    for k in ("any", "all"):
        if isinstance(to.get(k), list):
            out += [_map(_map(e).get("with")).get("type") for e in to[k]]
    return [t for t in out if _literal(t)]


def _org(task):
    return _map(_map(task.get("metadata")).get("org"))


def _acceptance_items(task):
    a = _org(task).get("acceptance")
    return a if isinstance(a, list) else []


def _is_decision_gate(task):
    o = _org(task)
    return o.get("role") == OWNER or "signer" in o or any(isinstance(i, dict) and "human" in i
                                                   for i in _acceptance_items(task))


def _document_errors(doc, manifest, errs):
    d = _map(doc.get("document"))
    md = d.get("metadata")
    if md is not None and not isinstance(md, dict):
        errs.append("document.metadata: must be a map")
    md = _map(md)
    for k in md:
        if k != "org":
            errs.append(f"document.metadata: unknown namespace '{k}'; only 'org' is allowed")
    org = md.get("org")
    if org is not None:
        if not isinstance(org, dict):
            errs.append("document.metadata.org: must be a map")
        else:
            for k in org:
                if k != "policy":
                    errs.append(f"document.metadata.org: unknown key '{k}'")
            pol = org.get("policy")
            if pol is not None:
                if not isinstance(pol, list) or not all(isinstance(p, str) and POLICY.fullmatch(p) for p in pol):
                    errs.append("document.metadata.org.policy: must be a list of dotted names like vcs.remote")
                elif len(set(pol)) != len(pol):
                    errs.append("document.metadata.org.policy: duplicate name")
    sch = doc.get("schedule")
    if "schedule" in doc and not isinstance(sch, dict):
        errs.append("schedule: must be a map")
    if isinstance(sch, dict):
        for k in ("every", "cron", "after"):
            if k in sch:
                errs.append(f"schedule.{k}: not in the accepted subset")
        on = _map(sch.get("on"))
        filters = ([on["one"]] if "one" in on else []) + [e for k in ("any", "all") if isinstance(on.get(k), list)
                                                          for e in on[k]]
        for i, f in enumerate(filters):
            if not _literal(_map(_map(f).get("with")).get("type")):
                errs.append(f"schedule.on: event filter {i} needs a literal with.type")
    ev = doc.get("evaluate")
    if "evaluate" in doc and not isinstance(ev, dict):
        errs.append("evaluate: must be a map")
    if isinstance(ev, dict):
        if ev.get("language", "jq") != "jq":
            errs.append("evaluate.language: not in the accepted subset")
        if ev.get("mode", "strict") != "strict":
            errs.append("evaluate.mode: not in the accepted subset")
    tm = doc.get("timeout")
    if isinstance(tm, str):
        errs.append("timeout: a named timeout needs 'use', which is refused; write it inline")
    elif isinstance(tm, dict):
        _duration(tm.get("after"), "", "timeout.after", errs)
    elif "timeout" in doc:
        errs.append("timeout: must be a map")
    name, ns = d.get("name"), d.get("namespace")
    if not (isinstance(name, str) and name in _map(manifest.get("workflows"))):
        errs.append(f"document.name: workflow {_r(name)} is not in manifest.workflows")
    if not (isinstance(ns, str) and ns == manifest.get("namespace")):
        errs.append(f"document.namespace: {_r(ns)} differs from manifest namespace")


def _acceptance_errors(items, p, kind, roles, checks, by, errs):
    for i, it in enumerate(items):
        loc = f"{p}: metadata.org.acceptance[{i}]"
        if not isinstance(it, dict):
            errs.append(f"{loc}: must be a map")
            continue
        if "human" in it and kind != "gate":
            errs.append(f"{loc}: a human item is allowed only on a gate")
        for k in it:
            if k not in ("check", "rubric", "human", "judge", "sample"):
                errs.append(f"{loc}: unknown key '{k}'")
        forms = [f for f in ("check", "rubric", "human") if f in it]
        if len(forms) != 1:
            errs.append(f"{loc}: exactly one of check, rubric, human")
            continue
        form = forms[0]
        if form != "rubric":
            for k in ("judge", "sample"):
                if k in it:
                    errs.append(f"{loc}: {k} needs rubric")
        if form == "check":
            name = it["check"]
            if not (isinstance(name, str) and KEBAB.fullmatch(name)):
                errs.append(f"{loc}.check: must be a kebab-case check name")
            elif name not in checks:
                errs.append(f"{loc}.check: unknown check '{name}' (not in manifest.checks)")
            elif checks[name] == "fact" and by != "code":
                errs.append(f"{loc}.check: fact check '{name}' may sit only on a by: code task; "
                            "put it on the code step that produces the fact")
        if form == "human" and not (isinstance(it["human"], str) and it["human"].strip()):
            errs.append(f"{loc}.human: must be a non-empty string")
        if form == "rubric":
            if not _relpath(it["rubric"], "criteria/", ".md"):
                errs.append(f"{loc}.rubric: must be a relative path under criteria/ ending .md")
            if "judge" not in it:
                errs.append(f"{loc}: rubric needs judge")
            elif not _str_in(it["judge"], roles):
                errs.append(f"{loc}.judge: unknown role {_r(it['judge'])}")
            if "sample" in it and not (_num(it["sample"]) and 0 < it["sample"] <= 1):
                errs.append(f"{loc}.sample: must be a number in (0, 1]")


def _org_errors(task, p, kind, catalog, roles, ctx, errs):
    """Check `metadata.org` of one task. Returns the org map, or None when the map itself is unusable."""
    meta = task.get("metadata")
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        errs.append(f"{p}: metadata: must be a map")
        return None
    for k in meta:
        if k != "org":
            errs.append(f"{p}: metadata: unknown namespace '{k}'; only 'org' is allowed")
    o = meta.get("org", {})
    if not isinstance(o, dict):
        errs.append(f"{p}: metadata.org: must be a map")
        return None
    for k in o:
        if k == "kind":
            errs.append(f"{p}: metadata.org.kind: kind is derived from the task key; do not declare it")
        elif k not in ORG_KEYS:
            errs.append(f"{p}: metadata.org: unknown key '{k}'")
        elif k not in ALLOWED[kind]:
            errs.append(f"{p}: metadata.org.{k}: not allowed on kind {kind}")
    for k in REQUIRED.get(kind, ()):
        if k not in o:
            errs.append(f"{p}: metadata.org.{k}: required for kind {kind}")
    if "by" in o and o["by"] not in BY:
        errs.append(f"{p}: metadata.org.by: {_r(o['by'])} is not one of code, human, model")
    for k in ("role", "to"):
        if k in o and not _str_in(o[k], roles):
            errs.append(f"{p}: metadata.org.{k}: unknown role {_r(o[k])}")
    if "metrics" in o:
        m = o["metrics"]
        if not isinstance(m, list) or not all(isinstance(x, str) for x in m):
            errs.append(f"{p}: metadata.org.metrics: must be a list of metric names")
        elif not m:
            errs.append(f"{p}: metadata.org.metrics: must not be empty")
        else:
            for x in m:
                if x not in catalog:
                    errs.append(f"{p}: metadata.org.metrics: unknown metric '{x}'")
            if len(set(m)) != len(m):
                errs.append(f"{p}: metadata.org.metrics: duplicate metric")
    if "acceptance" in o:
        a = o["acceptance"]
        if not isinstance(a, list):
            errs.append(f"{p}: metadata.org.acceptance: must be a list of items")
        elif not a:
            errs.append(f"{p}: metadata.org.acceptance: must not be empty")
        else:
            _acceptance_errors(a, p, kind, roles, ctx["checks"], o.get("by"), errs)
    if "brief" in o and not _relpath(o["brief"], "briefs/", ".md"):
        errs.append(f"{p}: metadata.org.brief: must be a relative path under briefs/ ending .md")
    if "network" in o and not (isinstance(o["network"], str) and POLICY.fullmatch(o["network"])):
        errs.append(f"{p}: metadata.org.network: must be a dotted policy name like research.source-allowlist")
    if "signer" in o and not _str_in(o["signer"], roles):
        errs.append(f"{p}: metadata.org.signer: unknown role {_r(o['signer'])}")
    if "floor" in o and not isinstance(o["floor"], bool):
        errs.append(f"{p}: metadata.org.floor: must be true or false")
    if o.get("role") == OWNER and "by" in o and o["by"] != "human":
        errs.append(f"{p}: metadata.org.by: role owner requires by human")
    return o


def _step_errors(task, p, o, errs):
    sh = _map(_map(task["run"]).get("shell"))
    cmd = sh.get("command")
    if not (isinstance(cmd, str) and COMMAND.fullmatch(cmd)):
        errs.append(f"{p}: run.shell.command: must be a bare command name with no path, space or arguments")
        return
    if cmd in WRAPPERS:
        errs.append(f"{p}: run.shell.command: '{cmd}' is a shell or wrapper and is refused")
        return
    if cmd != "agent-run":
        return
    if "brief" not in o:
        errs.append(f"{p}: metadata.org.brief: required for agent-run")
    if o.get("role") == OWNER:
        errs.append(f"{p}: metadata.org.role: agent-run may not run as owner")
    for k in ("environment", "stdin", "directory"):
        if k in sh:
            errs.append(f"{p}: run.shell.{k}: not allowed on agent-run; the runtime sets it")
    args = sh.get("arguments", [])
    if not isinstance(args, list):
        errs.append(f"{p}: run.shell.arguments: must be a list")
        args = []
    seen_isolated = skip = False
    for a in args:
        if skip:
            skip = False
            continue
        flag = next((f for f in ("--role", "--brief", "--network", "--input")
                     if a == f or (isinstance(a, str) and a.startswith(f + "="))), None)
        if flag:
            skip = a == flag
            source = "the task input" if flag == "--input" else "metadata.org"
            errs.append(f"{p}: run.shell.arguments: {flag} is set by the runtime from {source}; remove it")
        elif a == "--isolated":
            if seen_isolated:
                errs.append(f"{p}: run.shell.arguments: --isolated given more than once")
            seen_isolated = True
        else:
            errs.append(f"{p}: run.shell.arguments: {_r(a)} is not an allowed agent-run flag (allowed: --isolated)")


def _retry_errors(task, p, errs):
    r = _map(task.get("catch")).get("retry")
    if r is None:
        return
    if isinstance(r, str):
        errs.append(f"{p}: catch.retry: a named retry policy needs 'use', which is refused; write it inline")
        return
    r = _map(r)
    limit = _map(r.get("limit"))
    attempt = _map(limit.get("attempt"))
    count = attempt.get("count")
    if not (_int(count) and count > 0):
        errs.append(f"{p}: catch.retry: needs limit.attempt.count, a positive integer")
    elif count > 100:
        errs.append(f"{p}: catch.retry: limit.attempt.count must be at most 100")
    # Spec 7.1a lists the bounded durations: delay, limit.duration, limit.attempt.duration. `backoff` and
    # `jitter` only scale or spread the delay and are not in that list, so they are not checked here.
    if "delay" in r:
        _duration(r["delay"], p, "catch.retry.delay", errs)
    if "duration" in limit:
        _duration(limit["duration"], p, "catch.retry.limit.duration", errs)
    if "duration" in attempt:
        _duration(attempt["duration"], p, "catch.retry.limit.attempt.duration", errs)


def _call_errors(n, ctx, errs):
    p = n["path"]
    w = _map(_map(n["task"]["run"]).get("workflow"))
    name = w.get("name")
    known = isinstance(name, str) and name in ctx["wfs"]
    if not (known and w.get("namespace") == ctx["manifest"].get("namespace")):
        errs.append(f"{p}: run.workflow: workflow '{_s(w.get('namespace'))}/{_s(name)}' is not in manifest.workflows")
    if name == ctx["wfname"]:
        errs.append(f"{p}: run.workflow: a workflow may not call itself")
    if known and _map(ctx["wfs"][name]).get("floors") not in (None, []) \
            and isinstance(_map(ctx["wfs"][name]).get("floors"), list):
        n["floorcall"] = True


def _emit_errors(n, ctx, errs):
    p = n["path"]
    et = _map(_map(_map(n["task"]["emit"]).get("event")).get("with")).get("type")
    if not _literal(et):
        errs.append(f"{p}: emit.event.with.type: must be a literal event type")
    elif et.startswith(("org.owner-", "org.task-")):
        prefix = "org.owner-" if et.startswith("org.owner-") else "org.task-"
        errs.append(f"{p}: emit.event.with.type: '{et}' uses the reserved prefix {prefix}")
    elif et in ctx["decision_types"]:
        errs.append(f"{p}: emit.event.with.type: '{et}' is listened on by gate '{ctx['decision_types'][et]}'")


def _gate_errors(t, p, errs):
    tm = t.get("timeout")
    if "foreach" in t:
        errs.append(f"{p}: foreach: not in the accepted subset")
    if not isinstance(tm, (dict, str)):
        errs.append(f"{p}: kind gate needs an inline timeout")
    if _is_decision_gate(t):
        to = _map(_map(t["listen"]).get("to"))
        if set(to) - {"one"} or "one" not in to:
            errs.append(f"{p}: listen.to: a decision gate listens with to.one only")
        elif not _literal(_map(_map(to["one"]).get("with")).get("type")):
            errs.append(f"{p}: listen.to.one.with.type: must be a literal event type")


def _floor_rules(n, isfloor, ctx, errs):
    p, t = n["path"], n["task"]
    what = A_FLOOR if isfloor else A_FLOOR_CALL
    ctx["floors"].append(n)
    if "if" in t:
        errs.append(f"{p}: {what} may not have 'if'")
    if _map(t.get("run")).get("await") is False:
        errs.append(f"{p}: {what} may not have run.await: false")
    for a in _ancestors(n):
        if "if" in a["task"]:
            errs.append(f"{p}: {what} may not sit inside '{a['path']}', which has 'if'")
        if "fork" in a["task"] or "try" in a["task"]:
            errs.append(f"{p}: {what} may not sit inside fork or try '{a['path']}'")


def _schema_errors(owner, prefix, sides, errs):
    for side in sides:
        schema = _map(_map(owner.get(side)).get("schema"))
        if "resource" in schema and not _relpath(_map(schema["resource"]).get("endpoint"), "schemas/", ".json"):
            errs.append(f"{prefix + ': ' if prefix else ''}{side}.schema.resource.endpoint: "
                        "must be a relative path under schemas/ ending .json")


def _task_errors(n, nodes, ctx, errs):
    """All per-task rules except floors-by-manifest and `then`. Records floors on ctx."""
    p, t, kind = n["path"], n["task"], n["kind"]
    if "kind" in t:
        errs.append(f"{p}: kind is derived from the task key; do not declare it")
    if kind is None:
        found = sorted(k for k in TASK_KEYS if k in t)
        errs.append(f"{p}: not one OWS task; found task keys {found!r}")
        return
    if kind == "badrun":
        errs.append(f"{p}: run: needs exactly one of container, script, shell, workflow")
        return
    if kind.startswith("refused:"):
        errs.append(f"{p}: task '{kind[8:]}' is not in the accepted subset")
        return
    tm = t.get("timeout")
    if isinstance(tm, str):
        errs.append(f"{p}: timeout: a named timeout needs 'use', which is refused; write it inline")
    elif isinstance(tm, dict):
        _duration(tm.get("after"), p, "timeout.after", errs)
    elif "timeout" in t:
        errs.append(f"{p}: timeout: must be a map")
    for key in ("for", "fork"):
        if key in t and not isinstance(t[key], dict):
            errs.append(f"{p}: {key}: must be a map")
    if kind == "gate":
        _gate_errors(t, p, errs)
    if kind == "wait":
        _duration(t["wait"], p, "wait", errs)
    if kind == "escalation" and isinstance(_map(t["raise"]).get("error"), str):
        errs.append(f"{p}: raise.error: a named error needs 'use', which is refused; write it inline")
    for key, v in (("for.each", _map(t.get("for")).get("each")), ("for.at", _map(t.get("for")).get("at")),
                   ("catch.as", _map(t.get("catch")).get("as"))):
        if isinstance(v, str) and v in RESERVED_VARS:
            errs.append(f"{p}: {key}: '{v}' is a reserved variable name")
    if "for" in t and kind == "container" and "while" in t and not isinstance(_map(t["for"]).get("in"), list):
        errs.append(f"{p}: for: unbounded loop: 'while' needs an inline 'in' array")
    if "try" in t:
        _retry_errors(t, p, errs)
    _schema_errors(t, p, ("input", "output", "export"), errs)
    if kind == "call":
        _call_errors(n, ctx, errs)
    if kind == "emit":
        _emit_errors(n, ctx, errs)
    o = _org_errors(t, p, kind, ctx["catalog"], ctx["roles"], ctx, errs)
    if o is None:
        return
    if kind == "step":
        _step_errors(t, p, o, errs)
    isfloor = kind in LEAF and o.get("floor") is True
    if isfloor:
        ctx["realfloors"].append(n)
        for i, it in enumerate(_acceptance_items(t)):
            if isinstance(it, dict) and "rubric" in it and _num(it.get("sample")) and it["sample"] < 1:
                errs.append(f"{p}: metadata.org.acceptance[{i}].sample: "
                            "a floor item must be judged every run; remove sample")
    if isfloor or n.get("floorcall"):
        _floor_rules(n, isfloor, ctx, errs)


def _floor_list_errors(nodes, ctx, errs):
    if ctx["entry"] is None:
        return
    wf = ctx["wfname"]
    listed = ctx["entry"].get("floors")
    listed = listed if isinstance(listed, list) else []
    byname = {}
    for n in nodes:
        byname.setdefault(n["name"], n)
    for f in listed:
        if not isinstance(f, str) or f not in byname:
            errs.append(f"manifest: workflows.{wf}.floors: floor {_r(f)} is not a task in the workflow")
        elif _org(byname[f]["task"]).get("floor") is not True:
            errs.append(f"{byname[f]['path']}: listed as a floor in the manifest but floor is not true")
    for n in ctx["realfloors"]:
        if n["name"] not in listed:
            errs.append(f"{n['path']}: floor is true but the manifest does not list it as a floor")


def _directives(n):
    t = n["task"]
    out = []
    if "then" in t:
        out.append(("then", t["then"]))
    if n["kind"] == "branch" and isinstance(t["switch"], list):
        for j, case in enumerate(t["switch"]):
            if isinstance(case, dict) and len(case) == 1:
                (cname, c), = case.items()
                if isinstance(c, dict) and "then" in c:
                    out.append((f"switch[{j}].{cname}.then", c["then"]))
    if n["kind"] == "container" and "try" in t and "then" in _map(t.get("catch")):
        out.append(("catch.then", t["catch"]["then"]))
    return out


def _then_errors(nodes, floors, errs):
    """Check every `then`. Linear: a subtree is a contiguous pre-order range, so "does it hold a floor" is a
    range query over the sorted floor positions."""
    lists, names, pos = {}, {}, {}
    for n in nodes:
        pos[id(n)] = len(lists.setdefault(n["list"], []))  # position among the tasks that made it into the list
        lists[n["list"]].append(n)
        names.setdefault(n["list"], {}).setdefault(n["name"], n)
    last = {id(n): n["order"] for n in nodes}  # pre-order position of the last node in each subtree
    for n in reversed(nodes):
        p = n["parent"]
        if p is not None and last[id(n)] > last[id(p)]:
            last[id(p)] = last[id(n)]
    orders = sorted(f["order"] for f in floors)
    by_order = {f["order"]: f for f in floors}

    def first_floor(lo, hi):
        """The first floor with pre-order position in lo..hi, or None."""
        i = bisect.bisect_left(orders, lo)
        return by_order[orders[i]] if i < len(orders) and orders[i] <= hi else None

    def sibling_holding(f, list_id):
        s = f
        while s["list"] != list_id:
            s = s["parent"]
        return s

    for n in nodes:
        kind = n["kind"]
        if kind is None or kind in ("badrun", "escalation") or kind.startswith("refused:"):
            continue
        sibs, p, lid = lists[n["list"]], n["path"], n["list"]
        for where, v in _directives(n):
            if not isinstance(v, str):
                errs.append(f"{p}: {where}: must be a string")
            elif v == "continue":
                continue
            elif v == "end" or (v == "exit" and n["parent"] is None):
                later = first_floor(last[id(n)] + 1, len(nodes))
                if later:
                    errs.append(f"{p}: {where}: '{v}' skips floor '{later['name']}'")
            elif v == "exit":
                f = first_floor(last[id(n)] + 1, last[id(sibs[-1])])
                if f:
                    errs.append(f"{p}: {where}: 'exit' skips floor in '{sibling_holding(f, lid)['path']}'")
            else:
                target = names[lid].get(v)
                if target is None:
                    errs.append(f"{p}: {where}: '{v}' is not a task in the same list")
                elif pos[id(target)] <= pos[id(n)]:
                    errs.append(f"{p}: {where}: '{v}' is not later in the same list; "
                                "a backward jump is an unbounded loop")
                elif pos[id(target)] > pos[id(n)] + 1:
                    f = first_floor(sibs[pos[id(n)] + 1]["order"], last[id(sibs[pos[id(target)] - 1])])
                    if f:
                        errs.append(f"{p}: {where}: '{v}' skips floor in '{sibling_holding(f, lid)['path']}'")


def validate_org(doc, catalog, manifest):
    """Return the list of errors for one workflow document; empty means valid. Never raises."""
    if not isinstance(doc, dict):
        return ["(root): workflow must be a map"]
    errs = _value_errors(doc)
    if errs:
        return errs
    catalog, manifest = _map(catalog), _map(manifest)
    for k in doc:
        if k == "use":
            errs.append("use: not in the accepted subset")
        elif k not in ROOT_KEYS:
            errs.append(f"{k}: unknown top-level key")
    _document_errors(doc, manifest, errs)
    _schema_errors(doc, "", ("input", "output"), errs)
    wfname = _map(doc.get("document")).get("name")
    wfs = _map(manifest.get("workflows"))
    entry = wfs.get(wfname) if isinstance(wfname, str) else None
    ctx = {"catalog": catalog, "manifest": manifest, "wfs": wfs, "wfname": wfname, "floors": [], "realfloors": [], "decision_types": {},
           "checks": _map(manifest.get("checks")),
           "roles": set(_map(manifest.get("roles"))) | {OWNER},
           "entry": _map(entry) if entry is not None else None}
    nodes = []
    try:
        _walk(doc.get("do", []), "", 1, errs, nodes, None)
    except _TooManyTasks as e:
        errs.append(f"{e}: more than {MAX_TASKS} tasks in the workflow")
        return errs
    first = {}
    for n in nodes:
        if not KEBAB.fullmatch(n["name"]):
            errs.append(f"{n['path']}: task name must be kebab-case")
        if n["name"] in first:
            errs.append(f"{n['path']}: duplicate task name '{n['name']}' (first at {first[n['name']]})")
        else:
            first[n["name"]] = n["path"]
    for g in nodes:  # event types that a decision gate listens on, to the first such gate
        if g["kind"] == "gate" and _is_decision_gate(g["task"]):
            for et in _event_types(_map(g["task"]["listen"]).get("to")):
                ctx["decision_types"].setdefault(et, g["path"])
    for n in nodes:
        _task_errors(n, nodes, ctx, errs)
    _floor_list_errors(nodes, ctx, errs)
    _then_errors(nodes, ctx["floors"], errs)
    return errs


# ---------------------------------------------------------------- loading (spec 2.1)

class LoadError(Exception):
    """A file that cannot be loaded. The message starts with the file label."""


class UsageError(Exception):
    """A usage problem (unknown extension, YAML without PyYAML). The message starts with the file label."""


def _dup_hook(label):
    def hook(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise LoadError(f"{label}: duplicate key '{k}'")
            d[k] = v
        return d
    return hook


MAX_LOAD_DEPTH = 512  # same refusal on every Python: the json module's own recursion limit differs by version


def _json_depth_exceeds(text, limit):
    """One linear pass: track string and escape state and bracket depth. No recursion."""
    depth, in_str, esc = 0, False, False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return True
        elif ch in "]}":
            depth -= 1
    return False


def _load_json(path):
    def bad(text):
        raise LoadError(f"{path}: non-finite number {text}")

    def flt(text):
        v = float(text)
        if not math.isfinite(v):
            bad(text)
        return v
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if _json_depth_exceeds(text, MAX_LOAD_DEPTH):
        raise LoadError(f"{path}: nesting too deep to load")
    return json.loads(text, object_pairs_hook=_dup_hook(path), parse_constant=bad, parse_float=flt)


def _yaml_loader(yaml, label):
    class Loader(yaml.SafeLoader):
        pass

    # Copy the resolver table first: changing SafeLoader's own table would change it for every user.
    drop = ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")
    Loader.yaml_implicit_resolvers = {k: [(t, r) for t, r in v if t not in drop]
                                      for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
    Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
                                 list("tTfF"))

    def construct_map(loader, node):
        d = {}
        for knode, vnode in node.value:
            if knode.tag == "tag:yaml.org,2002:merge":
                raise LoadError(f"{label}: merge key '<<' is not accepted; write the keys out")
            k = loader.construct_object(knode, deep=True)
            if k in d:
                raise LoadError(f"{label}: duplicate key '{k}'")
            d[k] = loader.construct_object(vnode, deep=True)
        return d
    Loader.add_constructor("tag:yaml.org,2002:map", construct_map)

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise LoadError(f"{label}: alias '*{self.peek_event().anchor}' is not accepted; write the value out")
        return yaml.SafeLoader.compose_node(self, parent, index)
    Loader.compose_node = compose_node
    return Loader


def _load_yaml(path):
    try:
        import yaml
    except ImportError:
        raise UsageError(f"{path}: reading YAML needs PyYAML; run with uv run --with pyyaml, "
                         "or convert the file to JSON") from None
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=_yaml_loader(yaml, path))


def load_file(path):
    """Load a .json, .yaml or .yml file per spec 2.1. Raises LoadError or UsageError, nothing else."""
    if path.endswith(".json"):
        loader = _load_json
    elif path.endswith((".yaml", ".yml")):
        loader = _load_yaml
    else:
        raise UsageError(f"{path}: unknown extension; use .json, .yaml or .yml")
    try:
        return loader(path)
    except (LoadError, UsageError):
        raise
    except RecursionError:
        raise LoadError(f"{path}: nesting too deep to load") from None
    except OSError as e:
        raise LoadError(f"{path}: {e.strerror or type(e).__name__}") from None
    except Exception as e:  # json.JSONDecodeError, yaml.YAMLError, int() ValueError, bad UTF-8
        msg = str(e)
        if isinstance(e, ValueError) and "Exceeds the limit" in msg and "integer string conversion" in msg:
            raise LoadError(f"{path}: integer longer than 4300 digits") from None
        first = msg.splitlines()[0] if msg else type(e).__name__
        raise LoadError(f"{path}: parse error: {first}") from None


def merge_catalogs(files):
    """files: list of (label, parsed). Returns (merged map, errors)."""
    merged, where, errs = {}, {}, []
    for label, data in files:
        if not isinstance(data, dict):
            errs.append(f"catalog {label}: must be a map of metric names")
            continue
        for name, entry in data.items():
            if name in where:
                errs.append(f"catalog: {name}: defined in {where[name]} and {label}")
            else:
                where[name] = label
                merged[name] = entry
    return merged, errs


def main(argv=None):
    ap = argparse.ArgumentParser(prog="validate_org.py", description="Validate workflow metadata.org.")
    ap.add_argument("--catalog", action="append", required=True, metavar="FILE")
    ap.add_argument("--manifest", required=True, metavar="FILE")
    ap.add_argument("workflows", nargs="+", metavar="WORKFLOW")
    args = ap.parse_args(argv)
    load_errors = []

    def load(path):
        try:
            return load_file(path)
        except LoadError as e:
            load_errors.append(f"ERROR: {e}")
        return None

    try:
        catalogs = [(p, load(p)) for p in args.catalog]
        manifest = load(args.manifest)
        docs = [(p, load(p)) for p in args.workflows]
    except UsageError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if load_errors:
        print("\n".join(load_errors), file=sys.stderr)
        return 1
    catalog, errs = merge_catalogs(catalogs)
    if errs:
        print("\n".join(f"ERROR: {e}" for e in errs), file=sys.stderr)
        return 1
    bad = False
    for path, doc in docs:
        for e in validate_org(doc, catalog, manifest):
            print(f"ERROR: {path}: {e}", file=sys.stderr)
            bad = True
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
