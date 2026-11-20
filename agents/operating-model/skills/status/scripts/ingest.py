#!/usr/bin/env python3
"""Build-state ingest: the append-only log clients report unit state into, and the projection of it. Stdlib only.

The log is site/ingest/events.jsonl (ORG_INGEST overrides the path). One JSON object per line:

  {"seq": 3, "prev": "<hash of line 2>", "at": 1795180000.1, "src": "http", "unit": "U20",
   "state": "building", "title": "...", "text": "...", "pr": 176, "branch": "...", "agent": "...",
   "wave": 7, "deps": ["U19"], "hash": "<sha256 of prev + the line without hash>"}

`at` and `src` are stamped by the writer (serve.py or emit.py's fallback), never taken from the client.
The chain is a hash chain without a key: it catches a hand edit, a torn write or a reordered line, not a
forger who rewrites the whole file. A broken chain is flagged; lines after the first break are ignored and
new appends are refused until someone moves the file aside. The file is never rewritten.

  python3 site/ingest.py verify [FILE]     check the chain, print the latest state per unit
"""
import calendar
import fcntl
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATES = ("queued", "building", "review", "ci", "merged", "done", "blocked", "failed", "needs-owner")
# view state of each unit state: one table the projection and every count read
VIEW = {"queued": "queued", "building": "active", "review": "active", "ci": "active", "merged": "done", "done": "done",
        "needs-owner": "gate", "blocked": "gate", "failed": "failed"}
UNIT_RE = re.compile(r"^[A-Z]{1,3}\d{1,4}[a-z]?$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")
MAX_BODY = 4096
FIELDS = {"unit", "state", "title", "text", "pr", "branch", "agent", "wave", "deps"}


def log_path():
    return Path(os.environ.get("ORG_INGEST") or HERE / "ingest" / "events.jsonl")


def _printable(s, n):
    return isinstance(s, str) and 0 < len(s) <= n and not any(ord(c) < 32 and c not in "\t" for c in s)


def validate(rec):
    """Return (clean record, None) or (None, reason). Unknown keys are refused."""
    if not isinstance(rec, dict):
        return None, "body must be a JSON object"
    extra = set(rec) - FIELDS
    if extra:
        return None, "unknown field: %s" % ", ".join(sorted(extra))
    out = {}
    u = rec.get("unit")
    if not isinstance(u, str) or not UNIT_RE.match(u):
        return None, "unit must look like U20, U13a or H1"
    out["unit"] = u
    if rec.get("state") not in STATES:
        return None, "state must be one of %s" % ", ".join(STATES)
    out["state"] = rec["state"]
    for k, n in (("title", 200), ("text", 1000), ("agent", 100)):
        if rec.get(k) is not None:
            if not _printable(rec[k], n):
                return None, "%s must be text of 1 to %d characters, no control characters" % (k, n)
            out[k] = rec[k]
    if rec.get("pr") is not None:
        if type(rec["pr"]) is not int or not 0 < rec["pr"] < 10 ** 7:
            return None, "pr must be a positive integer"
        out["pr"] = rec["pr"]
    if rec.get("branch") is not None:
        if not isinstance(rec["branch"], str) or not BRANCH_RE.match(rec["branch"]) or ".." in rec["branch"]:
            return None, "branch must be letters, digits and . _ / -"
        out["branch"] = rec["branch"]
    if rec.get("wave") is not None:
        if type(rec["wave"]) is not int or not 1 <= rec["wave"] <= 99:
            return None, "wave must be an integer from 1 to 99"
        out["wave"] = rec["wave"]
    if rec.get("deps") is not None:
        d = rec["deps"]
        if not isinstance(d, list) or len(d) > 30 or not all(isinstance(x, str) and UNIT_RE.match(x) for x in d) or u in d:
            return None, "deps must be a list of at most 30 unit ids, not the unit itself"
        out["deps"] = list(dict.fromkeys(d))
    return out, None


def _hash(prev, line):
    body = json.dumps({k: v for k, v in line.items() if k != "hash"}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev + "\n" + body).encode()).hexdigest()


def read(path=None):
    """Verify the chain. Returns {"events": [valid lines], "broken": None or text, "ignored": n, "seq": last valid seq}."""
    path = Path(path or log_path())
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {"events": [], "broken": None, "ignored": 0, "seq": 0, "head": ""}
    lines = raw.split(b"\n")
    torn = lines.pop()  # text after the last newline: a torn write
    evs, prev, seq, broken, ignored = [], "", 0, None, 0
    for i, b in enumerate(lines, 1):
        if broken:
            ignored += 1
            continue
        try:
            e = json.loads(b.decode("utf-8"))
            ok = isinstance(e, dict) and e.get("seq") == seq + 1 and e.get("prev") == prev and e.get("hash") == _hash(prev, e)
        except (ValueError, UnicodeDecodeError):
            e, ok = None, False
        if not ok:
            broken, ignored = "line %d does not continue the chain (edited, reordered or not JSON)" % i, 1
            continue
        evs.append(e)
        prev, seq = e["hash"], e["seq"]
    if torn.strip() and not broken:
        broken, ignored = "line %d is torn (no newline at the end)" % (len(lines) + 1), 1
    elif torn.strip():
        ignored += 1
    return {"events": evs, "broken": broken, "ignored": ignored, "seq": seq, "head": prev}


class ChainBroken(Exception):
    pass


def append(rec, src, path=None, now=None):
    """Validate, then append one line under an exclusive lock. Raises ValueError (bad record) or ChainBroken."""
    clean, err = validate(rec)
    if err:
        raise ValueError(err)
    path = Path(path or log_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        st = read(path)
        if st["broken"]:
            raise ChainBroken("ingest log %s: %s; move it aside to start a new log" % (path, st["broken"]))
        line = dict(clean, seq=st["seq"] + 1, prev=st["head"], at=round(now or time.time(), 3), src=src)
        line["hash"] = _hash(st["head"], line)
        os.write(fd, (json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n").encode())
        return line
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def latest(events):
    """Per unit: the state of the highest seq, each other field's newest non-empty value, and `about`, the first text."""
    out = {}
    for e in sorted(events, key=lambda e: e["seq"]):
        u = out.setdefault(e["unit"], {"unit": e["unit"]})
        if e.get("text") and "about" not in u:
            u["about"] = e["text"]  # the first text describes the unit; later texts are status notes
        for k in ("state", "title", "text", "pr", "branch", "agent", "wave", "deps", "at", "seq", "src"):
            if e.get(k) is not None:
                u[k] = e[k]
    return out


# ---------------------------------------------------------------- projection of the build view
def _ts(iso):
    try:
        return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")) if iso else None
    except (TypeError, ValueError):
        return None


def project_units(base, ing, merged_prs, open_prs, warn=lambda m: None):
    """Latest state per unit. Sources, oldest to newest by time: the static units (status-units.json, agent plans,
    run log; time 0), merged pull requests (at mergedAt), open pull requests (at updatedAt) and ingest (at its
    server time). The newest wins the state; ingest also sets title, text, pr, branch, wave and deps.
    base: units as gen.py builds them; ing: latest(); merged_prs: [{n, head, merged_at}]; open_prs: {n: {head, ci, draft, updated}}."""
    units = [dict(u) for u in base]
    by = {u["id"]: u for u in units}
    for uid, e in ing.items():
        if uid not in by:
            u = {"id": uid, "w": None, "name": e.get("title") or uid, "st": "queued", "note": "", "dep": [], "what": "", "tgt": "",
                 "acc": [], "src": "ingest", "branch": None, "pr": None, "pr_open": False, "findings": [], "followup": None, "items": []}
            units.append(u)
            by[uid] = u
    for u in units:
        u["state"], u["state_at"], u["state_src"] = {"done": "done", "active": "building", "gate": "needs-owner"}.get(u["st"], "queued"), 0, "plan"
        e = ing.get(u["id"])
        if e:
            for k, f in (("title", "name"), ("branch", "branch"), ("pr", "pr")):
                if e.get(k) is not None:
                    u[f] = e[k]
            if e.get("about"):
                u["what"] = u["what"] or e["about"]
            if e.get("deps") is not None:
                u["dep"] = list(e["deps"])
            if e.get("wave"):
                u["w"] = e["wave"]
            if e.get("agent"):
                u["agent"] = e["agent"]
        if not u["what"]:
            u["what"] = u["name"]
    head2merged = {p["head"]: p for p in merged_prs}
    n2merged = {p["n"]: p for p in merged_prs}
    head2open = {v["head"]: k for k, v in open_prs.items()}
    cands = {}
    for u in units:
        c = [(0, 0, u["state"], "plan", u.get("note") or u["state"])]
        m = n2merged.get(u.get("pr")) or head2merged.get(u.get("branch"))
        if m:
            u["pr"] = u.get("pr") or m["n"]
            c.append((_ts(m["merged_at"]) or 1, 1, "merged", "gh", "PR #%d merged" % m["n"]))
        on = u.get("pr") if u.get("pr") in open_prs else head2open.get(u.get("branch"))
        if on and not m:
            p = open_prs[on]
            u["pr"] = on
            st = "ci" if p.get("ci") in ("running", "failing") else "review"
            c.append((_ts(p.get("updated")) or 1, 1, st, "gh", "PR #%d open, checks %s" % (on, p.get("ci"))))
        e = ing.get(u["id"])
        if e:
            c.append((e["at"], 2, e["state"], "ingest", e.get("text") or ""))
        cands[u["id"]] = c
    for u in units:
        at, _, st, src, note = max(cands[u["id"]], key=lambda x: (x[0], x[1]))
        u.update(state=st, state_at=at, state_src=src, st=VIEW[st])
        if src != "plan":
            u["note"] = note
        u["pr_open"] = u.get("pr") in open_prs
        if st in ("merged", "done") and u["pr_open"]:
            u["conflict"] = "reported %s, but PR #%d is still open on GitHub" % (st, u["pr"])
    ids = set(by)
    for u in units:
        bad = [d for d in u["dep"] if d not in ids]
        if bad:
            warn("unit %s needs %s, which is no unit; dropped" % (u["id"], ", ".join(bad)))
            u["dep"] = [d for d in u["dep"] if d in ids]
    wave = {}

    def w_of(uid, seen=()):
        u = by[uid]
        if u.get("w"):
            return u["w"]
        if uid in wave:
            return wave[uid]
        wave[uid] = 1 + max([w_of(d, seen + (uid,)) for d in u["dep"] if d not in seen] or [0])
        return wave[uid]
    for u in units:
        u["w"] = w_of(u["id"])
    return units


def main(argv):
    if argv[:1] == ["verify"]:
        st = read(argv[1] if len(argv) > 1 else None)
        for uid, e in sorted(latest(st["events"]).items()):
            print("%-5s %-12s seq %-4d %s" % (uid, e["state"], e["seq"], e.get("title") or ""))
        print("%d events, chain %s" % (len(st["events"]), ("BROKEN: %s, %d lines ignored" % (st["broken"], st["ignored"])) if st["broken"] else "ok"))
        sys.exit(1 if st["broken"] else 0)
    sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
