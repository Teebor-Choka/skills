"""Fixtures for amendments, metrics and rollback runs."""
import hashlib
import hmac
import json

from procedure_testkit import step
from runtime_fixtures import LOCATORS, SWE, done, fresh, run, started

# Every stage reports the built-in `rework` metric, so the runtime can observe it.
MET = SWE.replace("metrics: [m]", "metrics: [rework]")

KEY = b"owner-key-the-agents-cannot-read"


def sign(item, decision):
    return hmac.new(KEY, json.dumps([item, decision]).encode(), hashlib.sha256).hexdigest()


def verify(event):
    return hmac.compare_digest(event.get("signature", ""), sign(event["item"], event["decision"]))


def approve(item, decision="approve"):
    return {"type": "owner-decided", "item": item, "decision": decision, "signature": sign(item, decision)}


def change(metrics="rework", direction="down", window="2 stages", reason="tighten review"):
    return f"change:\n  reason: {reason}\n  metrics: [{metrics}]\n  direction: {direction}\n  window: {window}\n"


LINT = (
    "stages:\n  lint:\n    entity: lead\n    needs: [build]\n    consumes: [change]\n"
    "    produces: [lint-report]\n    metrics: [rework]\n"
)


def delta(body=LINT, **kw):
    return f"---\n{change(**kw)}{body}---\n"


def propose(text=None, by="lead", **kw):
    return {"type": "amendment-proposed", "by": by, "delta": text if text is not None else delta(**kw)}


def run_with(*events, state=None, **kw):
    """Fold events with the owner verifier. Returns (state, [actions per event])."""
    state = state if state is not None else started(MET, **kw)[0]
    out = []
    for ev in events:
        state, acts = step(state, ev, verify_owner=verify)
        out.append(acts)
    return state, out


def item_of(acts):
    return next(a["item"] for a in acts if a.get("item"))


def amended(**kw):
    """A run with amendment v2 (adds `lint`) applied at the first stage boundary.

    Returns (state, actions of the stage-done that applied it)."""
    state, acts = run_with(propose(**kw))
    state, _ = run_with(approve(item_of(acts[0])), state=state)
    state, acts = run_with(done("align"), state=state)
    return state, acts[0]


def v2(window="2 stages", policy=None):
    """A run with amendment v2 (adds `lint`) applied: spec has just started under snapshot 2."""
    state, acts = run_with(propose(window=window), policy=policy or {})
    state, _ = run_with(approve(item_of(acts[0])), state=state)
    state, _ = run_with(done("align"), state=state)
    return state


NOTE = {"verdict": "note://defects"}


def regressed_run(**kw):
    """Under v2 with a 3-stage window: review fails once, so rework rises before the window ends."""
    from runtime_fixtures import failed

    state = v2(window="3 stages", **kw)
    state, _ = run_with(done("spec"), done("build"), failed("review", NOTE), state=state)
    state, acts = run_with(done("build"), state=state)
    return state, acts[0]
