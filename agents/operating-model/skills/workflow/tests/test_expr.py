"""Tests for the OWS runtime expression subset (U5)."""

import ast
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "expr.py"
sys.path.insert(0, str(SCRIPT.parent))

from expr import ExprError, evaluate, is_expression, parse, resolve, unwrap  # noqa: E402


def ev(source, data=None, **variables):
    return evaluate(source, data, variables)


# --- Acceptance 2: every expression in the two example workflows -----------
# The originals in examples/ and the 12.6 copies, as YAML loads them.

EXAMPLES = [
    # (expression as loaded, input data, variables, expected)
    ('${ .verdict != "pass" }', {"verdict": "pass"}, {}, False),
    ('${ .verdict != "pass" }', {"verdict": "fail"}, {}, True),
    ('${ .verdict != "pass" }', {}, {}, True),
    ("${ .accepted != true }", {"accepted": True}, {}, False),
    ("${ .accepted != true }", {"accepted": 1}, {}, True),
    ("${ .accepted != true }", None, {}, True),
    ("${ .units }", {"units": [{"id": "a"}]}, {}, [{"id": "a"}]),
    ("${ .unit }", {"unit": {"id": "a"}}, {}, {"id": "a"}),
    ("${ $workflow.id }", {}, {"workflow": {"id": "run-1"}}, "run-1"),
    ('${ $accepted["build/acceptance-run"] != true }', {}, {"accepted": {}}, True),
    ('${ $accepted["build/acceptance-run"] != true }', {}, {"accepted": {"build/acceptance-run": True}}, False),
    ('${ $accepted["build/acceptance-run"] != true }', {}, {"accepted": {"build/acceptance-run": False}}, True),
    ('${ $accepted["cycle/unit-review"] != true }', {}, {"accepted": {"cycle/unit-review": True}}, False),
    ('${ $accepted["cycle/unit-review"] != true }', {}, {"accepted": {"cycle/red": True}}, True),
    ('${ $accepted["merge-gate"] == true }', {}, {"accepted": {}}, False),
    ('${ $accepted["merge-gate"] == true }', {}, {"accepted": {"merge-gate": True}}, True),
    ('${ $accepted["merge-gate"] == true }', {}, {"accepted": {"merge-gate": False}}, False),
]


@pytest.mark.parametrize("text,data,variables,expected", EXAMPLES)
def test_every_example_expression_evaluates(text, data, variables, expected):
    assert is_expression(text) is True
    assert evaluate(unwrap(text), data, variables) == expected


def test_example_call_inputs_resolve():
    tdd_input = {"unit": "${ .unit }"}
    improve_input = {"run": "${ $workflow.id }"}
    assert resolve(tdd_input, {"unit": "u1"}, {}) == {"unit": "u1"}
    assert resolve(improve_input, {}, {"workflow": {"id": "r9"}}) == {"run": "r9"}


def test_an_absent_accepted_key_is_null():
    assert ev('$accepted["x"]', accepted={}) is None
    assert ev('$accepted["x"] == null', accepted={}) is True


# --- Acceptance 3: accepted constructs ---------------------------------------

DOC = {"a": {"b": 2, "k-x": "dash"}, "list": [10, 20, 30], "t": True, "f": False, "n": None}


@pytest.mark.parametrize(
    "source,expected",
    [
        (".", DOC),
        (".a.b", 2),
        ('."a"."k-x"', "dash"),
        ('.["a"]["b"]', 2),
        ('.a.["b"]', 2),
        (".list[0]", 10),
        (".list[-1]", 30),
        (".list[7]", None),
        (".missing.deeper", None),
        (".n.x", None),
        ("(.a.b)", 2),
        ('"s\\u00e9"', "sé"),
        ("1.5", 1.5),
        ("true", True),
        ("null", None),
        ("[]", []),
        ('[1, .a.b, "s", [true]]', [1, 2, "s", [True]]),
        (".a.b == 2", True),
    ],
)
def test_accepted_path_and_literal(source, expected):
    assert ev(source, DOC) == expected


@pytest.mark.parametrize(
    "source,expected",
    [
        ("1 == 1.0", True),
        ("1 == true", False),
        ("0 == false", False),
        ("[1] == [true]", False),
        ("$x == $y", True),
        ("$x != $z", True),
        ("null == false", False),
        ("1 < 2", True),
        ("2 <= 2", True),
        ('"b" > "a"', True),
        ('"a" >= "b"', False),
    ],
)
def test_accepted_comparison(source, expected):
    variables = {"x": {"a": [1, {"b": None}]}, "y": {"a": [1, {"b": None}]}, "z": {"a": [True, {"b": None}]}}
    assert evaluate(source, None, variables) is expected


@pytest.mark.parametrize(
    "source,expected",
    [
        (".t and .f", False),
        (".t or .f", True),
        (".f or .n", False),
        ("0 or false", True),
        ('"" and []', True),
        (".t | not", False),
        (".n | not", True),
        ("(.f | not) and .t", True),
        (".a.b == 2 and .list[0] == 10", True),
        (".f and .missing.x", False),
        ("1 == 1 | not", False),
    ],
)
def test_accepted_boolean(source, expected):
    assert ev(source, DOC) is expected


def test_plus_merges_objects_right_wins():
    out = ev("$context + .", {"b": 3, "c": 4}, context={"a": 1, "b": 2})
    assert out == {"a": 1, "b": 3, "c": 4}


def test_plus_with_null_is_identity():
    assert ev("$context + .", {"a": 1}, context=None) == {"a": 1}
    assert ev(". + $context", {"a": 1}, context=None) == {"a": 1}


def test_result_is_a_copy_not_an_alias():
    accepted = {"k": True}
    out = ev("$accepted", None, accepted=accepted)
    out["k"] = False
    assert accepted == {"k": True}


# --- Acceptance 3: refused constructs, each error names the construct -------

REFUSED = [
    (". | length", "pipe '|'"),
    (".a, .b", "comma ','"),
    (".a // 1", "alternative '//'"),
    (".a?", "optional '?'"),
    ("..", "recursive descent '..'"),
    (".[]", "iterator '.[]'"),
    (".list[1:2]", "slice"),
    ("{a: 1}", "object construction"),
    ("length", "function 'length'"),
    ("select(.a)", "function 'select'"),
    ("not", "function 'not'"),
    ("if . then 1 else 2 end", "keyword 'if'"),
    ("reduce .[] as $x (0; . + $x)", "keyword 'reduce'"),
    ("def f: .; f", "keyword 'def'"),
    ("try .a catch 1", "keyword 'try'"),
    (". as $x", "keyword 'as'"),
    (".a - 1", "operator '-'"),
    (".a * 2", "operator '*'"),
    (".a / 2", "operator '/'"),
    (".a % 2", "operator '%'"),
    (".a = 1", "assignment '='"),
    (".a |= 1", "assignment '|='"),
    (".a += 1", "assignment '+='"),
    ('"x\\(.a)"', "string interpolation"),
    ("@base64", "format '@base64'"),
    ("1 == 1 == true", "chained comparison"),
    ("[.a | not]", "pipe '|'"),
]


@pytest.mark.parametrize("source,construct", REFUSED)
def test_refused_construct_is_named(source, construct):
    with pytest.raises(ExprError) as err:
        parse(source)
    assert construct in str(err.value)
    assert "not in the accepted subset" in str(err.value)


@pytest.mark.parametrize(
    "source,variables,construct",
    [
        ('"a" + "b"', {}, "'+' on string and string"),
        ("[1] + [2]", {}, "'+' on array and array"),
        ("1 + 2", {}, "'+' on number and number"),
        ("$o + 1", {"o": {}}, "'+' on object and number"),
        ('1 < "a"', {}, "ordering '<' on number and string"),
        ("null < 1", {}, "ordering '<' on null and number"),
    ],
)
def test_refused_at_evaluation_names_the_types(source, variables, construct):
    with pytest.raises(ExprError) as err:
        evaluate(source, None, variables)
    assert construct in str(err.value)


@pytest.mark.parametrize(
    "source,data,message",
    [
        (".a.b", {"a": 3}, "cannot index number with \"b\""),
        (".a", "text", "cannot index string with \"a\""),
        (".[0]", {"a": 1}, "cannot index object with number"),
        ('.["a"]', [1], 'cannot index array with "a"'),
        (".[true]", [1], "index must be a string or an integer"),
        ("$nope", None, "variable '$nope' is not defined"),
    ],
)
def test_runtime_errors_are_expr_errors(source, data, message):
    with pytest.raises(ExprError) as err:
        evaluate(source, data, {})
    assert message in str(err.value)


@pytest.mark.parametrize(
    "source,message",
    [
        (".a | not and .b", "pipe '|'"),
        (".a | not == true", "pipe '|'"),
        ("and .a", "unexpected 'and'"),
        (".a == or", "unexpected 'or'"),
    ],
)
def test_misplaced_accepted_operator_is_not_reported_as_refused(source, message):
    # jq reads `X | not and Y` as `X | (not and Y)`: a pipe into something other than `not`.
    with pytest.raises(ExprError) as err:
        parse(source)
    assert message in str(err.value)
    assert "keyword 'and'" not in str(err.value) and "keyword 'or'" not in str(err.value)


@pytest.mark.parametrize("source", ["", "   ", ".a ==", "(.a", "[1,", ".a ]", '"open', "1 2", ".a ."])
def test_malformed_source_is_an_expr_error(source):
    with pytest.raises(ExprError):
        parse(source)


# --- Strict mode: ${ } wrapping, and input data is never evaluated ----------


def test_strict_mode_needs_the_wrapper():
    assert is_expression("${ .a }") is True
    assert is_expression(".a") is False
    assert is_expression("plain text") is False
    assert is_expression(3) is False
    with pytest.raises(ExprError) as err:
        unwrap(".a")
    assert "not a runtime expression" in str(err.value)


def test_resolve_keeps_literals_and_walks_containers():
    template = {"n": 1, "s": "plain", "l": ["${ .a }", "x"], "m": {"k": "${ .a }"}}
    assert resolve(template, {"a": 5}, {}) == {"n": 1, "s": "plain", "l": [5, "x"], "m": {"k": 5}}


def test_expression_text_inside_data_is_not_evaluated():
    # OWS dsl.md: runtimes must not evaluate expression syntax found in input data.
    data = {"x": "${ $ENV.HOME }", "y": "${ length }"}
    assert resolve({"a": "${ .x }", "b": "${ .y }"}, data, {}) == {"a": "${ $ENV.HOME }", "b": "${ length }"}


# --- Acceptance 5: no environment, no files, no network, no eval ------------

HOSTILE = [
    "$ENV.U5_SENTINEL",
    "$ENV",
    "env.U5_SENTINEL",
    "env",
    '"\\(env)"',
    "$__loc__",
    "$__prog_args",
    "input",
    "inputs",
    "input_filename",
    '"x" | @sh',
    "@base64d",
    "$secrets",
    "$secrets.token",
    "$authorization.parameter",
    'getpath(["a"])',
    "splits(\"a\")",
    "$ENV | keys",
    'ltrimstr("a")',
    "debug",
    "stderr",
    "halt_error",
    '"\\(.)"',
]


@pytest.mark.parametrize("source", HOSTILE)
def test_crafted_expression_cannot_read_the_environment(source, monkeypatch):
    monkeypatch.setenv("U5_SENTINEL", "leak-7f3a")
    with pytest.raises(ExprError) as err:
        evaluate(source, {"a": 1}, {"context": {}, "workflow": {"id": "r"}})
    assert "leak-7f3a" not in str(err.value)


@pytest.mark.parametrize("name", ["ENV", "secrets", "authorization", "__loc__"])
def test_refused_variables_stay_refused_even_when_bound(name):
    with pytest.raises(ExprError) as err:
        evaluate(f"${name}", None, {name: {"leak": "leak-7f3a"}})
    assert f"variable '${name}'" in str(err.value)
    assert "leak-7f3a" not in str(err.value)


class Probe:
    secret = "leak-7f3a"

    def __getitem__(self, key):
        return "leak-7f3a"


@pytest.mark.parametrize("source", ['."__class__"', '.["__globals__"]', ".secret", '.["secret"]', ".[0]", "."])
def test_non_json_input_is_never_reached_through_attributes(source):
    with pytest.raises(ExprError) as err:
        evaluate(source, Probe(), {})
    assert "leak-7f3a" not in str(err.value)


ALLOWED_IMPORTS = {"json", "math", "re"}
FORBIDDEN_NAMES = {"eval", "exec", "compile", "open", "__import__", "getattr", "setattr", "globals", "locals", "vars", "input", "breakpoint"}


def test_module_has_no_eval_file_network_or_os_access():
    tree = ast.parse(SCRIPT.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= ALLOWED_IMPORTS, imported - ALLOWED_IMPORTS
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert not names & FORBIDDEN_NAMES, names & FORBIDDEN_NAMES


# --- Hostile size and nesting ------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "(" * 200 + "." + ")" * 200,
        "[" * 200 + "]" * 200,
        "." + ".a" * 3000,
        "1e999",
        "-1e999",
        "9" * 5000,
    ],
)
def test_hostile_source_raises_expr_error_only(source):
    with pytest.raises(ExprError):
        evaluate(source, {}, {})


def test_deep_input_data_raises_expr_error_not_recursion_error():
    deep = []
    for _ in range(100000):
        deep = [deep]
    with pytest.raises(ExprError):
        evaluate(". == .", deep, {})
    with pytest.raises(ExprError):
        evaluate(".", deep, {})


def test_non_finite_input_numbers_are_refused():
    with pytest.raises(ExprError):
        evaluate(".a", {"a": float("nan")}, {})


# --- Acceptance 4: parallel units, decision "sequential for only" -----------


def test_counting_until_for_fan_in_is_refused():
    # A variable-count join (run await:false + listen to.any until) needs a count;
    # the OWS reference's own example uses `length`.
    for until in ["($context.done | length) == ($context.units | length)", "length == 2", "$context.done | length"]:
        with pytest.raises(ExprError) as err:
            parse(until)
        assert "pipe '|'" in str(err.value) or "function 'length'" in str(err.value)


def test_sequential_for_runs_each_unit_in_order_with_context_data_flow():
    """Drive build/units the way the interpreter would, sequentially."""
    cut_output = {"units": [{"id": "u1"}, {"id": "u2"}, {"id": "u3"}]}
    # cut: export.as merges its output into the context.
    context = evaluate(unwrap("${ $context + . }"), cut_output, {"context": None})
    assert context == cut_output
    # round 2 input to units is acceptance-run's output, which has no .units.
    round_two_input = {"exit": 1}
    assert evaluate(unwrap("${ .units }"), round_two_input, {}) is None
    for round_input in (cut_output, round_two_input):
        items = evaluate(unwrap("${ $context.units }"), round_input, {"context": context})
        calls = []
        for index, unit in enumerate(items):
            variables = {"context": context, "unit": unit, "index": index}
            calls.append(resolve({"unit": "${ $unit }", "at": "${ $index }"}, round_input, variables))
        assert calls == [{"unit": {"id": "u1"}, "at": 0}, {"unit": {"id": "u2"}, "at": 1}, {"unit": {"id": "u3"}, "at": 2}]
