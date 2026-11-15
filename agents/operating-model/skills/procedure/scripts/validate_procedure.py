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
import functools
import os
import sys
from graphlib import CycleError, TopologicalSorter

# Same parser the policy skill uses, so both files accept one frontmatter subset.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "policy"))
from policy_loader import PolicyError, _parse_frontmatter, _split_frontmatter  # noqa: E402

__all__ = ("validate_text", "validate_layers", "parse_frontmatter", "parse_procedure", "main")

OWNER = "owner"  # the user: the reserved last rung of every ladder
LIST_KEYS = ("needs", "consumes", "produces", "review", "metrics")
BOOL_KEYS = ("disabled", "floor")
# A delta may not change these on a floor stage; `review` may only grow.
FLOOR_LOCKED = ("needs", "consumes", "produces", "skill", "entity")
# Id maps a delta overlays per id, like `stages`, and what protects each. `protected`: keys a delta
# cannot change on an existing id. `removable`: whether a delta may disable an id. `lower_only`:
# numeric keys a delta may lower but not raise. A new map is one entry here.
ID_MAPS = {
    "entities": {"protected": ("escalates-to",), "removable": True},
    "loops": {"protected": ("on-exhausted",), "removable": False, "lower_only": ("bound",)},
    "kpis": {"protected": ("owner",), "removable": False},
}
# The closed vocabulary of `when` and loop `exit` conditions: key -> (value type, the context set
# the value must belong to, or None). A runner evaluates these without a model.
PREDICATES = {"paths": (list, None), "kind": (str, "kinds"), "policy": (str, None)}


def parse_frontmatter(text, src="<text>"):
    """Parse a frontmatter document with the policy skill's subset. Returns (map, errors)."""
    try:
        return _parse_frontmatter(_split_frontmatter(text, src), src), []
    except PolicyError as exc:
        return None, [str(exc)]


def parse_procedure(text, src="<text>"):
    """Parse a procedure into its stages and id maps. Returns (procedure, errors)."""
    return _load(text, src)


def _load(text, src, required=True):
    """Parse a procedure and return (proc, errors). A delta may omit `stages`."""
    fm, errs = parse_frontmatter(text, src)
    if errs:
        return None, errs
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


def _names_entity(value, ents):
    """True when `value` names a defined entity or the owner."""
    return isinstance(value, str) and (value == OWNER or value in ents)


def _posint(value):
    """The value as a positive integer, or None."""
    return int(value) if isinstance(value, str) and value.isdecimal() and int(value) > 0 else None


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
        if not _names_entity(to, ents):
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
    ctx = {"kinds": kinds}
    names = ", ".join(sorted(PREDICATES))
    if not isinstance(pred, dict) or not pred:
        return [f"{where}: must be a map of predicates ({names})"]
    errs = []
    for key, val in pred.items():
        spec = PREDICATES.get(key)
        if spec is None:
            errs.append(f"{where}: unknown predicate '{key}' (allowed: {names})")
            continue
        want, scope = spec
        if not isinstance(val, want) or not val:
            errs.append(f"{where}: '{key}' must be a non-empty {want.__name__}")
        elif scope and val not in ctx[scope]:
            errs.append(f"{where}: {key} '{val}' is not known to the procedure")
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
        if _posint(bound) is None:
            errs.append(f"{where}: 'bound' must be a positive integer, the maximum rounds")
        if "exit" not in lp:
            errs.append(f"{where}: needs an 'exit' condition")
        else:
            errs += _predicate_errors(f"{where}: 'exit'", lp["exit"], kinds)
        to = lp.get("on-exhausted")
        if not _names_entity(to, ents or {}):
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
        if not _names_entity(owner, ents):
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
    """A change names why, what it should move, which way, and how long to watch."""
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
    reason = change.get("reason")
    if not isinstance(reason, str) or not reason:
        errs.append("change: 'reason' must say why, so the owner can judge the change")
    window = change.get("window")
    if not isinstance(window, str) or not window:
        errs.append("change: 'window' must name the observation window, such as '5 runs'")
    return errs


# The checks in the order they must run: each assumes the ones before it passed, since ancestors
# need resolved `needs`. Every rule takes the whole procedure. A new rule is one entry here.
# `strict_only` rules are the ones every real procedure meets and a structure test may skip.
RULES = (
    (lambda p: _shape_errors(p["stages"]), False),
    (lambda p: _when_errors(p["stages"]), False),
    (lambda p: _graph_errors(p["stages"]), False),
    (lambda p: _retry_errors(p["stages"]), False),
    (lambda p: _kind_errors(p["stages"]), False),
    (_entity_errors, False),
    (_loop_errors, False),
    (_metric_errors, True),
)


def _validate(proc, strict=True):
    for rule, strict_only in RULES:
        errs = rule(proc) if strict or not strict_only else []
        if errs:
            return errs
    return []


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
    old = base_stage.get("review") or []
    kept = over.get("review", old)
    if not isinstance(kept, list) or not set(old) <= set(kept):
        errs.append(f"stage '{sid}' is floor: a delta cannot remove review angles")
    return errs


def _merge_stages(base_stages, delta_stages):
    """Per stage id, a delta's keys replace the base's; `disabled: true` removes the stage.

    Returns (merged, structural errors, protected errors). A protected error is a change only
    the owner may approve; a structural error is a mistake no approval fixes."""
    merged = {k: dict(v) for k, v in base_stages.items()}
    errs, protected = [], []
    for sid, over in delta_stages.items():
        is_floor = merged.get(sid, {}).get("floor") is True
        if over.get("disabled") is True:
            if sid not in merged:
                errs.append(f"delta disables unknown stage '{sid}'")
            elif is_floor:
                protected.append(f"stage '{sid}' is floor and cannot be disabled")
            else:
                gates = [f for f in _ancestors(base_stages, sid) if base_stages[f].get("floor") is True]
                if gates:
                    protected.append(
                        f"stage '{sid}' waits on floor stage '{gates[0]}' and cannot be removed"
                    )
            merged.pop(sid, None)
            continue
        if is_floor:
            protected += _floor_delta_errors(sid, merged[sid], over)
        merged.setdefault(sid, {}).update(over)
    return merged, errs, protected


def _raises(new, old):
    """True when both are positive integers and `new` is larger."""
    n, o = _posint(new), _posint(old)
    return n is not None and o is not None and n > o


def _merge_map(name, base_map, delta_map):
    """Overlay an id map per id; `disabled: true` removes the id.

    What a delta may not do comes from the map's registry entry: change a protected key, remove an
    id the map keeps, or raise a key that may only fall. Changing those needs the owner."""
    spec = ID_MAPS[name]
    merged = {k: dict(v) for k, v in base_map.items()}
    errs = []
    for key, over in delta_map.items():
        old = merged.get(key)
        if over.get("disabled") is True:
            if old is not None and not spec["removable"]:
                errs.append(f"{name}.{key} is protected: a delta cannot remove it")
            else:
                merged.pop(key, None)
            continue
        if old is not None:
            for k in spec["protected"]:
                if k in over and over[k] != old.get(k):
                    errs.append(f"{name}.{key}: '{k}' is protected; changing it needs the owner")
            for k in spec.get("lower_only", ()):
                if k in over and _raises(over[k], old.get(k)):
                    errs.append(f"{name}.{key}: a delta cannot raise '{k}'")
        merged.setdefault(key, {}).update(over)
    return merged, errs


def _merge(base, delta):
    """Overlay a delta procedure on a base. Returns (merged, structural errors, protected errors)."""
    stages, errs, protected = _merge_stages(base["stages"], delta["stages"])
    merged = {"stages": stages}
    for name in ID_MAPS:
        if name in base or name in delta:
            merged[name], more = _merge_map(name, base.get(name, {}), delta.get(name, {}))
            protected += more
    return merged, errs, protected


def _floor_errors(base, merged):
    """A floor stage keeps everything that waited on it, and nothing upstream is conditional."""
    anc_base = {s: _ancestors(base, s) for s in base}
    anc_merged = {s: _ancestors(merged, s) for s in merged}
    errs = []
    for fid, bst in base.items():
        if bst.get("floor") is not True or fid not in merged:
            continue
        if any("when" in merged[a] for a in anc_merged[fid]):
            errs.append(f"stage '{fid}' is floor: no upstream stage may carry 'when'")
        for sid in base:
            if sid in merged and fid in anc_base[sid] and fid not in anc_merged[sid]:
                errs.append(f"stage '{sid}' no longer runs after floor stage '{fid}'")
    return errs


@functools.lru_cache(maxsize=8)
def _checked_base(base_text, strict):
    """Parse and validate a baseline once: a swarm overlays many proposals on one baseline.

    The result is shared across calls, so a caller must not mutate it."""
    base, errs = _load(base_text, "<base>")
    if errs:
        return base, errs
    return base, [f"<base>: {e}" for e in _validate(base, strict)]


def validate_layers(base_text, delta_text, src="<delta>", strict=True, ratified=False):
    """Overlay a delta on a baseline, then validate the merged procedure.

    A protected change (a floor stage, the ladder, loop escalation, a KPI) is rejected unless
    `ratified` is true. Only a caller holding the owner's approval may pass it: the CLI has no
    such flag. Ratification never excuses a structural error or a missing change hypothesis."""
    base, errs = _checked_base(base_text, strict)
    delta, errs2 = _load(delta_text, src, required=False)
    if errs or errs2:
        return errs + errs2
    merged, errs, protected = _merge(base, delta)
    if errs:
        return errs
    if protected and not ratified:
        return protected
    errs = _validate(merged, strict)
    if not errs and not ratified:
        errs = _floor_errors(base["stages"], merged["stages"])
    empty = not delta["stages"] and not any(delta.get(name) for name in ID_MAPS)
    if errs or not strict or empty:
        return errs
    return _change_errors(delta.get("change"), merged)



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
