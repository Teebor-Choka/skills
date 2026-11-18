#!/usr/bin/env python3
"""Audit the input side of sessions: what the agent was offered, and what it used.

Per transcript: the skill listing (skills with a description versus name only, total
characters, characters per source), the tools offered, the tools called, and the offered
tools never called. Across transcripts: per-skill rate (sessions that were offered the
skill, and sessions that invoked it). Sizes of always-on files (instructions, output
style) come from --always-on.

A "never called" finding is valid only for a tool or skill that was offered. When a
transcript records no offered-tool list, tools_offered and tools_never_called are null.
A low skill rate is not a wording problem until hook-forced loads are excluded.

Usage: context-audit.py PATH [PATH ...] [--always-on FILE ...]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works under python -I
import reflectlib as lib  # noqa: E402

LISTING_LINE_RE = re.compile(r"^- (\S+?)(?:: (.*))?$")


def parse_listing(content):
    """(skills, per-source chars) of a skill-listing text: one '- name: description' per line."""
    if isinstance(content, list):
        content = lib.text_of(content)
    if not isinstance(content, str):
        return [], {}, 0
    skills, by_source = [], {}
    for line in content.splitlines():
        m = LISTING_LINE_RE.match(line)
        if not m:
            continue
        name, desc = m.group(1), m.group(2)
        source = name.split(":", 1)[0] if ":" in name else "user"
        skills.append({"name": name, "described": bool(desc and desc.strip())})
        by_source[source] = by_source.get(source, 0) + len(line) + 1
    return skills, by_source, len(content)


def audit_session(path):
    offered_tools = None
    listing = None
    called, invoked = {}, {}
    for _, o in lib.iter_entries(path):
        typ = o.get("type")
        if typ == "system" and o.get("subtype") == "init" and isinstance(o.get("tools"), list):
            offered_tools = sorted({t if isinstance(t, str) else str(t.get("name"))
                                    for t in o["tools"] if isinstance(t, (str, dict))})
        elif typ == "attachment":
            att = o.get("attachment")
            if isinstance(att, dict) and att.get("type") == "skill_listing":
                listing = parse_listing(att.get("content"))
        elif typ == "assistant":
            content = lib.message_of(o).get("content")
            for b in content if isinstance(content, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    called[b.get("name")] = called.get(b.get("name"), 0) + 1
                    inp = b.get("input") or {}
                    if b.get("name") == "Skill" and isinstance(inp.get("skill"), str):
                        invoked[inp["skill"]] = invoked.get(inp["skill"], 0) + 1
    skills, by_source, chars = listing if listing else ([], {}, 0)
    return {
        "file": path,
        "sidechain": "/subagents/" in path.replace(os.sep, "/"),
        "skill_listing": {
            "described": sum(1 for s in skills if s["described"]),
            "name_only": sum(1 for s in skills if not s["described"]),
            "chars": chars, "by_source": by_source,
        },
        "skills_offered": [s["name"] for s in skills],
        "skills_invoked": invoked,
        "tools_offered": offered_tools,
        "tools_called": called,
        "tools_never_called": (sorted(t for t in offered_tools if t not in called)
                              if offered_tools is not None else None),
    }


def audit(paths, always_on=()):
    sessions = [audit_session(p) for p in lib.collect_files(paths)]
    rates = {}
    for s in sessions:
        for name in set(s["skills_offered"]):
            r = rates.setdefault(name, {"offered": 0, "invoked": 0})
            r["offered"] += 1
            r["invoked"] += 1 if name in s["skills_invoked"] else 0
    for r in rates.values():
        r["rate"] = round(r["invoked"] / r["offered"], 3)
    sized = []
    for path in always_on:
        try:
            with open(path, errors="replace") as fh:
                sized.append({"path": path, "chars": len(fh.read())})
        except OSError as e:
            print(f"skipped {path}: {e}", file=sys.stderr)
    return {"sessions": sessions, "skill_rates": dict(sorted(rates.items())), "always_on": sized}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--always-on", action="append", default=[], metavar="FILE")
    a = ap.parse_args(argv)
    json.dump(audit(a.paths, a.always_on), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
