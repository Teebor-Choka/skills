"""Interpreter for the accepted OWS subset (spec sections 6.1, 7.3 to 7.11).

Control flow only: scripted or real steps, no ledger (U13b appends the event list to
its hash chain and verifies signatures). Standard library only, plus the sibling
modules `expr` (U5) and `validate_org` (U1).

Layout, in file order (the work splits along these lines, see the unit report):
  1. values and errors        4. hosts: ScriptedHost, ProcessHost
  2. load-time refusal        5. the run: tasks, acceptance, gates, calls
  3. deterministic scheduler  6. run accounting and the public Interpreter

Execution model: one thread, a virtual clock, generators as processes. Parallel work
(`fork`, `run.await: false`) interleaves on the clock, so two runs with the same run id
and the same scripted host give the same event list.

Decisions the spec leaves open (all PROVISIONAL, listed in the unit report):
  D1 a finished `await: false` unit appends {task, ok} to `$context.results` (one entry
     per full key, replaced on a re-run) and emits `org.unit-done`, with `data.run` and
     `data.task`, so a counted join cannot double-count.
  D2 a gate with `to.any` and `until` evaluates `until` on entry and after each event.
  D3 `emit` stamps `data.run` with the run id.
  D4 `limit.attempt.count` counts retries after the first try (count 2 = 3 tries).
  D5 every `for` iteration gets the `for` task's own input.
  D6 `$workflow.id` is the run id in every subflow.
  D7 `set` outputs the resolved map and replaces the input.
  D8 a raised error is reported as `<full key>: <title or type>`.
  D9 error types: expression 400, timeout 408, runtime 500 under the OWS error base
     (the status codes are from memory of the OWS spec, not verified here).
  D10 the workflow-level `timeout` caps the deadline of every step and gate in that
     execution; it does not interrupt `wait` or containers.
"""

import hashlib
import heapq
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import expr  # noqa: E402
import validate_org  # noqa: E402

# ------------------------------------------------------------------ 1. values and errors

ERR = "https://open-workflow-specification.org/spec/1.0.0/errors/"
E_EXPR, E_TIMEOUT, E_RUNTIME = ERR + "expression", ERR + "timeout", ERR + "runtime"
TASK_KEYS = {"call", "do", "emit", "for", "fork", "listen", "raise", "run", "set", "switch", "try", "wait"}
STEP_LIMIT = 3600  # 7.10
MAX_FOR = 1000  # 7.1
MAX_CALLS = 8  # 7.7
MAX_LISTS = 16
UNIT_DONE = "org.unit-done"
DURATION_UNITS = {"days": 86400, "hours": 3600, "minutes": 60, "seconds": 1, "milliseconds": 0.001}


@dataclass
class StepRequest:
    key: str = ""
    rel: str = ""
    path: str = ""
    command: str = ""
    arguments: list = field(default_factory=list)
    argv: list = field(default_factory=list)
    role: str = ""
    brief: str = ""
    by: str = ""
    input: object = None
    limit: object = None
    run_id: str = ""
    accepted: dict = field(default_factory=dict)
    shell: dict = field(default_factory=dict)


@dataclass
class StepOutcome:
    exit_code: int = 0
    output: object = None
    stdout: object = None
    duration: float = 0.0
    error: object = None
    timed_out: bool = False


@dataclass
class JudgeRequest:
    key: str = ""
    item: int = 0
    role: str = ""
    rubric: str = ""
    run_id: str = ""
    invocation: str = ""


@dataclass
class RunResult:
    status: str = "error"  # success | error | refused
    errors: list = field(default_factory=list)
    error_objects: list = field(default_factory=list)
    events: list = field(default_factory=list)
    accepted: dict = field(default_factory=dict)
    records: dict = field(default_factory=dict)
    run_id: str = ""
    output: object = None
    context: object = None
    now: float = 0.0


class OutsideRoot(Exception):
    """A file a host was asked to use resolves outside the org root (2.2)."""


class TaskError(Exception):
    def __init__(self, key, type_, status, text, fatal=False, title=None, detail=None):
        super().__init__(f"{key}: {text}")
        self.key, self.type, self.status, self.fatal = key, type_, status, fatal
        self.text = f"{key}: {text}"
        self.title, self.detail = title, detail

    def obj(self):
        return {"type": self.type, "status": self.status, "title": self.title, "detail": self.detail, "instance": self.key}


def _truthy(v):
    return v is not None and v is not False


def _secs(d):
    return sum(DURATION_UNITS[k] * v for k, v in d.items() if k in DURATION_UNITS) if isinstance(d, dict) else 0


def _tkey(task):
    ks = [k for k in task if k in TASK_KEYS]
    if set(ks) == {"for", "do"}:
        return "for"
    return ks[0] if len(ks) == 1 else None


def _items(lst):
    for item in lst:
        (n, t), = item.items()
        yield n, t


def _child_lists(task):
    k = _tkey(task)
    if k in ("do", "for"):
        return [task["do"]]
    if k == "fork":
        return [task["fork"].get("branches", [])]
    if k == "try":
        out = [task["try"]]
        if isinstance(task.get("catch"), dict) and isinstance(task["catch"].get("do"), list):
            out.append(task["catch"]["do"])
        return out
    return []


def _walk(lst, prefix=""):
    """Yield (path, task) in pre-order."""
    for n, t in _items(lst):
        yield prefix + n, t
        for sub in _child_lists(t):
            yield from _walk(sub, prefix + n + "/")


# ------------------------------------------------------------------ 2. load-time refusal


def _subset_errors(doc):
    """Own minimal gate: shapes the executor relies on, and the constructs spec 3.2 refuses."""
    if not isinstance(doc, dict):
        return ["(root): workflow must be a map"]
    errs = []
    if "use" in doc:
        errs.append("use: not in the accepted subset")
    if isinstance(doc.get("schedule"), dict):
        errs += [f"schedule.{k}: not in the accepted subset" for k in ("every", "cron", "after") if k in doc["schedule"]]
    if not isinstance(doc.get("do"), list):
        return errs + ["do: task list must be a list"]

    def check(lst, prefix, depth):
        if depth > MAX_LISTS:
            errs.append(f"{prefix or 'do'}: nesting deeper than {MAX_LISTS} task lists")
            return
        for i, item in enumerate(lst):
            if not isinstance(item, dict) or len(item) != 1:
                errs.append(f"{prefix}[{i}]: task item must be a map with one name")
                continue
            (n, t), = item.items()
            p = prefix + n
            if not isinstance(t, dict):
                errs.append(f"{p}: task must be a map")
                continue
            k = _tkey(t)
            if k is None:
                errs.append(f"{p}: not one OWS task; found task keys {sorted(x for x in t if x in TASK_KEYS)!r}")
                continue
            if k == "call":
                errs.append(f"{p}: task 'call' is not in the accepted subset")
            elif k == "run":
                run = t["run"] if isinstance(t["run"], dict) else {}
                for bad in ("container", "script"):
                    if bad in run:
                        errs.append(f"{p}: task 'run.{bad}' is not in the accepted subset")
                if not ("shell" in run or "workflow" in run) and not any(b in run for b in ("container", "script")):
                    errs.append(f"{p}: run: needs exactly one of container, script, shell, workflow")
            elif k == "listen":
                if "foreach" in t:
                    errs.append(f"{p}: foreach: not in the accepted subset")
                to = t["listen"].get("to") if isinstance(t["listen"], dict) else None
                if not isinstance(to, dict) or not any(m in to for m in ("one", "any", "all")):
                    errs.append(f"{p}: listen.to: needs one, any or all")
                elif "until" in to and not isinstance(to["until"], str):
                    errs.append(f"{p}: listen.to.until: only an expression is accepted")
            elif k in ("for", "do") and not isinstance(t.get("do"), list):
                errs.append(f"{p}: do: task list must be a list")
            elif k == "fork" and not isinstance(t["fork"], dict):
                errs.append(f"{p}: fork: must be a map")
            elif k == "try" and not isinstance(t["try"], list):
                errs.append(f"{p}: try: task list must be a list")
            if errs and any(e.startswith(p) for e in errs):
                continue
            for sub in _child_lists(t):
                if isinstance(sub, list):
                    check(sub, p + "/", depth + 1)
                else:
                    errs.append(f"{p}: task list must be a list")

    check(doc["do"], "", 1)
    return errs


# ------------------------------------------------------------------ 3. deterministic scheduler


class Sleep:
    def __init__(self, until):
        self.until = until


class WaitEvent:
    def __init__(self, matcher, deadline=None):
        self.matcher, self.deadline = matcher, deadline


class Join:
    def __init__(self, procs, compete=False):
        self.procs, self.compete = procs, compete


class WaitTimeout(Exception):
    pass


class _Proc:
    def __init__(self, gen):
        self.gen, self.done, self.cancelled = gen, False, False
        self.result = self.error = None
        self.token, self.finish_seq = 0, 0
        self.on_done, self.joining = [], []


class _Scheduler:
    def __init__(self, ext_events):
        self.now = 0.0
        self.ready, self.timers, self.waiters = deque(), [], []
        self.ext = sorted(enumerate(ext_events), key=lambda x: (x[1][0], x[0]))
        self.ext = [e for _, e in self.ext]
        self.ext_i = 0
        self.seq = 0
        self.live = 0
        self.fin = 0
        self.on_event = None

    def spawn(self, gen):
        p = _Proc(gen)
        self.live += 1
        self.ready.append((p, None, None))
        return p

    def publish(self, event):
        if self.on_event:
            self.on_event(event)
        for p, token, matcher in list(self.waiters):
            if p.done or p.token != token:
                continue
            r = matcher(event)
            if r is not None:
                self._resume(p, r[0])

    def cancel(self, p):
        if p.done:
            return
        for c in p.joining:
            self.cancel(c)
        p.cancelled, p.done = True, True
        self.waiters = [w for w in self.waiters if w[0] is not p]
        self.live -= 1
        p.gen.close()

    def _resume(self, p, value=None, exc=None):
        p.token += 1
        self.waiters = [w for w in self.waiters if w[0] is not p]
        self.ready.append((p, value, exc))

    def _timer(self, t, p, exc):
        self.seq += 1
        heapq.heappush(self.timers, (t, self.seq, p, p.token, exc))

    def _finish(self, p, result, error):
        p.done, p.result, p.error = True, result, error
        self.live -= 1
        self.fin += 1
        p.finish_seq = self.fin
        for cb in p.on_done:
            cb()

    def _step(self, p, value, exc):
        if p.done:
            return
        try:
            req = p.gen.throw(exc) if exc is not None else p.gen.send(value)
        except StopIteration as stop:
            self._finish(p, stop.value, None)
            return
        except TaskError as err:
            self._finish(p, None, err)
            return
        if isinstance(req, Sleep):
            self._timer(req.until, p, None)
        elif isinstance(req, WaitEvent):
            self.waiters.append((p, p.token, req.matcher))
            if req.deadline is not None:
                self._timer(req.deadline, p, WaitTimeout())
        elif isinstance(req, Join):
            self._join(p, req)
        else:
            raise TypeError(f"unknown wait request {req!r}")

    def _join(self, parent, req):
        procs = req.procs
        parent.joining = list(procs)
        state = {"over": False}

        def check():
            if state["over"] or parent.done:
                return
            fin = sorted((c for c in procs if c.done and not c.cancelled), key=lambda c: c.finish_seq)
            errs = [c for c in fin if c.error]
            if errs:
                outcome = (None, errs[0].error)
            elif req.compete and fin:
                outcome = (fin[0].result, None)
            elif len(fin) == len(procs):
                outcome = ([c.result for c in procs], None)
            else:
                return
            state["over"] = True
            for c in procs:
                self.cancel(c)
            parent.joining = []
            self._resume(parent, *outcome)

        for c in procs:
            c.on_done.append(check)
        check()

    def run(self):
        """Run until every process is done. False on a deadlock (live processes, nothing can wake)."""
        while self.live > 0:
            if self.ready:
                p, value, exc = self.ready.popleft()
                self._step(p, value, exc)
                continue
            nt = self.timers[0][0] if self.timers else None
            ne = self.ext[self.ext_i][0] if self.ext_i < len(self.ext) else None
            if nt is None and ne is None:
                return False
            if nt is not None and (ne is None or nt <= ne):
                t = nt
                self.now = max(self.now, t)
                while self.timers and self.timers[0][0] <= t:
                    _, _, p, token, exc = heapq.heappop(self.timers)
                    if not p.done and p.token == token:
                        self._resume(p, None, exc)
            else:
                t = ne
                self.now = max(self.now, t)
                while self.ext_i < len(self.ext) and self.ext[self.ext_i][0] <= t:
                    event = self.ext[self.ext_i][1]
                    self.ext_i += 1
                    self.publish(event)
        return True


# ------------------------------------------------------------------ 4. hosts


def _lookup(table, key):
    """Script entry for a full key: exact, then the part after the last '>', each with '#<i>' removed."""
    last = key.rsplit(">", 1)[-1]
    for cand in (key, last, _strip_idx(key), _strip_idx(last)):
        if cand in table:
            return cand, table[cand]
    return None, None


def _strip_idx(key):
    return re.sub(r"#[0-9]+", "", key)


class ScriptedHost:
    """Fixed results per node: no model, no processes. `calls` records every request."""

    def __init__(self, steps=None, checks=None, judges=None, events=None, signed=None, outside=()):
        self.steps, self.checks, self.judges = dict(steps or {}), dict(checks or {}), dict(judges or {})
        self.events = list(events or [])
        self.signed = signed or (lambda e: e.get("signature") == "owner")
        self.outside = set(outside)
        self.calls = []
        self._n = {}

    def _pick(self, table, name, lookup):
        k, v = lookup(table, name)
        if k is None:
            return None, False
        if isinstance(v, list):
            i = self._n.get((id(table), k), 0)
            self._n[(id(table), k)] = i + 1
            return v[min(i, len(v) - 1)], True
        return v, True

    def scheduled_events(self):
        return list(self.events)

    def verify_owner(self, event):
        return bool(self.signed(event))

    def confined(self, rel):
        return rel not in self.outside

    def run_step(self, req):
        self.calls.append(("step", req.command, req.key))
        v, found = self._pick(self.steps, req.key, _lookup)
        if callable(v):
            v = v(req)
        if v is None:
            return StepOutcome()
        return v if isinstance(v, StepOutcome) else StepOutcome(**v)

    def run_check(self, name, key, evidence):
        self.calls.append(("check", name, key))
        if f"checks/{name}.py" in self.outside:
            raise OutsideRoot(f"checks/{name}.py")
        v, found = self._pick(self.checks, name, lambda t, n: (n, t[n]) if n in t else (None, None))
        if callable(v):
            return bool(v(name, key, evidence))
        return True if not found else bool(v)

    def run_judge(self, req):
        self.calls.append(("judge", req.role, req.key))
        v, found = self._pick(self.judges, req.key, _lookup)
        if callable(v):
            return v(req)
        verdict = v if found else "pass"
        return {"invocation": req.invocation, "type": "org.rubric-verdict",
                "data": {"run": req.run_id, "task": req.key, "item": req.item, "verdict": verdict}}


class ProcessHost:
    """Real argv exec (7.8): `agent-run`, or a file in `<root>/bin`; never a shell.

    Files are opened first and the descriptor's own path is compared with the root
    before any byte is read (2.2). Events and the clock stay virtual: this host runs
    commands and checks, it does not wait in real time for events.
    """

    def __init__(self, root, agent_run=None, events=(), verify=None):
        self.root = os.path.realpath(root)
        self.agent_run = agent_run
        self.events = list(events)
        self.verify = verify
        self.calls = []

    def scheduled_events(self):
        return list(self.events)

    def verify_owner(self, event):
        return bool(self.verify(event)) if self.verify else False

    def _where(self, rel):
        """inside | outside | missing, from the opened descriptor's own path."""
        try:
            fd = os.open(os.path.join(self.root, rel), os.O_RDONLY)
        except OSError:
            return "missing"
        try:
            if sys.platform == "darwin":
                import fcntl
                raw = fcntl.fcntl(fd, fcntl.F_GETPATH, b"\0" * 1024)
                path = raw.split(b"\0", 1)[0].decode()
            else:
                path = os.readlink(f"/proc/self/fd/{fd}")
            path = os.path.realpath(path)
        finally:
            os.close(fd)
        return "inside" if path == self.root or path.startswith(self.root + os.sep) else "outside"

    def confined(self, rel):
        return self._where(rel) == "inside"

    def run_step(self, req):
        cmd = req.command
        if cmd == "agent-run":
            exe = self.agent_run or ""
        else:
            exe = os.path.join(self.root, "bin", cmd)
            if self._where(os.path.join("bin", cmd)) != "inside" or not os.access(exe, os.X_OK):
                exe = ""
        if not exe:
            return StepOutcome(exit_code=127, error=f"run.shell.command: '{cmd}' is not agent-run or a file in bin/")
        env = {"PATH": os.environ.get("PATH", ""), "ORG_ROOT": self.root, "ORG_RUN": req.run_id, "ORG_KEY": req.key}
        if cmd != "agent-run":
            env.update({str(k): str(v) for k, v in (req.shell.get("environment") or {}).items()})
        stdin = json.dumps(req.input)
        t0 = time.monotonic()
        try:
            proc = subprocess.Popen([exe] + req.argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=env, cwd=self.root, text=True, start_new_session=True)
        except OSError as e:
            return StepOutcome(exit_code=127, error=f"cannot start: {e.strerror}")
        try:
            out, err = proc.communicate(stdin, timeout=req.limit)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return StepOutcome(exit_code=-9, duration=req.limit or 0, timed_out=True)
        dur = time.monotonic() - t0
        text = out.strip()
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = text
        error = None
        if proc.returncode != 0:
            error = (err.strip().splitlines() or [f"command exited {proc.returncode}"])[0]
        return StepOutcome(exit_code=proc.returncode, output=parsed, stdout=out, duration=dur, error=error)

    def run_check(self, name, key, evidence):
        rel = f"checks/{name}.py"
        where = self._where(rel)
        if where == "outside":
            raise OutsideRoot(rel)
        if where == "missing":
            return False
        fd, path = tempfile.mkstemp(prefix="org-evidence-", suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(evidence, f)
            env = {"PATH": os.environ.get("PATH", ""), "ORG_EVIDENCE": os.path.abspath(path), "ORG_KEY": key,
                   "ORG_RUN": evidence["run"]}
            try:
                r = subprocess.run([sys.executable, os.path.join(self.root, rel), key], env=env, cwd=self.root,
                                   capture_output=True, timeout=300, stdin=subprocess.DEVNULL)
            except (OSError, subprocess.TimeoutExpired):
                return False
            return r.returncode == 0  # 1 fail, 2 bad evidence (fail), anything else fail
        finally:
            os.unlink(path)

    def run_judge(self, req):
        return None  # the model judge is U12's agent-run; this host has no adapter for it


# ------------------------------------------------------------------ 5. the run


class _Sc:
    __slots__ = ("iters", "loops", "lv")

    def __init__(self, iters=(), loops=(), lv=None):
        self.iters, self.loops, self.lv = iters, loops, lv or {}


class _T:
    """One task occurrence: names, keys, scope."""

    def __init__(self, ex, name, task, parent, sc):
        self.name, self.task, self.sc = name, task, sc
        self.path = parent + name
        self.rel = self.path + "".join(f"#{i}" for i in sc.iters)
        self.full = ex.prefix + self.rel
        self.kind = _tkey(task)
        org = (task.get("metadata") or {}).get("org")
        self.org = org if isinstance(org, dict) else {}
        self.floor = self.path in ex.floors
        self.sort = ex.sortbase + (ex.pre.get(self.path, 0),) + tuple(sc.iters)


class _Rec:
    def __init__(self, ok, sort, base):
        self.ok, self.sort, self.base = ok, sort, base


class _Ex:
    """One workflow execution: its context, `$accepted` and code-step results."""

    def __init__(self, run, name, doc, prefix, sortbase, stack):
        self.run, self.name, self.doc, self.prefix, self.sortbase, self.stack = run, name, doc, prefix, sortbase, stack
        self.context, self.accepted, self.code = {}, {}, {}
        self.pre = {p: i for i, (p, _) in enumerate(_walk(doc["do"]))}
        self.floors = {p for p, t in _walk(doc["do"]) if run.is_floor(t)}
        self.deadline = None


class _Run:
    def __init__(self, interp, rid):
        self.interp, self.host, self.rid = interp, interp.host, rid
        self.events, self.records, self.execs = [], {}, []
        self.detached_errors, self.inv = [], 0
        self.sched = _Scheduler(list(getattr(self.host, "scheduled_events", lambda: [])()))
        self.sched.on_event = lambda e: self.log("event", type=e.get("type"), event=json.loads(json.dumps(e)))

    # -- infrastructure

    def log(self, kind, **kw):
        e = {"seq": len(self.events), "t": self.sched.now, "kind": kind}
        e.update(kw)
        self.events.append(e)

    def is_floor(self, task):
        org = (task.get("metadata") or {}).get("org")
        if isinstance(org, dict) and org.get("floor") is True:
            return True
        run = task.get("run")
        if isinstance(run, dict) and isinstance(run.get("workflow"), dict):
            target = self.interp.workflows.get(run["workflow"].get("name"))
            return bool(target) and any(self._direct_floor(t) for _, t in _walk(target["do"]))
        return False

    @staticmethod
    def _direct_floor(task):
        org = (task.get("metadata") or {}).get("org")
        return isinstance(org, dict) and org.get("floor") is True

    def vars(self, ex, sc, extra):
        v = dict(sc.lv)
        v.update(extra)
        v.update({"context": ex.context, "runtime": {"name": "ows-interpreter", "version": "0"},
                  "workflow": {"id": self.rid, "definition": {"document": ex.doc.get("document", {})}}})
        v["accepted"] = ex.accepted  # bound last: nothing shadows it
        return v

    def x(self, ex, key, value, data, sc, **extra):
        try:
            return expr.resolve(value, data, self.vars(ex, sc, extra))
        except expr.ExprError as e:
            raise TaskError(key, E_EXPR, 400, str(e)) from None

    def record(self, ex, t, ok):
        ex.accepted[t.rel] = ok
        self.records[t.full] = _Rec(ok, t.sort, ex.prefix + t.path)
        self.log("accept", key=t.full, ok=ok)

    def discard(self, ex, path):
        pre = path + "/"
        for table in (ex.accepted, ex.code):
            for k in [k for k in table if k.startswith(pre)]:
                del table[k]
        fp = ex.prefix + pre
        for k in [k for k in self.records if k.startswith(fp)]:
            del self.records[k]

    # -- workflow and task lists

    def workflow(self, ex, inp):
        self.execs.append(ex)
        self.log("workflow-start", workflow=ex.name, prefix=ex.prefix)
        tmo = ex.doc.get("timeout")
        if isinstance(tmo, dict) and "after" in tmo:
            ex.deadline = self.sched.now + _secs(tmo["after"])
        sc = _Sc()
        data = inp
        wi = ex.doc.get("input")
        if isinstance(wi, dict) and "from" in wi:
            data = self.x(ex, ex.prefix.rstrip(">") or ex.name, wi["from"], data, sc, input=data)
        out, _ = yield from self.tasks(ex, ex.doc["do"], "", sc, data)
        wo = ex.doc.get("output")
        if isinstance(wo, dict) and "as" in wo:
            out = self.x(ex, ex.prefix.rstrip(">") or ex.name, wo["as"], out, sc, output=out)
        return out

    def tasks(self, ex, lst, parent, sc, data):
        names = [n for n, _ in _items(lst)]
        i = 0
        while i < len(lst):
            (name, task), = lst[i].items()
            out, d = yield from self.task(ex, name, task, parent, sc, data)
            data = out
            if d in (None, "continue"):
                i += 1
            elif d in ("end", "exit"):
                return data, d
            elif d in names[i + 1:]:
                i = names.index(d, i + 1)
            else:
                raise TaskError(ex.prefix + parent + name, E_RUNTIME, 500,
                                f"then: '{d}' is not a later task in the same list", fatal=True)
        return data, None

    def task(self, ex, name, task, parent, sc, data):
        t = _T(ex, name, task, parent, sc)
        data0 = data
        inp = task.get("input")
        if isinstance(inp, dict) and "from" in inp:
            data = data0 = self.x(ex, t.full, inp["from"], data, sc, input=data)
        if "if" in task and not _truthy(self.x(ex, t.full, task["if"], data, sc, input=data)):
            self.log("task-skip", key=t.full)
            return data, None
        self.log("task-start", key=t.full, path=t.path)
        sig, directive, k = None, None, t.kind
        if k == "do":
            out, sig = yield from self.tasks(ex, task["do"], t.path + "/", sc, data)
        elif k == "for":
            out, sig = yield from self.for_(ex, t, data)
        elif k == "fork":
            out = yield from self.fork(ex, t, data)
        elif k == "try":
            out, sig, directive = yield from self.try_(ex, t, data)
        elif k == "switch":
            out, directive = data, self.switch(ex, t, data)
        elif k == "set":
            out = self.x(ex, t.full, task["set"], data, sc, input=data)
        elif k == "wait":
            yield Sleep(self.sched.now + _secs(task["wait"]))
            out = data
        elif k == "raise":
            self.raise_(ex, t, data)
        else:
            out = yield from self.leaf(ex, t, data)
        if isinstance(task.get("output"), dict) and "as" in task["output"]:
            out = self.x(ex, t.full, task["output"]["as"], out, sc, input=data0, output=out)
        if isinstance(task.get("export"), dict) and "as" in task["export"]:
            ex.context = self.x(ex, t.full, task["export"]["as"], out, sc, input=data0, output=out)
        self.log("task-end", key=t.full)
        if sig == "end":
            return out, "end"
        return out, directive or task.get("then")

    # -- control kinds

    def for_(self, ex, t, data):
        task, sc = t.task, t.sc
        f = task["for"]
        each, at = f.get("each", "item"), f.get("at", "index")
        items = self.x(ex, t.full, f.get("in"), data, sc, input=data)
        if not isinstance(items, list):
            raise TaskError(t.full, E_RUNTIME, 400, "for.in: must evaluate to a list")
        if len(items) > MAX_FOR:
            raise TaskError(t.full, E_RUNTIME, 400, f"for.in: {len(items)} items exceeds the cap of {MAX_FOR}")
        cond = task.get("while")
        loops = sc.loops + (expr.unwrap(cond),) if isinstance(cond, str) and expr.is_expression(cond) else sc.loops
        out = data
        for i, item in enumerate(items):
            lv = dict(sc.lv)
            lv[each], lv[at] = item, i
            if cond is not None:
                # while sees the previous round's results; only then are they discarded (7.4 rule 2)
                if not _truthy(self.x(ex, t.full, cond, data, _Sc(sc.iters, loops, lv), input=data)):
                    break
                if i > 0:
                    self.discard(ex, t.path)
            isc = _Sc(sc.iters if cond is not None else sc.iters + (i,), loops, lv)
            out, sig = yield from self.tasks(ex, task["do"], t.path + "/", isc, data)
            if sig == "end":
                return out, "end"
        return out, None

    def fork(self, ex, t, data):
        fk = t.task["fork"]
        procs = [self.sched.spawn(self.branch(ex, b, t.path + "/", t.sc, data)) for b in fk.get("branches", [])]
        return (yield Join(procs, bool(fk.get("compete"))))

    def branch(self, ex, item, parent, sc, data):
        out, _ = yield from self.tasks(ex, [item], parent, sc, data)
        return out

    def try_(self, ex, t, data):
        task, sc = t.task, t.sc
        c = task.get("catch") or {}
        as_name = c.get("as", "error")
        retry = c.get("retry") if isinstance(c.get("retry"), dict) else None
        retries = retry["limit"]["attempt"]["count"] if retry else 0  # D4
        delay = _secs(retry.get("delay")) if retry else 0
        attempt = 0
        while True:
            try:
                out, sig = yield from self.tasks(ex, task["try"], t.path + "/", sc, data)
                return out, sig, None
            except TaskError as e:
                if e.fatal or not self.catches(ex, t, c, as_name, e, data):
                    raise
                if attempt < retries:
                    attempt += 1
                    self.log("retry", key=t.full, attempt=attempt)
                    if delay:
                        yield Sleep(self.sched.now + delay)
                    continue
                self.log("caught", key=t.full, error=e.text)
                out, sig = data, None
                if isinstance(c.get("do"), list):
                    lv = dict(sc.lv)
                    lv[as_name] = e.obj()
                    out, sig = yield from self.tasks(ex, c["do"], t.path + "/", _Sc(sc.iters, sc.loops, lv), data)
                return out, sig, c.get("then") or task.get("then")

    def catches(self, ex, t, c, as_name, e, data):
        flt = ((c.get("errors") or {}).get("with")) or {}
        obj = e.obj()
        for k, v in flt.items():
            if obj.get(k) != v:
                return False
        sc = _Sc(t.sc.iters, t.sc.loops, dict(t.sc.lv, **{as_name: obj}))
        if "when" in c and not _truthy(self.x(ex, t.full, c["when"], data, sc, input=data)):
            return False
        return not ("exceptWhen" in c and _truthy(self.x(ex, t.full, c["exceptWhen"], data, sc, input=data)))

    def switch(self, ex, t, data):
        for case in t.task["switch"]:
            (_, c), = case.items()
            if "when" not in c or _truthy(self.x(ex, t.full, c["when"], data, t.sc, input=data)):
                return c.get("then", "continue")
        return None

    def raise_(self, ex, t, data):
        err = self.x(ex, t.full, (t.task["raise"] or {}).get("error"), data, t.sc, input=data)
        err = err if isinstance(err, dict) else {"type": str(err)}
        to = t.org.get("to")
        if to is not None:
            self.log("escalation", key=t.full, to=to)
        raise TaskError(t.full, err.get("type"), err.get("status"), err.get("title") or str(err.get("type")),
                        title=err.get("title"), detail=err.get("detail"))

    # -- leaves: step, call, gate, emit

    def limit(self, ex, t):
        tmo = t.task.get("timeout")
        if isinstance(tmo, dict) and "after" in tmo:
            lim = _secs(tmo["after"])
        elif t.kind == "run" and "shell" in t.task["run"]:
            lim = STEP_LIMIT  # 7.10
        else:
            return None if ex.deadline is None else ex.deadline
        dl = self.sched.now + lim
        return dl if ex.deadline is None else min(dl, ex.deadline)

    def leaf(self, ex, t, data):
        run = t.task.get("run")
        if t.kind == "run" and isinstance(run, dict) and run.get("await", True) is False:
            self.sched.spawn(self.detached(ex, t, data))  # 7.11: completes at once
            return data
        return (yield from self.body(ex, t, data))

    def detached(self, ex, t, data):
        ok = True
        try:
            yield from self.body(ex, t, data)
            ok = ex.accepted.get(t.rel) is not False
        except TaskError as e:
            ok = False
            self.detached_errors.append(e)
        ctx = dict(ex.context) if isinstance(ex.context, dict) else {}
        ctx["results"] = [r for r in ctx.get("results", []) if r["task"] != t.full] + [{"task": t.full, "ok": ok}]  # D1
        ex.context = ctx
        self.sched.publish({"type": UNIT_DONE, "data": {"run": self.rid, "task": t.full, "ok": ok}})

    def body(self, ex, t, data):
        deadline = self.limit(ex, t)
        try:
            decision = None
            if t.kind == "listen":
                out, decision = yield from self.listen(ex, t, data, deadline)
            elif t.kind == "emit":
                out = self.emit(ex, t, data)
            elif "shell" in t.task["run"]:
                out = yield from self.step(ex, t, data, deadline)
            else:
                out = yield from self.call(ex, t, data)
            results = yield from self.items(ex, t, deadline, decision)
        except TaskError:
            self.record(ex, t, False)  # a raised error records fail (6.1)
            raise
        ok = "fail" not in results
        self.record(ex, t, ok)
        if not ok and t.floor and not self.exempt(t):
            raise TaskError(t.full, E_RUNTIME, 500, "acceptance failed")  # 7.4 rule 1
        return out

    def exempt(self, t):
        return any(t.rel in expr.accepted_keys(w) for w in t.sc.loops)

    def timeout(self, t):
        return TaskError(t.full, E_TIMEOUT, 408, "timeout")

    def step(self, ex, t, data, deadline):
        shell = t.task["run"]["shell"]
        cmd = shell.get("command")
        args = list(shell.get("arguments") or [])
        org = t.org
        argv = [cmd] + args
        role = brief = ""
        if cmd == "agent-run":
            role, brief = org.get("role"), org.get("brief")
            if role == "owner":
                raise TaskError(t.full, E_RUNTIME, 500, "metadata.org.role: agent-run may not run as owner", fatal=True)
            for a in args:
                if a != "--isolated":
                    raise TaskError(t.full, E_RUNTIME, 500,
                                    f"run.shell.arguments: '{a}' is not an allowed agent-run flag (allowed: --isolated)", fatal=True)
            for k in ("environment", "stdin", "directory"):
                if k in shell:
                    raise TaskError(t.full, E_RUNTIME, 500, f"run.shell.{k}: not allowed on agent-run; the runtime sets it", fatal=True)
            if not brief:
                raise TaskError(t.full, E_RUNTIME, 500, "metadata.org.brief: required for agent-run", fatal=True)
            if not self.host.confined(brief):
                raise TaskError(t.full, E_RUNTIME, 500, f"metadata.org.brief: '{brief}' resolves outside the org root", fatal=True)
            argv += ["--role", role, "--brief", brief]
        now = self.sched.now
        req = StepRequest(key=t.full, rel=t.rel, path=t.path, command=cmd, arguments=args, argv=argv, role=role or org.get("role", ""),
                          brief=brief or org.get("brief", ""), by=org.get("by", ""), input=data,
                          limit=None if deadline is None else max(deadline - now, 0), run_id=self.rid,
                          accepted=dict(ex.accepted), shell=shell)
        self.log("step", key=t.full, command=cmd)
        o = self.host.run_step(req)
        dur = o.duration or 0
        if o.timed_out or (deadline is not None and now + dur > deadline):
            if deadline is not None:
                yield Sleep(deadline)
            raise self.timeout(t)
        if dur > 0:
            yield Sleep(now + dur)
        if org.get("by") == "code":
            out_text = o.stdout if o.stdout is not None else (o.output if isinstance(o.output, str) else
                                                              ("" if o.output is None else json.dumps(o.output)))
            ex.code[t.rel] = {"exit": o.exit_code, "stdout": out_text}
        if o.exit_code != 0 or o.error:
            raise TaskError(t.full, E_RUNTIME, 500, str(o.error) if o.error else f"command exited {o.exit_code}")
        return o.output

    def call(self, ex, t, data):
        w = t.task["run"]["workflow"]
        name = w.get("name")
        target = self.interp.workflows.get(name)
        if target is None:
            raise TaskError(t.full, E_RUNTIME, 500, f"run.workflow: workflow '{w.get('namespace')}/{name}' is not loaded", fatal=True)
        if name in ex.stack:
            chain = " -> ".join(f"'{n}'" for n in ex.stack[ex.stack.index(name):] + (name,))
            raise TaskError(t.full, E_RUNTIME, 500, f"run.workflow: call cycle {chain}", fatal=True)
        if len(ex.stack) > MAX_CALLS:
            raise TaskError(t.full, E_RUNTIME, 500, f"run.workflow: call depth exceeds {MAX_CALLS}", fatal=True)
        inp = self.x(ex, t.full, w.get("input"), data, t.sc, input=data)
        child = _Ex(self, name, target, t.full + ">", t.sort, ex.stack + (name,))
        return (yield from self.workflow(child, inp))

    def emit(self, ex, t, data):
        ev = self.x(ex, t.full, t.task["emit"]["event"]["with"], data, t.sc, input=data)
        ev = dict(ev)
        d = ev.get("data")
        d = dict(d) if isinstance(d, dict) else ({} if d is None else {"value": d})
        d["run"] = self.rid  # D3
        ev["data"] = d
        self.log("emit", key=t.full, event=json.loads(json.dumps(ev)))
        self.sched.publish(ev)
        return data

    # -- gates and decision events

    def decision_test(self, event, full, item=None):
        if not self.host.verify_owner(event):
            return None, "not signed by the owner"
        d = event.get("data") if isinstance(event.get("data"), dict) else {}
        if d.get("run") != self.rid:
            return None, "data.run is not this run"
        if d.get("task") != full:
            return None, f"data.task is not '{full}'"
        if item is not None and d.get("item") != item:
            return None, f"data.item is not {item}"
        if d.get("decision") not in ("approve", "reject"):
            return None, "data.decision must be approve or reject"
        return d["decision"], None

    def ignore(self, full, event, why):
        et = event.get("type")
        self.log("ignored", key=full, type=et, reason=why, text=f"{full}: ignored event '{et}': {why}")

    @staticmethod
    def flt_match(want, event):
        for k, v in want.items():
            got = event.get(k)
            if isinstance(v, dict) and isinstance(got, dict):
                if any(got.get(a) != b for a, b in v.items()):
                    return False
            elif got != v:
                return False
        return True

    def listen(self, ex, t, data, deadline):
        to = t.task["listen"]["to"]
        items = t.org.get("acceptance") or []
        decision_gate = t.org.get("role") == "owner" or any(isinstance(i, dict) and "human" in i for i in items)
        mode = "one" if "one" in to else "any" if "any" in to else "all"
        raw = [to["one"]] if mode == "one" else list(to[mode])
        flts = [(self.x(ex, t.full, f.get("with") or {}, data, t.sc, input=data), f.get("correlate")) for f in raw]
        until = to.get("until")
        full, hits, got, expect = t.full, set(), [], {}

        def done(v):
            return (v,)

        if decision_gate:
            def matcher(event):
                if not any(self.flt_match(w, event) for w, _ in flts):
                    return None
                dec, why = self.decision_test(event, full)
                if why:
                    self.ignore(full, event, why)
                    return None
                return done((dec, event))
        else:
            def matcher(event):
                for idx, (w, corr) in enumerate(flts):
                    if not self.flt_match(w, event):
                        continue
                    if corr:
                        if not self.correlated(ex, t, corr, event, expect, data):
                            continue
                    elif (event.get("data") or {}).get("run") != self.rid:
                        self.ignore(full, event, "data.run is not this run")
                        continue
                    got.append(event)
                    hits.add(idx)
                    if mode == "one":
                        return done((event, None))
                    if mode == "all":
                        if len(hits) == len(flts):
                            return done((list(got), None))
                    elif until is None:
                        return done((list(got), None))
                    elif _truthy(self.x(ex, full, until, list(got), t.sc, input=data)):  # D2
                        return done((list(got), None))
                return None

            if until is not None and _truthy(self.x(ex, full, until, [], t.sc, input=data)):
                return [], None
        try:
            value = yield WaitEvent(matcher, deadline)
        except WaitTimeout:
            raise self.timeout(t) from None
        if decision_gate:
            verdict, event = value
            if verdict == "reject":
                raise TaskError(full, E_RUNTIME, 500, "decision rejected")
            return event, "approve"
        return value[0], None

    def correlated(self, ex, t, corr, event, expect, data):
        for key, spec in corr.items():
            val = self.x(ex, t.full, spec["from"], event, t.sc, input=data)
            if "expect" in spec:
                want = self.x(ex, t.full, spec["expect"], data, t.sc, input=data)
            else:
                want = expect.setdefault(key, val)
            if val != want:
                return False
        return True

    # -- acceptance items (6.1)

    def items(self, ex, t, deadline, decision):
        results = []
        for idx, item in enumerate(t.org.get("acceptance") or []):
            if "check" in item:
                kind = "check"
                evidence = {"run": self.rid, "key": t.full, "steps": json.loads(json.dumps(ex.code))}
                try:
                    r = "pass" if self.host.run_check(item["check"], t.full, evidence) else "fail"
                except OutsideRoot as e:
                    raise TaskError(t.full, E_RUNTIME, 500,
                                    f"metadata.org.acceptance[{idx}].check: '{e}' resolves outside the org root", fatal=True)
            elif "rubric" in item:
                kind = "rubric"
                r = yield from self.rubric(ex, t, idx, item, deadline)
            else:
                kind = "human"
                r = "pass" if decision == "approve" else "fail"
            self.log("item", key=t.full, index=idx, item=kind, result=r)
            results.append(r)
        return results

    def rubric(self, ex, t, idx, item, deadline):
        sample = item.get("sample", 1)
        h = int.from_bytes(hashlib.sha256(f"{self.rid}\n{t.full}\n{idx}".encode()).digest()[:8], "big")
        if not h / 2**64 < sample:
            return "pending"
        if item["judge"] == "owner":
            full = t.full

            def matcher(event):
                d = event.get("data")
                if not isinstance(d, dict) or d.get("task") != full:
                    return None
                dec, why = self.decision_test(event, full, idx)
                if why:
                    self.ignore(full, event, why)
                    return None
                return (dec,)
            try:
                dec = yield WaitEvent(matcher, deadline)
            except WaitTimeout:
                raise self.timeout(t) from None
            return "pass" if dec == "approve" else "fail"
        if not self.host.confined(item["rubric"]):
            raise TaskError(t.full, E_RUNTIME, 500,
                            f"metadata.org.acceptance[{idx}].rubric: '{item['rubric']}' resolves outside the org root", fatal=True)
        self.inv += 1
        req = JudgeRequest(key=t.full, item=idx, role=item["judge"], rubric=item["rubric"], run_id=self.rid,
                           invocation=f"{self.rid}:{self.inv}")
        reply = self.host.run_judge(req)
        if not isinstance(reply, dict):
            return "fail"
        dur = reply.get("duration") or 0
        if dur and deadline is not None and self.sched.now + dur > deadline:
            yield Sleep(deadline)
            raise self.timeout(t)
        if dur:
            yield Sleep(self.sched.now + dur)
        d = reply.get("data") if isinstance(reply.get("data"), dict) else {}
        valid = (reply.get("invocation") == req.invocation and reply.get("type") == "org.rubric-verdict"
                 and d.get("run") == self.rid and d.get("task") == t.full and d.get("item") == idx)
        return d.get("verdict") if valid and d.get("verdict") in ("pass", "fail") else "fail"

    # -- accounting (7.4 runtime rule 3)

    def accounting(self):
        errs = []
        for ex in self.execs:
            for path in sorted(ex.floors, key=lambda p: ex.pre.get(p, 0)):
                base = ex.prefix + path
                if not any(r.base == base for r in self.records.values()):
                    errs.append((ex.sortbase + (ex.pre.get(path, 0),), f"{base}: floor-not-run"))
        for key, r in self.records.items():
            if not r.ok:
                errs.append((r.sort, f"{key}: acceptance failed"))
        seen, out = set(), []
        for _, text in sorted(errs, key=lambda e: e[0]):
            if text not in seen:
                seen.add(text)
                out.append(text)
        return out

    def main(self, ex, inp):
        out = yield from self.workflow(ex, inp)
        return out

    def execute(self, name, inp):
        doc = self.interp.workflows[name]
        root = _Ex(self, name, doc, "", (), (name,))
        self.log("run-start", workflow=name, run=self.rid)
        main = self.sched.spawn(self.main(root, inp))
        finished = self.sched.run()
        errors, objects = [], []
        if main.error is not None:
            errors.append(main.error.text)
            objects.append(main.error.obj())
        for e in self.detached_errors:
            if e.text not in errors:
                errors.append(e.text)
                objects.append(e.obj())
        if main.error is None:
            if not finished:
                errors.append("deadlock: tasks are waiting and nothing can wake them")
            for text in self.accounting():
                if text not in errors:
                    errors.append(text)
        status = "error" if errors else "success"
        self.log("run-end", status=status)
        return RunResult(status=status, errors=errors, error_objects=objects, events=self.events,
                         accepted=dict(root.accepted), records={k: r.ok for k, r in self.records.items()},
                         run_id=self.rid, output=main.result, context=root.context, now=self.sched.now)


# ------------------------------------------------------------------ 6. public interface


class Interpreter:
    """Runs workflows from `workflows` (name to parsed OWS document) against a host.

    With `catalog` and `manifest` every workflow also passes `validate_org` before the
    first task. Without them only the built-in subset gate runs; the runtime floor
    accounting still holds either way.
    """

    def __init__(self, workflows, host, catalog=None, manifest=None):
        self.workflows, self.host = workflows, host
        self.catalog, self.manifest = catalog, manifest

    def refusals(self, name):
        if name not in self.workflows:
            return [f"run refused: {name}: workflow is not loaded"]
        errs = []
        for n in [name] + [n for n in self.workflows if n != name]:
            doc = self.workflows[n]
            found = _subset_errors(doc)
            if not found and self.catalog is not None and self.manifest is not None:
                found = validate_org.validate_org(doc, self.catalog, self.manifest)
            errs += [f"run refused: {n}: {e}" for e in found]
        return errs

    def run(self, name, input=None, run_id=None):
        rid = run_id or secrets.token_hex(16)  # 128 random bits, 32 hex digits
        errs = self.refusals(name)
        if errs:
            return RunResult(status="refused", errors=errs, run_id=rid)
        return _Run(self, rid).execute(name, input)
