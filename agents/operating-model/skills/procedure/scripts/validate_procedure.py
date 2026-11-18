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
BOOL_KEYS = ("disabled", "floor")
# A delta may not change these on a floor stage; `review` may only grow.
FLOOR_LOCKED = ("needs", "consumes", "produces", "skill")


def _load(text, src, required=True):
    """Parse a procedure and return (stages, errors). A delta may omit `stages`."""
    try:
        fm = _parse_frontmatter(_split_frontmatter(text, src), src)
    except PolicyError as exc:
        return None, [str(exc)]
    if not required and not fm.get("stages", {}):
        return {}, []
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
        for key in BOOL_KEYS:
            if key in st and not isinstance(st[key], bool):
                errs.append(f"stage '{sid}': '{key}' must be true or false")
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
        to = st.get("on-fail", {}).get("to")
        if to and to not in stages:
            errs.append(f"stage '{sid}': on-fail.to names unknown stage '{to}'")
    if errs:
        return errs
    ts = TopologicalSorter({s: list(st.get("needs") or []) for s, st in stages.items()})
    try:
        ts.prepare()
    except CycleError as exc:
        return [f"cycle in needs: {' -> '.join(map(str, exc.args[1]))}"]
    return []


def _retry_errors(stages):
    errs = []
    for sid, st in stages.items():
        to = st.get("on-fail", {}).get("to")
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
    # Each check assumes the one before it passed: ancestors need resolved `needs`.
    return (
        _shape_errors(stages)
        or _graph_errors(stages)
        or _retry_errors(stages)
        or _kind_errors(stages)
    )


def validate_text(text, src="<text>"):
    """Return error strings for one procedure file; empty means valid."""
    stages, errs = _load(text, src)
    return errs or _validate_stages(stages)


def _floor_delta_errors(sid, base_stage, over):
    """What a delta may not do to a floor stage: change its flag, wiring, skill, or drop reviews."""
    errs = []
    if "floor" in over or "when" in over:
        errs.append(f"stage '{sid}' is floor: a delta cannot change 'floor' or add 'when'")
    for key in FLOOR_LOCKED:
        if key in over and over[key] != base_stage.get(key):
            errs.append(f"stage '{sid}' is floor: a delta cannot change '{key}'")
    kept = over.get("review", base_stage.get("review") or [])
    if not isinstance(kept, list) or not set(base_stage.get("review") or []) <= set(kept):
        errs.append(f"stage '{sid}' is floor: a delta cannot remove review angles")
    return errs


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
        if is_floor:
            errs += _floor_delta_errors(sid, merged[sid], over)
        merged.setdefault(sid, {}).update(over)
    return merged, errs


def validate_layers(base_text, delta_text, src="<delta>"):
    """Overlay a delta on a baseline, then validate the merged stages."""
    base, errs = _load(base_text, "<base>")
    delta, errs2 = _load(delta_text, src, required=False)
    if errs or errs2:
        return errs + errs2
    errs = _validate_stages(base)
    if errs:
        return [f"<base>: {e}" for e in errs]
    merged, errs = merge(base, delta)
    return errs or _validate_stages(merged) or _floor_errors(base, merged)


def _floor_errors(base, merged):
    """A floor stage keeps everything that waited on it, and nothing upstream is conditional."""
    errs = []
    for fid, bst in base.items():
        if bst.get("floor") is not True or fid not in merged:
            continue
        if any("when" in merged[a] for a in _ancestors(merged, fid)):
            errs.append(f"stage '{fid}' is floor: no upstream stage may carry 'when'")
        for sid in base:
            if sid in merged and fid in _ancestors(base, sid) and fid not in _ancestors(merged, sid):
                errs.append(f"stage '{sid}' no longer runs after floor stage '{fid}'")
    return errs


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
    layered = bool(a.base)
    errs = validate_layers(*texts, paths[-1]) if layered else validate_text(texts[0], paths[0])
    for e in errs:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
