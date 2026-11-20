"""Organization command line (U19): run the organization on one machine.

Standard library only, plus the sibling modules `org_runtime` (U13b, public API) and `dispatcher` (U18).

  org.py serve  --root DIR --state DIR --inbox DIR [--once] [--poll SECONDS]
  org.py emit   --inbox DIR --type T [--data JSON] [--id ID] [--source S]
  org.py status --state DIR [--json]

`serve` reads event files from the inbox (the hardened `InboxFeed`: O_NOFOLLOW, size cap, strict JSON), hands each
to the `Dispatcher`, and runs every started workflow through `OrgRuntime` with `OrgProcessHost`. Decision events
(types `org.owner-` and `org.task-`) arrive through the same inbox as signed files. A run waiting at a gate polls
the inbox for them while it waits, so a decision that arrives later wakes the gate.

State directory layout: `ledger.key` (mode 0600, owned by the user, at least 32 bytes), `keys/` (public key lines
`<role> <public key>`), `snapshots/` (the owner-signed snapshot chain), `dispatcher.json`, `ledgers/`, `sessions/`
and `serve.lock`. The org root must hold `stack.yaml` or `stack.json`. `serve` refuses to start without them, with
a located message: there is no unenforced mode.

Exit codes: serve 0 ok, 1 a run ended in error (every run is still processed), 2 usage, a refused start or a run
the runtime refused (a refused root); emit 0 or 2; status 0 or 2.

PROVISIONAL choices (the spec and the brief are silent; listed in the unit report):
  - an inbox file is moved to `.seen` after the run it started is journaled, and to `.rejected` when it cannot be
    read, is an unsigned or foreign decision, or the dispatcher refuses it;
  - a decision file must verify against some role of the key ring, else it is moved to `.rejected` at once; a
    verified one is delivered only to the run it names (`data.run`) and otherwise stays in the inbox;
  - a signal ends `serve` after the current delivery. A run waiting at a gate is part of that delivery and ends
    at the gate's timeout; a run cut off by a crash is not resumed by `serve`;
  - `--once` takes polls until one finds no start event; a gate that nobody decides ends at its timeout;
  - the frozen-outside list of the repository is not enforced (the CLI has no repository root);
  - `emit` takes a JSON object for `--data`.

Frozen-outside protection (spec 13.1): `serve` enforces the runtime's default frozen-outside list against `--repo`
(default: the git top level of the org root, found by walking up to a `.git`). With no repository and no `--repo`
it refuses to start. The only way to run without it is `--no-outside-check`: a warning goes to stderr and the
dispatcher state records `"outside_check": "disabled"`.

Restart: at startup `serve` resumes every dispatcher pair left "starting" (a crash after the state write) with
`OrgRuntime.resume`, instead of reporting a redelivered event as a duplicate. A pair whose ledger is missing or does
not verify is reported (exit 1) and left as it is: not resumed and not started again. The events a resumed run
emitted are not dispatched again.

A run the runtime refused (a changed root with no new signed snapshot, for example) is marked done by the dispatcher,
so the same event id never starts it again. After the owner fixes the root, emit the event again with a new id
(`emit --id`). `status` prints the refusal reason of such a pair.
"""

import argparse
import hashlib
import json
import os
import secrets
import signal
import stat
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dispatcher as dp  # noqa: E402
import org_runtime as ort  # noqa: E402

try:
    import fcntl
except ImportError:  # pragma: no cover - non-posix
    fcntl = None

__all__ = ("main", "build_host", "Refused")

STATE_FILE = "dispatcher.json"
LOCK_FILE = "serve.lock"
KEY_FILE = "ledger.key"
STACK_FILES = ("stack.yaml", "stack.json")
NO_LIMIT = 10**9


class Refused(Exception):
    """A start condition does not hold. The message names the file."""


def _say(text, stream=None):
    print(text, file=stream or sys.stdout, flush=True)


# ---------------------------------------------------------------- start conditions


def _read_ledger_key(state):
    path = os.path.join(state, KEY_FILE)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    except OSError as e:
        raise Refused(f"{path}: cannot open the ledger key: {e.strerror}") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise Refused(f"{path}: the ledger key must be a regular file")
        if st.st_mode & 0o077:
            raise Refused(f"{path}: the ledger key must have mode 0600 (it has {stat.S_IMODE(st.st_mode):04o})")
        if hasattr(os, "getuid") and st.st_uid != os.getuid():
            raise Refused(f"{path}: the ledger key must belong to the user who runs serve")
        key = os.read(fd, 65536)
    finally:
        os.close(fd)
    if len(key) < ort.MIN_KEY:
        raise Refused(f"{path}: the ledger key must be at least {ort.MIN_KEY} bytes (it has {len(key)})")
    return key


def _load_ring(state, verifier):
    keys = os.path.join(state, "keys")
    if not os.path.isdir(keys):
        raise Refused(f"{keys}: no key directory: put the public keys there, one `<role> <public key>` per line")
    chunks = []
    for name in sorted(os.listdir(keys)):
        if name.startswith("."):
            continue
        path = os.path.join(keys, name)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError as e:
            raise Refused(f"{path}: cannot read the key file: {e.strerror}") from None
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Refused(f"{path}: a key file must be a regular file")
            chunks.append(os.read(fd, 1_000_000).decode("utf-8"))
        except UnicodeDecodeError:
            raise Refused(f"{path}: the key file is not UTF-8 text") from None
        finally:
            os.close(fd)
    try:
        ring = ort.load_ring("\n".join(chunks), verifier=verifier)
    except (ort.OwnerKeyError, ValueError) as e:
        raise Refused(f"{keys}: {e}") from None
    if not ring.list():
        raise Refused(f"{keys}: no public key found: the key ring is empty")
    return ring


def build_host(root, session_dir, env=None):
    """The process host. Only `ORG_*` variables reach it: the harness is chosen by the environment (U12), and the
    scripted harness answers only when the caller set `ORG_TEST_HARNESS=1`."""
    env = os.environ if env is None else env
    return ort.OrgProcessHost(root, session_dir, env={k: v for k, v in env.items() if k.startswith("ORG_")})


# ---------------------------------------------------------------- the inbox


class _Inbox(ort.InboxFeed):
    """The hardened `InboxFeed`, split in two by event type.

    mode "start": delivers ordinary events to the serve loop; a decision file that verifies is left for the run.
    mode "decision": delivers verified decision files that name the bound run to a run waiting at a gate.
    In both modes a file that cannot be read, or a decision no key of the ring signed, is moved to `.rejected`.
    """

    def __init__(self, path, mode, ring, key, poll_limit=100):
        super().__init__(path, max_per_poll=poll_limit, max_total=NO_LIMIT)
        self.mode, self.ring, self.key = mode, ring, key
        self.items, self._ledger, self._run, self._skip = [], None, None, {}

    def bind(self, ledger_path):
        self._ledger, self._run = ledger_path, None
        self._skip.clear()  # a new run may be the one a left decision names

    def _run_id(self):
        if self._run is None and self._ledger and os.path.exists(self._ledger):
            try:
                entries = ort.RunLedger(self._ledger, self.key, readonly=True).read()
                self._run = entries[0]["body"]["run_id"] if entries else None
            except (ort.LedgerError, OSError, ValueError, KeyError, TypeError):
                self._run = None
        return self._run

    def _signed(self, event):
        return any(self.ring.verify(event, role) for role in self.ring.list())

    def _reject(self, name, path, why):
        self.rejected.append(f"{name}: {why}")
        try:
            os.replace(path, path[:-5] + ".rejected")
        except OSError:
            pass

    def poll(self):
        out, self.items = [], []
        try:
            names = sorted(os.listdir(self.dir))
        except OSError as e:
            self.rejected.append(f"{self.dir}: {e.strerror}")
            return out
        self._skip = {p: k for p, k in self._skip.items() if os.path.basename(p) in names}
        for name in names:
            if not name.endswith(".json"):
                continue
            if len(out) >= self.max_per_poll:
                break
            path = os.path.join(self.dir, name)
            try:
                st = os.lstat(path)
            except OSError:
                continue
            stamp = (st.st_mtime_ns, st.st_size)
            if self._skip.get(path) == stamp:  # left here before and unchanged: no new read, no new verification
                continue
            try:
                event = self._load(path)
            except Exception as e:  # noqa: BLE001  every escape is a rejected file, never a crash
                self._reject(name, path, f"{type(e).__name__}: {e}")
                continue
            etype = event.get("type")
            if isinstance(etype, str) and etype.startswith(dp.RESERVED_PREFIXES):
                if not self._signed(event):
                    self._reject(name, path, "decision event is not signed by any key of the ring")
                    continue
                data = event.get("data")
                run = data.get("run") if isinstance(data, dict) else None
                if not isinstance(run, str):
                    self._reject(name, path, "decision event does not name a run")
                    continue
                if self.mode == "start" or run != self._run_id():
                    if self.mode == "start" or self._run is not None:
                        self._skip[path] = stamp
                    continue
            elif self.mode == "decision":
                self._skip[path] = stamp
                continue
            self._pending.append(path)
            self.items.append((path, event))
            out.append(event)
        return out

    @staticmethod
    def ack_path(path, suffix):
        try:
            os.replace(path, path[:-5] + suffix)
        except OSError:
            pass


class _LiveRun:
    """What the dispatcher calls: runs the workflow with the decision feed, so a gate hears the inbox."""

    def __init__(self, runtime, feed, ledger_path):
        self.runtime, self.feed, self.ledger_path = runtime, feed, ledger_path

    def run(self, name, input=None, **_):
        self.feed.bind(self.ledger_path)
        return self.runtime.run(name, input=input, feed=self.feed)

    def resume(self):
        self.feed.bind(self.ledger_path)
        return self.runtime.resume(feed=self.feed)


# ---------------------------------------------------------------- state patches (the dispatcher's own file)


def _patch_state(state_file, patch):
    """Apply `patch(state)` to the dispatcher state under the dispatcher's own lock; same shape, atomic replace."""
    lock = open(state_file + ".lock", "a")
    try:
        if fcntl is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with open(state_file, encoding="utf-8") as f:
                st = json.load(f)
        except FileNotFoundError:
            st = {"pairs": {}, "starts": {}, "refusals": []}
        patch(st)
        tmp = state_file + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(st, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, state_file)
    finally:
        lock.close()


def _finish_pair(state_file, key, res):
    def patch(st):
        pair = st["pairs"].setdefault(key, {})
        pair.update(state="done", run_id=res.run_id, status=res.status)
        if res.status != "success" and res.errors:
            pair["reason"] = "; ".join(res.errors)
    _patch_state(state_file, patch)


def _frozen(args, root):
    """(FrozenOutside, disabled) from `--repo`, the git top level of the root, or `--no-outside-check`."""
    if args.no_outside_check:
        _say("org: warning: the outside check is off: files outside the org root are not compared with the "
             "signed snapshot", sys.stderr)
        return ort.NO_OUTSIDE, True
    repo = args.repo
    if repo is None:
        here = os.path.realpath(root)
        while not os.path.lexists(os.path.join(here, ".git")):
            parent = os.path.dirname(here)
            if parent == here:
                raise Refused(f"{root}: no git repository above the org root: pass --repo <path>, or "
                              "--no-outside-check to run without the frozen-outside protection")
            here = parent
        repo = here
    if not os.path.isdir(repo):
        raise Refused(f"{repo}: --repo is not a directory")
    return ort.FrozenOutside(os.path.abspath(repo), ort.DEFAULT_FROZEN_OUTSIDE), False


def _resume_starting(disp, state, make_runtime):
    """Resume every pair left 'starting'. Returns the exit code contribution (0, 1 or 2)."""
    code = 0
    state_file = os.path.join(state, STATE_FILE)
    for key, rec in sorted(disp.state()["pairs"].items()):
        if rec.get("state") != "starting":
            continue
        event, _, workflow = key.partition("\n")
        name = str(rec.get("ledger"))
        path = os.path.join(state, "ledgers", name)
        where = f"{workflow} event={event} ledger={name}"
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            _say(f"org: not resumed {where}: no ledger", sys.stderr)
            code = max(code, 1)
            continue
        try:
            res = make_runtime(path).resume()
        except (ort.LedgerError, ValueError, OSError) as e:
            _say(f"org: not resumed {where}: the ledger does not verify: {e}", sys.stderr)
            code = max(code, 1)
            continue
        _finish_pair(state_file, key, res)
        _say(f"resumed {workflow} event={event} run={res.run_id} status={res.status}"
             + (f": {'; '.join(res.errors)}" if res.status != "success" and res.errors else ""))
        if res.status == "refused":
            code = 2
        elif res.status != "success":
            code = max(code, 1)
    return code


# ---------------------------------------------------------------- serve


def _describe(rec):
    wf, ev = rec.get("workflow") or "-", rec.get("event") or "-"
    if rec["outcome"] == "started":
        text = f"started {wf} event={ev} run={rec['run_id']} status={rec['status']}"
        return text + (f": {'; '.join(rec['errors'])}" if rec["status"] != "success" and rec.get("errors") else "")
    return f"{rec['outcome']} {wf} event={ev}: {rec.get('reason')}"


def _serve(args, host, verifier, clock, sleep):
    root, state, inbox = (os.path.abspath(p) for p in (args.root, args.state, args.inbox))
    for label, path in (("org root", root), ("state directory", state), ("inbox", inbox)):
        if not os.path.isdir(path):
            raise Refused(f"{path}: the {label} is not a directory")
    if fcntl is None:
        raise Refused("serve needs flock, which this platform does not have")
    lock = open(os.path.join(state, LOCK_FILE), "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        raise Refused(f"{os.path.join(state, LOCK_FILE)}: another serve holds this state directory") from None
    try:
        return _serve_locked(args, host, verifier, clock, sleep, root, state, inbox)
    finally:
        lock.close()


def _serve_locked(args, host, verifier, clock, sleep, root, state, inbox):
    key = _read_ledger_key(state)
    ring = _load_ring(state, verifier)
    snapshots = os.path.join(state, "snapshots")
    if not os.path.isdir(snapshots):
        raise Refused(f"{snapshots}: no snapshot store: the owner signs the first snapshot of the org root")
    if not any(os.path.isfile(os.path.join(root, n)) for n in STACK_FILES):
        raise Refused(f"{root}: no stack.yaml or stack.json in the org root")
    try:
        ort.build_file_map(root)
    except (ort.FileMapError, OSError) as e:
        raise Refused(f"{root}: org root refused: {e}") from None
    if host is None:
        host = build_host(root, os.path.join(state, "sessions"))
    start = _Inbox(inbox, "start", ring, key)
    decisions = _Inbox(inbox, "decision", ring, key)
    decisions.closed = args.once  # with no timer left, nothing can wake a run that must not wait for the inbox
    store = ort.SnapshotStore(snapshots)
    frozen, outside_off = _frozen(args, root)

    def make_runtime(ledger_path):
        rt = ort.OrgRuntime(root, ledger_path=ledger_path, ledger_key=key, ring=ring, host=host, snapshots=store,
                            frozen=frozen, clock=clock, sleep=sleep, poll=args.poll)
        return _LiveRun(rt, decisions, ledger_path)

    disp = dp.Dispatcher(root, os.path.join(state, STATE_FILE), os.path.join(state, "ledgers"), make_runtime)
    stop, old, shown, code = [], {}, [0, 0], 0
    _patch_state(os.path.join(state, STATE_FILE), lambda st: st.update(
        outside_check="disabled" if outside_off else "enabled"))

    def report():
        for i, feed in enumerate((start, decisions)):
            for text in feed.rejected[shown[i]:]:
                _say(f"rejected {text}", sys.stderr)
            shown[i] = len(feed.rejected)

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            old[sig] = signal.signal(sig, lambda *_: stop.append(1))
        except ValueError:  # not the main thread: the caller owns the signals
            pass
    try:
        code = _resume_starting(disp, state, make_runtime)
        while not stop:
            events = start.poll()
            items = list(start.items)
            report()
            for (path, _), event in zip(items, events):
                try:
                    records = disp.deliver(event)
                except dp.DispatcherError as e:
                    _say(f"org: {e}", sys.stderr)
                    return 2
                refused = False
                for rec in records:
                    _say(_describe(rec))
                    if rec["outcome"] == "started" and rec["status"] != "success" and rec.get("errors"):
                        _patch_state(os.path.join(state, STATE_FILE), lambda st, r=rec: st["pairs"].get(
                            f"{r['event']}\n{r['workflow']}", {}).update(reason="; ".join(r["errors"])))
                    if rec["outcome"] == "refused":
                        refused = refused or rec.get("event") == event.get("id")
                        if str(rec.get("reason", "")).startswith("run could not start"):
                            code = max(code, 1)
                    elif rec["outcome"] == "started":
                        if rec["status"] == "refused":
                            code = 2
                        elif rec["status"] != "success" and code != 2:
                            code = 1
                start.ack_path(path, ".rejected" if refused else ".seen")
                report()
                if stop:
                    break
            if not events:
                if args.once:
                    break
                if not stop:
                    sleep(args.poll)
    finally:
        for sig, handler in old.items():
            signal.signal(sig, handler)
        report()
    return code


# ---------------------------------------------------------------- emit


def _reject_constant(name):
    raise ValueError(f"{name} is not allowed")


def _emit(args):
    etype = args.type
    if not etype:
        raise Refused("--type must not be empty")
    if etype.startswith(dp.RESERVED_PREFIXES):
        raise Refused(f"the type '{etype}' uses a reserved prefix ({', '.join(dp.RESERVED_PREFIXES)}): "
                      "only a signed decision file may carry it")
    if not os.path.isdir(args.inbox):
        raise Refused(f"{args.inbox}: the inbox is not a directory")
    if args.id is not None and not args.id:
        raise Refused("--id must not be empty")
    event = {"type": etype}
    if args.data is not None:
        try:
            data = json.loads(args.data, parse_constant=_reject_constant)
        except (ValueError, RecursionError) as e:
            raise Refused(f"--data is not strict JSON: {e}") from None
        if not isinstance(data, dict):
            raise Refused("--data must be a JSON object")
        event["data"] = data
    if args.source is not None:
        event["source"] = args.source
    stamp, tag = f"{time.time_ns():020d}", secrets.token_hex(4)
    event["id"] = args.id or f"{stamp}-{tag}"
    name = f"{stamp}-{tag}.json"
    final = os.path.join(args.inbox, name)
    tmp = os.path.join(args.inbox, f".{name}.tmp")  # not `.json`: the inbox ignores it until the rename
    try:
        text = json.dumps(event, sort_keys=True, allow_nan=False)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, final)
    except (OSError, ValueError) as e:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise Refused(f"{final}: cannot write the event: {getattr(e, 'strerror', None) or e}") from None
    _say(event["id"])
    return 0


# ---------------------------------------------------------------- status


def _last_line(path):
    try:
        with open(path, "rb") as f:
            lines = f.read().split(b"\n")
    except OSError:
        return None
    lines.pop()  # a torn or empty tail
    for raw in reversed(lines):
        try:
            entry = json.loads(raw.decode("utf-8"))
            body = entry["body"]
            kind = body.get("kind") if isinstance(body, dict) and entry["kind"] == "log" else None
            return {"seq": entry["seq"], "kind": entry["kind"], "event_kind": kind}
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return None


def _status(args):
    state = os.path.abspath(args.state)
    if not os.path.isdir(state):
        raise Refused(f"{state}: the state directory is not a directory")
    try:
        data = dp.Dispatcher("", os.path.join(state, STATE_FILE), os.path.join(state, "ledgers"), None).state()
    except dp.DispatcherError as e:
        raise Refused(str(e)) from None
    try:
        key = _read_ledger_key(state)
    except Refused:
        key = None
    pairs = []
    for pair_key in sorted(data["pairs"]):
        event, _, workflow = pair_key.partition("\n")
        rec = data["pairs"][pair_key]
        path = os.path.join(state, "ledgers", str(rec.get("ledger")))
        verified = None
        if key is not None and os.path.exists(path):
            try:
                ledger = ort.RunLedger(path, key, readonly=True)
                ledger.verify_head(ledger.read())
                verified = True
            except (ort.LedgerError, OSError, ValueError):
                verified = False
        pairs.append({"event": event, "workflow": workflow, "state": rec.get("state"), "run_id": rec.get("run_id"),
                      "status": rec.get("status"), "reason": rec.get("reason"), "ledger": rec.get("ledger"),
                      "verified": verified,
                      "last": _last_line(path)})
    if args.json:
        _say(json.dumps({"pairs": pairs, "refusals": data["refusals"], "outside_check": data.get("outside_check")},
                        sort_keys=True))
        return 0
    if data.get("outside_check") == "disabled":
        _say("outside check: DISABLED (files outside the org root are not compared with the snapshot)")
    if not pairs and not data["refusals"]:
        _say("no events dispatched yet")
    for p in pairs:
        last = p["last"]
        if last is None:
            tail = "no ledger"
        else:
            tail = f"ledger entry {last['seq']} {last['kind']}" + (f"/{last['event_kind']}" if last["event_kind"] else "")
        check = {True: "verified", False: "NOT VERIFIED", None: "unchecked"}[p["verified"]]
        _say(f"{p['workflow']} event={p['event']} {p['state']} run={p['run_id'] or '-'} "
             f"status={p['status'] or '-'} | {tail} ({check})" + (f" reason={p['reason']}" if p["reason"] else ""))
    for r in data["refusals"][-20:]:
        _say(f"refused {r.get('workflow') or '-'} event={r.get('event') or '-'}: {r.get('reason')}")
    return 0


# ---------------------------------------------------------------- command line


def _parser():
    p = argparse.ArgumentParser(prog="org.py", description="Run the organization on this machine.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="read the inbox, dispatch events, run the workflows they start")
    s.add_argument("--root", required=True, help="the org root")
    s.add_argument("--state", required=True, help="the state directory")
    s.add_argument("--inbox", required=True, help="the inbox directory")
    s.add_argument("--once", action="store_true", help="handle what is there, then exit")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--repo", help="the repository whose frozen files are compared with the snapshot "
                                  "(default: the git top level of the org root)")
    g.add_argument("--no-outside-check", action="store_true",
                   help="run without the frozen-outside protection (warns, and is recorded in the state)")
    s.add_argument("--poll", type=float, default=1.0, metavar="SECONDS", help="seconds between inbox polls")
    e = sub.add_parser("emit", help="write one event file into the inbox")
    e.add_argument("--inbox", required=True)
    e.add_argument("--type", required=True)
    e.add_argument("--data", help="a JSON object")
    e.add_argument("--id", help="the event id (generated when absent)")
    e.add_argument("--source")
    t = sub.add_parser("status", help="print the dispatcher state and the last ledger line of each run")
    t.add_argument("--state", required=True)
    t.add_argument("--json", action="store_true")
    return p


def main(argv=None, *, host=None, verifier=None, clock=time.monotonic, sleep=time.sleep):
    """Run one command and return its exit code. `host`, `verifier`, `clock` and `sleep` are test seams."""
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    try:
        if args.cmd == "serve":
            if not args.poll > 0:
                raise Refused("--poll must be greater than 0")
            return _serve(args, host, verifier, clock, sleep)
        if args.cmd == "emit":
            return _emit(args)
        return _status(args)
    except Refused as e:
        _say(f"org: {e}", sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
