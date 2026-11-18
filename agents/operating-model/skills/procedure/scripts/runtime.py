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
import posixpath
import re

from validate_procedure import parse_procedure, validate_text

__all__ = ("new_state", "step", "replay", "register", "HANDLERS", "Rejected")

HANDLERS = {}
CAPS = ("max-agents", "max-depth")
SETTLED = ("done", "skipped")  # a skipped stage satisfies `needs`: it chose not to run
LIVE = ("running", "blocked")  # advice and spawning work while a run waits on an answer
# Bounds on an event, checked before any copy: a hostile payload must not cost a crash.
MAX_DEPTH, MAX_NODES, MAX_TEXT = 16, 5000, 4096


class Rejected(Exception):
    """A handler raises this to refuse an event. The state is left exactly as it was."""


def register(event_type):
    """Register a handler `fn(state, event, ctx) -> [actions]` for an event type."""

    def wrap(fn):
        HANDLERS[event_type] = fn
        return fn

    return wrap


class Ctx:
    """What a handler may ask of its caller, beyond the state and the event."""

    def __init__(self, verify_owner=None):
        self.verify_owner = verify_owner


def new_state(procedure_text, *, policy=None, strict=True, run_id="run"):
    """Validate and freeze a procedure for one run. Raises ValueError when it is invalid."""
    errs = validate_text(procedure_text, "<procedure>", strict)
    if errs:
        raise ValueError("invalid procedure: " + "; ".join(errs))
    proc, _ = parse_procedure(procedure_text, "<procedure>")
    policy = dict(policy or {})
    for key in CAPS:
        if key in policy and not (type(policy[key]) is int and policy[key] >= 0):
            raise ValueError(f"policy '{key}' must be a non-negative integer, not {policy[key]!r}")
    return {
        "run_id": run_id,
        "version": 1,
        "status": "new",
        "proc": proc,
        "policy": policy,
        "stages": {sid: {"status": "pending", "locators": {}} for sid in proc["stages"]},
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
    if isinstance(event, dict) and _sane(event):
        shown = copy.deepcopy(event)
    elif isinstance(event, dict):
        shown = {"type": _label(event), "dropped": "too large, too deep or not plain data"}
    else:
        shown = {"dropped": f"not an event: {type(event).__name__}"}
    out["rejected"].append({"event": shown, "reason": reason})
    return out, [_error(reason, event)]


def step(state, event, *, verify_owner=None):
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
    verify = kwargs.pop("verify_owner", None)
    state, out = new_state(procedure_text, **kwargs), []
    for event in events:
        state, actions = step(state, event, verify_owner=verify)
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
    actions = []
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


def _raise_to(state, to, asks, frm, blocks=(), loop=None):
    item = f"esc-{len(state.setdefault('items', [])) + 1}"
    state["items"].append(
        {"id": item, "from": frm, "at": to, "asks": asks, "status": "open", "blocks": list(blocks), "loop": loop}
    )
    if to == "owner":
        return {"do": "notify-owner", "item": item, "asks": asks, "from": frm, "default-if-silent": "wait"}
    return {"do": "escalate", "item": item, "to": to, "asks": asks, "from": frm}


def _resume(state, item):
    """An answered item that was blocking the run lets it continue, with a fresh bound for a loop."""
    if state["status"] != "blocked" or not item["blocks"]:
        return []
    state["status"] = "running"
    name = item.get("loop")
    if name:
        state.get("rounds", {}).pop(name, None)
        state.get("carried", {}).pop(name, None)
    _reset(state, item["blocks"], round=1 if name else None)
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
    return _advance(state)


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
    name, lp = _loop_of(state, sid)
    if name and sid == _rank(state, lp["stages"])[-1]:
        if not _holds(state, lp.get("exit")):
            return _next_round(state, name, lp, f"loop '{name}' exit condition not met")
        state.get("carried", {}).pop(name, None)  # the loop is finished: nothing carries over
        state.get("rounds", {}).pop(name, None)
    return _advance(state)


def _next_round(state, name, lp, why, failed=None):
    """Run the loop again, or escalate when its bound is spent."""
    rounds = state.setdefault("rounds", {})
    rounds[name] = rounds.get(name, 1) + 1
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
        return [{"do": "advice-resolved", "item": item["id"], "by": by, "answer": answer}] + _resume(state, item)
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
    signed = {**event, "run_id": state["run_id"]}  # a verifier can bind a decision to this run
    if ctx.verify_owner is None or ctx.verify_owner(signed) is not True:
        raise Rejected("owner decision has no valid signature")
    if item["status"] != "open" or item["at"] != "owner":
        raise Rejected(f"item '{item['id']}' is not waiting on the owner")
    item["status"] = "owner-ruled"
    item["decision"] = event.get("decision")
    actions = [{"do": "owner-ruled", "item": item["id"], "decision": item["decision"]}]
    if item["decision"] == "abort":
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
