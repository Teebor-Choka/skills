# `:improve` — architect, run against an existing codebase

The main workflow starts from a fuzzy ask and designs forward. `:improve` runs the other direction:
start from code you already have, find where its structure is paying interest, and feed the worst
offender into the same design flow. It is the deepening pass — turning shallow modules deep, leaky
interfaces narrow — not a greenfield design.

Use it when the ask is "make this codebase better to work in / build on," when a bug turned out to
have no good seam to lock it down, or in a spare moment of upkeep. For a new capability, use the main
flow; `:improve` is for structure that already exists.

## The move

1. **Ground in the graph, don't recall.** Build or refresh the code graph (codegraph preferred;
   `references/code-graphing.md`) and read the real coupling — afferent/efferent edges, call depth,
   module sizes. The graph is the input; a hand-read of a few files is not.
2. **Scan for shallow modules and leaky seams.** Rank every module by **depth** — how much it hides
   behind how small an interface (Ousterhout; `references/principles.md` §9–10). The opportunities are
   the inversions of the structural red flags already in §9:
   - **Shallow module** — a large or complex interface over a thin implementation; the interface costs
     more than it saves. Deepen it or fold it in.
   - **Information leakage** — the same design decision smeared across several modules; a change forces
     edits in lockstep. Pull it behind one.
   - **Pass-through / temporal decomposition** — a layer that only forwards calls, or modules split by
     _when_ things run rather than _what_ they know. Collapse or re-cut the seam.
   - **Boundary leak** — implementation types (an ORM row, a transport frame) escaping their module.
3. **Rank by leverage, not count.** Order candidates by complexity hidden ÷ interface widened, times
   blast radius — the change that deepens the most behind the smallest, safest interface wins. Cite
   each to its graph evidence (the coupling edges, the call sites).
4. **Present, then let the user pick.** A short ranked list, each candidate with its current vs.
   proposed interface shape (the before/after seam) and the leverage estimate. Don't fan out; surface
   the few that matter.
5. **Feed the pick into the main flow.** The chosen deepening becomes a normal architect package at
   its blast-radius tier (often `small`: a proposal + decision-log + spec with tests). Carry the
   **deep-module invariant** into `invariants.md` — _components and libraries stay deep: a large
   implementation behind a tiny, stable interface_ — so every brief inherits it and the fix doesn't
   regress on the next change.

## What it reuses

Nothing new: the code-graph grounding (`code-graphing.md`), the deep-module and connascence theory
(`principles.md` §9–10), the tiering and the normal document set. `:improve` is an _entry_ — it finds
the work and names the invariant; the main workflow does the rest.
