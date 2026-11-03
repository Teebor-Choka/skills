#!/usr/bin/env python3
"""Engineer a work-division spec into an execution graph, deterministically.

This is the deterministic core of graph engineering: the discipline of splitting work
into a shape a fleet of agents can collaborate on. The agent's only job is to name the
nodes (one deliverable each), their true dependencies, and their write-sets. Everything
graph-theoretic is computed here, not judged: acyclicity, redundant-edge removal
(transitive reduction), parallel waves, the critical path, barriers, write-set
collisions, the concurrency cap, and a pattern label per shape. Same input, same graph,
every time.

Usage:
    graph.py <spec.json> [--json] [--out FILE]

Input JSON:
    {
      "name": "Order system build",
      "nodes": [
        {"id": "0", "deliverable": "shared event schema", "deps": [], "write_set": ["schema/"]},
        {"id": "1", "deliverable": "intake API", "deps": ["0"], "write_set": ["api/"]},
        ...
      ],
      "loops": [
        {"name": "integration", "nodes": ["7", "8"], "exit": "e2e passes", "bound": "5 rounds"}
      ]
    }

Per node, `deps` (aka `depends_on`) lists the ids it consumes; `write_set` (aka `writes`)
lists every file/resource it mutates, which is what parallel-safety is decided on. `cost`
(default 1) weights the critical path. `loops` is optional.

Output: a Markdown execution-graph document on stdout (or `--out`), or the computed
structure as JSON with `--json`. Exit 0 on a valid graph; exit 1 on a hard error (a
cycle, a dangling dependency, or a write-set collision inside a wave), which is a spec
the fleet cannot run as written. Standard library only (json, graphlib, argparse).
"""
import argparse
import json
import sys
from graphlib import TopologicalSorter, CycleError


def load(path):
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    nodes = {}
    order = []
    for n in spec.get("nodes", []):
        nid = str(n["id"])
        if nid in nodes:
            raise ValueError(f"duplicate node id: {nid}")
        deps = [str(d) for d in (n.get("deps") or n.get("depends_on") or [])]
        ws = list(n.get("write_set") or n.get("writes") or [])
        nodes[nid] = {
            "id": nid,
            "deliverable": n.get("deliverable", ""),
            "deps": deps,
            "write_set": ws,
            "cost": n.get("cost", 1),
        }
        order.append(nid)
    return spec.get("name", "Work"), nodes, order, spec.get("loops", [])


def validate(nodes):
    errors = []
    for nid, n in nodes.items():
        for d in n["deps"]:
            if d == nid:
                errors.append(f"node {nid} depends on itself")
            elif d not in nodes:
                errors.append(f"node {nid} depends on unknown node {d}")
    # Acyclicity via a topological sort over the predecessor map.
    ts = TopologicalSorter({nid: set(n["deps"]) for nid, n in nodes.items()})
    try:
        ts.prepare()
    except CycleError as e:
        errors.append(f"dependency cycle: {' -> '.join(map(str, e.args[1]))}")
    return errors


def descendants(nodes):
    """Reachable-set per node over direct dep edges (dep -> node), memoized."""
    succ = {nid: [] for nid in nodes}
    for nid, n in nodes.items():
        for d in n["deps"]:
            succ[d].append(nid)
    memo = {}

    def reach(u):
        if u in memo:
            return memo[u]
        acc = set()
        for v in succ[u]:
            acc.add(v)
            acc |= reach(v)
        memo[u] = acc
        return acc

    return {u: reach(u) for u in nodes}, succ


def transitive_reduction(nodes, succ, reach):
    """Remove edge u->v when v is reachable from another successor of u. Returns cut edges."""
    cut = []
    reduced = {u: set(vs) for u, vs in succ.items()}
    for u in nodes:
        for v in list(succ[u]):
            if any(v in reach[w] for w in succ[u] if w != v):
                reduced[u].discard(v)
                cut.append((u, v))
    return reduced, sorted(cut)


def levels(nodes):
    """Longest-path level per node = earliest wave it can run in (0-based)."""
    lvl = {}

    def depth(nid):
        if nid in lvl:
            return lvl[nid]
        ds = nodes[nid]["deps"]
        lvl[nid] = 0 if not ds else 1 + max(depth(d) for d in ds)
        return lvl[nid]

    for nid in nodes:
        depth(nid)
    return lvl


def waves(nodes, lvl):
    w = {}
    for nid in sorted(nodes, key=lambda x: (lvl[x], x)):
        w.setdefault(lvl[nid], []).append(nid)
    return [w[k] for k in sorted(w)]


def wave_collisions(nodes, wave):
    """Pairs in a wave that mutate a shared write-set entry (would corrupt each other)."""
    hits = []
    for i, a in enumerate(wave):
        for b in wave[i + 1:]:
            shared = set(nodes[a]["write_set"]) & set(nodes[b]["write_set"])
            if shared:
                hits.append((a, b, sorted(shared)))
    return hits


def critical_path(nodes):
    """Longest path by summed node cost. Returns (path ids, total cost)."""
    best = {}

    def solve(nid):
        if nid in best:
            return best[nid]
        c = nodes[nid]["cost"]
        ds = nodes[nid]["deps"]
        if not ds:
            best[nid] = (c, [nid])
        else:
            bc, bp = max((solve(d) for d in ds), key=lambda t: t[0])
            best[nid] = (bc + c, bp + [nid])
        return best[nid]

    total, path = max((solve(n) for n in nodes), key=lambda t: t[0], default=(0, []))
    return path, total


def indegrees(nodes, reduced):
    indeg = {nid: 0 for nid in nodes}
    for vs in reduced.values():
        for v in vs:
            indeg[v] += 1
    return indeg


def label_shapes(nodes, reduced, wv, barrier_nodes):
    """Deterministic pattern labels, cross-referenced to references/graph-patterns.md."""
    labels = []
    if any(len(w) > 1 for w in wv):
        labels.append("parallel split + synchronization (fan-out/fan-in) on multi-node waves")
    if any(len(reduced[u]) > 1 for u in nodes):
        labels.append("fork at nodes with multiple successors")
    if barrier_nodes:
        labels.append("barrier / synchronizing merge at convergence nodes")
    if all(len(w) == 1 for w in wv) and len(wv) > 1:
        labels.append("sequence / pipeline (no parallelism in this shape)")
    return labels


def compute(path):
    name, nodes, order, loops = load(path)
    errs = validate(nodes)
    if errs:
        return {"name": name, "errors": errs}, nodes, order, loops, None
    reach, succ = descendants(nodes)
    reduced, cut = transitive_reduction(nodes, succ, reach)
    lvl = levels(nodes)
    wv = waves(nodes, lvl)
    collisions = []
    for i, w in enumerate(wv):
        for a, b, shared in wave_collisions(nodes, w):
            collisions.append({"wave": i + 1, "a": a, "b": b, "shared": shared})
    cpath, ctotal = critical_path(nodes)
    indeg = indegrees(nodes, reduced)
    barrier_nodes = sorted(nid for nid, d in indeg.items() if d > 1)
    result = {
        "name": name,
        "errors": [],
        "waves": wv,
        "reduced_edges": {u: sorted(vs) for u, vs in reduced.items()},
        "cut_edges": cut,
        "critical_path": cpath,
        "critical_cost": ctotal,
        "barriers": barrier_nodes,
        "concurrency_cap": max((len(w) for w in wv), default=0),
        "collisions": collisions,
        "labels": label_shapes(nodes, reduced, wv, barrier_nodes),
        "loops": loops,
    }
    return result, nodes, order, loops, reduced


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(str(c) for c in cells) + " |" for cells in rows]
    lines.append("")
    return lines


def render_md(res, nodes, order, reduced):
    L = []
    L.append(f"# {res['name']} — Execution Graph\n")
    L.append("_Generated by graph.py. Edit the input spec, not this file._\n")

    L.append("## Nodes\n")
    L += md_table(
        ["id", "deliverable", "deps", "write-set"],
        [[nid, nodes[nid]["deliverable"],
          ", ".join(nodes[nid]["deps"]) or "—",
          ", ".join(nodes[nid]["write_set"]) or "—"] for nid in order],
    )

    L.append("## DAG\n")
    L.append("```mermaid")
    L.append("flowchart TB")
    for i, w in enumerate(res["waves"]):
        L.append(f"  subgraph W{i + 1}[Wave {i + 1} · {len(w)} parallel]")
        for nid in w:
            L.append(f"    {nid}[\"{nid}: {nodes[nid]['deliverable']}\"]")
        L.append("  end")
    for u in order:
        for v in sorted(reduced[u]):
            L.append(f"  {u} --> {v}")
    L.append("```\n")

    L.append("## Waves\n")
    L += md_table(
        ["wave", "parallel N", "nodes"],
        [[i + 1, len(w), ", ".join(w)] for i, w in enumerate(res["waves"])],
    )

    L.append(f"## Critical path\n\n`{' -> '.join(res['critical_path'])}` "
             f"(cost {res['critical_cost']}). This is the wall-clock floor; adding agents "
             f"beyond the widest wave ({res['concurrency_cap']}) does not shorten it.\n")

    if res["barriers"]:
        L.append(f"## Barriers\n\nConvergence nodes (start only when all inputs are done): "
                 f"{', '.join(res['barriers'])}.\n")

    if res["cut_edges"]:
        L.append("## Eliminated edges (transitive reduction)\n")
        L.append("Redundant dependencies removed because a longer path already implies them:\n")
        for u, v in res["cut_edges"]:
            L.append(f"- {u} -> {v}")
        L.append("")

    if res["loops"]:
        L.append("## Loop register\n")
        L += md_table(
            ["loop", "nodes", "exit condition", "bound"],
            [[lp.get("name", "?"), ", ".join(map(str, lp.get("nodes", []))),
              lp.get("exit", "?"), lp.get("bound", "?")] for lp in res["loops"]],
        )

    if res["labels"]:
        L.append("## Pattern shapes\n")
        L.append("Detected shapes (see `references/graph-patterns.md`):\n")
        for lab in res["labels"]:
            L.append(f"- {lab}")
        L.append("")

    L.append(f"## Concurrency cap\n\nWidest wave = {res['concurrency_cap']} → a "
             f"{res['concurrency_cap']}-agent fleet saturates this plan; more idle.")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--json", action="store_true", help="emit the computed structure as JSON")
    ap.add_argument("--out", help="write output to a file instead of stdout")
    args = ap.parse_args()

    try:
        res, nodes, order, loops, reduced = compute(args.spec)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if res["errors"]:
        for e in res["errors"]:
            print(f"FAIL {e}", file=sys.stderr)
        return 1

    if res["collisions"]:
        for c in res["collisions"]:
            print(f"FAIL wave {c['wave']}: nodes {c['a']} and {c['b']} both write "
                  f"{c['shared']} — split one or add a dependency so they don't run together",
                  file=sys.stderr)
        return 1

    out = json.dumps(res, indent=2) if args.json else render_md(res, nodes, order, reduced)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out + ("\n" if not out.endswith("\n") else ""))
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
