#!/usr/bin/env python3
"""One pass over a session transcript, one session record out (metric definitions:
references/metrics.md). Read-only, no network, standard library only, deterministic.

    metrics.py record PATH             one JSON line with the fixed keys: session_id, ts_last,
                                       project, turns, human_prompts, compactions, cost_usd,
                                       context_tokens_peak, tool_errors, timer_turns, outcome
    metrics.py full PATH [--dispatch FILE]
                                       one JSON line with the wide record the report reads
    metrics.py scan PATH [PATH ...] [--dispatch FILE]
                                       one wide record per transcript (files and folders)

--dispatch FILE is JSON {skill: [regex, ...]}: a skill is an "opportunity" in a session when a
human prompt matches one of its regexes.

An unreadable or empty input prints {"error": "..."} and exits 0, so a caller that loops over
many transcripts never stops on one bad file. A session's record never reads its subagents'
transcripts: pass those as their own paths.
"""
import argparse
import importlib.util
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # works under python -I
import cost as costlib  # noqa: E402
import reflectlib as lib  # noqa: E402

LONG_WAIT_S = 1800          # a human wait is a gap above 30 minutes
UNPRICED_MIN_TURNS = 50     # cost 0 over this many turns means the price is missing
BIG_CONTEXT = 300_000       # a timer tick in a context this large is an alert
CHARS_PER_TOKEN = 4
NUDGE_RE = re.compile(r"(continue|go on|keep going|carry on|proceed)[\s.!]*", re.I)
FIXED_KEYS = ("session_id", "ts_last", "project", "turns", "human_prompts", "compactions",
              "cost_usd", "context_tokens_peak", "tool_errors", "timer_turns", "outcome")


def _parse_listing(content):
    spec = importlib.util.spec_from_file_location(
        "context_audit", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "context-audit.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_listing(content)[0]


def _context_of(usage):
    if not isinstance(usage, dict):
        return 0
    return sum(usage.get(k, 0) for k in
               ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
               if isinstance(usage.get(k), (int, float)))


def full_record(path, dispatch=None, prices=None):
    """The wide session record. Raises OSError for an unreadable path, ValueError for no entries."""
    meter = costlib.CostMeter(prices)
    turn_ids, anon_turns = set(), 0
    call_ids, calls_anon = set(), 0
    tool_by_id = {}
    hooks, hook_seen = {}, set()
    skills_invoked, prs, models = set(), set(), set()
    c = dict(human_prompts=0, compactions=0, tool_errors=0, denials=0, interrupts=0, nudges=0,
             hook_blocks=0, hook_block_repeats=0, gate_events=0, timer_turns=0,
             timer_turns_big_context=0, peak=0)
    waits = []
    listing = {}  # skill name -> has a description in the listing
    fixed_chars = 0
    session_id = cwd = None
    t_first = t_last = last_et = last_assistant_et = None
    pending = None  # what the next new assistant turn answers: "timer", "other" or None
    seen_assistant = False
    opportunities = set()
    patterns = {s: [re.compile(p, re.I) for p in ps] for s, ps in (dispatch or {}).items()}
    entries = 0

    for ln, o in lib.iter_entries(path):
        entries += 1
        meter.feed(path, ln, o)
        session_id = session_id or lib.session_id_of(o)
        cwd = cwd or lib.cwd_of(o)
        et = lib.entry_time(o)
        if et is None:
            et = last_et
        else:
            last_et = et
            t_first = et if t_first is None else min(t_first, et)
            t_last = et if t_last is None else max(t_last, et)
        typ = o.get("type")
        msg = lib.message_of(o)
        content = msg.get("content")

        ref = lib.pr_ref(o)
        if ref:
            prs.add(ref)

        if typ == "system" and o.get("subtype") == "init" and not seen_assistant:
            fixed_chars += len(json.dumps(o.get("tools", []), sort_keys=True))
        elif typ == "attachment":
            att = o.get("attachment") if isinstance(o.get("attachment"), dict) else {}
            kind = lib.classify_hook_event(att)
            if att.get("type") == "skill_listing":  # sent in pieces: later ones add skills
                for s in _parse_listing(att.get("content")):
                    listing[s["name"]] = listing.get(s["name"], False) or s["described"]
            if kind == "deny":
                text = lib.hook_text(att)
                name = str(att.get("hookName") or att.get("hookEvent") or "?")
                hooks[name] = hooks.get(name, 0) + 1
                c["hook_blocks"] += 1
                if (name, text) in hook_seen:
                    c["hook_block_repeats"] += 1
                hook_seen.add((name, text))
            elif kind == "nonblocking" and lib.hook_text(att).startswith("policy-gate: BLOCK"):
                c["gate_events"] += 1
            if not seen_assistant and not str(att.get("type", "")).startswith("hook_") \
                    and isinstance(att.get("content"), str):
                fixed_chars += len(att["content"])
        elif typ == "assistant":
            seen_assistant = True
            last_assistant_et = et
            mid = msg.get("id")
            new_turn = True
            if isinstance(mid, str) and mid:
                new_turn = mid not in turn_ids
                turn_ids.add(mid)
            else:
                anon_turns += 1
            ctx = _context_of(msg.get("usage"))
            c["peak"] = max(c["peak"], ctx)
            if isinstance(msg.get("model"), str) and msg["model"]:
                models.add(msg["model"])
            if new_turn:
                if pending == "timer":
                    c["timer_turns"] += 1
                    if ctx >= BIG_CONTEXT:
                        c["timer_turns_big_context"] += 1
                pending = None
            for b in content if isinstance(content, list) else []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                uid = b.get("id")
                if isinstance(uid, str) and uid:
                    if uid in call_ids:
                        continue
                    call_ids.add(uid)
                    tool_by_id[uid] = b.get("name")
                else:
                    calls_anon += 1
                if b.get("name") == lib.SKILL_TOOL and isinstance(
                        (b.get("input") or {}).get("skill"), str):
                    skills_invoked.add(b["input"]["skill"])
        if typ != "user":
            continue

        cls = lib.classify_user_turn(o)
        text = lib.text_of(content)
        if cls == "tool_result":
            timer = False
            for b in content:
                if not isinstance(b, dict) or b.get("type") != "tool_result":
                    continue
                if b.get("is_error"):
                    c["tool_errors"] += 1
                    if any(m in lib.text_of([b]) for m in lib.DENIAL_MARKERS):
                        c["denials"] += 1
                timer = timer or tool_by_id.get(b.get("tool_use_id")) in lib.TIMER_TOOLS
            pending = "timer" if timer else "other"
        elif cls == "human":
            if text.lstrip().startswith(lib.INTERRUPT_PREFIX):
                c["interrupts"] += 1
                continue
            c["human_prompts"] += 1
            if NUDGE_RE.fullmatch(text.strip()):
                c["nudges"] += 1
            if last_assistant_et is not None and et is not None \
                    and et - last_assistant_et > LONG_WAIT_S:
                waits.append(int(et - last_assistant_et))
            last_assistant_et = None
            pending = None
            for skill, rxs in patterns.items():
                if any(rx.search(text) for rx in rxs):
                    opportunities.add(skill)
        elif cls == "compaction_summary":
            c["compactions"] += 1
        elif cls == "task_notification":
            pending = "timer"
        else:
            pending = "other"
            if not seen_assistant and cls in ("injected", "other"):
                fixed_chars += len(text)

    if entries == 0:
        raise ValueError("no transcript entries")

    meter.end_file()
    res = meter.result()
    turns = len(turn_ids) + anon_turns
    state, usage_usd = res["cost_state_usd"], res["usage_usd"]
    source = "cost-state" if state is not None else ("usage" if res["messages"] else None)
    floor = state if state is not None else (usage_usd if res["messages"] else None)
    missing_price = [w for w in res["warnings"] if "<synthetic>" not in w]  # not a real model
    unpriced = bool(res["unknown_model_cost"]) or (state is None and bool(missing_price)) \
        or (floor == 0 and turns > UNPRICED_MIN_TURNS)
    wall = int(t_last - t_first) if t_first is not None and t_last is not None else 0
    pr_list = sorted(prs)
    return {
        "session_id": session_id or os.path.splitext(os.path.basename(path))[0],
        "ts_first": lib.iso(t_first) if t_first is not None else None,
        "ts_last": lib.iso(t_last) if t_last is not None else None,
        "project": os.path.basename(cwd.rstrip("/")) if cwd else
        os.path.basename(os.path.dirname(os.path.abspath(path))),
        "turns": turns,
        "human_prompts": c["human_prompts"],
        "compactions": c["compactions"],
        "cost_usd": None if unpriced or floor is None else round(floor, 6),
        "cost_floor_usd": None if floor is None else round(floor, 6),
        "cost_source": source,
        "unpriced": unpriced,
        "context_tokens_peak": c["peak"],
        "tool_calls": len(call_ids) + calls_anon,
        "tool_errors": c["tool_errors"],
        "timer_turns": c["timer_turns"],
        "timer_turns_big_context": c["timer_turns_big_context"],
        "outcome": "pr-link" if pr_list else None,
        "prs": pr_list,
        "hook_blocks": c["hook_blocks"],
        "hook_block_repeats": c["hook_block_repeats"],
        "hook_blocks_by_hook": dict(sorted(hooks.items())),
        "gate_events": c["gate_events"],
        "interrupts": c["interrupts"],
        "denials": c["denials"],
        "nudges": c["nudges"],
        "waits": waits,
        "wait_seconds": sum(waits),
        "wall_seconds": wall,
        "models": sorted(models),
        "skills_invoked": sorted(skills_invoked),
        "skills_offered": {
            "visible": sorted(n for n, described in listing.items() if described),
            "name_only": sorted(n for n, described in listing.items() if not described),
        },
        "skill_opportunities": sorted(opportunities),
        "fixed_tokens": fixed_chars // CHARS_PER_TOKEN,
    }


def fixed_record(full):
    return {k: full[k] for k in FIXED_KEYS}


def _emit(obj):
    print(json.dumps(obj, sort_keys=True))


def _safe(path, dispatch):
    try:
        return full_record(path, dispatch)
    except (OSError, ValueError) as e:
        return {"error": f"{path}: {e}"}


def _dispatch_table(path):
    if not path:
        return None
    with open(path) as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("record", "full", "scan"))
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--dispatch")
    a = ap.parse_args(argv)
    try:
        table = _dispatch_table(a.dispatch)
    except (OSError, ValueError) as e:
        _emit({"error": f"dispatch table: {e}"})
        return 0
    if a.mode == "scan":
        for p in lib.collect_files(a.paths):
            _emit(_safe(p, table))
        return 0
    rec = _safe(a.paths[0], table)
    _emit(rec if "error" in rec or a.mode == "full" else fixed_record(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
