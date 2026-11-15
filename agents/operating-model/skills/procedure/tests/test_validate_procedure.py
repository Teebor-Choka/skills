from procedure_testkit import FIXTURES, main, validate_layers, validate_text


def proc(stages):
    return f"---\nname: t\nstages:\n{stages}---\nbody\n"


OK = """  a:
    produces: [x]
  b:
    needs: [a]
    consumes: [x]
    produces: [y]
"""

BASE = """---
name: base
stages:
  spec:
    floor: true
    produces: [item]
  build:
    needs: [spec]
    consumes: [item]
    produces: [change]
---
"""


def layered(stages):
    return validate_layers(BASE, f"---\nstages:\n{stages}---\n")


def errs(stages):
    return validate_text(proc(stages))


def has(errors, word):
    return any(word in e for e in errors)


def test_valid_chain_passes():
    assert errs(OK) == []


def test_campaign_ops_fixture_passes():
    assert validate_text((FIXTURES / "campaign-ops.md").read_text()) == []


def test_unknown_keys_pass():
    assert errs(OK + "    colour: blue\n") == []


def test_on_fail_back_edge_is_a_loop_not_a_cycle():
    assert errs(OK + "    on-fail:\n      to: a\n      bound: 3 rounds\n") == []


def test_cycle_via_needs_fails():
    s = ("  a:\n    needs: [b]\n    produces: [x]\n"
         "  b:\n    needs: [a]\n    consumes: [x]\n    produces: [y]\n")
    assert has(errs(s), "cycle")


def test_dangling_needs_fails():
    assert has(errs("  a:\n    needs: [ghost]\n    produces: [x]\n"), "ghost")


def test_consumed_kind_without_producer_fails():
    s = OK + "  c:\n    needs: [b]\n    consumes: [nothing]\n    produces: [z]\n"
    assert has(errs(s), "nothing")


def test_entry_stage_may_consume_external_input():
    assert errs("  a:\n    consumes: [issue]\n    produces: [x]\n") == []


def test_sole_conditional_producer_fails():
    s = ("  a:\n    when:\n      policy: has-ui\n    produces: [x]\n"
         "  b:\n    needs: [a]\n    consumes: [x]\n    produces: [y]\n")
    assert has(errs(s), "conditional")


def test_conditional_producer_with_unconditional_peer_passes():
    s = ("  a:\n    when:\n      policy: has-ui\n    produces: [x]\n"
         "  a2:\n    produces: [x]\n"
         "  b:\n    needs: [a, a2]\n    consumes: [x]\n    produces: [y]\n")
    assert errs(s) == []


def test_on_fail_unknown_stage_fails():
    assert has(errs(OK + "    on-fail:\n      to: ghost\n"), "ghost")


def test_needs_not_a_list_fails():
    s = "  a:\n    produces: [x]\n  b:\n    needs: a\n    consumes: [x]\n    produces: [y]\n"
    assert has(errs(s), "needs")


def test_produces_not_a_list_fails():
    assert has(errs("  a:\n    produces: x\n"), "produces")


def test_malformed_frontmatter_fails():
    assert validate_text("no frontmatter here") != []




def test_delta_cannot_disable_floor_stage():
    delta = "  spec:\n    disabled: true\n"
    assert has(layered(delta), "floor")


def test_delta_can_disable_a_stage_that_does_not_wait_on_a_floor_stage():
    base = BASE[:-4] + "  notes:\n    produces: [n]\n---\n"
    assert validate_layers(base, "---\nstages:\n  notes:\n    disabled: true\n---\n") == []


def test_delta_cannot_disable_a_stage_that_waits_on_a_floor_stage():
    delta = "---\nstages:\n  build:\n    disabled: true\n---\n"
    assert has(validate_layers(BASE, delta), "floor")


def test_delta_adds_stage_with_needs():
    delta = "  ship:\n    needs: [build]\n    consumes: [change]\n    produces: [release]\n"
    assert layered(delta) == []


def test_delta_stage_with_unmet_kind_fails():
    delta = "  ship:\n    needs: [build]\n    consumes: [nope]\n    produces: [release]\n"
    assert has(layered(delta), "nope")


def test_on_fail_to_must_be_a_stage_name_not_a_list():
    s = OK + "    on-fail:\n      to: [a]\n"
    assert has(errs(s), "on-fail")


def test_on_fail_requires_to():
    assert has(errs(OK + "    on-fail:\n      bound: 3\n"), "on-fail")


def test_on_fail_to_downstream_stage_fails():
    s = ("  a:\n    produces: [x]\n    on-fail:\n      to: b\n"
         "  b:\n    needs: [a]\n    consumes: [x]\n")
    assert has(errs(s), "on-fail")


def test_on_fail_to_self_passes():
    assert errs("  a:\n    produces: [x]\n    on-fail:\n      to: a\n") == []


def test_delta_cannot_change_floor_flag():
    delta = "  spec:\n    floor: false\n"
    assert has(layered(delta), "floor")


def test_floor_stage_cannot_be_made_conditional():
    delta = "  spec:\n    when:\n      policy: never\n"
    assert has(layered(delta), "floor")


def test_delta_disabling_unknown_stage_fails():
    delta = "  bulid:\n    disabled: true\n"
    assert has(layered(delta), "bulid")


def test_delta_without_stages_passes():
    assert validate_layers(BASE, "---\ntrigger:\n  on: x\n---\n") == []


def test_cli_missing_file_prints_error_and_exits_1(capsys):
    assert main(["/nonexistent/procedure.md"]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_delta_with_empty_stages_map_is_a_no_op():
    assert validate_layers(BASE, "---\nstages:\n---\n") == []


GATED = """---
stages:
  build:
    produces: [change]
  gate:
    floor: true
    needs: [build]
    review: [adversarial]
    produces: [approval]
  release:
    needs: [gate]
    consumes: [approval]
---
"""


def gated(stages):
    return validate_layers(GATED, f"---\nstages:\n{stages}---\n")


def test_delta_cannot_rewire_around_a_floor_stage():
    s = "  release:\n    needs: [build]\n    consumes: [change]\n"
    assert has(gated(s), "floor")


def test_delta_cannot_change_a_floor_stage_wiring_or_skill():
    for tail in ("needs: []", "skill: noop", "produces: [other]"):
        assert has(gated(f"  gate:\n    {tail}\n"), "floor"), tail


def test_delta_cannot_remove_a_review_angle_from_a_floor_stage():
    assert has(gated("  gate:\n    review: []\n"), "floor")


def test_delta_may_add_a_review_angle_to_a_floor_stage():
    assert gated("  gate:\n    review: [adversarial, security]\n") == []


def test_floor_stage_cannot_sit_downstream_of_a_conditional_stage():
    s = "  hold:\n    when:\n      policy: never\n    produces: [x]\n  gate:\n    needs: [build, hold]\n"
    assert has(gated(s), "floor")


def test_delta_may_add_a_stage_after_a_floor_stage():
    s = "  ship:\n    needs: [release]\n"
    assert gated(s) == []


def test_non_boolean_disabled_or_floor_fails():
    assert has(gated("  gate:\n    disabled: yes\n"), "disabled")
    assert has(errs("  a:\n    floor: yes\n    produces: [x]\n"), "floor")
