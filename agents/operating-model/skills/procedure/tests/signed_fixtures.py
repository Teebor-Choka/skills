"""Per-entity HMAC identities for signed runs. The caller holds the keys; the reducer holds none."""
import hashlib
import hmac
import json

from procedure_testkit import new_state, step
from runtime_fixtures import LOCATORS, SWE

KEYS = {"pm": b"key-pm", "lead": b"key-lead", "worker": b"key-worker", "executor": b"key-executor"}
OWNER_KEY = b"key-owner"
STAGE_ENTITY = {"align": "pm", "spec": "lead", "build": "worker", "review": "lead", "integrate": "pm"}


def _mac(key, event):
    body = json.dumps({k: v for k, v in event.items() if k != "signature"}, sort_keys=True).encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def seal(event, entity, run_id="run"):
    """Stamp an event as sent by `entity`. The signature covers the event and the run id."""
    event = {**event, "sender": entity}
    return {**event, "signature": _mac(KEYS[entity], {**event, "run_id": run_id})}


def verify_sender(event):
    entity = event.get("sender")
    key = KEYS.get(entity) if entity != "executor" else None
    if key is None or not isinstance(entity, str):
        return None
    return entity if hmac.compare_digest(event.get("signature", ""), _mac(key, event)) else None


def verify_executor(event):
    return event.get("sender") == "executor" and hmac.compare_digest(
        event.get("signature", ""), _mac(KEYS["executor"], event)
    )


def owner_sign(item, decision):
    return hmac.new(OWNER_KEY, json.dumps([item, decision]).encode(), hashlib.sha256).hexdigest()


def verify_owner(event):
    return hmac.compare_digest(event.get("signature", ""), owner_sign(event["item"], event["decision"]))


VERIFIERS = {"verify_sender": verify_sender, "verify_executor": verify_executor, "verify_owner": verify_owner}


def sfresh(text=SWE, **kw):
    return new_state(text, trust="signed", **kw)


def srun(state, *events, **overrides):
    """Fold events through step with all three verifiers. Returns (state, [actions per event])."""
    out = []
    for ev in events:
        state, acts = step(state, ev, **{**VERIFIERS, **overrides})
        out.append(acts)
    return state, out


def go(text=SWE, **kw):
    """A signed run that the executor has started."""
    state, acts = srun(sfresh(text, **kw), seal({"type": "run-started"}, "executor"))
    return state, acts[0]


def sdone(stage, locators=None, by=None):
    return seal(
        {"type": "stage-done", "stage": stage, "locators": locators if locators is not None else LOCATORS[stage]},
        by or STAGE_ENTITY[stage],
    )


def sfailed(stage, by=None, locators=None):
    return seal({"type": "stage-failed", "stage": stage, "reason": "defects", "locators": locators or {}}, by or STAGE_ENTITY[stage])
