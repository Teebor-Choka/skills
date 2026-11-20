# Cut the design into units

Role: lead.

Cut the design into units that agents can build in parallel. Output the cut as JSON that matches schemas/org/units.json.

## Rules

- Give each unit one goal and one write-set.
- Make write-sets disjoint: no two units may write the same file or one inside the other's directory.
- List the criteria each unit serves.
- State dependencies between units.

## Output

The write-sets-are-disjoint script runs on the output. A shared file means you must merge the units or add a dependency.

## Order

The build runs the units one after another, in the order of `depends_on` (a sequential `for`). Keep write-sets disjoint anyway, so a later parallel build stays safe. A unit may rely on an earlier unit's files only through `depends_on`. Do not give a unit the acceptance test files, `checks/`, `criteria/`, `bin/`, `collectors/`, `manifest.json` or `metrics.json` in its write-set.
