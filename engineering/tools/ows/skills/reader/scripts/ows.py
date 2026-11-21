#!/usr/bin/env python3
"""Read and validate OWS workflow files with `metadata.org` governance.

    ows.py validate --catalog FILE [--catalog FILE ...] --manifest FILE WORKFLOW [WORKFLOW ...] [--json]
    ows.py tasks WORKFLOW [--json]
    ows.py floors WORKFLOW [--manifest FILE] [--json]

`validate` prints the same `ERROR:` lines as validate_org.py; with --json it prints {"errors": [...]} on stdout.
`tasks` lists every task in pre-order: key, kind, and `floor` when the task is a floor.
`floors` lists the floor tasks; with --manifest, calls to a workflow that has floors count too.
Files are JSON, or YAML when PyYAML is importable.
Exit 0: valid or listed. Exit 1: invalid, or a load error. Exit 2: usage error.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ows  # noqa: E402
from ows import validate_org  # noqa: E402


def _validate(args):
    if not args.json:
        argv = [a for c in args.catalog for a in ("--catalog", c)] + ["--manifest", args.manifest, *args.workflows]
        return validate_org.main(argv)
    # Same order as validate_org.main: every load error first, then catalog merge errors, then the workflows.
    errors = []

    def load(path):
        try:
            return ows.load(path)
        except ows.LoadError as e:
            errors.append(str(e))
        return None

    try:
        catalogs = [(p, load(p)) for p in args.catalog]
        manifest = load(args.manifest)
        docs = [(p, load(p)) for p in args.workflows]
    except ows.UsageError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    if not errors:
        catalog, errors = validate_org.merge_catalogs(catalogs)
    if not errors:
        errors = [f"{p}: {e}" for p, doc in docs for e in ows.validate(doc, catalog, manifest)]
    print(json.dumps({"errors": errors}, indent=2))
    return 1 if errors else 0


def _load_or_exit(path):
    try:
        return ows.load(path), 0
    except ows.UsageError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return None, 2
    except ows.LoadError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return None, 1


def _tasks(args):
    doc, code = _load_or_exit(args.workflow)
    if code:
        return code
    rows = ows.tasks(doc)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print("\t".join([r["key"], str(r["kind"])] + (["floor"] if r["floor"] else [])))
    return 0


def _floors(args):
    doc, code = _load_or_exit(args.workflow)
    manifest = None
    if not code and args.manifest:
        manifest, code = _load_or_exit(args.manifest)
    if code:
        return code
    rows = ows.floors(doc, manifest)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print("\t".join([r["key"], r["kind"]] + ([r["calls"]] if r["calls"] else [])))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ows.py", description="Read and validate OWS workflow files.")
    sub = ap.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate", help="validate workflows against a catalog and a manifest")
    v.add_argument("--catalog", action="append", required=True, metavar="FILE")
    v.add_argument("--manifest", required=True, metavar="FILE")
    v.add_argument("--json", action="store_true")
    v.add_argument("workflows", nargs="+", metavar="WORKFLOW")
    t = sub.add_parser("tasks", help="list every task in pre-order")
    t.add_argument("--json", action="store_true")
    t.add_argument("workflow", metavar="WORKFLOW")
    f = sub.add_parser("floors", help="list the floor tasks")
    f.add_argument("--manifest", metavar="FILE")
    f.add_argument("--json", action="store_true")
    f.add_argument("workflow", metavar="WORKFLOW")
    args = ap.parse_args(argv)
    return {"validate": _validate, "tasks": _tasks, "floors": _floors}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
