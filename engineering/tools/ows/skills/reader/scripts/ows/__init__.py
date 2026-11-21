"""Read and validate OWS workflow files that carry `metadata.org` governance.

    from ows import load, validate, tasks, floors

Standard library only; PyYAML is imported only to read a .yaml or .yml file. The validators are the
modules `validate_org`, `validate_catalog` and `validate_manifest`; `expr` is the runtime expression subset.
"""
from . import expr, validate_catalog, validate_manifest, validate_org  # noqa: F401
from .validate_org import LoadError, UsageError, load_file as load  # noqa: F401

__all__ = ["load", "validate", "tasks", "floors", "LoadError", "UsageError"]


def validate(doc, catalog, manifest):
    """Errors for one parsed workflow against a merged catalog and a manifest; empty means valid. Never raises."""
    return validate_org.validate_org(doc, catalog, manifest)


def _nodes(doc):
    nodes = []
    if isinstance(doc, dict):
        try:
            validate_org._walk(doc.get("do", []), "", 1, [], nodes, None)
        except validate_org._TooManyTasks:
            pass
    return nodes


def tasks(doc):
    """Every task in pre-order, with the keys a validator error would name it by.

    Each row: key (the task path), kind, by, role, brief, floor, acceptance, metrics, calls (the called
    workflow's name, for kind call). A value the task does not declare is None.
    """
    rows = []
    for n in _nodes(doc):
        org = validate_org._org(n["task"])
        call = validate_org._map(validate_org._map(n["task"].get("run")).get("workflow")).get("name")
        rows.append({
            "key": n["path"],
            "kind": n["kind"],
            "by": org.get("by"),
            "role": org.get("role"),
            "brief": org.get("brief"),
            "floor": org.get("floor") is True,
            "acceptance": org.get("acceptance"),
            "metrics": org.get("metrics"),
            "calls": call if n["kind"] == "call" else None,
        })
    return rows


def floors(doc, manifest=None):
    """Floor tasks in pre-order: leaf tasks with `floor: true`, and, when a manifest is given, calls to a
    workflow whose manifest entry lists floors. Each row: key, kind, calls."""
    wfs = validate_org._map(validate_org._map(manifest).get("workflows"))
    out = []
    for row in tasks(doc):
        if row["kind"] in validate_org.LEAF and row["floor"]:
            out.append({"key": row["key"], "kind": row["kind"], "calls": row["calls"]})
        elif row["kind"] == "call" and isinstance(row["calls"], str) and row["calls"] in wfs:
            listed = validate_org._map(wfs[row["calls"]]).get("floors")
            if isinstance(listed, list) and listed:
                out.append({"key": row["key"], "kind": row["kind"], "calls": row["calls"]})
    return out
