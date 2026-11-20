"""Restricted jq subset for OWS runtime expressions (strict mode).

Accepted: path access (`.`, `.a`, `."k"`, `.["k"]`, `[n]`), variables bound by the
caller (`$context`, `$accepted`, `$workflow`, loop variables), JSON literals, array
literals, `==` `!=` `<` `<=` `>` `>=`, `and`, `or`, `X | not`, and `+` on objects
(null is the identity). Everything else raises ExprError naming the construct.

Standard library only. No eval, no file, network or environment access: an
expression sees only the input value and the variables passed in.
"""

import json
import math
import re

MAX_SOURCE = 4096
MAX_DEPTH = 32

SUBSET = "not in the accepted subset"

KEYWORDS = {
    "if", "then", "elif", "else", "end", "as", "def", "reduce", "foreach", "try",
    "catch", "label", "import", "include", "and", "or", "__loc__",
}
LITERALS = {"true": True, "false": False, "null": None}
# Bound or not, these never resolve: they would expose the process or credentials.
REFUSED_VARIABLES = {"ENV", "__loc__", "__prog_args", "secrets", "authorization"}

OPERATORS = [
    # longest first
    ("?//", "alternative destructuring '?//'"),
    ("//=", "assignment '//='"),
    ("|=", "assignment '|='"),
    ("+=", "assignment '+='"),
    ("-=", "assignment '-='"),
    ("*=", "assignment '*='"),
    ("/=", "assignment '/='"),
    ("%=", "assignment '%='"),
    ("==", None),
    ("!=", None),
    ("<=", None),
    (">=", None),
    ("//", "alternative '//'"),
    ("..", "recursive descent '..'"),
    ("=", "assignment '='"),
    ("<", None),
    (">", None),
    ("+", None),
    ("|", None),
    (",", None),
    ("(", None),
    (")", None),
    ("[", None),
    ("]", None),
    (":", None),
    ("?", "optional '?'"),
    ("-", "operator '-'"),
    ("*", "operator '*'"),
    ("/", "operator '/'"),
    ("%", "operator '%'"),
    ("{", "object construction '{...}'"),
    ("}", "object construction '{...}'"),
    (";", "separator ';'"),
]

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NUMBER = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
COMPARE = {"==", "!=", "<", "<=", ">", ">="}


class ExprError(ValueError):
    pass


def _refuse(construct):
    raise ExprError(f"{construct}: {SUBSET}")


# --- strict mode wrapper ----------------------------------------------------


def is_expression(value):
    """True when `value` is a strict-mode runtime expression `${ ... }`."""
    return isinstance(value, str) and value.startswith("${") and value.endswith("}")


def unwrap(text):
    """Return the jq source inside `${ ... }`."""
    if not is_expression(text):
        raise ExprError(f"{text!r} is not a runtime expression; strict mode needs '${{ ... }}'")
    return text[2:-1]


# --- lexer ------------------------------------------------------------------


def _string(src, i):
    """Lex a JSON string literal starting at src[i] == '"'; return (value, end)."""
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            if src[j + 1 : j + 2] == "(":
                _refuse("string interpolation '\\(...)'")
            j += 2
            continue
        if c == '"':
            try:
                return json.loads(src[i : j + 1]), j + 1
            except ValueError:
                raise ExprError(f"malformed string literal at offset {i}") from None
        j += 1
    raise ExprError(f"unterminated string literal at offset {i}")


def _tokens(src):
    """Lex `src`. A lex error becomes a final ("error", message) token, so the parser
    reports whichever refused construct comes first in source order."""
    out = []
    try:
        _lex(src, out)
    except ExprError as err:
        out.append(("error", str(err)))
        return out
    out.append(("end", None))
    return out


def _ends_value(tok):
    """True when `tok` can end an operand, so a following '-' is binary minus."""
    kind, value = tok
    if kind in ("str", "num", "var", "field", "dot"):
        return True
    if kind == "ident":
        return value in LITERALS
    return tok in (("op", ")"), ("op", "]"))


def _lex(src, out):
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c == "#":
            _refuse("comment '#'")
        if c == '"':
            value, i = _string(src, i)
            out.append(("str", value))
            continue
        if c == "@":
            m = IDENT.match(src, i + 1)
            _refuse(f"format '@{m.group(0) if m else ''}'")
        if c == "$":
            m = IDENT.match(src, i + 1)
            if not m:
                raise ExprError(f"malformed variable at offset {i}")
            out.append(("var", m.group(0)))
            i = m.end()
            continue
        if c == "." and src[i + 1 : i + 2] != ".":
            m = IDENT.match(src, i + 1)
            if m:
                out.append(("field", m.group(0)))
                i = m.end()
                continue
            if src[i + 1 : i + 2] == '"':
                value, i = _string(src, i + 1)
                out.append(("field", value))
                continue
            out.append(("dot", "."))
            i += 1
            continue
        negative = (
            c == "-"
            and src[i + 1 : i + 2].isdigit()
            and not (out and _ends_value(out[-1]))
        )
        if c.isdigit() or negative:
            m = NUMBER.match(src, i + 1 if negative else i)
            text = ("-" if negative else "") + m.group(0)
            value = float(text) if any(ch in text for ch in ".eE") else int(text)
            if isinstance(value, float) and not math.isfinite(value):
                raise ExprError(f"number '{text}' is not finite")
            out.append(("num", value))
            i = m.end()
            continue
        m = IDENT.match(src, i)
        if m:
            out.append(("ident", m.group(0)))
            i = m.end()
            continue
        for op, refused in OPERATORS:
            if src.startswith(op, i):
                if refused:
                    _refuse(refused)
                out.append(("op", op))
                i += len(op)
                break
        else:
            raise ExprError(f"character {c!r} at offset {i} is not allowed")


# --- parser -----------------------------------------------------------------
# AST nodes are tuples: ("dot",), ("lit", v), ("var", name), ("index", base, key),
# ("array", [items]), ("not", e), ("and", a, b), ("or", a, b), ("cmp", op, a, b),
# ("plus", a, b).


class _Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.pos = 0
        self.depth = 0

    def peek(self):
        tok = self.toks[self.pos]
        if tok[0] == "error":
            raise ExprError(tok[1])
        return tok

    def take(self):
        tok = self.toks[self.pos]
        self.pos += 1
        return tok

    def at(self, kind, value=None):
        tok = self.peek()
        return tok[0] == kind and (value is None or tok[1] == value)

    def expect(self, kind, value):
        if not self.at(kind, value):
            self.unexpected()
        self.take()

    def unexpected(self):
        kind, value = self.peek()
        if kind == "end":
            raise ExprError("unexpected end of expression")
        if kind == "op" and value == ",":
            _refuse("comma ','")
        if kind == "op" and value == "|":
            _refuse("pipe '|' (only 'X | not' is accepted)")
        if kind == "op" and value == ":":
            _refuse("slice '[:]'")
        if kind == "ident":
            self.ident(value)
        raise ExprError(f"unexpected {value!r}")

    def ident(self, name):
        if name in ("and", "or"):
            raise ExprError(f"unexpected {name!r}")
        if name in KEYWORDS:
            _refuse(f"keyword '{name}'")
        _refuse(f"function '{name}'")

    def nest(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ExprError(f"expression nests deeper than {MAX_DEPTH}")

    def pipe(self):
        node = self.disjunction()
        while self.at("op", "|"):
            self.take()
            if not self.at("ident", "not"):
                _refuse("pipe '|' (only 'X | not' is accepted)")
            self.take()
            node = ("not", node)
            # jq reads `X | not and Y` as `X | (not and Y)`: a pipe into more than `not`.
            if not (self.at("end") or self.at("op", "|") or self.at("op", ")") or self.at("op", "]")):
                _refuse("pipe '|' (only 'X | not' is accepted)")
        return node

    def disjunction(self):
        node = self.conjunction()
        while self.at("ident", "or"):
            self.take()
            node = ("or", node, self.conjunction())
        return node

    def conjunction(self):
        node = self.comparison()
        while self.at("ident", "and"):
            self.take()
            node = ("and", node, self.comparison())
        return node

    def comparison(self):
        node = self.additive()
        if self.at("op") and self.peek()[1] in COMPARE:
            op = self.take()[1]
            node = ("cmp", op, node, self.additive())
            if self.at("op") and self.peek()[1] in COMPARE:
                _refuse("chained comparison")
        return node

    def additive(self):
        node = self.postfix()
        while self.at("op", "+"):
            self.take()
            node = ("plus", node, self.postfix())
        return node

    def postfix(self):
        node = self.primary()
        while True:
            if self.at("field"):
                node = ("index", node, ("lit", self.take()[1]))
            elif self.at("op", "["):
                node = ("index", node, self.bracket())
            elif self.at("dot") and self.toks[self.pos + 1] == ("op", "["):
                self.take()
                node = ("index", node, self.bracket())
            else:
                return node

    def bracket(self):
        self.take()  # [
        if self.at("op", "]"):
            _refuse("iterator '.[]'")
        if self.at("op", ":"):
            _refuse("slice '[:]'")
        self.nest()
        key = self.pipe()
        self.depth -= 1
        if self.at("op", ":"):
            _refuse("slice '[:]'")
        self.expect("op", "]")
        return key

    def primary(self):
        kind, value = self.peek()
        if kind == "dot":
            self.take()
            return ("dot",)
        if kind == "field":
            self.take()
            return ("index", ("dot",), ("lit", value))
        if kind in ("str", "num"):
            self.take()
            return ("lit", value)
        if kind == "var":
            self.take()
            if value in REFUSED_VARIABLES:
                _refuse(f"variable '${value}'")
            return ("var", value)
        if kind == "ident":
            if value in LITERALS:
                self.take()
                return ("lit", LITERALS[value])
            self.ident(value)
        if kind == "op" and value == "(":
            self.take()
            self.nest()
            node = self.pipe()
            self.depth -= 1
            self.expect("op", ")")
            return node
        if kind == "op" and value == "[":
            return self.array()
        self.unexpected()

    def array(self):
        self.take()  # [
        self.nest()
        items = []
        if not self.at("op", "]"):
            items.append(self.disjunction())
            while self.at("op", ","):
                self.take()
                items.append(self.disjunction())
        if self.at("op", "|"):
            _refuse("pipe '|' inside an array literal")
        self.expect("op", "]")
        self.depth -= 1
        return ("array", items)


def parse(source):
    """Parse jq source (without `${ }`) into an AST; raise ExprError on anything refused."""
    if not isinstance(source, str):
        raise ExprError("expression must be a string")
    if len(source) > MAX_SOURCE:
        raise ExprError(f"expression longer than {MAX_SOURCE} characters")
    parser = _Parser(_tokens(source))
    if parser.at("end"):
        raise ExprError("empty expression")
    node = parser.pipe()
    if not parser.at("end"):
        parser.unexpected()
    return node


# --- evaluator --------------------------------------------------------------


def _type(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    raise ExprError(f"value of Python type {type(v).__name__} is not JSON")


def _json(v):
    """Deep-copy a JSON value; refuse anything else (no attribute access, ever)."""
    t = _type(v)
    if t == "array":
        return [_json(x) for x in v]
    if t == "object":
        out = {}
        for k, x in v.items():
            if not isinstance(k, str):
                raise ExprError("object key is not a string")
            out[k] = _json(x)
        return out
    if t == "number" and isinstance(v, float) and not math.isfinite(v):
        raise ExprError("number is not finite")
    return v


def _equal(a, b):
    ta, tb = _type(a), _type(b)
    if ta != tb:
        return False
    if ta == "array":
        return len(a) == len(b) and all(_equal(x, y) for x, y in zip(a, b))
    if ta == "object":
        return a.keys() == b.keys() and all(_equal(a[k], b[k]) for k in a)
    return a == b


def _truthy(v):
    return v is not None and v is not False


def _index(base, key):
    tb, tk = _type(base), _type(key)
    if tk not in ("string", "number") or (tk == "number" and not isinstance(key, int)):
        raise ExprError(f"index must be a string or an integer, not {tk}")
    if tb == "null":
        return None
    if tb == "object" and tk == "string":
        return base.get(key)
    if tb == "array" and tk == "number":
        if -len(base) <= key < len(base):
            return base[key]
        return None
    what = json.dumps(key) if tk == "string" else "number"
    raise ExprError(f"cannot index {tb} with {what}")


def _eval(node, data, variables):
    tag = node[0]
    if tag == "dot":
        return data
    if tag == "lit":
        return node[1]
    if tag == "var":
        if node[1] not in variables:
            raise ExprError(f"variable '${node[1]}' is not defined")
        return variables[node[1]]
    if tag == "index":
        return _index(_eval(node[1], data, variables), _eval(node[2], data, variables))
    if tag == "array":
        return [_eval(item, data, variables) for item in node[1]]
    if tag == "not":
        return not _truthy(_eval(node[1], data, variables))
    if tag == "and":
        return _truthy(_eval(node[1], data, variables)) and _truthy(_eval(node[2], data, variables))
    if tag == "or":
        return _truthy(_eval(node[1], data, variables)) or _truthy(_eval(node[2], data, variables))
    if tag == "plus":
        a, b = _eval(node[1], data, variables), _eval(node[2], data, variables)
        ta, tb = _type(a), _type(b)
        if ta == "null":
            return b
        if tb == "null":
            return a
        if ta == "object" and tb == "object":
            return {**a, **b}
        _refuse(f"'+' on {ta} and {tb}")
    if tag == "cmp":
        op = node[1]
        a, b = _eval(node[2], data, variables), _eval(node[3], data, variables)
        if op == "==":
            return _equal(a, b)
        if op == "!=":
            return not _equal(a, b)
        ta, tb = _type(a), _type(b)
        if ta != tb or ta not in ("number", "string"):
            _refuse(f"ordering '{op}' on {ta} and {tb}")
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    raise ExprError(f"unknown node {tag!r}")


def evaluate(source, data=None, variables=None):
    """Evaluate jq `source` (no `${ }`) on `data` with `variables` (names without `$`).

    Returns a fresh JSON value. Every failure is an ExprError.
    """
    node = parse(source)
    try:
        return _json(_eval(node, data, dict(variables or {})))
    except RecursionError:
        raise ExprError("value nests too deeply") from None


def resolve(value, data=None, variables=None):
    """Evaluate every `${ }` string in a definition value; other values stay literal.

    Only the definition is walked. A result is never evaluated again, so expression
    text that arrives in data stays data (OWS dsl.md, runtime expressions warning).
    """
    if is_expression(value):
        return evaluate(unwrap(value), data, variables)
    if isinstance(value, list):
        return [resolve(x, data, variables) for x in value]
    if isinstance(value, dict):
        return {k: resolve(x, data, variables) for k, x in value.items()}
    return value
