# Work packages: isolated, ordered, filed to the policy destination

The architect's job ends when the work packages exist and are filed. Dispatch, execution and
integration belong to other processes (`decompose` files per-unit items; `harness:assign`,
`harness:pull` and `implement` run them). The architect never dispatches, executes or integrates.

## Split via graph-engine

Cut the spec blocks into the most isolated packages the **graph-engine** skill can find: disjoint
write-sets, listed in the Block index (workflow step 5). `graph.py` computes the waves and catches
write-set collisions; the architect only names the nodes, their true dependencies and their
write-sets. Lint E10 rejects a shared write-set with no ordering edge and no shared channel marker.

## Blocked by / blocks

Every block carries both lines, so execution order is readable without the whole set:

```
**Blocked by:** 0, 1
**Blocks:** none
```

Ids come from the Block index `Depends on` column; `none` is the explicit empty value. Lint E11
fails a block with a missing line or a list that disagrees with the index.

## Destination

Where the packages are filed is a policy input, never hardcoded: the `--destination` arg, then the
`.agents/policy` key `work-package` (for example `work-package: issues`), read by the same policy
loader and with the same arg-then-policy order as every other input (`scripts/resolve_input.py`).
`work.tracker` is the deprecated fallback; when both are set and differ `work-package` wins and the line notes `work.tracker` was ignored. `:improve` output reads the same chain. Unset, it defaults to `issues` (`github issues` reads as `issues`), a stated default written into the spec's `**Destination:**` line
with its source. The schema of the key's value is not settled yet.

## Optional coordination channel (declaration only)

When two blocks cannot be made disjoint and an ordering edge does not fit, declare the same
`Coordination channel: <name>` line in both blocks. It is a marker: the architect never opens or
runs the channel; the executor does.
