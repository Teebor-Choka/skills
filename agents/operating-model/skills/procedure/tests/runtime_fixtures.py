"""A small software-delivery procedure for runtime tests, and helpers to drive a run."""
import copy
import json

from procedure_testkit import new_state, step

SWE = """---
entities:
  pm:
    role: project-manager
    escalates-to: owner
    may-spawn: [lead]
  lead:
    role: team-lead
    escalates-to: pm
    may-spawn: [worker]
  worker:
    role: worker
    escalates-to: lead
    may-spawn: [worker]
kpis:
  flow:
    owner: owner
    metrics: [m]
loops:
  fix:
    stages: [build, review]
    exit:
      kind: verdict
    bound: 3
    on-exhausted: lead
    carries: verdict
stages:
  align:
    entity: pm
    produces: [brief]
    metrics: [m]
  spec:
    floor: true
    entity: lead
    needs: [align]
    consumes: [brief]
    produces: [item]
    metrics: [m]
  build:
    entity: worker
    needs: [spec]
    consumes: [item]
    produces: [change]
    metrics: [m]
  review:
    entity: lead
    needs: [build]
    consumes: [change]
    produces: [verdict]
    metrics: [m]
  integrate:
    entity: pm
    needs: [review]
    consumes: [verdict]
    produces: [merged]
    metrics: [m]
---
"""

LOCATORS = {"align": {"brief": "doc://brief"}, "spec": {"item": "issue://1"},
            "build": {"change": "pr://7"}, "review": {"verdict": "note://ok"},
            "integrate": {"merged": "sha://abc"}}


def fresh(text=SWE, **kw):
    return new_state(text, **kw)


def run(state, *events, **kw):
    """Fold events through step. Returns (state, [actions of every event])."""
    out = []
    for ev in events:
        state, actions = step(state, ev, **kw)
        out.append(actions)
    return state, out


def started(text=SWE, **kw):
    state, acts = run(fresh(text, **kw), {"type": "run-started"})
    return state, acts[0]


def done(stage, locators=None):
    return {"type": "stage-done", "stage": stage, "locators": locators if locators is not None else LOCATORS[stage]}


def failed(stage, locators=None, reason="defects"):
    return {"type": "stage-failed", "stage": stage, "reason": reason, "locators": locators or {}}


def dos(actions):
    return [a["do"] for a in actions]


def of(actions, kind):
    return [a for a in actions if a["do"] == kind]


def snapshot(x):
    return json.dumps(copy.deepcopy(x), sort_keys=True)
