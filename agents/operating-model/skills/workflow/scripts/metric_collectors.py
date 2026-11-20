"""Metric collectors: a registry keyed by the catalog's `reads` sources (spec update 13, P62 to P64).

A collector serves one source name, for example `run-ledger` or `session-record`. It turns that source's bytes into
data once (`parse`) and computes the metrics it knows (`metrics`: name -> fn(data, key)). `data` maps every source
the metric reads to its parsed form; `key` is the task key for a per-node row, None for a run or turn row.

A metric gets exactly one result, never a silent skip and never a zero by accident:
  {"value": n}    a finite JSON number;
  {"reason": s}   no value: `no collector for <source>` (the first source in `reads` with no collector),
                  `no input for <source>` (the source has a collector but no bytes at this point),
                  `no collector computes <metric>`, or a collector's own NoValue reason;
  {"error": s}    the collector raised or returned no finite number; the run goes on.

Collectors are pure: bytes in, numbers out. No clock, file, environment, network or randomness. Times come from the
interpreter's virtual `t` in the ledger.
"""
import json
import math
import os
import re
import sys
from typing import Callable, Mapping, Protocol

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import session_export  # noqa: E402

RUN_LEDGER = "run-ledger"
SESSION_RECORD = "session-record"


class NoValue(Exception):
    """The metric has no value at this point; the message is the recorded reason."""


class Collector(Protocol):
    source: str
    metrics: Mapping[str, Callable[[dict, "str | None"], float]]

    def parse(self, data: bytes) -> object: ...


def _finite(v):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def _err(e):
    return {"error": f"{type(e).__name__}: {e}"}


class Registry:
    """Collectors by source name. One collector per source."""

    def __init__(self, collectors=()):
        self._by = {}
        for c in collectors:
            if c.source in self._by:
                raise ValueError(f"two collectors for source {c.source}")
            self._by[c.source] = c

    def sources(self):
        return list(self._by)

    def compute(self, metric, entry, inputs, key=None, _parsed=None):
        parsed = {} if _parsed is None else _parsed
        reads = list(entry.get("reads") or [])
        for s in reads:
            if s not in self._by:
                return {"reason": f"no collector for {s}"}
        for s in reads:
            if s not in inputs:
                return {"reason": f"no input for {s}"}
        fn = next((self._by[s].metrics[metric] for s in reads if metric in self._by[s].metrics), None)
        if fn is None:
            return {"reason": f"no collector computes {metric}"}
        data = {}
        for s in reads:
            if s not in parsed:
                try:
                    parsed[s] = ("ok", self._by[s].parse(inputs[s]))
                except Exception as e:  # noqa: BLE001  a bad source is an error row for each metric that reads it
                    parsed[s] = ("error", _err(e))
            state, v = parsed[s]
            if state == "error":
                return dict(v)
            data[s] = v
        try:
            v = fn(data, key)
        except NoValue as e:
            return {"reason": str(e)}
        except Exception as e:  # noqa: BLE001  never abort the run over a metric
            return _err(e)
        if not _finite(v):
            return {"error": f"collector returned no finite number: {v!r}"[:300]}
        return {"value": v}


def collect(catalog, registry, inputs, key=None):
    """Every catalog metric, in name order. Each source is parsed once."""
    parsed = {}
    return {m: registry.compute(m, catalog[m], inputs, key, parsed) for m in sorted(catalog)}


# ---------------------------------------------------------------- run-ledger


def _last(key):
    return re.sub(r"#[0-9]+$", "", re.split(r"[>/]", key)[-1]) if isinstance(key, str) else None


class LedgerView:
    """The ledger's entries in order. Parsing only: the runtime has verified the chain before it hands bytes over."""

    def __init__(self, data):
        self.entries = []
        for n, line in enumerate(data.split(b"\n"), 1):
            if not line.strip():
                continue
            e = json.loads(line.decode("utf-8"))
            if not isinstance(e, dict) or not isinstance(e.get("body"), (dict, list, str, int, float, type(None))):
                raise ValueError(f"line {n} is not a ledger entry")
            self.entries.append((e.get("kind"), e.get("body")))

    def logs(self, kind=None):
        return [b for k, b in self.entries if k == "log" and isinstance(b, dict) and (kind is None or b.get("kind") == kind)]

    def accepts(self, key):
        return [b for b in self.logs("accept") if b.get("key") == key]

    def nodes(self, metric):
        """Keys the runtime wrote a per-node row for: the nodes of this run that carry the metric."""
        out = []
        for k, b in self.entries:
            if k == "metric" and isinstance(b, dict) and b.get("metric") == metric and b.get("key") not in out:
                out.append(b.get("key"))
        return out

    def start_t(self):
        s = self.logs("run-start")
        return s[0]["t"] if s else 0.0

    def decided(self):
        """(key, start t, accept t) of every gate execution that consumed a signed decision."""
        start, pending, out = {}, {}, []
        for k, b in self.entries:
            if k == "log" and isinstance(b, dict) and b.get("kind") == "task-start":
                start[b.get("key")] = b["t"]
            elif k == "decision-id" and isinstance(b, dict) and b.get("key") in start:
                pending[b["key"]] = start[b["key"]]
            elif k == "log" and isinstance(b, dict) and b.get("kind") == "accept" and b.get("key") in pending:
                out.append((b["key"], pending.pop(b["key"]), b["t"]))
        return out

    def costs(self):
        out = []
        for k, b in self.entries:
            if k == "host" and isinstance(b, dict) and b.get("call") == "step":
                o = (b.get("result") or {}).get("output")
                if isinstance(o, dict) and isinstance(o.get("cost"), dict):
                    out.append(o["cost"])
        return out


def _rounds(view, key):
    n = 0
    for b in view.accepts(key):
        n += 1
        if b.get("status") == "pass":
            break
    return n


def _first_pass_hours(view, key):
    t = next((b["t"] for b in view.accepts(key) if b.get("status") == "pass"), None)
    return None if t is None else (t - view.start_t()) / 3600


def _nodes_or_reason(view, metric):
    nodes = view.nodes(metric)
    if not nodes:
        raise NoValue(f"no node of this run carries {metric}")
    return nodes


def escalations(d, key):
    return sum(1 for b in d[RUN_LEDGER].logs("escalation") if key is None or b.get("key") == key)


def green_rounds(d, key):
    return sum(1 for b in d[RUN_LEDGER].logs("accept") if b.get("status") == "fail"
               and (b.get("key") == key if key is not None else _last(b.get("key")) == "green-evidence"))


def rounds_until_pass(metric):
    def fn(d, key):
        v = d[RUN_LEDGER]
        if key is not None:
            return _rounds(v, key)
        return max(_rounds(v, k) for k in _nodes_or_reason(v, metric))
    return fn


def hours_to_pass(metric):
    def fn(d, key):
        v = d[RUN_LEDGER]
        keys = [key] if key is not None else _nodes_or_reason(v, metric)
        hours = [h for h in (_first_pass_hours(v, k) for k in keys) if h is not None]
        if not hours:
            raise NoValue(f"no node carrying {metric} has passed")
        return min(hours)
    return fn


def decision_latency(d, key):
    lat = [(a - s) / 3600 for k, s, a in d[RUN_LEDGER].decided() if key is None or k == key]
    if not lat:
        raise NoValue("no signed decision in this run")
    return lat[-1] if key is not None else sum(lat) / len(lat)


def run_duration(d, key):
    logs = d[RUN_LEDGER].logs()
    if not logs:
        raise NoValue("no event in the ledger")
    end = next((b["t"] for b in logs if b.get("kind") == "run-end"), logs[-1]["t"])
    return end - d[RUN_LEDGER].start_t()


def model_calls(d, key):
    return len(d[RUN_LEDGER].costs())


def model_cost(d, key):
    return sum(c["usd"] for c in d[RUN_LEDGER].costs() if _finite(c.get("usd")))


def model_tokens(d, key):
    counts = [v for c in d[RUN_LEDGER].costs() for k, v in sorted(c.items()) if k.endswith("_tokens") and _finite(v)]
    if not counts:
        raise NoValue("no step reported a token count")
    return sum(counts)


def task_reruns(d, key):
    seen = {}
    for b in d[RUN_LEDGER].logs("task-start"):
        seen[b.get("key")] = seen.get(b.get("key"), 0) + 1
    return sum(n - 1 for n in seen.values())


def skipped_tasks(d, key):
    return len(d[RUN_LEDGER].logs("task-skip"))


def failed_items(kind):
    def fn(d, key):
        return sum(1 for b in d[RUN_LEDGER].logs("item") if b.get("item") == kind and b.get("result") == "fail")
    return fn


def gate_wait(d, key):
    v = d[RUN_LEDGER]
    gates = {b.get("key") for b in v.logs("until")} | {b.get("key") for k, b in v.entries
                                                         if k == "decision-id" and isinstance(b, dict)}
    start, total = {}, 0.0
    for b in v.logs():
        if b.get("key") not in gates:
            continue
        if b.get("kind") == "task-start":
            start[b["key"]] = b["t"]
        elif b.get("kind") == "accept" and b["key"] in start:
            total += b["t"] - start.pop(b["key"])
    return total


class RunLedgerCollector:
    source = RUN_LEDGER
    metrics = {
        "escalations": escalations,
        "green-rounds": green_rounds,
        "acceptance-rounds": rounds_until_pass("acceptance-rounds"),
        "claim-review-rounds": rounds_until_pass("claim-review-rounds"),
        "lead-time": hours_to_pass("lead-time"),
        "question-turnaround": hours_to_pass("question-turnaround"),
        "decision-latency": decision_latency,
        "run-duration": run_duration,
        "model-calls": model_calls,
        "model-cost": model_cost,
        "model-tokens": model_tokens,
        "task-reruns": task_reruns,
        "skipped-tasks": skipped_tasks,
        "check-failures": failed_items("check"),
        "judge-failures": failed_items("rubric"),
        "gate-wait": gate_wait,
    }

    def parse(self, data):
        return LedgerView(data)


# ---------------------------------------------------------------- session-record (U11)


def _records(kind, pred=lambda r: True):
    def fn(d, key):
        return sum(1 for r in d[SESSION_RECORD] if r["kind"] == kind and pred(r))
    return fn


class SessionRecordCollector:
    """The U11 record, one JSON object per line, checked with the exporter's own validator. Schema 1 has no token
    counts: tokens come from the run ledger's agent-run costs (model-tokens)."""

    source = SESSION_RECORD
    metrics = {
        "session-tool-calls": _records("tool_call"),
        "session-tool-errors": _records("tool_result", lambda r: r["is_error"]),
        "session-compactions": _records("compaction"),
    }

    def parse(self, data):
        out = []
        for n, line in enumerate(data.split(b"\n"), 1):
            if not line.strip():
                continue
            try:
                r = session_export._loads(line.decode("utf-8"))
                session_export.validate_record(r)
            except (ValueError, UnicodeDecodeError) as e:
                raise ValueError(f"session record line {n}: {e}") from None
            out.append(r)
        return out


def default_registry():
    return Registry([RunLedgerCollector(), SessionRecordCollector()])
