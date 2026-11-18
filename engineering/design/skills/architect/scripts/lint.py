#!/usr/bin/env python3
"""Lint an architect work package for completeness and internal consistency.

Judgment (what to write) stays with the author; this checks only that the package is
well-formed: the mechanical invariants a reader or a fleet of agents relies on. Every
finding names a file, a rule, and what is wrong, so it reads like a checklist.

Usage:
    lint.py <work-package-dir> [--tier note|small|full] [--strict]

Exit code 0 if no errors (warnings allowed), else 1. `--strict` also fails on warnings.
Standard library only (re, os, glob, graphlib, argparse), so it runs anywhere Python 3.9+
does. No YAML dependency: every check is heading- or regex-based.

`--tier note` checks only the single `<slug>-plan.md` (E1/E2/E3): there is no package to keep
internally consistent, so the cross-document rules (E4-E8) do not apply.

The rules, keyed to the document set:
  E1  required artifacts present and non-empty (tier-dependent)
  E2  required headings present in each artifact
  E3  no leftover scaffold placeholders (TODO, TBD, $slug, <name>, <Title>, FILL-IN); code spans and fences are exempt
  E4  every spec block has BOTH a Verification and an Adversarial test table, each with >=1 row
  E5  every decision-log entry carries a Status (Proposed|Accepted|Deprecated|Superseded)
  E6  research-notes.md and the proposal each carry a Sources section with >=1 URL
  E7  the development graph is acyclic (graphlib), and its edges match the spec block table
  E8  every relative markdown link resolves to a file that exists
  E9  the spec states the decomposition depth (interfaces|modules|components|functions), says the
      user gave it, and carries acceptance criteria at every rung from interfaces down to it
  E10 two blocks whose write-sets overlap are ordered by a dependency edge or both declare the same
      `Coordination channel:`; sharing a write-set implicitly is an error
  W1  a spec block declares a requirement backlink (task -> requirement traceability)
  W2  the README names a hinge decision and lists open items
  W3  the Block index has no Write-set column, so isolation cannot be checked

`--improve` lints a single `:improve` report instead of a package (rules I-*, see check_improve).
"""
import argparse
import glob
import os
import re
import sys
from graphlib import TopologicalSorter, CycleError

PLACEHOLDERS = [r"\bTODO\b", r"\bTBD\b", r"\bFILL-IN\b", r"\$slug\b", r"\$title\b",
                r"<name>", r"<Title>", r"<slug>", r"<TICKET>", r"<n>"]

SMALL_FILES = ["README.md", "decision-log.md"]  # plus one *-proposal.md and one *-spec.md
FULL_EXTRA = ["research-notes.md", "development-graph.md", "agent-methodology.md",
              "test-methodology.md", "invariants.md"]

REQUIRED_HEADINGS = {
    "README.md": ["Read in this order", "Status", "hinge", "Environments"],
    "decision-log.md": ["Verified facts", "Decisions", "Considered and set aside", "Open items"],
    "research-notes.md": ["Sources"],
    "development-graph.md": ["Waves"],
    "agent-methodology.md": ["GREEN"],
    "test-methodology.md": ["Acceptance"],
    "invariants.md": ["Invariants"],
}

# note tier: the single plan must still carry a goal and a positive+adversarial acceptance gate.
PLAN_REQUIRED = ["Goal", "Acceptance"]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def find_one(root, suffix):
    hits = sorted(glob.glob(os.path.join(root, f"*{suffix}")))
    return hits[0] if hits else None


# Fenced blocks and inline code may name a placeholder on purpose (a doc about the scaffold).
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def check_placeholders(path, text, errs):
    text = CODE.sub("", text)
    for pat in PLACEHOLDERS:
        if re.search(pat, text):
            errs.append(f"E3 {os.path.basename(path)}: leftover placeholder matching /{pat}/")


def check_headings(path, text, errs):
    name = os.path.basename(path)
    for needle in REQUIRED_HEADINGS.get(name, []):
        if needle.lower() not in text.lower():
            errs.append(f"E2 {name}: missing required section mentioning '{needle}'")


def check_spec(spec_path, errs, warns):
    """E4: each block has both test tables with a data row. W1: requirement backlink."""
    text = read(spec_path)
    # Split on numbered block headings only: "## Block 0", "### Block 12" (not "## Block index").
    blocks = re.split(r"(?m)^#{2,3}\s+Block\s+(?=\d)", text)
    if len(blocks) <= 1:
        errs.append(f"E4 {os.path.basename(spec_path)}: no 'Block N' sections found")
        return
    for chunk in blocks[1:]:
        label = chunk.splitlines()[0].strip() if chunk.strip() else "?"
        low = chunk.lower()
        has_pos = bool(re.search(r"(verification|positive)[^\n]*test", low))
        has_adv = bool(re.search(r"(adversarial|negative)[^\n]*test", low))
        # A data row is a table line that is not the header or the |---| separator.
        rows = [ln for ln in chunk.splitlines()
                if ln.strip().startswith("|") and not re.match(r"^\s*\|[\s:|-]+\|\s*$", ln)]
        data_rows = len(rows) - 2 if len(rows) >= 2 else 0
        if not has_pos:
            errs.append(f"E4 spec Block {label}: no Verification (positive) test table")
        if not has_adv:
            errs.append(f"E4 spec Block {label}: no Adversarial (negative) test table")
        if data_rows < 1:
            errs.append(f"E4 spec Block {label}: test tables have no data rows")
        if not re.search(r"(requirement|satisfies|REQ-)", chunk, re.I):
            warns.append(f"W1 spec Block {label}: no requirement backlink (task -> requirement)")


LADDER = ["interfaces", "modules", "components", "functions"]


def section(text, heading):
    """Body of the `## heading` section (up to the next `## `), or None when absent."""
    m = re.search(rf"(?ims)^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text)
    return m.group(1) if m else None


def table_rows(body):
    """Data rows of the first markdown table in body, as cell lists, plus its header cells."""
    lines = [ln for ln in body.splitlines() if ln.strip().startswith("|")]
    sep = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
    cells = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines if not sep.match(ln)]
    return (cells[0], cells[1:]) if cells else ([], [])


def check_depth(text, errs):
    """E9: depth dialed per invocation, acceptance at each rung from interfaces to the dialed one."""
    body = section(text, "Decomposition depth")
    if body is None:
        errs.append("E9 spec: no '## Decomposition depth' section (ask the user for depth and scope)")
        return
    m = re.search(r"\*\*Dialed rung:\*\*\s*([A-Za-z-]+)", body)
    rung = m.group(1).lower() if m else ""
    if rung not in LADDER:
        errs.append(f"E9 spec: dialed rung '{rung or 'missing'}' is not one of {'|'.join(LADDER)}")
        return
    g = re.search(r"\*\*Given by:\*\*\s*(.+)", body)
    if not g or re.search(r"default|assum|guess|infer", g.group(1), re.I):
        errs.append("E9 spec: 'Given by' must say the user gave the depth; a silent default is not allowed")
    acc = section(text, "Acceptance by rung") or ""
    _, rows = table_rows(acc)
    have = {r[0].lower(): r[1] for r in rows if len(r) >= 2 and r[1].strip()}
    for r in LADDER[: LADDER.index(rung) + 1]:
        if r not in have:
            errs.append(f"E9 spec: no acceptance criteria for traversed rung '{r}'")


def _block_chunks(text):
    parts = re.split(r"(?m)^#{2,3}\s+Block\s+(?=\d)", text)
    return {re.match(r"[\w.-]+", c).group(0): c for c in parts[1:] if re.match(r"[\w.-]+", c)}


def _overlap(a, b):
    a, b = a.strip("/"), b.strip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def check_write_sets(text, errs, warns):
    """E10: overlapping write-sets need an ordering edge or a shared declared channel."""
    m = re.search(r"(?ms)^#{2,3}\s+Block index\s*$(.*?)(?=^#{1,3}\s|\Z)", text)
    header, rows = table_rows(m.group(1)) if m else ([], [])
    low = [h.lower() for h in header]
    wi = next((i for i, h in enumerate(low) if "write" in h), None)
    if wi is None:
        warns.append("W3 spec: Block index has no Write-set column; isolation cannot be checked")
        return
    ni = low.index("#") if "#" in low else 0
    sets = {}
    for r in rows:
        if len(r) > max(wi, ni) and re.match(r"^[\w.-]+$", r[ni]):
            sets[r[ni]] = [w.strip() for w in re.split(r"[,;]", r[wi]) if w.strip() not in ("", "-")]
    succ = {}
    for dep, node in parse_block_deps(text):
        succ.setdefault(dep, set()).add(node)

    def reach(a, b, seen=()):
        return b in succ.get(a, ()) or any(reach(n, b, seen + (a,)) for n in succ.get(a, ()) if n not in seen)

    chunks = _block_chunks(text)

    def channel(n):
        c = re.search(r"Coordination channel:\*{0,2}\s*(\S+)", chunks.get(n, ""))
        return c.group(1) if c else None

    ids = list(sets)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if not any(_overlap(x, y) for x in sets[a] for y in sets[b]):
                continue
            if reach(a, b) or reach(b, a):
                continue
            if channel(a) and channel(a) == channel(b):
                continue
            errs.append(f"E10 spec: blocks {a} and {b} share a write-set with no dependency edge "
                        "and no shared 'Coordination channel:' declared in both")


def check_improve(text, errs):
    """`:improve` report: target/grounding/location given, honest empty result, capped boxes."""
    def field(name):
        m = re.search(rf"\*\*{name}:\*\*[ \t]*(.+)", text)
        return m.group(1).strip() if m else ""
    for name in ("Target", "Grounding", "Output location", "Box cap"):
        if not field(name):
            errs.append(f"I1 improve report: '{name}' is not stated")
    grounding = field("Grounding").lower()
    if grounding and "graph" not in grounding and not ("direct read" in grounding and "warn" in grounding):
        errs.append("I2 improve report: Grounding must name the code graph, or 'direct read' with a warning")
    boxes = re.split(r"(?m)^###\s+Box\s+(?=\d)", "\n" + (section(text, "Boxes") or ""))[1:]
    header, rows = table_rows(section(text, "All findings") or "")
    ei = next((i for i, h in enumerate(h.lower() for h in header) if h == "emitted"), None)
    emitted = [r[ei].lower().startswith("y") for r in rows if ei is not None and len(r) > ei]
    if "nothing worth deepening" in (section(text, "Result") or "").lower():
        if boxes or rows:
            errs.append("I3 improve report: 'nothing worth deepening' must come with no boxes and no findings")
        return
    if not boxes:
        errs.append("I3 improve report: no boxes and no 'nothing worth deepening' result")
    cap = field("Box cap")
    if cap.isdigit() and len(boxes) > int(cap):
        errs.append(f"I4 improve report: {len(boxes)} boxes exceed the cap of {cap}")
    for c in boxes:
        label = c.splitlines()[0].strip()
        if "acceptance" not in c.lower():
            errs.append(f"I5 improve report: Box {label} has no acceptance criteria")
        if "deep with tiny interfaces" not in c.lower():
            errs.append(f"I5 improve report: Box {label} lacks the deep-module invariant")
    if sum(emitted) != len(boxes):
        errs.append("I6 improve report: rows marked emitted do not match the box count")
    if emitted != sorted(emitted, reverse=True):
        errs.append("I6 improve report: emitted rows must be the top-ranked ones, listed first")
    if not all(emitted) and not (section(text, "Not emitted") or "").strip():
        errs.append("I6 improve report: findings below the cap need a 'Not emitted' tail note")


def check_decision_log(path, errs):
    """E5: each decision entry carries a Status."""
    text = read(path)
    # Decision entries look like "### D1" or "**D1" or a "Decision" row.
    entries = re.findall(r"(?ms)^#{2,4}\s*D\d+.*?(?=^#{2,4}\s*D\d+|\Z)", text)
    if not entries:
        # Fall back: at least one Status token must exist in the file.
        if not re.search(r"Status\s*[:|]", text):
            errs.append("E5 decision-log.md: no decisions with a Status field found")
        return
    for e in entries:
        head = e.splitlines()[0].strip()
        # Tolerate markdown around the field: "- **Status:** Accepted", "| Status | Accepted |".
        if not re.search(r"status\W{0,4}(proposed|accepted|deprecated|superseded)", e, re.I):
            errs.append(f"E5 decision-log.md: '{head}' has no Status "
                        "(Proposed|Accepted|Deprecated|Superseded)")


def check_sources(root, proposal, errs):
    for path in [find_one(root, "research-notes.md"), proposal]:
        if not path or not os.path.exists(path):
            continue
        text = read(path)
        if "## sources" not in text.lower():
            errs.append(f"E6 {os.path.basename(path)}: no '## Sources' section")
        elif not re.search(r"https?://|\]\(\.{0,2}/", text):
            errs.append(f"E6 {os.path.basename(path)}: Sources section cites no URL or path")


def parse_dag(text):
    """Return (edges, nodes) from mermaid 'A --> B' lines."""
    edges, nodes = set(), set()
    for m in re.finditer(r"(?m)^\s*([\w./-]+)\s*-->\s*([\w./-]+)", text):
        a, b = m.group(1), m.group(2)
        edges.add((a, b))
        nodes.update([a, b])
    return edges, nodes


def parse_block_deps(spec_text):
    """Return dependency edges from the 'Block index' table only, using its column headers.

    Reads the table under the '## Block index' heading, finds the node column (header '#')
    and the 'Depends on' column by name, and builds (dep -> node) edges. Other tables in the
    spec (test tables, tech/licensing, escalation) are ignored.
    """
    edges = set()
    m = re.search(r"(?ms)^#{2,3}\s+Block index\s*$(.*?)(?=^#{1,3}\s|\Z)", spec_text)
    if not m:
        return edges
    rows = [ln for ln in m.group(1).splitlines() if ln.strip().startswith("|")]
    if len(rows) < 2:
        return edges

    def cells(ln):
        return [c.strip() for c in ln.strip().strip("|").split("|")]

    header = [h.lower() for h in cells(rows[0])]
    try:
        node_i = header.index("#")
    except ValueError:
        node_i = 0
    dep_i = next((i for i, h in enumerate(header) if "depend" in h), None)
    if dep_i is None:
        return edges
    for ln in rows[1:]:
        if re.match(r"^\s*\|[\s:|-]+\|\s*$", ln):  # separator row
            continue
        c = cells(ln)
        if len(c) <= max(node_i, dep_i):
            continue
        node = c[node_i]
        if not re.match(r"^[\w.-]+$", node):
            continue
        for dep in re.split(r"[,\s]+", c[dep_i]):
            if re.match(r"^[\w.-]+$", dep) and dep.lower() not in ("-", "none") and dep != node:
                edges.add((dep, node))
    return edges


def check_dag(root, spec_path, errs, warns):
    """E7: acyclic + edges match the spec block table (set-equality, both directions)."""
    graph_path = find_one(root, "development-graph.md")
    if not graph_path:
        return  # absent graph is a tier question, handled by E1
    edges, nodes = parse_dag(read(graph_path))
    if not edges:
        warns.append("E7 development-graph.md: no mermaid 'A --> B' edges parsed")
        return
    ts = TopologicalSorter()
    succ = {}
    for a, b in edges:
        succ.setdefault(b, set()).add(a)
    for node, preds in succ.items():
        ts.add(node, *preds)
    try:
        ts.prepare()
    except CycleError as e:
        errs.append(f"E7 development-graph.md: DAG has a cycle: {e.args[1]}")
    if spec_path:
        spec_edges = parse_block_deps(read(spec_path))
        if spec_edges:
            only_graph = edges - spec_edges
            only_spec = spec_edges - edges
            if only_graph:
                warns.append(f"E7 edges in graph not in spec block table: {sorted(only_graph)}")
            if only_spec:
                warns.append(f"E7 spec dependencies missing from graph: {sorted(only_spec)}")


def check_links(root, errs):
    """E8: relative markdown links resolve."""
    for md in glob.glob(os.path.join(root, "**", "*.md"), recursive=True):
        text = read(md)
        for m in re.finditer(r"\]\((?!https?://|#|mailto:)([^)#]+)(?:#[^)]*)?\)", text):
            target = m.group(1).strip()
            if not target:
                continue
            resolved = os.path.normpath(os.path.join(os.path.dirname(md), target))
            if not os.path.exists(resolved):
                errs.append(f"E8 {os.path.relpath(md, root)}: dead link -> {target}")


def check_readme_hinge(root, warns):
    readme = os.path.join(root, "README.md")
    if os.path.exists(readme):
        text = read(readme).lower()
        if "hinge" not in text and "the one decision" not in text:
            warns.append("W2 README.md: no hinge decision named")
        if "open item" not in text:
            warns.append("W2 README.md: no open items listed")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("--tier", choices=["note", "small", "full"], default="full")
    ap.add_argument("--improve", action="store_true", help="lint one :improve report file")
    ap.add_argument("--strict", action="store_true", help="fail on warnings too")
    args = ap.parse_args()

    root = args.dir
    if args.improve:
        errs = []
        text = read(root)
        check_placeholders(root, text, errs)
        check_improve(text, errs)
        for e in errs:
            print(f"FAIL {e}")
        print(f"\n1 report checked, {len(errs)} error(s).")
        return 0 if not errs else 1
    if not os.path.isdir(root):
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 2

    errs, warns = [], []

    # note tier: one self-contained plan, no cross-document checks.
    if args.tier == "note":
        plan = find_one(root, "-plan.md")
        if not plan:
            errs.append("E1 missing required artifact: *-plan.md")
        elif not read(plan).strip():
            errs.append("E1 empty artifact: *-plan.md")
        else:
            text = read(plan)
            name = os.path.basename(plan)
            for needle in PLAN_REQUIRED:
                if needle.lower() not in text.lower():
                    errs.append(f"E2 {name}: missing required section mentioning '{needle}'")
            check_placeholders(plan, text, errs)
        for e in errs:
            print(f"FAIL {e}")
        print(f"\n1 plan checked, {len(errs)} error(s), 0 warning(s).")
        return 0 if not errs else 1

    proposal = find_one(root, "-proposal.md")
    spec = find_one(root, "-spec.md")

    # E1 required artifacts.
    required = list(SMALL_FILES)
    if args.tier == "full":
        required += FULL_EXTRA
    for name in required:
        p = os.path.join(root, name)
        if not os.path.exists(p):
            errs.append(f"E1 missing required artifact: {name}")
        elif not read(p).strip():
            errs.append(f"E1 empty artifact: {name}")
    if not proposal:
        errs.append("E1 missing required artifact: *-proposal.md")
    if not spec:
        errs.append("E1 missing required artifact: *-spec.md")

    # E2 / E3 across all present markdown.
    for md in glob.glob(os.path.join(root, "*.md")):
        text = read(md)
        check_headings(md, text, errs)
        check_placeholders(md, text, errs)

    # E4 spec, E5 decisions, E6 sources, E7 dag, E8 links, W2 readme.
    if spec:
        check_spec(spec, errs, warns)
        check_depth(read(spec), errs)
        check_write_sets(read(spec), errs, warns)
    dlog = os.path.join(root, "decision-log.md")
    if os.path.exists(dlog):
        check_decision_log(dlog, errs)
    check_sources(root, proposal, errs)
    check_dag(root, spec, errs, warns)
    check_links(root, errs)
    check_readme_hinge(root, warns)

    for w in warns:
        print(f"WARN {w}")
    for e in errs:
        print(f"FAIL {e}")

    ok = not errs and (not warns or not args.strict)
    n = len(glob.glob(os.path.join(root, "**", "*.md"), recursive=True))
    print(f"\n{n} markdown file(s) checked, {len(errs)} error(s), {len(warns)} warning(s).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
