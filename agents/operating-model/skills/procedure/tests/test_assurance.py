import pytest
from procedure_testkit import new_state
from runtime_fixtures import SWE, dos
from signed_fixtures import decide, go, sfailed, srun


def at_owner(policy=None, protected=False):
    state, _ = go(policy=policy) if policy else go()
    state, acts = srun(state, sfailed("align"))
    item = acts[0][0]["item"]
    if protected:
        next(i for i in state["items"] if i["id"] == item)["protected"] = True
    return state, item


def attested(state, item, decision="retry"):
    return {**decide(state, item, decision), "assurance": "attested"}


def refused(acts, word=None):
    return dos(acts) == ["error"] and (word is None or word in acts[0]["reason"])


def test_a_decision_with_no_assurance_is_a_signed_one():
    state, item = at_owner()
    state, acts = srun(state, decide(state, item, "retry"))
    assert acts[0][0]["do"] == "owner-ruled" and acts[0][0]["assurance"] == "signed"
    assert next(i for i in state["items"] if i["id"] == item)["assurance"] == "signed"


def test_an_attested_decision_applies_to_an_ordinary_item_by_default():
    state, item = at_owner()
    state, acts = srun(state, attested(state, item))
    assert acts[0][0]["do"] == "owner-ruled" and acts[0][0]["assurance"] == "attested"
    assert next(i for i in state["items"] if i["id"] == item)["assurance"] == "attested"


def test_an_attested_decision_is_refused_on_a_protected_item_by_default():
    state, item = at_owner(protected=True)
    state, acts = srun(state, attested(state, item))
    assert refused(acts[0], "signature")
    assert next(i for i in state["items"] if i["id"] == item)["status"] == "open"


def test_a_signed_decision_still_applies_to_a_protected_item():
    state, item = at_owner(protected=True)
    state, acts = srun(state, decide(state, item, "retry"))
    assert acts[0][0]["do"] == "owner-ruled"


def test_the_policy_can_let_attested_decisions_close_a_protected_item():
    state, item = at_owner({"attested-decisions": ["ordinary", "protected"]}, protected=True)
    state, acts = srun(state, attested(state, item))
    assert acts[0][0]["do"] == "owner-ruled"


def test_the_policy_can_refuse_attested_decisions_altogether():
    state, item = at_owner({"attested-decisions": []})
    state, acts = srun(state, attested(state, item))
    assert refused(acts[0], "signature")


@pytest.mark.parametrize("bad", ["delegate", 3, None, ["ordinary", "everything"], "ordinary"])
def test_an_unknown_assurance_is_refused(bad):
    state, item = at_owner()
    state, acts = srun(state, {**decide(state, item, "retry"), "assurance": bad})
    assert refused(acts[0], "assurance")


def test_a_refused_attested_decision_is_spent_so_it_cannot_be_replayed():
    state, item = at_owner(protected=True)
    ev = attested(state, item)
    state, acts = srun(state, ev, ev)
    assert refused(acts[0], "signature") and refused(acts[1], "replay")


@pytest.mark.parametrize("bad", ["ordinary", ["ordinary", "everything"], [3], "all"])
def test_attested_decisions_must_be_a_list_of_known_classes(bad):
    with pytest.raises(ValueError, match="attested-decisions"):
        new_state(SWE, policy={"attested-decisions": bad}, trust="signed")


def test_the_default_is_ordinary_only():
    assert new_state(SWE, trust="signed")["policy"].get("attested-decisions", ["ordinary"]) == ["ordinary"]
