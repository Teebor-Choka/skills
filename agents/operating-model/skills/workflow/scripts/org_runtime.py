"""Org runtime (U13b): the interpreter's run record, signatures, rungs, metrics and the real-time driver.

Standard library only, plus the sibling modules `interpreter` (U13a), `check_change` (U15), `agent_run` (U12)
and the validators. Around the interpreter, without editing it (spec 13.1):

  1. `RunLedger` and `OrgRuntime.run/resume/replay`. Every interpreter event goes to an HMAC hash chain, and a
     `<ledger>.head` file records the entry count and last MAC after each append, so a rolled-back ledger is
     refused. Resume and replay re-run the interpreter with the same run id and answer every host call from the
     ledger. A run killed after any node ends in the same state; a live-fed run resumes with a feed.
     `RunLedger` is a port of `procedure/scripts/ledger.py`: U16 deletes that module and its names clash here.
     The ledger key (at least 32 random bytes) belongs in a file with mode 0600 outside the org root, readable
     by the runtime user only. It is the runtime's own key, never the owner key.
  2. `KeyRing`: a decision event verifies against the gate's signer role (P18); each decision event id is
     consumed once per run (P33). The runtime holds public keys only; no code here signs anything.
     `SshKeygenVerifier` is the first implementation of the identity port (OpenSSH).
  3. Load refusals, run before the first task: file maps, rung enforcement against a signed monotonic snapshot
     chain, the start-cycle check, catalog and collector checks. Manifest, catalogs and workflows are parsed
     from the verified file-map bytes, never from a second disk read. Before every exec of a check, a `bin/`
     command or `agent_run.py`, the bytes on disk are compared with the verified ones.
     OPERATIONAL REQUIREMENT: agent children must not have write access to the org root (U12, sandboxing), and
     the runtime must be launched from a trusted copy of `scripts/`.
  4. `InboxFeed`, `QueueFeed` and `LiveScheduler`, the real-time driver.
  5. `OrgProcessHost`: `ProcessHost` plus the `agent-run` environment and `run_judge` (6.1).
  6. Metrics (spec update 13, P62 to P64): per-node `metric` rows through `RegistryCollector` (the
     `metric_collectors` registry; `ProcessCollector` stays injectable), one `org.metric` entry per catalog metric
     at run end, and `TurnBoundary`, the P61 order (export, metrics, reflection, turn-complete) as ledger entries.
     All of them go through `RunLedger.append`: the ledger is never rewritten, pruned or summarised.

Private names of `interpreter` this module still uses (a note for U13a: public hooks would replace them):
`_Run` (subclassed for decision ids; `events`, `sched`, `execute`, `decision_test`), `_Scheduler` (subclassed:
`timers`, `ext`, `ext_i`, `ready`, `live`, `_step`, `_resume`, `publish`, `on_event`), `_walk`, `heapq`, `signal`.

PROVISIONAL choices (the spec is silent; listed in the unit report):
  - an event signature is an armored SSH signature in `event["signature"]` over the canonical JSON of the
    event without that key; namespace `org-event` for events and `org-snapshot` for snapshots;
  - the rung base is the newest snapshot of a signed chain (`seq`, `prev`, `root_id`);
  - the proposer's rungs come from the base manifest role named by `proposer_role` (default `improver`);
  - file maps follow a file symlink that resolves inside the root and refuse every other symlink;
  - the script collector convention (`ProcessCollector`, no longer the default) and an unreadable metric as an
    error row, never 0;
  - the time a resumed run spent down does not count toward its timeouts (the clock resumes at the last event).
"""

import dataclasses
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_change  # noqa: E402
import interpreter as it  # noqa: E402
import metric_collectors as mc  # noqa: E402
import validate_catalog as vc  # noqa: E402
import validate_manifest as vman  # noqa: E402

__all__ = (
    "UNENFORCED", "NO_OUTSIDE", "DEFAULT_FROZEN_OUTSIDE", "LedgerError", "DivergenceError", "OwnerKeyError",
    "FileMapError", "SnapshotError", "IntegrityError", "FrozenOutside", "RunLedger", "KeyRing", "SshKeygenVerifier",
    "SnapshotStore", "ProcessCollector", "RegistryCollector", "TurnBoundary", "TurnOrderError", "InboxFeed", "QueueFeed", "LiveScheduler", "OrgProcessHost", "OrgRuntime",
    "load_ring", "validate_stack", "event_payload", "snapshot_event", "build_file_map", "check_collisions",
)

UNENFORCED = object()  # pass as `snapshots` to run with no rung enforcement (tests, throwaway roots)
NS_EVENT = "org-event"
NS_SNAPSHOT = "org-snapshot"
ORG_ENTRIES = ("workflows", "briefs", "criteria", "schemas", "collectors", "checks", "bin")
ROOT_FILE = re.compile(r"(manifest|metrics[^/]*)\.(json|yaml|yml)|stack\.(json|yaml)")
MANIFEST_FILE = re.compile(r"manifest\.(json|yaml|yml)")
STACK_FILES = ("stack.yaml", "stack.json")
STACK_TOOLS = ("Read", "Grep", "Glob", "Edit", "Write", "Bash")
ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]*")
PROTECTED_STACK_KEYS = ("roles", "bin-env")
KEY_LINE = re.compile(r"(ssh-[a-z0-9-]+|sk-ssh-[a-z0-9@.-]+|ecdsa-sha2-[a-z0-9]+|sk-ecdsa-sha2-[a-z0-9@.-]+) \S+( [^\n]*)?")
PRINCIPAL = re.compile(r"[A-Za-z0-9._-]+")
GENESIS = "0" * 64
MIN_KEY = 32

# Files outside the org root that only the owner may change (spec 10, 13.1): the grammar (interpreter and
# validators), port contracts, harness, bindings, hooks, plugin metadata, CI and the repo tooling that runs tests.
# Relative to the repository root; a trailing slash names a directory. PROVISIONAL default.
_W = "agents/operating-model/skills/workflow/"
DEFAULT_FROZEN_OUTSIDE = (
    _W + "scripts/", _W + "contracts/", _W + "harness/", _W + "bindings/", _W + "SKILL.md",
    "agents/operating-model/hooks/", "agents/operating-model/.claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json", ".github/workflows/", ".claude/", "pyproject.toml", "uv.lock", "conftest.py",
)


class LedgerError(it.ControlFlow):
    """The ledger does not verify, or a run cannot be recovered from it."""


class DivergenceError(LedgerError):
    """A resumed run produced an event that differs from the one the ledger holds."""


class OwnerKeyError(Exception):
    """Private key material was offered to the runtime."""


class FileMapError(Exception):
    """A file map cannot be built safely."""


class SnapshotError(Exception):
    """The signed snapshot chain is broken."""


class IntegrityError(Exception):
    """A file about to run differs from the verified bytes."""


# ---------------------------------------------------------------- file maps


def check_collisions(paths):
    seen = {}
    for p in paths:
        k = unicodedata.normalize("NFC", p).casefold()
        if k in seen and seen[k] != p:
            raise FileMapError(f"{p}: paths collide when compared case-insensitively: '{seen[k]}' and '{p}'")
        seen[k] = p


def _read_file(full, rel, real_root):
    """Bytes of a regular file, or of a symlink that resolves to a regular file inside the root."""
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
    """Add the file or the tree `entry` (relative to `base`) to `out`. Bytecode caches are left out."""
    real_root = os.path.realpath(base)
    full = os.path.join(base, entry)
    if os.path.islink(full) and os.path.isdir(full):
        raise FileMapError(f"{entry}: directory symlink")
    if os.path.isdir(full):
        for dirpath, dirnames, filenames in os.walk(full, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__" or os.path.islink(os.path.join(dirpath, d)))
            for d in dirnames:
                dp = os.path.join(dirpath, d)
                if os.path.islink(dp):
                    raise FileMapError(f"{os.path.relpath(dp, base).replace(os.sep, '/')}: directory symlink")
            for fn in sorted(filenames):
                if fn.endswith(".pyc"):
                    continue
                fp = os.path.join(dirpath, fn)
                rel = os.path.relpath(fp, base).replace(os.sep, "/")
                out[rel] = _read_file(fp, rel, real_root)
    elif os.path.lexists(full) and not entry.endswith(".pyc"):
        out[entry] = _read_file(full, entry, real_root)


def build_file_map(root):
    """Map of org-root-relative path to bytes for the org root's own entries (spec section 1)."""
    root = str(root)
    out = {}
    for name in sorted(os.listdir(root)):
        if ROOT_FILE.fullmatch(name) or name in ORG_ENTRIES:
            _collect(root, name, out)
    check_collisions(list(out))
    return out


class FrozenOutside:
    """The path list of files outside the org root that are frozen (13.1), relative to `repo_root`.

    A missing repo root or an empty list is an error; `NO_OUTSIDE` says it on purpose.
    """

    def __init__(self, repo_root, paths, _explicit_none=False):
        if not _explicit_none and (repo_root is None or not paths):
            raise ValueError("FrozenOutside needs a repo root and paths; pass NO_OUTSIDE to opt out explicitly")
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


NO_OUTSIDE = FrozenOutside(None, (), _explicit_none=True)


# ---------------------------------------------------------------- the ledger


def _mac(key, entry):
    body = json.dumps({k: entry[k] for k in ("seq", "prev", "kind", "body")}, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()


class RunLedger:
    """Append-only JSON lines, each holding the MAC of the one before it, plus a `.head` file.

    A torn last line is dropped. The head file (HMAC over run id, entry count and last MAC, written by an atomic
    replace after every append) lets `verify_head` refuse a ledger that was cut back.
    """

    def __init__(self, path, key, readonly=False):
        if not isinstance(key, (bytes, bytearray)) or len(key) < MIN_KEY:
            raise ValueError(f"the ledger key must be at least {MIN_KEY} bytes")
        self.path, self.key, self.readonly, self.torn = str(path), bytes(key), readonly, False
        self.head_path = self.path + ".head"
        self._last, self._seq, self._good, self._run_id = GENESIS, 0, 0, None
        if os.path.exists(self.path):
            entries, _, self._good = self._load()
            if entries:
                self._last, self._seq = entries[-1]["mac"], entries[-1]["seq"]
                if entries[0]["kind"] == "header":
                    self._run_id = entries[0]["body"].get("run_id")

    def read(self):
        """The verified entries. Reading never moves this writer's position: only `__init__` and `append` do."""
        return self._load()[0]

    def _load(self):
        """(entries, their line bytes, byte length of the verified lines), all from one read of the file."""
        try:
            with open(self.path, "rb") as f:
                raw = f.read()
        except FileNotFoundError:
            return [], [], 0
        lines = raw.split(b"\n")
        self.torn = bool(lines.pop())
        entries, prev, good = [], GENESIS, 0
        for n, line in enumerate(lines, 1):
            try:
                entry = json.loads(line.decode("utf-8"))
                ok = isinstance(entry, dict) and all(k in entry for k in ("seq", "prev", "kind", "body", "mac"))
            except (ValueError, UnicodeDecodeError):
                ok = False
            if not ok:
                raise LedgerError(f"{self.path}: line {n} is not a ledger entry (strict UTF-8 JSON)")
            if entry["seq"] != n or entry["prev"] != prev:
                raise LedgerError(f"{self.path}: entry {n} does not follow the one before it")
            if not hmac.compare_digest(str(entry["mac"]), _mac(self.key, entry)):
                raise LedgerError(f"{self.path}: entry {n} has a bad signature")
            entries.append(entry)
            prev, good = entry["mac"], good + len(line) + 1
        return entries, lines, good

    def _head_mac(self, run_id, count, last):
        return hmac.new(self.key, f"head\n{run_id}\n{count}\n{last}".encode(), hashlib.sha256).hexdigest()

    def _write_head(self):
        head = {"run_id": self._run_id, "count": self._seq, "last": self._last}
        head["mac"] = self._head_mac(head["run_id"], head["count"], head["last"])
        tmp = self.head_path + ".tmp"
        with open(tmp, "w") as f:
            f.write(json.dumps(head, sort_keys=True))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.head_path)

    def append(self, kind, body):
        if self.readonly:
            raise LedgerError(f"{self.path}: replay would write a '{kind}' entry")
        size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        if size < self._good:
            raise LedgerError(f"{self.path}: the ledger shrank under this writer")
        if size > self._good:
            with open(self.path, "r+b") as f:
                f.seek(self._good)
                if b"\n" in f.read():  # whole lines another writer appended: refuse, never cut them
                    raise LedgerError(f"{self.path}: the ledger grew under this writer (a second writer?)")
                f.truncate(self._good)  # a torn tail: cut it before writing after it
        entry = {"seq": self._seq + 1, "prev": self._last, "kind": kind, "body": json.loads(json.dumps(body, default=str))}
        entry["mac"] = _mac(self.key, entry)
        line = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
        with open(self.path, "ab") as f:
            f.write(line.encode())
            f.flush()
            os.fsync(f.fileno())
        self._last, self._seq, self._good = entry["mac"], entry["seq"], self._good + len(line.encode())
        if kind == "header" and isinstance(entry["body"], dict):
            self._run_id = entry["body"].get("run_id")
        self._write_head()
        return entry

    def prefix(self, seq, mac):
        """The verified bytes of entries 1..seq (a collector's input), from the same read that verified them.
        Refused unless entry `seq` carries `mac`."""
        entries, lines, _ = self._load()
        if seq < 1 or len(entries) < seq or entries[seq - 1]["mac"] != mac:
            raise LedgerError(f"{self.path}: entry {seq} is not the one the metrics were computed from")
        return b"".join(line + b"\n" for line in lines[:seq])

    def verify_head(self, entries, expected_head=None):
        """Refuse a ledger that is shorter than its head file, belongs to another run, or has no valid head."""
        try:
            with open(self.head_path) as f:
                head = json.load(f)
            run_id, count, last, mac = head["run_id"], head["count"], head["last"], head["mac"]
            valid = hmac.compare_digest(str(mac), self._head_mac(run_id, count, last)) and isinstance(count, int)
        except FileNotFoundError:
            if len(entries) > 1:
                raise LedgerError(f"{self.path}: the head file is missing") from None
            valid, run_id, count, last = None, None, 0, None
        except (OSError, ValueError, KeyError, TypeError):
            valid = False
        if valid is False:
            raise LedgerError(f"{self.path}: the head file does not verify")
        if valid:
            first = entries[0]["body"].get("run_id") if entries and isinstance(entries[0]["body"], dict) else None
            if run_id != first:
                raise LedgerError(f"{self.path}: the ledger's run id differs from the head file's")
            if len(entries) < count:
                raise LedgerError(f"{self.path}: the ledger is shorter than its head file (rolled back?)")
            if count and entries[count - 1]["mac"] != last:
                raise LedgerError(f"{self.path}: entry {count} differs from the head file")
        if expected_head is not None:
            n, mac = expected_head
            if len(entries) < n or (n and entries[n - 1]["mac"] != mac):
                raise LedgerError(f"{self.path}: the ledger does not match the expected head")


# ---------------------------------------------------------------- the key ring (identity port: verify, revoke, list)


def event_payload(event):
    """The bytes a signature covers: canonical JSON of the event without its `signature` key."""
    body = {k: v for k, v in event.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _trusted_dirs():
    dirs = ["/usr/bin", "/bin", "/run/current-system/sw/bin", "/nix/var/nix/profiles/default/bin"]
    user = os.environ.get("USER")
    if user:
        dirs.append(f"/etc/profiles/per-user/{user}/bin")
    home = os.path.expanduser("~")
    if home and home != "~":
        dirs.append(os.path.join(home, ".nix-profile", "bin"))
    return dirs


class SshKeygenVerifier:
    """OpenSSH verification: `ssh-keygen -Y verify` against an allowed-signers file of public keys only.

    `ssh-keygen` is resolved once to an absolute path from a fixed trusted directory list, not from the caller's
    PATH, and runs with a minimal environment. If it cannot be found, every verification fails.
    """

    def __init__(self, ssh_keygen=None):
        self._dirs = _trusted_dirs()
        self.path = ssh_keygen
        if self.path is None:
            for d in self._dirs:
                cand = os.path.join(d, "ssh-keygen")
                if os.path.isfile(cand) and os.access(cand, os.X_OK):
                    self.path = cand
                    break

    def verify(self, principal, keys, payload, sig, namespace):
        if not self.path or not isinstance(principal, str) or not PRINCIPAL.fullmatch(principal) \
                or not isinstance(sig, str) or not sig or namespace not in (NS_EVENT, NS_SNAPSHOT):
            return False
        with tempfile.TemporaryDirectory(prefix="org-verify-") as tmp:
            allowed, sigfile = os.path.join(tmp, "allowed"), os.path.join(tmp, "sig")
            with open(allowed, "w") as f:
                for k in keys:
                    f.write(f'{principal} namespaces="{namespace}" {k}\n')
            with open(sigfile, "w") as f:
                f.write(sig)
            try:
                r = subprocess.run([self.path, "-Y", "verify", "-f", allowed, "-I", principal, "-n", namespace,
                                    "-s", sigfile], input=payload, capture_output=True, timeout=15,
                                   env={"PATH": ":".join(self._dirs), "LC_ALL": "C"})
            except (OSError, subprocess.TimeoutExpired):
                return False  # fail closed
            return r.returncode == 0


def _check_key_line(line):
    if not isinstance(line, str) or "PRIVATE KEY" in line:
        raise OwnerKeyError("the key ring takes public keys only; private key material was refused")
    if not KEY_LINE.fullmatch(line):
        raise ValueError(f"not a public key line: {line[:40]!r}")
    return line


class KeyRing:
    """Role name to public keys. `verify(event, signer)` asks the signer role's keys, never the claimed sender."""

    def __init__(self, keys, verifier=None):
        self._keys = {role: [_check_key_line(k) for k in lines] for role, lines in keys.items()}
        self._verifier = verifier or SshKeygenVerifier()

    def verify(self, event, signer, namespace=NS_EVENT):
        try:
            if not isinstance(event, dict) or not isinstance(event.get("signature"), str):
                return False
            keys = list(self._keys.get(signer) or [])
            if not keys:
                return False
            return self._verifier.verify(signer, keys, event_payload(event), event["signature"], namespace) is True
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


# ---------------------------------------------------------------- owner-signed snapshot chain (the base for rungs)


def _hashes(m):
    return {k: hashlib.sha256(v).hexdigest() for k, v in sorted(m.items())}


def snapshot_event(files, outside, root_id, seq, prev):
    """The event the owner signs (namespace `org-snapshot`): hashes of every org-root and listed outside file."""
    return {"type": "org.snapshot", "data": {"files": _hashes(files), "outside": _hashes(outside), "seq": seq,
                                              "prev": prev, "root_id": root_id}}


class SnapshotStore:
    """A chain of whole-root snapshots in a directory outside the org root: blobs plus `snapshots.jsonl`.

    Each line is signed by the owner and binds `seq`, `prev` (hash of the previous line of the same root) and
    `root_id`. The runtime verifies and reads; adding a snapshot is the owner's act.
    """

    def __init__(self, path):
        self.dir = str(path)
        self.file = os.path.join(self.dir, "snapshots.jsonl")

    def _lines(self):
        try:
            with open(self.file, encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    @staticmethod
    def _parse(raw):
        try:
            entry = json.loads(raw)
            data, sig = entry["data"], entry["signature"]
            if isinstance(data, dict) and isinstance(sig, str) and isinstance(data.get("root_id"), str):
                return data, sig
        except Exception:  # noqa: BLE001
            pass
        return None

    def next_event(self, files, outside, root_id, ring=None):
        """The event to sign next for `root_id`. With a `ring` it continues the verified chain."""
        seq, prev = 0, GENESIS
        if ring is not None:
            got = self.latest_valid(ring, root_id)
            if got:
                seq, prev = got["seq"], got["hash"]
        else:
            for raw in self._lines():
                parsed = self._parse(raw)
                if parsed and parsed[0]["root_id"] == root_id and isinstance(parsed[0].get("seq"), int):
                    seq, prev = parsed[0]["seq"], hashlib.sha256(raw.encode()).hexdigest()
        return snapshot_event(files, outside, root_id, seq + 1, prev)

    def add(self, event, signature, files, outside):
        os.makedirs(os.path.join(self.dir, "blobs"), exist_ok=True)
        for blob in list(files.values()) + list(outside.values()):
            p = os.path.join(self.dir, "blobs", hashlib.sha256(blob).hexdigest())
            if not os.path.exists(p):
                with open(p, "wb") as f:
                    f.write(blob)
        with open(self.file, "a") as f:
            f.write(json.dumps({"data": event["data"], "signature": signature}, sort_keys=True) + "\n")

    def latest_valid(self, ring, root_id):
        """The newest snapshot of the signed chain of `root_id`, or None. A break in the chain raises SnapshotError.

        A line that is not owner-signed is ignored. An owner-signed line that does not extend the chain (an older
        one appended, a gap) refuses the run: there is no fallback to an older snapshot.
        """
        last_seq, last_hash, best = 0, GENESIS, None
        for raw in self._lines():
            parsed = self._parse(raw)
            if parsed is None or parsed[0]["root_id"] != root_id:
                continue
            data, sig = parsed
            if not ring.verify({"type": "org.snapshot", "data": data, "signature": sig}, "owner", NS_SNAPSHOT):
                continue
            if data.get("seq") != last_seq + 1 or data.get("prev") != last_hash:
                raise SnapshotError(f"owner-signed snapshot {data.get('seq')} is out of sequence after {last_seq}")
            last_seq, last_hash, best = data["seq"], hashlib.sha256(raw.encode()).hexdigest(), data
        if best is None:
            return None
        maps = []
        try:
            for part in ("files", "outside"):
                m = {}
                for rel, digest in best[part].items():
                    with open(os.path.join(self.dir, "blobs", digest), "rb") as b:
                        blob = b.read()
                    if hashlib.sha256(blob).hexdigest() != digest:
                        raise ValueError(digest)
                    m[rel] = blob
                maps.append(m)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            raise SnapshotError(f"snapshot {last_seq}: a blob is missing or does not match its hash ({e})") from None
        return {"seq": last_seq, "hash": last_hash, "files": maps[0], "outside": maps[1]}


# ---------------------------------------------------------------- metrics


class CollectorError(Exception):
    pass


_COLLECTOR_PRELUDE = (
    "import sys\n"
    "path, key = sys.argv[1], sys.argv[2]\n"
    "src = sys.stdin.read()\n"
    "sys.argv = [path, key]\n"
    "exec(compile(src, path, 'exec'), {'__name__': '__main__', '__file__': path})\n"
)


class ProcessCollector:
    """Run `collectors/<name>.py` and read one JSON number from stdout. PROVISIONAL convention.

    The collector runs as `python -I -c <prelude> <path> <full key>` from the verified bytes (`bind`), in its own
    process group that is killed on timeout, with a minimal environment: ORG_METRIC_INPUT (a read-only copy of the
    run ledger), ORG_KEY, ORG_RUN, ORG_METRIC. Exit 0 with a finite JSON number is a value; anything else raises
    CollectorError, which the runtime records as an error: a metric is never recorded as zero by accident.
    """

    def __init__(self, root, timeout=60):
        self.root, self.timeout, self.files = os.path.realpath(str(root)), timeout, None

    def bind(self, files):
        self.files = files

    def _source(self, rel):
        if self.files is not None:
            if rel not in self.files:
                raise CollectorError(f"{rel}: collector is not in the verified file map")
            return self.files[rel]
        if not vc.relative_path_ok(rel, "collectors/", (".py",)) or not vc.file_under_root(self.root, rel):
            raise CollectorError(f"{rel}: collector is not a file inside the org root")
        with open(os.path.join(self.root, rel), "rb") as f:
            return f.read()

    def __call__(self, metric, entry, key, run_id, ledger_path):
        rel = entry.get("collector", "")
        source = self._source(rel)
        with tempfile.TemporaryDirectory(prefix="org-metric-") as tmp:
            copy = os.path.join(tmp, "ledger")
            with open(ledger_path, "rb") as f, open(copy, "wb") as g:
                g.write(f.read())
            os.chmod(copy, 0o444)
            env = {"PATH": os.environ.get("PATH", ""), "ORG_METRIC_INPUT": copy, "ORG_KEY": key, "ORG_RUN": run_id,
                   "ORG_METRIC": metric}
            try:
                p = subprocess.Popen([sys.executable, "-I", "-c", _COLLECTOR_PRELUDE, os.path.join(self.root, rel), key],
                                     env=env, cwd=tmp, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, start_new_session=True)
            except OSError as e:
                raise CollectorError(f"collector cannot start: {e.strerror}") from None
            try:
                out, err = p.communicate(source, timeout=self.timeout)
            except subprocess.TimeoutExpired:
                OrgProcessHost._killpg(p.pid)
                p.communicate()
                raise CollectorError("collector timed out") from None
        if p.returncode != 0:
            lines = err.decode("utf-8", errors="replace").strip().splitlines()
            raise CollectorError(lines[0] if lines else f"collector exited {p.returncode}")
        try:
            v = json.loads(out.decode("utf-8", errors="replace"))
        except ValueError:
            raise CollectorError("collector printed no JSON number") from None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
            raise CollectorError("collector printed no finite number")
        return v


# ---------------------------------------------------------------- feeds and the real-time scheduler


class QueueFeed:
    """An in-memory feed: `push` an event from anywhere, the driver polls it. Events must be strict JSON."""

    def __init__(self):
        self._q, self.closed, self.rejected = deque(), False, []

    def push(self, event):
        try:
            if not isinstance(event, dict):
                raise ValueError("not an object")
            json.dumps(event, allow_nan=False)
        except (TypeError, ValueError) as e:
            self.rejected.append(f"event is not strict JSON: {e}")
            return
        self._q.append(event)

    def close(self):
        self.closed = True

    def poll(self):
        out = list(self._q)
        self._q.clear()
        return out

    def ack(self):
        pass


def _reject_constant(name):
    raise ValueError(f"{name} is not allowed")


def _depth_ok(text, limit=64):
    depth, in_str, esc = 0, False, False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return False
        elif ch in "]}":
            depth -= 1
    return True


class InboxFeed:
    """A directory of `*.json` event files, each delivered once, in name order.

    Files open with `O_NOFOLLOW | O_NONBLOCK` and must be regular; they are read from the descriptor under a size
    cap and parsed as strict JSON objects (no NaN or Infinity, bounded nesting). A bad file is renamed `.rejected`.
    A good file is renamed `.seen` by `ack()`, which the driver calls after it has journaled the event, so a crash
    in between redelivers (decision ids make that harmless). At most `max_per_poll` events per poll and
    `max_total` per feed.
    """

    def __init__(self, path, max_bytes=1_000_000, max_per_poll=100, max_total=10000):
        self.dir, self.max_bytes, self.max_per_poll, self.max_total = str(path), max_bytes, max_per_poll, max_total
        self.closed, self.rejected, self.total, self._pending, self._capped = False, [], 0, [], False

    def _load(self, path):
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("not a regular file")
            raw = b""
            while len(raw) <= self.max_bytes:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                raw += chunk
            if len(raw) > self.max_bytes:
                raise ValueError("over the size limit")
        finally:
            os.close(fd)
        text = raw.decode("utf-8")
        if not _depth_ok(text):
            raise ValueError("nested too deeply")
        event = json.loads(text, parse_constant=_reject_constant)
        if not isinstance(event, dict):
            raise ValueError("not a JSON object")
        return event

    def poll(self):
        out = []
        try:
            names = sorted(os.listdir(self.dir))
        except OSError as e:
            self.rejected.append(f"{self.dir}: {e.strerror}")
            return out
        for name in names:
            if not name.endswith(".json"):
                continue
            if len(out) >= self.max_per_poll:
                break
            if self.total >= self.max_total:
                if not self._capped:
                    self.rejected.append("run cap reached: further events are not delivered")
                    self._capped = True
                break
            path = os.path.join(self.dir, name)
            try:
                event = self._load(path)
            except Exception as e:  # noqa: BLE001  every escape is a rejected file, never a crash
                self.rejected.append(f"{name}: {type(e).__name__}: {e}")
                try:
                    os.replace(path, path[:-5] + ".rejected")
                except OSError:
                    pass
                continue
            self._pending.append(path)
            self.total += 1
            out.append(event)
        return out

    def ack(self):
        for path in self._pending:
            try:
                os.replace(path, path[:-5] + ".seen")
            except OSError:
                pass
        self._pending = []


class LiveScheduler(it._Scheduler):
    """The U13a scheduler on a wall clock, in two phases.

    Replay phase (a resumed run): behaves like the base scheduler, jumping the virtual clock over the journaled
    timers and events up to `replay_end`. Live phase: `now` follows `clock()` from where the replay ended; due
    timers and host events fire, then feed events (journaled by `journal` before `feed.ack()`), else it sleeps.
    A fresh run is live from the start. `go_live()` also fires before a live host call during replay.
    """

    def __init__(self, ext, feed, clock, sleep, journal, poll, replay_end=None):
        self._clock, self._virt, self._origin = clock, 0.0, None
        super().__init__(ext)
        self.feed, self._sleep, self._journal, self._poll = feed, sleep, journal, poll
        self.replay_end = replay_end
        if replay_end is None:
            self.go_live()

    def _get_now(self):
        if self._origin is None:
            return self._virt
        return self._origin[0] + (self._clock() - self._origin[1])

    def _set_now(self, v):
        if self._origin is None:
            self._virt = v

    now = property(_get_now, _set_now)

    def go_live(self):
        if self._origin is None:
            self._origin = (self._virt, self._clock())

    def _fire_timers(self, t):
        while self.timers and self.timers[0][0] <= t:
            _, _, p, token, exc = it.heapq.heappop(self.timers)
            if not p.done and p.token == token:
                self._resume(p, None, exc)

    def _fire_ext(self, t):
        while self.ext_i < len(self.ext) and self.ext[self.ext_i][0] <= t:
            event = self.ext[self.ext_i][1]
            self.ext_i += 1
            self.publish(event)

    def run(self):
        while self.live > 0:
            if self.ready:
                p, value, exc = self.ready.popleft()
                self._step(p, value, exc)
                continue
            nt = self.timers[0][0] if self.timers else None
            ne = self.ext[self.ext_i][0] if self.ext_i < len(self.ext) else None
            if self._origin is None:  # replay phase: the base scheduler's jumps
                due = min(t for t in (nt, ne) if t is not None) if (nt is not None or ne is not None) else None
                if due is None or due > self.replay_end:
                    self.go_live()
                    continue
                if nt is not None and (ne is None or nt <= ne):
                    self.now = max(self.now, nt)
                    self._fire_timers(nt)
                else:
                    self.now = max(self.now, ne)
                    self._fire_ext(ne)
                continue
            now = self.now
            if nt is not None and nt <= now:
                self._fire_timers(now)
                continue
            if ne is not None and ne <= now:
                self._fire_ext(now)
                continue
            fed = self.feed.poll()
            if fed:
                for event in fed:
                    try:
                        self._journal(now, event)
                    except Exception:  # noqa: BLE001  an event that cannot be journaled is not delivered
                        getattr(self.feed, "rejected", []).append("event could not be journaled")
                        continue
                    self.publish(event)
                ack = getattr(self.feed, "ack", None)
                if ack:
                    ack()
                continue
            nxt = [t for t in (nt, ne) if t is not None]
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
        self.root = getattr(inner, "root", None)

    def scheduled_events(self):
        return self._inner.scheduled_events()

    def confined(self, rel):
        return self._inner.confined(rel)

    def _no(self, what):
        raise LedgerError(f"replay needs a live {what}: the ledger does not hold that answer")

    def run_step(self, req):
        self._no(f"step '{req.key}'")

    def run_check(self, name, key, evidence, rungs=None):
        self._no(f"check '{name}' on '{key}'")

    def run_judge(self, req):
        self._no(f"judge on '{req.key}'")

    def verify_signed(self, event, signer):
        self._no("signature check")

    def change(self):
        self._no("change query")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


class _VerifiedHost:
    """Before a live exec of a check, a `bin/` command or `agent_run.py`, compare the bytes on disk with the
    verified ones and refuse on a mismatch. (The window between this read and the exec is closed for hosts that
    exec from a descriptor; agent children must not be able to write the org root at all.)"""

    def __init__(self, inner, root, files):
        self._inner, self._root, self._files = inner, os.path.realpath(str(root)), files
        agent = getattr(inner, "agent_run", None)
        self._agent = agent if agent and os.path.isfile(agent) else None
        self._agent_hash = None
        if self._agent:
            with open(self._agent, "rb") as f:
                self._agent_hash = _sha(f.read())
        self.root = getattr(inner, "root", None)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _check(self, rel):
        verified = self._files.get(rel)
        full = os.path.join(self._root, rel)
        if verified is None:
            if os.path.lexists(full):
                raise IntegrityError(f"{rel}: is not in the verified file map")
            return  # absent then and now: the host refuses it itself
        try:
            current = _read_file(full, rel, self._root)
        except (OSError, FileMapError) as e:
            raise IntegrityError(f"{rel}: changed since the run started ({e})") from None
        if _sha(current) != _sha(verified):
            raise IntegrityError(f"{rel}: changed since the run started")

    def _check_agent(self):
        if self._agent:
            with open(self._agent, "rb") as f:
                if _sha(f.read()) != self._agent_hash:
                    raise IntegrityError("agent_run.py: changed since the run started")

    def run_step(self, req):
        if req.command == "agent-run":
            self._check_agent()
        else:
            self._check(f"bin/{req.command}")
        return self._inner.run_step(req)

    def run_check(self, name, key, evidence, rungs=None):
        self._check(f"checks/{name}.py")
        return self._inner.run_check(name, key, evidence, rungs)

    def run_judge(self, req):
        self._check_agent()
        return self._inner.run_judge(req)


class _JournalHost:
    """Answers host calls from the ledger while it holds an answer, else asks the live host and records it.

    Real step durations are journaled as the host returned them: the virtual replay rebuilds the same timeline
    as the live run, and a live run's own `Sleep(now + duration)` is already in the past."""

    def __init__(self, inner, ring, ledger, journal, fed):
        self.inner, self.ring, self.ledger = inner, ring, ledger
        self.journal, self.fed, self.sched = journal, fed, None
        self.root = getattr(inner, "root", None)

    def _take(self, kind, key):
        q = self.journal.get((kind, key))
        if q:
            return True, q.popleft()
        if kind != "verify" and self.sched is not None and hasattr(self.sched, "go_live"):
            self.sched.go_live()  # the journal is exhausted: from here on the clock is the wall clock
        return False, None

    def _put(self, kind, key, result):
        self.ledger.append("host", {"call": kind, "key": key, "result": result})

    def scheduled_events(self):
        return list(self.inner.scheduled_events()) + [(t, e) for t, e in self.fed]

    def confined(self, rel):
        return self.inner.confined(rel)

    def verify_signed(self, event, signer):
        sig = json.dumps(event.get("signature") if isinstance(event, dict) else None, default=str)
        k = _sha(event_payload(event) + b"\n" + signer.encode() + b"\n" + sig.encode())
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
        self._put("step", req.key, dataclasses.asdict(out))
        return out

    def run_check(self, name, key, evidence, rungs=None):
        hit, res = self._take("check", f"{name}\n{key}")
        if not hit:
            try:
                res = bool(self.inner.run_check(name, key, evidence, rungs))
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

    def change(self):
        hit, res = self._take("change", "")
        if hit:
            return res
        fn = getattr(self.inner, "change", None)
        res = fn() if fn else {"head": None, "worktree": None}
        self._put("change", "", res)
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


class _OrgRun(it._Run):
    """`_Run` plus a ledger row for each decision id the interpreter accepted (P33).

    The interpreter is the one authority: it ignores an event with no string id and an id it already consumed.
    Replay re-consumes the ids of a resumed run, so nothing here needs to remember them across a resume."""

    def __init__(self, interp, rid, ledger, recorded):
        super().__init__(interp, rid)
        self._ledger, self._recorded = ledger, set(recorded)

    def decision_test(self, event, full, item=None, signer="owner"):
        dec, why = super().decision_test(event, full, item, signer)
        if why:
            return dec, why
        eid = event["id"]  # the interpreter has checked it is a non-empty string
        if eid not in self._recorded:
            self._ledger.append("decision-id", {"id": eid, "key": full})
            self._recorded.add(eid)
        return dec, None


class _StageError(Exception):
    pass


class OrgProcessHost(it.ProcessHost):
    """`ProcessHost` that gives `agent-run` its environment and runs model judges through it (6.1)."""

    AGENT_RUN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_run.py")

    def __init__(self, root, session_dir, env=None, agent_run=None, events=(), verify=None):
        super().__init__(root, agent_run=agent_run or self.AGENT_RUN, events=events, verify=verify)
        self.session_dir = os.path.realpath(str(session_dir))
        self.env = dict(env or {})
        self.stack = {"bin-env": {}, "roles": {}}
        self._workflow_of = lambda key: None
        os.makedirs(self.session_dir, exist_ok=True)

    def bind_stack(self, stack, workflow_of):
        """The stack data (a plain dict: `bin-env` and `roles`, already checked) and a key-to-workflow function."""
        self.stack, self._workflow_of = stack, workflow_of

    def _bin_env(self, key, workflow=None):
        """Exactly the names the stack lists for the step's workflow; never ORG_, LD_, DYLD_ or PATH."""
        wf = workflow or self._workflow_of(key)
        names = (self.stack.get("bin-env") or {}).get(wf) or {}
        return {n: v for n, v in names.items() if _env_name_ok(n) and isinstance(v, str)}

    @staticmethod
    def _killpg(pid):
        try:
            os.killpg(pid, it.signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def _env(self, req, item=None):
        env = {"PATH": os.environ.get("PATH", ""), "ORG_ROOT": self.root, "ORG_RUN": req.run_id, "ORG_KEY": req.key,
               "ORG_SESSION_DIR": self.session_dir}
        env.update({k: v for k, v in self.env.items() if k.startswith("ORG_") and k not in env})
        if item is not None:
            env["ORG_ITEM"] = str(item)
        return env

    def _stage_input(self, argv, input_file):
        """agent-run reads its input file only from the session directory or the org root, and U13a writes it to
        a private temporary directory: copy it (read-only) into the session directory and point `--input` there."""
        argv = list(argv)
        if not input_file or input_file not in argv:
            return argv
        if os.path.realpath(input_file).startswith(self.session_dir + os.sep):
            return argv
        try:
            dst_dir = os.path.join(self.session_dir, "inputs")
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, secrets.token_hex(8) + ".json")
            with open(input_file, "rb") as f:
                data = f.read()
            with open(dst, "wb") as f:
                f.write(data)
            os.chmod(dst, 0o444)
        except OSError as e:
            raise _StageError(f"input file cannot be staged: {e.strerror or type(e).__name__}") from None
        return [dst if a == input_file else a for a in argv]

    def _agent_run(self, argv, input_file, env, stdin, limit):
        """(stdout, stderr, seconds, exit code, timed out); text decoded with replacement, never raising."""
        try:
            argv = self._stage_input(argv, input_file)
        except _StageError as e:
            return None, str(e), 0.0, 127, False
        try:
            p = subprocess.Popen([sys.executable, self.agent_run] + argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=env, cwd=self.root, start_new_session=True)
        except OSError as e:
            return None, f"cannot start: {e.strerror}", 0.0, 127, False
        t0 = time.monotonic()
        try:
            out, err = p.communicate(stdin.encode(), timeout=limit)
        except subprocess.TimeoutExpired:
            self._killpg(p.pid)
            p.communicate()
            return None, None, None, -9, True
        return (out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace"),
                time.monotonic() - t0, p.returncode, False)

    def run_step(self, req):
        if req.command != "agent-run":
            env = self._bin_env(req.key, getattr(req, "workflow", None))
            return super().run_step(dataclasses.replace(req, shell={**req.shell, "environment": env}))
        out, err, dur, code, timed_out = self._agent_run(req.argv[1:], req.input_file, self._env(req),
                                                         json.dumps(req.input, default=str), req.limit)
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
        try:
            out, err, dur, code, timed_out = self._agent_run(req.argv[1:], req.input_file, self._env(req, req.item), "",
                                                             3600)
            if timed_out or code != 0 or out is None:
                return None
            event = json.loads(out)["event"]
            d = event["data"]
            if not isinstance(event, dict) or not isinstance(d, dict):
                return None
            if (event.get("type") != "org.rubric-verdict" or d.get("run") != req.run_id or d.get("task") != req.key
                    or d.get("item") != req.item):
                return None
            return {"invocation": req.invocation, "type": event["type"],
                    "data": {"run": d["run"], "task": d["task"], "item": d["item"], "verdict": d.get("verdict")}}
        except Exception:  # noqa: BLE001  anything odd in the agent's output is no verdict
            return None


# ---------------------------------------------------------------- the stack document (8.6)


def _env_name_ok(name):
    return (isinstance(name, str) and ENV_NAME.fullmatch(name) is not None and name != "PATH"
            and not name.startswith(("ORG_", "LD_", "DYLD_")))


def validate_stack(stack, manifest):
    """The first problem in a stack document as `(dotted key path, reason)`, or None. Keys other than `bin-env`
    and `roles` are outside the spec and are not checked (8.6)."""
    if not isinstance(stack, dict):
        return "stack", "must be a map"
    workflows, roles = manifest.get("workflows") or {}, manifest.get("roles") or {}
    env = stack.get("bin-env", {})
    if not isinstance(env, dict):
        return "bin-env", "must be a map"
    for wf, names in env.items():
        if wf not in workflows:
            return f"bin-env.{wf}", "workflow is not listed in the manifest"
        if not isinstance(names, dict):
            return f"bin-env.{wf}", "must be a map"
        for name, value in names.items():
            if not _env_name_ok(name):
                return f"bin-env.{wf}.{name}", "name is not allowed"
            if not isinstance(value, str) or "\0" in value:
                return f"bin-env.{wf}.{name}", "value must be a string"
    table = stack.get("roles", {})
    if not isinstance(table, dict):
        return "roles", "must be a map"
    for wf, entries in table.items():
        if wf not in workflows:
            return f"roles.{wf}", "workflow is not listed in the manifest"
        if not isinstance(entries, dict):
            return f"roles.{wf}", "must be a map"
        for role, entry in entries.items():
            at = f"roles.{wf}.{role}"
            if role not in roles:
                return at, "role is not listed in the manifest"
            if not isinstance(entry, dict):
                return at, "must be a map"
            for key in entry:
                if key not in ("tools", "workdir"):
                    return f"{at}.{key}", "unknown key"
            tools = entry.get("tools", [])
            if not isinstance(tools, list):
                return f"{at}.tools", "must be a list"
            for i, tool in enumerate(tools):
                if tool not in STACK_TOOLS:
                    return f"{at}.tools", f"'{tool}' is not one of {', '.join(STACK_TOOLS)}"
                if tool in tools[:i]:
                    return f"{at}.tools", f"'{tool}' is listed twice"
            if "workdir" in entry:
                var, vars_ = entry["workdir"], env.get(wf) or {}
                if not isinstance(var, str) or var not in vars_:
                    return f"{at}.workdir", f"'{var}' is not a bin-env variable of this workflow"
                if not vars_[var].startswith("/"):
                    return f"{at}.workdir", f"'{var}' must be an absolute path"
    return None


def _parse_bytes(name, data):
    """A document parsed from bytes with the 2.1 loader, or None when it does not load."""
    with tempfile.TemporaryDirectory(prefix="org-parse-") as tmp:
        path = os.path.join(tmp, name)
        with open(path, "wb") as f:
            f.write(data)
        try:
            return vc.load_document(path)
        except (vc.LoadError, vc.UsageError):
            return None


def _stack_changes(base_files, new_files):
    """`(path, rung)` for a stack change, classified per top-level key (P53); an unparseable stack is frozen."""
    changed = [p for p in STACK_FILES if base_files.get(p) != new_files.get(p)]
    if not changed:
        return []
    docs = []
    for files in (base_files, new_files):
        present = [p for p in STACK_FILES if files.get(p) is not None]
        if len(present) > 1:
            return [(changed[0], "frozen")]
        doc_ = {} if not present else _parse_bytes(present[0], files[present[0]])
        if not isinstance(doc_, dict):
            return [(changed[0], "frozen")]
        docs.append(doc_)
    keys = {k for k in set(docs[0]) | set(docs[1]) if docs[0].get(k) != docs[1].get(k)}
    if not keys:
        return []  # the same content in the other format
    return [(changed[0], "protected" if keys & set(PROTECTED_STACK_KEYS) else "free")]


# ---------------------------------------------------------------- the runtime


def _digest(files):
    h = hashlib.sha256()
    for k in sorted(files):
        h.update(k.encode() + b"\0" + hashlib.sha256(files[k]).digest())
    return h.hexdigest()


class RegistryCollector:
    """The default per-node collector: the metric over the ledger so far, through the registry (P64).

    Same call shape as `ProcessCollector`. A metric with no value raises `NoValue` (a `reason` row), a collector
    failure `CollectorError` (an `error` row). The input is the run writer's verified bytes (`bind_ledger`). A metric
    whose sources the registry serves but no built-in computes (an org-authored metric) goes to `fallback`, the
    catalog's own collector script, so the catalog `collector` field keeps its meaning."""

    def __init__(self, registry, fallback=None):
        self.registry, self.fallback, self.ledger = registry, fallback, None

    def bind(self, files):
        if hasattr(self.fallback, "bind"):
            self.fallback.bind(files)

    def bind_ledger(self, ledger):
        self.ledger = ledger

    def __call__(self, metric, entry, key, run_id, ledger_path):
        if self.ledger is not None:
            data = self.ledger.prefix(self.ledger._seq, self.ledger._last)
        else:
            with open(ledger_path, "rb") as f:
                data = f.read()
        res = self.registry.compute(metric, entry, {mc.RUN_LEDGER: data}, key)
        if self.fallback is not None and res.get("reason") == f"no collector computes {metric}":
            return self.fallback(metric, entry, key, run_id, ledger_path)
        if "reason" in res:
            raise mc.NoValue(res["reason"])
        if "error" in res:
            raise CollectorError(res["error"])
        return res["value"]


class TurnOrderError(Exception):
    """A turn-boundary entry was asked for out of the P61 order; nothing was appended."""


def _ref(e):
    return {"seq": e["seq"], "mac": e["mac"]}


class TurnBoundary:
    """The P61 order as ledger entries, for one turn of an agent session (spec 13.3, P63).

    export (the U11 session record's digest) -> one org.metric per catalog metric -> reflection -> turn-complete.
    Each call reads the ledger through a separate read-only view, verifies the chain and the head file, and refuses
    (TurnOrderError, nothing appended) when its predecessors are missing. It writes only through `writer`, the run's
    own `RunLedger`, and only while that writer's last entry is the file's last entry: a second writer, a rollback
    or a ledger of another run raises LedgerError. With no writer (no run in this runtime) it only reads. It runs no
    reflection and compacts nothing: `compaction_allowed(turn)` only reads the ledger.
    """

    def __init__(self, path, key, writer, catalog, registry, run_id=None):
        self.path, self.key, self.ledger = str(path), bytes(key), writer
        self.catalog, self.registry, self.run_id = catalog, registry, run_id

    @staticmethod
    def _turn(turn):
        if not isinstance(turn, str) or not 0 < len(turn) <= 200:
            raise TurnOrderError("a turn id is a string of 1 to 200 characters")
        return turn

    def _entries(self):
        """The verified entries of this run's ledger, or LedgerError."""
        led = RunLedger(self.path, self.key, readonly=True)
        es = led.read()
        led.verify_head(es)
        if not es or es[0]["kind"] != "header" or not isinstance(es[0]["body"], dict):
            raise LedgerError(f"{self.path}: no header: no run to record a turn for")
        if self.run_id is not None and es[0]["body"].get("run_id") != self.run_id:
            raise LedgerError(f"{self.path}: the ledger belongs to another run")
        return es

    def _state(self, turn, es):
        st = {"export": None, "metrics": {}, "reflection": None, "complete": None}
        for e in es:
            b = e["body"]
            if not (e["kind"].startswith("org.") and isinstance(b, dict) and b.get("turn") == turn):
                continue
            if e["kind"] == "org.session-export":
                st["export"] = e
            elif e["kind"] == "org.metric" and b.get("at") == "turn":
                st["metrics"].setdefault(b.get("metric"), e)
            elif e["kind"] == "org.reflection":
                st["reflection"] = e
            elif e["kind"] == "org.turn-complete":
                st["complete"] = e
        return st

    def _open(self, turn):
        self._turn(turn)
        if self.ledger is None:
            raise TurnOrderError("no run in this runtime: run or resume first; the turn seam never opens a writer")
        es = self._entries()
        if (es[-1]["seq"], es[-1]["mac"]) != (self.ledger._seq, self.ledger._last):
            raise LedgerError(f"{self.path}: the ledger changed under this run's writer")
        st = self._state(turn, es)
        st["last"] = es[-1]
        if st["complete"]:
            raise TurnOrderError(f"turn {turn}: already complete")
        return st

    def _full(self, st):
        return self.catalog is not None and set(st["metrics"]) >= set(self.catalog)

    def export(self, turn, record):
        st = self._open(turn)
        if st["export"]:
            raise TurnOrderError(f"turn {turn}: the session record is already exported")
        if not isinstance(record, (bytes, bytearray)):
            raise TypeError("the session record must be bytes")
        return self.ledger.append("org.session-export", {"turn": turn, "sha256": _sha(bytes(record)),
                                                         "bytes": len(record)})

    def collect(self, turn, record):
        st = self._open(turn)
        if not st["export"]:
            raise TurnOrderError(f"turn {turn}: metrics before the session record export")
        if self.catalog is None:
            raise TurnOrderError("no catalog loaded: run, resume or replay first")
        if not isinstance(record, (bytes, bytearray)) or _sha(bytes(record)) != st["export"]["body"]["sha256"]:
            raise TurnOrderError(f"turn {turn}: the record differs from the exported one")
        if self._full(st):
            raise TurnOrderError(f"turn {turn}: metrics are already recorded")
        sha = {"sha256": st["export"]["body"]["sha256"]}
        if st["metrics"]:  # a kill between rows: finish with the boundary the first rows used
            boundary = next(iter(st["metrics"].values()))["body"]["inputs"][mc.RUN_LEDGER]
        else:
            boundary = _ref(st["last"])
        inputs = {mc.RUN_LEDGER: self.ledger.prefix(boundary["seq"], boundary["mac"]),
                  mc.SESSION_RECORD: bytes(record)}
        out, parsed = [], {}
        for m in sorted(self.catalog):
            if m in st["metrics"]:
                continue
            res = self.registry.compute(m, self.catalog[m], inputs, None, parsed)
            out.append(self.ledger.append("org.metric", {"metric": m, "at": "turn", "turn": turn,
                                                         "inputs": {mc.RUN_LEDGER: boundary,
                                                                    mc.SESSION_RECORD: sha}, **res}))
        return out

    def reflect(self, turn, ref):
        st = self._open(turn)
        if not (st["export"] and self._full(st)):
            raise TurnOrderError(f"turn {turn}: reflection before the turn's metrics")
        if st["reflection"]:
            raise TurnOrderError(f"turn {turn}: the reflection is already recorded")
        if not isinstance(ref, str) or not ref:
            raise TurnOrderError("a reflection reference is a non-empty string")
        return self.ledger.append("org.reflection", {"turn": turn, "ref": ref})

    def complete(self, turn):
        st = self._open(turn)
        exp, refl = st["export"], st["reflection"]
        if not (exp and self._full(st) and refl):
            raise TurnOrderError(f"turn {turn}: turn-complete needs the export, the metrics and the reflection")
        rows = [st["metrics"][m] for m in sorted(self.catalog)]
        if not (exp["seq"] < min(r["seq"] for r in rows) and max(r["seq"] for r in rows) < refl["seq"]):
            raise TurnOrderError(f"turn {turn}: export, metrics and reflection are out of order")
        return self.ledger.append("org.turn-complete", {"turn": turn, "export": _ref(exp),
                                                        "metrics": [_ref(r) for r in rows],
                                                        "reflection": _ref(refl)})

    def compaction_allowed(self, turn, record=None):
        """True only when this run's verified ledger holds the turn's turn-complete and the entries it names, in
        order; with `record`, also only when that is the exported session record."""
        try:
            es = self._entries()
        except (LedgerError, OSError):
            return False
        if not isinstance(turn, str):
            return False
        done = next((e for e in es if e["kind"] == "org.turn-complete" and isinstance(e["body"], dict)
                     and e["body"].get("turn") == turn), None)
        if done is None:
            return False
        b = done["body"]

        def at(r, kind):
            try:
                e = es[r["seq"] - 1]
            except (TypeError, KeyError, IndexError):
                return None
            ok = e["mac"] == r["mac"] and e["kind"] == kind and e["body"].get("turn") == turn
            return e["seq"] if ok else None

        seqs = [at(b.get("export"), "org.session-export")] + [at(r, "org.metric") for r in b.get("metrics") or []]
        seqs += [at(b.get("reflection"), "org.reflection")]
        if record is not None and (seqs[0] is None or not isinstance(record, (bytes, bytearray))
                                   or es[seqs[0] - 1]["body"].get("sha256") != _sha(bytes(record))):
            return False
        return len(seqs) > 2 and None not in seqs and seqs[0] < min(seqs[1:-1]) and max(seqs[1:-1]) < seqs[-1] \
            < done["seq"]


def _no_collector(*args, **kw):
    raise LedgerError("replay would run a collector")


class _Loaded:
    def __init__(self, errs=(), workflows=None, catalog=None, manifest=None, files=None, snap=None, stack=None):
        self.errs, self.workflows, self.catalog = list(errs), workflows, catalog
        self.manifest, self.files, self.snap, self.stack = manifest, files, snap, stack


class OrgRuntime:
    """Load, refuse, run, resume and replay workflows of one org root against a host and a ledger.

    `snapshots` (a `SnapshotStore`, or `UNENFORCED`) and `frozen` (a `FrozenOutside`, or `NO_OUTSIDE`) are
    required: leaving rung enforcement out has to be written down. A caller-chosen run id needs
    `allow_run_id=True` (tests only); an id any earlier ledger in the same directory used is refused.
    """

    def __init__(self, root, *, ledger_path, ledger_key, ring, host, snapshots, frozen, proposer_rungs=None,
                 proposer_role="improver", collector=None, clock=time.monotonic, sleep=time.sleep, poll=1.0,
                 root_id=None, allow_run_id=False, used_ids_path=None, registry=None):
        if not isinstance(ledger_key, (bytes, bytearray)) or len(ledger_key) < MIN_KEY:
            raise ValueError(f"the ledger key must be at least {MIN_KEY} bytes")
        if proposer_rungs is not None and "frozen" in proposer_rungs:
            raise ValueError("a proposer may never be given the 'frozen' rung")
        self.root, self.ledger_path, self.ledger_key = str(root), str(ledger_path), bytes(ledger_key)
        self.ring, self.host, self.snapshots, self.frozen = ring, host, snapshots, frozen
        self.proposer_rungs, self.proposer_role = proposer_rungs, proposer_role
        self.registry = registry or mc.default_registry()
        self.collector = collector or RegistryCollector(self.registry, ProcessCollector(self.root))
        self._ledger, self._catalog, self._run_id = None, None, None  # the last run's, for `turn_boundary`
        self.clock, self.sleep, self.poll = clock, sleep, poll
        self.root_id = root_id or hashlib.sha256(os.path.realpath(self.root).encode()).hexdigest()[:32]
        self.allow_run_id = allow_run_id
        self.used_ids_path = str(used_ids_path or os.path.join(os.path.dirname(os.path.abspath(self.ledger_path)),
                                                               "used-run-ids"))

    # -- load

    def _rungs_for(self, base_files):
        if self.proposer_rungs is not None:
            return set(self.proposer_rungs)
        for name, data in base_files.items():  # the BASE manifest: a proposer cannot grant itself rungs
            if MANIFEST_FILE.fullmatch(name) and data is not None:
                try:
                    man = json.loads(data) if name.endswith(".json") else __import__("yaml").safe_load(data)
                    rungs = man["roles"][self.proposer_role]["rungs"]
                    if isinstance(rungs, list) and all(isinstance(r, str) for r in rungs):
                        return set(rungs) - {"frozen"}
                except Exception:  # noqa: BLE001
                    break
        return {"free", "ordinary"}

    def _rung_refusals(self, files):
        """(refusals, snapshot info)."""
        if self.snapshots is UNENFORCED:
            return [], None
        try:
            base = self.snapshots.latest_valid(self.ring, self.root_id)
        except SnapshotError as e:
            return [f"run refused: snapshot: {e}"], None
        if base is None:
            return ["run refused: snapshot: no owner-signed snapshot to compare against"], None
        snap = {"seq": base["seq"], "hash": base["hash"]}
        errs = []
        try:
            out = self.frozen.map()
        except FileMapError as e:
            return [f"run refused: {e}"], snap
        for p in sorted(set(base["outside"]) | set(out)):
            if base["outside"].get(p) != out.get(p):
                errs.append(f"run refused: {p}: change needs rung 'frozen' and has no owner signature")
        if base["files"] != files:
            allowed = self._rungs_for(base["files"])
            for path, rung in _stack_changes(base["files"], files):  # per key (P53); U15 sees no stack file
                if rung not in allowed:
                    errs.append(f"run refused: {path}: change needs rung '{rung}' and has no owner signature")
            paths = (set(base["files"]) | set(files)) - set(STACK_FILES)
            b = {p: base["files"].get(p) for p in paths}
            n = {p: files.get(p) for p in paths}
            _, refused = check_change.check_change(b, n, allowed)
            for path, _task, _row, rung in sorted(refused, key=lambda e: (e[0], e[3])):
                errs.append(f"run refused: {path}: change needs rung '{rung}' and has no owner signature")
        return errs, snap

    def _load(self, name):
        """Everything is parsed from the verified file-map bytes, materialised in a private temporary directory."""
        try:
            files = build_file_map(self.root)
        except (FileMapError, OSError) as e:
            return _Loaded([f"run refused: {e}"])
        errs, snap = self._rung_refusals(files)
        if errs:
            return _Loaded(errs, files=files, snap=snap)
        mans = [n for n in files if MANIFEST_FILE.fullmatch(n)]
        if len(mans) != 1:
            return _Loaded([f"run refused: manifest: need exactly one manifest file, found {len(mans)}"], files=files)
        mname = mans[0]
        cat_files = sorted(n for n in files if n.startswith("metrics") and ROOT_FILE.fullmatch(n))
        with tempfile.TemporaryDirectory(prefix="org-load-") as tmp:
            for rel, data in files.items():
                dst = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as f:
                    f.write(data)
            try:
                manifest = vc.load_document(os.path.join(tmp, mname))
                docs = [(n, vc.load_document(os.path.join(tmp, n))) for n in cat_files]
            except (vc.LoadError, vc.UsageError) as e:
                return _Loaded([f"run refused: {mname}: {getattr(e, 'msg', e)}"], files=files)
            catalog, cerrs = vc.merge_catalogs(docs)
            cerrs = cerrs or vc.validate_catalog(docs, tmp)
            if cerrs:
                label = cat_files[0] if len(cat_files) == 1 else "metrics"
                return _Loaded([f"run refused: {label}: {cerrs[0]}"], files=files)
            merrs = vman.validate_manifest(manifest, catalog, tmp)
            if merrs:
                return _Loaded([f"run refused: {mname}: {merrs[0]}"], files=files)
            present = [n for n in STACK_FILES if n in files]
            if len(present) > 1:
                return _Loaded([f"run refused: stack: found {' and '.join(present)}; use one stack file"], files=files)
            stack = {"bin-env": {}, "roles": {}}
            if present:
                try:
                    raw = vc.load_document(os.path.join(tmp, present[0]))
                except (vc.LoadError, vc.UsageError) as e:
                    return _Loaded([f"run refused: {present[0]}: {getattr(e, 'msg', e)}"], files=files)
                bad = validate_stack(raw, manifest)
                if bad:
                    return _Loaded([f"run refused: {present[0]}: {bad[0]}: {bad[1]}"], files=files)
                stack = {"bin-env": raw.get("bin-env", {}), "roles": raw.get("roles", {})}
            workflows = {}
            for wname, entry in manifest["workflows"].items():
                workflows[wname] = vc.load_document(os.path.join(tmp, entry["path"]))
        interp = it.Interpreter(workflows, self.host, catalog=catalog, manifest=manifest)
        return _Loaded(interp.refusals(name), workflows, catalog, manifest, files, snap, stack)

    # -- metrics

    @staticmethod
    def _task_index(workflows):
        return {n: {p: t for p, t in it._walk(doc["do"])} for n, doc in workflows.items()}

    @staticmethod
    def _metrics_of(index, start, full):
        wf, parts, task = start, full.split(">"), None
        for i, part in enumerate(parts):
            task = index.get(wf, {}).get(re.sub(r"#[0-9]+", "", part))
            if task is None:
                return []
            if i < len(parts) - 1:
                wf = ((task.get("run") or {}).get("workflow") or {}).get("name")
        org = (task.get("metadata") or {}).get("org")
        return list(org.get("metrics") or []) if isinstance(org, dict) else []

    @staticmethod
    def _workflow_of(index, start, full):
        """The workflow whose task `full` is: follow each call along the key chain."""
        wf, parts = start, full.split(">")
        for part in parts[:-1]:
            task = index.get(wf, {}).get(re.sub(r"#[0-9]+", "", part))
            wf = (((task or {}).get("run") or {}).get("workflow") or {}).get("name")
            if wf is None:
                return None
        return wf

    # -- execute

    def _execute(self, name, inp, rid, ledger, loaded, entries, feed=None, readonly=False):
        workflows, catalog, manifest = loaded.workflows, loaded.catalog, loaded.manifest
        existing = [e["body"] for e in entries if e["kind"] == "log"]
        journal, fed, recorded_ids, rows_after, cur = {}, [], [], {}, None
        for e in entries:
            b = e["body"]
            if e["kind"] == "host":
                journal.setdefault((b["call"], b["key"]), deque()).append(b["result"])
            elif e["kind"] == "feed":
                fed.append((b["t"], b["event"]))
            elif e["kind"] == "decision-id":
                recorded_ids.append(b["id"])
            if e["kind"] == "log":
                cur = b["seq"] if b.get("kind") == "accept" else None
            elif e["kind"] == "metric" and cur is not None:
                rows_after.setdefault(cur, set()).add(b["metric"])
        index = self._task_index(workflows)
        collector = _no_collector if readonly else self.collector
        if hasattr(collector, "bind"):
            collector.bind(loaded.files)
        if hasattr(collector, "bind_ledger"):
            collector.bind_ledger(ledger)

        def collect(e, done=()):
            if e["kind"] != "accept" or e.get("status") == "cancelled":
                return
            for metric in self._metrics_of(index, name, e["key"]):
                if metric in done:
                    continue
                row = {"key": e["key"], "metric": metric}
                try:
                    row["value"] = collector(metric, catalog[metric], e["key"], rid, ledger.path)
                except mc.NoValue as exc:
                    row["reason"] = str(exc)
                except Exception as exc:  # noqa: BLE001  an unreadable metric is an error row, never a zero
                    row["error"] = str(exc) or type(exc).__name__
                ledger.append("metric", row)

        bind = getattr(self.host, "bind_stack", None)
        if bind:
            bind(loaded.stack, lambda key: self._workflow_of(index, name, key))
        verified = _VerifiedHost(_NoLive(self.host) if readonly else self.host, self.root, loaded.files)
        jhost = _JournalHost(verified, self.ring, ledger, journal, fed)
        interp = it.Interpreter(workflows, jhost, catalog=catalog, manifest=manifest)
        run = _OrgRun(interp, rid, ledger, recorded_ids)
        tee = _Tee(ledger, existing, collect, lambda e: collect(e, done=rows_after.get(e["seq"], set())))
        run.events = tee
        if feed is not None:
            replay_end = existing[-1]["t"] if existing else None
            sched = LiveScheduler(list(jhost.scheduled_events()), feed, self.clock, self.sleep,
                                  lambda t, ev: ledger.append("feed", {"t": t, "event": ev}), self.poll, replay_end)
            sched.on_event = run.sched.on_event
            run.sched = sched
            jhost.sched = sched
        self._catalog, self._run_id = catalog, rid
        self._ledger = None if readonly else ledger
        try:
            res = run.execute(name, inp)
        finally:
            tee.closed = True  # a crash writes nothing more; neither does unwinding after one
        if readonly:
            self._check_run_end(ledger, catalog)
        else:
            self._collect_run_end(ledger, catalog)
        return res

    @staticmethod
    def _run_end_rows(ledger):
        return {e["body"]["metric"]: e["body"] for e in ledger.read()
                if e["kind"] == "org.metric" and isinstance(e["body"], dict) and e["body"].get("at") == "run-end"}

    def _collect_run_end(self, ledger, catalog):
        """One `org.metric` per catalog metric after the run ends (P62). A resume adds only the missing rows, computed
        from the boundary the first rows recorded, so a kill between rows changes no value."""
        done = self._run_end_rows(ledger)
        if set(catalog) <= set(done):
            return
        boundary = next(iter(done.values()))["inputs"][mc.RUN_LEDGER] if done else {"seq": ledger._seq,
                                                                                      "mac": ledger._last}
        inputs = {mc.RUN_LEDGER: ledger.prefix(boundary["seq"], boundary["mac"])}
        parsed = {}
        for m in sorted(catalog):
            if m not in done:
                res = self.registry.compute(m, catalog[m], inputs, None, parsed)
                ledger.append("org.metric", {"metric": m, "at": "run-end", "inputs": {mc.RUN_LEDGER: boundary}, **res})

    def _check_run_end(self, ledger, catalog):
        """Replay: recompute each recorded run-end metric from its boundary; a different result is a divergence.
        Turn rows are not rechecked: the ledger holds the session record's digest, not its bytes."""
        cache = {}  # boundary -> (input bytes, parsed sources)
        for m, body in sorted(self._run_end_rows(ledger).items()):
            if m not in catalog:
                raise DivergenceError(f"org.metric {m}: not in the catalog this replay loaded")
            b = body["inputs"][mc.RUN_LEDGER]
            k = (b["seq"], b["mac"])
            if k not in cache:
                cache[k] = (ledger.prefix(b["seq"], b["mac"]), {})
            data, parsed = cache[k]
            again = self.registry.compute(m, catalog[m], {mc.RUN_LEDGER: data}, None, parsed)
            held = {k: body[k] for k in ("value", "reason", "error") if k in body}
            if json.dumps(again, sort_keys=True) != json.dumps(held, sort_keys=True):
                raise DivergenceError(f"org.metric {m}: replay computes {again}, the ledger holds {held}")

    def _used(self):
        try:
            with open(self.used_ids_path) as f:
                return set(f.read().split())
        except FileNotFoundError:
            return set()

    def run(self, name, input=None, run_id=None, feed=None):
        if run_id is not None:
            if not self.allow_run_id:
                raise ValueError("a caller-chosen run id needs allow_run_id=True (tests only)")
            if not (isinstance(run_id, str) and it.RUN_ID.fullmatch(run_id)):
                raise ValueError("run id must match [A-Za-z0-9-]{8,64}")
        rid = run_id or secrets.token_hex(16)
        loaded = self._load(name)
        if loaded.errs:
            return it.RunResult(status="refused", errors=loaded.errs, run_id=rid)
        if rid in self._used():
            raise ValueError(f"run id {rid} was already used by an earlier ledger")
        ledger = RunLedger(self.ledger_path, self.ledger_key)
        if ledger.read():
            raise LedgerError(f"{self.ledger_path}: the ledger already holds a run; resume it")
        ledger.append("header", {"run_id": rid, "workflow": name, "input": input,
                                 "root_digest": _digest(loaded.files), "snapshot": loaded.snap,
                                 "stack_hash": next((_sha(loaded.files[n]) for n in STACK_FILES if n in loaded.files), None)})
        with open(self.used_ids_path, "a") as f:
            f.write(rid + "\n")
        return self._execute(name, input, rid, ledger, loaded, [], feed=feed)

    def _recover(self, readonly, expected_head=None):
        ledger = RunLedger(self.ledger_path, self.ledger_key, readonly=readonly)
        entries = ledger.read()
        if not entries or entries[0]["kind"] != "header":
            raise LedgerError(f"{self.ledger_path}: no header: there is nothing to resume")
        ledger.verify_head(entries, expected_head)
        h = entries[0]["body"]
        loaded = self._load(h["workflow"])
        if loaded.errs:
            return None, it.RunResult(status="refused", errors=loaded.errs, run_id=h["run_id"])
        snap = h.get("snapshot")
        if snap and loaded.snap:
            if loaded.snap["seq"] < snap["seq"]:
                err = "run refused: snapshot: the signed snapshot chain is older than the one this run started with"
            elif loaded.snap["seq"] == snap["seq"] and loaded.snap["hash"] != snap["hash"]:
                err = "run refused: snapshot: the signed snapshot differs from the one this run started with"
            else:
                err = None
            if err:
                return None, it.RunResult(status="refused", errors=[err], run_id=h["run_id"])
        if _digest(loaded.files) != h["root_digest"]:
            err = "run refused: org root: the org root changed since the run started"
            return None, it.RunResult(status="refused", errors=[err], run_id=h["run_id"])
        return (ledger, h, loaded, entries[1:]), None

    def resume(self, feed=None, expected_head=None):
        """Re-run the recorded run from its ledger. Host calls the ledger answers are not made again.

        With a `feed` the run continues live after the journal is replayed: a gate waiting days survives a restart.
        `expected_head=(entry count, last MAC)` pins the ledger to a head kept somewhere else.
        """
        ctx, refused = self._recover(readonly=False, expected_head=expected_head)
        if refused:
            return refused
        ledger, h, loaded, entries = ctx
        return self._execute(h["workflow"], h["input"], h["run_id"], ledger, loaded, entries, feed=feed)

    def turn_boundary(self):
        """The P61 turn seam over this runtime's ledger. It writes only through the writer of the last run or resume
        in this runtime; after a replay, or with no run, it can only read (`compaction_allowed`)."""
        return TurnBoundary(self.ledger_path, self.ledger_key, self._ledger, self._catalog, self.registry,
                            self._run_id)

    def replay(self):
        """Rebuild the run's result from its ledger alone: no live call, no collector and no write."""
        ctx, refused = self._recover(readonly=True)
        if refused:
            return refused
        ledger, h, loaded, entries = ctx
        return self._execute(h["workflow"], h["input"], h["run_id"], ledger, loaded, entries, readonly=True)
