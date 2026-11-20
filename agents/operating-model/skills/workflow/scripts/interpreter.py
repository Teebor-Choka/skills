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

Decisions the spec leaves open (PROVISIONAL, listed in the unit report):
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
  D11 (spec P24, amended by review 1) a plain gate on `org.task-ended` first replays the
     matching events of its scope that no earlier gate consumed; each event is consumed
     by at most one gate execution per run.
  D12 `exit` inside a `for` body leaves the whole loop (the body list is the task list).
  D13 an executable `bin` command runs from the verified descriptor (`/dev/fd/N`). A `#!`
     script works everywhere (its interpreter opens the descriptor); a binary works where
     the OS can exec a read-only descriptor (Linux) and fails to start with a located
     error elsewhere (macOS). Python scripts get `-I`.
  D14 a check script runs from the verified bytes (`python -I -c`, script on stdin, run as
     `__main__`), not from its path; the org root is never on `sys.path` ahead of the stdlib.
  D15 a caller's `$accepted` also holds callee keys as `<call key>><callee key>`.

The runtime input file (7.8) lives in a private 0700 temp directory outside the org root
with mode 0444. Permissions do not protect it from a child running as the same user:
the model child must never receive the path (U12 reads the file and gives the model the
contents). The runtime refuses a TMPDIR inside the org root.
"""

import hashlib
import heapq
import json
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import expr  # noqa: E402
import validate_org  # noqa: E402

# ------------------------------------------------------------------ 1. values and errors

ERR = "https://open-workflow-specification.org/spec/1.0.0/errors/"
E_EXPR, E_TIMEOUT, E_RUNTIME = ERR + "expression", ERR + "timeout", ERR + "runtime"
TASK_KEYS = {"call", "do", "emit", "for", "fork", "listen", "raise", "run", "set", "switch", "try", "wait"}
STEP_LIMIT = 3600  # 7.10
OWNER_RUBRIC_LIMIT = 7 * 86400  # an owner-judged rubric without an inline task timeout (6.1)
MAX_FOR = 1000  # 7.1
MAX_ITERATIONS = 10000  # for iterations in one run, nested multiplication included
MAX_CALLS = 8  # 7.7
MAX_LISTS = 16
OUTPUT_CAP = 1_000_000
TASK_ENDED = "org.task-ended"
RESERVED_PREFIXES = ("org.owner-", "org.task-")
DURATION_UNITS = {"days": 86400, "hours": 3600, "minutes": 60, "seconds": 1, "milliseconds": 0.001}
RUNGS = ("free", "ordinary", "protected")
RUN_ID = re.compile(r"[A-Za-z0-9-]{8,64}")
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
CMD_NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")
CHECK_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
CHECK_PRELUDE = (
    "import os, sys, __main__\n"
    "path, key = sys.argv[1], sys.argv[2]\n"
    "src = sys.stdin.buffer.read()\n"
    "sys.argv = [path, key]\n"
    "sys.path.append(os.path.dirname(path))\n"  # siblings such as _lib, after the stdlib
    "ns = __main__.__dict__\n"
    "ns['__file__'] = path\n"
    "exec(compile(src, path, 'exec'), ns)\n"
)


def drawn(h, sample):
    """The sampling draw, compared as integers: h / 2**64 < sample (6.1)."""
    try:
        return h < Fraction(sample) * 2**64
    except (TypeError, ValueError):
        return True


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
    network: object = None
    input_file: str = ""


@dataclass
class StepOutcome:
    exit_code: int = 0
    output: object = None
    stdout: object = None
    duration: float = 0.0
    error: object = None
    timed_out: bool = False
    truncated: bool = False


@dataclass
class JudgeRequest:
    key: str = ""
    item: int = 0
    role: str = ""
    rubric: str = ""
    run_id: str = ""
    invocation: str = ""
    input_file: str = ""
    argv: list = field(default_factory=list)


@dataclass
class RunResult:
    status: str = "error"  # success | error | refused
    errors: list = field(default_factory=list)
    error_objects: list = field(default_factory=list)
    events: list = field(default_factory=list)
    accepted: dict = field(default_factory=dict)
    records: dict = field(default_factory=dict)
    statuses: dict = field(default_factory=dict)
    run_id: str = ""
    output: object = None
    context: object = None
    now: float = 0.0


class ControlFlow(Exception):
    """Base for exceptions that must pass through the interpreter unchanged (U13b's ledger and divergence errors)."""


class OutsideRoot(Exception):
    """A file a host was asked to use resolves outside the org root (2.2)."""


class TaskError(Exception):
    def __init__(self, key, type_, status, text, fatal=False, title=None, detail=None):
        super().__init__(f"{key}: {text}")
        self.key, self.type, self.status, self.fatal = key, type_, status, fatal
        self.text = f"{key}: {text}"
        self.title, self.detail = title, detail
        self.failed = []  # (key, record) pairs this error turned into fail (for `handled`)

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
        self.procs = []
        self.abort = False
        self.on_event = None

    def spawn(self, gen):
        """Start a process now: it runs to its first wait before the spawner continues."""
        p = _Proc(gen)
        self.live += 1
        self.procs.append(p)
        self._step(p, None, None)
        return p

    def publish(self, event):
        if self.on_event:
            self.on_event(event)
        for p, token, matcher in list(self.waiters):
            if p.done or p.token != token:
                continue
            try:
                r = matcher(event)
            except TaskError as err:  # a filter error belongs to the waiting gate, never to the publisher
                self._resume(p, None, err)
                continue
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

    def close_all(self):
        """Cancel every live process (a deadlock): their cleanup runs now, before the run ends."""
        for p in list(self.procs):
            self.cancel(p)

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
            if self.abort:
                self.close_all()
                return True
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
    """Fixed results per node: no model, no processes. `calls` records every request.

    `root` only tells the interpreter where the org root is (for the TMPDIR check);
    `change` is what `evidence.change` reports (P28).
    """

    def __init__(self, steps=None, checks=None, judges=None, events=None, signed=None, outside=(), root=None, change=None):
        self.steps, self.checks, self.judges = dict(steps or {}), dict(checks or {}), dict(judges or {})
        self.events = list(events or [])
        self.signed = signed or (lambda e, signer: e.get("signature") == signer)
        self.outside = set(outside)
        self.root = root
        self._change = change or {"head": None, "worktree": None}
        self.calls = []
        self.last_rungs = None
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

    def verify_signed(self, event, signer):
        return bool(self.signed(event, signer))

    def confined(self, rel):
        return rel not in self.outside

    def change(self):
        return dict(self._change)

    def run_step(self, req):
        self.calls.append(("step", req.command, req.key))
        v, found = self._pick(self.steps, req.key, _lookup)
        if callable(v):
            v = v(req)
        if v is None:
            return StepOutcome()
        return v if isinstance(v, StepOutcome) else StepOutcome(**v)

    def run_check(self, name, key, evidence, rungs):
        self.calls.append(("check", name, key))
        self.last_rungs = rungs
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
    """Real argv exec (7.8): `agent-run`, or a file directly in `<root>/bin`; never a shell.

    A command or check script is opened once (`O_NOFOLLOW`), the descriptor's own path is
    compared with the root, and the program then runs from that descriptor, so a path
    swapped after the check changes nothing (2.2). `after_verify` is a test seam called
    between the check and the exec. Events and the clock stay virtual: this host runs
    commands and checks, it does not wait in real time for events.
    """

    def __init__(self, root, agent_run=None, events=(), verify=None, check_timeout=300, output_cap=OUTPUT_CAP):
        self.root = os.path.realpath(root)
        self.agent_run = agent_run
        self.events = list(events)
        self.verify = verify
        self.check_timeout = check_timeout
        self.output_cap = output_cap
        self.after_verify = None
        self.calls = []

    def scheduled_events(self):
        return list(self.events)

    def verify_signed(self, event, signer):
        return bool(self.verify(event, signer)) if self.verify else False  # default refuses

    def _fd_path(self, fd):
        if sys.platform == "darwin":
            import fcntl
            raw = fcntl.fcntl(fd, fcntl.F_GETPATH, b"\0" * 1024)
            return os.path.realpath(raw.split(b"\0", 1)[0].decode())
        return os.path.realpath(os.readlink(f"/proc/self/fd/{fd}"))

    def _open(self, rel, nofollow=False):
        """(state, fd, path): state is inside | outside | missing | invalid, from the opened descriptor."""
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
        if nofollow:
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(os.path.join(self.root, rel), flags)
        except (OSError, ValueError):
            return "missing", None, None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                return "invalid", None, None
            path = self._fd_path(fd)
        except (OSError, ValueError):
            os.close(fd)
            return "invalid", None, None
        if not (path == self.root or path.startswith(self.root + os.sep)):
            os.close(fd)
            return "outside", None, path
        return "inside", fd, path

    def confined(self, rel):
        state, fd, _ = self._open(rel)
        if fd is not None:
            os.close(fd)
        return state == "inside"

    def _verified(self, folder, name, ok_name, suffix=""):
        """Open `<folder>/<name><suffix>` for exec: a regular file directly in the folder, or None."""
        if not ok_name.fullmatch(name):
            return "missing", None, None
        state, fd, path = self._open(f"{folder}/{name}{suffix}", nofollow=True)
        if fd is not None and (os.path.dirname(path) != os.path.join(self.root, folder) or os.path.basename(path) != name + suffix):
            os.close(fd)
            return "invalid", None, path  # inside the root, but not a file directly in the folder
        return state, fd, path

    def _kill(self, proc):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            proc.kill()
        except OSError:
            pass
        proc.wait()

    def _read(self, f, cap):
        f.seek(0)
        raw = f.read(cap + 1)
        return raw[:cap].decode("utf-8", errors="replace"), len(raw) > cap

    def run_step(self, req):
        cmd = req.command
        fd = None
        if cmd == "agent-run":
            argv0 = [self.agent_run] if self.agent_run else []
            pass_fds = ()
        else:
            state, fd, path = self._verified("bin", cmd, CMD_NAME)
            argv0, pass_fds = [], ()
            if fd is not None:
                if self.after_verify:
                    self.after_verify()
                head = os.pread(fd, 512, 0)
                if head.startswith(b"#!"):
                    toks = head.split(b"\n", 1)[0][2:].decode("utf-8", errors="replace").split(None, 1)
                    if toks:
                        py = 1 if os.path.basename(toks[0]) == "env" and len(toks) > 1 else 0
                        if re.fullmatch(r"python[0-9.]*", os.path.basename(toks[py])):
                            toks.insert(py + 1, "-I")  # isolated: no cwd, no user site, no PYTHON* variables
                        argv0 = toks + [f"/dev/fd/{fd}"]
                else:
                    argv0 = [f"/dev/fd/{fd}"]
                pass_fds = (fd,)
        if not argv0:
            return StepOutcome(exit_code=127, error=f"run.shell.command: '{cmd}' is not agent-run or a file in bin/")
        env = {}
        if cmd != "agent-run":
            env.update({str(k): str(v) for k, v in (req.shell.get("environment") or {}).items()})
        env.update({"PATH": os.environ.get("PATH", ""), "ORG_ROOT": self.root, "ORG_RUN": req.run_id, "ORG_KEY": req.key})
        t0 = time.monotonic()
        out_f, err_f = tempfile.TemporaryFile(), tempfile.TemporaryFile()
        try:
            try:
                proc = subprocess.Popen(argv0 + req.argv[1:], stdin=subprocess.PIPE, stdout=out_f, stderr=err_f, env=env,
                                        cwd=self.root, start_new_session=True, pass_fds=pass_fds)
            except OSError as e:
                return StepOutcome(exit_code=127, error=f"cannot start: {e.strerror}")
            try:
                proc.communicate(json.dumps(req.input, default=str).encode(), timeout=req.limit)
            except subprocess.TimeoutExpired:
                self._kill(proc)
                return StepOutcome(exit_code=-9, duration=req.limit or 0, timed_out=True)
            dur = time.monotonic() - t0
            out, trunc = self._read(out_f, self.output_cap)
            err, _ = self._read(err_f, self.output_cap)
        finally:
            out_f.close()
            err_f.close()
            if fd is not None:
                os.close(fd)
        text = out.strip()
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = text
        error = None
        if proc.returncode != 0:
            error = (err.strip().splitlines() or [f"command exited {proc.returncode}"])[0]
        return StepOutcome(exit_code=proc.returncode, output=parsed, stdout=out, duration=dur, error=error, truncated=trunc)

    def run_check(self, name, key, evidence, rungs):
        tmp = os.path.realpath(tempfile.gettempdir())
        if tmp == self.root or tmp.startswith(self.root + os.sep):
            raise RuntimeError(f"temp directory '{tmp}' is inside the org root")
        state, fd, path = self._verified("checks", name, CHECK_NAME, ".py")
        if state == "outside":
            raise OutsideRoot(f"checks/{name}.py")
        if fd is None:
            return False
        try:
            if self.after_verify:
                self.after_verify()
            chunks, total = [], 0
            while True:
                chunk = os.pread(fd, 65536, total)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > 4_000_000:
                    return False
        finally:
            os.close(fd)
        source = b"".join(chunks)
        efd, epath = tempfile.mkstemp(prefix="org-evidence-", suffix=".json")
        try:
            with os.fdopen(efd, "w") as f:
                json.dump(evidence, f, default=str)
            env = {"PATH": os.environ.get("PATH", ""), "ORG_EVIDENCE": os.path.abspath(epath), "ORG_KEY": key,
                   "ORG_RUN": evidence["run"], "ORG_ALLOWED_RUNGS": ",".join(rungs)}
            try:
                proc = subprocess.Popen([sys.executable, "-I", "-c", CHECK_PRELUDE, path, key], env=env, cwd=self.root,
                                        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
            except OSError:
                return False
            try:
                proc.communicate(source, timeout=self.check_timeout)
            except subprocess.TimeoutExpired:
                self._kill(proc)
                return False
            return proc.returncode == 0  # 1 fail, 2 bad evidence (fail), anything else fail
        finally:
            os.unlink(epath)

    def change(self):
        """The VCS head and working tree of the org root (P28); head is None outside a git tree."""
        env = {"PATH": os.environ.get("PATH", "")}

        def git(*args):
            r = subprocess.run(["git", "-C", self.root, *args], capture_output=True, text=True, timeout=30, env=env)
            return r.stdout.strip() if r.returncode == 0 else None
        try:
            head, top = git("rev-parse", "HEAD"), git("rev-parse", "--show-toplevel")
        except (OSError, subprocess.TimeoutExpired):
            head = top = None
        return {"head": head, "worktree": top or self.root}

    def run_judge(self, req):
        return None  # the model judge is U12's agent-run; this host has no adapter for it


# ------------------------------------------------------------------ 5. the run


class _Sc:
    """Scope of a task list: key prefixes, loop variables, rework loops, cancel registries."""

    __slots__ = ("pathp", "relp", "idx", "iters", "loops", "lv", "regs", "outer", "fors", "base")

    def __init__(self, pathp="", relp="", idx=None, iters=(), loops=(), lv=None, regs=(), outer=(), fors=(), base=""):
        self.pathp, self.relp, self.idx, self.iters, self.loops = pathp, relp, idx, iters, loops
        self.lv, self.regs, self.outer, self.fors, self.base = lv or {}, regs, outer, fors, base

    def derive(self, **kw):
        new = _Sc(self.pathp, self.relp, self.idx, self.iters, self.loops, self.lv, self.regs, self.outer, self.fors, self.base)
        for k, v in kw.items():
            setattr(new, k, v)
        return new

    def child(self, t, idx=None, **kw):
        """Scope for the tasks inside task `t`; `idx` marks the iteration of a `for` without `while` (section 1).

        The direct body task of an iteration (`self.idx` set) becomes the base of the relative `$accepted` view.
        """
        kw.setdefault("base", t.rel + "/" if self.idx is not None else self.base)
        return self.derive(pathp=t.path + "/", relp=t.rel + "/", idx=idx, **kw)

    def with_vars(self, **names):
        return self.derive(lv=dict(self.lv, **names), idx=self.idx)


class _T:
    """One task occurrence: names, keys, scope."""

    def __init__(self, ex, name, task, sc):
        self.name, self.task, self.sc = name, task, sc
        self.path = sc.pathp + name
        self.rel = sc.relp + name + (f"#{sc.idx}" if sc.idx is not None else "")
        self.full = ex.prefix + self.rel
        self.kind = _tkey(task)
        org = (task.get("metadata") or {}).get("org")
        self.org = org if isinstance(org, dict) else {}
        self.floor = self.path in ex.floors
        self.sort = ex.sortbase + (ex.pre.get(self.path, 0),) + tuple(sc.iters)
        self.entry = None
        self.cls = None  # step | call | emit | gate
        self.consumed = []  # ids of task-ended events a gate consumed; released if the gate does not pass


class _Rec:
    """Last result of one key. status: pass | fail | handled | cancelled (6.1)."""

    def __init__(self, status, sort, base):
        self.status, self.sort, self.base = status, sort, base

    @property
    def ok(self):
        return self.status == "pass"


class _Loop:
    """A rework loop (`for` with `while`): its round, its unfinished detached work, its reject reasons."""

    def __init__(self, src, ex, base=""):
        self.src, self.ex, self.base, self.round = src, ex, base, 0
        self.serial = ex.run.nxt()
        self.procs, self.reasons, self.next = [], {}, {}


class _Ex:
    """One workflow execution: context, `$accepted`, task entries and decisions of the round."""

    def __init__(self, run, name, doc, prefix, sortbase, stack, parent=None, call_rel=None):
        self.run, self.name, self.doc, self.prefix, self.sortbase, self.stack = run, name, doc, prefix, sortbase, stack
        self.parent, self.call_rel = parent, call_rel
        self.serial = run.nxt()
        self.context, self.accepted, self.ent, self.dec = {}, {}, {}, {}
        self.pre = {p: i for i, (p, _) in enumerate(_walk(doc["do"]))}
        self.floors = {p for p, t in _walk(doc["do"]) if run.is_floor(t)}
        self.deadline = None


class _Run:
    def __init__(self, interp, rid):
        self.interp, self.host, self.rid = interp, interp.host, rid
        self.events, self.records, self.execs = [], {}, []
        self.detached_errors, self.inv, self.seq, self.iterations, self.serial = [], 0, 0, 0, 0
        self.fatal_errors = []
        self.scopes, self.tmp, self.nfile, self.ended = {}, None, 0, []
        self.consumed, self.internal, self.seen_decisions = {}, {}, set()
        self._floors = {}
        self.sched = _Scheduler(list(getattr(self.host, "scheduled_events", lambda: [])()))
        self.sched.on_event = lambda e: self.log("event", type=e.get("type") if isinstance(e, dict) else None, event=self.plain(e))

    # -- infrastructure

    def nxt(self):
        self.serial += 1
        return self.serial

    @staticmethod
    def plain(value):
        try:
            return json.loads(json.dumps(value, default=str))
        except (TypeError, ValueError, RecursionError):  # non-string keys, cycles
            return repr(value)[:10000]

    def log(self, kind, **kw):
        e = {"seq": len(self.events), "t": self.sched.now, "kind": kind}
        e.update(kw)
        self.events.append(e)

    def has_floors(self, name):
        """P35: a workflow has floors if it, or a workflow it can call, has one (cycle-safe, never a cached partial)."""
        if name in self._floors:
            return self._floors[name]
        seen, stack, found = set(), [name], False
        while stack and not found:
            n = stack.pop()
            doc = self.interp.workflows.get(n)
            if n in seen or doc is None:
                continue
            seen.add(n)
            for _, t in _walk(doc["do"]):
                org = (t.get("metadata") or {}).get("org")
                if isinstance(org, dict) and org.get("floor") is True:
                    found = True
                    break
                if isinstance(t.get("run"), dict) and isinstance(t["run"].get("workflow"), dict):
                    stack.append(t["run"]["workflow"].get("name"))
        self._floors[name] = found
        return found

    def is_floor(self, task):
        org = (task.get("metadata") or {}).get("org")
        if isinstance(org, dict) and org.get("floor") is True:
            return True
        run = task.get("run")
        return isinstance(run, dict) and isinstance(run.get("workflow"), dict) and self.has_floors(run["workflow"].get("name"))

    def vars(self, ex, sc, extra):
        v = dict(sc.lv)
        v.update(extra)
        v.update({"context": ex.context, "runtime": {"name": "ows-interpreter", "version": "0"},
                  "workflow": {"id": self.rid, "definition": {"document": ex.doc.get("document", {})}}})
        acc = ex.accepted
        if sc.base:  # inside an iteration the keys are also visible relative to its body (spec update 8)
            n = len(sc.base)
            acc = dict(acc)
            acc.update({k[n:]: val for k, val in ex.accepted.items() if k.startswith(sc.base)})
        v["accepted"] = acc  # bound last: nothing shadows it
        return v

    def x(self, ex, key, value, data, sc, **extra):
        try:
            return expr.resolve(value, data, self.vars(ex, sc, extra))
        except expr.ExprError as e:
            raise TaskError(key, E_EXPR, 400, str(e)) from None

    def hostcall(self, t, fn, *args, outside=False):
        """A host that raises is a located run error, never a traceback. ControlFlow passes through."""
        try:
            return fn(*args)
        except OutsideRoot as e:
            if outside:
                raise
            raise TaskError(t.full, E_RUNTIME, 500, f"'{e}' resolves outside the org root", fatal=True) from None
        except (TaskError, ControlFlow):
            raise
        except Exception as e:
            raise TaskError(t.full, E_RUNTIME, 500, f"host: {type(e).__name__}: {e}") from None

    def record(self, ex, t, status):
        ok = status == "pass"
        ex.accepted[t.rel] = ok
        node, key = ex, t.rel
        while node.parent is not None:  # D15: a caller sees callee keys as `<call key>><callee key>`
            key = node.call_rel + ">" + key
            node = node.parent
            node.accepted[key] = ok
        rec = self.records[t.full] = _Rec(status, t.sort, ex.prefix + t.path)
        self.log("accept", key=t.full, ok=ok, status=status)
        return rec

    def input_file(self, key, inp, reasons):
        """Runtime-owned task input file (7.8): private directory outside the org root, mode 0444."""
        if self.tmp is None:
            root = getattr(self.host, "root", None)
            base = os.path.realpath(tempfile.gettempdir())
            if root:
                r = os.path.realpath(root)
                if base == r or base.startswith(r + os.sep):
                    raise TaskError(key, E_RUNTIME, 500, f"input file directory '{base}' is inside the org root", fatal=True)
            self.tmp = tempfile.mkdtemp(prefix="org-run-")
        self.nfile += 1
        path = os.path.join(self.tmp, f"input-{self.nfile}.json")
        with open(path, "w") as f:
            json.dump({"run": self.rid, "key": key, "input": inp, "reasons": reasons}, f, default=str)
        os.chmod(path, 0o444)
        return path

    @staticmethod
    def reasons_of(sc):
        out = {}
        for loop in sc.loops:
            out.update(loop.reasons)
        return out

    def discard(self, ex, rel):
        """7.4 rule 2: remove the subtree of one loop task (its rel key), for the current iteration only."""
        pre = rel + "/"
        for table in (ex.accepted, ex.ent, ex.dec):
            for k in [k for k in table if k.startswith(pre)]:
                del table[k]
        node, p = ex, pre
        while node.parent is not None:
            p = node.call_rel + ">" + p
            node = node.parent
            for k in [k for k in node.accepted if k.startswith(p)]:
                del node.accepted[k]
        fp = ex.prefix + pre
        for k in [k for k in self.records if k.startswith(fp)]:
            del self.records[k]

    def change(self, t):
        return self.plain(self.hostcall(t, self.host.change))

    def rungs(self, t):
        role = t.org.get("role")
        if role == "owner":
            return RUNGS + ("frozen",)
        roles = (self.interp.manifest or {}).get("roles")
        entry = roles.get(role) if isinstance(roles, dict) else None
        listed = entry.get("rungs") if isinstance(entry, dict) else None
        if listed is None:
            return RUNGS[:2]
        valid = tuple(r for r in RUNGS if isinstance(listed, list) and r in listed)
        if not valid:  # an empty or all-invalid list is an error, never the default (N2)
            raise TaskError(t.full, E_RUNTIME, 500,
                            f"manifest.roles.{role}.rungs: must list at least one of {', '.join(RUNGS)}", fatal=True)
        return valid

    def evidence(self, ex, t, start_seq):
        """The 6.1 evidence file content: runtime-built from entries that ended before the task started."""
        steps = {k: e for k, (seq, e, cls, code) in ex.ent.items() if seq <= start_seq and code and cls != "gate"}
        outputs = {k: e for k, (seq, e, cls, code) in ex.ent.items() if seq <= start_seq}
        decisions = {k: d for k, (seq, d) in ex.dec.items() if seq <= start_seq}
        # entries are shared by reference and never mutated; the host serialises the file once
        return {"run": self.rid, "key": t.full, "output": t.entry, "steps": steps, "outputs": outputs,
                "decisions": decisions, "change": self.change(t)}

    def finish_entry(self, ex, t):
        if t.entry is not None:
            self.seq += 1
            ex.ent[t.rel] = (self.seq, t.entry, t.cls, t.org.get("by") == "code")

    # -- workflow and task lists

    def workflow(self, ex, inp, outer=(), regs=()):
        self.execs.append(ex)
        self.log("workflow-start", workflow=ex.name, prefix=ex.prefix)
        tmo = ex.doc.get("timeout")
        if isinstance(tmo, dict) and "after" in tmo:
            ex.deadline = self.sched.now + _secs(tmo["after"])
        sc = _Sc(regs=regs, outer=outer)
        data = inp
        wi = ex.doc.get("input")
        here = ex.prefix.rstrip(">") or ex.name
        if isinstance(wi, dict) and "from" in wi:
            data = self.x(ex, here, wi["from"], data, sc, input=data)
        out, _ = yield from self.tasks(ex, ex.doc["do"], sc, data)
        wo = ex.doc.get("output")
        if isinstance(wo, dict) and "as" in wo:
            out = self.x(ex, here, wo["as"], out, sc, output=out)
        return out

    def tasks(self, ex, lst, sc, data):
        names = [n for n, _ in _items(lst)]
        i = 0
        while i < len(lst):
            if self.fatal_errors:
                raise self.fatal_errors[0]  # a fatal error in detached work ends the run (review 2, 8)
            (name, task), = lst[i].items()
            out, d = yield from self.task(ex, name, task, sc, data)
            data = out
            if d in (None, "continue"):
                i += 1
            elif d in ("end", "exit"):
                return data, d
            elif d in names[i + 1:]:
                i = names.index(d, i + 1)
            else:
                raise TaskError(ex.prefix + sc.relp + name, E_RUNTIME, 500,
                                f"then: '{d}' is not a later task in the same list", fatal=True)
        return data, None

    def task(self, ex, name, task, sc, data):
        t = _T(ex, name, task, sc)
        data0 = data
        inp = task.get("input")
        if isinstance(inp, dict) and "from" in inp:
            data = data0 = self.x(ex, t.full, inp["from"], data, sc, input=data)
        if "if" in task and not _truthy(self.x(ex, t.full, task["if"], data, sc, input=data)):
            self.log("task-skip", key=t.full)
            return data, None
        self.log("task-start", key=t.full, path=t.path)
        sig, directive, k = None, None, t.kind
        try:
            if k == "do":
                out, sig = yield from self.tasks(ex, task["do"], sc.child(t), data)
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
        except (KeyError, TypeError, AttributeError, ValueError, IndexError) as e:  # a shape validation would have refused
            raise TaskError(t.full, E_RUNTIME, 500, f"malformed task: {type(e).__name__}: {e}", fatal=True) from None
        if isinstance(task.get("output"), dict) and "as" in task["output"]:
            out = self.x(ex, t.full, task["output"]["as"], out, sc, input=data0, output=out)
        if isinstance(task.get("export"), dict) and "as" in task["export"]:
            ex.context = self.x(ex, t.full, task["export"]["as"], out, sc, input=data0, output=out)
        self.log("task-end", key=t.full)
        if sig == "end":
            return out, "end"
        return out, directive or task.get("then")

    # -- control kinds

    def count_iteration(self, t):
        self.iterations += 1
        if self.iterations > MAX_ITERATIONS:
            raise TaskError(t.full, E_RUNTIME, 500, f"iteration cap: more than {MAX_ITERATIONS} for iterations in one run", fatal=True)

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
        loop = None
        if cond is not None:
            loop = _Loop(expr.unwrap(cond) if isinstance(cond, str) and expr.is_expression(cond) else None, ex, sc.base)
        loops = sc.loops + (loop,) if loop else sc.loops
        regs = sc.regs + (loop.procs,) if loop else sc.regs
        out = data
        fsr = self.nxt()
        for i, item in enumerate(items):
            self.count_iteration(t)
            lv = dict(sc.lv)
            lv[each], lv[at] = item, i
            if cond is not None:
                # while sees the previous round's results; only then are they discarded (7.4 rule 2)
                if not _truthy(self.x(ex, t.full, cond, data, sc.derive(loops=loops, lv=lv), input=data)):
                    break
                if i > 0:
                    self.new_round(ex, t, loop)
                loop.round = i
            isc = sc.child(t, idx=None if cond is not None else i, iters=sc.iters if cond is not None else sc.iters + (i,),
                           loops=loops, lv=lv, regs=regs, fors=sc.fors if cond is not None else sc.fors + ((fsr, i),))
            out, sig = yield from self.tasks(ex, task["do"], isc, data)
            if sig in ("end", "exit"):  # D12
                return out, ("end" if sig == "end" else None)
        return out, None

    def new_round(self, ex, t, loop):
        """7.4 rule 2: cancel earlier detached work, discard earlier results, keep reject reasons."""
        for p in list(loop.procs):
            self.sched.cancel(p)  # its keys record `cancelled`, it emits nothing
        loop.procs.clear()
        self.detached_errors = [x for x in self.detached_errors if not any(l is loop for l, _ in x[1])]
        loop.reasons, loop.next = loop.next, {}
        self.discard(ex, t.rel)

    def fork(self, ex, t, data):
        fk = t.task["fork"]
        compete = bool(fk.get("compete"))
        branches = fk.get("branches", [])
        lists = [[] for _ in branches]
        procs = []
        for b, lst in zip(branches, lists):
            sc = t.sc.child(t, regs=t.sc.regs + (lst,) if compete else t.sc.regs)
            procs.append(self.sched.spawn(self.branch(ex, b, sc, data)))
        try:
            return (yield Join(procs, compete))
        finally:
            if compete:  # S9: detached work started in a losing branch goes with it
                for proc, lst in zip(procs, lists):
                    if proc.cancelled:
                        for d in lst:
                            self.sched.cancel(d)

    def branch(self, ex, item, sc, data):
        out, _ = yield from self.tasks(ex, [item], sc, data)
        return out

    def try_(self, ex, t, data):
        task, sc = t.task, t.sc
        c = task.get("catch") or {}
        as_name = c.get("as", "error")
        retries, delay, total, per_attempt = 0, 0, 0, 0
        if "retry" in c:
            retry = c["retry"]
            lim = retry.get("limit") if isinstance(retry, dict) else None
            att = lim.get("attempt") if isinstance(lim, dict) else None
            count = att.get("count") if isinstance(att, dict) else None
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise TaskError(t.full, E_RUNTIME, 500, "catch.retry: needs limit.attempt.count, a positive integer", fatal=True)
            retries, delay = count, _secs(retry.get("delay"))  # D4
            total, per_attempt = _secs(lim.get("duration")), _secs(att.get("duration"))
        attempt, started, failed = 0, self.sched.now, []
        while True:
            saved = ex.deadline
            if per_attempt:
                dl = self.sched.now + per_attempt
                ex.deadline = dl if saved is None else min(saved, dl)
            try:
                out, sig = yield from self.tasks(ex, task["try"], sc.child(t), data)
                for key, rec in failed:  # a retry succeeded: the failures it replaced are handled
                    if self.records.get(key) is rec:
                        rec.status = "handled"
                return out, sig, None
            except TaskError as e:
                if e.fatal or not self.catches(ex, t, c, as_name, e, data):
                    raise
                failed.extend(e.failed)
                if attempt < retries and not (total and self.sched.now + delay - started > total):
                    attempt += 1
                    self.log("retry", key=t.full, attempt=attempt)
                    if delay:
                        yield Sleep(self.sched.now + delay)
                    continue
                self.log("caught", key=t.full, error=e.text)
                out, sig = data, None
                if isinstance(c.get("do"), list):
                    out, sig = yield from self.tasks(ex, c["do"], sc.child(t).with_vars(**{as_name: e.obj()}), data)
                for key, rec in failed:  # the catch completed: `handled` (6.1)
                    if self.records.get(key) is rec:
                        rec.status = "handled"
                return out, sig, c.get("then") or task.get("then")
            finally:
                ex.deadline = saved

    def catches(self, ex, t, c, as_name, e, data):
        flt = ((c.get("errors") or {}).get("with")) or {}
        obj = e.obj()
        for k, v in flt.items():
            if obj.get(k) != v:
                return False
        sc = t.sc.with_vars(**{as_name: obj})
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
            owner = any(isinstance(i, dict) and "rubric" in i and i.get("judge") == "owner" for i in t.org.get("acceptance") or [])
            lim = OWNER_RUBRIC_LIMIT if owner else STEP_LIMIT  # 7.10, P34
        else:
            return None if ex.deadline is None else ex.deadline
        dl = self.sched.now + lim
        return dl if ex.deadline is None else min(dl, ex.deadline)

    def leaf(self, ex, t, data):
        run = t.task.get("run")
        if t.kind == "run" and isinstance(run, dict) and run.get("await", True) is False:
            proc = self.sched.spawn(self.detached(ex, t, data))  # 7.11: completes at once
            for reg in t.sc.regs:
                reg.append(proc)
            return data
        return (yield from self.body(ex, t, data))

    def scope_of(self, ex, t):
        return (ex.serial, t.sc.fors, tuple((loop.serial, loop.round) for loop in t.sc.loops))

    def detached(self, ex, t, data):
        scope = self.scope_of(ex, t)
        try:
            yield from self.body(ex, t, data)
        except TaskError as e:
            if e.fatal:  # never dropped by a new round: the run ends
                self.fatal_errors.append(e)
                self.sched.abort = True
                return
            self.detached_errors.append((e, tuple((loop, loop.round) for loop in t.sc.loops + t.sc.outer)))
        rec = self.records.get(t.full)
        ev = {"type": TASK_ENDED, "data": {"run": self.rid, "task": t.full, "accepted": bool(rec and rec.ok)}}
        self.scopes[id(ev)] = (ev, scope)
        self.internal[id(ev)] = ev
        self.ended.append(ev)
        self.sched.publish(ev)

    def body(self, ex, t, data):
        deadline = self.limit(ex, t)
        start_seq = self.seq
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
            results = yield from self.items(ex, t, deadline, decision, start_seq)
        except TaskError as e:
            self.release(t)
            self.finish_entry(ex, t)
            e.failed.append((t.full, self.record(ex, t, "fail")))  # a raised error records fail (6.1)
            raise
        except GeneratorExit:
            self.release(t)
            self.record(ex, t, "cancelled")
            raise
        self.finish_entry(ex, t)
        ok = "fail" not in results and decision != "reject"
        if not ok:
            self.release(t)
        self.record(ex, t, "pass" if ok else "fail")
        if not ok and t.floor and not self.exempt(t):
            raise TaskError(t.full, E_RUNTIME, 500, "acceptance failed")  # 7.4 rule 1
        return out

    def release(self, t):
        """A gate that timed out, failed or was cancelled gives its consumed events back to the pool."""
        for i in t.consumed:
            self.consumed.pop(i, None)
        t.consumed = []

    def exempt(self, t):
        """7.4 rule 1: a rework loop whose `while` names this task's key reads the result, so a fail does not raise."""
        for loop in t.sc.loops:
            if not loop.src:
                continue
            keys = expr.accepted_keys(loop.src)
            if t.rel in keys or (loop.base and t.rel.startswith(loop.base) and t.rel[len(loop.base):] in keys):
                return True
        for loop in t.sc.outer:  # a callee floor is named by its full key from the caller (P36)
            if loop.src and t.full[len(loop.ex.prefix):] in expr.accepted_keys(loop.src):
                return True
        return False

    def timeout(self, t):
        return TaskError(t.full, E_TIMEOUT, 408, "timeout")

    def step(self, ex, t, data, deadline):
        t.cls = "step"
        shell = t.task["run"]["shell"]
        cmd = shell.get("command")
        args = list(shell.get("arguments") or [])
        org = t.org
        argv = [cmd] + args
        role = brief = ""
        network = None
        input_file = ""
        fatal = lambda text: TaskError(t.full, E_RUNTIME, 500, text, fatal=True)  # noqa: E731
        if cmd == "agent-run":
            role, brief = org.get("role"), org.get("brief")
            if not role:
                raise fatal("metadata.org.role: required for agent-run")
            if role == "owner":
                raise fatal("metadata.org.role: agent-run may not run as owner")
            if org.get("by") == "code":
                raise fatal("metadata.org.by: agent-run may not run as by code")  # agent output must not enter evidence
            bad = self.flag_error(args)
            if bad:
                raise fatal(bad)
            for k in ("environment", "stdin", "directory"):
                if k in shell:
                    raise fatal(f"run.shell.{k}: not allowed on agent-run; the runtime sets it")
            if not brief:
                raise fatal("metadata.org.brief: required for agent-run")
            if not self.hostcall(t, self.host.confined, brief):
                raise fatal(f"metadata.org.brief: '{brief}' resolves outside the org root")
            argv += ["--role", role, "--brief", brief]
            network = org.get("network")
            if network is not None:
                if not isinstance(network, str):
                    raise fatal("metadata.org.network: must be a string")
                argv += ["--network", network]
            input_file = self.input_file(t.full, data, self.reasons_of(t.sc))
            argv += ["--input", input_file]
        else:
            env = shell.get("environment")
            for name in (env.keys() if isinstance(env, dict) else ()):
                if not ENV_NAME.fullmatch(str(name)) or str(name).startswith(("LD_", "DYLD_")):
                    raise fatal(f"run.shell.environment: '{name}' is not an allowed name")
        now = self.sched.now
        req = StepRequest(key=t.full, rel=t.rel, path=t.path, command=cmd, arguments=args, argv=argv, role=role or org.get("role", ""),
                          brief=brief or org.get("brief", ""), by=org.get("by", ""), input=data,
                          limit=None if deadline is None else max(deadline - now, 0), run_id=self.rid,
                          accepted=dict(ex.accepted), shell=shell, network=network, input_file=input_file)
        self.log("step", key=t.full, command=cmd)
        o = self.hostcall(t, self.host.run_step, req)
        dur = o.duration or 0
        if o.timed_out or (deadline is not None and now + dur > deadline):
            if deadline is not None:
                yield Sleep(deadline)
            raise self.timeout(t)
        if dur > 0:
            yield Sleep(now + dur)
        text = o.stdout if o.stdout is not None else (o.output if isinstance(o.output, str) else
                                                      ("" if o.output is None else json.dumps(o.output, default=str)))
        text, truncated = str(text), o.truncated
        if len(text) > OUTPUT_CAP:  # the cap holds for every host
            text, truncated = text[:OUTPUT_CAP], True
        t.entry = {"exit": o.exit_code, "stdout": text}
        if truncated:
            t.entry["truncated"] = True
        if o.exit_code != 0 or o.error:
            raise TaskError(t.full, E_RUNTIME, 500, str(o.error) if o.error else f"command exited {o.exit_code}")
        return o.output

    @staticmethod
    def flag_error(args):
        """7.8: an agent-run step may carry only --isolated, once."""
        seen = 0
        for a in args:
            flag = a.split("=", 1)[0] if isinstance(a, str) and a.startswith("--") else None
            if a == "--isolated":
                seen += 1
                if seen > 1:
                    return "run.shell.arguments: --isolated given more than once"
            elif flag in ("--role", "--brief", "--network"):
                return f"run.shell.arguments: {flag} is set by the runtime from metadata.org; remove it"
            elif flag == "--input":
                return "run.shell.arguments: --input is set by the runtime from the task input; remove it"
            else:
                return f"run.shell.arguments: '{a}' is not an allowed agent-run flag (allowed: --isolated)"
        return None

    def call(self, ex, t, data):
        t.cls = "call"
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
        child = _Ex(self, name, target, t.full + ">", t.sort, ex.stack + (name,), parent=ex, call_rel=t.rel)
        try:
            out = yield from self.workflow(child, inp, outer=t.sc.outer + t.sc.loops, regs=t.sc.regs)
        except TaskError:
            t.entry = {"exit": 1, "stdout": ""}
            raise
        pre = t.full + ">"
        failed = any(k.startswith(pre) and r.status == "fail" for k, r in self.records.items())
        t.entry = {"exit": 1 if failed else 0, "stdout": ""}
        return out

    def emit(self, ex, t, data):
        t.cls = "emit"
        ev = self.x(ex, t.full, t.task["emit"]["event"]["with"], data, t.sc, input=data)
        if not isinstance(ev, dict):
            raise TaskError(t.full, E_RUNTIME, 500, "emit.event.with: must resolve to a map", fatal=True)
        ev = dict(ev)
        for prefix in RESERVED_PREFIXES:
            if str(ev.get("type")).startswith(prefix):
                raise TaskError(t.full, E_RUNTIME, 500,
                                f"emit.event.with.type: '{ev['type']}' uses the reserved prefix {prefix}", fatal=True)
        d = ev.get("data")
        d = dict(d) if isinstance(d, dict) else ({} if d is None else {"value": d})
        d["run"] = self.rid  # D3
        ev["data"] = d
        t.entry = {"exit": 0, "stdout": json.dumps(d, default=str)}
        self.log("emit", key=t.full, event=self.plain(ev))
        self.internal[id(ev)] = ev  # S3: an internal event never reaches a decision gate
        self.sched.publish(ev)
        return data

    # -- gates and decision events

    def decision_test(self, event, full, item=None, signer="owner"):
        """Content first, so a foreign event never reaches the verifier; then the signature; then once-only by id (P33)."""
        if id(event) in self.internal:
            return None, "emitted by the runtime"
        d = event.get("data") if isinstance(event.get("data"), dict) else {}
        if d.get("run") != self.rid:
            return None, "data.run is not this run"
        if d.get("task") != full:
            return None, f"data.task is not '{full}'"
        if item is not None and d.get("item") != item:
            return None, f"data.item is not {item}"
        if d.get("decision") not in ("approve", "reject"):
            return None, "data.decision must be approve or reject"
        if "reason" in d and not isinstance(d["reason"], str):
            return None, "data.reason must be a string"
        eid = event.get("id")
        if not isinstance(eid, str) or not eid:
            return None, "event has no id"
        if not self.host.verify_signed(event, signer):  # the matcher guard turns a host error into the gate's error
            return None, f"not signed by the {signer}"
        if eid in self.seen_decisions:
            return None, "decision event already consumed"
        self.seen_decisions.add(eid)
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

    def guard(self, t, matcher):
        """Any error in a matcher (filters, correlate, until, the verifier) is the gate's own run error."""
        def guarded(event):
            if not isinstance(event, dict):
                return None
            try:
                return matcher(event)
            except (TaskError, ControlFlow):
                raise
            except Exception as e:
                raise TaskError(t.full, E_RUNTIME, 500, f"event filter failed: {type(e).__name__}: {e}") from None
        return guarded

    def listen(self, ex, t, data, deadline):
        t.cls = "gate"
        to = t.task["listen"]["to"]
        items = t.org.get("acceptance") or []
        decision_gate = (t.org.get("role") == "owner" or "signer" in t.org
                         or any(isinstance(i, dict) and "human" in i for i in items))
        signer = t.org.get("signer", "owner")  # 7.5, P18
        mode = "one" if "one" in to else "any" if "any" in to else "all"
        raw = [to["one"]] if mode == "one" else list(to[mode])
        flts = [(self.x(ex, t.full, f.get("with") or {}, data, t.sc, input=data), f.get("correlate")) for f in raw]
        until = to.get("until")
        full, hits, got, expect = t.full, set(), [], {}
        scope = (ex.serial, t.sc.fors, tuple((loop.serial, loop.round) for loop in t.sc.loops))

        def done(v):
            return (v,)

        if decision_gate:
            def matcher(event):
                if not any(self.flt_match(w, event) for w, _ in flts):
                    return None
                dec, why = self.decision_test(event, full, signer=signer)
                if why:
                    self.ignore(full, event, why)
                    return None
                return done((dec, event))
        else:
            def matcher(event):
                idxs, warned = [], False
                for idx, (w, corr) in enumerate(flts):
                    if not self.flt_match(w, event):
                        continue
                    if event.get("type") == TASK_ENDED and (not self.in_scope(event, scope) or id(event) in self.consumed):
                        continue
                    if corr:
                        if not self.correlated(ex, t, corr, event, expect, data):
                            continue
                    elif (event.get("data") or {}).get("run") != self.rid:
                        if not warned:
                            self.ignore(full, event, "data.run is not this run")
                            warned = True
                        continue
                    idxs.append(idx)
                if not idxs:
                    return None
                got.append(event)  # once, however many filters it matches
                hits.update(idxs)
                if event.get("type") == TASK_ENDED:
                    self.consumed[id(event)] = (event, full)  # D11: once per run, released if this gate does not pass
                    t.consumed.append(id(event))
                if mode == "one":
                    return done((event, None))
                if mode == "all":
                    return done((list(got), None)) if len(hits) == len(flts) else None
                if until is None or self.until_holds(ex, t, until, got, data):  # D2
                    return done((list(got), None))
                return None

            if until is not None and self.until_holds(ex, t, until, [], data):  # 7.5: once, before the first event
                t.entry = {"exit": 0, "stdout": "[]"}
                return [], None
        matcher = self.guard(t, matcher)
        if not decision_gate and any(w.get("type") == TASK_ENDED for w, _ in flts):
            for ev in list(self.ended):  # D11: replay what ended before the gate listened
                r = matcher(ev)
                if r is not None:
                    t.entry = {"exit": 0, "stdout": json.dumps(self.plain(r[0][0]))}
                    return r[0]
        try:
            value = yield WaitEvent(matcher, deadline)
        except WaitTimeout:
            raise self.timeout(t) from None
        if decision_gate:
            verdict, event = value
            t.entry = {"exit": 0, "stdout": json.dumps([self.plain(event)])}
            self.seq += 1
            ex.dec[t.rel] = (self.seq, {"decision": verdict, "signer_role": signer, "signature_verified": True,
                                        "run": self.rid, "task": t.full, "head": self.change(t).get("head")})
            if verdict == "reject":
                reason = (event.get("data") or {}).get("reason")
                if reason is not None:
                    for loop in t.sc.loops:
                        loop.next[t.rel] = reason  # for the next round's input file (7.4 rule 2)
                if not self.exempt(t):
                    raise TaskError(full, E_RUNTIME, 500, "decision rejected")
                return event, "reject"  # P21: a rework loop reads the gate; the fail is recorded, the loop decides
            return event, "approve"
        t.entry = {"exit": 0, "stdout": json.dumps(self.plain(value[0]))}
        return value[0], None

    def until_holds(self, ex, t, until, got, data):
        """Evaluate a counted `until` with `$events` bound to what the gate has consumed (7.5)."""
        ok = _truthy(self.x(ex, t.full, until, list(got), t.sc, input=data, events=list(got)))
        tasks = [e["data"].get("task") for e in got if isinstance(e.get("data"), dict)]
        self.log("until", key=t.full, events=len(got), result=ok, tasks=tasks)
        return ok

    def in_scope(self, event, scope):
        """A join consumes task-ended events of its own workflow execution, `for` iteration and rework round."""
        entry = self.scopes.get(id(event))
        if entry is None or entry[0] is not event:
            return False
        exid, fors, loops = entry[1]
        gate_ex, gate_fors, gate_loops = scope
        return exid == gate_ex and fors[:len(gate_fors)] == gate_fors and loops[:len(gate_loops)] == gate_loops

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

    def items(self, ex, t, deadline, decision, start_seq):
        results = []
        evidence = None
        for idx, item in enumerate(t.org.get("acceptance") or []):
            if "check" in item:
                kind = "check"
                if evidence is None:
                    evidence = self.evidence(ex, t, start_seq)
                rungs = self.rungs(t)
                try:
                    ok = self.hostcall(t, self.host.run_check, item["check"], t.full, evidence, rungs, outside=True)
                    r = "pass" if ok else "fail"
                except OutsideRoot as e:
                    raise TaskError(t.full, E_RUNTIME, 500,
                                    f"metadata.org.acceptance[{idx}].check: '{e}' resolves outside the org root", fatal=True)
            elif "rubric" in item:
                kind = "rubric"
                if evidence is None and item.get("judge") != "owner":
                    evidence = self.evidence(ex, t, start_seq)
                r = yield from self.rubric(ex, t, idx, item, deadline, evidence)
            else:
                kind = "human"
                r = "pass" if decision == "approve" else "fail"
            self.log("item", key=t.full, index=idx, item=kind, result=r)
            results.append(r)
        return results

    def rubric(self, ex, t, idx, item, deadline, evidence):
        sample = item.get("sample", 1)
        h = int.from_bytes(hashlib.sha256(f"{self.rid}\n{t.full}\n{idx}".encode()).digest()[:8], "big")
        if not drawn(h, sample):
            return "pending"
        if item["judge"] == "owner":
            full = t.full
            tmo = t.task.get("timeout")
            if deadline is None and not (isinstance(tmo, dict) and "after" in tmo):  # 6.1: no task limit at all, wait 7 days
                deadline = self.sched.now + OWNER_RUBRIC_LIMIT
                if ex.deadline is not None:
                    deadline = min(deadline, ex.deadline)

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
                dec = yield WaitEvent(self.guard(t, matcher), deadline)
            except WaitTimeout:
                raise self.timeout(t) from None
            return "pass" if dec == "approve" else "fail"
        if not self.hostcall(t, self.host.confined, item["rubric"]):
            raise TaskError(t.full, E_RUNTIME, 500,
                            f"metadata.org.acceptance[{idx}].rubric: '{item['rubric']}' resolves outside the org root", fatal=True)
        self.inv += 1
        path = self.input_file(t.full, {"item": idx, "output": t.entry, "evidence": evidence}, {})
        req = JudgeRequest(key=t.full, item=idx, role=item["judge"], rubric=item["rubric"], run_id=self.rid,
                           invocation=f"{self.rid}:{self.inv}", input_file=path,
                           argv=["agent-run", "--role", item["judge"], "--brief", item["rubric"], "--input", path])
        reply = self.hostcall(t, self.host.run_judge, req)
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
        by_base = {}
        for k, r in self.records.items():
            by_base.setdefault(r.base, []).append((k, r))
        for ex in self.execs:
            for path in sorted(ex.floors, key=lambda p: ex.pre.get(p, 0)):
                base = ex.prefix + path
                recs = by_base.get(base, [])
                if not recs:
                    errs.append((ex.sortbase + (ex.pre.get(path, 0),), f"{base}: floor-not-run"))
                for k, r in recs:  # a floor must pass: handled and cancelled never count for one (S1)
                    if r.status != "pass":
                        errs.append((r.sort, f"{k}: acceptance failed"))
        for key, r in self.records.items():
            if r.status == "fail":  # handled and cancelled keys are skipped (7.4 rule 3)
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
        try:
            finished = self.sched.run()
            if not finished:
                self.sched.close_all()  # cleanup logs here, before run-end
        finally:
            if self.tmp:
                shutil.rmtree(self.tmp, ignore_errors=True)
        errors, objects = [], []
        if main.error is not None:
            errors.append(main.error.text)
            objects.append(main.error.obj())
        for e in self.fatal_errors + [x for x, _ in self.detached_errors]:
            if e.text not in errors:
                errors.append(e.text)
                objects.append(e.obj())
        if main.error is None and not self.fatal_errors:
            if not finished:
                errors.append("deadlock: tasks are waiting and nothing can wake them")
            for text in self.accounting():
                if text not in errors:
                    errors.append(text)
        status = "error" if errors else "success"
        self.log("run-end", status=status)
        return RunResult(status=status, errors=errors, error_objects=objects, events=list(self.events),
                         accepted=dict(root.accepted), records={k: r.ok for k, r in self.records.items()},
                         statuses={k: r.status for k, r in self.records.items()},
                         run_id=self.rid, output=main.result, context=root.context, now=self.sched.now)


# ------------------------------------------------------------------ 6. public interface


class Interpreter:
    """Runs workflows from `workflows` (name to parsed OWS document) against a host.

    With `catalog` and `manifest` (both or neither) every workflow also passes
    `validate_org` before the first task, and the manifest supplies each role's rungs.
    Without them only the built-in subset gate runs; the runtime floor accounting
    still holds either way.
    """

    def __init__(self, workflows, host, catalog=None, manifest=None):
        if (catalog is None) != (manifest is None):
            raise ValueError("catalog and manifest must be given together or not at all")
        if not callable(getattr(host, "change", None)) or not hasattr(host, "root"):
            raise ValueError("host must provide change() and root")
        self.workflows, self.host = workflows, host
        self.catalog, self.manifest = catalog, manifest

    def refusals(self, name):
        if name not in self.workflows:
            return [f"run refused: {name}: workflow is not loaded"]
        errs = []
        for n in [name] + [n for n in self.workflows if n != name]:
            doc = self.workflows[n]
            found = _subset_errors(doc)
            if not found and self.catalog is not None:
                found = validate_org.validate_org(doc, self.catalog, self.manifest)
            errs += [f"run refused: {n}: {e}" for e in found]
        return errs

    def run(self, name, input=None, run_id=None):
        if run_id is not None and not (isinstance(run_id, str) and RUN_ID.fullmatch(run_id)):
            raise ValueError("run id must match [A-Za-z0-9-]{8,64}")
        rid = run_id or secrets.token_hex(16)  # 128 random bits, 32 hex digits
        errs = self.refusals(name)
        if errs:
            return RunResult(status="refused", errors=errs, run_id=rid)
        return _Run(self, rid).execute(name, input)
