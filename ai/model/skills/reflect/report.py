#!/usr/bin/env python3
"""Weekly report: the twelve metrics and the north star (cost per merged PR), this window against
the one before, plus the change log (references/metrics.md defines every number, references/
metrics.toml holds targets and alert thresholds).

    report.py [PATH ...] [--records FILE ...] [--outcomes FILE] [--until DATE] [--days N]
              [--thresholds FILE] [--changes FILE] [--dispatch FILE] [--json OUT]

PATH is a transcript or folder (read with metrics.py); --records is a JSONL file of session
records (metrics.py scan output; the last line per session id wins). --outcomes is outcomes.py's
file. The window is the N days (default 7) ending on --until (default today, UTC), by each
session's last event; the "before" column is the N days before that. --changes is a JSONL file,
one accepted change per line: {"date", "rule", "metric", "baseline"}; the report prints the metric
over the sessions since each date and flags a change that moved nothing as a no-op candidate.

Prints a table. Exit 1 when any alert fires, else 0. Python 3.13 or newer.
"""
import argparse
import json
import math
import os
import statistics
import sys
import time
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works under python -I
import cost as costlib  # noqa: E402
import metrics as metrics_mod  # noqa: E402
import reflectlib as lib  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS = os.path.join(HERE, "references", "metrics.toml")
DAY = 86400
NAMES = {
    "m1": "cost per human prompt", "m2": "tool errors per 100 calls",
    "m3": "hook blocks per 100 calls", "m4": "gate integrity (events)",
    "m5": "human corrections per 100", "m6": "human-wait share of wall time",
    "m7": "always-loaded context (tokens)", "m8": "skill dispatch hit rate",
    "m9": "long-session share of spend", "m10": "compactions per session",
    "m11": "timer-driven turn share", "m12": "unpriced sessions",
}


def load_thresholds(path=None):
    with open(DEFAULTS, "rb") as fh:
        th = tomllib.load(fh)
    if path:
        with open(path, "rb") as fh:
            for section, values in tomllib.load(fh).items():
                th.setdefault(section, {}).update(values)
    return th


def read_jsonl(path):
    rows = []
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if isinstance(o, dict):
                    rows.append(o)
    except OSError as e:
        print(f"skipped {path}: {e}", file=sys.stderr)
    return rows


def load_records(paths, record_files, dispatch=None):
    """session id -> record; later sources win, so a ledger line replaces an older one."""
    recs = {}
    for p in lib.collect_files(paths):
        try:
            r = metrics_mod.full_record(p, dispatch)
        except (OSError, ValueError) as e:
            print(f"skipped {p}: {e}", file=sys.stderr)
            continue
        recs[r["session_id"]] = r
    for f in record_files:
        for r in read_jsonl(f):
            if "error" not in r and r.get("session_id"):
                recs[r["session_id"]] = r
    return list(recs.values())


def g(r, key, default=0):
    v = r.get(key)
    return default if v is None else v


def ratio(a, b):
    return a / b if b else None


def pctl(values, q):
    """Nearest-rank percentile (q in 0..1) of a list, None when empty."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(q * len(s)) - 1)]


def in_window(r, lo, hi):
    t = lib.parse_ts(r.get("ts_last"))
    return t is not None and lo < t <= hi


def north_star(recs, outcomes, th):
    """Cost per merged PR over sessions that touched a PR, with its three companions."""
    merge_s = th["window"]["merge_days"] * DAY
    priced = [r for r in recs if r.get("prs") and r.get("cost_usd") is not None]
    touch = {}
    for r in priced:
        t = lib.parse_ts(r.get("ts_last")) or 0
        for ref in r["prs"]:
            touch[ref] = max(touch.get(ref, 0), t)
    merged = [ref for ref, t in touch.items()
              if outcomes.get(ref, {}).get("state") == "MERGED"
              and (lib.parse_ts(outcomes[ref].get("merged")) or math.inf) <= t + merge_s]
    cost = sum(r["cost_usd"] for r in priced)
    hours = [outcomes[r]["hours_to_merge"] for r in merged
             if outcomes[r].get("hours_to_merge") is not None]
    rounds = [outcomes[r]["review_rounds"] for r in merged
              if outcomes[r].get("review_rounds") is not None]
    ns = {
        "prs": len(touch), "merged": len(merged), "cost_usd": round(cost, 4),
        "pr_sessions": len(priced),
        "unpriced_pr_sessions": sum(1 for r in recs if r.get("prs") and r.get("cost_usd") is None),
        "merged_share": ratio(len(merged), len(touch)),
        "hours_to_merge_p50": statistics.median(hours) if hours else None,
        "review_rounds_p50": statistics.median(rounds) if rounds else None,
        "cost_per_pr_session_median": statistics.median(r["cost_usd"] for r in priced)
        if priced else None,
    }
    cpm = ratio(cost, len(merged))
    missing = [name for name, v in (
        ("cost per merged PR", cpm), ("merged share", ns["merged_share"]),
        ("hours to merge", ns["hours_to_merge_p50"]),
        ("review rounds", ns["review_rounds_p50"])) if v is None]
    ns["cost_per_merged_pr"] = None if missing else cpm  # never published without its companions
    ns["cost_per_merged_pr_unguarded"] = cpm
    ns["withheld"] = missing
    return ns


def compute(recs, outcomes, th):
    """Metric values for a set of session records, and the alerts they raise."""
    a, t = th["alert"], th["target"]
    alerts = []
    m = {}
    n = len(recs)
    priced = [r for r in recs if r.get("cost_usd") is not None]
    cost = sum(r["cost_usd"] for r in priced)
    calls = sum(g(r, "tool_calls") for r in recs)
    prompts = sum(g(r, "human_prompts") for r in recs)
    turns = sum(g(r, "turns") for r in recs)

    def alert(metric, text):
        alerts.append({"metric": metric, "text": text})

    # m1
    pp = sum(g(r, "human_prompts") for r in priced)
    m["m1"] = {"value": ratio(cost, pp),
               "turns_per_prompt": ratio(sum(g(r, "turns") for r in priced), pp)}
    if m["m1"]["value"] is not None and m["m1"]["value"] > a["cost_per_prompt"]:
        alert("m1", f"m1 week cost per prompt ${m['m1']['value']:.2f} above ${a['cost_per_prompt']:.2f}")
    for r in priced:
        if g(r, "human_prompts") and r["cost_usd"] / r["human_prompts"] > a["cost_per_prompt_session"]:
            alert("m1", f"m1 session {str(r.get('session_id'))[:8]} "
                        f"${r['cost_usd'] / r['human_prompts']:.2f} per prompt")
    # m2
    m["m2"] = {"value": ratio(100 * sum(g(r, "tool_errors") for r in recs), calls), "projects": {}}
    by_project = {}
    for r in recs:
        by_project.setdefault(r.get("project") or "?", []).append(r)
    for proj, rs in sorted(by_project.items()):
        c, e = sum(g(r, "tool_calls") for r in rs), sum(g(r, "tool_errors") for r in rs)
        rate = ratio(100 * e, c)
        m["m2"]["projects"][proj] = {"calls": c, "per_100": rate}
        if c >= a["tool_errors_min_calls"] and rate is not None and rate > a["tool_errors_per_100"]:
            alert("m2", f"m2 project {proj}: {rate:.1f} errors per 100 calls over {c} calls")
    # m3
    blocks = sum(g(r, "hook_blocks") for r in recs)
    repeats = sum(g(r, "hook_block_repeats") for r in recs)
    m["m3"] = {"value": ratio(100 * blocks, calls), "blocks": blocks,
               "repeat_ratio": ratio(repeats, blocks)}
    if m["m3"]["value"] is not None and m["m3"]["value"] > a["hook_blocks_per_100"]:
        alert("m3", f"m3 {m['m3']['value']:.1f} hook blocks per 100 calls")
    if blocks >= a["hook_repeat_min_blocks"] and m["m3"]["repeat_ratio"] > a["hook_repeat_ratio"]:
        alert("m3", f"m3 hook repeat ratio {m['m3']['repeat_ratio']:.0%}")
    # m4
    gate = sum(g(r, "gate_events") for r in recs)
    m["m4"] = {"value": gate}
    if gate > a["gate_events"]:
        alert("m4", f"m4 {gate} policy-gate BLOCK events reached the agent as non-blocking")
    # m5
    corr = sum(g(r, "interrupts") + g(r, "denials") + g(r, "nudges") for r in recs)
    m["m5"] = {"value": ratio(100 * corr, prompts), "corrections": corr}
    if m["m5"]["value"] is not None and m["m5"]["value"] > a["correction_rate"]:
        alert("m5", f"m5 {m['m5']['value']:.1f} corrections per 100 prompts")
    # m6
    wall = [r for r in recs if g(r, "wall_seconds") > 0]
    shares = [g(r, "wait_seconds") / r["wall_seconds"] for r in wall]
    waits = [w for r in recs for w in g(r, "waits", [])]
    m["m6"] = {"value": ratio(sum(g(r, "wait_seconds") for r in wall),
                              sum(r["wall_seconds"] for r in wall)),
               "p50": pctl(shares, 0.5), "p90": pctl(shares, 0.9), "waits": len(waits)}
    idle = sum(1 for r in recs if any(w > a["idle_seconds"] for w in g(r, "waits", [])))
    if idle:
        alert("m6", f"m6 {idle} session(s) with an agent idle over {a['idle_seconds'] // 3600} h")
    # m7
    fixed = [g(r, "fixed_tokens") for r in recs]
    dollars = 0.0
    for r in recs:
        rate = costlib.price_for((g(r, "models", []) or [None])[0], costlib.PRICES)
        if rate:
            dollars += g(r, "fixed_tokens") * g(r, "turns") * rate["cache_read"] / 1_000_000
    m["m7"] = {"value": statistics.mean(fixed) if fixed else None, "fixed_dollars": dollars}
    if m["m7"]["value"] is not None and m["m7"]["value"] > a["fixed_tokens"]:
        alert("m7", f"m7 {m['m7']['value']:.0f} fixed tokens per session")
    # m8
    skills = {}
    for r in recs:
        offered = r.get("skills_offered") or {}
        for s in g(r, "skill_opportunities", []):
            for bucket in ("visible", "name_only"):
                if s in offered.get(bucket, []):
                    e = skills.setdefault(s, {b: {"opportunities": 0, "invoked": 0}
                                              for b in ("visible", "name_only")})[bucket]
                    e["opportunities"] += 1
                    e["invoked"] += 1 if s in g(r, "skills_invoked", []) else 0
    opps = inv = 0
    for s, buckets in sorted(skills.items()):
        so = si = 0
        for e in buckets.values():
            e["rate"] = ratio(e["invoked"], e["opportunities"])
            so, si = so + e["opportunities"], si + e["invoked"]
        opps, inv = opps + so, inv + si
        if so >= a["skill_hit_min_opportunities"] and si / so < a["skill_hit_rate"]:
            alert("m8", f"m8 skill {s}: {si} of {so} opportunities invoked")
    m["m8"] = {"value": ratio(inv, opps), "skills": skills}
    # m9
    long_cost = sum(r["cost_usd"] for r in priced
                    if g(r, "wall_seconds") > th["window"]["long_session_seconds"])
    m["m9"] = {"value": ratio(long_cost, cost),
               "cost_share_2plus_compactions": ratio(
                   sum(r["cost_usd"] for r in priced if g(r, "compactions") >= 2), cost)}
    if m["m9"]["value"] is not None and m["m9"]["value"] > a["long_session_share"]:
        alert("m9", f"m9 long sessions are {m['m9']['value']:.0%} of spend")
    # m10
    comp = sum(g(r, "compactions") for r in recs)
    worst = max((g(r, "compactions") for r in recs), default=0)
    m["m10"] = {"value": ratio(comp, n), "total": comp, "per_100_usd": ratio(100 * comp, cost),
                "max_per_session": worst}
    if worst >= a["compactions_per_session"]:
        alert("m10", f"m10 a session reached {worst} compactions")
    if comp > a["compactions_per_week"]:
        alert("m10", f"m10 {comp} compactions in the window")
    # m11
    timer = sum(g(r, "timer_turns") for r in recs)
    big = sum(g(r, "timer_turns_big_context") for r in recs)
    m["m11"] = {"value": ratio(timer, turns), "timer_turns": timer, "big_context": big}
    if m["m11"]["value"] is not None and m["m11"]["value"] > a["timer_share"]:
        alert("m11", f"m11 {m['m11']['value']:.1%} of turns are timer-driven")
    if big >= a["timer_big_context"]:
        alert("m11", f"m11 {big} timer turn(s) inside a 300K+ context")
    # m12
    unpriced = [r for r in recs if r.get("unpriced")]
    m["m12"] = {"value": len(unpriced),
                "floor_usd": sum(g(r, "cost_floor_usd") for r in unpriced)}
    if len(unpriced) > a["unpriced_sessions"]:
        alert("m12", f"m12 {len(unpriced)} unpriced session(s)")

    # north star
    ns = north_star(recs, outcomes, th)
    ns["projects"] = {}
    for proj in sorted({r.get("project") or "?" for r in recs if r.get("prs")}):
        pns = north_star([r for r in recs if (r.get("project") or "?") == proj], outcomes, th)
        ns["projects"][proj] = {"prs": pns["prs"], "merged": pns["merged"],
                                "cost_per_merged_pr": pns["cost_per_merged_pr_unguarded"]}
        if pns["prs"] >= a["project_min_prs"]:
            cpm = pns["cost_per_merged_pr_unguarded"]
            if cpm is None:
                alert("north_star", f"cost per merged PR in {proj}: none of {pns['prs']} PRs merged")
            elif cpm > a["cost_per_merged_pr"]:
                alert("north_star", f"cost per merged PR ${cpm:.2f} in {proj} "
                                    f"({pns['prs']} PRs, limit ${a['cost_per_merged_pr']:.2f})")
    if ns["merged_share"] is not None and ns["merged_share"] < a["merged_share"]:
        alert("north_star", f"merged share {ns['merged_share']:.0%} below {a['merged_share']:.0%}")
    return m, ns, alerts


def meets(mid, value, t):
    if value is None:
        return None
    return {
        "m1": value <= t["cost_per_prompt"], "m2": value < t["tool_errors_per_100"],
        "m3": value < t["hook_blocks_per_100"], "m4": value <= t["gate_events"],
        "m5": value < t["correction_rate"], "m6": None, "m7": value <= t["fixed_tokens"],
        "m8": value >= t["skill_hit_rate"], "m9": value < t["long_session_share"],
        "m10": value <= t["compactions_per_session"], "m11": value < t["timer_share"],
        "m12": value <= t["unpriced_sessions"],
    }[mid]


FORMAT = {
    "m1": lambda v: f"${v:.2f}", "m2": lambda v: f"{v:.1f}", "m3": lambda v: f"{v:.1f}",
    "m4": lambda v: f"{v:.0f}", "m5": lambda v: f"{v:.1f}", "m6": lambda v: f"{v:.1%}",
    "m7": lambda v: f"{v:.0f}", "m8": lambda v: f"{v:.0%}", "m9": lambda v: f"{v:.1%}",
    "m10": lambda v: f"{v:.2f}", "m11": lambda v: f"{v:.1%}", "m12": lambda v: f"{v:.0f}",
}
TARGET = {
    "m1": ("<=", "cost_per_prompt", "${:.2f}"), "m2": ("<", "tool_errors_per_100", "{:.1f}"),
    "m3": ("<", "hook_blocks_per_100", "{:.1f}"), "m4": ("=", "gate_events", "{:.0f}"),
    "m5": ("<", "correction_rate", "{:.1f}"), "m6": None, "m7": ("<=", "fixed_tokens", "{:.0f}"),
    "m8": (">=", "skill_hit_rate", "{:.0%}"), "m9": ("<", "long_session_share", "{:.0%}"),
    "m10": ("<=", "compactions_per_session", "{:.1f}"), "m11": ("<", "timer_share", "{:.0%}"),
    "m12": ("=", "unpriced_sessions", "{:.0f}"),
}


def fmt(mid, v):
    return "-" if v is None else FORMAT[mid](v)


SHARES = ("m6", "m8", "m9", "m11")


def delta_text(mid, d):
    if mid in SHARES:
        return f"{d * 100:+.1f}pp"
    return f"{d:+.0f}" if mid in ("m4", "m7", "m12") else f"{d:+.2f}"


def metric_value(mid, m, ns):
    return ns["cost_per_merged_pr"] if mid == "north_star" else m[mid]["value"]


def parse_date(s, end=False):
    t = lib.parse_ts(s)
    if t is None:
        raise SystemExit(f"bad date: {s}")
    return t + DAY - 1 if end and len(s) == 10 else t


def render(rep):
    out = [f"reflect weekly report: {rep['window']['from']} to {rep['window']['to']} "
           f"({rep['window']['days']} days), {rep['sessions']} sessions "
           f"(before: {rep['sessions_before']})"]
    if rep["sessions"] == 0:
        out.append("no sessions in the window")
        return "\n".join(out) + "\n"
    if rep["changes"]:
        out += ["", "changes since their date"]
        for c in rep["changes"]:
            now = "-" if c["now"] is None else f"{c['now']:.2f}"
            delta = "-" if c["delta"] is None else f"{c['delta']:+.2f}"
            flag = "  no-op candidate: remove or rework" if c["no_op_candidate"] else ""
            out.append(f"  {c['rule']} ({c['metric']}) since {c['date']}: "
                       f"baseline {c['baseline']} now {now} delta {delta}{flag}")
    ns = rep["north_star"]
    out += ["", "north star"]
    if ns["withheld"]:
        out.append(f"  withheld: missing {', '.join(ns['withheld'])}")
    else:
        out.append(f"  cost per merged PR: ${ns['cost_per_merged_pr']:.2f} "
                   f"(target <= ${rep['target_cost_per_merged_pr']:.2f})")
        out.append(f"  merged share {ns['merged_share']:.0%} ({ns['merged']} of {ns['prs']} PRs), "
                   f"hours to merge p50 {ns['hours_to_merge_p50']:.1f}, "
                   f"review rounds p50 {ns['review_rounds_p50']:.0f}")
    out += ["", f"{'metric':<34}{'now':>10}{'before':>10}{'delta':>10}  {'target':<9}status"]
    for mid in NAMES:
        e = rep["metrics"][mid]
        delta = "-" if e["value"] is None or e["before"] is None else \
            delta_text(mid, e["value"] - e["before"])
        target = "track" if e["target"] is None else e["target"]
        out.append(f"{mid + ' ' + NAMES[mid]:<34}{fmt(mid, e['value']):>10}"
                   f"{fmt(mid, e['before']):>10}{delta:>10}  {target:<9}{e['status']}")
    out += ["", "alerts"] + ([f"  {a['text']}" for a in rep["alerts"]] or ["  none"])
    return "\n".join(out) + "\n"


def build(recs, outcomes, th, lo, hi, days, changes):
    span = days * DAY
    now_recs = [r for r in recs if in_window(r, lo, hi)]
    before_recs = [r for r in recs if in_window(r, lo - span, lo)]
    m, ns, alerts = compute(now_recs, outcomes, th)
    bm, bns, _ = compute(before_recs, outcomes, th) if before_recs else ({}, {}, [])
    fired = {a["metric"] for a in alerts}
    metrics = {}
    for mid in NAMES:
        e = dict(m[mid])
        e["before"] = bm.get(mid, {}).get("value")
        spec = TARGET[mid]
        e["target"] = None if spec is None else spec[0] + spec[2].format(th["target"][spec[1]])
        ok = meets(mid, e["value"], th["target"])
        e["status"] = "!!" if mid in fired else ("ok" if ok else ("-" if ok is None else ".."))
        metrics[mid] = e
    rows = []
    for c in changes:
        since = parse_date(str(c.get("date")))
        sub = [r for r in recs if since <= (lib.parse_ts(r.get("ts_last")) or 0) <= hi]
        cm, cns, _ = compute(sub, outcomes, th) if sub else ({}, {"cost_per_merged_pr": None}, [])
        now = metric_value(c.get("metric"), cm, cns) if cm or c.get("metric") == "north_star" else None
        base = c.get("baseline")
        delta = None if now is None or not isinstance(base, (int, float)) else now - base
        age = int((hi - since) // DAY)
        tol = th["window"]["no_op_tolerance"] * abs(base or 0)
        rows.append({"date": c.get("date"), "rule": c.get("rule"), "metric": c.get("metric"),
                     "baseline": base, "now": now, "delta": delta, "age_days": age,
                     "no_op_candidate": delta is not None and age >= th["window"]["stale_change_days"]
                     and abs(delta) <= tol})
    return {
        "window": {"from": lib.iso(lo + 1)[:10], "to": lib.iso(hi)[:10], "days": days},
        "sessions": len(now_recs), "sessions_before": len(before_recs),
        "metrics": metrics if now_recs else {}, "north_star": ns, "alerts": alerts,
        "changes": rows, "target_cost_per_merged_pr": th["target"]["cost_per_merged_pr"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--records", action="append", default=[])
    ap.add_argument("--outcomes")
    ap.add_argument("--until")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--thresholds")
    ap.add_argument("--changes")
    ap.add_argument("--dispatch")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    th = load_thresholds(a.thresholds)
    dispatch = None
    if a.dispatch:
        with open(a.dispatch) as fh:
            dispatch = json.load(fh)
    until = a.until or time.strftime("%Y-%m-%d", time.gmtime())
    hi = parse_date(until, end=True)
    recs = load_records(a.paths, a.records, dispatch)
    outcomes = {r["ref"]: r for r in read_jsonl(a.outcomes)} if a.outcomes else {}
    changes = read_jsonl(a.changes) if a.changes else []
    rep = build(recs, outcomes, th, hi - a.days * DAY, hi, a.days, changes)
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(rep, fh, indent=2, sort_keys=True)
            fh.write("\n")
    sys.stdout.write(render(rep))
    return 1 if rep["alerts"] else 0


if __name__ == "__main__":
    sys.exit(main())
