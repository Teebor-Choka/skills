#!/usr/bin/env python3
"""Report the state of a build unit to the organization site. Standard library only.

  python3 site/emit.py --unit U20 --state building --title 'Metric collectors' --pr 176
  python3 site/emit.py --unit U22 --state review --deps U21,U19 --wave 7 --branch kauki/feat/x
  ... --hook < hook.json      read a Claude Code hook payload on stdin; the unit comes from --unit or from the
                              first unit id (U20, U13a) in its agent_type, description or prompt; no unit: exit 0

Posts to http://127.0.0.1:8765/api/ingest (ORG_SITE overrides). When nothing listens there it appends to
site/ingest/events.jsonl itself, with the same validation and lock (ingest.py). A refused report (400, 409,
429) is never written to the file: it exits 1 with the server's reason.
States: queued building review ci merged done blocked failed needs-owner.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest  # noqa: E402

URL = os.environ.get("ORG_SITE", "http://127.0.0.1:8765") + "/api/ingest"


def post(rec, url=URL):
    """(status, text); status None when nothing answers."""
    req = urllib.request.Request(url, data=json.dumps(rec).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace").strip()
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (ConnectionRefusedError, FileNotFoundError)) or isinstance(e, ConnectionRefusedError):
            return None, "server down"
        return 0, "no answer: %s" % reason  # a timeout may have been stored: do not write it a second time


def emit(rec, url=URL, path=None):
    code, text = post(rec, url)
    if code is None:
        try:
            line = ingest.append(rec, "file", path)
        except (ValueError, ingest.ChainBroken) as e:
            return 1, "not stored: %s" % e
        return 0, "server down; appended seq %d to %s" % (line["seq"], path or ingest.log_path())
    if code == 201:
        return 0, "stored seq %d" % json.loads(text)["seq"]
    return 1, "refused (%s): %s" % (code, text)


def from_hook(stdin):
    try:
        h = json.loads(stdin.read() or "{}")
    except ValueError:
        return None, {}
    blob = " ".join(str(h.get(k) or "") for k in ("agent_type", "description", "prompt", "subagent_type"))
    m = re.search(r"\b([A-Z]\d{1,4}[a-z]?)\b", blob)
    return (m.group(1) if m else None), {"agent": str(h.get("agent_id") or h.get("agent_type") or "")[:100] or None}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Report a build unit's state to the organization site.")
    ap.add_argument("--unit")
    ap.add_argument("--state", required=True, choices=ingest.STATES)
    ap.add_argument("--title")
    ap.add_argument("--text")
    ap.add_argument("--pr", type=int)
    ap.add_argument("--branch")
    ap.add_argument("--agent")
    ap.add_argument("--wave", type=int)
    ap.add_argument("--deps", help="comma separated unit ids")
    ap.add_argument("--hook", action="store_true", help="read a Claude Code hook payload on stdin")
    ap.add_argument("--url", default=URL)
    a = ap.parse_args(argv)
    extra = {}
    if a.hook:
        unit, extra = from_hook(sys.stdin)
        a.unit = a.unit or unit
        if not a.unit:
            return 0  # not a unit's agent; a hook must never block the session
    if not a.unit:
        ap.error("--unit is required")
    rec = {"unit": a.unit, "state": a.state}
    for k in ("title", "text", "pr", "branch", "agent", "wave"):
        if getattr(a, k) is not None:
            rec[k] = getattr(a, k)
    if a.deps:
        rec["deps"] = [d.strip() for d in a.deps.split(",") if d.strip()]
    if extra.get("agent") and "agent" not in rec:
        rec["agent"] = extra["agent"]
    rc, msg = emit(rec, a.url)
    print("emit %s %s: %s" % (a.unit, a.state, msg), file=sys.stderr if rc else sys.stdout)
    return 0 if a.hook else rc


if __name__ == "__main__":
    sys.exit(main())
