from procedure_testkit import has, validate_layers, validate_text


def proc(stages, top=""):
    return f"---\nname: t\n{top}stages:\n{stages}---\n"


BASE_STAGES = (
    "  build:\n    produces: [change]\n"
    "  review:\n    needs: [build]\n    consumes: [change]\n    produces: [findings]\n"
)
LOOP = (
    "loops:\n  fix:\n    stages: [build, review]\n    exit:\n      kind: findings\n"
    "    bound: 3\n    on-exhausted: owner\n    carries: findings\n"
)


def errs(stages=BASE_STAGES, top=LOOP):
    return validate_text(proc(stages, top))


def loop_with(**over):
    keep = {"stages": "[build, review]", "bound": "3", "on-exhausted": "owner", "carries": "findings"}
    keep.update(over)
    lines = ["loops:", "  fix:"]
    for key, val in keep.items():
        if val is not None:
            lines.append(f"    {key}: {val}")
    if "exit" not in over:
        lines += ["    exit:", "      kind: findings"]
    return "\n".join(lines) + "\n"


def with_when(when_block):
    return BASE_STAGES + f"  gate:\n    needs: [review]\n    consumes: [findings]\n{when_block}"


def test_when_accepts_each_closed_predicate():
    assert errs(with_when("    when:\n      paths: [src/auth/**, infra/**]\n"), "") == []
    assert errs(with_when("    when:\n      kind: findings\n"), "") == []
    assert errs(with_when("    when:\n      policy: security\n"), "") == []


def test_when_accepts_several_predicates_together():
    block = "    when:\n      paths: [src/**]\n      policy: security\n"
    assert errs(with_when(block), "") == []


def test_when_must_be_a_map_not_a_string():
    assert has(errs(with_when("    when: has-ui\n"), ""), "when")


def test_when_rejects_an_unknown_predicate():
    assert has(errs(with_when("    when:\n      mood: good\n"), ""), "predicate")


def test_when_rejects_an_empty_map():
    assert has(errs(with_when("    when:\n"), ""), "when")


def test_when_paths_must_be_a_list():
    assert has(errs(with_when("    when:\n      paths: src\n"), ""), "paths")


def test_when_kind_must_be_a_kind_the_procedure_knows():
    assert has(errs(with_when("    when:\n      kind: ghost\n"), ""), "ghost")


def test_a_sole_conditional_producer_still_fails_with_map_when():
    s = (
        "  a:\n    when:\n      policy: ui\n    produces: [x]\n"
        "  b:\n    needs: [a]\n    consumes: [x]\n    produces: [y]\n"
    )
    assert has(errs(s, ""), "conditional")


def test_a_complete_loop_passes():
    assert errs() == []


def test_a_loop_over_a_back_edge_is_not_a_needs_cycle():
    assert errs(BASE_STAGES + "    on-fail:\n      to: build\n") == []


def test_loop_requires_a_bound():
    assert has(errs(top=loop_with(bound=None)), "bound")


def test_loop_bound_must_be_a_positive_integer():
    for bad in ("0", "three", "-2", "2.5"):
        assert has(errs(top=loop_with(bound=bad)), "bound"), bad


def test_loop_requires_an_exit_condition():
    top = "loops:\n  fix:\n    stages: [build, review]\n    bound: 3\n    on-exhausted: owner\n"
    assert has(errs(top=top), "exit")


def test_loop_exit_must_use_closed_predicates():
    top = loop_with(exit="\n      mood: good")
    assert has(errs(top=top), "predicate")


def test_loop_requires_on_exhausted():
    assert has(errs(top=loop_with(**{"on-exhausted": None})), "on-exhausted")


def test_loop_stages_must_exist_and_not_be_empty():
    assert has(errs(top=loop_with(stages="[build, ghost]")), "ghost")
    assert has(errs(top=loop_with(stages="[]")), "stages")


def test_loop_carries_a_kind_one_of_its_members_produces():
    assert has(errs(top=loop_with(carries="verdict")), "carries")


ENTS = "entities:\n  lead:\n    escalates-to: owner\n"
ENT_STAGES = (
    "  build:\n    entity: lead\n    produces: [change]\n"
    "  review:\n    entity: lead\n    needs: [build]\n    consumes: [change]\n    produces: [findings]\n"
)


def test_on_exhausted_must_name_an_entity_or_owner():
    assert errs(ENT_STAGES, ENTS + loop_with(**{"on-exhausted": "lead"})) == []
    assert has(errs(ENT_STAGES, ENTS + loop_with(**{"on-exhausted": "ghost"})), "ghost")


BASE = proc(BASE_STAGES, LOOP).replace("---\nname: t\n", "---\n")


def test_delta_can_tighten_a_loop_bound():
    assert validate_layers(BASE, "---\nloops:\n  fix:\n    bound: 2\n---\n") == []


def test_delta_cannot_remove_the_bound_from_a_loop():
    delta = "---\nloops:\n  fix:\n    bound:\n---\n"
    assert has(validate_layers(BASE, delta), "bound")


def test_delta_can_add_a_loop():
    delta = (
        "---\nloops:\n  again:\n    stages: [review]\n    exit:\n      kind: findings\n"
        "    bound: 2\n    on-exhausted: owner\n---\n"
    )
    assert validate_layers(BASE, delta) == []
