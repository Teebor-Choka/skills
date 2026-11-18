#!/usr/bin/env python3
"""Synthesis pass over findings from several rounds or readers.

Input: a JSON list of findings {"id", "mechanism", "verdict", "count", "basis"} where
verdict is CONFIRMED, REFUTED or ROOT_CAUSE, count is how often the mechanism occurred,
and basis is "full" when count covers every occurrence (anything else is a sample).

Output: findings grouped by mechanism, with `conflict` set when one mechanism holds both a
CONFIRMED/ROOT_CAUSE and a REFUTED verdict; `ranked` (by count, most first), `refuted`, and
`unranked`: a root-cause claim made without a full count may not enter the ranking.

Usage: synthesize.py FINDINGS.json
"""
import json
import sys

POSITIVE = {"CONFIRMED", "ROOT_CAUSE"}


def synthesize(findings):
    groups = {}
    for f in findings:
        groups.setdefault(f.get("mechanism") or "?", []).append(f)
    out_groups = []
    for mechanism, items in sorted(groups.items()):
        verdicts = {f.get("verdict") for f in items}
        out_groups.append({"mechanism": mechanism, "findings": [f["id"] for f in items],
                           "verdicts": sorted(v for v in verdicts if v),
                           "conflict": "REFUTED" in verdicts and bool(verdicts & POSITIVE)})
    ranked, unranked, refuted = [], [], []
    for f in findings:
        if f.get("verdict") == "REFUTED":
            refuted.append(f)
        elif f.get("verdict") == "ROOT_CAUSE" and f.get("basis") != "full":
            unranked.append({"id": f["id"], "reason": "root-cause claim without a full count"})
        else:
            ranked.append(f)
    ranked.sort(key=lambda f: -(f.get("count") or 0))
    return {"groups": out_groups, "ranked": ranked, "unranked": unranked, "refuted": refuted}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[0]) as fh:
        json.dump(synthesize(json.load(fh)), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
