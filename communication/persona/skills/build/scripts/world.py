#!/usr/bin/env python3
"""Build a persona's world model by predicting each next message before learning from it.

  world.py init          --persona P [--seed S] [--force]
  world.py run           --persona P --runner R [--max-steps N] [--max-cost-usd X] [--resume]
  world.py cost-estimate --persona P --runner R --steps N [--max-cost-usd X]
  world.py status        --persona P
  world.py final         --persona P --runner R [--max-cost-usd X] [--rerun-test REASON]
  world.py render        --persona P
  world.py validate      --persona P

Per stream item: extract the point (no words of the message), PREDICT the message from map.md,
SCORE prediction against the actual (blind pick and rubric), UPDATE the map with JSON patches when
the surprise is high or the item is new, CONSOLIDATE every N steps. Checkpoint after every step.
The split's test slice is sealed: never streamed, judged once by `final`.
See ../references/world-model.md.
"""

import argparse
import copy
import fcntl
import hashlib
import json
import math
import os
import random
import re
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import personalib as m  # noqa: E402
import evaluate as ev  # noqa: E402

TYPES = ("entity", "belief", "decision_rule", "reaction_pattern", "format_rule", "lexicon", "never_do")
TITLES = {"entity": "Entities", "belief": "Beliefs", "decision_rule": "Decision rules",
          "reaction_pattern": "Reaction patterns", "format_rule": "Format rules", "lexicon": "Lexicon",
          "never_do": "Never do"}
EDGE_TYPES = ("supports", "applies-to")
BANDS = ("short", "long", "any")
MISSED = ("format", "length", "content", "belief", "reaction", "vocabulary")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
MAX_TEXT = 280
MAX_PATCHES = 24
OPS = ("add", "strengthen", "weaken", "revise", "remove", "merge", "add_edge", "remove_edge")
CONSOLIDATE_OPS = tuple(o for o in OPS if o != "add")
ROLE_DEFAULTS = {"extract": "execution", "predict": "reasoning", "score": "execution", "update": "reasoning",
                 "consolidate": "reasoning", "generate": "reasoning", "judge": "reasoning"}

SYS_PREDICT = ("You predict the next message one specific person writes, from a world model of that person. "
               "Output only the message text.")
SYS_UPDATE = "You maintain a world model of one person as a small graph. Reply with JSON only."

SCORE_EXTRA = ('\nIn the same JSON also give "missed": what the CANDIDATE got wrong, a list from format, '
               'length, content, belief, reaction, vocabulary (empty when nothing); and "entities": the '
               "named people, projects, places and products the REFERENCE mentions (names only, empty when none).")

SCHEMA_HELP = f"""Map schema: nodes {{"id": slug [a-z0-9-], "type": one of {", ".join(TYPES)},
"text": a general rule or fact in your own words (at most {MAX_TEXT} characters), "confidence": 0 to 1}};
format_rule nodes also need "band" (short, long or any) and "channel". Edges {{"from", "to",
"type": supports or applies-to}}. Patch ops: {{"op": "add", "node": {{...}}}}, {{"op": "strengthen" or
"weaken", "id", "by"?}}, {{"op": "revise", "id", "text", "confidence"?}}, {{"op": "remove", "id"}},
{{"op": "merge", "ids": [...], "into": {{node}}}}, {{"op": "add_edge" or "remove_edge", "edge": {{...}}}}.
Evidence is recorded for you."""


class PatchError(ValueError):
    pass


@dataclass
class Opts:
    models: dict = field(default_factory=dict)
    threshold: float = 0.3
    window: int = 20
    consolidate_every: int = 10
    max_nodes: int = 120
    max_map_bytes: int = 16384
    exemplars: int = 4
    seed: int = 1337

    def model(self, role):
        return m.resolve_model(self.models.get(role) or ROLE_DEFAULTS[role])[0]


# --- files -----------------------------------------------------------------------------------

def dumps(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_atomic(path, text):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_json(path, step):
    return json.loads(m.require(path, step).read_text(encoding="utf-8"))


@contextmanager
def locked(d):
    fd = os.open(Path(d) / ".world.lock", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise m.Fail(f"another world.py run holds {d}: wait for it to finish") from e
        yield
    finally:
        os.close(fd)


# --- stream ----------------------------------------------------------------------------------

def parse_ts(s):
    """An aware datetime from ISO 8601 or RFC 2822 (naive counts as UTC), else None."""
    s = (s or "").strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            dt = parsedate_to_datetime(s)
        except (TypeError, ValueError, IndexError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def order_stream(items, seed):
    """(ids, order, reason): chronological when every ts parses, else a recorded seeded shuffle."""
    stamps = [parse_ts(it.get("ts")) for it in items]
    bad = sum(1 for t in stamps if t is None)
    if items and not bad:
        idx = sorted(range(len(items)), key=lambda k: (stamps[k], k))
        return [items[k]["id"] for k in idx], "chronological", ""
    ids = sorted(it["id"] for it in items)
    random.Random(seed).shuffle(ids)
    return ids, "seeded", f"{bad} of {len(items)} items have no parseable ts"


def init(d, seed=None, force=False):
    d = Path(d)
    manifest, train, dev, test = m.load_split(d)
    if (d / "stream.json").exists() and not force:
        raise m.Fail("world.py init already ran: pass --force to start over (drops the map, log and curve; "
                     "the ledger stays)")
    held = dev + test
    keys = [m.grams(h["text"]) for h in held]
    kept, dropped = [], []
    for t in train:
        g = m.grams(t["text"])
        (dropped if any(m.jaccard(g, k) >= m.NEAR_DUP for k in keys) else kept).append(t)
    seed = manifest.get("seed", 1337) if seed is None else seed
    ids, order, reason = order_stream(kept, seed)
    stream = {"version": 1, "split_id": manifest["split_id"], "corpus_hash": manifest.get("corpus_hash"),
              "order": order, "seed": seed, "reason": reason, "ids": ids,
              "sealed": [h["id"] for h in test], "dropped_near_duplicates": sorted(t["id"] for t in dropped)}
    for f in ("map.next.json", "log.jsonl", "curve.json"):
        (d / f).unlink(missing_ok=True)
    write_atomic(d / "stream.json", dumps(stream))
    mp = empty_map(d.name)
    text = dumps(mp)
    write_atomic(d / "map.json", text)
    write_atomic(d / "map.md", render(mp))
    write_atomic(d / "curve.json", dumps(curve([], 20)))
    write_atomic(d / "state.json", dumps({"next": 0, "map_hash": text_hash(text), "steps_total": len(ids),
                                         "ledger_total": round(ledger_total(d), 6)}))
    return stream


def ledger_total(d):
    return sum(float(r.get("cost_usd") or 0) for r in m.read_jsonl(Path(d) / "ledger.jsonl"))


def check_split(d):
    stream = load_json(Path(d) / "stream.json", "world.py init")
    manifest, train, dev, test = m.load_split(d)
    if manifest["split_id"] != stream["split_id"]:
        raise m.Fail(f"the split changed since world.py init ({stream['split_id']} -> {manifest['split_id']}): "
                     "run world.py init --force")
    return stream, train, test


# --- map -------------------------------------------------------------------------------------

def empty_map(persona):
    return {"version": 1, "persona": persona, "step": 0, "nodes": [], "edges": []}


def normalize(mp):
    for n in mp["nodes"]:
        n["evidence"] = sorted(set(n["evidence"]))
    mp["nodes"].sort(key=lambda n: n["id"])
    uniq = {(e["from"], e["to"], e["type"]) for e in mp["edges"]}
    mp["edges"] = [{"from": f, "to": t, "type": ty} for f, t, ty in sorted(uniq)]
    return mp


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def node_errors(n, seen=None):
    nid = n.get("id") if isinstance(n, dict) else None
    where = f"node {nid!r}"
    if not isinstance(n, dict):
        return ["node is not an object"]
    errs = []
    if not isinstance(nid, str) or not SLUG.match(nid):
        errs.append(f"{where}: bad id (slug [a-z0-9-], 48 chars at most)")
    if n.get("type") not in TYPES:
        errs.append(f"{where}: unknown type {n.get('type')!r}")
    t = n.get("text")
    if not isinstance(t, str) or not t.strip() or len(t) > MAX_TEXT:
        errs.append(f"{where}: text must be 1 to {MAX_TEXT} characters")
    c = n.get("confidence")
    if not _num(c) or not 0 <= c <= 1:
        errs.append(f"{where}: confidence must be within 0 to 1")
    evid = n.get("evidence")
    if not isinstance(evid, list) or not evid or not all(isinstance(x, str) for x in evid):
        errs.append(f"{where}: no evidence item ids")
    elif seen is not None:
        unseen = [x for x in evid if x not in seen]
        if unseen:
            errs.append(f"{where}: evidence {unseen[0]} is unseen (not an earlier stream item)")
    if n.get("type") == "format_rule":
        if n.get("band") not in BANDS:
            errs.append(f"{where}: format_rule needs band short, long or any")
        if not isinstance(n.get("channel"), str) or not n.get("channel", "").strip():
            errs.append(f"{where}: format_rule needs a channel")
    return errs


def validate_map(mp, seen=None, max_nodes=120, max_map_bytes=16384):
    """Errors of a map against the schema (empty list = valid)."""
    if not isinstance(mp, dict) or not isinstance(mp.get("nodes"), list) or not isinstance(mp.get("edges"), list):
        return ["map must be an object with nodes and edges lists"]
    errs = []
    if mp.get("version") != 1:
        errs.append("map version must be 1")
    ids = set()
    for n in mp["nodes"]:
        errs += node_errors(n, seen)
        nid = n.get("id") if isinstance(n, dict) else None
        if nid in ids:
            errs.append(f"duplicate node id {nid!r}")
        ids.add(nid)
    keys = set()
    for e in mp["edges"]:
        if not isinstance(e, dict):
            errs.append("edge is not an object")
            continue
        k = (e.get("from"), e.get("to"), e.get("type"))
        if e.get("from") not in ids or e.get("to") not in ids:
            errs.append(f"edge {k}: unknown node")
        if e.get("from") == e.get("to"):
            errs.append(f"edge {k}: joins a node to itself")
        if e.get("type") not in EDGE_TYPES:
            errs.append(f"edge {k}: unknown edge type")
        if k in keys:
            errs.append(f"edge {k}: duplicate")
        keys.add(k)
    if len(mp["nodes"]) > max_nodes:
        errs.append(f"{len(mp['nodes'])} nodes, over the cap of {max_nodes} nodes")
    if len(mp["edges"]) > 2 * max_nodes:
        errs.append(f"{len(mp['edges'])} edges, over the cap of {2 * max_nodes} edges")
    if not errs:
        size = len(render(mp).encode("utf-8"))
        if size > max_map_bytes:
            errs.append(f"map.md is {size} bytes, over {max_map_bytes} bytes")
    return errs


def _evidence(p, seen):
    extra = p.get("evidence", [])
    if not isinstance(extra, list) or not all(isinstance(x, str) for x in extra):
        raise PatchError("evidence must be a list of item ids")
    bad = [x for x in extra if x not in seen]
    if bad:
        raise PatchError(f"evidence {bad[0]} is not a seen stream item")
    return extra


def _build_node(spec, seen, step, base_evidence):
    if not isinstance(spec, dict):
        raise PatchError("node must be an object")
    n = {"id": spec.get("id"), "type": spec.get("type"),
         "text": spec.get("text").strip() if isinstance(spec.get("text"), str) else spec.get("text"),
         "confidence": spec.get("confidence", 0.5), "created": step, "updated": step}
    extra = _evidence(spec, seen)
    n["evidence"] = sorted(set(base_evidence) | set(extra))
    if n["type"] == "format_rule":
        n["band"], n["channel"] = spec.get("band"), spec.get("channel")
    errs = node_errors(n, seen)
    if errs:
        raise PatchError(errs[0])
    n["confidence"] = round(float(n["confidence"]), 4)
    return n


def _apply_one(mp, p, item_id, seen, step, max_nodes, ops):
    if not isinstance(p, dict):
        raise PatchError("patch is not an object")
    op = p.get("op")
    if op not in OPS:
        raise PatchError(f"unknown op {op!r}")
    if op not in ops:
        raise PatchError(f"op {op} is not allowed here")
    extra = _evidence(p, seen)
    tag = set(extra) | ({item_id} if item_id else set())
    nodes = {n["id"]: n for n in mp["nodes"]}

    def get(nid):
        if nid not in nodes:
            raise PatchError(f"unknown node {nid!r}")
        return nodes[nid]

    def touch(n):
        n["evidence"] = sorted(set(n["evidence"]) | tag)
        n["updated"] = step

    if op == "add":
        n = _build_node(p.get("node"), seen, step, tag)
        if n["id"] in nodes:
            raise PatchError(f"duplicate node id {n['id']!r}")
        if len(nodes) >= max_nodes:
            raise PatchError(f"cap: the map holds {max_nodes} nodes")
        mp["nodes"].append(n)
    elif op in ("strengthen", "weaken"):
        n = get(p.get("id"))
        by = p.get("by", 0.1)
        if not _num(by) or not 0 < by <= 1:
            raise PatchError("by must be within 0 and 1")
        c = n["confidence"] + (by if op == "strengthen" else -by)
        n["confidence"] = round(min(1.0, max(0.0, c)), 4)
        touch(n)
    elif op == "revise":
        n = get(p.get("id"))
        new = dict(n, text=p.get("text").strip() if isinstance(p.get("text"), str) else p.get("text"))
        if "confidence" in p:
            new["confidence"] = p["confidence"]
        errs = node_errors(new)
        if errs:
            raise PatchError(errs[0])
        n.update(text=new["text"], confidence=round(float(new["confidence"]), 4))
        touch(n)
    elif op == "remove":
        get(p.get("id"))
        nid = p["id"]
        mp["nodes"] = [x for x in mp["nodes"] if x["id"] != nid]
        mp["edges"] = [e for e in mp["edges"] if nid not in (e["from"], e["to"])]
    elif op == "merge":
        ids = p.get("ids")
        if not isinstance(ids, list) or len(set(map(str, ids))) < 2:
            raise PatchError("merge needs 2 or more distinct ids")
        olds = [get(x) for x in ids]
        into = p.get("into") if isinstance(p.get("into"), dict) else None
        if into is None:
            raise PatchError("merge needs an into node")
        if into.get("id") in nodes and into.get("id") not in ids:
            raise PatchError(f"duplicate node id {into.get('id')!r}")
        spec = dict(into)
        spec.setdefault("confidence", max(o["confidence"] for o in olds))
        if into.get("type") == "format_rule":
            first = next((o for o in olds if o["type"] == "format_rule"), {})
            spec.setdefault("band", first.get("band"))
            spec.setdefault("channel", first.get("channel"))
        union = set(tag)
        for o in olds:
            union |= set(o["evidence"])
        n = _build_node(spec, seen | union, step, union)
        n["created"] = min(o["created"] for o in olds)
        gone = set(ids)
        mp["nodes"] = [x for x in mp["nodes"] if x["id"] not in gone] + [n]
        edges = []
        for e in mp["edges"]:
            f, t = (n["id"] if e["from"] in gone else e["from"]), (n["id"] if e["to"] in gone else e["to"])
            if f != t:
                edges.append({"from": f, "to": t, "type": e["type"]})
        mp["edges"] = edges
    else:
        e = p.get("edge")
        if not isinstance(e, dict):
            raise PatchError("edge must be an object")
        k = {"from": e.get("from"), "to": e.get("to"), "type": e.get("type")}
        if op == "remove_edge":
            if k not in mp["edges"]:
                raise PatchError(f"unknown edge {k}")
            mp["edges"].remove(k)
            return
        get(k["from"])
        get(k["to"])
        if k["from"] == k["to"]:
            raise PatchError("an edge joins two distinct nodes")
        if k["type"] not in EDGE_TYPES:
            raise PatchError(f"unknown edge type {k['type']!r}")
        if k in mp["edges"]:
            raise PatchError("duplicate edge")
        if len(mp["edges"]) >= 2 * max_nodes:
            raise PatchError(f"cap: the map holds {2 * max_nodes} edges")
        mp["edges"].append(k)


def apply_patches(mp, patches, item_id, seen, step, max_nodes, ops=OPS):
    """Apply each patch on its own, atomically; return (applied, rejected [{patch, reason}])."""
    applied, rejected = [], []
    seen = set(seen)
    for k, p in enumerate(patches if isinstance(patches, list) else []):
        if k >= MAX_PATCHES:
            rejected.append({"patch": p, "reason": f"more than {MAX_PATCHES} patches in one reply"})
            continue
        cand = copy.deepcopy(mp)
        try:
            _apply_one(cand, p, item_id, seen, step, max_nodes, ops)
        except PatchError as e:
            rejected.append({"patch": p, "reason": str(e)})
            continue
        mp.clear()
        mp.update(normalize(cand))
        applied.append(p)
    normalize(mp)
    return applied, rejected


def prune(mp, max_nodes, max_bytes=None):
    """Drop nodes by lowest confidence, fewest evidence, oldest update, id until the map fits."""
    removed = []
    order = sorted(mp["nodes"], key=lambda n: (n["confidence"], len(n["evidence"]), n["updated"], n["id"]))
    for n in order:
        fits = len(mp["nodes"]) <= max_nodes and (
            max_bytes is None or len(render(mp).encode("utf-8")) <= max_bytes)
        if fits:
            break
        mp["nodes"] = [x for x in mp["nodes"] if x["id"] != n["id"]]
        mp["edges"] = [e for e in mp["edges"] if n["id"] not in (e["from"], e["to"])]
        removed.append(n["id"])
    normalize(mp)
    return removed


def _node_line(n):
    return f"- [{n['id']}] {n['text']} (confidence {n['confidence']:.2f}, evidence {len(n['evidence'])})"


def render(mp):
    """map.md: fixed section order, nodes by confidence then id, no timestamps."""
    nodes = sorted(mp["nodes"], key=lambda n: (-n["confidence"], n["id"]))
    out = [f"# World model: {mp.get('persona', '')}", "",
           f"steps: {mp.get('step', 0)}; nodes: {len(mp['nodes'])}; edges: {len(mp['edges'])}",
           "Confidence runs 0 to 1; evidence counts the stream items behind a node. A simulation of how "
           "the person writes and thinks, learned from their messages; not their words.", ""]
    for t in TYPES:
        out += [f"## {TITLES[t]}", ""]
        group = [n for n in nodes if n["type"] == t]
        if t == "format_rule":
            keys = sorted({(BANDS.index(n["band"]), n["channel"]) for n in group})
            for bi, ch in keys:
                out += [f"### {BANDS[bi]} / {ch}", ""]
                out += [_node_line(n) for n in group if n["band"] == BANDS[bi] and n["channel"] == ch]
                out.append("")
        else:
            out += [_node_line(n) for n in group]
            out.append("")
        if not group:
            out[-1:] = ["- none yet", ""]
    out += ["## Edges", ""]
    edges = sorted((e["from"], e["type"], e["to"]) for e in mp["edges"])
    out += [f"- {f} {ty} {t}" for f, ty, t in edges] or ["- none yet"]
    return "\n".join(out) + "\n"


# --- math ------------------------------------------------------------------------------------

def surprise(hit, rubric):
    return round(0.5 * hit + 0.5 * (1 - rubric / 5), 4)


def _window(rows):
    if not rows:
        return None
    n = len(rows)
    return {"n": n, "id_rate": round(sum(r["hit"] for r in rows) / n, 4),
            "rubric": round(sum(r["rubric"] for r in rows) / n, 4),
            "surprise": round(sum(r["surprise"] for r in rows) / n, 4)}


def curve(rows, window):
    scored = [r for r in rows if not r.get("excluded") and r.get("surprise") is not None]
    points = [dict(_window(scored[max(0, k - window + 1):k + 1]), step=r["step"]) for k, r in enumerate(scored)]
    return {"window": window, "points": points, "first": _window(scored[:window]),
            "last": _window(scored[-window:]), "scored": len(scored), "excluded": len(rows) - len(scored)}


# --- the loop --------------------------------------------------------------------------------

def predict_prompt(map_md, it, ext):
    return (f"World model of the person:\n{map_md}\n\nPredict the next message this person writes.\n"
            f"Channel: {it['channel']}\nAudience: {it['audience']}\n"
            f"Context: {ext.get('context') or it['context'] or 'none given'}\n"
            f"What it communicates: {ext.get('point', '')}\nIntent: {ext.get('intent', '')}\n"
            "Choose the length and form the person would use here. Output only the message, no quotes, "
            "no commentary.")


def update_prompt(mp, it, row):
    pred = row.get("prediction")
    delta = ("none: this item was not predicted (" + str(row["excluded"]) + ")" if pred is None else
             f"identified by the judge: {row['identified']}; rubric 0-5: {json.dumps(row['scores'])}; "
             f"missed: {', '.join(row['missed']) or 'nothing listed'}; judge notes: "
             + "; ".join(f"{k}: {v}" for k, v in sorted((row.get('reasons') or {}).items())))
    return (f"{SCHEMA_HELP}\n\nCurrent map (JSON):\n{json.dumps(mp, ensure_ascii=False, sort_keys=True)}\n\n"
            f"The person's ACTUAL message (channel {it['channel']}, audience {it['audience']}, "
            f"{it['band']}, context: {it['context'] or 'none given'}):\n<<<\n{it['text']}\n>>>\n"
            f"The map's PREDICTION:\n<<<\n{pred if pred is not None else '(none)'}\n>>>\n"
            f"Delta: {delta}\n\n"
            "Return small patches that make the next prediction better: prefer strengthen, weaken and "
            "revise over add; add a node only for something new (an entity, belief, decision rule, "
            "reaction, format rule for this band and channel, a characteristic word, or a never-do). "
            "Rules are general, in your own words; a lexicon node may hold a short characteristic phrase. "
            f'At most {MAX_PATCHES} patches. JSON: {{"patches": [...]}}')


def consolidate_prompt(mp, target):
    return (f"{SCHEMA_HELP}\n\nCurrent map (JSON):\n{json.dumps(mp, ensure_ascii=False, sort_keys=True)}\n\n"
            f"Consolidate it to at most {target} nodes: merge duplicates and near duplicates (merge keeps "
            "the union of evidence), remove weak or redundant nodes, revise vague text. Do not add nodes. "
            f'JSON: {{"patches": [...]}}')


def _call_json(runner, role, model, system, prompt, meta):
    try:
        out = runner.complete(role, model, system, prompt, meta)
    except m.RunnerError:
        return None, "error"
    obj = m.parse_json(out)
    if not obj or not isinstance(obj.get("patches"), list):
        return None, "unparseable"
    return obj["patches"], None


def do_step(i, it, ids, items, mp, runner, opts):
    """One step on a copy of the map: (row, new map). Writes nothing."""
    mp = copy.deepcopy(mp)
    seen = set(ids[:i + 1])
    past = [items[x] for x in ids[:i]]
    row = {"step": i, "item": it["id"], "band": it["band"], "channel": it["channel"], "excluded": None,
           "prediction": None, "exemplars": [], "original_pos": None, "picked": None, "identified": None,
           "hit": None, "scores": None, "reasons": {}, "rubric": None, "surprise": None, "missed": [],
           "entities": [], "new": [], "update": None, "skip": None, "update_error": None, "applied": [],
           "rejected": [], "consolidate": None}
    base = {"item_id": it["id"], "step": i, "channel": it["channel"]}
    ext, excluded, _ = ev.extract_point(runner, opts.model("extract"), it,
                                        dict(base, original=it["text"], band=it["band"], context=it["context"]))
    if ext is None:
        row["excluded"] = excluded
    else:
        try:
            pred = runner.complete("predict", opts.model("predict"), SYS_PREDICT,
                                   predict_prompt(render(mp), it, ext), dict(base, point=ext["point"])).strip()
        except m.RunnerError:
            pred = None
            row["excluded"] = "error"
        if pred is not None and m.copied(pred, it["text"]):
            row["excluded"] = "copied"
        elif pred is not None:
            row["prediction"] = pred
            ex = ev.pick_exemplars(past, it, opts.exemplars, opts.seed)
            row["exemplars"] = [t["id"] for t in ex]
            first = m.original_first(opts.seed, 0, it["id"])
            a, b = (it["text"], pred) if first else (pred, it["text"])
            row["original_pos"] = "A" if first else "B"
            judge = dict(base, original=it["text"], band=it["band"], context=it["context"])
            try:
                out = runner.complete("identify", opts.model("score"), ev.SYS_JUDGE, ev.identify_prompt(it, ext, ex, a, b),
                                      dict(judge, original_pos=row["original_pos"], candidates=(a, b)))
                pick = str((m.parse_json(out) or {}).get("original", "")).strip().upper()
            except m.RunnerError:
                pick = ""
            if pick in ("A", "B"):
                row["picked"], row["identified"] = pick, pick == row["original_pos"]
            obj = {}
            try:
                out = runner.complete("score", opts.model("score"), ev.SYS_JUDGE,
                                      ev.score_prompt(it, ex, pred) + SCORE_EXTRA, judge)
                row["scores"], row["reasons"] = ev.parse_scores(out)
                obj = m.parse_json(out) or {}
            except m.RunnerError:
                pass
            row["scores"] = row["scores"] or None
            missed = obj.get("missed") if isinstance(obj.get("missed"), list) else []
            row["missed"] = sorted({x for x in missed if x in MISSED})
            ents = obj.get("entities") if isinstance(obj.get("entities"), list) else []
            row["entities"] = [e.strip()[:60] for e in ents if isinstance(e, str) and e.strip()][:10]
            row["hit"] = 0 if row["identified"] is False else 1
            row["rubric"] = round(sum(row["scores"].values()) / len(m.DIMS), 4) if row["scores"] else 0.0
            row["surprise"] = surprise(row["hit"], row["rubric"])

    blob = f" {m.canonical(' '.join(n['text'] for n in mp['nodes']))} "
    new = []
    if not mp["nodes"]:
        new.append("empty_map")
    if "belief" in row["missed"]:
        new.append("belief")
    if any(m.canonical(e) and f" {m.canonical(e)} " not in blob for e in row["entities"]):
        new.append("entity")
    row["new"] = new
    if row["excluded"] or new or row["surprise"] >= opts.threshold:
        row["update"] = "update"
        patches, err = _call_json(runner, "update", opts.model("update"), SYS_UPDATE, update_prompt(mp, it, row),
                                  dict(base, map=copy.deepcopy(mp)))
        row["update_error"] = err
        row["applied"], row["rejected"] = apply_patches(mp, patches or [], it["id"], seen, i, opts.max_nodes)
    else:
        row["update"], row["skip"] = "skip", "low_surprise"

    capped = any(r["reason"].startswith("cap") for r in row["rejected"])
    if (i + 1) % max(1, opts.consolidate_every) == 0 or capped:
        target = max(1, int(opts.max_nodes * 0.8))
        before = len(mp["nodes"])
        patches, err = _call_json(runner, "consolidate", opts.model("consolidate"), SYS_UPDATE,
                                  consolidate_prompt(mp, target), dict(base, map=copy.deepcopy(mp)))
        applied, rejected = apply_patches(mp, patches or [], None, seen, i, opts.max_nodes, CONSOLIDATE_OPS)
        pruned = prune(mp, target, int(opts.max_map_bytes * 0.8))
        row["consolidate"] = {"before": before, "after": len(mp["nodes"]), "applied": len(applied),
                              "rejected": len(rejected), "error": err, "pruned": pruned}
    hard = prune(mp, opts.max_nodes, opts.max_map_bytes)
    if hard:
        row["pruned"] = hard
    mp["step"] = i + 1
    row["nodes"] = len(mp["nodes"])
    return row, mp


def recover(d):
    """Finish or undo a half-written step; refuse a hand-edited map. Returns state.json."""
    st = load_json(d / "state.json", "world.py init")
    nxt = d / "map.next.json"
    if nxt.exists():
        if file_hash(nxt) == st["map_hash"]:
            os.replace(nxt, d / "map.json")
        else:
            nxt.unlink()
    if file_hash(d / "map.json") != st["map_hash"]:
        raise m.Fail("map.json changed outside world.py (its hash is not the checkpoint's): restore it, or "
                     "run world.py init --force to start over")
    rows = m.read_jsonl(d / "log.jsonl")
    keep = [r for r in rows if r["step"] < st["next"]]
    if len(keep) != len(rows):
        write_atomic(d / "log.jsonl", "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n"
                                               for r in keep))
    return st


def commit(d, i, mp, row, st, opts):
    """Paired commit: map.next.json, log row, state.json, then the rename and the derived files."""
    text = dumps(mp)
    write_atomic(d / "map.next.json", text)
    fd = os.open(d / "log.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    st = dict(st, next=i + 1, map_hash=text_hash(text), ledger_total=round(ledger_total(d), 6))
    write_atomic(d / "state.json", dumps(st))
    os.replace(d / "map.next.json", d / "map.json")
    write_atomic(d / "map.md", render(mp))
    write_atomic(d / "curve.json", dumps(curve(m.read_jsonl(d / "log.jsonl"), opts.window)))
    return st


def run(d, runner, opts, max_steps=None, resume=False, echo=None):
    """Run steps until the stream ends or max_steps; return the number of steps done."""
    d = Path(d)
    stream, train, _ = check_split(d)
    items = {r["id"]: r for r in train}
    ids = stream["ids"]
    with locked(d):
        st = recover(d)
        if st["next"] > 0 and not resume:
            raise m.Fail(f"the loop already ran {st['next']} of {len(ids)} steps: pass --resume to continue")
        mp = json.loads((d / "map.json").read_text(encoding="utf-8"))
        done = 0
        while st["next"] < len(ids) and (max_steps is None or done < max_steps):
            i = st["next"]
            if getattr(runner, "tags", None) is not None:
                runner.tags = {"tool": "world", "step": i}
            row, mp = do_step(i, items[ids[i]], ids, items, mp, runner, opts)
            st = commit(d, i, mp, row, st, opts)
            done += 1
            if echo:
                echo(f"step {i + 1}/{len(ids)}: surprise {row['surprise']}, {row['update']}, "
                     f"nodes {row['nodes']}, spent ${st['ledger_total']:.4f}")
    return done


# --- final -----------------------------------------------------------------------------------

def cost_summary(d):
    rows = m.read_jsonl(Path(d) / "ledger.jsonl")
    by_role, by_tool = {}, {}
    for r in rows:
        by_role[r["role"]] = round(by_role.get(r["role"], 0) + float(r["cost_usd"]), 6)
        by_tool[r.get("tool", "?")] = round(by_tool.get(r.get("tool", "?"), 0) + float(r["cost_usd"]), 6)
    return {"total": round(sum(by_role.values()), 6), "by_role": by_role, "by_tool": by_tool,
            "estimated_calls": sum(1 for r in rows if r.get("estimated"))}


def final(d, runner, opts, ledger=None, rerun=None, gen_model="reasoning", judge_model="reasoning"):
    d = Path(d)
    stream, train, test = check_split(d)
    items = {r["id"]: r for r in train}
    ids = stream["ids"]
    with locked(d):
        st = recover(d)
        if st["next"] < len(ids):
            raise m.Fail(f"the loop has run {st['next']} of {len(ids)} steps: finish world.py run --resume first")
        mp = json.loads((d / "map.json").read_text(encoding="utf-8"))
        profile = render(mp)
        sealed = d / "split" / "test.sealed"
        seal = {}
        if sealed.exists():
            seal = json.loads(sealed.read_text(encoding="utf-8") or "{}")
            if not rerun:
                raise m.Fail("the sealed slice was already used (by world.py final or evaluate.py --slice test); "
                             "pass --rerun-test REASON to run it again (it overfits)")
        if not test:
            raise m.Fail("the sealed slice is empty")
        models = {"extract": opts.model("extract"), "generate": m.resolve_model(gen_model)[0],
                  "judge": m.resolve_model(judge_model)[0]}
        warnings = []
        if m.resolve_model(judge_model)[1] != "reasoning":
            warnings.append(f"judge model {models['judge']} is not the reasoning tier: the verdict is weaker")
        m.preflight(ledger, ev.cost_calls(models, profile, test), len(test), "the sealed final")
        runs = seal.get("runs", []) + [{"tool": "world", "map": st["map_hash"], "reason": rerun,
                                        "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}]
        m.write_json(sealed, {"runs": runs})
        if getattr(runner, "tags", None) is not None:
            runner.tags = {"tool": "world-final"}
        stream_items = [items[x] for x in ids]
        results = [ev.run_item(runner, models, it, profile, stream_items, opts.seed, len(runs), opts.exemplars)
                   for it in test]
    rep = m.summarize(results)
    rep["warnings"] = warnings + rep["warnings"]
    cv = curve(m.read_jsonl(d / "log.jsonl"), opts.window)
    rep.update(persona=d.name, slice="sealed", round=len(runs), seed=opts.seed, runner=getattr(runner, "name", ""),
               models=models, map_hash=st["map_hash"], steps=len(ids), test_runs=len(runs), rerun_reason=rerun,
               curve={"window": cv["window"], "first": cv["first"], "last": cv["last"], "scored": cv["scored"],
                      "excluded": cv["excluded"]},
               cost=cost_summary(d))
    out = d / "final"
    m.write_jsonl(out / "items.jsonl", results)
    m.write_json(out / "report.json", rep)
    md = report_md(rep)
    m.write_text(out / "report.md", md)
    return rep, md


def _w(w):
    return "n/a" if not w else f"id rate {w['id_rate']:.2f}, rubric {w['rubric']:.2f}, surprise {w['surprise']:.2f} (n {w['n']})"


def report_md(rep):
    md = ev.report_md(rep).rstrip("\n").split("\n")
    md[0] = f"# persona world model: {rep['persona']} sealed run {rep['round']}"
    c, cost = rep["curve"], rep["cost"]
    md += ["", f"curve (window {c['window']}, {c['scored']} scored steps, {c['excluded']} excluded):",
           f"- first window: {_w(c['first'])}", f"- last window: {_w(c['last'])}",
           f"cost: ${cost['total']:.4f} total; " + ", ".join(f"{k} ${v:.4f}" for k, v in sorted(cost["by_tool"].items()))
           + "; by role: " + ", ".join(f"{k} ${v:.4f}" for k, v in sorted(cost["by_role"].items()))
           + (f" ({cost['estimated_calls']} calls of unknown cost charged their estimate)" if cost["estimated_calls"] else ""),
           f"map: {rep['map_hash']} after {rep['steps']} steps (map.md is the profile the sealed run used)"]
    return "\n".join(md) + "\n"


# --- commands --------------------------------------------------------------------------------

def cost_estimate(d, runner, opts, steps, echo=None):
    st0 = load_json(d / "state.json", "world.py init")
    start = st0["next"]
    n = run(d, runner, opts, max_steps=steps, resume=True, echo=echo)
    rows = m.read_jsonl(d / "ledger.jsonl")
    loop = [r for r in rows if r.get("tool") == "world"]
    per = [sum(float(r["cost_usd"]) for r in loop if r.get("step") == s) for s in range(start, start + n)]
    stream = load_json(d / "stream.json", "world.py init")
    total_steps, done = len(stream["ids"]), start + n
    mean = sum(per) / len(per) if per else 0.0
    spent = sum(float(r["cost_usd"]) for r in loop)

    def role_mean(role):
        c = [float(r["cost_usd"]) for r in loop if r["role"] == role]
        return sum(c) / len(c) if c else 0.0

    per_item = role_mean("extract") + role_mean("predict") + role_mean("identify") + role_mean("score")
    return {"steps_run": n, "stream_steps": total_steps, "steps_done": done, "per_step_mean": round(mean, 6),
            "per_step_max": round(max(per, default=0.0), 6), "spent_loop": round(spent, 6),
            "projected_loop_total": round(spent + mean * (total_steps - done), 6),
            "projected_final": round(per_item * len(stream["sealed"]), 6),
            "final_note": "from the loop's per-role means (predict stands in for generate); a lower bound when "
                          "the final's generator or judge is a stronger tier than the loop's",
            "spent_total": round(ledger_total(d), 6)}


def status(d, opts):
    stream = load_json(d / "stream.json", "world.py init")
    st = load_json(d / "state.json", "world.py init")
    mp = json.loads((d / "map.json").read_text(encoding="utf-8"))
    cv = curve(m.read_jsonl(d / "log.jsonl"), opts.window)
    by_type = {}
    for n in mp["nodes"]:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    return {"order": stream["order"], "steps": f"{st['next']}/{len(stream['ids'])}", "sealed": len(stream["sealed"]),
            "sealed_used": (d / "split" / "test.sealed").exists(), "nodes": len(mp["nodes"]),
            "edges": len(mp["edges"]), "by_type": by_type, "curve_first": cv["first"], "curve_last": cv["last"],
            "cost": cost_summary(d)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["init", "run", "cost-estimate", "status", "final", "render", "validate"])
    m.add_state_args(p)
    p.add_argument("--runner", default="claude", help="claude, stub, or cmd:'<command>'")
    p.add_argument("--stub-script", type=Path, help="scripted replies and costs for --runner stub")
    p.add_argument("--seed", type=int, help="init: stream shuffle seed (default the split seed); run: judge seed")
    p.add_argument("--force", action="store_true", help="init: start over")
    p.add_argument("--resume", action="store_true", help="run: continue after the last checkpoint")
    p.add_argument("--max-steps", type=int, help="run: stop after this many steps")
    p.add_argument("--steps", type=int, default=10, help="cost-estimate: steps to run")
    p.add_argument("--max-cost-usd", type=float, help="refuse the call that would pass this total (exit 4)")
    p.add_argument("--call-estimate-usd", type=float, default=0.5,
                   help="cost assumed for a role and model with no ledger history")
    p.add_argument("--rerun-test", metavar="REASON", help="final: judge the sealed slice again, recording why")
    for role in ("extract", "predict", "score", "update", "consolidate"):
        p.add_argument(f"--{role}-model", default=ROLE_DEFAULTS[role], help="tier or model")
    p.add_argument("--generator-model", default="reasoning", help="final: tier or model")
    p.add_argument("--judge-model", default="reasoning", help="final: tier or model")
    p.add_argument("--threshold", type=float, default=0.3, help="surprise below this skips the update")
    p.add_argument("--window", type=int, default=20, help="curve window")
    p.add_argument("--consolidate-every", type=int, default=10)
    p.add_argument("--max-nodes", type=int, default=120)
    p.add_argument("--max-map-bytes", type=int, default=16384)
    p.add_argument("--exemplars", type=int, default=4, help="earlier stream items shown to the judge")
    a = p.parse_args()
    d = m.state_dir(a)
    m.guard(d, a.allow_git_worktree)
    opts = Opts(models={r: getattr(a, f"{r}_model") for r in ("extract", "predict", "score", "update", "consolidate")},
                threshold=a.threshold, window=a.window, consolidate_every=a.consolidate_every,
                max_nodes=a.max_nodes, max_map_bytes=a.max_map_bytes, exemplars=a.exemplars,
                seed=1337 if a.seed is None else a.seed)
    if a.command == "init":
        m.make_dir(d)
        s = init(d, a.seed, a.force)
        print(f"stream: {len(s['ids'])} items, {s['order']}" + (f" ({s['reason']})" if s["reason"] else "")
              + f"; sealed: {len(s['sealed'])}; dropped near duplicates of sealed items: "
              f"{len(s['dropped_near_duplicates'])}")
        return 0
    if a.command in ("render", "validate"):
        mp = load_json(d / "map.json", "world.py init")
        if a.command == "render":
            write_atomic(d / "map.md", render(mp))
            print(f"rendered {d / 'map.md'}")
            return 0
        stream = load_json(d / "stream.json", "world.py init")
        errs = validate_map(mp, set(stream["ids"]), a.max_nodes, a.max_map_bytes)
        if errs:
            raise m.Fail("map.json invalid:\n" + "\n".join(errs))
        print("valid")
        return 0
    if a.command == "status":
        print(json.dumps(status(d, opts), indent=1))
        return 0
    ledger = m.Ledger(d / "ledger.jsonl", a.max_cost_usd, a.call_estimate_usd, tool="world")
    runner = m.make_runner(a.runner, a.stub_script, ledger)
    runner.name = a.runner
    echo = lambda s: print(s, flush=True)  # noqa: E731
    if a.command == "run":
        n = run(d, runner, opts, a.max_steps, a.resume, echo)
        st = load_json(d / "state.json", "world.py init")
        print(f"{n} steps run; {st['next']}/{st['steps_total']} done; spent ${st['ledger_total']:.4f}")
        return 0
    if a.command == "cost-estimate":
        print(json.dumps(cost_estimate(d, runner, opts, a.steps), indent=1))
        return 0
    _, md = final(d, runner, opts, ledger, a.rerun_test, a.generator_model, a.judge_model)
    print(md, end="")
    print(f"\nwritten to {d / 'final'}")
    return 0


if __name__ == "__main__":
    m.main_wrapper(main)
