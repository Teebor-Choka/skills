# The decomposition-depth dial

How **far down** the architect decomposes before it stops cutting boxes. The architect works
top-down — APIs and interfaces first, then into specifics and how to chop the system into
thin-interface-compliant pieces — and this dial sets where that descent stops.

> This is a _decomposition-depth_ knob, not a context/token budget. (It supersedes the earlier
> "context dial" framing.) It governs the grain of the spec blocks, nothing about token counts.

## The ladder

Coarse → fine:

| rung         | the boxes are cut at the grain of…                      |
| ------------ | ------------------------------------------------------- |
| `interfaces` | the public APIs / contracts between parts; no internals |
| `modules`    | the modules behind those interfaces                     |
| `components` | the components inside a module                          |
| `functions`  | individual functions / units                            |

Semantics: **decompose from the root down to and including the dialed rung, then stop.** `interfaces`
yields only interface-grain boxes; `functions` drills all the way down. The architect may refine the
rungs from the role's input (a domain may name its own intermediate levels), but the top-down,
stop-at-rung meaning is fixed.

## Input

The depth — and the scope it applies to — is **given per invocation**. If it was not provided, the
architect **asks**; it never silently picks a default rung.

## Output grain and layered ATDD

The dial sets the **leaf grain** of the emitted blocks and the DAG. ATDD is a **cycle across every
rung traversed**: it writes **separate acceptance criteria at each depth**, not only at the leaf. A
run dialed to `components` carries acceptance at interfaces, then modules, then components — each
rung's contract tested at its own grain (interface-contract tests, then module, then component).
Deeper rungs refine, they do not replace, the acceptance of the rungs above them.

## Relation to `:improve`

Both reason about module depth, and roughly share the depth concept, but normal depth-dialed scoping
and `:improve` (scoping an _existing_ codebase for deepening; `references/improve.md`) are **different
processes**. Cross-reference them; do not merge them.
