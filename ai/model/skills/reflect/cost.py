#!/usr/bin/env python3
"""Dollar cost of agent sessions, two ways, so a retrospective quotes real money.

usage_usd       per-message token usage times a price table. A message the transcript
                logs once per content block is priced once (keyed on message id).
cost_state_usd  the harness's own running cost, summed over segments: a drop in the
                running value is a reset, and each segment counts once. None when the
                transcripts hold no cost state.

An unknown model id adds a warning and costs nothing, so a missing price shows up as a
warning, not as a silently low total. Quote both figures and say which one you use.

Usage: cost.py PATH [PATH ...] [--since ISO] [--until ISO] [--prices FILE.json]
PATH is a .jsonl file or a folder (searched recursively, so subagents are included).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works under python -I
import reflectlib as lib  # noqa: E402

# US dollars per million tokens. Defaults are list prices at the time of writing: verify
# them, or pass --prices. A key matches a model id by prefix; the longest key wins.
PRICES = {
    "claude-opus": {"in": 5.0, "out": 25.0, "cache_write": 6.25, "cache_read": 0.50},
    "claude-sonnet": {"in": 3.0, "out": 15.0, "cache_write": 3.75, "cache_read": 0.30},
    "claude-haiku": {"in": 1.0, "out": 5.0, "cache_write": 1.25, "cache_read": 0.10},
}
FIELDS = (("input_tokens", "in"), ("output_tokens", "out"),
          ("cache_creation_input_tokens", "cache_write"), ("cache_read_input_tokens", "cache_read"))


def price_for(model, prices):
    keys = [k for k in prices if isinstance(model, str) and model.startswith(k)]
    return prices[max(keys, key=len)] if keys else None


class CostMeter:
    """Both cost figures, fed one transcript entry at a time (so a caller that already walks
    the file does not read it twice). Call end_file() after each file, then result()."""

    def __init__(self, prices=None, since=None, until=None):
        self.prices = prices or PRICES
        self.lo = lib.parse_ts(since) if isinstance(since, str) else since
        self.hi = lib.parse_ts(until) if isinstance(until, str) else until
        if isinstance(until, str) and len(until) == 10 and self.hi is not None:
            self.hi += 86399  # a date-only upper bound spans the whole day
        self.messages = {}  # message id -> {"model", token fields}: per-field max over repeats
        self.state_total, self.saw_state = 0.0, False
        self.unknown_flag = False  # the harness flagged an unpriced model in its last cost entry
        self.prev = self.seg_last = None

    def feed(self, path, ln, o):
        state = lib.cost_state(o)  # the harness's own running cost, if this entry carries it
        if state is not None:
            v, self.unknown_flag = state
            self.saw_state = True
            if self.prev is not None and v < self.prev:
                self.state_total += self.seg_last
            self.prev = self.seg_last = v
            return
        if o.get("type") != "assistant":
            return
        if not lib.in_window(lib.entry_time(o), self.lo, self.hi):
            return
        msg = lib.message_of(o)
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            return
        key = msg.get("id") if isinstance(msg.get("id"), str) and msg.get("id") \
            else f"{path}:{ln}"
        rec = self.messages.setdefault(key, {"model": msg.get("model")})
        if msg.get("model"):
            rec["model"] = msg["model"]
        for field, _ in FIELDS:
            v = usage.get(field)
            if isinstance(v, (int, float)):
                rec[field] = max(rec.get(field, 0), v)

    def end_file(self):
        if self.seg_last is not None:
            self.state_total += self.seg_last
        self.prev = self.seg_last = None

    def result(self):
        by_model, warnings, total = {}, [], 0.0
        for rec in self.messages.values():
            model = rec["model"]
            entry = by_model.setdefault(str(model), {"messages": 0, "usd": 0.0, "tokens": 0})
            entry["messages"] += 1
            entry["tokens"] += sum(rec.get(f, 0) for f, _ in FIELDS)
            rate = price_for(model, self.prices)
            if rate is None:
                warning = f"unknown model id {model!r}: priced at 0"
                if warning not in warnings:
                    warnings.append(warning)
                continue
            usd = sum(rec.get(f, 0) * rate[k] for f, k in FIELDS) / 1_000_000
            entry["usd"] += usd
            total += usd
        for entry in by_model.values():
            entry["usd"] = round(entry["usd"], 4)
        return {
            "usage_usd": round(total, 4),
            "cost_state_usd": round(self.state_total, 4) if self.saw_state else None,
            "unknown_model_cost": self.unknown_flag,
            "messages": len(self.messages),
            "by_model": by_model,
            "warnings": warnings,
            "windowed": self.lo is not None or self.hi is not None,
            "note": "cost_state_usd is cumulative and ignores the window",
        }


def cost_of(paths, prices=None, since=None, until=None):
    meter = CostMeter(prices, since, until)
    for path in lib.collect_files(paths):
        for ln, o in lib.iter_entries(path):
            meter.feed(path, ln, o)
        meter.end_file()
    return meter.result()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--prices", help="JSON file: {model-prefix: {in, out, cache_write, cache_read}}")
    a = ap.parse_args(argv)
    prices = None
    if a.prices:
        with open(a.prices) as fh:
            prices = json.load(fh)
    result = cost_of(a.paths, prices, a.since, a.until)
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    print()
    for w in result["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
