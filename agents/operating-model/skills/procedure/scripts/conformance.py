#!/usr/bin/env python3
"""Check that a ledger conforms to the contract. Stdlib only.

    conformance.py LEDGER --key KEY --state STATE.json

An executor is conforming when its ledger meets these rules, whatever it is built from. This checks the
ledger and the run's final state; it does not run the executor. `check_ledger` returns the violations,
empty when the ledger conforms. A ledger that does not verify is reported as a violation, never raised.

1. The chain verifies, and the ledger starts with a header.
2. The header's trust matches the final state's.
3. Every event entry says whether it was signed (`signing`) and who sent it (`by`).
4. A signed run has no unsigned entry, and no entry whose sender is `unverified`.
5. A run with no signing has no entry that names an identity: every `by` is `unverified`.
6. Replaying the ledger reproduces the final state.
"""
import argparse
import json
import sys

from ledger import Ledger, LedgerError, recover

__all__ = ("check_ledger", "main")

COMPARED = ("status", "stages", "log", "metrics", "items", "seen", "version", "trust")


def check_ledger(ledger, state, key=None):
    """The violations of the contract in `ledger`, given the run's final `state`. Empty when it conforms.

    `ledger` is a `Ledger`, or a path with the `key` to open it. Opening verifies the chain, so a broken
    one is reported here, not raised."""
    try:
        if not isinstance(ledger, Ledger):
            ledger = Ledger(ledger, key)
        entries = ledger.read()
    except LedgerError as exc:
        return [f"the chain does not verify: {exc}"]
    if not entries or entries[0]["kind"] != "header":
        return ["the ledger has no header"]
    out = []
    trust = entries[0]["body"].get("trust")
    if trust != state.get("trust"):
        out.append(f"the header's trust is {trust!r}, but the run's is {state.get('trust')!r}")
    for n, e in enumerate(entries[1:], 2):
        if e["kind"] != "event":
            continue
        body = e["body"]
        if body.get("signing") not in ("signed", "none"):
            out.append(f"entry {n}: the signing label is missing or unknown")
            continue
        by = body.get("by")
        if trust == "signed" and body["signing"] != "signed":
            out.append(f"entry {n}: a signed run has an unsigned entry")
        if trust == "signed" and by in (None, "unverified"):
            out.append(f"entry {n}: a signed run has an entry whose sender is unverified")
        if trust != "signed" and by != "unverified":
            out.append(f"entry {n}: a run with no signing names an identity ({by!r}); every sender must be unverified")
    try:
        replayed = recover(ledger)
    except Exception as exc:  # a ledger that cannot be replayed is a violation, not a crash
        return out + [f"replay failed: {exc}"]
    out += [f"replay differs from the final state in {k!r}" for k in COMPARED if replayed.get(k) != state.get(k)]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("ledger")
    ap.add_argument("--key", required=True, help="the ledger key, as text")
    ap.add_argument("--state", required=True, help="the run's final state, as JSON")
    a = ap.parse_args(argv)
    try:
        with open(a.state, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"ERROR: --state {a.state}: {exc}", file=sys.stderr)
        return 1
    violations = check_ledger(a.ledger, state, a.key.encode())
    for v in violations:
        print(f"VIOLATION: {v}", file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
