#!/usr/bin/env python3
"""Check workflow files against the vendored OWS 1.1.0 JSON Schema.

Usage: uv run --with jsonschema --with pyyaml python check_flow_schema.py [--schema FILE] FLOW.yaml...

Exit codes: 0 all valid, 1 schema violations, 2 unreadable input, 3 missing dependency.
Optional tooling: it never reports a pass when jsonschema or PyYAML is absent.
"""
import sys
from pathlib import Path

DEFAULT_SCHEMA = Path(__file__).resolve().parent.parent / "schemas" / "ows" / "workflow.yaml.upstream"
MAX_SHOWN = 8


def main(argv):
    try:
        import yaml
        import jsonschema
    except ImportError as exc:
        name = getattr(exc, "name", None) or str(exc)
        print(
            f"check_flow_schema: missing dependency '{name}'. "
            "Run: uv run --with jsonschema --with pyyaml python check_flow_schema.py ...",
            file=sys.stderr,
        )
        return 3

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

    try:
        schema = yaml.safe_load(schema_path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        print(f"check_flow_schema: cannot load schema {schema_path}: {exc}", file=sys.stderr)
        return 2
    validator = jsonschema.Draft202012Validator(schema)

    status = 0
    for name in args:
        try:
            doc = yaml.safe_load(Path(name).read_text())
        except (OSError, yaml.YAMLError) as exc:
            print(f"{name}: cannot read: {exc}", file=sys.stderr)
            status = max(status, 2)
            continue
        errors = sorted(validator.iter_errors(doc), key=lambda e: [str(p) for p in e.absolute_path])
        if not errors:
            print(f"{name}: OK")
            continue
        print(f"{name}: {len(errors)} errors")
        for e in errors[:MAX_SHOWN]:
            print(f"  /{'/'.join(map(str, e.absolute_path))} :: {e.message[:160]}")
        if len(errors) > MAX_SHOWN:
            print(f"  ... {len(errors) - MAX_SHOWN} more")
        status = max(status, 1)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
