#!/usr/bin/env python3
"""The executor side of a signed run: key custody and the loop that drives the reducer. Stdlib only.

The reducer (`runtime.step`) holds no key and does no work. Whoever runs it supplies verifiers, and
turns each action into work. This module is that caller's half:

- `KeyRing` issues each entity instance its own secret when it is spawned, keeps the executor's own
  key apart from every entity key, and verifies events for `step`.
- `drive` feeds a new signed run through `step`, hands each action to an `Executor`, and feeds the
  events back, until the run settles, waits, stalls or runs out of steps.

An `Executor` is any object with `run(action) -> list[event]`: one context for single mode, board
items and agents for team mode. It seals every event with an `Identity` from the ring.

Custody is by reference, not by isolation. An `Identity` reaches only its own key, never the ring, the
executor key or another instance's key, so one agent cannot sign as another through it. Python cannot
hide a key from code in the same process, though: an agent that shares the process with the ring can
read it. An executor that must resist a hostile agent runs the ring in its own process and gives the
agent a channel that signs, not the key.
"""
import copy
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field

from runtime import step

__all__ = ("Identity", "KeyRing", "Outcome", "drive")

EXECUTOR = "executor"


STAMPED = ("sender", "instance", "nonce", "signature", "run_id")  # set by the ring, never by a caller


def _mac(key, event):
    body = json.dumps({k: v for k, v in event.items() if k != "signature"}, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()


def _sealer(entity, instance, key, run_id):
    """A function that signs for one instance. It closes over that instance's key only."""

    def seal(event):
        stamped = {**{k: v for k, v in event.items() if k not in STAMPED}, "sender": entity, "instance": instance,
                   "nonce": secrets.token_hex(8)}
        return {**stamped, "signature": _mac(key, {**stamped, "run_id": run_id})}

    return seal


class Identity:
    """One entity instance's right to sign. It reaches its own key and nothing else in the ring."""

    __slots__ = ("entity", "instance", "_seal")

    def __init__(self, entity, instance, seal):
        self.entity, self.instance, self._seal = entity, instance, seal

    def seal(self, event):
        """The event, stamped as sent by this instance and signed for this run."""
        return self._seal(event)

    def __repr__(self):
        return f"Identity(entity={self.entity!r}, instance={self.instance!r})"


class KeyRing:
    """Per-run key custody. Issues identities, verifies events, and signs the executor's own facts."""

    def __init__(self, run_id, entities):
        self.run_id = run_id
        self._entities = frozenset(entities)
        self._executor_key = secrets.token_bytes(32)
        self._keys = {}  # instance -> (entity, key)

    def issue(self, entity):
        """A new instance of `entity` with its own secret."""
        if entity not in self._entities:
            raise ValueError(f"'{entity}' is not an entity of this procedure")
        instance, key = secrets.token_hex(8), secrets.token_bytes(32)
        self._keys[instance] = (entity, key)

        return Identity(entity, instance, _sealer(entity, instance, key, self.run_id))

    def revoke(self, instance):
        """Stop accepting events from an instance, for example when its agent ends."""
        self._keys.pop(instance, None)

    def executor_event(self, event):
        """A fact the executor states, signed with the executor's key."""
        stamped = {**{k: v for k, v in event.items() if k not in STAMPED}, "sender": EXECUTOR, "instance": EXECUTOR,
                   "nonce": secrets.token_hex(8)}
        return {**stamped, "signature": _mac(self._executor_key, {**stamped, "run_id": self.run_id})}

    def verify_sender(self, event):
        """The verified entity behind an agent event, or None. Fails closed.

        The signature covers the sender, the instance, a nonce and the run id, so a retargeted event or one
        from another run fails it. Single use is the reducer's job: it records each signature it sees."""
        try:
            entity, key = self._keys.get(event.get("instance"), (None, None))
            ok = key is not None and hmac.compare_digest(str(event.get("signature", "")), _mac(key, event))
        except (TypeError, ValueError):
            return None
        return entity if ok else None

    def verify_executor(self, event):
        try:
            return event.get("sender") == EXECUTOR and hmac.compare_digest(
                str(event.get("signature", "")), _mac(self._executor_key, event))
        except (TypeError, ValueError):
            return False


@dataclass
class Outcome:
    """How a drive ended. `status` is done, halted, waiting (needs a person or an agent), stalled
    (events were refused), exhausted (out of steps) or failed (the executor raised)."""

    state: dict
    status: str
    actions: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def drive(state, executor, ring, *, verify_owner=None, changed=(), max_steps=1000):
    """Run a new signed run to a stop. Every event, including the executor's own, goes through `step`.

    `max_steps` bounds the work: each action handed to the executor and each event fed back counts."""
    if state["trust"] != "signed":
        raise ValueError("drive needs a signed run: an unsigned one cannot tell who sent an event")
    if state["status"] != "new":
        raise ValueError(f"drive starts a new run, not one that is {state['status']}")
    if not (isinstance(changed, (list, tuple)) and all(isinstance(p, str) for p in changed)):
        raise ValueError("'changed' must be a list of paths")
    kw = {"verify_owner": verify_owner, "verify_sender": ring.verify_sender, "verify_executor": ring.verify_executor}
    state, queue = step(state, ring.executor_event({"type": "run-started", "changed": list(changed)}), **kw)
    queue, actions, errors, work, stuck = list(queue), [], [], 1, False
    while queue:
        action = queue.pop(0)
        actions.append(action)
        if action["do"] == "error":
            errors.append(action)
            continue
        kind = action["do"]
        work += 1
        if work > max_steps:
            return Outcome(state, "exhausted", actions, errors)
        try:
            events = executor.run(copy.deepcopy(action))
            if isinstance(events, (str, bytes, dict)):
                raise TypeError(f"run() must return a list of events, not {type(events).__name__}")
            events = list(events)  # a lazy sequence runs here, inside the guard
        except Exception as exc:  # an executor bug ends the drive visibly; it never reaches the reducer
            errors.append({"do": "error", "reason": f"executor failed on '{kind}': {exc}", "event": None})
            return Outcome(state, "failed", actions, errors)
        for event in events:
            work += 1
            if work > max_steps:
                return Outcome(state, "exhausted", actions, errors)
            state, more = step(state, event, **kw)
            stuck = bool(more) and all(a["do"] == "error" for a in more)
            queue.extend(more)
    if state["status"] in ("done", "halted"):
        return Outcome(state, state["status"], actions, errors)
    return Outcome(state, "stalled" if stuck and state["status"] == "running" else "waiting", actions, errors)
