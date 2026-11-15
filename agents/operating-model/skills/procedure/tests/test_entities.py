from procedure_testkit import has, validate_layers, validate_text

LADDER = """  pm:
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
"""

STAGE = "  a:\n    entity: worker\n    produces: [x]\n"


def proc(entities=LADDER, stages=STAGE):
    return f"---\nname: t\nentities:\n{entities}stages:\n{stages}---\n"


def errs(entities=LADDER, stages=STAGE):
    return validate_text(proc(entities, stages))


def test_a_ladder_with_downward_and_peer_spawning_passes():
    assert errs() == []


def test_escalates_to_unknown_entity_fails():
    assert has(errs(LADDER + "  rogue:\n    escalates-to: ghost\n"), "ghost")


def test_a_ladder_that_never_reaches_owner_fails():
    loop = "  a1:\n    escalates-to: a2\n  a2:\n    escalates-to: a1\n"
    assert has(errs(loop, "  s:\n    entity: a1\n    produces: [x]\n"), "owner")


def test_owner_is_a_reserved_entity_name():
    assert has(errs(LADDER + "  owner:\n    escalates-to: owner\n"), "owner")


def test_may_spawn_unknown_entity_fails():
    assert has(errs(LADDER.replace("may-spawn: [lead]", "may-spawn: [ghost]")), "ghost")


def test_spawning_upward_fails():
    up = LADDER.replace("may-spawn: [worker]\n  worker", "may-spawn: [worker, pm]\n  worker")
    assert has(errs(up), "spawn")


def test_spawning_a_sideways_entity_fails():
    two = LADDER + "  lead2:\n    escalates-to: pm\n    may-spawn: [worker2]\n"
    two += "  worker2:\n    escalates-to: lead2\n"
    side = two.replace("may-spawn: [worker2]", "may-spawn: [worker2, worker]")
    assert has(errs(side), "spawn")


def test_an_entity_may_not_spawn_owner():
    assert has(errs(LADDER.replace("may-spawn: [lead]", "may-spawn: [lead, owner]")), "owner")


def test_stage_naming_an_unknown_entity_fails():
    assert has(errs(stages="  a:\n    entity: ghost\n    produces: [x]\n"), "ghost")


def test_stage_without_an_entity_fails_when_entities_are_defined():
    assert has(errs(stages="  a:\n    produces: [x]\n"), "entity")


def test_procedure_without_entities_needs_no_stage_entity():
    assert validate_text("---\nstages:\n  a:\n    produces: [x]\n---\n") == []


BASE = """---
entities:
  rev:
    role: reviewer
    escalates-to: owner
  dev:
    role: worker
    escalates-to: owner
stages:
  build:
    entity: dev
    produces: [change]
  review:
    floor: true
    entity: rev
    needs: [build]
    consumes: [change]
    produces: [verdict]
---
"""


def test_delta_cannot_reassign_who_runs_a_floor_stage():
    delta = "---\nstages:\n  review:\n    entity: dev\n---\n"
    assert has(validate_layers(BASE, delta), "floor")


def test_delta_can_add_an_entity_and_a_stage_that_uses_it():
    delta = (
        "---\nentities:\n  sec:\n    role: security\n    escalates-to: owner\n"
        "stages:\n  scan:\n    entity: sec\n    needs: [build]\n    consumes: [change]\n---\n"
    )
    assert validate_layers(BASE, delta) == []


def test_removing_an_entity_a_stage_still_uses_fails():
    delta = "---\nentities:\n  dev:\n    disabled: true\n---\n"
    assert has(validate_layers(BASE, delta), "dev")
