# Cost, workspace, integration

## Tiers: run the cheap work cheap

Pick the lowest tier that does the task right. Tier names map to models in the host config.

- **Dispatcher, steward, curator, reporter, watchers: Light.** Reading large context and emitting a
  few tokens is light work. Running it on the Reasoning tier is the common waste.
- **Workers: Execution.** Pass the Execution model as the spawn override. A worker must not
  inherit a Reasoning-tier parent: that silently runs every worker on the costliest model.
- **Advisors and hard design nodes: Reasoning**, sparingly. An advisor exists to answer what a
  cheaper agent cannot.
- Escalate a stalled node one tier up. Do not run everything high.

`decompose` assigns a tier per unit. The charter assigns a tier per role.

## Bounded width

Match the number of concurrent agents to the work, not to the budget. Extra agents add cost and
duplicate findings, not coverage. Cap concurrent writers by the charter (and by the
write-set collisions `decompose` reports).

## Workspace per agent

Parallel writers must not share a workspace: one writer's switch or reset drops another's
uncommitted work. Use the workspace the policy names (`work.isolation`: `worktree`, `branch`,
or `none`), unless the charter overrides it. Default for parallel writers: `worktree`. Read-only
roles need none. For non-code work, `none` is valid if the items' write-sets are disjoint.

## Serial integration pass

Isolated contexts do not integrate themselves. After a wave or when units finish:

1. Combine the units in dependency order.
2. Run the charter's whole-result check on the combined result (for code: the full test run and
   a review of the combined diff).
3. Approval binds to a revision (`mechanics.md` rule 7). Any change after approval returns to its gate.
4. Clean up workspaces only after the whole-result check passes.

How code lands (merge queue, rebase, PR ownership) is `git-workflow`'s job.
