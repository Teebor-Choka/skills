"""Event dispatcher (U18): the `trigger` node and the `event` connection.

Standard library only, plus the sibling modules `org_runtime` (U13b, public API only) and `validate_catalog`
(document loading). `Dispatcher.deliver(event)` takes a host-delivered event, starts one run of every workflow whose
`schedule.on` is `one` with a literal `with.type` equal to the event type, and then does the same for every event
those runs emit (the event connection), breadth first. The run input is `{"event": <the event>}`, so the ledger
header (`workflow`, `input`) records which event started which workflow. The runtime names the run id.

Rules (spec 7.7, 7.5a):
  - events with the reserved prefixes `org.owner-` and `org.task-` never start a run;
  - one run per (event id, workflow), at most once, kept in a state file and written BEFORE the run starts, so a
    crash cannot start the pair twice (a crashed run is resumed with `OrgRuntime.resume`, not restarted);
  - `data.chain` is the hop depth: absent on a host event means 0; the dispatcher sets it to parent + 1 on every
    emitted event, whatever the workflow wrote; a start at depth above 8 is refused; at most 100 starts per original
    host event, counted across the whole chain and kept across restarts;
  - a refusal is a record (returned and kept in the state file), never an exception.

PROVISIONAL choices (the spec is silent; listed in the unit report):
  - the routing table is read from the manifest and workflow files on disk at each delivery, without validation:
    the runtime validates and verifies the root again when it starts the run, so a swapped file is refused there;
  - an emitted event gets the id `<run id>:<emit seq>` whatever id its author wrote, so an emit cannot collide
    with a host event id or with another run's event;
  - `schedule.on` with any key besides `one`, or `one.with` with any key besides `type`, starts nothing;
  - each run gets its own ledger, `<ledger_dir>/<hash of event id and workflow>.ledger`; `make_runtime(ledger_path)`
    builds the `OrgRuntime`;
  - one `deliver` at a time per state file (an exclusive `flock` where the platform has one);
  - the emits of a run that was cut off by a crash are not re-dispatched on restart.
"""

import contextlib
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import org_runtime as ort  # noqa: E402
import validate_catalog as vc  # noqa: E402

try:
    import fcntl
except ImportError:  # pragma: no cover - non-posix
    fcntl = None

__all__ = ("Dispatcher", "DispatcherError", "MAX_DEPTH", "MAX_STARTS", "RESERVED_PREFIXES")

RESERVED_PREFIXES = ("org.owner-", "org.task-")
MAX_DEPTH = 8
MAX_STARTS = 100
MAX_REFUSALS = 1000
MANIFEST_NAMES = ("manifest.json", "manifest.yaml", "manifest.yml")


class DispatcherError(Exception):
    """The state file cannot be trusted (corrupt or unreadable). Fail closed: no run starts."""


def _literal(value):
    return isinstance(value, str) and bool(value) and "${" not in value


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _start_type(doc):
    """(type, None) for `schedule.on = one with literal type`; (None, reason) for a schedule that starts nothing;
    (None, None) for a workflow with no schedule."""
    if not isinstance(doc, dict) or "schedule" not in doc:
        return None, None
    sched = doc["schedule"]
    on = sched.get("on") if isinstance(sched, dict) else None
    if not isinstance(on, dict) or set(on) != {"one"}:
        return None, "schedule.on is not a single 'one' form, so it starts nothing"
    one = on["one"]
    with_ = one.get("with") if isinstance(one, dict) else None
    if not isinstance(with_, dict) or set(with_) != {"type"}:
        return None, "schedule.on.one.with must hold only 'type', so it starts nothing"
    if not _literal(with_["type"]):
        return None, "schedule.on.one.with.type is not a literal string, so it starts nothing"
    return with_["type"], None


class Dispatcher:
    def __init__(self, root, state_path, ledger_dir, make_runtime, max_depth=MAX_DEPTH, max_starts=MAX_STARTS):
        self.root, self.state_path, self.ledger_dir = str(root), str(state_path), str(ledger_dir)
        self.make_runtime, self.max_depth, self.max_starts = make_runtime, max_depth, max_starts

    # -- state

    def _read(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                st = json.load(f)
        except FileNotFoundError:
            return {"pairs": {}, "starts": {}, "refusals": []}
        except (OSError, ValueError) as e:
            raise DispatcherError(f"{self.state_path}: cannot read the state file: {e}") from None
        ok = (isinstance(st, dict) and isinstance(st.get("pairs"), dict) and isinstance(st.get("starts"), dict)
              and isinstance(st.get("refusals"), list))
        if not ok:
            raise DispatcherError(f"{self.state_path}: the state file has the wrong shape")
        return st

    def _write(self, st):
        st["refusals"] = st["refusals"][-MAX_REFUSALS:]
        tmp = self.state_path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(st, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.state_path)

    def state(self):
        return self._read()

    @contextlib.contextmanager
    def _locked(self):
        """One writer at a time per state file (an exclusive `flock` where the platform has one)."""
        os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
        lock = None
        if fcntl is not None:
            lock = open(self.state_path + ".lock", "a")
            fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if lock is not None:
                lock.close()

    def set_outside_check(self, enabled):
        """Record whether `serve` enforces the frozen-outside list: `outside_check` is "enabled" or "disabled"."""
        with self._locked():
            st = self._read()
            st["outside_check"] = "enabled" if enabled else "disabled"
            self._write(st)

    def finish_pair(self, key, res):
        """Mark a pair done with the result of its run (a run the dispatcher did not see end, resumed after a crash).
        Keeps the error text as `reason`. Returns the records of any follow-up dispatch."""
        with self._locked():
            st = self._read()
            pair = st["pairs"].setdefault(key, {})
            pair.update(state="done", run_id=res.run_id, status=res.status)
            if res.status != "success" and res.errors:
                pair["reason"] = "; ".join(res.errors)
            self._write(st)
        return []

    def record_reason(self, key, reason):
        """Keep `reason` on an existing pair; an unknown pair is ignored."""
        with self._locked():
            st = self._read()
            if key in st["pairs"]:
                st["pairs"][key]["reason"] = reason
                self._write(st)

    # -- routing

    def _routes(self):
        """({type: [workflow, ...] sorted}, [skip records], fatal reason or None)."""
        found = [n for n in MANIFEST_NAMES if os.path.isfile(os.path.join(self.root, n))]
        if len(found) != 1:
            return {}, [], f"manifest: need exactly one manifest file in the org root, found {len(found)}"
        try:
            manifest = vc.load_document(os.path.join(self.root, found[0]))
        except (vc.LoadError, vc.UsageError) as e:
            return {}, [], f"manifest: {getattr(e, 'msg', e)}"
        entries = manifest.get("workflows") if isinstance(manifest, dict) else None
        if not isinstance(entries, dict):
            return {}, [], "manifest: workflows is not a map"
        real_root = os.path.realpath(self.root)
        table, notes = {}, []
        for name in sorted(entries):
            path = entries[name].get("path") if isinstance(entries[name], dict) else None
            full = os.path.realpath(os.path.join(real_root, path)) if isinstance(path, str) else None
            if not full or os.path.commonpath([real_root, full]) != real_root or not os.path.isfile(full):
                notes.append(self._note(name, "workflow file is missing or outside the org root"))
                continue
            try:
                doc = vc.load_document(full)
            except (vc.LoadError, vc.UsageError) as e:
                notes.append(self._note(name, f"workflow file cannot be loaded: {getattr(e, 'msg', e)}"))
                continue
            etype, why = _start_type(doc)
            if why:
                notes.append(self._note(name, why))
            elif etype is not None:
                table.setdefault(etype, []).append(name)
        return table, notes, None

    @staticmethod
    def _note(name, reason):
        return {"outcome": "skipped", "workflow": name, "reason": f"workflow '{name}': {reason}"}

    # -- delivery

    def deliver(self, event):
        """Dispatch a host-delivered event and, breadth first, every event the started runs emit. Returns records."""
        with self._locked():
            return self._deliver(event)

    def _deliver(self, event):
        st = self._read()
        table, notes, fatal = self._routes()
        records = []
        queue = []
        root_id = event.get("id") if isinstance(event, dict) else None
        queue.append((event, None, root_id))  # (event, depth override, root id)
        while queue:
            ev, depth, root = queue.pop(0)
            self._one(st, table, ev, depth, root, fatal, records, queue)
        records.extend(notes)
        return records

    def _refuse(self, st, records, ev, reason, workflow=None, depth=None):
        eid = ev.get("id") if isinstance(ev, dict) else None
        rec = {"outcome": "refused", "event": eid if isinstance(eid, str) else None, "workflow": workflow,
               "reason": reason, "depth": depth}
        records.append(rec)
        st["refusals"].append({k: v for k, v in rec.items()})
        self._write(st)

    def _one(self, st, table, ev, depth, root, fatal, records, queue):
        if not isinstance(ev, dict):
            return self._refuse(st, records, ev, "event is not a map")
        etype = ev.get("type")
        if not _literal(etype):
            return self._refuse(st, records, ev, "event type must be a literal, non-empty string")
        eid = ev.get("id")
        if not isinstance(eid, str) or not eid:
            return self._refuse(st, records, ev, "event id must be a non-empty string")
        for prefix in RESERVED_PREFIXES:
            if etype.startswith(prefix):
                return self._refuse(st, records, ev, f"event type '{etype}' uses the reserved prefix {prefix}")
        if depth is None:  # host-delivered
            data = ev.get("data")
            if data is not None and not isinstance(data, dict):
                return self._refuse(st, records, ev, "data must be a map")
            chain = data.get("chain", 0) if data else 0
            if not _is_int(chain) or chain < 0:
                return self._refuse(st, records, ev, "data.chain must be a non-negative integer")
            depth = chain
        if fatal:
            return self._refuse(st, records, ev, fatal)
        names = table.get(etype, [])
        if not names:
            records.append({"outcome": "skipped", "event": eid, "workflow": None, "depth": depth,
                            "reason": f"no workflow starts on event type '{etype}'"})
            return None
        for name in names:
            key = f"{eid}\n{name}"
            if key in st["pairs"]:
                records.append({"outcome": "duplicate", "event": eid, "workflow": name, "depth": depth,
                                "reason": "this event already started this workflow"})
                continue
            if depth > self.max_depth:
                self._refuse(st, records, ev, f"chain depth {depth} exceeds {self.max_depth}", name, depth)
                continue
            if st["starts"].get(root, 0) >= self.max_starts:
                self._refuse(st, records, ev,
                             f"more than {self.max_starts} starts for the original event '{root}'", name, depth)
                continue
            self._start(st, ev, name, key, depth, root, records, queue)
        return None

    def _start(self, st, ev, name, key, depth, root, records, queue):
        ledger = hashlib.sha256(key.encode()).hexdigest()[:32] + ".ledger"
        st["pairs"][key] = {"state": "starting", "ledger": ledger, "root": root}
        st["starts"][root] = st["starts"].get(root, 0) + 1
        self._write(st)  # before the run: a crash must not start the pair a second time
        os.makedirs(self.ledger_dir, exist_ok=True)
        try:
            res = self.make_runtime(os.path.join(self.ledger_dir, ledger)).run(name, input={"event": ev})
        except (ort.LedgerError, ValueError, OSError) as e:
            st["pairs"][key]["state"] = "failed-to-start"
            self._refuse(st, records, ev, f"run could not start: {e}", name, depth)
            return
        st["pairs"][key].update(state="done", run_id=res.run_id, status=res.status)
        self._write(st)
        records.append({"outcome": "started", "event": ev["id"], "workflow": name, "depth": depth,
                        "run_id": res.run_id, "status": res.status, "errors": list(res.errors),
                        "ledger": ledger, "reason": None})
        for e in res.events:
            if e.get("kind") != "emit" or not isinstance(e.get("event"), dict):
                continue
            out = dict(e["event"])
            data = out.get("data")
            data = dict(data) if isinstance(data, dict) else ({} if data is None else {"value": data})
            data["chain"] = depth + 1
            out["data"], out["id"] = data, f"{res.run_id}:{e.get('seq')}"
            queue.append((out, depth + 1, root))
