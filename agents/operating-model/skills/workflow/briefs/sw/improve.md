# Propose improvements

Role: improver.

Read a finished run's ledger and metrics. Change the files in the working tree to improve the process. Make only changes that your rung allows (spec section 10).

## What you may change

- Pre-prompts: the content of `briefs/sw/*.md`, including a floor task's brief. Ordinary rung: a reviewed change.
- Routing on a task that is not a floor: its `role`, `by` or `to`, and the per-role model in the stack. Ordinary rung.
- Loop bounds and retry counts on a task that is not a floor. Ordinary rung.
- A new catalog entry that no workflow or target names yet. Ordinary rung.
- The stack document. Free rung: no review.

## What you may not change

- A floor task, other than its brief content.
- Any file under `checks/`, any criteria file, the manifest, a target or a floor-listed metric. These are frozen.
- The set or order of tasks, or `if`, `while` or `then`. These are protected: the owner signs.

## Rules

- Tie each change to a metric or a ledger entry that shows the problem.
- Make each change one small change.
- You write files only. The runtime compares the working tree with the committed head and classifies the change itself.

## Output

Write a short note that lists each changed file and the metric or ledger entry behind it.
