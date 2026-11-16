#!/usr/bin/env python3
"""The run-time core: a pure reducer over an event log. Stdlib only.

    new_state(procedure_text) -> state        resolve and freeze a procedure for one run
    step(state, event) -> (state, actions)    pure: never mutates, never raises on a bad event
    replay(procedure_text, events)            fold a recorded log: same log, same result
    register(event_type)                      add an event handler without editing the core

The state is plain data (it survives JSON). An action is an intent for an executor, such as
`start-stage` or `escalate`. The reducer does no work and calls no agent: every gate lives here, so
an agent cannot talk its way past one.
"""
import copy
import fnmatch
import hashlib
import json
import math
import posixpath
import re

from validate_procedure import apply_delta, parse_frontmatter, parse_procedure, validate_text

__all__ = (
    "new_state", "step", "replay", "register", "collector", "observed_rates", "regressed",
    "iteration_report", "COLLECTORS", "HANDLERS", "Rejected",
)

HANDLERS = {}
CAPS = ("max-agents", "max-depth")
DEFAULT_TOLERANCE = 0.1  # how far a metric may move the wrong way before it counts as a regression
COLLECTORS = {}  # metric name -> fn(counters) -> number. Only code here may observe: agents cannot write one.
COUNTERS = ("stages-done", "rework", "escalations", "refusals", "rounds")
WINDOW = re.compile(r"^([1-9][0-9]{0,2}) stages\Z")  # at most 999: a longer window is never judged
SETTLED = ("done", "skipped")  # a skipped stage satisfies `needs`: it chose not to run
LIVE = ("running", "blocked")  # advice and spawning work while a run waits on an answer
# Bounds on an event, checked before any copy: a hostile payload must not cost a crash.
MAX_DEPTH, MAX_NODES, MAX_TEXT = 16, 5000, 4096


def collector(name):
    """Register a metric the runtime can observe: `fn(counters) -> number`. Trusted code only."""

    def wrap(fn):
        COLLECTORS[name] = fn
        return fn

    return wrap


for _name in ("rework", "escalations", "refusals", "rounds"):
    COLLECTORS[_name] = lambda c, n=_name: c.get(n, 0) / max(1, c.get("stages-done", 0))


def _count(state, name, n=1):
    """Only the runtime counts: an event can carry no number into a metric."""
    state["metrics"][str(state["version"])][name] += n


def _fresh_counters():
    return {name: 0 for name in COUNTERS}


def observed_rates(state, version=None):
    """Each observable metric's rate under a snapshot version: its count per finished stage."""
    counters = state["metrics"][str(version or state["version"])]
    return {name: fn(counters) for name, fn in sorted(COLLECTORS.items())}


def regressed(observed, baseline, direction, threshold):
    """Whether a metric moved the wrong way, by more than the tolerance.

    `down` means lower is better, `up` means higher is better. From a baseline of zero, any
    increase is a regression for `down` and nothing is for `up`."""
    if direction == "down":
        return observed > baseline * (1 + threshold) if baseline > 0 else observed > 0
    return observed < baseline * (1 - threshold)


def iteration_report(state):
    """One record per snapshot: its change, baseline, observed rates, finished stages and outcome."""
    return [
        {
            "version": snap["version"],
            "change": copy.deepcopy(snap["change"]),
            "baseline": dict(snap["baseline"]),
            "observed": observed_rates(state, snap["version"]),
            "stages_done": state["metrics"][str(snap["version"])]["stages-done"],
            "outcome": snap["outcome"],
        }
        for snap in state["snapshots"]
    ]


class Rejected(Exception):
    """A handler raises this to refuse an event. The state is left exactly as it was."""


SOURCES = ("agent", "executor", "owner")
TRUST = ("claims", "signed")


def register(event_type, source="agent"):
    """Register a handler `fn(state, event, ctx) -> [actions]` for an event type."""

    def wrap(fn):
        HANDLERS[event_type] = fn
        return fn

    return wrap


class Ctx:
    """What a handler may ask of its caller, beyond the state and the event."""

    def __init__(self, verify_owner=None):
        self.verify_owner = verify_owner


def new_state(procedure_text, *, policy=None, strict=True, run_id="run", trust="claims"):
    """Validate and freeze a procedure for one run. Raises ValueError when it is invalid."""
    errs = validate_text(procedure_text, "<procedure>", strict)
    if errs:
        raise ValueError("invalid procedure: " + "; ".join(errs))
    proc, _ = parse_procedure(procedure_text, "<procedure>")
    proc.pop("change", None)  # a hypothesis belongs to a delta, not to a frozen base
    policy = dict(policy or {})
    for key in CAPS:
        if key in policy and not (type(policy[key]) is int and policy[key] >= 0):
            raise ValueError(f"policy '{key}' must be a non-negative integer, not {policy[key]!r}")
    tol = policy.get("regression-threshold", DEFAULT_TOLERANCE)
    if type(tol) not in (int, float) or not math.isfinite(tol) or tol < 0:
        raise ValueError(f"policy 'regression-threshold' must be a non-negative number, not {tol!r}")
    safety = policy.get("safety-metrics", [])
    if not isinstance(safety, list) or not all(isinstance(m, str) for m in safety):
        raise ValueError(f"policy 'safety-metrics' must be a list of metric names, not {safety!r}")
    unknown = sorted(set(safety) - set(COLLECTORS))
    if unknown:
        raise ValueError(f"policy 'safety-metrics' names {', '.join(unknown)}, which nothing observes")
    return {
        "run_id": run_id,
        "version": 1,
        "status": "new",
        "proc": proc,
        "policy": policy,
        "stages": {sid: {"status": "pending", "locators": {}} for sid in proc["stages"]},
        "snapshots": [{"version": 1, "proc": copy.deepcopy(proc), "change": None, "baseline": {}, "outcome": "initial"}],
        "pending": [],
        "metrics": {"1": _fresh_counters()},
        "log": [],
        "rejected": [],
    }


def _sane(value):
    """True for plain JSON-like data that is small and shallow enough to copy safely."""
    stack, nodes = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            return False
        kind = type(item)
        if kind is dict:
            if any(type(k) is not str or len(k) > MAX_TEXT for k in item):
                return False
            stack.extend((v, depth + 1) for v in item.values())
        elif kind is list:
            stack.extend((v, depth + 1) for v in item)
        elif kind is str:
            if len(item) > MAX_TEXT:
                return False
        elif kind is int:
            if item.bit_length() > 64:
                return False
        elif not (kind is bool or kind is float or item is None):
            return False
    return True


def _label(event):
    t = event.get("type") if isinstance(event, dict) else None
    return t if isinstance(t, str) and len(t) <= 64 else None


def _error(reason, event=None):
    return {"do": "error", "reason": reason, "event": _label(event)}


def _reject(state, event, reason):
    out = copy.deepcopy(state)
    _count(out, "refusals")
    # A refused event is logged too: it moved a metric, so a replay needs it. One that cannot be
    # stored is logged as a placeholder of an unknown type, which a replay refuses the same way.
    out["log"].append(copy.deepcopy(event) if isinstance(event, dict) and _sane(event) else {"type": "unreadable-event"})
    if isinstance(event, dict) and _sane(event):
        shown = copy.deepcopy(event)
    elif isinstance(event, dict):
        shown = {"type": _label(event), "dropped": "too large, too deep or not plain data"}
    else:
        shown = {"dropped": f"not an event: {type(event).__name__}"}
    out["rejected"].append({"event": shown, "reason": reason})
    return out, [_error(reason, event)]


def step(state, event, *, verify_owner=None, verify_sender=None, verify_executor=None):
    """Apply one event. Returns (new state, actions). Pure: `state` is never changed."""
    if not isinstance(event, dict) or not isinstance(event.get("type"), str) or not event["type"]:
        return _reject(state, event, "malformed event: needs a non-empty text 'type'")
    if not _sane(event):
        return _reject(state, event, "event is too large, too deep or not plain data")
    handler = HANDLERS.get(event["type"])
    if handler is None:
        return _reject(state, event, f"unknown event type '{event['type']}'")
    work, mine = copy.deepcopy(state), copy.deepcopy(event)
    try:
        actions = copy.deepcopy(handler(work, mine, Ctx(verify_owner)))
    except Rejected as exc:
        return _reject(state, event, str(exc))
    except Exception as exc:  # a handler bug must be visible and must change nothing
        return _reject(state, event, f"internal error in '{event['type']}': {type(exc).__name__}: {exc}")
    work["log"].append(copy.deepcopy(event))
    return work, actions


def replay(procedure_text, events, **kwargs):
    """Fold a recorded event log from a fresh state. Returns (state, every action in order)."""
    verifiers = {k: kwargs.pop(k, None) for k in ("verify_owner", "verify_sender", "verify_executor")}
    state, out = new_state(procedure_text, **kwargs), []
    for event in events:
        state, actions = step(state, event, **verifiers)
        out += actions
    return state, out


# ---------------------------------------------------------------- stages


def _stage(state, sid):
    if not isinstance(sid, str) or sid not in state["stages"]:
        raise Rejected(f"unknown stage '{sid}'")
    return state["stages"][sid]


def _ready(state):
    """Pending stages whose needs are all settled."""
    stages = state["proc"]["stages"]
    return [
        sid
        for sid, st in state["stages"].items()
        if st["status"] == "pending"
        and all(state["stages"][n]["status"] in SETTLED for n in stages[sid].get("needs") or [])
    ]


def _inputs(state, sid):
    """The locators for exactly the kinds the stage consumes."""
    wanted = state["proc"]["stages"][sid].get("consumes") or []
    found = {}
    for st in state["stages"].values():
        for kind, loc in st["locators"].items():
            if kind in wanted:
                found[kind] = loc
    return {k: found[k] for k in wanted if k in found}


def _start(state, sid):
    st = state["stages"][sid]
    st["status"] = "running"
    spec = state["proc"]["stages"][sid]
    inputs = _inputs(state, sid)
    name, lp = _loop_of(state, sid)
    carried = state.get("carried", {}).get(name) if name else None
    if carried and sid == _rank(state, lp["stages"])[0]:
        inputs[lp["carries"]] = carried
    return {
        "do": "start-stage",
        "stage": sid,
        "entity": spec.get("entity"),
        "inputs": inputs,
        "round": st.get("round", 1),
        "verify": True,
    }


def _advance(state):
    """Start every ready stage, skipping those whose `when` fails, until nothing new is ready."""
    actions = _apply_pending(state)
    while True:
        skipped = False
        for sid in _ready(state):
            when = state["proc"]["stages"][sid].get("when")
            if when is not None and not _holds(state, when):
                state["stages"][sid]["status"] = "skipped"
                actions.append({"do": "stage-skipped", "stage": sid, "why": "when not met"})
                skipped = True
            else:
                actions.append(_start(state, sid))
        if not skipped:
            break
    if all(st["status"] in SETTLED for st in state["stages"].values()):
        state["status"] = "done"
        actions.append({"do": "run-complete"})
    return actions


def _holds(state, pred):
    """Evaluate a closed predicate map against the run. Every key must hold."""
    for key, val in (pred or {}).items():
        if key == "kind":
            ok = any(val in st["locators"] for st in state["stages"].values())
        elif key == "policy":
            ok = bool(state["policy"].get(val))
        elif key == "paths":
            ok = any(fnmatch.fnmatchcase(p, g) for p in state.get("changed", []) for g in val)
        else:
            ok = False
        if not ok:
            return False
    return True


def _loop_of(state, sid):
    for name, lp in (state["proc"].get("loops") or {}).items():
        if sid in lp.get("stages", []):
            return name, lp
    return None, None


def _rank(state, sids):
    """The stages in `needs` order."""
    stages, order, seen = state["proc"]["stages"], [], set()

    def visit(s):
        if s in seen or s not in sids:
            return
        seen.add(s)
        for n in stages[s].get("needs") or []:
            visit(n)
        order.append(s)

    for s in sorted(sids):
        visit(s)
    return order


def _descendants(state, sids):
    """Every stage that, directly or not, needs one of `sids`."""
    stages, found, grew = state["proc"]["stages"], set(), True
    while grew:
        grew = False
        for sid, spec in stages.items():
            if sid not in found and any(n in sids or n in found for n in spec.get("needs") or []):
                found.add(sid)
                grew = True
    return found


def _reset(state, sids, round=None):
    for sid in sids:
        keep = state["stages"][sid].get("round", 1) if round is None else round
        state["stages"][sid] = {"status": "pending", "locators": {}, "round": keep}


def _invalidate(state, sids, keep=None):
    """Redo `sids` and everything downstream of them: nothing may keep an output built on old input.

    A stage still running on the old input is cancelled, so its late result is refused."""
    span = _rank(state, set(sids) | _descendants(state, set(sids)))
    _count(state, "rework", sum(1 for sid in span if state["stages"][sid]["status"] in ("done", "running", "failed")))
    actions = [
        {"do": "stage-cancelled", "stage": sid, "why": "its input is being redone"}
        for sid in span
        if state["stages"][sid]["status"] == "running" and sid != keep
    ]
    _reset(state, span)
    return actions


def _escalate_up(state, entity, asks, blocks=()):
    """Put a question to the entity above `entity`, or to the owner at the top of the ladder."""
    ents = state["proc"].get("entities") or {}
    to = ents[entity]["escalates-to"] if entity in ents else "owner"
    return _raise_to(state, to, asks, entity, blocks)


def _raise_to(state, to, asks, frm, blocks=(), loop=None, **extra):
    """Open an item for `to`. `extra` keys go on the item. `change` and `protected` are shown too."""
    item = f"esc-{len(state.setdefault('items', [])) + 1}"
    if extra.get("kind") not in ("amendment", "rollback"):  # a proposal is not a sign of trouble
        _count(state, "escalations")
    state["items"].append(
        {"id": item, "from": frm, "at": to, "asks": asks, "status": "open", "blocks": list(blocks),
         "blocking": bool(blocks), "loop": loop, **extra}
    )
    shown = {k: extra[k] for k in ("change", "protected", "kind", "evidence") if k in extra}
    if to == "owner":
        return {"do": "notify-owner", "item": item, "asks": asks, "from": frm, "default-if-silent": "wait", **shown}
    return {"do": "escalate", "item": item, "to": to, "asks": asks, "from": frm, **shown}


def _resume(state, item):
    """An answered item that was blocking the run lets it continue, with a fresh bound for a loop."""
    if state["status"] != "blocked" or not item.get("blocking"):
        return []
    state["status"] = "running"
    name = item.get("loop")
    if name:
        state.get("rounds", {}).pop(name, None)
        state.get("carried", {}).pop(name, None)
    _reset(state, [sid for sid in item["blocks"] if sid in state["stages"]], round=1 if name else None)
    return _advance(state)


def _bound(text):
    m = re.search(r"\d+", str(text or ""))
    return int(m.group()) if m else 1


def _norm_path(path):
    norm = posixpath.normpath(path)
    if norm.startswith("/") or norm == ".." or norm.startswith("../"):
        raise Rejected(f"path '{path}' leaves the project")
    return norm


@register("run-started")
def _run_started(state, event, ctx):
    if state["status"] != "new":
        raise Rejected("the run has already started")
    changed = event.get("changed", [])
    if not isinstance(changed, list) or not all(isinstance(p, str) and p for p in changed):
        raise Rejected("'changed' must be a list of paths")
    state["changed"] = [_norm_path(p) for p in changed]
    state["status"] = "running"
    declared = {m for st in state["proc"]["stages"].values() for m in st.get("metrics") or []}
    missing = sorted(declared - set(COLLECTORS))
    notice = [{"do": "metrics-unobserved", "metrics": missing}] if missing else []
    return notice + _advance(state)


def _require_running(state):
    if state["status"] != "running":
        raise Rejected(f"the run is {state['status']}, not running")


def _require_live(state):
    if state["status"] not in LIVE:
        raise Rejected(f"the run is {state['status']}: no advice or spawning now")


def _locators(sid, spec, event, *, whole):
    """The locators an event registers: only kinds the stage produces, each non-empty text."""
    raw = event.get("locators")
    locators = raw if isinstance(raw, dict) else {}
    produces = spec.get("produces") or []
    extra = sorted(set(locators) - set(produces))
    if extra:
        raise Rejected(f"stage '{sid}' registered kinds it does not produce: {', '.join(extra)}")
    for kind, loc in locators.items():
        if not isinstance(loc, str) or not loc.strip():
            raise Rejected(f"stage '{sid}' needs a non-empty locator for '{kind}'")
    missing = [k for k in produces if k not in locators]
    if whole and missing:
        raise Rejected(f"stage '{sid}' needs a non-empty locator for '{missing[0]}'")
    return locators


@register("stage-done")
def _stage_done(state, event, ctx):
    _require_running(state)
    sid = event.get("stage")
    st = _stage(state, sid)
    if st["status"] != "running":
        raise Rejected(f"stage '{sid}' is {st['status']}, not running")
    spec = state["proc"]["stages"][sid]
    locators = _locators(sid, spec, event, whole=True)
    st["status"] = "done"
    st["locators"] = {k: locators[k] for k in spec.get("produces") or []}
    _count(state, "stages-done")
    verdict = _evaluate(state)
    name, lp = _loop_of(state, sid)
    if name and sid == _rank(state, lp["stages"])[-1]:
        if not _holds(state, lp.get("exit")):
            return verdict + _next_round(state, name, lp, f"loop '{name}' exit condition not met")
        state.get("carried", {}).pop(name, None)  # the loop is finished: nothing carries over
        state.get("rounds", {}).pop(name, None)
    return verdict + _advance(state)


def _next_round(state, name, lp, why, failed=None):
    """Run the loop again, or escalate when its bound is spent."""
    rounds = state.setdefault("rounds", {})
    rounds[name] = rounds.get(name, 1) + 1
    _count(state, "rounds")
    members = _rank(state, lp["stages"])
    if rounds[name] > _bound(lp["bound"]):
        state["status"] = "blocked"
        asks = f"loop '{name}' spent its bound of {lp['bound']} rounds: {why}"
        return [_raise_to(state, lp["on-exhausted"], asks, None, members, loop=name)]
    actions = _invalidate(state, members, keep=failed)
    for sid in members:
        state["stages"][sid]["round"] = rounds[name]
    return actions + _advance(state)


@register("stage-failed")
def _stage_failed(state, event, ctx):
    _require_running(state)
    sid = event.get("stage")
    st = _stage(state, sid)
    if st["status"] != "running":
        raise Rejected(f"stage '{sid}' is {st['status']}, not running")
    spec = state["proc"]["stages"][sid]
    locators = _locators(sid, spec, event, whole=False)
    name, lp = _loop_of(state, sid)
    reason = str(event.get("reason") or "failed")[:200]
    if name:
        carried, carries = state.setdefault("carried", {}), lp.get("carries")
        if carries and carries in locators:
            carried[name] = locators[carries]
        else:
            carried.pop(name, None)  # only what this round found goes into the next
        return _next_round(state, name, lp, reason, failed=sid)
    retry = spec.get("on-fail")
    if retry:
        count = state.setdefault("retries", {}).get(sid, 0) + 1
        state["retries"][sid] = count
        if count <= _bound(retry.get("bound")):
            span = _between(state, retry["to"], sid)
            actions = _invalidate(state, span, keep=sid)
            for member in span:
                state["stages"][member]["round"] = count + 1
            return actions + _advance(state)
    st["status"] = "failed"
    state["status"] = "blocked"
    return [_escalate_up(state, spec.get("entity"), f"stage '{sid}' failed: {reason}", [sid])]


def _between(state, start, end):
    """`start`, `end` and every stage that runs after `start` and before `end`."""
    stages = state["proc"]["stages"]

    def anc(s):
        out, todo = set(), list(stages[s].get("needs") or [])
        while todo:
            n = todo.pop()
            if n not in out:
                out.add(n)
                todo.extend(stages[n].get("needs") or [])
        return out

    inside = {s for s in stages if (s == start or start in anc(s)) and (s == end or s in anc(end))}
    return _rank(state, inside)


# ---------------------------------------------------------------- the ladder


def _item(state, item_id):
    for item in state.get("items", []):
        if item["id"] == item_id:
            return item
    raise Rejected(f"unknown item '{item_id}'")


def _entity(state, name):
    if not isinstance(name, str) or name not in (state["proc"].get("entities") or {}):
        raise Rejected(f"unknown entity '{name}'")
    return state["proc"]["entities"][name]


@register("advice-requested")
def _advice_requested(state, event, ctx):
    """A specialist asks the entity above it. The asker keeps its own work."""
    _require_live(state)
    frm = event.get("from")
    _entity(state, frm)
    question = event.get("question")
    if not isinstance(question, str) or not question.strip():
        raise Rejected("advice needs a question")
    return [_escalate_up(state, frm, question)]


@register("advice-given")
def _advice_given(state, event, ctx):
    _require_live(state)
    item = _item(state, event.get("item"))
    by, answer = event.get("by"), event.get("answer")
    _entity(state, by)  # the owner is not an entity: its answer comes only through `owner-decided`
    if item["status"] != "open" or item["at"] != by:
        raise Rejected(f"item '{item['id']}' is with '{item['at']}', not '{by}'")
    if not isinstance(answer, str):
        raise Rejected("an answer is 'sure' or 'unsure: <why>'")
    if answer.split(":")[0].strip() == "sure":
        item["status"] = "advice-ruled"
        resolved = [{"do": "advice-resolved", "item": item["id"], "by": by, "answer": answer}]
        if item.get("kind") == "rollback":
            if not _rollback_current(state, item["target"]):
                return resolved + [_stale(state, item)]
            state["pending"].append({"kind": "rollback", "item": item["id"], "to": item["target"]})
            return resolved + _apply_pending(state) + (_advance(state) if state["status"] == "running" else [])
        return resolved + _resume(state, item)
    kind, _, why = answer.partition(":")
    if kind.strip() != "unsure" or not why.strip():
        raise Rejected("an answer is 'sure' or 'unsure: <why>'")
    return [_forward(item, _entity(state, by)["escalates-to"], by, why.strip())]


def _forward(item, to, frm, analysis):
    """The same item climbs one rung. The analysis so far travels with it."""
    item["at"] = to
    item.setdefault("analysis", []).append(analysis)
    shared = {"item": item["id"], "asks": item["asks"], "from": frm, "analysis": list(item["analysis"])}
    if to == "owner":
        return {"do": "notify-owner", "default-if-silent": "wait", **shared}
    return {"do": "escalate", "to": to, **shared}


@register("owner-decided")
def _owner_decided(state, event, ctx):
    """Only a verified owner decision applies. With none, none does. `abort` ends the run."""
    item = _item(state, event.get("item"))
    if state["status"] in ("done", "halted"):
        raise Rejected(f"the run is {state['status']}: nothing is left to decide")
    # The verifier sees the run and a digest of what is being decided, so it can bind to both.
    signed = {**event, "run_id": state["run_id"], "item_digest": _digest(item)}
    if ctx.verify_owner is None or ctx.verify_owner(signed) is not True:
        raise Rejected("owner decision has no valid signature")
    if item["status"] != "open" or item["at"] != "owner":
        raise Rejected(f"item '{item['id']}' is not waiting on the owner")
    kind, decision = item.get("kind"), event.get("decision")
    if kind == "rollback" and decision not in ("rollback", "keep"):
        raise Rejected("a rollback is decided with 'rollback' or 'keep'")
    if kind == "amendment" and decision not in ("approve", "reject"):
        raise Rejected("a change is decided with 'approve' or 'reject'")
    item["status"], item["decision"] = "owner-ruled", decision
    actions = [{"do": "owner-ruled", "item": item["id"], "decision": decision}]
    if kind == "rollback":
        if decision == "keep":
            _mark(state, item["target"] + 1, "kept")
            return actions
        if not _rollback_current(state, item["target"]):
            return actions + [_stale(state, item)]
        state["pending"].append({"kind": "rollback", "item": item["id"], "to": item["target"]})
        return actions + _apply_pending(state) + (_advance(state) if state["status"] == "running" else [])
    if kind == "amendment":
        if decision != "approve":
            return actions
        state["pending"].append(
            {"kind": "amendment", "item": item["id"], "delta": item["delta"], "base_version": item["base_version"]}
        )
        return actions + _apply_pending(state) + (_advance(state) if state["status"] == "running" else [])
    if decision == "abort":
        state["status"] = "halted"
        return actions + [{"do": "run-halted", "item": item["id"]}]
    return actions + _resume(state, item)


# ---------------------------------------------------------------- spawning


@register("spawn-requested")
def _spawn_requested(state, event, ctx):
    """Authority runs down the ladder: an entity spawns only the roles its `may-spawn` lists."""
    _require_live(state)
    by, role, why = event.get("by"), event.get("role"), event.get("why")
    allowed = _entity(state, by).get("may-spawn") or []
    if role not in (state["proc"].get("entities") or {}):
        raise Rejected(f"unknown role '{role}'")
    if role not in allowed:
        raise Rejected(f"'{by}' may not spawn '{role}': not in may-spawn")
    if not isinstance(why, str) or not why.strip():
        raise Rejected("a spawn must say why")
    spawned = state.setdefault("spawned", [])
    parent = event.get("parent")
    if parent is not None and not (type(parent) is int and 1 <= parent <= len(spawned)):
        raise Rejected(f"parent {parent!r} is not an agent the runtime issued")
    # Depth comes from what the runtime issued, never from a claim: leaving out `parent` must not
    # reset it, so the spawner counts as at least as deep as the deepest agent of its own role.
    known = [spawned[parent - 1]["depth"]] if parent is not None else []
    depth = 1 + max([0, *known, *(a["depth"] for a in spawned if a["role"] == by)])
    for key, value in (("max-agents", len(spawned) + 1), ("max-depth", depth)):
        cap = state["policy"].get(key)
        if cap is not None and value > cap:
            return [_raise_to(state, "owner", f"spawn of '{role}' by '{by}' exceeds {key} {cap}: raise the cap?", by)]
    spawned.append({"id": len(spawned) + 1, "role": role, "by": by, "why": why.strip(), "depth": depth})
    return [{"do": "spawn", "id": len(spawned), "role": role, "by": by, "why": why.strip(), "depth": depth}]


# ---------------------------------------------------------------- amendments and snapshots


def _apply_pending(state):
    """Apply approved changes in order, at a stage boundary: never while a stage is running.

    Each is checked again when it applies. One that no longer fits is reported, never dropped."""
    if not state["pending"] or any(st["status"] == "running" for st in state["stages"].values()):
        return []
    queue, state["pending"] = state["pending"], []
    actions = []
    for pending in queue:
        actions += _apply_one(state, pending)
    return actions


def _apply_one(state, pending):
    if pending["kind"] == "rollback":
        item = next((i for i in state.get("items", []) if i["id"] == pending["item"]), None)
        if not pending.get("auto") and not _rollback_current(state, pending["to"]):
            return [_stale(state, item)]
        return _roll_back(state, pending)
    if pending["base_version"] != state["version"]:
        return [{"do": "amendment-failed", "item": pending["item"],
                 "errors": ["the procedure changed since this was proposed: propose it again"]}]
    merged, errs, _ = apply_delta(state["proc"], pending["delta"], "<amendment>", True, ratified=True)
    if errs:
        return [{"do": "amendment-failed", "item": pending["item"], "errors": errs}]
    change = parse_frontmatter(pending["delta"], "<amendment>")[0].get("change")
    return _install(state, merged, change)


def _install(state, proc, change, outcome="pending"):
    """Make `proc` the next snapshot. Stages already run keep their status."""
    baseline = observed_rates(state)
    version = state["version"] + 1
    if state["snapshots"][-1]["outcome"] == "pending":
        state["snapshots"][-1]["outcome"] = "superseded"  # replaced before its window ended
    state["snapshots"].append(
        {"version": version, "proc": copy.deepcopy(proc), "change": copy.deepcopy(change), "baseline": baseline, "outcome": outcome}
    )
    old = state["proc"]["stages"]
    state["stages"] = {sid: state["stages"].get(sid, {"status": "pending", "locators": {}}) for sid in proc["stages"]}
    state["proc"], state["version"] = copy.deepcopy(proc), version
    state["metrics"][str(version)] = _fresh_counters()
    for item in state.get("items", []):
        item["blocks"] = [sid for sid in item["blocks"] if sid in state["stages"]]  # never wait on a stage that is gone
    # A finished stage whose inputs or outputs changed no longer holds what its dependents need.
    redo = [
        sid for sid, spec in proc["stages"].items()
        if sid in old and state["stages"][sid]["status"] == "done"
        and any(spec.get(k) != old[sid].get(k) for k in ("produces", "consumes"))
    ]
    return [{"do": "snapshot-applied", "version": version, "change": change}] + (_invalidate(state, redo) if redo else [])


@register("amendment-proposed")
def _amendment_proposed(state, event, ctx):
    """An entity drafts a change to the procedure. It never applies on its own: the owner decides."""
    _require_live(state)
    by = event.get("by")
    _entity(state, by)
    delta = event.get("delta")
    if not isinstance(delta, str) or not delta.strip():
        raise Rejected("an amendment needs a delta")
    merged, errs, protected = apply_delta(state["proc"], delta, "<amendment>", True, ratified=True)
    if errs:
        raise Rejected("amendment is invalid: " + "; ".join(errs))
    if merged == state["proc"]:
        raise Rejected("amendment changes nothing")
    change = parse_frontmatter(delta, "<amendment>")[0].get("change") or {}
    for metric in change.get("metrics", []):
        if metric not in COLLECTORS:
            raise Rejected(f"metric '{metric}' has no collector, so the change cannot be judged")
    if not WINDOW.match(str(change.get("window", ""))):
        raise Rejected(f"window '{change.get('window')}' must be a count of stages, such as '5 stages'")
    asks = f"approve change: {change.get('reason')}"
    return [
        _raise_to(state, "owner", asks, by, kind="amendment", delta=delta, change=change, protected=protected,
                  base_version=state["version"])
    ]


# ---------------------------------------------------------------- judging a change


def _digest(item):
    """What the owner is deciding on, so a signature can cover content and not only an id."""
    body = [item.get("kind", "escalation"), item.get("delta"), item.get("target"), item["asks"], item["at"], item.get("base_version")]
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def _rollback_current(state, target):
    """A rollback still applies only to the change it was raised for, and only while it is the latest."""
    return state["version"] == target + 1 and state["snapshots"][-1]["outcome"] == "regressed"


def _stale(state, item):
    if item is not None:
        item["status"] = "stale"
    return {"do": "rollback-stale", "item": item["id"] if item else None, "why": "the change it was raised for is no longer the current one"}


def _mark(state, version, outcome):
    for snap in state["snapshots"]:
        if snap["version"] == version:
            snap["outcome"] = outcome


def _project_manager(state):
    for name, ent in (state["proc"].get("entities") or {}).items():
        if ent.get("role") == "project-manager":
            return name
    return "owner"


def _evaluate(state):
    """Once a change's window is spent, compare it with its baseline and act on the result."""
    snap = state["snapshots"][-1]
    change = snap["change"]
    if snap["outcome"] != "pending" or not change:
        return []
    window = int(WINDOW.match(change["window"]).group(1))
    if state["metrics"][str(state["version"])]["stages-done"] < window:
        return []
    tol = state["policy"].get("regression-threshold", DEFAULT_TOLERANCE)
    rates = observed_rates(state)

    def evidence(names, direction):
        return {m: {"baseline": snap["baseline"].get(m, 0.0), "observed": rates.get(m, 0.0), "direction": direction} for m in names}

    named = evidence(change["metrics"], change["direction"])
    safety = evidence([m for m in state["policy"].get("safety-metrics", []) if m in rates], "down")
    bad_safety = sorted(m for m, e in safety.items() if regressed(e["observed"], e["baseline"], "down", tol))
    bad_named = sorted(m for m, e in named.items() if regressed(e["observed"], e["baseline"], e["direction"], tol))
    if bad_safety:
        snap["outcome"] = "regressed"  # becomes rolled-back only when the rollback is installed
        state["pending"].append({"kind": "rollback", "item": None, "to": snap["version"] - 1, "auto": True})
        shown = {**named, **{m: safety[m] for m in bad_safety}}
        return [
            {"do": "change-regressed", "version": snap["version"], "metrics": shown, "auto": True},
            {"do": "inform-owner", "text": f"change {snap['version']} rolled back: safety metric {', '.join(bad_safety)} regressed"},
        ] + _apply_pending(state)
    if bad_named:
        snap["outcome"] = "regressed"
        shown = {m: named[m] for m in bad_named}
        asks = f"change {snap['version']} regressed {', '.join(bad_named)}: roll it back?"
        ask = _raise_to(state, _project_manager(state), asks, None, kind="rollback", target=snap["version"] - 1, evidence=shown)
        return [{"do": "change-regressed", "version": snap["version"], "metrics": shown, "auto": False}, ask]
    snap["outcome"] = "confirmed"
    return [{"do": "change-confirmed", "version": snap["version"], "metrics": named}]


def _roll_back(state, pending):
    """Restore the procedure of an earlier snapshot as a new snapshot. History is never edited."""
    target = next(s for s in state["snapshots"] if s["version"] == pending["to"])
    for snap in state["snapshots"]:
        if snap["version"] == state["version"] and snap["outcome"] in ("pending", "regressed"):
            snap["outcome"] = "rolled-back"
    change = {"rollback-of": state["version"], "auto": bool(pending.get("auto"))}
    return _install(state, target["proc"], change, outcome="rollback")
