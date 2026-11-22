#!/usr/bin/env python3
"""Ingest samples of one person's messages into <state>/corpus.jsonl.

Formats: .txt/.md (messages split on a `---` line, else on blank lines), .jsonl/.ndjson/.json
(objects with `text` and optional channel, audience, ts, reply_to, context, author, id),
.eml/.mbox (text/plain body, quotes and signature removed), .vtt/.srt auto-captions (header, timing,
tags, [Music] cues and rolling duplicate lines removed; cues join into sentence-ish records). Text is
kept as written; only exact duplicates collapse, with a count.

  ingest.py --persona NAME [--author A] [--channel C] [--audience A] FILE...
"""

import argparse
import email
import email.policy
import html
import json
import mailbox
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import personalib as m  # noqa: E402

WROTE_RE = re.compile(r"^On .+wrote:\s*$")
CUE_TIME_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})")
CUE_NOISE_RE = re.compile(r"<[^>]*>|\[[^\]]*\]")
SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")
PAUSE_SECONDS = 2.0  # a gap between cues longer than this starts a new record


def clean(text):
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def split_blocks(text):
    lines = text.replace("\r\n", "\n").split("\n")
    if any(ln.strip() == "---" for ln in lines):
        blocks, cur = [], []
        for ln in lines:
            if ln.strip() == "---":
                blocks.append("\n".join(cur))
                cur = []
            else:
                cur.append(ln)
        blocks.append("\n".join(cur))
        return blocks
    return re.split(r"\n\s*\n", text)


def from_text(path, ext):
    text = path.read_text(encoding="utf-8")
    if ext == ".md" and text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    return [{"text": b} for b in split_blocks(text)]


def from_captions(path):
    sentences, buf, prev_end, last_line = [], "", None, None
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    for block in re.split(r"\n\s*\n", text):
        lines = block.split("\n")
        at = next((i for i, ln in enumerate(lines) if CUE_TIME_RE.search(ln)), None)
        if at is None:
            continue  # WEBVTT header, NOTE, STYLE, REGION
        g = [int(x or 0) for x in CUE_TIME_RE.search(lines[at]).groups()]
        start, end = (g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000, g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000)
        body = [" ".join(html.unescape(CUE_NOISE_RE.sub("", ln)).split()) for ln in lines[at + 1:]]
        body = [ln for ln in body if ln]
        if body and body[0] == last_line:
            body = body[1:]  # rolling caption: the cue repeats the previous cue's last line
        if body:
            last_line = body[-1]
            if prev_end is not None and start - prev_end > PAUSE_SECONDS and buf:
                sentences.append(buf)
                buf = ""
            *done, buf = SENTENCE_END_RE.split((buf + " " + " ".join(body)).strip())
            sentences.extend(done)
        prev_end = end
    if buf:
        sentences.append(buf)
    if not sentences:
        raise m.Fail(f"{path}: no caption text")
    return [{"text": s} for s in sentences]


def from_records(path, ext):
    if ext == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise m.Fail(f"{path}: bad JSON: {e}") from e
        if not isinstance(data, list):
            raise m.Fail(f"{path}: expected a JSON array of objects")
        rows = list(enumerate(data, 1))
    else:
        rows = []
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append((n, json.loads(line)))
            except ValueError as e:
                raise m.Fail(f"{path}:{n}: bad JSON line: {e}") from e
    out = []
    for n, r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("text"), str):
            raise m.Fail(f"{path}:{n}: each record needs a string `text`")
        out.append(r)
    by_id = {str(r["id"]): r["text"] for r in out if "id" in r}
    for r in out:
        rt = r.get("reply_to")
        if rt is not None and not r.get("context"):
            r["context"] = by_id.get(str(rt), str(rt))
    return out


def mail_body(msg):
    part = msg.get_body(preferencelist=("plain",))
    if part is None:
        return ""
    try:
        body = part.get_content()
    except (LookupError, ValueError):
        body = part.get_payload(decode=True).decode("utf-8", "replace")
    kept = []
    for ln in body.replace("\r\n", "\n").split("\n"):
        if ln in ("-- ", "--") or WROTE_RE.match(ln):
            break
        if not ln.lstrip().startswith(">"):
            kept.append(ln)
    return "\n".join(kept)


def from_mail(path, ext, author):
    def parse(f):
        return email.message_from_binary_file(f, policy=email.policy.default)

    if ext == ".eml":
        with open(path, "rb") as f:
            msgs = [parse(f)]
    else:
        msgs = list(mailbox.mbox(str(path), factory=parse, create=False))
    out = []
    for msg in msgs:
        if author and author.lower() not in str(msg.get("From", "")).lower():
            continue
        subj = str(msg.get("Subject", "") or "")
        out.append({"text": mail_body(msg), "channel": "email",
                    "context": f"subject: {subj}" if subj else "", "ts": str(msg.get("Date", "") or "")})
    return out


def load(path, author):
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        loader = from_text
    elif ext in (".vtt", ".srt"):
        return from_captions(require_file(path))
    elif ext in (".jsonl", ".ndjson", ".json"):
        loader = from_records
    elif ext in (".eml", ".mbox"):
        return from_mail(require_file(path), ext, author)
    else:
        raise m.Fail(f"{path}: unknown extension {ext!r} (txt, md, jsonl, ndjson, json, eml, mbox, vtt, srt)")
    rows = loader(require_file(path), ext)
    if author:
        rows = [r for r in rows if r.get("author") in (None, author)]
    return rows


def require_file(path):
    if not path.is_file():
        raise m.Fail(f"no such file: {path}")
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m.add_state_args(p)
    p.add_argument("--author", help="keep only records or mails by this author")
    p.add_argument("--channel", default="default", help="channel for records that name none")
    p.add_argument("--audience", default="default", help="audience for records that name none")
    p.add_argument("--exclude-pattern", action="append", default=[], metavar="REGEX",
                   help="drop messages matching this regex (repeatable), e.g. other speakers' lines")
    p.add_argument("files", nargs="+", type=Path)
    a = p.parse_args()
    try:
        excludes = [re.compile(x) for x in a.exclude_pattern]
    except re.error as e:
        raise m.Fail(f"bad --exclude-pattern: {e}") from e
    d = m.state_dir(a)
    m.guard(d, a.allow_git_worktree)
    raw = [(f, r) for f in a.files for r in load(f, a.author)]
    kept, index, empty, dups, excluded = [], {}, 0, 0, 0
    for f, r in raw:
        text = clean(r["text"])
        if not text:
            empty += 1
            continue
        if any(x.search(text) for x in excludes):
            excluded += 1
            continue
        key = " ".join(text.split())
        if key in index:
            index[key]["count"] += 1
            dups += 1
            continue
        rec = {"id": m.sha12(text), "text": text, "channel": str(r.get("channel") or a.channel),
               "audience": str(r.get("audience") or a.audience), "ts": str(r.get("ts") or ""),
               "context": str(r.get("context") or ""), "source": f.name, "words": m.words(text),
               "band": m.band(text), "count": 1}
        index[key] = rec
        kept.append(rec)
    m.make_dir(d)
    m.write_jsonl(d / "corpus.jsonl", kept)
    short = sum(1 for r in kept if r["band"] == "short")
    print(f"kept {len(kept)}, empty {empty}, excluded {excluded}, duplicates {dups}, short {short}, "
          f"long {len(kept) - short}"
          f" -> {d / 'corpus.jsonl'}")


if __name__ == "__main__":
    m.main_wrapper(main)
