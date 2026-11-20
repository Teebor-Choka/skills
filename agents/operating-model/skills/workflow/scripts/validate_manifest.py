#!/usr/bin/env python3
"""Manifest validator (spec sections 2 and 8).

Usage: validate_manifest.py --root DIR --catalog FILE [--catalog FILE ...] MANIFEST

Standard library only. It loads every workflow the manifest lists, to check the document name and the
start graph (calls and emits) for cycles. It does not run validate_org on them.
Exit codes: 0 valid, 1 invalid or a load error, 2 usage error.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate_catalog import (  # noqa: E402
    KEBAB,
    NAMESPACE,
    LoadError,
    UsageError,
    file_under_root,
    load_document,
    merge_catalogs,
    relative_path_ok,
    shape_errors,
)

OWNER = "owner"
TOP_KEYS = ("owner", "namespace", "roles", "workflows", "targets", "vetoes")
ROLE_KEYS = ("escalates-to", "may-spawn", "summary")
WORKFLOW_KEYS = ("path", "floors")
TARGET_KEYS = ("at-most", "at-least", "per")
PER = ("item", "run", "unit")
WORKFLOW_SUFFIXES = (".yaml", ".yml", ".json")
MAX_LISTS = 16


def _map(value):
    return value if isinstance(value, dict) else {}


def _is_name(value, table):
    return isinstance(value, str) and value in table


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _literal(value):
    return isinstance(value, str) and "${" not in value


# ---------------------------------------------------------------- roles (8.2)


def _chain(roles, role):
    """Roles above `role` up to owner, or None on a cycle."""
    seen, above = {role}, []
    while True:
        nxt = roles[role]["escalates-to"]
        if nxt == OWNER:
            return above
        if nxt in seen:
            return None
        seen.add(nxt)
        above.append(nxt)
        role = nxt


def _role_errors(roles):
    errs = []
    if OWNER in roles:
        errs.append(f"manifest: roles.{OWNER}: 'owner' is reserved for the top rung; do not declare it")
    for name, role in roles.items():
        loc = f"manifest: roles.{name}"
        if not KEBAB.match(name):
            errs.append(f"{loc}: name must be kebab-case")
        if not isinstance(role, dict):
            errs.append(f"{loc}: must be a map")
            continue
        for key in role:
            if key not in ROLE_KEYS:
                errs.append(f"{loc}: unknown key '{key}'")
        up = role.get("escalates-to")
        if up is None:
            errs.append(f"{loc}.escalates-to: required")
        elif up != OWNER and not _is_name(up, roles):
            errs.append(f"{loc}.escalates-to: unknown role {up!r}")
        spawn = role.get("may-spawn", [])
        if not isinstance(spawn, list):
            errs.append(f"{loc}.may-spawn: must be a list of roles")
            continue
        for target in spawn:
            if target == OWNER:
                errs.append(f"{loc}.may-spawn: 'owner' cannot be spawned")
            elif not _is_name(target, roles):
                errs.append(f"{loc}.may-spawn: unknown role {target!r}")
    if errs or not roles:
        return errs
    chains = {name: _chain(roles, name) for name in roles}
    loops = [f"manifest: roles.{n}: escalation chain never reaches owner" for n, c in chains.items() if c is None]
    if loops:
        return loops
    for name, role in roles.items():
        for target in role.get("may-spawn", []):
            if target != name and name not in chains[target]:
                errs.append(f"manifest: roles.{name}.may-spawn: {target!r} is not below {name} on the ladder")
    return errs


# ---------------------------------------------------------------- workflow entries (8.3)


def _entry_errors(workflows, root):
    errs = []
    for name, entry in workflows.items():
        loc = f"manifest: workflows.{name}"
        if not KEBAB.match(name):
            errs.append(f"{loc}: name must be kebab-case")
        if not isinstance(entry, dict):
            errs.append(f"{loc}: must be a map")
            continue
        for key in entry:
            if key not in WORKFLOW_KEYS:
                errs.append(f"{loc}: unknown key '{key}'")
        if "path" not in entry:
            errs.append(f"{loc}.path: required")
        elif not relative_path_ok(entry["path"], "workflows/", WORKFLOW_SUFFIXES):
            errs.append(f"{loc}.path: must be a relative path under workflows/ ending .yaml, .yml or .json")
        elif not file_under_root(root, entry["path"]):
            errs.append(f"{loc}.path: file not found under root: {entry['path']}")
        if "floors" not in entry:
            errs.append(f"{loc}.floors: required")
        else:
            floors = entry["floors"]
            if not (isinstance(floors, list) and all(isinstance(f, str) and KEBAB.match(f) for f in floors)):
                errs.append(f"{loc}.floors: must be a list of task names")
            elif len(set(floors)) != len(floors):
                errs.append(f"{loc}.floors: duplicate task name")
    return errs


def _load_workflows(workflows, root, errs):
    """Load each listed workflow that exists. Returns {name: document}."""
    docs = {}
    for name, entry in workflows.items():
        if not (
            isinstance(entry, dict)
            and relative_path_ok(entry.get("path"), "workflows/", WORKFLOW_SUFFIXES)
            and file_under_root(root, entry["path"])
        ):
            continue
        loc = f"manifest: workflows.{name}.path"
        try:
            doc = load_document(os.path.join(root, entry["path"]))
        except LoadError as exc:
            errs.append(f"{loc}: {exc.msg}")
            continue
        if not isinstance(doc, dict):
            errs.append(f"{loc}: workflow must be a map")
            continue
        found = _map(doc.get("document")).get("name")
        if found != name:
            errs.append(f"{loc}: document.name is {found!r}, expected '{name}'")
        docs[name] = doc
    return docs


def _walk(name, doc, errs):
    """Every task of a workflow as (path, task). Shape problems become located errors."""
    loc = f"manifest: workflows.{name}.path"
    out = []

    def lst(items, prefix, depth):
        if not isinstance(items, list):
            errs.append(f"{loc}: {prefix or 'do'}: task list must be a list")
            return
        for i, item in enumerate(items):
            if not (isinstance(item, dict) and len(item) == 1):
                errs.append(f"{loc}: {prefix + '/' if prefix else ''}[{i}]: task item must be a map with one name")
                continue
            ((task_name, task),) = item.items()
            path = f"{prefix}/{task_name}" if prefix else str(task_name)
            if depth > MAX_LISTS:
                errs.append(f"{loc}: {path}: nesting deeper than {MAX_LISTS} task lists")
                return
            if not isinstance(task, dict):
                errs.append(f"{loc}: {path}: task must be a map")
                continue
            out.append((path, task))
            for sub in (task.get("do"), task.get("try"), _map(task.get("catch")).get("do"),
                        _map(task.get("fork")).get("branches")):
                if sub is not None:
                    lst(sub, path, depth + 1)

    if "do" in doc:
        lst(doc["do"], "", 1)
    return out


def _event_types(to):
    """Event types named in a listen.to or schedule.on map."""
    to = _map(to)
    found = []
    if "one" in to:
        found.append(_map(_map(to["one"]).get("with")).get("type"))
    for key in ("any", "all"):
        if isinstance(to.get(key), list):
            found += [_map(_map(e).get("with")).get("type") for e in to[key]]
    return [t for t in found if isinstance(t, str)]


def _is_decision_gate(task):
    org = _map(_map(task.get("metadata")).get("org"))
    acceptance = org.get("acceptance")
    items = acceptance if isinstance(acceptance, list) else []
    return org.get("role") == OWNER or any(isinstance(i, dict) and "human" in i for i in items)


def _cycle_error(edges):
    """First back edge of a sorted DFS, then the shortest path back (spec 8.3). At most one error."""
    state, back = {}, []

    def dfs(v):
        state[v] = 1
        for x in sorted(edges[v]):
            if back:
                return
            if state.get(x) == 1:
                back.append((v, x))
                return
            if x not in state:
                dfs(x)
        state[v] = 2

    for v in sorted(edges):
        if back:
            break
        if v not in state:
            dfs(v)
    if not back:
        return None
    u, v = back[0]
    prev, level = {v: None}, [v]
    while level and u not in prev:
        nxt = []
        for a in level:
            for b in sorted(edges[a]):
                if b not in prev:
                    prev[b] = a
                    nxt.append(b)
        level = nxt
    path, x = [], u
    while x is not None:
        path.append(x)
        x = prev[x]
    cycle = list(reversed(path)) + [v]
    return "manifest: workflows: start cycle " + " -> ".join(f"'{n}'" for n in cycle)


def _graph_errors(docs, errs):
    starts, edges, emits, gates = {}, {n: set() for n in docs}, {}, {}
    for name, doc in docs.items():
        starts[name] = {t for t in _event_types(_map(doc.get("schedule")).get("on")) if _literal(t)}
        for path, task in _walk(name, doc, errs):
            target = _map(_map(task.get("run")).get("workflow")).get("name")
            if isinstance(target, str) and target in docs:
                edges[name].add(target)
            if "emit" in task:
                etype = _map(_map(_map(task["emit"]).get("event")).get("with")).get("type")
                if _literal(etype):
                    emits.setdefault(name, []).append((path, etype))
            if "listen" in task and _is_decision_gate(task):
                for etype in _event_types(_map(task["listen"]).get("to")):
                    if _literal(etype):
                        gates.setdefault(etype, []).append((name, path))
    for name, found in emits.items():
        for path, etype in found:
            for other in docs:
                if etype in starts[other]:
                    edges[name].add(other)
            for other, gate_path in gates.get(etype, []):
                if other != name:
                    errs.append(
                        f"manifest: workflows.{name}: emit '{path}' type '{etype}' "
                        f"is listened on by gate '{other}:{gate_path}'"
                    )
    cycle = _cycle_error(edges)
    if cycle:
        errs.append(cycle)


# ---------------------------------------------------------------- targets (8.4)


def _target_errors(targets, catalog):
    errs = []
    for name, target in targets.items():
        loc = f"manifest: targets.{name}"
        if name not in catalog:
            errs.append(f"{loc}: unknown metric '{name}'")
        if not isinstance(target, dict):
            errs.append(f"{loc}: must be a map")
            continue
        for key in target:
            if key not in TARGET_KEYS:
                errs.append(f"{loc}: unknown key '{key}'")
        bounds = [k for k in ("at-least", "at-most") if k in target]
        if len(bounds) != 1:
            errs.append(f"{loc}: exactly one of at-least, at-most")
        elif not _number(target[bounds[0]]):
            errs.append(f"{loc}.{bounds[0]}: must be a finite number")
        if "per" in target and not (isinstance(target["per"], str) and target["per"] in PER):
            errs.append(f"{loc}.per: {target['per']!r} is not one of {', '.join(PER)}")
    return errs


# ---------------------------------------------------------------- entry point


def validate_manifest(manifest, catalog, root):
    """Validate a parsed manifest against the merged catalog and the org root. Never raises on a JSON value."""
    if not isinstance(manifest, dict):
        return ["manifest: must be a map"]
    bad = shape_errors(manifest)
    if bad:
        return [f"manifest: {e}" for e in bad]
    catalog = _map(catalog)
    errs = []
    for key in manifest:
        if key not in TOP_KEYS:
            errs.append(f"manifest: unknown key '{key}'")
    for key in ("owner", "namespace", "roles", "workflows", "vetoes"):
        if key not in manifest:
            errs.append(f"manifest: {key}: required")
    if "owner" in manifest and not (isinstance(manifest["owner"], str) and manifest["owner"].strip()):
        errs.append("manifest: owner: must be a non-empty string")
    if "namespace" in manifest and not (
        isinstance(manifest["namespace"], str) and NAMESPACE.match(manifest["namespace"])
    ):
        errs.append("manifest: namespace: must match the OWS namespace pattern")

    roles = manifest.get("roles", {})
    if "roles" in manifest and not (isinstance(roles, dict) and roles):
        errs.append("manifest: roles: must be a non-empty map")
    errs += _role_errors(roles) if isinstance(roles, dict) else []

    workflows = manifest.get("workflows", {})
    if "workflows" in manifest and not (isinstance(workflows, dict) and workflows):
        errs.append("manifest: workflows: must be a non-empty map")
    if isinstance(workflows, dict):
        errs += _entry_errors(workflows, root)
        _graph_errors(_load_workflows(workflows, root, errs), errs)

    if "targets" in manifest:
        targets = manifest["targets"]
        if isinstance(targets, dict):
            errs += _target_errors(targets, catalog)
        else:
            errs.append("manifest: targets: must be a map")

    vetoes = manifest.get("vetoes")
    if "vetoes" in manifest and not (
        isinstance(vetoes, list) and vetoes and all(isinstance(v, str) and v.strip() for v in vetoes)
    ):
        errs.append("manifest: vetoes: must be a non-empty list of strings")
    return errs


def main(argv=None):
    parser = argparse.ArgumentParser(prog="validate_manifest.py", description="Validate an org manifest.")
    parser.add_argument("--root", required=True, help="the org root that holds workflows/")
    parser.add_argument("--catalog", action="append", required=True, metavar="FILE")
    parser.add_argument("manifest", metavar="MANIFEST")
    args = parser.parse_args(argv)
    try:
        catalog_files = [(path, load_document(path)) for path in args.catalog]
        manifest = load_document(args.manifest)
        catalog, errs = merge_catalogs(catalog_files)
        if not errs:
            errs = validate_manifest(manifest, catalog, args.root)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except LoadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    for err in errs:
        print(f"ERROR: {err}", file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
