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
