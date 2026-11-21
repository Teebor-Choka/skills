#!/usr/bin/env python3
"""Write the profile skeleton from TRAIN, or validate a filled profile.

  profile.py skeleton --persona NAME [--force]     -> <state>/profile.md (stats, examples, TODO)
  profile.py validate --persona NAME [--profile P] -> exit 0 valid, 1 with one error per line
"""

import argparse
import re
import statistics
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mimiclib as m  # noqa: E402

GUIDE = {
    "Habits": "How they open and close, length, punctuation, casing, emoji, line breaks; state rates.",
    "Temperament": "Directness, hedging, humor, warmth; reaction to bad news, disagreement, praise, requests.",
    "Short messages": "What a yes, no, thanks, acknowledgement and question look like in 25 words or fewer.",
    "Channels and audiences": "Channel by audience: length, formality, emoji, greeting. Name every channel below.",
    "Lexicon": "Signature words and phrases with a rough rate; their word where others use a common one.",
    "Never": "What they never do: words, punctuation, structures, tones.",
    "Decisions and responses": "How they decide, commit, defer, say no, delegate; how fast and firmly.",
}


def is_emoji(ch):
    o = ord(ch)
    return unicodedata.category(ch) == "So" or 0x1F300 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF


def first_last(text):
    toks = [t for t in re.split(r"\s+", text.strip()) if t]
    clean = [re.sub(r"^\W+|\W+$", "", t).lower() for t in toks]
    clean = [t for t in clean if t]
    return (clean[0], clean[-1]) if clean else ("", "")


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "n/a"


def stats(train):
    n = len(train)
    lines = [f"Measured on {n} TRAIN messages (distinct; exact repeats counted in `count`)."]
    for b in ("short", "long"):
        rows = [t for t in train if t["band"] == b]
        if rows:
            w = sorted(t["words"] for t in rows)
            lines.append(f"- {b}: {len(rows)} messages, median {statistics.median(w):g} words, max {w[-1]}")
        else:
            lines.append(f"- {b}: 0 messages")
    lines.append("- per channel / audience:")
    groups = Counter((t["channel"], t["audience"]) for t in train)
    for (ch, au), c in sorted(groups.items()):
        w = sorted(t["words"] for t in train if (t["channel"], t["audience"]) == (ch, au))
        lines.append(f"  - {ch} / {au}: {c} messages, median {statistics.median(w):g} words")
    texts = [t["text"] for t in train]
    starts_lower = sum(1 for t in texts if t[:1].isalpha() and t[:1].islower())
    caps = sum(1 for t in texts if re.search(r"\b[A-Z]{2,}\b", t))
    lines += [
        f"- casing: {pct(starts_lower, n)} start lowercase; {pct(caps, n)} have an all-caps word",
        f"- ending: {pct(sum(1 for t in texts if t.rstrip().endswith('.')), n)} end with a period, "
        f"{pct(sum(1 for t in texts if t.rstrip().endswith('?')), n)} with ?, "
        f"{pct(sum(1 for t in texts if t.rstrip().endswith('!')), n)} with !",
        f"- marks per message: ! {sum(t.count('!') for t in texts) / max(n, 1):.2f}, "
        f"? {sum(t.count('?') for t in texts) / max(n, 1):.2f}, "
        f"ellipsis {sum(t.count('...') + t.count('…') for t in texts) / max(n, 1):.2f}, "
        f"dash {sum(t.count('—') + t.count('–') + t.count(' - ') for t in texts) / max(n, 1):.2f}",
        f"- emoji: in {pct(sum(1 for t in texts if any(is_emoji(c) for c in t)), n)} of messages",
        f"- line breaks: in {pct(sum(1 for t in texts if chr(10) in t), n)} of messages",
    ]
    fl = [first_last(t) for t in texts]
    lines.append("- top openers: " + ", ".join(f"{w} ({c})" for w, c in Counter(f for f, _ in fl if f).most_common(8)))
    lines.append("- top closers: " + ", ".join(f"{w} ({c})" for w, c in Counter(x for _, x in fl if x).most_common(8)))
    phrases = Counter()
    for t in texts:
        toks = m.canonical(t).split()
        phrases.update({" ".join(toks[i:i + k]) for k in (2, 3) for i in range(len(toks) - k + 1)})
    rep = sorted(((p, c) for p, c in phrases.items() if c >= 3), key=lambda pc: (-pc[1], pc[0]))[:10]
    lines.append("- repeated phrases (3+ messages): " + (", ".join(f"{p} ({c})" for p, c in rep) or "none"))
    return "\n".join(lines)


def examples(train):
    out = []
    for key in sorted({(t["band"], t["channel"]) for t in train}):
        rows = sorted((t for t in train if (t["band"], t["channel"]) == key), key=lambda t: t["id"])[:2]
        out += [f"- [train:{t['id']}] {t['text'].replace(chr(10), chr(92) + 'n')}" for t in rows]
    return "\n".join(out)


def skeleton(d, persona, train, dev, test):
    parts = [f"# Voice profile: {persona}", "", f"split: {m.split_id(dev, test)}", "round: 0", "",
             "## Measured stats", "", stats(train), ""]
    for s in m.SECTIONS[1:-1]:
        parts += [f"## {s}", "", f"<!-- {GUIDE[s]} -->", "TODO", ""]
    parts += ["## Worked examples", "",
              "<!-- Candidates from TRAIN. Keep, drop or swap for TRAIN messages that show a habit above. -->",
              examples(train), ""]
    return "\n".join(parts)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["skeleton", "validate"])
    m.add_state_args(p)
    p.add_argument("--profile", type=Path, help="profile to validate (default <state>/profile.md)")
    p.add_argument("--force", action="store_true", help="overwrite an existing profile")
    a = p.parse_args()
    d = m.state_dir(a)
    if a.command == "skeleton":
        m.guard(d, a.allow_git_worktree)
        manifest, train, dev, test = m.load_split(d)
        out = d / "profile.md"
        if out.exists() and not a.force:
            raise m.Fail(f"{out} exists; pass --force to overwrite it")
        m.write_text(out, skeleton(d, a.persona or d.name, train, dev, test))
        print(f"wrote {out}: fill every TODO from TRAIN only, then run profile.py validate")
        return 0
    prof = a.profile or d / "profile.md"
    if not prof.is_file():
        raise m.Fail(f"no profile at {prof}: run profile.py skeleton first")
    errs = m.validate_profile(d, prof.read_text(encoding="utf-8"))
    for e in errs:
        print(e)
    if not errs:
        print(f"{prof}: valid")
    return 1 if errs else 0


if __name__ == "__main__":
    m.main_wrapper(main)
