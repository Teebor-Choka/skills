#!/usr/bin/env python3
"""Claude Code statusLine command: `$cost | ctx <tokens> (P%) | total <tokens>`, one line, no network, no files.

A statusLine is a Claude Code setting, not a hook, so a plugin cannot register it: point the setting at
this script (see the plugin README). Reads the statusline JSON on stdin (cost.total_cost_usd,
context_window.current_usage, used_percentage and total_input_tokens:
https://code.claude.com/docs/en/statusline). `ctx` is the current context: input + cache creation + cache
read tokens of current_usage (output tokens excluded), with used_percentage. `total_input_tokens` is a
cumulative session count, so it is labelled `total` and never `ctx`. The line turns red at $150 session cost or 80% context. Bad stdin prints nothing harmful. Always exits 0.
Tests: hooks/tests/test_statusline.py.
"""
import json
import sys

RED_COST = 150.0
RED_PCT = 80.0


def number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def kilo(tokens):
    return f"{tokens / 1000:.0f}K" if tokens >= 1000 else str(int(tokens))


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            data = {}
    except ValueError:
        data = {}
    cost_obj = data.get("cost") if isinstance(data.get("cost"), dict) else {}
    ctx_obj = data.get("context_window") if isinstance(data.get("context_window"), dict) else {}
    cost = number(cost_obj.get("total_cost_usd"))
    total = number(ctx_obj.get("total_input_tokens"))
    pct = number(ctx_obj.get("used_percentage"))
    usage = ctx_obj.get("current_usage") if isinstance(ctx_obj.get("current_usage"), dict) else {}
    counted = [number(usage.get(k)) for k in
               ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
    current = sum(c for c in counted if c is not None) if any(c is not None for c in counted) else None

    parts = []
    if cost is not None:
        parts.append(f"${cost:.2f}")
    if current is not None:
        parts.append(f"ctx {kilo(current)}" + (f" ({pct:.0f}%)" if pct is not None else ""))
    elif pct is not None:
        parts.append(f"ctx {pct:.0f}%")
    if current is None and total is not None and total > 0:  # the cumulative count only stands in when no current usage
        parts.append(f"total {kilo(total)}")
    if not parts:
        return
    line = " | ".join(parts)
    if (cost is not None and cost >= RED_COST) or (pct is not None and pct >= RED_PCT):
        line = f"\x1b[31m{line}\x1b[0m"
    print(line)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
