#!/usr/bin/env python3
"""Convert a WebVTT/SRT file to `[hh:mm:ss] text` lines.

Auto-captions repeat each line across rolling cues; a line is dropped when the
previous cue already carried it.
"""
import html, re, sys

TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,]\d{3}\s*-->")
TAG = re.compile(r"<[^>]*>")


def parse(text):
    cues, start, lines = [], None, []
    for raw in text.splitlines() + [""]:
        m = TIME.search(raw)
        if m:
            h, mi, s = int(m.group(1) or 0), int(m.group(2)), int(m.group(3))
            start, lines = h * 3600 + mi * 60 + s, []
        elif start is not None and raw.strip():
            lines.append(" ".join(html.unescape(TAG.sub("", raw)).split()))
        elif start is not None and not raw.strip() and lines:
            cues.append((start, [l for l in lines if l]))
            start, lines = None, []
    return cues


def main(path):
    out, prev = [], []
    for start, lines in parse(open(path, encoding="utf-8", errors="replace").read()):
        for line in lines:
            if line not in prev:
                out.append(f"[{start // 3600:02d}:{start % 3600 // 60:02d}:{start % 60:02d}] {line}")
        prev = lines
    if not out:
        sys.exit(f"vtt2txt: no cue text in {path}")
    print("\n".join(out))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: vtt2txt.py FILE.vtt")
    main(sys.argv[1])
