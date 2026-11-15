import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
# Self-contained: CI runs every suite in one pytest session, where a shared `conftest`
# module name resolves to another suite's file.
sys.path.insert(0, str(HERE.parent / "scripts"))

from validate_procedure import main, validate_layers, validate_text  # noqa: E402


def proc(stages, top=""):
    return f"---\nname: t\n{top}stages:\n{stages}---\nbody\n"


OK = """  a:
    produces: [x]
  b:
    needs: [a]
    consumes: [x]
    produces: [y]
"""


def errs(stages, top=""):
    return validate_text(proc(stages, top))


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
    s = ("  a:\n    when: has-ui\n    produces: [x]\n"
         "  b:\n    needs: [a]\n    consumes: [x]\n    produces: [y]\n")
    assert has(errs(s), "conditional")


def test_conditional_producer_with_unconditional_peer_passes():
    s = ("  a:\n    when: has-ui\n    produces: [x]\n"
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


def test_delta_cannot_disable_floor_stage():
    delta = "---\nstages:\n  spec:\n    disabled: true\n---\n"
    assert has(validate_layers(BASE, delta), "floor")


def test_delta_can_disable_non_floor_stage():
    assert validate_layers(BASE, "---\nstages:\n  build:\n    disabled: true\n---\n") == []


def test_delta_adds_stage_with_needs():
    delta = ("---\nstages:\n  ship:\n    needs: [build]\n"
             "    consumes: [change]\n    produces: [release]\n---\n")
    assert validate_layers(BASE, delta) == []


def test_delta_stage_with_unmet_kind_fails():
    delta = ("---\nstages:\n  ship:\n    needs: [build]\n"
             "    consumes: [nope]\n    produces: [release]\n---\n")
    assert has(validate_layers(BASE, delta), "nope")


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
    delta = "---\nstages:\n  spec:\n    floor: false\n---\n"
    assert has(validate_layers(BASE, delta), "floor")


def test_floor_stage_cannot_be_made_conditional():
    delta = "---\nstages:\n  spec:\n    when: never\n---\n"
    assert has(validate_layers(BASE, delta), "floor")


def test_delta_disabling_unknown_stage_fails():
    delta = "---\nstages:\n  bulid:\n    disabled: true\n---\n"
    assert has(validate_layers(BASE, delta), "bulid")


def test_delta_without_stages_passes():
    assert validate_layers(BASE, "---\ntrigger:\n  on: x\n---\n") == []


def test_cli_missing_file_prints_error_and_exits_1(capsys):
    assert main(["/nonexistent/procedure.md"]) == 1
    assert "ERROR" in capsys.readouterr().err
