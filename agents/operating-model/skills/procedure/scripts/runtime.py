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

from validate_procedure import parse_procedure, validate_text

__all__ = ("new_state", "step", "replay", "register", "HANDLERS", "Rejected")

HANDLERS = {}


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
    return {
        "run_id": run_id,
        "version": 1,
        "status": "new",
        "proc": proc,
        "policy": dict(policy or {}),
        "stages": {sid: {"status": "pending", "locators": {}} for sid in proc["stages"]},
        "log": [],
        "rejected": [],
    }


def _error(reason, event=None):
    return {"do": "error", "reason": reason, "event": event.get("type") if isinstance(event, dict) else None}


def _reject(state, event, reason):
    out = copy.deepcopy(state)
    shown = copy.deepcopy(event) if isinstance(event, (dict, list)) else repr(event)
    out["rejected"].append({"event": shown, "reason": reason})
    return out, [_error(reason, event)]


def step(state, event, *, verify_owner=None):
    """Apply one event. Returns (new state, actions). Pure: `state` is never changed."""
    if not isinstance(event, dict) or not isinstance(event.get("type"), str) or not event["type"]:
        return _reject(state, event, "malformed event: needs a non-empty text 'type'")
    handler = HANDLERS.get(event["type"])
    if handler is None:
        return _reject(state, event, f"unknown event type '{event['type']}'")
    work = copy.deepcopy(state)
    try:
        actions = handler(work, event, Ctx(verify_owner))
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
    """Pending stages whose needs are all done."""
    stages = state["proc"]["stages"]
    return [
        sid
        for sid, st in state["stages"].items()
        if st["status"] == "pending"
        and all(state["stages"][n]["status"] == "done" for n in stages[sid].get("needs") or [])
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
    state["stages"][sid]["status"] = "running"
    spec = state["proc"]["stages"][sid]
    return {
        "do": "start-stage",
        "stage": sid,
        "entity": spec.get("entity"),
        "inputs": _inputs(state, sid),
        "round": 1,
        "verify": True,
    }


def _advance(state):
    actions = [_start(state, sid) for sid in _ready(state)]
    if not actions and all(st["status"] == "done" for st in state["stages"].values()):
        state["status"] = "done"
        actions.append({"do": "run-complete"})
    return actions


@register("run-started")
def _run_started(state, event, ctx):
    if state["status"] != "new":
        raise Rejected("the run has already started")
    state["status"] = "running"
    return _advance(state)


def _require_running(state):
    if state["status"] != "running":
        raise Rejected(f"the run is {state['status']}, not running")


@register("stage-done")
def _stage_done(state, event, ctx):
    _require_running(state)
    sid = event.get("stage")
    st = _stage(state, sid)
    if st["status"] != "running":
        raise Rejected(f"stage '{sid}' is {st['status']}, not running")
    produces = state["proc"]["stages"][sid].get("produces") or []
    locators = event.get("locators") if isinstance(event.get("locators"), dict) else {}
    extra = sorted(set(locators) - set(produces))
    if extra:
        raise Rejected(f"stage '{sid}' registered kinds it does not produce: {', '.join(map(str, extra))}")
    for kind in produces:
        loc = locators.get(kind)
        if not isinstance(loc, str) or not loc.strip():
            raise Rejected(f"stage '{sid}' needs a non-empty locator for '{kind}'")
    st["status"] = "done"
    st["locators"] = {k: locators[k] for k in produces}
    return _advance(state)
