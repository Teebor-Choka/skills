"""Org runtime (U13b): the interpreter's run record, signatures, rungs, metrics and the real-time driver.

Standard library only, plus the sibling modules `interpreter` (U13a), `check_change` (U15), `agent_run` (U12) and
the validators. It adds, around the interpreter and without editing it (spec 13.1):

  1. `RunLedger`, `OrgRuntime.run/resume/replay`: every interpreter event goes to an HMAC hash chain. Resume and
     replay re-run the interpreter with the same run id and answer every host call from the ledger, so a run
     killed after any node ends in the same state. The ledger MAC key is the runtime's own; it is not the owner key.
  2. `KeyRing`: decision events verify against the gate's signer role (P18). The runtime holds public keys only.
     `SshKeygenVerifier` is the first implementation of the identity port (OpenSSH); others plug in behind
     `verify(principal, keys, payload, signature)`. No code here signs anything.
  3. Load refusals (run before the first task): file maps, rung enforcement against the last owner-signed
     snapshot, the static start-cycle check, catalog and collector checks.
  4. `InboxFeed`, `QueueFeed` and the real-time scheduler that delivers events to waiting gates.
  5. `OrgProcessHost`: `ProcessHost` plus the `agent-run` environment and `run_judge` (6.1).

It reuses `interpreter._Run` and `interpreter._Scheduler`, which are private to the same skill.

PROVISIONAL choices (spec silent; each listed in the unit report):
  - the signature of a decision event is an armored SSH signature (namespace `org-event`) in `event["signature"]`
    over the canonical JSON of the event without that key;
  - the base for rungs is the newest whole-root snapshot carrying a valid owner signature (see `SnapshotStore`);
  - a proposer without a signed snapshot may apply the rungs of the role named by `proposer_role`
    (default `improver`) in the base manifest, else `free` and `ordinary`;
  - file maps follow a file symlink that resolves inside the root and refuse every other symlink;
  - the collector calling convention (`ProcessCollector`);
  - an unreadable metric is recorded as an error, never as 0.
"""

import dataclasses
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_change  # noqa: E402
import interpreter as it  # noqa: E402
import validate_catalog as vc  # noqa: E402
import validate_manifest as vman  # noqa: E402

__all__ = (
    "UNENFORCED", "DEFAULT_FROZEN_OUTSIDE", "LedgerError", "DivergenceError", "OwnerKeyError", "FileMapError",
    "FrozenOutside", "RunLedger", "KeyRing", "SshKeygenVerifier", "SnapshotStore", "ProcessCollector",
    "InboxFeed", "QueueFeed", "OrgProcessHost", "OrgRuntime", "load_ring", "event_payload", "snapshot_event",
    "build_file_map", "check_collisions",
)

UNENFORCED = object()  # pass as `snapshots` to run with no rung enforcement (tests, throwaway roots)
NAMESPACE = "org-event"
ORG_ENTRIES = ("workflows", "briefs", "criteria", "schemas", "collectors", "checks", "bin")
ROOT_FILE = re.compile(r"^(manifest|metrics[^/]*)\.(json|yaml|yml)$")
MANIFEST_FILE = re.compile(r"^manifest\.(json|yaml|yml)$")
KEY_LINE = re.compile(r"^(ssh-[a-z0-9-]+|sk-ssh-[a-z0-9@.-]+|ecdsa-sha2-[a-z0-9]+|sk-ecdsa-sha2-[a-z0-9@.-]+) \S+( [^\n]*)?$")
PRINCIPAL = re.compile(r"^[A-Za-z0-9._-]+$")

# Files outside the org root that only the owner may change (spec 10, 13.1): the grammar (kind table, accepted
# subset, interpreter and validators), the harness and port contracts, hooks, plugin metadata and CI.
# Relative to the repository root; a trailing slash names a directory. PROVISIONAL default.
DEFAULT_FROZEN_OUTSIDE = (
    "agents/operating-model/skills/workflow/scripts/",
    "agents/operating-model/skills/workflow/contracts/",
    "agents/operating-model/skills/workflow/harness/",
    "agents/operating-model/hooks/",
    "agents/operating-model/.claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".github/workflows/",
)


class LedgerError(Exception):
    """The ledger does not verify, or a run cannot be recovered from it."""


class DivergenceError(LedgerError):
    """A resumed run produced an event that differs from the one the ledger holds."""


class OwnerKeyError(Exception):
    """Private key material was offered to the runtime."""


class FileMapError(Exception):
    """A file map cannot be built safely."""


# ---------------------------------------------------------------- file maps


def check_collisions(paths):
    seen = {}
    for p in paths:
        k = unicodedata.normalize("NFC", p).casefold()
        if k in seen and seen[k] != p:
            raise FileMapError(f"{p}: paths collide when compared case-insensitively: '{seen[k]}' and '{p}'")
        seen[k] = p


def _read_file(full, rel, real_root):
    """Bytes of a regular file or of a symlink that resolves to a regular file inside the root."""
    if os.path.islink(full):
        target = os.path.realpath(full)
        if not os.path.exists(target):
            raise FileMapError(f"{rel}: dangling symlink")
        if not (target == real_root or target.startswith(real_root + os.sep)):
            raise FileMapError(f"{rel}: symlink resolves outside the root")
        full = target
    if not os.path.isfile(full):
        raise FileMapError(f"{rel}: not a regular file")
    with open(full, "rb") as f:
        return f.read()


def _collect(base, entry, out):
    """Add the file or the tree `entry` (relative to `base`) to `out`."""
    real_root = os.path.realpath(base)
    full = os.path.join(base, entry)
    if os.path.islink(full) and os.path.isdir(full):
        raise FileMapError(f"{entry}: directory symlink")
    if os.path.isdir(full):
        for dirpath, dirnames, filenames in os.walk(full, followlinks=False):
            for d in sorted(dirnames):
                dp = os.path.join(dirpath, d)
                if os.path.islink(dp):
                    raise FileMapError(f"{os.path.relpath(dp, base).replace(os.sep, '/')}: directory symlink")
            for fn in sorted(filenames):
                fp = os.path.join(dirpath, fn)
                rel = os.path.relpath(fp, base).replace(os.sep, "/")
                out[rel] = _read_file(fp, rel, real_root)
    elif os.path.lexists(full):
        out[entry] = _read_file(full, entry, real_root)


def build_file_map(root):
    """Map of org-root-relative path to bytes for the org root's own entries (spec section 1)."""
    root = str(root)
    out = {}
    for name in sorted(os.listdir(root)):
        if ROOT_FILE.match(name):
            _collect(root, name, out)
        elif name in ORG_ENTRIES:
            _collect(root, name, out)
    check_collisions(list(out))
    return out


class FrozenOutside:
    """The path list of files outside the org root that are frozen (13.1), relative to `repo_root`."""

    def __init__(self, repo_root, paths):
        for p in paths:
            if not isinstance(p, str) or not p or p.startswith("/") or "\\" in p or any(
                    seg in ("", ".", "..") for seg in p.rstrip("/").split("/")):
                raise ValueError(f"frozen path '{p}' must be a relative POSIX path with no '..'")
        self.repo_root, self.paths = (None if repo_root is None else str(repo_root)), tuple(paths)

    def map(self):
        out = {}
        if self.repo_root is None:
            return out
        for p in self.paths:
            _collect(self.repo_root, p.rstrip("/"), out)
        check_collisions(list(out))
        return out


# ---------------------------------------------------------------- the ledger


def _mac(key, entry):
    body = json.dumps({k: entry[k] for k in ("seq", "prev", "kind", "body")}, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()


class RunLedger:
    """Append-only JSON lines. Each entry holds the MAC of the one before it. A torn last line is dropped."""

    GENESIS = "0" * 64

    def __init__(self, path, key, readonly=False):
        self.path, self.key, self.readonly, self.torn = str(path), key, readonly, False
        self._last, self._seq, self._good = self.GENESIS, 0, 0
        if os.path.exists(self.path):
            entries = self.read()
            if entries:
                self._last, self._seq = entries[-1]["mac"], entries[-1]["seq"]

    def read(self):
        try:
            with open(self.path, "rb") as f:
                raw = f.read()
        except FileNotFoundError:
            return []
        lines = raw.decode("utf-8", errors="replace").split("\n")
        self.torn = bool(lines.pop())
        entries, prev, good = [], self.GENESIS, 0
        for n, line in enumerate(lines, 1):
            try:
                entry = json.loads(line)
                ok = isinstance(entry, dict) and all(k in entry for k in ("seq", "prev", "kind", "body", "mac"))
            except ValueError:
                ok = False
            if not ok:
                raise LedgerError(f"{self.path}: line {n} is not a ledger entry")
            if entry["seq"] != n or entry["prev"] != prev:
                raise LedgerError(f"{self.path}: entry {n} does not follow the one before it")
            if not hmac.compare_digest(str(entry["mac"]), _mac(self.key, entry)):
                raise LedgerError(f"{self.path}: entry {n} has a bad signature")
            entries.append(entry)
            prev, good = entry["mac"], good + len(line.encode()) + 1
        self._good = good
        return entries

    def append(self, kind, body):
        if self.readonly:
            raise LedgerError(f"{self.path}: replay would write a '{kind}' entry")
        if os.path.exists(self.path) and os.path.getsize(self.path) > self._good:
            with open(self.path, "r+b") as f:  # cut a torn tail before writing after it
                f.truncate(self._good)
        entry = {"seq": self._seq + 1, "prev": self._last, "kind": kind, "body": json.loads(json.dumps(body, default=str))}
        entry["mac"] = _mac(self.key, entry)
        line = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
        with open(self.path, "ab") as f:
            f.write(line.encode())
            f.flush()
            os.fsync(f.fileno())
        self._last, self._seq, self._good = entry["mac"], entry["seq"], self._good + len(line.encode())
        return entry


# ---------------------------------------------------------------- the key ring (identity port: verify, revoke, list)


def event_payload(event):
    """The bytes a signature covers: canonical JSON of the event without its `signature` key."""
    body = {k: v for k, v in event.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


class SshKeygenVerifier:
    """OpenSSH verification: `ssh-keygen -Y verify` against an allowed-signers file of public keys only."""

    def verify(self, principal, keys, payload, sig):
        if not PRINCIPAL.match(principal) or not isinstance(sig, str) or not sig:
            return False
        with tempfile.TemporaryDirectory(prefix="org-verify-") as tmp:
            allowed, sigfile = os.path.join(tmp, "allowed"), os.path.join(tmp, "sig")
            with open(allowed, "w") as f:
                for k in keys:
                    f.write(f'{principal} namespaces="{NAMESPACE}" {k}\n')
            with open(sigfile, "w") as f:
                f.write(sig)
            try:
                r = subprocess.run(["ssh-keygen", "-Y", "verify", "-f", allowed, "-I", principal, "-n", NAMESPACE,
                                    "-s", sigfile], input=payload, capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                return False  # fail closed
            return r.returncode == 0


def _check_key_line(line):
    if not isinstance(line, str) or "PRIVATE KEY" in line:
        raise OwnerKeyError("the key ring takes public keys only; private key material was refused")
    if not KEY_LINE.match(line):
        raise ValueError(f"not a public key line: {line[:40]!r}")
    return line


class KeyRing:
    """Role name to public keys. `verify(event, signer)` asks the signer role's keys, never the claimed sender."""

    def __init__(self, keys, verifier=None):
        self._keys = {role: [_check_key_line(k) for k in lines] for role, lines in keys.items()}
        self._verifier = verifier or SshKeygenVerifier()

    def verify(self, event, signer):
        try:
            if not isinstance(event, dict) or not isinstance(event.get("signature"), str):
                return False
            keys = list(self._keys.get(signer) or [])
            if not keys:
                return False
            return self._verifier.verify(signer, keys, event_payload(event), event["signature"]) is True
        except Exception:  # noqa: BLE001  fail closed on anything odd in the event
            return False

    def revoke(self, key):
        ident = key.split()[:2]
        for role in self._keys:
            self._keys[role] = [k for k in self._keys[role] if k.split()[:2] != ident]

    def list(self):
        return {role: list(keys) for role, keys in self._keys.items() if keys}


def load_ring(text, verifier=None):
    """Parse `<role> <public key line>` lines. Private key material raises OwnerKeyError."""
    if "PRIVATE KEY" in text:
        raise OwnerKeyError("the key ring takes public keys only; private key material was refused")
    keys = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        role, _, key = line.partition(" ")
        keys.setdefault(role, []).append(key.strip())
    return KeyRing(keys, verifier=verifier)


# ---------------------------------------------------------------- owner-signed snapshots (the base for rungs)


def _hashes(m):
    return {k: hashlib.sha256(v).hexdigest() for k, v in sorted(m.items())}


def snapshot_event(files, outside):
    """The event the owner signs: the hashes of every org-root file and every listed outside file."""
    return {"type": "org.snapshot", "data": {"files": _hashes(files), "outside": _hashes(outside)}}


class SnapshotStore:
    """Whole-root snapshots in a directory outside the org root: blobs by hash plus `snapshots.jsonl`.

    The runtime reads it and verifies the owner signature of each snapshot; adding one is the owner's act.
    A snapshot holds every file, so "the last owner-signed version of each file" is the newest valid snapshot.
    """

    def __init__(self, path):
        self.dir = str(path)

    def add(self, files, outside, signature):
        os.makedirs(os.path.join(self.dir, "blobs"), exist_ok=True)
        for blob in list(files.values()) + list(outside.values()):
            p = os.path.join(self.dir, "blobs", hashlib.sha256(blob).hexdigest())
            if not os.path.exists(p):
                with open(p, "wb") as f:
                    f.write(blob)
        entry = {"data": snapshot_event(files, outside)["data"], "signature": signature}
        with open(os.path.join(self.dir, "snapshots.jsonl"), "a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")

    def latest_valid(self, ring):
        """(files, outside) of the newest snapshot with a valid owner signature, else None."""
        try:
            with open(os.path.join(self.dir, "snapshots.jsonl")) as f:
                lines = f.read().splitlines()
        except FileNotFoundError:
            return None
        for line in reversed(lines):
            try:
                entry = json.loads(line)
                event = {"type": "org.snapshot", "data": entry["data"], "signature": entry["signature"]}
                if not ring.verify(event, "owner"):
                    continue
                maps = []
                for part in ("files", "outside"):
                    m = {}
                    for rel, digest in entry["data"][part].items():
                        with open(os.path.join(self.dir, "blobs", digest), "rb") as b:
                            blob = b.read()
                        if hashlib.sha256(blob).hexdigest() != digest:
                            raise ValueError("blob does not match its hash")
                        m[rel] = blob
                    maps.append(m)
                return maps[0], maps[1]
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return None


# ---------------------------------------------------------------- metrics


class CollectorError(Exception):
    pass


class ProcessCollector:
    """Run `collectors/<name>.py` by argv exec and read one JSON number from stdout. PROVISIONAL convention.

    argv: `<python> <collector> <full task key>`; environment: ORG_LEDGER (the run ledger, read it only),
    ORG_KEY, ORG_RUN, ORG_METRIC. Exit 0 with a finite JSON number on stdout is a value. Anything else raises
    CollectorError, which the runtime records as an error: a metric is never recorded as zero by accident.
    """

    def __init__(self, root, timeout=60):
        self.root, self.timeout = os.path.realpath(str(root)), timeout

    def __call__(self, metric, entry, key, run_id, ledger_path):
        rel = entry.get("collector", "")
        if not vc.relative_path_ok(rel, "collectors/", (".py",)) or not vc.file_under_root(self.root, rel):
            raise CollectorError(f"{rel}: collector is not a file inside the org root")
        env = {"PATH": os.environ.get("PATH", ""), "ORG_LEDGER": os.path.abspath(ledger_path), "ORG_KEY": key,
               "ORG_RUN": run_id, "ORG_METRIC": metric}
        try:
            r = subprocess.run([sys.executable, os.path.join(self.root, rel), key], env=env, cwd=self.root,
                               capture_output=True, text=True, timeout=self.timeout, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise CollectorError(f"collector cannot run: {type(e).__name__}") from None
        if r.returncode != 0:
            lines = r.stderr.strip().splitlines()
            raise CollectorError(lines[0] if lines else f"collector exited {r.returncode}")
        try:
            v = json.loads(r.stdout)
        except ValueError:
            raise CollectorError("collector printed no JSON number") from None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
            raise CollectorError("collector printed no finite number")
        return v


# ---------------------------------------------------------------- feeds and the real-time scheduler


class QueueFeed:
    """An in-memory feed: `push` an event from anywhere, the driver polls it."""

    def __init__(self):
        self._q, self.closed, self.rejected = deque(), False, []

    def push(self, event):
        self._q.append(event)

    def close(self):
        self.closed = True

    def poll(self):
        out = list(self._q)
        self._q.clear()
        return out


class InboxFeed:
    """A directory of `*.json` event files, delivered once each in name order, then renamed `.seen`.

    A file that is not a JSON object is renamed `.rejected` and listed in `rejected`. Delivery is not trust:
    the gates verify signatures themselves.
    """

    def __init__(self, path, max_bytes=1_000_000):
        self.dir, self.max_bytes, self.closed, self.rejected = str(path), max_bytes, False, []

    def poll(self):
        out = []
        for name in sorted(os.listdir(self.dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self.dir, name)
            try:
                if os.path.getsize(path) > self.max_bytes:
                    raise ValueError("over the size limit")
                with open(path, encoding="utf-8") as f:
                    event = json.load(f)
                if not isinstance(event, dict):
                    raise ValueError("not a JSON object")
                out.append(event)
                os.replace(path, path[:-5] + ".seen")
            except (OSError, ValueError) as e:
                self.rejected.append(f"{name}: {e}")
                try:
                    os.replace(path, path[:-5] + ".rejected")
                except OSError:
                    pass
        return out


class _LiveScheduler(it._Scheduler):
    """The U13a scheduler on a wall clock: due timers and host events fire, then feed events, else wait."""

    def __init__(self, ext, feed, clock, sleep, journal, poll):
        self._clock, self._t0 = clock, clock()
        super().__init__(ext)
        self.feed, self._sleep, self._journal, self._poll = feed, sleep, journal, poll

    now = property(lambda s: s._clock() - s._t0, lambda s, v: None)

    def run(self):
        while self.live > 0:
            if self.ready:
                p, value, exc = self.ready.popleft()
                self._step(p, value, exc)
                continue
            now = self.now
            if self.timers and self.timers[0][0] <= now:
                while self.timers and self.timers[0][0] <= now:
                    _, _, p, token, exc = it.heapq.heappop(self.timers)
                    if not p.done and p.token == token:
                        self._resume(p, None, exc)
                continue
            if self.ext_i < len(self.ext) and self.ext[self.ext_i][0] <= now:
                event = self.ext[self.ext_i][1]
                self.ext_i += 1
                self.publish(event)
                continue
            fed = self.feed.poll()
            if fed:
                for event in fed:
                    self._journal(now, event)
                    self.publish(event)
                continue
            nxt = [t for t in (self.timers[0][0] if self.timers else None,
                               self.ext[self.ext_i][0] if self.ext_i < len(self.ext) else None) if t is not None]
            if not nxt and self.feed.closed:
                return False
            wait = self._poll if not nxt else min(self._poll, max(min(nxt) - now, 0.0))
            self._sleep(max(wait, 0.0001))
        return True


# ---------------------------------------------------------------- hosts


class _NoLive:
    """Inner host for replay: any call that would reach the world is an error."""

    def __init__(self, inner):
        self._inner = inner

    def scheduled_events(self):
        return self._inner.scheduled_events()

    def confined(self, rel):
        return self._inner.confined(rel)

    def _no(self, what):
        raise LedgerError(f"replay needs a live {what}: the ledger does not hold that answer")

    def run_step(self, req):
        self._no(f"step '{req.key}'")

    def run_check(self, name, key, evidence):
        self._no(f"check '{name}' on '{key}'")

    def run_judge(self, req):
        self._no(f"judge on '{req.key}'")

    def verify_signed(self, event, signer):
        self._no("signature check")


class _JournalHost:
    """Answers host calls from the ledger while it holds an answer, else asks the live host and records it."""

    def __init__(self, inner, ring, ledger, journal, fed, zero_duration):
        self.inner, self.ring, self.ledger = inner, ring, ledger
        self.journal, self.fed, self.zero_duration = journal, fed, zero_duration

    def _take(self, kind, key):
        q = self.journal.get((kind, key))
        return (True, q.popleft()) if q else (False, None)

    def _put(self, kind, key, result):
        self.ledger.append("host", {"call": kind, "key": key, "result": result})

    def scheduled_events(self):
        return list(self.inner.scheduled_events()) + [(t, e) for t, e in self.fed]

    def confined(self, rel):
        return self.inner.confined(rel)

    def verify_signed(self, event, signer):
        k = hashlib.sha256(event_payload(event) + b"\n" + signer.encode()).hexdigest()
        hit, res = self._take("verify", k)
        if hit:
            return res
        res = self.ring.verify(event, signer)  # the ring decides; the inner host's opinion is ignored
        self._put("verify", k, res)
        return res

    def run_step(self, req):
        hit, res = self._take("step", req.key)
        if hit:
            return it.StepOutcome(**res)
        out = self.inner.run_step(req)
        if self.zero_duration:
            out.duration = 0.0  # a live step already took wall time
        self._put("step", req.key, dataclasses.asdict(out))
        return out

    def run_check(self, name, key, evidence):
        hit, res = self._take("check", f"{name}\n{key}")
        if not hit:
            try:
                res = bool(self.inner.run_check(name, key, evidence))
            except it.OutsideRoot as e:
                res = {"outside": str(e)}
            self._put("check", f"{name}\n{key}", res)
        if isinstance(res, dict):
            raise it.OutsideRoot(res["outside"])
        return res

    def run_judge(self, req):
        key = f"{req.key}\n{req.item}"
        hit, res = self._take("judge", key)
        if hit:
            return res
        res = self.inner.run_judge(req)
        self._put("judge", key, res)
        return res


class _Tee(list):
    """The run's event list. Appends go to the ledger; events the ledger already holds are compared, not rewritten."""

    def __init__(self, ledger, existing, on_new, on_skipped):
        super().__init__()
        self.ledger, self.existing, self.on_new, self.on_skipped = ledger, existing, on_new, on_skipped
        self.closed = False

    def append(self, e):
        super().append(e)
        if self.closed:
            return
        i = e["seq"]
        if i < len(self.existing):
            a = {k: v for k, v in self.existing[i].items() if k != "t"}
            b = {k: v for k, v in json.loads(json.dumps(e, default=str)).items() if k != "t"}
            if a != b:
                raise DivergenceError(f"event {i} differs from the ledger: {b.get('kind')} vs {a.get('kind')}")
            self.on_skipped(e)
            return
        self.ledger.append("log", e)
        self.on_new(e)


class OrgProcessHost(it.ProcessHost):
    """`ProcessHost` that gives `agent-run` its environment and runs model judges through it (6.1)."""

    AGENT_RUN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_run.py")

    def __init__(self, root, session_dir, env=None, agent_run=None, events=(), verify=None):
        super().__init__(root, agent_run=agent_run or self.AGENT_RUN, events=events, verify=verify)
        self.session_dir = os.path.abspath(str(session_dir))
        self.env = dict(env or {})
        os.makedirs(self.session_dir, exist_ok=True)

    def _env(self, req, item=None):
        env = {"PATH": os.environ.get("PATH", ""), "ORG_ROOT": self.root, "ORG_RUN": req.run_id, "ORG_KEY": req.key,
               "ORG_SESSION_DIR": self.session_dir}
        env.update({k: v for k, v in self.env.items() if k.startswith("ORG_") and k not in env})
        if item is not None:
            env["ORG_ITEM"] = str(item)
        return env

    def _stage_input(self, argv):
        """agent-run reads its input file only from the session directory or the org root, and U13a writes it to
        a private temporary directory: copy it (read-only) into the session directory and point `--input` there."""
        argv = list(argv)
        if "--input" in argv and argv.index("--input") + 1 < len(argv):
            i = argv.index("--input") + 1
            src = argv[i]
            if not os.path.realpath(src).startswith(self.session_dir + os.sep):
                dst_dir = os.path.join(self.session_dir, "inputs")
                os.makedirs(dst_dir, exist_ok=True)
                dst = os.path.join(dst_dir, secrets.token_hex(8) + ".json")
                with open(src, "rb") as f:
                    data = f.read()
                with open(dst, "wb") as f:
                    f.write(data)
                os.chmod(dst, 0o444)
                argv[i] = dst
        return argv

    def _agent_run(self, argv, env, stdin, limit):
        argv = self._stage_input(argv)
        try:
            p = subprocess.Popen([sys.executable, self.agent_run] + argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=env, cwd=self.root, text=True, start_new_session=True)
        except OSError as e:
            return None, None, f"cannot start: {e.strerror}", 127, False
        t0 = time.monotonic()
        try:
            out, err = p.communicate(stdin, timeout=limit)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, it.signal.SIGKILL)
            p.communicate()
            return None, None, None, -9, True
        return out, err, time.monotonic() - t0, p.returncode, False

    def run_step(self, req):
        if req.command != "agent-run":
            return super().run_step(req)
        out, err, dur, code, timed_out = self._agent_run(req.argv[1:], self._env(req), json.dumps(req.input), req.limit)
        if timed_out:
            return it.StepOutcome(exit_code=-9, duration=req.limit or 0, timed_out=True)
        if out is None:
            return it.StepOutcome(exit_code=code, error=err)
        try:
            parsed = json.loads(out.strip())
        except ValueError:
            parsed = out.strip()
        error = None if code == 0 else (err.strip().splitlines() or [f"command exited {code}"])[0]
        return it.StepOutcome(exit_code=code, output=parsed, stdout=out, duration=dur, error=error)

    def run_judge(self, req):
        out, err, dur, code, timed_out = self._agent_run(req.argv[1:], self._env(req, req.item), "", 3600)
        if timed_out or code != 0 or out is None:
            return None
        try:
            event = json.loads(out)["event"]
            d = event["data"]
        except (ValueError, KeyError, TypeError):
            return None
        if (event.get("type") != "org.rubric-verdict" or d.get("run") != req.run_id or d.get("task") != req.key
                or d.get("item") != req.item):
            return None
        return {"invocation": req.invocation, "type": event["type"],
                "data": {"run": d["run"], "task": d["task"], "item": d["item"], "verdict": d.get("verdict")}}


# ---------------------------------------------------------------- the runtime


def _digest(files):
    h = hashlib.sha256()
    for k in sorted(files):
        h.update(k.encode() + b"\0" + hashlib.sha256(files[k]).digest())
    return h.hexdigest()


class OrgRuntime:
    """Load, refuse, run, resume and replay workflows of one org root against a host and a ledger.

    `snapshots` (a `SnapshotStore`, or `UNENFORCED`) and `frozen` (a `FrozenOutside`) are required: leaving rung
    enforcement out has to be written down.
    """

    def __init__(self, root, *, ledger_path, ledger_key, ring, host, snapshots, frozen, proposer_rungs=None,
                 proposer_role="improver", collector=None, clock=time.monotonic, sleep=time.sleep, poll=1.0):
        self.root, self.ledger_path, self.ledger_key = str(root), str(ledger_path), ledger_key
        self.ring, self.host, self.snapshots, self.frozen = ring, host, snapshots, frozen
        self.proposer_rungs, self.proposer_role = proposer_rungs, proposer_role
        self.collector = collector or ProcessCollector(self.root)
        self.clock, self.sleep, self.poll = clock, sleep, poll

    # -- load

    def _rungs_for(self, base_files):
        if self.proposer_rungs is not None:
            return set(self.proposer_rungs)
        for name, data in base_files.items():  # the BASE manifest: a proposer cannot grant itself rungs
            if MANIFEST_FILE.match(name) and data is not None:
                try:
                    man = json.loads(data) if name.endswith(".json") else __import__("yaml").safe_load(data)
                    rungs = man["roles"][self.proposer_role]["rungs"]
                    if isinstance(rungs, list) and all(isinstance(r, str) for r in rungs):
                        return set(rungs) - {"frozen"}
                except Exception:  # noqa: BLE001
                    break
        return {"free", "ordinary"}

    def _rung_refusals(self, files):
        if self.snapshots is UNENFORCED:
            return []
        base = self.snapshots.latest_valid(self.ring)
        if base is None:
            return ["run refused: snapshot: no owner-signed snapshot to compare against"]
        base_files, base_out = base
        errs = []
        try:
            out = self.frozen.map()
        except FileMapError as e:
            return [f"run refused: {e}"]
        for p in sorted(set(base_out) | set(out)):
            if base_out.get(p) != out.get(p):
                errs.append(f"run refused: {p}: change needs rung 'frozen' and has no owner signature")
        if base_files != files:
            paths = set(base_files) | set(files)
            b = {p: base_files.get(p) for p in paths}
            n = {p: files.get(p) for p in paths}
            _, refused = check_change.check_change(b, n, self._rungs_for(base_files))
            for path, _task, _row, rung in sorted(refused, key=lambda e: (e[0], e[3])):
                errs.append(f"run refused: {path}: change needs rung '{rung}' and has no owner signature")
        return errs

    def _load(self, name):
        """(refusals, workflows, catalog, manifest, files)."""
        try:
            files = build_file_map(self.root)
        except (FileMapError, OSError) as e:
            return [f"run refused: {e}"], None, None, None, None
        errs = self._rung_refusals(files)
        if errs:
            return errs, None, None, None, files
        mans = [n for n in files if MANIFEST_FILE.match(n)]
        if len(mans) != 1:
            return [f"run refused: manifest: need exactly one manifest file, found {len(mans)}"], None, None, None, files
        mname = mans[0]
        cat_files = sorted(n for n in files if n.startswith("metrics") and ROOT_FILE.match(n))
        try:
            manifest = vc.load_document(os.path.join(self.root, mname))
            docs = [(n, vc.load_document(os.path.join(self.root, n))) for n in cat_files]
        except (vc.LoadError, vc.UsageError) as e:
            return [f"run refused: {getattr(e, 'path', mname)}: {getattr(e, 'msg', e)}"], None, None, None, files
        catalog, cerrs = vc.merge_catalogs(docs)
        cerrs = cerrs or vc.validate_catalog(docs, self.root)
        if cerrs:
            return [f"run refused: {cat_files[0] if len(cat_files) == 1 else 'metrics'}: {cerrs[0]}"], None, None, None, files
        merrs = vman.validate_manifest(manifest, catalog, self.root)
        if merrs:
            return [f"run refused: {mname}: {merrs[0]}"], None, None, None, files
        workflows = {}
        for wname, entry in manifest["workflows"].items():
            workflows[wname] = vc.load_document(os.path.join(self.root, entry["path"]))
        interp = it.Interpreter(workflows, self.host, catalog=catalog, manifest=manifest)
        return interp.refusals(name), workflows, catalog, manifest, files

    # -- metrics

    @staticmethod
    def _task_index(workflows):
        return {n: {p: t for p, t in it._walk(doc["do"])} for n, doc in workflows.items()}

    def _metrics_of(self, index, start, full):
        wf, parts, task = start, full.split(">"), None
        for i, part in enumerate(parts):
            task = index.get(wf, {}).get(re.sub(r"#[0-9]+", "", part))
            if task is None:
                return []
            if i < len(parts) - 1:
                wf = ((task.get("run") or {}).get("workflow") or {}).get("name")
        org = (task.get("metadata") or {}).get("org")
        return list(org.get("metrics") or []) if isinstance(org, dict) else []

    # -- execute

    def _execute(self, name, inp, rid, ledger, loaded, journal, existing, fed, feed=None):
        _errs, workflows, catalog, manifest, _files = loaded
        index = self._task_index(workflows)
        pending = {"seq": None}

        def collect(e):
            if e["kind"] != "accept" or e.get("status") == "cancelled":
                return
            for metric in self._metrics_of(index, name, e["key"]):
                row = {"key": e["key"], "metric": metric}
                try:
                    row["value"] = self.collector(metric, catalog[metric], e["key"], rid, ledger.path)
                except Exception as exc:  # noqa: BLE001  an unreadable metric is an error row, never a zero
                    row["error"] = str(exc) or type(exc).__name__
                ledger.append("metric", row)

        def skipped(e):
            if pending["seq"] == e["seq"]:  # killed between the accept entry and its metric rows
                collect(e)

        jhost = _JournalHost(self.host, self.ring, ledger, journal, fed, zero_duration=feed is not None)
        interp = it.Interpreter(workflows, jhost, catalog=catalog, manifest=manifest)
        run = it._Run(interp, rid)
        tail = ledger.read()
        if tail and tail[-1]["kind"] == "log" and tail[-1]["body"].get("kind") == "accept":
            pending["seq"] = tail[-1]["body"]["seq"]
        tee = _Tee(ledger, existing, collect, skipped)
        run.events = tee
        if feed is not None:
            sched = _LiveScheduler(list(jhost.scheduled_events()), feed, self.clock, self.sleep,
                                   lambda t, ev: ledger.append("feed", {"t": t, "event": ev}), self.poll)
            sched.on_event = run.sched.on_event
            run.sched = sched
        try:
            return run.execute(name, inp)
        finally:
            tee.closed = True  # a crash writes nothing more; neither does unwinding after one

    def run(self, name, input=None, run_id=None, feed=None):
        rid = run_id or secrets.token_hex(16)
        loaded = self._load(name)
        if loaded[0]:
            return it.RunResult(status="refused", errors=loaded[0], run_id=rid)
        ledger = RunLedger(self.ledger_path, self.ledger_key)
        if ledger.read():
            raise LedgerError(f"{self.ledger_path}: the ledger already holds a run; resume it")
        ledger.append("header", {"run_id": rid, "workflow": name, "input": input, "root_digest": _digest(loaded[4])})
        return self._execute(name, input, rid, ledger, loaded, {}, [], [], feed=feed)

    def _recover(self, readonly):
        ledger = RunLedger(self.ledger_path, self.ledger_key, readonly=readonly)
        entries = ledger.read()
        if not entries or entries[0]["kind"] != "header":
            raise LedgerError(f"{self.ledger_path}: no header: there is nothing to resume")
        h = entries[0]["body"]
        loaded = self._load(h["workflow"])
        if loaded[0]:
            return None, it.RunResult(status="refused", errors=loaded[0], run_id=h["run_id"])
        if _digest(loaded[4]) != h["root_digest"]:
            err = "run refused: org root: the org root changed since the run started"
            return None, it.RunResult(status="refused", errors=[err], run_id=h["run_id"])
        journal, existing, fed = {}, [], []
        for e in entries[1:]:
            if e["kind"] == "log":
                existing.append(e["body"])
            elif e["kind"] == "host":
                b = e["body"]
                journal.setdefault((b["call"], b["key"]), deque()).append(b["result"])
            elif e["kind"] == "feed":
                fed.append((e["body"]["t"], e["body"]["event"]))
        return (ledger, h, loaded, journal, existing, fed), None

    def resume(self):
        """Re-run the recorded run from its ledger. Host calls the ledger answers are not made again."""
        ctx, refused = self._recover(readonly=False)
        if refused:
            return refused
        ledger, h, loaded, journal, existing, fed = ctx
        return self._execute(h["workflow"], h["input"], h["run_id"], ledger, loaded, journal, existing, fed)

    def replay(self):
        """Rebuild the run's result from its ledger alone: no live call and no write."""
        ctx, refused = self._recover(readonly=True)
        if refused:
            return refused
        ledger, h, loaded, journal, existing, fed = ctx
        real = self.host
        try:
            self.host = _NoLive(real)
            return self._execute(h["workflow"], h["input"], h["run_id"], ledger, loaded, journal, existing, fed)
        finally:
            self.host = real
