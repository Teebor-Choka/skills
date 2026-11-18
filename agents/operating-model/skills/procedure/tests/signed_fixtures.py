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


def owner_sign(item, decision, run_id="run", digest=""):
    """The owner signs the run, the item, what is being decided and the decision."""
    body = json.dumps([run_id, item, digest, decision]).encode()
    return hmac.new(OWNER_KEY, body, hashlib.sha256).hexdigest()


def verify_owner(event):
    want = owner_sign(event.get("item"), event.get("decision"), event.get("run_id"), event.get("item_digest"))
    return hmac.compare_digest(event.get("signature", ""), want)


def decide(state, item, decision):
    """An owner decision signed for this run and for the content of `item` as it now stands."""
    from runtime import item_digest
    return {"type": "owner-decided", "item": item, "decision": decision,
            "signature": owner_sign(item, decision, state["run_id"], item_digest(state, item))}


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
    state, acts = srun(sfresh(text, **kw), seal({"type": "run-started"}, "executor", run_id=kw.get("run_id", "run")))
    return state, acts[0]


def sdone(stage, locators=None, by=None, round=1, run_id="run"):
    return seal(
        {"type": "stage-done", "stage": stage, "round": round,
         "locators": locators if locators is not None else LOCATORS[stage]},
        by or STAGE_ENTITY[stage], run_id,
    )


def sfailed(stage, by=None, locators=None, round=1, run_id="run"):
    return seal({"type": "stage-failed", "stage": stage, "round": round, "reason": "defects",
                 "locators": locators or {}}, by or STAGE_ENTITY[stage], run_id)
