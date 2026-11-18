#!/usr/bin/env python3
"""Drill into transcripts: matches of a regex, ranked across all files, scrubbed.

Files with the most matches come first, then by line. --agent ID keeps only the transcript
of that subagent (agent-ID.jsonl). Each hit has the file, line, timestamp and a scrubbed
excerpt; open the line with Read for the full entry.

Usage: drill.py PATH [PATH ...] --pattern REGEX [--agent ID] [--limit N]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works under python -I
import reflectlib as lib  # noqa: E402


def entry_text(entry):
    """Searchable text of an entry: message text plus tool-call inputs."""
    parts = [lib.text_of(lib.message_of(entry).get("content"))]
    content = lib.message_of(entry).get("content")
    for b in content if isinstance(content, list) else []:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            parts.append(json.dumps(b.get("input", {}), ensure_ascii=False))
    return " ".join(p for p in parts if p)


def drill(paths, pattern, agent=None, limit=20):
    rx = re.compile(pattern, re.I)
    per_file = []
    for path in lib.collect_files(paths):
        if agent and os.path.basename(path) != f"agent-{agent}.jsonl":
            continue
        hits = []
        for ln, o in lib.iter_entries(path):
            text = entry_text(o)
            m = rx.search(text)
            if m:
                lo = max(0, m.start() - 60)
                t = lib.parse_ts(o.get("timestamp"))
                hits.append({"file": path, "line": ln, "ts": lib.iso(t) if t else None,
                             "excerpt": re.sub(r"\s+", " ", lib.scrub(text[lo:lo + 200])).strip()})
        for h in hits:
            h["file_matches"] = len(hits)
        per_file.append(hits)
    per_file.sort(key=lambda hits: (-len(hits), hits[0]["file"] if hits else ""))
    return [h for hits in per_file for h in hits][:limit]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--agent")
    ap.add_argument("--limit", type=int, default=20)
    a = ap.parse_args(argv)
    json.dump(drill(a.paths, a.pattern, a.agent, a.limit), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
