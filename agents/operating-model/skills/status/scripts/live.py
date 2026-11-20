#!/usr/bin/env python3
"""Live view of the org runtime: tail run ledgers and dispatcher state, turn entries into run state.

Standard library only (PyYAML, when importable, lets rungs of an org-root change be classified).
Sources come from the --state-dir and --ledger options (see config.py): `state_dirs` (org.py state
directories, holding dispatcher.json and ledgers/*.ledger) and `ledgers` (globs of single ledger files).

The ledger MAC is not verified here: the ledger key is the runtime's own secret (mode 0600) and this
viewer never reads it. The seq/prev chain is checked, and a break is reported on the run.

  python3 scripts/live.py snapshot [source options]   print the current snapshot as JSON
  python3 scripts/live.py replay SRC DST [--rate N]
                                             copy a finished ledger into DST entry by entry, with
                                             its own pacing divided by N, to exercise the live view
"""
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

KEEP_EVENTS = 300
GIT_EVERY = 2.0
# git never runs a command the inspected repo configures, and never takes an optional lock in an agent's worktree
GIT = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "--no-optional-locks"]
CLASSIFY_FILES = 2000  # a worktree with more tracked or present files is not classified
CLASSIFY_BYTES = 1 << 20  # files above this size are compared as absent
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def under(path, roots):
    """True when the real path of `path` is inside one of `roots`."""
    rp = os.path.realpath(path)
    return any(rp == r or rp.startswith(r.rstrip("/") + "/") for r in (os.path.realpath(x) for x in roots))


def org_metric(e):
    """The org.metric record a ledger entry carries, or None. The collectors agent is not merged yet, so this is the
    one place that knows the shape. Assumed: {type: 'org.metric', metric, value, reason?}, found as the entry body,
    as the event of a fed entry (body.event), or as the body of an entry of kind 'org.metric'. Adjust here only."""
    b = e.get("body") if isinstance(e.get("body"), dict) else {}
    for r in (b, b.get("event") if isinstance(b.get("event"), dict) else None):
        if r and (r.get("type") == "org.metric" or e.get("kind") == "org.metric") and isinstance(r.get("metric"), str) and "value" in r:
            return {"metric": r["metric"], "value": r["value"], "reason": r.get("reason")}
    return None


def num(x):
    """A number from a ledger field, 0.0 when it is not one."""
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def run_id_of(path):
    return "r" + hashlib.sha1(str(path).encode()).hexdigest()[:10]


def fmt_usd(x):
    return "%.2f USD" % x if x >= 0.01 or x == 0 else "%.4f USD" % x


class Run:
    """State of one ledger, built entry by entry."""

    def __init__(self, path, org_root=None, worktree_roots=()):
        self.path = str(path)
        self.org_root = org_root
        self.worktree_roots = list(worktree_roots)
        self.id = run_id_of(path)
        self.reset()

    def reset(self):
        self.offset, self.buf, self.last_mac, self.last_seq = 0, b"", None, 0
        self.run_id = self.workflow = self.title = None
        self.status, self.end_status = "starting", None
        self.start_wall = self.last_wall = None
        self.t_last = 0.0
        self.cost, self.calls, self.seconds, self.judge_calls = 0.0, 0, 0.0, 0
        self._journal_key, self._journal = None, None
        self.tasks, self.prefixes = {}, {"": None}
        self.change = None
        self.events, self.problems = [], []
        self.escalations, self.emits = [], []
        self.metrics = {}
        self.pair = None
        self._git_at, self._git_key = 0.0, None

    # ---------------------------------------------------------------- reading
    def poll(self, now=None):
        """Read appended lines. Returns the new normalized events."""
        now = now or time.time()
        try:
            st = os.stat(self.path)
        except OSError:
            return []
        if st.st_size < self.offset:  # cut back or replaced: start again
            self.reset()
        if st.st_size == self.offset:
            self.refresh_change(now)
            return []
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read()
        self.offset += len(data)
        data = self.buf + data
        lines = data.split(b"\n")
        self.buf = lines.pop()  # a torn or unfinished last line waits for the rest
        first = self.start_wall is None
        out = []
        entries = []
        for line in lines:
            if not line.strip():
                continue
            try:
                e = json.loads(line.decode("utf-8"))
            except (ValueError, UnicodeDecodeError, RecursionError):
                e = None
            if isinstance(e, dict):
                entries.append(e)
            else:
                self.problems.append("line after entry %d is not a JSON object" % self.last_seq)
        if first and entries:
            # wall clock of entry t: the file's mtime belongs to the newest entry read
            ts = [num((e.get("body") or {}).get("t")) for e in entries if isinstance(e.get("body"), dict)]
            self.start_wall = st.st_mtime - max(ts or [0.0])
        for e in entries:
            try:
                ev = self.apply(e, now if not first else None)
            except (TypeError, ValueError, AttributeError, KeyError) as err:  # a hostile or broken entry is a problem, not a crash
                self.problems.append("entry %s unreadable: %s" % (e.get("seq"), str(err)[:120]))
                del self.problems[:-50]
                continue
            if ev:
                out.append(ev)
        self.last_wall = st.st_mtime if first else now
        self.refresh_change(now)
        return out

    def wall(self, t):
        return (self.start_wall or 0) + float(t or 0)

    # ---------------------------------------------------------------- state machine
    def task(self, key):
        if key not in self.tasks:
            wf, rel = self.split(key)
            self.tasks[key] = {"key": key, "wf": wf, "rel": rel, "state": "queued", "starts": 0, "t_start": None,
                               "t_end": None, "accept": None, "checks": {}, "judges": {}, "usd": 0.0, "command": None}
        return self.tasks[key]

    def split(self, key):
        best = ""
        for p in self.prefixes:
            if p and key.startswith(p) and len(p) > len(best):
                best = p
        return self.prefixes.get(best) or self.workflow, key[len(best):]

    def apply(self, e, seen_wall):
        if not isinstance(e, dict) or not all(k in e for k in ("seq", "prev", "kind", "body")):
            self.problems.append("entry after %d lacks seq, prev, kind or body" % self.last_seq)
            return None
        if e["seq"] != self.last_seq + 1 or (self.last_mac is not None and e["prev"] != self.last_mac):
            self.problems.append("chain break at entry %s" % e["seq"])
        self.last_seq, self.last_mac = e["seq"], e.get("mac")
        kind, b = e["kind"], e["body"] if isinstance(e["body"], dict) else {}
        ev = {"run": self.id, "seq": e["seq"], "kind": kind, "t": None, "text": None, "token": None}
        m = org_metric(e)
        if m:  # latest value per metric; time from the entry's t when it has one, else when it was read
            t = b.get("t")
            m.update(at=self.wall(t) if t is not None and self.start_wall else (seen_wall or time.time()), seq=e["seq"], run=self.id)
            self.metrics[m["metric"]] = m
            ev.update(kind="org.metric", text="metric %s is %s%s" % (m["metric"], m["value"], (", " + str(m["reason"])) if m.get("reason") else ""))
            self.events.append({x: ev[x] for x in ("seq", "kind", "key", "t", "text") if x in ev})
            return ev
        if kind == "header":
            rid, wf = b.get("run_id"), b.get("workflow")
            self.run_id = rid if isinstance(rid, str) else None
            self.workflow = wf if isinstance(wf, str) else None
            self.prefixes[""] = self.workflow
            unit = ((b.get("input") or {}).get("unit") or {}) if isinstance(b.get("input"), dict) else {}
            ev_in = (b.get("input") or {}).get("event") if isinstance(b.get("input"), dict) else None
            self.title = unit.get("title") or (ev_in or {}).get("type") if isinstance(unit, dict) else None
            ev.update(text="run %s of %s opened" % ((self.run_id or "?")[:8], self.workflow), token={"type": "trigger", "wf": self.workflow})
            self.status = "running"
            return ev
        if kind == "host":
            call, key, res = b.get("call"), b.get("key") or "", b.get("result")
            if call == "step" and isinstance(res, dict):
                cost = ((res.get("output") or {}).get("cost") or {}) if isinstance(res.get("output"), dict) else {}
                usd = float(cost.get("usd") or 0)
                self.cost += usd
                self.calls += 1
                self.seconds += float(res.get("duration") or 0)
                t = self.task(key)
                t["usd"] += usd
                ev.update(key=key, text="%s returned, exit %s, %s" % (key, res.get("exit_code"), fmt_usd(usd)))
            elif call == "check":
                name, _, tkey = key.partition("\n")
                self.task(tkey)["checks"][name] = res
                t = self.task(tkey)
                ev.update(key=tkey, text="check %s on %s: %s" % (name, tkey, "pass" if res is True else "fail" if res is False else res),
                          token={"type": "check", "key": tkey, "wf": t["wf"], "rel": t["rel"], "ok": res is True})
            elif call == "judge":
                self.judge_calls += 1
                tkey, _, item = key.partition("\n")
                verdict = (((res or {}).get("data") or {}).get("verdict")) if isinstance(res, dict) else None
                self.task(tkey)["judges"][item] = verdict or "no verdict"
                t = self.task(tkey)
                ev.update(key=tkey, text="judge on %s item %s: %s" % (tkey, item, verdict or "no verdict"),
                          token={"type": "judge", "key": tkey, "wf": t["wf"], "rel": t["rel"], "ok": verdict == "pass"})
            elif call == "change" and isinstance(res, dict):
                wt = res.get("worktree")
                if not self.change or self.change.get("worktree") != wt or self.change.get("head") != res.get("head"):
                    self.change = {"worktree": wt, "head": res.get("head"), "files": None, "rungs": None, "note": None}
                    self._git_key = None
                return None  # asked before every check: not worth an event
            else:
                ev.update(text="host call %s" % call)
            return ev
        if kind == "metric":
            ev.update(key=b.get("key"), text="metric %s on %s: %s" % (b.get("metric"), b.get("key"), b.get("value", b.get("error"))))
            return ev
        if kind == "feed":
            ty = ((b.get("event") or {}).get("type")) if isinstance(b.get("event"), dict) else None
            ev.update(text="event %s fed to the run" % ty, token={"type": "feed", "event": ty})
            return ev
        if kind == "decision-id":
            ev.update(key=b.get("key"), text="decision accepted at %s" % b.get("key"), token={"type": "gate", "key": b.get("key")})
            return ev
        if kind != "log":
            ev.update(text="ledger entry %s" % kind)
            return ev
        # interpreter events
        k, key, t = b.get("kind"), b.get("key"), b.get("t")
        self.t_last = max(self.t_last, float(t or 0))
        ev.update(kind=k, key=key, t=t, wall=self.wall(t))
        if k == "run-start":
            self.status = "running"
            ev["text"] = "run started: %s" % b.get("workflow")
        elif k == "workflow-start":
            pre = b.get("prefix") or ""
            self.prefixes[pre] = b.get("workflow")
            ev["text"] = "workflow %s started%s" % (b.get("workflow"), (" under " + pre.rstrip("/")) if pre else "")
            if pre:
                ev["token"] = {"type": "call", "wf": b.get("workflow"), "key": pre.rstrip("/")}
        elif k == "task-start":
            tk = self.task(key)
            tk["starts"] += 1
            rework = tk["starts"] > 1 and tk["state"] in ("done", "failed", "skipped")
            tk.update(state="running", t_start=t, t_end=None, accept=None)
            ev["text"] = "%s started%s" % (key, " again (round %d)" % tk["starts"] if tk["starts"] > 1 else "")
            ev["token"] = {"type": "rework" if rework else "start", "key": key, "wf": tk["wf"], "rel": tk["rel"]}
        elif k == "task-end":
            tk = self.task(key)
            tk.update(state="failed" if tk["accept"] not in (None, "pass") else "done", t_end=t)
            ev["text"] = "%s ended%s" % (key, "" if tk["state"] == "done" else ", acceptance " + str(tk["accept"]))
            ev["token"] = {"type": "end", "key": key, "wf": tk["wf"], "rel": tk["rel"]}
        elif k == "task-skip":
            tk = self.task(key)
            tk.update(state="skipped", t_end=t, accept=None)
            ev["text"] = "%s skipped" % key
            ev["token"] = {"type": "skip", "key": key, "wf": tk["wf"], "rel": tk["rel"]}
        elif k == "accept":
            tk = self.task(key)
            tk["accept"] = b.get("status") or ("pass" if b.get("ok") else "fail")
            ev["text"] = "%s acceptance: %s" % (key, tk["accept"])
            ev["token"] = {"type": "accept", "key": key, "ok": bool(b.get("ok")), "wf": tk["wf"], "rel": tk["rel"]}
        elif k == "step":
            self.task(key)["command"] = b.get("command")
            ev["text"] = "%s runs %s" % (key, b.get("command"))
        elif k == "emit":
            ty = (b.get("event") or {}).get("type") if isinstance(b.get("event"), dict) else None
            self.emits.append(ty)
            ev["text"] = "%s emitted %s" % (key, ty)
            ev["token"] = {"type": "emit", "event": ty, "key": key, "wf": self.task(key)["wf"]}
        elif k == "event":
            ev["text"] = "event %s arrived" % b.get("type")
            ev["token"] = {"type": "event", "event": b.get("type")}
        elif k == "escalation":
            self.escalations.append({"key": key, "to": b.get("to")})
            if key in self.tasks:
                self.tasks[key]["state"] = "escalated"
            ev["text"] = "%s escalated to %s" % (key, b.get("to"))
            ev["token"] = {"type": "escalation", "key": key, "to": b.get("to")}
        elif k == "item":
            ev["text"] = "%s acceptance item %s (%s): %s" % (key, b.get("index"), b.get("item"), b.get("result"))
        elif k == "until":
            ev["text"] = "%s heard %s events, result %s" % (key, b.get("events"), b.get("result"))
        elif k in ("retry", "caught"):
            ev["text"] = "%s %s%s" % (key, k, (": " + str(b.get("error"))) if b.get("error") else "")
        elif k == "ignored":
            ev["text"] = b.get("text") or "event ignored"
        elif k == "run-end":
            self.status, self.end_status = "ended", b.get("status")
            for tk in self.tasks.values():
                if tk["state"] == "running":
                    tk["state"] = "interrupted"
            ev["text"] = "run ended: %s" % b.get("status")
            ev["token"] = {"type": "run-end", "status": b.get("status")}
        else:
            ev["text"] = k
        if ev["text"]:
            self.events.append({x: ev[x] for x in ("seq", "kind", "key", "t", "text") if x in ev})
            del self.events[:-KEEP_EVENTS]
        if seen_wall:
            ev["wall"] = seen_wall
        return ev

    # ---------------------------------------------------------------- what changed
    def refresh_change(self, now):
        c = self.change
        if not c or not c.get("worktree") or now - self._git_at < GIT_EVERY:
            return
        self._git_at = now
        wt = c["worktree"]
        if not isinstance(wt, str) or not under(wt, self.worktree_roots):
            c.update(files=None, note="not inspected: the worktree is outside every --worktree-root")
            return
        if not os.path.isdir(wt):
            c.update(files=None, note="the worktree no longer exists")
            return
        try:
            p = subprocess.run(GIT + ["-C", wt, "status", "--porcelain", "-uall"], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError) as e:
            c.update(files=None, note="git status failed: %s" % e)
            return
        if p.returncode:
            c.update(files=None, note="not a git repository, so the changed files are unknown")
            return
        files = [{"status": l[:2].strip(), "path": l[3:]} for l in p.stdout.splitlines() if l.strip()]
        key = json.dumps(files)
        if key == self._git_key:
            return
        self._git_key = key
        c.update(files=files, note=None)
        c["rungs"] = classify(wt, files, self.org_root) if self.org_root and (Path(wt) / "manifest.json").exists() else None

    def journal(self):
        """The runtime's per-call cost journal, sessions/<run_id>.calls.jsonl beside the ledger.
        The ledger carries cost only on step results; judge calls (reviewer, lead) are paid model calls
        that only this journal records. Returns {usd, calls, tasks, unknown} or None."""
        if not self.run_id or not SAFE_ID.match(self.run_id):
            return None
        f = Path(self.path).parent / "sessions" / ("%s.calls.jsonl" % self.run_id)
        try:
            st = f.stat()
        except OSError:
            return None
        key = (st.st_size, st.st_mtime)
        if key != self._journal_key:
            usd, n, unknown, tasks = 0.0, 0, 0, {}
            try:
                for line in f.read_text().splitlines():
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(r, dict) or (r.get("run") and r.get("run") != self.run_id):
                        continue
                    n += 1
                    u = float(r.get("usd") or 0)
                    usd += u
                    if not r.get("usd_known", True):
                        unknown += 1
                    tasks[r.get("task") or ""] = tasks.get(r.get("task") or "", 0.0) + u
            except OSError:
                return None
            self._journal_key, self._journal = key, {"usd": usd, "calls": n, "tasks": tasks, "unknown": unknown}
        return self._journal

    # ---------------------------------------------------------------- output
    def running_keys(self):
        run = [k for k, v in self.tasks.items() if v["state"] == "running"]
        return [k for k in run if not any(o != k and o.startswith(k + "/") for o in run)]

    def snapshot(self, now=None, events=60):
        now = now or time.time()
        status = self.status  # a run waiting at a gate appends nothing for days: it stays running, with idle seconds
        cur = []
        for k in self.running_keys():
            t = self.tasks[k]
            cur.append({"key": k, "wf": t["wf"], "rel": t["rel"], "since": self.wall(t["t_start"]), "usd": t["usd"]})
        j = self.journal()
        if j:  # the journal counts every model call, judges included
            cost, src, partial = j["usd"], "journal", j["unknown"] > 0
            tusd = j["tasks"]
        else:  # ledger only: judge calls have no cost there
            cost, src, partial = self.cost, "ledger", self.judge_calls > 0
            tusd = {}
        return {"id": self.id, "path": self.path, "run_id": self.run_id, "workflow": self.workflow, "title": self.title,
                "status": status, "end_status": self.end_status, "idle": round(now - self.last_wall) if self.last_wall else None, "started": self.start_wall, "last": self.last_wall,
                "cost_usd": round(cost, 6), "cost_src": src, "cost_partial": partial, "ledger_usd": round(self.cost, 6),
                "model_calls": j["calls"] if j else None, "judge_calls": self.judge_calls, "calls": self.calls, "current": cur,
                "tasks": {k: dict({x: v[x] for x in ("wf", "rel", "state", "starts", "accept", "checks", "judges", "usd")}, **({"usd": round(tusd[k], 6)} if k in tusd else {}))
                          for k, v in self.tasks.items()},
                "workflows": sorted({v for v in self.prefixes.values() if v}),
                "change": self.change, "escalations": self.escalations[-10:], "emits": self.emits[-10:],
                "pair": self.pair, "problems": self.problems[-5:], "events": self.events[-events:], "entries": self.last_seq}


def classify(worktree, files, org_root):
    """Rung of each changed path of an org-root worktree, with check_change against the git HEAD."""
    try:
        import yaml  # noqa: F401  workflows are YAML; without it check_change would call every file frozen
    except ImportError:
        return {"note": "rung unknown: PyYAML is missing (start serve.py with uv run --with pyyaml)"}
    sys.path.insert(0, str(Path(org_root) / "scripts"))
    try:
        import check_change as cc
    except ImportError as e:
        return {"note": "rung unknown: cannot load check_change (%s)" % e}
    finally:
        sys.path.pop(0)
    try:
        top = subprocess.run(GIT + ["-C", worktree, "rev-parse", "--show-prefix"], capture_output=True, text=True, timeout=5).stdout.strip()
        tracked = [t for t in subprocess.run(GIT + ["-C", worktree, "ls-files"], capture_output=True, text=True, timeout=5).stdout.split("\n") if t]
    except (OSError, subprocess.SubprocessError) as e:
        return {"note": "rung unknown: %s" % e}
    present = []
    for p in Path(worktree).rglob("*"):
        if ".git" in p.parts or p.is_symlink() or not p.is_file():
            continue
        present.append(p)
        if len(present) > CLASSIFY_FILES:
            break
    if len(tracked) > CLASSIFY_FILES or len(present) > CLASSIFY_FILES:
        return {"note": "rung unknown: more than %d files" % CLASSIFY_FILES}
    base, new = {}, {}
    for rel in tracked:
        try:
            b = subprocess.run(GIT + ["-C", worktree, "show", "HEAD:./" + rel], capture_output=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            b = None
        base[rel] = b.stdout if b is not None and b.returncode == 0 and len(b.stdout) <= CLASSIFY_BYTES else None
    for p in present:
        rel = str(p.relative_to(worktree))
        new[rel] = p.read_bytes() if p.stat().st_size <= CLASSIFY_BYTES else None
        base.setdefault(rel, None)
    for rel in base:
        new.setdefault(rel, None)
    entries, refused = cc.check_change(base, new, ["free", "ordinary"])
    order = ["free", "ordinary", "protected", "frozen"]
    rows = [{"path": p, "task": t, "row": r, "rung": g} for p, t, r, g in entries]
    top_rung = max((r["rung"] for r in rows), key=order.index, default=None)
    return {"rows": rows[:50], "highest": top_rung, "refused": len(refused), "prefix": top}


class Live:
    """Every source, polled together. `poll()` returns new events across runs."""

    def __init__(self, cfg):
        """cfg: {"state_dirs": [...], "ledgers": [globs], "org_root": path or None, "worktree_roots": [...]}.
        A ledger's worktree is inspected with git only under a worktree root: the ledger names the path."""
        self.cfg = {"state_dirs": list(cfg.get("state_dirs") or []), "ledgers": list(cfg.get("ledgers") or []),
                    "org_root": cfg.get("org_root"), "worktree_roots": list(cfg.get("worktree_roots") or [])}
        self.runs = {}
        self.sources = []

    def discover(self):
        found, sources, pairs = [], [], {}
        for d in self.cfg["state_dirs"]:
            sf = os.path.join(d, "dispatcher.json")
            note = None
            try:
                st = json.loads(Path(sf).read_text())
                for pk, pv in (st.get("pairs") or {}).items():
                    name = pv.get("ledger") if isinstance(pv, dict) else None
                    if isinstance(name, str) and name == os.path.basename(name) and not name.startswith("."):
                        lp = os.path.join(d, "ledgers", pv["ledger"])
                        event, _, wf = pk.partition("\n")
                        pairs[lp] = {"event": event, "workflow": wf, "state": pv.get("state"), "status": pv.get("status")}
                        found.append(lp)
            except FileNotFoundError:
                note = "no dispatcher.json"
            except (OSError, ValueError) as e:
                note = "dispatcher.json unreadable: %s" % e
            found += glob.glob(os.path.join(d, "ledgers", "*.ledger"))
            sources.append({"kind": "state dir", "path": d, "note": note})
        for g in self.cfg["ledgers"]:
            hits = glob.glob(g)
            found += hits
            sources.append({"kind": "ledger glob", "path": g, "note": None if hits else "no file matches"})
        self.sources = sources
        for p in dict.fromkeys(os.path.abspath(x) for x in found):
            if p not in self.runs:
                self.runs[p] = Run(p, self.cfg["org_root"], self.cfg["worktree_roots"])
            self.runs[p].pair = pairs.get(p)

    def metrics(self):
        """Latest value per org metric across every ledger: newest by time, then by ledger seq."""
        out = {}
        for r in self.runs.values():
            for k, m in r.metrics.items():
                if k not in out or (m["at"], m["seq"]) > (out[k]["at"], out[k]["seq"]):
                    out[k] = m
        return out

    def poll(self, now=None):
        self.discover()
        out = []
        for r in self.runs.values():
            for ev in r.poll(now):
                out.append(ev)
        return out

    def snapshot(self, now=None):
        now = now or time.time()
        runs = sorted((r.snapshot(now) for r in self.runs.values() if r.last_seq and r.workflow), key=lambda s: -(s["last"] or 0))
        newest = {}
        for r in runs:  # the page shows the latest run per workflow: keep each one even past the cap
            if r["workflow"] not in newest or (r["started"] or 0) > (newest[r["workflow"]]["started"] or 0):
                newest[r["workflow"]] = r
        keep = runs[:20] + [r for r in newest.values() if r not in runs[:20]]
        return {"at": now, "sources": self.sources, "runs": keep, "metrics": self.metrics(),
                "verified": "chain only: the ledger MAC needs the runtime's key, which this viewer never reads"}


def replay(src, dst, rate=1.0):
    lines = [l for l in Path(src).read_bytes().split(b"\n") if l.strip()]
    Path(dst).write_bytes(b"")
    last_t = 0.0
    for line in lines:
        try:
            b = json.loads(line).get("body") or {}
            t = float(b.get("t") or last_t) if isinstance(b, dict) else last_t
        except ValueError:
            t = last_t
        time.sleep(min(3.0, max(0.15, (t - last_t))) / rate)
        last_t = max(last_t, t)
        with open(dst, "ab") as f:
            f.write(line + b"\n")
    print("replayed %d entries into %s" % (len(lines), dst))


def main(argv):
    if argv[:1] == ["snapshot"]:
        import argparse

        import config

        ap = argparse.ArgumentParser(prog="live.py snapshot")
        config.add_args(ap)
        try:
            cfg = config.resolve(ap.parse_args(argv[1:]))
        except config.ConfigError as e:
            ap.error(str(e))
        lv = Live({"state_dirs": cfg.state_dirs, "ledgers": cfg.ledgers, "org_root": str(cfg.org_root), "worktree_roots": cfg.worktree_roots})
        lv.poll()
        print(json.dumps(lv.snapshot(), indent=1, default=str))
    elif argv[:1] == ["replay"] and len(argv) >= 3:
        rate = float(argv[argv.index("--rate") + 1]) if "--rate" in argv else 1.0
        replay(argv[1], argv[2], rate)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
