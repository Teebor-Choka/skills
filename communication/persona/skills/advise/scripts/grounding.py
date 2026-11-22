#!/usr/bin/env python3
"""Grounding line for a persona:advise answer. Read-only, stdlib only.

    grounding.py --map map.json NODE_ID [NODE_ID ...]

Prints one line naming the nodes used with (confidence, evidence count) and an overall level.
Exit 2 when an id is not in the map or the map cannot be read.
"""
import argparse
import json
import sys

LOW_CONF, HIGH_CONF, MIN_EVIDENCE = 0.4, 0.7, 2


def summarize(mp, ids):
    by_id = {n["id"]: n for n in mp.get("nodes", [])}
    ids = list(dict.fromkeys(ids))
    unknown = [i for i in ids if i not in by_id]
    used = [by_id[i] for i in ids if i in by_id]
    if not used:
        level = "none"
        line = "Grounding: no map node used, outside the map; simulation, not the person."
    else:
        mean = sum(n["confidence"] for n in used) / len(used)
        thin = min(len(n["evidence"]) for n in used) < MIN_EVIDENCE
        level = "low" if mean < LOW_CONF or thin else "high" if mean >= HIGH_CONF else "medium"
        names = ", ".join(f"{n['id']} ({n['confidence']:.2f}, {len(n['evidence'])})" for n in used)
        note = " (thin evidence)" if thin else ""
        line = f"Grounding: {names}; {level} confidence{note}."
    if unknown:
        line += f" Unknown ids, not in the map: {', '.join(unknown)}."
    return {"level": level, "line": line, "unknown": unknown}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--map", required=True)
    ap.add_argument("ids", nargs="*")
    a = ap.parse_args(argv)
    try:
        with open(a.map, encoding="utf-8") as f:
            mp = json.load(f)
    except (OSError, ValueError) as e:
        print(f"cannot read map: {e}", file=sys.stderr)
        return 2
    r = summarize(mp, a.ids)
    print(r["line"])
    return 2 if r["unknown"] else 0


if __name__ == "__main__":
    sys.exit(main())
