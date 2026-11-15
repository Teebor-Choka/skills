#!/usr/bin/env python3
"""Validate a procedure's structure, never its content. Stdlib only.

A procedure is a frontmatter file with a `stages` map. This checks shape and wiring:
list-typed keys, dangling `needs`, cycles, `on-fail` targets, and that every kind a
non-entry stage consumes has an unconditional producer upstream. Unknown keys pass.

    validate_procedure.py FILE                 validate one procedure
    validate_procedure.py --base B --delta D   overlay D on B, then validate
"""
import argparse
import os
import sys
from graphlib import CycleError, TopologicalSorter

# Same parser the policy skill uses, so both files accept one frontmatter subset.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "policy"))
from policy_loader import PolicyError, _parse_frontmatter, _split_frontmatter  # noqa: E402

LIST_KEYS = ("needs", "consumes", "produces", "review")


def _parse(text, src):
    try:
        return _parse_frontmatter(_split_frontmatter(text, src), src), []
    except PolicyError as exc:
        return None, [str(exc)]


def _stages(fm, src):
    stages = fm.get("stages")
    if not isinstance(stages, dict) or not stages:
        return None, [f"{src}: no 'stages' map"]
    bad = [k for k, v in stages.items() if not isinstance(v, dict)]
    return stages, [f"{src}: stage '{k}' is not a map" for k in bad]


def _shape_errors(stages):
    errs = []
    for sid, st in stages.items():
        for key in LIST_KEYS:
            if key in st and not isinstance(st[key], list):
                errs.append(f"stage '{sid}': '{key}' must be a list like [a, b]")
        of = st.get("on-fail")
        if of is not None and not (isinstance(of, dict) and isinstance(of.get("to"), str)):
            errs.append(f"stage '{sid}': 'on-fail' must be a map with a stage id in 'to'")
    return errs


def _graph_errors(stages):
    errs = []
    for sid, st in stages.items():
        for dep in st.get("needs") or []:
            if dep not in stages:
                errs.append(f"stage '{sid}': needs unknown stage '{dep}'")
        of = st.get("on-fail")
        if of and of["to"] not in stages:
            errs.append(f"stage '{sid}': on-fail.to names unknown stage '{of['to']}'")
    if errs:
        return errs
    ts = TopologicalSorter({s: list(st.get("needs") or []) for s, st in stages.items()})
    try:
        ts.prepare()
    except CycleError as exc:
        return [f"cycle in needs: {' -> '.join(map(str, exc.args[1]))}"]
    return _retry_errors(stages)


def _retry_errors(stages):
    errs = []
    for sid, st in stages.items():
        to = (st.get("on-fail") or {}).get("to")
        if to and to != sid and to not in _ancestors(stages, sid):
            errs.append(f"stage '{sid}': on-fail.to '{to}' is not this stage or upstream of it")
    return errs


def _ancestors(stages, sid):
    seen, todo = set(), list(stages[sid].get("needs") or [])
    while todo:
        n = todo.pop()
        if n not in seen:
            seen.add(n)
            todo.extend(stages[n].get("needs") or [])
    return seen


def _kind_errors(stages):
    """A non-entry stage's consumed kind needs an unconditional upstream producer.

    An entry stage (no `needs`) consumes external input, so its kinds are not checked."""
    errs = []
    for sid, st in stages.items():
        if not st.get("needs"):
            continue
        ups = _ancestors(stages, sid)
        for kind in st.get("consumes") or []:
            makers = [u for u in ups if kind in (stages[u].get("produces") or [])]
            if not makers:
                errs.append(f"stage '{sid}': consumes '{kind}' but no upstream stage produces it")
            elif all("when" in stages[m] for m in makers):
                errs.append(
                    f"stage '{sid}': '{kind}' is produced only by conditional stage(s) "
                    f"{sorted(makers)}; add an unconditional producer or drop the 'when'"
                )
    return errs


def _validate_stages(stages):
    errs = _shape_errors(stages)
    if errs:
        return errs
    errs = _graph_errors(stages)
    return errs or _kind_errors(stages)


def validate_text(text, src="<text>"):
    """Return error strings for one procedure file; empty means valid."""
    fm, errs = _parse(text, src)
    if errs:
        return errs
    stages, errs = _stages(fm, src)
    return errs or _validate_stages(stages)


def merge(base_stages, delta_stages):
    """Per stage id, a delta's keys replace the base's; `disabled: true` removes the stage."""
    merged = {k: dict(v) for k, v in base_stages.items()}
    errs = []
    for sid, over in delta_stages.items():
        is_floor = merged.get(sid, {}).get("floor") is True
        if over.get("disabled") is True:
            if sid not in merged:
                errs.append(f"delta disables unknown stage '{sid}'")
            elif is_floor:
                errs.append(f"stage '{sid}' is floor and cannot be disabled")
            merged.pop(sid, None)
            continue
        if is_floor and ("floor" in over or "when" in over):
            errs.append(f"stage '{sid}' is floor: a delta cannot change 'floor' or add 'when'")
        merged.setdefault(sid, {}).update(over)
    return merged, errs


def validate_layers(base_text, delta_text, src="<delta>"):
    """Overlay a delta on a baseline, then validate the merged stages."""
    base_fm, errs = _parse(base_text, "<base>")
    delta_fm, errs2 = _parse(delta_text, src)
    if errs or errs2:
        return errs + errs2
    base, errs = _stages(base_fm, "<base>")
    delta, errs2 = _stages(delta_fm, src) if "stages" in delta_fm else ({}, [])
    if errs or errs2:
        return errs + errs2
    merged, errs = merge(base, delta)
    return errs or _validate_stages(merged)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--base")
    ap.add_argument("--delta")
    a = ap.parse_args(argv)
    if a.base and a.delta and not a.file:
        paths = (a.base, a.delta)
    elif a.file and not (a.base or a.delta):
        paths = (a.file,)
    else:
        ap.error("give FILE, or both --base and --delta")
    try:
        texts = [open(p, encoding="utf-8").read() for p in paths]
    except (OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    errs = validate_layers(*texts, paths[-1]) if len(texts) == 2 else validate_text(texts[0], paths[0])
    for e in errs:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
