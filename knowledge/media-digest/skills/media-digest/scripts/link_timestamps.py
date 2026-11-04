#!/usr/bin/env python3
"""Turn `[hh:mm:ss]` and `[hh:mm:ss–hh:mm:ss]` in a summary into deep links to the source.

Usage: link_timestamps.py SUMMARY.md META.json   (rewrites SUMMARY.md in place)
Supported: YouTube, Vimeo. Other sources and articles are left unchanged. Safe to re-run.
"""
import json, re, sys

STAMP = re.compile(r"\[(\d\d):(\d\d):(\d\d)((?:[–-]\d\d:\d\d:\d\d)?)\](?!\()")


def link_for(meta, secs):
    kind, url = (meta.get("extractor") or "").lower(), meta.get("url") or ""
    if kind == "youtube":
        return f"{url}{'&' if '?' in url else '?'}t={secs}s"
    if kind == "vimeo":
        return f"{url.split('#')[0]}#t={secs}s"
    return None


def main(summary, meta_path):
    meta = json.load(open(meta_path, encoding="utf-8"))
    text = open(summary, encoding="utf-8").read()

    def sub(m):
        h, mi, s = int(m[1]), int(m[2]), int(m[3])
        target = link_for(meta, h * 3600 + mi * 60 + s)
        return m[0] if target is None else f"{m[0]}({target})"

    open(summary, "w", encoding="utf-8").write(STAMP.sub(sub, text))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: link_timestamps.py SUMMARY.md META.json")
    main(*sys.argv[1:])
