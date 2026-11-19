#!/usr/bin/env python3
"""Check workflow files against the vendored OWS 1.1.0 JSON Schema.

Usage: uv run --with jsonschema --with pyyaml python check_flow_schema.py [--schema FILE] FLOW.yaml...

Exit codes: 0 all valid, 1 schema violations, 2 unreadable or unparseable input
(bad encoding, multiple documents, duplicate keys, bad schema), 3 missing dependency.
Optional tooling: it never reports a pass when jsonschema or PyYAML is absent.

PyYAML parses YAML 1.1, where unquoted on, yes and no are booleans. The loader here
keeps only true and false as booleans, so the vendored schema's `read: [ on ]` stays
the string "on". Other YAML 1.1 quirks remain, so a flow can false-fail with exit 1.
It never false-passes.
"""
import re
import sys
from pathlib import Path

DEFAULT_SCHEMA = Path(__file__).resolve().parent.parent / "schemas" / "ows" / "workflow.yaml.upstream"
MAX_SHOWN = 8
HINT = "uv run --with jsonschema --with pyyaml python check_flow_schema.py ..."
PACKAGES = {"yaml": "PyYAML", "jsonschema": "jsonschema"}


def strict_loader(yaml):
    class StrictLoader(yaml.SafeLoader):
        pass

    def construct_mapping(loader, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in seen:
                raise yaml.YAMLError(f"duplicate mapping key {key!r} (line {key_node.start_mark.line + 1})")
            seen.add(key)
        return yaml.SafeLoader.construct_mapping(loader, node, deep)

    # YAML 1.2 booleans: drop the 1.1 resolver (on/off/yes/no), then allow true/false only.
    StrictLoader.yaml_implicit_resolvers = {
        ch: [(tag, rx) for tag, rx in rules if tag != "tag:yaml.org,2002:bool"]
        for ch, rules in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    StrictLoader.add_implicit_resolver(
        "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
    )
    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)
    return StrictLoader


def main(argv):
    missing = []
    try:
        import yaml
    except ImportError:
        missing.append(PACKAGES["yaml"])
    try:
        import jsonschema
    except ImportError:
        missing.append(PACKAGES["jsonschema"])
    if missing:
        names = ", ".join(f"'{m}'" for m in missing)
        print(f"check_flow_schema: missing dependency {names}. Run: {HINT}", file=sys.stderr)
        return 3
    if not hasattr(jsonschema, "Draft202012Validator"):
        print(
            "check_flow_schema: installed jsonschema lacks Draft202012Validator (needs 4.0 or newer). "
            f"Run: {HINT}",
            file=sys.stderr,
        )
        return 3
    from jsonschema.exceptions import SchemaError, best_match

    args = list(argv)
    schema_path = DEFAULT_SCHEMA
    if args[:1] == ["--schema"]:
        if len(args) < 2:
            print("check_flow_schema: --schema needs a file", file=sys.stderr)
            return 2
        schema_path = Path(args[1])
        args = args[2:]
    if not args:
        print("usage: check_flow_schema.py [--schema FILE] FLOW.yaml...", file=sys.stderr)
        return 2

    loader = strict_loader(yaml)
    try:
        schema = yaml.load(schema_path.read_text(encoding="utf-8"), Loader=loader)
        if not isinstance(schema, dict) or not schema:
            raise ValueError("schema is empty")
        jsonschema.Draft202012Validator.check_schema(schema)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, SchemaError, ValueError) as exc:
        print(f"check_flow_schema: cannot use schema {schema_path}: {exc}", file=sys.stderr)
        return 2
    validator = jsonschema.Draft202012Validator(schema)

    status = 0
    for name in args:
        try:
            doc = yaml.load(Path(name).read_text(encoding="utf-8"), Loader=loader)
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            print(f"{name}: cannot read: {exc}", file=sys.stderr)
            status = max(status, 2)
            continue
        errors = sorted(validator.iter_errors(doc), key=lambda e: [str(p) for p in e.absolute_path])
        if not errors:
            print(f"{name}: OK")
            continue
        print(f"{name}: {len(errors)} errors")
        for e in errors[:MAX_SHOWN]:
            leaf = best_match(e.context) if e.context else e
            print(f"  /{'/'.join(map(str, leaf.absolute_path))} :: {leaf.message[:160]}")
        if len(errors) > MAX_SHOWN:
            print(f"  ... {len(errors) - MAX_SHOWN} more")
        status = max(status, 1)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
