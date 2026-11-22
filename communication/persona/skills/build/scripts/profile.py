#!/usr/bin/env python3
"""Write the profile skeleton from TRAIN, measure TRAIN for the analysis, or validate a profile.

  profile.py skeleton --persona NAME [--force]     -> <state>/profile.md (stats, examples, TODO)
  profile.py analyze --persona NAME                -> <state>/analysis-stats.md (all, per channel)
  profile.py validate --persona NAME [--profile P] [--fold F] -> exit 0 valid, 1 one error per line
"""

import argparse
import re
import statistics
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import personalib as m  # noqa: E402

GUIDE = {
    "Long messages": "How a long piece is built: opening, setup, structure, repetition, examples, close.",
    "Habits": "How they open and close, length, punctuation, casing, emoji, line breaks; state rates.",
    "Temperament": "Directness, hedging, humor, warmth; reaction to bad news, disagreement, praise, requests.",
    "Short messages": "What a yes, no, thanks, acknowledgement and question look like in 25 words or fewer.",
    "Channels and audiences": "Channel by audience: length, formality, emoji, greeting. Name every channel below.",
    "Lexicon": "Signature words and phrases with a rough rate; their word where others use a common one.",
    "Never": "What they never do: words, punctuation, structures, tones.",
    "Decisions and responses": "How they decide, commit, defer, say no, delegate; how fast and firmly.",
}


MODEL_GUIDE = {
    "Beliefs and values": "What they hold true and care about; what they argue for again and again.",
    "Framing": "How they frame a problem: the lens, the unit of analysis, the usual reframe.",
    "Reasoning moves": "Argument shapes they reach for: contrast, numbers, story, rule, analogy.",
    "Emotional range": "Range and default mood; reactions to bad news, disagreement, praise, requests.",
    "Stance": "Stance toward the audience and status: teacher, peer, challenger; how they address you.",
    "Compressed": "The same mind in 25 words or fewer: what survives, what is dropped.",
    "Expanded": "The same mind in long form: structure, repetition, setups, closings.",
}
HEDGES = ("maybe", "perhaps", "probably", "might", "possibly", "i think", "i guess", "kind of", "sort of",
          "i feel like", "not sure")
IMPERATIVE_STARTS = set("""do don't dont stop start get go make take try let write ask think read find keep focus
build sell use be never always quit pick look give put tell show learn work buy spend raise charge""".split())
PERSONS = {"I": "i me my mine myself i'm i've i'll i'd", "we": "we us our ours we're we've",
           "you": "you your yours you're you've yourself", "they": "they them their he she people"}
PAST = set("was were did had said went got made".split())
FUTURE = set("will won't gonna 'll".split())
STOP = set("""the a an and or but of to in on at for with is are be it that this as by from not no so if
then than there their they them you your i me my we our he she his her its was were been have has had do
does did will would can could should just about into out up down over more most very what which who
when where why how all any some one get got like don't it's i'm you're that's""".split())


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
    return "\n".join(lines + analysis_stats(train))


def analysis_stats(train):
    """Measures for the mental model: hedging, questions, imperatives, person, tense, rhythm, words."""
    n = max(len(train), 1)
    texts = [t["text"] for t in train]
    toks = [re.findall(r"[a-z']+", t.lower()) for t in texts]
    words = max(sum(len(x) for x in toks), 1)
    low = [" " + " ".join(x) + " " for x in toks]
    hedged = sum(1 for t in low if any(f" {h} " in t for h in HEDGES))
    sents = [s for t in texts for s in re.split(r"(?<=[.!?])\s+|\n+", t) if s.strip()]
    slen = [len(s.split()) for s in sents]
    per = {k: sum(1 for x in toks for w in x if w in v.split()) for k, v in PERSONS.items()}
    past = sum(1 for x in toks for w in x if w in PAST or (w.endswith("ed") and len(w) > 4))
    fut = sum(1 for x in toks for w in x if w in FUTURE) + sum(t.count(" going to ") for t in low)
    top = Counter(w for x in toks for w in x if w not in STOP and len(w) > 2).most_common(15)
    return [
        f"- hedging: {pct(hedged, n)} of messages hedge (maybe, probably, i think, ...)",
        f"- questions: {pct(sum(1 for t in texts if '?' in t), n)} of messages ask; "
        f"imperative opener in {pct(sum(1 for x in toks if x and x[0] in IMPERATIVE_STARTS), n)}",
        "- person per 100 words: " + ", ".join(f"{k} {100 * v / words:.1f}" for k, v in per.items()),
        f"- tense per 100 words: past {100 * past / words:.1f}, future {100 * fut / words:.1f}",
        f"- rhythm: {len(sents) / n:.1f} sentences per message, {statistics.mean(slen) if slen else 0:.1f} "
        f"words per sentence (sd {statistics.pstdev(slen) if slen else 0:.1f}), "
        f"{pct(sum(1 for x in slen if x <= 5), len(slen))} of sentences 5 words or fewer",
        "- top words: " + ", ".join(f"{w} ({c})" for w, c in top),
    ]


def examples(train):
    out = []
    for key in sorted({(t["band"], t["channel"]) for t in train}):
        rows = sorted((t for t in train if (t["band"], t["channel"]) == key), key=lambda t: t["id"])[:2]
        out += [f"- [train:{t['id']}] {t['text'].replace(chr(10), chr(92) + 'n')}" for t in rows]
    return "\n".join(out[:m.MAX_EXAMPLES])


def skeleton(d, persona, train, dev, test):
    parts = [f"# Voice profile: {persona}", "", f"split: {m.split_id(dev, test)}", "round: 0", "",
             "## Measured stats", "", stats(train), "",
             "## Mental model", "",
             "<!-- How this person thinks, from TRAIN and analysis.md: the generator writes from this. -->", ""]
    for s in m.MODEL_SUBSECTIONS:
        parts += [f"### {s}", "", f"<!-- {MODEL_GUIDE[s]} -->", "TODO", ""]
    for s in m.SECTIONS[2:-1]:
        parts += [f"## {s}", "", f"<!-- {GUIDE[s]} -->", "TODO", ""]
    parts += ["## Worked examples", "",
              "<!-- Candidates from TRAIN. Keep, drop or swap for TRAIN messages that show a habit above. -->",
              examples(train), ""]
    return "\n".join(parts)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["skeleton", "analyze", "validate"])
    p.add_argument("--fold", type=int, help="validate as for the revision round on this fold")
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
    if a.command == "analyze":
        m.guard(d, a.allow_git_worktree)
        _, train, _, _ = m.load_split(d)
        parts = ["# TRAIN measures", "", "## All channels", "", stats(train)]
        for ch in sorted({t["channel"] for t in train}):
            parts += ["", f"## Channel: {ch}", "", stats([t for t in train if t["channel"] == ch])]
        out = d / "analysis-stats.md"
        m.write_text(out, "\n".join(parts) + "\n")
        print(f"wrote {out}: TRAIN only; the analysis agent reads it with TRAIN to write analysis.md")
        return 0
    prof = a.profile or d / "profile.md"
    if not prof.is_file():
        raise m.Fail(f"no profile at {prof}: run profile.py skeleton first")
    errs = m.validate_profile(d, prof.read_text(encoding="utf-8"), a.fold)
    for e in errs:
        print(e)
    if not errs:
        print(f"{prof}: valid")
    return 1 if errs else 0


if __name__ == "__main__":
    m.main_wrapper(main)
