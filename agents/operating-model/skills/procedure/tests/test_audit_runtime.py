"""Audit leads on the reducer and the validator, pinned as failing tests first."""
from collections import Counter

import pytest
from metrics_fixtures import MET, approve, delta, item_of, propose, run_with, v2
from procedure_testkit import step
from runtime import new_state
from runtime_fixtures import SWE, dos, done, of
from signed_fixtures import KEYS, decide, go, sdone, seal, sfailed, sfresh, srun
from validate_procedure import apply_delta, parse_procedure

from executor import KeyRing, drive


def counters(state):
    return state["metrics"][str(state["version"])]


def at_owner():
    state, _ = go()
    state, acts = srun(state, sfailed("align"))
    return state, acts[0][0]["item"]


def refused(acts, word=None):
    return dos(acts) == ["error"] and (word is None or word in acts[0]["reason"])


# ---- an unsigned owner event moves nothing in a signed run

def test_an_unsigned_owner_decided_for_an_unknown_item_is_not_counted_or_logged():
    state, _ = go()
    before = (counters(state)["refusals"], len(state["log"]), len(state["rejected"]))
    state, acts = srun(state, {"type": "owner-decided", "item": "nope", "decision": "retry", "signature": "x"})
    assert refused(acts[0])
    assert (counters(state)["refusals"], len(state["log"]), len(state["rejected"])) == before


def test_an_unsigned_owner_decided_on_a_halted_run_is_not_counted_or_logged():
    state, item = at_owner()
    state, _ = srun(state, decide(state, item, "abort"))
    assert state["status"] == "halted"
    before = (counters(state)["refusals"], len(state["log"]))
    state, acts = srun(state, {"type": "owner-decided", "item": item, "decision": "retry", "signature": "x"})
    assert refused(acts[0]) and (counters(state)["refusals"], len(state["log"])) == before


def test_a_verified_owner_decision_that_is_refused_is_spent():
    state, item = at_owner()
    first, second = decide(state, item, "retry"), decide(state, item, "abort")
    state, _ = srun(state, first)
    r0 = counters(state)["refusals"]
    state, acts = srun(state, second, second, second)
    assert refused(acts[0], "not waiting on the owner")
    assert refused(acts[1], "replay") and refused(acts[2], "replay")
    assert counters(state)["refusals"] == r0 + 1


# ---- an amendment that routes around a floor stage reaches the owner flagged

FLOOR_REWIRE = "stages:\n  build:\n    needs: [align]\n    consumes: [brief]\n"


def test_a_ratified_delta_that_sheds_a_floor_ordering_is_flagged_protected():
    base, _ = parse_procedure(MET, "<m>")
    merged, errs, protected = apply_delta(base, delta(body=FLOOR_REWIRE), "<d>", True, ratified=True)
    assert errs == [] and protected is True


def test_the_owner_is_told_a_floor_rewire_touches_the_protected_set():
    state, acts = run_with(propose(text=delta(body=FLOOR_REWIRE)))
    notice = next(a for a in acts[0] if a["do"] == "notify-owner")
    assert notice["protected"] is True


# ---- an automatic rollback does not revert a change queued ahead of it

LINT2 = "stages:\n  lint2:\n    entity: lead\n    needs: [build]\n    consumes: [change]\n    produces: [lint2-report]\n    metrics: [rework]\n"


def test_an_auto_rollback_does_not_revert_an_approved_amendment_queued_ahead_of_it():
    state = v2(window="1 stages", policy={"safety-metrics": ["escalations"]})
    state, acts = run_with(propose(text=delta(body=LINT2)), state=state)
    state, _ = run_with(approve(item_of(acts[0])), state=state)  # queued: spec is running
    state, _ = run_with({"type": "advice-requested", "from": "worker", "question": "q"}, state=state)
    state, acts = run_with(done("spec"), state=state)
    assert "amendment-failed" in dos(acts[0])
    reverted = [a for a in acts[0] if a["do"] == "snapshot-applied" and a.get("change", {}).get("rollback-of") == 3]
    assert not reverted


# ---- a cancelled stage's late result is refused after the stage restarts

def test_a_cancelled_stages_late_result_is_refused_once_the_stage_restarts():
    from test_runtime_hardening import NOTE, SEC
    state = sfresh(SEC)
    state, _ = srun(state, seal({"type": "run-started", "changed": ["src/auth/x.py"]}, "executor"))
    state, _ = srun(state, sdone("align"), sdone("spec"), sdone("build"))
    late = seal({"type": "stage-done", "stage": "audit", "round": 1, "locators": {"report": "r://late"}}, "lead")
    state, acts = srun(state, sfailed("review", by="lead", locators=NOTE))
    assert any(a["do"] == "stage-cancelled" and a["stage"] == "audit" for a in acts[0])
    state, _ = srun(state, sdone("build", {"change": "pr://8"}, round=2))
    assert state["stages"]["audit"]["status"] == "running"
    state, acts = srun(state, late)
    assert refused(acts[0]) and state["stages"]["audit"]["status"] == "running"


SIDE = """---
entities:
  w:
    role: worker
    escalates-to: owner
stages:
  a:
    entity: w
    produces: [x]
  b:
    entity: w
    needs: [a]
    consumes: [x]
    produces: [y]
    on-fail:
      to: a
      bound: 2 rounds
  c:
    entity: w
    needs: [a]
    consumes: [x]
    produces: [z]
---
"""


def test_drive_does_not_hand_the_executor_a_start_for_a_stage_step_has_cancelled():
    class Ex:
        def __init__(self, ring):
            self.ring, self.starts, self.failed = ring, Counter(), False

        def run(self, action):
            if action["do"] != "start-stage":
                return []
            sid = action["stage"]
            self.starts[sid] += 1
            who = self.ring.issue("w")
            if sid == "a":
                return [who.seal({"type": "stage-done", "stage": "a", "round": action["round"], "locators": {"x": "u://x"}})]
            if sid == "b" and not self.failed:
                self.failed = True
                return [who.seal({"type": "stage-failed", "stage": "b", "round": action["round"], "reason": "r", "locators": {}})]
            return []

    state = sfresh(SIDE, strict=False)
    ring = KeyRing(state["run_id"], state["proc"]["entities"])
    ex = Ex(ring)
    drive(state, ex, ring, verify_owner=lambda e: False)
    assert ex.starts["c"] == 1, ex.starts


# ---- stage inputs come only from upstream producers

PRODUCERS = """---
entities:
  w:
    role: worker
    escalates-to: owner
stages:
  build:
    entity: w
    produces: [patch]
  x:
    entity: w
    produces: [patch]
  review:
    entity: w
    floor: true
    needs: [build]
    consumes: [patch]
    produces: [verdict]
  deploy:
    entity: w
    needs: [review]
    consumes: [patch]
    produces: [shipped]
---
"""


def test_a_stage_gets_inputs_only_from_its_own_upstream_producers():
    state = new_state(PRODUCERS, strict=False)
    state, _ = step(state, {"type": "run-started"})
    state, _ = step(state, {"type": "stage-done", "stage": "build", "locators": {"patch": "doc://good"}})
    state, _ = step(state, {"type": "stage-done", "stage": "x", "locators": {"patch": "doc://evil"}})
    state, acts = step(state, {"type": "stage-done", "stage": "review", "locators": {"verdict": "note://ok"}})
    start = next(a for a in acts if a["do"] == "start-stage" and a["stage"] == "deploy")
    assert start["inputs"]["patch"] == "doc://good"


# ---- a loop is judged only when every member has settled

LOOP = """---
entities:
  fixer:
    role: worker
    escalates-to: owner
  checker:
    role: worker
    escalates-to: owner
loops:
  fix:
    stages: [a-fix, b-check]
    exit:
      kind: checked
    bound: 2
    on-exhausted: owner
stages:
  a-fix:
    entity: fixer
    produces: [patched]
  b-check:
    entity: checker
    produces: [checked]
---
"""


def test_a_failing_member_cannot_restart_the_loop_bound_after_an_early_exit():
    state = new_state(LOOP, strict=False)
    state, _ = step(state, {"type": "run-started"})
    for _ in range(3):
        if state["status"] != "running":
            break
        state, _ = step(state, {"type": "stage-done", "stage": "b-check", "locators": {"checked": "x"}})
        state, acts = step(state, {"type": "stage-failed", "stage": "a-fix", "reason": "r", "locators": {}})
    assert state["status"] == "blocked"
    assert any(a["do"] == "notify-owner" for a in acts)


def test_a_round_never_moves_backwards_on_a_loop_retry():
    state = new_state(LOOP, strict=False)
    state, _ = step(state, {"type": "run-started"})
    state["stages"]["b-check"]["round"] = 5
    state, _ = step(state, {"type": "stage-failed", "stage": "a-fix", "reason": "r", "locators": {}})
    assert state["stages"]["b-check"]["round"] >= 5


ON_FAIL = SIDE.replace("  c:\n    entity: w\n    needs: [a]\n    consumes: [x]\n    produces: [z]\n", "")


def test_a_round_never_moves_backwards_on_an_on_fail_retry():
    state = new_state(ON_FAIL, strict=False)
    state, _ = step(state, {"type": "run-started"})
    state, _ = step(state, {"type": "stage-done", "stage": "a", "locators": {"x": "u://x"}})
    state["stages"]["a"]["round"] = 5
    state, _ = step(state, {"type": "stage-failed", "stage": "b", "reason": "r", "locators": {}})
    assert state["stages"]["a"]["round"] >= 5
