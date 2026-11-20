#!/usr/bin/env python3
"""Metric catalog validator and the shared document loader (spec sections 2 and 9).

Usage: validate_catalog.py --root DIR FILE [FILE ...]

Standard library only. PyYAML is imported lazily, and only to read a .yaml file.
Exit codes: 0 valid, 1 invalid or a load error, 2 usage error (bad arguments, unknown
extension, YAML without PyYAML).
"""
import argparse
import json
import math
import os
import re
import sys

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAMESPACE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
SOURCE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")

ENTRY_KEYS = ("scope", "unit", "better", "formula", "collector", "reads")
SCOPES = ("node", "stage", "process")
BETTER = ("lower", "higher", "context")
MAX_DEPTH = 128

YAML_HINT = "reading YAML needs PyYAML; run with uv run --with pyyaml, or convert the file to JSON"


class LoadError(Exception):
    """A document cannot be read. str(e) is `<file>: <message>`; `.msg` is the message alone."""

    def __init__(self, label, msg):
        super().__init__(f"{label}: {msg}")
        self.label = label
        self.msg = msg


class UsageError(Exception):
    """Bad arguments, an unknown extension, or YAML without PyYAML (exit 2)."""


# ---------------------------------------------------------------- loader (spec 2.1)


def _no_duplicates(label):
    def hook(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise LoadError(label, f"duplicate key '{key}'")
            out[key] = value
        return out

    return hook


def _load_json(path):
    def constant(text):
        raise LoadError(path, f"non-finite number {text}")

    def number(text):
        value = float(text)
        if not math.isfinite(value):
            raise LoadError(path, f"non-finite number {text}")
        return value

    with open(path, encoding="utf-8") as fh:
        return json.load(fh, object_pairs_hook=_no_duplicates(path), parse_constant=constant, parse_float=number)


def _load_yaml(path):
    try:
        import yaml
    except ImportError:
        raise UsageError(f"{path}: {YAML_HINT}") from None

    class Loader(yaml.SafeLoader):
        pass

    # Copy the resolver table: changing SafeLoader's own table would change it for every user.
    drop = ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")
    Loader.yaml_implicit_resolvers = {
        first: [(tag, rx) for tag, rx in rules if tag not in drop]
        for first, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    Loader.add_implicit_resolver(
        "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
    )

    def construct_map(loader, node):
        out = {}
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise LoadError(path, "merge key '<<' is not accepted; write the keys out")
            key = loader.construct_object(key_node, deep=True)
            if key in out:
                raise LoadError(path, f"duplicate key '{key}'")
            out[key] = loader.construct_object(value_node, deep=True)
        return out

    Loader.add_constructor("tag:yaml.org,2002:map", construct_map)

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise LoadError(path, f"alias '*{self.peek_event().anchor}' is not accepted; write the value out")
        return yaml.SafeLoader.compose_node(self, parent, index)

    Loader.compose_node = compose_node
    with open(path, encoding="utf-8") as fh:
        return yaml.load(fh, Loader=Loader)  # noqa: S506 - SafeLoader subclass


def load_document(path):
    """Parse a .json, .yaml or .yml file. Raises LoadError (exit 1) or UsageError (exit 2)."""
    if path.endswith(".json"):
        reader = _load_json
    elif path.endswith((".yaml", ".yml")):
        reader = _load_yaml
    else:
        raise UsageError(f"{path}: unknown extension; use .json, .yaml or .yml")
    try:
        return reader(path)
    except (LoadError, UsageError):
        raise
    except RecursionError:
        raise LoadError(path, "nesting too deep to load") from None
    except OSError as exc:
        raise LoadError(path, f"cannot read: {exc.strerror or type(exc).__name__}") from None
    except json.JSONDecodeError as exc:
        # A syntax error whose message happens to contain "4300" (an offset) is not a digit-limit error.
        raise LoadError(path, f"parse error: {str(exc).splitlines()[0]}") from None
    except ValueError as exc:
        text = str(exc)
        if "integer string conversion" in text:
            raise LoadError(path, "integer longer than 4300 digits") from None
        raise LoadError(path, f"parse error: {text.splitlines()[0] if text else type(exc).__name__}") from None
    except Exception as exc:  # PyYAML's own error classes, and anything else a parser throws
        text = str(exc)
        raise LoadError(path, f"parse error: {text.splitlines()[0] if text else type(exc).__name__}") from None


def shape_errors(value):
    """Spec 2.1 rule 6: string keys, JSON types, finite numbers, at most 128 levels. Iterative."""
    errs = []
    stack = [("(root)", value, 1)]
    too_deep = False
    while stack:
        loc, node, level = stack.pop()
        if isinstance(node, bool) or node is None or isinstance(node, (str, int)):
            continue
        if isinstance(node, float):
            if not math.isfinite(node):
                errs.append(f"{loc}: non-finite number")
            continue
        if not isinstance(node, (dict, list)):
            errs.append(f"{loc}: value of type {type(node).__name__} is not JSON")
            continue
        if level > MAX_DEPTH:
            if not too_deep:
                too_deep = True
                errs.append(f"{loc}: value nested deeper than {MAX_DEPTH} levels")
            continue
        prefix = "" if loc == "(root)" else loc
        if isinstance(node, dict):
            children = []
            for key, child in node.items():
                if not isinstance(key, str):
                    errs.append(
                        f"{loc}: key {key!r} is not a string "
                        "(YAML 1.1 reads on, off, yes and no as booleans; quote it)"
                    )
                    continue
                children.append((f"{prefix}.{key}" if prefix else key, child, level + 1))
        else:
            children = [(f"{prefix}[{i}]", child, level + 1) for i, child in enumerate(node)]
        stack.extend(reversed(children))
    return errs


# ---------------------------------------------------------------- paths (spec 2.2)


def relative_path_ok(path, prefix, suffixes):
    """A POSIX relative path with the given prefix and one of the suffixes.

    The stem may not be empty (`collectors/.py`): a validator choice, the spec is silent on it.
    """
    if isinstance(suffixes, str):
        suffixes = (suffixes,)
    if not isinstance(path, str) or CONTROL.search(path) or "\\" in path or path.startswith("/"):
        return False
    if any(seg in ("", ".", "..") for seg in path.split("/")):
        return False
    if not path.startswith(prefix):
        return False
    return any(path.endswith(s) and len(path) > len(prefix) + len(s) for s in suffixes)


def file_under_root(root, rel):
    """True when root/rel is a regular file whose resolved path stays inside the resolved root."""
    full = os.path.join(root, rel)
    if not os.path.isfile(full):
        return False
    real_root = os.path.realpath(root)
    real = os.path.realpath(full)
    return os.path.commonpath([real_root, real]) == real_root


# ---------------------------------------------------------------- catalog (spec 9)


def merge_catalogs(files):
    """Merge parsed catalog files. Returns (merged map, errors). Names must be unique across files."""
    merged, where, errs = {}, {}, []
    for label, data in files:
        if not isinstance(data, dict):
            errs.append(f"catalog {label}: must be a map of metric names")
            continue
        for name, entry in data.items():
            if name in where:
                errs.append(f"catalog: {name}: defined in {where[name]} and {label}")
            else:
                where[name] = label
                merged[name] = entry
    return merged, errs


def _entry_errors(name, entry, root):
    loc = f"catalog: {name}"
    if not KEBAB.fullmatch(name):
        yield f"{loc}: name must be kebab-case"
    if not isinstance(entry, dict):
        yield f"{loc}: entry must be a map"
        return
    for key in entry:
        if key not in ENTRY_KEYS:
            yield f"{loc}: unknown key '{key}'"
    for key in ENTRY_KEYS:
        if key not in entry:
            yield f"{loc}.{key}: required"
    if "scope" in entry and not (isinstance(entry["scope"], str) and entry["scope"] in SCOPES):
        yield f"{loc}.scope: {entry['scope']!r} is not one of {', '.join(sorted(SCOPES))}"
    if "better" in entry and not (isinstance(entry["better"], str) and entry["better"] in BETTER):
        yield f"{loc}.better: {entry['better']!r} is not one of {', '.join(sorted(BETTER))}"
    for key in ("unit", "formula"):
        if key in entry and not (isinstance(entry[key], str) and entry[key].strip()):
            yield f"{loc}.{key}: must be a non-empty string"
    if "collector" in entry:
        path = entry["collector"]
        if not relative_path_ok(path, "collectors/", ".py"):
            yield f"{loc}.collector: must be a relative path under collectors/ ending .py"
        elif not file_under_root(root, path):
            yield f"{loc}.collector: file not found under root: {path}"
    if "reads" in entry:
        reads = entry["reads"]
        if not (isinstance(reads, list) and reads and all(isinstance(s, str) and SOURCE.fullmatch(s) for s in reads)):
            yield f"{loc}.reads: must be a non-empty list of source names"
        elif len(set(reads)) != len(reads):
            yield f"{loc}.reads: duplicate source"


def validate_catalog(files, root):
    """Validate one or more parsed catalog files. Returns every error; never raises on a JSON value."""
    errs, usable = [], []
    for label, data in files:
        bad = shape_errors(data)
        if bad:
            errs += [f"catalog {label}: {e}" for e in bad]
        else:
            usable.append((label, data))
    merged, merge_errs = merge_catalogs(usable)
    errs += merge_errs
    for name, entry in merged.items():
        errs += _entry_errors(name, entry, root)
    return errs


# ---------------------------------------------------------------- command line


def _print_errors(errs):
    for err in errs:
        print(f"ERROR: {err}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="validate_catalog.py", description="Validate metric catalog files.")
    parser.add_argument("--root", required=True, help="the org root that holds collectors/")
    parser.add_argument("files", nargs="+", metavar="FILE")
    args = parser.parse_args(argv)
    try:
        loaded = [(path, load_document(path)) for path in args.files]
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except LoadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    errs = validate_catalog(loaded, args.root)
    _print_errors(errs)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
