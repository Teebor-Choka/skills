#!/usr/bin/env python3
"""Verify the presentation:patterns reference files against the plugin's own registry.

The registry (scripts/registry.mjs, REGISTRY) is the single list of the catalogued patterns (P) and
antipatterns (AP), each with the reference file that holds its entry. This script checks that every
reference file contains exactly the registry's entries for it, correctly typed. Run:

    python3 scripts/verify.py

Exit 0 and prints PASS on success; exit 1 and lists discrepancies otherwise.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "references")
REGISTRY = os.path.join(HERE, "registry.mjs")

_OBJECT = re.compile(r"\{([^{}]*)\}")
_FIELD = re.compile(r'(\w+):\s*"((?:[^"\\]|\\.)*)"')


def load_manifest(path=REGISTRY):
    """{file: {name: type}} from the REGISTRY array of registry.mjs. Its rows are flat objects."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index("export const REGISTRY = [")
    body = text[start:text.index("];", start)]
    manifest = {}
    for obj in _OBJECT.finditer(body):
        fields = dict(_FIELD.findall(obj.group(1)))
        if {"name", "type", "file"} <= fields.keys():
            manifest.setdefault(fields["file"], {})[fields["name"]] = fields["type"]
    return manifest


ENTRY = re.compile(r"^\*\*(.+?)\*\*\s*\((P|AP)\)", re.MULTILINE)


def parse(path):
    with open(path, encoding="utf-8") as fh:
        return {m.group(1).strip(): m.group(2) for m in ENTRY.finditer(fh.read())}


def main():
    MANIFEST = load_manifest()
    if not MANIFEST:
        print(f"FAIL: no entries parsed from {REGISTRY}")
        sys.exit(1)
    missing, extra, misclassified, misplaced = [], [], [], []
    total = p = ap = 0
    all_expected = {n: (f, t) for f, items in MANIFEST.items() for n, t in items.items()}

    for fname, expected in MANIFEST.items():
        path = os.path.join(REF, fname)
        if not os.path.exists(path):
            missing += [f"{fname}: FILE MISSING" ]
            continue
        found = parse(path)
        for name, typ in expected.items():
            if name not in found:
                missing.append(f"{fname}: {name} ({typ})")
            elif found[name] != typ:
                misclassified.append(f"{fname}: {name} is ({found[name]}), expected ({typ})")
        for name, typ in found.items():
            total += 1
            p += typ == "P"
            ap += typ == "AP"
            if name not in expected:
                where = all_expected.get(name)
                if where:
                    misplaced.append(f"{fname}: {name} belongs in {where[0]}")
                else:
                    extra.append(f"{fname}: {name} ({typ}) not in the registry")

    ok = not (missing or extra or misclassified or misplaced)
    exp_total = sum(len(v) for v in MANIFEST.values())
    for label, rows in (("MISSING", missing), ("EXTRA", extra),
                        ("MISCLASSIFIED", misclassified), ("MISPLACED", misplaced)):
        for r in rows:
            print(f"  [{label}] {r}")
    verdict = "PASS" if ok and total == exp_total else "FAIL"
    print(f"{verdict}: {total}/{exp_total} items, {p} P / {ap} AP, "
          f"{len(missing)} missing, {len(extra)} extra, "
          f"{len(misclassified)} misclassified, {len(misplaced)} misplaced")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
