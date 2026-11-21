#!/usr/bin/env python3
"""List facts in a transcript that the summary lacks.

Checks numbers, proper-noun phrases and quoted strings. Exit 1 when any is
missing. Add each to the summary, or list it under `## Omitted` with a reason.
"""
import re, sys

STAMP = re.compile(r"^\[\d\d:\d\d:\d\d\]\s*", re.M)
NUM = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
CONTRACTION = re.compile(r"['’](?:s|m|d|ll|re|ve|t)$", re.I)
QUOTE = re.compile(r'"([^"\n]{3,})"')


def names(text):
    found = {}  # reported phrase -> phrase that must appear in the summary
    for line in text.splitlines():
        run, lead = [], False  # lead: run began at a sentence start, so one word proves nothing
        sentence_start = True
        for m in re.finditer(r"[A-Za-z][\w'’-]*|[.!?,;:]", line):
            w = CONTRACTION.sub("", m.group())
            if w in ".!?,;:":
                _flush(run, lead, found)
                run, lead, sentence_start = [], False, True
                continue
            if w[0].isupper() and len(w) > 1:
                if not run:
                    lead = sentence_start
                run.append(w)
            else:
                _flush(run, lead, found)
                run, lead = [], False
            sentence_start = False
        _flush(run, lead, found)
    return found


def _flush(run, lead, found):
    # A capital at a sentence start proves nothing, so a lead run is covered when its tail
    # is in the summary ("But Rich Dad" -> "Rich Dad"). A lone lead word is skipped.
    if run and not (lead and len(run) == 1):
        found.setdefault(" ".join(run), " ".join(run[1:] if lead else run))


def missing(transcript, summary):
    body = STAMP.sub("", transcript)
    low = summary.lower()
    norm = low.replace(",", "")
    out = {"numbers": [], "names": [], "quotes": []}
    for n in sorted(set(NUM.findall(body))):
        if not re.search(r"(?<![\d.])" + re.escape(n.replace(",", "")) + r"(?![\d])", norm):
            out["numbers"].append(n)
    for n, need in sorted(names(body).items()):
        if need.lower() not in low:
            out["names"].append(n)
    for q in sorted(set(QUOTE.findall(body))):
        if q.lower() not in low:
            out["quotes"].append(q)
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: check_coverage.py TRANSCRIPT SUMMARY")
    res = missing(*(open(p, encoding="utf-8").read() for p in sys.argv[1:]))
    total = sum(map(len, res.values()))
    for kind, items in res.items():
        for i in items:
            print(f"{kind}: {i}")
    print(f"missing: {total}")
    sys.exit(1 if total else 0)
