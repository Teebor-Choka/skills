#!/usr/bin/env python3
"""Validate a procedure's structure, never its content. Stdlib only.

A procedure is a frontmatter file with a `stages` map and optional id maps such as `entities`.
This checks shape and wiring: list-typed keys, dangling `needs`, cycles, `on-fail` targets,
that every kind a non-entry stage consumes has an unconditional producer upstream, and that
entities form a ladder that reaches the owner with downward-only spawning. Unknown keys pass.

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

OWNER = "owner"  # the user: the reserved last rung of every ladder
LIST_KEYS = ("needs", "consumes", "produces", "review", "metrics")
BOOL_KEYS = ("disabled", "floor")
# A delta may not change these on a floor stage; `review` may only grow.
FLOOR_LOCKED = ("needs", "consumes", "produces", "skill", "entity")
# Top-level maps of id -> map that a delta overlays per id, like `stages`.
ID_MAPS = ("entities", "loops", "kpis")
# The protected set: keys a delta cannot change on an existing id, and ids it cannot remove.
PROTECTED_KEYS = {"entities": ("escalates-to",), "loops": ("on-exhausted",), "kpis": ("owner",)}
PROTECTED_IDS = ("loops", "kpis")
# The closed vocabulary of `when` and loop `exit` conditions: a runner evaluates these without a model.
PREDICATES = {"paths": list, "kind": str, "policy": str}


def _load(text, src, required=True):
    """Parse a procedure and return (proc, errors). A delta may omit `stages`."""
    try:
        fm = _parse_frontmatter(_split_frontmatter(text, src), src)
    except PolicyError as exc:
        return None, [str(exc)]
    errs = []
    proc = {}
    for name in ID_MAPS:
        found = fm.get(name)
        if found is None:
            continue
        if isinstance(found, dict) and all(isinstance(v, dict) for v in found.values()):
            proc[name] = found
        else:
            errs.append(f"{src}: '{name}' must be a map of maps")
    if "change" in fm:
        proc["change"] = fm["change"]
    stages = fm.get("stages", {})
    if not required and not stages:
        proc["stages"] = {}
        return proc, errs
    if not isinstance(stages, dict) or not stages:
        return None, errs + [f"{src}: no 'stages' map"]
    proc["stages"] = stages
    bad = [k for k, v in stages.items() if not isinstance(v, dict)]
    return proc, errs + [f"{src}: stage '{k}' is not a map" for k in bad]


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


def _chain(ents, eid):
    """The entities above `eid` on its escalation ladder, nearest first; None if it loops."""
    seen, above = {eid}, []
    while True:
        nxt = ents[eid]["escalates-to"]
        if nxt == OWNER:
            return above
        if nxt in seen:
            return None
        seen.add(nxt)
        above.append(nxt)
        eid = nxt


def _entity_errors(proc):
    """Entities form a ladder that reaches the owner; spawning only goes down or to a peer."""
    ents = proc.get("entities")
    if ents is None:
        return []
    errs = [f"entity '{OWNER}' is reserved for the user, the last rung"] if OWNER in ents else []
    for eid, e in ents.items():
        to = e.get("escalates-to")
        if not isinstance(to, str) or (to != OWNER and to not in ents):
            errs.append(f"entity '{eid}': escalates-to names unknown entity '{to}'")
        may = e.get("may-spawn", [])
        if not isinstance(may, list):
            errs.append(f"entity '{eid}': 'may-spawn' must be a list like [a, b]")
            continue
        for t in may:
            if t == OWNER:
                errs.append(f"entity '{eid}': may-spawn names '{OWNER}', which cannot be spawned")
            elif t not in ents:
                errs.append(f"entity '{eid}': may-spawn names unknown entity '{t}'")
    if errs:
        return errs
    chains = {eid: _chain(ents, eid) for eid in ents}
    errs = [f"entity '{e}': escalation chain never reaches {OWNER}" for e, c in chains.items() if c is None]
    if errs:
        return errs
    for eid, e in ents.items():
        for t in e.get("may-spawn", []):
            if t != eid and eid not in chains[t]:
                errs.append(f"entity '{eid}': may-spawn '{t}', which is not below it on the ladder")
    for sid, st in proc["stages"].items():
        ent = st.get("entity")
        if ent is None:
            errs.append(f"stage '{sid}': needs an 'entity' because entities are defined")
        elif not isinstance(ent, str) or ent not in ents:
            errs.append(f"stage '{sid}': entity '{ent}' is not defined")
    return errs


def _known_kinds(stages):
    """Kinds a predicate may name: produced by a stage, or supplied to an entry stage."""
    kinds = set()
    for st in stages.values():
        kinds.update(st.get("produces") or [])
        if not st.get("needs"):
            kinds.update(st.get("consumes") or [])
    return kinds


def _predicate_errors(where, pred, kinds):
    names = ", ".join(sorted(PREDICATES))
    if not isinstance(pred, dict) or not pred:
        return [f"{where}: must be a map of predicates ({names})"]
    errs = []
    for key, val in pred.items():
        want = PREDICATES.get(key)
        if want is None:
            errs.append(f"{where}: unknown predicate '{key}' (allowed: {names})")
        elif not isinstance(val, want) or not val:
            errs.append(f"{where}: '{key}' must be a non-empty {want.__name__}")
        elif key == "kind" and val not in kinds:
            errs.append(f"{where}: kind '{val}' is not produced by any stage")
    return errs


def _when_errors(stages):
    kinds = _known_kinds(stages)
    return [
        e
        for sid, st in stages.items()
        if "when" in st
        for e in _predicate_errors(f"stage '{sid}': 'when'", st["when"], kinds)
    ]


def _loop_errors(proc):
    """A loop names its members, a closed exit, a positive bound and who hears of exhaustion."""
    stages, ents = proc["stages"], proc.get("entities")
    kinds = _known_kinds(stages)
    errs = []
    for name, lp in (proc.get("loops") or {}).items():
        where = f"loop '{name}'"
        members = lp.get("stages")
        if not isinstance(members, list) or not members:
            errs.append(f"{where}: 'stages' must be a non-empty list like [a, b]")
            members = []
        errs += [f"{where}: stage '{m}' does not exist" for m in members if m not in stages]
        bound = lp.get("bound")
        if not (isinstance(bound, str) and bound.isdecimal() and int(bound) > 0):
            errs.append(f"{where}: 'bound' must be a positive integer, the maximum rounds")
        if "exit" not in lp:
            errs.append(f"{where}: needs an 'exit' condition")
        else:
            errs += _predicate_errors(f"{where}: 'exit'", lp["exit"], kinds)
        to = lp.get("on-exhausted")
        if not isinstance(to, str) or (to != OWNER and to not in (ents or {})):
            errs.append(f"{where}: 'on-exhausted' must name an entity or '{OWNER}', not '{to}'")
        carries = lp.get("carries")
        if carries is not None and not any(
            carries in (stages[m].get("produces") or []) for m in members if m in stages
        ):
            errs.append(f"{where}: carries '{carries}', which no member stage produces")
    return errs


def _declared_metrics(stages):
    return {m for st in stages.values() for m in (st.get("metrics") or [])}


def _metric_errors(proc):
    """Every stage declares a metric, and a KPI that its project manager or the user owns links it."""
    stages, kpis, ents = proc["stages"], proc.get("kpis") or {}, proc.get("entities") or {}
    declared = _declared_metrics(stages)
    errs = [
        f"stage '{sid}': needs at least one metric in 'metrics', linked to a kpi"
        for sid, st in stages.items()
        if not st.get("metrics")
    ]
    linked = set()
    for name, k in kpis.items():
        owner = k.get("owner")
        if not isinstance(owner, str) or (owner != OWNER and owner not in ents):
            errs.append(f"kpi '{name}': 'owner' must name an entity or '{OWNER}'")
        ms = k.get("metrics")
        if not isinstance(ms, list) or not ms:
            errs.append(f"kpi '{name}': 'metrics' must be a non-empty list like [a, b]")
            continue
        linked.update(ms)
        errs += [f"kpi '{name}': metric '{m}' is not declared by any stage" for m in ms if m not in declared]
    errs += [f"metric '{m}' is not linked to any kpi" for m in sorted(declared - linked, key=str)]
    return errs


def _change_errors(change, merged):
    """A change to the procedure names what it should move, which way, and how long to watch."""
    if not isinstance(change, dict):
        return ["a delta needs a 'change' map: metrics, direction, window"]
    errs = []
    ms = change.get("metrics")
    if not isinstance(ms, list) or not ms:
        errs.append("change: 'metrics' must list the metrics the change should move")
    else:
        declared = _declared_metrics(merged["stages"])
        errs += [f"change: metric '{m}' is not declared by any stage" for m in ms if m not in declared]
    if change.get("direction") not in ("up", "down"):
        errs.append("change: 'direction' must be 'up' or 'down'")
    window = change.get("window")
    if not isinstance(window, str) or not window:
        errs.append("change: 'window' must name the observation window, such as '5 runs'")
    return errs


def _validate(proc, strict=True):
    # Each check assumes the one before it passed: ancestors need resolved `needs`.
    stages = proc["stages"]
    return (
        _shape_errors(stages)
        or _when_errors(stages)
        or _graph_errors(stages)
        or _retry_errors(stages)
        or _kind_errors(stages)
        or _entity_errors(proc)
        or _loop_errors(proc)
        or (_metric_errors(proc) if strict else [])
    )


def validate_text(text, src="<text>", strict=True):
    """Return error strings for one procedure file; empty means valid.

    `strict` adds the rules every real procedure must meet (metrics and KPIs)."""
    proc, errs = _load(text, src)
    return errs or _validate(proc, strict)


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


def _merge_stages(base_stages, delta_stages):
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


def _raises(new, old):
    """True when both are positive integers and `new` is larger."""
    return all(isinstance(x, str) and x.isdecimal() for x in (new, old)) and int(new) > int(old)


def _merge_map(name, base_map, delta_map):
    """Overlay an id map per id; `disabled: true` removes the id.

    The protected set stays out of a delta's reach: the ladder's rungs, where a loop escalates,
    a loop's round bound, and who owns a KPI. Changing them needs the owner."""
    merged = {k: dict(v) for k, v in base_map.items()}
    errs = []
    for key, over in delta_map.items():
        old = merged.get(key)
        if over.get("disabled") is True:
            if old is not None and name in PROTECTED_IDS:
                errs.append(f"{name}.{key} is protected: a delta cannot remove it")
            else:
                merged.pop(key, None)
            continue
        if old is not None:
            for k in PROTECTED_KEYS.get(name, ()):
                if k in over and over[k] != old.get(k):
                    errs.append(f"{name}.{key}: '{k}' is protected; changing it needs the owner")
            if name == "loops" and "bound" in over and _raises(over["bound"], old.get("bound")):
                errs.append(f"loops.{key}: a delta cannot raise 'bound'")
        merged.setdefault(key, {}).update(over)
    return merged, errs


def merge(base, delta):
    """Overlay a delta procedure on a base. Returns (merged, errors)."""
    stages, errs = _merge_stages(base["stages"], delta["stages"])
    merged = {"stages": stages}
    for name in ID_MAPS:
        if name in base or name in delta:
            merged[name], more = _merge_map(name, base.get(name, {}), delta.get(name, {}))
            errs += more
    return merged, errs


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


def validate_layers(base_text, delta_text, src="<delta>", strict=True):
    """Overlay a delta on a baseline, then validate the merged procedure."""
    base, errs = _load(base_text, "<base>")
    delta, errs2 = _load(delta_text, src, required=False)
    if errs or errs2:
        return errs + errs2
    errs = _validate(base, strict)
    if errs:
        return [f"<base>: {e}" for e in errs]
    merged, errs = merge(base, delta)
    errs = errs or _validate(merged, strict) or _floor_errors(base["stages"], merged["stages"])
    if errs or not strict or _is_empty(delta):
        return errs
    return _change_errors(delta.get("change"), merged)


def _is_empty(delta):
    """A delta that overlays nothing needs no change hypothesis."""
    return not delta["stages"] and not any(delta.get(name) for name in ID_MAPS)


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
