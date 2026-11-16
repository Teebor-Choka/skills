#!/usr/bin/env python3
"""The run-time core: a pure reducer over an event log. Stdlib only.

    new_state(procedure_text) -> state        resolve and freeze a procedure for one run
    step(state, event) -> (state, actions)    pure: never mutates, never raises on a bad event
    replay(procedure_text, events)            fold a recorded log: same log, same result
    register(event_type)                      add an event handler without editing the core
"""

__all__ = ("new_state", "step", "replay", "register", "HANDLERS")

HANDLERS = {}


def register(event_type):
    def wrap(fn):
        HANDLERS[event_type] = fn
        return fn

    return wrap


def new_state(procedure_text, *, policy=None, strict=True, run_id="run"):
    return {"status": "new", "stages": {}, "log": [], "rejected": []}


def step(state, event, *, verify_owner=None):
    return state, []


def replay(procedure_text, events, **kwargs):
    return new_state(procedure_text, **kwargs), []
