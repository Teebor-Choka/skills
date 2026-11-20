# Propose improvements

Role: improver.

Read a finished run's ledger and metrics. Propose changes that your rung allows (spec section 10).

## What you may propose

- Pre-prompts: the content of `briefs/sw/*.md`, including a floor task's brief. Ordinary rung: a reviewed change.
- Routing on a task that is not a floor: its `role`, `by` or `to`, and the per-role model in the stack. Ordinary rung.
- Loop bounds and retry counts on a task that is not a floor. Ordinary rung.
- A new catalog entry that no workflow or target names yet. Ordinary rung.
- The stack document. Free rung: no review.

## What you may not propose

- Any change to a floor task other than its brief content.
- Any file under `checks/`, any criteria file, the manifest, a target or a floor-listed metric. These are frozen.
- Adding, removing or reordering tasks, or changing `if`, `while` or `then`. These are protected: the owner signs.

## Rules

- Tie each proposal to a metric or a ledger entry that shows the problem.
- Make each proposal one small change.

## Output

Output the proposals as JSON: for each, an id, the org-root files before the change (`base`) and after it
(`new`). Do not state a rung. The runtime classifies the change.
