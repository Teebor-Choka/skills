#!/usr/bin/env python3
"""The executor's ledger: a signed, append-only record of a run. Stdlib only.

One JSON object per line. Each entry holds the MAC of the entry before it and its own MAC under the
executor's key, so an edit, a reorder or a deletion in the middle is detectable. Only the executor
holds the key and writes. A crash can leave a partial last line: it is dropped and reported (`torn`),
never an error. Everything else that fails to verify raises `LedgerError`.

`drive` writes a header and then every event that reached the reducer's log, with the identity the
executor verified for it. `recover` replays that record through `step` and returns the state the run
ended in. The chain is what vouches for the recorded identities, so recovery needs no key ring.
"""
import hashlib
import hmac
import json
import os

from runtime import SOURCE_OF, new_state, step

__all__ = ("GENESIS", "Ledger", "LedgerError", "assurance_of", "recover")

GENESIS = "0" * 64


class LedgerError(Exception):
    """The ledger does not verify, or it cannot be recovered from."""


def _mac(key, entry):
    body = json.dumps({k: entry[k] for k in ("seq", "prev", "kind", "body")}, sort_keys=True, separators=(",", ":"))
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()


class Ledger:
    def __init__(self, path, key):
        self.path, self.key, self.torn = str(path), key, False
        self._last, self._seq, self._good = GENESIS, 0, 0
        if os.path.exists(self.path):
            entries = self.read()
            if entries:
                self._last, self._seq = entries[-1]["mac"], entries[-1]["seq"]

    def read(self):
        """The verified entries, oldest first. A torn last line is dropped and sets `torn`."""
        try:
            with open(self.path, "rb") as f:
                raw = f.read()
        except FileNotFoundError:
            return []
        text = raw.decode("utf-8", errors="replace")
        lines = text.split("\n")
        tail = lines.pop()  # whatever follows the last newline: empty, or a write that never finished
        if tail:
            self.torn = True
        entries, prev, good = [], GENESIS, 0
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
        """Add one entry and flush it to disk. Returns the entry."""
        if os.path.exists(self.path) and os.path.getsize(self.path) > self._good:
            with open(self.path, "r+b") as f:  # cut a torn tail before writing after it
                f.truncate(self._good)
        entry = {"seq": self._seq + 1, "prev": self._last, "kind": kind, "body": body}
        entry["mac"] = _mac(self.key, entry)
        line = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
        with open(self.path, "ab") as f:
            f.write(line.encode())
            f.flush()
            os.fsync(f.fileno())
        self._last, self._seq, self._good = entry["mac"], entry["seq"], self._good + len(line.encode())
        return entry


def header_of(state):
    return {k: state[k] for k in ("run_id", "trust", "procedure_text", "policy", "bindings", "revision")}


def recover(ledger):
    """Replay a ledger through `step` and return the state the run ended in."""
    entries = ledger.read()
    if not entries or entries[0]["kind"] != "header":
        raise LedgerError("the ledger has no header: there is nothing to recover from")
    h = entries[0]["body"]
    state = new_state(h["procedure_text"], policy=h["policy"], bindings=h["bindings"], revision=h["revision"],
                      trust=h["trust"], run_id=h["run_id"])
    by = {e["body"]["event"]["signature"]: e["body"]["by"] for e in entries[1:] if e["kind"] == "event"
          and isinstance(e["body"]["event"].get("signature"), str)}
    sender = lambda ev: by.get(ev.get("signature")) if by.get(ev.get("signature")) not in ("executor", "owner") else None  # noqa: E731
    kw = {"verify_sender": sender, "verify_executor": lambda ev: by.get(ev.get("signature")) == "executor",
          "verify_owner": lambda ev: by.get(ev.get("signature")) == "owner"}
    for e in entries[1:]:
        if e["kind"] == "event":
            state, _ = step(state, e["body"]["event"], **kw)
    return state


def assurance_of(entries):
    """What a ledger can prove about who sent what: `signed` only when the run was signed and every event
    entry says so, else `none`. A run with no signing is a trusted environment, and an audit must not
    mistake it for a verified one."""
    if not entries or entries[0].get("kind") != "header" or entries[0]["body"].get("trust") != "signed":
        return "none"
    events = [e for e in entries[1:] if e.get("kind") == "event"]
    return "signed" if all(e["body"].get("signing") == "signed" for e in events) else "none"


def identity_of(event, ring, run_id):
    """Who the executor verifies this event as: an entity, `executor` or `owner`. With no ring, nobody."""
    if ring is None:
        return "unverified"
    source = SOURCE_OF.get(event.get("type"))
    if source == "agent":
        return ring.verify_sender({**event, "run_id": run_id})
    return source
